#!/usr/bin/env python3

import sqlite3
from flask import render_template, request, session, redirect, url_for, flash, send_file
import pandas as pd
from datetime import datetime
import re
from zipfile import ZipFile
from tempfile import TemporaryDirectory
from os import path, remove
import glob

# import global config
from ..config import conf
from ..session import check_logged_in

#
from .genomes import get_assembly_grade

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('query', __name__)


@blueprint.route("/query/", methods=['POST', 'GET'])
def page_main():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))

    # if submitting a job
    if request.method == 'POST':
        
        # validate and parse input sequences
        input_validated, input_proteins = parse_input_prots(request.form["protsequences"])

        if not input_validated:
            flash("Failed to submit query: '{}'. please check your input sequences".format(
                input_proteins
            ), "alert-danger")
            return redirect(url_for("query.page_main"))

        # check if user have a pending submitted job
        user_jobs_pending_count = pd.read_sql((
            "select count(jobs.id) from jobs,status_enum"
            " where userid=? and jobs.status=status_enum.code"
            " and status_enum.code in ('PENDING', 'PROCESSING')"
        ), sqlite3.connect(conf["query_db_path"]), params=(session["userid"],)).iloc[0, 0]
        if user_jobs_pending_count > 0:
            flash("Failed to submit query: you still have a submission in progress", "alert-danger")
            return redirect(url_for("query.page_main"))

        # submit the new job
        job_id = submit_new_job(session["userid"], input_proteins)

        # redirect to the job's page
        return redirect(url_for("query.page_job", job_id=job_id))
        
    # page title
    page_title = "BLAST Query"
    page_subtitle = ("")

    # render view
    return render_template(
        "query/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )


@blueprint.route("/query/result/<int:job_id>")
def page_job(job_id):

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))

    # get job data
    job_data = pd.read_sql((
        "SELECT jobs.*, status_enum.name as status_desc"
        " FROM jobs, status_enum"
        " WHERE userid=? AND jobs.id=? and jobs.status=status_enum.code"
    ), sqlite3.connect(conf["query_db_path"]), params=(session["userid"], job_id))

    if job_data.shape[0] != 1:
        flash("Can't find the specified job id", "alert-danger")
        return redirect(url_for("query.page_main"))

    job_data = job_data.iloc[0].to_dict()

    # get protein queries
    job_data["proteins"] = {row["id"]: row["name"] for idx, row in pd.read_sql((
        "SELECT id, name FROM query_proteins"
        " WHERE jobid=?"
    ), sqlite3.connect(conf["query_db_path"]), params=(job_id,)).iterrows()}

    # page title
    page_title = "Query result: job #{}".format(job_id)
    page_subtitle = ("")

    # render view
    return render_template(
        "query/job.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle,
        auto_refresh=(job_data["status_desc"] in ["PROCESSING", "PENDING"]),
        job_id=job_data["id"],
        job_status=job_data["status_desc"],
        job_submitted=job_data["submitted"][:16],
        job_finished=job_data["finished"][:16] if job_data["finished"] else "",
        job_proteins=job_data["proteins"]
    )


def parse_input_prots(prot_seq):
    name = ""
    seq = ""
    results = {}
    for line in prot_seq.split("\n"):
        line = line.rstrip("\r")
        if line.startswith(">"):
            if name != "":                
                if name in results: # double naming
                    return False, "duplicated protein ids"
                if re.fullmatch(r"([ABCDEFGHIKLMNPQRSTUVWYZX\*-]+)", seq) == None:
                    return False, "fasta protein sequence format unrecognized"
                if len(seq) < 50: # too short of a protein
                    return False, "AA too short (min. 50)"
                if len(seq) > 30000: # too short of a protein
                    return False, "AA too long (max. 30,000)"
                results[name] = seq
                name = ""
            name = line[1:].split(" ")[0].replace(",", "_")
            seq = ""
        else:
            if name == "": # format error
                print("d")
                return False, {}
            seq += line.upper()

    if name != "":
        if name in results: # double naming
            return False, "duplicated protein ids"
        if re.fullmatch(r"([ABCDEFGHIKLMNPQRSTUVWYZX\*-]+)", seq) == None:
            return False, "fasta protein sequence format unrecognized"
        if len(seq) < 50: # too short of a protein
            return False, "AA too short (min. 50)"
        if len(seq) > 30000: # too short of a protein
            return False, "AA too long (max. 30,000)"
        results[name] = seq

    return True, results


@blueprint.route("/api/query/get_list")
def get_list():

    # check login
    if not check_logged_in():
        return ""

    result = {}
    result["draw"] = request.args.get('draw', type=int)
    limit = request.args.get('length', type=int)
    offset = request.args.get('start', type=int)

    with sqlite3.connect(conf["query_db_path"]) as con:
        cur = con.cursor()

        # fetch total records
        result["recordsTotal"] = cur.execute((
            "select count(id)"
            " from jobs"
            " where userid=?"
        ), (session["userid"],)).fetchall()[0][0]

        # fetch total records (filtered)
        result["recordsFiltered"] = cur.execute((
            "select count(id)"
            " from jobs"
            " where userid=?"
        ), (session["userid"],)).fetchall()[0][0]

        result["data"] = []

        query_result = pd.read_sql_query((
            "select jobs.id, status_enum.name as status, jobs.submitted, jobs.finished,"
            " group_concat(query_proteins.name) as input_proteins"
            " from jobs, status_enum inner join query_proteins"
            " on query_proteins.jobid=jobs.id"
            " where userid=? and status_enum.code=jobs.status"
            " group by jobs.id"
            " order by jobs.id desc"
            " limit ? offset ?"
        ), con, params=(session["userid"], limit, offset))

        for idx, row in query_result.iterrows():
            result["data"].append([
                (row["status"], row["id"]),
                row["input_proteins"].split(","),
                row["submitted"][:19],
                row["finished"][:19] if row["finished"] != None else ""
            ])

    return result


def submit_new_job(user_id, input_proteins):
    
    with sqlite3.connect(conf["query_db_path"]) as con:

        # submit job and get the new id back
        cur = con.cursor()
        cur.execute((
            "INSERT INTO jobs (userid, submitted, status)"
            " VALUES (?, ?, ?)"
        ), (user_id, datetime.now(), -2))
        con.commit()
        job_id = cur.lastrowid

        # submit protein sequences
        cur.executemany((
            "INSERT INTO query_proteins (jobid, name, aa_seq)"
            " VALUES (?, ?, ?)"
        ), (
            [(job_id, name, aa_seq) for name, aa_seq in input_proteins.items()]
        ))
        con.commit()

        # update job status so the workers will pick it up
        cur.execute((
            "UPDATE jobs SET status=?"
            " WHERE id=?"
        ), (0, job_id))
        con.commit()

    return job_id


@blueprint.route("/api/query/get_results_list")
def get_results_list():

    # check login
    if not check_logged_in():
        return ""

    type_req = request.args.get('type', type=str)
    job_id = request.args.get('jobid', type=int)
    query_protein_id = request.args.get('protid', type=int)

    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()
        cur.execute("ATTACH DATABASE ? AS job_db", (conf["query_db_path"],))

        num_query_proteins = cur.execute("select count(id) from job_db.query_proteins where jobid=?", (job_id,)).fetchall()[0][0]

        q_blast_hits = "".join(["(",
            "select blast_hits.target_cds_id, blast_hits.query_prot_id, blast_hits.target_genome_id,"
            " blast_hits.target_bgc_id, blast_hits.pct_identity",
            " from job_db.query_proteins, job_db.blast_hits where query_proteins.jobid=?",
            " and query_proteins.id=blast_hits.query_prot_id",
            (" and query_proteins.id = ?" if query_protein_id != 0 else " and ?"),
        ")"])


        if type_req == "genome":
            sql_query = {
                "q": "".join([
                    "select * from (",
                        "select count(distinct hits.query_prot_id) as num_hits_unique,",
                        " avg(hits.pct_identity) as avg_pct_id,",
                        " genomes.*, genomes_cached.*",
                        " from " + q_blast_hits + " as hits left join genomes on genomes.id=hits.target_genome_id",
                        " left join genomes_cached on genomes.id=genomes_cached.genome_id",
                        " group by genomes.id",
                    ")",
                    " where num_hits_unique=?"
                    " order by avg_pct_id desc"
                ]),
                "p": (
                    job_id,
                    query_protein_id if query_protein_id != 0 else "1",
                    1 if query_protein_id != 0 else num_query_proteins
                )
            }

            result = pd.read_sql_query((sql_query["q"]), con, params=sql_query["p"])
            result["grade"] = result.apply(get_assembly_grade, axis=1) if result.shape[0] > 0 else []
            result = {col: vals.tolist() for col, vals in result.iteritems()}

        elif type_req == "bgc":
            sql_query = {
                "q": "".join([
                    "select * from (",
                        "select count(distinct hits.query_prot_id) as num_hits_unique,",
                        " avg(hits.pct_identity) as avg_pct_id,",
                        " bgcs.*, bgcs_cached.*",
                        " from " + q_blast_hits + " as hits left join bgcs on hits.target_bgc_id=bgcs.id",
                        " left join bgcs_cached on bgcs.id=bgcs_cached.bgc_id",
                        " where hits.target_bgc_id > -1"
                        " group by bgc_id"
                    ")",
                    " where num_hits_unique=?"
                    " order by avg_pct_id desc"
                ]),
                "p": (
                    job_id,
                    query_protein_id if query_protein_id != 0 else "1",
                    1 if query_protein_id != 0 else num_query_proteins
                )
            }

            result = pd.read_sql_query((sql_query["q"]), con, params=sql_query["p"])
            result["knowncb_cutoff"] = conf["knowncb_cutoff"]
            result = {col: vals.tolist() for col, vals in result.iteritems()}
        else:
            result = ""


    return result


@blueprint.route("/query/download/<int:job_id>", methods=["GET"])
def page_download_result(job_id):

    # check login
    if not check_logged_in():
        return "not_authorized"

    # get job data
    job_data = pd.read_sql((
        "SELECT jobs.*, status_enum.name as status_desc"
        " FROM jobs, status_enum"
        " WHERE userid=? AND jobs.id=? and status_desc=? and jobs.status=status_enum.code"
    ), sqlite3.connect(conf["query_db_path"]), params=(session["userid"], job_id, "PROCESSED")).fillna("")

    if job_data.shape[0] != 1:
        return "wrong_request"
    else:
        job_data = job_data.iloc[0]

    # check request type
    action = request.args.get("action", type=str)
    if action not in ["check", "prepare", "download"]:
        return "wrong_request"

    # check if there is any pending download process
    for fp in glob.iglob(path.join(conf["temp_download_folder"], "blast-{}-*.pending".format(job_id))):
        return "pending_processing"
    for fp in glob.iglob(path.join(conf["temp_download_folder"], "blast-{}-*.pending.locked".format(job_id))):
        return "pending_processing"

    if action == "check":
        return "free"

    # build output filename
    file_type = request.args.get("filetype", type=str)    
    if file_type in ["fasta_proteins", "blast_table"]:
        query_prot_id = request.args.get("query_prot_id", type=str)
        if not query_prot_id:
            return "wrong_request"
        query_prot_ids = [int(query_prot_id)]
    elif file_type == "fasta_bgcs":
        query_prot_ids = request.args.get("query_prot_ids", type=str)
        if not query_prot_ids:
            return "wrong_request"
        query_prot_ids = [int(prot_id) for prot_id in query_prot_ids.split(",")]
    else:
        return "wrong_request"

    output_filepath = path.join(conf["temp_download_folder"], "blast-{}-{}-{}.zip".format(
        job_id,
        file_type,
        ",".join([str(prot_id) for prot_id in query_prot_ids])
    ))

    if action == "prepare":
        if path.exists(output_filepath):
            return "ready"
        else:
            # put on the pending file
            with open(output_filepath + ".pending", "w") as out:
                out.write("")
                return "processed"

    elif action == "download":
        
        # check if on cooldown
        if job_data["last_result_downloaded"] != "":
            sec_since_last_download = (
                datetime.now() - datetime.strptime(job_data["last_result_downloaded"], "%Y-%m-%d %H:%M:%S")
            ).total_seconds()
            if sec_since_last_download > -1 and sec_since_last_download < conf["consecutive_download_duration"]:
                flash("download on cooldown<br/>(please wait {:.0f}s)".format(
                    conf["consecutive_download_duration"] - sec_since_last_download
                ), "alert-danger")
                return redirect(url_for("query.page_job", job_id=job_id))

        # check if file exists
        if path.exists(output_filepath):
            with sqlite3.connect(conf["query_db_path"]) as con:
                con.cursor().execute((
                    "update jobs"
                    " set last_result_downloaded=?"
                    " where id=?"
                ), (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), job_id))
            return send_file(
                output_filepath, as_attachment=True, download_name=path.basename(output_filepath)
            )
        else:
            flash("can't find results file (please report this via the feedback form)", "alert-danger")
            return redirect(url_for("query.page_job", job_id=job_id))
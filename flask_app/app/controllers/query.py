#!/usr/bin/env python3

import sqlite3
from flask import render_template, request, session, redirect, url_for, flash
import pandas as pd
from datetime import datetime
import re

# import global config
from ..config import conf
from ..session import check_logged_in

#
from .genomes import get_assembly_grade

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('query', __name__)


@blueprint.route("/gdb/query/", methods=['POST', 'GET'])
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

@blueprint.route("/gdb/query/result/<int:job_id>")
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
        auto_refresh=(job_data["status"] < 2),
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

        if type_req == "genome":
            sql_query = {
                "q": "".join([
                    "select * from (",
                        "select count(distinct hits.query_prot_id) as num_hits_unique, genomes.*",
                        " from cds inner join (",
                            " select blast_hits.target_cds_id, blast_hits.query_prot_id",
                            " from job_db.query_proteins, job_db.blast_hits where query_proteins.jobid=? and query_proteins.id=blast_hits.query_prot_id",
                            " and query_proteins.id = ?" if query_protein_id != 0 else " and ?",
                        ") as hits on cds.id=hits.target_cds_id inner join (",
                            "select genomes.*, group_concat(bgcs.id) as bgcs, group_concat(bgcs.mibig_name, ';') as mibig_bgcs",
                            " from genomes left join (",
                            "    select bgcs.genome_id, bgcs.id, mibig.mibig_id, mibig.mibig_name",
                            "    from bgcs left join (",
                            "      select bgc_id, mibig_id, mibig.name_dereplicated as mibig_name",
                            "      from bgc_mibig_hit inner join mibig on mibig.id=bgc_mibig_hit.mibig_id",
                            "      where bgc_mibig_hit.hit_pct >= 40",
                            "    ) as mibig on mibig.bgc_id=bgcs.id",
                            " ) as bgcs on genomes.id=bgcs.genome_id",
                            " group by genomes.id"
                        ") as genomes on cds.genome_id=genomes.id",
                    " group by cds.genome_id)",
                    " where num_hits_unique=?"
                    " order by npdc_id asc"
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
            result = {
                "columns": [],
                "data": []
            }
        else:
            result = ""


    return result
#!/usr/bin/env python3

from flask import render_template, request, session, redirect, url_for, flash, send_file
import sqlite3
import pandas as pd
from os import path
from datetime import datetime

# import global config
from ..config import conf
from ..session import check_logged_in

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('genomes', __name__)


@blueprint.route("/genomes/")
def page_genomes():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # page title
    page_title = "Genomes"
    page_subtitle = (
        ""
    )

    # render view
    return render_template(
        "genomes/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )


@blueprint.route("/genomes/view/<int:genome_id>")
def page_genomes_view(genome_id):

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # grab genome's npdc id
    try:
        npdc_id = pd.read_sql_query((
            "select npdc_id from genomes"
            " where id=?"
        ), sqlite3.connect(conf["db_path"]), params=(genome_id, )).iloc[0, 0]
    except:        
        flash("can't find genome id", "alert-danger")
        return redirect(url_for("home.page_home"))

    return redirect(url_for("strains.page_strains_detail", npdc_id=npdc_id))


def get_assembly_grade(genome_row):

    if genome_row["genome_num_contigs"] <= 50:
        assembly_grade = "high"
    elif genome_row["genome_num_contigs"] <= 100:
        assembly_grade = "good"
    elif genome_row["genome_num_contigs"] <= 500:
        assembly_grade = "fair"
    else:
        assembly_grade = "fragmented"

    return assembly_grade


def get_sec_since_last_download(user_id, npdc_id):
    existing_log = pd.read_sql_query((
        "select * from user_downloads"
        " where user_id=? and npdc_id=?"
    ), sqlite3.connect(conf["user_db_path"]), params=(user_id, npdc_id))
    if existing_log.shape[0] > 0 and existing_log.iloc[0]["last_download_genome"] != None:
        sec_since_last_download = (
            datetime.now() - datetime.strptime(existing_log.iloc[0]["last_download_genome"], "%Y-%m-%d %H:%M:%S")
        ).total_seconds()
    else:
        sec_since_last_download = -1
    return sec_since_last_download


@blueprint.route("/genomes/download/<int:genome_id>", methods=["GET"])
def page_genomes_download(genome_id):

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # check if genomes exists
    try:
        genome_data = pd.read_sql_query((
            "select * from genomes"
            " where id=?"
        ), sqlite3.connect(conf["db_path"]), params=(genome_id, )).iloc[0].to_dict()
    except:
        flash("can't find genome id", "alert-danger")
        return redirect(url_for("home.page_home"))

    # check if have downloaded before
    sec_since_last_download = get_sec_since_last_download(session["userid"], int(genome_data["npdc_id"]))
    if sec_since_last_download > -1 and sec_since_last_download < conf["consecutive_download_duration"]:
        flash("can't download genome<br/>(downloaded before, please wait {:.0f}s)".format(
            conf["consecutive_download_duration"] - sec_since_last_download
        ), "alert-danger")
        return redirect(url_for("genomes.page_genomes_view", genome_id=genome_id))

    # check file type
    file_type = request.args.get("filetype", type=str)
    if file_type == "genbank":
        genome_file_path = path.join(conf["genome_folder_path"], "{}.gbk".format(genome_data["id"]))
        genome_file_delivery_name = "NPDC{:06d}.gbk".format(genome_data["npdc_id"])
    elif file_type == "fasta":
        genome_file_path = path.join(conf["genome_folder_path"], "{}.fna".format(genome_data["id"]))
        genome_file_delivery_name = "NPDC{:06d}.fna".format(genome_data["npdc_id"])
    else:
        flash("wrong request", "alert-danger")
        return redirect(url_for("home.page_home"))

    # check if genome file exists
    if not path.exists(genome_file_path):
        flash("can't find genome file<br/>(please report this via the feedback form)", "alert-danger")
        return redirect(url_for("genomes.page_genomes_view", genome_id=genome_id))

    # update downloads count
    existing_log = pd.read_sql_query((
        "select * from user_downloads"
        " where user_id=? and npdc_id=?"
    ), sqlite3.connect(conf["user_db_path"]), params=(session["userid"], int(genome_data["npdc_id"])))
    with sqlite3.connect(conf["user_db_path"]) as con:
        if existing_log.shape[0] > 0:
            con.cursor().execute((
                "update user_downloads"
                " set count_download_genome=?, last_download_genome=?"
                " where user_id=? and npdc_id=?"
            ), (
                int(existing_log.iloc[0]["count_download_genome"]) + 1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                session["userid"],
                int(genome_data["npdc_id"]
            )))
        else:
            con.cursor().execute((
                "insert into user_downloads"
                "(user_id, npdc_id, count_download_genome, last_download_genome)"
                " values(?, ?, ?, ?)"
            ), (
                session["userid"],
                int(genome_data["npdc_id"]),
                1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

    return send_file(genome_file_path, as_attachment=True, download_name=genome_file_delivery_name)


@blueprint.route("/api/genomes/get_overview", methods=["GET"])
def get_overview():
    """ for genomes overview tables """
    result = {}
    result["draw"] = request.args.get('draw', type=int)
    limit = request.args.get('length', type=int)
    offset = request.args.get('start', type=int)

    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()

        genome_filter = "1"
        genome_filter_params = []
        if request.args.get("mash_group", "") != "":
            genome_filter += " and genome_mash_species like ?"
            genome_filter_params.append(request.args.get("mash_group"))
        if request.args.get("exclude_id", "") != "":
            genome_filter += " and genomes.id<>?"
            genome_filter_params.append(request.args.get("exclude_id"))

        # fetch total records
        result["recordsTotal"] = cur.execute((
            "select count(id)"
            " from genomes"
            " where 1"
        )).fetchall()[0][0]

        # fetch total records (filtered)
        result["recordsFiltered"] = cur.execute("".join([
            "select count(id) from ("
                "select * from genomes left join genomes_cached on genomes.id=genomes_cached.genome_id",
                " where 1",
                (" and " + genome_filter) if genome_filter != "" else "",
                " group by genomes.id",
            ")"
        ]), tuple([*genome_filter_params])).fetchall()[0][0]

        result["data"] = []

        query_result = pd.read_sql_query("".join([
            "select * from genomes left join genomes_cached on genomes.id=genomes_cached.genome_id",
            " where 1",
            (" and " + genome_filter) if genome_filter != "" else "",
            " group by genomes.id",
            " limit ? offset ?"
        ]), con, params=tuple([*genome_filter_params, *[limit, offset]]))
        for idx, row in query_result.iterrows():

            result["data"].append([
                (row["id"], row["npdc_id"]),
                (row["genome_gtdb_species"] if row["genome_gtdb_species"] != ""
                    else row["genome_gtdb_genus"] + " spp."),
                row["genome_mash_species"],
                {
                    "grade": get_assembly_grade(row),
                    "cleaned": row["is_cleaned_up"],
                    "n50": row["genome_n50"],
                    "num_contigs": row["genome_num_contigs"],
                    "contamination": row["genome_qc_contamination"],
                    "completeness": row["genome_qc_completeness"],
                },
                row["genome_gc"],
                row["num_bgcs"],
                list(set(row["name_bgcs_mibig"].split("|"))) if row["name_bgcs_mibig"] else []
            ])

    return result
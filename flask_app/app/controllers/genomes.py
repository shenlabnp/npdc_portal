#!/usr/bin/env python3

from flask import render_template, request, session, redirect, url_for, flash, send_file, current_app
import sqlite3
import pandas as pd
from os import path
from datetime import datetime
import re
import json
from flask import jsonify

# import global config
from ..config import conf
from ..session import check_logged_in

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('genomes', __name__)

# import functions
from app.utils import construct_numeric_filter

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
        genome_file_path = path.join(conf["genome_folder_path"], str(genome_data["id"]), "{}.gbk".format(genome_data["id"]))
        genome_file_delivery_name = "NPDC{:06d}.gbk".format(genome_data["npdc_id"])
    elif file_type == "fasta":
        genome_file_path = path.join(conf["genome_folder_path"], str(genome_data["id"]), "{}.fna".format(genome_data["id"]))
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
    search_value = request.args.get('search[value]', default="", type=str)

    # Column name mapping
    column_mapping = {
        "NPDC No.": "npdc_id",
        "Taxonomy": "genome_name",
        "Mash cluster": "genome_mash_species",
        "Assembly quality": "genome_assembly_grade",
        "GC content": "genome_gc",
        "Num. of BGCs": "num_bgcs",
        "Known BGC hits": "genomes_known_bgcs"
    }

    default_numeric_columns = ["npdc_id", "genome_gc", "num_bgcs", "genomes_known_bgcs"]

    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()
        sql_filter = "1"
        sql_filter_params = []

        if request.args.get("mash_group", "") != "":
            sql_filter += " and genome_mash_species like ?"
            sql_filter_params.append(request.args.get("mash_group"))
        if request.args.get("exclude_id", "") != "":
            sql_filter += " and genomes.id<>?"
            sql_filter_params.append(request.args.get("exclude_id")) 

        if search_value:
            is_numeric_search = search_value.replace('.', '', 1).isdigit()
            parts = re.split(r'\s+and\s+', search_value, flags=re.IGNORECASE)            
            for part in parts:
                part_handled = False
                part = part.strip()
                if '[' in part and ']' in part:
                    term, user_column_with_bracket = part.split('[', 1)
                    user_column = user_column_with_bracket.rsplit(']', 1 )[0].strip()
                    term = term.strip()
                    db_column = column_mapping.get(user_column, None )
                    if db_column:                   
                        if db_column in default_numeric_columns:
                            numeric_filter, numeric_params = construct_numeric_filter(term, db_column)
                            sql_filter += numeric_filter
                            sql_filter_params.extend(numeric_params)                          
                            part_handled = True
                        else:
                            sql_filter += f" and {db_column} LIKE ?".format(db_column=db_column)
                            sql_filter_params.append(f"%{term}%")
                            part_handled = True
 
                if not part_handled:
                    generic_filter = " OR ".join([f"{col} LIKE ?" for col in column_mapping.values()])
                    sql_filter += f" and ({generic_filter})"
                    sql_filter_params.extend([f"%{part}%"] * len(column_mapping))

        # fetch total records
        result["recordsTotal"] = cur.execute((
            "select count(id)"
            " from genomes"
            " where 1"
        )).fetchall()[0][0]
   
        sql_query = ''.join([
            "select count(id) from (",
            "select * from genomes left join genomes_cached on genomes.id=genomes_cached.genome_id",
            " where 1",
            f" and {sql_filter}" if sql_filter != "" else "",            
            ")"
        ])

        current_app.logger.info(f"Final SQL Query: {sql_query}")
        current_app.logger.info(f"SQL Parameters: {sql_filter_params}")
 
        # fetch total records (filtered)
        result["recordsFiltered"] = cur.execute("".join([
            "select count(id) from ("
                "select * from genomes left join genomes_cached on genomes.id=genomes_cached.genome_id",
                " where 1",
                (" and " + sql_filter) if sql_filter != "" else "",
                " group by genomes.id",
            ")"
        ]), tuple([*sql_filter_params])).fetchall()[0][0]
        
        result["data"] = []

        query_result = pd.read_sql_query("".join([
            "select genomes.id, genomes.npdc_id, genomes.genome_num_contigs, genomes.genome_size_nt, ",
            "genomes.genome_n50, genomes.genome_gc, genomes.genome_gc_std, genomes.genome_qc_completeness, ",
            "genomes.genome_qc_contamination, genomes.genome_qc_heterogenity, genomes.genome_qc_taxon, ",
            "genomes.genome_gtdb_phylum, genomes.genome_gtdb_genus, genomes.genome_gtdb_species,  ",
            "genomes.genome_mash_species, genomes.is_cleaned_up, genomes.orig_identifier, genomes.genome_assembly_grade,  ",
            "genomes_cached.genome_id, genomes_cached.num_cds, genomes_cached.num_bgcs, genomes_cached.id_bgcs, genomes_cached.num_bgcs_mibig, ",
            "genomes_cached.name_bgcs_mibig, genomes_cached.id_bgcs_mibig, genomes_cached.genome_name, genomes_cached.genomes_known_bgcs ", 
            "FROM genomes ", 
            "LEFT JOIN genomes_cached on genomes.id=genomes_cached.genome_id ",
            "WHERE 1=1 ",
            (f" AND {sql_filter}" if sql_filter != "" else ""),
            " ORDER BY  genomes.id",
          " LIMIT ? OFFSET ?"
        ]), con, params=tuple([*sql_filter_params, *[limit, offset]])) 

        for idx, row in query_result.iterrows():
            result["data"].append([
                (row["id"], row["npdc_id"]),
                row["genome_name"],
                row["genome_mash_species"],
                {
                    "grade": row["genome_assembly_grade"],
                    "cleaned": row["is_cleaned_up"],
                    "n50": row["genome_n50"],
                    "num_contigs": row["genome_num_contigs"],
                    "contamination": row["genome_qc_contamination"],
                    "completeness": row["genome_qc_completeness"],
                },
                row["genome_gc"],
                row["num_bgcs"],
                row["genomes_known_bgcs"]
            ])

    return result

@blueprint.route("/api/genomes/get_cds_list", methods=["GET"])
def get_cds_list():
    """ for cds overview tables """
    result = {}
    result["draw"] = request.args.get('draw', type=int)
    limit = request.args.get('length', type=int)
    offset = request.args.get('start', type=int)

    bgc_id = request.args.get("bgc_id", "")
    genome_id = request.args.get("genome_id", "")

    if bgc_id == "" and genome_id == "":
        return "" # need to specify either genome_id or bgc_id

    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()
        query_filter = "1"
        query_filter_params = []
        if genome_id != "":
            query_filter += " and genome_id=?"
            query_filter_params.append(genome_id)
        if bgc_id != "":
            query_filter += " and bgc_id=?"
            query_filter_params.append(bgc_id)

        # fetch total records
        result["recordsTotal"] = cur.execute("".join([
            "select count(id) from (",
                "select cds.id from cds left join cds_bgc_map on cds.id=cds_bgc_map.cds_id",
                " where 1",
                (" and " + query_filter) if query_filter != "" else "",
            ")"
        ]), tuple([*query_filter_params])).fetchall()[0][0]

        # do other filters here
        #...

        # fetch total records (filtered)
        result["recordsFiltered"] = cur.execute("".join([
            "select count(id) from (",
                "select cds.id from cds left join cds_bgc_map on cds.id=cds_bgc_map.cds_id",
                " where 1",
                (" and " + query_filter) if query_filter != "" else "",
            ")"
        ]), tuple([*query_filter_params])).fetchall()[0][0]

        result["data"] = []

        query_result = pd.read_sql_query("".join([
            "select cds.nt_start, cds.nt_end, cds.locus_tag, cds.annotation, cds.aa_seq",
            " from cds left join cds_bgc_map on cds.id=cds_bgc_map.cds_id",
            " where 1",
            (" and " + query_filter) if query_filter != "" else "",
            " limit ? offset ?"
        ]), con, params=tuple([*query_filter_params, *[limit, offset]]))

        for idx, row in query_result.iterrows():
            result["data"].append([
                row["nt_start"],
                row["nt_end"],
                row["nt_end"] - row["nt_start"],
                row["locus_tag"],
                row["annotation"],
                row["aa_seq"]
            ])

    return result
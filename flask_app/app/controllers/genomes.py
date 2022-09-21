#!/usr/bin/env python3

from flask import render_template, request, session, redirect, url_for, flash
import sqlite3
import pandas as pd

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
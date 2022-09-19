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

        # fetch total records
        result["recordsTotal"] = cur.execute((
            "select count(id)"
            " from genomes"
            " where 1"
        )).fetchall()[0][0]

        # fetch total records (filtered)
        result["recordsFiltered"] = cur.execute((
            "select count(id)"
            " from genomes"
            " where 1"
        )).fetchall()[0][0]

        result["data"] = []

        query_result = pd.read_sql_query((
            "select genomes.*, group_concat(distinct bgcs.id) as bgcs, group_concat(bgcs.mibig_name, ';') as mibig_bgcs"
            " from genomes left join ("
            "    select bgcs.genome_id, bgcs.id, mibig.mibig_id, mibig.mibig_name"
            "    from bgcs left join ("
            "      select bgc_id, mibig_id, mibig.name_dereplicated as mibig_name"
            "      from bgc_mibig_hit inner join mibig on mibig.id=bgc_mibig_hit.mibig_id"
            "      where bgc_mibig_hit.hit_pct >= {}"
            "    ) as mibig on mibig.bgc_id=bgcs.id"
            " ) as bgcs on genomes.id=bgcs.genome_id"
            " where 1"
            " group by genomes.id"
            " limit {} offset {}"
        ).format(conf["knowncb_cutoff"], limit, offset), con)
        for idx, row in query_result.iterrows():

            assembly_grade = ""

            if row["genome_num_contigs"] <= 50:
                assembly_grade = "high"
            elif row["genome_num_contigs"] <= 100:
                assembly_grade = "good"
            elif row["genome_num_contigs"] <= 500:
                assembly_grade = "fair"
            else:
                assembly_grade = "fragmented"

            result["data"].append([
                (row["id"], row["npdc_id"]),
                (row["genome_gtdb_species"] if row["genome_gtdb_species"] != ""
                    else row["genome_gtdb_genus"] + " spp."),
                row["genome_mash_species"],
                {
                    "grade": assembly_grade,
                    "cleaned": row["is_cleaned_up"],
                    "n50": row["genome_n50"],
                    "num_contigs": row["genome_num_contigs"],
                    "contamination": row["genome_qc_contamination"],
                    "completeness": row["genome_qc_completeness"],
                },
                row["genome_gc"],
                len(row["bgcs"].split(",")),
                list(set(row["mibig_bgcs"].split(";"))) if row["mibig_bgcs"] else []
            ])

    return result
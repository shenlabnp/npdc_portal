#!/usr/bin/env python3

from flask import render_template, request, session, redirect, url_for, flash
import sqlite3
import pandas as pd

# import global config
from ..config import conf
from ..session import check_logged_in

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('bgcs', __name__)


@blueprint.route("/bgcs")
def page_bgcs():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # page title
    page_title = "Biosynthetic Gene Clusters"
    page_subtitle = (
        ""
    )

    # render view
    return render_template(
        "bgcs/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )


@blueprint.route("/api/bgcs/get_overview", methods=["GET"])
def get_overview():
    """ for bgcs overview tables """
    result = {}
    result["draw"] = request.args.get('draw', type=int)
    limit = request.args.get('length', type=int)
    offset = request.args.get('start', type=int)

    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()

        sql_filter = "1"
        sql_filter_params = []
        if request.args.get("genome_id", "") != "":
            sql_filter += " and genome_id=?"
            sql_filter_params.append(request.args.get("genome_id"))

        # fetch total records
        result["recordsTotal"] = cur.execute((
            "select seq"
            " from sqlite_sequence"
            " where name like 'bgcs'"
        )).fetchall()[0][0]

        # fetch total records (filtered)
        result["recordsFiltered"] = len(cur.execute("".join([
            "select bgcs.id from bgcs",
            " left join bgc_class_map on bgc_class_map.bgc_id=bgcs.id",
            " left join bgc_class on bgc_class_map.class_id=bgc_class.id",
            " left join genomes on genomes.id=bgcs.genome_id",
            " where 1",
            (" and " + sql_filter) if sql_filter != "" else "",
            " group by bgcs.id"
        ]), tuple([*sql_filter_params])).fetchall())

        result["data"] = []

        query_result = pd.read_sql_query("".join([
            "select bgcs.*, genomes.genome_mash_species, genomes.npdc_id",
            ", genomes.genome_gtdb_species, genomes.genome_gtdb_genus",
            ", group_concat(bgc_class.name, ';') as bgc_class from bgcs",
            " left join bgc_class_map on bgc_class_map.bgc_id=bgcs.id",
            " left join bgc_class on bgc_class_map.class_id=bgc_class.id",
            " left join genomes on genomes.id=bgcs.genome_id",
            " where 1",
            (" and " + sql_filter) if sql_filter != "" else "",
            " group by bgcs.id",
            " order by contig_num, nt_start asc"
            " limit ? offset ?"
        ]), con, params=tuple([*sql_filter_params, *[limit, offset]]))
        for idx, row in query_result.iterrows():
            result["data"].append([
                (row["genome_id"], row["npdc_id"]),
                row["genome_gtdb_genus"] + " spp." if row["genome_gtdb_species"] == "" else row["genome_gtdb_species"],
                row["genome_mash_species"],
                row["contig_num"],
                (row["id"], row["npdc_id"], row["contig_num"], row["orig_identifier"]),
                row["gcf"],
                row["fragmented"],
                list(set(row["bgc_class"].split(";"))),
                (row["nt_end"] - row["nt_start"]) / 1000,
                -1
            ])

    return result
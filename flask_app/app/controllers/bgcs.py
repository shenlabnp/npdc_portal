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

    flash("page not implemented yet", "alert-warning")
    return redirect(url_for("home.page_home"))


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
            "select count(id)"
            " from bgcs"
            " where 1"
        )).fetchall()[0][0]

        # fetch total records (filtered)
        result["recordsFiltered"] = cur.execute("".join([
            "select count(id) from (",
                "select bgcs.*, genomes.genome_mash_species, genomes.npdc_id",
                ", genomes.genome_gtdb_species, genomes.genome_gtdb_genus",
                ", count(cds_id) as num_cds",
                ", group_concat(bgc_class.name, ';') as bgc_class from bgcs",
                " inner join bgc_class_map on bgc_class_map.bgc_id=bgcs.id",
                " inner join bgc_class on bgc_class_map.class_id=bgc_class.id",
                " inner join genomes on genomes.id=bgcs.genome_id",
                " inner join cds_bgc_map on cds_bgc_map.bgc_id=bgcs.id",
                " where 1",
                (" and " + sql_filter) if sql_filter != "" else "",
                " group by bgcs.id",
            ")"
        ]), tuple([*sql_filter_params])).fetchall()[0][0]

        result["data"] = []

        query_result = pd.read_sql_query("".join([
            "select bgcs.*, genomes.genome_mash_species, genomes.npdc_id",
            ", genomes.genome_gtdb_species, genomes.genome_gtdb_genus",
            ", count(cds_id) as num_cds",
            ", group_concat(bgc_class.name, ';') as bgc_class from bgcs",
            " inner join bgc_class_map on bgc_class_map.bgc_id=bgcs.id",
            " inner join bgc_class on bgc_class_map.class_id=bgc_class.id",
            " inner join genomes on genomes.id=bgcs.genome_id",
            " inner join cds_bgc_map on cds_bgc_map.bgc_id=bgcs.id",
            " where 1",
            (" and " + sql_filter) if sql_filter != "" else "",
            " group by bgcs.id",
            " order by contig_num, nt_start asc"
            " limit ? offset ?"
        ]), con, params=tuple([*sql_filter_params, *[limit, offset]]))
        for idx, row in query_result.iterrows():
            result["data"].append([
                (row["genome_id"], row["npdc_id"]),
                row["genome_gtdb_genus"] + " spp." if row["genome_gtdb_species"] else row["genome_gtdb_species"],
                row["genome_mash_species"],
                row["contig_num"],
                (row["id"], row["npdc_id"], row["contig_num"], row["orig_identifier"]),
                row["gcf"],
                row["fragmented"],
                list(set(row["bgc_class"].split(";"))),
                (row["nt_end"] - row["nt_start"]) / 1000,
                row["num_cds"]
            ])

    return result
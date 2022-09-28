#!/usr/bin/env python3

from flask import render_template, request, session, redirect, url_for, flash
import sqlite3
import pandas as pd
from datetime import datetime
from os import path

# import global config
from ..config import conf
from ..session import check_logged_in

from .genomes import get_assembly_grade

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('strains', __name__)


@blueprint.route("/strains/view")
def page_strains():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # page title
    page_title = "Strain Collection"
    page_subtitle = (
        ""
    )

    # render view
    return render_template(
        "strains/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )


@blueprint.route("/order")
def page_strains_ordering():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # page title
    page_title = "Order a strain"
    page_subtitle = (
        ""
    )

    # render view
    return render_template(
        "strains/ordering.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )


def get_strain_name(data):

    result = "Unknown bacterium"
    if data["genome_gtdb_species"] != "":
        result = data["genome_gtdb_species"]
    elif data["genome_gtdb_genus"] != "":
        result = data["genome_gtdb_genus"] + " spp."
    elif data["empirical_genus"] != "":
        result = "Unknown " + data["empirical_genus"]
    elif data["empirical_category"] != "":
        result = "Unknown " + data["empirical_category"]

    return result


@blueprint.route("/strains/view/<int:npdc_id>")
def page_strains_detail(npdc_id):

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))

    with sqlite3.connect(conf["db_path"]) as con:
        strain_data = pd.read_sql_query((
            "select strains.*, genomes.*, genomes.id as genome_id,"
            " strains_cached.alt_ids, strains_cached.medias"
            " from strains left join genomes on strains.npdc_id=genomes.npdc_id"
            " left join strains_cached on strains.npdc_id=strains_cached.npdc_id"
            " where strains.npdc_id=?"
            " limit 1"
        ),  con, params=(npdc_id, )).fillna("")

        if strain_data.shape[0] < 1:
            flash("can't find strain id", "alert-danger")
            return redirect(url_for("home.page_home"))

        strain_data = strain_data.iloc[0]
        strain_data = strain_data.groupby(strain_data.index).first()

        if strain_data["genome_id"] != "":
            strain_data["complete_bgcs"] = pd.read_sql_query((
                "select count(id)"
                " from bgcs"
                " where genome_id=? and fragmented=0"
            ),  con, params=(int(strain_data["genome_id"]), )).iloc[0, 0]
            strain_data["fragmented_bgcs"] = pd.read_sql_query((
                "select count(id)"
                " from bgcs"
                " where genome_id=? and fragmented=1"
            ),  con, params=(int(strain_data["genome_id"]), )).iloc[0, 0]
            strain_data["mibig_hits"] = pd.read_sql_query((
                "select count(id)"
                " from bgcs inner join bgc_mibig_hit on bgcs.id=bgc_mibig_hit.bgc_id"
                " where bgcs.genome_id=? and bgc_mibig_hit.hit_pct >= ?"
            ),  con, params=(int(strain_data["genome_id"]), conf["knowncb_cutoff"])).iloc[0, 0]
            strain_data["genome_quality"] = get_assembly_grade(strain_data)
        else:
            strain_data["complete_bgcs"] = ""
            strain_data["fragmented_bgcs"] = ""
            strain_data["mibig_hits"] = ""
            strain_data["genome_quality"] = ""
    
        strain_data["name"] = get_strain_name(strain_data)

        if strain_data["collection_date"] != "":
            strain_data["collection_date"] = datetime.strftime(
                datetime.strptime(strain_data["collection_date"], "%Y-%m-%d"), "%B %-m, %Y"
            )

        strain_data["picture_available"] = path.exists(path.join(conf["strain_pictures_folder_path"], "{}.jpg".format(strain_data["npdc_id"])))

        strain_data = strain_data.replace("", "n/a").to_dict()

    # page title
    page_title = "NPDC{:06d}".format(strain_data["npdc_id"])

    # render view
    return render_template(
        "strains/detail.html.j2",
        strain_data=strain_data,
        page_title=page_title
    )


@blueprint.route("/api/strains/get_overview")
def get_overview():
    """ for strain overview tables """
    result = {}
    result["draw"] = request.args.get('draw', type=int)
    limit = request.args.get('length', type=int)
    offset = request.args.get('start', type=int)

    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()

        # fetch total records
        result["recordsTotal"] = cur.execute((
            "select count(npdc_id)"
            " from strains"
        )).fetchall()[0][0]

        # fetch total records (filtered)
        result["recordsFiltered"] = cur.execute((
            "select count(npdc_id)"
            " from strains"
        )).fetchall()[0][0]


        result["data"] = []

        query_result = pd.read_sql_query((
            "select strains.*, genomes.*, genomes.id as genome_id,"
            " strains_cached.alt_ids, strains_cached.medias"
            " from strains left join genomes on strains.npdc_id=genomes.npdc_id"
            " left join strains_cached on strains.npdc_id=strains_cached.npdc_id"
            " limit {} offset {}"
        ).format(limit, offset), con).fillna("")
        query_result = query_result.loc[:,~query_result.columns.duplicated()]

        for idx, row in query_result.iterrows():

            taxonomy = ""

            result["data"].append([
                row["npdc_id"],
                get_strain_name(row),
                row["genome_id"] != "",
                "n/a" if row["collection_date"] == "" else row["collection_date"],
                "n/a" if row["collection_country"] == "" else row["collection_country"],
                [media for media in row["medias"].split("|") if media != ""],
                [alt_id for alt_id in row["alt_ids"].split("|") if alt_id != ""],
                [comment for comment in row["comment"].split(";") if comment != ""],
            ])

    return result
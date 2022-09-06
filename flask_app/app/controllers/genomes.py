#!/usr/bin/env python3

from flask import render_template, request, session, redirect, url_for
import sqlite3
import pandas as pd

# import global config
from ..config import conf
from ..session import check_logged_in

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('genomes', __name__)


@blueprint.route("/gdb/genomes/")
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


@blueprint.route("/api/genomes/get_overview")
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
            "select *"
            " from genomes"
            " where 1"
            " limit {} offset {}"
        ).format(limit, offset), con)


        for idx, row in query_result.iterrows():
            result["data"].append([
                "NPDC{:06d}".format(row["npdc_id"]) if isinstance(row["npdc_id"], int) else row["npdc_id"],
            ])

    return result
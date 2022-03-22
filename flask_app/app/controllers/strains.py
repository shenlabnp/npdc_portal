#!/usr/bin/env python3

from flask import render_template, request
import sqlite3
import pandas as pd

# import global config
from ..config import conf

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('strains', __name__)


@blueprint.route("/strains")
def page_strains():

    # page title
    page_title = "Strains Collection"
    page_subtitle = (
        "metadata"
    )

    # render view
    return render_template(
        "strains/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )



@blueprint.route("/api/strains/get_years_data")
def get_years_data():
    """ for strain years pie chart """
    result = {}

    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()

        query_result = (pd.read_sql_query((
            "select collection_date"
            " from strains"
        ), con).iloc[:, 0])
        query_result = query_result.map(
            lambda x: (x[2] + "0s" if x[0] == "1" else "20" + x[2] + "0s") if x != "" else "Unknown"
        ).value_counts().sort_index()

        result["data"] = list(query_result)
        result["labels"] = list(query_result.index)

    return result



@blueprint.route("/api/strains/get_genus_data")
def get_genus_data():
    """ for strain genus pie chart """
    result = {}

    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()

        query_result = (pd.read_sql_query((
            "select empirical_genus"
            " from strains"
        ), con).iloc[:, 0])
        query_result = query_result.value_counts()
        query_result = pd.concat([
            query_result.iloc[:9],
            pd.Series([query_result.iloc[10:].sum()], index=["Others"])
        ])

        result["data"] = list(query_result)
        result["labels"] = list(query_result.index)

    return result


@blueprint.route("/api/strains/get_sequencing_data")
def get_sequencing_data():
    """ for strain sequencing pie chart """
    result = {}

    result["data"] = list([
        120000,
        7000,
        7600,
        750,
        350,
        1300,
    ])
    result["labels"] = list([
        "archive",
        "gDNA extracted",
        "sent for sequencing",
        "sequenced - on progress",
        "sequenced - failed QC",
        "sequenced - annotated",
    ])

    return result


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
            "select *"
            " from strains order by npdc_id"
            " limit {} offset {}"
        ).format(limit, offset), con)


        for idx, row in query_result.iterrows():
            result["data"].append([
                "NPDC{:06d}".format(row["npdc_id"]),
                "-",
                "-",
                "-",
                "-" if row["collection_date"] == "" else row["collection_date"],
                "Unknown" if row["collection_country"] == "" else row["collection_country"],
                row["source_library"],
                "-",
            ])

    return result
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


@blueprint.route("/bgcs/view/<int:bgc_id>")
def page_bgcs_detail(bgc_id):

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))

    with sqlite3.connect(conf["db_path"]) as con:
        bgc_data = pd.read_sql_query((
            "select * from bgcs left join bgcs_cached on bgcs.id=bgcs_cached.bgc_id"
            " where bgc_id=?"
        ), sqlite3.connect(conf["db_path"]), params=(bgc_id, ))

        if bgc_data.shape[0] < 1:
            flash("can't find bgc id", "alert-danger")
            return redirect(url_for("home.page_home"))

        bgc_data = bgc_data.iloc[0]
        bgc_data = bgc_data.to_dict()
        bgc_data["name"] = get_bgc_name(bgc_data)
        bgc_data["strain_name"] = get_strain_name(bgc_data)
        bgc_data["annotation_tool"] = "antiSMASH v5.1.1"
        bgc_data["knowncb_cutoff"] = conf["knowncb_cutoff"]
        bgc_data["num_related_bgcs"] = pd.read_sql_query((
            "select count(id) from bgcs"
            " where id<>? and gcf=?"
        ), sqlite3.connect(conf["db_path"]), params=(bgc_data["bgc_id"], bgc_data["gcf"])).iloc[0, 0]

    page_title = bgc_data["name"]

    # render view
    return render_template(
        "bgcs/detail.html.j2",
        bgc_data = bgc_data,
        page_title=page_title
    )


def get_strain_name(data):

    result = "Unknown bacterium"
    if data["species"] != "":
        result = data["species"]
    elif data["genus"] != "":
        result = data["genus"] + " spp."

    return result


def get_bgc_name(row):
    return "NPDC{:06d}.ctg-{:04d}.region{:03d}".format(
        row["npdc_id"],
        row["contig_num"],
        row["region_num"]
    )


def get_sec_since_last_download(user_id, npdc_id):
    existing_log = pd.read_sql_query((
        "select * from user_downloads"
        " where user_id=? and npdc_id=?"
    ), sqlite3.connect(conf["user_db_path"]), params=(user_id, npdc_id))
    if existing_log.shape[0] > 0 and existing_log.iloc[0]["last_download_bgc"] != None:
        sec_since_last_download = (
            datetime.now() - datetime.strptime(existing_log.iloc[0]["last_download_bgc"], "%Y-%m-%d %H:%M:%S")
        ).total_seconds()
    else:
        sec_since_last_download = -1
    return sec_since_last_download


@blueprint.route("/bgcs/download/<int:bgc_id>", methods=["GET"])
def page_bgcs_download(bgc_id):

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # check if bgc_id exists
    try:
        bgc_data = pd.read_sql_query((
            "select * from bgcs left join bgcs_cached on bgcs.id=bgcs_cached.bgc_id"
            " where bgc_id=?"
        ), sqlite3.connect(conf["db_path"]), params=(bgc_id, )).iloc[0].to_dict()
    except:
        flash("can't find bgc id", "alert-danger")
        return redirect(url_for("home.page_home"))

    # check if have downloaded before
    sec_since_last_download = get_sec_since_last_download(session["userid"], int(bgc_data["npdc_id"]))
    if sec_since_last_download > -1 and sec_since_last_download < conf["consecutive_download_duration"]:
        flash("can't download BGC<br/>(downloaded before, please wait {:.0f}s)".format(
            conf["consecutive_download_duration"] - sec_since_last_download
        ), "alert-danger")
        return redirect(url_for("bgcs.page_bgcs_detail", bgc_id=bgc_id))

    # check file type
    file_type = request.args.get("filetype", type=str)
    if file_type == "regiongbk":
        bgc_file_path = path.join(conf["bgc_folder_path"], str(bgc_data["genome_id"]), "{}.gbk".format(bgc_data["bgc_id"]))
        bgc_file_delivery_name = get_bgc_name(bgc_data) + ".gbk"
    else:
        flash("wrong request", "alert-danger")
        return redirect(url_for("home.page_home"))

    # check if bgc file exists
    if not path.exists(bgc_file_path):
        flash("can't find bgc file<br/>(please report this via the feedback form)", "alert-danger")
        return redirect(url_for("bgcs.page_bgcs_detail", bgc_id=bgc_id))

    # update downloads count
    existing_log = pd.read_sql_query((
        "select * from user_downloads"
        " where user_id=? and npdc_id=?"
    ), sqlite3.connect(conf["user_db_path"]), params=(session["userid"], int(bgc_data["npdc_id"])))
    with sqlite3.connect(conf["user_db_path"]) as con:
        if existing_log.shape[0] > 0:
            con.cursor().execute((
                "update user_downloads"
                " set count_download_bgc=?, last_download_bgc=?"
                " where user_id=? and npdc_id=?"
            ), (
                int(existing_log.iloc[0]["count_download_bgc"]) + 1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                session["userid"],
                int(bgc_data["npdc_id"]
            )))
        else:
            con.cursor().execute((
                "insert into user_downloads"
                "(user_id, npdc_id, count_download_bgc, last_download_bgc)"
                " values(?, ?, ?, ?)"
            ), (
                session["userid"],
                int(bgc_data["npdc_id"]),
                1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

    return send_file(bgc_file_path, as_attachment=True, download_name=bgc_file_delivery_name)


@blueprint.route("/api/bgc/get_arrower_objects")
def get_arrower_objects():
    """ for arrower js """
    result = {}
    bgc_ids = map(int, request.args.get('bgc_id', type=str).split(","))

    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()

        for bgc_id in bgc_ids:
            bgc_data = pd.read_sql((
                "select * from bgcs left join bgcs_cached on bgcs.id=bgcs_cached.bgc_id where bgc_id=?"
            ), con, params=(bgc_id,)).iloc[0]
            data = {
                "id": get_bgc_name(bgc_data),
                "start": int(bgc_data["nt_start"]),
                "end": int(bgc_data["nt_end"]),
            }
            # get cds
            data["orfs"] = []
            for idx, row in pd.read_sql((
                "select cds.nt_start, cds.nt_end, cds.strand, cds.locus_tag, cds.annotation"
                " from cds_bgc_map left join cds on cds.id=cds_bgc_map.cds_id"
                " where bgc_id=?"
            ), con, params=(bgc_id,)).iterrows():
                orf = {
                    "start": int(row["nt_start"]) - int(bgc_data["nt_start"]),
                    "end": int(row["nt_end"]) - int(bgc_data["nt_start"]),
                    "strand": int(row["strand"])
                }
                orf["id"] = row["locus_tag"] + " (" + row["annotation"] + ")"
                orf["domains"] = []
                data["orfs"].append(orf)
            # append
            result[bgc_id] = data

    return result


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
        if request.args.get("exclude_bgcs", "") != "":
            bgc_ids = [int(bgc_id) for bgc_id in request.args.get("exclude_bgcs").split(",")]
            sql_filter += " and bgc_id not in ({})".format(",".join(["?"]*len(bgc_ids)))
            sql_filter_params.extend(bgc_ids)
        if request.args.get("genome_id", "") != "":
            sql_filter += " and genome_id=?"
            sql_filter_params.append(request.args.get("genome_id"))
        if request.args.get("gcf", "") != "":
            sql_filter += " and gcf=?"
            sql_filter_params.append(request.args.get("gcf"))            

        # fetch total records
        result["recordsTotal"] = cur.execute((
            "select seq"
            " from sqlite_sequence"
            " where name like 'bgcs'"
        )).fetchall()[0][0]

        # fetch total records (filtered)
        result["recordsFiltered"] = len(cur.execute("".join([
            "select bgcs.*, bgcs_cached.*",
            " from bgcs left join bgcs_cached on bgcs.id=bgcs_cached.bgc_id"
            " where 1",
            (" and " + sql_filter) if sql_filter != "" else "",
        ]), tuple([*sql_filter_params])).fetchall())

        result["data"] = []

        query_result = pd.read_sql_query("".join([
            "select bgcs.*, bgcs_cached.*",
            " from bgcs left join bgcs_cached on bgcs.id=bgcs_cached.bgc_id"
            " where 1",
            (" and " + sql_filter) if sql_filter != "" else "",
            " order by contig_num, nt_start asc"
            " limit ? offset ?"
        ]), con, params=tuple([*sql_filter_params, *[limit, offset]]))
        for idx, row in query_result.iterrows():
            result["data"].append([
                (row["genome_id"], row["npdc_id"]),
                row["genus"] + " spp." if row["species"] == "" else row["species"],
                row["mash_species"],
                row["contig_num"],
                (row["id"], row["npdc_id"], row["contig_num"], row["orig_identifier"]),
                row["gcf"],
                row["fragmented"],
                list(set(row["name_class"].split("|"))),
                (row["nt_end"] - row["nt_start"]) / 1000,
                row["num_cds"],
                (row["mibig_hit_id"], row["mibig_hit_name"], row["mibig_hit_pct"], conf["knowncb_cutoff"])
            ])

    return result
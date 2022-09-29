#!/usr/bin/env python3

import sqlite3
from flask import render_template, request, session, redirect, url_for, current_app

# import global config
from ..config import conf
from ..session import check_logged_in
import sqlite3
import pandas as pd
from os import path
from datetime import datetime

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('dashboard', __name__)


@blueprint.route("/dashboard", methods=['POST', 'GET'])
def page_dashboard():

    if request.args.get("action", "") == "logout":
        session.pop("dashboard_accessible", None)
        return redirect(url_for("home.page_home"))

    if request.method == 'POST':
        if current_app.secret_key == request.form['key']:
            session["dashboard_accessible"] = True
        return redirect(url_for("dashboard.page_dashboard"))

    num_registered_user = pd.read_sql_query((
        "select count(id) from users"
    ),  sqlite3.connect(conf["user_db_path"])).iloc[0, 0]


    num_login_today = pd.read_sql_query((
        "select count(id) from users where last_login >= ?"
    ),  sqlite3.connect(conf["user_db_path"]), params=(datetime.now().strftime("%Y-%m-%d 00:00:00"),)).iloc[0, 0]

    users_countries = pd.read_sql_query((
        "select countries.name from users left join user_details on users.id=user_details.user_id"
        " left join countries on countries.code=user_details.country"
    ),  sqlite3.connect(conf["user_db_path"])).iloc[:, 0]
    users_countries = list(sorted(users_countries.value_counts().to_dict().items(), key=lambda x: x[1], reverse=True))

    users_jobs_academia = pd.read_sql_query((
        "select job_titles.name as name, count(users.id) as count_users,"
        " ifnull(sum(user_details.have_nih_funding), 0) as num_nih_funding,"
        " ifnull(sum(user_details.have_nsf_funding), 0) as num_nsf_funding,"
        " ifnull(sum(user_details.have_other_funding), 0) as num_other_funding"
        " from users left join user_details on users.id=user_details.user_id"
        " left join job_titles on job_titles.id=user_details.job_title"
        " where user_details.is_academics=1"
        " group by name"
    ),  sqlite3.connect(conf["user_db_path"])).values.tolist()

    users_jobs_nonacademia = pd.read_sql_query((
        "select 'n/a' as name, count(users.id) as count_users,"
        " ifnull(sum(user_details.have_nih_funding), 0) as num_nih_funding,"
        " ifnull(sum(user_details.have_nsf_funding), 0) as num_nsf_funding,"
        " ifnull(sum(user_details.have_other_funding), 0) as num_other_funding"
        " from users left join user_details on users.id=user_details.user_id"
        " where user_details.is_academics=0"
        " group by name"
    ),  sqlite3.connect(conf["user_db_path"])).values.tolist()

    blast_queries = pd.read_sql_query((
        "select status_enum.name, count(jobs.id) from jobs left join status_enum on jobs.status=status_enum.code"
        " group by status_enum.code"
    ),  sqlite3.connect(conf["query_db_path"])).values.tolist()

    user_downloads = pd.read_sql_query((
        "select npdc_id, sum(count_download_genome), sum(count_download_bgc) from user_downloads"
        " group by npdc_id"
    ),  sqlite3.connect(conf["user_db_path"])).values.tolist()

    # render view
    return render_template(
        "dashboard/main.html.j2",
        dashboard_accessible = session.get("dashboard_accessible", False),
        num_registered_user=num_registered_user,
        num_login_today=num_login_today,
        users_countries=users_countries,
        users_jobs_academia=users_jobs_academia,
        users_jobs_nonacademia=users_jobs_nonacademia,
        blast_queries=blast_queries,
        user_downloads=user_downloads
    )
#!/usr/bin/env python3

from flask import render_template, redirect
import sqlite3
from datetime import datetime

# import global config
from ..config import conf
from ..session import check_logged_in

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('home', __name__)


@blueprint.route("/home")
def page_home():

    # check login
    if not check_logged_in():
        pass # do nothing
        
    # page title
    page_title = "Welcome to the NPDC Portal!"
    page_subtitle = ""

    # fetch data
    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()

        strains_count, = cur.execute(
            "SELECT count(npdc_id) FROM strains"
        ).fetchall()[0]

        genomes_count, = cur.execute(
            "SELECT count(id) FROM genomes"
        ).fetchall()[0]


    # render view
    return render_template(
        "home/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle,
        strains_count=strains_count,
        genomes_count=genomes_count
    )


@blueprint.route("/countdown")
def page_launch_countdown():

    launch_datetime = datetime.strptime(conf["launch_datetime"], "%Y-%m-%d %H:%M:%S")
    seconds_to_launch = (launch_datetime - datetime.now()).total_seconds()

    if seconds_to_launch <= 0:
        return redirect(url_for("home.page_home"))

    return render_template(
        "home/countdown.html.j2",
        launch_datetime=launch_datetime.strftime("%Y-%m-%dT%H:%M:%S")
    )
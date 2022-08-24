#!/usr/bin/env python3

from flask import render_template
import sqlite3

# import global config
from ..config import conf

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('home', __name__)


@blueprint.route("/home")
def page_home():

    # page title
    page_title = "Natural Products Discovery Collection"
    page_subtitle = (
        "home of the largest sequenced bacterial strains collection to enable scientific discovery"
    )

    # fetch data (test)
    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()

        strains_count, = cur.execute(
            "SELECT count(npdc_id) FROM strains"
        ).fetchall()[0]



    # render view
    return render_template(
        "home/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle,
        strains_count="{:,}".format(strains_count)
    )

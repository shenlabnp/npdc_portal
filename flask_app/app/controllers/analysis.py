#!/usr/bin/env python3

from flask import render_template, session, redirect, url_for
import sqlite3

# import global config
from ..config import conf
from ..session import check_logged_in

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('analysis', __name__)


@blueprint.route("/analysis")
def page_analysis():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))

    # page title
    page_title = "Bioinformatics Analysis"
    page_subtitle = (
        "platform to explore the sequenced NPDC genomes"
    )

    # render view
    return render_template(
        "analysis/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )

#!/usr/bin/env python3

import sqlite3
from flask import render_template, request, session, redirect, url_for

# import global config
from ..config import conf
from ..session import check_logged_in

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('about', __name__)


@blueprint.route("/about")
def page_fabout():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # page title
    page_title = "About NPDC"
    page_subtitle = ("")

    # render view
    return render_template(
        "about/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )
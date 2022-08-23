#!/usr/bin/env python3

from flask import render_template, session, redirect, url_for
import sqlite3

# import global config
from ..config import conf

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('gdnas', __name__)


@blueprint.route("/gdnas")
def page_gdnas():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # page title
    page_title = "gDNAs"
    page_subtitle = (
        "isolated to date"
    )

    # render view
    return render_template(
        "gdnas/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )

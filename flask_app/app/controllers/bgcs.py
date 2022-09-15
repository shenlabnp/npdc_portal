#!/usr/bin/env python3

import sqlite3
from flask import render_template, request, session, redirect, url_for, flash

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

    flash("page not implemented yet", "alert-warning")
    return redirect(url_for("home.page_home"))
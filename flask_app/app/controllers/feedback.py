#!/usr/bin/env python3

import sqlite3
from flask import render_template, request, session, redirect, url_for, current_app

# import global config
from ..config import conf
from ..session import check_logged_in

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('feedback', __name__)


@blueprint.route("/feedback")
def page_feedback():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # page title
    page_title = "Help / Feedback"
    page_subtitle = ("")

    # render view
    return render_template(
        "feedback/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle,
        mailto_target=current_app.config["MAIL_SEND_ORDER_TO"]
    )
#!/usr/bin/env python3

from flask import render_template, session, redirect, url_for, session, request
import sqlite3

# import global config
from ..config import conf

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('login', __name__)


@blueprint.route("/login", methods=['GET', 'POST'])
def page_login():

    # if loggin in
    if request.method == 'POST':
        session["username"] = request.form['username']
        return redirect(url_for("home.page_home"))

    # page title
    page_title = "Login / Sign up"
    page_subtitle = (
        ""
    )

    # render view
    return render_template(
        "login/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )


@blueprint.route("/logout")
def page_logout():
    session.pop("username", None)
    return redirect(url_for("home.page_home"))
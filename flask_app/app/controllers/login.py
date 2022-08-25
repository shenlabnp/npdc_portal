#!/usr/bin/env python3

from flask import render_template, session, redirect, url_for, session, request, flash, current_app
from flask_mail import Mail, Message
import sqlite3
import pandas as pd
import string
import random
from datetime import datetime


def generate_token(size):
    chars = list(set(string.ascii_uppercase + string.digits).difference('LIO01'))
    return ''.join(random.choices(chars, k=size))

# import global config
from ..config import conf

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('login', __name__)


@blueprint.route("/login", methods=['POST', 'GET'])
def page_login():

    # if loggin in
    if request.method == 'POST':        
        with sqlite3.connect(conf["user_db_path"]) as con:
            cur_userdata =  pd.read_sql_query((
                "select * from users where username like ? and token like ?"
            ), con=con, params=(request.form['username'], request.form['token']))
            if cur_userdata.shape[0] == 1:
                session["userdata"] = cur_userdata.iloc[0].to_dict()
                session["userid"] = session["userdata"]["id"]
                flash("login success", "alert-success")
                return redirect(url_for("home.page_home"))
            else:
                flash("login failed", "alert-danger")
                return redirect(url_for("login.page_login"))

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


@blueprint.route("/register", methods=['POST'])
def page_register():

    with sqlite3.connect(conf["user_db_path"]) as con:

        existing_userdata = pd.read_sql_query((
            "select id from users where username like ? or email like ?"
        ), con=con, params=(request.form['username'], request.form['email']))
        if existing_userdata.shape[0] > 0:
            # user exists, registration failed
            flash("username / email exists!", "alert-danger")
            return redirect(url_for("login.page_login"))

        token = generate_token(6)
        userdata = pd.DataFrame([{
            "username": request.form["username"],
            "email": request.form["email"],
            "token": token,
            "num_login": 0,
            "last_login": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }])
        userdata.to_sql("users", con, index=False, if_exists="append")

        # success, send e-mail with token
        email_sender = Mail(current_app)
        msg = Message(
            "Your NPDC Database account",
            sender=current_app.config["MAIL_USERNAME"],
            recipients=[userdata.iloc[0]["email"]]
        )
        msg.html = (
            "Please save your token and username for login purpose:<br />"
            "<b>username:</b> {}<br />"
            "<b>token:</b> {}<br />"
        ).format(
            userdata.iloc[0]["username"],
            userdata.iloc[0]["token"]
        )
        email_sender.send(msg)

        # render view
        flash("registration success! please check your e-mail for login information", "alert-info")
        return redirect(url_for("home.page_home"))


@blueprint.route("/logout")
def page_logout():
    session.pop("userid", None)
    session.pop("userdata", None)
    flash("logged out", "alert-warning")
    return redirect(url_for("home.page_home"))
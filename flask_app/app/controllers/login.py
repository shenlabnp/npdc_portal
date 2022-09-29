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

    # if logging in
    if request.method == 'POST':        
        with sqlite3.connect(conf["user_db_path"]) as con:
            cur_userdata =  pd.read_sql_query((
                "select *"
                " from users where username like ? and token like ?"
            ), con=con, params=(request.form['username'], request.form['token']))
            if cur_userdata.shape[0] == 1:
                session["userdata"] = cur_userdata.iloc[0].to_dict()
                session["userid"] = session["userdata"]["id"]
                flash("login success", "alert-success")
                return redirect(url_for("home.page_home"))
            else:
                flash("login failed", "alert-danger")
                return redirect(url_for("login.page_login"))

    # fetch data for registration page
    with sqlite3.connect(conf["user_db_path"]) as con:
        job_titles = [(row["id"], row["name"]) for idx, row in pd.read_sql((
            "SELECT id, name FROM job_titles"
        ), con).iterrows()]
        countries = [(row["code"], row["name"]) for idx, row in pd.read_sql((
            "SELECT code, name FROM countries ORDER BY name ASC"
        ), con).iterrows()]

    # page title
    page_title = "Login / Sign up"
    page_subtitle = (
        ""
    )

    # render view
    return render_template(
        "login/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle,
        job_titles=job_titles,
        countries=countries
    )


@blueprint.route("/register", methods=['POST'])
def page_register():

    with sqlite3.connect(conf["user_db_path"]) as con:


        # validations
        validation_messages = []

        if pd.read_sql_query((
            "select id from users where username like ? or email like ?"
        ), con=con, params=(request.form['username'], request.form['email'])).shape[0] > 0:
            validation_messages.append("username / email exists!")

        if not request.form.get("username") or request.form.get("username") == "":
            validation_messages.append("'username' is empty")
        if not request.form.get("email") or request.form.get("email") == "":
            validation_messages.append("'email' is empty")
        if not request.form.get("firstname") or request.form.get("firstname") == "":
            validation_messages.append("'First Name' is empty")
        if not request.form.get("lastname") or request.form.get("lastname") == "":
            validation_messages.append("'Last Name' is empty")
        if not request.form.get("category"):
            validation_messages.append("Please select Academia/Non-Academia")
        if request.form.get("jobtitle") and pd.read_sql_query((
            "select count(id) from job_titles where id=?"
        ), con=con, params=(request.form.get("jobtitle"),)).iloc[0, 0] < 1:
            validation_messages.append("Please select the correct Job title")
        if not request.form.get("country") or pd.read_sql_query((
            "select count(code) from countries where code=?"
        ), con=con, params=(request.form.get("country"),)).iloc[0, 0] < 1:
            validation_messages.append("Please select the correct Country")

        if len(validation_messages) > 0:
            flash("Registration failed:<ul>{}</ul>".format("".join(["<li>" + msg + "</li>" for msg in validation_messages])), "alert-danger")
            return redirect(url_for("login.page_login"))

        # insert data

        token = generate_token(6)
        userdata = pd.DataFrame([{
            "username": request.form.get("username"),
            "email": request.form.get("email"),
            "token": token,
            "num_login": 0,
            "last_login": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }])
        userdata.to_sql("users", con, index=False, if_exists="append")

        userdata =  pd.read_sql_query((
            "select * from users where username like ? and token like ?"
        ), con=con, params=(userdata.iloc[0]['username'], userdata.iloc[0]['token'])).iloc[0]

        # details data
        pd.DataFrame([{
         "user_id": userdata["id"],
         "first_name": request.form.get("firstname"),
         "last_name": request.form.get("lastname"),
         "is_academics": request.form.get("category") == "academia",
         "job_title": request.form.get("jobtitle") if request.form.get("category") == "academia" else None,
         "country": request.form.get("country"),
         "have_nih_funding": 1 if request.form.get("funding_nih") else 0,
         "have_nsf_funding": 1 if request.form.get("funding_nsf") else 0,
         "have_other_funding": 1 if request.form.get("funding_others") else 0,
        }]).to_sql("user_details", con, index=False, if_exists="append")

        # success, send e-mail with token
        email_sender = Mail(current_app)
        msg = Message(
            "Your NPDC Database account",
            sender=current_app.config["MAIL_SEND_AS"],
            recipients=[userdata["email"]]
        )
        msg.html = (
            "Please save your token and username for login purpose:<br />"
            "<b>username:</b> {}<br />"
            "<b>token:</b> {}<br />"
        ).format(
            userdata["username"],
            userdata["token"]
        )
        try:
            email_sender.send(msg)
        except:
            con.cursor().execute("delete from user_details where user_id=?", (userdata["id"],));
            con.cursor().execute("delete from users where id=?", (userdata["id"],));
            flash("failed to send the e-mail token (have you checked if you entered a valid e-mail?)", "alert-danger")
            return redirect(url_for("login.page_register"))

        # render view
        flash("registration success! please check your e-mail for login information", "alert-success")
        return redirect(url_for("home.page_home"))


@blueprint.route("/logout")
def page_logout():
    session.pop("userid", None)
    session.pop("userdata", None)
    flash("logged out", "alert-warning")
    return redirect(url_for("home.page_home"))
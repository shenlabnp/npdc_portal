#!/usr/bin/env python3

from flask import Flask, redirect, url_for, session
from os import path
import sqlite3
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple
from sys import argv
import json
import datetime
import pandas as pd

# import global config
from app.config import conf

# import controllers
from app.controllers import root, login
from app.controllers import home, strains, genomes, bgcs
from app.controllers import feedback, about, query

def portal():

    # check and create account database if not exists
    if not path.exists(conf["user_db_path"]):
        with sqlite3.connect(conf["user_db_path"]) as con:
            cur = con.cursor()
            cur.executescript(open(path.join(path.dirname(path.dirname(path.realpath(__file__))), "sql_schemas", "sql_schema_accounts.txt")).read())
            con.commit()

            # insert countries data
            countries_ref = pd.read_csv(path.join(path.dirname(path.dirname(path.realpath(__file__))), "sql_schemas", "country-capitals.csv"), sep=",")
            pd.DataFrame({
                "code": countries_ref["CountryCode"],
                "name": countries_ref["CountryName"],
                "lat": countries_ref["CapitalLatitude"],
                "long": countries_ref["CapitalLongitude"],
                "continent": countries_ref["ContinentName"]
            }).to_sql("countries", con, index=False, if_exists="append")

    # initiate app
    app = Flask(
        __name__,
        template_folder=path.join(path.dirname(
            path.realpath(__file__)), "app", "views"),
        static_folder=path.join(path.dirname(
            path.realpath(__file__)), "app", "static")
    )

    # secret key for session
    app.secret_key = open(conf["session_key_path"], "r").read().rstrip("\n")

    # e-mail configuration
    for key, val in (json.load(open(conf["email_config_path"], "r"))).items():
        app.config[key] = val

    # register controllers
    app.register_blueprint(root.blueprint)
    app.register_blueprint(login.blueprint)
    app.register_blueprint(home.blueprint)
    app.register_blueprint(strains.blueprint)
    app.register_blueprint(genomes.blueprint)
    app.register_blueprint(bgcs.blueprint)
    app.register_blueprint(feedback.blueprint)
    app.register_blueprint(about.blueprint)
    app.register_blueprint(query.blueprint)

    # app-specific contexts #
    @app.context_processor
    def inject_global():
        gbal = {
            "cur_userdata": session.get("userdata", None)
        }

        # get last db update stats
        with sqlite3.connect(conf["db_path"]) as con:
            cur = con.cursor()
            last_db_updated, = cur.execute("select logs.time from logs where message like 'START' limit 1").fetchone()
            last_db_updated = datetime.datetime.strptime(last_db_updated, "%Y-%m-%d %H:%M:%S")
            now_date = datetime.datetime.now()
            last_db_updated_days = (now_date - last_db_updated).days

        if conf["is_in_beta"]:
            gbal["version"] = "beta"
        else:
            gbal["version"] = datetime.datetime.strftime(last_db_updated, "%Y.%m.%d")

        # get last query db update stats
        with sqlite3.connect(conf["query_db_path"]) as con:
            cur = con.cursor()
            num_jobs_pending = cur.execute("select count(id) from jobs where status in (0, 1)").fetchone()[0]
            num_jobs_processed = cur.execute("select count(id) from jobs where status in (2, 3)").fetchone()[0]

        # for navigations
        nav_items = []
        nav_items.append(("Home", url_for("home.page_home")))
        nav_items.append(("Strain Collection", url_for("strains.page_strains")))
        nav_items.append(("Genome database", url_for("genomes.page_genomes")))
        nav_items.append(("BGC database", url_for("bgcs.page_bgcs")))
        nav_items.append(("BLAST", url_for("query.page_main")))
        nav_items.append(("Purchase Strains", url_for("strains.page_strains_ordering")))
        nav_items.append(("Help", url_for("feedback.page_feedback")))
        nav_items.append(("About NPDC", url_for("about.page_about")))

        # for important alerts
        important_message = ""

        return dict(
            gbal=gbal,
            nav_items=nav_items,
            last_db_updated=last_db_updated.strftime("%x"),
            last_db_updated_days=last_db_updated_days,
            last_db_updated_days_wording="{} days ago".format(last_db_updated_days) if last_db_updated_days > 1 else (
                "yesterday" if last_db_updated_days == 1 else (
                    "today" if last_db_updated_days == 0 else "???"
                )
            ),
            num_jobs_pending=num_jobs_pending,
            num_jobs_processed=num_jobs_processed,
            important_message=important_message
        )

    return app


if __name__ == "__main__":

    if len(argv) > 1:
        port = int(argv[1])
    else:
        port = 5000

    if len(argv) > 2:
        def create_dummy_app(actual_subfolder):
            app = Flask(__name__)

            @ app.route("/")
            def dummy():
                return redirect("/" + actual_subfolder)
            return app

        app = DispatcherMiddleware(
            create_dummy_app(argv[2]), {
                "/" + argv[2]: portal()
            })
    else:
        app = portal()

    run_simple(
        hostname="0.0.0.0",
        port=port,
        application=app
    )

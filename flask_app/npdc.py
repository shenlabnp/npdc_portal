#!/usr/bin/env python3

from flask import Flask, redirect, url_for, session
from os import path
import sqlite3
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple
from sys import argv
import datetime

# import global config
from app.config import conf

# import controllers
from app.controllers import root, login
from app.controllers import home, strains, genomes, feedback, about

def portal():


    # initiate app
    app = Flask(
        __name__,
        template_folder=path.join(path.dirname(
            path.realpath(__file__)), "app", "views"),
        static_folder=path.join(path.dirname(
            path.realpath(__file__)), "app", "static")
    )

    app.secret_key = open(conf["session_key_path"], "r").read().rstrip("\n")


    # register controllers
    app.register_blueprint(root.blueprint)
    app.register_blueprint(login.blueprint)
    app.register_blueprint(home.blueprint)
    app.register_blueprint(strains.blueprint)
    app.register_blueprint(genomes.blueprint)
    app.register_blueprint(feedback.blueprint)
    app.register_blueprint(about.blueprint)

    # app-specific contexts #
    @app.context_processor
    def inject_global():
        gbal = {
            "version": "1.0.0",
            "cur_username": session.get("username", "")
        }

        # get last db update stats
        with sqlite3.connect(conf["db_path"]) as con:
            cur = con.cursor()
            last_updated, = cur.execute("select logs.time from logs where message like 'START' limit 1").fetchone()
            last_updated = datetime.datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
            now_date = datetime.datetime.now()
            last_updated_days = (now_date - last_updated).days

        # for navigations
        nav_items = []
        nav_items.append(("Main page", url_for("home.page_home")))
        nav_items.append(("Strains collection", [
            ("Browse strains", "/strains/view"),
            ("Ordering a strain", "/strains/order")
        ]))
        nav_items.append(("Genomes database", [
            ("Browse genomes", "/genomes/view"),
            ("Browse BGCs", "/dummy"),
            ("BLAST query", "/dummy")
        ]))
        nav_items.append(("Natural Products library", [
            ("Browse NPs", "/dummy"),
            ("Metabolomics database", "/dummy")
        ]))
        nav_items.append(("Help / Feedback", "/feedback"))
        nav_items.append(("About NPDC", "/about"))

        return dict(
            gbal=gbal,
            nav_items=nav_items,
            last_updated=last_updated.strftime("%x"),
            last_updated_days=last_updated_days,
            last_updated_days_wording="{} days ago".format(last_updated_days) if last_updated_days > 1 else (
                "yesterday" if last_updated_days == 1 else (
                    "today" if last_updated_days == 0 else "???"
                )
            )
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

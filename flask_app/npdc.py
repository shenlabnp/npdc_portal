#!/usr/bin/env python3

from flask import Flask, redirect, url_for
from os import path
import sqlite3
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple
from sys import argv
import datetime

# import global config
from app.config import conf

# import controllers
from app.controllers import root
from app.controllers import home, analysis, sequencing, gdnas, strains


def dashboard():


    # initiate app
    app = Flask(
        __name__,
        template_folder=path.join(path.dirname(
            path.realpath(__file__)), "app", "views"),
        static_folder=path.join(path.dirname(
            path.realpath(__file__)), "app", "static")
    )

    # register controllers
    app.register_blueprint(root.blueprint)
    app.register_blueprint(home.blueprint)
    app.register_blueprint(analysis.blueprint)
    app.register_blueprint(sequencing.blueprint)
    app.register_blueprint(gdnas.blueprint)
    app.register_blueprint(strains.blueprint)

    # app-specific contexts #
    @app.context_processor
    def inject_global():
        gbal = {
            "version": "1.0.0"
        }

        # get last db update stats
        last_updated = datetime.datetime(2022, 3, 1)
        now_date = datetime.datetime.now()
        last_updated_days = (now_date - last_updated).days

        # for navigations
        nav_items = []
        nav_items.append(("Summary", url_for("home.page_home")))
        nav_items.append(("Analysis", url_for("analysis.page_analysis")))
        nav_items.append(("Sequencing", url_for("sequencing.page_sequencing")))
        nav_items.append(("gDNAs", url_for("gdnas.page_gdnas")))
        nav_items.append(("Strains", url_for("strains.page_strains")))

        return dict(
            gbal=gbal,
            nav_items=nav_items,
            last_updated=last_updated.strftime("%x"),
            last_updated_days=last_updated_days
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
                "/" + argv[2]: dashboard()
            })
    else:
        app = dashboard()

    run_simple(
        hostname="0.0.0.0",
        port=port,
        application=app
    )

#!/usr/bin/env python3

from flask import Flask, redirect, url_for
from os import path
import sqlite3
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple
from sys import argv

# import global config
from app.config import conf

# import controllers
from app.controllers import root
from app.controllers import home


def npdc():


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

    # app-specific contexts #
    @app.context_processor
    def inject_global():
        g = {
            "version": "1.0.0"
        }

        # for navigations
        nav_items = []
        nav_items.append(("Home", url_for("home.page_home")))

        return dict(
            g=g,
            nav_items=nav_items
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
                "/" + argv[2]: npdc()
            })
    else:
        app = npdc()

    run_simple(
        hostname="0.0.0.0",
        port=port,
        application=app
    )

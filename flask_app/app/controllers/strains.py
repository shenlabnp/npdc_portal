#!/usr/bin/env python3

from flask import render_template
import sqlite3

# import global config
from ..config import conf

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('strains', __name__)


@blueprint.route("/strains")
def page_strains():

    # page title
    page_title = "Strains Collection"
    page_subtitle = (
        "metadata"
    )

    # render view
    return render_template(
        "strains/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )

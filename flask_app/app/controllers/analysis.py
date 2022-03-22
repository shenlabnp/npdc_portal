#!/usr/bin/env python3

from flask import render_template
import sqlite3

# import global config
from ..config import conf

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('analysis', __name__)


@blueprint.route("/analysis")
def page_analysis():

    # page title
    page_title = "Bioinformatics Analysis"
    page_subtitle = (
        "platform to explore the sequenced NPDC genomes"
    )

    # render view
    return render_template(
        "analysis/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )

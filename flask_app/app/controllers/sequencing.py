#!/usr/bin/env python3

from flask import render_template
import sqlite3

# import global config
from ..config import conf

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('sequencing', __name__)


@blueprint.route("/sequencing")
def page_sequencing():

    # page title
    page_title = "Genome Sequencing"
    page_subtitle = (
        "progress and summary"
    )

    # render view
    return render_template(
        "sequencing/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )

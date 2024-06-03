#!/usr/bin/env python3

from flask import render_template, request, session, redirect, url_for, flash, current_app
import sqlite3
import pandas as pd
from datetime import datetime
from os import path
import re
from datetime import datetime
from calendar import monthrange

# import global config
from ..config import conf
from ..session import check_logged_in

from .genomes import get_assembly_grade

# set blueprint object
from flask import Blueprint
blueprint = Blueprint('strains', __name__)

# import functions
from app.utils import construct_numeric_filter

@blueprint.route("/strains/view")
def page_strains():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # page title
    page_title = "Strain Collection"
    page_subtitle = (
        ""
    )

    # render view
    return render_template(
        "strains/main.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle
    )


@blueprint.route("/order")
def page_strains_ordering():

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))
        
    # page title
    page_title = "Request a strain"
    page_subtitle = (
        ""
    )

    # render view
    return render_template(
        "strains/ordering.html.j2",
        page_title=page_title,
        page_subtitle=page_subtitle,
        mailto_target=current_app.config["MAIL_SEND_ORDER_TO"]
    )


def get_strain_name(data):

    result = "Unknown bacterium"
    if data["genome_gtdb_species"] != "":
        result = data["genome_gtdb_species"]
    elif data["genome_gtdb_genus"] != "":
        result = data["genome_gtdb_genus"] + " spp."
    elif data["empirical_genus"] != "":
        result = "Unknown " + data["empirical_genus"]
    elif data["empirical_category"] != "":
        result = "Unknown " + data["empirical_category"]

    return result


@blueprint.route("/strains/view/<int:npdc_id>")
def page_strains_detail(npdc_id):

    # check login
    if not check_logged_in():
        return redirect(url_for("login.page_login"))

    with sqlite3.connect(conf["db_path"]) as con:
        strain_data = pd.read_sql_query((
            "select strains.*, genomes.*, genomes.id as genome_id,"
            " strains_cached.alt_ids, strains_cached.medias"
            " from strains left join genomes on strains.npdc_id=genomes.npdc_id"
            " left join strains_cached on strains.npdc_id=strains_cached.npdc_id"
            " where strains.npdc_id=?"
            " limit 1"
        ),  con, params=(npdc_id, )).fillna("")

        if strain_data.shape[0] < 1:
            flash("can't find strain id", "alert-danger")
            return redirect(url_for("home.page_home"))

        strain_data = strain_data.iloc[0]
        strain_data = strain_data.groupby(strain_data.index).first()

        if strain_data["genome_id"] != "":
            strain_data["complete_bgcs"] = pd.read_sql_query((
                "select count(id)"
                " from bgcs"
                " where genome_id=? and fragmented=0"
            ),  con, params=(int(strain_data["genome_id"]), )).iloc[0, 0]
            strain_data["fragmented_bgcs"] = pd.read_sql_query((
                "select count(id)"
                " from bgcs"
                " where genome_id=? and fragmented=1"
            ),  con, params=(int(strain_data["genome_id"]), )).iloc[0, 0]
            strain_data["mibig_hits"] = pd.read_sql_query((
                "select count(id)"
                " from bgcs inner join bgc_mibig_hit on bgcs.id=bgc_mibig_hit.bgc_id"
                " where bgcs.genome_id=? and bgc_mibig_hit.hit_pct >= ?"
            ),  con, params=(int(strain_data["genome_id"]), conf["knowncb_cutoff"])).iloc[0, 0]
            strain_data["genome_quality"] = get_assembly_grade(strain_data)
        else:
            strain_data["complete_bgcs"] = ""
            strain_data["fragmented_bgcs"] = ""
            strain_data["mibig_hits"] = ""
            strain_data["genome_quality"] = ""
    
        strain_data["name"] = get_strain_name(strain_data)

        if strain_data["collection_date"] != "":
            strain_data["collection_date"] = datetime.strftime(
                datetime.strptime(strain_data["collection_date"], "%Y-%m-%d"), "%B %-m, %Y"
            )
        
        try:
            strain_data["ecology"] = [comment.split("found in '")[1].rstrip("'") for comment in strain_data["comment"].split(";") if comment.lstrip().startswith("found in '")]
        except:
            strain_data["ecology"] = []
            
        strain_data["picture_available"] = path.exists(path.join(conf["strain_pictures_folder_path"], "{}.jpg".format(strain_data["npdc_id"])))

        strain_data = strain_data.replace("", "n/a").to_dict()

    # userdata
    with sqlite3.connect(conf["user_db_path"]) as con:
        user_data = pd.read_sql_query((
            "select users.*,user_details.*,countries.name as country_name, job_titles.name as job_name"
            " from users"
            " left join user_details on user_details.user_id=users.id"
            " left join countries on user_details.country=countries.code"
            " left join job_titles on user_details.job_title=job_titles.id"
            " where users.id like ?"
        ), con=con, params=(session['userid'],)).iloc[0].to_dict()

    # page title
    page_title = "NPDC{:06d}".format(strain_data["npdc_id"])

    # render view
    return render_template(
        "strains/detail.html.j2",
        strain_data=strain_data,
        page_title=page_title,
        mailto_target=current_app.config["MAIL_SEND_ORDER_TO"],
        user_fullname=user_data["first_name"] + " " + user_data["last_name"],
        user_country=user_data["country_name"]
    )

def parse_date_filter(date_filter):

    def parse_and_format(date_str):
        formats = ['%Y-%m-%d', '%Y-%m', '%Y']
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def validate_and_convert(parts):
        # Ensure parts can be converted to integers
        try:
            return [int(part) for part in parts if part.isdigit() and part != '']
        except ValueError:
            return []

    def process_date_parts(parts):
        try:
            if len(parts) == 1:
                # Only year is provided
                return datetime(parts[0], 1, 1), datetime(parts[0], 12, 31)
            elif len(parts) == 2:
                # Year and month provided
                start_date = datetime(parts[0], parts[1], 1)
                _, last_day = monthrange(parts[0], parts[1])
                end_date = datetime(parts[0], parts[1], last_day)
                return start_date, end_date
            else:
                # Full date provided
                date = parse_and_format('-'.join(map(str, parts)))
                return date, date
        except ValueError:
            return None, None

    # Split input by '|' to support range queries
    if '|' in date_filter:
        start_date_str, end_date_str = date_filter.split('|', 1)
    else:
        start_date_str = end_date_str = date_filter.strip()

    start_parts = validate_and_convert(start_date_str.split('-'))
    end_parts = validate_and_convert(end_date_str.split('-'))

    if not start_parts or not end_parts:
        # Invalid input or conversion failure, return None
        return None, None

    start_date, _ = process_date_parts(start_parts) if start_parts else (None, None)
    _, end_date = process_date_parts(end_parts) if end_parts else (None, None)

    if start_date and end_date and start_date <= end_date:
        return start_date, end_date
    else:
        return None, None

@blueprint.route("/api/strains/get_overview")
def get_overview():
    """ for strain overview tables """
    result = {}
    result["draw"] = request.args.get('draw', type=int)
    limit = request.args.get('length', type=int)
    offset = request.args.get('start', type=int)
    search_value = request.args.get('search[value]', default="", type=str)

    # Column mapping
    column_mapping = {
        "NPDC No.": "strains.npdc_id",
        "Taxonomy": "strain_name",        
        "Collection date": "collection_date",
        "Genome available": "strains.genome_available",
        "Collection place": "collection_country",
        "Growing Media": "medias"
    }

    default_numeric_columns = ['strains.npdc_id']

    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()
        sql_filter = "1"
        sql_filter_params = []
        if request.args.get("exclude_bgcs", "") != "":
            bgc_ids = [int(bgc_id) for bgc_id in request.args.get("exclude_bgcs").split(",")]
            sql_filter += " and bgc_id not in ({})".format(",".join(["?"]*len(bgc_ids)))
            sql_filter_params.extend(bgc_ids)
        if request.args.get("genome_id", "") != "":
            sql_filter += " and genome_id=?"
            sql_filter_params.append(request.args.get("genome_id"))
        if request.args.get("gcf", "") != "":
            sql_filter += " and gcf=?"
            sql_filter_params.append(request.args.get("gcf"))

        if search_value:
            is_numeric_search = search_value.replace('.', '', 1).isdigit()
            parts = re.split(r'\s+and\s+', search_value, flags=re.IGNORECASE)
            for part in parts:
                part_handled = False
                part = part.strip()
                if '[' in part and ']' in part:
                    term, user_column_with_bracket = part.split('[', 1)
                    user_column = user_column_with_bracket.rsplit(']', 1 )[0].strip()
                    term = term.strip()
                    db_column = column_mapping.get(user_column, None )
                    if db_column:
                        if db_column in default_numeric_columns:
                            numeric_filter, numeric_params = construct_numeric_filter(term, db_column)
                            sql_filter += numeric_filter
                            sql_filter_params.extend(numeric_params)
                            part_handled = True
                        elif db_column == "collection_date":
                            start_date, end_date = parse_date_filter(term)
                            if start_date and end_date:
                                start_date_str = start_date.strftime('%Y-%m-%d')
                                end_date_str = end_date.strftime('%Y-%m-%d')
                                sql_filter += " AND collection_date BETWEEN ? AND ?"
                                sql_filter_params.extend([start_date_str, end_date_str])
                                part_handled = True
                            else:
                               continue   
                        elif db_column == "strains.genome_available":
                            term_normalized = term.strip().capitalize()
                            if term_normalized in ["Yes", "No"]:
                                sql_filter += f" AND {db_column} = ?"
                                sql_filter_params.append(term_normalized)
                                part_handled = True
                        elif db_column == "medias":
                            search_terms = term.split("|")
                            for search_term in search_terms:
                                sql_filter += f" AND medias LIKE ?"
                                sql_filter_params.append(f"%{search_term}%")
                            part_handled = True
                        else:
                            sql_filter += f" and {db_column} LIKE ?".format(db_column=db_column)
                            sql_filter_params.append(f"%{term}%")
                            part_handled = True
                if not part_handled:
                    generic_filter = " OR ".join([f"{col} LIKE ?" for col in column_mapping.values()])
                    sql_filter += f" and ({generic_filter})"
                    sql_filter_params.extend([f"%{part}%"] * len(column_mapping))
  
        # fetch total records
        result["recordsTotal"] = cur.execute((
            "select count(npdc_id)"
            " from strains"
        )).fetchall()[0][0]

        # Construct SQL query for logging/debugging purposes
        sql_query = ''.join([
            "SELECT COUNT(DISTINCT strains.npdc_id) FROM strains ",
            "LEFT JOIN genomes ON strains.npdc_id = genomes.npdc_id ",
            "LEFT JOIN strains_cached ON strains.npdc_id = strains_cached.npdc_id ",
            "WHERE 1=1 ",
            (f"AND {sql_filter} " if sql_filter != "1" else ""),
        ])

        # Log the constructed query for debugging 
        current_app.logger.info(f"Final SQL Query: {sql_query}")
        current_app.logger.info(f"SQL Parameters: {sql_filter_params}")

        # fetch total records (filtered)
        result["recordsFiltered"] = cur.execute("".join([
            "SELECT COUNT(DISTINCT strains.npdc_id) FROM strains ",
            "LEFT JOIN genomes ON strains.npdc_id = genomes.npdc_id ",
            "LEFT JOIN strains_cached ON strains.npdc_id = strains_cached.npdc_id ",
            "WHERE 1=1 ",
            (f"AND {sql_filter} " if sql_filter != "1" else ""),
        ]), tuple([*sql_filter_params])).fetchall()[0][0]
 
        result["data"] = []
 
        query_result = pd.read_sql_query("".join([
            "select genomes.id AS genome_id, ", 
            "genomes.genome_gtdb_species, genomes.genome_gtdb_genus, ",
            "strains.npdc_id, strains.collection_date, strains.collection_country, ",
            "strains.collection_region, strains.empirical_category, strains.empirical_genus, ",
            "strains.empirical_species, strains.comment, strains.genome_available, ",
            "strains_cached.alt_ids, strains_cached.medias, ",
            "strains_cached.strain_name ",
            "FROM strains ",
            "LEFT JOIN genomes ON strains.npdc_id = genomes.npdc_id ",
            "LEFT JOIN strains_cached ON strains.npdc_id = strains_cached.npdc_id ",
            "WHERE 1=1 ",
            (f"AND {sql_filter} " if sql_filter != "1" else ""),
            "ORDER BY strains.npdc_id ",
            "LIMIT ? OFFSET ?",
        ]), con, params=tuple([*sql_filter_params, limit, offset])).fillna("")

        query_result = query_result.loc[:,~query_result.columns.duplicated()] 
        for idx, row in query_result.iterrows():
            taxonomy = ""
            result["data"].append([
                row["npdc_id"],
                row["strain_name"],
                row["genome_available"],
                "n/a" if row["collection_date"] == "" else row["collection_date"],
                "n/a" if row["collection_country"] == "" else row["collection_country"],
                [media for media in row["medias"].split("|") if media != ""],
                [alt_id for alt_id in row["alt_ids"].split("|") if alt_id != ""],
                [comment for comment in row["comment"].split(";") if comment != ""],
            ])

    return result
#!/usr/bin/env python3

from app.config import conf
from os import path
import sqlite3
from sys import argv
import json
import datetime
import pandas as pd


if __name__ == "__main__":

    # check and create account database if not exists
    if not path.exists(conf["user_db_path"]):
        print("creating accounts db ({})...".format(conf["query_db_path"]))
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

    # check and create jobs database if not exists
    if not path.exists(conf["query_db_path"]):
        print("creating jobs db ({})...".format(conf["query_db_path"]))
        with sqlite3.connect(conf["query_db_path"]) as con:
            cur = con.cursor()
            schema_sql = path.join(
                path.dirname(__file__),
                "..",
                "sql_schemas",
                "sql_schema_jobs.txt",
            )
            with open(schema_sql, "r") as sql_script:
                cur.executescript(sql_script.read())
                con.commit()

    # check and generate npdc_db cache tables
    with sqlite3.connect(conf["db_path_original"]) as con:
        cur = con.cursor()
        generate_new_cache = False
        logs_cache_generation = pd.read_sql_query((
            "select * from logs where message like 'generating db cache: %' order by time desc"
        ), con)
        if logs_cache_generation.shape[0] == 0:
            generate_new_cache = True
        else:
            params={
                x.split("=")[0]:x.split("=")[1] for x in logs_cache_generation.iloc[0]["message"].split("generating db cache: ")[-1].split(";")
            }
            if params.get("knowncb_cutoff", None) != str(conf["knowncb_cutoff"]):
                generate_new_cache = True
        if generate_new_cache:
            print("generating cache tables...")
            cur.executescript(
                open(
                    path.join(path.dirname(path.dirname(path.realpath(__file__))), "sql_schemas", "sql_schema_db_cache.txt")
                ).read().replace("--knowncb_cutoff--", str(conf["knowncb_cutoff"]))
            )
            con.commit()
            pd.DataFrame([{
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": "generating db cache: knowncb_cutoff={}".format(
                    conf["knowncb_cutoff"]
                ),
            }]).to_sql("logs", con, index=False, if_exists="append")
    print("done.")

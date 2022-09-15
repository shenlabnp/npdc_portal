#!/usr/bin/env python3

from os import path, listdir
from subprocess import run, DEVNULL
from shutil import copytree
from tempfile import TemporaryDirectory
from sys import exit, argv
from sqlite3 import connect
from time import sleep
from datetime import datetime
from multiprocessing import cpu_count
import pandas as pd
import numpy as np
import subprocess


def fetch_pending_jobs(jobs_db):
    with connect(jobs_db) as con:
        cur = con.cursor()
        return [row[0] for row in cur.execute((
            "select id"
            " from jobs"
            " where status=0"
            " order by submitted asc"
        )).fetchall()]


def deploy_jobs(pending, jobs_db, instance_folder, num_threads, ram_size_gb):
    for job_id in pending:
        print("PROCESSING: job#{}".format(job_id))
        # update status to "PROCESSING"
        with connect(jobs_db) as con:
            cur = con.cursor()
            cur.execute((
                "update jobs"
                " set status=?, started=?"
                " where id=?"
            ), (1, datetime.now(), job_id))
            con.commit()

        with TemporaryDirectory() as temp_dir:
            # create fasta input
            fasta_input_path = path.join(temp_dir, "input.fasta")
            with open(fasta_input_path, "w") as oo:
                for idx, row in pd.read_sql((
                    "select id,aa_seq from query_proteins"
                    " where jobid=?"
                    ),
                con=connect(jobs_db),
                params=(job_id,)
                ).iterrows():
                    oo.write(">{}\n{}\n".format(
                        row["id"],
                        row["aa_seq"]
                        ))

            # run DIAMOND BLASTP
            blast_columns = "qseqid sseqid qstart qend sstart send evalue bitscore pident"
            diamond_blast_db_path = path.join(
                path.dirname(__file__),
                "..",
                "instance",
                "db_data",
                "npdc_portal.dmnd"
            )
            blast_output_path = path.join(temp_dir, "output.txt")
            try:
                subprocess.check_output(
                    "diamond blastp -d {} -q {} -e 1e-10 -o {} -f 6 {} --ignore-warnings --query-cover 80 --id 40 -k 999999 -p {} -b{:.1f} -c4".format(
                        diamond_blast_db_path,
                        fasta_input_path,
                        blast_output_path,
                        blast_columns,
                        num_threads,
                        max(1, ram_size_gb / 7)
                    ), shell=True
                )
                status = 2
            except subprocess.CalledProcessError as e:
                status = -1

            # update status
            with connect(jobs_db) as con:
                cur = con.cursor()
                cur.execute((
                    "update jobs"
                    " set status=?, finished=?"
                    " where id=?"
                ), (status, datetime.now(), job_id))
                con.commit()

            print("COMPLETED: job#{}".format(job_id))

    return 0


def main():

    num_threads = int(argv[1])
    ram_size_gb = int(argv[2])

    instance_folder = path.join(
        path.dirname(__file__),
        "..",
        "instance"
    )
    jobs_db = path.join(instance_folder, "queries.db")

    if not path.exists(jobs_db):
        print("creating jobs db ({})...".format(jobs_db))
        with connect(jobs_db) as con:
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

    print("workers are running...")
    while(True):
        pending = fetch_pending_jobs(jobs_db)
        if len(pending) > 0:
            print("deploying {} jobs...".format(
                len(pending)
            ))
            deploy_jobs(pending, jobs_db, instance_folder, num_threads, ram_size_gb)

        sleep(5)

    return 0


if __name__ == '__main__':
    exit(main())
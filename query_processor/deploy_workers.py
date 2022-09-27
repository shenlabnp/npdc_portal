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


def deploy_jobs(pending, jobs_db, npdc_db, instance_folder, num_threads, ram_size_gb, use_srun):
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
            blast_columns = "qseqid sseqid qstart qend sstart send evalue bitscore pident slen qlen"
            diamond_blast_db_path = path.join(
                path.dirname(__file__),
                "..",
                "instance",
                "db_data",
                "npdc_portal.dmnd"
            )
            blast_output_path = path.join(temp_dir, "output.txt")
            try:
                cmd = 
                "{}diamond blastp -d {} -q {} -e 1e-10 -o {} -f 6 {} --ignore-warnings --query-cover 80 --id 40 -k 999999 -p {} -b{:.1f} -c1".format(
                    "srun -c {} -n 1 --mem={}G -t 1000 ".format(num_threads, ram_size_gb) if use_srun else "",
                    diamond_blast_db_path,
                    fasta_input_path,
                    blast_output_path,
                    blast_columns,
                    num_threads,
                    max(1, ram_size_gb / 7)
                )
                subprocess.check_output(
                    cmd, shell=True
                )
                status = 2
            except subprocess.CalledProcessError as e:
                status = -1

            if status == 2 and (path.getsize(blast_output_path) > 0): # else, no hit's produced
                # process BLAST result
                blast_result = pd.read_csv(
                    blast_output_path, sep="\t", header=None
                )
                blast_result.columns = blast_columns.split(" ")
                blast_result = blast_result.sort_values(by=["qseqid", "bitscore"], ascending=False)
                # fetch bgc_id and genome_id for the proteins
                all_target_cds_ids = [int(cds_id) for cds_id in blast_result["sseqid"].unique()]
                cds_to_genome_id = pd.read_sql((
                    "select id as cds_id, genome_id from cds where id in ({})"
                ).format(
                    ",".join(["?"]*len(all_target_cds_ids))
                ), connect(npdc_db), params=tuple([*all_target_cds_ids]))
                if cds_to_genome_id.shape[0] > 0:
                    cds_to_genome_id = cds_to_genome_id.groupby("cds_id").apply(lambda x: x.iloc[0])["genome_id"].to_dict()
                else:
                    cds_to_genome_id = {}
                cds_to_bgc_id = pd.read_sql((
                    "select cds_id, bgc_id from cds_bgc_map where cds_id in ({})"
                ).format(
                    ",".join(["?"]*len(all_target_cds_ids))
                ), connect(npdc_db), params=(tuple([*all_target_cds_ids])))
                if cds_to_bgc_id.shape[0] > 0:
                    cds_to_bgc_id = cds_to_bgc_id.groupby("cds_id").apply(lambda x: x.iloc[0])["bgc_id"].to_dict()
                else:
                    cds_to_bgc_id = {}
                # insert into db
                pd.DataFrame({
                    "query_prot_id": blast_result["qseqid"],
                    "target_cds_id": blast_result["sseqid"],
                    "target_bgc_id": blast_result["sseqid"].map(lambda x: cds_to_bgc_id.get(int(x), -1)),
                    "target_genome_id": blast_result["sseqid"].map(lambda x: cds_to_genome_id[int(x)]),
                    "query_start": blast_result["qstart"],
                    "query_end": blast_result["qend"],
                    "query_cov": abs(blast_result["qend"] - blast_result["qstart"]) / blast_result["qlen"] * 100,
                    "target_start": blast_result["sstart"],
                    "target_end": blast_result["send"],
                    "target_cov": abs(blast_result["send"] - blast_result["sstart"]) / blast_result["slen"] * 100,
                    "evalue": blast_result["evalue"],
                    "bitscore": blast_result["bitscore"],
                    "pct_identity": blast_result["pident"]
                }).to_sql("blast_hits", connect(jobs_db), index=False, if_exists="append")

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
    use_srun = False
    if len(argv) > 3:
        use_srun = int(argv[3]) == 1

    instance_folder = path.join(
        path.dirname(__file__),
        "..",
        "instance"
    )
    jobs_db = path.join(instance_folder, "queries.db")
    npdc_db = path.join(instance_folder, "db_data", "npdc_portal.db")

    if not path.exists(jobs_db):
        print("database is not up-to-date, please run init_db.py first!!")
        return(1)

    print("workers are running...")
    while(True):
        pending = fetch_pending_jobs(jobs_db)
        if len(pending) > 0:
            print("deploying {} jobs...".format(
                len(pending)
            ))
            deploy_jobs(pending, jobs_db, npdc_db, instance_folder, num_threads, ram_size_gb, use_srun)

        sleep(5)

    return 0


if __name__ == '__main__':
    exit(main())
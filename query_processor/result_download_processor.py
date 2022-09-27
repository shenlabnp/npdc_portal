import glob
from os import path, remove, getpid
from sqlite3 import connect
from sys import argv
import subprocess
from multiprocessing import Pool, cpu_count
from time import sleep
from zipfile import ZipFile
from tempfile import TemporaryDirectory
import pandas as pd


def main():

    instance_folder = path.join(
        path.dirname(__file__),
        "..",
        "instance"
    )
    tmp_download_folder = path.join(instance_folder, "tmp_download")
    npdc_db = path.join(instance_folder, "db_data", "npdc_portal.db")
    jobs_db = path.join(instance_folder, "queries.db")
    cds_fasta_path = path.join(instance_folder, "db_data", "npdc_portal.fasta")


    if argv[1].isnumeric(): # deployer mode
        num_threads = int(argv[1])
        pool = fetch_pool(num_threads)
        use_srun = False
        if len(argv) > 2:
            use_srun = int(argv[2]) == 1

        print("workers are running...")
        while(True):
            pending = sorted(glob.glob(path.join(tmp_download_folder, "blast-*.zip.pending")), key = path.getmtime)
            if len(pending) > 0:
                print("deploying {} jobs...".format(
                    len(pending)
                ))
                pool.map_async(fire_worker, [(use_srun, path.abspath(fp)) for fp in pending])

            sleep(1)


        return 0
    elif path.exists(argv[1]): # worker mode
        pending_file = path.abspath(argv[1])
        subprocess.run("mv {} {}".format(
            pending_file,
            pending_file + ".locked"
        ), shell=True)
        _, job_id, file_type, query_prot_ids = path.basename(pending_file).split(".zip")[0].split("-")
        job_id = int(job_id)
        query_prot_ids = [int(prot_id) for prot_id in query_prot_ids.split(",")]
        zip_output_file = pending_file.rsplit(".pending", 1)[0]
        zipped = ZipFile(zip_output_file, "w")
        error_ = False
        with TemporaryDirectory() as temp_dir:

            if file_type in ["fasta_bgcs", "fasta_proteins"]:

                # generate fasta file
                out_fasta = path.join(temp_dir, "cds.fasta")
                if file_type == "fasta_proteins":
                    query_cds = (
                        "SELECT DISTINCT target_cds_id as cds_id, target_bgc_id as bgc_id FROM blast_hits"
                        " WHERE query_prot_id=?"
                        " ORDER BY target_cds_id ASC"
                    )
                    params_ = query_prot_ids
                elif file_type == "fasta_bgcs":
                    query_cds = (
                        "SELECT DISTINCT cds_bgc_map.cds_id as cds_id, cds_bgc_map.bgc_id as bgc_id FROM ("
                            "SELECT bgc_id FROM ("
                                "SELECT target_bgc_id AS bgc_id, count(distinct query_prot_id) AS count_hits FROM blast_hits"
                                " WHERE query_prot_id IN ({}) AND target_bgc_id>-1"
                                " GROUP BY target_bgc_id"
                            ") AS bgc_hits WHERE bgc_hits.count_hits=?"
                        ") AS list_bgc LEFT JOIN npdc_db.cds_bgc_map ON cds_bgc_map.bgc_id=list_bgc.bgc_id"
                        " ORDER BY cds_bgc_map.cds_id ASC"
                    ).format(",".join(["?"]*len(query_prot_ids)))
                    params_ = list(
                        [*query_prot_ids, *[len(query_prot_ids)]]
                    )
                with connect(jobs_db) as con:
                    cur = con.cursor()
                    cur.execute("ATTACH DATABASE ? AS npdc_db", (npdc_db,))
                    df_ = pd.read_sql("".join([
                        "SELECT *",
                        " FROM (" + query_cds + ") AS cds_to_pull",
                        " LEFT JOIN cds ON cds_to_pull.cds_id=cds.id"
                        " LEFT JOIN genomes ON cds.genome_id=genomes.id"
                        " LEFT JOIN bgcs ON cds_to_pull.bgc_id=bgcs.id"
                        " ORDER BY cds_id ASC"
                    ]), con, params=tuple([*params_]))
                cds_to_pull = [int(x) for x in df_["cds_id"]]
                if len(cds_to_pull) > 0:
                    with open(out_fasta, "w") as output_fasta:
                        with open(cds_fasta_path, "r") as input_fasta:
                            i = 0
                            to_pull = cds_to_pull.pop(0)
                            for line in input_fasta:
                                if (i % 2) == 1: # AA section
                                    cur_id = (i // 2) + 1
                                    if cur_id > to_pull:
                                        # something is wrong
                                        error_ = True
                                        break
                                    elif cur_id == to_pull:
                                        # write down fasta
                                        output_fasta.write(">{}\n{}\n".format(
                                            cur_id,
                                            line.rstrip("\n")
                                        ))
                                        if len(cds_to_pull) > 0:
                                            # pop a new cds id
                                            to_pull = cds_to_pull.pop(0)
                                        else:
                                            break
                                i += 1
                    if not error_:
                        zipped.write(out_fasta, "cds.fasta")
                else:
                    error_ = True

                # generate cytoscape annotation file
                if not error_:
                    out_cyto = path.join(temp_dir, "metadata.tsv")
                    df_.to_csv(out_cyto, sep="\t", index=False)
                    zipped.write(out_cyto, "metadata.tsv")

            elif file_type == "blast_table":
                # generate blast results
                with connect(jobs_db) as con:
                    cur = con.cursor()
                    cur.execute("ATTACH DATABASE ? AS npdc_db", (npdc_db,))
                    out_blast = path.join(temp_dir, "blast_tabular_result.txt")
                    with open(out_blast, "w") as fp:
                        fp.write("")
                    for prot_id in query_prot_ids:
                        df_ = pd.read_sql("".join([
                            "SELECT {}".format(", ".join([
                                "blast_hits.query_prot_id",
                                "blast_hits.target_cds_id",
                                "blast_hits.pct_identity",
                                "blast_hits.evalue",
                                "blast_hits.bitscore",
                                "blast_hits.query_start",
                                "blast_hits.query_end",
                                "blast_hits.target_start",
                                "blast_hits.target_end"
                            ])),
                            " FROM blast_hits",
                            " WHERE query_prot_id=?",
                            " ORDER BY bitscore DESC"
                        ]), con, params=tuple([*[prot_id]]))
                        with open(out_blast, "a") as fp:
                            fp.write("".join([
                                "# DIAMOND-blastp (npdc.rc.ufl.edu)\n",
                                "# Query: {}\n".format(prot_id),
                                "# Database: npdc\n",
                                "# Fields: {}\n".format(
                                    ", ".join([
                                        "query acc.ver",
                                        "subject acc.ver",
                                        "%% identity",
                                        "evalue",
                                        "bit score",
                                        "q. start",
                                        "q. end",
                                        "s. start",
                                        "s. end"
                                    ])
                                ),
                                "# {} hits found".format(df_.shape[0])
                            ]))
                        df_.to_csv(out_blast, mode="a", index=False, header=False, sep="\t")
                        with open(out_blast, "a") as fp:
                            fp.write("\n")
                zipped.write(out_blast, "blast_tabular_result.txt")

        if error_:
            print("ERROR processing " + zip_output_file)
            remove(zip_output_file)
            remove(pending_file + ".locked")
            return 1
        else:
            remove(pending_file + ".locked")
            return 0

    else:
        return 1


def fire_worker(tup):
    use_srun, fp = tup
    print("processing " + fp)
    try:
        subprocess.check_output("{}python {} {}".format(
            "srun -c 1 -n 1 --mem=8G -t 25 " if use_srun else "",
            path.abspath(__file__),
            fp
        ), shell=True)
    except subprocess.CalledProcessError as e:
        print(e.output)


def fetch_pool(num_threads: int):
    pool = Pool(processes=num_threads)

    try:
        # set cores for the multiprocessing pools
        all_cpu_ids = set()
        for i, p in enumerate(pool._pool):
            cpu_id = str(cpu_count() - (i % cpu_count()) - 1)
            subprocess.run(["taskset",
                            "-p", "-c",
                            cpu_id,
                            str(p.pid)], check=True)
            all_cpu_ids.add(cpu_id)

        # set core for the main python script
        subprocess.run(["taskset",
                        "-p", "-c",
                        ",".join(all_cpu_ids),
                        str(getpid())], check=True)

    except FileNotFoundError:
        pass  # running in OSX?

    return pool


if __name__ == '__main__':
    exit(main())
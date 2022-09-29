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
                    params_ = [query_prot_ids[0]]
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
                        "SELECT {}".format(", ".join([
                            "cds_to_pull.cds_id as cds_id",
                            "genomes.genome_gtdb_genus as genus",
                            "genomes.genome_gtdb_species as species",
                            "genomes.genome_mash_species as mash_cluster",
                            "genomes.npdc_id as npdc_id",
                            "cds.contig_num as contig",
                            "cds.nt_start as loc_start",
                            "cds.nt_end as loc_end",
                            "cds.strand as strand",
                            "bgcs.region_num as bgc",
                            "bgcs.gcf as gcf",
                            "bgcs_cached.name_class as bgc_class",
                            "bgcs.fragmented as bgc_fragmented"
                        ])),
                        " FROM (" + query_cds + ") AS cds_to_pull",
                        " LEFT JOIN cds ON cds.id=cds_to_pull.cds_id",
                        " LEFT JOIN genomes ON genomes.id=cds.genome_id",
                        " LEFT JOIN genomes_cached ON genomes_cached.genome_id=cds.genome_id",
                        " LEFT JOIN bgcs ON bgcs.id=cds_to_pull.bgc_id",
                        " LEFT JOIN bgcs_cached ON bgcs_cached.bgc_id=cds_to_pull.bgc_id"
                    ]), con, params=tuple([*params_]))
                cds_to_pull = sorted([int(x) for x in df_["cds_id"]])
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
                    df_["bgc"] = df_.apply(lambda row: "NPDC-{}:r{}c{}".format(
                        row["npdc_id"],
                        row["contig"],
                        row["bgc"]
                    ), axis=1)
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
                        prot_name = pd.read_sql(
                            "SELECT name FROM query_proteins WHERE id=?",
                            con,
                            params=(prot_id,)
                        ).iloc[0, 0]
                        df_ = pd.read_sql("".join([
                            "SELECT hits.*, {}".format(", ".join([
                                "cds.id as cds_id",
                                "genomes.genome_gtdb_genus as genus",
                                "genomes.genome_gtdb_species as species",
                                "genomes.genome_mash_species as mash_cluster",
                                "genomes.npdc_id as npdc_id",
                                "cds.contig_num as contig",
                                "cds.nt_start as loc_start",
                                "cds.nt_end as loc_end",
                                "cds.strand as strand",
                                "bgcs.region_num as bgc",
                                "bgcs.gcf as gcf",
                                "bgcs_cached.name_class as bgc_class",
                                "bgcs.fragmented as bgc_fragmented"
                            ])),
                            " FROM (SELECT {}".format(", ".join([
                                    "blast_hits.query_prot_id as bls_query",
                                    "blast_hits.target_cds_id as bls_subject",
                                    "blast_hits.pct_identity as bls_pident",
                                    "blast_hits.evalue as bls_evalue",
                                    "blast_hits.bitscore as bls_bitscore",
                                    "blast_hits.query_start as bls_qstart",
                                    "blast_hits.query_end as bls_qend",
                                    "blast_hits.target_start as bls_sstart",
                                    "blast_hits.target_end as bls_send",
                                    "blast_hits.target_bgc_id as bgc_id",
                                    "blast_hits.target_genome_id as genome_id"
                                ])),
                                " FROM blast_hits",
                                " WHERE query_prot_id=?",
                                " ORDER BY bitscore DESC",
                                ") as hits",
                            " LEFT JOIN cds ON cds.id=hits.bls_subject",
                            " LEFT JOIN genomes ON genomes.id=hits.genome_id",
                            " LEFT JOIN genomes_cached ON genomes_cached.genome_id=hits.genome_id",
                            " LEFT JOIN bgcs ON bgcs.id=hits.bgc_id",
                            " LEFT JOIN bgcs_cached ON bgcs_cached.bgc_id=hits.bgc_id",
                        ]), con, params=tuple([*[prot_id]])).fillna("")
                        df_["bls_query"] = prot_name
                        df_["bgc"] = df_.apply(lambda row: "NPDC-{}:r{}c{}".format(
                            row["npdc_id"],
                            row["contig"],
                            row["bgc"]
                        ), axis=1)
                        with open(out_blast, "a") as fp:
                            fp.write("".join([
                                "# DIAMOND-blastp (npdc.rc.ufl.edu)\n",
                                "# Query: {}\n".format(prot_name),
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
                        df_.loc[
                            :,
                            df_.columns[df_.columns.str.startswith("bls_")]
                        ].to_csv(
                            out_blast, mode="a", index=False, header=False, sep="\t"
                        )
                        with open(out_blast, "a") as fp:
                            fp.write("\n")

                        out_blast_metadata = path.join(temp_dir, "metadata_{}.txt".format(prot_name))
                        df_.loc[
                            :,
                            df_.columns[~df_.columns.str.startswith("bls_")]
                        ].to_csv(
                            out_blast_metadata, index=False, header=True, sep="\t"
                        )
                        zipped.write(out_blast_metadata, "metadata_{}.tsv".format(prot_name))
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
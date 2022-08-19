#!/usr/bin/env python

import sqlite3
import pandas as pd
from sys import argv
from os import path
from multiprocessing import Pool, cpu_count
import glob
from tqdm import tqdm
import subprocess
import datetime


def main():
    input_tables_folder = argv[1]
    genome_sequencing_folder = argv[2]
    output_database_path = argv[3]
    pool = fetch_pool(int(argv[4]))

    return generate_sql_database(input_tables_folder, genome_sequencing_folder, output_database_path, pool)


def parse_sequencing_row(tup):
    genome_sequencing_folder, dataset, name = tup
    data = {
        "dataset": dataset,
        "name": name
    }

    # parse reads --> todo: parse R2!!!
    read_file_path = path.abspath(path.join(
        genome_sequencing_folder, "filtered_reads", dataset, name, name + ".R1.fastq.gz"
    ))
    if path.exists(read_file_path):
        data["read_file_folder"] = path.dirname(read_file_path)
        fp = read_file_path

        # check assembly-stats
        stats_file = path.join(data["read_file_folder"], data["name"] + ".stats.txt")
        if not path.exists(stats_file):
            print("WARNING: {} missing stats.txt (skipped)".format(data["read_file_folder"]), flush=True)
            return data
        with open(stats_file, "r") as ii:
            lines = ii.readlines()
            if lines[0].startswith("running srun via a wrapper script"):
                lines = lines[1:]
            try:
                data["reads_gc"] = float(lines[1].split("\t")[7]) * 100
                data["reads_gc_stdev"] = float(lines[1].split("\t")[8]) * 100
                data["reads_count"] = int(lines[3].split("\t")[1])
                data["reads_size"] = int(float(lines[5].split("\t")[1].split(" ")[0]) * 1000000)
            except:
                print("WARNING: {} file is corrupted!".format(stats_file), flush=True)
        if path.exists(fp + ".failed"):
            data["failed_assembly"] = True
        else:
            data["failed_assembly"] = None


    # parse genome
    genome_file_path = path.abspath(path.join(
        genome_sequencing_folder, "genomes", "per_batches", dataset, "all_genomes", name, name + ".fna"
    ))
    if path.exists(genome_file_path):
        data["genome_folder"] = path.dirname(genome_file_path)
        fp = genome_file_path

        # check QC status
        if path.exists(fp.replace("/all_genomes/", "/passed_qc/")):
            data["finished_qc"] = True
            data["passed_qc"] = True
        elif path.exists(fp.replace("/all_genomes/", "/failed_qc/")):
            data["finished_qc"] = True
            data["passed_qc"] = False
        else:
            data["finished_qc"] = False
            data["passed_qc"] = None

        # assembly data
        assembly_stats_path = path.join(data["genome_folder"], "qc", "assembly_stats.txt")
        if path.exists(assembly_stats_path):
            try:
                with open(assembly_stats_path, "r") as oo:
                    for line in oo:
                        if line.startswith("sum ="):
                            data["genome_size"] = int(line.split(",")[0].split(" = ")[1])
                            data["num_contigs"] = int(line.split(",")[1].split(" = ")[1])
                        elif line.startswith("N50 ="):
                            data["n50"] = int(line.split(",")[0].split(" = ")[1])
            except:
                print("WARNING: failed to parse {} (corrupted?)".format(assembly_stats_path), flush=True)
        elif data["finished_qc"]:
            print("WARNING: {} marked as 'finished QC' but lack assembly-stats files, please re-run QC!".format(fp), flush=True)
            data["passed_qc"] = None

        # checkm
        checkm_path = path.join(path.dirname(fp), "qc", "checkm", "checkm_result.txt")
        if path.exists(checkm_path):
            try:
                with open(checkm_path, "r") as oo:
                    lines = oo.readlines()
                    data["taxon_checkm"] = lines[1].split("\t")[1]
                    data["completeness"] = float(lines[1].split("\t")[11])
                    data["contamination"] = float(lines[1].split("\t")[12])
                    data["heterogenity"] = float(lines[1].split("\t")[13].rstrip("\n"))
            except:
                print("WARNING: failed to parse {} (corrupted?)".format(checkm_path), flush=True)
        elif data["finished_qc"]:
            if path.exists(path.join(path.dirname(checkm_path), "checkm.log")):
                data["passed_qc"] = False
            elif data["passed_qc"] != False:
                print("WARNING: {} marked as 'finished QC' but lack checkM files, please re-run QC!".format(fp), flush=True)
                data["passed_qc"] = None

        # checkm_blast
        checkm_blast_path = path.join(path.dirname(fp), "qc", "checkm", "blast", "blast_result.filtered.txt")
        if path.exists(checkm_blast_path):
            try:
                df_ = pd.read_csv(checkm_blast_path, sep="\t").fillna("n/a")
                data["taxa_blast_hits"] = ",".join([
                    "{}({})".format(taxa, count) for taxa, count in df_.groupby(
                        "sphylums"
                    )["marker"].count().sort_index().iteritems()
                ])
                data["taxa_blast_markers"] = ",".join([
                    "{}({})".format(taxa, count) for taxa, count in df_.groupby(
                        "marker"
                    )["sphylums"].unique().map(lambda x: "/".join(sorted(x))).value_counts().sort_index().iteritems()
                ])
                data["taxa_blast_contigs"] = ",".join([
                    "{}({})".format(taxa, count) for taxa, count in df_.groupby(
                        "contig"
                    )["sphylums"].unique().map(lambda x: "/".join(sorted(x))).value_counts().sort_index().iteritems()
                ])
                data["taxa_blast_strains"] = ",".join([
                    "{}({})".format(taxa, count) for taxa, count in df_.groupby(
                        "sphylums"
                    )["taxa"].nunique().sort_index().iteritems()
                ])
            except:
                print("WARNING: failed to parse {} (corrupted?)".format(checkm_blast_path), flush=True)                
                
        # annotations
        gtdb_path = path.join(path.dirname(fp), data["name"] + ".taxa.txt")
        antismash_path = path.join(path.dirname(fp), "annotations", "antismash", "regions.js")
        if path.exists(gtdb_path):
            try:
                with open(gtdb_path, "r") as oo:
                    lines = oo.readlines()
                    data["phylum_gtdb"] = lines[1].split("\t")[1].split(";")[1].rstrip("\n")
                    data["genus_gtdb"] = lines[1].split("\t")[1].split(";")[5].rstrip("\n")
                    data["species_gtdb"] = lines[1].split("\t")[1].split(";")[6].rstrip("\n")
                    data["fastANI_gtdb"] = lines[5].split("\t")[1].rstrip("\n")
                    data["fastANI_gtdb"] = float(data["fastANI_gtdb"]) if not data["fastANI_gtdb"] == "N/A" else None
                    data["related_species"] = {x.split(",")[1].lstrip().rstrip(): float(x.split(",")[3].lstrip().rstrip()) for x in lines[15].split("\t")[1].split(";") if len(x.split(",")) == 5}
                    if len(data["related_species"]) > 0:
                        data["closest_species"] = max(data["related_species"], key=data["related_species"].get)
                        data["closest_species_ani"] = max(data["related_species"].values())
            except:
                print("WARNING: failed to parse {} (corrupted?)".format(gtdb_path), flush=True)

            if path.exists(antismash_path):
                data["annotated"] = True
            else:
                data["annotated"] = False
        else:
            data["annotated"] = False

        data["failed_assembly"] = False

    return data


"""
Load all related tsv files in "input_tables_folder", parse, then
output the SQLite database file to "output_database_path"
"""
def generate_sql_database(input_tables_folder, genome_sequencing_folder, output_database_path, pool):

    # initiate logs recording
    logs = []
    def write_log(text, print_msg=True):
        logs.append({
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": text
        })
        if print_msg:
            print(text, flush=True)
        
    write_log("START", False)

    # check if file exists

    if path.exists(output_database_path):
        write_log("SQL database exists! {}".format(output_database_path))
        return 1

    # first, initiate the sqlite database schema

    write_log("initiating database..")
    with sqlite3.connect(output_database_path) as con:
        cur = con.cursor()
        with open(path.join(path.dirname(__file__), "sql_schema.txt")) as fp:
            con.executescript(fp.read())
            
    # parse strains data

    def parse_strains_data():
        write_log("parsing strains data..")
        strains_data_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-strains-*.tsv"))
        )

        write_log("found {} files".format(len(strains_data_files)))
        all_strains_data = pd.concat([
            pd.read_csv(filepath, sep="\t", dtype=str).fillna("") for filepath in strains_data_files
        ])

        write_log("inserting {} rows".format(all_strains_data.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            all_strains_data.to_sql("strains", con, if_exists='append', index=False)

    parse_strains_data()

    # parse strains location data

    def parse_locations_data():

        write_log("parsing strains location data..")
        strains_archive_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-stocks-*.tsv"))
        )

        write_log("found {} files".format(len(strains_archive_files)))
        all_strains_archives = pd.concat([
            pd.read_csv(filepath, sep="\t", dtype=str).fillna("") for filepath in strains_archive_files
        ])

        write_log("inserting {} rows".format(all_strains_archives.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            all_strains_archives.to_sql("stocks", con, if_exists='append', index=False)

    parse_locations_data()
    
    # parse growth data

    def parse_growth_data():

        write_log("parsing growth data..")
        growth_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-growth-*.tsv"))
        )

        write_log("found {} files".format(len(growth_files)))
        all_growths = pd.concat([
            pd.read_csv(filepath, sep="\t", dtype=str).fillna("") for filepath in growth_files
        ])

        write_log("inserting {} rows".format(all_growths.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            all_growths.to_sql("growth", con, if_exists='append', index=False)

    parse_growth_data()
    
    # parse extracts data

    def parse_extracts_data():

        write_log("parsing extracts data..")
        extract_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-extracts-*.tsv"))
        )

        write_log("found {} files".format(len(extract_files)))
        all_extracts = pd.concat([
            pd.read_csv(filepath, sep="\t", dtype=str).fillna("") for filepath in extract_files
        ])

        write_log("inserting {} rows".format(all_extracts.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            all_extracts.to_sql("extracts", con, if_exists='append', index=False)

    parse_extracts_data()

    # parse gdna data

    def parse_gdna_data():

        write_log("parsing gdna data..")
        gdna_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-gdnas-*.tsv"))
        )

        write_log("found {} files".format(len(gdna_files)))
        all_gdnas = pd.concat([
            pd.read_csv(filepath, sep="\t", dtype=str).fillna("") for filepath in gdna_files
        ])

        write_log("inserting {} rows".format(all_gdnas.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            all_gdnas.to_sql("gdnas", con, if_exists='append', index=False)

    parse_gdna_data()

    # parse projects data

    def parse_projects_data():

        write_log("parsing projects data..")
        projects_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-projects-*.tsv"))
        )

        write_log("found {} files".format(len(projects_files)))
        projects_data = pd.concat([
            pd.read_csv(filepath, sep="\t", dtype=str).fillna("") for filepath in projects_files
        ])

        write_log("inserting {} rows".format(projects_data.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            projects_data.to_sql("sequencing_projects", con, if_exists='append', index=False)

    parse_projects_data()

    # parse batches data

    def parse_batches_data():

        write_log("parsing sequencing batches data..")
        batches_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-batches-*.tsv"))
        )

        write_log("found {} files".format(len(batches_files)))
        batches_data = pd.concat([
            pd.read_csv(filepath, sep="\t", dtype=str).fillna("") for filepath in batches_files
        ])

        write_log("inserting {} rows".format(batches_data.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            batches_data.to_sql("sequencing_batches", con, if_exists='append', index=False)

    parse_batches_data()

    # parse samples data

    def parse_samples_data():

        write_log("parsing sequencing samples data..")
        samples_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-samples-*.tsv"))
        )

        write_log("found {} files".format(len(samples_files)))
        samples_data = pd.concat([
            pd.read_csv(filepath, sep="\t", dtype=str).fillna("") for filepath in samples_files
        ])

        write_log("inserting {} rows".format(samples_data.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            samples_data.to_sql("sequencing_samples", con, if_exists='append', index=False)

    parse_samples_data()
    
    def scan_sequencing_folder():

        write_log("scanning raw reads...")
        read_indices = set([(genome_sequencing_folder, x.split("/")[-3], x.split("/")[-2]) for x in glob.iglob(path.join(
            genome_sequencing_folder, "filtered_reads", "*", "*", "*.R1.fastq.gz"
        )) if x.split("/")[-2] == x.split("/")[-1].split(".R1.fastq.gz")[0]])

        write_log("scanning assembled genomes...")
        genome_indices = set([(genome_sequencing_folder, x.split("/")[-4], x.split("/")[-2]) for x in glob.iglob(path.join(
            genome_sequencing_folder, "genomes", "per_batches", "*", "all_genomes", "*", "*.fna"
        )) if x.split("/")[-2] == x.split("/")[-1].split(".fna")[0]])

        merged_indices = sorted(read_indices.union(genome_indices))

        write_log("found {:,} total sequences, parsing...".format(len(merged_indices)))

        result = tqdm(pool.imap(parse_sequencing_row, merged_indices), total=len(merged_indices))
        result = pd.DataFrame(result)
        
        result.index = result["dataset"] + "/" + result["name"]
        return result

    df_sequencing = scan_sequencing_folder()
    
    def insert_sequencing_data():
                
        write_log("scanning link files...")

        links_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-links-*.tsv"))
        )

        write_log("found {} files".format(len(links_files)))
        links_data = pd.concat([
            pd.read_csv(filepath, index_col="sequencing_id", sep="\t", dtype=str).fillna("") for filepath in links_files
        ]).apply(lambda row: row["dataset"] + "/" + row["name"], axis=1)
        
        df_sequencing_linked = links_data.map(
            lambda x: list(
                df_sequencing[df_sequencing.index.str.rsplit("-cleaned", 1).str[0].str.startswith(x[:-1])].index
            ) if x.endswith("*") else list(df_sequencing[df_sequencing.index.str.rsplit("-cleaned", 1).str[0] == x].index)
        ).explode()
        df_sequencing_linked = df_sequencing_linked[~df_sequencing_linked.isna()]

        write_log("linking {} sequences".format(df_sequencing_linked.shape[0]))
        
        # print warnings for unlinked sequences
        for idx, row in df_sequencing[~df_sequencing.index.isin(df_sequencing_linked)].iterrows():
            write_log("WARNING: found no linkage info for {} (skipping)".format(idx))
        
        # print warnings (and stop as it will fail integrity checking) for double-assigned sequences
        multi_samples_links = df_sequencing_linked[df_sequencing_linked.duplicated(False)]
        if multi_samples_links.shape[0] > 0:
            for idx, count in multi_samples_links.value_counts().iteritems():
                write_log("WARNING: genome {} is assigned to {} samples ({})".format(
                    idx,
                    count,
                    ",".join(multi_samples_links[multi_samples_links == idx].index)
                ))
            write_log("failing genome sequences insertion due to integrity issues")
            return
        
        # insert the rest
        write_log("inserting {} rows".format(df_sequencing_linked.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            temp_sequencing_id = df_sequencing_linked.index
            df_sequencing_linked = df_sequencing.reindex(df_sequencing_linked.values)
            df_sequencing_linked["linked_sequencing_id"] = temp_sequencing_id
            df_sequencing_linked = pd.DataFrame({
                "orig_identifier": df_sequencing_linked.index,
                "sequencing_id": df_sequencing_linked["linked_sequencing_id"],
                "assembly_status": df_sequencing_linked["failed_assembly"].map(lambda x: 0 if x == True else (1 if x == False else -1)),
                "qc_status": df_sequencing_linked.apply(lambda row: -1 if row["finished_qc"] != True else (1 if row["passed_qc"] == True else 0), axis=1),
                "annotation_status": df_sequencing_linked.apply(
                    lambda row: (1 if row["annotated"] == True else -1) if row["passed_qc"] == True else 0, axis=1
                ),
                "reads_folder": df_sequencing_linked["read_file_folder"],
                "reads_count": df_sequencing_linked["reads_count"].astype(int, errors="ignore"),
                "reads_size_nt": df_sequencing_linked["reads_size"].astype(int, errors="ignore"),
                "reads_gc": df_sequencing_linked["reads_count"],
                "reads_gc_std": df_sequencing_linked["reads_gc_stdev"],
                "genome_folder": df_sequencing_linked["genome_folder"],
                "genome_num_contigs": df_sequencing_linked["num_contigs"].astype(int, errors="ignore"),
                "genome_size_nt": df_sequencing_linked["genome_size"].astype(int, errors="ignore"),
                "genome_n50": df_sequencing_linked["n50"].fillna(-1),
                "genome_qc_completeness": df_sequencing_linked["completeness"],
                "genome_qc_contamination": df_sequencing_linked["contamination"],
                "genome_qc_heterogenity": df_sequencing_linked["heterogenity"],
                "genome_qc_taxon": df_sequencing_linked["taxon_checkm"],
                "genome_taxablast_hits": df_sequencing_linked["taxa_blast_hits"],
                "genome_taxablast_markers": df_sequencing_linked["taxa_blast_markers"],
                "genome_taxablast_contigs": df_sequencing_linked["taxa_blast_contigs"],
                "genome_taxablast_strains": df_sequencing_linked["taxa_blast_strains"],
                "genome_taxa_phylum": df_sequencing_linked["phylum_gtdb"],
                "genome_taxa_genus": df_sequencing_linked["genus_gtdb"],
                "genome_taxa_species": df_sequencing_linked["species_gtdb"],
                "genome_taxa_ref_fastani": df_sequencing_linked["fastANI_gtdb"],
            })
            df_sequencing_linked.to_sql("sequences", con, if_exists='append', index=False)
        
        return
    
    insert_sequencing_data()
    
    ### pause and perform foreign keys checking
    write_log("checking the integrity of tables linkage...")
    with sqlite3.connect(output_database_path) as con:
        failed_foreign_keys = pd.read_sql_query("PRAGMA foreign_key_check", con)
        for idx, val in (
            failed_foreign_keys["table"] + "->" + failed_foreign_keys["parent"]
        ).value_counts().iteritems():
            write_log("WARNING: missing foreign keys for {} rows in '{}'".format(val, idx))
            
    print("completed.")
    write_log("FINISH", False)
    
    with sqlite3.connect(output_database_path) as con:
        pd.DataFrame(logs).to_sql("logs", con, if_exists='append', index=False)


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

    except:
        pass  # running in OSX?

    return pool
        
        
if __name__ == "__main__":
    main()
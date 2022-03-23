#!/usr/bin/env python

import sqlite3
import pandas as pd
from sys import argv
from os import path
import glob
from tqdm import tqdm

def main():
    input_tables_folder = argv[1]
    genome_sequencing_folder = argv[2]
    output_database_path = argv[3]

    return generate_sql_database(input_tables_folder, genome_sequencing_folder, output_database_path)


"""
Load all related tsv files in "input_tables_folder", parse, then
output the SQLite database file to "output_database_path"
"""
def generate_sql_database(input_tables_folder, genome_sequencing_folder, output_database_path):

    # check if file exists

    if path.exists(output_database_path):
        print("SQL database exists! {}".format(output_database_path))
        return 1

    # first, initiate the sqlite database schema

    print("initiating database..")
    with sqlite3.connect(output_database_path) as con:
        cur = con.cursor()
        with open(path.join(path.dirname(__file__), "sql_schema.txt")) as fp:
            con.executescript(fp.read())

    # parse strains data

    def parse_strains_data():
        print("parsing strains data..")
        strains_data_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-strains-*.tsv"))
        )

        print("found {} files".format(len(strains_data_files)))
        all_strains_data = pd.concat([
            pd.read_csv(filepath, sep="\t").fillna("") for filepath in strains_data_files
        ])

        print("inserting {} rows".format(all_strains_data.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            all_strains_data.to_sql("strains", con, if_exists='append', index=False)

    parse_strains_data()

    # parse strains location data

    def parse_locations_data():

        print("parsing strains location data..")
        strains_archive_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-stocks-*.tsv"))
        )

        print("found {} files".format(len(strains_archive_files)))
        all_strains_archives = pd.concat([
            pd.read_csv(filepath, sep="\t").fillna("") for filepath in strains_archive_files
        ])

        print("inserting {} rows".format(all_strains_archives.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            all_strains_archives.to_sql("stocks", con, if_exists='append', index=False)

    parse_locations_data()

    # parse gdna data

    def parse_gdna_data():

        print("parsing gdna data..")
        gdna_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-gdnas-*.tsv"))
        )

        print("found {} files".format(len(gdna_files)))
        all_gdnas = pd.concat([
            pd.read_csv(filepath, sep="\t").fillna("") for filepath in gdna_files
        ])

        """
        all_gdnas["gdna_id"] = (
            "GDNA-" + 
            all_gdnas["plate"].map(
                lambda x: (
                    "T{:03d}".format(int(x[1:])) if x.startswith("T") else (
                        "X{:03d}".format(int(x[1:])) if x.startswith("X") else "{:04d}".format(int(x))
                    )
                )
            ) +
            all_gdnas["well"].map(lambda x: "{}{:02d}".format(x[0].upper(), int(x[1:])))
        )
        """

        print("inserting {} rows".format(all_gdnas.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            all_gdnas.to_sql("gdnas", con, if_exists='append', index=False)

    parse_gdna_data()

    # parse projects data

    def parse_projects_data():

        print("parsing projects data..")
        projects_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-projects-*.tsv"))
        )

        print("found {} files".format(len(projects_files)))
        projects_data = pd.concat([
            pd.read_csv(filepath, sep="\t").fillna("") for filepath in projects_files
        ])

        print("inserting {} rows".format(projects_data.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            projects_data.to_sql("sequencing_projects", con, if_exists='append', index=False)

    parse_projects_data()

    # parse batches data

    def parse_batches_data():

        print("parsing sequencing batches data..")
        batches_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-batches-*.tsv"))
        )

        print("found {} files".format(len(batches_files)))
        batches_data = pd.concat([
            pd.read_csv(filepath, sep="\t").fillna("") for filepath in batches_files
        ])

        print("inserting {} rows".format(batches_data.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            batches_data.to_sql("sequencing_batches", con, if_exists='append', index=False)

    parse_batches_data()

    # parse samples data

    def parse_samples_data():

        print("parsing sequencing samples data..")
        samples_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-samples-*.tsv"))
        )

        print("found {} files".format(len(samples_files)))
        samples_data = pd.concat([
            pd.read_csv(filepath, sep="\t").fillna("") for filepath in samples_files
        ])

        print("inserting {} rows".format(samples_data.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            samples_data.to_sql("sequencing_samples", con, if_exists='append', index=False)

    parse_samples_data()

    def scan_sequencing_folder():

        print("scanning raw reads...")
        read_indices = set([(x.split("/")[-3], x.split("/")[-2]) for x in glob.iglob(path.join(
            genome_sequencing_folder, "filtered_reads", "*", "*", "*.R1.fastq.gz"
        )) if x.split("/")[-2] == x.split("/")[-1].split(".R1.fastq.gz")[0]])

        print("scanning assembled genomes...")
        genome_indices = set([(x.split("/")[-4], x.split("/")[-2]) for x in glob.iglob(path.join(
            genome_sequencing_folder, "genomes", "per_batches", "*", "all_genomes", "*", "*.fna"
        )) if x.split("/")[-2] == x.split("/")[-1].split(".fna")[0]])

        merged_indices = sorted(read_indices.union(genome_indices))

        print("found {:,} total sequences, parsing...".format(len(merged_indices)))

        result = []
        for dataset, name in tqdm(merged_indices):
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
                    print("WARNING: {} missing stats.txt (skipped)".format(data["read_file_folder"]))
                    continue
                with open(stats_file, "r") as ii:
                    lines = ii.readlines()
                    try:
                        data["reads_gc"] = float(lines[1].split("\t")[7]) * 100
                        data["reads_gc_stdev"] = float(lines[1].split("\t")[8]) * 100
                        data["reads_count"] = int(lines[3].split("\t")[1])
                        data["reads_size"] = int(float(lines[5].split("\t")[1].split(" ")[0]) * 1000000)
                    except:
                        print("WARNING: {} file is corrupted!".format(stats_file))
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
                            lines = oo.readlines()
                            data["genome_size"] = int(lines[1].split(",")[0].split(" = ")[1])
                            data["num_contigs"] = int(lines[1].split(",")[1].split(" = ")[1])
                            data["n50"] = int(lines[2].split(",")[0].split(" = ")[1])
                    except:
                        print("WARNING: failed to parse {} (corrupted?)".format(assembly_stats_path))
                elif data["finished_qc"]:
                    print("WARNING: {} marked as 'finished QC' but lack assembly-stats files, please re-run QC!".format(fp))
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
                        print("WARNING: failed to parse {} (corrupted?)".format(checkm_path))
                elif data["finished_qc"]:
                    print("WARNING: {} marked as 'finished QC' but lack checkM files, please re-run QC!".format(fp))
                    data["passed_qc"] = None

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
                        print("WARNING: failed to parse {} (corrupted?)".format(gtdb_path))

                    if path.exists(antismash_path):
                        data["annotated"] = True
                    else:
                        data["annotated"] = False
                else:
                    data["annotated"] = False

                data["failed_assembly"] = False

            result.append(data)

        result = pd.DataFrame(result)
        result.index = result["dataset"] + "/" + result["name"]
        return result

    df_sequencing = scan_sequencing_folder()
    
    def insert_sequencing_data():
                
        print("scanning link files...")

        links_files = list(
            glob.iglob(path.join(input_tables_folder, "npdc_db-links-*.tsv"))
        )

        print("found {} files".format(len(links_files)))
        links_data = pd.concat([
            pd.read_csv(filepath, sep="\t").fillna("") for filepath in links_files
        ])

        print("linking {} sequences".format(links_data.shape[0]))
        df_sequencing.loc[links_data["dataset"].values + "/" + links_data["name"].values, "linked_sequencing_id"] = links_data["sequencing_id"].values
        
        # print warnings for unlinked sequences
        for idx, row in df_sequencing[df_sequencing["linked_sequencing_id"].isna()].iterrows():
            print("WARNING: found no linkage info for {} (skipping)".format(idx))
        
        # insert the rest
        df_sequencing_linked = df_sequencing[~df_sequencing["linked_sequencing_id"].isna()]
        print("inserting {} rows".format(df_sequencing_linked.shape[0]))
        with sqlite3.connect(output_database_path) as con:
            df_sequencing_linked = pd.DataFrame({
                "orig_identifier": df_sequencing_linked.index,
                "sequencing_id": df_sequencing_linked["linked_sequencing_id"],
                "assembly_status": df_sequencing_linked["failed_assembly"].map(lambda x: 1 if x == True else (0 if x == False else -1)),
                "qc_status": df_sequencing_linked.apply(lambda row: -1 if row["finished_qc"] != True else (1 if row["passed_qc"] == True else 0), axis=1),
                "annotation_status": df_sequencing_linked["annotated"].map(lambda x: 1 if x == True else (0 if x == False else -1)),
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
                "genome_taxa_phylum": df_sequencing_linked["phylum_gtdb"],
                "genome_taxa_genus": df_sequencing_linked["genus_gtdb"],
                "genome_taxa_species": df_sequencing_linked["species_gtdb"],
                "genome_taxa_ref_fastani": df_sequencing_linked["fastANI_gtdb"],
            })
            df_sequencing_linked.to_sql("sequences", con, if_exists='append', index=False)
        
        return
    
    insert_sequencing_data()
        
    print("completed.")

    
if __name__ == "__main__":
    main()
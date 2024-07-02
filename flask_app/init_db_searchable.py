#!/usr/bin/env python3

from app.config import conf
from os import path
import sqlite3
from sys import argv
import json
import datetime
import pandas as pd
import logging

# Configure logging
logging.basicConfig(filename='init_db.log', level=logging.INFO)

def check_and_add_column(con, table, column, dtype):
    """Check if a column exists in a table, and add it if it does not."""
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    columns = [info[1] for info in cur.fetchall()]
    if column not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {dtype}")
        con.commit()

def populate_bgc_size_column(con):
    """Populate the bgc_size_kb column with calculated values."""
    cur = con.cursor()
    cur.execute("UPDATE bgcs SET bgc_size_kb = (nt_end - nt_start) / 1000.0")
    con.commit()

def populate_bgc_name_column(con):
    """Populate the bgcs_name column with values based on species and genus."""
    cur = con.cursor()
    # Assuming 'species' and 'genus' are columns in the 'bgcs' table
    # This SQL CASE statement mirrors the logic of your Python function
    update_sql = """
    UPDATE bgcs_cached
    SET bgc_name = CASE
                        WHEN species != '' AND species IS NOT NULL THEN species
                        WHEN genus != '' AND genus IS NOT NULL THEN genus || ' spp.'
                        ELSE 'Unknown bacterium'
                    END
    """
    cur.execute(update_sql)
    con.commit()

def populate_genome_name_column(con):
    """Populate the genome_name column with values based on species and genus."""
    cur = con.cursor()
    # Assuming 'species' and 'genus' are columns in the 'genomes' table
    # This SQL CASE statement mirrors the logic of your Python function
    update_sql = """
    UPDATE genomes_cached
    SET genome_name = (
        SELECT CASE
            WHEN genomes.genome_gtdb_species != '' AND genomes.genome_gtdb_species IS NOT NULL THEN genomes.genome_gtdb_species
            WHEN genomes.genome_gtdb_genus != '' AND genomes.genome_gtdb_genus IS NOT NULL THEN genomes.genome_gtdb_genus || ' spp.'
            ELSE 'Unknown bacterium'
        END
        FROM genomes
        WHERE genomes.id = genomes_cached.genome_id
    )
    """
    cur.execute(update_sql)
    con.commit()

def populate_strain_name_column(con):
    """Populate the strain_name column in strains_cached based on species and genus from the genomes table."""
    cur = con.cursor()
    update_sql = """
    UPDATE strains_cached
    SET strain_name = (
        SELECT CASE
            WHEN genomes.genome_gtdb_species != '' THEN genomes.genome_gtdb_species
            WHEN genomes.genome_gtdb_genus != '' THEN genomes.genome_gtdb_genus || ' spp.'
            WHEN strains.empirical_genus != '' THEN 'Unknown ' || strains.empirical_genus
            WHEN strains.empirical_category != '' THEN 'Unknown ' || strains.empirical_category
            ELSE 'Unknown bacterium'
        END
        FROM strains
        LEFT JOIN genomes ON strains.npdc_id = genomes.npdc_id
        WHERE strains.npdc_id = strains_cached.npdc_id
    )
    """
    cur.execute(update_sql)
    con.commit()

def populate_bgc_label_column(con):
    """Populate the bgc_label column with a formatted string based on npdc_id from bgcs_cached, contig_num, and the region part extracted from orig_identifier in bgcs."""
    cur = con.cursor()
    
    # Update SQL to extract numeric part after ".region" and integrate it into the bgc_region_contig value
    update_sql = """
    UPDATE bgcs_cached
    SET bgc_region_contig = (
        SELECT 'NPDC-' || bgcs_cached.npdc_id || ':r' || bgcs.contig_num || 'c' || 
               CAST(substr(orig_identifier, instr(orig_identifier, 'region') + 6) AS INTEGER)
        FROM bgcs
        WHERE bgcs.id = bgcs_cached.bgc_id
    )
    """
    cur.execute(update_sql)
    con.commit()

def populate_fragmented_status_column(con):
    """Populate the fragmented_status column with 'fragmented' or 'complete' based on the fragmented column."""
    cur = con.cursor()

    try:
        # SQL to update fragmented_status column
        update_sql = """
        UPDATE bgcs
        SET fragmented_status = CASE
                                  WHEN fragmented = 1 THEN 'fragmented'
                                  WHEN fragmented = 0 THEN 'complete'
                                  ELSE 'unknown'
                               END
        """
        cur.execute(update_sql)
        con.commit()
        logging.info("Fragmented status column populated successfully.")

    except Exception as e:
        logging.error("Error populating fragmented status column: %s", e)

def populate_mibig_hit_display_column(con):
    """Populate the mibig_hit_display column with just the mibig_id."""
    cur = con.cursor()
    try:
        # Populate mibig_hit_display with mibig_id, assuming it's stored as an integer.
        cur.execute("""
            UPDATE bgcs_cached
            SET mibig_hit_display = CASE
                WHEN mibig_hit_id > -1 THEN 'BGC' || printf('%07d', mibig_hit_id)
                ELSE 'n/a'
            END
        """)
        con.commit()
    except Exception as e:
        logging.error("Error populating mibig_hit_display column: %s", e)

def populate_assembly_status(con):
    """Populate the genome_assembly_status column based on the number of contigs."""
    cur = con.cursor()
    # Fetch all genomes to calculate their assembly status
    cur.execute("SELECT id, genome_num_contigs FROM genomes")
    for genome in cur.fetchall():
        genome_id, genome_num_contigs = genome
        # Determine assembly grade based on num_contigs
        if genome_num_contigs <= 50:
            assembly_grade = "high"
        elif genome_num_contigs <= 100:
            assembly_grade = "good"
        elif genome_num_contigs <= 500:
            assembly_grade = "fair"
        else:
            assembly_grade = "fragmented"

        # Update the assembly_status for each genome record
        cur.execute("UPDATE genomes SET genome_assembly_grade = ? WHERE id = ?", (assembly_grade, genome_id))

    con.commit()

def populate_genomes_known_bgcs(con):
    """Populate the genomes_known_bgcs column with the count of unique non-empty name_bgcs_mibig values."""
    check_and_add_column(con, 'genomes_cached', 'genomes_known_bgcs', 'INTEGER')
    
    cur = con.cursor()
    # Fetch all records to process their known bgcs from genomes_cached
    cur.execute("SELECT genome_id, name_bgcs_mibig FROM genomes_cached")
    
    for genome in cur.fetchall():
        genome_id, name_bgcs_mibig = genome
        # Deduplicate name_bgcs_mibig values and count non-empty, trimmed entries
        if name_bgcs_mibig:
            deduplicated_count = len(set(filter(None, [bgcs.strip() for bgcs in name_bgcs_mibig.split('|')])))
        else:
            deduplicated_count = 0
                
        # Update the genome_known_bgcs for each record in genomes_cached with the count of unique bgcs
        cur.execute("UPDATE genomes_cached SET genomes_known_bgcs = ? WHERE genome_id = ?", (deduplicated_count, genome_id))
    
    con.commit()

def populate_genome_available_column(con):
    """Populate the genome_available column in strains based on the presence of a linked genome."""
    cur = con.cursor()
    # This query updates the genome_available column to 'Yes' if a matching npdc_id is found in the genomes table, 'No' otherwise.
    update_sql = """
    UPDATE strains
    SET genome_available = (
        SELECT CASE
            WHEN EXISTS (
                SELECT 1 FROM genomes WHERE genomes.npdc_id = strains.npdc_id
            ) THEN 'Yes'
            ELSE 'No'
        END
    )
    """
    cur.execute(update_sql)
    con.commit()

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
            con.commit()
                path.dirname(__file__),
                "..",
                "sql_schemas",
                "sql_schema_jobs.txt",
            )
            with open(schema_sql, "r") as sql_script:
                cur.executescript(sql_script.read())
                con.commit()
    # check and generate npdc_db cache tables
    with sqlite3.connect(conf["db_path"]) as con:
        cur = con.cursor()
        
        check_and_add_column(con, 'bgcs', 'bgc_size_kb', 'REAL')
        check_and_add_column(con, 'bgcs_cached', 'bgc_name', 'TEXT')
        check_and_add_column(con, 'bgcs_cached', 'bgc_region_contig', 'TEXT')
        check_and_add_column(con, 'bgcs', 'fragmented_status', 'TEXT')
        check_and_add_column(con, 'bgcs_cached', 'mibig_hit_display', 'TEXT')
        check_and_add_column(con, 'genomes_cached', 'genome_name', 'TEXT')
        check_and_add_column(con, 'genomes', 'genome_assembly_grade', 'TEXT')
        check_and_add_column(con, 'genomes_cached', 'genomes_known_bgcs', 'INTEGER')
        check_and_add_column(con, 'strains_cached', 'strain_name', 'TEXT')
        check_and_add_column(con, 'strains', 'genome_available', 'TEXT')

        populate_bgc_size_column(con)
        populate_bgc_name_column(con)
        populate_bgc_label_column(con)
        populate_fragmented_status_column(con)
        populate_mibig_hit_display_column(con)
        populate_genome_name_column(con)
        populate_assembly_status(con)
        populate_genomes_known_bgcs(con)
        populate_strain_name_column(con)
        populate_genome_available_column(con)

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
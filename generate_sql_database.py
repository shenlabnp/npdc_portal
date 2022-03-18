#!/usr/bin/env python

import sqlite3
import pandas as pd
from sys import argv
from os import path
import glob

def main():
	input_tables_folder = argv[1]
	output_database_path = argv[2]

	return generate_sql_database(input_tables_folder, output_database_path)


"""
Load all related tsv files in "input_tables_folder", parse, then
output the SQLite database file to "output_database_path"
"""
def generate_sql_database(input_tables_folder, output_database_path):

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



if __name__ == "__main__":
    main()
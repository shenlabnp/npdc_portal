#!/usr/bin/env python3
from os import path

# path to result folder
conf = {
    "instance_folder": path.abspath(
        path.join(
            path.dirname(__file__), "..", "..", "instance"
        )
    )
}

conf["db_path_original"] = path.join(conf["instance_folder"], "db_data/npdc_portal.db")
conf["db_path"] = path.join(conf["instance_folder"], "db_data/npdc_portal_searchable.db")
conf["cds_fasta_path"] = path.join(conf["instance_folder"], "db_data/npdc_portal.fasta")
conf["genome_folder_path"] = path.join(conf["instance_folder"], "db_data/genome_files/")
conf["bgc_folder_path"] = path.join(conf["instance_folder"], "db_data/bgc_files/")
conf["user_db_path"] = path.join(conf["instance_folder"], "accounts.db")
conf["query_db_path"] = path.join(conf["instance_folder"], "queries.db")
conf["session_key_path"] = path.join(conf["instance_folder"], "session_key.txt")
conf["email_config_path"] = path.join(conf["instance_folder"], "email_config.json")
conf["app_config_path"] = path.join(conf["instance_folder"], "app_config.json")
conf["strain_pictures_folder_path"] = path.join(conf["instance_folder"], "strain_pictures")
conf["temp_download_folder"] = path.join(conf["instance_folder"], "tmp_download")

# other app-specific configurations
conf["is_in_beta"] = False
conf["launch_datetime"] = "1901-01-01 00:00:00"
conf["knowncb_cutoff"] = 80
conf["consecutive_download_duration"] = 15 # in seconds

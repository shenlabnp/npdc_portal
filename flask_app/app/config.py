#!/usr/bin/env python3
from os import path

# path to result folder
conf = {
    "instance_folder": path.join(
        path.dirname(__file__), "..", "..", "instance"
    )
}

conf["db_path"] = path.join(conf["instance_folder"], "db_data/npdc_portal.db")
conf["user_db_path"] = path.join(conf["instance_folder"], "accounts.db")
conf["query_db_path"] = path.join(conf["instance_folder"], "queries.db")
conf["session_key_path"] = path.join(conf["instance_folder"], "session_key.txt")
conf["email_config_path"] = path.join(conf["instance_folder"], "email_config.json")
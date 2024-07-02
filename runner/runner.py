#!/usr/bin/env python3

from multiprocessing import Process
from time import sleep
import subprocess
from sys import argv
from os import path
from datetime import datetime
import glob

from runner_config import conf


def start_webserver(num_threads, port):

    while True:

        try:
            print("starting WEBSERVER")
            cmd = (
                "gunicorn -w {} -b 0.0.0.0:{} --log-level debug \"npdc:portal()\"".format(
                    num_threads,
                    port
                )
            )
            subprocess.check_output(cmd,
                cwd=path.join(path.dirname(path.dirname(__file__)), "flask_app"),
                shell=True
            )
        except subprocess.CalledProcessError as e:
            print(e.output)
            print("WEBSERVER ERROR!!")
        print("restarting WEBSERVER in 5 seconds...")
        sleep(5)

    return


def start_blastserver(num_threads, ram_size_gb, use_srun):

    while True:

        try:
            print("starting BLASTSERVER")
            cmd = (
                "python deploy_workers.py {} {} {}".format(
                    num_threads,
                    ram_size_gb,
                    1 if use_srun else 0
                )
            )
            subprocess.check_output(cmd,
                cwd=path.join(path.dirname(path.dirname(__file__)), "query_processor"),
                shell=True
            )
        except subprocess.CalledProcessError as e:
            print(e.output)
            print("BLASTSERVER ERROR!!")
        print("restarting BLASTSERVER in 5 seconds...")
        sleep(5)

    return


def start_downloadserver(num_threads, use_srun):

    while True:

        try:
            print("starting DOWNLOADSERVER")
            cmd = (
                "python result_download_processor.py {} {}".format(
                    num_threads,
                    1 if use_srun else 0
                )
            )
            subprocess.check_output(cmd,
                cwd=path.join(path.dirname(path.dirname(__file__)), "query_processor"),
                shell=True
            )
        except subprocess.CalledProcessError as e:
            print(e.output)
            print("DOWNLOADSERVER ERROR!!")
        print("restarting DOWNLOADSERVER in 5 seconds...")
        sleep(5)

    return


def autobackup():

    backup_folder = path.abspath(path.join(path.dirname(path.dirname(__file__)), "instance", "backups"))

    while True:
        all_backups = [path.basename(fp) for fp in sorted(glob.glob(path.join(backup_folder, "backup-*")), reverse=True)]
        do_backup = False
        backup_name = "backup-{}".format(datetime.now().strftime("%Y-%m-%d"))

        if len(all_backups) < 1:
            do_backup = True
        elif all_backups[0] < backup_name:
            do_backup = True

        if do_backup:
            print("BACKING UP DBs.....")
            subprocess.run("mkdir {}".format(
                path.join(backup_folder, backup_name)
            ), shell=True)
            subprocess.run("cp {} {}".format(
                path.abspath(path.join(path.dirname(path.dirname(__file__)), "instance", "accounts.db")),
                path.join(backup_folder, backup_name, "accounts.db")
            ), shell=True)
            subprocess.run("cp {} {}".format(
                path.abspath(path.join(path.dirname(path.dirname(__file__)), "instance", "queries.db")),
                path.join(backup_folder, backup_name, "queries.db")
            ), shell=True)
            

        sleep(60)

    return


def main():

    process_webserver = Process(
        target=start_webserver,
        args=(
            conf["webserver_num_threads"],
            conf["webserver_port"]
        )
    )
    process_webserver.start()

    process_blastserver = Process(
        target=start_blastserver,
        args=(
            conf["blastserver_num_threads"],
            conf["blastserver_ram_size_gb"],
            conf["blastserver_use_srun"]
        )
    )
    process_blastserver.start()

    process_downloadserver = Process(
        target=start_downloadserver,
        args=(
            conf["downloadserver_num_threads"],
            conf["downloadserver_use_srun"])
        )
    process_downloadserver.start()

    process_autobackup = Process(
        target=autobackup
    )
    process_autobackup.start()

    process_webserver.join()
    process_blastserver.join()
    process_downloadserver.join()

if __name__ == '__main__':
    exit(main())

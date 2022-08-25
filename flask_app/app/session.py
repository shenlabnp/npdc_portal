#!/usr/bin/env python3
from flask import session
import sqlite3
import pandas as pd
from .config import conf
from datetime import datetime


def check_logged_in():
    cur_userid = session.get("userid", -1)
    if cur_userid == -1:
        return False
    else:
        try:
            with sqlite3.connect(conf["user_db_path"]) as con:
                cur_userdata =  pd.read_sql_query((
                    "select * from users where id=?"
                ), con=con, params=(cur_userid,)).iloc[0].to_dict()

                # update last_login and num_login
                last_login = datetime.strptime(cur_userdata["last_login"], "%Y-%m-%d %H:%M:%S")
                cur_datetime = datetime.now()
                if (cur_datetime - last_login).days > 0 or cur_userdata["num_login"] == 0:
                    cur_userdata["num_login"] += 1
                cur_userdata["last_login"] = cur_datetime.strftime("%Y-%m-%d %H:%M:%S")
                con.cursor().execute((
                    "update users set num_login=?, last_login=? where id=?"
                ), (cur_userdata["num_login"], cur_userdata["last_login"], cur_userdata["id"]))

                # save in session
                session["userdata"] = cur_userdata
                return True
        except:
            session.pop("userid", None)
            session.pop("userdata", None)
            return False
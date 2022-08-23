#!/usr/bin/env python3
from flask import session


def check_logged_in():
	if session.get("username", "") != "":
		return True
	else:
		return False
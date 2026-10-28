#!/usr/bin/env python3
"""Write SUB-01's one login identity (owner 10-28: a dedicated account, one password everywhere) for the agent.

Run it yourself in the pod's Jupyter terminal:  python3 /home/unreal/.sub01-private/set_sub01_login.py
It asks for the e-mail, a username and the password (hidden, twice) and writes
/home/unreal/.sub01-private/sub01-login.json (0600, owner unreal). Nothing is printed or logged; the password never
goes through chat, git or any model: the agent types {{password}} and fills it in at the moment of typing.
"""
import getpass
import json
import os
import pwd
import sys

PATH = "/home/unreal/.sub01-private/sub01-login.json"


def main():
    email = input("E-mail of SUB-01's account: ").strip()
    username = input("Username for sign-ups (Enter = the part before @): ").strip() or email.split("@")[0]
    password = getpass.getpass("Password (hidden): ")
    if password != getpass.getpass("Password again: "):
        sys.exit("the two passwords differ: nothing written")
    if "@" not in email or not 8 <= len(password) <= 200 or not 1 <= len(username) <= 200 or "\n" in password:
        sys.exit("need an e-mail, a username and a password of 8 to 200 characters: nothing written")
    tmp = PATH + ".new"
    old = os.umask(0o077)
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"email": email, "username": username, "password": password}, f)
        if os.geteuid() == 0:
            u = pwd.getpwnam("unreal")
            os.chown(tmp, u.pw_uid, u.pw_gid)
        os.replace(tmp, PATH)
    finally:
        os.umask(old)
    print("saved (0600). The agent reads it at each login; run this again to change it.")


if __name__ == "__main__":
    main()

#!/usr/bin/python3

"""Nexia Climate Device Access"""

import argparse

from nexia.home import NexiaHome

parser = argparse.ArgumentParser()
parser.add_argument("--username", type=str, help="Your Nexia username/email address.")
parser.add_argument("--password", type=str, help="Your Nexia password.")
args = parser.parse_args()

if args.username and args.password:
    nexia_home = NexiaHome(username=args.username, password=args.password)
else:
    parser.print_help()
    exit()

print(nexia_home.devices_json)
print(nexia_home.automations_json)

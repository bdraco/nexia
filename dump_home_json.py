#!/usr/bin/python3

"""Nexia Climate Device Access"""

import argparse
import logging

from nexia.home import NexiaHome
from nexia.const import BRAND_NEXIA

parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_const", const=True, help="Enable debug.")
parser.add_argument("--brand", type=str, help="Brand (nexia or asair or trane).")
parser.add_argument("--username", type=str, help="Your username/email address.")
parser.add_argument("--password", type=str, help="Your password.")
args = parser.parse_args()
brand = args.brand or BRAND_NEXIA

if args.debug:
    logging.basicConfig(level=logging.DEBUG)

if args.username and args.password:
    nexia_home = NexiaHome(username=args.username, password=args.password, brand=brand)
else:
    parser.print_help()
    exit()

print(nexia_home.devices_json)
print(nexia_home.automations_json)

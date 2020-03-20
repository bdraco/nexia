#!/usr/bin/python3

"""Nexia Climate Device Access"""

import argparse
import pprint

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

count = 0
for phone_id in nexia_home.get_phone_ids():
    count += 1
    if count < 5:
        continue

    print("Delete phone id: ", phone_id)
    response = nexia_home.session.delete(
        "https://www.mynexia.com/mobile/phones/" + str(phone_id),
        headers=nexia_home._api_key_headers(),
    )
    pprint.pprint(response)

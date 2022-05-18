#!/usr/bin/python3

"""Nexia Climate Device Access"""

import argparse
import asyncio
import pprint

import aiohttp

from nexia.const import BRAND_NEXIA
from nexia.home import NexiaHome


async def _runner(username, password, brand):
    session = aiohttp.ClientSession()
    try:
        nexia_home = NexiaHome(
            session, username=username, password=password, brand=brand
        )
        await nexia_home.login()
        count = 0
        for phone_id in await nexia_home.get_phone_ids():
            count += 1
            if count < 5:
                continue

            print("Delete phone id: ", phone_id)
            response = await nexia_home.session.delete(
                "https://www.mynexia.com/mobile/phones/" + str(phone_id),
                headers=nexia_home._api_key_headers(),
            )
            pprint.pprint(response)
    finally:
        await session.close()
    return nexia_home


parser = argparse.ArgumentParser()
parser.add_argument("--brand", type=str, help="Brand (nexia or asair or trane).")
parser.add_argument("--username", type=str, help="Your Nexia username/email address.")
parser.add_argument("--password", type=str, help="Your Nexia password.")
args = parser.parse_args()
brand = args.brand or BRAND_NEXIA

if args.username and args.password:
    nexia_home = asyncio.run(_runner(args.username, args.password, brand))
else:
    parser.print_help()
    exit()

#!/usr/bin/python3

"""Nexia Climate Device Access"""

import argparse
import code
import readline
import rlcompleter
import aiohttp
import asyncio
import logging

from nexia.const import BRAND_NEXIA
from nexia.home import NexiaHome

parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_const", const=True, help="Enable debug.")
parser.add_argument("--brand", type=str, help="Brand (nexia or asair or trane).")
parser.add_argument("--username", type=str, help="Your Nexia username/email address.")
parser.add_argument("--password", type=str, help="Your Nexia password.")

args = parser.parse_args()
brand = args.brand or BRAND_NEXIA

if args.debug:
    logging.basicConfig(level=logging.DEBUG)

async def _runner(username, password, brand):
    session = aiohttp.ClientSession()
    try:
        nexia_home = NexiaHome(session, username=username, password=password, brand=brand)
        await nexia_home.login()
        await nexia_home.update()
    finally:
        await session.close()
    return nexia_home

if args.username and args.password:
    nexia_home = asyncio.run(_runner(args.username, args.password, brand))
else:
    parser.print_help()
    exit()

variables = globals()
print("NexiaThermostat instance can be referenced using t_{id}.<command>.")
print("Room IQ instance can be referenced using i_{id}.<command>.")
print("Zone instance can be referenced using z_{id}.<command>.")
print("List of available thermostats and zones:")
for _thermostat_id in nexia_home.get_thermostat_ids():
    thermostat = nexia_home.get_thermostat_by_id(_thermostat_id)
    _thermostat_name = thermostat.get_name()
    _thermostat_model = thermostat.get_model()
    _thermostat_compressor_speed = thermostat.get_current_compressor_speed()

    variables[f"t_{_thermostat_id}"] = thermostat

    print(
        f't_{_thermostat_id} - "{_thermostat_name}" ({_thermostat_model}) [{_thermostat_compressor_speed}]'
    )

    print(" Room IQs:")
    for _room_iq_id in thermostat.get_room_iq_ids():
        iq = thermostat.get_room_iq_by_id(_room_iq_id)
        _iq_name = iq.get_name()
        _iq_weight = iq.get_weight()
        _iq_temp = iq.get_temperature()
        _iq_hum = iq.get_humidity()
        _iq_batt = iq.get_battery_level()

        variables[f"i_{_room_iq_id}"] = iq

        print(f'    i_{_room_iq_id} - "{_iq_name}" ({_iq_weight}) temp={_iq_temp} hum={_iq_hum} batt={_iq_batt}')


    print("  Zones:")
    for _zone_id in thermostat.get_zone_ids():
        zone = thermostat.get_zone_by_id(_zone_id)
        _zone_name = zone.get_name()
        _zone_status = zone.get_status()

        variables[f"z_{_zone_id}"] = zone

        print(f'    z_{_zone_id} - "{_zone_name}" ({_zone_status})')

readline.set_completer(rlcompleter.Completer(variables).complete)
readline.parse_and_bind("tab: complete")
code.InteractiveConsole(variables).interact()

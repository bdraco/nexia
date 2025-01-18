#!/usr/bin/python3

"""Nexia Climate Device Access"""

import argparse
import code
import readline
import rlcompleter
import time

import asyncio
import aiohttp

from nexia.home import NexiaHome

def displaystatus(nexia_home):
    print("NexiaThermostat instance can be referenced using nt.<command>.")
    print("List of available thermostats and zones:")
    for _thermostat_id in nexia_home.get_thermostat_ids():
        thermostat = nexia_home.get_thermostat_by_id(_thermostat_id)
        _thermostat_name = thermostat.get_name()
        _thermostat_model = thermostat.get_model()
        _thermostat_compressor_speed = thermostat.get_current_compressor_speed()
        
        print(
            f'{_thermostat_id} - "{_thermostat_name}" ({_thermostat_model}) [{_thermostat_compressor_speed}]'
        )
        _thermostat_firmware = thermostat.get_firmware()
        print( f'Firmware: {_thermostat_firmware}' )
        _thermostat_dev_build_number = thermostat.get_dev_build_number()
        print( f'Build   : {_thermostat_dev_build_number}' )
        _thermostat_has_outdoor_temperature = thermostat.has_outdoor_temperature()
        _thermostat_has_relative_humidity = thermostat.has_relative_humidity()
        _thermostat_has_variable_speed_compressor = thermostat.has_variable_speed_compressor()
        _thermostat_has_emergency_heat = thermostat.has_emergency_heat()
        _thermostat_has_variable_fan_speed = thermostat.has_variable_fan_speed()
        _thermostat_has_zones = thermostat.has_zones()
        _thermostat_has_dehumidify_support = thermostat.has_dehumidify_support()
        _thermostat_has_humidify_support = thermostat.has_humidify_support()
        
        print( f'Has Outdoor Temperature   : {_thermostat_has_outdoor_temperature}' )
        print( f'Has Relative Humidity     : {_thermostat_has_relative_humidity}' )
        print( f'Has Variable Compressor   : {_thermostat_has_variable_speed_compressor}' )
        print( f'Has Emergency Heat        : {_thermostat_has_emergency_heat}' )
        print( f'Has Variable Fan          : {_thermostat_has_variable_fan_speed}' )
        print( f'Has Zones                 : {_thermostat_has_zones}' )
        print( f'Has Dehumidify Support    : {_thermostat_has_dehumidify_support}' )
        print( f'Has Humidify Support      : {_thermostat_has_humidify_support}' )

        _thermostat_fanmode = thermostat.get_fan_mode()
        print( f'Fan Mode                  : {_thermostat_fanmode}' )

        print("  Zones:")

        for _zone_id in thermostat.get_zone_ids():
            zone = thermostat.get_zone_by_id(_zone_id)
            _zone_name = zone.get_name()
            _zone_status = zone.get_status()

            print(f'    {_zone_id} - "{_zone_name}" ({_zone_status})')


async def _runner(username, password, brand):
    session = aiohttp.ClientSession()
    try:
        nexia_home = NexiaHome(
            session, username=username, password=password, brand=brand
        )
        await nexia_home.login()
        await nexia_home.update()
        displaystatus(nexia_home)

        """ Various tests """
        # await nexia_home.thermostats[0].zones[0].set_heat_cool_temp(cool_temperature=76.0)
        await nexia_home.thermostats[0].set_fan_mode("on")

        time.sleep(5)

        displaystatus(nexia_home)

    finally:
        await session.close()
    return nexia_home


parser = argparse.ArgumentParser()
parser.add_argument("--username", type=str, help="Your Nexia username/email address.")
parser.add_argument("--password", type=str, help="Your Nexia password.")
parser.add_argument("--brand", type=str, help="Brand (nexia or asair or trane).")

args = parser.parse_args()

if args.username and args.password and args.brand:
    # nexia_home = NexiaHome(username=args.username, password=args.password, brand=args.brand)
    nexia_home = asyncio.run(_runner(username=args.username, password=args.password, brand=args.brand))
else:
    parser.print_help()
    exit()




variables = globals()
variables.update(locals())

readline.set_completer(rlcompleter.Completer(variables).complete)
readline.parse_and_bind("tab: complete")
# code.InteractiveConsole(variables).interact()

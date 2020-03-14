"""Nexia Climate Device Access"""

import argparse
import code
import readline
import rlcompleter

from nexia.home import NexiaHome

parser = argparse.ArgumentParser()
parser.add_argument("--username", type=str, help="Your Nexia username/email address.")
parser.add_argument("--password", type=str, help="Your Nexia password.")
parser.add_argument(
    "--offline_json",
    type=str,
    help="Offline JSON file to load. No NexiaHome communication will be performed.",
)

args = parser.parse_args()
if args.offline_json:
    nexia_home = NexiaHome(offline_json=args.offline_json)
elif args.username and args.password:
    nexia_home = NexiaHome(username=args.username, password=args.password)
else:
    parser.print_help()
    exit()

print("NexiaThermostat instance can be referenced using nt.<command>.")
print("List of available thermostats and zones:")
for _thermostat_id in nexia_home.get_thermostat_ids():
    thermostat = nexia_home.get_thermostat_by_id(_thermostat_id)
    _thermostat_name = thermostat.get_thermostat_name()
    _thermostat_model = thermostat.get_thermostat_model()
    print(f'{_thermostat_id} - "{_thermostat_name}" ({_thermostat_model})')
    print(f"  Zones:")

    for _zone_id in thermostat.get_zone_ids():
        zone = thermostat.get_zone_by_id(_zone_id)
        _zone_name = zone.get_name()
        _zone_status = zone.get_status()

        print(f'    {_zone_id} - "{_zone_name}" ({_zone_status})')
del (
    _thermostat_id,
    _thermostat_model,
    _thermostat_name,
    _zone_name,
    _zone_id,
    args,
    parser,
)

nexia_home.update()


variables = globals()
variables.update(locals())

readline.set_completer(rlcompleter.Completer(variables).complete)
readline.parse_and_bind("tab: complete")
code.InteractiveConsole(variables).interact()

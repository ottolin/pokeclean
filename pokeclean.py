#!/usr/bin/env python
"""
pgoapi - Pokemon Go API
Copyright (c) 2016 tjado <https://github.com/tejado>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
OR OTHER DEALINGS IN THE SOFTWARE.

Author: tjado <https://github.com/tejado>
"""

import os
import re
import sys
import json
import time
import pprint
import logging
import argparse
import getpass
from geopy.geocoders import GoogleV3

# add directory of this file to PATH, so that the package will be found
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# import Pokemon Go API lib
from pgoapi import PGoApi

pokemon_list = json.load(open('data/pokemon.json'))
pokemon_safe_list = json.load(open('data/keep.json'))
log = logging.getLogger(__name__)

def init_config():
    parser = argparse.ArgumentParser()
    config_file = "config.json"

    # If config file exists, load variables from json
    load   = {}
    if os.path.isfile(config_file):
        with open(config_file) as data:
            load.update(json.load(data))

    # Read passed in Arguments
    required = lambda x: not x in load
    parser.add_argument("-a", "--auth_service", help="Auth Service ('ptc' or 'google')", required=required("auth_service"))
    parser.add_argument("-u", "--username", help="Username", required=required("username"))
    parser.add_argument("-p", "--password", help="Password")
    parser.add_argument("-l", "--location", help="Location", required=required("location"))
    parser.add_argument("-d", "--debug", help="Debug Mode", action='store_true')
    parser.add_argument("-t", "--test", help="Only parse the specified location", action='store_true')
    parser.add_argument("-s", "--show", help="Only show dry run result. Not deleting actually", action='store_true')
    parser.set_defaults(DEBUG=False, TEST=False, SHOW=False)
    config = parser.parse_args()


    # Passed in arguments shoud trump
    for key in config.__dict__:
        if key in load and config.__dict__[key] == None:
            config.__dict__[key] = str(load[key])

    if config.__dict__["password"] is None:
        log.info("Secure Password Input (if there is no password prompt, use --password <pw>):")
        config.__dict__["password"] = getpass.getpass()

    if config.auth_service not in ['ptc', 'google']:
      log.error("Invalid Auth service specified! ('ptc' or 'google')")
      return None

    return config

def transfer_mon(api, response_dict, config):
    try:
        reduce(dict.__getitem__, ["responses", "GET_INVENTORY", "inventory_delta", "inventory_items"], response_dict)
    except KeyError:
            pass
    else:
        for item in response_dict['responses']['GET_INVENTORY']['inventory_delta']['inventory_items']:
            try:
                reduce(dict.__getitem__, ["inventory_item_data", "pokemon_data"], item)
            except KeyError:
                pass
            else:
                pokemon = item['inventory_item_data']['pokemon_data']
                if pokemon.get('is_egg', False):
                    continue

                iv_stats = ['individual_attack', 'individual_defense', 'individual_stamina']
                ind_low = False
                pid = pokemon['pokemon_id'] -1
                total_IV = 0
                for individual_stat in iv_stats:
                    try:
                        total_IV += pokemon[individual_stat]
                        if pokemon[individual_stat] < 5:
                            ind_low = True
                    except:
                        pokemon[individual_stat] = 0
                        continue

                pokemon_potential = round((total_IV / 45.0), 2)
                pokemon_name = pokemon_list[int(pid)]['Name']
                att = pokemon['individual_attack']
                defe = pokemon['individual_defense']
                stm = pokemon['individual_stamina']
                cp = pokemon['cp']
		favorite = pokemon.get('favorite', False)
                release = False
                if ind_low or (pokemon_potential < 0.8) or pokemon_name in pokemon_safe_list['always_transfer']:
                    release = True

                if pokemon_name in pokemon_safe_list['always_keep'] or favorite:
                    log.info("{} is in safe list!".format(pokemon_name))
                    release = False

                if release:
                    log.info("*** Releasing {} ({}/{}/{} CP: {} IV: {}) ***".format(pokemon_name, att, defe, stm, cp, pokemon_potential))
                    if not config.show:
                        do_transfer(api, pokemon)
                else:
                    log.info("Keeping {} ({}/{}/{} CP: {} IV: {})".format(pokemon_name, att, defe, stm, cp, pokemon_potential))

def do_transfer(api, mon):
    api.release_pokemon(pokemon_id=mon['id'])
    api.call()
    time.sleep(1)

def info_player(response_dict):
    try:
        reduce(dict.__getitem__, ["responses", "GET_INVENTORY", "inventory_delta", "inventory_items"], response_dict)
    except KeyError:
            pass
    else:
        for item in response_dict['responses']['GET_INVENTORY']['inventory_delta']['inventory_items']:
            try:
                reduce(dict.__getitem__, ["inventory_item_data", "player_stats"], item)
            except KeyError:
                pass
            else:
                player = item['inventory_item_data']['player_stats']
                log.info("Lv: {} Exp: {}/{}".format(
                    player['level'],
                    player['experience'],
                    player['next_level_xp'],
                ))


def info_resp(response_dict):
    info_player(response_dict)
    info_mon(response_dict)

def info_mon(response_dict):
    nEggs = 0
    nMon = 0
    try:
        reduce(dict.__getitem__, ["responses", "GET_INVENTORY", "inventory_delta", "inventory_items"], response_dict)
    except KeyError:
            pass
    else:
        for item in response_dict['responses']['GET_INVENTORY']['inventory_delta']['inventory_items']:
            try:
                reduce(dict.__getitem__, ["inventory_item_data", "pokemon_data"], item)
            except KeyError:
                pass
            else:
                pokemon = item['inventory_item_data']['pokemon_data']
                if pokemon.get('is_egg', False):
                    nEggs += 1
                    continue

                nMon += 1

    log.info("Eggs: {}, Mon: {}".format(nEggs, nMon))

def get_pos_by_name(location_name):
    # Check if the given location is already a coordinate.
    if ',' in location_name:
        possibleCoordinates = re.findall("[-]?\d{1,3}[.]\d{6,7}", location_name)
        if len(possibleCoordinates) == 2:
            # 2 matches, this must be a coordinate. We'll bypass the Google geocode so we keep the exact location.
            log.info(
                '[x] Coordinates found in passed in location, not geocoding.')
            return (float(possibleCoordinates[0]), float(possibleCoordinates[1]), float("0.0"))

    geolocator = GoogleV3()
    loc = geolocator.geocode(location_name, timeout=10)

    log.info('Your given location: %s', loc.address.encode('utf-8'))
    log.info('lat/long/alt: %s %s %s', loc.latitude, loc.longitude, loc.altitude)

    return (loc.latitude, loc.longitude, loc.altitude)

def main():
    # log settings
    # log format
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format='%(asctime)s [%(module)10s] [%(levelname)5s] %(message)s')
    # log level for http request class
    logging.getLogger("requests").setLevel(logging.WARNING)
    # log level for main pgoapi class
    logging.getLogger("pgoapi").setLevel(logging.INFO)
    # log level for internal pgoapi class
    logging.getLogger("rpc_api").setLevel(logging.INFO)

    config = init_config()
    if not config:
        return

    if config.debug:
        logging.getLogger("requests").setLevel(logging.DEBUG)
        logging.getLogger("pgoapi").setLevel(logging.DEBUG)
        logging.getLogger("rpc_api").setLevel(logging.DEBUG)

    position = get_pos_by_name(config.location)
    if not position:
        log.error('Your given location could not be found by name')
        return

    if config.test:
        return

    # instantiate pgoapi
    api = PGoApi()

    # provide player position on the earth
    api.set_position(*position)

    if not api.login(config.auth_service, config.username, config.password):
        return

    # chain subrequests (methods) into one RPC call

    # get player profile call
    # ----------------------
    api.get_player()

    # get inventory call
    # ----------------------
    api.get_inventory()

    # execute the RPC call
    log.info("Before cleanup:")
    response_dict = api.call()
    info_resp(response_dict)
    transfer_mon(api, response_dict, config)

    log.info("After cleanup:")
    api.get_inventory()
    response_dict = api.call()
    info_resp(response_dict)


    # get map objects call
    # repeated fields (e.g. cell_id and since_timestamp_ms in get_map_objects) can be provided over a list
    # ----------------------
    #cell_ids = util.get_cell_ids(position[0], position[1])
    #timestamps = [0,] * len(cell_ids)
    #api.get_map_objects(latitude = position[0], longitude = position[1], since_timestamp_ms = timestamps, cell_id = cell_ids)

    # spin a fort
    # ----------------------
    #fortid = '<your fortid>'
    #lng = <your longitude>
    #lat = <your latitude>
    #api.fort_search(fort_id=fortid, fort_latitude=lat, fort_longitude=lng, player_latitude=f2i(position[0]), player_longitude=f2i(position[1]))

    # release/transfer a pokemon and get candy for it
    # ----------------------
    #api.release_pokemon(pokemon_id = <your pokemonid>)

    # evolve a pokemon if you have enough candies
    # ----------------------
    #api.evolve_pokemon(pokemon_id = <your pokemonid>)

    # get download settings call
    # ----------------------
    #api.download_settings(hash="05daf51635c82611d1aac95c0b051d3ec088a930")

    # print the response dict
    # print('Response dictionary: \n\r{}'.format(pprint.PrettyPrinter(indent=4).pformat(response_dict)))

    # or dumps it as a JSON
    #print('Response dictionary: \n\r{}'.format(json.dumps(response_dict, indent=2, cls=util.JSONByteEncoder)))

    # alternative:
    # api.get_player().get_inventory().get_map_objects().download_settings(hash="05daf51635c82611d1aac95c0b051d3ec088a930").call()

if __name__ == '__main__':
    main()

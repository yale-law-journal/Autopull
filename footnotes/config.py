import json
from os.path import dirname, join

with open(join(dirname(__file__), 'config.json')) as config_f:
    CONFIG = json.load(config_f)['perma']

import json
from os.path import dirname, join

try:
    with open(join(dirname(__file__), 'config_development.json')) as config_f:
        CONFIG = json.load(config_f)
except FileNotFoundError:
    with open(join(dirname(__file__), 'config.json')) as config_f:
        CONFIG = json.load(config_f)

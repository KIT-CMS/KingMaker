import configparser
from sys import argv
import os

config = configparser.ConfigParser()

# Get target path from provided argument
try:
    cfg_path = argv[1]
except IndexError:
    print(
        "Please provided a luigi config file to search for the necessary environments."
    )
    print("Example: 'python ParseRFSPath.py <config_file>'")
    exit(1)

# Check if file exists at that location
if not os.path.isfile(cfg_path):
    print("There was no file found at {}".format(cfg_path))
    exit(1)

# Try to parse config file
try:
    config.read(cfg_path)
except (configparser.ParsingError, configparser.MissingSectionHeaderError) as error:
    print(error)
    print("@File at {} could not be parsed. Is it a valid luigi config file?".format(cfg_path))
    exit(1)

# Try to get remote file system path from 'wlcg_path' of 'DEFAULT' section
try:
    wlcg_path = config["DEFAULT"]["wlcg_path"].strip()
except KeyError as error:
    print(
        "Config file at {} does not provide an 'ENV_NAME' in it's 'DEFAULT' section.".format(
            cfg_path
        ),
        "Without this, the starting env cannot be set.",
    )
    exit(1)
print(wlcg_path)

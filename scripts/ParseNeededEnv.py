import configparser
from sys import argv
import os
import sys

config = configparser.ConfigParser()

# Get target path from provided argument
try:
    cfg_path = argv[1]
except IndexError:
    print(
        "Please provided a luigi config file to search for the necessary environments."
    )
    print("Example: 'python ParseNeededEnv.py <config_file>'")
    sys.exit(1)

# Check if file exists at that location
if not os.path.isfile(cfg_path):
    print(f"There was no file found at {cfg_path}")
    sys.exit(1)

# Try to parse config file
try:
    config.read(cfg_path)
except (configparser.ParsingError, configparser.MissingSectionHeaderError) as error:
    print(
        f"{error}@File at {cfg_path} could not be parsed. Is it a valid luigi config file?"
    )
    sys.exit(1)

# Try to get starting env from 'ENV_NAME' of 'DEFAULT' section
try:
    base_env = config["DEFAULT"]["ENV_NAME"].strip()
except KeyError as error:
    print(
        f"Config file at {cfg_path} does not provide an 'ENV_NAME' in it's 'DEFAULT' section.",
        "Without this, the starting env cannot be set.",
    )
    sys.exit(1)

all_envs = [base_env]
# Add all other envs mentioned in the 'ENV_NAME' of the sections to the list
for section in config.sections():
    all_envs.append(config[section]["ENV_NAME"].strip())
# Keep only one entry for each of the envs
all_envs = list(set(all_envs))
# Push the starting env to the front of the list
all_envs.insert(0, all_envs.pop(all_envs.index(base_env)))
# Return a newline seperated list of all necessary envs
for env in all_envs:
    print(env)

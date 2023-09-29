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
    print("Example: 'python ParseNeededEnv.py <config_file>'")
    exit(1)

# Check if file exists at that location
if not os.path.isfile(cfg_path):
    print("There was no file found at {}".format(cfg_path))
    exit(1)

# Try to parse config file
try:
    config.read(cfg_path)
except (configparser.ParsingError, configparser.MissingSectionHeaderError) as error:
    print(
        "{}@File at {} could not be parsed. Is it a valid luigi config file?".format(
            error, cfg_path
        )
    )
    exit(1)

# Try to get starting env from 'ENV_NAME' of 'DEFAULT' section
try:
    base_env = config["DEFAULT"]["ENV_NAME"].strip()
except KeyError as error:
    print(
        "Config file at {} does not provide an 'ENV_NAME' in it's 'DEFAULT' section.".format(
            cfg_path
        ),
        "Without this, the starting env cannot be set.",
    )
    exit(1)

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

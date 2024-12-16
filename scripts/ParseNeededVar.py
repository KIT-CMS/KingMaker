import configparser
from sys import argv
import os
import sys

config = configparser.ConfigParser()

# Get target path from provided argument
try:
    cfg_path = argv[1]
    var_name = argv[2]
except IndexError:
    print(
        "Please provided a luigi config file to search for the necessary variable and the variable name."
    )
    print("Example: 'python ParseNeededEnv.py <config_file> <var_name>'")
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

# Try to get variable from 'DEFAULT' section
try:
    base_var = config["DEFAULT"][var_name].strip()
except KeyError as error:
    print(
        f"Config file at {cfg_path} does not provide a {var_name} in its 'DEFAULT' section.",
        "Without this, the variable cannot be determined.",
    )
    sys.exit(1)

all_var = [base_var]
# Add all other values set throughout the other sections to the list
for section in config.sections():
    all_var.append(config[section][var_name].strip())
# Keep only one entry for each of the values
all_var = list(set(all_var))
# Push the starting value to the front of the list
all_var.insert(0, all_var.pop(all_var.index(base_var)))
# Return a newline seperated list of all variable values
# As of now, only the values in the 'DEFAULT' section are used in the setup
for var in all_var:
    print(var)

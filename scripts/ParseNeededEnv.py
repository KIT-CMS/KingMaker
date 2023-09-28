import configparser
from sys import argv
import os

#print(sys.argv)

cfg_path = argv[1]
if not os.path.isfile(cfg_path):
    print('File was not found at {}'.format(cfg_path))
    exit(1)
config = configparser.ConfigParser()

try:
    config.read(cfg_path)
    base_env = config["DEFAULT"]["ENV_NAME"]
except (KeyError, configparser.ParsingError) as error:
    print('File at {} is not a valid config file.@{}'.format(cfg_path, error))
    exit(1)

all_env = [base_env]
for section in config.sections():
    all_env.append(config[section]["ENV_NAME"])
all_env = list(set(all_env))
print(base_env)
for i in all_env:
    print(i)

import luigi
import os
import json
import yaml
from framework import Task
from framework import console


def ensure_dir(file_path):
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)


class ConfigureDatasets(Task):
    """
    Gather information on the selected datasets, for now just mentioning an explicit dataset
    """

    nick = luigi.Parameter()
    era = luigi.Parameter()
    sample_type = luigi.Parameter()
    production_tag = luigi.Parameter()
    silent = luigi.BoolParameter(default=False)

    def output(self):
        target = self.remote_target("sample_database/{}.json".format(self.nick))
        return target

    def load_filelist_config(self):
        # first check if a json exists, if not, check for a yaml
        sample_configfile_json = "sample_database/{era}/{type}/{nick}.json".format(
            era=self.era, type=self.sample_type, nick=self.nick
        )
        sample_configfile_yaml = "sample_database/{era}/{type}/{nick}.yaml".format(
            era=self.era, type=self.sample_type, nick=self.nick
        )
        if os.path.exists(sample_configfile_json):
            with open(sample_configfile_json, "r") as stream:
                try:
                    sample_data = json.load(stream)
                except json.JSONDecodeError as exc:
                    print(exc)
                    raise Exception("Failed to load sample information")
        elif os.path.exists(sample_configfile_yaml):
            console.log("[DEPRECATED] Loading from YAML")
            with open(sample_configfile_yaml, "r") as stream:
                try:
                    sample_data = yaml.safe_load(stream)
                except yaml.YAMLError as exc:
                    print(exc)
                    raise Exception("Failed to load sample information")
        else:
            console.log("[DEPRECATED] Loading from DAS is not supported anymore")
            raise Exception("Failed to load sample information")
        return sample_data

    def run(self):
        output = self.output()
        output.parent.touch()
        if not output.exists():
            output.parent.touch()
            sample_data = self.load_filelist_config()
            if not self.silent:
                console.log("Sample: {}".format(self.nick))
                console.log("Era: {}".format(sample_data["era"]))
                console.log("Type: {}".format(sample_data["sample_type"]))
                console.log("Total Files: {}".format(sample_data["nfiles"]))
                console.log("Total Events: {}".format(sample_data["nevents"]))
                console.rule()
            output.dump(sample_data)

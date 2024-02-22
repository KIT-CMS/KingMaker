import luigi
import law
import os
from framework import Task
import json
from CROWNRun import CROWNRun


class QuantitiesMap(law.LocalWorkflow, Task):
    scopes = luigi.ListParameter()
    all_sample_types = luigi.ListParameter(significant=False)
    all_eras = luigi.ListParameter(significant=False)
    era = luigi.Parameter()
    sample_type = luigi.Parameter()
    production_tag = luigi.Parameter()
    analysis = luigi.Parameter(significant=False)
    config = luigi.Parameter(significant=False)
    nick = luigi.Parameter(significant=False)

    def workflow_requires(self):
        requirements = {}
        requirements["ntuples"] = CROWNRun(
            nick=self.nick,
            analysis=self.analysis,
            config=self.config,
            production_tag=self.production_tag,
            all_eras=self.all_eras,
            all_sample_types=self.all_sample_types,
            era=self.era,
            sample_type=self.sample_type,
            scopes=self.scopes,
        )
        return requirements

    def requires(self):
        requirements = {}
        requirements["ntuples"] = CROWNRun(
            nick=self.nick,
            analysis=self.analysis,
            config=self.config,
            production_tag=self.production_tag,
            all_eras=self.all_eras,
            all_sample_types=self.all_sample_types,
            era=self.era,
            sample_type=self.sample_type,
            scopes=self.scopes,
        )
        return requirements

    def create_branch_map(self):
        return {
            0: {
                "era": self.era,
                "sample_type": self.sample_type,
            }
        }

    def output(self):
        target = self.remote_target(
            "{}/{}_{}_quantities_map.json".format(
                self.production_tag, self.era, self.sample_type
            )
        )
        target.parent.touch()
        return target

    def run(self):
        output = self.output()
        era = self.era
        sample_type = self.sample_type
        _workdir = os.path.abspath(f"quantities_map/{self.production_tag}")
        if not os.path.exists(_workdir):
            os.makedirs(_workdir)
        quantities_map = {}
        quantities_map[era] = {}
        quantities_map[era][sample_type] = {}
        # go through all input files and get all quantities maps
        inputs = self.input()["ntuples"]
        for sample in inputs:
            if isinstance(
                self.input()["ntuples"][sample], law.NestedSiblingFileCollection
            ):
                inputfiles = self.input()["ntuples"][sample]._flat_target_list
                for inputfile in inputfiles:
                    if inputfile.path.endswith("quantities_map.json"):
                        with inputfile.localize("r") as _file:
                            # open file and update quantities map
                            update = json.load(open(_file.path, "r"))
                            scope = list(update[era][sample_type].keys())[0]
                            quantities_map[era][sample_type][scope] = update[era][
                                sample_type
                            ][scope]
        # write the quantities map to a file
        local_filename = os.path.join(
            _workdir, "{}_{}_quantities_map.json".format(era, sample_type)
        )

        with open(local_filename, "w") as f:
            json.dump(quantities_map, f, indent=4)
        output.copy_from_local(local_filename)

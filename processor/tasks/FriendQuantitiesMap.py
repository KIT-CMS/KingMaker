import luigi
import law
import os
from framework import Task, console
from CROWNRun import CROWNRun
from CROWNFriends import CROWNFriends
import json


class FriendQuantitiesMap(law.LocalWorkflow, Task):
    scopes = luigi.ListParameter()
    all_sampletypes = luigi.ListParameter(significant=False)
    all_eras = luigi.ListParameter(significant=False)
    era = luigi.Parameter()
    sampletype = luigi.Parameter()
    production_tag = luigi.Parameter()
    analysis = luigi.Parameter(significant=False)
    config = luigi.Parameter(significant=False)
    nick = luigi.Parameter(significant=False)
    friend_dependencies = luigi.ListParameter(significant=False)
    friend_mapping = luigi.DictParameter(significant=False, default={})

    def workflow_requires(self):
        requirements = {}
        requirements["ntuples"] = CROWNRun(
            nick=self.nick,
            analysis=self.analysis,
            config=self.config,
            production_tag=self.production_tag,
            all_eras=self.all_eras,
            all_sampletypes=self.all_sampletypes,
            era=self.era,
            sampletype=self.sampletype,
            scopes=self.scopes,
        )
        for friend in self.friend_dependencies:
            requirements[
                f"CROWNFriends_{self.nick}_{self.friend_mapping[friend]}"
            ] = CROWNFriends(
                nick=self.nick,
                analysis=self.analysis,
                config=self.config,
                production_tag=self.production_tag,
                all_eras=self.all_eras,
                all_sampletypes=self.all_sampletypes,
                era=self.era,
                sampletype=self.sampletype,
                scopes=self.scopes,
                friend_name=self.friend_mapping[friend],
                friend_config=friend,
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
            all_sampletypes=self.all_sampletypes,
            era=self.era,
            sampletype=self.sampletype,
            scopes=self.scopes,
        )
        for friend in self.friend_dependencies:
            requirements[f"CROWNFriends_{friend}"] = CROWNFriends(
                nick=self.nick,
                analysis=self.analysis,
                config=self.config,
                production_tag=self.production_tag,
                all_eras=self.all_eras,
                all_sampletypes=self.all_sampletypes,
                era=self.era,
                sampletype=self.sampletype,
                scopes=self.scopes,
                friend_name=friend,
                friend_config=friend,
            )
        return requirements

    def create_branch_map(self):
        return {
            0: {
                "era": self.era,
                "sampletype": self.sampletype,
            }
        }

    def output(self):
        target = self.remote_target(
            "{}/{}_{}_quantities_map.json".format(
                self.production_tag, self.era, self.sampletype
            )
        )
        target.parent.touch()
        return target

    def run(self):
        output = self.output()
        era = self.era
        sampletype = self.sampletype
        _workdir = os.path.abspath(f"quantities_map/{self.production_tag}")
        if not os.path.exists(_workdir):
            os.makedirs(_workdir)
        quantities_map = {}
        quantities_map[era] = {}
        quantities_map[era][sampletype] = {}
        # go through all input files and get all quantities maps
        samples = self.input()["ntuples"]
        for sample in samples:
            if isinstance(
                self.input()["ntuples"][sample], law.NestedSiblingFileCollection
            ):
                inputfiles = self.input()["ntuples"][sample]._flat_target_list
                # add all friend files to the inputfiles list
                for friend in self.friend_dependencies:
                    inputfiles.extend(
                        self.input()[f"CROWNFriends_{friend}"][sample]._flat_target_list
                    )
                for inputfile in inputfiles:
                    if inputfile.path.endswith("quantities_map.json"):
                        with inputfile.localize("r") as _file:
                            # open file and update quantities map
                            update = json.load(open(_file.path, "r"))
                            scope = list(update[era][sampletype].keys())[0]
                            if scope not in quantities_map[era][sampletype].keys():
                                quantities_map[era][sampletype][scope] = {}
                            for shift in update[era][sampletype][scope].keys():
                                if (
                                    shift
                                    not in quantities_map[era][sampletype][scope].keys()
                                ):
                                    quantities_map[era][sampletype][scope][shift] = []
                                quantities_map[era][sampletype][scope][shift].extend(
                                    update[era][sampletype][scope][shift]
                                )
        # write the quantities map to a file
        local_filename = os.path.join(
            _workdir, "{}_{}_quantities_map.json".format(era, sampletype)
        )

        with open(local_filename, "w") as f:
            json.dump(quantities_map, f, indent=4)
        output.copy_from_local(local_filename)

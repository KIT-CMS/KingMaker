import luigi
import yaml
import law
from CROWNFriends import CROWNFriends
from framework import console
from law.task.base import WrapperTask
from rich.table import Table
import ast


class ProduceFriends(WrapperTask):
    """
    collective task to trigger friend production for a list of samples,
    if the samples are not already present, trigger ntuple production first
    """

    sample_list = luigi.Parameter()
    analysis = luigi.Parameter()
    friend_config = luigi.Parameter()
    friend_name = luigi.Parameter()
    config = luigi.Parameter()
    dataset_database = luigi.Parameter()
    production_tag = luigi.Parameter()
    shifts = luigi.Parameter()
    scopes = luigi.Parameter()

    def requires(self):
        # load the list of samples to be processed
        data = {}
        data["sampletypes"] = set()
        data["eras"] = set()
        data["details"] = {}
        samples = []
        # check if sample list is a file or a comma separated list
        if self.sample_list.endswith(".txt"):
            with open(self.sample_list) as file:
                samples = [nick.replace("\n", "") for nick in file.readlines()]
        elif "," in self.sample_list:
            samples = self.sample_list.split(",")
        else:
            samples = [self.sample_list]
        console.rule("")
        console.log(f"Production tag: {self.production_tag}")
        console.log(f"Analysis: {self.analysis}")
        console.log(f"Friend Config: {self.friend_config}")
        console.rule("")
        table = Table(title="Samples to be processed")

        table.add_column("Samplenick", justify="left")
        table.add_column("Era", justify="left")
        table.add_column("Sampletype", justify="left")

        # sanitize the scopes information
        try:
            self.scopes = ast.literal_eval(self.scopes)
        except:
            self.scopes = self.scopes
        if isinstance(self.scopes, str):
            self.scopes = self.scopes.split(",")
        elif isinstance(self.scopes, list):
            self.scopes = self.scopes

        for i, nick in enumerate(samples):
            data["details"][nick] = {}
            # check if sample exists in datasets.yaml
            with open(self.dataset_database, "r") as stream:
                sample_db = yaml.safe_load(stream)
            if nick not in sample_db:
                console.log(
                    "Sample {} not found in {}".format(nick, self.dataset_database)
                )
                raise Exception("Sample not found in DB")
            sample_data = sample_db[nick]
            data["details"][nick]["era"] = str(sample_data["era"])
            data["details"][nick]["sampletype"] = sample_data["sample_type"]
            # all samplestypes and eras are added to a list,
            # used to built the CROWN executable
            data["eras"].add(data["details"][nick]["era"])
            data["sampletypes"].add(data["details"][nick]["sampletype"])
            table.add_row(
                nick, data["details"][nick]["era"], data["details"][nick]["sampletype"]
            )
        console.log(table)

        console.log(
            f"Producing friends for {len(data['details'])} samples in {len(data['eras'])} eras and {len(self.scopes)} scopes: {self.scopes}"
        )
        console.rule("")
        requirements = {}
        for samplenick in data["details"]:
            requirements[f"CROWNFriends_{samplenick}"] = CROWNFriends(
                nick=samplenick,
                analysis=self.analysis,
                config=self.config,
                production_tag=self.production_tag,
                all_eras=data["eras"],
                all_sampletypes=data["sampletypes"],
                scopes=self.scopes,
                era=data["details"][samplenick]["era"],
                sampletype=data["details"][samplenick]["sampletype"],
                friend_config=self.friend_config,
                friend_name=self.friend_name,
            )

        return requirements

    def run(self):
        pass

import luigi
from CROWNFriends import CROWNFriends
from CROWNMultiFriends import CROWNMultiFriends
from framework import console
from CROWNBase import ProduceBase


class ProduceFriends(ProduceBase):
    """
    collective task to trigger friend production for a list of samples,
    if the samples are not already present, trigger ntuple production first
    """

    friend_config = luigi.Parameter()
    friend_name = luigi.Parameter()
    friend_dependencies = luigi.Parameter(significant=False)

    def requires(self):
        self.sanitize_scopes()
        self.sanitize_shifts()
        if self.friend_dependencies:
            self.sanitize_friend_dependencies()

        console.rule("")
        console.log(f"Production tag: {self.production_tag}")
        console.log(f"Analysis: {self.analysis}")
        console.log(f"Friend Config: {self.friend_config}")
        console.log(f"Config: {self.config}")
        console.log(f"Shifts: {self.shifts}")
        console.log(f"Scopes: {self.scopes}")
        if self.friend_dependencies:
            console.log(f"Friend Dependencies: {self.friend_dependencies}")
        console.rule("")

        data = self.set_sample_data(self.parse_samplelist(self.sample_list))

        console.rule("")

        requirements = {}
        for samplenick in data["details"]:
            if self.friend_dependencies:
                requirements[
                    f"CROWNFriends_{samplenick}_{self.friend_name}"
                ] = CROWNMultiFriends(
                    nick=samplenick,
                    analysis=self.analysis,
                    config=self.config,
                    production_tag=self.production_tag,
                    all_eras=data["eras"],
                    shifts=self.shifts,
                    all_sampletypes=data["sampletypes"],
                    scopes=self.scopes,
                    era=data["details"][samplenick]["era"],
                    sampletype=data["details"][samplenick]["sampletype"],
                    friend_config=self.friend_config,
                    friend_name=self.friend_name,
                    friend_dependencies=self.friend_dependencies,
                )
            else:
                requirements[
                    f"CROWNFriends_{samplenick}_{self.friend_name}"
                ] = CROWNFriends(
                    nick=samplenick,
                    analysis=self.analysis,
                    config=self.config,
                    production_tag=self.production_tag,
                    all_eras=data["eras"],
                    shifts=self.shifts,
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

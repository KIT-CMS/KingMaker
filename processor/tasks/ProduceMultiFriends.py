import luigi
from CROWNFriends import CROWNFriends
from CROWNMultiFriends import CROWNMultiFriends
from framework import console
from CROWNBase import ProduceBase


class ProduceMultiFriends(ProduceBase):
    """
    collective task to trigger friend production for a list of samples,
    if the samples are not already present, trigger ntuple production first
    """

    friend_config = luigi.Parameter()
    friend_name = luigi.Parameter()
    friend_dependencies = luigi.Parameter()
    friend_mapping = luigi.DictParameter(significant=False, default={})

    def requires(self):
        self.sanitize_scopes()
        self.sanitize_shifts()
        self.sanitize_friend_dependencies()
        self.validate_friend_mapping()
        if not self.silent:
            console.rule("")
            console.log(f"Production tag: {self.production_tag}")
            console.log(f"Analysis: {self.analysis}")
            console.log(f"Friend Config: {self.friend_config}")
            console.log(f"Config: {self.config}")
            console.log(f"Shifts: {self.shifts}")
            console.log(f"Scopes: {self.scopes}")
            console.log(f"Friend Dependencies: {self.friend_dependencies}")
            console.log(f"Friend Mapping: {self.friend_mapping}")
            console.rule("")

        data = self.set_sample_data(self.parse_samplelist(self.sample_list))
        self.silent = True

        requirements = {}
        for samplenick in data["details"]:
            requirements[f"CROWNFriends_{samplenick}_{self.friend_name}"] = (
                CROWNMultiFriends.req(
                    self,
                    nick=samplenick,
                    all_eras=data["eras"],
                    all_sample_types=data["sample_types"],
                    era=data["details"][samplenick]["era"],
                    sample_type=data["details"][samplenick]["sample_type"],
                )
            )
        return requirements

    def run(self):
        pass

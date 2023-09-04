from CROWNRun import CROWNRun
from framework import console
from CROWNBase import ProduceBase


class ProduceSamples(ProduceBase):
    """
    collective task to trigger ntuple production for a list of samples
    """

    def requires(self):
        self.sanitize_scopes()
        self.sanitize_shifts()

        console.rule("")
        console.log(f"Production tag: {self.production_tag}")
        console.log(f"Analysis: {self.analysis}")
        console.log(f"Config: {self.config}")
        console.log(f"Shifts: {self.shifts}")
        console.log(f"Scopes: {self.scopes}")
        console.rule("")

        data = self.set_sample_data(self.parse_samplelist(self.sample_list))

        console.rule("")

        requirements = {}
        for samplenick in data["details"]:
            requirements[f"CROWNRun_{samplenick}"] = CROWNRun(
                nick=samplenick,
                analysis=self.analysis,
                config=self.config,
                scopes=self.scopes,
                shifts=self.shifts,
                production_tag=self.production_tag,
                all_eras=data["eras"],
                all_sampletypes=data["sampletypes"],
                era=data["details"][samplenick]["era"],
                sampletype=data["details"][samplenick]["sampletype"],
            )

        return requirements

    def run(self):
        pass

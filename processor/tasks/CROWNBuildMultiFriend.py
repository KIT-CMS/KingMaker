import luigi
import os
from framework import console
from FriendQuantitiesMap import FriendQuantitiesMap
from helpers.helpers import convert_to_comma_seperated
from BuildCROWNLib import BuildCROWNLib
from CROWNBase import CROWNBuildBase


class CROWNBuildMultiFriend(CROWNBuildBase):
    """
    Gather and compile CROWN for friend tree production with the given configuration
    """

    # additional configuration variables
    friend_config = luigi.Parameter()
    friend_name = luigi.Parameter()
    era = luigi.Parameter()
    sampletype = luigi.Parameter()
    nick = luigi.Parameter(significant=False)
    friend_dependencies = luigi.ListParameter(significant=False)

    def requires(self):
        results = {"quantities_map": FriendQuantitiesMap.req(self)}
        results["crownlib"] = BuildCROWNLib.req(self)
        return results

    def output(self):
        target = self.remote_target(
            f"crown_friends_{self.analysis}_{self.friend_config}_{self.friend_name}_{self.sampletype}_{self.era}.tar.gz"
        )
        return target

    def run(self):
        crownlib = self.input()["crownlib"]
        # get output file path
        output = self.output()
        quantity_target = []
        # get quantities map
        for target in self.input()["quantities_map"]["collection"]._iter_flat():
            quantity_target = target
        if len(quantity_target) != 1:
            raise Exception(
                f"There should be only one quantities map file, but found {len(quantity_target)} \n Full map: {quantity_target}"
            )
        with quantity_target[0].localize("r") as _file:
            _quantities_map_file = _file.path
        # convert list to comma separated strings
        _sampletype = self.sampletype
        _era = self.era
        _shifts = convert_to_comma_seperated(self.shifts)
        _scopes = convert_to_comma_seperated(self.scopes)
        _analysis = str(self.analysis)
        _friend_config = str(self.friend_config)
        _friend_name = str(self.friend_name)
        # also use the tag for the local tarball creation
        _tag = f"{self.production_tag}/CROWNFriends_{_analysis}_{_friend_config}_{_friend_name}_{_sampletype}_{_era}"
        _install_dir = os.path.join(str(self.install_dir), _tag)
        _build_dir = os.path.join(str(self.build_dir), _tag)
        _crown_path = os.path.abspath("CROWN")
        _compile_script = os.path.join(
            str(os.path.abspath("processor")),
            "tasks",
            "scripts",
            "compile_crown_friends.sh",
        )

        if os.path.exists(output.path):
            console.log(f"tarball already existing in {output.path}")

        elif os.path.exists(os.path.join(_install_dir, output.basename)):
            console.log(f"tarball already existing in tarball directory {_install_dir}")
            console.log(f"Copying to remote: {output.path}")
            output.copy_from_local(os.path.join(_install_dir, output.basename))
        else:
            console.rule(f"Building new CROWN Friend tarball for {self.friend_name}")
            _build_dir, _install_dir = self.setup_build_environment(
                _build_dir, _install_dir, crownlib
            )
            # actual payload:
            console.rule(f"Starting cmake step for CROWN Friends {self.friend_name}")
            console.log(f"Using CROWN {_crown_path}")
            console.log(f"Using build_directory {_build_dir}")
            console.log(f"Using install directory {_install_dir}")
            console.log("Settings used: ")
            console.log(f"Analysis: {_analysis}")
            console.log(f"Friend Config: {_friend_config}")
            console.log(f"Friend Names: {_friend_name}")
            console.log(f"Sampletype: {_sampletype}")
            console.log(f"Era: {_era}")
            console.log(f"Scopes: {_scopes}")
            console.log(f"Shifts: {_shifts}")
            console.log(f"Quantities map: {_quantities_map_file}")
            console.rule("")

            # run crown compilation script
            command = [
                "bash",
                _compile_script,
                _crown_path,  # CROWNFOLDER=$1
                _analysis,  # ANALYSIS=$2
                _friend_config,  # CONFIG=$3
                _sampletype,  # SAMPLES=$4
                _era,  # ERAS=$5
                _scopes,  # SCOPES=$6
                _shifts,  # SHIFTS=$7
                _install_dir,  # INSTALLDIR=$8
                _build_dir,  # BUILDDIR=$9
                output.basename,  # TARBALLNAME=$10
                _quantities_map_file,  # QUANTITIESMAP=$11
            ]
            self.run_command_readable(command)
            self.upload_tarball(output, os.path.join(_install_dir, output.basename), 10)
        console.rule("Finished CROWNBuildFriend")

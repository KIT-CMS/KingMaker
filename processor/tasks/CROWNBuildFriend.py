import luigi
import law
import os
import subprocess
import shutil
from law.util import interruptable_popen
from framework import Task
from framework import console
from QuantitiesMap import QuantitiesMap
from helpers.helpers import convert_to_comma_seperated
from CROWNBase import CROWNBuildBase
from BuildCROWNLib import BuildCROWNLib


class CROWNBuildFriend(CROWNBuildBase):
    """
    Gather and compile CROWN for friend tree production with the given configuration
    """

    # additional configuration variables
    friend_config = luigi.Parameter()
    friend_name = luigi.Parameter()
    era = luigi.Parameter()
    sampletype = luigi.Parameter()
    nick = luigi.Parameter(significant=False)

    def requires(self):
        results = {"quantities_map": QuantitiesMap.req(self)}
        results["crownlib"] = BuildCROWNLib.req(self)
        return results

    def output(self):
        target = self.remote_target(
            "crown_friends_{}_{}_{}_{}_{}.tar.gz".format(
                self.analysis,
                self.friend_config,
                self.friend_name,
                self.sampletype,
                self.era,
            )
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
                "There should be only one quantities map file, but found {} \n Full map: {}".format(
                    len(quantity_target), quantity_target
                )
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
        _tag = "{}/CROWNFriends_{}_{}_{}_{}_{}".format(
            self.production_tag,
            _analysis,
            _friend_config,
            _friend_name,
            _sampletype,
            _era,
        )
        _install_dir = os.path.join(str(self.install_dir), _tag)
        _build_dir = os.path.join(str(self.build_dir), _tag)
        _crown_path = os.path.abspath("CROWN")
        _compile_script = os.path.join(
            str(os.path.abspath("processor")), "tasks", "scripts", "compile_crown_friends.sh"
        )

        if os.path.exists(output.path):
            console.log("tarball already existing in {}".format(output.path))

        elif os.path.exists(os.path.join(_install_dir, output.basename)):
            console.log(
                "tarball already existing in tarball directory {}".format(_install_dir)
            )
            console.log("Copying to remote: {}".format(output.path))
            output.copy_from_local(os.path.join(_install_dir, output.basename))
        else:
            console.rule(f"Building new CROWN Friend tarball for {self.friend_name}")
            my_env, _build_dir, _install_dir = self.setup_build_environment(
                _build_dir, _install_dir, crownlib
            )
            # checking cmake path
            code, _cmake_executable, error = interruptable_popen(
                ["which", "cmake"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=my_env,
            )
            # actual payload:
            console.rule(
                "Starting cmake step for CROWN Friends {}".format(self.friend_name)
            )
            console.log("Using cmake {}".format(_cmake_executable.replace("\n", "")))
            console.log("Using CROWN {}".format(_crown_path))
            console.log("Using build_directory {}".format(_build_dir))
            console.log("Using install directory {}".format(_install_dir))
            console.log("Settings used: ")
            console.log("Analysis: {}".format(_analysis))
            console.log("Friend Config: {}".format(_friend_config))
            console.log("Friend Name: {}".format(_friend_name))
            console.log("Sampletype: {}".format(_sampletype))
            console.log("Era: {}".format(_era))
            console.log("Scopes: {}".format(_scopes))
            console.log("Shifts: {}".format(_shifts))
            console.log("Quantities map: {}".format(_quantities_map_file))
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

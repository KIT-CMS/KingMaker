import luigi
import os
import subprocess
from law.util import interruptable_popen
from framework import Task
from framework import console
from BuildCROWNLib import BuildCROWNLib
from CROWNBase import CROWNBuildBase



def convert_to_comma_seperated(list):
    if isinstance(list, str):
        return list
    elif len(list) == 1:
        return list[0]
    else:
        return ",".join(list)


class CROWNBuild(CROWNBuildBase):
    """
    Gather and compile CROWN with the given configuration
    """

    def requires(self):
        result = {"crownlib": BuildCROWNLib.req(self)}
        return result

    def output(self):
        target = self.remote_target(
            "crown_{}_{}.tar.gz".format(self.analysis, self.config)
        )
        return target

    def run(self):
        crownlib = self.input()["crownlib"]
        # get output file path
        output = self.output()
        # convert list to comma separated strings
        _all_sampletypes = convert_to_comma_seperated(self.all_sampletypes)
        _all_eras = convert_to_comma_seperated(self.all_eras)
        _shifts = convert_to_comma_seperated(self.shifts)
        _scopes = convert_to_comma_seperated(self.scopes)
        _analysis = str(self.analysis)
        _config = str(self.config)
        _threads = str(self.threads)
        # also use the tag for the local tarball creation
        _tag = "{}/CROWN_{}_{}".format(self.production_tag, _analysis, _config)
        _install_dir = os.path.join(str(self.install_dir), _tag)
        _build_dir = os.path.join(str(self.build_dir), _tag)
        _crown_path = os.path.abspath("CROWN")
        _compile_script = os.path.join(
            str(os.path.abspath("processor")), "tasks", "scripts", "compile_crown.sh"
        )
        if os.path.exists(os.path.join(_install_dir, output.basename)):
            console.log(
                "tarball already existing in tarball directory {}".format(_install_dir)
            )
            self.upload_tarball(
                output, os.path.join(os.path.abspath(_install_dir), output.basename), 10
            )
        else:
            console.rule("Building new CROWN tarball")
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
            console.rule("Starting cmake step for CROWN")
            console.log("Using cmake {}".format(_cmake_executable.replace("\n", "")))
            console.log("Using CROWN {}".format(_crown_path))
            console.log("Using build_directory {}".format(_build_dir))
            console.log("Using install directory {}".format(_install_dir))
            console.log("Settings used: ")
            console.log("Threads: {}".format(_threads))
            console.log("Analysis: {}".format(_analysis))
            console.log("Config: {}".format(_config))
            console.log("Sampletypes: {}".format(_all_sampletypes))
            console.log("Eras: {}".format(_all_eras))
            console.log("Scopes: {}".format(_scopes))
            console.log("Shifts: {}".format(_shifts))
            console.rule("")

            # run crown compilation script
            command = [
                "bash",
                _compile_script,
                _crown_path,  # CROWNFOLDER=$1
                _analysis,  # ANALYSIS=$2
                _config,  # CONFIG=$3
                _all_sampletypes,  # SAMPLES=$4
                _all_eras,  # all_eras=$5
                _scopes,  # SCOPES=$6
                _shifts,  # SHIFTS=$7
                _install_dir,  # INSTALLDIR=$8
                _build_dir,  # BUILDDIR=$9
                output.basename,  # TARBALLNAME=$10
                _threads,  # THREADS=$11
            ]
            self.run_command_readable(command)
            console.rule("Finished CROWNBuild")
            self.upload_tarball(output, os.path.join(_install_dir, output.basename), 10)



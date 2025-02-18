import os
import luigi
from framework import console
from BuildCROWNLib import BuildCROWNLib
from CROWNBase import CROWNBuildBase
from helpers.helpers import convert_to_comma_seperated
import tarfile


class CROWNBuildCombined(CROWNBuildBase):
    """
    Gather and compile CROWN with the given configuration
    """

    def requires(self):
        result = {"crownlib": BuildCROWNLib.req(self)}
        return result

    def output(self):
        # sort the sample types and eras to have a unique string for the tarball
        target = self.remote_target(
            f"crown_{self.analysis}_{self.config}_{self.get_tarball_hash()}.hash"
        )
        return target

    def run(self):
        crownlib = self.input()["crownlib"]
        # get output file path
        output = self.output()
        _analysis = str(self.analysis)
        _config = str(self.config)
        _threads = str(self.htcondor_request_cpus)
        # also use the tag for the local tarball creation
        _tag = f"{self.production_tag}/CROWN_{_analysis}_{_config}"
        _install_dir = os.path.join(str(self.install_dir), _tag)
        _build_dir = os.path.join(str(self.build_dir), _tag)
        _crown_path = os.path.abspath("CROWN")
        _compile_script = os.path.join(
            str(os.path.abspath("processor")), "tasks", "scripts", "compile_crown.sh"
        )
        if os.path.exists(os.path.join(_install_dir, output.basename)):
            console.log(f"tarball already existing in tarball directory {_install_dir}")
            self.upload_tarball(
                output, os.path.join(os.path.abspath(_install_dir), output.basename), 10
            )
            return
        # check if certain sample types and eras are already build, if so, skip
        available_executables = []
        _required_sample_types = set()
        _required_eras = set()
        if os.path.exists(os.path.join(_install_dir)):
            available_files = os.listdir(_install_dir)
            available_executables = [
                name.replace("config_", "")
                for name in available_files
                if name.startswith("config_")
            ]
        console.log(f"Available executables: {available_executables}")
        for sample_type in self.all_sample_types:
            for era in self.all_eras:
                if f"{sample_type}_{era}" not in available_executables:
                    _required_sample_types.add(sample_type)
                    _required_eras.add(era)
                else:
                    console.log(
                        f"Skipping {_analysis} {_config} {sample_type} {era} as it is already built"
                    )
        _required_eras = convert_to_comma_seperated(_required_eras)
        _required_sample_types = convert_to_comma_seperated(_required_sample_types)
        _shifts = convert_to_comma_seperated(self.shifts)
        _scopes = convert_to_comma_seperated(self.scopes)
        if len(_required_sample_types) == 0 or len(_required_eras) == 0:
            console.rule("All required CROWN build already exist")
        else:
            console.rule("Building new CROWN tarball")
            _build_dir, _install_dir = self.setup_build_environment(
                _build_dir, _install_dir, crownlib
            )

            # actual payload:
            console.rule("Starting cmake step for CROWN")
            console.log(f"Using CROWN {_crown_path}")
            console.log(f"Using build_directory {_build_dir}")
            console.log(f"Using install directory {_install_dir}")
            console.log("Settings used: ")
            console.log(f"Threads: {_threads}")
            console.log(f"Analysis: {_analysis}")
            console.log(f"Config: {_config}")
            console.log(f"Sampletypes: {_required_sample_types}")
            console.log(f"Eras: {_required_eras}")
            console.log(f"Scopes: {_scopes}")
            console.log(f"Shifts: {_shifts}")
            console.rule("")

            # run crown compilation script
            command = [
                "bash",
                _compile_script,
                _crown_path,  # CROWNFOLDER=$1
                _analysis,  # ANALYSIS=$2
                _config,  # CONFIG=$3
                _required_sample_types,  # SAMPLES=$4
                _required_eras,  # all_eras=$5
                _scopes,  # SCOPES=$6
                _shifts,  # SHIFTS=$7
                _install_dir,  # INSTALLDIR=$8
                _build_dir,  # BUILDDIR=$9
                output.basename,  # TARBALLNAME=$10
                _threads,  # THREADS=$11
            ]
            self.run_command_readable(command)
            console.rule("Finished CROWNBuild")
            # upload an small file to signal that the build is done
        with open(os.path.join(_install_dir, output.basename), "w") as f:
            f.write("CROWN build done")
        output.copy_from_local(os.path.join(_install_dir, output.basename))


class CROWNBuild(CROWNBuildBase):
    """
    Gather and compile CROWN with the given configuration
    """

    era = luigi.Parameter()
    sample_type = luigi.Parameter()

    def requires(self):
        result = {
            "combined_build": CROWNBuildCombined.req(
                self,
                htcondor_request_cpus=self.htcondor_request_cpus,
            )
        }
        return result

    def output(self):
        return self.remote_target(
            f"crown_{self.analysis}_{self.config}_{self.sample_type}_{self.era}.tar.gz"
        )

    def run(self):
        # get output file path
        output = self.output()
        _analysis = str(self.analysis)
        _config = str(self.config)
        _era = str(self.era)
        _sample_type = str(self.sample_type)
        # also use the tag for the local tarball creation
        _tag = (
            f"{self.production_tag}/CROWN_{_analysis}_{_config}_{_sample_type}_{_era}"
        )
        _install_dir = os.path.join(str(self.install_dir), _tag)
        _unpacked_dir = os.path.join(
            str(self.install_dir), f"{self.production_tag}/CROWN_{_analysis}_{_config}"
        )
        _tarball = os.path.join(_install_dir, output.basename)
        os.makedirs(os.path.dirname(_tarball), exist_ok=True)
        if not os.path.exists(_unpacked_dir):
            raise FileNotFoundError(
                f"No builds for {self.production_tag}/CROWN_{_analysis}_{_config} found"
            )

        # now pack the specific tarball, excluding unwanted executables
        def exclude_files(tarinfo):
            filename = os.path.basename(tarinfo.name)
            if filename.endswith(".tar.gz"):
                return None
            if filename.startswith(f"{_config}") and not filename.endswith(
                f"{_sample_type}_{_era}"
            ):
                return None
            else:
                return tarinfo

        console.log(f"Creating tarball for {_sample_type} {_era}")
        with tarfile.open(_tarball, "w:gz") as tar:
            tar.add(
                _unpacked_dir,
                arcname=".",
                filter=exclude_files,
            )
        # now upload the tarball
        self.upload_tarball(output, os.path.join(_install_dir, output.basename), 10)
        # delete the local tarball
        os.remove(_tarball)
        console.rule(
            f"Finished CROWNBuild for {_analysis} {_config} {_sample_type} {_era}"
        )

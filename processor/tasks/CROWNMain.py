import luigi
import os
import tarfile
import subprocess
import time
import json
import hashlib
from CROWNBase import CROWNBuildBase
from framework import console, Task
from helpers.helpers import create_abspath
from CROWNBase import CROWNExecuteBase
from helpers.helpers import get_alternate_file_uri
from helpers.helpers import convert_to_comma_seperated


class CROWNRun(CROWNExecuteBase):
    """
    Gather and compile CROWN with the given configuration
    """

    problematic_eras = luigi.ListParameter()

    def workflow_requires(self):
        requirements = {}
        requirements["dataset"] = {}
        for sample_type in self.all_sample_types:
            for era in self.all_eras:
                requirements[f"tarball_{sample_type}_{era}"] = CROWNBuild.req(
                    self,
                    era=era,
                    sample_type=sample_type,
                    htcondor_request_cpus=self.htcondor_request_cpus,
                )
        return requirements

    def create_branch_map(self):
        branch_map = {}
        branchcounter = 0
        dataset = ConfigureDatasets.req(self)
        # since we use the filelist from the dataset, we need to run it first
        if not dataset.complete():
            dataset.run()
        datsetinfo = dataset.output()
        with datsetinfo.localize("r") as _file:
            inputdata = _file.load()
        branches = {}
        if len(inputdata["filelist"]) == 0:
            raise Exception("No files found for dataset {}".format(self.nick))
        files_per_task = self.files_per_task
        custom_fpt = self.custom_files_per_task.get(self.sample_type)
        if custom_fpt is not None:
            files_per_task = int(custom_fpt)
        if self.sample_type == "data" and any(
            era in self.nick for era in self.problematic_eras
        ):
            files_per_task = 1
        for filecounter, filename in enumerate(inputdata["filelist"]):
            if (int(filecounter / files_per_task)) not in branches:
                branches[int(filecounter / files_per_task)] = []
            branches[int(filecounter / files_per_task)].append(filename)
        for x in branches:
            branch_map[branchcounter] = {}
            branch_map[branchcounter]["nick"] = self.nick
            branch_map[branchcounter]["era"] = self.era
            branch_map[branchcounter]["sample_type"] = self.sample_type
            branch_map[branchcounter]["files"] = branches[x]
            branchcounter += 1
        return branch_map

    def output(self):
        targets = []
        nicks = [
            "{era}/{nick}/{scope}/{nick}_{branch}.root".format(
                era=self.branch_data["era"],
                nick=self.branch_data["nick"],
                branch=self.branch,
                scope=scope,
            )
            for scope in self.scopes
        ]
        targets = self.remote_target(nicks)
        return targets

    def run(self):
        outputs = self.output()
        inputs = self.workflow_input()
        branch_data = self.branch_data
        _base_workdir = os.path.abspath("workdir")
        create_abspath(_base_workdir)
        _workdir = os.path.join(
            _base_workdir, f"{self.production_tag}_{self.analysis}_{self.config}"
        )
        create_abspath(_workdir)
        _inputfiles = branch_data["files"]
        _sample_type = branch_data["sample_type"]
        _era = branch_data["era"]
        
        # This call aims to get a "better" XRootD server to access the file.
        # If the file is available on GridKA, take it from there.
        # Otherwise, use the official European or global redirector.
        _inputfiles = [
            get_alternate_file_uri(
                filename,
                [
                    "root://cmsdcache-kit-disk.gridka.de",
                    "root://xrootd-cms.infn.it",
                    "root://cms-xrd-global.cern.ch",
                ],
            )
            for filename in _inputfiles
        ]
        # set the outputfilename to the first name in the output list, removing the scope suffix
        _outputfile = str(
            outputs[0].basename.replace("_{}.root".format(self.scopes[0]), ".root")
        )
        _abs_executable = "{}/{}_{}_{}".format(
            _workdir, self.config, _sample_type, _era
        )
        _tarball = inputs["tarball_{}_{}".format(_sample_type, _era)]
        console.log(f"Getting CROWN tarball from {_tarball.uri()}")
        with _tarball.localize("r") as _file:
            _tarballpath = _file.path
        # first unpack the tarball if the exec is not there yet
        _tempfile = os.path.join(
            _workdir,
            "unpacking_{}_{}_{}".format(self.config, _sample_type, _era),
        )
        while os.path.exists(_tempfile):
            time.sleep(1)
        if not os.path.exists(_abs_executable) and not os.path.exists(_tempfile):
            # create a temp file to signal that we are unpacking
            open(_tempfile, "a").close()
            tar = tarfile.open(_tarballpath, "r:gz")
            tar.extractall(_workdir)
            os.remove(_tempfile)
        _crown_args = [_outputfile] + _inputfiles
        _executable = "./{}_{}_{}".format(
            self.config, _sample_type, _era
        )
        # actual payload:
        console.rule("Starting CROWNRun")
        console.log("Executable: {}".format(_executable))
        console.log("inputfile {}".format(_inputfiles))
        console.log("outputfile {}".format(_outputfile))
        console.log("workdir {}".format(_workdir))  # run CROWN
        command = [_executable] + _crown_args
        console.log(f"Running command: {command}")
        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            cwd=_workdir,
        ) as p:
            for line in p.stdout:
                if line != "\n":
                    console.log(line.replace("\n", ""))
            for line in p.stderr:
                if line != "\n":
                    console.log("Error: {}".format(line.replace("\n", "")))
        if p.returncode != 0:
            console.log(
                "Error when running crown {}".format(
                    [_executable] + _crown_args,
                )
            )
            console.log("crown returned non-zero exit status {}".format(p.returncode))
            raise Exception("crown failed")
        else:
            console.log("Successful")
        console.log("Output files afterwards: {}".format(os.listdir(_workdir)))
        for i, outputfile in enumerate(outputs):
            local_filename = os.path.join(
                _workdir,
                _outputfile.replace(".root", "_{}.root".format(self.scopes[i])),
            )
            # if the output files were produced in multithreaded mode,
            # we have to open the files once again, setting the
            # kEntriesReshuffled bit to false, otherwise,
            # we cannot add any friends to the trees
            self.run_command(
                command=[
                    "python3",
                    "processor/tasks/helpers/ResetROOTStatusBit.py",
                    "--input {}".format(local_filename),
                ],
                silent=True,
            )
            # for each outputfile, add the scope suffix
            outputfile.copy_from_local(local_filename)
        console.rule("Finished CROWNRun")


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


class BuildCROWNLib(CROWNBuildBase):
    """
    Compile the CROWN shared libary to be used for all executables with the given configuration
    """

    # configuration variables
    build_dir = luigi.Parameter()
    install_dir = luigi.Parameter()
    # friend_name = luigi.Parameter(default="ntuples")
    analysis = luigi.Parameter()

    def get_source_hash(self):
        """
        Compute a hash of the CROWN source tree so that any code change produces
        a new task output, triggering a fresh compilation.
        """
        crown_path = os.path.abspath("CROWN")
        subdirs = ["src", "include", "analysis_configurations"]
        h = hashlib.sha256()
        for subdir in sorted(subdirs):
            dirpath = os.path.join(crown_path, subdir)
            if not os.path.exists(dirpath):
                continue
            for root, dirs, files in os.walk(dirpath):
                dirs.sort()
                for fname in sorted(files):
                    fpath = os.path.join(root, fname)
                    with open(fpath, "rb") as f:
                        h.update(f.read())
        cmake_path = os.path.join(crown_path, "CMakeLists.txt")
        if os.path.exists(cmake_path):
            with open(cmake_path, "rb") as f:
                h.update(f.read())
        return h.hexdigest()[:16]

    def output(self):
        target = self.local_target(f"libCROWNLIB_{self.get_source_hash()}.so")
        return target

    def run(self):
        # get output file path
        output = self.output()
        _source_hash = self.get_source_hash()
        # also use the tag for the local tarball creation
        _install_dir = os.path.abspath(
            os.path.join(
                str(self.install_dir),
                str(self.production_tag),
                f"crownlib_{_source_hash}",
            )
        )
        _build_dir = os.path.abspath(
            os.path.join(
                str(self.build_dir),
                str(self.production_tag),
                f"crownlib_{_source_hash}",
            )
        )
        _crown_path = os.path.abspath("CROWN")
        _compile_script = os.path.join(
            str(os.path.abspath("processor")),
            "tasks",
            "scripts",
            "compile_crown_lib.sh",
        )
        # cmake always produces libCROWNLIB.so regardless of our output name
        _local_libfile = os.path.join(_install_dir, "lib", "libCROWNLIB.so")
        _analysis = str(self.analysis)
        if os.path.exists(_local_libfile):
            console.log(f"lib already existing in tarball directory {_install_dir}")
            output.parent.touch()
            output.copy_from_local(_local_libfile)
        else:
            console.rule("Building new CROWNlib")
            # create build directory
            if not os.path.exists(_build_dir):
                os.makedirs(_build_dir)
            # same for the install directory
            if not os.path.exists(_install_dir):
                os.makedirs(_install_dir)

            # actual payload:
            console.rule("Starting cmake step for CROWNlib")
            console.log(f"Using CROWN {_crown_path}")
            console.log(f"Using build_directory {_build_dir}")
            console.log(f"Using install directory {_install_dir}")
            console.rule("")

            # run crown compilation script
            command = [
                "bash",
                _compile_script,
                _crown_path,  # CROWNFOLDER=$1
                _install_dir,  # INSTALLDIR=$2
                _build_dir,  # BUILDDIR=$3
                _analysis,  # ANALYSIS=$4
            ]
            self.run_command_readable(command)
            console.rule("Finished build of CROWNlib")
            output.parent.touch()
            output.copy_from_local(_local_libfile)


class ConfigureDatasets(Task):
    """
    Gather information on the selected datasets.
    """

    nick = luigi.Parameter()
    era = luigi.Parameter()
    sample_type = luigi.Parameter()
    silent = luigi.BoolParameter(default=False, significant=False)

    def output(self):
        target = self.remote_target(
            f"sample_database/{self.nanoAOD_version}/{self.nick}.json"
        )
        return target

    def load_filelist_config(self):
        # first check if a json exists, if not, check for a yaml
        sample_configfile_json = f"sample_database/{self.nanoAOD_version}/{self.era}/{self.sample_type}/{self.nick}.json"
        if os.path.exists(sample_configfile_json):
            with open(sample_configfile_json, "r") as stream:
                try:
                    sample_data = json.load(stream)
                except json.JSONDecodeError as exc:
                    print(exc)
                    raise Exception("Failed to load sample information")
        else:
            console.log(
                f"The sample config json does not exist: {sample_configfile_json}"
            )
            raise Exception("Failed to load sample information")
        return sample_data

    def run(self):
        output = self.output()
        if not output.exists():
            sample_data = self.load_filelist_config()
            if not self.silent:
                console.log("Sample: {}".format(self.nick))
                console.log("Era: {}".format(sample_data["era"]))
                console.log("Type: {}".format(sample_data["sample_type"]))
                console.log("Total Files: {}".format(sample_data["nfiles"]))
                console.log("Total Events: {}".format(sample_data["nevents"]))
                console.rule()
            output.dump(sample_data)

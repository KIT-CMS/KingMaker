import law
import luigi
import os
import glob
import shutil
import tarfile
import subprocess
import threading
import time
import json
import hashlib
from CROWNBase import CROWNBuildBase, CROWNLocalBuildBase
from framework import console, Task, resolve_nanoAOD_version, HTCondorWorkflow
from helpers.helpers import create_abspath
from CROWNBase import CROWNExecuteBase
from helpers.helpers import get_alternate_file_uri
from helpers.helpers import convert_to_comma_seperated

_dataset_filelist_cache = {}
_dataset_filelist_lock = threading.Lock()

_source_hash_cache = {}
_source_hash_lock = threading.Lock()


def load_dataset_filelist(dataset_task):
    # dataset_task.output().localize() is a real network copy; cache it so the
    # per-sample cost is paid once even though create_branch_map runs it again later
    key = dataset_task.output().uri()
    with _dataset_filelist_lock:
        inputdata = _dataset_filelist_cache.get(key)
    if inputdata is not None:
        return inputdata

    if not dataset_task.complete():
        dataset_task.run()
    with dataset_task.output().localize("r") as _file:
        inputdata = _file.load()

    with _dataset_filelist_lock:
        _dataset_filelist_cache[key] = inputdata
    return inputdata


class CROWNRun(CROWNExecuteBase):
    """
    Gather and compile CROWN with the given configuration
    """

    problematic_eras = luigi.ListParameter()

    def workflow_requires(self):
        requirements = {}
        requirements["dataset"] = {}
        requirements["crown_build"] = CROWNBuild.req(
            self,
            htcondor_request_cpus=self.htcondor_request_cpus,
        )
        return requirements

    def create_branch_map(self):
        branch_map = {}
        branchcounter = 0
        dataset = ConfigureDatasets.req(self)
        inputdata = load_dataset_filelist(dataset)
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
        _tarball_name = f"crown_{self.analysis}_{self.config}_{_sample_type}_{_era}.tar.gz"
        _tarball = next(
            t
            for t in inputs["crown_build"]["collection"]._flat_target_list
            if t.basename == _tarball_name
        )
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
        _executable = "./{}_{}_{}".format(self.config, _sample_type, _era)
        # actual payload:
        console.rule("Starting CROWNRun")
        console.log("Executable: {}".format(_executable))
        console.log("inputfile {}".format(_inputfiles))
        console.log("outputfile {}".format(_outputfile))
        console.log("workdir {}".format(_workdir))  # run CROWN
        command = self.wrap_command([_executable] + _crown_args)
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
        # Small delay to ensure file handles are released
        time.sleep(1)
        for i, outputfile in enumerate(outputs):
            local_filename = os.path.join(
                _workdir,
                _outputfile.replace(".root", "_{}.root".format(self.scopes[i])),
            )
            # if the output files were produced in multithreaded mode,
            # we have to open the files once again, setting the
            # kEntriesReshuffled bit to false, otherwise,
            # we cannot add any friends to the trees
            command = self.wrap_command(
                [
                    "python3",
                    "processor/tasks/helpers/ResetROOTStatusBit.py",
                    "--input {}".format(local_filename),
                ]
            )
            self.run_command(
                command=command,
                silent=True,
            )
            # for each outputfile, add the scope suffix
            outputfile.copy_from_local(local_filename)
        console.rule("Finished CROWNRun")


class CROWNBuild(CROWNBuildBase, HTCondorWorkflow, law.LocalWorkflow):
    """
    Compile CROWN executables for every (sample_type, era) combination needed for the
    run, then package and upload one tarball per combination. Submits to HTCondor by
    default; pass e.g. --CROWNBuild-workflow local to run branches directly on the
    submission host instead, same as CROWNRun/CROWNExecuteBase.
    """

    nanoAOD_version = luigi.Parameter(default="", significant=False)

    def create_branch_map(self):
        # one branch per (sample_type, era) pair actually needed by the requested
        # samples, not the full cross product of all_sample_types x all_eras - e.g.
        # a list spanning data/2024 and mc/2023 shouldn't also build data/2023.
        return {
            i: {"sample_type": sample_type, "era": era}
            for i, (sample_type, era) in enumerate(
                tuple(pair) for pair in self.required_build_combinations
            )
        }

    def workflow_requires(self):
        return {"crownlib": BuildCROWNLib.req(self)}

    def htcondor_output_directory(self):
        return self.local_dir_target(f"htcondor_files/build/{self.analysis}_{self.config}")

    def htcondor_job_config(self, config, job_num, branches):
        with self.staged_crown_source():
            config = super().htcondor_job_config(config, job_num, branches)
        config.custom_content.append((
            "JobBatchName",
            f"CROWNBuild-{self.analysis}-{self.config}-{self.production_tag}",
        ))
        return config

    def output(self):
        sample_type = self.branch_data["sample_type"]
        era = self.branch_data["era"]
        return self.remote_target(
            f"crown_{self.analysis}_{self.config}_{sample_type}_{era}.tar.gz"
        )

    def run(self):
        crownlib = self.workflow_input()["crownlib"]
        output = self.output()
        _analysis = str(self.analysis)
        _config = str(self.config)
        _threads = str(self.htcondor_request_cpus)
        _sample_type = self.branch_data["sample_type"]
        _era = self.branch_data["era"]
        _tag = f"{self.production_tag}/CROWN_{_analysis}_{_config}_{_sample_type}_{_era}"
        _install_dir = os.path.join(str(self.install_dir), _tag)
        _build_dir = os.path.join(str(self.build_dir), _tag)
        _crown_path = self.crown_source_path()
        _compile_script = os.path.join(
            str(os.path.abspath("processor")), "tasks", "scripts", "compile_crown.sh"
        )
        _shifts = convert_to_comma_seperated(self.shifts)
        _scopes = convert_to_comma_seperated(self.scopes)

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
        console.log(f"Sampletype: {_sample_type}")
        console.log(f"Era: {_era}")
        console.log(f"Scopes: {_scopes}")
        console.log(f"Shifts: {_shifts}")
        console.rule("")

        # spdlog artifacts bundled alongside libCROWNLIB.so by BuildCROWNLib.run(),
        # extracted into _build_dir by setup_build_environment() above; passed through
        # to cmake so AddLogging.cmake reuses them instead of fetching+building spdlog
        # again for every branch job.
        _spdlog_lib = os.path.join(_build_dir, "spdlog", "lib", "libspdlog.a")
        _spdlog_include = os.path.join(_build_dir, "spdlog", "include")

        # run crown compilation script
        command = [
            "bash",
            _compile_script,
            _crown_path,  # CROWNFOLDER=$1
            _analysis,  # ANALYSIS=$2
            _config,  # CONFIG=$3
            _sample_type,  # SAMPLES=$4
            _era,  # all_eras=$5
            _scopes,  # SCOPES=$6
            _shifts,  # SHIFTS=$7
            _install_dir,  # INSTALLDIR=$8
            _build_dir,  # BUILDDIR=$9
            f"CROWN_{_analysis}_{_config}_{_sample_type}_{_era}",  # TARBALLNAME=$10, unused by the script
            _threads,  # THREADS=$11
            _spdlog_lib,  # SPDLOG_PREBUILT_LIB=$12
            _spdlog_include,  # SPDLOG_PREBUILT_INCLUDE=$13
        ]
        self.run_command_readable(self.wrap_command(command))
        console.rule("Finished CROWN compilation")

        # package and upload the tarball for this (sample_type, era)
        tarball_path = os.path.join(_install_dir, output.basename)

        def exclude_files(tarinfo):
            filename = os.path.basename(tarinfo.name)
            if filename.endswith(".tar.gz"):
                return None
            if filename.startswith(f"{_config}") and not filename.endswith(
                f"{_sample_type}_{_era}"
            ):
                return None
            return tarinfo

        console.log(f"Creating tarball for {_sample_type} {_era}")
        with tarfile.open(tarball_path, "w:gz") as tar:
            tar.add(_install_dir, arcname=".", filter=exclude_files)
        self.upload_tarball(output, tarball_path, 10)
        os.remove(tarball_path)
        console.rule(
            f"Finished CROWNBuild for {_analysis} {_config} {_sample_type} {_era}"
        )


class BuildCROWNLib(CROWNLocalBuildBase):
    """
    Compile the CROWN shared libary to be used for all executables with the given configuration
    """

    # configuration variables
    build_dir = luigi.Parameter()
    install_dir = luigi.Parameter()
    # friend_tag = luigi.Parameter(default="ntuples")
    analysis = luigi.Parameter()

    nanoAOD_version = luigi.Parameter(default="", significant=False)

    def get_source_hash(self):
        """
        Compute a hash of the CROWN source tree so that any code change produces
        a new task output, triggering a fresh compilation.

        output()/complete() get called repeatedly by luigi/law while building and
        checking the task graph, so cache the result per source tree instead of
        re-walking and re-hashing hundreds of files on every call.

        BuildCROWNLib itself only ever runs locally, but this method also gets
        evaluated inside remote CROWNBuild condor jobs (law recomputes
        workflow_requires() there, which resolves BuildCROWNLib.output()). Those jobs
        don't have the full "CROWN" checkout, only the staged copy CROWNBuild
        ships in build_staging/CROWN_src - which contains exactly the subdirs/file
        hashed below, so falling back to it here reproduces the same hash/filename
        that the local run already uploaded under.
        """
        crown_path = os.path.abspath("CROWN")
        if not os.path.exists(crown_path):
            crown_path = os.path.abspath(os.path.join("build_staging", "CROWN_src"))
        with _source_hash_lock:
            cached = _source_hash_cache.get(crown_path)
        if cached is not None:
            return cached
        subdirs = ["src", "include", "analysis_configurations"]
        h = hashlib.sha256()
        for subdir in sorted(subdirs):
            dirpath = os.path.join(crown_path, subdir)
            if not os.path.exists(dirpath):
                continue
            for root, dirs, files in os.walk(dirpath):
                # skip generated artifacts, they change while the workflow runs
                dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".git"))
                for fname in sorted(files):
                    if fname.endswith((".pyc", ".pyo", ".so")):
                        continue
                    fpath = os.path.join(root, fname)
                    h.update(os.path.relpath(fpath, crown_path).encode())
                    with open(fpath, "rb") as f:
                        h.update(f.read())
        cmake_path = os.path.join(crown_path, "CMakeLists.txt")
        if os.path.exists(cmake_path):
            with open(cmake_path, "rb") as f:
                h.update(f.read())
        digest = h.hexdigest()[:16]
        with _source_hash_lock:
            _source_hash_cache[crown_path] = digest
        return digest

    def output(self):
        target = self.remote_target(f"crownlib_{self.get_source_hash()}.tar.gz")
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
        else:
            console.rule("Building new CROWNlib")
            # create build directory
            os.makedirs(_build_dir, exist_ok=True)
            # same for the install directory
            os.makedirs(_install_dir, exist_ok=True)

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

        _spdlog_lib_matches = glob.glob(os.path.join(_build_dir, "lib*", "libspdlog.a"))
        if not _spdlog_lib_matches:
            raise FileNotFoundError(f"libspdlog.a not found under {_build_dir}")
        _spdlog_include_dir = os.path.join(_build_dir, "include", "spdlog")

        _bundle_dir = os.path.join(_install_dir, "bundle")
        if os.path.exists(_bundle_dir):
            shutil.rmtree(_bundle_dir)
        os.makedirs(os.path.join(_bundle_dir, "spdlog", "lib"))
        os.makedirs(os.path.join(_bundle_dir, "spdlog", "include"))
        shutil.copy2(_local_libfile, os.path.join(_bundle_dir, "libCROWNLIB.so"))
        shutil.copy2(
            _spdlog_lib_matches[0],
            os.path.join(_bundle_dir, "spdlog", "lib", "libspdlog.a"),
        )
        shutil.copytree(
            _spdlog_include_dir,
            os.path.join(_bundle_dir, "spdlog", "include", "spdlog"),
        )

        _bundle_tarball = os.path.join(_install_dir, output.basename)
        with tarfile.open(_bundle_tarball, "w:gz") as tar:
            tar.add(_bundle_dir, arcname=".")
        output.parent.touch()
        output.copy_from_local(_bundle_tarball)
        os.remove(_bundle_tarball)


class ConfigureDatasets(Task):
    """
    Gather information on the selected datasets.
    """

    nick = luigi.Parameter()
    era = luigi.Parameter()
    sample_type = luigi.Parameter()
    silent = luigi.BoolParameter(default=False, significant=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nanoAOD_version = resolve_nanoAOD_version(
            os.path.join(self.era, self.sample_type, f"{self.nick}.json"),
            self.nanoAOD_version,
        )

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

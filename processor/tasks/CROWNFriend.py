import luigi
import os
import shutil
import tarfile
import subprocess
import time
import law
from framework import console, HTCondorWorkflow
from CROWNMain import CROWNRun, resolve_crown_proxy
from helpers.helpers import create_abspath
from CROWNBase import CROWNExecuteBase
from CROWNBase import CROWNBuildBase
from CROWNBase import CROWNLocalBuildBase
from CROWNMain import BuildCROWNLib
from helpers.helpers import convert_to_comma_seperated


class CROWNFriend(CROWNExecuteBase):
    friend_mapping = luigi.DictParameter(default={})
    friend_config = luigi.Parameter()
    config = luigi.Parameter()
    nick = luigi.Parameter()
    analysis = luigi.Parameter()

    def workflow_requires(self):
        requirements = {}
        requirements["ntuples"] = CROWNRun.req(self)
        requirements["friend_tarball"] = CROWNBuildFriend.req(self)
        required_friends = self.friend_mapping[self.friend_config].get("requires", [])
        for requires_config in required_friends:
            if requires_config not in self.friend_mapping:
                raise Exception(f"Friend config {requires_config} not found in mapping")
            friend_tag = self.friend_mapping[requires_config]["friend_tag"]
            requirements[f"CROWNFriend_{self.nick}_{friend_tag}"] = CROWNFriend.req(
                self, friend_config=requires_config
            )
        return requirements

    def create_branch_map(self):
        branch_map = {}
        counter = 0
        inputs = self.workflow_input()
        branches = [
            inputfile
            for inputfile in inputs["ntuples"]["collection"]._flat_target_list
            if inputfile.path.endswith(".root")
        ]
        required_friends = self.friend_mapping[self.friend_config].get("requires", [])
        friend_inputs = [
            inputs[
                f'CROWNFriend_{self.nick}_{self.friend_mapping[requires_config]["friend_tag"]}'
            ]["collection"]
            for requires_config in required_friends  # type: ignore
        ]
        friend_branches = [
            [
                friend_inputfile
                for friend_inputfile in friend_input._flat_target_list
                if friend_inputfile.path.endswith(".root")
            ]
            for friend_input in friend_inputs
        ]
        for inputfile in branches:
            if not inputfile.path.endswith(".root"):
                continue
            # identify the scope from the inputfile
            scope = inputfile.path.split("/")[-2]
            if scope in self.scopes:
                branch_map[counter] = {
                    "scope": scope,
                    "nick": self.nick,
                    "era": self.era,
                    "sample_type": self.sample_type,
                    "inputfile": os.path.expandvars(str(self.wlcg_path))
                    + inputfile.path,
                    "filecounter": int(counter / len(self.scopes)),
                }
                filename = inputfile.path.split("/")[-1]
                for friend_index, _ in enumerate(required_friends):
                    if not friend_branches[friend_index][counter].path.endswith(
                        ".root"
                    ):
                        break
                    branch_map[counter][f"inputfile_friend_{friend_index}"] = (
                        os.path.expandvars(self.wlcg_path)
                        + friend_branches[friend_index][counter].path
                    )
                    friend_file_name = friend_branches[friend_index][
                        counter
                    ].path.split("/")[-1]
                    if friend_file_name != filename:
                        raise Exception(
                            f"Friend file name {friend_file_name} does not match input file name {filename}"
                        )
                counter += 1
        return branch_map

    def output(self):
        """
        The function `output` generates a file path based on various input parameters and returns the
        corresponding file target.
        :return: The `target` variable is being returned.
        """
        friend_tag = self.friend_mapping[self.friend_config]["friend_tag"]
        nicks = [
            "{friendtag}/{era}/{nick}/{scope}/{nick}_{branch}.root".format(
                friendtag=friend_tag,
                era=self.branch_data["era"],
                nick=self.branch_data["nick"],
                branch=self.branch_data["filecounter"],
                scope=self.branch_data["scope"],
            )
        ]
        # quantities_map json for each scope only needs to be created once per sample
        if self.branch_data["filecounter"] == 0:
            friend_tag = self.friend_mapping[self.friend_config]["friend_tag"]
            nicks.append(
                "{friendtag}/{era}/{nick}/{scope}/{era}_{nick}_{scope}_quantities_map.json".format(
                    friendtag=friend_tag,
                    era=self.branch_data["era"],
                    nick=self.branch_data["nick"],
                    scope=self.branch_data["scope"],
                )
            )

        targets = self.remote_target(nicks)
        return targets

    def run(self):
        """
        The function runs a CROWN friend process, unpacking a tarball if necessary, setting the
        environment, executing the process, and copying the output file.
        """
        outputs = self.output()
        output = outputs[0]
        inputs = self.workflow_input()
        branch_data = self.branch_data
        scope = branch_data["scope"]
        era = branch_data["era"]
        sample_type = branch_data["sample_type"]
        quantities_map_output = None
        create_quantities_map = False
        if self.branch_data["filecounter"] == 0:
            console.log(f"Will create quantities map for scope {scope}")
            create_quantities_map = True
            quantities_map_output = outputs[1]
        _base_workdir = os.path.abspath("workdir")
        create_abspath(_base_workdir)
        friend_tag = self.friend_mapping[self.friend_config]["friend_tag"]
        _workdir = os.path.join(_base_workdir, f"{self.production_tag}_{friend_tag}")
        create_abspath(_workdir)
        _inputfile = branch_data["inputfile"]
        _friend_inputs = [
            branch_data[input] for input in branch_data if "inputfile_friend_" in input
        ]
        # set the outputfilename to the first name in the output list, removing the scope suffix
        _outputfile = str(output.basename.replace(f"_{scope}.root", ".root"))
        _abs_executable = "{}/{}_{}_{}_{}".format(
            _workdir, self.friend_config, sample_type, era, scope
        )
        _friend_tarball = inputs["friend_tarball"]["collection"]._flat_target_list[0]
        console.log(
            "Getting CROWN friend_tarball from {}".format(_friend_tarball.uri())
        )
        with _friend_tarball.localize("r") as _file:
            _tarballpath = _file.path
        # first unpack the tarball if the exec is not there yet. All branches share
        # the same workdir and tarball, so a marker file signals that one of them is
        # currently unpacking; the others wait for it to disappear. A marker can
        # survive a crashed/interrupted run - treat it as stale (and remove it) once
        # it is older than UNPACK_LOCK_TIMEOUT so that future runs are not blocked.
        UNPACK_LOCK_TIMEOUT = 600  # seconds
        tempfile = os.path.join(
            _workdir,
            "unpacking_{}_{}_{}".format(self.friend_config, sample_type, era),
        )
        while os.path.exists(tempfile):
            if time.time() - os.path.getmtime(tempfile) > UNPACK_LOCK_TIMEOUT:
                console.log(f"Removing stale unpack marker {tempfile}")
                os.remove(tempfile)
                break
            time.sleep(1)
        if not os.path.exists(_abs_executable) and not os.path.exists(tempfile):
            # create a temp file to signal that we are unpacking
            open(
                tempfile,
                "a",
            ).close()
            tar = tarfile.open(_tarballpath, "r:gz")
            tar.extractall(_workdir)
            os.remove(tempfile)
        _crown_args = [_outputfile] + [_inputfile] + _friend_inputs
        _executable = "./{}_{}_{}_{}".format(
            self.friend_config, sample_type, era, scope
        )
        # actual payload:
        console.rule("Starting CROWNMultiFriends")
        console.log("Executable: {}".format(_executable))
        console.log("inputfile(s) {} {}".format(_inputfile, _friend_inputs))
        console.log("outputfile {}".format(_outputfile))
        console.log("workdir {}".format(_workdir))  # run CROWN
        command = self.wrap_command([_executable] + _crown_args)
        console.log(f"Running command: {command}")

        # Hand the container an absolute, existing proxy file. CROWN runs with
        # cwd=<_workdir>, and the singularity container only has that workdir
        # subtree bound - a proxy outside of it (e.g. <KingMaker>/.proxy/x509up)
        # is invisible to XRootD inside the container even with an absolute
        # X509_USER_PROXY ("Unable to use cert+key file ... does not exist.",
        # "security protocol 'ztn' disallowed for non-TLS connections."). So copy
        # the proxy into the workdir and point X509_USER_PROXY at that copy.
        _crown_env = None
        _crown_proxy = resolve_crown_proxy()
        if _crown_proxy is not None:
            _proxy_in_workdir_dir = os.path.join(_workdir, ".proxy")
            create_abspath(_proxy_in_workdir_dir)
            _proxy_in_workdir = os.path.join(_proxy_in_workdir_dir, "x509up")
            shutil.copy2(_crown_proxy, _proxy_in_workdir)
            os.chmod(_proxy_in_workdir, 0o600)
            _crown_env = dict(os.environ)
            _crown_env["X509_USER_PROXY"] = _proxy_in_workdir
            console.log(
                f"Using proxy {_proxy_in_workdir} for CROWN friend input access"
            )
        else:
            console.log(
                "No X509 proxy file found; CROWN will use default xrootd credentials"
            )
        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            cwd=_workdir,
            env=_crown_env,
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
        local_filename = os.path.join(
            _workdir,
            _outputfile.replace(".root", "_{}.root".format(scope)),
        )
        # for each outputfile, add the scope suffix
        output.copy_from_local(local_filename)
        if create_quantities_map and quantities_map_output is not None:
            inputfile = os.path.join(
                _workdir,
                _outputfile.replace(".root", f"_{scope}.root"),
            )
            local_outputfile = os.path.join(_workdir, "quantities_map.json")

            # The quantities map is extracted with ROOT, which is not available in
            # the luigi worker env of the local workflow - run the helper inside the
            # crown container instead, same as the ResetROOTStatusBit step in
            # CROWNRun. wrap_command() keeps the command plain on HTCondor, where
            # the branch already runs inside the container.
            qmap_command = self.wrap_command(
                [
                    "python3",
                    "processor/tasks/helpers/GetQuantitiesMap.py",
                    "--input {}".format(inputfile),
                    "--era {}".format(self.branch_data["era"]),
                    "--sample_type {}".format(self.branch_data["sample_type"]),
                    "--scope {}".format(scope),
                    "--output {}".format(local_outputfile),
                    "--libdir {}".format(os.path.join(_workdir, "lib")),
                ]
            )
            self.run_command_readable(qmap_command)
            # copy the generated quantities_map json to the output
            quantities_map_output.copy_from_local(local_outputfile)
        console.rule("Finished CROWNFriend")


class CROWNBuildFriend(CROWNBuildBase, HTCondorWorkflow, law.LocalWorkflow):
    """
    Gather and compile CROWN for friend tree production with the given configuration.
    Submits to HTCondor by default; pass e.g. --CROWNBuildFriend-workflow local to run
    directly on the submission host instead, same as CROWNRun/CROWNBuild.
    """

    # additional configuration variables
    friend_config = luigi.Parameter()
    era = luigi.Parameter()
    sample_type = luigi.Parameter()
    # insignificant: tarball is shared per (sample_type, era); avoids concurrent nicks racing to build the same _build_dir
    nick = luigi.Parameter(significant=False)
    friend_mapping = luigi.DictParameter(default={})

    def create_branch_map(self):
        return {0: None}

    def workflow_requires(self):
        requirements = {}
        requirements["Ntuples"] = CROWNRun.req(self)
        requirements["Ntuples_quantities"] = QuantitiesMap.req(self, friend_config="")
        required_friends = self.friend_mapping[self.friend_config].get("requires", [])
        for requires_config in required_friends:
            if requires_config not in self.friend_mapping:
                raise Exception(f"Friend config {requires_config} not found in mapping")
            requirements[f"Friend_{requires_config}"] = CROWNFriend.req(
                self, friend_config=requires_config
            )
            requirements[f"Friend_{requires_config}_quantities"] = QuantitiesMap.req(
                self, friend_config=requires_config
            )
        requirements["crownlib"] = BuildCROWNLib.req(self)
        return requirements

    def htcondor_output_directory(self):
        friend_tag = self.friend_mapping[self.friend_config]["friend_tag"]
        return self.local_dir_target(
            f"htcondor_files/build_friend/{self.analysis}_{friend_tag}_{self.sample_type}_{self.era}"
        )

    def htcondor_job_config(self, config, job_num, branches):
        friend_tag = self.friend_mapping[self.friend_config]["friend_tag"]
        with self.staged_crown_source():
            config = super().htcondor_job_config(config, job_num, branches)
        config.custom_content.append(
            (
                "JobBatchName",
                f"CROWNBuildFriend-{self.analysis}-{friend_tag}-{self.production_tag}",
            )
        )
        return config

    def output(self):
        friend_tag = self.friend_mapping[self.friend_config]["friend_tag"]
        target = self.remote_target(
            f"crown_friends_{self.analysis}_{friend_tag}_{self.sample_type}_{self.era}.tar.gz"
        )
        return target

    def run(self):
        friend_tag = self.friend_mapping[self.friend_config]["friend_tag"]
        inputs = self.workflow_input()
        # get quantities map
        main_quantities_map = inputs["Ntuples_quantities"]
        required_friends = self.friend_mapping[self.friend_config].get("requires", [])
        friend_quantities_maps = []
        for requires_config in required_friends:
            friend_quantities_maps += inputs[f"Friend_{requires_config}_quantities"]
        quantities_maps = main_quantities_map + friend_quantities_maps
        crownlib = inputs["crownlib"]
        # get output file path
        output = self.output()
        # convert list to comma separated strings
        _sample_type = self.sample_type
        _era = self.era
        _shifts = convert_to_comma_seperated(self.shifts)
        _scopes = convert_to_comma_seperated(self.scopes)
        _analysis = str(self.analysis)
        _friend_config = str(self.friend_config)
        _friend_tag = str(friend_tag)
        # also use the tag for the local tarball creation
        _tag = f"{self.production_tag}/CROWNFriend_{_analysis}_{_friend_config}_{_friend_tag}_{_sample_type}_{_era}"
        _install_dir = os.path.join(str(self.install_dir), _tag)
        _build_dir = os.path.join(str(self.build_dir), _tag)
        _crown_path = self.crown_source_path()
        _compile_script = os.path.join(
            str(os.path.abspath("processor")),
            "tasks",
            "scripts",
            "compile_crown_friends.sh",
        )

        _quantities_map_dir = os.path.abspath(os.path.join("quantities_maps", _tag))
        if os.path.exists(_quantities_map_dir):
            shutil.rmtree(_quantities_map_dir)
        os.makedirs(_quantities_map_dir, exist_ok=True)
        quantities_map_paths = []
        for target in quantities_maps:
            local_path = os.path.join(_quantities_map_dir, target.basename)
            target.copy_to_local(local_path)
            quantities_map_paths.append(local_path)

        console.rule(f"Building new CROWN Friend tarball for {friend_tag}")
        _build_dir, _install_dir = self.setup_build_environment(
            _build_dir, _install_dir, crownlib
        )
        # actual payload:
        console.rule(f"Starting cmake step for CROWN Friends {friend_tag}")
        console.log(f"Using CROWN {_crown_path}")
        console.log(f"Using build_directory {_build_dir}")
        console.log(f"Using install directory {_install_dir}")
        console.log("Settings used: ")
        console.log(f"Analysis: {_analysis}")
        console.log(f"Friend Config: {_friend_config}")
        console.log(f"Friend Tags: {_friend_tag}")
        console.log(f"Sampletype: {_sample_type}")
        console.log(f"Era: {_era}")
        console.log(f"Scopes: {_scopes}")
        console.log(f"Shifts: {_shifts}")
        console.log(f"Quantities maps: {quantities_map_paths}")
        console.rule("")

        _spdlog_lib = os.path.join(_build_dir, "spdlog", "lib", "libspdlog.a")
        _spdlog_include = os.path.join(_build_dir, "spdlog", "include")

        # run crown compilation script
        command = [
            "bash",
            _compile_script,
            _crown_path,  # CROWNFOLDER=$1
            _analysis,  # ANALYSIS=$2
            _friend_config,  # CONFIG=$3
            _sample_type,  # SAMPLES=$4
            _era,  # ERAS=$5
            _scopes,  # SCOPES=$6
            _shifts,  # SHIFTS=$7
            _install_dir,  # INSTALLDIR=$8
            _build_dir,  # BUILDDIR=$9
            convert_to_comma_seperated(quantities_map_paths),  # QUANTITIESMAP=$10
            _spdlog_lib,  # SPDLOG_PREBUILT_LIB=$11
            _spdlog_include,  # SPDLOG_PREBUILT_INCLUDE=$12
        ]
        self.run_command_readable(self.wrap_command(command))

        console.log(f"Creating tarball for {friend_tag}")
        _tarball = os.path.join(_install_dir, output.basename)
        _tmp_tarball = os.path.join(
            os.path.dirname(_install_dir), f"{output.basename}.tmp.{os.getpid()}"
        )

        def exclude_files(tarinfo):
            return None if tarinfo.name.endswith(".tar.gz") else tarinfo

        with tarfile.open(_tmp_tarball, "w:gz") as tar:
            tar.add(_install_dir, arcname=".", filter=exclude_files)
        os.replace(_tmp_tarball, _tarball)

        self.upload_tarball(output, os.path.join(_install_dir, output.basename), 10)
        console.rule("Finished CROWNBuildFriend")


class QuantitiesMap(CROWNLocalBuildBase):

    scopes = luigi.ListParameter()
    all_sample_types = luigi.ListParameter(significant=False)
    all_eras = luigi.ListParameter(significant=False)
    era = luigi.Parameter()
    sample_type = luigi.Parameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()
    # insignificant: quantities depend on the executable, built per (sample_type, era), not per sample
    nick = luigi.Parameter(significant=False)
    friend_config = luigi.Parameter(default="")
    friend_mapping = luigi.DictParameter(default={})

    def requires(self):
        requirements = {}
        if self.friend_config != "":
            requirements[f"CROWNFriend_{self.friend_config}"] = CROWNFriend.req(self)
        else:
            requirements["CROWNRun"] = CROWNRun.req(self)
        return requirements

    def output(self):
        if self.friend_config != "":
            name = self.friend_mapping[self.friend_config]["friend_tag"]
        else:
            name = "ntuple"
        return self.remote_target(
            [
                f"{self.sample_type}_{self.era}_{name}_{scope}_quantities_map.json"
                for scope in self.scopes
            ]
        )

    def run(self):
        if self.friend_config != "":
            inputs = self.input()[f"CROWNFriend_{self.friend_config}"]["collection"]
        else:
            inputs = self.input()[f"CROWNRun"]["collection"]
        rootfiles = [
            target
            for target in inputs._flat_target_list
            if target.path.endswith(".root")
        ]
        if len(rootfiles) == 0:
            raise Exception("No input rootfile found")

        from helpers.GetQuantitiesMap import read_quantities_map

        for outputfile, scope in zip(self.output(), self.scopes):
            # the quantities of a scope have to be read from a rootfile of that scope,
            # the scope is the last folder in the path of the rootfile
            scope_inputs = [
                target for target in rootfiles if target.path.split("/")[-2] == scope
            ]
            if len(scope_inputs) == 0:
                raise Exception(f"No input rootfile found for scope {scope}")
            rootfile_path = self.get_remote_path(scope_inputs[0])
            # read_quantities_map() writes to outputfile directly (plain open()), so
            # it needs a real local path even though output() is now a remote target.
            local_outputfile = self.local_path(outputfile.basename)
            read_quantities_map(
                input_file=rootfile_path,
                era=self.era,
                sample_type=self.sample_type,
                scope=scope,
                outputfile=local_outputfile,
                libdir=self.KingMaker_path("CROWN/.cache"),
            )
            outputfile.parent.touch()
            outputfile.copy_from_local(local_outputfile)

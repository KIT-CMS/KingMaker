import luigi
import os
import tarfile
import subprocess
import time
import law
from framework import console
from CROWNMain import CROWNRun
from framework import console
from helpers.helpers import create_abspath
from CROWNBase import CROWNExecuteBase
from CROWNBase import CROWNBuildBase
from CROWNMain import BuildCROWNLib
from helpers.GetQuantitiesMap import read_quantities_map
from helpers.helpers import convert_to_comma_seperated, printi

class CROWNFriend(CROWNExecuteBase):
    friend_mapping = luigi.DictParameter(default={})
    friend_config = luigi.Parameter()
    config = luigi.Parameter(significant=False)
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
            requirements[f'CROWNFriendsNew_{self.nick}_{self.friend_mapping[requires_config]["friend_name"]}'] = (
                CROWNFriend.req(self, friend_config=requires_config)
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
            inputs[f'CROWNFriendsNew_{self.nick}_{self.friend_mapping[requires_config]["friend_name"]}'][
                "collection"
            ]
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
                for friend_index, requires_config in enumerate(required_friends):
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
        nicks = [
            "{friendname}/{era}/{nick}/{scope}/{nick}_{branch}.root".format(
                friendname=self.friend_mapping[self.friend_config]["friend_name"],
                era=self.branch_data["era"],
                nick=self.branch_data["nick"],
                branch=self.branch_data["filecounter"],
                scope=self.branch_data["scope"],
            )
        ]
        # quantities_map json for each scope only needs to be created once per sample
        if self.branch_data["filecounter"] == 0:
            nicks.append(
                "{friendname}/{era}/{nick}/{scope}/{era}_{nick}_{scope}_quantities_map.json".format(
                    friendname=self.friend_mapping[self.friend_config]["friend_name"],
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
            console.log("Will create quantities map for scope {}".format(scope))
            create_quantities_map = True
            quantities_map_output = outputs[1]
        _base_workdir = os.path.abspath("workdir")
        create_abspath(_base_workdir)
        _workdir = os.path.join(
            _base_workdir, f'{self.production_tag}_{self.friend_mapping[self.friend_config]["friend_name"]}'
        )
        create_abspath(_workdir)
        _inputfile = branch_data["inputfile"]
        _friend_inputs = [
            branch_data[input] for input in branch_data if "inputfile_friend_" in input
        ]
        # set the outputfilename to the first name in the output list, removing the scope suffix
        _outputfile = str(output.basename.replace("_{}.root".format(scope), ".root"))
        _abs_executable = "{}/{}_{}_{}".format(
            _workdir, self.friend_config, sample_type, era
        )
        console.log(
            "Getting CROWN friend_tarball from {}".format(
                inputs["friend_tarball"].uri()
            )
        )
        with inputs["friend_tarball"].localize("r") as _file:
            _tarballpath = _file.path
        # first unpack the tarball if the exec is not there yet
        tempfile = os.path.join(
            _workdir,
            "unpacking_{}_{}_{}".format(self.friend_config, sample_type, era),
        )
        while os.path.exists(tempfile):
            time.sleep(1)
        if not os.path.exists(_abs_executable):
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
        with subprocess.Popen(
            [_executable] + _crown_args,
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
        local_filename = os.path.join(
            _workdir,
            _outputfile.replace(".root", "_{}.root".format(scope)),
        )
        # for each outputfile, add the scope suffix
        output.copy_from_local(local_filename)
        if create_quantities_map and quantities_map_output is not None:
            inputfile = os.path.join(
                _workdir,
                _outputfile.replace(".root", "_{}.root".format(scope)),
            )
            local_outputfile = os.path.join(_workdir, "quantities_map.json")
            
            read_quantities_map(input_file=inputfile, era=self.branch_data["era"], sample_type=self.branch_data["sample_type"], scope=scope, outputfile=local_outputfile, libdir=os.path.join(_workdir, "lib"))
            # copy the generated quantities_map json to the output
            quantities_map_output.copy_from_local(local_outputfile)
        console.rule("Finished CROWNMultiFriends")


# class CROWNBuildFriendNew(Task):
class CROWNBuildFriend(CROWNBuildBase):
    """
    Gather and compile CROWN for friend tree production with the given configuration
    """

    # additional configuration variables
    friend_config = luigi.Parameter()
    era = luigi.Parameter()
    sample_type = luigi.Parameter()
    nick = luigi.Parameter(significant=False)
    friend_mapping = luigi.DictParameter(default={})

    def requires(self):
        requirements = {}
        requirements["Ntuples"] = CROWNRun.req(self)
        requirements["Ntuples_quantities"] = QuantitiesMap.req(self, friend_config="")
        required_friends = self.friend_mapping[self.friend_config].get("requires", [])
        for requires_config in required_friends:
            if requires_config not in self.friend_mapping:
                raise Exception(f"Friend config {requires_config} not found in mapping")
            requirements[f'Friend_{requires_config}'] = (
                CROWNFriend.req(self, friend_config=requires_config)
            )
            requirements[f'Friend_{requires_config}_quantities'] = (
                QuantitiesMap.req(self, friend_config=requires_config)
            )
        requirements["crownlib"] = BuildCROWNLib.req(self)
        return requirements

    def output(self):
        target = self.remote_target(
            f"crown_friends_{self.analysis}_{self.friend_config}_{self.sample_type}_{self.era}.tar.gz"
        )
        return target

    def run(self):
        friend_name = self.friend_mapping[self.friend_config]["friend_name"]
        inputs = self.input()
        # get quantities map
        main_quantities_map = inputs["Ntuples_quantities"]
        required_friends = self.friend_mapping[self.friend_config].get("requires", [])
        friend_quantities_maps = []
        for requires_config in required_friends:
            friend_quantities_maps += inputs[f"Friend_{requires_config}_quantities"]
        quantities_maps = main_quantities_map + friend_quantities_maps
        quantities_map_paths = [p.path for p in quantities_maps]
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
        _friend_name = str(friend_name)
        # also use the tag for the local tarball creation
        _tag = f"{self.production_tag}/CROWNFriends_{_analysis}_{_friend_config}_{_friend_name}_{_sample_type}_{_era}"
        _install_dir = os.path.join(str(self.install_dir), _tag)
        _build_dir = os.path.join(str(self.build_dir), _tag)
        _crown_path = os.path.abspath("CROWN")
        _compile_script = os.path.join(
            str(os.path.abspath("processor")),
            "tasks",
            "scripts",
            "compile_crown_friends.sh",
        )

        if output.exists():
            console.log(f"tarball already existing in {output.path}")

        elif law.LocalFileTarget(os.path.join(_install_dir, output.basename)).exists():
            console.log(f"tarball already existing in tarball directory {_install_dir}")
            console.log(f"Copying to remote: {output.path}")
            output.copy_from_local(os.path.join(_install_dir, output.basename))
        else:
            console.rule(f"Building new CROWN Friend tarball for {friend_name}")
            _build_dir, _install_dir = self.setup_build_environment(
                _build_dir, _install_dir, crownlib
            )
            # actual payload:
            console.rule(f"Starting cmake step for CROWN Friends {friend_name}")
            console.log(f"Using CROWN {_crown_path}")
            console.log(f"Using build_directory {_build_dir}")
            console.log(f"Using install directory {_install_dir}")
            console.log("Settings used: ")
            console.log(f"Analysis: {_analysis}")
            console.log(f"Friend Config: {_friend_config}")
            console.log(f"Friend Names: {_friend_name}")
            console.log(f"Sampletype: {_sample_type}")
            console.log(f"Era: {_era}")
            console.log(f"Scopes: {_scopes}")
            console.log(f"Shifts: {_shifts}")
            console.log(f"Quantities maps: {quantities_map_paths}")
            console.rule("")

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
                output.basename,  # TARBALLNAME=$10
                convert_to_comma_seperated(quantities_map_paths),  # QUANTITIESMAP=$11
            ]
            self.run_command_readable(command)
            self.upload_tarball(output, os.path.join(_install_dir, output.basename), 10)
        console.rule("Finished CROWNBuildFriend")


class QuantitiesMap(CROWNBuildBase):

    scopes = luigi.ListParameter()
    all_sample_types = luigi.ListParameter(significant=False)
    all_eras = luigi.ListParameter(significant=False)
    era = luigi.Parameter()
    sample_type = luigi.Parameter()
    analysis = luigi.Parameter() #significant=False)
    config = luigi.Parameter() #significant=False)
    nick = luigi.Parameter() #significant=False)
    friend_config = luigi.Parameter(default="")
    friend_name = luigi.Parameter(default="")
    friend_mapping = luigi.DictParameter(default={})

    def requires(self):
        requirements = {}
        if self.friend_config != "":
            requirements[f"CROWNFriend_{self.friend_config}"] = CROWNFriend.req(self)
        else:
            requirements[f"CROWNRun"] = CROWNRun.req(self)
        return requirements
        

    def output(self):
        effective_config = self.friend_config if self.friend_config != "" else self.config
        return self.local_target([f"{self.nick}_{effective_config}_{scope}_quantities_map.json" for scope in self.scopes])

    def run(self):
        if self.friend_config != "":
            inputs = self.input()[f"CROWNFriend_{self.friend_config}"]["collection"]
        else:
            inputs = self.input()[f"CROWNRun"]["collection"]
        single_input = inputs.targets[0][0]
        if not single_input.path.endswith(".root"):
            raise Exception("Input should be a single rootfile")
        rootfile_path = self.get_remote_path(single_input)
        for outputfile, scope in zip(self.output(), self.scopes):
            read_quantities_map(input_file=rootfile_path, era=self.era, sample_type=self.sample_type, scope=scope, outputfile=outputfile.path, libdir=self.KingMaker_path("CROWN/.cache"))

           
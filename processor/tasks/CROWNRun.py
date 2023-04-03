import law
import luigi
import os
from CROWNBuild import CROWNBuild
import tarfile
from ConfigureDatasets import ConfigureDatasets
import subprocess
import time
from framework import console
from law.config import Config

from framework import Task, HTCondorWorkflow


def create_abspath(file_path):
    if not os.path.exists(file_path):
        os.makedirs(file_path)


class CROWNRun(HTCondorWorkflow, law.LocalWorkflow):
    """
    Gather and compile CROWN with the given configuration
    """

    output_collection_cls = law.NestedSiblingFileCollection

    scopes = luigi.ListParameter()
    all_sampletypes = luigi.ListParameter()
    all_eras = luigi.ListParameter()
    nick = luigi.Parameter()
    sampletype = luigi.Parameter()
    era = luigi.Parameter()
    shifts = luigi.Parameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()
    production_tag = luigi.Parameter()
    files_per_task = luigi.IntParameter()
    problematic_eras = luigi.ListParameter()

    def htcondor_output_directory(self):
        # Add identification-str to prevent interference between different tasks of the same class
        # Expand path to account for use of env variables (like $USER)
        return law.wlcg.WLCGDirectoryTarget(
            self.remote_path(f"htcondor_files/{self.nick}"),
            law.wlcg.WLCGFileSystem(
                None, base="{}".format(os.path.expandvars(self.wlcg_path))
            ),
        )

    def htcondor_create_job_file_factory(self):
        task_name = self.__class__.__name__
        task_name = "_".join([task_name, self.nick])
        _cfg = Config.instance()
        job_file_dir = _cfg.get_expanded("job", "job_file_dir")
        job_files = os.path.join(
            job_file_dir,
            self.production_tag,
            task_name,
            "files",
        )
        factory = super(HTCondorWorkflow, self).htcondor_create_job_file_factory(
            dir=job_files,
            mkdtemp=False,
        )
        return factory

    def htcondor_job_config(self, config, job_num, branches):
        config = super().htcondor_job_config(config, job_num, branches)
        config.custom_content.append(
            (
                "JobBatchName",
                f"{self.nick}-{self.analysis}-{self.config}-{self.production_tag}",
            )
        )
        for type in ["Log", "Output", "Error"]:
            logfilepath = ""
            for param in config.custom_content:
                if param[0] == type:
                    logfilepath = param[1]
                    break
            # split the filename, and add the sample nick as an additional folder
            logfolder = logfilepath.split("/")[:-1]
            logfile = logfilepath.split("/")[-1]
            logfolder.append(self.nick)
            # create the new path
            os.makedirs("/".join(logfolder), exist_ok=True)
            config.custom_content.append((type, "/".join(logfolder) + "/" + logfile))
        return config

    def modify_polling_status_line(self, status_line):
        """
        Hook to modify the status line that is printed during polling.
        """
        name = f"{self.nick} (Analysis: {self.analysis} Config: {self.config} Tag: {self.production_tag})"
        return f"{status_line} - {law.util.colored(name, color='light_cyan')}"

    def workflow_requires(self):
        requirements = {}
        requirements["dataset"] = {}
        requirements["dataset"] = ConfigureDatasets.req(
            self, nick=self.nick, production_tag=self.production_tag
        )
        requirements["tarball"] = CROWNBuild.req(self)
        return requirements

    def requires(self):
        return {"tarball": CROWNBuild.req(self)}

    def create_branch_map(self):
        branch_map = {}
        branchcounter = 0
        dataset = ConfigureDatasets(nick=self.nick, production_tag=self.production_tag)
        # since we use the filelist from the dataset, we need to run it first
        dataset.run()
        datsetinfo = dataset.output()
        with datsetinfo.localize("r") as _file:
            inputdata = _file.load()
        branches = {}
        if len(inputdata["filelist"]) == 0:
            raise Exception("No files found for dataset {}".format(self.nick))
        files_per_task = self.files_per_task
        if self.sampletype == "data" and any(era in self.nick for era in self.problematic_eras):
            files_per_task = 1
        for filecounter, filename in enumerate(inputdata["filelist"]):
            if (int(filecounter / files_per_task)) not in branches:
                branches[int(filecounter / files_per_task)] = []
            branches[int(filecounter / files_per_task)].append(filename)
        for x in branches:
            branch_map[branchcounter] = {}
            branch_map[branchcounter]["nick"] = self.nick
            branch_map[branchcounter]["era"] = self.era
            branch_map[branchcounter]["sampletype"] = self.sampletype
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
        # quantities_map json for each scope only needs to be created once per sample
        if self.branch == 0:
            nicks += [
                "{era}/{nick}/{scope}/{era}_{nick}_{scope}_quantities_map.json".format(
                    era=self.branch_data["era"],
                    nick=self.branch_data["nick"],
                    scope=scope,
                )
                for scope in self.scopes
            ]
        targets = self.remote_targets(nicks)
        for target in targets:
            target.parent.touch()
        return targets

    def run(self):
        outputs = self.output()
        rootfile_outputs = [x for x in outputs if x.path.endswith(".root")]
        quantities_map_outputs = [
            x for x in outputs if x.path.endswith("quantities_map.json")
        ]
        branch_data = self.branch_data
        _base_workdir = os.path.abspath("workdir")
        create_abspath(_base_workdir)
        _workdir = os.path.join(
            _base_workdir, f"{self.production_tag}_{self.analysis}_{self.config}"
        )
        create_abspath(_workdir)
        _inputfiles = branch_data["files"]
        # set the outputfilename to the first name in the output list, removing the scope suffix
        _outputfile = str(
            rootfile_outputs[0].basename.replace(
                "_{}.root".format(self.scopes[0]), ".root"
            )
        )
        _abs_executable = "{}/{}_{}_{}".format(
            _workdir, self.config, branch_data["sampletype"], branch_data["era"]
        )
        console.log(
            "Getting CROWN tarball from {}".format(self.input()["tarball"].uri())
        )
        with self.input()["tarball"].localize("r") as _file:
            _tarballpath = _file.path
        # first unpack the tarball if the exec is not there yet
        _tempfile = os.path.join(
            _workdir,
            "unpacking_{}_{}_{}".format(
                self.config, branch_data["sampletype"], branch_data["era"]
            ),
        )
        while os.path.exists(_tempfile):
            time.sleep(1)
        if not os.path.exists(_abs_executable) and not os.path.exists(_tempfile):
            # create a temp file to signal that we are unpacking
            open(_tempfile, "a").close()
            tar = tarfile.open(_tarballpath, "r:gz")
            tar.extractall(_workdir)
            os.remove(_tempfile)
        # set environment using env script
        my_env = self.set_environment("{}/init.sh".format(_workdir))
        _crown_args = [_outputfile] + _inputfiles
        _executable = "./{}_{}_{}".format(
            self.config, branch_data["sampletype"], branch_data["era"]
        )
        # actual payload:
        console.rule("Starting CROWNRun")
        console.log("Executable: {}".format(_executable))
        console.log("inputfile {}".format(_inputfiles))
        console.log("outputfile {}".format(_outputfile))
        console.log("workdir {}".format(_workdir))  # run CROWN
        with subprocess.Popen(
            [_executable] + _crown_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            env=my_env,
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
        for i, outputfile in enumerate(rootfile_outputs):
            outputfile.parent.touch()
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
                sourcescript=[
                    "{}/init.sh".format(_workdir),
                ],
                silent=True,
            )
            # for each outputfile, add the scope suffix
            outputfile.copy_from_local(local_filename)
        # write the quantities_map json, per scope This is only required once per sample,
        # only do it if the branch number is 0
        if self.branch == 0:
            for i, outputfile in enumerate(quantities_map_outputs):
                outputfile.parent.touch()
                inputfile = os.path.join(
                    _workdir,
                    _outputfile.replace(".root", "_{}.root".format(self.scopes[i])),
                )
                local_outputfile = os.path.join(_workdir, "quantities_map.json")

                self.run_command(
                    command=[
                        "python3",
                        "processor/tasks/helpers/GetQuantitiesMap.py",
                        "--input {}".format(inputfile),
                        "--era {}".format(self.branch_data["era"]),
                        "--scope {}".format(self.scopes[i]),
                        "--sampletype {}".format(self.branch_data["sampletype"]),
                        "--output {}".format(local_outputfile),
                    ],
                    sourcescript=[
                        "{}/init.sh".format(_workdir),
                    ],
                    silent=True,
                )
                # copy the generated quantities_map json to the output
                outputfile.copy_from_local(local_outputfile)
        console.rule("Finished CROWNRun")

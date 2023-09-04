import law
import luigi
import os
import yaml
import shutil
from framework import console
from law.config import Config
from framework import HTCondorWorkflow, Task
from law.task.base import WrapperTask
from rich.table import Table
from helpers.helpers import *
import ast


class ProduceBase(WrapperTask):
    """
    collective task to trigger friend production for a list of samples,
    if the samples are not already present, trigger ntuple production first
    """

    sample_list = luigi.Parameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()
    dataset_database = luigi.Parameter(significant=False)
    production_tag = luigi.Parameter()
    shifts = luigi.Parameter()
    scopes = luigi.Parameter()

    def parse_samplelist(self, sample_list):
        if str(sample_list).endswith(".txt"):
            with open(str(sample_list)) as file:
                samples = [nick.replace("\n", "") for nick in file.readlines()]
        elif "," in str(sample_list):
            samples = str(sample_list).split(",")
        else:
            samples = [sample_list]
        return samples

    def sanitize_scopes(self):
        # sanitize the scopes information
        try:
            self.scopes = ast.literal_eval(str(self.scopes))
        except:
            self.scopes = self.scopes
        if isinstance(self.scopes, str):
            self.scopes = self.scopes.split(",")
        elif isinstance(self.scopes, list):
            self.scopes = self.scopes

    def sanitize_shifts(self):
        # sanitize the shifts information
        try:
            self.shifts = ast.literal_eval(str(self.shifts))
        except:
            self.shifts = self.shifts
        if self.shifts is None:
            self.shifts = "None"
        if isinstance(self.shifts, list):
            self.shifts = self.shifts.join(",")

    def sanitize_friend_dependencies(self):
        # in this case, the required friends require not only the ntuple, but also other friends,
        # this means we have to add additional requirements to the task
        if isinstance(self.friend_dependencies, str):
            self.friend_dependencies = self.friend_dependencies.split(",")
        elif isinstance(self.friend_dependencies, list):
            self.friend_dependencies = self.friend_dependencies

    def set_sample_data(self, samples):
        data = {}
        data["sampletypes"] = set()
        data["eras"] = set()
        data["details"] = {}
        table = Table(title=f"Samples (selected Scopes: {self.scopes})")
        table.add_column("Samplenick", justify="left")
        table.add_column("Era", justify="left")
        table.add_column("Sampletype", justify="left")

        for nick in samples:
            data["details"][nick] = {}
            # check if sample exists in datasets.yaml
            with open(str(self.dataset_database), "r") as stream:
                sample_db = yaml.safe_load(stream)
            if nick not in sample_db:
                console.log(
                    "Sample {} not found in {}".format(nick, self.dataset_database)
                )
                raise Exception("Sample not found in DB")
            sample_data = sample_db[nick]
            data["details"][nick]["era"] = str(sample_data["era"])
            data["details"][nick]["sampletype"] = sample_data["sample_type"]
            # all samplestypes and eras are added to a list,
            # used to built the CROWN executable
            data["eras"].add(data["details"][nick]["era"])
            data["sampletypes"].add(data["details"][nick]["sampletype"])
            table.add_row(
                nick, data["details"][nick]["era"], data["details"][nick]["sampletype"]
            )
        console.log(table)
        return data


class CROWNExecuteBase(HTCondorWorkflow, law.LocalWorkflow):
    """
    Gather and compile CROWN with the given configuration
    """

    output_collection_cls = law.NestedSiblingFileCollection
    scopes = luigi.ListParameter()
    all_sampletypes = luigi.ListParameter(significant=False)
    all_eras = luigi.ListParameter(significant=False)
    nick = luigi.Parameter()
    sampletype = luigi.Parameter()
    era = luigi.Parameter()
    shifts = luigi.Parameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()
    production_tag = luigi.Parameter()
    files_per_task = luigi.IntParameter()

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
        class_name = self.__class__.__name__
        if "Friend" in class_name:
            task_name = [class_name + self.nick, self.friend_name]
        else:
            task_name = [class_name + self.nick]
        _cfg = Config.instance()
        job_file_dir = _cfg.get_expanded("job", "job_file_dir")
        job_files = os.path.join(
            job_file_dir,
            self.production_tag,
            "_".join(task_name),
            "files",
        )
        factory = super(HTCondorWorkflow, self).htcondor_create_job_file_factory(
            dir=job_files,
            mkdtemp=False,
        )
        return factory

    def htcondor_job_config(self, config, job_num, branches):
        class_name = self.__class__.__name__
        if "Friend" in class_name:
            condor_batch_name_pattern = (
                f"{self.nick}-{self.analysis}-{self.friend_name}-{self.production_tag}"
            )
        else:
            condor_batch_name_pattern = (
                f"{self.nick}-{self.analysis}-{self.config}-{self.production_tag}"
            )
        config = super().htcondor_job_config(config, job_num, branches)
        config.custom_content.append(("JobBatchName", self.condor_batch_name_pattern))
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
        class_name = self.__class__.__name__
        if "Friend" in class_name:
            status_line_pattern = f"{self.nick} (Analysis: {self.analysis} FriendConfig: {self.friend_config} Tag: {self.production_tag})"
        else:
            status_line_pattern = f"{self.nick} (Analysis: {self.analysis} Config: {self.config} Tag: {self.production_tag})"
        return f"{status_line} - {law.util.colored(status_line_pattern, color='light_cyan')}"


class CROWNBuildBase(Task):
    # configuration variables
    scopes = luigi.ListParameter()
    shifts = luigi.Parameter()
    build_dir = luigi.Parameter()
    install_dir = luigi.Parameter()
    all_sampletypes = luigi.ListParameter(significant=False)
    all_eras = luigi.ListParameter(significant=False)
    analysis = luigi.Parameter()
    config = luigi.Parameter(significant=False)
    htcondor_request_cpus = luigi.IntParameter(default=1)
    production_tag = luigi.Parameter()
    threads = htcondor_request_cpus

    def setup_build_environment(self, build_dir, install_dir, crownlib):
        # create build directory
        if not os.path.exists(build_dir):
            os.makedirs(build_dir)
        build_dir = os.path.abspath(build_dir)
        # same for the install directory
        if not os.path.exists(install_dir):
            os.makedirs(install_dir)
        install_dir = os.path.abspath(install_dir)

        # localize crownlib to build directory
        console.log(f"Localizing crownlib {crownlib.path} to {build_dir}")
        with crownlib.localize("r") as _file:
            _crownlib_file = _file.path
        # copy crownlib to build directory
        shutil.copy(_crownlib_file, os.path.join(build_dir, crownlib.basename))

        return build_dir, install_dir

    # @timeout_decorator.timeout(10)
    def upload_tarball(self, output, path, timeout):
        console.log("Copying from local: {}".format(path))
        output.parent.touch()
        timeout = 10
        console.log(
            f"Copying to remote with a {timeout} second timeout : {output.path}"
        )
        output.copy_from_local(path)
        return True

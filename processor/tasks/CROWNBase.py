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

# import timeout_decorator
import time


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
        """
        The function `parse_samplelist` takes a sample list as input and returns a list of samples, handling
        different input formats.

        :param sample_list: The `sample_list` parameter is the input that the function takes. It can be
        either a string, a list of strings, or a file path pointing to a text file
        :return: a list of samples.
        """
        if str(sample_list).endswith(".txt"):
            with open(str(sample_list)) as file:
                samples = [nick.replace("\n", "") for nick in file.readlines()]
        elif "," in str(sample_list):
            samples = str(sample_list).split(",")
        else:
            samples = [sample_list]
        return samples

    def sanitize_scopes(self):
        """
        The function sanitizes the scopes information by converting it to a list if it is a string or
        leaving it unchanged if it is already a list.
        """
        # sanitize the scopes information
        if not isinstance(self.scopes, list):
            self.scopes = self.scopes.split(",")
        self.scopes = [scope.strip() for scope in self.scopes]

    def sanitize_shifts(self):
        """
        The function sanitizes the shifts information by converting it to a list if possible and handling
        any exceptions.
        """
        # sanitize the shifts information
        if not isinstance(self.shifts, list):
            self.shifts = self.shifts.split(",")
        self.shifts = [shift.strip() for shift in self.shifts]
        if self.shifts is None:
            self.shifts = "None"
        else:
            # now convert the list to a comma separated string
            self.shifts = convert_to_comma_seperated(self.shifts)

    def sanitize_friend_dependencies(self):
        """
        The function `sanitize_friend_dependencies` checks the type of `self.friend_dependencies` and
        converts it to a list if it is a string.
        """
        # in this case, the required friends require not only the ntuple, but also other friends,
        # this means we have to add additional requirements to the task
        if isinstance(self.friend_dependencies, str):
            self.friend_dependencies = self.friend_dependencies.split(",")
        elif isinstance(self.friend_dependencies, list):
            self.friend_dependencies = self.friend_dependencies

    def validate_friend_mapping(self):
        """
        The function `validate_friend_mapping` checks if the `friend_mapping` dictionary is empty, and if
        so, creates a new dictionary with `friend_dependencies` as keys and values, otherwise it checks if
        each friend in `friend_dependencies` is present in `friend_mapping` and raises an exception if not.
        """
        data = {}
        if len(self.friend_mapping.keys()) == 0:
            for friend in self.friend_dependencies:
                data[friend] = friend
        else:
            for friend in self.friend_dependencies:
                if friend in self.friend_mapping:
                    data[friend] = self.friend_mapping[friend]
                else:
                    raise Exception(
                        f"Friend {friend} not found in friend mapping {self.friend_mapping}"
                    )
        self.friend_mapping = data

    def set_sample_data(self, samples):
        """
        The function `set_sample_data` sets up sample data by extracting information from a dataset database
        and organizing it into a dictionary and printing a rich table.

        :param samples: The `samples` parameter is a list of sample nicknames. Each nickname represents a
        sample that will be processed in the code
        :return: a dictionary named "data" which contains the following keys:
        - "sampletypes": a set of sample types
        - "eras": a set of eras
        - "details": a dictionary containing details about each sample, where the keys are the sample
        nicknames and the values are dictionaries containing the era and sample type of each sample.
        """
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
        """
        The function `htcondor_output_directory` returns a WLCGDirectoryTarget object that represents a
        directory in the WLCG file system.
        :return: The code is returning a `law.wlcg.WLCGDirectoryTarget` object.
        """
        # Add identification-str to prevent interference between different tasks of the same class
        # Expand path to account for use of env variables (like $USER)
        return law.wlcg.WLCGDirectoryTarget(
            self.remote_path(f"htcondor_files/{self.nick}"),
            law.wlcg.WLCGFileSystem(
                None, base="{}".format(os.path.expandvars(self.wlcg_path))
            ),
        )

    def htcondor_create_job_file_factory(self):
        """
        The function `htcondor_create_job_file_factory` creates a job file factory for HTCondor workflows.
        :return: The method is returning the factory object that is created by calling the
        `htcondor_create_job_file_factory` method of the superclass `HTCondorWorkflow`.
        """
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
        config.custom_content.append(("JobBatchName", condor_batch_name_pattern))
        for type in ["log", "stdout", "stderr"]:
            logfilepath = getattr(config, type)
            # split the filename, and add the sample nick as an additional folder
            logfolder, logfile = os.path.split(logfilepath)
            logfolder = os.path.join(logfolder, self.nick)
            # create the new path
            os.makedirs(logfolder, exist_ok=True)
            setattr(config, type, os.path.join(logfolder, logfile))
        return config

    def modify_polling_status_line(self, status_line):
        """
        The function `modify_polling_status_line` modifies the status line that is printed during polling by
        appending additional information based on the class name.

        :param status_line: The `status_line` parameter is a string that represents the current status line
        during polling
        :return: The modified status line with additional information about the class name, analysis,
        configuration, and production tag.
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
        """
        The function sets up the build environment by creating build and install directories, localizing a
        crownlib file, and copying it to the build directory.

        :param build_dir: The `build_dir` parameter is the directory where the build files will be
        generated. It is the location where the code will be compiled and built into an executable or
        library
        :param install_dir: The `install_dir` parameter is the directory where the built files will be
        installed
        :param crownlib: The `crownlib` parameter is the crownlib file that will be copied to the build directory
        """
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
    def copy_from_local_with_timeout(self, output, path):
        output.copy_from_local(path)

    def upload_tarball(self, output, path, retries=3):
        """
        The `upload_tarball` function attempts to copy a file from a local path to a remote location with a
        specified number of retries.

        :param output: The `output` parameter is the destination path where the tarball will be copied to on
        the remote server
        :param path: The `path` parameter in the `upload_tarball` method represents the local path of the
        tarball file that needs to be uploaded
        :param retries: The `retries` parameter is an optional parameter that specifies the number of times
        the upload should be retried in case of failure. By default, it is set to 3, meaning that the upload
        will be attempted up to 3 times before giving up, defaults to 3 (optional)
        :return: The function `upload_tarball` returns a boolean value. It returns `True` if the tarball is
        successfully uploaded, and `False` if the upload fails after the specified number of retries.
        """
        console.log("Copying from local: {}".format(path))
        output.parent.touch()
        for i in range(retries):
            try:
                console.log(f"Copying to remote (attempt {i+1}): {output.path}")
                self.copy_from_local_with_timeout(output, path)
                return True
            except Exception as e:
                console.log(f"Upload failed (attempt {i+1}): {e}")
                time.sleep(1)
        console.log(f"Upload failed after {retries} attempts.")
        return False

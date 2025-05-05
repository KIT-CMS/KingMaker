import law
import luigi
import os
import json
import shutil
from framework import console
from framework import HTCondorWorkflow, Task
from law.task.base import WrapperTask
from rich.table import Table
from helpers.helpers import convert_to_comma_seperated
import hashlib

# import timeout_decorator
import time

from processor.tasks.helpers.NanoAODVersions import NanoAODVersions


class ProduceBase(Task, WrapperTask):
    """
    collective task to trigger friend production for a list of samples,
    if the samples are not already present, trigger ntuple production first
    """

    sample_list = luigi.Parameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()
    nanoAOD_version = luigi.Parameter(default=NanoAODVersions.v12.value)
    dataset_database = luigi.Parameter(default=None, significant=False)
    shifts = luigi.Parameter()
    scopes = luigi.Parameter()
    silent = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically set the default value of dataset_database based on nanoAOD_version
        if self.dataset_database is None:
            self.dataset_database = f"sample_database/{self.nanoAOD_version}/datasets.json"

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

    def validate_friend_mapping(self):
        """
        The function validates that the friend_mapping dictionary is not empty.
        If empty, raises an exception since we need the mapping information.
        """
        if len(self.friend_mapping.keys()) == 0:
            raise Exception("Friend mapping cannot be empty")

    def set_sample_data(self, samples):
        """
        The function `set_sample_data` sets up sample data by extracting information from a dataset database
        and organizing it into a dictionary and printing a rich table.

        :param samples: The `samples` parameter is a list of sample nicknames. Each nickname represents a
        sample that will be processed in the code
        :return: a dictionary named "data" which contains the following keys:
        - "sample_types": a set of sample types
        - "eras": a set of eras
        - "details": a dictionary containing details about each sample, where the keys are the sample
        nicknames and the values are dictionaries containing the era and sample type of each sample.
        """
        data = {}
        data["sample_types"] = set()
        data["eras"] = set()
        data["details"] = {}
        table = Table(title=f"Samples (selected Scopes: {self.scopes})")
        table.add_column("Samplenick", justify="left")
        table.add_column("Era", justify="left")
        table.add_column("Sampletype", justify="left")

        with open(str(self.dataset_database), "r") as stream:
            sample_db = json.load(stream)

        for nick in samples:
            data["details"][nick] = {}
            # check if sample exists in datasets.json
            if nick not in sample_db:
                console.log(
                    "Sample {} not found in {}".format(nick, self.dataset_database)
                )
                raise Exception(f"Sample not found in DB: {nick}")
            sample_data = sample_db[nick]
            data["details"][nick]["era"] = str(sample_data["era"])
            data["details"][nick]["sample_type"] = sample_data["sample_type"]
            # all samplestypes and eras are added to a list,
            # used to built the CROWN executable
            data["eras"].add(data["details"][nick]["era"])
            data["sample_types"].add(data["details"][nick]["sample_type"])
            if not self.silent:
                table.add_row(
                    nick,
                    data["details"][nick]["era"],
                    data["details"][nick]["sample_type"],
                )
        if not self.silent:
            console.log(table)
            console.rule()
        return data


class CROWNExecuteBase(HTCondorWorkflow, law.LocalWorkflow):
    """
    Gather and compile CROWN with the given configuration
    """

    scopes = luigi.ListParameter()
    all_sample_types = luigi.ListParameter(significant=False)
    all_eras = luigi.ListParameter(significant=False)
    nick = luigi.Parameter()
    sample_type = luigi.Parameter()
    era = luigi.Parameter()
    shifts = luigi.Parameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()
    files_per_task = luigi.IntParameter()

    def htcondor_output_directory(self):
        return law.LocalDirectoryTarget(self.local_path(f"htcondor_files/{self.nick}"))

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
    build_dir = luigi.Parameter(
        default="build",
        significant=False,
    )
    install_dir = luigi.Parameter(
        default="tarballs",
        significant=False,
    )
    all_sample_types = luigi.ListParameter()
    all_eras = luigi.ListParameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()
    # Needed to propagate thread count to build tasks
    htcondor_request_cpus = luigi.IntParameter(default=1)

    def get_tarball_hash(self):
        """
        The function `get_tarball_hash` generates a SHA-256 hash based on concatenated and sorted lists of
        sample types, eras, scopes, and shifts.
        :return: The `get_tarball_hash` method returns a SHA-256 hash of a string created by concatenating
        sorted and comma-separated lists of sample types, eras, scopes, and shifts.
        """

        sample_types = list(self.all_sample_types)
        eras = list(self.all_eras)
        scopes = list(self.scopes)
        if self.shifts is not None and self.shifts != "None":
            shifts = list(self.shifts)
        else:
            shifts = ["None"]
        sample_types.sort()
        eras.sort()
        scopes.sort()
        shifts.sort()
        # convert the lists to a single comma separated string
        sample_types = convert_to_comma_seperated(sample_types)
        eras = convert_to_comma_seperated(eras)
        scopes = convert_to_comma_seperated(scopes)
        shifts = convert_to_comma_seperated(shifts)
        id_list = f"{sample_types};{eras};{scopes};{shifts}"
        hash = hashlib.sha256(str(id_list).encode()).hexdigest()
        return hash

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
                self.copy_from_local_with_timeout(output, os.path.abspath(path))
                return True
            except Exception as e:
                console.log(f"Upload failed (attempt {i+1}): {e}")
                time.sleep(1)
        console.log(f"Upload failed after {retries} attempts.")
        return False

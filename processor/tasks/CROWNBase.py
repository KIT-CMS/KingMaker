import law
import luigi
import os
import json
import shutil
import tarfile
import subprocess
import sys
import fcntl
import contextlib
from framework import (
    console,
    HTCondorWorkflow,
    Task,
    KingmakerSandbox,
    sandbox_pre_setup_cmds_factory,
    resolve_sample_data,
)
from law.task.base import WrapperTask
from rich.table import Table
from helpers.helpers import convert_to_comma_seperated
import hashlib
import time


class ProduceBase(WrapperTask, Task):
    """
    collective task to trigger friend production for a list of samples,
    if the samples are not already present, trigger ntuple production first
    """

    sample_list = luigi.Parameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()
    dataset_database = luigi.Parameter(default="", significant=False)
    shifts = luigi.Parameter()
    scopes = luigi.Parameter()
    silent = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only pin dataset_database to a single version's datasets.json when a
        # nanoAOD_version was requested explicitly, matching the historical
        # single-version behavior. If nanoAOD_version is left unset, dataset_database
        # stays empty and each sample's version/details are resolved individually
        # in set_sample_data(), so a sample_list can span multiple nanoAOD versions.
        if self.dataset_database == "" and self.nanoAOD_version != "":
            self.dataset_database = (
                f"sample_database/{self.nanoAOD_version}/datasets.json"
            )

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

    def validate_friend_mapping(self, mapping={}):
        """
        The function validates that the friend_mapping dictionary is not empty.
        If empty, raises an exception since we need the mapping information.
        """
        if len(mapping) == 0:
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
        table.add_column("NanoAOD", justify="left")

        # dataset_database is only set when nanoAOD_version was requested explicitly
        # (pins every sample to that single version, as before); otherwise each
        # sample's version is resolved individually, so the list can span versions.
        sample_db = None
        if self.dataset_database:
            with open(str(self.dataset_database), "r") as stream:
                sample_db = json.load(stream)

        for nick in samples:
            data["details"][nick] = {}
            if sample_db is not None:
                if nick not in sample_db:
                    console.log(
                        "Sample {} not found in {}".format(nick, self.dataset_database)
                    )
                    raise Exception(f"Sample not found in DB: {nick}")
                sample_data = sample_db[nick]
                nanoAOD_version = self.nanoAOD_version
            else:
                nanoAOD_version, sample_data = resolve_sample_data(
                    nick, self.nanoAOD_version
                )
            data["details"][nick]["era"] = str(sample_data["era"])
            data["details"][nick]["sample_type"] = sample_data["sample_type"]
            data["details"][nick]["nanoAOD_version"] = nanoAOD_version
            # all samplestypes and eras are added to a list,
            # used to built the CROWN executable
            data["eras"].add(data["details"][nick]["era"])
            data["sample_types"].add(data["details"][nick]["sample_type"])
            if not self.silent:
                table.add_row(
                    nick,
                    data["details"][nick]["era"],
                    data["details"][nick]["sample_type"],
                    nanoAOD_version,
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
    required_build_combinations = luigi.ListParameter(
        significant=False,
        description="[sample_type, era] pairs that are actually needed",
    )
    nick = luigi.Parameter()
    sample_type = luigi.Parameter()
    era = luigi.Parameter()
    shifts = luigi.Parameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()
    files_per_task = luigi.IntParameter(significant=False)
    custom_files_per_task = luigi.DictParameter(
        default={},
        significant=False,
        description="Map specific sample_types to custom files_per_task",
    )

    def htcondor_output_directory(self):
        if hasattr(self, "friend_config") and self.friend_config != "":
            friend_tag = self.friend_mapping[self.friend_config]["friend_tag"]
            path = f"htcondor_files/{friend_tag}/{self.nick}"
        else:
            path = f"htcondor_files/ntuples/{self.nick}"
        return self.local_dir_target(path)

    def htcondor_job_config(self, config, job_num, branches):
        effective_name = (
            self.friend_mapping[self.friend_config]["friend_tag"]
            if hasattr(self, "friend_config") and self.friend_config != ""
            else "Ntuple"
        )
        condor_batch_name_pattern = (
            f"{self.nick}-{self.analysis}-{effective_name}-{self.production_tag}"
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


class CROWNBuildBase:
    """
    Shared parameters and helpers for tasks that compile CROWN inside the crown
    container. Plain mixin (no Task/SandboxTask base of its own) so it composes with
    either a KingmakerSandbox-based local build (see CROWNLocalBuildBase below) or an
    HTCondorWorkflow-based remote build (see CROWNMain.CROWNBuild).
    """

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
    required_build_combinations = luigi.ListParameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()

    @contextlib.contextmanager
    def staged_crown_source(self):
        """
        Serializes stage_crown_source() -> (caller's htcondor_job_config work,
        i.e. tar+upload) -> cleanup_staged_crown_source() across concurrent task
        instances. CROWNBuild has one instance submitting all its branches together,
        but CROWNBuildFriend has one separate instance per (friend_config,
        sample_type, era), and luigi runs different task instances' htcondor_job_config()
        calls in separate worker *processes* - so a plain threading.Lock wouldn't help,
        and without any lock, two instances' rmtree/copytree into the same shared
        staging directory can interleave and corrupt each other's copy. All instances
        stage the exact same content (same CROWN checkout subset, same
        self.analysis-based git status), so there's nothing to gain from giving each
        one its own copy - just make sure only one touches the shared directory at a
        time; the others simply wait their turn.
        """
        lock_path = os.path.abspath(".crown_staging.lock")
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                self.stage_crown_source()
                try:
                    yield
                finally:
                    self.cleanup_staged_crown_source()
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

    def stage_crown_source(self):
        """
        HTCondorWorkflow.htcondor_job_config() only ships 'processor', law, and the
        lawluigi configs into the job tarball. The build additionally needs the CROWN
        source tree, which also holds several GB of local build directories, .git,
        .cache and other checkout-local clutter that must never be shipped. Stage only
        the subdirectories actually needed to compile into a clean directory, and point
        additional_files at that instead of the live checkout. Called from
        staged_crown_source() above - not meant to be called directly.
        """
        crown_path = os.path.abspath("CROWN")
        staging_dir = os.path.abspath(os.path.join("build_staging", "CROWN_src"))
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir)
        os.makedirs(staging_dir, exist_ok=True)
        # the job has no sample_database: build the norm/STXS tables here so they ship inside data/
        norm_script = os.path.join(crown_path, "analysis_configurations", str(self.analysis), "norm_table.py")
        if os.path.exists(norm_script):
            combos = getattr(self, "required_build_combinations", None)
            sample_types = {c[0] for c in combos} if combos else getattr(self, "all_sample_types", [])
            subprocess.check_call([sys.executable, norm_script, os.path.join(crown_path, "data", "normalization"), *sample_types])
        for subdir in (
            "src",
            "include",
            "analysis_configurations",
            "cmake",
            "tests",
            "code_generation",
            "data",
        ):
            src = os.path.join(crown_path, subdir)
            if os.path.exists(src):
                shutil.copytree(
                    src,
                    os.path.join(staging_dir, subdir),
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
        for filename in ("CMakeLists.txt", "generate.py"):
            shutil.copy2(
                os.path.join(crown_path, filename),
                os.path.join(staging_dir, filename),
            )
        # code_generation.py stamps generated code with the repo's commit hash / clean
        # state by shelling out to checks/git-status.sh, which needs full git history
        # (git status/rev-parse) - too heavy to ship (.git is hundreds of MB). Run the
        # real script once here, where the git history already is, and stage a static
        # replacement that just echoes the same captured output.
        git_status_output = subprocess.check_output(
            [
                os.path.join(crown_path, "checks", "git-status.sh"),
                crown_path,
                str(self.analysis),
            ],
            stderr=subprocess.STDOUT,
        ).decode("utf-8")
        checks_dir = os.path.join(staging_dir, "checks")
        os.makedirs(checks_dir, exist_ok=True)
        git_status_replacement = os.path.join(checks_dir, "git-status.sh")
        with open(git_status_replacement, "w") as f:
            f.write(
                "#!/bin/bash\ncat <<'CROWN_GIT_STATUS_EOF'\n"
                + git_status_output
                + "CROWN_GIT_STATUS_EOF\n"
            )
        os.chmod(git_status_replacement, 0o755)
        rel_staging_dir = os.path.relpath(staging_dir)
        if rel_staging_dir not in self.additional_files:
            self.additional_files = list(self.additional_files) + [rel_staging_dir]

    def cleanup_staged_crown_source(self):
        """
        The staged copy from stage_crown_source() is only needed transiently to build
        the job tarball; leaving it around just duplicates a large chunk of CROWN/ on
        local disk for no reason, so the whole build_staging/ directory gets recreated
        fresh (and removed again) on every staged_crown_source() call. Safe to remove
        entirely (not just the CROWN_src subdir) because the lock file guarding this
        lives outside of it (see staged_crown_source() above). Called from
        staged_crown_source() above, while still holding that lock - not meant to be
        called directly.
        """
        shutil.rmtree(
            os.path.abspath("build_staging"),
            ignore_errors=True,
        )

    def crown_source_path(self):
        """
        Local-workflow branches run directly on the submission host and use the real
        checkout; htcondor branches run inside the unpacked job sandbox and only have
        the filtered copy staged by stage_crown_source().
        """
        if self.effective_workflow == "local":
            return os.path.abspath("CROWN")
        return os.path.abspath(os.path.join("build_staging", "CROWN_src"))

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
        Downloads and extracts the crownlib bundle - libCROWNLIB.so plus the spdlog
        artifacts built alongside it (see BuildCROWNLib.run()) - into build_dir.
        Extracting straight into build_dir puts libCROWNLIB.so at the canonical path
        the build system looks for it at, and leaves the spdlog artifacts alongside it
        for SPDLOG_PREBUILT_LIB/SPDLOG_PREBUILT_INCLUDE to point at.
        """
        os.makedirs(build_dir, exist_ok=True)
        build_dir = os.path.abspath(build_dir)
        # same for the install directory
        os.makedirs(install_dir, exist_ok=True)
        install_dir = os.path.abspath(install_dir)

        console.log(f"Localizing crownlib bundle {crownlib.path} to {build_dir}")
        with crownlib.localize("r") as _file:
            with tarfile.open(_file.path, "r:gz") as tar:
                tar.extractall(build_dir)

        return build_dir, install_dir

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


class CROWNLocalBuildBase(CROWNBuildBase, KingmakerSandbox, Task):
    """
    Base for build tasks that compile locally, inside a singularity sandbox wrapping
    the whole task (KingmakerSandbox re-execs the entire `law run` invocation inside
    the crown container) rather than submitting to HTCondor. Used by BuildCROWNLib,
    QuantitiesMap, and CROWNBuildFriend.
    """

    # Copy over X509_USER_PROXY, LUIGIPORT, and CCACHE_DIR env values and run sandbox setup
    sandbox_pre_setup_cmds = sandbox_pre_setup_cmds_factory(
        "X509_USER_PROXY",
        "LUIGIPORT",
        "CCACHE_DIR",
        "WF_NAME",
        "LOCAL_SCHEDULER",
        "LUIGI_CFG_SCHEDULER_PORT",
    )

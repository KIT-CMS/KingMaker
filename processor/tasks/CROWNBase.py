import law
import luigi
import os
import shutil
from framework import console
from law.config import Config
from framework import HTCondorWorkflow, Task
from helpers.helpers import *
from BuildCROWNLib import BuildCROWNLib


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
    problematic_eras = luigi.ListParameter()
    task_name_extensions = [nick]
    condor_batch_name_pattern = f"{nick}-{analysis}-{config}-{production_tag}"
    status_line_pattern = (
        f"{nick} (Analysis: {analysis} Config: {config} Tag: {production_tag})"
    )

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
        _cfg = Config.instance()
        job_file_dir = _cfg.get_expanded("job", "job_file_dir")
        job_files = os.path.join(
            job_file_dir,
            self.production_tag,
            "_".join([task_name] + self.task_name_extensions),
            "files",
        )
        factory = super(HTCondorWorkflow, self).htcondor_create_job_file_factory(
            dir=job_files,
            mkdtemp=False,
        )
        return factory

    def htcondor_job_config(self, config, job_num, branches):
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
        return f"{status_line} - {law.util.colored(self.status_line_pattern, color='light_cyan')}"


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

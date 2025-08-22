import os
import luigi
import law
import select
import subprocess
import socket
from enum import Enum
from law.util import interruptable_popen
from rich.console import Console
from datetime import datetime
from tempfile import mkdtemp
from getpass import getuser

try:
    from luigi.parameter import UnconsumedParameterWarning
    import warnings

    # Ignore warnings about unused parameters that are set in the default config but not used by all tasks
    warnings.simplefilter("ignore", UnconsumedParameterWarning)
except:
    pass

law.contrib.load("wlcg")
law.contrib.load("htcondor")
# try to get the terminal width, if this fails, we are probably in a remote job, set it to 140
try:
    current_width = os.get_terminal_size().columns
except OSError:
    current_width = 140
console = Console(width=current_width)

# Determine startup time to use as default production_tag
# LOCAL_TIMESTAMP is used by remote workflows to ensure consistent tags
if os.getenv("LOCAL_TIMESTAMP"):
    startup_time = os.getenv("LOCAL_TIMESTAMP")
else:
    startup_time = datetime.now().strftime("%Y_%m_%d_%H_%M_%S_%f")

# Determine start dir to replace absolute paths
# LOCAL_PWD is used by remote workflows
if os.getenv("LOCAL_PWD"):
    startup_dir = os.getenv("LOCAL_PWD")
else:
    startup_dir = os.getcwd()


class NanoAODVersions(Enum):
    v9 = "nanoAOD_v9"
    v12 = "nanoAOD_v12"
    v15 = "nanoAOD_v15"

    
class Task(law.Task):
    local_user = getuser()
    wlcg_path = luigi.Parameter(
        description="Base-path to remote file location.",
        significant=False,
    )
    local_output_path = luigi.Parameter(
        description="Base-path to local file location.",
        default=os.getenv("ANALYSIS_DATA_PATH"),
        significant=False,
    )
    is_local_output = luigi.BoolParameter(
        description="Whether to use local storage. False by default.",
        default=False,
        significant=False,
    )

    # Modify production_tag to check for override
    production_tag = luigi.Parameter(
        default=f"default/{startup_time}",
        description="Tag to differentiate workflow runs. Set to a timestamp as default.",
    )
    nanoAOD_version = luigi.Parameter(
        default=NanoAODVersions.v12.value,
        description="Version of the NanoAOD files that are used in the analysis. 'NanoAOD_v12' is the default.",
    )

    # Ensure that branch parameter is processed normally
    exclude_params_req = law.Task.exclude_params_req | {"branch"}

    # Prefer some parameters from the command line over the values provided by the .req() method
    prefer_params_cli = law.Task.prefer_params_cli | {"production_tag"}

    # Set default for all inheriting Tasks
    output_collection_cls = law.NestedSiblingFileCollection

    # Path of local targets.
    #   Composed from the analysis path set during the setup.sh
    #   or the local_output_path if is_local_output is set,
    #   the production_tag, the name of the task and an additional path if provided.
    def local_path(self, *path):
        return os.path.join(
            (
                self.local_output_path
                if self.is_local_output
                else os.getenv("ANALYSIS_DATA_PATH")
            ),
            self.production_tag,
            self.__class__.__name__,
            *path,
        )

    def temporary_local_path(self, *path):
        if os.environ.get("_CONDOR_JOB_IWD"):
            prefix = os.environ.get("_CONDOR_JOB_IWD") + "/tmp/"
        else:
            prefix = f"/tmp/{self.local_user}"
        temporary_dir = mkdtemp(dir=prefix)
        parts = (temporary_dir,) + (self.__class__.__name__,) + path
        return os.path.join(*parts)

    def local_target(self, path):
        if isinstance(path, (list, tuple)):
            return [law.LocalFileTarget(self.local_path(p)) for p in path]

        return law.LocalFileTarget(self.local_path(path))

    def temporarylocal_target(self, *path):
        return law.LocalFileTarget(self.temporary_local_path(*path))

    # Path of remote targets. Composed from the production_tag,
    #   the name of the task and an additional path if provided.
    #   The wlcg_path will be prepended for WLCGFileTargets
    def remote_path(self, *path):
        parts = (self.production_tag,) + (self.__class__.__name__,) + path
        return os.path.join(*parts)

    def remote_target(self, path):
        if self.is_local_output:
            return self.local_target(path)

        if isinstance(path, (list, tuple)):
            return [law.wlcg.WLCGFileTarget(self.remote_path(p)) for p in path]

        return law.wlcg.WLCGFileTarget(self.remote_path(path))

    def convert_env_to_dict(self, env):
        my_env = {}
        for line in env.splitlines():
            if line.find(" ") < 0:
                try:
                    key, value = line.split("=", 1)
                    my_env[key] = value
                except ValueError:
                    pass
        return my_env

    # Function to apply a source-script and get the resulting environment.
    #   Anything apart from setting paths is likely not included in the resulting envs.
    def set_environment(self, sourcescript, silent=False):
        if not silent:
            console.log(f"with source script: {sourcescript}")
        if isinstance(sourcescript, str):
            sourcescript = [sourcescript]
        source_command = [
            f"source {_sourcescript};" for _sourcescript in sourcescript
        ] + ["env"]
        source_command_string = " ".join(source_command)
        code, out, error = interruptable_popen(
            source_command_string,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # rich_console=console
        )
        if code != 0:
            console.log(f"source returned non-zero exit status {code}")
            console.log(f"Error: {error}")
            raise Exception("source failed")
        my_env = self.convert_env_to_dict(out)
        return my_env

    # Run a bash command
    #   Command can be composed of multiple parts (interpreted as seperated by a space).
    #   A sourcescript can be provided that is called by set_environment the resulting
    #       env is then used for the command
    #   The command is run as if it was called from run_location
    #   With "collect_out" the output of the run command is returned
    def run_command(
        self,
        command=[],
        sourcescript=[],
        run_location=None,
        collect_out=False,
        silent=False,
    ):
        if command:
            if isinstance(command, str):
                command = [command]
            logstring = f"Running {command}"
            if run_location:
                logstring += f" from {run_location}"
            if not silent:
                console.log(logstring)
            if sourcescript:
                run_env = self.set_environment(sourcescript, silent)
            else:
                run_env = None
            if not silent:
                console.rule()
            code, out, error = interruptable_popen(
                " ".join(command),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=run_env,
                cwd=run_location,
            )
            if not silent:
                console.log(f"Output: {out}")
                console.rule()
            if not silent or code != 0:
                console.log(f"Error: {error}")
                console.rule()
            if code != 0:
                console.log(f"Error when running {list(command)}.")
                console.log(f"Command returned non-zero exit status {code}.")
                raise Exception(f"{list(command)} failed")
            else:
                if not silent:
                    console.log("Command successful.")
            if collect_out:
                return out
        else:
            raise Exception("No command provided.")

    def run_command_readable(self, command=[], sourcescript=[], run_location=None):
        """
        This can be used, to run a command, where you want to read the output while the command is running.
        redirect both stdout and stderr to the same output.
        """
        if command:
            if isinstance(command, str):
                command = [command]
            if sourcescript:
                run_env = self.set_environment(sourcescript)
            else:
                run_env = None
            logstring = f"Running {command}"
            if run_location:
                logstring += f" from {run_location}"
            console.rule()
            console.log(logstring)
            try:
                p = subprocess.Popen(
                    " ".join(command),
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=run_env,
                    cwd=run_location,
                    encoding="utf-8",
                )
                while True:
                    reads = [p.stdout.fileno(), p.stderr.fileno()]
                    ret = select.select(reads, [], [])

                    for fd in ret[0]:
                        if fd == p.stdout.fileno():
                            read = p.stdout.readline()
                            if read != "\n":
                                console.log(read.strip())
                        if fd == p.stderr.fileno():
                            read = p.stderr.readline()
                            if read != "\n":
                                console.log(read.strip())

                    if p.poll() != None:
                        break
                if p.returncode != 0:
                    raise Exception(f"Error when running {command}.")
            except Exception as e:
                raise Exception(f"Error when running {command}.")
        else:
            raise Exception("No command provided.")


class HTCondorWorkflow(Task, law.htcondor.HTCondorWorkflow):
    ENV_NAME = luigi.Parameter(description="Environment to be used in HTCondor job.")
    htcondor_accounting_group = luigi.Parameter(
        description="Accounting group to be set in Hthe TCondor job submission."
    )
    htcondor_requirements = luigi.Parameter(
        default="",
        description="Job requirements to be set in the HTCondor job submission.",
    )
    htcondor_remote_job = luigi.Parameter(
        description="Whether RemoteJob should be set in the HTCondor job submission."
    )
    htcondor_walltime = luigi.Parameter(
        description="Runtime to be set in HTCondor job submission."
    )
    htcondor_request_cpus = luigi.Parameter(
        description="Number of CPU cores to be requested in HTCondor job submission.",
        default="1",
    )
    htcondor_request_gpus = luigi.Parameter(
        default="0",
        description="Number of GPUs to be requested in HTCondor job submission. Default is none.",
    )
    htcondor_request_memory = luigi.Parameter(
        description="Amount of memory(MB) to be requested in HTCondor job submission."
    )
    htcondor_request_disk = luigi.Parameter(
        description="Amount of scratch-space(kB) to be requested in HTCondor job submission."
    )
    htcondor_universe = luigi.Parameter(
        description="Universe to be set in HTCondor job submission.",
        significant=False,
    )
    htcondor_docker_image = luigi.Parameter(
        description="Docker image to be used in HTCondor job submission.",
        default="Automatic",
    )
    bootstrap_file = luigi.Parameter(
        description="Bootstrap script to be used in HTCondor job to set up law.",
        significant=False,
    )
    additional_files = luigi.ListParameter(
        default=[],
        description="Additional files to be included in the job tarball. Will be unpacked in the run directory",
        significant=False,
    )
    remote_source_script = luigi.Parameter(
        description="Script to source environment in remote jobs. Leave empty if not needed. Defaults to use with docker images",
        default="source /opt/conda/bin/activate env",
        significant=False,
    )

    # Use proxy file located in $X509_USER_PROXY or /tmp/x509up_u$(id) if empty
    htcondor_user_proxy = law.wlcg.get_vomsproxy_file()

    # Do not propagate certain parameters via the ".req()" methode
    exclude_set = {
        "ENV_NAME",
        "htcondor_requirements",
        "htcondor_remote_job",
        "htcondor_walltime",
        "htcondor_request_cpus",
        "htcondor_request_gpus",
        "htcondor_request_memory",
        "htcondor_request_disk",
        "htcondor_universe",
        "htcondor_docker_image",
        "additional_files",
        "workflow",
    }
    exclude_params_req = (
        Task.exclude_params_req
        | law.htcondor.HTCondorWorkflow.exclude_params_req
        | exclude_set
    )

    def get_submission_os(self):
        # function to check, if running on centos7, rhel9 or Ubuntu22
        # Other OS are not permitted
        # based on this, the correct docker image is chosen, overwriting the htcondor_docker_image parameter
        # check if lsb_release is installed, if not, use the information from /etc/os-release
        # Please note that this selection can be somewhat unstable. Modify if neccessary.
        try:
            distro = (
                subprocess.check_output(
                    "lsb_release -i | cut -f2", stderr=subprocess.STDOUT
                )
                .decode()
                .replace("Linux", "")
                .replace("linux", "")
                .replace(" ", "")
                .strip()
            )
            os_version = (
                subprocess.check_output(
                    "lsb_release -r | cut -f2", stderr=subprocess.STDOUT
                )
                .decode()
                .strip()
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            distro = (
                subprocess.check_output(
                    "cat /etc/os-release | grep '^NAME=' | cut -f2 -d='' | tr -d '\"'",
                    shell=True,
                )
                .decode()
                .replace("Linux", "")
                .replace("linux", "")
                .replace(" ", "")
                .strip()
            )
            os_version = (
                subprocess.check_output(
                    "cat /etc/os-release | grep '^VERSION_ID=' | cut -f2 -d='' | tr -d '\"'",
                    shell=True,
                )
                .decode()
                .strip()
            )

        image_name = None

        if distro == "CentOS":
            if os_version[0] == "7":
                image_name = "centos7"
        elif distro in ("RedHatEnterprise", "Alma"):
            if os_version[0] == "9":
                image_name = "rhel9"
        elif distro == "Ubuntu":
            if os_version[0:2] == "22":
                image_name = "ubuntu2204"
        else:
            raise Exception(
                f"Unknown OS {distro} {os_version}, KingMaker will not run without changes"
            )
        image_hash = os.getenv("IMAGE_HASH")
        image = f"ghcr.io/kit-cms/kingmaker-images-{image_name}-{str(self.ENV_NAME).lower()}:main_{image_hash}"
        # print(f"Running on {distro} {os_version}, using image {image}")
        return image

    def htcondor_output_directory(self):
        return law.LocalDirectoryTarget(self.local_path("job_files"))

    def htcondor_log_directory(self):
        log_path = os.path.join(self.htcondor_output_directory().abspath, "logs")
        return law.LocalDirectoryTarget(log_path)

    def htcondor_create_job_file_factory(self):
        path = self.htcondor_output_directory().abspath
        factory = super().htcondor_create_job_file_factory(dir=path, mkdtemp=False)
        console.log(f"HTCondor job directory is: {path}")
        return factory

    def htcondor_bootstrap_file(self):
        hostfile = self.bootstrap_file
        return law.util.rel_path(__file__, hostfile)

    def htcondor_job_config(self, config, job_num, branches):
        domain_name = str(socket.getfqdn())

        if domain_name.endswith("cern.ch"):
            domain = "CERN"
        elif domain_name.endswith(
            ("etp.kit.edu", "darwin.kit.edu", "gridka.de", "bwforcluster")
        ):
            domain = "ETP"
        else:
            print("Unknown domain, default to CERN lxplus settings.")
            domain = "CERN"

        analysis_name = os.getenv("ANA_NAME")
        task_name = self.__class__.__name__

        # Write job config file
        log_base_path = self.htcondor_log_directory().abspath
        config.log = os.path.join(log_base_path, "Log_$(JobId).txt")
        config.custom_log_file = os.path.join("All_$(JobId).txt")
        # config.stdout = "Out_$(JobId).txt"
        # config.stderr = "Err_$(JobId).txt"
        # config.custom_content.append(("stream_error", "True"))  # Remove before commit. Streamed files will end up in
        # config.custom_content.append(("stream_output", "True"))  # `self.htcondor_create_job_file_factory().dir
        if self.htcondor_requirements:
            config.custom_content.append(("Requirements", self.htcondor_requirements))
        config.custom_content.append(("universe", self.htcondor_universe))
        if self.htcondor_docker_image != "Automatic":
            config.custom_content.append(("docker_image", self.htcondor_docker_image))
        else:
            config.custom_content.append(("docker_image", self.get_submission_os()))
        if domain == "ETP":
            config.custom_content.append(
                ("accounting_group", self.htcondor_accounting_group)
            )
            config.custom_content.append(("+RemoteJob", self.htcondor_remote_job))
            config.custom_content.append(("+RequestWalltime", self.htcondor_walltime))
        elif domain == "CERN":
            config.custom_content.append(("+MaxRuntime", self.htcondor_walltime))
        config.custom_content.append(("x509userproxy", self.htcondor_user_proxy))
        config.custom_content.append(("request_cpus", self.htcondor_request_cpus))
        # Only include "request_gpus" if any are requested, as nodes with GPU are otherwise excluded
        if float(self.htcondor_request_gpus) > 0:
            config.custom_content.append(("request_gpus", self.htcondor_request_gpus))
        config.custom_content.append(("RequestMemory", self.htcondor_request_memory))
        config.custom_content.append(("RequestDisk", self.htcondor_request_disk))

        # Ensure tarball dir exists
        if not os.path.exists(f"tarballs/{self.production_tag}"):
            os.makedirs(f"tarballs/{self.production_tag}")
        # Repack tarball if it is not available remotely

        if self.is_local_output:
            tarball = law.LocalFileTarget(
                os.path.join(
                    self.production_tag,
                    self.__class__.__name__,
                    "job_tarball",
                    "processor.tar.gz",
                ),
                fs=law.LocalFileSystem(
                    None,
                    base=f"{os.path.expandvars(self.local_output_path)}",
                ),
            )
        else:
            tarball = law.wlcg.WLCGFileTarget(
                os.path.join(
                    self.production_tag,
                    self.__class__.__name__,
                    "job_tarball",
                    "processor.tar.gz",
                )
            )
        if not tarball.exists():
            # Make new tarball
            # get absolute path to tarball dir
            tarball_dir = os.path.abspath(f"tarballs/{self.production_tag}")
            tarball_local = law.LocalFileTarget(
                os.path.join(
                    tarball_dir,
                    task_name,
                    "processor.tar.gz",
                )
            )
            print(
                f"Uploading framework tarball from {tarball_local.path} to {tarball.path}"
            )
            tarball_local.parent.touch()
            # Create tarball containing:
            #   The processor directory, thhe relevant config files, law
            #   and any other files specified in the additional_files parameter
            command = [
                "tar",
                "--exclude",
                "*.pyc",
                "--exclude",
                "*.git",
                "-czf",
                tarball_local.path,
                "processor",
                f"lawluigi_configs/{analysis_name}_luigi.cfg",
                f"lawluigi_configs/{analysis_name}_law.cfg",
                "law",
            ] + list(self.additional_files)
            code, out, error = interruptable_popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # rich_console=console
            )
            if code != 0:
                console.log(f"Error when taring job {error}")
                console.log(f"Output: {out}")
                console.log(f"tar returned non-zero exit status {code}")
                console.rule()
                os.remove(tarball_local.path)
                raise Exception("tar failed")
            else:
                console.rule("Successful tar of framework tarball !")
            # Copy new tarball to remote
            tarball.parent.touch()
            tarball.copy_from_local(src=tarball_local.path)
            console.rule("Framework tarball uploaded!")
        config.render_variables["USER"] = self.local_user
        config.render_variables["ANA_NAME"] = os.getenv("ANA_NAME")
        config.render_variables["ENV_NAME"] = self.ENV_NAME
        config.render_variables["TAG"] = self.production_tag
        config.render_variables["NTHREADS"] = self.htcondor_request_cpus
        config.render_variables["LUIGIPORT"] = os.getenv("LUIGIPORT")
        config.render_variables["SOURCE_SCRIPT"] = self.remote_source_script

        config.render_variables["IS_LOCAL_OUTPUT"] = str(self.is_local_output)
        if not self.is_local_output:
            config.render_variables["TARBALL_PATH"] = (
                os.path.expandvars(self.wlcg_path) + tarball.path
            )
        else:
            config.render_variables["TARBALL_PATH"] = (
                os.path.expandvars(self.local_output_path) + tarball.path
            )
        config.render_variables["LOCAL_TIMESTAMP"] = startup_time
        config.render_variables["LOCAL_PWD"] = startup_dir
        # only needed for $ANA_NAME=ML_train see setup.sh line 207
        if os.getenv("MODULE_PYTHONPATH"):
            config.render_variables["MODULE_PYTHONPATH"] = os.getenv(
                "MODULE_PYTHONPATH"
            )
        return config

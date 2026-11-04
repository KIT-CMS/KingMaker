import os
import json
import shlex
import fcntl
import shutil
import hashlib
import contextlib
import law
import luigi
import yaml
from rich.table import Table
from framework import console, Task, HTCondorWorkflow
from CROWNBase import ProduceBase, CROWNExecuteBase, config_modules
from CROWNMain import CROWNRun
from CROWNFriend import CROWNFriend
from ProduceNtuples import ProduceNtuples
from helpers.helpers import create_abspath
from helpers.python_friend_utils import (
    PythonFriendConfigError,
    check_outputs,
    get_evaluations,
    load_friend_config,
    resolve_inputs,
)

PAYLOAD_SCRIPT = os.path.join("processor", "tasks", "scripts", "run_python_friend.py")
SENSITIVITY_SCRIPT = os.path.join(
    "processor", "tasks", "scripts", "python_friend_sensitivity.py"
)
PLOT_SCRIPT = os.path.join(
    "processor", "tasks", "scripts", "plot_python_friend_sensitivity.py"
)
PLOT_FORMATS = ["pdf", "png"]
STAGING_DIR = "python_friend_staging"
# set by HTCondor (and the container runtime) to the GPUs assigned to the job
GPU_ENV_VARS = ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "_CONDOR_AssignedGPUs")


def target_uri(target):
    """
    Path that uproot (local) or XRootD (remote) can open directly.
    """
    if isinstance(target, law.LocalFileTarget):
        return target.abspath
    return target.uri()


def ntuple_files(collection):
    """
    {(scope, basename): target} of all root files in the output directories of a
    CROWNRun/CROWNFriend collection, sorted by file number. The directories are listed
    instead of using the collection's targets: those are recomputed from the current
    dataset configuration and files_per_task, which can differ from the ones of the
    production (e.g. 17 instead of the 85 files written for a sample).
    """
    directories = {}
    for target in collection._flat_target_list:
        if target.path.endswith(".root"):
            directories.setdefault(target.path.split("/")[-2], target.parent)
    files = {}
    for scope, directory in sorted(directories.items()):
        names = directory.listdir(pattern="*.root", type="f")
        for name in sorted(names, key=lambda n: int(n[: -len(".root")].rsplit("_", 1)[1])):
            files[(scope, name)] = directory.child(name, type="f")
    return files


def model_paths(path):
    """
    All files of a model, which can be a single file or a directory.
    """
    if os.path.isdir(path):
        return sorted(
            os.path.join(root, name)
            for root, _, names in os.walk(path)
            for name in names
        )
    return [path] if os.path.exists(path) else []


class PythonFriendParams:
    """
    Parameters shared by all python friend tasks.
    """

    python_friend_config = luigi.Parameter(
        description="Python friend config in CROWN/analysis_configurations/<analysis>/, without '.py'."
    )
    friend_tag = luigi.Parameter(
        description="Tag of the produced friend trees, used in the output paths."
    )
    allow_empty_values = luigi.BoolParameter(
        default=False,
        description="Fill inputs missing in the ntuples with the config's empty_values. Not for production.",
    )
    requires_friends = luigi.ListParameter(
        default=[],
        description="CROWN friend configs whose friend trees are used as additional inputs.",
    )
    friend_mapping = luigi.DictParameter(
        default={},
        description="Friend mapping of the CROWN friends in requires_friends.",
    )

    def crown_path(self):
        return self.KingMaker_path("CROWN")

    def analysis_dir(self, crown_path=None):
        return os.path.join(
            crown_path or self.crown_path(),
            "analysis_configurations",
            str(self.analysis),
        )

    def load_config(self, crown_path=None):
        return load_friend_config(
            crown_path or self.crown_path(), self.analysis, self.python_friend_config
        )

    def evaluations(self, module, scope):
        return get_evaluations(module, self.era, self.sample_type, scope, self.shifts)[
            0
        ]

    def model_files(self, module):
        """
        Local model files used by any evaluation of this era/sample_type, relative to
        the analysis directory. Remote models (root://...) are fetched by the jobs.
        """
        models = set()
        for scope in self.scopes:
            for evaluation in self.evaluations(module, scope):
                if "://" not in evaluation["model"]:
                    models.add(evaluation["model"])
        return sorted(models)

    def source_hash(self):
        """
        Hash of the config, its relative imports and the model files. Part of the check
        output and the job tarball path, so changing any of them re-runs the check and
        repacks the tarball.
        """
        if getattr(self, "_source_hash", None) is None:
            module = self.load_config()
            analysis_dir = self.analysis_dir()
            digest = hashlib.sha1()
            for path in sorted(
                config_modules(analysis_dir, str(self.python_friend_config))
            ):
                with open(path, "rb") as f:
                    digest.update(f.read())
            for model in self.model_files(module):
                # models can be directories, e.g. a tensorflow SavedModel; missing
                # models are reported by the input check, not here
                for path in model_paths(os.path.join(analysis_dir, model)):
                    stat = os.stat(path)
                    digest.update(f"{path}:{stat.st_size}:{stat.st_mtime}".encode())
            self._source_hash = digest.hexdigest()[:12]
        return self._source_hash

    def friend_input_requirements(self):
        requirements = {}
        for friend_config in self.requires_friends:
            if friend_config not in self.friend_mapping:
                raise Exception(f"Friend config {friend_config} not found in mapping")
            requirements[f"CROWNFriend_{friend_config}"] = CROWNFriend.req(
                self, friend_config=friend_config
            )
        return requirements

    def payload_command(
        self,
        crown_path,
        scope,
        inputfile,
        friend_files,
        outputfile,
        quantities_map=None,
        max_events=-1,
        allow_empty_values=False,
        nthreads=1,
    ):
        """
        Command running the payload on one ntuple, see ml_command().
        """
        args = [
            "python3",
            os.path.abspath(PAYLOAD_SCRIPT),
            "--crown-path",
            crown_path,
            "--analysis",
            self.analysis,
            "--config",
            self.python_friend_config,
            "--era",
            self.era,
            "--sample-type",
            self.sample_type,
            "--scope",
            scope,
            "--shifts",
            self.shifts,
            "--input",
            inputfile,
            "--output",
            outputfile,
            "--max-events",
            str(max_events),
        ]
        for friend_file in friend_files:
            args += ["--friend", friend_file]
        if quantities_map:
            args += ["--quantities-map", quantities_map]
        if allow_empty_values:
            args.append("--allow-empty-values")
        return self.ml_command(args, nthreads)

    def effective_ml_setup_script(self):
        return self.ml_setup_script

    def ml_command(self, args, nthreads=1):
        """
        Command running args in a clean environment with the ML setup script (LCG view)
        sourced, so the conda/container python of law does not leak in.
        """
        env = {
            "HOME": os.environ.get("HOME", os.getcwd()),
            "PATH": "/usr/bin:/bin",
            "USER": os.environ.get("USER", self.local_user),
            "X509_USER_PROXY": os.environ.get(
                "X509_USER_PROXY", law.wlcg.get_vomsproxy_file()
            ),
            "X509_CERT_DIR": "/cvmfs/grid.cern.ch/etc/grid-security/certificates",
            "X509_VOMS_DIR": "/cvmfs/grid.cern.ch/etc/grid-security/vomsdir",
            # never use more threads than cores requested from the batch system
            "PYTHON_FRIEND_NTHREADS": str(nthreads),
            "OMP_NUM_THREADS": str(nthreads),
            "MKL_NUM_THREADS": str(nthreads),
            "OPENBLAS_NUM_THREADS": str(nthreads),
            "TF_NUM_INTRAOP_THREADS": str(nthreads),
            "TF_NUM_INTEROP_THREADS": "1",
        }
        # keep the GPUs HTCondor assigned to the job, else it would see every GPU of the node
        for name in GPU_ENV_VARS:
            if name in os.environ:
                env[name] = os.environ[name]
        inner = f"source {shlex.quote(str(self.effective_ml_setup_script()))} && {shlex.join(args)}"
        command = ["env", "-i"] + [f"{k}={v}" for k, v in env.items()]
        command += ["bash", "-c", inner]
        return [shlex.quote(part) for part in command]


class PythonFriend(PythonFriendParams, CROWNExecuteBase):
    """
    Evaluate the models of a python friend config on the CROWN ntuples of one sample,
    one branch per ntuple file and scope, like CROWNFriend.
    """

    ml_setup_script = luigi.Parameter(
        significant=False,
        description="Script sourced to set up the ML environment of the payload, e.g. an LCG view.",
    )
    ml_setup_script_gpu = luigi.Parameter(
        significant=False,
        default="",
        description="ML environment used instead of ml_setup_script when htcondor_request_gpus > 0, e.g. a _cuda LCG view.",
    )

    def use_gpus(self):
        return float(self.htcondor_request_gpus) > 0

    def effective_ml_setup_script(self):
        if not self.use_gpus():
            return self.ml_setup_script
        if not self.ml_setup_script_gpu:
            raise ValueError(
                "htcondor_request_gpus > 0 needs ml_setup_script_gpu (e.g. a _cuda LCG view) in [PythonFriend]"
            )
        return self.ml_setup_script_gpu

    def workflow_requires(self):
        requirements = {}
        requirements["ntuples"] = CROWNRun.req(self)
        requirements.update(self.friend_input_requirements())
        # checks all needed columns before any job is submitted; not inside the jobs,
        # where the branch map only needs the ntuples and there is no CROWN checkout
        if "LAW_JOB_INIT_DIR" not in os.environ:
            requirements["input_check"] = PythonFriendInputCheck.req(self)
        return requirements

    def create_branch_map(self):
        inputs = self.workflow_input()
        ntuples = ntuple_files(inputs["ntuples"]["collection"])
        friends = {
            friend_config: ntuple_files(
                inputs[f"CROWNFriend_{friend_config}"]["collection"]
            )
            for friend_config in self.requires_friends
        }
        branch_map = {}
        for (scope, basename), target in ntuples.items():
            if scope not in self.scopes:
                continue
            friend_inputs = []
            for friend_config, files in friends.items():
                if (scope, basename) not in files:
                    raise Exception(
                        f"No {friend_config} friend for {scope}/{basename} of {self.nick}"
                    )
                friend_inputs.append(target_uri(files[(scope, basename)]))
            branch_map[len(branch_map)] = {
                "scope": scope,
                "nick": self.nick,
                "era": self.era,
                "sample_type": self.sample_type,
                "inputfile": target_uri(target),
                "friend_inputs": friend_inputs,
                "filecounter": int(basename[: -len(".root")].rsplit("_", 1)[1]),
            }
        return branch_map

    def output(self):
        return self.branch_output(self.branch_data)

    def workflow_complete(self):
        # same targets as the workflow collection, without instantiating every branch task
        targets = {
            b: self.branch_output(data) for b, data in self.get_branch_map().items()
        }
        return self.output_collection_cls(
            targets, threshold=self.workflow_proxy.threshold(len(targets))
        ).complete()

    def branch_output(self, branch_data):
        path = "{tag}/{era}/{nick}/{scope}".format(tag=self.friend_tag, **branch_data)
        files = [f"{path}/{branch_data['nick']}_{branch_data['filecounter']}.root"]
        # quantities_map json for each scope only needs to be created once per sample
        if branch_data["filecounter"] == 0:
            files.append(
                "{path}/{era}_{nick}_{scope}_quantities_map.json".format(
                    path=path, **branch_data
                )
            )
        return self.remote_target(files)

    def remote_path(self, *path):
        # friend trees go next to the CROWN friends; job files, logs and tarballs
        # go to PythonFriendBuild (job_tarball_task_dir)
        return os.path.join(self.production_tag, "CROWNFriends", *path)

    def remote_target(self, path):
        if self.is_local_output:
            return [
                law.LocalFileTarget(
                    os.path.join(self.local_output_path, self.remote_path(p))
                )
                for p in path
            ]
        return super().remote_target(path)

    def htcondor_output_directory(self):
        # job files and logs go next to the job tarballs, in PythonFriendBuild
        return law.LocalDirectoryTarget(
            os.path.join(
                os.path.dirname(self.local_path()),
                self.job_tarball_task_dir(),
                "htcondor_files",
                "python_friends",
                str(self.friend_tag),
                self.nick,
            )
        )

    def job_tarball_task_dir(self):
        return "PythonFriendBuild"

    def job_tarball_subdir(self):
        return os.path.join("python_friends", str(self.friend_tag), self.source_hash())

    def staging_dir(self):
        # no hash here: the jobs have to find this path without the CROWN checkout
        return os.path.join(STAGING_DIR, str(self.friend_tag))

    @contextlib.contextmanager
    def staged_python_friend_source(self):
        """
        Ship the config, the modules it imports relatively, CROWN's code_generation
        (configs may use its quantities) and the local model files with the job
        tarball, keeping the CROWN directory layout so the same imports work in the job.
        The lock serializes the tasks of different samples sharing this directory.
        """
        crown_path = self.crown_path()
        staging_dir = os.path.abspath(self.staging_dir())
        os.makedirs(STAGING_DIR, exist_ok=True)
        with open(os.path.join(STAGING_DIR, ".lock"), "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                if os.path.exists(staging_dir):
                    shutil.rmtree(staging_dir)
                analysis_dir = self.analysis_dir()
                files = config_modules(analysis_dir, str(self.python_friend_config))
                files |= {
                    os.path.join(analysis_dir, model)
                    for model in self.model_files(self.load_config())
                }
                for src in files:
                    dst = os.path.join(staging_dir, os.path.relpath(src, crown_path))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                shutil.copytree(
                    os.path.join(crown_path, "code_generation"),
                    os.path.join(staging_dir, "code_generation"),
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
                rel_staging_dir = os.path.relpath(staging_dir)
                if rel_staging_dir not in self.additional_files:
                    self.additional_files = list(self.additional_files) + [
                        rel_staging_dir
                    ]
                yield
            finally:
                shutil.rmtree(staging_dir, ignore_errors=True)
                fcntl.flock(lock_file, fcntl.LOCK_UN)

    def htcondor_job_config(self, config, job_num, branches):
        # fails before submission if GPUs are requested without a GPU view
        self.effective_ml_setup_script()
        with self.staged_python_friend_source():
            config = HTCondorWorkflow.htcondor_job_config(
                self, config, job_num, branches
            )
        config.custom_content.append(
            (
                "JobBatchName",
                f"{self.nick}-{self.analysis}-{self.friend_tag}-{self.production_tag}",
            )
        )
        return config

    def modify_polling_status_line(self, status_line):
        status_line_pattern = f"{self.nick} (Analysis: {self.analysis} PythonFriend: {self.python_friend_config} Tag: {self.friend_tag})"
        return f"{status_line} - {law.util.colored(status_line_pattern, color='light_cyan')}"

    def run(self):
        outputs = self.output()
        branch_data = self.branch_data
        scope = branch_data["scope"]
        # htcondor jobs only have the staged copy of the config, local branches the checkout
        if self.effective_workflow == "local":
            crown_path = self.crown_path()
        else:
            crown_path = os.path.abspath(self.staging_dir())
        _workdir = os.path.abspath(
            os.path.join("workdir", f"{self.production_tag}_{self.friend_tag}")
        )
        create_abspath(_workdir)
        local_output = os.path.join(_workdir, outputs[0].basename)
        local_quantities_map = None
        if branch_data["filecounter"] == 0:
            local_quantities_map = os.path.join(_workdir, outputs[1].basename)
        console.rule(f"Starting PythonFriend {self.friend_tag}")
        console.log(
            f"inputfile(s) {branch_data['inputfile']} {branch_data['friend_inputs']}"
        )
        console.log(f"outputfile {local_output}")
        console.log(
            f"ML setup script {self.effective_ml_setup_script()}"
            + (f" (GPUs: {os.environ.get('CUDA_VISIBLE_DEVICES', 'not set')})" if self.use_gpus() else "")
        )
        command = self.payload_command(
            crown_path=crown_path,
            scope=scope,
            inputfile=branch_data["inputfile"],
            friend_files=branch_data["friend_inputs"],
            outputfile=local_output,
            quantities_map=local_quantities_map,
            allow_empty_values=self.allow_empty_values,
            nthreads=self.htcondor_request_cpus,
        )
        self.run_command_readable(command)
        outputs[0].copy_from_local(local_output)
        if local_quantities_map is not None:
            outputs[1].copy_from_local(local_quantities_map)
        console.rule("Finished PythonFriend")


class PythonFriendInputCheck(PythonFriendParams, Task):
    """
    Opens the first ntuple (and required friend) file of each scope of a sample and
    checks that every column needed by the python friend config exists, before any
    PythonFriend job is submitted.
    """

    scopes = luigi.ListParameter()
    shifts = luigi.Parameter()
    all_sample_types = luigi.ListParameter(significant=False)
    all_eras = luigi.ListParameter(significant=False)
    required_build_combinations = luigi.ListParameter(significant=False)
    nick = luigi.Parameter()
    sample_type = luigi.Parameter()
    era = luigi.Parameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()

    def requires(self):
        requirements = {"ntuples": CROWNRun.req(self)}
        requirements.update(self.friend_input_requirements())
        return requirements

    def output(self):
        # the hash re-triggers the check whenever config or models change
        empty = "_allow_empty" if self.allow_empty_values else ""
        return self.local_target(
            f"{self.friend_tag}/{self.era}/{self.nick}/input_check_{self.source_hash()}{empty}.json"
        )

    def first_files(self, scope):
        """
        The first ntuple of a scope and the matching files of the required friends.
        """
        ntuples = ntuple_files(self.input()["ntuples"]["collection"])
        keys = sorted(
            (key for key in ntuples if key[0] == scope),
            key=lambda key: int(key[1][: -len(".root")].rsplit("_", 1)[1]),
        )
        if not keys:
            raise Exception(f"No ntuple found for scope {scope} of {self.nick}")
        files = [target_uri(ntuples[keys[0]])]
        for friend_config in self.requires_friends:
            friends = ntuple_files(
                self.input()[f"CROWNFriend_{friend_config}"]["collection"]
            )
            if keys[0] not in friends:
                raise Exception(f"No {friend_config} friend for {keys[0]}")
            files.append(target_uri(friends[keys[0]]))
        return files

    def model_exists(self, model):
        if "://" in model:
            from XRootD.client import FileSystem

            server, path = model.split("://", 1)[1].split("/", 1)
            status, _ = FileSystem(f"root://{server}").stat("/" + path.lstrip("/"))
            return status.ok
        return os.path.exists(os.path.join(self.analysis_dir(), model))

    def check_scope(self, module, scope):
        """
        Returns (errors, warnings, empty, available) for one scope.
        errors/warnings: lists of rows, empty: rows of inputs filled with empty values.
        """
        import uproot

        errors, warnings, empty = [], [], []
        available, entries = set(), {}
        for path in self.first_files(scope):
            console.log(f"Reading columns of {path}")
            with uproot.open(path) as f:
                tree = f["ntuple"]
                available |= set(tree.keys())
                entries[path] = tree.num_entries
        if len(set(entries.values())) > 1:
            errors.append((scope, "", "", f"different numbers of entries: {entries}"))
        try:
            evaluations = self.evaluations(module, scope)
        except PythonFriendConfigError as e:
            return [(scope, "", "", str(e))], warnings, empty, available
        for message in check_outputs(evaluations, available):
            errors.append((scope, "", "", message))
        for evaluation in evaluations:
            shift = evaluation["shift"]
            if not self.model_exists(evaluation["model"]):
                errors.append(
                    (scope, shift, "", f"model {evaluation['model']} not found")
                )
            result = resolve_inputs(evaluation, available, self.allow_empty_values)
            for model_input, column, suggestions in result["errors"]:
                hint = f"close matches: {', '.join(suggestions)}" if suggestions else ""
                if not self.allow_empty_values and (
                    model_input in evaluation["empty_values"]
                    or column in evaluation["empty_values"]
                ):
                    hint = "has an empty value, but --allow-empty-values is not set"
                errors.append(
                    (scope, shift, model_input, f"missing column '{column}' {hint}")
                )
            for model_input, (column, value) in result["empty"].items():
                empty.append((scope, shift, model_input, column, repr(value)))
            for message in result["warnings"]:
                warnings.append((scope, shift, "", message))
        return errors, warnings, empty, available

    def print_table(self, title, columns, rows, style):
        table = Table(title=title, title_style=style)
        for column in columns:
            table.add_column(column, justify="left")
        for row in rows:
            table.add_row(*[str(entry) for entry in row])
        console.log(table)

    def run(self):
        console.rule(f"Checking inputs of python friend {self.python_friend_config}")
        module = self.load_config()
        errors, warnings, empty, report = [], [], [], {}
        for scope in self.scopes:
            scope_errors, scope_warnings, scope_empty, available = self.check_scope(
                module, scope
            )
            errors += scope_errors
            warnings += scope_warnings
            empty += scope_empty
            report[scope] = {"available_columns": len(available)}
        if warnings:
            self.print_table(
                "Python friend notes",
                ["scope", "shift", "model input", "note"],
                warnings,
                "bold blue",
            )
        if empty:
            self.print_table(
                "WARNING: inputs filled with empty values (not for production!)",
                ["scope", "shift", "model input", "missing column", "fill value"],
                empty,
                "bold yellow",
            )
        if errors:
            self.print_table(
                f"Python friend input check failed for {self.nick}",
                ["scope", "shift", "model input", "problem"],
                errors,
                "bold red",
            )
            raise Exception(
                f"Input check of python friend {self.python_friend_config} failed for {self.nick}, no jobs submitted"
            )
        console.log(f"All inputs of {self.python_friend_config} found for {self.nick}")
        report["empty_values"] = empty
        report["notes"] = warnings
        self.output().parent.touch()
        self.output().dump(report, formatter="json")


class PythonFriendLocalTest(PythonFriendParams, Task):
    """
    Evaluate the python friend config locally on the first --max-events events of the
    first ntuple of each scope (or of --test-file) and print a summary of the outputs.
    Nothing is submitted and the outputs only go to the local data directory.
    """

    scopes = luigi.ListParameter()
    shifts = luigi.Parameter()
    # only needed to require the ntuples, derived from era/sample_type if not given
    all_sample_types = luigi.ListParameter(default=[], significant=False)
    all_eras = luigi.ListParameter(default=[], significant=False)
    required_build_combinations = luigi.ListParameter(default=[], significant=False)
    nick = luigi.Parameter()
    sample_type = luigi.Parameter()
    era = luigi.Parameter()
    analysis = luigi.Parameter()
    config = luigi.Parameter()
    ml_setup_script = luigi.Parameter(significant=False)
    max_events = luigi.IntParameter(default=1000)
    allow_empty_values = luigi.BoolParameter(
        default=True,
        description="Fill missing inputs with the config's empty_values (warned about).",
    )
    test_file = luigi.Parameter(
        default="",
        description="Use this ntuple instead of the sample's CROWNRun output (only one scope).",
    )
    test_friend_files = luigi.ListParameter(
        default=[], description="Friend files belonging to --test-file."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.all_eras:
            self.all_eras = [self.era]
        if not self.all_sample_types:
            self.all_sample_types = [self.sample_type]
        if not self.required_build_combinations:
            self.required_build_combinations = [[self.sample_type, self.era]]

    def requires(self):
        if self.test_file:
            return {}
        return {"input_check": PythonFriendInputCheck.req(self)}

    def output(self):
        # the source hash makes a changed config or model rerun the test
        source_hash = self.source_hash()
        return {
            scope: self.local_target(
                f"{self.friend_tag}/{self.era}/{self.nick}/{scope}/"
                f"{self.nick}_local_test_{source_hash}.root"
            )
            for scope in self.scopes
        }

    def run(self):
        if self.test_file and len(self.scopes) != 1:
            raise Exception("--test-file needs exactly one scope in --scopes")
        for scope, output in self.output().items():
            if self.test_file:
                files = [self.test_file] + list(self.test_friend_files)
            else:
                files = PythonFriendInputCheck.req(self).first_files(scope)
            output.parent.touch()
            console.rule(f"Local test of {self.python_friend_config}, scope {scope}")
            command = self.payload_command(
                crown_path=self.crown_path(),
                scope=scope,
                inputfile=files[0],
                friend_files=files[1:],
                outputfile=output.abspath,
                max_events=self.max_events,
                allow_empty_values=self.allow_empty_values,
            )
            self.run_command_readable(command)
            console.log(f"Output written to {output.abspath}")


class PythonFriendSensitivity(PythonFriendParams, Task):
    """
    Model independent sensitivity test of a python friend config: its models are
    evaluated on random inputs drawn from the config's input_ranges, and every input
    (and input group) is redrawn, or set to its empty_values, to see how much the outputs
    change. No ntuples are needed, so nothing is required or submitted. The scores are
    plotted into analysis_configurations/<analysis>/sensitivity_plots/, next to the config.
    """

    scopes = luigi.ListParameter()
    shifts = luigi.Parameter()
    era = luigi.Parameter()
    sample_type = luigi.Parameter()
    analysis = luigi.Parameter()
    ml_setup_script = luigi.Parameter(significant=False)
    n_samples = luigi.IntParameter(
        default=10_000, description="Number of random events per evaluation."
    )
    seed = luigi.IntParameter(default=0, description="Seed of the random inputs.")

    def plot_target(self, name):
        """
        Plots go next to the config, analysis_configurations/<analysis>/
        sensitivity_plots/<python friend config>/, later runs replace them.
        """
        return law.LocalFileTarget(
            os.path.join(
                self.analysis_dir(),
                "sensitivity_plots",
                str(self.python_friend_config),
                name,
            )
        )

    def plot_targets(self, name):
        return [self.plot_target(f"{name}.{ext}") for ext in PLOT_FORMATS]

    def output(self):
        # the source hash makes a changed config or model rerun the test
        source_hash = self.source_hash()
        module = self.load_config()
        # one test per era, the sample type is only stated in the plots
        prefix = str(self.era)
        outputs = {}
        for scope in self.scopes:
            plots = {}
            for evaluation in self.evaluations(module, scope):
                name = f"{prefix}_{scope}"
                if evaluation["shift"] != "nominal":
                    name += f"_{evaluation['name']}"
                plots[evaluation["name"]] = self.plot_targets(name)
            outputs[scope] = {
                "scores": self.local_target(
                    f"{self.friend_tag}/sensitivity/{self.era}/{self.sample_type}/"
                    f"{scope}_n{self.n_samples}_seed{self.seed}_{source_hash}.json"
                ),
                "plots": plots,
            }
        if len(self.scopes) > 1:
            # nominal models of all scopes in one plot
            outputs["comparison"] = self.plot_targets(f"{prefix}_scopes")
        return outputs

    def plot_command(self, scores, outputs, evaluation=None):
        args = ["python3", os.path.abspath(PLOT_SCRIPT)] + list(scores)
        if evaluation is not None:
            args += ["--evaluation", evaluation]
        args += ["--output"] + [target.abspath for target in outputs]
        return self.ml_command(args)

    def run(self):
        outputs = self.output()
        for scope in self.scopes:
            output = outputs[scope]["scores"]
            output.parent.touch()
            console.rule(
                f"Sensitivity test of {self.python_friend_config}, "
                f"{self.era} {self.sample_type} {scope}"
            )
            args = [
                "python3",
                os.path.abspath(SENSITIVITY_SCRIPT),
                "--crown-path",
                self.crown_path(),
                "--analysis",
                self.analysis,
                "--config",
                self.python_friend_config,
                "--era",
                self.era,
                "--sample-type",
                self.sample_type,
                "--scope",
                scope,
                "--shifts",
                self.shifts,
                "--n-samples",
                str(self.n_samples),
                "--seed",
                str(self.seed),
                "--output",
                output.abspath,
            ]
            self.run_command_readable(self.ml_command(args))
            console.log(f"Scores written to {output.abspath}")
            for evaluation, plots in outputs[scope]["plots"].items():
                plots[0].parent.touch()
                self.run_command_readable(
                    self.plot_command([output.abspath], plots, evaluation)
                )
        if "comparison" in outputs:
            scores = [
                f"{outputs[scope]['scores'].abspath}:{scope}" for scope in self.scopes
            ]
            self.run_command_readable(self.plot_command(scores, outputs["comparison"]))


class ProducePythonFriends(ProduceBase):
    """
    Collective task to evaluate a python (ML) friend config on the ntuples of a list of
    samples. The ntuples are required, so they are produced first if missing.
    """

    python_friend_config = luigi.Parameter()
    friend_tag = luigi.Parameter(default="")
    allow_empty_values = luigi.BoolParameter(
        default=False,
        description="Fill inputs missing in the ntuples with the config's empty_values. Not for production.",
    )
    requires_friends = luigi.Parameter(
        default="",
        description="Comma separated CROWN friend configs used as additional inputs.",
    )
    friend_mapping = luigi.Parameter(
        default="{}",
        description="Friend mapping (yaml file or dict) of the CROWN friends in requires_friends.",
    )
    local_test = luigi.BoolParameter(
        default=False,
        description="Only run PythonFriendLocalTest on the first --max-events events of each sample, nothing is submitted.",
    )
    max_events = luigi.IntParameter(default=1000, significant=False)
    sensitivity_test = luigi.BoolParameter(
        default=False,
        description="Only run PythonFriendSensitivity, a sensitivity test of the models on random inputs from the config's input_ranges, once per era (with the first simulated sample type of the list), nothing is submitted.",
    )

    def load_friend_mapping(self):
        """
        Friend mapping of the required CROWN friends, in the format of ProduceNtuples.
        """
        mapping = self.friend_mapping
        if isinstance(mapping, str):
            if os.path.isfile(mapping):
                with open(mapping) as stream:
                    mapping = yaml.safe_load(stream) or {}
            else:
                mapping = yaml.safe_load(mapping) or {}
        mapping = {key: dict(value or {}) for key, value in dict(mapping).items()}
        requires_friends = [f for f in str(self.requires_friends).split(",") if f]
        for friend_config in requires_friends:
            mapping.setdefault(friend_config, {})
        mapping = ProduceNtuples.normalize_configs(self, mapping)
        for friend_config in mapping:
            ProduceNtuples.recursive_check(
                self, mapping, friend_config, [friend_config]
            )
        return requires_friends, mapping

    def requires(self):
        friend_tag = self.friend_tag or self.python_friend_config
        requires_friends, friend_mapping = self.load_friend_mapping()
        self.sanitize_scopes()
        self.sanitize_shifts()
        if not self.silent:
            console.rule("")
            console.log(f"Production tag: {self.production_tag}")
            console.log(f"Analysis: {self.analysis}")
            console.log(f"Config: {self.config}")
            console.log(f"Python friend config: {self.python_friend_config}")
            console.log(f"Friend tag: {friend_tag}")
            console.log(f"Required CROWN friends: {requires_friends}")
            console.log(f"Shifts: {self.shifts}")
            console.log(f"Scopes: {self.scopes}")
            if self.allow_empty_values:
                console.log(
                    "[bold yellow]WARNING: --allow-empty-values is set, missing inputs are filled with constants"
                )
            console.rule("")

        data = self.set_sample_data(self.parse_samplelist(self.sample_list))
        self.silent = True

        # only build the (sample_type, era) pairs actually used by the requested samples
        required_build_combinations = sorted(
            {(info["sample_type"], info["era"]) for info in data["details"].values()}
        )
        requirements = {}
        if self.sensitivity_test:
            # no ntuples needed, one test per era, with the first simulated sample
            # type of the list (data/embedding only if there is nothing else)
            sample_types = {}
            for sample_type, era in required_build_combinations:
                sample_types.setdefault(era, []).append(sample_type)
            for era, types in sorted(sample_types.items()):
                simulated = [t for t in types if t not in ("data", "embedding")]
                sample_type = (simulated or types)[0]
                requirements[
                    f"PythonFriendSensitivity_{era}_{sample_type}_{friend_tag}"
                ] = PythonFriendSensitivity.req(
                    self,
                    era=era,
                    sample_type=sample_type,
                    friend_tag=friend_tag,
                    requires_friends=requires_friends,
                    friend_mapping=friend_mapping,
                )
            return requirements
        ProduceNtuples.preload_dataset_configs(self, data)
        task_cls = PythonFriendLocalTest if self.local_test else PythonFriend
        for samplenick, info in data["details"].items():
            requirements[f"{task_cls.__name__}_{samplenick}_{friend_tag}"] = (
                task_cls.req(
                    self,
                    nick=samplenick,
                    all_eras=data["eras"],
                    all_sample_types=data["sample_types"],
                    required_build_combinations=required_build_combinations,
                    era=info["era"],
                    sample_type=info["sample_type"],
                    nanoAOD_version=info["nanoAOD_version"],
                    friend_tag=friend_tag,
                    requires_friends=requires_friends,
                    friend_mapping=friend_mapping,
                    # the local test only warns about filled inputs
                    allow_empty_values=self.allow_empty_values or self.local_test,
                )
            )
        return requirements

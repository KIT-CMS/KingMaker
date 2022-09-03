# coding: utf-8

"""
Collection of tasks used to create training datasets and config files
for the NN trainings of the NMSSM analysis 
"""
import yaml
import os
import luigi
import law
from shutil import rmtree
from rich.console import Console
from framework import Task, HTCondorWorkflow, startup_dir
from itertools import compress
from law.target.collection import flatten_collections, NestedSiblingFileCollection
from law.task.base import WrapperTask
from ast import literal_eval
from ml_trainings.Config_merger import get_merged_config
import re

try:
    current_width = os.get_terminal_size().columns
except OSError:
    current_width = 140
console = Console(width=current_width)

# Task to create root shards for the NN training
# One shard is created for each process (like "ff" and "NMSSM_240_125_60")
# Shards are NOT shared between eras and decay channels
class CreateTrainingDataShard(HTCondorWorkflow, law.LocalWorkflow):
    # Define luigi parameters
    datashard_information = luigi.ListParameter(description="List of, tuples of process identifier and class mapping")
    process_config_dirs = luigi.ListParameter(description="List of process config dirs in which the datashard configs could be")

    # Set other variables and templates used by this class.
    files_template = "{identifier}_{training_class}_datashard_fold{fold}.root"

    # Add branch specific names to the HTCondor jobs
    def htcondor_job_config(self, config, job_num, branches):
        config = super(CreateTrainingDataShard, self).htcondor_job_config(config, job_num, branches)
        name_list = ["_".join(info + (fold,)) for info in self.datashard_information for fold in ["0","1"]]
        task_name = self.__class__.__name__
        branch_names = []
        for branch in branches:
            branch_names.append(name_list[branch])
        branch_str = "|".join(branch_names)
        config.custom_content.append(
            ("JobBatchName", f"{task_name}-{branch_str}")
        )
        return config

    # Create map for the branches of this task.
    # Each branch can be run as an individula job
    def create_branch_map(self):
        branches = [
            {
                "datashard_information": info,
                "fold": fold,
            }
            for info in self.datashard_information
            for fold in ["0", "1"]
        ]
        assert (
            branches
        ), "There are no valid branches for this set of parameters: \
            \n{}".format(
            self
        )
        return branches

    # Define output targets. Task is considerd complete if all targets are present.
    def output(self):
        identifier, training_class = self.branch_data["datashard_information"]
        file_ = self.files_template.format(
            identifier=identifier,
            training_class=training_class,
            fold=self.branch_data["fold"],
        )
        # target = self.local_target(file_)
        target = self.remote_target(file_)
        target.parent.touch()
        return target

    def run(self):
        identifier, training_class = self.branch_data["datashard_information"]
        fold = self.branch_data["fold"]
        run_loc = "sm-htt-analysis/"

        file_list = []
        for directory in self.process_config_dirs:
            tmp_file = "{}/{}.yaml".format(directory, identifier)
            if os.path.exists(tmp_file):
                file_list.append(tmp_file)
        if len(file_list) != 1:
            if len(file_list) == 0:
                print("{}.yaml not found in any dir of {}.".format(identifier, self.process_config_dirs))
            if len(file_list) > 1:
                print("{}.yaml found in more than one dir of {}.".format(identifier, self.process_config_dirs))
            raise Exception("Incorrect process config file path.")
        else:
            process_config_file = file_list[0]
        # out_dir = self.local_path("")
        out_file = self.wlcg_path + self.output().path
        out_dir = os.path.dirname(out_file)
        os.makedirs(out_dir, exist_ok=True)

        # Create datashard based on config file
        # ROOT_XRD_QUERY_READV_PARAMS=0 is necessary for streaming root files from dCache
        self.run_command(
            [
                "ROOT_XRD_QUERY_READV_PARAMS=0",
                "python",
                "ml_trainings/create_training_datashard.py",
                "--identifier {}".format(identifier),
                "--config {}".format(process_config_file),
                "--fold {}".format(fold),
                "--training-class {}".format(training_class),
                "--output-dir {}".format(out_dir),
            ],
            run_location=run_loc,
        )

# Task to run NN training (2 folds)
# One training is performed for each valid combination of:
# channel, mass, batch and fold
# The datashards are combined based on the training parameters
class RunTraining(HTCondorWorkflow, law.LocalWorkflow):
    # Define luigi parameters
    training_information = luigi.ListParameter(description="List of, tuples of training name and training config file")

    # Set other variables and templates used by this class.
    file_template_shard = "{identifier}_{training_class}_datashard_fold{fold}.root"
    file_templates = [
        "fold{fold}_keras_model.h5",
        "fold{fold}_keras_preprocessing.pickle",
        "fold{fold}_loss.pdf",
        "fold{fold}_loss.png",
        "fold{fold}_keras_architecture.json",
        "fold{fold}_keras_variables.json",
        "fold{fold}_keras_weights.h5",
        "fold{fold}_lwtnn.json",
    ]

    # Add branch specific names to the HTCondor jobs
    def htcondor_job_config(self, config, job_num, branches):
        config = super(RunTraining, self).htcondor_job_config(config, job_num, branches)
        name_list = ["_".join([info[0], fold]) for info in self.training_information for fold in ["0","1"]]
        task_name = self.__class__.__name__
        branch_names = []
        for branch in branches:
            branch_names.append(name_list[branch])
        branch_str = "|".join(branch_names)
        config.custom_content.append(
            ("JobBatchName", f"{task_name}-{branch_str}")
        )
        return config

    # Create map for the branches of this task
    def create_branch_map(self):
        branches = [
            {
                "training_information": info,
                "fold": fold,
            } 
            for info in self.training_information
            for fold in ["0", "1"]
        ]
        assert (
            branches
        ), "There are no valid branches for this set of parameters: \
            \n{}".format(
            self
        )
        return branches

    # Set prerequisites of this task:
    # All dataset shards have to be completed
    # All training config files have to be completed
    # The prerequisites are also dependant on whether all_eras is used
    def requires(self):
        # For the requested training branch

        training, config_file = self.branch_data["training_information"]

        # Replace prefix from config path
        config_file_rel = config_file.replace(startup_dir, os.getcwd())

        # Collect process identification, process, training class and config directory
        with open(config_file_rel, "r") as stream:
            training_config = yaml.safe_load(stream)
        conf = get_merged_config(training_config, training)
        ids = list(conf["parts"].keys())
        p_d = list(conf["parts"].values())
        processes = conf["processes"]
        mapped_classes = [conf["mapping"][proc] for proc in processes]
        file_list = []
        for id_, path in zip(ids, p_d):
            for process in processes:
                mapped_class = conf["mapping"][process]
                id_process = "{id}_{process}".format(
                    id=id_,
                    process=process,
                )
                file_list.append((id_process, mapped_class, path))
        idp, t_class, files = zip(*set(file_list))
        # Require Dataset-shards for all found process-training class combinations
        # List of identifier and training_class tuples
        datashard_information = list(zip(idp, t_class))
        # List of unique process config dirs
        process_config_dirs = list(set(files))
        requirements_para = {
            "datashard_information": datashard_information,
            "process_config_dirs": process_config_dirs,
        }
        requirements = {}
        requirements["CreateTrainingDataShard"] = CreateTrainingDataShard(**requirements_para)
        return requirements

    def workflow_requires(self):
        file_list = []
        # For each requested training
        for training, config_file in self.training_information:
            # Replace prefix from config path
            config_file_rel = config_file.replace(startup_dir, os.getcwd())
            
            # Collect process identification, process, training class and config directory
            with open(config_file_rel, "r") as stream:
                training_config = yaml.safe_load(stream)
            conf = get_merged_config(training_config, training)
            ids = list(conf["parts"].keys())
            p_d = list(conf["parts"].values())
            processes = conf["processes"]
            mapped_classes = [conf["mapping"][proc] for proc in processes]
            for id_, path in zip(ids, p_d):
                for process in processes:
                    mapped_class = conf["mapping"][process]
                    id_process = "{id}_{process}".format(
                        id=id_,
                        process=process,
                    )
                    file_list.append((id_process, mapped_class, path))
        # Only keep unique combinations
        datashard_information = set(file_list)
        # Check for combinations with same id, process and class, but different config_dir
        idp, t_class, files = zip(*datashard_information)
        if(len(list(zip(idp, t_class))) != len(set(zip(idp, t_class)))):
            print("Processes with the same identification and training class, but different config dirs found!")
            data_found = []
            for data in datashard_information:
                id_, t_class, file_ = data
                if (id_, t_class) in data_found:
                    print("Process {} is affected.".format((id_, t_class)))
                else:
                    data_found.append((id_, t_class))
            raise Exception("Consistency error in training config.")
        # Require Dataset-shards for all found process-training class combinations
        # List of identifier and training_class tuples
        datashard_information = list(zip(idp, t_class))
        # List of unique process config dirs
        process_config_dirs = list(set(files))
        requirements_para = {
            "datashard_information": datashard_information,
            "process_config_dirs": process_config_dirs,
        }
        requirements = {}
        requirements["CreateTrainingDataShard"] = CreateTrainingDataShard(**requirements_para)
        return requirements

    # Define output targets. Task is considerd complete if all targets are present.
    def output(self):
        t_name, t_file = self.branch_data["training_information"]
        files = [
            "/".join(
                [
                    t_name,
                    file_template.format(fold=self.branch_data["fold"]),
                ]
            )
            for file_template in self.file_templates
        ]
        targets = self.remote_targets(files)
        for target in targets:
            target.parent.touch()
        return targets

    def run(self):
        fold = self.branch_data["fold"]
        run_loc = "sm-htt-analysis"
        training_name, config_file = self.branch_data["training_information"]
        inputs = flatten_collections(self.input())
        filtered_inputs = [input_ for input_ in inputs if "_fold0.root" in input_.path]
        input_dir_list = list(set([os.path.dirname(target.path) for target in filtered_inputs]))
        if len(input_dir_list) != 1:
            if len(input_dir_list) == 0:
                print("Base directory of datashards could not be found from the task inputs.")
            if len(input_dir_list) > 1:
                print("Base directories of the datashards are not the same.")
            raise Exception("Data directory colud not be determined.")
        else:
            data_dir = self.wlcg_path + input_dir_list[0]

        out_dir = self.local_path(training_name)
        os.makedirs(out_dir, exist_ok=True)

        # Replace prefix from config path
        config_file_rel = config_file.replace(startup_dir, os.getcwd())

        # Set maximum number of threads (this number is somewhat inaccurate
        # as TensorFlow only abides by it for some aspects of the training)
        if os.getenv("OMP_NUM_THREADS"):
            max_threads = os.getenv("OMP_NUM_THREADS")
        else:
            max_threads = 12
        # Run NN training and save the model,
        # the preprocessing object and some images of the trasining process
        self.run_command(
            command=[
                "python",
                "ml_trainings/Tensorflow_training.py",
                "--config-file {}".format(config_file_rel),
                "--training-name {}".format(training_name),
                "--data-dir {}".format(data_dir),
                "--fold {}".format(fold),
                "--output-dir {}".format(out_dir),
            ],
            run_location=run_loc,
            sourcescript=["/cvmfs/etp.kit.edu/LAW_envs/conda_envs/miniconda/bin/activate ML_LAW"]
        )

        ## Convert model to lwtnn format
        self.run_command(
            command=[
                "python",
                "ml_trainings/export_keras_to_json.py",
                "--training-config {}".format(config_file_rel),
                "--training-name {}".format(training_name),
                "--fold {}".format(fold),
                "--in-out-dir {}".format(out_dir),
            ],
            run_location=run_loc,
            sourcescript=["/cvmfs/etp.kit.edu/LAW_envs/conda_envs/miniconda/bin/activate ML_LAW"]
        )

        self.run_command(
            command=[
                "python",
                "lwtnn/converters/keras2json.py",
                "{dir}/fold{fold}_keras_architecture.json".format(dir=out_dir, fold=fold),
                "{dir}/fold{fold}_keras_variables.json".format(dir=out_dir, fold=fold),
                "{dir}/fold{fold}_keras_weights.h5".format(dir=out_dir, fold=fold),
                "> {dir}/fold{fold}_lwtnn.json".format(dir=out_dir, fold=fold),
            ],
            run_location=run_loc,
            sourcescript=["/cvmfs/etp.kit.edu/LAW_envs/conda_envs/miniconda/bin/activate ML_LAW"]
        )

        # Copy locally created files to remote storage
        out_files = [
            "/".join([
                out_dir,
                file_template.format(fold=fold),
            ])
            for file_template in self.file_templates
        ]

        console.log("File copy out start.")
        for file_remote, file_local in zip(self.output(), out_files):
            file_remote.parent.touch()
            file_remote.copy_from_local(file_local)
        console.log("File copy out end.")


# Wrapper task to call all trainings specified in an analysis file
class RunAllAnalysisTrainings(WrapperTask):
    analysis_config = luigi.Parameter(description="Path to analysis config file")

    def requires(self):
        # Load dict from analysis yaml file
        with open(self.analysis_config, "r") as stream:
            analysis_config = yaml.safe_load(stream)
        # Collect all training names and the files in which their configs are found
        trainings = []
        trainings_configs = []
        for combined_training in analysis_config.keys():
            config = analysis_config[combined_training]
            trainings.append(config["training"])
            trainings_configs.append(config["trainings_config"])
        # Only keep unique combinations
        training_information = list(set(zip(
            trainings,
            trainings_configs,
        )))
        # Check if there are trainings with the same name from different files
        t_names, paths = zip(*training_information)
        if(len(t_names) != len(set(t_names))):
            print("Trainings with the same name, but different config paths found!")
            data_found = []
            for data in training_information:
                t_name, path = data
                if t_name in data_found:
                    print("Training {} is affected.".format(t_name))
                else:
                    data_found.append(t_name)
            raise Exception("Consistency error in analysis config.")
        # Require trainings for all found training names 
        requirements = {}
        parameters = {"training_information": training_information}
        requirements["RunTraining"] = RunTraining(**parameters)
        return requirements
# KingMaker


[![Analysis Containers](https://github.com/KIT-CMS/kingmaker-images/actions/workflows/deploy-base-images.yml/badge.svg?branch=main)](https://github.com/KIT-CMS/kingmaker-images/actions/workflows/deploy-base-images.yml)

KingMaker is the workflow management for producing ntuples with the [CROWN](github.com/KIT-CMS/CROWN) framework. The workflow management is based on [law](github.com/riga/law), which is using [luigi](https://github.com/spotify/luigi) as backend.

**⚠ Important: A detailed description of the KingMaker workflow to produce NTuples can be found in the [CROWN documentation](https://crown.readthedocs.io/en/latest/kingmaker.html#).**

---

<details>
  <summary>The ML_train workflow</summary>

# The ML_train workflow
---
## Workflow

The ML_train workflow currently contains a number of the tasks necessary for the `htt-ml` analysis. The-`NMSSM` analysis is currently not yet supported. It should be noted, that all created files are stored in remote storage and might be subject to file caching under certain circumstances.
The tasks , located in are:

1. [CreateTrainingDataShard](processor/tasks/MLTraining.py#L30)
    Remote workflow task that creates the process-datasets for the machine learning tasks from the config files you provide. The task uses the `ntuples` and `friend trees` described in the [Sample setup](https://github.com/tvoigtlaender/sm-htt-analysis/tree/master/utils/setup_samples.sh). These dependencies are currently not checked by LAW. Also uses the [create_training_datashard](https://github.com/tvoigtlaender/sm-htt-analysis/tree/master/ml_datasets/create_training_datashard.py) script. \
    The task branches each return a root file that consists of one fold of one of the processes described in the provided configs. These files can then be used for the machine learning tasks.
2. [RunTraining](processor/tasks/MLTraining.py#L141)
    Remote workflow task that performs the neural network training using GPU resources if possible. Uses the [Tensorflow_training](https://github.com/tvoigtlaender/sm-htt-analysis/tree/master/ml_trainings/Tensorflow_training.py) script. The hyperparameters of this training are set by the provided config files.\
    Each branch task returns a set of files for one fold of one training specified in the configs. Each set includes the trained `.h5` model, the preprocessing object as a `.pickle` file and a graph of the loss as a `.pdf` and `.png`. The task also returns a set of files that can be used with the [lwtnn](https://github.com/lwtnn/lwtnn) package.
3. [RunTesting](processor/tasks/MLTraining.py#L415)
    Remote workflow task that performs a number of tests on the trained neural network using GPU resources if possible. Uses the [ml_tests](https://github.com/tvoigtlaender/sm-htt-analysis/tree/master/ml_tests) scripts. The tests return a number plots and their `.json` files in a tarball, which is copied to the remote storage. The plots include confusion, efficiency, purity, 1D-taylor and taylor ranking.
5. [RunAllAnalysisTrainings](processor/tasks/MLTraining.py#L707)
    Task to run all trainings described in the configs.

## Run ML_train

Normally, the `ML_train` workflow can be run by running the `RunAllAnalysisTrainings` task:

```bash

law run RunAllAnalysisTrainings --analysis-config <Analysis configs>

```
Alternatively a single training/testing can be performed by using the `RunTraining`/`RunTesting` task directly:
```bash

law run RunTraining --training-information '[["<Training name>","<Training configs>"]]'
law run RunTesting --training-information '[["<Training name>","<Training configs>"]]'

```
Similarly it is possible to create only a single data-shard:

```bash

law run CreateTrainingDataShard --datashard-information '[["<Process name>", "<Process class>"]]' --process-config-dirs '["<Process dir>"]'

```

An example of how the above scripts could look like with the example configs: 
```bash

law run RunAllAnalysisTrainings --analysis-config ml_configs/example_configs/sm.yaml
law run RunTraining --training-information '[["sm_2018_mt","ml_configs/example_configs/trainings.yaml"]]'
law run RunTesting --training-information '[["sm_2018_mt","ml_configs/example_configs/trainings.yaml"]]'
law run CreateTrainingDataShard --datashard-information '[["2018_mt_ggh", "ggh"]]' --process-config-dirs '["ml_configs/example_configs/processes"]'

```
---
# Configurations, not set in the `ml_config` config files.
There are a number of parameters to be set in the [luigi](lawluigi_configs/ML_train_luigi.cfg) and [law](lawluigi_configs/ML_train_law.cfg) config files:

- `ENV_NAME`: The Environment used in all non-batch jobs. Can be set individually for each batch job.
- `additional_files`: What files should be transfered into a batch job in addition to the usual ones (`lawluigi_configs`, `processor` and `law`).
- `production_tag`: Can be any string. Used to differentiate the runs. Default is a unique timestamp.
- A number of htcondor specific settings that can be adjusted if necessary.

Useful command line arguments:
1. `--workers`; The number of tasks that are handled simultaneously. 
2. `--print-status -1`; Return the current status of all tasks involved in the workflow. 
3. `--remove-output -1`; Remove all output files of tasks.

</details>


<details>
  <summary>Old Setup readme</summary>


## Setup

Setting up KingMaker should be straight forward:

```sh
git clone --recursive git@github.com:KIT-CMS/KingMaker.git
cd KingMaker
source setup.sh <Analysis Name>
```

this should setup the environment specified in the luigi.cfg file (located at `lawluigi_configs/<Analysis Name>_luigi.cfg`), which includes all needed packages.
The environment is sourced from the conda instance located at `/cvmfs/etp.kit.edu/LAW_envs/conda_envs/miniconda/` if possible. 
If the relevant environment is not available this way, the environment will be set up in a local conda instance.
The environment files are located at `kingmaker-images/KingMaker_envs/<Analysis Name>_env.cfg`.
In addition other files are installed depending on the analysis.

A list of available analyses can be found in the `setup.sh` script or by running 
```sh
source setup.sh -l
```

In addition a `luigid` scheduler is also started if there isn't one running already. 

When setting up an already cloned version, a
```sh
source setup.sh <Analysis Name>
```
is enough.
</details>

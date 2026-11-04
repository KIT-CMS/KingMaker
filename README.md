# KingMaker

KingMaker is the workflow management for producing ntuples with the [CROWN](https://github.com/KIT-CMS/CROWN) framework. The workflow management is based on [law](https://github.com/riga/law), which is using [luigi](https://github.com/spotify/luigi) as backend.

**⚠ Important: A detailed description of the KingMaker workflow to produce NTuples can be found in the [CROWN documentation](https://crown.readthedocs.io/en/latest/kingmaker.html#).**


## 🛠 Infrastructure & Containers

KingMaker can run within container environments to ensure reproducibility.

* **Container Images and Environments**: Dockerfiles and Conda environment specifications are located in the [`/containers`](./containers) directory.
* **Usage**: For instructions on building custom images or using existing ones from CVMFS, see the [Container Documentation](./containers/README.md).

## 🤖 Python (ML) friends

`ProducePythonFriends` evaluates machine learning models on existing CROWN ntuples and writes the results as friend trees. It does not compile a CROWN friend: the config is a python file in `CROWN/analysis_configurations/<analysis>/`, and the jobs evaluate it in the LCG stack (`ml_setup_script` in `KingMaker_luigi.cfg`), so any model type works (onnxruntime, torch, xgboost, sklearn, ...). See `CROWN/analysis_configurations/template_analysis/template_python_friend_config.py` for a template.

The config provides three functions:

* `build_config(era, sample_type, scope, shifts)` returns the `evaluations`, one per model: `shift` (`"nominal"` or a shift name), `model` (path relative to the analysis directory, or a `root://` URL), `inputs` (the names the model was trained with) and `outputs`. Outputs of shift models are written as `<output>__<shift>`. Only shifts selected with `--shifts` are evaluated (same matching as CROWN); nominal is always evaluated.
  * `input_map` (top level or per evaluation) translates model input names to ntuple columns, so models don't have to be retrained when the ntuples name a quantity differently.
  * `empty_values` gives constants for inputs whose column is missing. Only meant for tests on incomplete ntuples; outside the local test it needs `--allow-empty-values`. Filled inputs are listed in the `python_friend_info` object of every output file.
* `load_model(path, evaluation)` is called once per job and model. Do the heavy imports here, because the config is also imported on the submission host. Use at most `PYTHON_FRIEND_NTHREADS` threads.
* `evaluate(model, data, evaluation)` maps model input names to numpy arrays and returns output name → array.

Before any job is submitted, `PythonFriendInputCheck` opens the first ntuple (and the friends from `--requires-friends`) of every sample and scope. It checks that all inputs exist and that the outputs don't clash with existing columns, and fails with a table of the problems. The check, and the job tarball, are redone whenever the config or the models change.

```bash
# local test: first 1000 events per sample, nothing is submitted
law run ProducePythonFriends --analysis template_analysis --config template_config \
    --sample-list samples.txt --python-friend-config template_python_friend_config \
    --friend-tag example_v1 --scopes mm --shifts MuonID --production-tag <existing tag> --local-test
# production (add e.g. --requires-friends fastmtt --friend-mapping map.yaml for CROWN friend inputs)
law run ProducePythonFriends --analysis template_analysis --config template_config \
    --sample-list samples.txt --python-friend-config template_python_friend_config \
    --friend-tag example_v1 --scopes mm --shifts MuonID --production-tag <existing tag>
# test on a single ntuple file
law run PythonFriendLocalTest --analysis template_analysis --config template_config \
    --python-friend-config template_python_friend_config --friend-tag example_v1 --nick <nick> \
    --era <era> --sample-type <sample_type> --scopes '["mm"]' --shifts None --test-file <ntuple.root>
```
The friend trees are written next to the CROWN friends, `<production tag>/CROWNFriends/<friend tag>/...`, so they can be used like any other friend. Choose a friend tag that no CROWN friend uses. Job files, logs and the job tarball go to `<production tag>/PythonFriendBuild/`. To run the jobs on GPUs, set `htcondor_request_gpus = 1` in `[PythonFriend]` of `KingMaker_luigi.cfg`: they then use the CUDA view `ml_setup_script_gpu` instead of `ml_setup_script`. The configs have to use a GPU if there is one (see the template), so the same config runs on GPUs and CPUs. Local tests and the sensitivity test always run on the CPU. After changes to the KingMaker code itself (not the config or models), add `--force-repack-tarball`.

### Sensitivity test

`--sensitivity-test` checks, without any ntuples, how much every input of the models changes their outputs, e.g. to see whether inputs that are missing in the ntuples and filled via `empty_values` matter. It only uses the config's three functions, so it works for any model type (TF, ONNX, xgboost, ...). Random events are drawn from ranges given in the config, each input independently. Then every input (and every input group) is drawn again while the others are kept, and the score per output is

    score = RMS(y_varied - y) / std(y)    0: the output ignores it, ~1.4: the output is fully driven by it

Inputs and groups with `empty_values` are additionally set to them ("masked" rows), which shows what the masking in the production changes. The test runs locally in the ML environment, prints one ranked table per evaluation (nominal and the selected shift models) and writes all scores (plus the absolute RMS in output units) to `data/<tag>/PythonFriendSensitivity/<friend tag>/sensitivity/<era>/<sample type>/<scope>_n<N>_seed<S>_<hash>.json`. The task also plots them (see below) next to the config, in `CROWN/analysis_configurations/<analysis>/sensitivity_plots/<python friend config>/`: `<era>_<scope>.pdf/.png` per scope (shift models get `_<evaluation name>` appended), and with several scopes `<era>_scopes.pdf/.png` comparing their nominal models. Later runs replace the plots, so commit them together with the config they belong to. Keep in mind that independent inputs ignore the correlations of real events: the scores show how the model responds over the given ranges, not the importance on data.

```bash
# one test per era of the sample list (with its first simulated sample type), nothing is submitted
law run ProducePythonFriends --analysis bbtautau --config sm_config --sample-list 2018.txt \
    --python-friend-config uhh_nu_regression_friend --friend-tag nu_regression --scopes mt \
    --shifts None --nanoAOD-version nanoAOD_v15 --production-tag <tag> --sensitivity-test
# or directly, with more events or another seed
law run PythonFriendSensitivity --analysis bbtautau --python-friend-config uhh_nu_regression_friend \
    --friend-tag nu_regression --era 2018 --sample-type dyjets --scopes '["mt"]' --shifts None \
    --production-tag <tag> --n-samples 50000 --seed 1
```

The plots are made by `processor/tasks/scripts/plot_python_friend_sensitivity.py`, which can also be used by hand to compare other results (e.g. seeds, model versions). It draws one row per input, group and masked row with a marker per JSON file (mean score over the outputs, whiskers from the smallest to the largest single output), plus a short explanation of how the scores were made (LCG view, needs matplotlib):

```bash
python3 processor/tasks/scripts/plot_python_friend_sensitivity.py mt.json:"mu tau" et.json:"e tau" --output sensitivity.pdf
```

**What the config needs.** `build_config()` returns, next to the usual keys (top level, or per evaluation, where the evaluation's entries win, as for `input_map`):

* `input_ranges`: **one entry for every input in `inputs`** of every evaluation, keyed by the model input name (not the ntuple column). Every input is tested; a missing entry is an error.
* `input_groups` (optional): group name → list of inputs that are also drawn again (and masked) together, e.g. the components of one four-vector. Group names must not be input names.

| Entry | Keys | Drawn as |
|---|---|---|
| uniform | `min`, `max` (`min < max`) | uniform in [min, max) |
| gaussian | `mean`, `std` (`std > 0`) | gaussian |
| discrete | `values`, optional `weights` (same length, ≥ 0) | one of the values; a single value marks an input fixed by the physics (e.g. the muon decay mode in mt), reported as `constant` with score 0 |
| + `empty_fraction` | in [0, 1), together with any of the above | the input's `empty_values` value with this probability; needs an `empty_values` entry |
| derived | a function `f(rng, n, data)` | computed after all dict entries (and earlier functions, in `input_ranges` order); `data` holds those inputs as arrays, `rng` is a `numpy.random.Generator`; returns an array of length n. Use it for inputs that depend on others, e.g. an energy from px/py/pz and a random mass. It is recomputed when an input it uses is drawn again. |

Arrays are passed as `float32` (floats) or `int32` (integers), as they are read from the ntuples. `evaluate()` has to handle every combination of values in these ranges and has to be deterministic. Inputs with `empty_values` get a masked row; members of a group whose inputs all have `empty_values` are only masked together. Misconfigured ranges (unknown keys, missing or unknown inputs, `min >= max`, `std <= 0`, empty `values`, `empty_fraction` without `empty_values`, invalid groups) stop the test with a list of all problems. `template_python_friend_config.py` uses every entry type; `uhh_nu_regression_friend.py` of bbtautau is a full example (scope dependent ranges, groups, derived inputs).

The payload tests run in the LCG view:
`source /cvmfs/sft.cern.ch/lcg/views/LCG_109/x86_64-el9-gcc13-opt/setup.sh && python3 -m pytest tests/python_friends`

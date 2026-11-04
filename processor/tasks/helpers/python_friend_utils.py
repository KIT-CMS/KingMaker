"""
Shared logic for python (ML) friends.

Used both on the submission host (PythonFriendInputCheck, law environment) and inside
the jobs (scripts/run_python_friend.py, LCG environment), so it only depends on the
standard library and, for the array helpers, numpy. Keeping the input resolution in one
place guarantees that the pre-submission check and the jobs agree on what is evaluated.
"""

import difflib
import importlib
import json
import os
import sys

NOMINAL = "nominal"
EVALUATION_KEYS = {
    "shift",
    "model",
    "inputs",
    "outputs",
    "input_map",
    "empty_values",
    "input_ranges",
    "input_groups",
    "name",
}
CONFIG_KEYS = {
    "evaluations",
    "batch_size",
    "input_map",
    "empty_values",
    "input_ranges",
    "input_groups",
}
# keys of a dict entry of input_ranges, see validate_input_ranges()
RANGE_TYPES = {"uniform": {"min", "max"}, "gaussian": {"mean", "std"}, "discrete": {"values"}}
RANGE_OPTIONS = {"weights", "empty_fraction"}
DEFAULT_BATCH_SIZE = 100_000


class PythonFriendConfigError(Exception):
    pass


def load_friend_config(crown_path, analysis, name):
    """
    Import CROWN/analysis_configurations/<analysis>/<name>.py as a package module, so
    relative imports inside the config (e.g. `from .quantities import output`) work.
    """
    crown_path = os.path.abspath(crown_path)
    config_file = os.path.join(
        crown_path, "analysis_configurations", str(analysis), f"{name}.py"
    )
    if not os.path.isfile(config_file):
        raise PythonFriendConfigError(f"Python friend config {config_file} not found")
    if crown_path not in sys.path:
        sys.path.insert(0, crown_path)
    try:
        module = importlib.import_module(f"analysis_configurations.{analysis}.{name}")
    except ImportError as e:
        raise PythonFriendConfigError(
            f"Importing {config_file} failed: {e}\n"
            "Hint: keep heavy imports (torch, onnxruntime, xgboost, ...) inside "
            "load_model()/evaluate(), the config is also imported on the submission host."
        ) from e
    for function in ("build_config", "load_model", "evaluate"):
        if not callable(getattr(module, function, None)):
            raise PythonFriendConfigError(
                f"Python friend config {config_file} has no function {function}()"
            )
    return module


def parse_shifts(shifts):
    """
    Normalize the --shifts value ("None", "All" or a comma separated list) to a list.
    """
    if shifts is None:
        return ["none"]
    if isinstance(shifts, str):
        shifts = shifts.split(",")
    shifts = [str(shift).strip() for shift in shifts if str(shift).strip()]
    return shifts or ["none"]


def shift_selected(shift, requested_shifts):
    """
    Same selection as CROWN: nominal always runs, "none" selects nothing else, "all"
    selects everything, otherwise a shift runs if any requested name is contained in it.
    """
    if shift == NOMINAL:
        return True
    requested = [s.lower() for s in requested_shifts]
    if requested == ["none"]:
        return False
    if requested == ["all"]:
        return True
    return any(name in shift.lower() for name in requested)


def output_name(output, shift):
    return output if shift == NOMINAL else f"{output}__{shift}"


def get_evaluations(module, era, sample_type, scope, shifts):
    """
    Call the config's build_config() and return (evaluations, batch_size). Top level
    input_map/empty_values are merged into every evaluation (evaluation entries win),
    and evaluations of shifts that were not requested are dropped.
    """
    requested_shifts = parse_shifts(shifts)
    config = module.build_config(
        era=era, sample_type=sample_type, scope=scope, shifts=requested_shifts
    )
    if not isinstance(config, dict) or "evaluations" not in config:
        raise PythonFriendConfigError(
            "build_config() has to return a dict with an 'evaluations' list"
        )
    unknown = set(config) - CONFIG_KEYS
    if unknown:
        raise PythonFriendConfigError(
            f"Unknown keys {sorted(unknown)} in build_config() result"
        )
    evaluations = []
    for index, evaluation in enumerate(config["evaluations"]):
        unknown = set(evaluation) - EVALUATION_KEYS
        if unknown:
            raise PythonFriendConfigError(
                f"Unknown keys {sorted(unknown)} in evaluation {index}"
            )
        for key in ("model", "inputs", "outputs"):
            if not evaluation.get(key):
                raise PythonFriendConfigError(f"Evaluation {index} has no '{key}'")
        shift = evaluation.get("shift", NOMINAL)
        if not shift_selected(shift, requested_shifts):
            continue
        evaluations.append(
            {
                "name": evaluation.get("name", f"{shift}_{index}"),
                "shift": shift,
                "scope": scope,
                "era": era,
                "sample_type": sample_type,
                "model": evaluation["model"],
                "inputs": list(evaluation["inputs"]),
                "outputs": list(evaluation["outputs"]),
                "input_map": {
                    **config.get("input_map", {}),
                    **evaluation.get("input_map", {}),
                },
                "empty_values": {
                    **config.get("empty_values", {}),
                    **evaluation.get("empty_values", {}),
                },
                # only used by the sensitivity test
                "input_ranges": {
                    **config.get("input_ranges", {}),
                    **evaluation.get("input_ranges", {}),
                },
                "input_groups": {
                    **config.get("input_groups", {}),
                    **evaluation.get("input_groups", {}),
                },
            }
        )
    if not any(e["shift"] == NOMINAL for e in evaluations):
        raise PythonFriendConfigError(
            f"No nominal evaluation defined for scope {scope}"
        )
    return evaluations, int(config.get("batch_size", DEFAULT_BATCH_SIZE))


def resolve_inputs(evaluation, available_branches, allow_empty):
    """
    Resolve the model inputs of one evaluation against the available branches.

    Per model input: translate via input_map (identity otherwise), use the branch if it
    exists, else fall back to empty_values (only if allow_empty), else report an error.
    Returns a dict with
        columns:  {model input: branch name}
        empty:    {model input: (missing branch name, fill value)}
        errors:   [(model input, missing branch name, [close matches])]
        warnings: [str]
    """
    available = set(available_branches)
    input_map = evaluation.get("input_map", {})
    empty_values = evaluation.get("empty_values", {})
    result = {"columns": {}, "empty": {}, "errors": [], "warnings": []}
    for model_input in evaluation["inputs"]:
        column = input_map.get(model_input, model_input)
        if column in available:
            result["columns"][model_input] = column
            if model_input in empty_values or column in empty_values:
                result["warnings"].append(
                    f"empty value for '{model_input}' ignored, column '{column}' exists"
                )
            continue
        fill = empty_values.get(model_input, empty_values.get(column))
        if fill is not None and allow_empty:
            result["empty"][model_input] = (column, fill)
            continue
        suggestions = difflib.get_close_matches(column, available, n=3)
        result["errors"].append((model_input, column, suggestions))
    for model_input in input_map:
        if model_input not in evaluation["inputs"]:
            result["warnings"].append(
                f"input_map entry '{model_input}' is not an input of the model"
            )
    return result


def check_outputs(evaluations, available_branches):
    """
    Output branches must neither exist already nor be produced twice.
    """
    errors = []
    seen = set()
    for evaluation in evaluations:
        for output in evaluation["outputs"]:
            name = output_name(output, evaluation["shift"])
            if name in seen:
                errors.append(f"output '{name}' is produced more than once")
            if name in available_branches:
                errors.append(f"output '{name}' already exists in the inputs")
            seen.add(name)
    return errors


def quantities_map(evaluations):
    """
    Shift -> produced quantities, in the layout of CROWN's shift_quantities_map.
    """
    data = {}
    for evaluation in evaluations:
        shift = "" if evaluation["shift"] == NOMINAL else f"__{evaluation['shift']}"
        data.setdefault(shift, [])
        data[shift] += [
            output_name(o, evaluation["shift"]) for o in evaluation["outputs"]
        ]
    return {shift: sorted(quantities) for shift, quantities in data.items()}


def empty_array(value, length):
    import numpy as np

    if isinstance(value, bool):
        return np.full(length, value, dtype=np.bool_)
    if isinstance(value, int):
        return np.full(length, value, dtype=np.int32)
    return np.full(length, value, dtype=np.float32)


def friend_info(evaluations, resolved):
    """
    JSON stored next to the friend tree, recording translated and defaulted inputs.
    """
    return json.dumps(
        {
            evaluation["name"]: {
                "shift": evaluation["shift"],
                "model": evaluation["model"],
                "columns": resolved[evaluation["name"]]["columns"],
                "empty_values": {
                    model_input: {"column": column, "value": value}
                    for model_input, (column, value) in resolved[evaluation["name"]][
                        "empty"
                    ].items()
                },
            }
            for evaluation in evaluations
        }
    )


def empty_value(evaluation, model_input):
    """
    The empty_values entry of a model input (keyed by input or column name), or None.
    """
    empty_values = evaluation.get("empty_values", {})
    column = evaluation.get("input_map", {}).get(model_input, model_input)
    return empty_values.get(model_input, empty_values.get(column))


def validate_input_ranges(evaluation):
    """
    Errors in the input_ranges/input_groups of an evaluation, as list of strings. Every
    input needs a range, so that every input is tested. Inputs fixed by the physics (e.g.
    the decay mode of the muon) take a single entry in values and are reported as
    constant.
    """
    errors = []
    inputs = evaluation["inputs"]
    ranges = evaluation.get("input_ranges", {})
    missing = [name for name in inputs if name not in ranges]
    if missing:
        errors.append(f"no input_ranges entry for the inputs {missing}")
    unknown = [name for name in ranges if name not in inputs]
    if unknown:
        errors.append(f"input_ranges entries {unknown} are not inputs of the model")
    for name, spec in ranges.items():
        if name not in inputs or callable(spec):
            continue
        if not isinstance(spec, dict):
            errors.append(f"input_ranges['{name}'] has to be a dict or a callable")
            continue
        types = [t for t, keys in RANGE_TYPES.items() if keys & set(spec)]
        known = set().union(*RANGE_TYPES.values(), RANGE_OPTIONS)
        if set(spec) - known:
            errors.append(f"input_ranges['{name}']: unknown keys {sorted(set(spec) - known)}")
        if len(types) != 1 or not RANGE_TYPES[types[0]] <= set(spec):
            errors.append(
                f"input_ranges['{name}'] needs exactly one of min/max, mean/std or values"
            )
            continue
        if types[0] == "uniform" and not spec["min"] < spec["max"]:
            errors.append(f"input_ranges['{name}']: min has to be smaller than max")
        if types[0] == "gaussian" and not spec["std"] > 0:
            errors.append(f"input_ranges['{name}']: std has to be positive")
        if types[0] == "discrete" and not len(spec["values"]):
            errors.append(f"input_ranges['{name}']: values must not be empty")
        if "weights" in spec and (
            types[0] != "discrete"
            or len(spec["weights"]) != len(spec["values"])
            or min(spec["weights"]) < 0
            or sum(spec["weights"]) <= 0
        ):
            errors.append(
                f"input_ranges['{name}']: weights need values of the same length, "
                "non-negative with a positive sum"
            )
        if "empty_fraction" in spec:
            if not 0 <= spec["empty_fraction"] < 1:
                errors.append(f"input_ranges['{name}']: empty_fraction has to be in [0, 1)")
            if empty_value(evaluation, name) is None:
                errors.append(
                    f"input_ranges['{name}']: empty_fraction needs an empty_values entry"
                )
    for group, members in evaluation.get("input_groups", {}).items():
        if group in inputs:
            errors.append(f"input_groups: group '{group}' has the name of an input")
        if not members or any(m not in inputs for m in members):
            errors.append(
                f"input_groups['{group}'] has to be a non-empty list of model inputs"
            )
    return errors


def sample_inputs(evaluation, n, seed, redraw=()):
    """
    Draw n random events from the input_ranges of an evaluation, every input independent.

    Every input has its own random stream, so drawing again with the same seed gives the
    same values, except for the inputs in redraw, which get new ones. Callable ranges are
    evaluated after all others (in input_ranges order) with their own fixed stream, so
    they only change if they are redrawn themselves or the inputs they use change.
    """
    import numpy as np

    ranges = evaluation["input_ranges"]
    index = {name: i for i, name in enumerate(evaluation["inputs"])}
    plain = [name for name in evaluation["inputs"] if not callable(ranges[name])]
    derived = [name for name in ranges if name in index and callable(ranges[name])]
    data = {}
    for name in plain + derived:
        rng = np.random.default_rng([seed, index[name], int(name in redraw)])
        spec = ranges[name]
        if callable(spec):
            values = np.asarray(spec(rng, n, dict(data)))
            if values.shape != (n,):
                raise PythonFriendConfigError(
                    f"input_ranges['{name}'] returned shape {values.shape}, expected ({n},)"
                )
        elif "values" in spec:
            weights = spec.get("weights")
            if weights is not None:
                weights = np.asarray(weights, dtype=np.float64) / np.sum(weights)
            values = rng.choice(np.asarray(spec["values"]), size=n, p=weights)
        elif "mean" in spec:
            values = rng.normal(spec["mean"], spec["std"], n)
        else:
            values = rng.uniform(spec["min"], spec["max"], n)
        if not callable(spec) and spec.get("empty_fraction"):
            empty = rng.random(n) < spec["empty_fraction"]
            values = np.where(empty, empty_value(evaluation, name), values)
        # same dtypes as read from the ntuples or filled by empty_array
        if np.issubdtype(values.dtype, np.floating):
            values = values.astype(np.float32)
        elif np.issubdtype(values.dtype, np.integer):
            values = values.astype(np.int32)
        data[name] = values
    return {name: data[name] for name in evaluation["inputs"]}


def sensitivity_variations(evaluation):
    """
    (name, kind, members) of all variations of the sensitivity test: every input and
    every group redrawn, every input and group with empty_values set to them (masked;
    inputs of a fully masked group only within the group). Inputs with a single value are redrawn as well, as kind "constant" (score 0).
    """
    ranges = evaluation["input_ranges"]

    def constant(name):
        spec = ranges[name]
        return (
            isinstance(spec, dict)
            and len(set(spec.get("values", []))) == 1
            and not spec.get("empty_fraction")
        )

    variations = [
        (name, "constant" if constant(name) else "input", [name])
        for name in evaluation["inputs"]
    ]
    groups = evaluation.get("input_groups", {})
    variations += [(group, "group", list(members)) for group, members in groups.items()]
    masked_groups = {
        group: list(members)
        for group, members in groups.items()
        if all(empty_value(evaluation, m) is not None for m in members)
    }
    # members of a masked group are only masked together, as in the production (e.g.
    # a fatjet with only px empty is no state the model can see)
    in_masked_group = {m for members in masked_groups.values() for m in members}
    variations += [
        (name, "masked", [name])
        for name in evaluation["inputs"]
        if empty_value(evaluation, name) is not None and name not in in_masked_group
    ]
    variations += [
        (group, "masked group", members) for group, members in masked_groups.items()
    ]
    return variations


def sensitivity_test(evaluation, evaluate, n, seed):
    """
    Model independent sensitivity test of one evaluation on random inputs.

    evaluate(data) returns {output: array}. For every variation of
    sensitivity_variations() the score per output is RMS(y_varied - y) / std(y): 0 if
    the output ignores the variation, ~1.4 if it is fully driven by it. Returns
    {"outputs": {output: {"mean", "std", "nonfinite"}}, "variations": [...]}, the
    variations sorted by the mean score over the outputs.
    """
    import numpy as np

    errors = validate_input_ranges(evaluation)
    if errors:
        raise PythonFriendConfigError(
            f"Invalid input_ranges of '{evaluation['name']}':\n  " + "\n  ".join(errors)
        )
    data = sample_inputs(evaluation, n, seed)
    nominal = {k: np.asarray(v, dtype=np.float64) for k, v in evaluate(data).items()}
    outputs = {}
    for output, values in nominal.items():
        finite = np.isfinite(values)
        outputs[output] = {
            "mean": float(values[finite].mean()) if finite.any() else float("nan"),
            "std": float(values[finite].std()) if finite.any() else float("nan"),
            "nonfinite": int((~finite).sum()),
        }
    results = []
    for name, kind, members in sensitivity_variations(evaluation):
        if kind in ("input", "constant", "group"):
            varied = sample_inputs(evaluation, n, seed, redraw=members)
        else:
            varied = dict(data)
            for member in members:
                varied[member] = empty_array(empty_value(evaluation, member), n)
        result = {"name": name, "kind": kind, "members": members, "scores": {}, "rms": {}}
        nonfinite = 0
        for output, values in evaluate(varied).items():
            diff = np.asarray(values, dtype=np.float64) - nominal[output]
            finite = np.isfinite(diff)
            nonfinite += int((~finite).sum())
            rms = float(np.sqrt(np.mean(diff[finite] ** 2))) if finite.any() else float("nan")
            std = outputs[output]["std"]
            result["rms"][output] = rms
            result["scores"][output] = rms / std if std > 0 else float("nan")
        scores = [s for s in result["scores"].values() if np.isfinite(s)]
        result["mean"] = float(np.mean(scores)) if scores else float("nan")
        result["max"] = float(np.max(scores)) if scores else float("nan")
        result["nonfinite"] = nonfinite
        results.append(result)
    results.sort(key=lambda r: -r["mean"] if np.isfinite(r["mean"]) else np.inf)
    return {"outputs": outputs, "variations": results}

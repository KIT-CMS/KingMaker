#!/usr/bin/env python3
"""
Evaluate the models of a python friend config on one CROWN ntuple (plus friends) and
write the outputs as a friend tree.

Runs in the ML environment (LCG view), not in the law environment: only numpy, uproot
and whatever the user's models need are imported here.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import uproot

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from helpers.python_friend_utils import (  # noqa: E402
    check_outputs,
    empty_array,
    friend_info,
    get_evaluations,
    quantities_map,
    load_friend_config,
    output_name,
    resolve_inputs,
)

TREE = "ntuple"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crown-path", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--era", required=True)
    parser.add_argument("--sample-type", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--shifts", default="None")
    parser.add_argument("--input", required=True, help="CROWN ntuple")
    parser.add_argument("--friend", action="append", default=[], help="friend files")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--quantities-map", default=None, help="also write the produced quantities"
    )
    parser.add_argument("--max-events", type=int, default=-1)
    parser.add_argument("--allow-empty-values", action="store_true")
    return parser.parse_args(argv)


def localize_model(model, analysis_dir, tmpdir):
    """
    Relative model paths point into the analysis directory, remote ones are copied.
    """
    if "://" in model:
        local = os.path.join(tmpdir, os.path.basename(model))
        if not os.path.exists(local):
            print(f"Copying model {model}")
            subprocess.run(["xrdcp", "-s", model, local], check=True)
        return local
    path = model if os.path.isabs(model) else os.path.join(analysis_dir, model)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model {path} not found")
    return path


def open_trees(paths):
    trees = [uproot.open(path)[TREE] for path in paths]
    entries = {path: tree.num_entries for path, tree in zip(paths, trees)}
    if len(set(entries.values())) != 1:
        raise RuntimeError(f"Input trees have different numbers of entries: {entries}")
    # like a TTree friend: a branch is taken from the first file that has it
    branch_tree = {}
    for index, tree in enumerate(trees):
        for branch in tree.keys():
            branch_tree.setdefault(branch, index)
    return trees, branch_tree, trees[0].num_entries


def validate_result(result, evaluation, length):
    if not isinstance(result, dict) or set(result) != set(evaluation["outputs"]):
        raise RuntimeError(
            f"evaluate() of '{evaluation['name']}' has to return a dict with the keys "
            f"{evaluation['outputs']}, got {list(result) if isinstance(result, dict) else type(result)}"
        )
    arrays = {}
    for output, values in result.items():
        values = np.asarray(values)
        if values.ndim != 1 or len(values) != length:
            raise RuntimeError(
                f"Output '{output}' of '{evaluation['name']}' has shape {values.shape}, "
                f"expected ({length},)"
            )
        if not (np.issubdtype(values.dtype, np.number) or values.dtype == np.bool_):
            raise RuntimeError(
                f"Output '{output}' of '{evaluation['name']}' has non numeric dtype {values.dtype}"
            )
        arrays[output_name(output, evaluation["shift"])] = values
    return arrays


def summarize(summary, arrays):
    for name, values in arrays.items():
        stats = summary.setdefault(
            name, {"n": 0, "sum": 0.0, "min": np.inf, "max": -np.inf, "nonfinite": 0}
        )
        values = values.astype(np.float64)
        finite = np.isfinite(values)
        stats["n"] += len(values)
        stats["nonfinite"] += int((~finite).sum())
        if finite.any():
            stats["sum"] += float(values[finite].sum())
            stats["min"] = min(stats["min"], float(values[finite].min()))
            stats["max"] = max(stats["max"], float(values[finite].max()))


def print_summary(summary):
    print(
        f"{'column':<40} {'entries':>10} {'mean':>12} {'min':>12} {'max':>12} {'nan/inf':>8}"
    )
    for name, s in summary.items():
        finite = s["n"] - s["nonfinite"]
        mean = s["sum"] / finite if finite else float("nan")
        print(
            f"{name:<40} {s['n']:>10} {mean:>12.5g} {s['min']:>12.5g} {s['max']:>12.5g} {s['nonfinite']:>8}"
        )


def run(args):
    module = load_friend_config(args.crown_path, args.analysis, args.config)
    analysis_dir = os.path.join(
        os.path.abspath(args.crown_path), "analysis_configurations", args.analysis
    )
    evaluations, batch_size = get_evaluations(
        module, args.era, args.sample_type, args.scope, args.shifts
    )
    trees, branch_tree, entries = open_trees([args.input] + list(args.friend))
    if args.max_events >= 0:
        entries = min(entries, args.max_events)

    resolved = {}
    errors = check_outputs(evaluations, branch_tree)
    for evaluation in evaluations:
        resolved[evaluation["name"]] = resolve_inputs(
            evaluation, branch_tree, args.allow_empty_values
        )
        for model_input, column, _ in resolved[evaluation["name"]]["errors"]:
            errors.append(
                f"'{evaluation['name']}': input '{model_input}' -> missing column '{column}'"
            )
        for model_input, (column, value) in resolved[evaluation["name"]][
            "empty"
        ].items():
            print(
                f"WARNING: '{evaluation['name']}': column '{column}' missing, "
                f"input '{model_input}' is filled with {value!r}"
            )
    if errors:
        raise RuntimeError("Invalid python friend inputs:\n  " + "\n  ".join(errors))

    tmpdir = tempfile.mkdtemp(prefix="python_friend_models_")
    models = {}
    for evaluation in evaluations:
        path = localize_model(evaluation["model"], analysis_dir, tmpdir)
        print(
            f"Loading model for '{evaluation['name']}' ({evaluation['shift']}): {path}"
        )
        models[evaluation["name"]] = module.load_model(path, evaluation)

    tree_columns = {}
    for r in resolved.values():
        for column in r["columns"].values():
            tree_columns.setdefault(branch_tree[column], set()).add(column)
    summary = {}
    output_file = uproot.recreate(args.output)
    tree = None
    for start in range(0, entries, batch_size):
        stop = min(start + batch_size, entries)
        data = {}
        for index, columns in tree_columns.items():
            data.update(
                trees[index].arrays(
                    sorted(columns), entry_start=start, entry_stop=stop, library="np"
                )
            )
        batch = {}
        for evaluation in evaluations:
            r = resolved[evaluation["name"]]
            inputs = {
                model_input: (
                    data[r["columns"][model_input]]
                    if model_input in r["columns"]
                    else empty_array(r["empty"][model_input][1], stop - start)
                )
                for model_input in evaluation["inputs"]
            }
            result = module.evaluate(models[evaluation["name"]], inputs, evaluation)
            batch.update(validate_result(result, evaluation, stop - start))
        if tree is None:
            # title as in CROWN: analysis frameworks look for the "ntuple" title
            tree = output_file.mktree(
                TREE, {k: v.dtype for k, v in batch.items()}, title=TREE
            )
        tree.extend(batch)
        summarize(summary, batch)
        print(f"Processed {stop}/{entries} events")
    if tree is None:
        # no events: still write a valid (empty) friend tree
        output_file.mktree(
            TREE,
            {
                output_name(o, e["shift"]): np.float32
                for e in evaluations
                for o in e["outputs"]
            },
            title=TREE,
        )
    output_file["python_friend_info"] = friend_info(evaluations, resolved)
    output_file.close()
    shutil.rmtree(tmpdir, ignore_errors=True)

    written = uproot.open(args.output)[TREE].num_entries
    if written != entries:
        raise RuntimeError(f"Wrote {written} entries, expected {entries}")
    if args.quantities_map:
        # same layout as the quantities maps of CROWN friends
        with open(args.quantities_map, "w") as f:
            json.dump(
                {
                    "quantities": {
                        args.era: {
                            args.sample_type: {args.scope: quantities_map(evaluations)}
                        }
                    },
                    "metadata": {
                        "era": args.era,
                        "sample_type": args.sample_type,
                        "python_friend_config": args.config,
                    },
                },
                f,
                indent=4,
            )
    print_summary(summary)
    return summary


if __name__ == "__main__":
    run(parse_args())

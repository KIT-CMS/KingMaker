#!/usr/bin/env python3
"""
Model independent sensitivity test of a python friend config: evaluate its models on
random inputs drawn from the config's input_ranges and measure how much the outputs
change when single inputs or input groups are redrawn or set to their empty_values.

Runs in the ML environment (LCG view), like run_python_friend.py. No ntuples are read.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers.python_friend_utils import (  # noqa: E402
    get_evaluations,
    load_friend_config,
    sensitivity_test,
)
from run_python_friend import localize_model, validate_result  # noqa: E402

CAVEAT = (
    "Inputs are drawn independently from the input_ranges of the config: the scores show "
    "how the model responds over these ranges, not the importance under the real "
    "correlations of the inputs."
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crown-path", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--era", required=True)
    parser.add_argument("--sample-type", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--shifts", default="None")
    parser.add_argument("--n-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", required=True, help="JSON file with all scores")
    return parser.parse_args(argv)


def print_table(evaluation, result):
    outputs = list(result["outputs"])
    print(f"\nSensitivity of '{evaluation['name']}' ({evaluation['model']})")
    print("score = RMS(y_varied - y) / std(y): 0 = ignored, ~1.4 = fully driven by it")
    header = f"{'variation':<28} {'kind':<13} {'mean':>7} {'max':>7}"
    header += "".join(f" {o[:10]:>10}" for o in outputs)
    print(header)
    for row in result["variations"]:
        line = f"{row['name'][:28]:<28} {row['kind']:<13} {row['mean']:>7.3f} {row['max']:>7.3f}"
        line += "".join(f" {row['scores'][o]:>10.3f}" for o in outputs)
        if row["nonfinite"]:
            line += f"  ({row['nonfinite']} nan/inf)"
        print(line)
    for output, stats in result["outputs"].items():
        if stats["nonfinite"]:
            print(f"WARNING: {stats['nonfinite']} nan/inf values of {output} (nominal)")
    print(CAVEAT)


def run(args):
    module = load_friend_config(args.crown_path, args.analysis, args.config)
    analysis_dir = os.path.join(
        os.path.abspath(args.crown_path), "analysis_configurations", args.analysis
    )
    evaluations, batch_size = get_evaluations(
        module, args.era, args.sample_type, args.scope, args.shifts
    )
    tmpdir = tempfile.mkdtemp(prefix="python_friend_models_")
    results = {}
    for evaluation in evaluations:
        path = localize_model(evaluation["model"], analysis_dir, tmpdir)
        print(f"Loading model for '{evaluation['name']}' ({evaluation['shift']}): {path}")
        model = module.load_model(path, evaluation)

        def evaluate(data):
            # in batches of the config's batch_size, as in the production
            batches = []
            for start in range(0, args.n_samples, batch_size):
                stop = min(start + batch_size, args.n_samples)
                batch = {k: v[start:stop] for k, v in data.items()}
                result = module.evaluate(model, batch, evaluation)
                batches.append(validate_result(result, evaluation, stop - start))
            return {k: np.concatenate([b[k] for b in batches]) for k in batches[0]}

        result = sensitivity_test(evaluation, evaluate, args.n_samples, args.seed)
        print_table(evaluation, result)
        results[evaluation["name"]] = {
            "shift": evaluation["shift"],
            "model": evaluation["model"],
            **result,
        }
    shutil.rmtree(tmpdir, ignore_errors=True)
    with open(args.output, "w") as f:
        json.dump(
            {
                "metadata": {
                    "python_friend_config": args.config,
                    "era": args.era,
                    "sample_type": args.sample_type,
                    "scope": args.scope,
                    "n_samples": args.n_samples,
                    "seed": args.seed,
                    "caveat": CAVEAT,
                },
                "evaluations": results,
            },
            f,
            indent=4,
        )
    print(f"Scores written to {args.output}")
    return results


if __name__ == "__main__":
    run(parse_args())

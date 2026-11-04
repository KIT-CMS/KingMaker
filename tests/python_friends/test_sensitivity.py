"""
Tests for the sensitivity test of python friend configs.

Run inside the LCG view used by the jobs:
    source /cvmfs/sft.cern.ch/lcg/views/LCG_109/x86_64-el9-gcc13-opt/setup.sh
    python3 -m pytest tests/python_friends -q
"""

import json
import os
import sys
import textwrap

import numpy as np
import pytest

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(BASE, "processor", "tasks"))
sys.path.insert(0, os.path.join(BASE, "processor", "tasks", "scripts"))

import python_friend_sensitivity  # noqa: E402
from helpers.python_friend_utils import (  # noqa: E402
    PythonFriendConfigError,
    sample_inputs,
    sensitivity_test,
    sensitivity_variations,
    validate_input_ranges,
)

N = 2000


def toy_evaluation(**changes):
    evaluation = {
        "name": "nominal_0",
        "shift": "nominal",
        "inputs": ["a", "b", "c", "d", "e", "f"],
        "outputs": ["y"],
        "input_map": {"e": "column_e"},
        "empty_values": {"column_e": -1.0, "f": 0.0},
        "input_ranges": {
            "a": {"min": 0.0, "max": 1.0},
            "b": {"mean": 5.0, "std": 2.0},
            "c": {"values": [3]},
            "d": lambda rng, n, data: 2 * data["a"] + rng.normal(0, 0.1, n),
            "e": {"values": [1.0, 2.0], "weights": [1, 3], "empty_fraction": 0.2},
            "f": {"min": -1.0, "max": 1.0},
        },
        "input_groups": {"ab": ["a", "b"], "ef": ["e", "f"]},
    }
    evaluation.update(changes)
    return evaluation


def toy_evaluate(data):
    # y = 2 a + 0 b + c + e, d and f are ignored
    return {"y": 2 * data["a"] + 0 * data["b"] + data["c"] + data["e"]}


def test_validation_lists_all_errors():
    evaluation = toy_evaluation()
    assert validate_input_ranges(evaluation) == []
    ranges = dict(evaluation["input_ranges"])
    del ranges["a"]
    ranges["typo"] = {"min": 0.0, "max": 1.0}
    ranges["b"] = {"mean": 0.0, "std": 0.0}
    ranges["c"] = {"min": 1.0, "max": 0.0, "unit": "GeV"}
    ranges["f"] = {"min": 0.0, "max": 1.0, "mean": 0.0, "std": 1.0}
    errors = validate_input_ranges(
        toy_evaluation(input_ranges=ranges, input_groups={"g": ["a", "x"], "b": ["a"]})
    )
    text = "\n".join(errors)
    for expected in (
        "no input_ranges entry for the inputs ['a']",
        "['typo'] are not inputs",
        "'b']: std has to be positive",
        "'c']: unknown keys ['unit']",
        "'c']: min has to be smaller than max",
        "'f'] needs exactly one of",
        "input_groups['g']",
        "group 'b' has the name of an input",
    ):
        assert expected in text


def test_empty_fraction_needs_empty_value():
    ranges = dict(toy_evaluation()["input_ranges"])
    ranges["a"] = {"min": 0.0, "max": 1.0, "empty_fraction": 0.5}
    errors = validate_input_ranges(toy_evaluation(input_ranges=ranges))
    assert errors == ["input_ranges['a']: empty_fraction needs an empty_values entry"]


def test_sampling():
    evaluation = toy_evaluation()
    data = sample_inputs(evaluation, N, seed=1)
    assert list(data) == evaluation["inputs"]
    assert all(len(v) == N for v in data.values())
    assert data["a"].dtype == np.float32 and data["c"].dtype == np.int32
    assert 0 <= data["a"].min() and data["a"].max() <= 1
    assert abs(data["b"].mean() - 5) < 0.2 and abs(data["b"].std() - 2) < 0.2
    assert set(np.unique(data["e"])) == {-1.0, 1.0, 2.0}
    assert abs((data["e"] == -1).mean() - 0.2) < 0.03
    assert abs((data["e"] == 2).sum() / (data["e"] > 0).sum() - 0.75) < 0.04
    np.testing.assert_allclose(data["d"], 2 * data["a"], atol=0.6)
    # same seed, same values
    again = sample_inputs(evaluation, N, seed=1)
    assert all(np.array_equal(data[k], again[k]) for k in data)
    assert not np.array_equal(data["a"], sample_inputs(evaluation, N, seed=2)["a"])


def test_redraw_only_changes_redrawn_inputs_and_their_derived_ones():
    evaluation = toy_evaluation()
    data = sample_inputs(evaluation, N, seed=1)
    redrawn = sample_inputs(evaluation, N, seed=1, redraw=["a"])
    changed = {k for k in data if not np.array_equal(data[k], redrawn[k])}
    # d is derived from a, its own random part stays the same
    assert changed == {"a", "d"}
    np.testing.assert_allclose(
        redrawn["d"] - data["d"], 2 * (redrawn["a"] - data["a"]), atol=1e-5
    )
    redrawn = sample_inputs(evaluation, N, seed=1, redraw=["d"])
    assert {k for k in data if not np.array_equal(data[k], redrawn[k])} == {"d"}


def test_variations():
    variations = sensitivity_variations(toy_evaluation())
    assert [v[:2] for v in variations] == [
        ("a", "input"),
        ("b", "input"),
        ("c", "constant"),
        ("d", "input"),
        ("e", "input"),
        ("f", "input"),
        ("ab", "group"),
        ("ef", "group"),
        ("ef", "masked group"),
    ]
    # without the group, e (via its column) and f are masked one by one
    variations = sensitivity_variations(toy_evaluation(input_groups={}))
    assert [v[:2] for v in variations if "masked" in v[1]] == [
        ("e", "masked"),
        ("f", "masked"),
    ]


def test_scores():
    result = sensitivity_test(toy_evaluation(), toy_evaluate, N, seed=3)
    rows = {(r["name"], r["kind"]): r for r in result["variations"]}
    assert rows[("a", "input")]["scores"]["y"] > 0.5
    assert rows[("e", "input")]["scores"]["y"] > 0.5
    for name in ("b", "c", "d", "f"):
        kind = "constant" if name == "c" else "input"
        assert rows[(name, kind)]["scores"]["y"] == 0
    assert rows[("ab", "group")]["scores"]["y"] == pytest.approx(
        rows[("a", "input")]["scores"]["y"], rel=0.1
    )
    # masking e and f to -1 and 0 changes y by e + 1 where e is not already empty
    assert rows[("ef", "masked group")]["scores"]["y"] > 0.5
    # independent redraws of the same distribution give RMS = sqrt(2) std
    rng = np.random.default_rng(0)
    single = toy_evaluation(
        inputs=["a"],
        input_ranges={"a": {"mean": 0.0, "std": 1.0}},
        input_groups={},
        empty_values={},
        input_map={},
    )
    result = sensitivity_test(single, lambda d: {"y": d["a"]}, 20_000, seed=int(rng.integers(100)))
    assert result["variations"][0]["scores"]["y"] == pytest.approx(np.sqrt(2), rel=0.03)
    # sorted by the mean score, reproducible
    means = [r["mean"] for r in result["variations"]]
    assert means == sorted(means, reverse=True)


def test_reproducible_and_invalid_config():
    first = sensitivity_test(toy_evaluation(), toy_evaluate, N, seed=5)
    assert first == sensitivity_test(toy_evaluation(), toy_evaluate, N, seed=5)
    with pytest.raises(PythonFriendConfigError, match="no input_ranges entry"):
        sensitivity_test(
            toy_evaluation(input_ranges={"a": {"min": 0, "max": 1}}),
            toy_evaluate,
            N,
            seed=5,
        )


CONFIG = textwrap.dedent(
    """
    def build_config(era, sample_type, scope, shifts):
        return {
            "evaluations": [
                {"shift": "nominal", "model": "payloads/nominal.txt",
                 "inputs": ["tau_pt", "mvis"], "outputs": ["score"]},
                {"shift": "tauEsUp", "model": "payloads/up.txt",
                 "inputs": ["tau_pt", "mvis"], "outputs": ["score"],
                 "input_ranges": {"mvis": {"values": [91.0]}}},
            ],
            "input_map": {"tau_pt": "pt_1", "mvis": "m_vis"},
            "input_ranges": {
                "tau_pt": {"min": 20.0, "max": 100.0},
                "mvis": {"min": 50.0, "max": 150.0},
            },
            "batch_size": 300,
        }

    def load_model(path, evaluation):
        with open(path) as f:
            return float(f.read())

    def evaluate(model, data, evaluation):
        return {"score": model * data["tau_pt"]}
    """
)


def test_script(tmp_path):
    crown = tmp_path / "CROWN"
    analysis = crown / "analysis_configurations" / "toy_sensitivity"
    (analysis / "payloads").mkdir(parents=True)
    (analysis / "toy_sensitivity_friend.py").write_text(CONFIG)
    (analysis / "payloads" / "nominal.txt").write_text("1.0")
    (analysis / "payloads" / "up.txt").write_text("2.0")
    output = tmp_path / "scores.json"
    python_friend_sensitivity.run(
        python_friend_sensitivity.parse_args(
            [
                "--crown-path", str(crown),
                "--analysis", "toy_sensitivity",
                "--config", "toy_sensitivity_friend",
                "--era", "2018",
                "--sample-type", "dy",
                "--scope", "mt",
                "--shifts", "tauEs",
                "--n-samples", "1000",
                "--output", str(output),
            ]
        )
    )
    with open(output) as f:
        result = json.load(f)
    assert result["metadata"]["n_samples"] == 1000
    evaluations = result["evaluations"]
    assert set(evaluations) == {"nominal_0", "tauEsUp_1"}
    nominal = {r["name"]: r for r in evaluations["nominal_0"]["variations"]}
    assert nominal["tau_pt"]["scores"]["score"] > 1
    assert nominal["mvis"]["scores"]["score"] == 0
    # shift outputs are named like in the friend trees, the per evaluation range wins
    up = {r["name"]: r for r in evaluations["tauEsUp_1"]["variations"]}
    assert set(up["tau_pt"]["scores"]) == {"score__tauEsUp"}
    assert up["mvis"]["kind"] == "constant"
    assert evaluations["tauEsUp_1"]["outputs"]["score__tauEsUp"]["mean"] == pytest.approx(
        2 * evaluations["nominal_0"]["outputs"]["score"]["mean"]
    )


def test_plot(tmp_path):
    import plot_python_friend_sensitivity as plot

    files = []
    for seed in (1, 2):
        path = tmp_path / f"scores_{seed}.json"
        result = sensitivity_test(toy_evaluation(), toy_evaluate, 500, seed=seed)
        meta = {
            "python_friend_config": "toy", "era": "2018", "sample_type": "dy",
            "scope": "mt", "n_samples": 500, "seed": seed,
        }
        evaluation = {"shift": "nominal", "model": "toy.txt", **result}
        path.write_text(json.dumps({"metadata": meta, "evaluations": {"nominal_0": evaluation}}))
        files.append(str(path))
    output = tmp_path / "plot.png"
    plot.run(plot.parse_args([files[0], f"{files[1]}:seed 2", "--output", str(output)]))
    assert output.stat().st_size > 0
    assert plot.load(f"{files[1]}:seed 2", None)["label"] == "seed 2"
    assert plot.load(files[0], None)["label"] == "2018 dy mt"

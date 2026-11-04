"""
Tests for the python friend payload and its input resolution.

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
import uproot

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(BASE, "processor", "tasks"))
sys.path.insert(0, os.path.join(BASE, "processor", "tasks", "scripts"))

import run_python_friend  # noqa: E402
from helpers.python_friend_utils import (  # noqa: E402
    PythonFriendConfigError,
    get_evaluations,
    load_friend_config,
    quantities_map,
    resolve_inputs,
    shift_selected,
)

N = 2500

# toy "model": score = weight * sum of inputs; the weight is read from the model file
CONFIG = textwrap.dedent(
    """
    def build_config(era, sample_type, scope, shifts):
        return {
            "evaluations": [
                {"shift": "nominal", "model": "payloads/nominal.txt",
                 "inputs": NOMINAL_INPUTS, "outputs": ["score"]},
                {"shift": "tauEsUp", "model": "payloads/up.txt",
                 "inputs": ["tau_pt", "mvis"], "outputs": ["score"],
                 "input_map": {"tau_pt": "pt_1__tauEsUp"}},
                {"shift": "jesDown", "model": "payloads/nominal.txt",
                 "inputs": ["tau_pt", "mvis"], "outputs": ["score"]},
            ],
            "input_map": {"tau_pt": "pt_1", "mvis": "m_vis"},
            "batch_size": 1000,
        }

    def load_model(path, evaluation):
        with open(path) as f:
            return float(f.read())

    def evaluate(model, data, evaluation):
        if evaluation["shift"] == "broken":
            return {"score": data["tau_pt"][:-1]}
        return {"score": model * (data["tau_pt"] + data["mvis"])}
    """
)


def write_config(crown, nominal_inputs='["tau_pt", "mvis"]', replace=()):
    config = CONFIG.replace("NOMINAL_INPUTS", nominal_inputs)
    for old, new in replace:
        config = config.replace(old, new)
    path = crown / "analysis_configurations" / "toy" / "toy_friend.py"
    path.write_text(config)
    # the module cache would otherwise keep the config of a previous run
    for name in list(sys.modules):
        if name.startswith("analysis_configurations"):
            del sys.modules[name]


@pytest.fixture
def setup(tmp_path):
    crown = tmp_path / "CROWN"
    analysis = crown / "analysis_configurations" / "toy"
    (analysis / "payloads").mkdir(parents=True)
    write_config(crown)
    (analysis / "payloads" / "nominal.txt").write_text("1.0")
    (analysis / "payloads" / "up.txt").write_text("2.0")
    rng = np.random.default_rng(1)
    columns = {
        "event": np.arange(N, dtype=np.uint64),
        "pt_1": rng.uniform(20, 100, N).astype(np.float32),
        "m_vis": rng.uniform(50, 150, N).astype(np.float32),
    }
    columns["pt_1__tauEsUp"] = columns["pt_1"] * np.float32(1.03)
    ntuple = tmp_path / "ntuple.root"
    with uproot.recreate(ntuple) as f:
        f["ntuple"] = {k: v for k, v in columns.items() if k != "m_vis"}
    friend = tmp_path / "friend.root"
    with uproot.recreate(friend) as f:
        f["ntuple"] = {"m_vis": columns["m_vis"]}
    return tmp_path, crown, columns, ntuple, friend


def run(tmp_path, crown, ntuple, friend, shifts="None", extra=()):
    output = tmp_path / "out.root"
    args = run_python_friend.parse_args(
        [
            "--crown-path", str(crown),
            "--analysis", "toy",
            "--config", "toy_friend",
            "--era", "2018",
            "--sample-type", "dy",
            "--scope", "mt",
            "--shifts", shifts,
            "--input", str(ntuple),
            "--friend", str(friend),
            "--output", str(output),
            *extra,
        ]
    )  # fmt: skip
    run_python_friend.run(args)
    return uproot.open(output)


def test_nominal_with_input_map_and_friend(setup):
    tmp_path, crown, columns, ntuple, friend = setup
    out = run(tmp_path, crown, ntuple, friend)
    tree = out["ntuple"]
    assert tree.keys() == ["score"]
    assert tree.num_entries == N
    assert tree.title == "ntuple"
    np.testing.assert_allclose(
        tree["score"].array(library="np"), columns["pt_1"] + columns["m_vis"]
    )


def test_shift_models_and_selection(setup):
    tmp_path, crown, columns, ntuple, friend = setup
    tree = run(tmp_path, crown, ntuple, friend, shifts="tauEs")["ntuple"]
    assert sorted(tree.keys()) == ["score", "score__tauEsUp"]
    np.testing.assert_allclose(
        tree["score__tauEsUp"].array(library="np"),
        2.0 * (columns["pt_1__tauEsUp"] + columns["m_vis"]),
        rtol=1e-6,
    )
    tree = run(tmp_path, crown, ntuple, friend, shifts="All")["ntuple"]
    assert sorted(tree.keys()) == ["score", "score__jesDown", "score__tauEsUp"]


def test_max_events_and_info(setup):
    tmp_path, crown, columns, ntuple, friend = setup
    out = run(tmp_path, crown, ntuple, friend, extra=["--max-events", "1500"])
    assert out["ntuple"].num_entries == 1500
    info = json.loads(str(out["python_friend_info"]))
    assert info["nominal_0"]["columns"] == {"tau_pt": "pt_1", "mvis": "m_vis"}


def test_missing_column_and_empty_values(setup):
    tmp_path, crown, columns, ntuple, friend = setup
    write_config(
        crown,
        nominal_inputs='["tau_pt", "mvis", "njets"]',
        replace=[
            (
                '"batch_size": 1000,',
                '"batch_size": 1000, "empty_values": {"njets": -1},',
            )
        ],
    )
    with pytest.raises(RuntimeError, match="missing column 'njets'"):
        run(tmp_path, crown, ntuple, friend)
    write_config(
        crown,
        nominal_inputs='["tau_pt", "mvis", "njets"]',
        replace=[
            (
                '"batch_size": 1000,',
                '"batch_size": 1000, "empty_values": {"njets": -1},',
            )
        ],
    )
    out = run(tmp_path, crown, ntuple, friend, extra=["--allow-empty-values"])
    info = json.loads(str(out["python_friend_info"]))
    assert info["nominal_0"]["empty_values"] == {
        "njets": {"column": "njets", "value": -1}
    }


def test_wrong_output_length(setup):
    tmp_path, crown, columns, ntuple, friend = setup
    write_config(crown, replace=[('"shift": "jesDown"', '"shift": "broken"')])
    with pytest.raises(RuntimeError, match="has shape"):
        run(tmp_path, crown, ntuple, friend, shifts="broken")


def test_resolve_inputs():
    evaluation = {
        "inputs": ["a", "b", "n"],
        "input_map": {"a": "pt_1__up", "unused": "x"},
        "empty_values": {"n": 3, "b": 1.5},
    }
    result = resolve_inputs(evaluation, {"pt_1__up", "b"}, allow_empty=True)
    assert result["columns"] == {"a": "pt_1__up", "b": "b"}
    assert result["empty"] == {"n": ("n", 3)}
    assert any("unused" in w for w in result["warnings"])
    assert any("'b' ignored" in w for w in result["warnings"])
    result = resolve_inputs(evaluation, {"pt_1_up", "b"}, allow_empty=False)
    assert [(i, c) for i, c, _ in result["errors"]] == [("a", "pt_1__up"), ("n", "n")]
    assert "pt_1_up" in result["errors"][0][2]


def test_empty_array_dtypes():
    from helpers.python_friend_utils import empty_array

    assert empty_array(-1, 4).dtype == np.int32
    assert empty_array(-1.0, 4).dtype == np.float32


def test_shift_selection_and_quantities_map(setup):
    tmp_path, crown, *_ = setup
    assert shift_selected("nominal", ["none"])
    assert not shift_selected("tauEsUp", ["None"])
    assert shift_selected("tauEsUp", ["tauES"])
    module = load_friend_config(crown, "toy", "toy_friend")
    evaluations, batch_size = get_evaluations(module, "2018", "dy", "mt", "All")
    assert batch_size == 1000
    assert quantities_map(evaluations) == {
        "": ["score"],
        "__tauEsUp": ["score__tauEsUp"],
        "__jesDown": ["score__jesDown"],
    }


def test_missing_config(tmp_path):
    with pytest.raises(PythonFriendConfigError, match="not found"):
        load_friend_config(tmp_path, "toy", "nothing")


def test_quantities_map_file(setup):
    tmp_path, crown, columns, ntuple, friend = setup
    qmap = tmp_path / "qmap.json"
    run(
        tmp_path,
        crown,
        ntuple,
        friend,
        shifts="tauEs",
        extra=["--quantities-map", str(qmap)],
    )
    data = json.loads(qmap.read_text())
    assert data["quantities"]["2018"]["dy"]["mt"] == {
        "": ["score"],
        "__tauEsUp": ["score__tauEsUp"],
    }

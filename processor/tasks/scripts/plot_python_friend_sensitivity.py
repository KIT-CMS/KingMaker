#!/usr/bin/env python3
"""
Comparison plot of sensitivity test results (JSON files of PythonFriendSensitivity),
e.g. of different scopes, seeds, models or config versions.

One row per variation (input, group, masked input/group). Per file the marker is the
mean score over the outputs, the whiskers span the smallest and largest score of a
single output. Rows are sorted by the first file. The page ends with a short
explanation of how the scores were made.

Runs in the LCG view (matplotlib):
    python3 processor/tasks/scripts/plot_python_friend_sensitivity.py \\
        mt.json:mt et.json:et --output sensitivity.pdf
"""

import argparse
import json
import math
import os
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# validated categorical palette (light surface), fixed order; markers as second encoding
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MARKERS = ["o", "s", "D", "^", "v", "P", "X", "h"]
TEXT = "#1f1f1e"
MUTED = "#6b6a63"
GRID = "#e4e3dd"
SECTIONS = [
    ("input", "Inputs (redrawn one at a time)"),
    ("group", "Input groups (redrawn together)"),
    ("masked", "Masked (set to empty_values, as in the production)"),
]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "files", nargs="+", help="JSON files of the sensitivity test, optionally as file:label"
    )
    parser.add_argument(
        "--evaluation", default=None, help="evaluation to plot (default: the nominal one)"
    )
    parser.add_argument(
        "--output", required=True, nargs="+", help="plot file(s), e.g. .pdf and .png"
    )
    parser.add_argument("--title", default=None)
    parser.add_argument(
        "--hide-constant", action="store_true", help="drop inputs fixed to one value"
    )
    return parser.parse_args(argv)


def split_label(spec):
    path, _, label = spec.partition(":") if not os.path.exists(spec) else (spec, "", "")
    return path, label


def load(spec, evaluation_name):
    path, label = split_label(spec)
    with open(path) as f:
        content = json.load(f)
    evaluations = content["evaluations"]
    if evaluation_name is None:
        evaluation_name = next(
            (n for n, e in evaluations.items() if e["shift"] == "nominal"), next(iter(evaluations))
        )
    if evaluation_name not in evaluations:
        raise KeyError(f"{path} has no evaluation '{evaluation_name}', only {list(evaluations)}")
    meta = content["metadata"]
    if not label:
        label = f"{meta['era']} {meta['sample_type']} {meta['scope']}"
    return {"label": label, "meta": meta, "evaluation": evaluations[evaluation_name]}


def section(kind):
    return "masked" if kind.startswith("masked") else ("input" if kind == "constant" else kind)


def row_label(row):
    label = row["name"]
    if row["kind"] == "constant":
        label += " (constant)"
    if row["kind"] == "group" or row["kind"] == "masked group":
        label += f" [{len(row['members'])}]"
    return label


def explanation(results):
    meta = results[0]["meta"]
    outputs = list(results[0]["evaluation"]["outputs"])
    samples = sorted({(r["meta"]["n_samples"], r["meta"]["seed"]) for r in results})
    samples = ", ".join(f"N = {n} (seed {s})" for n, s in samples)
    text = (
        f"How the scores were made. {samples} random events are drawn from the input_ranges "
        f"of the config '{meta['python_friend_config']}' (build_config() called for "
        f"{', '.join(sorted({r['meta']['era'] + ' ' + r['meta']['sample_type'] for r in results}))}), "
        "every input independently, and "
        "evaluated with the config's own evaluate() (so derived features, rotations and "
        "the masking of empty values are exactly as in the production). For every row, "
        "the listed inputs are drawn again (or set to their empty_values for the masked "
        "rows) while all others keep their values, and the model is evaluated again. "
        "Score per output y: RMS(y_varied − y) / std(y). 0: the output does not change; "
        "√2 ≈ 1.41: the output changes as much as between two independent events, i.e. "
        "it is fully driven by these inputs. Marker: mean over the outputs "
        f"({', '.join(outputs)}); whiskers: smallest and largest single output. "
        "Masked rows show what replacing the inputs by their empty_values (as for "
        "inputs missing in the ntuples) changes. Caveat: the inputs are uncorrelated, "
        "so the scores show how the model responds over the given ranges (a wider range "
        "gives a larger score), not the importance on real events."
    )
    return text


def plot(results, outputs, title=None, hide_constant=False):
    reference = results[0]["evaluation"]["variations"]
    keys = [(r["name"], r["kind"]) for r in reference]
    if hide_constant:
        keys = [k for k in keys if k[1] != "constant"]
    rows = []
    for result in results:
        by_key = {(r["name"], r["kind"]): r for r in result["evaluation"]["variations"]}
        rows.append(by_key)
    sections = [
        (title_, [k for k in keys if section(k[1]) == name]) for name, title_ in SECTIONS
    ]
    sections = [(t, k) for t, k in sections if k]

    n_rows = sum(len(k) for _, k in sections)
    text = textwrap.fill(explanation(results), 150)
    text_height = 0.16 * (text.count("\n") + 1) + 0.3
    height = 1.3 + 0.24 * n_rows + 0.45 * len(sections) + text_height
    fig = plt.figure(figsize=(10, height))
    top = 1 - 0.9 / height
    bottom = (text_height + 0.45) / height
    grid = fig.add_gridspec(
        len(sections), 1, height_ratios=[len(k) + 0.6 for _, k in sections],
        top=top, bottom=bottom, left=0.25, right=0.97,
        # hspace is relative to the mean axis height: 0.45 inch between the sections
        hspace=0.45 / ((top - bottom) * height / len(sections)),
    )
    largest = max(
        (r[k]["max"] for r in rows for _, ks in sections for k in ks if k in r and math.isfinite(r[k]["max"])),
        default=1.5,
    )
    xmax = max(1.5, largest * 1.05)
    n_files = len(results)
    offsets = [0.0] if n_files == 1 else [(i - (n_files - 1) / 2) * min(0.6 / (n_files - 1), 0.2) for i in range(n_files)]
    axes = []
    for index, (section_title, section_keys) in enumerate(sections):
        ax = fig.add_subplot(grid[index])
        axes.append(ax)
        for y, key in enumerate(section_keys):
            if y % 2 == 0:
                ax.axhspan(y - 0.5, y + 0.5, color="#f4f3ef", lw=0, zorder=0)
            for i, by_key in enumerate(rows):
                if key not in by_key:
                    continue
                row = by_key[key]
                yy = y + offsets[i]
                finite = [v for v in row["scores"].values() if math.isfinite(v)]
                ax.plot([min(finite, default=row["mean"]), row["max"]], [yy, yy],
                        color=COLORS[i % len(COLORS)], lw=1.2, alpha=0.6, solid_capstyle="round", zorder=2)
                ax.plot(row["mean"], yy, MARKERS[i % len(MARKERS)], color=COLORS[i % len(COLORS)],
                        ms=5.5, mec="white", mew=0.8, zorder=3)
        ax.set_yticks(range(len(section_keys)))
        ax.set_yticklabels([row_label(rows[0][k]) for k in section_keys], fontsize=8, color=TEXT)
        ax.set_ylim(len(section_keys) - 0.5, -0.5)
        ax.set_xlim(0, xmax)
        ax.axvline(math.sqrt(2), color=MUTED, lw=0.8, ls=(0, (3, 3)), zorder=1)
        ax.grid(axis="x", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="x", labelsize=8, colors=MUTED, length=0)
        ax.tick_params(axis="y", length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.set_title(section_title, loc="left", fontsize=9.5, color=TEXT, fontweight="bold")
        if index != len(sections) - 1:
            ax.tick_params(axis="x", labelbottom=False)
    axes[0].text(math.sqrt(2), -0.6, "fully driven: √2 ", fontsize=7.5, color=MUTED, va="bottom", ha="right")
    axes[-1].set_xlabel("score = RMS(y_varied − y) / std(y)   (marker: mean over outputs, whiskers: min – max)",
                        fontsize=8.5, color=TEXT)

    meta = results[0]["meta"]
    evaluation = results[0]["evaluation"]
    fig.suptitle(
        title or f"Sensitivity of {meta['python_friend_config']} ({evaluation['model']})",
        x=0.02, y=1 - 0.25 / height, ha="left", fontsize=12, color=TEXT, fontweight="bold",
    )
    if n_files > 1:
        handles = [
            plt.Line2D([], [], marker=MARKERS[i % len(MARKERS)], color=COLORS[i % len(COLORS)],
                       mec="white", ms=7, lw=1.2, label=r["label"])
            for i, r in enumerate(results)
        ]
        fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.02, 1 - 0.5 / height),
                   ncol=min(n_files, 4), frameon=False, fontsize=8.5)
    else:
        fig.text(0.02, 1 - 0.55 / height, results[0]["label"], fontsize=9, color=MUTED, va="top")
    fig.text(0.02, 0.2 / height, text, fontsize=7.5, color=MUTED, va="bottom", ha="left", linespacing=1.4)
    for output in outputs:
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
        fig.savefig(output, dpi=150)
        print(f"Plot written to {output}")
    plt.close(fig)


def run(args):
    results = [load(spec, args.evaluation) for spec in args.files]
    plot(results, args.output, args.title, args.hide_constant)


if __name__ == "__main__":
    run(parse_args())

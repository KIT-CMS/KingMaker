import os

import argparse
from rich.table import Table
from rich import print
from rich.live import Live
from rich.console import Console
from datetime import datetime
import time
import sys


def parse_args_from_law():
    arguments = sys.argv
    if arguments[1] != "law" or arguments[2] != "run" or len(arguments) < 4:
        print(
            "Wrong usage of script, to run it, just add <monitor_production> in front of your law command."
        )
        print("Usage: monitor_production <your_full_law_command>")
        print(
            "Example: monitor_production law run ProduceSamples --analysis tau --config config --sample-list samples_18.txt --production-tag best_samples_eu --workers 100 --scopes mt --shifts None"
        )
        raise ValueError("Wrong script usage.")
    args_dict = {}
    for i in range(1, len(arguments)):
        if arguments[i].startswith("--"):
            args_dict[arguments[i].replace("--", "")] = arguments[i + 1]
    return args_dict, arguments[3]


def parse_law(args_dict, task):
    # build the law command
    detailed_mapping = {
        "ProduceSamples": "CROWNRun",
        "ProduceFriends": "CROWNFriends",
        "ProduceMultiFriends": "CROWNMultifriends",
    }
    arguments = [f"--{key} {value}" for key, value in args_dict.items()]

    law_cmd = f"law run {task} {' '.join(arguments)} --print-status -1"
    # now run the law command using subprocess and store the output in a variable
    output = os.popen(law_cmd).read()
    data = {}
    # now parse output line by line
    lines = output.split("\n")
    parsing_sample = False
    for i, line in enumerate(lines):
        # if CROWNRun is in the line, we get the status of a new sample
        # print(parsing_sample, line)
        if not parsing_sample:
            if f"> {detailed_mapping[task]}" in line:
                parsing_sample = True
                # find out the samplename
                samplename = line.split("nick=")[1].split(",")[0]
                data[samplename] = {}
                continue
        if parsing_sample:
            if "NestedSiblingFileCollection" in line:
                statusline = lines[i + 1]
                result = statusline[statusline.find("(") + 1 : statusline.find(")")]
                data[samplename]["done"] = int(result.split("/")[0])
                data[samplename]["total"] = int(result.split("/")[1])
                parsing_sample = False
    return data


def build_table(new_data, old_data=None, skip_finished=True):
    now = datetime.now()

    table = Table(
        title=f"Sample Status (updated: {now.strftime('%d/%m/%Y, %H:%M:%S')}, refreshing roughly minute )",
        highlight=True,
    )
    if skip_finished:
        table.add_column(
            "Sample (only showing samples that are not done yet)", justify="right"
        )
    else:
        table.add_column("Sample", justify="right")
    table.add_column("Done", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Percent", justify="right")
    # add a total row at the end with the sum of all percentual completion
    total_done = sum([new_data[sample]["done"] for sample in new_data])
    total_total = sum([new_data[sample]["total"] for sample in new_data])
    percent_total = str(int(float(total_done) / float(total_total) * 100)) + "%"

    if old_data is not None:
        total_total_old = sum([old_data[sample]["total"] for sample in old_data])
        style = "green bold" if total_total != total_total_old else None
    else:
        style = None

    table.add_row(
        "Total (including finished samples)",
        str(total_done),
        str(total_total),
        percent_total,
        style=style,
    )

    for sample in new_data:
        done = new_data[sample]["done"]
        total = new_data[sample]["total"]
        percent = int(float(done) / float(total) * 100)
        if skip_finished:
            if done == total:
                continue
        if old_data is not None:
            percent_old = int(
                float(old_data[sample]["done"]) / float(old_data[sample]["total"]) * 100
            )
            style = "green bold" if percent != percent_old else None
        else:
            style = None

        table.add_row(sample, str(done), str(total), str(percent) + "%", style=style)
    return table


if __name__ == "__main__":
    args_dict, task = parse_args_from_law()
    live = True
    skip_finished = True
    console = Console()
    if live:
        print("Getting live updates...")
        old_data = parse_law(args_dict, task)
        with Live(
            build_table(parse_law(args_dict, task), old_data, skip_finished),
            auto_refresh=False,
            console=console,
            screen=True,
        ) as live:
            while True:
                live.update(
                    build_table(parse_law(args_dict, task), old_data, skip_finished),
                    refresh=True,
                )
                time.sleep(30)
    else:
        print(build_table(parse_law(args_dict, task)), skip_finished)

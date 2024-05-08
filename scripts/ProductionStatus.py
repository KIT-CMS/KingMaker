import os
from rich.table import Table
from rich import print as rprint
from rich.live import Live
from rich.console import Console
from datetime import datetime
import time
import sys
import shlex


def parse_args_from_law():
    """
    The function `parse_args_from_law` parses command line arguments for a script with specific
    requirements related to a "law" command.
    :return: The function `parse_args_from_law` returns a tuple containing two elements:
    1. `args_dict`: a dictionary containing the arguments passed to the script in the format of
    key-value pairs where the key is the argument name (without the leading "--") and the value is the
    argument value.
    2. `arguments[3]`: the fourth argument passed to the script which is the name of the law task to run.
    """
    arguments = sys.argv
    if arguments[1] != "law" or arguments[2] != "run" or len(arguments) < 4:
        rprint(
            """
        Wrong usage of script, to run it, just add <monitor_production> in front of your law command.
        Usage: monitor_production <your_full_law_command>
        Example: monitor_production law run ProduceSamples --analysis tau --config config --sample-list samples_18.txt --production-tag best_samples_eu --workers 100 --scopes mt --shifts None
        """
        )
        raise ValueError("Wrong script usage.")
    args_dict = {}
    for i in range(1, len(arguments)):
        if arguments[i].startswith("--"):
            args_dict[arguments[i].replace("--", "")] = arguments[i + 1]
    return args_dict, arguments[3]


def parse_law(arguments, task):
    """
    This Python function `parse_law` takes arguments and a task, constructs a law command, runs it using
    subprocess, parses the output to extract sample data, and returns a dictionary of sample statuses.

    :param arguments:
    :param task:
    :return: The function `parse_law` returns a dictionary containing information about the status of
    samples processed by a law command. The keys of the dictionary are the sample names, and the values
    are dictionaries with keys "done" and "total" representing the number of completed and total tasks
    for each sample, respectively.
    """
    # build the law command
    detailed_mapping = {
        "ProduceSamples": "CROWNRun",
        "ProduceFriends": "CROWNFriends",
        "ProduceMultiFriends": "CROWNMultifriends",
    }
    argument = [f"--{key} {value}" for key, value in arguments.items()]

    law_cmd = f"law run {task} {' '.join(argument)} --print-status -1"
    # now run the law command using subprocess and store the output in a variable
    output = os.popen(law_cmd).read()
    data = {}
    # now parse output line by line
    lines = output.split("\n")
    parsing_sample = False
    for i, line in enumerate(lines):
        # if CROWNRun is in the line, we get the status of a new sample
        # print(parsing_sample, line)
        if not parsing_sample and f"> {detailed_mapping[task]}" in line:
            parsing_sample = True
            # find out the samplename
            samplename = line.split("nick=")[1].split(",")[0]
            data[samplename] = {}
            continue
        if parsing_sample and "NestedSiblingFileCollection" in line:
            statusline = lines[i + 1]
            result = statusline[statusline.find("(") + 1 : statusline.find(")")]
            data[samplename]["done"] = int(result.split("/")[0])
            data[samplename]["total"] = int(result.split("/")[1])
            parsing_sample = False
    return data


def build_table(new_data, old_data=None, skip_finished=True):
    """
    The `build_table` function creates a table displaying sample status information, with an option to
    skip showing finished samples.

    :param new_data: The `new_data` parameter is a dictionary containing information about samples. Each
    key in the dictionary represents a sample, and the corresponding value is another dictionary with
    keys "done" and "total" representing the number of tasks done and the total number of tasks for that
    sample, respectively
    :param old_data: The `old_data` parameter in the `build_table` function is used to provide data from
    a previous time point for comparison with the new data. This allows for tracking changes in the
    status of samples over time, such as the progress made on each sample. If `old_data` is provided,
    :param skip_finished: The `skip_finished` parameter in the `build_table` function determines whether
    to skip showing samples that are already marked as done. If `skip_finished` is set to `True`, only
    samples that are not done yet will be displayed in the table. If it is set to `False`, all, defaults
    to True (optional)
    :return: The function `build_table` returns a Table object that displays the status of samples,
    including information such as sample name, done count, total count, and completion percentage. The
    table also includes a total row showing the overall progress of all samples.
    """
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
    total_done = sum((new_data[sample]["done"] for sample in new_data))
    total_total = sum((new_data[sample]["total"] for sample in new_data))
    percent_total = str(int(float(total_done) / float(total_total) * 100)) + "%"

    if old_data is not None:
        total_total_old = sum((old_data[sample]["total"] for sample in old_data))
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
        if skip_finished and done == total:
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
    args_dict, taskname = parse_args_from_law()
    live = True
    skip = True
    console = Console()
    if live:
        rprint("Getting live updates...")
        previous_data = parse_law(args_dict, taskname)
        with Live(
            build_table(parse_law(args_dict, taskname), previous_data, skip),
            auto_refresh=False,
            console=console,
            screen=True,
        ) as live:
            while True:
                live.update(
                    build_table(parse_law(args_dict, taskname), previous_data, skip),
                    refresh=True,
                )
                time.sleep(30)
    else:
        rprint(build_table(parse_law(args_dict, taskname)), skip)

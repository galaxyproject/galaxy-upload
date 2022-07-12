#!/usr/bin/env python3
"""Upload files to a Galaxy instance."""
import datetime
import re

import click
import rich.console
import rich.table
from bioblend.galaxy import GalaxyInstance


def make_table(quiet, histories=None):
    histories = histories or []
    # table setup
    if quiet:
        table = rich.table.Table(show_header=False, show_edge=False)
        table.add_column("ID", no_wrap=True)
    else:
        table = rich.table.Table(title="Active Histories")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="magenta")
        table.add_column("Last Modified", style="green")
    # add rows
    for history in histories:
        if quiet:
            row = (history["id"],)
        else:
            name = history["name"]
            update_time = datetime.datetime.fromisoformat(
                history["update_time"]
            ).strftime("%c")
            row = (
                history["id"],
                name,
                update_time,
            )
        table.add_row(*row)
    return table


def get_histories(gi, ignore_case=False, name=None):
    if name:
        if ignore_case:
            name_re = re.compile(name, flags=re.IGNORECASE)
        else:
            name_re = re.compile(name)

    # the "name" option to get_histories() only does exact matching, so we filter results ourselves
    histories = []
    for history in gi.histories.get_histories():
        if not name or name_re.search(history["name"]):
            histories.append(history)

    return histories


@click.command()
@click.option(
    "--url",
    envvar="GALAXY_URL",
    default="http://localhost:8080",
    help="URL of Galaxy instance",
)
@click.option(
    "--api-key",
    envvar="GALAXY_API_KEY",
    required=True,
    help="API key for Galaxy instance",
)
@click.option("--quiet", "-q", is_flag=True, help="Only output history IDs")
@click.option(
    "--ignore-case", "-i", is_flag=True, help="Ignore case when matching history names"
)
@click.argument("name", required=False)
def main(
    url,
    api_key,
    quiet,
    ignore_case,
    name,
):
    gi = GalaxyInstance(url, api_key)
    histories = get_histories(gi, ignore_case, name)
    table = make_table(quiet, histories=histories)
    console = rich.console.Console()
    console.print(table)


if __name__ == "__main__":
    main()

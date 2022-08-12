#!/usr/bin/env python3
"""Upload files to a Galaxy instance."""
import os
import sys
import traceback

import click
import rich.console
import rich.progress
from bioblend import ConnectionError
from bioblend.galaxy import GalaxyInstance
from click_option_group import RequiredMutuallyExclusiveOptionGroup, optgroup
from tusclient.fingerprint import fingerprint

from .history import get_histories, make_table


def make_bar(file_name, total=None):
    columns = (
        rich.progress.TextColumn("[progress.description]{task.description}"),
        rich.progress.BarColumn(),
        rich.progress.DownloadColumn(),
        rich.progress.TransferSpeedColumn(),
        rich.progress.TextColumn("eta"),
        rich.progress.TimeRemainingColumn(),
    )

    bar = rich.progress.Progress(*columns)
    task_id = bar.add_task(file_name, total=total)
    return (bar, task_id)


def find_history(gi, history_name, ignore_case):
    histories = get_histories(gi, ignore_case=ignore_case, name=history_name)
    if not histories:
        message = f"ERROR: No histories matching {history_name} found!"
        click.echo(click.style(message, bold=True, fg="red"), err=True)
        sys.exit(1)
    elif len(histories) > 1:
        table = make_table(quiet=False, histories=histories)
        console = rich.console.Console()
        console.print(table)
        message = f"ERROR: Multiple histories matching {history_name} found! Use --history-id to select one."
        click.echo(click.style(message, bold=True, fg="red"), err=True)
        sys.exit(1)
    return histories[0]


def upload_file(
    url,
    path,
    api_key,
    history_id=None,
    history_name=None,
    ignore_case=False,
    file_type="auto",
    dbkey="?",
    space_to_tab=False,
    auto_decompress=False,
    file_name=None,
    storage=None,
    silent=False,
    debug=False,
):
    file_name = file_name or os.path.basename(path)

    gi = GalaxyInstance(url, api_key)

    upload_kwargs = {
        "file_type": file_type,
        "dbkey": dbkey,
        "file_name": file_name,
        "space_to_tab": space_to_tab,
        "auto_decompress": auto_decompress,
    }

    if not history_id:
        history = find_history(gi, history_name, ignore_case)
        history_id = history["id"]
        if debug:
            click.echo(
                f"History name search '{history_name}' resolved to history {history_id}: {history['name']}"
            )

    try:
        if silent:
            gi.tools.upload_file_tus(
                path,
                history_id,
                storage=storage,
                **upload_kwargs,
            )
            return

        uploader = gi.get_tus_uploader(
            path,
            storage=storage,
        )
        file_size = uploader.get_file_size()
        bar, task_id = make_bar(file_name, total=file_size)

        with bar:
            last_offset = 0
            while uploader.offset < file_size:
                uploader.upload_chunk()
                bar.update(task_id, advance=(uploader.offset - last_offset))
                last_offset = uploader.offset

        gi.tools.post_to_fetch(path, history_id, uploader.session_id, **upload_kwargs)

    except ConnectionError as exc:
        if exc.status_code == 404 and storage:
            fingerprinter = fingerprint.Fingerprint()
            with open(path, "rb") as fh:
                fp_hash = fingerprinter.get_fingerprint(fh)
            message = (
                f"Unable to resume, previous upload may have been removed from server (hint: remove {fp_hash}"
                f" from {storage} or change storage to reupload from the start: {exc}"
            )
        else:
            message = str(exc)
        message = f"ERROR: {message}"
        if debug:
            click.echo(traceback.format_exc(), nl=False)
        click.echo(click.style(message, bold=True, fg="red"), err=True)


@click.command()
@optgroup.group("History Selection Options", cls=RequiredMutuallyExclusiveOptionGroup)
@optgroup.option("--history-id", type=str, help="Target history ID")
@optgroup.option("--history-name", type=str, help="Target history name")
@optgroup.group("History Options")
@optgroup.option(
    "--ignore-case", "-i", is_flag=True, help="Ignore case when matching history names"
)
@optgroup.group("Galaxy Server Options")
@optgroup.option(
    "--url",
    envvar="GALAXY_URL",
    default="http://localhost:8080",
    help="URL of Galaxy instance",
)
@optgroup.option(
    "--api-key",
    envvar="GALAXY_API_KEY",
    required=True,
    help="API key for Galaxy instance",
)
@optgroup.group("Upload Options")
@optgroup.option(
    "--file-type", default="auto", type=str, help="Galaxy file type to use"
)
@optgroup.option("--dbkey", default="?", type=str, help="Genome Build for dataset")
@optgroup.option(
    "--space-to-tab/--no-space-to-tab", default=False, help="Convert spaces to tabs"
)
@optgroup.option(
    "--auto-decompress/--no-auto-decompress",
    default=True,
    help="Automatically decompress after upload",
)
@optgroup.option(
    "--file-name",
    type=str,
    help="Filename to use in Galaxy history, if different from path",
)
@optgroup.group("General Options")
@optgroup.option(
    "--storage", type=click.Path(), required=False, help="Store URLs to resume here"
)
@optgroup.option(
    "--silent", is_flag=True, default=False, help="No output while uploading"
)
@optgroup.option("--debug", is_flag=True, default=False, help="Debug output")
@click.argument("path", type=click.Path(), nargs=-1)
def main(url, path, api_key, **kwargs):
    paths = path
    if not paths:
        message = "WARNING: No paths to upload specified (see --help)"
        click.echo(click.style(message, bold=True, fg="yellow"), err=True)
    elif len(paths) > 1 and kwargs["file_name"]:
        message = "ERROR: --file-name option cannot be used with multiple paths"
        click.echo(click.style(message, bold=True, fg="red"), err=True)
        sys.exit(1)
    for path in paths:
        upload_file(url, path, api_key, **kwargs)


if __name__ == "__main__":
    main()

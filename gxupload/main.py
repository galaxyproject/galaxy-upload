#!/usr/bin/env python3
"""Upload files to a Galaxy instance."""
import os
import traceback

import click
from rich import progress
from tusclient.fingerprint import fingerprint

from bioblend import ConnectionError
from bioblend.galaxy import GalaxyInstance

from .history import get_histories


def make_bar(filename, total=None):
    columns = (
        progress.TextColumn("[progress.description]{task.description}"),
        progress.BarColumn(),
        progress.DownloadColumn(),
        progress.TransferSpeedColumn(),
        progress.TextColumn("eta"),
        progress.TimeRemainingColumn(),
    )

    bar = progress.Progress(*columns)
    task_id = bar.add_task(filename, total=total)
    return (bar, task_id)


@click.command()
@click.option("--url", default="http://localhost:8080", help="URL of Galaxy instance")
@click.option("--api-key", envvar="GALAXY_API_KEY", required=True, help="API key for Galaxy instance")
@click.option("--history-id", type=str, required=True, help="Target History ID")
# TODO: make a mutually exclusive option --history-name that uses get_histories and automatically determines the history
# ID if there is only one match
@click.option("--file-type", default="auto", type=str, help="Galaxy file type to use")
@click.option("--dbkey", default="?", type=str, help="Genome Build for dataset")
@click.option("--space-to-tab/--no-space-to-tab", default=False, help="Convert spaces to tabs")
@click.option("--auto-decompress/--no-auto-decompress", default=True, help="Automatically decompress after upload")
@click.option("--filename", type=str, help="Filename to use in Galaxy history, if different from path")
@click.option("--storage", type=click.Path(), required=False, help="Store URLs to resume here")
@click.option("--silent/--no-silent", default=False, help="No output while uploading")
@click.option("--debug/--no-debug", default=False, help="Debug output")
@click.argument("path", type=click.Path())
def upload_file(
    url,
    path,
    api_key,
    history_id,
    file_type="auto",
    dbkey="?",
    space_to_tab=False,
    auto_decompress=False,
    filename=None,
    storage=None,
    silent=False,
    debug=False,
):
    gi = GalaxyInstance(url, api_key)

    upload_kwargs = {
        "file_type": file_type,
        "dbkey": dbkey,
        "file_name": filename,
        "space_to_tab": space_to_tab,
        "auto_decompress": auto_decompress,
    }

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
        # TODO: this is uploader.get_file_size() in tusclient 1.0.0
        bar, task_id = make_bar(filename or os.path.basename(path), total=uploader.file_size)

        with bar:
            last_offset = 0
            while uploader.offset < uploader.file_size:
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


if __name__ == "__main__":
    upload_file()

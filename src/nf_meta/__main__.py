import click
from functools import wraps
from pathlib import Path
from nf_meta.core.errors import (
    ConfigValidationError,
    GraphValidationError,
    format_errors_for_cli,
)
from nf_meta.runner import get_registered_runners
from nf_meta.core.graph import from_file
from nf_meta.editor import get_registered_editors


def handle_validation_errors(func):
    """Shared error handling for commands taking a `config` path: renders any
    validation failure through the unified format_errors_for_cli, with real
    line numbers when the config file can be read as text."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        config = kwargs.get("config")
        try:
            return func(*args, **kwargs)
        except (GraphValidationError, ConfigValidationError) as e:
            source_text = None
            if config:
                try:
                    source_text = Path(config).read_text()
                except OSError:
                    source_text = None
            click.echo(
                format_errors_for_cli(
                    e, source_text=source_text, filename=str(config or "")
                )
            )
            raise SystemExit(1)
        except FileNotFoundError as e:
            click.echo(click.style(str(e), fg="red"))
            raise SystemExit(1)

    return wrapper


@click.group()
@click.version_option()
def cli() -> None:
    return


@click.command("editor")
@click.option("--verbose", "-v", is_flag=True, help="Enables verbose mode")
@click.option(
    "--editor",
    "-e",
    type=click.Choice(get_registered_editors()),
    default="browser",
    help="Editor backend to use",
)
@click.option("--host", help="Host to bind the editor server to")
@click.option(
    "--port",
    type=int,
    help="Port for the editor server (auto-assigned if omitted)",
)
@click.argument("config", required=False, type=click.Path())
@handle_validation_errors
def edit_browser(config, verbose, editor, host, port):
    from nf_meta.editor import EditorOptions, run_editor
    from nf_meta.core.session import start_session

    start_session(config)
    opts = EditorOptions(editor_name=editor)
    if host is not None:
        opts.host = host
    if port is not None:
        opts.port = port
    run_editor(opts)


@click.command("validate")
@click.argument("config", type=click.Path())
@click.option("--verbose", "-v", is_flag=True, help="Enables verbose mode")
@handle_validation_errors
def validate_config(config, verbose):
    g = from_file(config)
    click.echo(click.style("✓ Config is valid", fg="green"))


@click.command("run")
@click.argument("config", type=click.Path())
@click.option("--verbose", "-v", is_flag=True, help="Enables verbose mode")
@click.option(
    "--runner",
    "-r",
    prompt=True,
    type=click.Choice(get_registered_runners()),
    default="python",
)
@click.option("--resume", is_flag=True, help="Resume a previous run")
@click.option(
    "--output-lines",
    "-l",
    default="25",
    type=int,
    help="Number of lines of workflow output to stream to output window (Only for Python Runner!)",
)
@click.option("--start", "-s", type=str, help="ID of workflow to start from")
@click.option("--target", "-t", type=str, help="ID of workflow to run until")
@click.option(
    "--profile",
    "-p",
    type=str,
    help="Nextflow profile to apply globally, taking precedent over config values.",
)
@click.option(
    "--stub",
    is_flag=True,
    help="Run all workflows as stub runs (passes -stub to Nextflow)",
)
@handle_validation_errors
def run(config, verbose, runner, resume, output_lines, start, target, profile, stub):
    from nf_meta.runner import run_metapipeline, RunOptions, NfMetaRunnerError

    try:
        run_options = RunOptions(
            runner_name=runner,
            verbose=verbose,
            output_lines=output_lines,
            nf_profile=profile,
            stub=stub,
            resume=resume,
            start=start,
            target=target,
        )
        g = from_file(config)
        run_metapipeline(g, run_options)
    except NfMetaRunnerError as e:
        click.echo(click.style(e.message, fg="red"))
        raise SystemExit(1)


cli.add_command(edit_browser)
cli.add_command(validate_config)
cli.add_command(run)


if __name__ == "__main__":
    cli()

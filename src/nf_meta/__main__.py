import click
from functools import wraps
from nf_meta.core.errors import (
    GraphValidationError,
    ValidationError,
    format_errors_for_cli,
)
from nf_meta.runner import (
    run_metapipeline,
    get_registered_runners,
    RunOptions,
    NfMetaRunnerError,
)
from nf_meta.core.graph import MetaworkflowGraph
from nf_meta.core.session import start_session
from nf_meta.editor import get_registered_editors, EditorOptions, run_editor


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
def edit_browser(config, verbose, editor, host, port):
    try:
        start_session(config)
        opts = EditorOptions(editor_name=editor)
        if host is not None:
            opts.host = host
        if port is not None:
            opts.port = port
        run_editor(opts)
    except (GraphValidationError, ValidationError) as e:
        click.echo(format_errors_for_cli(e))
        raise SystemExit(1)
    except FileNotFoundError as e:
        click.echo(click.style(e, fg="red"))
        raise SystemExit(1)


@click.command("validate")
@click.argument("config", type=click.Path())
@click.option("--verbose", "-v", is_flag=True, help="Enables verbose mode")
def validate_config(config, verbose):
    try:
        g = MetaworkflowGraph.from_file(config)
        click.echo(click.style("✓ Config is valid", fg="green"))
    except (GraphValidationError, ValidationError) as e:
        click.echo(format_errors_for_cli(e))
        raise SystemExit(1)
    except FileNotFoundError as e:
        click.echo(click.style(e, fg="red"))
        raise SystemExit(1)


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
def run(config, verbose, runner, resume, output_lines, start, target, profile, stub):
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
        g = MetaworkflowGraph.from_file(config)
        run_metapipeline(g, run_options)
    except (GraphValidationError, ValidationError) as e:
        click.echo(format_errors_for_cli(e))
        raise SystemExit(1)
    except NfMetaRunnerError as e:
        click.echo(click.style(e.message, fg="red"))
        raise SystemExit(1)
    except FileNotFoundError as e:
        click.echo(click.style(e, fg="red"))
        raise SystemExit(1)


cli.add_command(edit_browser)
cli.add_command(validate_config)
cli.add_command(run)


if __name__ == "__main__":
    cli()

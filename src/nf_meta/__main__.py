import click
from functools import wraps
from nf_meta.engine.errors import GraphValidationError, ValidationError, format_errors_for_cli
from nf_meta.runner import run_metapipeline, Runners, NfMetaRunnerError
from nf_meta.engine.graph import MetaworkflowGraph
from nf_meta.engine.session import start_session
from nf_meta.editor import start_editor_backend

@click.group()
@click.version_option()
def cli() -> None:
    return

@click.command("editor")
@click.option('--verbose', '-v', is_flag=True, help="Enables verbose mode")
@click.option("--host", default="localhost", help="Host to use for running the editor ui")
@click.option("--port", help="Port to use for running the editor ui")
@click.argument("config", required=False, type=click.Path())
def edit_browser(config, verbose, host, port):
    try:
        # start engine
        start_session(config)

        # start api and open editor in browser
        start_editor_backend(host, port)

    except (GraphValidationError, ValidationError) as e:
        click.echo(format_errors_for_cli(e))
        raise SystemExit(1)
    except FileNotFoundError as e:
        click.echo(click.style(e, fg="red"))
        raise SystemExit(1)

@click.command("validate")
@click.argument("config", type=click.Path())
@click.option('--verbose', '-v', is_flag=True, help="Enables verbose mode")
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
@click.option('--verbose', '-v', is_flag=True, help="Enables verbose mode")
@click.option("--runner", "-r", prompt=True, type=click.Choice([e.value for e in Runners]), default=Runners.PYTHON.value)
@click.option("--resume", is_flag=True, help="Resume a previous run")
@click.option("--output-lines", "-l", type=int, help="Number of lines of workflow output to stream to output window (Only for Python Runner!)")
@click.option("--start", "-s", type=str, help="ID of workflow to start from")
@click.option("--target", "-t", type=str, help="ID of workflow to run until")
@click.option("--profile", "-p", type=str, help="Nextflow profile to apply globally, taking precedent over config values.")
def run(config, verbose, runner, resume, output_lines, start, target, profile):
    try:
        g = MetaworkflowGraph.from_file(config)
        run_metapipeline(g,
                         runner_name=runner,
                         resume=resume,
                         verbose=verbose, 
                         output_lines=output_lines, 
                         start=start, 
                         target=target, 
                         profile=profile)
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

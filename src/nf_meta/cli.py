import click
from functools import wraps
from nf_meta.engine.runner import Runners, run
from nf_meta.engine.metawf_graph import MetaworkflowGraph


TOOL_VERSION = "0.0.1"


@click.group()
def cli() -> None:
    print("Hello from metaflow!")


@click.command("editor")
@click.option('--verbose', '-v', is_flag=True, help="Enables verbose mode")
@click.argument("config", required=False, type=click.Path())
def edit_browser(config, verbose):
    pass


@click.command("validate")
@click.argument("config", type=click.Path())
@click.option('--verbose', '-v', is_flag=True, help="Enables verbose mode")
def validate_config(config, verbose):
    g = MetaworkflowGraph.from_file(config)


@click.command("run")
@click.argument("config", type=click.Path())
@click.option('--verbose', '-v', is_flag=True, help="Enables verbose mode")
@click.option("--runner", "-r", prompt=True, type=click.Choice([e.value for e in Runners]), default=Runners.PYTHON.value)
def run(config, verbose, runner):
    g = MetaworkflowGraph.from_file(config)
    run(g, runner)


cli.add_command(edit_browser)
cli.add_command(validate_config)
cli.add_command(run)


if __name__ == "__main__":
    cli()

import click
from functools import wraps
from nf_meta.engine.runner import SimplePythonRunner, run_metapipeline, Runners
from nf_meta.engine.graph import MetaworkflowGraph
from nf_meta.engine.session import start_session
from nf_meta.editor import start_editor_backend


@click.group()
def cli() -> None:
    return

@click.command("editor")
@click.option('--verbose', '-v', is_flag=True, help="Enables verbose mode")
@click.option("--host", default="localhost", help="Host to use for running the editor ui")
@click.option("--port", help="Port to use for running the editor ui")
@click.argument("config", required=False, type=click.Path())
def edit_browser(config, verbose, host, port):
    # start engine
    start_session(config)

    # start api and open editor in browser
    start_editor_backend(host, port)


@click.command("validate")
@click.argument("config", type=click.Path())
@click.option('--verbose', '-v', is_flag=True, help="Enables verbose mode")
def validate_config(config, verbose):
    g = MetaworkflowGraph.from_file(config)


@click.command("run")
@click.argument("config", type=click.Path())
@click.option('--verbose', '-v', is_flag=True, help="Enables verbose mode")
@click.option("--runner", "-r", prompt=True, type=click.Choice([e.value for e in Runners]), default=Runners.PYTHON.value)
@click.option("--resume", is_flag=True, help="Resume a previous run")
def run(config, verbose, runner, resume):
    g = MetaworkflowGraph.from_file(config)
    run_metapipeline(g, SimplePythonRunner(), resume=resume)


cli.add_command(edit_browser)
cli.add_command(validate_config)
cli.add_command(run)


if __name__ == "__main__":
    cli()

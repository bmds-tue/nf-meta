import click
from functools import wraps
from nf_meta.engine.runner import Runners


VERSION = "0.0.1"


def common_options(f):
    @click.option('--verbose', '-v', is_flag=True, help="Enables verbose mode")
    @click.option('--config', type=click.Path(), help="Path to config file")
    @wraps(f)
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)
    return wrapper


@click.group()
def cli() -> None:
    print("Hello from metaflow!")


@click.command("editor")
@common_options
def edit_browser(verbose, config):
    pass


@click.command("validate")
@common_options
def validate_config(verbose, config):
    pass


@click.command("run")
@common_options
@click.option("--runner", type=click.Choice([e.value for e in Runners]), default=Runners.PYTHON.value)
def run(verbose, config, runner):
    pass


cli.add_command(edit_browser)
cli.add_command(validate_config)
cli.add_command(run)


if __name__ == "__main__":
    cli()

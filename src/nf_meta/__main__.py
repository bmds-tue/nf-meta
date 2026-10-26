import click
from functools import wraps
from pathlib import Path
from nf_meta.core.errors import (
    ConfigValidationError,
    GraphValidationError,
    format_errors_for_cli,
)
from nf_meta.runner import get_registered_runners
from nf_meta.core.config import from_file
from nf_meta.editor import get_registered_editors


def _read_text(path) -> str | None:
    try:
        return Path(path).read_text()
    except (OSError, TypeError):
        return None


def handle_validation_errors(func):
    """Shared error handling for commands taking a `config` path: renders any
    validation failure through the unified format_errors_for_cli, with real
    line numbers when the config file can be read as text.

    Each Diagnostic already carries its own document-relative yaml_path (set
    wherever it was created, per whether it belongs to a whole config or an
    isolated snippet), so no scope-specific handling is needed here at all.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        config = kwargs.get("config")
        try:
            return func(*args, **kwargs)
        except (GraphValidationError, ConfigValidationError) as e:
            source_text = _read_text(config) if config else None
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


@click.command("export-schema")
@click.argument(
    "output",
    required=False,
    type=click.Path(),
    default="schemas/metapipeline.schema.json",
)
def export_schema(output):
    """Write the metapipeline.yaml JSON Schema to OUTPUT (default:
    schemas/metapipeline.schema.json)."""
    import json
    from nf_meta.core.schema_export import generate_schema

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(generate_schema(), fh, indent=2)
        fh.write("\n")
    click.echo(click.style(f"✓ Schema written to {path}", fg="green"))


@click.command("validate")
@click.argument("config", type=click.Path())
@click.option("--verbose", "-v", is_flag=True, help="Enables verbose mode")
@click.option(
    "--scope",
    type=click.Choice(["config", "workflow", "globals"]),
    default="config",
    help=(
        "Validate a whole config (default), or an isolated workflow/globals "
        "YAML snippet -- a flat mapping (e.g. `name:`/`version:`/`params:` at "
        "the root for a workflow), not a `workflows: {<id>: {...}}` excerpt."
    ),
)
@handle_validation_errors
def validate_config(config, verbose, scope):
    if scope == "config":
        from nf_meta.core.errors import WARNING_COLOR, format_warnings_for_cli

        g = from_file(config, collect_errors=True)
        if g.warnings:
            click.echo(
                format_warnings_for_cli(
                    g.warnings, source_text=_read_text(config), filename=str(config)
                )
            )
            n = len(g.warnings)
            click.echo(
                click.style(
                    f"✓ Config is valid with {n} warning{'' if n == 1 else 's'}",
                    fg=WARNING_COLOR,
                )
            )
        else:
            click.echo(click.style("✓ Config is valid", fg="green"))
    elif scope == "workflow":
        from nf_meta.core.config import validated_workflow_from_file

        validated_workflow_from_file(config)
        click.echo(click.style("✓ Workflow is valid", fg="green"))
    else:
        from nf_meta.core.config import validated_globals_from_file

        validated_globals_from_file(config)
        click.echo(click.style("✓ Global options are valid", fg="green"))


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
@click.option(
    "--out",
    "-o",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to run in and write results to (default: nf-meta-out next to the config)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print each step's command and params file without running anything",
)
@handle_validation_errors
def run(
    config,
    verbose,
    runner,
    resume,
    output_lines,
    start,
    target,
    profile,
    stub,
    out_dir,
    dry_run,
):
    from nf_meta.runner import (
        plan_metapipeline,
        run_metapipeline,
        RunOptions,
        NfMetaRunnerError,
    )

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
            out_dir=out_dir,
        )
        g = from_file(config)
        if dry_run:
            _print_plan(plan_metapipeline(g, run_options))
        else:
            run_metapipeline(g, run_options)
    except NfMetaRunnerError as e:
        click.echo(click.style(e.message, fg="red"))
        raise SystemExit(1)


def _print_plan(steps) -> None:
    import shlex
    import yaml

    for i, step in enumerate(steps, start=1):
        header = f"Step {i}/{len(steps)}: {step.workflow.id} ({step.workflow.name})"
        if step.skip:
            header += " -- skipped, already done"
        click.echo(click.style(header, bold=True))
        click.echo(f"  cwd: {step.command.cwd}")
        env = " ".join(f"{k}={shlex.quote(v)}" for k, v in step.command.env.items())
        click.echo(f"  {env + ' ' if env else ''}{shlex.join(step.command.argv)}")
        if step.command.params_file:
            click.echo(f"  {step.command.params_file}:")
            for line in yaml.safe_dump(step.command.params, sort_keys=False).splitlines():
                click.echo(f"    {line}")
        click.echo()


cli.add_command(edit_browser)
cli.add_command(validate_config)
cli.add_command(run)
cli.add_command(export_schema)


if __name__ == "__main__":
    cli()

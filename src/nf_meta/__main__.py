from contextlib import contextmanager
from functools import wraps
from pathlib import Path

import click

from nf_meta.core.config import from_file
from nf_meta.core.errors import (
    ConfigValidationError,
    GraphValidationError,
    format_errors_for_cli,
)
from nf_meta.editor import get_registered_editors
from nf_meta.runner import get_registered_runners


def _read_text(path) -> str | None:
    try:
        return Path(path).read_text()
    except (OSError, TypeError):
        return None


def _echo_warnings(warnings, config) -> int:
    """Print `warnings` in the same format as validation errors; return how
    many there were."""
    from nf_meta.core.errors import format_warnings_for_cli

    if warnings:
        click.echo(format_warnings_for_cli(warnings, source_text=_read_text(config), filename=str(config)))
    return len(warnings)


def _echo_valid(what: str, n_warnings: int, verb: str = "is") -> None:
    from nf_meta.core.errors import WARNING_COLOR

    if n_warnings:
        plural = "" if n_warnings == 1 else "s"
        click.echo(click.style(f"✓ {what} {verb} valid with {n_warnings} warning{plural}", fg=WARNING_COLOR))
    else:
        click.echo(click.style(f"✓ {what} {verb} valid", fg="green"))


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
            click.echo(format_errors_for_cli(e, source_text=source_text, filename=str(config or "")))
            raise SystemExit(1) from None
        except FileNotFoundError as e:
            click.echo(click.style(str(e), fg="red"))
            raise SystemExit(1) from None

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
@click.option("--no-browser", is_flag=True, help="Don't open a browser; open the printed link yourself")
@click.option(
    "--no-redirect-file",
    is_flag=True,
    help="Open the editor link directly, not through a private local file; "
    "needed when the browser runs on another machine (VS Code Remote, dev containers)",
)
@click.argument("config", required=False, type=click.Path())
@handle_validation_errors
def edit_browser(config, verbose, editor, host, port, no_browser, no_redirect_file):
    from nf_meta.core.session import start_session
    from nf_meta.editor import EditorOptions, run_editor
    from nf_meta.editor.backend import recent

    session = start_session(config)
    _echo_warnings(session.graph.warnings, config)
    if config:
        recent.remember(config)
    opts = EditorOptions(editor_name=editor, open_browser=not no_browser, use_redirect_file=not no_redirect_file)
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
    # `workflow` is the old name of `step`, still accepted
    type=click.Choice(["config", "step", "globals", "workflow"]),
    metavar="[config|step|globals]",
    default="config",
    help=(
        "Validate a whole config (default), or an isolated step/globals "
        "YAML snippet -- a flat mapping (e.g. `name:`/`version:`/`params:` at "
        "the root for a step), not a `steps: {<id>: {...}}` excerpt."
    ),
)
@handle_validation_errors
def validate_config(config, verbose, scope):
    if scope == "config":
        g = from_file(config, collect_errors=True)
        _echo_valid("Config", _echo_warnings(g.warnings, config))
    elif scope in ("step", "workflow"):
        from nf_meta.core.config import validated_workflow_from_file

        if scope == "workflow":
            click.secho("--scope workflow is deprecated; use --scope step.", fg="yellow", err=True)
        warnings = _whole_config_warning(config, "step")
        with _with_warnings(warnings):
            validated_workflow_from_file(config, warnings)
        _echo_valid("Step", _echo_warnings(warnings, config))
    else:
        from nf_meta.core.config import validated_globals_from_file

        warnings = _whole_config_warning(config, scope)
        with _with_warnings(warnings):
            validated_globals_from_file(config)
        _echo_valid("Global options", _echo_warnings(warnings, config), verb="are")


def _whole_config_warning(config, scope: str) -> list:
    """A warning when a snippet passed with --scope step/globals is
    actually a whole config."""
    import yaml

    from nf_meta.core.errors import Diagnostic, Severity

    try:
        data = yaml.safe_load(Path(config).read_text())
    except (OSError, yaml.YAMLError):
        return []
    keys = [key for key in ("steps", "workflows", "config_version") if isinstance(data, dict) and key in data]
    if not keys:
        return []
    key = keys[0]
    return [
        Diagnostic(
            workflow_id=None,
            field=key,
            yaml_path=key,
            message=f"This looks like a whole config, not a single {scope} snippet; use --scope config.",
            severity=Severity.WARNING,
        )
    ]


@contextmanager
def _with_warnings(warnings: list):
    """Attach `warnings` to a validation error raised inside the block, so
    they're shown with it."""
    try:
        yield
    except ConfigValidationError as e:
        e.warnings = [*warnings, *e.warnings]
        raise
    except GraphValidationError as e:
        raise ConfigValidationError(errors=[], graph_messages=[str(e)], warnings=warnings) from e


@click.command("run")
@click.argument("config", type=click.Path())
@click.option("--verbose", "-v", is_flag=True, help="Enables verbose mode")
@click.option(
    "--runner",
    "-r",
    type=click.Choice(get_registered_runners()),
    default="python",
    show_default=True,
    help="Runner backend to execute the metapipeline with",
)
@click.option("--resume", is_flag=True, help="Resume a previous run")
@click.option(
    "--output-lines",
    "-l",
    default="25",
    type=int,
    help="Number of lines of step output to stream to output window (Only for Python Runner!)",
)
@click.option("--start", "-s", type=str, help="ID of the step to start from")
@click.option("--target", "-t", type=str, help="ID of the step to run until")
@click.option(
    "--nf-profile",
    "-p",
    "profile",
    type=str,
    help="Nextflow profile for every step, after the configured ones.",
)
@click.option(
    "--nf-config",
    "-c",
    "nf_config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Nextflow config for every step, taking precedence over the global and step configs.",
)
@click.option(
    "--stub",
    is_flag=True,
    help="Run all steps as stub runs (passes -stub to Nextflow)",
)
@click.option(
    "--out",
    "-o",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to run in and write results to (default: nf-meta-out in the current directory)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print each step's command and params file without running anything",
)
@click.option(
    "--input",
    "-i",
    "input_values",
    multiple=True,
    metavar="NAME=VALUE",
    help="Value for an input (or <step_id>.<param> for a reference to a step outside the run). "
    "Use once per value: --input ids=ids.csv --input genome=GRCh38",
)
@click.option(
    "--inputs-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="YAML mapping of input values; --input takes precedence.",
)
@click.option(
    "--input-mode",
    type=click.Choice(["prompt", "fail", "reproduce"]),
    help="What to do with values the run needs but doesn't have: ask (default in a terminal), "
    "stop with a list of them (default otherwise), or reuse the values of the last run.",
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
    nf_config,
    input_values,
    inputs_file,
    input_mode,
):
    import sys

    from nf_meta.runner import (
        InputMode,
        NfMetaRunnerError,
        RunOptions,
        plan_metapipeline,
        run_metapipeline,
    )

    mode = InputMode(input_mode or ("prompt" if sys.stdin.isatty() else "fail"))
    try:
        run_options = RunOptions(
            runner_name=runner,
            verbose=verbose,
            output_lines=output_lines,
            nf_profile=profile,
            nf_config=nf_config.resolve() if nf_config else None,
            stub=stub,
            resume=resume,
            start=start,
            target=target,
            out_dir=out_dir,
            input_mode=mode,
            inputs=_given_inputs(input_values, inputs_file),
            prompter=_prompt_for_input if mode == InputMode.PROMPT else None,
        )
        g = from_file(config, collect_errors=True)
        _echo_warnings(g.warnings, config)
        if dry_run:
            _print_plan(plan_metapipeline(g, run_options))
        else:
            run_metapipeline(g, run_options)
    except NfMetaRunnerError as e:
        click.echo(click.style(e.message, fg="red"))
        raise SystemExit(1) from None


def _given_inputs(input_values: tuple[str, ...], inputs_file: Path | None) -> dict:
    import yaml

    given: dict = {}
    if inputs_file is not None:
        data = yaml.safe_load(inputs_file.read_text()) or {}
        if not isinstance(data, dict):
            raise click.BadParameter("must contain a mapping of input names to values", param_hint="--inputs-file")
        given.update({str(k): v for k, v in data.items()})
    for item in input_values:
        name, sep, value = item.partition("=")
        if not sep or not name:
            raise click.BadParameter(f"expected NAME=VALUE, got {item!r}", param_hint="--input")
        given[name] = value
    return given


def _prompt_for_input(inp, problem: str | None):
    """Ask for one input: an interactive question in a terminal (selection
    lists, path completion, validation while typing), a plain prompt
    otherwise."""
    import sys

    if sys.stdin.isatty() and sys.stdout.isatty():
        answer = _question_for_input(inp).ask()
        if answer is None:  # Ctrl-C
            raise click.Abort
        return answer
    return _plain_prompt_for_input(inp, problem)


def _question_for_input(inp):
    """The questionary question for `inp`, chosen from its schema."""
    import questionary

    from nf_meta.runner.collect import coerce

    def validate(text: str):
        problems = inp.validate(coerce(inp, text), project_dir=Path.cwd())
        return True if not problems else "; ".join(problems)

    label = inp.name + (f" ({inp.description})" if inp.description else "")
    schema = inp.schema
    if schema.get("enum"):
        choices = [str(e) for e in schema["enum"]]
        many = len(choices) > 10
        return questionary.select(label, choices=choices, use_search_filter=many, use_jk_keys=not many)
    if schema.get("type") == "boolean":
        return questionary.confirm(label)
    if inp.is_path:
        return questionary.path(label, only_directories=schema.get("format") == "directory-path", validate=validate)
    return questionary.text(label, validate=validate)


def _plain_prompt_for_input(inp, problem: str | None):
    from nf_meta.core.errors import WARNING_COLOR

    if problem:
        click.echo(click.style(f"  {problem}", fg=WARNING_COLOR))
    label = inp.name + (f" -- {inp.description}" if inp.description else "")
    schema = inp.schema
    if schema.get("enum"):
        return click.prompt(label, type=click.Choice([str(e) for e in schema["enum"]]))
    if schema.get("type") == "boolean":
        return click.confirm(label)
    if inp.is_path:
        return click.prompt(f"{label} (path)", type=str)
    types = {"integer": int, "number": float}
    return click.prompt(label, type=types.get(schema.get("type"), str))


def _print_plan(steps) -> None:
    import shlex

    import yaml

    from nf_meta.core.errors import WARNING_COLOR

    if steps.values:
        click.echo(click.style("Values", bold=True))
        for name, value in steps.values.items():
            click.echo(f"  {name}: {value}")
        click.echo()

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

    if steps.missing:
        click.echo(
            click.style(
                f"Missing values (shown as <input: ...>): {', '.join(steps.missing)}. "
                "A real run needs them: give them with --input or --inputs-file, or use --input-mode prompt.",
                fg=WARNING_COLOR,
            )
        )


cli.add_command(edit_browser)
cli.add_command(validate_config)
cli.add_command(run)
cli.add_command(export_schema)


if __name__ == "__main__":
    cli()

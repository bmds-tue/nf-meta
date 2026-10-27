"""Pin down Nextflow behaviors that nf-meta's runner design relies on.

These run real Nextflow against the local fixture pipelines in
``tests/fixtures/nextflow`` and deliberately bypass nf-meta's runner: they
document Nextflow's behavior, not ours. Findings: ``plans/P0-findings.md``.

Every executed (non-cached) task appends a line to ``params.counter``, so a
cache hit shows up as "no new line".

Run with ``uv run pytest -m nextflow``.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.nextflow,
    pytest.mark.skipif(shutil.which("nextflow") is None, reason="nextflow not installed"),
]

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "nextflow"
PIPELINE_A = FIXTURES / "pipeline_a" / "main.nf"
PIPELINE_B = FIXTURES / "pipeline_b" / "main.nf"


def nextflow(
    *args: str, cwd: Path, log: Path | None = None, cache_dir: Path | None = None
) -> subprocess.CompletedProcess:
    """Run ``nextflow [-log <log>] <args>`` in ``cwd``; fail the test on a non-zero exit.

    ``cache_dir`` sets ``NXF_CACHE_DIR`` (run history + task cache) for this run.
    """
    cmd = ["nextflow"]
    if log is not None:
        cmd += ["-log", str(log)]
    cmd += [*args, "-ansi-log", "false"]
    env = {**os.environ, "NXF_CACHE_DIR": str(cache_dir)} if cache_dir else None
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"{cmd} failed:\n{proc.stdout}\n{proc.stderr}"
    return proc


def session_id(log: Path) -> str:
    match = re.search(r"Session UUID: ([0-9a-f-]+)", log.read_text())
    assert match, f"no session UUID in {log}"
    return match.group(1)


def run_name(log: Path) -> str:
    match = re.search(r"Run name: (\w+)", log.read_text())
    assert match, f"no run name in {log}"
    return match.group(1)


def executed(counter: Path) -> list[str]:
    return counter.read_text().split() if counter.exists() else []


@pytest.fixture
def launch_dir(tmp_path):
    d = tmp_path / "launch"
    d.mkdir()
    return d


def test_baseline_bare_resume_reuses_tasks(launch_dir, tmp_path):
    counter = tmp_path / "a.txt"
    nextflow("run", str(PIPELINE_A), "--counter", str(counter), cwd=launch_dir)
    nextflow("run", str(PIPELINE_A), "-resume", "--counter", str(counter), cwd=launch_dir)
    assert len(executed(counter)) == 3


def test_h1_bare_resume_after_other_pipeline_reruns_everything(launch_dir, tmp_path):
    """Today's nf-meta behavior: steps share one launch dir and pass a bare -resume."""
    counter_a, counter_b = tmp_path / "a.txt", tmp_path / "b.txt"
    nextflow("run", str(PIPELINE_A), "--counter", str(counter_a), cwd=launch_dir)
    nextflow("run", str(PIPELINE_B), "--counter", str(counter_b), cwd=launch_dir)

    nextflow("run", str(PIPELINE_A), "-resume", "--counter", str(counter_a), cwd=launch_dir)

    assert len(executed(counter_a)) == 6  # all three tasks of A ran again


def test_h2_resume_with_session_id_after_other_pipeline(launch_dir, tmp_path):
    counter_a, counter_b = tmp_path / "a.txt", tmp_path / "b.txt"
    log_a = tmp_path / "a.log"
    nextflow("run", str(PIPELINE_A), "--counter", str(counter_a), cwd=launch_dir, log=log_a)
    nextflow("run", str(PIPELINE_B), "--counter", str(counter_b), cwd=launch_dir)

    nextflow(
        "run",
        str(PIPELINE_A),
        "-resume",
        session_id(log_a),
        "--counter",
        str(counter_a),
        cwd=launch_dir,
    )

    assert len(executed(counter_a)) == 3


def test_h3_shared_work_dir_both_pipelines_resume(launch_dir, tmp_path):
    work = launch_dir / "work"
    counter_a, counter_b = tmp_path / "a.txt", tmp_path / "b.txt"
    log_a, log_b = tmp_path / "a.log", tmp_path / "b.log"
    nextflow("run", str(PIPELINE_A), "-w", str(work), "--counter", str(counter_a), cwd=launch_dir, log=log_a)
    nextflow("run", str(PIPELINE_B), "-w", str(work), "--counter", str(counter_b), cwd=launch_dir, log=log_b)

    nextflow(
        "run",
        str(PIPELINE_A),
        "-w",
        str(work),
        "-resume",
        session_id(log_a),
        "--counter",
        str(counter_a),
        cwd=launch_dir,
    )
    nextflow(
        "run",
        str(PIPELINE_B),
        "-w",
        str(work),
        "-resume",
        session_id(log_b),
        "--counter",
        str(counter_b),
        cwd=launch_dir,
    )

    assert len(executed(counter_a)) == 3
    assert len(executed(counter_b)) == 2


def test_h4_resumed_run_keeps_session_id(launch_dir, tmp_path):
    counter = tmp_path / "a.txt"
    first, second = tmp_path / "first.log", tmp_path / "second.log"
    nextflow("run", str(PIPELINE_A), "--counter", str(counter), cwd=launch_dir, log=first)
    nextflow(
        "run", str(PIPELINE_A), "-resume", session_id(first), "--counter", str(counter), cwd=launch_dir, log=second
    )

    assert session_id(second) == session_id(first)


def test_h4_resume_silently_ignores_run_name(launch_dir, tmp_path):
    """A run name is not a valid -resume argument: Nextflow falls back to the
    most recent session without any warning, so nf-meta must store the UUID."""
    counter_a, counter_b = tmp_path / "a.txt", tmp_path / "b.txt"
    log_a, log_b, log_resume = tmp_path / "a.log", tmp_path / "b.log", tmp_path / "r.log"
    nextflow("run", str(PIPELINE_A), "--counter", str(counter_a), cwd=launch_dir, log=log_a)
    nextflow("run", str(PIPELINE_B), "--counter", str(counter_b), cwd=launch_dir, log=log_b)

    nextflow(
        "run", str(PIPELINE_A), "-resume", run_name(log_a), "--counter", str(counter_a), cwd=launch_dir, log=log_resume
    )

    assert session_id(log_resume) == session_id(log_b)
    assert len(executed(counter_a)) == 6


def test_h5_log_option_replaces_shared_log(launch_dir, tmp_path):
    log = tmp_path / "state" / "step.log"
    nextflow("run", str(PIPELINE_A), "--counter", str(tmp_path / "a.txt"), cwd=launch_dir, log=log)

    assert log.exists()
    assert not (launch_dir / ".nextflow.log").exists()
    assert (launch_dir / ".nextflow").is_dir()  # run history stays in the launch dir


def test_h6_relative_paths_resolve_against_launch_dir(launch_dir, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "data.txt").write_text("project copy\n")
    (launch_dir / "data.txt").write_text("launch-dir copy\n")
    params_file = project / "params.yaml"
    params_file.write_text(f"input: data.txt\noutdir: out_rel\ncounter: {tmp_path / 'a.txt'}\n")

    proc = nextflow("run", str(PIPELINE_A), "-params-file", str(params_file), cwd=launch_dir)

    assert f"INPUT_RESOLVED={launch_dir / 'data.txt'}" in proc.stdout
    assert (launch_dir / "out_rel").is_dir()
    assert not (project / "out_rel").exists()


def test_h8_stub_and_real_runs_do_not_share_cache(launch_dir, tmp_path):
    real_first, stub_first = tmp_path / "real_first.txt", tmp_path / "stub_first.txt"

    log = tmp_path / "real.log"
    nextflow("run", str(PIPELINE_A), "--counter", str(real_first), cwd=launch_dir, log=log)
    nextflow("run", str(PIPELINE_A), "-stub", "-resume", session_id(log), "--counter", str(real_first), cwd=launch_dir)
    assert "a_one_stub:1" in executed(real_first)

    log = tmp_path / "stub.log"
    nextflow("run", str(PIPELINE_A), "-stub", "--counter", str(stub_first), cwd=launch_dir, log=log)
    nextflow("run", str(PIPELINE_A), "-resume", session_id(log), "--counter", str(stub_first), cwd=launch_dir)
    assert "a_one:1" in executed(stub_first)


def test_h7_module_run_supports_resume_flags(tmp_path):
    """`nextflow module` exists only from 26.04; check the flags we rely on are accepted."""
    proc = subprocess.run(
        ["nextflow", "module", "run", "-h"], capture_output=True, text=True, timeout=120, cwd=tmp_path
    )
    if "Expected a command, got module" in proc.stdout + proc.stderr:
        pytest.skip("installed Nextflow has no `module` command (needs >= 26.04)")
    for flag in ("-resume", "-work-dir", "-params-file", "-stub"):
        assert flag in proc.stdout


def test_h10_resume_after_failure_with_changed_param_reruns_only_affected(launch_dir, tmp_path):
    """The realistic case: a step fails part-way, the user fixes a param and resumes."""
    counter, log = tmp_path / "a.txt", tmp_path / "a.log"
    with pytest.raises(AssertionError):
        nextflow("run", str(PIPELINE_A), "--counter", str(counter), "--fail_two", "true", cwd=launch_dir, log=log)
    nextflow("run", str(PIPELINE_B), "--counter", str(tmp_path / "b.txt"), cwd=launch_dir)
    counter.write_text("")

    nextflow(
        "run",
        str(PIPELINE_A),
        "-resume",
        session_id(log),
        "--counter",
        str(counter),
        "--fail_two",
        "false",
        cwd=launch_dir,
    )

    assert executed(counter) == ["a_two"]


def test_h11_resume_after_failure_with_extra_config_reruns_only_failed(launch_dir, tmp_path):
    """Same, but the fix is a Nextflow config (resources) instead of a param."""
    counter, log = tmp_path / "a.txt", tmp_path / "a.log"
    with pytest.raises(AssertionError):
        nextflow("run", str(PIPELINE_A), "--counter", str(counter), "--min_cpus_two", "2", cwd=launch_dir, log=log)
    fix = tmp_path / "fix.config"
    fix.write_text("process {\n  withName: A_TWO { cpus = 2 }\n}\n")
    counter.write_text("")

    nextflow(
        "run",
        str(PIPELINE_A),
        "-c",
        str(fix),
        "-resume",
        session_id(log),
        "--counter",
        str(counter),
        "--min_cpus_two",
        "2",
        cwd=launch_dir,
    )

    assert executed(counter) == ["a_two"]


def test_h12_per_step_cache_dir_makes_bare_resume_per_step(launch_dir, tmp_path):
    """With NXF_CACHE_DIR per step, a bare -resume finds that step's own last run,
    even after other pipelines ran in the same launch dir."""
    counter_a, counter_b = tmp_path / "a.txt", tmp_path / "b.txt"
    cache_a, cache_b = tmp_path / "state" / "a", tmp_path / "state" / "b"
    nextflow("run", str(PIPELINE_A), "--counter", str(counter_a), cwd=launch_dir, cache_dir=cache_a)
    nextflow("run", str(PIPELINE_B), "--counter", str(counter_b), cwd=launch_dir, cache_dir=cache_b)

    nextflow("run", str(PIPELINE_A), "-resume", "--counter", str(counter_a), cwd=launch_dir, cache_dir=cache_a)

    assert len(executed(counter_a)) == 3
    assert not (launch_dir / ".nextflow").exists()
    assert (cache_a / "history").exists()

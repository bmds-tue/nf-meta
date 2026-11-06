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
    *args: str,
    cwd: Path,
    log: Path | None = None,
    cache_dir: Path | None = None,
    nxf_home: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run ``nextflow [-log <log>] <args>`` in ``cwd``; fail the test on a
    non-zero exit unless ``check`` is false.

    ``cache_dir`` sets ``NXF_CACHE_DIR`` (run history + task cache) and
    ``nxf_home`` sets ``NXF_HOME`` (where pulled pipelines live) for this run.
    """
    cmd = ["nextflow"]
    if log is not None:
        cmd += ["-log", str(log)]
    cmd += [*args, "-ansi-log", "false"]
    env = dict(os.environ)
    if cache_dir:
        env["NXF_CACHE_DIR"] = str(cache_dir)
    if nxf_home:
        env["NXF_HOME"] = str(nxf_home)
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    if check:
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


# ---------------------------------------------------------------------------
# Pinned revisions and -latest (H9, H13-H15)
#
# A local bare git repository stands in for a remote pipeline repository
# (``file://`` URL), with ``NXF_HOME`` pointing at a fresh directory so the
# pulled copy is isolated. History: one (tag 1.0.0) - two - three (tag 1.1.0) - four.
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


def _commit(work: Path, label: str) -> str:
    with open(work / "main.nf", "a") as fh:
        fh.write(f"// {label}\n")
    _git("commit", "-qam", label, cwd=work)
    return _git("rev-parse", "HEAD", cwd=work)


def _nextflow_major() -> int:
    from nf_meta.runner.utils import get_installed_nextflow_version

    return get_installed_nextflow_version()[0]


@pytest.fixture
def pipeline_repo(tmp_path):
    """A pipeline repository; `behind_tag` is the full hash of commit two."""
    work = tmp_path / "work_repo"
    work.mkdir()
    _git("init", "-q", "-b", "main", cwd=work)
    (work / "main.nf").write_text(PIPELINE_A.read_text())
    _git("add", ".", cwd=work)
    _git("commit", "-qm", "one", cwd=work)
    _git("tag", "1.0.0", cwd=work)
    behind_tag = _commit(work, "two")
    _commit(work, "three")
    _git("tag", "1.1.0", cwd=work)
    _commit(work, "four")
    bare = tmp_path / "repo.git"
    _git("clone", "-q", "--bare", str(work), str(bare), cwd=tmp_path)
    return {"url": f"file://{bare}", "bare": bare, "work": work, "behind_tag": behind_tag}


def _run(repo, revision, launch_dir, tmp_path, *extra):
    return nextflow(
        "run",
        repo["url"],
        "-r",
        revision,
        *extra,
        "--counter",
        str(tmp_path / "c.txt"),
        cwd=launch_dir,
        nxf_home=tmp_path / "nxf_home",
        check=False,
    )


def test_h13_latest_and_commit_behind_a_tag(pipeline_repo, launch_dir, tmp_path):
    """Nextflow 25.x: a commit that isn't a tag or branch tip is checked out
    detached, and -latest's pull on the next run fails. nf-meta passed -latest
    until this was found."""
    rev = pipeline_repo["behind_tag"]
    assert _run(pipeline_repo, rev, launch_dir, tmp_path, "-latest").returncode == 0
    second = _run(pipeline_repo, rev, launch_dir, tmp_path, "-latest")
    if _nextflow_major() < 26:
        assert second.returncode != 0
        assert "did not advertise Ref" in second.stdout + second.stderr
    else:
        assert second.returncode == 0


def test_h14_without_latest_repeated_runs_of_pinned_revisions_work(pipeline_repo, launch_dir, tmp_path):
    for rev in (pipeline_repo["behind_tag"], "1.0.0"):
        for _ in range(2):
            assert _run(pipeline_repo, rev, launch_dir, tmp_path).returncode == 0


def test_h15_without_latest_revisions_published_later_are_fetched(pipeline_repo, launch_dir, tmp_path):
    assert _run(pipeline_repo, "1.0.0", launch_dir, tmp_path).returncode == 0  # first download
    work = pipeline_repo["work"]
    _commit(work, "five")
    _git("tag", "1.2.0", cwd=work)
    new_commit = _commit(work, "six")
    _git("push", "-q", str(pipeline_repo["bare"]), "main", "--tags", cwd=work)

    assert _run(pipeline_repo, "1.2.0", launch_dir, tmp_path).returncode == 0
    assert _run(pipeline_repo, new_commit, launch_dir, tmp_path).returncode == 0


def test_h16_abbreviated_commit_hashes(pipeline_repo, launch_dir, tmp_path):
    """Nextflow 26.x fetches each revision separately and git can't fetch an
    abbreviated hash; 25.x clones everything and resolves it locally."""
    short = pipeline_repo["behind_tag"][:7]
    run = _run(pipeline_repo, short, launch_dir, tmp_path)
    if _nextflow_major() < 26:
        assert run.returncode == 0
    else:
        assert run.returncode != 0
        assert "available for fetch" in run.stdout + run.stderr


# ---------------------------------------------------------------------------
# H17: with -main-script, the script's folder is the pipeline (main_script steps
# read their schema from there)
# ---------------------------------------------------------------------------

_REPORT = 'workflow { println "projectDir=${projectDir} root=${params.root} own=${params.own}" }\n'


@pytest.fixture
def connectors_repo(tmp_path):
    """A repository with a connector in `connectors/a2b` and its own config,
    next to a root config."""
    work = tmp_path / "connectors_repo"
    a2b = work / "connectors" / "a2b"
    a2b.mkdir(parents=True)
    (a2b / "main.nf").write_text(_REPORT)
    (a2b / "nextflow.config").write_text('params.own = "a2b"\n')
    (work / "nextflow.config").write_text('params.root = "yes"\n')
    _git("init", "-q", "-b", "main", cwd=work)
    _git("add", ".", cwd=work)
    _git("commit", "-qm", "one", cwd=work)
    _git("tag", "1.0.0", cwd=work)
    bare = tmp_path / "connectors.git"
    _git("clone", "-q", "--bare", str(work), str(bare), cwd=tmp_path)
    return {"url": f"file://{bare}", "work": work}


def test_h17_main_script_folder_is_the_pipeline(connectors_repo, launch_dir, tmp_path):
    run = nextflow(
        "run",
        connectors_repo["url"],
        "-r",
        "1.0.0",
        "-main-script",
        "connectors/a2b/main.nf",
        cwd=launch_dir,
        nxf_home=tmp_path / "nxf_home",
    )
    assert re.search(r"projectDir=\S+/connectors/a2b root=null own=a2b", run.stdout), run.stdout


def test_h17_a_local_script_file_runs_like_main_script(connectors_repo, launch_dir):
    script = connectors_repo["work"] / "connectors" / "a2b" / "main.nf"
    run = nextflow("run", str(script), cwd=launch_dir)
    assert f"projectDir={script.parent} root=null own=a2b" in run.stdout


def test_h17_a_local_folder_ignores_main_script(connectors_repo, launch_dir):
    run = nextflow(
        "run", str(connectors_repo["work"]), "-main-script", "connectors/a2b/main.nf", cwd=launch_dir, check=False
    )
    assert run.returncode != 0

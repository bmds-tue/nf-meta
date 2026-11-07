import json

import pytest
import yaml

from nf_meta import (
    ConfigValidationError,
    GlobalOptions,
    InputDefinition,
    Metapipeline,
    NfMetaRunnerError,
    NfModule,
    NfPipeline,
    Ref,
    run_step,
)
from nf_meta.runner.python_runner import SimplePythonRunner  # type: ignore[import]


def fetchngs(**params):
    return NfPipeline(name="nf-core/fetchngs", version="1.12.0", params={"outdir": "out_fetchngs", **params})


def rnaseq(**params):
    return NfPipeline(name="nf-core/rnaseq", version="3.14.0", params={"outdir": "out_rnaseq", **params})


@pytest.fixture
def two_steps(tmp_path):
    mp = Metapipeline(project_dir=tmp_path)
    fetch = mp.add(fetchngs())
    rna = mp.add(rnaseq(input=Ref(fetch, "outdir") / "samplesheet/samplesheet.csv"))
    return mp, fetch, rna


@pytest.fixture
def fake_execute(monkeypatch, mock_nextflow):
    """Replace step execution; returns the list of executed step ids."""
    executed: list[str] = []
    outcome = {"success": True}

    def execute(self, spec, command):
        executed.append(spec.step_id)
        return outcome["success"]

    monkeypatch.setattr(SimplePythonRunner, "_execute", execute)
    monkeypatch.setattr(SimplePythonRunner, "_check_nextflow", lambda self, graph, steps: None)
    execute.outcome = outcome  # type: ignore[attr-defined]
    return executed, outcome


class TestRef:
    def test_param_reference(self):
        assert Ref("n01", "outdir") == "${n01:params:outdir}"

    def test_from_a_model(self):
        wf = fetchngs()
        assert Ref(wf, "outdir") == f"${{{wf.id}:params:outdir}}"

    def test_slash_appends_a_path(self):
        assert Ref("n01", "outdir") / "a" / "/b.csv" == "${n01:params:outdir}/a/b.csv"

    def test_input_reference(self):
        assert Ref.input("ids") == "${inputs:ids}"

    def test_input_reference_takes_no_path(self):
        with pytest.raises(TypeError, match="whole value"):
            Ref.input("ids") / "x.csv"

    def test_stored_as_plain_str(self):
        wf = rnaseq(input=Ref("n01", "outdir"))
        assert type(wf.params["input"]) is str


class TestBuild:
    def test_reference_creates_the_edge(self, two_steps):
        mp, fetch, rna = two_steps
        assert mp.graph.get_transition(fetch.id, rna.id) is not None
        assert [wf.id for wf in mp.steps] == [fetch.id, rna.id]

    def test_after_creates_an_edge(self, tmp_path):
        mp = Metapipeline(project_dir=tmp_path)
        fetch = mp.add(fetchngs())
        rna = mp.add(rnaseq(), after=[fetch])
        assert mp.graph.get_transition(fetch.id, rna.id) is not None

    def test_add_returns_its_argument_and_keeps_a_copy(self, tmp_path):
        mp = Metapipeline(project_dir=tmp_path)
        wf = fetchngs()
        assert mp.add(wf) is wf
        wf.params["outdir"] = "changed"
        assert mp[wf.id].params["outdir"] == "out_fetchngs"

    def test_update_applies_changes(self, two_steps):
        mp, fetch, _ = two_steps
        changed = mp[fetch.id]
        changed.params["outdir"] = "elsewhere"
        mp.update(changed)
        assert mp[fetch.id].params["outdir"] == "elsewhere"

    def test_reference_to_unknown_step_raises_and_changes_nothing(self, tmp_path):
        mp = Metapipeline(project_dir=tmp_path)
        with pytest.raises(ConfigValidationError, match="unknown step: nmissing"):
            mp.add(rnaseq(input=Ref("nmissing", "outdir")))
        assert mp.steps == []

    def test_invalid_update_raises_and_changes_nothing(self, two_steps):
        mp, fetch, rna = two_steps
        broken = mp[rna.id]
        broken.params["input"] = Ref(fetch, "no_such_param")
        with pytest.raises(ConfigValidationError):
            mp.update(broken)
        assert mp[rna.id].params["input"] == f"${{{fetch.id}:params:outdir}}/samplesheet/samplesheet.csv"

    def test_ref_assigned_after_creation_is_stored(self, two_steps):
        mp, fetch, rna = two_steps
        step = mp[rna.id]
        step.params["outdir"] = Ref(fetch, "outdir") / "rnaseq"
        mp.update(step)
        assert mp[rna.id].params["outdir"] == f"${{{fetch.id}:params:outdir}}/rnaseq"
        assert type(mp[rna.id].params["outdir"]) is str

    def test_remove(self, tmp_path):
        mp = Metapipeline(project_dir=tmp_path)
        fetch = mp.add(fetchngs())
        mp.remove(fetch)
        assert mp.steps == []

    def test_unknown_step_id_raises_key_error(self, tmp_path):
        with pytest.raises(KeyError):
            Metapipeline(project_dir=tmp_path)["nope"]

    def test_globals(self, tmp_path):
        mp = Metapipeline(project_dir=tmp_path)
        mp.set_globals(GlobalOptions(nf_profile="docker"))
        assert mp.globals.nf_profile == "docker"

    def test_implicit_input_is_listed(self, tmp_path):
        mp = Metapipeline(project_dir=tmp_path)
        mp.add(fetchngs(input=Ref.input("ids")))
        assert mp.inputs == {"ids": InputDefinition()}

    def test_inputs(self, tmp_path):
        mp = Metapipeline(project_dir=tmp_path)
        mp.add_input("ids", InputDefinition(description="Accessions"))
        mp.add(fetchngs(input=Ref.input("ids")))
        assert mp.inputs["ids"].description == "Accessions"
        assert mp.graph.input_bindings()["ids"]


class TestHistory:
    def test_undo_and_redo(self, two_steps):
        mp, _, rna = two_steps
        mp.undo()
        assert rna.id not in [wf.id for wf in mp.steps]
        mp.redo()
        assert rna.id in [wf.id for wf in mp.steps]

    def test_undo_removes_a_step_with_its_edges(self, two_steps):
        mp, fetch, rna = two_steps
        mp.undo()
        assert mp.graph.get_transition(fetch.id, rna.id) is None

    def test_nothing_to_undo(self, tmp_path):
        with pytest.raises(ValueError, match="Nothing to undo"):
            Metapipeline(project_dir=tmp_path).undo()


class TestLoadSave:
    def test_save_and_load_round_trip(self, two_steps, tmp_path):
        mp, fetch, rna = two_steps
        path = tmp_path / "metaconfig.yaml"
        mp.save(path)

        data = yaml.safe_load(path.read_text())
        assert data["steps"][rna.id]["from"] == [fetch.id]

        loaded = Metapipeline.load(path)
        assert [wf.id for wf in loaded.steps] == [fetch.id, rna.id]
        assert loaded.path == path
        assert loaded.graph.project_dir == tmp_path.resolve()

    def test_nothing_written_before_save(self, two_steps, tmp_path):
        mp, _, _ = two_steps
        path = tmp_path / "metaconfig.yaml"
        mp.save(path)
        before = path.read_text()

        loaded = Metapipeline.load(path)
        loaded.add(rnaseq(), after=[loaded.steps[0]])
        assert path.read_text() == before

        loaded.save()
        assert path.read_text() != before

    def test_a_module_step_round_trips(self, tmp_path):
        mp = Metapipeline(project_dir=tmp_path)
        module = mp.add(NfModule(name="nf-core/fastqc", version="0.0.0-6c4ed3a"))
        path = tmp_path / "metaconfig.yaml"
        mp.save(path)
        assert yaml.safe_load(path.read_text())["steps"][module.id]["type"] == "nf-module"
        assert Metapipeline.load(path).steps[0].name == "nf-core/fastqc"

    def test_a_failed_save_keeps_the_old_file(self, two_steps, tmp_path, monkeypatch):
        mp, _, _ = two_steps
        path = tmp_path / "metaconfig.yaml"
        mp.save(path)
        before = path.read_text()

        def broken(_):
            raise RuntimeError("dump failed")

        monkeypatch.setattr("nf_meta.core.config.dump_config", broken)
        with pytest.raises(RuntimeError):
            mp.save(path)
        assert path.read_text() == before

    def test_save_without_a_path_raises(self, tmp_path):
        with pytest.raises(ValueError):
            Metapipeline(project_dir=tmp_path).save()


class TestRun:
    def test_run_returns_results(self, two_steps, fake_execute, tmp_path):
        mp, fetch, rna = two_steps
        executed, _ = fake_execute
        results = mp.run(out_dir=tmp_path / "out")

        assert executed == [fetch.id, rna.id]
        assert list(results) == [fetch.id, rna.id]
        assert results.out_dir == (tmp_path / "out").resolve()
        assert results[fetch.id].outdir == (tmp_path / "out" / "out_fetchngs").resolve()
        assert results[rna.id].params["input"].endswith("out_fetchngs/samplesheet/samplesheet.csv")
        json.dumps(results.to_dict())

    def test_failing_step_raises(self, two_steps, fake_execute, tmp_path):
        mp, fetch, _ = two_steps
        executed, outcome = fake_execute
        outcome["success"] = False
        with pytest.raises(NfMetaRunnerError, match=fetch.id):
            mp.run(out_dir=tmp_path / "out")
        assert executed == [fetch.id]

    def test_start_and_target_accept_models(self, two_steps, fake_execute, tmp_path):
        mp, fetch, _ = two_steps
        executed, _ = fake_execute
        mp.run(out_dir=tmp_path / "out", start=fetch, target=fetch)
        assert executed == [fetch.id]

    def test_resume_reruns_a_step_whose_outdir_another_run_overwrote(self, tmp_path, monkeypatch, mock_nextflow):
        executed: list[str] = []

        def execute(self, spec, command):
            executed.append(spec.params["count"])
            spec.state_dir.mkdir(parents=True, exist_ok=True)
            (spec.state_dir / SimplePythonRunner.OUT_FILE).write_text("done")
            return True

        monkeypatch.setattr(SimplePythonRunner, "_execute", execute)
        monkeypatch.setattr(SimplePythonRunner, "_check_nextflow", lambda self, graph, steps: None)
        mp = Metapipeline(project_dir=tmp_path)
        step = mp.add(rnaseq(count=1))
        for count in (1, 2, 1):
            step.params["count"] = count
            mp.update(step)
            mp.run(out_dir=tmp_path / "out", resume=True)
        assert executed == [1, 2, 1]
        mp.run(out_dir=tmp_path / "out", resume=True)
        assert executed == [1, 2, 1]

    def test_plan_runs_nothing(self, two_steps, fake_execute, tmp_path):
        mp, fetch, rna = two_steps
        executed, _ = fake_execute
        plan = mp.plan(out_dir=tmp_path / "out")
        assert [s.workflow.id for s in plan] == [fetch.id, rna.id]
        assert executed == []
        json.dumps(plan.to_dict())

    def test_inputs_given_to_run(self, tmp_path, fake_execute):
        (tmp_path / "ids.csv").write_text("SRR1\n")
        mp = Metapipeline(project_dir=tmp_path)
        mp.add_input("ids", InputDefinition(format="file-path"))
        fetch = mp.add(fetchngs(input=Ref.input("ids")))
        results = mp.run(out_dir=tmp_path / "out", inputs={"ids": str(tmp_path / "ids.csv")}, input_mode="fail")
        assert results[fetch.id].params["input"] == str(tmp_path / "ids.csv")

    def test_unknown_option_raises(self, two_steps):
        mp, _, _ = two_steps
        with pytest.raises(TypeError):
            mp.run(no_such_option=True)


class TestRunStep:
    def test_runs_a_single_model(self, fake_execute, tmp_path):
        executed, _ = fake_execute
        wf = fetchngs()
        results = run_step(wf, out_dir=tmp_path / "out", project_dir=tmp_path)
        assert executed == [wf.id]
        assert results[wf.id].outdir == (tmp_path / "out" / "out_fetchngs").resolve()

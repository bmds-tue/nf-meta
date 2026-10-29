import pytest
import yaml
from fastapi.testclient import TestClient

from nf_meta.core.session import EditorSession
from nf_meta.editor.backend import api

from ..conftest import FAKE_PIPELINE_SCHEMA


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "mp.yaml"
    path.write_text("config_version: 0.4.0\nworkflows: {}\n")
    return path


@pytest.fixture
def client(monkeypatch, config):
    session = EditorSession()
    session.start(config)
    monkeypatch.setattr(api, "SESSION", session)
    return TestClient(api.app)


def add_step(client, **params) -> str:
    response = client.post(
        "/api/node/add/",
        json={"type": "nf-pipeline", "name": "nf-core/fetchngs", "version": "1.12.0", "params": params or None},
    )
    assert response.status_code == 200, response.json()
    return response.json()["events"][0]["workflow"]["id"]


def inputs(client) -> dict[str, dict]:
    return {i["name"]: i for i in client.get("/api/graph/").json()["inputs"]}


class TestInputState:
    def test_no_inputs(self, client):
        add_step(client)
        assert inputs(client) == {}

    def test_bound_input(self, client):
        step = add_step(client)
        client.post("/api/inputs/add/", json={"name": "ids", "definition": {"bind": [f"{step}.input"]}})
        ids = inputs(client)["ids"]
        assert ids["declared"] is True
        assert ids["bound_by"] == "bind"
        assert ids["bindings"] == [f"{step}.input"]
        assert ids["definition"] == {"bind": [f"{step}.input"]}
        assert ids["schema"]["type"] == FAKE_PIPELINE_SCHEMA["input"]["type"]

    def test_implicit_input(self, client):
        step = add_step(client, input="${inputs:ids}")
        ids = inputs(client)["ids"]
        assert ids["declared"] is False
        assert ids["definition"] is None
        assert ids["bound_by"] == "reference"
        assert ids["bindings"] == [f"{step}.input"]

    def test_declaration_adds_metadata_to_an_implicit_input(self, client):
        add_step(client, input="${inputs:ids}")
        response = client.post("/api/inputs/add/", json={"name": "ids", "definition": {"description": "Run ids"}})
        assert response.status_code == 200, response.json()
        ids = inputs(client)["ids"]
        assert (ids["declared"], ids["bound_by"], ids["description"]) == (True, "reference", "Run ids")

    def test_unused_input_has_a_warning(self, client):
        add_step(client)
        client.post("/api/inputs/add/", json={"name": "ids", "definition": {}})
        ids = inputs(client)["ids"]
        assert ids["bound_by"] is None
        assert ("warning", "not used by any step") in [(d["severity"], d["message"]) for d in ids["diagnostics"]]


class TestInputCommands:
    def test_unknown_param_is_a_field_error_on_the_input(self, client):
        step = add_step(client)
        response = client.post("/api/inputs/add/", json={"name": "ids", "definition": {"bind": [f"{step}.nope"]}})
        assert response.status_code == 422
        errors = response.json()["field_errors"]
        assert [(e["workflow_id"], e["field"]) for e in errors] == [(None, "inputs.ids.bind")]
        assert inputs(client) == {}

    def test_unknown_keyword_is_a_field_error_on_the_input(self, client):
        response = client.post("/api/inputs/add/", json={"name": "ids", "definition": {"colour": "red"}})
        assert response.status_code == 422
        assert [e["field"] for e in response.json()["field_errors"]] == ["inputs.ids.colour"]

    def test_invalid_name(self, client):
        response = client.post("/api/inputs/add/", json={"name": "a:b", "definition": {}})
        assert response.status_code == 422
        assert "Invalid input name" in response.json()["graph_errors"][0]

    def test_bind_and_reference_conflict_reported_at_the_param(self, client):
        step = add_step(client, input="${inputs:ids}")
        response = client.post("/api/inputs/add/", json={"name": "ids", "definition": {"bind": [f"{step}.input"]}})
        assert response.status_code == 422
        errors = response.json()["field_errors"]
        assert [(e["workflow_id"], e["field"]) for e in errors] == [(step, "params.input")]

    def test_update_delete_undo_redo(self, client, config):
        step = add_step(client)
        client.post("/api/inputs/add/", json={"name": "ids", "definition": {"bind": [f"{step}.input"]}})
        client.post(
            "/api/inputs/update/",
            json={"name": "ids", "definition": {"bind": [f"{step}.input"], "description": "Run ids"}},
        )
        assert inputs(client)["ids"]["description"] == "Run ids"
        assert yaml.safe_load(config.read_text())["inputs"]["ids"]["description"] == "Run ids"

        response = client.request("DELETE", "/api/inputs/delete/", json={"name": "ids"})
        assert response.status_code == 200
        assert inputs(client) == {}
        assert "inputs" not in yaml.safe_load(config.read_text())

        client.get("/api/graph/undo/")
        assert inputs(client)["ids"]["description"] == "Run ids"
        client.get("/api/graph/undo/")
        assert inputs(client)["ids"]["description"] == ""
        client.get("/api/graph/redo/")
        assert inputs(client)["ids"]["description"] == "Run ids"

    def test_events_carry_the_definition_as_written(self, client):
        step = add_step(client)
        response = client.post("/api/inputs/add/", json={"name": "ids", "definition": {"bind": f"{step}.input"}})
        assert response.json()["events"] == [
            {"type": "InputAdded", "name": "ids", "definition": {"bind": [f"{step}.input"]}}
        ]


class TestNodeSchema:
    def test_schema_of_a_step(self, client):
        step = add_step(client)
        assert client.get(f"/api/node/{step}/schema/").json() == FAKE_PIPELINE_SCHEMA

    def test_unknown_step(self, client):
        assert client.get("/api/node/nope/schema/").status_code == 404

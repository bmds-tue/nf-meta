import pytest
import yaml
from fastapi.testclient import TestClient

from nf_meta.core.session import EditorSession
from nf_meta.editor.backend import api
from nf_meta.editor.backend.guard import TOKEN_HEADER, configure_access

from ..conftest import FAKE_PIPELINE_SCHEMA


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "mp.yaml"
    path.write_text("config_version: 0.4.0\nworkflows: {}\n")
    return path


TOKEN = "test-token"


@pytest.fixture
def access(monkeypatch):
    """Restores the app's access settings after the test."""
    monkeypatch.setattr(api.app, "state", type(api.app.state)())
    configure_access(api.app, TOKEN)


@pytest.fixture
def client(monkeypatch, config, access):
    session = EditorSession()
    session.start(config)
    monkeypatch.setattr(api, "SESSION", session)
    return TestClient(api.app, base_url="http://127.0.0.1", headers={TOKEN_HEADER: TOKEN})


def add_step(client, **params) -> str:
    response = client.post(
        "/api/node/add/",
        json={"type": "nf-pipeline", "name": "nf-core/fetchngs", "version": "1.12.0", "params": params or None},
    )
    assert response.status_code == 200, response.json()
    return response.json()["events"][0]["workflow"]["id"]


def save_input(client, name, *, bindings=(), in_params=True, create=False, **extra):
    body = {"name": name, "bindings": list(bindings), "in_params": in_params, "create": create, **extra}
    return client.post("/api/inputs/save/", json=body)


def inputs(client) -> dict[str, dict]:
    return {i["name"]: i for i in client.get("/api/graph/").json()["inputs"]}


class TestInputState:
    def test_no_inputs(self, client):
        add_step(client)
        assert inputs(client) == {}

    def test_bound_input(self, client):
        step = add_step(client)
        save_input(client, "ids", bindings=[f"{step}.input"], in_params=False, create=True)
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
        step = add_step(client, input="${inputs:ids}")
        response = save_input(client, "ids", bindings=[f"{step}.input"], definition={"description": "Run ids"})
        assert response.status_code == 200, response.json()
        ids = inputs(client)["ids"]
        assert (ids["declared"], ids["bound_by"], ids["description"]) == (True, "reference", "Run ids")

    def test_unused_input_has_a_warning(self, client):
        add_step(client)
        save_input(client, "ids", create=True)
        ids = inputs(client)["ids"]
        assert ids["bound_by"] is None
        assert ("warning", "not used by any step") in [(d["severity"], d["message"]) for d in ids["diagnostics"]]


class TestInputCommands:
    def test_create_in_params(self, client):
        step = add_step(client)
        response = save_input(client, "ids", bindings=[f"{step}.input"], create=True)
        assert response.status_code == 200, response.json()
        assert client.get("/api/graph/").json()["nodes"][0]["params"] == {"input": "${inputs:ids}"}
        assert inputs(client)["ids"]["declared"] is False

    def test_unknown_param_is_a_field_error_on_the_input(self, client):
        step = add_step(client)
        response = save_input(client, "ids", bindings=[f"{step}.nope"], in_params=False, create=True)
        assert response.status_code == 422
        errors = response.json()["field_errors"]
        assert (None, "inputs.ids.bind") in [(e["workflow_id"], e["field"]) for e in errors]
        assert inputs(client) == {}

    def test_malformed_binding(self, client):
        response = save_input(client, "ids", bindings=["nodot"], create=True)
        assert [e["field"] for e in response.json()["field_errors"]] == ["inputs.ids.bind"]

    def test_unknown_keyword_is_a_field_error_on_the_input(self, client):
        response = save_input(client, "ids", create=True, definition={"colour": "red"})
        assert response.status_code == 422
        assert [e["field"] for e in response.json()["field_errors"]] == ["inputs.ids.colour"]

    def test_invalid_name(self, client):
        response = save_input(client, "a:b", create=True)
        assert response.status_code == 422
        assert "Invalid input name" in response.json()["graph_errors"][0]

    def test_rename_and_switch_style(self, client):
        step = add_step(client, input="${inputs:ids}")
        response = save_input(client, "ids", bindings=[f"{step}.input"], in_params=False, new_name="runs")
        assert response.status_code == 200, response.json()
        assert inputs(client)["runs"]["bound_by"] == "bind"
        assert client.get("/api/graph/").json()["nodes"][0]["params"] is None

    def test_delete_undo_redo(self, client, config):
        step = add_step(client, outdir="out")
        save_input(client, "ids", bindings=[f"{step}.input"], in_params=False, create=True)
        save_input(client, "ids", bindings=[f"{step}.input"], in_params=False, definition={"description": "Run ids"})
        assert inputs(client)["ids"]["description"] == "Run ids"
        assert yaml.safe_load(config.read_text())["inputs"]["ids"]["description"] == "Run ids"

        response = client.request("DELETE", "/api/inputs/delete/", json={"name": "ids"})
        assert response.status_code == 200, response.json()
        assert inputs(client) == {}

        client.get("/api/graph/undo/")
        assert inputs(client)["ids"]["description"] == "Run ids"
        client.get("/api/graph/redo/")
        assert inputs(client) == {}

    def test_set_inputs_style(self, client):
        add_step(client, input="${inputs:ids}")
        response = client.post("/api/inputs/style/", json={"in_params": False})
        assert response.status_code == 200, response.json()
        assert inputs(client)["ids"]["bound_by"] == "bind"
        client.post("/api/inputs/style/", json={"in_params": True})
        assert client.get("/api/graph/").json()["nodes"][0]["params"] == {"input": "${inputs:ids}"}

    def test_declare_step_inputs(self, client):
        step = add_step(client, input="${inputs:ids}")
        response = client.post(f"/api/node/{step}/declare-inputs/")
        assert response.status_code == 200, response.json()
        assert inputs(client)["ids"]["definition"] == {"bind": [f"{step}.input"]}

    def test_events_carry_the_definition_as_written(self, client):
        step = add_step(client)
        response = save_input(client, "ids", bindings=[f"{step}.input"], in_params=False, create=True)
        assert response.json()["events"] == [
            {"type": "InputAdded", "name": "ids", "definition": {"bind": [f"{step}.input"]}}
        ]


class TestSaveNode:
    def test_reference_to_an_unconnected_step_adds_the_edge(self, client):
        first = add_step(client, outdir="out")
        second = add_step(client, input=f"${{{first}:params:outdir}}/samplesheet.csv")
        transitions = client.get("/api/graph/").json()["transitions"]
        assert [(t["source"], t["target"]) for t in transitions] == [(first, second)]

    def test_update_adds_the_edge_too(self, client):
        first = add_step(client, outdir="out")
        second = add_step(client)
        node = next(n for n in client.get("/api/graph/").json()["nodes"] if n["id"] == second)
        response = client.post(
            "/api/node/update/", json={**node, "params": {"outdir": f"${{{first}:params:outdir}}/x"}}
        )
        assert response.status_code == 200, response.json()
        transitions = client.get("/api/graph/").json()["transitions"]
        assert [(t["source"], t["target"]) for t in transitions] == [(first, second)]


class TestDeleteNode:
    def test_edges_and_nodes_in_one_change(self, client):
        first = add_step(client, outdir="out")
        second = add_step(client, input=f"${{{first}:params:outdir}}/x.csv")
        third = add_step(client)
        client.post("/api/edge/add/", json={"source": third, "target": second})
        response = client.request("DELETE", "/api/delete/", json={"nodes": [third], "edges": [f"{third}->{second}"]})
        assert response.status_code == 200, response.json()
        state = client.get("/api/graph/").json()
        assert sorted(n["id"] for n in state["nodes"]) == sorted([first, second])
        assert [(t["source"], t["target"]) for t in state["transitions"]] == [(first, second)]
        client.get("/api/graph/undo/")
        assert len(client.get("/api/graph/").json()["nodes"]) == 3

    def test_bound_input_does_not_block_deleting_its_step(self, client):
        step = add_step(client)
        response = save_input(client, "count", bindings=[f"{step}.count"], in_params=False, create=True)
        assert response.status_code == 200, response.json()
        response = client.request("DELETE", "/api/delete/", json={"nodes": [step], "edges": []})
        assert response.status_code == 200, response.json()
        count = inputs(client)["count"]
        assert (count["bindings"], count["bound_by"]) == ([], None)
        assert ("warning", "not used by any step") in [(d["severity"], d["message"]) for d in count["diagnostics"]]


class TestLoadAndSave:
    def test_missing_file(self, client, tmp_path):
        response = client.post("/api/graph/load/", json={"config": str(tmp_path / "nope.yaml")})
        assert response.status_code == 404
        assert "No such file" in response.json()["detail"]

    def test_invalid_config_keeps_the_current_one(self, client, config, tmp_path):
        add_step(client)
        bad = tmp_path / "bad.yaml"
        bad.write_text("config_version: 0.4.0\nworkflows:\n  n01: {name: nf-core/nope, version: '1'}\n")
        response = client.post("/api/graph/load/", json={"config": str(bad)})
        assert response.status_code == 422
        assert response.json()["detail"].startswith("Invalid config: ")
        state = client.get("/api/graph/").json()
        assert (state["filename"], len(state["nodes"])) == (str(config), 1)

    def test_save_to_an_unwritable_place(self, client, tmp_path):
        response = client.post("/api/graph/save/", json={"config": str(tmp_path / "missing-dir" / "mp.yaml")})
        assert response.status_code == 400
        assert "Can't write" in response.json()["detail"]


class TestFiles:
    def test_starts_in_the_folder_of_the_config(self, client, config):
        listing = client.get("/api/files/").json()
        assert listing["path"] == str(config.parent.resolve())
        assert ("file", "mp.yaml") in [(e["kind"], e["name"]) for e in listing["entries"]]

    def test_missing_folder(self, client, tmp_path):
        response = client.get("/api/files/", params={"path": str(tmp_path / "nope")})
        assert response.status_code == 404
        assert "No such folder" in response.json()["detail"]


class TestNodeSchema:
    def test_schema_of_a_step(self, client):
        step = add_step(client)
        assert client.get(f"/api/node/{step}/schema/").json() == FAKE_PIPELINE_SCHEMA

    def test_unknown_step(self, client):
        assert client.get("/api/node/nope/schema/").status_code == 404


class TestAccess:
    def test_api_needs_the_token(self, client):
        assert client.get("/api/graph/", headers={TOKEN_HEADER: ""}).status_code == 401
        assert client.get("/api/graph/", headers={TOKEN_HEADER: "wrong"}).status_code == 401
        assert client.get("/api/graph/").status_code == 200

    def test_no_configured_token_refuses_the_api(self, client):
        configure_access(api.app, None)
        assert client.get("/api/graph/").status_code == 401

    def test_page_loads_without_the_token(self, client):
        assert client.get("/", headers={TOKEN_HEADER: ""}).status_code == 200

    @pytest.mark.parametrize("path", ["/", "/api/graph/"])
    def test_foreign_host_is_refused(self, client, path):
        response = client.get(path, headers={"host": "evil.example"})
        assert response.status_code == 400

    @pytest.mark.parametrize("host", ["localhost:1234", "127.0.0.1", "[::1]:8080"])
    def test_loopback_hosts_are_accepted(self, client, host):
        assert client.get("/api/graph/", headers={"host": host}).status_code == 200

    def test_bind_host_is_accepted(self, client):
        configure_access(api.app, TOKEN, bind_host="csdnode1")
        assert client.get("/api/graph/", headers={"host": "csdnode1:8080"}).status_code == 200
        assert client.get("/api/graph/", headers={"host": "other:8080"}).status_code == 400

    def test_wildcard_bind_host_accepts_any_host_but_needs_the_token(self, client):
        configure_access(api.app, TOKEN, bind_host="0.0.0.0")
        assert client.get("/api/graph/", headers={"host": "other:8080"}).status_code == 200
        assert client.get("/api/graph/", headers={"host": "other:8080", TOKEN_HEADER: ""}).status_code == 401


class TestShutdown:
    def test_shutdown_stops_the_server(self, client):
        stopped = []
        api.configure_shutdown(api.app, lambda: stopped.append(True))
        assert client.post("/api/shutdown/").json() == {"ok": True}
        assert stopped == [True]

    def test_shutdown_needs_the_token(self, client):
        stopped = []
        api.configure_shutdown(api.app, lambda: stopped.append(True))
        assert client.post("/api/shutdown/", headers={TOKEN_HEADER: ""}).status_code == 401
        assert stopped == []

    def test_shutdown_without_a_server(self, client):
        response = client.post("/api/shutdown/")
        assert response.status_code == 503
        assert "can't be stopped" in response.json()["detail"]

    def test_ping(self, client):
        assert client.get("/api/ping/").json() == {"ok": True}
        assert client.get("/api/ping/", headers={TOKEN_HEADER: ""}).status_code == 401

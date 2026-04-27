from fastapi.testclient import TestClient
import pytest

from preon_systems_cell.web import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["storage"]["primary"] == "postgres"
    assert payload["storage"]["fallback"] == "memory"
    assert payload["storage"]["mode"] in {"postgres", "memory"}


def test_default_scenario_endpoint():
    response = client.get("/api/default-scenario")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario"]["version"] == 3
    assert payload["scenario"]["scenario_name"] == "default_cell"
    assert payload["scenario"]["environment"]["glucose_concentration"] == 24.0
    assert payload["scenario"]["environment"]["electron_acceptor_concentration"] == 24.0
    assert payload["scenario"]["cell"]["initial_cell_id"] == "cell-1"
    assert payload["scenario"]["cell"]["cytosol"]["nad_plus"] == 10.0


def test_validate_endpoint_accepts_default_scenario():
    scenario = client.get("/api/default-scenario").json()["scenario"]

    response = client.post("/api/validate", json={"scenario": scenario, "seed": 7})

    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_create_cell_endpoint_supports_xyz():
    scenario = client.get("/api/default-scenario").json()["scenario"]

    response = client.post(
        "/api/cells",
        json={
            "scenario": scenario,
            "cell": {
                "name": "Navigator",
                "initial_cell_id": "nav-1",
                "initial_atp": 17,
                "glucose_transporter_density": 2.0,
                "cytosol": {
                    "glucose": 2.5,
                    "pyruvate": 1.0,
                    "nadh": 0.5,
                    "acetyl_coa": 0.25,
                    "nad_plus": 9.0,
                    "fad": 3.0,
                    "fadh2": 0.75,
                    "co2": 1.25,
                    "membrane_gradient": 2.5,
                },
                "x": 11.5,
                "y": -4.25,
                "z": 0.75,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    cell = payload["state"]["cells"][0]
    assert payload["scenario"]["cell"]["x"] == 11.5
    assert cell["id"] == "nav-1"
    assert cell["name"] == "Navigator"
    assert cell["glucose_transporter_density"] == 2.0
    assert cell["cytosol"]["glucose"] == 2.5
    assert cell["cytosol"]["membrane_gradient"] == 2.5
    assert cell["z"] == 0.75


def test_run_endpoint_returns_population_artifacts():
    scenario = client.get("/api/default-scenario").json()["scenario"]

    response = client.post("/api/run", json={"scenario": scenario, "seed": 7, "max_steps": 4})

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["seed"] == 7
    assert payload["final_state"]["step"] >= 1
    assert payload["final_state"]["cells"]
    assert "environment_glucose" in payload["metrics"][0]
    assert "environment_electron_acceptor" in payload["metrics"][0]
    assert "alive_count" in payload["metrics"][0]
    assert payload["snapshots"][0]["state"]["cells"]
    assert payload["metrics"]
    assert payload["metadata"]["run_id"].startswith("run-")
    runs_response = client.get("/api/runs")
    assert runs_response.status_code == 200
    assert any(run["run_id"] == payload["metadata"]["run_id"] for run in runs_response.json()["runs"])


def test_run_endpoint_rejects_non_positive_max_steps():
    scenario = client.get("/api/default-scenario").json()["scenario"]

    response = client.post("/api/run", json={"scenario": scenario, "seed": 7, "max_steps": 0})

    assert response.status_code == 422


def test_run_centric_endpoints_expose_metrics_lineage_cells_and_events():
    scenario = client.get("/api/default-scenario").json()["scenario"]

    create_response = client.post("/api/runs", json={"scenario": scenario, "seed": 7, "max_steps": 8})

    assert create_response.status_code == 200
    run_id = create_response.json()["run"]["run_id"]

    run_response = client.get(f"/api/runs/{run_id}")
    metrics_response = client.get(f"/api/runs/{run_id}/metrics", params={"from_step": 1, "resolution": 2})
    lineage_response = client.get(f"/api/runs/{run_id}/lineage", params={"root": "cell-1"})
    cell_response = client.get(f"/api/runs/{run_id}/cells/cell-1")
    events_response = client.get(f"/api/runs/{run_id}/cells/cell-1/events", params={"scope": "lineage"})

    assert run_response.status_code == 200
    assert metrics_response.status_code == 200
    assert lineage_response.status_code == 200
    assert cell_response.status_code == 200
    assert events_response.status_code == 200
    assert metrics_response.json()["run_id"] == run_id
    assert metrics_response.json()["series"]
    assert lineage_response.json()["nodes"][0]["id"] == "cell-1"
    assert cell_response.json()["cell"]["id"] == "cell-1"
    assert events_response.json()["events"]


def test_run_analytics_endpoints_expose_timeseries_and_intelligence():
    scenario = client.get("/api/default-scenario").json()["scenario"]
    run_id = client.post("/api/runs", json={"scenario": scenario, "seed": 41, "max_steps": 8}).json()["run"]["run_id"]

    timeseries_response = client.get(f"/api/runs/{run_id}/timeseries", params={"from_step": 2, "resolution": 2})
    intelligence_response = client.get(f"/api/runs/{run_id}/intelligence")

    assert timeseries_response.status_code == 200
    assert intelligence_response.status_code == 200
    points = timeseries_response.json()["points"]
    assert points
    assert all((point["step"] - 2) % 2 == 0 for point in points)
    assert "atp_per_alive_cell" in points[0]
    assert intelligence_response.json()["peak_population"] >= 1
    assert intelligence_response.json()["collapse_cause"]


def test_compare_endpoint_supports_n_runs_and_validates_bounds():
    scenario = client.get("/api/default-scenario").json()["scenario"]
    run_ids = [
        client.post("/api/runs", json={"scenario": scenario, "seed": seed, "max_steps": 4}).json()["run"]["run_id"]
        for seed in (51, 53, 59)
    ]

    response = client.get("/api/runs/compare", params={"runs": ",".join(run_ids), "resolution": 1})
    single_response = client.get("/api/runs/compare", params={"runs": run_ids[0]})
    repeated_response = client.get("/api/runs/compare", params={"runs": f"{run_ids[0]},{run_ids[0]}"})
    missing_response = client.get("/api/runs/compare", params={"runs": f"{run_ids[0]},missing-run"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline_run_id"] == run_ids[0]
    assert [run["run_id"] for run in payload["runs"]] == run_ids
    assert set(payload["deltas"]) == {run_ids[1], run_ids[2]}
    assert payload["aligned_series"]
    assert single_response.status_code == 422
    assert repeated_response.status_code == 422
    assert missing_response.status_code == 404


def test_step_window_endpoints_reject_inverted_ranges():
    scenario = client.get("/api/default-scenario").json()["scenario"]
    run_ids = [
        client.post("/api/runs", json={"scenario": scenario, "seed": seed, "max_steps": 4}).json()["run"]["run_id"]
        for seed in (71, 73)
    ]

    metrics_response = client.get(f"/api/runs/{run_ids[0]}/metrics", params={"from_step": 3, "to_step": 1})
    timeseries_response = client.get(f"/api/runs/{run_ids[0]}/timeseries", params={"from_step": 3, "to_step": 1})
    compare_response = client.get(
        "/api/runs/compare",
        params={"runs": ",".join(run_ids), "from_step": 3, "to_step": 1},
    )

    assert metrics_response.status_code == 422
    assert timeseries_response.status_code == 422
    assert compare_response.status_code == 422


def test_compare_endpoint_rejects_more_than_eight_runs():
    scenario = client.get("/api/default-scenario").json()["scenario"]
    run_ids = [
        client.post("/api/runs", json={"scenario": scenario, "seed": seed, "max_steps": 1}).json()["run"]["run_id"]
        for seed in range(61, 70)
    ]

    response = client.get("/api/runs/compare", params={"runs": ",".join(run_ids)})

    assert response.status_code == 422


def test_run_centric_cell_routes_reject_unknown_cell():
    scenario = client.get("/api/default-scenario").json()["scenario"]
    run_id = client.post("/api/runs", json={"scenario": scenario, "seed": 7, "max_steps": 2}).json()["run"]["run_id"]

    lineage_response = client.get(f"/api/runs/{run_id}/lineage", params={"root": "missing-cell"})
    events_response = client.get(f"/api/runs/{run_id}/cells/missing-cell/events")

    assert lineage_response.status_code == 404
    assert events_response.status_code == 404


def test_run_exports_can_be_created_and_downloaded():
    pytest.importorskip("pyarrow")
    scenario = client.get("/api/default-scenario").json()["scenario"]
    run_id = client.post("/api/runs", json={"scenario": scenario, "seed": 19, "max_steps": 4}).json()["run"]["run_id"]

    initial_response = client.get(f"/api/runs/{run_id}/exports")
    create_response = client.post(f"/api/runs/{run_id}/exports", json={"formats": ["parquet", "powerbi"]})
    download_response = client.get(f"/api/runs/{run_id}/exports/powerbi/download")

    assert initial_response.status_code == 200
    assert initial_response.json()["manifest"] is None
    assert create_response.status_code == 200
    assert create_response.json()["manifest"]["run_id"] == run_id
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "application/zip"
    assert download_response.content.startswith(b"PK")


def test_run_exports_reject_unknown_format():
    scenario = client.get("/api/default-scenario").json()["scenario"]
    run_id = client.post("/api/runs", json={"scenario": scenario, "seed": 23, "max_steps": 2}).json()["run"]["run_id"]

    response = client.post(f"/api/runs/{run_id}/exports", json={"formats": ["csv"]})

    assert response.status_code == 422


def test_run_stream_replays_metric_steps():
    scenario = client.get("/api/default-scenario").json()["scenario"]
    run_id = client.post("/api/runs", json={"scenario": scenario, "seed": 3, "max_steps": 3}).json()["run"]["run_id"]

    with client.websocket_connect(f"/api/runs/{run_id}/stream") as websocket:
        first = websocket.receive_json()
        complete_seen = False
        while first["type"] != "complete":
            assert first["type"] == "step"
            assert first["run_id"] == run_id
            assert "metrics" in first
            first = websocket.receive_json()
        complete_seen = first["type"] == "complete"

    assert complete_seen is True


def test_run_updates_websocket_broadcasts_created_runs():
    scenario = client.get("/api/default-scenario").json()["scenario"]

    with client.websocket_connect("/api/runs/updates") as websocket:
        response = client.post("/api/runs", json={"scenario": scenario, "seed": 5, "max_steps": 2})
        assert response.status_code == 200
        run_id = response.json()["run"]["run_id"]
        message = websocket.receive_json()

    assert message["type"] == "run_created"
    assert message["run"]["run_id"] == run_id
    assert message["storage"]["mode"] in {"postgres", "memory"}


def test_root_serves_frontend():
    response = client.get("/")

    assert response.status_code == 200
    assert "Cell v3 Population Engine" in response.text

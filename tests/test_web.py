from fastapi.testclient import TestClient

from preon_systems_cell.web import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_default_scenario_endpoint():
    response = client.get("/api/default-scenario")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario"]["scenario_name"] == "default_cell"


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
                "initial_atp": 17,
                "x": 11.5,
                "y": -4.25,
                "z": 0.75,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario"]["cell"]["x"] == 11.5
    assert payload["state"]["cell"]["name"] == "Navigator"
    assert payload["state"]["cell"]["z"] == 0.75


def test_run_endpoint_returns_artifacts():
    scenario = client.get("/api/default-scenario").json()["scenario"]

    response = client.post("/api/run", json={"scenario": scenario, "seed": 7, "max_steps": 4})

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["seed"] == 7
    assert payload["final_state"]["step"] >= 1
    assert payload["metrics"]


def test_root_serves_frontend():
    response = client.get("/")

    assert response.status_code == 200
    assert "Design a cell, place it in space, and run the simulation." in response.text

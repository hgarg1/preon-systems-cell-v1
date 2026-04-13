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
    assert payload["scenario"]["environment"]["glucose_concentration"] == 24.0
    assert payload["scenario"]["environment"]["electron_acceptor_concentration"] == 24.0
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
    assert payload["scenario"]["cell"]["x"] == 11.5
    assert payload["state"]["cell"]["name"] == "Navigator"
    assert payload["state"]["cell"]["glucose_transporter_density"] == 2.0
    assert payload["state"]["cell"]["cytosol"]["glucose"] == 2.5
    assert payload["state"]["cell"]["cytosol"]["membrane_gradient"] == 2.5
    assert payload["state"]["cell"]["z"] == 0.75


def test_run_endpoint_returns_artifacts():
    scenario = client.get("/api/default-scenario").json()["scenario"]

    response = client.post("/api/run", json={"scenario": scenario, "seed": 7, "max_steps": 4})

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["seed"] == 7
    assert payload["final_state"]["step"] >= 1
    assert "environment_glucose" in payload["metrics"][0]
    assert "environment_electron_acceptor" in payload["metrics"][0]
    assert "membrane_gradient" in payload["metrics"][0]
    assert payload["metrics"]


def test_root_serves_frontend():
    response = client.get("/")

    assert response.status_code == 200
    assert "Cell v2 Simulation Engine" in response.text

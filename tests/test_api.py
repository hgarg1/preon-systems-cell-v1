from pathlib import Path
from random import Random

import pytest

from preon_systems_cell.analytics.features import extract_cell_features, extract_run_features
from preon_systems_cell.api import create_cell, load_scenario, run_simulation, step_simulation, validate_scenario
from preon_systems_cell.engine import initial_state_for_scenario
from preon_systems_cell.models import CellCreateParams, CytosolCreateParams, TerminationReason


SCENARIO_PATH = Path("scenarios/default_cell.yaml")


def test_load_and_validate_scenario():
    scenario = load_scenario(SCENARIO_PATH)
    report = validate_scenario(scenario)
    assert report.valid is True
    assert scenario.version == 3


def test_step_simulation_advances_population_state_and_tracks_aggregate_metrics():
    scenario = load_scenario(SCENARIO_PATH)
    state = initial_state_for_scenario(scenario)

    transition = step_simulation(state, dt=scenario.simulation.dt, rng=Random(7), scenario=scenario)

    assert transition.state.step == 1
    assert transition.state.time == scenario.simulation.dt
    assert transition.metrics.total_atp >= 0
    assert transition.metrics.environment_glucose >= 0
    assert transition.metrics.population_count >= 1
    assert transition.snapshot.state.step == 1
    assert transition.state.cells[0].x != state.cells[0].x or transition.state.cells[0].z != state.cells[0].z
    assert transition.events


def test_create_cell_supports_position_and_cytosol_overrides():
    scenario = load_scenario(SCENARIO_PATH)

    created = create_cell(
        scenario,
        CellCreateParams(
            name="Scout",
            initial_cell_id="scout-1",
            initial_atp=18.0,
            glucose_transporter_density=2.25,
            cytosol=CytosolCreateParams(
                glucose=3.5,
                pyruvate=1.0,
                nadh=0.5,
                acetyl_coa=0.25,
                nad_plus=9.0,
                fad=3.0,
                fadh2=0.75,
                co2=1.25,
                membrane_gradient=2.5,
            ),
            x=3.5,
            y=-2.0,
            z=8.25,
        ),
    )
    cell = created.state.cells[0]

    assert created.scenario.cell.name == "Scout"
    assert cell.id == "scout-1"
    assert cell.energy.atp == 18.0
    assert cell.glucose_transporter_density == 2.25
    assert cell.cytosol.glucose == 3.5
    assert cell.cytosol.pyruvate == 1.0
    assert cell.cytosol.nadh == 0.5
    assert cell.cytosol.acetyl_coa == 0.25
    assert cell.cytosol.nad_plus == 9.0
    assert cell.cytosol.fad == 3.0
    assert cell.cytosol.fadh2 == 0.75
    assert cell.cytosol.co2 == 1.25
    assert cell.cytosol.membrane_gradient == 2.5
    assert cell.x == 3.5
    assert cell.y == -2.0
    assert cell.z == 8.25


def test_run_simulation_is_deterministic(tmp_path):
    scenario = load_scenario(SCENARIO_PATH)

    run_a = run_simulation(scenario, seed=11, output_dir=tmp_path / "a")
    run_b = run_simulation(scenario, seed=11, output_dir=tmp_path / "b")

    assert run_a.termination_reason == run_b.termination_reason
    assert run_a.final_state.model_dump(mode="json") == run_b.final_state.model_dump(mode="json")
    assert [metric.model_dump(mode="json") for metric in run_a.metrics] == [
        metric.model_dump(mode="json") for metric in run_b.metrics
    ]
    assert [snapshot.model_dump(mode="json") for snapshot in run_a.snapshots] == [
        snapshot.model_dump(mode="json") for snapshot in run_b.snapshots
    ]


def test_run_produces_expected_artifacts(tmp_path):
    scenario = load_scenario(SCENARIO_PATH)

    run = run_simulation(scenario, seed=3, output_dir=tmp_path)

    assert run.termination_reason in set(TerminationReason)
    assert run.snapshots
    assert any(
        snapshot.state.cells[0].x != scenario.cell.x
        or snapshot.state.cells[0].y != scenario.cell.y
        or snapshot.state.cells[0].z != scenario.cell.z
        for snapshot in run.snapshots
    )
    assert all(metric.environment_glucose >= 0 for metric in run.metrics)
    assert (tmp_path / "resolved_scenario.json").exists()
    assert (tmp_path / "run_metadata.json").exists()
    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "snapshots.json").exists()
    assert (tmp_path / "events.json").exists()
    assert (tmp_path / "final_state.json").exists()
    assert (tmp_path / "run_summary.json").exists()
    assert (tmp_path / "analytics" / "step_metrics.jsonl").exists()
    assert (tmp_path / "analytics" / "cell_events.jsonl").exists()
    assert (tmp_path / "analytics" / "cells.jsonl").exists()
    assert (tmp_path / "features" / "run_features.json").exists()
    assert (tmp_path / "features" / "cell_features.json").exists()


def test_run_fallback_snapshot_matches_final_state_when_record_every_skips_steps():
    base = load_scenario(SCENARIO_PATH)
    scenario = base.model_copy(update={"simulation": base.simulation.model_copy(update={"record_every": 100})})

    run = run_simulation(scenario, seed=5, max_steps=2)

    assert len(run.metrics) == 2
    assert len(run.snapshots) == 1
    assert run.metrics[-1].step == run.final_state.step
    assert run.snapshots[0].state.model_dump(mode="json") == run.final_state.model_dump(mode="json")


def test_run_simulation_rejects_non_positive_max_steps():
    scenario = load_scenario(SCENARIO_PATH)

    with pytest.raises(ValueError, match="max_steps"):
        run_simulation(scenario, seed=5, max_steps=0)


def test_feature_extractors_emit_run_and_cell_feature_rows():
    scenario = load_scenario(SCENARIO_PATH)

    run = run_simulation(scenario, seed=9, max_steps=4)
    run_features = extract_run_features(run)
    cell_features = extract_cell_features(run)

    assert run_features["feature_version"] == "cell-platform-v1"
    assert run_features["final_population"] == run.metrics[-1].population_count
    assert cell_features
    assert all(row["feature_version"] == "cell-platform-v1" for row in cell_features)

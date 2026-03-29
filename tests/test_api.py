from pathlib import Path
from random import Random

from preon_systems_cell.api import create_cell, load_scenario, run_simulation, step_simulation, validate_scenario
from preon_systems_cell.engine import initial_state_for_scenario
from preon_systems_cell.models import CellCreateParams, TerminationReason


SCENARIO_PATH = Path("scenarios/default_cell.yaml")


def test_load_and_validate_scenario():
    scenario = load_scenario(SCENARIO_PATH)
    report = validate_scenario(scenario)
    assert report.valid is True


def test_step_simulation_advances_state():
    scenario = load_scenario(SCENARIO_PATH)
    state = initial_state_for_scenario(scenario)

    transition = step_simulation(state, dt=scenario.simulation.dt, rng=Random(7), scenario=scenario)

    assert transition.state.step == 1
    assert transition.state.time == scenario.simulation.dt
    assert transition.metrics.atp >= 0
    assert transition.state.cell.x != state.cell.x or transition.state.cell.y != state.cell.y or transition.state.cell.z != state.cell.z
    assert transition.metrics.x == transition.state.cell.x
    assert transition.events


def test_create_cell_supports_position_and_overrides():
    scenario = load_scenario(SCENARIO_PATH)

    created = create_cell(
        scenario,
        CellCreateParams(name="Scout", initial_atp=18.0, x=3.5, y=-2.0, z=8.25),
    )

    assert created.scenario.cell.name == "Scout"
    assert created.state.cell.energy.atp == 18.0
    assert created.state.cell.x == 3.5
    assert created.state.cell.y == -2.0
    assert created.state.cell.z == 8.25


def test_run_simulation_is_deterministic(tmp_path):
    scenario = load_scenario(SCENARIO_PATH)

    run_a = run_simulation(scenario, seed=11, output_dir=tmp_path / "a")
    run_b = run_simulation(scenario, seed=11, output_dir=tmp_path / "b")

    assert run_a.termination_reason == run_b.termination_reason
    assert run_a.final_state.model_dump(mode="json") == run_b.final_state.model_dump(mode="json")
    assert [metric.model_dump(mode="json") for metric in run_a.metrics] == [
        metric.model_dump(mode="json") for metric in run_b.metrics
    ]


def test_run_produces_expected_artifacts(tmp_path):
    scenario = load_scenario(SCENARIO_PATH)

    run = run_simulation(scenario, seed=3, output_dir=tmp_path)

    assert run.termination_reason in set(TerminationReason)
    assert any(
        metric.x != scenario.cell.x or metric.y != scenario.cell.y or metric.z != scenario.cell.z
        for metric in run.metrics
    )
    assert (tmp_path / "resolved_scenario.json").exists()
    assert (tmp_path / "run_metadata.json").exists()
    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "events.json").exists()
    assert (tmp_path / "final_state.json").exists()
    assert (tmp_path / "run_summary.json").exists()

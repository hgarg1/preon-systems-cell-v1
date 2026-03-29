from pathlib import Path
from random import Random

from preon_systems_cell.api import load_scenario, run_simulation, step_simulation, validate_scenario
from preon_systems_cell.engine import initial_state_for_scenario
from preon_systems_cell.models import TerminationReason


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
    assert transition.events


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
    assert (tmp_path / "resolved_scenario.json").exists()
    assert (tmp_path / "run_metadata.json").exists()
    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "events.json").exists()
    assert (tmp_path / "final_state.json").exists()
    assert (tmp_path / "run_summary.json").exists()

from datetime import UTC, datetime
from pathlib import Path

import pytest

from preon_systems_cell.analytics.comparison import compare_runs
from preon_systems_cell.analytics.intelligence import summarize_run_intelligence
from preon_systems_cell.analytics.series import build_time_series
from preon_systems_cell.api import load_scenario, run_simulation
from preon_systems_cell.domain.runs import RunRecord, RunStatus


SCENARIO_PATH = Path("scenarios/default_cell.yaml")


def test_time_series_downsamples_and_adds_energy_per_cell():
    artifacts = run_simulation(load_scenario(SCENARIO_PATH), seed=101, max_steps=6)

    points = build_time_series(artifacts, from_step=2, resolution=2)

    assert points
    assert all((point.step - 2) % 2 == 0 for point in points)
    assert all(point.step >= 2 for point in points)
    assert all(point.atp_per_population_cell is not None for point in points)


def test_run_intelligence_computes_peak_growth_and_efficiency():
    artifacts = run_simulation(load_scenario(SCENARIO_PATH), seed=103, max_steps=8)

    intelligence = summarize_run_intelligence(artifacts)

    assert intelligence.run_id == artifacts.metadata.run_id
    assert intelligence.peak_population == max(metric.population_count for metric in artifacts.metrics)
    assert intelligence.time_to_peak_step is not None
    assert intelligence.lifespan_steps == artifacts.final_state.step
    assert 0 <= intelligence.survival_ratio <= 1
    assert intelligence.collapse_cause


def test_compare_runs_aligns_multiple_run_series_and_uses_first_as_baseline():
    scenario = load_scenario(SCENARIO_PATH)
    artifacts = [
        run_simulation(scenario, seed=111, max_steps=4),
        run_simulation(scenario, seed=113, max_steps=6),
        run_simulation(scenario, seed=117, max_steps=8),
    ]
    pairs = [(_record_for(item), item) for item in artifacts]

    comparison = compare_runs(pairs, resolution=1)

    assert comparison.baseline_run_id == artifacts[0].metadata.run_id
    assert [run.run_id for run in comparison.runs] == [item.metadata.run_id for item in artifacts]
    assert comparison.runs[0].role == "baseline"
    assert set(comparison.deltas) == {artifacts[1].metadata.run_id, artifacts[2].metadata.run_id}
    assert comparison.aligned_series
    assert any(
        point.population[artifacts[0].metadata.run_id] is None
        for point in comparison.aligned_series
        if point.step > artifacts[0].final_state.step
    )


def test_compare_rejects_single_run():
    artifacts = run_simulation(load_scenario(SCENARIO_PATH), seed=119, max_steps=2)

    with pytest.raises(ValueError, match="at least two"):
        compare_runs([(_record_for(artifacts), artifacts)])


def _record_for(artifacts):
    return RunRecord(
        run_id=artifacts.metadata.run_id,
        scenario_name=artifacts.metadata.scenario_name,
        scenario_hash="test",
        seed=artifacts.metadata.seed,
        status=RunStatus.COMPLETED,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        max_steps=artifacts.metadata.max_steps,
        final_step=artifacts.final_state.step,
        termination_reason=artifacts.termination_reason.value,
    )

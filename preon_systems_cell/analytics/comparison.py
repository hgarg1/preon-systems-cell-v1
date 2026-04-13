from __future__ import annotations

from collections.abc import Sequence

from preon_systems_cell.analytics.intelligence import summarize_run_intelligence
from preon_systems_cell.analytics.series import build_time_series
from preon_systems_cell.domain.runs import RunRecord
from preon_systems_cell.models import (
    ComparedRun,
    ComparisonPoint,
    MetricDelta,
    RunArtifacts,
    RunComparisonResponse,
    RunIntelligence,
)


COMPARE_METRICS = (
    "peak_population",
    "time_to_peak_step",
    "lifespan_steps",
    "early_growth_rate",
    "late_growth_rate",
    "growth_rate_delta",
    "survival_ratio",
    "energy_per_alive_cell_final",
    "energy_per_population_cell_final",
    "division_intensity",
)


def compare_runs(
    runs: Sequence[tuple[RunRecord, RunArtifacts]],
    resolution: int = 1,
    from_step: int = 0,
    to_step: int | None = None,
) -> RunComparisonResponse:
    if len(runs) < 2:
        raise ValueError("at least two runs are required for comparison")
    intelligence_by_run = {
        run.run_id: summarize_run_intelligence(artifacts) for run, artifacts in runs
    }
    baseline_run = runs[0][0]
    baseline = intelligence_by_run[baseline_run.run_id]
    compared_runs = [
        ComparedRun(
            run_id=run.run_id,
            scenario_name=run.scenario_name,
            seed=run.seed,
            status=run.status.value,
            role="baseline" if index == 0 else "comparison",
            intelligence=intelligence_by_run[run.run_id],
        )
        for index, (run, _artifacts) in enumerate(runs)
    ]
    return RunComparisonResponse(
        baseline_run_id=baseline_run.run_id,
        runs=compared_runs,
        deltas=_deltas(baseline, intelligence_by_run),
        aligned_series=_aligned_series(runs, resolution, from_step, to_step),
    )


def _deltas(
    baseline: RunIntelligence,
    intelligence_by_run: dict[str, RunIntelligence],
) -> dict[str, dict[str, MetricDelta]]:
    rows = {}
    for run_id, intelligence in intelligence_by_run.items():
        if run_id == baseline.run_id:
            continue
        rows[run_id] = {}
        for metric_name in COMPARE_METRICS:
            baseline_value = getattr(baseline, metric_name)
            value = getattr(intelligence, metric_name)
            rows[run_id][metric_name] = _metric_delta(baseline_value, value)
    return rows


def _metric_delta(baseline: float | int | None, value: float | int | None) -> MetricDelta:
    if baseline is None or value is None:
        return MetricDelta(baseline=baseline, value=value, absolute_delta=None, percent_delta=None)
    absolute_delta = value - baseline
    percent_delta = ((absolute_delta / abs(baseline)) * 100) if baseline != 0 else None
    return MetricDelta(
        baseline=baseline,
        value=value,
        absolute_delta=absolute_delta,
        percent_delta=percent_delta,
    )


def _aligned_series(
    runs: Sequence[tuple[RunRecord, RunArtifacts]],
    resolution: int,
    from_step: int,
    to_step: int | None,
) -> list[ComparisonPoint]:
    series_by_run = {
        run.run_id: {
            point.step: point
            for point in build_time_series(artifacts, from_step=from_step, to_step=to_step, resolution=resolution)
        }
        for run, artifacts in runs
    }
    steps = sorted({step for series in series_by_run.values() for step in series})
    points = []
    for step in steps:
        population: dict[str, int | None] = {}
        total_atp: dict[str, float | None] = {}
        atp_per_alive_cell: dict[str, float | None] = {}
        for run_id, series in series_by_run.items():
            point = series.get(step)
            population[run_id] = point.population if point else None
            total_atp[run_id] = point.total_atp if point else None
            atp_per_alive_cell[run_id] = point.atp_per_alive_cell if point else None
        points.append(
            ComparisonPoint(
                step=step,
                population=population,
                total_atp=total_atp,
                atp_per_alive_cell=atp_per_alive_cell,
            )
        )
    return points

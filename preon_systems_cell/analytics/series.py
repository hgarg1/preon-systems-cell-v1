from __future__ import annotations

from preon_systems_cell.models import RunArtifacts, RunTimeSeriesPoint


def build_time_series(
    artifacts: RunArtifacts,
    from_step: int = 0,
    to_step: int | None = None,
    resolution: int = 1,
) -> list[RunTimeSeriesPoint]:
    stride = max(resolution, 1)
    points = []
    for metric in artifacts.metrics:
        if metric.step < from_step:
            continue
        if to_step is not None and metric.step > to_step:
            continue
        if (metric.step - from_step) % stride != 0:
            continue
        points.append(
            RunTimeSeriesPoint(
                step=metric.step,
                time=metric.time,
                population=metric.population_count,
                alive=metric.alive_count,
                dead=metric.dead_count,
                divided=metric.divided_count,
                division_count_total=metric.division_count_total,
                total_atp=metric.total_atp,
                total_biomass=metric.total_biomass,
                atp_per_alive_cell=_safe_divide(metric.total_atp, metric.alive_count),
                atp_per_population_cell=_safe_divide(metric.total_atp, metric.population_count),
                environment_glucose=metric.environment_glucose,
                environment_electron_acceptor=metric.environment_electron_acceptor,
                toxicity=metric.toxicity,
            )
        )
    return points


def _safe_divide(numerator: float, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator

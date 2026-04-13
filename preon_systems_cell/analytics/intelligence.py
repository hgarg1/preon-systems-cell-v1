from __future__ import annotations

import math

from preon_systems_cell.models import PopulationMetrics, RunArtifacts, RunIntelligence, TerminationReason


def summarize_run_intelligence(artifacts: RunArtifacts) -> RunIntelligence:
    metrics = artifacts.metrics
    final = metrics[-1] if metrics else None
    peak_population = max((metric.population_count for metric in metrics), default=0)
    peak_metric = next((metric for metric in metrics if metric.population_count == peak_population), None)
    lifespan_steps = artifacts.final_state.step
    early_window, late_window = _growth_windows(metrics)
    early_growth_rate = _growth_rate(early_window)
    late_growth_rate = _growth_rate(late_window)
    final_population = final.population_count if final else 0
    final_alive = final.alive_count if final else 0
    final_atp = final.total_atp if final else 0.0
    final_divisions = final.division_count_total if final else 0
    return RunIntelligence(
        run_id=artifacts.metadata.run_id,
        peak_population=peak_population,
        time_to_peak_step=peak_metric.step if peak_metric else None,
        lifespan_steps=lifespan_steps,
        collapse_cause=_collapse_cause(artifacts, final, late_growth_rate),
        early_growth_rate=early_growth_rate,
        late_growth_rate=late_growth_rate,
        growth_rate_delta=late_growth_rate - early_growth_rate,
        survival_ratio=_safe_divide(final_alive, final_population) or 0,
        energy_per_alive_cell_final=_safe_divide(final_atp, final_alive),
        energy_per_population_cell_final=_safe_divide(final_atp, final_population),
        division_intensity=final_divisions / max(lifespan_steps, 1),
    )


def _growth_windows(metrics: list[PopulationMetrics]) -> tuple[list[PopulationMetrics], list[PopulationMetrics]]:
    if not metrics:
        return [], []
    window_size = min(len(metrics), max(2, math.ceil(len(metrics) * 0.2)))
    return metrics[:window_size], metrics[-window_size:]


def _growth_rate(window: list[PopulationMetrics]) -> float:
    if len(window) < 2:
        return 0.0
    step_delta = max(window[-1].step - window[0].step, 1)
    return (window[-1].population_count - window[0].population_count) / step_delta


def _collapse_cause(
    artifacts: RunArtifacts,
    final: PopulationMetrics | None,
    late_growth_rate: float,
) -> str:
    if artifacts.termination_reason == TerminationReason.ALL_CELLS_DEAD:
        return "population_extinction"
    if final is None:
        return artifacts.termination_reason.value
    if final.alive_count == 0:
        return "population_extinction"
    if final.total_atp <= 0.1 and final.alive_count > 0:
        return "energy_depletion"
    if final.toxicity >= 1.0:
        return "toxicity"
    if late_growth_rate < 0 and final.dead_count > final.alive_count:
        return "late_population_decline"
    if artifacts.termination_reason == TerminationReason.MAX_STEPS_REACHED:
        return "max_steps_reached"
    return artifacts.termination_reason.value


def _safe_divide(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator

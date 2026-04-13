from __future__ import annotations

import json
from typing import Any

from preon_systems_cell.analytics.features import extract_cell_features, extract_run_features
from preon_systems_cell.analytics.intelligence import summarize_run_intelligence
from preon_systems_cell.models import CellState, Event, RunArtifacts


BI_SCHEMA_VERSION = "cell-bi-v1"


def build_bi_tables(artifacts: RunArtifacts) -> dict[str, list[dict[str, Any]]]:
    run_id = artifacts.metadata.run_id
    scenario_name = artifacts.metadata.scenario_name
    final_metric = artifacts.metrics[-1] if artifacts.metrics else None
    return {
        "runs": [
            {
                "run_id": run_id,
                "schema_version": BI_SCHEMA_VERSION,
                "scenario_name": scenario_name,
                "engine_version": artifacts.metadata.engine_version,
                "seed": artifacts.metadata.seed,
                "dt": artifacts.metadata.dt,
                "max_steps": artifacts.metadata.max_steps,
                "steps_completed": artifacts.final_state.step,
                "termination_reason": artifacts.termination_reason.value,
                "final_population_count": final_metric.population_count if final_metric else 0,
                "final_alive_count": final_metric.alive_count if final_metric else 0,
                "final_dead_count": final_metric.dead_count if final_metric else 0,
                "final_divided_count": final_metric.divided_count if final_metric else 0,
                "final_total_atp": final_metric.total_atp if final_metric else 0.0,
                "final_total_biomass": final_metric.total_biomass if final_metric else 0.0,
            }
        ],
        "step_metrics": [_with_run_context(run_id, scenario_name, metric.model_dump(mode="json")) for metric in artifacts.metrics],
        "cells": [_cell_row(run_id, scenario_name, cell) for cell in artifacts.final_state.cells],
        "cell_events": [_event_row(run_id, scenario_name, event) for event in artifacts.events],
        "run_features": [_with_run_context(run_id, scenario_name, extract_run_features(artifacts))],
        "cell_features": [
            _with_run_context(run_id, scenario_name, row) for row in extract_cell_features(artifacts)
        ],
        "run_intelligence": [
            _with_run_context(
                run_id,
                scenario_name,
                summarize_run_intelligence(artifacts).model_dump(mode="json"),
            )
        ],
    }


def _with_run_context(run_id: str, scenario_name: str, row: dict[str, Any]) -> dict[str, Any]:
    return {"run_id": run_id, "scenario_name": scenario_name, **row}


def _cell_row(run_id: str, scenario_name: str, cell: CellState) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "scenario_name": scenario_name,
        "cell_id": cell.id,
        "parent_id": cell.parent_id,
        "generation": cell.generation,
        "birth_step": cell.birth_step,
        "death_step": cell.death_step,
        "status": cell.status.value,
        "name": cell.name,
        "alive": cell.alive,
        "division_count": cell.division_count,
        "atp": cell.energy.atp,
        "adp": cell.energy.adp,
        "glucose": cell.cytosol.glucose,
        "pyruvate": cell.cytosol.pyruvate,
        "nadh": cell.cytosol.nadh,
        "acetyl_coa": cell.cytosol.acetyl_coa,
        "nad_plus": cell.cytosol.nad_plus,
        "fad": cell.cytosol.fad,
        "fadh2": cell.cytosol.fadh2,
        "co2": cell.cytosol.co2,
        "membrane_gradient": cell.cytosol.membrane_gradient,
        "waste": cell.waste,
        "membrane_integrity": cell.membrane_integrity,
        "glucose_transporter_density": cell.glucose_transporter_density,
        "biomass": cell.biomass,
        "x": cell.x,
        "y": cell.y,
        "z": cell.z,
    }


def _event_row(run_id: str, scenario_name: str, event: Event) -> dict[str, Any]:
    daughter_ids = event.values.get("daughter_ids")
    return {
        "run_id": run_id,
        "scenario_name": scenario_name,
        "step": event.step,
        "time": event.time,
        "type": event.type.value,
        "message": event.message,
        "cell_id": event.values.get("cell_id"),
        "parent_id": event.values.get("parent_id"),
        "daughter_ids_json": json.dumps(daughter_ids if isinstance(daughter_ids, list) else []),
        "values_json": json.dumps(event.values, sort_keys=True),
    }

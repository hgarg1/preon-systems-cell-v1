from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from preon_systems_cell.models import Scenario, ValidationReport


def load_scenario(path: str | Path) -> Scenario:
    scenario_path = Path(path)
    with scenario_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return Scenario.model_validate(raw)


def validate_scenario_file(path: str | Path) -> ValidationReport:
    try:
        load_scenario(path)
    except (OSError, yaml.YAMLError, ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            return ValidationReport(valid=False, errors=[err["msg"] for err in exc.errors()])
        return ValidationReport(valid=False, errors=[str(exc)])
    return ValidationReport(valid=True)


def validate_scenario(scenario: Scenario) -> ValidationReport:
    try:
        Scenario.model_validate(scenario.model_dump())
    except ValidationError as exc:
        return ValidationReport(valid=False, errors=[err["msg"] for err in exc.errors()])
    return ValidationReport(valid=True)

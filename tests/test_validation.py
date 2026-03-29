import pytest
import yaml
from pydantic import ValidationError

from preon_systems_cell.models import Scenario, TerminationReason


def test_invalid_scenario_rejected():
    payload = yaml.safe_load(
        """
version: 1
scenario_name: bad
environment:
  nutrient_concentration: 10
  replenishment_rate: 0
  toxicity_rate: 0.01
transport:
  uptake_rate: 1
  atp_cost_per_unit: 2
metabolism:
  atp_yield_per_nutrient: 2
  waste_per_nutrient: 0.2
  reserve_conversion_cap: 1
maintenance:
  basal_atp_cost: 1
  membrane_decay: 0.1
  repair_rate: 0.5
  repair_atp_cost: 0
  growth_atp_cost: 0
  biomass_gain_per_growth: 0
cell:
  name: bad
  initial_atp: 1
  initial_adp: 0
  nutrient_reserve: 0
  waste: 0
  membrane_integrity: 1
  biomass: 1
  maintenance_threshold_atp: 1
  division_biomass_threshold: 2
simulation:
  dt: 1
  max_steps: 2
  record_every: 1
"""
    )
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


def test_termination_reason_enum_is_stable():
    assert TerminationReason.ATP_DEPLETION.value == "atp_depletion"

from random import Random

import pytest

from preon_systems_cell.engine import step_simulation
from preon_systems_cell.models import Scenario, build_initial_state


def make_scenario(**overrides) -> Scenario:
    payload = {
        "version": 2,
        "scenario_name": "engine_test",
        "environment": {
            "glucose_concentration": 10.0,
            "basal_glucose_level": 10.0,
            "glucose_replenishment_rate": 1.0,
            "toxicity_rate": 0.0,
        },
        "transport": {
            "passive_diffusion_rate": 2.0,
        },
        "metabolism": {
            "glucose_processing_cap_per_step": 5.0,
        },
        "maintenance": {
            "basal_atp_cost": 0.0,
            "membrane_decay": 0.0,
            "repair_rate": 0.0,
            "repair_atp_cost": 0.0,
            "growth_atp_cost": 0.0,
            "biomass_gain_per_growth": 0.0,
        },
        "movement": {
            "enabled": False,
            "drift_strength": 0.0,
            "vertical_drift": 0.0,
            "atp_influence": 0.0,
        },
        "cell": {
            "name": "TestCell",
            "initial_atp": 4.0,
            "initial_adp": 4.0,
            "cytosol": {
                "glucose": 0.0,
                "pyruvate": 0.0,
                "nadh": 0.0,
            },
            "waste": 0.0,
            "membrane_integrity": 1.0,
            "glucose_transporter_density": 1.0,
            "biomass": 1.0,
            "maintenance_threshold_atp": 1.0,
            "division_biomass_threshold": 2.0,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        },
        "simulation": {
            "dt": 1.0,
            "max_steps": 4,
            "record_every": 1,
        },
    }

    for key, value in overrides.items():
        payload[key] = value
    return Scenario.model_validate(payload)


def test_passive_transport_imports_without_atp_cost():
    scenario = make_scenario()
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))

    assert transition.state.cell.energy.atp == state.cell.energy.atp + 4.0
    assert transition.state.cell.cytosol.glucose == 0.0
    assert transition.state.environment.glucose_concentration == 8.0


def test_passive_transport_stops_when_gradient_is_zero_or_negative():
    scenario = make_scenario(
        cell={
            "name": "TestCell",
            "initial_atp": 4.0,
            "initial_adp": 4.0,
            "cytosol": {"glucose": 12.0, "pyruvate": 0.0, "nadh": 0.0},
            "waste": 0.0,
            "membrane_integrity": 1.0,
            "glucose_transporter_density": 1.0,
            "biomass": 1.0,
            "maintenance_threshold_atp": 1.0,
            "division_biomass_threshold": 2.0,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        }
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))

    assert transition.state.environment.glucose_concentration == 10.0
    assert transition.state.cell.cytosol.glucose == 7.0
    assert transition.state.cell.energy.atp == 14.0


def test_environment_replenishes_toward_basal_without_overshoot():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 4.0,
            "basal_glucose_level": 5.0,
            "glucose_replenishment_rate": 3.0,
            "toxicity_rate": 0.0,
        },
        transport={"passive_diffusion_rate": 0.1},
        metabolism={"glucose_processing_cap_per_step": 0.0 + 0.5},
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))

    assert transition.state.environment.glucose_concentration < 5.0
    assert transition.state.environment.glucose_concentration >= 4.4


def test_glycolysis_obeys_exact_stoichiometry_and_cap():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
        },
        cell={
            "name": "TestCell",
            "initial_atp": 4.0,
            "initial_adp": 4.0,
            "cytosol": {"glucose": 3.0, "pyruvate": 0.0, "nadh": 0.0},
            "waste": 0.0,
            "membrane_integrity": 1.0,
            "glucose_transporter_density": 1.0,
            "biomass": 1.0,
            "maintenance_threshold_atp": 1.0,
            "division_biomass_threshold": 2.0,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        },
        metabolism={"glucose_processing_cap_per_step": 1.5},
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))

    assert transition.state.cell.cytosol.glucose == 1.5
    assert transition.state.cell.cytosol.pyruvate == 3.0
    assert transition.state.cell.cytosol.nadh == 3.0
    assert transition.state.cell.energy.atp == 7.0
    assert transition.state.cell.energy.adp == 1.0
    assert transition.state.cell.waste == 0.0


def test_starvation_uses_glucose_pools():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
        },
        cell={
            "name": "TestCell",
            "initial_atp": 0.5,
            "initial_adp": 1.0,
            "cytosol": {"glucose": 0.0, "pyruvate": 0.0, "nadh": 0.0},
            "waste": 0.0,
            "membrane_integrity": 1.0,
            "glucose_transporter_density": 1.0,
            "biomass": 1.0,
            "maintenance_threshold_atp": 1.0,
            "division_biomass_threshold": 2.0,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        },
        maintenance={
            "basal_atp_cost": 0.0,
            "membrane_decay": 0.0,
            "repair_rate": 0.0,
            "repair_atp_cost": 0.0,
            "growth_atp_cost": 0.0,
            "biomass_gain_per_growth": 0.0,
        },
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))

    assert transition.terminated is True
    assert transition.termination_reason.value == "starvation"


def test_division_partitions_soluble_pools_and_preserves_structure():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
        },
        maintenance={
            "basal_atp_cost": 0.0,
            "membrane_decay": 0.0,
            "repair_rate": 0.0,
            "repair_atp_cost": 0.0,
            "growth_atp_cost": 2.0,
            "biomass_gain_per_growth": 0.8,
        },
        cell={
            "name": "TestCell",
            "initial_atp": 10.0,
            "initial_adp": 6.0,
            "cytosol": {"glucose": 4.0, "pyruvate": 8.0, "nadh": 6.0},
            "waste": 2.0,
            "membrane_integrity": 0.8,
            "glucose_transporter_density": 1.25,
            "biomass": 1.6,
            "maintenance_threshold_atp": 1.0,
            "division_biomass_threshold": 2.0,
            "x": 4.0,
            "y": -2.0,
            "z": 3.0,
        },
        metabolism={"glucose_processing_cap_per_step": 0.0 + 0.0 + 0.01},
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))
    cell = transition.state.cell

    assert cell.division_count == 1
    assert cell.biomass == pytest.approx(1.2)
    assert cell.energy.atp == pytest.approx(4.01)
    assert cell.energy.adp == pytest.approx(3.99)
    assert cell.cytosol.glucose == pytest.approx(1.995)
    assert cell.cytosol.pyruvate == pytest.approx(4.01)
    assert cell.cytosol.nadh == pytest.approx(3.01)
    assert cell.waste == pytest.approx(1.0)
    assert cell.membrane_integrity == 0.8
    assert cell.glucose_transporter_density == 1.25
    assert cell.x == 4.0
    assert cell.y == -2.0
    assert cell.z == 3.0
    division_event = next(event for event in transition.events if event.message == "Completed a simple division event")
    assert division_event.values["post_division_glucose"] == pytest.approx(1.995)
    assert division_event.values["post_division_pyruvate"] == pytest.approx(4.01)
    assert division_event.values["post_division_nadh"] == pytest.approx(3.01)
    assert division_event.values["post_division_waste"] == pytest.approx(1.0)


def test_toxicity_remains_waste_only_even_with_high_pyruvate_and_nadh():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
        },
        maintenance={
            "basal_atp_cost": 0.0,
            "membrane_decay": 0.0,
            "repair_rate": 0.0,
            "repair_atp_cost": 0.0,
            "growth_atp_cost": 0.0,
            "biomass_gain_per_growth": 0.0,
        },
        cell={
            "name": "TestCell",
            "initial_atp": 4.0,
            "initial_adp": 4.0,
            "cytosol": {"glucose": 0.0, "pyruvate": 500.0, "nadh": 500.0},
            "waste": 0.0,
            "membrane_integrity": 1.0,
            "glucose_transporter_density": 1.0,
            "biomass": 1.0,
            "maintenance_threshold_atp": 1.0,
            "division_biomass_threshold": 2.0,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        },
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))

    assert transition.terminated is False


def test_toxicity_still_triggers_from_waste_or_environment_toxicity():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
        },
        maintenance={
            "basal_atp_cost": 0.0,
            "membrane_decay": 0.0,
            "repair_rate": 0.0,
            "repair_atp_cost": 0.0,
            "growth_atp_cost": 0.0,
            "biomass_gain_per_growth": 0.0,
        },
        cell={
            "name": "TestCell",
            "initial_atp": 4.0,
            "initial_adp": 4.0,
            "cytosol": {"glucose": 0.0, "pyruvate": 0.0, "nadh": 0.0},
            "waste": 12.0,
            "membrane_integrity": 1.0,
            "glucose_transporter_density": 1.0,
            "biomass": 1.0,
            "maintenance_threshold_atp": 1.0,
            "division_biomass_threshold": 2.0,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        },
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))

    assert transition.terminated is True
    assert transition.termination_reason.value == "toxicity"


def test_repair_growth_and_movement_behaviors_still_operate():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
        },
        movement={
            "enabled": True,
            "drift_strength": 0.45,
            "vertical_drift": 0.18,
            "atp_influence": 0.08,
        },
        maintenance={
            "basal_atp_cost": 0.0,
            "membrane_decay": 0.0,
            "repair_rate": 0.2,
            "repair_atp_cost": 1.0,
            "growth_atp_cost": 2.0,
            "biomass_gain_per_growth": 0.25,
        },
        cell={
            "name": "TestCell",
            "initial_atp": 10.0,
            "initial_adp": 4.0,
            "cytosol": {"glucose": 0.0, "pyruvate": 0.0, "nadh": 0.0},
            "waste": 0.0,
            "membrane_integrity": 0.6,
            "glucose_transporter_density": 1.0,
            "biomass": 1.0,
            "maintenance_threshold_atp": 1.0,
            "division_biomass_threshold": 10.0,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        },
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(7))

    assert transition.state.cell.membrane_integrity > 0.6
    assert transition.state.cell.biomass > 1.0
    assert (
        transition.state.cell.x != state.cell.x
        or transition.state.cell.y != state.cell.y
        or transition.state.cell.z != state.cell.z
    )

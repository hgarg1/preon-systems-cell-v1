from random import Random

import pytest

from preon_systems_cell.engine import step_simulation
from preon_systems_cell.models import CellStatus, Scenario, build_initial_state


def make_scenario(**overrides) -> Scenario:
    def merge(base, update):
        for key, value in update.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                merge(base[key], value)
            else:
                base[key] = value
        return base

    payload = {
        "version": 3,
        "scenario_name": "engine_test",
        "environment": {
            "glucose_concentration": 10.0,
            "basal_glucose_level": 10.0,
            "glucose_replenishment_rate": 1.0,
            "toxicity_rate": 0.0,
            "electron_acceptor_concentration": 10.0,
            "basal_electron_acceptor_level": 10.0,
            "electron_acceptor_replenishment_rate": 0.0,
        },
        "transport": {"passive_diffusion_rate": 2.0},
        "metabolism": {
            "glucose_processing_cap_per_step": 5.0,
            "pyruvate_oxidation_cap_per_step": 0.0,
            "tca_cycle_cap_per_step": 0.0,
            "electron_transport_cap_per_step": 0.0,
            "oxidative_phosphorylation_cap_per_step": 0.0,
            "gradient_per_nadh": 2.5,
            "gradient_per_fadh2": 1.5,
            "atp_per_gradient": 1.0,
            "membrane_gradient_decay": 0.0,
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
            "initial_cell_id": "cell-1",
            "max_population": 128,
            "initial_atp": 4.0,
            "initial_adp": 4.0,
            "cytosol": {
                "glucose": 0.0,
                "pyruvate": 0.0,
                "nadh": 0.0,
                "acetyl_coa": 0.0,
                "nad_plus": 10.0,
                "fad": 4.0,
                "fadh2": 0.0,
                "co2": 0.0,
                "membrane_gradient": 0.0,
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
        "simulation": {"dt": 1.0, "max_steps": 4, "record_every": 1},
    }

    merge(payload, overrides)
    return Scenario.model_validate(payload)


def living_cells(state):
    return [cell for cell in state.cells if cell.status == CellStatus.ALIVE]


def test_initial_state_contains_one_founder_cell():
    scenario = make_scenario()

    state = build_initial_state(scenario)

    assert len(state.cells) == 1
    assert state.cells[0].id == "cell-1"
    assert state.cells[0].parent_id is None
    assert state.cells[0].generation == 0


def test_passive_transport_imports_without_atp_cost():
    scenario = make_scenario()
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))
    cell = transition.state.cells[0]

    assert cell.energy.atp == state.cells[0].energy.atp + 4.0
    assert cell.cytosol.glucose == 0.0
    assert transition.state.environment.glucose_concentration == 8.0
    assert transition.metrics.alive_count == 1


def test_glycolysis_obeys_exact_stoichiometry_and_cap():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
        },
        cell={"cytosol": {"glucose": 3.0, "pyruvate": 0.0, "nadh": 0.0}},
        metabolism={"glucose_processing_cap_per_step": 1.5},
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))
    cell = transition.state.cells[0]

    assert cell.cytosol.glucose == 1.5
    assert cell.cytosol.pyruvate == 3.0
    assert cell.cytosol.nadh == 3.0
    assert cell.energy.atp == 7.0
    assert cell.energy.adp == 1.0


def test_coarse_respiration_processes_pyruvate_through_tca_and_electron_transport():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
            "electron_acceptor_concentration": 10.0,
            "basal_electron_acceptor_level": 10.0,
            "electron_acceptor_replenishment_rate": 0.0,
        },
        cell={
            "initial_adp": 2.0,
            "cytosol": {
                "glucose": 0.0,
                "pyruvate": 2.0,
                "nadh": 0.0,
                "acetyl_coa": 0.0,
                "nad_plus": 10.0,
                "fad": 4.0,
                "fadh2": 0.0,
                "co2": 0.0,
                "membrane_gradient": 0.0,
            },
        },
        metabolism={
            "glucose_processing_cap_per_step": 0.01,
            "pyruvate_oxidation_cap_per_step": 2.0,
            "tca_cycle_cap_per_step": 1.0,
            "electron_transport_cap_per_step": 2.0,
            "oxidative_phosphorylation_cap_per_step": 0.0,
            "membrane_gradient_decay": 0.0,
        },
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))
    cell = transition.state.cells[0]

    assert cell.cytosol.pyruvate == pytest.approx(0.0)
    assert cell.cytosol.acetyl_coa == pytest.approx(1.0)
    assert cell.cytosol.co2 == pytest.approx(4.0)
    assert cell.cytosol.nadh == pytest.approx(3.0)
    assert cell.cytosol.nad_plus == pytest.approx(7.0)
    assert cell.cytosol.fad == pytest.approx(3.0)
    assert cell.cytosol.fadh2 == pytest.approx(1.0)
    assert cell.cytosol.membrane_gradient == pytest.approx(5.0)
    assert transition.state.environment.electron_acceptor_concentration == pytest.approx(8.0)
    assert {event.type.value for event in transition.events} >= {
        "pyruvate_oxidation",
        "tca_cycle",
        "electron_transport",
    }
    assert all("cell_id" in event.values for event in transition.events if event.type.value != "termination")


def test_oxidative_phosphorylation_converts_gradient_and_adp_to_atp():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
        },
        cell={
            "initial_adp": 2.0,
            "cytosol": {"glucose": 0.0, "membrane_gradient": 3.0},
        },
        metabolism={
            "glucose_processing_cap_per_step": 0.01,
            "oxidative_phosphorylation_cap_per_step": 5.0,
            "atp_per_gradient": 1.0,
            "membrane_gradient_decay": 0.0,
        },
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))
    cell = transition.state.cells[0]

    assert cell.cytosol.membrane_gradient == pytest.approx(1.0)
    assert cell.energy.atp == pytest.approx(6.0)
    assert cell.energy.adp == pytest.approx(0.0)
    assert any(event.type.value == "oxidative_phosphorylation" for event in transition.events)


def test_respiration_respects_missing_electron_acceptor_without_negative_pools():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
            "electron_acceptor_concentration": 0.5,
            "basal_electron_acceptor_level": 0.5,
            "electron_acceptor_replenishment_rate": 0.0,
        },
        cell={
            "cytosol": {
                "glucose": 0.0,
                "nadh": 3.0,
                "nad_plus": 7.0,
                "fad": 3.0,
                "fadh2": 2.0,
            }
        },
        metabolism={
            "electron_transport_cap_per_step": 10.0,
            "oxidative_phosphorylation_cap_per_step": 0.0,
            "membrane_gradient_decay": 0.0,
        },
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))
    cell = transition.state.cells[0]

    assert transition.state.environment.electron_acceptor_concentration == pytest.approx(0.0)
    assert cell.cytosol.nadh == pytest.approx(2.5)
    assert cell.cytosol.fadh2 == pytest.approx(2.0)
    assert cell.cytosol.nad_plus == pytest.approx(7.5)
    assert cell.cytosol.fad == pytest.approx(3.0)
    assert cell.cytosol.membrane_gradient == pytest.approx(1.25)


def test_division_replaces_parent_with_two_daughters_that_continue_next_step():
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
        movement={
            "enabled": True,
            "drift_strength": 0.45,
            "vertical_drift": 0.18,
            "atp_influence": 0.08,
        },
        cell={
            "initial_atp": 10.0,
            "initial_adp": 6.0,
            "cytosol": {"glucose": 4.0, "pyruvate": 8.0, "nadh": 6.0},
            "waste": 2.0,
            "membrane_integrity": 0.8,
            "glucose_transporter_density": 1.25,
            "biomass": 1.6,
            "division_biomass_threshold": 2.0,
            "x": 4.0,
            "y": -2.0,
            "z": 3.0,
        },
        metabolism={"glucose_processing_cap_per_step": 0.01},
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))
    parent = next(cell for cell in transition.state.cells if cell.id == "cell-1")
    daughters = living_cells(transition.state)

    assert parent.status == CellStatus.DIVIDED
    assert parent.alive is False
    assert [daughter.id for daughter in daughters] == ["cell-1.1", "cell-1.2"]
    assert all(daughter.parent_id == "cell-1" for daughter in daughters)
    assert all(daughter.generation == 1 for daughter in daughters)
    assert daughters[0].biomass == pytest.approx(1.2)
    assert daughters[0].energy.atp == pytest.approx(4.01)
    assert daughters[0].energy.adp == pytest.approx(3.99)
    assert daughters[0].cytosol.pyruvate == pytest.approx(4.01)
    assert daughters[0].cytosol.nad_plus == pytest.approx(5.0)
    assert daughters[0].membrane_integrity == 0.8
    assert daughters[0].glucose_transporter_density == 1.25
    assert transition.metrics.population_count == 3
    assert transition.metrics.alive_count == 2
    assert transition.metrics.divided_count == 1
    assert any(event.type.value == "movement" and event.values["cell_id"] == "cell-1" for event in transition.events)
    assert parent.x != state.cells[0].x or parent.y != state.cells[0].y or parent.z != state.cells[0].z
    division_event = next(event for event in transition.events if event.type.value == "division")
    assert division_event.values["daughter_ids"] == ["cell-1.1", "cell-1.2"]

    follow_up = step_simulation(transition.state, scenario, Random(1))

    assert any(cell.parent_id == "cell-1.1" for cell in follow_up.state.cells)
    assert any(cell.parent_id == "cell-1.2" for cell in follow_up.state.cells)
    assert follow_up.metrics.alive_count == 4


def test_population_cap_prevents_division_without_killing_cell():
    scenario = make_scenario(
        maintenance={
            "basal_atp_cost": 0.0,
            "membrane_decay": 0.0,
            "repair_rate": 0.0,
            "repair_atp_cost": 0.0,
            "growth_atp_cost": 2.0,
            "biomass_gain_per_growth": 0.8,
        },
        cell={"max_population": 1, "initial_atp": 10.0, "initial_adp": 6.0, "biomass": 1.6},
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))

    assert len(transition.state.cells) == 1
    assert transition.state.cells[0].status == CellStatus.ALIVE
    assert any(event.type.value == "population_cap" for event in transition.events)


def test_dead_cells_remain_in_state_but_stop_consuming_resources():
    scenario = make_scenario(
        environment={
            "glucose_concentration": 0.0,
            "basal_glucose_level": 0.0,
            "glucose_replenishment_rate": 0.0,
            "toxicity_rate": 0.0,
        },
        cell={"initial_atp": 0.5, "initial_adp": 1.0, "cytosol": {"glucose": 0.0}},
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))
    cell = transition.state.cells[0]

    assert transition.terminated is True
    assert transition.termination_reason.value == "all_cells_dead"
    assert cell.status == CellStatus.DEAD
    assert cell.death_step == 1
    assert any(event.type.value == "death" and event.values["reason"] == "starvation" for event in transition.events)


def test_global_toxicity_kills_living_population():
    scenario = make_scenario(
        maintenance={
            "basal_atp_cost": 0.0,
            "membrane_decay": 0.0,
            "repair_rate": 0.0,
            "repair_atp_cost": 0.0,
            "growth_atp_cost": 0.0,
            "biomass_gain_per_growth": 0.0,
        },
        cell={"waste": 12.0},
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(1))

    assert transition.terminated is True
    assert transition.termination_reason.value == "toxicity"
    assert transition.state.cells[0].status == CellStatus.DEAD


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
            "initial_atp": 10.0,
            "initial_adp": 4.0,
            "cytosol": {"glucose": 0.0},
            "membrane_integrity": 0.6,
            "division_biomass_threshold": 10.0,
        },
    )
    state = build_initial_state(scenario)

    transition = step_simulation(state, scenario, Random(7))
    cell = transition.state.cells[0]

    assert cell.membrane_integrity > 0.6
    assert cell.biomass > 1.0
    assert cell.x != state.cells[0].x or cell.y != state.cells[0].y or cell.z != state.cells[0].z

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TerminationReason(StrEnum):
    ATP_DEPLETION = "atp_depletion"
    STARVATION = "starvation"
    MEMBRANE_FAILURE = "membrane_failure"
    TOXICITY = "toxicity"
    MAX_STEPS_REACHED = "max_steps_reached"


class EventType(StrEnum):
    TRANSPORT = "transport"
    METABOLISM = "metabolism"
    MAINTENANCE = "maintenance"
    REPAIR = "repair"
    GROWTH = "growth"
    MOVEMENT = "movement"
    DAMAGE = "damage"
    TERMINATION = "termination"
    INVARIANT = "invariant"


class BaseConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnvironmentConfig(BaseConfigModel):
    nutrient_concentration: float = Field(gt=0)
    replenishment_rate: float = Field(ge=0)
    toxicity_rate: float = Field(ge=0, default=0.01)


class TransportConfig(BaseConfigModel):
    uptake_rate: float = Field(gt=0)
    atp_cost_per_unit: float = Field(ge=0)


class MetabolismConfig(BaseConfigModel):
    atp_yield_per_nutrient: float = Field(gt=0)
    waste_per_nutrient: float = Field(ge=0)
    reserve_conversion_cap: float = Field(gt=0, default=5.0)


class MaintenanceConfig(BaseConfigModel):
    basal_atp_cost: float = Field(gt=0)
    membrane_decay: float = Field(ge=0)
    repair_rate: float = Field(ge=0)
    repair_atp_cost: float = Field(ge=0)
    growth_atp_cost: float = Field(ge=0)
    biomass_gain_per_growth: float = Field(ge=0)


class MovementConfig(BaseConfigModel):
    enabled: bool = True
    drift_strength: float = Field(ge=0, default=0.45)
    vertical_drift: float = Field(ge=0, default=0.18)
    atp_influence: float = Field(ge=0, default=0.08)


class CellConfig(BaseConfigModel):
    name: str = Field(min_length=1)
    initial_atp: float = Field(gt=0)
    initial_adp: float = Field(ge=0)
    nutrient_reserve: float = Field(ge=0)
    waste: float = Field(ge=0)
    membrane_integrity: float = Field(ge=0, le=1)
    biomass: float = Field(gt=0)
    maintenance_threshold_atp: float = Field(gt=0)
    division_biomass_threshold: float = Field(gt=0)
    x: float = 0
    y: float = 0
    z: float = 0


class SimulationConfig(BaseConfigModel):
    dt: float = Field(gt=0, default=1.0)
    max_steps: int = Field(gt=0, default=100)
    record_every: int = Field(gt=0, default=1)


class Scenario(BaseConfigModel):
    version: int = Field(default=1)
    scenario_name: str = Field(min_length=1)
    environment: EnvironmentConfig
    transport: TransportConfig
    metabolism: MetabolismConfig
    maintenance: MaintenanceConfig
    movement: MovementConfig = Field(default_factory=MovementConfig)
    cell: CellConfig
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)

    @model_validator(mode="after")
    def validate_cross_field_rules(self) -> "Scenario":
        if self.maintenance.repair_rate > 0 and self.maintenance.repair_atp_cost == 0:
            raise ValueError("repair_atp_cost must be positive when repair_rate is enabled")
        if self.maintenance.biomass_gain_per_growth > 0 and self.maintenance.growth_atp_cost == 0:
            raise ValueError("growth_atp_cost must be positive when growth is enabled")
        if self.cell.initial_atp <= self.transport.atp_cost_per_unit:
            raise ValueError("initial_atp must exceed the per-unit transport ATP cost")
        return self


class ValidationReport(BaseConfigModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class EnergyState(BaseConfigModel):
    atp: float = Field(ge=0)
    adp: float = Field(ge=0)


class CellState(BaseConfigModel):
    name: str
    energy: EnergyState
    nutrient_reserve: float = Field(ge=0)
    waste: float = Field(ge=0)
    membrane_integrity: float = Field(ge=0, le=1)
    biomass: float = Field(ge=0)
    x: float = 0
    y: float = 0
    z: float = 0
    alive: bool = True
    division_count: int = 0


class EnvironmentState(BaseConfigModel):
    nutrient_concentration: float = Field(ge=0)
    toxicity: float = Field(ge=0)


class WorldState(BaseConfigModel):
    step: int = 0
    time: float = 0
    cell: CellState
    environment: EnvironmentState


class Event(BaseConfigModel):
    step: int
    time: float
    type: EventType
    message: str
    values: dict[str, Any] = Field(default_factory=dict)


class StepMetrics(BaseConfigModel):
    step: int
    time: float
    atp: float
    adp: float
    nutrient_reserve: float
    environment_nutrients: float
    waste: float
    toxicity: float
    membrane_integrity: float
    biomass: float
    x: float
    y: float
    z: float


class StepTransition(BaseConfigModel):
    state: WorldState
    metrics: StepMetrics
    events: list[Event]
    terminated: bool = False
    termination_reason: TerminationReason | None = None


class RunMetadata(BaseConfigModel):
    scenario_name: str
    engine_version: str
    seed: int
    dt: float
    max_steps: int


class RunSummary(BaseConfigModel):
    metadata: RunMetadata
    final_state: WorldState
    final_metrics: StepMetrics
    termination_reason: TerminationReason
    steps_completed: int
    event_count: int


class RunArtifacts(BaseConfigModel):
    resolved_scenario: Scenario
    metadata: RunMetadata
    metrics: list[StepMetrics]
    events: list[Event]
    final_state: WorldState
    termination_reason: TerminationReason


class CellCreateParams(BaseConfigModel):
    name: str | None = None
    initial_atp: float | None = Field(default=None, gt=0)
    initial_adp: float | None = Field(default=None, ge=0)
    nutrient_reserve: float | None = Field(default=None, ge=0)
    waste: float | None = Field(default=None, ge=0)
    membrane_integrity: float | None = Field(default=None, ge=0, le=1)
    biomass: float | None = Field(default=None, gt=0)
    maintenance_threshold_atp: float | None = Field(default=None, gt=0)
    division_biomass_threshold: float | None = Field(default=None, gt=0)
    x: float | None = None
    y: float | None = None
    z: float | None = None


class CellCreateResponse(BaseConfigModel):
    scenario: Scenario
    state: WorldState


def build_initial_state(scenario: Scenario) -> WorldState:
    return WorldState(
        cell=CellState(
            name=scenario.cell.name,
            energy=EnergyState(atp=scenario.cell.initial_atp, adp=scenario.cell.initial_adp),
            nutrient_reserve=scenario.cell.nutrient_reserve,
            waste=scenario.cell.waste,
            membrane_integrity=scenario.cell.membrane_integrity,
            biomass=scenario.cell.biomass,
            x=scenario.cell.x,
            y=scenario.cell.y,
            z=scenario.cell.z,
        ),
        environment=EnvironmentState(
            nutrient_concentration=scenario.environment.nutrient_concentration,
            toxicity=0,
        ),
    )

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
    GLYCOLYSIS = "glycolysis"
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
    glucose_concentration: float = Field(ge=0)
    basal_glucose_level: float = Field(ge=0)
    glucose_replenishment_rate: float = Field(ge=0)
    toxicity_rate: float = Field(ge=0, default=0.01)


class TransportConfig(BaseConfigModel):
    passive_diffusion_rate: float = Field(gt=0)


class MetabolismConfig(BaseConfigModel):
    glucose_processing_cap_per_step: float = Field(gt=0, default=5.0)


class MaintenanceConfig(BaseConfigModel):
    basal_atp_cost: float = Field(ge=0)
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


class CytosolConfig(BaseConfigModel):
    glucose: float = Field(ge=0)
    pyruvate: float = Field(ge=0, default=0)
    nadh: float = Field(ge=0, default=0)


class CellConfig(BaseConfigModel):
    name: str = Field(min_length=1)
    initial_atp: float = Field(gt=0)
    initial_adp: float = Field(ge=0)
    cytosol: CytosolConfig
    waste: float = Field(ge=0)
    membrane_integrity: float = Field(ge=0, le=1)
    glucose_transporter_density: float = Field(ge=0)
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
    version: int = Field(default=2)
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
        if self.version != 2:
            raise ValueError("scenario version must be 2")
        if self.maintenance.repair_rate > 0 and self.maintenance.repair_atp_cost == 0:
            raise ValueError("repair_atp_cost must be positive when repair_rate is enabled")
        if self.maintenance.biomass_gain_per_growth > 0 and self.maintenance.growth_atp_cost == 0:
            raise ValueError("growth_atp_cost must be positive when growth is enabled")
        if self.environment.glucose_concentration < self.environment.basal_glucose_level:
            max_reachable = self.environment.glucose_concentration + (
                self.environment.glucose_replenishment_rate * self.simulation.dt
            )
            if max_reachable <= self.environment.glucose_concentration:
                raise ValueError(
                    "glucose_replenishment_rate must be positive when glucose_concentration starts below basal_glucose_level"
                )
        return self


class ValidationReport(BaseConfigModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class EnergyState(BaseConfigModel):
    atp: float = Field(ge=0)
    adp: float = Field(ge=0)


class CytosolState(BaseConfigModel):
    glucose: float = Field(ge=0)
    pyruvate: float = Field(ge=0)
    nadh: float = Field(ge=0)


class CellState(BaseConfigModel):
    name: str
    energy: EnergyState
    cytosol: CytosolState
    waste: float = Field(ge=0)
    membrane_integrity: float = Field(ge=0, le=1)
    glucose_transporter_density: float = Field(ge=0)
    biomass: float = Field(ge=0)
    x: float = 0
    y: float = 0
    z: float = 0
    alive: bool = True
    division_count: int = 0


class EnvironmentState(BaseConfigModel):
    glucose_concentration: float = Field(ge=0)
    basal_glucose_level: float = Field(ge=0)
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
    cytosolic_glucose: float
    pyruvate: float
    nadh: float
    environment_glucose: float
    waste: float
    toxicity: float
    membrane_integrity: float
    glucose_transporter_density: float
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


class CytosolCreateParams(BaseConfigModel):
    glucose: float | None = Field(default=None, ge=0)
    pyruvate: float | None = Field(default=None, ge=0)
    nadh: float | None = Field(default=None, ge=0)


class CellCreateParams(BaseConfigModel):
    name: str | None = None
    initial_atp: float | None = Field(default=None, gt=0)
    initial_adp: float | None = Field(default=None, ge=0)
    cytosol: CytosolCreateParams | None = None
    waste: float | None = Field(default=None, ge=0)
    membrane_integrity: float | None = Field(default=None, ge=0, le=1)
    glucose_transporter_density: float | None = Field(default=None, ge=0)
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
            cytosol=CytosolState(
                glucose=scenario.cell.cytosol.glucose,
                pyruvate=scenario.cell.cytosol.pyruvate,
                nadh=scenario.cell.cytosol.nadh,
            ),
            waste=scenario.cell.waste,
            membrane_integrity=scenario.cell.membrane_integrity,
            glucose_transporter_density=scenario.cell.glucose_transporter_density,
            biomass=scenario.cell.biomass,
            x=scenario.cell.x,
            y=scenario.cell.y,
            z=scenario.cell.z,
        ),
        environment=EnvironmentState(
            glucose_concentration=scenario.environment.glucose_concentration,
            basal_glucose_level=scenario.environment.basal_glucose_level,
            toxicity=0,
        ),
    )

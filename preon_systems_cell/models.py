from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TerminationReason(StrEnum):
    ALL_CELLS_DEAD = "all_cells_dead"
    ATP_DEPLETION = "atp_depletion"
    STARVATION = "starvation"
    MEMBRANE_FAILURE = "membrane_failure"
    TOXICITY = "toxicity"
    MAX_STEPS_REACHED = "max_steps_reached"


class EventType(StrEnum):
    TRANSPORT = "transport"
    GLYCOLYSIS = "glycolysis"
    PYRUVATE_OXIDATION = "pyruvate_oxidation"
    TCA_CYCLE = "tca_cycle"
    ELECTRON_TRANSPORT = "electron_transport"
    OXIDATIVE_PHOSPHORYLATION = "oxidative_phosphorylation"
    MAINTENANCE = "maintenance"
    REPAIR = "repair"
    GROWTH = "growth"
    DIVISION = "division"
    POPULATION_CAP = "population_cap"
    MOVEMENT = "movement"
    DAMAGE = "damage"
    DEATH = "death"
    TERMINATION = "termination"
    INVARIANT = "invariant"


class CellStatus(StrEnum):
    ALIVE = "alive"
    DIVIDED = "divided"
    DEAD = "dead"


class BaseConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnvironmentConfig(BaseConfigModel):
    glucose_concentration: float = Field(ge=0)
    basal_glucose_level: float = Field(ge=0)
    glucose_replenishment_rate: float = Field(ge=0)
    toxicity_rate: float = Field(ge=0, default=0.01)
    electron_acceptor_concentration: float = Field(ge=0, default=24.0)
    basal_electron_acceptor_level: float = Field(ge=0, default=24.0)
    electron_acceptor_replenishment_rate: float = Field(ge=0, default=0.9)


class TransportConfig(BaseConfigModel):
    passive_diffusion_rate: float = Field(gt=0)


class MetabolismConfig(BaseConfigModel):
    glucose_processing_cap_per_step: float = Field(gt=0, default=5.0)
    pyruvate_oxidation_cap_per_step: float = Field(ge=0, default=2.0)
    tca_cycle_cap_per_step: float = Field(ge=0, default=2.0)
    electron_transport_cap_per_step: float = Field(ge=0, default=4.0)
    oxidative_phosphorylation_cap_per_step: float = Field(ge=0, default=4.0)
    gradient_per_nadh: float = Field(ge=0, default=2.5)
    gradient_per_fadh2: float = Field(ge=0, default=1.5)
    atp_per_gradient: float = Field(ge=0, default=1.0)
    membrane_gradient_decay: float = Field(ge=0, default=0.05)


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
    acetyl_coa: float = Field(ge=0, default=0)
    nad_plus: float = Field(ge=0, default=10)
    fad: float = Field(ge=0, default=4)
    fadh2: float = Field(ge=0, default=0)
    co2: float = Field(ge=0, default=0)
    membrane_gradient: float = Field(ge=0, default=0)


class CellConfig(BaseConfigModel):
    name: str = Field(min_length=1)
    initial_cell_id: str = Field(default="cell-1", min_length=1)
    max_population: int = Field(default=128, ge=1)
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
    version: int = Field(default=3)
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
        if self.version != 3:
            raise ValueError("scenario version must be 3")
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
        if self.environment.electron_acceptor_concentration < self.environment.basal_electron_acceptor_level:
            max_reachable_acceptor = self.environment.electron_acceptor_concentration + (
                self.environment.electron_acceptor_replenishment_rate * self.simulation.dt
            )
            if max_reachable_acceptor <= self.environment.electron_acceptor_concentration:
                raise ValueError(
                    "electron_acceptor_replenishment_rate must be positive when electron_acceptor_concentration starts below basal_electron_acceptor_level"
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
    pyruvate: float = Field(ge=0, default=0)
    nadh: float = Field(ge=0, default=0)
    acetyl_coa: float = Field(ge=0, default=0)
    nad_plus: float = Field(ge=0, default=10)
    fad: float = Field(ge=0, default=4)
    fadh2: float = Field(ge=0, default=0)
    co2: float = Field(ge=0, default=0)
    membrane_gradient: float = Field(ge=0, default=0)


class CellState(BaseConfigModel):
    id: str = Field(min_length=1)
    parent_id: str | None = None
    generation: int = Field(ge=0, default=0)
    birth_step: int = Field(ge=0, default=0)
    death_step: int | None = Field(default=None, ge=0)
    status: CellStatus = CellStatus.ALIVE
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
    electron_acceptor_concentration: float = Field(ge=0, default=24.0)
    basal_electron_acceptor_level: float = Field(ge=0, default=24.0)
    toxicity: float = Field(ge=0)


class WorldState(BaseConfigModel):
    step: int = 0
    time: float = 0
    cells: list[CellState] = Field(min_length=1)
    environment: EnvironmentState


class Event(BaseConfigModel):
    step: int
    time: float
    type: EventType
    message: str
    values: dict[str, Any] = Field(default_factory=dict)


class PopulationMetrics(BaseConfigModel):
    step: int
    time: float
    population_count: int
    alive_count: int
    dead_count: int
    divided_count: int
    division_count_total: int
    total_atp: float
    total_biomass: float
    environment_glucose: float
    environment_electron_acceptor: float
    toxicity: float


class StepSnapshot(PopulationMetrics):
    state: WorldState


class StepTransition(BaseConfigModel):
    state: WorldState
    metrics: PopulationMetrics
    snapshot: StepSnapshot
    events: list[Event]
    terminated: bool = False
    termination_reason: TerminationReason | None = None


class RunMetadata(BaseConfigModel):
    run_id: str = "run-local"
    scenario_name: str
    engine_version: str
    seed: int
    dt: float
    max_steps: int


class RunSummary(BaseConfigModel):
    metadata: RunMetadata
    final_state: WorldState
    final_metrics: PopulationMetrics
    termination_reason: TerminationReason
    steps_completed: int
    event_count: int


class RunArtifacts(BaseConfigModel):
    resolved_scenario: Scenario
    metadata: RunMetadata
    metrics: list[PopulationMetrics]
    snapshots: list[StepSnapshot]
    events: list[Event]
    final_state: WorldState
    termination_reason: TerminationReason


class RunTimeSeriesPoint(BaseConfigModel):
    step: int
    time: float
    population: int
    alive: int
    dead: int
    divided: int
    division_count_total: int
    total_atp: float
    total_biomass: float
    atp_per_alive_cell: float | None
    atp_per_population_cell: float | None
    environment_glucose: float
    environment_electron_acceptor: float
    toxicity: float


class RunTimeSeriesResponse(BaseConfigModel):
    run_id: str
    resolution: int
    points: list[RunTimeSeriesPoint]


class RunIntelligence(BaseConfigModel):
    run_id: str
    peak_population: int
    time_to_peak_step: int | None
    lifespan_steps: int
    collapse_cause: str
    early_growth_rate: float
    late_growth_rate: float
    growth_rate_delta: float
    survival_ratio: float
    energy_per_alive_cell_final: float | None
    energy_per_population_cell_final: float | None
    division_intensity: float


class MetricDelta(BaseConfigModel):
    baseline: float | int | None
    value: float | int | None
    absolute_delta: float | int | None
    percent_delta: float | None


class ComparedRun(BaseConfigModel):
    run_id: str
    scenario_name: str
    seed: int
    status: str
    role: str
    intelligence: RunIntelligence


class ComparisonPoint(BaseConfigModel):
    step: int
    population: dict[str, int | None]
    total_atp: dict[str, float | None]
    atp_per_alive_cell: dict[str, float | None]


class RunComparisonResponse(BaseConfigModel):
    baseline_run_id: str
    runs: list[ComparedRun]
    deltas: dict[str, dict[str, MetricDelta]]
    aligned_series: list[ComparisonPoint]


class CytosolCreateParams(BaseConfigModel):
    glucose: float | None = Field(default=None, ge=0)
    pyruvate: float | None = Field(default=None, ge=0)
    nadh: float | None = Field(default=None, ge=0)
    acetyl_coa: float | None = Field(default=None, ge=0)
    nad_plus: float | None = Field(default=None, ge=0)
    fad: float | None = Field(default=None, ge=0)
    fadh2: float | None = Field(default=None, ge=0)
    co2: float | None = Field(default=None, ge=0)
    membrane_gradient: float | None = Field(default=None, ge=0)


class CellCreateParams(BaseConfigModel):
    name: str | None = None
    initial_cell_id: str | None = Field(default=None, min_length=1)
    max_population: int | None = Field(default=None, ge=1)
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
        cells=[
            CellState(
                id=scenario.cell.initial_cell_id,
                parent_id=None,
                generation=0,
                birth_step=0,
                death_step=None,
                status=CellStatus.ALIVE,
                name=scenario.cell.name,
                energy=EnergyState(atp=scenario.cell.initial_atp, adp=scenario.cell.initial_adp),
                cytosol=CytosolState(
                    glucose=scenario.cell.cytosol.glucose,
                    pyruvate=scenario.cell.cytosol.pyruvate,
                    nadh=scenario.cell.cytosol.nadh,
                    acetyl_coa=scenario.cell.cytosol.acetyl_coa,
                    nad_plus=scenario.cell.cytosol.nad_plus,
                    fad=scenario.cell.cytosol.fad,
                    fadh2=scenario.cell.cytosol.fadh2,
                    co2=scenario.cell.cytosol.co2,
                    membrane_gradient=scenario.cell.cytosol.membrane_gradient,
                ),
                waste=scenario.cell.waste,
                membrane_integrity=scenario.cell.membrane_integrity,
                glucose_transporter_density=scenario.cell.glucose_transporter_density,
                biomass=scenario.cell.biomass,
                x=scenario.cell.x,
                y=scenario.cell.y,
                z=scenario.cell.z,
            )
        ],
        environment=EnvironmentState(
            glucose_concentration=scenario.environment.glucose_concentration,
            basal_glucose_level=scenario.environment.basal_glucose_level,
            electron_acceptor_concentration=scenario.environment.electron_acceptor_concentration,
            basal_electron_acceptor_level=scenario.environment.basal_electron_acceptor_level,
            toxicity=0,
        ),
    )

from random import Random

from preon_systems_cell.models import (
    CellState,
    CellStatus,
    CytosolState,
    EnergyState,
    Event,
    EventType,
    PopulationMetrics,
)
from preon_systems_cell.storage.postgres import (
    SCHEMA_PATH,
    PostgresRunBuffer,
    decode_rng_state,
    encode_rng_state,
)


def test_postgres_schema_defines_core_tables_and_indexes():
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS runs" in schema
    assert "CREATE TABLE IF NOT EXISTS cells" in schema
    assert "CREATE TABLE IF NOT EXISTS step_metrics" in schema
    assert "CREATE TABLE IF NOT EXISTS events" in schema
    assert "idx_step_metrics_run_step" in schema
    assert "idx_events_run_cell_step" in schema


def test_postgres_buffer_batches_metrics_cells_and_events():
    cell = CellState(
        id="cell-1",
        parent_id=None,
        generation=0,
        birth_step=0,
        status=CellStatus.ALIVE,
        name="Cell",
        energy=EnergyState(atp=10, adp=1),
        cytosol=CytosolState(glucose=1),
        waste=0,
        membrane_integrity=1,
        glucose_transporter_density=1,
        biomass=2,
    )
    metric = PopulationMetrics(
        step=1,
        time=1,
        population_count=1,
        alive_count=1,
        dead_count=0,
        divided_count=0,
        division_count_total=0,
        total_atp=10,
        total_biomass=2,
        environment_glucose=20,
        environment_electron_acceptor=24,
        toxicity=0.01,
    )
    event = Event(
        step=1,
        time=1,
        type=EventType.MOVEMENT,
        message="Cell drifted",
        values={"cell_id": "cell-1", "delta_x": 0.1},
    )

    buffer = PostgresRunBuffer()
    buffer.add_metric("run-1", metric)
    buffer.extend_cells("run-1", [cell], updated_step=1)
    buffer.extend_events("run-1", [event])

    assert buffer.metrics[0][:3] == ("run-1", 1, 1)
    assert buffer.cells[0][:3] == ("run-1", "cell-1", None)
    assert buffer.events[0][:5] == ("run-1", 1, 1, "movement", "cell-1")


def test_random_state_round_trips_through_json_payload():
    rng = Random(7)
    restored = Random()
    restored.setstate(decode_rng_state(encode_rng_state(rng)))

    assert restored.random() == rng.random()

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    scenario_hash TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    seed INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    max_steps INTEGER NOT NULL CHECK (max_steps > 0),
    final_step INTEGER CHECK (final_step >= 0),
    termination_reason TEXT,
    scenario JSONB NOT NULL,
    current_state JSONB NOT NULL,
    rng_state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_runs_status_started_at ON runs (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_scenario_started_at ON runs (scenario_name, started_at DESC);

CREATE TABLE IF NOT EXISTS cells (
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    cell_id TEXT NOT NULL,
    parent_id TEXT,
    generation INTEGER NOT NULL CHECK (generation >= 0),
    birth_step INTEGER NOT NULL CHECK (birth_step >= 0),
    death_step INTEGER CHECK (death_step >= 0),
    status TEXT NOT NULL,
    alive BOOLEAN NOT NULL,
    x DOUBLE PRECISION NOT NULL,
    y DOUBLE PRECISION NOT NULL,
    z DOUBLE PRECISION NOT NULL,
    atp DOUBLE PRECISION NOT NULL,
    biomass DOUBLE PRECISION NOT NULL,
    updated_step INTEGER NOT NULL CHECK (updated_step >= 0),
    payload JSONB NOT NULL,
    PRIMARY KEY (run_id, cell_id)
);

CREATE INDEX IF NOT EXISTS idx_cells_run_parent ON cells (run_id, parent_id);
CREATE INDEX IF NOT EXISTS idx_cells_run_status ON cells (run_id, status);
CREATE INDEX IF NOT EXISTS idx_cells_run_generation ON cells (run_id, generation);
CREATE INDEX IF NOT EXISTS idx_cells_cell_id ON cells (cell_id);

CREATE TABLE IF NOT EXISTS step_metrics (
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    step INTEGER NOT NULL CHECK (step >= 0),
    time DOUBLE PRECISION NOT NULL,
    population_count INTEGER NOT NULL,
    alive_count INTEGER NOT NULL,
    dead_count INTEGER NOT NULL,
    divided_count INTEGER NOT NULL,
    division_count_total INTEGER NOT NULL,
    total_atp DOUBLE PRECISION NOT NULL,
    total_biomass DOUBLE PRECISION NOT NULL,
    environment_glucose DOUBLE PRECISION NOT NULL,
    environment_electron_acceptor DOUBLE PRECISION NOT NULL,
    toxicity DOUBLE PRECISION NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (run_id, step)
);

CREATE INDEX IF NOT EXISTS idx_step_metrics_run_step ON step_metrics (run_id, step);
CREATE INDEX IF NOT EXISTS idx_step_metrics_step ON step_metrics (step);

CREATE TABLE IF NOT EXISTS events (
    event_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    step INTEGER NOT NULL CHECK (step >= 0),
    time DOUBLE PRECISION NOT NULL,
    event_type TEXT NOT NULL,
    cell_id TEXT,
    message TEXT NOT NULL,
    values JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_run_step ON events (run_id, step, event_id);
CREATE INDEX IF NOT EXISTS idx_events_run_cell_step ON events (run_id, cell_id, step) WHERE cell_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_run_type_step ON events (run_id, event_type, step);
CREATE INDEX IF NOT EXISTS idx_events_values_gin ON events USING GIN (values);

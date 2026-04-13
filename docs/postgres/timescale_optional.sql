DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        CREATE EXTENSION IF NOT EXISTS timescaledb;
    ELSE
        RAISE NOTICE 'TimescaleDB is not available for this PostgreSQL installation. Standard PostgreSQL indexes remain active.';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'TimescaleDB could not be enabled: %. Standard PostgreSQL indexes remain active.', SQLERRM;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_proc
        WHERE proname = 'create_hypertable'
    ) THEN
        PERFORM create_hypertable(
            'step_metrics',
            'step',
            if_not_exists => TRUE,
            chunk_time_interval => 1000
        );
    ELSE
        RAISE NOTICE 'create_hypertable is unavailable. step_metrics will stay a regular indexed table.';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'step_metrics hypertable conversion skipped: %. Standard PostgreSQL indexes remain active.', SQLERRM;
END $$;

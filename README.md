# Preon Systems Cell

Preon Systems Cell is a deterministic, glucose-centric simulation engine for a
scientifically anchored, prokaryote-like cell model.

## What It Does

- Loads typed YAML scenarios.
- Validates world, cell, transport, cytosol, and glycolysis parameters.
- Runs discrete-time simulations with deterministic seeds.
- Emits structured JSON artifacts for metrics, events, and final state.
- Exposes both a Python API and a CLI.

## Quick Start

```bash
python main.py validate scenarios/default_cell.yaml
python main.py run scenarios/default_cell.yaml --seed 7 --max-steps 48 --out runs/demo
python main.py inspect runs/demo/run_summary.json
simulate-web
```

The FastAPI server exposes JSON endpoints and a small browser UI on
`http://127.0.0.1:8000/`.

## HTTP API

Run the server:

```bash
simulate-web
```

If the installed script is not on your `PATH`, you can run either of these from the repo root:

```bash
python main.py web
run-web.bat
```

Available routes:

- `GET /` serves the web UI
- `GET /health` returns server health and engine version
- `GET /api/default-scenario` returns the bundled default scenario as JSON
- `POST /api/cells` creates a new cell state from scenario defaults plus optional overrides, including `x`, `y`, and `z`
- `POST /api/validate` validates a scenario payload
- `POST /api/run` runs a simulation and returns run artifacts
- `POST /api/step` advances a single simulation step

## Model Overview

The v2 engine models a simple prokaryote-like cell with:

- environmental glucose maintained around a basal level
- passive glucose transport across the membrane into the cytosol
- glycolysis that converts glucose into pyruvate, ATP, and NADH
- ATP consumption for maintenance, repair, and growth
- membrane integrity loss and repair
- viability checks driven by explicit termination conditions

This is biology-inspired and scientifically anchored, but it is not intended to
be a literal biochemical simulator.

from __future__ import annotations

import argparse
import json
from pathlib import Path

from preon_systems_cell.api import load_scenario, run_simulation, validate_scenario
from preon_systems_cell.artifacts import read_json
from preon_systems_cell.models import ValidationReport
from preon_systems_cell.scenario import validate_scenario_file
from preon_systems_cell.web import main as run_web_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="simulate", description="Run ATP-centric cell simulations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a scenario YAML file.")
    validate_parser.add_argument("scenario", type=Path)

    run_parser = subparsers.add_parser("run", help="Run a simulation and optionally write artifacts.")
    run_parser.add_argument("scenario", type=Path)
    run_parser.add_argument("--seed", type=int, required=True)
    run_parser.add_argument("--max-steps", type=int, default=None)
    run_parser.add_argument("--dt", type=float, default=None)
    run_parser.add_argument("--out", type=Path, default=None)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a generated JSON artifact.")
    inspect_parser.add_argument("artifact", type=Path)

    web_parser = subparsers.add_parser("web", help="Run the FastAPI web server.")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        report = validate_scenario_file(args.scenario)
        return _emit_validation_report(report)

    if args.command == "run":
        scenario = load_scenario(args.scenario)
        report = validate_scenario(scenario)
        if not report.valid:
            return _emit_validation_report(report)
        artifacts = run_simulation(
            scenario=scenario,
            seed=args.seed,
            max_steps=args.max_steps,
            dt=args.dt,
            output_dir=args.out,
        )
        summary = {
            "scenario": artifacts.metadata.scenario_name,
            "seed": artifacts.metadata.seed,
            "steps_completed": artifacts.final_state.step,
            "termination_reason": artifacts.termination_reason.value,
            "final_atp": round(artifacts.final_state.cell.energy.atp, 4),
            "final_biomass": round(artifacts.final_state.cell.biomass, 4),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    if args.command == "inspect":
        print(json.dumps(read_json(args.artifact), indent=2, sort_keys=True))
        return 0

    if args.command == "web":
        run_web_server(host=args.host, port=args.port)
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


def _emit_validation_report(report: ValidationReport) -> int:
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0 if report.valid else 1

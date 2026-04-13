from __future__ import annotations

import argparse
import json
from pathlib import Path

from preon_systems_cell.api import load_scenario, run_simulation, validate_scenario
from preon_systems_cell.artifacts import read_json, read_run_artifacts
from preon_systems_cell.bi import BI_EXPORT_FORMATS, write_bi_bundle
from preon_systems_cell.models import ValidationReport
from preon_systems_cell.scenario import validate_scenario_file
from preon_systems_cell.web import main as run_web_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="simulate", description="Run glucose-centric cell simulations.")
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

    export_parser = subparsers.add_parser("export-bi", help="Write native BI exports and Parquet for a run directory.")
    export_parser.add_argument("--run-dir", type=Path, required=True)
    export_parser.add_argument("--out", type=Path, required=True)
    export_parser.add_argument(
        "--formats",
        default=",".join(BI_EXPORT_FORMATS),
        help="Comma-separated export formats: parquet,powerbi,tableau",
    )

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
        final_metrics = artifacts.metrics[-1]
        summary = {
            "run_id": artifacts.metadata.run_id,
            "scenario": artifacts.metadata.scenario_name,
            "seed": artifacts.metadata.seed,
            "steps_completed": artifacts.final_state.step,
            "termination_reason": artifacts.termination_reason.value,
            "population_count": final_metrics.population_count,
            "alive_count": final_metrics.alive_count,
            "dead_count": final_metrics.dead_count,
            "divided_count": final_metrics.divided_count,
            "total_atp": round(final_metrics.total_atp, 4),
            "total_biomass": round(final_metrics.total_biomass, 4),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    if args.command == "inspect":
        print(json.dumps(read_json(args.artifact), indent=2, sort_keys=True))
        return 0

    if args.command == "export-bi":
        try:
            artifacts = read_run_artifacts(args.run_dir)
            formats = [item.strip() for item in args.formats.split(",") if item.strip()]
            manifest = write_bi_bundle(artifacts, args.out, formats=formats)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True))
        return 0

    if args.command == "web":
        run_web_server(host=args.host, port=args.port)
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


def _emit_validation_report(report: ValidationReport) -> int:
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0 if report.valid else 1

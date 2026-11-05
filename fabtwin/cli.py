"""Command line entry point: ``python -m fabtwin``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .compare_report import (
    default_comparison_report_path,
    evidence_transition,
    format_delta,
    format_value,
    write_comparison_report,
)
from .errors import (
    FabTwinError,
    ScenarioError,
    ScenarioValidationError,
    StoreError,
)
from .model import EVIDENCE_CLASSES
from .provenance import display_path
from .run import DEFAULT_STORE, execute, validate_scenario
from .scenario import load_scenario
from .store import ObservationStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fabtwin",
        description="Reproducible foundry-twin scenario runner",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate",
        help="validate a scenario and its engine inputs",
    )
    validate_parser.add_argument("scenario", help="path to the scenario YAML")

    run_parser = subparsers.add_parser(
        "run",
        help="execute a scenario and write run artifacts",
    )
    run_parser.add_argument("scenario", help="path to the scenario YAML")
    run_parser.add_argument(
        "--out",
        default=None,
        help="output root (default: out/fabtwin)",
    )

    query_parser = subparsers.add_parser(
        "query",
        help="query the SQLite observation index",
    )
    query_parser.add_argument(
        "--db",
        default=None,
        help="SQLite index (default: out/fabtwin/fabtwin.db)",
    )
    query_parser.add_argument(
        "--runs",
        action="store_true",
        help="list runs instead of observations",
    )
    query_parser.add_argument("--run", dest="run_id", help="filter by run ID")
    query_parser.add_argument("--metric", help="filter by metric")
    query_parser.add_argument(
        "--entity",
        dest="entity_id",
        help="filter by entity ID",
    )
    query_parser.add_argument(
        "--evidence",
        choices=sorted(EVIDENCE_CLASSES),
        help="filter by evidence class",
    )
    query_parser.add_argument("--product", help="filter by product")
    query_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="maximum rows, 1-1000 (default: 50)",
    )
    query_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit JSON instead of a table",
    )

    compare_parser = subparsers.add_parser(
        "compare",
        help="diff two indexed runs by entity and metric",
    )
    compare_parser.add_argument("run_a", help="first run ID")
    compare_parser.add_argument("run_b", help="second run ID")
    compare_parser.add_argument(
        "--db",
        default=None,
        help="SQLite index (default: out/fabtwin/fabtwin.db)",
    )
    compare_parser.add_argument("--metric", help="filter by metric")
    compare_parser.add_argument(
        "--only-changes",
        action="store_true",
        help="show only rows with a value, unit, model, or evidence change",
    )
    compare_parser.add_argument(
        "--report",
        default=None,
        help="comparison report path (default: beside the store)",
    )
    compare_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit JSON instead of a table",
    )
    return parser


def _resolve_store(value: str | None) -> Path:
    path = Path(value) if value else DEFAULT_STORE
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _print_runs(rows: list[dict]) -> None:
    if not rows:
        print("no runs")
        return
    print("run_id\tscenario\tproduct\tobservations\tstatus\tstarted_at")
    for row in rows:
        print(
            f"{row['run_id']}\t{row['scenario_id']}\t{row['product']}\t"
            f"{row['observation_count']}\t{row['status']}\t"
            f"{row['started_at']}"
        )


def _print_observations(rows: list[dict]) -> None:
    if not rows:
        print("no observations")
        return
    print("run_id\tentity_id\tmetric\tvalue\tunit\tevidence")
    for row in rows:
        print(
            f"{row['run_id']}\t{row['entity_id']}\t{row['metric']}\t"
            f"{float(row['value']):.8g}\t{row['unit']}\t"
            f"{row['evidence_class']}"
        )


def _query(args: argparse.Namespace) -> int:
    path = _resolve_store(args.db)
    if not path.is_file():
        print(
            f"error: SQLite store not found: {display_path(path)}",
            file=sys.stderr,
        )
        return 1
    store = ObservationStore(path)
    try:
        if args.runs:
            rows = store.list_runs(limit=args.limit)
        else:
            rows = store.query_observations(
                run_id=args.run_id,
                metric=args.metric,
                entity_id=args.entity_id,
                evidence_class=args.evidence,
                product=args.product,
                limit=args.limit,
            )
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(rows, indent=2))
    elif args.runs:
        _print_runs(rows)
    else:
        _print_observations(rows)
    return 0


def _print_comparison(diff: dict) -> None:
    summary = diff["summary"]
    filter_info = diff.get("filter", {})
    print(f"A: {diff['run_a']['run_id']}")
    print(f"B: {diff['run_b']['run_id']}")
    print(
        f"rows: {summary['rows']}  shown: {filter_info.get('shown_rows', summary['rows'])}  "
        f"changed: {summary['changed']}  "
        f"evidence: {summary['evidence_changes']}  "
        f"added: {summary['added']}  removed: {summary['removed']}"
    )
    print("entity_id\tmetric\tA\tB\tdelta\tevidence\tflags")
    for row in diff["rows"]:
        flags = ",".join(row["flags"]) if row["flags"] else "unchanged"
        print(
            f"{row['entity_id']}\t{row['metric']}\t"
            f"{format_value(row['value_a'], row['unit_a'])}\t"
            f"{format_value(row['value_b'], row['unit_b'])}\t"
            f"{format_delta(row)}\t{evidence_transition(row)}\t{flags}"
        )


def _compare(args: argparse.Namespace) -> int:
    path = _resolve_store(args.db)
    if not path.is_file():
        print(
            f"error: SQLite store not found: {display_path(path)}",
            file=sys.stderr,
        )
        return 1
    store = ObservationStore(path)
    try:
        diff = store.compare_runs(
            args.run_a,
            args.run_b,
            metric=args.metric,
            only_changes=args.only_changes,
        )
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    report_path = (
        Path(args.report)
        if args.report
        else default_comparison_report_path(path, args.run_a, args.run_b)
    )
    if not report_path.is_absolute():
        report_path = Path.cwd() / report_path
    try:
        report_path = write_comparison_report(diff, report_path)
    except OSError as exc:
        print(f"error: cannot write comparison report: {exc}", file=sys.stderr)
        return 1
    diff["report_path"] = display_path(report_path)

    if args.as_json:
        print(json.dumps(diff, indent=2))
    else:
        _print_comparison(diff)
        print(f"report: {display_path(report_path)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "query":
        return _query(args)
    if args.command == "compare":
        return _compare(args)

    try:
        scenario = load_scenario(args.scenario)
        errors = validate_scenario(scenario)
        if args.command == "validate":
            if errors:
                print(f"invalid: {display_path(scenario.path)}", file=sys.stderr)
                for error in errors:
                    print(f"  {error}", file=sys.stderr)
                return 2
            print(
                f"valid: {display_path(scenario.path)} "
                f"({scenario.id}, engine={', '.join(scenario.engines)})"
            )
            return 0
        if errors:
            print(f"invalid: {display_path(scenario.path)}", file=sys.stderr)
            for error in errors:
                print(f"  {error}", file=sys.stderr)
            return 2

        result = execute(scenario, args.out)
        print(f"run: {result.run_id}")
        print(f"  observations: {result.observation_count}")
        print(f"  manifest: {display_path(result.manifest_path)}")
        print(f"  report: {display_path(result.run_dir / 'report.md')}")
        print(f"  store: {display_path(result.store_path)}")
        return 0
    except ScenarioValidationError as exc:
        print(f"invalid scenario: {display_path(args.scenario)}", file=sys.stderr)
        for error in exc.errors:
            print(f"  {error}", file=sys.stderr)
        return 2
    except (ScenarioError, FabTwinError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

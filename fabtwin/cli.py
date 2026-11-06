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
from .site_export import default_scenarios, export_site
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
    listing_group = query_parser.add_mutually_exclusive_group()
    listing_group.add_argument(
        "--runs",
        action="store_true",
        help="list runs instead of observations",
    )
    listing_group.add_argument(
        "--reports",
        action="store_true",
        help="list registered comparison reports",
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

    verify_parser = subparsers.add_parser(
        "verify-artifacts",
        help="recompute hashes for indexed run and comparison artifacts",
    )
    verify_parser.add_argument(
        "--db",
        default=None,
        help="SQLite index (default: out/fabtwin/fabtwin.db)",
    )
    verify_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit JSON instead of a report",
    )

    export_parser = subparsers.add_parser(
        "export-site",
        help="run scenarios fresh and write the website data bundle",
    )
    export_parser.add_argument("out", help="bundle directory (must be empty)")
    export_parser.add_argument(
        "--scenario",
        dest="scenarios",
        action="append",
        default=None,
        help="scenario YAML to include; repeatable (default: scenarios/*.yaml)",
    )
    export_parser.add_argument("--commit", default=None, help="source commit SHA")
    export_parser.add_argument(
        "--run-url", default=None, help="URL of the CI run that built the bundle"
    )
    export_parser.add_argument(
        "--wheel",
        dest="wheels",
        action="append",
        default=[],
        help="pure-Python wheel the browser runner installs; repeatable",
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


def _print_comparison_artifacts(rows: list[dict]) -> None:
    if not rows:
        print("no comparison reports")
        return
    print("comparison_id\trun_a\trun_b\tbytes\tsha256\tpath")
    for row in rows:
        print(
            f"{row['comparison_id']}\t{row['run_a']}\t{row['run_b']}\t"
            f"{row['bytes']}\t{row['sha256']}\t{row['path']}"
        )


def _print_verification(result: dict) -> None:
    for title, key in (
        ("Run artifacts", "run_artifacts"),
        ("Input files", "inputs"),
        ("Comparison reports", "comparison_artifacts"),
    ):
        rows = result[key]
        print(f"{title}: {len(rows)}")
        if not rows:
            print("  none")
            continue
        for row in rows:
            scope = row.get("run_id") or (
                f"{row['run_a']} vs {row['run_b']}"
            )
            if row.get("role"):
                scope += f" [{row['role']}]"
            print(f"  {row['status']:<24} {scope}  {row['path']}")
            if row["status"] == "ok":
                continue
            actual_bytes = (
                "-" if row["actual_bytes"] is None else row["actual_bytes"]
            )
            print(
                f"    expected sha256={row['expected_sha256']} "
                f"actual={row['actual_sha256'] or '-'}"
            )
            print(
                f"    expected bytes={row['expected_bytes']} "
                f"actual={actual_bytes}"
            )
            if row.get("error"):
                print(f"    error: {row['error']}")
    print(
        f"checked: {result['checked']}  ok: {result['ok']}  "
        f"failed: {result['failed']}"
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
        elif args.reports:
            rows = store.list_comparison_artifacts(
                run_id=args.run_id, limit=args.limit
            )
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
    elif args.reports:
        _print_comparison_artifacts(rows)
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
    try:
        artifact = store.record_comparison_artifact(
            run_a=args.run_a,
            run_b=args.run_b,
            path=report_path,
        )
    except StoreError as exc:
        print(
            f"error: cannot register comparison report: {exc}",
            file=sys.stderr,
        )
        return 1
    diff["report_path"] = artifact["path"]
    diff["report_artifact"] = artifact

    if args.as_json:
        print(json.dumps(diff, indent=2))
    else:
        _print_comparison(diff)
        print(f"report: {artifact['path']}")
        print(f"report sha256: {artifact['sha256']}")
    return 0


def _verify_artifacts(args: argparse.Namespace) -> int:
    path = _resolve_store(args.db)
    if not path.is_file():
        print(
            f"error: SQLite store not found: {display_path(path)}",
            file=sys.stderr,
        )
        return 1
    store = ObservationStore(path)
    try:
        result = store.verify_artifacts()
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        _print_verification(result)
    return 0 if result["failed"] == 0 else 1


def _export_site(args: argparse.Namespace) -> int:
    try:
        index = export_site(
            args.scenarios or default_scenarios(),
            args.out,
            commit=args.commit,
            run_url=args.run_url,
            wheels=args.wheels,
        )
    except (ScenarioError, FabTwinError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for run in index["runs"]:
        print(f"{run['scenario_id']}: {run['observation_count']} observations")
    print(f"bundle: {args.out} ({len(index['runs'])} runs)")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "query":
        return _query(args)
    if args.command == "compare":
        return _compare(args)
    if args.command == "verify-artifacts":
        return _verify_artifacts(args)
    if args.command == "export-site":
        return _export_site(args)

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

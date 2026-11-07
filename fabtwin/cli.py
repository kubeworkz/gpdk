"""Command line entry point: ``python -m fabtwin``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .catalog import load_catalog
from .compare_report import (
    default_comparison_report_path,
    evidence_transition,
    format_delta,
    format_value,
    write_comparison_report,
)
from .errors import (
    CatalogError,
    FabTwinError,
    MesError,
    MesIngestError,
    MesReplayError,
    ScenarioError,
    ScenarioValidationError,
    StoreError,
)
from .mes import EVIDENCE_CLASS, generate as generate_mes
from .mes_ingest import ACCEPTANCE_FILE, build_manifest, write_acceptance_report
from .mes_replay import load_replay
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

    catalog_parser = subparsers.add_parser(
        "catalog",
        help="validate a data-source catalog and registered datasets",
    )
    catalog_parser.add_argument("catalog", help="path to the catalog YAML")
    catalog_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit JSON instead of a report",
    )

    mes_parser = subparsers.add_parser(
        "mes-synth",
        help="generate synthetic MES events for schema smoke tests",
    )
    mes_parser.add_argument(
        "--out",
        default="out/mes",
        help="output directory (default: out/mes)",
    )
    mes_parser.add_argument(
        "--seed", type=int, default=42, help="random seed (default: 42)"
    )
    mes_parser.add_argument(
        "--lots",
        type=int,
        default=4,
        help="number of fab lots, at least 2 (default: 4)",
    )
    mes_parser.add_argument(
        "--days",
        type=int,
        default=14,
        help="event window in days (default: 14)",
    )
    mes_parser.add_argument(
        "--start",
        default="2026-11-01T00:00:00+00:00",
        help="window start as ISO 8601 with an offset",
    )

    manifest_parser = subparsers.add_parser(
        "mes-manifest",
        help="hash a provider MES export and write its manifest",
    )
    manifest_parser.add_argument(
        "data_dir", help="directory containing the event CSVs"
    )
    manifest_parser.add_argument(
        "--route",
        default="mes_route_events.csv",
        help="route CSV relative to data_dir (default: mes_route_events.csv)",
    )
    manifest_parser.add_argument(
        "--equipment",
        default="mes_equipment_events.csv",
        help=(
            "equipment CSV relative to data_dir "
            "(default: mes_equipment_events.csv)"
        ),
    )
    manifest_parser.add_argument(
        "--evidence-class",
        choices=sorted(EVIDENCE_CLASSES),
        default="measured",
        help="evidence class for the extract (default: measured)",
    )
    manifest_parser.add_argument("--provider", help="provider or site token")
    manifest_parser.add_argument(
        "--source-system", help="MES/OSAT source system and version"
    )
    manifest_parser.add_argument(
        "--extract-id", help="extract name and version"
    )
    manifest_parser.add_argument(
        "--extract-time",
        help="extraction time as ISO 8601 with an offset",
    )
    manifest_parser.add_argument(
        "--window-start",
        help="inclusive window start; inferred from events if omitted",
    )
    manifest_parser.add_argument(
        "--window-end",
        help="inclusive window end; inferred from events if omitted",
    )
    manifest_parser.add_argument(
        "--generator",
        default="provider.export",
        help="provider export tool (default: provider.export)",
    )
    manifest_parser.add_argument(
        "--generator-version",
        default="unspecified",
        help="provider export version (default: unspecified)",
    )
    manifest_parser.add_argument(
        "--note", help="known exclusions, outages or transfer reference"
    )
    manifest_parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing manifest.json",
    )
    manifest_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit the manifest as JSON",
    )

    check_parser = subparsers.add_parser(
        "mes-check",
        help="verify a manifested MES extract before replay",
    )
    check_parser.add_argument("manifest", help="path to manifest.json")
    report_group = check_parser.add_mutually_exclusive_group()
    report_group.add_argument(
        "--report",
        help=(
            "acceptance report path "
            "(default: acceptance.json beside the manifest)"
        ),
    )
    report_group.add_argument(
        "--no-report",
        action="store_true",
        help="verify without writing an acceptance report",
    )
    check_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit the verification summary as JSON",
    )

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


def _catalog(args: argparse.Namespace) -> int:
    try:
        catalog = load_catalog(args.catalog)
    except CatalogError as exc:
        print(
            f"invalid catalog: {display_path(Path(args.catalog))}",
            file=sys.stderr,
        )
        for error in exc.errors:
            print(f"  {error}", file=sys.stderr)
        return 2

    checks = [asdict(check) for check in catalog.verify()]
    failed = sum(1 for check in checks if check["status"] != "ok")
    result = {
        **catalog.summary(),
        "checks": checks,
        "checked": len(checks),
        "ok": len(checks) - failed,
        "failed": failed,
    }
    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"catalog: {result['catalog']}")
        print(f"sha256: {result['sha256']}")
        print(
            f"schema: {result['schema_version']}  "
            f"sources: {result['sources']['total']} "
            f"(connected={result['sources']['connected']}, "
            f"planned={result['sources']['planned']}, "
            f"blocked={result['sources']['blocked']})  "
            f"datasets: {result['datasets']}"
        )
        for check in checks:
            if check["status"] == "ok":
                print(f"  ok  {check['dataset_id']}  {check['path']}")
                continue
            print(
                f"  {check['status']}  {check['dataset_id']}  "
                f"{check['path']}"
            )
            if check["error"]:
                print(f"    {check['error']}")
        print(
            f"checked: {result['checked']}  ok: {result['ok']}  "
            f"failed: {result['failed']}"
        )
    return 0 if failed == 0 else 1


def _mes_synth(args: argparse.Namespace) -> int:
    try:
        start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    except ValueError:
        print(
            "error: --start must be ISO 8601 with an offset",
            file=sys.stderr,
        )
        return 2
    try:
        dataset = generate_mes(
            seed=args.seed,
            fab_lots=args.lots,
            days=args.days,
            start=start,
        )
        route_path, equipment_path, manifest_path = dataset.write(args.out)
    except (MesError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    summary = dataset.summary()
    print(f"synthetic MES events: {display_path(Path(args.out))}")
    print(f"  evidence: {EVIDENCE_CLASS} (synthetic, not measured)")
    print(
        f"  window: {summary['window']['start_utc']} to "
        f"{summary['window']['end_utc']}"
    )
    print(
        f"  route events: {summary['route_events']}  "
        f"{display_path(route_path)}"
    )
    print(
        f"  equipment events: {summary['equipment_events']}  "
        f"{display_path(equipment_path)}"
    )
    print(f"  manifest: {display_path(manifest_path)}")
    return 0


def _mes_manifest(args: argparse.Namespace) -> int:
    try:
        path, manifest = build_manifest(
            args.data_dir,
            evidence_class=args.evidence_class,
            route=args.route,
            equipment=args.equipment,
            provider=args.provider,
            source_system=args.source_system,
            extract_id=args.extract_id,
            extract_time=args.extract_time,
            window_start=args.window_start,
            window_end=args.window_end,
            generator=args.generator,
            generator_version=args.generator_version,
            note=args.note,
            overwrite=args.force,
        )
    except (MesIngestError, MesReplayError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps(manifest, indent=2))
        return 0

    print(f"MES manifest: {display_path(path)}")
    print(
        f"  evidence: {manifest['evidence_class']} "
        f"(synthetic={str(manifest['synthetic']).lower()}, "
        f"measured={str(manifest['measured']).lower()})"
    )
    print(
        f"  window: {manifest['window']['start_utc']} to "
        f"{manifest['window']['end_utc']}"
    )
    for entry in manifest["files"]:
        print(
            f"  {entry['path']}: {entry['rows']} rows, "
            f"{entry['bytes']} bytes, sha256 {entry['sha256']}"
        )
    print(f"  next: python -m fabtwin mes-check {display_path(path)}")
    return 0


def _mes_check(args: argparse.Namespace) -> int:
    report_path: Path | None = None
    if not args.no_report:
        report_path = (
            Path(args.report)
            if args.report
            else Path(args.manifest).parent / ACCEPTANCE_FILE
        )
        if not report_path.is_absolute():
            report_path = Path.cwd() / report_path

    try:
        result = load_replay(args.manifest)
    except (MesReplayError, OSError) as exc:
        if report_path is not None:
            try:
                written, _report = write_acceptance_report(
                    args.manifest,
                    error=str(exc),
                    report_path=report_path,
                )
            except (MesIngestError, OSError) as report_exc:
                print(
                    f"warning: cannot write acceptance report: "
                    f"{report_exc}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"acceptance: {display_path(written)}",
                    file=sys.stderr,
                )
        print(f"error: {exc}", file=sys.stderr)
        return 1

    report_ref: str | None = None
    if report_path is not None:
        try:
            written, _report = write_acceptance_report(
                args.manifest,
                result=result,
                report_path=report_path,
            )
        except (MesIngestError, OSError) as exc:
            print(
                f"error: cannot write acceptance report: {exc}",
                file=sys.stderr,
            )
            return 2
        report_ref = display_path(written)

    payload = {
        "manifest": display_path(result.manifest_path),
        "manifest_sha256": result.manifest_sha256,
        "evidence_class": result.evidence_class,
        "synthetic": result.synthetic,
        "generator": result.generator,
        "generator_version": result.generator_version,
        "window": {
            "start_utc": result.window_start.isoformat(),
            "end_utc": result.window_end.isoformat(),
        },
        "route": {
            "path": display_path(result.route_path),
            "rows": result.route_rows,
            "sha256": result.route_sha256,
        },
        "equipment": {
            "path": display_path(result.equipment_path),
            "rows": result.equipment_rows,
            "sha256": result.equipment_sha256,
        },
        "lots": result.lot_count,
        "completed_lots": result.completed_lots,
        "completed_wafers": result.completed_wafers,
        "open_lots": result.open_lots,
        "cycle_time_hours": result.cycle_time_hours,
        "queue_time_hours": result.queue_time_hours,
        "wip_lots": result.wip_lots,
        "peak_wip_lots": result.peak_wip_lots,
        "throughput_wafers_per_week": (
            result.throughput_wafers_per_week
        ),
        "tool_count": len(result.tool_utilization),
        "tool_group_count": len(result.tool_group_utilization),
        "acceptance_report": report_ref,
    }
    if args.as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"extract: {payload['manifest']}")
    print(f"  manifest sha256: {payload['manifest_sha256']}")
    print(
        f"  evidence: {payload['evidence_class']} "
        f"(synthetic={str(payload['synthetic']).lower()})"
    )
    print(
        f"  window: {payload['window']['start_utc']} to "
        f"{payload['window']['end_utc']}"
    )
    print(
        f"  route events: {payload['route']['rows']}  "
        f"equipment events: {payload['equipment']['rows']}"
    )
    print(
        f"  lots: {payload['lots']}  "
        f"completed: {payload['completed_lots']}  "
        f"open: {payload['open_lots']}"
    )
    print(f"  cycle time: {payload['cycle_time_hours']:.2f} h")
    print(f"  queue time: {payload['queue_time_hours']:.2f} h")
    print(
        f"  WIP: {payload['wip_lots']:.3f} lots  "
        f"peak: {payload['peak_wip_lots']}"
    )
    print(
        f"  throughput: "
        f"{payload['throughput_wafers_per_week']:.2f} wafers/week"
    )
    print(
        f"  tools: {payload['tool_count']}  "
        f"groups: {payload['tool_group_count']}"
    )
    if report_ref:
        print(f"  acceptance: {report_ref}")
    print("status: ok")
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
    if args.command == "catalog":
        return _catalog(args)
    if args.command == "mes-synth":
        return _mes_synth(args)
    if args.command == "mes-manifest":
        return _mes_manifest(args)
    if args.command == "mes-check":
        return _mes_check(args)
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

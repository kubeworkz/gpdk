"""Build a verifiable manifest for a provider MES event extract.

The synthetic generator writes its own manifest because it controls the files.
A real extract arrives as provider CSVs, so ingest has to establish provenance
instead: verify the contract headers, count rows, reject duplicate event IDs,
hash the exact bytes and record the declared evidence class and window. The
result is the same manifest format the replay verifier already consumes.

This module never repairs a bad export and never invents rows. If a header,
timestamp or identifier is wrong, the provider must re-export it.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import MesIngestError
from .mes_replay import MesReplayResult, load_contract
from .model import EVIDENCE_CLASSES
from .provenance import display_path, sha256_file

MANIFEST_SCHEMA_VERSION = "0.1"
MANIFEST_FILE = "manifest.json"
ROUTE_FILE = "mes_route_events.csv"
EQUIPMENT_FILE = "mes_equipment_events.csv"
ROUTE_CONTRACT = "catalog/templates/mes_route_events.schema.yaml"
EQUIPMENT_CONTRACT = "catalog/templates/mes_equipment_events.schema.yaml"
ACCEPTANCE_SCHEMA_VERSION = "0.1"
ACCEPTANCE_FILE = "acceptance.json"
ACCEPTANCE_CHECKS = (
    "manifest_schema",
    "file_integrity",
    "contract_headers",
    "event_timestamps",
    "route_order",
    "genealogy",
    "tool_states",
    "completed_lots",
    "metrics",
)


@dataclass(frozen=True)
class FileInventory:
    """One CSV's contract, size and event-time envelope."""

    path: Path
    relative_path: str
    rows: int
    bytes: int
    sha256: str
    first_event: datetime
    last_event: datetime


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise MesIngestError(
            f"{label} must be ISO 8601 with an explicit offset"
        ) from exc
    if parsed.tzinfo is None:
        raise MesIngestError(
            f"{label} must include an explicit UTC offset"
        )
    return parsed.astimezone(timezone.utc)


def _stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat()


def _header_error(
    actual: tuple[str, ...], expected: tuple[str, ...], label: str
) -> str:
    missing = [name for name in expected if name not in actual]
    extra = [name for name in actual if name not in expected]
    details: list[str] = []
    if missing:
        details.append("missing " + ", ".join(missing))
    if extra:
        details.append("unexpected " + ", ".join(extra))
    if not details:
        details.append("column order differs")
    return (
        f"{label}: header does not match the contract "
        f"({'; '.join(details)})"
    )


def _scan_event_file(
    path: Path,
    relative_path: str,
    columns: tuple[str, ...],
    label: str,
) -> FileInventory:
    try:
        event_id_index = columns.index("event_id")
        time_index = columns.index("event_time_utc")
    except ValueError as exc:
        raise MesIngestError(
            f"{label}: contract is missing event_id or event_time_utc"
        ) from exc

    rows = 0
    event_ids: set[str] = set()
    first_event: datetime | None = None
    last_event: datetime | None = None
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle, strict=True)
            header = next(reader, None)
            if header is None:
                raise MesIngestError(f"{label}: file is empty")
            if tuple(header) != columns:
                raise MesIngestError(
                    _header_error(tuple(header), columns, label)
                )
            for line, record in enumerate(reader, start=2):
                if not record:
                    raise MesIngestError(
                        f"{label} line {line}: blank rows are not allowed"
                    )
                if len(record) != len(columns):
                    raise MesIngestError(
                        f"{label} line {line}: expected {len(columns)} "
                        f"columns, found {len(record)}"
                    )
                event_id = record[event_id_index].strip()
                if not event_id:
                    raise MesIngestError(
                        f"{label} line {line}: event_id is empty"
                    )
                if event_id in event_ids:
                    raise MesIngestError(
                        f"{label} line {line}: duplicate event_id "
                        f"{event_id!r}"
                    )
                event_ids.add(event_id)
                when = _parse_timestamp(
                    record[time_index],
                    f"{label} line {line}: event_time_utc",
                )
                if first_event is None or when < first_event:
                    first_event = when
                if last_event is None or when > last_event:
                    last_event = when
                rows += 1
    except MesIngestError:
        raise
    except UnicodeError as exc:
        raise MesIngestError(
            f"{label}: file is not valid UTF-8: {exc}"
        ) from exc
    except csv.Error as exc:
        raise MesIngestError(f"{label}: malformed CSV: {exc}") from exc
    except OSError as exc:
        raise MesIngestError(f"{label}: cannot read file: {exc}") from exc

    if rows == 0:
        raise MesIngestError(f"{label}: file has no event rows")
    assert first_event is not None and last_event is not None
    return FileInventory(
        path=path,
        relative_path=relative_path,
        rows=rows,
        bytes=path.stat().st_size,
        sha256=sha256_file(path),
        first_event=first_event,
        last_event=last_event,
    )


def _member_path(
    directory: Path, value: str | Path, default: str, label: str
) -> tuple[Path, str]:
    candidate = Path(value) if value else Path(default)
    if not candidate.is_absolute():
        candidate = directory / candidate
    path = candidate.resolve()
    try:
        relative = path.relative_to(directory).as_posix()
    except ValueError as exc:
        raise MesIngestError(
            f"{label} must be inside the extract directory: {path}"
        ) from exc
    if not path.is_file():
        raise MesIngestError(f"{label} not found: {path}")
    return path, relative


def _file_entry(
    inventory: FileInventory, contract: str
) -> dict[str, Any]:
    return {
        "path": inventory.relative_path,
        "contract": contract,
        "rows": inventory.rows,
        "bytes": inventory.bytes,
        "sha256": inventory.sha256,
    }


def build_manifest(
    data_dir: str | Path,
    *,
    evidence_class: str = "measured",
    route: str | Path = ROUTE_FILE,
    equipment: str | Path = EQUIPMENT_FILE,
    provider: str | None = None,
    source_system: str | None = None,
    extract_id: str | None = None,
    extract_time: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    generator: str = "provider.export",
    generator_version: str = "unspecified",
    note: str | None = None,
    overwrite: bool = False,
) -> tuple[Path, dict[str, Any]]:
    """Verify a provider extract and write its ``manifest.json``.

    ``measured`` ingest requires the provenance fields needed to identify the
    source and extraction. ``assumed``/``literature`` ingest is allowed for
    dry runs but remains visibly non-measured.
    """
    directory = Path(data_dir).resolve()
    if not directory.is_dir():
        raise MesIngestError(
            f"MES extract directory not found: {directory}"
        )
    if evidence_class not in EVIDENCE_CLASSES:
        raise MesIngestError(
            f"unknown evidence class {evidence_class!r}"
        )
    generator = generator.strip()
    generator_version = generator_version.strip()
    if not generator or not generator_version:
        raise MesIngestError("generator and generator_version are required")

    provider = provider.strip() if provider else ""
    source_system = source_system.strip() if source_system else ""
    extract_id = extract_id.strip() if extract_id else ""
    if evidence_class == "measured":
        missing = [
            name
            for name, value in (
                ("provider", provider),
                ("source_system", source_system),
                ("extract_id", extract_id),
                ("extract_time", extract_time),
            )
            if not value
        ]
        if missing:
            raise MesIngestError(
                "measured ingest requires "
                + ", ".join(f"--{name.replace('_', '-')}" for name in missing)
            )

    manifest_path = directory / MANIFEST_FILE
    if manifest_path.exists() and not overwrite:
        raise MesIngestError(
            f"manifest already exists: {manifest_path}; "
            "use --force to replace it"
        )

    route_columns, _ = load_contract(ROUTE_CONTRACT)
    equipment_columns, _ = load_contract(EQUIPMENT_CONTRACT)
    route_path, route_relative = _member_path(
        directory, route, ROUTE_FILE, "route file"
    )
    equipment_path, equipment_relative = _member_path(
        directory, equipment, EQUIPMENT_FILE, "equipment file"
    )
    route_inventory = _scan_event_file(
        route_path, route_relative, route_columns, "route file"
    )
    equipment_inventory = _scan_event_file(
        equipment_path,
        equipment_relative,
        equipment_columns,
        "equipment file",
    )

    inferred_start = min(
        route_inventory.first_event, equipment_inventory.first_event
    )
    inferred_end = max(
        route_inventory.last_event, equipment_inventory.last_event
    )
    start = (
        _parse_timestamp(window_start, "--window-start")
        if window_start
        else inferred_start
    )
    end = (
        _parse_timestamp(window_end, "--window-end")
        if window_end
        else inferred_end
    )
    if end <= start:
        raise MesIngestError(
            "manifest window must end after it starts"
        )
    for label, inventory in (
        ("route", route_inventory),
        ("equipment", equipment_inventory),
    ):
        if (
            inventory.first_event < start
            or inventory.last_event > end
        ):
            raise MesIngestError(
                f"{label} events span "
                f"{_stamp(inventory.first_event)} to "
                f"{_stamp(inventory.last_event)}, outside the manifest "
                f"window {_stamp(start)} to {_stamp(end)}"
            )

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generator": generator,
        "generator_version": generator_version,
        "evidence_class": evidence_class,
        "synthetic": False,
        "measured": evidence_class == "measured",
        "window": {
            "start_utc": _stamp(start),
            "end_utc": _stamp(end),
        },
        "files": [
            _file_entry(route_inventory, ROUTE_CONTRACT),
            _file_entry(equipment_inventory, EQUIPMENT_CONTRACT),
        ],
    }
    if provider:
        manifest["provider"] = provider
    if source_system:
        manifest["source_system"] = source_system
    if extract_id:
        manifest["extract_id"] = extract_id
    if extract_time:
        manifest["extract_time_utc"] = _stamp(
            _parse_timestamp(extract_time, "--extract-time")
        )
    manifest["note"] = (
        note.strip()
        if note and note.strip()
        else (
            "Provider MES extract ingested by fabtwin.mes-manifest. "
            "Run fabtwin mes-check before replay; see "
            "docs/mes-ingest-checklist.md."
        )
    )

    try:
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise MesIngestError(
            f"cannot write manifest {manifest_path}: {exc}"
        ) from exc
    return manifest_path, manifest


def write_acceptance_report(
    manifest_path: str | Path,
    *,
    result: MesReplayResult | None = None,
    error: str | None = None,
    report_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Write a machine-readable acceptance report beside the manifest.

    The report embeds the manifest, records every verification gate that
    succeeded and stores the event-derived metric summary. A failed check also
    writes a report, with ``status: failed`` and the error, so a stale success
    cannot be mistaken for the current state of the extract.
    """
    if result is not None and error is not None:
        raise MesIngestError(
            "an acceptance report cannot be both passed and failed"
        )
    if result is None and error is None:
        raise MesIngestError(
            "an acceptance report needs a result or an error"
        )

    path = Path(manifest_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()

    if report_path is None:
        target = path.parent / ACCEPTANCE_FILE
    else:
        target = Path(report_path)
        if not target.is_absolute():
            target = Path.cwd() / target
        target = target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
    if target == path:
        raise MesIngestError(
            "acceptance report path must not be the manifest"
        )
    if not target.parent.is_dir():
        raise MesIngestError(
            f"acceptance report directory not found: {target.parent}"
        )

    manifest_bytes: int | None = None
    manifest_sha256: str | None = None
    raw_manifest: Any = None
    manifest_read_error: str | None = None
    if path.is_file():
        try:
            manifest_bytes = path.stat().st_size
            manifest_sha256 = sha256_file(path)
            raw_manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            manifest_read_error = str(exc)
    else:
        manifest_read_error = f"manifest not found: {display_path(path)}"

    if isinstance(raw_manifest, dict):
        files = raw_manifest.get("files")
        if isinstance(files, list):
            for entry in files:
                if not isinstance(entry, dict):
                    continue
                event_path = entry.get("path")
                if not isinstance(event_path, str):
                    continue
                if target == (path.parent / event_path).resolve():
                    raise MesIngestError(
                        "acceptance report path must not overwrite "
                        "an event file"
                    )

    if result is not None:
        if manifest_sha256 != result.manifest_sha256:
            raise MesIngestError(
                "manifest changed after verification; rerun mes-check"
            )
        checks = [
            {"id": name, "status": "ok"}
            for name in ACCEPTANCE_CHECKS
        ]
        metrics: dict[str, Any] | None = {
            "window_hours": result.window_hours,
            "route_rows": result.route_rows,
            "equipment_rows": result.equipment_rows,
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
        }
        status = "ok"
    else:
        checks = [
            {
                "id": "replay_verification",
                "status": "failed",
                "detail": error,
            }
        ]
        metrics = None
        status = "failed"

    try:
        manifest_ref = path.relative_to(target.parent).as_posix()
    except ValueError:
        manifest_ref = display_path(path)
    evidence = (
        result.evidence_class
        if result is not None
        else (
            raw_manifest.get("evidence_class")
            if isinstance(raw_manifest, dict)
            else None
        )
    )
    report: dict[str, Any] = {
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "status": status,
        "manifest_path": manifest_ref,
        "manifest_sha256": manifest_sha256,
        "manifest_bytes": manifest_bytes,
        "evidence_class": evidence,
        "manifest": raw_manifest,
        "checks": checks,
        "metrics": metrics,
        "error": error,
    }
    if manifest_read_error:
        report["manifest_read_error"] = manifest_read_error

    try:
        target.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise MesIngestError(
            f"cannot write acceptance report {target}: {exc}"
        ) from exc
    return target, report

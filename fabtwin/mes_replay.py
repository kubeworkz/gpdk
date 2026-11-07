"""Replay a verified MES event extract into event-derived line metrics.

The replay is not a simulation. It reads the route and equipment event files
declared by an extract manifest, verifies their size, SHA-256, row count and
column contract, and derives cycle time, queue time, WIP, throughput and tool
usage from the event timestamps. The manifest's evidence class is carried
through to every observation, so a synthetic fixture cannot be reported as
measured line data.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

from .errors import MesReplayError
from .model import EVIDENCE_CLASSES
from .provenance import ROOT, sha256_file

MANIFEST_SCHEMA_VERSION = "0.1"
HOURS_PER_WEEK = 168.0
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ROUTE_SUFFIX = "mes_route_events.schema.yaml"
_EQUIPMENT_SUFFIX = "mes_equipment_events.schema.yaml"


@dataclass(frozen=True)
class MesReplayResult:
    """Verified extract provenance plus event-derived factory metrics."""

    manifest_path: Path
    manifest_sha256: str
    evidence_class: str
    synthetic: bool
    generator: str
    generator_version: str
    window_start: datetime
    window_end: datetime
    route_path: Path
    route_sha256: str
    equipment_path: Path
    equipment_sha256: str
    route_rows: int
    equipment_rows: int
    lot_count: int
    completed_lots: int
    completed_wafers: int
    open_lots: int
    cycle_time_hours: float
    queue_time_hours: float
    wip_lots: float
    peak_wip_lots: int
    throughput_wafers_per_week: float
    tool_utilization: Mapping[str, float]
    tool_group_utilization: Mapping[str, float]
    step_queue_hours: Mapping[str, float]

    @property
    def window_hours(self) -> float:
        return (
            self.window_end - self.window_start
        ).total_seconds() / 3600.0


def _text(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MesReplayError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MesReplayError(f"{label} must be a non-negative integer")
    return value


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MesReplayError(f"{label} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise MesReplayError(
            f"{label} must be an ISO 8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise MesReplayError(f"{label} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


_MISSING = object()


def _integer(
    value: Any, label: str, default: Any = _MISSING
) -> int | Any:
    if value is None or value == "":
        if default is _MISSING:
            raise MesReplayError(f"{label} must be an integer")
        return default
    if isinstance(value, bool):
        raise MesReplayError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise MesReplayError(f"{label} must be an integer") from exc
    if parsed < 0:
        raise MesReplayError(f"{label} must be non-negative")
    return parsed


def _schema(contract_ref: Any) -> tuple[tuple[str, ...], Mapping[str, Any]]:
    if not isinstance(contract_ref, str) or not contract_ref.strip():
        raise MesReplayError("manifest file entry needs a contract path")
    path = (ROOT / contract_ref.strip()).resolve()
    if path != ROOT and ROOT not in path.parents:
        raise MesReplayError(
            f"contract path escapes the project: {contract_ref!r}"
        )
    if not path.is_file():
        raise MesReplayError(f"contract not found: {contract_ref}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise MesReplayError(f"cannot read contract {contract_ref}: {exc}")
    if not isinstance(raw, Mapping):
        raise MesReplayError(f"contract {contract_ref} must be a mapping")
    columns = raw.get("columns")
    if not isinstance(columns, list) or not columns:
        raise MesReplayError(f"contract {contract_ref} has no columns")
    names: list[str] = []
    for column in columns:
        if not isinstance(column, Mapping):
            raise MesReplayError(
                f"contract {contract_ref} has an invalid column"
            )
        name = column.get("name")
        if not isinstance(name, str) or not name:
            raise MesReplayError(
                f"contract {contract_ref} has an invalid column name"
            )
        names.append(name)
    if len(set(names)) != len(names):
        raise MesReplayError(
            f"contract {contract_ref} has duplicate column names"
        )
    return tuple(names), raw


def load_contract(
    contract_ref: Any,
) -> tuple[tuple[str, ...], Mapping[str, Any]]:
    """Return the ordered columns and raw schema for a contract path."""
    return _schema(contract_ref)


def _allowed_values(
    schema: Mapping[str, Any], name: str
) -> frozenset[str]:
    columns = schema.get("columns", [])
    for column in columns:
        if isinstance(column, Mapping) and column.get("name") == name:
            values = column.get("allowed_values", [])
            if isinstance(values, list):
                return frozenset(
                    value for value in values if isinstance(value, str)
                )
    return frozenset()


def _file_entry(
    files: Any, suffix: str
) -> Mapping[str, Any]:
    if not isinstance(files, list) or not files:
        raise MesReplayError("manifest.files must be a non-empty list")
    matches = [
        entry
        for entry in files
        if isinstance(entry, Mapping)
        and str(entry.get("contract", "")).endswith(suffix)
    ]
    if len(matches) != 1:
        raise MesReplayError(
            f"manifest must declare exactly one {suffix} file"
        )
    return matches[0]


def _load_event_file(
    base: Path, entry: Mapping[str, Any], suffix: str
) -> tuple[Path, str, list[dict[str, str]], Mapping[str, Any]]:
    path_value = entry.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise MesReplayError("manifest file entry needs a path")
    relative = Path(path_value.strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise MesReplayError(
            f"manifest path must be relative: {path_value!r}"
        )
    path = (base / relative).resolve()
    if base.resolve() not in path.parents:
        raise MesReplayError(
            f"manifest path escapes its directory: {path_value!r}"
        )
    if not path.is_file():
        raise MesReplayError(f"MES event file not found: {path_value}")

    expected_bytes = _non_negative_int(
        entry.get("bytes"), f"{path_value}.bytes"
    )
    expected_rows = _non_negative_int(
        entry.get("rows"), f"{path_value}.rows"
    )
    expected_sha256 = entry.get("sha256")
    if (
        not isinstance(expected_sha256, str)
        or not _SHA256_RE.fullmatch(expected_sha256)
    ):
        raise MesReplayError(
            f"{path_value}.sha256 must be 64 lowercase hex digits"
        )
    actual_bytes = path.stat().st_size
    actual_sha256 = sha256_file(path)
    if actual_bytes != expected_bytes:
        raise MesReplayError(
            f"{path_value} byte count is {actual_bytes}, "
            f"manifest says {expected_bytes}"
        )
    if actual_sha256 != expected_sha256:
        raise MesReplayError(
            f"{path_value} SHA-256 is {actual_sha256}, "
            f"manifest says {expected_sha256}"
        )

    columns, schema = _schema(entry.get("contract"))
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            header = tuple(reader.fieldnames or ())
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise MesReplayError(f"cannot read {path_value}: {exc}")
    if header != columns:
        raise MesReplayError(
            f"{path_value} header does not match its contract"
        )
    if len(rows) != expected_rows:
        raise MesReplayError(
            f"{path_value} has {len(rows)} rows, "
            f"manifest says {expected_rows}"
        )
    for line, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise MesReplayError(
                f"{path_value} line {line} has the wrong column count"
            )
    return path, actual_sha256, rows, schema


def _load_manifest(path: Path) -> Mapping[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MesReplayError(f"cannot read MES manifest: {exc}")
    if not isinstance(raw, Mapping):
        raise MesReplayError("MES manifest must be a mapping")
    if raw.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise MesReplayError(
            "MES manifest schema_version must be "
            f"{MANIFEST_SCHEMA_VERSION!r}"
        )
    evidence = raw.get("evidence_class")
    if evidence not in EVIDENCE_CLASSES:
        raise MesReplayError(
            f"MES manifest evidence_class {evidence!r} is not valid"
        )
    synthetic = raw.get("synthetic", False)
    measured = raw.get("measured", False)
    if not isinstance(synthetic, bool) or not isinstance(measured, bool):
        raise MesReplayError(
            "MES manifest synthetic and measured flags must be booleans"
        )
    if synthetic and measured:
        raise MesReplayError(
            "MES manifest cannot be both synthetic and measured"
        )
    if synthetic and evidence != "assumed":
        raise MesReplayError(
            "a synthetic MES manifest must use evidence_class 'assumed'"
        )
    if measured and evidence != "measured":
        raise MesReplayError(
            "a measured MES manifest must use evidence_class 'measured'"
        )
    if measured:
        for key in (
            "provider",
            "source_system",
            "extract_id",
            "extract_time_utc",
        ):
            value = raw.get(key)
            if not isinstance(value, str) or not value.strip():
                raise MesReplayError(
                    f"a measured MES manifest requires {key}"
                )
        _parse_time(
            raw.get("extract_time_utc"),
            "manifest.extract_time_utc",
        )
    window = raw.get("window")
    if not isinstance(window, Mapping):
        raise MesReplayError("MES manifest needs a window mapping")
    start = _parse_time(window.get("start_utc"), "window.start_utc")
    end = _parse_time(window.get("end_utc"), "window.end_utc")
    if end <= start:
        raise MesReplayError("MES manifest window must end after it starts")
    _text(raw, "generator", "manifest")
    _text(raw, "generator_version", "manifest")
    return raw


def _route_rows(
    rows: list[dict[str, str]],
    schema: Mapping[str, Any],
    start: datetime,
    end: datetime,
) -> dict[str, list[tuple[datetime, dict[str, str]]]]:
    allowed_events = _allowed_values(schema, "event_type")
    lots: dict[str, list[tuple[datetime, dict[str, str]]]] = {}
    for line, row in enumerate(rows, start=2):
        label = f"route line {line}"
        event_type = row.get("event_type", "")
        if not event_type:
            raise MesReplayError(f"{label} has no event_type")
        if allowed_events and event_type not in allowed_events:
            raise MesReplayError(
                f"{label} has unknown event_type {event_type!r}"
            )
        when = _parse_time(row.get("event_time_utc"), f"{label} event_time")
        if not start <= when <= end:
            raise MesReplayError(
                f"{label} event_time is outside the manifest window"
            )
        lot_id = row.get("lot_id", "")
        if not lot_id:
            raise MesReplayError(f"{label} has no lot_id")
        _integer(row.get("wafer_count"), f"{label} wafer_count")
        parent = row.get("parent_lot_id", "")
        if event_type in {"split", "merge"}:
            if not parent:
                raise MesReplayError(
                    f"{label} {event_type} has no parent_lot_id"
                )
        elif parent:
            raise MesReplayError(
                f"{label} parent_lot_id is only valid on split or merge"
            )
        if event_type in {"process_start", "process_end"}:
            if not row.get("operation_id"):
                raise MesReplayError(f"{label} has no operation_id")
        lots.setdefault(lot_id, []).append((when, row))

    for lot_id, items in lots.items():
        times = [item[0] for item in items]
        if any(earlier > later for earlier, later in zip(times, times[1:])):
            raise MesReplayError(
                f"route: {lot_id} events are out of order"
            )
    return lots


def _queue_visits(
    items: list[tuple[datetime, dict[str, str]]]
) -> tuple[float, list[tuple[str, float]]]:
    pending: list[tuple[datetime, int | None, str]] = []
    last = items[0][0]
    total_hours = 0.0
    visits: list[tuple[str, float]] = []
    for when, row in items:
        event_type = row["event_type"]
        if event_type == "move_in":
            pending.append(
                (
                    when,
                    _integer(
                        row.get("queue_time_s"), "queue_time_s", None
                    ),
                    row.get("operation_id", ""),
                )
            )
        elif event_type == "process_start":
            setup_s = _integer(row.get("setup_time_s"), "setup_time_s", 0)
            if pending:
                move_time, recorded, operation_id = pending.pop(0)
                if recorded is None:
                    queue_s = max(
                        0.0,
                        (when - move_time).total_seconds() - setup_s,
                    )
                else:
                    queue_s = float(recorded)
            else:
                queue_s = max(
                    0.0, (when - last).total_seconds() - setup_s
                )
                operation_id = row.get("operation_id", "")
            total_hours += queue_s / 3600.0
            visits.append((operation_id, queue_s / 3600.0))
        last = when
    return total_hours, visits


def _wip(
    lots: dict[str, list[tuple[datetime, dict[str, str]]]],
    completed: Mapping[str, tuple[datetime, datetime, int]],
    parent_ends: Mapping[str, list[datetime]],
    start: datetime,
    end: datetime,
) -> tuple[float, int, int]:
    intervals: list[tuple[datetime, datetime]] = []
    open_lots = 0
    for lot_id, items in lots.items():
        interval_start = max(items[0][0], start)
        if lot_id in completed:
            interval_end = completed[lot_id][1]
        elif lot_id in parent_ends:
            interval_end = min(parent_ends[lot_id])
        else:
            interval_end = end
            open_lots += 1
        interval_end = min(interval_end, end)
        if interval_end > interval_start:
            intervals.append((interval_start, interval_end))
    changes: list[tuple[datetime, int]] = []
    for interval_start, interval_end in intervals:
        changes.append((interval_start, 1))
        changes.append((interval_end, -1))
    changes.sort(key=lambda item: (item[0], item[1]))
    area = 0.0
    count = 0
    peak = 0
    last = start
    for when, delta in changes:
        area += count * (when - last).total_seconds()
        count += delta
        peak = max(peak, count)
        last = when
    area += count * (end - last).total_seconds()
    window_seconds = (end - start).total_seconds()
    return area / window_seconds, peak, open_lots


def _tool_metrics(
    rows: list[dict[str, str]],
    schema: Mapping[str, Any],
    start: datetime,
    end: datetime,
) -> tuple[dict[str, float], dict[str, float]]:
    allowed_states = _allowed_values(schema, "state")
    tools: dict[str, list[tuple[datetime, dict[str, str]]]] = {}
    for line, row in enumerate(rows, start=2):
        label = f"equipment line {line}"
        when = _parse_time(row.get("event_time_utc"), f"{label} event_time")
        if not start <= when <= end:
            raise MesReplayError(
                f"{label} event_time is outside the manifest window"
            )
        tool_id = row.get("tool_id", "")
        if not tool_id:
            raise MesReplayError(f"{label} has no tool_id")
        state = row.get("state", "")
        if allowed_states and state not in allowed_states:
            raise MesReplayError(f"{label} has unknown state {state!r}")
        tools.setdefault(tool_id, []).append((when, row))

    window_seconds = (end - start).total_seconds()
    utilization: dict[str, float] = {}
    group_tools: dict[str, set[str]] = {}
    group_busy: dict[str, float] = {}
    for tool_id, items in tools.items():
        if items[0][0] != start:
            raise MesReplayError(
                f"equipment: {tool_id} does not start at the window boundary"
            )
        times = [item[0] for item in items]
        if any(earlier >= later for earlier, later in zip(times, times[1:])):
            raise MesReplayError(
                f"equipment: {tool_id} states are not strictly ordered"
            )
        group = items[0][1].get("tool_group_id", "")
        if not group:
            raise MesReplayError(f"equipment: {tool_id} has no tool_group_id")
        busy_seconds = 0.0
        for index, (when, row) in enumerate(items):
            if row.get("tool_group_id", "") != group:
                raise MesReplayError(
                    f"equipment: {tool_id} changes tool_group_id"
                )
            interval_end = (
                items[index + 1][0] if index + 1 < len(items) else end
            )
            if row["state"] in {"productive", "setup"}:
                busy_seconds += (interval_end - when).total_seconds()
        utilization[tool_id] = busy_seconds / window_seconds
        group_tools.setdefault(group, set()).add(tool_id)
        group_busy[group] = group_busy.get(group, 0.0) + busy_seconds

    group_utilization = {
        group: group_busy[group] / (window_seconds * len(members))
        for group, members in group_tools.items()
    }
    return (
        dict(sorted(utilization.items())),
        dict(sorted(group_utilization.items())),
    )


def load_replay(manifest_path: str | Path) -> MesReplayResult:
    """Verify an MES manifest and derive metrics from its event files."""
    path = Path(manifest_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.is_file():
        raise MesReplayError(f"MES manifest not found: {path}")

    manifest = _load_manifest(path)
    start = _parse_time(
        manifest["window"]["start_utc"], "window.start_utc"
    )
    end = _parse_time(manifest["window"]["end_utc"], "window.end_utc")
    evidence = str(manifest["evidence_class"])
    synthetic = bool(manifest.get("synthetic", False))

    route_entry = _file_entry(manifest.get("files"), _ROUTE_SUFFIX)
    equipment_entry = _file_entry(
        manifest.get("files"), _EQUIPMENT_SUFFIX
    )
    route_path, route_sha256, route_rows, route_schema = (
        _load_event_file(path.parent, route_entry, _ROUTE_SUFFIX)
    )
    equipment_path, equipment_sha256, equipment_rows, equipment_schema = (
        _load_event_file(
            path.parent, equipment_entry, _EQUIPMENT_SUFFIX
        )
    )

    lots = _route_rows(route_rows, route_schema, start, end)
    completed: dict[str, tuple[datetime, datetime, int]] = {}
    for lot_id, items in lots.items():
        done = [
            row for _when, row in items
            if row["event_type"] == "lot_complete"
        ]
        if len(done) > 1:
            raise MesReplayError(
                f"route: {lot_id} has multiple lot_complete events"
            )
        if done:
            completed[lot_id] = (
                items[0][0],
                _parse_time(
                    done[0]["event_time_utc"],
                    f"{lot_id} lot_complete",
                ),
                _integer(
                    done[0].get("wafer_count"),
                    f"{lot_id} lot_complete wafer_count",
                ),
            )
    if not completed:
        raise MesReplayError(
            "route: no completed lots in the window; cannot derive cycle time"
        )

    parent_ends: dict[str, list[datetime]] = {}
    parents: dict[str, list[tuple[str, int]]] = {}
    for lot_id, items in lots.items():
        for when, row in items:
            if row["event_type"] not in {"split", "merge"}:
                continue
            parent = row.get("parent_lot_id", "")
            if parent not in lots:
                raise MesReplayError(
                    f"route: {lot_id} references unknown parent {parent!r}"
                )
            parent_ends.setdefault(parent, []).append(when)
            parents.setdefault(lot_id, []).append(
                (
                    parent,
                    _integer(
                        row.get("wafer_count"),
                        f"{lot_id} genealogy wafer_count",
                    ),
                )
            )

    checked: set[str] = set()

    def check_genealogy(lot_id: str, path: frozenset[str]) -> None:
        if lot_id in path:
            raise MesReplayError("route: lot genealogy contains a cycle")
        if lot_id in checked:
            return
        for parent, _qty in parents.get(lot_id, []):
            check_genealogy(parent, path | {lot_id})
        checked.add(lot_id)

    for lot_id in lots:
        check_genealogy(lot_id, frozenset())

    queue_totals: dict[str, float] = {}
    step_totals: dict[str, float] = {}
    step_visits: dict[str, int] = {}
    for lot_id, items in lots.items():
        queue_hours, visits = _queue_visits(items)
        queue_totals[lot_id] = queue_hours
        for operation_id, hours in visits:
            step_totals[operation_id] = (
                step_totals.get(operation_id, 0.0) + hours
            )
            step_visits[operation_id] = step_visits.get(operation_id, 0) + 1

    start_cache: dict[str, datetime] = {}
    queue_cache: dict[str, float] = {}

    def lineage_start(lot_id: str, stack: frozenset[str]) -> datetime:
        if lot_id in start_cache:
            return start_cache[lot_id]
        if lot_id in stack:
            raise MesReplayError("route: lot genealogy contains a cycle")
        starts = [lots[lot_id][0][0]]
        for parent, _qty in parents.get(lot_id, []):
            starts.append(lineage_start(parent, stack | {lot_id}))
        start_cache[lot_id] = min(starts)
        return start_cache[lot_id]

    def lineage_queue(lot_id: str, stack: frozenset[str]) -> float:
        if lot_id in queue_cache:
            return queue_cache[lot_id]
        if lot_id in stack:
            raise MesReplayError("route: lot genealogy contains a cycle")
        own = queue_totals[lot_id]
        links = parents.get(lot_id, [])
        if not links:
            value = own
        elif len(links) == 1:
            value = lineage_queue(links[0][0], stack | {lot_id}) + own
        else:
            total_qty = sum(qty for _parent, qty in links)
            if total_qty <= 0:
                raise MesReplayError(
                    f"route: {lot_id} merge has no wafer quantity"
                )
            value = own + sum(
                lineage_queue(parent, stack | {lot_id}) * qty
                for parent, qty in links
            ) / total_qty
        queue_cache[lot_id] = value
        return value

    cycles = [
        (end_time - lineage_start(lot_id, frozenset())).total_seconds()
        / 3600.0
        for lot_id, (_start, end_time, _qty) in completed.items()
    ]
    queue_values = [
        lineage_queue(lot_id, frozenset()) for lot_id in completed
    ]

    wip, peak_wip, open_lots = _wip(
        lots, completed, parent_ends, start, end
    )
    completed_wafers = sum(item[2] for item in completed.values())
    window_hours = (end - start).total_seconds() / 3600.0
    tools, groups = _tool_metrics(
        equipment_rows, equipment_schema, start, end
    )
    return MesReplayResult(
        manifest_path=path,
        manifest_sha256=sha256_file(path),
        evidence_class=evidence,
        synthetic=synthetic,
        generator=str(manifest["generator"]),
        generator_version=str(manifest["generator_version"]),
        window_start=start,
        window_end=end,
        route_path=route_path,
        route_sha256=route_sha256,
        equipment_path=equipment_path,
        equipment_sha256=equipment_sha256,
        route_rows=len(route_rows),
        equipment_rows=len(equipment_rows),
        lot_count=len(lots),
        completed_lots=len(completed),
        completed_wafers=completed_wafers,
        open_lots=open_lots,
        cycle_time_hours=statistics.fmean(cycles),
        queue_time_hours=statistics.fmean(queue_values),
        wip_lots=wip,
        peak_wip_lots=peak_wip,
        throughput_wafers_per_week=(
            completed_wafers * HOURS_PER_WEEK / window_hours
        ),
        tool_utilization=tools,
        tool_group_utilization=groups,
        step_queue_hours={
            operation_id: step_totals[operation_id]
            / step_visits[operation_id]
            for operation_id in sorted(step_totals)
        },
    )

"""Deterministic synthetic MES events for the catalog's request contracts.

The illustrative generator in ``docs/fab-sim.md`` prints a flat lot table with
pandas. This module produces the same split-and-run sequence in the two event
contracts the catalog actually declares, using only the standard library:

* route events, ``catalog/templates/mes_route_events.schema.yaml``;
* equipment states, ``catalog/templates/mes_equipment_events.schema.yaml``.

Every row is synthetic. Synthetic events exercise the schema, genealogy and
calibration plumbing; they are never measured data and must not be registered
or reported as such.
"""

from __future__ import annotations

import csv
import io
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .errors import MesError
from .provenance import sha256_bytes

GENERATOR_ID = "fabtwin.mes"
GENERATOR_VERSION = "0.1"
EVIDENCE_CLASS = "assumed"
WAFERS_PER_LOT = 25
DEFAULT_SEED = 42
DEFAULT_LOTS = 4
DEFAULT_DAYS = 14
DEFAULT_START = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)

ROUTE_COLUMNS = (
    "event_id",
    "event_type",
    "event_time_utc",
    "lot_id",
    "parent_lot_id",
    "wafer_id",
    "product_id",
    "route_id",
    "route_revision",
    "operation_seq",
    "operation_id",
    "operation_type",
    "tool_id",
    "tool_group_id",
    "tool_class",
    "chamber_id",
    "recipe_id",
    "recipe_revision",
    "process_time_s",
    "queue_time_s",
    "setup_time_s",
    "wafer_count",
    "scrap_qty",
    "rework_qty",
    "hold_reason_code",
    "data_quality_flag",
)

EQUIPMENT_COLUMNS = (
    "event_id",
    "event_time_utc",
    "tool_id",
    "tool_group_id",
    "tool_class",
    "state",
    "reason_code",
    "failure_mode_code",
    "maintenance_type",
    "lot_id",
    "wafer_count",
    "recipe_id",
    "alarm_code",
    "data_quality_flag",
)

EQUIPMENT_STATES = (
    "productive",
    "standby",
    "engineering",
    "scheduled_down",
    "unscheduled_down",
    "non_scheduled",
    "setup",
)

FAILURE_MODES = (
    "RF_MATCH_LOSS",
    "GAS_FLOW_DRIFT",
    "VACUUM_LOSS",
    "SENSOR_DRIFT",
)


@dataclass(frozen=True)
class Operation:
    """One route step and its tool, recipe and time envelope."""

    seq: int
    operation_id: str
    operation_type: str
    tool_group_id: str
    tool_class: str
    recipe_id: str
    setup_s: int
    process_min_s: int
    process_max_s: int


@dataclass(frozen=True)
class Route:
    """An ordered process flow with a versioned identity."""

    route_id: str
    revision: str
    operations: tuple[Operation, ...]

    def operation(self, seq: int) -> Operation:
        for operation in self.operations:
            if operation.seq == seq:
                return operation
        raise KeyError(seq)


@dataclass(frozen=True)
class Tool:
    """One physical tool and the group it belongs to."""

    tool_id: str
    tool_group_id: str
    tool_class: str


FAB_ROUTE = Route(
    "ROUTE_FE_MEMS_V1",
    "1",
    (
        Operation(10, "OXIDE_GROW", "oxidation", "FURNACE_A", "furnace",
                  "RCP_OXIDE_A", 900, 45, 120),
        Operation(20, "LITHO_1", "lithography", "LITHO_CELL", "litho_scanner",
                  "RCP_LITHO_L1", 600, 20, 45),
        Operation(30, "ETCH_1", "etch", "ETCH_CELL", "plasma_etcher",
                  "RCP_ETCH_E1", 300, 15, 40),
        Operation(40, "LITHO_2", "lithography", "LITHO_CELL", "litho_scanner",
                  "RCP_LITHO_L2", 600, 20, 45),
        Operation(50, "ETCH_2", "etch", "ETCH_CELL", "plasma_etcher",
                  "RCP_ETCH_E2", 300, 15, 40),
        Operation(60, "IMPLANT_1", "implant", "IMPLANT_CELL",
                  "ion_implanter", "RCP_IMPLANT_I1", 1200, 30, 60),
        Operation(70, "ANNEAL_1", "anneal", "FURNACE_A", "furnace",
                  "RCP_ANNEAL_A1", 900, 40, 90),
        Operation(80, "LITHO_3", "lithography", "LITHO_CELL", "litho_scanner",
                  "RCP_LITHO_L3", 600, 20, 45),
        Operation(90, "ETCH_3", "etch", "ETCH_CELL", "plasma_etcher",
                  "RCP_ETCH_E3", 300, 15, 40),
        Operation(100, "DEPOSITION_1", "deposition", "DEP_CELL",
                  "cvd_reactor", "RCP_DEP_D1", 600, 30, 75),
        Operation(110, "CMP_1", "cmp", "CMP_CELL", "cmp_polisher",
                  "RCP_CMP_C1", 300, 10, 30),
        Operation(120, "METROLOGY_CD", "metrology", "METRO_CELL", "metrology",
                  "RCP_METRO_M1", 120, 5, 15),
        Operation(130, "WAFER_SORT", "test", "SORT_CELL", "wafer_prober",
                  "RCP_SORT_S1", 300, 20, 50),
    ),
)

OSAT_ROUTE = Route(
    "ROUTE_OSAT_PKG_V1",
    "1",
    (
        Operation(10, "DIE_ATTACH", "assembly", "DIE_ATTACH_CELL",
                  "die_bonder", "RCP_DA_D1", 600, 20, 45),
        Operation(20, "WIRE_BOND", "assembly", "WIRE_BOND_CELL",
                  "wire_bonder", "RCP_WB_W1", 600, 15, 40),
        Operation(30, "MOLD", "mold", "MOLD_CELL", "mold_press",
                  "RCP_MOLD_M1", 900, 30, 90),
        Operation(40, "FINAL_TEST", "final_test", "TEST_CELL",
                  "final_tester", "RCP_FT_F1", 300, 20, 60),
    ),
)

TOOLS = (
    Tool("FURN_A_01", "FURNACE_A", "furnace"),
    Tool("FURN_A_02", "FURNACE_A", "furnace"),
    Tool("LITHO_01", "LITHO_CELL", "litho_scanner"),
    Tool("LITHO_02", "LITHO_CELL", "litho_scanner"),
    Tool("ETCH_01", "ETCH_CELL", "plasma_etcher"),
    Tool("ETCH_02", "ETCH_CELL", "plasma_etcher"),
    Tool("IMPLANT_01", "IMPLANT_CELL", "ion_implanter"),
    Tool("DEP_01", "DEP_CELL", "cvd_reactor"),
    Tool("CMP_01", "CMP_CELL", "cmp_polisher"),
    Tool("METRO_01", "METRO_CELL", "metrology"),
    Tool("SORT_01", "SORT_CELL", "wafer_prober"),
    Tool("DA_01", "DIE_ATTACH_CELL", "die_bonder"),
    Tool("WB_01", "WIRE_BOND_CELL", "wire_bonder"),
    Tool("WB_02", "WIRE_BOND_CELL", "wire_bonder"),
    Tool("MOLD_01", "MOLD_CELL", "mold_press"),
    Tool("TEST_01", "TEST_CELL", "final_tester"),
)


@dataclass(frozen=True)
class MesDataset:
    """Generated route and equipment events plus their window."""

    seed: int
    fab_lots: int
    window_start: datetime
    window_end: datetime
    route_events: tuple[dict[str, str], ...]
    equipment_events: tuple[dict[str, str], ...]

    def summary(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for row in self.route_events:
            counts[row["event_type"]] = counts.get(row["event_type"], 0) + 1
        return {
            "seed": self.seed,
            "fab_lots": self.fab_lots,
            "window": {
                "start_utc": _stamp(self.window_start),
                "end_utc": _stamp(self.window_end),
            },
            "route_events": len(self.route_events),
            "equipment_events": len(self.equipment_events),
            "event_types": dict(sorted(counts.items())),
            "lots": len({row["lot_id"] for row in self.route_events}),
            "tools": len({row["tool_id"] for row in self.equipment_events}),
        }

    def write(self, directory: str | Path) -> tuple[Path, Path, Path]:
        """Write both CSVs and a manifest, returning their paths."""
        route_bytes = _csv_bytes(ROUTE_COLUMNS, self.route_events)
        equipment_bytes = _csv_bytes(
            EQUIPMENT_COLUMNS, self.equipment_events
        )
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        route_path = target / "mes_route_events.csv"
        equipment_path = target / "mes_equipment_events.csv"
        manifest_path = target / "manifest.json"
        route_path.write_bytes(route_bytes)
        equipment_path.write_bytes(equipment_bytes)
        manifest = {
            "schema_version": "0.1",
            "generator": GENERATOR_ID,
            "generator_version": GENERATOR_VERSION,
            "evidence_class": EVIDENCE_CLASS,
            "synthetic": True,
            "measured": False,
            "seed": self.seed,
            "fab_lots": self.fab_lots,
            "window": {
                "start_utc": _stamp(self.window_start),
                "end_utc": _stamp(self.window_end),
            },
            "files": [
                {
                    "path": route_path.name,
                    "contract": (
                        "catalog/templates/"
                        "mes_route_events.schema.yaml"
                    ),
                    "rows": len(self.route_events),
                    "bytes": len(route_bytes),
                    "sha256": sha256_bytes(route_bytes),
                },
                {
                    "path": equipment_path.name,
                    "contract": (
                        "catalog/templates/"
                        "mes_equipment_events.schema.yaml"
                    ),
                    "rows": len(self.equipment_events),
                    "bytes": len(equipment_bytes),
                    "sha256": sha256_bytes(equipment_bytes),
                },
            ],
            "note": (
                "Synthetic MES events generated by fabtwin.mes. The evidence "
                "class is assumed: these rows exercise schemas, genealogy and "
                "calibration plumbing and are not measured line data."
            ),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return route_path, equipment_path, manifest_path


@dataclass(frozen=True)
class _Marker:
    """A non-process event inserted into a lot plan."""

    kind: str
    operation: Operation
    value: int = 0


@dataclass(frozen=True)
class _Busy:
    start: datetime
    end: datetime
    kind: str
    lot_id: str
    recipe_id: str
    wafer_count: int


@dataclass(frozen=True)
class _Down:
    start: datetime
    end: datetime
    meta: dict[str, str]


class _ToolCalendar:
    """Reserve a tool one job at a time, around planned downtime."""

    def __init__(self, tool: Tool, down: list[_Down]) -> None:
        self.tool = tool
        self.down = down
        self.busy: list[_Busy] = []
        self.jobs = 0

    def earliest(
        self, ready: datetime, duration: timedelta, window_end: datetime
    ) -> datetime:
        candidate = ready
        while True:
            moved = False
            for start, end in self._occupied():
                if candidate < end and candidate + duration > start:
                    candidate = end
                    moved = True
            if not moved:
                break
        if candidate + duration > window_end:
            raise MesError(
                f"window is too short for {self.tool.tool_id}; "
                "increase days or lower the lot count"
            )
        return candidate

    def reserve(
        self,
        setup_start: datetime,
        process_start: datetime,
        process_end: datetime,
        lot_id: str,
        recipe_id: str,
        wafer_count: int,
    ) -> None:
        self.busy.append(
            _Busy(
                setup_start,
                process_start,
                "setup",
                lot_id,
                recipe_id,
                wafer_count,
            )
        )
        self.busy.append(
            _Busy(
                process_start,
                process_end,
                "productive",
                lot_id,
                recipe_id,
                wafer_count,
            )
        )
        self.jobs += 1

    def _occupied(self) -> list[tuple[datetime, datetime]]:
        spans = [(job.start, job.end) for job in self.busy]
        spans.extend((window.start, window.end) for window in self.down)
        return sorted(spans)


def _stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_stamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _text(value: int | None) -> str:
    return "" if value is None else str(value)


def _csv_bytes(
    columns: tuple[str, ...], rows: tuple[dict[str, str], ...]
) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(columns),
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _plan_downtime(
    tool: Tool, rng: random.Random, start: datetime, end: datetime
) -> list[_Down]:
    span = int((end - start).total_seconds() // 60)
    candidates: list[tuple[datetime, int, dict[str, str]]] = []
    pm_start = start + timedelta(
        minutes=rng.randint(18 * 60, max(18 * 60 + 1, span - 30 * 60))
    )
    candidates.append(
        (
            pm_start,
            rng.randint(120, 360),
            {
                "state": "scheduled_down",
                "reason_code": "pm",
                "failure_mode_code": "",
                "maintenance_type": "pm",
                "alarm_code": "",
            },
        )
    )
    if rng.random() < 0.45:
        failure_start = start + timedelta(
            minutes=rng.randint(6 * 60, max(6 * 60 + 1, span - 10 * 60))
        )
        candidates.append(
            (
                failure_start,
                rng.randint(30, 240),
                {
                    "state": "unscheduled_down",
                    "reason_code": "failure",
                    "failure_mode_code": rng.choice(FAILURE_MODES),
                    "maintenance_type": "",
                    "alarm_code": f"ALM_{rng.randint(1100, 4999)}",
                },
            )
        )
    if tool.tool_id == "METRO_01":
        candidates.append(
            (
                start + timedelta(minutes=span // 3),
                180,
                {
                    "state": "engineering",
                    "reason_code": "engineering_run",
                    "failure_mode_code": "",
                    "maintenance_type": "",
                    "alarm_code": "",
                },
            )
        )
    if tool.tool_id == "MOLD_01":
        candidates.append(
            (
                start + timedelta(minutes=span // 2),
                240,
                {
                    "state": "non_scheduled",
                    "reason_code": "no_shift",
                    "failure_mode_code": "",
                    "maintenance_type": "",
                    "alarm_code": "",
                },
            )
        )
    candidates.sort(key=lambda item: item[0])
    planned: list[_Down] = []
    cursor = start
    latest = end - timedelta(minutes=45)
    for candidate, minutes, meta in candidates:
        candidate = max(candidate, cursor)
        finish = min(candidate + timedelta(minutes=minutes), latest)
        if finish - candidate < timedelta(minutes=15):
            continue
        planned.append(_Down(candidate, finish, meta))
        cursor = finish
    return planned


def _append(
    rows: list[dict[str, str]],
    event_type: str,
    when: datetime,
    *,
    lot_id: str,
    product_id: str,
    route: Route,
    operation: Operation,
    wafer_count: int,
    parent_lot_id: str = "",
    tool: Tool | None = None,
    process_time_s: int | None = None,
    queue_time_s: int | None = None,
    setup_time_s: int | None = None,
    scrap_qty: int | None = None,
    rework_qty: int | None = None,
    hold_reason_code: str = "",
    data_quality_flag: str = "ok",
) -> None:
    rows.append(
        {
            "event_id": "",
            "event_type": event_type,
            "event_time_utc": _stamp(when),
            "lot_id": lot_id,
            "parent_lot_id": parent_lot_id,
            "wafer_id": "",
            "product_id": product_id,
            "route_id": route.route_id,
            "route_revision": route.revision,
            "operation_seq": str(operation.seq),
            "operation_id": operation.operation_id,
            "operation_type": operation.operation_type,
            "tool_id": tool.tool_id if tool else "",
            "tool_group_id": tool.tool_group_id if tool else "",
            "tool_class": tool.tool_class if tool else "",
            "chamber_id": "",
            "recipe_id": operation.recipe_id if tool else "",
            "recipe_revision": route.revision if tool else "",
            "process_time_s": _text(process_time_s),
            "queue_time_s": _text(queue_time_s),
            "setup_time_s": _text(setup_time_s),
            "wafer_count": str(wafer_count),
            "scrap_qty": _text(scrap_qty),
            "rework_qty": _text(rework_qty),
            "hold_reason_code": hold_reason_code,
            "data_quality_flag": data_quality_flag,
        }
    )


def _run_operation(
    *,
    rows: list[dict[str, str]],
    route: Route,
    operation: Operation,
    lot_id: str,
    product_id: str,
    wafer_count: int,
    ready: datetime,
    calendars: dict[str, _ToolCalendar],
    rng: random.Random,
    window_end: datetime,
) -> datetime:
    process_s = 60 * rng.randint(
        operation.process_min_s, operation.process_max_s
    )
    duration = timedelta(seconds=operation.setup_s + process_s)
    best: tuple[tuple[datetime, str], _ToolCalendar, datetime] | None = None
    for tool_id in sorted(calendars):
        calendar = calendars[tool_id]
        if calendar.tool.tool_group_id != operation.tool_group_id:
            continue
        slot = calendar.earliest(ready, duration, window_end)
        key = (slot, calendar.jobs, tool_id)
        if best is None or key < best[0]:
            best = (key, calendar, slot)
    if best is None:
        raise MesError(f"no tool declared for {operation.tool_group_id}")
    _, calendar, setup_start = best
    tool = calendar.tool
    process_start = setup_start + timedelta(seconds=operation.setup_s)
    process_end = process_start + timedelta(seconds=process_s)
    if process_end + timedelta(minutes=25) > window_end:
        raise MesError(
            "window is too short for the move-out and completion events; "
            "increase days or lower the lot count"
        )
    calendar.reserve(
        setup_start,
        process_start,
        process_end,
        lot_id,
        operation.recipe_id,
        wafer_count,
    )
    _append(
        rows,
        "move_in",
        ready,
        lot_id=lot_id,
        product_id=product_id,
        route=route,
        operation=operation,
        wafer_count=wafer_count,
        queue_time_s=int((setup_start - ready).total_seconds()),
    )
    _append(
        rows,
        "process_start",
        process_start,
        lot_id=lot_id,
        product_id=product_id,
        route=route,
        operation=operation,
        wafer_count=wafer_count,
        tool=tool,
        setup_time_s=operation.setup_s,
    )
    _append(
        rows,
        "process_end",
        process_end,
        lot_id=lot_id,
        product_id=product_id,
        route=route,
        operation=operation,
        wafer_count=wafer_count,
        tool=tool,
        process_time_s=process_s,
    )
    move_out = process_end + timedelta(minutes=rng.randint(5, 20))
    _append(
        rows,
        "move_out",
        move_out,
        lot_id=lot_id,
        product_id=product_id,
        route=route,
        operation=operation,
        wafer_count=wafer_count,
    )
    return move_out


def _plan_index(plan: list[Operation | _Marker], seq: int) -> int:
    for index, item in enumerate(plan):
        if isinstance(item, Operation) and item.seq == seq:
            return index
    raise KeyError(seq)


def _fab_plan(index: int) -> list[Operation | _Marker]:
    plan: list[Operation | _Marker] = list(FAB_ROUTE.operations)
    if index == 1:
        at = _plan_index(plan, 120)
        plan.insert(
            at + 1, _Marker("rework", FAB_ROUTE.operation(120))
        )
        plan.insert(at + 2, FAB_ROUTE.operation(80))
        plan.insert(at + 3, FAB_ROUTE.operation(90))
    if index == 3:
        at = _plan_index(plan, 50)
        plan.insert(
            at + 1, _Marker("scrap", FAB_ROUTE.operation(50), 1)
        )
    if index == 4:
        at = _plan_index(plan, 30)
        plan.insert(
            at + 1, _Marker("hold", FAB_ROUTE.operation(30), 9)
        )
    return plan


def _tool_states(
    tool: Tool,
    calendar: _ToolCalendar,
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, str]]:
    items: list[tuple[datetime, datetime, dict[str, str]]] = []
    for job in calendar.busy:
        items.append(
            (
                job.start,
                job.end,
                {
                    "state": job.kind,
                    "reason_code": "",
                    "failure_mode_code": "",
                    "maintenance_type": "",
                    "lot_id": job.lot_id,
                    "wafer_count": str(job.wafer_count),
                    "recipe_id": job.recipe_id,
                    "alarm_code": "",
                },
            )
        )
    for down in calendar.down:
        items.append((down.start, down.end, down.meta))
    items.sort(key=lambda item: (item[0], item[1], item[2]["state"]))

    rows: list[dict[str, str]] = []
    cursor = window_start
    for start, end, meta in items:
        if start < cursor:
            raise MesError(
                f"overlapping equipment states on {tool.tool_id} at {start}"
            )
        if start > cursor:
            rows.append(
                _state_row(tool, cursor, state="standby", reason_code="no_lot")
            )
        rows.append(_state_row(tool, start, **meta))
        cursor = end
    if cursor < window_end:
        rows.append(
            _state_row(tool, cursor, state="standby", reason_code="no_lot")
        )
    return rows


def _state_row(
    tool: Tool,
    when: datetime,
    *,
    state: str,
    reason_code: str = "",
    failure_mode_code: str = "",
    maintenance_type: str = "",
    lot_id: str = "",
    wafer_count: str = "",
    recipe_id: str = "",
    alarm_code: str = "",
) -> dict[str, str]:
    return {
        "event_id": "",
        "event_time_utc": _stamp(when),
        "tool_id": tool.tool_id,
        "tool_group_id": tool.tool_group_id,
        "tool_class": tool.tool_class,
        "state": state,
        "reason_code": reason_code,
        "failure_mode_code": failure_mode_code,
        "maintenance_type": maintenance_type,
        "lot_id": lot_id,
        "wafer_count": wafer_count,
        "recipe_id": recipe_id,
        "alarm_code": alarm_code,
        "data_quality_flag": "ok",
    }


def generate(
    seed: int = DEFAULT_SEED,
    fab_lots: int = DEFAULT_LOTS,
    days: int = DEFAULT_DAYS,
    start: datetime | None = None,
) -> MesDataset:
    """Generate a deterministic synthetic MES event window."""
    if fab_lots < 2:
        raise MesError("fab_lots must be at least 2 to exercise lot merging")
    if days < 1:
        raise MesError("days must be at least 1")
    window_start = start or DEFAULT_START
    if window_start.tzinfo is None:
        raise MesError("start must include a UTC offset")
    window_start = window_start.astimezone(timezone.utc).replace(
        second=0, microsecond=0
    )
    window_end = window_start + timedelta(days=days)
    rng = random.Random(seed)

    calendars = {
        tool.tool_id: _ToolCalendar(
            tool, _plan_downtime(tool, rng, window_start, window_end)
        )
        for tool in TOOLS
    }

    rows: list[dict[str, str]] = []
    sub_lots: list[dict[str, object]] = []
    for index in range(1, fab_lots + 1):
        lot_id = f"LOT_FE_{index:03d}"
        product_id = (
            "PROD_MEMS_MCM" if index <= 2 else "PROD_MEMS_STD"
        )
        ready = window_start + timedelta(minutes=rng.randint(0, 36 * 60))
        qty = WAFERS_PER_LOT
        entry = FAB_ROUTE.operations[0]
        _append(
            rows,
            "lot_start",
            ready,
            lot_id=lot_id,
            product_id=product_id,
            route=FAB_ROUTE,
            operation=entry,
            wafer_count=qty,
        )
        for item in _fab_plan(index):
            if isinstance(item, Operation):
                ready = _run_operation(
                    rows=rows,
                    route=FAB_ROUTE,
                    operation=item,
                    lot_id=lot_id,
                    product_id=product_id,
                    wafer_count=qty,
                    ready=ready,
                    calendars=calendars,
                    rng=rng,
                    window_end=window_end,
                )
                continue
            if item.kind == "scrap":
                before = qty
                qty -= item.value
                when = ready + timedelta(minutes=1)
                _append(
                    rows,
                    "scrap",
                    when,
                    lot_id=lot_id,
                    product_id=product_id,
                    route=FAB_ROUTE,
                    operation=item.operation,
                    wafer_count=before,
                    scrap_qty=item.value,
                )
                ready = when + timedelta(minutes=2)
            elif item.kind == "hold":
                _append(
                    rows,
                    "hold_start",
                    ready,
                    lot_id=lot_id,
                    product_id=product_id,
                    route=FAB_ROUTE,
                    operation=item.operation,
                    wafer_count=qty,
                    hold_reason_code="engineering",
                )
                release = ready + timedelta(hours=item.value)
                _append(
                    rows,
                    "hold_end",
                    release,
                    lot_id=lot_id,
                    product_id=product_id,
                    route=FAB_ROUTE,
                    operation=item.operation,
                    wafer_count=qty,
                    hold_reason_code="engineering",
                )
                ready = release + timedelta(minutes=rng.randint(5, 20))
            elif item.kind == "rework":
                when = ready + timedelta(minutes=2)
                _append(
                    rows,
                    "rework",
                    when,
                    lot_id=lot_id,
                    product_id=product_id,
                    route=FAB_ROUTE,
                    operation=item.operation,
                    wafer_count=qty,
                    rework_qty=qty,
                )
                ready = when + timedelta(minutes=3)

        split_time = ready + timedelta(minutes=rng.randint(10, 40))
        first_qty = (qty + 1) // 2
        second_qty = qty - first_qty
        for side, child_qty in (("A", first_qty), ("B", second_qty)):
            child_id = f"{lot_id}_{side}"
            _append(
                rows,
                "split",
                split_time,
                lot_id=child_id,
                parent_lot_id=lot_id,
                product_id=product_id,
                route=FAB_ROUTE,
                operation=FAB_ROUTE.operation(130),
                wafer_count=child_qty,
            )
            sub_lots.append(
                {
                    "lot_id": child_id,
                    "product_id": product_id,
                    "qty": child_qty,
                    "ready": split_time + timedelta(minutes=rng.randint(5, 30)),
                    "fab_index": index,
                    "side": side,
                }
            )

    merged: list[dict[str, object]] = []
    for sub in sub_lots:
        child_id = str(sub["lot_id"])
        product_id = str(sub["product_id"])
        qty = int(sub["qty"])
        ready = sub["ready"]
        assert isinstance(ready, datetime)
        for seq in (10, 20):
            ready = _run_operation(
                rows=rows,
                route=OSAT_ROUTE,
                operation=OSAT_ROUTE.operation(seq),
                lot_id=child_id,
                product_id=product_id,
                wafer_count=qty,
                ready=ready,
                calendars=calendars,
                rng=rng,
                window_end=window_end,
            )
        if sub["fab_index"] == 1 or sub["fab_index"] == 2:
            if sub["side"] == "A":
                sub["ready"] = ready
                merged.append(sub)
                continue
        for seq in (30, 40):
            ready = _run_operation(
                rows=rows,
                route=OSAT_ROUTE,
                operation=OSAT_ROUTE.operation(seq),
                lot_id=child_id,
                product_id=product_id,
                wafer_count=qty,
                ready=ready,
                calendars=calendars,
                rng=rng,
                window_end=window_end,
            )
        _append(
            rows,
            "lot_complete",
            ready + timedelta(minutes=5),
            lot_id=child_id,
            product_id=product_id,
            route=OSAT_ROUTE,
            operation=OSAT_ROUTE.operation(40),
            wafer_count=qty,
        )

    merge_time = max(
        sub["ready"] for sub in merged  # type: ignore[type-var]
    ) + timedelta(minutes=15)
    merged_id = "LOT_PKG_MCM_001"
    merged_qty = sum(int(sub["qty"]) for sub in merged)
    for sub in merged:
        _append(
            rows,
            "merge",
            merge_time,
            lot_id=merged_id,
            parent_lot_id=str(sub["lot_id"]),
            product_id=str(sub["product_id"]),
            route=OSAT_ROUTE,
            operation=OSAT_ROUTE.operation(30),
            wafer_count=int(sub["qty"]),
        )
    ready = merge_time + timedelta(minutes=10)
    for seq in (30, 40):
        ready = _run_operation(
            rows=rows,
            route=OSAT_ROUTE,
            operation=OSAT_ROUTE.operation(seq),
            lot_id=merged_id,
            product_id="PROD_MEMS_MCM",
            wafer_count=merged_qty,
            ready=ready,
            calendars=calendars,
            rng=rng,
            window_end=window_end,
        )
    _append(
        rows,
        "lot_complete",
        ready + timedelta(minutes=5),
        lot_id=merged_id,
        product_id="PROD_MEMS_MCM",
        route=OSAT_ROUTE,
        operation=OSAT_ROUTE.operation(40),
        wafer_count=merged_qty,
    )

    rows.sort(
        key=lambda row: (
            row["event_time_utc"],
            row["lot_id"],
            row["event_type"],
        )
    )
    for index, row in enumerate(rows, start=1):
        row["event_id"] = f"RX_{index:06d}"

    equipment_rows: list[dict[str, str]] = []
    for tool in TOOLS:
        equipment_rows.extend(
            _tool_states(
                tool,
                calendars[tool.tool_id],
                window_start,
                window_end,
            )
        )
    equipment_rows.sort(
        key=lambda row: (
            row["tool_id"],
            row["event_time_utc"],
            row["state"],
        )
    )
    for index, row in enumerate(equipment_rows, start=1):
        row["event_id"] = f"EQ_{index:06d}"

    dataset = MesDataset(
        seed=seed,
        fab_lots=fab_lots,
        window_start=window_start,
        window_end=window_end,
        route_events=tuple(rows),
        equipment_events=tuple(equipment_rows),
    )
    validate_dataset(dataset)
    return dataset


_ROUTE_REQUIRED = (
    "event_id",
    "event_type",
    "event_time_utc",
    "lot_id",
    "product_id",
    "route_id",
    "route_revision",
    "operation_seq",
    "operation_id",
    "operation_type",
    "wafer_count",
)
_ROUTE_INTEGERS = (
    "operation_seq",
    "wafer_count",
    "scrap_qty",
    "rework_qty",
    "process_time_s",
    "queue_time_s",
    "setup_time_s",
)


def check_dataset(dataset: MesDataset) -> tuple[str, ...]:
    """Return every contract or genealogy problem found in a dataset."""
    errors: list[str] = []
    lot_ids: set[str] = set()
    events_by_lot: dict[str, list[dict[str, str]]] = {}
    event_ids: set[str] = set()

    for line, row in enumerate(dataset.route_events, start=2):
        label = f"route line {line}"
        if tuple(row) != ROUTE_COLUMNS:
            errors.append(f"{label}: column set or order is wrong")
        missing = [name for name in _ROUTE_REQUIRED if not row.get(name)]
        if missing:
            errors.append(
                f"{label}: missing {', '.join(missing)}"
            )
            continue
        if row["event_id"] in event_ids:
            errors.append(f"{label}: duplicate event_id {row['event_id']}")
        event_ids.add(row["event_id"])
        when = _parse_stamp(row["event_time_utc"])
        if when is None:
            errors.append(
                f"{label}: event_time_utc is not an offset timestamp"
            )
        elif not dataset.window_start <= when <= dataset.window_end:
            errors.append(f"{label}: event_time_utc is outside the window")
        for name in _ROUTE_INTEGERS:
            value = row.get(name, "")
            if value and not value.isdigit():
                errors.append(f"{label}: {name} is not a non-negative integer")
        event_type = row["event_type"]
        if event_type in {"process_start", "process_end"}:
            for name in ("tool_id", "tool_group_id", "tool_class"):
                if not row[name]:
                    errors.append(
                        f"{label}: {event_type} requires {name}"
                    )
        if event_type == "process_end" and not row["process_time_s"]:
            errors.append(f"{label}: process_end requires process_time_s")
        if event_type == "scrap" and not row["scrap_qty"]:
            errors.append(f"{label}: scrap requires scrap_qty")
        if event_type == "rework" and not row["rework_qty"]:
            errors.append(f"{label}: rework requires rework_qty")
        if event_type in {"split", "merge"}:
            if not row["parent_lot_id"]:
                errors.append(
                    f"{label}: {event_type} requires parent_lot_id"
                )
        elif row["parent_lot_id"]:
            errors.append(
                f"{label}: parent_lot_id is only valid on split or merge"
            )
        lot_ids.add(row["lot_id"])
        events_by_lot.setdefault(row["lot_id"], []).append(row)

    for row in dataset.route_events:
        if row["event_type"] not in {"split", "merge"}:
            continue
        if row["parent_lot_id"] and row["parent_lot_id"] not in lot_ids:
            errors.append(
                f"route: {row['parent_lot_id']} is not a known parent lot"
            )

    for lot_id, lot_rows in events_by_lot.items():
        times = [
            _parse_stamp(row["event_time_utc"]) for row in lot_rows
        ]
        for earlier, later in zip(times, times[1:]):
            if earlier is not None and later is not None and earlier > later:
                errors.append(f"route: {lot_id} events are out of order")

    tool_times: dict[str, list[datetime]] = {}
    for line, row in enumerate(dataset.equipment_events, start=2):
        label = f"equipment line {line}"
        if tuple(row) != EQUIPMENT_COLUMNS:
            errors.append(f"{label}: column set or order is wrong")
        if row["state"] not in EQUIPMENT_STATES:
            errors.append(f"{label}: unknown state {row['state']!r}")
        if not row["event_id"] or not row["tool_id"]:
            errors.append(f"{label}: missing event_id or tool_id")
        when = _parse_stamp(row["event_time_utc"])
        if when is None:
            errors.append(
                f"{label}: event_time_utc is not an offset timestamp"
            )
            continue
        if not dataset.window_start <= when <= dataset.window_end:
            errors.append(f"{label}: event_time_utc is outside the window")
        tool_times.setdefault(row["tool_id"], []).append(when)
        if row["state"] in {"productive", "setup"}:
            if row["lot_id"] not in lot_ids:
                errors.append(
                    f"{label}: {row['state']} references unknown lot "
                    f"{row['lot_id']!r}"
                )
        elif row["lot_id"]:
            errors.append(
                f"{label}: {row['state']} must not reference a lot"
            )

    expected_tools = {tool.tool_id for tool in TOOLS}
    if set(tool_times) != expected_tools:
        missing = sorted(expected_tools - set(tool_times))
        errors.append(f"equipment: no states for {', '.join(missing)}")
    for tool_id, times in tool_times.items():
        ordered = sorted(times)
        if ordered[0] != dataset.window_start:
            errors.append(
                f"equipment: {tool_id} does not start at the window boundary"
            )
        for earlier, later in zip(ordered, ordered[1:]):
            if earlier >= later:
                errors.append(
                    f"equipment: {tool_id} has duplicate or overlapping states"
                )
    return tuple(errors)


def validate_dataset(dataset: MesDataset) -> None:
    """Raise ``MesError`` when generated events do not meet the contract."""
    errors = check_dataset(dataset)
    if errors:
        raise MesError("\n".join(errors))

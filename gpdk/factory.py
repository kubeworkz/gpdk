"""F1 SimPy factory and ATP planning model for the G100 MCM line.

The route is a planning abstraction, not a foundry MES. Lots move through
workstations with finite tool capacity. Downtime is represented by an
availability factor from MTBF and MTTR, applied as extra effective processing
time rather than sampled random failures. Batched stations wait up to
``batch_wait_hours`` to form a load and then process what is available.

The model reports queue time, cycle time, WIP, throughput, tool utilization,
the bottleneck step and the factory operating cost per good package. It does
not model dispatch rules, reticles, reticle changes, operator constraints,
transport time or maintenance calendars.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, replace
from typing import Any, Mapping

import simpy

HOURS_PER_WEEK = 168.0
SECONDS_PER_HOUR = 3600.0
WEEKS_PER_YEAR = 52.0
DCF_YEARS = 5


def _number(raw: Mapping[str, Any], key: str, label: str) -> float:
    try:
        value = float(raw[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} needs numeric {key!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label}.{key} must be finite")
    return value


def _mappings(raw: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"factory model needs a non-empty {key!r} list")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"every {key!r} entry must be a mapping")
    return value


def _number_list(
    raw: Mapping[str, Any], key: str, label: str
) -> tuple[float, ...]:
    values = raw.get(key, [])
    if not isinstance(values, list):
        raise ValueError(f"{label}.{key} must be a list")
    return tuple(float(value) for value in values)


def _dcf_cash_flows(
    capex_usd: float,
    annual_cash_flow_usd: float,
    ramp: tuple[float, ...],
    terminal_value_pct_of_capex: float,
) -> tuple[float, ...]:
    terminal_value = capex_usd * terminal_value_pct_of_capex
    flows = [-capex_usd]
    for year, factor in enumerate(ramp, start=1):
        flow = annual_cash_flow_usd * factor
        if year == len(ramp):
            flow += terminal_value
        flows.append(flow)
    return tuple(flows)


def _dcf_npv(flows: tuple[float, ...], discount_rate: float) -> float:
    return sum(
        flow / (1.0 + discount_rate) ** year
        for year, flow in enumerate(flows)
    )


def _dcf_irr(flows: tuple[float, ...]) -> float | None:
    if len(flows) < 2 or sum(flows) <= 0:
        return None
    low = 0.0
    high = 1.0
    while _dcf_npv(flows, high) > 0:
        high *= 2.0
        if high > 1_000_000.0:
            return None
    for _ in range(200):
        mid = (low + high) / 2.0
        if _dcf_npv(flows, mid) > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _dcf_metrics(
    capex_usd: float,
    annual_cash_flow_usd: float,
    discount_rate: float,
    ramp: tuple[float, ...],
    terminal_value_pct_of_capex: float,
) -> tuple[float | None, float | None]:
    if capex_usd <= 0:
        return None, None
    flows = _dcf_cash_flows(
        capex_usd,
        annual_cash_flow_usd,
        ramp,
        terminal_value_pct_of_capex,
    )
    return _dcf_npv(flows, discount_rate), _dcf_irr(flows)


@dataclass(frozen=True)
class ToolGroupSpec:
    id: str
    tools: int
    mtbf_hours: float
    mttr_hours: float
    capex_usd_per_tool: float = 0.0
    depreciation_years: float = 5.0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("tool group id must not be empty")
        if self.tools <= 0:
            raise ValueError("tool group needs at least one tool")
        if self.mtbf_hours <= 0 or self.mttr_hours < 0:
            raise ValueError("tool group MTBF must be positive and MTTR non-negative")
        if (
            not math.isfinite(self.capex_usd_per_tool)
            or self.capex_usd_per_tool < 0
        ):
            raise ValueError("tool capex must be finite and non-negative")
        if (
            not math.isfinite(self.depreciation_years)
            or self.depreciation_years <= 0
        ):
            raise ValueError("depreciation years must be finite and positive")

    @property
    def availability(self) -> float:
        return self.mtbf_hours / (self.mtbf_hours + self.mttr_hours)

    @property
    def weekly_depreciation_usd(self) -> float:
        return self.capex_usd_per_tool / (
            self.depreciation_years * WEEKS_PER_YEAR
        )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ToolGroupSpec":
        return cls(
            id=str(raw["id"]),
            tools=int(raw["tools"]),
            mtbf_hours=_number(raw, "mtbf_hours", "tool group"),
            mttr_hours=_number(raw, "mttr_hours", "tool group"),
            capex_usd_per_tool=float(raw.get("capex_usd_per_tool", 0.0)),
            depreciation_years=float(raw.get("depreciation_years", 5.0)),
        )


@dataclass(frozen=True)
class RouteStep:
    name: str
    tool_group: str
    process_hours: float
    batch_size: int = 1
    setup_hours: float = 0.0
    batch_wait_hours: float = 0.0

    def __post_init__(self) -> None:
        if not self.name or not self.tool_group:
            raise ValueError("route step needs name and tool_group")
        if self.process_hours <= 0:
            raise ValueError("route process time must be positive")
        if self.batch_size <= 0:
            raise ValueError("route batch size must be positive")
        if self.setup_hours < 0 or self.batch_wait_hours < 0:
            raise ValueError("route setup and batch wait must be non-negative")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RouteStep":
        return cls(
            name=str(raw["name"]),
            tool_group=str(raw["tool_group"]),
            process_hours=_number(raw, "process_hours", "route step"),
            batch_size=int(raw.get("batch_size", 1)),
            setup_hours=float(raw.get("setup_hours", 0.0)),
            batch_wait_hours=float(raw.get("batch_wait_hours", 0.0)),
        )


@dataclass(frozen=True)
class WhatIf:
    id: str
    description: str
    wafer_starts_per_week: float | None = None
    mttr_scale: float = 1.0
    mtbf_scale: float = 1.0
    operating_cost_delta_usd_per_week: float = 0.0
    tool_count_overrides: tuple[tuple[str, int], ...] = ()
    roi_reference: str = "baseline"

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("what-if id must not be empty")
        if self.id == "baseline":
            raise ValueError("what-if id 'baseline' is reserved")
        if not self.roi_reference:
            raise ValueError("what-if ROI reference must not be empty")
        if self.roi_reference == self.id:
            raise ValueError("what-if ROI reference must be another case")
        if self.wafer_starts_per_week is not None and self.wafer_starts_per_week <= 0:
            raise ValueError("what-if wafer starts must be positive")
        if self.mttr_scale < 0 or self.mtbf_scale <= 0:
            raise ValueError("what-if downtime scales are invalid")
        if (
            not math.isfinite(self.operating_cost_delta_usd_per_week)
            or self.operating_cost_delta_usd_per_week < 0
        ):
            raise ValueError(
                "what-if operating cost delta must be finite and non-negative"
            )
        keys = [key for key, _tools in self.tool_count_overrides]
        if len(set(keys)) != len(keys):
            raise ValueError("what-if tool group overrides must be unique")
        for key, tools in self.tool_count_overrides:
            if not key:
                raise ValueError("what-if tool group id must not be empty")
            if tools <= 0:
                raise ValueError("what-if tool count must be positive")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "WhatIf":
        starts = raw.get("wafer_starts_per_week")
        overrides_raw = raw.get("tool_count_overrides", {})
        if not isinstance(overrides_raw, Mapping):
            raise ValueError("what-if tool_count_overrides must be a mapping")
        overrides: list[tuple[str, int]] = []
        for group_id, tools in overrides_raw.items():
            if not isinstance(group_id, str) or not group_id.strip():
                raise ValueError("what-if tool group id must not be empty")
            if isinstance(tools, bool) or not isinstance(tools, int) or tools <= 0:
                raise ValueError(
                    "what-if tool count overrides must be positive integers"
                )
            overrides.append((group_id.strip(), tools))
        return cls(
            id=str(raw["id"]),
            description=str(raw.get("description", "")).strip(),
            wafer_starts_per_week=(
                None if starts is None else float(starts)
            ),
            mttr_scale=float(raw.get("mttr_scale", 1.0)),
            mtbf_scale=float(raw.get("mtbf_scale", 1.0)),
            operating_cost_delta_usd_per_week=float(
                raw.get("operating_cost_delta_usd_per_week", 0.0)
            ),
            tool_count_overrides=tuple(overrides),
            roi_reference=str(raw.get("roi_reference", "baseline")).strip(),
        )


@dataclass(frozen=True)
class FactorySensitivitySpec:
    package_prices_usd: tuple[float, ...] = ()
    gross_margins_usd_per_good_package: tuple[float, ...] = ()
    discount_rates: tuple[float, ...] = ()
    terminal_value_pcts_of_capex: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not any(
            (
                self.package_prices_usd,
                self.gross_margins_usd_per_good_package,
                self.discount_rates,
                self.terminal_value_pcts_of_capex,
            )
        ):
            raise ValueError(
                "factory sensitivity needs at least one price, margin, "
                "discount rate or terminal value"
            )
        for label, values in (
            ("package prices", self.package_prices_usd),
            (
                "gross margins",
                self.gross_margins_usd_per_good_package,
            ),
            ("discount rates", self.discount_rates),
            ("terminal values", self.terminal_value_pcts_of_capex),
        ):
            if any(
                not math.isfinite(value) or value < 0 for value in values
            ):
                raise ValueError(
                    f"sensitivity {label} must be finite and non-negative"
                )
            if len(set(values)) != len(values):
                raise ValueError(f"sensitivity {label} must be unique")

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any]
    ) -> "FactorySensitivitySpec":
        if not isinstance(raw, Mapping):
            raise ValueError("factory sensitivity must be a mapping")
        return cls(
            package_prices_usd=_number_list(
                raw, "package_prices_usd", "sensitivity"
            ),
            gross_margins_usd_per_good_package=_number_list(
                raw,
                "gross_margins_usd_per_good_package",
                "sensitivity",
            ),
            discount_rates=_number_list(
                raw, "discount_rates", "sensitivity"
            ),
            terminal_value_pcts_of_capex=_number_list(
                raw, "terminal_value_pcts_of_capex", "sensitivity"
            ),
        )


@dataclass(frozen=True)
class FactoryAssumptions:
    id: str
    product: str
    process: str
    revision: str
    description: str
    wafer_starts_per_week: float
    simulation_weeks: float
    warmup_weeks: float
    wafers_per_lot: int
    operating_cost_usd_per_week: float
    package_option: str
    tool_groups: tuple[ToolGroupSpec, ...]
    fab_route: tuple[RouteStep, ...]
    atp_route: tuple[RouteStep, ...]
    what_if: tuple[WhatIf, ...]
    package_price_usd: float | None = None
    gross_margin_usd_per_good_package: float | None = None
    sensitivity: FactorySensitivitySpec | None = None
    discount_rate: float = 0.10
    dcf_ramp: tuple[float, ...] = (1.0,) * DCF_YEARS
    terminal_value_pct_of_capex: float = 0.0

    def __post_init__(self) -> None:
        if not self.id or not self.product or not self.process:
            raise ValueError("factory model needs id, product and process")
        if not self.package_option:
            raise ValueError("factory model needs a package option")
        if self.wafer_starts_per_week <= 0:
            raise ValueError("wafer starts must be positive")
        if self.simulation_weeks <= 0 or self.warmup_weeks < 0:
            raise ValueError("factory simulation and warm-up must be valid")
        if self.warmup_weeks >= self.simulation_weeks:
            raise ValueError("warm-up must be shorter than the simulation")
        if self.wafers_per_lot <= 0:
            raise ValueError("wafers per lot must be positive")
        if self.operating_cost_usd_per_week < 0:
            raise ValueError("operating cost must be non-negative")
        if not self.tool_groups or not self.fab_route or not self.atp_route:
            raise ValueError("factory model needs tools and routes")
        if len(self.what_if) < 2:
            raise ValueError("factory model needs at least two what-if cases")
        group_ids = [group.id for group in self.tool_groups]
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("tool group ids must be unique")
        groups = set(group_ids)
        for step in (*self.fab_route, *self.atp_route):
            if step.tool_group not in groups:
                raise ValueError(
                    f"route step {step.name!r} refers to unknown tool group "
                    f"{step.tool_group!r}"
                )
        step_names = [step.name for step in (*self.fab_route, *self.atp_route)]
        if len(set(step_names)) != len(step_names):
            raise ValueError("route step names must be unique")
        what_if_ids = [case.id for case in self.what_if]
        if len(set(what_if_ids)) != len(what_if_ids):
            raise ValueError("what-if ids must be unique")
        for case in self.what_if:
            if (
                case.roi_reference != "baseline"
                and case.roi_reference not in what_if_ids
            ):
                raise ValueError(
                    f"what-if {case.id!r} has unknown ROI reference "
                    f"{case.roi_reference!r}"
                )
            for group_id, _tools in case.tool_count_overrides:
                if group_id not in groups:
                    raise ValueError(
                        f"what-if {case.id!r} overrides unknown tool group "
                        f"{group_id!r}"
                    )
        if (
            self.package_price_usd is not None
            and self.gross_margin_usd_per_good_package is not None
        ):
            raise ValueError(
                "provide package_price_usd or "
                "gross_margin_usd_per_good_package, not both"
            )
        if self.package_price_usd is not None:
            if (
                not math.isfinite(self.package_price_usd)
                or self.package_price_usd < 0
            ):
                raise ValueError(
                    "package price must be finite and non-negative"
                )
        if self.gross_margin_usd_per_good_package is not None:
            if not math.isfinite(self.gross_margin_usd_per_good_package):
                raise ValueError("gross margin must be finite")
        if (
            not math.isfinite(self.discount_rate)
            or self.discount_rate < 0
        ):
            raise ValueError(
                "discount rate must be finite and non-negative"
            )
        if len(self.dcf_ramp) != DCF_YEARS:
            raise ValueError(f"dcf ramp must have {DCF_YEARS} entries")
        if any(
            not math.isfinite(factor) or factor < 0.0 or factor > 1.0
            for factor in self.dcf_ramp
        ):
            raise ValueError("dcf ramp factors must be between 0 and 1")
        if (
            not math.isfinite(self.terminal_value_pct_of_capex)
            or self.terminal_value_pct_of_capex < 0.0
            or self.terminal_value_pct_of_capex > 1.0
        ):
            raise ValueError(
                "terminal value percentage must be between 0 and 1"
            )
        if (
            self.sensitivity is not None
            and (
                self.sensitivity.discount_rates
                or self.sensitivity.terminal_value_pcts_of_capex
            )
            and self.package_price_usd is None
            and self.gross_margin_usd_per_good_package is None
        ):
            raise ValueError(
                "discount-rate and terminal-value sensitivity need a base "
                "package price or gross margin"
            )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "FactoryAssumptions":
        return cls(
            id=str(raw["id"]),
            product=str(raw["product"]),
            process=str(raw["process"]),
            revision=str(raw.get("revision", "0.1.0")),
            description=str(raw.get("description", "")).strip(),
            wafer_starts_per_week=_number(raw, "wafer_starts_per_week", "factory"),
            simulation_weeks=_number(raw, "simulation_weeks", "factory"),
            warmup_weeks=_number(raw, "warmup_weeks", "factory"),
            wafers_per_lot=int(raw["wafers_per_lot"]),
            operating_cost_usd_per_week=_number(
                raw, "operating_cost_usd_per_week", "factory"
            ),
            package_option=str(raw["package_option"]),
            tool_groups=tuple(
                ToolGroupSpec.from_mapping(item)
                for item in _mappings(raw, "tool_groups")
            ),
            fab_route=tuple(
                RouteStep.from_mapping(item)
                for item in _mappings(raw, "fab_route")
            ),
            atp_route=tuple(
                RouteStep.from_mapping(item)
                for item in _mappings(raw, "atp_route")
            ),
            what_if=tuple(
                WhatIf.from_mapping(item)
                for item in _mappings(raw, "what_if")
            ),
            package_price_usd=(
                None
                if raw.get("package_price_usd") is None
                else float(raw["package_price_usd"])
            ),
            gross_margin_usd_per_good_package=(
                None
                if raw.get("gross_margin_usd_per_good_package") is None
                else float(raw["gross_margin_usd_per_good_package"])
            ),
            sensitivity=(
                None
                if raw.get("sensitivity") is None
                else FactorySensitivitySpec.from_mapping(raw["sensitivity"])
            ),
            discount_rate=float(raw.get("discount_rate", 0.10)),
            dcf_ramp=(
                (1.0,) * DCF_YEARS
                if raw.get("dcf_ramp") is None
                else _number_list(raw, "dcf_ramp", "factory")
            ),
            terminal_value_pct_of_capex=float(
                raw.get("terminal_value_pct_of_capex", 0.0)
            ),
        )


@dataclass(frozen=True)
class FactoryCaseResult:
    id: str
    description: str
    wafer_starts_per_week: float
    lots: int
    wafers: int
    cycle_time_hours: float
    queue_time_hours: float
    wip_lots: float
    throughput_wafers_per_week: float
    good_packages_per_week: float
    cost_per_good_package_usd: float
    tool_capex_usd: float
    depreciation_usd_per_week: float
    depreciation_per_good_package_usd: float
    bottleneck_step: str
    bottleneck_step_queue_hours: float
    bottleneck_tool_group: str
    bottleneck_utilization: float
    operating_cost_usd_per_week: float
    tool_counts: Mapping[str, int]
    tool_utilization: Mapping[str, float]
    step_queue_hours: Mapping[str, float]
    incremental_capex_usd: float = 0.0
    incremental_annual_cash_flow_usd: float = 0.0
    incremental_annual_net_income_usd: float = 0.0
    payback_years: float | None = None
    roi: float | None = None
    roi_reference: str = "baseline"
    npv_usd: float | None = None
    irr: float | None = None


@dataclass(frozen=True)
class FactorySensitivityPoint:
    id: str
    case_id: str
    basis: str
    assumption_usd: float
    package_price_usd: float | None
    gross_margin_usd_per_good_package: float
    incremental_capex_usd: float
    incremental_annual_cash_flow_usd: float
    incremental_annual_net_income_usd: float
    payback_years: float | None
    roi: float | None
    npv_usd: float | None
    irr: float | None
    roi_reference: str


@dataclass(frozen=True)
class FactoryDiscountRatePoint:
    id: str
    case_id: str
    discount_rate: float
    incremental_capex_usd: float
    incremental_annual_cash_flow_usd: float
    npv_usd: float
    irr: float | None
    roi_reference: str


@dataclass(frozen=True)
class FactoryTerminalValuePoint:
    id: str
    case_id: str
    terminal_value_pct_of_capex: float
    terminal_value_usd: float
    incremental_capex_usd: float
    incremental_annual_cash_flow_usd: float
    npv_usd: float
    irr: float | None
    roi_reference: str


@dataclass(frozen=True)
class FactoryStudy:
    baseline: FactoryCaseResult
    cases: tuple[FactoryCaseResult, ...]
    sensitivity: tuple[FactorySensitivityPoint, ...] = ()
    discount_rate_sensitivity: tuple[FactoryDiscountRatePoint, ...] = ()
    terminal_value_sensitivity: tuple[FactoryTerminalValuePoint, ...] = ()

    def all_cases(self) -> tuple[FactoryCaseResult, ...]:
        return (self.baseline, *self.cases)


@dataclass
class _Lot:
    index: int
    release: float
    completion: float = 0.0
    queue_hours: float = 0.0


class _Station:
    """A route step with a queue, batch formation and a shared tool group."""

    def __init__(
        self,
        env: simpy.Environment,
        step: RouteStep,
        resource: simpy.Resource,
        availability: float,
        analysis_start: float,
        group_busy: dict[str, float],
        step_queue: dict[str, float],
        step_visits: dict[str, int],
    ) -> None:
        self.env = env
        self.step = step
        self.resource = resource
        self.availability = availability
        self.analysis_start = analysis_start
        self.group_busy = group_busy
        self.step_queue = step_queue
        self.step_visits = step_visits
        self.queue: simpy.Store = simpy.Store(env)
        self.process = env.process(self._dispatch())

    def enqueue(self, lot: _Lot) -> simpy.Event:
        lot.step_enter = self.env.now
        done = self.env.event()
        self.queue.put((lot, done))
        return done

    def _dispatch(self):
        while True:
            batch = [(yield self.queue.get())]
            if self.step.batch_size > 1:
                while len(batch) < self.step.batch_size and self.queue.items:
                    batch.append((yield self.queue.get()))
                if (
                    len(batch) < self.step.batch_size
                    and self.step.batch_wait_hours > 0
                ):
                    yield self.env.timeout(self.step.batch_wait_hours)
                    while len(batch) < self.step.batch_size and self.queue.items:
                        batch.append((yield self.queue.get()))
            self.env.process(self._run_batch(batch))

    def _run_batch(self, batch):
        with self.resource.request() as request:
            yield request
            start = self.env.now
            if start >= self.analysis_start:
                for lot, _done in batch:
                    self.step_queue[self.step.name] = (
                        self.step_queue.get(self.step.name, 0.0)
                        + (start - lot.step_enter)
                    )
                    self.step_visits[self.step.name] = (
                        self.step_visits.get(self.step.name, 0) + 1
                    )
            for lot, _done in batch:
                lot.queue_hours += start - lot.step_enter
            duration = (
                self.step.setup_hours + self.step.process_hours
            ) / self.availability
            yield self.env.timeout(duration)
            end = self.env.now
            busy_start = max(start, self.analysis_start)
            if end > busy_start:
                self.group_busy[self.step.tool_group] = (
                    self.group_busy.get(self.step.tool_group, 0.0)
                    + (end - busy_start)
                )
            for _lot, done in batch:
                if not done.triggered:
                    done.succeed()


def simulate_factory_case(
    assumptions: FactoryAssumptions,
    *,
    case_id: str,
    description: str,
    wafer_starts_per_week: float,
    good_packages_per_wafer: float,
    package_cost_per_good_package_usd: float,
    mttr_scale: float = 1.0,
    mtbf_scale: float = 1.0,
    operating_cost_delta_usd_per_week: float = 0.0,
    tool_count_overrides: Mapping[str, int] | None = None,
    roi_reference: str = "baseline",
) -> FactoryCaseResult:
    """Run one deterministic SimPy factory/ATP operating point."""
    if wafer_starts_per_week <= 0:
        raise ValueError("wafer starts must be positive")
    if good_packages_per_wafer <= 0:
        raise ValueError("good packages per wafer must be positive")
    if package_cost_per_good_package_usd < 0:
        raise ValueError("package cost must be non-negative")
    if mttr_scale < 0 or mtbf_scale <= 0:
        raise ValueError("downtime scales are invalid")
    if (
        not math.isfinite(operating_cost_delta_usd_per_week)
        or operating_cost_delta_usd_per_week < 0
    ):
        raise ValueError(
            "operating cost delta must be finite and non-negative"
        )
    operating_cost = (
        assumptions.operating_cost_usd_per_week
        + operating_cost_delta_usd_per_week
    )

    env = simpy.Environment()
    warmup_hours = assumptions.warmup_weeks * HOURS_PER_WEEK
    lot_starts_per_week = wafer_starts_per_week / assumptions.wafers_per_lot
    lot_count = max(
        1,
        int(math.floor(assumptions.simulation_weeks * lot_starts_per_week)),
    )
    release_interval = HOURS_PER_WEEK / lot_starts_per_week

    tool_counts = {group.id: group.tools for group in assumptions.tool_groups}
    for group_id, tools in (tool_count_overrides or {}).items():
        if group_id not in tool_counts:
            raise ValueError(f"unknown tool group {group_id!r}")
        if tools <= 0:
            raise ValueError("tool count override must be positive")
        tool_counts[group_id] = tools

    resources: dict[str, simpy.Resource] = {}
    availability: dict[str, float] = {}
    for group in assumptions.tool_groups:
        resources[group.id] = simpy.Resource(
            env, capacity=tool_counts[group.id]
        )
        mtbf = group.mtbf_hours * mtbf_scale
        mttr = group.mttr_hours * mttr_scale
        availability[group.id] = mtbf / (mtbf + mttr)

    group_busy: dict[str, float] = {}
    step_queue: dict[str, float] = {}
    step_visits: dict[str, int] = {}
    stations = [
        _Station(
            env,
            step,
            resources[step.tool_group],
            availability[step.tool_group],
            warmup_hours,
            group_busy,
            step_queue,
            step_visits,
        )
        for step in (*assumptions.fab_route, *assumptions.atp_route)
    ]

    active: set[int] = set()
    wip_samples: list[float] = []
    completed: list[_Lot] = []
    all_done = env.event()

    def sample_wip():
        while True:
            yield env.timeout(6.0)
            if env.now >= warmup_hours:
                wip_samples.append(float(len(active)))

    def route_lot(lot: _Lot):
        active.add(lot.index)
        for station in stations:
            yield station.enqueue(lot)
        lot.completion = env.now
        active.discard(lot.index)
        completed.append(lot)
        if len(completed) == lot_count and not all_done.triggered:
            all_done.succeed()

    def release_lots():
        for index in range(lot_count):
            if index:
                yield env.timeout(release_interval)
            lot = _Lot(index, env.now)
            env.process(route_lot(lot))

    env.process(sample_wip())
    env.process(release_lots())
    env.run(until=all_done)

    analyzed = [lot for lot in completed if lot.release >= warmup_hours]
    if not analyzed:
        raise ValueError("simulation produced no lots after warm-up")
    cycle = statistics.fmean(
        lot.completion - lot.release for lot in analyzed
    )
    analysis_end = max(lot.completion for lot in analyzed)
    analysis_hours = max(analysis_end - warmup_hours, HOURS_PER_WEEK)
    queue = statistics.fmean(lot.queue_hours for lot in analyzed)
    wip = statistics.fmean(wip_samples) if wip_samples else float(len(analyzed))
    # Measure throughput between pipeline fill and drain so a growing backlog
    # reports the line's capacity, not the release schedule.
    window_start = warmup_hours + cycle
    window_end = analysis_end - cycle
    steady = [
        lot
        for lot in completed
        if window_start <= lot.completion <= window_end
    ]
    if steady and window_end - window_start >= HOURS_PER_WEEK:
        throughput = len(steady) * assumptions.wafers_per_lot / (
            (window_end - window_start) / HOURS_PER_WEEK
        )
    else:
        throughput = len(analyzed) * assumptions.wafers_per_lot / (
            analysis_hours / HOURS_PER_WEEK
        )
    good_packages = throughput * good_packages_per_wafer
    tool_capex = sum(
        tool_counts[group.id] * group.capex_usd_per_tool
        for group in assumptions.tool_groups
    )
    depreciation = sum(
        tool_counts[group.id] * group.weekly_depreciation_usd
        for group in assumptions.tool_groups
    )
    cost = package_cost_per_good_package_usd + (
        operating_cost + depreciation
    ) / good_packages
    depreciation_per_package = depreciation / good_packages
    utilizations = {
        group.id: min(
            1.0,
            group_busy.get(group.id, 0.0)
            / (tool_counts[group.id] * analysis_hours),
        )
        for group in assumptions.tool_groups
    }
    queue_averages = {
        name: step_queue[name] / step_visits[name]
        for name in step_queue
        if step_visits.get(name, 0)
    }
    bottleneck_group = max(
        utilizations,
        key=lambda name: utilizations[name],
        default="none",
    )
    bottleneck_steps = [
        step.name
        for step in (*assumptions.fab_route, *assumptions.atp_route)
        if step.tool_group == bottleneck_group
    ]
    bottleneck_step = max(
        bottleneck_steps,
        key=lambda name: queue_averages.get(name, 0.0),
        default="none",
    )
    return FactoryCaseResult(
        id=case_id,
        description=description,
        wafer_starts_per_week=wafer_starts_per_week,
        lots=lot_count,
        wafers=lot_count * assumptions.wafers_per_lot,
        cycle_time_hours=cycle,
        queue_time_hours=queue,
        wip_lots=wip,
        throughput_wafers_per_week=throughput,
        good_packages_per_week=good_packages,
        cost_per_good_package_usd=cost,
        tool_capex_usd=tool_capex,
        depreciation_usd_per_week=depreciation,
        depreciation_per_good_package_usd=depreciation_per_package,
        bottleneck_step=bottleneck_step,
        bottleneck_step_queue_hours=queue_averages.get(bottleneck_step, 0.0),
        bottleneck_tool_group=bottleneck_group,
        bottleneck_utilization=utilizations.get(bottleneck_group, 0.0),
        operating_cost_usd_per_week=operating_cost,
        tool_counts=tool_counts,
        tool_utilization=utilizations,
        step_queue_hours=queue_averages,
        roi_reference=roi_reference,
    )


def simulate_factory(
    assumptions: FactoryAssumptions,
    *,
    good_packages_per_wafer: float,
    package_cost_per_good_package_usd: float,
) -> FactoryStudy:
    """Run the baseline and every declared what-if case."""
    baseline = simulate_factory_case(
        assumptions,
        case_id="baseline",
        description="Baseline route, tool count and downtime",
        wafer_starts_per_week=assumptions.wafer_starts_per_week,
        good_packages_per_wafer=good_packages_per_wafer,
        package_cost_per_good_package_usd=package_cost_per_good_package_usd,
    )
    cases = tuple(
        simulate_factory_case(
            assumptions,
            case_id=case.id,
            description=case.description,
            wafer_starts_per_week=(
                assumptions.wafer_starts_per_week
                if case.wafer_starts_per_week is None
                else case.wafer_starts_per_week
            ),
            good_packages_per_wafer=good_packages_per_wafer,
            package_cost_per_good_package_usd=package_cost_per_good_package_usd,
            mttr_scale=case.mttr_scale,
            mtbf_scale=case.mtbf_scale,
            operating_cost_delta_usd_per_week=(
                case.operating_cost_delta_usd_per_week
            ),
            tool_count_overrides=dict(case.tool_count_overrides),
            roi_reference=case.roi_reference,
        )
        for case in assumptions.what_if
    )

    margin = assumptions.gross_margin_usd_per_good_package
    if margin is None and assumptions.package_price_usd is not None:
        margin = (
            assumptions.package_price_usd - package_cost_per_good_package_usd
        )

    by_id = {baseline.id: baseline}
    by_id.update({case.id: case for case in cases})

    def annual_cash_flow(
        case: FactoryCaseResult, case_margin: float
    ) -> float:
        return (
            case.good_packages_per_week * case_margin
            - case.operating_cost_usd_per_week
        ) * WEEKS_PER_YEAR

    def investment(
        case: FactoryCaseResult, case_margin: float
    ) -> tuple[
        float,
        float,
        float,
        float | None,
        float | None,
    ]:
        reference = by_id[case.roi_reference]
        cash = annual_cash_flow(case, case_margin)
        net = cash - case.depreciation_usd_per_week * WEEKS_PER_YEAR
        reference_cash = annual_cash_flow(reference, case_margin)
        reference_net = reference_cash - (
            reference.depreciation_usd_per_week * WEEKS_PER_YEAR
        )
        capex_delta = case.tool_capex_usd - reference.tool_capex_usd
        cash_delta = cash - reference_cash
        net_delta = net - reference_net
        payback = (
            capex_delta / cash_delta
            if capex_delta > 0 and cash_delta > 0
            else None
        )
        roi = net_delta / capex_delta if capex_delta > 0 else None
        return capex_delta, cash_delta, net_delta, payback, roi

    if margin is not None:

        def with_investment(case: FactoryCaseResult) -> FactoryCaseResult:
            capex_delta, cash_delta, net_delta, payback, roi = investment(
                case, margin
            )
            npv, irr = _dcf_metrics(
                capex_delta,
                cash_delta,
                assumptions.discount_rate,
                assumptions.dcf_ramp,
                assumptions.terminal_value_pct_of_capex,
            )
            return replace(
                case,
                incremental_capex_usd=capex_delta,
                incremental_annual_cash_flow_usd=cash_delta,
                incremental_annual_net_income_usd=net_delta,
                payback_years=payback,
                roi=roi,
                npv_usd=npv,
                irr=irr,
            )

        baseline = with_investment(baseline)
        cases = tuple(with_investment(case) for case in cases)

    sensitivity_points: list[FactorySensitivityPoint] = []
    if assumptions.sensitivity is not None:
        for case in cases:
            reference = by_id[case.roi_reference]
            if case.tool_capex_usd <= reference.tool_capex_usd:
                continue
            for price in assumptions.sensitivity.package_prices_usd:
                point_margin = (
                    price - package_cost_per_good_package_usd
                )
                capex, cash, net, payback, roi = investment(
                    case, point_margin
                )
                npv, irr = _dcf_metrics(
                    capex,
                    cash,
                    assumptions.discount_rate,
                    assumptions.dcf_ramp,
                    assumptions.terminal_value_pct_of_capex,
                )
                sensitivity_points.append(
                    FactorySensitivityPoint(
                        id=f"{case.id}:price:{price:g}",
                        case_id=case.id,
                        basis="package_price",
                        assumption_usd=price,
                        package_price_usd=price,
                        gross_margin_usd_per_good_package=point_margin,
                        incremental_capex_usd=capex,
                        incremental_annual_cash_flow_usd=cash,
                        incremental_annual_net_income_usd=net,
                        payback_years=payback,
                        roi=roi,
                        npv_usd=npv,
                        irr=irr,
                        roi_reference=case.roi_reference,
                    )
                )
            for point_margin in (
                assumptions.sensitivity.gross_margins_usd_per_good_package
            ):
                capex, cash, net, payback, roi = investment(
                    case, point_margin
                )
                npv, irr = _dcf_metrics(
                    capex,
                    cash,
                    assumptions.discount_rate,
                    assumptions.dcf_ramp,
                    assumptions.terminal_value_pct_of_capex,
                )
                sensitivity_points.append(
                    FactorySensitivityPoint(
                        id=f"{case.id}:margin:{point_margin:g}",
                        case_id=case.id,
                        basis="gross_margin",
                        assumption_usd=point_margin,
                        package_price_usd=None,
                        gross_margin_usd_per_good_package=point_margin,
                        incremental_capex_usd=capex,
                        incremental_annual_cash_flow_usd=cash,
                        incremental_annual_net_income_usd=net,
                        payback_years=payback,
                        roi=roi,
                        npv_usd=npv,
                        irr=irr,
                        roi_reference=case.roi_reference,
                    )
                )

    discount_rate_points: list[FactoryDiscountRatePoint] = []
    if assumptions.sensitivity is not None and margin is not None:
        for case in cases:
            reference = by_id[case.roi_reference]
            if case.tool_capex_usd <= reference.tool_capex_usd:
                continue
            capex, cash, _net, _payback, _roi = investment(case, margin)
            flows = _dcf_cash_flows(
                capex,
                cash,
                assumptions.dcf_ramp,
                assumptions.terminal_value_pct_of_capex,
            )
            irr = _dcf_irr(flows)
            for rate in assumptions.sensitivity.discount_rates:
                discount_rate_points.append(
                    FactoryDiscountRatePoint(
                        id=f"{case.id}:discount:{rate:g}",
                        case_id=case.id,
                        discount_rate=rate,
                        incremental_capex_usd=capex,
                        incremental_annual_cash_flow_usd=cash,
                        npv_usd=_dcf_npv(flows, rate),
                        irr=irr,
                        roi_reference=case.roi_reference,
                    )
                )

    terminal_value_points: list[FactoryTerminalValuePoint] = []
    if assumptions.sensitivity is not None and margin is not None:
        for case in cases:
            reference = by_id[case.roi_reference]
            if case.tool_capex_usd <= reference.tool_capex_usd:
                continue
            capex, cash, _net, _payback, _roi = investment(case, margin)
            for percent in (
                assumptions.sensitivity.terminal_value_pcts_of_capex
            ):
                flows = _dcf_cash_flows(
                    capex, cash, assumptions.dcf_ramp, percent
                )
                terminal_value_points.append(
                    FactoryTerminalValuePoint(
                        id=f"{case.id}:terminal:{percent:g}",
                        case_id=case.id,
                        terminal_value_pct_of_capex=percent,
                        terminal_value_usd=capex * percent,
                        incremental_capex_usd=capex,
                        incremental_annual_cash_flow_usd=cash,
                        npv_usd=_dcf_npv(
                            flows, assumptions.discount_rate
                        ),
                        irr=_dcf_irr(flows),
                        roi_reference=case.roi_reference,
                    )
                )

    return FactoryStudy(
        baseline=baseline,
        cases=cases,
        sensitivity=tuple(sensitivity_points),
        discount_rate_sensitivity=tuple(discount_rate_points),
        terminal_value_sensitivity=tuple(terminal_value_points),
    )

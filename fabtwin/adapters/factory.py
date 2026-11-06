"""F1 SimPy factory and ATP discrete-event adapter.

The factory route consumes the G100 die area, the Phase 3 MCM yield/package
model and the Phase 4 route assumptions. Package cost and good packages per
wafer come from the selected Phase 3 package option; factory operating cost is
added per good package produced by the simulated line.
"""

from __future__ import annotations

from typing import Callable

import yaml

from gpdk.block import load_chip
from gpdk.dtco import best_step, build_steps
from gpdk.factory import (
    DCF_YEARS,
    HOURS_PER_WEEK,
    SECONDS_PER_HOUR,
    FactoryAssumptions,
    FactoryCaseResult,
    simulate_factory,
)
from gpdk.mcm import McmYieldAssumptions, simulate_mcm_yield
from gpdk.tech import load_tech

from ..errors import EngineError
from ..model import EngineResult, InputFile, Observation
from ..provenance import display_path
from ..scenario import Scenario
from .pta import _read_mapping, _slug

_MODEL_VERSION_PREFIX = "factory-atp"
_CASE_METRICS: dict[
    str, tuple[str, Callable[[FactoryCaseResult], float]]
] = {
    "wafer_starts_per_s": (
        "1/s",
        lambda case: case.wafer_starts_per_week
        / (HOURS_PER_WEEK * SECONDS_PER_HOUR),
    ),
    "cycle_time_s": (
        "s",
        lambda case: case.cycle_time_hours * SECONDS_PER_HOUR,
    ),
    "queue_time_s": (
        "s",
        lambda case: case.queue_time_hours * SECONDS_PER_HOUR,
    ),
    "wip_lots": ("lot", lambda case: case.wip_lots),
    "throughput_wafers_per_s": (
        "1/s",
        lambda case: case.throughput_wafers_per_week
        / (HOURS_PER_WEEK * SECONDS_PER_HOUR),
    ),
    "good_packages_per_s": (
        "1/s",
        lambda case: case.good_packages_per_week
        / (HOURS_PER_WEEK * SECONDS_PER_HOUR),
    ),
    "cost_per_good_package_usd": (
        "USD",
        lambda case: case.cost_per_good_package_usd,
    ),
    "tool_capex_usd": ("USD", lambda case: case.tool_capex_usd),
    "depreciation_usd_per_week": (
        "USD/week",
        lambda case: case.depreciation_usd_per_week,
    ),
    "depreciation_per_good_package_usd": (
        "USD",
        lambda case: case.depreciation_per_good_package_usd,
    ),
    "bottleneck_step_queue_s": (
        "s",
        lambda case: case.bottleneck_step_queue_hours * SECONDS_PER_HOUR,
    ),
    "bottleneck_tool_utilization": (
        "1",
        lambda case: case.bottleneck_utilization,
    ),
}
_INVESTMENT_METRICS: dict[
    str, tuple[str, Callable[[FactoryCaseResult], float | None]]
] = {
    "incremental_capex_usd": (
        "USD",
        lambda case: case.incremental_capex_usd,
    ),
    "incremental_annual_cash_flow_usd": (
        "USD",
        lambda case: case.incremental_annual_cash_flow_usd,
    ),
    "incremental_annual_net_income_usd": (
        "USD",
        lambda case: case.incremental_annual_net_income_usd,
    ),
    "payback_years": ("year", lambda case: case.payback_years),
    "roi": ("1", lambda case: case.roi),
    "npv_usd": ("USD", lambda case: case.npv_usd),
    "irr": ("1", lambda case: case.irr),
}
_EXTRA_METRICS = frozenset({"step_queue_time_s", "tool_utilization"})
SUPPORTED_METRICS = frozenset(
    {*_CASE_METRICS, *_INVESTMENT_METRICS, *_EXTRA_METRICS}
)


def _load_model_inputs(scenario: Scenario):
    cfg = load_chip(scenario.chip_path)
    tech = load_tech(cfg.tech_file)
    if scenario.factory_path is None:
        raise ValueError("factory scenario requires inputs.factory")
    if scenario.package_path is None:
        raise ValueError("factory scenario requires inputs.package")
    if scenario.yield_path is None:
        raise ValueError("factory scenario requires inputs.yield")
    factory = FactoryAssumptions.from_mapping(
        _read_mapping(scenario.factory_path, "factory model")
    )
    yield_assumptions = McmYieldAssumptions.from_mapping(
        _read_mapping(scenario.yield_path, "MCM yield model")
    )
    estimate = best_step(build_steps(cfg)).iso
    simulation = simulate_mcm_yield(yield_assumptions, estimate.die_area_mm2)
    option = next(
        (
            item
            for item in simulation.options
            if item.option.id == factory.package_option
        ),
        None,
    )
    if option is None:
        available = ", ".join(item.option.id for item in simulation.options)
        raise ValueError(
            f"unknown package option {factory.package_option!r}; "
            f"available: {available}"
        )
    return cfg, tech, factory, simulation, option


class FactoryAtpEngine:
    """F1 deterministic SimPy factory and ATP planning engine."""

    name = "factory_atp"
    version = "0.1.0"
    fidelity = "F1"

    def validate(self, scenario: Scenario) -> list[str]:
        errors: list[str] = []
        if scenario.samples != 1:
            errors.append("factory_atp is deterministic; samples must be 1")
        unknown = sorted(set(scenario.outputs) - SUPPORTED_METRICS)
        if unknown:
            errors.append(
                "unsupported factory metric(s): " + ", ".join(unknown)
            )
        try:
            cfg, tech, factory, simulation, _option = _load_model_inputs(
                scenario
            )
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"cannot load factory inputs: {exc}")
            return errors
        if scenario.product != _slug(cfg.name):
            errors.append(
                f"product {scenario.product!r} does not match chip "
                f"{cfg.name!r} (expected {_slug(cfg.name)!r})"
            )
        expected_process = f"{_slug(tech.name)}@{tech.revision}"
        if scenario.process.lower() != expected_process:
            errors.append(
                f"process {scenario.process!r} does not match "
                f"{tech.name} revision {tech.revision} "
                f"(expected {expected_process!r})"
            )
        if factory.product != scenario.product:
            errors.append(
                f"factory product {factory.product!r} does not match "
                f"scenario product {scenario.product!r}"
            )
        if factory.process.lower() != scenario.process.lower():
            errors.append(
                f"factory process {factory.process!r} does not match "
                f"scenario process {scenario.process!r}"
            )
        investment_outputs = {
            "incremental_capex_usd",
            "incremental_annual_cash_flow_usd",
            "incremental_annual_net_income_usd",
            "payback_years",
            "roi",
        } & set(scenario.outputs)
        has_economics = (
            factory.package_price_usd is not None
            or factory.gross_margin_usd_per_good_package is not None
            or factory.sensitivity is not None
        )
        if investment_outputs and not has_economics:
            errors.append(
                "payback/ROI metrics require package_price_usd, "
                "gross_margin_usd_per_good_package or a sensitivity block"
            )
        if simulation.g100_gross_dies_per_wafer <= 0:
            errors.append("G100 does not fit on the wafer")
        return errors

    def run(self, scenario: Scenario) -> EngineResult:
        errors = self.validate(scenario)
        if errors:
            raise EngineError("; ".join(errors))
        cfg, tech, factory, simulation, option = _load_model_inputs(scenario)
        study = simulate_factory(
            factory,
            good_packages_per_wafer=option.good_packages_per_g100_wafer,
            package_cost_per_good_package_usd=(
                option.cost_per_good_package_usd
            ),
        )
        source = display_path(scenario.factory_path)
        model_version = f"{_MODEL_VERSION_PREFIX}@{factory.revision}"
        gross_margin = factory.gross_margin_usd_per_good_package
        if gross_margin is None and factory.package_price_usd is not None:
            gross_margin = (
                factory.package_price_usd
                - option.cost_per_good_package_usd
            )
        observations: list[Observation] = []
        for case in study.all_cases():
            for metric in scenario.outputs:
                if metric not in _CASE_METRICS:
                    continue
                unit, projector = _CASE_METRICS[metric]
                observations.append(
                    Observation(
                        entity_type="factory_case",
                        entity_id=case.id,
                        metric=metric,
                        value=float(projector(case)),
                        unit=unit,
                        uncertainty=None,
                        evidence_class="assumed",
                        source_artifact=source,
                        model_version=model_version,
                    )
                )
            if case.incremental_capex_usd > 0:
                for metric in scenario.outputs:
                    if metric not in _INVESTMENT_METRICS:
                        continue
                    unit, projector = _INVESTMENT_METRICS[metric]
                    value = projector(case)
                    if value is None:
                        continue
                    observations.append(
                        Observation(
                            entity_type="factory_case",
                            entity_id=case.id,
                            metric=metric,
                            value=float(value),
                            unit=unit,
                            uncertainty=None,
                            evidence_class="assumed",
                            source_artifact=source,
                            model_version=model_version,
                        )
                    )
            if "step_queue_time_s" in scenario.outputs:
                for step in sorted(case.step_queue_hours):
                    observations.append(
                        Observation(
                            entity_type="route_step",
                            entity_id=f"{case.id}:{step}",
                            metric="step_queue_time_s",
                            value=(
                                case.step_queue_hours[step]
                                * SECONDS_PER_HOUR
                            ),
                            unit="s",
                            uncertainty=None,
                            evidence_class="assumed",
                            source_artifact=source,
                            model_version=model_version,
                        )
                    )
            if "tool_utilization" in scenario.outputs:
                for group in sorted(case.tool_utilization):
                    observations.append(
                        Observation(
                            entity_type="tool_group",
                            entity_id=f"{case.id}:{group}",
                            metric="tool_utilization",
                            value=float(case.tool_utilization[group]),
                            unit="1",
                            uncertainty=None,
                            evidence_class="assumed",
                            source_artifact=source,
                            model_version=model_version,
                        )
                    )
        for point in study.sensitivity:
            for metric, value, unit in (
                ("payback_years", point.payback_years, "year"),
                ("roi", point.roi, "1"),
                ("npv_usd", point.npv_usd, "USD"),
                ("irr", point.irr, "1"),
            ):
                if metric not in scenario.outputs or value is None:
                    continue
                observations.append(
                    Observation(
                        entity_type="factory_sensitivity",
                        entity_id=point.id,
                        metric=metric,
                        value=float(value),
                        unit=unit,
                        uncertainty=None,
                        evidence_class="assumed",
                        source_artifact=source,
                        model_version=model_version,
                    )
                )
        for point in study.discount_rate_sensitivity:
            for metric, value, unit in (
                ("npv_usd", point.npv_usd, "USD"),
                ("irr", point.irr, "1"),
            ):
                if metric not in scenario.outputs or value is None:
                    continue
                observations.append(
                    Observation(
                        entity_type="factory_discount_sensitivity",
                        entity_id=point.id,
                        metric=metric,
                        value=float(value),
                        unit=unit,
                        uncertainty=None,
                        evidence_class="assumed",
                        source_artifact=source,
                        model_version=model_version,
                    )
                )
        for point in study.terminal_value_sensitivity:
            for metric, value, unit in (
                ("npv_usd", point.npv_usd, "USD"),
                ("irr", point.irr, "1"),
            ):
                if metric not in scenario.outputs or value is None:
                    continue
                observations.append(
                    Observation(
                        entity_type="factory_terminal_value_sensitivity",
                        entity_id=point.id,
                        metric=metric,
                        value=float(value),
                        unit=unit,
                        uncertainty=None,
                        evidence_class="assumed",
                        source_artifact=source,
                        model_version=model_version,
                    )
                )
        input_files = [
            InputFile(scenario.chip_path, "chip"),
            InputFile(scenario.package_path, "package"),
            InputFile(scenario.yield_path, "yield"),
            InputFile(scenario.factory_path, "factory"),
        ]
        if tech.path is not None:
            input_files.append(InputFile(tech.path, "tech"))
        return EngineResult(
            engine=self.name,
            engine_version=self.version,
            fidelity=self.fidelity,
            model_version=model_version,
            observations=tuple(observations),
            inputs=tuple(input_files),
            metadata={
                "chip": cfg.name,
                "tech": {"name": tech.name, "revision": tech.revision},
                "factory": {
                    "id": factory.id,
                    "revision": factory.revision,
                    "product": factory.product,
                    "process": factory.process,
                    "wafer_starts_per_week": factory.wafer_starts_per_week,
                    "simulation_weeks": factory.simulation_weeks,
                    "warmup_weeks": factory.warmup_weeks,
                    "wafers_per_lot": factory.wafers_per_lot,
                    "operating_cost_usd_per_week": (
                        factory.operating_cost_usd_per_week
                    ),
                    "package_price_usd": factory.package_price_usd,
                    "gross_margin_usd_per_good_package": gross_margin,
                    "discount_rate": factory.discount_rate,
                    "dcf_years": DCF_YEARS,
                    "dcf_ramp": list(factory.dcf_ramp),
                    "terminal_value_pct_of_capex": (
                        factory.terminal_value_pct_of_capex
                    ),
                    "investment_basis": (
                        "incremental versus the declared reference case; "
                        "payback uses annual cash flow, ROI uses net income "
                        "after depreciation, NPV/IRR use five annual steps"
                    ),
                    "package_option": factory.package_option,
                    "sensitivity": (
                        None
                        if factory.sensitivity is None
                        else {
                            "package_prices_usd": list(
                                factory.sensitivity.package_prices_usd
                            ),
                            "gross_margins_usd_per_good_package": list(
                                factory.sensitivity.gross_margins_usd_per_good_package
                            ),
                            "discount_rates": list(
                                factory.sensitivity.discount_rates
                            ),
                            "terminal_value_pcts_of_capex": list(
                                factory.sensitivity.terminal_value_pcts_of_capex
                            ),
                        }
                    ),
                    "priced_tool_groups": [
                        {
                            "id": group.id,
                            "tools": group.tools,
                            "capex_usd_per_tool": group.capex_usd_per_tool,
                            "depreciation_years": group.depreciation_years,
                            "weekly_depreciation_usd": (
                                group.weekly_depreciation_usd
                            ),
                        }
                        for group in factory.tool_groups
                        if group.capex_usd_per_tool > 0
                    ],
                    "tool_groups": len(factory.tool_groups),
                    "route_steps": (
                        len(factory.fab_route) + len(factory.atp_route)
                    ),
                },
                "package": {
                    "option": option.option.id,
                    "name": option.option.name,
                    "assembly_yield": option.assembly_yield,
                    "good_packages_per_g100_wafer": (
                        option.good_packages_per_g100_wafer
                    ),
                    "package_cost_per_good_package_usd": (
                        option.cost_per_good_package_usd
                    ),
                },
                "cases": [
                    {
                        "id": case.id,
                        "description": case.description,
                        "wafer_starts_per_week": case.wafer_starts_per_week,
                        "lots": case.lots,
                        "wafers": case.wafers,
                        "cycle_time_hours": case.cycle_time_hours,
                        "queue_time_hours": case.queue_time_hours,
                        "wip_lots": case.wip_lots,
                        "throughput_wafers_per_week": (
                            case.throughput_wafers_per_week
                        ),
                        "good_packages_per_week": (
                            case.good_packages_per_week
                        ),
                        "cost_per_good_package_usd": (
                            case.cost_per_good_package_usd
                        ),
                        "tool_capex_usd": case.tool_capex_usd,
                        "depreciation_usd_per_week": (
                            case.depreciation_usd_per_week
                        ),
                        "depreciation_per_good_package_usd": (
                            case.depreciation_per_good_package_usd
                        ),
                        "incremental_capex_usd": case.incremental_capex_usd,
                        "incremental_annual_cash_flow_usd": (
                            case.incremental_annual_cash_flow_usd
                        ),
                        "incremental_annual_net_income_usd": (
                            case.incremental_annual_net_income_usd
                        ),
                        "payback_years": case.payback_years,
                        "roi": case.roi,
                        "npv_usd": case.npv_usd,
                        "irr": case.irr,
                        "roi_reference": case.roi_reference,
                        "operating_cost_usd_per_week": (
                            case.operating_cost_usd_per_week
                        ),
                        "tool_counts": dict(case.tool_counts),
                        "bottleneck_step": case.bottleneck_step,
                        "bottleneck_step_queue_hours": (
                            case.bottleneck_step_queue_hours
                        ),
                        "bottleneck_tool_group": case.bottleneck_tool_group,
                        "bottleneck_utilization": (
                            case.bottleneck_utilization
                        ),
                    }
                    for case in study.all_cases()
                ],
                "sensitivity_points": [
                    {
                        "id": point.id,
                        "case_id": point.case_id,
                        "basis": point.basis,
                        "assumption_usd": point.assumption_usd,
                        "package_price_usd": point.package_price_usd,
                        "gross_margin_usd_per_good_package": (
                            point.gross_margin_usd_per_good_package
                        ),
                        "incremental_capex_usd": (
                            point.incremental_capex_usd
                        ),
                        "incremental_annual_cash_flow_usd": (
                            point.incremental_annual_cash_flow_usd
                        ),
                        "incremental_annual_net_income_usd": (
                            point.incremental_annual_net_income_usd
                        ),
                        "payback_years": point.payback_years,
                        "roi": point.roi,
                        "npv_usd": point.npv_usd,
                        "irr": point.irr,
                        "roi_reference": point.roi_reference,
                    }
                    for point in study.sensitivity
                ],
                "discount_rate_points": [
                    {
                        "id": point.id,
                        "case_id": point.case_id,
                        "discount_rate": point.discount_rate,
                        "incremental_capex_usd": (
                            point.incremental_capex_usd
                        ),
                        "incremental_annual_cash_flow_usd": (
                            point.incremental_annual_cash_flow_usd
                        ),
                        "npv_usd": point.npv_usd,
                        "irr": point.irr,
                        "roi_reference": point.roi_reference,
                    }
                    for point in study.discount_rate_sensitivity
                ],
                "terminal_value_points": [
                    {
                        "id": point.id,
                        "case_id": point.case_id,
                        "terminal_value_pct_of_capex": (
                            point.terminal_value_pct_of_capex
                        ),
                        "terminal_value_usd": point.terminal_value_usd,
                        "incremental_capex_usd": (
                            point.incremental_capex_usd
                        ),
                        "incremental_annual_cash_flow_usd": (
                            point.incremental_annual_cash_flow_usd
                        ),
                        "npv_usd": point.npv_usd,
                        "irr": point.irr,
                        "roi_reference": point.roi_reference,
                    }
                    for point in study.terminal_value_sensitivity
                ],
                "simulation": {
                    "samples": 1,
                    "scope": (
                        "deterministic SimPy route with finite tool groups, "
                        "batch formation, setup and MTBF/MTTR availability"
                    ),
                },
            },
            warnings=(
                "Phase 4 route, tool counts, process times, MTBF/MTTR and "
                "operating cost are planning assumptions, not a foundry MES "
                "route card or measured line performance.",
                "Downtime is an availability factor applied to effective "
                "process time; random failures, maintenance calendars, "
                "reticle changes, dispatch rules and transport time are not "
                "modelled.",
                "Cost per good package is the Phase 3 package cost plus "
                "factory operating cost and straight-line depreciation for "
                "priced tool groups; it is not a qualified product cost. Only "
                "tool groups with a declared capex are depreciated, so the "
                "absolute cost is partial. Payback and ROI are reported only "
                "when a package price, gross margin or sensitivity block is "
                "supplied; they are planning economics, not a market forecast.",
                "Scanner DCF uses the declared five-year cash-flow ramp and "
                "terminal value; taxes, working capital, price erosion and "
                "replacement capex are not modelled.",
                "Discount-rate and terminal-value sensitivity hold the base "
                "scanner cash flow, ramp and hurdle rate fixed.",
                "Price/margin sensitivity is one-at-a-time and holds output, "
                "cost and margin constant; it is not a demand forecast.",
            ),
        )

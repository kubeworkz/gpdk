"""Tests for the Phase 4 SimPy factory and ATP planning model."""

from __future__ import annotations

import csv
import json
from dataclasses import replace

import pytest
import yaml

from fabtwin.adapters.factory import FactoryAtpEngine
from fabtwin.provenance import ROOT
from fabtwin.run import execute, validate_scenario
from fabtwin.scenario import load_scenario
from gpdk.block import load_chip
from gpdk.dtco import best_step, build_steps
from gpdk.factory import (
    FactoryAssumptions,
    RouteStep,
    ToolGroupSpec,
    WhatIf,
    simulate_factory,
    simulate_factory_case,
)
from gpdk.mcm import McmYieldAssumptions, simulate_mcm_yield

ASSUMPTIONS_PATH = ROOT / "factory" / "g100_28nm.yaml"
SCENARIO_PATH = ROOT / "scenarios" / "g100_factory_28nm.yaml"


def _assumptions() -> FactoryAssumptions:
    raw = yaml.safe_load(ASSUMPTIONS_PATH.read_text(encoding="utf-8"))
    return FactoryAssumptions.from_mapping(raw)


def _minimal() -> FactoryAssumptions:
    return FactoryAssumptions(
        id="minimal_factory",
        product="g100",
        process="grx28@0.1.0",
        revision="0.1.0",
        description="",
        wafer_starts_per_week=25.0,
        simulation_weeks=4.0,
        warmup_weeks=0.0,
        wafers_per_lot=25,
        operating_cost_usd_per_week=0.0,
        package_option="silicon_interposer",
        tool_groups=(ToolGroupSpec("single", 1, 1000.0, 0.0),),
        fab_route=(RouteStep("fab_step", "single", 10.0),),
        atp_route=(RouteStep("atp_step", "single", 2.0),),
        what_if=(
            WhatIf("downtime_a", "", mttr_scale=0.5),
            WhatIf("downtime_b", "", mttr_scale=0.25),
        ),
    )


def _mcm_option(assumptions: FactoryAssumptions):
    cfg = load_chip(ROOT / "chips" / "g100.yaml")
    estimate = best_step(build_steps(cfg)).iso
    simulation = simulate_mcm_yield(
        McmYieldAssumptions.from_mapping(
            yaml.safe_load(
                (ROOT / "yields" / "g100_mcm_28nm.yaml").read_text(
                    encoding="utf-8"
                )
            )
        ),
        estimate.die_area_mm2,
    )
    return next(
        option
        for option in simulation.options
        if option.option.id == assumptions.package_option
    )


def test_minimal_route_matches_hand_calculation() -> None:
    case = simulate_factory_case(
        _minimal(),
        case_id="baseline",
        description="",
        wafer_starts_per_week=25.0,
        good_packages_per_wafer=10.0,
        package_cost_per_good_package_usd=5.0,
    )
    assert case.cycle_time_hours == pytest.approx(12.0)
    assert case.queue_time_hours == pytest.approx(0.0, abs=1e-9)
    assert case.throughput_wafers_per_week == pytest.approx(25.0, rel=0.05)
    assert case.good_packages_per_week == pytest.approx(250.0, rel=0.05)
    assert case.cost_per_good_package_usd == pytest.approx(5.0)
    assert case.bottleneck_tool_group == "single"
    assert case.bottleneck_utilization > 0.0


def test_factory_assumptions_declare_what_ifs() -> None:
    assumptions = _assumptions()
    assert assumptions.wafer_starts_per_week == pytest.approx(600.0)
    assert assumptions.package_price_usd == pytest.approx(100.0)
    assert assumptions.gross_margin_usd_per_good_package is None
    assert assumptions.discount_rate == pytest.approx(0.10)
    assert assumptions.dcf_ramp == (0.60, 0.80, 1.00, 1.00, 1.00)
    assert assumptions.terminal_value_pct_of_capex == pytest.approx(0.20)
    assert assumptions.sensitivity is not None
    assert assumptions.sensitivity.package_prices_usd == (
        70.0,
        85.0,
        100.0,
        115.0,
        130.0,
    )
    assert assumptions.sensitivity.gross_margins_usd_per_good_package == (
        20.0,
        40.0,
        60.0,
        80.0,
    )
    assert assumptions.sensitivity.discount_rates == (
        0.05,
        0.075,
        0.10,
        0.125,
        0.15,
    )
    assert assumptions.sensitivity.terminal_value_pcts_of_capex == (
        0.0,
        0.10,
        0.20,
        0.30,
        0.40,
    )
    assert {case.id for case in assumptions.what_if} == {
        "higher_starts",
        "low_downtime",
        "extra_litho",
    }
    extra_litho = next(
        case for case in assumptions.what_if if case.id == "extra_litho"
    )
    assert extra_litho.wafer_starts_per_week == pytest.approx(800.0)
    assert extra_litho.tool_count_overrides == (("litho", 4),)
    assert extra_litho.operating_cost_delta_usd_per_week == pytest.approx(
        120000.0
    )
    litho = next(
        group for group in assumptions.tool_groups if group.id == "litho"
    )
    assert litho.capex_usd_per_tool == pytest.approx(60000000.0)
    assert litho.depreciation_years == pytest.approx(5.0)
    assert litho.weekly_depreciation_usd == pytest.approx(
        60000000.0 / (5.0 * 52.0)
    )
    assert len(assumptions.tool_groups) == 14
    assert len(assumptions.fab_route) + len(assumptions.atp_route) == 38


def test_factory_study_reports_bottleneck_and_start_sensitivity() -> None:
    assumptions = _assumptions()
    option = _mcm_option(assumptions)
    study = simulate_factory(
        assumptions,
        good_packages_per_wafer=option.good_packages_per_g100_wafer,
        package_cost_per_good_package_usd=option.cost_per_good_package_usd,
    )
    baseline, higher_starts, low_downtime, extra_litho = study.all_cases()

    assert baseline.bottleneck_tool_group == "litho"
    assert 0.70 <= baseline.bottleneck_utilization <= 0.85
    assert 100.0 < baseline.cycle_time_hours < 250.0
    assert 550.0 <= baseline.throughput_wafers_per_week <= 650.0
    assert (
        baseline.cost_per_good_package_usd
        > option.cost_per_good_package_usd
    )

    assert higher_starts.cycle_time_hours > (
        baseline.cycle_time_hours * 1.5
    )
    assert higher_starts.wip_lots > baseline.wip_lots
    assert (
        higher_starts.bottleneck_utilization
        > baseline.bottleneck_utilization
    )
    assert higher_starts.throughput_wafers_per_week < 800.0

    assert low_downtime.cycle_time_hours < baseline.cycle_time_hours
    assert (
        low_downtime.tool_utilization["litho"]
        < baseline.tool_utilization["litho"]
    )

    assert extra_litho.tool_counts["litho"] == 4
    assert extra_litho.cycle_time_hours < higher_starts.cycle_time_hours * 0.7
    assert extra_litho.wip_lots < higher_starts.wip_lots
    assert (
        extra_litho.throughput_wafers_per_week
        > higher_starts.throughput_wafers_per_week
    )
    assert baseline.tool_capex_usd == pytest.approx(180000000.0)
    assert baseline.depreciation_usd_per_week == pytest.approx(
        3.0 * 60000000.0 / (5.0 * 52.0)
    )
    assert higher_starts.tool_capex_usd == baseline.tool_capex_usd
    assert extra_litho.tool_capex_usd == pytest.approx(240000000.0)
    assert (
        extra_litho.depreciation_usd_per_week
        > higher_starts.depreciation_usd_per_week
    )
    assert (
        extra_litho.cost_per_good_package_usd
        > higher_starts.cost_per_good_package_usd
    )
    assert baseline.incremental_capex_usd == pytest.approx(0.0)
    assert baseline.payback_years is None
    assert higher_starts.incremental_capex_usd == pytest.approx(0.0)
    assert higher_starts.payback_years is None
    assert extra_litho.roi_reference == "higher_starts"
    assert extra_litho.incremental_capex_usd == pytest.approx(60000000.0)
    assert extra_litho.incremental_annual_cash_flow_usd > 0.0
    assert extra_litho.incremental_annual_net_income_usd > 0.0
    assert extra_litho.payback_years is not None
    assert 3.0 < extra_litho.payback_years < 6.0
    assert extra_litho.roi is not None
    assert 0.0 < extra_litho.roi < 0.2
    expected_npv = -extra_litho.incremental_capex_usd + sum(
        extra_litho.incremental_annual_cash_flow_usd
        * factor
        / (1.10**year)
        for year, factor in enumerate(assumptions.dcf_ramp, start=1)
    ) + (
        extra_litho.incremental_capex_usd
        * assumptions.terminal_value_pct_of_capex
        / (1.10**5)
    )
    assert extra_litho.npv_usd == pytest.approx(expected_npv)
    assert extra_litho.npv_usd < 0.0
    assert extra_litho.irr is not None
    assert 0.05 < extra_litho.irr < 0.10


def test_factory_sensitivity_reports_price_and_margin_curves() -> None:
    assumptions = _assumptions()
    option = _mcm_option(assumptions)
    study = simulate_factory(
        assumptions,
        good_packages_per_wafer=option.good_packages_per_g100_wafer,
        package_cost_per_good_package_usd=option.cost_per_good_package_usd,
    )
    scanner = next(case for case in study.cases if case.id == "extra_litho")
    points = {point.id: point for point in study.sensitivity}
    assert len(points) == 9
    base = points["extra_litho:price:100"]
    assert base.payback_years == pytest.approx(scanner.payback_years)
    assert base.roi == pytest.approx(scanner.roi)
    assert base.npv_usd == pytest.approx(scanner.npv_usd)
    assert base.irr == pytest.approx(scanner.irr)

    low_price = points["extra_litho:price:70"]
    high_price = points["extra_litho:price:130"]
    assert low_price.payback_years > high_price.payback_years
    assert low_price.roi < high_price.roi
    assert low_price.roi < 0.0
    assert low_price.npv_usd < high_price.npv_usd
    assert low_price.irr is None
    assert high_price.irr is not None
    assert high_price.irr > 0.2

    low_margin = points["extra_litho:margin:20"]
    high_margin = points["extra_litho:margin:80"]
    assert low_margin.payback_years > high_margin.payback_years
    assert low_margin.roi < high_margin.roi
    assert low_margin.roi < 0.0
    assert low_margin.npv_usd < high_margin.npv_usd
    assert low_margin.irr is None
    assert high_margin.irr is not None
    assert high_margin.irr > 0.2
    assert all(point.case_id == "extra_litho" for point in points.values())

    rate_points = {
        point.discount_rate: point
        for point in study.discount_rate_sensitivity
    }
    assert len(rate_points) == 5
    assert rate_points[0.05].npv_usd > 0.0
    assert rate_points[0.15].npv_usd < 0.0
    assert (
        rate_points[0.05].npv_usd
        > rate_points[0.10].npv_usd
        > rate_points[0.15].npv_usd
    )
    assert rate_points[0.10].npv_usd == pytest.approx(scanner.npv_usd)
    assert all(
        point.irr == pytest.approx(scanner.irr)
        for point in rate_points.values()
    )

    terminal_points = {
        point.terminal_value_pct_of_capex: point
        for point in study.terminal_value_sensitivity
    }
    assert len(terminal_points) == 5
    assert terminal_points[0.0].npv_usd < 0.0
    assert terminal_points[0.4].npv_usd > terminal_points[0.0].npv_usd
    assert terminal_points[0.2].npv_usd == pytest.approx(scanner.npv_usd)
    assert terminal_points[0.0].irr is not None
    assert terminal_points[0.4].irr > terminal_points[0.0].irr


def test_factory_rejects_both_price_and_margin() -> None:
    with pytest.raises(ValueError, match="not both"):
        replace(
            _assumptions(),
            gross_margin_usd_per_good_package=50.0,
        )


def test_factory_gross_margin_matches_equivalent_price() -> None:
    assumptions = _assumptions()
    option = _mcm_option(assumptions)
    assert assumptions.package_price_usd is not None
    margin = assumptions.package_price_usd - option.cost_per_good_package_usd
    price_study = simulate_factory(
        assumptions,
        good_packages_per_wafer=option.good_packages_per_g100_wafer,
        package_cost_per_good_package_usd=option.cost_per_good_package_usd,
    )
    margin_study = simulate_factory(
        replace(
            assumptions,
            package_price_usd=None,
            gross_margin_usd_per_good_package=margin,
        ),
        good_packages_per_wafer=option.good_packages_per_g100_wafer,
        package_cost_per_good_package_usd=option.cost_per_good_package_usd,
    )
    price_scanner = price_study.all_cases()[-1]
    margin_scanner = margin_study.all_cases()[-1]
    assert margin_scanner.payback_years == pytest.approx(
        price_scanner.payback_years
    )
    assert margin_scanner.roi == pytest.approx(price_scanner.roi)


def test_factory_case_is_deterministic() -> None:
    assumptions = _assumptions()
    option = _mcm_option(assumptions)
    kwargs = dict(
        case_id="baseline",
        description="",
        wafer_starts_per_week=600.0,
        good_packages_per_wafer=option.good_packages_per_g100_wafer,
        package_cost_per_good_package_usd=option.cost_per_good_package_usd,
    )
    first = simulate_factory_case(assumptions, **kwargs)
    second = simulate_factory_case(assumptions, **kwargs)
    assert first == second


def test_factory_requires_two_what_ifs() -> None:
    with pytest.raises(ValueError, match="two what-if"):
        replace(
            _minimal(),
            what_if=(WhatIf("only_one", "", mttr_scale=0.5),),
        )


def test_factory_engine_requires_factory_input(tmp_path) -> None:
    raw = yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8"))
    raw["inputs"].pop("factory")
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    errors = validate_scenario(load_scenario(path))
    assert any("inputs.factory" in error for error in errors)


def test_factory_scenario_runs_and_reports_cases(tmp_path) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    assert FactoryAtpEngine().validate(scenario) == []
    result = execute(scenario, tmp_path)
    assert result.observation_count == 316

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenario"]["factory"] == "factory/g100_28nm.yaml"
    assert "factory" in {item["role"] for item in manifest["inputs"]}

    with (result.run_dir / "observations.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    case_rows = [row for row in rows if row["entity_type"] == "factory_case"]
    assert {row["entity_id"] for row in case_rows} == {
        "baseline",
        "higher_starts",
        "low_downtime",
        "extra_litho",
    }
    assert len(case_rows) == 55
    assert {row["metric"] for row in case_rows} >= {
        "tool_capex_usd",
        "depreciation_usd_per_week",
        "depreciation_per_good_package_usd",
        "incremental_capex_usd",
        "payback_years",
        "roi",
        "npv_usd",
        "irr",
    }
    payback_rows = [
        row
        for row in rows
        if row["metric"] == "payback_years"
        and row["entity_type"] == "factory_case"
    ]
    assert len(payback_rows) == 1
    assert payback_rows[0]["entity_id"] == "extra_litho"
    assert float(payback_rows[0]["value"]) > 0.0
    assert len(
        [row for row in rows if row["metric"] == "tool_utilization"]
    ) == 56
    sensitivity_rows = [
        row for row in rows if row["entity_type"] == "factory_sensitivity"
    ]
    assert len(sensitivity_rows) == 33
    assert {row["metric"] for row in sensitivity_rows} == {
        "payback_years",
        "roi",
        "npv_usd",
        "irr",
    }
    discount_rows = [
        row
        for row in rows
        if row["entity_type"] == "factory_discount_sensitivity"
    ]
    assert len(discount_rows) == 10
    assert {row["metric"] for row in discount_rows} == {
        "npv_usd",
        "irr",
    }
    terminal_rows = [
        row
        for row in rows
        if row["entity_type"] == "factory_terminal_value_sensitivity"
    ]
    assert len(terminal_rows) == 10
    assert {row["metric"] for row in terminal_rows} == {
        "npv_usd",
        "irr",
    }
    assert len(
        [row for row in rows if row["metric"] == "step_queue_time_s"]
    ) == 152
    assert {row["evidence_class"] for row in rows} == {"assumed"}
    assert {
        row["unit"] for row in rows if row["metric"] == "wip_lots"
    } == {"lot"}

    report = (result.run_dir / "report.md").read_text(encoding="utf-8")
    assert "## Factory cases" in report
    assert "Bottleneck step" in report
    assert "Capex (Δ vs base)" in report
    assert "Depreciation/week" in report
    assert "Payback / ROI" in report
    assert "## Scanner discounted cash flow" in report
    assert "Terminal value" in report
    assert "## Scanner discount-rate sensitivity" in report
    assert "## Scanner terminal-value sensitivity" in report
    assert "## Scanner economics sensitivity" in report
    assert "IRR" in report
    assert "$70.00" in report
    assert "$130.00" in report
    assert "via_litho" in report
    assert "extra_litho" in report
    assert "1/week" in report

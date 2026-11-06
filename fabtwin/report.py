"""Report generation: prose and display units, never new numbers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .model import EngineResult, Observation
from .provenance import display_path
from .scenario import Scenario

_EVIDENCE_MEANING = {
    "measured": "silicon, PCM, metrology, or a qualified test structure",
    "vendor": "PDK, foundry deck, or licensed model",
    "literature": "public source with a valid range",
    "proxy": "open PDK or predictive kit",
    "assumed": "planning assumption or uncalibrated model",
}


def _table(headers: list[str], rows: Sequence[Sequence[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _display_value(observation: Observation) -> tuple[str, str]:
    value = float(observation.value)
    unit = observation.unit
    if unit == "m2":
        if abs(value) < 1e-3:
            return f"{value * 1e6:.3f}", "mm2"
        return f"{value:.6g}", "m2"
    if unit == "Hz":
        if abs(value) >= 1e9:
            return f"{value / 1e9:.3f}", "GHz"
        if abs(value) >= 1e6:
            return f"{value / 1e6:.3f}", "MHz"
        return f"{value:.3f}", "Hz"
    if unit == "W":
        if abs(value) < 1.0:
            return f"{value * 1e3:.3f}", "mW"
        return f"{value:.6g}", "W"
    if unit == "W/m2":
        return f"{value / 1e6:.4f}", "W/mm2"
    if unit == "1":
        return f"{value:.3f}", "ratio"
    if unit == "s" and abs(value) >= 3600.0:
        return f"{value / 3600.0:.2f}", "h"
    if unit == "1/s":
        return f"{value * 604800.0:.3f}", "1/week"
    return f"{value:.6g}", unit


def _display_uncertainty(
    observation: Observation, display_unit: str
) -> str:
    if observation.uncertainty is None:
        return "not estimated"
    value = float(observation.uncertainty)
    if display_unit == "mm2":
        value *= 1e6
    elif display_unit == "GHz":
        value /= 1e9
    elif display_unit == "MHz":
        value /= 1e6
    elif display_unit == "mW":
        value *= 1e3
    elif display_unit == "W/mm2":
        value /= 1e6
    return f"{value:.6g}"


def render_report(
    scenario: Scenario,
    run_id: str,
    observations: Sequence[Observation],
    engine_results: Sequence[EngineResult],
    input_records: Sequence[dict[str, Any]],
    reproduce: str,
    store_path: Path,
    artifact_names: Sequence[str] = (),
) -> str:
    """Render all tables from the run's observation set."""
    evidence_counts = Counter(item.evidence_class for item in observations)
    engine_rows = []
    design_rows = []
    for result in engine_results:
        tech = result.metadata.get("tech", {})
        tech_text = ""
        if isinstance(tech, dict):
            tech_text = " ".join(
                str(tech.get(key, "")) for key in ("name", "revision")
            ).strip()
        engine_rows.append(
            [
                result.engine,
                result.engine_version,
                result.fidelity,
                result.model_version,
                result.metadata.get("chip", ""),
                tech_text,
            ]
        )
        points = result.metadata.get("design_points", [])
        if isinstance(points, list):
            for point in points:
                if not isinstance(point, dict):
                    continue
                design_rows.append(
                    [
                        result.engine,
                        point.get("key", ""),
                        point.get("label", ""),
                        point.get("library", ""),
                        f"{float(point.get('tracks', 0.0)):g}T",
                        point.get("binding", ""),
                        "yes" if point.get("best") else "",
                    ]
                )

    factory_cases: list[dict[str, Any]] = []
    for result in engine_results:
        cases = result.metadata.get("cases")
        if isinstance(cases, list):
            factory_cases.extend(
                case for case in cases if isinstance(case, dict)
            )
    factory_meta: dict[str, Any] = {}
    for result in engine_results:
        meta = result.metadata.get("factory")
        if isinstance(meta, dict):
            factory_meta = meta
            break
    factory_sensitivity: list[dict[str, Any]] = []
    for result in engine_results:
        points = result.metadata.get("sensitivity_points")
        if isinstance(points, list):
            factory_sensitivity.extend(
                point for point in points if isinstance(point, dict)
            )
    factory_discount_sensitivity: list[dict[str, Any]] = []
    for result in engine_results:
        points = result.metadata.get("discount_rate_points")
        if isinstance(points, list):
            factory_discount_sensitivity.extend(
                point for point in points if isinstance(point, dict)
            )
    factory_terminal_value_sensitivity: list[dict[str, Any]] = []
    for result in engine_results:
        points = result.metadata.get("terminal_value_points")
        if isinstance(points, list):
            factory_terminal_value_sensitivity.extend(
                point for point in points if isinstance(point, dict)
            )
    factory_rows = []
    baseline_cycle = next(
        (
            float(case["cycle_time_hours"])
            for case in factory_cases
            if case.get("id") == "baseline"
            and isinstance(case.get("cycle_time_hours"), (int, float))
        ),
        None,
    )
    baseline_capex = next(
        (
            float(case["tool_capex_usd"])
            for case in factory_cases
            if case.get("id") == "baseline"
            and isinstance(case.get("tool_capex_usd"), (int, float))
        ),
        None,
    )
    for case in factory_cases:
        cycle = float(case.get("cycle_time_hours", 0.0))
        delta = (
            f"{(cycle / baseline_cycle - 1.0) * 100:+.1f}%"
            if baseline_cycle
            else ""
        )
        capex = float(case.get("tool_capex_usd", 0.0))
        capex_text = f"${capex / 1e6:.1f}M"
        if baseline_capex is not None and capex != baseline_capex:
            capex_text += f" ({capex / 1e6 - baseline_capex / 1e6:+.1f}M)"
        depreciation_text = (
            f"${float(case.get('depreciation_usd_per_week', 0.0)) / 1e6:.2f}M"
        )
        payback = case.get("payback_years")
        roi = case.get("roi")
        if payback is None and roi is None:
            investment_text = "n/a"
        else:
            payback_text = (
                f"{float(payback):.2f} yr"
                if isinstance(payback, (int, float))
                else "n/a"
            )
            roi_text = (
                f"{float(roi):.1%}"
                if isinstance(roi, (int, float))
                else "n/a"
            )
            investment_text = f"{payback_text} / {roi_text}"
            reference = case.get("roi_reference", "baseline")
            if reference != "baseline":
                investment_text += f" vs {reference}"
        factory_rows.append(
            [
                case.get("id", ""),
                f"{float(case.get('wafer_starts_per_week', 0.0)):.0f}",
                f"{cycle:.1f}",
                delta,
                f"{float(case.get('queue_time_hours', 0.0)):.1f}",
                f"{float(case.get('wip_lots', 0.0)):.1f}",
                f"{float(case.get('throughput_wafers_per_week', 0.0)):.0f}",
                f"{float(case.get('good_packages_per_week', 0.0)):.0f}",
                f"${float(case.get('cost_per_good_package_usd', 0.0)):.2f}",
                capex_text,
                depreciation_text,
                investment_text,
                case.get("bottleneck_tool_group", ""),
                case.get("bottleneck_step", ""),
                f"{float(case.get('bottleneck_utilization', 0.0)):.1%}",
            ]
        )
    factory_section = ""
    if factory_rows:
        factory_section = (
            "\n## Factory cases\n\n"
            + _table(
                [
                    "Case",
                    "Starts/week",
                    "Cycle (h)",
                    "Δ cycle",
                    "Queue (h)",
                    "WIP (lots)",
                    "Throughput (wafers/week)",
                    "Good packages/week",
                    "Cost/package",
                    "Capex (Δ vs base)",
                    "Depreciation/week",
                    "Payback / ROI",
                    "Bottleneck tool group",
                    "Bottleneck step",
                    "Utilization",
                ],
                factory_rows,
            )
            + "\n\nCycle time and queue time are simulated hours. Throughput is "
            "the steady-state completion rate between pipeline fill and "
            "drain. The change column compares cycle time with the baseline "
            "case. Cost/package includes straight-line depreciation for "
            "priced tool groups; capex is the total priced fleet and the "
            "parenthetical change is versus baseline. Payback uses "
            "incremental annual cash flow versus the case's ROI reference; "
            "ROI is incremental annual net income after depreciation divided "
            "by incremental capex. Both are n/a without a capex change or a "
            "price/margin input.\n"
        )

    if factory_meta:
        dcf_rows = []
        discount_rate = float(factory_meta.get("discount_rate", 0.0))
        dcf_years = int(factory_meta.get("dcf_years", 5))
        terminal_pct = float(
            factory_meta.get("terminal_value_pct_of_capex", 0.0)
        )
        ramp = factory_meta.get("dcf_ramp")
        ramp_text = (
            " / ".join(f"{float(value):.0%}" for value in ramp)
            if isinstance(ramp, list) and ramp
            else "n/a"
        )
        for case in factory_cases:
            npv = case.get("npv_usd")
            irr = case.get("irr")
            if npv is None and irr is None:
                continue
            capex = float(case.get("incremental_capex_usd", 0.0))
            cash = float(
                case.get("incremental_annual_cash_flow_usd", 0.0)
            )
            cash_text = (
                f"{'+' if cash >= 0 else '-'}${abs(cash) / 1e6:.2f}M"
            )
            terminal_value = capex * terminal_pct
            terminal_text = f"${terminal_value / 1e6:.1f}M"
            npv_text = (
                f"{'+' if float(npv) >= 0 else '-'}"
                f"${abs(float(npv)) / 1e6:.2f}M"
                if isinstance(npv, (int, float))
                else "n/a"
            )
            irr_text = (
                f"{float(irr):.1%}"
                if isinstance(irr, (int, float))
                else "n/a"
            )
            dcf_rows.append(
                [
                    case.get("id", ""),
                    f"{discount_rate:.1%}",
                    f"{dcf_years}",
                    f"${capex / 1e6:.1f}M",
                    cash_text,
                    terminal_text,
                    npv_text,
                    irr_text,
                ]
            )
        if dcf_rows:
            factory_section += (
                "\n## Scanner discounted cash flow\n\n"
                + _table(
                    [
                        "Case",
                        "Discount rate",
                        "Years",
                        "Incremental capex",
                        "Annual cash flow",
                        "Terminal value",
                        "NPV",
                        "IRR",
                    ],
                    dcf_rows,
                )
                + f"\n\nCash-flow ramp is {ramp_text} of steady state; "
                f"terminal value is {terminal_pct:.0%} of incremental capex "
                f"at the end of year {dcf_years}. NPV discounts at the "
                "reported hurdle rate; IRR is the zero-NPV rate. No taxes, "
                "working capital, price erosion or replacement capex is "
                "modelled.\n"
            )

    if factory_discount_sensitivity:
        discount_rows = []
        for point in factory_discount_sensitivity:
            rate = float(point.get("discount_rate", 0.0))
            npv = point.get("npv_usd")
            npv_text = (
                f"{'+' if float(npv) >= 0 else '-'}"
                f"${abs(float(npv)) / 1e6:.2f}M"
                if isinstance(npv, (int, float))
                else "n/a"
            )
            irr = point.get("irr")
            irr_text = (
                f"{float(irr):.1%}"
                if isinstance(irr, (int, float))
                else "n/a"
            )
            discount_rows.append(
                [
                    point.get("case_id", ""),
                    f"{rate:.1%}",
                    npv_text,
                    irr_text,
                ]
            )
        factory_section += (
            "\n## Scanner discount-rate sensitivity\n\n"
            + _table(
                ["Case", "Discount rate", "NPV", "IRR"],
                discount_rows,
            )
            +            "\n\nIRR is independent of the hurdle rate; NPV crosses zero "
            "at the IRR. The curve holds the base scanner cash flow, ramp and "
            "terminal value constant.\n"
        )

    if factory_terminal_value_sensitivity:
        terminal_rows = []
        for point in factory_terminal_value_sensitivity:
            pct = float(point.get("terminal_value_pct_of_capex", 0.0))
            terminal = float(point.get("terminal_value_usd", 0.0))
            npv = point.get("npv_usd")
            npv_text = (
                f"{'+' if float(npv) >= 0 else '-'}"
                f"${abs(float(npv)) / 1e6:.2f}M"
                if isinstance(npv, (int, float))
                else "n/a"
            )
            irr = point.get("irr")
            irr_text = (
                f"{float(irr):.1%}"
                if isinstance(irr, (int, float))
                else "n/a"
            )
            terminal_rows.append(
                [
                    point.get("case_id", ""),
                    f"{pct:.0%}",
                    f"${terminal / 1e6:.2f}M",
                    npv_text,
                    irr_text,
                ]
            )
        factory_section += (
            "\n## Scanner terminal-value sensitivity\n\n"
            + _table(
                ["Case", "Terminal value", "Value", "NPV", "IRR"],
                terminal_rows,
            )
            + "\n\nThe terminal value is a residual percentage of incremental "
            "capex at the end of year 5. The curve holds the base cash flow, "
            "ramp and hurdle rate constant.\n"
        )

    if factory_sensitivity:
        sensitivity_rows = []
        for point in factory_sensitivity:
            basis = str(point.get("basis", ""))
            basis_text = {
                "package_price": "Price",
                "gross_margin": "Margin",
            }.get(basis, basis.replace("_", " ").title())
            price = point.get("package_price_usd")
            price_text = (
                f"${float(price):.2f}"
                if isinstance(price, (int, float))
                else "n/a"
            )
            margin = float(
                point.get("gross_margin_usd_per_good_package", 0.0)
            )
            cash = float(
                point.get("incremental_annual_cash_flow_usd", 0.0)
            )
            cash_text = (
                f"{'+' if cash >= 0 else '-'}${abs(cash) / 1e6:.2f}M"
            )
            payback = point.get("payback_years")
            payback_text = (
                f"{float(payback):.2f} yr"
                if isinstance(payback, (int, float))
                else "n/a"
            )
            roi = point.get("roi")
            roi_text = (
                f"{float(roi):.1%}"
                if isinstance(roi, (int, float))
                else "n/a"
            )
            npv = point.get("npv_usd")
            npv_text = (
                f"{'+' if float(npv) >= 0 else '-'}"
                f"${abs(float(npv)) / 1e6:.2f}M"
                if isinstance(npv, (int, float))
                else "n/a"
            )
            irr = point.get("irr")
            irr_text = (
                f"{float(irr):.1%}"
                if isinstance(irr, (int, float))
                else "n/a"
            )
            sensitivity_rows.append(
                [
                    point.get("case_id", ""),
                    basis_text,
                    price_text,
                    f"${margin:.2f}",
                    cash_text,
                    payback_text,
                    roi_text,
                    npv_text,
                    irr_text,
                ]
            )
        factory_section += (
            "\n## Scanner economics sensitivity\n\n"
            + _table(
                [
                    "Case",
                    "Basis",
                    "Price",
                    "Gross margin",
                    "Annual cash flow",
                    "Payback",
                    "ROI",
                    "NPV",
                    "IRR",
                ],
                sensitivity_rows,
            )
            + "\n\nPrice points derive gross margin as price minus the Phase 3 "
            "package cost; margin points state contribution margin before "
            "factory operating cost. Payback uses incremental cash flow versus "
            "the scanner's ROI reference; ROI is after depreciation. NPV "
            "and IRR use the scanner ramp and terminal value assumptions; "
            "the sweep is one-at-a-time and is not a demand or price "
            "forecast.\n"
        )

    observation_rows = []
    for item in observations:
        value, unit = _display_value(item)
        uncertainty = _display_uncertainty(item, unit)
        observation_rows.append(
            [
                item.entity_type,
                item.entity_id,
                item.metric,
                value,
                unit,
                item.evidence_class,
                uncertainty,
            ]
        )

    evidence_rows = [
        [name, evidence_counts.get(name, 0), _EVIDENCE_MEANING[name]]
        for name in _EVIDENCE_MEANING
        if evidence_counts.get(name, 0)
    ]
    input_rows = [
        [
            item["role"],
            f"`{item['path']}`",
            f"`{str(item['sha256'])[:16]}...`",
            item["bytes"],
        ]
        for item in input_records
    ]
    warnings = []
    for result in engine_results:
        warnings.extend(result.warnings)
    warning_md = (
        "\n".join(f"- {warning}" for warning in warnings)
        if warnings
        else "- None."
    )
    outputs = ", ".join(f"`{output}`" for output in scenario.outputs)
    artifact_links = " · ".join(
        f"[{name}]({name})"
        for name in ("observations.csv", *artifact_names, "run.json")
    )

    return f"""# fabtwin run `{run_id}`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

{_table(["Field", "Value"], [
    ["Scenario", f"`{scenario.id}`"],
    ["Description", scenario.description or "—"],
    ["Product", f"`{scenario.product}`"],
    ["Process", f"`{scenario.process}`"],
    ["Seed", scenario.seed],
    ["Samples", scenario.samples],
    ["Engines", ", ".join(f"`{name}`" for name in scenario.engines)],
    ["Outputs", outputs],
    ["Scenario SHA-256", f"`{scenario.sha256[:16]}...`"],
    *(
        [["Package", f"`{scenario.package_ref}`"]]
        if scenario.package_ref
        else []
    ),
    *(
        [["Yield model", f"`{scenario.yield_ref}`"]]
        if scenario.yield_ref
        else []
    ),
    *(
        [["Factory model", f"`{scenario.factory_ref}`"]]
        if scenario.factory_ref
        else []
    ),
    *(
        [["Photonic model", f"`{scenario.photonic_ref}`"]]
        if scenario.photonic_ref
        else []
    ),
    *(
        [
            [
                "Photonic calibration",
                f"`{scenario.photonic_calibration_ref}`",
            ]
        ]
        if scenario.photonic_calibration_ref
        else []
    ),
])}

## Engines

{_table(["Engine", "Version", "Fidelity", "Model version", "Chip", "Technology"], engine_rows)}

### Design points

{_table(["Engine", "Key", "Label", "Library", "Tracks", "Die binding", "Best"], design_rows)}
{factory_section}
## Observations

Values in `observations.csv` are base SI. This table converts area to mm2,
frequency to MHz/GHz, and power to mW/W for readability. A blank uncertainty in
the CSV, or "not estimated" here, means it was not estimated, not that the
value is exact.

{_table(["Entity type", "Entity", "Metric", "Value", "Unit", "Evidence", "Uncertainty"], observation_rows)}

## Evidence

{_table(["Class", "Rows", "Meaning"], evidence_rows)}

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

{_table(["Role", "Path", "SHA-256", "Bytes"], input_rows)}

## Reproduce

```bash
{reproduce}
```

## Observation store

The run is indexed in SQLite at `{display_path(store_path)}`:

```bash
python -m fabtwin query --db {display_path(store_path)} --run {run_id}
```

Artifacts: {artifact_links}

## Caveats

{warning_md}
"""

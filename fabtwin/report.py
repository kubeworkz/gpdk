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
    return f"{value:.6g}", unit


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

    observation_rows = []
    for item in observations:
        value, unit = _display_value(item)
        uncertainty = (
            "not estimated"
            if item.uncertainty is None
            else f"{float(item.uncertainty):.6g}"
        )
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
])}

## Engines

{_table(["Engine", "Version", "Fidelity", "Model version", "Chip", "Technology"], engine_rows)}

### Design points

{_table(["Engine", "Key", "Label", "Library", "Tracks", "Die binding", "Best"], design_rows)}

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

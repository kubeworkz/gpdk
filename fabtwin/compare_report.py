"""Markdown report for a comparison between two indexed runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def format_value(value: float | None, unit: str | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.8g} {unit or ''}".rstrip()


def format_delta(row: Mapping[str, Any]) -> str:
    delta = row["delta"]
    if delta is None:
        return "-"
    text = f"{float(delta):+.8g}"
    if row["delta_pct"] is not None:
        text += f" ({row['delta_pct']:+.2f}%)"
    return text


def evidence_transition(row: Mapping[str, Any]) -> str:
    evidence_a = row["evidence_a"]
    evidence_b = row["evidence_b"]
    if evidence_a is None:
        return evidence_b or "-"
    if evidence_b is None:
        return evidence_a
    if evidence_a != evidence_b:
        return f"{evidence_a} -> {evidence_b}"
    return evidence_a


def default_comparison_report_path(
    db_path: str | Path, run_a: str, run_b: str
) -> Path:
    """Place a comparison beside the store, not inside a single run."""
    return (
        Path(db_path).resolve().parent
        / "comparisons"
        / f"{run_a}__vs__{run_b}.md"
    )


def _table(headers: list[str], rows: Sequence[Sequence[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def render_comparison_report(diff: Mapping[str, Any]) -> str:
    """Render only values already produced by ``ObservationStore.compare_runs``."""
    run_a = diff["run_a"]
    run_b = diff["run_b"]
    summary = diff["summary"]
    filter_info = diff.get("filter", {})
    only_changes = bool(filter_info.get("only_changes"))
    shown_rows = int(filter_info.get("shown_rows", summary["rows"]))

    run_rows = [
        [
            label,
            f"`{run['run_id']}`",
            run["scenario_id"],
            run["product"],
            run["status"],
            run["started_at"],
        ]
        for label, run in (("A", run_a), ("B", run_b))
    ]
    summary_rows = [
        ["Matched observations", summary["rows"]],
        ["Shown observations", shown_rows],
        ["Changed", summary["changed"]],
        ["Evidence changes", summary["evidence_changes"]],
        ["Added", summary["added"]],
        ["Removed", summary["removed"]],
        ["Value changes", summary["value_changes"]],
        ["Unit changes", summary["unit_changes"]],
        ["Model-version changes", summary["model_changes"]],
    ]

    rows = diff["rows"]
    row_table = (
        _table(
            ["Entity", "Metric", "A", "B", "Delta", "Evidence", "Flags"],
            [
                [
                    row["entity_id"],
                    row["metric"],
                    format_value(row["value_a"], row["unit_a"]),
                    format_value(row["value_b"], row["unit_b"]),
                    format_delta(row),
                    evidence_transition(row),
                    ", ".join(row["flags"]) if row["flags"] else "unchanged",
                ]
                for row in rows
            ],
        )
        if rows
        else "No rows matched."
    )
    evidence_rows = [
        row for row in rows if row.get("evidence_changed")
    ]
    evidence_table = (
        _table(
            ["Entity", "Metric", "A", "B"],
            [
                [
                    row["entity_id"],
                    row["metric"],
                    row["evidence_a"],
                    row["evidence_b"],
                ]
                for row in evidence_rows
            ],
        )
        if evidence_rows
        else "No evidence-class changes in the shown rows."
    )
    scope_note = (
        "This report shows changed rows only."
        if only_changes
        else "This report shows every matched row."
    )

    return f"""# fabtwin comparison: `{run_a['run_id']}` vs `{run_b['run_id']}`

> **Read-only comparison, not a new run.** Values are taken from the indexed
> observations; this report does not alter either run, its artifacts, or the
> evidence classes used to produce them.

## Runs

{_table(["Run", "ID", "Scenario", "Product", "Status", "Started"], run_rows)}

## Summary

{_table(["Measure", "Count"], summary_rows)}

{scope_note}

## Rows

Values are shown in the base SI units stored in `observations.csv`. A delta is
shown only when both runs use the same unit. The `evidence` column makes a
change such as `assumed -> measured` explicit.

{row_table}

## Evidence changes

{evidence_table}

## Provenance

- Run A: `{run_a['run_id']}` — `{run_a.get('manifest_path', '')}`
- Run B: `{run_b['run_id']}` — `{run_b.get('manifest_path', '')}`

The SQLite index is an index over the per-run artifacts; the run manifests and
CSV files remain the durable source of truth.
"""


def write_comparison_report(
    diff: Mapping[str, Any], path: str | Path
) -> Path:
    """Write a comparison report and return its resolved path."""
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_comparison_report(diff), encoding="utf-8")
    return target

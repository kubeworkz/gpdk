"""Run a scenario in memory with input overrides, for the browser (Pyodide).

The website loads this package into Pyodide and calls :func:`run_scenario`
with the visitor's settings. It runs the same engines as ``fabtwin run`` on the
same inputs, with the requested values replaced, and returns the observations
as plain data. Nothing is written to the observation store; overridden inputs
are written to a temporary directory and the scenario points at them there.

Overrides are a mapping from an input role (``yield``, ``factory``,
``package``, ``photonic``) to dotted paths into that input's YAML, e.g.::

    {"yield": {"defects.density_per_cm2": 0.12},
     "factory": {"wafer_starts_per_week": 700, "tool_groups.litho.tools": 4}}

A path segment that meets a list of mappings selects the entry whose ``id``
matches. Every path must already exist and hold a number; anything else is an
error, so a renamed input field cannot be silently ignored.
"""

from __future__ import annotations

import math
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import yaml

from .engines import build_engine
from .errors import FabTwinError
from .run import _unique_observations, validate_scenario
from .scenario import Scenario, load_scenario

ROLES = ("yield", "factory", "package", "photonic")


def _input_path(scenario: Scenario, role: str) -> Path:
    path = getattr(scenario, f"{role}_path")
    if path is None:
        raise FabTwinError(f"scenario {scenario.id} has no {role!r} input to override")
    return path


def _set(doc: Any, dotted: str, value: float) -> float:
    """Replace the number at ``dotted`` in ``doc``; return the previous value."""
    parts = dotted.split(".")
    node = doc
    for depth, part in enumerate(parts):
        last = depth == len(parts) - 1
        where = ".".join(parts[: depth + 1])
        if isinstance(node, list):
            match = [item for item in node if isinstance(item, dict) and item.get("id") == part]
            if len(match) != 1:
                raise FabTwinError(f"override {dotted!r}: no single entry with id {part!r} at {where}")
            if last:
                raise FabTwinError(f"override {dotted!r}: {where} is an entry, not a number")
            node = match[0]
            continue
        if not isinstance(node, dict) or part not in node:
            raise FabTwinError(f"override {dotted!r}: {where} does not exist")
        if last:
            old = node[part]
            if isinstance(old, bool) or not isinstance(old, (int, float)):
                raise FabTwinError(f"override {dotted!r}: {where} is not a number")
            node[part] = type(old)(value) if isinstance(old, int) and float(value).is_integer() else float(value)
            return float(old)
        node = node[part]
    raise FabTwinError(f"override {dotted!r}: empty path")


def run_scenario(
    scenario_path: str | Path,
    overrides: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, Any]:
    """Run ``scenario_path`` with ``overrides`` applied; return plain data.

    The result is JSON-serializable: engine metadata is the same mapping
    ``run.json`` records.
    """
    scenario = load_scenario(scenario_path)
    applied: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="fabtwin-browser-") as work:
        if overrides:
            raw = yaml.safe_load(Path(scenario.path).read_text("utf-8"))
            for role, changes in overrides.items():
                if role not in ROLES:
                    raise FabTwinError(f"unknown override role {role!r}; expected one of {', '.join(ROLES)}")
                source = _input_path(scenario, role)
                doc = yaml.safe_load(source.read_text("utf-8"))
                for dotted, value in changes.items():
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                        raise FabTwinError(f"override {role}.{dotted}: value must be a finite number")
                    old = _set(doc, dotted, value)
                    applied.append({"role": role, "path": dotted, "from": old, "to": float(value)})
                target = Path(work) / f"{role}.yaml"
                target.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
                raw["inputs"][role] = str(target)
            copy = Path(work) / "scenario.yaml"
            copy.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
            scenario = load_scenario(copy)

        errors = validate_scenario(scenario)
        if errors:
            raise FabTwinError("scenario validation failed:\n" + "\n".join(f"- {e}" for e in errors))
        results = [build_engine(name).run(scenario) for name in scenario.engines]
        observations = _unique_observations(results)

    return {
        "scenario_id": scenario.id,
        "overrides": applied,
        "engines": [
            {
                "name": r.engine, "version": r.engine_version, "fidelity": r.fidelity,
                "model_version": r.model_version, "metadata": dict(r.metadata),
            }
            for r in results
        ],
        "observations": [asdict(o) for o in observations],
        "artifacts": {
            a.filename: a.content.decode("utf-8")
            for r in results
            for a in r.artifacts
            if a.media_type.startswith("text/")
        },
        "warnings": [w for r in results for w in r.warnings],
    }

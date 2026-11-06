"""F1 yield adapter over the Phase 1 die/package planning model."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import yaml

from gpdk.block import load_chip
from gpdk.dieyield import (
    SensitivitySpec,
    YieldAssumptions,
    YieldEstimate,
    assembly_tolerance_curve,
    defect_density_curve,
    pad_count_curve,
    simulate_yield,
)
from gpdk.dtco import best_step, build_steps
from gpdk.package import PinBudget, choose_package
from gpdk.tech import load_tech

from ..errors import EngineError
from ..model import EngineResult, InputFile, Observation
from ..provenance import display_path
from ..scenario import Scenario

_MODEL_VERSION_PREFIX = "yield-assumptions"
_METRICS: dict[
    str,
    tuple[
        str,
        Callable[[YieldEstimate], float],
        Callable[[YieldEstimate], float | None] | None,
    ],
] = {
    "die_area_m2": (
        "m2",
        lambda estimate: estimate.die_area_mm2 * 1e-6,
        None,
    ),
    "critical_area_m2": (
        "m2",
        lambda estimate: estimate.critical_area_mm2 * 1e-6,
        None,
    ),
    "gross_dies_per_wafer": (
        "1",
        lambda estimate: float(estimate.gross_dies_per_wafer),
        None,
    ),
    "die_yield": (
        "1",
        lambda estimate: estimate.die_yield,
        lambda estimate: estimate.die_yield_stderr,
    ),
    "assembly_yield": (
        "1",
        lambda estimate: estimate.assembly_yield,
        None,
    ),
    "known_good_dies_per_wafer": (
        "1",
        lambda estimate: estimate.known_good_dies_per_wafer,
        lambda estimate: estimate.known_good_dies_stderr,
    ),
    "good_packages_per_wafer": (
        "1",
        lambda estimate: estimate.good_packages_per_wafer,
        lambda estimate: estimate.good_packages_stderr,
    ),
    "cost_per_known_good_die_usd": (
        "USD",
        lambda estimate: estimate.cost_per_known_good_die_usd,
        None,
    ),
    "cost_per_good_package_usd": (
        "USD",
        lambda estimate: estimate.cost_per_good_package_usd,
        lambda estimate: estimate.cost_per_good_package_stderr,
    ),
    "wafer_utilization": (
        "1",
        lambda estimate: estimate.wafer_utilization,
        None,
    ),
}
SUPPORTED_METRICS = frozenset(_METRICS)
_SENSITIVITY_STDERR_KEYS = {
    "die_yield": "die_yield_stderr",
    "good_packages_per_wafer": "good_packages_stderr",
    "cost_per_good_package_usd": "cost_per_good_package_stderr",
}
_SENSITIVITY_METRICS = frozenset(
    {
        "defect_density_per_cm2",
        "pad_count",
        "assembly_per_pad_ppm",
        "die_yield",
        "good_packages_per_wafer",
        "cost_per_good_package_usd",
    }
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read yield model {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"yield model {path} must be a mapping")
    return raw


def _load_inputs(scenario: Scenario):
    cfg = load_chip(scenario.chip_path)
    tech = load_tech(cfg.tech_file)
    if scenario.yield_path is None:
        raise ValueError("yield scenario requires inputs.yield")
    assumptions = YieldAssumptions.from_mapping(_read_yaml(scenario.yield_path))
    if not cfg.pin_spec:
        raise ValueError("yield scenario needs a chip pin budget")
    estimate = best_step(build_steps(cfg)).iso
    selected = str(cfg.pin_spec.get("selected") or next(iter(cfg.pin_spec["variants"])))
    budget = PinBudget.from_spec(cfg.pin_spec, selected)
    package = choose_package(budget.total_pads, estimate.die_area_mm2**0.5)
    if package is None:
        raise ValueError("no catalog package carries the chip pad ring")
    return cfg, tech, assumptions, estimate, budget, package


class YieldEngine:
    """F1 die, package and cost model with explicit assumptions."""

    name = "yield"
    version = "0.1.0"
    fidelity = "F1"

    def validate(self, scenario: Scenario) -> list[str]:
        errors: list[str] = []
        if scenario.samples < 1:
            errors.append("yield needs at least one sample")
        unknown = sorted(set(scenario.outputs) - SUPPORTED_METRICS)
        if unknown:
            errors.append(
                "unsupported yield output metric(s): " + ", ".join(unknown)
            )
        try:
            cfg, tech, assumptions, estimate, budget, package = (
                _load_inputs(scenario)
            )
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"cannot load yield inputs: {exc}")
            return errors

        expected_product = _slug(cfg.name)
        if scenario.product != expected_product:
            errors.append(
                f"product {scenario.product!r} does not match chip "
                f"{cfg.name!r} (expected {expected_product!r})"
            )
        expected_process = f"{_slug(tech.name)}@{tech.revision}"
        if scenario.process.lower() != expected_process:
            errors.append(
                f"process {scenario.process!r} does not match "
                f"{tech.name} revision {tech.revision} "
                f"(expected {expected_process!r})"
            )
        if assumptions.product != scenario.product:
            errors.append(
                f"yield model product {assumptions.product!r} does not match "
                f"scenario product {scenario.product!r}"
            )
        if assumptions.process.lower() != scenario.process.lower():
            errors.append(
                f"yield model process {assumptions.process!r} does not match "
                f"scenario process {scenario.process!r}"
            )
        if budget.total_pads <= 0:
            errors.append("pin budget must contain at least one pad")
        if estimate.die_area_mm2 <= 0:
            errors.append("modelled die area must be positive")
        return errors

    def run(self, scenario: Scenario) -> EngineResult:
        errors = self.validate(scenario)
        if errors:
            raise EngineError("; ".join(errors))

        cfg, tech, assumptions, estimate, budget, package = _load_inputs(
            scenario
        )
        simulation = simulate_yield(
            assumptions,
            estimate.die_area_mm2,
            budget.total_pads,
            samples=scenario.samples,
            seed=scenario.seed,
        )
        source = display_path(scenario.yield_path)
        model_version = (
            f"{_MODEL_VERSION_PREFIX}@{assumptions.revision}"
        )
        observations: list[Observation] = []
        for metric in scenario.outputs:
            unit, projector, uncertainty_projector = _METRICS[metric]
            uncertainty = (
                None
                if uncertainty_projector is None
                else uncertainty_projector(simulation)
            )
            observations.append(
                Observation(
                    entity_type="product",
                    entity_id=scenario.product,
                    metric=metric,
                    value=float(projector(simulation)),
                    unit=unit,
                    uncertainty=uncertainty,
                    evidence_class="assumed",
                    source_artifact=source,
                    model_version=model_version,
                )
            )

        input_files = [
            InputFile(scenario.chip_path, "chip"),
            InputFile(scenario.yield_path, "yield"),
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
                "tech": {
                    "name": tech.name,
                    "revision": tech.revision,
                },
                "die_area_mm2": estimate.die_area_mm2,
                "pad_count": budget.total_pads,
                "package": {
                    "name": package.name,
                    "kind": package.kind,
                    "body_mm": package.body_mm,
                    "pads": package.pads,
                },
                "wafer": {
                    "diameter_mm": assumptions.wafer.diameter_mm,
                    "edge_exclusion_mm": assumptions.wafer.edge_exclusion_mm,
                    "scribe_lane_um": assumptions.wafer.scribe_lane_um,
                    "cost_usd": assumptions.wafer.cost_usd,
                },
                "defects": {
                    "density_per_cm2": assumptions.defect_density_per_cm2,
                    "critical_area_fraction": (
                        assumptions.critical_area_fraction
                    ),
                },
                "assembly": {
                    "base_yield": assumptions.base_assembly_yield,
                    "per_pad_defect_ppm": (
                        assumptions.per_pad_defect_ppm
                    ),
                    "package_cost_usd": assumptions.package_cost_usd,
                    "test_cost_usd": assumptions.test_cost_usd,
                },
                "simulation": {
                    "samples": scenario.samples,
                    "seed": scenario.seed,
                    "scope": (
                        "die and assembly sampling uncertainty, not "
                        "wafer-to-wafer process variation"
                    ),
                },
            },
            warnings=(
                "Yield is an F1 planning estimate, not a foundry yield "
                "prediction.",
                "Wafer, defect, critical-area, assembly and cost values are "
                "explicit assumptions; replace them with calibrated data "
                "before making commitments.",
                "Monte Carlo reports sampling uncertainty for one wafer, not "
                "wafer-to-wafer variation.",
            ),
        )


class YieldSensitivityEngine:
    """F1 sensitivity engine over the same yield assumptions."""

    name = "yield_sensitivity"
    version = "0.1.0"
    fidelity = "F1"

    def validate(self, scenario: Scenario) -> list[str]:
        errors: list[str] = []
        if scenario.samples < 1:
            errors.append("yield sensitivity needs at least one sample per point")
        unknown = sorted(set(scenario.outputs) - _SENSITIVITY_METRICS)
        if unknown:
            errors.append(
                "unsupported yield sensitivity metric(s): "
                + ", ".join(unknown)
            )
        try:
            cfg, tech, assumptions, estimate, budget, package = (
                _load_inputs(scenario)
            )
            sensitivity = SensitivitySpec.from_mapping(
                _read_yaml(scenario.yield_path)
            )
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"cannot load yield sensitivity inputs: {exc}")
            return errors
        expected_product = _slug(cfg.name)
        if scenario.product != expected_product:
            errors.append(
                f"product {scenario.product!r} does not match chip "
                f"{cfg.name!r} (expected {expected_product!r})"
            )
        expected_process = f"{_slug(tech.name)}@{tech.revision}"
        if scenario.process.lower() != expected_process:
            errors.append(
                f"process {scenario.process!r} does not match "
                f"{tech.name} revision {tech.revision} "
                f"(expected {expected_process!r})"
            )
        if assumptions.product != scenario.product:
            errors.append(
                f"yield model product {assumptions.product!r} does not match "
                f"scenario product {scenario.product!r}"
            )
        if assumptions.process.lower() != scenario.process.lower():
            errors.append(
                f"yield model process {assumptions.process!r} does not match "
                f"scenario process {scenario.process!r}"
            )
        if not sensitivity.pad_counts:
            errors.append("sensitivity pad count list is empty")
        if not sensitivity.defect_density_per_cm2:
            errors.append("sensitivity defect density list is empty")
        if not sensitivity.assembly_per_pad_ppm:
            errors.append("sensitivity assembly ppm list is empty")
        return errors

    def run(self, scenario: Scenario) -> EngineResult:
        errors = self.validate(scenario)
        if errors:
            raise EngineError("; ".join(errors))

        cfg, tech, assumptions, estimate, budget, package = _load_inputs(
            scenario
        )
        raw = _read_yaml(scenario.yield_path)
        sensitivity = SensitivitySpec.from_mapping(raw)
        curves = (
            (
                "defect_density",
                defect_density_curve(
                    assumptions,
                    estimate.die_area_mm2,
                    budget.total_pads,
                    sensitivity.defect_density_per_cm2,
                    samples=scenario.samples,
                    seed=scenario.seed,
                ),
            ),
            (
                "pad_count",
                pad_count_curve(
                    assumptions,
                    estimate.die_area_mm2,
                    sensitivity.pad_counts,
                    samples=scenario.samples,
                    seed=scenario.seed + 1000,
                ),
            ),
            (
                "assembly_tolerance",
                assembly_tolerance_curve(
                    assumptions,
                    estimate.die_area_mm2,
                    budget.total_pads,
                    sensitivity.assembly_per_pad_ppm,
                    samples=scenario.samples,
                    seed=scenario.seed + 2000,
                ),
            ),
        )
        units = {
            "defect_density_per_cm2": "1/cm2",
            "pad_count": "1",
            "assembly_per_pad_ppm": "ppm",
            "die_yield": "1",
            "good_packages_per_wafer": "1",
            "cost_per_good_package_usd": "USD",
        }
        x_metric = {
            "defect_density": "defect_density_per_cm2",
            "pad_count": "pad_count",
            "assembly_tolerance": "assembly_per_pad_ppm",
        }
        source = display_path(scenario.yield_path)
        model_version = f"{_MODEL_VERSION_PREFIX}@{assumptions.revision}"
        observations: list[Observation] = []
        for curve_name, rows in curves:
            for row in rows:
                x_value = row[x_metric[curve_name]]
                entity_id = f"{curve_name}:{x_value:g}"
                for metric in scenario.outputs:
                    if metric not in row:
                        continue
                    value = float(row[metric])
                    stderr_key = _SENSITIVITY_STDERR_KEYS.get(metric)
                    uncertainty = (
                        None if stderr_key is None else row.get(stderr_key)
                    )
                    observations.append(
                        Observation(
                            entity_type="sensitivity_point",
                            entity_id=entity_id,
                            metric=metric,
                            value=value,
                            unit=units[metric],
                            uncertainty=(
                                None
                                if uncertainty is None
                                else float(uncertainty)
                            ),
                            evidence_class="assumed",
                            source_artifact=source,
                            model_version=model_version,
                        )
                    )

        input_files = [
            InputFile(scenario.chip_path, "chip"),
            InputFile(scenario.yield_path, "yield"),
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
                "tech": {
                    "name": tech.name,
                    "revision": tech.revision,
                },
                "die_area_mm2": estimate.die_area_mm2,
                "pad_count": budget.total_pads,
                "package": {
                    "name": package.name,
                    "kind": package.kind,
                    "pads": package.pads,
                },
                "curves": {
                    "defect_density_per_cm2": list(
                        sensitivity.defect_density_per_cm2
                    ),
                    "pad_counts": list(sensitivity.pad_counts),
                    "assembly_per_pad_ppm": list(
                        sensitivity.assembly_per_pad_ppm
                    ),
                },
                "simulation": {
                    "samples_per_point": scenario.samples,
                    "seed": scenario.seed,
                    "scope": (
                        "die and assembly sampling uncertainty, not "
                        "wafer-to-wafer process variation"
                    ),
                },
            },
            warnings=(
                "Yield sensitivity is an F1 planning exercise, not a "
                "foundry process corner.",
                "Curve points share model assumptions; they do not represent "
                "independent measured wafers.",
                "Monte Carlo reports sampling uncertainty, not model "
                "calibration uncertainty.",
            ),
        )

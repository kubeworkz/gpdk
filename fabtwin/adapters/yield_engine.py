"""F1 yield adapter over the Phase 1 die/package planning model."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import yaml

from gpdk.block import load_chip
from gpdk.dieyield import (
    LotEstimate,
    SensitivitySpec,
    WaferMapEstimate,
    YieldAssumptions,
    YieldEstimate,
    assembly_tolerance_curve,
    defect_density_curve,
    pad_count_curve,
    simulate_lot_yield,
    simulate_wafer_map,
    simulate_yield,
)
from gpdk.dtco import best_step, build_steps
from gpdk.package import PinBudget, choose_package
from gpdk.tech import load_tech
from gpdk.wafermap import to_csv as wafer_map_csv
from gpdk.wafermap import to_svg as wafer_map_svg

from ..errors import EngineError
from ..model import EngineResult, GeneratedArtifact, InputFile, Observation
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
_VARIATION_METRICS: dict[
    str,
    tuple[
        str,
        Callable[[LotEstimate], float],
        Callable[[LotEstimate], float | None] | None,
    ],
] = {
    "die_yield_mean": (
        "1",
        lambda estimate: estimate.die_yield_mean,
        lambda estimate: estimate.die_yield_stderr,
    ),
    "wafer_to_wafer_die_yield_sigma": (
        "1",
        lambda estimate: estimate.wafer_to_wafer_die_yield_sigma,
        None,
    ),
    "lot_to_lot_die_yield_sigma": (
        "1",
        lambda estimate: estimate.lot_to_lot_die_yield_sigma,
        None,
    ),
    "assembly_yield_mean": (
        "1",
        lambda estimate: estimate.assembly_yield_mean,
        lambda estimate: estimate.assembly_yield_stderr,
    ),
    "good_packages_per_wafer_mean": (
        "1",
        lambda estimate: estimate.good_packages_per_wafer_mean,
        lambda estimate: estimate.good_packages_stderr,
    ),
    "cost_per_good_package_usd_mean": (
        "USD",
        lambda estimate: estimate.cost_per_good_package_usd_mean,
        lambda estimate: estimate.cost_per_good_package_stderr,
    ),
}
SUPPORTED_VARIATION_METRICS = frozenset(_VARIATION_METRICS)
_WAFER_MAP_METRICS: dict[
    str,
    tuple[
        str,
        Callable[[WaferMapEstimate], float],
        Callable[[WaferMapEstimate], float | None] | None,
    ],
] = {
    "die_yield_mean": (
        "1",
        lambda estimate: estimate.die_yield_mean,
        lambda estimate: estimate.die_yield_stderr,
    ),
    "center_die_yield": (
        "1",
        lambda estimate: estimate.center_die_yield,
        None,
    ),
    "edge_die_yield": (
        "1",
        lambda estimate: estimate.edge_die_yield,
        None,
    ),
    "edge_to_center_yield_ratio": (
        "1",
        lambda estimate: estimate.edge_to_center_yield_ratio,
        None,
    ),
    "radial_yield_slope_per_mm": (
        "1/mm",
        lambda estimate: estimate.radial_yield_slope_per_mm,
        None,
    ),
    "assembly_yield": (
        "1",
        lambda estimate: estimate.assembly_yield,
        None,
    ),
    "good_packages_per_wafer": (
        "1",
        lambda estimate: estimate.good_packages_per_wafer,
        lambda estimate: estimate.good_packages_stderr,
    ),
    "cost_per_good_package_usd": (
        "USD",
        lambda estimate: estimate.cost_per_good_package_usd,
        lambda estimate: estimate.cost_per_good_package_stderr,
    ),
}
SUPPORTED_WAFER_MAP_METRICS = frozenset(_WAFER_MAP_METRICS)


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


class YieldVariationEngine:
    """F1 lot and wafer variation over the same yield assumptions."""

    name = "yield_variation"
    version = "0.1.0"
    fidelity = "F1"

    def validate(self, scenario: Scenario) -> list[str]:
        errors: list[str] = []
        if scenario.samples < 2:
            errors.append("yield variation needs at least two lots")
        unknown = sorted(
            set(scenario.outputs) - SUPPORTED_VARIATION_METRICS
        )
        if unknown:
            errors.append(
                "unsupported yield variation metric(s): "
                + ", ".join(unknown)
            )
        try:
            cfg, tech, assumptions, estimate, budget, package = (
                _load_inputs(scenario)
            )
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"cannot load yield variation inputs: {exc}")
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
        if assumptions.variation is None:
            errors.append(
                "yield model needs a variation mapping for the variation "
                "engine"
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
        variation = assumptions.variation
        if variation is None:
            raise EngineError("yield model needs a variation mapping")
        simulation = simulate_lot_yield(
            assumptions,
            estimate.die_area_mm2,
            budget.total_pads,
            lots=scenario.samples,
            seed=scenario.seed,
        )
        source = display_path(scenario.yield_path)
        model_version = f"{_MODEL_VERSION_PREFIX}@{assumptions.revision}"
        observations: list[Observation] = []
        for metric in scenario.outputs:
            unit, projector, uncertainty_projector = _VARIATION_METRICS[metric]
            uncertainty = (
                None
                if uncertainty_projector is None
                else uncertainty_projector(simulation)
            )
            observations.append(
                Observation(
                    entity_type="lot_simulation",
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
                "variation": {
                    "wafers_per_lot": variation.wafers_per_lot,
                    "defect_density_cv_lot": (
                        variation.defect_density_cv_lot
                    ),
                    "defect_density_cv_wafer": (
                        variation.defect_density_cv_wafer
                    ),
                    "assembly_ppm_cv_lot": variation.assembly_ppm_cv_lot,
                },
                "simulation": {
                    "lots": scenario.samples,
                    "wafers": simulation.wafers,
                    "seed": scenario.seed,
                    "scope": (
                        "lognormal lot and wafer variation plus die and "
                        "assembly sampling; not calibrated fab or OSAT "
                        "distributions"
                    ),
                },
            },
            warnings=(
                "Yield variation is an F1 planning exercise, not a "
                "calibrated fab or OSAT distribution.",
                "Defect-density and assembly CVs are assumed lognormal "
                "multipliers with the nominal value as median.",
                "Yield sigmas describe the modelled expected yield; they "
                "exclude die-sampling noise.",
            ),
        )


class YieldWaferMapEngine:
    """F1 radial within-wafer yield map over the same assumptions."""

    name = "yield_wafer_map"
    version = "0.1.0"
    fidelity = "F1"

    def validate(self, scenario: Scenario) -> list[str]:
        errors: list[str] = []
        if scenario.samples < 1:
            errors.append("wafer map needs at least one sample")
        unknown = sorted(
            set(scenario.outputs) - SUPPORTED_WAFER_MAP_METRICS
        )
        if unknown:
            errors.append(
                "unsupported wafer map metric(s): " + ", ".join(unknown)
            )
        try:
            cfg, tech, assumptions, estimate, budget, package = (
                _load_inputs(scenario)
            )
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"cannot load wafer map inputs: {exc}")
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
        if assumptions.spatial is None:
            errors.append(
                "yield model needs a spatial mapping for the wafer map engine"
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
        spatial = assumptions.spatial
        if spatial is None:
            raise EngineError("yield model needs a spatial mapping")
        simulation = simulate_wafer_map(
            assumptions,
            estimate.die_area_mm2,
            budget.total_pads,
            samples=scenario.samples,
            seed=scenario.seed,
        )
        source = display_path(scenario.yield_path)
        model_version = f"{_MODEL_VERSION_PREFIX}@{assumptions.revision}"
        observations: list[Observation] = []
        for metric in scenario.outputs:
            unit, projector, uncertainty_projector = _WAFER_MAP_METRICS[metric]
            uncertainty = (
                None
                if uncertainty_projector is None
                else uncertainty_projector(simulation)
            )
            observations.append(
                Observation(
                    entity_type="wafer_map",
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
        for zone in simulation.zones:
            entity_id = f"zone:{zone.index}"
            for metric, value, unit in (
                (
                    "defect_density_per_cm2",
                    zone.defect_density_per_cm2,
                    "1/cm2",
                ),
                ("die_yield", zone.die_yield, "1"),
                ("die_count", float(zone.die_count), "1"),
                ("radius_mm", zone.r_mid_mm, "mm"),
            ):
                observations.append(
                    Observation(
                        entity_type="wafer_zone",
                        entity_id=entity_id,
                        metric=metric,
                        value=value,
                        unit=unit,
                        uncertainty=None,
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
                "spatial": {
                    "edge_boost": spatial.edge_boost,
                    "radial_exponent": spatial.radial_exponent,
                    "radial_bins": spatial.radial_bins,
                },
                "zones": [
                    {
                        "index": zone.index,
                        "r_min_mm": zone.r_min_mm,
                        "r_max_mm": zone.r_max_mm,
                        "r_mid_mm": zone.r_mid_mm,
                        "die_count": zone.die_count,
                        "defect_density_per_cm2": (
                            zone.defect_density_per_cm2
                        ),
                        "die_yield": zone.die_yield,
                    }
                    for zone in simulation.zones
                ],
                "simulation": {
                    "samples": scenario.samples,
                    "seed": scenario.seed,
                    "scope": (
                        "radial defect-density profile plus die and "
                        "assembly sampling; no angular or clustering "
                        "structure"
                    ),
                },
            },
            artifacts=(
                GeneratedArtifact(
                    "wafer_map.csv",
                    "text/csv",
                    wafer_map_csv(simulation),
                ),
                GeneratedArtifact(
                    "wafer_map.svg",
                    "image/svg+xml",
                    wafer_map_svg(
                        simulation,
                        title=f"{scenario.id} wafer map",
                    ),
                ),
            ),
            warnings=(
                "Wafer map is an F1 planning profile, not a measured "
                "wafer map.",
                "The radial density profile is an assumption; it carries "
                "no angular or spatial-clustering structure.",
                "Zone yields use modelled expected yield; the wafer mean "
                "and package counts include sampling noise.",
            ),
        )

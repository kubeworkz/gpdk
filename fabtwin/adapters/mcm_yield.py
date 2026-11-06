"""F1 G100 + PTA MCM assembly, KGD matching and package comparison adapter."""

from __future__ import annotations

from typing import Any, Callable

import yaml

from gpdk.block import load_chip
from gpdk.dtco import best_step, build_steps
from gpdk.mcm import McmEstimate, McmYieldAssumptions, simulate_mcm_yield
from gpdk.tech import load_tech

from ..errors import EngineError
from ..model import EngineResult, InputFile, Observation
from ..provenance import display_path
from ..scenario import Scenario
from .pta import _package_products, _read_mapping, _slug

_MODEL_VERSION_PREFIX = "mcm-yield"
_PRODUCT_METRICS: dict[
    str,
    tuple[str, str, Callable[[McmEstimate], float]],
] = {
    "g100_die_area_m2": (
        "g100",
        "m2",
        lambda estimate: estimate.g100_area_mm2 * 1e-6,
    ),
    "g100_die_yield": (
        "g100",
        "1",
        lambda estimate: estimate.g100_die_yield,
    ),
    "g100_known_good_dies_per_wafer": (
        "g100",
        "1",
        lambda estimate: estimate.g100_kgd_per_wafer,
    ),
    "pta_die_area_m2": (
        "pta",
        "m2",
        lambda estimate: estimate.pta_area_mm2 * 1e-6,
    ),
    "pta_die_yield": (
        "pta",
        "1",
        lambda estimate: estimate.pta_die_yield,
    ),
    "pta_known_good_dies_per_wafer": (
        "pta",
        "1",
        lambda estimate: estimate.pta_kgd_per_wafer,
    ),
    "kgd_match_yield": (
        "mcm",
        "1",
        lambda estimate: estimate.kgd_match_yield,
    ),
    "pta_wafers_per_g100_wafer": (
        "mcm",
        "1",
        lambda estimate: estimate.pta_wafers_per_g100_wafer,
    ),
}
_OPTION_METRICS: dict[str, tuple[str, Callable[[Any], float]]] = {
    "assembly_yield": (
        "1",
        lambda option: option.assembly_yield,
    ),
    "good_packages_per_g100_wafer": (
        "1",
        lambda option: option.good_packages_per_g100_wafer,
    ),
    "cost_per_good_package_usd": (
        "USD",
        lambda option: option.cost_per_good_package_usd,
    ),
}
SUPPORTED_METRICS = frozenset(
    (*_PRODUCT_METRICS, *_OPTION_METRICS)
)


def _load_inputs(scenario: Scenario):
    cfg = load_chip(scenario.chip_path)
    tech = load_tech(cfg.tech_file)
    if scenario.package_path is None:
        raise ValueError("MCM scenario requires inputs.package")
    if scenario.yield_path is None:
        raise ValueError("MCM scenario requires inputs.yield")
    package = _read_mapping(scenario.package_path, "MCM package")
    assumptions = McmYieldAssumptions.from_mapping(
        _read_mapping(scenario.yield_path, "MCM yield model")
    )
    estimate = best_step(build_steps(cfg)).iso
    simulation = simulate_mcm_yield(assumptions, estimate.die_area_mm2)
    return cfg, tech, package, assumptions, simulation


class McmYieldEngine:
    """F1 G100/PTA MCM assembly and package-option engine."""

    name = "mcm_yield"
    version = "0.1.0"
    fidelity = "F1"

    def validate(self, scenario: Scenario) -> list[str]:
        errors: list[str] = []
        if scenario.samples != 1:
            errors.append("mcm_yield is deterministic; samples must be 1")
        unknown = sorted(set(scenario.outputs) - SUPPORTED_METRICS)
        if unknown:
            errors.append(
                "unsupported MCM yield metric(s): " + ", ".join(unknown)
            )
        try:
            cfg, tech, package, assumptions, simulation = _load_inputs(
                scenario
            )
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"cannot load MCM yield inputs: {exc}")
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
        if assumptions.product != scenario.product:
            errors.append(
                f"MCM yield product {assumptions.product!r} does not match "
                f"scenario product {scenario.product!r}"
            )
        if assumptions.process.lower() != scenario.process.lower():
            errors.append(
                f"MCM yield process {assumptions.process!r} does not match "
                f"scenario process {scenario.process!r}"
            )
        if str(package.get("id")) != "mcm_si":
            errors.append("Phase 3 currently expects the mcm_si package definition")
        try:
            products = _package_products(package)
        except ValueError as exc:
            errors.append(str(exc))
            return errors
        if not {"g100", "pta"} <= products:
            errors.append("MCM package must reference both g100 and pta chiplets")
        if simulation.g100_gross_dies_per_wafer <= 0:
            errors.append("G100 does not fit on the wafer")
        return errors

    def run(self, scenario: Scenario) -> EngineResult:
        errors = self.validate(scenario)
        if errors:
            raise EngineError("; ".join(errors))
        cfg, tech, package, assumptions, simulation = _load_inputs(scenario)
        source = display_path(scenario.yield_path)
        model_version = f"{_MODEL_VERSION_PREFIX}@{assumptions.revision}"
        observations: list[Observation] = []
        for metric in scenario.outputs:
            if metric in _PRODUCT_METRICS:
                entity_id, unit, projector = _PRODUCT_METRICS[metric]
                observations.append(
                    Observation(
                        entity_type="product",
                        entity_id=entity_id,
                        metric=metric,
                        value=float(projector(simulation)),
                        unit=unit,
                        uncertainty=None,
                        evidence_class="assumed",
                        source_artifact=source,
                        model_version=model_version,
                    )
                )
            else:
                unit, projector = _OPTION_METRICS[metric]
                for option in simulation.options:
                    observations.append(
                        Observation(
                            entity_type="package_option",
                            entity_id=option.option.id,
                            metric=metric,
                            value=float(projector(option)),
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
        ]
        if tech.path is not None:
            input_files.append(InputFile(tech.path, "tech"))
        best_cost = simulation.best_option("cost")
        best_yield = simulation.best_option("yield")
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
                "package": {
                    "id": package.get("id"),
                    "revision": package.get("revision"),
                    "kind": package.get("kind"),
                },
                "g100": {
                    "die_area_mm2": simulation.g100_area_mm2,
                    "gross_dies_per_wafer": simulation.g100_gross_dies_per_wafer,
                    "die_yield": simulation.g100_die_yield,
                    "kgd_per_wafer": simulation.g100_kgd_per_wafer,
                },
                "pta": {
                    "die_area_mm2": simulation.pta_area_mm2,
                    "gross_dies_per_wafer": simulation.pta_gross_dies_per_wafer,
                    "die_yield": simulation.pta_die_yield,
                    "kgd_per_wafer": simulation.pta_kgd_per_wafer,
                },
                "kgd_match_yield": simulation.kgd_match_yield,
                "pta_wafers_per_g100_wafer": (
                    simulation.pta_wafers_per_g100_wafer
                ),
                "options": [
                    {
                        "id": option.option.id,
                        "name": option.option.name,
                        "kind": option.option.kind,
                        "assembly_yield": option.assembly_yield,
                        "good_packages_per_g100_wafer": (
                            option.good_packages_per_g100_wafer
                        ),
                        "cost_per_good_package_usd": (
                            option.cost_per_good_package_usd
                        ),
                    }
                    for option in simulation.options
                ],
                "best_cost_option": best_cost.option.id,
                "best_yield_option": best_yield.option.id,
                "simulation": {
                    "samples": 1,
                    "scope": (
                        "deterministic Poisson die yield, KGD test yield, "
                        "matched-pair supply and exponential assembly yield; "
                        "not a measured OSAT model"
                    ),
                },
            },
            warnings=(
                "Phase 3 MCM yield and package costs are F1 planning estimates, "
                "not measured OSAT data or vendor quotes.",
                "KGD matching assumes the test-yield factors in the assumptions "
                "file; test escapes and handling damage are not separately "
                "modelled.",
                "Package assembly, interconnect ppm and package costs are "
                "explicit assumptions; replace them with qualified package and "
                "assembly data before commitments.",
            ),
        )

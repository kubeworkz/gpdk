"""F1 planning model for G100 + PTA MCM assembly and package selection.

The model is deliberately deterministic. Die yield comes from the existing
Poisson critical-area model; KGD yield adds a test-yield factor; package
assembly yield uses the existing exponential per-interconnect model. Costs are
explicit planning assumptions, not OSAT quotes.

KGD matching is modelled by purchasing enough PTA wafers to supply every G100
known-good die. ``kgd_match_yield`` is the probability that a randomly selected
G100/PTA pair is known-good; the package assembly yield is conditional on using
matched KGD pairs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from .dieyield import (
    WaferSpec,
    die_grid,
    package_assembly_yield,
    poisson_die_yield,
)


def _mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"MCM yield model needs a {key!r} mapping")
    return value


def _number(raw: Mapping[str, Any], key: str, label: str) -> float:
    try:
        value = float(raw[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} needs numeric {key!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label}.{key} must be finite")
    return value


@dataclass(frozen=True)
class McmWaferSpec:
    diameter_mm: float
    edge_exclusion_mm: float
    scribe_lane_um: float
    g100_cost_usd: float
    pta_cost_usd: float

    def __post_init__(self) -> None:
        wafer = self.as_wafer()
        if wafer.diameter_mm <= 0 or wafer.usable_radius_mm <= 0:
            raise ValueError("MCM wafer geometry must be positive")
        if self.g100_cost_usd < 0 or self.pta_cost_usd < 0:
            raise ValueError("MCM wafer costs must be non-negative")

    def as_wafer(self) -> WaferSpec:
        return WaferSpec(
            diameter_mm=self.diameter_mm,
            edge_exclusion_mm=self.edge_exclusion_mm,
            scribe_lane_um=self.scribe_lane_um,
            cost_usd=0.0,
        )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "McmWaferSpec":
        return cls(
            diameter_mm=_number(raw, "diameter_mm", "wafer"),
            edge_exclusion_mm=_number(raw, "edge_exclusion_mm", "wafer"),
            scribe_lane_um=_number(raw, "scribe_lane_um", "wafer"),
            g100_cost_usd=_number(raw, "g100_cost_usd", "wafer"),
            pta_cost_usd=_number(raw, "pta_cost_usd", "wafer"),
        )


@dataclass(frozen=True)
class KgdSpec:
    critical_area_fraction: float
    defect_density_per_cm2: float
    kgd_test_yield: float
    test_cost_usd: float
    area_mm2: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.critical_area_fraction <= 1.0:
            raise ValueError("critical area fraction must be in [0, 1]")
        if self.defect_density_per_cm2 < 0:
            raise ValueError("defect density must be non-negative")
        if not 0.0 < self.kgd_test_yield <= 1.0:
            raise ValueError("KGD test yield must be in (0, 1]")
        if self.test_cost_usd < 0:
            raise ValueError("test cost must be non-negative")
        if self.area_mm2 is not None and self.area_mm2 <= 0:
            raise ValueError("die area must be positive")

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any], label: str
    ) -> "KgdSpec":
        area = raw.get("area_mm2")
        return cls(
            area_mm2=None if area is None else float(area),
            critical_area_fraction=_number(
                raw, "critical_area_fraction", label
            ),
            defect_density_per_cm2=_number(
                raw, "defect_density_per_cm2", label
            ),
            kgd_test_yield=_number(raw, "kgd_test_yield", label),
            test_cost_usd=_number(raw, "test_cost_usd", label),
        )


@dataclass(frozen=True)
class PackageOption:
    id: str
    name: str
    kind: str
    assembly_base_yield: float
    interconnect_count: int
    per_interconnect_ppm: float
    package_cost_usd: float

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.kind:
            raise ValueError("package option needs id, name and kind")
        if not 0.0 <= self.assembly_base_yield <= 1.0:
            raise ValueError("assembly base yield must be in [0, 1]")
        if self.interconnect_count <= 0:
            raise ValueError("interconnect count must be positive")
        if self.per_interconnect_ppm < 0:
            raise ValueError("per-interconnect ppm must be non-negative")
        if self.package_cost_usd < 0:
            raise ValueError("package cost must be non-negative")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PackageOption":
        return cls(
            id=str(raw["id"]),
            name=str(raw["name"]),
            kind=str(raw["kind"]),
            assembly_base_yield=_number(
                raw, "assembly_base_yield", "package option"
            ),
            interconnect_count=int(raw["interconnect_count"]),
            per_interconnect_ppm=_number(
                raw, "per_interconnect_ppm", "package option"
            ),
            package_cost_usd=_number(
                raw, "package_cost_usd", "package option"
            ),
        )


@dataclass(frozen=True)
class McmYieldAssumptions:
    id: str
    product: str
    process: str
    revision: str
    description: str
    wafer: McmWaferSpec
    g100: KgdSpec
    pta: KgdSpec
    package_options: tuple[PackageOption, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.product or not self.process:
            raise ValueError("MCM yield model needs id, product and process")
        if not self.package_options:
            raise ValueError("MCM yield model needs package options")
        ids = [option.id for option in self.package_options]
        if len(set(ids)) != len(ids):
            raise ValueError("package option ids must be unique")
        if self.pta.area_mm2 is None:
            raise ValueError("PTA KGD model needs an area_mm2")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "McmYieldAssumptions":
        options_raw = raw.get("package_options")
        if not isinstance(options_raw, list) or not options_raw:
            raise ValueError("MCM yield model needs package_options")
        options: list[PackageOption] = []
        for item in options_raw:
            if not isinstance(item, Mapping):
                raise ValueError("each package option must be a mapping")
            options.append(PackageOption.from_mapping(item))
        return cls(
            id=str(raw["id"]),
            product=str(raw["product"]),
            process=str(raw["process"]),
            revision=str(raw.get("revision", "0.1.0")),
            description=str(raw.get("description", "")).strip(),
            wafer=McmWaferSpec.from_mapping(_mapping(raw, "wafer")),
            g100=KgdSpec.from_mapping(_mapping(raw, "g100"), "g100"),
            pta=KgdSpec.from_mapping(_mapping(raw, "pta"), "pta"),
            package_options=tuple(options),
        )


@dataclass(frozen=True)
class PackageOptionEstimate:
    option: PackageOption
    assembly_yield: float
    good_packages_per_g100_wafer: float
    cost_per_good_package_usd: float


@dataclass(frozen=True)
class McmEstimate:
    g100_area_mm2: float
    g100_gross_dies_per_wafer: int
    g100_die_yield: float
    g100_kgd_per_wafer: float
    pta_area_mm2: float
    pta_gross_dies_per_wafer: int
    pta_die_yield: float
    pta_kgd_per_wafer: float
    pta_wafers_per_g100_wafer: float
    kgd_match_yield: float
    options: tuple[PackageOptionEstimate, ...]

    def best_option(self, key: str) -> PackageOptionEstimate:
        if key == "cost":
            return min(self.options, key=lambda item: item.cost_per_good_package_usd)
        if key == "yield":
            return max(
                self.options,
                key=lambda item: item.good_packages_per_g100_wafer,
            )
        raise ValueError("best option key must be 'cost' or 'yield'")


def simulate_mcm_yield(
    assumptions: McmYieldAssumptions,
    g100_area_mm2: float,
) -> McmEstimate:
    """Evaluate G100/PTA KGD matching and each package option."""
    if g100_area_mm2 <= 0:
        raise ValueError("G100 die area must be positive")
    if assumptions.pta.area_mm2 is None:
        raise ValueError("PTA KGD model needs an area_mm2")
    pta_area_mm2 = assumptions.pta.area_mm2
    wafer = assumptions.wafer.as_wafer()
    g100_side = math.sqrt(g100_area_mm2)
    pta_side = math.sqrt(pta_area_mm2)
    g100_grid = die_grid(wafer, g100_side, g100_side)
    pta_grid = die_grid(wafer, pta_side, pta_side)
    if g100_grid.count == 0 or pta_grid.count == 0:
        raise ValueError("G100 or PTA die does not fit on the wafer")

    g100_die_yield = poisson_die_yield(
        g100_area_mm2,
        assumptions.g100.critical_area_fraction,
        assumptions.g100.defect_density_per_cm2,
    )
    pta_die_yield = poisson_die_yield(
        pta_area_mm2,
        assumptions.pta.critical_area_fraction,
        assumptions.pta.defect_density_per_cm2,
    )
    g100_kgd_yield = g100_die_yield * assumptions.g100.kgd_test_yield
    pta_kgd_yield = pta_die_yield * assumptions.pta.kgd_test_yield
    g100_kgd = g100_grid.count * g100_kgd_yield
    pta_kgd = pta_grid.count * pta_kgd_yield
    pta_wafers_per_g100_wafer = g100_kgd / pta_kgd
    kgd_match_yield = g100_kgd_yield * pta_kgd_yield
    fixed_cost = (
        assumptions.wafer.g100_cost_usd
        + pta_wafers_per_g100_wafer * assumptions.wafer.pta_cost_usd
        + g100_grid.count * assumptions.g100.test_cost_usd
        + pta_grid.count
        * pta_wafers_per_g100_wafer
        * assumptions.pta.test_cost_usd
    )

    package_results: list[PackageOptionEstimate] = []
    for option in assumptions.package_options:
        assembly = package_assembly_yield(
            option.interconnect_count,
            option.assembly_base_yield,
            option.per_interconnect_ppm,
        )
        good_packages = g100_kgd * assembly
        total = fixed_cost + g100_kgd * option.package_cost_usd
        package_results.append(
            PackageOptionEstimate(
                option=option,
                assembly_yield=assembly,
                good_packages_per_g100_wafer=good_packages,
                cost_per_good_package_usd=total / good_packages,
            )
        )
    return McmEstimate(
        g100_area_mm2=g100_area_mm2,
        g100_gross_dies_per_wafer=g100_grid.count,
        g100_die_yield=g100_die_yield,
        g100_kgd_per_wafer=g100_kgd,
        pta_area_mm2=pta_area_mm2,
        pta_gross_dies_per_wafer=pta_grid.count,
        pta_die_yield=pta_die_yield,
        pta_kgd_per_wafer=pta_kgd,
        pta_wafers_per_g100_wafer=pta_wafers_per_g100_wafer,
        kgd_match_yield=kgd_match_yield,
        options=tuple(package_results),
    )

"""F0 die-per-wafer and package-yield planning model.

This is a deliberately small yield model. It does not pretend to be a foundry
yield model: the wafer geometry is exact for the stated grid, the defect model is
a Poisson critical-area approximation, and every package/assembly/cost number is
an explicit planning assumption. The point is to make the assumptions visible
and the sensitivity reproducible.

The wafer map uses square die sites. A die is counted only when all four corners
lie inside the usable wafer radius; partial edge die are excluded.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, replace
from typing import Any, Mapping

_CM2_PER_MM2 = 0.01


@dataclass(frozen=True)
class WaferSpec:
    diameter_mm: float = 300.0
    edge_exclusion_mm: float = 3.0
    scribe_lane_um: float = 80.0
    cost_usd: float = 4500.0

    def __post_init__(self) -> None:
        if self.diameter_mm <= 0:
            raise ValueError("wafer diameter must be positive")
        if self.edge_exclusion_mm < 0:
            raise ValueError("edge exclusion must be non-negative")
        if self.diameter_mm / 2.0 <= self.edge_exclusion_mm:
            raise ValueError("edge exclusion must leave a positive wafer radius")
        if self.scribe_lane_um < 0:
            raise ValueError("scribe lane must be non-negative")
        if self.cost_usd < 0:
            raise ValueError("wafer cost must be non-negative")

    @property
    def usable_radius_mm(self) -> float:
        return self.diameter_mm / 2.0 - self.edge_exclusion_mm

    @property
    def scribe_lane_mm(self) -> float:
        return self.scribe_lane_um / 1000.0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "WaferSpec":
        return cls(
            diameter_mm=float(raw.get("diameter_mm", 300.0)),
            edge_exclusion_mm=float(raw.get("edge_exclusion_mm", 3.0)),
            scribe_lane_um=float(raw.get("scribe_lane_um", 80.0)),
            cost_usd=float(raw.get("cost_usd", 4500.0)),
        )


@dataclass(frozen=True)
class DieGrid:
    die_x_mm: float
    die_y_mm: float
    positions: tuple[tuple[float, float], ...]

    @property
    def count(self) -> int:
        return len(self.positions)


@dataclass(frozen=True)
class YieldAssumptions:
    id: str
    product: str
    process: str
    revision: str
    wafer: WaferSpec
    defect_density_per_cm2: float
    critical_area_fraction: float
    base_assembly_yield: float
    per_pad_defect_ppm: float
    package_cost_usd: float
    test_cost_usd: float
    description: str = ""
    variation: VariationSpec | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("yield assumption id must not be empty")
        if self.defect_density_per_cm2 < 0:
            raise ValueError("defect density must be non-negative")
        if not 0.0 <= self.critical_area_fraction <= 1.0:
            raise ValueError("critical area fraction must be in [0, 1]")
        if not 0.0 <= self.base_assembly_yield <= 1.0:
            raise ValueError("base assembly yield must be in [0, 1]")
        if self.per_pad_defect_ppm < 0:
            raise ValueError("per-pad defect rate must be non-negative")
        if self.package_cost_usd < 0:
            raise ValueError("package cost must be non-negative")
        if self.test_cost_usd < 0:
            raise ValueError("test cost must be non-negative")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "YieldAssumptions":
        wafer = raw.get("wafer")
        defects = raw.get("defects")
        assembly = raw.get("assembly")
        if not isinstance(wafer, Mapping):
            raise ValueError("yield model needs a wafer mapping")
        if not isinstance(defects, Mapping):
            raise ValueError("yield model needs a defects mapping")
        if not isinstance(assembly, Mapping):
            raise ValueError("yield model needs an assembly mapping")
        return cls(
            id=str(raw["id"]),
            product=str(raw["product"]),
            process=str(raw["process"]),
            revision=str(raw.get("revision", "0.1.0")),
            wafer=WaferSpec.from_mapping(wafer),
            defect_density_per_cm2=float(
                defects.get("density_per_cm2", 0.08)
            ),
            critical_area_fraction=float(
                defects.get("critical_area_fraction", 0.35)
            ),
            base_assembly_yield=float(
                assembly.get("base_yield", 0.995)
            ),
            per_pad_defect_ppm=float(
                assembly.get("per_pad_defect_ppm", 8.0)
            ),
            package_cost_usd=float(assembly.get("package_cost_usd", 1.20)),
            test_cost_usd=float(assembly.get("test_cost_usd", 0.40)),
            description=str(raw.get("description", "")).strip(),
            variation=(
                VariationSpec.from_mapping(raw)
                if "variation" in raw
                else None
            ),
        )


@dataclass(frozen=True)
class SensitivitySpec:
    defect_density_per_cm2: tuple[float, ...]
    pad_counts: tuple[int, ...]
    assembly_per_pad_ppm: tuple[float, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SensitivitySpec":
        sensitivity = raw.get("sensitivity")
        if not isinstance(sensitivity, Mapping):
            raise ValueError("yield model needs a sensitivity mapping")
        densities = tuple(
            float(value)
            for value in sensitivity.get("defect_density_per_cm2", [])
        )
        pads = tuple(
            int(value) for value in sensitivity.get("pad_counts", [])
        )
        ppm = tuple(
            float(value)
            for value in sensitivity.get("assembly_per_pad_ppm", [])
        )
        if not densities or not pads or not ppm:
            raise ValueError("sensitivity lists must not be empty")
        if any(value < 0 for value in densities):
            raise ValueError("defect densities must be non-negative")
        if any(value <= 0 for value in pads):
            raise ValueError("pad counts must be positive")
        if any(value < 0 for value in ppm):
            raise ValueError("assembly ppm values must be non-negative")
        return cls(densities, pads, ppm)


@dataclass(frozen=True)
class VariationSpec:
    """Lognormal lot/wafer variation around the nominal yield assumptions.

    Coefficients of variation apply to lognormal multipliers whose median is
    the nominal value. Defect density varies per lot and again per wafer;
    assembly per-pad defect ppm varies per assembly lot.
    """

    wafers_per_lot: int = 25
    defect_density_cv_lot: float = 0.15
    defect_density_cv_wafer: float = 0.10
    assembly_ppm_cv_lot: float = 0.10

    def __post_init__(self) -> None:
        if self.wafers_per_lot < 2:
            raise ValueError("variation needs at least two wafers per lot")
        for name in (
            "defect_density_cv_lot",
            "defect_density_cv_wafer",
            "assembly_ppm_cv_lot",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "VariationSpec":
        variation = raw.get("variation")
        if not isinstance(variation, Mapping):
            raise ValueError("yield model needs a variation mapping")
        return cls(
            wafers_per_lot=int(variation.get("wafers_per_lot", 25)),
            defect_density_cv_lot=float(
                variation.get("defect_density_cv_lot", 0.15)
            ),
            defect_density_cv_wafer=float(
                variation.get("defect_density_cv_wafer", 0.10)
            ),
            assembly_ppm_cv_lot=float(
                variation.get("assembly_ppm_cv_lot", 0.10)
            ),
        )


@dataclass(frozen=True)
class YieldEstimate:
    die_area_mm2: float
    critical_area_mm2: float
    gross_dies_per_wafer: int
    die_yield: float
    die_yield_stderr: float | None
    known_good_dies_per_wafer: float
    known_good_dies_stderr: float | None
    assembly_yield: float
    good_packages_per_wafer: float
    good_packages_stderr: float | None
    cost_per_known_good_die_usd: float
    cost_per_good_package_usd: float
    cost_per_good_package_stderr: float | None
    wafer_utilization: float
    samples: int

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "die_area_mm2": self.die_area_mm2,
            "critical_area_mm2": self.critical_area_mm2,
            "gross_dies_per_wafer": self.gross_dies_per_wafer,
            "die_yield": self.die_yield,
            "die_yield_stderr": self.die_yield_stderr,
            "known_good_dies_per_wafer": self.known_good_dies_per_wafer,
            "known_good_dies_stderr": self.known_good_dies_stderr,
            "assembly_yield": self.assembly_yield,
            "good_packages_per_wafer": self.good_packages_per_wafer,
            "good_packages_stderr": self.good_packages_stderr,
            "cost_per_known_good_die_usd": self.cost_per_known_good_die_usd,
            "cost_per_good_package_usd": self.cost_per_good_package_usd,
            "cost_per_good_package_stderr": self.cost_per_good_package_stderr,
            "wafer_utilization": self.wafer_utilization,
            "samples": self.samples,
        }


@dataclass(frozen=True)
class LotEstimate:
    die_area_mm2: float
    critical_area_mm2: float
    gross_dies_per_wafer: int
    lots: int
    wafers_per_lot: int
    wafers: int
    die_yield_mean: float
    die_yield_stderr: float | None
    wafer_to_wafer_die_yield_sigma: float
    lot_to_lot_die_yield_sigma: float
    assembly_yield_mean: float
    assembly_yield_stderr: float | None
    good_packages_per_wafer_mean: float
    good_packages_stderr: float | None
    cost_per_good_package_usd_mean: float
    cost_per_good_package_stderr: float | None

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "die_area_mm2": self.die_area_mm2,
            "critical_area_mm2": self.critical_area_mm2,
            "gross_dies_per_wafer": self.gross_dies_per_wafer,
            "lots": self.lots,
            "wafers_per_lot": self.wafers_per_lot,
            "wafers": self.wafers,
            "die_yield_mean": self.die_yield_mean,
            "die_yield_stderr": self.die_yield_stderr,
            "wafer_to_wafer_die_yield_sigma": (
                self.wafer_to_wafer_die_yield_sigma
            ),
            "lot_to_lot_die_yield_sigma": self.lot_to_lot_die_yield_sigma,
            "assembly_yield_mean": self.assembly_yield_mean,
            "assembly_yield_stderr": self.assembly_yield_stderr,
            "good_packages_per_wafer_mean": (
                self.good_packages_per_wafer_mean
            ),
            "good_packages_stderr": self.good_packages_stderr,
            "cost_per_good_package_usd_mean": (
                self.cost_per_good_package_usd_mean
            ),
            "cost_per_good_package_stderr": (
                self.cost_per_good_package_stderr
            ),
        }


def die_grid(
    wafer: WaferSpec,
    die_x_mm: float,
    die_y_mm: float,
) -> DieGrid:
    """Place square/rectangular die on a centered grid and drop edge partials."""
    if die_x_mm <= 0 or die_y_mm <= 0:
        raise ValueError("die dimensions must be positive")
    pitch_x = die_x_mm + wafer.scribe_lane_mm
    pitch_y = die_y_mm + wafer.scribe_lane_mm
    radius = wafer.usable_radius_mm
    if pitch_x > 2.0 * radius or pitch_y > 2.0 * radius:
        return DieGrid(die_x_mm, die_y_mm, ())

    n_x = int(math.floor(2.0 * radius / pitch_x))
    n_y = int(math.floor(2.0 * radius / pitch_y))
    positions: list[tuple[float, float]] = []
    x0 = -(n_x - 1) * pitch_x / 2.0
    y0 = -(n_y - 1) * pitch_y / 2.0
    half_x = die_x_mm / 2.0
    half_y = die_y_mm / 2.0
    for row in range(n_y):
        y = y0 + row * pitch_y
        for column in range(n_x):
            x = x0 + column * pitch_x
            if math.hypot(abs(x) + half_x, abs(y) + half_y) <= radius + 1e-9:
                positions.append((x, y))
    return DieGrid(die_x_mm, die_y_mm, tuple(positions))


def critical_area_mm2(die_area_mm2: float, fraction: float) -> float:
    if die_area_mm2 <= 0:
        raise ValueError("die area must be positive")
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("critical area fraction must be in [0, 1]")
    return die_area_mm2 * fraction


def poisson_die_yield(
    die_area_mm2: float,
    critical_area_fraction: float,
    defect_density_per_cm2: float,
) -> float:
    """Poisson yield for a critical area; D is defects per cm2."""
    if defect_density_per_cm2 < 0:
        raise ValueError("defect density must be non-negative")
    critical_cm2 = (
        critical_area_mm2(die_area_mm2, critical_area_fraction)
        * _CM2_PER_MM2
    )
    return math.exp(-critical_cm2 * defect_density_per_cm2)


def package_assembly_yield(
    pad_count: int,
    base_yield: float,
    per_pad_defect_ppm: float,
) -> float:
    """Planning assembly yield with an exponential per-pad defect term."""
    if pad_count < 0:
        raise ValueError("pad count must be non-negative")
    if not 0.0 <= base_yield <= 1.0:
        raise ValueError("base yield must be in [0, 1]")
    if per_pad_defect_ppm < 0:
        raise ValueError("per-pad defect rate must be non-negative")
    value = base_yield * math.exp(
        -pad_count * per_pad_defect_ppm * 1e-6
    )
    return min(1.0, max(0.0, value))


def _mean_stderr(values: list[float]) -> tuple[float, float | None]:
    if not values:
        raise ValueError("cannot summarize an empty sample")
    mean = statistics.fmean(values)
    if len(values) < 2:
        return mean, None
    return mean, statistics.stdev(values) / math.sqrt(len(values))


def _lognormal_sigma(cv: float) -> float:
    if cv < 0:
        raise ValueError("coefficient of variation must be non-negative")
    return math.sqrt(math.log1p(cv * cv))


def _sample_wafer(
    rng: random.Random,
    die_count: int,
    die_yield: float,
    assembly_yield: float,
) -> tuple[int, int]:
    good_dies = sum(1 for _ in range(die_count) if rng.random() < die_yield)
    good_packages = sum(
        1 for _ in range(good_dies) if rng.random() < assembly_yield
    )
    return good_dies, good_packages


def _wafer_cost(
    assumptions: YieldAssumptions,
    die_count: int,
    good_die_count: int,
    good_package_count: int,
) -> float | None:
    if not good_package_count:
        return None
    total_cost = (
        assumptions.wafer.cost_usd
        + die_count * assumptions.test_cost_usd
        + good_die_count * assumptions.package_cost_usd
    )
    return total_cost / good_package_count


def simulate_yield(
    assumptions: YieldAssumptions,
    die_area_mm2: float,
    pad_count: int,
    *,
    samples: int = 1000,
    seed: int = 0,
) -> YieldEstimate:
    """Run a seeded die/assembly yield simulation and summarize one wafer."""
    if die_area_mm2 <= 0:
        raise ValueError("die area must be positive")
    if pad_count < 0:
        raise ValueError("pad count must be non-negative")
    if samples < 1:
        raise ValueError("samples must be at least one")

    side_mm = math.sqrt(die_area_mm2)
    grid = die_grid(assumptions.wafer, side_mm, side_mm)
    if grid.count == 0:
        raise ValueError("die does not fit on the wafer")
    die_yield = poisson_die_yield(
        die_area_mm2,
        assumptions.critical_area_fraction,
        assumptions.defect_density_per_cm2,
    )
    assembly = package_assembly_yield(
        pad_count,
        assumptions.base_assembly_yield,
        assumptions.per_pad_defect_ppm,
    )
    rng = random.Random(seed)
    die_yields: list[float] = []
    good_dies: list[float] = []
    good_packages: list[float] = []
    package_costs: list[float] = []
    for _ in range(samples):
        good_die_count, good_package_count = _sample_wafer(
            rng, grid.count, die_yield, assembly
        )
        die_yields.append(good_die_count / grid.count)
        good_dies.append(float(good_die_count))
        good_packages.append(float(good_package_count))
        cost = _wafer_cost(
            assumptions,
            grid.count,
            good_die_count,
            good_package_count,
        )
        if cost is not None:
            package_costs.append(cost)

    if not package_costs:
        raise ValueError(
            "no good packages in any sample; cost per good package is "
            "undefined"
        )
    die_mean, die_stderr = _mean_stderr(die_yields)
    good_die_mean, good_die_stderr = _mean_stderr(good_dies)
    package_mean, package_stderr = _mean_stderr(good_packages)
    cost_mean, cost_stderr = _mean_stderr(package_costs)
    utilization = (
        grid.count * die_area_mm2
        / (math.pi * assumptions.wafer.usable_radius_mm**2)
    )
    return YieldEstimate(
        die_area_mm2=die_area_mm2,
        critical_area_mm2=critical_area_mm2(
            die_area_mm2, assumptions.critical_area_fraction
        ),
        gross_dies_per_wafer=grid.count,
        die_yield=die_mean,
        die_yield_stderr=die_stderr,
        known_good_dies_per_wafer=good_die_mean,
        known_good_dies_stderr=good_die_stderr,
        assembly_yield=assembly,
        good_packages_per_wafer=package_mean,
        good_packages_stderr=package_stderr,
        cost_per_known_good_die_usd=(
            assumptions.wafer.cost_usd / good_die_mean
        ),
        cost_per_good_package_usd=cost_mean,
        cost_per_good_package_stderr=cost_stderr,
        wafer_utilization=utilization,
        samples=samples,
    )


def simulate_lot_yield(
    assumptions: YieldAssumptions,
    die_area_mm2: float,
    pad_count: int,
    *,
    lots: int = 40,
    seed: int = 0,
) -> LotEstimate:
    """Simulate lots with lognormal defect-density and assembly variation.

    Defect density is drawn once per lot and again per wafer around the lot
    value; per-pad assembly ppm is drawn once per assembly lot. The reported
    yield sigmas describe the modelled expected die yield, so they exclude
    die-sampling noise. Good-package and cost means come from sampled wafers
    and therefore include sampling noise.
    """
    if die_area_mm2 <= 0:
        raise ValueError("die area must be positive")
    if pad_count < 0:
        raise ValueError("pad count must be non-negative")
    if lots < 2:
        raise ValueError("lot simulation must cover at least two lots")
    variation = assumptions.variation
    if variation is None:
        raise ValueError("lot simulation requires a variation mapping")

    side_mm = math.sqrt(die_area_mm2)
    grid = die_grid(assumptions.wafer, side_mm, side_mm)
    if grid.count == 0:
        raise ValueError("die does not fit on the wafer")
    sigma_lot = _lognormal_sigma(variation.defect_density_cv_lot)
    sigma_wafer = _lognormal_sigma(variation.defect_density_cv_wafer)
    sigma_ppm = _lognormal_sigma(variation.assembly_ppm_cv_lot)
    rng = random.Random(seed)
    lot_yields: list[float] = []
    lot_packages: list[float] = []
    lot_costs: list[float] = []
    lot_assembly: list[float] = []
    within_lot_variances: list[float] = []
    for _ in range(lots):
        density_lot = assumptions.defect_density_per_cm2 * math.exp(
            rng.gauss(0.0, sigma_lot)
        )
        ppm_lot = assumptions.per_pad_defect_ppm * math.exp(
            rng.gauss(0.0, sigma_ppm)
        )
        assembly = package_assembly_yield(
            pad_count,
            assumptions.base_assembly_yield,
            ppm_lot,
        )
        wafer_yields: list[float] = []
        wafer_packages: list[float] = []
        wafer_costs: list[float] = []
        for _ in range(variation.wafers_per_lot):
            density = density_lot * math.exp(rng.gauss(0.0, sigma_wafer))
            expected_yield = poisson_die_yield(
                die_area_mm2,
                assumptions.critical_area_fraction,
                density,
            )
            good_dies, good_packages = _sample_wafer(
                rng,
                grid.count,
                expected_yield,
                assembly,
            )
            wafer_yields.append(expected_yield)
            wafer_packages.append(float(good_packages))
            cost = _wafer_cost(
                assumptions,
                grid.count,
                good_dies,
                good_packages,
            )
            if cost is not None:
                wafer_costs.append(cost)
        if not wafer_costs:
            raise ValueError(
                "no good packages in a lot; cost per good package is "
                "undefined"
            )
        lot_yields.append(statistics.fmean(wafer_yields))
        lot_packages.append(statistics.fmean(wafer_packages))
        lot_costs.append(statistics.fmean(wafer_costs))
        lot_assembly.append(assembly)
        within_lot_variances.append(statistics.variance(wafer_yields))

    die_mean, die_stderr = _mean_stderr(lot_yields)
    package_mean, package_stderr = _mean_stderr(lot_packages)
    cost_mean, cost_stderr = _mean_stderr(lot_costs)
    assembly_mean, assembly_stderr = _mean_stderr(lot_assembly)
    return LotEstimate(
        die_area_mm2=die_area_mm2,
        critical_area_mm2=critical_area_mm2(
            die_area_mm2, assumptions.critical_area_fraction
        ),
        gross_dies_per_wafer=grid.count,
        lots=lots,
        wafers_per_lot=variation.wafers_per_lot,
        wafers=lots * variation.wafers_per_lot,
        die_yield_mean=die_mean,
        die_yield_stderr=die_stderr,
        wafer_to_wafer_die_yield_sigma=math.sqrt(
            statistics.fmean(within_lot_variances)
        ),
        lot_to_lot_die_yield_sigma=statistics.stdev(lot_yields),
        assembly_yield_mean=assembly_mean,
        assembly_yield_stderr=assembly_stderr,
        good_packages_per_wafer_mean=package_mean,
        good_packages_stderr=package_stderr,
        cost_per_good_package_usd_mean=cost_mean,
        cost_per_good_package_stderr=cost_stderr,
    )


def defect_density_curve(
    assumptions: YieldAssumptions,
    die_area_mm2: float,
    pad_count: int,
    densities: tuple[float, ...],
    *,
    samples: int = 200,
    seed: int = 0,
) -> list[dict[str, float]]:
    """Return a seeded yield/cost curve over defect densities."""
    rows: list[dict[str, float]] = []
    for index, density in enumerate(densities):
        scenario = replace(assumptions, defect_density_per_cm2=density)
        estimate = simulate_yield(
            scenario,
            die_area_mm2,
            pad_count,
            samples=samples,
            seed=seed + index,
        )
        rows.append(
            {
                "defect_density_per_cm2": density,
                "die_yield": estimate.die_yield,
                "die_yield_stderr": estimate.die_yield_stderr or 0.0,
                "good_packages_per_wafer": estimate.good_packages_per_wafer,
                "good_packages_stderr": (
                    estimate.good_packages_stderr or 0.0
                ),
                "cost_per_good_package_usd": (
                    estimate.cost_per_good_package_usd
                ),
                "cost_per_good_package_stderr": (
                    estimate.cost_per_good_package_stderr or 0.0
                ),
            }
        )
    return rows


def pad_count_curve(
    assumptions: YieldAssumptions,
    die_area_mm2: float,
    pad_counts: tuple[int, ...],
    *,
    samples: int = 200,
    seed: int = 0,
) -> list[dict[str, float]]:
    """Return a seeded assembly-yield curve over pad counts."""
    rows: list[dict[str, float]] = []
    for index, pad_count in enumerate(pad_counts):
        estimate = simulate_yield(
            assumptions,
            die_area_mm2,
            pad_count,
            samples=samples,
            seed=seed + index,
        )
        rows.append(
            {
                "pad_count": float(pad_count),
                "die_yield": estimate.die_yield,
                "die_yield_stderr": estimate.die_yield_stderr or 0.0,
                "good_packages_per_wafer": estimate.good_packages_per_wafer,
                "good_packages_stderr": (
                    estimate.good_packages_stderr or 0.0
                ),
                "cost_per_good_package_usd": (
                    estimate.cost_per_good_package_usd
                ),
                "cost_per_good_package_stderr": (
                    estimate.cost_per_good_package_stderr or 0.0
                ),
            }
        )
    return rows


def assembly_tolerance_curve(
    assumptions: YieldAssumptions,
    die_area_mm2: float,
    pad_count: int,
    ppm_values: tuple[float, ...],
    *,
    samples: int = 200,
    seed: int = 0,
) -> list[dict[str, float]]:
    """Return a seeded assembly-yield curve over per-pad defect ppm."""
    rows: list[dict[str, float]] = []
    for index, ppm in enumerate(ppm_values):
        scenario = replace(assumptions, per_pad_defect_ppm=ppm)
        estimate = simulate_yield(
            scenario,
            die_area_mm2,
            pad_count,
            samples=samples,
            seed=seed + index,
        )
        rows.append(
            {
                "assembly_per_pad_ppm": ppm,
                "die_yield": estimate.die_yield,
                "die_yield_stderr": estimate.die_yield_stderr or 0.0,
                "good_packages_per_wafer": estimate.good_packages_per_wafer,
                "good_packages_stderr": (
                    estimate.good_packages_stderr or 0.0
                ),
                "cost_per_good_package_usd": (
                    estimate.cost_per_good_package_usd
                ),
                "cost_per_good_package_stderr": (
                    estimate.cost_per_good_package_stderr or 0.0
                ),
            }
        )
    return rows

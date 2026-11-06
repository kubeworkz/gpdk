"""F1 analytical silicon-photonic and thermal planning model for the PTA.

The model is intentionally small and auditable. It propagates five planning
distributions through a per-MZI phase model and a 1D interposer thermal path:

* waveguide width error -> effective-index shift -> phase error,
* etch-depth error -> effective-index shift -> phase error,
* line-edge roughness -> scattering loss,
* ambient temperature plus electronic-die heat -> phase error,
* package alignment -> coupling loss.

It does not model a full MZI transfer matrix, a qualified SiPh PDK, or full-chip
thermal FEA. Every value is an assumption, not measured silicon data.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Any, Mapping

_TWO_PI = 2.0 * math.pi


def _mapping(raw: Mapping[str, Any], key: str, label: str) -> Mapping[str, Any]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} needs a {key!r} mapping")
    return value


def _float(mapping: Mapping[str, Any], key: str, label: str) -> float:
    try:
        value = float(mapping[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} needs numeric {key!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label}.{key} must be finite")
    return value


def _int(mapping: Mapping[str, Any], key: str, label: str) -> int:
    try:
        value = int(mapping[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} needs integer {key!r}") from exc
    return value


@dataclass(frozen=True)
class GaussianParameter:
    """A normal planning distribution with an optional non-negative sample."""

    mean: float
    sigma: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.mean):
            raise ValueError("distribution mean must be finite")
        if not math.isfinite(self.sigma) or self.sigma < 0.0:
            raise ValueError("distribution sigma must be finite and non-negative")

    @classmethod
    def from_mapping(
        cls, raw: Any, label: str
    ) -> "GaussianParameter":
        if not isinstance(raw, Mapping):
            raise ValueError(f"{label} must be a mapping")
        return cls(
            mean=_float(raw, "mean", label),
            sigma=_float(raw, "sigma", label),
        )

    def sample(self, rng: random.Random, *, nonnegative: bool = False) -> float:
        value = rng.gauss(self.mean, self.sigma)
        return max(0.0, value) if nonnegative else value


@dataclass(frozen=True)
class OpticalSpec:
    """Optical material, loss, heater and tensor-error assumptions."""

    wavelength_nm: float
    effective_index: float
    nominal_width_nm: float
    nominal_etch_depth_nm: float
    width_sensitivity_per_nm: float
    etch_sensitivity_per_nm: float
    thermo_optic_per_k: float
    laser_drift_nm_per_k: float
    base_loss_db_per_cm: float
    scattering_loss_db_per_cm_nm2: float
    coupling_loss_db: float
    alignment_loss_db_per_um2: float
    heater_power_mw_per_2pi: float
    mesh_excess_loss_db: float

    def __post_init__(self) -> None:
        if self.wavelength_nm <= 0.0:
            raise ValueError("wavelength must be positive")
        if self.effective_index <= 0.0:
            raise ValueError("effective index must be positive")
        if self.nominal_width_nm <= 0.0:
            raise ValueError("nominal width must be positive")
        if self.nominal_etch_depth_nm <= 0.0:
            raise ValueError("nominal etch depth must be positive")
        if not math.isfinite(self.width_sensitivity_per_nm):
            raise ValueError("width sensitivity must be finite")
        if not math.isfinite(self.etch_sensitivity_per_nm):
            raise ValueError("etch sensitivity must be finite")
        for name in (
            "thermo_optic_per_k",
            "laser_drift_nm_per_k",
            "base_loss_db_per_cm",
            "scattering_loss_db_per_cm_nm2",
            "coupling_loss_db",
            "alignment_loss_db_per_um2",
            "heater_power_mw_per_2pi",
            "mesh_excess_loss_db",
        ):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "OpticalSpec":
        optical = _mapping(raw, "optical", "photonic model")
        return cls(
            wavelength_nm=_float(optical, "wavelength_nm", "optical"),
            effective_index=_float(optical, "effective_index", "optical"),
            nominal_width_nm=_float(optical, "nominal_width_nm", "optical"),
            nominal_etch_depth_nm=_float(
                optical, "nominal_etch_depth_nm", "optical"
            ),
            width_sensitivity_per_nm=_float(
                optical, "width_sensitivity_per_nm", "optical"
            ),
            etch_sensitivity_per_nm=_float(
                optical, "etch_sensitivity_per_nm", "optical"
            ),
            thermo_optic_per_k=_float(
                optical, "thermo_optic_per_k", "optical"
            ),
            laser_drift_nm_per_k=_float(
                optical, "laser_drift_nm_per_k", "optical"
            ),
            base_loss_db_per_cm=_float(
                optical, "base_loss_db_per_cm", "optical"
            ),
            scattering_loss_db_per_cm_nm2=_float(
                optical, "scattering_loss_db_per_cm_nm2", "optical"
            ),
            coupling_loss_db=_float(optical, "coupling_loss_db", "optical"),
            alignment_loss_db_per_um2=_float(
                optical, "alignment_loss_db_per_um2", "optical"
            ),
            heater_power_mw_per_2pi=_float(
                optical, "heater_power_mw_per_2pi", "optical"
            ),
            mesh_excess_loss_db=_float(
                optical, "mesh_excess_loss_db", "optical"
            ),
        )


@dataclass(frozen=True)
class PhotonicVariation:
    """Process and environment distributions for the PTA model."""

    width_nm: GaussianParameter
    etch_depth_nm: GaussianParameter
    ler_nm: GaussianParameter
    alignment_um: GaussianParameter
    ambient_c: GaussianParameter

    def __post_init__(self) -> None:
        if self.width_nm.mean <= 0.0:
            raise ValueError("width mean must be positive")
        if self.etch_depth_nm.mean <= 0.0:
            raise ValueError("etch depth mean must be positive")
        if self.ler_nm.mean < 0.0:
            raise ValueError("line-edge roughness mean must be non-negative")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PhotonicVariation":
        variation = _mapping(raw, "variation", "photonic model")
        return cls(
            width_nm=GaussianParameter.from_mapping(
                variation.get("width_nm"), "variation.width_nm"
            ),
            etch_depth_nm=GaussianParameter.from_mapping(
                variation.get("etch_depth_nm"), "variation.etch_depth_nm"
            ),
            ler_nm=GaussianParameter.from_mapping(
                variation.get("ler_nm"), "variation.ler_nm"
            ),
            alignment_um=GaussianParameter.from_mapping(
                variation.get("alignment_um"), "variation.alignment_um"
            ),
            ambient_c=GaussianParameter.from_mapping(
                variation.get("ambient_c"), "variation.ambient_c"
            ),
        )


@dataclass(frozen=True)
class ThermalSpec:
    """A one-dimensional interposer heat path.

    Heat crosses a vertical path through the interposer and a lateral path from
    the electronic die to the PTA. Optional air trenches are placed in series in
    the lateral path. The model is a planning approximation, not FEA.
    """

    reference_c: float
    electronic_heat_w: float
    distance_mm: float
    contact_width_mm: float
    interposer_thickness_um: float
    silicon_conductivity_w_mk: float
    trench_count: int
    trench_width_um: float
    air_conductivity_w_mk: float
    measured_resistance_k_per_w: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.reference_c):
            raise ValueError("thermal reference must be finite")
        if self.electronic_heat_w < 0.0:
            raise ValueError("electronic heat must be non-negative")
        if self.distance_mm <= 0.0:
            raise ValueError("thermal distance must be positive")
        if self.contact_width_mm <= 0.0:
            raise ValueError("thermal contact width must be positive")
        if self.interposer_thickness_um <= 0.0:
            raise ValueError("interposer thickness must be positive")
        if self.silicon_conductivity_w_mk <= 0.0:
            raise ValueError("silicon conductivity must be positive")
        if self.air_conductivity_w_mk <= 0.0:
            raise ValueError("air conductivity must be positive")
        if self.trench_count < 0:
            raise ValueError("trench count must be non-negative")
        if self.trench_width_um < 0.0:
            raise ValueError("trench width must be non-negative")
        if self.trench_count and self.trench_width_um <= 0.0:
            raise ValueError("positive trench count needs a positive width")
        if self.trench_count * self.trench_width_um > self.distance_mm * 1000.0:
            raise ValueError("trenches exceed the thermal path")
        if self.measured_resistance_k_per_w is not None:
            if (
                not math.isfinite(self.measured_resistance_k_per_w)
                or self.measured_resistance_k_per_w <= 0.0
            ):
                raise ValueError(
                    "measured thermal resistance must be finite and positive"
                )

    def geometry_resistance_k_per_w(self) -> float:
        """Return the one-dimensional geometry-only resistance."""
        width_m = self.contact_width_mm * 1e-3
        thickness_m = self.interposer_thickness_um * 1e-6
        area_m2 = width_m * width_m
        cross_section_m2 = width_m * thickness_m
        r_vertical = thickness_m / (
            self.silicon_conductivity_w_mk * area_m2
        )
        gap_m = self.distance_mm * 1e-3
        trench_m = self.trench_count * self.trench_width_um * 1e-6
        silicon_m = gap_m - trench_m
        r_lateral = silicon_m / (
            self.silicon_conductivity_w_mk * cross_section_m2
        )
        if trench_m:
            r_lateral += trench_m / (
                self.air_conductivity_w_mk * cross_section_m2
            )
        return r_vertical + r_lateral

    def resistance_k_per_w(self) -> float:
        if self.measured_resistance_k_per_w is not None:
            return self.measured_resistance_k_per_w
        return self.geometry_resistance_k_per_w()

    def local_temperature_rise_k(self) -> float:
        return self.electronic_heat_w * self.resistance_k_per_w()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ThermalSpec":
        thermal = _mapping(raw, "thermal", "photonic model")
        return cls(
            reference_c=_float(thermal, "reference_c", "thermal"),
            electronic_heat_w=_float(
                thermal, "electronic_heat_w", "thermal"
            ),
            distance_mm=_float(thermal, "distance_mm", "thermal"),
            contact_width_mm=_float(
                thermal, "contact_width_mm", "thermal"
            ),
            interposer_thickness_um=_float(
                thermal, "interposer_thickness_um", "thermal"
            ),
            silicon_conductivity_w_mk=_float(
                thermal, "silicon_conductivity_w_mk", "thermal"
            ),
            trench_count=_int(thermal, "trench_count", "thermal"),
            trench_width_um=_float(
                thermal, "trench_width_um", "thermal"
            ),
            air_conductivity_w_mk=_float(
                thermal, "air_conductivity_w_mk", "thermal"
            ),
        )


@dataclass(frozen=True)
class PhotonicAssumptions:
    """Versioned assumptions for the PTA photonic and thermal model."""

    id: str
    product: str
    process: str
    revision: str
    optical: OpticalSpec
    variation: PhotonicVariation
    thermal: ThermalSpec
    description: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("photonic model id must not be empty")
        if not self.product:
            raise ValueError("photonic model product must not be empty")
        if not self.process:
            raise ValueError("photonic model process must not be empty")
        if not self.revision:
            raise ValueError("photonic model revision must not be empty")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PhotonicAssumptions":
        return cls(
            id=str(raw["id"]),
            product=str(raw["product"]),
            process=str(raw["process"]),
            revision=str(raw.get("revision", "0.1.0")),
            description=str(raw.get("description", "")).strip(),
            optical=OpticalSpec.from_mapping(raw),
            variation=PhotonicVariation.from_mapping(raw),
            thermal=ThermalSpec.from_mapping(raw),
        )


@dataclass(frozen=True)
class PhotonicDesign:
    """The optical mesh dimensions used by the model."""

    mesh_rows: int
    mesh_columns: int
    optical_window_um: float

    def __post_init__(self) -> None:
        if self.mesh_rows < 1 or self.mesh_columns < 1:
            raise ValueError("mesh dimensions must be positive")
        if self.optical_window_um <= 0.0:
            raise ValueError("optical window must be positive")

    @property
    def mzi_count(self) -> int:
        return self.mesh_rows * self.mesh_columns

    @property
    def stages(self) -> int:
        return self.mesh_rows + self.mesh_columns - 1

    @property
    def path_length_cm(self) -> float:
        return self.optical_window_um * self.stages * 1e-4

    @classmethod
    def from_mapping(cls, mesh: Mapping[str, Any]) -> "PhotonicDesign":
        return cls(
            mesh_rows=int(mesh["rows"]),
            mesh_columns=int(mesh["columns"]),
            optical_window_um=float(mesh["optical_window_um"]),
        )


@dataclass(frozen=True)
class PhotonicMetrics:
    """One deterministic operating point."""

    insertion_loss_db: float
    phase_error_rad: float
    tuning_power_w: float
    tensor_error: float
    temperature_rise_k: float


@dataclass(frozen=True)
class SensitivityResult:
    """One-at-a-time one-sigma shift from the nominal operating point."""

    parameter: str
    phase_error_swing_rad: float
    insertion_loss_swing_db: float


@dataclass(frozen=True)
class PhotonicEstimate:
    """Seeded Monte Carlo result plus the deterministic sensitivity ranking."""

    insertion_loss_db_mean: float
    insertion_loss_db_stderr: float | None
    phase_error_rad_mean: float
    phase_error_rad_stderr: float | None
    tuning_power_w_mean: float
    tuning_power_w_stderr: float | None
    tensor_error_mean: float
    tensor_error_stderr: float | None
    temperature_rise_k_mean: float
    temperature_rise_k_stderr: float | None
    thermal_resistance_k_per_w: float
    local_temperature_rise_k: float
    sensitivity: tuple[SensitivityResult, ...]
    samples: int

    @property
    def dominant_phase_parameter(self) -> str:
        ranked = max(
            self.sensitivity,
            key=lambda item: item.phase_error_swing_rad,
            default=None,
        )
        if ranked is None or ranked.phase_error_swing_rad <= 0.0:
            return "none"
        return ranked.parameter

    @property
    def dominant_loss_parameter(self) -> str:
        ranked = max(
            self.sensitivity,
            key=lambda item: item.insertion_loss_swing_db,
            default=None,
        )
        if ranked is None or ranked.insertion_loss_swing_db <= 0.0:
            return "none"
        return ranked.parameter


def _metrics(
    assumptions: PhotonicAssumptions,
    design: PhotonicDesign,
    *,
    width_nm: float,
    etch_depth_nm: float,
    ler_nm: float,
    alignment_um: float,
    ambient_c: float,
) -> PhotonicMetrics:
    optical = assumptions.optical
    variation = assumptions.variation
    thermal = assumptions.thermal
    width_nm = max(0.0, width_nm)
    etch_depth_nm = max(0.0, etch_depth_nm)
    ler_nm = max(0.0, ler_nm)

    local_rise = thermal.local_temperature_rise_k()
    temperature_rise = (ambient_c - thermal.reference_c) + local_rise
    wavelength_nm = optical.wavelength_nm + (
        optical.laser_drift_nm_per_k * (ambient_c - thermal.reference_c)
    )
    if wavelength_nm <= 0.0:
        raise ValueError("temperature drift produced a non-positive wavelength")

    effective_index = (
        optical.effective_index
        + optical.width_sensitivity_per_nm
        * (width_nm - optical.nominal_width_nm)
        + optical.etch_sensitivity_per_nm
        * (etch_depth_nm - optical.nominal_etch_depth_nm)
        + optical.thermo_optic_per_k * temperature_rise
    )
    length_m = design.optical_window_um * 1e-6
    wavelength_m = wavelength_nm * 1e-9
    phase_ideal = (
        _TWO_PI
        * optical.effective_index
        * length_m
        / (optical.wavelength_nm * 1e-9)
    )
    phase_active = _TWO_PI * effective_index * length_m / wavelength_m
    phase_error = abs(phase_active - phase_ideal)
    tensor_error = phase_error / math.pi

    propagation_loss = (
        optical.base_loss_db_per_cm
        + optical.scattering_loss_db_per_cm_nm2 * ler_nm * ler_nm
    ) * design.path_length_cm
    alignment_loss = (
        optical.alignment_loss_db_per_um2 * alignment_um * alignment_um
    )
    insertion_loss = (
        2.0 * optical.coupling_loss_db
        + propagation_loss
        + optical.mesh_excess_loss_db * design.stages
        + alignment_loss
    )
    tuning_power = (
        phase_error
        * optical.heater_power_mw_per_2pi
        / _TWO_PI
        * design.mzi_count
        / 1000.0
    )
    return PhotonicMetrics(
        insertion_loss_db=insertion_loss,
        phase_error_rad=phase_error,
        tuning_power_w=tuning_power,
        tensor_error=tensor_error,
        temperature_rise_k=temperature_rise,
    )


def _mean_stderr(values: list[float]) -> tuple[float, float | None]:
    mean = statistics.fmean(values)
    if len(values) < 2:
        return mean, None
    return mean, statistics.stdev(values) / math.sqrt(len(values))


def _nominal_parameters(
    assumptions: PhotonicAssumptions,
) -> dict[str, float]:
    variation = assumptions.variation
    return {
        "width_nm": variation.width_nm.mean,
        "etch_depth_nm": variation.etch_depth_nm.mean,
        "ler_nm": variation.ler_nm.mean,
        "alignment_um": variation.alignment_um.mean,
        "ambient_c": variation.ambient_c.mean,
    }


def _sensitivity(
    assumptions: PhotonicAssumptions, design: PhotonicDesign
) -> tuple[SensitivityResult, ...]:
    nominal = _metrics(
        assumptions, design, **_nominal_parameters(assumptions)
    )
    specifications = (
        ("width_nm", assumptions.variation.width_nm),
        ("etch_depth_nm", assumptions.variation.etch_depth_nm),
        ("ler_nm", assumptions.variation.ler_nm),
        ("alignment_um", assumptions.variation.alignment_um),
        ("ambient_c", assumptions.variation.ambient_c),
    )
    results: list[SensitivityResult] = []
    for parameter, distribution in specifications:
        if distribution.sigma == 0.0:
            results.append(SensitivityResult(parameter, 0.0, 0.0))
            continue
        parameters = _nominal_parameters(assumptions)
        parameters[parameter] = distribution.mean + distribution.sigma
        shifted = _metrics(assumptions, design, **parameters)
        results.append(
            SensitivityResult(
                parameter=parameter,
                phase_error_swing_rad=abs(
                    shifted.phase_error_rad - nominal.phase_error_rad
                ),
                insertion_loss_swing_db=abs(
                    shifted.insertion_loss_db - nominal.insertion_loss_db
                ),
            )
        )
    return tuple(results)


def simulate_photonic(
    assumptions: PhotonicAssumptions,
    design: PhotonicDesign,
    *,
    samples: int = 200,
    seed: int = 0,
) -> PhotonicEstimate:
    """Run a seeded process/temperature Monte Carlo for the PTA mesh."""
    if samples < 1:
        raise ValueError("samples must be at least one")
    rng = random.Random(seed)
    points: list[PhotonicMetrics] = []
    for _ in range(samples):
        points.append(
            _metrics(
                assumptions,
                design,
                width_nm=assumptions.variation.width_nm.sample(
                    rng, nonnegative=True
                ),
                etch_depth_nm=assumptions.variation.etch_depth_nm.sample(
                    rng, nonnegative=True
                ),
                ler_nm=assumptions.variation.ler_nm.sample(
                    rng, nonnegative=True
                ),
                alignment_um=assumptions.variation.alignment_um.sample(rng),
                ambient_c=assumptions.variation.ambient_c.sample(rng),
            )
        )

    insertion_mean, insertion_stderr = _mean_stderr(
        [point.insertion_loss_db for point in points]
    )
    phase_mean, phase_stderr = _mean_stderr(
        [point.phase_error_rad for point in points]
    )
    tuning_mean, tuning_stderr = _mean_stderr(
        [point.tuning_power_w for point in points]
    )
    tensor_mean, tensor_stderr = _mean_stderr(
        [point.tensor_error for point in points]
    )
    temperature_mean, temperature_stderr = _mean_stderr(
        [point.temperature_rise_k for point in points]
    )
    return PhotonicEstimate(
        insertion_loss_db_mean=insertion_mean,
        insertion_loss_db_stderr=insertion_stderr,
        phase_error_rad_mean=phase_mean,
        phase_error_rad_stderr=phase_stderr,
        tuning_power_w_mean=tuning_mean,
        tuning_power_w_stderr=tuning_stderr,
        tensor_error_mean=tensor_mean,
        tensor_error_stderr=tensor_stderr,
        temperature_rise_k_mean=temperature_mean,
        temperature_rise_k_stderr=temperature_stderr,
        thermal_resistance_k_per_w=(
            assumptions.thermal.resistance_k_per_w()
        ),
        local_temperature_rise_k=(
            assumptions.thermal.local_temperature_rise_k()
        ),
        sensitivity=_sensitivity(assumptions, design),
        samples=samples,
    )

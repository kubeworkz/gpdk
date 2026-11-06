"""Measured-coefficient calibration for the PTA photonic/thermal model.

This contract carries parameter estimates already extracted from measured test
structures. It deliberately does not fit raw laboratory traces: the platform
consumes the extracted value, its standard uncertainty, and the test structure
that produced it. A calibration file is optional; omitted coefficients keep
their planning-assumption values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Mapping

from .photonics import PhotonicAssumptions

SCHEMA_VERSION = "0.1"
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "id",
        "revision",
        "product",
        "process",
        "description",
        "evidence",
        "source",
        "parameters",
    }
)
_GROUPS = ("width", "etch", "loss", "thermal")
_GROUP_MEMBERS = {
    "width": ("width_sensitivity_per_nm",),
    "etch": ("etch_sensitivity_per_nm",),
    "loss": (
        "base_loss_db_per_cm",
        "scattering_loss_db_per_cm_nm2",
        "coupling_loss_db",
        "alignment_loss_db_per_um2",
        "mesh_excess_loss_db",
    ),
    "thermal": ("thermo_optic_per_k", "thermal_resistance_k_per_w"),
}
_PARAMETER_SPECS: dict[str, tuple[str, str, bool]] = {
    "width_sensitivity_per_nm": ("1/nm", "width", True),
    "etch_sensitivity_per_nm": ("1/nm", "etch", True),
    "base_loss_db_per_cm": ("dB/cm", "loss", False),
    "scattering_loss_db_per_cm_nm2": ("dB/cm/nm2", "loss", False),
    "coupling_loss_db": ("dB", "loss", False),
    "alignment_loss_db_per_um2": ("dB/um2", "loss", False),
    "mesh_excess_loss_db": ("dB", "loss", False),
    "thermo_optic_per_k": ("1/K", "thermal", True),
    "thermal_resistance_k_per_w": ("K/W", "thermal", True),
}


def _text(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} needs a non-empty {key!r}")
    return value.strip()


def _number(raw: Mapping[str, Any], key: str, label: str) -> float:
    try:
        value = float(raw[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} needs numeric {key!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label}.{key} must be finite")
    return value


@dataclass(frozen=True)
class CalibrationParameter:
    """One measured coefficient with its uncertainty and test structure."""

    name: str
    value: float
    uncertainty: float
    unit: str
    test_structure: str
    method: str

    def __post_init__(self) -> None:
        if self.name not in _PARAMETER_SPECS:
            raise ValueError(f"unknown calibration parameter {self.name!r}")
        if not math.isfinite(self.value):
            raise ValueError(f"{self.name} value must be finite")
        if not math.isfinite(self.uncertainty) or self.uncertainty <= 0.0:
            raise ValueError(f"{self.name} uncertainty must be positive")
        unit, _group, strictly_positive = _PARAMETER_SPECS[self.name]
        if self.unit != unit:
            raise ValueError(
                f"{self.name} unit must be {unit!r}, got {self.unit!r}"
            )
        if strictly_positive and self.value <= 0.0:
            raise ValueError(f"{self.name} must be positive")
        if not strictly_positive and self.value < 0.0:
            raise ValueError(f"{self.name} must be non-negative")
        if not self.test_structure.strip():
            raise ValueError(f"{self.name} needs a test_structure")
        if not self.method.strip():
            raise ValueError(f"{self.name} needs a method")

    @classmethod
    def from_mapping(
        cls,
        name: str,
        raw: Any,
        *,
        default_method: str,
    ) -> "CalibrationParameter":
        if not isinstance(raw, Mapping):
            raise ValueError(f"calibration parameter {name!r} must be a mapping")
        spec = _PARAMETER_SPECS.get(name)
        if spec is None:
            raise ValueError(f"unknown calibration parameter {name!r}")
        unit = _text(raw, "unit", name)
        if unit != spec[0]:
            raise ValueError(
                f"{name} unit must be {spec[0]!r}, got {unit!r}"
            )
        method = raw.get("method", default_method)
        if not isinstance(method, str) or not method.strip():
            raise ValueError(f"{name} method must be a non-empty string")
        return cls(
            name=name,
            value=_number(raw, "value", name),
            uncertainty=_number(raw, "uncertainty", name),
            unit=unit,
            test_structure=_text(raw, "test_structure", name),
            method=method.strip(),
        )


@dataclass(frozen=True)
class CalibrationResult:
    """Assumptions after calibration plus the remaining-assumption audit."""

    assumptions: PhotonicAssumptions
    calibrated: tuple[str, ...]
    remaining: tuple[str, ...]
    complete_groups: tuple[str, ...]
    incomplete_groups: tuple[str, ...]


@dataclass(frozen=True)
class PhotonicCalibration:
    """Versioned measured-coefficient calibration for the PTA model."""

    id: str
    revision: str
    product: str
    process: str
    description: str
    source: str
    parameters: tuple[CalibrationParameter, ...]

    def __post_init__(self) -> None:
        if not self.parameters:
            raise ValueError("calibration needs at least one parameter")
        names = [item.name for item in self.parameters]
        if len(set(names)) != len(names):
            raise ValueError("calibration parameters must be unique")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PhotonicCalibration":
        if not isinstance(raw, Mapping):
            raise ValueError("photonic calibration must be a mapping")
        unknown = sorted(set(raw) - _TOP_LEVEL_FIELDS)
        if unknown:
            raise ValueError(
                "unknown photonic calibration field(s): " + ", ".join(unknown)
            )
        schema_version = _text(raw, "schema_version", "photonic calibration")
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                "photonic calibration schema_version must be "
                f"{SCHEMA_VERSION!r}, got {schema_version!r}"
            )
        evidence = _text(raw, "evidence", "photonic calibration")
        if evidence != "measured":
            raise ValueError(
                "photonic calibration evidence must be 'measured', "
                f"got {evidence!r}"
            )
        parameter_map = raw.get("parameters")
        if not isinstance(parameter_map, Mapping) or not parameter_map:
            raise ValueError(
                "photonic calibration needs a non-empty parameters mapping"
            )
        unknown_parameters = sorted(set(parameter_map) - set(_PARAMETER_SPECS))
        if unknown_parameters:
            raise ValueError(
                "unknown calibration parameter(s): "
                + ", ".join(str(name) for name in unknown_parameters)
            )
        description = raw.get("description", "")
        if not isinstance(description, str):
            raise ValueError("photonic calibration description must be a string")
        parameters = tuple(
            CalibrationParameter.from_mapping(
                name,
                parameter_map[name],
                default_method="measured parameter extraction",
            )
            for name in _PARAMETER_SPECS
            if name in parameter_map
        )
        return cls(
            id=_text(raw, "id", "photonic calibration"),
            revision=_text(raw, "revision", "photonic calibration"),
            product=_text(raw, "product", "photonic calibration"),
            process=_text(raw, "process", "photonic calibration"),
            description=description.strip(),
            source=_text(raw, "source", "photonic calibration"),
            parameters=parameters,
        )

    def apply(self, assumptions: PhotonicAssumptions) -> CalibrationResult:
        """Replace only supplied coefficients and report the remaining ones."""
        if assumptions.product != self.product:
            raise ValueError(
                f"calibration product {self.product!r} does not match "
                f"photonic model product {assumptions.product!r}"
            )
        if assumptions.process.lower() != self.process.lower():
            raise ValueError(
                f"calibration process {self.process!r} does not match "
                f"photonic model process {assumptions.process!r}"
            )
        values = {item.name: item.value for item in self.parameters}
        optical_updates = {
            name: value
            for name, value in values.items()
            if name
            in {
                "width_sensitivity_per_nm",
                "etch_sensitivity_per_nm",
                "base_loss_db_per_cm",
                "scattering_loss_db_per_cm_nm2",
                "coupling_loss_db",
                "alignment_loss_db_per_um2",
                "mesh_excess_loss_db",
                "thermo_optic_per_k",
            }
        }
        optical = replace(assumptions.optical, **optical_updates)
        thermal = assumptions.thermal
        if "thermal_resistance_k_per_w" in values:
            thermal = replace(
                thermal,
                measured_resistance_k_per_w=values[
                    "thermal_resistance_k_per_w"
                ],
            )
        calibrated = tuple(item.name for item in self.parameters)
        remaining = tuple(
            name for name in _PARAMETER_SPECS if name not in values
        )
        complete = tuple(
            group
            for group in _GROUPS
            if all(name in values for name in _GROUP_MEMBERS[group])
        )
        incomplete = tuple(group for group in _GROUPS if group not in complete)
        return CalibrationResult(
            assumptions=replace(
                assumptions,
                optical=optical,
                thermal=thermal,
            ),
            calibrated=calibrated,
            remaining=remaining,
            complete_groups=complete,
            incomplete_groups=incomplete,
        )

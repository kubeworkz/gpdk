"""F1 PTA photonic/thermal adapter over ``gpdk.photonics``.

The Phase 0 ``pta`` adapter records topology only. This adapter consumes a
separate photonic-assumptions file and returns seeded optical, thermal and
sensitivity observations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml

from gpdk.photonic_calibration import (
    CalibrationResult,
    PhotonicCalibration,
)
from gpdk.photonics import (
    PhotonicAssumptions,
    PhotonicDesign,
    PhotonicEstimate,
    simulate_photonic,
)
from gpdk.tech import load_tech

from ..errors import EngineError
from ..model import EngineResult, InputFile, Observation
from ..provenance import display_path
from ..scenario import Scenario
from .pta import _mesh, _package_products, _package_ref, _read_mapping, _slug

_MODEL_VERSION_PREFIX = "pta-photonic"
_METRICS: dict[
    str,
    tuple[
        str,
        Callable[[PhotonicEstimate], float],
        Callable[[PhotonicEstimate], float | None] | None,
    ],
] = {
    "insertion_loss_db": (
        "dB",
        lambda estimate: estimate.insertion_loss_db_mean,
        lambda estimate: estimate.insertion_loss_db_stderr,
    ),
    "phase_error_rad": (
        "rad",
        lambda estimate: estimate.phase_error_rad_mean,
        lambda estimate: estimate.phase_error_rad_stderr,
    ),
    "tuning_power_w": (
        "W",
        lambda estimate: estimate.tuning_power_w_mean,
        lambda estimate: estimate.tuning_power_w_stderr,
    ),
    "tensor_error": (
        "1",
        lambda estimate: estimate.tensor_error_mean,
        lambda estimate: estimate.tensor_error_stderr,
    ),
    "temperature_rise_k": (
        "K",
        lambda estimate: estimate.temperature_rise_k_mean,
        lambda estimate: estimate.temperature_rise_k_stderr,
    ),
}
SUPPORTED_METRICS = frozenset(_METRICS)


def _load_inputs(scenario: Scenario):
    product = _read_mapping(scenario.chip_path, "PTA definition")
    tech = load_tech(str(product.get("tech", "grx28.yaml")))
    if scenario.package_path is None:
        raise ValueError("PTA photonic scenario requires inputs.package")
    if scenario.photonic_path is None:
        raise ValueError("PTA photonic scenario requires inputs.photonic")
    package = _read_mapping(scenario.package_path, "package definition")
    assumptions = PhotonicAssumptions.from_mapping(
        _read_mapping(scenario.photonic_path, "photonic model")
    )
    calibration = None
    if scenario.photonic_calibration_path is not None:
        calibration = PhotonicCalibration.from_mapping(
            _read_mapping(
                scenario.photonic_calibration_path,
                "photonic calibration",
            )
        )
    mesh = _mesh(product)
    design = PhotonicDesign.from_mapping(mesh)
    return product, tech, package, assumptions, calibration, design


class PtaPhotonicEngine:
    """F1 optical, thermal and one-at-a-time sensitivity engine for the PTA."""

    name = "pta_photonic"
    version = "0.1.0"
    fidelity = "F1"

    def validate(self, scenario: Scenario) -> list[str]:
        errors: list[str] = []
        if scenario.samples < 1:
            errors.append("PTA photonic model needs at least one sample")
        unknown = sorted(set(scenario.outputs) - SUPPORTED_METRICS)
        if unknown:
            errors.append(
                "unsupported PTA photonic metric(s): " + ", ".join(unknown)
            )
        try:
            (
                product,
                tech,
                package,
                assumptions,
                calibration,
                design,
            ) = _load_inputs(scenario)
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"cannot load PTA photonic inputs: {exc}")
            return errors

        expected_product = _slug(str(product.get("name", "")))
        if scenario.product != expected_product:
            errors.append(
                f"product {scenario.product!r} does not match PTA definition "
                f"{product.get('name')!r} (expected {expected_product!r})"
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
                f"photonic model product {assumptions.product!r} does not "
                f"match scenario product {scenario.product!r}"
            )
        if assumptions.process.lower() != scenario.process.lower():
            errors.append(
                f"photonic model process {assumptions.process!r} does not "
                f"match scenario process {scenario.process!r}"
            )
        if calibration is not None:
            try:
                calibration.apply(assumptions)
            except ValueError as exc:
                errors.append(str(exc))
        expected_package = _package_ref(package)
        if str(product.get("package")) != expected_package:
            errors.append(
                f"PTA package {product.get('package')!r} does not match "
                f"{expected_package!r}"
            )
        try:
            products = _package_products(package)
        except ValueError as exc:
            errors.append(str(exc))
            return errors
        if not {"g100", "pta"} <= products:
            errors.append("MCM package must reference both g100 and pta chiplets")
        if design.mesh_rows < 1 or design.mesh_columns < 1:
            errors.append("PTA mesh rows and columns must be positive")
        if design.optical_window_um <= 0.0:
            errors.append("PTA optical window must be positive")
        return errors

    def run(self, scenario: Scenario) -> EngineResult:
        errors = self.validate(scenario)
        if errors:
            raise EngineError("; ".join(errors))

        (
            product,
            tech,
            package,
            assumptions,
            calibration,
            design,
        ) = _load_inputs(scenario)
        calibration_result: CalibrationResult | None = None
        if calibration is not None:
            calibration_result = calibration.apply(assumptions)
            assumptions = calibration_result.assumptions
        simulation = simulate_photonic(
            assumptions,
            design,
            samples=scenario.samples,
            seed=scenario.seed,
        )
        source = display_path(scenario.photonic_path)
        model_version = f"{_MODEL_VERSION_PREFIX}@{assumptions.revision}"
        if calibration is not None:
            model_version += f"+cal@{calibration.revision}"
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

        if calibration is not None:
            calibration_source = display_path(
                scenario.photonic_calibration_path
            )
            calibration_version = f"pta-calibration@{calibration.revision}"
            for parameter in calibration.parameters:
                observations.append(
                    Observation(
                        entity_type="calibration",
                        entity_id=calibration.id,
                        metric=parameter.name,
                        value=parameter.value,
                        unit=parameter.unit,
                        uncertainty=parameter.uncertainty,
                        evidence_class="measured",
                        source_artifact=calibration_source,
                        model_version=calibration_version,
                    )
                )

        for item in simulation.sensitivity:
            for metric, value, unit in (
                (
                    "phase_error_swing",
                    item.phase_error_swing_rad,
                    "rad",
                ),
                (
                    "insertion_loss_swing",
                    item.insertion_loss_swing_db,
                    "dB",
                ),
            ):
                observations.append(
                    Observation(
                        entity_type="sensitivity",
                        entity_id=item.parameter,
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
            InputFile(scenario.package_path, "package"),
            InputFile(scenario.photonic_path, "photonic"),
        ]
        if scenario.photonic_calibration_path is not None:
            input_files.append(
                InputFile(
                    scenario.photonic_calibration_path,
                    "photonic_calibration",
                )
            )
        if tech.path is not None:
            input_files.append(InputFile(tech.path, "tech"))

        phase_ranked = sorted(
            simulation.sensitivity,
            key=lambda item: item.phase_error_swing_rad,
            reverse=True,
        )
        loss_ranked = sorted(
            simulation.sensitivity,
            key=lambda item: item.insertion_loss_swing_db,
            reverse=True,
        )
        calibration_metadata = None
        if calibration_result is not None and calibration is not None:
            calibration_metadata = {
                "id": calibration.id,
                "revision": calibration.revision,
                "source": calibration.source,
                "calibrated_parameters": list(
                    calibration_result.calibrated
                ),
                "remaining_assumed_parameters": list(
                    calibration_result.remaining
                ),
                "complete_groups": list(
                    calibration_result.complete_groups
                ),
                "incomplete_groups": list(
                    calibration_result.incomplete_groups
                ),
            }
        if calibration_result is None:
            warnings = (
                "PTA photonic/thermal results are F1 planning estimates, not "
                "measured or calibrated PTA performance.",
                "Phase error is a per-MZI analytical estimate without "
                "common-mode cancellation or tuning feedback; tensor error is "
                "phase error divided by pi, a stated proxy, not a measured "
                "inference error.",
                "The thermal path is a one-dimensional silicon-interposer "
                "approximation that omits TIM, bump and die-level interface "
                "resistances; it is not full-chip thermal FEA and its absolute "
                "temperature rise is optimistic.",
            )
        else:
            warnings = (
                "Measured calibration coefficients replace model assumptions, "
                "but aggregate outputs remain model estimates and are tagged "
                "assumed; they are not measured PTA performance.",
                "Calibration uncertainty is recorded per measured parameter but "
                "is not propagated to aggregate uncertainty.",
                "Calibration covers groups "
                + ", ".join(calibration_result.complete_groups)
                + "; assumptions remain for "
                + ", ".join(calibration_result.remaining)
                + ".",
                "Phase error is a per-MZI analytical estimate without "
                "common-mode cancellation or tuning feedback; tensor error is "
                "phase error divided by pi, a stated proxy, not a measured "
                "inference error.",
                "The thermal path is a one-dimensional silicon-interposer "
                "approximation that omits TIM, bump and die-level interface "
                "resistances; it is not full-chip thermal FEA and its absolute "
                "temperature rise is optimistic.",
            )
        return EngineResult(
            engine=self.name,
            engine_version=self.version,
            fidelity=self.fidelity,
            model_version=model_version,
            observations=tuple(observations),
            inputs=tuple(input_files),
            metadata={
                "chip": product.get("name"),
                "tech": {
                    "name": tech.name,
                    "revision": tech.revision,
                },
                "package": {
                    "id": package.get("id"),
                    "revision": package.get("revision"),
                    "kind": package.get("kind"),
                },
                "mesh": {
                    "rows": design.mesh_rows,
                    "columns": design.mesh_columns,
                    "mzi_count": design.mzi_count,
                    "stages": design.stages,
                    "optical_window_um": design.optical_window_um,
                    "wavelength_nm": assumptions.optical.wavelength_nm,
                },
                "optical": {
                    "effective_index": assumptions.optical.effective_index,
                    "nominal_width_nm": (
                        assumptions.optical.nominal_width_nm
                    ),
                    "nominal_etch_depth_nm": (
                        assumptions.optical.nominal_etch_depth_nm
                    ),
                    "width_sensitivity_per_nm": (
                        assumptions.optical.width_sensitivity_per_nm
                    ),
                    "etch_sensitivity_per_nm": (
                        assumptions.optical.etch_sensitivity_per_nm
                    ),
                    "thermo_optic_per_k": (
                        assumptions.optical.thermo_optic_per_k
                    ),
                    "base_loss_db_per_cm": (
                        assumptions.optical.base_loss_db_per_cm
                    ),
                    "coupling_loss_db": (
                        assumptions.optical.coupling_loss_db
                    ),
                },
                "variation": {
                    "width_nm": {
                        "mean": assumptions.variation.width_nm.mean,
                        "sigma": assumptions.variation.width_nm.sigma,
                    },
                    "etch_depth_nm": {
                        "mean": assumptions.variation.etch_depth_nm.mean,
                        "sigma": assumptions.variation.etch_depth_nm.sigma,
                    },
                    "ler_nm": {
                        "mean": assumptions.variation.ler_nm.mean,
                        "sigma": assumptions.variation.ler_nm.sigma,
                    },
                    "alignment_um": {
                        "mean": assumptions.variation.alignment_um.mean,
                        "sigma": assumptions.variation.alignment_um.sigma,
                    },
                    "ambient_c": {
                        "mean": assumptions.variation.ambient_c.mean,
                        "sigma": assumptions.variation.ambient_c.sigma,
                    },
                },
                "thermal": {
                    "electronic_heat_w": (
                        assumptions.thermal.electronic_heat_w
                    ),
                    "distance_mm": assumptions.thermal.distance_mm,
                    "contact_width_mm": (
                        assumptions.thermal.contact_width_mm
                    ),
                    "interposer_thickness_um": (
                        assumptions.thermal.interposer_thickness_um
                    ),
                    "trench_count": assumptions.thermal.trench_count,
                    "trench_width_um": (
                        assumptions.thermal.trench_width_um
                    ),
                    "resistance_k_per_w": (
                        simulation.thermal_resistance_k_per_w
                    ),
                    "resistance_basis": (
                        "measured"
                        if assumptions.thermal.measured_resistance_k_per_w
                        is not None
                        else "geometry"
                    ),
                    "local_temperature_rise_k": (
                        simulation.local_temperature_rise_k
                    ),
                },
                "calibration": calibration_metadata,
                "sensitivity": {
                    "phase_error_rad": [
                        {
                            "parameter": item.parameter,
                            "swing": item.phase_error_swing_rad,
                        }
                        for item in phase_ranked
                    ],
                    "insertion_loss_db": [
                        {
                            "parameter": item.parameter,
                            "swing": item.insertion_loss_swing_db,
                        }
                        for item in loss_ranked
                    ],
                },
                "dominant_phase_parameter": (
                    simulation.dominant_phase_parameter
                ),
                "dominant_loss_parameter": (
                    simulation.dominant_loss_parameter
                ),
                "simulation": {
                    "samples": scenario.samples,
                    "seed": scenario.seed,
                    "scope": (
                        "F1 per-MZI phase, loss and one-dimensional interposer "
                        "thermal path; not a full MZI transfer matrix, SiPh PDK "
                        "or full-chip FEA"
                    ),
                },
            },
            warnings=warnings,
        )

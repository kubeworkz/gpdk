"""F0 engine adapter over the repository's existing ``gpdk`` model.

The adapter deliberately keeps the model's own units and APIs.  It converts
the outputs to base SI for the observation store and makes the evidence class
explicit: measured source data is ``measured``; every projected number from the
uncalibrated analytical model is ``assumed``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import yaml

from gpdk import __version__ as GPDK_VERSION
from gpdk.asbuilt import AsBuilt
from gpdk.block import BlockEstimate, load_chip
from gpdk.dtco import best_step, build_steps
from gpdk.tech import load_tech

from ..errors import EngineError
from ..model import EngineResult, InputFile, Observation
from ..provenance import display_path
from ..scenario import Scenario

_MODEL_VERSION = f"gpdk@{GPDK_VERSION}"
_PROJECTED_METRICS: dict[
    str, tuple[str, Callable[[BlockEstimate], float]]
] = {
    "cell_area_m2": ("m2", lambda est: est.cell_area_mm2 * 1e-6),
    "content_area_m2": ("m2", lambda est: est.total_area_mm2 * 1e-6),
    "die_area_m2": ("m2", lambda est: est.die_area_mm2 * 1e-6),
    "native_frequency_hz": ("Hz", lambda est: est.freq_ghz * 1e9),
    "pad_floor_area_m2": ("m2", lambda est: est.pad_floor_mm2 * 1e-6),
    "power_at_target_w": ("W", lambda est: est.power_at_target_w),
    "power_density_at_target_w_per_m2": (
        "W/m2",
        lambda est: est.power_density_at_target_w_per_mm2 * 1e6,
    ),
    "power_w": ("W", lambda est: est.total_power_w),
    "sram_area_m2": ("m2", lambda est: est.sram_area_mm2 * 1e-6),
    "util": ("1", lambda est: est.util),
}
_MEASURED_METRICS: dict[
    str, tuple[str, Callable[[AsBuilt], float]]
] = {
    "as_built_clock_frequency_hz": ("Hz", lambda ab: ab.clock_mhz * 1e6),
    "as_built_content_area_m2": ("m2", lambda ab: ab.content_mm2 * 1e-6),
    "as_built_die_area_m2": ("m2", lambda ab: ab.die_mm2 * 1e-6),
}
SUPPORTED_METRICS = frozenset((*_PROJECTED_METRICS, *_MEASURED_METRICS))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _load_inputs(scenario: Scenario):
    cfg = load_chip(scenario.chip_path)
    tech = load_tech(cfg.tech_file)
    return cfg, tech


class GpdkEngine:
    """Deterministic F0 adapter over ``gpdk.dtco``."""

    name = "gpdk"
    version = GPDK_VERSION
    fidelity = "F0"

    def validate(self, scenario: Scenario) -> list[str]:
        errors: list[str] = []
        if scenario.samples != 1:
            errors.append(
                "gpdk is a deterministic F0 engine; samples must be 1"
            )
        unknown = sorted(set(scenario.outputs) - SUPPORTED_METRICS)
        if unknown:
            errors.append(
                "unsupported gpdk output metric(s): " + ", ".join(unknown)
            )
        try:
            cfg, tech = _load_inputs(scenario)
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"cannot load gpdk inputs: {exc}")
            return errors

        expected_process = f"{_slug(tech.name)}@{tech.revision}"
        if scenario.process.lower() != expected_process:
            errors.append(
                f"process {scenario.process!r} does not match "
                f"{tech.name} revision {tech.revision} "
                f"(expected {expected_process!r})"
            )
        expected_product = _slug(cfg.name)
        if scenario.product != expected_product:
            errors.append(
                f"product {scenario.product!r} does not match chip "
                f"{cfg.name!r} (expected {expected_product!r})"
            )
        if cfg.as_built is None and any(
            metric in _MEASURED_METRICS for metric in scenario.outputs
        ):
            errors.append(
                "scenario requests as-built observations but the chip has no "
                "'as_built' block"
            )
        return errors

    def run(self, scenario: Scenario) -> EngineResult:
        errors = self.validate(scenario)
        if errors:
            raise EngineError("; ".join(errors))

        cfg, tech = _load_inputs(scenario)
        steps = build_steps(cfg)
        best = best_step(steps)
        ab = AsBuilt.from_mapping(cfg.as_built) if cfg.as_built else None
        source = display_path(scenario.chip_path)
        observations: list[Observation] = []

        if ab is not None:
            for metric in scenario.outputs:
                spec = _MEASURED_METRICS.get(metric)
                if spec is None:
                    continue
                unit, projector = spec
                observations.append(
                    Observation(
                        entity_type="product",
                        entity_id=scenario.product,
                        metric=metric,
                        value=float(projector(ab)),
                        unit=unit,
                        uncertainty=None,
                        evidence_class="measured",
                        source_artifact=source,
                        model_version="as_built",
                    )
                )

        for step in steps:
            for metric in scenario.outputs:
                spec = _PROJECTED_METRICS.get(metric)
                if spec is None:
                    continue
                unit, projector = spec
                observations.append(
                    Observation(
                        entity_type="design_point",
                        entity_id=f"{scenario.product}:{step.key}",
                        metric=metric,
                        value=float(projector(step.iso)),
                        unit=unit,
                        uncertainty=None,
                        evidence_class="assumed",
                        source_artifact=source,
                        model_version=_MODEL_VERSION,
                    )
                )

        design_points: list[dict[str, Any]] = [
            {
                "key": step.key,
                "label": step.label,
                "library": step.library.id,
                "tracks": float(step.library.tracks),
                "isolation": step.library.isolation,
                "binding": step.iso.die_binding,
                "best": step.key == best.key,
            }
            for step in steps
        ]
        metadata: dict[str, Any] = {
            "chip": cfg.name,
            "description": cfg.description,
            "tech": {
                "name": tech.name,
                "revision": tech.revision,
            },
            "best_design_point": best.key,
            "design_points": design_points,
            "parameter_evidence": {
                "as_built": "measured",
                "technology": "literature",
                "planning_assumptions": "assumed",
            },
        }
        warnings = [
            "gpdk is an uncalibrated F0 analytical model; these are scenario "
            "estimates, not silicon predictions.",
            "Uncertainty is not estimated in Phase 0; the uncertainty column "
            "is intentionally blank.",
        ]
        if ab is not None:
            warnings.append(
                "The as-built rows are measured source data, not model outputs."
            )

        input_files = [InputFile(scenario.chip_path, "chip")]
        if tech.path is not None:
            input_files.append(InputFile(tech.path, "tech"))

        return EngineResult(
            engine=self.name,
            engine_version=self.version,
            fidelity=self.fidelity,
            model_version=_MODEL_VERSION,
            observations=tuple(observations),
            inputs=tuple(input_files),
            metadata=metadata,
            warnings=tuple(warnings),
        )

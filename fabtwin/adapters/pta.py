"""F0 PTA product-definition adapter.

This adapter records the PTA's declared topology and package contract. It does
not model optical propagation, insertion loss, phase error, thermal tuning or
tensor error; those belong to the Phase 2 photonic/thermal slice.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from gpdk.tech import load_tech

from ..errors import EngineError
from ..model import EngineResult, InputFile, Observation
from ..provenance import display_path
from ..scenario import Scenario

_MODEL_VERSION_PREFIX = "pta-assumptions"
_SUPPORTED_METRICS = frozenset(
    {
        "mesh_rows",
        "mesh_columns",
        "mzi_count",
        "input_port_count",
        "output_port_count",
        "optical_window_m",
        "lane_pitch_m",
        "wavelength_m",
    }
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _read_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} {path} must be a mapping")
    return raw


def _load_inputs(scenario: Scenario):
    product = _read_mapping(scenario.chip_path, "PTA definition")
    tech = load_tech(str(product.get("tech", "grx28.yaml")))
    if scenario.package_path is None:
        raise ValueError("PTA scenario requires inputs.package")
    package = _read_mapping(scenario.package_path, "package definition")
    return product, tech, package


def _mesh(product: dict[str, Any]) -> dict[str, Any]:
    design = product.get("design")
    if not isinstance(design, dict):
        raise ValueError("PTA definition needs a design mapping")
    mesh = design.get("mesh")
    if not isinstance(mesh, dict):
        raise ValueError("PTA definition needs design.mesh")
    return mesh


def _package_ref(package: dict[str, Any]) -> str:
    return f"{package['id']}@{package['revision']}"


def _package_products(package: dict[str, Any]) -> set[str]:
    chiplets = package.get("chiplets")
    if not isinstance(chiplets, list) or not chiplets:
        raise ValueError("package definition needs a non-empty chiplets list")
    products: set[str] = set()
    for item in chiplets:
        if not isinstance(item, dict) or not item.get("product"):
            raise ValueError("each package chiplet needs a product reference")
        products.add(str(item["product"]).split("@", 1)[0])
    return products


class PtaEngine:
    """Deterministic F0 product-envelope adapter for the PTA chiplet."""

    name = "pta"
    version = "0.1.0"
    fidelity = "F0"

    def validate(self, scenario: Scenario) -> list[str]:
        errors: list[str] = []
        if scenario.samples != 1:
            errors.append("pta is a deterministic F0 engine; samples must be 1")
        unknown = sorted(set(scenario.outputs) - _SUPPORTED_METRICS)
        if unknown:
            errors.append(
                "unsupported pta output metric(s): " + ", ".join(unknown)
            )
        try:
            product, tech, package = _load_inputs(scenario)
            expected_package = _package_ref(package)
            mesh = _mesh(product)
            rows = int(mesh["rows"])
            columns = int(mesh["columns"])
            input_ports = int(mesh["input_ports"])
            output_ports = int(mesh["output_ports"])
            window_um = float(mesh["optical_window_um"])
            lane_pitch_um = float(mesh["lane_pitch_um"])
            wavelength_nm = float(product["design"]["wavelength_nm"])
        except (KeyError, TypeError, ValueError, OSError) as exc:
            errors.append(f"cannot load PTA inputs: {exc}")
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
            errors.append(
                "MCM package must reference both g100 and pta chiplets"
            )
        if rows <= 0 or columns <= 0:
            errors.append("PTA mesh rows and columns must be positive")
        if input_ports <= 0 or output_ports <= 0:
            errors.append("PTA input and output ports must be positive")
        if window_um <= 0 or lane_pitch_um <= 0 or wavelength_nm <= 0:
            errors.append("PTA geometry and wavelength must be positive")
        return errors

    def run(self, scenario: Scenario) -> EngineResult:
        errors = self.validate(scenario)
        if errors:
            raise EngineError("; ".join(errors))

        product, tech, package = _load_inputs(scenario)
        mesh = _mesh(product)
        rows = int(mesh["rows"])
        columns = int(mesh["columns"])
        model_version = (
            f"{_MODEL_VERSION_PREFIX}@{product.get('revision', '0.1.0')}"
        )
        values: dict[str, tuple[float, str]] = {
            "mesh_rows": (float(rows), "1"),
            "mesh_columns": (float(columns), "1"),
            "mzi_count": (float(rows * columns), "1"),
            "input_port_count": (float(mesh["input_ports"]), "1"),
            "output_port_count": (float(mesh["output_ports"]), "1"),
            "optical_window_m": (float(mesh["optical_window_um"]) * 1e-6, "m"),
            "lane_pitch_m": (float(mesh["lane_pitch_um"]) * 1e-6, "m"),
            "wavelength_m": (
                float(product["design"]["wavelength_nm"]) * 1e-9,
                "m",
            ),
        }
        source = display_path(scenario.chip_path)
        observations = tuple(
            Observation(
                entity_type="product",
                entity_id=scenario.product,
                metric=metric,
                value=values[metric][0],
                unit=values[metric][1],
                uncertainty=None,
                evidence_class="assumed",
                source_artifact=source,
                model_version=model_version,
            )
            for metric in scenario.outputs
        )
        input_files = [
            InputFile(scenario.chip_path, "chip"),
            InputFile(scenario.package_path, "package"),
        ]
        if tech.path is not None:
            input_files.append(InputFile(tech.path, "tech"))

        return EngineResult(
            engine=self.name,
            engine_version=self.version,
            fidelity=self.fidelity,
            model_version=model_version,
            observations=observations,
            inputs=tuple(input_files),
            metadata={
                "chip": product.get("name"),
                "revision": product.get("revision"),
                "kind": product.get("kind"),
                "tech": {
                    "name": tech.name,
                    "revision": tech.revision,
                },
                "package": {
                    "id": package.get("id"),
                    "revision": package.get("revision"),
                    "kind": package.get("kind"),
                },
                "mesh": dict(mesh),
                "scope": "topology and package contract only",
            },
            warnings=(
                "PTA baseline records topology assumptions only; optical "
                "insertion loss, phase error, thermal tuning and tensor error "
                "are not modeled in Phase 0.",
                "No qualified silicon-photonics PDK or measured PTA data is "
                "used; these are planning assumptions.",
            ),
        )

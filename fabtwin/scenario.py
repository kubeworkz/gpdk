"""Strict parsing for the first scenario contract.

The schema is intentionally a small, code-owned contract rather than a copy of
the wide tables in the concept document.  Unknown fields are errors: a typo
must not silently change a manufacturing experiment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import ScenarioError, ScenarioValidationError
from .provenance import ROOT, display_path, sha256_file

SCHEMA_VERSION = "0.1"
TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "id",
        "description",
        "product",
        "process",
        "seed",
        "samples",
        "engines",
        "inputs",
        "outputs",
    }
)
INPUT_FIELDS = frozenset({"chip", "package", "yield"})
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_PRODUCT_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_PROCESS_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9_.-]*$"
)
_ENGINE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_OUTPUT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Scenario:
    """A validated manufacturing question and its input contract."""

    path: Path
    sha256: str
    schema_version: str
    id: str
    description: str
    product: str
    process: str
    seed: int
    samples: int
    engines: tuple[str, ...]
    chip_ref: str
    chip_path: Path
    package_ref: str | None
    package_path: Path | None
    yield_ref: str | None
    yield_path: Path | None
    outputs: tuple[str, ...]


def _add(errors: list[str], path: Path, message: str) -> None:
    errors.append(f"{display_path(path)}: {message}")


def _text(
    raw: dict[str, Any],
    key: str,
    errors: list[str],
    path: Path,
    *,
    required: bool = True,
    pattern: re.Pattern[str] | None = None,
) -> str | None:
    if key not in raw:
        if required:
            _add(errors, path, f"missing required field {key!r}")
        return None
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        _add(errors, path, f"{key!r} must be a non-empty string")
        return None
    value = value.strip()
    if pattern is not None and not pattern.fullmatch(value):
        _add(errors, path, f"{key!r} has invalid format: {value!r}")
        return None
    return value


def _integer(
    raw: dict[str, Any],
    key: str,
    errors: list[str],
    path: Path,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    if key not in raw:
        _add(errors, path, f"missing required field {key!r}")
        return None
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        _add(errors, path, f"{key!r} must be an integer")
        return None
    if not minimum <= value <= maximum:
        _add(errors, path, f"{key!r} must be in [{minimum}, {maximum}]")
        return None
    return value


def _strings(
    raw: dict[str, Any],
    key: str,
    errors: list[str],
    path: Path,
    *,
    pattern: re.Pattern[str],
) -> tuple[str, ...]:
    if key not in raw:
        _add(errors, path, f"missing required field {key!r}")
        return ()
    value = raw[key]
    if not isinstance(value, list) or not value:
        _add(errors, path, f"{key!r} must be a non-empty list")
        return ()
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            _add(errors, path, f"{key!r} entries must be non-empty strings")
            return ()
        item = item.strip()
        if not pattern.fullmatch(item):
            _add(errors, path, f"{key!r} has invalid entry {item!r}")
            return ()
        result.append(item)
    if len(set(result)) != len(result):
        _add(errors, path, f"{key!r} entries must be unique")
    return tuple(result)


def load_scenario(path: str | Path) -> Scenario:
    """Read and validate a scenario; every unknown field is rejected."""
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.is_file():
        raise ScenarioError(f"scenario not found: {display_path(path)}")

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ScenarioError(f"cannot read {display_path(path)}: {exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ScenarioValidationError(
            [f"{display_path(path)}: invalid YAML: {exc}"]
        ) from exc
    if not isinstance(raw, dict):
        raise ScenarioValidationError(
            [f"{display_path(path)}: top level must be a mapping"]
        )

    errors: list[str] = []
    unknown = sorted(set(raw) - TOP_LEVEL_FIELDS)
    if unknown:
        _add(errors, path, f"unknown top-level field(s): {', '.join(unknown)}")
    schema_version = _text(raw, "schema_version", errors, path)
    if schema_version is not None and schema_version != SCHEMA_VERSION:
        _add(
            errors,
            path,
            f"'schema_version' must be {SCHEMA_VERSION!r}; got {schema_version!r}",
        )
    scenario_id = _text(raw, "id", errors, path, pattern=_ID_RE)
    product = _text(raw, "product", errors, path, pattern=_PRODUCT_RE)
    process = _text(raw, "process", errors, path, pattern=_PROCESS_RE)
    seed = _integer(raw, "seed", errors, path, minimum=0, maximum=2**63 - 1)
    samples = _integer(
        raw, "samples", errors, path, minimum=1, maximum=1_000_000
    )
    engines = _strings(raw, "engines", errors, path, pattern=_ENGINE_RE)
    outputs = _strings(raw, "outputs", errors, path, pattern=_OUTPUT_RE)

    description = ""
    if "description" in raw:
        value = raw["description"]
        if not isinstance(value, str):
            _add(errors, path, "'description' must be a string")
        else:
            description = value.strip()

    chip_ref: str | None = None
    chip_path: Path | None = None
    package_ref: str | None = None
    package_path: Path | None = None
    yield_ref: str | None = None
    yield_path: Path | None = None
    inputs = raw.get("inputs")
    if not isinstance(inputs, dict):
        _add(errors, path, "'inputs' must be a mapping")
    else:
        unknown_inputs = sorted(set(inputs) - INPUT_FIELDS)
        if unknown_inputs:
            _add(
                errors,
                path,
                f"unknown inputs field(s): {', '.join(unknown_inputs)}",
            )
        chip_value = inputs.get("chip")
        if not isinstance(chip_value, str) or not chip_value.strip():
            _add(errors, path, "'inputs.chip' must be a non-empty path string")
        else:
            chip_ref = chip_value.strip()
            candidate = Path(chip_ref)
            if not candidate.is_absolute():
                candidate = ROOT / candidate
            chip_path = candidate.resolve()
            if not chip_path.is_file():
                _add(
                    errors,
                    path,
                    f"'inputs.chip' does not exist: {display_path(chip_path)}",
                )

        package_value = inputs.get("package")
        if package_value is not None:
            if not isinstance(package_value, str) or not package_value.strip():
                _add(
                    errors,
                    path,
                    "'inputs.package' must be a non-empty path string",
                )
            else:
                package_ref = package_value.strip()
                candidate = Path(package_ref)
                if not candidate.is_absolute():
                    candidate = ROOT / candidate
                package_path = candidate.resolve()
                if not package_path.is_file():
                    _add(
                        errors,
                        path,
                        "'inputs.package' does not exist: "
                        f"{display_path(package_path)}",
                    )

        yield_value = inputs.get("yield")
        if yield_value is not None:
            if not isinstance(yield_value, str) or not yield_value.strip():
                _add(
                    errors,
                    path,
                    "'inputs.yield' must be a non-empty path string",
                )
            else:
                yield_ref = yield_value.strip()
                candidate = Path(yield_ref)
                if not candidate.is_absolute():
                    candidate = ROOT / candidate
                yield_path = candidate.resolve()
                if not yield_path.is_file():
                    _add(
                        errors,
                        path,
                        "'inputs.yield' does not exist: "
                        f"{display_path(yield_path)}",
                    )

    if errors:
        raise ScenarioValidationError(errors)
    assert scenario_id is not None
    assert product is not None
    assert process is not None
    assert seed is not None
    assert samples is not None
    assert chip_ref is not None
    assert chip_path is not None

    return Scenario(
        path=path,
        sha256=sha256_file(path),
        schema_version=SCHEMA_VERSION,
        id=scenario_id,
        description=description,
        product=product,
        process=process,
        seed=seed,
        samples=samples,
        engines=engines,
        chip_ref=chip_ref,
        chip_path=chip_path,
        package_ref=package_ref,
        package_path=package_path,
        yield_ref=yield_ref,
        yield_path=yield_path,
        outputs=outputs,
    )

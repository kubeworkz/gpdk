"""Run orchestration and content-addressed provenance."""

from __future__ import annotations

import csv
import io
import json
import platform
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import __version__ as FABTWIN_VERSION
from .baseline import observation_fingerprint
from .engines import build_engine
from .errors import FabTwinError, ScenarioError
from .model import EngineResult, Observation
from .provenance import (
    ROOT,
    display_path,
    sha256_bytes,
    sha256_file,
    source_tree_sha256,
)
from .report import render_report
from .scenario import Scenario
from .store import ObservationStore, STORE_SCHEMA_VERSION

DEFAULT_OUT = ROOT / "out" / "fabtwin"
DEFAULT_STORE = DEFAULT_OUT / "fabtwin.db"
OBSERVATION_FIELDS = [
    "observation_id",
    "run_id",
    "entity_type",
    "entity_id",
    "metric",
    "value",
    "unit",
    "uncertainty",
    "evidence_class",
    "source_artifact",
    "model_version",
]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    manifest_path: Path
    store_path: Path
    observation_count: int


def validate_scenario(scenario: Scenario) -> list[str]:
    """Run scenario-specific validation for every requested engine."""
    errors: list[str] = []
    for name in scenario.engines:
        try:
            engine = build_engine(name)
        except KeyError as exc:
            errors.append(str(exc))
            continue
        errors.extend(f"{name}: {error}" for error in engine.validate(scenario))
    return errors


def _resolve_out(out_dir: str | Path | None) -> Path:
    if out_dir is None:
        return DEFAULT_OUT
    path = Path(out_dir)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _number(value: float) -> str:
    return format(float(value), ".15g")


def _observation_rows(
    run_id: str, observations: tuple[Observation, ...]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in observations:
        identity = f"{run_id}|{item.entity_type}|{item.entity_id}|{item.metric}|{item.model_version}"
        observation_id = "obs-" + sha256_bytes(identity.encode("utf-8"))[:16]
        rows.append(
            {
                "observation_id": observation_id,
                "run_id": run_id,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "metric": item.metric,
                "value": _number(item.value),
                "unit": item.unit,
                "uncertainty": (
                    "" if item.uncertainty is None else _number(item.uncertainty)
                ),
                "evidence_class": item.evidence_class,
                "source_artifact": item.source_artifact,
                "model_version": item.model_version,
            }
        )
    return rows


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=OBSERVATION_FIELDS,
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _input_record(
    role: str, path: Path, digest: str | None = None
) -> dict[str, Any]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise ScenarioError(f"input file not found: {display_path(resolved)}")
    return {
        "role": role,
        "path": display_path(resolved),
        "sha256": digest or sha256_file(resolved),
        "bytes": resolved.stat().st_size,
    }


def _reproduce(scenario: Scenario, out_root: Path) -> str:
    scenario_ref = display_path(scenario.path)
    if out_root.resolve() == DEFAULT_OUT.resolve():
        return f"python -m fabtwin run {scenario_ref}"
    return (
        f"python -m fabtwin run {scenario_ref} "
        f"--out {display_path(out_root)}"
    )


def _unique_observations(
    results: list[EngineResult],
) -> tuple[Observation, ...]:
    observations: list[Observation] = []
    seen: set[tuple[str, str, str, str]] = set()
    for result in results:
        for item in result.observations:
            key = (
                item.entity_type,
                item.entity_id,
                item.metric,
                item.model_version,
            )
            if key in seen:
                raise FabTwinError(
                    "two engines produced the same observation key: "
                    + "|".join(key)
                )
            seen.add(key)
            observations.append(item)
    if not observations:
        raise FabTwinError("the run produced no observations")
    return tuple(observations)


def execute(
    scenario: Scenario, out_dir: str | Path | None = None
) -> RunResult:
    """Execute a validated scenario and write a reproducible artifact set."""
    errors = validate_scenario(scenario)
    if errors:
        raise FabTwinError(
            "scenario validation failed:\n"
            + "\n".join(f"- {error}" for error in errors)
        )

    engines = [build_engine(name) for name in scenario.engines]
    started = datetime.now(timezone.utc)
    results = [engine.run(scenario) for engine in engines]

    out_root = _resolve_out(out_dir)
    run_id = (
        f"{scenario.id}-{started.strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    store_path = out_root / "fabtwin.db"

    generated_artifacts = []
    seen_artifact_names = {"observations.csv", "report.md", "run.json"}
    for result in results:
        for artifact in result.artifacts:
            if artifact.filename in seen_artifact_names:
                raise FabTwinError(
                    f"engine {result.engine} returned duplicate artifact "
                    f"name {artifact.filename!r}"
                )
            seen_artifact_names.add(artifact.filename)
            generated_artifacts.append(artifact)

    observations = _unique_observations(results)
    rows = _observation_rows(run_id, observations)
    csv_data = _csv_bytes(rows)

    input_records: list[dict[str, Any]] = [
        _input_record("scenario", scenario.path, scenario.sha256)
    ]
    seen_inputs: set[tuple[str, str]] = {
        ("scenario", display_path(scenario.path))
    }
    if scenario.package_path is not None:
        input_records.append(_input_record("package", scenario.package_path))
        seen_inputs.add(
            ("package", display_path(scenario.package_path))
        )
    if scenario.yield_path is not None:
        input_records.append(_input_record("yield", scenario.yield_path))
        seen_inputs.add(
            ("yield", display_path(scenario.yield_path))
        )
    if scenario.factory_path is not None:
        input_records.append(
            _input_record("factory", scenario.factory_path)
        )
        seen_inputs.add(
            ("factory", display_path(scenario.factory_path))
        )
    if scenario.photonic_path is not None:
        input_records.append(
            _input_record("photonic", scenario.photonic_path)
        )
        seen_inputs.add(
            ("photonic", display_path(scenario.photonic_path))
        )
    if scenario.photonic_calibration_path is not None:
        input_records.append(
            _input_record(
                "photonic_calibration",
                scenario.photonic_calibration_path,
            )
        )
        seen_inputs.add(
            (
                "photonic_calibration",
                display_path(scenario.photonic_calibration_path),
            )
        )
    for result in results:
        for input_file in result.inputs:
            key = (input_file.role, display_path(input_file.path))
            if key in seen_inputs:
                continue
            seen_inputs.add(key)
            input_records.append(_input_record(input_file.role, input_file.path))

    reproduce = _reproduce(scenario, out_root)
    report_text = render_report(
        scenario,
        run_id,
        observations,
        results,
        input_records,
        reproduce,
        store_path,
        [artifact.filename for artifact in generated_artifacts],
    )
    report_data = report_text.encode("utf-8")

    observations_path = run_dir / "observations.csv"
    report_path = run_dir / "report.md"
    observations_path.write_bytes(csv_data)
    report_path.write_bytes(report_data)
    generated_records: list[dict[str, Any]] = []
    for generated in generated_artifacts:
        path = run_dir / generated.filename
        path.write_bytes(generated.content)
        generated_records.append(
            {
                "path": generated.filename,
                "media_type": generated.media_type,
                "bytes": len(generated.content),
                "sha256": sha256_bytes(generated.content),
            }
        )
    finished = datetime.now(timezone.utc)

    artifacts = [
        {
            "path": observations_path.name,
            "media_type": "text/csv",
            "bytes": len(csv_data),
            "sha256": sha256_bytes(csv_data),
        },
        {
            "path": report_path.name,
            "media_type": "text/markdown",
            "bytes": len(report_data),
            "sha256": sha256_bytes(report_data),
        },
        *generated_records,
    ]
    evidence_classes: dict[str, int] = {}
    for item in observations:
        evidence_classes[item.evidence_class] = (
            evidence_classes.get(item.evidence_class, 0) + 1
        )
    warnings: list[str] = []
    for result in results:
        warnings.extend(result.warnings)

    manifest_path = run_dir / "run.json"
    manifest = {
        "schema_version": "0.1",
        "run_id": run_id,
        "status": "succeeded",
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "run_dir": display_path(run_dir),
        "manifest_path": display_path(manifest_path),
        "report_path": display_path(report_path),
        "store": {
            "kind": "sqlite",
            "path": display_path(store_path),
            "schema_version": STORE_SCHEMA_VERSION,
        },
        "scenario": {
            "id": scenario.id,
            "path": display_path(scenario.path),
            "sha256": scenario.sha256,
            "product": scenario.product,
            "process": scenario.process,
            "package": scenario.package_ref,
            "yield": scenario.yield_ref,
            "factory": scenario.factory_ref,
            "photonic": scenario.photonic_ref,
            "photonic_calibration": scenario.photonic_calibration_ref,
            "seed": scenario.seed,
            "samples": scenario.samples,
            "outputs": list(scenario.outputs),
        },
        "engines": [
            {
                "name": result.engine,
                "version": result.engine_version,
                "fidelity": result.fidelity,
                "model_version": result.model_version,
                "metadata": dict(result.metadata),
            }
            for result in results
        ],
        "toolchain": {
            "fabtwin_version": FABTWIN_VERSION,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pyyaml": yaml.__version__,
            "source_tree_sha256": source_tree_sha256(),
        },
        "inputs": input_records,
        "observations": {
            "count": len(observations),
            "metrics": sorted({item.metric for item in observations}),
            "evidence_classes": dict(sorted(evidence_classes.items())),
            "fingerprint_sha256": observation_fingerprint(rows),
            "uncertainty": (
                "not_estimated"
                if all(item.uncertainty is None for item in observations)
                else "mixed"
            ),
        },
        "artifacts": artifacts,
        "warnings": warnings,
        "reproduce": reproduce,
        "claim": "scenario estimate; not foundry sign-off",
    }
    manifest_tmp = run_dir / "run.json.tmp"
    manifest_tmp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        ObservationStore(store_path).record_run(manifest, rows)
        manifest_tmp.replace(manifest_path)
    except Exception:
        manifest_tmp.unlink(missing_ok=True)
        raise
    return RunResult(
        run_id=run_id,
        run_dir=run_dir,
        manifest_path=manifest_path,
        store_path=store_path,
        observation_count=len(observations),
    )

"""Stable fingerprints for reproducible Phase 0 baselines.

A baseline fingerprint deliberately excludes run IDs, timestamps, run paths and
platform details. It covers the observation payload and the hashed inputs, so a
model or input change is visible without making the check machine-dependent.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from .provenance import sha256_bytes

_OBSERVATION_FIELDS = (
    "entity_type",
    "entity_id",
    "metric",
    "value",
    "unit",
    "uncertainty",
    "evidence_class",
    "source_artifact",
    "model_version",
)


def observation_fingerprint(
    rows: Iterable[Mapping[str, str]],
) -> str:
    """Hash normalized observation rows without run-local identifiers."""
    canonical = [
        {field: str(row[field]) for field in _OBSERVATION_FIELDS}
        for row in rows
    ]
    canonical.sort(
        key=lambda row: json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_bytes(payload.encode("utf-8"))


def baseline_record(
    manifest: Mapping[str, Any],
    rows: Iterable[Mapping[str, str]],
) -> dict[str, Any]:
    """Build the stable portion of a run manifest for baseline comparison."""
    row_list = list(rows)
    scenario = manifest["scenario"]
    inputs = sorted(
        (
            {
                "role": str(item["role"]),
                "path": str(item["path"]),
                "sha256": str(item["sha256"]),
            }
            for item in manifest["inputs"]
        ),
        key=lambda item: (item["role"], item["path"]),
    )
    return {
        "scenario": str(scenario["id"]),
        "product": str(scenario["product"]),
        "scenario_sha256": str(scenario["sha256"]),
        "inputs": inputs,
        "observation_count": len(row_list),
        "observations_sha256": observation_fingerprint(row_list),
        "evidence_classes": dict(
            manifest["observations"]["evidence_classes"]
        ),
        "model_versions": sorted(
            {str(row["model_version"]) for row in row_list}
        ),
    }

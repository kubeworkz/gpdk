"""Export a website data bundle: fresh runs of the published scenarios.

The bundle is what gridworkz.com reads at build time. Each scenario is run
fresh into a private store, and its run files are copied unchanged, so every
number the site shows traces to a run manifest, its input hashes and its model
versions.

Layout::

    index.json                      bundle index (SITE_SCHEMA_VERSION)
    runs/<scenario-id>/run.json     the run manifest, unchanged
    runs/<scenario-id>/observations.csv
    runs/<scenario-id>/observations.json   the same rows with numeric values
    runs/<scenario-id>/report.md
    runs/<scenario-id>/<engine artifacts>  e.g. wafer_map.svg, wafer_map.csv
"""

from __future__ import annotations

import csv
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .errors import FabTwinError
from .provenance import ROOT, display_path, sha256_bytes
from .run import execute, validate_scenario
from .scenario import load_scenario

SITE_SCHEMA_VERSION = "1"
DEFAULT_SCENARIO_DIR = ROOT / "scenarios"
CLAIM = "scenario estimate; not foundry sign-off"


def default_scenarios() -> list[Path]:
    """Every scenario in ``scenarios/``, in name order."""
    return sorted(DEFAULT_SCENARIO_DIR.glob("*.yaml"))


def _number(text: str) -> float | str | None:
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return text


def _observations_json(csv_bytes: bytes) -> bytes:
    rows = list(csv.DictReader(csv_bytes.decode("utf-8").splitlines()))
    for row in rows:
        row["value"] = _number(row["value"])
        row["uncertainty"] = _number(row["uncertainty"])
    return (json.dumps(rows, indent=1) + "\n").encode("utf-8")


def _file_record(root: Path, path: Path, media_type: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "media_type": media_type,
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def export_site(
    scenario_paths: Iterable[str | Path],
    out_dir: str | Path,
    *,
    commit: str | None = None,
    run_url: str | None = None,
) -> dict[str, Any]:
    """Run each scenario and write the bundle to ``out_dir``; return the index."""
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FabTwinError(f"export directory is not empty: {out}")
    paths = [Path(p) for p in scenario_paths]
    if not paths:
        raise FabTwinError("no scenarios to export")

    scenarios = []
    seen: set[str] = set()
    for path in paths:
        scenario = load_scenario(path)
        errors = validate_scenario(scenario)
        if errors:
            raise FabTwinError(
                f"scenario {display_path(path)} is invalid:\n"
                + "\n".join(f"- {error}" for error in errors)
            )
        if scenario.id in seen:
            raise FabTwinError(f"duplicate scenario id {scenario.id!r}")
        seen.add(scenario.id)
        scenarios.append(scenario)

    out.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="fabtwin-site-") as work:
        for scenario in scenarios:
            result = execute(scenario, work)
            manifest = json.loads(result.manifest_path.read_text("utf-8"))
            dest = out / "runs" / scenario.id
            dest.mkdir(parents=True)

            files = [("run.json", "application/json")]
            files += [(a["path"], a["media_type"]) for a in manifest["artifacts"]]
            records = []
            for name, media_type in files:
                data = (result.run_dir / name).read_bytes()
                (dest / name).write_bytes(data)
                records.append(_file_record(out, dest / name, media_type))
            csv_data = (result.run_dir / "observations.csv").read_bytes()
            (dest / "observations.json").write_bytes(_observations_json(csv_data))
            records.append(
                _file_record(out, dest / "observations.json", "application/json")
            )

            runs.append(
                {
                    "scenario_id": scenario.id,
                    "run_id": manifest["run_id"],
                    "description": scenario.description,
                    "product": scenario.product,
                    "process": scenario.process,
                    "seed": scenario.seed,
                    "samples": scenario.samples,
                    "started_at": manifest["started_at"],
                    "engines": [
                        {
                            "name": e["name"],
                            "version": e["version"],
                            "fidelity": e["fidelity"],
                            "model_version": e["model_version"],
                        }
                        for e in manifest["engines"]
                    ],
                    "observation_count": manifest["observations"]["count"],
                    "evidence_classes": manifest["observations"]["evidence_classes"],
                    "fingerprint_sha256": manifest["observations"][
                        "fingerprint_sha256"
                    ],
                    "warnings": manifest["warnings"],
                    "files": records,
                }
            )

    index = {
        "schema_version": SITE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "run_url": run_url,
        "claim": CLAIM,
        "runs": runs,
    }
    (out / "index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    return index

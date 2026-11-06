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
    browser/manifest.json           what the site's Pyodide runner loads
    browser/gpdk-src.zip            fabtwin, gpdk and the input files they read
    browser/<wheel>                 pure-Python dependencies (``--wheel``)
    browser/inputs.json             each scenario's inputs by role, parsed

The browser files let the site rerun a scenario in the visitor's browser with
``fabtwin.browser.run_scenario`` (Pyodide), on the same code and inputs as the
published runs.
"""

from __future__ import annotations

import csv
import json
import shutil

import yaml
import tempfile
import zipfile
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
BROWSER_SCHEMA_VERSION = "1"
# Python packages and the input trees their engines read, relative to ROOT.
BROWSER_PACKAGES = ("fabtwin", "gpdk")
BROWSER_INPUTS = (
    "scenarios", "chips", "tech", "libraries", "yields",
    "factory", "packages", "photonic",
)
# Pyodide's own builds, loaded with pyodide.loadPackage.
PYODIDE_PACKAGES = ("pyyaml",)
_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def _source_zip(path: Path) -> list[str]:
    """Write fabtwin, gpdk and their inputs to a byte-reproducible zip."""
    names: list[str] = []
    for top in BROWSER_PACKAGES:
        names += [p.relative_to(ROOT).as_posix() for p in (ROOT / top).rglob("*.py")]
    for top in BROWSER_INPUTS:
        names += [p.relative_to(ROOT).as_posix() for p in (ROOT / top).rglob("*.yaml")]
    names = sorted(set(n for n in names if "__pycache__" not in n))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, (ROOT / name).read_bytes())
    return names


def _write_browser(out: Path, wheels: list[Path], scenarios: list[Any]) -> dict[str, Any]:
    browser = out / "browser"
    browser.mkdir()
    names = _source_zip(browser / "gpdk-src.zip")
    wheel_records = []
    for wheel in wheels:
        if wheel.suffix != ".whl" or not wheel.is_file():
            raise FabTwinError(f"not a wheel file: {wheel}")
        shutil.copyfile(wheel, browser / wheel.name)
        wheel_records.append(_file_record(out, browser / wheel.name, "application/zip"))
    # The site reads current input values (slider defaults) from here, so they
    # always match the source in the zip.
    roles = ("chip", "package", "yield", "factory", "photonic")
    by_scenario: dict[str, dict[str, str]] = {}
    files: dict[str, Any] = {}
    for s in scenarios:
        refs = {}
        for role in roles:
            path = getattr(s, f"{role}_path")
            if path is None:
                continue
            refs[role] = display_path(path)
            files[refs[role]] = yaml.safe_load(Path(path).read_text("utf-8"))
        by_scenario[s.id] = refs
    (browser / "inputs.json").write_text(
        json.dumps({"scenarios": by_scenario, "files": files}, indent=1) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": BROWSER_SCHEMA_VERSION,
        "entry": "fabtwin.browser:run_scenario",
        "root": "/gpdk",
        "source": {
            **_file_record(out, browser / "gpdk-src.zip", "application/zip"),
            "files": len(names),
        },
        "wheels": wheel_records,
        "pyodide_packages": list(PYODIDE_PACKAGES),
        "inputs": _file_record(out, browser / "inputs.json", "application/json"),
        "scenarios": {
            s.id: display_path(s.path) for s in scenarios
        },
    }
    (browser / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


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
    wheels: Iterable[str | Path] = (),
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

    _write_browser(out, [Path(w) for w in wheels], scenarios)

    index = {
        "schema_version": SITE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "run_url": run_url,
        "claim": CLAIM,
        "browser": "browser/manifest.json",
        "runs": runs,
    }
    (out / "index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    return index

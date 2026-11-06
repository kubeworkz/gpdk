"""Reproduce Phase 0 from an isolated source-only tree.

The tree deliberately contains no ``out/``, caches, or VCS metadata. That is
the same starting state as a clean checkout, so the test fails if a baseline
depends on previously generated artifacts or local state.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fabtwin.baseline import baseline_record

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORIES = (
    "baselines",
    "chips",
    "fabtwin",
    "gpdk",
    "libraries",
    "packages",
    "scenarios",
    "tech",
)
SOURCE_FILES = ("pytest.ini", "requirements.txt")
SCENARIOS = (
    ("grx930_28nm_baseline.yaml", "grx930", 27),
    ("g100_28nm_baseline.yaml", "g100", 40),
    ("pta_28nm_baseline.yaml", "pta", 8),
)


def _copy_source_tree(destination: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for name in SOURCE_DIRECTORIES:
        shutil.copytree(
            ROOT / name,
            destination / name,
            ignore=ignore,
        )
    for name in SOURCE_FILES:
        shutil.copy2(ROOT / name, destination / name)


def _run(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "fabtwin", *args],
        cwd=workspace,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_json(workspace: Path, *args: str) -> object:
    completed = _run(workspace, *args)
    assert completed.returncode == 0, (
        f"command failed: fabtwin {' '.join(args)}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    return json.loads(completed.stdout)


def test_clean_source_tree_reproduces_all_phase0_baselines(tmp_path):
    workspace = tmp_path / "clean-checkout"
    workspace.mkdir()
    _copy_source_tree(workspace)

    assert not (workspace / "out").exists()

    for filename, _product, _count in SCENARIOS:
        completed = _run(
            workspace,
            "run",
            f"scenarios/{filename}",
        )
        assert completed.returncode == 0, (
            f"baseline failed: {filename}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )

    runs = _run_json(workspace, "query", "--runs", "--json")
    assert isinstance(runs, list)
    assert len(runs) == len(SCENARIOS)
    observed = {
        row["product"]: row["observation_count"]
        for row in runs
        if row["status"] == "succeeded"
    }
    assert observed == {
        product: count for _filename, product, count in SCENARIOS
    }
    assert {row["status"] for row in runs} == {"succeeded"}

    baseline = json.loads(
        (workspace / "baselines" / "phase0_baseline.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(baseline["products"]) == {
        product for _filename, product, _count in SCENARIOS
    }
    run_ids = {row["product"]: row["run_id"] for row in runs}
    for _filename, product, _count in SCENARIOS:
        run_dir = workspace / "out" / "fabtwin" / run_ids[product]
        manifest = json.loads(
            (run_dir / "run.json").read_text(encoding="utf-8")
        )
        with (run_dir / "observations.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            rows = list(csv.DictReader(handle))
        record = baseline_record(manifest, rows)
        assert record == baseline["products"][product]
        assert manifest["observations"]["fingerprint_sha256"] == (
            record["observations_sha256"]
        )

    verification = _run_json(workspace, "verify-artifacts", "--json")
    assert isinstance(verification, dict)
    assert verification["checked"] == 16
    assert verification["ok"] == 16
    assert verification["failed"] == 0
    assert len(verification["run_artifacts"]) == 6
    assert len(verification["inputs"]) == 10
    assert verification["comparison_artifacts"] == []
    assert {row["status"] for row in verification["run_artifacts"]} == {"ok"}
    assert {row["status"] for row in verification["inputs"]} == {"ok"}
    assert "package" in {row["role"] for row in verification["inputs"]}
    assert (workspace / "out" / "fabtwin" / "fabtwin.db").is_file()

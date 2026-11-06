"""The website data bundle: fresh runs, unchanged run files, a verifiable index."""

from __future__ import annotations

import csv
import json

import pytest

from fabtwin.cli import main
from fabtwin.errors import FabTwinError
from fabtwin.provenance import ROOT, sha256_file
from fabtwin.site_export import SITE_SCHEMA_VERSION, export_site

BASELINE = ROOT / "scenarios" / "grx930_28nm_baseline.yaml"
WAFER_MAP = ROOT / "scenarios" / "grx930_yield_wafer_map_28nm.yaml"


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp("bundle")
    index = export_site([BASELINE, WAFER_MAP], out, commit="abc123")
    return out, index


def test_index_lists_each_scenario_once(bundle):
    _, index = bundle
    assert index["schema_version"] == SITE_SCHEMA_VERSION
    assert index["commit"] == "abc123"
    assert index["claim"] == "scenario estimate; not foundry sign-off"
    assert [r["scenario_id"] for r in index["runs"]] == [
        "grx930_28nm_baseline",
        "grx930_yield_wafer_map_28nm",
    ]


def test_every_listed_file_exists_with_its_hash(bundle):
    out, index = bundle
    for run in index["runs"]:
        assert run["files"]
        for record in run["files"]:
            path = out / record["path"]
            assert path.is_file()
            assert path.stat().st_size == record["bytes"]
            assert sha256_file(path) == record["sha256"]


def test_engine_artifacts_are_published(bundle):
    out, _ = bundle
    run_dir = out / "runs" / "grx930_yield_wafer_map_28nm"
    for name in ("run.json", "observations.csv", "report.md", "wafer_map.svg",
                 "wafer_map.csv", "observations.json"):
        assert (run_dir / name).is_file(), name


def test_observations_json_matches_the_csv(bundle):
    out, _ = bundle
    run_dir = out / "runs" / "grx930_yield_wafer_map_28nm"
    with (run_dir / "observations.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    data = json.loads((run_dir / "observations.json").read_text("utf-8"))
    assert len(data) == len(rows)
    for row, item in zip(rows, data):
        assert item["metric"] == row["metric"]
        assert item["value"] == float(row["value"])
        if row["uncertainty"]:
            assert item["uncertainty"] == float(row["uncertainty"])
        else:
            assert item["uncertainty"] is None


def test_baseline_run_reproduces_its_committed_fingerprint(bundle):
    _, index = bundle
    baselines = json.loads(
        (ROOT / "baselines" / "phase0_baseline.json").read_text("utf-8")
    )["products"]
    run = index["runs"][0]
    assert run["fingerprint_sha256"] == baselines["grx930"]["observations_sha256"]


def test_refuses_a_non_empty_directory(tmp_path):
    (tmp_path / "stale.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FabTwinError, match="not empty"):
        export_site([BASELINE], tmp_path)


def test_refuses_a_duplicate_scenario(tmp_path):
    with pytest.raises(FabTwinError, match="duplicate scenario id"):
        export_site([BASELINE, BASELINE], tmp_path / "bundle")


def test_cli_writes_the_bundle(tmp_path, capsys):
    out = tmp_path / "bundle"
    assert main(["export-site", str(out), "--scenario", str(BASELINE)]) == 0
    assert "1 runs" in capsys.readouterr().out
    assert (out / "index.json").is_file()

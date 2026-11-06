"""The in-memory runner the website calls through Pyodide, and its bundle."""

from __future__ import annotations

import csv
import json
import zipfile

import pytest

from fabtwin.browser import run_scenario
from fabtwin.errors import FabTwinError
from fabtwin.provenance import ROOT, sha256_file
from fabtwin.run import execute
from fabtwin.scenario import load_scenario
from fabtwin.site_export import export_site

WAFER_MAP = ROOT / "scenarios" / "grx930_yield_wafer_map_28nm.yaml"
FACTORY = ROOT / "scenarios" / "g100_factory_28nm.yaml"
PTA = ROOT / "scenarios" / "pta_28nm_baseline.yaml"


def _value(result, entity_type, entity_id, metric):
    return next(
        o["value"] for o in result["observations"]
        if (o["entity_type"], o["entity_id"], o["metric"]) == (entity_type, entity_id, metric)
    )


@pytest.fixture(scope="module")
def wafer_map():
    return run_scenario(WAFER_MAP)


def test_without_overrides_it_matches_a_recorded_run(wafer_map, tmp_path):
    run = execute(load_scenario(WAFER_MAP), tmp_path)
    with (run.run_dir / "observations.csv").open(encoding="utf-8") as handle:
        recorded = {
            (r["entity_type"], r["entity_id"], r["metric"]): float(r["value"])
            for r in csv.DictReader(handle)
        }
    mine = {
        (o["entity_type"], o["entity_id"], o["metric"]): o["value"]
        for o in wafer_map["observations"]
    }
    assert mine.keys() == recorded.keys()
    for key, value in recorded.items():
        assert mine[key] == pytest.approx(value, rel=1e-12, abs=0)
    assert wafer_map["overrides"] == []
    assert "wafer_map.csv" in wafer_map["artifacts"]


def test_an_override_moves_the_result_and_is_reported(wafer_map):
    worse = run_scenario(WAFER_MAP, {"yield": {"defects.density_per_cm2": 0.2}})
    assert worse["overrides"] == [
        {"role": "yield", "path": "defects.density_per_cm2", "from": 0.08, "to": 0.2}
    ]
    assert _value(worse, "wafer_map", "grx930", "die_yield_mean") < _value(
        wafer_map, "wafer_map", "grx930", "die_yield_mean"
    )


def test_a_list_entry_is_selected_by_id():
    result = run_scenario(FACTORY, {"factory": {"tool_groups.litho.tools": 4}})
    assert result["overrides"][0]["from"] == 3.0
    assert _value(result, "tool_group", "baseline:litho", "tool_utilization") < 0.7


def test_overrides_do_not_touch_the_input_files():
    before = sha256_file(ROOT / "yields" / "grx930_28nm.yaml")
    run_scenario(WAFER_MAP, {"yield": {"defects.density_per_cm2": 0.2}})
    assert sha256_file(ROOT / "yields" / "grx930_28nm.yaml") == before


@pytest.mark.parametrize(
    ("scenario", "overrides", "message"),
    [
        (WAFER_MAP, {"yield": {"defects.nope": 1}}, "does not exist"),
        (WAFER_MAP, {"yield": {"wafer": 1}}, "is not a number"),
        (WAFER_MAP, {"yield": {"defects.density_per_cm2": True}}, "finite number"),
        (WAFER_MAP, {"yield": {"defects.density_per_cm2": float("nan")}}, "finite number"),
        (WAFER_MAP, {"chip": {"x": 1}}, "unknown override role"),
        (FACTORY, {"factory": {"tool_groups.nope.tools": 1}}, "no single entry"),
        (PTA, {"yield": {"defects.density_per_cm2": 0.1}}, "has no 'yield' input"),
    ],
)
def test_bad_overrides_are_rejected(scenario, overrides, message):
    with pytest.raises(FabTwinError, match=message):
        run_scenario(scenario, overrides)


def test_export_writes_a_reproducible_browser_bundle(tmp_path):
    wheel = tmp_path / "demo-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("demo/__init__.py", "")
    first = tmp_path / "a"
    second = tmp_path / "b"
    index = export_site([WAFER_MAP], first, wheels=[wheel])
    export_site([WAFER_MAP], second)
    assert index["browser"] == "browser/manifest.json"
    manifest = json.loads((first / "browser" / "manifest.json").read_text("utf-8"))
    assert manifest["entry"] == "fabtwin.browser:run_scenario"
    assert manifest["scenarios"] == {
        "grx930_yield_wafer_map_28nm": "scenarios/grx930_yield_wafer_map_28nm.yaml"
    }
    assert [w["path"] for w in manifest["wheels"]] == ["browser/demo-1.0-py3-none-any.whl"]
    source = first / manifest["source"]["path"]
    assert sha256_file(source) == manifest["source"]["sha256"]
    assert sha256_file(source) == sha256_file(second / "browser" / "gpdk-src.zip")
    names = zipfile.ZipFile(source).namelist()
    assert "fabtwin/browser.py" in names
    assert "yields/grx930_28nm.yaml" in names
    assert not any("__pycache__" in n for n in names)


def test_export_rejects_a_file_that_is_not_a_wheel(tmp_path):
    bogus = tmp_path / "simpy.tar.gz"
    bogus.write_bytes(b"")
    with pytest.raises(FabTwinError, match="not a wheel"):
        export_site([WAFER_MAP], tmp_path / "bundle", wheels=[bogus])

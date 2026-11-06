"""Phase 0 tests for the foundry-twin runner and its gpdk adapter."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from fabtwin.adapters.gpdk import GpdkEngine
from fabtwin.baseline import observation_fingerprint
from fabtwin.cli import main
from fabtwin.errors import ScenarioValidationError
from fabtwin.provenance import ROOT, sha256_file
from fabtwin.run import execute, validate_scenario
from fabtwin.scenario import load_scenario
from fabtwin.store import ObservationStore

SCENARIO = ROOT / "scenarios" / "grx930_28nm_baseline.yaml"
G100_SCENARIO = ROOT / "scenarios" / "g100_28nm_baseline.yaml"
PTA_SCENARIO = ROOT / "scenarios" / "pta_28nm_baseline.yaml"
YIELD_SCENARIO = ROOT / "scenarios" / "grx930_yield_28nm.yaml"
YIELD_SENSITIVITY_SCENARIO = (
    ROOT / "scenarios" / "grx930_yield_sensitivity_28nm.yaml"
)
YIELD_VARIATION_SCENARIO = (
    ROOT / "scenarios" / "grx930_yield_variation_28nm.yaml"
)
YIELD_WAFER_MAP_SCENARIO = (
    ROOT / "scenarios" / "grx930_yield_wafer_map_28nm.yaml"
)


@pytest.fixture(scope="module")
def scenario():
    return load_scenario(SCENARIO)


def _variant(tmp_path: Path, **changes) -> Path:
    raw = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    raw.update(changes)
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def test_scenario_loads_with_hash(scenario):
    assert scenario.id == "grx930_28nm_baseline"
    assert scenario.product == "grx930"
    assert scenario.process == "grx28@0.1.0"
    assert scenario.engines == ("gpdk",)
    assert scenario.samples == 1
    assert len(scenario.sha256) == 64
    assert scenario.chip_path == ROOT / "chips" / "grx930.yaml"
    assert scenario.package_path is None


def test_phase0_baselines_validate():
    for path in (SCENARIO, G100_SCENARIO, PTA_SCENARIO):
        loaded = load_scenario(path)
        assert validate_scenario(loaded) == []


def test_unknown_scenario_field_is_rejected(tmp_path):
    path = _variant(tmp_path, unexpected_field=True)
    with pytest.raises(ScenarioValidationError) as exc:
        load_scenario(path)
    assert "unexpected_field" in str(exc.value)


def test_gpdk_adapter_emits_measured_and_projected_rows(scenario):
    result = GpdkEngine().run(scenario)
    assert result.engine == "gpdk"
    assert result.fidelity == "F0"
    assert len(result.metadata["design_points"]) == 4
    assert len(result.observations) == 3 + 4 * 6
    assert {item.evidence_class for item in result.observations} == {
        "measured",
        "assumed",
    }
    assert all(item.unit for item in result.observations)
    measured = [
        item for item in result.observations if item.evidence_class == "measured"
    ]
    assert len(measured) == 3
    assert measured[0].metric.startswith("as_built_")


def test_run_writes_manifest_and_hashes(scenario, tmp_path):
    result = execute(scenario, tmp_path)
    assert result.observation_count == 27
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "succeeded"
    assert manifest["scenario"]["sha256"] == scenario.sha256
    assert manifest["observations"]["count"] == 27
    assert manifest["observations"]["uncertainty"] == "not_estimated"
    assert manifest["store"]["kind"] == "sqlite"
    assert manifest["store"]["path"].endswith("fabtwin.db")
    assert {item["role"] for item in manifest["inputs"]} == {
        "scenario",
        "chip",
        "tech",
    }
    for artifact in manifest["artifacts"]:
        path = result.run_dir / artifact["path"]
        assert path.exists()
        assert sha256_file(path) == artifact["sha256"]
        assert path.stat().st_size == artifact["bytes"]

    with (result.run_dir / "observations.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 27
    assert all(row["run_id"] == result.run_id for row in rows)
    assert all(row["unit"] for row in rows)
    assert {row["evidence_class"] for row in rows} == {"measured", "assumed"}
    assert manifest["observations"]["fingerprint_sha256"] == (
        observation_fingerprint(rows)
    )


def test_same_scenario_produces_same_observations(scenario, tmp_path):
    first = execute(scenario, tmp_path / "first")
    second = execute(scenario, tmp_path / "second")
    keys = [
        "entity_type",
        "entity_id",
        "metric",
        "value",
        "unit",
        "evidence_class",
        "source_artifact",
        "model_version",
    ]

    def rows(result):
        with (result.run_dir / "observations.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            return [
                {key: row[key] for key in keys}
                for row in csv.DictReader(handle)
            ]

    assert rows(first) == rows(second)
    assert first.run_id != second.run_id


def test_g100_baseline_scenario_runs(tmp_path):
    loaded = load_scenario(G100_SCENARIO)
    assert loaded.product == "g100"
    result = execute(loaded, tmp_path)
    assert result.observation_count == 40
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenario"]["package"] is None
    assert {item["role"] for item in manifest["inputs"]} == {
        "scenario",
        "chip",
        "tech",
    }
    with (result.run_dir / "observations.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 40
    assert {row["evidence_class"] for row in rows} == {"assumed"}
    assert all(row["unit"] for row in rows)


def test_pta_baseline_records_topology_and_package(tmp_path):
    loaded = load_scenario(PTA_SCENARIO)
    assert loaded.product == "pta"
    assert loaded.package_ref == "packages/mcm_si.yaml"
    assert loaded.package_path == ROOT / "packages" / "mcm_si.yaml"
    result = execute(loaded, tmp_path)
    assert result.observation_count == 8
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenario"]["package"] == "packages/mcm_si.yaml"
    assert {item["role"] for item in manifest["inputs"]} == {
        "scenario",
        "chip",
        "package",
        "tech",
    }
    package_meta = manifest["engines"][0]["metadata"]["package"]
    assert package_meta["id"] == "mcm_si"
    assert package_meta["revision"] == "0.1.0"
    report_text = (result.run_dir / "report.md").read_text(encoding="utf-8")
    assert "packages/mcm_si.yaml" in report_text
    with (result.run_dir / "observations.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    values = {row["metric"]: float(row["value"]) for row in rows}
    assert len(rows) == 8
    assert values["mzi_count"] == 16.0
    assert values["optical_window_m"] == pytest.approx(200e-6)
    assert values["wavelength_m"] == pytest.approx(1550e-9)
    assert {row["evidence_class"] for row in rows} == {"assumed"}
    assert {row["source_artifact"] for row in rows} == {"chips/pta.yaml"}


def test_yield_scenario_records_wafer_package_and_uncertainty(tmp_path):
    loaded = load_scenario(YIELD_SCENARIO)
    assert loaded.product == "grx930"
    assert loaded.yield_ref == "yields/grx930_28nm.yaml"
    result = execute(loaded, tmp_path)
    assert result.observation_count == 9
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenario"]["yield"] == "yields/grx930_28nm.yaml"
    assert {item["role"] for item in manifest["inputs"]} == {
        "scenario",
        "chip",
        "yield",
        "tech",
    }
    engine = manifest["engines"][0]
    assert engine["name"] == "yield"
    assert engine["metadata"]["package"]["name"] == "TFBGA-196"
    with (result.run_dir / "observations.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    values = {row["metric"]: float(row["value"]) for row in rows}
    assert values["gross_dies_per_wafer"] > values[
        "good_packages_per_wafer"
    ]
    assert values["good_packages_per_wafer"] > 0.0
    assert 0.0 < values["die_yield"] < 1.0
    assert values["cost_per_good_package_usd"] > 0.0
    uncertainties = {row["metric"]: row["uncertainty"] for row in rows}
    assert uncertainties["die_yield"]
    assert uncertainties["cost_per_good_package_usd"]
    assert {row["evidence_class"] for row in rows} == {"assumed"}
    assert {row["model_version"] for row in rows} == {
        "yield-assumptions@0.2.0"
    }
    assert {row["source_artifact"] for row in rows} == {
        "yields/grx930_28nm.yaml"
    }


def test_yield_sensitivity_scenario_records_curves(tmp_path):
    loaded = load_scenario(YIELD_SENSITIVITY_SCENARIO)
    assert loaded.engines == ("yield_sensitivity",)
    assert validate_scenario(loaded) == []
    result = execute(loaded, tmp_path)
    assert result.observation_count == 56
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    engine = manifest["engines"][0]
    assert engine["name"] == "yield_sensitivity"
    assert engine["metadata"]["curves"] == {
        "defect_density_per_cm2": [0.02, 0.05, 0.08, 0.12, 0.2],
        "pad_counts": [57, 112, 178, 220],
        "assembly_per_pad_ppm": [2.0, 5.0, 8.0, 12.0, 20.0],
    }
    with (result.run_dir / "observations.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 56
    assert {row["entity_type"] for row in rows} == {"sensitivity_point"}
    assert {row["evidence_class"] for row in rows} == {"assumed"}
    assert {row["source_artifact"] for row in rows} == {
        "yields/grx930_28nm.yaml"
    }
    points = {row["entity_id"] for row in rows}
    assert "defect_density:0.2" in points
    assert "pad_count:178" in points
    assert "assembly_tolerance:20" in points
    assert len(points) == 14
    by_metric = {}
    for row in rows:
        assert row["unit"]
        by_metric.setdefault(row["metric"], []).append(row)
    assert float(by_metric["pad_count"][0]["value"]) == 57.0
    assert all(0.0 < float(row["value"]) <= 1.0 for row in by_metric["die_yield"])
    assert all(float(row["uncertainty"]) > 0.0 for row in by_metric["die_yield"])
    assert all(
        float(row["uncertainty"]) > 0.0
        for row in by_metric["cost_per_good_package_usd"]
    )


def test_yield_variation_scenario_records_lot_statistics(tmp_path):
    loaded = load_scenario(YIELD_VARIATION_SCENARIO)
    assert loaded.engines == ("yield_variation",)
    assert validate_scenario(loaded) == []
    result = execute(loaded, tmp_path)
    assert result.observation_count == 6
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    engine = manifest["engines"][0]
    assert engine["name"] == "yield_variation"
    assert engine["metadata"]["variation"] == {
        "wafers_per_lot": 25,
        "defect_density_cv_lot": 0.15,
        "defect_density_cv_wafer": 0.1,
        "assembly_ppm_cv_lot": 0.1,
    }
    assert engine["metadata"]["simulation"]["lots"] == 40
    assert engine["metadata"]["simulation"]["wafers"] == 1000
    with (result.run_dir / "observations.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6
    values = {row["metric"]: row for row in rows}
    assert {row["entity_type"] for row in rows} == {"lot_simulation"}
    assert {row["evidence_class"] for row in rows} == {"assumed"}
    assert {row["source_artifact"] for row in rows} == {
        "yields/grx930_28nm.yaml"
    }
    assert 0.0 < float(values["die_yield_mean"]["value"]) < 1.0
    assert float(values["wafer_to_wafer_die_yield_sigma"]["value"]) > 0.0
    assert float(values["lot_to_lot_die_yield_sigma"]["value"]) > float(
        values["wafer_to_wafer_die_yield_sigma"]["value"]
    )
    assert values["die_yield_mean"]["uncertainty"]
    assert values["cost_per_good_package_usd_mean"]["uncertainty"]
    assert not values["wafer_to_wafer_die_yield_sigma"]["uncertainty"]
    assert not values["lot_to_lot_die_yield_sigma"]["uncertainty"]
    assert float(values["good_packages_per_wafer_mean"]["value"]) > 0.0
    assert float(values["cost_per_good_package_usd_mean"]["value"]) > 0.0


def test_wafer_map_scenario_records_radial_zones(tmp_path):
    loaded = load_scenario(YIELD_WAFER_MAP_SCENARIO)
    assert loaded.engines == ("yield_wafer_map",)
    assert validate_scenario(loaded) == []
    result = execute(loaded, tmp_path)
    assert result.observation_count == 28
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    engine = manifest["engines"][0]
    assert engine["name"] == "yield_wafer_map"
    assert engine["metadata"]["spatial"] == {
        "edge_boost": 2.0,
        "radial_exponent": 3.0,
        "radial_bins": 5,
        "angular_amplitude": 0.18,
        "angular_harmonics": 3,
        "angular_phase_deg": 20.0,
        "clusters": [
            {
                "x_mm": 62.0,
                "y_mm": 48.0,
                "sigma_mm": 15.0,
                "strength": 1.4,
            },
            {
                "x_mm": -94.0,
                "y_mm": -46.0,
                "sigma_mm": 11.0,
                "strength": 2.0,
            },
        ],
    }
    assert len(engine["metadata"]["zones"]) == 5
    with (result.run_dir / "observations.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 28
    assert {row["entity_type"] for row in rows} == {
        "wafer_map",
        "wafer_zone",
    }
    assert {row["evidence_class"] for row in rows} == {"assumed"}
    aggregate = {
        row["metric"]: row
        for row in rows
        if row["entity_type"] == "wafer_map"
    }
    zone_rows = [row for row in rows if row["entity_type"] == "wafer_zone"]
    assert len(zone_rows) == 20
    assert 0.0 < float(aggregate["edge_to_center_yield_ratio"]["value"]) < 1.0
    assert float(aggregate["radial_yield_slope_per_mm"]["value"]) < 0.0
    assert aggregate["die_yield_mean"]["uncertainty"]
    assert aggregate["cost_per_good_package_usd"]["uncertainty"]
    densities = [
        float(row["value"])
        for row in zone_rows
        if row["metric"] == "defect_density_per_cm2"
    ]
    assert len(densities) == 5
    assert densities == sorted(densities)
    assert all(row["unit"] for row in rows)
    artifact_paths = {item["path"] for item in manifest["artifacts"]}
    assert {
        "observations.csv",
        "report.md",
        "wafer_map.csv",
        "wafer_map.svg",
    } <= artifact_paths
    map_csv = (result.run_dir / "wafer_map.csv").read_text(encoding="utf-8")
    assert map_csv.startswith("die_index,x_mm,y_mm")
    assert len(map_csv.splitlines()) == 4866
    map_svg = (result.run_dir / "wafer_map.svg").read_text(encoding="utf-8")
    assert map_svg.startswith("<?xml")
    assert map_svg.count('class="die"') == 4865
    assert map_svg.count('class="cluster"') == 2
    assert "angular 3θ" in map_svg
    report_text = (result.run_dir / "report.md").read_text(encoding="utf-8")
    assert "wafer_map.svg" in report_text
    verified = ObservationStore(result.store_path).verify_artifacts()
    assert len(verified["run_artifacts"]) == 4
    assert {row["status"] for row in verified["run_artifacts"]} == {"ok"}


def test_sqlite_store_indexes_run(scenario, tmp_path):
    result = execute(scenario, tmp_path)
    assert result.store_path == tmp_path / "fabtwin.db"
    store = ObservationStore(result.store_path)
    assert len(store.query_observations(run_id=result.run_id)) == 27
    assert len(
        store.query_observations(
            run_id=result.run_id, metric="die_area_m2"
        )
    ) == 4
    assert len(
        store.query_observations(
            run_id=result.run_id, evidence_class="measured"
        )
    ) == 3
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0]["run_id"] == result.run_id
    assert runs[0]["observation_count"] == 27

    second = execute(scenario, tmp_path)
    runs = store.list_runs()
    assert {row["run_id"] for row in runs} == {
        result.run_id,
        second.run_id,
    }
    assert len(store.query_observations(metric="die_area_m2")) == 8
    assert not (result.run_dir / "run.json.tmp").exists()


def test_query_cli_reads_sqlite(scenario, tmp_path, capsys):
    result = execute(scenario, tmp_path)
    status = main(
        [
            "query",
            "--db",
            str(result.store_path),
            "--run",
            result.run_id,
            "--metric",
            "die_area_m2",
            "--json",
        ]
    )
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 4
    assert {row["metric"] for row in payload} == {"die_area_m2"}
    assert {row["run_id"] for row in payload} == {result.run_id}


def test_compare_flags_value_and_evidence_changes(
    scenario, tmp_path, capsys
):
    first = execute(scenario, tmp_path)
    second = execute(scenario, tmp_path)
    store = ObservationStore(first.store_path)

    identical = store.compare_runs(first.run_id, first.run_id)
    assert identical["summary"]["rows"] == 27
    assert identical["summary"]["changed"] == 0

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE observations SET value = value * 2, "
            "evidence_class = ? WHERE run_id = ? "
            "AND entity_id = ? AND metric = ?",
            (
                "measured",
                second.run_id,
                "grx930:node9t",
                "die_area_m2",
            ),
        )

    diff = store.compare_runs(first.run_id, second.run_id)
    changed = next(
        row
        for row in diff["rows"]
        if row["entity_id"] == "grx930:node9t"
        and row["metric"] == "die_area_m2"
    )
    filtered = store.compare_runs(
        first.run_id, second.run_id, only_changes=True
    )
    assert filtered["filter"] == {
        "only_changes": True,
        "matched_rows": 27,
        "shown_rows": 1,
    }
    assert filtered["rows"] == [changed]
    assert changed["flags"] == ["value", "evidence"]
    assert changed["value_changed"] is True
    assert changed["evidence_changed"] is True
    assert changed["evidence_a"] == "assumed"
    assert changed["evidence_b"] == "measured"
    assert changed["delta"] == pytest.approx(1.299242025e-05)
    assert changed["delta_pct"] == pytest.approx(100.0)
    assert diff["summary"]["changed"] == 1
    assert diff["summary"]["value_changes"] == 1
    assert diff["summary"]["evidence_changes"] == 1

    status = main(
        [
            "compare",
            first.run_id,
            second.run_id,
            "--db",
            str(store.path),
            "--only-changes",
            "--json",
        ]
    )
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_a"]["run_id"] == first.run_id
    assert payload["run_b"]["run_id"] == second.run_id
    assert payload["summary"]["evidence_changes"] == 1
    assert payload["filter"]["shown_rows"] == 1
    assert len(payload["rows"]) == 1
    report_path = Path(payload["report_path"])
    assert report_path.is_file()
    report_text = report_path.read_text(encoding="utf-8")
    assert "This report shows changed rows only." in report_text
    assert "assumed -> measured" in report_text

    artifact = payload["report_artifact"]
    assert artifact["run_a"] == first.run_id
    assert artifact["run_b"] == second.run_id
    assert artifact["path"] == payload["report_path"]
    assert artifact["media_type"] == "text/markdown"
    assert artifact["bytes"] == report_path.stat().st_size
    assert artifact["sha256"] == sha256_file(report_path)
    assert store.list_comparison_artifacts() == [artifact]

    status = main(
        [
            "query",
            "--db",
            str(store.path),
            "--reports",
            "--json",
        ]
    )
    assert status == 0
    indexed = json.loads(capsys.readouterr().out)
    assert indexed == [artifact]


def test_comparison_report_registration_updates_same_path(
    scenario, tmp_path, capsys
):
    first = execute(scenario, tmp_path)
    second = execute(scenario, tmp_path)
    report_path = tmp_path / "comparison.md"

    status = main(
        [
            "compare",
            first.run_id,
            second.run_id,
            "--db",
            str(first.store_path),
            "--report",
            str(report_path),
            "--json",
        ]
    )
    assert status == 0
    initial = json.loads(capsys.readouterr().out)["report_artifact"]

    status = main(
        [
            "compare",
            first.run_id,
            second.run_id,
            "--db",
            str(first.store_path),
            "--report",
            str(report_path),
            "--only-changes",
            "--json",
        ]
    )
    assert status == 0
    updated = json.loads(capsys.readouterr().out)["report_artifact"]

    assert updated["comparison_id"] == initial["comparison_id"]
    assert updated["sha256"] != initial["sha256"]
    assert updated["sha256"] == sha256_file(report_path)
    assert len(ObservationStore(first.store_path).list_comparison_artifacts()) == 1


def test_verify_artifacts_checks_runs_and_comparison_reports(
    scenario, tmp_path, capsys
):
    first = execute(scenario, tmp_path)
    second = execute(scenario, tmp_path)
    status = main(
        [
            "compare",
            first.run_id,
            second.run_id,
            "--db",
            str(first.store_path),
            "--json",
        ]
    )
    assert status == 0
    comparison = json.loads(capsys.readouterr().out)
    comparison_path = Path(comparison["report_path"])

    status = main(
        [
            "verify-artifacts",
            "--db",
            str(first.store_path),
            "--json",
        ]
    )
    assert status == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["checked"] == 11
    assert verified["ok"] == 11
    assert verified["failed"] == 0
    assert len(verified["run_artifacts"]) == 4
    assert len(verified["inputs"]) == 6
    assert len(verified["comparison_artifacts"]) == 1
    assert {row["status"] for row in verified["run_artifacts"]} == {"ok"}
    assert {row["status"] for row in verified["inputs"]} == {"ok"}
    assert {row["role"] for row in verified["inputs"]} == {
        "scenario",
        "chip",
        "tech",
    }
    assert verified["comparison_artifacts"][0]["path"] == comparison["report_path"]
    assert (
        verified["comparison_artifacts"][0]["actual_sha256"]
        == comparison["report_artifact"]["sha256"]
    )

    with (second.run_dir / "report.md").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write("\n")
    comparison_path.unlink()

    status = main(
        [
            "verify-artifacts",
            "--db",
            str(first.store_path),
            "--json",
        ]
    )
    assert status == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["checked"] == 11
    assert failed["ok"] == 9
    assert failed["failed"] == 2
    changed_run = next(
        row
        for row in failed["run_artifacts"]
        if row["run_id"] == second.run_id
        and Path(row["path"]).name == "report.md"
    )
    assert changed_run["status"] == "size_and_hash_mismatch"
    assert failed["comparison_artifacts"][0]["status"] == "missing"


def test_verify_artifacts_checks_input_hashes(tmp_path, capsys):
    scenario_path = _variant(tmp_path)
    copied_scenario = load_scenario(scenario_path)
    result = execute(copied_scenario, tmp_path / "runs")

    status = main(
        [
            "verify-artifacts",
            "--db",
            str(result.store_path),
            "--json",
        ]
    )
    assert status == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["checked"] == 5
    assert verified["ok"] == 5
    assert {row["role"] for row in verified["inputs"]} == {
        "scenario",
        "chip",
        "tech",
    }
    assert {row["status"] for row in verified["inputs"]} == {"ok"}

    with scenario_path.open("a", encoding="utf-8") as handle:
        handle.write("\n")

    status = main(
        [
            "verify-artifacts",
            "--db",
            str(result.store_path),
            "--json",
        ]
    )
    assert status == 1
    failed = json.loads(capsys.readouterr().out)
    changed = next(
        row for row in failed["inputs"] if row["role"] == "scenario"
    )
    assert changed["status"] == "size_and_hash_mismatch"
    assert failed["failed"] == 1


def test_gpdk_rejects_more_than_one_sample(tmp_path):
    path = _variant(tmp_path, samples=2)
    scenario = load_scenario(path)
    errors = validate_scenario(scenario)
    assert any("samples must be 1" in error for error in errors)

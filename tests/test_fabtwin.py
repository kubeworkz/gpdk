"""Phase 0 tests for the foundry-twin runner and its gpdk adapter."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from fabtwin.adapters.gpdk import GpdkEngine
from fabtwin.cli import main
from fabtwin.errors import ScenarioValidationError
from fabtwin.provenance import ROOT, sha256_file
from fabtwin.run import execute, validate_scenario
from fabtwin.scenario import load_scenario
from fabtwin.store import ObservationStore

SCENARIO = ROOT / "scenarios" / "grx930_28nm_baseline.yaml"


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


def test_gpdk_rejects_more_than_one_sample(tmp_path):
    path = _variant(tmp_path, samples=2)
    scenario = load_scenario(path)
    errors = validate_scenario(scenario)
    assert any("samples must be 1" in error for error in errors)

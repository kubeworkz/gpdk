"""Tests for MES extract verification and event-derived replay metrics."""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from fabtwin.errors import MesReplayError
from fabtwin.mes import generate as generate_mes
from fabtwin.mes_replay import load_replay
from fabtwin.provenance import ROOT
from fabtwin.run import execute, validate_scenario
from fabtwin.scenario import load_scenario

FIXTURE = ROOT / "factory" / "mes_smoke"
MANIFEST = FIXTURE / "manifest.json"
SCENARIO = ROOT / "scenarios" / "mes_line_replay.yaml"


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "mes"
    shutil.copytree(FIXTURE, target)
    return target / "manifest.json"


def test_replay_verifies_the_extract_and_derives_metrics():
    result = load_replay(MANIFEST)
    assert result.evidence_class == "assumed"
    assert result.synthetic is True
    assert result.completed_lots == 3
    assert result.completed_wafers == 50
    assert result.lot_count == 7
    assert result.open_lots == 0
    assert result.cycle_time_hours > 20.0
    assert result.queue_time_hours > 1.0
    assert 0.0 < result.wip_lots <= result.peak_wip_lots
    assert result.throughput_wafers_per_week > 0.0
    assert all(
        0.0 <= value <= 1.0
        for value in result.tool_utilization.values()
    )
    assert all(
        0.0 <= value <= 1.0
        for value in result.tool_group_utilization.values()
    )
    assert result.route_rows > 0
    assert result.equipment_rows > 0


def test_cycle_time_traces_split_and_merge_ancestors():
    result = load_replay(MANIFEST)
    route = MANIFEST.parent / "mes_route_events.csv"
    with route.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    starts: dict[str, datetime] = {}
    completes: dict[str, datetime] = {}
    for row in rows:
        starts.setdefault(
            row["lot_id"],
            datetime.fromisoformat(row["event_time_utc"]),
        )
        if row["event_type"] == "lot_complete":
            completes[row["lot_id"]] = datetime.fromisoformat(
                row["event_time_utc"]
            )
    assert completes
    # Cycle from each finished lot's own creation event ignores the fab
    # ancestor that produced its wafers. The replay must be longer.
    own_segment = sum(
        (end - starts[lot]).total_seconds() / 3600.0
        for lot, end in completes.items()
    ) / len(completes)
    assert result.cycle_time_hours > own_segment


def test_fixture_is_byte_reproducible(tmp_path):
    dataset = generate_mes(seed=20261106, fab_lots=2, days=6)
    paths = dataset.write(tmp_path)
    for name, path in zip(
        (
            "mes_route_events.csv",
            "mes_equipment_events.csv",
            "manifest.json",
        ),
        paths,
    ):
        assert path.read_bytes() == (FIXTURE / name).read_bytes(), name


def test_replay_rejects_a_tampered_event_file(tmp_path):
    manifest = _copy_fixture(tmp_path)
    route = manifest.parent / "mes_route_events.csv"
    route.write_bytes(route.read_bytes() + b"\n")
    with pytest.raises(MesReplayError, match="byte count|SHA-256"):
        load_replay(manifest)


def test_synthetic_manifest_cannot_claim_measured(tmp_path):
    manifest = _copy_fixture(tmp_path)
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["evidence_class"] = "measured"
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(MesReplayError, match="synthetic"):
        load_replay(manifest)


def test_replay_scenario_runs_end_to_end(tmp_path):
    scenario = load_scenario(SCENARIO)
    assert validate_scenario(scenario) == []
    result = execute(scenario, tmp_path)
    observations = result.run_dir / "observations.csv"
    with observations.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    metrics = {row["metric"] for row in rows}
    assert {
        "cycle_time_s",
        "queue_time_s",
        "wip_lots",
        "throughput_wafers_per_s",
        "step_queue_time_s",
        "tool_utilization",
    } <= metrics
    assert {row["evidence_class"] for row in rows} == {"assumed"}
    manifest = json.loads(
        (result.run_dir / "run.json").read_text(encoding="utf-8")
    )
    assert manifest["scenario"]["mes"] == "factory/mes_smoke/manifest.json"
    assert manifest["engines"][0]["name"] == "factory_replay"
    assert "mes" in {row["role"] for row in manifest["inputs"]}
    cycle = next(row for row in rows if row["metric"] == "cycle_time_s")
    assert float(cycle["value"]) > 20.0 * 3600.0

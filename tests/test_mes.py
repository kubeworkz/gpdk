"""Tests for the deterministic synthetic MES generator."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from fabtwin.cli import main
from fabtwin.errors import MesError
from fabtwin.mes import (
    EQUIPMENT_COLUMNS,
    ROUTE_COLUMNS,
    TOOLS,
    check_dataset,
    generate,
)
from fabtwin.provenance import ROOT, sha256_file

TEMPLATES = ROOT / "catalog" / "templates"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _header(name: str) -> tuple[str, ...]:
    with (TEMPLATES / name).open(newline="", encoding="utf-8") as handle:
        return tuple(next(csv.reader(handle)))


def _schema(name: str) -> dict:
    return yaml.safe_load((TEMPLATES / name).read_text(encoding="utf-8"))


def _time(row: dict[str, str]) -> datetime:
    return datetime.fromisoformat(row["event_time_utc"])


def _by_lot(dataset) -> dict[str, list[dict[str, str]]]:
    lots: dict[str, list[dict[str, str]]] = {}
    for row in dataset.route_events:
        lots.setdefault(row["lot_id"], []).append(row)
    return lots


def test_headers_match_the_request_templates():
    assert ROUTE_COLUMNS == _header("mes_route_events.csv")
    assert EQUIPMENT_COLUMNS == _header("mes_equipment_events.csv")


@pytest.mark.parametrize(
    ("schema_name", "attribute"),
    (
        ("mes_route_events.schema.yaml", "route_events"),
        ("mes_equipment_events.schema.yaml", "equipment_events"),
    ),
)
def test_every_row_meets_the_declared_schema(schema_name, attribute):
    schema = _schema(schema_name)
    rows = getattr(generate(seed=5), attribute)
    allowed = {
        column["name"]: set(column.get("allowed_values", ()))
        for column in schema["columns"]
    }
    required = [
        column["name"]
        for column in schema["columns"]
        if column["required"]
    ]
    for row in rows:
        for name in required:
            assert row[name] != ""
        for name, values in allowed.items():
            if values and row[name]:
                assert row[name] in values, (name, row[name])


def test_generation_passes_its_own_contract_checks():
    dataset = generate(seed=5)
    assert check_dataset(dataset) == ()
    summary = dataset.summary()
    assert summary["route_events"] == len(dataset.route_events)
    assert summary["equipment_events"] == len(dataset.equipment_events)
    assert summary["tools"] == len(TOOLS)


def test_generation_is_deterministic():
    first = generate(seed=11)
    second = generate(seed=11)
    assert first.route_events == second.route_events
    assert first.equipment_events == second.equipment_events
    assert generate(seed=12).route_events != first.route_events


def test_split_and_merge_conserve_wafers_and_order():
    dataset = generate(seed=3)
    lots = _by_lot(dataset)
    splits = [
        row for row in dataset.route_events if row["event_type"] == "split"
    ]
    assert splits
    for row in splits:
        child = lots[row["lot_id"]]
        assert child[0]["event_type"] == "split"
        move_in = next(
            item for item in child if item["event_type"] == "move_in"
        )
        assert move_in["wafer_count"] == row["wafer_count"]
        parent = lots[row["parent_lot_id"]]
        assert _time(parent[-1]) <= _time(row)

    merges = [
        row for row in dataset.route_events if row["event_type"] == "merge"
    ]
    assert merges
    merged_ids = {row["lot_id"] for row in merges}
    assert len(merged_ids) == 1
    merged_id = merged_ids.pop()
    contributions = sum(int(row["wafer_count"]) for row in merges)
    move_in = next(
        row
        for row in lots[merged_id]
        if row["event_type"] == "move_in"
    )
    assert int(move_in["wafer_count"]) == contributions
    assert {row["parent_lot_id"] for row in merges} == {
        "LOT_FE_001_A",
        "LOT_FE_002_A",
    }


def test_scrap_reduces_following_quantities():
    dataset = generate(seed=3)
    scrap = [
        row for row in dataset.route_events if row["event_type"] == "scrap"
    ]
    assert len(scrap) == 1
    row = scrap[0]
    assert row["scrap_qty"] == "1"
    following = [
        item
        for item in dataset.route_events
        if item["lot_id"] == row["lot_id"]
        and _time(item) > _time(row)
    ]
    assert following
    assert all(
        int(item["wafer_count"]) == int(row["wafer_count"]) - 1
        for item in following
    )


def test_rework_hold_and_completion_events_are_present():
    event_types = {
        row["event_type"] for row in generate(seed=3).route_events
    }
    assert {
        "lot_start",
        "hold_start",
        "hold_end",
        "rework",
        "scrap",
        "split",
        "merge",
        "lot_complete",
    } <= event_types


def test_equipment_states_tile_each_tool_window():
    dataset = generate(seed=4)
    by_tool: dict[str, list[dict[str, str]]] = {}
    for row in dataset.equipment_events:
        by_tool.setdefault(row["tool_id"], []).append(row)
    assert set(by_tool) == {tool.tool_id for tool in TOOLS}
    for tool_id, rows in by_tool.items():
        assert _time(rows[0]) == dataset.window_start, tool_id
        times = [_time(row) for row in rows]
        assert times == sorted(times), tool_id
        assert len(set(times)) == len(times), tool_id
        assert all(time <= dataset.window_end for time in times), tool_id
        assert any(row["state"] == "productive" for row in rows), tool_id


def test_process_events_align_with_equipment_states():
    dataset = generate(seed=4)
    states = {
        (
            row["tool_id"],
            row["event_time_utc"],
            row["lot_id"],
            row["state"],
        )
        for row in dataset.equipment_events
    }
    for row in dataset.route_events:
        if row["event_type"] != "process_start":
            continue
        assert (
            row["tool_id"],
            row["event_time_utc"],
            row["lot_id"],
            "productive",
        ) in states


def test_write_produces_a_manifest_with_content_hashes(tmp_path):
    dataset = generate(seed=9, fab_lots=2, days=10)
    route, equipment, manifest = dataset.write(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["schema_version"] == "0.1"
    assert data["evidence_class"] == "assumed"
    assert data["synthetic"] is True
    assert data["measured"] is False
    files = {entry["path"]: entry for entry in data["files"]}
    assert files["mes_route_events.csv"]["sha256"] == sha256_file(route)
    assert files["mes_equipment_events.csv"]["sha256"] == (
        sha256_file(equipment)
    )
    assert files["mes_route_events.csv"]["rows"] == len(
        dataset.route_events
    )
    assert len(_rows(route)) == len(dataset.route_events)
    assert len(_rows(equipment)) == len(dataset.equipment_events)


def test_cli_writes_a_synthetic_window(tmp_path, capsys):
    code = main(
        [
            "mes-synth",
            "--out",
            str(tmp_path),
            "--seed",
            "7",
            "--lots",
            "2",
            "--days",
            "10",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "assumed" in output
    assert "not measured" in output
    assert (tmp_path / "manifest.json").is_file()


def test_invalid_options_are_rejected():
    with pytest.raises(MesError):
        generate(fab_lots=1)
    with pytest.raises(MesError):
        generate(days=0)

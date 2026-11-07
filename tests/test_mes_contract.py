"""Tests for the MES request templates and de-identification contract."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from fabtwin.provenance import ROOT

TEMPLATES = ROOT / "catalog" / "templates"
CASES = (
    ("mes_route_events.schema.yaml", "mes_route_events.csv"),
    ("mes_equipment_events.schema.yaml", "mes_equipment_events.csv"),
)
TYPES = {"string", "integer", "number", "datetime"}
DEIDENTIFICATION = {
    "generated",
    "tokenized",
    "generalized",
    "shifted",
    "preserved",
    "not_collected",
}
FORBIDDEN_HEADERS = {
    "operator_id",
    "employee_id",
    "customer_id",
    "customer_name",
    "comment",
    "comments",
    "notes",
    "address",
    "email",
    "phone",
}


def _schema(name: str) -> dict:
    return yaml.safe_load((TEMPLATES / name).read_text(encoding="utf-8"))


def _header(name: str) -> list[str]:
    with (TEMPLATES / name).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 1, f"{name} must be header-only"
    return rows[0]


@pytest.mark.parametrize(("schema_name", "csv_name"), CASES)
def test_template_header_matches_schema(schema_name, csv_name):
    schema = _schema(schema_name)
    header = _header(csv_name)
    columns = schema["columns"]
    names = [column["name"] for column in columns]

    assert schema["schema_version"] == "0.1"
    assert schema["format"] == "csv"
    assert schema["encoding"] == "utf-8"
    assert schema["timezone"] == "UTC"
    assert schema["primary_key"] == ["event_id"]
    assert schema["time_column"] == "event_time_utc"
    assert header == names
    assert len(set(names)) == len(names)
    assert not (set(header) & FORBIDDEN_HEADERS)

    for column in columns:
        assert column["type"] in TYPES
        assert isinstance(column["required"], bool)
        assert isinstance(column["nullable"], bool)
        assert column["pii"] is False
        assert column["deidentification"] in DEIDENTIFICATION
        if column["required"]:
            assert column["nullable"] is False
        if column["type"] in {"integer", "number"}:
            assert column["unit"]
        if column["type"] == "datetime":
            assert column["name"] == "event_time_utc"
        if "allowed_values" in column:
            assert column["allowed_values"]
            assert len(set(column["allowed_values"])) == len(
                column["allowed_values"]
            )


def test_route_contract_covers_required_event_and_operation_types():
    schema = _schema("mes_route_events.schema.yaml")
    columns = {column["name"]: column for column in schema["columns"]}
    assert {
        "lot_start",
        "move_in",
        "process_start",
        "process_end",
        "lot_complete",
    } <= set(columns["event_type"]["allowed_values"])
    assert {
        "lithography",
        "etch",
        "deposition",
        "metrology",
        "assembly",
        "final_test",
    } <= set(columns["operation_type"]["allowed_values"])
    assert columns["event_time_utc"]["type"] == "datetime"
    assert columns["process_time_s"]["unit"] == "s"


def test_route_contract_carries_split_and_merge_genealogy():
    schema = _schema("mes_route_events.schema.yaml")
    columns = {column["name"]: column for column in schema["columns"]}
    parent = columns["parent_lot_id"]
    assert parent["required"] is False
    assert parent["nullable"] is True
    assert parent["deidentification"] == "tokenized"


def test_equipment_contract_covers_semi_e10_like_states():
    schema = _schema("mes_equipment_events.schema.yaml")
    columns = {column["name"]: column for column in schema["columns"]}
    assert {
        "productive",
        "standby",
        "engineering",
        "scheduled_down",
        "unscheduled_down",
        "non_scheduled",
        "setup",
    } <= set(columns["state"]["allowed_values"])
    assert columns["event_time_utc"]["type"] == "datetime"
    assert columns["state"]["required"] is True
    assert columns["tool_id"]["deidentification"] == "tokenized"

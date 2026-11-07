"""Tests for the data-source catalog and dataset contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from fabtwin.catalog import load_catalog
from fabtwin.cli import main
from fabtwin.errors import CatalogError
from fabtwin.provenance import ROOT, sha256_file

CATALOG = ROOT / "catalog" / "gpdk.yaml"


def _payload(tmp_path: Path) -> tuple[Path, dict]:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    dataset = data / "mes.csv"
    dataset.write_text(
        "lot_id,cycle_time_h\nL1,10.5\nL2,11.0\n", encoding="utf-8"
    )
    payload = {
        "schema_version": "0.1",
        "data_root": "data",
        "sources": [
            {
                "id": "mes_routes",
                "name": "MES routes",
                "domain": "factory",
                "evidence_class": "measured",
                "status": "planned",
                "access": "local_file",
                "format": "csv",
                "owner": "unassigned",
                "license": "unassigned",
                "sensitivity": "confidential",
                "personal_data": "unverified",
                "refresh": "lot",
                "description": "Synthetic MES fixture for tests.",
            }
        ],
        "datasets": [
            {
                "id": "mes_route_fixture",
                "source": "mes_routes",
                "path": "mes.csv",
                "media_type": "text/csv",
                "sha256": sha256_file(dataset),
                "bytes": dataset.stat().st_size,
                "rows": 2,
                "collected_at": "2026-11-01T00:00:00Z",
                "evidence_class": "measured",
                "keys": ["lot_id"],
                "columns": [
                    {"name": "lot_id", "type": "string"},
                    {
                        "name": "cycle_time_h",
                        "type": "number",
                        "unit": "h",
                    },
                ],
                "description": "Two synthetic route rows.",
            }
        ],
    }
    return dataset, payload


def _write_catalog(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "catalog.yaml"
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    return path


def test_repository_catalog_loads_with_registered_measured_dataset():
    catalog = load_catalog(CATALOG)
    assert catalog.schema_version == "0.1"
    assert len(catalog.sources) == 15
    assert len(catalog.datasets) == 1
    assert catalog.summary()["sources"] == {
        "total": 15,
        "blocked": 0,
        "connected": 1,
        "planned": 14,
    }
    assert catalog.summary()["datasets"] == 1
    dataset = catalog.dataset("grx930_as_built_2026_11")
    assert dataset.source == "grx930_as_built"
    assert dataset.evidence_class == "measured"
    assert dataset.keys == ("chip",)
    assert len(dataset.columns) == 22
    checks = catalog.verify()
    assert len(checks) == 1
    assert checks[0].status == "ok"
    assert checks[0].actual_rows == 1


def test_dataset_contract_and_file_verify(tmp_path):
    _, payload = _payload(tmp_path)
    catalog = load_catalog(_write_catalog(tmp_path, payload))
    assert catalog.dataset("mes_route_fixture").keys == ("lot_id",)
    checks = catalog.verify()
    assert len(checks) == 1
    check = checks[0]
    assert check.status == "ok"
    assert check.actual_bytes == check.expected_bytes
    assert check.actual_sha256 == check.expected_sha256
    assert check.actual_rows == 2


def test_catalog_rejects_unknown_source_field(tmp_path):
    _, payload = _payload(tmp_path)
    payload["sources"][0]["url"] = "https://example.invalid"
    with pytest.raises(CatalogError, match="unknown field"):
        load_catalog(_write_catalog(tmp_path, payload))


def test_catalog_rejects_duplicate_source_and_dataset_ids(tmp_path):
    _, payload = _payload(tmp_path)
    payload["sources"].append(dict(payload["sources"][0]))
    with pytest.raises(CatalogError, match="source ids must be unique"):
        load_catalog(_write_catalog(tmp_path, payload))

    _, payload = _payload(tmp_path)
    payload["datasets"].append(dict(payload["datasets"][0]))
    with pytest.raises(CatalogError, match="dataset ids must be unique"):
        load_catalog(_write_catalog(tmp_path, payload))


def test_catalog_rejects_unknown_dataset_source(tmp_path):
    _, payload = _payload(tmp_path)
    payload["datasets"][0]["source"] = "missing_source"
    with pytest.raises(CatalogError, match="unknown source"):
        load_catalog(_write_catalog(tmp_path, payload))


def test_catalog_rejects_path_traversal(tmp_path):
    _, payload = _payload(tmp_path)
    payload["datasets"][0]["path"] = "../outside.csv"
    with pytest.raises(CatalogError, match="relative path without"):
        load_catalog(_write_catalog(tmp_path, payload))


def test_catalog_rejects_unkeyed_or_ununitized_numeric_columns(tmp_path):
    _, payload = _payload(tmp_path)
    payload["datasets"][0]["keys"] = []
    with pytest.raises(CatalogError, match="keys must be a non-empty list"):
        load_catalog(_write_catalog(tmp_path, payload))

    _, payload = _payload(tmp_path)
    payload["datasets"][0]["columns"][1].pop("unit")
    with pytest.raises(CatalogError, match="unit is required"):
        load_catalog(_write_catalog(tmp_path, payload))


def test_verify_detects_changed_bytes(tmp_path):
    dataset, payload = _payload(tmp_path)
    catalog = load_catalog(_write_catalog(tmp_path, payload))
    dataset.write_text(
        "lot_id,cycle_time_h\nL1,10.5\nL2,11.1\n", encoding="utf-8"
    )
    check = catalog.verify()[0]
    assert check.status == "hash_mismatch"
    assert check.actual_sha256 != check.expected_sha256


def test_verify_detects_csv_header_and_row_count_mismatches(tmp_path):
    dataset, payload = _payload(tmp_path)
    payload["datasets"][0]["columns"][1]["name"] = "cycle_h"
    path = _write_catalog(tmp_path, payload)
    catalog = load_catalog(path)
    check = catalog.verify()[0]
    assert check.status == "csv_header_mismatch"

    _, payload = _payload(tmp_path)
    dataset.write_text(
        "lot_id,cycle_time_h\nL1,10.5\nL2,11.0\nL3,9.5\n",
        encoding="utf-8",
    )
    payload["datasets"][0]["sha256"] = sha256_file(dataset)
    payload["datasets"][0]["bytes"] = dataset.stat().st_size
    catalog = load_catalog(_write_catalog(tmp_path, payload))
    check = catalog.verify()[0]
    assert check.status == "row_count_mismatch"
    assert check.actual_rows == 3


def test_catalog_cli_reports_success_and_failure(tmp_path, capsys):
    _, payload = _payload(tmp_path)
    path = _write_catalog(tmp_path, payload)
    status = main(["catalog", str(path), "--json"])
    assert status == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checked"] == 1
    assert result["ok"] == 1
    assert result["failed"] == 0
    assert result["checks"][0]["status"] == "ok"

    payload["sources"][0]["url"] = "https://example.invalid"
    path = _write_catalog(tmp_path, payload)
    status = main(["catalog", str(path)])
    assert status == 2
    captured = capsys.readouterr()
    assert "invalid catalog" in captured.err
    assert "unknown field" in captured.err

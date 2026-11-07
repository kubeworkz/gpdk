"""Tests for provider MES manifest ingestion and acceptance checks."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from fabtwin.cli import main
from fabtwin.errors import MesIngestError, MesReplayError
from fabtwin.mes_ingest import build_manifest
from fabtwin.mes_replay import load_replay
from fabtwin.provenance import ROOT, sha256_file
from fabtwin.run import execute, validate_scenario
from fabtwin.scenario import load_scenario

FIXTURE = ROOT / "factory" / "mes_smoke"
FILES = ("mes_route_events.csv", "mes_equipment_events.csv")


def _extract(tmp_path: Path) -> Path:
    target = tmp_path / "extract"
    target.mkdir(exist_ok=True)
    for name in FILES:
        shutil.copy2(FIXTURE / name, target / name)
    return target


def _args(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "evidence_class": "measured",
        "provider": "provider-a",
        "source_system": "mes-prod",
        "extract_id": "extract-001",
        "extract_time": "2026-11-06T12:00:00+00:00",
        "generator": "provider.export",
        "generator_version": "4.2",
    }
    values.update(overrides)
    return values


def test_measured_manifest_hashes_files_and_replays(tmp_path):
    extract = _extract(tmp_path)
    path, manifest = build_manifest(
        extract,
        window_start="2026-11-01T00:00:00+00:00",
        window_end="2026-11-07T00:00:00+00:00",
        **_args(),
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw == manifest
    assert manifest["evidence_class"] == "measured"
    assert manifest["synthetic"] is False
    assert manifest["measured"] is True
    assert manifest["window"] == {
        "start_utc": "2026-11-01T00:00:00+00:00",
        "end_utc": "2026-11-07T00:00:00+00:00",
    }
    files = {entry["path"]: entry for entry in manifest["files"]}
    assert set(files) == set(FILES)
    for name in FILES:
        entry = files[name]
        assert entry["bytes"] == (extract / name).stat().st_size
        assert entry["sha256"] == sha256_file(extract / name)
    assert files["mes_route_events.csv"]["rows"] == 180
    assert files["mes_route_events.csv"]["contract"].endswith(
        "mes_route_events.schema.yaml"
    )

    result = load_replay(path)
    assert result.evidence_class == "measured"
    assert result.synthetic is False
    assert result.completed_lots == 3
    assert result.completed_wafers == 50


def test_measured_manifest_requires_provenance(tmp_path):
    with pytest.raises(MesIngestError, match="--provider"):
        build_manifest(_extract(tmp_path), **_args(provider=None))
    with pytest.raises(MesIngestError, match="--extract-time"):
        build_manifest(_extract(tmp_path), **_args(extract_time=None))


def test_measured_manifest_requires_provenance_on_replay(tmp_path):
    extract = _extract(tmp_path)
    path, _manifest = build_manifest(extract, **_args())
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("provider")
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(MesReplayError, match="provider"):
        load_replay(path)


def test_measured_extract_replaces_fixture_in_a_scenario(tmp_path):
    extract = _extract(tmp_path)
    path, _manifest = build_manifest(
        extract,
        window_start="2026-11-01T00:00:00+00:00",
        window_end="2026-11-07T00:00:00+00:00",
        **_args(),
    )
    scenario_path = tmp_path / "mes_line_measured.yaml"
    scenario_path.write_text(
        f"""schema_version: "0.1"
id: mes_line_measured
description: Accepted measured MES replay.
product: mes_line_measured
process: mes_measured@0.1.0
seed: 1
samples: 1
engines:
  - factory_replay
inputs:
  chip: chips/g100.yaml
  mes: "{path.as_posix()}"
outputs:
  - cycle_time_s
  - queue_time_s
  - wip_lots
  - completed_wafers
""",
        encoding="utf-8",
    )
    scenario = load_scenario(scenario_path)
    assert validate_scenario(scenario) == []
    result = execute(scenario, tmp_path / "out")
    assert result.observation_count == 4
    with (result.run_dir / "observations.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert {row["evidence_class"] for row in rows} == {"measured"}
    values = {row["metric"]: float(row["value"]) for row in rows}
    assert values["completed_wafers"] == 50.0
    assert values["cycle_time_s"] > 20.0 * 3600.0


def test_manifest_template_is_valid_json():
    template = json.loads(
        (ROOT / "catalog" / "templates" / "mes_manifest.template.json")
        .read_text(encoding="utf-8")
    )
    assert template["schema_version"] == "0.1"
    assert template["evidence_class"] == "measured"
    assert template["measured"] is True
    assert len(template["files"]) == 2


def test_manifest_refuses_to_overwrite_without_force(tmp_path):
    extract = _extract(tmp_path)
    build_manifest(extract, **_args())
    with pytest.raises(MesIngestError, match="already exists"):
        build_manifest(extract, **_args())
    path, _manifest = build_manifest(
        extract, **_args(), overwrite=True
    )
    assert path.is_file()


def test_manifest_rejects_a_header_mismatch(tmp_path):
    extract = _extract(tmp_path)
    route = extract / "mes_route_events.csv"
    text = route.read_text(encoding="utf-8")
    route.write_text(
        text.replace("event_id,event_type", "event_id,event_kind", 1),
        encoding="utf-8",
    )
    with pytest.raises(MesIngestError, match="header"):
        build_manifest(extract, **_args())


def test_manifest_rejects_duplicate_event_ids(tmp_path):
    extract = _extract(tmp_path)
    route = extract / "mes_route_events.csv"
    with route.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[1]["event_id"] = rows[0]["event_id"]
    with route.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(MesIngestError, match="duplicate event_id"):
        build_manifest(extract, **_args())


def test_manifest_rejects_a_window_that_clips_events(tmp_path):
    with pytest.raises(MesIngestError, match="outside"):
        build_manifest(
            _extract(tmp_path),
            window_start="2026-11-02T00:00:00+00:00",
            **_args(),
        )


def test_cli_manifests_and_checks_an_extract(tmp_path, capsys):
    extract = _extract(tmp_path)
    code = main(
        [
            "mes-manifest",
            str(extract),
            "--provider",
            "provider-a",
            "--source-system",
            "mes-prod",
            "--extract-id",
            "extract-001",
            "--extract-time",
            "2026-11-06T12:00:00+00:00",
            "--generator",
            "provider.export",
            "--generator-version",
            "4.2",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "measured" in output
    assert "next: python -m fabtwin mes-check" in output

    code = main(
        ["mes-check", str(extract / "manifest.json"), "--json"]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["evidence_class"] == "measured"
    assert payload["synthetic"] is False
    assert payload["completed_lots"] == 3
    assert payload["route"]["rows"] == 180

    report_path = extract / "acceptance.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "0.1"
    assert report["status"] == "ok"
    assert report["manifest"]["provider"] == "provider-a"
    assert report["manifest_sha256"] == payload["manifest_sha256"]
    assert report["manifest_path"] == "manifest.json"
    assert report["checks"] and all(
        check["status"] == "ok" for check in report["checks"]
    )
    assert report["metrics"]["completed_wafers"] == 50
    assert Path(payload["acceptance_report"]) == report_path


def test_mes_check_can_skip_the_report(tmp_path):
    extract = _extract(tmp_path)
    build_manifest(extract, **_args())
    code = main(
        ["mes-check", str(extract / "manifest.json"), "--no-report"]
    )
    assert code == 0
    assert not (extract / "acceptance.json").exists()


def test_mes_check_writes_a_custom_acceptance_report(tmp_path, capsys):
    extract = _extract(tmp_path)
    build_manifest(extract, **_args())
    target = tmp_path / "reports" / "acceptance.json"
    code = main(
        [
            "mes-check",
            str(extract / "manifest.json"),
            "--report",
            str(target),
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["acceptance_report"]) == target
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["status"] == "ok"
    assert report["manifest_path"].endswith("manifest.json")


def test_acceptance_report_cannot_overwrite_the_manifest(tmp_path):
    extract = _extract(tmp_path)
    build_manifest(extract, **_args())
    manifest = extract / "manifest.json"
    code = main(
        [
            "mes-check",
            str(manifest),
            "--report",
            str(manifest),
        ]
    )
    assert code == 2
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "0.1"


def test_mes_check_rejects_a_changed_event_file(tmp_path, capsys):
    extract = _extract(tmp_path)
    build_manifest(extract, **_args())
    route = extract / "mes_route_events.csv"
    route.write_bytes(route.read_bytes() + b"\n")
    code = main(["mes-check", str(extract / "manifest.json")])
    assert code == 1
    error = capsys.readouterr().err
    assert "byte count" in error or "SHA-256" in error

    report = json.loads(
        (extract / "acceptance.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "failed"
    assert report["metrics"] is None
    assert report["checks"][0]["status"] == "failed"
    assert report["error"]
    assert "byte count" in report["error"] or "SHA-256" in report["error"]

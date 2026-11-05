"""SQLite index for runs and observations.

The SQLite database is a query index, not a replacement for the per-run
artifacts. The CSV, report, and manifest stay on disk and are referenced by
their SHA-256 hashes. The store makes cross-run queries cheap without changing
the engine contract: engines still return ``EngineResult`` values.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .errors import StoreError

STORE_SCHEMA_VERSION = "1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    scenario_path TEXT NOT NULL,
    scenario_sha256 TEXT NOT NULL,
    product TEXT NOT NULL,
    process TEXT NOT NULL,
    seed INTEGER NOT NULL,
    samples INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL,
    run_dir TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    report_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    uncertainty REAL,
    evidence_class TEXT NOT NULL CHECK (
        evidence_class IN ('measured', 'vendor', 'literature', 'proxy', 'assumed')
    ),
    source_artifact TEXT NOT NULL,
    model_version TEXT NOT NULL,
    UNIQUE (run_id, entity_type, entity_id, metric, model_version)
);

CREATE INDEX IF NOT EXISTS idx_observations_run
    ON observations(run_id);
CREATE INDEX IF NOT EXISTS idx_observations_metric
    ON observations(metric);
CREATE INDEX IF NOT EXISTS idx_observations_entity
    ON observations(entity_id);
CREATE INDEX IF NOT EXISTS idx_observations_evidence
    ON observations(evidence_class);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    UNIQUE (run_id, path)
);

CREATE TABLE IF NOT EXISTS inputs (
    input_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    UNIQUE (run_id, role, path)
);

CREATE TABLE IF NOT EXISTS engines (
    engine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    fidelity TEXT NOT NULL,
    model_version TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE (run_id, name)
);
"""


class ObservationStore:
    """A small, transaction-safe SQLite index for completed runs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create the schema if needed; safe to call before every operation."""
        try:
            with self._connect() as connection:
                connection.executescript(_SCHEMA)
        except sqlite3.Error as exc:
            raise StoreError(f"cannot initialize {self.path}: {exc}") from exc

    def record_run(
        self,
        manifest: Mapping[str, Any],
        observation_rows: Sequence[Mapping[str, str]],
    ) -> None:
        """Insert one completed run and all of its observations atomically."""
        scenario = manifest["scenario"]
        run_id = str(manifest["run_id"])
        observation_values = [
            (
                row["observation_id"],
                run_id,
                row["entity_type"],
                row["entity_id"],
                row["metric"],
                float(row["value"]),
                row["unit"],
                None if row["uncertainty"] == "" else float(row["uncertainty"]),
                row["evidence_class"],
                row["source_artifact"],
                row["model_version"],
            )
            for row in observation_rows
        ]
        artifact_values = [
            (
                run_id,
                artifact["path"],
                artifact["media_type"],
                int(artifact["bytes"]),
                artifact["sha256"],
            )
            for artifact in manifest.get("artifacts", [])
        ]
        input_values = [
            (
                run_id,
                item["role"],
                item["path"],
                item["sha256"],
                int(item["bytes"]),
            )
            for item in manifest.get("inputs", [])
        ]
        engine_values = [
            (
                run_id,
                engine["name"],
                engine["version"],
                engine["fidelity"],
                engine["model_version"],
                json.dumps(
                    engine.get("metadata", {}),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            for engine in manifest.get("engines", [])
        ]

        try:
            self.initialize()
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, schema_version, scenario_id, scenario_path,
                        scenario_sha256, product, process, seed, samples,
                        started_at, finished_at, status, run_dir,
                        manifest_path, report_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        manifest["schema_version"],
                        scenario["id"],
                        scenario["path"],
                        scenario["sha256"],
                        scenario["product"],
                        scenario["process"],
                        int(scenario["seed"]),
                        int(scenario["samples"]),
                        manifest["started_at"],
                        manifest["finished_at"],
                        manifest["status"],
                        manifest["run_dir"],
                        manifest["manifest_path"],
                        manifest["report_path"],
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO observations (
                        observation_id, run_id, entity_type, entity_id, metric,
                        value, unit, uncertainty, evidence_class,
                        source_artifact, model_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    observation_values,
                )
                connection.executemany(
                    """
                    INSERT INTO artifacts (
                        run_id, path, media_type, bytes, sha256
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    artifact_values,
                )
                connection.executemany(
                    """
                    INSERT INTO inputs (
                        run_id, role, path, sha256, bytes
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    input_values,
                )
                connection.executemany(
                    """
                    INSERT INTO engines (
                        run_id, name, version, fidelity, model_version,
                        metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    engine_values,
                )
        except sqlite3.IntegrityError as exc:
            raise StoreError(
                f"run {run_id!r} is already indexed or conflicts with an "
                f"existing row: {exc}"
            ) from exc
        except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
            raise StoreError(f"cannot index run {run_id!r}: {exc}") from exc

    def query_observations(
        self,
        *,
        run_id: str | None = None,
        metric: str | None = None,
        entity_id: str | None = None,
        evidence_class: str | None = None,
        product: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return observations joined to their run metadata, newest first."""
        limit = _checked_limit(limit)
        clauses: list[str] = []
        parameters: list[Any] = []
        for column, value in (
            ("o.run_id", run_id),
            ("o.metric", metric),
            ("o.entity_id", entity_id),
            ("o.evidence_class", evidence_class),
            ("r.product", product),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        where = " AND ".join(clauses) if clauses else "1 = 1"
        query = f"""
            SELECT
                o.observation_id, o.run_id, r.scenario_id, r.product,
                o.entity_type, o.entity_id, o.metric, o.value, o.unit,
                o.uncertainty, o.evidence_class, o.source_artifact,
                o.model_version, r.started_at, r.status
            FROM observations AS o
            JOIN runs AS r ON r.run_id = o.run_id
            WHERE {where}
            ORDER BY r.started_at DESC, o.rowid ASC
            LIMIT ?
        """
        parameters.append(limit)
        try:
            self.initialize()
            with self._connect() as connection:
                return [
                    dict(row)
                    for row in connection.execute(query, parameters)
                ]
        except sqlite3.Error as exc:
            raise StoreError(f"cannot query {self.path}: {exc}") from exc

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Return one run's metadata or raise a clear store error."""
        try:
            self.initialize()
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise StoreError(f"cannot read run {run_id!r}: {exc}") from exc
        if row is None:
            raise StoreError(f"run {run_id!r} not found in {self.path}")
        return dict(row)

    def _run_observations(
        self, run_id: str, metric: str | None = None
    ) -> dict[tuple[str, str, str], dict[str, Any]]:
        clauses = ["run_id = ?"]
        parameters: list[Any] = [run_id]
        if metric is not None:
            clauses.append("metric = ?")
            parameters.append(metric)
        query = f"""
            SELECT
                observation_id, entity_type, entity_id, metric, value, unit,
                uncertainty, evidence_class, source_artifact, model_version
            FROM observations
            WHERE {' AND '.join(clauses)}
            ORDER BY entity_id, metric, entity_type
        """
        try:
            self.initialize()
            with self._connect() as connection:
                source_rows = [
                    dict(row)
                    for row in connection.execute(query, parameters)
                ]
        except sqlite3.Error as exc:
            raise StoreError(f"cannot read observations for {run_id!r}: {exc}") from exc

        observations: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in source_rows:
            key = (row["entity_type"], row["entity_id"], row["metric"])
            if key in observations:
                raise StoreError(
                    f"run {run_id!r} has multiple observations for "
                    f"{key[1]}/{key[2]}; comparison requires one model per metric"
                )
            observations[key] = row
        return observations

    def compare_runs(
        self,
        run_a: str,
        run_b: str,
        *,
        metric: str | None = None,
        only_changes: bool = False,
    ) -> dict[str, Any]:
        """Diff two indexed runs by entity and metric.

        Values are compared in their stored units. A change in unit, model
        version, or evidence class is flagged even when the numeric value is
        unchanged.
        """
        meta_a = self.get_run(run_a)
        meta_b = self.get_run(run_b)
        observations_a = self._run_observations(run_a, metric)
        observations_b = self._run_observations(run_b, metric)
        keys = sorted(
            set(observations_a) | set(observations_b),
            key=lambda key: (key[1], key[2], key[0]),
        )
        rows = [
            _comparison_row(key, observations_a.get(key), observations_b.get(key))
            for key in keys
        ]
        matched_rows = len(rows)
        if only_changes:
            rows = [row for row in rows if row["flags"]]
        summary = {
            "rows": len(rows),
            "changed": sum(1 for row in rows if row["flags"]),
            "unchanged": sum(1 for row in rows if not row["flags"]),
            "added": sum(1 for row in rows if "added" in row["flags"]),
            "removed": sum(1 for row in rows if "removed" in row["flags"]),
            "value_changes": sum(
                1 for row in rows if "value" in row["flags"]
            ),
            "evidence_changes": sum(
                1 for row in rows if "evidence" in row["flags"]
            ),
            "unit_changes": sum(1 for row in rows if "unit" in row["flags"]),
            "model_changes": sum(
                1 for row in rows if "model" in row["flags"]
            ),
        }
        return {
            "run_a": meta_a,
            "run_b": meta_b,
            "summary": summary,
            "filter": {
                "only_changes": only_changes,
                "matched_rows": matched_rows,
                "shown_rows": len(rows),
            },
            "rows": rows,
        }

    def list_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent runs with their observation counts."""
        limit = _checked_limit(limit)
        query = """
            SELECT
                r.run_id, r.scenario_id, r.product, r.process, r.status,
                r.started_at, r.finished_at, COUNT(o.observation_id)
                    AS observation_count
            FROM runs AS r
            LEFT JOIN observations AS o ON o.run_id = r.run_id
            GROUP BY r.run_id
            ORDER BY r.started_at DESC, r.run_id DESC
            LIMIT ?
        """
        try:
            self.initialize()
            with self._connect() as connection:
                return [
                    dict(row)
                    for row in connection.execute(query, (limit,))
                ]
        except sqlite3.Error as exc:
            raise StoreError(f"cannot list runs in {self.path}: {exc}") from exc


def _comparison_row(
    key: tuple[str, str, str],
    a: dict[str, Any] | None,
    b: dict[str, Any] | None,
) -> dict[str, Any]:
    entity_type, entity_id, metric = key
    flags: list[str] = []
    delta: float | None = None
    delta_pct: float | None = None

    if a is None and b is not None:
        flags.append("added")
    elif a is not None and b is None:
        flags.append("removed")
    elif a is not None and b is not None:
        if a["unit"] != b["unit"]:
            flags.append("unit")
        else:
            delta = float(b["value"]) - float(a["value"])
            if delta != 0.0:
                flags.append("value")
            if float(a["value"]) != 0.0:
                delta_pct = delta / abs(float(a["value"])) * 100.0
        if a["model_version"] != b["model_version"]:
            flags.append("model")
        if a["evidence_class"] != b["evidence_class"]:
            flags.append("evidence")

    evidence_changed = bool(
        a is not None
        and b is not None
        and a["evidence_class"] != b["evidence_class"]
    )
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "metric": metric,
        "value_a": None if a is None else float(a["value"]),
        "value_b": None if b is None else float(b["value"]),
        "unit_a": None if a is None else a["unit"],
        "unit_b": None if b is None else b["unit"],
        "delta": delta,
        "delta_pct": delta_pct,
        "evidence_a": None if a is None else a["evidence_class"],
        "evidence_b": None if b is None else b["evidence_class"],
        "evidence_changed": evidence_changed,
        "model_a": None if a is None else a["model_version"],
        "model_b": None if b is None else b["model_version"],
        "model_changed": bool(
            a is not None
            and b is not None
            and a["model_version"] != b["model_version"]
        ),
        "unit_changed": bool(
            a is not None and b is not None and a["unit"] != b["unit"]
        ),
        "value_changed": "value" in flags,
        "flags": flags,
        "change": (
            "added"
            if a is None and b is not None
            else "removed"
            if a is not None and b is None
            else "changed"
            if flags
            else "unchanged"
        ),
    }


def _checked_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StoreError("query limit must be an integer")
    if not 1 <= value <= 1000:
        raise StoreError("query limit must be in [1, 1000]")
    return value

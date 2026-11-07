"""Strict catalog for foundry data sources and measured datasets.

The catalog is metadata-only. It records where a source comes from, how it may
be used, and the contract for each registered dataset without copying raw data
into the evidence store. Dataset files are content-addressed by SHA-256 and may
be verified without modifying them.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml

from .errors import CatalogError
from .model import EVIDENCE_CLASSES
from .provenance import display_path, sha256_file

SCHEMA_VERSION = "0.1"
_CATALOG_FIELDS = frozenset(
    {"schema_version", "data_root", "sources", "datasets"}
)
_SOURCE_FIELDS = frozenset(
    {
        "id",
        "name",
        "domain",
        "evidence_class",
        "status",
        "access",
        "format",
        "owner",
        "license",
        "sensitivity",
        "personal_data",
        "refresh",
        "description",
    }
)
_DATASET_FIELDS = frozenset(
    {
        "id",
        "source",
        "path",
        "media_type",
        "sha256",
        "bytes",
        "rows",
        "collected_at",
        "evidence_class",
        "columns",
        "keys",
        "time_column",
        "description",
    }
)
_COLUMN_FIELDS = frozenset(
    {"name", "type", "unit", "nullable", "description"}
)
_DOMAINS = frozenset(
    {
        "process",
        "metrology",
        "equipment",
        "factory",
        "test",
        "package",
        "design",
        "simulation",
        "commercial",
        "external",
    }
)
_SOURCE_STATUSES = frozenset({"connected", "planned", "blocked"})
_ACCESS_MODES = frozenset({"local_file", "database", "api", "manual"})
_REFRESH_MODES = frozenset(
    {"static", "lot", "wafer", "daily", "weekly", "monthly", "per_run", "unknown"}
)
_SENSITIVITIES = frozenset(
    {"public", "internal", "confidential", "restricted"}
)
_PERSONAL_DATA = frozenset({"present", "absent", "unverified"})
_COLUMN_TYPES = frozenset(
    {"string", "integer", "number", "boolean", "datetime"}
)
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_FORMAT_RE = re.compile(r"^[a-z][a-z0-9_.+-]*$")
_MEDIA_TYPE_RE = re.compile(r"^[a-z][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CatalogSource:
    """A data source and its access/evidence contract."""

    id: str
    name: str
    domain: str
    evidence_class: str
    status: str
    access: str
    format: str
    owner: str
    license: str
    sensitivity: str
    personal_data: str
    refresh: str
    description: str


@dataclass(frozen=True)
class ColumnContract:
    """One column in a registered dataset."""

    name: str
    type: str
    unit: str | None
    nullable: bool
    description: str


@dataclass(frozen=True)
class DatasetContract:
    """A content-addressed dataset and its expected schema."""

    id: str
    source: str
    path: str
    media_type: str
    sha256: str
    bytes: int
    rows: int
    collected_at: str
    evidence_class: str
    columns: tuple[ColumnContract, ...]
    keys: tuple[str, ...]
    time_column: str | None
    description: str


@dataclass(frozen=True)
class DatasetCheck:
    """Result of verifying one registered dataset file."""

    dataset_id: str
    source: str
    path: str
    status: str
    expected_sha256: str
    actual_sha256: str | None
    expected_bytes: int
    actual_bytes: int | None
    expected_rows: int
    actual_rows: int | None
    error: str | None


@dataclass(frozen=True)
class Catalog:
    """A validated source registry plus zero or more dataset contracts."""

    path: Path
    sha256: str
    schema_version: str
    data_root: Path
    sources: tuple[CatalogSource, ...]
    datasets: tuple[DatasetContract, ...]

    def source(self, source_id: str) -> CatalogSource:
        for source in self.sources:
            if source.id == source_id:
                return source
        raise KeyError(source_id)

    def dataset(self, dataset_id: str) -> DatasetContract:
        for dataset in self.datasets:
            if dataset.id == dataset_id:
                return dataset
        raise KeyError(dataset_id)

    def verify(self) -> tuple[DatasetCheck, ...]:
        """Verify every registered dataset without changing any file."""
        return tuple(
            _verify_dataset(self.data_root, dataset)
            for dataset in self.datasets
        )

    def summary(self) -> dict[str, Any]:
        statuses = {
            status: sum(
                1 for source in self.sources if source.status == status
            )
            for status in sorted(_SOURCE_STATUSES)
        }
        return {
            "catalog": display_path(self.path),
            "sha256": self.sha256,
            "schema_version": self.schema_version,
            "data_root": display_path(self.data_root),
            "sources": {"total": len(self.sources), **statuses},
            "datasets": len(self.datasets),
        }


def _unknown_fields(
    raw: Mapping[str, Any], allowed: frozenset[str], label: str
) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(
            f"{label} has unknown field(s): " + ", ".join(unknown)
        )


def _text(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def _optional_text(
    raw: Mapping[str, Any], key: str, label: str
) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def _enum(
    raw: Mapping[str, Any],
    key: str,
    label: str,
    allowed: frozenset[str],
) -> str:
    value = _text(raw, key, label)
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{label}.{key} must be one of: {choices}")
    return value


def _identifier(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = _text(raw, key, label)
    if not _ID_RE.fullmatch(value):
        raise ValueError(
            f"{label}.{key} must match {_ID_RE.pattern!r}"
        )
    return value


def _integer(raw: Mapping[str, Any], key: str, label: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label}.{key} must be a non-negative integer")
    return value


def _boolean(
    raw: Mapping[str, Any], key: str, label: str, default: bool
) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be a boolean")
    return value


def _relative_path(value: str, label: str, *, allow_dot: bool) -> str:
    if "\\" in value:
        raise ValueError(f"{label} must use forward slashes")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be a relative path without '..'")
    if path.as_posix() == ".":
        if allow_dot:
            return "."
        raise ValueError(f"{label} must not be empty")
    if not path.parts:
        raise ValueError(f"{label} must not be empty")
    return path.as_posix()


def _timestamp(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = raw.get(key)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError(
                f"{label}.{key} must be ISO 8601"
            ) from exc
    else:
        raise ValueError(f"{label}.{key} must be an ISO 8601 timestamp")
    if parsed.tzinfo is None:
        raise ValueError(f"{label}.{key} must include a timezone")
    return parsed.isoformat()


def _source_from_mapping(raw: Any, index: int) -> CatalogSource:
    label = f"source[{index}]"
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a mapping")
    _unknown_fields(raw, _SOURCE_FIELDS, label)
    source_format = _text(raw, "format", label)
    if not _FORMAT_RE.fullmatch(source_format):
        raise ValueError(f"{label}.format is not a valid format name")
    return CatalogSource(
        id=_identifier(raw, "id", label),
        name=_text(raw, "name", label),
        domain=_enum(raw, "domain", label, _DOMAINS),
        evidence_class=_enum(
            raw, "evidence_class", label, EVIDENCE_CLASSES
        ),
        status=_enum(raw, "status", label, _SOURCE_STATUSES),
        access=_enum(raw, "access", label, _ACCESS_MODES),
        format=source_format,
        owner=_text(raw, "owner", label),
        license=_text(raw, "license", label),
        sensitivity=_enum(
            raw, "sensitivity", label, _SENSITIVITIES
        ),
        personal_data=_enum(
            raw, "personal_data", label, _PERSONAL_DATA
        ),
        refresh=_enum(raw, "refresh", label, _REFRESH_MODES),
        description=_text(raw, "description", label),
    )


def _column_from_mapping(raw: Any, index: int) -> ColumnContract:
    label = f"column[{index}]"
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a mapping")
    _unknown_fields(raw, _COLUMN_FIELDS, label)
    name = _text(raw, "name", label)
    if any(character in name for character in "\r\n,"):
        raise ValueError(f"{label}.name must not contain commas or newlines")
    column_type = _enum(raw, "type", label, _COLUMN_TYPES)
    unit = _optional_text(raw, "unit", label)
    if column_type in {"integer", "number"} and unit is None:
        raise ValueError(f"{label}.unit is required for numeric columns")
    return ColumnContract(
        name=name,
        type=column_type,
        unit=unit,
        nullable=_boolean(raw, "nullable", label, False),
        description=_optional_text(raw, "description", label) or "",
    )


def _dataset_from_mapping(raw: Any, index: int) -> DatasetContract:
    label = f"dataset[{index}]"
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a mapping")
    _unknown_fields(raw, _DATASET_FIELDS, label)
    dataset_id = _identifier(raw, "id", label)
    source = _identifier(raw, "source", label)
    path = _relative_path(
        _text(raw, "path", label), f"{label}.path", allow_dot=False
    )
    media_type = _text(raw, "media_type", label)
    if not _MEDIA_TYPE_RE.fullmatch(media_type):
        raise ValueError(f"{label}.media_type is not a valid media type")
    digest = _text(raw, "sha256", label)
    if not _SHA256_RE.fullmatch(digest):
        raise ValueError(f"{label}.sha256 must be 64 lowercase hex digits")
    raw_columns = raw.get("columns")
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ValueError(f"{label}.columns must be a non-empty list")
    columns = tuple(
        _column_from_mapping(column, column_index)
        for column_index, column in enumerate(raw_columns)
    )
    names = [column.name for column in columns]
    if len(set(names)) != len(names):
        raise ValueError(f"{label}.columns must have unique names")
    raw_keys = raw.get("keys")
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ValueError(f"{label}.keys must be a non-empty list")
    if not all(isinstance(key, str) and key.strip() for key in raw_keys):
        raise ValueError(f"{label}.keys must contain non-empty strings")
    keys = tuple(key.strip() for key in raw_keys)
    if len(set(keys)) != len(keys):
        raise ValueError(f"{label}.keys must be unique")
    unknown_keys = sorted(set(keys) - set(names))
    if unknown_keys:
        raise ValueError(
            f"{label}.keys reference unknown columns: "
            + ", ".join(unknown_keys)
        )
    time_column = _optional_text(raw, "time_column", label)
    if time_column is not None:
        matching = {column.name: column for column in columns}
        if time_column not in matching:
            raise ValueError(
                f"{label}.time_column references an unknown column"
            )
        if matching[time_column].type != "datetime":
            raise ValueError(f"{label}.time_column must be a datetime column")
    return DatasetContract(
        id=dataset_id,
        source=source,
        path=path,
        media_type=media_type,
        sha256=digest,
        bytes=_integer(raw, "bytes", label),
        rows=_integer(raw, "rows", label),
        collected_at=_timestamp(raw, "collected_at", label),
        evidence_class=_enum(
            raw, "evidence_class", label, EVIDENCE_CLASSES
        ),
        columns=columns,
        keys=keys,
        time_column=time_column,
        description=_text(raw, "description", label),
    )


def _resolve_data_root(
    raw: Mapping[str, Any], catalog_path: Path
) -> Path:
    value = _relative_path(
        _text(raw, "data_root", "catalog"),
        "catalog.data_root",
        allow_dot=True,
    )
    return (catalog_path.parent / value).resolve()


def load_catalog(path: str | Path) -> Catalog:
    """Load and strictly validate a catalog, then return its contracts.

    File contents are not verified here; call ``Catalog.verify()`` for hashes,
    sizes, row counts and CSV headers. This keeps metadata validation fast and
    usable before a planned dataset exists.
    """
    catalog_path = Path(path)
    if not catalog_path.is_absolute():
        catalog_path = Path.cwd() / catalog_path
    catalog_path = catalog_path.resolve()
    if not catalog_path.is_file():
        raise CatalogError(
            [f"{display_path(catalog_path)}: catalog file not found"]
        )
    try:
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CatalogError(
            [f"{display_path(catalog_path)}: cannot read catalog: {exc}"]
        ) from exc
    if not isinstance(raw, Mapping):
        raise CatalogError(
            [f"{display_path(catalog_path)}: catalog must be a mapping"]
        )

    errors: list[str] = []
    try:
        _unknown_fields(raw, _CATALOG_FIELDS, "catalog")
    except ValueError as exc:
        errors.append(str(exc))
    schema_version = raw.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        errors.append(
            f"catalog.schema_version must be {SCHEMA_VERSION!r}, "
            f"got {schema_version!r}"
        )
    try:
        data_root = _resolve_data_root(raw, catalog_path)
    except ValueError as exc:
        errors.append(str(exc))
        data_root = catalog_path.parent
    if data_root.exists() and not data_root.is_dir():
        errors.append(
            f"catalog.data_root is not a directory: {display_path(data_root)}"
        )

    source_values = raw.get("sources")
    sources: list[CatalogSource] = []
    if not isinstance(source_values, list) or not source_values:
        errors.append("catalog.sources must be a non-empty list")
    else:
        for index, value in enumerate(source_values):
            try:
                sources.append(_source_from_mapping(value, index))
            except ValueError as exc:
                errors.append(str(exc))
    source_ids = [source.id for source in sources]
    if len(set(source_ids)) != len(source_ids):
        errors.append("catalog source ids must be unique")

    dataset_values = raw.get("datasets")
    datasets: list[DatasetContract] = []
    if not isinstance(dataset_values, list):
        errors.append("catalog.datasets must be a list")
    else:
        for index, value in enumerate(dataset_values):
            try:
                datasets.append(_dataset_from_mapping(value, index))
            except ValueError as exc:
                errors.append(str(exc))
    dataset_ids = [dataset.id for dataset in datasets]
    if len(set(dataset_ids)) != len(dataset_ids):
        errors.append("catalog dataset ids must be unique")
    known_sources = set(source_ids)
    for dataset in datasets:
        if dataset.source not in known_sources:
            errors.append(
                f"dataset {dataset.id!r} references unknown source "
                f"{dataset.source!r}"
            )

    if errors:
        raise CatalogError(
            [f"{display_path(catalog_path)}: {error}" for error in errors]
        )
    return Catalog(
        path=catalog_path,
        sha256=sha256_file(catalog_path),
        schema_version=SCHEMA_VERSION,
        data_root=data_root,
        sources=tuple(sources),
        datasets=tuple(datasets),
    )


def _check(
    dataset: DatasetContract,
    path: Path,
    status: str,
    *,
    actual_sha256: str | None = None,
    actual_bytes: int | None = None,
    actual_rows: int | None = None,
    error: str | None = None,
) -> DatasetCheck:
    return DatasetCheck(
        dataset_id=dataset.id,
        source=dataset.source,
        path=display_path(path),
        status=status,
        expected_sha256=dataset.sha256,
        actual_sha256=actual_sha256,
        expected_bytes=dataset.bytes,
        actual_bytes=actual_bytes,
        expected_rows=dataset.rows,
        actual_rows=actual_rows,
        error=error,
    )


def _verify_dataset(
    data_root: Path, dataset: DatasetContract
) -> DatasetCheck:
    path = data_root.joinpath(*PurePosixPath(dataset.path).parts)
    if path.is_symlink():
        return _check(
            dataset,
            path,
            "unreadable",
            error="dataset path must not be a symbolic link",
        )
    if not path.exists():
        return _check(dataset, path, "missing")
    if not path.is_file():
        return _check(dataset, path, "not_file")

    try:
        actual_bytes = path.stat().st_size
    except OSError as exc:
        return _check(
            dataset, path, "unreadable", error=str(exc)
        )

    try:
        actual_sha256 = sha256_file(path)
    except OSError as exc:
        return _check(
            dataset,
            path,
            "unreadable",
            actual_bytes=actual_bytes,
            error=str(exc),
        )

    size_mismatch = actual_bytes != dataset.bytes
    hash_mismatch = actual_sha256 != dataset.sha256
    if size_mismatch and hash_mismatch:
        return _check(
            dataset,
            path,
            "size_and_hash_mismatch",
            actual_sha256=actual_sha256,
            actual_bytes=actual_bytes,
        )
    if size_mismatch:
        return _check(
            dataset,
            path,
            "size_mismatch",
            actual_sha256=actual_sha256,
            actual_bytes=actual_bytes,
        )
    if hash_mismatch:
        return _check(
            dataset,
            path,
            "hash_mismatch",
            actual_sha256=actual_sha256,
            actual_bytes=actual_bytes,
        )

    if dataset.media_type != "text/csv" and path.suffix.lower() != ".csv":
        return _check(
            dataset,
            path,
            "ok",
            actual_sha256=actual_sha256,
            actual_bytes=actual_bytes,
        )

    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            actual_rows = sum(1 for row in reader if row)
    except (OSError, UnicodeError, csv.Error) as exc:
        return _check(
            dataset,
            path,
            "unreadable",
            actual_sha256=actual_sha256,
            actual_bytes=actual_bytes,
            error=str(exc),
        )

    expected_header = [column.name for column in dataset.columns]
    header_mismatch = header != expected_header
    rows_mismatch = actual_rows != dataset.rows
    if header_mismatch:
        status = (
            "csv_contract_mismatch"
            if rows_mismatch
            else "csv_header_mismatch"
        )
        details = [
            f"expected header {expected_header!r}",
            f"found {header!r}",
        ]
        if rows_mismatch:
            details.append(
                f"expected {dataset.rows} rows, found {actual_rows}"
            )
        return _check(
            dataset,
            path,
            status,
            actual_sha256=actual_sha256,
            actual_bytes=actual_bytes,
            actual_rows=actual_rows,
            error="; ".join(details),
        )
    if rows_mismatch:
        return _check(
            dataset,
            path,
            "row_count_mismatch",
            actual_sha256=actual_sha256,
            actual_bytes=actual_bytes,
            actual_rows=actual_rows,
            error=(
                f"expected {dataset.rows} rows, found {actual_rows}"
            ),
        )
    return _check(
        dataset,
        path,
        "ok",
        actual_sha256=actual_sha256,
        actual_bytes=actual_bytes,
        actual_rows=actual_rows,
    )

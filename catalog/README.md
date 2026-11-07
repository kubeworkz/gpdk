# Foundry data catalog

`catalog/gpdk.yaml` is the entry point for the evidence plane. It inventories
data sources and declares the contract for any dataset that is registered.
It is metadata only: raw data stays under `catalog/data/` (ignored by Git) or
another approved store. No access credentials or connection strings belong in
the catalog.

The catalog contains one connected measured dataset: a normalized GRX930
as-built baseline extracted from `chips/grx930.yaml`. It is legacy silicon data
with an undisclosed node, not 28 nm process data. All fab, metrology, test and
commercial sources remain **planned** until their data owner, access path,
license and sensitivity review are complete.

The GRX930 extract records the original measurement date as unavailable; its
`collected_at` value is the source baseline commit date. The raw measured block
is still the YAML source of record, and the CSV is a reproducible normalized
view rather than a new measurement.

## Validate

```bash
python -m fabtwin catalog catalog/gpdk.yaml
python -m fabtwin catalog catalog/gpdk.yaml --json
```

The command exits `2` for an invalid catalog contract, `1` when a registered
dataset is missing or fails verification, and `0` when all checks pass. It
verifies SHA-256, byte size, row count and the exact CSV header. It never
modifies the dataset.

## Source fields

Every source declares:

| Field | Meaning |
|---|---|
| `id` | Stable lowercase identifier |
| `name` | Human-readable source name |
| `domain` | `process`, `metrology`, `equipment`, `factory`, `test`, `package`, `design`, `simulation`, `commercial` or `external` |
| `evidence_class` | `measured`, `vendor`, `literature`, `proxy` or `assumed` |
| `status` | `planned`, `connected` or `blocked` |
| `access` | `local_file`, `database`, `api` or `manual` |
| `format` | Expected export format, such as `csv`, `sql`, `json` or `xlsx` |
| `owner` | Accountable data owner, or `unassigned` |
| `license` | Usage rights, or `unassigned` |
| `sensitivity` | `public`, `internal`, `confidential` or `restricted` |
| `personal_data` | `present`, `absent` or `unverified` |
| `refresh` | `static`, `lot`, `wafer`, `daily`, `weekly`, `monthly`, `per_run` or `unknown` |
| `description` | What the source contains and how it is used |

A source does not become `measured` because it is planned. TCAD output, for
example, remains `assumed` until it is validated against measured structures.

## Dataset contract

A registered dataset is immutable and content-addressed:

```yaml
datasets:
  - id: mes_route_2026_11
    source: mes_route_events
    path: mes_route_2026_11.csv
    media_type: text/csv
    sha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    bytes: 18432
    rows: 2048
    collected_at: "2026-11-01T00:00:00Z"
    evidence_class: measured
    keys: [lot_id, wafer_id]
    time_column: event_time
    columns:
      - name: lot_id
        type: string
      - name: wafer_id
        type: integer
      - name: event_time
        type: datetime
      - name: cycle_time_h
        type: number
        unit: h
    description: De-identified MES route extract for November 2026.
```

- `path` is relative to `data_root`; absolute paths, `..` and symlinks are
  rejected. The repository catalog uses `data_root: .` so curated datasets live
  in `catalog/datasets/` while sensitive raw exports can remain in the ignored
  `catalog/data/`.
- Numeric columns must declare a unit. Text, boolean and datetime columns omit
  it.
- `keys` must reference declared columns and identify the join grain.
- `time_column` is optional but, when present, must be a datetime column.
- CSV verification is exact: extra or missing columns fail the contract.
- If the raw file changes, register a new dataset with a new hash; do not edit
  the hash in place.

## Adding data

1. Obtain the data owner's approval and confirm the license and sensitivity.
2. Export a stable, de-identified file into `catalog/data/` or an approved
   local store.
3. Compute SHA-256 and byte size.
4. Declare every column, unit, key and optional time column.
5. Run the validation command and keep only `ok` checks.
6. Record any transformation or extraction outside this catalog; the catalog
   points to the exact bytes, not a mutable query result.

The catalog deliberately does not ingest raw data. A later calibration step
will read registered datasets through their contracts, preserve the same
provenance, and back-test the model against held-out lots and time periods.

## MES request package

The partner-facing request is [docs/mes-data-request.md](../docs/mes-data-request.md).
It covers the proposed NDA term sheet, de-identification checklist, delivery
format and acceptance criteria. Header-only templates live in
[`templates/`](templates/): `mes_route_events.csv` and
`mes_equipment_events.csv`, with matching `.schema.yaml` field contracts.

These templates are not registered datasets. When a provider supplies a real
extract, verify its header against the schema, keep the raw file outside Git,
compute the SHA-256 of the exact bytes, and register it only after the
acceptance checks pass. Do not silently add columns; update the template and schema
together.

The executable ingest and acceptance runbook is
[docs/mes-ingest-checklist.md](../docs/mes-ingest-checklist.md); the fillable
manifest template is
[`templates/mes_manifest.template.json`](templates/mes_manifest.template.json).

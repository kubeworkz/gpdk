# MES request templates

The CSV files here are **header-only request contracts**; the JSON file is a
provenance template. None are datasets. They are not registered in
`catalog/gpdk.yaml` and must never be labelled `measured`.

- `mes_route_events.csv` / `.schema.yaml`: event-level route, lot, wafer, tool
  and duration contract.
- `mes_equipment_events.csv` / `.schema.yaml`: tool state-transition contract.
- `mes_manifest.template.json`: fillable extract manifest. Generate the real
  hash and row inventory with `python -m fabtwin mes-manifest`; never replay the
  template itself.

The partner-facing scope, de-identification checklist, acceptance criteria and
NDA term sheet are in [`../../docs/mes-data-request.md`](../../docs/mes-data-request.md).
The executable ingest and acceptance runbook is
[`../../docs/mes-ingest-checklist.md`](../../docs/mes-ingest-checklist.md).

When a real extract arrives, keep the raw file outside Git, verify its header
against the schema, hash the exact bytes, and register it with the catalog only
after the acceptance checks pass. Update the header and schema together if the
provider needs an agreed extension; do not silently add columns.

## Synthetic fixtures

`python -m fabtwin mes-synth --out out/mes` generates a deterministic synthetic
window from `fabtwin/mes.py`. It covers a re-entrant front-end route, an OSAT
route, lot splits and merges, scrap, hold and rework events, and tiling tool
states. The manifest marks every file `evidence_class: assumed`,
`synthetic: true` and `measured: false`. These are test fixtures for the schema
and genealogy plumbing; never register or cite them as measured data.

A committed two-lot fixture lives in
[`../../factory/mes_smoke`](../../factory/mes_smoke).
`scenarios/mes_line_replay.yaml` replays it through the `factory_replay` engine,
which verifies the manifest and contracts before reporting event-derived cycle,
queue, WIP and tool metrics.

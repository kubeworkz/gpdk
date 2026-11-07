# MES extract ingest checklist

**Status:** runbook v0.1, 2026-11-06

**Use with:** [mes-data-request.md](mes-data-request.md) for scope, de-identification,
acceptance criteria and the data-use term sheet.

**Manifest template:** [mes_manifest.template.json](../catalog/templates/mes_manifest.template.json)

`factory/mes_smoke/` is a synthetic regression fixture. It is not a template for
a measured extract and is never registered as measured data. A real extract gets
its own directory, manifest and scenario.

No extract is replayed or registered as `measured` until every required check in
this runbook passes. A failed check returns the extract to the provider for
correction; it is not silently repaired in place.

## 1. Before the files arrive

- [ ] The data-use agreement and de-identification attestation are signed.
- [ ] The provider has the exact header contracts from `catalog/templates/`.
- [ ] The window is agreed in writing, including the time shift. Target 8–12
      consecutive production weeks, not a clean-baseline-only sample.
- [ ] The provider will export all production lots in the window, or a documented
      representative sample of at least 20 lots, three products/routes and two
      tools per major tool group.
- [ ] The provider will include a state-transition row for every tool at the
      window start. A tool whose first row is later cannot be utilization-audited
      against the full window.
- [ ] At least one lot completes inside the window. The replay needs a completed
      lot to derive cycle time; an open-lot-only extract is not accepted.
- [ ] Raw files will arrive as UTF-8 RFC 4180 CSVs through the approved encrypted
      transfer. They will not be emailed or committed to Git.

The request, prohibited fields, tokenization rules and NDA term sheet are in
[mes-data-request.md](mes-data-request.md). Do not accept a file that contains
customer, product, employee, supplier or facility identifiers, free text or
recipe parameters.

## 2. Stage the extract

Use an approved local store, not the repository. `catalog/data/` is gitignored
for local work, but any approved store is acceptable.

```text
<approved-store>/mes/<extract-id>/
  mes_route_events.csv
  mes_equipment_events.csv
  manifest.json          # generated in step 3
```

If the provider uses different file names, pass them with `--route` and
`--equipment`. The manifest paths are recorded relative to the extract
directory; do not move the CSVs after the manifest is written.

## 3. Build the manifest

```bash
python -m fabtwin mes-manifest <approved-store>/mes/<extract-id> \
  --evidence-class measured \
  --provider <provider-or-site-token> \
  --source-system <MES-or-OSAT-system-and-version> \
  --extract-id <extract-name-and-version> \
  --extract-time 2026-11-06T12:00:00+00:00 \
  --generator <provider-export-tool> \
  --generator-version <export-version>
```

Add `--note` for known exclusions, outages or a transfer reference. Add
`--window-start`/`--window-end` when the agreed window differs from the first
and last event in the files. If the window is not supplied, it is inferred from
the event timestamps.

`mes-manifest` verifies and records:

- exact header names and order against both contracts;
- UTF-8 and RFC 4180 parsing, with no blank or ragged rows;
- a non-empty, unique `event_id` within each file;
- parseable `event_time_utc` values with an explicit offset;
- one or more data rows per file;
- the exact byte count, row count and SHA-256 of each file;
- the declared evidence class, window and provider metadata.

It refuses to overwrite an existing `manifest.json` unless `--force` is given.
Use `--force` only after re-exporting the data and rebuilding the manifest.

The template shows the full field set. Do not copy the template into place and
fill in hashes by hand; use the command so the bytes and hashes agree.

## 4. Run the acceptance check

```bash
python -m fabtwin mes-check <approved-store>/mes/<extract-id>/manifest.json
```

By default this writes `acceptance.json` beside `manifest.json`. The report
embeds the manifest and its SHA-256, lists every check with its status, stores
the event-derived metric summary, and records `status: ok` or `status: failed`.
Use `--report PATH` to write it elsewhere, or `--no-report` for a dry run. A
failed check writes a failed report with the error, so an old success cannot be
mistaken for the current extract.

The command must end with `status: ok` and at least one completed lot. It
re-verifies the manifest and runs the same checks the replay uses:

| Area | Required result |
|---|---|
| Manifest | `schema_version: "0.1"`, valid evidence class, `synthetic: false`, `measured: true` |
| Integrity | Byte count, row count and SHA-256 match every declared file |
| Header | Exact match to the route or equipment contract |
| Time | Every event is inside the manifest window; timestamps carry an offset |
| Route order | Events are monotonic within each lot; `split`/`merge` has a parent |
| Genealogy | Every `parent_lot_id` resolves to a lot in the extract; no cycles |
| Event types | Only the allowed route event types and equipment states are present |
| Tool states | Each tool starts exactly at the window start, then transitions in strictly increasing order with no overlap |
| Completion | At least one `lot_complete`; no lot has multiple completions |
| Metrics | Cycle, queue, WIP, throughput and utilization are derived successfully |
| Report | `acceptance.json` exists beside the manifest, has `status: ok`, the manifest hash and populated metrics |

`mes-check` does not reconcile the optional WIP-snapshot or lot-summary tables,
and it does not prove that the provider's MES extract is complete. Do that
reconciliation in step 5 before registration.

If the check fails, return the specific error to the provider. Do not edit a CSV
to make a check pass, and do not fabricate a standby row, split, completion or
timestamp. Re-export with the corrected boundary, window or identifiers.

## 5. Reconcile against the validation tables

Where the provider supplied `mes_wip_snapshots.csv` or `mes_lot_summary.csv`:

- [ ] Completed wafers reconcile to the lot summary, allowing documented
      scrap/rework.
- [ ] Daily WIP snapshots agree with the event-derived active-lot count within
      the documented snapshot tolerance.
- [ ] Scrap and rework quantities reconcile to the lot summary.
- [ ] The throughput denominator is the agreed window, not the extract's first
      and last event by accident.
- [ ] Missing values are empty and flagged, not sentinel values.
- [ ] Known exclusions and outages are recorded in the manifest note.

Resolve or document every difference. A reconciliation failure is a data-quality
finding, not a reason to alter the event log.

## 6. Replace the synthetic fixture

Keep `factory/mes_smoke/` and `scenarios/mes_line_replay.yaml` unchanged as the
synthetic regression baseline. Create a separate measured scenario:

```bash
cp scenarios/mes_line_replay.yaml scenarios/mes_line_measured.yaml
```

Edit the copy. At minimum:

```yaml
id: mes_line_measured
description: Replay the accepted measured MES extract for <window>.
product: <your-product-token>
process: <your-process-token>@<revision>
inputs:
  chip: chips/g100.yaml
  mes: catalog/data/mes/<extract-id>/manifest.json
```

Use a project-relative path when the approved store is under `catalog/data/`.
An absolute path works locally but makes the scenario non-portable and records a
local path in the run manifest.

Then validate and run:

```bash
python -m fabtwin validate scenarios/mes_line_measured.yaml
python -m fabtwin run scenarios/mes_line_measured.yaml --out out/mes_measured
```

In the report and `run.json`:

- [ ] Product and process are the measured product's internal tokens, not
      `mes_line`/`mes_fixture@0.1.0`.
- [ ] Every replay observation is `measured`, not `assumed`.
- [ ] The MES input record points to the accepted manifest and its hash.
- [ ] The metrics are plausible against the reconciliation in step 5.
- [ ] Held-out lots or a held-out time period were used for the back-test; the
      result is not a random-row split.

## 7. Register metadata, not rows

After acceptance:

- [ ] Keep the raw CSVs in the approved store; they remain gitignored.
- [ ] Register only the provider, license, sensitivity, retention, extraction
      window, de-identification attestation reference, manifest hash, byte size,
      row count and contract with the catalog.
- [ ] Do not register the manifest template, the synthetic fixture or a
      header-only contract as a measured dataset.
- [ ] Keep the `acceptance.json` report with the accepted extract and record
      its path.
- [ ] Record the accepted extract and scenario in the project notes so a later
      run can be reproduced.
- [ ] Retain or delete the raw data according to the agreement.

Follow [catalog/README.md](../catalog/README.md) for the catalog schema. A
catalog entry is metadata about a verified file, not a copy of its rows.

## Command summary

```bash
python -m fabtwin mes-manifest <extract-dir> --evidence-class measured \
  --provider <token> --source-system <system> --extract-id <id> \
  --extract-time <ISO-8601>
python -m fabtwin mes-check <extract-dir>/manifest.json  # writes acceptance.json
python -m fabtwin validate scenarios/mes_line_measured.yaml
python -m fabtwin run scenarios/mes_line_measured.yaml --out out/mes_measured
```

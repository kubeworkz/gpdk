# MES data request package

**Status:** draft v0.1 for data-owner and legal review, 2026-11-06
**Recipient:** GPDK foundry digital-twin project
**Data provider:** foundry, OSAT, pilot line, or manufacturing partner
**Purpose:** calibrate and back-test the G100/PTA factory and ATP model

This package is a scope and term-sheet starting point, not legal advice. Counsel
for both parties must review the final data-use agreement. The machine-readable
field contracts are in [`catalog/templates`](../catalog/templates/).

## 1. What we are asking for

The first request is deliberately narrow: **de-identified event-level MES data
for a bounded production window**, plus the equipment-state data needed to
separate process time from queue, setup and downtime.

| Priority | Table | Grain | Required |
|---|---|---|---|
| Core | `mes_route_events.csv` | One row per lot/wafer route event | Yes |
| Core | `mes_equipment_events.csv` | One row per tool state transition | Yes |
| Validation | `mes_wip_snapshots.csv` | One row per lot/wafer/operation at a daily snapshot | Preferred |
| Validation | `mes_lot_summary.csv` | One row per lot | Preferred |
| Phase 2 | `mes_test_package.csv` | One row per die/package/test bin | Optional |

### Window and sample

- **12 consecutive production weeks** is the target; accept 8 weeks if that is
  the available retention window.
- Include at least one planned-maintenance cycle and one excursion, hold, or
  recovery period. Do not send only a clean baseline.
- Include all production lots in the window, or a documented representative
  sample covering at least 20 lots, three products/routes and two tools per
  major tool group.
- Preserve the original event order and timestamps. Do not aggregate events
  before delivery.
- For an OSAT, include assembly, mold, final-test and package-yield events. For a
  front-end line, include the full route through wafer sort and die output.

### What not to send

Do not send customer names, design names, product names, operator or employee
identifiers, supplier identities, facility addresses, free-text comments,
recipe parameters, chemical formulas, prices or contract terms. Pseudonymous
tokens are sufficient for every join in this request.

## 2. Why the data is needed

The current factory model is an F1 planning model. It uses a declared 38-step
route, tool counts, process times, MTBF/MTTR availability and operating-cost
assumptions. It has no measured MES route, queue, equipment-state or yield
calibration. The model is useful for direction and bottleneck ranking, but its
absolute cycle time, WIP and cost are not yet calibrated to a real line.

The requested data lets us:

- replay actual lot and tool events through the SimPy model;
- fit process, queue, setup and downtime distributions by operation and tool
  group;
- reconcile WIP and throughput against measured line behavior;
- hold out complete lots and time periods for honest back-testing;
- replace the current planning assumptions with `measured` evidence, while
  keeping `assumed` and `measured` inputs visibly separate.

The data will **not** be used for production control, dispatch, foundry
sign-off, customer reporting or reverse engineering of a process recipe.

## 3. Field contract

### Route events

File: `catalog/templates/mes_route_events.csv`
Schema: `catalog/templates/mes_route_events.schema.yaml`

The route table is an **event log**, not a pre-aggregated cycle-time table. One
row describes one event for one lot or wafer. The minimum required fields are:

| Field | Meaning |
|---|---|
| `event_id` | Unique event identifier generated for the extract |
| `event_type` | `lot_start`, `move_in`, `process_start`, `process_end`, `move_out`, `hold_start`, `hold_end`, `rework`, `scrap`, `split`, `merge` or `lot_complete` |
| `event_time_utc` | Event timestamp in ISO 8601 with timezone |
| `lot_id` | Stable pseudonymous lot token |
| `parent_lot_id` | Optional parent token for split and merge edges |
| `product_id`, `route_id`, `route_revision` | Stable pseudonymous product and route tokens |
| `operation_seq`, `operation_id`, `operation_type` | Route position and generic operation class |
| `wafer_count` | Number of wafers represented by the event |
| `wafer_id` | Optional pseudonymous wafer token when the MES tracks wafer-level events |
| `tool_id`, `tool_group_id`, `tool_class` | Optional except for process events; stable tokens plus a generic tool class |
| `process_time_s`, `queue_time_s`, `setup_time_s` | Optional measured durations in seconds |
| `recipe_id`, `recipe_revision`, `chamber_id` | Optional pseudonymous tokens only; no recipe parameters |
| `scrap_qty`, `rework_qty` | Optional wafer counts for scrap/rework events |
| `hold_reason_code` | Optional generalized reason category |
| `data_quality_flag` | Optional `ok`, `late`, `estimated`, `missing`, `duplicate` or `other` |

Conditional requirements:

- `process_start` and `process_end` should carry `tool_id`, `tool_group_id` and
  `tool_class`; `process_end` should carry `process_time_s`.
- `move_in` should carry `queue_time_s` when it is available as a measured
  value. If queue time is not exported, we will derive it from the event log.
- A `split` or `merge` is one row per parent-child edge: `lot_id` is the child,
  `parent_lot_id` is the contributing parent, and `wafer_count` is the child or
  contributing quantity. This preserves genealogy without free-text notes.
- `wafer_id` is required only if the source system tracks wafers individually.
- `scrap_qty` is required for `scrap`; `rework_qty` is required for `rework`.
- A missing value is an empty field, not `NULL`, `N/A` or `-1`. Use
  `data_quality_flag` to distinguish a true missing value from a real zero.

### Equipment events

File: `catalog/templates/mes_equipment_events.csv`
Schema: `catalog/templates/mes_equipment_events.schema.yaml`

The equipment table is a **state-transition log**. One row starts a state; the
next event for the same tool closes it. Required fields are `event_id`,
`event_time_utc`, `tool_id`, `tool_group_id`, `tool_class` and `state`. The
state vocabulary is:

`productive`, `standby`, `engineering`, `scheduled_down`,
`unscheduled_down`, `non_scheduled`, `setup`.

Optional fields are `reason_code`, `failure_mode_code`, `maintenance_type`,
`lot_id`, `wafer_count`, `recipe_id`, `alarm_code` and `data_quality_flag`.
Reason, failure, alarm and maintenance values must be generalized or tokenized;
do not send free-text repair notes.

### Validation tables

`mes_wip_snapshots.csv` should contain `snapshot_time_utc`, `lot_id`,
`wafer_id`, `operation_seq`, `operation_id`, `tool_group_id`, `queue_status`,
`wafer_count` and `hold_flag`. `mes_lot_summary.csv` should contain `lot_id`,
`product_id`, `route_id`, `route_revision`, `start_time_utc`,
`completion_time_utc`, `wafer_count`, `good_die_count`, `scrap_qty`,
`rework_qty`, `priority` and `hold_flag`. These are validation aids; the event
tables remain the source of record.

## 4. Delivery specification

- One CSV per table, UTF-8, RFC 4180, header row, comma-separated, no Excel
  formatting, no merged cells and no formulas.
- ISO 8601 timestamps with `Z` or an explicit offset. Prefer UTC. State whether
  the source timestamps are event, transaction or equipment-clock times.
- SI durations in seconds; counts as integers; ratios as dimensionless values.
- Stable pseudonymous tokens for every entity. Tokens must join across tables.
- Empty fields for missing values. Do not use sentinel values.
- Do not sort away the original event sequence. A separate `extract_seq` column
  may be added if the source order is otherwise lost.
- Include a `manifest.json` or `manifest.csv` with: extract name and version,
  source system, extraction query or query hash, row counts, minimum and maximum
  event times, SHA-256 per file, byte sizes, known exclusions and known outages.
- Deliver as an AES-256 encrypted archive through an approved transfer method.
  Send the password through a separate channel. Do not email raw CSVs.

The header-only templates are not data and must not be registered as measured
datasets. They exist so the provider and the model team can agree on the exact
column contract before extraction.

## 5. De-identification checklist

- [ ] Remove customer, product, design, supplier, facility, operator, employee,
      phone, email and address identifiers.
- [ ] Replace lot, wafer, product, route, operation, tool, chamber and recipe
      identifiers with stable tokens from a salted keyed hash.
- [ ] Keep the token mapping at the provider. Do not send the salt, key or
      mapping table.
- [ ] Shift all timestamps by a constant per-site offset that preserves
      intervals and ordering. Do not disclose the offset unless separately
      agreed.
- [ ] Generalize operation and tool names to the controlled classes in the
      schema. Keep the route sequence.
- [ ] Generalize or tokenize hold, failure, alarm and maintenance reasons.
      Remove free-text repair notes.
- [ ] Suppress or group rare routes, products and tools with fewer than three
      lots if they could identify a customer or product.
- [ ] Remove recipe parameters, chemical names, chamber settings and any design
      or process IP. A tokenized recipe ID and revision are sufficient.
- [ ] Scan the header and a sample of every file for the prohibited identifiers
      and for free-text fields.
- [ ] Have the provider's data owner sign the de-identification attestation.
- [ ] Confirm that no received field can be used to re-identify a person,
      customer or product, and that re-identification is contractually
      prohibited.

| Treatment | Fields |
|---|---|
| Remove | customer, design, supplier, facility, operator, employee, contact, address, comments, recipe parameters |
| Tokenize | lot, wafer, product, route, operation, tool, chamber, recipe, reason/failure/alarm codes |
| Generalize | operation class, tool class, hold reason, maintenance type, rare routes/products |
| Shift | all event and snapshot timestamps by a constant per-site offset |
| Preserve | event order, route sequence, durations, queue/process/setup times, wafer counts, scrap/rework counts, state transitions, yield bins |

## 6. Acceptance criteria

| Check | Requirement |
|---|---|
| Header | Exact match to the agreed schema; no extra columns |
| Integrity | SHA-256 and byte size match the manifest |
| Keys | `event_id` unique; `lot_id`, `wafer_id`, `route_id`, `operation_id` and `tool_id` join across tables |
| Time | ISO 8601 with timezone; no impossible dates; event times monotonic within a lot/wafer/tool history |
| Sequence | Route operations follow a valid sequence; process end is not before process start |
| Tool state | Every state transition has a next state or an explicit open interval at the window boundary |
| Counts | `wafer_count`, scrap and rework reconcile to the lot summary where supplied |
| Coverage | Every required tool group and route has at least one measured lot; sample selection is documented |
| Missingness | Missing values are empty, flagged and explained; no sentinel values |
| PII | No direct identifiers or free text; de-identification attestation signed |
| Provenance | Source system, query version, extraction time, window and known exclusions recorded |

A failed check returns the file for correction; it is not silently repaired in
the catalog.

## 7. NDA-ready scope and term sheet

This is a proposed term sheet for counsel, not a signed agreement.

| Term | Proposed scope |
|---|---|
| Parties | GPDK project (Recipient) and the data provider (Provider) |
| Purpose | Calibrate, validate and back-test the GPDK factory/ATP digital twin, including training and evaluating internal models |
| Data | De-identified MES route events, equipment-state events, optional WIP snapshots, lot summaries and package/test summaries for the agreed window |
| Excluded data | Customer and design identity, employee identity, recipe parameters, chemical/process IP, supplier pricing, contract terms, free-text notes |
| Permitted use | Internal research, model development, calibration, validation and aggregate reporting |
| Prohibited use | Resale, redistribution, re-identification, reverse engineering, competitive benchmarking, production control, foundry sign-off, training models for third parties |
| Access | Named personnel only; least privilege; MFA; encrypted at rest and in transit; access logging |
| Transfer | Encrypted archive via an approved channel; password separately; no removable media |
| Retention | Raw data retained for 24 months unless a shorter period is agreed, then deleted or returned with written confirmation |
| Derived data | Aggregate results, model parameters and model code may survive deletion; no raw rows or re-identifiable derivatives |
| Publication | Aggregate results only, no raw examples, no customer/product attribution; Provider review for 30 days before submission |
| IP | Provider retains all rights in the raw data; Recipient retains rights in its models and code; no implied license beyond the purpose |
| Security incidents | Notify Provider within 72 hours of discovery; cooperate on containment and remediation |
| Warranty | Data is provided as-is; Provider does not warrant completeness or fitness for a particular purpose |
| Term | 12 months from signature, renewable by written agreement |
| Governing law | To be completed by counsel |

## 8. Request email

```text
Subject: De-identified MES data request for factory digital-twin calibration

Hello [Name],

We are calibrating an internal factory/ATP digital twin for a 28 nm-class
G100/PTA program. We would like to request a de-identified MES extract for a
12-week production window, covering route events and equipment-state events.
The package defines the exact columns, units, quality checks and proposed
data-use terms:

  docs/mes-data-request.md
  catalog/templates/mes_route_events.csv
  catalog/templates/mes_equipment_events.csv

We are not asking for customer or design identities, recipe parameters,
employee data, pricing or free-text notes. Identifiers can be replaced with
stable tokens, and timestamps can be shifted while preserving intervals. We
will use the data only for internal model calibration and aggregate reporting.
Raw data will be encrypted, access-limited and deleted at the end of the agreed
retention period.

Could we schedule a short review with your data owner and legal team? We can
adapt the scope to your retention and transfer requirements.

Regards,
[Name]
[Role]
[Contact]
```

## 9. Ingest and registration after delivery

The executable ingest and acceptance runbook is
[mes-ingest-checklist.md](mes-ingest-checklist.md); the fillable manifest is
[mes_manifest.template.json](../catalog/templates/mes_manifest.template.json).

When the provider delivers files:

1. Stage the two event CSVs in an approved store and build the manifest:

   ```bash
   python -m fabtwin mes-manifest <extract-dir> --evidence-class measured \
     --provider <token> --source-system <system> \
     --extract-id <id> --extract-time <ISO-8601>
   ```

2. Run `python -m fabtwin mes-check <extract-dir>/manifest.json`. It writes
   `acceptance.json` beside the manifest and must print `status: ok`; it
   verifies headers, hashes, row counts, timestamps, event order, genealogy,
   tool-state tiling and completed lots.
3. Reconcile completed wafers, WIP snapshots, scrap and rework against the
   optional validation tables. Document every difference; do not edit the event
   log to make a check pass.
4. Record the provider, license, sensitivity, retention and de-identification
   attestation as source metadata.
5. Do not copy raw data into Git. Keep it under `catalog/data/` or an approved
   local store and register only its hash, size, row count and contract.
6. Register the dataset as `measured` only after the acceptance checks pass.
   Templates, empty headers and synthetic demo data remain `assumed` or
   `literature`, never `measured`.
7. Back-test on held-out lots and time periods, not a random row split.

## 10. Out of scope for the first request

- Raw FDC traces, high-rate sensor waveforms and image data.
- Detailed recipe parameters, chamber settings, chemical names or process IP.
- Customer, design, product or employee identity.
- Full financial data, supplier contracts or prices.
- Any claim of foundry sign-off, tape-out readiness or production control.

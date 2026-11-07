# fabtwin run `pta_28nm_baseline-20261107T043410Z-158ad6f0`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `pta_28nm_baseline` |
| Description | Record the PTA product envelope and MCM package contract: 4x4 MZI mesh, four input/output ports, 200 um window, 20 um lane pitch and 1550 nm operation. No insertion-loss, phase-error or tensor-error model is applied. |
| Product | `pta` |
| Process | `grx28@0.1.0` |
| Seed | 20261105 |
| Samples | 1 |
| Engines | `pta` |
| Outputs | `mesh_rows`, `mesh_columns`, `mzi_count`, `input_port_count`, `output_port_count`, `optical_window_m`, `lane_pitch_m`, `wavelength_m` |
| Scenario SHA-256 | `88b2b9dc505b9202...` |
| Package | `packages/mcm_si.yaml` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| pta | 0.1.0 | F0 | pta-assumptions@0.1.0 | PTA | GRX28 0.1.0 |

### Design points

| Engine | Key | Label | Library | Tracks | Die binding | Best |
|---|---|---|---|---|---|---|

## Observations

Values in `observations.csv` are base SI. This table converts area to mm2,
frequency to MHz/GHz, and power to mW/W for readability. A blank uncertainty in
the CSV, or "not estimated" here, means it was not estimated, not that the
value is exact.

| Entity type | Entity | Metric | Value | Unit | Evidence | Uncertainty |
|---|---|---|---|---|---|---|
| product | pta | mesh_rows | 4.000 | ratio | assumed | not estimated |
| product | pta | mesh_columns | 4.000 | ratio | assumed | not estimated |
| product | pta | mzi_count | 16.000 | ratio | assumed | not estimated |
| product | pta | input_port_count | 4.000 | ratio | assumed | not estimated |
| product | pta | output_port_count | 4.000 | ratio | assumed | not estimated |
| product | pta | optical_window_m | 0.0002 | m | assumed | not estimated |
| product | pta | lane_pitch_m | 2e-05 | m | assumed | not estimated |
| product | pta | wavelength_m | 1.55e-06 | m | assumed | not estimated |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| assumed | 8 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/pta_28nm_baseline.yaml` | `88b2b9dc505b9202...` | 782 |
| package | `packages/mcm_si.yaml` | `66e840836c5a2d12...` | 1263 |
| chip | `chips/pta.yaml` | `c80fbe2fe91def53...` | 1286 |
| tech | `tech/grx28.yaml` | `fec22f0374bcdbf8...` | 5982 |

## Reproduce

```bash
python -m fabtwin run scenarios/pta_28nm_baseline.yaml --out /tmp/fabtwin-site-jjg9y_2q
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-jjg9y_2q/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-jjg9y_2q/fabtwin.db --run pta_28nm_baseline-20261107T043410Z-158ad6f0
```

Artifacts: [observations.csv](observations.csv) · [run.json](run.json)

## Caveats

- PTA baseline records topology assumptions only; optical insertion loss, phase error, thermal tuning and tensor error are not modeled in Phase 0.
- No qualified silicon-photonics PDK or measured PTA data is used; these are planning assumptions.

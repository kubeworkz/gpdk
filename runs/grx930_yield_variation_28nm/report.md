# fabtwin run `grx930_yield_variation_28nm-20261107T043410Z-09b55ada`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `grx930_yield_variation_28nm` |
| Description | Simulate GRX930 lots with lognormal lot and wafer defect-density variation and assembly-lot ppm variation, reporting the mean die yield and both variance components. |
| Product | `grx930` |
| Process | `grx28@0.1.0` |
| Seed | 20261106 |
| Samples | 40 |
| Engines | `yield_variation` |
| Outputs | `die_yield_mean`, `wafer_to_wafer_die_yield_sigma`, `lot_to_lot_die_yield_sigma`, `assembly_yield_mean`, `good_packages_per_wafer_mean`, `cost_per_good_package_usd_mean` |
| Scenario SHA-256 | `6308d45f4a95ba94...` |
| Yield model | `yields/grx930_28nm.yaml` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| yield_variation | 0.1.0 | F1 | yield-assumptions@0.2.0 | GRX930 | GRX28 0.1.0 |

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
| lot_simulation | grx930 | die_yield_mean | 0.996 | ratio | assumed | 9.70874e-05 |
| lot_simulation | grx930 | wafer_to_wafer_die_yield_sigma | 0.000 | ratio | assumed | not estimated |
| lot_simulation | grx930 | lot_to_lot_die_yield_sigma | 0.001 | ratio | assumed | not estimated |
| lot_simulation | grx930 | assembly_yield_mean | 0.994 | ratio | assumed | 2.27995e-05 |
| lot_simulation | grx930 | good_packages_per_wafer_mean | 4815.566 | ratio | assumed | 0.562587 |
| lot_simulation | grx930 | cost_per_good_package_usd_mean | 2.5464 | USD | assumed | 0.000185754 |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| assumed | 6 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/grx930_yield_variation_28nm.yaml` | `6308d45f4a95ba94...` | 803 |
| yield | `yields/grx930_28nm.yaml` | `3ebfeb60d2096a28...` | 2279 |
| chip | `chips/grx930.yaml` | `3d2a312cd4196c52...` | 4763 |
| tech | `tech/grx28.yaml` | `fec22f0374bcdbf8...` | 5982 |

## Reproduce

```bash
python -m fabtwin run scenarios/grx930_yield_variation_28nm.yaml --out /tmp/fabtwin-site-jjg9y_2q
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-jjg9y_2q/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-jjg9y_2q/fabtwin.db --run grx930_yield_variation_28nm-20261107T043410Z-09b55ada
```

Artifacts: [observations.csv](observations.csv) · [run.json](run.json)

## Caveats

- Yield variation is an F1 planning exercise, not a calibrated fab or OSAT distribution.
- Defect-density and assembly CVs are assumed lognormal multipliers with the nominal value as median.
- Yield sigmas describe the modelled expected yield; they exclude die-sampling noise.

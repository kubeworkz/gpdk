# fabtwin run `grx930_yield_28nm-20261107T043408Z-8161c102`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `grx930_yield_28nm` |
| Description | Estimate GRX930 die-per-wafer, defect-limited die yield, package assembly yield, known-good die count, and cost per good package with a seeded Monte Carlo sample. Every number is an assumption-driven planning estimate. |
| Product | `grx930` |
| Process | `grx28@0.1.0` |
| Seed | 20261106 |
| Samples | 1000 |
| Engines | `yield` |
| Outputs | `die_area_m2`, `critical_area_m2`, `gross_dies_per_wafer`, `die_yield`, `assembly_yield`, `known_good_dies_per_wafer`, `good_packages_per_wafer`, `cost_per_known_good_die_usd`, `cost_per_good_package_usd` |
| Scenario SHA-256 | `9551afbe7de7bed2...` |
| Yield model | `yields/grx930_28nm.yaml` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| yield | 0.1.0 | F1 | yield-assumptions@0.2.0 | GRX930 | GRX28 0.1.0 |

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
| product | grx930 | die_area_m2 | 12.992 | mm2 | assumed | not estimated |
| product | grx930 | critical_area_m2 | 4.547 | mm2 | assumed | not estimated |
| product | grx930 | gross_dies_per_wafer | 4865.000 | ratio | assumed | not estimated |
| product | grx930 | die_yield | 0.996 | ratio | assumed | 2.71959e-05 |
| product | grx930 | assembly_yield | 0.994 | ratio | assumed | not estimated |
| product | grx930 | known_good_dies_per_wafer | 4847.190 | ratio | assumed | 0.132308 |
| product | grx930 | good_packages_per_wafer | 4816.000 | ratio | assumed | 0.212219 |
| product | grx930 | cost_per_known_good_die_usd | 0.928373 | USD | assumed | not estimated |
| product | grx930 | cost_per_good_package_usd | 2.54623 | USD | assumed | 9.64294e-05 |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| assumed | 9 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/grx930_yield_28nm.yaml` | `9551afbe7de7bed2...` | 946 |
| yield | `yields/grx930_28nm.yaml` | `3ebfeb60d2096a28...` | 2279 |
| chip | `chips/grx930.yaml` | `3d2a312cd4196c52...` | 4763 |
| tech | `tech/grx28.yaml` | `fec22f0374bcdbf8...` | 5982 |

## Reproduce

```bash
python -m fabtwin run scenarios/grx930_yield_28nm.yaml --out /tmp/fabtwin-site-jjg9y_2q
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-jjg9y_2q/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-jjg9y_2q/fabtwin.db --run grx930_yield_28nm-20261107T043408Z-8161c102
```

Artifacts: [observations.csv](observations.csv) · [run.json](run.json)

## Caveats

- Yield is an F1 planning estimate, not a foundry yield prediction.
- Wafer, defect, critical-area, assembly and cost values are explicit assumptions; replace them with calibrated data before making commitments.
- Monte Carlo reports sampling uncertainty for one wafer, not wafer-to-wafer variation.

# fabtwin run `grx930_yield_sensitivity_28nm-20261107T043409Z-97332ece`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `grx930_yield_sensitivity_28nm` |
| Description | Sweep GRX930 die yield, good packages per wafer, and cost per good package over the planning defect-density, pad-count, and assembly-tolerance points in yields/grx930_28nm.yaml. |
| Product | `grx930` |
| Process | `grx28@0.1.0` |
| Seed | 20261106 |
| Samples | 100 |
| Engines | `yield_sensitivity` |
| Outputs | `defect_density_per_cm2`, `pad_count`, `assembly_per_pad_ppm`, `die_yield`, `good_packages_per_wafer`, `cost_per_good_package_usd` |
| Scenario SHA-256 | `7c3d2c2a5e4d569c...` |
| Yield model | `yields/grx930_28nm.yaml` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| yield_sensitivity | 0.1.0 | F1 | yield-assumptions@0.2.0 | GRX930 | GRX28 0.1.0 |

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
| sensitivity_point | defect_density:0.02 | defect_density_per_cm2 | 0.02 | 1/cm2 | assumed | not estimated |
| sensitivity_point | defect_density:0.02 | die_yield | 0.999 | ratio | assumed | 3.73337e-05 |
| sensitivity_point | defect_density:0.02 | good_packages_per_wafer | 4829.450 | ratio | assumed | 0.511361 |
| sensitivity_point | defect_density:0.02 | cost_per_good_package_usd | 2.54252 | USD | assumed | 0.000265084 |
| sensitivity_point | defect_density:0.05 | defect_density_per_cm2 | 0.05 | 1/cm2 | assumed | not estimated |
| sensitivity_point | defect_density:0.05 | die_yield | 0.998 | ratio | assumed | 6.77962e-05 |
| sensitivity_point | defect_density:0.05 | good_packages_per_wafer | 4822.180 | ratio | assumed | 0.730902 |
| sensitivity_point | defect_density:0.05 | cost_per_good_package_usd | 2.54454 | USD | assumed | 0.0003526 |
| sensitivity_point | defect_density:0.08 | defect_density_per_cm2 | 0.08 | 1/cm2 | assumed | not estimated |
| sensitivity_point | defect_density:0.08 | die_yield | 0.996 | ratio | assumed | 8.42329e-05 |
| sensitivity_point | defect_density:0.08 | good_packages_per_wafer | 4816.470 | ratio | assumed | 0.636032 |
| sensitivity_point | defect_density:0.08 | cost_per_good_package_usd | 2.54604 | USD | assumed | 0.000287696 |
| sensitivity_point | defect_density:0.12 | defect_density_per_cm2 | 0.12 | 1/cm2 | assumed | not estimated |
| sensitivity_point | defect_density:0.12 | die_yield | 0.995 | ratio | assumed | 9.58796e-05 |
| sensitivity_point | defect_density:0.12 | good_packages_per_wafer | 4807.250 | ratio | assumed | 0.770724 |
| sensitivity_point | defect_density:0.12 | cost_per_good_package_usd | 2.54886 | USD | assumed | 0.000341267 |
| sensitivity_point | defect_density:0.2 | defect_density_per_cm2 | 0.2 | 1/cm2 | assumed | not estimated |
| sensitivity_point | defect_density:0.2 | die_yield | 0.991 | ratio | assumed | 0.000136084 |
| sensitivity_point | defect_density:0.2 | good_packages_per_wafer | 4792.170 | ratio | assumed | 0.938304 |
| sensitivity_point | defect_density:0.2 | cost_per_good_package_usd | 2.55252 | USD | assumed | 0.00037599 |
| sensitivity_point | pad_count:57 | pad_count | 57.000 | ratio | assumed | not estimated |
| sensitivity_point | pad_count:57 | die_yield | 0.996 | ratio | assumed | 9.22639e-05 |
| sensitivity_point | pad_count:57 | good_packages_per_wafer | 4821.990 | ratio | assumed | 0.628369 |
| sensitivity_point | pad_count:57 | cost_per_good_package_usd | 2.54316 | USD | assumed | 0.000279979 |
| sensitivity_point | pad_count:112 | pad_count | 112.000 | ratio | assumed | not estimated |
| sensitivity_point | pad_count:112 | die_yield | 0.996 | ratio | assumed | 8.08641e-05 |
| sensitivity_point | pad_count:112 | good_packages_per_wafer | 4819.720 | ratio | assumed | 0.616291 |
| sensitivity_point | pad_count:112 | cost_per_good_package_usd | 2.54444 | USD | assumed | 0.000289749 |
| sensitivity_point | pad_count:178 | pad_count | 178.000 | ratio | assumed | not estimated |
| sensitivity_point | pad_count:178 | die_yield | 0.996 | ratio | assumed | 7.98756e-05 |
| sensitivity_point | pad_count:178 | good_packages_per_wafer | 4816.340 | ratio | assumed | 0.604231 |
| sensitivity_point | pad_count:178 | cost_per_good_package_usd | 2.54613 | USD | assumed | 0.00028343 |
| sensitivity_point | pad_count:220 | pad_count | 220.000 | ratio | assumed | not estimated |
| sensitivity_point | pad_count:220 | die_yield | 0.996 | ratio | assumed | 8.76166e-05 |
| sensitivity_point | pad_count:220 | good_packages_per_wafer | 4814.630 | ratio | assumed | 0.808122 |
| sensitivity_point | pad_count:220 | cost_per_good_package_usd | 2.54711 | USD | assumed | 0.000368596 |
| sensitivity_point | assembly_tolerance:2 | assembly_per_pad_ppm | 2 | ppm | assumed | not estimated |
| sensitivity_point | assembly_tolerance:2 | die_yield | 0.996 | ratio | assumed | 0.000104385 |
| sensitivity_point | assembly_tolerance:2 | good_packages_per_wafer | 4822.270 | ratio | assumed | 0.738529 |
| sensitivity_point | assembly_tolerance:2 | cost_per_good_package_usd | 2.54307 | USD | assumed | 0.000305651 |
| sensitivity_point | assembly_tolerance:5 | assembly_per_pad_ppm | 5 | ppm | assumed | not estimated |
| sensitivity_point | assembly_tolerance:5 | die_yield | 0.996 | ratio | assumed | 8.43324e-05 |
| sensitivity_point | assembly_tolerance:5 | good_packages_per_wafer | 4818.440 | ratio | assumed | 0.695341 |
| sensitivity_point | assembly_tolerance:5 | cost_per_good_package_usd | 2.54498 | USD | assumed | 0.000314225 |
| sensitivity_point | assembly_tolerance:8 | assembly_per_pad_ppm | 8 | ppm | assumed | not estimated |
| sensitivity_point | assembly_tolerance:8 | die_yield | 0.996 | ratio | assumed | 9.91737e-05 |
| sensitivity_point | assembly_tolerance:8 | good_packages_per_wafer | 4816.980 | ratio | assumed | 0.735668 |
| sensitivity_point | assembly_tolerance:8 | cost_per_good_package_usd | 2.54574 | USD | assumed | 0.000325333 |
| sensitivity_point | assembly_tolerance:12 | assembly_per_pad_ppm | 12 | ppm | assumed | not estimated |
| sensitivity_point | assembly_tolerance:12 | die_yield | 0.996 | ratio | assumed | 8.09604e-05 |
| sensitivity_point | assembly_tolerance:12 | good_packages_per_wafer | 4812.380 | ratio | assumed | 0.743155 |
| sensitivity_point | assembly_tolerance:12 | cost_per_good_package_usd | 2.54809 | USD | assumed | 0.000349831 |
| sensitivity_point | assembly_tolerance:20 | assembly_per_pad_ppm | 20 | ppm | assumed | not estimated |
| sensitivity_point | assembly_tolerance:20 | die_yield | 0.996 | ratio | assumed | 8.58886e-05 |
| sensitivity_point | assembly_tolerance:20 | good_packages_per_wafer | 4805.010 | ratio | assumed | 0.832241 |
| sensitivity_point | assembly_tolerance:20 | cost_per_good_package_usd | 2.55203 | USD | assumed | 0.000392006 |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| assumed | 56 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/grx930_yield_sensitivity_28nm.yaml` | `7c3d2c2a5e4d569c...` | 792 |
| yield | `yields/grx930_28nm.yaml` | `3ebfeb60d2096a28...` | 2279 |
| chip | `chips/grx930.yaml` | `3d2a312cd4196c52...` | 4763 |
| tech | `tech/grx28.yaml` | `fec22f0374bcdbf8...` | 5982 |

## Reproduce

```bash
python -m fabtwin run scenarios/grx930_yield_sensitivity_28nm.yaml --out /tmp/fabtwin-site-jjg9y_2q
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-jjg9y_2q/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-jjg9y_2q/fabtwin.db --run grx930_yield_sensitivity_28nm-20261107T043409Z-97332ece
```

Artifacts: [observations.csv](observations.csv) · [run.json](run.json)

## Caveats

- Yield sensitivity is an F1 planning exercise, not a foundry process corner.
- Curve points share model assumptions; they do not represent independent measured wafers.
- Monte Carlo reports sampling uncertainty, not model calibration uncertainty.

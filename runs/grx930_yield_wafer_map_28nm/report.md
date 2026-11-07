# fabtwin run `grx930_yield_wafer_map_28nm-20261107T143637Z-da61d3e0`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `grx930_yield_wafer_map_28nm` |
| Description | Sample GRX930 die yield, edge-to-center yield ratio, radial yield slope and zone-level defect density under a planning radial, angular and clustered defect profile. |
| Product | `grx930` |
| Process | `grx28@0.1.0` |
| Seed | 20261106 |
| Samples | 200 |
| Engines | `yield_wafer_map` |
| Outputs | `die_yield_mean`, `center_die_yield`, `edge_die_yield`, `edge_to_center_yield_ratio`, `radial_yield_slope_per_mm`, `assembly_yield`, `good_packages_per_wafer`, `cost_per_good_package_usd` |
| Scenario SHA-256 | `225ba8bd71d939ae...` |
| Yield model | `yields/grx930_28nm.yaml` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| yield_wafer_map | 0.1.0 | F1 | yield-assumptions@0.2.0 | GRX930 | GRX28 0.1.0 |

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
| wafer_map | grx930 | die_yield_mean | 0.993 | ratio | assumed | 8.46626e-05 |
| wafer_map | grx930 | center_die_yield | 0.996 | ratio | assumed | not estimated |
| wafer_map | grx930 | edge_die_yield | 0.991 | ratio | assumed | not estimated |
| wafer_map | grx930 | edge_to_center_yield_ratio | 0.995 | ratio | assumed | not estimated |
| wafer_map | grx930 | radial_yield_slope_per_mm | -5.64195e-05 | 1/mm | assumed | not estimated |
| wafer_map | grx930 | assembly_yield | 0.994 | ratio | assumed | not estimated |
| wafer_map | grx930 | good_packages_per_wafer | 4800.935 | ratio | assumed | 0.608114 |
| wafer_map | grx930 | cost_per_good_package_usd | 2.5503 | USD | assumed | 0.000248477 |
| wafer_zone | zone:0 | defect_density_per_cm2 | 0.080542 | 1/cm2 | assumed | not estimated |
| wafer_zone | zone:0 | die_yield | 0.996 | ratio | assumed | not estimated |
| wafer_zone | zone:0 | die_count | 193.000 | ratio | assumed | not estimated |
| wafer_zone | zone:0 | radius_mm | 14.7 | mm | assumed | not estimated |
| wafer_zone | zone:1 | defect_density_per_cm2 | 0.0869833 | 1/cm2 | assumed | not estimated |
| wafer_zone | zone:1 | die_yield | 0.996 | ratio | assumed | not estimated |
| wafer_zone | zone:1 | die_count | 600.000 | ratio | assumed | not estimated |
| wafer_zone | zone:1 | radius_mm | 44.1 | mm | assumed | not estimated |
| wafer_zone | zone:2 | defect_density_per_cm2 | 0.112301 | 1/cm2 | assumed | not estimated |
| wafer_zone | zone:2 | die_yield | 0.995 | ratio | assumed | not estimated |
| wafer_zone | zone:2 | die_count | 996.000 | ratio | assumed | not estimated |
| wafer_zone | zone:2 | radius_mm | 73.5 | mm | assumed | not estimated |
| wafer_zone | zone:3 | defect_density_per_cm2 | 0.148422 | 1/cm2 | assumed | not estimated |
| wafer_zone | zone:3 | die_yield | 0.993 | ratio | assumed | not estimated |
| wafer_zone | zone:3 | die_count | 1408.000 | ratio | assumed | not estimated |
| wafer_zone | zone:3 | radius_mm | 102.9 | mm | assumed | not estimated |
| wafer_zone | zone:4 | defect_density_per_cm2 | 0.19774 | 1/cm2 | assumed | not estimated |
| wafer_zone | zone:4 | die_yield | 0.991 | ratio | assumed | not estimated |
| wafer_zone | zone:4 | die_count | 1668.000 | ratio | assumed | not estimated |
| wafer_zone | zone:4 | radius_mm | 132.3 | mm | assumed | not estimated |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| assumed | 28 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/grx930_yield_wafer_map_28nm.yaml` | `225ba8bd71d939ae...` | 792 |
| yield | `yields/grx930_28nm.yaml` | `3ebfeb60d2096a28...` | 2279 |
| chip | `chips/grx930.yaml` | `3d2a312cd4196c52...` | 4763 |
| tech | `tech/grx28.yaml` | `fec22f0374bcdbf8...` | 5982 |

## Reproduce

```bash
python -m fabtwin run scenarios/grx930_yield_wafer_map_28nm.yaml --out /tmp/fabtwin-site-ar9ksehj
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-ar9ksehj/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-ar9ksehj/fabtwin.db --run grx930_yield_wafer_map_28nm-20261107T143637Z-da61d3e0
```

Artifacts: [observations.csv](observations.csv) · [wafer_map.csv](wafer_map.csv) · [wafer_map.svg](wafer_map.svg) · [run.json](run.json)

## Caveats

- Wafer map is an F1 planning profile, not a measured wafer map.
- The radial, angular and cluster density terms are planning assumptions; they are not a measured wafer signature.
- Zone yields use modelled expected yield; the wafer mean and package counts include sampling noise.

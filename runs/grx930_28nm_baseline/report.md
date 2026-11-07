# fabtwin run `grx930_28nm_baseline-20261107T043408Z-ad329cf8`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `grx930_28nm_baseline` |
| Description | Reproduce the GRX930 measured-baseline projection and the four-point DTCO ladder from the existing gpdk model, with measured and modelled evidence kept in separate observation rows. |
| Product | `grx930` |
| Process | `grx28@0.1.0` |
| Seed | 20261105 |
| Samples | 1 |
| Engines | `gpdk` |
| Outputs | `as_built_die_area_m2`, `as_built_content_area_m2`, `as_built_clock_frequency_hz`, `die_area_m2`, `content_area_m2`, `pad_floor_area_m2`, `native_frequency_hz`, `power_at_target_w`, `power_density_at_target_w_per_m2` |
| Scenario SHA-256 | `9a7bbfb08433969b...` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| gpdk | 0.1.0 | F0 | gpdk@0.1.0 | GRX930 | GRX28 0.1.0 |

### Design points

| Engine | Key | Label | Library | Tracks | Die binding | Best |
|---|---|---|---|---|---|---|
| gpdk | node9t | GRX28 9T / 1-finger | grx28_9t_1f | 9T | pad ring |  |
| gpdk | track7t5 | + 7.5T track shrink | grx28_7t5_1f | 7.5T | pad ring |  |
| gpdk | mbff | + multibit flip-flops | grx28_7t5_1f | 7.5T | pad ring |  |
| gpdk | pin_aware | + pin-density-aware placement | grx28_7t5_1f | 7.5T | pad ring | yes |

## Observations

Values in `observations.csv` are base SI. This table converts area to mm2,
frequency to MHz/GHz, and power to mW/W for readability. A blank uncertainty in
the CSV, or "not estimated" here, means it was not estimated, not that the
value is exact.

| Entity type | Entity | Metric | Value | Unit | Evidence | Uncertainty |
|---|---|---|---|---|---|---|
| product | grx930 | as_built_die_area_m2 | 165.000 | mm2 | measured | not estimated |
| product | grx930 | as_built_content_area_m2 | 86.400 | mm2 | measured | not estimated |
| product | grx930 | as_built_clock_frequency_hz | 25.000 | MHz | measured | not estimated |
| design_point | grx930:node9t | die_area_m2 | 12.992 | mm2 | assumed | not estimated |
| design_point | grx930:node9t | content_area_m2 | 0.880 | mm2 | assumed | not estimated |
| design_point | grx930:node9t | pad_floor_area_m2 | 12.992 | mm2 | assumed | not estimated |
| design_point | grx930:node9t | native_frequency_hz | 1.935 | GHz | assumed | not estimated |
| design_point | grx930:node9t | power_at_target_w | 5.489 | mW | assumed | not estimated |
| design_point | grx930:node9t | power_density_at_target_w_per_m2 | 0.0062 | W/mm2 | assumed | not estimated |
| design_point | grx930:track7t5 | die_area_m2 | 12.992 | mm2 | assumed | not estimated |
| design_point | grx930:track7t5 | content_area_m2 | 0.820 | mm2 | assumed | not estimated |
| design_point | grx930:track7t5 | pad_floor_area_m2 | 12.992 | mm2 | assumed | not estimated |
| design_point | grx930:track7t5 | native_frequency_hz | 1.941 | GHz | assumed | not estimated |
| design_point | grx930:track7t5 | power_at_target_w | 5.480 | mW | assumed | not estimated |
| design_point | grx930:track7t5 | power_density_at_target_w_per_m2 | 0.0067 | W/mm2 | assumed | not estimated |
| design_point | grx930:mbff | die_area_m2 | 12.992 | mm2 | assumed | not estimated |
| design_point | grx930:mbff | content_area_m2 | 0.822 | mm2 | assumed | not estimated |
| design_point | grx930:mbff | pad_floor_area_m2 | 12.992 | mm2 | assumed | not estimated |
| design_point | grx930:mbff | native_frequency_hz | 1.941 | GHz | assumed | not estimated |
| design_point | grx930:mbff | power_at_target_w | 5.236 | mW | assumed | not estimated |
| design_point | grx930:mbff | power_density_at_target_w_per_m2 | 0.0064 | W/mm2 | assumed | not estimated |
| design_point | grx930:pin_aware | die_area_m2 | 12.992 | mm2 | assumed | not estimated |
| design_point | grx930:pin_aware | content_area_m2 | 0.801 | mm2 | assumed | not estimated |
| design_point | grx930:pin_aware | pad_floor_area_m2 | 12.992 | mm2 | assumed | not estimated |
| design_point | grx930:pin_aware | native_frequency_hz | 1.943 | GHz | assumed | not estimated |
| design_point | grx930:pin_aware | power_at_target_w | 5.233 | mW | assumed | not estimated |
| design_point | grx930:pin_aware | power_density_at_target_w_per_m2 | 0.0065 | W/mm2 | assumed | not estimated |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| measured | 3 | silicon, PCM, metrology, or a qualified test structure |
| assumed | 24 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/grx930_28nm_baseline.yaml` | `9a7bbfb08433969b...` | 865 |
| chip | `chips/grx930.yaml` | `3d2a312cd4196c52...` | 4763 |
| tech | `tech/grx28.yaml` | `fec22f0374bcdbf8...` | 5982 |

## Reproduce

```bash
python -m fabtwin run scenarios/grx930_28nm_baseline.yaml --out /tmp/fabtwin-site-jjg9y_2q
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-jjg9y_2q/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-jjg9y_2q/fabtwin.db --run grx930_28nm_baseline-20261107T043408Z-ad329cf8
```

Artifacts: [observations.csv](observations.csv) · [run.json](run.json)

## Caveats

- gpdk is an uncalibrated F0 analytical model; these are scenario estimates, not silicon predictions.
- Uncertainty is not estimated in Phase 0; the uncertainty column is intentionally blank.
- The as-built rows are measured source data, not model outputs.

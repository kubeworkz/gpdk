# fabtwin run `g100_28nm_baseline-20261107T043407Z-de0897c9`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `g100_28nm_baseline` |
| Description | Reproduce the G100 digital block projection from the pre-split planning profile, with every projected value marked as an assumption. |
| Product | `g100` |
| Process | `grx28@0.1.0` |
| Seed | 20261105 |
| Samples | 1 |
| Engines | `gpdk` |
| Outputs | `cell_area_m2`, `content_area_m2`, `die_area_m2`, `native_frequency_hz`, `pad_floor_area_m2`, `power_at_target_w`, `power_density_at_target_w_per_m2`, `power_w`, `sram_area_m2`, `util` |
| Scenario SHA-256 | `15ebff8492f7617b...` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| gpdk | 0.1.0 | F0 | gpdk@0.1.0 | G100 | GRX28 0.1.0 |

### Design points

| Engine | Key | Label | Library | Tracks | Die binding | Best |
|---|---|---|---|---|---|---|
| gpdk | node9t | GRX28 9T / 1-finger | grx28_9t_1f | 9T | logic utilisation |  |
| gpdk | track7t5 | + 7.5T track shrink | grx28_7t5_1f | 7.5T | logic utilisation |  |
| gpdk | mbff | + multibit flip-flops | grx28_7t5_1f | 7.5T | logic utilisation |  |
| gpdk | pin_aware | + pin-density-aware placement | grx28_7t5_1f | 7.5T | logic utilisation | yes |

## Observations

Values in `observations.csv` are base SI. This table converts area to mm2,
frequency to MHz/GHz, and power to mW/W for readability. A blank uncertainty in
the CSV, or "not estimated" here, means it was not estimated, not that the
value is exact.

| Entity type | Entity | Metric | Value | Unit | Evidence | Uncertainty |
|---|---|---|---|---|---|---|
| design_point | g100:node9t | cell_area_m2 | 246.821 | mm2 | assumed | not estimated |
| design_point | g100:node9t | content_area_m2 | 411.926 | mm2 | assumed | not estimated |
| design_point | g100:node9t | die_area_m2 | 411.926 | mm2 | assumed | not estimated |
| design_point | g100:node9t | native_frequency_hz | 1.016 | GHz | assumed | not estimated |
| design_point | g100:node9t | pad_floor_area_m2 | 0.000 | mm2 | assumed | not estimated |
| design_point | g100:node9t | power_at_target_w | 126.875 | W | assumed | not estimated |
| design_point | g100:node9t | power_density_at_target_w_per_m2 | 0.3080 | W/mm2 | assumed | not estimated |
| design_point | g100:node9t | power_w | 171.131 | W | assumed | not estimated |
| design_point | g100:node9t | sram_area_m2 | 75.497 | mm2 | assumed | not estimated |
| design_point | g100:node9t | util | 0.752 | ratio | assumed | not estimated |
| design_point | g100:track7t5 | cell_area_m2 | 205.684 | mm2 | assumed | not estimated |
| design_point | g100:track7t5 | content_area_m2 | 384.904 | mm2 | assumed | not estimated |
| design_point | g100:track7t5 | die_area_m2 | 384.904 | mm2 | assumed | not estimated |
| design_point | g100:track7t5 | native_frequency_hz | 1.037 | GHz | assumed | not estimated |
| design_point | g100:track7t5 | pad_floor_area_m2 | 0.000 | mm2 | assumed | not estimated |
| design_point | g100:track7t5 | power_at_target_w | 123.127 | W | assumed | not estimated |
| design_point | g100:track7t5 | power_density_at_target_w_per_m2 | 0.3199 | W/mm2 | assumed | not estimated |
| design_point | g100:track7t5 | power_w | 169.43 | W | assumed | not estimated |
| design_point | g100:track7t5 | sram_area_m2 | 75.497 | mm2 | assumed | not estimated |
| design_point | g100:track7t5 | util | 0.682 | ratio | assumed | not estimated |
| design_point | g100:mbff | cell_area_m2 | 201.254 | mm2 | assumed | not estimated |
| design_point | g100:mbff | content_area_m2 | 387.534 | mm2 | assumed | not estimated |
| design_point | g100:mbff | die_area_m2 | 387.534 | mm2 | assumed | not estimated |
| design_point | g100:mbff | native_frequency_hz | 1.035 | GHz | assumed | not estimated |
| design_point | g100:mbff | pad_floor_area_m2 | 0.000 | mm2 | assumed | not estimated |
| design_point | g100:mbff | power_at_target_w | 118.14 | W | assumed | not estimated |
| design_point | g100:mbff | power_density_at_target_w_per_m2 | 0.3049 | W/mm2 | assumed | not estimated |
| design_point | g100:mbff | power_w | 162.212 | W | assumed | not estimated |
| design_point | g100:mbff | sram_area_m2 | 75.497 | mm2 | assumed | not estimated |
| design_point | g100:mbff | util | 0.662 | ratio | assumed | not estimated |
| design_point | g100:pin_aware | cell_area_m2 | 201.254 | mm2 | assumed | not estimated |
| design_point | g100:pin_aware | content_area_m2 | 378.317 | mm2 | assumed | not estimated |
| design_point | g100:pin_aware | die_area_m2 | 378.317 | mm2 | assumed | not estimated |
| design_point | g100:pin_aware | native_frequency_hz | 1.042 | GHz | assumed | not estimated |
| design_point | g100:pin_aware | pad_floor_area_m2 | 0.000 | mm2 | assumed | not estimated |
| design_point | g100:pin_aware | power_at_target_w | 116.829 | W | assumed | not estimated |
| design_point | g100:pin_aware | power_density_at_target_w_per_m2 | 0.3088 | W/mm2 | assumed | not estimated |
| design_point | g100:pin_aware | power_w | 161.548 | W | assumed | not estimated |
| design_point | g100:pin_aware | sram_area_m2 | 75.497 | mm2 | assumed | not estimated |
| design_point | g100:pin_aware | util | 0.683 | ratio | assumed | not estimated |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| assumed | 40 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/g100_28nm_baseline.yaml` | `15ebff8492f7617b...` | 761 |
| chip | `chips/g100.yaml` | `b9e127cb2fa42f08...` | 1016 |
| tech | `tech/grx28.yaml` | `fec22f0374bcdbf8...` | 5982 |

## Reproduce

```bash
python -m fabtwin run scenarios/g100_28nm_baseline.yaml --out /tmp/fabtwin-site-jjg9y_2q
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-jjg9y_2q/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-jjg9y_2q/fabtwin.db --run g100_28nm_baseline-20261107T043407Z-de0897c9
```

Artifacts: [observations.csv](observations.csv) · [run.json](run.json)

## Caveats

- gpdk is an uncalibrated F0 analytical model; these are scenario estimates, not silicon predictions.
- Uncertainty is not estimated in Phase 0; the uncertainty column is intentionally blank.

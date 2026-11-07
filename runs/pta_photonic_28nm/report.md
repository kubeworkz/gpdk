# fabtwin run `pta_photonic_28nm-20261107T043410Z-3b0cbf38`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `pta_photonic_28nm` |
| Description | Propagate PTA waveguide width, etch depth, line-edge roughness, temperature and package alignment through an F1 optical and one-dimensional thermal model to insertion loss, phase error, tuning power and tensor error, then rank the dominant contributors. |
| Product | `pta` |
| Process | `grx28@0.1.0` |
| Seed | 20261106 |
| Samples | 400 |
| Engines | `pta_photonic` |
| Outputs | `insertion_loss_db`, `phase_error_rad`, `tuning_power_w`, `tensor_error`, `temperature_rise_k` |
| Scenario SHA-256 | `d38643e42fbe7940...` |
| Package | `packages/mcm_si.yaml` |
| Photonic model | `photonic/pta_siph_28nm.yaml` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| pta_photonic | 0.1.0 | F1 | pta-photonic@0.1.0 | PTA | GRX28 0.1.0 |

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
| product | pta | insertion_loss_db | 3.20501 | dB | assumed | 0.035835 |
| product | pta | phase_error_rad | 1.62458 | rad | assumed | 0.0565315 |
| product | pta | tuning_power_w | 82.739 | mW | assumed | 2.87913 |
| product | pta | tensor_error | 0.517 | ratio | assumed | 0.0179945 |
| product | pta | temperature_rise_k | 6.2662 | K | assumed | 0.240346 |
| sensitivity | width_nm | phase_error_swing | 1.2161 | rad | assumed | not estimated |
| sensitivity | width_nm | insertion_loss_swing | 0 | dB | assumed | not estimated |
| sensitivity | etch_depth_nm | phase_error_swing | 1.01342 | rad | assumed | not estimated |
| sensitivity | etch_depth_nm | insertion_loss_swing | 0 | dB | assumed | not estimated |
| sensitivity | ler_nm | phase_error_swing | 0 | rad | assumed | not estimated |
| sensitivity | ler_nm | insertion_loss_swing | 0.0903 | dB | assumed | not estimated |
| sensitivity | alignment_um | phase_error_swing | 0 | rad | assumed | not estimated |
| sensitivity | alignment_um | insertion_loss_swing | 0.45 | dB | assumed | not estimated |
| sensitivity | ambient_c | phase_error_swing | 0.125948 | rad | assumed | not estimated |
| sensitivity | ambient_c | insertion_loss_swing | 0 | dB | assumed | not estimated |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| assumed | 15 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/pta_photonic_28nm.yaml` | `d38643e42fbe7940...` | 842 |
| package | `packages/mcm_si.yaml` | `66e840836c5a2d12...` | 1263 |
| photonic | `photonic/pta_siph_28nm.yaml` | `8d896882a544ac8e...` | 1776 |
| chip | `chips/pta.yaml` | `c80fbe2fe91def53...` | 1286 |
| tech | `tech/grx28.yaml` | `fec22f0374bcdbf8...` | 5982 |

## Reproduce

```bash
python -m fabtwin run scenarios/pta_photonic_28nm.yaml --out /tmp/fabtwin-site-jjg9y_2q
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-jjg9y_2q/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-jjg9y_2q/fabtwin.db --run pta_photonic_28nm-20261107T043410Z-3b0cbf38
```

Artifacts: [observations.csv](observations.csv) · [run.json](run.json)

## Caveats

- PTA photonic/thermal results are F1 planning estimates, not measured or calibrated PTA performance.
- Phase error is a per-MZI analytical estimate without common-mode cancellation or tuning feedback; tensor error is phase error divided by pi, a stated proxy, not a measured inference error.
- The thermal path is a one-dimensional silicon-interposer approximation that omits TIM, bump and die-level interface resistances; it is not full-chip thermal FEA and its absolute temperature rise is optimistic.

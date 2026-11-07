# fabtwin run `g100_mcm_28nm-20261107T043408Z-625660d8`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `g100_mcm_28nm` |
| Description | Combine G100 Poisson die yield with PTA known-good-die supply, matched-pair KGD yield and three package assembly options, then compare good packages per G100 wafer and cost per good package. |
| Product | `g100` |
| Process | `grx28@0.1.0` |
| Seed | 20261106 |
| Samples | 1 |
| Engines | `mcm_yield` |
| Outputs | `g100_die_area_m2`, `g100_die_yield`, `g100_known_good_dies_per_wafer`, `pta_die_area_m2`, `pta_die_yield`, `pta_known_good_dies_per_wafer`, `kgd_match_yield`, `pta_wafers_per_g100_wafer`, `assembly_yield`, `good_packages_per_g100_wafer`, `cost_per_good_package_usd` |
| Scenario SHA-256 | `2da3dfad86c62d92...` |
| Package | `packages/mcm_si.yaml` |
| Yield model | `yields/g100_mcm_28nm.yaml` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| mcm_yield | 0.1.0 | F1 | mcm-yield@0.1.0 | G100 | GRX28 0.1.0 |

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
| product | g100 | g100_die_area_m2 | 378.317 | mm2 | assumed | not estimated |
| product | g100 | g100_die_yield | 0.899 | ratio | assumed | not estimated |
| product | g100 | g100_known_good_dies_per_wafer | 133.354 | ratio | assumed | not estimated |
| product | pta | pta_die_area_m2 | 50.000 | mm2 | assumed | not estimated |
| product | pta | pta_die_yield | 0.980 | ratio | assumed | not estimated |
| product | pta | pta_known_good_dies_per_wafer | 1219.789 | ratio | assumed | not estimated |
| product | mcm | kgd_match_yield | 0.868 | ratio | assumed | not estimated |
| product | mcm | pta_wafers_per_g100_wafer | 0.109 | ratio | assumed | not estimated |
| package_option | silicon_interposer | assembly_yield | 0.987 | ratio | assumed | not estimated |
| package_option | organic_substrate | assembly_yield | 0.977 | ratio | assumed | not estimated |
| package_option | silicon_bridge | assembly_yield | 0.985 | ratio | assumed | not estimated |
| package_option | silicon_interposer | good_packages_per_g100_wafer | 131.630 | ratio | assumed | not estimated |
| package_option | organic_substrate | good_packages_per_g100_wafer | 130.317 | ratio | assumed | not estimated |
| package_option | silicon_bridge | good_packages_per_g100_wafer | 131.366 | ratio | assumed | not estimated |
| package_option | silicon_interposer | cost_per_good_package_usd | 56.3521 | USD | assumed | not estimated |
| package_option | organic_substrate | cost_per_good_package_usd | 44.64 | USD | assumed | not estimated |
| package_option | silicon_bridge | cost_per_good_package_usd | 50.3744 | USD | assumed | not estimated |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| assumed | 17 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/g100_mcm_28nm.yaml` | `2da3dfad86c62d92...` | 802 |
| package | `packages/mcm_si.yaml` | `66e840836c5a2d12...` | 1263 |
| yield | `yields/g100_mcm_28nm.yaml` | `340be98f95ef0529...` | 1703 |
| chip | `chips/g100.yaml` | `b9e127cb2fa42f08...` | 1016 |
| tech | `tech/grx28.yaml` | `fec22f0374bcdbf8...` | 5982 |

## Reproduce

```bash
python -m fabtwin run scenarios/g100_mcm_28nm.yaml --out /tmp/fabtwin-site-jjg9y_2q
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-jjg9y_2q/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-jjg9y_2q/fabtwin.db --run g100_mcm_28nm-20261107T043408Z-625660d8
```

Artifacts: [observations.csv](observations.csv) · [run.json](run.json)

## Caveats

- Phase 3 MCM yield and package costs are F1 planning estimates, not measured OSAT data or vendor quotes.
- KGD matching assumes the test-yield factors in the assumptions file; test escapes and handling damage are not separately modelled.
- Package assembly, interconnect ppm and package costs are explicit assumptions; replace them with qualified package and assembly data before commitments.

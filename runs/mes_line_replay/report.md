# fabtwin run `mes_line_replay-20261107T043410Z-973dcab8`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `mes_line_replay` |
| Description | Replay a deterministic synthetic front-end and OSAT MES event log. Cycle time, queue time, WIP, throughput and tool utilization are derived from the verified event timestamps instead of the YAML factory assumptions. The log is a synthetic fixture and is not a G100 route card or measured line performance. |
| Product | `mes_line` |
| Process | `mes_fixture@0.1.0` |
| Seed | 20261106 |
| Samples | 1 |
| Engines | `factory_replay` |
| Outputs | `cycle_time_s`, `queue_time_s`, `wip_lots`, `peak_wip_lots`, `throughput_wafers_per_s`, `completed_lots`, `completed_wafers`, `open_lots`, `observation_window_s`, `step_queue_time_s`, `tool_utilization`, `tool_group_utilization` |
| Scenario SHA-256 | `afda9c865ee7105d...` |
| MES extract | `factory/mes_smoke/manifest.json` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| factory_replay | 0.1.0 | F1 | mes-replay@0.1.0 |  |  |

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
| factory_case | mes_replay | cycle_time_s | 33.81 | h | assumed | not estimated |
| factory_case | mes_replay | queue_time_s | 2.30 | h | assumed | not estimated |
| factory_case | mes_replay | wip_lots | 0.610995 | lot | assumed | not estimated |
| factory_case | mes_replay | peak_wip_lots | 3 | lot | assumed | not estimated |
| factory_case | mes_replay | throughput_wafers_per_s | 58.333 | 1/week | assumed | not estimated |
| factory_case | mes_replay | completed_lots | 3 | lot | assumed | not estimated |
| factory_case | mes_replay | completed_wafers | 50 | wafer | assumed | not estimated |
| factory_case | mes_replay | open_lots | 0 | lot | assumed | not estimated |
| factory_case | mes_replay | observation_window_s | 144.00 | h | assumed | not estimated |
| route_step | mes_replay:ANNEAL_1 | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:CMP_1 | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:DEPOSITION_1 | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:DIE_ATTACH | step_queue_time_s | 1800 | s | assumed | not estimated |
| route_step | mes_replay:ETCH_1 | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:ETCH_2 | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:ETCH_3 | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:FINAL_TEST | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:IMPLANT_1 | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:LITHO_1 | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:LITHO_2 | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:LITHO_3 | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:METROLOGY_CD | step_queue_time_s | 1.07 | h | assumed | not estimated |
| route_step | mes_replay:MOLD | step_queue_time_s | 2040 | s | assumed | not estimated |
| route_step | mes_replay:OXIDE_GROW | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:WAFER_SORT | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | mes_replay:WIRE_BOND | step_queue_time_s | 0 | s | assumed | not estimated |
| tool | CMP_01 | tool_utilization | 0.006 | ratio | assumed | not estimated |
| tool | DA_01 | tool_utilization | 0.023 | ratio | assumed | not estimated |
| tool | DEP_01 | tool_utilization | 0.017 | ratio | assumed | not estimated |
| tool | ETCH_01 | tool_utilization | 0.015 | ratio | assumed | not estimated |
| tool | ETCH_02 | tool_utilization | 0.012 | ratio | assumed | not estimated |
| tool | FURN_A_01 | tool_utilization | 0.023 | ratio | assumed | not estimated |
| tool | FURN_A_02 | tool_utilization | 0.019 | ratio | assumed | not estimated |
| tool | IMPLANT_01 | tool_utilization | 0.017 | ratio | assumed | not estimated |
| tool | LITHO_01 | tool_utilization | 0.021 | ratio | assumed | not estimated |
| tool | LITHO_02 | tool_utilization | 0.014 | ratio | assumed | not estimated |
| tool | METRO_01 | tool_utilization | 0.003 | ratio | assumed | not estimated |
| tool | MOLD_01 | tool_utilization | 0.027 | ratio | assumed | not estimated |
| tool | SORT_01 | tool_utilization | 0.008 | ratio | assumed | not estimated |
| tool | TEST_01 | tool_utilization | 0.014 | ratio | assumed | not estimated |
| tool | WB_01 | tool_utilization | 0.010 | ratio | assumed | not estimated |
| tool | WB_02 | tool_utilization | 0.009 | ratio | assumed | not estimated |
| tool_group | CMP_CELL | tool_group_utilization | 0.006 | ratio | assumed | not estimated |
| tool_group | DEP_CELL | tool_group_utilization | 0.017 | ratio | assumed | not estimated |
| tool_group | DIE_ATTACH_CELL | tool_group_utilization | 0.023 | ratio | assumed | not estimated |
| tool_group | ETCH_CELL | tool_group_utilization | 0.013 | ratio | assumed | not estimated |
| tool_group | FURNACE_A | tool_group_utilization | 0.021 | ratio | assumed | not estimated |
| tool_group | IMPLANT_CELL | tool_group_utilization | 0.017 | ratio | assumed | not estimated |
| tool_group | LITHO_CELL | tool_group_utilization | 0.017 | ratio | assumed | not estimated |
| tool_group | METRO_CELL | tool_group_utilization | 0.003 | ratio | assumed | not estimated |
| tool_group | MOLD_CELL | tool_group_utilization | 0.027 | ratio | assumed | not estimated |
| tool_group | SORT_CELL | tool_group_utilization | 0.008 | ratio | assumed | not estimated |
| tool_group | TEST_CELL | tool_group_utilization | 0.014 | ratio | assumed | not estimated |
| tool_group | WIRE_BOND_CELL | tool_group_utilization | 0.009 | ratio | assumed | not estimated |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| assumed | 54 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/mes_line_replay.yaml` | `afda9c865ee7105d...` | 920 |
| mes | `factory/mes_smoke/manifest.json` | `f175dab2b93593f9...` | 1006 |
| mes_route | `factory/mes_smoke/mes_route_events.csv` | `36af736ab9e90d93...` | 27988 |
| mes_equipment | `factory/mes_smoke/mes_equipment_events.csv` | `aae9016f01f2ce65...` | 19198 |

## Reproduce

```bash
python -m fabtwin run scenarios/mes_line_replay.yaml --out /tmp/fabtwin-site-jjg9y_2q
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-jjg9y_2q/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-jjg9y_2q/fabtwin.db --run mes_line_replay-20261107T043410Z-973dcab8
```

Artifacts: [observations.csv](observations.csv) · [run.json](run.json)

## Caveats

- MES replay reads event timestamps; it does not simulate dispatch, batching, failures or maintenance.
- Cycle time, queue time and WIP are descriptive statistics for the manifest window, not a forecast.
- The event log is synthetic (`assumed`); replay metrics describe generated events and are not measured line performance.

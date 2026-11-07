# fabtwin run `g100_factory_28nm-20261107T043407Z-a53074bd`

> **Scenario result, not silicon sign-off.** This report is generated from a
> versioned scenario and the recorded engine versions. It is not a foundry
> DRC/LVS/ERC/RCX/reliability sign-off and does not claim fabricated yield.

## Scenario

| Field | Value |
|---|---|
| Scenario | `g100_factory_28nm` |
| Description | Simulate the G100 28 nm fab and ATP route with finite tool groups, batching, setup and availability loss. Report cycle time, queue time, WIP, throughput, tool utilization, bottleneck step and fully loaded cost per good package for a baseline and two what-if cases. |
| Product | `g100` |
| Process | `grx28@0.1.0` |
| Seed | 20261106 |
| Samples | 1 |
| Engines | `factory_atp` |
| Outputs | `wafer_starts_per_s`, `cycle_time_s`, `queue_time_s`, `wip_lots`, `throughput_wafers_per_s`, `good_packages_per_s`, `cost_per_good_package_usd`, `tool_capex_usd`, `depreciation_usd_per_week`, `depreciation_per_good_package_usd`, `incremental_capex_usd`, `incremental_annual_cash_flow_usd`, `incremental_annual_net_income_usd`, `payback_years`, `roi`, `npv_usd`, `irr`, `step_queue_time_s`, `tool_utilization`, `bottleneck_step_queue_s`, `bottleneck_tool_utilization` |
| Scenario SHA-256 | `bd634af551b5f317...` |
| Package | `packages/mcm_si.yaml` |
| Yield model | `yields/g100_mcm_28nm.yaml` |
| Factory model | `factory/g100_28nm.yaml` |

## Engines

| Engine | Version | Fidelity | Model version | Chip | Technology |
|---|---|---|---|---|---|
| factory_atp | 0.1.0 | F1 | factory-atp@0.1.0 | G100 | GRX28 0.1.0 |

### Design points

| Engine | Key | Label | Library | Tracks | Die binding | Best |
|---|---|---|---|---|---|---|

## Factory cases

| Case | Starts/week | Cycle (h) | Δ cycle | Queue (h) | WIP (lots) | Throughput (wafers/week) | Good packages/week | Cost/package | Capex (Δ vs base) | Depreciation/week | Payback / ROI | Bottleneck tool group | Bottleneck step | Utilization |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 600 | 141.5 | +0.0% | 61.2 | 19.7 | 599 | 78784 | $95.60 | $180.0M | $0.69M | n/a | litho | via_litho | 75.9% |
| higher_starts | 800 | 299.7 | +111.7% | 219.3 | 51.9 | 730 | 96035 | $88.55 | $180.0M | $0.69M | n/a | litho | m1_litho | 97.0% |
| low_downtime | 600 | 139.0 | -1.8% | 61.0 | 19.3 | 602 | 79212 | $95.39 | $180.0M | $0.69M | n/a | litho | via_litho | 72.2% |
| extra_litho | 800 | 146.0 | +3.1% | 65.6 | 26.8 | 800 | 105247 | $89.07 | $240.0M (+60.0M) | $0.92M | 4.09 yr / 4.4% vs higher_starts | dep | silicide_dep | 90.3% |

Cycle time and queue time are simulated hours. Throughput is the steady-state completion rate between pipeline fill and drain. The change column compares cycle time with the baseline case. Cost/package includes straight-line depreciation for priced tool groups; capex is the total priced fleet and the parenthetical change is versus baseline. Payback uses incremental annual cash flow versus the case's ROI reference; ROI is incremental annual net income after depreciation divided by incremental capex. Both are n/a without a capex change or a price/margin input.

## Scanner discounted cash flow

| Case | Discount rate | Years | Incremental capex | Annual cash flow | Terminal value | NPV | IRR |
|---|---|---|---|---|---|---|---|
| extra_litho | 10.0% | 5 | $60.0M | +$14.67M | $12.0M | -$4.71M | 7.3% |

Cash-flow ramp is 60% / 80% / 100% / 100% / 100% of steady state; terminal value is 20% of incremental capex at the end of year 5. NPV discounts at the reported hurdle rate; IRR is the zero-NPV rate. No taxes, working capital, price erosion or replacement capex is modelled.

## Scanner discount-rate sensitivity

| Case | Discount rate | NPV | IRR |
|---|---|---|---|
| extra_litho | 5.0% | +$4.66M | 7.3% |
| extra_litho | 7.5% | -$0.29M | 7.3% |
| extra_litho | 10.0% | -$4.71M | 7.3% |
| extra_litho | 12.5% | -$8.65M | 7.3% |
| extra_litho | 15.0% | -$12.19M | 7.3% |

IRR is independent of the hurdle rate; NPV crosses zero at the IRR. The curve holds the base scanner cash flow, ramp and terminal value constant.

## Scanner terminal-value sensitivity

| Case | Terminal value | Value | NPV | IRR |
|---|---|---|---|---|
| extra_litho | 0% | $0.00M | -$12.16M | 2.3% |
| extra_litho | 10% | $6.00M | -$8.43M | 5.0% |
| extra_litho | 20% | $12.00M | -$4.71M | 7.3% |
| extra_litho | 30% | $18.00M | -$0.98M | 9.5% |
| extra_litho | 40% | $24.00M | +$2.75M | 11.4% |

The terminal value is a residual percentage of incremental capex at the end of year 5. The curve holds the base cash flow, ramp and hurdle rate constant.

## Scanner economics sensitivity

| Case | Basis | Price | Gross margin | Annual cash flow | Payback | ROI | NPV | IRR |
|---|---|---|---|---|---|---|---|---|
| extra_litho | Price | $70.00 | $13.65 | +$0.30M | 201.74 yr | -19.5% | -$51.58M | n/a |
| extra_litho | Price | $85.00 | $28.65 | +$7.48M | 8.02 yr | -7.5% | -$28.14M | n/a |
| extra_litho | Price | $100.00 | $43.65 | +$14.67M | 4.09 yr | 4.4% | -$4.71M | 7.3% |
| extra_litho | Price | $115.00 | $58.65 | +$21.85M | 2.75 yr | 16.4% | +$18.73M | 19.9% |
| extra_litho | Price | $130.00 | $73.65 | +$29.04M | 2.07 yr | 28.4% | +$42.17M | 31.2% |
| extra_litho | Margin | n/a | $20.00 | +$3.34M | 17.96 yr | -14.4% | -$41.65M | n/a |
| extra_litho | Margin | n/a | $40.00 | +$12.92M | 4.64 yr | 1.5% | -$10.41M | 4.0% |
| extra_litho | Margin | n/a | $60.00 | +$22.50M | 2.67 yr | 17.5% | +$20.84M | 21.0% |
| extra_litho | Margin | n/a | $80.00 | +$32.08M | 1.87 yr | 33.5% | +$52.09M | 35.7% |

Price points derive gross margin as price minus the Phase 3 package cost; margin points state contribution margin before factory operating cost. Payback uses incremental cash flow versus the scanner's ROI reference; ROI is after depreciation. NPV and IRR use the scanner ramp and terminal value assumptions; the sweep is one-at-a-time and is not a demand or price forecast.

## Observations

Values in `observations.csv` are base SI. This table converts area to mm2,
frequency to MHz/GHz, and power to mW/W for readability. A blank uncertainty in
the CSV, or "not estimated" here, means it was not estimated, not that the
value is exact.

| Entity type | Entity | Metric | Value | Unit | Evidence | Uncertainty |
|---|---|---|---|---|---|---|
| factory_case | baseline | wafer_starts_per_s | 600.000 | 1/week | assumed | not estimated |
| factory_case | baseline | cycle_time_s | 141.54 | h | assumed | not estimated |
| factory_case | baseline | queue_time_s | 61.18 | h | assumed | not estimated |
| factory_case | baseline | wip_lots | 19.6713 | lot | assumed | not estimated |
| factory_case | baseline | throughput_wafers_per_s | 598.531 | 1/week | assumed | not estimated |
| factory_case | baseline | good_packages_per_s | 78784.404 | 1/week | assumed | not estimated |
| factory_case | baseline | cost_per_good_package_usd | 95.6023 | USD | assumed | not estimated |
| factory_case | baseline | tool_capex_usd | 1.8e+08 | USD | assumed | not estimated |
| factory_case | baseline | depreciation_usd_per_week | 692308 | USD/week | assumed | not estimated |
| factory_case | baseline | depreciation_per_good_package_usd | 8.78737 | USD | assumed | not estimated |
| factory_case | baseline | bottleneck_step_queue_s | 1824.26 | s | assumed | not estimated |
| factory_case | baseline | bottleneck_tool_utilization | 0.759 | ratio | assumed | not estimated |
| route_step | baseline:contact_etch | step_queue_time_s | 395.239 | s | assumed | not estimated |
| route_step | baseline:contact_litho | step_queue_time_s | 619.03 | s | assumed | not estimated |
| route_step | baseline:dice | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | baseline:die_attach | step_queue_time_s | 6.00 | h | assumed | not estimated |
| route_step | baseline:extension_implant | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | baseline:final_test | step_queue_time_s | 8.00 | h | assumed | not estimated |
| route_step | baseline:gate_etch | step_queue_time_s | 567.973 | s | assumed | not estimated |
| route_step | baseline:gate_litho | step_queue_time_s | 1105.55 | s | assumed | not estimated |
| route_step | baseline:gate_oxide | step_queue_time_s | 5.02 | h | assumed | not estimated |
| route_step | baseline:inline_metrology_1 | step_queue_time_s | 3.13 | h | assumed | not estimated |
| route_step | baseline:inline_metrology_2 | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | baseline:inline_metrology_3 | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | baseline:liner_dep | step_queue_time_s | 1251.98 | s | assumed | not estimated |
| route_step | baseline:m1_cmp | step_queue_time_s | 9.36608 | s | assumed | not estimated |
| route_step | baseline:m1_dep | step_queue_time_s | 2081.34 | s | assumed | not estimated |
| route_step | baseline:m1_etch | step_queue_time_s | 327.999 | s | assumed | not estimated |
| route_step | baseline:m1_litho | step_queue_time_s | 704.19 | s | assumed | not estimated |
| route_step | baseline:mold | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | baseline:pack_ship | step_queue_time_s | 1646.27 | s | assumed | not estimated |
| route_step | baseline:pad_etch | step_queue_time_s | 224.423 | s | assumed | not estimated |
| route_step | baseline:pad_litho | step_queue_time_s | 1274.96 | s | assumed | not estimated |
| route_step | baseline:passivation_dep | step_queue_time_s | 175.787 | s | assumed | not estimated |
| route_step | baseline:sd_anneal | step_queue_time_s | 7.75 | h | assumed | not estimated |
| route_step | baseline:sd_implant | step_queue_time_s | 13.2966 | s | assumed | not estimated |
| route_step | baseline:silicide_dep | step_queue_time_s | 996.567 | s | assumed | not estimated |
| route_step | baseline:spacer_dep | step_queue_time_s | 2317.36 | s | assumed | not estimated |
| route_step | baseline:spacer_etch | step_queue_time_s | 566.433 | s | assumed | not estimated |
| route_step | baseline:sti_cmp | step_queue_time_s | 36.3306 | s | assumed | not estimated |
| route_step | baseline:sti_etch | step_queue_time_s | 306.115 | s | assumed | not estimated |
| route_step | baseline:top_etch | step_queue_time_s | 96.1482 | s | assumed | not estimated |
| route_step | baseline:top_litho | step_queue_time_s | 292.349 | s | assumed | not estimated |
| route_step | baseline:underfill_cure | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | baseline:via_cmp | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | baseline:via_dep | step_queue_time_s | 2131.6 | s | assumed | not estimated |
| route_step | baseline:via_etch | step_queue_time_s | 23.4431 | s | assumed | not estimated |
| route_step | baseline:via_litho | step_queue_time_s | 1824.26 | s | assumed | not estimated |
| route_step | baseline:wafer_sort | step_queue_time_s | 6.00 | h | assumed | not estimated |
| route_step | baseline:well_implant | step_queue_time_s | 122.474 | s | assumed | not estimated |
| tool_group | baseline:cmp | tool_utilization | 0.349 | ratio | assumed | not estimated |
| tool_group | baseline:dep | tool_utilization | 0.679 | ratio | assumed | not estimated |
| tool_group | baseline:dice | tool_utilization | 0.053 | ratio | assumed | not estimated |
| tool_group | baseline:die_attach | tool_utilization | 0.141 | ratio | assumed | not estimated |
| tool_group | baseline:diffusion | tool_utilization | 0.467 | ratio | assumed | not estimated |
| tool_group | baseline:etch | tool_utilization | 0.661 | ratio | assumed | not estimated |
| tool_group | baseline:final_test | tool_utilization | 0.332 | ratio | assumed | not estimated |
| tool_group | baseline:implant | tool_utilization | 0.259 | ratio | assumed | not estimated |
| tool_group | baseline:litho | tool_utilization | 0.759 | ratio | assumed | not estimated |
| tool_group | baseline:metrology | tool_utilization | 0.058 | ratio | assumed | not estimated |
| tool_group | baseline:mold | tool_utilization | 0.081 | ratio | assumed | not estimated |
| tool_group | baseline:pack_ship | tool_utilization | 0.144 | ratio | assumed | not estimated |
| tool_group | baseline:underfill | tool_utilization | 0.060 | ratio | assumed | not estimated |
| tool_group | baseline:wafer_test | tool_utilization | 0.139 | ratio | assumed | not estimated |
| factory_case | higher_starts | wafer_starts_per_s | 800.000 | 1/week | assumed | not estimated |
| factory_case | higher_starts | cycle_time_s | 299.69 | h | assumed | not estimated |
| factory_case | higher_starts | queue_time_s | 219.34 | h | assumed | not estimated |
| factory_case | higher_starts | wip_lots | 51.9213 | lot | assumed | not estimated |
| factory_case | higher_starts | throughput_wafers_per_s | 729.587 | 1/week | assumed | not estimated |
| factory_case | higher_starts | good_packages_per_s | 96035.337 | 1/week | assumed | not estimated |
| factory_case | higher_starts | cost_per_good_package_usd | 88.5518 | USD | assumed | not estimated |
| factory_case | higher_starts | tool_capex_usd | 1.8e+08 | USD | assumed | not estimated |
| factory_case | higher_starts | depreciation_usd_per_week | 692308 | USD/week | assumed | not estimated |
| factory_case | higher_starts | depreciation_per_good_package_usd | 7.20888 | USD | assumed | not estimated |
| factory_case | higher_starts | bottleneck_step_queue_s | 26.46 | h | assumed | not estimated |
| factory_case | higher_starts | bottleneck_tool_utilization | 0.970 | ratio | assumed | not estimated |
| route_step | higher_starts:contact_etch | step_queue_time_s | 981.252 | s | assumed | not estimated |
| route_step | higher_starts:contact_litho | step_queue_time_s | 25.94 | h | assumed | not estimated |
| route_step | higher_starts:dice | step_queue_time_s | 3.65 | h | assumed | not estimated |
| route_step | higher_starts:die_attach | step_queue_time_s | 5.73 | h | assumed | not estimated |
| route_step | higher_starts:extension_implant | step_queue_time_s | 498.153 | s | assumed | not estimated |
| route_step | higher_starts:final_test | step_queue_time_s | 6.99 | h | assumed | not estimated |
| route_step | higher_starts:gate_etch | step_queue_time_s | 794.049 | s | assumed | not estimated |
| route_step | higher_starts:gate_litho | step_queue_time_s | 25.86 | h | assumed | not estimated |
| route_step | higher_starts:gate_oxide | step_queue_time_s | 6.29 | h | assumed | not estimated |
| route_step | higher_starts:inline_metrology_1 | step_queue_time_s | 3.15 | h | assumed | not estimated |
| route_step | higher_starts:inline_metrology_2 | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | higher_starts:inline_metrology_3 | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | higher_starts:liner_dep | step_queue_time_s | 2187.39 | s | assumed | not estimated |
| route_step | higher_starts:m1_cmp | step_queue_time_s | 1.62942 | s | assumed | not estimated |
| route_step | higher_starts:m1_dep | step_queue_time_s | 2354.37 | s | assumed | not estimated |
| route_step | higher_starts:m1_etch | step_queue_time_s | 749.825 | s | assumed | not estimated |
| route_step | higher_starts:m1_litho | step_queue_time_s | 26.46 | h | assumed | not estimated |
| route_step | higher_starts:mold | step_queue_time_s | 3.71 | h | assumed | not estimated |
| route_step | higher_starts:pack_ship | step_queue_time_s | 1.01 | h | assumed | not estimated |
| route_step | higher_starts:pad_etch | step_queue_time_s | 650.378 | s | assumed | not estimated |
| route_step | higher_starts:pad_litho | step_queue_time_s | 25.50 | h | assumed | not estimated |
| route_step | higher_starts:passivation_dep | step_queue_time_s | 2041.22 | s | assumed | not estimated |
| route_step | higher_starts:sd_anneal | step_queue_time_s | 7.18 | h | assumed | not estimated |
| route_step | higher_starts:sd_implant | step_queue_time_s | 145.178 | s | assumed | not estimated |
| route_step | higher_starts:silicide_dep | step_queue_time_s | 2558.35 | s | assumed | not estimated |
| route_step | higher_starts:spacer_dep | step_queue_time_s | 3173.23 | s | assumed | not estimated |
| route_step | higher_starts:spacer_etch | step_queue_time_s | 1617.72 | s | assumed | not estimated |
| route_step | higher_starts:sti_cmp | step_queue_time_s | 122.143 | s | assumed | not estimated |
| route_step | higher_starts:sti_etch | step_queue_time_s | 926.568 | s | assumed | not estimated |
| route_step | higher_starts:top_etch | step_queue_time_s | 856.129 | s | assumed | not estimated |
| route_step | higher_starts:top_litho | step_queue_time_s | 25.59 | h | assumed | not estimated |
| route_step | higher_starts:underfill_cure | step_queue_time_s | 3.65 | h | assumed | not estimated |
| route_step | higher_starts:via_cmp | step_queue_time_s | 0.553208 | s | assumed | not estimated |
| route_step | higher_starts:via_dep | step_queue_time_s | 1983.44 | s | assumed | not estimated |
| route_step | higher_starts:via_etch | step_queue_time_s | 731.852 | s | assumed | not estimated |
| route_step | higher_starts:via_litho | step_queue_time_s | 25.97 | h | assumed | not estimated |
| route_step | higher_starts:wafer_sort | step_queue_time_s | 4.98 | h | assumed | not estimated |
| route_step | higher_starts:well_implant | step_queue_time_s | 337.087 | s | assumed | not estimated |
| tool_group | higher_starts:cmp | tool_utilization | 0.443 | ratio | assumed | not estimated |
| tool_group | higher_starts:dep | tool_utilization | 0.863 | ratio | assumed | not estimated |
| tool_group | higher_starts:dice | tool_utilization | 0.061 | ratio | assumed | not estimated |
| tool_group | higher_starts:die_attach | tool_utilization | 0.162 | ratio | assumed | not estimated |
| tool_group | higher_starts:diffusion | tool_utilization | 0.533 | ratio | assumed | not estimated |
| tool_group | higher_starts:etch | tool_utilization | 0.842 | ratio | assumed | not estimated |
| tool_group | higher_starts:final_test | tool_utilization | 0.332 | ratio | assumed | not estimated |
| tool_group | higher_starts:implant | tool_utilization | 0.327 | ratio | assumed | not estimated |
| tool_group | higher_starts:litho | tool_utilization | 0.970 | ratio | assumed | not estimated |
| tool_group | higher_starts:metrology | tool_utilization | 0.083 | ratio | assumed | not estimated |
| tool_group | higher_starts:mold | tool_utilization | 0.092 | ratio | assumed | not estimated |
| tool_group | higher_starts:pack_ship | tool_utilization | 0.186 | ratio | assumed | not estimated |
| tool_group | higher_starts:underfill | tool_utilization | 0.069 | ratio | assumed | not estimated |
| tool_group | higher_starts:wafer_test | tool_utilization | 0.159 | ratio | assumed | not estimated |
| factory_case | low_downtime | wafer_starts_per_s | 600.000 | 1/week | assumed | not estimated |
| factory_case | low_downtime | cycle_time_s | 139.01 | h | assumed | not estimated |
| factory_case | low_downtime | queue_time_s | 60.98 | h | assumed | not estimated |
| factory_case | low_downtime | wip_lots | 19.2981 | lot | assumed | not estimated |
| factory_case | low_downtime | throughput_wafers_per_s | 601.780 | 1/week | assumed | not estimated |
| factory_case | low_downtime | good_packages_per_s | 79212.095 | 1/week | assumed | not estimated |
| factory_case | low_downtime | cost_per_good_package_usd | 95.3904 | USD | assumed | not estimated |
| factory_case | low_downtime | tool_capex_usd | 1.8e+08 | USD | assumed | not estimated |
| factory_case | low_downtime | depreciation_usd_per_week | 692308 | USD/week | assumed | not estimated |
| factory_case | low_downtime | depreciation_per_good_package_usd | 8.73992 | USD | assumed | not estimated |
| factory_case | low_downtime | bottleneck_step_queue_s | 1606.4 | s | assumed | not estimated |
| factory_case | low_downtime | bottleneck_tool_utilization | 0.722 | ratio | assumed | not estimated |
| route_step | low_downtime:contact_etch | step_queue_time_s | 313.446 | s | assumed | not estimated |
| route_step | low_downtime:contact_litho | step_queue_time_s | 934.296 | s | assumed | not estimated |
| route_step | low_downtime:dice | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | low_downtime:die_attach | step_queue_time_s | 6.00 | h | assumed | not estimated |
| route_step | low_downtime:extension_implant | step_queue_time_s | 104.697 | s | assumed | not estimated |
| route_step | low_downtime:final_test | step_queue_time_s | 7.40 | h | assumed | not estimated |
| route_step | low_downtime:gate_etch | step_queue_time_s | 595.776 | s | assumed | not estimated |
| route_step | low_downtime:gate_litho | step_queue_time_s | 1593.66 | s | assumed | not estimated |
| route_step | low_downtime:gate_oxide | step_queue_time_s | 5.40 | h | assumed | not estimated |
| route_step | low_downtime:inline_metrology_1 | step_queue_time_s | 3.29 | h | assumed | not estimated |
| route_step | low_downtime:inline_metrology_2 | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | low_downtime:inline_metrology_3 | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | low_downtime:liner_dep | step_queue_time_s | 2005.45 | s | assumed | not estimated |
| route_step | low_downtime:m1_cmp | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | low_downtime:m1_dep | step_queue_time_s | 898.541 | s | assumed | not estimated |
| route_step | low_downtime:m1_etch | step_queue_time_s | 495.266 | s | assumed | not estimated |
| route_step | low_downtime:m1_litho | step_queue_time_s | 820.191 | s | assumed | not estimated |
| route_step | low_downtime:mold | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | low_downtime:pack_ship | step_queue_time_s | 2227.37 | s | assumed | not estimated |
| route_step | low_downtime:pad_etch | step_queue_time_s | 573.275 | s | assumed | not estimated |
| route_step | low_downtime:pad_litho | step_queue_time_s | 751.146 | s | assumed | not estimated |
| route_step | low_downtime:passivation_dep | step_queue_time_s | 968.817 | s | assumed | not estimated |
| route_step | low_downtime:sd_anneal | step_queue_time_s | 7.31 | h | assumed | not estimated |
| route_step | low_downtime:sd_implant | step_queue_time_s | 318.195 | s | assumed | not estimated |
| route_step | low_downtime:silicide_dep | step_queue_time_s | 1687.47 | s | assumed | not estimated |
| route_step | low_downtime:spacer_dep | step_queue_time_s | 3407.3 | s | assumed | not estimated |
| route_step | low_downtime:spacer_etch | step_queue_time_s | 405.738 | s | assumed | not estimated |
| route_step | low_downtime:sti_cmp | step_queue_time_s | 63.5786 | s | assumed | not estimated |
| route_step | low_downtime:sti_etch | step_queue_time_s | 508.492 | s | assumed | not estimated |
| route_step | low_downtime:top_etch | step_queue_time_s | 346.544 | s | assumed | not estimated |
| route_step | low_downtime:top_litho | step_queue_time_s | 400.268 | s | assumed | not estimated |
| route_step | low_downtime:underfill_cure | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | low_downtime:via_cmp | step_queue_time_s | 0 | s | assumed | not estimated |
| route_step | low_downtime:via_dep | step_queue_time_s | 1166.28 | s | assumed | not estimated |
| route_step | low_downtime:via_etch | step_queue_time_s | 207.017 | s | assumed | not estimated |
| route_step | low_downtime:via_litho | step_queue_time_s | 1606.4 | s | assumed | not estimated |
| route_step | low_downtime:wafer_sort | step_queue_time_s | 5.36 | h | assumed | not estimated |
| route_step | low_downtime:well_implant | step_queue_time_s | 0 | s | assumed | not estimated |
| tool_group | low_downtime:cmp | tool_utilization | 0.338 | ratio | assumed | not estimated |
| tool_group | low_downtime:dep | tool_utilization | 0.661 | ratio | assumed | not estimated |
| tool_group | low_downtime:dice | tool_utilization | 0.050 | ratio | assumed | not estimated |
| tool_group | low_downtime:die_attach | tool_utilization | 0.133 | ratio | assumed | not estimated |
| tool_group | low_downtime:diffusion | tool_utilization | 0.478 | ratio | assumed | not estimated |
| tool_group | low_downtime:etch | tool_utilization | 0.645 | ratio | assumed | not estimated |
| tool_group | low_downtime:final_test | tool_utilization | 0.282 | ratio | assumed | not estimated |
| tool_group | low_downtime:implant | tool_utilization | 0.254 | ratio | assumed | not estimated |
| tool_group | low_downtime:litho | tool_utilization | 0.722 | ratio | assumed | not estimated |
| tool_group | low_downtime:metrology | tool_utilization | 0.066 | ratio | assumed | not estimated |
| tool_group | low_downtime:mold | tool_utilization | 0.076 | ratio | assumed | not estimated |
| tool_group | low_downtime:pack_ship | tool_utilization | 0.144 | ratio | assumed | not estimated |
| tool_group | low_downtime:underfill | tool_utilization | 0.057 | ratio | assumed | not estimated |
| tool_group | low_downtime:wafer_test | tool_utilization | 0.131 | ratio | assumed | not estimated |
| factory_case | extra_litho | wafer_starts_per_s | 800.000 | 1/week | assumed | not estimated |
| factory_case | extra_litho | cycle_time_s | 145.97 | h | assumed | not estimated |
| factory_case | extra_litho | queue_time_s | 65.61 | h | assumed | not estimated |
| factory_case | extra_litho | wip_lots | 26.8361 | lot | assumed | not estimated |
| factory_case | extra_litho | throughput_wafers_per_s | 799.569 | 1/week | assumed | not estimated |
| factory_case | extra_litho | good_packages_per_s | 105246.974 | 1/week | assumed | not estimated |
| factory_case | extra_litho | cost_per_good_package_usd | 89.0664 | USD | assumed | not estimated |
| factory_case | extra_litho | tool_capex_usd | 2.4e+08 | USD | assumed | not estimated |
| factory_case | extra_litho | depreciation_usd_per_week | 923077 | USD/week | assumed | not estimated |
| factory_case | extra_litho | depreciation_per_good_package_usd | 8.77058 | USD | assumed | not estimated |
| factory_case | extra_litho | bottleneck_step_queue_s | 1.32 | h | assumed | not estimated |
| factory_case | extra_litho | bottleneck_tool_utilization | 0.903 | ratio | assumed | not estimated |
| factory_case | extra_litho | incremental_capex_usd | 6e+07 | USD | assumed | not estimated |
| factory_case | extra_litho | incremental_annual_cash_flow_usd | 1.46676e+07 | USD | assumed | not estimated |
| factory_case | extra_litho | incremental_annual_net_income_usd | 2.66757e+06 | USD | assumed | not estimated |
| factory_case | extra_litho | payback_years | 4.09066 | year | assumed | not estimated |
| factory_case | extra_litho | roi | 0.044 | ratio | assumed | not estimated |
| factory_case | extra_litho | npv_usd | -4.70536e+06 | USD | assumed | not estimated |
| factory_case | extra_litho | irr | 0.073 | ratio | assumed | not estimated |
| route_step | extra_litho:contact_etch | step_queue_time_s | 1807.47 | s | assumed | not estimated |
| route_step | extra_litho:contact_litho | step_queue_time_s | 1629.17 | s | assumed | not estimated |
| route_step | extra_litho:dice | step_queue_time_s | 3.40 | h | assumed | not estimated |
| route_step | extra_litho:die_attach | step_queue_time_s | 5.27 | h | assumed | not estimated |
| route_step | extra_litho:extension_implant | step_queue_time_s | 642.599 | s | assumed | not estimated |
| route_step | extra_litho:final_test | step_queue_time_s | 7.17 | h | assumed | not estimated |
| route_step | extra_litho:gate_etch | step_queue_time_s | 1661.53 | s | assumed | not estimated |
| route_step | extra_litho:gate_litho | step_queue_time_s | 1281.39 | s | assumed | not estimated |
| route_step | extra_litho:gate_oxide | step_queue_time_s | 6.27 | h | assumed | not estimated |
| route_step | extra_litho:inline_metrology_1 | step_queue_time_s | 3.04 | h | assumed | not estimated |
| route_step | extra_litho:inline_metrology_2 | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | extra_litho:inline_metrology_3 | step_queue_time_s | 4.00 | h | assumed | not estimated |
| route_step | extra_litho:liner_dep | step_queue_time_s | 3373.24 | s | assumed | not estimated |
| route_step | extra_litho:m1_cmp | step_queue_time_s | 21.8645 | s | assumed | not estimated |
| route_step | extra_litho:m1_dep | step_queue_time_s | 1.15 | h | assumed | not estimated |
| route_step | extra_litho:m1_etch | step_queue_time_s | 2095.34 | s | assumed | not estimated |
| route_step | extra_litho:m1_litho | step_queue_time_s | 883.435 | s | assumed | not estimated |
| route_step | extra_litho:mold | step_queue_time_s | 3.49 | h | assumed | not estimated |
| route_step | extra_litho:pack_ship | step_queue_time_s | 1.07 | h | assumed | not estimated |
| route_step | extra_litho:pad_etch | step_queue_time_s | 1808.09 | s | assumed | not estimated |
| route_step | extra_litho:pad_litho | step_queue_time_s | 1177.75 | s | assumed | not estimated |
| route_step | extra_litho:passivation_dep | step_queue_time_s | 3276.37 | s | assumed | not estimated |
| route_step | extra_litho:sd_anneal | step_queue_time_s | 6.94 | h | assumed | not estimated |
| route_step | extra_litho:sd_implant | step_queue_time_s | 198.318 | s | assumed | not estimated |
| route_step | extra_litho:silicide_dep | step_queue_time_s | 1.32 | h | assumed | not estimated |
| route_step | extra_litho:spacer_dep | step_queue_time_s | 1.06 | h | assumed | not estimated |
| route_step | extra_litho:spacer_etch | step_queue_time_s | 2302.41 | s | assumed | not estimated |
| route_step | extra_litho:sti_cmp | step_queue_time_s | 162.345 | s | assumed | not estimated |
| route_step | extra_litho:sti_etch | step_queue_time_s | 1838.13 | s | assumed | not estimated |
| route_step | extra_litho:top_etch | step_queue_time_s | 1390.56 | s | assumed | not estimated |
| route_step | extra_litho:top_litho | step_queue_time_s | 619.38 | s | assumed | not estimated |
| route_step | extra_litho:underfill_cure | step_queue_time_s | 3.51 | h | assumed | not estimated |
| route_step | extra_litho:via_cmp | step_queue_time_s | 11.0764 | s | assumed | not estimated |
| route_step | extra_litho:via_dep | step_queue_time_s | 2735.02 | s | assumed | not estimated |
| route_step | extra_litho:via_etch | step_queue_time_s | 1542.48 | s | assumed | not estimated |
| route_step | extra_litho:via_litho | step_queue_time_s | 477.818 | s | assumed | not estimated |
| route_step | extra_litho:wafer_sort | step_queue_time_s | 5.20 | h | assumed | not estimated |
| route_step | extra_litho:well_implant | step_queue_time_s | 387.392 | s | assumed | not estimated |
| tool_group | extra_litho:cmp | tool_utilization | 0.464 | ratio | assumed | not estimated |
| tool_group | extra_litho:dep | tool_utilization | 0.903 | ratio | assumed | not estimated |
| tool_group | extra_litho:dice | tool_utilization | 0.058 | ratio | assumed | not estimated |
| tool_group | extra_litho:die_attach | tool_utilization | 0.154 | ratio | assumed | not estimated |
| tool_group | extra_litho:diffusion | tool_utilization | 0.545 | ratio | assumed | not estimated |
| tool_group | extra_litho:etch | tool_utilization | 0.881 | ratio | assumed | not estimated |
| tool_group | extra_litho:final_test | tool_utilization | 0.320 | ratio | assumed | not estimated |
| tool_group | extra_litho:implant | tool_utilization | 0.345 | ratio | assumed | not estimated |
| tool_group | extra_litho:litho | tool_utilization | 0.758 | ratio | assumed | not estimated |
| tool_group | extra_litho:metrology | tool_utilization | 0.072 | ratio | assumed | not estimated |
| tool_group | extra_litho:mold | tool_utilization | 0.088 | ratio | assumed | not estimated |
| tool_group | extra_litho:pack_ship | tool_utilization | 0.192 | ratio | assumed | not estimated |
| tool_group | extra_litho:underfill | tool_utilization | 0.065 | ratio | assumed | not estimated |
| tool_group | extra_litho:wafer_test | tool_utilization | 0.152 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:price:70 | payback_years | 201.737 | year | assumed | not estimated |
| factory_sensitivity | extra_litho:price:70 | roi | -0.195 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:price:70 | npv_usd | -5.15788e+07 | USD | assumed | not estimated |
| factory_sensitivity | extra_litho:price:85 | payback_years | 8.01872 | year | assumed | not estimated |
| factory_sensitivity | extra_litho:price:85 | roi | -0.075 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:price:85 | npv_usd | -2.81421e+07 | USD | assumed | not estimated |
| factory_sensitivity | extra_litho:price:100 | payback_years | 4.09066 | year | assumed | not estimated |
| factory_sensitivity | extra_litho:price:100 | roi | 0.044 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:price:100 | npv_usd | -4.70536e+06 | USD | assumed | not estimated |
| factory_sensitivity | extra_litho:price:100 | irr | 0.073 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:price:115 | payback_years | 2.74566 | year | assumed | not estimated |
| factory_sensitivity | extra_litho:price:115 | roi | 0.164 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:price:115 | npv_usd | 1.87314e+07 | USD | assumed | not estimated |
| factory_sensitivity | extra_litho:price:115 | irr | 0.199 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:price:130 | payback_years | 2.06628 | year | assumed | not estimated |
| factory_sensitivity | extra_litho:price:130 | roi | 0.284 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:price:130 | npv_usd | 4.21681e+07 | USD | assumed | not estimated |
| factory_sensitivity | extra_litho:price:130 | irr | 0.312 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:20 | payback_years | 17.9635 | year | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:20 | roi | -0.144 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:20 | npv_usd | -4.1654e+07 | USD | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:40 | payback_years | 4.64389 | year | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:40 | roi | 0.015 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:40 | npv_usd | -1.0405e+07 | USD | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:40 | irr | 0.040 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:60 | payback_years | 2.66663 | year | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:60 | roi | 0.175 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:60 | npv_usd | 2.08439e+07 | USD | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:60 | irr | 0.210 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:80 | payback_years | 1.8703 | year | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:80 | roi | 0.335 | ratio | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:80 | npv_usd | 5.20929e+07 | USD | assumed | not estimated |
| factory_sensitivity | extra_litho:margin:80 | irr | 0.357 | ratio | assumed | not estimated |
| factory_discount_sensitivity | extra_litho:discount:0.05 | npv_usd | 4.65679e+06 | USD | assumed | not estimated |
| factory_discount_sensitivity | extra_litho:discount:0.05 | irr | 0.073 | ratio | assumed | not estimated |
| factory_discount_sensitivity | extra_litho:discount:0.075 | npv_usd | -294159 | USD | assumed | not estimated |
| factory_discount_sensitivity | extra_litho:discount:0.075 | irr | 0.073 | ratio | assumed | not estimated |
| factory_discount_sensitivity | extra_litho:discount:0.1 | npv_usd | -4.70536e+06 | USD | assumed | not estimated |
| factory_discount_sensitivity | extra_litho:discount:0.1 | irr | 0.073 | ratio | assumed | not estimated |
| factory_discount_sensitivity | extra_litho:discount:0.125 | npv_usd | -8.64894e+06 | USD | assumed | not estimated |
| factory_discount_sensitivity | extra_litho:discount:0.125 | irr | 0.073 | ratio | assumed | not estimated |
| factory_discount_sensitivity | extra_litho:discount:0.15 | npv_usd | -1.21858e+07 | USD | assumed | not estimated |
| factory_discount_sensitivity | extra_litho:discount:0.15 | irr | 0.073 | ratio | assumed | not estimated |
| factory_terminal_value_sensitivity | extra_litho:terminal:0 | npv_usd | -1.21564e+07 | USD | assumed | not estimated |
| factory_terminal_value_sensitivity | extra_litho:terminal:0 | irr | 0.023 | ratio | assumed | not estimated |
| factory_terminal_value_sensitivity | extra_litho:terminal:0.1 | npv_usd | -8.43089e+06 | USD | assumed | not estimated |
| factory_terminal_value_sensitivity | extra_litho:terminal:0.1 | irr | 0.050 | ratio | assumed | not estimated |
| factory_terminal_value_sensitivity | extra_litho:terminal:0.2 | npv_usd | -4.70536e+06 | USD | assumed | not estimated |
| factory_terminal_value_sensitivity | extra_litho:terminal:0.2 | irr | 0.073 | ratio | assumed | not estimated |
| factory_terminal_value_sensitivity | extra_litho:terminal:0.3 | npv_usd | -979836 | USD | assumed | not estimated |
| factory_terminal_value_sensitivity | extra_litho:terminal:0.3 | irr | 0.095 | ratio | assumed | not estimated |
| factory_terminal_value_sensitivity | extra_litho:terminal:0.4 | npv_usd | 2.74569e+06 | USD | assumed | not estimated |
| factory_terminal_value_sensitivity | extra_litho:terminal:0.4 | irr | 0.114 | ratio | assumed | not estimated |

## Evidence

| Class | Rows | Meaning |
|---|---|---|
| assumed | 316 | planning assumption or uncalibrated model |

Projected and simulated rows are `assumed` because the technology, model
parameters and planning assumptions are uncalibrated. The as-built rows are
`measured` source data. A projected result must not be described as a measured
yield or a qualified silicon result.

## Inputs

| Role | Path | SHA-256 | Bytes |
|---|---|---|---|
| scenario | `scenarios/g100_factory_28nm.yaml` | `bd634af551b5f317...` | 1179 |
| package | `packages/mcm_si.yaml` | `66e840836c5a2d12...` | 1263 |
| yield | `yields/g100_mcm_28nm.yaml` | `340be98f95ef0529...` | 1703 |
| factory | `factory/g100_28nm.yaml` | `a8a98e63b010a348...` | 6724 |
| chip | `chips/g100.yaml` | `b9e127cb2fa42f08...` | 1016 |
| tech | `tech/grx28.yaml` | `fec22f0374bcdbf8...` | 5982 |

## Reproduce

```bash
python -m fabtwin run scenarios/g100_factory_28nm.yaml --out /tmp/fabtwin-site-jjg9y_2q
```

## Observation store

The run is indexed in SQLite at `/tmp/fabtwin-site-jjg9y_2q/fabtwin.db`:

```bash
python -m fabtwin query --db /tmp/fabtwin-site-jjg9y_2q/fabtwin.db --run g100_factory_28nm-20261107T043407Z-a53074bd
```

Artifacts: [observations.csv](observations.csv) · [run.json](run.json)

## Caveats

- Phase 4 route, tool counts, process times, MTBF/MTTR and operating cost are planning assumptions, not a foundry MES route card or measured line performance.
- Downtime is an availability factor applied to effective process time; random failures, maintenance calendars, reticle changes, dispatch rules and transport time are not modelled.
- Cost per good package is the Phase 3 package cost plus factory operating cost and straight-line depreciation for priced tool groups; it is not a qualified product cost. Only tool groups with a declared capex are depreciated, so the absolute cost is partial. Payback and ROI are reported only when a package price, gross margin or sensitivity block is supplied; they are planning economics, not a market forecast.
- Scanner DCF uses the declared five-year cash-flow ramp and terminal value; taxes, working capital, price erosion and replacement capex are not modelled.
- Discount-rate and terminal-value sensitivity hold the base scanner cash flow, ramp and hurdle rate fixed.
- Price/margin sensitivity is one-at-a-time and holds output, cost and margin constant; it is not a demand forecast.

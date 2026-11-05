# Open-source 28 nm implementation flow

This is the implementation plan for shrinking GRX930 and G100 at 28 nm
using open-source EDA. It separates three things that are often conflated:

1. what the open-source tools can do today,
2. what PDK data exists openly, and
3. which of the model's DTCO levers map to real tool knobs.

Checked November 2026. Versions are the ones published on the projects' own
release pages at that time.

## Bottom line

**There is no open-source 28 nm PDK.** The open, manufacturable kits stop at
130 nm (SkyWater SKY130, IHP SG13G2) and 180 nm (GlobalFoundries GF180MCU). The
open predictive kits are 45 nm (FreePDK45 / NanGate45) and 7 nm (ASAP7). For
28 nm there are device model cards (ASU PTM 28 nm HP/LP, BSIM4) but no LEF,
Liberty, GDS, DRC, LVS or RCX collateral.

That means a 28 nm flow is a **PDK-porting project**, not a tool-installation
project. The engines are ready; the decks are the deliverable.

## Toolchain

| Stage | Tool | Current status | 28 nm note |
|---|---|---|---|
| Lint / simulation | Verilator, Icarus, cocotb | Mature | Node-independent |
| Synthesis | Yosys + ABC | Mature; LibreLane pins Yosys and best-effort supports 0.67+ | Liberty-driven mapping; delay/area scripts and `dont_use` matter more than at 130 nm |
| Floorplan / place / CTS / route | OpenROAD (`floorplan`, `gpl`, `dpl`, `cts`, `grt`, `drt`, `rsz`) | Mature, rolling master; no v1.0 tag | `drt` has `-db_process_node` and `-repair_pdn_vias` for M1/M2 rail stacks; multi-patterning colour rules are not covered by open decks |
| Flow orchestration | OpenROAD-flow-scripts (ORFS) | Rolling master, no tagged releases | Ships sky130, gf180, ihp-sg13g2, nangate45, asap7, gt2n |
| Flow orchestration | LibreLane (OpenLane 2 lineage) | 3.0.18 stable, 3.0.17 latest release, 3.1.0.dev5 pre-release | Ships sky130, gf180mcu, ihp-sg13, freepdk45; hermetic Nix flow |
| Flow orchestration | SiliconCompiler | 0.38.12 (0.x API) | Drives OpenROAD; ships freepdk45, asap7, gt2n, icsprout55 |
| STA | OpenSTA | Mature; LibreLane supports 3.0/3.1 | Needs 28 nm Liberty corners and SPEF; no vendor OCV signoff guarantee |
| RC extraction | OpenRCX | Mature engine | Needs a calibrated per-node extraction-rules file; this is the hardest 28 nm blocker |
| DRC / LVS | KLayout, Magic, Netgen | Mature engines | The 28 nm runset must be authored; Magic is not a realistic 28 nm colour-aware signoff deck |
| Cell layout / GDS | KLayout, Magic | Mature | GDS stream-out and XOR checks are ready |
| SPICE / characterisation | ngspice, Xyce | Mature | Use with PTM 28 nm cards for device-level calibration |

The practical choices are **ORFS** for the reference flow, **LibreLane 3.0.x**
for a hermetic flow with an explicit proven/experimental boundary, and
**SiliconCompiler** when tool-swappability or cluster execution matters. All
three inherit the same PDK limitation.

## Two-track plan

### Track A — 45 nm proxy, now

Run the complete flow on **FreePDK45 / NanGate45**:

- Yosys synthesis into the 45 nm Liberty set, with `abc` area and delay scripts.
- OpenROAD floorplan, placement, CTS, global and detailed routing.
- OpenSTA at the available corners; OpenRCX with the platform rules.
- KLayout/Magic stream-out and DRC, Netgen LVS.

The purpose is not to predict 28 nm area. It is to make the flow, the scripts and
the regression reproducible, and to measure the **relative** value of each lever
(MBFF on/off, placement density, pin-access repair). Those relative deltas
transfer better than absolute area does.

**The 45 nm proxy cannot measure 9T versus 7.5T.** NanGate45 is a single
10-track library: 1.4 µm rows against a 0.14 µm M1 pitch. No open 45 nm library
ships 9T or 7.5T variants. The first measured run therefore has two arms: a
45 nm 10T anchor, and a same-PDK GF180MCU 9T-versus-7T A/B for the track-height
sensitivity. GF180 is 180 nm; its delta is relative, not a 28 nm result. The
measured numbers are in [`out/FLOW_RESULTS.md`](../out/FLOW_RESULTS.md).

Cross-check device-level power and FO4 against **PTM 28 nm HP/LP** cards in
ngspice. Report the result as *28 nm-class, extrapolated from a 45 nm predictive
proxy*, never as silicon area.

### Track B — NDA 28 nm, target

Port the same flow to a foundry 28 nm kit. What must come from the foundry under
NDA:

- calibrated BSIM4/BSIM-CMG corners and mismatch models,
- LEF, Liberty at all PVT corners, and GDS for the standard-cell, IO and SRAM
  libraries (often third-party IP the foundry cannot sublicense),
- DRC, LVS, antenna, density, fill, EM/IR and multi-patterning decks,
- a calibrated RCX rules file and the metal stack,
- seal ring, ESD and IO libraries.

Only then can the flow produce a manufacturable 28 nm block.

## What each model lever becomes in the flow

| Model lever | Tool knob | How to measure it |
|---|---|---|
| 9T → 7.5T library | At 28 nm, swap the Liberty/LEF set; re-synthesise and re-place. The 45 nm proxy cannot: NanGate45 is 10T only. | Measured on GF180 9T/7T: −20.6% routed cell area, −10.6% wirelength, 0.72 ns worse WNS, 0 DRC |
| MBFF-2/4 | Map to MBFF Liberty cells; `dfflibmap`; `dont_use` the 1-bit flop | Sequential area, clock power, congestion |
| Pin-density-aware placement | Placement density and routability iterations; `repair_design` | Detailed-route DRC, pin-access violations, area inflation |
| M1–M3 pitch compression | Platform LEF/tech file | RC, WNS, routability |
| Via pillar | Platform via rules (FinFET only) | Via resistance, wire delay |
| SRAM area | Compiled SRAM macros | Macro area and aspect ratio, not just bitcell area |

The model's pad-ring result does not map to any of these: it is a package and
interface decision. At 178 pads it sets a 13.0 mm² die regardless of the library.

## Metrics to capture from the first real run

- **Area:** placed cell area, block area, utilisation, SRAM macro area.
- **Timing:** WNS, TNS, critical-path FO4 count, clock skew.
- **Power:** dynamic, clock, leakage at 25 °C and 85 °C; IR drop if the deck exists.
- **Physical:** detailed-route DRC, antenna violations, total and long-net wirelength.
- **Flow health:** runtime, peak memory, reproducible seed, and a clean re-run from RTL.

These are the numbers that replace the planning model. Until they exist, every
28 nm area and power figure in this repository is a target, not a result.

## Sources

- LibreLane releases and changelog: <https://github.com/librelane/librelane/releases>, <https://github.com/librelane/librelane/blob/main/Changelog.md>
- LibreLane flow reference: <https://librelane.readthedocs.io/en/latest/reference/flows.html>
- OpenROAD-flow-scripts: <https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts>
- OpenROAD PDK support: <https://openroad.readthedocs.io/en/latest/main/README.html>
- OpenROAD detailed routing: <https://openroad.readthedocs.io/en/latest/main/src/drt/README.html>
- OpenROAD RC extraction: <https://openroad.readthedocs.io/en/latest/main/src/rcx/README.html>
- SiliconCompiler: <https://docs.siliconcompiler.com/en/latest/>
- FOSSi Ciel PDK list: <https://github.com/fossi-foundation/ciel>
- FreePDK45: <https://eda.ncsu.edu/freepdk/freepdk45/>
- ASAP7: <https://github.com/The-OpenROAD-Project/asap7>
- SKY130: <https://github.com/google/skywater-pdk>
- GF180MCU: <https://github.com/google/gf180mcu-pdk>
- IHP SG13G2: <https://github.com/IHP-GmbH/IHP-Open-PDK>
- PTM 28 nm: <https://ptm.asu.edu/> — device cards only. The site was unreachable
during the November 2026 check, so the card set was not re-verified.

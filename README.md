# GRX28 — a 28 nm-class PDK, DTCO starter and foundry digital-twin platform

This repository is the beginning of a process-design kit we own: a technology
definition, a planar device model, standard-cell libraries, a BEOL stack, a
block-level DTCO estimator, a pad-ring/package floorplan, and a FinFET layout
demo kept as the advanced-node reference. It answers one question
quantitatively: **what actually shrinks the quad-core, dual-NPU GRX930 and the
GRXGPU/PTA logic at 28 nm, and by how much?**

It is a planning model, not a foundry-qualified PDK. See
[Limitations](#limitations) before using any number in a schedule or a datasheet.

## New direction: foundry digital twin

The repository is now also the home of a foundry digital-twin platform for
GRX930, G100/GRXGPU and the PTA. The proposed architecture and phased plan are
in [docs/fab-sim-architecture.md](docs/fab-sim-architecture.md); the concept and
requirements catalogue is [docs/fab-sim.md](docs/fab-sim.md). The twin starts
from the existing `gpdk` analytical models and measured flow results, not from a
full-chip TCAD stack. The Phase 0 skeleton is in `fabtwin/`; the first
reproducible scenario is
[`scenarios/grx930_28nm_baseline.yaml`](scenarios/grx930_28nm_baseline.yaml).
Each run is indexed in `out/fabtwin/fabtwin.db`; `python -m fabtwin query`
provides the cross-run observation path.

## Quick start

```bash
python -m gpdk          # regenerate out/REPORT.md, CSVs, GDS, SVG, PNG
python -m gpdk padring  # rebuild the GRX930 pad ring and ball map
python -m gpdk drc      # check the 12 nm FinFET demo inverter
python -m fabtwin validate scenarios/grx930_28nm_baseline.yaml
python -m fabtwin run scenarios/grx930_28nm_baseline.yaml
python -m fabtwin query --runs
python -m fabtwin query --run RUN_ID --metric die_area_m2
python -m fabtwin compare RUN_A RUN_B --only-changes
python -m pytest        # model, geometry, package and fabtwin tests
```

Dependencies: Python 3.10+, PyYAML. Pillow is optional and only used for the PNG
layout preview. Tested with Python 3.14, PyYAML 6.0, pytest 9.2, Pillow 12.3.

`query` reads the SQLite index and accepts `--run`, `--metric`, `--entity`,
`--evidence`, `--product` and `--limit`; `--runs` lists indexed runs and
`--json` is machine-readable. The store path defaults to
`out/fabtwin/fabtwin.db`.

`compare` matches observations by entity and metric. It reports value deltas,
added and removed rows, unit and model-version changes, and evidence transitions
such as `assumed -> measured`. `--only-changes` limits the table to flagged
rows. Each comparison writes a Markdown report beside the store at
`out/fabtwin/comparisons/<run-a>__vs__<run-b>.md`; use `--report` to override
the path.

## What is in the box

```
tech/grx28.yaml             our 28 nm target: 117 nm CPP, 90 nm M1/M2, 9/7.5T
tech/grx12f.yaml            12 nm FinFET reference node (84 nm CPP, fins)
tech/12lp_class_ref.yaml    first-generation 12 nm comparison baseline
libraries/lp28_*.yaml       28 nm planar libraries: 9T and 7.5T, single-finger
libraries/hp*_*.yaml        12 nm FinFET reference libraries
chips/grx930.yaml           measured quad-core RV64 + dual-NPU baseline
chips/grxgpu_pta.yaml       GPU / parallel throughput accelerator assumptions
gpdk/tech.py                node loader; fin and finger width units
gpdk/device.py              planar/FinFET Ion/Ioff/Cgg/Ron/FO4 model
gpdk/cells.py               cell templates, track/isolation architecture
gpdk/beol.py                size-effect-corrected R, C, via and wire delay
gpdk/block.py               area, frequency, power and pad-floor estimator
gpdk/asbuilt.py             measured baseline, node jump, pad sensitivity
gpdk/package.py             pin budget, package selection, assembly floor
gpdk/padring.py             pad-ring floorplan and TFBGA ball map
gpdk/dtco.py                node-aware lever sweep at the target clock
fabtwin/                    Phase 0 runner, strict schema, manifest, SQLite index, gpdk adapter
scenarios/grx930_28nm_baseline.yaml  first reproducible Phase 0 baseline
gpdk/layout.py              abstract FinFET inverter layout, SVG/PNG
gpdk/drc.py                 fin/gate grid, COAG, enclosure, width/space checks
gpdk/gds.py                 GDSII writer and reader
gpdk/report.py              report and CSV generator
out/REPORT.md               generated node, library and chip report
out/grx930_package.png      pad ring and TFBGA-196 ball map
out/grx930_padring.csv      pad coordinates; out/grx930_ballmap.csv nets
out/fabtwin/<run-id>/       run.json, observations.csv and report.md
out/fabtwin/fabtwin.db      SQLite observation index for all runs
out/fabtwin/comparisons/    generated run-to-run comparison reports
docs/open-source-28nm-flow.md  tools, PDK reality, two-track plan
docs/dtco-strategy.md       the 28 nm levers, results, and validation plan
docs/fab-sim-architecture.md  foundry-twin architecture and phased plan
docs/fab-sim.md             concept and requirements catalogue
flow/                        Yosys + OpenROAD proxy flow (45 nm, GF180 and ASAP7)
out/FLOW_RESULTS.md          measured synthesis and P&R results
docs/node-definition.md     full GRX12F FinFET reference definition
```

## Headline results

GRX930 uses the **measured RISC-V test chip** as its baseline: four RV64IMAC
cores, two NPUs, operand banks and 96 KB of on-chip SRAM. GRXGPU/PTA is still a
planning profile. All block numbers are at or above each chip's target clock,
with the 28 nm 9T single-finger library as the baseline.

| Chip | Baseline area | Optimised area | Area | Power at target | Target clock |
|---|---|---|---|---|---|
| GRX930 (28 nm retarget) | 0.88 mm² | **0.80 mm²** | **−9.0%** | 5.5 → 5.2 mW | 25 MHz |
| GRXGPU/PTA | 411.9 mm² | **378.3 mm²** | **−8.2%** | 126.9 → 116.8 W | 0.75 GHz |

**The measured chip is the real baseline.** Its 46.2 mm² of logic and 40.2 mm²
of SRAM sit on a 165 mm² die, i.e. 34.2 µm² per NAND2-equivalent and 51.1 µm² per
SRAM bit. The same netlist on GRX28 is 0.88 mm² of content at the 9T baseline — a
**98× node jump** — and 0.80 mm² after the levers. Logic alone falls 81×; SRAM
falls 273×.

But its real pin budget is 118 signals plus 60 supply and analog pads: **178
pads, 13.0 mm², a TFBGA-196**. Two staggered rows at 152.9 µm minimum pitch
carry the ring, and the 196-ball package leaves 18 balls spare. **93.8% of that
die is empty and no library lever changes it.** GRX930 at 28 nm is pad-limited:
density buys integration headroom and power, not a smaller chip.

| Lever (cumulative) | GRX930 | GRXGPU/PTA |
|---|---|---|
| 7.5T track shrink | −6.9% | −6.6% |
| + MBFF | −6.7% | −5.9% |
| + pin-aware placement | −9.0% | −8.2% |

The whole 9T-to-7.5T ladder is worth 0.08 mm² on GRX930 — 0.6% of the pad-ring
die. Deleting the 64-bit off-chip bus is worth 7.8 mm².

## Findings that matter

1. **28 nm is planar, so the FinFET levers disappear.** There are no fins, no
   single diffusion break and no COAG. Cell height is the only cell-architecture
   density lever left. A 6T library is not modelled because 540 nm rows cannot
   fit the two width units a series stack needs; 7.5T is the density floor.
2. **Track height is still the cleanest lever.** 9T → 7.5T removes 135 nm of row
   height (16.7%) with no change in cell topology. Average cell area falls from
   0.495 to 0.412 µm².
3. **MBFF is a clock-power lever, not an area lever.** At 6–8% sequential
   density, MBFF-2/4 changed CPU area by +0.2% while cutting 0.2 mW, and GPU area
   by +0.7% while cutting 5.0 W. The widely quoted 20–30% saving applies to the
   sequential cells, not to the block.
4. **The interface, not the library, sets the die.** At 178 pads the ring needs
   13.0 mm² against 0.80 mm² of content. 16-bit DDR drops the die to 5.1 mm²;
   integrating the 64 KB drops it to the 4.0 mm² assembly floor.
5. **The GPU clock has to change.** 1.5 GHz is not a 28 nm target for a 420M-gate
   block. The model's native capability is 0.71 GHz at one finger and 1.04 GHz
   with two; 0.75 GHz is the planning point, at 117 W.
6. **There is no open 28 nm PDK.** Open-source EDA can run the flow, but the
   28 nm LEF/lib/GDS and DRC/LVS/RCX decks must come from a foundry under NDA.
   See [the flow plan](docs/open-source-28nm-flow.md).

## Recommended starting configuration

| Chip | Library | Why |
|---|---|---|
| GRX930 | `lp28_7t5_1f` — 7.5T, single-finger, DDB | Same pad-limited die as 9T, but 16.7% shorter rows and lower leakage; no COAG/SDB decision exists at this node. |
| GRXGPU/PTA | `lp28_7t5_1f` — 7.5T, single-finger, DDB | The 9T baseline costs 6.6% more area without buying enough routability; MBFF-4 and pin-aware placement recover another 3%. |

Both use the same device, BEOL and isolation assumptions, so the comparison is
apples-to-apples within this model.

## Open-source implementation path

The flow is ready; the 28 nm decks are not. The plan is two-track:

1. **Now:** run Yosys → OpenROAD on **FreePDK45 / NanGate45** for a 45 nm 10T
   anchor, and use **GF180MCU 9T/7T** for the real track-height A/B. NanGate45 has
   no 9T/7.5T variant, so 45 nm cannot answer that question. The measured run is
   in [out/FLOW_RESULTS.md](out/FLOW_RESULTS.md): 7T saves 20.6% routed cell area and
   10.6% wirelength, costs 0.72 ns WNS at the same clock, and both routes are
   DRC-clean.
   ASAP7 supplies the closest real 7.5T/6T pair. On the same slice, 7.5T → 6T
   measures 990.113 → 750.765 µm² (−24.17% total cell area; −20.07%
   combinational) and 1,025 → 796 µm² routed cell area (−22.34%), with
   27,238 → 23,616 µm wirelength (−13.30%). Both routes are DRC-clean at 20 ns.
   The 6T arm uses a derived 6T-compatible VIA12 because the 6T release has no
   technology LEF; this is not a 28 nm result.
2. **Target:** port the identical flow to an NDA 28 nm kit (LEF, Liberty, GDS,
   DRC/LVS, RCX, EM/IR, multi-patterning). Only that run can sign off a 28 nm
   block.

Tool versions and the specific 28 nm blockers are in
[docs/open-source-28nm-flow.md](docs/open-source-28nm-flow.md).

## Limitations

- **Not a foundry PDK.** There are no wells, implants, Vt flavours, SRAM
  compilers, IO/ESD cells, DRC/LVS decks, OPC models, reliability rules, or
  silicon-calibrated compact models here. A real 28 nm PDK is a fab-coupled
  effort; this is the DTCO and architecture layer above it.
- **The device model is analytic, not BSIM.** It captures width, overdrive,
  DIBL, subthreshold slope, temperature, gate capacitance and FO4 scaling. It
  does not capture GIDL, BTBT, self-heating, layout-dependent effects, or
  statistical variation.
- **The planar finger abstraction is a model.** Fingers are treated as width
  units that fit inside the fixed cell height. It captures drive and leakage
  scaling, not the exact layout-dependent width of every cell.
- **Routability is a heuristic.** Pin capacity and routable utilisation are a
  model, not a global router. The 7.5T result needs a real trial route on the
  45 nm proxy and then the 28 nm PDK.
- **Absolute frequency and power are optimistic.** The model is for relative
  comparisons. Its 1.94 GHz CPU capability and 1.04 GHz GPU capability are
  planning numbers, not silicon results. GRX930 is modelled at its measured
  25 MHz clock, where leakage dominates.
- **The measured baseline's process is not disclosed.** Only its area, clock and
  memory data are known. GRX930's memory pins are derived from 8 B/cycle and
  64 KB, but the fixed groups (JTAG, UART, boot, GPIO) and the 1:6 supply ratio
  are assumptions; the die floor moves linearly with the pad count.

## Provenance

All technology parameters in `tech/grx28.yaml` are our own design targets,
informed by public 28 nm planar HKMG literature and industry-typical geometry.
`tech/grx12f.yaml` is the FinFET reference node, and `tech/12lp_class_ref.yaml`
is a deliberately conservative approximation used only for comparison. Nothing
in this repository is foundry confidential data, and no claim is made that any
foundry's 28 nm process uses these exact values.

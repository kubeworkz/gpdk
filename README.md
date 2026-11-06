# GRX28 — a 28 nm-class PDK, DTCO starter and foundry digital-twin platform

This repository is the beginning of a process-design kit we own: a technology
definition, a planar device model, standard-cell libraries, a BEOL stack, a
block-level DTCO estimator, a pad-ring/package floorplan, and a FinFET layout
demo kept as the advanced-node reference. It answers one question
quantitatively: **what actually shrinks the quad-core, dual-NPU GRX930 and the
G100 logic at 28 nm, and by how much?**

It is a planning model, not a foundry-qualified PDK. See
[Limitations](#limitations) before using any number in a schedule or a datasheet.

## New direction: foundry digital twin

The repository is now also the home of a foundry digital-twin platform for
GRX930, G100 and the PTA. The proposed architecture and phased plan are
in [docs/fab-sim-architecture.md](docs/fab-sim-architecture.md); the concept and
requirements catalogue is [docs/fab-sim.md](docs/fab-sim.md). The twin starts
from the existing `gpdk` analytical models and measured flow results, not from a
full-chip TCAD stack. The Phase 0 runner is in `fabtwin/`; the baseline
scenarios are
[`grx930`](scenarios/grx930_28nm_baseline.yaml),
[`g100`](scenarios/g100_28nm_baseline.yaml) and
[`pta`](scenarios/pta_28nm_baseline.yaml).
Each run is indexed in `out/fabtwin/fabtwin.db`; `python -m fabtwin query`
provides the cross-run observation path. Phase 0 now defines three products:
GRX930, G100 and PTA. G100 is the digital GPU profile; PTA is a separate
photonic chiplet with an MCM package definition. Phase 1 implements the GRX930
die/package planning slice: a 300 mm wafer grid, Poisson critical-area die
yield, exponential per-pad assembly yield, and cost per good package, with
seeded sampling uncertainty. Its assumptions are in `yields/grx930_28nm.yaml`
and its session is `scenarios/grx930_yield_28nm.yaml`.

At those assumptions the model gives 4,865 gross dies per wafer, 99.63% die
yield, 4,816 good packages and $2.55 per good package. The sensitivity session
`scenarios/grx930_yield_sensitivity_28nm.yaml` sweeps defect density
(0.02–0.20 cm⁻²), pad count (57–220) and assembly tolerance (2–20 ppm per pad).
Density takes die yield from 99.91% to 99.11% and cost from $2.543 to $2.553;
57 → 220 pads takes good packages from 4,822 to 4,815; 2 → 20 ppm takes them
from 4,822 to 4,805. The defect-density effect is small because the modelled
critical area is 4.55 mm² of a 12.99 mm² die. Every value is `assumed`: this is
scenario yield under stated assumptions, not a foundry yield prediction.

The variation session `scenarios/grx930_yield_variation_28nm.yaml` runs 40
assembly lots of 25 wafers with lognormal defect-density and assembly variation.
At 15% lot and 10% wafer defect-density CV it gives a 99.63% mean die yield with
0.036% wafer-to-wafer and 0.061% lot-to-lot sigma, 4,816 good packages per wafer
and $2.55 per good package. The sigmas describe the modelled expected yield, not
measured distributions.

The wafer-map session `scenarios/grx930_yield_wafer_map_28nm.yaml` adds a radial
defect-density profile, D(r) = D0 * (1 + 2 * (r/R)^3), and reports a five-zone
map. At the planning profile the mean die yield is 99.35%, with 99.63% at the
center and 99.11% at the edge (edge/center 0.995), 4,803 good packages per wafer
and $2.55 per good package. The radial yield slope is -5.7e-5 per mm. The
profile is an assumption; it has no angular or clustering structure.

## Quick start

```bash
python -m gpdk          # regenerate out/REPORT.md, CSVs, GDS, SVG, PNG
python -m gpdk padring  # rebuild the GRX930 pad ring and ball map
python -m gpdk drc      # check the 12 nm FinFET demo inverter
python -m fabtwin validate scenarios/grx930_28nm_baseline.yaml
python -m fabtwin run scenarios/grx930_28nm_baseline.yaml
python -m fabtwin run scenarios/g100_28nm_baseline.yaml
python -m fabtwin run scenarios/pta_28nm_baseline.yaml
python -m fabtwin run scenarios/grx930_yield_28nm.yaml
python -m fabtwin run scenarios/grx930_yield_sensitivity_28nm.yaml
python -m fabtwin run scenarios/grx930_yield_variation_28nm.yaml
python -m fabtwin run scenarios/grx930_yield_wafer_map_28nm.yaml
python -m fabtwin query --runs
python -m fabtwin query --reports
python -m fabtwin query --run RUN_ID --metric die_area_m2
python -m fabtwin compare RUN_A RUN_B --only-changes
python -m fabtwin verify-artifacts
python -m pytest        # model, geometry, package and fabtwin tests
python -m pytest tests/test_clean_checkout.py  # isolated baseline reproducibility check
```

Dependencies: Python 3.10+, PyYAML. Pillow is optional and only used for the PNG
layout preview. Tested with Python 3.14, PyYAML 6.0, pytest 9.2, Pillow 12.3.

`query` reads the SQLite index and accepts `--run`, `--metric`, `--entity`,
`--evidence`, `--product` and `--limit`; `--runs` lists indexed runs,
`--reports` lists registered comparison reports, and `--json` is
machine-readable. The store path defaults to `out/fabtwin/fabtwin.db`.

`compare` matches observations by entity and metric. It reports value deltas,
added and removed rows, unit and model-version changes, and evidence transitions
such as `assumed -> measured`. `--only-changes` limits the table to flagged
rows. Each comparison writes a Markdown report beside the store at
`out/fabtwin/comparisons/<run-a>__vs__<run-b>.md`; use `--report` to override
the path. The report is registered in SQLite with its byte count and SHA-256,
returned as `report_artifact` in JSON output. Regenerating the same path updates
that entry rather than leaving a stale hash.

The PTA baseline records the declared 4x4 mesh, port count, optical window,
lane pitch and wavelength. It is a product-definition baseline, not an optical
performance model; insertion loss, phase error, thermal tuning and tensor error
are Phase 2 work. Its MCM package definition is a hashed scenario input.

`baselines/phase0_baseline.json` holds the run-independent fingerprints for
all three baselines: scenario and input hashes, observation rows, evidence
classes and model versions. The clean-checkout test compares every fresh run
against those fingerprints, not just against its own manifest.

`verify-artifacts` recomputes the SHA-256 and byte count of every indexed run
artifact, scenario/chip/technology input, and comparison report. It reports
missing, unreadable, size-mismatched and hash-mismatched files, then exits
nonzero if any check fails; `--json` returns the detailed result. It modifies
neither indexed records nor artifact files, and it verifies only what the index
claims; it does not discover unindexed files.

## What is in the box

```
tech/grx28.yaml             our 28 nm target: 117 nm CPP, 90 nm M1/M2, 9/7.5T
tech/grx12f.yaml            12 nm FinFET reference node (84 nm CPP, fins)
tech/12lp_class_ref.yaml    first-generation 12 nm comparison baseline
libraries/lp28_*.yaml       28 nm planar libraries: 9T and 7.5T, single-finger
libraries/hp*_*.yaml        12 nm FinFET reference libraries
chips/grx930.yaml           measured quad-core RV64 + dual-NPU baseline
chips/g100.yaml             digital GPU planning profile (pre-split block)
chips/pta.yaml              photonic tensor accelerator product definition
packages/mcm_si.yaml        2.5D silicon-interposer package definition
yields/grx930_28nm.yaml      Phase 1 wafer, defect, assembly and cost assumptions
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
scenarios/grx930_28nm_baseline.yaml  GRX930 Phase 0 baseline
scenarios/g100_28nm_baseline.yaml    G100 Phase 0 baseline
scenarios/pta_28nm_baseline.yaml     PTA topology/package baseline
scenarios/grx930_yield_28nm.yaml    GRX930 die/package yield vertical slice
scenarios/grx930_yield_sensitivity_28nm.yaml  GRX930 yield sensitivity curves
scenarios/grx930_yield_variation_28nm.yaml   GRX930 lot/wafer variation session
scenarios/grx930_yield_wafer_map_28nm.yaml   GRX930 radial wafer-map session
gpdk/dieyield.py             wafer grid, yield, variation, maps and curves
gpdk/layout.py              abstract FinFET inverter layout, SVG/PNG
gpdk/drc.py                 fin/gate grid, COAG, enclosure, width/space checks
gpdk/gds.py                 GDSII writer and reader
gpdk/report.py              report and CSV generator
out/REPORT.md               generated node, library and chip report
out/grx930_package.png      pad ring and TFBGA-196 ball map
out/grx930_padring.csv      pad coordinates; out/grx930_ballmap.csv nets
out/fabtwin/<run-id>/       run.json, observations.csv and report.md
out/fabtwin/fabtwin.db      SQLite index for runs, observations and report hashes
out/fabtwin/comparisons/    generated run-to-run comparison reports
baselines/phase0_baseline.json  committed, run-independent baseline fingerprints
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
cores, two NPUs, operand banks and 96 KB of on-chip SRAM. G100 is still a
planning profile. All block numbers are at or above each chip's target clock,
with the 28 nm 9T single-finger library as the baseline.

| Chip | Baseline area | Optimised area | Area | Power at target | Target clock |
|---|---|---|---|---|---|
| GRX930 (28 nm retarget) | 0.88 mm² | **0.80 mm²** | **−9.0%** | 5.5 → 5.2 mW | 25 MHz |
| G100 | 411.9 mm² | **378.3 mm²** | **−8.2%** | 126.9 → 116.8 W | 0.75 GHz |

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

| Lever (cumulative) | GRX930 | G100 |
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
| G100 | `lp28_7t5_1f` — 7.5T, single-finger, DDB | The 9T baseline costs 6.6% more area without buying enough routability; MBFF-4 and pin-aware placement recover another 3%. |

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

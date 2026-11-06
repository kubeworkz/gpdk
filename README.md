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
defect-density profile, a three-lobe angular term and two Gaussian clusters, and
reports a five-zone map. At the planning profile the mean die yield is 99.31%,
with 99.63% at the center and 99.10% at the edge (edge/center 0.9947), 4,801
good packages per wafer and $2.55 per good package. The radial yield slope is
-5.6e-5 per mm. The lobes and clusters are planning assumptions, not measured
signatures. Each map run writes `wafer_map.svg` and `wafer_map.csv` beside the
standard artifacts.

Phase 2 implements the PTA photonic/thermal slice in `gpdk/photonics.py`,
`photonic/pta_siph_28nm.yaml` and the `pta_photonic` F1 engine. The session
`scenarios/pta_photonic_28nm.yaml` propagates width, etch depth, line-edge
roughness, ambient temperature and package alignment through a per-MZI phase
and loss budget plus a one-dimensional silicon-interposer thermal path. At the
planning assumptions and 400 samples it gives 3.21 dB insertion loss, 1.62 rad
per-MZI phase error, 82.7 mW mesh tuning power, a 0.52 tensor-error proxy and a
6.27 K temperature rise. The one-sigma phase ranking is width (1.22 rad) ahead
of etch depth (1.01 rad) and ambient temperature (0.13 rad); the loss ranking is
alignment (0.45 dB) ahead of LER (0.09 dB). The thermal path is 3.38 K/W with a
6.77 K local rise before ambient variation. These are F1 planning estimates, not
measured PTA performance: phase is per-MZI without common-mode cancellation or
tuning feedback, and the thermal path omits TIM, bump and die-level interface
resistances.

A scenario may also set `inputs.photonic_calibration` to a measured-coefficient
file. The calibration contract replaces width sensitivity, etch sensitivity,
loss coefficients, thermo-optic coefficient and/or thermal resistance with
values extracted from named test structures; each value carries a standard
uncertainty and must be marked `evidence: measured`. Calibration observations
are stored as `measured`, while aggregate model outputs remain `assumed`
because they are still model estimates. No measured PTA calibration dataset is
included in the repository; synthetic fixtures are used only in tests.

Phase 3 adds the G100 + PTA MCM assembly slice in `gpdk/mcm.py`, with assumptions
in `yields/g100_mcm_28nm.yaml` and the `g100_mcm_28nm` session. It combines G100
Poisson die yield, PTA known-good-die supply, matched-pair KGD yield and three
package options. At the planning assumptions G100 die yield is 89.9% with 133
KGD per wafer, PTA die yield is 98.0% with 1,220 KGD per wafer, and a random
G100/PTA pair is both known-good 86.8% of the time. The silicon interposer gives
the highest package assembly yield at 98.7% and 131.6 good packages per G100
wafer; the organic substrate is cheapest at $44.64 per good package but lowest
yield at 97.7%; the silicon bridge sits between them at $50.37 and 98.5%. These
are F1 planning estimates, not OSAT quotes.

Phase 4 adds the SimPy factory and ATP slice in `gpdk/factory.py`, with
assumptions in `factory/g100_28nm.yaml`, the `factory_atp` engine and the
`g100_factory_28nm` session. The route has 38 steps across 14 tool groups, six
lithography passes on three scanners, batched furnaces, metrology, die attach,
mold and final test, and MTBF/MTTR availability applied as effective process
time. At 600 wafer starts/week the baseline gives 141.5 h cycle time (5.9 days),
61.2 h queue time, 19.7 lots WIP, 598.5 wafers/week throughput and 78,784 good
packages/week at $95.60 per good package. Lithography is the bottleneck at
75.9% utilization. Raising starts 33% to 800 pushes lithography to 97.0%,
doubles cycle time to 299.7 h and raises WIP to 51.9 lots while throughput
plateaus at 729.6 wafers/week, below the 800 start rate. Halving MTTR cuts cycle
time only 1.8% to 139.0 h and lowers lithography utilization to 72.2%, so
downtime is not the binding constraint at baseline. Adding a fourth
lithography scanner at 800 starts restores cycle time to 146.0 h (+3.1% versus
baseline) and WIP to 26.8 lots, reaches 799.6 wafers/week, and shifts the
bottleneck to deposition at 90.3%. Its capital-aware cost is $89.07 per good
package with $240M of scanner capex and $0.92M/week of depreciation, $0.51
above the higher-starts case. It adds about 9,212 good packages/week at roughly
$38.08 of incremental factory cost per additional package, before the $56.35
Phase 3 package cost. At the scenario's $100 planning price, the scanner adds
$14.67M of annual cash flow, pays back in 4.09 years and earns 4.4% annual ROI
after depreciation on its $60M incremental capex, measured against the matched
800-start, three-scanner case. Higher starts adds no capex but carries 299.7 h
cycle time and 51.9 lots WIP. The $100 price is a planning assumption, not a
market forecast. The scanner DCF uses a 60%/80%/100%/100%/100% cash-flow ramp
and a terminal value equal to 20% of incremental capex. At a 10% hurdle rate it
is -$4.71M NPV and 7.3% IRR, so the scanner misses the hurdle at $100; NPV
turns positive at $115. A discount-rate sweep gives +$4.66M NPV at 5%, -$0.29M
at 7.5% and -$12.19M at 15%, with IRR unchanged at 7.3%. A terminal-value sweep
runs from -$12.16M NPV and 2.3% IRR with no residual value to +$2.75M and 11.4%
at 40% of capex; NPV turns positive near a 33% residual. The one-at-a-time
sweep runs from 201.74 years
and -19.5% ROI at a $70 price to
2.07 years and 28.4% at $130; at a $20 gross margin it is 17.96 years and
-14.4%, improving to 1.87 years and 33.5% at $80. The baseline cost combines
the Phase 3 package cost with $39.25 of factory operating cost and
depreciation per good package. The higher-starts case spreads the fixed
operating cost and three-scanner fleet over more output, so its lower $88.55 is
not a capacity-expansion business case. Only lithography scanners are
capital-priced; other tool-group capex is not included. These are F1 planning
estimates, not a foundry MES route card or measured line performance.

## Quick start

```bash
python -m gpdk          # regenerate out/REPORT.md, CSVs, GDS, SVG, PNG
python -m gpdk padring  # rebuild the GRX930 pad ring and ball map
python -m gpdk drc      # check the 12 nm FinFET demo inverter
python -m fabtwin validate scenarios/grx930_28nm_baseline.yaml
python -m fabtwin run scenarios/grx930_28nm_baseline.yaml
python -m fabtwin run scenarios/g100_28nm_baseline.yaml
python -m fabtwin run scenarios/pta_28nm_baseline.yaml
python -m fabtwin run scenarios/pta_photonic_28nm.yaml
python -m fabtwin run scenarios/g100_mcm_28nm.yaml
python -m fabtwin run scenarios/g100_factory_28nm.yaml
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

Dependencies: Python 3.10+, PyYAML, SimPy 4.1+. Pillow is optional and only used
for the PNG layout preview. Tested with Python 3.14, PyYAML 6.0, SimPy 4.1.2,
pytest 9.2, Pillow 12.3.

`export-site` runs scenarios fresh, each into a private store, and writes the
website data bundle: `index.json` plus, under `runs/<scenario-id>/`, each run's
`run.json`, `observations.csv`, `report.md` and engine artifacts unchanged, and
an `observations.json` with the same rows as numbers. With no `--scenario` it
exports every file in `scenarios/`. The
[Twin data](.github/workflows/twin-data.yml) workflow force-pushes the bundle to
the `twin-data` branch on every push to main; gridworkz.com reads it from there
at build time.

```bash
python -m fabtwin export-site /tmp/twin-data --commit "$(git rev-parse HEAD)"
```

The bundle's `browser/` directory is what lets gridworkz.com rerun a scenario
in the visitor's browser: `gpdk-src.zip` (the `fabtwin` and `gpdk` packages and
every input YAML), the pure-Python wheels passed with `--wheel` (SimPy in CI),
and `manifest.json` with each file's hash. The site loads them into
[Pyodide](https://pyodide.org) and calls `fabtwin.browser.run_scenario`, which
runs a scenario's engines in memory with input overrides and returns the
observations without touching the store:

```python
from fabtwin.browser import run_scenario
run_scenario("scenarios/g100_factory_28nm.yaml",
             {"factory": {"wafer_starts_per_week": 700, "tool_groups.litho.tools": 4}})
```

An override is a dotted path into one of the scenario's inputs (`yield`,
`factory`, `package` or `photonic`); a list of entries is indexed by `id`.
Every path must already exist and hold a number. `tests/pyodide_smoke.mjs` runs
the bundle in Pyodide and checks that it reproduces the published runs:

```bash
mkdir -p /tmp/pyodide && cp tests/pyodide_smoke.mjs /tmp/pyodide/
(cd /tmp/pyodide && npm install pyodide@314.0.7 && node pyodide_smoke.mjs /tmp/twin-data)
```

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
lane pitch and wavelength. It remains a product-definition baseline and does
not consume the optical model. Its MCM package definition is a hashed scenario
input. The separate `pta_photonic` session consumes
`photonic/pta_siph_28nm.yaml` and reports insertion loss, phase error, tuning
power, tensor error and temperature rise plus the sensitivity rows; it leaves
the Phase 0 PTA fingerprint unchanged.

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
photonic/pta_siph_28nm.yaml Phase 2 PTA optical, process and 1D thermal assumptions
photonic/<name>_calibration.yaml  optional measured-coefficient calibration input
yields/grx930_28nm.yaml      Phase 1 wafer, defect, assembly and cost assumptions
yields/g100_mcm_28nm.yaml   Phase 3 G100/PTA KGD, assembly and package options
factory/g100_28nm.yaml      Phase 4 G100 fab/ATP route, tools, downtime and what-ifs
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
fabtwin/site_export.py      website data bundle (`export-site`), published to `twin-data`
fabtwin/browser.py          in-memory runner with input overrides, for the site's Pyodide runner
scenarios/grx930_28nm_baseline.yaml  GRX930 Phase 0 baseline
scenarios/g100_28nm_baseline.yaml    G100 Phase 0 baseline
scenarios/pta_28nm_baseline.yaml     PTA topology/package baseline
scenarios/pta_photonic_28nm.yaml     PTA photonic/thermal F1 sensitivity slice
scenarios/g100_mcm_28nm.yaml        G100/PTA MCM assembly and package comparison
scenarios/g100_factory_28nm.yaml    G100 fab/ATP cycle-time and bottleneck study
scenarios/grx930_yield_28nm.yaml    GRX930 die/package yield vertical slice
scenarios/grx930_yield_sensitivity_28nm.yaml  GRX930 yield sensitivity curves
scenarios/grx930_yield_variation_28nm.yaml   GRX930 lot/wafer variation session
scenarios/grx930_yield_wafer_map_28nm.yaml   GRX930 radial/angular/cluster map session
gpdk/dieyield.py             wafer grid, yield, variation, maps and curves
gpdk/mcm.py                  G100/PTA KGD matching and package comparison
gpdk/factory.py              SimPy fab/ATP route, batching, availability and metrics
gpdk/photonics.py            PTA optical, phase, loss, thermal and sensitivity model
gpdk/photonic_calibration.py measured-coefficient calibration contract
gpdk/layout.py               abstract FinFET inverter layout, SVG/PNG
gpdk/drc.py                 fin/gate grid, COAG, enclosure, width/space checks
gpdk/gds.py                 GDSII writer and reader
gpdk/report.py              report and CSV generator
out/REPORT.md               generated node, library and chip report
out/grx930_package.png      pad ring and TFBGA-196 ball map
out/grx930_padring.csv      pad coordinates; out/grx930_ballmap.csv nets
out/fabtwin/<run-id>/       run.json, observations.csv and report.md
out/fabtwin/<run-id>/wafer_map.csv  per-die position, angle, density and yield
out/fabtwin/<run-id>/wafer_map.svg  2D radial/angular/clustered yield map
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
- **The factory model is not a line simulation.** The 38-step route, 14 tool
  groups, process times, MTBF/MTTR and operating cost are planning assumptions.
  Downtime is deterministic availability, not random failures, and the model has
  no dispatch rules, reticle changes, maintenance calendar, transport time or
  operator constraints. Over-capacity what-ifs are a 16-week transient. Only
  lithography scanner capex is included, depreciated straight-line over five
  years; other tool groups are not capital-priced. What-if tool additions
  include only their declared weekly operating-cost delta. Payback, ROI, NPV
  and IRR need the optional package price or gross margin; the current scenario
  uses a $100 planning price. The price/margin sweep is one-at-a-time and holds
  volume, operating cost and depreciation constant; it is not a demand
  forecast. The five-year DCF uses the configured 60/80/100/100/100 ramp and a
  terminal value of 20% of incremental capex; it excludes taxes, working
  capital, price erosion and replacement capex. IRR is n/a when the five-year
  cash flow does not recover capex. The discount-rate curve holds the base
  scanner cash flow, ramp and terminal value fixed; IRR is independent of the
  hurdle rate. Use the
  bottleneck ranking and
  sensitivity direction, not the absolute cycle time, until the route is
  calibrated against a real line.
- **The PTA optical model is not calibrated by default.** There is no qualified
  SiPh PDK or measured PTA data behind `photonic/pta_siph_28nm.yaml`. The optional
  calibration input can replace coefficient assumptions with measured test-
  structure values, but aggregate outputs are still model estimates and remain
  `assumed`. The phase result is per-MZI without common-mode cancellation or
  tuning feedback; the tensor-error proxy is phase error divided by pi; and the
  1D thermal path omits TIM, bump and die-level interface resistances. Use the
  ranking, not the absolute optical numbers, until a measured calibration is
  supplied.

## Provenance

All technology parameters in `tech/grx28.yaml` are our own design targets,
informed by public 28 nm planar HKMG literature and industry-typical geometry.
`tech/grx12f.yaml` is the FinFET reference node, and `tech/12lp_class_ref.yaml`
is a deliberately conservative approximation used only for comparison. Nothing
in this repository is foundry confidential data, and no claim is made that any
foundry's 28 nm process uses these exact values.

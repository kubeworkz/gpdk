# Foundry digital twin: architecture and build plan

**Status:** architecture proposal for review, 2026-11-05.  
**Source concept:** [`fab-sim.md`](fab-sim.md).  
**Existing engines:** `gpdk/` for analytical PPA, `flow/` for Yosys/OpenROAD, and
`tech/` + `chips/` for the current technology and product definitions.

## 1. Decision

Build a **federated manufacturing experiment platform**, not a single
all-in-one simulator.

The platform owns the experiment: inputs, sampling, model versions, artifacts,
uncertainty, and the decision report. Each domain — process/device,
layout/patterning/yield, package/photonics, and factory/ATP — is an engine behind
a stable interface. An engine can be an analytical equation today, a calibrated
surrogate next year, and a TCAD or FDTD solver later without changing the
scenario or the report.

The twin exists to answer decision questions:

- **GRX930:** What is die and package yield at a given defect density, pad count,
  and assembly tolerance? Where is the cost per good package coming from?
- **G100/GRXGPU:** How do die size, power density, KGD binning, and package
  thermal limits change the viable product?
- **PTA:** How do waveguide width, etch depth, line-edge roughness, temperature,
  and alignment tolerances propagate into insertion loss, phase error, tensor
  error, and tuning power?
- **MCM:** What is the yield and cost of matching a known-good electronic die to
  a known-good PTA die, and which packaging option is limiting?
- **Factory:** What do wafer starts, tool availability, batching, and ATP capacity
  do to cycle time, WIP, throughput, and cost per good package?

A **virtual tape-out** is a versioned scenario report with explicit inputs,
model versions, uncertainty, and pass/fail gates. It is not a foundry sign-off
and cannot replace DRC, LVS, ERC, RCX, EM/IR, or reliability sign-off on a
qualified PDK.

## 2. What the three tiers should become

The three tiers in `fab-sim.md` are the right domains, but they are not a
sequential pipeline. In particular, full-chip GDS does not feed TCAD, and a
factory simulator does not consume GDS.

| Source idea | Architecture treatment |
|---|---|
| Tier 1: process and device TCAD | Keep as the **process/device domain**. Use TCAD on test structures and unit cells to build response surfaces; do not attempt full-chip TCAD. |
| Tier 2: lithography and spatial yield | Keep as the **layout/patterning/yield domain**. Start with DRC, critical-area analysis, defect Monte Carlo, and layout-aware proxies; full OPC/lithography is an external future adapter. |
| Tier 3: discrete-event factory | Keep as the **factory/ATP domain**. It consumes a process route, tool model, wafer starts, and package/test flow — not a GDS file. |
| Monte Carlo yield script | Keep the idea. Require calibrated distributions, evidence tags, and reproducible seeds; do not treat a normal distribution as a process model. |
| SQL schema in the document | Keep the entities, but replace the wide per-domain tables with a common observation store plus typed relationships. |
| Final BOM and tape-out manifest | Treat as a **template**, not evidence. The hashes, PDK names, and “signed off” language in the source document are not project results. |

The missing layer in the source document is the one that makes the twin useful:
the **experiment and evidence plane**. Without it, each domain produces numbers
that cannot be compared, reproduced, or defended.

## 3. Architecture

```text
                 product + process + package + scenario
                                   |
                    +--------------+--------------+
                    |    experiment orchestrator  |
                    |  DAG, sampling, seeds, cache|
                    +--------------+--------------+
                                   |
       +----------------+----------+----------+----------------+
       |                |                     |                |
  process/device   layout/yield          photonic/package   factory/ATP
  (gpdk, TCAD)     (KLayout/OpenROAD)    (surrogate/FDTD)   (SimPy)
       |                |                     |                |
       +----------------+----------+----------+----------------+
                                   |
                    observations + artifacts + provenance
                                   |
                  yield / cost / uncertainty / decision report
```

### 3.1 Planes

| Plane | Responsibility | First artifact |
|---|---|---|
| Input | Product, process, package, and scenario definitions | YAML contracts under `scenarios/` and `tech/` |
| Orchestration | Build the DAG, draw samples, assign RNG streams, cache results | `fabtwin` CLI and run manifest |
| Engines | One adapter per domain; no engine imports another engine | `EngineResult` with observations and artifacts |
| Evidence | Store every observation with units, uncertainty, evidence class, and source | SQLite plus a content-addressed artifact directory |
| Decision | Aggregate yield, cost, sensitivity, and confidence | Markdown/JSON report and CSV tables |
| Calibration | Compare against measured PCM/test-structure data and refit | Calibration report with residuals |

The orchestrator is the only component that writes a run to the evidence store.
Engines return data; they do not write prose or silently update a database.

### 3.2 Three domains, four fidelities

Fidelity is chosen per question, not per product. A yield question may need only
F1; a critical device question may justify F3.

| Domain | F0 analytical | F1 stochastic / surrogate | F2 layout-aware | F3 physics |
|---|---|---|---|---|
| Process/device | `gpdk` equations | DoE response surface | Cell/test-structure extraction | TCAD |
| Patterning/layout/yield | Critical area, die-per-wafer | Defect and variation Monte Carlo | KLayout/OpenROAD DRC, custom ORC, wafer maps | Litho/OPC (external) |
| Photonic/package | 1D thermal, RC, phase budget | Tolerance Monte Carlo | GDS stack, field solver, assembly geometry | FEA/FDTD |
| Factory/ATP | Capacity and cost arithmetic | SimPy discrete-event model | Tool calendar and route constraints | Digital shadow (future) |

The first implementation is deliberately mostly F0/F1, with F2 where the repo
already has layout or route data. F3 is added only when a sensitivity result
shows that the decision depends on it.

## 4. Product model

The twin needs separate product definitions before it needs a simulator. The
pre-split `chips/grxgpu_pta.yaml` combined the GPU and the PTA in one
planning block, which was adequate for a block-area estimate but not for a
manufacturing twin. The split is now defined in `chips/g100.yaml` and
`chips/pta.yaml`; `packages/mcm_si.yaml` defines the package stack.

| Entity | Definition | Current evidence |
|---|---|---|
| `grx930` | 28 nm planar digital SoC: four RV64 cores, two NPUs, 96 KB SRAM | Measured legacy baseline plus GRX28 projection |
| `g100` / `grxgpu` | 28 nm digital GPU/throughput chip | Planning assumptions only; 420M gates, 48 MB SRAM, 0.75 GHz target |
| `pta` | Photonic tensor accelerator chiplet, 28 nm-class silicon photonics | Declared topology and package assumptions only; no optical model or qualified SiPh PDK |
| `mcm` | 2.5D silicon interposer or bridge package containing an electronic die and a PTA die | Package assumptions only |

**Recommendation:** commit to the **chiplet baseline**: an electronic chiplet
(`grx930` or `g100`) plus a separate PTA chiplet on an interposer. A monolithic
electronic-plus-photonic die remains a comparison scenario, not the default. The
process, thermal, and known-good-die models are simpler and more honest when the
two technologies are separated.

The product-definition task is complete: G100 and PTA are separate revisioned
YAML files, and the MCM has its own stack definition. No yield model is written
against a combined block.

## 5. Data and contracts

### 5.1 Store

Use SQLite for the first implementation because it is zero-ops, local, and
adequate for scenario metadata and observations. Keep large artifacts — GDS,
OASIS, images, arrays, logs — on disk and reference them by SHA-256. Do not put
binary layout data in the database.

Use SHA-256, not MD5. The source document’s MD5 release checksum is not a
collision-resistant release identity.

### 5.2 Core entities

| Table | Purpose |
|---|---|
| `product` | GRX930, G100, PTA, MCM; revision and owner |
| `process_flow` | Ordered process steps and recipe parameters |
| `package_stack` | Die, interposer, bumps, underfill, lid, and assembly steps |
| `scenario` | The question: inputs, variations, sample count, seed, engines |
| `run` | One execution: scenario, code commit, tool versions, seed, status |
| `artifact` | Path, media type, SHA-256, size, producer |
| `observation` | One metric for one entity in one run; value, unit, uncertainty, evidence |
| `model_version` | Equation set, calibration data, fit parameters, valid range |
| `wafer`, `die`, `package` | Typed entities used to join across domains |
| `optical_channel` | PTA lane, geometry, loss, phase, tuning power |

The central table is narrow:

```text
observation(
  observation_id, run_id, entity_type, entity_id,
  metric, value, unit, uncertainty, evidence_class,
  source_artifact, model_version
)
```

Domain-specific views can pivot this into wafer maps, yield tables, or optical
budgets. The source document’s wide `fab_electronic_metrics`,
`fab_photonic_metrics`, and `twin_yield_analysis` tables should not be copied
literally; they duplicate entities and contain non-portable computed-column
syntax.

### 5.3 Evidence classes

Every parameter and every output carries one of:

| Class | Meaning |
|---|---|
| `measured` | From silicon, PCM, metrology, or a qualified test structure |
| `vendor` | From a PDK, foundry rule deck, or licensed model |
| `literature` | From a cited public source, with a valid range |
| `proxy` | From an open PDK or predictive kit such as ASAP7/GF180 |
| `assumed` | A planning assumption with no external evidence |

A result may not be labelled “predicted yield” if its inputs are mostly
`assumed`. It can be labelled “scenario yield under stated assumptions.” This
distinction is the main defence against false precision.

### 5.4 Units and IDs

- Store SI values with an explicit unit string; no bare floats.
- Use stable IDs: `product:grx930@rev`, `process:grx28@0.1`, `run:<uuid>`.
- Record the tool version, model version, git commit (if available), seed, and
  input hashes in every run.
- Give each stochastic engine its own RNG stream derived from the run seed and
  engine name. Never rely on a global random seed.

## 6. Interfaces

### 6.1 Scenario

A scenario is the only user-facing entry point. It names the question, not the
implementation:

```yaml
id: pta_width_sigma
product: pta@rev-a
process: pta28@0.1
package: mcm_si@0.1.0
samples: 2000
seed: 20261105
engines: [photonic, package, yield]
variations:
  waveguide_width_nm: {distribution: normal, mean: 450.0, sigma: 3.0}
  temperature_k: {distribution: uniform, low: 300.0, high: 340.0}
outputs:
  - insertion_loss_db
  - phase_error_deg
  - tensor_error
  - package_yield
```

The scenario must validate against a schema before any engine runs. Unknown
fields are errors, not silently ignored.

### 6.2 Engine adapter

Every engine implements the same small contract:

```python
class Engine(Protocol):
    name: str
    def validate(self, scenario) -> list[str]: ...
    def run(self, inputs, rng) -> EngineResult: ...
```

`EngineResult` contains observations, artifacts, warnings, and a model version.
It does not contain a formatted report. The report layer owns prose and tables.

### 6.3 CLI

```bash
python -m fabtwin validate scenarios/grx930_baseline.yaml
python -m fabtwin run scenarios/grx930_baseline.yaml --out out/fabtwin
python -m fabtwin report <run-id>
python -m fabtwin compare <run-a> <run-b>
```

A run must be reproducible from the scenario, the repository revision, and the
recorded tool versions. If it is not, it is not a twin result.

## 7. Build sequence

The sequence is chosen to produce a usable decision loop early, not to complete
all three tiers before showing value.

### Phase 0 — Contracts and baseline

**Goal:** one reproducible command that turns existing inputs into a traceable
baseline.

- Split `grxgpu_pta.yaml` into `g100` and `pta`; add an `mcm` package definition.
- Define the scenario, observation, and artifact schemas.
- Wrap the existing `gpdk` analytical path as the first engine.
- Add `fabtwin validate` and `fabtwin run`; write a run manifest with hashes.
- Produce baseline reports for GRX930, G100, and PTA.

**Exit gate:** a clean checkout reproduces the baseline report; every number
points to an input, a model version, and an evidence class. No new physics.
The committed baseline fingerprint is `baselines/phase0_baseline.json`; the
clean-checkout test compares fresh observation rows and input hashes to it.

### Phase 1 — GRX930 die and package vertical slice

**Goal:** answer a real yield and cost question for the product with the most
measured data.

- Die-per-wafer geometry, wafer map, defect-density Monte Carlo, critical-area
  approximation.
- Pad-ring and package assembly model; package yield and cost per good die.
- Reuse the existing layout/DRC data where available; do not invent a foundry
  DRC deck.
- Sensitivity: defect density, die area, pad count, assembly tolerance.

The implemented slice covers the projected GRX930 die grid, Poisson
critical-area yield, package assembly, cost per good package, and seeded
sampling uncertainty. It lives in `gpdk/dieyield.py`, `yields/grx930_28nm.yaml`,
and `scenarios/grx930_yield_28nm.yaml`. Three sensitivity curves — defect
density, pad count, and assembly per-pad defect rate — are emitted by
`scenarios/grx930_yield_sensitivity_28nm.yaml` as 56 `sensitivity_point`
observations, each with the standard error of the sampled mean. The sweep points
are listed under `sensitivity` in the yield assumptions; they are planning
points, not measured process corners.

The variation session `scenarios/grx930_yield_variation_28nm.yaml` adds a
hierarchical lot model: defect density is drawn per lot and again per wafer from
lognormal multipliers, and assembly per-pad ppm is drawn per assembly lot. It
reports the mean die yield, the wafer-to-wafer sigma, the lot-to-lot sigma, and
lot means for assembly yield, good packages and cost. At the planning CVs (15%
lot, 10% wafer) the GRX930 model gives 99.63% mean die yield with 0.036%
wafer-to-wafer and 0.061% lot-to-lot sigma. The sigmas describe modelled
expected yield and exclude die-sampling noise; the distributions are
assumptions, not calibration.

The wafer-map session `scenarios/grx930_yield_wafer_map_28nm.yaml` adds a radial
within-wafer profile, a three-lobe angular term and two Gaussian defect
clusters, and emits zone-level defect-density and yield observations plus
center/edge yield, the edge-to-center ratio and a radial slope. The density is
D0 times a radial factor (1 + edge_boost * (r/R)^p), an angular factor (1 +
amplitude * cos(h * (theta - phase))), and a cluster factor (1 + the sum of
Gaussian hotspot strengths). At the planning profile the model gives 99.31%
mean die yield, 99.63% center yield, 99.10% edge yield and a slope of -5.6e-5 per
mm. The lobes and clusters are assumptions, not measured map data. The run
writes `wafer_map.csv` (one row per die, including angle) and `wafer_map.svg`
(2D heat map with cluster rings), both hashed into the run manifest.

**Exit gate:** yield-versus-defect-density and yield-versus-pad-count curves with
uncertainty; a synthetic case with a known answer passes. Absolute yield remains
an assumption-driven estimate.

The curves and their uncertainty are in place, and the known-answer tests cover
the wafer-grid count, the Poisson yield equation, assembly-yield monotonicity,
curve monotonicity, and seeded reproducibility. The gate is met locally for the
F1 planning model. Absolute yield is still set by the assumptions in
`yields/grx930_28nm.yaml`, not by measured fab data.

### Phase 2 — PTA photonic and thermal vertical slice

**Goal:** connect process variation to optical and tensor-level error.

- Extract the useful equations from `fab-sim.md` into tested modules; fix unit
  and phase conventions before using any result.
- Model waveguide width, etch depth, line-edge roughness, temperature, and
  package alignment as distributions.
- Propagate to insertion loss, phase error, tuning power, and a stated tensor
  error metric.
- Add a 1D/2D thermal path from the electronic die through the interposer to the
  PTA; do not imply full-chip FEA.

**Exit gate:** a sensitivity ranking that says which process parameter dominates
the PTA error budget. No claim of an optimized 397 nm waveguide or a specific
phase error until there is measured calibration data.

### Phase 3 — G100 and MCM assembly

**Goal:** reuse the electronic path and add known-good-die packaging.

- Reuse the GRX930 digital/yield path for G100 with its larger die and power.
- Add KGD binning, die-to-PTA matching, interposer parasitics, crosstalk, and
  alignment loss.
- Compare silicon interposer, organic substrate, and bridge options on yield,
  bandwidth, thermal risk, and cost.

**Exit gate:** package yield and cost per good package for at least two packaging
options; the result identifies the limiting assembly step.

### Phase 4 — Factory and ATP discrete-event model

**Goal:** connect the process route to cycle time, WIP, throughput, and cost.

- Build a SimPy model with wafer lots, process steps, tool classes, batching,
  setup, downtime, and ATP.
- Feed it wafer starts and the process route; feed it die/package results from
  the earlier phases.
- Report cycle time, queue time, tool utilization, bottleneck step, and cost per
  good package.

**Exit gate:** a baseline route and at least two what-if scenarios; the model
identifies the bottleneck and the cycle-time sensitivity to wafer starts.

### Phase 5 — Calibration and virtual tape-out

**Goal:** replace assumptions with evidence where the decision is sensitive.

- Add TCAD, FDTD, or FEA adapters only for the parameters that the sensitivity
  analysis says matter.
- Calibrate against PCM, test structures, metrology, and, when available,
  silicon.
- Carry uncertainty through the full chain and publish a signed scenario report.
- Keep the “not a foundry sign-off” label until a qualified PDK and decks exist.

**Exit gate:** a back-test against measured data with stated residuals. If the
model cannot pass that gate, it remains a planning tool.

## 8. Acceptance tests

A model is not accepted because it produces a plausible number. It is accepted
when these checks pass:

1. **Schema:** every scenario and result validates; unknown fields fail.
2. **Units:** every observation has a unit and a valid range.
3. **Determinism:** the same scenario, seed, and model version reproduce the same
   observations.
4. **Conservation:** die-per-wafer, wafer starts, and package counts reconcile.
5. **Analytic limits:** simple cases match hand calculations.
6. **Monotonicity:** more defects cannot increase yield; wider traces cannot
   increase resistance.
7. **Calibration:** fitted models report residuals and a valid input range.
8. **Cross-domain join:** a die ID can be followed from wafer to package to
   factory cost.
9. **Report reproducibility:** every table in the report is generated from the
   run, not typed by hand.

A model without a test that fails on a wrong input is not ready.

## 9. Risks and non-goals

- **No open 28 nm PDK.** The repository has a planning definition, not a
  qualified LEF/Liberty/GDS/DRC/RCX kit. Absolute area, timing, and yield remain
  targets until an NDA kit is available.
- **No qualified silicon-photonics PDK.** Waveguide loss, phase efficiency,
  heater power, and process corners are assumptions or literature values.
- **No package design kit.** Bump, interposer, warpage, and assembly rules are
  planning models.
- **Full-chip TCAD and full-chip OPC are out of scope.** They are neither
  necessary for the first decisions nor feasible with the current stack.
- **The source document is a concept and requirements catalogue, not an
  executable spec.** Its snippets contain missing imports and unit ambiguities,
  and its tool list needs a licensing and fitness check. The platform owns tested
  code; the document remains the requirements source.
- **Do not use “sign-off” or “tape-out ready” for scenario output.** Those words
  are reserved for a qualified PDK and a complete verification record.
- **Do not carry forward the source document’s release manifest as evidence.**
  Its hashes, proprietary PDK names, and “signed off for mask fabrication”
  status are placeholders, not project artifacts.

## 10. Recommended first move

Approve the federated architecture and start with **Phase 0 plus the GRX930
vertical slice**. GRX930 is the right first product because it has a measured
baseline and a pad-limited die; it lets the team validate the data spine, the
yield arithmetic, and the package model before adding photonic uncertainty.

Run the PTA slice in parallel only at F0/F1: extract the equations, define the
distributions, and build the sensitivity harness. Do not wait for a SiPh PDK to
start the PTA model, and do not pretend the resulting numbers are silicon
predictions.

The first concrete deliverable is deliberately small:

```text
fabtwin/                 platform skeleton, schema, orchestrator, report
scenarios/grx930_28nm_baseline.yaml
scenarios/g100_28nm_baseline.yaml
scenarios/pta_28nm_baseline.yaml
out/fabtwin/<run-id>/run.json, observations.csv, report.md
```

That slice is more valuable than another catalogue of untested snippets: it
establishes the contract every later TCAD, lithography, photonic, package, and
factory model must obey.

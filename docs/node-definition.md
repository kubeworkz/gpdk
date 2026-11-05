# GRX12F node definition (advanced-node reference)

> **Status.** GRX12F is the 12 nm FinFET reference, not the production target.
> The 28 nm planar target is defined in [`tech/grx28.yaml`](../tech/grx28.yaml)
> and documented in [`open-source-28nm-flow.md`](open-source-28nm-flow.md).

GRX12F is our own 12 nm-class FinFET technology target. It is a *definition and
planning model*, not a fabrication-ready process. The machine-readable source of
truth is [`tech/grx12f.yaml`](../tech/grx12f.yaml); this document explains the
choices and records what is still missing.

## 1. Positioning

| Item | GRX12F | Approximate first-generation reference |
|---|---|---|
| Class | 12 nm FinFET, DTCO-optimised | 12 nm FinFET, 14 nm-derived |
| CPP | 84 nm | 90 nm |
| Drawn Lg | 18 nm | 20 nm |
| Fin pitch | 40 nm | 42 nm |
| Fin height / width | 44 / 6.5 nm | 42 / 7.0 nm |
| EOT | 0.85 nm | 0.95 nm |
| Weff per fin | 94.5 nm | 91.0 nm |
| HP supply | 0.80 V | 0.80 V |
| SRAM HD bitcell | 0.088 µm² | 0.100 µm² |

The reference column is a conservative approximation built from public 12/14 nm
literature. It exists so the reports can say "this lever bought X" without
claiming a specific vendor's data.

## 2. Device targets

| Parameter | nFinFET | pFinFET |
|---|---|---|
| Vt (long channel) | 0.27 V | 0.30 V |
| Subthreshold slope | 72 mV/dec | 74 mV/dec |
| DIBL | 42 mV/V | 46 mV/V |
| Ion at 0.8 V | 700 µA/µm | 480 µA/µm |
| Ioff at 0.8 V, 25 °C | 1.0 nA/µm | 0.8 nA/µm |
| Ioff temperature factor | 11× per 60 °C | 11× per 60 °C |

Per fin, with Weff = 94.5 nm: **66 µA** nFinFET Ion, **45 µA** pFinFET Ion,
0.086 fF gate capacitance, 0.21 nA subthreshold leakage at 25 °C. The inverter FO4
at minimum drive is **14.6 ps**.

The model computes:

- `Cox = 3.9 · ε0 / EOT` (40.6 fF/µm² at 0.85 nm)
- `Weff = 2·Hfin + Tfin` (tri-gate)
- `Ion(Vdd)` from the target current density with an overdrive exponent of 1.1
- `Ioff(Vdd, T)` from the target leakage, DIBL shift and temperature factor
- `FO4 = 1.2 · 4 · Cin · Vdd / Idrive`, with an optional 5% COAG benefit

These are planning equations, not BSIM-CMG. They reproduce the trends that the
DTCO decisions depend on and nothing more.

## 3. Cell architecture

Cell height is `tracks × track_pitch`, where the track pitch is the M2 pitch
(64 nm) because M2 carries the rails and row routing. M1 runs vertically for
gate and diffusion escape; M0 is the local interconnect.

| Library | Tracks | Height | Usable M2 tracks | Max fins/device (geometry) |
|---|---|---|---|---|
| 9T | 9.0 | 576 nm | 7.0 | 7 |
| 7.5T | 7.5 | 480 nm | 5.5 | 5 |
| 6T | 6.0 | 384 nm | 4.0 | 4 |
| 5.5T | 5.5 | 352 nm | 3.5 | 4 |

Usable tracks exclude the two power rails. The fin limit is geometric:

```
max_fins_per_device = floor((H - 2·edge_margin - fin_group_gap) / (2·fin_pitch)) + 1
```

with `edge_margin = 20 nm` and `fin_group_gap = 48 nm`. Routing binds well before
this geometric limit, which is why the pin-capacity model, not the fin count,
controls the routable utilisation in the block estimator.

### Width

```
width_cpp = active_cpp + isolation_cpp - (COAG ? 0.5 : 0)
width_nm  = width_cpp × CPP
area      = width_nm × cell_height_nm
```

Isolation overhead:

| Option | Overhead | Meaning |
|---|---|---|
| DDB | 2.0 CPP | Two dummy gates at the cell boundary |
| SDB | 1.0 CPP | One dummy gate shared across the boundary |
| CNOD | 0.0 CPP | Continuous diffusion, isolated by gate bias |

Each cell is modelled as owning its full isolation overhead. That convention
keeps the comparison between options consistent; absolute cell widths would need
to be re-derived from a real library databook.

### Fins

Fins stack **vertically**. Adding a fin increases drive and leakage but does not
widen the cell. This is the single most important correction to the common
"single-fin shrinks the cell" intuition:

- A 1-fin cell and a 2-fin cell at the same track height, isolation and COAG
  setting have identical area in this model.
- Single-fin earns its place by reducing the fin stack, pin count and leakage,
  which is what makes 6T rows and dense routing credible.
- Series stacks (NAND2 NMOS, NOR2 PMOS) double their fins to keep drive, so they
  do consume fin budget.

## 4. BEOL stack

| Layer | Direction | Pitch | Width | Thickness | ILD |
|---|---|---|---|---|---|
| M0 | vertical | 40 nm | 16 nm | 30 nm | 80 nm |
| M1 | vertical | 64 nm | 28 nm | 56 nm | 120 nm |
| M2 | horizontal | 64 nm | 30 nm | 60 nm | 120 nm |
| M3 | vertical | 64 nm | 30 nm | 60 nm | 120 nm |
| M4 | horizontal | 80 nm | 38 nm | 80 nm | 160 nm |
| M5 | vertical | 80 nm | 38 nm | 80 nm | 160 nm |
| M6 | horizontal | 112 nm | 56 nm | 110 nm | 220 nm |
| M7 | vertical | 112 nm | 56 nm | 110 nm | 220 nm |
| M8 | horizontal | 160 nm | 80 nm | 160 nm | 320 nm |
| M9 | horizontal | 400 nm | 200 nm | 400 nm | 800 nm |

Resistance includes a 2 nm barrier per side and the Fuchs-Sondheimer size effect
(39 nm copper mean free path). At 28 nm drawn width the effective resistivity is
about 2.6× bulk copper, which is why M1 is ~35 Ω/µm. Capacitance is parallel-plate
plus two-sided coupling to the neighbouring line. A via pillar is modelled as a
35% resistance reduction versus a single via per layer.

## 5. Layout conventions and demo cell

The demo inverter is 210 × 480 nm (2.5 CPP at 7.5T) with:

- continuous fins (CNOD) on a 40 nm grid, centred at y = 140 and 340 nm
- one gate at x = 84 nm on the 84 nm CPP grid, Lg = 18 nm
- COAG contact inside the gate and over the P fin
- local interconnect (M0) straps for output, gate, VDD and VSS
- M1 pin pads, VIA1 to M2 rails at the top and bottom

The rule deck checks cell height, cell width, fin grid, gate grid, drawn Lg,
minimum width and spacing on every layer, MD-to-fin enclosure, COAG contact
placement, VIA0/VIA1 enclosure, and the presence of both power rails. It reports
zero violations on the generated cell. It is a demonstration deck, not a signoff
deck.

## 6. What a production PDK would still need

This repository deliberately stops at the architecture and DTCO layer. A
fabricable 12 nm PDK also needs:

1. **Complete layer map**: wells, implants, Vt flavors (LVT/SVT/HVT/ULVT), channel
   and halo implants, silicide block, dummy fill, seal ring, alignment marks.
2. **Full device set**: native/high-voltage/IO devices, diodes, decap, ESD,
   bipolar parasitics, varactors, SRAM bit cells and compilers.
3. **Compact models**: BSIM-CMG or BSIM-IMG extraction, corner models (FF/SS/SF/FS),
   mismatch and statistical variation, aging (BTI, HCI, TDDB), self-heating.
4. **Signoff decks**: DRC, LVS, ERC, antenna, density, CMP, EM/IR, ESD, latch-up.
5. **Lithography**: OPC/SRAF models, multi-patterning decomposition and coloring,
   SDB/CNOD printability, via-pillar patterning.
6. **Reliability and yield**: TDDB, electromigration, thermal, package stress,
   defect density, yield ramp, test structures and PCM.
7. **EDA collateral**: LEF, Liberty, SPICE, CDL, GDS, techfile, layer map,
   extraction tech (QRC/StarRC), filler and tap cells.
8. **Silicon correlation**: test chips, ring oscillators, SRAM monitors, thermal
   sensors, and a calibration loop back into every model in this repo.

Nothing in `gpdk/` pretends to cover those. The value here is the decision
framework: it makes the area, frequency, power and routing consequences of a
node/library choice explicit before any of that expensive work begins.

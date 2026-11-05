# GRX28 — 28 nm-class planar PDK and DTCO starter

Generated 2026-11-05 from `tech/grx28.yaml` and
`tech/grx12f.yaml`.

> **What this is.** A transparent, reproducible planning model for a 28 nm-class
> planar platform we own, with the 12 nm FinFET model kept as the advanced-node
> reference. It carries the cell, BEOL, block and layout models needed to compare
> DTCO choices for the quad-core/dual-NPU GRX930 and for G100.
>
> **What this is not.** A foundry-qualified PDK, a calibrated compact model, a
> silicon-verified rule deck, or a statement about any foundry's actual 28 nm
> process. Public-literature numbers are used as targets and the baseline is an
> approximation. No vendor confidential data is used.

## 1. Node definition

| Metric | GRX12F (12 nm FinFET reference) | GRX28 (28 nm planar target) |
|---|---|---|
| Device class | finfet | planar |
| CPP | 84.0 nm | 117.0 nm |
| Drawn gate length | 18.0 nm | 30.0 nm |
| Width-unit pitch | 40.0 nm | 140.0 nm |
| Width-unit height | 44.0 nm | 0.0 nm |
| Width-unit width | 6.5 nm | 120.0 nm |
| EOT | 0.85 nm | 1.4 nm |
| Weff per unit | 94.5 nm | 120.0 nm |
| 9T cell height | 576 nm | 810 nm |
| 7.5T cell height | 480 nm | 675 nm |
| 6T cell height | 384 nm | 540 nm |
| 5.5T cell height | 352 nm | 495 nm |
| Max units/device at 7.5T | 5 | 2 |
| SRAM HD bitcell | 0.088 um2 | 0.135 um2 |
| Core supply | 0.8 V | 0.9 V |
| nMOS Ion | 66.2 uA/unit | 78.0 uA/unit |
| pMOS Ion | 45.4 uA/unit | 38.4 uA/unit |
| Inverter FO4 | 14.62 ps | 23.93 ps |

The cell height is set by track count. A 7.5T GRX28 row is
675 nm, 16.7% shorter than 9T. At 28 nm the width unit
is a gate finger, not a fin: there is no fin height, no single diffusion break and
no COAG. What remains is a fixed-height cell whose drive is set by how many
fingers fit between the rails.

## 2. Device model

| Device | Vt (V) | SS (mV/dec) | DIBL (mV/V) | Ion (uA/unit) | Ioff (nA/unit) | Cgg (fF/unit) | Ron (kohm/unit) |
|---|---|---|---|---|---|---|---|
| nMOS | 0.320 | 80 | 55 | 78.0 | 0.290 | 0.1110 | 11.54 |
| pMOS | 0.350 | 82 | 60 | 38.4 | 0.242 | 0.1110 | 23.44 |

Per-finger values at 0.90 V, 25 C. The
inverter FO4 is 23.93 ps at
minimum drive.

## 3. Standard-cell libraries

| Library | Role | Height | Base units | Isolation | COAG | Cell height (nm) | Avg cell (um2) | Pin capacity | Routable util | FO4 (ps) | Leak (nW) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lp28_7t5_1f | low_power | 7.5T | 1 | DDB | no | 675 | 0.4122 | 1.16 | 0.704 | 23.93 | 0.629 |
| lp28_9t_1f | baseline | 9T | 1 | DDB | no | 810 | 0.4947 | 1.48 | 0.775 | 23.93 | 0.629 |

### Track height sensitivity

| Tracks | Units | Isolation | Track pitch (nm) | Cell height (nm) | Avg cell (um2) | Area index | Routable util | FO4 (ps) |
|---|---|---|---|---|---|---|---|---|
| 9T | 1 | DDB | 90 | 810 | 0.4947 | 100.0% | 0.799 | 23.93 |
| 9T | 1 | DDB | 80 | 720 | 0.4397 | 88.9% | 0.799 | 23.93 |
| 7.5T | 1 | DDB | 90 | 675 | 0.4122 | 83.3% | 0.726 | 23.93 |

Cell height scales with tracks. At 28 nm there is no isolation or COAG lever, and
a single finger does not change a cell's area; it changes drive and leakage. The
only cell-architecture density lever left is the row height.

## 4. BEOL stack

| Layer | Direction | Pitch (nm) | Width (nm) | R (ohm/um) | C (fF/um) | RC (ps/um2) |
|---|---|---|---|---|---|---|
| M1 | vertical | 90 | 45 | 9.30 | 0.1016 | 0.0009 |
| M2 | horizontal | 90 | 45 | 9.30 | 0.1016 | 0.0009 |
| M3 | vertical | 90 | 45 | 8.79 | 0.1066 | 0.0009 |
| M4 | horizontal | 110 | 55 | 5.48 | 0.1016 | 0.0006 |
| M5 | vertical | 110 | 55 | 5.48 | 0.1016 | 0.0006 |
| M6 | horizontal | 160 | 80 | 2.14 | 0.1016 | 0.0002 |
| M7 | vertical | 160 | 80 | 2.14 | 0.1016 | 0.0002 |
| M8 | horizontal | 400 | 200 | 0.26 | 0.1016 | 0.0000 |

| Via | Resistance (ohm) |
|---|---|
| M1-M2 standard via | 6.83 |
| M2-M3 standard via | 6.83 |

Copper resistivity includes the barrier loss and the Fuchs-Sondheimer size effect;
at 28 nm drawn width the effective resistivity is above bulk copper. Via pillars
are a FinFET-node feature and are not offered on GRX28, so the BEOL lever here is
pitch and wire RC, not a new via structure.

## 5. Chip projections

### G100

Throughput-oriented digital GPU on GRX28. The 420M-gate, 48 MB SRAM profile is the pre-split GRXGPU/PTA planning block; the photonic PTA chiplet is now defined separately in chips/pta.yaml and is not part of this die.

**Planning assumptions:** 420M gates, FF ratio 0.06, 48 MB SRAM, 8 mm2 IO, 22 FO4 per stage, activity 0.18, target 0.75 GHz. These are placeholders until the real floorplan and netlist exist.

### Headline (all at or above target frequency)

| Metric | 9T baseline | 7.5T recommended | GRX28 optimised |
|---|---|---|---|
| Area (mm2) | 411.9 | 384.9 | 378.3 |
| Frequency, capability (GHz) | 1.02 | 1.04 | 1.04 |
| Power at target (W) | 126.9 W | 123.1 W | 116.8 W |
| Power density at target (W/mm2) | 0.31 W/mm2 | 0.32 W/mm2 | 0.31 W/mm2 |

The optimised configuration is **7.5T DDB, 2-finger, MBFF-4** (grx28_7t5_1f).


### Lever waterfall

| Step | Library | Tracks | Isolation | Fingers | Native GHz | Area mm2 | Step delta | Cumulative | Power at target |
|---|---|---|---|---|---|---|---|---|---|
| GRX28 9T / 1-finger | grx28_9t_1f | 9 | DDB | 2 | 0.71 | 411.926 | +0.0% | 0.0% | 126.9 W |
| + 7.5T track shrink | grx28_7t5_1f | 7.5 | DDB | 2 | 0.73 | 384.904 | -6.6% | -6.6% | 123.1 W |
| + multibit flip-flops | grx28_7t5_1f | 7.5 | DDB | 2 | 0.72 | 387.534 | +0.7% | -5.9% | 118.1 W |
| + pin-density-aware placement | grx28_7t5_1f | 7.5 | DDB | 2 | 0.73 | 378.317 | -2.4% | -8.2% | 116.8 W |

Cell area is not the same as block area: 7.5T keeps
5.5 usable M2 tracks against
7 at 9T, so routable
utilisation falls from 0.75 to 0.68 and part of the
cell-level gain is given back at placement. The largest single reduction here is
**7.5T track shrink** at 6.6%.

Multibit flops changed area by +0.7% and power by
-5.0 W. With a sequential fraction of only 0.06, MBFF is a
clock-power lever first and an area lever second; at low FF density the extra
placement congestion can cancel the cell-area saving.

### Library choice at the frequency target

| Library | Role | Tracks | Fingers used | Area mm2 | vs 9T | Native GHz | Power at target | Util |
|---|---|---|---|---|---|---|---|---|
| lp28_7t5_1f | low_power | 7.5 | 2 | 384.9 | -6.6% | 0.73 | 123.1 W | 0.70 |
| lp28_9t_1f | baseline | 9.0 | 2 | 411.9 | +0.0% | 0.71 | 126.9 W | 0.78 |

7.5T is the GPU recommendation at this node. The 9T baseline costs
about 7% more area and does not buy back enough routability to justify
it at the SRAM-dominated block scale.

A 6T library is not modelled at this node: 540 nm rows cannot fit the
two width units a series stack needs, so 7.5T is the density floor.
The remaining area lever is implementation quality, not a new cell
architecture: synthesis mapping, placement density and routing closure
are where the open-source flow earns its area.


### GRX930

Four RV64IMAC cores with 8 KB L1 per core, 64 KB shared L2, two NPUs and operand banks, re-targeted from the measured legacy-node test chip to GRX28. A small, latency-oriented control chip: 1.35M NAND2-equivalent gates and 96 KB of on-chip SRAM.

**Projection inputs (netlist-derived):** 0.948M combinational NAND2-equivalents, 67,007 flip-flops, 96 KB SRAM, 25 MHz clock target. The remaining planning assumptions are 20 FO4 per pipeline stage, activity 0.12, and a 178-pad perimeter ring.

### Headline (all at or above target frequency)

| Metric | 9T baseline | 7.5T recommended | GRX28 lowest area |
|---|---|---|---|
| Area (mm2) | 0.88 | 0.82 | 0.80 |
| Frequency, capability (GHz) | 1.94 | 1.94 | 1.94 |
| Power at target (W) | 5.5 mW | 5.5 mW | 5.2 mW |
| Power density at target (W/mm2) | 6 mW/mm2 | 7 mW/mm2 | 7 mW/mm2 |

The lowest area configuration is **7.5T DDB, 1-finger, MBFF-2** (grx28_7t5_1f).


### Measured baseline (silicon)

| Item | Measured |
| --- | --- |
| Die | 165 mm2 (12.9 x 12.9 mm) |
| Core (die minus IO ring) | 140.6 mm2 |
| Content (placed cells + SRAM) | 86.4 mm2 |
| Logic | 46.2 mm2 |
| SRAM | 40.2 mm2 (96 KB in 192 macros) |
| Utilisation, derived | 52.4% |
| Gate count | 1.35M NAND2-equivalent |
| Flip-flops | 67,007 |
| Clock | 25 MHz (40 ns) |
| FPGA prototype clock | 121 MHz |
| Memory port | 8 B/cycle = 200 MB/s |
| Main memory | 64 KB, off-chip |
| Implied logic density | **34.2 um2 per NAND2-eq** |
| Implied SRAM density | **51.1 um2 per bit** |

| Block | mm2 |
|---|---|
| Cores | 23.79 |
| NPUs | 17.73 |
| Operand banks | 2.70 |
| Glue (estimate) | 2.00 |

Node not disclosed in the source data. The implied 34 um2/NAND2 and 51 um2/SRAM bit are consistent with a 0.5 um-class or rad-hard process, roughly one hundred times less dense than GRX28. The stated 46% utilisation does not reconcile with 86.4 mm2 inside 165 mm2 (52.4%); the absolute areas are used throughout and the stated figure is kept only for reference.

A NAND2-equivalent costs 34.2 um2 here and an SRAM bit
costs 51.1 um2. Both numbers are far outside GRX28
territory, which is why the projection below is a **node jump**, not a DTCO saving.

### Same netlist on GRX28

This table holds the netlist (gates, flip-flops, 96 KB SRAM) fixed and changes
only the node. It says nothing about which library is used.

| Metric | As built | GRX28 9T baseline | GRX28 lowest area | Node jump | DTCO inside node |
|---|---|---|---|---|---|
| Logic (mm2) | 46.20 | 0.568 | 0.467 | 81x | -17.7% |
| SRAM (mm2) | 40.20 | 0.147 | 0.147 | 273x | 0.0% |
| Content (mm2) | 86.40 | 0.880 | 0.801 | 98x | -9.0% |
| Die (mm2) | 165 | 13.0 (pad ring) | 13.0 (pad ring) | 12.7x | ~0% |

The node jump is **98x** on content; the DTCO decisions
inside GRX28 are worth **-9.0%** on top of that. Quoting the
product of the two as a single DTCO saving would be dishonest, so they stay in
separate columns. The SRAM ratio (273x) is larger than the logic ratio
(81x) because the as-built macros are unusually large
(0.2094 mm2 for 4 Kb, i.e. 51 um2/bit).

### Package and pin list

| Pin group | Signals | Note |
|---|---|---|
| Clock and reset | 4 | ref clk, por, reset, pll_bypass |
| Boot and config | 4 | boot_mode[1:0], test_mode, scan_en |
| JTAG | 5 | TCK/TMS/TDI/TDO/TRST |
| Debug UART | 4 | TX/RX/RTS/CTS |
| GPIO and interrupts | 8 | bring-up and IRQ |
| Test and status | 2 | fault, heartbeat |
| Memory data | 64 | D[63:0] |
| Memory address | 13 | A[12:0] |
| Memory byte enables | 8 | BE/DM strobes |
| Memory control | 6 | CS/WE/OE/CLK |

| Pad type | Pads |
|---|---|
| Signal pads | 118 |
| IO supply/ground (20 pairs) | 40 |
| Core supply/ground (8 pairs) | 16 |
| Analog / PLL | 4 |
| **Total pads** | **178** |

Selected package: **TFBGA-196** (TFBGA, 0.65 mm pitch, 12 x 12 mm body, 18 spare pads). At 178 pads the design no longer fits the largest QFN
in the catalog (128), so the measured interface forces a BGA; the narrowed and
integrated variants return to QFN.

### What the interface costs

| Interface | Signals | Pads | Pad floor (mm2) | Die (mm2) | Binding | Package |
|---|---|---|---|---|---|---|
| 64-bit off-chip memory (measured interface) | 118 | 178 | 13.0 | 13.0 | pad ring | TFBGA-196 |
| 16-bit DDR at 50 MHz (200 MB/s), memory still off-chip | 68 | 112 | 5.1 | 5.1 | pad ring | QFN-128 |
| 64 KB on-die, no external memory bus | 27 | 57 | 1.3 | 4.0 | assembly minimum | QFN-64 |

At 178 pads (118 signals) the ring needs
**13.0 mm2** against **0.80 mm2** of content:
**93.8% of the die is empty**. No track height, cell library or placement
choice changes that number.

The interface is the largest lever on this chip. Narrowing the 64-bit bus to
16-bit DDR saves **7.8 mm2** of die; integrating the 64 KB
on-die saves **9.0 mm2**, and the memory itself costs only
0.10 mm2. The entire 9T-to-7.5T library ladder is worth
0.08 mm2. That is the order of operations at this node: delete the
legacy bus first, then argue about cells.

That flips the library recommendation for this chip. The whole
9T-to-7.5T ladder moves content by -9.0%, but it moves the **die** by 0%:
every library lands under the same pad ring. The recommendation is 7.5T
single-finger — same die, better pin access and lower leakage than
9T. Density is then spent on integration, not on a smaller chip: the measured
165 mm2 die, at its measured 52% utilisation, would
hold roughly **108x** this content. The node's
real return is latency, power and board area, not die shrinkage.

At the measured 25 MHz clock the 9T projection draws
**5.5 mW** and the area-optimal point
**5.2 mW**, of which
3.4 mW and 3.4 mW is leakage.
The modelled capability is 1.9 GHz, so the 40 ns clock is set
by the design and its memory system, not by GRX28; frequency is not the
binding constraint in either direction.

### Lever waterfall

| Step | Library | Tracks | Isolation | Fingers | Native GHz | Area mm2 | Step delta | Cumulative | Power at target |
|---|---|---|---|---|---|---|---|---|---|
| GRX28 9T / 1-finger | grx28_9t_1f | 9 | DDB | 1 | 1.94 | 0.88 | +0.0% | 0.0% | 5.5 mW |
| + 7.5T track shrink | grx28_7t5_1f | 7.5 | DDB | 1 | 1.94 | 0.82 | -6.8% | -6.8% | 5.5 mW |
| + multibit flip-flops | grx28_7t5_1f | 7.5 | DDB | 1 | 1.94 | 0.82 | +0.2% | -6.7% | 5.2 mW |
| + pin-density-aware placement | grx28_7t5_1f | 7.5 | DDB | 1 | 1.94 | 0.80 | -2.5% | -9.0% | 5.2 mW |

Cell area is not the same as block area: 7.5T keeps
5.5 usable M2 tracks against
7 at 9T, so routable
utilisation falls from 0.77 to 0.71 and part of the
cell-level gain is given back at placement. The largest single reduction here is
**7.5T track shrink** at 6.8%.

Multibit flops changed area by +0.2% and power by
-0.2 mW. With a sequential fraction of only 0.07, MBFF is a
clock-power lever first and an area lever second; at low FF density the extra
placement congestion can cancel the cell-area saving.

### Library choice at the frequency target

| Library | Role | Tracks | Fingers used | Area mm2 | vs 9T | Native GHz | Power at target | Util |
|---|---|---|---|---|---|---|---|---|
| lp28_7t5_1f | low_power | 7.5 | 1 | 0.8 | -6.8% | 1.94 | 5.5 mW | 0.70 |
| lp28_9t_1f | baseline | 9.0 | 1 | 0.9 | +0.0% | 1.94 | 5.5 mW | 0.78 |

This chip is pad-limited: the entire 9T-to-7.5T span saves
0.08 mm2 of content, 0.6% of a 13.0 mm2
pad-ring die. Stay on 7.5T for pin access and yield, and spend the
node on integration headroom instead of a smaller die.

A 6T library is not modelled at this node: 540 nm rows cannot fit the
two width units a series stack needs, so 7.5T is the density floor.
The remaining area lever is implementation quality, not a new cell
architecture: synthesis mapping, placement density and routing closure
are where the open-source flow earns its area.


## 6. Reference layout and DRC demo (GRX12F)

The layout generator is FinFET-specific, so this demo is the 12 nm reference: a
7.5T single-fin inverter with continuous diffusion and COAG, generated at
210 x 480 nm with 21 shapes.
The bundled rule deck found **0 violations**. A 28 nm planar
equivalent needs a different layer stack and rule deck and is not drawn here.

- [grx12f_inv.gds](grx12f_inv.gds) — GDSII, 1 nm database unit
- [grx12f_inv.svg](grx12f_inv.svg) — vector preview
- [grx12f_inv.png](grx12f_inv.png) — raster preview

GDS readback: 21 boundaries across
9 layers, bbox (0, 0, 210, 480) nm.

DRC covers fin/gate grids, cell height, min width/space, MD enclosure, COAG
contact placement, via enclosure and power rails. It is a demonstration deck, not
a signoff deck.

## 7. GRX930 pad ring and package ball map

| Side | Pads | Signals | Supplies |
|---|---|---|---|
| South | 44 | 32 | 12 |
| East | 44 | 32 | 12 |
| North | 45 | 27 | 18 |
| West | 45 | 27 | 18 |

Two staggered rows at a 152.9 um minimum pitch around a
3.60 mm die, with a 90 um corner margin. The ring is generated
from `pins.padring.sides`; every signal group is assigned to exactly one side and
the supply pairs are explicit, so an interface change regenerates the floorplan
instead of silently moving pads.

![GRX930 pad ring and TFBGA-196 ball map](grx930_package.png)

The TFBGA is wire-bond, so these are die pads and substrate balls, not flip-chip
bumps. The 196-ball array uses 178 balls and leaves
18 spare; supplies occupy the outer ring, memory data the lower
half, and control and bring-up I/O the upper half. The ball assignment is a
functional floorplan, not a routed substrate.

- [grx930_padring.csv](grx930_padring.csv) — 178 pads with side, row and coordinates
- [grx930_ballmap.csv](grx930_ballmap.csv) — 196 balls with net assignment
- [grx930_package.svg](grx930_package.svg) — vector version of the figure

## 8. Open-source implementation path

No open 28 nm PDK exists. The open engines are ready; the 28 nm decks are the
blocker.

| Stage | Tool | 28 nm status |
|---|---|---|
| Synthesis | Yosys + ABC | Ready; needs 28 nm Liberty and `dont_use` tuning |
| Floorplan/place/CTS/route | OpenROAD / ORFS | Ready; needs LEF, tech LEF and a platform |
| Flow orchestration | LibreLane 3.0.x / SiliconCompiler | Ready; ships 45 nm predictive, 130/180 nm open kits |
| STA | OpenSTA | Ready; needs 28 nm corners and SPEF |
| RC extraction | OpenRCX | Engine ready; calibrated rules file is the hardest blocker |
| DRC / LVS | KLayout, Magic, Netgen | Engines ready; 28 nm decks must be authored |
| Device calibration | ngspice + PTM 28 nm | Device cards only; no layout or timing collateral |

The first two steps are now measured: FreePDK45/NanGate45 supplies the 45 nm
10T anchor, and GF180MCU supplies the same-PDK 9T/7T track-height A/B (7T saves
20.6% routed cell area and 10.6% wirelength, costs 0.72 ns WNS, both routes DRC-clean).
Next is calibrating power and FO4 against PTM 28 nm cards, then porting the
identical flow to an NDA 28 nm kit. The 45 nm proxy cannot sign off 28 nm area;
only the foundry deck can. Details and sources are in
[the flow plan](../docs/open-source-28nm-flow.md) and
[the measured results](../out/FLOW_RESULTS.md).

## 9. Assumptions and what to do next

1. GRX930 carries measured silicon data in its `as_built` block. G100
   still uses planning assumptions; replace them when its netlist exists.
2. GRX930's 178-pad budget is derived from the measured memory interface, but
   the fixed I/O groups (JTAG, UART, boot, GPIO) and the 1:6 supply ratio are
   assumptions. A real pin list or package datasheet supersedes them.
3. Calibrate the device model against silicon or a foundry compact model before
   trusting absolute power and FO4; the relative rankings are the useful output.
4. GRX28 is a planning target, not a PDK. No open 28 nm PDK exists: PTM 28 nm
   cards cover devices only, and the open layout kits stop at 45 nm predictive
   (FreePDK45/NanGate45) or 130/180 nm manufacturable. A real 28 nm flow needs
   foundry LEF/lib/GDS plus DRC, LVS and RCX decks under NDA.
5. The largest remaining uncertainty is routability: the pin-capacity model is a
   heuristic, not a global router. The OpenROAD flow now measures it on the 45 nm
   proxy and the GF180MCU 9T/7T pair; the NDA 28 nm PDK run is still required
   before trusting the 28 nm util numbers.
6. Rebuild the reports with `python -m gpdk` after any tech or chip change.

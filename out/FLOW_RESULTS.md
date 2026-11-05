# Measured 45 nm, GF180, and ASAP7 track-height A/B

This is the first real Yosys + OpenROAD result in the repository. It replaces
the planning-only area numbers for the logic flow with measured synthesis and
detailed-route data from a structural GRX930 proxy.

**The requested 45 nm 9T-versus-7.5T experiment does not exist in open PDKs.**
FreePDK45/NanGate45 ships one row height, and it is 10 tracks. There is no open
45 nm 9T or 7.5T LEF/Liberty pair. The flow therefore measures three things:

1. a real **45 nm, 10T** synthesis and place-and-route anchor,
2. a real **same-PDK 9T-versus-7T** track-height A/B on GF180MCU, and
3. a real **same-PDK ASAP7 7.5T-versus-6T** synthesis and detailed-route A/B,
   using a 6T-compatible VIA12 derived from the library's own V1 geometry.

GF180MCU is 180 nm. The 9T/7T delta is a row-height sensitivity, not a 45 nm or
28 nm result. It is the closest open multi-height pair; 7T is the nearest real
point below 9T, not 7.5T.

ASAP7 is the closest real 7.5T/6T pair. The released libraries are
`asap7sc7p5t_28` (0.270 µm rows) and `asap7sc6t_26` (0.216 µm rows). No 9T
library is released; 9T appears only as an ICCAD'17 DTCO option. ASAP7 is a
7 nm predictive PDK, so its absolute numbers are not 28 nm data. Its 7.5T/6T
synthesis and routed results are measured below. The 6T release has no technology
LEF; both arms use a derived 6T-compatible VIA12, described with the route.

## What was built

| Item | Value |
|---|---|
| Synthesis | Yosys 0.36+42, ABC |
| Place and route | OpenROAD 26Q4-1108-g6f3f28cc85 |
| 45 nm platform | FreePDK45 / NanGate45, PDKv1.3, 10T, 1.4 µm rows |
| 180 nm platform | GF180MCU 5LM_1TM, 9T (5.04 µm rows) and 7T (3.92 µm rows) |
| Proxy | 4 x 32-bit core slices + 2 x NPU MAC-array slices |
| Full proxy | 23,136 cells, 1,853 flip-flops mapped on NanGate45 |
| Full 45 nm route | 23,136 cells, 35,851 µm² routed cell area at 37%, 0 DRC |
| Detailed-route slice | 1 core + 1 NPU, 9,096 cells, 700 flip-flops |
| ASAP7 platform | ASAP7 7.5T (0.270 µm) and 6T (0.216 µm), RVT/TT |
| ASAP7 synthesis | 7.5T 8,816 cells / 990.113 µm²; 6T 8,040 cells / 750.765 µm² |
| ASAP7 route | 7.5T 1,025 µm² at 31%, 27,238 µm; 6T 796 µm² at 31%, 23,616 µm; both 0 DRC |
| ASAP7 via rule | 6T-compatible 0.018 µm V1, applied to both routed arms |

The RTL is a structural proxy, not GRX930 and not RV64IMAC. It has register
files, ALUs, 16x16 multipliers, control and 8x8 MAC arrays. It has no SRAM
macros, IO ring, PDN, tapcells or antenna diodes. The absolute area is therefore
not the chip area; the **relative** library deltas are the result.

## Synthesis results

Cell area is the sum of the Liberty `area` values for every mapped instance, not
design area. The full and slice rows use the same core/NPU slice RTL,
instantiated four times and twice in the full proxy and once each in the slice.

| Node | Library | Design | Cells | DFF | Cell area (µm²) | vs 9T |
|---|---|---|---:|---:|---:|---:|
| 45 nm | NanGate45 10T | full | 23,136 | 1,853 | 34,662.7 | — |
| 45 nm | NanGate45 10T | slice | 9,096 | 700 | 13,557.2 | — |
| 180 nm | GF180MCU 9T | full | 22,076 | 1,853 | 669,823.3 | baseline |
| 180 nm | GF180MCU 7T | full | 21,757 | 1,853 | 530,184.7 | **−20.85%** |
| 180 nm | GF180MCU 9T | slice | 8,974 | 700 | 265,556.8 | baseline |
| 180 nm | GF180MCU 7T | slice | 8,926 | 700 | 210,161.9 | **−20.86%** |

The 7T row is 22.2% shorter than 9T (3.92 vs 5.04 µm). The mapped cell area falls
20.85%, almost exactly the geometric row-height change. The cell count is nearly
unchanged (−1.45% full, −0.53% slice): the 7T library uses slightly fewer, wider
cells rather than fewer instances.

These are synthesis-only numbers. They do not include placement whitespace,
routing inflation, SRAM or pads.

## Place-and-route results

All P&R runs use the same 50 MHz (20 ns) constraint, 40–50% initial placement
density, `set_max_fanout 16` and a single clock. GF180 uses its five available
metal layers; the 45 nm slice uses metal2-metal6 so the two arms are comparable
in layer count.

| Node | Library | Design | Design area (µm²) | Util | Detailed WL (µm) | WNS (ns) | TNS (ns) | Power | DRC |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 45 nm | NanGate45 10T | full | 35,851 | 37% | 347,859 | 0.00 | 0.00 | 1.77 mW | 0 |
| 45 nm | NanGate45 10T | slice | 13,875 | 41% | 106,406 | 0.00 | 0.00 | 0.669 mW | 0 |
| 180 nm | GF180MCU 9T | slice | 272,017 | 31% | 481,851 | −5.70 | −109.43 | 42.2 mW | 0 |
| 180 nm | GF180MCU 7T | slice | 215,885 | 31% | 430,643 | −6.42 | −139.35 | 29.9 mW | 0 |

The full 45 nm proxy closes timing at 50 MHz and routes with **zero DRC**:
23,136 cells, 35,851 µm² of routed cell area at 37% utilization, 347.9 mm of
detailed wire. Routed cell area is only 3.4% above the 34,662.7 µm² mapped area
(CTS and route optimization add buffers), so the flow is not inflating the
netlist to close. The 9,096-cell slice is the matched-scale arm for the GF180
comparison: 13,875 µm² at 41%, 106.4 mm wire, also zero DRC.

### Measured 9T-to-7T deltas (GF180MCU, same PDK)

| Metric | 9T | 7T | Delta |
|---|---:|---:|---:|
| Synthesized cell area | 265,556.8 µm² | 210,161.9 µm² | **−20.86%** |
| Routed cell area | 272,017 µm² | 215,885 µm² | **−20.63%** |
| Detailed wirelength | 481,851 µm | 430,643 µm | **−10.63%** |
| Cell count | 8,974 | 8,926 | −0.53% |
| WNS at 50 MHz | −5.70 ns | −6.42 ns | **−0.72 ns worse** |
| TNS at 50 MHz | −109.43 ns | −139.35 ns | −29.92 ns worse |
| Total power (reported) | 42.2 mW | 29.9 mW | −29.1% |
| Detailed-route DRC | 0 | 0 | equal |

The area and wirelength wins are real. The timing cost is also real: at the same
50 MHz constraint, 7T is 0.72 ns slower at the worst path and has 29.9 ns more
total negative slack. Both GF180 arms miss 50 MHz because this is a 5 V, 180 nm
library driving a proxy with 16x16 multipliers; the **difference** is the useful
number, not the absolute slack.

Power falls 29%, but the OpenROAD report warned that activity propagation through
registers did not converge after 50 passes. The power rows are recorded for
completeness and are not used for a conclusion.

## ASAP7 7.5T versus 6T

ASAP7 is a 7 nm predictive PDK. The released standard-cell libraries are 7.5T
(`asap7sc7p5t_28`, 0.270 µm rows) and 6T (`asap7sc6t_26`, 0.216 µm rows); both
sites are 0.054 µm wide, so 6T is 20.0% shorter. No released 9T library exists.

The A/B uses the same `grx930_slice` RTL, the same 20 ns SDC and the same
Yosys/OpenROAD recipe as the GF180 slice. Synthesis reads the merged RVT/TT
Liberty for each library; P&R reads the split Liberty files. ASAP7 Liberty is
characterised in ps, so the P&R arms run with `TIME_UNIT=ps`,
`CLK_PERIOD=20000` and `IO_DELAY=2000`. Running the same SDC with ns units gave
a 1000x timing error: the reported `-1979.14` was ps, not ns. The ps-unit run is
the valid one.

### Synthesis

| Library | Row (µm) | Cells | DFF | Cell types | Cell area (µm²) | vs 7.5T |
|---|---:|---:|---:|---:|---:|---:|
| ASAP7 7.5T | 0.270 | 8,816 | 700 | 53 | 990.113 | baseline |
| ASAP7 6T | 0.216 | 8,040 | 700 | 56 | 750.765 | **−24.17%** |

The total hides two different effects. Split by cell class:

| Component | 7.5T (µm²) | 6T (µm²) | Delta |
|---|---:|---:|---:|
| Combinational | 694.139 | 554.810 | **−20.07%** |
| Sequential | 265.356 | 195.955 | **−26.15%** |
| Tie cells | 30.618 | 0 | −100% |
| **Total** | **990.113** | **750.765** | **−24.17%** |
| Total excluding ties | 959.495 | 750.765 | **−21.75%** |

Combinational area falls 20.07%, essentially the 20.0% row-height change. The
total falls farther because the 7.5T flop is `DFFASRHQNx1`, which has both set
and reset controls; the unused reset pin is tied high by 700 `TIEHIx1` cells
(30.618 µm², 3.1% of the 7.5T area). The 6T netlist maps the same 700 flops to
`DFFASHQNx1`/`DFFARHQNx1` cells that need no tie. The 6T flop area is also
26.15% smaller. The 6T netlist has 8.80% fewer instances because ABC selected
wider 6T cells, so the total is not a pure row-height ratio.

### Place and route

| Library | Design area (µm²) | Util | Detailed WL (µm) | WNS (ns) | TNS (ns) | DRC |
|---|---:|---:|---:|---:|---:|---:|
| ASAP7 7.5T | 1,025 | 31% | 27,238 | 0.00 | 0.00 | 0 |
| ASAP7 6T | 796 | 31% | 23,616 | 0.00 | 0.00 | 0 |

Both slices route DRC-clean at 20 ns. The 7.5T slice uses 1,025 µm² of placed
cell area at 31%, 27,238 µm of detailed wire and zero violations; the 6T slice
uses 796 µm² at 31%, 23,616 µm and zero violations. Routed area is 3.5% and 6.0%
above the 990.113 and 750.765 µm² mapped areas respectively (CTS and route
repair add buffers), so neither route is inflating its netlist. WNS/TNS report
0.00 for both because the design meets the 20 ns constraint; this is not a
measured positive margin, and the loose constraint does not resolve a 6T timing
penalty.

**The 6T route uses a 6T-compatible via rule, not a cell repair.** The published
6T LEF has no technology section. Its pin geometry uses 0.018 µm V1 cuts and
0.018 µm M1/M2 bars; the 7.5T `VIA12` landing pad is 0.018 × 0.022 µm on M1 and
0.028 × 0.018 µm on M2, so it cannot fit on C1's 0.018 µm bar. The local
`flow/scripts/make_6t_tech.py` copies the 7.5T tech LEF and changes only
`VIA12` to a 0.018 × 0.018 µm pad, matching the 741 V1 cuts in the stock 6T LEF.
Both arms were rerun with that tech LEF. The earlier pin-pad experiments are not
used. The stock 7.5T route measured 26,936 µm; rerunning 7.5T on the shared
6T-compatible via rule measures 27,238 µm, a 1.1% difference, so the routed A/B
uses the shared-rule 27,238 µm baseline.

### Measured ASAP7 deltas

| Metric | 7.5T | 6T | Delta |
|---|---:|---:|---:|
| Synthesized cell area | 990.113 µm² | 750.765 µm² | **−24.17%** |
| Combinational cell area | 694.139 µm² | 554.810 µm² | **−20.07%** |
| Sequential cell area | 265.356 µm² | 195.955 µm² | −26.15% |
| Cell count | 8,816 | 8,040 | −8.80% |
| Routed cell area | 1,025 µm² | 796 µm² | **−22.34%** |
| Detailed wirelength | 27,238 µm | 23,616 µm | **−13.30%** |
| WNS at 20 ns | 0.00 ns | 0.00 ns | equal |
| TNS at 20 ns | 0.00 ns | 0.00 ns | equal |
| Detailed-route DRC | 0 | 0 | equal |

The measured result is **−24.17% total cell area**, **−20.07% combinational
cell area**, **−22.34% routed cell area** and **−13.30% detailed wirelength**
for 6T. The combinational number is the clean row-height effect; the total and
routed numbers are larger because the 6T netlist also has 8.80% fewer instances
and smaller flops. Both routes are DRC-clean and meet 20 ns, so there is no
measured timing penalty at this constraint.

## What this means

- **Track height is a real area lever.** The 7T library removes 20.6% of routed
  cell area and 10.6% of wirelength on an identical netlist and the same
  placement/routing recipe. Utilization is held at 31% in both arms, so core
  area falls by the same 20.6%. The saving is close to the row-height ratio.
- **ASAP7 measures the same direction at 7 nm.** 7.5T → 6T removes 20.07%
  of combinational cell area for a 20.0% row-height reduction. Total cell area
  falls 24.17% and routed cell area 22.34% because the 7.5T flop/tie overhead
  also disappears; wirelength falls 13.30%. Both routes are DRC-clean at 20 ns,
  so this is a synthesis and routed result.
- **It is not free.** The shorter library is slower at a fixed clock. A 28 nm
  plan that takes the 7.5T area saving must budget for the delay penalty or
  upsize cells, which gives part of the area back.
- **The model's 28 nm 9T-to-7.5T result is not this number.** The planning model
  predicts −6.9% block area because it includes SRAM, IO and a routable-
  utilization penalty. This proxy measures logic-only routed cell area at 180 nm. The
  two numbers answer different questions; do not transfer the 20.6% directly to
  GRX930.
- **45 nm cannot answer the 9T/7.5T question.** NanGate45's only row height is
  10T. The 45 nm run validates the flow, the cell mapping and detailed routing;
  it cannot measure a library that does not exist.
- **The full 23k-cell proxy routes, and it does not change the lever ranking.**
  At 37% utilization, routed cell area is 3.4% above mapped area and the route
  is DRC-clean. The 9k-cell slice remains the matched-scale arm for the 180 nm
  A/B, so the 9T/7T delta is measured at equal scale, not across nodes.

## Limits

- The proxy is not GRX930: no RV64 execution, caches, SRAM macros, IO ring, PDN,
  tapcells, antenna diodes, fill or signoff decks.
- NanGate45 is predictive and non-manufacturable. GF180MCU is a real open PDK,
  but it is 180 nm and 5 V.
- The GF180 A/B and the comparable 45 nm slice are one core and one NPU; the
  full 45 nm anchor is the full quad-core/dual-NPU proxy.
- The 50 MHz constraint is a comparison point. It is not a product target and it
  is not a 28 nm frequency claim.
- Power is not trustworthy because activity propagation did not converge.
- ASAP7 is a predictive 7 nm PDK. The published 6T library has no technology
  LEF, so the 6T route uses a derived tech LEF that changes only `VIA12` to the
  0.018 µm geometry seen in the 6T LEF. Both arms use that rule. This is not a
  foundry-qualified 6T tech LEF; DRC is OpenROAD's check under the derived rule.
- The ASAP7 6T synthesis uses a locally repaired SIMPLE Liberty (premature
  library close). The 7.5T merged library repairs 37 missing `area`
  semicolons in INVBUF. These are formatting fixes, not cell changes.
- The 6T netlist maps to a different cell mix (8,040 vs 8,816 instances), so
  the total-area delta is not a pure row-height ratio.
- No foundry 28 nm data was used or is implied.

## Reproduce

The flow is in [`flow/`](../flow/README.md). The key files are:

- [`flow/rtl/grx930_proxy.v`](../flow/rtl/grx930_proxy.v) — full structural proxy
- [`flow/rtl/grx930_slice.v`](../flow/rtl/grx930_slice.v) — one-core/one-NPU slice
- [`flow/scripts/pnr.tcl`](../flow/scripts/pnr.tcl) — parameterized OpenROAD flow
- [`flow/scripts/area.py`](../flow/scripts/area.py) — Liberty-aware cell area
- [`flow/scripts/collect.py`](../flow/scripts/collect.py) — P&R metric extraction
- [`flow/build/nangate45/full_pnr/openroad.log`](../flow/build/nangate45/full_pnr/openroad.log) — full 45 nm route log
- [`flow/build/nangate45/slice/pnr_orig/openroad.log`](../flow/build/nangate45/slice/pnr_orig/openroad.log) — 45 nm slice route log
- [`flow/build/gf180/slice_9t/pnr_30/openroad.log`](../flow/build/gf180/slice_9t/pnr_30/openroad.log) — 9T route log
- [`flow/build/gf180/slice_7t/pnr_30/openroad.log`](../flow/build/gf180/slice_7t/pnr_30/openroad.log) — 7T route log
- [`flow/build/asap7/75t/pnr_6tvia/openroad.log`](../flow/build/asap7/75t/pnr_6tvia/openroad.log) — 7.5T ASAP7 route log, shared 6T via rule
- [`flow/build/asap7/6t/pnr_6tvia/openroad.log`](../flow/build/asap7/6t/pnr_6tvia/openroad.log) — 6T ASAP7 route log
- [`flow/scripts/repair_liberty.py`](../flow/scripts/repair_liberty.py) — 6T SIMPLE library repair
- [`flow/scripts/make_6t_tech.py`](../flow/scripts/make_6t_tech.py) — derives the 6T-compatible tech LEF
- [`flow/scripts/asap7_6t_tracks.tcl`](../flow/scripts/asap7_6t_tracks.tcl) — 6T track definitions

`flow/build` and `flow/vendor` are gitignored; the logs are local artifacts. The
synthesis and P&R commands are in the flow README. The 45 nm detailed route must
use `NangateOpenCellLibrary.macro.lef`; the `macro.mod.lef` variant stalled
OpenROAD 26Q4 pin access for more than 15 minutes on the same slice.

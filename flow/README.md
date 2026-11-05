# Proxy flow: 45 nm, GF180 and ASAP7

Real Yosys + OpenROAD runs for the GRX930 structural proxy. The results are in
[`out/FLOW_RESULTS.md`](../out/FLOW_RESULTS.md).

## The 45 nm library reality

FreePDK45 / NanGate45 is a **single 10-track library**. Its site is
`FreePDK45_38x28_10R_NP_162NW_34O`, the site height is 1.4 µm, and the M1 pitch
is 0.14 µm: 1.4 / 0.14 = 10 tracks. There is no open 45 nm 9T or 7.5T library to
swap in.

The flow therefore has three arms:

| Arm | Node | Libraries | Purpose |
|---|---|---|---|
| 45 nm anchor | FreePDK45 / NanGate45 | 10T only | Real 45 nm synthesis, placement, CTS and detailed route |
| Track-height A/B | GF180MCU | 9T and 7T, same PDK | Real same-node row-height comparison; 7T is the closest open point below 9T |
| ASAP7 A/B | ASAP7 | 7.5T and 6T, same PDK | Closest real 7.5T/6T pair; synthesis and both detailed routes measured with a 6T-compatible via rule |

GF180MCU is 180 nm, not 45 nm. It is used only for the **relative** 9T-to-7T
delta, because no open 45 nm multi-height pair exists. Do not read its absolute
area or timing as 45 nm data.

ASAP7 is a 7 nm predictive PDK. Its released libraries are 7.5T
(`asap7sc7p5t_28`, 0.270 µm rows) and 6T (`asap7sc6t_26`, 0.216 µm rows); no
9T library is released. The 7.5T-to-6T synthesis and routed deltas are measured
below. Both slices route DRC-clean with a derived 6T-compatible VIA12; the 6T
release has no technology LEF.

## Proxy scale

The RTL is a structural proxy, not the GRX930 netlist and not RV64IMAC.

- `rtl/grx930_proxy.v`: four 32-bit core slices (register file, ALU, multiplier,
  control) plus two NPU slices (8x8 MAC arrays). 23,136 mapped cells, 1,853
  flip-flops on NanGate45.
- `rtl/grx930_slice.v`: one core and one NPU, 9,096 mapped cells, 700 flip-flops.
  This is the matched-scale arm for the GF180 and ASAP7 A/B. The full proxy also completes
  detailed route on NanGate45: 35,851 µm² routed cell area at 37%, 347.9 mm wire, 0 DRC.

No SRAM macros, IO ring, PDN, tapcells or antenna diodes are included. The flow
measures standard-cell logic and signal routing only.

## Prerequisites

- Docker Desktop with the `hdlc/yosys:latest` and `openroad/ubuntu22.04:latest`
  images.
- An OpenROAD-flow-scripts sparse checkout at `flow/vendor/orfs` containing
  `flow/platforms/nangate45`, `flow/platforms/gf180` and `flow/platforms/asap7`.
- ASAP7 7.5T collateral from the ORFS `asap7` platform and the 6T
  `asap7sc6t_26` LEF/Liberty, unpacked under `flow/build/asap7/`.
- Git Bash on Windows. The commands use `ROOT=$(pwd -W)` and
  `MSYS_NO_PATHCONV=1` so Docker Desktop receives Windows paths unchanged.

The vendor checkout and build outputs are gitignored.

## Synthesis

NanGate45, full proxy:

```bash
ROOT=$(pwd -W)
MSYS_NO_PATHCONV=1 docker run --rm -v "$ROOT:/work" -w /work hdlc/yosys:latest bash -lc '
yosys -p "
read_verilog flow/rtl/grx930_proxy.v
hierarchy -check -top grx930_proxy
synth -top grx930_proxy -flatten
dfflibmap -liberty flow/vendor/orfs/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib
abc -liberty flow/vendor/orfs/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib
opt -fast
hilomap -hicell LOGIC1_X1 Z -locell LOGIC0_X1 Z
opt_clean
write_verilog -noattr flow/build/nangate45/grx930_proxy_netlist.v
"'
```

The GF180 Liberty files are gzipped in the platform. Expand them first:

```bash
gunzip -c flow/vendor/orfs/flow/platforms/gf180/lib/gf180mcu_fd_sc_mcu9t5v0__tt_025C_5v00.lib.gz \
  > flow/build/gf180/lib/gf180_9t.lib
gunzip -c flow/vendor/orfs/flow/platforms/gf180/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_5v00.lib.gz \
  > flow/build/gf180/lib/gf180_7t.lib
```

Then repeat the Yosys command with the 9T or 7T Liberty and the matching tie
cells (`gf180mcu_fd_sc_mcu9t5v0__tieh`/`__tiel` or the `mcu7t5v0` pair).

### ASAP7 7.5T and 6T

The ASAP7 Liberty is split by cell family and characterised in ps. Merge each
arm before synthesis with `flow/scripts/merge_liberty.py`. The 6T SIMPLE file
needs `flow/scripts/repair_liberty.py` first: the published file closes the
library prematurely at line 53,405. The 7.5T INVBUF file has 37 `area` lines
without semicolons; the merger repairs them.

```bash
# 7.5T
dfflibmap -liberty flow/build/asap7/lib/75t/asap7sc7p5t_SEQ_RVT_TT.lib
abc -liberty flow/build/asap7/lib/75t/asap7_75t_rvt_tt_abc.lib
hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L

# 6T
dfflibmap -liberty flow/build/asap7/lib/6t/asap7sc6t_SEQ_RVT_TT_nldm_211010.lib
abc -liberty flow/build/asap7/lib/6t/asap7_6t_rvt_tt_abc.lib
hilomap -hicell TIEHIxp5_ASAP7_6t_R H -locell TIELOxp5_ASAP7_6t_R L
```

Both read `flow/rtl/grx930_proxy.v` then `flow/rtl/grx930_slice.v` and run
`synth -top grx930_slice -flatten`. Sum area with `area.py` against the merged
library:

```bash
python flow/scripts/area.py flow/build/asap7/75t/synth/grx930_slice_netlist.v \
  flow/build/asap7/lib/75t/asap7_75t_rvt_tt.lib \
  --json flow/build/asap7/75t/synth/area.json
```

`flow/scripts/area.py` sums the mapped cell area from the netlist and Liberty:

```bash
python flow/scripts/area.py \
  flow/build/gf180/synth_9t/grx930_proxy_netlist.v \
  flow/build/gf180/lib/gf180_9t.lib \
  --json flow/build/gf180/full_9t_area.json
```

## Place and route

`flow/scripts/pnr.tcl` is parameterized by environment variables. The NanGate45
slice command is:

```bash
ROOT=$(pwd -W)
MSYS_NO_PATHCONV=1 docker run --rm -u 0 -v "$ROOT:/work" -w /work \
  -e TECH_LEF=flow/vendor/orfs/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef \
  -e SC_LEF=flow/vendor/orfs/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef \
  -e LIB_FILES=flow/vendor/orfs/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib \
  -e SITE=FreePDK45_38x28_10R_NP_162NW_34O \
  -e NETLIST=flow/build/nangate45/slice/grx930_slice_netlist.v \
  -e SDC=flow/scripts/proxy.sdc \
  -e OUT_DIR=flow/build/nangate45/slice/pnr_orig \
  -e DESIGN=grx930_slice \
  -e MAX_ROUTING_LAYER=metal6 \
  -e CORE_UTIL=0.40 \
  -e PLACE_DENSITY=0.50 \
  -e CTS_BUFS='CLKBUF_X1 CLKBUF_X2 BUF_X4' \
  -e ROOT_BUF=CLKBUF_X1 \
  openroad/ubuntu22.04:latest bash -lc '
    export PATH=/OpenROAD/install/bin:$PATH
    openroad -no_init -exit flow/scripts/pnr.tcl
  '
```

For the full proxy, keep the same command but set `NETLIST` to
`flow/build/nangate45/grx930_proxy_netlist.v`, `DESIGN=grx930_proxy`,
`OUT_DIR=flow/build/nangate45/full_pnr`, `CORE_UTIL=0.35` and
`PLACE_DENSITY=0.45`. That is the reported full 45 nm run.

**Use `NangateOpenCellLibrary.macro.lef`, not `...macro.mod.lef`.** With the
modified LEF, OpenROAD 26Q4 stalled in detailed-route pin access for over 15
minutes on the 9k-cell slice. The original LEF completed the same design in
about 8 minutes with zero DRC, and the full proxy in about 13 minutes. This is a
flow finding, not a library-quality statement.

For GF180, use the same command with these substitutions:

```text
TECH_LEF=flow/vendor/orfs/flow/platforms/gf180/lef/gf180mcu_5LM_1TM_9K_{9t,7t}_tech.lef
SC_LEF=flow/vendor/orfs/flow/platforms/gf180/lef/gf180mcu_5LM_1TM_9K_{9t,7t}_sc.lef
LIB_FILES=flow/build/gf180/lib/gf180_{9t,7t}.lib
SITE=GF018hv5v_green_sc9          # 9T; use GF018hv5v_mcu_sc7 for 7T
MIN_ROUTING_LAYER=Metal2
MAX_ROUTING_LAYER=Metal5
CLOCK_LAYER=Metal4
IO_H_LAYER=Metal3
IO_V_LAYER=Metal4
CORE_UTIL=0.30
PLACE_DENSITY=0.40
CTS_BUFS=gf180mcu_fd_sc_mcu{9t,7t}5v0__clkbuf_4 ... __clkbuf_8 ... __buf_4
ROOT_BUF=gf180mcu_fd_sc_mcu{9t,7t}5v0__clkbuf_4
```

The exact commands that produced the reported numbers are also recorded in the
OpenROAD logs under `flow/build/gf180/slice_{9t,7t}/pnr_30/`.

### ASAP7

`flow/build/asap7/run_pnr_ns.sh` drives both arms with `SITE=asap7sc7p5t` or
`asap7sc6t`, `MIN_ROUTING_LAYER=M2`,
`MAX_ROUTING_LAYER=M7`, `CLOCK_LAYER=M4`, `CORE_UTIL=0.30`,
`PLACE_DENSITY=0.55`, `CORE_SPACE=1.0`, `TIME_UNIT=ps`, `CLK_PERIOD=20000`
and `IO_DELAY=2000`. The 7.5T track file is the ORFS
`flow/platforms/asap7/openRoad/make_tracks.tcl`; 6T uses
`flow/scripts/asap7_6t_tracks.tcl` (M1 offset 0.0, M2 y offsets 0.036-0.216).

The 6T release has no technology LEF. Its pins use 0.018 µm V1 cuts; the
published 7.5T `VIA12` needs a 0.022 µm-tall M1 landing pad and cannot fit on
the 0.018 µm 6T input bars. `flow/scripts/make_6t_tech.py` copies the 7.5T tech
LEF and changes only `VIA12` to 0.018 × 0.018 µm. Both arms are routed with
`flow/build/asap7/lef/asap7_tech_6t.lef`, so the comparison uses one via rule.
Generate it with:

```bash
python flow/scripts/make_6t_tech.py \
  flow/vendor/orfs/flow/platforms/asap7/lef/asap7_tech_1x_201209.lef \
  flow/build/asap7/lef/asap7_tech_6t.lef
```

ASAP7 Liberty is in ps. Do **not** run the 20.0 SDC with `TIME_UNIT=ns`: the
period is then read as 20 ps and WNS is 1000x too large. Use
`CLK_PERIOD=20000` with ps units.

The 7.5T arm completes at 1,025 µm², 31%, 27,238 µm wire, 0 DRC, WNS/TNS 0.00.
The 6T arm completes at 796 µm², 31%, 23,616 µm wire, 0 DRC, WNS/TNS 0.00. The
6T cell LEF is the stock published file; no cell geometry is changed. The stock
7.5T route was 26,936 µm; rerunning it on the shared 6T-compatible via rule
gives 27,238 µm, so the routed A/B uses the shared-rule number.

`flow/scripts/collect.py` extracts area, utilization, WNS/TNS, detailed-route
wirelength and DRC count from the OpenROAD log and DRC report.

## What was measured

| Run | Node | Library | Cells | Cell area (µm²) | Design area (µm²) | Wirelength (µm) | WNS (ns) | DRC |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Full synthesis | 45 nm | 10T | 23,136 | 34,662.7 | — | — | — | — |
| Full P&R | 45 nm | 10T | 23,136 | 34,662.7 | 35,851 | 347,859 | 0.00 | 0 |
| Slice P&R | 45 nm | 10T | 9,096 | 13,557.2 | 13,875 | 106,406 | 0.00 | 0 |
| Full synthesis | 180 nm | 9T | 22,076 | 669,823.3 | — | — | — | — |
| Full synthesis | 180 nm | 7T | 21,757 | 530,184.7 | — | — | — | — |
| Slice P&R | 180 nm | 9T | 8,974 | 265,556.8 | 272,017 | 481,851 | -5.70 | 0 |
| Slice P&R | 180 nm | 7T | 8,926 | 210,161.9 | 215,885 | 430,643 | -6.42 | 0 |
| Slice synthesis | ASAP7 | 7.5T | 8,816 | 990.113 | — | — | — | — |
| Slice synthesis | ASAP7 | 6T | 8,040 | 750.765 | — | — | — | — |
| Slice P&R | ASAP7 | 7.5T | 8,816 | 990.113 | 1,025 | 27,238 | 0.00 | 0 |
| Slice P&R | ASAP7 | 6T | 8,040 | 750.765 | 796 | 23,616 | 0.00 | 0 |

The GF180 9T-to-7T measured deltas are **−20.85% synthesized cell area**,
**−20.63% routed cell area**, **−10.63% wirelength**, and **0.72 ns worse WNS** at the
same 50 MHz constraint. Both detailed routes are DRC-clean.

The ASAP7 7.5T-to-6T measured deltas are **−24.17% total cell area**,
**−20.07% combinational cell area**, **−22.34% routed cell area** and
**−13.30% detailed wirelength** for a 20.0% row-height reduction. Both slices
are DRC-clean at 20 ns and meet the 20 ns constraint. See
[`out/FLOW_RESULTS.md`](../out/FLOW_RESULTS.md) for the interpretation and
limitations.

## Limits

- The proxy is not GRX930. It has no RV64 execution, caches, SRAM macros, IO ring,
  PDN, tapcells, antenna diodes or signoff decks.
- The 45 nm anchor is a predictive, non-manufacturable PDK.
- GF180 is 180 nm. Its 9T/7T delta is a track-height sensitivity, not a 28 nm
  result.
- The 50 MHz constraint is a comparison point, not a product target. GF180 9T/7T
  both miss it; the delta is the useful number.
- ASAP7 is a predictive 7 nm PDK. Its 7.5T/6T delta is not 28 nm data. The
  published 6T release has no technology LEF, so the 6T route uses a derived
  tech LEF that changes only `VIA12` to the 0.018 µm geometry seen in the 6T
  library; both arms use it. This is not a foundry-qualified 6T tech LEF.
- The 6T SIMPLE Liberty is locally repaired (premature library close), and the
  7.5T merged Liberty repairs 37 missing `area` semicolons in INVBUF. These are
  formatting fixes, not cell changes.
- Power reports are unreliable because activity propagation through registers
  did not converge. They are recorded but not used for a conclusion.
- Detailed route is reported both on the full 23k-cell proxy and on the 9k-cell
  slice; the slice is the equal-scale arm for the GF180 A/B.

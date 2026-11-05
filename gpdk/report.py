"""Generate the GRX28 node, library and chip DTCO reports."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from dataclasses import replace

from .asbuilt import AsBuilt, node_jump
from .beol import layer_table, via_resistance_ohm
from .block import (
    BlockConfig,
    BlockEstimate,
    load_chips,
    pad_limited_die_mm2,
)
from .package import PinBudget, choose_package, die_floor
from .padring import build_floorplan, write_artifacts
from .cells import Library, load_libraries
from .device import DeviceModel
from .drc import check, summarize
from .dtco import best_step, build_steps, lever_table, library_matrix, reference_pair
from .gds import read_gds, write_gds
from .layout import inverter_layout, to_png, to_svg
from .tech import ROOT, Tech, load_tech

OUT = ROOT / "out"


def _table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _num(value: float, digits: int = 1) -> str:
    """Two decimals below 10 so sub-mm2 blocks do not round to one digit."""
    return f"{value:.2f}" if abs(value) < 10 else f"{value:.{digits}f}"


def _power(watts: float) -> str:
    return f"{watts * 1000:.1f} mW" if abs(watts) < 1.0 else f"{watts:.1f} W"


def _power_delta(watts: float) -> str:
    return f"{watts * 1000:+.1f} mW" if abs(watts) < 1.0 else f"{watts:+.1f} W"


def _power_density(w_per_mm2: float) -> str:
    if abs(w_per_mm2) < 0.1:
        return f"{w_per_mm2 * 1000:.0f} mW/mm2"
    return f"{w_per_mm2:.2f} W/mm2"


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _node_rows(ref: Tech, tech: Tech) -> list[list[object]]:
    ref_dev, dev = DeviceModel(ref), DeviceModel(tech)
    rows: list[list[object]] = []

    def add(metric: str, a: object, b: object, unit: str = "") -> None:
        rows.append([metric, f"{a}{unit}", f"{b}{unit}"])

    add("Device class", ref.device_kind, tech.device_kind)
    add("CPP", ref.cpp_nm, tech.cpp_nm, " nm")
    add("Drawn gate length", ref.gate_length_nm, tech.gate_length_nm, " nm")
    add("Width-unit pitch", ref.fin_pitch_nm, tech.fin_pitch_nm, " nm")
    add("Width-unit height", ref.fin_height_nm, tech.fin_height_nm, " nm")
    add("Width-unit width", ref.fin_width_nm, tech.fin_width_nm, " nm")
    add("EOT", ref.eot_nm, tech.eot_nm, " nm")
    add("Weff per unit", f"{ref.weff_per_fin_nm:.1f}", f"{tech.weff_per_fin_nm:.1f}", " nm")
    add("9T cell height", f"{ref.cell_height_nm(9):.0f}", f"{tech.cell_height_nm(9):.0f}", " nm")
    add("7.5T cell height", f"{ref.cell_height_nm(7.5):.0f}", f"{tech.cell_height_nm(7.5):.0f}", " nm")
    add("6T cell height", f"{ref.cell_height_nm(6):.0f}", f"{tech.cell_height_nm(6):.0f}", " nm")
    add("5.5T cell height", f"{ref.cell_height_nm(5.5):.0f}", f"{tech.cell_height_nm(5.5):.0f}", " nm")
    add("Max units/device at 7.5T", ref.max_fins_per_device(7.5), tech.max_fins_per_device(7.5))
    add("SRAM HD bitcell", ref.sram.hd_bitcell_um2, tech.sram.hd_bitcell_um2, " um2")
    add("Core supply", ref.vdd_hp, tech.vdd_hp, " V")
    add("nMOS Ion", f"{ref_dev.ion_per_fin_ua('n', ref.vdd_hp):.1f}",
        f"{dev.ion_per_fin_ua('n', tech.vdd_hp):.1f}", " uA/unit")
    add("pMOS Ion", f"{ref_dev.ion_per_fin_ua('p', ref.vdd_hp):.1f}",
        f"{dev.ion_per_fin_ua('p', tech.vdd_hp):.1f}", " uA/unit")
    add("Inverter FO4", f"{ref_dev.stage(1, 1, ref.vdd_hp).fo4_ps:.2f}",
        f"{dev.stage(1, 1, tech.vdd_hp).fo4_ps:.2f}", " ps")
    return rows


def _sensitivity_rows(tech: Tech) -> list[list[object]]:
    if tech.device_kind == "planar":
        combos = [
            (9.0, 1, "DDB", tech),
            (9.0, 1, "DDB", tech.with_beol_scale(80.0 / 90.0)),
            (7.5, 1, "DDB", tech),
        ]
    else:
        combos = [
            (9.0, 2, "DDB", tech),
            (9.0, 2, "SDB", tech),
            (9.0, 2, "CNOD", tech),
            (7.5, 2, "DDB", tech),
            (7.5, 2, "SDB", tech),
            (7.5, 1, "SDB", tech),
            (6.0, 1, "SDB", tech),
            (6.0, 1, "CNOD", tech),
            (5.5, 1, "CNOD", tech),
        ]
    base = Library.build(
        tech, id="sens_base", label="baseline", tracks=9.0, base_fins=1,
        isolation="DDB", coag=False,
    ).avg_cell_area_um2
    rows: list[list[object]] = []
    for i, (tracks, fins, iso, node) in enumerate(combos):
        lib = Library.build(
            node,
            id=f"sens_{i}",
            label="",
            tracks=tracks,
            base_fins=fins,
            isolation=iso,
            coag=tech.device_kind == "finfet",
        )
        rows.append(
            [
                f"{tracks:g}T",
                fins,
                iso,
                f"{node.track_pitch_nm:.0f}",
                f"{lib.cell_height_nm:.0f}",
                f"{lib.avg_cell_area_um2:.4f}",
                f"{lib.avg_cell_area_um2 / base * 100:.1f}%",
                f"{lib.routable_utilization(pin_aware=True):.3f}",
                f"{lib.fo4_ps:.2f}",
            ]
        )
    return rows


def _device_rows(tech: Tech) -> list[list[object]]:
    dev = DeviceModel(tech)
    rows = []
    for pol, label in (("n", "nMOS"), ("p", "pMOS")):
        p = tech.nfet if pol == "n" else tech.pfet
        rows.append(
            [
                label,
                f"{p.vt_v:.3f}",
                f"{p.ss_mv_dec:.0f}",
                f"{p.dibl_mv_v:.0f}",
                f"{dev.ion_per_fin_ua(pol, tech.vdd_hp):.1f}",
                f"{dev.ioff_per_fin_na(pol, tech.vdd_hp):.3f}",
                f"{dev.cap_per_fin_ff(pol):.4f}",
                f"{dev.ron_per_fin_ohm(pol, tech.vdd_hp)/1000:.2f}",
            ]
        )
    return rows


def _asbuilt_md(
    cfg: BlockConfig,
    ab: AsBuilt,
    node_est: BlockEstimate,
    best_est: BlockEstimate,
    tech: Tech,
) -> str:
    jump = node_jump(node_est, ab)
    best_jump = node_jump(best_est, ab)

    spec = cfg.pin_spec or {}
    selected = str(spec.get("selected") or next(iter(spec.get("variants", {})), ""))
    base_pins = PinBudget.from_spec(spec, selected) if selected else None
    pin_rows = (
        [[g.name, g.signals, g.note] for g in base_pins.groups]
        if base_pins
        else []
    )
    supply_rows: list[list[object]] = []
    variant_rows: list[list[object]] = []
    variant_areas: dict[str, float] = {}
    base_die = best_est.die_area_mm2
    base_floor = best_est.pad_floor_mm2
    base_pkg = None
    if base_pins is not None:
        supply_rows = [
            ["Signal pads", base_pins.signal_pads],
            [f"IO supply/ground ({base_pins.io_supply_pairs} pairs)", base_pins.io_supply_pads],
            [f"Core supply/ground ({base_pins.core_pairs} pairs)", base_pins.core_supply_pads],
            ["Analog / PLL", base_pins.analog_pads],
            ["**Total pads**", f"**{base_pins.total_pads}**"],
        ]
        base_pkg = choose_package(base_pins.total_pads, base_die**0.5)
        for key in spec.get("variants", {}):
            pb = PinBudget.from_spec(spec, key)
            floor = pad_limited_die_mm2(replace(cfg, pad_pins=pb.total_pads))
            area, binding = die_floor(
                best_est.total_area_mm2, floor, best_est.assembly_floor_mm2
            )
            pkg = choose_package(pb.total_pads, area**0.5)
            variant_areas[key] = area
            variant_rows.append(
                [
                    pb.label,
                    pb.signal_pads,
                    pb.total_pads,
                    f"{floor:.1f}",
                    f"{area:.1f}",
                    binding,
                    pkg.name if pkg else "none",
                ]
            )
    else:
        base_floor = best_est.pad_floor_mm2
    block_labels = {
        "cores": "Cores",
        "npus": "NPUs",
        "operand_banks": "Operand banks",
        "glue": "Glue (estimate)",
    }
    block_rows = [
        [block_labels.get(name, name.replace("_", " ").capitalize()), f"{area:.2f}"]
        for name, area in ab.blocks_mm2.items()
    ]
    dtco_pct = (best_est.total_area_mm2 / node_est.total_area_mm2 - 1.0) * 100.0
    on_die_main_mm2 = best_est.sram_area_mm2 * ab.offchip_kb / max(cfg.sram_mb * 1024, 1e-9)
    on_die_main_pct = on_die_main_mm2 / best_est.die_area_mm2 * 100.0
    node_logic_dtco = (best_est.cell_area_mm2 / node_est.cell_area_mm2 - 1.0) * 100.0
    util_delta = ab.derived_util - (ab.stated_util or ab.derived_util)
    util_note = (
        f"The stated {ab.stated_util:.0%} utilisation does not reconcile with "
        f"{ab.content_mm2:.1f} mm2 inside {ab.die_mm2:.0f} mm2 ({ab.derived_util:.1%}); "
        "the absolute areas are used throughout and the stated figure is kept "
        "only for reference."
        if abs(util_delta) > 0.02
        else ""
    )

    opt_label = "lowest area" if cfg.as_built is not None else "optimised"
    ladder = "9T-to-7.5T" if tech.device_kind == "planar" else "9T-to-6T"

    package_md = ""
    if base_pins is not None:
        empty = max(0.0, 1.0 - best_est.total_area_mm2 / base_die)
        narrow = variant_areas.get("narrow_ddr", base_die)
        integrated = variant_areas.get("integrated", base_die)
        dtco_mm2 = (best_est.total_area_mm2 - node_est.total_area_mm2) * -1.0
        pkg_line = (
            f"Selected package: **{base_pkg.name}** ({base_pkg.kind}, "
            f"{base_pkg.pitch_mm:.2f} mm pitch, {base_pkg.body_mm:.0f} x "
            f"{base_pkg.body_mm:.0f} mm body, "
            f"{base_pkg.pads - base_pins.total_pads} spare pads)."
            if base_pkg
            else "No catalog package fits; a custom substrate is required."
        )
        package_md = f"""### Package and pin list

{_table(["Pin group", "Signals", "Note"], pin_rows)}

{_table(["Pad type", "Pads"], supply_rows)}

{pkg_line} At {base_pins.total_pads} pads the design no longer fits the largest QFN
in the catalog (128), so the measured interface forces a BGA; the narrowed and
integrated variants return to QFN.

### What the interface costs

{_table(["Interface", "Signals", "Pads", "Pad floor (mm2)", "Die (mm2)", "Binding", "Package"], variant_rows)}

At {base_pins.total_pads} pads ({base_pins.signal_pads} signals) the ring needs
**{base_floor:.1f} mm2** against **{best_est.total_area_mm2:.2f} mm2** of content:
**{empty:.1%} of the die is empty**. No track height, cell library or placement
choice changes that number.

The interface is the largest lever on this chip. Narrowing the 64-bit bus to
16-bit DDR saves **{base_die - narrow:.1f} mm2** of die; integrating the 64 KB
on-die saves **{base_die - integrated:.1f} mm2**, and the memory itself costs only
{on_die_main_mm2:.2f} mm2. The entire {ladder} library ladder is worth
{dtco_mm2:.2f} mm2. That is the order of operations at this node: delete the
legacy bus first, then argue about cells.
"""

    return f"""### Measured baseline (silicon)

| Item | Measured |
| --- | --- |
| Die | {ab.die_mm2:.0f} mm2 ({ab.die_xy_mm[0]:.1f} x {ab.die_xy_mm[1]:.1f} mm) |
| Core (die minus IO ring) | {ab.core_mm2:.1f} mm2 |
| Content (placed cells + SRAM) | {ab.content_mm2:.1f} mm2 |
| Logic | {ab.logic_mm2:.1f} mm2 |
| SRAM | {ab.sram_mm2:.1f} mm2 ({ab.sram_kb:.0f} KB in {ab.sram_macros} macros) |
| Utilisation, derived | {ab.derived_util:.1%} |
| Gate count | {ab.nand2_eq_m:.2f}M NAND2-equivalent |
| Flip-flops | {ab.ff_count:,.0f} |
| Clock | {ab.clock_mhz:.0f} MHz ({ab.clock_ns:.0f} ns) |
| FPGA prototype clock | {ab.fpga_clock_mhz:.0f} MHz |
| Memory port | 8 B/cycle = {8 * ab.clock_mhz:.0f} MB/s |
| Main memory | {ab.offchip_kb:.0f} KB, off-chip |
| Implied logic density | **{ab.logic_um2_per_nand2:.1f} um2 per NAND2-eq** |
| Implied SRAM density | **{ab.sram_um2_per_bit:.1f} um2 per bit** |

{_table(["Block", "mm2"], block_rows)}

{ab.node_note} {util_note}

A NAND2-equivalent costs {ab.logic_um2_per_nand2:.1f} um2 here and an SRAM bit
costs {ab.sram_um2_per_bit:.1f} um2. Both numbers are far outside {tech.name}
territory, which is why the projection below is a **node jump**, not a DTCO saving.

### Same netlist on {tech.name}

This table holds the netlist (gates, flip-flops, 96 KB SRAM) fixed and changes
only the node. It says nothing about which library is used.

{_table(["Metric", "As built", f"{tech.name} {node_est.tracks:g}T baseline", f"{tech.name} {opt_label}", "Node jump", "DTCO inside node"], [
    ["Logic (mm2)", f"{ab.logic_mm2:.2f}", f"{node_est.cell_area_mm2:.3f}",
     f"{best_est.cell_area_mm2:.3f}", f"{jump.logic_ratio:.0f}x", f"{node_logic_dtco:+.1f}%"],
    ["SRAM (mm2)", f"{ab.sram_mm2:.2f}", f"{node_est.sram_area_mm2:.3f}",
     f"{best_est.sram_area_mm2:.3f}", f"{jump.sram_ratio:.0f}x", "0.0%"],
    ["Content (mm2)", f"{ab.content_mm2:.2f}", f"{node_est.total_area_mm2:.3f}",
     f"{best_est.total_area_mm2:.3f}", f"{jump.content_ratio:.0f}x", f"{dtco_pct:+.1f}%"],
    ["Die (mm2)", f"{ab.die_mm2:.0f}", f"{node_est.die_area_mm2:.1f} ({node_est.die_binding})",
     f"{best_est.die_area_mm2:.1f} ({best_est.die_binding})", f"{jump.die_ratio:.1f}x", "~0%"],
])}

The node jump is **{jump.content_ratio:.0f}x** on content; the DTCO decisions
inside {tech.name} are worth **{dtco_pct:+.1f}%** on top of that. Quoting the
product of the two as a single DTCO saving would be dishonest, so they stay in
separate columns. The SRAM ratio ({jump.sram_ratio:.0f}x) is larger than the logic ratio
({jump.logic_ratio:.0f}x) because the as-built macros are unusually large
({ab.sram_macro_mm2:.4f} mm2 for 4 Kb, i.e. {ab.sram_um2_per_bit:.0f} um2/bit).

{package_md}
That flips the library recommendation for this chip. The whole
{ladder} ladder moves content by {dtco_pct:+.1f}%, but it moves the **die** by 0%:
every library lands under the same pad ring. The recommendation is 7.5T
single-{tech.width_unit_name} — same die, better pin access and lower leakage than
9T. Density is then spent on integration, not on a smaller chip: the measured
{ab.die_mm2:.0f} mm2 die, at its measured {ab.derived_util:.0%} utilisation, would
hold roughly **{best_jump.integration_headroom:.0f}x** this content. The node's
real return is latency, power and board area, not die shrinkage.

At the measured {cfg.target_freq_ghz * 1000:.0f} MHz clock the 9T projection draws
**{node_est.power_at_target_w * 1000:.1f} mW** and the area-optimal point
**{best_est.power_at_target_w * 1000:.1f} mW**, of which
{node_est.leakage_w * 1000:.1f} mW and {best_est.leakage_w * 1000:.1f} mW is leakage.
The modelled capability is {best_est.freq_ghz:.1f} GHz, so the 40 ns clock is set
by the design and its memory system, not by {tech.name}; frequency is not the
binding constraint in either direction.
"""


def _chip_section(cfg: BlockConfig, libs: dict[str, Library]) -> tuple[str, list[dict[str, object]]]:
    steps = build_steps(cfg)
    tech = steps[0].library.tech
    ladder = "9T-to-7.5T" if tech.device_kind == "planar" else "9T-to-6T"
    rows = lever_table(steps)
    pair = reference_pair(cfg)
    best = best_step(steps)
    matrix = library_matrix(cfg, libs)
    baseline = steps[0].iso
    opt_label = "lowest area" if cfg.as_built is not None else "optimised"

    measured_md = ""
    if cfg.as_built is not None:
        ab = AsBuilt.from_mapping(cfg.as_built)
        baseline_est = pair.reference if tech.device_kind == "planar" else pair.node
        measured_md = "\n" + _asbuilt_md(cfg, ab, baseline_est, best.iso, tech)
        inputs_md = (
            f"**Projection inputs (netlist-derived):** {cfg.gates_m:.3f}M "
            f"combinational NAND2-equivalents, {ab.ff_count:,.0f} flip-flops, "
            f"{cfg.sram_mb * 1024:.0f} KB SRAM, {cfg.target_freq_ghz * 1000:.0f} MHz "
            "clock target. The remaining planning assumptions are "
            f"{cfg.logic_depth_fo4:.0f} FO4 per pipeline stage, activity "
            f"{cfg.activity:.2f}, and a {cfg.pad_pins}-pad perimeter ring."
        )
    else:
        inputs_md = (
            f"**Planning assumptions:** {cfg.gates_m:.0f}M gates, FF ratio "
            f"{cfg.ff_ratio:.2f}, {cfg.sram_mb:.0f} MB SRAM, {cfg.io_mm2:.0f} mm2 IO, "
            f"{cfg.logic_depth_fo4:.0f} FO4 per stage, activity {cfg.activity:.2f}, "
            f"target {cfg.target_freq_ghz or baseline.freq_ghz:.2f} GHz. These are "
            "placeholders until the real floorplan and netlist exist."
        )

    headline_rows = [
        [
            "Area (mm2)",
            _num(pair.reference.total_area_mm2),
            _num(pair.node.total_area_mm2),
            _num(best.iso.total_area_mm2),
        ],
        [
            "Frequency, capability (GHz)",
            f"{pair.reference.freq_ghz:.2f}",
            f"{pair.node.freq_ghz:.2f}",
            f"{best.iso.freq_ghz:.2f}",
        ],
        [
            "Power at target (W)",
            _power(pair.reference.power_at_target_w),
            _power(pair.node.power_at_target_w),
            _power(best.iso.power_at_target_w),
        ],
        [
            "Power density at target (W/mm2)",
            _power_density(pair.reference.power_density_at_target_w_per_mm2),
            _power_density(pair.node.power_density_at_target_w_per_mm2),
            _power_density(best.iso.power_density_at_target_w_per_mm2),
        ],
    ]

    waterfall_rows = [
        [
            r["label"],
            r["library"],
            r["tracks"],
            r["isolation"],
            r["fins"],
            f"{r['native_freq_ghz']:.2f}",
            _num(r["iso_area_mm2"], 3),
            f"{r['step_delta_pct']:+.1f}%",
            f"{r['vs_baseline_pct']:.1f}%",
            _power(r["power_w"]),
        ]
        for r in rows
    ]

    matrix_rows = [
        [
            r["library"],
            r["role"],
            r["tracks"],
            r["fins_for_target"],
            f"{r['area_mm2']:.1f}",
            f"{r['area_delta_pct']:+.1f}%",
            f"{r['native_freq_ghz']:.2f}",
            _power(r["power_w"]),
            f"{r['routable_util']:.2f}",
        ]
        for r in matrix
    ]

    shortfalls = [s for s in steps if s.iso.freq_ghz + 1e-9 < s.target_ghz]
    timing_note = (
        "all at or above target frequency"
        if not shortfalls
        else "at target where reachable; "
        + ", ".join(f"{s.library.id} stops at {s.iso.freq_ghz:.2f} GHz" for s in shortfalls)
    )
    best_lever = min(rows[1:], key=lambda r: r["step_delta_pct"])
    mbff_row = next(r for r in rows if r["step"] == "mbff")
    mbff_index = next(i for i, r in enumerate(rows) if r["step"] == "mbff")
    mbff_prev = rows[mbff_index - 1]
    power_delta = mbff_row["power_w"] - mbff_prev["power_w"]
    best_label = (
        f"{best.library.tracks:g}T {best.library.isolation}"
        + (", COAG" if best.library.coag else "")
        + f", {best.iso.upsize_fins}-{tech.width_unit_name}, MBFF-{best.iso.mbff_bits}"
    )
    beol_note = (
        ", with M1-M3 pitch compression and via pillars"
        if best.key == "beol"
        else ""
    )
    if cfg.as_built is not None:
        pad_die = best.iso.die_area_mm2
        content_saving = steps[0].iso.total_area_mm2 - best.iso.total_area_mm2
        share = content_saving / pad_die * 100.0 if pad_die else 0.0
        cpu_note = (
            f"This chip is pad-limited: the entire {ladder} span saves\n"
            f"{content_saving:.2f} mm2 of content, {share:.1f}% of a {pad_die:.1f} mm2\n"
            "pad-ring die. Stay on 7.5T for pin access and yield, and spend the\n"
            "node on integration headroom instead of a smaller die."
        )
    elif cfg.name == "GRX930":
        cpu_note = (
            "The 6T library also models smaller for GRX930, but it has no vertical\n"
            "headroom for 2-fin upsizing and only four usable M2 tracks. The CPU\n"
            "recommendation stays at 7.5T until a trial route proves 6T closure at 3 GHz."
        )
    else:
        cpu_note = (
            "7.5T is the GPU recommendation at this node. The 9T baseline costs\n"
            "about 7% more area and does not buy back enough routability to justify\n"
            "it at the SRAM-dominated block scale."
        )

    if tech.device_kind == "planar":
        tail_note = (
            "A 6T library is not modelled at this node: 540 nm rows cannot fit the\n"
            "two width units a series stack needs, so 7.5T is the density floor.\n"
            "The remaining area lever is implementation quality, not a new cell\n"
            "architecture: synthesis mapping, placement density and routing closure\n"
            "are where the open-source flow earns its area."
        )
    else:
        tail_note = (
            "The experimental 5.5T CNOD point models smaller still, but it is outside the\n"
            "comfortable pin-access and lithography envelope for a 12 nm-class process: 3.5\n"
            "usable tracks, gate-bias isolation, and layout-dependent effects that this model\n"
            "does not capture. It is a research direction, not a tapeout recommendation."
        )
    ref_header = "12LP-class ref" if tech.device_kind == "finfet" else "9T baseline"
    node_header = (
        f"{tech.name} 9T baseline" if tech.device_kind == "finfet" else "7.5T recommended"
    )
    unit_header = "Fins" if tech.width_unit_name == "fin" else "Fingers"
    text = f"""### {cfg.name}

{cfg.description}

{inputs_md}

### Headline ({timing_note})

{_table(["Metric", ref_header, node_header, f"{tech.name} {opt_label}"], headline_rows)}

The {opt_label} configuration is **{best_label}** ({best.library.id}){beol_note}.

{measured_md}
### Lever waterfall

{_table(["Step", "Library", "Tracks", "Isolation", unit_header, "Native GHz", "Area mm2", "Step delta", "Cumulative", "Power at target"], waterfall_rows)}

Cell area is not the same as block area: {best.library.tracks:g}T keeps
{best.library.usable_tracks:g} usable M2 tracks against
{steps[0].library.usable_tracks:g} at {steps[0].library.tracks:g}T, so routable
utilisation falls from {baseline.util:.2f} to {best.iso.util:.2f} and part of the
cell-level gain is given back at placement. The largest single reduction here is
**{best_lever['label'].removeprefix('+ ')}** at {abs(best_lever['step_delta_pct']):.1f}%.

Multibit flops changed area by {mbff_row['step_delta_pct']:+.1f}% and power by
{_power_delta(power_delta)}. With a sequential fraction of only {cfg.ff_ratio:.2f}, MBFF is a
clock-power lever first and an area lever second; at low FF density the extra
placement congestion can cancel the cell-area saving.

### Library choice at the frequency target

{_table(["Library", "Role", "Tracks", f"{unit_header} used", "Area mm2", "vs 9T", "Native GHz", "Power at target", "Util"], matrix_rows)}

{cpu_note}

{tail_note}
"""
    return text, rows


def _write_reports() -> dict[str, object]:
    OUT.mkdir(parents=True, exist_ok=True)
    tech = load_tech("grx28.yaml")
    ref = load_tech("grx12f.yaml")
    libs = load_libraries(tech)
    chips = load_chips()

    # The layout demo is the 12 nm FinFET cell: the 28 nm node is planar and has
    # no fin/COAG geometry to draw with this generator.
    layout = inverter_layout(ref, tracks=7.5, coag=True)
    violations = check(layout, ref, tracks=7.5)
    gds_path = write_gds(layout, OUT / "grx12f_inv.gds")
    gds_info = read_gds(gds_path)
    to_svg(layout, OUT / "grx12f_inv.svg")
    png_written = True
    try:
        to_png(layout, OUT / "grx12f_inv.png")
    except ImportError:
        png_written = False
    drc_info = summarize(layout, violations)

    device_rows = _device_rows(tech)
    lib_rows = [
        [
            lib.id,
            lib.role,
            f"{lib.tracks:g}T",
            lib.base_fins,
            lib.isolation,
            "yes" if lib.coag else "no",
            f"{lib.cell_height_nm:.0f}",
            f"{lib.avg_cell_area_um2:.4f}",
            f"{lib.pin_capacity:.2f}",
            f"{lib.routable_utilization():.3f}",
            f"{lib.fo4_ps:.2f}",
            f"{lib.avg_leakage_nw:.3f}",
        ]
        for lib in libs.values()
    ]

    beol_rows = [
        [
            row.name,
            row.direction,
            f"{row.pitch_nm:.0f}",
            f"{row.width_nm:.0f}",
            f"{row.r_ohm_per_um:.2f}",
            f"{row.c_ff_per_um:.4f}",
            f"{row.rc_ps_per_um2:.4f}",
        ]
        for row in layer_table(tech)
    ]

    chip_texts = []
    all_lever_rows: list[dict[str, object]] = []
    asbuilt_rows: list[dict[str, object]] = []
    for cfg in chips:
        text, rows = _chip_section(cfg, libs)
        chip_texts.append(text)
        all_lever_rows.extend(rows)
        if cfg.as_built is not None:
            ab = AsBuilt.from_mapping(cfg.as_built)
            steps = build_steps(cfg)
            jump = node_jump(steps[0].iso, ab)
            best = best_step(steps).iso
            asbuilt_rows.append(
                {
                    "chip": cfg.name,
                    "item": "logic_mm2",
                    "as_built": ab.logic_mm2,
                    "node_9t": round(steps[0].iso.cell_area_mm2, 4),
                    "node_best": round(best.cell_area_mm2, 4),
                    "node_jump_x": round(jump.logic_ratio, 1),
                }
            )
            asbuilt_rows.append(
                {
                    "chip": cfg.name,
                    "item": "sram_mm2",
                    "as_built": ab.sram_mm2,
                    "node_9t": round(steps[0].iso.sram_area_mm2, 4),
                    "node_best": round(best.sram_area_mm2, 4),
                    "node_jump_x": round(jump.sram_ratio, 1),
                }
            )
            asbuilt_rows.append(
                {
                    "chip": cfg.name,
                    "item": "content_mm2",
                    "as_built": ab.content_mm2,
                    "node_9t": round(steps[0].iso.total_area_mm2, 4),
                    "node_best": round(best.total_area_mm2, 4),
                    "node_jump_x": round(jump.content_ratio, 1),
                }
            )
            asbuilt_rows.append(
                {
                    "chip": cfg.name,
                    "item": "die_mm2",
                    "as_built": ab.die_mm2,
                    "node_9t": round(steps[0].iso.die_area_mm2, 2),
                    "node_best": round(best.die_area_mm2, 2),
                    "node_jump_x": round(jump.die_ratio, 2),
                }
            )
    chips_md = "\n\n".join(chip_texts)

    padring_md = ""
    grx = next((c for c in chips if c.name == "GRX930" and c.pin_spec), None)
    if grx is not None:
        est = best_step(build_steps(grx)).iso
        budget = PinBudget.from_spec(grx.pin_spec, str(grx.pin_spec["selected"]))
        plan = build_floorplan(
            grx, budget, est.die_area_mm2**0.5, est.total_area_mm2
        )
        write_artifacts(plan, OUT)
        side_rows = []
        for side, count in plan.side_counts.items():
            signals = sum(1 for p in plan.pads if p.side == side and p.kind == "signal")
            side_rows.append([side.capitalize(), count, signals, count - signals])
        padring_md = f"""## 7. GRX930 pad ring and package ball map

{_table(["Side", "Pads", "Signals", "Supplies"], side_rows)}

Two staggered rows at a {plan.min_pitch_um:.1f} um minimum pitch around a
{plan.die_mm:.2f} mm die, with a {90} um corner margin. The ring is generated
from `pins.padring.sides`; every signal group is assigned to exactly one side and
the supply pairs are explicit, so an interface change regenerates the floorplan
instead of silently moving pads.

![GRX930 pad ring and TFBGA-196 ball map](grx930_package.png)

The TFBGA is wire-bond, so these are die pads and substrate balls, not flip-chip
bumps. The 196-ball array uses {plan.balls_used} balls and leaves
{plan.balls_spare} spare; supplies occupy the outer ring, memory data the lower
half, and control and bring-up I/O the upper half. The ball assignment is a
functional floorplan, not a routed substrate.

- [grx930_padring.csv](grx930_padring.csv) — {len(plan.pads)} pads with side, row and coordinates
- [grx930_ballmap.csv](grx930_ballmap.csv) — 196 balls with net assignment
- [grx930_package.svg](grx930_package.svg) — vector version of the figure

"""

    m1 = tech.layer("M1")
    m2 = tech.layer("M2")
    via_rows = [
        ["M1-M2 standard via", f"{via_resistance_ohm(tech, m1, pillar=False):.2f}"],
        ["M2-M3 standard via", f"{via_resistance_ohm(tech, m2, pillar=False):.2f}"],
    ]
    if tech.via_pillar_enabled:
        via_rows += [
            ["M1-M2 via pillar", f"{via_resistance_ohm(tech, m1, pillar=True):.2f}"],
            ["M2-M3 via pillar", f"{via_resistance_ohm(tech, m2, pillar=True):.2f}"],
        ]

    flow_md = f"""## 8. Open-source implementation path

No open 28 nm PDK exists. The open engines are ready; the 28 nm decks are the
blocker.

{_table(["Stage", "Tool", "28 nm status"], [
    ["Synthesis", "Yosys + ABC", "Ready; needs 28 nm Liberty and `dont_use` tuning"],
    ["Floorplan/place/CTS/route", "OpenROAD / ORFS", "Ready; needs LEF, tech LEF and a platform"],
    ["Flow orchestration", "LibreLane 3.0.x / SiliconCompiler", "Ready; ships 45 nm predictive, 130/180 nm open kits"],
    ["STA", "OpenSTA", "Ready; needs 28 nm corners and SPEF"],
    ["RC extraction", "OpenRCX", "Engine ready; calibrated rules file is the hardest blocker"],
    ["DRC / LVS", "KLayout, Magic, Netgen", "Engines ready; 28 nm decks must be authored"],
    ["Device calibration", "ngspice + PTM 28 nm", "Device cards only; no layout or timing collateral"],
])}

The first two steps are now measured: FreePDK45/NanGate45 supplies the 45 nm
10T anchor, and GF180MCU supplies the same-PDK 9T/7T track-height A/B (7T saves
20.6% routed cell area and 10.6% wirelength, costs 0.72 ns WNS, both routes DRC-clean).
Next is calibrating power and FO4 against PTM 28 nm cards, then porting the
identical flow to an NDA 28 nm kit. The 45 nm proxy cannot sign off 28 nm area;
only the foundry deck can. Details and sources are in
[the flow plan](../docs/open-source-28nm-flow.md) and
[the measured results](../out/FLOW_RESULTS.md).

"""

    doc = f"""# GRX28 — 28 nm-class planar PDK and DTCO starter

Generated {dt.date.today().isoformat()} from `{tech.path.relative_to(ROOT).as_posix()}` and
`{ref.path.relative_to(ROOT).as_posix()}`.

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

{_table(["Metric", "GRX12F (12 nm FinFET reference)", "GRX28 (28 nm planar target)"], _node_rows(ref, tech))}

The cell height is set by track count. A 7.5T GRX28 row is
{tech.cell_height_nm(7.5):.0f} nm, 16.7% shorter than 9T. At 28 nm the width unit
is a gate finger, not a fin: there is no fin height, no single diffusion break and
no COAG. What remains is a fixed-height cell whose drive is set by how many
fingers fit between the rails.

## 2. Device model

{_table(["Device", "Vt (V)", "SS (mV/dec)", "DIBL (mV/V)", "Ion (uA/unit)", "Ioff (nA/unit)", "Cgg (fF/unit)", "Ron (kohm/unit)"], device_rows)}

Per-{tech.width_unit_name} values at {tech.vdd_hp:.2f} V, {tech.temp_c:.0f} C. The
inverter FO4 is {DeviceModel(tech).stage(1, 1, tech.vdd_hp).fo4_ps:.2f} ps at
minimum drive.

## 3. Standard-cell libraries

{_table(["Library", "Role", "Height", "Base units", "Isolation", "COAG", "Cell height (nm)", "Avg cell (um2)", "Pin capacity", "Routable util", "FO4 (ps)", "Leak (nW)"], lib_rows)}

### Track height sensitivity

{_table(["Tracks", "Units", "Isolation", "Track pitch (nm)", "Cell height (nm)", "Avg cell (um2)", "Area index", "Routable util", "FO4 (ps)"], _sensitivity_rows(tech))}

Cell height scales with tracks. At 28 nm there is no isolation or COAG lever, and
a single finger does not change a cell's area; it changes drive and leakage. The
only cell-architecture density lever left is the row height.

## 4. BEOL stack

{_table(["Layer", "Direction", "Pitch (nm)", "Width (nm)", "R (ohm/um)", "C (fF/um)", "RC (ps/um2)"], beol_rows)}

{_table(["Via", "Resistance (ohm)"], via_rows)}

Copper resistivity includes the barrier loss and the Fuchs-Sondheimer size effect;
at 28 nm drawn width the effective resistivity is above bulk copper. Via pillars
are a FinFET-node feature and are not offered on GRX28, so the BEOL lever here is
pitch and wire RC, not a new via structure.

## 5. Chip projections

{chips_md}

## 6. Reference layout and DRC demo (GRX12F)

The layout generator is FinFET-specific, so this demo is the 12 nm reference: a
7.5T single-fin inverter with continuous diffusion and COAG, generated at
{layout.width_nm()} x {layout.height_nm()} nm with {len(layout.shapes)} shapes.
The bundled rule deck found **{len(violations)} violations**. A 28 nm planar
equivalent needs a different layer stack and rule deck and is not drawn here.

- [grx12f_inv.gds](grx12f_inv.gds) — GDSII, 1 nm database unit
- [grx12f_inv.svg](grx12f_inv.svg) — vector preview
{'- [grx12f_inv.png](grx12f_inv.png) — raster preview' if png_written else ''}

GDS readback: {gds_info['boundaries']} boundaries across
{len(gds_info['layers'])} layers, bbox {gds_info['bbox_nm']} nm.

DRC covers fin/gate grids, cell height, min width/space, MD enclosure, COAG
contact placement, via enclosure and power rails. It is a demonstration deck, not
a signoff deck.

{padring_md}{flow_md}## 9. Assumptions and what to do next

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
"""
    (OUT / "REPORT.md").write_text(doc, encoding="utf-8")

    _csv(OUT / "libraries.csv", [dict(zip(
        ["library", "role", "tracks", "base_units", "isolation", "coag",
         "cell_height_nm", "avg_cell_area_um2", "pin_capacity", "routable_util",
         "fo4_ps", "leakage_nw"],
        row,
    )) for row in lib_rows])
    _csv(OUT / "node_comparison.csv", [
        {"metric": r[0], "grx12f_reference": r[1], "grx28_target": r[2]}
        for r in _node_rows(ref, tech)
    ])
    _csv(OUT / "devices.csv", [
        dict(zip(["device", "vt_v", "ss_mv_dec", "dibl_mv_v", "ion_ua_per_unit",
                  "ioff_na_per_unit", "cgg_ff_per_unit", "ron_kohm_per_unit"], row))
        for row in device_rows
    ])
    _csv(OUT / "dtco_all.csv", all_lever_rows)
    _csv(OUT / "asbuilt.csv", asbuilt_rows)
    _csv(OUT / "drc.csv", [{
        "layout": drc_info["layout"],
        "width_nm": drc_info["width_nm"],
        "height_nm": drc_info["height_nm"],
        "shapes": drc_info["shapes"],
        "violations": drc_info["violations"],
    }])

    return {
        "report": OUT / "REPORT.md",
        "drc": drc_info,
        "gds": gds_info,
        "chips": [c.name for c in chips],
    }


def main() -> None:
    info = _write_reports()
    print(f"wrote {info['report']}")
    print(f"DRC violations: {info['drc']['violations']}")
    print(f"GDS boundaries: {info['gds']['boundaries']}")
    print(f"chips: {', '.join(info['chips'])}")


if __name__ == "__main__":
    main()

"""Block-level DTCO estimator.

Given a library, a BEOL stack and a handful of block assumptions, estimate area,
frequency and power. The point is not absolute accuracy -- it is to make every
lever (track height, fin count, isolation, COAG, MBFF, pin-aware placement,
via pillar, pitch compression) move the numbers in a traceable way.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from .beol import layer_rc, wire_delay_ps
from .cells import Library, load_libraries
from .package import PinBudget
from .tech import ROOT, Tech

CHIP_DIR = ROOT / "chips"


@dataclass(frozen=True)
class BlockConfig:
    name: str
    description: str
    tech_file: str
    library: str
    gates_m: float
    ff_ratio: float
    sram_mb: float
    io_mm2: float
    logic_depth_fo4: float = 16.0
    activity: float = 0.12
    vdd: float = 0.80
    target_freq_ghz: float | None = None
    mbff_bits: int = 1
    upsize_fins: int | None = None
    pin_aware: bool = False
    pad_pins: int | None = None
    pad_pitch_um: float = 150.0
    pad_rows: int = 2
    pad_corner_allowance: float = 0.08
    pin_spec: dict[str, object] | None = None
    as_built: dict[str, object] | None = None
    notes: str = ""

    @property
    def gates(self) -> float:
        return self.gates_m * 1e6

    @property
    def ff_count(self) -> float:
        return self.gates * self.ff_ratio


@dataclass(frozen=True)
class BlockEstimate:
    name: str
    library: str
    tracks: float
    base_fins: int
    upsize_fins: int
    mbff_bits: int
    pin_aware: bool
    util: float
    cell_area_mm2: float
    comb_area_mm2: float
    ff_area_mm2: float
    sram_area_mm2: float
    io_area_mm2: float
    total_area_mm2: float
    pad_floor_mm2: float
    assembly_floor_mm2: float
    die_area_mm2: float
    die_binding: str
    fo4_ps: float
    wire_delay_ps: float
    avg_wire_um: float
    freq_ghz: float
    logic_dynamic_w: float
    wire_dynamic_w: float
    clock_w: float
    leakage_w: float
    total_power_w: float
    target_ghz: float
    power_at_target_w: float
    assumptions: dict[str, object]

    @property
    def power_density_w_per_mm2(self) -> float:
        return self.total_power_w / self.total_area_mm2

    @property
    def power_density_at_target_w_per_mm2(self) -> float:
        return self.power_at_target_w / self.total_area_mm2

    def as_dict(self) -> dict[str, object]:
        return {
            "block": self.name,
            "library": self.library,
            "tracks": self.tracks,
            "upsize_fins": self.upsize_fins,
            "mbff_bits": self.mbff_bits,
            "pin_aware": self.pin_aware,
            "util": round(self.util, 3),
            "logic_area_mm2": round(
                self.comb_area_mm2 + self.ff_area_mm2, 3
            ),
            "total_area_mm2": round(self.total_area_mm2, 3),
            "pad_floor_mm2": round(self.pad_floor_mm2, 3),
            "assembly_floor_mm2": round(self.assembly_floor_mm2, 3),
            "die_area_mm2": round(self.die_area_mm2, 3),
            "die_binding": self.die_binding,
            "freq_ghz": round(self.freq_ghz, 3),
            "power_w": round(self.total_power_w, 3),
            "power_density_w_per_mm2": round(self.power_density_w_per_mm2, 3),
        }


def load_chip(path: str | Path) -> BlockConfig:
    path = Path(path)
    if not path.is_absolute():
        path = CHIP_DIR / path
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    pins = raw.get("pins") or {}
    pad_pins: int | None = None
    if pins.get("variants"):
        selected = str(pins.get("selected") or next(iter(pins["variants"])))
        pad_pins = PinBudget.from_spec(pins, selected).total_pads
    elif (raw.get("pads") or {}).get("signal_pins"):
        pad_pins = int(raw["pads"]["signal_pins"])
    return BlockConfig(
        name=str(raw["name"]),
        description=str(raw.get("description", "")).strip(),
        tech_file=str(raw.get("tech", "grx12f.yaml")),
        library=str(raw["library"]),
        gates_m=float(raw["gates_m"]),
        ff_ratio=float(raw["ff_ratio"]),
        sram_mb=float(raw["sram_mb"]),
        io_mm2=float(raw["io_mm2"]),
        logic_depth_fo4=float(raw.get("logic_depth_fo4", 16.0)),
        activity=float(raw.get("activity", 0.12)),
        vdd=float(raw.get("vdd", 0.80)),
        target_freq_ghz=(
            float(raw["target_freq_ghz"]) if raw.get("target_freq_ghz") else None
        ),
        mbff_bits=int(raw.get("mbff_bits", 1)),
        upsize_fins=(
            int(raw["upsize_fins"]) if raw.get("upsize_fins") is not None else None
        ),
        pin_aware=bool(raw.get("pin_aware", False)),
        pad_pins=pad_pins,
        pad_pitch_um=float(raw.get("pads", {}).get("pitch_um", 150.0)),
        pad_rows=int(raw.get("pads", {}).get("rows", 2)),
        pad_corner_allowance=float(raw.get("pads", {}).get("corner_allowance", 0.08)),
        pin_spec=pins or None,
        as_built=raw.get("as_built"),
        notes=str(raw.get("notes", "")).strip(),
    )


def load_chips() -> list[BlockConfig]:
    """Load digital block definitions, skipping non-digital products."""
    chips: list[BlockConfig] = []
    for path in sorted(CHIP_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "gates_m" not in raw:
            continue
        chips.append(load_chip(path))
    return chips


def pad_limited_die_mm2(cfg: BlockConfig) -> float:
    """Square die whose perimeter pad ring can carry ``cfg.pad_pins``.

    A ring with ``rows`` staggered rows needs ``pins * pitch / rows`` of edge
    length, plus a corner allowance. This is a lower bound: it ignores
    power/ground pads, ESD overlap and the wider supply pitch, so a real ring is
    usually larger. It answers one question -- when does the pad ring, rather
    than the transistors, set the die size?
    """
    if not cfg.pad_pins:
        return 0.0
    perimeter_um = cfg.pad_pins * cfg.pad_pitch_um / max(1, cfg.pad_rows)
    perimeter_um *= 1.0 + cfg.pad_corner_allowance
    side_um = perimeter_um / 4.0
    return side_um * side_um / 1e6


def _blended_rc(tech: Tech):
    """Average local-route RC: half M2 (horizontal), half M3 (vertical)."""
    m2, m3 = layer_rc(tech, tech.m2), layer_rc(tech, tech.m3)
    return type(m2)(
        name="M2/M3",
        direction="blended",
        pitch_nm=(m2.pitch_nm + m3.pitch_nm) / 2,
        width_nm=(m2.width_nm + m3.width_nm) / 2,
        thickness_nm=(m2.thickness_nm + m3.thickness_nm) / 2,
        space_nm=(m2.space_nm + m3.space_nm) / 2,
        r_ohm_per_um=(m2.r_ohm_per_um + m3.r_ohm_per_um) / 2,
        c_ff_per_um=(m2.c_ff_per_um + m3.c_ff_per_um) / 2,
    )


def estimate(
    cfg: BlockConfig,
    lib: Library,
    *,
    upsize_fins: int | None = None,
    mbff_bits: int | None = None,
    pin_aware: bool | None = None,
) -> BlockEstimate:
    tech = lib.tech
    upsize = cfg.upsize_fins if upsize_fins is None else upsize_fins
    upsize = lib.base_fins if upsize is None else upsize
    mbff = cfg.mbff_bits if mbff_bits is None else mbff_bits
    pin_aware = cfg.pin_aware if pin_aware is None else pin_aware
    if mbff not in (1, *lib.mbff_bits):
        raise ValueError(f"{lib.id} does not offer a {mbff}-bit flip-flop")
    if not lib.base_fins <= upsize <= tech.max_fins_per_device(lib.tracks):
        raise ValueError(
            f"upsize_fins={upsize} outside [{lib.base_fins}, "
            f"{tech.max_fins_per_device(lib.tracks)}] for {lib.id}"
        )

    drive_gain = upsize / lib.base_fins
    mbff_congestion = 0.985 if mbff == 2 else (0.97 if mbff >= 4 else 1.0)
    util = lib.routable_utilization(pin_aware)
    util *= 1.0 - 0.03 * (upsize - lib.base_fins)
    util *= mbff_congestion
    util = min(max(util, 0.40), 0.90)

    gates = cfg.gates
    comb_area = gates * lib.avg_cell_area_um2
    ff_area = cfg.ff_count * lib.dff_area_per_bit_um2(mbff)
    htree = float(tech.model.get("block", {}).get("htree_overhead", 0.05))
    cell_area = (comb_area + ff_area) * (1.0 + htree)

    sram_eff = float(
        tech.model.get("block", {}).get("sram_array_efficiency", 0.72)
    )
    if not 0.3 <= sram_eff <= 1.0:
        raise ValueError("sram_array_efficiency must be in [0.3, 1.0]")
    # sram_mb is MiB: 96 KB is 0.09375, and 1 MiB is 8 * 1024 * 1024 bits.
    sram_area_um2 = (
        cfg.sram_mb * 8 * 1024 * 1024 * tech.sram.hd_bitcell_um2 / sram_eff
    )
    logic_placed_um2 = cell_area / util
    total_area_mm2 = (logic_placed_um2 + sram_area_um2) / 1e6 + cfg.io_mm2
    pad_floor = pad_limited_die_mm2(cfg)
    min_die_mm = float(tech.model.get("assembly", {}).get("min_die_mm", 0.0))
    assembly_floor = min_die_mm * min_die_mm
    die_area = max(total_area_mm2, pad_floor, assembly_floor)
    if die_area == assembly_floor and assembly_floor > 0:
        die_binding = "assembly minimum"
    elif pad_floor > total_area_mm2:
        die_binding = "pad ring"
    else:
        die_binding = "logic utilisation"

    # -- timing -----------------------------------------------------------
    vdd_scale = (tech.vdd_hp / cfg.vdd) ** 1.2 if cfg.vdd != tech.vdd_hp else 1.0
    fo4 = lib.fo4_ps * vdd_scale
    k_wire = float(tech.model.get("block", {}).get("wire_length_coefficient", 0.0015))
    avg_wire_um = k_wire * math.sqrt(logic_placed_um2)
    rc = _blended_rc(tech)
    margin = float(tech.model.get("block", {}).get("wire_cap_margin", 1.15))
    # An average net is driven by roughly a 2x cell, not minimum size.
    driver_ohm = lib.driver_ron_ohm / drive_gain / 2.0
    wire_ps = wire_delay_ps(
        rc, avg_wire_um, driver_ohm, pillar=tech.via_pillar_enabled
    ) * margin
    stage_ps = fo4 + wire_ps
    freq_ghz = 1000.0 / (cfg.logic_depth_fo4 * stage_ps)

    # -- power ------------------------------------------------------------
    cin = lib.avg_cin_ff * drive_gain
    dyn = gates * cin * 1e-15 * cfg.vdd**2 * freq_ghz * 1e9 * cfg.activity
    nets = gates * 1.3
    wire_cap_ff = avg_wire_um * rc.c_ff_per_um * margin
    wire_dyn = (
        nets
        * wire_cap_ff
        * 1e-15
        * cfg.vdd**2
        * freq_ghz
        * 1e9
        * cfg.activity
        * 0.3
    )
    clock_cap = lib.clock_cap_per_bit_ff(mbff)
    transitions = float(tech.model.get("block", {}).get("clock_transitions_per_cycle", 2.0))
    clock_w = (
        cfg.ff_count
        * clock_cap
        * 1e-15
        * cfg.vdd**2
        * freq_ghz
        * 1e9
        * transitions
    )
    sram_leak = float(tech.model.get("block", {}).get("sram_leak_mw_per_mb", 25.0))
    leakage_w = (
        gates * lib.avg_leakage_nw * drive_gain * 1e-9
        + cfg.sram_mb * sram_leak * 1e-3
    )
    total_power = dyn + wire_dyn + clock_w + leakage_w

    # Power at the chip's actual clock, not at the frequency the library could
    # reach. Dynamic terms scale with frequency; leakage does not.
    target_ghz = cfg.target_freq_ghz or freq_ghz
    power_scale = min(1.0, target_ghz / freq_ghz) if freq_ghz > 0 else 1.0
    power_at_target = (dyn + wire_dyn + clock_w) * power_scale + leakage_w

    return BlockEstimate(
        name=cfg.name,
        library=lib.id,
        tracks=lib.tracks,
        base_fins=lib.base_fins,
        upsize_fins=upsize,
        mbff_bits=mbff,
        pin_aware=pin_aware,
        util=util,
        cell_area_mm2=cell_area / 1e6,
        comb_area_mm2=comb_area / 1e6,
        ff_area_mm2=ff_area / 1e6,
        sram_area_mm2=sram_area_um2 / 1e6,
        io_area_mm2=cfg.io_mm2,
        total_area_mm2=total_area_mm2,
        pad_floor_mm2=pad_floor,
        assembly_floor_mm2=assembly_floor,
        die_area_mm2=die_area,
        die_binding=die_binding,
        fo4_ps=fo4,
        wire_delay_ps=wire_ps,
        avg_wire_um=avg_wire_um,
        freq_ghz=freq_ghz,
        logic_dynamic_w=dyn,
        wire_dynamic_w=wire_dyn,
        clock_w=clock_w,
        leakage_w=leakage_w,
        total_power_w=total_power,
        target_ghz=target_ghz,
        power_at_target_w=power_at_target,
        assumptions={
            "gates_m": cfg.gates_m,
            "ff_ratio": cfg.ff_ratio,
            "sram_mb": cfg.sram_mb,
            "io_mm2": cfg.io_mm2,
            "logic_depth_fo4": cfg.logic_depth_fo4,
            "activity": cfg.activity,
            "vdd": cfg.vdd,
            "tech": tech.name,
            "avg_cell_area_um2": round(lib.avg_cell_area_um2, 4),
        },
    )


def frequency_matched(
    cfg: BlockConfig, lib: Library, target_ghz: float
) -> BlockEstimate:
    """Smallest fin count that meets a frequency target, if reachable."""
    max_fins = lib.tech.max_fins_per_device(lib.tracks)
    best: BlockEstimate | None = None
    for fins in range(lib.base_fins, max_fins + 1):
        est = estimate(cfg, lib, upsize_fins=fins)
        best = est
        if est.freq_ghz >= target_ghz:
            return est
    assert best is not None
    return best


def default_library(cfg: BlockConfig) -> Library:
    libs = load_libraries()
    if cfg.library not in libs:
        raise KeyError(f"{cfg.name}: unknown library {cfg.library!r}")
    return libs[cfg.library]

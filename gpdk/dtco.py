"""DTCO lever sweep for the GRX930 and GRXGPU/PTA blocks.

The waterfall depends on the node class. A FinFET node (GRX12F) can trade track
height, fin count, isolation and COAG. A planar node (GRX28) has no fins, no
single diffusion break and no COAG: its levers are track height, multibit
flip-flops, pin-aware placement and metal pitch. Every step is evaluated at the
chip's frequency target, and drive is added (up to the library limit) when a
step would otherwise miss it. Density that only exists because the block got
slower is not counted as density.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .block import BlockConfig, BlockEstimate, estimate, frequency_matched
from .cells import Library
from .tech import load_tech

REF_TECH_FILE = "12lp_class_ref.yaml"
BASE_TECH_FILE = "grx12f.yaml"


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    detail: str
    library: Library
    cfg: BlockConfig
    native: BlockEstimate
    iso: BlockEstimate
    target_ghz: float


@dataclass(frozen=True)
class ReferencePair:
    reference: BlockEstimate
    node: BlockEstimate


def _lib(
    tech,
    id: str,
    tracks: float,
    base_fins: int,
    isolation: str,
    coag: bool,
    *,
    label: str = "",
    role: str = "sweep",
) -> Library:
    return Library.build(
        tech,
        id=id,
        label=label or id,
        tracks=tracks,
        base_fins=base_fins,
        isolation=isolation,
        coag=coag,
        mbff_bits=(1, 2, 4),
        role=role,
    )


def _plain(cfg: BlockConfig) -> BlockConfig:
    """Config with every optional lever switched off."""
    return replace(cfg, mbff_bits=1, pin_aware=False, upsize_fins=None)


def reference_pair(cfg: BlockConfig) -> ReferencePair:
    """Baseline versus recommended library on the chip's own node.

    For a FinFET chip this is the first-generation 12 nm reference against our
    GRX12F library. For a planar chip it is the same 28 nm node at 9T and 7.5T,
    so the delta is a library choice, not a node jump.
    """
    tech = load_tech(cfg.tech_file)
    plain = _plain(cfg)
    if tech.device_kind == "planar":
        base = _lib(tech, "grx28_9t_1f", 9, 1, "DDB", False, label="GRX28 9T baseline")
        node = _lib(tech, "grx28_7t5_1f", 7.5, 1, "DDB", False, label="GRX28 7.5T")
    else:
        base = _lib(load_tech(REF_TECH_FILE), "ref9t_2f", 9, 2, "DDB", False,
                    label="12LP-class ref 9T 2-fin")
        node = _lib(load_tech(BASE_TECH_FILE), "grx9t_2f", 9, 2, "DDB", False,
                    label="GRX12F 9T 2-fin")
    target = cfg.target_freq_ghz or estimate(plain, node).freq_ghz
    return ReferencePair(
        reference=frequency_matched(plain, base, target),
        node=frequency_matched(plain, node, target),
    )


def _planar_steps(tech, plain: BlockConfig, mbff_bits: int) -> list[tuple[str, str, str, Library, BlockConfig]]:
    """28 nm planar levers: track height, MBFF and placement."""
    base = _lib(tech, "grx28_9t_1f", 9, 1, "DDB", False, label="9T / 1-finger baseline")
    mid = _lib(tech, "grx28_7t5_1f", 7.5, 1, "DDB", False, label="7.5T / 1-finger")
    return [
        (
            "node9t",
            "GRX28 9T / 1-finger",
            "Baseline for the waterfall: 810 nm rows, double diffusion break",
            base,
            plain,
        ),
        (
            "track7t5",
            "+ 7.5T track shrink",
            "675 nm rows instead of 810 nm, same single-finger devices",
            mid,
            plain,
        ),
        (
            "mbff",
            "+ multibit flip-flops",
            f"MBFF-{mbff_bits} merging, shared clock and control",
            mid,
            replace(plain, mbff_bits=mbff_bits),
        ),
        (
            "pin_aware",
            "+ pin-density-aware placement",
            "Spread high-pin cells before routing inflates the block",
            mid,
            replace(plain, mbff_bits=mbff_bits, pin_aware=True),
        ),
    ]


def build_steps(cfg: BlockConfig) -> list[Step]:
    tech = load_tech(cfg.tech_file)
    plain = _plain(cfg)

    if tech.device_kind == "planar":
        steps = _planar_steps(tech, plain, cfg.mbff_bits)
    else:
        steps = _finfet_steps(tech, plain)
    base_lib = steps[0][3]
    target = cfg.target_freq_ghz or estimate(plain, base_lib).freq_ghz

    out: list[Step] = []
    for key, label, detail, lib, step_cfg in steps:
        native = estimate(step_cfg, lib)
        iso = frequency_matched(step_cfg, lib, target)
        out.append(
            Step(
                key=key,
                label=label,
                detail=detail,
                library=lib,
                cfg=step_cfg,
                native=native,
                iso=iso,
                target_ghz=target,
            )
        )
    return out


def _finfet_steps(tech, plain: BlockConfig) -> list[tuple[str, str, str, Library, BlockConfig]]:
    """GRX12F FinFET-specific steps."""
    base_lib = _lib(tech, "grx9t_2f", 9, 2, "DDB", False, label="9T / 2-fin baseline")
    steps: list[tuple[str, str, str, Library, BlockConfig]] = [
        (
            "node9t",
            "GRX12F 9T / 2-fin",
            "Baseline for the waterfall: our node, first-generation library",
            base_lib,
            plain,
        ),
        (
            "track7t5",
            "+ 7.5T track shrink",
            "Same 2-fin devices, 480 nm instead of 576 nm cell height",
            _lib(tech, "grx7t5_2f", 7.5, 2, "DDB", False),
            plain,
        ),
        (
            "single_fin",
            "+ single-fin, SDB, COAG",
            "1-fin base cells, single diffusion break, contact over active gate",
            _lib(tech, "grx7t5_1f", 7.5, 1, "SDB", True),
            plain,
        ),
        (
            "hd6t",
            "+ 6T high-density library",
            "384 nm cells with 4 usable M2 tracks",
            _lib(tech, "grx6t_1f", 6, 1, "SDB", True),
            plain,
        ),
        (
            "mbff",
            "+ multibit flip-flops",
            f"MBFF-{plain.mbff_bits} merging, shared clock and control",
            _lib(tech, "grx6t_1f", 6, 1, "SDB", True),
            replace(plain, mbff_bits=plain.mbff_bits),
        ),
        (
            "pin_aware",
            "+ pin-density-aware placement",
            "Spread high-pin cells before routing inflates the block",
            _lib(tech, "grx6t_1f", 6, 1, "SDB", True),
            replace(plain, mbff_bits=plain.mbff_bits, pin_aware=True),
        ),
    ]
    beol_tech = tech.with_beol_scale(60.0 / 64.0)
    steps.append(
        (
            "beol",
            "+ BEOL pitch compression and via pillar",
            "M1-M3 pitch 64 -> 60 nm, via pillar at M1-M3, 6T cells on 360 nm rows",
            _lib(beol_tech, "grx6t_1f_beol", 6, 1, "SDB", True),
            replace(plain, mbff_bits=plain.mbff_bits, pin_aware=True),
        )
    )
    return steps


def lever_table(steps: list[Step]) -> list[dict[str, object]]:
    baseline = steps[0].iso.total_area_mm2
    previous = baseline
    rows: list[dict[str, object]] = []
    for i, step in enumerate(steps):
        delta = step.iso.total_area_mm2 - previous if i else 0.0
        rows.append(
            {
                "block": steps[0].cfg.name,
                "step": step.key,
                "label": step.label,
                "library": step.library.id,
                "tracks": step.library.tracks,
                "isolation": step.library.isolation,
                "coag": step.library.coag,
                "mbff": step.iso.mbff_bits,
                "pin_aware": step.iso.pin_aware,
                "fins": step.iso.upsize_fins,
                "native_freq_ghz": round(step.native.freq_ghz, 3),
                "iso_freq_ghz": round(step.iso.freq_ghz, 3),
                "iso_area_mm2": round(step.iso.total_area_mm2, 3),
                "step_delta_mm2": round(delta, 3),
                "step_delta_pct": round(delta / previous * 100.0, 2) if i else 0.0,
                "vs_baseline_pct": round(
                    (step.iso.total_area_mm2 - baseline) / baseline * 100.0, 2
                ),
                # Power at the chip's target clock, not at the frequency the
                # library could reach. The two differ by more than an order of
                # magnitude for a legacy-clocked block.
                "power_w": round(step.iso.power_at_target_w, 5),
                "util": round(step.iso.util, 3),
            }
        )
        previous = step.iso.total_area_mm2
    return rows


def library_matrix(cfg: BlockConfig, libraries: dict[str, Library]) -> list[dict[str, object]]:
    """Every candidate library on our node, at the chip's frequency target."""
    baseline_lib = next(
        (lib for lib in libraries.values() if lib.role == "baseline"),
        next(iter(libraries.values())),
    )
    plain = _plain(cfg)
    target = cfg.target_freq_ghz or estimate(plain, baseline_lib).freq_ghz
    baseline_area = frequency_matched(
        plain, baseline_lib, target
    ).total_area_mm2
    rows: list[dict[str, object]] = []
    for lib in libraries.values():
        native = estimate(plain, lib)
        iso = frequency_matched(plain, lib, target)
        rows.append(
            {
                "library": lib.id,
                "role": lib.role,
                "tracks": lib.tracks,
                "base_fins": lib.base_fins,
                "isolation": lib.isolation,
                "coag": lib.coag,
                "cell_height_nm": round(lib.cell_height_nm, 1),
                "avg_cell_area_um2": round(lib.avg_cell_area_um2, 4),
                "routable_util": round(lib.routable_utilization(pin_aware=False), 3),
                "fo4_ps": round(lib.fo4_ps, 2),
                "native_freq_ghz": round(native.freq_ghz, 3),
                "fins_for_target": iso.upsize_fins,
                "area_mm2": round(iso.total_area_mm2, 3),
                "area_delta_pct": round(
                    (iso.total_area_mm2 / baseline_area - 1.0) * 100.0, 2
                ),
                "power_w": round(iso.power_at_target_w, 5),
            }
        )
    return rows


def best_step(steps: list[Step]) -> Step:
    viable = [s for s in steps if s.iso.freq_ghz >= 0.95 * s.target_ghz]
    return min(viable or steps, key=lambda s: s.iso.total_area_mm2)

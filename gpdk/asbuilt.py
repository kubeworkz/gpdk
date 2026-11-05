"""Measured-baseline bookkeeping for a chip that already exists in silicon.

The point of this module is to keep *measured* numbers and *modelled* numbers in
separate columns. A projection of a design built on a legacy node is a node jump
**plus** a DTCO delta inside the target node, and those two must never be added
together and reported as one saving.

Everything here is derived from the numbers in a chip YAML's ``as_built`` block.
No new assumptions are introduced, except the explicit note that the baseline's
process node is not disclosed in the source data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .block import BlockEstimate

BYTES_PER_MB = 8e6
BITS_PER_KB = 1024 * 8


@dataclass(frozen=True)
class AsBuilt:
    label: str
    node_note: str
    die_mm2: float
    die_xy_mm: tuple[float, float]
    core_mm2: float
    content_mm2: float
    logic_mm2: float
    sram_mm2: float
    sram_kb: float
    sram_macros: int
    sram_macro_mm2: float
    nand2_eq_m: float
    comb_nand2_eq_m: float
    ff_count: float
    clock_mhz: float
    fpga_clock_mhz: float
    offchip_kb: float
    stated_util: float | None
    blocks_mm2: dict[str, float]

    # -- derived ----------------------------------------------------------
    @property
    def sram_bits(self) -> float:
        return self.sram_kb * BITS_PER_KB

    @property
    def logic_um2_per_nand2(self) -> float:
        """Placed logic area per NAND2-equivalent gate."""
        return self.logic_mm2 * 1e6 / (self.nand2_eq_m * 1e6)

    @property
    def sram_um2_per_bit(self) -> float:
        """Silicon SRAM area per stored bit, including macro periphery."""
        return self.sram_mm2 * 1e6 / self.sram_bits

    @property
    def derived_util(self) -> float:
        """Content area as a fraction of die area, from the absolutes."""
        return self.content_mm2 / self.die_mm2

    @property
    def block_sum_mm2(self) -> float:
        return sum(self.blocks_mm2.values())

    @property
    def macro_sum_mm2(self) -> float:
        return self.sram_macros * self.sram_macro_mm2

    @property
    def clock_ns(self) -> float:
        return 1000.0 / self.clock_mhz

    def validate(self) -> None:
        errors: list[str] = []
        total = self.logic_mm2 + self.sram_mm2
        if abs(total - self.content_mm2) > 0.01 * self.content_mm2:
            errors.append(
                f"logic {self.logic_mm2} + sram {self.sram_mm2} != content "
                f"{self.content_mm2}"
            )
        if self.content_mm2 > self.die_mm2:
            errors.append("content area exceeds die area")
        if abs(self.macro_sum_mm2 - self.sram_mm2) > 0.01 * self.sram_mm2:
            errors.append(
                f"{self.sram_macros} macros x {self.sram_macro_mm2} mm2 != "
                f"{self.sram_mm2} mm2"
            )
        if self.block_sum_mm2 and abs(self.block_sum_mm2 - self.logic_mm2) > 0.02 * self.logic_mm2:
            errors.append(
                f"block breakdown sums to {self.block_sum_mm2:.2f} mm2, "
                f"logic is {self.logic_mm2:.2f} mm2"
            )
        if self.stated_util is not None and not 0.0 < self.stated_util <= 1.0:
            errors.append("stated_util must be a fraction")
        if errors:
            raise ValueError(f"{self.label}: " + "; ".join(errors))

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "AsBuilt":
        xy = raw.get("die_xy_mm") or [0.0, 0.0]
        obj = cls(
            label=str(raw.get("label", "as built")),
            node_note=str(raw.get("node_note", "")).strip(),
            die_mm2=float(raw["die_mm2"]),
            die_xy_mm=(float(xy[0]), float(xy[1])),
            core_mm2=float(raw.get("core_mm2", raw["die_mm2"])),
            content_mm2=float(raw["content_mm2"]),
            logic_mm2=float(raw["logic_mm2"]),
            sram_mm2=float(raw["sram_mm2"]),
            sram_kb=float(raw["sram_kb"]),
            sram_macros=int(raw.get("sram_macros", 0)),
            sram_macro_mm2=float(raw.get("sram_macro_mm2", 0.0)),
            nand2_eq_m=float(raw["nand2_eq_m"]),
            comb_nand2_eq_m=float(raw.get("comb_nand2_eq_m", raw["nand2_eq_m"])),
            ff_count=float(raw.get("ff_count", 0.0)),
            clock_mhz=float(raw["clock_mhz"]),
            fpga_clock_mhz=float(raw.get("fpga_clock_mhz", 0.0)),
            offchip_kb=float(raw.get("offchip_kb", 0.0)),
            stated_util=(float(raw["stated_util"]) if raw.get("stated_util") else None),
            blocks_mm2={str(k): float(v) for k, v in (raw.get("blocks_mm2") or {}).items()},
        )
        obj.validate()
        return obj


@dataclass(frozen=True)
class NodeJump:
    """Same design, measured silicon versus a target-node projection."""

    as_built: AsBuilt
    projected_logic_mm2: float
    projected_sram_mm2: float
    projected_content_mm2: float
    logic_ratio: float
    sram_ratio: float
    content_ratio: float
    pad_floor_mm2: float
    die_area_mm2: float
    die_binding: str
    die_ratio: float
    empty_fraction: float
    integration_headroom: float


def node_jump(est: BlockEstimate, ab: AsBuilt) -> NodeJump:
    """Compare the measured design with its target-node projection.

    ``est`` must be the same netlist on the target node (same gates, FFs and
    SRAM), so the ratio is a node effect and nothing else. DTCO deltas inside the
    node are reported separately by the lever waterfall.
    """
    projected_logic = est.cell_area_mm2
    projected_sram = est.sram_area_mm2
    projected_content = est.total_area_mm2
    if projected_content <= 0:
        raise ValueError("projected content area must be positive")
    return NodeJump(
        as_built=ab,
        projected_logic_mm2=projected_logic,
        projected_sram_mm2=projected_sram,
        projected_content_mm2=projected_content,
        logic_ratio=ab.logic_mm2 / projected_logic,
        sram_ratio=ab.sram_mm2 / projected_sram,
        content_ratio=ab.content_mm2 / projected_content,
        pad_floor_mm2=est.pad_floor_mm2,
        die_area_mm2=est.die_area_mm2,
        die_binding=est.die_binding,
        die_ratio=ab.die_mm2 / est.die_area_mm2,
        empty_fraction=max(0.0, 1.0 - projected_content / est.die_area_mm2),
        integration_headroom=(ab.die_mm2 * ab.derived_util) / projected_content,
    )


def pad_sensitivity(cfg, pins: tuple[int, ...] = (96, 160, 240, 320)) -> list[dict[str, float]]:
    """Die floor for a range of signal-pin counts.

    Pin count is a package decision, not a process one, so it is the honest way
    to show how far the die can shrink once the logic stops being the limit.
    """
    from dataclasses import replace

    from .block import pad_limited_die_mm2

    rows: list[dict[str, float]] = []
    for count in pins:
        floor = pad_limited_die_mm2(replace(cfg, pad_pins=count))
        rows.append({"pins": float(count), "die_mm2": floor, "side_mm": floor**0.5})
    return rows

"""Package and pin-budget model.

A pad ring is sized by the chip's interfaces, not by its standard-cell library.
This module turns the interface list into a signal-pin budget, adds IO and core
supply/ground and analog pads, and picks the smallest conventional package that
can carry the result.

The interface variants exist because GRX930's measured 64-bit, 25 MHz off-chip
memory bus is an artifact of its legacy node. At 28 nm the same 64 KB costs
about 0.09 mm2 on-die, so the bus -- not the cell library -- is the largest
remaining area lever on the package.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any


@dataclass(frozen=True)
class PinGroup:
    name: str
    signals: int
    note: str = ""


@dataclass(frozen=True)
class PinBudget:
    variant: str
    label: str
    groups: tuple[PinGroup, ...]
    supply_ratio: float
    core_pairs: int
    analog_pads: int

    @property
    def signal_pads(self) -> int:
        return sum(g.signals for g in self.groups)

    @property
    def io_supply_pairs(self) -> int:
        return ceil(self.signal_pads / self.supply_ratio)

    @property
    def io_supply_pads(self) -> int:
        return 2 * self.io_supply_pairs

    @property
    def core_supply_pads(self) -> int:
        return 2 * self.core_pairs

    @property
    def total_pads(self) -> int:
        return (
            self.signal_pads
            + self.io_supply_pads
            + self.core_supply_pads
            + self.analog_pads
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "label": self.label,
            "signals": self.signal_pads,
            "io_supply_pairs": self.io_supply_pairs,
            "io_supply_pads": self.io_supply_pads,
            "core_supply_pads": self.core_supply_pads,
            "analog_pads": self.analog_pads,
            "total_pads": self.total_pads,
        }

    @classmethod
    def from_spec(cls, spec: dict[str, Any], variant: str) -> "PinBudget":
        variants = spec.get("variants") or {}
        if variant not in variants:
            raise KeyError(f"unknown pin variant {variant!r}")
        raw = variants[variant]
        groups = [
            PinGroup(
                name=str(g["name"]),
                signals=int(g["signals"]),
                note=str(g.get("note", "")),
            )
            for g in spec.get("fixed_groups", [])
        ]
        mem = raw.get("memory")
        if mem:
            data = int(mem.get("data", 0))
            address = int(mem.get("address", 0))
            strobes = int(mem.get("byte_enables", 0))
            control = int(mem.get("control", 0))
            dqs = int(mem.get("dqs", 0))
            if data:
                groups.append(PinGroup("Memory data", data, "D[%d:0]" % (data - 1)))
            if address:
                groups.append(
                    PinGroup("Memory address", address, "A[%d:0]" % (address - 1))
                )
            if strobes:
                groups.append(
                    PinGroup("Memory byte enables", strobes, "BE/DM strobes")
                )
            if dqs:
                groups.append(PinGroup("Memory DQS pairs", dqs, "source-synchronous"))
            if control:
                groups.append(PinGroup("Memory control", control, "CS/WE/OE/CLK"))
        if not groups:
            raise ValueError(f"pin variant {variant!r} has no pin groups")
        return cls(
            variant=variant,
            label=str(raw.get("label", variant)),
            groups=tuple(groups),
            supply_ratio=float(spec.get("supply_ratio", 6)),
            core_pairs=int(spec.get("core_pairs", 8)),
            analog_pads=int(spec.get("analog_pads", 4)),
        )


@dataclass(frozen=True)
class PackageSpec:
    name: str
    kind: str
    pitch_mm: float
    body_mm: float
    pads: int

    @property
    def spare_pads(self) -> int:
        return self.pads


# Conventional, family-level packages. These are package types, not vendor
# part numbers; a real selection also depends on thermal, cost and assembly.
PACKAGES: tuple[PackageSpec, ...] = (
    PackageSpec("QFN-48", "QFN", 0.50, 7.0, 48),
    PackageSpec("QFN-64", "QFN", 0.50, 9.0, 64),
    PackageSpec("QFN-88", "QFN", 0.40, 10.0, 88),
    PackageSpec("QFN-128", "QFN", 0.40, 14.0, 128),
    PackageSpec("TFBGA-144", "TFBGA", 0.50, 10.0, 144),
    PackageSpec("TFBGA-196", "TFBGA", 0.65, 12.0, 196),
    PackageSpec("TFBGA-256", "TFBGA", 0.80, 17.0, 256),
)


def choose_package(
    total_pads: int, die_side_mm: float, clearance_mm: float = 1.5
) -> PackageSpec | None:
    """Smallest package that carries every pad and clears the die.

    QFN is preferred over BGA at equal capability because it is cheaper to
    assemble; among QFN options the smallest body wins. ``clearance_mm`` covers
    the wire-bond fanout and the die-attach fillet.
    """
    fits = [
        p
        for p in PACKAGES
        if p.pads >= total_pads and p.body_mm >= die_side_mm + clearance_mm
    ]
    if not fits:
        return None
    return min(fits, key=lambda p: (0 if p.kind == "QFN" else 1, p.body_mm**2, p.pads))


def die_floor(
    content_mm2: float,
    pad_floor_mm2: float,
    assembly_floor_mm2: float,
) -> tuple[float, str]:
    """Largest of the three constraints, with the binding one named."""
    candidates = (
        (content_mm2, "logic utilisation"),
        (pad_floor_mm2, "pad ring"),
        (assembly_floor_mm2, "assembly minimum"),
    )
    area, binding = max(candidates, key=lambda c: c[0])
    return area, binding

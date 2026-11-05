"""Standard-cell architecture and library generation.

A cell is sized in two independent directions:

  * width  -- active CPP count plus diffusion-isolation overhead, optionally
              reduced by COAG on a FinFET node
  * height -- track count * track pitch, fixed per library

Drive strength comes from *width units* that stack vertically: fins on GRX12F,
gate fingers on GRX28. Adding a unit therefore increases drive without widening
the cell, which is why track height and pin access, not transistor width,
dominate density in both node classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .device import DeviceModel
from .tech import ROOT, Tech, load_tech

LIB_DIR = ROOT / "libraries"


@dataclass(frozen=True)
class CellTemplate:
    name: str
    function: str
    active_cpp: float
    pins: int
    stack_n: int = 1
    stack_p: int = 1
    weight: float = 0.0
    kind: str = "comb"  # comb | seq | clock
    bits: int = 1


# Combinational mix used to compute an average logic cell. Weights sum to 1.0.
CELL_TEMPLATES: tuple[CellTemplate, ...] = (
    CellTemplate("INV_X1", "inverter", 2.0, 2, weight=0.10),
    CellTemplate("BUF_X2", "buffer", 4.0, 2, weight=0.16),
    CellTemplate("NAND2_X1", "nand2", 3.0, 3, stack_n=2, weight=0.20),
    CellTemplate("NOR2_X1", "nor2", 3.0, 3, stack_p=2, weight=0.12),
    CellTemplate("AOI21_X1", "aoi21", 4.0, 4, stack_n=2, weight=0.10),
    CellTemplate("OAI21_X1", "oai21", 4.0, 4, stack_p=2, weight=0.08),
    CellTemplate("MUX2_X1", "mux2", 5.0, 4, weight=0.08),
    CellTemplate("XNOR2_X1", "xnor2", 5.0, 3, weight=0.06),
    CellTemplate("LATCH_X1", "latch", 5.0, 4, weight=0.04),
    CellTemplate("AOI22_X1", "aoi22", 5.0, 5, stack_n=2, stack_p=2, weight=0.06),
)

DFF_TEMPLATE = CellTemplate("DFF_X1", "dff", 9.0, 5, kind="seq")
SDFF_TEMPLATE = CellTemplate("SDFF_X1", "sdff", 11.0, 6, kind="seq")


@dataclass(frozen=True)
class Cell:
    template: CellTemplate
    library: str
    tracks: float
    nfins_n: int
    nfins_p: int
    width_cpp: float
    width_nm: float
    height_nm: float
    area_um2: float
    cin_ff: float
    drive_ua: float
    leakage_nw: float
    coag: bool

    @property
    def name(self) -> str:
        return self.template.name

    @property
    def pins(self) -> int:
        return self.template.pins

    @property
    def is_sequential(self) -> bool:
        return self.template.kind == "seq"

    def as_dict(self) -> dict[str, object]:
        return {
            "cell": self.name,
            "width_cpp": round(self.width_cpp, 2),
            "width_nm": round(self.width_nm, 1),
            "height_nm": round(self.height_nm, 1),
            "area_um2": round(self.area_um2, 4),
            "nfins_n": self.nfins_n,
            "nfins_p": self.nfins_p,
            "cin_ff": round(self.cin_ff, 4),
            "drive_ua": round(self.drive_ua, 1),
            "leakage_nw": round(self.leakage_nw, 3),
        }


@dataclass
class Library:
    id: str
    label: str
    tech: Tech
    tracks: float
    base_fins: int
    isolation: str
    coag: bool
    mbff_bits: tuple[int, ...] = (1,)
    beol_scale: float = 1.0
    role: str = "candidate"
    notes: str = ""
    cells: dict[str, Cell] = field(default_factory=dict)

    # -- construction -----------------------------------------------------
    @classmethod
    def build(
        cls,
        tech: Tech,
        *,
        id: str,
        label: str,
        tracks: float,
        base_fins: int,
        isolation: str,
        coag: bool,
        mbff_bits: tuple[int, ...] = (1,),
        role: str = "candidate",
        notes: str = "",
    ) -> "Library":
        if tracks not in (9.0, 7.5, 6.0, 5.5):
            raise ValueError(f"unsupported track height {tracks}")
        if base_fins < 1:
            raise ValueError("base_fins must be >= 1")
        lib = cls(
            id=id,
            label=label,
            tech=tech,
            tracks=tracks,
            base_fins=base_fins,
            isolation=isolation,
            coag=coag,
            mbff_bits=mbff_bits,
            role=role,
            notes=notes,
        )
        lib._populate()
        return lib

    def _populate(self) -> None:
        model = DeviceModel(self.tech)
        isolation = self.tech.isolation_overhead_cpp(self.isolation)
        height = self.tech.cell_height_nm(self.tracks)
        max_fins = self.tech.max_fins_per_device(self.tracks)

        for tpl in (*CELL_TEMPLATES, DFF_TEMPLATE, SDFF_TEMPLATE):
            nfins_n = self.base_fins * tpl.stack_n
            nfins_p = self.base_fins * tpl.stack_p
            if nfins_n > max_fins or nfins_p > max_fins:
                raise ValueError(
                    f"{self.id}/{tpl.name}: {nfins_n}N/{nfins_p}P fins do not fit "
                    f"in {self.tracks}T (max {max_fins} per device)"
                )
            width_cpp = tpl.active_cpp + isolation
            if self.coag:
                width_cpp -= self.tech.coag_cpp_saving
            width_cpp = max(2.0, width_cpp)
            width_nm = width_cpp * self.tech.cpp_nm
            cin = model.cap_per_fin_ff("n") * nfins_n / tpl.stack_n
            cin += model.cap_per_fin_ff("p") * nfins_p / tpl.stack_p
            ion_n = model.ion_per_fin_ua("n", self.tech.vdd_hp) * nfins_n / tpl.stack_n
            ion_p = model.ion_per_fin_ua("p", self.tech.vdd_hp) * nfins_p / tpl.stack_p
            ioff = model.ioff_per_fin_na("n", self.tech.vdd_hp) * nfins_n
            ioff += model.ioff_per_fin_na("p", self.tech.vdd_hp) * nfins_p
            self.cells[tpl.name] = Cell(
                template=tpl,
                library=self.id,
                tracks=self.tracks,
                nfins_n=nfins_n,
                nfins_p=nfins_p,
                width_cpp=width_cpp,
                width_nm=width_nm,
                height_nm=height,
                area_um2=width_nm * height / 1e6,
                cin_ff=cin,
                drive_ua=min(ion_n, ion_p),
                leakage_nw=ioff * self.tech.vdd_hp,
                coag=self.coag,
            )

    # -- aggregates -------------------------------------------------------
    @property
    def cell_height_nm(self) -> float:
        return self.tech.cell_height_nm(self.tracks)

    @property
    def unit_name(self) -> str:
        return self.tech.width_unit_name

    @property
    def usable_tracks(self) -> float:
        return self.tech.usable_tracks(self.tracks)

    @property
    def comb_cells(self) -> list[Cell]:
        return [c for c in self.cells.values() if c.template.kind == "comb"]

    @property
    def avg_cell_area_um2(self) -> float:
        total = sum(c.template.weight for c in self.comb_cells)
        return sum(c.area_um2 * c.template.weight for c in self.comb_cells) / total

    @property
    def avg_pins(self) -> float:
        total = sum(c.template.weight for c in self.comb_cells)
        return sum(c.pins * c.template.weight for c in self.comb_cells) / total

    @property
    def avg_cin_ff(self) -> float:
        total = sum(c.template.weight for c in self.comb_cells)
        return sum(c.cin_ff * c.template.weight for c in self.comb_cells) / total

    @property
    def avg_leakage_nw(self) -> float:
        total = sum(c.template.weight for c in self.comb_cells)
        return sum(c.leakage_nw * c.template.weight for c in self.comb_cells) / total

    @property
    def dff_area_um2(self) -> float:
        return self.cells["DFF_X1"].area_um2

    def dff_area_per_bit_um2(self, bits: int) -> float:
        """Area per stored bit for a 2-bit or 4-bit merged flip-flop."""
        if bits <= 1:
            return self.dff_area_um2
        model = self.tech.model.get("mbff", {}).get(str(bits))
        if model is None:
            raise ValueError(f"no MBFF model for {bits}-bit in {self.tech.name}")
        return self.dff_area_um2 * float(model["area_per_bit"])

    def clock_cap_per_bit_ff(self, bits: int) -> float:
        base = float(self.tech.model.get("block", {}).get("clock_cap_ff_per_bit", 0.3))
        if bits <= 1:
            return base
        model = self.tech.model.get("mbff", {}).get(str(bits))
        return base * float(model["clock_cap_per_bit"])

    @property
    def fo4_ps(self) -> float:
        return DeviceModel(self.tech).stage(
            self.base_fins, self.base_fins, self.tech.vdd_hp, coag=self.coag
        ).fo4_ps

    @property
    def driver_ron_ohm(self) -> float:
        return DeviceModel(self.tech).stage(
            self.base_fins, self.base_fins, self.tech.vdd_hp, coag=self.coag
        ).ron_ohm

    @property
    def pin_capacity(self) -> float:
        demand = float(self.tech.model.get("routing", {}).get("pin_track_demand", 1.3))
        return self.usable_tracks / (demand * self.avg_pins)

    def routable_utilization(self, pin_aware: bool = False) -> float:
        routing = self.tech.model.get("routing", {})
        ceiling = float(routing.get("util_ceiling", 0.82))
        gain = float(routing.get("pin_aware_util_gain", 0.0)) if pin_aware else 0.0
        exponent = float(routing.get("util_exponent", 0.35))
        capacity = self.pin_capacity * (1.0 + gain)
        return ceiling * min(1.0, capacity / 1.6) ** exponent

    @property
    def leakage_index(self) -> float:
        return self.avg_leakage_nw * self.base_fins

    def describe(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "tracks": self.tracks,
            "cell_height_nm": round(self.cell_height_nm, 1),
            "base_units": self.base_fins,
            "unit": self.unit_name,
            "isolation": self.isolation,
            "coag": self.coag,
            "avg_cell_area_um2": round(self.avg_cell_area_um2, 4),
            "avg_pins": round(self.avg_pins, 2),
            "pin_capacity": round(self.pin_capacity, 2),
            "routable_util": round(self.routable_utilization(), 3),
            "fo4_ps": round(self.fo4_ps, 2),
            "leakage_nw": round(self.avg_leakage_nw, 3),
        }


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def load_library(path: str | Path, tech: Tech | None = None) -> Library:
    path = Path(path)
    if not path.is_absolute():
        path = LIB_DIR / path
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    tech = tech or load_tech(raw.get("tech", "grx12f.yaml"))
    return Library.build(
        tech,
        id=str(raw["id"]),
        label=str(raw["label"]),
        tracks=float(raw["tracks"]),
        base_fins=int(raw["base_fins"]),
        isolation=str(raw["isolation"]),
        coag=bool(raw["coag"]),
        mbff_bits=tuple(int(b) for b in raw.get("mbff_bits", [1])),
        role=str(raw.get("role", "candidate")),
        notes=str(raw.get("notes", "")).strip(),
    )


def load_libraries(tech: Tech | None = None) -> dict[str, Library]:
    """Load every library, or only those declared against ``tech``."""
    libs: dict[str, Library] = {}
    for path in sorted(LIB_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if tech is not None and str(raw.get("tech")) != tech.path.name:
            continue
        lib = load_library(path, tech=tech)
        libs[lib.id] = lib
    if not libs:
        raise FileNotFoundError(f"no library definitions for {tech.name if tech else LIB_DIR}")
    return libs

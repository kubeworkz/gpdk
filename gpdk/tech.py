"""Technology definition: geometry, devices, cell options and BEOL.

The same schema describes a FinFET node (GRX12F) and a planar node (GRX28).
A *width unit* is one fin on the FinFET node and one gate finger on the planar
node; both stack inside the cell height, so the cell-area model is shared.

Everything in this package is a *planning model*. The tech files are the single
source of truth; the rest of the package derives from them so that a change to a
pitch or a track height propagates to cells, wires and block estimates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
TECH_DIR = ROOT / "tech"


@dataclass(frozen=True)
class Polarity:
    vt_v: float
    ss_mv_dec: float
    dibl_mv_v: float
    ion_ua_per_um: float
    ioff_na_per_um: float
    temp_ioff_factor: float


@dataclass(frozen=True)
class Layer:
    name: str
    direction: str
    pitch_nm: float
    width_nm: float
    thickness_nm: float
    ild_nm: float

    def __post_init__(self) -> None:
        if self.direction not in ("vertical", "horizontal"):
            raise ValueError(f"{self.name}: direction must be vertical or horizontal")
        if self.pitch_nm <= self.width_nm:
            raise ValueError(f"{self.name}: pitch must exceed width")

    @property
    def space_nm(self) -> float:
        return self.pitch_nm - self.width_nm


@dataclass(frozen=True)
class Sram:
    hd_bitcell_um2: float
    hc_bitcell_um2: float


@dataclass(frozen=True)
class Tech:
    name: str
    revision: str
    node_class: str
    device_kind: str
    provenance: str
    vdd_hp: float
    vdd_hd: float
    temp_c: float
    cpp_nm: float
    gate_length_nm: float
    fin_pitch_nm: float
    fin_height_nm: float
    fin_width_nm: float
    eot_nm: float
    spacer_nm: float
    nfet: Polarity
    pfet: Polarity
    track_pitch_nm: float
    rail_width_nm: float
    edge_margin_nm: float
    fin_group_gap_nm: float
    isolation_cpp: dict[str, float]
    coag_cpp_saving: float
    coag_rg_reduction: float
    sram: Sram
    ild_k: float
    barrier_nm: float
    cu_resistivity_ohm_m: float
    cu_mean_free_path_nm: float
    layers: tuple[Layer, ...]
    via_pillar_enabled: bool
    via_pillar_resistance_reduction: float
    via_pillar_landing_relaxation: float
    model: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    # -- geometry ---------------------------------------------------------
    @property
    def width_unit_name(self) -> str:
        return "fin" if self.device_kind == "finfet" else "finger"

    @property
    def weff_per_fin_nm(self) -> float:
        """Effective width of one width unit (a fin or a planar finger)."""
        if self.device_kind == "planar":
            return self.fin_width_nm
        return 2.0 * self.fin_height_nm + self.fin_width_nm

    @property
    def weff_per_fin_um(self) -> float:
        return self.weff_per_fin_nm / 1000.0

    def cell_height_nm(self, tracks: float) -> float:
        if tracks <= 2:
            raise ValueError("a cell needs at least two tracks for the rails")
        return tracks * self.track_pitch_nm

    def usable_tracks(self, tracks: float) -> float:
        """M2 tracks left after the two power rails."""
        return max(0.0, tracks - 2.0)

    def max_fins_per_device(self, tracks: float) -> int:
        """Width units that physically fit in one device group (P or N).

        The cell keeps an edge margin under each rail and one isolation gap
        between the N and P groups. Each group is ``(n-1) * pitch + width``
        tall; the two groups share the remaining height.
        """
        usable = (
            self.cell_height_nm(tracks)
            - 2.0 * self.edge_margin_nm
            - self.fin_group_gap_nm
        )
        if usable <= 0:
            return 0
        if self.device_kind == "planar":
            span = usable / 2.0 - self.fin_width_nm
            if span < 0:
                return 0
            return max(0, int(math.floor(span / self.fin_pitch_nm)) + 1)
        return max(0, int(math.floor(usable / (2.0 * self.fin_pitch_nm))) + 1)

    def max_fins_total(self, tracks: float) -> int:
        usable = self.cell_height_nm(tracks) - 2.0 * self.edge_margin_nm
        return max(0, int(math.floor(usable / self.fin_pitch_nm)) + 1)

    def isolation_overhead_cpp(self, isolation: str) -> float:
        try:
            return float(self.isolation_cpp[isolation])
        except KeyError as exc:
            raise ValueError(
                f"unknown isolation {isolation!r}; choose from "
                f"{sorted(self.isolation_cpp)}"
            ) from exc

    # -- layers -----------------------------------------------------------
    def layer(self, name: str) -> Layer:
        for layer in self.layers:
            if layer.name == name:
                return layer
        raise KeyError(f"no layer {name!r} in {self.name}")

    @property
    def m1(self) -> Layer:
        return self.layer("M1")

    @property
    def m2(self) -> Layer:
        return self.layer("M2")

    @property
    def m3(self) -> Layer:
        return self.layer("M3")

    # -- variants ---------------------------------------------------------
    def with_beol_scale(self, scale: float, names: tuple[str, ...] = ("M1", "M2", "M3")) -> "Tech":
        """Return a copy with selected layer pitches (and track pitch) scaled.

        Used by the BEOL DTCO lever. Layers are scaled only in pitch and width;
        thickness stays fixed so resistance does not improve for free.
        """
        if not 0.5 <= scale <= 1.0:
            raise ValueError("beol scale must be in [0.5, 1.0]")
        scaled: list[Layer] = []
        for layer in self.layers:
            if layer.name in names:
                scaled.append(
                    replace(
                        layer,
                        pitch_nm=round(layer.pitch_nm * scale, 3),
                        width_nm=round(layer.width_nm * scale, 3),
                        ild_nm=round(layer.ild_nm * scale, 3),
                    )
                )
            else:
                scaled.append(layer)
        return replace(
            self,
            layers=tuple(scaled),
            track_pitch_nm=round(self.track_pitch_nm * scale, 3),
        )

    def scaled_for_pitch(self, pitch_nm: float) -> "Tech":
        """Copy of the tech whose track pitch is an explicit value."""
        return self.with_beol_scale(pitch_nm / self.track_pitch_nm)

    # -- validation -------------------------------------------------------
    def validate(self) -> None:
        errors: list[str] = []
        if self.cpp_nm <= self.gate_length_nm + 2 * self.spacer_nm:
            errors.append("CPP must exceed Lg + 2*spacer")
        if self.device_kind not in ("finfet", "planar"):
            errors.append("device_kind must be finfet or planar")
        if self.fin_pitch_nm <= self.fin_width_nm:
            errors.append("width-unit pitch must exceed its width")
        if self.device_kind == "finfet" and self.fin_height_nm <= 0:
            errors.append("a FinFET needs a non-zero fin height")
        if self.track_pitch_nm <= self.m2.width_nm:
            errors.append("track pitch must exceed M2 width")
        for tracks in (9.0, 7.5, 6.0, 5.5):
            if self.max_fins_per_device(tracks) < 1:
                errors.append(f"{tracks}T cell cannot fit a single fin")
        if not 0.5 <= self.vdd_hp <= 1.0:
            errors.append("vdd_hp outside the 0.5-1.0 V range for this node class")
        if self.model.get("routing", {}).get("util_ceiling", 0) > 0.95:
            errors.append("routing.util_ceiling above 95% is not credible")
        if errors:
            raise ValueError(f"{self.name}: " + "; ".join(errors))

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "revision": self.revision,
            "class": self.node_class,
            "device_kind": self.device_kind,
            "cpp_nm": self.cpp_nm,
            "fin_pitch_nm": self.fin_pitch_nm,
            "weff_per_fin_nm": self.weff_per_fin_nm,
            "track_pitch_nm": self.track_pitch_nm,
            "cell_heights_nm": {t: self.cell_height_nm(t) for t in (9.0, 7.5, 6.0, 5.5)},
            "max_fins_per_device": {
                t: self.max_fins_per_device(t) for t in (9.0, 7.5, 6.0, 5.5)
            },
            "vdd_hp": self.vdd_hp,
            "sram_hd_um2": self.sram.hd_bitcell_um2,
        }


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _polarity(raw: dict[str, Any]) -> Polarity:
    return Polarity(
        vt_v=float(raw["vt_v"]),
        ss_mv_dec=float(raw["ss_mv_dec"]),
        dibl_mv_v=float(raw["dibl_mv_v"]),
        ion_ua_per_um=float(raw["ion_ua_per_um"]),
        ioff_na_per_um=float(raw["ioff_na_per_um"]),
        temp_ioff_factor=float(raw["temp_ioff_factor"]),
    )


def load_tech(path: str | Path) -> Tech:
    path = Path(path)
    if not path.is_absolute():
        path = TECH_DIR / path
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    dev = raw["device"]
    cell = raw["cell"]
    il = raw["interconnect"]
    supply = raw["supply"]
    tech = Tech(
        name=str(raw["name"]),
        revision=str(raw["revision"]),
        node_class=str(raw["node_class"]),
        device_kind=str(dev.get("kind", "finfet")),
        provenance=str(raw["provenance"]).strip(),
        vdd_hp=float(supply["vdd_hp"]),
        vdd_hd=float(supply["vdd_hd"]),
        temp_c=float(supply["temp_c"]),
        cpp_nm=float(dev["cpp_nm"]),
        gate_length_nm=float(dev["gate_length_nm"]),
        fin_pitch_nm=float(dev.get("finger_pitch_nm", dev.get("fin_pitch_nm"))),
        fin_height_nm=float(dev.get("fin_height_nm", 0.0)),
        fin_width_nm=float(dev.get("finger_width_nm", dev.get("fin_width_nm"))),
        eot_nm=float(dev["eot_nm"]),
        spacer_nm=float(dev["spacer_nm"]),
        nfet=_polarity(dev["nfet"]),
        pfet=_polarity(dev["pfet"]),
        track_pitch_nm=float(cell["track_pitch_nm"]),
        rail_width_nm=float(cell["rail_width_nm"]),
        edge_margin_nm=float(cell["edge_margin_nm"]),
        fin_group_gap_nm=float(cell["fin_group_gap_nm"]),
        isolation_cpp={str(k): float(v) for k, v in cell["isolation_cpp"].items()},
        coag_cpp_saving=float(cell["coag_cpp_saving"]),
        coag_rg_reduction=float(cell["coag_rg_reduction"]),
        sram=Sram(
            hd_bitcell_um2=float(raw["sram"]["hd_bitcell_um2"]),
            hc_bitcell_um2=float(raw["sram"]["hc_bitcell_um2"]),
        ),
        ild_k=float(il["ild_k"]),
        barrier_nm=float(il["barrier_nm"]),
        cu_resistivity_ohm_m=float(il["cu_resistivity_ohm_m"]),
        cu_mean_free_path_nm=float(il["cu_mean_free_path_nm"]),
        layers=tuple(
            Layer(
                name=str(l["name"]),
                direction=str(l["direction"]),
                pitch_nm=float(l["pitch_nm"]),
                width_nm=float(l["width_nm"]),
                thickness_nm=float(l["thickness_nm"]),
                ild_nm=float(l["ild_nm"]),
            )
            for l in il["layers"]
        ),
        via_pillar_enabled=bool(il["via_pillar"]["enabled"]),
        via_pillar_resistance_reduction=float(il["via_pillar"]["resistance_reduction"]),
        via_pillar_landing_relaxation=float(il["via_pillar"]["landing_pad_relaxation"]),
        model=raw.get("model", {}),
        path=path,
    )
    tech.validate()
    return tech

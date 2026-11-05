"""Back-end-of-line electrical model.

Interconnect is often what actually sets block area: if the router runs out of
tracks the block is inflated until DRCs close. This module computes per-layer
resistance and capacitance from geometry, including the copper size effect that
makes narrow wires far more resistive than bulk copper at either node.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tech import Layer, Tech

EPS0_F_PER_M = 8.854e-12


@dataclass(frozen=True)
class LayerRC:
    name: str
    direction: str
    pitch_nm: float
    width_nm: float
    thickness_nm: float
    space_nm: float
    r_ohm_per_um: float
    c_ff_per_um: float

    @property
    def rc_ps_per_um2(self) -> float:
        """Distributed RC product; multiply by length^2 for delay in ps."""
        return self.r_ohm_per_um * self.c_ff_per_um * 1e-3

    def as_dict(self) -> dict[str, object]:
        return {
            "layer": self.name,
            "direction": self.direction,
            "pitch_nm": self.pitch_nm,
            "width_nm": self.width_nm,
            "r_ohm_per_um": round(self.r_ohm_per_um, 2),
            "c_ff_per_um": round(self.c_ff_per_um, 4),
            "rc_ps_per_um2": round(self.rc_ps_per_um2, 4),
        }


def effective_resistivity_ohm_m(tech: Tech, width_nm: float) -> float:
    """Copper resistivity with barrier loss and Fuchs-Sondheimer size effect."""
    barrier = tech.barrier_nm
    w_eff = max(width_nm - 2.0 * barrier, 1.0)
    return tech.cu_resistivity_ohm_m * (
        1.0 + tech.cu_mean_free_path_nm / w_eff
    )


def layer_rc(tech: Tech, layer: Layer) -> LayerRC:
    barrier = tech.barrier_nm
    w_eff = max(layer.width_nm - 2.0 * barrier, 1.0)
    t_eff = max(layer.thickness_nm - 2.0 * barrier, 1.0)
    rho = effective_resistivity_ohm_m(tech, layer.width_nm)
    r_per_m = rho / (w_eff * 1e-9 * t_eff * 1e-9)
    r_per_um = r_per_m / 1e6

    eps = EPS0_F_PER_M * tech.ild_k
    c_plate = eps * (layer.width_nm * 1e-9) / (layer.ild_nm * 1e-9)
    c_couple = 2.0 * eps * (layer.thickness_nm * 1e-9) / (layer.space_nm * 1e-9)
    c_ff_per_um = (c_plate + c_couple) * 1e9

    return LayerRC(
        name=layer.name,
        direction=layer.direction,
        pitch_nm=layer.pitch_nm,
        width_nm=layer.width_nm,
        thickness_nm=layer.thickness_nm,
        space_nm=layer.space_nm,
        r_ohm_per_um=r_per_um,
        c_ff_per_um=c_ff_per_um,
    )


def layer_table(tech: Tech) -> list[LayerRC]:
    return [layer_rc(tech, layer) for layer in tech.layers]


def via_resistance_ohm(tech: Tech, layer: Layer, pillar: bool | None = None) -> float:
    """Resistance of one via landing between two adjacent metal layers.

    A via is approximated as a square landing at 80% of the layer width. The
    3x contact factor accounts for barrier/interface resistance, which dominates
    at these dimensions.
    """
    pillar = tech.via_pillar_enabled if pillar is None else pillar
    rho = effective_resistivity_ohm_m(tech, layer.width_nm)
    side = 0.8 * layer.width_nm
    height = layer.thickness_nm
    r = rho * height * 1e-9 / ((side * 1e-9) ** 2) * 3.0
    if pillar:
        r *= 1.0 - tech.via_pillar_resistance_reduction
    return r


def wire_delay_ps(
    rc: LayerRC,
    length_um: float,
    driver_ohm: float,
    *,
    pillar: bool = False,
) -> float:
    """Extra delay of a wire, on top of the driver's FO4 delay.

    Distributed RC (0.38*R*C*L^2) plus the driver charging the wire capacitance
    (0.69*Rs*C*L). The receiver's gate capacitance is already inside the FO4
    number, so it is not counted twice here.
    """
    if length_um <= 0:
        return 0.0
    distributed = 0.38 * rc.rc_ps_per_um2 * length_um**2
    driver_term = 0.69 * driver_ohm * rc.c_ff_per_um * length_um * 1e-3
    total = distributed + driver_term
    if pillar:
        total *= 0.96  # fewer via stacks in the average local route
    return total


def summary(tech: Tech) -> dict[str, object]:
    table = layer_table(tech)
    return {
        "ild_k": tech.ild_k,
        "barrier_nm": tech.barrier_nm,
        "via_pillar": tech.via_pillar_enabled,
        "layers": [row.as_dict() for row in table],
        "m3": next(r.as_dict() for r in table if r.name == "M3"),
    }

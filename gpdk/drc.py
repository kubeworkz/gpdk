"""A small, explicit DRC deck for the GRX12F demo cell.

It is not a production rule deck. It checks exactly the rules that matter for
the DTCO choices in this package:

  * fin and gate grids (placement legality)
  * cell height versus track height
  * COAG: the gate contact must sit inside the gate and over active
  * contact enclosure by the local interconnect and metals
  * min width / min space on every drawn layer
  * power rails at the top and bottom of the cell
"""

from __future__ import annotations

from dataclasses import dataclass

from .layout import Layout, Shape
from .tech import Tech

VIA_RULES = {
    "VIA0": {"size": 12, "space": 24},
    "VIA1": {"size": 14, "space": 28},
}
MD_MIN_WIDTH = 16
MD_MIN_SPACE = 24
MD_PC_MIN_SPACE = 18
PC_MIN_SPACE = 30


@dataclass(frozen=True)
class Violation:
    rule: str
    layer: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.layer}: {self.message}"


def _min_width(tech: Tech, layer: str) -> float:
    if layer in VIA_RULES:
        return VIA_RULES[layer]["size"]
    if layer == "PC":
        return tech.gate_length_nm
    if layer == "MD":
        return MD_MIN_WIDTH
    if layer == "FIN":
        return tech.fin_width_nm
    return tech.layer(layer).width_nm


def _min_space(tech: Tech, layer: str) -> float:
    if layer in VIA_RULES:
        return VIA_RULES[layer]["space"]
    if layer == "MD":
        return MD_MIN_SPACE
    if layer == "PC":
        return PC_MIN_SPACE
    if layer == "FIN":
        return tech.fin_pitch_nm - tech.fin_width_nm
    if layer == "M2":
        return tech.m2.pitch_nm - tech.m2.width_nm
    return tech.layer(layer).space_nm


def check(layout: Layout, tech: Tech, tracks: float = 7.5) -> list[Violation]:
    v: list[Violation] = []
    height = tech.cell_height_nm(tracks)
    width = layout.width_nm()

    # -- cell frame -------------------------------------------------------
    boundaries = layout.on("BOUNDARY")
    if len(boundaries) != 1:
        v.append(Violation("cell-frame", "BOUNDARY", "exactly one boundary is required"))
    if abs(layout.height_nm() - height) > 0.5:
        v.append(
            Violation(
                "cell-height",
                "BOUNDARY",
                f"height {layout.height_nm()} nm != {tracks}T * "
                f"{tech.track_pitch_nm} nm = {height:.1f} nm",
            )
        )
    if width < 2 * tech.cpp_nm:
        v.append(
            Violation(
                "cell-width",
                "BOUNDARY",
                f"width {width} nm below the 2 CPP minimum of {2*tech.cpp_nm:.0f} nm",
            )
        )

    # -- min width --------------------------------------------------------
    for shape in layout.shapes:
        if shape.layer == "BOUNDARY":
            continue
        need = _min_width(tech, shape.layer)
        actual = min(shape.width, shape.height)
        if actual + 1e-6 < need:
            v.append(
                Violation(
                    "min-width",
                    shape.layer,
                    f"{actual} nm < {need:.1f} nm at {shape.bbox()}",
                )
            )

    # -- min space --------------------------------------------------------
    by_layer: dict[str, list[Shape]] = {}
    for shape in layout.shapes:
        if shape.layer != "BOUNDARY":
            by_layer.setdefault(shape.layer, []).append(shape)
    for layer, shapes in by_layer.items():
        need = _min_space(tech, layer)
        for i, a in enumerate(shapes):
            for b in shapes[i + 1 :]:
                gap = Shape.gap(a, b)
                if gap + 1e-6 < need:
                    v.append(
                        Violation(
                            "min-space",
                            layer,
                            f"gap {gap:.1f} nm < {need:.1f} nm between {a.bbox()} and {b.bbox()}",
                        )
                    )

    # -- fin / gate grids -------------------------------------------------
    for fin in layout.on("FIN"):
        center = fin.center_y
        offset = (center - tech.fin_pitch_nm / 2.0) % tech.fin_pitch_nm
        if min(offset, tech.fin_pitch_nm - offset) > 0.6:
            v.append(
                Violation(
                    "fin-grid",
                    "FIN",
                    f"fin centre y={center:.1f} off the {tech.fin_pitch_nm} nm grid",
                )
            )
    for gate in layout.on("PC"):
        if gate.x0 % round(tech.cpp_nm) != 0:
            v.append(
                Violation(
                    "gate-grid",
                    "PC",
                    f"gate x0={gate.x0} off the {tech.cpp_nm:.0f} nm CPP grid",
                )
            )
        if abs(gate.width - tech.gate_length_nm) > 1.0:
            v.append(
                Violation(
                    "gate-length",
                    "PC",
                    f"drawn Lg {gate.width} nm != {tech.gate_length_nm:.1f} nm",
                )
            )

    # -- contacts ---------------------------------------------------------
    fins = layout.on("FIN")
    for md in layout.on("MD"):
        under = [f for f in fins if md.overlaps(f)]
        if not under:
            v.append(Violation("md-active", "MD", f"contact at {md.bbox()} lands on no fin"))
            continue
        for fin in under:
            if md.y0 > fin.y0 - 6 or md.y1 < fin.y1 + 6:
                v.append(
                    Violation(
                        "md-enclosure",
                        "MD",
                        f"contact {md.bbox()} must enclose fin {fin.bbox()} by 6 nm",
                    )
                )
            if md.overlap_area(fin) < 12 * fin.height:
                v.append(
                    Violation(
                        "md-overlap",
                        "MD",
                        f"contact {md.bbox()} overlaps fin {fin.bbox()} by too little",
                    )
                )

    for md in layout.on("MD"):
        for gate in layout.on("PC"):
            gap = Shape.gap(md, gate)
            if gap + 1e-6 < MD_PC_MIN_SPACE:
                v.append(
                    Violation(
                        "md-pc-space",
                        "MD",
                        f"contact-to-gate gap {gap:.1f} nm < {MD_PC_MIN_SPACE} nm",
                    )
                )

    for via in layout.on("VIA0"):
        gates = [g for g in layout.on("PC") if g.contains(via, margin=2)]
        if not gates:
            v.append(
                Violation(
                    "coag-enclosure",
                    "VIA0",
                    f"gate contact {via.bbox()} must be inside a gate with 2 nm margin",
                )
            )
        if not any(via.overlaps(f) for f in fins):
            v.append(
                Violation(
                    "coag-active",
                    "VIA0",
                    f"gate contact {via.bbox()} is not over active (COAG requires it)",
                )
            )
        if not any(m.contains(via, margin=2) for m in layout.on("M0")):
            v.append(
                Violation(
                    "m0-enclosure",
                    "VIA0",
                    f"local interconnect must enclose {via.bbox()} by 2 nm",
                )
            )

    for via in layout.on("VIA1"):
        if not any(m.contains(via, margin=4) for m in layout.on("M1")):
            v.append(
                Violation(
                    "m1-enclosure",
                    "VIA1",
                    f"M1 must enclose {via.bbox()} by 4 nm",
                )
            )
        if not any(m.contains(via, margin=4) for m in layout.on("M2")):
            v.append(
                Violation(
                    "m2-enclosure",
                    "VIA1",
                    f"M2 must enclose {via.bbox()} by 4 nm",
                )
            )

    # -- power rails ------------------------------------------------------
    rails = layout.on("M2")
    bottom = [r for r in rails if r.y0 == 0]
    top = [r for r in rails if abs(r.y1 - height) < 0.5]
    for name, found in (("VSS", bottom), ("VDD", top)):
        if not found:
            v.append(Violation("power-rail", "M2", f"missing {name} rail"))
        elif not any(abs(r.width - width) < 1.0 and r.height >= tech.rail_width_nm for r in found):
            v.append(
                Violation(
                    "power-rail",
                    "M2",
                    f"{name} rail must span the cell and be at least "
                    f"{tech.rail_width_nm:.0f} nm tall",
                )
            )

    return v


def summarize(layout: Layout, violations: list[Violation]) -> dict[str, object]:
    return {
        "layout": layout.name,
        "width_nm": layout.width_nm(),
        "height_nm": layout.height_nm(),
        "shapes": len(layout.shapes),
        "violations": len(violations),
        "details": [str(x) for x in violations],
    }

"""Abstract cell layouts for the GRX12F PDK demo.

Coordinates are integer nanometres. This is not a full transistor-level layout
database; it is enough geometry to exercise the interesting DTCO rules:
continuous diffusion, COAG, fin/gate grids, contact enclosure and local
interconnect spacing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tech import Tech

# GDS layer numbers used by the demo and by the SVG renderer.
LAYER_ORDER = ("FIN", "PC", "MD", "M0", "VIA0", "M1", "VIA1", "M2", "BOUNDARY")
LAYER_COLORS = {
    "FIN": "#2f6f4e",
    "PC": "#c0392b",
    "MD": "#8e44ad",
    "M0": "#2980b9",
    "VIA0": "#e67e22",
    "M1": "#16a085",
    "VIA1": "#d35400",
    "M2": "#34495e",
    "BOUNDARY": "#111111",
}
GDS_LAYERS = {
    "FIN": 1,
    "PC": 2,
    "MD": 3,
    "M0": 4,
    "VIA0": 5,
    "M1": 6,
    "VIA1": 7,
    "M2": 8,
    "BOUNDARY": 63,
}


@dataclass(frozen=True)
class Shape:
    layer: str
    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self) -> None:
        if self.layer not in GDS_LAYERS:
            raise ValueError(f"unknown layer {self.layer!r}")
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError(f"degenerate shape on {self.layer}: {self}")

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2.0

    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x0, self.y0, self.x1, self.y1)

    def overlaps(self, other: "Shape") -> bool:
        return (
            self.x0 < other.x1
            and other.x0 < self.x1
            and self.y0 < other.y1
            and other.y0 < self.y1
        )

    def overlap_area(self, other: "Shape") -> int:
        dx = max(0, min(self.x1, other.x1) - max(self.x0, other.x0))
        dy = max(0, min(self.y1, other.y1) - max(self.y0, other.y0))
        return dx * dy

    def contains(self, other: "Shape", margin: int = 0) -> bool:
        return (
            self.x0 <= other.x0 - margin
            and self.y0 <= other.y0 - margin
            and self.x1 >= other.x1 + margin
            and self.y1 >= other.y1 + margin
        )

    @staticmethod
    def gap(a: "Shape", b: "Shape") -> float:
        """Euclidean edge-to-edge distance (0 when they overlap)."""
        dx = max(0, max(a.x0, b.x0) - min(a.x1, b.x1))
        dy = max(0, max(a.y0, b.y0) - min(a.y1, b.y1))
        return (dx * dx + dy * dy) ** 0.5


@dataclass
class Layout:
    name: str
    shapes: list[Shape] = field(default_factory=list)

    def add(self, layer: str, x0: int, y0: int, x1: int, y1: int) -> Shape:
        shape = Shape(layer, int(x0), int(y0), int(x1), int(y1))
        self.shapes.append(shape)
        return shape

    def on(self, layer: str) -> list[Shape]:
        return [s for s in self.shapes if s.layer == layer]

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        if not self.shapes:
            raise ValueError("empty layout")
        xs = [s.x0 for s in self.shapes] + [s.x1 for s in self.shapes]
        ys = [s.y0 for s in self.shapes] + [s.y1 for s in self.shapes]
        return min(xs), min(ys), max(xs), max(ys)

    def width_nm(self) -> int:
        b = self.bbox
        return b[2] - b[0]

    def height_nm(self) -> int:
        b = self.bbox
        return b[3] - b[1]


def inverter_layout(
    tech: Tech,
    *,
    tracks: float = 7.5,
    coag: bool = True,
) -> Layout:
    """Single-fin inverter with continuous diffusion and optional COAG.

    The cell is 2.5 CPP wide and uses the whole 7.5T height. Fins run
    continuously through the cell (CNOD); the single gate is placed on the CPP
    grid. With COAG the gate contact lands over the P fin instead of beside it,
    which is what allows the compact width.
    """
    height = int(tech.cell_height_nm(tracks))
    cpp = tech.cpp_nm
    width = int(round(2.5 * cpp))
    fin_w = tech.fin_width_nm
    fin_y = 140.0
    p_fin_y = 340.0
    gate_l = int(round(cpp))          # 84: gate sits on the first CPP grid line
    gate_w = int(round(tech.gate_length_nm))
    rail = int(round(tech.rail_width_nm))

    lay = Layout(name=f"INV_{int(tracks*10)}T_{'COAG' if coag else 'noCOAG'}")
    lay.add("BOUNDARY", 0, 0, width, height)

    # Continuous fins (CNOD): no diffusion break inside the cell.
    lay.add("FIN", 0, int(fin_y - fin_w / 2), width, int(fin_y + fin_w / 2))
    lay.add("FIN", 0, int(p_fin_y - fin_w / 2), width, int(p_fin_y + fin_w / 2))

    # Gate stripe crossing both fins.
    lay.add("PC", gate_l, 120, gate_l + gate_w, 360)

    # Source/drain contacts: drains on the left, sources on the right.
    md_w, md_h = 18, 24
    lay.add("MD", 30, int(fin_y - md_h / 2), 30 + md_w, int(fin_y + md_h / 2))
    lay.add("MD", 30, int(p_fin_y - md_h / 2), 30 + md_w, int(p_fin_y + md_h / 2))
    lay.add("MD", 126, int(fin_y - md_h / 2), 126 + md_w, int(fin_y + md_h / 2))
    lay.add("MD", 126, int(p_fin_y - md_h / 2), 126 + md_w, int(p_fin_y + md_h / 2))

    # Local interconnect: output strap ties both drains; sources go to rails.
    lay.add("M0", 28, 128, 44, 352)          # output
    lay.add("M0", 126, 328, 142, height - 8)  # P source -> VDD
    lay.add("M0", 126, 8, 142, 152)           # N source -> VSS
    lay.add("M0", 85, 326, 101, 350)          # gate landing

    if coag:
        # Contact over active gate: inside Lg, overlapping the P fin.
        lay.add("VIA0", 87, 334, 99, 346)
    else:
        # Contact beside the gate, on a widened landing pad.
        lay.add("M0", 60, 326, 84, 350)
        lay.add("VIA0", 66, 334, 78, 346)

    # M1 pin pads (min width 28) and rail connections.
    lay.add("M1", 26, 120, 54, 148)     # output pin
    lay.add("M1", 79, 318, 107, 346)    # input pin
    lay.add("M1", 122, height - 36, 150, height - 8)
    lay.add("M1", 122, 8, 150, 36)

    # Vias up to the M2 rails.
    lay.add("VIA1", 128, height - 28, 142, height - 14)
    lay.add("VIA1", 128, 14, 142, 28)

    # M2 power rails along the top and bottom of the cell.
    lay.add("M2", 0, 0, width, rail)
    lay.add("M2", 0, height - rail, width, height)
    return lay


def to_png(layout: Layout, path, scale: int = 6, legend_px: int = 150) -> None:
    """Rasterise the layout to PNG with a readable stacking order (Pillow)."""
    from pathlib import Path

    from PIL import Image, ImageColor, ImageDraw

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = layout.bbox
    pad = 16
    w = (x1 - x0) * scale + 2 * pad + legend_px
    h = (y1 - y0) * scale + 2 * pad
    img = Image.new("RGB", (w, h), "#f7f7f7")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    order = ("FIN", "MD", "PC", "M0", "VIA0", "M1", "VIA1", "M2")
    for layer in order:
        rgb = ImageColor.getrgb(LAYER_COLORS[layer])
        for s in layout.on(layer):
            left = pad + (s.x0 - x0) * scale
            top = pad + (y1 - s.y1) * scale
            right = pad + (s.x1 - x0) * scale
            bottom = pad + (y1 - s.y0) * scale
            draw.rectangle(
                [left, top, right, bottom], fill=rgb + (190,), outline=rgb + (255,)
            )
    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(img)
    for s in layout.on("BOUNDARY"):
        left = pad + (s.x0 - x0) * scale
        top = pad + (y1 - s.y1) * scale
        right = pad + (s.x1 - x0) * scale
        bottom = pad + (y1 - s.y0) * scale
        draw.rectangle([left, top, right, bottom], outline="#111111", width=2)
    for i, layer in enumerate(order):
        ly = pad + i * 22
        draw.rectangle(
            [w - legend_px + 8, ly, w - legend_px + 20, ly + 12],
            fill=LAYER_COLORS[layer],
        )
        draw.text((w - legend_px + 26, ly), layer, fill="#222222")
    bar_y = h - pad - 8
    draw.line([pad, bar_y, pad + 100 * scale, bar_y], fill="#111111", width=2)
    draw.text((pad, bar_y - 14), "100 nm", fill="#222222")
    img.convert("RGB").save(path)


def to_svg(layout: Layout, path, scale: float = 4.0) -> None:
    """Write a simple layered SVG preview of the layout."""
    from pathlib import Path

    path = Path(path)
    x0, y0, x1, y1 = layout.bbox
    pad = 10
    w = (x1 - x0) * scale + 2 * pad
    h = (y1 - y0) * scale + 2 * pad
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
        f'viewBox="0 0 {w:.0f} {h:.0f}">',
        '<rect width="100%" height="100%" fill="#fafafa"/>',
    ]
    for layer in LAYER_ORDER:
        color = LAYER_COLORS[layer]
        for s in layout.on(layer):
            rx = pad + (s.x0 - x0) * scale
            ry = pad + (y1 - s.y1) * scale
            rw = s.width * scale
            rh = s.height * scale
            if layer == "BOUNDARY":
                parts.append(
                    f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" '
                    'fill="none" stroke="#111" stroke-width="1.5" stroke-dasharray="4 3"/>'
                )
            else:
                parts.append(
                    f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" '
                    f'fill="{color}" fill-opacity="0.78" stroke="{color}" stroke-width="0.6"/>'
                )
    # Layer legend
    lx = pad
    for i, layer in enumerate(LAYER_ORDER):
        if layer == "BOUNDARY":
            continue
        ly = pad + (i + 1) * 16
        parts.append(
            f'<rect x="{lx}" y="{ly}" width="10" height="10" fill="{LAYER_COLORS[layer]}"/>'
        )
        parts.append(
            f'<text x="{lx + 14}" y="{ly + 9}" font-family="monospace" font-size="10">{layer}</text>'
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")

"""GRX930 pad-ring floorplan and package ball map.

TFBGA is a wire-bond package, so the die carries pads rather than flip-chip
bumps; the 196-ball array is the substrate ball map. This module places every
pad on two staggered perimeter rows, checks the pitch and corner clearance, and
assigns every net to a ball.

The ball assignment is a *functional* floorplan, not a routed substrate: data is
kept together, control and bring-up I/O stay together, and supplies occupy the
outer ring where decoupling is easiest. A real substrate would refine it for
wire length and cross-talk.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Any

from .package import PinBudget

PAD_SIZE_UM = 60.0
PAD_INSETS_UM = (80.0, 150.0)
CORNER_MARGIN_UM = 90.0
MIN_PITCH_UM = 150.0
BALL_PITCH_MM = 0.65
BALL_ROWS = 14
BALL_COLS = 14

COLORS: dict[str, str] = {
    "Memory data": "#3b6fb6",
    "Memory address": "#2a9d8f",
    "Memory byte enables": "#57a773",
    "Memory control": "#8ab17d",
    "Clock and reset": "#e9a13b",
    "Boot and config": "#d98e04",
    "JTAG": "#8e6bbf",
    "Debug UART": "#b07aa1",
    "GPIO and interrupts": "#9c6b4e",
    "Test and status": "#c9a227",
    "IO supply": "#e76f51",
    "Core supply": "#b23a48",
    "Analog": "#d81159",
    "Spare": "#c9c9c9",
}

SIDE_ORDER = ("south", "east", "north", "west")

EXPLICIT_NETS: dict[str, tuple[str, ...]] = {
    "Clock and reset": ("CLK_IN", "POR_N", "RESET_N", "PLL_BYPASS"),
    "Boot and config": ("BOOT0", "BOOT1", "TEST_MODE", "SCAN_EN"),
    "JTAG": ("TCK", "TMS", "TDI", "TDO", "TRST_N"),
    "Debug UART": ("UART_TX", "UART_RX", "UART_RTS", "UART_CTS"),
    "Test and status": ("FAULT_N", "HEARTBEAT"),
    "Memory control": ("CS_N", "WE_N", "OE_N", "MEM_CLK", "ADV_N", "WAIT_N"),
}


@dataclass(frozen=True)
class Pad:
    index: int
    net: str
    group: str
    kind: str
    side: str
    row: int
    x_um: float
    y_um: float


@dataclass(frozen=True)
class Ball:
    name: str
    row: int
    col: int
    net: str
    group: str
    kind: str


@dataclass(frozen=True)
class Floorplan:
    die_mm: float
    content_mm2: float
    pads: tuple[Pad, ...]
    balls: tuple[Ball, ...]
    side_counts: dict[str, int]
    min_pitch_um: float
    balls_used: int
    balls_spare: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "die_mm": round(self.die_mm, 4),
            "content_mm2": round(self.content_mm2, 4),
            "pads": len(self.pads),
            "side_counts": self.side_counts,
            "min_pitch_um": round(self.min_pitch_um, 1),
            "balls_used": self.balls_used,
            "balls_spare": self.balls_spare,
        }


def _group_nets(name: str, count: int) -> list[str]:
    if name in EXPLICIT_NETS:
        nets = list(EXPLICIT_NETS[name])
        if len(nets) != count:
            raise ValueError(f"{name}: {len(nets)} nets defined, {count} required")
        return nets
    if name == "Memory data":
        return [f"D{i}" for i in range(count)]
    if name == "Memory address":
        return [f"A{i}" for i in range(count)]
    if name == "Memory byte enables":
        return [f"BE{i}" for i in range(count)]
    if name == "GPIO and interrupts":
        return [f"GPIO{i}" for i in range(count)]
    slug = name.upper().replace(" ", "_").replace("/", "_")
    return [f"{slug}{i}" for i in range(count)]


def _interleave(signals: list[tuple[str, str, str]], supplies: list[tuple[str, str, str]]):
    """Insert supply pairs evenly between signal pads."""
    if not supplies:
        return list(signals)
    pairs = len(supplies) // 2
    out: list[tuple[str, str, str]] = []
    placed = 0
    for i, signal in enumerate(signals):
        out.append(signal)
        want = (i + 1) * pairs // len(signals)
        while placed < want:
            out.extend(supplies[2 * placed : 2 * placed + 2])
            placed += 1
    while placed < pairs:
        out.extend(supplies[2 * placed : 2 * placed + 2])
        placed += 1
    return out


def _side_geometry(side: str, along_um: float, inset_um: float, die_um: float):
    """Map an along-edge coordinate to (x, y) running clockwise."""
    margin = CORNER_MARGIN_UM + PAD_SIZE_UM / 2.0
    t = margin + along_um
    if side == "south":
        return t, inset_um
    if side == "east":
        return die_um - inset_um, t
    if side == "north":
        return die_um - t, die_um - inset_um
    return inset_um, die_um - t


def build_floorplan(
    cfg, budget: PinBudget, die_mm: float, content_mm2: float = 0.0
) -> Floorplan:
    spec = (cfg.pin_spec or {}).get("padring") or {}
    sides = spec.get("sides") or {}
    if not sides:
        raise ValueError("chip has no padring.sides plan")

    group_counts = {g.name: g.signals for g in budget.groups}
    cursor = {name: 0 for name in group_counts}
    assigned = {name: 0 for name in group_counts}

    die_um = die_mm * 1000.0
    margin = CORNER_MARGIN_UM + PAD_SIZE_UM / 2.0
    span = die_um - 2 * margin
    pads: list[Pad] = []
    side_counts: dict[str, int] = {}
    min_pitch = float("inf")
    index = 0

    supply_numbers = {"io": 0, "core": 0, "analog": 0}
    supply_prefix = {
        "io": ("VDDIO", "VSSIO", "IO supply"),
        "core": ("VDDCORE", "VSSCORE", "Core supply"),
        "analog": ("VDDA", "VSSA", "Analog"),
    }

    for side in SIDE_ORDER:
        plan = sides.get(side)
        if plan is None:
            raise ValueError(f"padring.sides is missing {side!r}")
        seeds: list[tuple[str, str, str]] = []
        for group_name, count in plan.get("signals", []):
            if group_name not in group_counts:
                raise ValueError(f"unknown pin group {group_name!r} on {side}")
            available = group_counts[group_name] - cursor[group_name]
            if count > available:
                raise ValueError(
                    f"{group_name}: {count} pads assigned to {side}, only "
                    f"{available} left"
                )
            nets = _group_nets(group_name, group_counts[group_name])[
                cursor[group_name] : cursor[group_name] + count
            ]
            seeds.extend((net, group_name, "signal") for net in nets)
            cursor[group_name] += count
            assigned[group_name] += count

        supplies: list[tuple[str, str, str]] = []
        for kind in ("io", "core", "analog"):
            pairs = int(plan.get("supply_pairs", {}).get(kind, 0))
            pos, neg, label = supply_prefix[kind]
            for _ in range(pairs):
                n = supply_numbers[kind]
                supplies.append((f"{pos}_{n}", label, "supply"))
                supplies.append((f"{neg}_{n}", label, "supply"))
                supply_numbers[kind] += 1

        ordered = _interleave(seeds, supplies)
        n = len(ordered)
        n0 = (n + 1) // 2
        n1 = n // 2
        rows = max(n0, n1)
        if rows <= 1:
            pitch = span
        elif n1 == n0:
            # The staggered row's last pad sits half a pitch further out.
            pitch = span / (rows - 0.5)
        else:
            pitch = span / (rows - 1)
        min_pitch = min(min_pitch, pitch)
        if pitch < MIN_PITCH_UM:
            raise ValueError(
                f"{side}: {n} pads need {pitch:.1f} um pitch, below "
                f"{MIN_PITCH_UM:.0f} um"
            )

        side_counts[side] = n
        for i, (net, group, kind) in enumerate(ordered):
            row = i % 2
            k = i // 2
            along = k * pitch + (pitch / 2 if row else 0.0)
            x, y = _side_geometry(side, along, PAD_INSETS_UM[row], die_um)
            index += 1
            pads.append(
                Pad(
                    index=index,
                    net=net,
                    group=group,
                    kind=kind,
                    side=side,
                    row=row,
                    x_um=round(x, 2),
                    y_um=round(y, 2),
                )
            )

    for name, total in group_counts.items():
        if assigned[name] != total:
            raise ValueError(
                f"{name}: {assigned[name]} pads placed, budget is {total}"
            )
    if len(pads) != budget.total_pads:
        raise ValueError(f"{len(pads)} pads placed, budget is {budget.total_pads}")
    if index != len(pads):
        raise ValueError("pad index mismatch")
    if min_pitch < MIN_PITCH_UM:
        raise ValueError(f"minimum pitch {min_pitch:.1f} um is too small")

    balls, used, spare = _ball_map(pads)
    return Floorplan(
        die_mm=die_mm,
        content_mm2=content_mm2,
        pads=tuple(pads),
        balls=balls,
        side_counts=side_counts,
        min_pitch_um=min_pitch,
        balls_used=used,
        balls_spare=spare,
    )


# ---------------------------------------------------------------------------
# Ball map
# ---------------------------------------------------------------------------
def _ball_name(row: int, col: int) -> str:
    return f"{chr(ord('A') + row)}{col + 1}"


def _supply_group(net: str) -> str:
    if net.startswith(("VDDA", "VSSA")):
        return "Analog"
    if net.startswith(("VDDCORE", "VSSCORE")):
        return "Core supply"
    return "IO supply"


def _ball_map(pads: tuple[Pad, ...]) -> tuple[tuple[Ball, ...], int, int]:
    """Assign nets to a 14 x 14 TFBGA array.

    Outer ring: 52 supply balls. Inner 12 x 12: data in the lower half,
    address/control and bring-up I/O in the upper half, remaining supplies
    inside, and 18 spare balls.
    """
    if BALL_ROWS * BALL_COLS != 196:
        raise ValueError("TFBGA-196 map must be 14 x 14")

    supply_nets = [p.net for p in pads if p.kind == "supply"]
    signal_pads = [p for p in pads if p.kind == "signal"]
    data = [p for p in signal_pads if p.group == "Memory data"]
    control = [p for p in signal_pads if p.group in (
        "Memory address",
        "Memory byte enables",
        "Memory control",
    )]
    fixed = [p for p in signal_pads if p.group not in (
        "Memory data",
        "Memory address",
        "Memory byte enables",
        "Memory control",
    )]
    if len(supply_nets) != 60:
        raise ValueError(f"expected 60 supply pads, got {len(supply_nets)}")
    if len(data) + len(control) + len(fixed) != len(signal_pads):
        raise ValueError("signal partition does not add up")

    outer: list[tuple[int, int]] = []
    for c in range(BALL_COLS):
        outer.append((0, c))
    for r in range(1, BALL_ROWS):
        outer.append((r, BALL_COLS - 1))
    for c in range(BALL_COLS - 2, -1, -1):
        outer.append((BALL_ROWS - 1, c))
    for r in range(BALL_ROWS - 2, 0, -1):
        outer.append((r, 0))
    if len(outer) != 52:
        raise ValueError(f"perimeter is {len(outer)} balls, expected 52")

    inner = [
        (r, c)
        for r in range(1, BALL_ROWS - 1)
        for c in range(1, BALL_COLS - 1)
    ]
    if len(inner) != 144:
        raise ValueError(f"interior is {len(inner)} balls, expected 144")

    placed: dict[tuple[int, int], tuple[str, str, str]] = {}
    for (r, c), net in zip(outer, supply_nets, strict=False):
        placed[(r, c)] = (net, _supply_group(net), "supply")

    remaining_supplies = supply_nets[52:]
    bottom = [pos for pos in inner if pos[0] <= 6]
    top = [pos for pos in inner if pos[0] > 6]

    bottom_nets: list[tuple[str, str, str]] = [
        (p.net, p.group, "signal") for p in data
    ] + [("SPARE", "Spare", "spare")] * 8
    top_nets: list[tuple[str, str, str]] = [
        (p.net, p.group, "signal") for p in control
    ] + [(p.net, p.group, "signal") for p in fixed]
    top_nets += [(net, _supply_group(net), "supply") for net in remaining_supplies]
    top_nets += [("SPARE", "Spare", "spare")] * 10

    if len(bottom_nets) != 72 or len(top_nets) != 72:
        raise ValueError(
            f"ball halves must be 72 each, got {len(bottom_nets)} and {len(top_nets)}"
        )
    for pos, entry in zip(bottom, bottom_nets, strict=True):
        placed[pos] = entry
    for pos, entry in zip(top, top_nets, strict=True):
        placed[pos] = entry

    balls: list[Ball] = []
    for r in range(BALL_ROWS):
        for c in range(BALL_COLS):
            net, group, kind = placed[(r, c)]
            balls.append(
                Ball(
                    name=_ball_name(r, c),
                    row=r,
                    col=c,
                    net=net,
                    group=group,
                    kind=kind,
                )
            )
    used = sum(1 for b in balls if b.kind != "spare")
    return tuple(balls), used, len(balls) - used


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------
def _color(group: str) -> str:
    return COLORS.get(group, "#888888")


def write_csvs(plan: Floorplan, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pad_path = directory / "grx930_padring.csv"
    with pad_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["pad", "net", "group", "kind", "side", "row", "x_um", "y_um"])
        for p in plan.pads:
            writer.writerow(
                [p.index, p.net, p.group, p.kind, p.side, p.row, p.x_um, p.y_um]
            )
    ball_path = directory / "grx930_ballmap.csv"
    with ball_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ball", "row", "col", "net", "group", "kind", "x_mm", "y_mm"])
        for b in plan.balls:
            x = (b.col - (BALL_COLS - 1) / 2) * BALL_PITCH_MM
            y = (b.row - (BALL_ROWS - 1) / 2) * BALL_PITCH_MM
            writer.writerow(
                [b.name, chr(ord("A") + b.row), b.col + 1, b.net, b.group, b.kind,
                 round(x, 3), round(y, 3)]
            )
    return pad_path, ball_path


def _layout(plan: Floorplan):
    """Shared geometry for the SVG and PNG renderers, in figure pixels."""
    width, height = 1500, 980
    die_px = 684
    scale = die_px / plan.die_mm
    ox, oy = 90, 115
    ball_spacing = 32
    bx, by = 905, 190
    return width, height, scale, ox, oy, ball_spacing, bx, by


def _die_xy(plan, x_um, y_um):
    width, height, scale, ox, oy, *_ = _layout(plan)
    return ox + x_um / 1000.0 * scale, oy + (plan.die_mm - y_um / 1000.0) * scale


def _ball_xy(plan, ball):
    width, height, scale, ox, oy, spacing, bx, by = _layout(plan)
    return bx + ball.col * spacing, by + (BALL_ROWS - 1 - ball.row) * spacing


def to_svg(plan: Floorplan, path: Path) -> None:
    width, height, scale, ox, oy, spacing, bx, by = _layout(plan)
    die_px = plan.die_mm * scale
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#f5f5f2"/>',
        '<text x="90" y="45" font-family="sans-serif" font-size="24" '
        'font-weight="bold" fill="#222">GRX930 pad ring and TFBGA-196 ball map</text>',
        f'<text x="90" y="68" font-family="sans-serif" font-size="13" fill="#555">'
        f'{len(plan.pads)} pads, {plan.die_mm:.2f} mm die, '
        f'{plan.min_pitch_um:.1f} um minimum pitch</text>',
        f'<rect x="{ox}" y="{oy}" width="{die_px}" height="{die_px}" '
        'fill="#ffffff" stroke="#222" stroke-width="1.5"/>',
        f'<rect x="{ox + 0.16 * scale}" y="{oy + 0.16 * scale}" '
        f'width="{die_px - 0.32 * scale}" height="{die_px - 0.32 * scale}" '
        'fill="none" stroke="#999" stroke-dasharray="6 4"/>',
        f'<text x="{ox + 0.22 * scale}" y="{oy + 0.22 * scale + 14}" '
        'font-family="sans-serif" font-size="11" fill="#777">core area</text>',
    ]
    if plan.content_mm2 > 0:
        side_px = sqrt(plan.content_mm2) * scale
        cx = ox + die_px / 2
        cy = oy + die_px / 2
        parts.append(
            f'<rect x="{cx - side_px / 2:.1f}" y="{cy - side_px / 2:.1f}" '
            f'width="{side_px:.1f}" height="{side_px:.1f}" fill="#dbe7f5" '
            'stroke="#3b6fb6" stroke-width="1.2" stroke-dasharray="4 3"/>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{cy + side_px / 2 + 14:.1f}" '
            'text-anchor="middle" font-family="sans-serif" font-size="10" '
            f'fill="#3b6fb6">{plan.content_mm2:.2f} mm2 content</text>'
        )
    for p in plan.pads:
        x, y = _die_xy(plan, p.x_um, p.y_um)
        size = PAD_SIZE_UM / 1000.0 * scale
        parts.append(
            f'<rect x="{x - size / 2:.1f}" y="{y - size / 2:.1f}" '
            f'width="{size:.1f}" height="{size:.1f}" fill="{_color(p.group)}" '
            f'stroke="#333" stroke-width="0.4"/>'
        )
    side_labels = {
        "south": (ox + die_px / 2, oy + die_px + 26, "middle"),
        "east": (ox + die_px + 12, oy + die_px / 2, "start"),
        "north": (ox + die_px / 2, oy - 12, "middle"),
        "west": (ox - 12, oy + die_px / 2, "end"),
    }
    for side, (x, y, anchor) in side_labels.items():
        parts.append(
            f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="{anchor}" '
            f'font-family="sans-serif" font-size="12" fill="#444">'
            f'{side.upper()} ({plan.side_counts[side]})</text>'
        )

    parts.append(
        f'<text x="{bx - 40}" y="{by - 45}" font-family="sans-serif" font-size="16" '
        'font-weight="bold" fill="#222">Package ball map (top view)</text>'
    )
    for c in range(BALL_COLS):
        parts.append(
            f'<text x="{bx + c * spacing}" y="{by + 13 * spacing + 20}" '
            'text-anchor="middle" font-family="sans-serif" font-size="9" '
            f'fill="#666">{c + 1}</text>'
        )
    for r in range(BALL_ROWS):
        parts.append(
            f'<text x="{bx - 22}" y="{by + (13 - r) * spacing + 3}" '
            'text-anchor="end" font-family="sans-serif" font-size="9" '
            f'fill="#666">{chr(ord("A") + r)}</text>'
        )
    for b in plan.balls:
        x, y = _ball_xy(plan, b)
        color = "#ffffff" if b.kind == "spare" else _color(b.group)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{color}" '
            'stroke="#333" stroke-width="0.6"/>'
        )

    legend_groups = list(COLORS)
    lx, ly = 90, 900
    for i, group in enumerate(legend_groups):
        col = i % 4
        row = i // 4
        x = lx + col * 350
        y = ly + row * 22
        parts.append(
            f'<rect x="{x}" y="{y - 10}" width="12" height="12" fill="{COLORS[group]}" '
            'stroke="#333" stroke-width="0.4"/>'
        )
        parts.append(
            f'<text x="{x + 18}" y="{y}" font-family="sans-serif" font-size="11" '
            f'fill="#333">{group}</text>'
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def to_png(plan: Floorplan, path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height, scale, ox, oy, spacing, bx, by = _layout(plan)
    die_px = plan.die_mm * scale
    img = Image.new("RGB", (width, height), "#f5f5f2")
    draw = ImageDraw.Draw(img)

    def font(size: int):
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    draw.text((90, 30), "GRX930 pad ring and TFBGA-196 ball map",
              fill="#222", font=font(24))
    draw.text((90, 60),
              f"{len(plan.pads)} pads, {plan.die_mm:.2f} mm die, "
              f"{plan.min_pitch_um:.1f} um minimum pitch",
              fill="#555", font=font(13))
    draw.rectangle([ox, oy, ox + die_px, oy + die_px], fill="white",
                   outline="#222", width=2)
    inset = 0.16 * scale
    draw.rectangle([ox + inset, oy + inset, ox + die_px - inset, oy + die_px - inset],
                   outline="#999")
    draw.text((ox + 0.22 * scale, oy + 0.22 * scale + 4), "core area",
              fill="#777", font=font(11))
    if plan.content_mm2 > 0:
        side_px = sqrt(plan.content_mm2) * scale
        cx = ox + die_px / 2
        cy = oy + die_px / 2
        draw.rectangle(
            [cx - side_px / 2, cy - side_px / 2, cx + side_px / 2, cy + side_px / 2],
            fill="#dbe7f5", outline="#3b6fb6", width=2,
        )
        draw.text((cx, cy + side_px / 2 + 6), f"{plan.content_mm2:.2f} mm2 content",
                  fill="#3b6fb6", font=font(10), anchor="ma")

    size = PAD_SIZE_UM / 1000.0 * scale
    for p in plan.pads:
        x, y = _die_xy(plan, p.x_um, p.y_um)
        draw.rectangle([x - size / 2, y - size / 2, x + size / 2, y + size / 2],
                       fill=_color(p.group), outline="#333", width=1)

    labels = {
        "south": (ox + die_px / 2, oy + die_px + 14, "mb"),
        "north": (ox + die_px / 2, oy - 26, "mb"),
        "east": (ox + die_px + 10, oy + die_px / 2 - 8, "lm"),
        "west": (ox - 10, oy + die_px / 2 - 8, "rm"),
    }
    for side, (x, y, anchor) in labels.items():
        draw.text((x, y), f"{side.upper()} ({plan.side_counts[side]})",
                  fill="#444", font=font(12), anchor=anchor)

    draw.text((bx - 40, by - 60), "Package ball map (top view)",
              fill="#222", font=font(16))
    for c in range(BALL_COLS):
        draw.text((bx + c * spacing, by + 13 * spacing + 14), str(c + 1),
                  fill="#666", font=font(9), anchor="mm")
    for r in range(BALL_ROWS):
        draw.text((bx - 14, by + (13 - r) * spacing), chr(ord("A") + r),
                  fill="#666", font=font(9), anchor="rm")
    for b in plan.balls:
        x, y = _ball_xy(plan, b)
        color = "#ffffff" if b.kind == "spare" else _color(b.group)
        draw.ellipse([x - 11, y - 11, x + 11, y + 11], fill=color,
                     outline="#333", width=1)

    lx, ly = 90, 900
    for i, (group, color) in enumerate(COLORS.items()):
        col = i % 4
        row = i // 4
        x = lx + col * 350
        y = ly + row * 22
        draw.rectangle([x, y - 10, x + 12, y + 2], fill=color, outline="#333")
        draw.text((x + 18, y - 8), group, fill="#333", font=font(11))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def write_artifacts(plan: Floorplan, directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pad_csv, ball_csv = write_csvs(plan, directory)
    svg = directory / "grx930_package.svg"
    png = directory / "grx930_package.png"
    to_svg(plan, svg)
    to_png(plan, png)
    return {"padring_csv": pad_csv, "ballmap_csv": ball_csv, "svg": svg, "png": png}

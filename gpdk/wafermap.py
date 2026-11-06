"""Deterministic CSV and SVG output for a radial wafer map."""

from __future__ import annotations

import csv
import html
import io
import math

from .dieyield import WaferMapEstimate

_CSV_FIELDS = [
    "die_index",
    "x_mm",
    "y_mm",
    "radius_mm",
    "normalized_radius",
    "defect_density_per_cm2",
    "expected_die_yield",
]


def to_csv(estimate: WaferMapEstimate) -> bytes:
    """Return one row per die with position, density and expected yield."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=_CSV_FIELDS, lineterminator="\n"
    )
    writer.writeheader()
    for index, (position, density, die_yield) in enumerate(
        zip(
            estimate.die_positions,
            estimate.die_defect_densities,
            estimate.die_yields,
        )
    ):
        x, y = position
        radius = math.hypot(x, y)
        writer.writerow(
            {
                "die_index": index,
                "x_mm": f"{x:.3f}",
                "y_mm": f"{y:.3f}",
                "radius_mm": f"{radius:.3f}",
                "normalized_radius": (
                    f"{radius / estimate.usable_radius_mm:.3f}"
                ),
                "defect_density_per_cm2": f"{density:.6f}",
                "expected_die_yield": f"{die_yield:.6f}",
            }
        )
    return buffer.getvalue().encode("utf-8")


def _colour(fraction: float) -> str:
    stops = (
        (0.0, (214.0, 51.0, 46.0)),
        (0.5, (242.0, 184.0, 51.0)),
        (1.0, (33.0, 128.0, 61.0)),
    )
    fraction = min(1.0, max(0.0, fraction))
    for (left_t, left_rgb), (right_t, right_rgb) in zip(stops, stops[1:]):
        if fraction <= right_t:
            span = right_t - left_t
            blend = 0.0 if span == 0.0 else (fraction - left_t) / span
            rgb = tuple(
                left + (right - left) * blend
                for left, right in zip(left_rgb, right_rgb)
            )
            return "#" + "".join(
                f"{int(round(channel)):02x}" for channel in rgb
            )
    return "#21803d"


def to_svg(
    estimate: WaferMapEstimate,
    *,
    title: str = "wafer map",
) -> bytes:
    """Return a deterministic SVG heat map of expected die yield."""
    width, height = 900, 820
    center_x, center_y = 450.0, 360.0
    plot_radius = 320.0
    scale = plot_radius / estimate.usable_radius_mm
    outer_radius = estimate.wafer_diameter_mm / 2.0 * scale
    die_side = max(math.sqrt(estimate.die_area_mm2) * scale - 0.35, 0.7)
    lowest = min(estimate.die_yields)
    highest = max(estimate.die_yields)
    span = highest - lowest
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<defs><linearGradient id="yieldScale" x1="0" y1="0" x2="1" y2="0">',
        '<stop offset="0" stop-color="#d6332e"/>',
        '<stop offset="0.5" stop-color="#f2b833"/>',
        '<stop offset="1" stop-color="#21803d"/>',
        "</linearGradient></defs>",
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        (
            f'<text x="30" y="38" font-family="sans-serif" font-size="22" '
            f'fill="#111111">{html.escape(title)}</text>'
        ),
        (
            f'<text x="30" y="60" font-family="sans-serif" font-size="13" '
            'fill="#444444">'
            f"mean {estimate.die_yield_mean * 100:.3f}% · "
            f"center {estimate.center_die_yield * 100:.3f}% · "
            f"edge {estimate.edge_die_yield * 100:.3f}% · "
            f"edge/center {estimate.edge_to_center_yield_ratio:.4f}"
            "</text>"
        ),
        (
            f'<circle cx="{center_x}" cy="{center_y}" '
            f'r="{outer_radius:.1f}" fill="#f4f4f4" '
            'stroke="#888888" stroke-width="1"/>'
        ),
        (
            f'<circle cx="{center_x}" cy="{center_y}" '
            f'r="{plot_radius:.1f}" fill="none" stroke="#777777" '
            'stroke-width="1" stroke-dasharray="4 3"/>'
        ),
    ]
    for zone in estimate.zones:
        parts.append(
            f'<circle cx="{center_x}" cy="{center_y}" '
            f'r="{zone.r_max_mm * scale:.1f}" fill="none" '
            'stroke="#bbbbbb" stroke-width="0.8" stroke-dasharray="2 4"/>'
        )
    for (x, y), die_yield in zip(estimate.die_positions, estimate.die_yields):
        fraction = 0.5 if span == 0.0 else (die_yield - lowest) / span
        pixel_x = center_x + x * scale
        pixel_y = center_y - y * scale
        parts.append(
            f'<rect class="die" x="{pixel_x - die_side / 2.0:.2f}" '
            f'y="{pixel_y - die_side / 2.0:.2f}" '
            f'width="{die_side:.2f}" height="{die_side:.2f}" '
            f'fill="{_colour(fraction)}"/>'
        )
    parts.extend(
        [
            (
                '<text x="30" y="704" font-family="sans-serif" '
                'font-size="13" fill="#333333">expected die yield</text>'
            ),
            (
                '<rect x="30" y="714" width="300" height="14" '
                'fill="url(#yieldScale)" stroke="#888888"/>'
            ),
            (
                f'<text x="30" y="746" font-family="sans-serif" '
                f'font-size="12" fill="#333333">{lowest * 100:.3f}%</text>'
            ),
            (
                '<text x="330" y="746" text-anchor="end" '
                'font-family="sans-serif" font-size="12" fill="#333333">'
                f"{highest * 100:.3f}%</text>"
            ),
            (
                '<text x="30" y="778" font-family="sans-serif" '
                'font-size="12" fill="#555555">F1 planning assumption; '
                "not measured wafer data.</text>"
            ),
            (
                '<text x="450" y="778" font-family="sans-serif" '
                'font-size="12" fill="#555555">'
                f"wafer Ø {estimate.wafer_diameter_mm:.0f} mm · "
                f"{estimate.gross_dies_per_wafer} die · "
                f"{estimate.samples} samples</text>"
            ),
            "</svg>",
        ]
    )
    return "\n".join(parts).encode("utf-8")

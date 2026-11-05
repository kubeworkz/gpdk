"""Minimal GDSII writer and reader for the demo layouts.

Only the subset needed for flat cell geometry is implemented: one structure of
BOUNDARY elements, 1 nm database unit. The reader exists so tests can prove the
file is structurally valid and round-trips coordinates.
"""

from __future__ import annotations

import struct
from pathlib import Path

from .layout import GDS_LAYERS, LAYER_ORDER, Layout

DB_UNIT_M = 1e-9
USER_UNIT_M = 1e-6


def _rec(rectype: int, datatype: int, data: bytes = b"") -> bytes:
    length = 4 + len(data)
    if length > 0xFFFF:
        raise ValueError("GDS record exceeds 65535 bytes")
    return struct.pack(">HBB", length, rectype, datatype) + data


def _i2(value: int) -> bytes:
    return struct.pack(">h", int(value))


def _i4(value: int) -> bytes:
    return struct.pack(">i", int(value))


def _ascii(text: str) -> bytes:
    raw = text.encode("ascii")
    if len(raw) % 2:
        raw += b"\x00"
    return raw


def _real(value: float) -> bytes:
    """GDSII 8-byte real: sign, base-16 exponent (bias 64), 56-bit mantissa."""
    if value == 0:
        return b"\x00" * 8
    sign = 0x80 if value < 0 else 0
    v = abs(float(value))
    exponent = 64
    while v >= 1.0:
        v /= 16.0
        exponent += 1
    while v < 1.0 / 16.0:
        v *= 16.0
        exponent -= 1
    if not 0 <= exponent <= 127:
        raise ValueError(f"value {value} outside the GDS real range")
    mantissa = int(round(v * (1 << 56)))
    if mantissa >= 1 << 56:
        mantissa >>= 4
        exponent += 1
    return bytes([sign | exponent]) + mantissa.to_bytes(7, "big")


def write_gds(layout: Layout, path: str | Path, libname: str = "GRX12F") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = [2026, 11, 4, 12, 0, 0] * 2
    out = bytearray()
    out += _rec(0x00, 0x02, _i2(600))                       # HEADER
    out += _rec(0x01, 0x02, struct.pack(">12h", *timestamp))  # BGNLIB
    out += _rec(0x02, 0x06, _ascii(libname))                # LIBNAME
    out += _rec(0x03, 0x05, _real(DB_UNIT_M / USER_UNIT_M) + _real(DB_UNIT_M))
    out += _rec(0x05, 0x02, struct.pack(">12h", *timestamp))  # BGNSTR
    out += _rec(0x06, 0x06, _ascii(layout.name))            # STRNAME

    order = {name: i for i, name in enumerate(LAYER_ORDER)}
    for shape in sorted(layout.shapes, key=lambda s: order[s.layer]):
        out += _rec(0x08, 0x00)                             # BOUNDARY
        out += _rec(0x0D, 0x02, _i2(GDS_LAYERS[shape.layer]))
        out += _rec(0x0E, 0x02, _i2(0))                     # DATATYPE
        points = [
            (shape.x0, shape.y0),
            (shape.x1, shape.y0),
            (shape.x1, shape.y1),
            (shape.x0, shape.y1),
            (shape.x0, shape.y0),
        ]
        payload = b"".join(struct.pack(">ii", x, y) for x, y in points)
        out += _rec(0x10, 0x03, payload)                    # XY
        out += _rec(0x11, 0x00)                             # ENDEL
    out += _rec(0x07, 0x00)                                 # ENDSTR
    out += _rec(0x04, 0x00)                                 # ENDLIB
    path.write_bytes(bytes(out))
    return path


# ---------------------------------------------------------------------------
# Reader (verification only)
# ---------------------------------------------------------------------------
def read_gds(path: str | Path) -> dict[str, object]:
    data = Path(path).read_bytes()
    pos = 0
    records = 0
    layers: dict[int, int] = {}
    bbox = [10**9, 10**9, -10**9, -10**9]
    current_layer: int | None = None
    while pos + 4 <= len(data):
        length, rectype, _datatype = struct.unpack(">HBB", data[pos : pos + 4])
        if length < 4 or pos + length > len(data):
            raise ValueError(f"corrupt record at byte {pos}")
        payload = data[pos + 4 : pos + length]
        records += 1
        if rectype == 0x0D:  # LAYER
            current_layer = struct.unpack(">h", payload)[0]
        elif rectype == 0x10:  # XY
            count = len(payload) // 4
            pts = struct.unpack(f">{count}i", payload)
            x = pts[0::2]
            y = pts[1::2]
            if current_layer is not None:
                layers[current_layer] = layers.get(current_layer, 0) + 1
            bbox[0] = min(bbox[0], *x)
            bbox[1] = min(bbox[1], *y)
            bbox[2] = max(bbox[2], *x)
            bbox[3] = max(bbox[3], *y)
        pos += length
    if pos != len(data):
        raise ValueError("trailing bytes in GDS file")
    return {
        "records": records,
        "boundaries": sum(layers.values()),
        "layers": layers,
        "bbox_nm": tuple(bbox),
        "bytes": len(data),
    }

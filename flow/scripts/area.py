#!/usr/bin/env python3
"""Sum mapped standard-cell area for a Yosys netlist.

The netlist is flat and uses one instance per line in the form
``  CELL inst (``.  Area comes from the Liberty file used for mapping, so the
result is the library's own cell area, not a placed/ routed area.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path


def read_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", errors="replace") as fh:
            return fh.read()
    return path.read_text(errors="replace")


def liberty_areas(path: Path) -> dict[str, float]:
    text = read_text(path)
    areas: dict[str, float] = {}
    # Liberty allows both "cell (name)" and "cell(name)".
    matches = list(re.finditer(r"(?m)^\s*cell\s*\(\s*([^)]+?)\s*\)\s*\{", text))
    for i, match in enumerate(matches):
        name = match.group(1).strip().strip('"')
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[match.end():end]
        area_match = re.search(r"\barea\s*:\s*([0-9.eE+-]+)\s*;", block)
        if area_match:
            areas[name] = float(area_match.group(1))
    return areas


def netlist_cells(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    instance = re.compile(r"^\s{2}([A-Za-z_][A-Za-z0-9_$]*)\s+\S+\s+\($")
    for line in read_text(path).splitlines():
        match = instance.match(line)
        if match:
            cell = match.group(1)
            counts[cell] = counts.get(cell, 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("netlist", type=Path)
    parser.add_argument("liberty", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    areas = liberty_areas(args.liberty)
    counts = netlist_cells(args.netlist)
    unknown = sorted(set(counts) - set(areas))
    if unknown:
        raise SystemExit(f"cells missing from Liberty: {unknown[:10]}")

    total_area = sum(areas[cell] * count for cell, count in counts.items())
    total_cells = sum(counts.values())
    sequential = sum(
        count for cell, count in counts.items()
        if re.search(r"(DFF|SDFF|dff|sdff|dffr|dffs)", cell)
    )
    result = {
        "netlist": str(args.netlist),
        "liberty": str(args.liberty),
        "cells": total_cells,
        "sequential": sequential,
        "cell_area_um2": round(total_area, 3),
        "cell_types": len(counts),
        "top_cells": sorted(
            ({"cell": c, "count": n, "area_um2": round(areas[c] * n, 3)}
             for c, n in counts.items()),
            key=lambda row: row["area_um2"], reverse=True,
        )[:10],
    }
    print(json.dumps(result, indent=2))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

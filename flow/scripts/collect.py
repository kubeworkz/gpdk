#!/usr/bin/env python3
"""Collect the measured metrics from one OpenROAD run."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def search(text: str, pattern: str, cast=float, default=None):
    matches = re.findall(pattern, text)
    if not matches:
        return default
    return cast(matches[-1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--drc", type=Path, required=True)
    parser.add_argument("--synth", type=Path, required=True,
                        help="area.py JSON for the mapped netlist")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--time-scale", type=float, default=1.0,
                        help="multiply reported WNS/TNS by this to get ns (0.001 for ps logs)")
    args = parser.parse_args()

    log = args.log.read_text(errors="replace")
    synth = json.loads(args.synth.read_text())
    drc_lines = 0
    if args.drc.exists():
        drc_lines = sum(1 for line in args.drc.read_text(errors="replace").splitlines() if line.strip())

    wns = search(log, r"wns max\s+(-?[0-9.]+)")
    tns = search(log, r"tns max\s+(-?[0-9.]+)")
    row = {
        "label": args.label,
        "cells": synth["cells"],
        "sequential": synth["sequential"],
        "cell_area_um2": synth["cell_area_um2"],
        "design_area_um2": search(log, r"Design area\s+([0-9.]+)\s+um\^2"),
        "utilization": search(log, r"Design area\s+[0-9.]+\s+um\^2\s+([0-9]+)%"),
        "wns_ns": None if wns is None else wns * args.time_scale,
        "tns_ns": None if tns is None else tns * args.time_scale,
        "wirelength_um": search(log, r"Total wire length\s*=\s*([0-9.]+)\s*um"),
        "drc": drc_lines,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(row, indent=2) + "\n")
    print(json.dumps(row, indent=2))


if __name__ == "__main__":
    main()

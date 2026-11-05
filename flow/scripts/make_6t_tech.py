#!/usr/bin/env python3
"""Derive a 6T-compatible tech LEF from the ASAP7 7.5T tech LEF.

The published asap7sc6t LEF has no technology section.  Its pin geometry uses
0.018 um V1 cuts and 0.018 um M1/M2 bars, so the 7.5T VIA12 landing pad
(0.018 x 0.022 um on M1, 0.028 x 0.018 um on M2) cannot fit on many 6T input
pins.  This script changes only VIA12 to the 6T geometry observed in the
library.  All layer rules, tracks and upper-layer vias are unchanged.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

VIA12 = """VIA VIA12 Default
  LAYER M1 ;
 RECT -0.009 -0.009 0.009 0.009 ;
  LAYER M2 ;
 RECT -0.009 -0.009 0.009 0.009 ;
  LAYER V1 ;
 RECT -0.009 -0.009 0.009 0.009 ;
END VIA12"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    text = args.source.read_text()
    pattern = re.compile(r"(?ms)^VIA VIA12 Default\n.*?^END VIA12\s*$")
    if len(pattern.findall(text)) != 1:
        raise SystemExit("expected exactly one VIA12 block")
    text = pattern.sub(VIA12, text, count=1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()

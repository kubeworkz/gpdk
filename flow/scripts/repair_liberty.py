#!/usr/bin/env python3
"""Repair known formatting defects in the ASAP7 Liberty files.

Two defects are present in the published collateral:

* the 7.5T INVBUF library omits the semicolon after every ``area`` statement;
* the 6T SIMPLE library closes the ``library`` group at line 53405 and then
  continues with more ``cell`` groups.

Both are delimiters only; no numeric value or cell is changed.  The repaired
file is written to the output path.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def remove_premature_library_close(text: str) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    depth = 0
    removed = 0
    for i, line in enumerate(lines):
        if line.strip() == "}" and depth == 1:
            rest = "".join(lines[i + 1:])
            if re.search(r"(?m)^  cell\s*\(", rest):
                removed += 1
                continue
        out.append(line)
        depth += line.count("{") - line.count("}")
    return "".join(out), removed


def fix_area_semicolons(text: str) -> tuple[str, int]:
    pattern = re.compile(r"(?m)^(\s*area\s*:\s*[0-9.eE+-]+)\s*$")
    fixed = pattern.subn(r"\1;", text)
    return fixed[0], fixed[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    text = args.input.read_text(errors="replace")
    text, closes = remove_premature_library_close(text)
    text, areas = fix_area_semicolons(text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    print(f"{args.input} -> {args.output}: "
          f"{closes} premature close(s), {areas} area semicolon(s)")


if __name__ == "__main__":
    main()

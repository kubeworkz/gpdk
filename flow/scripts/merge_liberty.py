#!/usr/bin/env python3
"""Merge split Liberty libraries into one library for Yosys/ABC.

ASAP7 ships its standard cells as per-group Liberty files (AO, INVBUF, OA,
SIMPLE, SEQ).  ABC reads one library per file, and Yosys's ``abc -liberty``
needs a target library containing every cell.  This script keeps the header
(units, templates, operating conditions) of one file and appends the cell
blocks from every input into a single ``library`` block.

It also repairs the known ASAP7 7.5T INVBUF formatting issue: every ``area``
statement in that file is missing its terminating semicolon.  The value is
unchanged; only the delimiter is added so strict Liberty readers see it.

Example:
    python flow/scripts/merge_liberty.py \
        --output flow/build/asap7/lib/75t/asap7_75t_rvt_tt.lib \
        flow/build/asap7/lib/75t/asap7sc7p5t_SIMPLE_RVT_TT.lib \
        flow/build/asap7/lib/75t/asap7sc7p5t_AO_RVT_TT.lib \
        flow/build/asap7/lib/75t/asap7sc7p5t_OA_RVT_TT.lib \
        flow/build/asap7/lib/75t/asap7sc7p5t_INVBUF_RVT_TT.lib
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def matching_brace(text: str, open_index: int) -> int:
    """Return the index just past the brace matching text[open_index]."""
    depth = 0
    i = open_index
    while i < len(text):
        char = text[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced braces")


def strip_group(text: str, keyword: str) -> str:
    """Remove every ``keyword (...) { ... }`` group from text."""
    pattern = re.compile(r"(?m)^\s*" + keyword + r"\s*\([^)]*\)\s*\{")
    out: list[str] = []
    pos = 0
    while True:
        match = pattern.search(text, pos)
        if not match:
            out.append(text[pos:])
            return "".join(out)
        out.append(text[pos:match.start()])
        pos = matching_brace(text, match.end() - 1)


def library_body(text: str) -> str:
    """Return the body of the first top-level library group."""
    match = re.search(r"(?m)^library\s*\([^)]*\)\s*\{", text)
    if not match:
        raise ValueError("no library group")
    end = matching_brace(text, match.end() - 1)
    return text[match.start():end]


def cell_blocks(body: str) -> list[tuple[str, str]]:
    """Return (name, source) for every top-level cell group in body."""
    pattern = re.compile(r"(?m)^  cell\s*\(([^)]+)\)\s*\{")
    blocks: list[tuple[str, str]] = []
    for match in pattern.finditer(body):
        name = match.group(1).strip().strip('"')
        end = matching_brace(body, match.end() - 1)
        blocks.append((name, body[match.start():end]))
    return blocks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("inputs", type=Path, nargs="+",
                        help="first input supplies the library header")
    args = parser.parse_args()

    cleaned: list[str] = []
    for path in args.inputs:
        text = path.read_text(errors="replace")
        text = strip_group(text, "pg_pin")
        text = re.sub(
            r"(?m)^(\s*area\s*:\s*[0-9.eE+-]+)\s*$", r"\1;", text
        )
        cleaned.append(text)

    header_body = library_body(cleaned[0])
    first_cell = re.search(r"(?m)^  cell\s*\(", header_body)
    header = header_body[:first_cell.start()] if first_cell else header_body

    # ICG cells drive a gated clock output without a combinational function,
    # and SDF cells are scan flops.  Neither is used by this RTL, and Yosys's
    # strict Liberty reader rejects the ICG output, so leave both out of the
    # synthesis library.  They remain available in the original files for P&R.
    skip_prefixes = ("ICG", "SDF")
    cells: dict[str, str] = {}
    skipped = 0
    for text in cleaned:
        for name, source in cell_blocks(library_body(text)):
            if name.startswith(skip_prefixes):
                skipped += 1
                continue
            cells.setdefault(name, source)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header + "\n" + "\n".join(cells.values()) + "\n}\n")
    print(f"{args.output}: {len(cells)} cells from {len(args.inputs)} libraries"
          f" ({skipped} ICG/SDF cells skipped)")


if __name__ == "__main__":
    main()

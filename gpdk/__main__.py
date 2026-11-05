"""Command line entry point: python -m gpdk [report|drc|padring]."""

from __future__ import annotations

import argparse

from .block import load_chip
from .dtco import best_step, build_steps
from .drc import check
from .layout import inverter_layout
from .package import PinBudget
from .padring import build_floorplan, write_artifacts
from .report import main as report_main
from .tech import ROOT, load_tech


def padring_main() -> None:
    cfg = load_chip("grx930.yaml")
    if not cfg.pin_spec:
        raise SystemExit("GRX930 has no pin budget")
    est = best_step(build_steps(cfg)).iso
    budget = PinBudget.from_spec(cfg.pin_spec, str(cfg.pin_spec["selected"]))
    plan = build_floorplan(cfg, budget, est.die_area_mm2**0.5, est.total_area_mm2)
    paths = write_artifacts(plan, ROOT / "out")
    print(
        f"{len(plan.pads)} pads on a {plan.die_mm:.3f} mm die, "
        f"{plan.min_pitch_um:.1f} um minimum pitch"
    )
    print(
        f"sides: "
        + ", ".join(f"{side} {count}" for side, count in plan.side_counts.items())
    )
    print(f"balls: {plan.balls_used} used, {plan.balls_spare} spare")
    for name, path in paths.items():
        print(f"  {name}: {path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="gpdk", description="GRX28/GRX12F PDK tools")
    parser.add_argument(
        "command",
        nargs="?",
        default="report",
        choices=["report", "drc", "padring"],
        help=(
            "report: regenerate out/; drc: check the 12 nm demo inverter; "
            "padring: rebuild the GRX930 pad ring and ball map"
        ),
    )
    args = parser.parse_args()
    if args.command == "report":
        report_main()
        return
    if args.command == "padring":
        padring_main()
        return
    tech = load_tech("grx12f.yaml")
    layout = inverter_layout(tech, tracks=7.5, coag=True)
    violations = check(layout, tech, tracks=7.5)
    print(
        f"{layout.name}: {layout.width_nm()} x {layout.height_nm()} nm, "
        f"{len(layout.shapes)} shapes, {len(violations)} violations"
    )
    for violation in violations:
        print(f"  {violation}")


if __name__ == "__main__":
    main()

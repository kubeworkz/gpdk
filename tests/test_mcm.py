"""Tests for the Phase 3 G100 + PTA MCM planning model."""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from gpdk.dieyield import package_assembly_yield, poisson_die_yield
from gpdk.mcm import McmYieldAssumptions, simulate_mcm_yield
from fabtwin.provenance import ROOT

ASSUMPTIONS_PATH = ROOT / "yields" / "g100_mcm_28nm.yaml"


def _assumptions() -> McmYieldAssumptions:
    raw = yaml.safe_load(ASSUMPTIONS_PATH.read_text(encoding="utf-8"))
    return McmYieldAssumptions.from_mapping(raw)


def test_mcm_known_answers_and_package_comparison() -> None:
    assumptions = _assumptions()
    estimate = simulate_mcm_yield(assumptions, 378.3)
    assert estimate.g100_gross_dies_per_wafer > 0
    assert estimate.pta_gross_dies_per_wafer > estimate.g100_gross_dies_per_wafer
    assert estimate.g100_die_yield == pytest.approx(
        poisson_die_yield(378.3, 0.35, 0.08)
    )
    assert estimate.pta_die_yield == pytest.approx(
        poisson_die_yield(50.0, 0.50, 0.08)
    )
    assert 0.0 < estimate.kgd_match_yield < 1.0
    assert estimate.pta_wafers_per_g100_wafer > 0.0
    assert len(estimate.options) == 3
    for option in estimate.options:
        assert option.assembly_yield == pytest.approx(
            package_assembly_yield(
                option.option.interconnect_count,
                option.option.assembly_base_yield,
                option.option.per_interconnect_ppm,
            )
        )
        assert option.good_packages_per_g100_wafer > 0.0
        assert option.cost_per_good_package_usd > 0.0
    assert estimate.best_option("cost").option.id == "organic_substrate"
    assert estimate.best_option("yield").option.id == "silicon_interposer"


def test_mcm_rejects_non_positive_pta_area() -> None:
    base = _assumptions()
    with pytest.raises(ValueError, match="area_mm2"):
        replace(base, pta=replace(base.pta, area_mm2=None))

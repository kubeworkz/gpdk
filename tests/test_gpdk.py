"""Focused tests for the GRX12F planning model."""

from __future__ import annotations

import math

import pytest

from dataclasses import replace

from gpdk.asbuilt import AsBuilt, node_jump, pad_sensitivity
from gpdk.beol import layer_rc, via_resistance_ohm, wire_delay_ps
from gpdk.package import PinBudget, choose_package
from gpdk.padring import build_floorplan, write_artifacts
from gpdk.block import (
    estimate,
    frequency_matched,
    load_chip,
    load_chips,
    pad_limited_die_mm2,
)
from gpdk.cells import Library, load_libraries
from gpdk.device import DeviceModel
from gpdk.dieyield import (
    SensitivitySpec,
    SpatialSpec,
    VariationSpec,
    WaferSpec,
    YieldAssumptions,
    assembly_tolerance_curve,
    defect_density_curve,
    die_grid,
    pad_count_curve,
    package_assembly_yield,
    poisson_die_yield,
    simulate_lot_yield,
    simulate_wafer_map,
    simulate_yield,
)
from gpdk.drc import check
from gpdk.dtco import build_steps, lever_table, reference_pair
from gpdk.gds import read_gds, write_gds
from gpdk.layout import inverter_layout
from gpdk.tech import load_tech


@pytest.fixture(scope="module")
def tech():
    return load_tech("grx12f.yaml")


@pytest.fixture(scope="module")
def tech28():
    return load_tech("grx28.yaml")


@pytest.fixture(scope="module")
def libs(tech):
    return load_libraries(tech)


@pytest.fixture(scope="module")
def chip_libs():
    return load_libraries(load_tech("grx28.yaml"))


def test_node_geometry(tech):
    assert tech.cpp_nm == pytest.approx(84.0)
    assert tech.weff_per_fin_nm == pytest.approx(2 * 44.0 + 6.5)
    assert tech.cell_height_nm(9) == pytest.approx(576.0)
    assert tech.cell_height_nm(7.5) == pytest.approx(480.0)
    assert tech.cell_height_nm(6) == pytest.approx(384.0)
    assert tech.max_fins_per_device(6) >= 1
    assert tech.max_fins_per_device(9) > tech.max_fins_per_device(6)
    with pytest.raises(ValueError):
        tech.cell_height_nm(2)


def test_planar_node_geometry(tech28):
    assert tech28.device_kind == "planar"
    assert tech28.weff_per_fin_nm == pytest.approx(120.0)
    assert tech28.width_unit_name == "finger"
    assert tech28.cell_height_nm(9) == pytest.approx(810.0)
    assert tech28.cell_height_nm(7.5) == pytest.approx(675.0)
    assert tech28.max_fins_per_device(7.5) == 2
    assert tech28.max_fins_per_device(6) == 1
    assert tech28.sram.hd_bitcell_um2 == pytest.approx(0.135)
    fo4 = DeviceModel(tech28).stage(1, 1, tech28.vdd_hp).fo4_ps
    assert 18.0 < fo4 < 30.0


def test_28nm_libraries_do_not_mix_nodes(tech28):
    planar = load_libraries(tech28)
    assert set(planar) == {"lp28_7t5_1f", "lp28_9t_1f"}
    finfet = load_libraries(load_tech("grx12f.yaml"))
    assert not set(planar) & set(finfet)
    assert all(lib.tech.device_kind == "planar" for lib in planar.values())


def test_grx930_28nm_is_pad_limited(chip_libs):
    cfg = load_chip("grx930.yaml")
    assert cfg.tech_file == "grx28.yaml"
    est = estimate(cfg, chip_libs[cfg.library])
    assert est.total_area_mm2 == pytest.approx(0.80, abs=0.05)
    assert est.sram_area_mm2 == pytest.approx(0.1475, abs=0.002)
    assert est.die_binding == "pad ring"
    assert est.die_area_mm2 == pytest.approx(13.0, abs=0.1)
    assert est.power_at_target_w < 0.010


def test_reference_tech_loads():
    ref = load_tech("12lp_class_ref.yaml")
    assert ref.cpp_nm > load_tech("grx12f.yaml").cpp_nm
    assert ref.via_pillar_enabled is False


def test_device_metrics_are_in_range(tech):
    dev = DeviceModel(tech)
    n = dev.point("n", 1, tech.vdd_hp)
    p = dev.point("p", 1, tech.vdd_hp)
    assert 40 < n.ion_ua < 100
    assert p.ion_ua < n.ion_ua
    assert 0.05 < n.cgg_ff < 0.15
    assert 10 < n.ron_ohm / 1000 < 25
    fo4 = dev.stage(1, 1, tech.vdd_hp).fo4_ps
    assert 11.0 < fo4 < 18.0


def test_scaling_with_fins(tech):
    dev = DeviceModel(tech)
    one = dev.point("n", 1, tech.vdd_hp)
    two = dev.point("n", 2, tech.vdd_hp)
    assert two.ion_ua == pytest.approx(2 * one.ion_ua)
    assert two.ron_ohm == pytest.approx(one.ron_ohm / 2)
    # FO4 is scale invariant: twice the drive and twice the input capacitance.
    assert dev.stage(1, 1, tech.vdd_hp).fo4_ps == pytest.approx(
        dev.stage(2, 2, tech.vdd_hp).fo4_ps
    )


def test_leakage_rises_with_temperature(tech):
    hot = DeviceModel(tech, temp_c=85.0)
    cold = DeviceModel(tech, temp_c=25.0)
    assert hot.ioff_per_fin_na("n", tech.vdd_hp) > 5 * cold.ioff_per_fin_na(
        "n", tech.vdd_hp
    )


def test_library_height_and_isolation_ordering(libs):
    areas = [libs[k].avg_cell_area_um2 for k in ("hp9t_2f", "hp7t5_2f", "hd6t_1f")]
    assert areas[0] > areas[1] > areas[2]
    assert libs["hp7t5_1f"].routable_utilization() < libs["hp9t_2f"].routable_utilization()
    assert libs["hp7t5_1f"].avg_leakage_nw < libs["hp9t_2f"].avg_leakage_nw


def test_fin_count_does_not_change_cell_area(tech):
    """A fin stacks vertically: adding one must not widen the cell."""
    one = Library.build(
        tech,
        id="one",
        label="one",
        tracks=7.5,
        base_fins=1,
        isolation="SDB",
        coag=True,
    )
    two = Library.build(
        tech,
        id="two",
        label="two",
        tracks=7.5,
        base_fins=2,
        isolation="SDB",
        coag=True,
    )
    assert one.avg_cell_area_um2 == pytest.approx(two.avg_cell_area_um2)
    assert two.avg_cell_area_um2 > 0


def test_isolation_overhead_and_coag(tech):
    ddb = Library.build(
        tech, id="ddb", label="", tracks=7.5, base_fins=1, isolation="DDB", coag=False
    )
    sdb = Library.build(
        tech, id="sdb", label="", tracks=7.5, base_fins=1, isolation="SDB", coag=False
    )
    coag = Library.build(
        tech, id="coag", label="", tracks=7.5, base_fins=1, isolation="SDB", coag=True
    )
    assert ddb.cells["INV_X1"].width_cpp > sdb.cells["INV_X1"].width_cpp
    assert coag.cells["INV_X1"].width_cpp < sdb.cells["INV_X1"].width_cpp
    assert coag.cells["INV_X1"].width_cpp >= 2.0


def test_mbff_area_and_clock_cap(libs):
    lib = libs["hd6t_1f"]
    assert lib.dff_area_per_bit_um2(2) < lib.dff_area_per_bit_um2(1)
    assert lib.dff_area_per_bit_um2(4) < lib.dff_area_per_bit_um2(2)
    assert lib.clock_cap_per_bit_ff(4) < lib.clock_cap_per_bit_ff(1)


def test_beol_size_effect(tech):
    m1 = layer_rc(tech, tech.m1)
    m6 = layer_rc(tech, tech.layer("M6"))
    assert m1.r_ohm_per_um > m6.r_ohm_per_um
    assert m1.c_ff_per_um < m6.c_ff_per_um
    assert via_resistance_ohm(tech, tech.m1, pillar=True) < via_resistance_ohm(
        tech, tech.m1, pillar=False
    )
    # Wire-only delay is distributed RC, so it scales with L^2.
    d1 = wire_delay_ps(m1, 100.0, 0.0)
    d2 = wire_delay_ps(m1, 200.0, 0.0)
    assert d2 == pytest.approx(4 * d1)
    assert wire_delay_ps(m1, 100.0, 5000.0) > d1


def test_block_area_and_frequency(chip_libs):
    cfg = load_chip("grx930.yaml")
    est = estimate(cfg, chip_libs[cfg.library])
    assert est.total_area_mm2 > est.cell_area_mm2
    assert 0.4 < est.util < 0.9
    assert 1.0 < est.freq_ghz < 6.0
    assert 0.0 < est.total_power_w < 100.0
    assert est.total_area_mm2 > est.sram_area_mm2 + est.io_area_mm2


def test_mbff_reduces_clock_power(chip_libs):
    cfg = load_chip("grx930.yaml")
    lib = chip_libs[cfg.library]
    plain = estimate(cfg, lib, mbff_bits=1)
    merged = estimate(cfg, lib, mbff_bits=4)
    assert merged.clock_w < plain.clock_w
    assert merged.ff_area_mm2 < plain.ff_area_mm2


def test_frequency_matching(chip_libs):
    cfg = load_chip("grx930.yaml")
    lib = chip_libs[cfg.library]
    target = 5.0  # deliberately above what a single fin can do
    est = frequency_matched(cfg, lib, target)
    assert est.upsize_fins >= lib.base_fins
    if est.freq_ghz < target:
        assert est.upsize_fins == lib.tech.max_fins_per_device(lib.tracks)


def test_dtco_steps_reduce_area(libs):
    cfg = load_chip("g100.yaml")
    pair = reference_pair(cfg)
    assert pair.node.total_area_mm2 < pair.reference.total_area_mm2
    steps = build_steps(cfg)
    rows = lever_table(steps)
    assert rows[0]["step"] == "node9t"
    assert rows[-1]["iso_area_mm2"] < rows[0]["iso_area_mm2"]
    for row in rows[1:]:
        assert row["step_delta_pct"] <= 1.0  # nothing should grow by more than 1%
    assert all(step.iso.freq_ghz >= 0.95 * step.target_ghz for step in steps)


def test_load_chips_skips_non_digital_products():
    assert {cfg.name for cfg in load_chips()} == {"G100", "GRX930"}


def test_layout_is_drc_clean(tech):
    layout = inverter_layout(tech, tracks=7.5, coag=True)
    violations = check(layout, tech, tracks=7.5)
    assert violations == []
    assert layout.width_nm() == 210
    assert layout.height_nm() == 480


def test_drc_catches_bad_geometry(tech):
    layout = inverter_layout(tech, tracks=7.5, coag=True)
    layout.add("M1", 0, 200, 10, 210)  # too narrow and too close to the edge
    violations = check(layout, tech, tracks=7.5)
    assert any(v.rule == "min-width" for v in violations)


def test_sram_area_includes_periphery(libs):
    cfg = load_chip("grx930.yaml")
    lib = libs["hp7t5_1f"]
    est = estimate(cfg, lib)
    raw_array_um2 = cfg.sram_mb * 8e6 * lib.tech.sram.hd_bitcell_um2
    assert est.sram_area_mm2 * 1e6 > raw_array_um2  # periphery is not free


def test_pad_floor_scales_with_pins(libs):
    cfg = load_chip("grx930.yaml")
    assert pad_limited_die_mm2(cfg) > 0
    rows = pad_sensitivity(cfg)
    areas = [r["die_mm2"] for r in rows]
    assert areas == sorted(areas)
    assert areas[-1] > 2 * areas[0]


def test_measured_baseline_is_internally_consistent():
    cfg = load_chip("grx930.yaml")
    assert cfg.as_built is not None
    ab = AsBuilt.from_mapping(cfg.as_built)
    assert ab.logic_mm2 + ab.sram_mm2 == pytest.approx(ab.content_mm2)
    assert ab.derived_util == pytest.approx(0.524, abs=0.01)
    assert 30 < ab.logic_um2_per_nand2 < 40
    assert 45 < ab.sram_um2_per_bit < 60


def test_node_jump_separates_node_from_dtco(libs):
    cfg = load_chip("grx930.yaml")
    ab = AsBuilt.from_mapping(cfg.as_built)
    est = estimate(cfg, libs["hp7t5_1f"])
    jump = node_jump(est, ab)
    assert jump.content_ratio > 100  # a node jump, not a DTCO delta
    assert jump.projected_content_mm2 < 1.0
    assert jump.die_binding == "pad ring"
    assert jump.die_area_mm2 == pytest.approx(est.pad_floor_mm2)
    assert jump.empty_fraction > 0.9  # the pad ring, not logic, sets the die
    assert jump.integration_headroom > 100


def test_power_at_measured_clock(libs):
    cfg = load_chip("grx930.yaml")
    est = estimate(cfg, libs["hp7t5_1f"])
    assert est.target_ghz == pytest.approx(0.025)
    assert est.power_at_target_w < 0.05 * est.total_power_w
    assert est.power_at_target_w >= est.leakage_w


def test_pin_budget_comes_from_interfaces():
    cfg = load_chip("grx930.yaml")
    assert cfg.pin_spec is not None
    pb = PinBudget.from_spec(cfg.pin_spec, "as_built")
    assert pb.signal_pads == 118
    assert pb.io_supply_pairs == 20  # one pair per 6 signals
    assert pb.total_pads == 178
    assert cfg.pad_pins == pb.total_pads


def test_pin_variants_reduce_pads():
    cfg = load_chip("grx930.yaml")
    counts = {
        key: PinBudget.from_spec(cfg.pin_spec, key).total_pads
        for key in ("as_built", "narrow_ddr", "integrated")
    }
    assert counts == {"as_built": 178, "narrow_ddr": 112, "integrated": 57}


def test_package_selection():
    assert choose_package(178, 3.6).name == "TFBGA-196"
    assert choose_package(112, 2.3).name == "QFN-128"
    assert choose_package(57, 2.0).name == "QFN-64"
    assert choose_package(400, 5.0) is None


def test_pad_ring_sets_grx930_die(chip_libs):
    cfg = load_chip("grx930.yaml")
    est = estimate(cfg, chip_libs[cfg.library])
    assert est.die_binding == "pad ring"
    assert est.die_area_mm2 == pytest.approx(13.0, abs=0.1)
    assert est.assembly_floor_mm2 == pytest.approx(4.0)


def test_integrated_memory_is_assembly_limited(chip_libs):
    cfg = load_chip("grx930.yaml")
    pb = PinBudget.from_spec(cfg.pin_spec, "integrated")
    est = estimate(replace(cfg, pad_pins=pb.total_pads), chip_libs[cfg.library])
    assert est.die_binding == "assembly minimum"
    assert est.die_area_mm2 == pytest.approx(4.0)


def test_padring_places_every_pad(chip_libs):
    cfg = load_chip("grx930.yaml")
    est = estimate(cfg, chip_libs[cfg.library])
    plan = build_floorplan(
        cfg, PinBudget.from_spec(cfg.pin_spec, "as_built"), est.die_area_mm2**0.5
    )
    assert len(plan.pads) == 178
    assert plan.side_counts == {"south": 44, "east": 44, "north": 45, "west": 45}
    assert plan.min_pitch_um >= 150.0
    assert len({p.net for p in plan.pads}) == 178


def test_ball_map_is_complete(chip_libs):
    cfg = load_chip("grx930.yaml")
    est = estimate(cfg, chip_libs[cfg.library])
    plan = build_floorplan(
        cfg, PinBudget.from_spec(cfg.pin_spec, "as_built"), est.die_area_mm2**0.5
    )
    assert len(plan.balls) == 196
    assert plan.balls_used == 178
    assert plan.balls_spare == 18
    pad_nets = {p.net for p in plan.pads}
    ball_nets = {b.net for b in plan.balls if b.kind != "spare"}
    assert ball_nets == pad_nets


def test_padring_artifacts(chip_libs, tmp_path):
    cfg = load_chip("grx930.yaml")
    est = estimate(cfg, chip_libs[cfg.library])
    plan = build_floorplan(
        cfg, PinBudget.from_spec(cfg.pin_spec, "as_built"), est.die_area_mm2**0.5
    )
    paths = write_artifacts(plan, tmp_path)
    assert paths["png"].exists() and paths["png"].stat().st_size > 5000
    assert paths["svg"].read_text(encoding="utf-8").startswith("<svg")
    assert len(paths["padring_csv"].read_text(encoding="utf-8").splitlines()) == 179
    assert len(paths["ballmap_csv"].read_text(encoding="utf-8").splitlines()) == 197


def test_gds_round_trip(tech, tmp_path):
    layout = inverter_layout(tech, tracks=7.5, coag=True)
    path = write_gds(layout, tmp_path / "inv.gds")
    info = read_gds(path)
    assert info["boundaries"] == len(layout.shapes)
    assert info["bbox_nm"] == (0, 0, 210, 480)
    assert len(info["layers"]) == 9
    assert path.stat().st_size > 500


def test_die_grid_known_answers():
    wafer = WaferSpec(
        diameter_mm=100.0,
        edge_exclusion_mm=0.0,
        scribe_lane_um=0.0,
        cost_usd=1000.0,
    )
    assert die_grid(wafer, 10.0, 10.0).count == 60
    exact_fit = WaferSpec(
        diameter_mm=2.0 * math.sqrt(50.0),
        edge_exclusion_mm=0.0,
        scribe_lane_um=0.0,
        cost_usd=1000.0,
    )
    assert die_grid(exact_fit, 10.0, 10.0).count == 1


def test_poisson_yield_known_answer():
    assert poisson_die_yield(100.0, 0.5, 1.0) == pytest.approx(
        math.exp(-0.5)
    )
    assert poisson_die_yield(100.0, 0.5, 0.0) == 1.0
    assert poisson_die_yield(100.0, 0.5, 2.0) < poisson_die_yield(
        100.0, 0.5, 1.0
    )


def test_package_assembly_yield_known_answer():
    assert package_assembly_yield(0, 0.99, 10.0) == pytest.approx(0.99)
    assert package_assembly_yield(100, 0.99, 10.0) < 0.99


def test_yield_simulation_is_seeded_and_physical():
    assumptions = YieldAssumptions(
        id="test_yield",
        product="grx930",
        process="grx28@0.1.0",
        revision="0.1.0",
        wafer=WaferSpec(100.0, 0.0, 0.0, 1000.0),
        defect_density_per_cm2=0.1,
        critical_area_fraction=0.5,
        base_assembly_yield=0.99,
        per_pad_defect_ppm=10.0,
        package_cost_usd=1.0,
        test_cost_usd=0.2,
    )
    first = simulate_yield(assumptions, 100.0, 100, samples=20, seed=7)
    second = simulate_yield(assumptions, 100.0, 100, samples=20, seed=7)
    assert first == second
    assert 0.0 < first.die_yield < 1.0
    assert first.known_good_dies_per_wafer < first.gross_dies_per_wafer
    assert first.good_packages_per_wafer < first.known_good_dies_per_wafer
    assert first.cost_per_good_package_usd > 0.0


def test_defect_density_curve_is_monotonic():
    assumptions = YieldAssumptions(
        id="test_curve",
        product="grx930",
        process="grx28@0.1.0",
        revision="0.1.0",
        wafer=WaferSpec(100.0, 0.0, 0.0, 1000.0),
        defect_density_per_cm2=0.1,
        critical_area_fraction=0.5,
        base_assembly_yield=0.99,
        per_pad_defect_ppm=10.0,
        package_cost_usd=1.0,
        test_cost_usd=0.2,
    )
    rows = defect_density_curve(
        assumptions,
        100.0,
        100,
        (0.0, 0.1, 0.5),
        samples=20,
    )
    yields = [row["die_yield"] for row in rows]
    assert yields == sorted(yields, reverse=True)
    assert all("die_yield_stderr" in row for row in rows)


def _sensitivity_assumptions() -> YieldAssumptions:
    return YieldAssumptions(
        id="test_sensitivity",
        product="grx930",
        process="grx28@0.1.0",
        revision="0.1.0",
        wafer=WaferSpec(100.0, 0.0, 0.0, 1000.0),
        defect_density_per_cm2=0.1,
        critical_area_fraction=0.5,
        base_assembly_yield=0.99,
        per_pad_defect_ppm=10.0,
        package_cost_usd=1.0,
        test_cost_usd=0.2,
    )


def test_sensitivity_spec_parses_and_rejects_bad_points():
    spec = SensitivitySpec.from_mapping(
        {
            "sensitivity": {
                "defect_density_per_cm2": [0.02, 0.2],
                "pad_counts": [57, 220],
                "assembly_per_pad_ppm": [2.0, 20.0],
            }
        }
    )
    assert spec.defect_density_per_cm2 == (0.02, 0.2)
    assert spec.pad_counts == (57, 220)
    with pytest.raises(ValueError, match="sensitivity mapping"):
        SensitivitySpec.from_mapping({})
    with pytest.raises(ValueError, match="pad counts must be positive"):
        SensitivitySpec.from_mapping(
            {
                "sensitivity": {
                    "defect_density_per_cm2": [0.1],
                    "pad_counts": [0],
                    "assembly_per_pad_ppm": [8.0],
                }
            }
        )


def test_pad_count_curve_is_monotonic_and_reproducible():
    assumptions = replace(_sensitivity_assumptions(), per_pad_defect_ppm=2000.0)
    first = pad_count_curve(
        assumptions, 100.0, (57, 112, 178, 220), samples=20, seed=5
    )
    second = pad_count_curve(
        assumptions, 100.0, (57, 112, 178, 220), samples=20, seed=5
    )
    assert first == second
    packages = [row["good_packages_per_wafer"] for row in first]
    assert packages == sorted(packages, reverse=True)
    costs = [row["cost_per_good_package_usd"] for row in first]
    assert costs == sorted(costs)
    assert all(row["good_packages_stderr"] > 0.0 for row in first)
    assert all(row["cost_per_good_package_stderr"] > 0.0 for row in first)


def test_assembly_tolerance_curve_is_monotonic():
    rows = assembly_tolerance_curve(
        _sensitivity_assumptions(),
        100.0,
        178,
        (0.0, 500.0, 2000.0),
        samples=20,
        seed=9,
    )
    packages = [row["good_packages_per_wafer"] for row in rows]
    assert packages == sorted(packages, reverse=True)
    assert rows[0]["assembly_per_pad_ppm"] == 0.0
    assert rows[0]["good_packages_per_wafer"] > rows[-1][
        "good_packages_per_wafer"
    ]
    assert rows[0]["cost_per_good_package_usd"] < rows[-1][
        "cost_per_good_package_usd"
    ]
    assert all(row["die_yield_stderr"] > 0.0 for row in rows)


def test_zero_good_packages_is_reported_clearly():
    assumptions = replace(_sensitivity_assumptions(), base_assembly_yield=0.0)
    with pytest.raises(ValueError, match="no good packages"):
        simulate_yield(assumptions, 100.0, 100, samples=5)


def test_variation_spec_parses_and_rejects_bad_cv():
    spec = VariationSpec.from_mapping(
        {
            "variation": {
                "wafers_per_lot": 10,
                "defect_density_cv_lot": 0.2,
                "defect_density_cv_wafer": 0.1,
                "assembly_ppm_cv_lot": 0.05,
            }
        }
    )
    assert spec.wafers_per_lot == 10
    assert spec.defect_density_cv_lot == 0.2
    with pytest.raises(ValueError, match="variation mapping"):
        VariationSpec.from_mapping({})
    with pytest.raises(ValueError, match="non-negative"):
        VariationSpec.from_mapping(
            {"variation": {"defect_density_cv_lot": -0.1}}
        )


def test_lot_simulation_with_zero_cv_has_no_process_variation():
    assumptions = replace(
        _sensitivity_assumptions(),
        variation=VariationSpec(
            wafers_per_lot=10,
            defect_density_cv_lot=0.0,
            defect_density_cv_wafer=0.0,
            assembly_ppm_cv_lot=0.0,
        ),
    )
    estimate = simulate_lot_yield(assumptions, 100.0, 100, lots=12, seed=3)
    assert estimate.wafer_to_wafer_die_yield_sigma == 0.0
    assert estimate.lot_to_lot_die_yield_sigma == 0.0
    assert estimate.die_yield_stderr == 0.0
    assert estimate.die_yield_mean == pytest.approx(
        poisson_die_yield(100.0, 0.5, 0.1)
    )
    assert estimate.assembly_yield_mean == pytest.approx(
        package_assembly_yield(100, 0.99, 10.0)
    )


def test_lot_variation_is_seeded_and_ordered():
    assumptions = replace(
        _sensitivity_assumptions(),
        variation=VariationSpec(
            wafers_per_lot=8,
            defect_density_cv_lot=0.15,
            defect_density_cv_wafer=0.10,
            assembly_ppm_cv_lot=0.10,
        ),
    )
    first = simulate_lot_yield(assumptions, 100.0, 100, lots=20, seed=7)
    second = simulate_lot_yield(assumptions, 100.0, 100, lots=20, seed=7)
    assert first == second
    assert first.lots == 20
    assert first.wafers == 160
    assert 0.0 < first.die_yield_mean < 1.0
    assert first.die_yield_stderr is not None
    assert first.wafer_to_wafer_die_yield_sigma > 0.0
    assert first.lot_to_lot_die_yield_sigma > first.wafer_to_wafer_die_yield_sigma
    assert first.good_packages_per_wafer_mean > 0.0
    assert first.cost_per_good_package_usd_mean > 0.0


def test_lot_simulation_requires_variation_mapping():
    with pytest.raises(ValueError, match="variation mapping"):
        simulate_lot_yield(_sensitivity_assumptions(), 100.0, 100, lots=2)


def test_spatial_spec_parses_and_rejects_bad_profile():
    spec = SpatialSpec.from_mapping(
        {
            "spatial": {
                "edge_boost": 1.5,
                "radial_exponent": 2.0,
                "radial_bins": 4,
            }
        }
    )
    assert spec.edge_boost == 1.5
    assert spec.radial_bins == 4
    with pytest.raises(ValueError, match="spatial mapping"):
        SpatialSpec.from_mapping({})
    with pytest.raises(ValueError, match="radial exponent"):
        SpatialSpec.from_mapping({"spatial": {"radial_exponent": 0.0}})
    with pytest.raises(ValueError, match="radial bins"):
        SpatialSpec.from_mapping({"spatial": {"radial_bins": 1}})


def test_wafer_map_is_seeded_and_edge_limited():
    assumptions = replace(
        _sensitivity_assumptions(),
        spatial=SpatialSpec(
            edge_boost=2.0,
            radial_exponent=3.0,
            radial_bins=5,
        ),
    )
    first = simulate_wafer_map(assumptions, 100.0, 100, samples=40, seed=11)
    second = simulate_wafer_map(assumptions, 100.0, 100, samples=40, seed=11)
    assert first == second
    assert len(first.zones) == 5
    assert sum(zone.die_count for zone in first.zones) == (
        first.gross_dies_per_wafer
    )
    assert first.zones[0].die_yield > first.zones[-1].die_yield
    assert first.center_die_yield > first.edge_die_yield
    assert first.edge_to_center_yield_ratio < 1.0
    assert first.radial_yield_slope_per_mm < 0.0
    densities = [zone.defect_density_per_cm2 for zone in first.zones]
    assert densities == sorted(densities)
    assert 0.0 < first.die_yield_mean < 1.0
    assert first.die_yield_stderr is not None
    assert first.good_packages_per_wafer > 0.0
    assert first.cost_per_good_package_usd > 0.0


def test_wafer_map_without_edge_boost_is_flat():
    assumptions = replace(
        _sensitivity_assumptions(),
        spatial=SpatialSpec(edge_boost=0.0),
    )
    estimate = simulate_wafer_map(assumptions, 100.0, 100, samples=20, seed=4)
    assert estimate.center_die_yield == pytest.approx(
        estimate.edge_die_yield
    )
    assert estimate.edge_to_center_yield_ratio == pytest.approx(1.0)
    assert estimate.radial_yield_slope_per_mm == pytest.approx(0.0, abs=1e-12)
    assert estimate.die_yield_mean == pytest.approx(
        poisson_die_yield(100.0, 0.5, 0.1), abs=0.002
    )


def test_wafer_map_requires_spatial_mapping():
    with pytest.raises(ValueError, match="spatial mapping"):
        simulate_wafer_map(_sensitivity_assumptions(), 100.0, 100)

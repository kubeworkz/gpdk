"""Tests for the F1 PTA photonic and thermal planning model."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from gpdk.photonic_calibration import PhotonicCalibration
from gpdk.photonics import (
    GaussianParameter,
    PhotonicAssumptions,
    PhotonicDesign,
    simulate_photonic,
)

ROOT = Path(__file__).resolve().parents[1]
ASSUMPTIONS_PATH = ROOT / "photonic" / "pta_siph_28nm.yaml"


def _assumptions() -> PhotonicAssumptions:
    raw = yaml.safe_load(ASSUMPTIONS_PATH.read_text(encoding="utf-8"))
    return PhotonicAssumptions.from_mapping(raw)


def _design() -> PhotonicDesign:
    return PhotonicDesign(
        mesh_rows=4,
        mesh_columns=4,
        optical_window_um=200.0,
    )


def _calibration_mapping() -> dict:
    parameters = {
        "width_sensitivity_per_nm": (0.0004, "1/nm"),
        "etch_sensitivity_per_nm": (0.0002, "1/nm"),
        "base_loss_db_per_cm": (0.8, "dB/cm"),
        "scattering_loss_db_per_cm_nm2": (0.4, "dB/cm/nm2"),
        "coupling_loss_db": (0.9, "dB"),
        "alignment_loss_db_per_um2": (18.0, "dB/um2"),
        "mesh_excess_loss_db": (0.04, "dB"),
        "thermo_optic_per_k": (0.00018, "1/K"),
        "thermal_resistance_k_per_w": (4.0, "K/W"),
    }
    return {
        "schema_version": "0.1",
        "id": "pta_siph_synthetic_cal",
        "revision": "0.2.0",
        "product": "pta",
        "process": "grx28@0.1.0",
        "description": "Synthetic fixture for tests; not real measured data.",
        "evidence": "measured",
        "source": "synthetic test fixture",
        "parameters": {
            name: {
                "value": value,
                "uncertainty": max(abs(value) * 0.01, 1e-6),
                "unit": unit,
                "test_structure": f"synthetic {name} structure",
                "method": "synthetic linear extraction",
            }
            for name, (value, unit) in parameters.items()
        },
    }


def _flat_assumptions() -> PhotonicAssumptions:
    base = _assumptions()
    zero = GaussianParameter
    return replace(
        base,
        variation=replace(
            base.variation,
            width_nm=zero(450.0, 0.0),
            etch_depth_nm=zero(220.0, 0.0),
            ler_nm=zero(0.0, 0.0),
            alignment_um=zero(0.0, 0.0),
            ambient_c=zero(25.0, 0.0),
        ),
        thermal=replace(
            base.thermal,
            electronic_heat_w=0.0,
            trench_count=0,
            trench_width_um=0.0,
        ),
    )


def test_known_answer_flat_case() -> None:
    estimate = simulate_photonic(
        _flat_assumptions(), _design(), samples=1, seed=0
    )
    assert estimate.insertion_loss_db_mean == pytest.approx(2.49)
    assert estimate.phase_error_rad_mean == pytest.approx(0.0)
    assert estimate.tensor_error_mean == pytest.approx(0.0)
    assert estimate.tuning_power_w_mean == pytest.approx(0.0)
    assert estimate.temperature_rise_k_mean == pytest.approx(0.0)
    assert estimate.insertion_loss_db_stderr is None


def test_thermal_path_known_answer() -> None:
    estimate = simulate_photonic(
        _assumptions(), _design(), samples=1, seed=0
    )
    assert estimate.thermal_resistance_k_per_w == pytest.approx(
        3.38255, rel=1e-4
    )
    assert estimate.local_temperature_rise_k == pytest.approx(
        6.76510, rel=1e-4
    )


def test_simulation_is_seeded_and_reports_uncertainty() -> None:
    first = simulate_photonic(_assumptions(), _design(), samples=80, seed=11)
    second = simulate_photonic(_assumptions(), _design(), samples=80, seed=11)
    assert first == second
    assert first.insertion_loss_db_stderr is not None
    assert first.phase_error_rad_stderr is not None
    assert first.tuning_power_w_stderr is not None
    assert first.tensor_error_stderr is not None
    assert first.temperature_rise_k_stderr is not None
    assert first.insertion_loss_db_mean > 0.0
    assert first.phase_error_rad_mean > 0.0
    assert first.tuning_power_w_mean > 0.0
    assert first.tensor_error_mean > 0.0
    assert first.thermal_resistance_k_per_w > 0.0


def test_width_and_etch_increase_phase_error() -> None:
    base = _flat_assumptions()
    wide = replace(
        base,
        variation=replace(
            base.variation,
            width_nm=GaussianParameter(455.0, 0.0),
        ),
    )
    deep = replace(
        base,
        variation=replace(
            base.variation,
            etch_depth_nm=GaussianParameter(225.0, 0.0),
        ),
    )
    nominal = simulate_photonic(base, _design(), samples=1)
    wider = simulate_photonic(wide, _design(), samples=1)
    deeper = simulate_photonic(deep, _design(), samples=1)
    assert wider.phase_error_rad_mean > nominal.phase_error_rad_mean
    assert deeper.phase_error_rad_mean > nominal.phase_error_rad_mean
    expected_phase = (
        2.0 * 3.141592653589793 * 0.0025 * 200e-6 / 1550e-9
    )
    assert wider.phase_error_rad_mean == pytest.approx(expected_phase)
    assert wider.tensor_error_mean == pytest.approx(expected_phase / 3.141592653589793)
    assert wider.tuning_power_w_mean == pytest.approx(
        expected_phase * 20.0 / (2.0 * 3.141592653589793) * 16.0 / 1000.0
    )


def test_ler_alignment_and_heat_increase_loss_or_phase() -> None:
    base = _flat_assumptions()
    rough = replace(
        base,
        variation=replace(
            base.variation,
            ler_nm=GaussianParameter(3.0, 0.0),
        ),
    )
    misaligned = replace(
        base,
        variation=replace(
            base.variation,
            alignment_um=GaussianParameter(0.5, 0.0),
        ),
    )
    hot = replace(
        base,
        thermal=replace(base.thermal, electronic_heat_w=5.0),
    )
    nominal = simulate_photonic(base, _design(), samples=1)
    rough_estimate = simulate_photonic(rough, _design(), samples=1)
    misaligned_estimate = simulate_photonic(misaligned, _design(), samples=1)
    hot_estimate = simulate_photonic(hot, _design(), samples=1)
    assert rough_estimate.insertion_loss_db_mean > nominal.insertion_loss_db_mean
    assert (
        misaligned_estimate.insertion_loss_db_mean
        > nominal.insertion_loss_db_mean
    )
    assert hot_estimate.phase_error_rad_mean > nominal.phase_error_rad_mean


def test_sensitivity_ranking_identifies_dominant_parameters() -> None:
    estimate = simulate_photonic(_assumptions(), _design(), samples=50, seed=3)
    assert estimate.dominant_phase_parameter == "width_nm"
    assert estimate.dominant_loss_parameter == "alignment_um"
    phase = {
        item.parameter: item.phase_error_swing_rad
        for item in estimate.sensitivity
    }
    loss = {
        item.parameter: item.insertion_loss_swing_db
        for item in estimate.sensitivity
    }
    assert phase["width_nm"] > phase["etch_depth_nm"]
    assert phase["width_nm"] > phase["ambient_c"]
    assert loss["alignment_um"] > loss["ler_nm"]


def test_calibration_replaces_all_model_groups() -> None:
    calibration = PhotonicCalibration.from_mapping(_calibration_mapping())
    result = calibration.apply(_assumptions())
    assert result.remaining == ()
    assert result.incomplete_groups == ()
    assert result.complete_groups == ("width", "etch", "loss", "thermal")
    assert result.assumptions.optical.width_sensitivity_per_nm == 0.0004
    assert result.assumptions.optical.etch_sensitivity_per_nm == 0.0002
    assert result.assumptions.optical.base_loss_db_per_cm == 0.8
    assert result.assumptions.optical.scattering_loss_db_per_cm_nm2 == 0.4
    assert result.assumptions.optical.coupling_loss_db == 0.9
    assert result.assumptions.optical.alignment_loss_db_per_um2 == 18.0
    assert result.assumptions.optical.mesh_excess_loss_db == 0.04
    assert result.assumptions.optical.thermo_optic_per_k == 0.00018
    assert result.assumptions.thermal.resistance_k_per_w() == 4.0
    assert simulate_photonic(
        result.assumptions, _design(), samples=1
    ).thermal_resistance_k_per_w == pytest.approx(4.0)


def test_partial_calibration_leaves_other_assumptions_visible() -> None:
    raw = _calibration_mapping()
    raw["parameters"] = {
        "base_loss_db_per_cm": raw["parameters"]["base_loss_db_per_cm"]
    }
    result = PhotonicCalibration.from_mapping(raw).apply(_assumptions())
    assert result.calibrated == ("base_loss_db_per_cm",)
    assert result.complete_groups == ()
    assert "loss" in result.incomplete_groups
    assert "etch" in result.incomplete_groups
    assert "width_sensitivity_per_nm" in result.remaining
    assert result.assumptions.optical.base_loss_db_per_cm == 0.8


def test_calibration_rejects_non_measured_or_unknown_data() -> None:
    with pytest.raises(ValueError, match="evidence"):
        PhotonicCalibration.from_mapping(
            {**_calibration_mapping(), "evidence": "assumed"}
        )
    raw = _calibration_mapping()
    raw["parameters"]["width_sensitivity_per_nm"]["unit"] = "nm"
    with pytest.raises(ValueError, match="unit"):
        PhotonicCalibration.from_mapping(raw)
    raw = _calibration_mapping()
    raw["parameters"]["not_a_parameter"] = raw["parameters"].pop(
        "base_loss_db_per_cm"
    )
    with pytest.raises(ValueError, match="unknown calibration"):
        PhotonicCalibration.from_mapping(raw)
    raw = _calibration_mapping()
    raw["parameters"]["base_loss_db_per_cm"]["uncertainty"] = 0.0
    with pytest.raises(ValueError, match="uncertainty"):
        PhotonicCalibration.from_mapping(raw)


def test_photonic_assumptions_reject_bad_values() -> None:
    with pytest.raises(ValueError, match="sigma"):
        GaussianParameter(1.0, -0.1)
    base = _assumptions()
    with pytest.raises(ValueError, match="trenches exceed"):
        replace(
            base.thermal,
            trench_count=2,
            trench_width_um=1000.0,
        )
    with pytest.raises(ValueError, match="width mean"):
        replace(
            base.variation,
            width_nm=GaussianParameter(0.0, 1.0),
        )

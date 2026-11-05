"""Analytic device model for a FinFET or planar node.

This is deliberately *not* BSIM-CMG. It is a transparent planning model that
captures the effects our DTCO decisions actually depend on:

  * effective width per fin (tri-gate: 2*Hfin + Tfin)
  * drive current per fin, with overdrive and DIBL-aware Vt
  * subthreshold leakage per fin, with supply and temperature dependence
  * gate capacitance per fin from EOT and drawn Lg
  * on-resistance and a fanout-of-4 inverter delay

The absolute numbers are targets taken from public literature for the node in
question (12/14 nm FinFET, or 28 nm planar HKMG).
They are accurate enough to compare library and node choices, not to sign off a
design.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tech import Polarity, Tech

EPS_OX_F_PER_M = 3.9 * 8.854e-12
REF_TEMP_C = 25.0


def cox_ff_per_um2(tech: Tech) -> float:
    """Gate capacitance per unit area at inversion (fF/um^2)."""
    return EPS_OX_F_PER_M * 1e3 / (tech.eot_nm * 1e-9)


@dataclass(frozen=True)
class StageMetrics:
    """Electrical metrics for one inverter-sized stage."""

    vdd: float
    nfins_n: int
    nfins_p: int
    cin_ff: float
    ion_ua: float
    ioff_na: float
    ron_ohm: float
    fo4_ps: float

    @property
    def drive_ua(self) -> float:
        return self.ion_ua


@dataclass(frozen=True)
class DevicePoint:
    polarity: str
    vdd: float
    nfins: int
    weff_um: float
    ion_ua: float
    ioff_na: float
    cgg_ff: float
    ron_ohm: float


class DeviceModel:
    def __init__(self, tech: Tech, temp_c: float | None = None) -> None:
        self.tech = tech
        self.temp_c = tech.temp_c if temp_c is None else temp_c
        self.cox_ff_um2 = cox_ff_per_um2(tech)
        self.overlap_factor = float(tech.model.get("device", {}).get("overlap_factor", 1.25))
        self.gate_leak_na_per_fin = float(
            tech.model.get("device", {}).get("gate_leak_na_per_fin", 0.12)
        )

    # -- helpers ----------------------------------------------------------
    def _p(self, polarity: str) -> Polarity:
        return self.tech.nfet if polarity == "n" else self.tech.pfet

    def vt_eff_v(self, polarity: str, vdd: float) -> float:
        p = self._p(polarity)
        return p.vt_v - p.dibl_mv_v * 1e-3 * vdd

    def cap_per_fin_ff(self, polarity: str) -> float:
        """Total gate capacitance of one fin, including overlap/fringe."""
        return (
            self.cox_ff_um2
            * self.tech.weff_per_fin_um
            * (self.tech.gate_length_nm / 1000.0)
            * self.overlap_factor
        )

    def ion_per_fin_ua(self, polarity: str, vdd: float) -> float:
        """Saturation current per fin at a given supply."""
        p = self._p(polarity)
        vt_ref = p.vt_v - p.dibl_mv_v * 1e-3 * self.tech.vdd_hp
        vt = self.vt_eff_v(polarity, vdd)
        overdrive = max(vdd - vt, 0.02)
        overdrive_ref = max(self.tech.vdd_hp - vt_ref, 0.02)
        scale = (overdrive / overdrive_ref) ** 1.1
        return p.ion_ua_per_um * self.tech.weff_per_fin_um * scale

    def ioff_per_fin_na(self, polarity: str, vdd: float) -> float:
        """Subthreshold plus gate leakage per fin at a given supply."""
        p = self._p(polarity)
        # Lower Vds raises Vt through DIBL, so leakage falls faster than V^2.
        dv = self.tech.vdd_hp - vdd
        dibl_shift = 10.0 ** (-(p.dibl_mv_v * dv) / p.ss_mv_dec)
        temp_shift = p.temp_ioff_factor ** ((self.temp_c - REF_TEMP_C) / 60.0)
        subthreshold = p.ioff_na_per_um * self.tech.weff_per_fin_um * dibl_shift * temp_shift
        return subthreshold + self.gate_leak_na_per_fin * temp_shift

    def ron_per_fin_ohm(self, polarity: str, vdd: float) -> float:
        ion_a = self.ion_per_fin_ua(polarity, vdd) * 1e-6
        return vdd / ion_a

    def point(self, polarity: str, nfins: int, vdd: float) -> DevicePoint:
        if nfins < 1:
            raise ValueError("nfins must be >= 1")
        return DevicePoint(
            polarity=polarity,
            vdd=vdd,
            nfins=nfins,
            weff_um=self.tech.weff_per_fin_um * nfins,
            ion_ua=self.ion_per_fin_ua(polarity, vdd) * nfins,
            ioff_na=self.ioff_per_fin_na(polarity, vdd) * nfins,
            cgg_ff=self.cap_per_fin_ff(polarity) * nfins,
            ron_ohm=self.ron_per_fin_ohm(polarity, vdd) / nfins,
        )

    def stage(
        self,
        nfins_n: int,
        nfins_p: int,
        vdd: float | None = None,
        coag: bool = False,
        stack_n: int = 1,
        stack_p: int = 1,
    ) -> StageMetrics:
        """Inverter-like stage: input drives nfins_n + nfins_p gate fingers.

        ``stack_n``/``stack_p`` let a cell report the current of a series stack;
        a 2-input NAND pulls down through two devices, so its effective drive is
        halved unless the fins are doubled.
        """
        vdd = self.tech.vdd_hp if vdd is None else vdd
        cin = self.cap_per_fin_ff("n") * nfins_n + self.cap_per_fin_ff("p") * nfins_p
        ion_n = self.ion_per_fin_ua("n", vdd) * nfins_n / max(stack_n, 1)
        ion_p = self.ion_per_fin_ua("p", vdd) * nfins_p / max(stack_p, 1)
        ion = min(ion_n, ion_p)  # the weaker side limits the transition
        ioff = (
            self.ioff_per_fin_na("n", vdd) * nfins_n
            + self.ioff_per_fin_na("p", vdd) * nfins_p
        )
        if ion <= 0:
            raise ValueError("no drive current")
        fo4 = 4.0 * cin * vdd / ion  # ns, because fF*V/uA = ns
        fo4 *= float(self.tech.model.get("fo4_parasitic_factor", 1.5))
        if coag:
            fo4 *= 1.0 - float(self.tech.model.get("coag_fo4_benefit", 0.0))
        return StageMetrics(
            vdd=vdd,
            nfins_n=nfins_n,
            nfins_p=nfins_p,
            cin_ff=cin,
            ion_ua=ion,
            ioff_na=ioff,
            ron_ohm=vdd / (ion * 1e-6),
            fo4_ps=fo4 * 1000.0,
        )

    def summary(self) -> dict[str, object]:
        return {
            "cox_ff_per_um2": round(self.cox_ff_um2, 2),
            "device_kind": self.tech.device_kind,
            "weff_per_unit_nm": round(self.tech.weff_per_fin_nm, 2),
            "cap_per_fin_ff": {
                "n": round(self.cap_per_fin_ff("n"), 4),
                "p": round(self.cap_per_fin_ff("p"), 4),
            },
            "ion_per_fin_ua": {
                "n": round(self.ion_per_fin_ua("n", self.tech.vdd_hp), 2),
                "p": round(self.ion_per_fin_ua("p", self.tech.vdd_hp), 2),
            },
            "ioff_per_fin_na_25c": {
                "n": round(self.ioff_per_fin_na("n", self.tech.vdd_hp), 4),
                "p": round(self.ioff_per_fin_na("p", self.tech.vdd_hp), 4),
            },
            "inverter_fo4_ps": round(self.stage(1, 1, self.tech.vdd_hp).fo4_ps, 2),
        }

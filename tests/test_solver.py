"""Tests for the AArch64 EL switching constraint solver."""

from __future__ import annotations

import pytest

from el_switch_solver.models import (
    ExceptionLevel,
    HCR_EL2,
    SCR_EL3,
    SPSR,
    SystemState,
)
from el_switch_solver.solver import solve, solve_all


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def state(
    el: int,
    *,
    el2: bool = True,
    el3: bool = True,
    scr_ns: int = 0,
    scr_smd: int = 0,
    scr_hce: int = 1,
    scr_eel2: int = 0,
    hcr_tge: int = 0,
    hcr_hcd: int = 0,
    hcr_e2h: int = 0,
    spsr_m: int = 0,
) -> SystemState:
    return SystemState(
        current_el=ExceptionLevel(el),
        el2_implemented=el2,
        el3_implemented=el3,
        scr_el3=SCR_EL3(
            ns=scr_ns, smd=scr_smd, hce=scr_hce, eel2=scr_eel2
        ),
        hcr_el2=HCR_EL2(tge=hcr_tge, hcd=hcr_hcd, e2h=hcr_e2h),
        spsr=SPSR(m=spsr_m),
    )


EL0 = ExceptionLevel.EL0
EL1 = ExceptionLevel.EL1
EL2 = ExceptionLevel.EL2
EL3 = ExceptionLevel.EL3


# ===========================================================================
# SVC
# ===========================================================================


class TestSVC:
    def test_el0_to_el1_default(self):
        """SVC at EL0 with EL2 present but TGE=0 → EL1."""
        r = solve("svc", state(0))
        assert r.is_valid
        assert r.target_el == EL1

    def test_el0_to_el1_no_el2(self):
        """SVC at EL0 with EL2 absent → EL1."""
        r = solve("svc", state(0, el2=False))
        assert r.is_valid
        assert r.target_el == EL1

    def test_el0_to_el2_tge(self):
        """SVC at EL0 with EL2 and TGE=1 → EL2."""
        r = solve("svc", state(0, hcr_tge=1))
        assert r.is_valid
        assert r.target_el == EL2

    def test_el0_tge_without_el2_goes_to_el1(self):
        """TGE=1 but EL2 not implemented → still EL1 (TGE has no effect)."""
        r = solve("svc", state(0, el2=False, hcr_tge=1))
        assert r.is_valid
        assert r.target_el == EL1

    def test_el1_not_a_switch(self):
        """SVC at EL1 is not an inter-level switch."""
        r = solve("svc", state(1))
        assert not r.is_valid

    def test_el2_not_a_switch(self):
        r = solve("svc", state(2))
        assert not r.is_valid

    def test_el3_not_a_switch(self):
        r = solve("svc", state(3))
        assert not r.is_valid

    def test_case_insensitive(self):
        r = solve("SVC", state(0))
        assert r.is_valid


# ===========================================================================
# HVC
# ===========================================================================


class TestHVC:
    def test_el1_to_el2_default(self):
        """HVC at EL1 with EL2/EL3 present and defaults → EL2."""
        r = solve("hvc", state(1))
        assert r.is_valid
        assert r.target_el == EL2

    def test_el1_no_el2(self):
        """HVC at EL1 when EL2 not implemented → invalid."""
        r = solve("hvc", state(1, el2=False))
        assert not r.is_valid
        names = [v.name for v in r.violations]
        assert any("EL2" in n for n in names)

    def test_el1_scr_hce_0(self):
        """HVC at EL1 when EL3 present and SCR_EL3.HCE=0 → invalid."""
        r = solve("hvc", state(1, scr_hce=0))
        assert not r.is_valid
        names = [v.name for v in r.violations]
        assert any("HCE" in n for n in names)

    def test_el1_hcr_hcd_1(self):
        """HVC at EL1 when HCR_EL2.HCD=1 → invalid."""
        r = solve("hvc", state(1, hcr_hcd=1))
        assert not r.is_valid
        names = [v.name for v in r.violations]
        assert any("HCD" in n for n in names)

    def test_el1_no_el3_hce_irrelevant(self):
        """HVC at EL1 when EL3 not implemented → HCE bit is irrelevant → valid."""
        r = solve("hvc", state(1, el3=False))
        assert r.is_valid
        assert r.target_el == EL2

    def test_el0_undef(self):
        """HVC at EL0 is always UNDEF."""
        r = solve("hvc", state(0))
        assert not r.is_valid

    def test_el2_no_switch(self):
        r = solve("hvc", state(2))
        assert not r.is_valid

    def test_el3_no_switch(self):
        r = solve("hvc", state(3))
        assert not r.is_valid

    def test_multiple_violations(self):
        """Both HCE=0 and HCD=1 are reported."""
        r = solve("hvc", state(1, scr_hce=0, hcr_hcd=1))
        assert not r.is_valid
        assert len(r.violations) >= 2


# ===========================================================================
# SMC
# ===========================================================================


class TestSMC:
    def test_el1_to_el3_default(self):
        """SMC at EL1 with EL3 present and SMD=0 → EL3."""
        r = solve("smc", state(1))
        assert r.is_valid
        assert r.target_el == EL3

    def test_el2_to_el3_default(self):
        """SMC at EL2 with EL3 present and SMD=0 → EL3."""
        r = solve("smc", state(2))
        assert r.is_valid
        assert r.target_el == EL3

    def test_el1_no_el3(self):
        """SMC at EL1 when EL3 not implemented → invalid."""
        r = solve("smc", state(1, el3=False))
        assert not r.is_valid
        names = [v.name for v in r.violations]
        assert any("EL3" in n for n in names)

    def test_el1_smd_1(self):
        """SMC at EL1 when SCR_EL3.SMD=1 → invalid."""
        r = solve("smc", state(1, scr_smd=1))
        assert not r.is_valid
        names = [v.name for v in r.violations]
        assert any("SMD" in n for n in names)

    def test_el0_undef(self):
        r = solve("smc", state(0))
        assert not r.is_valid

    def test_el3_nop(self):
        """SMC at EL3 is a NOP → invalid as an EL switch."""
        r = solve("smc", state(3))
        assert not r.is_valid


# ===========================================================================
# ERET
# ===========================================================================


class TestERET:
    # ---- EL1 → EL0 ----

    def test_el1_to_el0(self):
        """ERET from EL1 with SPSR.M=0 → EL0."""
        r = solve("eret", state(1, spsr_m=0))
        assert r.is_valid
        assert r.target_el == EL0

    def test_el1_spsr_el1_illegal(self):
        """ERET from EL1 with SPSR.M[3:2]=0b01 (EL1) → illegal same-level return."""
        r = solve("eret", state(1, spsr_m=0b0100))  # EL1t
        assert not r.is_valid

    def test_el1_spsr_el2_illegal(self):
        """ERET from EL1 to EL2 (higher level) → illegal."""
        r = solve("eret", state(1, spsr_m=0b1000))  # EL2t
        assert not r.is_valid

    # ---- EL2 → EL0/EL1 ----

    def test_el2_to_el0(self):
        """ERET from EL2 with SPSR.M=0 → EL0."""
        r = solve("eret", state(2, spsr_m=0))
        assert r.is_valid
        assert r.target_el == EL0

    def test_el2_to_el1(self):
        """ERET from EL2 with SPSR.M=4 (EL1t) → EL1."""
        r = solve("eret", state(2, spsr_m=0b0100))
        assert r.is_valid
        assert r.target_el == EL1

    def test_el2_to_el1h(self):
        """ERET from EL2 with SPSR.M=5 (EL1h) → EL1."""
        r = solve("eret", state(2, spsr_m=0b0101))
        assert r.is_valid
        assert r.target_el == EL1

    def test_el2_same_level_illegal(self):
        """ERET from EL2 with SPSR.M[3:2]=0b10 (EL2) → illegal same-level."""
        r = solve("eret", state(2, spsr_m=0b1000))  # EL2t
        assert not r.is_valid

    def test_el2_to_el3_illegal(self):
        """ERET from EL2 to EL3 (higher) → illegal."""
        r = solve("eret", state(2, spsr_m=0b1100))  # EL3t
        assert not r.is_valid

    # ---- EL3 → EL0/EL1/EL2 ----

    def test_el3_to_el0(self):
        """ERET from EL3 with SPSR.M=0 → EL0."""
        r = solve("eret", state(3, spsr_m=0))
        assert r.is_valid
        assert r.target_el == EL0

    def test_el3_to_el1(self):
        """ERET from EL3 with SPSR.M=4 (EL1t) → EL1."""
        r = solve("eret", state(3, spsr_m=0b0100))
        assert r.is_valid
        assert r.target_el == EL1

    def test_el3_to_el2_non_secure(self):
        """ERET from EL3 to EL2 with NS=1 → valid."""
        r = solve("eret", state(3, spsr_m=0b1000, scr_ns=1))
        assert r.is_valid
        assert r.target_el == EL2

    def test_el3_to_el2_secure_eel2(self):
        """ERET from EL3 to EL2 in Secure state but EEL2=1 → valid."""
        r = solve("eret", state(3, spsr_m=0b1000, scr_ns=0, scr_eel2=1))
        assert r.is_valid
        assert r.target_el == EL2

    def test_el3_to_el2_secure_no_eel2(self):
        """ERET from EL3 to EL2 in Secure state, EEL2=0 → invalid."""
        r = solve("eret", state(3, spsr_m=0b1000, scr_ns=0, scr_eel2=0))
        assert not r.is_valid
        names = [v.name for v in r.violations]
        assert any("Secure EL2" in n for n in names)

    def test_el3_to_el2_not_implemented(self):
        """ERET from EL3 to EL2 but EL2 not implemented → invalid."""
        r = solve("eret", state(3, el2=False, spsr_m=0b1000, scr_ns=1))
        assert not r.is_valid

    def test_el3_same_level_illegal(self):
        """ERET from EL3 with SPSR.M[3:2]=0b11 (EL3) → illegal."""
        r = solve("eret", state(3, spsr_m=0b1100))  # EL3t
        assert not r.is_valid

    def test_el0_undef(self):
        """ERET at EL0 is UNDEF."""
        r = solve("eret", state(0))
        assert not r.is_valid

    # ---- SPSR.M encodings ----

    def test_spsr_el1h(self):
        """SPSR.M=5 (EL1h) from EL2 → EL1."""
        r = solve("eret", state(2, spsr_m=5))
        assert r.is_valid
        assert r.target_el == EL1

    def test_spsr_el2h(self):
        """SPSR.M=9 (EL2h) from EL3 with NS=1 → EL2."""
        r = solve("eret", state(3, spsr_m=9, scr_ns=1))
        assert r.is_valid
        assert r.target_el == EL2


# ===========================================================================
# solve_all
# ===========================================================================


class TestSolveAll:
    def test_returns_four_results(self):
        results = solve_all(state(1))
        assert len(results) == 4

    def test_instructions_covered(self):
        results = solve_all(state(1))
        instrs = {r.instruction for r in results}
        assert instrs == {"svc", "hvc", "smc", "eret"}

    def test_el1_valid_switches(self):
        """From EL1 with defaults: HVC→EL2, SMC→EL3 should be valid."""
        results = solve_all(state(1))
        valid = {r.instruction: r.target_el for r in results if r.is_valid}
        assert valid.get("hvc") == EL2
        assert valid.get("smc") == EL3

    def test_el3_only_eret_valid(self):
        """From EL3 with SPSR pointing to EL1, only ERET should be valid."""
        results = solve_all(state(3, spsr_m=0b0100))
        valid = {r.instruction for r in results if r.is_valid}
        assert valid == {"eret"}


# ===========================================================================
# Invalid instruction name
# ===========================================================================


class TestSolveErrors:
    def test_unknown_instruction(self):
        with pytest.raises(ValueError, match="Unknown instruction"):
            solve("wfi", state(1))


# ===========================================================================
# Model validation
# ===========================================================================


class TestModels:
    def test_scr_el3_invalid_bit(self):
        with pytest.raises(ValueError):
            SCR_EL3(ns=2)

    def test_hcr_el2_invalid_bit(self):
        with pytest.raises(ValueError):
            HCR_EL2(tge=3)

    def test_spsr_invalid_m(self):
        with pytest.raises(ValueError):
            SPSR(m=16)

    def test_spsr_target_el(self):
        assert SPSR(m=0b0000).target_el == EL0
        assert SPSR(m=0b0100).target_el == EL1
        assert SPSR(m=0b1000).target_el == EL2
        assert SPSR(m=0b1100).target_el == EL3

"""Tests for the AArch64 EL switching constraint solver."""

from __future__ import annotations

import pytest

from el_switch_solver.models import (
    ExceptionLevel,
    HCR_EL2,
    SCR_EL3,
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
    hcr_tsc: int = 0,
    hcr_tge: int = 0,
    hcr_hcd: int = 0,
    hcr_e2h: int = 0,
) -> SystemState:
    return SystemState(
        current_el=ExceptionLevel(el),
        el2_implemented=el2,
        el3_implemented=el3,
        scr_el3=SCR_EL3(
            ns=scr_ns, smd=scr_smd, hce=scr_hce, eel2=scr_eel2
        ),
        hcr_el2=HCR_EL2(
            tsc=hcr_tsc, tge=hcr_tge, hcd=hcr_hcd, e2h=hcr_e2h
        ),
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

    def test_el1_vhe_host_mode_undef(self):
        """HVC at EL1 in VHE host mode (E2H=1, TGE=1) → UNDEFINED."""
        r = solve("hvc", state(1, hcr_e2h=1, hcr_tge=1))
        assert not r.is_valid
        names = [v.name for v in r.violations]
        assert any("VHE" in n or "E2H" in n for n in names)

    def test_el1_e2h_only_not_undef(self):
        """E2H=1 but TGE=0 → NOT VHE host mode; HVC is still valid."""
        r = solve("hvc", state(1, hcr_e2h=1, hcr_tge=0))
        assert r.is_valid
        assert r.target_el == EL2

    def test_el1_tge_only_not_undef(self):
        """TGE=1 but E2H=0 → NOT VHE host mode; HVC is still valid."""
        r = solve("hvc", state(1, hcr_e2h=0, hcr_tge=1))
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

    def test_vhe_host_mode_and_no_el2_both_violations(self):
        """E2H=1, TGE=1, but EL2 not implemented: EL2-absent violation reported."""
        r = solve("hvc", state(1, el2=False, hcr_e2h=1, hcr_tge=1))
        assert not r.is_valid
        names = [v.name for v in r.violations]
        assert any("EL2" in n for n in names)


# ===========================================================================
# SMC
# ===========================================================================


class TestSMC:
    def test_el1_to_el3_default(self):
        """SMC at EL1 with EL3 present, SMD=0, TSC=0 → EL3."""
        r = solve("smc", state(1))
        assert r.is_valid
        assert r.target_el == EL3

    def test_el2_to_el3_default(self):
        """SMC at EL2 with EL3 present and SMD=0 → EL3."""
        r = solve("smc", state(2))
        assert r.is_valid
        assert r.target_el == EL3

    def test_el1_no_el3(self):
        """SMC at EL1 when EL3 not implemented, TSC=0 → invalid."""
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

    def test_el1_tsc_1_non_secure_traps_to_el2(self):
        """SMC at EL1 with TSC=1, Non-Secure (no EL3) → trapped to EL2."""
        r = solve("smc", state(1, el3=False, hcr_tsc=1))
        assert r.is_valid
        assert r.target_el == EL2

    def test_el1_tsc_1_non_secure_with_el3_traps_to_el2(self):
        """SMC at EL1 with TSC=1, NS=1 (Non-Secure) → trapped to EL2."""
        r = solve("smc", state(1, scr_ns=1, hcr_tsc=1))
        assert r.is_valid
        assert r.target_el == EL2

    def test_el1_tsc_1_secure_state_goes_to_el3(self):
        """SMC at EL1 with TSC=1 but Secure state (NS=0, EL3 present) → EL3 (TSC inactive in Secure)."""
        r = solve("smc", state(1, scr_ns=0, scr_smd=0, hcr_tsc=1))
        assert r.is_valid
        assert r.target_el == EL3

    def test_el1_tsc_1_vhe_host_mode_goes_to_el3(self):
        """SMC at EL1 with TSC=1 in VHE host mode → EL3 (TSC inactive in VHE host)."""
        r = solve("smc", state(1, scr_ns=1, hcr_tsc=1, hcr_e2h=1, hcr_tge=1))
        assert r.is_valid
        assert r.target_el == EL3

    def test_el2_tsc_does_not_apply(self):
        """TSC does not trap SMC from EL2 (TSC is EL1-only); EL2 still goes to EL3."""
        r = solve("smc", state(2, hcr_tsc=1))
        assert r.is_valid
        assert r.target_el == EL3

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
    def test_el0_undef(self):
        """ERET at EL0 is UNDEF."""
        r = solve("eret", state(0))
        assert not r.is_valid
        assert r.valid_targets == []

    def test_el1_targets_only_el0(self):
        """ERET from EL1 can only return to EL0."""
        r = solve("eret", state(1))
        assert r.is_valid
        assert r.valid_targets == [EL0]
        assert r.target_el == EL0  # single-element convenience

    def test_el2_targets_el0_and_el1(self):
        """ERET from EL2 can return to EL0 or EL1."""
        r = solve("eret", state(2))
        assert r.is_valid
        assert set(r.valid_targets) == {EL0, EL1}

    def test_el3_secure_no_eel2_no_el2(self):
        """ERET from EL3 in Secure state without EEL2 → EL0 and EL1 only."""
        r = solve("eret", state(3, scr_ns=0, scr_eel2=0))
        assert r.is_valid
        assert EL2 not in r.valid_targets
        assert EL0 in r.valid_targets
        assert EL1 in r.valid_targets

    def test_el3_non_secure_includes_el2(self):
        """ERET from EL3 with NS=1 → EL0, EL1, and EL2."""
        r = solve("eret", state(3, scr_ns=1))
        assert r.is_valid
        assert set(r.valid_targets) == {EL0, EL1, EL2}

    def test_el3_secure_eel2_includes_el2(self):
        """ERET from EL3 in Secure state with EEL2=1 → EL0, EL1, and EL2."""
        r = solve("eret", state(3, scr_ns=0, scr_eel2=1))
        assert r.is_valid
        assert set(r.valid_targets) == {EL0, EL1, EL2}

    def test_el3_no_el2_excludes_el2(self):
        """ERET from EL3 when EL2 is not implemented → EL0 and EL1 only."""
        r = solve("eret", state(3, el2=False, scr_ns=1))
        assert r.is_valid
        assert EL2 not in r.valid_targets
        assert EL0 in r.valid_targets
        assert EL1 in r.valid_targets

    def test_el3_secure_no_eel2_violation_reported(self):
        """ERET from EL3 Secure without EEL2: violation is reported for EL2."""
        r = solve("eret", state(3, scr_ns=0, scr_eel2=0))
        assert r.violations  # EL2 not reachable violation
        names = [v.name for v in r.violations]
        assert any("EL2" in n for n in names)

    def test_el3_target_el_none_for_multiple(self):
        """target_el is None when there are multiple valid targets."""
        r = solve("eret", state(3, scr_ns=1))
        assert len(r.valid_targets) > 1
        assert r.target_el is None


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
        """From EL1 with defaults: HVC→EL2, SMC→EL3, ERET→EL0 should be valid."""
        results = solve_all(state(1))
        valid = {r.instruction: r for r in results if r.is_valid}
        assert valid["hvc"].target_el == EL2
        assert valid["smc"].target_el == EL3
        assert EL0 in valid["eret"].valid_targets

    def test_el3_valid_switches(self):
        """From EL3 (default Secure state, EL2 present): ERET reaches EL0 and EL1."""
        results = solve_all(state(3))
        eret_result = next(r for r in results if r.instruction == "eret")
        assert eret_result.is_valid
        assert EL0 in eret_result.valid_targets
        assert EL1 in eret_result.valid_targets
        assert EL2 not in eret_result.valid_targets  # Secure, no EEL2

    def test_el3_non_secure_eret_includes_el2(self):
        """From EL3 in Non-Secure state: ERET can also reach EL2."""
        results = solve_all(state(3, scr_ns=1))
        eret_result = next(r for r in results if r.instruction == "eret")
        assert EL2 in eret_result.valid_targets


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

    def test_hcr_el2_tsc_validated(self):
        with pytest.raises(ValueError):
            HCR_EL2(tsc=2)

    def test_hcr_el2_e2h_validated(self):
        with pytest.raises(ValueError):
            HCR_EL2(e2h=5)


# ===========================================================================
# SwitchResult properties
# ===========================================================================


class TestSwitchResult:
    def test_is_valid_empty_targets(self):
        r = solve("hvc", state(0))
        assert not r.is_valid
        assert r.valid_targets == []

    def test_target_el_single(self):
        r = solve("hvc", state(1))
        assert r.target_el == EL2

    def test_target_el_none_for_multiple(self):
        r = solve("eret", state(2))
        assert len(r.valid_targets) == 2
        assert r.target_el is None  # multiple targets → None

    def test_str_valid_single(self):
        r = solve("smc", state(1))
        s = str(r)
        assert "[VALID]" in s
        assert "EL3" in s

    def test_str_invalid(self):
        r = solve("hvc", state(0))
        s = str(r)
        assert "[INVALID]" in s

    def test_str_valid_multiple_targets(self):
        r = solve("eret", state(3, scr_ns=1))
        s = str(r)
        assert "[VALID]" in s
        assert "EL2" in s


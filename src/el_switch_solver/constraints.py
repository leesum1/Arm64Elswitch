"""Constraint evaluation for each AArch64 EL-switching instruction.

Each public function accepts a :class:`~el_switch_solver.models.SystemState`
and returns a :class:`~el_switch_solver.models.SwitchResult` that describes
whether the requested EL switch is architecturally legal and, if not, which
constraints were violated.

Reference: Arm Architecture Reference Manual for A-profile architecture
           (DDI 0487), Chapter D1 (System-level architecture).
"""

from __future__ import annotations

from .models import (
    ConstraintViolation,
    ExceptionLevel,
    Instruction,
    SwitchResult,
    SystemState,
)


# ---------------------------------------------------------------------------
# SVC
# ---------------------------------------------------------------------------


def check_svc(state: SystemState) -> SwitchResult:
    """Evaluate ``SVC`` executed at ``state.current_el``.

    SVC causes a synchronous exception routed to EL1 or EL2:

    * At **EL0**: routed to EL2 when EL2 is implemented and
      ``HCR_EL2.TGE = 1``; otherwise routed to EL1.
    * At **EL1** and above: the exception stays at the same level; this is
      *not* an inter-level switch and is therefore reported as invalid here.
    """
    el = state.current_el

    if el != ExceptionLevel.EL0:
        return SwitchResult(
            instruction=Instruction.SVC,
            current_el=el,
            target_el=None,
            is_valid=False,
            reason=(
                f"SVC at {el} does not change the exception level "
                "(exception is taken at the current EL)."
            ),
        )

    # EL0 path
    if state.el2_implemented and state.hcr_el2.tge == 1:
        return SwitchResult(
            instruction=Instruction.SVC,
            current_el=el,
            target_el=ExceptionLevel.EL2,
            is_valid=True,
            reason=(
                "EL2 is implemented and HCR_EL2.TGE=1 → "
                "SVC from EL0 is routed to EL2."
            ),
        )

    return SwitchResult(
        instruction=Instruction.SVC,
        current_el=el,
        target_el=ExceptionLevel.EL1,
        is_valid=True,
        reason=(
            "EL2 not implemented or HCR_EL2.TGE=0 → "
            "SVC from EL0 is routed to EL1."
        ),
    )


# ---------------------------------------------------------------------------
# HVC
# ---------------------------------------------------------------------------


def check_hvc(state: SystemState) -> SwitchResult:
    """Evaluate ``HVC`` executed at ``state.current_el``.

    HVC from EL1 causes a synchronous exception to EL2 when all three
    conditions below hold:

    1. EL2 is implemented.
    2. EL3 is not implemented **or** ``SCR_EL3.HCE = 1``.
    3. ``HCR_EL2.HCD = 0``.

    HVC from EL0 is always UNDEFINED.
    HVC from EL2/EL3 does not change the exception level.
    """
    el = state.current_el
    instr = Instruction.HVC

    if el == ExceptionLevel.EL0:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            target_el=None,
            is_valid=False,
            reason="HVC at EL0 is architecturally UNDEFINED.",
            violations=[
                ConstraintViolation(
                    "EL0 restriction",
                    "HVC may only be executed at EL1 or above.",
                )
            ],
        )

    if el != ExceptionLevel.EL1:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            target_el=None,
            is_valid=False,
            reason=(
                f"HVC at {el} does not perform an inter-level switch "
                "(exception is taken at the current EL or is a NOP)."
            ),
        )

    # EL1 path — collect all violations
    violations: list[ConstraintViolation] = []

    if not state.el2_implemented:
        violations.append(
            ConstraintViolation(
                "EL2 not implemented",
                "HVC requires EL2 to be implemented.",
            )
        )

    if state.el3_implemented and state.scr_el3.hce == 0:
        violations.append(
            ConstraintViolation(
                "SCR_EL3.HCE=0",
                "EL3 is implemented and SCR_EL3.HCE=0 disables HVC from EL1.",
            )
        )

    if state.el2_implemented and state.hcr_el2.hcd == 1:
        violations.append(
            ConstraintViolation(
                "HCR_EL2.HCD=1",
                "HCR_EL2.HCD=1 traps HVC to EL3 or causes UNDEF; "
                "EL2 is not reached.",
            )
        )

    if violations:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            target_el=None,
            is_valid=False,
            reason="HVC from EL1 to EL2 is blocked by one or more constraints.",
            violations=violations,
        )

    return SwitchResult(
        instruction=instr,
        current_el=el,
        target_el=ExceptionLevel.EL2,
        is_valid=True,
        reason=(
            "EL2 implemented, SCR_EL3.HCE=1 (or EL3 absent), "
            "and HCR_EL2.HCD=0 → HVC from EL1 reaches EL2."
        ),
    )


# ---------------------------------------------------------------------------
# SMC
# ---------------------------------------------------------------------------


def check_smc(state: SystemState) -> SwitchResult:
    """Evaluate ``SMC`` executed at ``state.current_el``.

    SMC from EL1 or EL2 causes a synchronous exception to EL3 when:

    1. EL3 is implemented.
    2. ``SCR_EL3.SMD = 0``.

    SMC from EL0 is always UNDEFINED.
    SMC from EL3 is treated as a NOP (no EL change).
    """
    el = state.current_el
    instr = Instruction.SMC

    if el == ExceptionLevel.EL0:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            target_el=None,
            is_valid=False,
            reason="SMC at EL0 is architecturally UNDEFINED.",
            violations=[
                ConstraintViolation(
                    "EL0 restriction",
                    "SMC may only be executed at EL1 or EL2.",
                )
            ],
        )

    if el == ExceptionLevel.EL3:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            target_el=None,
            is_valid=False,
            reason="SMC at EL3 is a NOP (no exception level change).",
        )

    # EL1 or EL2 path
    violations: list[ConstraintViolation] = []

    if not state.el3_implemented:
        violations.append(
            ConstraintViolation(
                "EL3 not implemented",
                "SMC requires EL3 to be implemented.",
            )
        )

    if state.el3_implemented and state.scr_el3.smd == 1:
        violations.append(
            ConstraintViolation(
                "SCR_EL3.SMD=1",
                "SCR_EL3.SMD=1 disables SMC (UNDEF or trapped).",
            )
        )

    if violations:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            target_el=None,
            is_valid=False,
            reason=f"SMC from {el} to EL3 is blocked by one or more constraints.",
            violations=violations,
        )

    return SwitchResult(
        instruction=instr,
        current_el=el,
        target_el=ExceptionLevel.EL3,
        is_valid=True,
        reason=(
            f"EL3 implemented and SCR_EL3.SMD=0 → "
            f"SMC from {el} reaches EL3."
        ),
    )


# ---------------------------------------------------------------------------
# ERET
# ---------------------------------------------------------------------------


def check_eret(state: SystemState) -> SwitchResult:
    """Evaluate ``ERET`` executed at ``state.current_el``.

    ERET returns to the exception level encoded in ``SPSR_ELn.M[3:2]``.
    The target EL must be *strictly lower* than the current EL (same-level
    return is architecturally reserved/illegal).

    Additional constraint for ERET from EL3 to EL2:
      EL2 must be implemented and accessible in the current security state:
      ``SCR_EL3.NS = 1`` (Non-Secure EL2) **or** ``SCR_EL3.EEL2 = 1``
      (Secure EL2 extension enabled).
    """
    el = state.current_el
    instr = Instruction.ERET

    if el == ExceptionLevel.EL0:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            target_el=None,
            is_valid=False,
            reason="ERET at EL0 is architecturally UNDEFINED.",
            violations=[
                ConstraintViolation(
                    "EL0 restriction",
                    "ERET may only be executed at EL1, EL2, or EL3.",
                )
            ],
        )

    target_el = state.spsr.target_el
    violations: list[ConstraintViolation] = []

    # Target must be strictly lower than current EL.
    if target_el >= el:
        violations.append(
            ConstraintViolation(
                "Illegal exception return level",
                f"SPSR_EL{el.value}.M[3:2]={target_el.value} encodes {target_el}, "
                f"which is >= current {el}. ERET cannot return to the same "
                "or a higher exception level.",
            )
        )
        return SwitchResult(
            instruction=instr,
            current_el=el,
            target_el=None,
            is_valid=False,
            reason=(
                f"SPSR_EL{el.value} encodes {target_el} which is not "
                f"below current {el}."
            ),
            violations=violations,
        )

    # Additional check: ERET from EL3 to EL2
    if el == ExceptionLevel.EL3 and target_el == ExceptionLevel.EL2:
        if not state.el2_implemented:
            violations.append(
                ConstraintViolation(
                    "EL2 not implemented",
                    "Cannot ERET to EL2 when EL2 is not implemented.",
                )
            )
        else:
            # EL2 must be accessible for the current security state.
            ns = state.scr_el3.ns
            eel2 = state.scr_el3.eel2
            if ns == 0 and eel2 == 0:
                violations.append(
                    ConstraintViolation(
                        "Secure EL2 not enabled",
                        "SCR_EL3.NS=0 (Secure state) and SCR_EL3.EEL2=0. "
                        "EL2 is not available in Secure state. "
                        "Set SCR_EL3.NS=1 (Non-Secure) or "
                        "SCR_EL3.EEL2=1 (Secure EL2 extension).",
                    )
                )

    # ERET from EL2 to EL0: EL0 is always present, no extra checks needed.
    # ERET from EL2 to EL1: EL1 is always present, no extra checks needed.
    # ERET from EL1 to EL0: EL0 is always present, no extra checks needed.

    if violations:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            target_el=None,
            is_valid=False,
            reason=(
                f"ERET from {el} to {target_el} is blocked "
                "by one or more constraints."
            ),
            violations=violations,
        )

    return SwitchResult(
        instruction=instr,
        current_el=el,
        target_el=target_el,
        is_valid=True,
        reason=(
            f"SPSR_EL{el.value}.M[3:2]={target_el.value} is valid → "
            f"ERET from {el} returns to {target_el}."
        ),
    )

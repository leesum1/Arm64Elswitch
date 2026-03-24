"""Constraint evaluation for each AArch64 EL-switching instruction.

Each public function accepts a :class:`~el_switch_solver.models.SystemState`
and returns a :class:`~el_switch_solver.models.SwitchResult` that lists all
architecturally legal target ELs and describes any constraint violations.

SPSR_ELn is intentionally excluded from all checks: it is software-controlled
and therefore not an architectural constraint.  The solver enumerates every EL
that is reachable given the *hardware* register state; the caller must then
configure SPSR_ELn to match the desired target.

Reference: Arm Architecture Reference Manual for A-profile architecture
           (DDI 0487), Sections D1.10–D1.14.
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
# Internal helpers
# ---------------------------------------------------------------------------


def _is_non_secure(state: SystemState) -> bool:
    """Return True when lower ELs are in Non-Secure state.

    The processor is Non-Secure when EL3 is not implemented (there is only
    one security world) or when SCR_EL3.NS = 1.
    """
    return not state.el3_implemented or state.scr_el3.ns == 1


def _is_vhe_host_mode(state: SystemState) -> bool:
    """Return True when the VHE host mode is active (E2H=1 AND TGE=1).

    In this mode the hypervisor host OS runs directly at EL2 and exceptions
    from lower ELs are routed differently.  Several HCR_EL2 bits (e.g. TSC)
    are inactive in this mode.
    """
    return (
        state.el2_implemented
        and state.hcr_el2.e2h == 1
        and state.hcr_el2.tge == 1
    )


# ---------------------------------------------------------------------------
# SVC
# ---------------------------------------------------------------------------


def check_svc(state: SystemState) -> SwitchResult:
    """Evaluate ``SVC`` executed at ``state.current_el``.

    Routing rules (DDI 0487 D1.10.1):

    * **EL0 → EL2**: EL2 is implemented AND ``HCR_EL2.TGE = 1``.
      Regardless of security state: TGE routes *all* EL0 exceptions to EL2.
    * **EL0 → EL1**: otherwise (EL2 absent or ``HCR_EL2.TGE = 0``).
    * **EL1 and above**: SVC is taken at the *current* EL (not an inter-level
      switch) and is therefore out of scope.
    """
    el = state.current_el

    if el != ExceptionLevel.EL0:
        return SwitchResult(
            instruction=Instruction.SVC,
            current_el=el,
            valid_targets=[],
            reason=(
                f"SVC at {el} causes a same-level exception and does not "
                "change the exception level."
            ),
        )

    # EL0 path: TGE wins over everything else when EL2 is present.
    if state.el2_implemented and state.hcr_el2.tge == 1:
        return SwitchResult(
            instruction=Instruction.SVC,
            current_el=el,
            valid_targets=[ExceptionLevel.EL2],
            reason=(
                "EL2 implemented and HCR_EL2.TGE=1 → "
                "SVC from EL0 is routed to EL2."
            ),
        )

    return SwitchResult(
        instruction=Instruction.SVC,
        current_el=el,
        valid_targets=[ExceptionLevel.EL1],
        reason=(
            "HCR_EL2.TGE=0 (or EL2 absent) → "
            "SVC from EL0 is routed to EL1."
        ),
    )


# ---------------------------------------------------------------------------
# HVC
# ---------------------------------------------------------------------------


def check_hvc(state: SystemState) -> SwitchResult:
    """Evaluate ``HVC`` executed at ``state.current_el``.

    Routing rules (DDI 0487 D1.14.9):

    **EL0**: always UNDEFINED.

    **EL1 → EL2**: all four conditions below must hold:

    1. EL2 is implemented.
    2. ``HCR_EL2.E2H = 0`` OR ``HCR_EL2.TGE = 0`` — in VHE host mode
       (E2H=1, TGE=1) HVC from EL1 is UNDEFINED.
    3. EL3 not implemented, **OR** ``SCR_EL3.HCE = 1`` — when EL3 is
       present, HCE must enable the instruction.
    4. ``HCR_EL2.HCD = 0`` — the HVC-disable bit must be clear.

    **EL2 / EL3**: HVC causes a same-level exception or is a NOP;
    no inter-level switch occurs.

    Note: there is **no** field named ``SCR_EL3.HCR``; the relevant
    SCR_EL3 bit for HVC enablement is ``HCE`` (bit 8).
    """
    el = state.current_el
    instr = Instruction.HVC

    if el == ExceptionLevel.EL0:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            valid_targets=[],
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
            valid_targets=[],
            reason=(
                f"HVC at {el} causes a same-level exception or is a NOP; "
                "no inter-level switch occurs."
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

    if state.el2_implemented and _is_vhe_host_mode(state):
        violations.append(
            ConstraintViolation(
                "VHE host mode (HCR_EL2.E2H=1, HCR_EL2.TGE=1)",
                "In VHE host mode HVC from EL1 is architecturally UNDEFINED.",
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
                "HCR_EL2.HCD=1 disables HVC from EL1 (trapped to EL3 or UNDEF).",
            )
        )

    if violations:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            valid_targets=[],
            reason="HVC from EL1 to EL2 is blocked by one or more constraints.",
            violations=violations,
        )

    return SwitchResult(
        instruction=instr,
        current_el=el,
        valid_targets=[ExceptionLevel.EL2],
        reason=(
            "EL2 implemented, not in VHE host mode, "
            "SCR_EL3.HCE=1 (or EL3 absent), HCR_EL2.HCD=0 → "
            "HVC from EL1 reaches EL2."
        ),
    )


# ---------------------------------------------------------------------------
# SMC
# ---------------------------------------------------------------------------


def check_smc(state: SystemState) -> SwitchResult:
    """Evaluate ``SMC`` executed at ``state.current_el``.

    Routing rules (DDI 0487 D1.14.10):

    **EL0**: always UNDEFINED.

    **EL1 → EL2 (trap via TSC)**:
      ``HCR_EL2.TSC = 1`` AND EL2 is implemented AND in Non-Secure state
      (SCR_EL3.NS=1 or EL3 absent) AND NOT in VHE host mode (E2H=0 or TGE=0).
      This trap takes priority over the EL3 path below.

    **EL1 → EL3**:
      ``HCR_EL2.TSC = 0`` (or TSC inactive) AND EL3 is implemented
      AND ``SCR_EL3.SMD = 0``.

    **EL2 → EL3**:
      EL3 is implemented AND ``SCR_EL3.SMD = 0``.
      (TSC applies only to EL1 execution, not EL2.)

    **EL3**: SMC is a NOP (no exception level change).

    Note: ``HCR_EL2.DC`` (Default Cacheability, bit 12) controls stage-2
    translation cacheability and has **no effect** on exception routing.
    """
    el = state.current_el
    instr = Instruction.SMC

    if el == ExceptionLevel.EL0:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            valid_targets=[],
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
            valid_targets=[],
            reason="SMC at EL3 is a NOP (no exception level change).",
        )

    if el == ExceptionLevel.EL1:
        non_secure = _is_non_secure(state)
        vhe_host = _is_vhe_host_mode(state)

        # TSC trap path (EL1 only, Non-Secure, not VHE host mode).
        tsc_active = (
            state.el2_implemented
            and state.hcr_el2.tsc == 1
            and non_secure
            and not vhe_host
        )
        if tsc_active:
            return SwitchResult(
                instruction=instr,
                current_el=el,
                valid_targets=[ExceptionLevel.EL2],
                reason=(
                    "HCR_EL2.TSC=1 in Non-Secure state (and not VHE host mode) → "
                    "SMC from EL1 is trapped to EL2."
                ),
            )

        # Normal EL3 path.
        violations: list[ConstraintViolation] = []

        if not state.el3_implemented:
            violations.append(
                ConstraintViolation(
                    "EL3 not implemented",
                    "SMC requires EL3 to be implemented "
                    "(and HCR_EL2.TSC=0 or inactive).",
                )
            )

        if state.el3_implemented and state.scr_el3.smd == 1:
            violations.append(
                ConstraintViolation(
                    "SCR_EL3.SMD=1",
                    "SCR_EL3.SMD=1 disables SMC from EL1 (UNDEF).",
                )
            )

        if violations:
            return SwitchResult(
                instruction=instr,
                current_el=el,
                valid_targets=[],
                reason="SMC from EL1 to EL3 is blocked by one or more constraints.",
                violations=violations,
            )

        return SwitchResult(
            instruction=instr,
            current_el=el,
            valid_targets=[ExceptionLevel.EL3],
            reason=(
                "EL3 implemented, SCR_EL3.SMD=0, HCR_EL2.TSC=0 (or inactive) → "
                "SMC from EL1 reaches EL3."
            ),
        )

    # EL2 → EL3 path (TSC does not apply to EL2 execution).
    violations = []

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
                "SCR_EL3.SMD=1 disables SMC from EL2 (UNDEF).",
            )
        )

    if violations:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            valid_targets=[],
            reason="SMC from EL2 to EL3 is blocked by one or more constraints.",
            violations=violations,
        )

    return SwitchResult(
        instruction=instr,
        current_el=el,
        valid_targets=[ExceptionLevel.EL3],
        reason=(
            "EL3 implemented and SCR_EL3.SMD=0 → "
            "SMC from EL2 reaches EL3."
        ),
    )


# ---------------------------------------------------------------------------
# ERET
# ---------------------------------------------------------------------------


def check_eret(state: SystemState) -> SwitchResult:
    """Evaluate ``ERET`` executed at ``state.current_el``.

    ERET restores execution to the EL encoded in ``SPSR_ELn.M[3:2]``.
    Because SPSR is software-controlled (the caller sets it), this function
    reports **all** ELs that are architecturally reachable, letting the caller
    choose the actual target by configuring SPSR_ELn appropriately.

    Reachability rules (DDI 0487 D1.11.1):

    * **EL0**: UNDEFINED.
    * **EL1**: can return to EL0 (always valid).
    * **EL2**: can return to EL0 or EL1 (both always valid).
    * **EL3**: can return to EL0 or EL1 (always valid).  EL2 is also
      reachable when EL2 is implemented AND (``SCR_EL3.NS = 1`` **or**
      ``SCR_EL3.EEL2 = 1``).
    """
    el = state.current_el
    instr = Instruction.ERET

    if el == ExceptionLevel.EL0:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            valid_targets=[],
            reason="ERET at EL0 is architecturally UNDEFINED.",
            violations=[
                ConstraintViolation(
                    "EL0 restriction",
                    "ERET may only be executed at EL1, EL2, or EL3.",
                )
            ],
        )

    if el == ExceptionLevel.EL1:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            valid_targets=[ExceptionLevel.EL0],
            reason=(
                "ERET from EL1 can return to EL0. "
                "Set SPSR_EL1.M[3:0]=0b0000 (EL0t) or 0b0000 (EL0) before ERET."
            ),
        )

    if el == ExceptionLevel.EL2:
        return SwitchResult(
            instruction=instr,
            current_el=el,
            valid_targets=[ExceptionLevel.EL0, ExceptionLevel.EL1],
            reason=(
                "ERET from EL2 can return to EL0 or EL1. "
                "Set SPSR_EL2.M[3:2]=0b00 (EL0) or 0b01 (EL1) before ERET."
            ),
        )

    # EL3 path
    valid_targets: list[ExceptionLevel] = [ExceptionLevel.EL0, ExceptionLevel.EL1]
    el2_notes: list[str] = []

    if not state.el2_implemented:
        el2_notes.append("EL2 is not implemented")
    elif state.scr_el3.ns == 0 and state.scr_el3.eel2 == 0:
        el2_notes.append(
            "SCR_EL3.NS=0 (Secure state) and SCR_EL3.EEL2=0: "
            "Secure EL2 is not enabled. "
            "Set SCR_EL3.NS=1 (Non-Secure) or SCR_EL3.EEL2=1 (ARMv8.4-SecEL2) "
            "to make EL2 reachable."
        )
    else:
        valid_targets.append(ExceptionLevel.EL2)

    parts = [
        f"ERET from EL3 can return to: "
        f"{', '.join(str(t) for t in valid_targets)}."
    ]
    if el2_notes:
        parts.append(f"EL2 not reachable: {el2_notes[0]}.")
    else:
        parts.append(
            "EL2 reachable: EL2 implemented and accessible in current security state."
        )

    violations = (
        [ConstraintViolation("EL2 not reachable from EL3", el2_notes[0])]
        if el2_notes
        else []
    )

    return SwitchResult(
        instruction=instr,
        current_el=el,
        valid_targets=valid_targets,
        reason=" ".join(parts),
        violations=violations,
    )


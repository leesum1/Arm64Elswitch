"""Main solver and CLI entry-point for the AArch64 EL-switching solver.

Usage (after installing with ``uv``):

.. code-block:: console

   # Check whether HVC from EL1 can reach EL2
   el-switch --el 1 --instr hvc

   # HVC from EL1 in VHE host mode (E2H=1, TGE=1) → UNDEF
   el-switch --el 1 --instr hvc --hcr-e2h 1 --hcr-tge 1

   # SMC from EL1: TSC=1 traps to EL2 instead of EL3
   el-switch --el 1 --instr smc --hcr-tsc 1

   # ERET from EL3 — enumerate all reachable ELs (Non-Secure world)
   el-switch --el 3 --instr eret --scr-ns 1

   # Enumerate all valid switches from EL1
   el-switch --el 1 --all

Alternatively import and use the Python API directly:

.. code-block:: python

   from el_switch_solver.models import (
       ExceptionLevel, HCR_EL2, SCR_EL3, SystemState,
   )
   from el_switch_solver.solver import solve, solve_all

   state = SystemState(
       current_el=ExceptionLevel.EL1,
       el2_implemented=True,
       el3_implemented=True,
       scr_el3=SCR_EL3(hce=1),
       hcr_el2=HCR_EL2(hcd=0, tsc=0),
   )
   result = solve("hvc", state)
   print(result)
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable

from .constraints import check_eret, check_hvc, check_smc, check_svc
from .models import (
    ExceptionLevel,
    HCR_EL2,
    Instruction,
    SCR_EL3,
    SwitchResult,
    SystemState,
)

_CHECKERS: dict[str, Callable[[SystemState], SwitchResult]] = {
    Instruction.SVC: check_svc,
    Instruction.HVC: check_hvc,
    Instruction.SMC: check_smc,
    Instruction.ERET: check_eret,
}


def solve(instruction: str, state: SystemState) -> SwitchResult:
    """Evaluate whether ``instruction`` is a legal EL switch from ``state``.

    Parameters
    ----------
    instruction:
        One of ``"svc"``, ``"hvc"``, ``"smc"``, ``"eret"`` (case-insensitive).
    state:
        The complete system state (current EL, register values, …).

    Returns
    -------
    SwitchResult
        ``valid_targets`` lists all architecturally reachable destination ELs.
        For SVC/HVC/SMC this is at most one EL (routing is deterministic).
        For ERET it may be multiple ELs (SPSR_ELn selects the actual target).

    Raises
    ------
    ValueError
        If ``instruction`` is not one of the four supported instructions.
    """
    key = instruction.lower()
    if key not in _CHECKERS:
        raise ValueError(
            f"Unknown instruction '{instruction}'. "
            f"Must be one of: {', '.join(sorted(_CHECKERS))}."
        )
    return _CHECKERS[key](state)


def solve_all(state: SystemState) -> list[SwitchResult]:
    """Evaluate all four instructions for ``state``.

    Returns a list of :class:`~el_switch_solver.models.SwitchResult` objects,
    one per instruction.
    """
    return [_CHECKERS[instr](state) for instr in Instruction.ALL]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="el-switch",
        description=(
            "AArch64 Exception Level switching constraint solver.\n\n"
            "Evaluates which ELs are architecturally reachable from the "
            "current exception level via SVC/HVC/SMC/ERET, "
            "given the current system register values.\n\n"
            "SPSR_ELn is intentionally excluded: it is software-controlled "
            "and does not constrain reachability."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--el",
        type=int,
        choices=[0, 1, 2, 3],
        required=True,
        metavar="N",
        help="Current exception level (0–3).",
    )
    parser.add_argument(
        "--instr",
        choices=[*Instruction.ALL, "all"],
        default="all",
        metavar="INSTR",
        help=(
            "Instruction to evaluate: svc, hvc, smc, eret, or 'all' "
            "(default: all)."
        ),
    )

    # Optional EL presence flags
    parser.add_argument(
        "--no-el2",
        action="store_true",
        help="EL2 is NOT implemented on this processor.",
    )
    parser.add_argument(
        "--no-el3",
        action="store_true",
        help="EL3 is NOT implemented on this processor.",
    )

    # SCR_EL3 bits
    scr = parser.add_argument_group("SCR_EL3 bits (only relevant when EL3 is present)")
    scr.add_argument("--scr-ns",   type=int, choices=[0, 1], default=0,
                     metavar="0|1", help="SCR_EL3.NS   (default: 0, Secure)")
    scr.add_argument("--scr-smd",  type=int, choices=[0, 1], default=0,
                     metavar="0|1", help="SCR_EL3.SMD  (default: 0, SMC enabled)")
    scr.add_argument("--scr-hce",  type=int, choices=[0, 1], default=1,
                     metavar="0|1", help="SCR_EL3.HCE  (default: 1, HVC enabled) "
                                         "[Note: no 'SCR_EL3.HCR' field exists; "
                                         "the correct field name is HCE]")
    scr.add_argument("--scr-rw",   type=int, choices=[0, 1], default=1,
                     metavar="0|1", help="SCR_EL3.RW   (default: 1, AArch64)")
    scr.add_argument("--scr-eel2", type=int, choices=[0, 1], default=0,
                     metavar="0|1", help="SCR_EL3.EEL2 (default: 0, Secure EL2 off)")

    # HCR_EL2 bits
    hcr = parser.add_argument_group("HCR_EL2 bits (only relevant when EL2 is present)")
    hcr.add_argument("--hcr-tsc", type=int, choices=[0, 1], default=0,
                     metavar="0|1", help="HCR_EL2.TSC (default: 0); "
                                         "when 1, Non-secure EL1 SMC is trapped to EL2")
    hcr.add_argument("--hcr-tge", type=int, choices=[0, 1], default=0,
                     metavar="0|1", help="HCR_EL2.TGE (default: 0); "
                                         "when 1, EL0 exceptions route to EL2")
    hcr.add_argument("--hcr-hcd", type=int, choices=[0, 1], default=0,
                     metavar="0|1", help="HCR_EL2.HCD (default: 0); "
                                         "when 1, HVC from EL1 is disabled")
    hcr.add_argument("--hcr-e2h", type=int, choices=[0, 1], default=0,
                     metavar="0|1", help="HCR_EL2.E2H (default: 0); "
                                         "VHE host mode when combined with TGE=1")

    return parser


def main(argv: list[str] | None = None) -> None:  # pragma: no cover
    """CLI entry-point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    state = SystemState(
        current_el=ExceptionLevel(args.el),
        el2_implemented=not args.no_el2,
        el3_implemented=not args.no_el3,
        scr_el3=SCR_EL3(
            ns=args.scr_ns,
            smd=args.scr_smd,
            hce=args.scr_hce,
            rw=args.scr_rw,
            eel2=args.scr_eel2,
        ),
        hcr_el2=HCR_EL2(
            tsc=args.hcr_tsc,
            tge=args.hcr_tge,
            hcd=args.hcr_hcd,
            e2h=args.hcr_e2h,
        ),
    )

    if args.instr == "all":
        results = solve_all(state)
    else:
        results = [solve(args.instr, state)]

    any_valid = False
    for result in results:
        print(result)
        if result.is_valid:
            any_valid = True

    sys.exit(0 if any_valid else 1)


if __name__ == "__main__":
    main()


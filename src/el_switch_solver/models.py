"""Data models for the AArch64 EL switching solver."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class ExceptionLevel(IntEnum):
    """AArch64 exception levels."""

    EL0 = 0
    EL1 = 1
    EL2 = 2
    EL3 = 3

    def __str__(self) -> str:
        return f"EL{self.value}"


class Instruction(str):
    """Manual EL-switching instructions."""

    SVC = "svc"
    HVC = "hvc"
    SMC = "smc"
    ERET = "eret"

    ALL = ("svc", "hvc", "smc", "eret")


@dataclass
class SCR_EL3:
    """Secure Configuration Register (EL3).

    Only meaningful when EL3 is implemented.
    Reset values reflect a typical boot state.
    """

    #: bit[0]  Non-Secure state. 0 = Secure, 1 = Non-Secure for lower ELs.
    ns: int = 0
    #: bit[7]  Secure Monitor Call Disable.
    #:         0 = SMC causes exception to EL3, 1 = SMC is UNDEF/trapped.
    smd: int = 0
    #: bit[8]  HVC instruction Enable. 1 = HVC permitted from EL1/EL2.
    #:         (Note: there is no "HCR" field in SCR_EL3; this is "HCE".)
    hce: int = 1
    #: bit[10] Register Width. 1 = EL2/EL1/EL0 use AArch64.
    rw: int = 1
    #: bit[18] Secure EL2 Enable. 1 = EL2 available in Secure state.
    eel2: int = 0

    def __post_init__(self) -> None:
        _validate_bits(
            {"ns": self.ns, "smd": self.smd, "hce": self.hce,
             "rw": self.rw, "eel2": self.eel2}
        )


@dataclass
class HCR_EL2:
    """Hypervisor Configuration Register (EL2).

    Only meaningful when EL2 is implemented.
    """

    #: bit[19] Trap SMC instructions.
    #:         When 1, Non-secure EL1 SMC is trapped to EL2.
    #:         Only active when NOT in VHE host mode (E2H=0 or TGE=0).
    tsc: int = 0
    #: bit[27] Trap General Exceptions.
    #:         When 1, all exceptions from EL0 are routed to EL2 (incl. SVC).
    tge: int = 0
    #: bit[29] HVC Call Disable.
    #:         When 1, HVC from EL1 is trapped to EL3 or UNDEF.
    hcd: int = 0
    #: bit[34] EL2 Host (VHE) mode.
    #:         When 1 together with TGE=1, processor runs in VHE host mode.
    #:         In this mode HVC from EL1 is UNDEFINED, and TSC is inactive.
    e2h: int = 0

    def __post_init__(self) -> None:
        _validate_bits(
            {"tsc": self.tsc, "tge": self.tge, "hcd": self.hcd, "e2h": self.e2h}
        )


@dataclass
class SystemState:
    """Complete system state required to evaluate EL-switch constraints.

    Parameters
    ----------
    current_el:
        The exception level at which the instruction is about to execute.
    el2_implemented:
        Whether EL2 is implemented on this processor.
    el3_implemented:
        Whether EL3 is implemented on this processor.
    scr_el3:
        Value of SCR_EL3 (ignored when ``el3_implemented`` is False).
    hcr_el2:
        Value of HCR_EL2 (ignored when ``el2_implemented`` is False).

    Note
    ----
    SPSR_ELn is **intentionally excluded**: it is software-controlled and
    does not impose architectural constraints on *whether* an EL switch is
    legal.  The solver reports all architecturally valid target ELs; the
    caller must configure SPSR_ELn to encode the desired target before
    issuing the instruction.
    """

    current_el: ExceptionLevel
    el2_implemented: bool = True
    el3_implemented: bool = True
    scr_el3: SCR_EL3 = field(default_factory=SCR_EL3)
    hcr_el2: HCR_EL2 = field(default_factory=HCR_EL2)


@dataclass
class ConstraintViolation:
    """A single constraint that was not satisfied."""

    name: str
    description: str


@dataclass
class SwitchResult:
    """Result of evaluating whether an EL switch is legal.

    Attributes
    ----------
    instruction:
        The instruction being evaluated.
    current_el:
        EL at which the instruction executes.
    valid_targets:
        All architecturally legal destination ELs for this instruction given
        the current system state.  Empty when the instruction is illegal.

        * SVC / HVC / SMC: at most one element (routing is deterministic).
        * ERET: may contain multiple elements (EL0 and/or EL1 and/or EL2)
          because the actual target is selected by SPSR_ELn, which the
          software controls.
    is_valid:
        ``True`` when ``valid_targets`` is non-empty.
    target_el:
        Convenience property that returns the single valid target for
        instructions with deterministic routing (SVC/HVC/SMC), or ``None``
        when there are zero or more than one valid targets.
    reason:
        Human-readable explanation of the outcome.
    violations:
        List of constraint violations (empty when ``is_valid`` is True).
    """

    instruction: str
    current_el: ExceptionLevel
    valid_targets: list[ExceptionLevel]
    reason: str
    violations: list[ConstraintViolation] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when at least one legal target EL exists."""
        return bool(self.valid_targets)

    @property
    def target_el(self) -> ExceptionLevel | None:
        """The single valid target EL, or None if there are 0 or 2+ targets."""
        return self.valid_targets[0] if len(self.valid_targets) == 1 else None

    def __str__(self) -> str:
        if self.valid_targets:
            targets = ", ".join(str(t) for t in self.valid_targets)
            status = "VALID"
        else:
            targets = "N/A"
            status = "INVALID"
        lines = [
            f"[{status}] {self.instruction.upper()} @ {self.current_el} → {targets}",
            f"  Reason: {self.reason}",
        ]
        for v in self.violations:
            lines.append(f"  ✗ {v.name}: {v.description}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_bits(fields: dict[str, int]) -> None:
    for name, value in fields.items():
        if value not in (0, 1):
            raise ValueError(f"{name} must be 0 or 1, got {value}")

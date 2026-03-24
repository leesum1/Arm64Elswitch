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

    #: bit[27] Trap General Exceptions.
    #:         1 = exceptions from EL0 are routed to EL2 (incl. SVC).
    tge: int = 0
    #: bit[29] HVC Call Disable.
    #:         1 = HVC from EL1 is trapped to EL3 or UNDEF.
    hcd: int = 0
    #: bit[34] EL2 Host (VHE) mode.
    e2h: int = 0

    def __post_init__(self) -> None:
        _validate_bits({"tge": self.tge, "hcd": self.hcd, "e2h": self.e2h})


@dataclass
class SPSR:
    """Saved Program Status Register (SPSR_ELn).

    The ``m`` field encodes target state and SP select for ERET.

    Valid AArch64 encodings for M[3:0]:

    ========  =====  ==========================
    Binary    Hex    Meaning
    ========  =====  ==========================
    0b0000     0     EL0t — EL0, SP_EL0
    0b0100     4     EL1t — EL1, SP_EL0
    0b0101     5     EL1h — EL1, SP_EL1
    0b1000     8     EL2t — EL2, SP_EL0
    0b1001     9     EL2h — EL2, SP_EL1
    0b1100    12     EL3t — EL3, SP_EL0
    0b1101    13     EL3h — EL3, SP_EL1
    ========  =====  ==========================
    """

    #: bits[3:0]  Mode field (target EL + SP select).
    m: int = 0

    @property
    def target_el(self) -> ExceptionLevel:
        """Return the exception level encoded in M[3:2]."""
        return ExceptionLevel((self.m >> 2) & 0b11)

    def __post_init__(self) -> None:
        if not (0 <= self.m <= 15):
            raise ValueError(f"SPSR.m must be in [0, 15], got {self.m}")


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
    spsr:
        Value of SPSR_ELn for the current EL (used by ERET).
    """

    current_el: ExceptionLevel
    el2_implemented: bool = True
    el3_implemented: bool = True
    scr_el3: SCR_EL3 = field(default_factory=SCR_EL3)
    hcr_el2: HCR_EL2 = field(default_factory=HCR_EL2)
    spsr: SPSR = field(default_factory=SPSR)


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
    target_el:
        The destination EL if the switch is legal; ``None`` otherwise.
    is_valid:
        Whether the switch is architecturally legal.
    reason:
        Human-readable explanation of the outcome.
    violations:
        List of constraint violations (empty when ``is_valid`` is True).
    """

    instruction: str
    current_el: ExceptionLevel
    target_el: ExceptionLevel | None
    is_valid: bool
    reason: str
    violations: list[ConstraintViolation] = field(default_factory=list)

    def __str__(self) -> str:
        target = str(self.target_el) if self.target_el is not None else "N/A"
        status = "VALID" if self.is_valid else "INVALID"
        lines = [
            f"[{status}] {self.instruction.upper()} @ {self.current_el} → {target}",
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

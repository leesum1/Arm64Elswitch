# AArch64 Exception Level Switching Constraints

## Overview

AArch64 defines four exception levels (ELs):

| Level | Role |
|-------|------|
| EL0 | User / Application |
| EL1 | OS / Kernel |
| EL2 | Hypervisor |
| EL3 | Secure Monitor (TrustZone) |

EL0 and EL1 are always implemented. EL2 and EL3 are optional.

Execution can move **upward** (to a higher EL) via the `SVC`, `HVC`, and `SMC`
instructions, and **downward** (to a lower EL) via the `ERET` instruction.
Interrupts and other synchronous exceptions are **excluded** from this
document; only manual invocations are covered.

---

## Key Control Registers

### SCR_EL3 — Secure Configuration Register (EL3)

Only present when EL3 is implemented.

| Bit | Name | Meaning |
|-----|------|---------|
| 0 | NS | **Non-Secure state**. When 0, EL0/EL1 (and optionally EL2) operate in Secure state. When 1, they operate in Non-Secure state. |
| 7 | SMD | **Secure Monitor Call Disable**. When 1, `SMC` is disabled (UNDEF or trap). When 0, `SMC` causes an exception to EL3. |
| 8 | HCE | **HVC instruction Enable**. When 1, `HVC` is permitted from EL1/EL2. When 0, `HVC` is UNDEF from EL1. |
| 10 | RW | **Register Width**. When 1, EL2 and below run in AArch64. When 0, they run in AArch32. |
| 18 | EEL2 | **Secure EL2 Enable**. When 1, EL2 is available in Secure state. Required for an ERET from EL3 to EL2 when `NS=0`. |

### HCR_EL2 — Hypervisor Configuration Register (EL2)

Only meaningful when EL2 is implemented.

| Bit | Name | Meaning |
|-----|------|---------|
| 27 | TGE | **Trap General Exceptions**. When 1, all exceptions from EL0 are routed to EL2 instead of EL1. This includes `SVC`. |
| 29 | HCD | **HVC Call Disable**. When 1, `HVC` from EL1 is trapped to EL3 (if present) or is UNDEF, rather than reaching EL2. |
| 34 | E2H | **EL2 Host** mode. When 1, the processor is running in VHE (Virtualization Host Extension) mode. |

### SPSR_ELn — Saved Program Status Register

Used by `ERET` to determine the target state. The key field is:

| Bits | Name | Meaning |
|------|------|---------|
| [3:2] | M\[3:2\] | Target exception level (00=EL0, 01=EL1, 10=EL2, 11=EL3) |
| [0] | M\[0\] | Stack pointer select (0=SP\_EL0, 1=SP\_ELn) |

Valid `M[3:0]` encodings in AArch64:

| M[3:0] | Value | Meaning |
|--------|-------|---------|
| `0b0000` | 0 | EL0t — EL0, SP\_EL0 |
| `0b0100` | 4 | EL1t — EL1, SP\_EL0 |
| `0b0101` | 5 | EL1h — EL1, SP\_EL1 |
| `0b1000` | 8 | EL2t — EL2, SP\_EL0 |
| `0b1001` | 9 | EL2h — EL2, SP\_EL1 |
| `0b1100` | 12 | EL3t — EL3, SP\_EL0 |
| `0b1101` | 13 | EL3h — EL3, SP\_EL1 |

---

## Upward EL Switches

### SVC (Supervisor Call)

`SVC` causes a synchronous exception that is taken to **EL1 or EL2**.

#### SVC executed at EL0

| Condition | Target EL | Valid? |
|-----------|-----------|--------|
| EL2 not implemented OR `HCR_EL2.TGE = 0` | EL1 | ✅ Valid |
| EL2 implemented AND `HCR_EL2.TGE = 1` | EL2 | ✅ Valid |

**Formal constraint:**
```
(EL2_implemented ∧ HCR_EL2.TGE = 1) → target = EL2
¬(EL2_implemented ∧ HCR_EL2.TGE = 1) → target = EL1
```

#### SVC executed at EL1 or higher

`SVC` at EL1 causes a synchronous exception that stays at EL1 (not an EL
switch). `SVC` at EL2/EL3 is architecturally valid but is treated as an
exception taken to the current EL (same-level switch, not covered here).

---

### HVC (Hypervisor Call)

`HVC` causes a synchronous exception taken to **EL2**.

#### HVC executed at EL0

Always **UNDEFINED** (illegal instruction). No EL switch occurs.

#### HVC executed at EL1 → EL2

All three conditions below must hold:

| # | Constraint | Consequence if violated |
|---|------------|------------------------|
| 1 | EL2 is implemented | `HVC` is UNDEF |
| 2 | EL3 not implemented, **OR** `SCR_EL3.HCE = 1` | `HVC` is UNDEF at EL1 |
| 3 | `HCR_EL2.HCD = 0` | `HVC` is trapped to EL3 (if present) or UNDEF |

**Formal constraint:**
```
EL2_implemented
∧ (¬EL3_implemented ∨ SCR_EL3.HCE = 1)
∧ HCR_EL2.HCD = 0
→ target = EL2
```

#### HVC executed at EL2

In standard (non-VHE) mode `HVC` from EL2 is effectively a self-exception to
EL2 (no EL change). In VHE mode (`HCR_EL2.E2H = 1`) it is a host call. No
EL switch occurs; excluded from this document.

#### HVC executed at EL3

`HVC` is treated as a NOP or UNDEF. No EL switch.

---

### SMC (Secure Monitor Call)

`SMC` causes a synchronous exception taken to **EL3**.

#### SMC executed at EL0

Always **UNDEFINED**. No EL switch occurs.

#### SMC executed at EL1 → EL3

Both conditions below must hold:

| # | Constraint | Consequence if violated |
|---|------------|------------------------|
| 1 | EL3 is implemented | `SMC` is UNDEF |
| 2 | `SCR_EL3.SMD = 0` | `SMC` is UNDEF (or trapped to EL2 in some implementations) |

**Formal constraint:**
```
EL3_implemented
∧ SCR_EL3.SMD = 0
→ target = EL3
```

#### SMC executed at EL2 → EL3

Same constraints as from EL1:

```
EL3_implemented
∧ SCR_EL3.SMD = 0
→ target = EL3
```

#### SMC executed at EL3

Treated as a NOP by the architecture. No EL switch.

---

## Downward EL Switches

### ERET (Exception Return)

`ERET` reads `SPSR_ELn` and `ELR_ELn` from the **current** exception level,
then returns to the state described in `SPSR_ELn`.

The target EL is `SPSR_ELn.M[3:2]`. The target EL **must** be strictly lower
than (or equal to, but same-level ERET is architecturally reserved/UNDEF) the
current EL.

#### ERET executed at EL0

Always **UNDEFINED**.

#### ERET executed at EL1 → EL0

| Constraint | Detail |
|------------|--------|
| `SPSR_EL1.M[3:2] = 0b00` | Target must be EL0 |

Any other value of `SPSR_EL1.M[3:2]` is an illegal exception return.

**Formal constraint:**
```
SPSR_EL1.M[3:2] = 0b00
→ target = EL0   ✅
```

#### ERET executed at EL2

| `SPSR_EL2.M[3:2]` | Target | Valid? | Additional constraints |
|--------------------|--------|--------|------------------------|
| `0b00` | EL0 | ✅ | None |
| `0b01` | EL1 | ✅ | None |
| `0b10` | EL2 | ❌ | Illegal exception return (same level) |
| `0b11` | EL3 | ❌ | Cannot ERET to higher EL |

**Formal constraint:**
```
SPSR_EL2.M[3:2] ∈ {0b00, 0b01}
→ target = EL(SPSR_EL2.M[3:2])   ✅
```

#### ERET executed at EL3

| `SPSR_EL3.M[3:2]` | Target | Valid? | Additional constraints |
|--------------------|--------|--------|------------------------|
| `0b00` | EL0 | ✅ | None |
| `0b01` | EL1 | ✅ | None |
| `0b10` | EL2 | ✅ (conditional) | EL2 must be implemented **AND** (`SCR_EL3.NS = 1` OR `SCR_EL3.EEL2 = 1`) |
| `0b11` | EL3 | ❌ | Illegal exception return (same level) |

**Formal constraint for target EL2:**
```
EL2_implemented
∧ (SCR_EL3.NS = 1 ∨ SCR_EL3.EEL2 = 1)
∧ SPSR_EL3.M[3:2] = 0b10
→ target = EL2   ✅
```

---

## Summary Table

| Instruction | From EL | Target EL | Key Constraints |
|-------------|---------|-----------|-----------------|
| `SVC` | EL0 | EL1 | EL2 not implemented OR `HCR_EL2.TGE=0` |
| `SVC` | EL0 | EL2 | EL2 implemented AND `HCR_EL2.TGE=1` |
| `HVC` | EL1 | EL2 | EL2 implemented AND (`¬EL3` OR `SCR_EL3.HCE=1`) AND `HCR_EL2.HCD=0` |
| `SMC` | EL1 | EL3 | EL3 implemented AND `SCR_EL3.SMD=0` |
| `SMC` | EL2 | EL3 | EL3 implemented AND `SCR_EL3.SMD=0` |
| `ERET` | EL1 | EL0 | `SPSR_EL1.M[3:2]=0b00` |
| `ERET` | EL2 | EL0 | `SPSR_EL2.M[3:2]=0b00` |
| `ERET` | EL2 | EL1 | `SPSR_EL2.M[3:2]=0b01` |
| `ERET` | EL3 | EL0 | `SPSR_EL3.M[3:2]=0b00` |
| `ERET` | EL3 | EL1 | `SPSR_EL3.M[3:2]=0b01` |
| `ERET` | EL3 | EL2 | `SPSR_EL3.M[3:2]=0b10` AND EL2 implemented AND (`SCR_EL3.NS=1` OR `SCR_EL3.EEL2=1`) |

---

## Security State and `SCR_EL3.NS`

When executing at EL3, `SCR_EL3.NS` controls the security state of lower ELs:

- `SCR_EL3.NS = 0` → Secure World (lower ELs are in Secure state)
- `SCR_EL3.NS = 1` → Normal World (lower ELs are in Non-Secure state)

Writing `SCR_EL3.NS` at EL3 is the standard way to switch between Secure and
Non-Secure worlds before issuing an `ERET` to the target EL. This bit is
automatically updated on exception entry to EL3.

Additionally, `SCR_EL3.EEL2 = 1` enables Secure EL2 (ARMv8.4-SecEL2 extension).
Without it, EL2 only exists in Non-Secure state.

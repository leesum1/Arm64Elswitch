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

> **Note on SPSR_ELn** — SPSR is *software-controlled*, not an architectural
> constraint.  The solver enumerates all hardware-reachable target ELs; the
> caller must configure `SPSR_ELn.M[3:0]` to match the desired target before
> executing the instruction.

---

## Key Control Registers

### SCR_EL3 — Secure Configuration Register (EL3)

Only present when EL3 is implemented.

| Bit | Name | Meaning |
|-----|------|---------|
| 0 | **NS** | **Non-Secure state**. When 0, EL0/EL1 (and optionally EL2) operate in Secure state. When 1, they operate in Non-Secure state. |
| 7 | **SMD** | **Secure Monitor Call Disable**. When 1, `SMC` is UNDEF. When 0, `SMC` causes an exception to EL3. |
| 8 | **HCE** | **HVC instruction Enable**. When 1, `HVC` is permitted from EL1/EL2. When 0, `HVC` is UNDEF from EL1. **There is no "HCR" field in SCR_EL3; the correct field name is HCE.** |
| 10 | **RW** | **Register Width**. When 1, EL2 and below run in AArch64. When 0, they run in AArch32. |
| 18 | **EEL2** | **Secure EL2 Enable** (ARMv8.4). When 1, EL2 is available in Secure state. Required for an `ERET` from EL3 to EL2 when `NS=0`. |

### HCR_EL2 — Hypervisor Configuration Register (EL2)

Only meaningful when EL2 is implemented.

| Bit | Name | Meaning |
|-----|------|---------|
| 12 | **DC** | **Default Cacheability**. When 1, enables stage-2 translation with default cacheability (implies `VM=1` semantics for data accesses). **DC does not affect exception routing** — it has no influence on whether SVC/HVC/SMC/ERET switches are legal. |
| 19 | **TSC** | **Trap SMC**. When 1, Non-secure EL1 execution of `SMC` is trapped to EL2. This takes priority over routing to EL3. **Inactive** when in VHE host mode (`E2H=1 ∧ TGE=1`). |
| 27 | **TGE** | **Trap General Exceptions**. When 1, all exceptions from EL0 are routed to EL2 (including `SVC`). Also participates in VHE host mode definition together with E2H. |
| 29 | **HCD** | **HVC Call Disable**. When 1, `HVC` from EL1 is trapped to EL3 (if present) or UNDEF; EL2 is not reached. |
| 34 | **E2H** | **EL2 Host** (VHE — Virtualization Host Extension). When E2H=1 **together with TGE=1**, the processor is in **VHE host mode**: the host OS runs directly at EL2, applications run at EL0/EL1; `HVC` from EL1 is UNDEF; `TSC` is inactive. When E2H=1 but TGE=0, the system is in *guest mode*; HVC from EL1 still works normally. |

### VHE Host Mode

VHE host mode is active when **both** `HCR_EL2.E2H = 1` and `HCR_EL2.TGE = 1`.
Its effects on manual EL switching:

| Effect | Details |
|--------|---------|
| `HVC` from EL1 → **UNDEFINED** | In VHE host mode the hypervisor host runs at EL2, so HVC from EL1 is architecturally UNDEFINED. |
| `TSC` becomes **inactive** | `HCR_EL2.TSC` only traps Non-secure EL1 SMC when `E2H=0 ∨ TGE=0`; in VHE host mode the SMC goes normally to EL3 (subject to `SCR_EL3.SMD`). |

### Security State

When EL3 is implemented, `SCR_EL3.NS` controls the security state of lower ELs:

- **Secure state** (`SCR_EL3.NS = 0`): lower ELs run in Secure World.
  `HCR_EL2.TSC` does **not** trap SMC in this state.
- **Non-Secure state** (`SCR_EL3.NS = 1`): lower ELs run in Normal World.
  `HCR_EL2.TSC` is active (subject to VHE host mode).

When EL3 is **not implemented**, the processor is always in Non-Secure state.

---

## Upward EL Switches

### SVC (Supervisor Call)

`SVC` causes a synchronous exception routed to **EL1 or EL2**.
Reference: DDI 0487 D1.10.1

#### SVC executed at EL0

| Condition | Target EL | Valid? |
|-----------|-----------|--------|
| EL2 not implemented **OR** `HCR_EL2.TGE = 0` | EL1 | ✅ |
| EL2 implemented **AND** `HCR_EL2.TGE = 1` | EL2 | ✅ |

`HCR_EL2.TGE` routes **all** EL0 exceptions (including SVC) to EL2 regardless of
security state.

**Formal constraint:**
```
if EL2_implemented ∧ HCR_EL2.TGE = 1:
    target = EL2
else:
    target = EL1
```

#### SVC executed at EL1 or higher

`SVC` causes a same-level exception (stays at EL1). **Not an inter-level switch.**

---

### HVC (Hypervisor Call)

`HVC` causes a synchronous exception taken to **EL2**.
Reference: DDI 0487 D1.14.9

#### HVC executed at EL0

Always **UNDEFINED** (illegal instruction). No EL switch.

#### HVC executed at EL1 → EL2

All **four** conditions below must hold:

| # | Constraint | Consequence if violated |
|---|------------|------------------------|
| 1 | EL2 is implemented | `HVC` is UNDEF |
| 2 | `HCR_EL2.E2H = 0` **OR** `HCR_EL2.TGE = 0` (NOT in VHE host mode) | `HVC` is UNDEFINED in VHE host mode |
| 3 | EL3 not implemented, **OR** `SCR_EL3.HCE = 1` | `HVC` is UNDEF when EL3 present and HCE=0 |
| 4 | `HCR_EL2.HCD = 0` | `HVC` is trapped to EL3 or UNDEF when HCD=1 |

**Formal constraint:**
```
EL2_implemented
∧ ¬(HCR_EL2.E2H = 1 ∧ HCR_EL2.TGE = 1)   # not VHE host mode
∧ (¬EL3_implemented ∨ SCR_EL3.HCE = 1)
∧ HCR_EL2.HCD = 0
→ target = EL2   ✅
```

#### HVC executed at EL2 or EL3

Same-level exception or NOP; no inter-level switch.

---

### SMC (Secure Monitor Call)

`SMC` can route to **EL2 (trap)** or **EL3** depending on the register state.
Reference: DDI 0487 D1.14.10

#### SMC executed at EL0

Always **UNDEFINED**. No EL switch.

#### SMC executed at EL1 → EL2 (TSC trap path)

This path has **priority** over the EL3 path below.

All conditions must hold:

| # | Constraint | Detail |
|---|------------|--------|
| 1 | EL2 is implemented | TSC can only redirect to EL2 |
| 2 | `HCR_EL2.TSC = 1` | TSC enabled |
| 3 | Non-Secure state | `SCR_EL3.NS = 1` **or** EL3 not implemented |
| 4 | NOT VHE host mode | `HCR_EL2.E2H = 0` **or** `HCR_EL2.TGE = 0` |

**Formal constraint (EL1 → EL2 via TSC):**
```
EL2_implemented
∧ HCR_EL2.TSC = 1
∧ (¬EL3_implemented ∨ SCR_EL3.NS = 1)     # Non-Secure state
∧ ¬(HCR_EL2.E2H = 1 ∧ HCR_EL2.TGE = 1)   # not VHE host mode
→ target = EL2   ✅
```

#### SMC executed at EL1 → EL3 (normal path)

Applies when the TSC trap path above does **not** fire.

| # | Constraint | Consequence if violated |
|---|------------|------------------------|
| 1 | EL3 is implemented | `SMC` is UNDEF |
| 2 | `SCR_EL3.SMD = 0` | `SMC` is UNDEF |

**Formal constraint (EL1 → EL3):**
```
¬TSC_trap_active                            # TSC path did not fire
∧ EL3_implemented
∧ SCR_EL3.SMD = 0
→ target = EL3   ✅
```

#### SMC executed at EL2 → EL3

TSC does **not** apply to EL2 execution. The same two conditions as above:

```
EL3_implemented
∧ SCR_EL3.SMD = 0
→ target = EL3   ✅
```

#### SMC executed at EL3

NOP by the architecture. No EL switch.

---

## Downward EL Switches

### ERET (Exception Return)

`ERET` restores execution to the EL encoded in `SPSR_ELn.M[3:2]` and sets PC
from `ELR_ELn`.  Because SPSR is software-controlled, the solver reports **all**
architecturally valid target ELs; the caller selects the actual target by
configuring `SPSR_ELn` before the instruction.
Reference: DDI 0487 D1.11.1

#### ERET executed at EL0

Always **UNDEFINED**.

#### ERET executed at EL1

| Reachable target | Constraints |
|-----------------|-------------|
| EL0 | Always reachable |

Set `SPSR_EL1.M[3:0] = 0b0000` (EL0t) or choose appropriately.

#### ERET executed at EL2

| Reachable target | Constraints |
|-----------------|-------------|
| EL0 | Always reachable |
| EL1 | Always reachable |

Set `SPSR_EL2.M[3:2] = 0b00` (EL0) or `0b01` (EL1).

#### ERET executed at EL3

| Reachable target | Constraints |
|-----------------|-------------|
| EL0 | Always reachable |
| EL1 | Always reachable |
| EL2 | EL2 implemented **AND** (`SCR_EL3.NS = 1` **or** `SCR_EL3.EEL2 = 1`) |

**Formal constraint for EL2 reachability from EL3:**
```
EL2_implemented
∧ (SCR_EL3.NS = 1 ∨ SCR_EL3.EEL2 = 1)
→ EL2 is a valid ERET target   ✅
```

Typical usage: write `SCR_EL3.NS` to select the security world, configure
`SPSR_EL3.M[3:2]` to encode the target EL, then execute `ERET`.

---

## Complete Summary Table

| Instruction | From EL | Target EL | Key Constraints |
|-------------|---------|-----------|-----------------|
| `SVC` | EL0 | EL1 | EL2 absent **or** `HCR_EL2.TGE=0` |
| `SVC` | EL0 | EL2 | EL2 implemented **and** `HCR_EL2.TGE=1` |
| `HVC` | EL1 | EL2 | EL2 present **∧** not VHE host mode **∧** (`¬EL3` ∨ `HCE=1`) **∧** `HCD=0` |
| `SMC` | EL1 | EL2 *(trap)* | EL2 present **∧** `TSC=1` **∧** Non-Secure **∧** not VHE host |
| `SMC` | EL1 | EL3 | TSC inactive **∧** EL3 present **∧** `SMD=0` |
| `SMC` | EL2 | EL3 | EL3 present **∧** `SMD=0` *(TSC does not apply to EL2)* |
| `ERET` | EL1 | EL0 | Always valid (EL0 always present) |
| `ERET` | EL2 | EL0, EL1 | Always valid |
| `ERET` | EL3 | EL0, EL1 | Always valid |
| `ERET` | EL3 | EL2 | EL2 present **∧** (`NS=1` ∨ `EEL2=1`) |

---

## Registers That Do Not Affect EL Switching

| Register / Field | Reason not relevant |
|-----------------|---------------------|
| `HCR_EL2.DC` (bit 12) | Controls stage-2 translation cacheability only; no effect on exception routing. |
| `HCR_EL2.VM` (bit 0) | Enables stage-2 translation; no effect on which EL an exception is taken to. |
| `SCR_EL3.IRQ/FIQ/EA` | Route physical interrupts/SErrors; irrelevant to manual SVC/HVC/SMC/ERET. |
| `SCR_EL3.RW` (bit 10) | Controls AArch32/AArch64 state of lower ELs; does not gate EL switching itself. |


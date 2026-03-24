# Arm64Elswitch — AArch64 Exception Level Switching Solver

A Python library and command-line tool that **documents and evaluates** the
architectural constraints governing manual exception-level (EL) switches in
AArch64, using the `SVC`, `HVC`, `SMC`, and `ERET` instructions.

---

## Background

AArch64 defines four exception levels:

| Level | Role |
|-------|------|
| EL0 | User / Application |
| EL1 | OS / Kernel |
| EL2 | Hypervisor |
| EL3 | Secure Monitor (TrustZone) |

Manual EL transitions are controlled by several system registers
(`SCR_EL3`, `HCR_EL2`, `SPSR_ELn`). Not every combination of instruction,
current EL, and register values produces a legal switch.

See **[docs/el_switch_constraints.md](docs/el_switch_constraints.md)** for the
complete constraint reference documentation.

---

## Installation

This project is managed with [uv](https://docs.astral.sh/uv/).

```bash
# Install uv (if not already present)
pip install uv

# Create the virtual environment and install dependencies
uv sync

# Run the CLI
uv run el-switch --help
```

---

## CLI Usage

```
el-switch --el <N> [--instr <INSTR>] [register options]
```

### Examples

```bash
# Check all instructions from EL1 (default register values)
uv run el-switch --el 1

# Check HVC from EL1
uv run el-switch --el 1 --instr hvc

# Check SMC from EL1 when SCR_EL3.SMD=1 (SMC disabled)
uv run el-switch --el 1 --instr smc --scr-smd 1

# Check ERET from EL3 targeting EL2 (Non-Secure, SPSR.M=8)
uv run el-switch --el 3 --instr eret --spsr-m 8 --scr-ns 1

# Check ERET from EL3 targeting EL2 in Secure state with EEL2=1
uv run el-switch --el 3 --instr eret --spsr-m 8 --scr-eel2 1

# Check SVC from EL0 when HCR_EL2.TGE=1 (routed to EL2)
uv run el-switch --el 0 --instr svc --hcr-tge 1
```

### Options

```
  --el N              Current exception level (0–3)
  --instr INSTR       Instruction: svc, hvc, smc, eret, or all (default: all)
  --no-el2            EL2 is not implemented
  --no-el3            EL3 is not implemented

SCR_EL3 bits:
  --scr-ns  0|1       SCR_EL3.NS   (default: 0 = Secure)
  --scr-smd 0|1       SCR_EL3.SMD  (default: 0 = SMC enabled)
  --scr-hce 0|1       SCR_EL3.HCE  (default: 1 = HVC enabled)
  --scr-rw  0|1       SCR_EL3.RW   (default: 1 = AArch64)
  --scr-eel2 0|1      SCR_EL3.EEL2 (default: 0 = Secure EL2 off)

HCR_EL2 bits:
  --hcr-tge 0|1       HCR_EL2.TGE (default: 0)
  --hcr-hcd 0|1       HCR_EL2.HCD (default: 0)
  --hcr-e2h 0|1       HCR_EL2.E2H (default: 0)

SPSR (ERET only):
  --spsr-m M          SPSR.M[3:0] value (default: 0 = EL0t)
                      0=EL0t, 4=EL1t, 5=EL1h, 8=EL2t, 9=EL2h
```

---

## Python API

```python
from el_switch_solver.models import (
    ExceptionLevel, HCR_EL2, SCR_EL3, SPSR, SystemState,
)
from el_switch_solver.solver import solve, solve_all

# Example: can HVC from EL1 reach EL2?
state = SystemState(
    current_el=ExceptionLevel.EL1,
    el2_implemented=True,
    el3_implemented=True,
    scr_el3=SCR_EL3(hce=1),
    hcr_el2=HCR_EL2(hcd=0),
)
result = solve("hvc", state)
print(result)
# [VALID] HVC @ EL1 → EL2
#   Reason: EL2 implemented, SCR_EL3.HCE=1 (or EL3 absent), and HCR_EL2.HCD=0 → HVC from EL1 reaches EL2.

# Example: ERET from EL3 to EL2 (Secure state, EEL2 required)
state2 = SystemState(
    current_el=ExceptionLevel.EL3,
    scr_el3=SCR_EL3(ns=0, eel2=0),
    spsr=SPSR(m=0b1000),  # EL2t
)
result2 = solve("eret", state2)
print(result2)
# [INVALID] ERET @ EL3 → N/A
#   Reason: ERET from EL3 to EL2 is blocked by one or more constraints.
#   ✗ Secure EL2 not enabled: ...

# Evaluate all four instructions at once
all_results = solve_all(state)
```

---

## Running Tests

```bash
uv run pytest
```

---

## Constraint Reference

The full constraint reference is in
[docs/el_switch_constraints.md](docs/el_switch_constraints.md).

### Quick Summary

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

## Project Structure

```
├── docs/
│   └── el_switch_constraints.md   # Detailed constraint documentation
├── src/
│   └── el_switch_solver/
│       ├── __init__.py
│       ├── models.py              # Data models (SystemState, registers, …)
│       ├── constraints.py         # Per-instruction constraint evaluation
│       └── solver.py              # Public API + CLI entry-point
├── tests/
│   └── test_solver.py
└── pyproject.toml                 # uv / hatchling project config
```

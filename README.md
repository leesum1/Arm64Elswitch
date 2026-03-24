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
(`SCR_EL3`, `HCR_EL2`). Not every combination of instruction,
current EL, and register values produces a legal switch.

`SPSR_ELn` is software-controlled and is **intentionally excluded** from the
solver: the solver reports all architecturally valid target ELs; the caller
configures `SPSR_ELn` to select the actual target.

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

# HVC from EL1 in VHE host mode (E2H=1, TGE=1) → UNDEFINED
uv run el-switch --el 1 --instr hvc --hcr-e2h 1 --hcr-tge 1

# SMC from EL1: TSC=1 traps to EL2 instead of EL3 (Non-Secure)
uv run el-switch --el 1 --instr smc --hcr-tsc 1 --scr-ns 1

# ERET from EL3: enumerate all reachable ELs (Non-Secure)
uv run el-switch --el 3 --instr eret --scr-ns 1

# ERET from EL3 in Secure state with Secure EL2 enabled
uv run el-switch --el 3 --instr eret --scr-eel2 1

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
                      [Note: there is no SCR_EL3.HCR field; the correct name is HCE]
  --scr-rw  0|1       SCR_EL3.RW   (default: 1 = AArch64)
  --scr-eel2 0|1      SCR_EL3.EEL2 (default: 0 = Secure EL2 off)

HCR_EL2 bits:
  --hcr-tsc 0|1       HCR_EL2.TSC (default: 0); when 1, Non-secure EL1 SMC → EL2
  --hcr-tge 0|1       HCR_EL2.TGE (default: 0); when 1, EL0 exceptions → EL2
  --hcr-hcd 0|1       HCR_EL2.HCD (default: 0); when 1, HVC from EL1 disabled
  --hcr-e2h 0|1       HCR_EL2.E2H (default: 0); VHE host mode when combined with TGE=1
```

---

## Python API

```python
from el_switch_solver.models import (
    ExceptionLevel, HCR_EL2, SCR_EL3, SystemState,
)
from el_switch_solver.solver import solve, solve_all

# Example: can HVC from EL1 reach EL2?
state = SystemState(
    current_el=ExceptionLevel.EL1,
    el2_implemented=True,
    el3_implemented=True,
    scr_el3=SCR_EL3(hce=1),
    hcr_el2=HCR_EL2(hcd=0, tsc=0),
)
result = solve("hvc", state)
print(result)
# [VALID] HVC @ EL1 → EL2
#   Reason: EL2 implemented, not in VHE host mode, SCR_EL3.HCE=1 (or EL3 absent),
#           HCR_EL2.HCD=0 → HVC from EL1 reaches EL2.

# Example: ERET from EL3 — enumerate all reachable ELs
state2 = SystemState(
    current_el=ExceptionLevel.EL3,
    scr_el3=SCR_EL3(ns=1),   # Non-Secure: EL0, EL1, and EL2 all reachable
)
result2 = solve("eret", state2)
print(result2)
# [VALID] ERET @ EL3 → EL0, EL1, EL2
#   Reason: ERET from EL3 can return to: EL0, EL1, EL2. ...
print(result2.valid_targets)   # [EL0, EL1, EL2]

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
| `HVC` | EL1 | EL2 | EL2 present ∧ not VHE host mode ∧ (`¬EL3` ∨ `HCE=1`) ∧ `HCD=0` |
| `SMC` | EL1 | EL2 *(trap)* | EL2 present ∧ `TSC=1` ∧ Non-Secure ∧ not VHE host |
| `SMC` | EL1 | EL3 | TSC inactive ∧ EL3 present ∧ `SMD=0` |
| `SMC` | EL2 | EL3 | EL3 present ∧ `SMD=0` |
| `ERET` | EL1 | EL0 | Always valid |
| `ERET` | EL2 | EL0, EL1 | Always valid |
| `ERET` | EL3 | EL0, EL1 | Always valid |
| `ERET` | EL3 | EL2 | EL2 present ∧ (`NS=1` ∨ `EEL2=1`) |

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


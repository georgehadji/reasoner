# Context: Constraints

## Directory: `src/reasoner/infrastructure/llm/constraints`

## Description
Validators enforcing format rules, token budgets, or prompt structural boundaries on model outputs.

## Files
- **`__init__.py`**: ACR routing constraints (Phase 4).
- **`bloc_diversity.py`**: Constraint: enforce cross-bloc diversity in model assignments.
- **`budget_ceiling.py`**: Constraint: total estimated cost ≤ preset tier budget.
- **`circuit_state.py`**: Constraint: skip models with open circuit breakers.
- **`concurrency.py`**: Constraint: avoid models near their concurrency limit.
- **`no_repeat_lab.py`**: Constraint: max 60% of roles from one lab (configurable).

## Subfolders
*No subfolders in this directory.*

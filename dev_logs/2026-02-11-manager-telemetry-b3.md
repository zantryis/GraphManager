# 2026-02-11 - Manager Telemetry And Policy-Efficiency Diagnostics (B3)

## Context

- Workstream B3 requires per-issue manager telemetry and policy-efficiency metrics beyond aggregate F1.
- Existing manager token payload tracked tool counters but lacked explicit stop reasons and a stable telemetry serialization shape.

## Decision

- Added manager telemetry serialization utility:
  - `serialize_manager_telemetry(...)` in `src/manager_agent.py`.
- Added explicit stop-reason handling in manager execution:
  - `sufficient_confidence`, `budget`, `max_turns`.
- `ManagerAgent.find_relevant_files(...)` now returns token payloads containing:
  - `stop_reason`
  - `manager_telemetry` (tool counts/cache hits/response chars/by-tool calls/stop reason)
- Extended aggregation (`src/evaluation.py`) to include:
  - per-method `stop_reason_counts`
  - `tokens_per_f1`
  - `token_per_f1_delta_vs_rag_baseline`
- Kept existing token accounting formulas unchanged for compatibility.

## Alternatives Considered

1. Keep telemetry only inside raw manager outputs without aggregation.
Tradeoff: data available but harder to compare methods/issues systematically.
2. Track stop reasons externally in runner scripts.
Tradeoff: less code churn, but brittle and detached from source-of-truth method outputs.
3. Add coarse global stop reason only.
Tradeoff: minimal changes, but loses per-method diagnostic detail.

## Evidence

- Updated tests:
  - `tests/test_agent_grounding.py`
    - manager telemetry serialization payload
    - manager stop-reason propagation on grounded-output rejection path
  - `tests/test_evaluation_logic.py`
    - stop-reason counting and token-per-F1 delta regression
- Full suite:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - Result: 29 tests passing.

## Consequences

- Expected benefits:
  - richer per-issue diagnostics for manager policy behavior,
  - explicit accounting of why search terminated,
  - immediate comparability of token efficiency vs RAG baseline.
- Known risks:
  - stop-reason taxonomy is heuristic and may need refinement under broader runs.
  - `tokens_per_f1` is sensitive to very low F1 values and should be interpreted carefully.
- Monitoring signals:
  - distribution of stop reasons by method/mode,
  - trend of `token_per_f1_delta_vs_rag_baseline`,
  - consistency between telemetry and tool-call logs.

## Follow-up

1. Emit telemetry aggregates to report plots/tables for policy diagnostics.
2. Refine stop-reason logic with explicit budget thresholds across runs.
3. Add evaluation-time checks for telemetry completeness in result artifacts.

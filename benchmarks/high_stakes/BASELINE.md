# High-stakes baseline

Plan: `docs/plans/high-stakes-reliability.md` §6.

## Offline routing recall (regex only, free) — 2026-11-14

`PYTHONPATH=src python benchmarks/high_stakes/route_eval.py` over `cases.jsonl`
(14 high-stakes questions, 8 negatives, English and Greek):

| Domain | Flagged by regex |
|---|---|
| health | 4 / 5 |
| legal | 1 / 4 |
| financial | 5 / 5 |

No false positives, no wrong-domain hits. Misses include "Can I take paracetamol
with amoxicillin?" and "Can my landlord keep my deposit after I move out?". The
regex is the floor; the model detector (`stakes_detector`) is what should catch
these. Its recall is not measured yet.

The 22 cases were written by the implementer to exercise routing. They are a
smoke corpus, not a sample of real traffic, so the recall figures are not an
estimate of production recall.

## Not yet measured

- Detector recall and its parse rate on `gemini-2.5-flash`.
- Label precision, authority rate, refer precision/recall, cost and latency.
  These need `reference` answers in `cases.jsonl`.
  [INPUT REQUIRED: reference answers written or reviewed by qualified people per domain; no model-written gold answers.]
- `run_eval.py` (billed calls, `integration-live` workflow) is not written; it has nothing to score against until the reference answers exist.

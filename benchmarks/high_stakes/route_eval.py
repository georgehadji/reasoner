"""Offline routing recall for the high-stakes policy (plan §6, metric 1). Free: no LLM calls.

Runs the deterministic detector (hypergate/stakes_patterns) over cases.jsonl and
reports, per domain, how many high-stakes questions it flags and how many
negatives it wrongly flags. A miss here is a question the model detector alone
must catch; see BASELINE.md for the live numbers.

    PYTHONPATH=src python benchmarks/high_stakes/route_eval.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from reasoner.domain.stakes import StakesDomain
from reasoner.hypergate.stakes_patterns import match_stakes

CASES = Path(__file__).with_name("cases.jsonl")


def load_cases() -> list[dict]:
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line]


def evaluate(cases: list[dict]) -> dict:
    hit, total, wrong_domain, false_pos = Counter(), Counter(), [], []
    for c in cases:
        got = match_stakes(c["question"])
        if c["domain"] == "none":
            if got is not StakesDomain.NONE:
                false_pos.append(c["question"])
            continue
        total[c["domain"]] += 1
        if got.value == c["domain"]:
            hit[c["domain"]] += 1
        elif got is not StakesDomain.NONE:
            wrong_domain.append((c["question"], got.value))
    return {"hit": dict(hit), "total": dict(total), "wrong_domain": wrong_domain,
            "false_positives": false_pos}


if __name__ == "__main__":
    print(json.dumps(evaluate(load_cases()), indent=2, ensure_ascii=False))

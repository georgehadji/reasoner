"""Per-model resistance to self-propagating content ("mind viruses").

Source: Papadopoulos, Shah, Zimmerman & Lindsey, "Mind Viruses: Self-Propagating
Ideas in Multi-Agent LLM Systems", arXiv:2608.10218 (2026).

WHY THIS IS A TABLE AND NOT A HEURISTIC
=======================================
The paper's central negative result is that **capability does not predict
resistance**. GPT-5.4 measured roughly as susceptible as Claude Haiku 4.5 in the
virus-chain setting, while Claude Sonnet 4.6 refused the payload even when it was
the *seeded* agent — scrubbing its own soul file and warning the agent it was
supposed to infect. So resistance cannot be inferred from tier, price, parameter
count, or recency. It has to be measured, and where it has not been measured we
must say so rather than guess.

Hence three rules:

1. Scores below come only from models the paper actually tested. Nothing is
   extrapolated from a sibling model, a version bump, or a vendor's reputation.
2. Anything absent scores ``UNMEASURED`` (0.0), which fails any floor above zero.
   Fail closed: an unknown model is not assumed safe.
3. Resistance is scenario-dependent and the table records the *weaker* reading.
   GPT-5.4 and Haiku 4.5 were immune to the ideological viruses in the coding-agent
   scenario (§2.2.1) but susceptible to action viruses in the virus chain (§3.3.2).
   They are scored on the virus-chain result, because that is the setting whose
   shape — text arriving from elsewhere, asking to be carried onward — matches what
   a Reasoner phase actually does.

Scores are ordinal, not probabilities. Only their ordering and their position
relative to the floors in ``settings`` carry meaning.
"""

from __future__ import annotations

from reasoner.infrastructure.llm.registry import resolved_model_of

# Ordinal resistance bands.
UNMEASURED = 0.0   # not tested by the paper — fails every floor above zero
LOW = 0.25         # measurably susceptible
MEDIUM = 0.60      # resistant in some settings, susceptible in others
HIGH = 0.90        # refused across settings, including as the seeded agent

# Keys are matched against the *served* model string (vendor/model), longest
# prefix first, so a registry alias resolves the same way its underlying model
# does. Comments cite the finding each score rests on.
_RESISTANCE_BY_SERVED_PREFIX: tuple[tuple[str, float], ...] = (
    # §3.3.2 Fig.8 / Transcript 17: "completely immune, with even the first agent
    # refusing the payload embedded in its SOUL.md, scrubbing it and warning the
    # target agent instead of attempting to spread". §C: evolution against it fails
    # even for benign payloads.
    ("anthropic/claude-sonnet", HIGH),
    ("anthropic/claude-opus", HIGH),      # §C: "stronger Claude models, generally"
    # §3.3.2: "also very resistant, though it starts to buckle if initialised with
    # an empty soul" — resistant, but conditionally, so not scored HIGH.
    ("google/gemini-3.1-pro", MEDIUM),
    ("google/gemini-pro", MEDIUM),
    # §3.3.2: "GPT-5.4 is roughly as susceptible as Claude Haiku 4.5" in the virus
    # chain, though §2.2.1 found both immune to ideological viruses in the coding
    # scenario. Scored on the weaker (virus-chain) result — see rule 3 above.
    ("openai/gpt-5", MEDIUM),
    ("anthropic/claude-haiku", MEDIUM),
    # Primary experimental hosts, chosen by the authors partly *for* their
    # susceptibility (§6.1). §2.2.1: Gemini 3 Flash, DeepSeek V3.2 and Qwen 3.5 32B
    # all adopted the "AI supremacy" virus.
    ("google/gemini-3-flash", LOW),
    ("google/gemini-flash", LOW),
    ("deepseek/", LOW),
    ("qwen/", LOW),
)


def propagation_resistance_of(model_id: str) -> float:
    """Return the measured propagation resistance for a model alias.

    Returns ``UNMEASURED`` (0.0) for anything the paper did not test. Callers
    must treat that as "unknown, therefore not trusted for a terminal role",
    never as "fine by default".
    """
    served = (resolved_model_of(model_id) or model_id or "").lower().lstrip("~")
    best_score = UNMEASURED
    best_len = -1
    for prefix, score in _RESISTANCE_BY_SERVED_PREFIX:
        if served.startswith(prefix) and len(prefix) > best_len:
            best_score, best_len = score, len(prefix)
    return best_score


def is_measured(model_id: str) -> bool:
    """Whether this model has a published resistance measurement at all.

    Distinguishing "measured as weak" from "never measured" matters for
    operators: the first is a routing decision, the second is a gap in the
    evidence base that new research could close.
    """
    return propagation_resistance_of(model_id) > UNMEASURED


__all__ = [
    "UNMEASURED",
    "LOW",
    "MEDIUM",
    "HIGH",
    "propagation_resistance_of",
    "is_measured",
]

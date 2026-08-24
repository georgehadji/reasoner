"""Domain value objects for model capability profiles (ACR Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelConstraints:
    """Hard limits for a model — used for filtering, not ranking.

    All values derived from provider documentation and OpenRouter metadata.
    """

    max_context_tokens: int = 4096
    cost_per_1k_input_usd: float = 0.0
    cost_per_1k_output_usd: float = 0.0
    supports_tools: bool = False
    supports_vision: bool = False
    supports_streaming: bool = True
    supports_json_mode: bool = False
    supports_temperature: bool = True  # o-series doesn't
    vendor: str = ""
    bloc: str = ""  # "US", "CN", "EU", "OTHER"
    # Fully-qualified served model string (e.g. "anthropic/claude-sonnet-5").
    # Two registry aliases can point at the same served model; selection code
    # compares this — not model_id — to tell a real alternative from a rename.
    served_model: str = ""
    # Provenance of the fields above: "catalogue" (OpenRouter snapshot),
    # "hint" (hand-maintained override), or "unknown" (nothing found).
    # Selection excludes "unknown" — guessed limits would either bar a good
    # model from every role or let a bad one through a cost ceiling.
    data_source: str = "unknown"


@dataclass(frozen=True)
class ModelCapabilities:
    """Measured capability scores (0.0–1.0 normalized).

    All values must derive from benchmarks or production telemetry —
    never hand-assigned subjective scores.

    The ``scores`` dict maps dimension names (e.g. "reasoning", "coding")
    to float values in [0.0, 1.0]. Dimension names follow the role
    requirement conventions from the TaskRequirement system.
    """

    scores: dict[str, float] = field(default_factory=dict)
    source: str = "unknown"  # "benchmark_v1", "telemetry_7d", "combined"
    measured_at: str = ""  # ISO-8601 UTC
    sample_count: int = 0  # How many datapoints back this profile

    def get_score(self, dimension: str, default: float = 0.0) -> float:
        """Get the score for a capability dimension with a default fallback."""
        return self.scores.get(dimension, default)


@dataclass(frozen=True)
class ModelProfile:
    """Complete model profile: identity + constraints + capabilities.

    This is the primary value object used by the Adaptive Router for
    model selection decisions.
    """

    model_id: str  # e.g. "claude-sonnet"
    constraints: ModelConstraints
    capabilities: ModelCapabilities | None = None  # None = no data yet (cold start)

    @property
    def has_capabilities(self) -> bool:
        """Whether capability scores are available."""
        return self.capabilities is not None and len(self.capabilities.scores) > 0

    @property
    def cost_per_1k_total_usd(self) -> float:
        """Combined input + output cost per 1K tokens."""
        return self.constraints.cost_per_1k_input_usd + self.constraints.cost_per_1k_output_usd


__all__ = [
    "ModelConstraints",
    "ModelCapabilities",
    "ModelProfile",
]

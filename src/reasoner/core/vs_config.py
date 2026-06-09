"""Verbalized Sampling configuration models and vertical registry."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from reasoner.core.vs_constants import (
    VS_K_GENERATION,
    VS_TAIL_THRESHOLD_RADIOLOGY,
)


class VSDeploymentProfile(str, Enum):
    LATENCY_SENSITIVE = "latency_sensitive"
    BALANCED = "balanced"
    MAX_ACCURACY = "max_accuracy"


class VSFeatureFlags(BaseModel):
    probe_generation: bool = True
    decomposition: bool = True
    coverage_audit: bool = True
    generation: bool = True
    calibration: bool = True
    claim_extraction: bool = True
    verification_routing: bool = True
    conflict_surfacing: bool = True
    behavioral_audit: bool = True

    @classmethod
    def all_disabled(cls) -> "VSFeatureFlags":
        return cls(**{k: False for k in cls.model_fields})


class VSVerticalConfig(BaseModel):
    domain: str = Field(..., min_length=1)
    k: int = Field(..., ge=2)
    tail_threshold: float = Field(..., gt=0.0, lt=1.0)
    generation_strategy: str = "best_verifiable"
    probe_template: str = ""
    compliance_flags: list[str] = Field(default_factory=list)

    @field_validator("k")
    @classmethod
    def k_reasonable(cls, v: int) -> int:
        if v > 20:
            raise ValueError("k > 20 is excessive")
        return v


class VSVerticalRegistry:
    _configs: dict[str, VSVerticalConfig] = {}

    @classmethod
    def register(cls, config: VSVerticalConfig) -> None:
        cls._configs[config.domain] = config

    @classmethod
    def get(cls, domain: str) -> VSVerticalConfig:
        return cls._configs.get(
            domain,
            VSVerticalConfig(
                domain="default",
                k=VS_K_GENERATION,
                tail_threshold=VS_TAIL_THRESHOLD_RADIOLOGY,
            ),
        )

    @classmethod
    def clear(cls) -> None:
        cls._configs.clear()

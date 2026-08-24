"""
Reasoner Domain Models - Pure Business Entities
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache


class TaskType(str, Enum):
    ANALYTICAL = "analytical"
    STRATEGIC = "strategic"
    CREATIVE = "creative"
    TECHNICAL = "technical"
    PREDICTIVE = "predictive"
    HYBRID = "hybrid"

    @classmethod
    def coerce(cls, value: str | TaskType) -> TaskType:
        if isinstance(value, cls):
            return value
        raw = str(value).lower().strip()
        try:
            return cls(raw)
        except ValueError:
            return cls.HYBRID


class ClaimLabel(str, Enum):
    VERIFIED = "VERIFIED"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


class PerspectiveType(str, Enum):
    CONSTRUCTIVE = "constructive"
    DESTRUCTIVE = "destructive"
    SYSTEMIC = "systemic"
    MINIMALIST = "minimalist"


class PerspectiveRegistry:
    """Runtime-validatable registry of perspective types."""
    _known: dict[str, str] = {
        "constructive": "Constructive analysis",
        "destructive": "Destructive critique",
        "systemic": "Systemic view",
        "minimalist": "Minimalist approach",
    }

    @classmethod
    def register(cls, name: str, description: str) -> None:
        cls._known[name.lower()] = description

    @classmethod
    @lru_cache(maxsize=64)
    def validate(cls, value: str) -> bool:
        return value.lower() in cls._known

    @classmethod
    def coerce(cls, value: str) -> PerspectiveType | str:
        try:
            return PerspectiveType(value)
        except ValueError as exc:
            if cls.validate(value):
                return value.lower()
            raise ValueError(f"Unknown perspective: {value}") from exc

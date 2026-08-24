"""
Widget Protocol (Hexagonal Architecture Port)

Defines the interface that all widgets must implement.
The domain layer depends only on this protocol, not concrete implementations.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class WidgetType(str, Enum):
    """Types of widgets available in Reasoner."""
    WEATHER = "weather"
    STOCKS = "stocks"
    CALCULATOR = "calculator"
    DISCOVER = "discover"
    IMAGE_SEARCH = "image_search"
    VIDEO_SEARCH = "video_search"
    SUGGESTIONS = "suggestions"


@dataclass
class WidgetResult:
    """
    Result from widget execution.
    
    Contains all data needed to render the widget in the UI.
    """
    widget_type: WidgetType
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'widget_type': self.widget_type.value,
            'success': self.success,
            'data': self.data,
            'error': self.error,
            'duration': self.duration_seconds,
            'metadata': self.metadata,
        }

    @classmethod
    def success_result(
        cls,
        widget_type: WidgetType,
        data: dict[str, Any],
        duration: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> WidgetResult:
        """Create a success result."""
        return cls(
            widget_type=widget_type,
            success=True,
            data=data,
            duration_seconds=duration,
            metadata=metadata or {},
        )

    @classmethod
    def error_result(
        cls,
        widget_type: WidgetType,
        error: str,
        duration: float = 0.0,
    ) -> WidgetResult:
        """Create an error result."""
        return cls(
            widget_type=widget_type,
            success=False,
            error=error,
            duration_seconds=duration,
        )


@runtime_checkable
class Widget(Protocol):
    """
    Protocol for widgets (Hexagonal Architecture Port).
    
    Any class that implements this protocol can be used as a widget,
    regardless of inheritance.
    
    This is the interface that the domain layer depends on.
    """

    name: str
    """Unique identifier for the widget."""

    widget_type: WidgetType
    """Type of widget."""

    trigger_patterns: list[re.Pattern]
    """Regex patterns to detect when widget should activate."""

    description: str
    """Human-readable description of the widget."""

    async def detect(self, query: str) -> bool:
        """
        Detect if this widget should activate for the given query.
        
        Args:
            query: User's input query
        
        Returns:
            True if widget should activate
        """
        ...

    async def execute(self, params: dict[str, Any]) -> WidgetResult:
        """
        Execute the widget with given parameters.
        
        Args:
            params: Parameters extracted from the query
        
        Returns:
            WidgetResult with data or error
        """
        ...

    def extract_params(self, query: str) -> dict[str, Any] | None:
        """
        Extract parameters from the query.
        
        Args:
            query: User's input query
        
        Returns:
            Dictionary of parameters, or None if no match
        """
        ...


class BaseWidget(ABC):
    """
    Base class for widgets with common functionality.
    
    Provides:
    - Pattern matching for detection
    - Parameter extraction
    - Error handling
    
    Subclasses must implement:
    - name, widget_type, description
    - _execute_impl(): The actual widget logic
    """

    name: str
    widget_type: WidgetType
    description: str
    trigger_patterns: list[re.Pattern]

    def __init__(self):
        self._initialized = False

    async def detect(self, query: str) -> bool:
        """Detect if widget should activate based on patterns."""
        query_lower = query.lower()

        for pattern in self.trigger_patterns:
            if pattern.search(query_lower):
                return True

        return False

    def extract_params(self, query: str) -> dict[str, Any] | None:
        """Extract parameters from query using regex patterns."""
        for pattern in self.trigger_patterns:
            match = pattern.search(query)
            if match:
                return self._extract_from_match(match, query)

        return None

    def _extract_from_match(
        self,
        match: re.Match,
        query: str,
    ) -> dict[str, Any]:
        """
        Extract parameters from regex match.
        
        Override in subclasses for custom extraction.
        """
        # Default: return all named groups
        return match.groupdict()

    async def execute(self, params: dict[str, Any]) -> WidgetResult:
        """Execute with error handling."""
        import time

        start_time = time.perf_counter()

        try:
            data = await self._execute_impl(params)
            duration = time.perf_counter() - start_time

            return WidgetResult.success_result(
                widget_type=self.widget_type,
                data=data,
                duration=duration,
            )

        except Exception as e:
            duration = time.perf_counter() - start_time

            return WidgetResult.error_result(
                widget_type=self.widget_type,
                error=str(e),
                duration=duration,
            )

    @abstractmethod
    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Implement the actual widget logic.
        
        Subclasses must override this with widget-specific logic.
        """
        ...


# ─────────────────────────────────────────────────────────────────────
# WIDGET DETECTION RESULT
# ─────────────────────────────────────────────────────────────────────

@dataclass
class WidgetDetectionResult:
    """Result from widget detection."""
    widget: Widget
    confidence: float
    params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'widget_name': self.widget.name,
            'widget_type': self.widget.widget_type.value,
            'confidence': self.confidence,
            'params': self.params,
        }

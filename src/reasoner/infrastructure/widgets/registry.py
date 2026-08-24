"""
Widget Registry

Central registry for all available widgets.
Handles discovery, execution, and lifecycle management.
"""

from __future__ import annotations

import logging
from typing import Any

from reasoner.infrastructure.widgets.protocol import (
    Widget,
    WidgetDetectionResult,
    WidgetResult,
    WidgetType,
)

logger = logging.getLogger(__name__)


class WidgetRegistry:
    """
    Central registry for all widgets.
    
    Provides:
    - Widget registration
    - Auto-detection from queries
    - Execution orchestration
    - Health tracking
    """

    def __init__(self):
        self._widgets: dict[str, Widget] = {}
        self._widgets_by_type: dict[WidgetType, Widget] = {}
        self._execution_count: dict[str, int] = {}
        self._error_count: dict[str, int] = {}

    def register(self, widget: Widget) -> None:
        """
        Register a widget.
        
        Args:
            widget: Widget instance to register
        """
        self._widgets[widget.name] = widget
        self._widgets_by_type[widget.widget_type] = widget
        self._execution_count[widget.name] = 0
        self._error_count[widget.name] = 0

        logger.info(f"Registered widget: {widget.name} ({widget.widget_type.value})")

    def unregister(self, widget_name: str) -> None:
        """
        Unregister a widget.
        
        Args:
            widget_name: Name of widget to unregister
        """
        if widget_name in self._widgets:
            widget = self._widgets[widget_name]
            del self._widgets[widget_name]
            del self._widgets_by_type[widget.widget_type]
            logger.info(f"Unregistered widget: {widget_name}")

    def get_widget(self, name: str) -> Widget | None:
        """Get widget by name."""
        return self._widgets.get(name)

    def get_widget_by_type(self, widget_type: WidgetType) -> Widget | None:
        """Get widget by type."""
        return self._widgets_by_type.get(widget_type)

    async def detect_widgets(self, query: str) -> list[WidgetDetectionResult]:
        """
        Detect all widgets that should activate for a query.
        
        Args:
            query: User's input query
        
        Returns:
            List of detection results, sorted by confidence
        """
        results = []

        for widget in self._widgets.values():
            try:
                should_activate = await widget.detect(query)

                if should_activate:
                    params = widget.extract_params(query) or {}

                    # Calculate confidence based on pattern match quality
                    confidence = self._calculate_confidence(widget, query, params)

                    results.append(WidgetDetectionResult(
                        widget=widget,
                        confidence=confidence,
                        params=params,
                    ))

            except Exception as e:
                logger.error(f"Error detecting widget {widget.name}: {e}")

        # Sort by confidence (highest first)
        results.sort(key=lambda r: r.confidence, reverse=True)

        return results

    def _calculate_confidence(
        self,
        widget: Widget,
        query: str,
        params: dict[str, Any],
    ) -> float:
        """
        Calculate confidence score for widget detection.
        
        Factors:
        - Number of matched patterns
        - Parameter completeness
        - Query length
        """
        confidence = 0.5  # Base confidence

        # Boost for each matched pattern
        matched_patterns = sum(
            1 for pattern in widget.trigger_patterns
            if pattern.search(query.lower())
        )
        confidence += min(matched_patterns * 0.15, 0.3)

        # Boost for complete parameters
        if params:
            confidence += 0.1

        # Boost for specific parameter values
        for value in params.values():
            if value and len(str(value)) > 2:
                confidence += 0.05

        return min(confidence, 1.0)

    async def execute_widget(
        self,
        widget_name: str,
        params: dict[str, Any],
    ) -> WidgetResult:
        """
        Execute a widget by name.

        Args:
            widget_name: Name of widget to execute
            params: Parameters for execution

        Returns:
            WidgetResult with data or error
            
        Raises:
            ValueError: If widget not found
            RuntimeError: If widget execution fails
        """
        widget = self.get_widget(widget_name)

        if not widget:
            logger.warning(f"Widget '{widget_name}' not found")
            return WidgetResult.error_result(
                widget_type=WidgetType.CALCULATOR,
                error=f"Widget '{widget_name}' not found",
            )

        self._execution_count[widget_name] = (
            self._execution_count.get(widget_name, 0) + 1
        )

        try:
            result = await widget.execute(params)

            if not result.success:
                self._error_count[widget_name] = (
                    self._error_count.get(widget_name, 0) + 1
                )
                logger.warning(f"Widget {widget_name} execution failed: {result.error}")

            return result
        except Exception as e:
            self._error_count[widget_name] = (
                self._error_count.get(widget_name, 0) + 1
            )
            logger.error(f"Unexpected error executing widget {widget_name}: {e}")
            return WidgetResult.error_result(
                widget_type=widget.widget_type,
                error=str(e),
            )

    async def auto_execute(
        self,
        query: str,
        max_widgets: int = 1,
    ) -> list[WidgetResult]:
        """
        Auto-detect and execute widgets for a query.
        
        Args:
            query: User's input query
            max_widgets: Maximum number of widgets to execute
        
        Returns:
            List of execution results
        """
        detections = await self.detect_widgets(query)

        if not detections:
            return []

        results = []

        for detection in detections[:max_widgets]:
            result = await self.execute_widget(
                detection.widget.name,
                detection.params,
            )
            results.append(result)

        return results

    def list_widgets(self) -> list[dict[str, Any]]:
        """List all registered widgets with metadata."""
        return [
            {
                'name': widget.name,
                'type': widget.widget_type.value,
                'description': widget.description,
                'execution_count': self._execution_count.get(widget.name, 0),
                'error_count': self._error_count.get(widget.name, 0),
                'success_rate': self._get_success_rate(widget.name),
            }
            for widget in self._widgets.values()
        ]

    def _get_success_rate(self, widget_name: str) -> float:
        """Calculate success rate for a widget."""
        executions = self._execution_count.get(widget_name, 0)
        errors = self._error_count.get(widget_name, 0)

        if executions == 0:
            return 1.0

        return (executions - errors) / executions

    def clear_stats(self) -> None:
        """Clear execution statistics."""
        self._execution_count.clear()
        self._error_count.clear()


# ─────────────────────────────────────────────────────────────────────
# GLOBAL REGISTRY INSTANCE
# ─────────────────────────────────────────────────────────────────────

_registry: WidgetRegistry | None = None


def get_widget_registry() -> WidgetRegistry:
    """Get or create the global widget registry."""
    global _registry
    if _registry is None:
        _registry = WidgetRegistry()
        _register_default_widgets(_registry)
    return _registry


def reset_widget_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None


def _register_default_widgets(registry: WidgetRegistry) -> None:
    """Register default widgets."""
    # Import here to avoid circular dependencies
    from reasoner.infrastructure.widgets.calculator import CalculatorWidget
    from reasoner.infrastructure.widgets.discover import DiscoverWidget
    from reasoner.infrastructure.widgets.image_search import ImageSearchWidget
    from reasoner.infrastructure.widgets.stocks import StockWidget
    from reasoner.infrastructure.widgets.video_search import VideoSearchWidget
    from reasoner.infrastructure.widgets.weather import WeatherWidget

    registry.register(WeatherWidget())
    registry.register(StockWidget())
    registry.register(CalculatorWidget())
    registry.register(DiscoverWidget())
    registry.register(ImageSearchWidget())
    registry.register(VideoSearchWidget())

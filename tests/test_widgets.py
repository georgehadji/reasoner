"""
Tests for Widget Protocol and Registry

Tests the widget plugin system.
"""

import pytest
import re

from reasoner.infrastructure.widgets.protocol import (
    WidgetType,
    WidgetResult,
    BaseWidget,
    WidgetDetectionResult,
)
from reasoner.infrastructure.widgets.registry import (
    WidgetRegistry,
    get_widget_registry,
    reset_widget_registry,
)


class TestWidgetResult:
    """Tests for WidgetResult dataclass."""
    
    def test_success_result_factory(self):
        """Test success_result class method."""
        result = WidgetResult.success_result(
            widget_type=WidgetType.WEATHER,
            data={"temperature": 25},
            duration=0.5,
        )
        
        assert result.success is True
        assert result.widget_type == WidgetType.WEATHER
        assert result.data["temperature"] == 25
        assert result.duration_seconds == 0.5
        assert result.error == ""
    
    def test_error_result_factory(self):
        """Test error_result class method."""
        result = WidgetResult.error_result(
            widget_type=WidgetType.CALCULATOR,
            error="Invalid expression",
            duration=0.1,
        )
        
        assert result.success is False
        assert result.widget_type == WidgetType.CALCULATOR
        assert result.error == "Invalid expression"
        assert result.duration_seconds == 0.1
    
    def test_to_dict(self):
        """Test result serialization."""
        result = WidgetResult.success_result(
            widget_type=WidgetType.STOCKS,
            data={"price": 150.50},
        )
        
        data = result.to_dict()
        
        assert data["widget_type"] == "stocks"
        assert data["success"] is True
        assert data["data"]["price"] == 150.50


class TestBaseWidget:
    """Tests for BaseWidget class."""
    
    @pytest.mark.asyncio
    async def test_detect_with_patterns(self):
        """Test widget detection with regex patterns."""
        class TestWidget(BaseWidget):
            name = "test"
            widget_type = WidgetType.CALCULATOR
            description = "Test widget"
            trigger_patterns = [
                re.compile(r'calculate\s+(.+)', re.I),
            ]
            
            async def _execute_impl(self, params):
                return {}
        
        widget = TestWidget()
        
        # Should detect
        assert await widget.detect("Calculate 2+2") is True
        assert await widget.detect("CALCULATE something") is True
        
        # Should not detect
        assert await widget.detect("Hello world") is False
    
    @pytest.mark.asyncio
    async def test_extract_params(self):
        """Test parameter extraction from query."""
        class TestWidget(BaseWidget):
            name = "test"
            widget_type = WidgetType.WEATHER
            description = "Test widget"
            trigger_patterns = [
                re.compile(r'weather(?:\s+in)?\s+(?P<location>[a-z\s]+)', re.I),
            ]
            
            async def _execute_impl(self, params):
                return {}
        
        widget = TestWidget()
        
        params = widget.extract_params("Weather in Athens")
        
        assert params is not None
        assert "location" in params
    
    @pytest.mark.asyncio
    async def test_execute_with_error_handling(self):
        """Test execution with error handling."""
        class FailingWidget(BaseWidget):
            name = "failing"
            widget_type = WidgetType.CALCULATOR
            description = "Always fails"
            trigger_patterns = []
            
            async def _execute_impl(self, params):
                raise ValueError("Intentional failure")
        
        widget = FailingWidget()
        
        result = await widget.execute({})
        
        assert result.success is False
        assert "Intentional failure" in result.error
        assert result.widget_type == WidgetType.CALCULATOR
    
    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful execution."""
        class SuccessWidget(BaseWidget):
            name = "success"
            widget_type = WidgetType.CALCULATOR
            description = "Always succeeds"
            trigger_patterns = []
            
            async def _execute_impl(self, params):
                return {"result": params.get("value", 0) * 2}
        
        widget = SuccessWidget()
        
        result = await widget.execute({"value": 21})
        
        assert result.success is True
        assert result.data["result"] == 42


class TestWidgetRegistry:
    """Tests for WidgetRegistry class."""
    
    @pytest.fixture
    def registry(self):
        """Create fresh registry for each test."""
        reg = WidgetRegistry()
        yield reg
    
    def test_register_widget(self, registry):
        """Test widget registration."""
        class TestWidget(BaseWidget):
            name = "test_widget"
            widget_type = WidgetType.CALCULATOR
            description = "Test"
            trigger_patterns = []
            
            async def _execute_impl(self, params):
                return {}
        
        widget = TestWidget()
        registry.register(widget)
        
        assert registry.get_widget("test_widget") is widget
        assert registry.get_widget_by_type(WidgetType.CALCULATOR) is widget
    
    def test_unregister_widget(self, registry):
        """Test widget unregistration."""
        class TestWidget(BaseWidget):
            name = "test_widget"
            widget_type = WidgetType.CALCULATOR
            description = "Test"
            trigger_patterns = []
            
            async def _execute_impl(self, params):
                return {}
        
        widget = TestWidget()
        registry.register(widget)
        registry.unregister("test_widget")
        
        assert registry.get_widget("test_widget") is None
    
    @pytest.mark.asyncio
    async def test_detect_widgets(self, registry):
        """Test widget detection."""
        class WeatherTestWidget(BaseWidget):
            name = "weather_test"
            widget_type = WidgetType.WEATHER
            description = "Weather test"
            trigger_patterns = [re.compile(r'weather', re.I)]
            
            async def _execute_impl(self, params):
                return {}
        
        registry.register(WeatherTestWidget())
        
        results = await registry.detect_widgets("What's the weather?")
        
        assert len(results) > 0
        assert results[0].widget.name == "weather_test"
    
    @pytest.mark.asyncio
    async def test_execute_widget(self, registry):
        """Test widget execution via registry."""
        class CalcTestWidget(BaseWidget):
            name = "calc_test"
            widget_type = WidgetType.CALCULATOR
            description = "Calc test"
            trigger_patterns = []
            
            async def _execute_impl(self, params):
                return {"sum": params.get("a", 0) + params.get("b", 0)}
        
        registry.register(CalcTestWidget())
        
        result = await registry.execute_widget("calc_test", {"a": 5, "b": 3})
        
        assert result.success is True
        assert result.data["sum"] == 8
    
    @pytest.mark.asyncio
    async def test_auto_execute(self, registry):
        """Test auto-detection and execution."""
        class AutoWidget(BaseWidget):
            name = "auto"
            widget_type = WidgetType.CALCULATOR
            description = "Auto test"
            trigger_patterns = [re.compile(r'auto\s+(?P<number>\d+)', re.I)]
            
            async def _execute_impl(self, params):
                return {"value": int(params.get("number", 0))}
        
        registry.register(AutoWidget())
        
        results = await registry.auto_execute("auto 42")
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].data["value"] == 42
    
    def test_list_widgets(self, registry):
        """Test listing registered widgets."""
        class ListWidget(BaseWidget):
            name = "list_widget"
            widget_type = WidgetType.WEATHER
            description = "List test"
            trigger_patterns = []
            
            async def _execute_impl(self, params):
                return {}
        
        registry.register(ListWidget())
        
        widgets = registry.list_widgets()
        
        assert len(widgets) > 0
        widget_info = widgets[-1]
        assert widget_info["name"] == "list_widget"
        assert widget_info["type"] == "weather"
    
    @pytest.mark.asyncio
    async def test_execution_stats(self, registry):
        """Test execution statistics tracking."""
        class StatsWidget(BaseWidget):
            name = "stats"
            widget_type = WidgetType.CALCULATOR
            description = "Stats"
            trigger_patterns = []
            
            async def _execute_impl(self, params):
                if params.get("fail"):
                    raise ValueError("Fail")
                return {}
        
        registry.register(StatsWidget())
        
        # Successful execution
        await registry.execute_widget("stats", {})
        
        # Failed execution
        await registry.execute_widget("stats", {"fail": True})
        
        # Check stats
        widgets = registry.list_widgets()
        stats = [w for w in widgets if w["name"] == "stats"][0]
        
        assert stats["execution_count"] == 2
        assert stats["error_count"] == 1
        assert stats["success_rate"] == 0.5


class TestGlobalRegistry:
    """Tests for global widget registry."""
    
    def test_get_widget_registry_singleton(self):
        """Test that get_widget_registry returns singleton."""
        reset_widget_registry()
        
        reg1 = get_widget_registry()
        reg2 = get_widget_registry()
        
        assert reg1 is reg2
        
        reset_widget_registry()
    
    def test_reset_widget_registry(self):
        """Test resetting global registry."""
        reset_widget_registry()
        
        reg = get_widget_registry()
        initial_count = len(reg.list_widgets())
        
        # Should have default widgets registered
        assert initial_count > 0
        
        reset_widget_registry()

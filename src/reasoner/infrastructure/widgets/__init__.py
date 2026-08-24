"""
Infrastructure Widgets Package
"""

from reasoner.infrastructure.widgets.calculator import CalculatorWidget
from reasoner.infrastructure.widgets.discover import DiscoverWidget
from reasoner.infrastructure.widgets.image_search import ImageSearchWidget
from reasoner.infrastructure.widgets.protocol import Widget, WidgetResult, WidgetType
from reasoner.infrastructure.widgets.registry import WidgetRegistry, get_widget_registry
from reasoner.infrastructure.widgets.stocks import StockWidget
from reasoner.infrastructure.widgets.video_search import VideoSearchWidget
from reasoner.infrastructure.widgets.weather import WeatherWidget

__all__ = [
    'Widget',
    'WidgetResult',
    'WidgetType',
    'WidgetRegistry',
    'get_widget_registry',
    'WeatherWidget',
    'StockWidget',
    'CalculatorWidget',
    'DiscoverWidget',
    'ImageSearchWidget',
    'VideoSearchWidget',
]

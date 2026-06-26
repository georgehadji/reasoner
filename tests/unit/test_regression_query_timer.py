import pytest
from reasoner.api.metrics import QueryTimer

def test_query_timer_import_and_functional():
    """Verify that QueryTimer is correctly defined and works."""
    timer = QueryTimer(preset="test-preset")
    timer.start()
    # It should not crash on observe
    timer.observe()

def test_api_init_imports_query_timer():
    """Verify that the reasoner.api module can be imported without QueryTimer failures."""
    # Ensure reasoner.api package can resolve and import QueryTimer as expected
    import reasoner.api
    assert hasattr(reasoner.api, "_run_stream_with_metrics")

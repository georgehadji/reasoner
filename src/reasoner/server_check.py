#!/usr/bin/env python
"""
Reasoner - Server Startup Test

This script verifies that all components are properly configured
and the server is ready to start.
"""

import sys
import os

# Add src directory to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))

def check_component(name, func):
    """Check a component and print status."""
    try:
        result = func()
        print(f"[OK]   {name}")
        return True
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
        return False

def main():
    print("=" * 60)
    print("  Reasoner - AI Reasoning Platform")
    print("  Server Readiness Check")
    print("=" * 60)
    print()
    
    checks = []
    
    # Check 1: Domain Events
    def check_events():
        from reasoner.core.events.domain_events import PipelineStarted, EventType
        return True
    checks.append(check_component("Domain Events", check_events))
    
    # Check 2: Persistence
    def check_persistence():
        from reasoner.infrastructure.persistence import get_event_store
        store = get_event_store()
        return True
    checks.append(check_component("Persistence", check_persistence))
    
    # Check 3: Handlers
    def check_handlers():
        from reasoner.application.handlers import get_handler_registry
        from reasoner.infrastructure.llm.ports import BaseLLMProvider, LLMResponse
        
        class DummyProvider(BaseLLMProvider):
            async def _complete_impl(self, messages, config):
                return LLMResponse(content="test", model_used="test")
            async def _complete_stream_impl(self, messages, config):
                yield "test"
            @property
            def provider_name(self):
                return "test"
        
        registry = get_handler_registry(DummyProvider(model="test"), None)
        return True
    checks.append(check_component("Handlers", check_handlers))
    
    # Check 4: WebSocket
    def check_websocket():
        from reasoner.infrastructure.websocket import get_websocket_manager
        manager = get_websocket_manager()
        return True
    checks.append(check_component("WebSocket", check_websocket))
    
    # Check 5: API App
    def check_api():
        from reasoner.api import app
        return app.title == "Reasoner v2.0"
    checks.append(check_component("API App", check_api))
    
    # Check 6: LLM Providers
    def check_llm():
        from reasoner.infrastructure.llm.registry import _REGISTRY as registry
        return len(registry) > 10
    checks.append(check_component("LLM Providers", check_llm))
    
    # Check 6b: OpenRouter key quota (soft check - warns but does not fail)
    def check_openrouter_key():
        import httpx
        from reasoner.core.settings import settings
        key = settings.OPENROUTER_API_KEY or ""
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        from reasoner.core.constants import OPENROUTER_AUTH_KEY_URL
        r = httpx.get(
            OPENROUTER_AUTH_KEY_URL,
            headers={"Authorization": f"Bearer {key}"},
            timeout=10.0,
        )
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        data = r.json()
        limit = data.get("data", {}).get("limit", None)
        usage = data.get("data", {}).get("usage", 0)
        if limit is not None and usage >= limit:
            raise RuntimeError(f"Quota exceeded ({usage}/{limit})")
        return True
    
    try:
        check_openrouter_key()
        print("[OK]   OpenRouter Key: Quota available")
    except Exception as e:
        print(f"[WARN] OpenRouter Key: {e} — requests will fail with 403")
    
    # Check 7: Widgets
    def check_widgets():
        from reasoner.infrastructure.widgets import get_widget_registry
        registry = get_widget_registry()
        return len(registry.list_widgets()) > 0
    checks.append(check_component("Widgets", check_widgets))
    
    # Check 8: SearXNG (soft check - warns but does not fail)
    def check_searxng():
        from reasoner.core.settings import settings
        from reasoner.core.constants import TIMEOUTS
        import httpx
        url = settings.SEARXNG_URL + "/healthz"
        r = httpx.get(url, timeout=TIMEOUTS.HEALTH_CHECK)
        return r.status_code == 200
    
    try:
        if check_searxng():
            print("[OK]   SearXNG: OK")
        else:
            print("[WARN] SearXNG: Not reachable (web search will be disabled)")
    except Exception as e:
        print(f"[WARN] SearXNG: Not reachable ({e}) - web search will be disabled")
    
    print()
    print("=" * 60)
    
    if all(checks):
        print("  [OK] All checks passed! Server is ready to start.")
        print()
        print("  To start the server:")
        print("    python start_all.py")
        print("  Or:")
        from reasoner.core.settings import settings
        print(f"    python -m uvicorn asgi:app --host {settings.UVICORN_HOST} --port {settings.SERVER_PORT}")
        print()
        print(f"  Then open: http://{settings.SERVER_HOST}:{settings.SERVER_PORT}")
        print("=" * 60)
        return 0
    else:
        failed = len([c for c in checks if not c])
        print(f"  [FAIL] {failed} check(s) failed. Please fix the issues above.")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())

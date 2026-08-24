"""Tests for GET /api/presets and GET /api/models endpoints."""

from fastapi.testclient import TestClient

from reasoner.api import app

client = TestClient(app)


class TestPresetsEndpoint:
    """Verify /api/presets returns public preset metadata."""

    def test_presets_returns_non_empty_dict(self):
        response = client.get("/api/presets")
        assert response.status_code == 200
        data = response.json()
        assert "presets" in data
        assert isinstance(data["presets"], dict)
        assert len(data["presets"]) > 0

    def test_presets_have_required_keys(self):
        response = client.get("/api/presets")
        data = response.json()
        for _preset_id, meta in data["presets"].items():
            assert "name" in meta
            assert "description" in meta
            assert "primary_id" in meta
            assert isinstance(meta["name"], str)
            assert isinstance(meta["description"], str)

    def test_presets_do_not_expose_routing_tables(self):
        """Security: routing tables and API keys must not be exposed."""
        response = client.get("/api/presets")
        data = response.json()
        raw = str(data)
        assert "routing" not in raw.lower() or "fallback_routing" not in raw.lower()
        assert "OPENROUTER_API_KEY" not in raw
        assert "api_key" not in raw.lower()


class TestModelsEndpoint:
    """Verify /api/models returns public model metadata."""

    def test_models_returns_non_empty_groups(self):
        response = client.get("/api/models")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Should have at least openrouter group
        assert "openrouter" in data
        assert len(data["openrouter"]) > 0

    def test_models_are_strings(self):
        response = client.get("/api/models")
        data = response.json()
        for _group, models in data.items():
            for model_id in models:
                assert isinstance(model_id, str)
                assert len(model_id) > 0

    def test_models_do_not_expose_api_keys(self):
        """Security: no secrets in model list response."""
        response = client.get("/api/models")
        data = response.json()
        raw = str(data)
        assert "sk-or-v1" not in raw
        assert "api_key" not in raw.lower()

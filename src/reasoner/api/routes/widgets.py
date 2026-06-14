"""Widget, suggestions, and UI status endpoints."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from reasoner.api.auth_deps import require_csrf

from reasoner.api.schemas import SuggestionRequestModel
from reasoner.application.commands import ExecuteWidgetCommand
from reasoner.presets import PRESETS
from reasoner.infrastructure.llm.registry import list_models
from reasoner.sanitization import sanitize_for_prompt
from reasoner.suggestions import generate_suggestions_async, SuggestionRequest

logger = logging.getLogger(__name__)
router = APIRouter()


class ExecuteWidgetRequest(BaseModel):
    """Lightweight request DTO for widget execution.

    The backend constructs the full ExecuteWidgetCommand internally,
    generating command_id and timestamp server-side.
    """
    widget_type: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    auto_detect: bool = True
    query: str = ""


@router.get("/api/ui/status")
async def ui_status():
    """Check if UI integration is available."""
    return {
        "available": True,
        "endpoints": {
            "run_with_context": "/api/run-with-context",
        },
        # SECURITY: Do not expose supported methods or presets
    }


@router.get("/api/presets")
async def api_presets() -> dict[str, Any]:
    """Return all presets with public metadata.

    Only names, descriptions, and methods are exposed.
    No API keys or routing tables are included.
    """
    return {
        "presets": {
            preset_id: {
                "name": preset.name,
                "description": preset.description,
                "primary_id": preset.primary_id,
            }
            for preset_id, preset in PRESETS.items()
        }
    }


@router.get("/api/models")
async def api_models() -> dict[str, list[str]]:
    """Return all registered model IDs grouped by provider.

    No API keys or internal configuration are exposed.
    """
    return list_models()


@router.post("/api/suggestions")
async def get_suggestions(req: SuggestionRequestModel):
    """Get smart search suggestions based on query."""
    try:
        request = SuggestionRequest(
            query=req.query,
            chat_history=req.chat_history,
            max_suggestions=req.max_suggestions,
        )
        response = await generate_suggestions_async(request)
        return {"suggestions": response.suggestions, "query": response.query}
    except Exception as e:
        logger.error(f"Suggestions error: {e}")
        return {"suggestions": [], "query": req.query}


@router.post("/api/widget/execute")
async def execute_widget(
    req: ExecuteWidgetRequest,
    csrf_checked=Depends(require_csrf),
) -> dict[str, Any]:
    """Execute widget using new architecture.

    Supports auto-detection from query or explicit widget execution.
    """
    try:
        from reasoner.api import get_architecture_components

        _, handler_registry = get_architecture_components()

        sanitized_query, _ = sanitize_for_prompt(req.query)

        command = ExecuteWidgetCommand(
            command_id=str(uuid.uuid4()),
            timestamp=time.time(),
            widget_type=req.widget_type,
            params=req.params,
            auto_detect=req.auto_detect,
            query=sanitized_query,
        )
        result = await handler_registry.handle_command(command)
        return result
    except Exception as e:
        logger.error(f"Widget execution error: {e}")
        return {"error": "Internal server error", "detected": False}


@router.get("/api/widgets/list")
async def list_widgets():
    """List all available widgets."""
    try:
        from reasoner.infrastructure.widgets import get_widget_registry

        registry = get_widget_registry()
        widgets = registry.list_widgets()
        return {"widgets": widgets, "total": len(widgets)}
    except Exception as e:
        logger.error(f"List widgets error: {e}")
        return {"error": "Internal server error", "widgets": []}


@router.get("/api/widgets/detect")
async def detect_widgets(query: str = ""):
    """Detect widgets for a query."""
    try:
        from reasoner.infrastructure.widgets import get_widget_registry

        registry = get_widget_registry()
        detections = await registry.detect_widgets(query)
        return {
            "detected": len(detections) > 0,
            "widgets": [d.to_dict() for d in detections],
        }
    except Exception as e:
        logger.error(f"Widget detection error: {e}")
        return {"detected": False, "widgets": []}

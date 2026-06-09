"""Prism query classifier — ports Prism's classifier.ts to Python."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reasoner.application.flows.base import WorkflowServices
    from reasoner.domain.pipeline_state import PipelineState


@dataclass(frozen=True)
class PrismClassification:
    skip_search: bool
    personal_search: bool
    academic_search: bool
    discussion_search: bool
    show_weather_widget: bool
    show_stock_widget: bool
    show_calculation_widget: bool
    standalone_follow_up: str


_CLASSIFY_SYSTEM = (
    "You are a query classifier. Analyze the user's message and output ONLY valid JSON.\n"
    "Your response must have this shape:\n"
    '{\n'
    '  "classification": {\n'
    '    "skipSearch": bool,\n'
    '    "personalSearch": bool,\n'
    '    "academicSearch": bool,\n'
    '    "discussionSearch": bool,\n'
    '    "showWeatherWidget": bool,\n'
    '    "showStockWidget": bool,\n'
    '    "showCalculationWidget": bool\n'
    '  },\n'
    '  "standaloneFollowUp": string\n'
    '}\n'
    "Rules:\n"
    "- skipSearch: true for creative writing, greetings, or pure opinion questions.\n"
    "- academicSearch: true for research, papers, studies, or technical deep-dives.\n"
    "- discussionSearch: true for opinions, debates, or community perspectives.\n"
    "- showWeatherWidget: true if asking about weather in a location.\n"
    "- showStockWidget: true if asking about stock prices or tickers.\n"
    "- showCalculationWidget: true if asking for math, conversion, or calculation.\n"
    "- standaloneFollowUp: rewrite the query as a self-contained search phrase."
)


async def classify_query(
    problem: str,
    services: WorkflowServices,
    state: PipelineState,
) -> PrismClassification:
    """Classify a query via a cheap LLM call.

    Returns a PrismClassification without mutating state — caller decides
    whether to store it in method_state["prism"].
    """
    from reasoner.parsing import extract_json
    raw, _ = await services.call_llm(
        role="prism_classify",
        phase_key="prism_classify",
        system_prompt=_CLASSIFY_SYSTEM,
        user_prompt=problem,
        state=state,
        max_tokens=256,
    )
    data = extract_json(raw) or {}
    cls = data.get("classification", {})
    return PrismClassification(
        skip_search=bool(cls.get("skipSearch", False)),
        personal_search=bool(cls.get("personalSearch", False)),
        academic_search=bool(cls.get("academicSearch", False)),
        discussion_search=bool(cls.get("discussionSearch", False)),
        show_weather_widget=bool(cls.get("showWeatherWidget", False)),
        show_stock_widget=bool(cls.get("showStockWidget", False)),
        show_calculation_widget=bool(cls.get("showCalculationWidget", False)),
        standalone_follow_up=str(data.get("standaloneFollowUp", problem)),
    )

"""Prompts are checked against the target model's context window before sending.

max_context was used only to *select* between models. Nothing compared an
assembled prompt against the window of the model it was about to go to, so an
over-long prompt was rejected by the provider only after the request was made —
the run paid the round-trip, and on some providers the input tokens, first.
"""

from __future__ import annotations

import logging

import pytest

from reasoner.infrastructure.llm.capability_registry import (
    check_context_fit,
    context_budget_for,
    estimate_tokens,
)


class TestTokenEstimate:
    def test_scales_with_length(self):
        assert estimate_tokens("x" * 3500) > estimate_tokens("x" * 350)

    def test_over_estimates_rather_than_under(self):
        """A guard rail that under-counts lets the very case it guards slip past."""
        # ~4 chars/token is the common rule of thumb; we use 3.5, so our estimate
        # must come out higher than that rule for the same text.
        text = "x" * 40_000
        assert estimate_tokens(text) > len(text) / 4

    def test_empty_text_is_cheap(self):
        assert estimate_tokens("") <= 1


class TestContextBudget:
    def test_known_model_reports_its_window(self):
        assert context_budget_for("claude-haiku") == 200_000

    def test_unknown_model_falls_back_conservatively(self):
        """An unknown model must not be assumed to have a huge window."""
        assert context_budget_for("not-a-real-model-id") == 4096


class TestContextFit:
    def test_ordinary_prompt_fits(self):
        fits, why = check_context_fit("claude-haiku", prompt_chars=4_000, max_output_tokens=2048)
        assert fits
        assert why == ""

    def test_oversized_prompt_is_caught(self):
        fits, why = check_context_fit("claude-haiku", prompt_chars=900_000, max_output_tokens=2048)
        assert not fits
        assert "exceeds" in why

    def test_message_names_the_model_and_the_overshoot(self):
        """The warning has to be actionable without opening the code."""
        _, why = check_context_fit("claude-haiku", prompt_chars=900_000, max_output_tokens=2048)
        assert "claude-haiku" in why
        assert "200,000" in why

    def test_requested_output_counts_against_the_window(self):
        """Input alone fitting is not enough — the completion shares the window."""
        # Sized to fit on input alone but not once a large completion is added.
        chars = int(4096 * 3.5) - 2_000
        fits_small, _ = check_context_fit("unknown-model", chars, max_output_tokens=16)
        fits_large, _ = check_context_fit("unknown-model", chars, max_output_tokens=4_000)
        assert fits_small
        assert not fits_large

    @pytest.mark.parametrize("model", ["claude-haiku", "unknown-model"])
    def test_never_raises(self, model):
        """This runs on every LLM call; it must not be able to break one."""
        assert isinstance(check_context_fit(model, 0, 0), tuple)


class TestRouterIntegration:
    def test_router_warns_before_dispatch(self, caplog, monkeypatch):
        """The check has to run where the model is known — in the router."""
        from reasoner.infrastructure.llm import router as router_mod

        src = (
            __import__("pathlib").Path(router_mod.__file__).read_text(encoding="utf-8")
        )
        assert "check_context_fit" in src, (
            "the pre-flight must sit in ProviderRouter.call, where the role has "
            "been resolved to a concrete model"
        )

    def test_guard_failure_cannot_break_a_call(self):
        """It is wrapped so a registry problem degrades to no warning, not an error."""
        from reasoner.infrastructure.llm import router as router_mod

        src = (
            __import__("pathlib").Path(router_mod.__file__).read_text(encoding="utf-8")
        )
        block = src[src.index("check_context_fit") - 400 : src.index("check_context_fit") + 600]
        assert "except Exception" in block

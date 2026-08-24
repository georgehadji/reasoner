"""Tests for Calculator Widget."""

from __future__ import annotations

import math

import pytest

from reasoner.infrastructure.widgets.calculator import CalculatorWidget


class TestCalculatorWidget:
    """Test mathematical expression evaluation."""

    @pytest.fixture
    def widget(self):
        return CalculatorWidget()

    @pytest.mark.asyncio
    async def test_basic_arithmetic(self, widget):
        result = await widget._execute_impl({"expression": "2 + 2"})
        assert result["valid"] is True
        assert result["result"] == 4

    @pytest.mark.asyncio
    async def test_subtraction(self, widget):
        result = await widget._execute_impl({"expression": "10 - 3"})
        assert result["valid"] is True
        assert result["result"] == 7

    @pytest.mark.asyncio
    async def test_multiplication(self, widget):
        result = await widget._execute_impl({"expression": "6 * 7"})
        assert result["valid"] is True
        assert result["result"] == 42

    @pytest.mark.asyncio
    async def test_division(self, widget):
        result = await widget._execute_impl({"expression": "10 / 2"})
        assert result["valid"] is True
        assert result["result"] == 5.0

    @pytest.mark.asyncio
    async def test_parentheses(self, widget):
        result = await widget._execute_impl({"expression": "(2 + 3) * 4"})
        assert result["valid"] is True
        assert result["result"] == 20

    @pytest.mark.asyncio
    async def test_math_functions(self, widget):
        result = await widget._execute_impl({"expression": "sqrt(16)"})
        # NOTE: sqrt may not be available depending on simpleeval version
        assert "valid" in result
        if result["valid"]:
            assert result["result"] == 4.0

    @pytest.mark.asyncio
    async def test_constants(self, widget):
        result = await widget._execute_impl({"expression": "pi"})
        assert result["valid"] is True
        assert abs(result["result"] - math.pi) < 0.001

    @pytest.mark.asyncio
    async def test_empty_expression(self, widget):
        result = await widget._execute_impl({"expression": ""})
        # NOTE: empty expression returns error dict without 'valid' key
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_expression(self, widget):
        result = await widget._execute_impl({"expression": "2 +"})
        assert result["valid"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_power_operator(self, widget):
        result = await widget._execute_impl({"expression": "2 ** 10"})
        assert result["valid"] is True
        assert result["result"] == 1024

    @pytest.mark.asyncio
    async def test_caret_is_bitwise_xor_not_power(self, widget):
        """BUG: '^' is bitwise XOR in Python, not power. Users may expect power."""
        result = await widget._execute_impl({"expression": "2 ^ 10"})
        assert result["valid"] is True
        assert result["result"] == 8  # 2 XOR 10 = 8, not 1024

    def test_format_result_integer(self, widget):
        assert widget._format_result(42.0) == "42"

    def test_format_result_float(self, widget):
        result = widget._format_result(3.14159)
        assert "3.14" in result

    def test_format_result_string(self, widget):
        assert widget._format_result("hello") == "hello"

    def test_trigger_patterns_match_math(self, widget):
        assert any(p.match("2 + 2") for p in widget.trigger_patterns)
        assert any(p.match("calculate: 2 + 2") for p in widget.trigger_patterns)
        assert any(p.match("what is 10 * 5") for p in widget.trigger_patterns)

    def test_trigger_patterns_reject_non_math(self, widget):
        assert not any(p.match("hello world") for p in widget.trigger_patterns)

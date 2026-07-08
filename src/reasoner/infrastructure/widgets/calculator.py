"""
Calculator Widget

Evaluates mathematical expressions using asteval (BSD-licensed safe evaluator).
"""

from __future__ import annotations

import re
import math
from typing import Any

from reasoner.infrastructure.widgets.protocol import BaseWidget, WidgetResult, WidgetType


class CalculatorWidget(BaseWidget):
    """
    Calculator widget for mathematical expressions.

    Features:
    - Basic arithmetic: +, -, *, /
    - Advanced: sin, cos, tan, log, sqrt, etc.
    - Constants: pi, e
    - Parentheses support
    """

    name = "calculator"
    widget_type = WidgetType.CALCULATOR
    description = "Mathematical expression evaluation"

    trigger_patterns = [
        # Pure math expressions
        re.compile(r'^[\d\+\-\*\/\.\(\)\s\^%]+$', re.I),
        # With math functions
        re.compile(r'^(?:calculate|compute|eval)\s*:?\s*(.+)$', re.I),
        # With "what is"
        re.compile(r"^what'?s?\s+(.+)$", re.I),
        # Percentage calculations
        re.compile(r'(\d+(?:\.\d+)?)\s*%\s*(?:of)?\s*(\d+(?:\.\d+)?)', re.I),
    ]

    def _extract_from_match(
        self,
        match: re.Match,
        query: str,
    ) -> dict[str, Any]:
        """Extract expression from match."""
        expression = None

        # Check for pure math expression
        if re.match(r'^[\d\+\-\*\/\.\(\)\s\^%]+$', query.strip()):
            expression = query.strip()
        else:
            # Get from capture group
            if match.lastindex and match.lastindex >= 1:
                expression = match.group(1).strip()

        # Clean up common phrases
        if expression:
            expression = re.sub(
                r"^(calculate|compute|eval|what'?s?)\s*:?\s*",
                '',
                expression,
                flags=re.I
            ).strip()

        return {'expression': expression or ''}

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        """Evaluate mathematical expression."""
        expression = params.get('expression', '')

        if not expression:
            return {'error': 'No expression provided'}

        # Try asteval (BSD-licensed safe expression evaluator)
        try:
            from asteval import Interpreter
            
            # Create evaluator with math functions
            evaluator = Interpreter()
            evaluator.symtable.update({
                'pi': math.pi,
                'e': math.e,
                'sqrt': math.sqrt,
                'sin': math.sin,
                'cos': math.cos,
                'tan': math.tan,
                'log': math.log,
                'log10': math.log10,
                'exp': math.exp,
                'abs': abs,
                'round': round,
                'floor': math.floor,
                'ceil': math.ceil,
            })
            
            result = evaluator.eval(expression)

            # asteval returns None on parse/evaluation errors; check error state
            if evaluator.error:
                err = evaluator.error
                evaluator.error = None  # clear for next use
                return {
                    'expression': expression,
                    'error': str(err.get_exc()) if hasattr(err, 'get_exc') else str(err),
                    'valid': False,
                }

            if result is None:
                return {
                    'expression': expression,
                    'error': 'Expression evaluation returned no result',
                    'valid': False,
                }

            return {
                'expression': expression,
                'result': result,
                'result_formatted': self._format_result(result),
                'valid': True,
                'engine': 'asteval',
            }

        except ImportError:
            return {
                'expression': expression,
                'error': 'Expression evaluator not available (asteval required)',
                'valid': False,
            }
        except Exception as e:
            return {
                'expression': expression,
                'error': str(e),
                'valid': False,
            }

    def _format_result(self, result: Any) -> str:
        """Format result for display."""
        if isinstance(result, float):
            # Round to reasonable precision
            if result == int(result):
                return str(int(result))
            return f"{result:.6g}"
        elif isinstance(result, complex):
            return f"{result.real:.6g} + {result.imag:.6g}i"
        else:
            return str(result)
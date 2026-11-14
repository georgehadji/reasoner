"""
Calculator Widget

Evaluates mathematical expressions with a whitelisting AST walker. Not
asteval: its minimal mode let (((9999**1000)**10)**10)**10 hold the GIL
for ~3s and one more level for over 20s, which the 1s timeout cannot stop.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import math
import operator
import re
from typing import Any

from reasoner.infrastructure.widgets.protocol import BaseWidget, WidgetType

logger = logging.getLogger(__name__)

# Safe math operators
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Safe math functions
SAFE_FUNCTIONS = {
    'abs': abs,
    'round': round,
    'min': min,
    'max': max,
    'sum': sum,
    'sqrt': math.sqrt,
    'sin': math.sin,
    'cos': math.cos,
    'tan': math.tan,
    'log': math.log,
    'log10': math.log10,
    'exp': math.exp,
    'floor': math.floor,
    'ceil': math.ceil,
    # No 'pow': it bypassed the ** size guard below, so pow(3, 400000000)
    # ran for minutes holding the GIL (the 1s timeout cannot stop a thread).
}

# Safe constants
SAFE_CONSTANTS = {
    'pi': math.pi,
    'e': math.e,
}


class SafeExpressionError(Exception):
    """Raised when expression contains unsafe operations."""
    pass


def _safe_eval_expr(node: ast.AST, depth: int = 0) -> Any:
    """
    Recursively evaluate AST node with safety checks.
    Raises SafeExpressionError for unsafe operations.
    """
    if depth > 20:
        raise SafeExpressionError("Expression too deeply nested")
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise SafeExpressionError("Boolean constants not allowed")
        if isinstance(node.value, (int, float, complex)):
            if isinstance(node.value, float) and not math.isfinite(node.value):
                raise SafeExpressionError("Inf/NaN not allowed")
            return node.value
        raise SafeExpressionError("Only numeric constants allowed")
    elif isinstance(node, ast.BinOp):
        left = _safe_eval_expr(node.left, depth + 1)
        right = _safe_eval_expr(node.right, depth + 1)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise SafeExpressionError(f"Unsafe operator: {op_type.__name__}")
        if op_type == ast.Div and right == 0:
            raise SafeExpressionError("Division by zero")
        if op_type == ast.Pow:
            if abs(right) > 1000:
                raise SafeExpressionError("Exponent too large")
            if abs(left) > 10000 and abs(right) > 10:
                raise SafeExpressionError("Result would be too large")
            # Nested powers, ((9999**1000)**10)**10..., passed both checks
            # above while the digit count grew 10x per level.
            ints = isinstance(left, int) and isinstance(right, int)
            if ints and left.bit_length() * abs(right) > 100_000:
                raise SafeExpressionError("Result would be too large")
        return SAFE_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        operand = _safe_eval_expr(node.operand, depth + 1)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise SafeExpressionError(f"Unsafe operator: {op_type.__name__}")
        return SAFE_OPERATORS[op_type](operand)
    elif isinstance(node, ast.Call):
        if node.keywords:
            raise SafeExpressionError("Keyword arguments not allowed")
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name not in SAFE_FUNCTIONS:
                raise SafeExpressionError(f"Unsafe function: {func_name}")
            args = [_safe_eval_expr(arg, depth + 1) for arg in node.args]
            return SAFE_FUNCTIONS[func_name](*args)
        raise SafeExpressionError("Function calls must be simple names")
    elif isinstance(node, ast.Name):
        if node.id in SAFE_CONSTANTS:
            return SAFE_CONSTANTS[node.id]
        raise SafeExpressionError(f"Unknown variable: {node.id}")
    elif isinstance(node, ast.Expression):
        return _safe_eval_expr(node.body, depth + 1)
    else:
        raise SafeExpressionError(f"Unsupported expression type: {type(node).__name__}")


def calculate_expression(expression: str) -> dict[str, Any]:
    """
    Evaluate a mathematical expression SAFELY.

    Supports:
    - Basic arithmetic: +, -, *, /
    - Exponents: **
    - Functions: abs, round, min, max, sum, sqrt, sin, cos, tan, log, log10, exp, floor, ceil
    - Constants: pi, e

    Security: Uses AST parsing instead of eval() to prevent code injection.

    Returns:
        dict with 'result', 'valid', 'expression' keys
    """
    expr = expression.strip()
    if not expr:
        return {"error": "Empty expression", "valid": False}
    if len(expr) > 10000:
        return {"error": "Expression too long", "valid": False}

    try:
        tree = ast.parse(expr, mode='eval')

        # Safely evaluate the AST
        result = _safe_eval_expr(tree)

        # Validate result is numeric
        if not isinstance(result, (int, float, complex)):
            return {"error": "Result must be numeric", "valid": False}
        # Both reach the client as JSON, which has no complex type, and int->str
        # refuses past 4300 digits (~14_280 bits): either one was a 500.
        if isinstance(result, complex):
            return {"error": "Result is not a real number", "valid": False}
        if isinstance(result, int) and result.bit_length() > 14_000:
            return {"error": "Result too large", "valid": False}

        return {"result": result, "valid": True, "expression": expression}

    except SafeExpressionError as e:
        return {"error": str(e), "valid": False}
    except SyntaxError:
        return {"error": "Invalid expression syntax", "valid": False}
    except ZeroDivisionError:
        return {"error": "Division by zero", "valid": False}
    except OverflowError:
        return {"error": "Result too large", "valid": False}
    except Exception as e:
        logger.error(f"Unexpected calculation error: {e}")
        return {"error": "Calculation failed", "valid": False}



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

        # Off the loop and bounded, like /api/calculate.
        try:
            out = await asyncio.wait_for(
                asyncio.to_thread(calculate_expression, expression), timeout=1.0
            )
        except TimeoutError:
            return {'expression': expression, 'error': 'Calculation timed out', 'valid': False}

        if not out['valid']:
            return {'expression': expression, 'error': out['error'], 'valid': False}

        return {
            'expression': expression,
            'result': out['result'],
            'result_formatted': self._format_result(out['result']),
            'valid': True,
            'engine': 'ast',
        }

    def _format_result(self, result: Any) -> str:
        """Format result for display."""
        if isinstance(result, float):
            # Round to reasonable precision
            if result == int(result):
                return str(int(result))
            return f"{result:.6g}"
        else:
            return str(result)

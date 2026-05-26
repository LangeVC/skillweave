"""Safe condition expression evaluator for hook bindings.

Conditions are simple predicate expressions evaluated against the
PhaseContext.  Only a restricted subset of operations is allowed
to prevent code injection.

Supported syntax::

    phase == 'build'
    position == 'pre'
    phase == 'build' and position == 'pre'
    phase != 'test'
    phase in ('build', 'test')
    gate_decision == True

No imports, no function calls, no attribute access beyond the
allowed names.
"""

from __future__ import annotations

import ast
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Names that may appear in condition expressions
ALLOWED_NAMES = frozenset({
    "phase", "position", "gate_decision",
    "True", "False", "None",
    "and", "or", "not", "in",
})

# AST node types we allow
ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Tuple,
)


class ConditionError(Exception):
    """Raised when a condition expression is invalid or unsafe."""


def evaluate_condition(
    expression: str,
    context_vars: Dict[str, Any],
) -> bool:
    """Evaluate a condition expression against context variables.

    Args:
        expression: The condition string (e.g. "phase == 'build'").
        context_vars: Dict of variable names to values.

    Returns:
        True if the condition passes, False otherwise.

    Raises:
        ConditionError: If the expression is syntactically invalid or
                        uses disallowed constructs.
    """
    if not expression or not expression.strip():
        return True  # No condition = always run

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ConditionError(
            f"Invalid condition syntax: {expression!r} — {exc}"
        ) from exc

    # Validate all AST nodes are safe
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ConditionError(
                f"Disallowed expression element {type(node).__name__} "
                f"in condition: {expression!r}"
            )
        if isinstance(node, ast.Name) and node.id not in ALLOWED_NAMES:
            # Check if it's a context variable
            if node.id not in context_vars:
                raise ConditionError(
                    f"Unknown variable '{node.id}' in condition: {expression!r}. "
                    f"Allowed: {', '.join(sorted(ALLOWED_NAMES | set(context_vars.keys())))}"
                )

    # Build safe evaluation namespace
    safe_ns = {
        "True": True,
        "False": False,
        "None": None,
        "__builtins__": {},
    }
    safe_ns.update(context_vars)

    try:
        result = eval(compile(tree, "<condition>", "eval"), safe_ns)  # noqa: S307
    except Exception as exc:
        raise ConditionError(
            f"Condition evaluation failed: {expression!r} — {exc}"
        ) from exc

    return bool(result)

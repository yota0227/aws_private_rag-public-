"""Bitwidth Evaluator for SystemVerilog parameter expressions.

Evaluates port bitwidth expressions like ``[SizeX-1:0]`` to concrete
integers (``[3:0]``) using a safe AST-based integer arithmetic parser.
Python ``eval()`` is **never** used — all evaluation goes through
``ast.NodeVisitor`` to prevent code injection.

Supported operations:
  - Addition (+), Subtraction (-), Multiplication (*), Integer Division (/)
  - $clog2() function (ceiling of log base 2)
  - Unary minus (-)
  - Parameter references resolved from a context dict

Parameter resolution order:
  1. Local parameters (from the same module/file)
  2. Package parameters (from *_pkg.sv files)
  Both are passed together in ``param_context`` — the caller is
  responsible for merging them in the correct priority order.

When an expression contains unresolvable parameters, the original
expression string is returned and a DEBUG log is emitted.

Malicious inputs (function calls other than $clog2, import, exec,
attribute access, etc.) are rejected with ``ValueError``.

v9 Phase 7 — Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6
"""

import ast
import math
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safe integer evaluator (ast.NodeVisitor)
# ---------------------------------------------------------------------------

class SafeIntEvaluator(ast.NodeVisitor):
    """Walk a Python AST and evaluate safe integer arithmetic only.

    Allowed node types:
      - ast.Constant / ast.Num  (integer literals)
      - ast.BinOp               (+, -, *, /)
      - ast.UnaryOp             (unary -)
      - ast.Name                (parameter references)
      - ast.Call                (only ``clog2`` — the ``$`` prefix is
                                 stripped before parsing)

    Everything else raises ``ValueError``.
    """

    def __init__(self, param_context: dict):
        self.param_context = param_context or {}

    # -- literals ----------------------------------------------------------

    def visit_Constant(self, node: ast.Constant) -> int:
        if isinstance(node.value, int):
            return node.value
        raise ValueError(
            f"Unsupported constant type: {type(node.value).__name__}"
        )

    # Python < 3.8 compat (ast.Num is deprecated but still present)
    def visit_Num(self, node: ast.Num) -> int:  # pragma: no cover
        return node.n

    # -- binary operators --------------------------------------------------

    _BINOP_MAP = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a // b,       # integer division
        ast.FloorDiv: lambda a, b: a // b,   # also accept //
    }

    def visit_BinOp(self, node: ast.BinOp) -> int:
        op_type = type(node.op)
        if op_type not in self._BINOP_MAP:
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
        left = self.visit(node.left)
        right = self.visit(node.right)
        if op_type in (ast.Div, ast.FloorDiv) and right == 0:
            raise ValueError("Division by zero")
        return self._BINOP_MAP[op_type](left, right)

    # -- unary operators ---------------------------------------------------

    def visit_UnaryOp(self, node: ast.UnaryOp) -> int:
        if isinstance(node.op, ast.USub):
            return -self.visit(node.operand)
        raise ValueError(
            f"Unsupported unary operator: {type(node.op).__name__}"
        )

    # -- parameter references (Name nodes) ---------------------------------

    def visit_Name(self, node: ast.Name) -> int:
        name = node.id
        if name in self.param_context:
            val = self.param_context[name]
            if isinstance(val, int):
                return val
            # Try to convert string values that look like integers
            try:
                return int(str(val))
            except (ValueError, TypeError):
                pass
        # Unresolvable — signal to caller
        raise _UnresolvableParam(name)

    # -- function calls (only clog2 allowed) -------------------------------

    def visit_Call(self, node: ast.Call) -> int:
        # Only allow simple function name (no attribute access)
        if not isinstance(node.func, ast.Name):
            raise ValueError("Unsupported function call with attribute access")
        func_name = node.func.id
        if func_name != "clog2":
            raise ValueError(f"Unsupported function: {func_name}")
        if len(node.args) != 1 or node.keywords:
            raise ValueError("$clog2() requires exactly one positional argument")
        arg_val = self.visit(node.args[0])
        return _clog2(arg_val)

    # -- expression wrapper ------------------------------------------------

    def visit_Expr(self, node: ast.Expr) -> int:
        return self.visit(node.value)

    def visit_Expression(self, node: ast.Expression) -> int:
        return self.visit(node.body)

    # -- catch-all: reject everything else ---------------------------------

    def generic_visit(self, node: ast.AST):
        raise ValueError(
            f"Unsupported AST node: {type(node).__name__}"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _UnresolvableParam(Exception):
    """Raised when a parameter cannot be resolved from the context."""

    def __init__(self, param_name: str):
        self.param_name = param_name
        super().__init__(f"Unresolvable parameter: {param_name}")


def _clog2(n: int) -> int:
    """Compute ceil(log2(n)).

    Special cases:
      - $clog2(1) = 0  (standard SystemVerilog behaviour)
      - $clog2(0) → ValueError
      - $clog2(negative) → ValueError
    """
    if n <= 0:
        raise ValueError(f"$clog2() argument must be positive, got {n}")
    if n == 1:
        return 0
    return math.ceil(math.log2(n))


def _preprocess_expr(expr: str) -> str:
    """Prepare a SystemVerilog-style expression for Python AST parsing.

    - Replace ``$clog2(...)`` with ``clog2(...)`` (strip the ``$`` prefix)
    - Strip leading/trailing whitespace
    """
    processed = expr.strip().replace("$clog2", "clog2")
    return processed


def _validate_input(expr: str) -> None:
    """Reject obviously malicious inputs before AST parsing.

    Raises ``ValueError`` for inputs containing dangerous patterns.
    """
    dangerous_patterns = [
        "__import__",
        "import ",
        "exec(",
        "eval(",
        "compile(",
        "getattr(",
        "setattr(",
        "delattr(",
        "globals(",
        "locals(",
        "open(",
        "__builtins__",
        "__class__",
        "__subclasses__",
        "os.system",
        "subprocess",
        "lambda ",
    ]
    lower_expr = expr.lower()
    for pattern in dangerous_patterns:
        if pattern.lower() in lower_expr:
            raise ValueError(
                f"Potentially malicious input detected: {pattern!r}"
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_bitwidth(expr: str, param_context: dict = None) -> object:
    """Evaluate a bitwidth expression to an integer.

    Args:
        expr: A SystemVerilog-style bitwidth expression, e.g.
              ``"SizeX-1"``, ``"$clog2(NumTensix)"``, ``"SizeX*SizeY"``.
        param_context: Dict mapping parameter names to integer values.
                       Resolution order (local → package) should be
                       pre-merged by the caller.

    Returns:
        int — the evaluated integer result, **or**
        str — the original expression string when it contains
              unresolvable parameters.

    Raises:
        ValueError: If the expression contains disallowed constructs
                    (function calls other than $clog2, attribute access,
                    import, exec, etc.).
    """
    if param_context is None:
        param_context = {}

    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("Expression must be a non-empty string")

    original_expr = expr.strip()

    # Step 1: reject obviously dangerous inputs
    _validate_input(original_expr)

    # Step 2: preprocess for Python AST compatibility
    processed = _preprocess_expr(original_expr)

    # Step 3: parse into AST
    try:
        tree = ast.parse(processed, mode="eval")
    except SyntaxError:
        # If it can't be parsed, it might contain unresolvable params
        # with special characters — return original
        logger.debug(
            "Bitwidth expression parse failed, returning original: %s",
            original_expr,
        )
        return original_expr

    # Step 4: evaluate safely
    evaluator = SafeIntEvaluator(param_context)
    try:
        result = evaluator.visit(tree)
        return int(result)
    except _UnresolvableParam as e:
        logger.debug(
            "Bitwidth expression contains unresolvable parameter '%s': %s",
            e.param_name,
            original_expr,
        )
        return original_expr
    except ValueError:
        # Re-raise ValueError (malicious input, unsupported ops, etc.)
        raise
    except ZeroDivisionError:
        raise ValueError("Division by zero in bitwidth expression")

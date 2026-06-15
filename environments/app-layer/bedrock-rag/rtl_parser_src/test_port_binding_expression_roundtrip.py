"""Property-based test: Port binding expression round-trip.

**Validates: Requirements 5.1, 5.2, 5.4, 5.5**

Property 4: For any valid port binding expression containing arithmetic
operators (+, -, *, /) and integer literals (including nested parenthesized
expressions), parsing the expression from RTL text and formatting it back
to text SHALL produce a string equivalent to the original expression
(whitespace-normalized).

Uses hypothesis library with minimum 100 iterations.
Generator: +, -, *, / operators + integer literals + parentheses + identifiers.
Assertion: parse(format(expr)) == expr (whitespace-normalized)
"""
import os
import re

# Ensure feature flag is enabled for tests
os.environ.setdefault('PARSER_PORT_BINDING_ENABLED', 'true')

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from port_binding_parser import (
    _find_all_port_bindings,
    _strip_comments,
    classify_expression_type,
)


# --- Strategies for generating random arithmetic expressions ---

# Identifiers: valid Verilog signal names (letter/underscore start, alphanumeric)
identifier_strategy = st.from_regex(r'[a-zA-Z_][a-zA-Z0-9_]{0,7}', fullmatch=True)

# Integer literals: small positive integers (avoid 0 to prevent division issues in display)
integer_literal_strategy = st.integers(min_value=0, max_value=9999).map(str)

# Leaf nodes: either an identifier or an integer literal
leaf_strategy = st.one_of(identifier_strategy, integer_literal_strategy)

# Arithmetic operators
operator_strategy = st.sampled_from(['+', '-', '*', '/'])


def _extend_expr(base):
    """Extend a base expression strategy with binary ops and parentheses."""
    return st.one_of(
        # Binary expression: left op right
        st.tuples(base, operator_strategy, base).map(
            lambda t: f"{t[0]} {t[1]} {t[2]}"
        ),
        # Parenthesized expression: (expr)
        base.map(lambda e: f"({e})"),
    )


# Recursive expression strategy using st.recursive
# Base: identifiers and integer literals
# Extend: binary operations and parenthesization
port_binding_expr_strategy = st.recursive(
    base=leaf_strategy,
    extend=_extend_expr,
    max_leaves=8,
)


def normalize_whitespace(s):
    """Normalize whitespace for comparison: collapse multiple spaces to one, strip."""
    return re.sub(r'\s+', ' ', s.strip())


def format_rtl_with_expression(expr):
    """Format a port binding expression into a minimal RTL instantiation statement.

    Creates: module_type instance_name (.port_name(expr));
    """
    return f"""
    test_mod u_test (
        .test_port({expr})
    );
    """


class TestPortBindingExpressionRoundTrip:
    """Property 4: Port binding expression round-trip.

    **Validates: Requirements 5.1, 5.2, 5.4, 5.5**

    For any valid port binding expression containing arithmetic operators
    (+, -, *, /) and integer literals (including nested parenthesized expressions),
    parsing the expression from RTL text and formatting it back to text SHALL produce
    a string equivalent to the original expression (whitespace-normalized).
    """

    @given(expr=port_binding_expr_strategy)
    @settings(max_examples=200)
    def test_expression_round_trip(self, expr):
        """parse(format(expr)) == expr (whitespace-normalized).

        **Validates: Requirements 5.1, 5.2, 5.4, 5.5**
        """
        # Skip expressions that could be confused with Verilog keywords
        # or that are empty after normalization
        normalized_input = normalize_whitespace(expr)
        assume(len(normalized_input) > 0)

        # Avoid expressions that start with '{' (concatenation, not arithmetic)
        assume(not normalized_input.startswith('{'))

        # Format as RTL and parse
        rtl_text = format_rtl_with_expression(expr)
        clean = _strip_comments(rtl_text)
        bindings = _find_all_port_bindings(clean, "test.sv")

        # Should extract exactly one binding
        assert len(bindings) == 1, (
            f"Expected 1 binding, got {len(bindings)} for expr: {expr!r}"
        )

        # Extract parsed signal expression
        parsed_expr = bindings[0]["signal_expr"]

        # Round-trip assertion: whitespace-normalized comparison
        assert normalize_whitespace(parsed_expr) == normalized_input, (
            f"Round-trip failed!\n"
            f"  Input (normalized):  {normalized_input!r}\n"
            f"  Parsed (normalized): {normalize_whitespace(parsed_expr)!r}\n"
            f"  Raw parsed:          {parsed_expr!r}"
        )

    @given(expr=port_binding_expr_strategy)
    @settings(max_examples=200)
    def test_expression_type_consistent(self, expr):
        """Expression type classification is consistent with content.

        **Validates: Requirements 5.1, 5.2**

        If an expression contains +, -, *, / operators, it should be
        classified as 'arithmetic'. Otherwise 'simple'.
        """
        normalized_input = normalize_whitespace(expr)
        assume(len(normalized_input) > 0)
        assume(not normalized_input.startswith('{'))

        # Format as RTL and parse
        rtl_text = format_rtl_with_expression(expr)
        clean = _strip_comments(rtl_text)
        bindings = _find_all_port_bindings(clean, "test.sv")

        assert len(bindings) == 1

        expression_type = bindings[0]["expression_type"]
        parsed_expr = bindings[0]["signal_expr"]

        # Verify classification matches content
        has_arithmetic_ops = bool(re.search(r'[+\-*/]', parsed_expr))

        if has_arithmetic_ops:
            assert expression_type == "arithmetic", (
                f"Expression with operators should be 'arithmetic', "
                f"got '{expression_type}' for: {parsed_expr!r}"
            )
        else:
            assert expression_type == "simple", (
                f"Expression without operators should be 'simple', "
                f"got '{expression_type}' for: {parsed_expr!r}"
            )

    @given(expr=port_binding_expr_strategy)
    @settings(max_examples=100)
    def test_parentheses_preserved(self, expr):
        """Parenthesized sub-expressions are preserved without simplification.

        **Validates: Requirements 5.4, 5.5**

        The parser must not evaluate or simplify expressions like (SizeX - 1) * 2.
        Parentheses in the original must appear in the parsed output.
        """
        normalized_input = normalize_whitespace(expr)
        assume(len(normalized_input) > 0)
        assume(not normalized_input.startswith('{'))
        # Only test expressions that have parentheses
        assume('(' in normalized_input)

        # Format as RTL and parse
        rtl_text = format_rtl_with_expression(expr)
        clean = _strip_comments(rtl_text)
        bindings = _find_all_port_bindings(clean, "test.sv")

        assert len(bindings) == 1

        parsed_expr = bindings[0]["signal_expr"]
        parsed_normalized = normalize_whitespace(parsed_expr)

        # Count parentheses — should be preserved
        input_open_parens = normalized_input.count('(')
        input_close_parens = normalized_input.count(')')
        parsed_open_parens = parsed_normalized.count('(')
        parsed_close_parens = parsed_normalized.count(')')

        assert parsed_open_parens == input_open_parens, (
            f"Open parentheses count mismatch: "
            f"input={input_open_parens}, parsed={parsed_open_parens}\n"
            f"  Input:  {normalized_input!r}\n"
            f"  Parsed: {parsed_normalized!r}"
        )
        assert parsed_close_parens == input_close_parens, (
            f"Close parentheses count mismatch: "
            f"input={input_close_parens}, parsed={parsed_close_parens}\n"
            f"  Input:  {normalized_input!r}\n"
            f"  Parsed: {parsed_normalized!r}"
        )

"""Property-Based Test: Wire dimension count preservation (Task 6.2).

**Validates: Requirements 8.1, 8.3, 8.4**

Property 1: For any wire declaration with N dimensions (N >= 1),
the Wire_Declaration_Parser SHALL extract exactly N dimension expressions
in their original order. No trailing dimensions shall be dropped regardless
of total dimension count.

Uses hypothesis library with minimum 100 iterations.
Generator: 1-5 dimensions, each being an identifier or expression.
"""

import re
import unittest

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from wire_declaration_parser import extract_wire_declarations, _parse_dimensions


# --- Strategies / Generators ---

# Identifier strategy: simple RTL identifiers (e.g., SizeX, NumCols, WIDTH)
identifier_st = st.from_regex(r'[A-Z][a-zA-Z0-9_]{1,10}', fullmatch=True)

# Integer literal strategy
int_literal_st = st.integers(min_value=0, max_value=255).map(str)

# Expression strategy: identifier with optional arithmetic (e.g., N-1, 2*WIDTH, SizeX+1)
expression_st = st.one_of(
    identifier_st,
    int_literal_st,
    # identifier - integer (e.g., SizeY-1)
    st.tuples(identifier_st, st.sampled_from(['-', '+']), st.integers(min_value=1, max_value=16)).map(
        lambda t: f"{t[0]}{t[1]}{t[2]}"
    ),
    # integer * identifier (e.g., 2*WIDTH)
    st.tuples(st.integers(min_value=2, max_value=8), identifier_st).map(
        lambda t: f"{t[0]}*{t[1]}"
    ),
)

# Dimension list: 1-5 dimensions
dimensions_st = st.lists(expression_st, min_size=1, max_size=5)


def _build_dim_string(dims):
    """Build '[dim1][dim2]...' string from dimension list."""
    return ''.join(f'[{d}]' for d in dims)


# --- Property Test Class ---

class TestWireDimensionCountPreservation(unittest.TestCase):
    """Property 1: Wire dimension count preservation.

    **Validates: Requirements 8.1, 8.3, 8.4**
    """

    @given(dims=dimensions_st)
    @settings(max_examples=150)
    def test_pattern_a_dimension_count_preserved(self, dims):
        """Pattern A: wire struct_type_t signal[dims] preserves dimension count and order."""
        dim_str = _build_dim_string(dims)
        rtl = f"    wire some_struct_t test_signal{dim_str};"

        claims = extract_wire_declarations(rtl, "test_mod", "test.sv", "pipe1")
        assume(len(claims) > 0)

        claim_text = claims[0]["claim_text"]
        # Extract dimensions from claim text: "with dimensions [dim1, dim2, ...]"
        dim_match = re.search(r"with dimensions \[([^\]]+)\]", claim_text)
        self.assertIsNotNone(dim_match, f"No dimensions found in: {claim_text}")

        extracted_dims = [d.strip() for d in dim_match.group(1).split(',')]
        # Assertion: count matches
        self.assertEqual(
            len(extracted_dims), len(dims),
            f"Expected {len(dims)} dims, got {len(extracted_dims)}. "
            f"Input: {dims}, Extracted: {extracted_dims}"
        )
        # Assertion: order preserved
        self.assertEqual(
            extracted_dims, dims,
            f"Order mismatch. Input: {dims}, Extracted: {extracted_dims}"
        )

    @given(dims=dimensions_st)
    @settings(max_examples=150)
    def test_pattern_c_dimension_count_preserved(self, dims):
        """Pattern C: type_t signal[dims] preserves dimension count and order."""
        dim_str = _build_dim_string(dims)
        # Pattern C: type ending with _t, no wire/logic keyword, at line start
        rtl = f"    custom_type_t test_signal{dim_str};"

        claims = extract_wire_declarations(rtl, "test_mod", "test.sv", "pipe1")
        assume(len(claims) > 0)

        claim_text = claims[0]["claim_text"]
        dim_match = re.search(r"with dimensions \[([^\]]+)\]", claim_text)
        self.assertIsNotNone(dim_match, f"No dimensions found in: {claim_text}")

        extracted_dims = [d.strip() for d in dim_match.group(1).split(',')]
        self.assertEqual(
            len(extracted_dims), len(dims),
            f"Expected {len(dims)} dims, got {len(extracted_dims)}. "
            f"Input: {dims}, Extracted: {extracted_dims}"
        )
        self.assertEqual(
            extracted_dims, dims,
            f"Order mismatch. Input: {dims}, Extracted: {extracted_dims}"
        )

    @given(dims=dimensions_st)
    @settings(max_examples=150)
    def test_parse_dimensions_helper_preserves_count(self, dims):
        """_parse_dimensions() directly preserves dimension count and order."""
        dim_str = _build_dim_string(dims)
        extracted = _parse_dimensions(dim_str)

        self.assertEqual(
            len(extracted), len(dims),
            f"Expected {len(dims)} dims, got {len(extracted)}. "
            f"Input: {dims}, Extracted: {extracted}"
        )
        self.assertEqual(
            extracted, dims,
            f"Order mismatch. Input: {dims}, Extracted: {extracted}"
        )


if __name__ == "__main__":
    unittest.main()

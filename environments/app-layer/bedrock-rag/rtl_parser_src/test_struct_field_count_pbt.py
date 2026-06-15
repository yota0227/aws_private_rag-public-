"""Property-based test: Struct field count invariant.

**Validates: Requirements 9.1, 9.2, 9.3, 9.4**

Property 2: For any struct definition with N declared fields (including fields
with packed dimensions, unpacked dimensions, and custom type references), the
Package_Extractor SHALL extract exactly N fields, correctly distinguishing
between packed dimensions (bit-width) and unpacked dimensions (array).

Uses hypothesis library with minimum 100 iterations.
Generator: 1-15 fields of random struct definitions (packed/unpacked/custom type mix).
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from package_extractor import _parse_struct_fields


# --- Strategies for generating random struct fields ---

# Valid SystemVerilog identifiers (avoid reserved words)
_RESERVED = frozenset([
    "logic", "bit", "int", "integer", "wire", "reg", "byte",
    "shortint", "longint", "string", "real", "typedef", "struct",
    "packed", "unsigned", "signed", "input", "output", "inout",
    "module", "endmodule", "function", "endfunction", "task", "endtask",
])

identifier_st = st.from_regex(r"[a-z][a-z0-9_]{2,10}", fullmatch=True).filter(
    lambda s: s not in _RESERVED and not s.endswith("_t")
)

# Custom type names (end with _t to mimic typedef names)
custom_type_st = st.from_regex(r"[a-z][a-z0-9_]{2,8}_t", fullmatch=True)

# Packed dimension values: [MSB:LSB] where MSB > LSB >= 0
packed_dim_st = st.builds(
    lambda msb, lsb: f"[{msb}:{lsb}]",
    msb=st.integers(min_value=1, max_value=63),
    lsb=st.integers(min_value=0, max_value=0),
)

# Unpacked dimension values: [SIZE:0] or [N]
unpacked_dim_st = st.builds(
    lambda size: f"[{size}:0]",
    size=st.integers(min_value=1, max_value=15),
)


# Field type enum
class FieldKind:
    PACKED = "packed"       # logic [7:0] field_name;
    UNPACKED = "unpacked"  # logic field_name [3:0];
    BOTH = "both"          # logic [7:0] field_name [3:0];
    PLAIN = "plain"        # logic field_name;
    CUSTOM = "custom"      # custom_t field_name;
    CUSTOM_UNPACKED = "custom_unpacked"  # custom_t field_name [3:0];


field_kind_st = st.sampled_from([
    FieldKind.PACKED,
    FieldKind.UNPACKED,
    FieldKind.BOTH,
    FieldKind.PLAIN,
    FieldKind.CUSTOM,
    FieldKind.CUSTOM_UNPACKED,
])


@st.composite
def struct_field_st(draw):
    """Generate a single struct field declaration and its expected properties."""
    kind = draw(field_kind_st)
    name = draw(identifier_st)

    if kind == FieldKind.PACKED:
        dim = draw(packed_dim_st)
        declaration = f"    logic {dim} {name};"
        expected_packed = dim
        expected_unpacked = ""
        expected_ref_type = ""
    elif kind == FieldKind.UNPACKED:
        dim = draw(unpacked_dim_st)
        declaration = f"    logic {name} {dim};"
        expected_packed = ""
        expected_unpacked = dim
        expected_ref_type = ""
    elif kind == FieldKind.BOTH:
        p_dim = draw(packed_dim_st)
        u_dim = draw(unpacked_dim_st)
        declaration = f"    logic {p_dim} {name} {u_dim};"
        expected_packed = p_dim
        expected_unpacked = u_dim
        expected_ref_type = ""
    elif kind == FieldKind.PLAIN:
        declaration = f"    logic {name};"
        expected_packed = ""
        expected_unpacked = ""
        expected_ref_type = ""
    elif kind == FieldKind.CUSTOM:
        custom_type = draw(custom_type_st)
        declaration = f"    {custom_type} {name};"
        expected_packed = ""
        expected_unpacked = ""
        expected_ref_type = custom_type
    elif kind == FieldKind.CUSTOM_UNPACKED:
        custom_type = draw(custom_type_st)
        dim = draw(unpacked_dim_st)
        declaration = f"    {custom_type} {name} {dim};"
        expected_packed = ""
        expected_unpacked = dim
        expected_ref_type = custom_type
    else:
        raise ValueError(f"Unknown field kind: {kind}")

    return {
        "declaration": declaration,
        "name": name,
        "expected_packed": expected_packed,
        "expected_unpacked": expected_unpacked,
        "expected_ref_type": expected_ref_type,
    }


@st.composite
def struct_definition_st(draw):
    """Generate a complete struct body with 1-15 unique fields."""
    num_fields = draw(st.integers(min_value=1, max_value=15))
    fields = []
    used_names = set()

    for _ in range(num_fields):
        field = draw(struct_field_st())
        # Ensure unique field names
        assume(field["name"] not in used_names)
        used_names.add(field["name"])
        fields.append(field)

    # Build struct body text (inside the braces)
    body = "\n".join(f["declaration"] for f in fields) + "\n"
    return {"body": body, "fields": fields}


# --- Property test ---

@settings(max_examples=150)
@given(struct_def=struct_definition_st())
def test_struct_field_count_invariant(struct_def):
    """Property 2: Struct field count invariant.

    **Validates: Requirements 9.1, 9.2, 9.3, 9.4**

    For any struct definition with N declared fields, _parse_struct_fields
    SHALL extract exactly N fields, correctly distinguishing between packed
    dimensions and unpacked dimensions.
    """
    body = struct_def["body"]
    expected_fields = struct_def["fields"]
    n = len(expected_fields)

    # Act: parse the struct body
    result = _parse_struct_fields(body, "")

    # Assert 1: Field count matches
    assert len(result) == n, (
        f"Expected {n} fields but got {len(result)}.\n"
        f"Body:\n{body}\n"
        f"Result: {[f['name'] for f in result]}"
    )

    # Build lookup by name for property assertions
    result_by_name = {f["name"]: f for f in result}

    for expected in expected_fields:
        name = expected["name"]
        assert name in result_by_name, (
            f"Field '{name}' not found in result. "
            f"Got: {list(result_by_name.keys())}"
        )
        actual = result_by_name[name]

        # Assert 2: packed_dim correctly classified
        assert actual["packed_dim"] == expected["expected_packed"], (
            f"Field '{name}': expected packed_dim='{expected['expected_packed']}' "
            f"but got '{actual['packed_dim']}'"
        )

        # Assert 3: unpacked_dim correctly classified
        assert actual["unpacked_dim"] == expected["expected_unpacked"], (
            f"Field '{name}': expected unpacked_dim='{expected['expected_unpacked']}' "
            f"but got '{actual['unpacked_dim']}'"
        )

        # Assert 4: ref_type correctly identified for custom types
        assert actual["ref_type"] == expected["expected_ref_type"], (
            f"Field '{name}': expected ref_type='{expected['expected_ref_type']}' "
            f"but got '{actual['ref_type']}'"
        )

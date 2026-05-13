"""
Tests for package_extractor.py — Struct Field Packed Dimension (Task 7.1).

Validates Requirements 9.1, 9.2, 9.3, 9.4:
- Packed dimension extraction (logic [7:0] field_name)
- Unpacked dimension extraction (logic field_name [3:0])
- Both packed + unpacked on same field
- Field count validation (mismatch detection)
- Correct classification of packed vs unpacked
"""

import logging
import pytest
from package_extractor import extract_package_constants, _parse_struct_fields


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_struct_claims(rtl_content, file_path="test_pkg.sv", pipeline_id="test"):
    """Run extract_package_constants and return only struct-related claims."""
    all_claims = extract_package_constants(rtl_content, file_path, pipeline_id)
    return [c for c in all_claims if "struct" in c["claim_text"].lower()
            or "flit structure" in c["claim_text"].lower()]


# ---------------------------------------------------------------------------
# Req 9.1: Packed dimension extraction
# ---------------------------------------------------------------------------

class TestPackedDimensionExtraction:
    """Req 9.1: Extract packed dimensions from struct fields."""

    def test_packed_dim_logic_field(self):
        """logic [7:0] field_name → packed_dim='[7:0]'"""
        body = "logic [7:0] data_field;"
        fields = _parse_struct_fields(body)
        assert len(fields) == 1
        assert fields[0]["name"] == "data_field"
        assert fields[0]["packed_dim"] == "[7:0]"
        assert fields[0]["unpacked_dim"] == ""

    def test_packed_dim_expression(self):
        """logic [SizeX-1:0] field_name → packed_dim='[SizeX-1:0]'"""
        body = "logic [SizeX-1:0] x_coord;"
        fields = _parse_struct_fields(body)
        assert len(fields) == 1
        assert fields[0]["name"] == "x_coord"
        assert fields[0]["packed_dim"] == "[SizeX-1:0]"
        assert fields[0]["unpacked_dim"] == ""

    def test_no_packed_dim_single_bit(self):
        """logic field_name → packed_dim=''"""
        body = "logic valid;"
        fields = _parse_struct_fields(body)
        assert len(fields) == 1
        assert fields[0]["name"] == "valid"
        assert fields[0]["packed_dim"] == ""
        assert fields[0]["unpacked_dim"] == ""
        assert fields[0]["bit_width"] == 1

    def test_multiple_packed_fields(self):
        """Multiple fields with different packed dimensions."""
        body = """
            logic [7:0] byte_field;
            logic [15:0] half_word;
            logic [31:0] word;
        """
        fields = _parse_struct_fields(body)
        assert len(fields) == 3
        assert fields[0]["packed_dim"] == "[7:0]"
        assert fields[1]["packed_dim"] == "[15:0]"
        assert fields[2]["packed_dim"] == "[31:0]"


# ---------------------------------------------------------------------------
# Req 9.3: Unpacked dimension extraction
# ---------------------------------------------------------------------------

class TestUnpackedDimensionExtraction:
    """Req 9.3: Distinguish unpacked dimensions (array) from packed."""

    def test_unpacked_dim_after_name(self):
        """logic field_name [3:0] → unpacked_dim='[3:0]'"""
        body = "logic data_arr [3:0];"
        fields = _parse_struct_fields(body)
        assert len(fields) == 1
        assert fields[0]["name"] == "data_arr"
        assert fields[0]["packed_dim"] == ""
        assert fields[0]["unpacked_dim"] == "[3:0]"

    def test_both_packed_and_unpacked(self):
        """logic [7:0] field_name [3:0] → packed='[7:0]', unpacked='[3:0]'"""
        body = "logic [7:0] data_matrix [3:0];"
        fields = _parse_struct_fields(body)
        assert len(fields) == 1
        assert fields[0]["name"] == "data_matrix"
        assert fields[0]["packed_dim"] == "[7:0]"
        assert fields[0]["unpacked_dim"] == "[3:0]"
        assert fields[0]["bit_width"] == 8  # packed dim determines bit_width

    def test_custom_type_with_unpacked_dim(self):
        """tile_t dest_tiles [3:0] → unpacked_dim='[3:0]'"""
        body = "tile_t dest_tiles [3:0];"
        fields = _parse_struct_fields(body)
        assert len(fields) == 1
        assert fields[0]["name"] == "dest_tiles"
        assert fields[0]["ref_type"] == "tile_t"
        assert fields[0]["packed_dim"] == ""
        assert fields[0]["unpacked_dim"] == "[3:0]"

    def test_expression_unpacked_dim(self):
        """logic field_name [SizeX-1:0] → unpacked_dim='[SizeX-1:0]'"""
        body = "logic flags [SizeX-1:0];"
        fields = _parse_struct_fields(body)
        assert len(fields) == 1
        assert fields[0]["name"] == "flags"
        assert fields[0]["unpacked_dim"] == "[SizeX-1:0]"


# ---------------------------------------------------------------------------
# Req 9.2, 9.4: Field count validation
# ---------------------------------------------------------------------------

class TestFieldCountValidation:
    """Req 9.2, 9.4: Field count matches source declaration."""

    def test_correct_field_count_no_warning(self, caplog):
        """No warning when field count matches semicolons."""
        body = """
            logic [7:0] a;
            logic [7:0] b;
            logic [7:0] c;
        """
        with caplog.at_level(logging.WARNING):
            fields = _parse_struct_fields(body)
        assert len(fields) == 3
        assert not any("mismatch" in r.message for r in caplog.records)

    def test_field_count_mismatch_raises_error(self):
        """StructFieldCountMismatchError raised when extraction misses a field."""
        from package_extractor import StructFieldCountMismatchError
        # Body has 3 semicolons but one line is a bare identifier (no type)
        # which won't match either the builtin or custom field patterns.
        body = """
            logic [7:0] a;
            logic [7:0] b;
            standalone_field;
        """
        # 'standalone_field;' has no type prefix, so it won't be extracted.
        # Expected=3 (3 non-keyword semicolons), actual=2 → mismatch.
        with pytest.raises(StructFieldCountMismatchError) as exc_info:
            _parse_struct_fields(body)
        assert exc_info.value.expected == 3
        assert exc_info.value.actual == 2

    def test_keyword_lines_not_counted_as_fields(self):
        """Lines starting with skip keywords (typedef, struct, etc.) are excluded from count."""
        # 'typedef foo;' starts with 'typedef' which is in skip_keywords,
        # so it won't be counted as an expected field.
        body = """
            logic [7:0] a;
            typedef foo;
            logic [7:0] c;
        """
        # typedef line is filtered from expected count → expected=2, actual=2 → no error
        fields = _parse_struct_fields(body)
        assert len(fields) == 2

    def test_realistic_struct_field_count(self):
        """Realistic struct: all fields extracted correctly."""
        body = """
            logic [3:0] x_dest;
            logic [3:0] y_dest;
            logic [15:0] payload;
            logic valid;
            tile_t dest_tile;
        """
        fields = _parse_struct_fields(body)
        assert len(fields) == 5


# ---------------------------------------------------------------------------
# Integration: realistic trinity_clock_routing_t-like struct
# ---------------------------------------------------------------------------

class TestRealisticClockRoutingStruct:
    """Integration test with realistic struct containing packed dims."""

    def test_clock_routing_struct(self):
        """Struct with mixed packed dimensions — all fields extracted."""
        rtl = """
        package trinity_pkg;
            typedef struct packed {
                logic [SizeX-1:0] clk_en_x;
                logic [SizeY-1:0] clk_en_y;
                logic [3:0] clk_div;
                logic clk_gate;
                logic [1:0] clk_sel;
                logic bypass;
                logic [7:0] scan_chain;
                logic test_mode;
                logic reset_sync;
            } trinity_clock_routing_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        summary = [c for c in claims if "defines typedef struct" in c["claim_text"]]
        assert len(summary) == 1
        assert "9 fields" in summary[0]["claim_text"]

        # Verify packed_dim on specific fields via _parse_struct_fields directly
        body = """
                logic [SizeX-1:0] clk_en_x;
                logic [SizeY-1:0] clk_en_y;
                logic [3:0] clk_div;
                logic clk_gate;
                logic [1:0] clk_sel;
                logic bypass;
                logic [7:0] scan_chain;
                logic test_mode;
                logic reset_sync;
        """
        fields = _parse_struct_fields(body)
        assert len(fields) == 9

        # Check packed dimensions
        clk_en_x = next(f for f in fields if f["name"] == "clk_en_x")
        assert clk_en_x["packed_dim"] == "[SizeX-1:0]"
        assert clk_en_x["unpacked_dim"] == ""

        clk_gate = next(f for f in fields if f["name"] == "clk_gate")
        assert clk_gate["packed_dim"] == ""
        assert clk_gate["bit_width"] == 1

    def test_struct_with_mixed_packed_unpacked(self):
        """Struct with both packed and unpacked dimensions."""
        body = """
            logic [7:0] data;
            logic flags [3:0];
            logic [15:0] addr [7:0];
        """
        fields = _parse_struct_fields(body)
        assert len(fields) == 3

        data_f = next(f for f in fields if f["name"] == "data")
        assert data_f["packed_dim"] == "[7:0]"
        assert data_f["unpacked_dim"] == ""

        flags_f = next(f for f in fields if f["name"] == "flags")
        assert flags_f["packed_dim"] == ""
        assert flags_f["unpacked_dim"] == "[3:0]"

        addr_f = next(f for f in fields if f["name"] == "addr")
        assert addr_f["packed_dim"] == "[15:0]"
        assert addr_f["unpacked_dim"] == "[7:0]"

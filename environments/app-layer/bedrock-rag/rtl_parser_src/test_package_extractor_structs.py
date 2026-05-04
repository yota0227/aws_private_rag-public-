"""
Tests for package_extractor.py — Flit Struct Field-Level Parsing (Task 14.3).

Validates Requirements 20.1, 20.2, 20.3, 20.4, 20.5:
- Per-field bitwidth extraction (logic [N:0])
- Per-field claim_text format
- Flit layout claim for *_flit_t, *_header_t, *_payload_t
- Inline comment extraction
- Type reference extraction
- parser_source='package_struct_parser' on all struct claims
"""

import pytest
from package_extractor import extract_package_constants


# ---------------------------------------------------------------------------
# Helper: extract struct-related claims from RTL content
# ---------------------------------------------------------------------------

def _get_struct_claims(rtl_content, file_path="test_pkg.sv", pipeline_id="test"):
    """Run extract_package_constants and return only struct-related claims."""
    all_claims = extract_package_constants(rtl_content, file_path, pipeline_id)
    return [c for c in all_claims if "struct" in c["claim_text"].lower()
            or "flit structure" in c["claim_text"].lower()]


# ---------------------------------------------------------------------------
# Req 20.1: Per-field bitwidth extraction
# ---------------------------------------------------------------------------

class TestFieldBitwidthExtraction:
    """Req 20.1: Extract per-field bitwidth from typedef struct."""

    def test_logic_field_with_dimension(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                logic [7:0] x_dest;
                logic [7:0] y_dest;
                logic [15:0] payload;
            } noc_flit_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        field_claims = [c for c in claims if "field '" in c["claim_text"]]
        assert len(field_claims) == 3

        x_claim = [c for c in field_claims if "'x_dest'" in c["claim_text"]][0]
        assert "width 8" in x_claim["claim_text"]

        payload_claim = [c for c in field_claims if "'payload'" in c["claim_text"]][0]
        assert "width 16" in payload_claim["claim_text"]

    def test_single_bit_logic_field(self):
        rtl = """
        package test_pkg;
            typedef struct packed {
                logic valid;
                logic [3:0] id;
            } simple_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        field_claims = [c for c in claims if "field '" in c["claim_text"]]

        valid_claim = [c for c in field_claims if "'valid'" in c["claim_text"]][0]
        assert "width 1" in valid_claim["claim_text"]

        id_claim = [c for c in field_claims if "'id'" in c["claim_text"]][0]
        assert "width 4" in id_claim["claim_text"]

    def test_bit_type_field(self):
        rtl = """
        package test_pkg;
            typedef struct packed {
                bit [15:0] data;
            } data_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        field_claims = [c for c in claims if "field '" in c["claim_text"]]
        assert len(field_claims) == 1
        assert "width 16" in field_claims[0]["claim_text"]


# ---------------------------------------------------------------------------
# Req 20.2: Per-field claim_text format
# ---------------------------------------------------------------------------

class TestFieldClaimFormat:
    """Req 20.2: claim_text format for struct fields."""

    def test_claim_text_format(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                logic [31:0] addr;
            } addr_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        field_claims = [c for c in claims if "field '" in c["claim_text"]]
        assert len(field_claims) == 1
        ct = field_claims[0]["claim_text"]
        assert ct.startswith("Package 'noc_pkg' defines struct 'addr_t' field 'addr' with width 32")

    def test_summary_claim_preserved(self):
        """Existing summary claim (with field count) must still be generated."""
        rtl = """
        package test_pkg;
            typedef struct packed {
                logic [7:0] a;
                logic [7:0] b;
            } pair_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        summary = [c for c in claims if "defines typedef struct" in c["claim_text"]]
        assert len(summary) == 1
        assert "2 fields" in summary[0]["claim_text"]
        assert "a, b" in summary[0]["claim_text"]


# ---------------------------------------------------------------------------
# Req 20.3: Flit layout claim for flit-related types
# ---------------------------------------------------------------------------

class TestFlitLayoutClaim:
    """Req 20.3: Layout claim for *_flit_t, *_header_t, *_payload_t."""

    def test_flit_t_generates_layout(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                logic [3:0] x_dest;
                logic [3:0] y_dest;
                logic [23:0] payload;
            } noc_flit_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        layout = [c for c in claims if "Flit structure" in c["claim_text"]]
        assert len(layout) == 1
        lt = layout[0]["claim_text"]
        assert "Flit structure 'noc_flit_t' layout:" in lt
        # Fields should be sorted by MSB descending
        assert "payload[23:0]" in lt
        assert "x_dest[3:0]" in lt
        assert "y_dest[3:0]" in lt

    def test_header_t_generates_layout(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                logic [7:0] src_id;
                logic [7:0] dst_id;
            } noc_header_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        layout = [c for c in claims if "Flit structure" in c["claim_text"]]
        assert len(layout) == 1
        assert "'noc_header_t'" in layout[0]["claim_text"]

    def test_payload_t_generates_layout(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                logic [31:0] data;
                logic [3:0] byte_en;
            } noc_payload_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        layout = [c for c in claims if "Flit structure" in c["claim_text"]]
        assert len(layout) == 1
        assert "'noc_payload_t'" in layout[0]["claim_text"]

    def test_non_flit_type_no_layout(self):
        """Regular structs should NOT get a layout claim."""
        rtl = """
        package test_pkg;
            typedef struct packed {
                logic [7:0] data;
            } config_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        layout = [c for c in claims if "Flit structure" in c["claim_text"]]
        assert len(layout) == 0

    def test_layout_sorted_by_msb_descending(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                logic [3:0] low_field;
                logic [31:24] high_field;
                logic [15:8] mid_field;
            } test_flit_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        layout = [c for c in claims if "Flit structure" in c["claim_text"]]
        assert len(layout) == 1
        lt = layout[0]["claim_text"]
        # high_field (MSB=31) should come before mid_field (MSB=15) before low_field (MSB=3)
        high_pos = lt.index("high_field")
        mid_pos = lt.index("mid_field")
        low_pos = lt.index("low_field")
        assert high_pos < mid_pos < low_pos


# ---------------------------------------------------------------------------
# Req 20.4: Inline comment extraction
# ---------------------------------------------------------------------------

class TestInlineCommentExtraction:
    """Req 20.4: Parse inline comments and include in claim_text."""

    def test_inline_comment_included(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                logic [3:0] x_dest;  // destination X coordinate
                logic [3:0] y_dest;  // destination Y coordinate
            } noc_flit_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        field_claims = [c for c in claims if "field '" in c["claim_text"]]

        x_claim = [c for c in field_claims if "'x_dest'" in c["claim_text"]][0]
        assert "destination X coordinate" in x_claim["claim_text"]

        y_claim = [c for c in field_claims if "'y_dest'" in c["claim_text"]][0]
        assert "destination Y coordinate" in y_claim["claim_text"]

    def test_field_without_comment(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                logic [7:0] data;
            } simple_flit_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        field_claims = [c for c in claims if "field 'data'" in c["claim_text"]]
        assert len(field_claims) == 1
        # No parenthesized comment should appear
        assert "(" not in field_claims[0]["claim_text"] or "width" in field_claims[0]["claim_text"]


# ---------------------------------------------------------------------------
# Req 20.5: Type reference extraction
# ---------------------------------------------------------------------------

class TestTypeReferenceExtraction:
    """Req 20.5: Include referenced typedef name in claim."""

    def test_typedef_reference_included(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                tile_t dest_tile;
                logic [7:0] data;
            } noc_flit_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        field_claims = [c for c in claims if "field '" in c["claim_text"]]

        tile_claim = [c for c in field_claims if "'dest_tile'" in c["claim_text"]][0]
        assert "type reference 'tile_t'" in tile_claim["claim_text"]

    def test_typedef_reference_with_comment(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                tile_t dest_tile;  // destination tile coordinates
                logic [7:0] data;
            } noc_flit_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        tile_claims = [c for c in claims if "'dest_tile'" in c["claim_text"]]
        assert len(tile_claims) == 1
        ct = tile_claims[0]["claim_text"]
        assert "type reference 'tile_t'" in ct
        assert "destination tile coordinates" in ct


# ---------------------------------------------------------------------------
# parser_source validation
# ---------------------------------------------------------------------------

class TestParserSource:
    """All struct claims must have parser_source='package_struct_parser'."""

    def test_all_struct_claims_have_parser_source(self):
        rtl = """
        package noc_pkg;
            typedef struct packed {
                logic [3:0] x_dest;  // X coordinate
                tile_t dest_tile;
                logic [7:0] payload;
            } noc_flit_t;
        endpackage
        """
        claims = _get_struct_claims(rtl)
        for claim in claims:
            assert claim.get("parser_source") == "package_struct_parser", (
                f"Missing or wrong parser_source on claim: {claim['claim_text'][:80]}"
            )

    def test_non_struct_claims_unaffected(self):
        """Localparam/enum claims should NOT have package_struct_parser source."""
        rtl = """
        package test_pkg;
            localparam SizeX = 4;
            typedef enum { A, B } my_enum_t;
            typedef struct packed {
                logic [7:0] data;
            } data_t;
        endpackage
        """
        all_claims = extract_package_constants(rtl, "test.sv", "p1")
        for claim in all_claims:
            if "struct" not in claim["claim_text"].lower():
                assert claim.get("parser_source", "") != "package_struct_parser"


# ---------------------------------------------------------------------------
# Integration: realistic noc_pkg.sv-like content
# ---------------------------------------------------------------------------

class TestRealisticNocPackage:
    """Integration test with realistic NoC package content."""

    def test_full_noc_flit_struct(self):
        rtl = """
        package noc_pkg;
            localparam SizeX = 4;
            localparam SizeY = 5;

            typedef enum logic [2:0] {
                TENSIX = 0,
                NOC2AXI = 1
            } tile_type_t;

            typedef struct packed {
                logic [3:0] x_dest;       // destination X coordinate
                logic [3:0] y_dest;       // destination Y coordinate
                tile_type_t tile_type;    // destination tile type
                logic [15:0] payload;     // packet payload data
                logic        valid;       // valid bit
            } noc_flit_t;
        endpackage
        """
        all_claims = extract_package_constants(rtl, "noc_pkg.sv", "pipe1")

        # Should have struct summary claim
        summary = [c for c in all_claims
                   if "defines typedef struct 'noc_flit_t'" in c["claim_text"]]
        assert len(summary) == 1
        assert "5 fields" in summary[0]["claim_text"]

        # Should have per-field claims
        field_claims = [c for c in all_claims
                        if "defines struct 'noc_flit_t' field" in c["claim_text"]]
        assert len(field_claims) == 5

        # Check specific fields
        x_claim = [c for c in field_claims if "'x_dest'" in c["claim_text"]][0]
        assert "width 4" in x_claim["claim_text"]
        assert "destination X coordinate" in x_claim["claim_text"]

        tile_claim = [c for c in field_claims if "'tile_type'" in c["claim_text"]][0]
        assert "type reference 'tile_type_t'" in tile_claim["claim_text"]
        assert "destination tile type" in tile_claim["claim_text"]

        valid_claim = [c for c in field_claims if "'valid'" in c["claim_text"]][0]
        assert "width 1" in valid_claim["claim_text"]

        # Should have flit layout claim
        layout = [c for c in all_claims
                  if "Flit structure 'noc_flit_t' layout:" in c["claim_text"]]
        assert len(layout) == 1
        lt = layout[0]["claim_text"]
        assert "payload[15:0]" in lt
        assert "x_dest[3:0]" in lt
        assert "y_dest[3:0]" in lt
        assert "valid[0:0]" in lt

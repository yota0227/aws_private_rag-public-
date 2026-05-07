"""Unit tests for Instance-Position Mapping (Task 25).

Tests _extract_instance_positions and _extract_noc_repeaters functions
for NOC2AXI dual-row detection, NoC repeater extraction, EP ID parsing,
and position inference from generate block content.
"""

import unittest
from generate_block_parser import (
    extract_generate_blocks,
    _extract_instance_positions,
    _extract_noc_repeaters,
    _build_genvar_ranges,
    _extract_block_label,
    _infer_position_from_label,
)


class TestNOC2AXIDualRow(unittest.TestCase):
    """Test NOC2AXI dual-row detection (Y=4+3 format)."""

    def test_dual_row_detection_router_block(self):
        """Router block with 2 Y coordinates should produce Y=y1+y2 format."""
        block_content = """
        for (genvar y = 0; y < SizeY; y++) begin : gen_router
            noc2axi_bridge bridge_inst (
                .clk(clk),
                .ep_id(9),
                .data_in(data[3]),
                .data_out(data[4])
            );
        end
        """
        claims = _extract_instance_positions(
            block_content, "gen_router", {"y": {"start": "0", "limit": "SizeY"}},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertTrue(len(claims) > 0)
        # Should detect dual-row from the [3] and [4] references
        found_dual = any("3+4" in c["claim_text"] for c in claims)
        self.assertTrue(found_dual, f"Expected dual-row Y=3+4 in claims: {[c['claim_text'] for c in claims]}")

    def test_noc2axi_tile_type(self):
        """NOC2AXI instances should be tagged with NOC2AXI tile_type."""
        block_content = """
        noc2axi_wrapper u_noc2axi (
            .clk(clk),
            .ep_id(5)
        );
        """
        claims = _extract_instance_positions(
            block_content, "gen_noc2axi_block", {},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertTrue(len(claims) > 0)
        self.assertIn("NOC2AXI", claims[0]["claim_text"])


class TestNoCRepeaterExtraction(unittest.TestCase):
    """Test NoC repeater NUM parameter extraction."""

    def test_num_4_extraction(self):
        """Should extract NUM=4 from tt_noc_repeaters #(.NUM(4))."""
        block_content = """
        tt_noc_repeaters #(.NUM(4)) u_rep_east (
            .clk(clk),
            .data_in(data_in),
            .data_out(data_out)
        );
        """
        claims = _extract_noc_repeaters(
            block_content, "gen_col_0", {"y": {"start": "0", "limit": "SizeY"}},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertEqual(len(claims), 1)
        self.assertIn("NUM=4", claims[0]["claim_text"])
        self.assertIn("u_rep_east", claims[0]["claim_text"])

    def test_num_6_extraction(self):
        """Should extract NUM=6 from noc_repeater #(.NUM(6))."""
        block_content = """
        tt_noc_repeaters #(.NUM(6)) u_rep_west (
            .clk(clk)
        );
        """
        claims = _extract_noc_repeaters(
            block_content, "gen_col_1", {"y": {"start": "0", "limit": "4"}},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertEqual(len(claims), 1)
        self.assertIn("NUM=6", claims[0]["claim_text"])


class TestInterColumnPlacement(unittest.TestCase):
    """Test inter-column placement inference (X=1↔X=2)."""

    def test_default_inter_column(self):
        """Default inter-column placement should be X=1↔X=2."""
        block_content = """
        tt_noc_repeaters #(.NUM(4)) u_rep (
            .clk(clk)
        );
        """
        claims = _extract_noc_repeaters(
            block_content, "gen_repeater", {},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertEqual(len(claims), 1)
        self.assertIn("X=1\u2194X=2", claims[0]["claim_text"])

    def test_east_label_placement(self):
        """Block label with 'east' should infer X=0↔X=1."""
        block_content = """
        tt_noc_repeaters #(.NUM(4)) u_rep_e (
            .clk(clk)
        );
        """
        claims = _extract_noc_repeaters(
            block_content, "gen_east_repeater", {},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertEqual(len(claims), 1)
        self.assertIn("X=0\u2194X=1", claims[0]["claim_text"])

    def test_genvar_x_range_placement(self):
        """Genvar x range should override default X placement."""
        block_content = """
        tt_noc_repeaters #(.NUM(4)) u_rep (
            .clk(clk)
        );
        """
        claims = _extract_noc_repeaters(
            block_content, "gen_repeater",
            {"x": {"start": "0", "limit": "3"}, "y": {"start": "0", "limit": "5"}},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertEqual(len(claims), 1)
        self.assertIn("X=0\u2194X=3", claims[0]["claim_text"])


class TestEPIDExtraction(unittest.TestCase):
    """Test EP ID extraction from port connection."""

    def test_ep_id_numeric(self):
        """Should extract numeric EP ID from .ep_id(9)."""
        block_content = """
        some_module u_inst (
            .clk(clk),
            .ep_id(9),
            .data(data)
        );
        """
        claims = _extract_instance_positions(
            block_content, "gen_block", {},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertTrue(len(claims) > 0)
        self.assertIn("EP=9", claims[0]["claim_text"])

    def test_ep_id_expression(self):
        """Should extract expression EP ID from .endpoint_id(x*2+1)."""
        block_content = """
        some_module u_inst (
            .clk(clk),
            .endpoint_id(x*2+1),
            .data(data)
        );
        """
        claims = _extract_instance_positions(
            block_content, "gen_block", {},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertTrue(len(claims) > 0)
        self.assertIn("EP=x*2+1", claims[0]["claim_text"])

    def test_no_ep_id_fallback(self):
        """Should use UNKNOWN when no EP ID port is found."""
        block_content = """
        some_module u_inst (
            .clk(clk),
            .data(data)
        );
        """
        claims = _extract_instance_positions(
            block_content, "gen_block", {},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertTrue(len(claims) > 0)
        self.assertIn("EP=UNKNOWN", claims[0]["claim_text"])


class TestUnknownFallback(unittest.TestCase):
    """Test UNKNOWN fallback when position can't be inferred."""

    def test_no_genvar_no_label_heuristic(self):
        """Should use UNKNOWN for both X and Y when no info available."""
        block_content = """
        custom_module u_custom (
            .clk(clk)
        );
        """
        claims = _extract_instance_positions(
            block_content, "gen_misc", {},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertTrue(len(claims) > 0)
        self.assertIn("X=UNKNOWN", claims[0]["claim_text"])
        self.assertIn("Y=UNKNOWN", claims[0]["claim_text"])


class TestInstanceNameModuleName(unittest.TestCase):
    """Test instance name and module name are non-empty."""

    def test_instance_and_module_in_claim(self):
        """Claim should contain both instance module type and block label."""
        block_content = """
        my_module my_instance (
            .clk(clk)
        );
        """
        claims = _extract_instance_positions(
            block_content, "gen_test", {},
            "top_module", "test.sv", "pipe_001",
        )
        self.assertTrue(len(claims) > 0)
        self.assertIn("my_module", claims[0]["claim_text"])
        self.assertIn("gen_test", claims[0]["claim_text"])

    def test_keywords_are_skipped(self):
        """Keywords like 'if', 'for', 'assign' should not be treated as instances."""
        block_content = """
        if (condition) begin
            assign out = in;
        end
        """
        claims = _extract_instance_positions(
            block_content, "gen_test", {},
            "top_module", "test.sv", "pipe_001",
        )
        # Should not produce claims for keywords
        for claim in claims:
            self.assertNotIn("instantiates 'if'", claim["claim_text"])
            self.assertNotIn("instantiates 'assign'", claim["claim_text"])


class TestBlockLabelMapping(unittest.TestCase):
    """Test generate block label → module name mapping."""

    def test_ne_opt_label_x_position(self):
        """ne_opt label should infer X=1."""
        pos = _infer_position_from_label("gen_ne_opt_block")
        self.assertEqual(pos.get("x"), "1")

    def test_nw_opt_label_x_position(self):
        """nw_opt label should infer X=2."""
        pos = _infer_position_from_label("gen_nw_opt_block")
        self.assertEqual(pos.get("x"), "2")

    def test_empty_label_returns_empty(self):
        """Empty label should return empty dict."""
        pos = _infer_position_from_label("")
        self.assertEqual(pos, {})

    def test_build_genvar_ranges(self):
        """Should extract genvar ranges from for-loop headers."""
        block_text = """
        for (genvar x = 0; x < SizeX; x++) begin : gen_col
            for (genvar y = 0; y < SizeY; y++) begin : gen_row
                assign out[x][y] = in[x][y];
            end
        end
        """
        ranges = _build_genvar_ranges(block_text)
        self.assertIn("x", ranges)
        self.assertIn("y", ranges)
        self.assertEqual(ranges["x"]["start"], "0")
        self.assertEqual(ranges["x"]["limit"], "SizeX")
        self.assertEqual(ranges["y"]["start"], "0")
        self.assertEqual(ranges["y"]["limit"], "SizeY")

    def test_extract_block_label(self):
        """Should extract the first block label."""
        block_text = "for (...) begin : gen_my_block\n  ...\nend"
        label = _extract_block_label(block_text)
        self.assertEqual(label, "gen_my_block")


class TestParserSourceField(unittest.TestCase):
    """Test that parser_source is correctly set."""

    def test_instance_claims_parser_source(self):
        """Instance position claims should have parser_source = generate_block_parser."""
        block_content = """
        some_module u_inst (
            .clk(clk)
        );
        """
        claims = _extract_instance_positions(
            block_content, "gen_block", {},
            "top_module", "test.sv", "pipe_001",
        )
        for claim in claims:
            self.assertEqual(claim["parser_source"], "generate_block_parser")

    def test_repeater_claims_parser_source(self):
        """Repeater claims should have parser_source = generate_block_parser."""
        block_content = """
        tt_noc_repeaters #(.NUM(4)) u_rep (
            .clk(clk)
        );
        """
        claims = _extract_noc_repeaters(
            block_content, "gen_block", {},
            "top_module", "test.sv", "pipe_001",
        )
        for claim in claims:
            self.assertEqual(claim["parser_source"], "generate_block_parser")


if __name__ == "__main__":
    unittest.main()

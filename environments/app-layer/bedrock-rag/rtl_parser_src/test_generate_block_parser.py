"""Unit tests for Generate Block Parser (task 15.1).

Tests extract_generate_blocks() and internal helper functions for
topology pattern recognition in SystemVerilog generate blocks.
"""

import unittest
from generate_block_parser import (
    extract_generate_blocks,
    _strip_comments,
    _find_generate_blocks,
    _extract_for_loops,
    _find_nested_loops,
    _detect_topology_pattern,
    _detect_bypass,
    _extract_loop_body,
    _make_claim,
)


class TestStripComments(unittest.TestCase):
    """Test _strip_comments helper."""

    def test_single_line_comments(self):
        content = "assign a = b; // this is a comment\nassign c = d;"
        result = _strip_comments(content)
        self.assertNotIn("this is a comment", result)
        self.assertIn("assign a = b;", result)
        self.assertIn("assign c = d;", result)

    def test_block_comments(self):
        content = "assign a = b; /* block\ncomment */ assign c = d;"
        result = _strip_comments(content)
        self.assertNotIn("block", result)
        self.assertIn("assign a = b;", result)
        self.assertIn("assign c = d;", result)


class TestFindGenerateBlocks(unittest.TestCase):
    """Test _find_generate_blocks."""

    def test_single_generate_block(self):
        content = """
generate
  for (genvar x = 0; x < SizeX; x++) begin : gen_col
    assign out[x] = in[x];
  end
endgenerate
"""
        blocks = _find_generate_blocks(content)
        self.assertEqual(len(blocks), 1)
        self.assertIn("for (genvar x", blocks[0])

    def test_multiple_generate_blocks(self):
        content = """
generate
  for (genvar x = 0; x < 4; x++) begin : gen_a
    assign a[x] = b[x];
  end
endgenerate

generate
  for (genvar y = 0; y < 5; y++) begin : gen_b
    assign c[y] = d[y];
  end
endgenerate
"""
        blocks = _find_generate_blocks(content)
        self.assertEqual(len(blocks), 2)

    def test_empty_generate_block(self):
        content = "generate\nendgenerate"
        blocks = _find_generate_blocks(content)
        self.assertEqual(len(blocks), 0)


class TestExtractForLoops(unittest.TestCase):
    """Test _extract_for_loops."""

    def test_basic_for_loop(self):
        block = """
for (genvar x = 0; x < SizeX; x++) begin : gen_col
  assign out[x] = in[x];
end
"""
        loops = _extract_for_loops(block)
        self.assertEqual(len(loops), 1)
        self.assertEqual(loops[0]["genvar"], "x")
        self.assertEqual(loops[0]["start"], "0")
        self.assertEqual(loops[0]["limit"], "SizeX")
        self.assertEqual(loops[0]["label"], "gen_col")

    def test_for_loop_without_label(self):
        block = """
for (genvar i = 0; i < N; i++) begin
  assign out[i] = in[i];
end
"""
        loops = _extract_for_loops(block)
        self.assertEqual(len(loops), 1)
        self.assertEqual(loops[0]["genvar"], "i")
        self.assertEqual(loops[0]["label"], "")

    def test_nested_for_loops(self):
        block = """
for (genvar x = 0; x < SizeX; x++) begin : gen_x
  for (genvar y = 0; y < SizeY; y++) begin : gen_y
    assign out[x][y] = in[x][y];
  end
end
"""
        loops = _extract_for_loops(block)
        self.assertEqual(len(loops), 2)
        self.assertEqual(loops[0]["genvar"], "x")
        self.assertEqual(loops[1]["genvar"], "y")


class TestFindNestedLoops(unittest.TestCase):
    """Test _find_nested_loops."""

    def test_nested_2d_loops(self):
        block = """
for (genvar x = 0; x < SizeX; x++) begin : gen_x
  for (genvar y = 0; y < SizeY; y++) begin : gen_y
    assign out[x][y] = in[x][y];
  end
end
"""
        nested = _find_nested_loops(block)
        self.assertEqual(len(nested), 1)
        self.assertEqual(nested[0]["outer_genvar"], "x")
        self.assertEqual(nested[0]["inner_genvar"], "y")
        self.assertEqual(nested[0]["outer_limit"], "SizeX")
        self.assertEqual(nested[0]["inner_limit"], "SizeY")
        self.assertEqual(nested[0]["outer_label"], "gen_x")
        self.assertEqual(nested[0]["inner_label"], "gen_y")

    def test_no_nested_loops(self):
        block = """
for (genvar x = 0; x < SizeX; x++) begin : gen_x
  assign out[x] = in[x];
end
"""
        nested = _find_nested_loops(block)
        self.assertEqual(len(nested), 0)


class TestDetectTopologyPattern(unittest.TestCase):
    """Test _detect_topology_pattern for all 4 topology types."""

    def test_daisy_chain_pattern(self):
        body = """
        assign chain[y+1] = chain[y];
"""
        pattern_type, signal = _detect_topology_pattern(body, "y")
        self.assertEqual(pattern_type, "daisy-chain")
        self.assertEqual(signal, "chain")

    def test_feedthrough_pattern(self):
        body = """
        assign de_to_t6_column[y] = (y == 0) ? dispatch_out : t6_to_de[y-1];
"""
        pattern_type, signal = _detect_topology_pattern(body, "y")
        self.assertEqual(pattern_type, "feedthrough")
        self.assertEqual(signal, "de_to_t6_column")

    def test_ring_pattern(self):
        body = """
        assign ring_out[N-1] = ring_in[0];
"""
        pattern_type, signal = _detect_topology_pattern(body, "i")
        self.assertEqual(pattern_type, "ring")
        self.assertEqual(signal, "ring_out")

    def test_2d_array_pattern(self):
        body = """
        assign clock_routing_in[x][y].ai_clk = i_ai_clk;
"""
        pattern_type, signal = _detect_topology_pattern(body, "y", "x")
        self.assertEqual(pattern_type, "2D array")
        self.assertEqual(signal, "clock_routing_in")

    def test_2d_array_reversed_order(self):
        body = """
        assign data[y][x] = source;
"""
        pattern_type, signal = _detect_topology_pattern(body, "y", "x")
        self.assertEqual(pattern_type, "2D array")
        self.assertEqual(signal, "data")

    def test_daisy_chain_via_instance_ports(self):
        body = """
        tt_edc u_edc (
          .i_serial_in  (edc_chain[y]),
          .o_serial_out (edc_chain[y+1])
        );
"""
        pattern_type, signal = _detect_topology_pattern(body, "y")
        self.assertEqual(pattern_type, "daisy-chain")
        self.assertEqual(signal, "edc_chain")

    def test_unknown_pattern_fallback(self):
        body = """
        some_module u_inst (.clk(clk));
"""
        pattern_type, signal = _detect_topology_pattern(body, "i")
        self.assertEqual(pattern_type, "unknown")


class TestDetectBypass(unittest.TestCase):
    """Test _detect_bypass."""

    def test_bypass_pattern(self):
        body = """
      if (tile_type[x][y] != HARVESTED) begin
        tt_edc u_edc (
          .i_serial_in  (edc_chain[x][y]),
          .o_serial_out (edc_chain[x][y+1])
        );
      end else begin
        assign edc_chain[x][y+1] = edc_chain[x][y];
      end
"""
        result = _detect_bypass(body)
        self.assertIsNotNone(result)
        self.assertIn("HARVESTED", result["condition"])
        self.assertEqual(result["bypass_signal"], "edc_chain")

    def test_no_bypass(self):
        body = """
        assign out[x] = in[x];
"""
        result = _detect_bypass(body)
        self.assertIsNone(result)


class TestExtractLoopBody(unittest.TestCase):
    """Test _extract_loop_body."""

    def test_simple_body(self):
        block = "begin : label\n  assign a = b;\nend"
        body = _extract_loop_body(block, len("begin : label\n"))
        self.assertIn("assign a = b;", body)

    def test_nested_begin_end(self):
        block = (
            "begin : outer\n"
            "  if (cond) begin\n"
            "    assign a = b;\n"
            "  end\n"
            "end\n"
        )
        body = _extract_loop_body(block, len("begin : outer\n"))
        self.assertIn("if (cond) begin", body)
        self.assertIn("assign a = b;", body)

    def test_empty_body(self):
        body = _extract_loop_body("", 0)
        self.assertEqual(body, "")


class TestMakeClaim(unittest.TestCase):
    """Test _make_claim helper."""

    def test_claim_structure(self):
        claim = _make_claim(
            "test claim", "structural", "test_mod",
            "GenerateTopology", "test.sv", "pipe1",
            parser_source="generate_block_parser",
        )
        self.assertEqual(claim["analysis_type"], "claim")
        self.assertEqual(claim["claim_text"], "test claim")
        self.assertEqual(claim["module_name"], "test_mod")
        self.assertEqual(claim["topic"], "GenerateTopology")
        self.assertEqual(claim["file_path"], "test.sv")
        self.assertEqual(claim["pipeline_id"], "pipe1")
        self.assertEqual(claim["parser_source"], "generate_block_parser")
        self.assertIn("claim_id", claim)
        self.assertEqual(claim["confidence_score"], 1.0)

    def test_claim_without_parser_source(self):
        claim = _make_claim(
            "test", "structural", "mod", "topic", "f.sv", "p1",
        )
        self.assertNotIn("parser_source", claim)


class TestExtractGenerateBlocksIntegration(unittest.TestCase):
    """Integration tests using full RTL examples from the SoC Engineer doc."""

    def test_edc_u_shape_ring_with_bypass(self):
        """EDC U-shape ring topology with harvest bypass."""
        rtl = """
module trinity (
  input i_clk
);
generate
  for (genvar x = 0; x < SizeX; x++) begin : gen_edc_col
    for (genvar y = 0; y < SizeY; y++) begin : gen_edc_row
      if (tile_type[x][y] != HARVESTED) begin
        tt_edc u_edc (
          .i_serial_in  (edc_chain[x][y]),
          .o_serial_out (edc_chain[x][y+1])
        );
      end else begin
        assign edc_chain[x][y+1] = edc_chain[x][y];
      end
    end
  end
endgenerate
endmodule
"""
        claims = extract_generate_blocks(rtl, "trinity", "trinity.sv", "pipe1")
        self.assertGreaterEqual(len(claims), 1)

        claim = claims[0]
        self.assertEqual(claim["parser_source"], "generate_block_parser")
        self.assertEqual(claim["module_name"], "trinity")
        self.assertIn("gen_edc_col", claim["claim_text"])
        self.assertIn("edc_chain", claim["claim_text"])
        self.assertIn("2D", claim["claim_text"])
        self.assertIn("SizeX", claim["claim_text"])
        self.assertIn("SizeY", claim["claim_text"])
        # Should detect bypass
        self.assertIn("bypass", claim["claim_text"].lower())
        self.assertIn("HARVESTED", claim["claim_text"])

    def test_dispatch_feedthrough(self):
        """Dispatch feedthrough topology."""
        rtl = """
module trinity (
  input i_clk
);
generate
  for (genvar y = 0; y < SizeY; y++) begin : gen_dispatch_col
    assign de_to_t6_column[y] = (y == 0) ? dispatch_out : t6_to_de[y-1];
  end
endgenerate
endmodule
"""
        claims = extract_generate_blocks(rtl, "trinity", "trinity.sv", "pipe1")
        self.assertGreaterEqual(len(claims), 1)

        claim = claims[0]
        self.assertIn("feedthrough", claim["claim_text"])
        self.assertIn("de_to_t6_column", claim["claim_text"])
        self.assertIn("gen_dispatch_col", claim["claim_text"])
        self.assertIn("SizeY", claim["claim_text"])

    def test_clock_routing_2d_array(self):
        """Clock routing 2D array topology."""
        rtl = """
module trinity (
  input i_clk
);
generate
  for (genvar x = 0; x < SizeX; x++) begin : gen_clk_x
    for (genvar y = 0; y < SizeY; y++) begin : gen_clk_y
      assign clock_routing_in[x][y].ai_clk = i_ai_clk;
    end
  end
endgenerate
endmodule
"""
        claims = extract_generate_blocks(rtl, "trinity", "trinity.sv", "pipe1")
        self.assertGreaterEqual(len(claims), 1)

        claim = claims[0]
        self.assertIn("2D array", claim["claim_text"])
        self.assertIn("clock_routing_in", claim["claim_text"])
        self.assertIn("2D", claim["claim_text"])

    def test_no_generate_blocks(self):
        """RTL without generate blocks returns empty list."""
        rtl = """
module simple (
  input clk,
  output data
);
  assign data = 1'b0;
endmodule
"""
        claims = extract_generate_blocks(rtl, "simple", "simple.sv", "pipe1")
        self.assertEqual(len(claims), 0)

    def test_module_name_auto_detection(self):
        """Module name is auto-detected when not provided."""
        rtl = """
module auto_detect_mod (
  input clk
);
generate
  for (genvar i = 0; i < 4; i++) begin : gen_chain
    assign chain[i+1] = chain[i];
  end
endgenerate
endmodule
"""
        claims = extract_generate_blocks(rtl, "", "test.sv", "pipe1")
        self.assertGreaterEqual(len(claims), 1)
        self.assertEqual(claims[0]["module_name"], "auto_detect_mod")

    def test_generate_if_only(self):
        """Generate block with only if/else (no for loop)."""
        rtl = """
module cond_mod (
  input clk
);
generate
  if (FEATURE_ENABLED) begin : gen_feature
    feature_block u_feat (.clk(clk));
  end
endgenerate
endmodule
"""
        claims = extract_generate_blocks(rtl, "cond_mod", "cond.sv", "pipe1")
        self.assertGreaterEqual(len(claims), 1)
        self.assertIn("gen_feature", claims[0]["claim_text"])
        self.assertIn("FEATURE_ENABLED", claims[0]["claim_text"])

    def test_all_claims_have_parser_source(self):
        """All generated claims must have parser_source='generate_block_parser'."""
        rtl = """
module test_mod;
generate
  for (genvar x = 0; x < 4; x++) begin : gen_a
    for (genvar y = 0; y < 5; y++) begin : gen_b
      assign sig[x][y] = val;
    end
  end
endgenerate

generate
  for (genvar i = 0; i < 8; i++) begin : gen_c
    assign chain[i+1] = chain[i];
  end
endgenerate
endmodule
"""
        claims = extract_generate_blocks(rtl, "test_mod", "test.sv", "pipe1")
        for claim in claims:
            self.assertEqual(
                claim["parser_source"], "generate_block_parser",
                f"Claim missing parser_source: {claim['claim_text'][:60]}",
            )

    def test_claim_text_format(self):
        """Verify claim_text follows the required format."""
        rtl = """
module fmt_mod;
generate
  for (genvar i = 0; i < N; i++) begin : gen_chain
    assign data[i+1] = data[i];
  end
endgenerate
endmodule
"""
        claims = extract_generate_blocks(rtl, "fmt_mod", "fmt.sv", "pipe1")
        self.assertGreaterEqual(len(claims), 1)
        text = claims[0]["claim_text"]
        # Must contain required components
        self.assertIn("Module 'fmt_mod'", text)
        self.assertIn("has generate block", text)
        self.assertIn("topology connecting", text)
        self.assertIn("across", text)
        self.assertIn("elements)", text)

    def test_simple_daisy_chain(self):
        """Simple daisy-chain pattern with assign statement."""
        rtl = """
module daisy_mod;
generate
  for (genvar i = 0; i < 8; i++) begin : gen_daisy
    assign pipeline[i+1] = pipeline[i];
  end
endgenerate
endmodule
"""
        claims = extract_generate_blocks(rtl, "daisy_mod", "daisy.sv", "pipe1")
        self.assertGreaterEqual(len(claims), 1)
        self.assertIn("daisy-chain", claims[0]["claim_text"])
        self.assertIn("pipeline", claims[0]["claim_text"])


if __name__ == "__main__":
    unittest.main()

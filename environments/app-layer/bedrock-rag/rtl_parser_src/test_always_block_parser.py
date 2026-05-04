"""Unit tests for Always Block Parser (task 15.3).

Tests extract_clock_domains() and internal helper functions for
clock domain extraction from SystemVerilog always_ff blocks.
"""

import unittest
from always_block_parser import (
    extract_clock_domains,
    _strip_comments,
    _find_always_ff_blocks,
    _parse_sensitivity_list,
    _is_clock_signal,
    _is_reset_signal,
    _map_clock_to_domain,
    _make_claim,
)


class TestStripComments(unittest.TestCase):
    """Test _strip_comments helper."""

    def test_single_line_comments(self):
        content = "always_ff @(posedge clk) // clock edge\n  data <= 0;"
        result = _strip_comments(content)
        self.assertNotIn("clock edge", result)
        self.assertIn("always_ff", result)

    def test_block_comments(self):
        content = "always_ff /* block\ncomment */ @(posedge clk)"
        result = _strip_comments(content)
        self.assertNotIn("block", result)
        self.assertIn("always_ff", result)
        self.assertIn("@(posedge clk)", result)


class TestIsClockSignal(unittest.TestCase):
    """Test _is_clock_signal classification."""

    def test_standard_clock_signals(self):
        self.assertTrue(_is_clock_signal("i_ai_clk"))
        self.assertTrue(_is_clock_signal("i_noc_clk"))
        self.assertTrue(_is_clock_signal("clk"))
        self.assertTrue(_is_clock_signal("sys_clk"))
        self.assertTrue(_is_clock_signal("ref_clk"))

    def test_non_clock_signals(self):
        self.assertFalse(_is_clock_signal("i_ai_reset_n"))
        self.assertFalse(_is_clock_signal("data"))
        self.assertFalse(_is_clock_signal("rst_n"))


class TestIsResetSignal(unittest.TestCase):
    """Test _is_reset_signal classification."""

    def test_standard_reset_signals(self):
        self.assertTrue(_is_reset_signal("i_ai_reset_n"))
        self.assertTrue(_is_reset_signal("reset"))
        self.assertTrue(_is_reset_signal("rst_n"))
        self.assertTrue(_is_reset_signal("i_noc_reset_n"))

    def test_non_reset_signals(self):
        self.assertFalse(_is_reset_signal("i_ai_clk"))
        self.assertFalse(_is_reset_signal("data"))
        self.assertFalse(_is_reset_signal("enable"))


class TestMapClockToDomain(unittest.TestCase):
    """Test _map_clock_to_domain mapping rules."""

    def test_known_mappings(self):
        self.assertEqual(_map_clock_to_domain("i_ai_clk"), "AI")
        self.assertEqual(_map_clock_to_domain("i_noc_clk"), "NoC")
        self.assertEqual(_map_clock_to_domain("i_dm_clk"), "DM")

    def test_derived_domain_with_prefix(self):
        self.assertEqual(_map_clock_to_domain("i_pcie_clk"), "pcie")
        self.assertEqual(_map_clock_to_domain("i_usb_clk"), "usb")

    def test_derived_domain_without_prefix(self):
        self.assertEqual(_map_clock_to_domain("ref_clk"), "ref")
        self.assertEqual(_map_clock_to_domain("sys_clk"), "sys")

    def test_bare_clk_signal(self):
        # "clk" → strip _clk suffix leaves empty → return original
        self.assertEqual(_map_clock_to_domain("clk"), "clk")

    def test_output_prefix(self):
        self.assertEqual(_map_clock_to_domain("o_test_clk"), "test")


class TestParseSensitivityList(unittest.TestCase):
    """Test _parse_sensitivity_list."""

    def test_single_clock(self):
        result = _parse_sensitivity_list("posedge i_ai_clk")
        self.assertEqual(result["clocks"], ["i_ai_clk"])
        self.assertIn("AI", result["domains"])
        self.assertEqual(len(result["resets"]), 0)

    def test_clock_and_reset_with_or(self):
        result = _parse_sensitivity_list(
            "posedge i_ai_clk or negedge i_ai_reset_n"
        )
        self.assertEqual(result["clocks"], ["i_ai_clk"])
        self.assertIn("AI", result["domains"])
        self.assertIn("i_ai_reset_n", result["resets"])

    def test_clock_and_reset_with_comma(self):
        result = _parse_sensitivity_list(
            "posedge i_noc_clk, negedge rst_n"
        )
        self.assertEqual(result["clocks"], ["i_noc_clk"])
        self.assertIn("NoC", result["domains"])
        self.assertIn("rst_n", result["resets"])

    def test_negedge_clock(self):
        result = _parse_sensitivity_list("negedge i_dm_clk")
        self.assertEqual(result["clocks"], ["i_dm_clk"])
        self.assertIn("DM", result["domains"])

    def test_edge_info_preserved(self):
        result = _parse_sensitivity_list(
            "posedge i_ai_clk or negedge i_ai_reset_n"
        )
        self.assertEqual(len(result["edge_info"]), 2)
        self.assertEqual(result["edge_info"][0], ("posedge", "i_ai_clk"))
        self.assertEqual(result["edge_info"][1], ("negedge", "i_ai_reset_n"))


class TestFindAlwaysFFBlocks(unittest.TestCase):
    """Test _find_always_ff_blocks."""

    def test_single_always_ff(self):
        content = """
always_ff @(posedge i_ai_clk or negedge i_ai_reset_n) begin
  if (!i_ai_reset_n) data <= 0;
  else data <= next_data;
end
"""
        blocks = _find_always_ff_blocks(content)
        self.assertEqual(len(blocks), 1)
        self.assertIn("AI", blocks[0]["domains"])
        self.assertIn("i_ai_reset_n", blocks[0]["resets"])

    def test_multiple_always_ff(self):
        content = """
always_ff @(posedge i_ai_clk) begin
  ai_reg <= ai_data;
end

always_ff @(posedge i_noc_clk) begin
  noc_reg <= noc_data;
end
"""
        blocks = _find_always_ff_blocks(content)
        self.assertEqual(len(blocks), 2)

    def test_always_comb_excluded(self):
        content = """
always_comb begin
  next_state = current_state;
end

always_ff @(posedge i_ai_clk) begin
  state <= next_state;
end
"""
        blocks = _find_always_ff_blocks(content)
        self.assertEqual(len(blocks), 1)
        self.assertIn("AI", blocks[0]["domains"])

    def test_no_always_blocks(self):
        content = "assign data = 1'b0;"
        blocks = _find_always_ff_blocks(content)
        self.assertEqual(len(blocks), 0)

    def test_only_always_comb(self):
        content = """
always_comb begin
  next_state = current_state;
  case (current_state)
    IDLE: if (start) next_state = ACTIVE;
  endcase
end
"""
        blocks = _find_always_ff_blocks(content)
        self.assertEqual(len(blocks), 0)


class TestMakeClaim(unittest.TestCase):
    """Test _make_claim helper."""

    def test_claim_structure(self):
        claim = _make_claim(
            "test claim", "clock_domain", "test_mod",
            "ClockDomain", "test.sv", "pipe1",
            parser_source="always_block_parser",
        )
        self.assertEqual(claim["analysis_type"], "claim")
        self.assertEqual(claim["claim_text"], "test claim")
        self.assertEqual(claim["claim_type"], "clock_domain")
        self.assertEqual(claim["module_name"], "test_mod")
        self.assertEqual(claim["topic"], "ClockDomain")
        self.assertEqual(claim["file_path"], "test.sv")
        self.assertEqual(claim["pipeline_id"], "pipe1")
        self.assertEqual(claim["parser_source"], "always_block_parser")
        self.assertIn("claim_id", claim)
        self.assertEqual(claim["confidence_score"], 1.0)

    def test_claim_without_parser_source(self):
        claim = _make_claim(
            "test", "clock_domain", "mod", "topic", "f.sv", "p1",
        )
        self.assertNotIn("parser_source", claim)


class TestExtractClockDomainsIntegration(unittest.TestCase):
    """Integration tests using full RTL examples."""

    def test_single_clock_domain(self):
        """Single clock domain with reset — Req 19.1, 19.2, 19.3, 19.7."""
        rtl = """
module ai_reg_block (
  input i_ai_clk,
  input i_ai_reset_n,
  input [7:0] next_data,
  output reg [7:0] data
);
always_ff @(posedge i_ai_clk or negedge i_ai_reset_n) begin
  if (!i_ai_reset_n) data <= 0;
  else data <= next_data;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "ai_reg_block", "ai_reg.sv", "pipe1",
        )
        self.assertEqual(len(claims), 1)  # Only summary, no CDC

        summary = claims[0]
        self.assertIn("Module 'ai_reg_block'", summary["claim_text"])
        self.assertIn("1 clock domain", summary["claim_text"])
        self.assertIn("AI", summary["claim_text"])
        self.assertIn("i_ai_reset_n", summary["claim_text"])
        self.assertEqual(summary["parser_source"], "always_block_parser")
        self.assertEqual(summary["claim_type"], "clock_domain")

    def test_multiple_clock_domains_cdc(self):
        """Multiple clock domains trigger CDC warnings — Req 19.4."""
        rtl = """
module cdc_module (
  input i_ai_clk,
  input i_noc_clk
);
always_ff @(posedge i_ai_clk) begin
  ai_reg <= ai_data;
end

always_ff @(posedge i_noc_clk) begin
  noc_reg <= noc_data;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "cdc_module", "cdc.sv", "pipe1",
        )
        # 1 summary + 1 CDC pair (AI, NoC)
        self.assertEqual(len(claims), 2)

        summary = claims[0]
        self.assertIn("2 clock domains", summary["claim_text"])
        self.assertIn("AI", summary["claim_text"])
        self.assertIn("NoC", summary["claim_text"])

        cdc = claims[1]
        self.assertIn("clock domain crossing", cdc["claim_text"])
        self.assertIn("AI", cdc["claim_text"])
        self.assertIn("NoC", cdc["claim_text"])
        self.assertEqual(cdc["claim_type"], "clock_domain_crossing")

    def test_three_domains_all_cdc_pairs(self):
        """Three domains generate 3 CDC pair claims — all pairs."""
        rtl = """
module triple_domain (
  input i_ai_clk,
  input i_noc_clk,
  input i_dm_clk
);
always_ff @(posedge i_ai_clk) begin
  ai_reg <= ai_data;
end

always_ff @(posedge i_noc_clk) begin
  noc_reg <= noc_data;
end

always_ff @(posedge i_dm_clk) begin
  dm_reg <= dm_data;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "triple_domain", "triple.sv", "pipe1",
        )
        # 1 summary + 3 CDC pairs (AI-DM, AI-NoC, DM-NoC)
        self.assertEqual(len(claims), 4)

        summary = claims[0]
        self.assertIn("3 clock domains", summary["claim_text"])

        cdc_texts = [c["claim_text"] for c in claims[1:]]
        # All 3 pairs should be present
        self.assertEqual(len(cdc_texts), 3)
        for text in cdc_texts:
            self.assertIn("clock domain crossing", text)

    def test_always_comb_excluded(self):
        """always_comb blocks should not contribute clock domains — Req 19.6."""
        rtl = """
module mixed_module (
  input i_ai_clk
);
always_comb begin
  next_state = current_state;
  case (current_state)
    IDLE: if (start) next_state = ACTIVE;
  endcase
end

always_ff @(posedge i_ai_clk) begin
  state <= next_state;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "mixed_module", "mixed.sv", "pipe1",
        )
        self.assertEqual(len(claims), 1)
        self.assertIn("1 clock domain", claims[0]["claim_text"])
        self.assertIn("AI", claims[0]["claim_text"])

    def test_no_always_blocks(self):
        """RTL without always blocks returns empty list."""
        rtl = """
module combinational (
  input a,
  output b
);
  assign b = a;
endmodule
"""
        claims = extract_clock_domains(
            rtl, "combinational", "comb.sv", "pipe1",
        )
        self.assertEqual(len(claims), 0)

    def test_only_always_comb(self):
        """RTL with only always_comb returns empty list."""
        rtl = """
module comb_only;
always_comb begin
  next_state = current_state;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "comb_only", "comb_only.sv", "pipe1",
        )
        self.assertEqual(len(claims), 0)

    def test_module_name_auto_detection(self):
        """Module name is auto-detected when not provided."""
        rtl = """
module auto_detect_mod (
  input i_ai_clk
);
always_ff @(posedge i_ai_clk) begin
  data <= next_data;
end
endmodule
"""
        claims = extract_clock_domains(rtl, "", "test.sv", "pipe1")
        self.assertGreaterEqual(len(claims), 1)
        self.assertEqual(claims[0]["module_name"], "auto_detect_mod")

    def test_derived_clock_domain(self):
        """Unknown clock signal derives domain from name — Req 19.2."""
        rtl = """
module custom_clk_mod;
always_ff @(posedge ref_clk) begin
  data <= next_data;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "custom_clk_mod", "custom.sv", "pipe1",
        )
        self.assertEqual(len(claims), 1)
        self.assertIn("ref", claims[0]["claim_text"])

    def test_reset_signals_in_claim(self):
        """Reset signals from sensitivity list appear in claims — Req 19.7."""
        rtl = """
module reset_mod;
always_ff @(posedge i_noc_clk or negedge i_noc_reset_n) begin
  if (!i_noc_reset_n) reg_a <= 0;
  else reg_a <= data;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "reset_mod", "reset.sv", "pipe1",
        )
        self.assertEqual(len(claims), 1)
        self.assertIn("Reset signals", claims[0]["claim_text"])
        self.assertIn("i_noc_reset_n", claims[0]["claim_text"])

    def test_all_claims_have_parser_source(self):
        """All claims must have parser_source='always_block_parser'."""
        rtl = """
module multi_mod;
always_ff @(posedge i_ai_clk) begin
  ai_reg <= ai_data;
end
always_ff @(posedge i_noc_clk) begin
  noc_reg <= noc_data;
end
always_ff @(posedge i_dm_clk) begin
  dm_reg <= dm_data;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "multi_mod", "multi.sv", "pipe1",
        )
        for claim in claims:
            self.assertEqual(
                claim["parser_source"], "always_block_parser",
                f"Claim missing parser_source: {claim['claim_text'][:60]}",
            )

    def test_duplicate_clock_domains_deduplicated(self):
        """Multiple always_ff with same clock produce single domain."""
        rtl = """
module dup_clk_mod;
always_ff @(posedge i_ai_clk) begin
  reg_a <= data_a;
end
always_ff @(posedge i_ai_clk) begin
  reg_b <= data_b;
end
always_ff @(posedge i_ai_clk or negedge i_ai_reset_n) begin
  reg_c <= data_c;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "dup_clk_mod", "dup.sv", "pipe1",
        )
        # Only 1 summary claim, no CDC (single domain)
        self.assertEqual(len(claims), 1)
        self.assertIn("1 clock domain", claims[0]["claim_text"])
        self.assertIn("AI", claims[0]["claim_text"])

    def test_negedge_clock(self):
        """Negedge clock is also extracted."""
        rtl = """
module neg_clk_mod;
always_ff @(negedge i_dm_clk) begin
  data <= next_data;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "neg_clk_mod", "neg.sv", "pipe1",
        )
        self.assertEqual(len(claims), 1)
        self.assertIn("DM", claims[0]["claim_text"])

    def test_claim_text_format_summary(self):
        """Verify summary claim_text follows required format — Req 19.3."""
        rtl = """
module fmt_mod;
always_ff @(posedge i_ai_clk) begin
  data <= next_data;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "fmt_mod", "fmt.sv", "pipe1",
        )
        self.assertGreaterEqual(len(claims), 1)
        text = claims[0]["claim_text"]
        self.assertIn("Module 'fmt_mod'", text)
        self.assertIn("operates in", text)
        self.assertIn("clock domain", text)

    def test_claim_text_format_cdc(self):
        """Verify CDC claim_text follows required format — Req 19.4."""
        rtl = """
module cdc_fmt_mod;
always_ff @(posedge i_ai_clk) begin
  a <= b;
end
always_ff @(posedge i_noc_clk) begin
  c <= d;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "cdc_fmt_mod", "cdc_fmt.sv", "pipe1",
        )
        cdc_claims = [
            c for c in claims if c["claim_type"] == "clock_domain_crossing"
        ]
        self.assertGreaterEqual(len(cdc_claims), 1)
        text = cdc_claims[0]["claim_text"]
        self.assertIn("Module 'cdc_fmt_mod'", text)
        self.assertIn("has potential clock domain crossing between", text)

    def test_comments_do_not_affect_parsing(self):
        """Comments containing always_ff should not be parsed."""
        rtl = """
module comment_mod;
// always_ff @(posedge fake_clk) begin
//   fake_reg <= fake_data;
// end

/* always_ff @(posedge another_fake_clk) begin
   another_fake <= data;
end */

always_ff @(posedge i_ai_clk) begin
  real_reg <= real_data;
end
endmodule
"""
        claims = extract_clock_domains(
            rtl, "comment_mod", "comment.sv", "pipe1",
        )
        self.assertEqual(len(claims), 1)
        self.assertIn("AI", claims[0]["claim_text"])
        self.assertNotIn("fake", claims[0]["claim_text"])


if __name__ == "__main__":
    unittest.main()

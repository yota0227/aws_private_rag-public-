"""Unit tests for Wire Declaration Parser (Task 26).

Tests extract_wire_declarations() for Pattern A/B/C matching,
dimension parsing, purpose inference, feature flag control,
and parser_source field correctness.
"""

import os
import unittest
from unittest.mock import patch

from wire_declaration_parser import (
    extract_wire_declarations,
    _parse_dimensions,
    _infer_purpose,
    PARSER_WIRE_DECLARATION_ENABLED,
)


class TestPatternA(unittest.TestCase):
    """Test Pattern A: wire/logic struct_type signal_name[dims];"""

    def test_wire_struct_type_with_dimensions(self):
        """Should parse: wire trinity_clock_routing_t clock_routing_in[SizeX][SizeY];"""
        rtl = """
module test_mod (
    input clk
);
    wire trinity_clock_routing_t clock_routing_in[SizeX][SizeY];
endmodule
"""
        claims = extract_wire_declarations(rtl, "test_mod", "test.sv", "pipe_001")
        self.assertTrue(len(claims) > 0)
        claim = claims[0]
        self.assertIn("clock_routing_in", claim["claim_text"])
        self.assertIn("trinity_clock_routing_t", claim["claim_text"])
        self.assertIn("SizeX", claim["claim_text"])
        self.assertIn("SizeY", claim["claim_text"])
        self.assertIn("of type", claim["claim_text"])

    def test_logic_struct_type(self):
        """Should parse: logic some_struct_t my_signal[4][8];"""
        rtl = "logic some_struct_t my_signal[4][8];"
        claims = extract_wire_declarations(rtl, "mod", "f.sv", "p1")
        self.assertTrue(len(claims) > 0)
        self.assertIn("my_signal", claims[0]["claim_text"])
        self.assertIn("some_struct_t", claims[0]["claim_text"])


class TestPatternB(unittest.TestCase):
    """Test Pattern B: logic [N:0] signal_name[dims];"""

    def test_logic_bit_range_with_array(self):
        """Should parse: logic [31:0] some_signal[4];"""
        rtl = "logic [31:0] some_signal[4];"
        claims = extract_wire_declarations(rtl, "mod", "f.sv", "p1")
        self.assertTrue(len(claims) > 0)
        claim = claims[0]
        self.assertIn("some_signal", claim["claim_text"])
        self.assertIn("4", claim["claim_text"])
        # Pattern B should produce "connects" not "of type"
        self.assertIn("connects", claim["claim_text"])


class TestPatternC(unittest.TestCase):
    """Test Pattern C: type_name_t signal_name[dims]; (no wire keyword)"""

    def test_implicit_wire_with_t_type(self):
        """Should parse: trinity_clock_routing_t clock_routing_out[SizeX][SizeY];"""
        rtl = """
trinity_clock_routing_t clock_routing_out[SizeX][SizeY];
"""
        claims = extract_wire_declarations(rtl, "mod", "f.sv", "p1")
        self.assertTrue(len(claims) > 0)
        claim = claims[0]
        self.assertIn("clock_routing_out", claim["claim_text"])
        self.assertIn("trinity_clock_routing_t", claim["claim_text"])
        self.assertIn("of type", claim["claim_text"])

    def test_three_dimension_preservation(self):
        """Req 8.1/8.2: de_to_t6_coloumn[SizeX][SizeY-1][2] → dims = [SizeX, SizeY-1, 2]"""
        rtl = "tt_chip_global_pkg::de_to_t6_t de_to_t6_coloumn[SizeX][SizeY-1][2];"
        claims = extract_wire_declarations(rtl, "trinity_top", "test.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        claim_text = claims[0]["claim_text"]
        self.assertIn("de_to_t6_coloumn", claim_text)
        self.assertIn("SizeX", claim_text)
        self.assertIn("SizeY-1", claim_text)
        self.assertIn("2", claim_text)
        # Verify all 3 dimensions are in the dimensions list
        self.assertIn("[SizeX, SizeY-1, 2]", claim_text)

    def test_packed_and_array_dimensions_separated(self):
        """Req 8.3: Packed dims should not appear in array dims."""
        rtl = "de_to_t6_t [NumDispatchCorners-1:0] de_to_t6_coloumn[SizeX][SizeY-1][2];"
        claims = extract_wire_declarations(rtl, "trinity_top", "test.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        claim_text = claims[0]["claim_text"]
        # Array dimensions should be [SizeX, SizeY-1, 2] — packed dim excluded
        self.assertIn("[SizeX, SizeY-1, 2]", claim_text)
        # Packed dimension should NOT appear in the dimensions list
        self.assertNotIn("NumDispatchCorners", claim_text)

    def test_multiple_packed_dimensions_separated(self):
        """Multiple packed dims should not leak into array dims."""
        rtl = "de_to_t6_t [3:0][7:0] de_to_t6_coloumn[SizeX][SizeY-1][2];"
        claims = extract_wire_declarations(rtl, "trinity_top", "test.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        claim_text = claims[0]["claim_text"]
        self.assertIn("[SizeX, SizeY-1, 2]", claim_text)


class TestDimensionParsing(unittest.TestCase):
    """Test dimension parsing: [SizeX][SizeY-1][2] → ['SizeX', 'SizeY-1', '2']"""

    def test_multiple_dimensions(self):
        """Should parse [SizeX][SizeY-1][2] into list."""
        result = _parse_dimensions("[SizeX][SizeY-1][2]")
        self.assertEqual(result, ['SizeX', 'SizeY-1', '2'])

    def test_single_dimension(self):
        """Should parse [4] into single-element list."""
        result = _parse_dimensions("[4]")
        self.assertEqual(result, ['4'])

    def test_expression_dimension(self):
        """Should parse [N*2+1] correctly."""
        result = _parse_dimensions("[N*2+1]")
        self.assertEqual(result, ['N*2+1'])

    def test_two_dimensions(self):
        """Should parse [SizeX][SizeY] into two elements."""
        result = _parse_dimensions("[SizeX][SizeY]")
        self.assertEqual(result, ['SizeX', 'SizeY'])


class TestPurposeInference(unittest.TestCase):
    """Test purpose inference from signal names."""

    def test_dispatch_to_tensix(self):
        """de_to_t6_coloumn should infer dispatch-to-tensix feedthrough."""
        purpose = _infer_purpose("de_to_t6_coloumn")
        self.assertEqual(purpose, "dispatch-to-tensix feedthrough")

    def test_clock_routing(self):
        """clock_routing_in should infer clock distribution."""
        purpose = _infer_purpose("clock_routing_in")
        self.assertEqual(purpose, "clock distribution")

    def test_noc_signal(self):
        """noc_data_bus should infer NoC interconnect."""
        purpose = _infer_purpose("noc_data_bus")
        self.assertEqual(purpose, "NoC interconnect")

    def test_axi_signal(self):
        """axi_master_out should infer AXI bus connection."""
        purpose = _infer_purpose("axi_master_out")
        self.assertEqual(purpose, "AXI bus connection")

    def test_unknown_signal(self):
        """Unknown signal should return general interconnect."""
        purpose = _infer_purpose("random_signal_xyz")
        self.assertEqual(purpose, "general interconnect")

    def test_edc_signal(self):
        """edc_chain should infer EDC ring connection."""
        purpose = _infer_purpose("edc_chain_data")
        self.assertEqual(purpose, "EDC ring connection")


class TestFeatureFlag(unittest.TestCase):
    """Test feature flag control."""

    def test_feature_flag_off_returns_empty(self):
        """When PARSER_WIRE_DECLARATION_ENABLED is false, no claims generated."""
        import wire_declaration_parser
        original = wire_declaration_parser.PARSER_WIRE_DECLARATION_ENABLED
        try:
            wire_declaration_parser.PARSER_WIRE_DECLARATION_ENABLED = False
            rtl = "wire trinity_clock_routing_t clock_routing_in[SizeX][SizeY];"
            claims = extract_wire_declarations(rtl, "mod", "f.sv", "p1")
            self.assertEqual(claims, [])
        finally:
            wire_declaration_parser.PARSER_WIRE_DECLARATION_ENABLED = original


class TestEmptyInput(unittest.TestCase):
    """Test empty input handling."""

    def test_empty_string_returns_empty(self):
        """Empty input should return empty list."""
        claims = extract_wire_declarations("", "mod", "f.sv", "p1")
        self.assertEqual(claims, [])

    def test_no_wire_declarations(self):
        """RTL without wire declarations should return empty list."""
        rtl = """
module simple_mod (
    input clk,
    output data
);
    assign data = clk;
endmodule
"""
        claims = extract_wire_declarations(rtl, "simple_mod", "f.sv", "p1")
        self.assertEqual(claims, [])


class TestParserSourceField(unittest.TestCase):
    """Test parser_source field is wire_declaration_parser."""

    def test_parser_source_set_correctly(self):
        """All claims should have parser_source = wire_declaration_parser."""
        rtl = "wire trinity_clock_routing_t clock_routing_in[SizeX][SizeY];"
        claims = extract_wire_declarations(rtl, "mod", "f.sv", "p1")
        self.assertTrue(len(claims) > 0)
        for claim in claims:
            self.assertEqual(claim["parser_source"], "wire_declaration_parser")


class TestSignalNameNonEmpty(unittest.TestCase):
    """Test signal name is non-empty in all claims."""

    def test_all_claims_have_signal_name(self):
        """Every claim should reference a non-empty signal name."""
        rtl = """
wire trinity_clock_routing_t clock_routing_in[SizeX][SizeY];
logic [31:0] noc_data[8];
trinity_clock_routing_t clock_routing_out[SizeX][SizeY];
"""
        claims = extract_wire_declarations(rtl, "mod", "f.sv", "p1")
        self.assertTrue(len(claims) > 0)
        import re
        for claim in claims:
            match = re.search(r"Wire '(\w+)'", claim["claim_text"])
            self.assertIsNotNone(match, f"No signal name in: {claim['claim_text']}")
            self.assertTrue(len(match.group(1)) > 0)


class TestStructReference(unittest.TestCase):
    """Test known_structs reference in claims."""

    def test_known_struct_reference_included(self):
        """When struct type is in known_structs, claim should include reference."""
        rtl = "wire trinity_clock_routing_t clock_routing_in[SizeX][SizeY];"
        claims = extract_wire_declarations(
            rtl, "mod", "f.sv", "p1",
            known_structs=["trinity_clock_routing_t"],
        )
        self.assertTrue(len(claims) > 0)
        self.assertIn("references struct", claims[0]["claim_text"])

    def test_unknown_struct_no_reference(self):
        """When struct type is NOT in known_structs, no reference tag."""
        rtl = "wire trinity_clock_routing_t clock_routing_in[SizeX][SizeY];"
        claims = extract_wire_declarations(
            rtl, "mod", "f.sv", "p1",
            known_structs=[],
        )
        self.assertTrue(len(claims) > 0)
        self.assertNotIn("references struct", claims[0]["claim_text"])


class TestClaimTopicField(unittest.TestCase):
    """Test that topic is set to WireTopology."""

    def test_topic_is_wire_topology(self):
        """All wire claims should have topic = WireTopology."""
        rtl = "wire trinity_clock_routing_t clock_routing_in[SizeX][SizeY];"
        claims = extract_wire_declarations(rtl, "mod", "f.sv", "p1")
        self.assertTrue(len(claims) > 0)
        for claim in claims:
            self.assertEqual(claim["topic"], "WireTopology")


if __name__ == "__main__":
    unittest.main()

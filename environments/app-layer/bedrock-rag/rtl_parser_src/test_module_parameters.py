"""
Tests for extract_module_parameters() — Task 5.1.

Validates Requirements 7.1, 7.2, 7.3, 7.4:
- 7.1: Extract parameter name and default value from top-level module
- 7.2: Numeric values stored as claims with topic "TopLevelParameter"
- 7.3: Expression default values preserved as-is (string)
- 7.4: Minimum extraction targets: AXI_SLV_OUTSTANDING_READS,
       AXI_SLV_OUTSTANDING_WRITES, AXI_SLV_RD_RDATA_FIFO_DEPTH
"""

import pytest
from package_extractor import extract_module_parameters


# ---------------------------------------------------------------------------
# Pattern 1: module #( parameter ... ) (ports);
# ---------------------------------------------------------------------------

class TestPattern1HeaderParameters:
    """Parameters declared in the module header #(...) block."""

    RTL_HEADER_PARAMS = """\
module trinity_top #(
    parameter int AXI_SLV_OUTSTANDING_READS = 64,
    parameter int AXI_SLV_OUTSTANDING_WRITES = 32,
    parameter int AXI_SLV_RD_RDATA_FIFO_DEPTH = 128
) (
    input  wire clk,
    input  wire rst_n,
    output wire [31:0] data_out
);
    // module body
endmodule
"""

    def test_extracts_all_three_axi_params(self):
        """Req 7.4: minimum extraction targets."""
        claims = extract_module_parameters(
            self.RTL_HEADER_PARAMS, "trinity_top", "trinity_top.sv", "tt_001"
        )
        names = [c["claim_text"].split("parameter ")[1].split(" = ")[0]
                 for c in claims]
        assert "AXI_SLV_OUTSTANDING_READS" in names
        assert "AXI_SLV_OUTSTANDING_WRITES" in names
        assert "AXI_SLV_RD_RDATA_FIFO_DEPTH" in names

    def test_numeric_value_preserved(self):
        """Req 7.2: numeric default values stored correctly."""
        claims = extract_module_parameters(
            self.RTL_HEADER_PARAMS, "trinity_top", "trinity_top.sv", "tt_001"
        )
        reads_claim = next(
            c for c in claims if "AXI_SLV_OUTSTANDING_READS" in c["claim_text"]
        )
        assert "= 64" in reads_claim["claim_text"]

    def test_claim_type_structural(self):
        """Req 7.2: claim_type is structural."""
        claims = extract_module_parameters(
            self.RTL_HEADER_PARAMS, "trinity_top", "trinity_top.sv", "tt_001"
        )
        for c in claims:
            assert c["claim_type"] == "structural"

    def test_topic_is_top_level_parameter(self):
        """Req 7.2: topic is TopLevelParameter."""
        claims = extract_module_parameters(
            self.RTL_HEADER_PARAMS, "trinity_top", "trinity_top.sv", "tt_001"
        )
        for c in claims:
            assert c["topic"] == "TopLevelParameter"

    def test_module_name_in_claim(self):
        """Req 7.1: module_name field set correctly."""
        claims = extract_module_parameters(
            self.RTL_HEADER_PARAMS, "trinity_top", "trinity_top.sv", "tt_001"
        )
        for c in claims:
            assert c["module_name"] == "trinity_top"


# ---------------------------------------------------------------------------
# Pattern 2: Internal parameter declarations
# ---------------------------------------------------------------------------

class TestPattern2InternalParameters:
    """Parameters declared inside the module body."""

    RTL_INTERNAL_PARAMS = """\
module axi_slave (
    input  wire clk,
    output wire ready
);
    parameter int AXI_SLV_OUTSTANDING_READS = 64;
    parameter int AXI_SLV_OUTSTANDING_WRITES = 32;
    parameter int AXI_SLV_RD_RDATA_FIFO_DEPTH = 128;

    // module logic
    assign ready = 1'b1;
endmodule
"""

    def test_extracts_internal_params(self):
        """Req 7.1: extract parameters from module body."""
        claims = extract_module_parameters(
            self.RTL_INTERNAL_PARAMS, "axi_slave", "axi_slave.sv", "tt_001"
        )
        assert len(claims) == 3
        names = [c["claim_text"].split("parameter ")[1].split(" = ")[0]
                 for c in claims]
        assert "AXI_SLV_OUTSTANDING_READS" in names
        assert "AXI_SLV_OUTSTANDING_WRITES" in names
        assert "AXI_SLV_RD_RDATA_FIFO_DEPTH" in names


# ---------------------------------------------------------------------------
# Expression default values
# ---------------------------------------------------------------------------

class TestExpressionDefaultValues:
    """Expression values preserved as strings (Req 7.3)."""

    RTL_EXPRESSION_PARAMS = """\
module fifo_ctrl #(
    parameter int WIDTH = 32,
    parameter DEPTH = WIDTH * 2,
    parameter ADDR_BITS = $clog2(DEPTH),
    parameter THRESHOLD = (WIDTH - 1) / 4
) (
    input clk
);
endmodule
"""

    def test_expression_preserved_as_string(self):
        """Req 7.3: expression default values stored as-is."""
        claims = extract_module_parameters(
            self.RTL_EXPRESSION_PARAMS, "fifo_ctrl", "fifo_ctrl.sv", "tt_001"
        )
        depth_claim = next(
            c for c in claims if "DEPTH" in c["claim_text"]
            and "RDATA" not in c["claim_text"]
        )
        assert "WIDTH * 2" in depth_claim["claim_text"]

    def test_clog2_expression_preserved(self):
        """Req 7.3: $clog2() expression preserved."""
        claims = extract_module_parameters(
            self.RTL_EXPRESSION_PARAMS, "fifo_ctrl", "fifo_ctrl.sv", "tt_001"
        )
        addr_claim = next(
            c for c in claims if "ADDR_BITS" in c["claim_text"]
        )
        assert "$clog2(DEPTH)" in addr_claim["claim_text"]

    def test_nested_parens_expression_preserved(self):
        """Req 7.3: nested parenthesized expression preserved."""
        claims = extract_module_parameters(
            self.RTL_EXPRESSION_PARAMS, "fifo_ctrl", "fifo_ctrl.sv", "tt_001"
        )
        threshold_claim = next(
            c for c in claims if "THRESHOLD" in c["claim_text"]
        )
        assert "(WIDTH - 1) / 4" in threshold_claim["claim_text"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and robustness."""

    def test_module_not_found_returns_empty(self):
        """No match for module name returns empty list."""
        rtl = "module other_module (input clk); endmodule"
        claims = extract_module_parameters(rtl, "nonexistent", "f.sv", "p1")
        assert claims == []

    def test_module_without_parameters(self):
        """Module with no parameters returns empty list."""
        rtl = "module simple (input clk, output data); endmodule"
        claims = extract_module_parameters(rtl, "simple", "f.sv", "p1")
        assert claims == []

    def test_comments_stripped(self):
        """Comments don't interfere with extraction."""
        rtl = """\
module m #(
    // This is a comment
    parameter int X = 10, // inline comment
    /* block comment */ parameter int Y = 20
) (input clk);
endmodule
"""
        claims = extract_module_parameters(rtl, "m", "m.sv", "p1")
        names = [c["claim_text"].split("parameter ")[1].split(" = ")[0]
                 for c in claims]
        assert "X" in names
        assert "Y" in names

    def test_both_patterns_combined(self):
        """Header params and internal params both extracted."""
        rtl = """\
module combo #(
    parameter int HEADER_PARAM = 100
) (input clk);
    parameter int BODY_PARAM = 200;
endmodule
"""
        claims = extract_module_parameters(rtl, "combo", "combo.sv", "p1")
        names = [c["claim_text"].split("parameter ")[1].split(" = ")[0]
                 for c in claims]
        assert "HEADER_PARAM" in names
        assert "BODY_PARAM" in names

    def test_no_duplicate_params(self):
        """Same parameter name in header is not duplicated from body."""
        rtl = """\
module dedup #(
    parameter int SHARED = 42
) (input clk);
    parameter int SHARED = 99;
endmodule
"""
        claims = extract_module_parameters(rtl, "dedup", "dedup.sv", "p1")
        shared_claims = [c for c in claims if "SHARED" in c["claim_text"]]
        # First occurrence (header) wins
        assert len(shared_claims) == 1
        assert "42" in shared_claims[0]["claim_text"]

"""Unit tests for Top Module Parameter extraction — Task 5.4.

Validates Requirements 7.2, 7.3, 7.4:
- 7.2: Numeric values (AXI_SLV_OUTSTANDING_READS=64) extracted correctly
- 7.3: Expression default values preserved as-is (not evaluated)
- 7.4: Instantiation parameter override (#(.NUM_REPEATERS(4))) extraction

Tests both extract_module_parameters (package_extractor.py) and
_extract_instance_param_overrides (port_binding_parser.py).
"""

import os
import pytest

os.environ.setdefault("PARSER_PORT_BINDING_ENABLED", "true")

from package_extractor import extract_module_parameters
from port_binding_parser import _extract_instance_param_overrides


# ---------------------------------------------------------------------------
# Requirement 7.2: AXI_SLV_OUTSTANDING_READS = 64 extraction
# ---------------------------------------------------------------------------

class TestAXISLVOutstandingReads:
    """Verify AXI_SLV_OUTSTANDING_READS=64 is extracted with value '64'."""

    RTL = """\
module trinity_top #(
    parameter integer AXI_SLV_OUTSTANDING_READS = 64,
    parameter integer AXI_SLV_OUTSTANDING_WRITES = 32
) (
    input  wire clk,
    input  wire rst_n
);
endmodule
"""

    def test_value_is_64(self):
        """Req 7.2: AXI_SLV_OUTSTANDING_READS value is '64'."""
        claims = extract_module_parameters(
            self.RTL, "trinity_top", "trinity_top.sv", "pipe1"
        )
        reads_claim = next(
            c for c in claims if "AXI_SLV_OUTSTANDING_READS" in c["claim_text"]
        )
        assert "= 64" in reads_claim["claim_text"]

    def test_claim_topic(self):
        """Req 7.2: topic is TopLevelParameter."""
        claims = extract_module_parameters(
            self.RTL, "trinity_top", "trinity_top.sv", "pipe1"
        )
        reads_claim = next(
            c for c in claims if "AXI_SLV_OUTSTANDING_READS" in c["claim_text"]
        )
        assert reads_claim["topic"] == "TopLevelParameter"

    def test_claim_type_structural(self):
        """Req 7.2: claim_type is structural."""
        claims = extract_module_parameters(
            self.RTL, "trinity_top", "trinity_top.sv", "pipe1"
        )
        reads_claim = next(
            c for c in claims if "AXI_SLV_OUTSTANDING_READS" in c["claim_text"]
        )
        assert reads_claim["claim_type"] == "structural"

    def test_module_name_in_claim(self):
        """Req 7.2: module_name is set to trinity_top."""
        claims = extract_module_parameters(
            self.RTL, "trinity_top", "trinity_top.sv", "pipe1"
        )
        reads_claim = next(
            c for c in claims if "AXI_SLV_OUTSTANDING_READS" in c["claim_text"]
        )
        assert reads_claim["module_name"] == "trinity_top"


# ---------------------------------------------------------------------------
# Requirement 7.3: Expression default value preservation
# ---------------------------------------------------------------------------

class TestExpressionDefaultPreservation:
    """Verify expression defaults like DEPTH = WIDTH * 2 are preserved as-is."""

    RTL = """\
module fifo_ctrl #(
    parameter int WIDTH = 32,
    parameter DEPTH = WIDTH * 2,
    parameter ADDR_W = $clog2(DEPTH),
    parameter MAX_IDX = (NUM_ENTRIES - 1) * STRIDE + OFFSET
) (
    input clk
);
endmodule
"""

    def test_multiplication_expression_preserved(self):
        """Req 7.3: 'WIDTH * 2' is stored as string, not evaluated to 64."""
        claims = extract_module_parameters(
            self.RTL, "fifo_ctrl", "fifo_ctrl.sv", "pipe1"
        )
        depth_claim = next(
            c for c in claims if "DEPTH" in c["claim_text"]
            and "RDATA" not in c["claim_text"]
        )
        # Must contain the expression text, NOT evaluated value
        assert "WIDTH * 2" in depth_claim["claim_text"]
        # Should NOT contain "= 64" (the evaluated result)
        assert "= 64" not in depth_claim["claim_text"]

    def test_system_function_expression_preserved(self):
        """Req 7.3: $clog2(DEPTH) preserved as-is."""
        claims = extract_module_parameters(
            self.RTL, "fifo_ctrl", "fifo_ctrl.sv", "pipe1"
        )
        addr_claim = next(
            c for c in claims if "ADDR_W" in c["claim_text"]
        )
        assert "$clog2(DEPTH)" in addr_claim["claim_text"]

    def test_complex_expression_preserved(self):
        """Req 7.3: multi-operator expression preserved without evaluation."""
        claims = extract_module_parameters(
            self.RTL, "fifo_ctrl", "fifo_ctrl.sv", "pipe1"
        )
        max_claim = next(
            c for c in claims if "MAX_IDX" in c["claim_text"]
        )
        # The expression should be preserved (may have parentheses)
        assert "NUM_ENTRIES" in max_claim["claim_text"]
        assert "STRIDE" in max_claim["claim_text"]


# ---------------------------------------------------------------------------
# Requirement 7.4: Instantiation parameter override extraction
# ---------------------------------------------------------------------------

class TestInstantiationParamOverride:
    """Verify #(.NUM_REPEATERS(4)) instantiation override extraction."""

    def test_single_param_override(self):
        """Req 7.4: module_name #(.NUM_REPEATERS(4)) u_instance parsed."""
        instance_text = "noc_repeater #(.NUM_REPEATERS(4)) u_repeater (.clk(clk))"
        overrides = _extract_instance_param_overrides(instance_text)

        assert len(overrides) == 1
        assert overrides[0]["param_name"] == "NUM_REPEATERS"
        assert overrides[0]["override_value"] == "4"
        assert overrides[0]["instance_name"] == "u_repeater"
        assert overrides[0]["module_name"] == "noc_repeater"

    def test_multiple_param_overrides(self):
        """Req 7.4: multiple overrides extracted correctly."""
        instance_text = """\
axi_fifo #(
    .DEPTH(16),
    .WIDTH(64),
    .ALMOST_FULL_THRESH(12)
) u_axi_fifo (
    .clk(clk),
    .rst(rst)
)"""
        overrides = _extract_instance_param_overrides(instance_text)

        assert len(overrides) == 3
        params = {o["param_name"]: o["override_value"] for o in overrides}
        assert params["DEPTH"] == "16"
        assert params["WIDTH"] == "64"
        assert params["ALMOST_FULL_THRESH"] == "12"
        # All should reference same instance/module
        for o in overrides:
            assert o["instance_name"] == "u_axi_fifo"
            assert o["module_name"] == "axi_fifo"

    def test_expression_override_value(self):
        """Req 7.4: expression override values preserved as string."""
        instance_text = "router #(.BUFFER_SIZE(DEPTH * 2)) u_router (.clk(clk))"
        overrides = _extract_instance_param_overrides(instance_text)

        assert len(overrides) == 1
        assert overrides[0]["param_name"] == "BUFFER_SIZE"
        assert overrides[0]["override_value"] == "DEPTH * 2"

    def test_no_override_returns_empty(self):
        """Req 7.4: instantiation without #() returns empty list."""
        instance_text = "simple_mod u_simple (.clk(clk))"
        overrides = _extract_instance_param_overrides(instance_text)
        assert overrides == []

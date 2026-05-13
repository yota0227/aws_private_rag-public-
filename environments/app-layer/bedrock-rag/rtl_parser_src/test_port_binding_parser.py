"""Unit tests for port_binding_parser.py.

Tests port binding extraction from module instantiation statements,
including parameter/port block separation, concatenation, unconnected
ports, bit ranges, and duplicate detection.
"""
import os
import logging
import pytest

# Ensure feature flag is enabled for tests
os.environ.setdefault('PARSER_PORT_BINDING_ENABLED', 'true')

from port_binding_parser import (
    extract_port_bindings,
    classify_expression_type,
    _find_all_port_bindings,
    _find_instantiation_statements,
    _extract_port_bindings_from_block,
    _extract_instance_param_overrides,
    extract_instance_param_override_claims,
    _find_matching_paren,
    _strip_comments,
    PARSER_PORT_BINDING_ENABLED,
)


class TestBasicPortBindingExtraction:
    """Test basic .port(signal) extraction."""

    def test_simple_instantiation(self):
        """Single instance with named port connections."""
        rtl = """
        module top;
            my_module inst0 (
                .clk(sys_clk),
                .rst_n(reset_n),
                .data_in(input_data)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 3

        # Verify claim structure
        for claim in claims:
            assert claim["parser_source"] == "port_binding_parser"
            assert claim["analysis_type"] == "claim"
            assert claim["claim_type"] == "structural"
            assert claim["topic"] == "PortBinding"
            assert claim["file_path"] == "test.sv"
            assert claim["pipeline_id"] == "pipe1"
            assert claim["module_name"] == "top"

        # Verify claim texts
        texts = [c["claim_text"] for c in claims]
        assert "Instance 'inst0' of module 'my_module' binds port 'clk' to signal 'sys_clk'" in texts
        assert "Instance 'inst0' of module 'my_module' binds port 'rst_n' to signal 'reset_n'" in texts
        assert "Instance 'inst0' of module 'my_module' binds port 'data_in' to signal 'input_data'" in texts

    def test_multiple_instances(self):
        """Multiple instances in the same module."""
        rtl = """
        module top;
            mod_a u_a (
                .port_x(sig_x)
            );
            mod_b u_b (
                .port_y(sig_y)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 2
        texts = [c["claim_text"] for c in claims]
        assert any("u_a" in t and "mod_a" in t and "port_x" in t for t in texts)
        assert any("u_b" in t and "mod_b" in t and "port_y" in t for t in texts)

    def test_module_name_auto_detection(self):
        """Module name extracted from content when not provided."""
        rtl = """
        module auto_detected_mod;
            sub_mod inst (
                .a(b)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "", "test.sv", "pipe1")
        assert len(claims) == 1
        assert claims[0]["module_name"] == "auto_detected_mod"


class TestParameterBlockSeparation:
    """Test #(…) parameter block vs (…) port block separation."""

    def test_instance_with_parameters(self):
        """Instance with #(params) should only extract port bindings."""
        rtl = """
        module top;
            my_module #(
                .WIDTH(32),
                .DEPTH(16)
            ) inst0 (
                .clk(sys_clk),
                .data(bus_data)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        # Should only get port bindings, not parameter bindings
        assert len(claims) == 2
        texts = [c["claim_text"] for c in claims]
        assert any("'clk'" in t for t in texts)
        assert any("'data'" in t for t in texts)
        # Parameter bindings should NOT appear
        assert not any("WIDTH" in t for t in texts)
        assert not any("DEPTH" in t for t in texts)

    def test_nested_parens_in_parameters(self):
        """Parameters with nested parentheses (e.g., $clog2(N))."""
        rtl = """
        module top;
            fifo #(
                .ADDR_WIDTH($clog2(DEPTH)),
                .DATA_WIDTH(WIDTH * 2)
            ) u_fifo (
                .wr_data(data_in),
                .rd_data(data_out)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 2
        texts = [c["claim_text"] for c in claims]
        assert any("'wr_data'" in t for t in texts)
        assert any("'rd_data'" in t for t in texts)

    def test_instance_without_parameters(self):
        """Instance without #() block."""
        rtl = """
        module top;
            simple_mod u0 (
                .in(a),
                .out(b)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 2


class TestUnconnectedPorts:
    """Test .port() unconnected port detection."""

    def test_unconnected_port(self):
        """Empty signal expression means unconnected."""
        rtl = """
        module top;
            my_mod inst (
                .clk(sys_clk),
                .unused_out(),
                .data(bus)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 3

        # Find the unconnected port claim
        unconnected_claim = [c for c in claims if "unused_out" in c["claim_text"]]
        assert len(unconnected_claim) == 1
        assert "signal ''" in unconnected_claim[0]["claim_text"]

    def test_unconnected_binding_metadata(self):
        """Verify is_unconnected in raw bindings."""
        rtl = """
        my_mod inst (
            .connected(sig),
            .floating()
        );
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        connected = [b for b in bindings if b["port_name"] == "connected"]
        floating = [b for b in bindings if b["port_name"] == "floating"]
        assert len(connected) == 1
        assert connected[0]["is_unconnected"] is False
        assert len(floating) == 1
        assert floating[0]["is_unconnected"] is True


class TestConcatenationBindings:
    """Test .port({sig_a, sig_b}) concatenation handling."""

    def test_simple_concatenation(self):
        """Concatenation binding decomposed into constituent signals."""
        rtl = """
        module top;
            my_mod inst (
                .bus({data_hi, data_lo})
            );
        endmodule
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        b = bindings[0]
        assert b["port_name"] == "bus"
        assert b["signal_expr"] == "{data_hi, data_lo}"
        assert b["is_concatenation"] is True
        assert b["constituent_signals"] == ["data_hi", "data_lo"]

    def test_three_signal_concatenation(self):
        """Three signals in concatenation."""
        rtl = """
        my_mod inst (
            .wide_bus({a, b, c})
        );
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        assert bindings[0]["constituent_signals"] == ["a", "b", "c"]

    def test_concatenation_claim_text(self):
        """Claim text preserves full concatenation expression."""
        rtl = """
        module top;
            my_mod inst (
                .bus({sig_a, sig_b})
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 1
        assert "{sig_a, sig_b}" in claims[0]["claim_text"]


class TestBitRangeExtraction:
    """Test bit range extraction from signal expressions."""

    def test_bit_range_colon(self):
        """Signal with [N:M] bit range."""
        rtl = """
        my_mod inst (
            .data(bus[7:0])
        );
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        assert bindings[0]["bit_range"] == "[7:0]"

    def test_bit_select(self):
        """Signal with single bit select [N]."""
        rtl = """
        my_mod inst (
            .flag(status[3])
        );
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        assert bindings[0]["bit_range"] == "[3]"

    def test_no_bit_range(self):
        """Signal without bit range."""
        rtl = """
        my_mod inst (
            .clk(sys_clk)
        );
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        assert bindings[0]["bit_range"] is None


class TestDuplicatePortDetection:
    """Test duplicate port name handling within same instance."""

    def test_duplicate_port_first_wins(self, caplog):
        """First binding is kept, duplicate generates WARNING."""
        rtl = """
        module top;
            my_mod inst (
                .clk(clk_a),
                .clk(clk_b),
                .data(bus)
            );
        endmodule
        """
        with caplog.at_level(logging.WARNING):
            claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")

        # Only 2 claims: first .clk and .data
        assert len(claims) == 2
        texts = [c["claim_text"] for c in claims]
        assert any("'clk'" in t and "'clk_a'" in t for t in texts)
        assert any("'data'" in t for t in texts)
        # clk_b should NOT appear
        assert not any("clk_b" in t for t in texts)

        # WARNING should be logged
        assert any("Duplicate port binding" in r.message for r in caplog.records)


class TestFeatureFlag:
    """Test PARSER_PORT_BINDING_ENABLED feature flag."""

    def test_disabled_returns_empty(self, monkeypatch):
        """When feature flag is disabled, returns empty list."""
        monkeypatch.setattr(
            'port_binding_parser.PARSER_PORT_BINDING_ENABLED', False
        )
        rtl = """
        module top;
            my_mod inst (.clk(sys_clk));
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert claims == []


class TestCommentStripping:
    """Test that comments are properly stripped before parsing."""

    def test_single_line_comment(self):
        """Single-line comments should not interfere."""
        rtl = """
        module top;
            // This is a comment
            my_mod inst (
                .clk(sys_clk) // clock input
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 1

    def test_block_comment(self):
        """Block comments should not interfere."""
        rtl = """
        module top;
            /* multi-line
               comment */
            my_mod inst (
                .data(bus)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_content(self):
        """Empty content returns empty list."""
        claims = extract_port_bindings("", "top", "test.sv", "pipe1")
        assert claims == []

    def test_no_instantiations(self):
        """Content without instantiations returns empty list."""
        rtl = """
        module top;
            wire [7:0] data;
            assign data = 8'hFF;
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert claims == []

    def test_keyword_not_treated_as_module(self):
        """Keywords like 'assign', 'always' should not be parsed as modules."""
        rtl = """
        module top;
            assign out = in;
            always @(posedge clk) begin
                reg_val <= data;
            end
            real_mod inst (.a(b));
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 1
        assert "real_mod" in claims[0]["claim_text"]

    def test_complex_signal_expression(self):
        """Signal expressions with operators/function calls."""
        rtl = """
        my_mod inst (
            .data(sig_a & sig_b)
        );
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        assert bindings[0]["signal_expr"] == "sig_a & sig_b"
        assert bindings[0]["is_unconnected"] is False


class TestClaimFormat:
    """Test claim_text format matches specification."""

    def test_claim_text_format(self):
        """Claim text matches required format exactly."""
        rtl = """
        module top;
            tensix_core t0 (
                .i_noc_data(noc_data_bus)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 1
        expected = (
            "Instance 't0' of module 'tensix_core' "
            "binds port 'i_noc_data' to signal 'noc_data_bus'"
        )
        assert claims[0]["claim_text"] == expected

    def test_parser_source_field(self):
        """All claims have parser_source='port_binding_parser'."""
        rtl = """
        module top;
            mod_a u0 (.x(y));
            mod_b u1 (.a(b));
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        for claim in claims:
            assert claim["parser_source"] == "port_binding_parser"


class TestRealisticRTL:
    """Test with realistic RTL patterns from semiconductor designs."""

    def test_tensix_instantiation(self):
        """Realistic tensix core instantiation with parameters."""
        rtl = """
        module trinity #(
            parameter SizeX = 4,
            parameter SizeY = 5
        ) (
            input wire clk,
            input wire rst_n
        );

            tensix_core #(
                .EP_ID(6),
                .NOC_WIDTH(64)
            ) t6 (
                .i_clk(clk),
                .i_rst_n(rst_n),
                .i_noc_data(noc_data_in[6]),
                .o_noc_data(noc_data_out[6]),
                .i_config()
            );

        endmodule
        """
        claims = extract_port_bindings(rtl, "trinity", "trinity.sv", "pipe1")
        # Should extract 5 port bindings from t6 instance
        assert len(claims) == 5
        texts = [c["claim_text"] for c in claims]
        assert any("'i_clk'" in t and "'clk'" in t for t in texts)
        assert any("'i_rst_n'" in t and "'rst_n'" in t for t in texts)
        assert any("'i_noc_data'" in t and "'noc_data_in[6]'" in t for t in texts)
        assert any("'o_noc_data'" in t and "'noc_data_out[6]'" in t for t in texts)
        assert any("'i_config'" in t and "signal ''" in t for t in texts)

    def test_noc2axi_with_concatenation(self):
        """NOC2AXI instance with concatenation port binding."""
        rtl = """
        module top;
            noc2axi_bridge #(
                .AXI_WIDTH(128)
            ) u_bridge (
                .i_clk(sys_clk),
                .i_data({upper_data, lower_data}),
                .o_axi_valid(axi_valid)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 3
        texts = [c["claim_text"] for c in claims]
        assert any("{upper_data, lower_data}" in t for t in texts)


class TestExpressionPreserverClassification:
    """Test ExpressionPreserver: expression_type classification logic.

    Classification rules:
    - Empty string → 'simple' (unconnected port)
    - Starts with '{' → 'concatenation'
    - Contains +, -, *, / operators → 'arithmetic'
    - Otherwise → 'simple'
    """

    def test_empty_string_is_simple(self):
        """Empty signal expression (unconnected port) classified as simple."""
        assert classify_expression_type("") is not None
        assert classify_expression_type("") == "simple"

    def test_simple_identifier(self):
        """Plain signal name classified as simple."""
        assert classify_expression_type("sys_clk") == "simple"
        assert classify_expression_type("data_in") == "simple"
        assert classify_expression_type("noc_data_bus") == "simple"

    def test_bit_select_is_simple(self):
        """Bit select without arithmetic is simple."""
        assert classify_expression_type("bus[7:0]") == "simple"
        assert classify_expression_type("data[3]") == "simple"

    def test_concatenation_starts_with_brace(self):
        """Expression starting with '{' classified as concatenation."""
        assert classify_expression_type("{data_hi, data_lo}") == "concatenation"
        assert classify_expression_type("{a, b, c}") == "concatenation"
        assert classify_expression_type("{32'h0, data}") == "concatenation"

    def test_arithmetic_plus(self):
        """Expression with + operator classified as arithmetic."""
        assert classify_expression_type("addr + 1") == "arithmetic"
        assert classify_expression_type("base_addr + offset") == "arithmetic"

    def test_arithmetic_minus(self):
        """Expression with - operator classified as arithmetic."""
        assert classify_expression_type("i_local_nodeid_y - 1") == "arithmetic"
        assert classify_expression_type("SizeX - 1") == "arithmetic"

    def test_arithmetic_multiply(self):
        """Expression with * operator classified as arithmetic."""
        assert classify_expression_type("WIDTH * 2") == "arithmetic"
        assert classify_expression_type("(SizeX - 1) * 2") == "arithmetic"

    def test_arithmetic_divide(self):
        """Expression with / operator classified as arithmetic."""
        assert classify_expression_type("DEPTH / 4") == "arithmetic"

    def test_nested_parenthesized_expression(self):
        """Nested parenthesized arithmetic classified as arithmetic."""
        assert classify_expression_type("(SizeX - 1) * 2") == "arithmetic"
        assert classify_expression_type("(a + b) * (c - d)") == "arithmetic"


class TestExpressionPreserverPreservation:
    """Test ExpressionPreserver: signal_expr preserves full expressions.

    Validates Requirements 5.1, 5.2, 5.4:
    - Arithmetic expressions preserved as-is in signal_expr
    - Nested parenthesized expressions preserved without simplification
    """

    def test_arithmetic_minus_one_preserved(self):
        """Expression 'i_local_nodeid_y - 1' preserved in signal_expr."""
        rtl = """
        module top;
            my_mod inst (
                .i_local_nodeid_y(i_local_nodeid_y - 1)
            );
        endmodule
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        assert bindings[0]["signal_expr"] == "i_local_nodeid_y - 1"
        assert bindings[0]["expression_type"] == "arithmetic"

    def test_nested_parenthesized_expression_preserved(self):
        """Expression '(SizeX - 1) * 2' preserved without simplification."""
        rtl = """
        module top;
            my_mod inst (
                .width_param((SizeX - 1) * 2)
            );
        endmodule
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        assert bindings[0]["signal_expr"] == "(SizeX - 1) * 2"
        assert bindings[0]["expression_type"] == "arithmetic"

    def test_addition_expression_preserved(self):
        """Expression 'base_addr + 4' preserved in signal_expr."""
        rtl = """
        module top;
            my_mod inst (
                .addr(base_addr + 4)
            );
        endmodule
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        assert bindings[0]["signal_expr"] == "base_addr + 4"
        assert bindings[0]["expression_type"] == "arithmetic"

    def test_complex_nested_expression_preserved(self):
        """Complex nested expression preserved without simplification."""
        rtl = """
        module top;
            my_mod inst (
                .idx((row_idx + 1) * col_count - offset)
            );
        endmodule
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        assert bindings[0]["signal_expr"] == "(row_idx + 1) * col_count - offset"
        assert bindings[0]["expression_type"] == "arithmetic"

    def test_division_expression_preserved(self):
        """Expression with division preserved."""
        rtl = """
        module top;
            my_mod inst (
                .half_width(FULL_WIDTH / 2)
            );
        endmodule
        """
        clean = _strip_comments(rtl)
        bindings = _find_all_port_bindings(clean, "test.sv")
        assert len(bindings) == 1
        assert bindings[0]["signal_expr"] == "FULL_WIDTH / 2"
        assert bindings[0]["expression_type"] == "arithmetic"


class TestExpressionPreserverClaimText:
    """Test ExpressionPreserver: claim_text includes full expression.

    Validates Requirement 5.3:
    - Claim text includes arithmetic expression
    - e.g., "binds port 'i_local_nodeid_y' to signal 'i_local_nodeid_y - 1'"
    """

    def test_claim_text_includes_arithmetic_expression(self):
        """Claim text includes the full arithmetic expression."""
        rtl = """
        module top;
            tensix_core t0 (
                .i_local_nodeid_y(i_local_nodeid_y - 1)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 1
        expected = (
            "Instance 't0' of module 'tensix_core' "
            "binds port 'i_local_nodeid_y' to signal 'i_local_nodeid_y - 1'"
        )
        assert claims[0]["claim_text"] == expected
        assert claims[0]["expression_type"] == "arithmetic"

    def test_claim_text_includes_nested_expression(self):
        """Claim text includes nested parenthesized expression."""
        rtl = """
        module top;
            grid_mod g0 (
                .col_end((SizeX - 1) * 2)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 1
        expected = (
            "Instance 'g0' of module 'grid_mod' "
            "binds port 'col_end' to signal '(SizeX - 1) * 2'"
        )
        assert claims[0]["claim_text"] == expected
        assert claims[0]["expression_type"] == "arithmetic"

    def test_claim_text_simple_expression(self):
        """Claim text for simple signal has expression_type 'simple'."""
        rtl = """
        module top;
            my_mod inst (
                .clk(sys_clk)
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 1
        assert claims[0]["expression_type"] == "simple"

    def test_claim_text_concatenation_expression(self):
        """Claim text for concatenation has expression_type 'concatenation'."""
        rtl = """
        module top;
            my_mod inst (
                .bus({data_hi, data_lo})
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 1
        assert claims[0]["expression_type"] == "concatenation"
        assert "{data_hi, data_lo}" in claims[0]["claim_text"]

    def test_expression_type_field_present_in_all_claims(self):
        """All claims have expression_type field."""
        rtl = """
        module top;
            my_mod inst (
                .clk(sys_clk),
                .data(addr + 1),
                .bus({a, b}),
                .unused()
            );
        endmodule
        """
        claims = extract_port_bindings(rtl, "top", "test.sv", "pipe1")
        assert len(claims) == 4
        for claim in claims:
            assert "expression_type" in claim
            assert claim["expression_type"] in ("simple", "arithmetic", "concatenation")


class TestInstanceParamOverrideExtraction:
    """Test _extract_instance_param_overrides function.

    Validates extraction of #(.PARAM_NAME(value)) patterns from
    module instantiation statements.
    Requirements: 7.2 (extended)
    """

    def test_single_param_override(self):
        """Extract single parameter override from instantiation."""
        instance_text = "repeater_mod #(.NUM_REPEATERS(4)) u_repeater"
        overrides = _extract_instance_param_overrides(instance_text)
        assert len(overrides) == 1
        assert overrides[0]["param_name"] == "NUM_REPEATERS"
        assert overrides[0]["override_value"] == "4"
        assert overrides[0]["instance_name"] == "u_repeater"
        assert overrides[0]["module_name"] == "repeater_mod"

    def test_multiple_param_overrides(self):
        """Extract multiple parameter overrides."""
        instance_text = """fifo_mod #(
            .WIDTH(32),
            .DEPTH(16),
            .ALMOST_FULL(12)
        ) u_fifo"""
        overrides = _extract_instance_param_overrides(instance_text)
        assert len(overrides) == 3
        assert overrides[0]["param_name"] == "WIDTH"
        assert overrides[0]["override_value"] == "32"
        assert overrides[1]["param_name"] == "DEPTH"
        assert overrides[1]["override_value"] == "16"
        assert overrides[2]["param_name"] == "ALMOST_FULL"
        assert overrides[2]["override_value"] == "12"
        # All share same instance and module
        for o in overrides:
            assert o["instance_name"] == "u_fifo"
            assert o["module_name"] == "fifo_mod"

    def test_expression_value_preserved(self):
        """Expression values like $clog2(DEPTH) preserved as string."""
        instance_text = "fifo #(.ADDR_WIDTH($clog2(DEPTH))) u_fifo"
        overrides = _extract_instance_param_overrides(instance_text)
        assert len(overrides) == 1
        assert overrides[0]["param_name"] == "ADDR_WIDTH"
        assert overrides[0]["override_value"] == "$clog2(DEPTH)"

    def test_arithmetic_expression_value(self):
        """Arithmetic expression values preserved."""
        instance_text = "mod_a #(.DATA_WIDTH(WIDTH * 2)) u_a"
        overrides = _extract_instance_param_overrides(instance_text)
        assert len(overrides) == 1
        assert overrides[0]["param_name"] == "DATA_WIDTH"
        assert overrides[0]["override_value"] == "WIDTH * 2"

    def test_no_param_block_returns_empty(self):
        """Instance without #() returns empty list."""
        instance_text = "simple_mod u_simple"
        overrides = _extract_instance_param_overrides(instance_text)
        assert overrides == []

    def test_empty_input_returns_empty(self):
        """Empty string returns empty list."""
        overrides = _extract_instance_param_overrides("")
        assert overrides == []

    def test_keyword_module_name_returns_empty(self):
        """Keyword as module name returns empty list."""
        instance_text = "assign #(.X(1)) u_x"
        overrides = _extract_instance_param_overrides(instance_text)
        assert overrides == []

    def test_nested_parentheses_in_value(self):
        """Nested parentheses in parameter value handled correctly."""
        instance_text = "mod #(.SIZE((A + B) * C)) u_inst"
        overrides = _extract_instance_param_overrides(instance_text)
        assert len(overrides) == 1
        assert overrides[0]["param_name"] == "SIZE"
        assert overrides[0]["override_value"] == "(A + B) * C"


class TestInstanceParamOverrideClaims:
    """Test extract_instance_param_override_claims function.

    Validates claim generation for instantiation parameter overrides.
    Requirements: 7.2 (extended)
    """

    def test_basic_claim_generation(self):
        """Generate InstanceParameter claims from RTL with param overrides."""
        rtl = """
        module top;
            repeater_mod #(
                .NUM_REPEATERS(4)
            ) u_repeater (
                .clk(sys_clk),
                .data(bus)
            );
        endmodule
        """
        claims = extract_instance_param_override_claims(
            rtl, "top", "test.sv", "pipe1"
        )
        assert len(claims) == 1
        claim = claims[0]
        assert claim["topic"] == "InstanceParameter"
        assert claim["claim_type"] == "structural"
        assert claim["parser_source"] == "port_binding_parser"
        assert "Instance 'u_repeater' overrides NUM_REPEATERS=4" == claim["claim_text"]

    def test_multiple_overrides_multiple_claims(self):
        """Multiple param overrides generate multiple claims."""
        rtl = """
        module top;
            fifo #(
                .WIDTH(32),
                .DEPTH(16)
            ) u_fifo (
                .wr_data(data_in)
            );
        endmodule
        """
        claims = extract_instance_param_override_claims(
            rtl, "top", "test.sv", "pipe1"
        )
        assert len(claims) == 2
        texts = [c["claim_text"] for c in claims]
        assert "Instance 'u_fifo' overrides WIDTH=32" in texts
        assert "Instance 'u_fifo' overrides DEPTH=16" in texts

    def test_instance_without_params_no_claims(self):
        """Instance without #() generates no InstanceParameter claims."""
        rtl = """
        module top;
            simple_mod u_simple (
                .clk(sys_clk)
            );
        endmodule
        """
        claims = extract_instance_param_override_claims(
            rtl, "top", "test.sv", "pipe1"
        )
        assert claims == []

    def test_multiple_instances_mixed(self):
        """Mix of instances with and without param overrides."""
        rtl = """
        module top;
            mod_a #(.SIZE(8)) u_a (
                .clk(clk)
            );
            mod_b u_b (
                .clk(clk)
            );
            mod_c #(.DEPTH(4), .WIDTH(64)) u_c (
                .data(bus)
            );
        endmodule
        """
        claims = extract_instance_param_override_claims(
            rtl, "top", "test.sv", "pipe1"
        )
        assert len(claims) == 3
        texts = [c["claim_text"] for c in claims]
        assert "Instance 'u_a' overrides SIZE=8" in texts
        assert "Instance 'u_c' overrides DEPTH=4" in texts
        assert "Instance 'u_c' overrides WIDTH=64" in texts

    def test_empty_content_returns_empty(self):
        """Empty RTL content returns empty list."""
        claims = extract_instance_param_override_claims(
            "", "top", "test.sv", "pipe1"
        )
        assert claims == []

    def test_claim_text_format_matches_spec(self):
        """Claim text matches spec: Instance 'u_repeater' overrides NUM_REPEATERS=4."""
        rtl = """
        module top;
            repeater_mod #(.NUM_REPEATERS(4)) u_repeater (
                .clk(clk)
            );
        endmodule
        """
        claims = extract_instance_param_override_claims(
            rtl, "top", "test.sv", "pipe1"
        )
        assert len(claims) == 1
        expected = "Instance 'u_repeater' overrides NUM_REPEATERS=4"
        assert claims[0]["claim_text"] == expected

    def test_expression_value_in_claim(self):
        """Expression override values preserved in claim text."""
        rtl = """
        module top;
            fifo #(.ADDR_WIDTH($clog2(DEPTH))) u_fifo (
                .wr_data(data)
            );
        endmodule
        """
        claims = extract_instance_param_override_claims(
            rtl, "top", "test.sv", "pipe1"
        )
        assert len(claims) == 1
        assert "ADDR_WIDTH=$clog2(DEPTH)" in claims[0]["claim_text"]

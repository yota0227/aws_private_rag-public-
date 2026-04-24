"""Unit tests for port bit-width extraction in parse_rtl_to_ast()."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from handler import parse_rtl_to_ast


class TestPortBitWidthExtraction:
    def test_simple_bitwidth(self):
        rtl = "module foo; input [7:0] data; endmodule"
        result = parse_rtl_to_ast(rtl)
        assert "input [7:0] data" in result["port_list"]

    def test_param_based_bitwidth(self):
        rtl = "module foo; input [SizeX-1:0] i_ai_clk; endmodule"
        result = parse_rtl_to_ast(rtl)
        assert "input [SizeX-1:0] i_ai_clk" in result["port_list"]

    def test_no_bitwidth(self):
        rtl = "module foo; input clk; endmodule"
        result = parse_rtl_to_ast(rtl)
        assert "input clk" in result["port_list"]

    def test_output_with_logic(self):
        rtl = "module foo; output logic [15:0] result; endmodule"
        result = parse_rtl_to_ast(rtl)
        assert any("[15:0] result" in p for p in result["port_list"])

    def test_multidim_array(self):
        rtl = "module foo; input [3:0][7:0] data; endmodule"
        result = parse_rtl_to_ast(rtl)
        assert any("[3:0][7:0] data" in p or "[3:0] [7:0] data" in p for p in result["port_list"])

    def test_mixed_ports(self):
        rtl = """
        module trinity;
            input [SizeX-1:0] i_ai_clk;
            input i_noc_clk;
            output [NumTensix-1:0] o_tensix_done;
        endmodule
        """
        result = parse_rtl_to_ast(rtl)
        assert any("[SizeX-1:0] i_ai_clk" in p for p in result["port_list"])
        assert "input i_noc_clk" in result["port_list"]
        assert any("[NumTensix-1:0] o_tensix_done" in p for p in result["port_list"])

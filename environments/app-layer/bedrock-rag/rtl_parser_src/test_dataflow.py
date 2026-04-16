"""Tests for dataflow module — port mapping extraction, width mismatch, connections."""

from dataflow import (
    build_dataflow_connections,
    detect_width_mismatch,
    extract_port_mappings,
)


# ---------------------------------------------------------------------------
# extract_port_mappings
# ---------------------------------------------------------------------------

class TestExtractPortMappings:
    """Tests for extract_port_mappings."""

    def test_empty_string(self):
        assert extract_port_mappings("") == []

    def test_none_input(self):
        assert extract_port_mappings(None) == []

    def test_no_instantiation(self):
        rtl = "module top; wire a; endmodule"
        assert extract_port_mappings(rtl) == []

    def test_single_port_mapping(self):
        rtl = "tt_noc_router u_router (.i_clk(clk_sig));"
        result = extract_port_mappings(rtl)
        assert len(result) == 1
        assert result[0]["module_name"] == "tt_noc_router"
        assert result[0]["instance_name"] == "u_router"
        assert result[0]["child_port"] == "i_clk"
        assert result[0]["parent_signal"] == "clk_sig"
        assert result[0]["bit_width"] is None

    def test_multiple_port_mappings(self):
        rtl = """
        tt_dispatch_engine u_engine (
            .i_data(data_in),
            .o_result(result_out),
            .i_clk(sys_clk)
        );
        """
        result = extract_port_mappings(rtl)
        assert len(result) == 3
        ports = {r["child_port"] for r in result}
        assert ports == {"i_data", "o_result", "i_clk"}

    def test_bit_width_extraction(self):
        rtl = "tt_fpu u_fpu (.i_data(data_bus[31:0]));"
        result = extract_port_mappings(rtl)
        assert len(result) == 1
        assert result[0]["bit_width"] == 32
        assert result[0]["parent_signal"] == "data_bus"

    def test_bit_width_non_zero_lsb(self):
        rtl = "tt_edc u_edc (.i_addr(addr_bus[15:8]));"
        result = extract_port_mappings(rtl)
        assert len(result) == 1
        assert result[0]["bit_width"] == 8

    def test_no_bit_width(self):
        rtl = "tt_sfpu u_sfpu (.i_valid(valid_sig));"
        result = extract_port_mappings(rtl)
        assert len(result) == 1
        assert result[0]["bit_width"] is None

    def test_with_parameters(self):
        rtl = "tt_overlay #(.WIDTH(8)) u_ov (.i_data(d_in));"
        result = extract_port_mappings(rtl)
        assert len(result) == 1
        assert result[0]["module_name"] == "tt_overlay"
        assert result[0]["child_port"] == "i_data"

    def test_multiple_instances(self):
        rtl = """
        tt_noc_router u_north (.i_data(north_data));
        tt_noc_router u_south (.i_data(south_data));
        """
        result = extract_port_mappings(rtl)
        assert len(result) == 2
        instances = {r["instance_name"] for r in result}
        assert instances == {"u_north", "u_south"}

    def test_integer_input(self):
        assert extract_port_mappings(123) == []


# ---------------------------------------------------------------------------
# detect_width_mismatch
# ---------------------------------------------------------------------------

class TestDetectWidthMismatch:
    """Tests for detect_width_mismatch."""

    def test_matching_widths(self):
        assert detect_width_mismatch(32, 32) is False

    def test_mismatching_widths(self):
        assert detect_width_mismatch(32, 16) is True

    def test_one_bit(self):
        assert detect_width_mismatch(1, 1) is False

    def test_invalid_types(self):
        assert detect_width_mismatch("32", 32) is False


# ---------------------------------------------------------------------------
# build_dataflow_connections
# ---------------------------------------------------------------------------

class TestBuildDataflowConnections:
    """Tests for build_dataflow_connections."""

    def test_empty_string(self):
        assert build_dataflow_connections("") == []

    def test_none_input(self):
        assert build_dataflow_connections(None) == []

    def test_input_direction(self):
        rtl = "tt_fpu u_fpu (.i_data(data_in));"
        result = build_dataflow_connections(rtl)
        assert len(result) == 1
        assert result[0]["direction"] == "input"
        assert result[0]["child_module"] == "tt_fpu"

    def test_output_direction(self):
        rtl = "tt_fpu u_fpu (.o_result(result_out));"
        result = build_dataflow_connections(rtl)
        assert len(result) == 1
        assert result[0]["direction"] == "output"

    def test_unknown_direction(self):
        rtl = "tt_fpu u_fpu (.clk(sys_clk));"
        result = build_dataflow_connections(rtl)
        assert len(result) == 1
        assert result[0]["direction"] == "unknown"

    def test_connection_fields(self):
        rtl = "tt_edc u_edc (.i_addr(addr_bus[7:0]));"
        result = build_dataflow_connections(rtl)
        assert len(result) == 1
        conn = result[0]
        assert conn["parent_signal"] == "addr_bus"
        assert conn["child_module"] == "tt_edc"
        assert conn["child_port"] == "i_addr"
        assert conn["bit_width"] == 8
        assert conn["width_mismatch"] is False

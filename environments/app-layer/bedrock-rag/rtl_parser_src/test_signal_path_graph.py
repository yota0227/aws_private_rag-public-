"""Unit tests for signal_path_graph.py."""
import logging

import signal_path_graph
from signal_path_graph import (
    extract_signal_path_edges,
    filter_edges_by_category,
    render_signal_path_markdown,
)


def _edges_by_type(edges, edge_type):
    return [edge for edge in edges if edge["edge_type"] == edge_type]


class TestSignalPathGraphExtraction:
    def test_router_clock_port_binding_preserves_indexed_signal_path(self):
        rtl = """
        module top;
            for (genvar x = 0; x < SizeX; x++) begin : gen_x
                for (genvar y = 0; y < SizeY; y++) begin : gen_y
                    trinity_noc2axi_router_ne_opt u_router_ne (
                        .router_o_ai_clk(clock_routing_out[x][y-1].ai_clk),
                        .router_i_ai_clk(clock_routing_in[x][y].ai_clk)
                    );
                end
            end
        endmodule
        """

        edges = extract_signal_path_edges(rtl, "top", "n1b0.sv", "v9.5")
        port_edges = _edges_by_type(edges, "PORT_CONNECTS_TO")

        clock_edge = next(
            edge for edge in port_edges
            if edge["port_name"] == "router_o_ai_clk"
        )
        assert clock_edge["dst"] == "clock_routing_out[x][y-1].ai_clk"
        assert clock_edge["category"] == "clock"
        assert clock_edge["instance_module_type"] == "trinity_noc2axi_router_ne_opt"
        assert clock_edge["generate_context"]
        assert {ctx["variable"] for ctx in clock_edge["generate_context"]} == {"x", "y"}

    def test_assign_edge_tracks_rhs_to_lhs_direction(self):
        rtl = """
        module top;
            for (genvar x = 0; x < SizeX; x++) begin : gen_x
                for (genvar y = 0; y < SizeY; y++) begin : gen_y
                    assign clock_routing_in[x][y] = clock_routing_out[x][y+1];
                end
            end
        endmodule
        """

        edges = extract_signal_path_edges(rtl, "top", "n1b0.sv", "v9.5")
        assign_edges = _edges_by_type(edges, "ASSIGNS_TO")

        assert len(assign_edges) == 1
        edge = assign_edges[0]
        assert edge["src"] == "clock_routing_out[x][y+1]"
        assert edge["dst"] == "clock_routing_in[x][y]"
        assert edge["category"] == "clock"
        assert "clock_routing_out" in edge["rhs_signals"]

    def test_dispatch_binding_is_classified_as_dispatch_path(self):
        rtl = """
        module top;
            trinity_dispatch_bridge u_dispatch (
                .o_de_west_to_t6_south(de_to_t6_coloumn[x][y-1][1]),
                .i_t6_south_to_de_west(t6_to_de_coloumn[x][y][0])
            );
        endmodule
        """

        edges = extract_signal_path_edges(rtl, "top", "dispatch.sv", "v9.5")
        dispatch_edges = filter_edges_by_category(edges, "dispatch")

        assert len(dispatch_edges) == 2
        assert any(
            edge["dst"] == "de_to_t6_coloumn[x][y-1][1]"
            for edge in dispatch_edges
        )

    def test_edc_assign_is_classified_as_edc_path(self):
        rtl = """
        module top;
            assign router_edc_ingress_intf.req_tgl =
                   noc2axi_edc_egress_intf.req_tgl;
        endmodule
        """

        edges = extract_signal_path_edges(rtl, "top", "edc.sv", "v9.5")
        edc_edges = filter_edges_by_category(edges, "edc")

        assert len(edc_edges) == 1
        assert edc_edges[0]["src"] == "noc2axi_edc_egress_intf.req_tgl"
        assert edc_edges[0]["dst"] == "router_edc_ingress_intf.req_tgl"

    def test_wire_declaration_edge_captures_typed_array_dimensions(self):
        rtl = """
        module top;
            trinity_pkg::trinity_clock_routing_t clock_routing_in[SizeX][SizeY];
        endmodule
        """

        edges = extract_signal_path_edges(rtl, "top", "wires.sv", "v9.5")
        declaration_edges = _edges_by_type(edges, "DECLARES_SIGNAL")

        assert len(declaration_edges) == 1
        edge = declaration_edges[0]
        assert edge["dst"] == "clock_routing_in"
        assert edge["signal_type"] == "trinity_pkg::trinity_clock_routing_t"
        assert edge["dimensions"] == ["SizeX", "SizeY"]
        assert edge["category"] == "clock"

    def test_sfr_and_prtn_signals_do_not_fall_into_general_category(self):
        rtl = """
        module top;
            logic [31:0] SFR_RF_2P_HSC_QNAPA;
            wire PRTNUN_FC2UN_DATA_IN;
            wire ISO_EN;
            assign SFR_RF_2P_HSC_QNAPA = sfr_ra1_cfg_data;
        endmodule
        """

        edges = extract_signal_path_edges(rtl, "top", "sfr_prtn.sv", "v9.5")
        sfr_edges = filter_edges_by_category(edges, "sfr")
        prtn_edges = filter_edges_by_category(edges, "prtn")

        assert any(edge["dst"] == "SFR_RF_2P_HSC_QNAPA" for edge in sfr_edges)
        assert any(edge["src"] == "sfr_ra1_cfg_data" for edge in sfr_edges)
        assert any(edge["dst"] == "PRTNUN_FC2UN_DATA_IN" for edge in prtn_edges)
        assert any(edge["dst"] == "ISO_EN" for edge in prtn_edges)

    def test_scalar_wire_declarations_are_extracted(self):
        rtl = """
        module top;
            logic clk_i;
            wire i_reset_n;
            logic [31:0] status_word;
            trinity_pkg::sfr_config_t sfr_cfg;
        endmodule
        """

        edges = extract_signal_path_edges(rtl, "top", "scalar.sv", "v9.5")
        declarations = _edges_by_type(edges, "DECLARES_SIGNAL")
        by_name = {edge["dst"]: edge for edge in declarations}

        assert by_name["clk_i"]["signal_type"] == "scalar"
        assert by_name["clk_i"]["dimensions"] == []
        assert by_name["i_reset_n"]["signal_type"] == "scalar"
        assert by_name["status_word"]["signal_type"] == "packed"
        assert by_name["status_word"]["bit_range"] == "31:0"
        assert by_name["sfr_cfg"]["signal_type"] == "trinity_pkg::sfr_config_t"

    def test_missing_port_binding_parser_logs_warning(
        self, monkeypatch, caplog
    ):
        rtl = """
        module top;
            child u_child (
                .clk(clk_i)
            );
        endmodule
        """
        monkeypatch.setattr(signal_path_graph, "_find_all_port_bindings", None)
        caplog.set_level(logging.WARNING, logger="signal_path_graph")

        edges = extract_signal_path_edges(rtl, "top", "missing_port.sv", "v9.5")

        assert _edges_by_type(edges, "PORT_CONNECTS_TO") == []
        assert "PORT_CONNECTS_TO edges will not be extracted" in caplog.text

    def test_markdown_renderer_outputs_edge_evidence(self):
        rtl = """
        module top;
            assign router_edc_ingress_intf.req_tgl =
                   noc2axi_edc_egress_intf.req_tgl;
        endmodule
        """

        edges = extract_signal_path_edges(rtl, "top", "edc.sv", "v9.5")
        markdown = render_signal_path_markdown(edges)

        assert "# Signal Path Graph Evidence" in markdown
        assert "`ASSIGNS_TO`" in markdown
        assert "noc2axi_edc_egress_intf.req_tgl" in markdown

"""
Tests for edc_analyzer.py — EDC topology, harvest bypass, serial bus, node ID.
"""

import pytest
from edc_analyzer import (
    build_edc_topology,
    identify_harvest_bypass,
    extract_serial_bus_interface,
    build_node_id_table,
)


class TestBuildEdcTopology:
    def test_empty_input(self):
        result = build_edc_topology([])
        assert result["nodes"] == []
        assert result["segment_a"] == []
        assert result["u_turn"] == ""
        assert result["segment_b"] == []

    def test_none_input(self):
        result = build_edc_topology(None)
        assert result["nodes"] == []

    def test_single_edc_module(self):
        modules = [{"module_name": "tt_edc1_node", "instance_list": ""}]
        result = build_edc_topology(modules)
        assert "tt_edc1_node" in result["nodes"]

    def test_multiple_edc_modules_sorted(self):
        modules = [
            {"module_name": "tt_edc1_node_b", "instance_list": ""},
            {"module_name": "tt_edc1_node_a", "instance_list": ""},
            {"module_name": "tt_edc1_node_c", "instance_list": ""},
        ]
        result = build_edc_topology(modules)
        assert result["nodes"] == ["tt_edc1_node_a", "tt_edc1_node_b", "tt_edc1_node_c"]

    def test_connections_from_instance_list(self):
        modules = [
            {"module_name": "tt_edc1_top", "instance_list": "u_node: tt_edc1_node"},
            {"module_name": "tt_edc1_node", "instance_list": ""},
        ]
        result = build_edc_topology(modules)
        assert len(result["connections"]) == 1
        assert result["connections"][0]["from"] == "tt_edc1_top"
        assert result["connections"][0]["to"] == "tt_edc1_node"

    def test_non_edc_modules_ignored(self):
        modules = [
            {"module_name": "tt_noc_router", "instance_list": ""},
            {"module_name": "tt_edc1_node", "instance_list": ""},
        ]
        result = build_edc_topology(modules)
        assert "tt_noc_router" not in result["nodes"]
        assert "tt_edc1_node" in result["nodes"]


class TestIdentifyHarvestBypass:
    def test_empty_input(self):
        result = identify_harvest_bypass([])
        assert result == []

    def test_none_input(self):
        result = identify_harvest_bypass(None)
        assert result == []

    def test_mux_bypass_detected(self):
        modules = [
            {"module_name": "tt_edc1_top",
             "instance_list": "u_mux: tt_edc1_serial_bus_mux"},
        ]
        result = identify_harvest_bypass(modules)
        assert len(result) == 1
        assert result[0]["type"] == "mux_bypass"
        assert result[0]["from"] == "tt_edc1_top"

    def test_demux_bypass_detected(self):
        modules = [
            {"module_name": "tt_edc1_ring",
             "instance_list": "u_demux: tt_edc1_serial_bus_demux"},
        ]
        result = identify_harvest_bypass(modules)
        assert len(result) == 1
        assert result[0]["type"] == "demux_bypass"

    def test_no_bypass_in_regular_modules(self):
        modules = [
            {"module_name": "tt_edc1_node", "instance_list": "u_reg: tt_edc1_reg"},
        ]
        result = identify_harvest_bypass(modules)
        assert result == []


class TestExtractSerialBusInterface:
    def test_empty_input(self):
        result = extract_serial_bus_interface("")
        assert result["signals"] == []

    def test_none_input(self):
        result = extract_serial_bus_interface(None)
        assert result["signals"] == []

    def test_finds_known_signals(self):
        content = """
        logic req_tgl;
        logic ack_tgl;
        logic [7:0] data;
        logic data_p;
        logic async_init;
        """
        result = extract_serial_bus_interface(content)
        assert "req_tgl" in result["signals"]
        assert "ack_tgl" in result["signals"]
        assert "data" in result["signals"]
        assert "async_init" in result["signals"]

    def test_keyword_search_fallback(self):
        content = "// The req_tgl signal is used for handshaking"
        result = extract_serial_bus_interface(content)
        assert "req_tgl" in result["signals"]


class TestBuildNodeIdTable:
    def test_empty_input(self):
        result = build_node_id_table([])
        assert result == []

    def test_none_input(self):
        result = build_node_id_table(None)
        assert result == []

    def test_extracts_node_id_fields(self):
        modules = [
            {"module_name": "edc_node_0",
             "parameter_list": "node_id_part=0, node_id_subp=1, node_id_inst=2"},
        ]
        result = build_node_id_table(modules)
        assert len(result) == 1
        assert result[0]["node"] == "edc_node_0"
        assert result[0]["part"] == 0
        assert result[0]["subp"] == 1
        assert result[0]["inst"] == 2

    def test_partial_node_id(self):
        modules = [
            {"module_name": "edc_node_1",
             "parameter_list": "node_id_part=3"},
        ]
        result = build_node_id_table(modules)
        assert len(result) == 1
        assert result[0]["part"] == 3
        assert result[0]["subp"] == 0
        assert result[0]["inst"] == 0

    def test_no_node_id_params(self):
        modules = [
            {"module_name": "edc_node_x", "parameter_list": "WIDTH=32"},
        ]
        result = build_node_id_table(modules)
        assert result == []

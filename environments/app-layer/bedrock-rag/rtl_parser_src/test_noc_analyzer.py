"""
Tests for noc_analyzer.py — routing algorithms, flit structure, AXI gasket, security fence.
"""

import pytest
from noc_analyzer import (
    extract_routing_algorithms,
    extract_flit_structure,
    extract_struct_fields,
    extract_axi_address_gasket,
    identify_security_fence,
)


class TestExtractRoutingAlgorithms:
    def test_empty_input(self):
        result = extract_routing_algorithms("")
        assert result == []

    def test_none_input(self):
        result = extract_routing_algorithms(None)
        assert result == []

    def test_route_enum_extraction(self):
        content = """
        typedef enum logic [1:0] {
            DIM_ORDER = 0,
            TENDRIL = 1,
            DYNAMIC = 2
        } noc_route_algo_t;
        """
        result = extract_routing_algorithms(content)
        assert len(result) == 3
        names = [r["name"] for r in result]
        assert "DIM_ORDER" in names
        assert "TENDRIL" in names
        assert "DYNAMIC" in names

    def test_enum_values_correct(self):
        content = """
        typedef enum { XY = 0, YX = 1 } route_t;
        """
        result = extract_routing_algorithms(content)
        assert result[0]["enum_value"] == 0
        assert result[1]["enum_value"] == 1

    def test_fallback_known_keywords(self):
        content = """
        typedef enum { DIM_ORDER, TENDRIL, DYNAMIC } algo_t;
        """
        result = extract_routing_algorithms(content)
        assert len(result) == 3


class TestExtractFlitStructure:
    def test_empty_input(self):
        result = extract_flit_structure("")
        assert result["header_fields"] == []
        assert result["total_bits"] == 0

    def test_none_input(self):
        result = extract_flit_structure(None)
        assert result["header_fields"] == []

    def test_noc_header_struct(self):
        content = """
        typedef struct packed {
            logic [3:0] x_dest;
            logic [3:0] y_dest;
            logic [7:0] endpoint_id;
            logic [1:0] flit_type;
        } noc_header_address_t;
        """
        result = extract_flit_structure(content)
        assert "x_dest" in result["header_fields"]
        assert "y_dest" in result["header_fields"]
        assert "endpoint_id" in result["header_fields"]
        assert "flit_type" in result["header_fields"]
        assert result["total_bits"] == 4 + 4 + 8 + 2

    def test_fallback_flit_keywords(self):
        content = """
        typedef struct packed {
            logic [3:0] x_dest;
            logic [3:0] y_dest;
        } some_struct_t;
        """
        result = extract_flit_structure(content)
        assert "x_dest" in result["header_fields"]


class TestExtractStructFields:
    def test_empty_content(self):
        result = extract_struct_fields("", "my_struct")
        assert result == []

    def test_empty_struct_name(self):
        result = extract_struct_fields("some content", "")
        assert result == []

    def test_struct_not_found(self):
        content = "typedef struct packed { logic a; } other_t;"
        result = extract_struct_fields(content, "nonexistent_t")
        assert result == []

    def test_extracts_fields_correctly(self):
        content = """
        typedef struct packed {
            logic [31:0] addr;
            logic [7:0] data;
            logic valid;
        } my_struct_t;
        """
        result = extract_struct_fields(content, "my_struct_t")
        assert len(result) == 3
        assert result[0]["name"] == "addr"
        assert result[0]["bit_width"] == 32
        assert result[1]["name"] == "data"
        assert result[1]["bit_width"] == 8
        assert result[2]["name"] == "valid"
        assert result[2]["bit_width"] == 1


class TestExtractAxiAddressGasket:
    def test_empty_input(self):
        result = extract_axi_address_gasket("")
        assert result["total_bits"] == 0
        assert result["fields"] == []

    def test_none_input(self):
        result = extract_axi_address_gasket(None)
        assert result["total_bits"] == 0

    def test_axi_struct_extraction(self):
        content = """
        typedef struct packed {
            logic [3:0] target_index;
            logic [7:0] endpoint_id;
            logic [11:0] tlb_index;
            logic [31:0] address;
        } axi_address_t;
        """
        result = extract_axi_address_gasket(content)
        assert result["total_bits"] == 4 + 8 + 12 + 32
        assert "target_index" in result["fields"]
        assert "address" in result["fields"]


class TestIdentifySecurityFence:
    def test_empty_input(self):
        result = identify_security_fence([])
        assert result["found"] is False
        assert result["module"] == ""

    def test_none_input(self):
        result = identify_security_fence(None)
        assert result["found"] is False

    def test_finds_security_fence_module(self):
        modules = [
            {"module_name": "tt_noc_sec_fence_edc_wrapper", "instance_list": "u_smn: smn_ctrl"},
        ]
        result = identify_security_fence(modules)
        assert result["found"] is True
        assert result["module"] == "tt_noc_sec_fence_edc_wrapper"
        assert result["mechanism"] == "smn_group_access_control"

    def test_no_fence_module(self):
        modules = [
            {"module_name": "tt_noc_router", "instance_list": ""},
        ]
        result = identify_security_fence(modules)
        assert result["found"] is False

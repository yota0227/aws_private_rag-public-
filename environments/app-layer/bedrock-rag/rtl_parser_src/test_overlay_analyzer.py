"""
Tests for overlay_analyzer.py — CPU cluster, submodule roles, L1 cache, APB slaves.
"""

import pytest
from overlay_analyzer import (
    extract_cpu_cluster_params,
    identify_submodule_roles,
    extract_l1_cache_params,
    extract_apb_slaves,
    OVERLAY_SUBMODULE_ROLES,
)


class TestExtractCpuClusterParams:
    def test_empty_input(self):
        result = extract_cpu_cluster_params("")
        assert result == {}

    def test_none_input(self):
        result = extract_cpu_cluster_params(None)
        assert result == {}

    def test_extracts_num_cluster_cpus(self):
        content = "localparam NUM_CLUSTER_CPUS = 4;"
        result = extract_cpu_cluster_params(content)
        assert "NUM_CLUSTER_CPUS" in result
        assert result["NUM_CLUSTER_CPUS"] == 4

    def test_extracts_num_interrupts(self):
        content = "parameter integer NUM_INTERRUPTS = 32;"
        result = extract_cpu_cluster_params(content)
        assert "NUM_INTERRUPTS" in result
        assert result["NUM_INTERRUPTS"] == 32

    def test_extracts_reset_vector_width(self):
        content = "localparam RESET_VECTOR_WIDTH = 32;"
        result = extract_cpu_cluster_params(content)
        assert "RESET_VECTOR_WIDTH" in result
        assert result["RESET_VECTOR_WIDTH"] == 32

    def test_ignores_non_cpu_params(self):
        content = "localparam DATA_WIDTH = 64;"
        result = extract_cpu_cluster_params(content)
        assert result == {}

    def test_multiple_params(self):
        content = """
        localparam NUM_CLUSTER_CPUS = 4;
        localparam NUM_INTERRUPTS = 32;
        localparam RESET_VECTOR_WIDTH = 32;
        """
        result = extract_cpu_cluster_params(content)
        assert len(result) == 3


class TestIdentifySubmoduleRoles:
    def test_empty_input(self):
        result = identify_submodule_roles([])
        assert result == {}

    def test_none_input(self):
        result = identify_submodule_roles(None)
        assert result == {}

    def test_exact_match(self):
        modules = [{"module_name": "tt_overlay_cpu_wrapper"}]
        result = identify_submodule_roles(modules)
        assert result["tt_overlay_cpu_wrapper"] == "cpu_cluster"

    def test_all_known_roles(self):
        modules = [{"module_name": name} for name in OVERLAY_SUBMODULE_ROLES]
        result = identify_submodule_roles(modules)
        assert len(result) == len(OVERLAY_SUBMODULE_ROLES)
        for name, role in OVERLAY_SUBMODULE_ROLES.items():
            assert result[name] == role

    def test_prefix_match(self):
        modules = [{"module_name": "tt_overlay_cpu_wrapper_v2"}]
        result = identify_submodule_roles(modules)
        assert result["tt_overlay_cpu_wrapper_v2"] == "cpu_cluster"

    def test_unknown_module_not_assigned(self):
        modules = [{"module_name": "tt_unknown_module"}]
        result = identify_submodule_roles(modules)
        assert result == {}

    def test_mixed_modules(self):
        modules = [
            {"module_name": "tt_overlay_cpu_wrapper"},
            {"module_name": "tt_idma_wrapper"},
            {"module_name": "tt_unknown"},
        ]
        result = identify_submodule_roles(modules)
        assert len(result) == 2
        assert "tt_unknown" not in result


class TestExtractL1CacheParams:
    def test_empty_input(self):
        result = extract_l1_cache_params("")
        assert result == {}

    def test_none_input(self):
        result = extract_l1_cache_params(None)
        assert result == {}

    def test_extracts_num_banks(self):
        content = "localparam NUM_BANKS = 8;"
        result = extract_l1_cache_params(content)
        assert "NUM_BANKS" in result
        assert result["NUM_BANKS"] == 8

    def test_extracts_bank_width(self):
        content = "parameter BANK_WIDTH = 64;"
        result = extract_l1_cache_params(content)
        assert "BANK_WIDTH" in result
        assert result["BANK_WIDTH"] == 64

    def test_extracts_string_ecc_type(self):
        content = 'localparam ECC_TYPE = "SECDED";'
        result = extract_l1_cache_params(content)
        assert "ECC_TYPE" in result
        assert result["ECC_TYPE"] == "SECDED"

    def test_multiple_cache_params(self):
        content = """
        localparam NUM_BANKS = 8;
        localparam BANK_WIDTH = 64;
        localparam SRAM_TYPE = "SP_SRAM";
        """
        result = extract_l1_cache_params(content)
        assert len(result) == 3


class TestExtractApbSlaves:
    def test_empty_input(self):
        result = extract_apb_slaves("")
        assert result == []

    def test_none_input(self):
        result = extract_apb_slaves(None)
        assert result == []

    def test_slave_localparam(self):
        content = """
        localparam SLAVE_0_ADDR = 32'h0000_0000;
        localparam SLAVE_1_ADDR = 32'h0000_1000;
        """
        result = extract_apb_slaves(content)
        assert len(result) >= 2

    def test_numbered_slave_pattern(self):
        content = """
        localparam SLAVE_0 = 32'h0000;
        localparam SLAVE_1 = 32'h1000;
        localparam SLAVE_2 = 32'h2000;
        """
        result = extract_apb_slaves(content)
        assert len(result) >= 3

    def test_case_decode_pattern(self):
        content = """
        0: begin base_addr <= 32'h0000; end
        1: begin base_addr <= 32'h1000; end
        """
        result = extract_apb_slaves(content)
        assert len(result) >= 2

    def test_no_duplicates(self):
        content = """
        localparam SLV_0 = 32'h0000;
        localparam SLV_0 = 32'h0000;
        """
        result = extract_apb_slaves(content)
        # Should deduplicate by name
        slv0_count = sum(1 for s in result if "slv_0" in s["name"].lower())
        assert slv0_count == 1

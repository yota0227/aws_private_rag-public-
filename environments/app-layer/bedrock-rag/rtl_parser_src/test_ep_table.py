"""Unit tests for EP Index Table computation (Task 24.1, Requirements 27)."""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from unittest.mock import patch
from package_extractor import extract_package_constants, _compute_ep_index_table, _get_tile_type


TRINITY_PKG_4X5 = """
package trinity_pkg;
    localparam int SizeX = 4;
    localparam int SizeY = 5;
    localparam int NumNodes = 20;
    localparam int NumTensix = 12;

    typedef enum logic [2:0] {
        TENSIX              = 3'd0,
        NOC2AXI_NE_OPT     = 3'd1,
        NOC2AXI_ROUTER_NE_OPT = 3'd2,
        NOC2AXI_ROUTER_NW_OPT = 3'd3,
        NOC2AXI_NW_OPT     = 3'd4,
        DISPATCH_E          = 3'd5,
        DISPATCH_W          = 3'd6,
        ROUTER              = 3'd7
    } tile_t;
endpackage
"""


class TestComputeEpIndexTable:
    """Test _compute_ep_index_table function."""

    def test_generates_20_ep_claims_for_4x5(self):
        """SizeX=4, SizeY=5 → 20 individual EP claims + 1 summary = 21 total."""
        content = "localparam int SizeX = 4;\nlocalparam int SizeY = 5;"
        claims = _compute_ep_index_table(content, "trinity_pkg", "pkg.sv", "pipe1")
        assert len(claims) == 21

    def test_ep_indices_are_sequential(self):
        """EP indices should be 0..19 in order."""
        content = "localparam int SizeX = 4;\nlocalparam int SizeY = 5;"
        claims = _compute_ep_index_table(content, "trinity_pkg", "pkg.sv", "pipe1")
        ep_numbers = []
        for c in claims[:-1]:
            text = c["claim_text"]
            ep_str = text.split("EP=")[1].split(" ")[0]
            ep_numbers.append(int(ep_str))
        assert ep_numbers == list(range(20))

    def test_ep_formula_roundtrip(self):
        """EP = X * SizeY + Y should hold for all claims."""
        content = "localparam int SizeX = 4;\nlocalparam int SizeY = 5;"
        claims = _compute_ep_index_table(content, "trinity_pkg", "pkg.sv", "pipe1")
        size_y = 5
        for c in claims[:-1]:
            text = c["claim_text"]
            ep = int(text.split("EP=")[1].split(" ")[0])
            x = int(text.split("X=")[1].split(",")[0])
            y = int(text.split("Y=")[1].split(")")[0])
            assert ep == x * size_y + y

    def test_tile_type_mapping_tensix(self):
        """Y=0,1,2 should be TENSIX for all X."""
        content = "localparam int SizeX = 4;\nlocalparam int SizeY = 5;"
        claims = _compute_ep_index_table(content, "trinity_pkg", "pkg.sv", "pipe1")
        for c in claims[:-1]:
            text = c["claim_text"]
            y = int(text.split("Y=")[1].split(")")[0])
            if y <= 2:
                assert "TENSIX" in text

    def test_tile_type_mapping_noc2axi(self):
        """Y=4 positions should have NOC2AXI types."""
        content = "localparam int SizeX = 4;\nlocalparam int SizeY = 5;"
        claims = _compute_ep_index_table(content, "trinity_pkg", "pkg.sv", "pipe1")
        y4_claims = [c for c in claims[:-1] if "Y=4)" in c["claim_text"]]
        assert len(y4_claims) == 4
        types = [c["claim_text"].split("tile type ")[1] for c in y4_claims]
        assert "NOC2AXI_NE_OPT" in types
        assert "NOC2AXI_ROUTER_NE_OPT" in types
        assert "NOC2AXI_ROUTER_NW_OPT" in types
        assert "NOC2AXI_NW_OPT" in types

    def test_tile_type_mapping_dispatch(self):
        """Y=3, X=0 should be DISPATCH_E, X=3 should be DISPATCH_W."""
        content = "localparam int SizeX = 4;\nlocalparam int SizeY = 5;"
        claims = _compute_ep_index_table(content, "trinity_pkg", "pkg.sv", "pipe1")
        y3_claims = [c for c in claims[:-1] if "Y=3)" in c["claim_text"]]
        x0y3 = [c for c in y3_claims if "X=0," in c["claim_text"]]
        x3y3 = [c for c in y3_claims if "X=3," in c["claim_text"]]
        assert "DISPATCH_E" in x0y3[0]["claim_text"]
        assert "DISPATCH_W" in x3y3[0]["claim_text"]

    def test_summary_claim_exists(self):
        """Last claim should be the EP Table summary."""
        content = "localparam int SizeX = 4;\nlocalparam int SizeY = 5;"
        claims = _compute_ep_index_table(content, "trinity_pkg", "pkg.sv", "pipe1")
        summary = claims[-1]
        assert "EP Index Table:" in summary["claim_text"]
        assert "20" in summary["claim_text"]

    def test_parser_source_field(self):
        """All EP claims should have parser_source='ep_index_table'."""
        content = "localparam int SizeX = 4;\nlocalparam int SizeY = 5;"
        claims = _compute_ep_index_table(content, "trinity_pkg", "pkg.sv", "pipe1")
        for c in claims:
            assert c.get("parser_source") == "ep_index_table"

    def test_missing_sizex_returns_empty(self):
        content = "localparam int SizeY = 5;"
        claims = _compute_ep_index_table(content, "trinity_pkg", "pkg.sv", "pipe1")
        assert claims == []

    def test_missing_sizey_returns_empty(self):
        content = "localparam int SizeX = 4;"
        claims = _compute_ep_index_table(content, "trinity_pkg", "pkg.sv", "pipe1")
        assert claims == []

    def test_feature_flag_disabled(self):
        with patch.dict(os.environ, {"PARSER_EP_TABLE_ENABLED": "false"}):
            claims = extract_package_constants(TRINITY_PKG_4X5, "pkg.sv", "pipe1")
            ep_claims = [c for c in claims if c.get("parser_source") == "ep_index_table"]
            assert len(ep_claims) == 0

    def test_feature_flag_enabled(self):
        with patch.dict(os.environ, {"PARSER_EP_TABLE_ENABLED": "true"}):
            claims = extract_package_constants(TRINITY_PKG_4X5, "pkg.sv", "pipe1")
            ep_claims = [c for c in claims if c.get("parser_source") == "ep_index_table"]
            assert len(ep_claims) == 21

    def test_smaller_grid_2x3(self):
        content = "localparam int SizeX = 2;\nlocalparam int SizeY = 3;"
        claims = _compute_ep_index_table(content, "test_pkg", "pkg.sv", "pipe1")
        assert len(claims) == 7  # 6 + 1 summary


class TestGetTileType:
    def test_tensix_positions(self):
        for x in range(4):
            for y in range(3):
                assert _get_tile_type(x, y) == "TENSIX"

    def test_noc2axi_ne_opt(self):
        assert _get_tile_type(0, 4) == "NOC2AXI_NE_OPT"

    def test_noc2axi_router_ne_opt(self):
        assert _get_tile_type(1, 4) == "NOC2AXI_ROUTER_NE_OPT"

    def test_dispatch_e(self):
        assert _get_tile_type(0, 3) == "DISPATCH_E"

    def test_dispatch_w(self):
        assert _get_tile_type(3, 3) == "DISPATCH_W"

    def test_router(self):
        assert _get_tile_type(1, 3) == "ROUTER"
        assert _get_tile_type(2, 3) == "ROUTER"

    def test_unknown_position(self):
        assert _get_tile_type(5, 5) == "UNKNOWN"

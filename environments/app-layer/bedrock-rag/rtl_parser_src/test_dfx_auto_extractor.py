"""
Unit tests for DFX auto-extraction logic (Requirements 4.1, 4.2, 4.3).

Tests:
- _is_dfx_module: DFX module pattern detection
- _count_clock_ports: clock port counting
- _detect_ijtag_ifdef: IJTAG ifdef detection
- extract_dfx_module_claims: full claim generation
- resolve_dfx_claim_conflict: manual vs auto claim priority
"""

import pytest
from handler import (
    _is_dfx_module,
    _count_clock_ports,
    _detect_ijtag_ifdef,
    extract_dfx_module_claims,
    resolve_dfx_claim_conflict,
)


class TestIsDfxModule:
    """_is_dfx_module 패턴 매칭 테스트."""

    def test_dfx_suffix_detected(self):
        assert _is_dfx_module("tt_noc_niu_router_dfx") is True

    def test_dfx_suffix_simple(self):
        assert _is_dfx_module("tt_overlay_wrapper_dfx") is True

    def test_non_dfx_module(self):
        assert _is_dfx_module("tt_noc_niu_router") is False

    def test_dfx_in_middle_not_detected(self):
        assert _is_dfx_module("tt_dfx_scan_controller") is False

    def test_empty_string(self):
        assert _is_dfx_module("") is False

    def test_just_dfx(self):
        # Edge case: module named exactly "_dfx"
        assert _is_dfx_module("_dfx") is True


class TestCountClockPorts:
    """_count_clock_ports clock 포트 카운팅 테스트."""

    def test_basic_clock_ports(self):
        ports = [
            "input clk",
            "input i_scan_clk",
            "output o_clk_out",
            "input reset_n",
        ]
        result = _count_clock_ports(ports)
        assert result["clock_in"] == 2
        assert result["clock_out"] == 1

    def test_no_clock_ports(self):
        ports = ["input data_in", "output data_out", "input reset_n"]
        result = _count_clock_ports(ports)
        assert result["clock_in"] == 0
        assert result["clock_out"] == 0

    def test_clock_keyword_variant(self):
        ports = [
            "input i_core_clock",
            "output o_divided_clock",
            "inout io_clk_bidir",
        ]
        result = _count_clock_ports(ports)
        assert result["clock_in"] == 2  # input + inout
        assert result["clock_out"] == 1

    def test_empty_port_list(self):
        result = _count_clock_ports([])
        assert result["clock_in"] == 0
        assert result["clock_out"] == 0

    def test_bitwidth_clock_ports(self):
        ports = [
            "input [3:0] i_clk_array",
            "output [1:0] o_clk_div",
        ]
        result = _count_clock_ports(ports)
        assert result["clock_in"] == 1
        assert result["clock_out"] == 1


class TestDetectIjtagIfdef:
    """_detect_ijtag_ifdef IJTAG ifdef 감지 테스트."""

    def test_ifdef_ijtag(self):
        content = """
module tt_noc_niu_router_dfx (
    input clk,
    output scan_out
);
`ifdef IJTAG
    // IJTAG scan chain logic
`endif
endmodule
"""
        assert _detect_ijtag_ifdef(content) is True

    def test_ifdef_dfx_ijtag(self):
        content = """
module tt_overlay_wrapper_dfx (
    input clk
);
`ifdef DFX_IJTAG
    wire scan_enable;
`endif
endmodule
"""
        assert _detect_ijtag_ifdef(content) is True

    def test_no_ijtag_ifdef(self):
        content = """
module tt_some_module (
    input clk,
    output data
);
    assign data = 1'b0;
endmodule
"""
        assert _detect_ijtag_ifdef(content) is False

    def test_ifdef_other_macro(self):
        content = """
`ifdef SYNTHESIS
    // synthesis only
`endif
"""
        assert _detect_ijtag_ifdef(content) is False


class TestExtractDfxModuleClaims:
    """extract_dfx_module_claims 전체 claim 생성 테스트."""

    def test_basic_dfx_module(self):
        rtl_content = """
module tt_noc_niu_router_dfx (
    input  clk,
    input  i_scan_clk,
    output o_scan_clk_out,
    input  reset_n,
    input  [7:0] data_in,
    output [7:0] data_out
);
`ifdef IJTAG
    wire scan_chain;
`endif
endmodule
"""
        claims = extract_dfx_module_claims(
            rtl_content,
            module_name="tt_noc_niu_router_dfx",
            file_path="rtl-sources/tt_20260221/dfx/tt_noc_niu_router_dfx.sv",
            pipeline_id="tt_20260221",
        )

        assert len(claims) == 1
        claim = claims[0]
        assert claim["claim_type"] == "structural"
        assert claim["topic"] == "DFX"
        assert claim["source"] == "auto_extracted"
        assert claim["confidence_score"] == 0.9
        assert claim["module_name"] == "tt_noc_niu_router_dfx"
        assert "tt_noc_niu_router_dfx" in claim["claim_text"]
        assert "DFX wrapper" in claim["claim_text"]
        assert "IJTAG ifdef present" in claim["claim_text"]
        assert "2 in" in claim["claim_text"]  # clk + i_scan_clk
        assert "1 out" in claim["claim_text"]  # o_scan_clk_out
        assert claim["pipeline_id"] == "tt_20260221"
        assert claim["analysis_type"] == "claim"

    def test_dfx_module_no_ijtag(self):
        rtl_content = """
module tt_simple_dfx (
    input  clk,
    output data
);
    assign data = 1'b0;
endmodule
"""
        claims = extract_dfx_module_claims(
            rtl_content,
            module_name="tt_simple_dfx",
            file_path="rtl-sources/tt_20260221/dfx/tt_simple_dfx.sv",
            pipeline_id="tt_20260221",
        )

        assert len(claims) == 1
        claim = claims[0]
        assert "no IJTAG ifdef detected" in claim["claim_text"]
        assert claim["dfx_metadata"]["has_ijtag"] is False

    def test_dfx_metadata_fields(self):
        rtl_content = """
module tt_t6_l1_partition_dfx (
    input  i_clk_a,
    input  i_clk_b,
    output o_clk_out,
    input  reset_n
);
`ifdef DFX_IJTAG
    // scan chain
`endif
endmodule
"""
        claims = extract_dfx_module_claims(
            rtl_content,
            module_name="tt_t6_l1_partition_dfx",
            file_path="rtl-sources/tt_20260221/dfx/tt_t6_l1_partition_dfx.sv",
            pipeline_id="tt_20260221",
        )

        assert len(claims) == 1
        meta = claims[0]["dfx_metadata"]
        assert meta["clock_in"] == 2
        assert meta["clock_out"] == 1
        assert meta["has_ijtag"] is True


class TestResolveDfxClaimConflict:
    """resolve_dfx_claim_conflict manual vs auto 우선순위 테스트."""

    def test_manual_overrides_auto(self):
        auto_claims = [
            {
                "claim_id": "auto_dfx_tt_noc_niu_router_dfx_tt_20260221",
                "module_name": "tt_noc_niu_router_dfx",
                "topic": "DFX",
                "source": "auto_extracted",
                "confidence_score": 0.9,
            },
        ]
        manual_claims = [
            {
                "claim_id": "manual_dfx_wrapper_001",
                "module_name": "tt_noc_niu_router_dfx",
                "topic": "DFX",
                "source": "manual_claim",
                "confidence_score": 1.0,
            },
        ]

        resolved = resolve_dfx_claim_conflict(auto_claims, manual_claims)
        assert len(resolved) == 0  # auto claim removed

    def test_auto_kept_when_no_manual(self):
        auto_claims = [
            {
                "claim_id": "auto_dfx_tt_new_dfx_tt_20260221",
                "module_name": "tt_new_dfx",
                "topic": "DFX",
                "source": "auto_extracted",
                "confidence_score": 0.9,
            },
        ]
        manual_claims = [
            {
                "claim_id": "manual_dfx_wrapper_001",
                "module_name": "tt_noc_niu_router_dfx",
                "topic": "DFX",
                "source": "manual_claim",
                "confidence_score": 1.0,
            },
        ]

        resolved = resolve_dfx_claim_conflict(auto_claims, manual_claims)
        assert len(resolved) == 1
        assert resolved[0]["module_name"] == "tt_new_dfx"

    def test_mixed_resolution(self):
        auto_claims = [
            {
                "module_name": "tt_noc_niu_router_dfx",
                "topic": "DFX",
                "source": "auto_extracted",
                "confidence_score": 0.9,
            },
            {
                "module_name": "tt_new_wrapper_dfx",
                "topic": "DFX",
                "source": "auto_extracted",
                "confidence_score": 0.9,
            },
        ]
        manual_claims = [
            {
                "module_name": "tt_noc_niu_router_dfx",
                "topic": "DFX",
                "source": "manual_claim",
                "confidence_score": 1.0,
            },
        ]

        resolved = resolve_dfx_claim_conflict(auto_claims, manual_claims)
        assert len(resolved) == 1
        assert resolved[0]["module_name"] == "tt_new_wrapper_dfx"

    def test_non_dfx_manual_claims_ignored(self):
        auto_claims = [
            {
                "module_name": "tt_noc_niu_router_dfx",
                "topic": "DFX",
                "source": "auto_extracted",
                "confidence_score": 0.9,
            },
        ]
        manual_claims = [
            {
                "module_name": "tt_noc_niu_router_dfx",
                "topic": "EDC",  # Different topic
                "source": "manual_claim",
                "confidence_score": 1.0,
            },
        ]

        resolved = resolve_dfx_claim_conflict(auto_claims, manual_claims)
        assert len(resolved) == 1  # auto claim kept (manual is EDC, not DFX)

    def test_empty_inputs(self):
        assert resolve_dfx_claim_conflict([], []) == []
        assert resolve_dfx_claim_conflict([], [{"module_name": "x", "topic": "DFX", "source": "manual_claim"}]) == []

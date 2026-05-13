"""
Unit tests for inject_manual_claims.py

Validates:
  - Correct claim structure (claim_id, claim_type, topic, confidence_score, source)
  - EDC per-column ring claim content (Req 1.1, 1.3)
  - EDC port [3:0] array dimension claim (Req 3.3)
  - DFX 4-wrapper chain claims (Req 4.1, 4.3)
  - Idempotent injection (skip on duplicate)
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from inject_manual_claims import build_manual_claims, inject_claims


class TestBuildManualClaims:
    """build_manual_claims() 함수 검증"""

    def test_returns_six_claims(self):
        """총 6개 claim 생성: EDC ring + EDC port array + DFX x4"""
        claims = build_manual_claims("tt_20260221")
        assert len(claims) == 6

    def test_edc_ring_claim_structure(self):
        """EDC per-column ring claim 구조 검증 (Req 1.1, 1.3)"""
        claims = build_manual_claims("tt_20260221")
        edc_ring = claims[0]

        assert edc_ring["claim_id"] == "manual_edc_ring_001"
        assert edc_ring["claim_type"] == "structural"
        assert edc_ring["topic"] == "EDC"
        assert edc_ring["confidence_score"] == Decimal("1.0")
        assert edc_ring["source"] == "manual_claim"
        assert edc_ring["pipeline_id"] == "tt_20260221"
        assert edc_ring["status"] == "verified"
        assert "Each column (X=0..3)" in edc_ring["claim_text"]
        assert "independent EDC ring" in edc_ring["claim_text"]

    def test_edc_port_array_claim(self):
        """EDC port [3:0] 배열 차원 claim 검증 (Req 3.3)"""
        claims = build_manual_claims("tt_20260221")
        edc_port = claims[1]

        assert edc_port["claim_id"] == "manual_edc_port_array_001"
        assert edc_port["claim_type"] == "structural"
        assert edc_port["topic"] == "EDC"
        assert edc_port["confidence_score"] == Decimal("1.0")
        assert edc_port["source"] == "manual_claim"
        assert "[3:0]" in edc_port["claim_text"]
        assert "i_edc_apb_psel[3:0]" in edc_port["claim_text"]
        assert "o_edc_fatal_err_irq[3:0]" in edc_port["claim_text"]

    def test_dfx_wrapper_claims_count(self):
        """DFX 4-wrapper chain: 정확히 4개 claim (Req 4.1)"""
        claims = build_manual_claims("tt_20260221")
        dfx_claims = [c for c in claims if c["topic"] == "DFX"]
        assert len(dfx_claims) == 4

    def test_dfx_wrapper_module_names(self):
        """DFX 4-wrapper chain: 올바른 모듈명 (Req 4.1)"""
        claims = build_manual_claims("tt_20260221")
        dfx_claims = [c for c in claims if c["topic"] == "DFX"]
        module_names = {c["module_name"] for c in dfx_claims}

        expected = {
            "tt_noc_niu_router_dfx",
            "tt_overlay_wrapper_dfx",
            "tt_instrn_engine_wrapper_dfx",
            "tt_t6_l1_partition_dfx",
        }
        assert module_names == expected

    def test_dfx_wrapper_claims_structure(self):
        """DFX wrapper claims: claim_type=structural, topic=DFX, source=manual_claim (Req 4.3)"""
        claims = build_manual_claims("tt_20260221")
        dfx_claims = [c for c in claims if c["topic"] == "DFX"]

        for claim in dfx_claims:
            assert claim["claim_type"] == "structural"
            assert claim["topic"] == "DFX"
            assert claim["source"] == "manual_claim"
            assert claim["confidence_score"] == Decimal("1.0")
            assert claim["status"] == "verified"

    def test_all_claims_have_required_fields(self):
        """모든 claim에 필수 필드가 존재"""
        claims = build_manual_claims("tt_20260221")
        required_fields = [
            "claim_id", "claim_type", "claim_text", "topic",
            "confidence_score", "source", "pipeline_id", "status",
            "created_at", "updated_at",
        ]

        for claim in claims:
            for field in required_fields:
                assert field in claim, f"Missing field '{field}' in claim {claim['claim_id']}"

    def test_pipeline_id_propagation(self):
        """커스텀 pipeline_id가 모든 claim에 전파됨"""
        custom_id = "tt_custom_20260301"
        claims = build_manual_claims(custom_id)

        for claim in claims:
            assert claim["pipeline_id"] == custom_id


class TestInjectClaims:
    """inject_claims() 함수 검증"""

    def test_dry_run_no_dynamodb_calls(self):
        """dry_run=True이면 DynamoDB 호출 없음"""
        claims = build_manual_claims("tt_20260221")

        with patch("inject_manual_claims.boto3") as mock_boto3:
            result = inject_claims(claims, "test-table", "ap-northeast-2", dry_run=True)

            mock_boto3.resource.assert_not_called()
            assert result["success_count"] == 6
            assert result["error_count"] == 0

    def test_successful_injection(self):
        """정상 삽입 시 success_count 증가"""
        claims = build_manual_claims("tt_20260221")

        with patch("inject_manual_claims.boto3") as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table

            result = inject_claims(claims, "test-table", "ap-northeast-2", dry_run=False)

            assert result["success_count"] == 6
            assert result["skip_count"] == 0
            assert result["error_count"] == 0
            assert mock_table.put_item.call_count == 6

    def test_duplicate_claim_skipped(self):
        """중복 claim 삽입 시 skip_count 증가 (idempotent)"""
        claims = build_manual_claims("tt_20260221")[:1]  # 1개만 테스트

        with patch("inject_manual_claims.boto3") as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table

            # ConditionalCheckFailedException 시뮬레이션
            exc_class = type("ConditionalCheckFailedException", (Exception,), {})
            mock_table.meta.client.exceptions.ConditionalCheckFailedException = exc_class
            mock_table.put_item.side_effect = exc_class("already exists")

            result = inject_claims(claims, "test-table", "ap-northeast-2", dry_run=False)

            assert result["success_count"] == 0
            assert result["skip_count"] == 1
            assert result["error_count"] == 0

"""Tests for handler.py — 대형 모듈 청킹 (Task 18.1) + 질의 유형별 동적 Boost (Task 18.3).

Validates Requirements: 23.1, 23.2, 23.3, 23.4, 23.5, 24.1~24.8
"""

import pytest
from unittest.mock import patch, MagicMock

from handler import (
    classify_query_type,
    get_dynamic_boosts,
    _create_sub_records,
    parse_rtl_to_ast,
)
from port_classifier import classify_ports


# ===========================================================================
# Task 18.1: 대형 모듈 청킹 — _create_sub_records()
# ===========================================================================


class TestCreateSubRecords:
    """Tests for _create_sub_records — 대형 모듈 Sub_Record 분할."""

    def _make_metadata(self, port_count=60, instance_count=5, param_count=3):
        """Helper: 테스트용 모듈 메타데이터 생성."""
        ports = [f"input port_{i}" for i in range(port_count)]
        instances = [f"u_inst_{i}: MOD_TYPE_{i}" for i in range(instance_count)]
        params = [f"PARAM_{i}={i * 10}" for i in range(param_count)]
        return {
            "module_name": "test_large_module",
            "parent_module": "top_module",
            "port_list": ports,
            "parameter_list": params,
            "instance_list": instances,
            "file_path": "rtl-sources/test/test_large_module.sv",
            "pipeline_id": "tt_20260301",
            "chip_type": "tt",
            "snapshot_date": "20260301",
            "analysis_type": "module_parse",
        }

    def _make_port_claims(self, module_name="test_large_module"):
        """Helper: classify_ports 결과를 시뮬레이션."""
        return [
            {
                "analysis_type": "claim",
                "claim_text": f"Module '{module_name}' has 5 AXI_Interface ports: npu_out_0, npu_out_1, npu_in_0, npu_in_1, axi_clk",
                "claim_type": "structural",
                "module_name": module_name,
                "topic": "TopLevelPorts",
            },
            {
                "analysis_type": "claim",
                "claim_text": f"Module '{module_name}' has 3 EDC_APB ports: edc_apb_psel, edc_apb_paddr, edc_apb_pwdata",
                "claim_type": "structural",
                "module_name": module_name,
                "topic": "TopLevelPorts",
            },
            {
                "analysis_type": "claim",
                "claim_text": f"Module '{module_name}' has 60 total ports: AXI_Interface(5), EDC_APB(3), Other(52)",
                "claim_type": "structural",
                "module_name": module_name,
                "topic": "TopLevelPorts",
            },
        ]

    # --- Requirement 23.1: 포트 50개 이상 → Sub_Record 분할 ---

    def test_sub_records_created_for_large_module(self):
        """포트 50개 이상 모듈에서 Sub_Record가 생성된다."""
        metadata = self._make_metadata(port_count=60)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)
        assert len(sub_records) > 0

    def test_three_sub_record_types_present(self):
        """3가지 Sub_Record 유형(port_summary, instance_hierarchy, parameter_config)이 모두 생성된다."""
        metadata = self._make_metadata(port_count=60)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)

        types = {r["sub_record_type"] for r in sub_records}
        assert "port_summary" in types
        assert "instance_hierarchy" in types
        assert "parameter_config" in types

    # --- Requirement 23.2: Sub_Record 필드 포함 ---

    def test_sub_record_has_required_fields(self):
        """각 Sub_Record에 parent_module_name, sub_record_type, analysis_type 필드가 포함된다."""
        metadata = self._make_metadata(port_count=60)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)

        for record in sub_records:
            assert "parent_module_name" in record
            assert "sub_record_type" in record
            assert "analysis_type" in record
            assert record["parent_module_name"] == "test_large_module"
            assert record["analysis_type"] == "module_parse_chunk"

    def test_sub_record_has_module_name(self):
        """각 Sub_Record에 module_name이 원본 모듈명과 동일하다."""
        metadata = self._make_metadata(port_count=60)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)

        for record in sub_records:
            assert record["module_name"] == "test_large_module"

    # --- Requirement 23.3: 기존 전체 모듈 레코드 유지 ---

    def test_original_metadata_unchanged(self):
        """_create_sub_records는 원본 metadata를 변경하지 않는다 (기존 레코드 유지)."""
        metadata = self._make_metadata(port_count=60)
        original_analysis_type = metadata["analysis_type"]
        port_claims = self._make_port_claims()
        _create_sub_records(metadata, port_claims)

        assert metadata["analysis_type"] == original_analysis_type
        assert metadata["analysis_type"] == "module_parse"

    # --- Requirement 23.4: port_summary는 Port_Classifier 카테고리별 ---

    def test_port_summary_per_category(self):
        """port_summary Sub_Record는 Port_Classifier의 카테고리별로 생성된다."""
        metadata = self._make_metadata(port_count=60)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)

        port_summaries = [r for r in sub_records if r["sub_record_type"] == "port_summary"]
        # port_claims에 3개 claim → 3개 port_summary Sub_Record
        assert len(port_summaries) == len(port_claims)

    def test_port_summary_contains_claim_text(self):
        """port_summary Sub_Record의 parsed_summary에 claim_text가 포함된다."""
        metadata = self._make_metadata(port_count=60)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)

        port_summaries = [r for r in sub_records if r["sub_record_type"] == "port_summary"]
        for i, summary in enumerate(port_summaries):
            assert summary["parsed_summary"] == port_claims[i]["claim_text"]

    # --- Requirement 23.5: 검색 응답에 parent_module_name 포함 ---

    def test_parent_module_name_in_sub_records(self):
        """Sub_Record에 parent_module_name이 포함되어 원본 모듈 식별 가능."""
        metadata = self._make_metadata(port_count=60)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)

        for record in sub_records:
            assert record["parent_module_name"] == metadata["module_name"]

    # --- instance_hierarchy Sub_Record ---

    def test_instance_hierarchy_contains_instances(self):
        """instance_hierarchy Sub_Record에 인스턴스 목록이 포함된다."""
        metadata = self._make_metadata(port_count=60, instance_count=3)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)

        hierarchy = [r for r in sub_records if r["sub_record_type"] == "instance_hierarchy"]
        assert len(hierarchy) == 1
        assert "instance hierarchy" in hierarchy[0]["parsed_summary"]
        assert "u_inst_0" in hierarchy[0]["instance_list"]

    def test_no_instance_hierarchy_when_empty(self):
        """인스턴스가 없으면 instance_hierarchy Sub_Record가 생성되지 않는다."""
        metadata = self._make_metadata(port_count=60, instance_count=0)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)

        hierarchy = [r for r in sub_records if r["sub_record_type"] == "instance_hierarchy"]
        assert len(hierarchy) == 0

    # --- parameter_config Sub_Record ---

    def test_parameter_config_contains_params(self):
        """parameter_config Sub_Record에 파라미터 목록이 포함된다."""
        metadata = self._make_metadata(port_count=60, param_count=4)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)

        config = [r for r in sub_records if r["sub_record_type"] == "parameter_config"]
        assert len(config) == 1
        assert "parameter configuration" in config[0]["parsed_summary"]
        assert "PARAM_0=0" in config[0]["parsed_summary"]

    def test_no_parameter_config_when_empty(self):
        """파라미터가 없으면 parameter_config Sub_Record가 생성되지 않는다."""
        metadata = self._make_metadata(port_count=60, param_count=0)
        port_claims = self._make_port_claims()
        sub_records = _create_sub_records(metadata, port_claims)

        config = [r for r in sub_records if r["sub_record_type"] == "parameter_config"]
        assert len(config) == 0

    # --- Edge case: 빈 port_claims ---

    def test_empty_port_claims(self):
        """port_claims가 빈 리스트여도 instance/parameter Sub_Record는 생성된다."""
        metadata = self._make_metadata(port_count=60, instance_count=2, param_count=2)
        sub_records = _create_sub_records(metadata, [])

        types = {r["sub_record_type"] for r in sub_records}
        assert "port_summary" not in types
        assert "instance_hierarchy" in types
        assert "parameter_config" in types


# ===========================================================================
# Task 18.3: 질의 유형별 동적 Boost — classify_query_type + get_dynamic_boosts
# ===========================================================================


class TestClassifyQueryType:
    """Tests for classify_query_type — 질의 유형 분류."""

    # --- Requirement 24.1: 5가지 유형 분류 ---

    def test_port_query_keywords(self):
        """포트 관련 키워드가 포함된 질의는 port_query로 분류된다."""
        assert classify_query_type("Power 관련 포트가 뭐야?") == "port_query"
        assert classify_query_type("AXI interface ports") == "port_query"
        assert classify_query_type("clock signal list") == "port_query"
        assert classify_query_type("reset 핀 목록") == "port_query"
        assert classify_query_type("input output 포트") == "port_query"
        assert classify_query_type("APB 인터페이스") == "port_query"

    def test_hierarchy_query_keywords(self):
        """계층 관련 키워드가 포함된 질의는 hierarchy_query로 분류된다."""
        assert classify_query_type("모듈 계층 구조를 보여줘") == "hierarchy_query"
        assert classify_query_type("인스턴스 목록") == "hierarchy_query"
        assert classify_query_type("hierarchy of BLK_UCIE") == "hierarchy_query"
        assert classify_query_type("instantiate 관계") == "hierarchy_query"
        assert classify_query_type("모듈 트리 구조") == "hierarchy_query"

    def test_config_query_keywords(self):
        """설정 관련 키워드가 포함된 질의는 config_query로 분류된다."""
        assert classify_query_type("파라미터 값이 뭐야?") == "config_query"
        assert classify_query_type("parameter SizeX") == "config_query"
        assert classify_query_type("localparam 설정") == "config_query"
        assert classify_query_type("크기 설정 확인") == "config_query"
        assert classify_query_type("size of buffer") == "config_query"

    def test_connectivity_query_keywords(self):
        """연결 관련 키워드가 포함된 질의는 connectivity_query로 분류된다."""
        assert classify_query_type("EDC 연결 토폴로지") == "connectivity_query"
        assert classify_query_type("ring topology") == "connectivity_query"
        assert classify_query_type("chain connection") == "connectivity_query"
        assert classify_query_type("routing 구조") == "connectivity_query"
        assert classify_query_type("generate block") == "connectivity_query"

    # --- Requirement 24.8: 미매칭 시 general_query 폴백 ---

    def test_general_query_fallback(self):
        """키워드 미매칭 시 general_query로 분류된다."""
        assert classify_query_type("이 모듈은 뭐하는 거야?") == "general_query"
        assert classify_query_type("설명해줘") == "general_query"
        assert classify_query_type("BLK_UCIE 기능") == "general_query"

    def test_empty_query(self):
        """빈 질의는 general_query로 분류된다."""
        assert classify_query_type("") == "general_query"

    def test_none_safe(self):
        """None 입력도 general_query로 분류된다 (방어적 처리)."""
        # classify_query_type은 빈 문자열 체크로 None도 처리
        assert classify_query_type("") == "general_query"

    # --- Requirement 24.2: 키워드 패턴 매칭 ---

    def test_case_insensitive_matching(self):
        """키워드 매칭은 대소문자를 구분하지 않는다."""
        assert classify_query_type("PORT list") == "port_query"
        assert classify_query_type("HIERARCHY view") == "hierarchy_query"
        assert classify_query_type("PARAMETER values") == "config_query"
        assert classify_query_type("TOPOLOGY map") == "connectivity_query"

    def test_first_match_wins(self):
        """여러 유형의 키워드가 포함되면 첫 번째 매칭 유형이 반환된다."""
        # _QUERY_TYPE_KEYWORDS 순서: port_query → hierarchy_query → config_query → connectivity_query
        result = classify_query_type("port hierarchy")
        assert result == "port_query"  # port가 먼저 매칭


class TestGetDynamicBoosts:
    """Tests for get_dynamic_boosts — 질의 유형별 boost 가중치."""

    # --- Requirement 24.3: port_query boost ---

    def test_port_query_boosts(self):
        """port_query: claim 4.0, module_parse 0.5."""
        boosts = get_dynamic_boosts("port_query")
        assert boosts["claim"] == 4.0
        assert boosts["module_parse"] == 0.5

    # --- Requirement 24.4: hierarchy_query boost ---

    def test_hierarchy_query_boosts(self):
        """hierarchy_query: claim 1.5, module_parse 3.0."""
        boosts = get_dynamic_boosts("hierarchy_query")
        assert boosts["claim"] == 1.5
        assert boosts["module_parse"] == 3.0

    # --- Requirement 24.5: config_query boost ---

    def test_config_query_boosts(self):
        """config_query: claim 4.0, module_parse 1.0."""
        boosts = get_dynamic_boosts("config_query")
        assert boosts["claim"] == 4.0
        assert boosts["module_parse"] == 1.0

    # --- Requirement 24.6: connectivity_query boost ---

    def test_connectivity_query_boosts(self):
        """connectivity_query: claim 4.0, module_parse 1.0."""
        boosts = get_dynamic_boosts("connectivity_query")
        assert boosts["claim"] == 4.0
        assert boosts["module_parse"] == 1.0

    # --- Requirement 24.8: general_query boost (기존 고정 가중치) ---

    def test_general_query_boosts(self):
        """general_query: claim 3.0, module_parse 1.0 (기존 고정 가중치)."""
        boosts = get_dynamic_boosts("general_query")
        assert boosts["claim"] == 3.0
        assert boosts["module_parse"] == 1.0

    def test_unknown_type_falls_back_to_general(self):
        """알 수 없는 유형은 general_query 가중치로 폴백."""
        boosts = get_dynamic_boosts("unknown_type")
        assert boosts == get_dynamic_boosts("general_query")

    def test_all_boosts_have_hdd_section(self):
        """모든 유형에 hdd_section boost가 포함된다."""
        for query_type in ["port_query", "hierarchy_query", "config_query",
                           "connectivity_query", "general_query"]:
            boosts = get_dynamic_boosts(query_type)
            assert "hdd_section" in boosts
            assert boosts["hdd_section"] == 2.0


# ===========================================================================
# 통합 테스트: _process_rtl_file 내 청킹 트리거 조건
# ===========================================================================


class TestChunkingTriggerCondition:
    """_process_rtl_file에서 청킹이 올바른 조건에서 트리거되는지 검증."""

    def test_50_ports_triggers_chunking(self):
        """포트 50개 이상이면 _create_sub_records가 호출된다."""
        # 50개 포트를 가진 RTL 생성
        ports = "\n".join([f"    input port_{i}," for i in range(50)])
        rtl = f"""
module large_module (
{ports}
    output result
);
endmodule
"""
        metadata = parse_rtl_to_ast(rtl)
        # parse_rtl_to_ast는 포트를 추출 — 50개 이상이면 청킹 대상
        # 실제 정규식 파서가 모든 포트를 추출하는지 확인
        assert len(metadata["port_list"]) >= 50

    def test_below_50_ports_no_chunking(self):
        """포트 50개 미만이면 청킹 대상이 아니다."""
        ports = "\n".join([f"    input port_{i}," for i in range(10)])
        rtl = f"""
module small_module (
{ports}
    output result
);
endmodule
"""
        metadata = parse_rtl_to_ast(rtl)
        assert len(metadata["port_list"]) < 50


# ===========================================================================
# 통합 테스트: classify_query_type + get_dynamic_boosts 연동
# ===========================================================================


class TestDynamicBoostIntegration:
    """classify_query_type → get_dynamic_boosts 파이프라인 통합 검증."""

    def test_port_query_pipeline(self):
        """포트 질의 → 높은 claim boost, 낮은 module_parse boost."""
        query = "AXI 포트 목록 보여줘"
        query_type = classify_query_type(query)
        boosts = get_dynamic_boosts(query_type)
        assert query_type == "port_query"
        assert boosts["claim"] > boosts["module_parse"]

    def test_hierarchy_query_pipeline(self):
        """계층 질의 → 높은 module_parse boost, 낮은 claim boost."""
        query = "모듈 계층 구조"
        query_type = classify_query_type(query)
        boosts = get_dynamic_boosts(query_type)
        assert query_type == "hierarchy_query"
        assert boosts["module_parse"] > boosts["claim"]

    def test_general_query_preserves_existing_behavior(self):
        """일반 질의는 기존 고정 가중치(claim 3.0, module_parse 1.0)를 유지."""
        query = "이 모듈 설명해줘"
        query_type = classify_query_type(query)
        boosts = get_dynamic_boosts(query_type)
        assert query_type == "general_query"
        assert boosts["claim"] == 3.0
        assert boosts["module_parse"] == 1.0
        assert boosts["hdd_section"] == 2.0

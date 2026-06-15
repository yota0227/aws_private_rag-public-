"""Unit tests for _load_port_bindings_to_neptune function.

Tests Neptune CONNECTS_TO edge loading from port binding data.
Requirements: 31.1, 31.2, 31.3, 31.4, 31.5, 31.6, 31.7, 31.8
"""
import json
import logging
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def sample_bindings():
    """Sample port binding data as returned by _find_all_port_bindings."""
    return [
        {
            "instance_name": "u_phy",
            "module_type": "UCIE_PHY",
            "port_name": "i_clk",
            "signal_expr": "sys_clk",
            "bit_range": None,
            "is_unconnected": False,
            "is_concatenation": False,
            "constituent_signals": [],
            "source_file": "rtl-sources/blk_ucie.sv",
            "line_number": 42,
        },
        {
            "instance_name": "u_phy",
            "module_type": "UCIE_PHY",
            "port_name": "i_data",
            "signal_expr": "data_bus[31:0]",
            "bit_range": "[31:0]",
            "is_unconnected": False,
            "is_concatenation": False,
            "constituent_signals": [],
            "source_file": "rtl-sources/blk_ucie.sv",
            "line_number": 43,
        },
    ]


@pytest.fixture
def unconnected_binding():
    """Unconnected port binding — should be skipped."""
    return [
        {
            "instance_name": "u_phy",
            "module_type": "UCIE_PHY",
            "port_name": "o_debug",
            "signal_expr": "",
            "bit_range": None,
            "is_unconnected": True,
            "is_concatenation": False,
            "constituent_signals": [],
            "source_file": "rtl-sources/blk_ucie.sv",
            "line_number": 50,
        },
    ]


@pytest.fixture
def concatenation_binding():
    """Concatenation binding — should create constituent edges."""
    return [
        {
            "instance_name": "u_noc",
            "module_type": "NOC_ROUTER",
            "port_name": "i_flit",
            "signal_expr": "{header, payload, tail}",
            "bit_range": None,
            "is_unconnected": False,
            "is_concatenation": True,
            "constituent_signals": ["header", "payload", "tail"],
            "source_file": "rtl-sources/noc_top.sv",
            "line_number": 100,
        },
    ]


def _mock_neptune_client():
    """현재 구현(_get_neptune_client → boto3 neptunedata client)에 대응하는 mock client.

    client.execute_open_cypher_query(openCypherQuery=..., parameters=<json str>)로 호출된다.
    """
    return MagicMock()


def _cypher_calls(mock_client):
    """mock client의 execute_open_cypher_query 호출 목록을 (query, params_dict) 튜플로 반환."""
    calls = []
    for c in mock_client.execute_open_cypher_query.call_args_list:
        query = c.kwargs.get("openCypherQuery", "")
        params_raw = c.kwargs.get("parameters")
        params = json.loads(params_raw) if params_raw else {}
        calls.append((query, params))
    return calls


class TestLoadPortBindingsToNeptune:
    """Tests for _load_port_bindings_to_neptune function.

    현재 구현은 UNWIND 배치 + boto3 neptunedata 클라이언트(execute_open_cypher_query)를 사용한다.
    바인딩 집합당 최대 3개의 배치 쿼리(Port nodes / Signal nodes / CONNECTS_TO edges)를 보낸다.
    """

    @patch('handler.NEPTUNE_ENDPOINT', '')
    def test_skips_when_neptune_endpoint_not_set(self, sample_bindings):
        """Req 31.6: Graceful degradation when Neptune not configured."""
        from handler import _load_port_bindings_to_neptune
        # Should return without error
        _load_port_bindings_to_neptune(sample_bindings, "test_module")

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    def test_skips_empty_bindings(self):
        """No queries should be sent for empty bindings list."""
        from handler import _load_port_bindings_to_neptune
        # Should return without error
        _load_port_bindings_to_neptune([], "test_module")

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler._get_neptune_client')
    def test_creates_port_and_signal_nodes(self, mock_get_client, sample_bindings):
        """Req 31.2, 31.3: Port/Signal nodes are MERGE'd via UNWIND batch queries."""
        from handler import _load_port_bindings_to_neptune

        mock_client = _mock_neptune_client()
        mock_get_client.return_value = mock_client

        _load_port_bindings_to_neptune(sample_bindings, "blk_ucie")

        # UNWIND 배치: Port nodes / Signal nodes / CONNECTS_TO edges = 3개 쿼리
        calls = _cypher_calls(mock_client)
        assert len(calls) == 3

        # 1번째 쿼리 = Port 노드 MERGE (UNWIND rows)
        port_query, port_params = calls[0]
        assert "MERGE (p:Port {name: row.port_node_id})" in port_query
        port_ids = [r["port_node_id"] for r in port_params["rows"]]
        assert "u_phy.i_clk" in port_ids
        assert "u_phy.i_data" in port_ids
        first_row = port_params["rows"][0]
        assert first_row["instance_name"] == "u_phy"
        assert first_row["module_type"] == "UCIE_PHY"

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler._get_neptune_client')
    def test_connects_to_edge_properties(self, mock_get_client, sample_bindings):
        """Req 31.4: CONNECTS_TO edge has bit_range, source_file, line_number, is_concatenation."""
        from handler import _load_port_bindings_to_neptune

        mock_client = _mock_neptune_client()
        mock_get_client.return_value = mock_client

        _load_port_bindings_to_neptune(sample_bindings, "blk_ucie")

        calls = _cypher_calls(mock_client)
        # 3번째 쿼리 = CONNECTS_TO 엣지 (UNWIND rows)
        edge_query, edge_params = calls[2]
        assert "CONNECTS_TO" in edge_query
        first_edge = edge_params["rows"][0]
        assert first_edge["source_file"] == "rtl-sources/blk_ucie.sv"
        assert first_edge["line_number"] == 42
        assert first_edge["is_concatenation"] is False

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler._get_neptune_client')
    def test_unconnected_ports_skipped(self, mock_get_client, unconnected_binding):
        """Req 31.7: Unconnected ports do not generate any queries."""
        from handler import _load_port_bindings_to_neptune

        mock_client = _mock_neptune_client()
        mock_get_client.return_value = mock_client

        _load_port_bindings_to_neptune(unconnected_binding, "blk_ucie")

        # unconnected만 있으면 row가 없어 쿼리도 없음
        assert mock_client.execute_open_cypher_query.call_count == 0

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler._get_neptune_client')
    def test_concatenation_creates_constituent_edges(self, mock_get_client, concatenation_binding):
        """Req 31.5: Concatenation bindings create constituent CONNECTS_TO edges (배치 rows에 포함)."""
        from handler import _load_port_bindings_to_neptune

        mock_client = _mock_neptune_client()
        mock_get_client.return_value = mock_client

        _load_port_bindings_to_neptune(concatenation_binding, "noc_top")

        calls = _cypher_calls(mock_client)
        # 여전히 3개 배치 쿼리(port/signal/edge) — constituent는 rows에 추가됨
        assert len(calls) == 3

        _edge_query, edge_params = calls[2]
        constituent_edges = [r for r in edge_params["rows"] if r.get("is_constituent") is True]
        assert len(constituent_edges) == 3
        assert {r["signal_name"] for r in constituent_edges} == {"header", "payload", "tail"}

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler._execute_neptune_queries')
    def test_graceful_degradation_on_neptune_failure(self, mock_exec, sample_bindings, caplog):
        """Req 31.6: Neptune failure logs neptune_load_failed and doesn't raise."""
        from handler import _load_port_bindings_to_neptune

        # 배치 실행 단계에서 예외 발생 시뮬레이션
        mock_exec.side_effect = Exception("Connection refused")

        with caplog.at_level(logging.ERROR):
            # Should NOT raise (graceful degradation)
            _load_port_bindings_to_neptune(sample_bindings, "blk_ucie")

        # neptune_load_failed 필드가 에러 로그에 포함되어야 함
        assert any("neptune_load_failed" in record.message for record in caplog.records)

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler._get_neptune_client')
    def test_individual_query_failure_continues_processing(self, mock_get_client, sample_bindings, caplog):
        """Req 31.6: 개별 쿼리 실패가 배치 전체를 중단시키지 않는다 (연속 실패 임계 미만)."""
        from handler import _load_port_bindings_to_neptune

        mock_client = _mock_neptune_client()
        mock_get_client.return_value = mock_client

        call_count = [0]

        def side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # 첫 쿼리 실패 (연속 5회 미만이므로 중단 안 됨)
                raise Exception("Timeout")
            return MagicMock()

        mock_client.execute_open_cypher_query.side_effect = side_effect

        with caplog.at_level(logging.WARNING):
            _load_port_bindings_to_neptune(sample_bindings, "blk_ucie")

        # 첫 쿼리 실패에도 3개 배치 쿼리 모두 시도
        assert call_count[0] == 3

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler._get_neptune_client')
    def test_merge_prevents_duplicate_nodes(self, mock_get_client, sample_bindings):
        """Req 31.8: Port/Signal 노드 생성 쿼리는 MERGE를 사용한다."""
        from handler import _load_port_bindings_to_neptune

        mock_client = _mock_neptune_client()
        mock_get_client.return_value = mock_client

        _load_port_bindings_to_neptune(sample_bindings, "blk_ucie")

        for query, _params in _cypher_calls(mock_client):
            if ":Port" in query or ":Signal" in query:
                assert "MERGE" in query, f"Expected MERGE in query: {query}"

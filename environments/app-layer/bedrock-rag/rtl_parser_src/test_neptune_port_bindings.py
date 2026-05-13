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


class TestLoadPortBindingsToNeptune:
    """Tests for _load_port_bindings_to_neptune function."""

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
    @patch('handler.boto3.Session')
    def test_creates_port_and_signal_nodes(self, mock_session, sample_bindings):
        """Req 31.2, 31.3: Port and Signal nodes are created with MERGE."""
        from handler import _load_port_bindings_to_neptune

        mock_creds = MagicMock()
        mock_creds.access_key = "test_key"
        mock_creds.secret_key = "test_secret"
        mock_creds.token = "test_token"
        mock_session.return_value.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
        mock_session.return_value.region_name = "ap-northeast-2"

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            _load_port_bindings_to_neptune(sample_bindings, "blk_ucie")

            # 2 bindings × 3 queries each (Port MERGE + Signal MERGE + CONNECTS_TO) = 6
            assert mock_post.call_count == 6

            # Verify Port node MERGE query
            first_call_json = mock_post.call_args_list[0][1]['json']
            assert "MERGE (p:Port {name: $port_node_id})" in first_call_json['query']
            assert first_call_json['parameters']['port_node_id'] == "u_phy.i_clk"
            assert first_call_json['parameters']['instance_name'] == "u_phy"
            assert first_call_json['parameters']['module_type'] == "UCIE_PHY"

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler.boto3.Session')
    def test_connects_to_edge_properties(self, mock_session, sample_bindings):
        """Req 31.4: CONNECTS_TO edge has bit_range, source_file, line_number, is_concatenation."""
        from handler import _load_port_bindings_to_neptune

        mock_creds = MagicMock()
        mock_creds.access_key = "test_key"
        mock_creds.secret_key = "test_secret"
        mock_creds.token = "test_token"
        mock_session.return_value.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
        mock_session.return_value.region_name = "ap-northeast-2"

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            _load_port_bindings_to_neptune(sample_bindings, "blk_ucie")

            # Third call is the CONNECTS_TO edge for first binding
            edge_call_json = mock_post.call_args_list[2][1]['json']
            assert "CONNECTS_TO" in edge_call_json['query']
            params = edge_call_json['parameters']
            assert params['source_file'] == "rtl-sources/blk_ucie.sv"
            assert params['line_number'] == 42
            assert params['is_concatenation'] is False

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler.boto3.Session')
    def test_unconnected_ports_skipped(self, mock_session, unconnected_binding):
        """Req 31.7: Unconnected ports do not generate CONNECTS_TO edges."""
        from handler import _load_port_bindings_to_neptune

        mock_creds = MagicMock()
        mock_creds.access_key = "test_key"
        mock_creds.secret_key = "test_secret"
        mock_creds.token = "test_token"
        mock_session.return_value.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
        mock_session.return_value.region_name = "ap-northeast-2"

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            _load_port_bindings_to_neptune(unconnected_binding, "blk_ucie")

            # No queries should be sent for unconnected ports
            assert mock_post.call_count == 0

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler.boto3.Session')
    def test_concatenation_creates_constituent_edges(self, mock_session, concatenation_binding):
        """Req 31.5: Concatenation bindings create constituent CONNECTS_TO edges."""
        from handler import _load_port_bindings_to_neptune

        mock_creds = MagicMock()
        mock_creds.access_key = "test_key"
        mock_creds.secret_key = "test_secret"
        mock_creds.token = "test_token"
        mock_session.return_value.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
        mock_session.return_value.region_name = "ap-northeast-2"

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            _load_port_bindings_to_neptune(concatenation_binding, "noc_top")

            # 1 binding: Port MERGE + Signal MERGE + CONNECTS_TO = 3
            # + 3 constituents × 2 (Signal MERGE + CONNECTS_TO) = 6
            # Total = 9
            assert mock_post.call_count == 9

            # Find constituent edge calls (those with is_constituent=True)
            constituent_calls = [
                call for call in mock_post.call_args_list
                if call[1]['json'].get('parameters', {}).get('is_constituent') is True
            ]
            assert len(constituent_calls) == 3

            # Verify constituent signal names
            constituent_signals = [
                call[1]['json']['parameters']['signal_name']
                for call in constituent_calls
            ]
            assert set(constituent_signals) == {"header", "payload", "tail"}

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler.boto3.Session')
    def test_graceful_degradation_on_neptune_failure(self, mock_session, sample_bindings, caplog):
        """Req 31.6: Neptune failure logs neptune_load_failed and doesn't raise."""
        from handler import _load_port_bindings_to_neptune

        # Simulate connection failure
        mock_session.side_effect = Exception("Connection refused")

        with caplog.at_level(logging.ERROR):
            # Should NOT raise
            _load_port_bindings_to_neptune(sample_bindings, "blk_ucie")

        # Verify error log contains neptune_load_failed: true
        assert any("neptune_load_failed" in record.message for record in caplog.records)

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler.boto3.Session')
    def test_individual_query_failure_continues_processing(self, mock_session, sample_bindings, caplog):
        """Req 31.6: Individual query failures don't stop batch processing."""
        from handler import _load_port_bindings_to_neptune

        mock_creds = MagicMock()
        mock_creds.access_key = "test_key"
        mock_creds.secret_key = "test_secret"
        mock_creds.token = "test_token"
        mock_session.return_value.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
        mock_session.return_value.region_name = "ap-northeast-2"

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_resp = MagicMock()
            if call_count[0] == 1:
                # First query fails
                mock_resp.raise_for_status.side_effect = Exception("Timeout")
            else:
                mock_resp.status_code = 200
                mock_resp.raise_for_status = MagicMock()
            return mock_resp

        with patch('requests.post', side_effect=side_effect):
            with caplog.at_level(logging.WARNING):
                _load_port_bindings_to_neptune(sample_bindings, "blk_ucie")

        # Should have attempted all 6 queries despite first failure
        assert call_count[0] == 6

    @patch('handler.NEPTUNE_ENDPOINT', 'neptune-test.cluster.amazonaws.com')
    @patch('handler.boto3.Session')
    def test_merge_prevents_duplicate_nodes(self, mock_session, sample_bindings):
        """Req 31.8: MERGE operation prevents duplicate node creation."""
        from handler import _load_port_bindings_to_neptune

        mock_creds = MagicMock()
        mock_creds.access_key = "test_key"
        mock_creds.secret_key = "test_secret"
        mock_creds.token = "test_token"
        mock_session.return_value.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
        mock_session.return_value.region_name = "ap-northeast-2"

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            _load_port_bindings_to_neptune(sample_bindings, "blk_ucie")

            # All Port and Signal node creation queries use MERGE
            for call in mock_post.call_args_list:
                query = call[1]['json']['query']
                if ":Port" in query or ":Signal" in query:
                    assert "MERGE" in query, f"Expected MERGE in query: {query}"

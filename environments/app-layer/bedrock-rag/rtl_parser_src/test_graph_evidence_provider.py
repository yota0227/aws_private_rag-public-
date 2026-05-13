"""
Tests for graph_evidence_provider.py

Validates:
- GraphEvidenceProvider class instantiation
- Graceful degradation when Neptune is not available (claim-only mode)
- Method signatures and return types
- Evidence formatting for HDD prompt injection

Requirements: 13.2, 13.3
"""
import json
import os
import unittest
from unittest.mock import patch, MagicMock

from graph_evidence_provider import (
    GraphEvidenceProvider,
    _NeptuneSigV4Client,
    _RagApiClient,
)


class TestGraphEvidenceProviderInit(unittest.TestCase):
    """Test GraphEvidenceProvider initialization."""

    def test_init_no_endpoint(self):
        """Provider initializes without Neptune endpoint (claim-only mode)."""
        with patch.dict(os.environ, {}, clear=True):
            provider = GraphEvidenceProvider(neptune_endpoint="", rag_api_url="")
            self.assertFalse(provider.neptune_available)

    def test_init_with_endpoint_env(self):
        """Provider reads endpoint from environment variable."""
        with patch.dict(os.environ, {"NEPTUNE_ENDPOINT": "test-cluster.neptune.amazonaws.com"}):
            provider = GraphEvidenceProvider()
            self.assertEqual(provider._neptune_endpoint, "test-cluster.neptune.amazonaws.com")

    def test_init_with_explicit_endpoint(self):
        """Provider uses explicitly provided endpoint over env."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="explicit.neptune.amazonaws.com",
            rag_api_url="https://api.example.com",
            region="us-east-1",
        )
        self.assertEqual(provider._neptune_endpoint, "explicit.neptune.amazonaws.com")
        self.assertEqual(provider._rag_api_url, "https://api.example.com")
        self.assertEqual(provider._region, "us-east-1")


class TestGracefulDegradation(unittest.TestCase):
    """Test graceful degradation when Neptune is not available."""

    def setUp(self):
        """Create provider with no Neptune endpoint (claim-only mode)."""
        self.provider = GraphEvidenceProvider(neptune_endpoint="", rag_api_url="")

    def test_neptune_available_false_when_no_endpoint(self):
        """neptune_available returns False when endpoint is empty."""
        self.assertFalse(self.provider.neptune_available)

    def test_get_section_evidence_returns_empty_dict(self):
        """get_section_evidence returns empty dict in claim-only mode."""
        result = self.provider.get_section_evidence("NoC", "trinity_top")
        self.assertEqual(result, {})

    def test_get_connectivity_path_returns_empty_list(self):
        """get_connectivity_path returns empty list in claim-only mode."""
        result = self.provider.get_connectivity_path(
            "flit_out_req[1][4]", "flit_in_req[2][4]"
        )
        self.assertEqual(result, [])

    def test_get_hierarchy_tree_returns_empty_dict(self):
        """get_hierarchy_tree returns empty dict in claim-only mode."""
        result = self.provider.get_hierarchy_tree("trinity_top", depth=3)
        self.assertEqual(result, {})

    def test_get_instance_params_returns_empty_dict(self):
        """get_instance_params returns empty dict in claim-only mode."""
        result = self.provider.get_instance_params(
            "trinity_top/gen_noc/u_repeater_stage_0"
        )
        self.assertEqual(result, {})

    def test_format_evidence_for_prompt_returns_empty_string(self):
        """format_evidence_for_prompt returns empty string in claim-only mode."""
        result = self.provider.format_evidence_for_prompt("NoC", "trinity_top")
        self.assertEqual(result, "")


class TestNeptuneAvailabilityCheck(unittest.TestCase):
    """Test Neptune availability checking logic."""

    def test_availability_cached_after_first_check(self):
        """neptune_available result is cached after first check."""
        provider = GraphEvidenceProvider(neptune_endpoint="", rag_api_url="")
        # First call sets the cache
        self.assertFalse(provider.neptune_available)
        # Verify it's cached (internal state)
        self.assertFalse(provider._neptune_available)

    @patch("graph_evidence_provider._NeptuneSigV4Client")
    def test_availability_true_when_health_check_passes(self, mock_client_cls):
        """neptune_available returns True when health check succeeds."""
        mock_instance = MagicMock()
        mock_instance.health_check.return_value = True
        mock_client_cls.return_value = mock_instance

        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        # Inject the mock client
        provider._neptune_client = mock_instance

        result = provider.neptune_available
        self.assertTrue(result)

    @patch("graph_evidence_provider._NeptuneSigV4Client")
    def test_availability_false_when_health_check_fails(self, mock_client_cls):
        """neptune_available returns False when health check fails."""
        mock_instance = MagicMock()
        mock_instance.health_check.return_value = False
        mock_client_cls.return_value = mock_instance

        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        provider._neptune_client = mock_instance

        result = provider.neptune_available
        self.assertFalse(result)

    @patch("graph_evidence_provider._NeptuneSigV4Client")
    def test_availability_false_on_exception(self, mock_client_cls):
        """neptune_available returns False when health check raises exception."""
        mock_instance = MagicMock()
        mock_instance.health_check.side_effect = Exception("Connection refused")
        mock_client_cls.return_value = mock_instance

        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        provider._neptune_client = mock_instance

        result = provider.neptune_available
        self.assertFalse(result)


class TestGetSectionEvidence(unittest.TestCase):
    """Test get_section_evidence with mocked Neptune."""

    def _make_provider_with_mock(self, query_result):
        """Create a provider with a mocked Neptune client."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_client.execute_query.return_value = query_result
        provider._neptune_client = mock_client
        provider._neptune_available = True
        return provider

    def test_returns_nodes_and_edges(self):
        """get_section_evidence returns structured evidence dict."""
        query_result = {
            "results": [{
                "module": "trinity_top",
                "instances": ["u_router", "u_repeater"],
                "bindings": [
                    {"port": "flit_out", "signal": "flit_net", "direction": "output"},
                    {"port": "flit_in", "signal": "flit_net", "direction": "input"},
                ],
            }]
        }
        provider = self._make_provider_with_mock(query_result)

        result = provider.get_section_evidence("NoC", "trinity_top")

        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertIn("summary", result)
        self.assertEqual(len(result["nodes"]), 2)
        self.assertEqual(len(result["edges"]), 2)
        self.assertIn("trinity_top", result["summary"])

    def test_returns_empty_on_exception(self):
        """get_section_evidence returns empty dict on query failure."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_client.execute_query.side_effect = Exception("Query timeout")
        provider._neptune_client = mock_client
        provider._neptune_available = True

        result = provider.get_section_evidence("NoC", "trinity_top")
        self.assertEqual(result, {})


class TestGetConnectivityPath(unittest.TestCase):
    """Test get_connectivity_path with mocked Neptune/API."""

    def test_returns_paths_from_neptune(self):
        """get_connectivity_path returns path list from Neptune query."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_client.execute_query.return_value = {
            "results": [{
                "path_nodes": [
                    {"name": "flit_out_req", "type": "PortInstance"},
                    {"name": "flit_net", "type": "Signal"},
                    {"name": "flit_in_req", "type": "PortInstance"},
                ],
                "path_edges": ["BINDS_TO", "READS"],
            }]
        }
        provider._neptune_client = mock_client
        provider._neptune_available = True

        result = provider.get_connectivity_path("flit_out_req", "flit_in_req")

        self.assertEqual(len(result), 1)
        self.assertIn("nodes", result[0])
        self.assertIn("edges", result[0])
        self.assertEqual(len(result[0]["nodes"]), 3)

    def test_returns_empty_list_on_failure(self):
        """get_connectivity_path returns empty list on exception."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_client.execute_query.side_effect = Exception("Timeout")
        provider._neptune_client = mock_client
        provider._neptune_available = True

        result = provider.get_connectivity_path("port_a", "port_b")
        self.assertEqual(result, [])


class TestGetHierarchyTree(unittest.TestCase):
    """Test get_hierarchy_tree with mocked Neptune/API."""

    def test_returns_hierarchy_from_neptune(self):
        """get_hierarchy_tree returns hierarchy dict from Neptune."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_client.execute_query.return_value = {
            "results": [
                {"root": "trinity_top", "hierarchy": ["trinity_top", "u_router"], "depth": 1},
                {"root": "trinity_top", "hierarchy": ["trinity_top", "u_router", "u_arb"], "depth": 2},
            ]
        }
        provider._neptune_client = mock_client
        provider._neptune_available = True

        result = provider.get_hierarchy_tree("trinity_top", depth=3)

        self.assertEqual(result["root"], "trinity_top")
        self.assertEqual(result["depth"], 3)
        self.assertEqual(len(result["children"]), 2)

    def test_depth_clamped_to_range(self):
        """get_hierarchy_tree clamps depth to [1, 10]."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_client.execute_query.return_value = {"results": []}
        provider._neptune_client = mock_client
        provider._neptune_available = True

        # depth=0 should be clamped to 1
        result = provider.get_hierarchy_tree("mod", depth=0)
        self.assertEqual(result["depth"], 1)

        # depth=20 should be clamped to 10
        result = provider.get_hierarchy_tree("mod", depth=20)
        self.assertEqual(result["depth"], 10)


class TestGetInstanceParams(unittest.TestCase):
    """Test get_instance_params with mocked Neptune."""

    def test_returns_params_from_json_string(self):
        """get_instance_params parses JSON string param_overrides."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_client.execute_query.return_value = {
            "results": [{
                "instance_name": "u_repeater_stage_0",
                "param_overrides": json.dumps({"NUM_REPEATERS": "4", "DEPTH": "8"}),
            }]
        }
        provider._neptune_client = mock_client
        provider._neptune_available = True

        result = provider.get_instance_params(
            "trinity_top/gen_noc/u_repeater_stage_0"
        )
        self.assertEqual(result, {"NUM_REPEATERS": "4", "DEPTH": "8"})

    def test_returns_params_from_dict(self):
        """get_instance_params handles dict param_overrides directly."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_client.execute_query.return_value = {
            "results": [{
                "instance_name": "u_repeater",
                "param_overrides": {"WIDTH": "32"},
            }]
        }
        provider._neptune_client = mock_client
        provider._neptune_available = True

        result = provider.get_instance_params("top/u_repeater")
        self.assertEqual(result, {"WIDTH": "32"})

    def test_returns_empty_when_no_results(self):
        """get_instance_params returns empty dict when instance not found."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_client.execute_query.return_value = {"results": []}
        provider._neptune_client = mock_client
        provider._neptune_available = True

        result = provider.get_instance_params("nonexistent/path")
        self.assertEqual(result, {})

    def test_returns_empty_on_invalid_json(self):
        """get_instance_params returns empty dict on invalid JSON."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_client.execute_query.return_value = {
            "results": [{
                "instance_name": "u_inst",
                "param_overrides": "not-valid-json{",
            }]
        }
        provider._neptune_client = mock_client
        provider._neptune_available = True

        result = provider.get_instance_params("top/u_inst")
        self.assertEqual(result, {})


class TestFormatEvidenceForPrompt(unittest.TestCase):
    """Test format_evidence_for_prompt output formatting."""

    def test_returns_empty_when_neptune_unavailable(self):
        """format_evidence_for_prompt returns empty string without Neptune."""
        provider = GraphEvidenceProvider(neptune_endpoint="", rag_api_url="")
        result = provider.format_evidence_for_prompt("NoC", "trinity_top")
        self.assertEqual(result, "")

    def test_formats_evidence_with_header(self):
        """format_evidence_for_prompt includes [GRAPH EVIDENCE] header."""
        provider = GraphEvidenceProvider(
            neptune_endpoint="test.neptune.amazonaws.com"
        )
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        # Mock get_section_evidence query
        mock_client.execute_query.return_value = {
            "results": [{
                "module": "trinity_top",
                "instances": ["u_router"],
                "bindings": [
                    {"port": "clk", "signal": "sys_clk", "direction": "input"},
                ],
            }]
        }
        provider._neptune_client = mock_client
        provider._neptune_available = True

        result = provider.format_evidence_for_prompt("NoC", "trinity_top")

        self.assertIn("[GRAPH EVIDENCE — NoC Section]", result)
        self.assertIn("Summary:", result)


class TestNeptuneSigV4Client(unittest.TestCase):
    """Test _NeptuneSigV4Client construction."""

    @patch("graph_evidence_provider.boto3.Session")
    def test_client_construction(self, mock_session_cls):
        """_NeptuneSigV4Client initializes with endpoint and region."""
        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
        mock_session.region_name = "ap-northeast-2"
        mock_session_cls.return_value = mock_session

        client = _NeptuneSigV4Client("test.neptune.amazonaws.com", region="us-east-1")

        self.assertEqual(client.endpoint, "test.neptune.amazonaws.com")
        self.assertEqual(client.region, "us-east-1")
        self.assertIn("8182", client.neptune_url)


class TestRagApiClient(unittest.TestCase):
    """Test _RagApiClient construction."""

    @patch("graph_evidence_provider.boto3.Session")
    def test_client_construction(self, mock_session_cls):
        """_RagApiClient initializes with API URL and region."""
        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
        mock_session.region_name = "ap-northeast-2"
        mock_session_cls.return_value = mock_session

        client = _RagApiClient("https://api.example.com/", region="us-east-1")

        self.assertEqual(client.api_url, "https://api.example.com")
        self.assertEqual(client.region, "us-east-1")


if __name__ == "__main__":
    unittest.main()

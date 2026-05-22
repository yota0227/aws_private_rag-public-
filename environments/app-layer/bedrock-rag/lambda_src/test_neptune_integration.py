"""
Integration test — Neptune ingestion end-to-end (Task 13.2)

Tests the full pipeline with mocked external services:
1. DynamoDB → neptune_ingestion.py → Graph Export API verification
2. Graph evidence provider → HDD evidence injection
3. Interactive Schematic graph data loading (JSON structure validation)

Requirements: 13.1, 13.4, 13.5
"""
import json
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# Add source directories to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rtl_parser_src"))

from neptune_ingestion import (
    transform_records_to_nodes,
    transform_records_to_edges,
    build_merge_query,
    build_edge_merge_query,
    _call_graph_export_api,
    verify_graph_export,
    GraphExportVerificationResult,
    NeptuneSigV4Client,
)


# ---------------------------------------------------------------------------
# Test fixtures — sample DynamoDB records
# ---------------------------------------------------------------------------

PIPELINE_ID = "tt_test_20260301"


def _sample_module_parse_records():
    """Sample module_parse records as they would come from DynamoDB scan."""
    return [
        {
            "claim_id": "mp_trinity_top",
            "analysis_type": "module_parse",
            "module_name": "trinity_top",
            "file_path": "rtl/trinity_top.sv",
            "pipeline_id": PIPELINE_ID,
            "module_type": "top",
            "port_list": [
                {"name": "clk", "direction": "input", "bit_width": "1"},
                {"name": "rst_n", "direction": "input", "bit_width": "1"},
                {"name": "flit_out", "direction": "output", "bit_width": "128"},
            ],
            "instance_list": [
                {"instance_name": "u_router", "module_type": "trinity_router", "hier_path": "trinity_top/u_router"},
                {"instance_name": "u_noc2axi", "module_type": "trinity_noc2axi", "hier_path": "trinity_top/u_noc2axi"},
            ],
        },
        {
            "claim_id": "mp_trinity_router",
            "analysis_type": "module_parse",
            "module_name": "trinity_router",
            "file_path": "rtl/trinity_router.sv",
            "pipeline_id": PIPELINE_ID,
            "module_type": "module",
            "port_list": [
                {"name": "i_flit", "direction": "input", "bit_width": "128"},
                {"name": "o_flit", "direction": "output", "bit_width": "128"},
            ],
            "instance_list": ["u_repeater_stage_0"],
        },
    ]


def _sample_claim_records():
    """Sample claim records (PortBinding, WireTopology, ClockDomain)."""
    return [
        {
            "claim_id": "claim_port_binding_001",
            "analysis_type": "claim",
            "topic": "PortBinding",
            "module_name": "trinity_top",
            "pipeline_id": PIPELINE_ID,
            "port_name": "flit_out",
            "signal_name": "flit_out_wire",
            "signal_expr": "flit_out_wire",
            "expression_type": "simple",
            "direction": "output",
        },
        {
            "claim_id": "claim_wire_001",
            "analysis_type": "claim",
            "topic": "WireTopology",
            "module_name": "trinity_top",
            "pipeline_id": PIPELINE_ID,
            "signal_name": "flit_out_wire",
            "dimensions": "[127:0]",
            "claim_text": "Wire 'flit_out_wire' is a 128-bit internal net",
        },
        {
            "claim_id": "claim_clock_001",
            "analysis_type": "claim",
            "topic": "ClockDomain",
            "module_name": "trinity_top",
            "pipeline_id": PIPELINE_ID,
            "signal_name": "clk",
            "clock_domain": "core_clk",
        },
    ]


def _all_sample_records():
    return _sample_module_parse_records() + _sample_claim_records()


# ---------------------------------------------------------------------------
# Test 1: DynamoDB → neptune_ingestion → Graph Export API verification
# ---------------------------------------------------------------------------

class TestNeptuneIngestionEndToEnd:
    """Integration test: DynamoDB scan → transform → Graph Export API."""

    def test_transform_produces_correct_node_counts(self):
        """Verify transform from DynamoDB records produces expected node types and counts."""
        records = _all_sample_records()
        nodes = transform_records_to_nodes(records)

        # Count by label
        label_counts = {}
        for n in nodes:
            label_counts[n["label"]] = label_counts.get(n["label"], 0) + 1

        # trinity_top + trinity_router = 2 ModuleDef nodes
        assert label_counts.get("ModuleDef", 0) == 2
        # u_router, u_noc2axi, u_repeater_stage_0 = 3 Instance nodes
        assert label_counts.get("Instance", 0) == 3
        # trinity_top has 3 ports, trinity_router has 2 ports → 5 PortDef
        assert label_counts.get("PortDef", 0) == 5
        # PortInstance for each port in port dicts
        assert label_counts.get("PortInstance", 0) == 5
        # 1 WireTopology claim → 1 Signal node
        assert label_counts.get("Signal", 0) == 1
        # 1 ClockDomain claim → 1 ClockDomain node
        assert label_counts.get("ClockDomain", 0) == 1

    def test_transform_produces_correct_edge_types(self):
        """Verify edge transformation generates expected relationship types."""
        records = _all_sample_records()
        nodes = transform_records_to_nodes(records)
        edges = transform_records_to_edges(records, nodes)

        edge_type_counts = {}
        for e in edges:
            edge_type_counts[e["type"]] = edge_type_counts.get(e["type"], 0) + 1

        # DEFINES: 5 ports across 2 modules
        assert edge_type_counts.get("DEFINES", 0) == 5
        # INSTANCE_OF: 3 instances (u_router, u_noc2axi from dicts + u_repeater_stage_0 from str)
        assert edge_type_counts.get("INSTANCE_OF", 0) == 3
        # BINDS_TO: 1 PortBinding claim
        assert edge_type_counts.get("BINDS_TO", 0) == 1
        # DRIVES: 1 output port binding
        assert edge_type_counts.get("DRIVES", 0) == 1
        # BELONGS_TO: 1 ClockDomain claim
        assert edge_type_counts.get("BELONGS_TO", 0) == 1
        # HAS_PORT: same as ports with dict entries (5)
        assert edge_type_counts.get("HAS_PORT", 0) == 5

    def test_graph_export_chip_scope_with_mock_neptune(self):
        """Verify Graph Export API chip scope returns correct node/edge counts."""
        # Mock Neptune client that returns expected data
        mock_client = MagicMock(spec=NeptuneSigV4Client)
        mock_client.execute_query.return_value = {
            "results": [
                {"root_name": "trinity_top", "child_name": "trinity_router", "child_labels": ["ModuleDef"]},
                {"root_name": "trinity_top", "child_name": "trinity_noc2axi", "child_labels": ["ModuleDef"]},
            ]
        }

        result = _call_graph_export_api(mock_client, "chip", "trinity_top")

        assert result["node_count"] == 3  # trinity_top + 2 children
        assert result["edge_count"] == 2  # 2 INSTANTIATES edges
        assert "INSTANTIATES" in result["edge_types"]
        assert result["edge_types"]["INSTANTIATES"] == 2

    def test_graph_export_module_scope_with_mock_neptune(self):
        """Verify Graph Export API module scope returns Port + Signal nodes."""
        mock_client = MagicMock(spec=NeptuneSigV4Client)
        mock_client.execute_query.return_value = {
            "results": [
                {"port_name": "clk", "port_direction": "input", "signal_name": "clk_wire", "rel_type": "BINDS_TO"},
                {"port_name": "rst_n", "port_direction": "input", "signal_name": "rst_wire", "rel_type": "BINDS_TO"},
                {"port_name": "flit_out", "port_direction": "output", "signal_name": "flit_net", "rel_type": "DRIVES"},
            ]
        }

        result = _call_graph_export_api(mock_client, "module", "trinity_top")

        assert result["node_types"]["Port"] == 3
        assert result["node_types"]["Signal"] == 3
        assert result["node_count"] == 6
        assert result["edge_count"] == 3
        assert "BINDS_TO" in result["edge_types"]
        assert "DRIVES" in result["edge_types"]

    def test_verify_graph_export_detects_mismatch(self):
        """Verify that parsing N>0 modules but 0 ingestion nodes triggers error."""
        mock_client = MagicMock(spec=NeptuneSigV4Client)

        result = verify_graph_export(
            client=mock_client,
            pipeline_id=PIPELINE_ID,
            root_module="trinity_top",
            module_parse_count=5,
            total_nodes_created=0,
        )

        assert not result.success
        assert len(result.errors) > 0
        assert "mismatch" in result.errors[0].lower()

    def test_build_merge_queries_are_valid(self):
        """Verify MERGE queries generated for nodes are syntactically valid."""
        records = _all_sample_records()
        nodes = transform_records_to_nodes(records)

        for node in nodes:
            query, params = build_merge_query(node)
            assert "MERGE" in query
            assert node["label"] in query
            # All params should have values
            for k, v in params.items():
                assert v is not None

    def test_build_edge_merge_queries_are_valid(self):
        """Verify MERGE queries generated for edges are syntactically valid."""
        records = _all_sample_records()
        nodes = transform_records_to_nodes(records)
        edges = transform_records_to_edges(records, nodes)

        for edge in edges:
            query, params = build_edge_merge_query(edge)
            assert "MATCH" in query
            assert "MERGE" in query
            assert edge["type"] in query


# ---------------------------------------------------------------------------
# Test 2: Graph Evidence Provider → HDD evidence injection
# ---------------------------------------------------------------------------

class TestGraphEvidenceHDDIntegration:
    """Integration test: graph_evidence_provider → hdd_generator evidence injection."""

    def test_evidence_provider_formats_evidence_for_prompt(self):
        """Verify evidence is formatted correctly for HDD prompt injection."""
        from graph_evidence_provider import GraphEvidenceProvider

        provider = GraphEvidenceProvider(
            neptune_endpoint="mock-endpoint.cluster.neptune.amazonaws.com"
        )

        # Mock Neptune as available and returning data
        provider._neptune_available = True
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = [
            # get_section_evidence query result
            {
                "results": [{
                    "module": "trinity_top",
                    "instances": ["u_router", "u_noc2axi"],
                    "bindings": [
                        {"port": "i_flit", "signal": "flit_wire", "direction": "input"},
                        {"port": "o_flit", "signal": "flit_out_net", "direction": "output"},
                    ],
                }]
            },
            # get_hierarchy_tree query result
            {
                "results": [{
                    "root": "trinity_top",
                    "hierarchy": ["trinity_top", "u_router", "u_repeater"],
                    "depth": 2,
                }]
            },
        ]
        provider._neptune_client = mock_client

        evidence_text = provider.format_evidence_for_prompt("NoC", "trinity_top")

        assert "[GRAPH EVIDENCE" in evidence_text
        assert "NoC" in evidence_text
        assert "trinity_top" in evidence_text
        assert "instances" in evidence_text.lower() or "u_router" in evidence_text

    def test_hdd_prompt_includes_graph_evidence_when_available(self):
        """Verify _build_hdd_prompt injects graph evidence into prompt."""
        from hdd_generator import _build_hdd_prompt
        from graph_evidence_provider import GraphEvidenceProvider

        # Create a mock provider that returns evidence
        mock_provider = MagicMock(spec=GraphEvidenceProvider)
        mock_provider.neptune_available = True
        mock_provider.format_evidence_for_prompt.return_value = (
            "[GRAPH EVIDENCE — NoC Section]\n"
            "- Summary: Module 'trinity_top' has 2 instances with 3 port bindings\n"
            "  - i_flit -> flit_wire (input)\n"
        )

        prompt = _build_hdd_prompt(
            pipeline_id=PIPELINE_ID,
            topic="NoC",
            hdd_type="subsystem",
            hierarchy={"module_name": "trinity_top", "children": []},
            clock_domains=[],
            dataflow=[],
            claims=[{"claim_text": "test claim"}],
            graph_evidence_provider=mock_provider,
        )

        assert "[GRAPH EVIDENCE — NoC Section]" in prompt
        assert "trinity_top" in prompt
        assert "port bindings" in prompt

    def test_hdd_prompt_graceful_degradation_without_neptune(self):
        """Verify _build_hdd_prompt works in claim-only mode when Neptune unavailable."""
        from hdd_generator import _build_hdd_prompt
        from graph_evidence_provider import GraphEvidenceProvider

        # Provider with Neptune unavailable
        mock_provider = MagicMock(spec=GraphEvidenceProvider)
        mock_provider.neptune_available = False
        mock_provider.format_evidence_for_prompt.return_value = ""

        prompt = _build_hdd_prompt(
            pipeline_id=PIPELINE_ID,
            topic="EDC",
            hdd_type="block",
            hierarchy={"module_name": "edc_ring", "children": []},
            clock_domains=[],
            dataflow=[],
            claims=[{"claim_text": "EDC ring claim"}],
            graph_evidence_provider=mock_provider,
        )

        # Prompt should still be generated without graph evidence
        assert "EDC" in prompt
        assert "EDC ring claim" in prompt
        assert "[GRAPH EVIDENCE" not in prompt


# ---------------------------------------------------------------------------
# Test 3: Interactive Schematic graph data loading — JSON structure validation
# ---------------------------------------------------------------------------

class TestInteractiveSchematicGraphData:
    """Integration test: graph export JSON structure for Interactive Schematic."""

    def test_graph_export_chip_json_has_required_keys(self):
        """Verify chip scope graph export JSON has nodes, edges, metadata keys."""
        mock_client = MagicMock(spec=NeptuneSigV4Client)
        mock_client.execute_query.return_value = {
            "results": [
                {"root_name": "trinity_top", "child_name": "trinity_router", "child_labels": ["ModuleDef"]},
            ]
        }

        result = _call_graph_export_api(mock_client, "chip", "trinity_top")

        # Required keys for Interactive Schematic loading
        assert "nodes" in result
        assert "edges" in result or "edge_count" in result
        assert "node_count" in result
        assert "edge_count" in result
        assert "node_types" in result
        assert "edge_types" in result

        # nodes must be a list
        assert isinstance(result["nodes"], list)
        # node_count and edge_count must be integers
        assert isinstance(result["node_count"], int)
        assert isinstance(result["edge_count"], int)
        # node_types and edge_types must be dicts
        assert isinstance(result["node_types"], dict)
        assert isinstance(result["edge_types"], dict)

    def test_graph_export_module_json_has_required_keys(self):
        """Verify module scope graph export JSON has correct structure."""
        mock_client = MagicMock(spec=NeptuneSigV4Client)
        mock_client.execute_query.return_value = {
            "results": [
                {"port_name": "clk", "port_direction": "input", "signal_name": "clk_net", "rel_type": "BINDS_TO"},
            ]
        }

        result = _call_graph_export_api(mock_client, "module", "trinity_top")

        # Required keys
        assert "nodes" in result
        assert "node_count" in result
        assert "edge_count" in result
        assert "node_types" in result
        assert "edge_types" in result

        # Validate types
        assert isinstance(result["nodes"], list)
        assert isinstance(result["node_count"], int)
        assert isinstance(result["edge_count"], int)

    def test_graph_export_json_is_serializable(self):
        """Verify graph export result can be serialized to JSON without errors."""
        mock_client = MagicMock(spec=NeptuneSigV4Client)
        mock_client.execute_query.return_value = {
            "results": [
                {"root_name": "trinity_top", "child_name": "trinity_router", "child_labels": ["ModuleDef"]},
                {"root_name": "trinity_top", "child_name": "trinity_noc2axi", "child_labels": ["ModuleDef"]},
            ]
        }

        result = _call_graph_export_api(mock_client, "chip", "trinity_top")

        # Must be JSON-serializable (no Decimal, datetime, or other non-serializable types)
        json_str = json.dumps(result)
        assert json_str is not None

        # Round-trip: parse back and verify structure preserved
        parsed = json.loads(json_str)
        assert parsed["node_count"] == result["node_count"]
        assert parsed["edge_count"] == result["edge_count"]

    def test_graph_export_metadata_structure_for_schematic(self):
        """Verify the exported data contains what Interactive Schematic needs.

        Interactive Schematic requires:
        - nodes: list of node names/identifiers
        - edges (or edge_count): edge information
        - metadata: node_types, edge_types for rendering
        """
        mock_client = MagicMock(spec=NeptuneSigV4Client)
        mock_client.execute_query.return_value = {
            "results": [
                {"root_name": "trinity_top", "child_name": "u_router", "child_labels": ["Instance"]},
                {"root_name": "trinity_top", "child_name": "u_noc2axi", "child_labels": ["Instance"]},
                {"root_name": "trinity_top", "child_name": "u_edc_ring", "child_labels": ["Instance"]},
            ]
        }

        result = _call_graph_export_api(mock_client, "chip", "trinity_top")

        # Build the metadata structure that Interactive Schematic expects
        schematic_data = {
            "nodes": result["nodes"],
            "edges": result["edges"] if isinstance(result["edges"], list) else [],
            "metadata": {
                "node_count": result["node_count"],
                "edge_count": result["edge_count"],
                "node_types": result["node_types"],
                "edge_types": result["edge_types"],
            },
        }

        # Validate schematic_data structure
        assert "nodes" in schematic_data
        assert "edges" in schematic_data
        assert "metadata" in schematic_data
        assert isinstance(schematic_data["nodes"], list)
        assert isinstance(schematic_data["edges"], (list, int))
        assert isinstance(schematic_data["metadata"], dict)
        assert schematic_data["metadata"]["node_count"] >= 0
        assert schematic_data["metadata"]["edge_count"] >= 0

        # JSON serializable — no JS errors on load
        json_output = json.dumps(schematic_data)
        assert json_output is not None
        # Re-parse to confirm validity
        reparsed = json.loads(json_output)
        assert reparsed["metadata"]["node_count"] == result["node_count"]


# ---------------------------------------------------------------------------
# End-to-end pipeline test combining all components
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:
    """Full pipeline integration: DynamoDB → transform → verify → evidence → schematic."""

    def test_full_pipeline_mocked(self):
        """Run the complete pipeline with mocked DynamoDB + Neptune."""
        records = _all_sample_records()

        # Step 1: Transform DynamoDB records to nodes
        nodes = transform_records_to_nodes(records)
        assert len(nodes) > 0

        # Step 2: Transform to edges
        edges = transform_records_to_edges(records, nodes)
        assert len(edges) > 0

        # Step 3: Verify all MERGE queries can be built
        for node in nodes:
            query, params = build_merge_query(node)
            assert "MERGE" in query

        for edge in edges:
            query, params = build_edge_merge_query(edge)
            assert "MERGE" in query

        # Step 4: Mock Neptune for graph export verification
        mock_client = MagicMock(spec=NeptuneSigV4Client)
        mock_client.execute_query.return_value = {
            "results": [
                {"root_name": "trinity_top", "child_name": "trinity_router", "child_labels": ["ModuleDef"]},
            ]
        }

        verify_result = verify_graph_export(
            client=mock_client,
            pipeline_id=PIPELINE_ID,
            root_module="trinity_top",
            module_parse_count=2,
            total_nodes_created=len(nodes),
        )

        # Verification should succeed (no mismatch)
        assert verify_result.success
        assert verify_result.chip_node_count > 0

        # Step 5: Verify graph export JSON is valid for schematic
        chip_result = _call_graph_export_api(mock_client, "chip", "trinity_top")
        json_str = json.dumps(chip_result)
        assert json_str is not None
        assert json.loads(json_str)["node_count"] > 0

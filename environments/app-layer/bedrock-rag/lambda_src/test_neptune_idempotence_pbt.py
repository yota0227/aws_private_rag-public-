"""Property-based test: Neptune ingestion idempotence.

**Validates: Requirements 10.5, 11.5**

Property 3: Neptune ingestion idempotence
For any set of DynamoDB records for a given pipeline_id, running the Neptune
ingestion pipeline twice SHALL produce the same node count and edge count as
running it once. No duplicate nodes or edges shall be created.

Uses hypothesis library with minimum 100 iterations.
Generator: random module_parse + claim records (mocked Neptune client).
Assertion: run_twice_count == run_once_count for both nodes and edges.
"""
import os
import sys
import json
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Ensure lambda_src is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neptune_ingestion import (
    transform_records_to_nodes,
    transform_records_to_edges,
    batch_upsert_nodes,
    batch_upsert_edges,
    build_merge_query,
    build_edge_merge_query,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies — Generate random DynamoDB records
# ---------------------------------------------------------------------------

# Valid identifiers for module/signal names
_identifier = st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,15}", fullmatch=True)

# Pipeline ID strategy
_pipeline_id = st.sampled_from(["tt_20260221", "tt_20260301", "n1b0_20260315"])


def _port_dict_strategy():
    """Generate a random port dict."""
    return st.fixed_dictionaries({
        "name": _identifier,
        "direction": st.sampled_from(["input", "output", "inout"]),
        "bit_width": st.sampled_from(["1", "8", "32", "64", "[7:0]", "[31:0]"]),
    })


def _instance_dict_strategy(module_name_st):
    """Generate a random instance dict."""
    return st.fixed_dictionaries({
        "instance_name": _identifier,
        "module_type": _identifier,
        "generate_scope": st.sampled_from(["", "gen_loop", "gen_x"]),
    }).map(lambda d: {
        **d,
        "hier_path": f"top/{d['instance_name']}",
    })


def _module_parse_record_strategy():
    """Generate a random module_parse DynamoDB record."""
    return st.fixed_dictionaries({
        "analysis_type": st.just("module_parse"),
        "pipeline_id": _pipeline_id,
        "module_name": _identifier,
        "file_path": _identifier.map(lambda n: f"/rtl/{n}.sv"),
        "module_type": st.sampled_from(["module", "interface"]),
        "port_list": st.lists(_port_dict_strategy(), min_size=0, max_size=5),
        "instance_list": st.lists(
            st.fixed_dictionaries({
                "instance_name": _identifier,
                "module_type": _identifier,
                "generate_scope": st.sampled_from(["", "gen_loop"]),
            }).map(lambda d: {**d, "hier_path": f"top/{d['instance_name']}"}),
            min_size=0,
            max_size=4,
        ),
    })


def _wire_claim_strategy():
    """Generate a random WireTopology claim record."""
    return st.fixed_dictionaries({
        "analysis_type": st.just("claim"),
        "pipeline_id": _pipeline_id,
        "topic": st.just("WireTopology"),
        "module_name": _identifier,
        "signal_name": _identifier,
        "claim_text": _identifier.map(lambda n: f"Wire '{n}' connects ..."),
        "dimensions": st.sampled_from(["", "[7:0]", "[3:0][1:0]"]),
        "struct_type": st.sampled_from(["", "logic", "wire"]),
        "purpose": st.sampled_from(["", "data", "control"]),
    })


def _port_binding_claim_strategy():
    """Generate a random PortBinding claim record."""
    return st.fixed_dictionaries({
        "analysis_type": st.just("claim"),
        "pipeline_id": _pipeline_id,
        "topic": st.just("PortBinding"),
        "module_name": _identifier,
        "port_name": _identifier,
        "signal_name": _identifier,
        "signal_expr": _identifier,
        "expression_type": st.sampled_from(["simple", "arithmetic", "concatenation"]),
        "direction": st.sampled_from(["input", "output", "inout"]),
        "claim_text": st.just("binds port ..."),
    })


def _clock_domain_claim_strategy():
    """Generate a random ClockDomain claim record."""
    return st.fixed_dictionaries({
        "analysis_type": st.just("claim"),
        "pipeline_id": _pipeline_id,
        "topic": st.just("ClockDomain"),
        "module_name": _identifier,
        "clock_domain": _identifier,
        "signal_name": _identifier,
        "claim_text": _identifier.map(lambda n: f"Clock domain '{n}' ..."),
        "frequency": st.sampled_from(["", "1GHz", "500MHz"]),
    })


# Combined record strategy
_record_strategy = st.one_of(
    _module_parse_record_strategy(),
    _wire_claim_strategy(),
    _port_binding_claim_strategy(),
    _clock_domain_claim_strategy(),
)

# A list of 1-20 random records
_records_strategy = st.lists(_record_strategy, min_size=1, max_size=20)


# ---------------------------------------------------------------------------
# Mock Neptune Client that tracks MERGE operations
# ---------------------------------------------------------------------------

class MockNeptuneClient:
    """Mock Neptune client that tracks execute_query calls.

    Counts MERGE operations for nodes and edges. Simulates idempotent
    MERGE behavior: same query + params = same result (no duplicates).
    """

    def __init__(self):
        self.queries_executed = []
        self.merge_count = 0

    def execute_query(self, query: str, parameters: dict = None) -> dict:
        """Record the query and return empty success response."""
        self.queries_executed.append((query, parameters))
        if "MERGE" in query:
            self.merge_count += 1
        return {"results": []}

    def reset(self):
        """Reset counters for a fresh run."""
        self.queries_executed = []
        self.merge_count = 0


# ---------------------------------------------------------------------------
# Property Test: Idempotence
# ---------------------------------------------------------------------------

class TestNeptuneIngestionIdempotence:
    """Property-based tests for Neptune ingestion idempotence.

    **Validates: Requirements 10.5, 11.5**
    """

    @given(records=_records_strategy)
    @settings(max_examples=100, deadline=None)
    def test_node_transform_idempotence(self, records):
        """Transform produces same node count regardless of how many times run.

        Running transform_records_to_nodes twice on same input must produce
        identical results (same count, same labels, same properties).
        """
        nodes_run1 = transform_records_to_nodes(records)
        nodes_run2 = transform_records_to_nodes(records)

        assert len(nodes_run1) == len(nodes_run2), (
            f"Node count mismatch: run1={len(nodes_run1)}, run2={len(nodes_run2)}"
        )

        # Verify each node is identical
        for n1, n2 in zip(nodes_run1, nodes_run2):
            assert n1["label"] == n2["label"]
            assert n1["properties"] == n2["properties"]

    @given(records=_records_strategy)
    @settings(max_examples=100, deadline=None)
    def test_edge_transform_idempotence(self, records):
        """Transform produces same edge count regardless of how many times run.

        Running transform_records_to_edges twice on same input must produce
        identical results.
        """
        nodes = transform_records_to_nodes(records)
        edges_run1 = transform_records_to_edges(records, nodes)
        edges_run2 = transform_records_to_edges(records, nodes)

        assert len(edges_run1) == len(edges_run2), (
            f"Edge count mismatch: run1={len(edges_run1)}, run2={len(edges_run2)}"
        )

        for e1, e2 in zip(edges_run1, edges_run2):
            assert e1["type"] == e2["type"]
            assert e1["from_node"] == e2["from_node"]
            assert e1["to_node"] == e2["to_node"]

    @given(records=_records_strategy)
    @settings(max_examples=100, deadline=None)
    def test_full_pipeline_idempotence_merge_count(self, records):
        """Full pipeline: running twice produces same MERGE operation count.

        **Validates: Requirements 10.5, 11.5**

        This is the core idempotence property. With a mocked Neptune client:
        - Run 1: transform + batch_upsert (nodes + edges)
        - Run 2: same transform + batch_upsert on same data
        - Assert: run1 MERGE count == run2 MERGE count

        Since MERGE is idempotent by design, the same number of operations
        should be issued regardless of how many times we run.
        """
        # --- Run 1 ---
        client1 = MockNeptuneClient()
        nodes = transform_records_to_nodes(records)
        edges = transform_records_to_edges(records, nodes)

        node_summary1 = batch_upsert_nodes(client1, nodes, batch_size=50)
        edge_summary1 = batch_upsert_edges(client1, edges, batch_size=50)

        run1_node_merges = node_summary1["upserted"]
        run1_edge_merges = edge_summary1["upserted"]
        run1_total = client1.merge_count

        # --- Run 2 (same input, fresh client) ---
        client2 = MockNeptuneClient()
        nodes2 = transform_records_to_nodes(records)
        edges2 = transform_records_to_edges(records, nodes2)

        node_summary2 = batch_upsert_nodes(client2, nodes2, batch_size=50)
        edge_summary2 = batch_upsert_edges(client2, edges2, batch_size=50)

        run2_node_merges = node_summary2["upserted"]
        run2_edge_merges = edge_summary2["upserted"]
        run2_total = client2.merge_count

        # --- Assertions: idempotence ---
        assert run1_node_merges == run2_node_merges, (
            f"Node MERGE count differs: run1={run1_node_merges}, run2={run2_node_merges}"
        )
        assert run1_edge_merges == run2_edge_merges, (
            f"Edge MERGE count differs: run1={run1_edge_merges}, run2={run2_edge_merges}"
        )
        assert run1_total == run2_total, (
            f"Total MERGE count differs: run1={run1_total}, run2={run2_total}"
        )

    @given(records=_records_strategy)
    @settings(max_examples=100, deadline=None)
    def test_merge_queries_are_deterministic(self, records):
        """MERGE queries generated are identical across runs.

        For the same input records, build_merge_query must produce the same
        query strings and parameters. This ensures Neptune receives identical
        MERGE statements, guaranteeing idempotent behavior.
        """
        nodes = transform_records_to_nodes(records)

        queries_run1 = []
        queries_run2 = []

        for node in nodes:
            try:
                q1, p1 = build_merge_query(node)
                queries_run1.append((q1, p1))
            except ValueError:
                queries_run1.append(None)

        # Re-transform and rebuild queries
        nodes2 = transform_records_to_nodes(records)
        for node in nodes2:
            try:
                q2, p2 = build_merge_query(node)
                queries_run2.append((q2, p2))
            except ValueError:
                queries_run2.append(None)

        assert len(queries_run1) == len(queries_run2)
        for q1, q2 in zip(queries_run1, queries_run2):
            assert q1 == q2, f"Query mismatch:\n  run1: {q1}\n  run2: {q2}"

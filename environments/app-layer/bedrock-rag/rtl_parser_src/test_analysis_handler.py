"""
Tests for analysis_handler.py — dispatch logic, error handling, and stage handlers.

Covers:
- Main dispatcher (analysis_handler) stage routing
- Invalid/missing stage and pipeline_id handling
- Each stage handler's basic flow with mocked AWS dependencies
"""

import json
import pytest
from unittest.mock import patch, MagicMock, call

# Patch boto3 before importing analysis_handler to avoid real AWS calls
with patch("boto3.client"), patch("boto3.resource"):
    import analysis_handler as ah


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    """Set minimal env vars for all tests."""
    monkeypatch.setenv("RTL_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("RTL_OPENSEARCH_ENDPOINT", "https://test-os.aoss.amazonaws.com")
    monkeypatch.setenv("RTL_OPENSEARCH_INDEX", "test-index")
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.setenv("DYNAMODB_EXTRACTION_TABLE", "test-extraction-tasks")


# ---------------------------------------------------------------------------
# 1–4. Dispatcher — valid stages route to correct handler
# ---------------------------------------------------------------------------

class TestDispatcherRouting:
    """analysis_handler dispatches to the correct stage handler."""

    def test_dispatch_hierarchy_extraction(self):
        mock_fn = MagicMock(return_value={"status": "completed"})
        with patch.dict(ah._STAGE_HANDLERS, {"hierarchy_extraction": mock_fn}):
            event = {"stage": "hierarchy_extraction", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"

    def test_dispatch_clock_domain_analysis(self):
        mock_fn = MagicMock(return_value={"status": "completed"})
        with patch.dict(ah._STAGE_HANDLERS, {"clock_domain_analysis": mock_fn}):
            event = {"stage": "clock_domain_analysis", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"

    def test_dispatch_dataflow_tracking(self):
        mock_fn = MagicMock(return_value={"status": "completed"})
        with patch.dict(ah._STAGE_HANDLERS, {"dataflow_tracking": mock_fn}):
            event = {"stage": "dataflow_tracking", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"

    def test_dispatch_topic_classification(self):
        mock_fn = MagicMock(return_value={"status": "completed"})
        with patch.dict(ah._STAGE_HANDLERS, {"topic_classification": mock_fn}):
            event = {"stage": "topic_classification", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# 5–7. Error handling — missing/invalid parameters
# ---------------------------------------------------------------------------

class TestDispatcherErrors:
    """analysis_handler raises ValueError for invalid inputs."""

    def test_missing_pipeline_id_raises(self):
        with pytest.raises(ValueError, match="pipeline_id is required"):
            ah.analysis_handler({"stage": "hierarchy_extraction"})

    def test_missing_stage_raises(self):
        with pytest.raises(ValueError, match="stage is required"):
            ah.analysis_handler({"pipeline_id": "tt_20260221"})

    def test_unknown_stage_raises(self):
        with pytest.raises(ValueError, match="unknown stage: nonexistent"):
            ah.analysis_handler({"stage": "nonexistent", "pipeline_id": "tt_20260221"})


# ---------------------------------------------------------------------------
# 8. Empty pipeline_id string
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases for the dispatcher."""

    def test_empty_pipeline_id_raises(self):
        with pytest.raises(ValueError, match="pipeline_id is required"):
            ah.analysis_handler({"stage": "hierarchy_extraction", "pipeline_id": ""})

    def test_empty_stage_raises(self):
        with pytest.raises(ValueError, match="stage is required"):
            ah.analysis_handler({"stage": "", "pipeline_id": "tt_20260221"})

    def test_empty_event_raises(self):
        with pytest.raises(ValueError, match="pipeline_id is required"):
            ah.analysis_handler({})


# ---------------------------------------------------------------------------
# 9–10. Stage handler propagates exceptions
# ---------------------------------------------------------------------------

class TestHandlerExceptionPropagation:
    """Exceptions from stage handlers propagate through the dispatcher."""

    def test_handler_exception_propagates(self):
        mock_fn = MagicMock(side_effect=RuntimeError("test error"))
        with patch.dict(ah._STAGE_HANDLERS, {"hierarchy_extraction": mock_fn}):
            with pytest.raises(RuntimeError, match="test error"):
                ah.analysis_handler({
                    "stage": "hierarchy_extraction",
                    "pipeline_id": "tt_20260221",
                })

    def test_handler_returns_result(self):
        expected = {"status": "completed", "modules_processed": 42}
        mock_fn = MagicMock(return_value=expected)
        with patch.dict(ah._STAGE_HANDLERS, {"dataflow_tracking": mock_fn}):
            result = ah.analysis_handler({
                "stage": "dataflow_tracking",
                "pipeline_id": "tt_20260221",
            })
            assert result == expected


# ---------------------------------------------------------------------------
# 11–12. Hierarchy handler with mocked dependencies
# ---------------------------------------------------------------------------

class TestHierarchyHandler:
    """handle_hierarchy_extraction with mocked OpenSearch/S3."""

    @patch.object(ah, "_update_dynamodb_status")
    @patch.object(ah, "_opensearch_scroll_query", return_value=[])
    def test_empty_modules_returns_zero(self, mock_query, mock_status):
        event = {"pipeline_id": "tt_20260221"}
        result = ah.handle_hierarchy_extraction(event)
        assert result["status"] == "completed"
        assert result["modules_processed"] == 0

    @patch.object(ah, "_update_dynamodb_status")
    @patch.object(ah, "_index_document", return_value=True)
    @patch.object(ah, "s3_client")
    @patch.object(ah, "_opensearch_scroll_query")
    def test_builds_hierarchy_from_modules(self, mock_query, mock_s3,
                                           mock_index, mock_status):
        mock_query.return_value = [
            {
                "module_name": "top",
                "instance_list": "u_sub: sub_mod",
                "port_list": "input clk",
                "parameter_list": "",
                "file_path": "rtl-sources/tt_20260221/top.sv",
            },
        ]
        ah.RTL_S3_BUCKET = "test-bucket"
        event = {"pipeline_id": "tt_20260221"}
        result = ah.handle_hierarchy_extraction(event)
        assert result["status"] == "completed"
        assert result["modules_processed"] >= 1
        assert mock_index.called


# ---------------------------------------------------------------------------
# 13. Topic classification handler
# ---------------------------------------------------------------------------

class TestTopicHandler:
    """handle_topic_classification with mocked dependencies."""

    @patch.object(ah, "_update_dynamodb_status")
    @patch.object(ah, "_opensearch_scroll_query", return_value=[])
    def test_empty_docs_returns_zero(self, mock_query, mock_status):
        event = {"pipeline_id": "tt_20260221"}
        result = ah.handle_topic_classification(event)
        assert result["status"] == "completed"
        assert result["modules_processed"] == 0

    @patch.object(ah, "_update_dynamodb_status")
    @patch.object(ah, "_update_document", return_value=True)
    @patch.object(ah, "_index_document", return_value=True)
    @patch.object(ah, "_opensearch_scroll_query")
    def test_classifies_noc_module(self, mock_query, mock_index,
                                   mock_update, mock_status):
        mock_query.return_value = [
            {
                "module_name": "tt_noc_router",
                "file_path": "rtl-sources/tt_20260221/noc/tt_noc_router.sv",
                "_id": "doc123",
            },
        ]
        event = {"pipeline_id": "tt_20260221"}
        result = ah.handle_topic_classification(event)
        assert result["status"] == "completed"
        assert result["classified"] == 1
        assert result["unclassified"] == 0


# ---------------------------------------------------------------------------
# 14–16. New stage dispatch tests: claim_generation, hdd_generation, variant_delta
# ---------------------------------------------------------------------------

class TestNewStageDispatch:
    """Dispatcher routes new stages to correct handlers."""

    def test_dispatch_claim_generation(self):
        mock_fn = MagicMock(return_value={"status": "completed", "claims_generated": 5})
        with patch.dict(ah._STAGE_HANDLERS, {"claim_generation": mock_fn}):
            event = {"stage": "claim_generation", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"
            assert result["claims_generated"] == 5

    def test_dispatch_hdd_generation(self):
        mock_fn = MagicMock(return_value={"status": "completed", "sections_generated": 3})
        with patch.dict(ah._STAGE_HANDLERS, {"hdd_generation": mock_fn}):
            event = {"stage": "hdd_generation", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"
            assert result["sections_generated"] == 3

    def test_dispatch_variant_delta(self):
        mock_fn = MagicMock(return_value={"status": "completed", "added": 2})
        with patch.dict(ah._STAGE_HANDLERS, {"variant_delta": mock_fn}):
            event = {"stage": "variant_delta", "pipeline_id": "tt_20260221",
                     "variant_baseline_id": "tt_20260101"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# 17. Claim generation handler with mocked dependencies
# ---------------------------------------------------------------------------

class TestClaimGenerationHandler:
    @patch.object(ah, "_update_dynamodb_status")
    @patch.object(ah, "_index_document", return_value=True)
    @patch.object(ah, "_opensearch_scroll_query")
    @patch("analysis_handler.generate_claims")
    def test_generates_and_indexes_claims(self, mock_gen, mock_query,
                                          mock_index, mock_status):
        mock_query.side_effect = lambda pid, atype: {
            "module_parse": [{"module_name": "tt_noc_router", "file_path": "noc/r.sv"}],
            "topic": [{"module_name": "tt_noc_router", "topics": ["NoC"]}],
            "hierarchy": [{"module_name": "top"}],
            "clock_domain": [],
            "dataflow": [],
        }.get(atype, [])

        mock_gen.return_value = [
            {"claim_id": "clm_001", "claim_type": "structural"},
        ]

        event = {"pipeline_id": "tt_20260221"}
        result = ah.handle_claim_generation(event)
        assert result["status"] == "completed"
        assert result["claims_generated"] == 1
        mock_index.assert_called()

    @patch.object(ah, "_update_dynamodb_status")
    @patch.object(ah, "_opensearch_scroll_query", return_value=[])
    def test_no_modules_returns_zero_claims(self, mock_query, mock_status):
        event = {"pipeline_id": "tt_20260221"}
        result = ah.handle_claim_generation(event)
        assert result["status"] == "completed"
        assert result["claims_generated"] == 0


# ---------------------------------------------------------------------------
# 18. HDD generation handler with mocked dependencies
# ---------------------------------------------------------------------------

class TestHddGenerationHandler:
    @patch.object(ah, "_update_dynamodb_status")
    @patch.object(ah, "_index_document", return_value=True)
    @patch.object(ah, "s3_client")
    @patch.object(ah, "_opensearch_scroll_query")
    @patch("analysis_handler.generate_hdd_section")
    def test_generates_and_stores_hdd(self, mock_gen, mock_query, mock_s3,
                                      mock_index, mock_status):
        mock_query.side_effect = lambda pid, atype: {
            "hierarchy": [{"module_name": "top", "children": []}],
            "clock_domain": [],
            "dataflow": [],
            "topic": [{"module_name": "tt_noc_router", "topics": ["NoC"]}],
            "claim": [],
        }.get(atype, [])

        mock_gen.return_value = {
            "pipeline_id": "tt_20260221",
            "topic": "NoC",
            "hdd_content": "## Overview\nContent",
            "analysis_type": "hdd_section",
            "hdd_type": "block",
            "hdd_section_title": "NoC HDD",
            "hdd_section_type": "block",
            "hdd_metadata": {},
        }

        ah.RTL_S3_BUCKET = "test-bucket"
        event = {"pipeline_id": "tt_20260221"}
        result = ah.handle_hdd_generation(event)
        assert result["status"] == "completed"
        assert result["sections_generated"] == 1


# ---------------------------------------------------------------------------
# 19. Variant delta handler with mocked dependencies
# ---------------------------------------------------------------------------

class TestVariantDeltaHandler:
    @patch.object(ah, "_update_dynamodb_status")
    @patch.object(ah, "_index_document", return_value=True)
    @patch.object(ah, "_opensearch_scroll_query")
    def test_computes_delta(self, mock_query, mock_index, mock_status):
        mock_query.side_effect = lambda pid, atype: {
            ("tt_20260101", "module_parse"): [
                {"module_name": "mod_a", "parameter_list": "W=32", "instance_list": ""},
            ],
            ("tt_20260221", "module_parse"): [
                {"module_name": "mod_a", "parameter_list": "W=64", "instance_list": ""},
                {"module_name": "mod_b", "parameter_list": "", "instance_list": ""},
            ],
        }.get((pid, atype), [])

        event = {
            "pipeline_id": "tt_20260221",
            "variant_baseline_id": "tt_20260101",
        }
        result = ah.handle_variant_delta(event)
        assert result["status"] == "completed"
        assert result["added"] >= 1  # mod_b added
        mock_index.assert_called()

    @patch.object(ah, "_update_dynamodb_status")
    def test_no_baseline_id_skips(self, mock_status):
        event = {"pipeline_id": "tt_20260221"}
        result = ah.handle_variant_delta(event)
        assert result["status"] == "completed"
        assert result.get("skipped") is True


# ---------------------------------------------------------------------------
# 20. Stage handlers registered in _STAGE_HANDLERS
# ---------------------------------------------------------------------------

class TestStageHandlersRegistered:
    def test_claim_generation_registered(self):
        assert "claim_generation" in ah._STAGE_HANDLERS

    def test_hdd_generation_registered(self):
        assert "hdd_generation" in ah._STAGE_HANDLERS

    def test_variant_delta_registered(self):
        assert "variant_delta" in ah._STAGE_HANDLERS

    def test_backfill_pipeline_id_registered(self):
        assert "backfill_pipeline_id" in ah._STAGE_HANDLERS


# ---------------------------------------------------------------------------
# 21. Backfill pipeline_id dispatch test
# ---------------------------------------------------------------------------

class TestBackfillDispatch:
    """Dispatcher routes backfill_pipeline_id to the correct handler."""

    def test_dispatch_backfill_pipeline_id(self):
        mock_fn = MagicMock(return_value={"status": "completed", "backfilled": 100, "failed": 0})
        with patch.dict(ah._STAGE_HANDLERS, {"backfill_pipeline_id": mock_fn}):
            event = {"stage": "backfill_pipeline_id", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"
            assert result["backfilled"] == 100


# ---------------------------------------------------------------------------
# 22–23. Dispatch tests: clear_index, reparse_all
# ---------------------------------------------------------------------------

class TestClearIndexAndReparseAllDispatch:
    """Dispatcher routes clear_index and reparse_all to correct handlers."""

    def test_dispatch_clear_index(self):
        mock_fn = MagicMock(return_value={"status": "completed"})
        with patch.dict(ah._STAGE_HANDLERS, {"clear_index": mock_fn}):
            event = {"stage": "clear_index", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"

    def test_dispatch_reparse_all(self):
        mock_fn = MagicMock(return_value={"status": "completed", "files_triggered": 50, "errors": 0})
        with patch.dict(ah._STAGE_HANDLERS, {"reparse_all": mock_fn}):
            event = {"stage": "reparse_all", "pipeline_id": "tt_20260221",
                     "s3_prefix": "rtl-sources/tt_20260221/"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"
            assert result["files_triggered"] == 50

    def test_clear_index_registered(self):
        assert "clear_index" in ah._STAGE_HANDLERS

    def test_reparse_all_registered(self):
        assert "reparse_all" in ah._STAGE_HANDLERS


# ---------------------------------------------------------------------------
# 24–27. Dispatch tests: chip_config, edc_topology, noc_protocol, overlay_deep_analysis
# ---------------------------------------------------------------------------

class TestSubsystemStageDispatch:
    """Dispatcher routes subsystem analysis stages to correct handlers."""

    def test_dispatch_chip_config(self):
        mock_fn = MagicMock(return_value={"status": "completed", "files_processed": 3})
        with patch.dict(ah._STAGE_HANDLERS, {"chip_config": mock_fn}):
            event = {"stage": "chip_config", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"
            assert result["files_processed"] == 3

    def test_dispatch_edc_topology(self):
        mock_fn = MagicMock(return_value={"status": "completed", "modules_processed": 10})
        with patch.dict(ah._STAGE_HANDLERS, {"edc_topology": mock_fn}):
            event = {"stage": "edc_topology", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"
            assert result["modules_processed"] == 10

    def test_dispatch_noc_protocol(self):
        mock_fn = MagicMock(return_value={"status": "completed", "noc_modules": 5, "routing_algorithms": 3})
        with patch.dict(ah._STAGE_HANDLERS, {"noc_protocol": mock_fn}):
            event = {"stage": "noc_protocol", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"
            assert result["routing_algorithms"] == 3

    def test_dispatch_overlay_deep_analysis(self):
        mock_fn = MagicMock(return_value={"status": "completed", "overlay_modules": 8, "roles_identified": 5})
        with patch.dict(ah._STAGE_HANDLERS, {"overlay_deep_analysis": mock_fn}):
            event = {"stage": "overlay_deep_analysis", "pipeline_id": "tt_20260221"}
            result = ah.analysis_handler(event)
            mock_fn.assert_called_once_with(event)
            assert result["status"] == "completed"
            assert result["roles_identified"] == 5


# ---------------------------------------------------------------------------
# 28. New stages registered in _STAGE_HANDLERS
# ---------------------------------------------------------------------------

class TestSubsystemStageHandlersRegistered:
    def test_chip_config_registered(self):
        assert "chip_config" in ah._STAGE_HANDLERS

    def test_edc_topology_registered(self):
        assert "edc_topology" in ah._STAGE_HANDLERS

    def test_noc_protocol_registered(self):
        assert "noc_protocol" in ah._STAGE_HANDLERS

    def test_overlay_deep_analysis_registered(self):
        assert "overlay_deep_analysis" in ah._STAGE_HANDLERS

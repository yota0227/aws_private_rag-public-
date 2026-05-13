"""
Tests for hdd_generator.py — Bedrock Claude HDD section generation with mocked AWS calls.

Covers:
- HDD type determination
- Prompt building
- Source file collection
- Empty/invalid input handling
- Successful HDD generation
- Claude failure handling
- Metadata generation
- Required sections constant
"""

import json
import logging
import sys
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO

# Patch boto3 before importing to avoid real AWS calls
with patch("boto3.client"), patch("boto3.resource"):
    import hdd_generator as hg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_hierarchy():
    return {
        "module_name": "trinity",
        "instance_name": "top",
        "hierarchy_path": "trinity",
        "file_path": "rtl-sources/tt_20260221/trinity.sv",
        "children": [
            {
                "module_name": "tt_dispatch_top",
                "instance_name": "gen_dispatch_e",
                "hierarchy_path": "trinity.gen_dispatch_e",
                "file_path": "rtl-sources/tt_20260221/dispatch/tt_dispatch_top.sv",
                "children": [],
            },
        ],
    }


# ---------------------------------------------------------------------------
# 1. HDD type determination
# ---------------------------------------------------------------------------

class TestDetermineHddType:
    def test_chip_type_for_empty_topic(self):
        assert hg._determine_hdd_type("", {}) == "chip"

    def test_chip_type_for_all_topic(self):
        assert hg._determine_hdd_type("all", {}) == "chip"

    def test_chip_type_for_top_topic(self):
        assert hg._determine_hdd_type("top", {}) == "chip"

    def test_subsystem_type_for_many_children(self):
        hierarchy = {"children": [{"m": i} for i in range(5)]}
        assert hg._determine_hdd_type("EDC", hierarchy) == "subsystem"

    def test_block_type_for_few_children(self):
        hierarchy = {"children": [{"m": 1}]}
        assert hg._determine_hdd_type("Overlay", hierarchy) == "block"

    def test_block_type_for_no_children(self):
        assert hg._determine_hdd_type("NoC", {}) == "block"


# ---------------------------------------------------------------------------
# 2. Prompt building
# ---------------------------------------------------------------------------

class TestBuildHddPrompt:
    def test_prompt_contains_pipeline_id(self):
        prompt = hg._build_hdd_prompt(
            "tt_20260221", "NoC", "block", {}, [], [], [],
        )
        assert "tt_20260221" in prompt

    def test_prompt_contains_topic(self):
        prompt = hg._build_hdd_prompt(
            "tt_20260221", "EDC", "subsystem", {}, [], [], [],
        )
        assert "EDC" in prompt

    def test_prompt_contains_hdd_type(self):
        prompt = hg._build_hdd_prompt(
            "tt_20260221", "NoC", "chip", {}, [], [], [],
        )
        assert "chip" in prompt


# ---------------------------------------------------------------------------
# 3. Source file collection
# ---------------------------------------------------------------------------

class TestCollectSourceFiles:
    def test_collects_files_from_hierarchy(self):
        files = hg._collect_source_files(_sample_hierarchy())
        assert len(files) == 2
        assert "trinity.sv" in files[0]
        assert "tt_dispatch_top.sv" in files[1]

    def test_empty_hierarchy_returns_empty(self):
        assert hg._collect_source_files({}) == []

    def test_non_dict_returns_empty(self):
        assert hg._collect_source_files("not a dict") == []


# ---------------------------------------------------------------------------
# 4. Empty/invalid input handling
# ---------------------------------------------------------------------------

class TestGenerateHddInvalidInputs:
    @patch.object(hg, "_invoke_claude", return_value="## Overview\nTest content")
    def test_non_dict_hierarchy_defaults(self, mock_claude):
        result = hg.generate_hdd_section(
            "tt_20260221", "NoC", "not_a_dict", "not_a_list", None, 42,
        )
        assert result["hdd_content"] == "## Overview\nTest content"
        assert result["pipeline_id"] == "tt_20260221"


# ---------------------------------------------------------------------------
# 5. Successful HDD generation
# ---------------------------------------------------------------------------

class TestGenerateHddSuccess:
    @patch.object(hg, "_invoke_claude")
    def test_generates_hdd_section(self, mock_claude):
        mock_claude.return_value = (
            "## Overview\nChip overview\n"
            "## Module Hierarchy\nHierarchy details\n"
            "## Functional Details\nDetails\n"
            "## Clock/Reset Structure\nClocks\n"
            "## Key Parameters\nParams\n"
            "## Verification Checklist\nChecklist"
        )

        result = hg.generate_hdd_section(
            "tt_20260221", "NoC", _sample_hierarchy(),
            [{"domain": "noc_clock_domain"}], [], [],
        )
        assert result["pipeline_id"] == "tt_20260221"
        assert result["topic"] == "NoC"
        assert result["analysis_type"] == "hdd_section"
        assert "## Overview" in result["hdd_content"]
        assert result["hdd_section_title"] == "NoC HDD"

    @patch.object(hg, "_invoke_claude", return_value="## Overview\nContent")
    def test_metadata_fields_present(self, mock_claude):
        result = hg.generate_hdd_section(
            "tt_20260221", "EDC", _sample_hierarchy(), [], [], [],
        )
        meta = result["hdd_metadata"]
        assert "source_rtl_files" in meta
        assert "generation_date" in meta
        assert "pipeline_version" in meta
        assert meta["pipeline_id"] == "tt_20260221"


# ---------------------------------------------------------------------------
# 6. Claude failure
# ---------------------------------------------------------------------------

class TestGenerateHddFailure:
    @patch.object(hg, "_invoke_claude", side_effect=RuntimeError("timeout"))
    def test_claude_failure_raises(self, mock_claude):
        with pytest.raises(RuntimeError, match="timeout"):
            hg.generate_hdd_section(
                "tt_20260221", "NoC", {}, [], [], [],
            )


# ---------------------------------------------------------------------------
# 7. Invoke Claude retry
# ---------------------------------------------------------------------------

class TestInvokeClaudeHdd:
    @patch("hdd_generator.boto3.client")
    def test_retry_on_failure(self, mock_boto_client):
        mock_bedrock = MagicMock()
        mock_boto_client.return_value = mock_bedrock

        mock_bedrock.invoke_model.side_effect = [
            Exception("transient"),
            {"body": BytesIO(json.dumps({
                "content": [{"type": "text", "text": "## Overview\nOK"}],
            }).encode())},
        ]

        result = hg._invoke_claude("test prompt")
        assert "Overview" in result
        assert mock_bedrock.invoke_model.call_count == 2

    @patch("hdd_generator.boto3.client")
    def test_all_retries_exhausted(self, mock_boto_client):
        mock_bedrock = MagicMock()
        mock_boto_client.return_value = mock_bedrock
        mock_bedrock.invoke_model.side_effect = Exception("persistent")

        with pytest.raises(RuntimeError, match="persistent"):
            hg._invoke_claude("test prompt")


# ---------------------------------------------------------------------------
# 8. Required sections constant
# ---------------------------------------------------------------------------

class TestRequiredSections:
    def test_required_sections_defined(self):
        assert len(hg.HDD_REQUIRED_SECTIONS) >= 6
        assert "Overview" in hg.HDD_REQUIRED_SECTIONS
        assert "Verification Checklist" in hg.HDD_REQUIRED_SECTIONS


# ---------------------------------------------------------------------------
# 9. Dispatch coordinate self-consistency check (Req 2.1, 2.2, 2.3)
# ---------------------------------------------------------------------------

class TestValidateDispatchCoordinates:
    """Tests for _validate_dispatch_coordinates() — EP Table consistency check."""

    def test_no_from_llm_text_passes_through(self):
        """Text without [FROM LLM] markers should pass through unchanged."""
        text = "East dispatch is at X=3. West dispatch is at X=0."
        assert hg._validate_dispatch_coordinates(text) == text

    def test_consistent_coordinates_pass(self):
        """[FROM LLM] text with correct coordinates should pass unchanged."""
        text = "[FROM LLM] The East dispatch is located at X=3."
        assert hg._validate_dispatch_coordinates(text) == text

    def test_east_contradiction_detected(self):
        """East dispatch with wrong X coordinate should be caught."""
        text = "[FROM LLM] The East dispatch is at X=0."
        result = hg._validate_dispatch_coordinates(text)
        # Coordinate part should be removed or paragraph discarded
        assert "X=0" not in result

    def test_west_contradiction_detected(self):
        """West dispatch with wrong X coordinate should be caught."""
        text = "[FROM LLM] The West dispatch is at X=3."
        result = hg._validate_dispatch_coordinates(text)
        assert "X=3" not in result

    def test_incomplete_sentence_discards_paragraph(self):
        """If removing coordinates leaves incomplete text, discard paragraph."""
        # After removing X=0, only "East dispatch at" remains — incomplete
        text = "[FROM LLM] East dispatch at X=0."
        result = hg._validate_dispatch_coordinates(text)
        # Paragraph should be discarded entirely
        assert result == ""

    def test_multiple_paragraphs_only_conflicting_affected(self):
        """Non-conflicting paragraphs should remain intact."""
        text = (
            "Normal paragraph without LLM inference.\n\n"
            "[FROM LLM] The East dispatch is at X=0."
        )
        result = hg._validate_dispatch_coordinates(text)
        assert "Normal paragraph without LLM inference." in result

    def test_empty_input_returns_empty(self):
        """Empty string input should return empty string."""
        assert hg._validate_dispatch_coordinates("") == ""

    def test_none_input_returns_none(self):
        """None input should return None."""
        assert hg._validate_dispatch_coordinates(None) is None

    def test_custom_ep_table(self):
        """Custom EP table should override defaults."""
        custom_table = {"east": 5, "west": 2}
        text = "[FROM LLM] The East dispatch is at X=3."
        result = hg._validate_dispatch_coordinates(text, ep_table=custom_table)
        # X=3 contradicts custom east=5
        assert "X=3" not in result

    def test_warning_log_emitted(self, caplog):
        """Conflict should emit a warning log with dispatch_coord_conflict event."""
        text = "[FROM LLM] The East dispatch is at X=0."
        with caplog.at_level(logging.WARNING):
            hg._validate_dispatch_coordinates(text)
        assert "dispatch_coord_conflict" in caplog.text

    def test_complete_sentence_after_removal(self):
        """If sentence remains complete after coord removal, keep it."""
        text = "[FROM LLM] The East dispatch handles traffic at X=0 for the NoC router subsystem."
        result = hg._validate_dispatch_coordinates(text)
        # Coordinate removed but sentence should still be meaningful
        assert "X=0" not in result
        assert "NoC router subsystem" in result


class TestIsSentenceComplete:
    """Tests for _is_sentence_complete() helper."""

    def test_empty_string_incomplete(self):
        assert hg._is_sentence_complete("") is False

    def test_short_text_incomplete(self):
        assert hg._is_sentence_complete("ab") is False

    def test_dangling_connector_incomplete(self):
        assert hg._is_sentence_complete("The dispatch is at and") is False

    def test_normal_sentence_complete(self):
        assert hg._is_sentence_complete("The dispatch handles traffic.") is True

    def test_long_text_without_period_complete(self):
        assert hg._is_sentence_complete("The dispatch handles traffic for the NoC") is True


class TestPromptContainsSelfConsistencyInstruction:
    """Verify the self-consistency check instruction is in the prompt (Req 2.3)."""

    def test_prompt_contains_ep_table_instruction(self):
        prompt = hg._build_hdd_prompt(
            "tt_20260221", "NoC", "block", {}, [], [], [],
        )
        assert "EP Table의 좌표를 참조하여 [FROM LLM] 추론을 검증하라" in prompt

    def test_prompt_contains_east_west_coordinates(self):
        prompt = hg._build_hdd_prompt(
            "tt_20260221", "Dispatch", "chip", {}, [], [], [],
        )
        assert "East dispatch는 X=3" in prompt
        assert "West dispatch는 X=0" in prompt


# ---------------------------------------------------------------------------
# 10. Generalized coordinate validation — _validate_coordinates() (Req 2.1, 2.2)
# ---------------------------------------------------------------------------

class TestValidateCoordinates:
    """Tests for _validate_coordinates() — generalized EP Table consistency check."""

    def test_no_from_llm_text_passes_through(self):
        """Text without [FROM LLM] markers should pass through unchanged."""
        text = "NOC2AXI overlay row is at Y=4. Tensix row is at Y=0."
        assert hg._validate_coordinates(text) == text

    def test_consistent_x_coordinates_pass(self):
        """[FROM LLM] text with correct X coordinates should pass unchanged."""
        text = "[FROM LLM] The East dispatch is located at X=3."
        assert hg._validate_coordinates(text) == text

    def test_consistent_y_noc2axi_passes(self):
        """[FROM LLM] text with correct NOC2AXI Y=4 should pass unchanged."""
        text = "[FROM LLM] The NOC2AXI row is located at Y=4 in the overlay layer."
        assert hg._validate_coordinates(text) == text

    def test_consistent_y_tensix_passes(self):
        """[FROM LLM] text with correct Tensix Y=0..3 should pass unchanged."""
        text = "[FROM LLM] The Tensix row is at Y=2 in the compute grid."
        assert hg._validate_coordinates(text) == text

    def test_east_x_contradiction_detected(self):
        """East dispatch with wrong X coordinate should be caught."""
        text = "[FROM LLM] The East dispatch is at X=0."
        result = hg._validate_coordinates(text)
        assert "X=0" not in result

    def test_west_x_contradiction_detected(self):
        """West dispatch with wrong X coordinate should be caught."""
        text = "[FROM LLM] The West dispatch is at X=3."
        result = hg._validate_coordinates(text)
        assert "X=3" not in result

    def test_noc2axi_y_contradiction_detected(self):
        """NOC2AXI overlay row with wrong Y coordinate should be caught."""
        text = "[FROM LLM] The NOC2AXI row is located at Y=0 in the overlay layer."
        result = hg._validate_coordinates(text)
        assert "Y=0" not in result

    def test_tensix_y_contradiction_detected(self):
        """Tensix row with Y=4 (NOC2AXI row) should be caught as contradiction."""
        text = "[FROM LLM] The Tensix row is at Y=4 in the compute grid."
        result = hg._validate_coordinates(text)
        assert "Y=4" not in result

    def test_tensix_y_out_of_range_detected(self):
        """Tensix row with Y=5 (out of valid range) should be caught."""
        text = "[FROM LLM] The Tensix row is at Y=5 in the compute grid."
        result = hg._validate_coordinates(text)
        assert "Y=5" not in result

    def test_composite_tile_valid_row_span(self):
        """Composite tile spanning Y=3 and Y=4 should pass."""
        text = "[FROM LLM] The composite tile has a row span covering Y=3 and Y=4."
        assert hg._validate_coordinates(text) == text

    def test_composite_tile_invalid_row_span(self):
        """Composite tile with invalid row_span (e.g., Y=0 and Y=1) should be caught."""
        text = "[FROM LLM] The composite tile has a row span covering Y=0 and Y=1."
        result = hg._validate_coordinates(text)
        # Y=0 and Y=1 are not valid composite tile rows (should be Y=3+Y=4)
        assert "Y=0" not in result or "Y=1" not in result

    def test_incomplete_sentence_discards_paragraph(self):
        """If removing coordinates leaves incomplete text, discard paragraph."""
        text = "[FROM LLM] NOC2AXI row at Y=0."
        result = hg._validate_coordinates(text)
        assert result == ""

    def test_multiple_paragraphs_only_conflicting_affected(self):
        """Non-conflicting paragraphs should remain intact."""
        text = (
            "Normal paragraph without LLM inference.\n\n"
            "[FROM LLM] The NOC2AXI row is at Y=0 in the overlay layer."
        )
        result = hg._validate_coordinates(text)
        assert "Normal paragraph without LLM inference." in result

    def test_empty_input_returns_empty(self):
        """Empty string input should return empty string."""
        assert hg._validate_coordinates("") == ""

    def test_none_input_returns_none(self):
        """None input should return None."""
        assert hg._validate_coordinates(None) is None

    def test_warning_log_emitted_for_y_conflict(self, caplog):
        """Y-axis conflict should emit a warning log with coord_conflict event."""
        text = "[FROM LLM] The NOC2AXI row is at Y=0 in the overlay layer."
        with caplog.at_level(logging.WARNING):
            hg._validate_coordinates(text)
        assert "coord_conflict" in caplog.text

    def test_both_x_and_y_validated(self):
        """Both X and Y contradictions in same paragraph should be caught."""
        text = "[FROM LLM] East dispatch at X=0 and NOC2AXI row at Y=0."
        result = hg._validate_coordinates(text)
        assert "X=0" not in result
        assert "Y=0" not in result

    def test_backward_compatible_with_dispatch_only(self):
        """Should still work for dispatch-only validation (X-axis)."""
        text = "[FROM LLM] The East dispatch handles traffic at X=0 for the NoC router subsystem."
        result = hg._validate_coordinates(text)
        assert "X=0" not in result
        assert "NoC router subsystem" in result


class TestValidateYCoordinatesInSentence:
    """Tests for _validate_y_coordinates_in_sentence() helper."""

    def test_no_y_coords_returns_no_conflict(self):
        """Sentence without Y coordinates should return no conflict."""
        has_conflict, conflicts = hg._validate_y_coordinates_in_sentence(
            "The module is instantiated here."
        )
        assert has_conflict is False
        assert conflicts == {}

    def test_noc2axi_correct_y4(self):
        """NOC2AXI with Y=4 should not conflict."""
        has_conflict, _ = hg._validate_y_coordinates_in_sentence(
            "The NOC2AXI row is at Y=4."
        )
        assert has_conflict is False

    def test_noc2axi_wrong_y0(self):
        """NOC2AXI with Y=0 should conflict."""
        has_conflict, conflicts = hg._validate_y_coordinates_in_sentence(
            "The NOC2AXI row is at Y=0."
        )
        assert has_conflict is True
        assert "noc2axi_y" in conflicts
        assert conflicts["noc2axi_y"]["found"] == 0
        assert conflicts["noc2axi_y"]["expected"] == 4

    def test_tensix_valid_y2(self):
        """Tensix with Y=2 should not conflict."""
        has_conflict, _ = hg._validate_y_coordinates_in_sentence(
            "The Tensix row is at Y=2."
        )
        assert has_conflict is False

    def test_tensix_invalid_y4(self):
        """Tensix with Y=4 should conflict (Y=4 is NOC2AXI)."""
        has_conflict, conflicts = hg._validate_y_coordinates_in_sentence(
            "The Tensix row is at Y=4."
        )
        assert has_conflict is True
        assert "tensix_y" in conflicts

    def test_composite_tile_valid_span(self):
        """Composite tile with Y=3 and Y=4 should not conflict."""
        has_conflict, _ = hg._validate_y_coordinates_in_sentence(
            "The composite tile row span covers Y=3 and Y=4."
        )
        assert has_conflict is False

    def test_composite_tile_invalid_span(self):
        """Composite tile with Y=0 and Y=1 should conflict."""
        has_conflict, conflicts = hg._validate_y_coordinates_in_sentence(
            "The composite tile row span covers Y=0 and Y=1."
        )
        assert has_conflict is True
        assert "composite_tile_row_span" in conflicts


class TestPromptContainsYAxisInstruction:
    """Verify the Y-axis coordinate instructions are in the prompt."""

    def test_prompt_contains_noc2axi_y_instruction(self):
        prompt = hg._build_hdd_prompt(
            "tt_20260221", "Overlay", "block", {}, [], [], [],
        )
        assert "NOC2AXI row는 Y=4" in prompt

    def test_prompt_contains_tensix_y_instruction(self):
        prompt = hg._build_hdd_prompt(
            "tt_20260221", "NoC", "chip", {}, [], [], [],
        )
        assert "Tensix rows는 Y=0..3" in prompt

    def test_prompt_contains_composite_tile_instruction(self):
        prompt = hg._build_hdd_prompt(
            "tt_20260221", "Overlay", "block", {}, [], [], [],
        )
        assert "Composite tile" in prompt
        assert "row_span" in prompt


# ---------------------------------------------------------------------------
# 11. EP Table Y-axis constants validation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 11b. Graph Evidence Provider integration (Req 13.2, 13.3)
# ---------------------------------------------------------------------------

class TestGraphEvidenceIntegration:
    """Tests for Graph Evidence Provider integration in _build_hdd_prompt()."""

    def test_prompt_includes_graph_evidence_when_available(self):
        """When provider returns evidence, it should appear in the prompt."""
        mock_provider = MagicMock()
        mock_provider.format_evidence_for_prompt.return_value = (
            "[GRAPH EVIDENCE — NoC Section]\n"
            "- Summary: Module 'trinity_top' has 5 instances with 10 port bindings (topic: NoC)\n"
            "  - flit_out_req -> net_flit_req (output)"
        )

        prompt = hg._build_hdd_prompt(
            "tt_20260221", "NoC", "block",
            {"module_name": "trinity_top", "children": []},
            [], [], [],
            graph_evidence_provider=mock_provider,
        )
        assert "[GRAPH EVIDENCE — NoC Section]" in prompt
        assert "trinity_top" in prompt
        assert "flit_out_req" in prompt
        mock_provider.format_evidence_for_prompt.assert_called_once_with("NoC", "trinity_top")

    def test_prompt_no_evidence_when_neptune_unavailable(self):
        """When provider returns empty string (Neptune unavailable), prompt has no evidence block."""
        mock_provider = MagicMock()
        mock_provider.format_evidence_for_prompt.return_value = ""

        prompt = hg._build_hdd_prompt(
            "tt_20260221", "EDC", "subsystem",
            {"module_name": "tt_edc_top", "children": []},
            [], [], [],
            graph_evidence_provider=mock_provider,
        )
        assert "[GRAPH EVIDENCE" not in prompt
        mock_provider.format_evidence_for_prompt.assert_called_once_with("EDC", "tt_edc_top")

    def test_prompt_graceful_on_provider_exception(self):
        """When provider raises an exception, prompt falls back to claim-only mode."""
        mock_provider = MagicMock()
        mock_provider.format_evidence_for_prompt.side_effect = RuntimeError("Neptune timeout")

        prompt = hg._build_hdd_prompt(
            "tt_20260221", "Overlay", "block",
            {"module_name": "tt_overlay", "children": []},
            [], [], [],
            graph_evidence_provider=mock_provider,
        )
        # Should not crash, and should not contain evidence block
        assert "[GRAPH EVIDENCE" not in prompt
        # Prompt should still contain the standard content
        assert "tt_20260221" in prompt
        assert "Overlay" in prompt

    def test_prompt_no_provider_defaults_to_auto_create(self):
        """When no provider is passed, _get_graph_evidence_provider is called."""
        with patch("hdd_generator._get_graph_evidence_provider") as mock_get:
            mock_get.return_value = None  # Simulate no Neptune available
            prompt = hg._build_hdd_prompt(
                "tt_20260221", "NoC", "block", {}, [], [], [],
            )
            mock_get.assert_called_once()
            # No evidence block since provider is None
            assert "[GRAPH EVIDENCE" not in prompt

    def test_prompt_evidence_with_empty_topic_skips_retrieval(self):
        """When topic is empty, evidence retrieval is skipped."""
        mock_provider = MagicMock()

        prompt = hg._build_hdd_prompt(
            "tt_20260221", "", "chip", {}, [], [], [],
            graph_evidence_provider=mock_provider,
        )
        mock_provider.format_evidence_for_prompt.assert_not_called()
        assert "[GRAPH EVIDENCE" not in prompt

    def test_prompt_extracts_module_name_from_hierarchy(self):
        """Provider should receive module_name from hierarchy dict."""
        mock_provider = MagicMock()
        mock_provider.format_evidence_for_prompt.return_value = ""

        hg._build_hdd_prompt(
            "tt_20260221", "DFX", "block",
            {"module_name": "tt_noc_niu_router_dfx", "children": []},
            [], [], [],
            graph_evidence_provider=mock_provider,
        )
        mock_provider.format_evidence_for_prompt.assert_called_once_with(
            "DFX", "tt_noc_niu_router_dfx"
        )

    def test_prompt_empty_module_name_when_hierarchy_has_no_module(self):
        """When hierarchy has no module_name key, empty string is passed."""
        mock_provider = MagicMock()
        mock_provider.format_evidence_for_prompt.return_value = ""

        hg._build_hdd_prompt(
            "tt_20260221", "NoC", "block",
            {"children": []},  # No module_name key
            [], [], [],
            graph_evidence_provider=mock_provider,
        )
        mock_provider.format_evidence_for_prompt.assert_called_once_with("NoC", "")


class TestGetGraphEvidenceProvider:
    """Tests for _get_graph_evidence_provider() helper."""

    def test_returns_none_on_import_error(self):
        """Should return None if graph_evidence_provider module is not importable."""
        with patch("builtins.__import__", side_effect=ImportError("no module")):
            result = hg._get_graph_evidence_provider()
            assert result is None

    def test_returns_none_on_init_exception(self):
        """Should return None if GraphEvidenceProvider init raises."""
        # Patch the import to succeed but constructor to fail
        mock_module = MagicMock()
        mock_module.GraphEvidenceProvider.side_effect = RuntimeError("no creds")
        with patch.dict(sys.modules, {"graph_evidence_provider": mock_module}):
            result = hg._get_graph_evidence_provider()
            assert result is None


# ---------------------------------------------------------------------------
# 12. EP Table Y-axis constants validation (original section 11)
# ---------------------------------------------------------------------------

class TestEPTableYConstants:
    """Verify EP Table Y-axis constants are correctly defined."""

    def test_y_coords_noc2axi_is_4(self):
        assert hg.EP_TABLE_Y_COORDS["noc2axi"] == 4

    def test_y_coords_tensix_rows(self):
        assert hg.EP_TABLE_Y_COORDS["tensix_row0"] == 0
        assert hg.EP_TABLE_Y_COORDS["tensix_row1"] == 1
        assert hg.EP_TABLE_Y_COORDS["tensix_row2"] == 2
        assert hg.EP_TABLE_Y_COORDS["tensix_row3"] == 3

    def test_y_valid_range(self):
        assert list(hg.EP_TABLE_Y_VALID_RANGE) == [0, 1, 2, 3, 4]

    def test_y_noc2axi_constant(self):
        assert hg.EP_TABLE_Y_NOC2AXI == 4

    def test_y_tensix_range(self):
        assert list(hg.EP_TABLE_Y_TENSIX_RANGE) == [0, 1, 2, 3]

    def test_composite_tile_rows(self):
        assert hg.EP_TABLE_COMPOSITE_TILE_ROWS == {3, 4}

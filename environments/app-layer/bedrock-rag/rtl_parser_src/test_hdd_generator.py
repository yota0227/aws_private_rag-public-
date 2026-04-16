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

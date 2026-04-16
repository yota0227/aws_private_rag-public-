"""
Tests for claim_generator.py — Bedrock Claude claim generation with mocked AWS calls.

Covers:
- Prompt building
- Claude response parsing
- Claim validation and filtering
- Empty/error handling
- Token splitting integration
- Retry logic
- End-to-end generate_claims flow
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO

# Patch boto3 before importing to avoid real AWS calls
with patch("boto3.client"), patch("boto3.resource"):
    import claim_generator as cg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claude_response(claims_list):
    """Build a mock Bedrock invoke_model response."""
    body_content = json.dumps({
        "content": [{"type": "text", "text": json.dumps(claims_list)}],
    }).encode()
    mock_resp = {"body": BytesIO(body_content)}
    return mock_resp


def _sample_modules():
    return [
        {
            "module_name": "tt_noc_router",
            "port_list": "input i_clk, output o_data",
            "instance_list": "u_arb: noc_arbiter",
            "parameter_list": "WIDTH=64",
            "file_path": "rtl-sources/tt_20260221/noc/tt_noc_router.sv",
            "parsed_summary": "module tt_noc_router ports: input i_clk",
        },
    ]


def _sample_analysis_results():
    return {
        "hierarchy": {"module_name": "top", "children": []},
        "clock_domains": [{"domain": "noc_clock_domain", "signals": ["i_noc_clk"]}],
        "dataflow": [],
    }


# ---------------------------------------------------------------------------
# 1. Prompt building
# ---------------------------------------------------------------------------

class TestBuildClaimPrompt:
    def test_prompt_contains_pipeline_id(self):
        prompt = cg._build_claim_prompt(
            "tt_20260221", "NoC", _sample_modules(), _sample_analysis_results(),
        )
        assert "tt_20260221" in prompt

    def test_prompt_contains_topic(self):
        prompt = cg._build_claim_prompt(
            "tt_20260221", "NoC", _sample_modules(), _sample_analysis_results(),
        )
        assert "NoC" in prompt

    def test_prompt_contains_module_name(self):
        prompt = cg._build_claim_prompt(
            "tt_20260221", "NoC", _sample_modules(), _sample_analysis_results(),
        )
        assert "tt_noc_router" in prompt


# ---------------------------------------------------------------------------
# 2. Response parsing
# ---------------------------------------------------------------------------

class TestParseClaimsResponse:
    def test_valid_json_array(self):
        text = json.dumps([{"claim_type": "structural"}])
        result = cg._parse_claims_response(text)
        assert len(result) == 1
        assert result[0]["claim_type"] == "structural"

    def test_markdown_fenced_json(self):
        text = "```json\n" + json.dumps([{"x": 1}]) + "\n```"
        result = cg._parse_claims_response(text)
        assert len(result) == 1

    def test_invalid_json_returns_empty(self):
        result = cg._parse_claims_response("not json at all")
        assert result == []

    def test_non_array_json_returns_empty(self):
        result = cg._parse_claims_response('{"key": "value"}')
        assert result == []


# ---------------------------------------------------------------------------
# 3. Empty modules
# ---------------------------------------------------------------------------

class TestGenerateClaimsEmpty:
    def test_empty_modules_returns_empty(self):
        result = cg.generate_claims("tt_20260221", "NoC", [], {})
        assert result == []


# ---------------------------------------------------------------------------
# 4. Successful claim generation
# ---------------------------------------------------------------------------

class TestGenerateClaimsSuccess:
    @patch.object(cg, "_invoke_claude")
    def test_generates_valid_claims(self, mock_claude):
        raw_claims = [
            {
                "claim_type": "connectivity",
                "claim_text": "Router has 4 directional ports",
                "confidence_score": 0.9,
                "module_name": "tt_noc_router",
                "source_files": ["noc/tt_noc_router.sv"],
            },
        ]
        mock_claude.return_value = json.dumps(raw_claims)

        result = cg.generate_claims(
            "tt_20260221", "NoC", _sample_modules(), _sample_analysis_results(),
        )
        assert len(result) == 1
        assert result[0]["claim_type"] == "connectivity"
        assert result[0]["topic"] == "NoC"
        assert result[0]["pipeline_id"] == "tt_20260221"
        assert result[0]["claim_id"].startswith("clm_tt_20260221_NoC_")

    @patch.object(cg, "_invoke_claude")
    def test_filters_invalid_claims(self, mock_claude):
        raw_claims = [
            {
                "claim_type": "invalid_type",
                "claim_text": "Bad claim",
                "confidence_score": 0.5,
                "module_name": "mod",
                "source_files": ["f.sv"],
            },
        ]
        mock_claude.return_value = json.dumps(raw_claims)

        result = cg.generate_claims(
            "tt_20260221", "NoC", _sample_modules(), _sample_analysis_results(),
        )
        assert len(result) == 0


# ---------------------------------------------------------------------------
# 5. Claude invocation failure
# ---------------------------------------------------------------------------

class TestGenerateClaimsFailure:
    @patch.object(cg, "_invoke_claude", side_effect=RuntimeError("timeout"))
    def test_claude_failure_returns_empty(self, mock_claude):
        result = cg.generate_claims(
            "tt_20260221", "NoC", _sample_modules(), _sample_analysis_results(),
        )
        assert result == []


# ---------------------------------------------------------------------------
# 6. Invoke Claude retry logic
# ---------------------------------------------------------------------------

class TestInvokeClaude:
    @patch("claim_generator.boto3.client")
    def test_retry_on_first_failure(self, mock_boto_client):
        mock_bedrock = MagicMock()
        mock_boto_client.return_value = mock_bedrock

        # First call fails, second succeeds
        mock_bedrock.invoke_model.side_effect = [
            Exception("transient error"),
            {"body": BytesIO(json.dumps({
                "content": [{"type": "text", "text": "hello"}],
            }).encode())},
        ]

        result = cg._invoke_claude("test prompt")
        assert result == "hello"
        assert mock_bedrock.invoke_model.call_count == 2

    @patch("claim_generator.boto3.client")
    def test_all_retries_exhausted_raises(self, mock_boto_client):
        mock_bedrock = MagicMock()
        mock_boto_client.return_value = mock_bedrock
        mock_bedrock.invoke_model.side_effect = Exception("persistent error")

        with pytest.raises(RuntimeError, match="persistent error"):
            cg._invoke_claude("test prompt")


# ---------------------------------------------------------------------------
# 7. Claim ID sequencing
# ---------------------------------------------------------------------------

class TestClaimIdSequencing:
    @patch.object(cg, "_invoke_claude")
    def test_claim_ids_are_sequential(self, mock_claude):
        raw_claims = [
            {
                "claim_type": "structural",
                "claim_text": f"Claim {i}",
                "confidence_score": 0.8,
                "module_name": "tt_noc_router",
                "source_files": ["f.sv"],
            }
            for i in range(3)
        ]
        mock_claude.return_value = json.dumps(raw_claims)

        result = cg.generate_claims(
            "tt_20260221", "NoC", _sample_modules(), _sample_analysis_results(),
        )
        assert len(result) == 3
        ids = [c["claim_id"] for c in result]
        assert ids == [
            "clm_tt_20260221_NoC_001",
            "clm_tt_20260221_NoC_002",
            "clm_tt_20260221_NoC_003",
        ]


# ---------------------------------------------------------------------------
# 8. Source files fallback
# ---------------------------------------------------------------------------

class TestSourceFilesFallback:
    @patch.object(cg, "_invoke_claude")
    def test_missing_source_files_uses_module_paths(self, mock_claude):
        raw_claims = [
            {
                "claim_type": "behavioral",
                "claim_text": "Module does X",
                "confidence_score": 0.7,
                "module_name": "tt_noc_router",
                # No source_files key
            },
        ]
        mock_claude.return_value = json.dumps(raw_claims)

        result = cg.generate_claims(
            "tt_20260221", "NoC", _sample_modules(), _sample_analysis_results(),
        )
        assert len(result) == 1
        assert "tt_noc_router.sv" in result[0]["source_files"][0]

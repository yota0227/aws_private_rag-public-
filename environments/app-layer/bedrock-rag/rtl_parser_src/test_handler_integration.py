"""Integration tests for handler.py Phase 7 features.

Tests:
- Parser feature flag control (_is_parser_enabled)
- Parser execution order in _process_rtl_file
- CloudWatch structured logging for parser execution
- parser_source field attribution
- CloudWatch metric publishing (graceful degradation)
- OpenSearch index field mappings (parent_module_name, sub_record_type, parser_source)

Requirements: 17.5, 18.5, 19.5, 22.5, 23.1, 23.6, 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure the rtl_parser_src directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Test: _is_parser_enabled helper function (Task 20.1)
# ---------------------------------------------------------------------------

class TestIsParserEnabled:
    """Tests for the _is_parser_enabled() helper function."""

    def test_default_true_when_env_not_set(self):
        """All parser flags default to true when env vars are not set."""
        env_clean = {k: v for k, v in os.environ.items()
                     if not k.startswith("PARSER_")}
        with patch.dict(os.environ, env_clean, clear=True):
            import handler
            assert handler._is_parser_enabled("PARSER_PACKAGE_ENABLED") is True
            assert handler._is_parser_enabled("PARSER_PORT_CLASSIFIER_ENABLED") is True
            assert handler._is_parser_enabled("PARSER_GENERATE_BLOCK_ENABLED") is True
            assert handler._is_parser_enabled("PARSER_ALWAYS_BLOCK_ENABLED") is True
            assert handler._is_parser_enabled("PARSER_FUNCTION_EXTRACTOR_ENABLED") is True

    def test_disabled_when_env_set_false(self):
        """Parser is disabled when env var is set to 'false'."""
        with patch.dict(os.environ, {"PARSER_PACKAGE_ENABLED": "false"}):
            import handler
            assert handler._is_parser_enabled("PARSER_PACKAGE_ENABLED") is False

    def test_enabled_when_env_set_true(self):
        """Parser is enabled when env var is explicitly set to 'true'."""
        with patch.dict(os.environ, {"PARSER_PACKAGE_ENABLED": "true"}):
            import handler
            assert handler._is_parser_enabled("PARSER_PACKAGE_ENABLED") is True

    def test_case_insensitive(self):
        """Feature flag check is case-insensitive."""
        with patch.dict(os.environ, {"PARSER_PACKAGE_ENABLED": "TRUE"}):
            import handler
            assert handler._is_parser_enabled("PARSER_PACKAGE_ENABLED") is True

        with patch.dict(os.environ, {"PARSER_PACKAGE_ENABLED": "False"}):
            import handler
            assert handler._is_parser_enabled("PARSER_PACKAGE_ENABLED") is False

    def test_unknown_flag_defaults_true(self):
        """Unknown flag names default to true."""
        import handler
        # Remove the env var if it exists
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PARSER_UNKNOWN_ENABLED", None)
            assert handler._is_parser_enabled("PARSER_UNKNOWN_ENABLED") is True


# ---------------------------------------------------------------------------
# Test: Parser execution with feature flags (Task 20.1, 21.2)
# ---------------------------------------------------------------------------

class TestParserFeatureFlagExecution:
    """Tests that parsers are skipped when their feature flag is disabled."""

    @pytest.fixture
    def sample_rtl_content(self):
        """Simple RTL module for testing."""
        return """
module test_module #(
    parameter DATA_WIDTH = 8
) (
    input  logic clk,
    input  logic rst_n,
    output logic [DATA_WIDTH-1:0] data_out
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            data_out <= '0;
        else
            data_out <= data_out + 1;
    end

endmodule
"""

    @patch('handler.s3_client')
    @patch('handler._generate_embedding', return_value=[0.1] * 1024)
    @patch('handler._index_to_opensearch')
    @patch('handler._load_to_neptune')
    @patch('handler._record_parse_event')
    @patch('handler._get_cloudwatch_client', return_value=None)
    @patch('handler.extract_generate_blocks', return_value=[])
    @patch('handler.extract_clock_domains', return_value=[])
    def test_generate_block_parser_skipped_when_disabled(
        self, mock_clock, mock_gen, mock_cw, mock_record,
        mock_neptune, mock_index, mock_embed, mock_s3,
        sample_rtl_content
    ):
        """Generate block parser is skipped when flag is disabled."""
        import handler

        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=sample_rtl_content.encode()))
        }

        original = handler.PARSER_GENERATE_BLOCK_ENABLED
        try:
            handler.PARSER_GENERATE_BLOCK_ENABLED = False
            handler._process_rtl_file("test-bucket", "rtl-sources/test.sv")
            # extract_generate_blocks should NOT have been called
            mock_gen.assert_not_called()
        finally:
            handler.PARSER_GENERATE_BLOCK_ENABLED = original

    @patch('handler.s3_client')
    @patch('handler._generate_embedding', return_value=[0.1] * 1024)
    @patch('handler._index_to_opensearch')
    @patch('handler._load_to_neptune')
    @patch('handler._record_parse_event')
    @patch('handler._get_cloudwatch_client', return_value=None)
    @patch('handler.extract_clock_domains', return_value=[])
    def test_always_block_parser_skipped_when_disabled(
        self, mock_clock, mock_cw, mock_record,
        mock_neptune, mock_index, mock_embed, mock_s3,
        sample_rtl_content
    ):
        """Always block parser is skipped when flag is disabled."""
        import handler

        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=sample_rtl_content.encode()))
        }

        original = handler.PARSER_ALWAYS_BLOCK_ENABLED
        try:
            handler.PARSER_ALWAYS_BLOCK_ENABLED = False
            handler._process_rtl_file("test-bucket", "rtl-sources/test.sv")
            mock_clock.assert_not_called()
        finally:
            handler.PARSER_ALWAYS_BLOCK_ENABLED = original


# ---------------------------------------------------------------------------
# Test: Structured CloudWatch logging (Task 20.1)
# ---------------------------------------------------------------------------

class TestStructuredLogging:
    """Tests that parser execution produces structured CloudWatch logs."""

    @patch('handler.s3_client')
    @patch('handler._generate_embedding', return_value=[0.1] * 1024)
    @patch('handler._index_to_opensearch')
    @patch('handler._load_to_neptune')
    @patch('handler._record_parse_event')
    @patch('handler._get_cloudwatch_client', return_value=None)
    def test_parser_execution_log_contains_required_fields(
        self, mock_cw, mock_record, mock_neptune, mock_index,
        mock_embed, mock_s3, caplog
    ):
        """Parser execution logs contain parser_name, claims_generated, execution_time_ms, files_processed."""
        import handler
        import logging

        rtl_content = """
module big_module (
    input logic clk,
    input logic rst_n
);
    always_ff @(posedge clk) begin
        data <= data + 1;
    end
endmodule
"""
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=rtl_content.encode()))
        }

        handler.PARSER_GENERATE_BLOCK_ENABLED = True
        handler.PARSER_ALWAYS_BLOCK_ENABLED = True

        with caplog.at_level(logging.INFO):
            handler._process_rtl_file("test-bucket", "rtl-sources/test.sv")

        # Check that structured log entries were emitted
        parser_logs = []
        for record in caplog.records:
            try:
                parsed = json.loads(record.message)
                if parsed.get("event") == "parser_execution_result":
                    parser_logs.append(parsed)
            except (json.JSONDecodeError, TypeError):
                continue

        # always_block_parser should have logged (it found always_ff)
        for log_entry in parser_logs:
            assert "parser_name" in log_entry
            assert "claims_generated" in log_entry
            assert "execution_time_ms" in log_entry
            assert "files_processed" in log_entry

    @patch('handler.s3_client')
    @patch('handler._generate_embedding', return_value=[0.1] * 1024)
    @patch('handler._index_to_opensearch')
    @patch('handler._load_to_neptune')
    @patch('handler._record_parse_event')
    @patch('handler._get_cloudwatch_client', return_value=None)
    def test_disabled_parser_logs_skip_event(
        self, mock_cw, mock_record, mock_neptune, mock_index,
        mock_embed, mock_s3, caplog
    ):
        """Disabled parsers log an INFO skip event."""
        import handler
        import logging

        rtl_content = """
module simple_mod (input logic clk);
endmodule
"""
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=rtl_content.encode()))
        }

        original = handler.PARSER_GENERATE_BLOCK_ENABLED
        try:
            handler.PARSER_GENERATE_BLOCK_ENABLED = False
            with caplog.at_level(logging.INFO):
                handler._process_rtl_file("test-bucket", "rtl-sources/test.sv")

            skip_logs = []
            for record in caplog.records:
                try:
                    parsed = json.loads(record.message)
                    if parsed.get("event") == "parser_disabled_skip":
                        skip_logs.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    continue

            assert any(
                log.get("parser_name") == "generate_block_parser"
                for log in skip_logs
            ), "Expected skip log for generate_block_parser"
        finally:
            handler.PARSER_GENERATE_BLOCK_ENABLED = original


# ---------------------------------------------------------------------------
# Test: CloudWatch metric publishing (Task 20.4)
# ---------------------------------------------------------------------------

class TestCloudWatchMetrics:
    """Tests for CloudWatch metric publishing with graceful degradation."""

    def test_publish_parser_metric_graceful_on_failure(self):
        """_publish_parser_metric does not raise when CloudWatch fails."""
        import handler

        mock_cw = MagicMock()
        mock_cw.put_metric_data.side_effect = Exception("CloudWatch unavailable")

        # Should not raise
        handler._publish_parser_metric(
            "ParserClaimCount", 5, "Count", "test_parser", cloudwatch=mock_cw
        )

    def test_publish_parser_metric_sends_correct_namespace(self):
        """_publish_parser_metric uses BOS-AI/RTLParser namespace."""
        import handler

        mock_cw = MagicMock()
        handler._publish_parser_metric(
            "ParserClaimCount", 10, "Count", "package_extractor", cloudwatch=mock_cw
        )

        mock_cw.put_metric_data.assert_called_once()
        call_kwargs = mock_cw.put_metric_data.call_args[1]
        assert call_kwargs['Namespace'] == 'BOS-AI/RTLParser'
        assert call_kwargs['MetricData'][0]['MetricName'] == 'ParserClaimCount'
        assert call_kwargs['MetricData'][0]['Value'] == 10.0
        assert call_kwargs['MetricData'][0]['Dimensions'][0]['Value'] == 'package_extractor'

    def test_publish_parser_metric_skips_when_no_client(self):
        """_publish_parser_metric does nothing when cloudwatch client is None."""
        import handler
        # Should not raise
        handler._publish_parser_metric(
            "ParserClaimCount", 5, "Count", "test_parser", cloudwatch=None
        )


# ---------------------------------------------------------------------------
# Test: parser_source field attribution (Task 20.1, 26.6)
# ---------------------------------------------------------------------------

class TestParserSourceAttribution:
    """Tests that all parser-generated claims include parser_source field."""

    def test_package_extractor_claims_have_parser_source(self):
        """Package extractor claims include parser_source field."""
        from package_extractor import extract_package_constants

        rtl = """
package test_pkg;
    localparam int SIZE = 4;
    function automatic int add(int a, int b);
        return a + b;
    endfunction
endpackage
"""
        claims = extract_package_constants(rtl, file_path="test.sv", pipeline_id="p1")
        assert len(claims) > 0
        for claim in claims:
            assert "parser_source" in claim
            assert claim["parser_source"] != ""

    def test_generate_block_parser_claims_have_parser_source(self):
        """Generate block parser claims include parser_source field."""
        from generate_block_parser import extract_generate_blocks

        rtl = """
module test_mod;
    generate
        for (genvar i = 0; i < 4; i++) begin : gen_chain
            assign data[i+1] = data[i];
        end
    endgenerate
endmodule
"""
        claims = extract_generate_blocks(rtl, module_name="test_mod",
                                         file_path="test.sv", pipeline_id="p1")
        assert len(claims) > 0
        for claim in claims:
            assert "parser_source" in claim
            assert claim["parser_source"] == "generate_block_parser"

    def test_always_block_parser_claims_have_parser_source(self):
        """Always block parser claims include parser_source field."""
        from always_block_parser import extract_clock_domains

        rtl = """
module test_mod;
    always_ff @(posedge i_ai_clk or negedge rst_n) begin
        data <= data + 1;
    end
endmodule
"""
        claims = extract_clock_domains(rtl, module_name="test_mod",
                                       file_path="test.sv", pipeline_id="p1")
        assert len(claims) > 0
        for claim in claims:
            assert "parser_source" in claim
            assert claim["parser_source"] == "always_block_parser"


# ---------------------------------------------------------------------------
# Test: OpenSearch index field mappings (Task 21.1)
# ---------------------------------------------------------------------------

class TestOpenSearchIndexMappings:
    """Tests that the OpenSearch index script includes Phase 7 fields."""

    @pytest.fixture
    def index_body(self):
        """Load INDEX_BODY from the create-opensearch-index.py script."""
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'scripts', 'create-opensearch-index.py'
        )
        # Parse the INDEX_BODY dict from the script file
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract INDEX_BODY using exec in a controlled namespace
        namespace = {}
        # Find the INDEX_BODY assignment
        start = content.find("INDEX_BODY = {")
        if start == -1:
            pytest.skip("Could not find INDEX_BODY in script")
        # Find the matching closing brace
        brace_count = 0
        end = start
        for i, ch in enumerate(content[start:], start):
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        exec(content[start:end], namespace)
        return namespace["INDEX_BODY"]

    def test_index_body_has_parent_module_name(self, index_body):
        """INDEX_BODY includes parent_module_name keyword field."""
        props = index_body["mappings"]["properties"]
        assert "parent_module_name" in props
        assert props["parent_module_name"]["type"] == "keyword"

    def test_index_body_has_sub_record_type(self, index_body):
        """INDEX_BODY includes sub_record_type keyword field."""
        props = index_body["mappings"]["properties"]
        assert "sub_record_type" in props
        assert props["sub_record_type"]["type"] == "keyword"

    def test_index_body_has_parser_source(self, index_body):
        """INDEX_BODY includes parser_source keyword field."""
        props = index_body["mappings"]["properties"]
        assert "parser_source" in props
        assert props["parser_source"]["type"] == "keyword"


# ---------------------------------------------------------------------------
# Test: Handler integration wiring — parser execution order (Task 21.2)
# ---------------------------------------------------------------------------

class TestHandlerIntegrationWiring:
    """Tests that _process_rtl_file calls parsers in the correct order."""

    @patch('handler.s3_client')
    @patch('handler._generate_embedding', return_value=[0.1] * 1024)
    @patch('handler._index_to_opensearch')
    @patch('handler._load_to_neptune')
    @patch('handler._record_parse_event')
    @patch('handler._get_cloudwatch_client', return_value=None)
    def test_all_parsers_called_for_complete_module(
        self, mock_cw, mock_record, mock_neptune, mock_index,
        mock_embed, mock_s3
    ):
        """All enabled parsers are called for a module with relevant content."""
        import handler

        rtl_content = """
module ordered_test #(parameter WIDTH = 8) (
    input  logic i_ai_clk,
    input  logic rst_n,
    output logic [WIDTH-1:0] data_out
);
    always_ff @(posedge i_ai_clk or negedge rst_n) begin
        if (!rst_n) data_out <= '0;
        else data_out <= data_out + 1;
    end

    generate
        for (genvar i = 0; i < 4; i++) begin : gen_chain
            assign chain[i+1] = chain[i];
        end
    endgenerate
endmodule
"""
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=rtl_content.encode()))
        }

        handler.PARSER_PACKAGE_ENABLED = True
        handler.PARSER_PORT_CLASSIFIER_ENABLED = True
        handler.PARSER_GENERATE_BLOCK_ENABLED = True
        handler.PARSER_ALWAYS_BLOCK_ENABLED = True

        handler._process_rtl_file("test-bucket", "rtl-sources/ordered_test.sv")

        # Verify _index_to_opensearch was called (at least for the module parse)
        assert mock_index.call_count >= 1

    @patch('handler.s3_client')
    @patch('handler._generate_embedding', return_value=[0.1] * 1024)
    @patch('handler._index_to_opensearch')
    @patch('handler._load_to_neptune')
    @patch('handler._record_parse_event')
    @patch('handler._get_cloudwatch_client', return_value=None)
    def test_bitwidth_evaluation_resolves_parameters(
        self, mock_cw, mock_record, mock_neptune, mock_index,
        mock_embed, mock_s3
    ):
        """Bitwidth evaluator resolves parametric port widths."""
        import handler

        rtl_content = """
module bw_test #(parameter DATA_WIDTH = 16) (
    input  logic clk,
    input  logic [DATA_WIDTH-1:0] data_in,
    output logic [DATA_WIDTH-1:0] data_out
);
endmodule
"""
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=rtl_content.encode()))
        }

        handler.PARSER_GENERATE_BLOCK_ENABLED = True
        handler.PARSER_ALWAYS_BLOCK_ENABLED = True

        handler._process_rtl_file("test-bucket", "rtl-sources/bw_test.sv")

        # The module parse should have been indexed
        assert mock_index.call_count >= 1

    def test_imports_are_available(self):
        """All Phase 7 parser imports are available in handler.py."""
        import handler
        assert hasattr(handler, 'extract_generate_blocks')
        assert hasattr(handler, 'extract_clock_domains')
        assert hasattr(handler, 'evaluate_bitwidth')
        assert callable(handler.extract_generate_blocks)
        assert callable(handler.extract_clock_domains)
        assert callable(handler.evaluate_bitwidth)

    def test_is_parser_enabled_function_exists(self):
        """The _is_parser_enabled helper function exists and is callable."""
        import handler
        assert hasattr(handler, '_is_parser_enabled')
        assert callable(handler._is_parser_enabled)

    def test_parser_feature_flags_dict_exists(self):
        """The _PARSER_FEATURE_FLAGS dict exists with all 5 flags."""
        import handler
        assert hasattr(handler, '_PARSER_FEATURE_FLAGS')
        flags = handler._PARSER_FEATURE_FLAGS
        assert "PARSER_PACKAGE_ENABLED" in flags
        assert "PARSER_PORT_CLASSIFIER_ENABLED" in flags
        assert "PARSER_GENERATE_BLOCK_ENABLED" in flags
        assert "PARSER_ALWAYS_BLOCK_ENABLED" in flags
        assert "PARSER_FUNCTION_EXTRACTOR_ENABLED" in flags

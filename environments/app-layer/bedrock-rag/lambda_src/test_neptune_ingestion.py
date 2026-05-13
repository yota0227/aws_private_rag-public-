"""Unit tests for neptune_ingestion.py — CLI interface and error handling.

Tests cover:
- CLI argument parsing (--pipeline-id, --neptune-endpoint, --batch-size, --dry-run, --verbose)
- Neptune endpoint missing → exit code 1 (no network attempt)
- Neptune endpoint unreachable → exit code 1
- Dry-run mode → exit code 0 (no connectivity check)
- SigV4 client initialization

Requirements: 12.1, 12.3, 12.4
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

# Ensure lambda_src is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neptune_ingestion import (
    parse_args,
    main,
    _resolve_neptune_endpoint,
    NeptuneSigV4Client,
)


class TestParseArgs:
    """Tests for CLI argument parsing."""

    def test_required_pipeline_id(self):
        """--pipeline-id is required."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args([])
        assert exc_info.value.code == 2  # argparse error

    def test_pipeline_id_only(self):
        """Minimal valid invocation with just --pipeline-id."""
        args = parse_args(["--pipeline-id", "tt_20260221"])
        assert args.pipeline_id == "tt_20260221"
        assert args.neptune_endpoint is None
        assert args.batch_size == 50
        assert args.dry_run is False
        assert args.verbose is False

    def test_all_options(self):
        """All CLI options are parsed correctly."""
        args = parse_args([
            "--pipeline-id", "tt_20260301",
            "--neptune-endpoint", "neptune-test.cluster.amazonaws.com",
            "--batch-size", "100",
            "--dry-run",
            "--verbose",
        ])
        assert args.pipeline_id == "tt_20260301"
        assert args.neptune_endpoint == "neptune-test.cluster.amazonaws.com"
        assert args.batch_size == 100
        assert args.dry_run is True
        assert args.verbose is True

    def test_batch_size_default(self):
        """Default batch size is 50."""
        args = parse_args(["--pipeline-id", "test"])
        assert args.batch_size == 50

    def test_batch_size_custom(self):
        """Custom batch size is accepted."""
        args = parse_args(["--pipeline-id", "test", "--batch-size", "25"])
        assert args.batch_size == 25


class TestResolveNeptuneEndpoint:
    """Tests for Neptune endpoint resolution priority."""

    def test_cli_arg_takes_priority(self):
        """CLI argument overrides env var."""
        with patch.dict(os.environ, {"NEPTUNE_ENDPOINT": "env-endpoint.com"}):
            result = _resolve_neptune_endpoint("cli-endpoint.com")
            assert result == "cli-endpoint.com"

    def test_env_var_fallback(self):
        """Falls back to NEPTUNE_ENDPOINT env var when CLI arg is None."""
        with patch.dict(os.environ, {"NEPTUNE_ENDPOINT": "env-endpoint.com"}):
            result = _resolve_neptune_endpoint(None)
            assert result == "env-endpoint.com"

    def test_empty_when_nothing_set(self):
        """Returns empty string when neither CLI nor env is set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove NEPTUNE_ENDPOINT if present
            os.environ.pop("NEPTUNE_ENDPOINT", None)
            result = _resolve_neptune_endpoint(None)
            assert result == ""


class TestMainEndpointMissing:
    """Tests for Requirement 12.4: Neptune endpoint not configured → exit 1."""

    def test_exit_1_when_no_endpoint(self):
        """Exit code 1 when Neptune endpoint is not configured (no network attempt)."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NEPTUNE_ENDPOINT", None)
            exit_code = main(["--pipeline-id", "tt_20260221"])
            assert exit_code == 1

    def test_no_network_call_when_endpoint_missing(self):
        """No network call is made when endpoint is missing."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NEPTUNE_ENDPOINT", None)
            with patch("neptune_ingestion.NeptuneSigV4Client") as mock_client:
                exit_code = main(["--pipeline-id", "tt_20260221"])
                assert exit_code == 1
                mock_client.assert_not_called()


class TestMainEndpointUnreachable:
    """Tests for Requirement 12.4: Neptune endpoint unreachable → exit 1."""

    @patch("neptune_ingestion.NeptuneSigV4Client")
    def test_exit_1_when_unreachable(self, mock_client_cls):
        """Exit code 1 when Neptune endpoint is configured but unreachable."""
        mock_instance = MagicMock()
        mock_instance.health_check.return_value = False
        mock_client_cls.return_value = mock_instance

        exit_code = main([
            "--pipeline-id", "tt_20260221",
            "--neptune-endpoint", "neptune-unreachable.cluster.amazonaws.com",
        ])
        assert exit_code == 1

    @patch("neptune_ingestion.NeptuneSigV4Client")
    def test_exit_1_on_connection_exception(self, mock_client_cls):
        """Exit code 1 when health_check raises an exception."""
        mock_instance = MagicMock()
        mock_instance.health_check.side_effect = Exception("Connection refused")
        mock_client_cls.return_value = mock_instance

        exit_code = main([
            "--pipeline-id", "tt_20260221",
            "--neptune-endpoint", "neptune-error.cluster.amazonaws.com",
        ])
        assert exit_code == 1


class TestMainDryRun:
    """Tests for --dry-run mode."""

    @patch("neptune_ingestion.scan_dynamodb_records")
    def test_dry_run_exits_0_without_neptune_check(self, mock_scan):
        """Dry-run mode exits 0 without checking Neptune connectivity."""
        mock_scan.return_value = []
        with patch("neptune_ingestion.NeptuneSigV4Client") as mock_client_cls:
            exit_code = main([
                "--pipeline-id", "tt_20260221",
                "--neptune-endpoint", "neptune-test.cluster.amazonaws.com",
                "--dry-run",
            ])
            assert exit_code == 0
            mock_client_cls.assert_not_called()


class TestMainSuccess:
    """Tests for successful pipeline execution."""

    @patch("neptune_ingestion.scan_dynamodb_records")
    @patch("neptune_ingestion.NeptuneSigV4Client")
    def test_exit_0_when_neptune_reachable(self, mock_client_cls, mock_scan):
        """Exit code 0 when Neptune endpoint is reachable."""
        mock_instance = MagicMock()
        mock_instance.health_check.return_value = True
        mock_client_cls.return_value = mock_instance
        mock_scan.return_value = []

        exit_code = main([
            "--pipeline-id", "tt_20260221",
            "--neptune-endpoint", "neptune-ok.cluster.amazonaws.com",
        ])
        assert exit_code == 0


class TestNeptuneSigV4Client:
    """Tests for NeptuneSigV4Client initialization."""

    @patch("neptune_ingestion.boto3.Session")
    def test_client_initialization(self, mock_session_cls):
        """Client initializes with endpoint and resolves credentials."""
        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_creds.access_key = "AKIATEST"
        mock_creds.secret_key = "secret"
        mock_creds.token = "token"
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
        mock_session.region_name = "ap-northeast-2"
        mock_session_cls.return_value = mock_session

        client = NeptuneSigV4Client(endpoint="neptune-test.cluster.amazonaws.com")
        assert client.endpoint == "neptune-test.cluster.amazonaws.com"
        assert client.neptune_url == "https://neptune-test.cluster.amazonaws.com:8182/openCypher"
        assert client.region == "ap-northeast-2"

    @patch("neptune_ingestion.boto3.Session")
    def test_client_custom_region(self, mock_session_cls):
        """Client uses custom region when provided."""
        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
        mock_session.region_name = "us-east-1"
        mock_session_cls.return_value = mock_session

        client = NeptuneSigV4Client(
            endpoint="neptune-test.cluster.amazonaws.com",
            region="us-west-2",
        )
        assert client.region == "us-west-2"


# ===========================================================================
# Task 9.2 Tests — DynamoDB Scan and Data Transformation
# Requirements: 10.1, 10.2, 10.3, 10.4
# ===========================================================================

from neptune_ingestion import (
    scan_dynamodb_records,
    transform_module_parse_to_module_def,
    transform_module_parse_to_instances,
    transform_module_parse_to_port_nodes,
    transform_wire_claim_to_signal,
    transform_clock_domain_claim,
    transform_records_to_nodes,
    _decimal_to_native,
    DYNAMODB_TABLE_NAME,
)
from decimal import Decimal


class TestDecimalToNative:
    """Tests for Decimal conversion helper."""

    def test_integer_decimal(self):
        assert _decimal_to_native(Decimal("42")) == 42
        assert isinstance(_decimal_to_native(Decimal("42")), int)

    def test_float_decimal(self):
        assert _decimal_to_native(Decimal("3.14")) == 3.14
        assert isinstance(_decimal_to_native(Decimal("3.14")), float)

    def test_non_decimal_passthrough(self):
        assert _decimal_to_native("hello") == "hello"
        assert _decimal_to_native(None) is None
        assert _decimal_to_native(7) == 7


class TestTransformModuleParseToModuleDef:
    """Tests for module_parse → ModuleDef node transformation (Req 10.1)."""

    def test_basic_module_parse(self):
        """module_parse record produces ModuleDef node with correct properties."""
        record = {
            "analysis_type": "module_parse",
            "module_name": "trinity_top",
            "file_path": "/rtl/trinity_top.sv",
            "pipeline_id": "tt_20260221",
            "module_type": "top_module",
        }
        result = transform_module_parse_to_module_def(record)
        assert result is not None
        assert result["label"] == "ModuleDef"
        assert result["properties"]["name"] == "trinity_top"
        assert result["properties"]["file_path"] == "/rtl/trinity_top.sv"
        assert result["properties"]["pipeline_id"] == "tt_20260221"
        assert result["properties"]["module_type"] == "top_module"

    def test_missing_module_name_returns_none(self):
        """Record without module_name returns None."""
        record = {"analysis_type": "module_parse", "file_path": "/rtl/test.sv"}
        assert transform_module_parse_to_module_def(record) is None

    def test_defaults_for_missing_fields(self):
        """Missing optional fields get default values."""
        record = {"module_name": "test_mod"}
        result = transform_module_parse_to_module_def(record)
        assert result["properties"]["file_path"] == ""
        assert result["properties"]["pipeline_id"] == ""
        assert result["properties"]["module_type"] == "module"


class TestTransformModuleParseToInstances:
    """Tests for module_parse → Instance node transformation (Req 10.1)."""

    def test_string_instance_list(self):
        """Simple string instance names are transformed correctly."""
        record = {
            "module_name": "trinity_top",
            "pipeline_id": "tt_20260221",
            "instance_list": ["u_router", "u_noc"],
        }
        result = transform_module_parse_to_instances(record)
        assert len(result) == 2
        assert result[0]["label"] == "Instance"
        assert result[0]["properties"]["instance_name"] == "u_router"
        assert result[0]["properties"]["hier_path"] == "trinity_top/u_router"
        assert result[0]["properties"]["parent_instance"] == "trinity_top"

    def test_dict_instance_list(self):
        """Dict instance entries with full properties are transformed."""
        record = {
            "module_name": "trinity_top",
            "pipeline_id": "tt_20260221",
            "instance_list": [
                {
                    "instance_name": "u_router",
                    "hier_path": "trinity_top/gen_noc/u_router",
                    "generate_scope": "gen_noc",
                    "x": Decimal("3"),
                    "y": Decimal("2"),
                    "parent_instance": "trinity_top",
                }
            ],
        }
        result = transform_module_parse_to_instances(record)
        assert len(result) == 1
        inst = result[0]
        assert inst["properties"]["instance_name"] == "u_router"
        assert inst["properties"]["hier_path"] == "trinity_top/gen_noc/u_router"
        assert inst["properties"]["generate_scope"] == "gen_noc"
        assert inst["properties"]["x"] == 3
        assert inst["properties"]["y"] == 2

    def test_json_string_instance_list(self):
        """JSON-encoded instance_list string is parsed correctly."""
        record = {
            "module_name": "mod_a",
            "pipeline_id": "tt_test",
            "instance_list": '["inst_1", "inst_2"]',
        }
        result = transform_module_parse_to_instances(record)
        assert len(result) == 2

    def test_empty_instance_list(self):
        """Empty instance_list returns empty list."""
        record = {"module_name": "mod_a", "pipeline_id": "tt_test", "instance_list": []}
        assert transform_module_parse_to_instances(record) == []

    def test_dict_instance_missing_name_skipped(self):
        """Dict instance without name is skipped."""
        record = {
            "module_name": "mod_a",
            "pipeline_id": "tt_test",
            "instance_list": [{"generate_scope": "gen_x"}],
        }
        assert transform_module_parse_to_instances(record) == []


class TestTransformModuleParseToPortNodes:
    """Tests for module_parse → PortDef/PortInstance node transformation (Req 10.2)."""

    def test_dict_port_list(self):
        """Dict port entries produce both PortDef and PortInstance nodes."""
        record = {
            "module_name": "trinity_router",
            "pipeline_id": "tt_20260221",
            "port_list": [
                {"name": "clk", "direction": "input", "bit_width": "1"},
                {"name": "data_out", "direction": "output", "bit_width": "32"},
            ],
        }
        port_defs, port_instances = transform_module_parse_to_port_nodes(record)
        assert len(port_defs) == 2
        assert len(port_instances) == 2

        assert port_defs[0]["label"] == "PortDef"
        assert port_defs[0]["properties"]["name"] == "clk"
        assert port_defs[0]["properties"]["direction"] == "input"
        assert port_defs[0]["properties"]["bit_width"] == "1"
        assert port_defs[0]["properties"]["parent_module"] == "trinity_router"

        assert port_instances[1]["label"] == "PortInstance"
        assert port_instances[1]["properties"]["name"] == "data_out"
        assert port_instances[1]["properties"]["direction"] == "output"

    def test_string_port_list(self):
        """Simple string port names produce PortDef only (no PortInstance)."""
        record = {
            "module_name": "mod_a",
            "pipeline_id": "tt_test",
            "port_list": ["clk", "rst_n"],
        }
        port_defs, port_instances = transform_module_parse_to_port_nodes(record)
        assert len(port_defs) == 2
        assert len(port_instances) == 0
        assert port_defs[0]["properties"]["direction"] == "unknown"

    def test_json_string_port_list(self):
        """JSON-encoded port_list string is parsed correctly."""
        record = {
            "module_name": "mod_a",
            "pipeline_id": "tt_test",
            "port_list": '[{"name": "clk", "direction": "input", "bit_width": "1"}]',
        }
        port_defs, port_instances = transform_module_parse_to_port_nodes(record)
        assert len(port_defs) == 1
        assert port_defs[0]["properties"]["name"] == "clk"

    def test_empty_port_list(self):
        """Empty port_list returns empty lists."""
        record = {"module_name": "mod_a", "pipeline_id": "tt_test", "port_list": []}
        port_defs, port_instances = transform_module_parse_to_port_nodes(record)
        assert port_defs == []
        assert port_instances == []


class TestTransformWireClaimToSignal:
    """Tests for WireTopology claim → Signal node transformation (Req 10.3)."""

    def test_signal_name_from_field(self):
        """Signal name extracted from signal_name field."""
        record = {
            "analysis_type": "claim",
            "topic": "WireTopology",
            "signal_name": "flit_out_req",
            "dimensions": ["SizeX", "SizeY-1", "2"],
            "struct_type": "flit_t",
            "purpose": "noc_data",
            "module_name": "trinity_top",
            "pipeline_id": "tt_20260221",
            "claim_text": "Wire 'flit_out_req' has 3 dimensions",
        }
        result = transform_wire_claim_to_signal(record)
        assert result is not None
        assert result["label"] == "Signal"
        assert result["properties"]["name"] == "flit_out_req"
        assert "SizeX" in result["properties"]["dimensions"]
        assert result["properties"]["struct_type"] == "flit_t"
        assert result["properties"]["purpose"] == "noc_data"
        assert result["properties"]["scope"] == "trinity_top"

    def test_signal_name_from_claim_text(self):
        """Signal name extracted from claim_text when signal_name field is missing."""
        record = {
            "analysis_type": "claim",
            "topic": "WireTopology",
            "claim_text": "Wire 'de_to_t6_coloumn' has dimensions [SizeX][SizeY-1][2]",
            "module_name": "trinity_top",
            "pipeline_id": "tt_20260221",
        }
        result = transform_wire_claim_to_signal(record)
        assert result is not None
        assert result["properties"]["name"] == "de_to_t6_coloumn"

    def test_no_signal_name_returns_none(self):
        """Returns None when signal name cannot be determined."""
        record = {
            "analysis_type": "claim",
            "topic": "WireTopology",
            "claim_text": "Some wire topology claim without name pattern",
            "module_name": "mod_a",
            "pipeline_id": "tt_test",
        }
        assert transform_wire_claim_to_signal(record) is None

    def test_dimensions_as_string(self):
        """String dimensions are preserved as-is."""
        record = {
            "signal_name": "sig_a",
            "dimensions": "[3:0]",
            "module_name": "mod_a",
            "pipeline_id": "tt_test",
            "claim_text": "",
        }
        result = transform_wire_claim_to_signal(record)
        assert result["properties"]["dimensions"] == "[3:0]"


class TestTransformClockDomainClaim:
    """Tests for ClockDomain claim → ClockDomain node transformation (Req 10.4)."""

    def test_clock_domain_from_field(self):
        """Clock domain name from clock_domain field."""
        record = {
            "analysis_type": "claim",
            "topic": "ClockDomain",
            "clock_domain": "core_clk",
            "frequency": Decimal("1000"),
            "module_name": "trinity_top",
            "pipeline_id": "tt_20260221",
            "claim_text": "Clock domain 'core_clk' at 1GHz",
        }
        result = transform_clock_domain_claim(record)
        assert result is not None
        assert result["label"] == "ClockDomain"
        assert result["properties"]["name"] == "core_clk"
        assert result["properties"]["frequency"] == "1000"
        assert result["properties"]["source_module"] == "trinity_top"

    def test_clock_domain_from_claim_text(self):
        """Clock domain name extracted from claim_text."""
        record = {
            "analysis_type": "claim",
            "topic": "ClockDomain",
            "claim_text": "Clock domain 'axi_clk' drives the interconnect",
            "module_name": "axi_top",
            "pipeline_id": "tt_20260221",
        }
        result = transform_clock_domain_claim(record)
        assert result is not None
        assert result["properties"]["name"] == "axi_clk"

    def test_clock_domain_fallback_to_module_name(self):
        """Falls back to module_name_clk when no domain name found."""
        record = {
            "analysis_type": "claim",
            "topic": "ClockDomain",
            "claim_text": "This module uses a clock",
            "module_name": "trinity_top",
            "pipeline_id": "tt_20260221",
        }
        result = transform_clock_domain_claim(record)
        assert result is not None
        assert result["properties"]["name"] == "trinity_top_clk"

    def test_no_domain_no_module_returns_none(self):
        """Returns None when neither domain name nor module_name available."""
        record = {
            "analysis_type": "claim",
            "topic": "ClockDomain",
            "claim_text": "Some clock claim",
            "module_name": "",
            "pipeline_id": "tt_test",
        }
        assert transform_clock_domain_claim(record) is None


class TestTransformRecordsToNodes:
    """Tests for the top-level transform_records_to_nodes dispatcher (Req 10.1-10.4)."""

    def test_mixed_records(self):
        """Mixed module_parse and claim records are all transformed."""
        records = [
            {
                "analysis_type": "module_parse",
                "module_name": "trinity_top",
                "file_path": "/rtl/trinity_top.sv",
                "pipeline_id": "tt_20260221",
                "instance_list": ["u_router"],
                "port_list": [{"name": "clk", "direction": "input", "bit_width": "1"}],
            },
            {
                "analysis_type": "claim",
                "topic": "WireTopology",
                "signal_name": "flit_out",
                "dimensions": "[4:0]",
                "module_name": "trinity_top",
                "pipeline_id": "tt_20260221",
                "claim_text": "Wire 'flit_out' topology",
            },
            {
                "analysis_type": "claim",
                "topic": "ClockDomain",
                "clock_domain": "core_clk",
                "module_name": "trinity_top",
                "pipeline_id": "tt_20260221",
                "claim_text": "Clock domain 'core_clk'",
            },
        ]
        nodes = transform_records_to_nodes(records)

        labels = [n["label"] for n in nodes]
        assert "ModuleDef" in labels
        assert "Instance" in labels
        assert "PortDef" in labels
        assert "PortInstance" in labels
        assert "Signal" in labels
        assert "ClockDomain" in labels

    def test_unknown_analysis_type_skipped(self):
        """Records with unknown analysis_type are skipped."""
        records = [
            {"analysis_type": "unknown_type", "module_name": "test"},
        ]
        nodes = transform_records_to_nodes(records)
        assert len(nodes) == 0

    def test_other_claim_topics_not_transformed(self):
        """Claims with topics other than WireTopology/ClockDomain are not transformed."""
        records = [
            {
                "analysis_type": "claim",
                "topic": "PortBinding",
                "claim_text": "Port binding claim",
                "module_name": "mod_a",
                "pipeline_id": "tt_test",
            },
        ]
        nodes = transform_records_to_nodes(records)
        assert len(nodes) == 0

    def test_empty_records(self):
        """Empty record list produces empty node list."""
        assert transform_records_to_nodes([]) == []


class TestScanDynamoDBRecords:
    """Tests for DynamoDB scan function."""

    @patch("neptune_ingestion.boto3.resource")
    def test_scan_with_pagination(self, mock_resource):
        """Scan handles pagination via LastEvaluatedKey."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        # First page returns items + LastEvaluatedKey
        mock_table.scan.side_effect = [
            {
                "Items": [{"claim_id": "1", "pipeline_id": "tt_test"}],
                "LastEvaluatedKey": {"claim_id": "1"},
            },
            {
                "Items": [{"claim_id": "2", "pipeline_id": "tt_test"}],
            },
        ]

        records = scan_dynamodb_records("tt_test")
        assert len(records) == 2
        assert mock_table.scan.call_count == 2

    @patch("neptune_ingestion.boto3.resource")
    def test_scan_empty_result(self, mock_resource):
        """Scan returns empty list when no records match."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.scan.return_value = {"Items": []}

        records = scan_dynamodb_records("nonexistent_pipeline")
        assert records == []

    @patch("neptune_ingestion.boto3.resource")
    def test_scan_uses_filter_expression(self, mock_resource):
        """Scan uses FilterExpression for pipeline_id."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.scan.return_value = {"Items": []}

        scan_dynamodb_records("tt_20260221")

        call_kwargs = mock_table.scan.call_args[1]
        assert "FilterExpression" in call_kwargs


# ===========================================================================
# Task 9.3 Tests — Neptune MERGE Upsert Node Loading
# Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
# ===========================================================================

from neptune_ingestion import (
    build_merge_query,
    batch_upsert_nodes,
    NODE_COMPOSITE_KEYS,
)


class TestBuildMergeQuery:
    """Tests for MERGE openCypher query generation (Req 10.5)."""

    def test_module_def_merge_query(self):
        """ModuleDef node produces correct MERGE with pipeline_id + name composite key."""
        node = {
            "label": "ModuleDef",
            "properties": {
                "name": "trinity_top",
                "file_path": "/rtl/trinity_top.sv",
                "pipeline_id": "tt_20260221",
                "module_type": "top_module",
            },
        }
        query, params = build_merge_query(node)

        assert "MERGE (n:ModuleDef {pipeline_id: $pipeline_id, name: $name})" in query
        assert "SET" in query
        assert "n.file_path = $set_file_path" in query
        assert "n.module_type = $set_module_type" in query
        assert params["pipeline_id"] == "tt_20260221"
        assert params["name"] == "trinity_top"
        assert params["set_file_path"] == "/rtl/trinity_top.sv"
        assert params["set_module_type"] == "top_module"

    def test_instance_merge_query(self):
        """Instance node uses pipeline_id + hier_path as composite key."""
        node = {
            "label": "Instance",
            "properties": {
                "instance_name": "u_router",
                "hier_path": "trinity_top/u_router",
                "generate_scope": "gen_noc",
                "x": 3,
                "y": 2,
                "parent_instance": "trinity_top",
                "pipeline_id": "tt_20260221",
            },
        }
        query, params = build_merge_query(node)

        assert "MERGE (n:Instance {pipeline_id: $pipeline_id, hier_path: $hier_path})" in query
        assert params["pipeline_id"] == "tt_20260221"
        assert params["hier_path"] == "trinity_top/u_router"
        assert params["set_instance_name"] == "u_router"
        assert params["set_generate_scope"] == "gen_noc"

    def test_port_def_merge_query(self):
        """PortDef node uses pipeline_id + parent_module + name as composite key."""
        node = {
            "label": "PortDef",
            "properties": {
                "name": "clk",
                "direction": "input",
                "bit_width": "1",
                "parent_module": "trinity_router",
                "pipeline_id": "tt_20260221",
            },
        }
        query, params = build_merge_query(node)

        assert "MERGE (n:PortDef {pipeline_id: $pipeline_id, parent_module: $parent_module, name: $name})" in query
        assert params["pipeline_id"] == "tt_20260221"
        assert params["parent_module"] == "trinity_router"
        assert params["name"] == "clk"
        assert params["set_direction"] == "input"

    def test_port_instance_merge_query(self):
        """PortInstance node uses pipeline_id + hier_path as composite key."""
        node = {
            "label": "PortInstance",
            "properties": {
                "name": "data_out",
                "direction": "output",
                "bit_width": "32",
                "parent_instance": "trinity_router",
                "hier_path": "trinity_router/data_out",
                "pipeline_id": "tt_20260221",
            },
        }
        query, params = build_merge_query(node)

        assert "MERGE (n:PortInstance {pipeline_id: $pipeline_id, hier_path: $hier_path})" in query
        assert params["pipeline_id"] == "tt_20260221"
        assert params["hier_path"] == "trinity_router/data_out"

    def test_signal_merge_query(self):
        """Signal node uses pipeline_id + scope + name as composite key."""
        node = {
            "label": "Signal",
            "properties": {
                "name": "flit_out_req",
                "dimensions": "[SizeX, SizeY-1, 2]",
                "struct_type": "flit_t",
                "purpose": "noc_data",
                "scope": "trinity_top",
                "pipeline_id": "tt_20260221",
            },
        }
        query, params = build_merge_query(node)

        assert "MERGE (n:Signal {pipeline_id: $pipeline_id, scope: $scope, name: $name})" in query
        assert params["pipeline_id"] == "tt_20260221"
        assert params["scope"] == "trinity_top"
        assert params["name"] == "flit_out_req"

    def test_clock_domain_merge_query(self):
        """ClockDomain node uses pipeline_id + name as composite key."""
        node = {
            "label": "ClockDomain",
            "properties": {
                "name": "core_clk",
                "frequency": "1000",
                "source_module": "trinity_top",
                "pipeline_id": "tt_20260221",
            },
        }
        query, params = build_merge_query(node)

        assert "MERGE (n:ClockDomain {pipeline_id: $pipeline_id, name: $name})" in query
        assert params["pipeline_id"] == "tt_20260221"
        assert params["name"] == "core_clk"
        assert params["set_frequency"] == "1000"

    def test_unknown_label_raises_value_error(self):
        """Unknown node label raises ValueError."""
        node = {"label": "UnknownType", "properties": {"name": "x", "pipeline_id": "tt"}}
        with pytest.raises(ValueError, match="Unknown node label"):
            build_merge_query(node)

    def test_missing_composite_key_raises_value_error(self):
        """Missing composite key field raises ValueError."""
        node = {
            "label": "ModuleDef",
            "properties": {"name": "test_mod"},  # missing pipeline_id
        }
        with pytest.raises(ValueError, match="Missing composite key field"):
            build_merge_query(node)

    def test_empty_composite_key_raises_value_error(self):
        """Empty string composite key field raises ValueError."""
        node = {
            "label": "ModuleDef",
            "properties": {"name": "", "pipeline_id": "tt_20260221"},
        }
        with pytest.raises(ValueError, match="Missing composite key field"):
            build_merge_query(node)

    def test_none_properties_excluded_from_set(self):
        """Properties with None values are excluded from SET clause."""
        node = {
            "label": "Instance",
            "properties": {
                "instance_name": "u_router",
                "hier_path": "trinity_top/u_router",
                "generate_scope": "",
                "x": None,
                "y": None,
                "parent_instance": "trinity_top",
                "pipeline_id": "tt_20260221",
            },
        }
        query, params = build_merge_query(node)

        # None values should not appear in SET or params
        assert "n.x" not in query
        assert "n.y" not in query
        assert "set_x" not in params
        assert "set_y" not in params

    def test_no_set_clause_when_only_keys(self):
        """No SET clause when all properties are composite keys."""
        node = {
            "label": "ClockDomain",
            "properties": {
                "name": "core_clk",
                "pipeline_id": "tt_20260221",
            },
        }
        query, params = build_merge_query(node)

        assert "SET" not in query
        assert params == {"pipeline_id": "tt_20260221", "name": "core_clk"}


class TestBatchUpsertNodes:
    """Tests for batch_upsert_nodes function (Req 10.5)."""

    def test_successful_batch_upsert(self):
        """All valid nodes are upserted successfully."""
        mock_client = MagicMock()
        mock_client.execute_query.return_value = {}

        nodes = [
            {
                "label": "ModuleDef",
                "properties": {"name": "mod_a", "pipeline_id": "tt_test", "file_path": "/a.sv", "module_type": "module"},
            },
            {
                "label": "ModuleDef",
                "properties": {"name": "mod_b", "pipeline_id": "tt_test", "file_path": "/b.sv", "module_type": "module"},
            },
        ]

        summary = batch_upsert_nodes(mock_client, nodes, batch_size=50)

        assert summary["upserted"] == 2
        assert summary["skipped"] == 0
        assert summary["failed"] == 0
        assert summary["by_label"]["ModuleDef"] == 2
        assert mock_client.execute_query.call_count == 2

    def test_batch_size_grouping(self):
        """Nodes are processed in batches of specified size."""
        mock_client = MagicMock()
        mock_client.execute_query.return_value = {}

        nodes = [
            {
                "label": "ModuleDef",
                "properties": {"name": f"mod_{i}", "pipeline_id": "tt_test", "file_path": f"/{i}.sv", "module_type": "module"},
            }
            for i in range(5)
        ]

        summary = batch_upsert_nodes(mock_client, nodes, batch_size=2)

        assert summary["upserted"] == 5
        assert mock_client.execute_query.call_count == 5

    def test_invalid_nodes_skipped(self):
        """Nodes with missing composite keys are skipped."""
        mock_client = MagicMock()
        mock_client.execute_query.return_value = {}

        nodes = [
            {
                "label": "ModuleDef",
                "properties": {"name": "mod_a", "pipeline_id": "tt_test", "file_path": "/a.sv", "module_type": "module"},
            },
            {
                "label": "ModuleDef",
                "properties": {"name": "", "pipeline_id": "tt_test"},  # invalid: empty name
            },
        ]

        summary = batch_upsert_nodes(mock_client, nodes, batch_size=50)

        assert summary["upserted"] == 1
        assert summary["skipped"] == 1
        assert summary["failed"] == 0

    def test_neptune_error_counted_as_failed(self):
        """Neptune execution errors are counted as failed."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = Exception("Neptune timeout")

        nodes = [
            {
                "label": "ModuleDef",
                "properties": {"name": "mod_a", "pipeline_id": "tt_test", "file_path": "/a.sv", "module_type": "module"},
            },
        ]

        summary = batch_upsert_nodes(mock_client, nodes, batch_size=50)

        assert summary["upserted"] == 0
        assert summary["failed"] == 1

    def test_empty_nodes_list(self):
        """Empty nodes list returns zero counts."""
        mock_client = MagicMock()

        summary = batch_upsert_nodes(mock_client, [], batch_size=50)

        assert summary["upserted"] == 0
        assert summary["skipped"] == 0
        assert summary["failed"] == 0
        assert summary["by_label"] == {}
        mock_client.execute_query.assert_not_called()

    def test_idempotent_upsert_same_nodes_twice(self):
        """Running upsert twice with same nodes calls MERGE twice (Neptune handles idempotence)."""
        mock_client = MagicMock()
        mock_client.execute_query.return_value = {}

        nodes = [
            {
                "label": "ModuleDef",
                "properties": {"name": "mod_a", "pipeline_id": "tt_test", "file_path": "/a.sv", "module_type": "module"},
            },
        ]

        # First run
        summary1 = batch_upsert_nodes(mock_client, nodes, batch_size=50)
        # Second run (same nodes)
        summary2 = batch_upsert_nodes(mock_client, nodes, batch_size=50)

        # Both runs should succeed — MERGE handles idempotence at Neptune level
        assert summary1["upserted"] == 1
        assert summary2["upserted"] == 1
        assert mock_client.execute_query.call_count == 2

    def test_mixed_node_types(self):
        """Multiple node types are all upserted correctly."""
        mock_client = MagicMock()
        mock_client.execute_query.return_value = {}

        nodes = [
            {"label": "ModuleDef", "properties": {"name": "mod_a", "pipeline_id": "tt_test", "file_path": "/a.sv", "module_type": "module"}},
            {"label": "Instance", "properties": {"hier_path": "mod_a/u_inst", "pipeline_id": "tt_test", "instance_name": "u_inst", "parent_instance": "mod_a"}},
            {"label": "Signal", "properties": {"name": "sig_a", "scope": "mod_a", "pipeline_id": "tt_test", "dimensions": "[3:0]"}},
            {"label": "ClockDomain", "properties": {"name": "core_clk", "pipeline_id": "tt_test", "frequency": "1000"}},
        ]

        summary = batch_upsert_nodes(mock_client, nodes, batch_size=50)

        assert summary["upserted"] == 4
        assert summary["by_label"]["ModuleDef"] == 1
        assert summary["by_label"]["Instance"] == 1
        assert summary["by_label"]["Signal"] == 1
        assert summary["by_label"]["ClockDomain"] == 1


class TestMainWithUpsert:
    """Tests for main() integration with batch_upsert_nodes (Task 9.3)."""

    @patch("neptune_ingestion.batch_upsert_nodes")
    @patch("neptune_ingestion.scan_dynamodb_records")
    @patch("neptune_ingestion.NeptuneSigV4Client")
    def test_main_calls_batch_upsert(self, mock_client_cls, mock_scan, mock_upsert):
        """main() calls batch_upsert_nodes with correct arguments."""
        mock_instance = MagicMock()
        mock_instance.health_check.return_value = True
        mock_client_cls.return_value = mock_instance
        mock_scan.return_value = [
            {
                "analysis_type": "module_parse",
                "module_name": "trinity_top",
                "file_path": "/rtl/trinity_top.sv",
                "pipeline_id": "tt_20260221",
                "instance_list": [],
                "port_list": [],
            },
        ]
        mock_upsert.return_value = {"upserted": 1, "skipped": 0, "failed": 0, "by_label": {"ModuleDef": 1}}

        exit_code = main([
            "--pipeline-id", "tt_20260221",
            "--neptune-endpoint", "neptune-ok.cluster.amazonaws.com",
            "--batch-size", "25",
        ])

        assert exit_code == 0
        mock_upsert.assert_called_once()
        call_args = mock_upsert.call_args
        assert call_args[1]["batch_size"] == 25 or call_args[0][2] == 25

    @patch("neptune_ingestion.batch_upsert_nodes")
    @patch("neptune_ingestion.scan_dynamodb_records")
    @patch("neptune_ingestion.NeptuneSigV4Client")
    def test_main_passes_client_to_upsert(self, mock_client_cls, mock_scan, mock_upsert):
        """main() passes the NeptuneSigV4Client instance to batch_upsert_nodes."""
        mock_instance = MagicMock()
        mock_instance.health_check.return_value = True
        mock_client_cls.return_value = mock_instance
        mock_scan.return_value = []
        mock_upsert.return_value = {"upserted": 0, "skipped": 0, "failed": 0, "by_label": {}}

        exit_code = main([
            "--pipeline-id", "tt_20260221",
            "--neptune-endpoint", "neptune-ok.cluster.amazonaws.com",
        ])

        assert exit_code == 0
        mock_upsert.assert_called_once()
        # First positional arg should be the client instance
        assert mock_upsert.call_args[0][0] is mock_instance


# ===========================================================================
# Task 10.2 Tests — Completion Summary, Error Handling, Edge Loading
# Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 12.5, 13.1
# ===========================================================================

from neptune_ingestion import (
    transform_records_to_edges,
    build_edge_merge_query,
    batch_upsert_edges,
    _count_edge_types,
    _log_completion_summary,
    _detect_parsing_ingestion_mismatch,
    _check_skip_ratio,
    _count_module_parse_records,
    EDGE_COMPOSITE_KEYS,
    SKIP_RATIO_WARNING_THRESHOLD,
)


class TestTransformRecordsToEdges:
    """Tests for edge transformation from DynamoDB records (Req 11.1-11.4)."""

    def test_module_parse_generates_defines_edges(self):
        """module_parse with port_list generates DEFINES edges."""
        records = [
            {
                "analysis_type": "module_parse",
                "module_name": "trinity_top",
                "pipeline_id": "tt_20260221",
                "port_list": [{"name": "clk", "direction": "input", "bit_width": "1"}],
                "instance_list": [],
            },
        ]
        edges = transform_records_to_edges(records, [])
        defines_edges = [e for e in edges if e["type"] == "DEFINES"]
        assert len(defines_edges) == 1
        assert defines_edges[0]["from_node"]["name"] == "trinity_top"
        assert defines_edges[0]["to_node"]["name"] == "clk"

    def test_module_parse_generates_has_port_edges(self):
        """module_parse with port_list generates HAS_PORT edges."""
        records = [
            {
                "analysis_type": "module_parse",
                "module_name": "trinity_top",
                "pipeline_id": "tt_20260221",
                "port_list": [{"name": "data_out", "direction": "output", "bit_width": "32"}],
                "instance_list": [],
            },
        ]
        edges = transform_records_to_edges(records, [])
        has_port_edges = [e for e in edges if e["type"] == "HAS_PORT"]
        assert len(has_port_edges) == 1
        assert has_port_edges[0]["from_node"]["hier_path"] == "trinity_top"
        assert has_port_edges[0]["to_node"]["hier_path"] == "trinity_top/data_out"

    def test_module_parse_generates_instance_of_edges(self):
        """module_parse with instance_list generates INSTANCE_OF edges."""
        records = [
            {
                "analysis_type": "module_parse",
                "module_name": "trinity_top",
                "pipeline_id": "tt_20260221",
                "port_list": [],
                "instance_list": ["u_router", "u_noc"],
            },
        ]
        edges = transform_records_to_edges(records, [])
        inst_edges = [e for e in edges if e["type"] == "INSTANCE_OF"]
        assert len(inst_edges) == 2
        assert inst_edges[0]["from_node"]["hier_path"] == "trinity_top/u_router"
        assert inst_edges[0]["properties"]["instance_name"] == "u_router"

    def test_port_binding_claim_generates_binds_to(self):
        """PortBinding claim generates BINDS_TO edge."""
        records = [
            {
                "analysis_type": "claim",
                "topic": "PortBinding",
                "port_name": "i_data",
                "signal_name": "data_bus",
                "signal_expr": "data_bus",
                "expression_type": "simple",
                "direction": "input",
                "module_name": "trinity_router",
                "pipeline_id": "tt_20260221",
            },
        ]
        edges = transform_records_to_edges(records, [])
        binds_edges = [e for e in edges if e["type"] == "BINDS_TO"]
        assert len(binds_edges) == 1
        assert binds_edges[0]["properties"]["signal_expr"] == "data_bus"
        assert binds_edges[0]["properties"]["expression_type"] == "simple"

    def test_output_port_binding_generates_drives(self):
        """Output PortBinding claim generates DRIVES edge."""
        records = [
            {
                "analysis_type": "claim",
                "topic": "PortBinding",
                "port_name": "o_data",
                "signal_name": "out_bus",
                "signal_expr": "out_bus",
                "direction": "output",
                "module_name": "trinity_router",
                "pipeline_id": "tt_20260221",
            },
        ]
        edges = transform_records_to_edges(records, [])
        drives_edges = [e for e in edges if e["type"] == "DRIVES"]
        assert len(drives_edges) == 1
        assert drives_edges[0]["properties"]["driver_type"] == "output"

    def test_input_port_binding_generates_reads(self):
        """Input PortBinding claim generates READS edge."""
        records = [
            {
                "analysis_type": "claim",
                "topic": "PortBinding",
                "port_name": "i_clk",
                "signal_name": "core_clk",
                "signal_expr": "core_clk",
                "direction": "input",
                "module_name": "trinity_router",
                "pipeline_id": "tt_20260221",
            },
        ]
        edges = transform_records_to_edges(records, [])
        reads_edges = [e for e in edges if e["type"] == "READS"]
        assert len(reads_edges) == 1
        assert reads_edges[0]["properties"]["reader_type"] == "input"

    def test_clock_domain_claim_generates_belongs_to(self):
        """ClockDomain claim with signal_name generates BELONGS_TO edge."""
        records = [
            {
                "analysis_type": "claim",
                "topic": "ClockDomain",
                "signal_name": "core_clk_sig",
                "clock_domain": "core_clk",
                "module_name": "trinity_top",
                "pipeline_id": "tt_20260221",
                "claim_text": "Clock domain 'core_clk'",
            },
        ]
        edges = transform_records_to_edges(records, [])
        belongs_edges = [e for e in edges if e["type"] == "BELONGS_TO"]
        assert len(belongs_edges) == 1
        assert belongs_edges[0]["from_node"]["name"] == "core_clk_sig"
        assert belongs_edges[0]["to_node"]["name"] == "core_clk"

    def test_empty_records_returns_empty_edges(self):
        """Empty records produce no edges."""
        assert transform_records_to_edges([], []) == []

    def test_missing_port_name_skipped(self):
        """PortBinding claim without port_name is skipped."""
        records = [
            {
                "analysis_type": "claim",
                "topic": "PortBinding",
                "port_name": "",
                "signal_name": "sig_a",
                "module_name": "mod_a",
                "pipeline_id": "tt_test",
            },
        ]
        edges = transform_records_to_edges(records, [])
        assert len(edges) == 0


class TestBuildEdgeMergeQuery:
    """Tests for edge MERGE openCypher query generation (Req 11.5)."""

    def test_defines_edge_query(self):
        """DEFINES edge produces correct MATCH + MERGE query."""
        edge = {
            "type": "DEFINES",
            "from_node": {"label": "ModuleDef", "pipeline_id": "tt_test", "name": "mod_a"},
            "to_node": {"label": "PortDef", "pipeline_id": "tt_test", "parent_module": "mod_a", "name": "clk"},
            "properties": {},
        }
        query, params = build_edge_merge_query(edge)
        assert "MATCH (a:ModuleDef" in query
        assert "MATCH (b:PortDef" in query
        assert "MERGE (a)-[r:DEFINES]->(b)" in query
        assert params["from_pipeline_id"] == "tt_test"
        assert params["from_name"] == "mod_a"
        assert params["to_name"] == "clk"

    def test_instance_of_edge_with_edge_keys(self):
        """INSTANCE_OF edge includes instance_name in MERGE."""
        edge = {
            "type": "INSTANCE_OF",
            "from_node": {"label": "Instance", "pipeline_id": "tt_test", "hier_path": "mod_a/u_inst"},
            "to_node": {"label": "ModuleDef", "pipeline_id": "tt_test", "name": "sub_mod"},
            "properties": {"instance_name": "u_inst"},
        }
        query, params = build_edge_merge_query(edge)
        assert "INSTANCE_OF" in query
        assert "instance_name: $edge_instance_name" in query
        assert params["edge_instance_name"] == "u_inst"

    def test_binds_to_edge_with_properties(self):
        """BINDS_TO edge includes signal_expr and expression_type."""
        edge = {
            "type": "BINDS_TO",
            "from_node": {"label": "PortInstance", "pipeline_id": "tt_test", "hier_path": "mod_a/clk"},
            "to_node": {"label": "Signal", "pipeline_id": "tt_test", "scope": "mod_a", "name": "clk_sig"},
            "properties": {"signal_expr": "clk_sig", "expression_type": "simple"},
        }
        query, params = build_edge_merge_query(edge)
        assert "BINDS_TO" in query
        assert "signal_expr: $edge_signal_expr" in query
        assert params["edge_signal_expr"] == "clk_sig"

    def test_unknown_edge_type_raises_error(self):
        """Unknown edge type raises ValueError."""
        edge = {"type": "UNKNOWN_EDGE", "from_node": {}, "to_node": {}, "properties": {}}
        with pytest.raises(ValueError, match="Unknown edge type"):
            build_edge_merge_query(edge)


class TestBatchUpsertEdges:
    """Tests for batch_upsert_edges function (Req 11.5)."""

    def test_successful_edge_upsert(self):
        """All valid edges are upserted successfully."""
        mock_client = MagicMock()
        mock_client.execute_query.return_value = {}

        edges = [
            {
                "type": "DEFINES",
                "from_node": {"label": "ModuleDef", "pipeline_id": "tt_test", "name": "mod_a"},
                "to_node": {"label": "PortDef", "pipeline_id": "tt_test", "parent_module": "mod_a", "name": "clk"},
                "properties": {},
            },
            {
                "type": "DEFINES",
                "from_node": {"label": "ModuleDef", "pipeline_id": "tt_test", "name": "mod_a"},
                "to_node": {"label": "PortDef", "pipeline_id": "tt_test", "parent_module": "mod_a", "name": "rst"},
                "properties": {},
            },
        ]

        summary = batch_upsert_edges(mock_client, edges, batch_size=50)
        assert summary["upserted"] == 2
        assert summary["skipped"] == 0
        assert summary["failed"] == 0
        assert summary["by_type"]["DEFINES"] == 2

    def test_neptune_error_counted_as_failed(self):
        """Neptune execution errors are counted as failed."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = Exception("Neptune timeout")

        edges = [
            {
                "type": "DEFINES",
                "from_node": {"label": "ModuleDef", "pipeline_id": "tt_test", "name": "mod_a"},
                "to_node": {"label": "PortDef", "pipeline_id": "tt_test", "parent_module": "mod_a", "name": "clk"},
                "properties": {},
            },
        ]

        summary = batch_upsert_edges(mock_client, edges, batch_size=50)
        assert summary["upserted"] == 0
        assert summary["failed"] == 1

    def test_empty_edges_list(self):
        """Empty edges list returns zero counts."""
        mock_client = MagicMock()
        summary = batch_upsert_edges(mock_client, [], batch_size=50)
        assert summary["upserted"] == 0
        assert summary["skipped"] == 0
        assert summary["failed"] == 0
        assert summary["by_type"] == {}


class TestCompletionSummary:
    """Tests for completion summary log and error handling (Req 12.5, 13.1)."""

    def test_log_completion_summary_normal(self, caplog):
        """Completion summary logs at INFO level when skip ratio is normal."""
        import logging
        with caplog.at_level(logging.INFO, logger="neptune_ingestion"):
            _log_completion_summary(
                pipeline_id="tt_20260221",
                total_nodes_created=10,
                total_edges_created=5,
                execution_time_seconds=2.5,
                skipped_records=1,
                total_records=20,
            )
        # Check that the summary was logged
        assert any("ingestion_complete" in r.message for r in caplog.records)
        # Parse the JSON log to verify fields
        for record in caplog.records:
            if "ingestion_complete" in record.message:
                log_data = json.loads(record.message)
                assert log_data["total_nodes_created"] == 10
                assert log_data["total_edges_created"] == 5
                assert log_data["execution_time_seconds"] == 2.5
                assert log_data["skipped_records"] == 1
                assert record.levelname == "INFO"

    def test_log_completion_summary_high_skip_ratio(self, caplog):
        """Completion summary logs at WARNING level when skip ratio > 30%."""
        import logging
        with caplog.at_level(logging.WARNING, logger="neptune_ingestion"):
            _log_completion_summary(
                pipeline_id="tt_20260221",
                total_nodes_created=5,
                total_edges_created=2,
                execution_time_seconds=1.0,
                skipped_records=8,
                total_records=20,  # 8/20 = 40% > 30%
            )
        # Check that warning was emitted
        assert any(r.levelname == "WARNING" for r in caplog.records)
        for record in caplog.records:
            if record.levelname == "WARNING":
                log_data = json.loads(record.message)
                assert log_data["skip_ratio_warning"] is True
                assert "exceeds threshold" in log_data["message"]

    def test_log_completion_summary_with_breakdowns(self, caplog):
        """Completion summary includes node and edge breakdowns when provided."""
        import logging
        with caplog.at_level(logging.INFO, logger="neptune_ingestion"):
            _log_completion_summary(
                pipeline_id="tt_test",
                total_nodes_created=3,
                total_edges_created=2,
                execution_time_seconds=0.5,
                skipped_records=0,
                total_records=5,
                node_breakdown={"ModuleDef": 2, "Instance": 1},
                edge_breakdown={"DEFINES": 1, "INSTANCE_OF": 1},
            )
        for record in caplog.records:
            if "ingestion_complete" in record.message:
                log_data = json.loads(record.message)
                assert log_data["node_breakdown"] == {"ModuleDef": 2, "Instance": 1}
                assert log_data["edge_breakdown"] == {"DEFINES": 1, "INSTANCE_OF": 1}


class TestParsingIngestionMismatch:
    """Tests for parsing-to-ingestion mismatch detection (Req 13.1)."""

    def test_mismatch_detected_when_modules_found_but_zero_nodes(self):
        """Mismatch detected: N>0 modules parsed but 0 nodes created."""
        assert _detect_parsing_ingestion_mismatch(5, 0) is True

    def test_no_mismatch_when_nodes_created(self):
        """No mismatch when nodes are created."""
        assert _detect_parsing_ingestion_mismatch(5, 3) is False

    def test_no_mismatch_when_zero_modules(self):
        """No mismatch when zero modules parsed (empty pipeline)."""
        assert _detect_parsing_ingestion_mismatch(0, 0) is False

    def test_count_module_parse_records(self):
        """_count_module_parse_records counts only module_parse records."""
        records = [
            {"analysis_type": "module_parse", "module_name": "mod_a"},
            {"analysis_type": "module_parse", "module_name": "mod_b"},
            {"analysis_type": "claim", "topic": "WireTopology"},
            {"analysis_type": "claim", "topic": "PortBinding"},
        ]
        assert _count_module_parse_records(records) == 2


class TestSkipRatio:
    """Tests for skip ratio warning threshold (Req 12.5)."""

    def test_below_threshold(self):
        """Skip ratio below 30% does not trigger warning."""
        exceeded, ratio = _check_skip_ratio(2, 10)  # 20%
        assert exceeded is False
        assert ratio == 0.2

    def test_above_threshold(self):
        """Skip ratio above 30% triggers warning."""
        exceeded, ratio = _check_skip_ratio(4, 10)  # 40%
        assert exceeded is True
        assert ratio == 0.4

    def test_exactly_at_threshold(self):
        """Skip ratio exactly at 30% does not trigger (> not >=)."""
        exceeded, ratio = _check_skip_ratio(3, 10)  # 30%
        assert exceeded is False
        assert ratio == 0.3

    def test_zero_total_records(self):
        """Zero total records returns no warning."""
        exceeded, ratio = _check_skip_ratio(0, 0)
        assert exceeded is False
        assert ratio == 0.0


class TestMainWithEdgeLoading:
    """Tests for main() integration with edge loading (Task 10.2)."""

    @patch("neptune_ingestion.batch_upsert_edges")
    @patch("neptune_ingestion.transform_records_to_edges")
    @patch("neptune_ingestion.batch_upsert_nodes")
    @patch("neptune_ingestion.scan_dynamodb_records")
    @patch("neptune_ingestion.NeptuneSigV4Client")
    def test_main_calls_edge_loading(self, mock_client_cls, mock_scan, mock_node_upsert, mock_edge_transform, mock_edge_upsert):
        """main() calls edge transformation and upsert after node loading."""
        mock_instance = MagicMock()
        mock_instance.health_check.return_value = True
        mock_client_cls.return_value = mock_instance
        mock_scan.return_value = [
            {
                "analysis_type": "module_parse",
                "module_name": "trinity_top",
                "pipeline_id": "tt_20260221",
                "port_list": [{"name": "clk", "direction": "input", "bit_width": "1"}],
                "instance_list": [],
            },
        ]
        mock_node_upsert.return_value = {"upserted": 1, "skipped": 0, "failed": 0, "by_label": {"ModuleDef": 1}}
        mock_edge_transform.return_value = [
            {"type": "DEFINES", "from_node": {}, "to_node": {}, "properties": {}},
        ]
        mock_edge_upsert.return_value = {"upserted": 1, "skipped": 0, "failed": 0, "by_type": {"DEFINES": 1}}

        exit_code = main([
            "--pipeline-id", "tt_20260221",
            "--neptune-endpoint", "neptune-ok.cluster.amazonaws.com",
        ])

        assert exit_code == 0
        mock_edge_transform.assert_called_once()
        mock_edge_upsert.assert_called_once()

    @patch("neptune_ingestion.batch_upsert_edges")
    @patch("neptune_ingestion.transform_records_to_edges")
    @patch("neptune_ingestion.batch_upsert_nodes")
    @patch("neptune_ingestion.scan_dynamodb_records")
    @patch("neptune_ingestion.NeptuneSigV4Client")
    def test_main_mismatch_detection_with_edges(self, mock_client_cls, mock_scan, mock_node_upsert, mock_edge_transform, mock_edge_upsert, caplog):
        """main() detects parsing-to-ingestion mismatch and logs error."""
        import logging
        mock_instance = MagicMock()
        mock_instance.health_check.return_value = True
        mock_client_cls.return_value = mock_instance
        mock_scan.return_value = [
            {
                "analysis_type": "module_parse",
                "module_name": "trinity_top",
                "pipeline_id": "tt_20260221",
                "port_list": [],
                "instance_list": [],
            },
        ]
        # Simulate: modules found but 0 nodes created (all failed)
        mock_node_upsert.return_value = {"upserted": 0, "skipped": 0, "failed": 1, "by_label": {}}
        mock_edge_transform.return_value = []
        mock_edge_upsert.return_value = {"upserted": 0, "skipped": 0, "failed": 0, "by_type": {}}

        with caplog.at_level(logging.ERROR, logger="neptune_ingestion"):
            exit_code = main([
                "--pipeline-id", "tt_20260221",
                "--neptune-endpoint", "neptune-ok.cluster.amazonaws.com",
            ])

        assert exit_code == 0  # Still exits 0 (mismatch is logged, not fatal)
        assert any("parsing_ingestion_mismatch" in r.message for r in caplog.records)


class TestDynamoDBScanRetry:
    """Tests for DynamoDB scan exponential backoff retry (Req 13.1)."""

    @patch("neptune_ingestion.time.sleep")
    @patch("neptune_ingestion.boto3.resource")
    def test_retry_on_timeout(self, mock_resource, mock_sleep):
        """DynamoDB scan retries with exponential backoff on timeout."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        # First call times out, second succeeds
        mock_table.scan.side_effect = [
            Exception("Read timeout"),
            {"Items": [{"claim_id": "1", "pipeline_id": "tt_test"}]},
        ]

        records = scan_dynamodb_records("tt_test")
        assert len(records) == 1
        assert mock_sleep.call_count == 1
        # First retry waits 2 seconds (2^1)
        mock_sleep.assert_called_with(2)

    @patch("neptune_ingestion.time.sleep")
    @patch("neptune_ingestion.boto3.resource")
    def test_max_retries_exhausted(self, mock_resource, mock_sleep):
        """DynamoDB scan raises after max retries exhausted."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        # All calls timeout
        mock_table.scan.side_effect = Exception("Read timeout")

        with pytest.raises(Exception, match="Read timeout"):
            scan_dynamodb_records("tt_test", max_retries=3)

        # Should have retried 3 times with exponential backoff
        assert mock_sleep.call_count == 3

    @patch("neptune_ingestion.time.sleep")
    @patch("neptune_ingestion.boto3.resource")
    def test_non_timeout_error_not_retried(self, mock_resource, mock_sleep):
        """Non-timeout errors are not retried."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        mock_table.scan.side_effect = Exception("Access denied")

        with pytest.raises(Exception, match="Access denied"):
            scan_dynamodb_records("tt_test")

        # No retries for non-timeout errors
        mock_sleep.assert_not_called()




# ===========================================================================
# Task 13.1 Tests — Graph Export API Verification Logic
# Requirements: 13.1, 13.2, 13.3
# ===========================================================================

from neptune_ingestion import (
    GraphExportVerificationResult,
    _call_graph_export_api,
    verify_graph_export,
)


class TestGraphExportVerificationResult:
    """Tests for GraphExportVerificationResult data class."""

    def test_initial_state(self):
        """New result starts with no errors and success=True."""
        result = GraphExportVerificationResult()
        assert result.success is True
        assert result.chip_verified is False
        assert result.module_verified is False
        assert result.errors == []
        assert result.warnings == []

    def test_success_false_with_errors(self):
        """success is False when errors are present."""
        result = GraphExportVerificationResult()
        result.errors.append("Something went wrong")
        assert result.success is False

    def test_to_dict_serialization(self):
        """to_dict() produces a complete serializable dict."""
        result = GraphExportVerificationResult()
        result.chip_verified = True
        result.chip_node_count = 5
        result.chip_edge_count = 3
        result.chip_edge_types = {"INSTANTIATES": 3}
        result.module_verified = True
        result.module_node_count = 10
        result.module_edge_count = 7
        result.module_edge_types = {"BINDS_TO": 4, "DRIVES": 3}
        result.module_node_types = {"Port": 6, "Signal": 4}
        result.warnings.append("test warning")

        d = result.to_dict()
        assert d["success"] is True
        assert d["chip_verified"] is True
        assert d["module_verified"] is True
        assert d["chip_node_count"] == 5
        assert d["chip_edge_count"] == 3
        assert d["chip_edge_types"] == {"INSTANTIATES": 3}
        assert d["module_node_count"] == 10
        assert d["module_edge_count"] == 7
        assert d["module_edge_types"] == {"BINDS_TO": 4, "DRIVES": 3}
        assert d["module_node_types"] == {"Port": 6, "Signal": 4}
        assert d["warnings"] == ["test warning"]
        assert d["errors"] == []


class TestCallGraphExportApi:
    """Tests for _call_graph_export_api Neptune query helper."""

    def test_chip_scope_with_results(self):
        """scope 'chip' returns Module nodes and INSTANTIATES edges."""
        mock_client = MagicMock()
        mock_client.execute_query.return_value = {
            "results": [
                {"root_name": "trinity_top", "child_name": "u_router", "child_labels": ["ModuleDef"]},
                {"root_name": "trinity_top", "child_name": "u_noc", "child_labels": ["ModuleDef"]},
            ]
        }

        result = _call_graph_export_api(mock_client, "chip", "trinity_top")

        assert result["node_count"] == 3  # trinity_top, u_router, u_noc
        assert result["edge_count"] == 2  # 2 INSTANTIATES edges
        assert result["edge_types"]["INSTANTIATES"] == 2
        assert "trinity_top" in result["nodes"]
        assert "u_router" in result["nodes"]
        assert "u_noc" in result["nodes"]

    def test_chip_scope_empty_results_fallback(self):
        """scope 'chip' falls back to count query when no INSTANTIATES found."""
        mock_client = MagicMock()
        # First query returns empty (no INSTANTIATES edges)
        # Second query (count) finds the root module
        mock_client.execute_query.side_effect = [
            {"results": []},
            {"results": [{"node_count": 1}]},
        ]

        result = _call_graph_export_api(mock_client, "chip", "trinity_top")

        assert result["node_count"] == 1
        assert result["edge_count"] == 0
        assert "trinity_top" in result["nodes"]

    def test_chip_scope_no_module_found(self):
        """scope 'chip' returns 0 nodes when module doesn't exist."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = [
            {"results": []},
            {"results": [{"node_count": 0}]},
        ]

        result = _call_graph_export_api(mock_client, "chip", "nonexistent_module")

        assert result["node_count"] == 0
        assert result["edge_count"] == 0

    def test_module_scope_with_results(self):
        """scope 'module' returns Port + Signal nodes and edge types."""
        mock_client = MagicMock()
        mock_client.execute_query.return_value = {
            "results": [
                {"port_name": "clk", "port_direction": "input", "signal_name": "clk_net", "rel_type": "BINDS_TO"},
                {"port_name": "data_out", "port_direction": "output", "signal_name": "data_sig", "rel_type": "DRIVES"},
                {"port_name": "rst_n", "port_direction": "input", "signal_name": "rst_net", "rel_type": "BINDS_TO"},
                {"port_name": "data_in", "port_direction": "input", "signal_name": None, "rel_type": None},
            ]
        }

        result = _call_graph_export_api(mock_client, "module", "trinity_router")

        assert result["node_types"]["Port"] == 4  # clk, data_out, rst_n, data_in
        assert result["node_types"]["Signal"] == 3  # clk_net, data_sig, rst_net
        assert result["node_count"] == 7  # 4 ports + 3 signals
        assert result["edge_count"] == 3  # 2 BINDS_TO + 1 DRIVES
        assert result["edge_types"]["BINDS_TO"] == 2
        assert result["edge_types"]["DRIVES"] == 1

    def test_module_scope_empty_results(self):
        """scope 'module' returns 0 when no ports/signals found."""
        mock_client = MagicMock()
        mock_client.execute_query.return_value = {"results": []}

        result = _call_graph_export_api(mock_client, "module", "empty_module")

        assert result["node_count"] == 0
        assert result["edge_count"] == 0
        assert result["node_types"]["Port"] == 0
        assert result["node_types"]["Signal"] == 0

    def test_invalid_scope_returns_empty(self):
        """Invalid scope returns empty result without querying."""
        mock_client = MagicMock()

        result = _call_graph_export_api(mock_client, "invalid", "any_module")

        assert result["node_count"] == 0
        assert result["edge_count"] == 0
        mock_client.execute_query.assert_not_called()


class TestVerifyGraphExport:
    """Tests for verify_graph_export post-ingestion verification (Req 13.1, 13.2, 13.3)."""

    def test_mismatch_detected_returns_error(self):
        """Parsing N>0 modules but 0 nodes → error reported immediately."""
        mock_client = MagicMock()

        result = verify_graph_export(
            client=mock_client,
            pipeline_id="tt_20260221",
            root_module="trinity_top",
            module_parse_count=5,
            total_nodes_created=0,
        )

        assert result.success is False
        assert len(result.errors) == 1
        assert "Parsing-to-ingestion mismatch" in result.errors[0]
        assert "5 module(s)" in result.errors[0]
        # Should not attempt Neptune queries after mismatch
        mock_client.execute_query.assert_not_called()

    def test_chip_scope_verified_with_instantiates(self):
        """scope 'chip' verified when Module nodes + INSTANTIATES edges found."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = [
            # chip scope query
            {"results": [
                {"root_name": "trinity_top", "child_name": "u_router", "child_labels": ["ModuleDef"]},
                {"root_name": "trinity_top", "child_name": "u_noc", "child_labels": ["ModuleDef"]},
            ]},
            # module scope query
            {"results": [
                {"port_name": "clk", "port_direction": "input", "signal_name": "clk_net", "rel_type": "BINDS_TO"},
            ]},
        ]

        result = verify_graph_export(
            client=mock_client,
            pipeline_id="tt_20260221",
            root_module="trinity_top",
            module_parse_count=3,
            total_nodes_created=10,
        )

        assert result.success is True
        assert result.chip_verified is True
        assert result.chip_node_count == 3
        assert result.chip_edge_count == 2
        assert result.chip_edge_types["INSTANTIATES"] == 2

    def test_module_scope_verified_with_binds_to_drives(self):
        """scope 'module' verified when Port/Signal nodes + BINDS_TO/DRIVES edges found."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = [
            # chip scope query
            {"results": [
                {"root_name": "trinity_top", "child_name": "u_router", "child_labels": ["ModuleDef"]},
            ]},
            # module scope query
            {"results": [
                {"port_name": "clk", "port_direction": "input", "signal_name": "clk_net", "rel_type": "BINDS_TO"},
                {"port_name": "data_out", "port_direction": "output", "signal_name": "data_sig", "rel_type": "DRIVES"},
            ]},
        ]

        result = verify_graph_export(
            client=mock_client,
            pipeline_id="tt_20260221",
            root_module="trinity_top",
            module_parse_count=2,
            total_nodes_created=10,
        )

        assert result.success is True
        assert result.module_verified is True
        assert result.module_node_types["Port"] == 2
        assert result.module_node_types["Signal"] == 2
        assert result.module_edge_types["BINDS_TO"] == 1
        assert result.module_edge_types["DRIVES"] == 1

    def test_chip_scope_warning_no_edges(self):
        """Warning when chip scope has nodes but no INSTANTIATES edges."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = [
            # chip scope: no INSTANTIATES edges found, fallback count finds root
            {"results": []},
            {"results": [{"node_count": 1}]},
            # module scope
            {"results": []},
        ]

        result = verify_graph_export(
            client=mock_client,
            pipeline_id="tt_20260221",
            root_module="trinity_top",
            module_parse_count=3,
            total_nodes_created=5,
        )

        assert result.success is True
        assert result.chip_verified is True
        assert result.chip_node_count == 1
        # Warning about missing INSTANTIATES edges
        assert any("INSTANTIATES" in w for w in result.warnings)

    def test_module_scope_warning_no_nodes(self):
        """Warning when module scope returns no Port/Signal nodes."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = [
            # chip scope
            {"results": [
                {"root_name": "trinity_top", "child_name": "u_router", "child_labels": ["ModuleDef"]},
            ]},
            # module scope: empty
            {"results": []},
        ]

        result = verify_graph_export(
            client=mock_client,
            pipeline_id="tt_20260221",
            root_module="trinity_top",
            module_parse_count=2,
            total_nodes_created=5,
        )

        assert result.success is True
        assert result.module_verified is False
        assert any("No Port/Signal nodes" in w for w in result.warnings)

    def test_neptune_query_failure_chip(self):
        """Neptune query failure for chip scope → error reported."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = [
            Exception("Neptune timeout"),
            # module scope still works
            {"results": [
                {"port_name": "clk", "port_direction": "input", "signal_name": "clk_net", "rel_type": "BINDS_TO"},
            ]},
        ]

        result = verify_graph_export(
            client=mock_client,
            pipeline_id="tt_20260221",
            root_module="trinity_top",
            module_parse_count=2,
            total_nodes_created=5,
        )

        assert result.success is False
        assert any("chip" in e for e in result.errors)
        # Module scope should still be verified
        assert result.module_verified is True

    def test_neptune_query_failure_module(self):
        """Neptune query failure for module scope → error reported."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = [
            # chip scope works
            {"results": [
                {"root_name": "trinity_top", "child_name": "u_router", "child_labels": ["ModuleDef"]},
            ]},
            # module scope fails
            Exception("Connection refused"),
        ]

        result = verify_graph_export(
            client=mock_client,
            pipeline_id="tt_20260221",
            root_module="trinity_top",
            module_parse_count=2,
            total_nodes_created=5,
        )

        assert result.success is False
        assert result.chip_verified is True
        assert any("module" in e for e in result.errors)

    def test_zero_modules_zero_nodes_no_error(self):
        """No error when 0 modules parsed and 0 nodes created (empty pipeline)."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = [
            # chip scope: empty
            {"results": []},
            {"results": [{"node_count": 0}]},
            # module scope: empty
            {"results": []},
        ]

        result = verify_graph_export(
            client=mock_client,
            pipeline_id="tt_empty",
            root_module="nonexistent",
            module_parse_count=0,
            total_nodes_created=0,
        )

        assert result.success is True
        assert result.chip_verified is False
        assert result.module_verified is False
        # No errors — empty pipeline is valid

    def test_full_successful_verification(self):
        """Full successful verification with both scopes passing."""
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = [
            # chip scope
            {"results": [
                {"root_name": "trinity_top", "child_name": "u_router", "child_labels": ["ModuleDef"]},
                {"root_name": "trinity_top", "child_name": "u_noc", "child_labels": ["ModuleDef"]},
                {"root_name": "trinity_top", "child_name": "u_overlay", "child_labels": ["ModuleDef"]},
            ]},
            # module scope
            {"results": [
                {"port_name": "clk", "port_direction": "input", "signal_name": "clk_net", "rel_type": "BINDS_TO"},
                {"port_name": "rst_n", "port_direction": "input", "signal_name": "rst_net", "rel_type": "BINDS_TO"},
                {"port_name": "data_out", "port_direction": "output", "signal_name": "data_sig", "rel_type": "DRIVES"},
            ]},
        ]

        result = verify_graph_export(
            client=mock_client,
            pipeline_id="tt_20260221",
            root_module="trinity_top",
            module_parse_count=4,
            total_nodes_created=20,
        )

        assert result.success is True
        assert result.chip_verified is True
        assert result.module_verified is True
        assert result.chip_node_count == 4  # trinity_top + 3 children
        assert result.chip_edge_count == 3
        assert result.module_node_count == 6  # 3 ports + 3 signals
        assert result.module_edge_count == 3
        assert result.errors == []
        assert result.warnings == []

#!/usr/bin/env python3
"""
Neptune Ingestion Pipeline — DynamoDB 파싱 데이터를 Neptune Graph DB에 적재

Usage:
    py neptune_ingestion.py --pipeline-id <id> [options]

Options:
    --pipeline-id       Required. DynamoDB 레코드 필터링 키
    --neptune-endpoint  Neptune endpoint (env: NEPTUNE_ENDPOINT)
    --batch-size        Batch upsert 크기 (default: 50)
    --dry-run           Neptune 쓰기 없이 변환 결과만 출력
    --verbose           상세 로그 출력

Requirements: 12.1, 12.3, 12.4
"""
import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

import boto3
import boto3.dynamodb.conditions
import botocore.auth
import botocore.awsrequest
import botocore.credentials
from decimal import Decimal

# ---------------------------------------------------------------------------
# Logging setup (structured JSON)
# ---------------------------------------------------------------------------
logger = logging.getLogger("neptune_ingestion")


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if hasattr(record, "event"):
            log_entry["event"] = record.event
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def _setup_logging(verbose: bool = False):
    """Configure structured JSON logging."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)


# ---------------------------------------------------------------------------
# SigV4 Authentication for Neptune
# ---------------------------------------------------------------------------
class NeptuneSigV4Client:
    """Neptune HTTPS client with IAM SigV4 authentication.

    Uses botocore.auth.SigV4Auth + AWSRequest for request signing,
    consistent with the existing Neptune read APIs in this project.
    """

    def __init__(self, endpoint: str, region: str = None):
        self.endpoint = endpoint
        self.neptune_url = f"https://{endpoint}:8182/openCypher"

        session = boto3.Session()
        self.credentials = session.get_credentials().get_frozen_credentials()
        self.region = region or session.region_name or "ap-northeast-2"

    def _sign_request(self, method: str, url: str, body: str = None, headers: dict = None):
        """Sign an HTTP request using SigV4 for neptune-db service."""
        request_headers = headers or {}
        if body:
            request_headers["Content-Type"] = "application/json"

        aws_request = botocore.awsrequest.AWSRequest(
            method=method,
            url=url,
            data=body,
            headers=request_headers,
        )

        signer = botocore.auth.SigV4Auth(self.credentials, "neptune-db", self.region)
        signer.add_auth(aws_request)

        return aws_request

    def execute_query(self, query: str, parameters: dict = None) -> dict:
        """Execute an openCypher query against Neptune.

        Args:
            query: openCypher query string
            parameters: Query parameters dict

        Returns:
            Parsed JSON response from Neptune

        Raises:
            urllib.error.URLError: On network/connection errors
            urllib.error.HTTPError: On HTTP error responses
        """
        payload = {"query": query}
        if parameters:
            payload["parameters"] = parameters

        body = json.dumps(payload).encode("utf-8")
        signed_request = self._sign_request("POST", self.neptune_url, body.decode("utf-8"))

        req = urllib.request.Request(
            self.neptune_url,
            data=body,
            method="POST",
        )
        # Apply signed headers
        for key, value in signed_request.headers.items():
            req.add_header(key, value)

        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def health_check(self) -> bool:
        """Verify Neptune endpoint is reachable.

        Returns:
            True if endpoint responds, False otherwise.
        """
        status_url = f"https://{self.endpoint}:8182/status"
        signed_request = self._sign_request("GET", status_url)

        req = urllib.request.Request(status_url, method="GET")
        for key, value in signed_request.headers.items():
            req.add_header(key, value)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            return False


# ---------------------------------------------------------------------------
# Configuration resolution
# ---------------------------------------------------------------------------
def _resolve_neptune_endpoint(cli_endpoint: str = None) -> str:
    """Resolve Neptune endpoint from CLI arg, env var, or fail.

    Priority:
        1. CLI --neptune-endpoint argument
        2. NEPTUNE_ENDPOINT environment variable
        3. None (caller should handle missing endpoint)
    """
    if cli_endpoint:
        return cli_endpoint
    return os.environ.get("NEPTUNE_ENDPOINT", "")


# ---------------------------------------------------------------------------
# DynamoDB Scan (Task 9.2)
# ---------------------------------------------------------------------------
DYNAMODB_TABLE_NAME = "bos-ai-claim-db-prod"


def scan_dynamodb_records(pipeline_id: str, table_name: str = DYNAMODB_TABLE_NAME,
                          region: str = "ap-northeast-2",
                          max_retries: int = 3) -> list[dict]:
    """Scan DynamoDB table for records matching the given pipeline_id.

    Uses FilterExpression to retrieve only records for the specified pipeline.
    Handles pagination automatically via LastEvaluatedKey.
    Retries with exponential backoff on timeout errors (max 3 attempts).

    Args:
        pipeline_id: Pipeline ID to filter records (e.g., 'tt_20260221')
        table_name: DynamoDB table name
        region: AWS region
        max_retries: Maximum number of retry attempts for timeout errors (default: 3)

    Returns:
        List of DynamoDB record dicts (with Decimal values preserved)

    Raises:
        Exception: If all retry attempts are exhausted on timeout errors,
                   or on non-retryable errors.
    """
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    records = []
    scan_kwargs = {
        "FilterExpression": boto3.dynamodb.conditions.Attr("pipeline_id").eq(pipeline_id),
    }

    attempt = 0
    while True:
        try:
            response = table.scan(**scan_kwargs)
            records.extend(response.get("Items", []))

            # Handle pagination
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            scan_kwargs["ExclusiveStartKey"] = last_key
            # Reset attempt counter on successful page scan
            attempt = 0

        except Exception as e:
            error_str = str(e).lower()
            is_timeout = (
                "timeout" in error_str
                or "timed out" in error_str
                or "read timeout" in error_str
                or "connect timeout" in error_str
                or (hasattr(e, "response") and
                    getattr(e, "response", {}).get("Error", {}).get("Code", "") == "RequestTimeout")
            )

            if is_timeout and attempt < max_retries:
                attempt += 1
                wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8 seconds
                logger.warning(json.dumps({
                    "event": "dynamodb_scan_timeout_retry",
                    "pipeline_id": pipeline_id,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "wait_seconds": wait_time,
                    "error": str(e),
                }))
                time.sleep(wait_time)
                continue
            else:
                # Non-retryable error or retries exhausted
                logger.error(json.dumps({
                    "event": "dynamodb_scan_failed",
                    "pipeline_id": pipeline_id,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "error": str(e),
                    "is_timeout": is_timeout,
                }))
                raise

    logger.info(json.dumps({
        "event": "dynamodb_scan_complete",
        "pipeline_id": pipeline_id,
        "total_records": len(records),
    }))

    return records


# ---------------------------------------------------------------------------
# Data Transformation — DynamoDB records → Neptune node dicts (Task 9.2)
# ---------------------------------------------------------------------------

def _decimal_to_native(value):
    """Convert Decimal values to int or float for JSON serialization."""
    if isinstance(value, Decimal):
        if value == int(value):
            return int(value)
        return float(value)
    return value


def transform_module_parse_to_module_def(record: dict) -> dict | None:
    """Transform a module_parse DynamoDB record into a ModuleDef node dict.

    ModuleDef node properties: name, file_path, pipeline_id, module_type

    Args:
        record: DynamoDB record with analysis_type='module_parse'

    Returns:
        Node dict with label 'ModuleDef' and properties, or None if invalid
    """
    module_name = record.get("module_name")
    if not module_name:
        return None

    return {
        "label": "ModuleDef",
        "properties": {
            "name": module_name,
            "file_path": record.get("file_path", ""),
            "pipeline_id": record.get("pipeline_id", ""),
            "module_type": record.get("module_type", "module"),
        },
    }


def transform_module_parse_to_instances(record: dict) -> list[dict]:
    """Transform instance_list from a module_parse record into Instance node dicts.

    Instance node properties: instance_name, hier_path, generate_scope, x, y, parent_instance

    Args:
        record: DynamoDB record with analysis_type='module_parse'

    Returns:
        List of Instance node dicts
    """
    instances = []
    instance_list = record.get("instance_list", [])
    module_name = record.get("module_name", "")
    pipeline_id = record.get("pipeline_id", "")

    if isinstance(instance_list, str):
        try:
            instance_list = json.loads(instance_list)
        except (json.JSONDecodeError, TypeError):
            instance_list = []

    for inst in instance_list:
        if isinstance(inst, str):
            # Simple string instance name
            instance_name = inst
            hier_path = f"{module_name}/{inst}"
            instances.append({
                "label": "Instance",
                "properties": {
                    "instance_name": instance_name,
                    "hier_path": hier_path,
                    "generate_scope": "",
                    "x": None,
                    "y": None,
                    "parent_instance": module_name,
                    "pipeline_id": pipeline_id,
                },
            })
        elif isinstance(inst, dict):
            instance_name = inst.get("instance_name", inst.get("name", ""))
            if not instance_name:
                continue
            hier_path = inst.get("hier_path", f"{module_name}/{instance_name}")
            instances.append({
                "label": "Instance",
                "properties": {
                    "instance_name": instance_name,
                    "hier_path": hier_path,
                    "generate_scope": inst.get("generate_scope", ""),
                    "x": _decimal_to_native(inst.get("x")),
                    "y": _decimal_to_native(inst.get("y")),
                    "parent_instance": inst.get("parent_instance", module_name),
                    "pipeline_id": pipeline_id,
                },
            })

    return instances


def transform_module_parse_to_port_nodes(record: dict) -> tuple[list[dict], list[dict]]:
    """Transform port_list from a module_parse record into PortDef and PortInstance nodes.

    PortDef node properties: name, direction, bit_width, parent_module
    PortInstance node properties: name, direction, bit_width, parent_instance, hier_path

    Args:
        record: DynamoDB record with analysis_type='module_parse'

    Returns:
        Tuple of (port_def_nodes, port_instance_nodes)
    """
    port_defs = []
    port_instances = []
    port_list = record.get("port_list", [])
    module_name = record.get("module_name", "")
    pipeline_id = record.get("pipeline_id", "")

    if isinstance(port_list, str):
        try:
            port_list = json.loads(port_list)
        except (json.JSONDecodeError, TypeError):
            port_list = []

    for port in port_list:
        if isinstance(port, str):
            # Simple port name string — minimal info
            port_defs.append({
                "label": "PortDef",
                "properties": {
                    "name": port,
                    "direction": "unknown",
                    "bit_width": "",
                    "parent_module": module_name,
                    "pipeline_id": pipeline_id,
                },
            })
        elif isinstance(port, dict):
            port_name = port.get("name", port.get("port_name", ""))
            if not port_name:
                continue
            direction = port.get("direction", "unknown")
            bit_width = str(port.get("bit_width", port.get("width", "")))

            port_defs.append({
                "label": "PortDef",
                "properties": {
                    "name": port_name,
                    "direction": direction,
                    "bit_width": bit_width,
                    "parent_module": module_name,
                    "pipeline_id": pipeline_id,
                },
            })

            # PortInstance for each instance of this module
            port_instances.append({
                "label": "PortInstance",
                "properties": {
                    "name": port_name,
                    "direction": direction,
                    "bit_width": bit_width,
                    "parent_instance": module_name,
                    "hier_path": f"{module_name}/{port_name}",
                    "pipeline_id": pipeline_id,
                },
            })

    return port_defs, port_instances


def transform_wire_claim_to_signal(record: dict) -> dict | None:
    """Transform a WireTopology claim into a Signal node dict.

    Signal node properties: name, dimensions, struct_type, purpose

    Args:
        record: DynamoDB claim record with topic='WireTopology'

    Returns:
        Signal node dict, or None if invalid
    """
    claim_text = record.get("claim_text", "")
    module_name = record.get("module_name", "")
    pipeline_id = record.get("pipeline_id", "")

    # Extract signal name from claim data
    signal_name = record.get("signal_name", "")
    if not signal_name:
        # Try to extract from claim_text — pattern: "Wire 'name' ..." or "Signal 'name' ..."
        for prefix in ("Wire '", "Signal '", "wire '", "signal '"):
            if prefix in claim_text:
                start = claim_text.index(prefix) + len(prefix)
                end = claim_text.index("'", start)
                signal_name = claim_text[start:end]
                break

    if not signal_name:
        return None

    dimensions = record.get("dimensions", "")
    if isinstance(dimensions, list):
        dimensions = json.dumps(dimensions)
    elif isinstance(dimensions, str):
        pass  # already a string
    else:
        dimensions = str(dimensions) if dimensions else ""

    return {
        "label": "Signal",
        "properties": {
            "name": signal_name,
            "dimensions": dimensions,
            "struct_type": record.get("struct_type", ""),
            "purpose": record.get("purpose", ""),
            "scope": module_name,
            "pipeline_id": pipeline_id,
        },
    }


def transform_clock_domain_claim(record: dict) -> dict | None:
    """Transform a ClockDomain claim into a ClockDomain node dict.

    ClockDomain node properties: name, frequency, source_module

    Args:
        record: DynamoDB claim record with topic='ClockDomain'

    Returns:
        ClockDomain node dict, or None if invalid
    """
    claim_text = record.get("claim_text", "")
    module_name = record.get("module_name", "")
    pipeline_id = record.get("pipeline_id", "")

    # Extract clock domain name from record or claim_text
    domain_name = record.get("clock_domain", record.get("domain_name", ""))
    if not domain_name:
        # Try to extract from claim_text — pattern: "Clock domain 'name' ..."
        for prefix in ("Clock domain '", "clock domain '", "ClockDomain '"):
            if prefix in claim_text:
                start = claim_text.index(prefix) + len(prefix)
                end = claim_text.index("'", start)
                domain_name = claim_text[start:end]
                break

    if not domain_name:
        # Use module_name as fallback domain identifier
        domain_name = f"{module_name}_clk" if module_name else ""

    if not domain_name:
        return None

    frequency = record.get("frequency", "")
    if isinstance(frequency, Decimal):
        frequency = _decimal_to_native(frequency)

    return {
        "label": "ClockDomain",
        "properties": {
            "name": domain_name,
            "frequency": str(frequency) if frequency else "",
            "source_module": module_name,
            "pipeline_id": pipeline_id,
        },
    }


def transform_records_to_nodes(records: list[dict]) -> list[dict]:
    """Transform all DynamoDB records into Neptune node dicts.

    Dispatches records by analysis_type and topic to appropriate transformers.

    Args:
        records: List of DynamoDB records for a pipeline_id

    Returns:
        List of node dicts with 'label' and 'properties' keys
    """
    nodes = []
    skipped = 0

    for record in records:
        analysis_type = record.get("analysis_type", "")

        if analysis_type == "module_parse":
            # ModuleDef node
            module_node = transform_module_parse_to_module_def(record)
            if module_node:
                nodes.append(module_node)

            # Instance nodes
            instance_nodes = transform_module_parse_to_instances(record)
            nodes.extend(instance_nodes)

            # PortDef and PortInstance nodes
            port_defs, port_instances = transform_module_parse_to_port_nodes(record)
            nodes.extend(port_defs)
            nodes.extend(port_instances)

        elif analysis_type == "claim":
            topic = record.get("topic", "")

            if topic == "WireTopology":
                signal_node = transform_wire_claim_to_signal(record)
                if signal_node:
                    nodes.append(signal_node)
                else:
                    skipped += 1

            elif topic == "ClockDomain":
                clock_node = transform_clock_domain_claim(record)
                if clock_node:
                    nodes.append(clock_node)
                else:
                    skipped += 1
            else:
                # Other claim topics are not transformed to nodes in this task
                pass
        else:
            skipped += 1

    logger.info(json.dumps({
        "event": "transform_complete",
        "total_nodes": len(nodes),
        "skipped_records": skipped,
        "node_breakdown": _count_node_labels(nodes),
    }))

    return nodes


def _count_node_labels(nodes: list[dict]) -> dict[str, int]:
    """Count nodes by label for summary logging."""
    counts: dict[str, int] = {}
    for node in nodes:
        label = node.get("label", "Unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Neptune MERGE Upsert — Node Loading (Task 9.3)
# Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
# ---------------------------------------------------------------------------

# Composite key definitions for each node type.
# These keys form the MERGE match criteria ensuring idempotent upserts.
NODE_COMPOSITE_KEYS: dict[str, list[str]] = {
    "ModuleDef": ["pipeline_id", "name"],
    "Instance": ["pipeline_id", "hier_path"],
    "PortDef": ["pipeline_id", "parent_module", "name"],
    "PortInstance": ["pipeline_id", "hier_path"],
    "Signal": ["pipeline_id", "scope", "name"],
    "ClockDomain": ["pipeline_id", "name"],
}


def build_merge_query(node: dict) -> tuple[str, dict]:
    """Build a MERGE openCypher query for a single node.

    Uses composite keys for the MERGE match and SET for remaining properties.
    This ensures idempotent upserts — re-running produces no duplicates.

    Args:
        node: Node dict with 'label' and 'properties' keys.

    Returns:
        Tuple of (query_string, parameters_dict).

    Raises:
        ValueError: If node label is unknown or composite key fields are missing.
    """
    label = node.get("label", "")
    properties = node.get("properties", {})

    if label not in NODE_COMPOSITE_KEYS:
        raise ValueError(f"Unknown node label: {label}")

    composite_keys = NODE_COMPOSITE_KEYS[label]

    # Validate that all composite key fields are present and non-empty
    for key in composite_keys:
        value = properties.get(key)
        if value is None or value == "":
            raise ValueError(
                f"Missing composite key field '{key}' for node label '{label}'"
            )

    # Build MERGE clause with composite key properties
    merge_props = ", ".join(f"{k}: ${k}" for k in composite_keys)

    # Build SET clause with remaining (non-key) properties
    set_props = []
    for k, v in properties.items():
        if k not in composite_keys and v is not None:
            set_props.append(f"n.{k} = $set_{k}")

    query = f"MERGE (n:{label} {{{merge_props}}})"
    if set_props:
        query += " SET " + ", ".join(set_props)

    # Build parameters dict
    params = {}
    for k in composite_keys:
        params[k] = properties[k]
    for k, v in properties.items():
        if k not in composite_keys and v is not None:
            params[f"set_{k}"] = v

    return query, params


def batch_upsert_nodes(
    client: NeptuneSigV4Client,
    nodes: list[dict],
    batch_size: int = 50,
) -> dict:
    """Upsert nodes to Neptune in batches using MERGE queries.

    Executes one MERGE query per node, grouped into batches of batch_size.
    Each MERGE uses composite keys to prevent duplicate nodes on re-execution.

    Args:
        client: Authenticated NeptuneSigV4Client instance.
        nodes: List of node dicts from transform_records_to_nodes().
        batch_size: Number of nodes per batch (default: 50).

    Returns:
        Summary dict with counts: upserted, skipped, failed, by_label.
    """
    upserted = 0
    skipped = 0
    failed = 0
    by_label: dict[str, int] = {}

    total = len(nodes)
    num_batches = (total + batch_size - 1) // batch_size if total > 0 else 0

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch = nodes[start:end]

        logger.debug(json.dumps({
            "event": "batch_start",
            "batch": batch_idx + 1,
            "total_batches": num_batches,
            "batch_size": len(batch),
        }))

        for node in batch:
            label = node.get("label", "Unknown")
            try:
                query, params = build_merge_query(node)
            except ValueError as e:
                logger.warning(json.dumps({
                    "event": "node_skip_invalid",
                    "label": label,
                    "reason": str(e),
                }))
                skipped += 1
                continue

            try:
                client.execute_query(query, params)
                upserted += 1
                by_label[label] = by_label.get(label, 0) + 1
            except Exception as e:
                logger.error(json.dumps({
                    "event": "node_upsert_failed",
                    "label": label,
                    "error": str(e),
                    "query": query,
                }))
                failed += 1

    summary = {
        "upserted": upserted,
        "skipped": skipped,
        "failed": failed,
        "by_label": by_label,
    }

    logger.info(json.dumps({
        "event": "node_upsert_complete",
        "summary": summary,
    }))

    return summary


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:])

    Returns:
        Parsed namespace with pipeline_id, neptune_endpoint, batch_size,
        dry_run, and verbose flags.
    """
    parser = argparse.ArgumentParser(
        prog="neptune_ingestion",
        description="Neptune Ingestion Pipeline — DynamoDB 파싱 데이터를 Neptune Graph DB에 적재",
    )
    parser.add_argument(
        "--pipeline-id",
        required=True,
        help="DynamoDB 레코드 필터링 키 (e.g., tt_20260221)",
    )
    parser.add_argument(
        "--neptune-endpoint",
        default=None,
        help="Neptune cluster endpoint (default: env NEPTUNE_ENDPOINT)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch upsert 크기 (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Neptune 쓰기 없이 변환 결과만 출력",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="상세 로그 출력 (DEBUG level)",
    )

    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Edge Transformation — DynamoDB records → Neptune edge dicts (Task 10.1)
# Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
# ---------------------------------------------------------------------------

# Composite key definitions for each edge type.
# These keys form the MERGE match criteria ensuring idempotent edge upserts.
EDGE_COMPOSITE_KEYS: dict[str, dict] = {
    "DEFINES": {
        "from_label": "ModuleDef",
        "to_label": "PortDef",
        "from_key": ["pipeline_id", "name"],
        "to_key": ["pipeline_id", "parent_module", "name"],
        "edge_keys": [],
    },
    "INSTANCE_OF": {
        "from_label": "Instance",
        "to_label": "ModuleDef",
        "from_key": ["pipeline_id", "hier_path"],
        "to_key": ["pipeline_id", "name"],
        "edge_keys": ["instance_name"],
    },
    "INSTANTIATES": {
        "from_label": "Instance",
        "to_label": "Instance",
        "from_key": ["pipeline_id", "hier_path"],
        "to_key": ["pipeline_id", "hier_path"],
        "edge_keys": [],
    },
    "HAS_PORT": {
        "from_label": "Instance",
        "to_label": "PortInstance",
        "from_key": ["pipeline_id", "hier_path"],
        "to_key": ["pipeline_id", "hier_path"],
        "edge_keys": [],
    },
    "BINDS_TO": {
        "from_label": "PortInstance",
        "to_label": "Signal",
        "from_key": ["pipeline_id", "hier_path"],
        "to_key": ["pipeline_id", "scope", "name"],
        "edge_keys": ["signal_expr", "expression_type"],
    },
    "DRIVES": {
        "from_label": "PortInstance",
        "to_label": "Signal",
        "from_key": ["pipeline_id", "hier_path"],
        "to_key": ["pipeline_id", "scope", "name"],
        "edge_keys": ["driver_type"],
    },
    "READS": {
        "from_label": "Signal",
        "to_label": "PortInstance",
        "from_key": ["pipeline_id", "scope", "name"],
        "to_key": ["pipeline_id", "hier_path"],
        "edge_keys": ["reader_type"],
    },
    "BELONGS_TO": {
        "from_label": "Signal",
        "to_label": "ClockDomain",
        "from_key": ["pipeline_id", "scope", "name"],
        "to_key": ["pipeline_id", "name"],
        "edge_keys": [],
    },
}


def transform_records_to_edges(records: list[dict], nodes: list[dict]) -> list[dict]:
    """Transform DynamoDB records into Neptune edge dicts.

    Generates edges based on relationships found in module_parse and claim records:
    - DEFINES: ModuleDef -> PortDef (from port_list in module_parse)
    - INSTANCE_OF: Instance -> ModuleDef (from instance_list in module_parse)
    - HAS_PORT: Instance -> PortInstance (from port_list)
    - BINDS_TO: PortInstance -> Signal (from PortBinding claims)
    - DRIVES: output PortInstance -> Signal
    - READS: Signal -> input PortInstance
    - BELONGS_TO: Signal -> ClockDomain

    Args:
        records: List of DynamoDB records for a pipeline_id
        nodes: List of already-transformed node dicts (for reference)

    Returns:
        List of edge dicts with 'type', 'from_node', 'to_node', 'properties' keys
    """
    edges = []
    skipped = 0

    for record in records:
        analysis_type = record.get("analysis_type", "")
        pipeline_id = record.get("pipeline_id", "")
        module_name = record.get("module_name", "")

        if analysis_type == "module_parse":
            # DEFINES edges: ModuleDef -> PortDef
            port_list = record.get("port_list", [])
            if isinstance(port_list, str):
                try:
                    port_list = json.loads(port_list)
                except (json.JSONDecodeError, TypeError):
                    port_list = []

            for port in port_list:
                if isinstance(port, dict):
                    port_name = port.get("name", port.get("port_name", ""))
                    if port_name and module_name:
                        edges.append({
                            "type": "DEFINES",
                            "from_node": {"label": "ModuleDef", "pipeline_id": pipeline_id, "name": module_name},
                            "to_node": {"label": "PortDef", "pipeline_id": pipeline_id, "parent_module": module_name, "name": port_name},
                            "properties": {},
                        })

                        # HAS_PORT edges: Instance -> PortInstance
                        edges.append({
                            "type": "HAS_PORT",
                            "from_node": {"label": "Instance", "pipeline_id": pipeline_id, "hier_path": module_name},
                            "to_node": {"label": "PortInstance", "pipeline_id": pipeline_id, "hier_path": f"{module_name}/{port_name}"},
                            "properties": {},
                        })

            # INSTANCE_OF edges: Instance -> ModuleDef
            instance_list = record.get("instance_list", [])
            if isinstance(instance_list, str):
                try:
                    instance_list = json.loads(instance_list)
                except (json.JSONDecodeError, TypeError):
                    instance_list = []

            for inst in instance_list:
                if isinstance(inst, str):
                    instance_name = inst
                    hier_path = f"{module_name}/{inst}"
                    edges.append({
                        "type": "INSTANCE_OF",
                        "from_node": {"label": "Instance", "pipeline_id": pipeline_id, "hier_path": hier_path},
                        "to_node": {"label": "ModuleDef", "pipeline_id": pipeline_id, "name": instance_name},
                        "properties": {"instance_name": instance_name},
                    })
                elif isinstance(inst, dict):
                    instance_name = inst.get("instance_name", inst.get("name", ""))
                    if not instance_name:
                        skipped += 1
                        continue
                    hier_path = inst.get("hier_path", f"{module_name}/{instance_name}")
                    module_type_name = inst.get("module_type", instance_name)
                    edges.append({
                        "type": "INSTANCE_OF",
                        "from_node": {"label": "Instance", "pipeline_id": pipeline_id, "hier_path": hier_path},
                        "to_node": {"label": "ModuleDef", "pipeline_id": pipeline_id, "name": module_type_name},
                        "properties": {"instance_name": instance_name, "generate_scope": inst.get("generate_scope", "")},
                    })

        elif analysis_type == "claim":
            topic = record.get("topic", "")

            if topic == "PortBinding":
                # BINDS_TO: PortInstance -> Signal
                port_name = record.get("port_name", "")
                signal_name = record.get("signal_name", record.get("signal_expr", ""))
                expression_type = record.get("expression_type", "simple")
                signal_expr = record.get("signal_expr", "")

                if port_name and signal_name and module_name:
                    port_hier = f"{module_name}/{port_name}"
                    direction = record.get("direction", "")

                    edges.append({
                        "type": "BINDS_TO",
                        "from_node": {"label": "PortInstance", "pipeline_id": pipeline_id, "hier_path": port_hier},
                        "to_node": {"label": "Signal", "pipeline_id": pipeline_id, "scope": module_name, "name": signal_name},
                        "properties": {"signal_expr": signal_expr, "expression_type": expression_type},
                    })

                    # DRIVES: output PortInstance -> Signal
                    if direction in ("output", "inout"):
                        edges.append({
                            "type": "DRIVES",
                            "from_node": {"label": "PortInstance", "pipeline_id": pipeline_id, "hier_path": port_hier},
                            "to_node": {"label": "Signal", "pipeline_id": pipeline_id, "scope": module_name, "name": signal_name},
                            "properties": {"driver_type": direction},
                        })

                    # READS: Signal -> input PortInstance
                    if direction in ("input", "inout"):
                        edges.append({
                            "type": "READS",
                            "from_node": {"label": "Signal", "pipeline_id": pipeline_id, "scope": module_name, "name": signal_name},
                            "to_node": {"label": "PortInstance", "pipeline_id": pipeline_id, "hier_path": port_hier},
                            "properties": {"reader_type": direction},
                        })
                else:
                    skipped += 1

            elif topic == "ClockDomain":
                # BELONGS_TO: Signal -> ClockDomain
                signal_name = record.get("signal_name", "")
                domain_name = record.get("clock_domain", record.get("domain_name", ""))

                if signal_name and domain_name and module_name:
                    edges.append({
                        "type": "BELONGS_TO",
                        "from_node": {"label": "Signal", "pipeline_id": pipeline_id, "scope": module_name, "name": signal_name},
                        "to_node": {"label": "ClockDomain", "pipeline_id": pipeline_id, "name": domain_name},
                        "properties": {},
                    })

    logger.info(json.dumps({
        "event": "edge_transform_complete",
        "total_edges": len(edges),
        "skipped_records": skipped,
        "edge_breakdown": _count_edge_types(edges),
    }))

    return edges


def _count_edge_types(edges: list[dict]) -> dict[str, int]:
    """Count edges by type for summary logging."""
    counts: dict[str, int] = {}
    for edge in edges:
        edge_type = edge.get("type", "Unknown")
        counts[edge_type] = counts.get(edge_type, 0) + 1
    return counts


def build_edge_merge_query(edge: dict) -> tuple[str, dict]:
    """Build a MERGE openCypher query for a single edge.

    Uses MATCH for source/target nodes and MERGE for the edge itself,
    ensuring idempotent upserts.

    Args:
        edge: Edge dict with 'type', 'from_node', 'to_node', 'properties' keys.

    Returns:
        Tuple of (query_string, parameters_dict).

    Raises:
        ValueError: If edge type is unknown or required fields are missing.
    """
    edge_type = edge.get("type", "")
    from_node = edge.get("from_node", {})
    to_node = edge.get("to_node", {})
    properties = edge.get("properties", {})

    if edge_type not in EDGE_COMPOSITE_KEYS:
        raise ValueError(f"Unknown edge type: {edge_type}")

    edge_def = EDGE_COMPOSITE_KEYS[edge_type]
    from_label = edge_def["from_label"]
    to_label = edge_def["to_label"]

    # Build MATCH clause for source node
    from_match_props = ", ".join(
        f"{k}: $from_{k}" for k in edge_def["from_key"]
    )

    # Build MATCH clause for target node
    to_match_props = ", ".join(
        f"{k}: $to_{k}" for k in edge_def["to_key"]
    )

    # Build MERGE clause for edge (with edge keys if any)
    non_empty_edge_keys = [
        k for k in edge_def["edge_keys"]
        if properties.get(k) is not None and properties.get(k) != ""
    ]
    if non_empty_edge_keys:
        edge_merge_props = ", ".join(f"{k}: $edge_{k}" for k in non_empty_edge_keys)
        edge_merge = f"[r:{edge_type} {{{edge_merge_props}}}]"
    else:
        edge_merge = f"[r:{edge_type}]"

    # Build SET clause for remaining edge properties
    set_props = []
    for k, v in properties.items():
        if k not in edge_def["edge_keys"] and v is not None and v != "":
            set_props.append(f"r.{k} = $prop_{k}")

    query = (
        f"MATCH (a:{from_label} {{{from_match_props}}})\n"
        f"MATCH (b:{to_label} {{{to_match_props}}})\n"
        f"MERGE (a)-{edge_merge}->(b)"
    )
    if set_props:
        query += "\nSET " + ", ".join(set_props)

    # Build parameters
    params = {}
    for k in edge_def["from_key"]:
        params[f"from_{k}"] = from_node.get(k, "")
    for k in edge_def["to_key"]:
        params[f"to_{k}"] = to_node.get(k, "")
    for k in non_empty_edge_keys:
        params[f"edge_{k}"] = properties[k]
    for k, v in properties.items():
        if k not in edge_def["edge_keys"] and v is not None and v != "":
            params[f"prop_{k}"] = v

    return query, params


def batch_upsert_edges(
    client: NeptuneSigV4Client,
    edges: list[dict],
    batch_size: int = 50,
) -> dict:
    """Upsert edges to Neptune in batches using MERGE queries.

    Executes one MERGE query per edge, grouped into batches of batch_size.
    Each MERGE uses MATCH for endpoints and MERGE for the relationship.

    Args:
        client: Authenticated NeptuneSigV4Client instance.
        edges: List of edge dicts from transform_records_to_edges().
        batch_size: Number of edges per batch (default: 50).

    Returns:
        Summary dict with counts: upserted, skipped, failed, by_type.
    """
    upserted = 0
    skipped = 0
    failed = 0
    by_type: dict[str, int] = {}

    total = len(edges)
    num_batches = (total + batch_size - 1) // batch_size if total > 0 else 0

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch = edges[start:end]

        logger.debug(json.dumps({
            "event": "edge_batch_start",
            "batch": batch_idx + 1,
            "total_batches": num_batches,
            "batch_size": len(batch),
        }))

        for edge in batch:
            edge_type = edge.get("type", "Unknown")
            try:
                query, params = build_edge_merge_query(edge)
            except ValueError as e:
                logger.warning(json.dumps({
                    "event": "edge_skip_invalid",
                    "type": edge_type,
                    "reason": str(e),
                }))
                skipped += 1
                continue

            try:
                client.execute_query(query, params)
                upserted += 1
                by_type[edge_type] = by_type.get(edge_type, 0) + 1
            except Exception as e:
                logger.error(json.dumps({
                    "event": "edge_upsert_failed",
                    "type": edge_type,
                    "error": str(e),
                    "query": query,
                }))
                failed += 1

    summary = {
        "upserted": upserted,
        "skipped": skipped,
        "failed": failed,
        "by_type": by_type,
    }

    logger.info(json.dumps({
        "event": "edge_upsert_complete",
        "summary": summary,
    }))

    return summary


# ---------------------------------------------------------------------------
# Completion Summary and Validation (Task 10.2)
# Requirements: 12.5, 13.1
# ---------------------------------------------------------------------------

SKIP_RATIO_WARNING_THRESHOLD = 0.30  # 30% skip ratio triggers warning escalation


def _count_module_parse_records(records: list[dict]) -> int:
    """Count the number of module_parse records in the DynamoDB scan results."""
    return sum(1 for r in records if r.get("analysis_type") == "module_parse")


def _detect_parsing_ingestion_mismatch(
    module_parse_count: int,
    total_nodes_created: int,
) -> bool:
    """Detect parsing-to-ingestion mismatch.

    If parsing discovered N>0 modules but ingestion produced 0 nodes,
    this indicates a critical mismatch that should be reported as an error.

    Args:
        module_parse_count: Number of module_parse records found in DynamoDB
        total_nodes_created: Total nodes successfully created/upserted in Neptune

    Returns:
        True if mismatch detected, False otherwise
    """
    return module_parse_count > 0 and total_nodes_created == 0


def _check_skip_ratio(skipped_records: int, total_records: int) -> tuple[bool, float]:
    """Check if skip ratio exceeds the warning threshold (30%).

    Args:
        skipped_records: Number of records that were skipped during transformation
        total_records: Total number of records processed

    Returns:
        Tuple of (threshold_exceeded: bool, ratio: float)
    """
    if total_records == 0:
        return False, 0.0
    ratio = skipped_records / total_records
    return ratio > SKIP_RATIO_WARNING_THRESHOLD, ratio


def _log_completion_summary(
    pipeline_id: str,
    total_nodes_created: int,
    total_edges_created: int,
    execution_time_seconds: float,
    skipped_records: int,
    total_records: int,
    node_breakdown: dict[str, int] | None = None,
    edge_breakdown: dict[str, int] | None = None,
) -> None:
    """Log structured completion summary as JSON.

    Includes skip ratio warning escalation when threshold is exceeded.

    Args:
        pipeline_id: Pipeline ID for this ingestion run
        total_nodes_created: Total nodes upserted to Neptune
        total_edges_created: Total edges upserted to Neptune
        execution_time_seconds: Total execution time in seconds
        skipped_records: Number of records skipped during transformation
        total_records: Total records scanned from DynamoDB
        node_breakdown: Optional dict of node counts by label
        edge_breakdown: Optional dict of edge counts by type
    """
    threshold_exceeded, skip_ratio = _check_skip_ratio(skipped_records, total_records)

    summary = {
        "event": "ingestion_complete",
        "pipeline_id": pipeline_id,
        "total_nodes_created": total_nodes_created,
        "total_edges_created": total_edges_created,
        "execution_time_seconds": round(execution_time_seconds, 3),
        "skipped_records": skipped_records,
        "total_records_scanned": total_records,
        "skip_ratio": round(skip_ratio, 4),
    }

    if node_breakdown:
        summary["node_breakdown"] = node_breakdown
    if edge_breakdown:
        summary["edge_breakdown"] = edge_breakdown

    # Escalate to WARNING level if skip ratio exceeds threshold
    if threshold_exceeded:
        summary["skip_ratio_warning"] = True
        summary["message"] = (
            f"Skip ratio {skip_ratio:.1%} exceeds threshold "
            f"{SKIP_RATIO_WARNING_THRESHOLD:.0%}. "
            "Review skipped records for potential data quality issues."
        )
        logger.warning(json.dumps(summary, ensure_ascii=False))
    else:
        logger.info(json.dumps(summary, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Graph Export API Verification (Task 13.1)
# Requirements: 13.1, 13.2, 13.3
# ---------------------------------------------------------------------------

class GraphExportVerificationResult:
    """Result of Graph Export API verification after ingestion."""

    def __init__(self):
        self.chip_verified: bool = False
        self.module_verified: bool = False
        self.chip_node_count: int = 0
        self.chip_edge_count: int = 0
        self.module_node_count: int = 0
        self.module_edge_count: int = 0
        self.chip_edge_types: dict[str, int] = {}
        self.module_edge_types: dict[str, int] = {}
        self.module_node_types: dict[str, int] = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def success(self) -> bool:
        """True if verification passed without errors."""
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        """Serialize to dict for JSON logging."""
        return {
            "success": self.success,
            "chip_verified": self.chip_verified,
            "module_verified": self.module_verified,
            "chip_node_count": self.chip_node_count,
            "chip_edge_count": self.chip_edge_count,
            "module_node_count": self.module_node_count,
            "module_edge_count": self.module_edge_count,
            "chip_edge_types": self.chip_edge_types,
            "module_edge_types": self.module_edge_types,
            "module_node_types": self.module_node_types,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _call_graph_export_api(
    client: NeptuneSigV4Client,
    scope: str,
    root_module: str,
) -> dict:
    """Call Graph Export API by querying Neptune directly for verification.

    Simulates the Graph Export API logic by executing the same openCypher queries
    that the API uses, returning node/edge counts and type breakdowns.

    Args:
        client: Authenticated NeptuneSigV4Client instance.
        scope: Query scope — "chip" or "module".
        root_module: Root module name to query.

    Returns:
        Dict with 'nodes', 'edges', 'node_count', 'edge_count',
        'node_types', 'edge_types' keys.

    Raises:
        Exception: On Neptune query failure.
    """
    if scope == "chip":
        # scope "chip": Module nodes + INSTANTIATES edges
        query = (
            "MATCH (root:ModuleDef {name: $root_module})-[:INSTANTIATES]->(child) "
            "RETURN root.name AS root_name, child.name AS child_name, "
            "labels(child) AS child_labels "
            "LIMIT 1000"
        )
        params = {"root_module": root_module}

        result = client.execute_query(query, params)

        # Count Module nodes and INSTANTIATES edges from result
        nodes_set = set()
        edge_count = 0
        node_types: dict[str, int] = {}
        edge_types: dict[str, int] = {}

        for row in result.get("results", []):
            root_name = row.get("root_name", "")
            child_name = row.get("child_name", "")
            if root_name:
                nodes_set.add(root_name)
            if child_name:
                nodes_set.add(child_name)
                edge_count += 1
                edge_types["INSTANTIATES"] = edge_types.get("INSTANTIATES", 0) + 1

        node_types["Module"] = len(nodes_set)

        # If direct query returned nothing, try counting the root module node
        if not nodes_set:
            count_query = (
                "MATCH (n:ModuleDef {name: $root_module}) "
                "RETURN count(n) AS node_count"
            )
            try:
                count_result = client.execute_query(count_query, {"root_module": root_module})
                for row in count_result.get("results", []):
                    nc = row.get("node_count", 0)
                    if nc > 0:
                        nodes_set.add(root_module)
                        node_types["Module"] = nc
            except Exception:
                pass

        return {
            "nodes": list(nodes_set),
            "edges": edge_count,
            "node_count": len(nodes_set),
            "edge_count": edge_count,
            "node_types": node_types,
            "edge_types": edge_types,
        }

    elif scope == "module":
        # scope "module": Port + Signal nodes + CONNECTS_TO/DRIVES edges
        query = (
            "MATCH (m:ModuleDef {name: $root_module})"
            "-[:DEFINES]->(p:PortDef) "
            "OPTIONAL MATCH (pi:PortInstance {parent_instance: $root_module})"
            "-[r:BINDS_TO|DRIVES]->(s:Signal) "
            "RETURN p.name AS port_name, p.direction AS port_direction, "
            "s.name AS signal_name, type(r) AS rel_type "
            "LIMIT 1000"
        )
        params = {"root_module": root_module}

        result = client.execute_query(query, params)

        port_nodes = set()
        signal_nodes = set()
        edge_types: dict[str, int] = {}
        node_types: dict[str, int] = {"Port": 0, "Signal": 0}

        for row in result.get("results", []):
            port_name = row.get("port_name", "")
            signal_name = row.get("signal_name", "")
            rel_type = row.get("rel_type", "")

            if port_name:
                port_nodes.add(port_name)
            if signal_name:
                signal_nodes.add(signal_name)
            if rel_type:
                edge_types[rel_type] = edge_types.get(rel_type, 0) + 1

        node_types["Port"] = len(port_nodes)
        node_types["Signal"] = len(signal_nodes)
        total_nodes = len(port_nodes) + len(signal_nodes)
        total_edges = sum(edge_types.values())

        return {
            "nodes": list(port_nodes | signal_nodes),
            "edges": total_edges,
            "node_count": total_nodes,
            "edge_count": total_edges,
            "node_types": node_types,
            "edge_types": edge_types,
        }

    else:
        return {
            "nodes": [],
            "edges": 0,
            "node_count": 0,
            "edge_count": 0,
            "node_types": {},
            "edge_types": {},
        }


def verify_graph_export(
    client: NeptuneSigV4Client,
    pipeline_id: str,
    root_module: str,
    module_parse_count: int,
    total_nodes_created: int,
) -> GraphExportVerificationResult:
    """Verify Graph Export API returns expected data after ingestion.

    Performs post-ingestion verification by querying Neptune through the same
    patterns used by the Graph Export API. Checks:
    1. scope "chip": Module nodes + INSTANTIATES edges are present
    2. scope "module": Port + Signal nodes + CONNECTS_TO/DRIVES edges are present
    3. Parsing N>0 modules but ingestion 0 nodes → error

    Args:
        client: Authenticated NeptuneSigV4Client instance.
        pipeline_id: Pipeline ID for this ingestion run.
        root_module: Root module name to verify against.
        module_parse_count: Number of module_parse records found during parsing.
        total_nodes_created: Total nodes created during ingestion.

    Returns:
        GraphExportVerificationResult with verification status and details.
    """
    result = GraphExportVerificationResult()

    # --- Check parsing-to-ingestion mismatch (Req 13.1) ---
    if _detect_parsing_ingestion_mismatch(module_parse_count, total_nodes_created):
        result.errors.append(
            f"Parsing-to-ingestion mismatch: parsed {module_parse_count} module(s) "
            f"but ingestion produced 0 nodes. Pipeline ID: {pipeline_id}"
        )
        logger.error(json.dumps({
            "event": "graph_export_verification_mismatch",
            "pipeline_id": pipeline_id,
            "module_parse_count": module_parse_count,
            "total_nodes_created": total_nodes_created,
        }))
        return result

    # --- Verify scope "chip" (Req 13.2) ---
    try:
        chip_result = _call_graph_export_api(client, "chip", root_module)
        result.chip_node_count = chip_result["node_count"]
        result.chip_edge_count = chip_result["edge_count"]
        result.chip_edge_types = chip_result["edge_types"]

        if result.chip_node_count > 0:
            result.chip_verified = True
            # Verify INSTANTIATES edges are present when there are child modules
            if result.chip_edge_count == 0 and module_parse_count > 1:
                result.warnings.append(
                    f"scope 'chip': Found {result.chip_node_count} Module node(s) "
                    f"but 0 INSTANTIATES edges. Expected hierarchy edges for "
                    f"{module_parse_count} parsed modules."
                )
        else:
            if total_nodes_created > 0:
                result.warnings.append(
                    f"scope 'chip': No Module nodes found for root_module='{root_module}' "
                    f"despite {total_nodes_created} total nodes created."
                )

        logger.info(json.dumps({
            "event": "graph_export_verify_chip",
            "pipeline_id": pipeline_id,
            "root_module": root_module,
            "node_count": result.chip_node_count,
            "edge_count": result.chip_edge_count,
            "edge_types": result.chip_edge_types,
            "verified": result.chip_verified,
        }))

    except Exception as e:
        result.errors.append(f"scope 'chip' verification failed: {e}")
        logger.error(json.dumps({
            "event": "graph_export_verify_chip_error",
            "pipeline_id": pipeline_id,
            "root_module": root_module,
            "error": str(e),
        }))

    # --- Verify scope "module" (Req 13.3) ---
    try:
        module_result = _call_graph_export_api(client, "module", root_module)
        result.module_node_count = module_result["node_count"]
        result.module_edge_count = module_result["edge_count"]
        result.module_edge_types = module_result["edge_types"]
        result.module_node_types = module_result["node_types"]

        if result.module_node_count > 0:
            result.module_verified = True
            # Verify expected edge types are present
            expected_edge_types = {"BINDS_TO", "DRIVES", "CONNECTS_TO"}
            found_edge_types = set(result.module_edge_types.keys())
            if found_edge_types and not found_edge_types.intersection(expected_edge_types):
                result.warnings.append(
                    f"scope 'module': Found edges of types {found_edge_types} "
                    f"but expected at least one of {expected_edge_types}."
                )
        else:
            if total_nodes_created > 0:
                result.warnings.append(
                    f"scope 'module': No Port/Signal nodes found for "
                    f"root_module='{root_module}' despite {total_nodes_created} "
                    f"total nodes created."
                )

        logger.info(json.dumps({
            "event": "graph_export_verify_module",
            "pipeline_id": pipeline_id,
            "root_module": root_module,
            "node_count": result.module_node_count,
            "edge_count": result.module_edge_count,
            "node_types": result.module_node_types,
            "edge_types": result.module_edge_types,
            "verified": result.module_verified,
        }))

    except Exception as e:
        result.errors.append(f"scope 'module' verification failed: {e}")
        logger.error(json.dumps({
            "event": "graph_export_verify_module_error",
            "pipeline_id": pipeline_id,
            "root_module": root_module,
            "error": str(e),
        }))

    # --- Final summary ---
    logger.info(json.dumps({
        "event": "graph_export_verification_complete",
        "pipeline_id": pipeline_id,
        "root_module": root_module,
        "result": result.to_dict(),
    }))

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    """Main entry point for Neptune ingestion pipeline.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    start_time = time.time()

    args = parse_args(argv)
    _setup_logging(verbose=args.verbose)

    logger.info(json.dumps({
        "event": "ingestion_start",
        "pipeline_id": args.pipeline_id,
        "batch_size": args.batch_size,
        "dry_run": args.dry_run,
    }))

    # --- Resolve Neptune endpoint ---
    neptune_endpoint = _resolve_neptune_endpoint(args.neptune_endpoint)

    if not neptune_endpoint:
        logger.error(json.dumps({
            "event": "neptune_endpoint_missing",
            "message": "Neptune endpoint not configured. Set --neptune-endpoint or NEPTUNE_ENDPOINT env var.",
            "pipeline_id": args.pipeline_id,
        }))
        return 1

    logger.info(json.dumps({
        "event": "neptune_endpoint_resolved",
        "endpoint": neptune_endpoint,
    }))

    # --- Dry-run mode: skip connectivity check ---
    if args.dry_run:
        logger.info(json.dumps({
            "event": "dry_run_mode",
            "message": "Dry-run mode enabled. Skipping Neptune connectivity check.",
            "pipeline_id": args.pipeline_id,
        }))
        # In dry-run mode, scan DynamoDB and transform but skip Neptune writes.
        try:
            records = scan_dynamodb_records(args.pipeline_id)
        except Exception as e:
            logger.error(json.dumps({
                "event": "dynamodb_scan_error",
                "message": f"Failed to scan DynamoDB: {e}",
                "pipeline_id": args.pipeline_id,
            }))
            return 1

        nodes = transform_records_to_nodes(records)
        edges = transform_records_to_edges(records, nodes)

        if args.verbose:
            for node in nodes:
                logger.debug(json.dumps({
                    "event": "dry_run_node",
                    "label": node["label"],
                    "properties": {k: v for k, v in node["properties"].items() if v is not None},
                }, ensure_ascii=False))
            for edge in edges:
                logger.debug(json.dumps({
                    "event": "dry_run_edge",
                    "type": edge["type"],
                    "from_node": edge["from_node"],
                    "to_node": edge["to_node"],
                    "properties": {k: v for k, v in edge["properties"].items() if v},
                }, ensure_ascii=False))

        execution_time = time.time() - start_time
        _log_completion_summary(
            pipeline_id=args.pipeline_id,
            total_nodes_created=0,
            total_edges_created=0,
            execution_time_seconds=execution_time,
            skipped_records=0,
            total_records=len(records),
            node_breakdown=_count_node_labels(nodes),
            edge_breakdown=_count_edge_types(edges),
        )

        logger.info(json.dumps({
            "event": "dry_run_complete",
            "pipeline_id": args.pipeline_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        }))
        return 0

    # --- Verify Neptune endpoint is reachable ---
    try:
        client = NeptuneSigV4Client(endpoint=neptune_endpoint)
        reachable = client.health_check()
    except Exception as e:
        logger.error(json.dumps({
            "event": "neptune_connection_error",
            "message": f"Failed to connect to Neptune endpoint: {e}",
            "endpoint": neptune_endpoint,
            "pipeline_id": args.pipeline_id,
        }))
        return 1

    if not reachable:
        logger.error(json.dumps({
            "event": "neptune_unreachable",
            "message": "Neptune endpoint is configured but unreachable.",
            "endpoint": neptune_endpoint,
            "pipeline_id": args.pipeline_id,
        }))
        return 1

    logger.info(json.dumps({
        "event": "neptune_connected",
        "endpoint": neptune_endpoint,
    }))

    # --- DynamoDB scan and data transformation ---
    try:
        records = scan_dynamodb_records(args.pipeline_id)
    except Exception as e:
        logger.error(json.dumps({
            "event": "dynamodb_scan_error",
            "message": f"Failed to scan DynamoDB: {e}",
            "pipeline_id": args.pipeline_id,
        }))
        return 1

    module_parse_count = _count_module_parse_records(records)
    nodes = transform_records_to_nodes(records)

    # --- Neptune MERGE upsert (Task 9.3) ---
    node_upsert_summary = batch_upsert_nodes(client, nodes, batch_size=args.batch_size)

    # --- Edge transformation and loading (Task 10.1) ---
    edges = transform_records_to_edges(records, nodes)
    edge_upsert_summary = batch_upsert_edges(client, edges, batch_size=args.batch_size)

    # --- Compute totals for summary ---
    total_nodes_created = node_upsert_summary["upserted"]
    total_edges_created = edge_upsert_summary["upserted"]
    skipped_records = (
        node_upsert_summary["skipped"] + node_upsert_summary["failed"]
        + edge_upsert_summary["skipped"] + edge_upsert_summary["failed"]
    )

    # --- Parsing-to-ingestion mismatch detection (Req 13.1) ---
    if _detect_parsing_ingestion_mismatch(module_parse_count, total_nodes_created):
        logger.error(json.dumps({
            "event": "parsing_ingestion_mismatch",
            "message": (
                f"Parsing discovered {module_parse_count} module(s) but ingestion "
                f"produced 0 nodes. This indicates a critical data pipeline issue."
            ),
            "pipeline_id": args.pipeline_id,
            "module_parse_count": module_parse_count,
            "total_nodes_created": total_nodes_created,
        }))

    # --- Completion summary log (Req 12.5) ---
    execution_time = time.time() - start_time
    _log_completion_summary(
        pipeline_id=args.pipeline_id,
        total_nodes_created=total_nodes_created,
        total_edges_created=total_edges_created,
        execution_time_seconds=execution_time,
        skipped_records=skipped_records,
        total_records=len(records),
        node_breakdown=node_upsert_summary.get("by_label"),
        edge_breakdown=edge_upsert_summary.get("by_type"),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Graph Evidence Provider — Neptune Graph DB에서 HDD 섹션별 evidence를 조회

HDD Generator가 Neptune 그래프 데이터를 활용하여 문서 생성 시
signal path, hierarchy tree, instance parameters 등의 evidence를 주입할 수 있도록 한다.

Fallback: Neptune 미접속 시 graceful degradation (claim-only 모드로 동작)

Requirements: 13.2, 13.3
"""
import json
import logging
import os
import urllib.request
import urllib.error

import boto3
import botocore.auth
import botocore.awsrequest

logger = logging.getLogger("graph_evidence_provider")


# ---------------------------------------------------------------------------
# Neptune SigV4 Client (reused pattern from neptune_ingestion.py)
# ---------------------------------------------------------------------------
class _NeptuneSigV4Client:
    """Neptune HTTPS client with IAM SigV4 authentication.

    Lightweight client for openCypher queries against Neptune.
    Uses botocore.auth.SigV4Auth + AWSRequest for request signing.
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
# RAG API Client (for trace-signal-path, find-instantiation-tree)
# ---------------------------------------------------------------------------
class _RagApiClient:
    """Client for calling RAG API Gateway endpoints (Private REST API).

    Uses SigV4 signing for API Gateway (execute-api service).
    """

    def __init__(self, api_url: str, region: str = None):
        self.api_url = api_url.rstrip("/")

        session = boto3.Session()
        self.credentials = session.get_credentials().get_frozen_credentials()
        self.region = region or session.region_name or "ap-northeast-2"

    def _sign_request(self, method: str, url: str, body: str = None):
        """Sign an HTTP request using SigV4 for execute-api service."""
        headers = {}
        if body:
            headers["Content-Type"] = "application/json"

        aws_request = botocore.awsrequest.AWSRequest(
            method=method,
            url=url,
            data=body,
            headers=headers,
        )

        signer = botocore.auth.SigV4Auth(self.credentials, "execute-api", self.region)
        signer.add_auth(aws_request)

        return aws_request

    def post(self, path: str, payload: dict) -> dict:
        """Send a signed POST request to the RAG API.

        Args:
            path: API path (e.g., '/rag/trace-signal-path')
            payload: Request body dict

        Returns:
            Parsed JSON response

        Raises:
            urllib.error.URLError: On network errors
            urllib.error.HTTPError: On HTTP error responses
        """
        url = f"{self.api_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        signed_request = self._sign_request("POST", url, body.decode("utf-8"))

        req = urllib.request.Request(url, data=body, method="POST")
        for key, value in signed_request.headers.items():
            req.add_header(key, value)

        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# GraphEvidenceProvider
# ---------------------------------------------------------------------------
class GraphEvidenceProvider:
    """Neptune Graph DB에서 HDD 섹션별 evidence를 조회하여 hdd_generator에 주입.

    Neptune 미접속 시 graceful degradation: 모든 메서드가 빈 dict/list를 반환하며
    기존 claim-only 모드로 동작한다.

    Usage:
        provider = GraphEvidenceProvider()
        evidence = provider.get_section_evidence("NoC", "trinity_top")
        path = provider.get_connectivity_path("flit_out_req[1][4]", "flit_in_req[2][4]")
        tree = provider.get_hierarchy_tree("trinity_top", depth=3)
        params = provider.get_instance_params("trinity_top/gen_noc/u_repeater_stage_0")
    """

    def __init__(
        self,
        neptune_endpoint: str = None,
        rag_api_url: str = None,
        region: str = None,
    ):
        """Initialize GraphEvidenceProvider.

        Args:
            neptune_endpoint: Neptune cluster endpoint (default: env NEPTUNE_ENDPOINT)
            rag_api_url: RAG API Gateway URL (default: env RAG_API_URL)
            region: AWS region (default: session region or ap-northeast-2)
        """
        self._neptune_endpoint = neptune_endpoint or os.environ.get("NEPTUNE_ENDPOINT", "")
        self._rag_api_url = rag_api_url or os.environ.get("RAG_API_URL", "")
        self._region = region

        self._neptune_client: _NeptuneSigV4Client | None = None
        self._api_client: _RagApiClient | None = None
        self._neptune_available: bool | None = None  # None = not yet checked

    @property
    def neptune_available(self) -> bool:
        """Check if Neptune is reachable (cached after first check).

        Returns:
            True if Neptune endpoint is configured and reachable, False otherwise.
        """
        if self._neptune_available is not None:
            return self._neptune_available

        if not self._neptune_endpoint:
            logger.info("Neptune endpoint not configured — operating in claim-only mode")
            self._neptune_available = False
            return False

        try:
            client = self._get_neptune_client()
            self._neptune_available = client.health_check()
        except Exception as e:
            logger.warning(f"Neptune health check failed: {e} — operating in claim-only mode")
            self._neptune_available = False

        if not self._neptune_available:
            logger.info("Neptune unreachable — operating in claim-only mode")

        return self._neptune_available

    def _get_neptune_client(self) -> _NeptuneSigV4Client:
        """Get or create the Neptune SigV4 client."""
        if self._neptune_client is None:
            self._neptune_client = _NeptuneSigV4Client(
                endpoint=self._neptune_endpoint,
                region=self._region,
            )
        return self._neptune_client

    def _get_api_client(self) -> _RagApiClient | None:
        """Get or create the RAG API client. Returns None if URL not configured."""
        if self._api_client is None:
            if not self._rag_api_url:
                return None
            self._api_client = _RagApiClient(
                api_url=self._rag_api_url,
                region=self._region,
            )
        return self._api_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_section_evidence(self, topic: str, module_name: str) -> dict:
        """HDD 섹션 생성 시 Neptune에서 관련 graph evidence를 조회.

        topic에 따라 적절한 openCypher 쿼리를 실행하여 해당 섹션에 필요한
        노드/엣지 정보를 반환한다.

        Args:
            topic: HDD 섹션 토픽 (e.g., "NoC", "EDC", "Overlay", "DFX")
            module_name: 대상 모듈 이름

        Returns:
            Evidence dict with keys: 'nodes', 'edges', 'summary'.
            Neptune 미접속 시 빈 dict 반환.
        """
        if not self.neptune_available:
            return {}

        try:
            client = self._get_neptune_client()

            # Query instances and port bindings related to the topic/module
            query = (
                "MATCH (m:ModuleDef {name: $module_name})"
                "-[:INSTANCE_OF|INSTANTIATES*0..2]-(inst:Instance) "
                "OPTIONAL MATCH (inst)-[:HAS_PORT]->(p:PortInstance)"
                "-[:BINDS_TO]->(s:Signal) "
                "RETURN m.name AS module, "
                "collect(DISTINCT inst.instance_name) AS instances, "
                "collect(DISTINCT {port: p.name, signal: s.name, "
                "direction: p.direction}) AS bindings "
                "LIMIT 50"
            )
            result = client.execute_query(query, {"module_name": module_name})

            nodes = []
            edges = []
            summary = ""

            results_data = result.get("results", [])
            for row in results_data:
                instances = row.get("instances", [])
                bindings = row.get("bindings", [])

                for inst_name in instances:
                    if inst_name:
                        nodes.append({"name": inst_name, "type": "Instance"})

                for binding in bindings:
                    if isinstance(binding, dict) and binding.get("port"):
                        edges.append({
                            "from": binding.get("port", ""),
                            "to": binding.get("signal", ""),
                            "type": "BINDS_TO",
                            "direction": binding.get("direction", ""),
                        })

            if nodes:
                summary = (
                    f"Module '{module_name}' has {len(nodes)} instances "
                    f"with {len(edges)} port bindings (topic: {topic})"
                )

            return {"nodes": nodes, "edges": edges, "summary": summary}

        except Exception as e:
            logger.warning(
                f"get_section_evidence failed for topic='{topic}', "
                f"module='{module_name}': {e}"
            )
            return {}

    def get_connectivity_path(self, from_port: str, to_port: str) -> list:
        """trace_signal_path API를 호출하여 signal propagation path 반환.

        from_port에서 to_port까지의 신호 전파 경로를 추적한다.
        RAG API가 설정되어 있으면 API를 호출하고, 그렇지 않으면
        Neptune에 직접 쿼리한다.

        Args:
            from_port: 시작 포트 (e.g., "flit_out_req[1][4]")
            to_port: 도착 포트 (e.g., "flit_in_req[2][4]")

        Returns:
            List of path dicts, each with 'nodes' and 'edges' keys.
            Neptune 미접속 시 빈 list 반환.
        """
        if not self.neptune_available:
            return []

        # Try RAG API first (if configured)
        api_client = self._get_api_client()
        if api_client:
            try:
                resp = api_client.post("/rag/trace-signal-path", {
                    "module_name": "",  # Search across all modules
                    "signal_name": from_port,
                })
                paths = resp.get("signal_path", [])
                if paths:
                    return paths
            except Exception as e:
                logger.debug(
                    f"RAG API trace-signal-path failed, falling back to Neptune: {e}"
                )

        # Fallback: direct Neptune query
        try:
            client = self._get_neptune_client()
            query = (
                "MATCH path = (src:PortInstance)-[:BINDS_TO|DRIVES|READS*1..6]"
                "->(dst:PortInstance) "
                "WHERE src.name CONTAINS $from_port "
                "AND dst.name CONTAINS $to_port "
                "RETURN [n IN nodes(path) | "
                "{name: n.name, type: labels(n)[0]}] AS path_nodes, "
                "[r IN relationships(path) | type(r)] AS path_edges "
                "LIMIT 10"
            )
            result = client.execute_query(query, {
                "from_port": from_port,
                "to_port": to_port,
            })

            paths = []
            for row in result.get("results", []):
                paths.append({
                    "nodes": row.get("path_nodes", []),
                    "edges": row.get("path_edges", []),
                })
            return paths

        except Exception as e:
            logger.warning(
                f"get_connectivity_path failed from='{from_port}' "
                f"to='{to_port}': {e}"
            )
            return []

    def get_hierarchy_tree(self, module_name: str, depth: int = 3) -> dict:
        """find-instantiation-tree API를 호출하여 hierarchy 반환.

        모듈의 인스턴스화 트리를 depth 레벨까지 조회한다.

        Args:
            module_name: 대상 모듈 이름
            depth: 탐색 깊이 (default: 3, max: 10)

        Returns:
            Hierarchy dict with keys: 'root', 'children', 'depth'.
            Neptune 미접속 시 빈 dict 반환.
        """
        if not self.neptune_available:
            return {}

        depth = max(1, min(depth, 10))

        # Try RAG API first (if configured)
        api_client = self._get_api_client()
        if api_client:
            try:
                resp = api_client.post("/rag/find-instantiation-tree", {
                    "module_name": module_name,
                    "depth": depth,
                })
                tree_data = resp.get("instantiation_tree", [])
                if tree_data:
                    return {
                        "root": module_name,
                        "children": tree_data,
                        "depth": depth,
                    }
            except Exception as e:
                logger.debug(
                    f"RAG API find-instantiation-tree failed, "
                    f"falling back to Neptune: {e}"
                )

        # Fallback: direct Neptune query
        try:
            client = self._get_neptune_client()
            query = (
                "MATCH path = (root:ModuleDef {name: $module})"
                "-[:INSTANTIATES*1.." + str(depth) + "]->(child) "
                "RETURN root.name AS root, "
                "[n IN nodes(path) | n.name] AS hierarchy, "
                "length(path) AS depth "
                "ORDER BY depth "
                "LIMIT 50"
            )
            result = client.execute_query(query, {"module": module_name})

            children = []
            for row in result.get("results", []):
                children.append({
                    "root": row.get("root", ""),
                    "hierarchy": row.get("hierarchy", []),
                    "depth": row.get("depth", 0),
                })

            return {
                "root": module_name,
                "children": children,
                "depth": depth,
            }

        except Exception as e:
            logger.warning(
                f"get_hierarchy_tree failed for module='{module_name}': {e}"
            )
            return {}

    def get_instance_params(self, instance_hier_path: str) -> dict:
        """특정 instance의 parameter override 값 조회.

        Neptune에서 Instance 노드의 param_overrides property를 조회한다.

        Args:
            instance_hier_path: Instance 계층 경로
                (e.g., "trinity_top/gen_noc/u_repeater_stage_0")

        Returns:
            Dict of parameter overrides (e.g., {"NUM_REPEATERS": "4"}).
            Neptune 미접속 시 빈 dict 반환.
        """
        if not self.neptune_available:
            return {}

        try:
            client = self._get_neptune_client()
            query = (
                "MATCH (inst:Instance {hier_path: $hier_path}) "
                "RETURN inst.instance_name AS instance_name, "
                "inst.param_overrides AS param_overrides "
                "LIMIT 1"
            )
            result = client.execute_query(query, {"hier_path": instance_hier_path})

            results_data = result.get("results", [])
            if not results_data:
                return {}

            row = results_data[0]
            param_overrides = row.get("param_overrides", "")

            # param_overrides is stored as JSON string in Neptune
            if isinstance(param_overrides, str) and param_overrides:
                try:
                    return json.loads(param_overrides)
                except (json.JSONDecodeError, TypeError):
                    return {}
            elif isinstance(param_overrides, dict):
                return param_overrides

            return {}

        except Exception as e:
            logger.warning(
                f"get_instance_params failed for path='{instance_hier_path}': {e}"
            )
            return {}

    # ------------------------------------------------------------------
    # Evidence formatting for HDD prompt injection
    # ------------------------------------------------------------------

    def format_evidence_for_prompt(self, topic: str, module_name: str) -> str:
        """Format graph evidence as a text block for HDD prompt injection.

        Combines section evidence, hierarchy, and instance params into a
        human-readable evidence table suitable for LLM prompt injection.

        Args:
            topic: HDD 섹션 토픽
            module_name: 대상 모듈 이름

        Returns:
            Formatted evidence string, or empty string if no evidence available.
        """
        if not self.neptune_available:
            return ""

        parts = []

        # Section evidence
        evidence = self.get_section_evidence(topic, module_name)
        if evidence and evidence.get("summary"):
            parts.append(f"- Summary: {evidence['summary']}")

            # Include top bindings
            edges = evidence.get("edges", [])
            for edge in edges[:10]:  # Limit to 10 bindings
                if edge.get("from") and edge.get("to"):
                    direction = edge.get("direction", "")
                    parts.append(
                        f"  - {edge['from']} -> {edge['to']} ({direction})"
                    )

        # Hierarchy tree
        tree = self.get_hierarchy_tree(module_name, depth=2)
        if tree and tree.get("children"):
            children = tree["children"]
            hierarchy_strs = []
            for child in children[:10]:  # Limit
                hier = child.get("hierarchy", [])
                if hier:
                    hierarchy_strs.append(" / ".join(hier))
            if hierarchy_strs:
                parts.append(f"- Hierarchy ({len(hierarchy_strs)} paths):")
                for h in hierarchy_strs[:5]:
                    parts.append(f"  - {h}")

        if not parts:
            return ""

        header = f"[GRAPH EVIDENCE — {topic} Section]"
        return header + "\n" + "\n".join(parts)

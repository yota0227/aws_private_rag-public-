"""
Search query builder for RTL auto-analysis pipeline.

Builds OpenSearch bool queries from structured search parameters,
excluding empty/None parameters automatically.

Requirements validated: 8.3
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Mapping from parameter names to OpenSearch field names.
_PARAM_FIELD_MAP: dict[str, str] = {
    "topic": "topic",
    "clock_domain": "clock_domains.domain",
    "hierarchy_path": "hierarchy_path",
    "pipeline_id": "pipeline_id",
    "analysis_type": "analysis_type",
}


def build_search_query(params: dict[str, Any]) -> dict[str, Any]:
    """Build an OpenSearch bool query from search parameters.

    Constructs a ``bool`` query with ``must`` term clauses for each
    non-empty parameter.  Empty strings, None values, and unknown
    parameter names are silently excluded.

    Supported parameters:
        - ``topic``
        - ``clock_domain``
        - ``hierarchy_path``
        - ``pipeline_id``
        - ``analysis_type``

    Args:
        params: Dictionary of search parameter name-value pairs.

    Returns:
        OpenSearch query dict in the form::

            {"query": {"bool": {"must": [{"term": {field: value}}, ...]}}}

        Returns ``{"query": {"bool": {"must": [{"match_all": {}}]}}}``
        when no valid parameters are provided.
    """
    if not params or not isinstance(params, dict):
        return {"query": {"bool": {"must": [{"match_all": {}}]}}}

    must_clauses: list[dict[str, Any]] = []

    for param_name, field_name in _PARAM_FIELD_MAP.items():
        value = params.get(param_name)
        if value is not None and isinstance(value, str) and value.strip():
            must_clauses.append({"term": {field_name: value.strip()}})

    if not must_clauses:
        return {"query": {"bool": {"must": [{"match_all": {}}]}}}

    return {"query": {"bool": {"must": must_clauses}}}

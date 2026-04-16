"""
Clock domain analysis for RTL auto-analysis pipeline.

Extracts clock domains from RTL source code by matching
``always_ff @(posedge <clock>)`` and ``always @(posedge <clock>)``
patterns, classifies clock signals into domain groups, and detects
CDC (Clock Domain Crossing) boundaries.

Requirements validated: 3.1, 3.2, 3.3, 3.5
"""

import logging
import re
from itertools import combinations
from typing import Any

logger = logging.getLogger(__name__)

# Regex to match always_ff @(posedge <clock>) and always @(posedge <clock>)
# Captures the clock signal name from the posedge sensitivity list.
_ALWAYS_POSEDGE_RE = re.compile(
    r"\balways(?:_ff)?\s*@\s*\(\s*posedge\s+(\w+)",
    re.IGNORECASE,
)

# Domain classification rules.  The match is case-insensitive and
# looks for the keyword anywhere in the signal name.
_DOMAIN_RULES: list[tuple[str, re.Pattern]] = [
    ("ai_clock_domain",  re.compile(r"ai[_]?clk", re.IGNORECASE)),
    ("noc_clock_domain", re.compile(r"noc[_]?clk", re.IGNORECASE)),
    ("dm_clock_domain",  re.compile(r"dm[_]?clk", re.IGNORECASE)),
    ("ref_clock_domain", re.compile(r"ref[_]?clk", re.IGNORECASE)),
]


def extract_clock_domains(rtl_content: str) -> list[str]:
    """Extract unique clock signal names from RTL source content.

    Scans *rtl_content* for ``always_ff @(posedge <clock>)`` and
    ``always @(posedge <clock>)`` patterns and returns a deduplicated,
    sorted list of clock signal names found.

    Args:
        rtl_content: Raw RTL (Verilog/SystemVerilog) source text.

    Returns:
        Sorted list of unique clock signal names.  Returns an empty
        list when no clock patterns are found or the input is empty.
    """
    if not rtl_content or not isinstance(rtl_content, str):
        return []

    signals: set[str] = set()
    for match in _ALWAYS_POSEDGE_RE.finditer(rtl_content):
        signals.add(match.group(1))

    return sorted(signals)


def classify_clock_domain(signal_name: str) -> str:
    """Classify a clock signal into a domain group.

    Classification rules (checked in order):
        - ``ai_clock_domain``:  signal contains ``ai_clk`` or ``aiclk``
        - ``noc_clock_domain``: signal contains ``noc_clk`` or ``nocclk``
        - ``dm_clock_domain``:  signal contains ``dm_clk`` or ``dmclk``
        - ``ref_clock_domain``: signal contains ``ref_clk`` or ``refclk``
        - ``unclassified_clock``: none of the above patterns match

    When a signal matches ``unclassified_clock``, a warning is logged
    per Requirement 3.5.

    Args:
        signal_name: Clock signal name extracted from RTL source.

    Returns:
        Domain group string.
    """
    if not signal_name or not isinstance(signal_name, str):
        return "unclassified_clock"

    for domain, pattern in _DOMAIN_RULES:
        if pattern.search(signal_name):
            return domain

    logger.warning(
        "Clock signal '%s' does not match any standard pattern. "
        "Classified as unclassified_clock.",
        signal_name,
    )
    return "unclassified_clock"


def detect_cdc_boundary(
    clock_domains: list[dict[str, Any]],
) -> dict[str, Any]:
    """Detect CDC (Clock Domain Crossing) boundaries.

    A CDC boundary exists when a module uses signals from two or more
    *distinct* clock domain groups.

    Args:
        clock_domains: List of dicts, each with at least a ``domain``
            key (str).  Example::

                [
                    {"domain": "noc_clock_domain", "signals": ["i_noc_clk"]},
                    {"domain": "ai_clock_domain",  "signals": ["i_ai_clk"]},
                ]

    Returns:
        A dict with:
            - ``is_cdc_boundary`` (bool): True when >= 2 distinct domains.
            - ``cdc_pairs`` (list[list[str]]): Sorted pairs of crossing
              domains.  Empty when ``is_cdc_boundary`` is False.
    """
    if not clock_domains or not isinstance(clock_domains, list):
        return {"is_cdc_boundary": False, "cdc_pairs": []}

    unique_domains: set[str] = set()
    for entry in clock_domains:
        domain = entry.get("domain", "") if isinstance(entry, dict) else ""
        if domain:
            unique_domains.add(domain)

    if len(unique_domains) < 2:
        return {"is_cdc_boundary": False, "cdc_pairs": []}

    # Generate all unique pairs, sorted for deterministic output.
    cdc_pairs = sorted(
        [sorted(pair) for pair in combinations(unique_domains, 2)]
    )

    return {"is_cdc_boundary": True, "cdc_pairs": cdc_pairs}

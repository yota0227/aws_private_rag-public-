"""Always Block Parser for SystemVerilog always_ff clock domain extraction.

Extracts clock domain information from always_ff block sensitivity lists
and converts them to structured claims for RAG indexing.

v9 Phase 7 — addresses the gap where module_parse captures module
declarations but misses clock domain information such as which clocks
drive which registers, and potential clock domain crossings (CDC).

Recognized clock domain mappings:
  - i_ai_clk  → AI
  - i_noc_clk → NoC
  - i_dm_clk  → DM
  - other *_clk patterns → derive domain from signal name

always_comb blocks are excluded — they have no clock domain.

Reset signals (posedge reset, negedge reset_n) are extracted from
the sensitivity list and included in claims.
"""

import re
import hashlib
import logging
from itertools import combinations

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Well-known clock signal → domain mappings
# ---------------------------------------------------------------------------

_KNOWN_CLOCK_DOMAINS = {
    "i_ai_clk": "AI",
    "i_noc_clk": "NoC",
    "i_dm_clk": "DM",
}


def _make_claim(claim_text, claim_type, module_name, topic,
                file_path, pipeline_id, parser_source=""):
    """Create a claim dict in the standard format for OpenSearch indexing."""
    claim_id = hashlib.sha256(
        f"{pipeline_id}:{file_path}:{claim_text[:100]}".encode()
    ).hexdigest()[:16]
    claim = {
        "analysis_type": "claim",
        "claim_id": claim_id,
        "claim_type": claim_type,
        "claim_text": claim_text,
        "module_name": module_name,
        "topic": topic,
        "pipeline_id": pipeline_id,
        "file_path": file_path,
        "confidence_score": 1.0,
        "source_files": [file_path],
    }
    if parser_source:
        claim["parser_source"] = parser_source
    return claim


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_clock_domains(rtl_content, module_name="", file_path="",
                          pipeline_id=""):
    """Extract clock domain information from always_ff blocks.

    Scans RTL content for always_ff blocks, extracts clock and reset
    signals from sensitivity lists, maps clock signals to domain names,
    and produces structured claims including CDC warnings when multiple
    domains are detected.

    Args:
        rtl_content: Raw RTL source code string.
        module_name: Name of the module being parsed.
        file_path: Source file path for claim metadata.
        pipeline_id: Pipeline identifier for claim metadata.

    Returns:
        List of claim dicts ready for OpenSearch indexing.
    """
    claims = []

    # Strip comments for reliable pattern matching
    clean = _strip_comments(rtl_content)

    # Extract module name from content if not provided
    if not module_name:
        mod_match = re.search(r"\bmodule\s+(\w+)\s*(?:#\s*\(|[\(\;])", clean)
        module_name = mod_match.group(1) if mod_match else "unknown"

    # Find all always_ff blocks and extract sensitivity list info
    ff_blocks = _find_always_ff_blocks(clean)

    if not ff_blocks:
        logger.debug(
            "No always_ff blocks found in %s (%s)", module_name, file_path,
        )
        return claims

    # Collect all clock domains and reset signals across the module
    all_domains = set()
    all_resets = set()

    for block_info in ff_blocks:
        all_domains.update(block_info["domains"])
        all_resets.update(block_info["resets"])

    if not all_domains:
        logger.debug(
            "No clock domains extracted from always_ff blocks in %s (%s)",
            module_name, file_path,
        )
        return claims

    # Generate clock domain summary claim (Req 19.3)
    domain_list = sorted(all_domains)
    summary_text = (
        f"Module '{module_name}' operates in {len(domain_list)} "
        f"clock domain{'s' if len(domain_list) != 1 else ''}: "
        f"{', '.join(domain_list)}"
    )

    if all_resets:
        reset_list = sorted(all_resets)
        summary_text += f". Reset signals: {', '.join(reset_list)}"

    claims.append(_make_claim(
        summary_text, "clock_domain", module_name,
        "ClockDomain", file_path, pipeline_id,
        parser_source="always_block_parser",
    ))

    # Generate CDC warning claims for each pair of different domains (Req 19.4)
    if len(domain_list) >= 2:
        for domain_a, domain_b in combinations(domain_list, 2):
            cdc_text = (
                f"Module '{module_name}' has potential clock domain "
                f"crossing between {domain_a} and {domain_b}"
            )
            claims.append(_make_claim(
                cdc_text, "clock_domain_crossing", module_name,
                "ClockDomain", file_path, pipeline_id,
                parser_source="always_block_parser",
            ))

    logger.info(
        "Extracted %d clock domain claims from module '%s' in %s "
        "(%d domains: %s)",
        len(claims), module_name, file_path,
        len(domain_list), ", ".join(domain_list),
    )
    return claims


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_comments(content):
    """Remove single-line and block comments from RTL content."""
    content = re.sub(r"//[^\n]*", "", content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return content


def _find_always_ff_blocks(clean_content):
    """Find always_ff blocks and extract sensitivity list information.

    Returns a list of dicts with keys:
        clocks: list of clock signal names
        domains: set of mapped domain names
        resets: set of reset signal names
        edge_info: list of (edge, signal) tuples
    """
    blocks = []

    # Match always_ff @(sensitivity_list)
    # The sensitivity list can contain posedge/negedge signals separated
    # by 'or' or ','
    pattern = re.compile(
        r"\balways_ff\s+@\s*\(([^)]+)\)",
        re.DOTALL,
    )

    for m in pattern.finditer(clean_content):
        sens_list = m.group(1).strip()
        block_info = _parse_sensitivity_list(sens_list)
        blocks.append(block_info)

    return blocks


def _parse_sensitivity_list(sens_list):
    """Parse a sensitivity list string into clock domains and reset signals.

    Handles formats like:
        posedge i_ai_clk
        posedge i_ai_clk or negedge i_ai_reset_n
        posedge clk, negedge rst_n

    Args:
        sens_list: The content between @( and ) in always_ff.

    Returns:
        Dict with keys: clocks, domains, resets, edge_info.
    """
    clocks = []
    domains = set()
    resets = set()
    edge_info = []

    # Split by 'or' or ',' to get individual edge-signal pairs
    # Normalize: replace commas with 'or' for uniform splitting
    normalized = sens_list.replace(",", " or ")
    parts = re.split(r"\bor\b", normalized)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Match posedge/negedge signal_name
        edge_match = re.match(
            r"(posedge|negedge)\s+(\w+)", part,
        )
        if not edge_match:
            continue

        edge = edge_match.group(1)
        signal = edge_match.group(2)
        edge_info.append((edge, signal))

        # Classify as clock or reset
        if _is_reset_signal(signal):
            resets.add(signal)
        elif _is_clock_signal(signal):
            clocks.append(signal)
            domain = _map_clock_to_domain(signal)
            domains.add(domain)

    return {
        "clocks": clocks,
        "domains": domains,
        "resets": resets,
        "edge_info": edge_info,
    }


def _is_clock_signal(signal):
    """Determine if a signal name is a clock signal.

    Clock signals typically contain 'clk' in their name.
    """
    return "clk" in signal.lower()


def _is_reset_signal(signal):
    """Determine if a signal name is a reset signal.

    Reset signals typically contain 'reset' or 'rst' in their name.
    """
    lower = signal.lower()
    return "reset" in lower or "rst" in lower


def _map_clock_to_domain(clock_signal):
    """Map a clock signal name to a domain name.

    Uses well-known mappings first, then derives domain from signal name.

    Mapping rules (Req 19.2):
        i_ai_clk  → AI
        i_noc_clk → NoC
        i_dm_clk  → DM
        other *_clk → derive from signal name

    For unknown signals, strips common prefixes (i_, o_) and the _clk
    suffix to derive the domain name.

    Examples:
        ref_clk     → ref
        sys_clk     → sys
        i_pcie_clk  → pcie
        clk         → clk
    """
    # Check well-known mappings first
    if clock_signal in _KNOWN_CLOCK_DOMAINS:
        return _KNOWN_CLOCK_DOMAINS[clock_signal]

    # Derive domain from signal name
    name = clock_signal

    # Strip common input/output prefixes
    if name.startswith("i_") or name.startswith("o_"):
        name = name[2:]

    # Strip _clk suffix
    if name.endswith("_clk"):
        name = name[:-4]

    # If nothing left after stripping, use the original signal name
    if not name:
        return clock_signal

    return name

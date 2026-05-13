"""Port classifier for top-level modules.

Categorizes ports into functional groups and generates per-category claims.
v7 — addresses "Lost in the Middle" attention problem.
"""

import re
import hashlib
import logging

logger = logging.getLogger(__name__)

PORT_CATEGORIES = [
    ("PRTN_Power", [r"PRTNUN_", r"ISO_EN", r"TIEL_DFT", r"power_good"]),
    ("EDC_APB", [r"edc_apb_", r"edc_.*irq", r"edc_reset", r"i_edc_", r"o_edc_"]),
    ("AXI_Interface", [r"npu_out_", r"npu_in_", r"axi_", r"i_axi_clk"]),
    ("APB_Register", [r"i_reg_", r"o_reg_", r"reg_psel", r"reg_paddr"]),
    ("DM_Clock_Reset", [r"i_dm_clk", r"i_dm_core_reset", r"i_dm_uncore_reset"]),
    ("AI_Clock_Reset", [r"i_ai_clk", r"i_ai_reset"]),
    ("NoC_Clock_Reset", [r"i_noc_clk", r"i_noc_reset"]),
    ("Tensix_Reset", [r"i_tensix_reset"]),
    ("SFR_Memory_Config", [r"SFR_", r"sfr_"]),
]


def classify_ports(port_list, module_name="", file_path="", pipeline_id=""):
    """Classify ports into categories and generate claims."""
    if not port_list or len(port_list) < 10:
        return []

    categorized = {}
    uncategorized = []

    for port in port_list:
        matched = False
        for cat_name, patterns in PORT_CATEGORIES:
            for pattern in patterns:
                if re.search(pattern, port, re.IGNORECASE):
                    categorized.setdefault(cat_name, []).append(port)
                    matched = True
                    break
            if matched:
                break
        if not matched:
            uncategorized.append(port)

    claims = []
    for cat_name, ports in categorized.items():
        claims.append(_make_port_claim(
            f"Module '{module_name}' has {len(ports)} {cat_name} ports: {', '.join(ports)}",
            cat_name, module_name, file_path, pipeline_id
        ))

    cat_summary = ", ".join(f"{c}({len(p)})" for c, p in categorized.items())
    if uncategorized:
        cat_summary += f", Other({len(uncategorized)})"
    claims.append(_make_port_claim(
        f"Module '{module_name}' has {len(port_list)} total ports: {cat_summary}",
        "PortSummary", module_name, file_path, pipeline_id
    ))

    return claims


def _make_port_claim(claim_text, category, module_name, file_path, pipeline_id):
    claim_id = hashlib.sha256(
        f"{pipeline_id}:{file_path}:port:{category}:{claim_text[:80]}".encode()
    ).hexdigest()[:16]
    return {
        "analysis_type": "claim",
        "claim_id": claim_id,
        "claim_type": "structural",
        "claim_text": claim_text,
        "module_name": module_name,
        "topic": "TopLevelPorts",
        "pipeline_id": pipeline_id,
        "file_path": file_path,
        "confidence_score": 1.0,
        "source_files": [file_path],
    }

"""Signal path graph extraction for RTL RAG.

This module builds evidence-oriented edges from RTL source.  It is intended as
the v9.5 bridge between low-level parser facts and grounded architecture
writing: instead of only listing code facts, it preserves signal relationships
that can be traversed later.

Edge types:
  - PORT_CONNECTS_TO: instance.port is bound to a signal expression
  - ASSIGNS_TO: RHS expression drives/assigns LHS expression
  - DECLARES_SIGNAL: module declares a signal or typed interconnect array
"""
import argparse
import hashlib
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from port_binding_parser import _find_all_port_bindings
    from port_binding_parser import _strip_comments as _strip_port_comments
except ImportError:  # pragma: no cover - defensive for package imports
    _find_all_port_bindings = None
    _strip_port_comments = None


CATEGORY_PATTERNS = (
    ("clock", ("clock_routing", "clk", "clock")),
    ("dispatch", ("de_to_t6", "t6_to_de", "dispatch", "tensix")),
    ("edc", ("edc_", "_edc", "edc")),
    ("noc", ("noc_", "_noc", "flit", "router")),
    ("dfx", ("dfx", "ijtag", "bist", "mbist", "scan")),
    ("axi", ("axi_", "_axi", "awvalid", "arvalid", "wvalid", "rvalid")),
    ("apb", ("apb_", "_apb", "paddr", "psel", "penable")),
    ("sfr", ("sfr_rf_2p", "sfr_ra1", "sfr_rf1", "sfr_")),
    ("prtn", ("prtnun_", "iso_en", "tiel_dft", "prtn")),
)

WIRE_DECLARATION_PATTERNS = (
    re.compile(
        r"\b(wire|logic|reg)\s+"
        r"((?:\w+::)?\w+)\s+"
        r"(\w+)\s*"
        r"((?:\[[^\]]+\])*)\s*;",
        re.MULTILINE,
    ),
    re.compile(
        r"\b(logic|wire|reg)\s+"
        r"\[([^\]]+)\]\s+"
        r"(\w+)\s*"
        r"((?:\[[^\]]+\])*)\s*;",
        re.MULTILINE,
    ),
    re.compile(
        r"^[ \t]*((?:\w+::)?\w+_t)\s+"
        r"((?:\[[^\]]+\]\s*)*)"
        r"(\w+)\s*"
        r"((?:\[[^\]]+\])*)\s*;",
        re.MULTILINE,
    ),
    re.compile(
        r"^[ \t]*(wire|logic|reg)\s+"
        r"(\w+)\s*;",
        re.MULTILINE,
    ),
)

ASSIGN_PATTERN = re.compile(
    r"\bassign\s+(.+?)\s*=\s*(.+?)\s*;",
    re.DOTALL | re.MULTILINE,
)


def extract_signal_path_edges(
    rtl_content,
    module_name="",
    file_path="",
    pipeline_id="",
):
    """Extract signal path graph edges from RTL content.

    Args:
        rtl_content: Raw SystemVerilog/Verilog source.
        module_name: Optional module name. Auto-detected when omitted.
        file_path: Source file path for evidence metadata.
        pipeline_id: Pipeline identifier for deterministic edge IDs.

    Returns:
        List of edge dictionaries suitable for JSONL indexing.
    """
    if not rtl_content:
        return []

    clean = _strip_comments(rtl_content)
    module_name = module_name or _detect_module_name(clean)
    generate_contexts = _extract_generate_contexts(clean)

    edges = []
    edges.extend(_extract_port_edges(clean, module_name, file_path, pipeline_id,
                                    generate_contexts))
    edges.extend(_extract_assign_edges(clean, module_name, file_path, pipeline_id,
                                      generate_contexts))
    edges.extend(_extract_wire_declaration_edges(clean, module_name, file_path,
                                                pipeline_id, generate_contexts))
    return _dedupe_edges(edges)


def filter_edges_by_category(edges, category):
    """Return only edges classified with the requested semantic category."""
    return [edge for edge in edges if edge.get("category") == category]


def render_signal_path_markdown(edges, title="Signal Path Graph Evidence"):
    """Render extracted edges as compact Markdown for review artifacts."""
    lines = [f"# {title}", ""]
    if not edges:
        lines.append("_No signal path edges extracted._")
        return "\n".join(lines)

    grouped = {}
    for edge in edges:
        grouped.setdefault(edge.get("category", "general"), []).append(edge)

    for category in sorted(grouped):
        lines.extend([f"## {category}", ""])
        for edge in grouped[category]:
            src = edge.get("src", "")
            dst = edge.get("dst", "")
            edge_type = edge.get("edge_type", "")
            line = edge.get("line_number", 0)
            raw = edge.get("raw_text", "").replace("\n", " ").strip()
            lines.append(f"- `{edge_type}` line {line}: `{src}` -> `{dst}`")
            if raw:
                lines.append(f"  - evidence: `{raw}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_edges_jsonl(edges, output_path):
    """Write edges to a JSONL file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for edge in edges:
            handle.write(json.dumps(edge, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _extract_port_edges(clean, module_name, file_path, pipeline_id,
                        generate_contexts):
    if _find_all_port_bindings is None:
        logger.warning(
            "port_binding_parser is unavailable; PORT_CONNECTS_TO edges will "
            "not be extracted from %s",
            file_path or "<memory>",
        )
        return []

    bindings = _find_all_port_bindings(clean, file_path)
    edges = []
    for binding in bindings:
        line_number = binding.get("line_number", 0)
        instance = binding.get("instance_name", "")
        port_name = binding.get("port_name", "")
        signal_expr = binding.get("signal_expr", "")
        src = f"{instance}.{port_name}" if instance and port_name else port_name
        raw_text = f".{port_name}({signal_expr})"
        edge = _make_edge(
            edge_type="PORT_CONNECTS_TO",
            src=src,
            dst=signal_expr,
            module_name=module_name,
            file_path=file_path,
            line_number=line_number,
            raw_text=raw_text,
            pipeline_id=pipeline_id,
            parser_source="signal_path_graph.port_binding_parser",
            category=_classify_category(src, signal_expr,
                                        binding.get("module_type", "")),
            confidence_score=0.92,
            generate_context=_context_for_line(line_number, generate_contexts),
            extra={
                "instance_name": instance,
                "instance_module_type": binding.get("module_type", ""),
                "port_name": port_name,
                "signal_expr": signal_expr,
                "expression_type": binding.get("expression_type", ""),
                "bit_range": binding.get("bit_range"),
                "is_unconnected": binding.get("is_unconnected", False),
                "is_concatenation": binding.get("is_concatenation", False),
                "constituent_signals": binding.get("constituent_signals", []),
            },
        )
        edges.append(edge)
    return edges


def _extract_assign_edges(clean, module_name, file_path, pipeline_id,
                          generate_contexts):
    edges = []
    for match in ASSIGN_PATTERN.finditer(clean):
        lhs = _normalize_expr(match.group(1))
        rhs = _normalize_expr(match.group(2))
        if not lhs or not rhs:
            continue
        line_number = _char_to_line(clean, match.start())
        raw_text = _normalize_expr(match.group(0))
        edges.append(_make_edge(
            edge_type="ASSIGNS_TO",
            src=rhs,
            dst=lhs,
            module_name=module_name,
            file_path=file_path,
            line_number=line_number,
            raw_text=raw_text,
            pipeline_id=pipeline_id,
            parser_source="signal_path_graph.assign_parser",
            category=_classify_category(lhs, rhs),
            confidence_score=0.96,
            generate_context=_context_for_line(line_number, generate_contexts),
            extra={
                "lhs": lhs,
                "rhs": rhs,
                "rhs_signals": _extract_signal_tokens(rhs),
            },
        ))
    return edges


def _extract_wire_declaration_edges(clean, module_name, file_path, pipeline_id,
                                    generate_contexts):
    edges = []
    for pattern_index, pattern in enumerate(WIRE_DECLARATION_PATTERNS):
        for match in pattern.finditer(clean):
            declaration = _parse_wire_declaration_match(pattern_index, match)
            if not declaration:
                continue

            line_number = _char_to_line(clean, match.start())
            signal_name = declaration["signal_name"]
            raw_text = _normalize_expr(match.group(0))
            edges.append(_make_edge(
                edge_type="DECLARES_SIGNAL",
                src=module_name or "unknown",
                dst=signal_name,
                module_name=module_name,
                file_path=file_path,
                line_number=line_number,
                raw_text=raw_text,
                pipeline_id=pipeline_id,
                parser_source="signal_path_graph.wire_declaration_parser",
                category=_classify_category(signal_name, raw_text,
                                            declaration.get("signal_type", "")),
                confidence_score=0.9,
                generate_context=_context_for_line(line_number, generate_contexts),
                extra=declaration,
            ))
    return edges


def _parse_wire_declaration_match(pattern_index, match):
    if pattern_index == 0:
        signal_kind = match.group(1)
        signal_type = match.group(2)
        signal_name = match.group(3)
        dimensions = _parse_dimensions(match.group(4))
        return {
            "signal_kind": signal_kind,
            "signal_type": signal_type,
            "signal_name": signal_name,
            "dimensions": dimensions,
        }

    if pattern_index == 1:
        signal_kind = match.group(1)
        bit_range = match.group(2).strip()
        signal_name = match.group(3)
        dimensions = _parse_dimensions(match.group(4))
        return {
            "signal_kind": signal_kind,
            "signal_type": "packed",
            "signal_name": signal_name,
            "bit_range": bit_range,
            "dimensions": dimensions,
        }

    if pattern_index == 3:
        signal_kind = match.group(1)
        signal_name = match.group(2)
        return {
            "signal_kind": signal_kind,
            "signal_type": "scalar",
            "signal_name": signal_name,
            "dimensions": [],
        }

    signal_type = match.group(1)
    packed_dimensions = _parse_dimensions(match.group(2) or "")
    signal_name = match.group(3)
    dimensions = _parse_dimensions(match.group(4))
    return {
        "signal_kind": "implicit",
        "signal_type": signal_type,
        "signal_name": signal_name,
        "packed_dimensions": packed_dimensions,
        "dimensions": dimensions,
    }


def _make_edge(edge_type, src, dst, module_name, file_path, line_number,
               raw_text, pipeline_id, parser_source, category,
               confidence_score, generate_context, extra=None):
    edge_key = "|".join([
        pipeline_id or "",
        file_path or "",
        str(line_number or 0),
        edge_type,
        src or "",
        dst or "",
    ])
    edge = {
        "analysis_type": "signal_path_edge",
        "edge_id": hashlib.sha256(edge_key.encode("utf-8")).hexdigest()[:16],
        "edge_type": edge_type,
        "src": src,
        "dst": dst,
        "module_name": module_name or "unknown",
        "category": category,
        "file_path": file_path,
        "line_number": line_number,
        "raw_text": raw_text,
        "pipeline_id": pipeline_id,
        "parser_source": parser_source,
        "confidence_score": confidence_score,
        "generate_context": generate_context,
    }
    if extra:
        edge.update(extra)
    return edge


def _dedupe_edges(edges):
    seen = set()
    deduped = []
    for edge in edges:
        key = edge.get("edge_id")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(edge)
    return deduped


def _strip_comments(content):
    if _strip_port_comments is not None:
        return _strip_port_comments(content)
    content = re.sub(r"//[^\n]*", "", content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return content


def _detect_module_name(clean):
    match = re.search(r"\bmodule\s+(\w+)\s*(?:#\s*\(|[\(\;])", clean)
    return match.group(1) if match else "unknown"


def _parse_dimensions(dim_str):
    return [dim.strip() for dim in re.findall(r"\[([^\]]+)\]", dim_str or "")]


def _normalize_expr(expr):
    return re.sub(r"\s+", " ", (expr or "").strip())


def _classify_category(*values):
    haystack = " ".join(value or "" for value in values).lower()
    for category, patterns in CATEGORY_PATTERNS:
        if any(pattern in haystack for pattern in patterns):
            return category
    return "general"


def _extract_signal_tokens(expr):
    tokens = re.findall(r"\b[a-zA-Z_]\w*(?:::\w+)?\b", expr or "")
    keywords = {
        "if", "else", "case", "assign", "logic", "wire", "reg", "module",
        "endmodule", "begin", "end", "for", "generate", "endgenerate",
    }
    return [token for token in tokens if token.lower() not in keywords]


def _extract_generate_contexts(clean):
    contexts = []
    lines = clean.splitlines()
    active = []
    block_depth = 0

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue

        begin_count = len(re.findall(r"\bbegin\b", stripped))
        end_count = len(re.findall(r"\bend\b", stripped))

        loop = _parse_generate_for(stripped, line_number, block_depth)
        if loop:
            loop["start_line"] = line_number
            loop["depth"] = block_depth + begin_count
            active.append(loop)

        if active:
            contexts.append({
                "line_number": line_number,
                "loops": [
                    {
                        "variable": ctx.get("variable"),
                        "lower_bound": ctx.get("lower_bound"),
                        "upper_bound": ctx.get("upper_bound"),
                        "step": ctx.get("step"),
                        "label": ctx.get("label"),
                        "start_line": ctx.get("start_line"),
                    }
                    for ctx in active
                ],
            })

        block_depth += begin_count
        if end_count:
            block_depth = max(0, block_depth - end_count)
            active = [
                ctx for ctx in active
                if ctx.get("depth", 0) <= block_depth
            ]

    return contexts


def _parse_generate_for(stripped, line_number, block_depth):
    match = re.search(
        r"\bfor\s*\(\s*(?:(?:genvar|int|integer)\s+)?"
        r"(\w+)\s*=\s*([^;]+);\s*"
        r"\1\s*([<>=!]+)\s*([^;]+);\s*"
        r"([^)]+)\)",
        stripped,
    )
    if not match:
        return None

    label_match = re.search(r"\bbegin\s*:\s*(\w+)", stripped)
    return {
        "variable": match.group(1).strip(),
        "lower_bound": match.group(2).strip(),
        "comparison": match.group(3).strip(),
        "upper_bound": match.group(4).strip(),
        "step": match.group(5).strip(),
        "label": label_match.group(1) if label_match else "",
        "line_number": line_number,
        "depth": block_depth,
    }


def _context_for_line(line_number, generate_contexts):
    for context in generate_contexts:
        if context.get("line_number") == line_number:
            return context.get("loops", [])
    return []


def _char_to_line(content, pos):
    return content.count("\n", 0, pos) + 1


def _main():
    parser = argparse.ArgumentParser(description="Extract RTL signal path edges")
    parser.add_argument("--input", required=True, help="RTL source file")
    parser.add_argument("--output", help="JSONL output path")
    parser.add_argument("--markdown", help="Markdown evidence output path")
    parser.add_argument("--module-name", default="", help="Module name override")
    parser.add_argument("--pipeline-id", default="", help="Pipeline ID")
    args = parser.parse_args()

    input_path = Path(args.input)
    rtl = input_path.read_text(encoding="utf-8")
    edges = extract_signal_path_edges(
        rtl,
        module_name=args.module_name,
        file_path=str(input_path),
        pipeline_id=args.pipeline_id,
    )

    if args.output:
        write_edges_jsonl(edges, args.output)
    if args.markdown:
        markdown_path = Path(args.markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_signal_path_markdown(edges),
                                 encoding="utf-8")
    if not args.output and not args.markdown:
        for edge in edges:
            print(json.dumps(edge, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    _main()

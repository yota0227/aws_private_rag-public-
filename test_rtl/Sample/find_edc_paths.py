#!/usr/bin/env python3
"""
Parse SystemVerilog/Verilog files and find all hierarchy paths
from a top module down to any EDC-related module instantiation.

Sources are collected from:
  1. A filelist.f  (if it exists and its paths can be resolved)
  2. Auto-scan of RTL_DIRS below

Usage:
    python3 find_edc_paths.py [top_module] [edc_keyword]

Defaults:
    top_module  : trinity
    edc_keyword : edc
"""

import re
import sys
import os
from collections import defaultdict

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.dirname(SCRIPT_DIR)           # /secure_data_from_tt/20260221
TOP_MODULE  = sys.argv[1] if len(sys.argv) > 1 else "trinity"
EDC_KEYWORD = sys.argv[2] if len(sys.argv) > 2 else "edc"

# Directories to auto-scan for *.sv / *.v
RTL_DIRS = [
    os.path.join(SCRIPT_DIR),                        # rtl/
    os.path.join(BASE_DIR, "tt_rtl"),                # tt_rtl/
]


# ── Step 1: collect source files ─────────────────────────────────────────────
def collect_sources(rtl_dirs):
    sources = []
    for d in rtl_dirs:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            for f in files:
                if f.endswith(".sv") or f.endswith(".v"):
                    path = os.path.join(root, f)
                    # skip testbench / sim-only dirs
                    if any(x in path for x in ["/tb/", "/sim/", "/test/", "/chipyard/"]):
                        continue
                    sources.append(path)
    return sources


# ── Step 2: parse a single SV/V file ─────────────────────────────────────────
SV_KEYWORDS = {
    'module','endmodule','input','output','inout','logic','wire','reg',
    'assign','always','initial','begin','end','if','else','for','while',
    'case','casez','casex','endcase','generate','endgenerate','parameter',
    'localparam','function','endfunction','task','endtask','typedef',
    'struct','union','enum','interface','endinterface','modport','clocking',
    'endclocking','package','endpackage','import','export','class','endclass',
    'virtual','automatic','static','signed','unsigned','posedge','negedge',
    'or','and','not','xor','nor','nand','xnor','buf','assert','property',
    'sequence','cover','assume','restrict','unique','priority','unique0',
    'forever','repeat','disable','fork','join','return','break','continue',
    'void','bit','byte','int','integer','real','time','shortint','longint',
    'string','chandle','event','genvar','defparam','specify','endspecify',
    'primitive','endprimitive','table','endtable','pullup','pulldown',
    'supply0','supply1','tri','triand','trior','trireg','wand','wor',
    'nmos','pmos','cmos','tran','notif0','notif1','bufif0','bufif1',
    'rnmos','rpmos','rcmos','weak0','weak1','strong0','strong1',
    'highz0','highz1','small','medium','large','scalared','vectored',
    'default','packed','const','ref','var','interconnect','let','checker',
    'endchecker','rand','randc','constraint','solve','before','dist',
    'inside','with','matches','tagged','cross','bins','binsof',
    'illegal_bins','ignore_bins','program','endprogram','config','endconfig',
    'cell','design','liblist','instance','use','bind','expect','eventually',
    'until','implies','iff','throughout','within','intersect','first_match',
    'always_comb','always_ff','always_latch','type',
}

# Match:  <ModName>  [#(...)]  <instName>  (
INST_RE = re.compile(
    r'\b([a-zA-Z_]\w*)\s*'          # module type
    r'(?:#\s*\([^;]*?\)\s*)?'       # optional #( param )
    r'([a-zA-Z_]\w*)\s*\('         # instance name (
)

def strip_comments(text):
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.DOTALL)
    text = re.sub(r'//[^\n]*', '', text)
    return text

def parse_file(filepath):
    """Return ({module_name: set((child_module, inst_name), ...)}, set_of_all_defined_names)"""
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            raw = f.read()
    except OSError:
        return {}

    text = strip_comments(raw)
    result = defaultdict(set)

    # First pass: collect all module names defined in this file
    defined_here = set(re.findall(r'\bmodule\s+(\w+)', text))

    current_module = None

    for line in text.splitlines():
        stripped = line.strip()

        # Module declaration (may be on any line, just look for the keyword)
        m = re.search(r'\bmodule\s+(\w+)', stripped)
        if m and m.group(1) in defined_here:
            current_module = m.group(1)
            continue

        if re.search(r'\bendmodule\b', stripped):
            current_module = None
            continue

        if current_module is None:
            continue

        # Scan for instantiations on this line
        for m in INST_RE.finditer(stripped):
            mod_type = m.group(1)
            inst_name = m.group(2)
            if mod_type in SV_KEYWORDS or inst_name in SV_KEYWORDS:
                continue
            # Skip all-caps (macros/parameters)
            if re.match(r'^[A-Z][A-Z0-9_]+$', mod_type):
                continue
            result[current_module].add((mod_type, inst_name))

    return {k: list(v) for k, v in result.items()}, defined_here


# ── Step 3: build hierarchy graph ────────────────────────────────────────────
def build_graph(sources):
    graph = defaultdict(list)
    all_defined = set()
    total_files = len(sources)

    for i, src in enumerate(sources, 1):
        if i % 100 == 0:
            print(f"    parsing {i}/{total_files} ...", flush=True)
        parsed, file_defs = parse_file(src)
        all_defined.update(file_defs)           # all modules, including leaves
        for parent, children in parsed.items():
            for entry in children:
                if entry not in graph[parent]:
                    graph[parent].append(entry)

    return dict(graph), all_defined


# ── Step 4: DFS to find all paths through EDC modules ────────────────────────
def find_edc_paths(graph, top, keyword, defined_modules):
    """
    DFS from top. Only follow edges to modules that are actually defined
    in the source. Report paths that end at a module whose name contains
    `keyword`.
    """
    keyword = keyword.lower()
    found_paths = []

    def dfs(module, path, visited):
        is_edc = keyword in module.lower()
        if is_edc:
            found_paths.append(list(path))

        if module in visited:
            return
        visited = visited | {module}

        for child_mod, inst_name in graph.get(module, []):
            # Prune: only recurse into modules that are actually defined
            if child_mod in defined_modules:
                dfs(child_mod, path + [(child_mod, inst_name)], visited)

    dfs(top, [(top, top)], set())
    return found_paths


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print(f"[1] Collecting source files from:")
    for d in RTL_DIRS:
        print(f"    {d}")
    sources = collect_sources(RTL_DIRS)
    print(f"    {len(sources)} source files found\n")

    print(f"[2] Parsing SV/V files ...")
    graph, all_defined = build_graph(sources)
    edge_count = sum(len(v) for v in graph.values())
    print(f"    {len(all_defined)} modules defined")
    print(f"    {edge_count} instantiation edges\n")

    if TOP_MODULE not in graph and TOP_MODULE not in all_defined:
        print(f"  WARNING: top module '{TOP_MODULE}' not found in parsed files.")
        print(f"  Available modules containing 'trinity': "
              + ", ".join(m for m in all_defined if 'trinity' in m.lower()))
        return

    print(f"[3] Finding '{EDC_KEYWORD}' paths from top '{TOP_MODULE}' ...\n")
    paths = find_edc_paths(graph, TOP_MODULE, EDC_KEYWORD, all_defined)

    if not paths:
        print(f"  No paths to '{EDC_KEYWORD}' modules found.")
        # Show what EDC modules were found at all
        edc_mods = [m for m in all_defined if EDC_KEYWORD.lower() in m.lower()]
        if edc_mods:
            print(f"  EDC modules in source: {edc_mods}")
        return

    print(f"  Found {len(paths)} path(s) to '{EDC_KEYWORD}' modules:\n")
    for i, path in enumerate(paths, 1):
        print(f"  Path {i}:")
        for depth, (mod, inst) in enumerate(path):
            indent = "    " + "  " * depth
            if depth == 0:
                print(f"{indent}{mod}  (top)")
            else:
                print(f"{indent}└─ [{inst}] : {mod}")
        print()


if __name__ == "__main__":
    main()

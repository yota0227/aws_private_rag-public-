#!/usr/bin/env python3.11
"""Create EDC_HDD_V0.7.md from V0.6 — remove audience guide, update PNG refs to versioned files."""

SRC = "/secure_data_from_tt/20260221/DOC/N1B0/EDC_HDD_V0.6.md"
DST = "/secure_data_from_tt/20260221/DOC/N1B0/EDC_HDD_V0.7.md"

with open(SRC, "r") as f:
    text = f.read()

# ─────────────────────────────────────────────────────────────────
# 1. Update header
# ─────────────────────────────────────────────────────────────────
old_header = """\
**Version:** EDC1 v1.1.0 (SUPER=1, MAJOR=1, MINOR=0) — Document V0.6
**Document Status:** V0.6
**Date:** 2026-03-25

**Changes from V0.5:**
- §2.1: Full-column ring diagram rewritten — each tile now shows both Segment A and Segment B DEMUX/MUX pairs (NOC boundary: DEMUX-A + MUX-B; OVL boundary: MUX-A + DEMUX-B); bypass-A and bypass-B wires both labeled
- §11.0: Harvest bypass motivation diagram updated to show Seg B bypass path
- §11.3: Mux/Demux instance table extended with Segment B instances (DEMUX-B in overlay, MUX-B in NOC router wrap)
- §11.4 (new): Segment B bypass — instance placement and signal names
- Fig 1 updated (render_fig1_fig4_v2.py): symmetric NOC/OVL boundary boxes with DEMUX-A/MUX-B and MUX-A/DEMUX-B per tile"""

new_header = """\
**Version:** EDC1 v1.1.0 (SUPER=1, MAJOR=1, MINOR=0) — Document V0.7
**Document Status:** V0.7
**Date:** 2026-03-25

**Changes from V0.6:**
- Removed "How to Use This Document" audience guide section
- Fig 1 (v0.7): SA_RAIL moved to LEFT (Seg A ↓), SB_RAIL to RIGHT (Seg B ↑) — each rail now adjacent to its DEMUX/MUX boxes; no more long crossing arrows
- Fig 1 (v0.7): chain box Seg B arrow now DOWN (same direction as Seg A) to correctly show both segments traverse T0→T1→T3→T2 in same order
- Fig 1 (v0.7): bypass-A (↓) and bypass-B (↑) dashed wires now have arrowheads at their entry points
- Fig 1 (v0.7): BIU tile (Y=4) expanded with explicit APB4 firmware interface block showing APB4→REQ_DATA→Seg A and Seg B→RSP_DATA→APB4 paths
- PNG filenames versioned: 01_edc_ring_full_architecture_v0.7.png, 04_harvest_bypass_signal_flow_v0.7.png

**Changes from V0.5:**
- §2.1: Full-column ring diagram rewritten — each tile shows both Segment A and Segment B DEMUX/MUX pairs
- §11.3: Mux/Demux instance table extended with Segment B instances
- §11.4 (new): Segment B bypass — instance placement and signal names"""

assert old_header in text, "ERROR: header not found"
text = text.replace(old_header, new_header, 1)

# ─────────────────────────────────────────────────────────────────
# 2. Remove "How to Use This Document" section entirely
#    (from "---\n\n## How to Use This Document" through "---\n\n\n## 1. Overview")
# ─────────────────────────────────────────────────────────────────
old_howto_start = "---\n\n## How to Use This Document"
old_howto_end   = "---\n\n\n## 1. Overview"
new_section1    = "## 1. Overview"

idx_start = text.find(old_howto_start)
idx_end   = text.find(old_howto_end)
assert idx_start != -1, "ERROR: How to Use start not found"
assert idx_end   != -1, "ERROR: How to Use end not found"
text = text[:idx_start] + new_section1 + text[idx_end+len(old_howto_end):]

# ─────────────────────────────────────────────────────────────────
# 3. Update diagram file references to versioned names
# ─────────────────────────────────────────────────────────────────
text = text.replace(
    "> - `01_edc_ring_full_architecture.png` — Fig 1: Full column ring — each tile shows NOC boundary (DEMUX-A + MUX-B) and OVL boundary (MUX-A + DEMUX-B); bypass-A and bypass-B wires; U-TURN at Y=0",
    "> - `01_edc_ring_full_architecture_v0.7.png` — Fig 1 [V0.7]: Full column ring — SA_RAIL left (Seg A ↓), SB_RAIL right (Seg B ↑); NOC boundary (DEMUX-A | MUX-B); OVL boundary (MUX-A | DEMUX-B); arrowheads on bypass wires; APB4 block in BIU tile"
)
text = text.replace(
    "> - `04_harvest_bypass_signal_flow.png` — Fig 4: Harvest bypass DEMUX/MUX per segment (Seg A + Seg B)",
    "> - `04_harvest_bypass_signal_flow_v0.7.png` — Fig 4 [V0.7]: Harvest bypass — Seg A: DEMUX-A→chain/bypass-A→MUX-A; Seg B symmetric with DEMUX-B/bypass-B/MUX-B"
)

# ─────────────────────────────────────────────────────────────────
# 4. Update TOC — remove "How to Use This Document" entry if present
# ─────────────────────────────────────────────────────────────────
# The TOC doesn't have a How to Use entry, so nothing to remove there.

# ─────────────────────────────────────────────────────────────────
# Write output
# ─────────────────────────────────────────────────────────────────
with open(DST, "w") as f:
    f.write(text)

print(f"Written: {DST}")
print(f"Lines: {len(text.splitlines())}")

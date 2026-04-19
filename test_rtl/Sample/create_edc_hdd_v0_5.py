#!/usr/bin/env python3.11
"""Create EDC_HDD_V0.5.md from V0.4 with structural improvements."""

SRC = "/secure_data_from_tt/20260221/DOC/N1B0/EDC_HDD_V0.4.md"
DST = "/secure_data_from_tt/20260221/DOC/N1B0/EDC_HDD_V0.5.md"

with open(SRC, "r") as f:
    lines = f.readlines()

text = "".join(lines)

# ─────────────────────────────────────────────────────────────────
# 1. Update header block: version, date, change summary
# ─────────────────────────────────────────────────────────────────
old_header = """\
# Hardware Design Document: EDC1 (Error Detection & Control / Event Diagnostic Channel)

**Project:** Trinity (Tenstorrent AI SoC)
**Version:** EDC1 v1.1.0 (SUPER=1, MAJOR=1, MINOR=0) — Document V0.5
**Document Status:** V0.5 — CDC analysis corrected: §3.5.4 expanded with Samsung 5nm MTBF calculation and effective toggle rate derivation; §14.1 corrected (CDC safety basis is low toggle rate, not single-bit encoding); §14.2 corrected to reflect RTL audit (parameters do not exist); Appendix B.6 corrected to align with §3.5.4 (set_false_path sufficient; no sync FF or proximity constraint required for Samsung 5nm)
**Date:** 2026-03-23
**Changes from V0.3:**"""

new_header = """\
# Hardware Design Document: EDC1 (Error Detection & Control / Event Diagnostic Channel)

**Project:** Trinity (Tenstorrent AI SoC)
**Version:** EDC1 v1.1.0 (SUPER=1, MAJOR=1, MINOR=0) — Document V0.5
**Document Status:** V0.5
**Date:** 2026-03-24

**Changes from V0.4:**
- Added "How to Use This Document" section (Part I / Part II / Part III audience guide)
- Fixed section numbering: §14.5.1–14.5.3 → §15.5.1–15.5.3 (were nested under §15 but numbered as §14)
- Fixed duplicate Appendix B: renamed second Appendix B to Appendix C
- Updated Fig 8 references: split into Fig 8a (Node→BIU write) and Fig 8b (BIU→Node read)
- Updated Fig 4 reference: now shows both Segment A and Segment B DEMUX/MUX pairs
- Updated TOC to reflect above changes

**Changes from V0.3:**"""

text = text.replace(old_header, new_header, 1)

# ─────────────────────────────────────────────────────────────────
# 2. Add "How to Use This Document" after the ToC and before §1
# ─────────────────────────────────────────────────────────────────
HOW_TO_USE = """
---

## How to Use This Document

This HDD is organized in three logical parts. Choose your reading path based on your role:

---

### Part I — Protocol and SW Interface (Sections 1–7)

**Audience:** Firmware engineers, verification engineers, system architects

| Section | Content |
|---------|---------|
| §1 Overview | What EDC1 is and why it exists |
| §2 Architecture | Block diagrams; ring flow; harvest bypass overview |
| §3 Serial Bus Interface | Toggle handshake protocol; CDC constraints; async_init; MCPDLY |
| §4 Packet Format | Bit-field layout; command structs; SW send/receive guide |
| §5 Node ID Structure | 16-bit node_id encoding; complete decode tables; quick-lookup table |
| §6 Event Types & Commands | Command codes; event types; error severity classification |
| §7 SW Error Handling | Interrupt-to-identification procedure; pseudocode handler; N1B0 notes |

---

### Part II — HW Architecture and RTL (Sections 8–17)

**Audience:** RTL designers, DV engineers, P&R engineers

| Section | Content |
|---------|---------|
| §8 Module Hierarchy | Full tile hierarchy showing EDC node placement |
| §9 Module Reference | Port-level reference for each EDC RTL module |
| §10 Ring Topology | Per-column ring traversal order; segment A/B flow |
| §11 Harvest Bypass | Mux/demux placement; RTL line references; signal names |
| §12 BIU | BIU transmit/receive path; CSR register map |
| §13 Node Configuration | event_cfg_t / capture_cfg_t; pulse register |
| §14 CDC / Synchronization | Toggle CDC safety; async_init path; set_false_path rules |
| §15 Firmware Interface | APB4 access; INIT sequence; §15.5 INIT counter detail |
| §16 Inter-Cluster Connectivity | trinity.sv wiring; per-column ring diagrams |
| §17 Instance Paths | Hierarchy path formulas for all tile types |

---

### Part III — N1B0 Reference (Sections 18–19 + Appendices)

**Audience:** N1B0 chip team, post-silicon debug

| Section | Content |
|---------|---------|
| §18 EDC Full Path Nodes (N1B0) | Per-tile instance paths; composite tile chain |
| §19 EDC Nodes Decode (N1B0) | N1B0-specific node_id tables by tile type |
| Appendix A | RTL file index |
| Appendix B | Full end-to-end EDC operation example (error event to firmware) |
| Appendix C | RTL verification audit: CDC sync parameters, per-node clock assignments |

---

> **Diagram files** are in `edc_diagrams/` alongside this document.
> Key diagrams:
> - `01_edc_ring_full_architecture.png` — Fig 1: Full column ring (both segments, bypass wires)
> - `04_harvest_bypass_signal_flow.png` — Fig 4: Harvest bypass DEMUX/MUX per segment (Seg A + Seg B)
> - `07_complete_column_ring.png` — Fig 7: Complete per-column ring with all tile details
> - `08a_write_timing_node_to_biu.png` — Fig 8a: Timing — Node reports error to BIU
> - `08b_read_timing_biu_to_node.png` — Fig 8b: Timing — BIU polls node (firmware RD_CMD)
> - `11_end_to_end_path.png` — Fig 11: 7-stage end-to-end path (HW/SW separated)

---

"""

# Insert after ToC and the N1B0 adaptation note block, right before "## 1. Overview"
text = text.replace("\n## 1. Overview\n", HOW_TO_USE + "\n## 1. Overview\n", 1)

# ─────────────────────────────────────────────────────────────────
# 3. Fix §14.5.x → §15.5.x section numbering
# ─────────────────────────────────────────────────────────────────
text = text.replace("#### 14.5.1 INIT Counter", "#### 15.5.1 INIT Counter")
text = text.replace("#### 14.5.2 `async_init` Synchronization Path", "#### 15.5.2 `async_init` Synchronization Path")
text = text.replace("#### 14.5.3 Why MCPDLY = 7?", "#### 15.5.3 Why MCPDLY = 7?")

# ─────────────────────────────────────────────────────────────────
# 4. Rename second "Appendix B" → "Appendix C"
# ─────────────────────────────────────────────────────────────────
# First Appendix B (line ~3919): "## Appendix B: Full End-to-End EDC Operation Example"
# Second Appendix B (line ~4197): "## Appendix B — RTL Verification: CDC Sync Parameters..."
# We want to rename the SECOND one to Appendix C.
# Strategy: replace the second occurrence of "## Appendix B"
first = text.find("## Appendix B")
second = text.find("## Appendix B", first + 1)
if second != -1:
    tail = text[second:]
    tail = tail.replace(
        "## Appendix B — RTL Verification: CDC Sync Parameters and Per-Node Clock Assignments",
        "## Appendix C — RTL Verification: CDC Sync Parameters and Per-Node Clock Assignments",
        1
    )
    # Also fix sub-section labels B.1 → C.1, etc.
    for i in range(1, 7):
        tail = tail.replace(f"### B.{i} ", f"### C.{i} ")
    text = text[:second] + tail

# ─────────────────────────────────────────────────────────────────
# 5. Update Fig 8 references (timing diagram splits)
# ─────────────────────────────────────────────────────────────────
text = text.replace(
    "![Fig 8: Toggle handshake timing](edc_diagrams/08_timing_diagram.png)",
    "![Fig 8a: Node→BIU write timing](edc_diagrams/08a_write_timing_node_to_biu.png)\n\n![Fig 8b: BIU→Node read timing](edc_diagrams/08b_read_timing_biu_to_node.png)"
)
# Also update any text references
text = text.replace("Fig 8 — Toggle handshake timing diagram", "Fig 8a/8b — Toggle handshake timing diagrams (write / read)")

# ─────────────────────────────────────────────────────────────────
# 6. Update ToC to add "How to Use", §15.5 subsections, Appendix C
# ─────────────────────────────────────────────────────────────────
old_toc_footer = "17. [Instance Paths (Trinity)](#17-instance-paths-trinity)\n\n---"
new_toc_footer = """17. [Instance Paths (Trinity)](#17-instance-paths-trinity)
18. [EDC Full Path Nodes (N1B0)](#18-edc-full-path-nodes-n1b0)
19. [EDC Nodes Decode Address (N1B0)](#19-edc-nodes-decode-address-n1b0)

- [Appendix A: RTL File Index](#appendix-a-rtl-file-index)
- [Appendix B: Full End-to-End EDC Operation Example](#appendix-b-full-end-to-end-edc-operation-example)
- [Appendix C: RTL Verification Audit](#appendix-c--rtl-verification-cdc-sync-parameters-and-per-node-clock-assignments)

---"""
text = text.replace(old_toc_footer, new_toc_footer, 1)

# ─────────────────────────────────────────────────────────────────
# Write output
# ─────────────────────────────────────────────────────────────────
with open(DST, "w") as f:
    f.write(text)

print(f"Written: {DST}")
print(f"Lines: {len(text.splitlines())}")

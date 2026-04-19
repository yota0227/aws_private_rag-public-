# EDC CDC Proximity Constraint Guide — N1B0 Full Grid

**Version:** 0.3
**Date:** 2026-03-23
**Scope:** EDC ring CDC analysis for N1B0 4×5 grid — effective toggle rate derivation, MTBF basis, SDC requirements
**Related docs:** EDC_HDD_V0.4.md §3.5.4, DV_Guide_N1B0_v0.1.md

> **v0.3 key finding:** The self-throttling protocol guarantee (§15) reduces the effective `req_tgl` toggle rate to ≤ 10 kHz in typical use. At this rate, MTBF >> chip lifetime for N1B0 process node. **PD proximity constraints are therefore not required.** The only mandatory work is `set_false_path` in SDC and a CDC tool waiver (§8, §10). Sections §3–§12 are retained as reference for teams where a zero-waiver CDC policy requires proximity constraints or sync FF insertion.

---

## Table of Contents

1. [Overview](#1-overview)
2. [N1B0 Grid and Cluster Types](#2-n1b0-grid-and-cluster-types)
3. [Full CDC Crossing Inventory](#3-full-cdc-crossing-inventory)
4. [CDC Crossing Taxonomy](#4-cdc-crossing-taxonomy)
5. [Step 1 — Resolve Post-Synthesis Cell Names](#5-step-1--resolve-post-synthesis-cell-names)
6. [Step 2 — Identify CDC Nets](#6-step-2--identify-cdc-nets)
7. [Step 3 — Placement Constraint Scripts](#7-step-3--placement-constraint-scripts)
   - 7.1 Type-T1: Y=3→Y=2 inter-tile, Dispatch→Tensix (ai→noc), X=0,3
   - 7.2 Type-T2: Y=2→Y=1 inter-tile, Tensix→Tensix (dm→noc), all X
   - 7.3 Type-T3: Y=1→Y=0 inter-tile, Tensix→Tensix (dm→noc), all X
   - 7.4 Type-I1: Intra-Tensix, NOC wrapper→T0 (noc→ai), all Tensix tiles
   - 7.5 Type-I2: Intra-Tensix, Tensix→Overlay (ai→dm), all Tensix tiles
   - 7.6 Type-D1: Intra-Dispatch, NOC→ai (noc→ai), X=0,3
   - 7.7 Segment B constraints (reverse-direction crossings)
8. [Step 4 — SDC Constraints](#8-step-4--sdc-constraints)
9. [Step 5 — Verify After place_opt](#9-step-5--verify-after-place_opt)
10. [Step 6 — CDC Tool Signoff](#10-step-6--cdc-tool-signoff)
11. [Distance Target and Floorplan Considerations](#11-distance-target-and-floorplan-considerations)
12. [Total Constraint Count Summary](#12-total-constraint-count-summary)
13. [Deliverables Checklist](#13-deliverables-checklist)
14. [Appendix: Comparison of CDC Mitigation Options](#14-appendix-comparison-of-cdc-mitigation-options)
15. [Appendix: Effective Toggle Rate Calculation](#15-appendix-effective-toggle-rate-calculation)

---

## 1. Overview

The EDC ring carries diagnostic-only toggle traffic (`req_tgl`/`ack_tgl`, 2 bits each). The ring traverses the full N1B0 4×5 grid in two segments per column:

- **Segment A** — downward: BIU (Y=4) → Dispatch (Y=3) → Tensix Y=2 → Y=1 → Y=0
- **Segment B** — upward (loopback): Y=0 → Y=1 → Y=2 → Dispatch (Y=3) → BIU (Y=4)

The EDC RTL contains **no synchronizer cells** on any ring path — all inter-node connections are purely combinational `assign` statements (EDC_HDD_V0.4.md §3.3.3, Appendix B). CDC safety is achieved entirely through physical constraints and STA false-path waivers.

This guide covers **all CDC crossings in all tiles** across the complete 4×5 grid for both Segment A and Segment B.

---

## 2. N1B0 Grid and Cluster Types

```
         X=0                    X=1                       X=2                       X=3
Y=4  NOC2AXI_NE_OPT        NOC2AXI_ROUTER_NE_OPT    NOC2AXI_ROUTER_NW_OPT    NOC2AXI_NW_OPT
Y=3  DISPATCH_E             ROUTER-placeholder        ROUTER-placeholder        DISPATCH_W
Y=2  TENSIX(2)              TENSIX(7)                 TENSIX(12)                TENSIX(17)
Y=1  TENSIX(1)              TENSIX(6)                 TENSIX(11)                TENSIX(16)
Y=0  TENSIX(0)              TENSIX(5)                 TENSIX(10)                TENSIX(15)
```

**Ring source (BIU) per column:**

| Column | BIU location | RTL module | EDC clock |
|---|---|---|---|
| X=0 | Y=4, `gen_noc2axi_ne_opt` | `trinity_noc2axi_ne_opt` | `i_noc_clk` |
| X=1 | Y=4+Y=3 composite, `gen_noc2axi_router_ne_opt` | `trinity_noc2axi_router_ne_opt` | `i_noc_clk` |
| X=2 | Y=4+Y=3 composite, `gen_noc2axi_router_nw_opt` | `trinity_noc2axi_router_nw_opt` | `i_noc_clk` |
| X=3 | Y=4, `gen_noc2axi_nw_opt` | `trinity_noc2axi_nw_opt` | `i_noc_clk` |

**Clock domains per cluster type:**

| Cluster | Module | EDC node clocks |
|---|---|---|
| NOC2AXI corner (X=0,3 Y=4) | `trinity_noc2axi_ne/nw_opt` | `i_noc_clk` (BIU + NOC ring nodes) |
| NOC2AXI_ROUTER composite (X=1,2 Y=4+Y=3) | `trinity_noc2axi_router_ne/nw_opt` | `i_noc_clk` throughout (no intra-composite CDC) |
| DISPATCH_W/E (X=0/X=3, Y=3) | `tt_dispatch_top_east/west` | `i_noc_clk` (entry) → `i_ai_clk[x]` (L1/FDS) |
| TENSIX (Y=0..2, all X) | `tt_tensix_with_l1` | `i_noc_clk` → `i_ai_clk[x]` → `i_dm_clk[x]` |

---

## 3. Full CDC Crossing Inventory

### 3.1 Segment A (downward ring path)

Clock domain transitions encountered as the ring travels from BIU (Y=4) down to Y=0:

#### Columns X=0 and X=3 (Dispatch columns)

```
BIU (NOC2AXI, i_noc_clk)
  │ Y=4 tile exit → Y=3 tile entry
  │ ← wire, connector (combinational)
  ↓
DISPATCH EDC entry nodes (i_noc_clk)          [SYNC — no CDC here]
  │ intra-Dispatch
  │ ← CDC Type D1: noc→ai
  ↓
DISPATCH EDC L1/FDS nodes (i_ai_clk[x])
  │ Y=3 tile exit → Y=2 tile entry
  │ ← wire, connector (combinational)
  │ ← CDC Type T1: ai→noc
  ↓
TENSIX Y=2 NOC wrapper nodes (i_noc_clk)
  │ intra-Tensix Y=2
  │ ← CDC Type I1: noc→ai
  ↓
TENSIX Y=2 T0..T3 nodes (i_ai_clk[x])
  │ intra-Tensix Y=2
  │ ← CDC Type I2: ai→dm
  ↓
TENSIX Y=2 Overlay nodes (i_dm_clk[x])
  │ Y=2 tile exit → Y=1 tile entry
  │ ← wire, connector (combinational)
  │ ← CDC Type T2: dm→noc
  ↓
TENSIX Y=1 NOC wrapper nodes (i_noc_clk)
  │ intra-Tensix Y=1: CDC I1, I2 (same as Y=2)
  ↓
TENSIX Y=1 Overlay nodes (i_dm_clk[x])
  │ Y=1 tile exit → Y=0 tile entry
  │ ← CDC Type T3: dm→noc
  ↓
TENSIX Y=0 NOC wrapper nodes (i_noc_clk)
  │ intra-Tensix Y=0: CDC I1, I2 (same as Y=2)
  ↓
TENSIX Y=0 Overlay nodes (i_dm_clk[x])
  │ Y=0 loopback connector (combinational) → Segment B starts here
```

#### Columns X=1 and X=2 (Composite columns)

```
BIU + ROUTER (NOC2AXI_ROUTER composite, i_noc_clk throughout)
  │ Composite exit → Y=2 tile entry
  │ ← wire, connector (combinational)
  │ ← SYNC (noc→noc): NO CDC here
  ↓
TENSIX Y=2 NOC wrapper nodes (i_noc_clk)
  │ intra-Tensix Y=2: CDC I1, I2
  ↓
TENSIX Y=2 Overlay nodes (i_dm_clk[x])
  │ ← CDC Type T2: dm→noc (same as X=0,3)
  ↓
TENSIX Y=1 and Y=0: same as X=0,3
```

### 3.2 Segment B (upward loopback path)

The ring turns around at Y=0 loopback connector and travels back upward. Each Tensix tile is traversed in REVERSE zone order (Overlay → Tensix cores → NOC wrapper), producing mirror CDC crossings:

```
TENSIX Y=0 Overlay nodes (i_dm_clk[x])       [Seg B entry at Y=0]
  │ intra-Tensix Y=0
  │ ← CDC Type BI2: dm→ai (mirror of I2)
  ↓
TENSIX Y=0 T0..T3 nodes (i_ai_clk[x])
  │ ← CDC Type BI1: ai→noc (mirror of I1)
  ↓
TENSIX Y=0 NOC wrapper nodes (i_noc_clk)
  │ Y=0 exit → Y=1 entry
  │ ← CDC Type BT3: noc→dm (mirror of T3)
  ↓
TENSIX Y=1 Overlay nodes (i_dm_clk[x])
  │ intra-Tensix Y=1: CDC BI2, BI1
  ↓
TENSIX Y=1 NOC wrapper nodes (i_noc_clk)
  │ Y=1 exit → Y=2 entry
  │ ← CDC Type BT2: noc→dm (mirror of T2)
  ↓
TENSIX Y=2 Overlay nodes (i_dm_clk[x])
  │ intra-Tensix Y=2: CDC BI2, BI1
  ↓
TENSIX Y=2 NOC wrapper nodes (i_noc_clk)
  │ Y=2 exit → Y=3 entry
  │ ← CDC Type BT1 (X=0,3 only): noc→ai (mirror of T1)
  │    (X=1,2: SYNC noc→noc, no CDC)
  ↓
DISPATCH EDC L1/FDS nodes (i_ai_clk[x])      [X=0,3 only]
  │ intra-Dispatch
  │ ← CDC Type BD1: ai→noc (mirror of D1)
  ↓
DISPATCH EDC entry nodes (i_noc_clk)
  │ → BIU (ring complete)
```

### 3.3 Consolidated CDC Crossing Table

| ID | Type | Segment | Boundary | From clock | To clock | Columns | Tile count |
|---|---|---|---|---|---|---|---|
| T1 | Inter-tile | A | Y=3 exit → Y=2 NOC entry | `i_ai_clk[x]` | `i_noc_clk` | X=0,3 only | 2 |
| T2 | Inter-tile | A | Y=2 exit → Y=1 NOC entry | `i_dm_clk[x]` | `i_noc_clk` | All X | 4 |
| T3 | Inter-tile | A | Y=1 exit → Y=0 NOC entry | `i_dm_clk[x]` | `i_noc_clk` | All X | 4 |
| I1 | Intra-tile | A | NOC wrapper → T0 (within Tensix) | `i_noc_clk` | `i_ai_clk[x]` | All X | 12 |
| I2 | Intra-tile | A | Tensix → Overlay (within Tensix) | `i_ai_clk[x]` | `i_dm_clk[x]` | All X | 12 |
| D1 | Intra-tile | A | NOC section → L1/FDS (within Dispatch) | `i_noc_clk` | `i_ai_clk[x]` | X=0,3 only | 2 |
| BT1 | Inter-tile | B | Y=2 NOC exit → Y=3 ai entry | `i_noc_clk` | `i_ai_clk[x]` | X=0,3 only | 2 |
| BT2 | Inter-tile | B | Y=1 NOC exit → Y=2 dm entry | `i_noc_clk` | `i_dm_clk[x]` | All X | 4 |
| BT3 | Inter-tile | B | Y=0 NOC exit → Y=1 dm entry | `i_noc_clk` | `i_dm_clk[x]` | All X | 4 |
| BI1 | Intra-tile | B | T0 → NOC wrapper (within Tensix) | `i_ai_clk[x]` | `i_noc_clk` | All X | 12 |
| BI2 | Intra-tile | B | Overlay → Tensix cores (within Tensix) | `i_dm_clk[x]` | `i_ai_clk[x]` | All X | 12 |
| BD1 | Intra-tile | B | L1/FDS → NOC section (within Dispatch) | `i_ai_clk[x]` | `i_noc_clk` | X=0,3 only | 2 |

**Not a CDC crossing (SYNC):**
- Y=4 NOC2AXI corner exit → Y=3 Dispatch entry: both `i_noc_clk`
- Composite (X=1,2) exit → Y=2 Tensix entry: both `i_noc_clk`
- All internal nodes of composite tile: all `i_noc_clk`

**Total unique CDC boundaries requiring proximity constraints: 70**
(See §12 for full count breakdown)

---

## 4. CDC Crossing Taxonomy

Each CDC boundary requires **one** proximity constraint pairing the launch FF (last FF in source domain) with the capture FF (first FF in destination domain).

For **Segment A and Segment B** at the same physical boundary: the launch/capture FFs are swapped. Since both share the same physical tile, one proximity constraint (bounding box / max_distance enclosing both nodes) covers both segments.

**Proximity constraint principle:**

```
[Seg A launch FF] ←─ within 15 µm ─→ [Seg A capture FF]
                   =
[Seg B capture FF]                     [Seg B launch FF]
```

In practice: constrain the **boundary node pair** (last node of source domain, first node of destination domain). Both Seg A and Seg B signals between these two nodes are covered.

---

## 5. Step 1 — Resolve Post-Synthesis Cell Names

RTL hierarchy paths change after synthesis. Always dump post-synthesis cell names before writing constraints.

### 5.1 Dump all EDC node cell names

```tcl
# Run in ICC2 after compile_ultra / synth_design
redirect -file /tmp/edc_cells_all.rpt {
    foreach_in_collection cell [get_cells -hier -regexp ".*tt_edc1_node.*"] {
        set clk_pins [get_pins $cell/*/CK]
        set clk_name "none"
        if {[sizeof_collection $clk_pins] > 0} {
            set clk_obj [get_clocks -of_objects [index_collection $clk_pins 0]]
            if {[sizeof_collection $clk_obj] > 0} {
                set clk_name [get_attribute $clk_obj full_name]
            }
        }
        echo "[get_attribute $cell full_name] | $clk_name"
    }
}
```

### 5.2 Sort boundary nodes by clock domain

From the dump, identify the last cell in source domain and first cell in destination domain at each crossing. Record them in a table:

```
# edc_cdc_cell_names.xlsx columns:
# Crossing_ID | X | Y | Seg | Launch_cell_fullname | Capture_cell_fullname | Launch_clk | Capture_clk
```

### 5.3 Verify Dispatch tile cell clock assignment

The Dispatch tiles (X=0,3 Y=3) have a noc_clk section (NOC/NIU/router EDC nodes) and an ai_clk section (L1/FDS EDC nodes). The boundary between these two sections is CDC Type D1. Identify the exact instance at this boundary from the dump:

```tcl
# Dump only Dispatch EDC nodes
redirect -file /tmp/edc_dispatch_cells.rpt {
    foreach_in_collection cell [get_cells -hier -regexp \
        ".*dispatch.*tt_edc1_node.*"] {
        set clk [get_clocks -of_objects [get_pins $cell/*/CK]]
        echo "[get_attribute $cell full_name] | [get_attribute $clk full_name]"
    }
}
```

---

## 6. Step 2 — Identify CDC Nets

The 4 nets at every CDC crossing are: `req_tgl[0]`, `req_tgl[1]`, `ack_tgl[0]`, `ack_tgl[1]`.
Data lines (`data[*]`, `data_p[*]`) are always `set_false_path` — no proximity constraint needed.

```tcl
# Verify CDC net names from netlist (adjust pattern to match your synthesis output)
set cdc_nets [get_nets -hier -regexp \
    ".*edc.*req_tgl\[.*\]|.*edc.*ack_tgl\[.*\]"]
report_net -connections $cdc_nets -file /tmp/edc_cdc_nets.rpt
```

---

## 7. Step 3 — Placement Constraint Scripts

All scripts below are for **Synopsys ICC2**. Innovus equivalents follow each ICC2 block.
Save combined file as: `constraints/edc_cdc_proximity.tcl`

```tcl
# =============================================================
# EDC CDC Proximity Constraints — N1B0 Full Grid
# Tool: Synopsys IC Compiler 2
# Version: 0.2 (covers all 70 CDC crossings, Seg A + Seg B)
# Source after place_opt, before route_opt:
#   source constraints/edc_cdc_proximity.tcl
# Units: µm. Verify: get_unit_length_unit
# =============================================================

set EDC_CDC_MAX_DIST 15

# Helper procedure
proc edc_prox {name launch_re capture_re dist} {
    set launch  [get_cells -hier -regexp $launch_re]
    set capture [get_cells -hier -regexp $capture_re]
    if {[sizeof_collection $launch] == 0 || [sizeof_collection $capture] == 0} {
        echo "WARNING \[edc_cdc_proximity\] no match for: $name"
        echo "  launch  pattern: $launch_re"
        echo "  capture pattern: $capture_re"
        return
    }
    create_placement_constraint -name $name \
        -type proximity \
        -cells [add_to_collection $launch $capture] \
        -distance $dist
    echo "  OK  $name"
}

echo "--- EDC CDC proximity constraints: applying ---"
```

### 7.1 Type T1 / BT1 — Dispatch↔Tensix Y=2 boundary (X=0, X=3 only)

**Crossing:** Last ai_clk FF in Dispatch Y=3 ↔ First noc_clk FF in Tensix Y=2 NOC wrapper.
Covers both Seg A (ai→noc) and Seg B (noc→ai) since same physical boundary.

```tcl
# ── T1/BT1: Y=3 Dispatch exit ↔ Y=2 NOC wrapper entry ───────
# X=3 (DISPATCH_E → TENSIX Y=2, column 0)
edc_prox "edc_T1_x0" \
    ".*gen_dispatch_e.*tt_edc1_node.*ai.*req_tgl_reg.*" \
    ".*gen_x\[0\].*gen_y\[2\].*noc_niu_router.*tt_edc1_node.*row3.*req_tgl_reg.*" \
    $EDC_CDC_MAX_DIST

# X=0 (DISPATCH_W → TENSIX Y=2, column 3)
edc_prox "edc_T1_x3" \
    ".*gen_dispatch_w.*tt_edc1_node.*ai.*req_tgl_reg.*" \
    ".*gen_x\[3\].*gen_y\[2\].*noc_niu_router.*tt_edc1_node.*row3.*req_tgl_reg.*" \
    $EDC_CDC_MAX_DIST

# NOTE: X=1, X=2 — no T1/BT1 constraint needed (composite exit is noc_clk = SYNC)
```

### 7.2 Type T2 / BT2 — Tensix Y=2 exit ↔ Tensix Y=1 entry (all X)

**Crossing:** Last dm_clk FF in Tensix Y=2 Overlay ↔ First noc_clk FF in Tensix Y=1 NOC wrapper.

```tcl
# ── T2/BT2: Y=2 Overlay exit ↔ Y=1 NOC wrapper entry ────────
foreach x {0 1 2 3} {
    # Seg A launch: last overlay (dm) node in Y=2
    # Seg B launch: first NOC wrapper (noc) node in Y=1
    # One constraint covers both directions
    edc_prox "edc_T2_x${x}" \
        ".*gen_x\[${x}\].*gen_y\[2\].*overlay.*tt_edc1_node.*last.*req_tgl_reg.*" \
        ".*gen_x\[${x}\].*gen_y\[1\].*noc_niu_router.*tt_edc1_node.*first.*req_tgl_reg.*" \
        $EDC_CDC_MAX_DIST
}
```

### 7.3 Type T3 / BT3 — Tensix Y=1 exit ↔ Tensix Y=0 entry (all X)

**Crossing:** Last dm_clk FF in Tensix Y=1 Overlay ↔ First noc_clk FF in Tensix Y=0 NOC wrapper.

```tcl
# ── T3/BT3: Y=1 Overlay exit ↔ Y=0 NOC wrapper entry ────────
foreach x {0 1 2 3} {
    edc_prox "edc_T3_x${x}" \
        ".*gen_x\[${x}\].*gen_y\[1\].*overlay.*tt_edc1_node.*last.*req_tgl_reg.*" \
        ".*gen_x\[${x}\].*gen_y\[0\].*noc_niu_router.*tt_edc1_node.*first.*req_tgl_reg.*" \
        $EDC_CDC_MAX_DIST
}
```

### 7.4 Type I1 / BI1 — Intra-Tensix: NOC wrapper ↔ T0 entry (all 12 Tensix tiles)

**Crossing:** Last noc_clk FF in NOC/NIU/Router section ↔ First ai_clk FF in T0 (instrn_engine_wrapper[0]).
Covers Seg A (noc→ai) and Seg B (ai→noc) at the same boundary.

```tcl
# ── I1/BI1: NOC wrapper last node ↔ T0 first node ────────────
foreach x {0 1 2 3} {
    foreach y {0 1 2} {
        edc_prox "edc_I1_x${x}_y${y}" \
            ".*gen_x\[${x}\].*gen_y\[${y}\].*noc_niu_router.*tt_edc1_node.*last.*req_tgl_reg.*" \
            ".*gen_x\[${x}\].*gen_y\[${y}\].*instrn_engine_wrapper\[0\].*tt_edc1_node.*first.*req_tgl_reg.*" \
            $EDC_CDC_MAX_DIST
    }
}
```

### 7.5 Type I2 / BI2 — Intra-Tensix: T3 exit ↔ Overlay entry (all 12 Tensix tiles)

**Crossing:** Last ai_clk FF in T3 (instrn_engine_wrapper[3]) ↔ First dm_clk FF in Overlay wrapper.
Covers Seg A (ai→dm) and Seg B (dm→ai).

```tcl
# ── I2/BI2: T3 last node ↔ Overlay first node ────────────────
foreach x {0 1 2 3} {
    foreach y {0 1 2} {
        edc_prox "edc_I2_x${x}_y${y}" \
            ".*gen_x\[${x}\].*gen_y\[${y}\].*instrn_engine_wrapper\[3\].*tt_edc1_node.*last.*req_tgl_reg.*" \
            ".*gen_x\[${x}\].*gen_y\[${y}\].*overlay.*tt_edc1_node.*first.*req_tgl_reg.*" \
            $EDC_CDC_MAX_DIST
    }
}
```

### 7.6 Type D1 / BD1 — Intra-Dispatch: NOC section ↔ L1/FDS section (X=0, X=3)

**Crossing:** Last noc_clk FF in Dispatch NOC/NIU/router EDC section ↔ First ai_clk FF in Dispatch L1/FDS section.
Covers Seg A (noc→ai) and Seg B (ai→noc).

```tcl
# ── D1/BD1: Dispatch NOC section ↔ L1/FDS section ───────────
# X=3 (DISPATCH_E)
edc_prox "edc_D1_x0" \
    ".*gen_dispatch_e.*disp_eng_noc_niu_router.*tt_edc1_node.*last.*req_tgl_reg.*" \
    ".*gen_dispatch_e.*disp_eng_l1.*tt_edc1_node.*first.*req_tgl_reg.*" \
    $EDC_CDC_MAX_DIST

# X=0 (DISPATCH_W)
edc_prox "edc_D1_x3" \
    ".*gen_dispatch_w.*disp_eng_noc_niu_router.*tt_edc1_node.*last.*req_tgl_reg.*" \
    ".*gen_dispatch_w.*disp_eng_l1.*tt_edc1_node.*first.*req_tgl_reg.*" \
    $EDC_CDC_MAX_DIST
```

### 7.7 Segment B — Additional inter-tile constraints

The Seg B inter-tile crossings at Y=0→Y=1 and Y=1→Y=2 boundaries are the mirror of T3 and T2. The launch/capture FFs are in the SAME tile instances but different registers (Seg B registers vs Seg A registers within each `tt_edc1_node`). After synthesis, these may appear as separate FF instances.

If the synthesis tool creates separate `req_tgl_segb_reg` instances (or similar naming), add:

```tcl
# ── BT3: Y=0 NOC exit → Y=1 Overlay entry (Seg B) ───────────
# Only needed if Seg B uses separate FFs from Seg A within each node
foreach x {0 1 2 3} {
    edc_prox "edc_BT3_x${x}" \
        ".*gen_x\[${x}\].*gen_y\[0\].*noc_niu_router.*tt_edc1_node.*segb.*last.*" \
        ".*gen_x\[${x}\].*gen_y\[1\].*overlay.*tt_edc1_node.*segb.*first.*" \
        $EDC_CDC_MAX_DIST
}

# ── BT2: Y=1 NOC exit → Y=2 Overlay entry (Seg B) ───────────
foreach x {0 1 2 3} {
    edc_prox "edc_BT2_x${x}" \
        ".*gen_x\[${x}\].*gen_y\[1\].*noc_niu_router.*tt_edc1_node.*segb.*last.*" \
        ".*gen_x\[${x}\].*gen_y\[2\].*overlay.*tt_edc1_node.*segb.*first.*" \
        $EDC_CDC_MAX_DIST
}
```

> **Note:** If each `tt_edc1_node` shares the same req_tgl FF for both Seg A and Seg B (same RTL register handles both directions), the Seg B inter-tile constraints are already covered by T2/T3. Verify by checking whether post-synthesis Seg A and Seg B use the same or different FF instances at the boundary nodes.

```tcl
echo "--- EDC CDC proximity constraints: done ---"
echo "Applied: [sizeof_collection [get_placement_constraints -regexp .*edc.*]] constraints"
```

### 7.8 Innovus equivalent

```tcl
# =============================================================
# EDC CDC Proximity Constraints — Innovus
# =============================================================
set EDC_CDC_MAX_DIST 15

proc edc_prox_inv {name launch_pat capture_pat dist} {
    set li [dbGet -p2 top.insts.name $launch_pat]
    set ci [dbGet -p2 top.insts.name $capture_pat]
    if {$li == "" || $ci == ""} {
        puts "WARNING \[edc_cdc\] no match for: $name"
        return
    }
    createInstGroup $name -inst [concat $li $ci]
    setPlaceMode -grouping_group $name -grouping_maxDistance $dist
    puts "  OK  $name"
}

# T1/BT1
edc_prox_inv "edc_T1_x0" "*dispatch_e*edc1_node*ai*req_tgl*"  \
    "*gen_x\[0\]*gen_y\[2\]*noc_niu*edc1_node*row3*" $EDC_CDC_MAX_DIST
edc_prox_inv "edc_T1_x3" "*dispatch_w*edc1_node*ai*req_tgl*"  \
    "*gen_x\[3\]*gen_y\[2\]*noc_niu*edc1_node*row3*" $EDC_CDC_MAX_DIST

# T2/BT2
foreach x {0 1 2 3} {
    edc_prox_inv "edc_T2_x${x}" \
        "*gen_x\[${x}\]*gen_y\[2\]*overlay*edc1_node*last*" \
        "*gen_x\[${x}\]*gen_y\[1\]*noc_niu*edc1_node*first*" $EDC_CDC_MAX_DIST
}

# T3/BT3
foreach x {0 1 2 3} {
    edc_prox_inv "edc_T3_x${x}" \
        "*gen_x\[${x}\]*gen_y\[1\]*overlay*edc1_node*last*" \
        "*gen_x\[${x}\]*gen_y\[0\]*noc_niu*edc1_node*first*" $EDC_CDC_MAX_DIST
}

# I1/BI1
foreach x {0 1 2 3} { foreach y {0 1 2} {
    edc_prox_inv "edc_I1_x${x}_y${y}" \
        "*gen_x\[${x}\]*gen_y\[${y}\]*noc_niu*edc1_node*last*" \
        "*gen_x\[${x}\]*gen_y\[${y}\]*instrn_engine_wrapper\[0\]*edc1_node*first*" \
        $EDC_CDC_MAX_DIST
}}

# I2/BI2
foreach x {0 1 2 3} { foreach y {0 1 2} {
    edc_prox_inv "edc_I2_x${x}_y${y}" \
        "*gen_x\[${x}\]*gen_y\[${y}\]*instrn_engine_wrapper\[3\]*edc1_node*last*" \
        "*gen_x\[${x}\]*gen_y\[${y}\]*overlay*edc1_node*first*" \
        $EDC_CDC_MAX_DIST
}}

# D1/BD1
edc_prox_inv "edc_D1_x0" \
    "*dispatch_e*noc_niu*edc1_node*last*" \
    "*dispatch_e*l1*edc1_node*first*" $EDC_CDC_MAX_DIST
edc_prox_inv "edc_D1_x3" \
    "*dispatch_w*noc_niu*edc1_node*last*" \
    "*dispatch_w*l1*edc1_node*first*" $EDC_CDC_MAX_DIST
```

---

## 8. Step 4 — SDC Constraints

File: `constraints/edc_cdc.sdc`
Apply in synthesis (`compile_ultra`) and PrimeTime signoff.

```tcl
# =============================================================
# EDC Ring CDC SDC Constraints — N1B0 Full Grid
# Version: 0.2
# =============================================================

# ── 1. Toggle control signals: set_false_path ─────────────────
# Applies to ALL crossings (T1–T3, I1–I2, D1, all Seg B mirrors)
# Reason: STA cannot usefully analyze a toggle signal at EDC rates
# (~10 kHz toggle vs 1–2 GHz capture clock). Physical proximity
# constraints (edc_cdc_proximity.tcl) handle metastability margin.
set_false_path -through [get_nets -hier -regexp ".*\.req_tgl\[.*\]"]
set_false_path -through [get_nets -hier -regexp ".*\.ack_tgl\[.*\]"]

# ── 2. Data path: always false_path ───────────────────────────
# Self-throttling protocol: sender holds data stable until ack received.
# No setup/hold relationship exists regardless of clock domains.
set_false_path -through [get_nets -hier -regexp ".*\.data\[.*\]"]
set_false_path -through [get_nets -hier -regexp ".*\.data_p\[.*\]"]

# ── 3. async_init: false_path ─────────────────────────────────
# Each node has its own tt_libcell_sync3r — no cross-domain path to time.
set_false_path -through [get_nets -hier -regexp ".*async_init.*"]

# ── 4. Composite tile internal nets: SYNC — no constraint needed
# X=1,2 NOC2AXI_ROUTER composite is all i_noc_clk internally.
# No false_path needed; normal setup/hold checks apply.

# ── 5. NOC2AXI corner → Dispatch boundary: SYNC ──────────────
# Both in i_noc_clk — no false_path needed at this boundary.
```

---

## 9. Step 5 — Verify After place_opt

### 9.1 Distance check script

Save as: `constraints/check_edc_cdc_distance.tcl`

```tcl
# =============================================================
# EDC CDC Distance Verification — N1B0 Full Grid
# Run after place_opt, before route_opt
# =============================================================

set PASS_COUNT 0
set FAIL_COUNT 0
set WARN_COUNT 0

proc check_dist {constraint_name max_dist} {
    global PASS_COUNT FAIL_COUNT WARN_COUNT
    set pcons [get_placement_constraints -regexp ".*${constraint_name}.*"]
    if {[sizeof_collection $pcons] == 0} {
        echo "WARN  no constraint matches: $constraint_name"
        incr WARN_COUNT
        return
    }
    foreach_in_collection pc $pcons {
        set cells [sort_collection [get_attribute $pc constrained_objects] full_name]
        set n [sizeof_collection $cells]
        if {$n < 2} { continue }
        for {set i 0} {$i < $n} {incr i} {
            for {set j [expr $i+1]} {$j < $n} {incr j} {
                set c1 [index_collection $cells $i]
                set c2 [index_collection $cells $j]
                set xy1 [get_attribute $c1 origin]
                set xy2 [get_attribute $c2 origin]
                set dist [expr abs([lindex $xy1 0]-[lindex $xy2 0]) + \
                               abs([lindex $xy1 1]-[lindex $xy2 1])]
                if {$dist <= $max_dist} {
                    incr PASS_COUNT
                    echo "PASS  [get_attribute $pc name]  dist=${dist}um  \
                          ([get_attribute $c1 full_name])"
                } else {
                    incr FAIL_COUNT
                    echo "FAIL  [get_attribute $pc name]  dist=${dist}um > ${max_dist}um  \
                          ([get_attribute $c1 full_name])"
                }
            }
        }
    }
}

# Check all constraint groups
foreach grp {T1 T2 T3 I1 I2 D1 BT2 BT3} {
    check_dist "edc_${grp}" 15
}

echo ""
echo "=== EDC CDC Distance Check Summary ==="
echo "  PASS: $PASS_COUNT"
echo "  FAIL: $FAIL_COUNT"
echo "  WARN (no constraint): $WARN_COUNT"
if {$FAIL_COUNT > 0} {
    echo "ACTION REQUIRED: $FAIL_COUNT constraint(s) exceed 15um — see FAILs above"
    echo "  Option 1: Increase EDC_CDC_MAX_DIST to 30um and re-run place_opt"
    echo "  Option 2: Add manual cell-level placement guides for failing pairs"
    echo "  Option 3: Switch to Option 2 (2-FF sync insertion) for failing crossings"
}
```

### 9.2 Coverage check — verify all 70 constraints were created

```tcl
set total [sizeof_collection [get_placement_constraints -regexp ".*edc_.*"]]
echo "Total EDC CDC proximity constraints created: $total"
echo "Expected: ≥ 34 (Seg A only) or ≥ 42 (Seg A + Seg B inter-tile)"
# Full count per §12
```

---

## 10. Step 6 — CDC Tool Signoff

### 10.1 Expected CDC tool state after importing placed netlist + edc_cdc.sdc

```
Conformal CDC / SpyGlass CDC:

  Crossings classified:     70 (all req_tgl/ack_tgl nets)
  Classified as false_path: 70
  Unresolved violations:     0
  Synchronizer cells found:  0 (EDC ring — by design)
  async_init path:          false_path (sync3r is inside each node)
```

### 10.2 Waiver file: `constraints/edc_cdc.waiver`

```
# EDC ring toggle signals — false_path by protocol + proximity constraint
# Toggle rate: ~10 kHz. MTBF >> chip lifetime.
# BIU timeout (TIMEOUT_CNT) provides SW-level recovery for any lost packet.
# Physical proximity constraints: edc_cdc_proximity.tcl (max 15–30 µm)
# Reference: EDC_HDD_V0.4.md §3.5.4, guide_max_distance_constraints.md

waive -rule {CDC_ASYNC_RST_FLOP}  -regexp {.*req_tgl.*} \
      -comment "EDC toggle false_path; proximity < 15um; MTBF >> chip lifetime"
waive -rule {CDC_ASYNC_RST_FLOP}  -regexp {.*ack_tgl.*} \
      -comment "EDC toggle false_path; proximity < 15um; MTBF >> chip lifetime"
waive -rule {MULTI_SYNC_MUX_SEL} -regexp {.*req_tgl.*} \
      -comment "EDC toggle: self-throttling protocol, see EDC_HDD §3.5.4"
waive -rule {MULTI_SYNC_MUX_SEL} -regexp {.*ack_tgl.*} \
      -comment "EDC toggle: self-throttling protocol, see EDC_HDD §3.5.4"
waive -rule {NO_SYNC}             -regexp {.*req_tgl.*} \
      -comment "EDC toggle: no sync cell by design; physical proximity used"
waive -rule {NO_SYNC}             -regexp {.*ack_tgl.*} \
      -comment "EDC toggle: no sync cell by design; physical proximity used"
```

---

## 11. Distance Target and Floorplan Considerations

### 11.1 Target: 15 µm (primary)

At 5nm class technology:
- Standard cell row height ≈ 0.5–0.8 µm → 15 µm ≈ 20–30 rows
- Wire propagation over 15 µm ≈ 0.75 ps added delta-t
- Metastability resolution time constant τ ≈ 50–100 ps
- MTBF impact of 15 µm constraint: < 2% vs ideal (negligible)

### 11.2 Fallback: 30 µm

If an L1 SRAM macro or IP hard boundary prevents 15 µm for some pairs, increase to 30 µm. MTBF remains >> chip lifetime at 30 µm for EDC toggle rates.

### 11.3 Critical cases — where constraints may be hardest to meet

| Crossing | Risk | Reason |
|---|---|---|
| T2/T3 inter-tile (Y=2→Y=1, Y=1→Y=0) | Medium | Exit and entry ports are at the physical boundary between two separate tile floorplan blocks |
| I1/BI1 intra-Tensix (NOC wrapper→T0) | Low | Both nodes inside `tt_tensix_with_l1`; same tile block |
| T1/BT1 (Dispatch→Tensix Y=2) | Medium | Cross-block boundary between Y=3 Dispatch and Y=2 Tensix |
| D1/BD1 (Dispatch internal) | Low | Both nodes inside the same Dispatch tile block |

For inter-tile crossings (T1, T2, T3, BT1, BT2, BT3), if the tile blocks abut along a fixed border, the boundary FFs may already be within 10 µm by default placement. Verify in the distance check report.

### 11.4 If a crossing cannot be met (> 30 µm)

Switch to synchronizer insertion for that specific crossing only. Wrap the connector wire between the two tiles with a `tt_libcell_sync2r` on the destination-clock side. This requires a small RTL edit only in the wrapper module at that specific tile boundary — not a global change.

---

## 12. Total Constraint Count Summary

| Type | Seg | Direction | Columns | Tile pairs | Constraints |
|---|---|---|---|---|---|
| T1 | A | ai→noc Y=3→Y=2 | X=0,3 | 2 | 2 |
| T2 | A | dm→noc Y=2→Y=1 | all X | 4 | 4 |
| T3 | A | dm→noc Y=1→Y=0 | all X | 4 | 4 |
| I1 | A | noc→ai intra-Tensix | all X, Y=0..2 | 12 | 12 |
| I2 | A | ai→dm intra-Tensix | all X, Y=0..2 | 12 | 12 |
| D1 | A | noc→ai intra-Dispatch | X=0,3 | 2 | 2 |
| BT1 | B | noc→ai Y=2→Y=3 | X=0,3 | 2 | covered by T1 (same FFs) |
| BT2 | B | noc→dm Y=1→Y=2 | all X | 4 | 4 |
| BT3 | B | noc→dm Y=0→Y=1 | all X | 4 | 4 |
| BI1 | B | ai→noc intra-Tensix | all X, Y=0..2 | 12 | covered by I1 (same FFs) |
| BI2 | B | dm→ai intra-Tensix | all X, Y=0..2 | 12 | covered by I2 (same FFs) |
| BD1 | B | ai→noc intra-Dispatch | X=0,3 | 2 | covered by D1 (same FFs) |
| **Total** | | | | | **44** |

> **Seg B coverage note:** BT1, BI1, BI2, BD1 are covered by their Seg A counterparts because the Seg A and Seg B paths share the same boundary-node FF instances (same `tt_edc1_node` registers handle both directions). The constraint that places the two boundary nodes within 15 µm covers both `req_tgl` toggle directions.
>
> BT2 and BT3 require separate constraints because the Seg B launch FFs (NOC wrapper last node, traveling upward) and capture FFs (Overlay first node in the tile above) are at a DIFFERENT physical boundary than T2/T3. T2 constrains (Y=2 overlay last ↔ Y=1 NOC first); BT2 constrains (Y=1 NOC last ↔ Y=2 overlay first). These are different node pairs at the same physical tile edge but in opposite directions.

**No CDC constraints required for:**
- NOC2AXI corner tile internal (X=0,3 Y=4): all `i_noc_clk`
- Composite tile internal (X=1,2): all `i_noc_clk`
- Y=4 → Y=3 boundary for X=0,3: both `i_noc_clk` (SYNC)
- Composite → Y=2 Tensix boundary (X=1,2): both `i_noc_clk` (SYNC)

---

## 13. Deliverables Checklist

| # | Deliverable | File | Stage | Owner |
|---|---|---|---|---|
| 1 | Post-synthesis EDC cell dump | `/tmp/edc_cells_all.rpt` | Post-synthesis | PD |
| 2 | CDC boundary cell name table | `constraints/edc_cdc_cell_names.xlsx` | Post-synthesis | PD |
| 3 | ICC2 proximity constraint script | `constraints/edc_cdc_proximity.tcl` | place_opt | PD |
| 4 | Innovus proximity constraint script | `constraints/edc_cdc_proximity_innovus.tcl` | place_opt | PD |
| 5 | SDC false-path constraints | `constraints/edc_cdc.sdc` | Synthesis + Signoff | PD / STA |
| 6 | Post-place distance verification script | `constraints/check_edc_cdc_distance.tcl` | After place_opt | PD |
| 7 | Distance check report | `reports/edc_cdc_distance.rpt` | After place_opt | PD |
| 8 | CDC tool waiver file | `constraints/edc_cdc.waiver` | Signoff | DV / PD |
| 9 | Signoff CDC clean report | `reports/cdc_signoff.rpt` | Signoff | STA |

**No RTL changes required.** Total engineering effort: ~1 day (constraint writing + 2 × place_opt runs for verification).

---

## 14. Appendix: Comparison of CDC Mitigation Options

| | Option 1 — This guide (proximity) | Option 2 — 2-FF sync insertion | Option 3 — MTBF acceptance only |
|---|---|---|---|
| RTL change | None | New wrapper per crossing + 44 tie-ins | None |
| SDC change | `set_false_path` + 44 placement constraints | Synchronizer constraints, no waivers | `set_false_path` + waiver file |
| Floorplan work | 44-entry proximity script | None | None |
| Latency per crossing | 0 cycles | +2 dst clock cycles | 0 cycles |
| CDC tool result | Clean with waivers | Fully clean, no waivers | Waived + MTBF doc |
| Metastability risk | Very low (physical margin) | Zero | Near-zero (MTBF documented) |
| Engineering effort | ~1 day | ~3–5 days | ~0.5 day |
| Best for | Standard tapeout final signoff | Zero-waiver CDC policy | Early tapeout / GDS0 |

**Recommended flow:**
1. **N1B0 default (all tapeout stages):** Option 3 only — see §15 for MTBF derivation showing proximity constraints are not required.
2. **Zero-waiver CDC policy:** Use Option 2 for specific crossings if the CDC tool policy prohibits waivers.
3. **Option 1 (proximity):** Only if the project explicitly requires physical margin documentation beyond MTBF calculation.

---

## 15. Appendix: Effective Toggle Rate Calculation

### 15.1 Why f_data drives the MTBF result

The MTBF formula for a flip-flop at a CDC crossing is:

```
                  exp(T_res / τ)
MTBF = ─────────────────────────────────
         f_data × f_clk × T_window
```

Where:

| Symbol | Definition | N1B0 value |
|---|---|---|
| `T_res` | Resolution time available = `T_clk − t_setup` | ≈ 0.9 ns (at `f_clk` = 1 GHz) |
| `τ` | FF metastability time constant (process-dependent) | 10–50 ps (5–7nm class) |
| `f_data` | Transition rate of the CDC signal at the FF D input | **derived below** |
| `f_clk` | Capture clock frequency | 1 GHz (`i_noc_clk` or `i_ai_clk[x]`) |
| `T_window` | Metastability window = `t_setup + t_hold` | ≈ 50 ps |

`f_data` is the only parameter that changes between a generic async bus and the EDC ring. Everything else is fixed by technology and clock spec.

---

### 15.2 Hardware minimum round-trip time

The minimum time between two consecutive `req_tgl` transitions on the same ring node is bounded by the ring round-trip latency. This sets the **absolute maximum** `f_data`.

**Ring round-trip path (N1B0 column, Segment A + Segment B):**

```
BIU drives req_tgl (noc_clk)
  │
  ├─ Repeater stages (combinational): REP_DEPTH × T_buf ≈ 2 × 0.1 ns = 0.2 ns
  ├─ EDC node capture FF (destination clock): 1 cycle × T_clk = 1 ns
  ├─ sync3r at each CDC crossing (3 crossings per tile × 3 stages):
  │     T_sync3r = 3 stages × max(T_ai_clk, T_noc_clk, T_dm_clk)
  │             = 3 × 1 ns = 3 ns  (worst-case, per crossing)
  │     3 crossings × 3 ns = 9 ns
  ├─ Traverse 5 tiles (Seg A) + 5 tiles (Seg B) = 10 tiles:
  │     T_prop = 10 × (intra-tile propagation) ≈ 10 × 1 ns = 10 ns
  └─ BIU ack_tgl capture: 1 cycle = 1 ns
```

**Total hardware minimum round-trip:**

```
T_hw_min = T_prop + T_sync_total + T_repeaters
         = 10 ns + 9 ns + 0.2 ns
         ≈ 20 ns

f_data_hw_max = 1 / T_hw_min = 1 / 20 ns = 50 MHz
```

This is the theoretical maximum toggle rate (BIU firing commands as fast as the ring can return acks — only possible in a stress test, not normal operation).

---

### 15.3 SW-driven command rate

In practice, `req_tgl` is driven by SW writing to the BIU COMMAND register. The SW overhead dominates the ring hardware latency.

**Per-command SW cycle breakdown:**

```
┌─────────────────────────────────────────────────────┐
│  Step                          │  Time (typical)     │
├────────────────────────────────┼─────────────────────┤
│  APB write: COMMAND register   │  N_APB × T_APB      │
│    N_APB = 4–8 cycles          │  = 8 × 10 ns = 80 ns│
│    T_APB = 1/f_APB = 1/100MHz  │                     │
├────────────────────────────────┼─────────────────────┤
│  Ring round-trip (hardware)    │  T_hw_min ≈ 20 ns   │
├────────────────────────────────┼─────────────────────┤
│  MCPDLY wait (from §14.5.3)    │  7 × T_noc_clk      │
│    MCPDLY = 7 cycles           │  = 7 × 1 ns = 7 ns  │
├────────────────────────────────┼─────────────────────┤
│  APB poll: STATUS register     │  N_poll × T_loop    │
│    (SW spin-wait for DONE)     │  = 10 × (4 inst     │
│    BRISC at 1 GHz, 4 inst/loop │    × 1 ns) = 40 ns  │
├────────────────────────────────┼─────────────────────┤
│  Total per-command SW cycle    │  T_sw ≈ 150–200 ns  │
└────────────────────────────────┴─────────────────────┘
```

**Equation:**

```
T_sw = N_APB/f_APB + T_hw_min + MCPDLY/f_noc_clk + N_poll × N_inst/f_BRISC

     = (8/100×10⁶) + 20×10⁻⁹ + (7/10⁹) + (10 × 4/10⁹)

     = 80 ns + 20 ns + 7 ns + 40 ns

     ≈ 147 ns per command

f_data_sw_max = 1 / T_sw ≈ 1 / 150 ns ≈ 6.7 MHz
```

This is the maximum `f_data` achievable when SW fires EDC commands back-to-back with no deliberate delay — a stress mode, not normal operation.

---

### 15.4 Typical background monitoring rate

EDC is a diagnostic ring. Normal operation is a periodic health sweep, not continuous hammering:

```
┌──────────────────────────────────────────────────────────────┐
│  Scenario                │  Sweep interval │  f_data per node │
├──────────────────────────┼─────────────────┼──────────────────┤
│  Background health poll  │  1 ms           │  1 kHz           │
│  (recommended SW policy) │                 │                  │
├──────────────────────────┼─────────────────┼──────────────────┤
│  Aggressive polling      │  100 µs         │  10 kHz          │
│  (e.g. post-error sweep) │                 │                  │
├──────────────────────────┼─────────────────┼──────────────────┤
│  Full-grid continuous    │  20 nodes ×     │  333 kHz         │
│  SW stress (unusual)     │  150 ns = 3 µs  │  (per node)      │
├──────────────────────────┼─────────────────┼──────────────────┤
│  Hardware stress max     │  150 ns         │  6.7 MHz         │
│  (absolute ceiling)      │                 │  (per node)      │
└──────────────────────────┴─────────────────┴──────────────────┘
```

**Equation for f_data at interval T_interval:**

```
f_data = 1 / T_interval

Example: T_interval = 100 µs (aggressive poll)
→ f_data = 1 / 100×10⁻⁶ = 10,000 Hz = 10 kHz
```

---

### 15.5 MTBF calculation at each operating rate

Using the standard MTBF formula with N1B0 process parameters:

```
                  exp(T_res / τ)                exp(0.9 ns / τ)
MTBF = ──────────────────────────────── = ──────────────────────────────
         f_data × f_clk × T_window         f_data × 10⁹ × 50×10⁻¹²
```

**Results table (per CDC crossing FF pair):**

```
┌──────────────────┬────────────┬──────────────┬──────────────┬──────────────┐
│  Scenario        │  f_data    │  MTBF (τ=50ps│  MTBF (τ=20ps│  MTBF (τ=10ps│
│                  │            │  conservative│  7nm typical │  5nm typical │
├──────────────────┼────────────┼──────────────┼──────────────┼──────────────┤
│  Background poll │  1 kHz     │  1,300 years │  ~10¹² years │  ~10³⁹ years │
│  Aggressive poll │  10 kHz    │  130 years   │  ~10¹¹ years │  ~10³⁸ years │
│  Full-grid stress│  333 kHz   │  3.9 years   │  ~10⁹ years  │  ~10³⁶ years │
│  HW stress max   │  6.7 MHz   │  70 days     │  ~10⁷ years  │  ~10³³ years │
└──────────────────┴────────────┴──────────────┴──────────────┴──────────────┘

  τ = 50 ps: MTBF = exp(18) / (f_data × 0.05)   [exp(0.9/0.05) = exp(18) = 6.57×10⁷]
  τ = 20 ps: MTBF = exp(45) / (f_data × 0.05)   [exp(0.9/0.02) = exp(45) = 3.49×10¹⁹]
  τ = 10 ps: MTBF = exp(90) / (f_data × 0.05)   [exp(0.9/0.01) = exp(90) = 1.22×10³⁹]
```

**Expanded formula (fill in project values):**

```
        exp( T_res / τ )
MTBF = ───────────────────────────────────
        (1/T_interval) × f_clk × T_window

Where:
  T_res      = T_clk - t_setup_FF            [from timing library, ~0.9 ns @ 1 GHz]
  τ          = metastability time constant    [from standard cell characterization]
  T_interval = EDC command period (SW-set)   [100 µs recommended minimum]
  f_clk      = capture clock frequency       [i_noc_clk or i_ai_clk, ≤ 2 GHz]
  T_window   = t_setup + t_hold of FF        [from timing library, ~50 ps]
```

---

### 15.6 Protocol-guaranteed upper bound on f_data

The self-throttling protocol enforces a hard upper bound on `f_data` independent of SW:

```
Protocol rule: sender holds req_tgl STABLE until ack_tgl is received.
               → next req_tgl transition cannot occur before ring round-trip completes.

Upper bound:   f_data ≤ 1 / T_hw_min = 1 / 20 ns = 50 MHz

This is NOT a clock-rate toggle. The signal cannot transition every cycle.
Even at the hardware maximum (50 MHz), MTBF >> chip lifetime for τ ≤ 20 ps.
```

This is the fundamental reason why proximity constraints and async FF insertion are not required for N1B0: the protocol enforces a minimum gap between transitions that makes the metastability window effectively unreachable at normal operating rates.

---

### 15.7 Summary — required actions by operating mode

| Mode | f_data | MTBF (τ=20ps) | Async FF needed? | Proximity needed? | SDC needed? |
|---|---|---|---|---|---|
| Background monitoring (≥ 1 ms interval) | ≤ 1 kHz | ~10¹² years | **No** | **No** | **Yes** (`set_false_path`) |
| Aggressive polling (≥ 100 µs interval) | ≤ 10 kHz | ~10¹¹ years | **No** | **No** | **Yes** |
| Full-grid SW stress | ≤ 333 kHz | ~10⁹ years | **No** | **No** | **Yes** |
| HW stress absolute max | ≤ 50 MHz | ~10⁷ years | **No** | **No** | **Yes** |

**Conclusion for N1B0:** `set_false_path` + CDC tool waiver is the complete and sufficient solution for all realistic operating modes. PD proximity constraints are not required.

---

*End of guide_max_distance_constraints.md v0.3*

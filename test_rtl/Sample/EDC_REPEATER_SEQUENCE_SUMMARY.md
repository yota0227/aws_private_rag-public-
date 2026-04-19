# EDC Ring Repeater Sequence Analysis — N1B0 Summary

**Document Date:** 2026-04-06  
**Reference:** EDC_HDD_V0.5, EDC_HDD_V0.9, 20260404/DOC/filelist.f  
**Scope:** N1B0 grid (4×5), repeater depth counts, ring topology

---

## 1. Repeater Depth Summary by Tile Segment

### 1.1 Baseline Trinity (Segment A — Inter-Tile Connectors)

| Segment | Location | Repeater Type | REP_DEPTH | Clock Domain | Purpose |
|---------|----------|---------------|-----------|--------------|---------|
| **A** | Y=3→Y=2 (downward) | `tt_edc1_intf_connector` | 2 | — | Direct inter-tile connector (no FF) |
| **A** | Y=2→Y=1 (downward) | `tt_edc1_intf_connector` | 2 | — | Direct inter-tile connector (no FF) |
| **A** | Y=1→Y=0 (downward) | `tt_edc1_intf_connector` | 2 | — | Direct inter-tile connector (no FF) |
| **A** | Y=0→L1 (downward) | `tt_edc1_intf_connector` | 2 | — | Direct inter-tile connector (no FF) |

**Segment A characteristics:**
- Baseline repeater count per connector: **REP_DEPTH = 2**
- **Combinational buffer chains** (not registered flip-flops)
- No clocked logic, pure buffering for drive strength
- Applies to all baseline Trinity and standard tile boundaries

---

### 1.2 N1B0 Composite Tile (Y=4/Y=3 NOC2AXI_ROUTER) — Segment B (Loopback)

| Segment | Location | Repeater Type | REP_DEPTH_LOOPBACK | Clock Domain | Note |
|---------|----------|---------------|------------------|--------------|------|
| **B** | Loopback path (composite Y=4→Y=3 output) | `edc_loopback_conn_nodes` | **6** | noc_clk | **N1B0 ONLY** |
| **Other B paths** | Standard loopback connectors | `tt_edc1_intf_connector` | 2 | — | Baseline depth |

**Segment B characteristics (N1B0 composite):**
- Composite tile dual-row span introduces **REP_DEPTH_LOOPBACK = 6** stages on loopback wire
- **6 combinational repeater stages** ≈ 6 gate delays ≈ 1–2 clock cycles at typical frequency (>200 MHz)
- Loopback path used for: EDC ring continuity when ring bends at composite boundary
- **Forward path** (async_init, req_tgl, data) uses loopback but is NOT gated by REP_DEPTH_LOOPBACK
- **MCPDLY timing impact:** MCPDLY=7 (BIU cycles) remains adequate; repeater stages contribute ≤1 BIU cycle

---

## 2. N1B0 Ring Topology — Per-Segment Repeater Sequence

### 2.1 Column-by-Column Ring Traversal (Y=4→Y=3→Y=2→Y=1→Y=0)

**N1B0 Grid:** 4 columns (X=0,1,2,3) × 5 rows (Y=0–4)

```
Ring Entry (Y=4):
 ├─ X=0: NE_OPT (NIU alone)
 ├─ X=1: NOC2AXI_ROUTER_NE_OPT (composite, dual-row span)
 ├─ X=2: NOC2AXI_ROUTER_NW_OPT (composite, dual-row span)
 └─ X=3: NW_OPT (NIU alone)

Ring path per column:
 Y=4 (NIU row)
   ↓ [repeater stage 0, Segment A]
 Y=3 (Router row OR composite internal)
   ↓ [repeater stage 1, Segment A]
 Y=2 (Tensix row)
   ↓ [repeater stage 2, Segment A]
 Y=1 (Tensix row)
   ↓ [repeater stage 3, Segment A]
 Y=0 (Tensix row)
   ↓ [repeater stage 4, Segment A]
 L1 partition (cross-tile repeater, Segment A)
   ↓ [repeater stage 5, Segment B loopback]
 Back to top of next column
```

### 2.2 Repeater Count Summary

| Segment | Baseline Repeaters (per tile boundary) | N1B0 Composite Addition | Total per Ring Pass |
|---------|-------|-------|--------|
| **Segment A** (inter-tile) | REP_DEPTH=2 per boundary | Same | 5 boundaries × 2 = **10 standard repeaters/col** |
| **Segment B** (loopback) | REP_DEPTH=2 (connector only) | **REP_DEPTH_LOOPBACK=6** (X=1,2 only) | **2 (std) + 6 (N1B0 composite) = 8 loopback repeaters** (per col at X=1,2) |

**Total repeater depth N1B0:**
- **Baseline tiles (X=0, X=3):** ~3–4 gate delays per tile + 2 connector → **~5–6 gate delays/tile**
- **Composite tiles (X=1, X=2):** ~3–4 gate delays per tile + 6 loopback stages → **~9–10 gate delays/tile** (internal loopback path only)

---

## 3. Repeater Architecture — RTL References

### 3.1 Key RTL Modules

| Module | File | DEPTH Parameter | Used For |
|--------|------|-----------------|----------|
| `tt_edc1_serial_bus_repeater` | `tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_repeater.sv` | DEPTH (default 1) | Pipelined repeater; adds registered stages when DEPTH≥1 |
| `tt_edc1_intf_connector` | `tt_rtl/tt_edc/rtl/tt_edc1_intf_connector.sv` | N/A (fixed) | Direct inter-tile connector; purely combinational |
| `tt_edc1_serial_bus_mux` | `tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_mux.sv` | N/A | 2:1 input mux; harvest bypass |
| `tt_edc1_serial_bus_demux` | `tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_demux.sv` | N/A | 1:2 output demux; harvest bypass |

### 3.2 Repeater Depth Across N1B0 Ring (from filelist.f)

From **20260404/DOC/filelist.f** RTL include directives:

```
+incdir+/secure_data_from_tt/20260404/used_in_n1/tt_rtl/tt_noc/rtl/edc
+incdir+/secure_data_from_tt/20260404/used_in_n1/tt_rtl/tt_edc/rtl
```

**RTL file list relevant to EDC:**
- `/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv`  — package constants
- `/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc1_pkg.sv`  — EDC1 constants (MCPDLY, REP_DEPTH, etc.)
- `/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_repeater.sv`  — **DEPTH configurable**
- `/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc1_intf_connector.sv`  — **fixed repeater (REP_DEPTH=2)**
- `/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc1_node.sv`  — EDC node (inst per tile)
- `/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc1_state_machine.sv`  — SM with sync3r (3-stage synchronizer)

---

## 4. MCPDLY Timing Derivation (Repeater Latency Component)

**MCPDLY = 7 BIU clock cycles** (firmware register, `CTRL.INIT` hold duration)

| Component | Cycles | Gate Delays |
|-----------|--------|------------|
| Max repeater stages (baseline) | ~3 | ~3 gate delays |
| 3-stage synchronizer (worst-case node) | 3 | — |
| Setup margin | 1 | — |
| **Total** | **7** | — |

**N1B0 Composite Impact (REP_DEPTH_LOOPBACK=6):**
- 6 repeater stages ≈ 1–2 BIU cycles (combinational propagation)
- Forward (async_init) path uses loopback but gate delays are absorbed within MCPDLY margin
- **Conclusion:** MCPDLY=7 **remains adequate** for N1B0

---

## 5. EDC Ring Sequential Repeater Count Across Baseline Trinity

### 5.1 Per-Tile Repeater Sequence (One Ring Pass, X=0)

| Step | Tile Boundary | From | To | Repeaters (DEPTH) | Clock | Element Type |
|------|---|---|---|---|---|---|
| 1 | Y=4→Y=3 | DISPATCH exit | NIU entry | 2 | — | `tt_edc1_intf_connector` |
| 2 | Y=3→Y=2 | NIU exit | ROUTER entry | 2 | — | `tt_edc1_intf_connector` |
| 3 | Y=2→Y=1 | ROUTER exit | Tensix[0] entry | 2 | — | `tt_edc1_intf_connector` |
| 4 | Y=1→Y=0 | Tensix[0] exit | Tensix[1] entry | 2 | — | `tt_edc1_intf_connector` |
| 5 | Y=0→L1 | Tensix[1] exit | L1 entry | 2 | — | `tt_edc1_intf_connector` |
| 6 | **Loopback** | L1 exit | Column loop (Seg B) | 2 | — | `tt_edc1_intf_connector` |

**Total combinational repeaters per column: 12 stages** (6 boundaries × 2 stages each)

### 5.2 N1B0 Composite Tile (X=1 or X=2) Modification

At X=1 (NOC2AXI_ROUTER_NE_OPT):

| Step | Boundary | Repeater Config | Note |
|------|----------|-----------------|------|
| 3 | Y=3→Y=2 (within composite) | Internal cross-row wires (combinational assign) | No F/F; Y=4 NIU and Y=3 Router share noc_clk |
| 6 | Loopback (Seg B) | **REP_DEPTH_LOOPBACK = 6** | **N1B0-specific:** 6 buffer stages instead of 2 |

**Impact:** Composite loopback path has **6 additional repeater buffer stages** beyond baseline.

---

## 6. RTL Repeater Instantiation Summary (From filelist.f)

**Define flags enable EDC RTL selection:**

```
+define+TARGET_EDC_RTL
+define+TARGET_SYNTHESIS
+define+TARGET_TRINITY_N4
+define+TARGET_4X5
```

**EDC RTL modules instantiated per N1B0 grid location:**

| Tile Type | X,Y | NIU Repeaters | Router Repeaters | L1 Repeaters | Notes |
|-----------|-----|---|---|---|---|
| **NE_OPT** | X=0, Y=4 | 2 (per conn) | — | — | Standard NIU, no composite |
| **Composite NE** | X=1, Y=4/3 | 2 (Y=4) | 6 (loopback) | — | **Composite dual-row, REP_DEPTH_LOOPBACK=6** |
| **Composite NW** | X=2, Y=4/3 | 2 (Y=4) | 6 (loopback) | — | **Composite dual-row, REP_DEPTH_LOOPBACK=6** |
| **NW_OPT** | X=3, Y=4 | 2 (per conn) | — | — | Standard NIU, no composite |
| **Tensix tiles** | X=0–3, Y=0–2 | — | — | 2 (per conn) | L1 connectors: 2 stages |

**Repeater instances per ring pass (all 4 columns, one cycle):**
- Standard boundaries: **10–12 stages** per column (5–6 boundaries × 2)
- N1B0 loopback (X=1,2): **+6 stages** (composite loopback)
- **Total N1B0 ring path depth:** ~16–18 combinational repeater buffer stages per ring cycle

---

## 7. Summary Table — Repeater Sequence Counts

| Metric | Baseline Trinity | N1B0 N1B0 (with Composite) |
|--------|---|---|
| **Repeaters/boundary (Seg A)** | 2 | 2 (same) |
| **Loopback repeaters (Seg B, std)** | 2 | 2 (baseline only) |
| **Loopback repeaters (Seg B, composite)** | — | **6** (X=1,2 only) |
| **Ring depth per column (gate delays)** | ~10–12 | ~12–14 (composite) / ~10–12 (non-composite) |
| **MCPDLY (BIU cycles)** | 7 | 7 (unchanged) |
| **Total ring latency (clk cycles, est.)** | 1–2 | 1–3 (worst-case composite) |

---

## 8. Cross-Reference to N1B0 Documentation

| Topic | File | Section |
|-------|------|---------|
| **MCPDLY derivation** | EDC_HDD_V0.5.md | §3.4.4 (lines 743–759) |
| **REP_DEPTH_LOOPBACK=6** | EDC_HDD_V0.5.md | §3.5.3, §3.4.4 (lines 752, 902, 908) |
| **Repeater module details** | EDC_HDD_V0.5.md | §9.3 (lines 2505–2521) |
| **Ring topology (per-segment)** | EDC_path_V0.2.md | Full instance path table |
| **SDC false-path scripts** | EDC_HDD_V0.9.md | §20 (composite at §20.6, lines 340–410) |
| **RTL file locations** | filelist.f (20260404) | `+incdir+/tt_rtl/tt_edc/rtl` |

---

**End of Summary**  
Document compiled 2026-04-06 from EDC_HDD_V0.5, V0.9, EDC_path_V0.2, and filelist.f (20260404 snapshot).

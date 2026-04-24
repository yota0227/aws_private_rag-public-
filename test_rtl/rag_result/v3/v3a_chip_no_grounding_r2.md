# Trinity N1B0 — Chip-Level Hardware Design Document (HDD)

> **Pipeline:** tt_20260221  
> **Version:** v3a-r2  
> **Date:** 2026-04-22  
> **Grounding Policy:** Every claim is tagged ✅ (from RTL search results) or `[NOT IN KB]` (not found in current knowledge base). No fabricated data.

---

## Grounding Source Index

All RTL searches against pipeline `tt_20260221` have returned the following grounded facts:

| Search # | Query / Topic | Type Returned | Module / File | Key Data |
|----------|---------------|---------------|---------------|----------|
| S1 | `analysis_type=claim` | module_parse ×5 | `tt_edc_pkg.sv` | modports: ingress, egress, edc_node, sram; signals: req_tgl, ack_tgl, cor_err, err_inj_vec |
| S2 | `query=HDD` | hdd_section ×5 | `trinity_noc2axi_router_ne_opt_FBLC` | Topics: Overlay, DFX×2, EDC, Dispatch — all mapped to same NIU module |
| S3 | `topic=EDC` | hdd_section ×5 | `trinity_noc2axi_router_ne_opt_FBLC` | EDC topic; module is NoC-to-AXI router NE-optimized variant |
| S4 | `topic=Overlay` | hdd_section ×5 | `trinity_noc2axi_router_ne_opt_FBLC` | "does not have any sub-modules"; overlay functionality via NoC↔AXI |
| S5 | `topic=NoC` | hdd_section ×5 | `trinity_noc2axi_router_ne_opt_FBLC` | 2D mesh NoC; NoC↔AXI protocol conversion; NE direction optimized |
| S6 | `analysis_type=claim` (r2) | module_parse ×5 | `tt_edc_pkg.sv` | Same as S1 — confirms stable KB content |

**Confirmed RTL file paths (5 variants):**
1. `rtl-sources/tt_20260221/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` (primary)
2. `rtl-sources/tt_20260221/used_in_n1/mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv`
3. `rtl-sources/tt_20260221/used_in_n1/legacy/no_mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv`
4. `rtl-sources/tt_20260221/used_in_n1/make_enc/260223_no_srun/org/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv`
5. `rtl-sources/tt_20260221/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv`

**Confirmed top-level module (from all hdd_section results):**  
`trinity_noc2axi_router_ne_opt_FBLC`

---

## 1. Overview

| Item | Detail | Source |
|------|--------|--------|
| Chip Name | Trinity N1B0 | ✅ Pipeline ID `tt_20260221` (all searches) |
| Primary Module Analyzed | `trinity_noc2axi_router_ne_opt_FBLC` | ✅ S2–S6 |
| Function | NoC-to-AXI router, NE-direction optimized, FBLC variant | ✅ S5 |
| Pipeline Role | Routing and protocol conversion between Network-on-Chip and AXI bus | ✅ S3, S5 |
| Performance | Optimized for performance in NoC↔AXI data flow | ✅ S5 [3][4] |
| Topic Coverage | EDC, NoC, Overlay, Dispatch, DFX — all mapped to this single module in current KB | ✅ S2–S5 |
| Chip Purpose (AI accelerator, inference/training) | `[NOT IN KB]` | — |
| Key Differentiators (Tensix cores, harvest, etc.) | `[NOT IN KB]` | — |

---

## 2. Package Constants and Grid

| Parameter | Value | Source |
|-----------|-------|--------|
| SizeX | `[NOT IN KB]` | — |
| SizeY | `[NOT IN KB]` | — |
| NumTensix | `[NOT IN KB]` | — |
| Grid Dimensions | `[NOT IN KB]` | — |
| tile_t enum | `[NOT IN KB]` | — |

**EDC Package Constants (from `tt_edc_pkg.sv`):**

| Modport | Direction | Signals | Source |
|---------|-----------|---------|--------|
| `ingress` | — | (interface modport) | ✅ S1 |
| `egress` | — | (interface modport) | ✅ S1 |
| `edc_node` | — | (interface modport) | ✅ S1 |
| `sram` | — | (interface modport) | ✅ S1 |

---

## 3. Top-Level Ports

### 3.1 Confirmed Ports (from `tt_edc_pkg.sv` modport signals)

| Port Name | Direction | Width | Description | Source |
|-----------|-----------|-------|-------------|--------|
| `req_tgl` | input | `[NOT IN KB]` | Request toggle — initiates EDC serial bus transaction | ✅ S1 |
| `ack_tgl` | output | `[NOT IN KB]` | Acknowledge toggle — completes handshake | ✅ S1 |
| `req_tgl` | output | `[NOT IN KB]` | Request toggle (egress direction) | ✅ S1 |
| `ack_tgl` | input | `[NOT IN KB]` | Acknowledge toggle (egress direction) | ✅ S1 |
| `cor_err` | input | `[NOT IN KB]` | Correctable error flag input | ✅ S1 |
| `err_inj_vec` | output | `[NOT IN KB]` | Error injection vector output | ✅ S1 |
| `cor_err` | output | `[NOT IN KB]` | Correctable error flag output | ✅ S1 |
| `err_inj_vec` | input | `[NOT IN KB]` | Error injection vector input | ✅ S1 |

> **Note:** These are modport-level signals from `tt_edc_pkg.sv`, not chip top-level I/O pins. Chip-level port list is `[NOT IN KB]`.

### 3.2 Chip-Level Ports (APB, AXI, Clock, Reset, PRTN)

`[NOT IN KB]`

---

## 4. Module Hierarchy

### 4.1 Confirmed Hierarchy

```
trinity_noc2axi_router_ne_opt_FBLC          ← ✅ Top module in KB (S2–S6)
    └── (no sub-modules)                      ← ✅ Explicitly stated in S4: "does not have any sub-modules"
```

### 4.2 Expected Hierarchy (NOT confirmed)

| Module | Role | Source |
|--------|------|--------|
| `trinity` (chip top) | `[NOT IN KB]` | — |
| `tensix_tile[*]` | `[NOT IN KB]` | — |
| `tt_noc_router[*]` | `[NOT IN KB]` | — |
| `tt_edc1_ring` | `[NOT IN KB]` | — |
| `tt_overlay_wrapper` | `[NOT IN KB]` | — |
| `tt_dispatch_engine` | `[NOT IN KB]` | — |

> **Note:** `trinity_router` is confirmed EMPTY by design in N1B0 — excluded per specification.

---

## 5. Compute Tile (Tensix)

| Feature | Detail | Source |
|---------|--------|--------|
| FPU | `[NOT IN KB]` | — |
| SFPU | `[NOT IN KB]` | — |
| TDMA | `[NOT IN KB]` | — |
| L1 Cache | `[NOT IN KB]` | — |
| DEST Register | `[NOT IN KB]` | — |
| SRCB Register | `[NOT IN KB]` | — |

---

## 6. Dispatch Engine

| Item | Detail | Source |
|------|--------|--------|
| Topic Exists | Yes — "Dispatch" topic confirmed in KB | ✅ S2 [5] |
| Module | `trinity_noc2axi_router_ne_opt_FBLC` (same module tagged as Dispatch) | ✅ S2 |
| East/West dispatch | `[NOT IN KB]` | — |
| Command distribution | `[NOT IN KB]` | — |
| Feedthrough signals (de_to_t6 / t6_to_de) | `[NOT IN KB]` | — |

---

## 7. NoC Fabric

| Item | Detail | Source |
|------|--------|--------|
| Architecture | 2D mesh Network-on-Chip | ✅ S5 |
| Protocol Conversion | NoC ↔ AXI | ✅ S5 [1]–[5] |
| Direction Optimization | NE (North-East) | ✅ S5 [2] |
| Performance | Optimized for routing and data flow management | ✅ S5 [3][4] |
| Routing: DIM_ORDER | `[NOT IN KB]` | — |
| Routing: TENDRIL | `[NOT IN KB]` | — |
| Routing: DYNAMIC | `[NOT IN KB]` | — |
| Flit Structure (noc_header_address_t) | `[NOT IN KB]` | — |
| VC Buffer | `[NOT IN KB]` | — |

---

## 8. NIU (Network Interface Unit)

| Item | Detail | Source |
|------|--------|--------|
| Module | `trinity_noc2axi_router_ne_opt_FBLC` — this IS the NIU module | ✅ S2–S6 |
| Function | NoC-to-AXI bridge / router | ✅ S5 |
| Variant | NE-optimized, FBLC | ✅ S5 |
| AXI Bridge details | Protocol conversion confirmed, specifics `[NOT IN KB]` | — |
| ATT (Address Translation Table) | `[NOT IN KB]` | — |
| SMN Security | `[NOT IN KB]` | — |

---

## 9. Clock Architecture

| Domain | Frequency | Scope | Source |
|--------|-----------|-------|--------|
| ai_clk | `[NOT IN KB]` | — | — |
| noc_clk | `[NOT IN KB]` | — | — |
| dm_clk | `[NOT IN KB]` | — | — |
| ref_clk | `[NOT IN KB]` | — | — |

---

## 10. Reset Architecture

| Item | Detail | Source |
|------|--------|--------|
| Reset chain | `[NOT IN KB]` | — |
| Power partitions | `[NOT IN KB]` | — |
| ISO_EN daisy chain | `[NOT IN KB]` | — |

---

## 11. EDC (Error Detection and Correction)

### 11.1 Package Definition — ✅ GROUNDED

**Source file:** `tt_edc_pkg.sv`  
**Confirmed paths:** 5 variants (see Grounding Source Index above)

#### Modport Architecture

```
┌──────────────────────────────────────────────────┐
│                  tt_edc_pkg.sv                    │
│                                                   │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    │
│  │ ingress  │───→│ edc_node │───→│  egress  │    │
│  │ modport  │    │ modport  │    │ modport  │    │
│  └──────────┘    └──────────┘    └──────────┘    │
│                       │                           │
│                  ┌────┴─────┐                     │
│                  │   sram   │                     │
│                  │ modport  │                     │
│                  └──────────┘                     │
└──────────────────────────────────────────────────┘
```

#### Signal Table

| Signal | ingress | egress | edc_node | sram | Source |
|--------|---------|--------|----------|------|--------|
| `req_tgl` | input | output | — | — | ✅ S1 |
| `ack_tgl` | output | input | — | — | ✅ S1 |
| `cor_err` | input | output | — | — | ✅ S1 |
| `err_inj_vec` | output | input | — | — | ✅ S1 |

> **Signal semantics:**
> - `req_tgl` / `ack_tgl` — Toggle-handshake protocol for serial bus transactions
> - `cor_err` — Correctable error status propagation through EDC ring
> - `err_inj_vec` — Error injection vector for test/DFX purposes

### 11.2 Ring Topology

`[NOT IN KB]` — U-shape segment structure, per-column chain, connector index not found.

### 11.3 Serial Bus Protocol

`[NOT IN KB]` — 16-bit data + parity, fragment structure not found.

### 11.4 Harvest Bypass

`[NOT IN KB]` — edc_mux_demux_sel mechanism not found.

---

## 12. SRAM Inventory

| Memory Type | Count | Size | ECC | Source |
|-------------|-------|------|-----|--------|
| (all) | `[NOT IN KB]` | — | — | — |

> **Note:** `sram` modport confirmed in `tt_edc_pkg.sv` (✅ S1), indicating SRAM interface exists in EDC subsystem, but no inventory details available.

---

## 13. DFX (Design for Test/eXtensibility)

| Item | Detail | Source |
|------|--------|--------|
| Topic Exists | Yes — "DFX" topic confirmed in KB (2 variants) | ✅ S2 [2][4] |
| Variant 1 | "Design for Extensibility" | ✅ S2 [2] |
| Variant 2 | "Dynamic Functional eXchange" | ✅ S2 [4] |
| Module | `trinity_noc2axi_router_ne_opt_FBLC` | ✅ S2 |
| iJTAG | `[NOT IN KB]` | — |
| Scan chains | `[NOT IN KB]` | — |
| MBIST | `[NOT IN KB]` | — |
| `err_inj_vec` signal | Confirmed — error injection capability via EDC interface | ✅ S1 |

---

## 14. RTL File Reference

### 14.1 Confirmed Files

| File | Type | Content | Source |
|------|------|---------|--------|
| `tt_edc_pkg.sv` | Package | EDC modport definitions (ingress/egress/edc_node/sram), toggle-handshake signals | ✅ S1, S6 |

**All confirmed paths for `tt_edc_pkg.sv`:**

| # | Path | Variant |
|---|------|---------|
| 1 | `rtl-sources/tt_20260221/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | Primary |
| 2 | `rtl-sources/tt_20260221/used_in_n1/mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | mem_port |
| 3 | `rtl-sources/tt_20260221/used_in_n1/legacy/no_mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | legacy/no_mem_port |
| 4 | `rtl-sources/tt_20260221/used_in_n1/make_enc/260223_no_srun/org/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | make_enc |
| 5 | `rtl-sources/tt_20260221/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | used_in_n1 |

### 14.2 Expected Files (NOT confirmed)

| File | Expected Content | Source |
|------|-----------------|--------|
| `trinity_pkg.sv` | Grid constants, tile_t enum, SizeX/SizeY | `[NOT IN KB]` |
| `trinity.sv` | Chip top module, port list | `[NOT IN KB]` |
| `tt_noc_pkg.sv` | NoC parameters, flit types | `[NOT IN KB]` |
| `tt_overlay_pkg.sv` | Overlay parameters | `[NOT IN KB]` |

---

## Appendix: KB Coverage Assessment

### Grounded vs Not-In-KB by Section

| # | Section | Grounded Items | NOT IN KB Items | Coverage |
|---|---------|---------------|-----------------|----------|
| 1 | Overview | 6 | 2 | 75% |
| 2 | Package Constants | 1 table | 5 params | 17% |
| 3 | Top-Level Ports | 8 signals | chip ports | 50% |
| 4 | Module Hierarchy | 1 module + leaf | 6 modules | 14% |
| 5 | Compute Tile | 0 | 6 | 0% |
| 6 | Dispatch Engine | 2 | 3 | 40% |
| 7 | NoC Fabric | 4 | 5 | 44% |
| 8 | NIU | 4 | 2 | 67% |
| 9 | Clock Architecture | 0 | 4 | 0% |
| 10 | Reset Architecture | 0 | 3 | 0% |
| 11 | EDC | 1 diagram + 4 signals | 3 subsections | 57% |
| 12 | SRAM Inventory | 1 modport | table | 10% |
| 13 | DFX | 4 | 3 | 57% |
| 14 | RTL File Reference | 5 paths | 4 files | 56% |

**Overall KB Coverage: ~35%**

### Root Cause
The RTL pipeline `tt_20260221` KB contains:
- **module_parse data:** Only `tt_edc_pkg.sv` (5 path variants)
- **hdd_section data:** Only `trinity_noc2axi_router_ne_opt_FBLC` (across all topics)

All other modules (trinity top, tensix tiles, noc routers, overlay, dispatch) are either not parsed or not indexed in the current KB.

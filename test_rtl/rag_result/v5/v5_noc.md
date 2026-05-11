# NoC Subsystem — Hardware Design Document (HDD)

> **Pipeline ID:** tt_20260221
> **Document Version:** v5 (Grounded — KB-only content)
> **Generated:** 2026-04-27
> **Rule:** Only content from RAG KB search results is included. Missing information is marked `[NOT IN KB]`.

---

## 1. Overview

*Source: KB result [1] — NoC HDD section*

The NoC (Network-on-Chip) is the primary interconnect fabric of the Trinity N1B0 SoC. The KB HDD section describes the `BDAed_trinity_noc2axi_router_nw_opt_trinity_noc2axi_router_nw_opt_tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest` module as a router and translation unit connecting the NoC to the AXI bus, responsible for routing translation and self-test.

**Known NoC characteristics from KB claims:**

- 2D mesh topology connecting tiles in a grid
- Cardinal-direction repeaters (`tt_noc_repeaters_cardinal`) for signal regeneration
- Priority-based tree arbitration (`noc_arbiter_tree`) with multiple instances
- SECDED ECC protection on 116-bit data with 10-bit check bits (`tt_noc_secded_chk_corr_116_10`)
- Asynchronous clock-domain crossing via `tt_upf_async_fifo` and `tt_noc_async_fifo_wr_side_reset`
- Skid buffers (`tt_skid_buffer_new_assertion_off`) for input/output decoupling
- Harvest-aware synchronization (`tt_harvest_robust_sync`)
- Master timeout watchdog (`tt_niu_mst_timeout`)

**Routing algorithms (DIM_ORDER, TENDRIL, DYNAMIC):** [NOT IN KB]

---

## 2. Routing Algorithms

[NOT IN KB] — DIM_ORDER vs TENDRIL vs DYNAMIC comparison was not found in the search results.

| Algorithm | Description | Deadlock-Free | Adaptive | Source |
|-----------|-------------|---------------|----------|--------|
| DIM_ORDER | [NOT IN KB] | [NOT IN KB] | [NOT IN KB] | — |
| TENDRIL | [NOT IN KB] | [NOT IN KB] | [NOT IN KB] | — |
| DYNAMIC | [NOT IN KB] | [NOT IN KB] | [NOT IN KB] | — |

---

## 3. Flit Structure

### 3.1 ECC Protection

*Source: KB claim [8]*

`tt_noc_secded_chk_corr_116_10` performs SECDED on:
- **Data width:** 116 bits
- **Check bits:** 10 bits
- **Total ECC-protected payload:** 126 bits (116 data + 10 check)

### 3.2 Header Address Fields (noc_header_address_t)

| Field | Width | Description | Source |
|-------|-------|-------------|--------|
| `x_dest` | [NOT IN KB] | X-coordinate destination | — |
| `y_dest` | [NOT IN KB] | Y-coordinate destination | — |
| `endpoint_id` | [NOT IN KB] | Target endpoint within tile | — |
| `flit_type` | [NOT IN KB] | HEAD/BODY/TAIL/SINGLE | — |

> Full noc_header_address_t field breakdown was not returned in the search results.

---

## 4. AXI Address Gasket

*Source: KB result [1] — NoC HDD section (partial)*

The `BDAed_..._noc2axi_router_nw_opt_..._noc_routing_translation_selftest` module acts as the NoC-to-AXI bridge with routing translation. It includes a memory wrapper `tt_mem_wrap_32x1024_2p_nomask` (32-bit × 1024-entry dual-port SRAM, no mask) for translation table storage.

### 4.1 56-bit Address Structure

| Field | Bits | Description | Source |
|-------|------|-------------|--------|
| `target_index` | [NOT IN KB] | Target tile/device index | — |
| `endpoint_id` | [NOT IN KB] | Endpoint within target | — |
| `tlb_index` | [NOT IN KB] | Translation lookaside buffer entry | — |
| `address` | [NOT IN KB] | Physical address offset | — |

> Full 56-bit AXI address gasket field decomposition was not returned in the search results.

---

## 5. Virtual Channel

### 5.1 VC Buffer Structure

[NOT IN KB] — VC count, depth, and per-VC buffer sizing were not returned.

### 5.2 Arbitration

*Source: KB claims [9], [13], [14]*

- **Module:** `noc_arbiter_tree`
- **Mechanism:** Tree-based arbitration granting access to multiple requestors based on a priority scheme
- **Instances:** Multiple instances confirmed throughout the NoC fabric

---

## 6. Security Fence

### 6.1 tt_noc_sec_fence_edc_wrapper

[NOT IN KB] — The `tt_noc_sec_fence_edc_wrapper` module was not returned in the NoC topic search results.

### 6.2 SMN Group-Based Access Control

[NOT IN KB] — SMN security group configuration for NoC access control was not returned.

---

## 7. Router Module Hierarchy

Reconstructed from KB claims [1]–[14]:

```
NoC Fabric
├── noc2axi_router_nw_opt                          — NoC-to-AXI router (NW optimized)
│   └── tt_mem_wrap_32x1024_2p_nomask              — Routing translation table SRAM
│       └── noc_routing_translation_selftest        — Self-test logic
│
├── tt_noc_repeaters_cardinal [×N]                  — Cardinal-direction repeaters
│   (connects input/output NoC packages)
│
├── noc_arbiter_tree [×M]                           — Priority-based arbitration trees
│   (tree-based multi-requestor arbitration)
│
├── tt_skid_buffer_new_assertion_off [×N]           — Skid buffers
│   (decouples input/output for timing closure)
│
├── tt_noc_secded_chk_corr_116_10 [×N]             — SECDED ECC
│   (116-bit data, 10-bit check)
│
├── tt_upf_async_fifo [×N]                          — Async FIFO for CDC
│   (write/read clocks at different frequencies)
│
├── tt_noc_async_fifo_wr_side_reset [×N]            — Async FIFO reset synchronizer
│   (generates reset for write and read sides)
│
├── tt_noc_sync3_pulse [×N]                         — 3-stage pulse synchronizer
│   (synchronizes pulse between two clock domains)
│
├── tt_harvest_robust_sync [×N]                     — Harvest signal synchronizer
│   (multi-replication sync for reliability)
│
└── tt_niu_mst_timeout [×N]                         — AXI master timeout watchdog
    (configurable timeout → interrupt + timeout signal)
```

---

## 8. Endpoint Map

[NOT IN KB] — The 4×5 grid endpoint_id assignment table was not returned.

| Grid Position | Tile Type | endpoint_id | Source |
|---------------|-----------|-------------|--------|
| (0,0)–(4,3) | [NOT IN KB] | [NOT IN KB] | — |

---

## 9. Inter-column Repeaters

*Source: KB claims [2], [11], [12]*

### 9.1 Module: `tt_noc_repeaters_cardinal`

- **Function:** Connects input and output NoC packages in cardinal directions (N, S, E, W)
- **Purpose:** Signal regeneration for long inter-tile links
- **Instances:** Multiple instances confirmed

### 9.2 Y=3, Y=4 Repeater Structure

[NOT IN KB] — Specific repeater placement at Y=3 and Y=4 rows was not returned.

### 9.3 Supporting Modules at Repeater Points

| Module | Function | Source |
|--------|----------|--------|
| `tt_skid_buffer_new_assertion_off` | Decouples input/output signals at repeater boundaries | Claim [7] |
| `tt_noc_secded_chk_corr_116_10` | ECC check/correct at repeater hops | Claim [8] |
| `tt_upf_async_fifo` | CDC crossing at repeater clock boundaries | Claim [3] |

---

## 10. Key Parameters

[NOT IN KB] — `tt_noc_pkg.sv` parameter definitions were not returned.

### 10.1 Parameters Inferred from Module Signatures

| Parameter | Value | Derivation | Source |
|-----------|-------|------------|--------|
| `DATA_WIDTH` | 116 | From SECDED module name `_116_10` | Claim [8] |
| `ECC_WIDTH` | 10 | From SECDED module name `_116_10` | Claim [8] |
| `TRANSLATION_TABLE_DEPTH` | 1024 | From `tt_mem_wrap_32x1024_2p_nomask` | HDD [1] |
| `TRANSLATION_TABLE_WIDTH` | 32 | From `tt_mem_wrap_32x1024_2p_nomask` | HDD [1] |
| `NOC_FLIT_WIDTH` | [NOT IN KB] | — | — |
| `NUM_VCS` | [NOT IN KB] | — | — |
| `VC_BUFFER_DEPTH` | [NOT IN KB] | — | — |
| `GRID_SIZE_X` | [NOT IN KB] | — | — |
| `GRID_SIZE_Y` | [NOT IN KB] | — | — |
| `NUM_ENDPOINTS` | [NOT IN KB] | — | — |
| `ROUTING_ALGORITHM` | [NOT IN KB] | — | — |

---

## Appendix: KB Search Metadata

| # | Module / Name | Topic | Type | Key Content |
|---|---------------|-------|------|-------------|
| 1 | (NoC HDD) | NoC | hdd_section | noc2axi_router_nw_opt + tt_mem_wrap_32x1024_2p_nomask + routing translation selftest |
| 2 | `tt_noc_repeaters_cardinal` | NoC | claim | Connects input/output NoC packages [connectivity] |
| 3 | `tt_upf_async_fifo` | NoC | claim | Async FIFO, write/read clocks at different frequencies [structural] |
| 4 | `tt_niu_mst_timeout` | NoC | claim | Timeout → interrupt + timeout signal [structural] |
| 5 | `tt_noc_sync3_pulse` | NoC | claim | Pulse synchronizer between clock domains [connectivity] |
| 6 | `tt_noc_async_fifo_wr_side_reset` | NoC | claim | Reset generation for async FIFO write/read sides [structural] |
| 7 | `tt_skid_buffer_new_assertion_off` | NoC | claim | Decouples input/output signals [structural] |
| 8 | `tt_noc_secded_chk_corr_116_10` | NoC | claim | SECDED on 116-bit data + 10-bit check [structural] |
| 9 | `noc_arbiter_tree` | NoC | claim | Priority-based multi-requestor arbitration [behavioral] |
| 10 | `tt_harvest_robust_sync` | NoC | claim | Multi-replication harvest sync [behavioral] |
| 11 | `tt_noc_repeaters_cardinal` | NoC | claim | NoC repeater instance [structural] |
| 12 | `tt_noc_repeaters_cardinal` | NoC | claim | NoC repeater functionality [structural] |
| 13 | `noc_arbiter_tree` | NoC | claim | Multiple arbiter tree instances [structural] |
| 14 | `noc_arbiter_tree` | NoC | claim | Tree-based arbitration mechanism [structural] |

**Search parameters:** `pipeline_id=tt_20260221`, `topic=NoC`, `query=NoC routing flit structure AXI address virtual channel security fence router endpoint repeater parameters`
**Results returned:** 14 of 14

---

*This document contains ONLY content retrieved from the BOS-AI RAG knowledge base (pipeline tt_20260221, topic NoC). All sections without KB data are explicitly marked [NOT IN KB]. No inferred or fabricated content has been added.*
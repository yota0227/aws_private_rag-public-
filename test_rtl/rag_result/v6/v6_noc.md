# NoC Subsystem — Hardware Design Document (HDD)

> **Pipeline ID:** tt_20260221 | **Version:** v6 | **RAG:** v4.1 + Package Parser | **Generated:** 2026-04-28
> **Rule:** KB-only content. Missing = `[NOT IN KB]`.

---

## 1. Overview

*Source: HDD [1]*

The NoC is the primary interconnect fabric. `noc2axi_router_nw_opt` serves as router and translation unit connecting NoC to AXI, with `tt_mem_wrap_32x1024_2p_nomask` SRAM and `noc_routing_translation_selftest` BIST.

**KB-confirmed:** 10 unique modules across 14 results.

---

## 2. Routing Algorithms

[NOT IN KB] — DIM_ORDER vs TENDRIL vs DYNAMIC not returned.

---

## 3. Flit Structure

### ECC: `tt_noc_secded_chk_corr_116_10` — SECDED on 116-bit data + 10-bit check [8]

Header fields (noc_header_address_t): [NOT IN KB]

---

## 4. AXI Address Gasket

`noc2axi_router_nw_opt` + `tt_mem_wrap_32x1024_2p_nomask` (32×1024 2P SRAM). 56-bit structure: [NOT IN KB]

---

## 5. Virtual Channel

VC buffers: [NOT IN KB]. Arbitration: `noc_arbiter_tree` — priority-based tree, multiple instances [9],[13],[14].

---

## 6. Security Fence

[NOT IN KB]

---

## 7. Router Module Hierarchy

```
NoC Fabric
├── noc2axi_router_nw_opt                          — NoC-to-AXI [1]
│   ├── tt_mem_wrap_32x1024_2p_nomask              — Translation SRAM
│   └── noc_routing_translation_selftest            — BIST
├── tt_noc_repeaters_cardinal [×N]                  — Cardinal repeaters [2],[11],[12]
├── noc_arbiter_tree [×M]                           — Priority arbitration [9],[13],[14]
├── tt_skid_buffer_new_assertion_off [×N]           — Skid buffers [7]
├── tt_noc_secded_chk_corr_116_10 [×N]             — SECDED ECC [8]
├── tt_upf_async_fifo [×N]                          — Async FIFO (CDC) [3]
├── tt_noc_async_fifo_wr_side_reset [×N]            — FIFO reset sync [6]
├── tt_noc_sync3_pulse [×N]                         — 3-stage pulse sync [5]
├── tt_harvest_robust_sync [×N]                     — Harvest sync [10]
└── tt_niu_mst_timeout [×N]                         — AXI master timeout [4]
```

---

## 8. Endpoint Map

[NOT IN KB]

---

## 9. Inter-column Repeaters

`tt_noc_repeaters_cardinal` — connects input/output NoC packages, cardinal directions, multiple instances [2],[11],[12]. Y=3/Y=4 placement: [NOT IN KB].

| Supporting Module | Function | Source |
|-------------------|----------|--------|
| `tt_skid_buffer_new_assertion_off` | I/O decoupling | [7] |
| `tt_noc_secded_chk_corr_116_10` | ECC at hops | [8] |
| `tt_upf_async_fifo` | CDC crossing | [3] |

---

## 10. Key Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| DATA_WIDTH | 116 | [8] |
| ECC_WIDTH | 10 | [8] |
| TABLE_DEPTH | 1024 | [1] |
| TABLE_WIDTH | 32 | [1] |
| Others | [NOT IN KB] | — |

---

**Search:** topic=NoC, 14 results (1 hdd + 13 claims). *KB-only.*

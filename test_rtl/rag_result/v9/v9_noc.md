# NoC Fabric — Hardware Design Document

**Pipeline ID:** tt_20260221
**RAG Version:** v9
**Generated:** 2026-05-06

---

## 1. Overview

The Trinity NoC (Network-on-Chip) implements a 2D mesh topology connecting all 20 nodes in the 4×5 grid. It supports three routing algorithms: DIM_ORDER, TENDRIL, and DYNAMIC (enabled via `EnableDynamicRouting = 1`).

---

## 2. Routing Algorithms

| Algorithm | Type | Description |
|-----------|------|-------------|
| DIM_ORDER | Deterministic | XY dimension-ordered routing |
| TENDRIL | Adaptive | Adaptive routing with congestion awareness |
| DYNAMIC | Dynamic | Fully dynamic routing (EnableDynamicRouting=1) |

---

## 3. Router Module Hierarchy

Key NoC modules identified:

| Module | Function |
|--------|----------|
| `tt_noc_repeaters_cardinal` | Inter-column signal repeater |
| `noc_arbiter_tree` | Tree-based priority arbitration |
| `tt_noc_secded_chk_corr_116_10` | SECDED ECC (116-bit data, 10-bit check) |
| `tt_noc_sync3_pulse` | 3-stage pulse synchronizer (CDC) |
| `tt_noc_async_fifo_wr_side_reset` | Async FIFO reset generation |
| `tt_upf_async_fifo` | Asynchronous FIFO (multi-clock) |
| `tt_skid_buffer_new_assertion_off` | Skid buffer (decoupling) |
| `tt_harvest_robust_sync` | Robust harvest synchronizer |
| `tt_niu_mst_timeout` | NIU master timeout with IRQ |

---

## 4. Repeaters

`tt_noc_repeaters_cardinal` connects input and output NoC packages, providing signal regeneration for inter-column communication.

---

## 5. Arbitration

`noc_arbiter_tree` implements tree-based arbitration granting access to multiple requestors based on priority scheme. Multiple instances are used throughout the NoC fabric.

---

## 6. Error Protection

`tt_noc_secded_chk_corr_116_10`:
- Single-bit Error Correction, Double-bit Error Detection (SECDED)
- 116-bit data width
- 10-bit check bits

---

## 7. Clock Domain Crossing

| Module | Function |
|--------|----------|
| `tt_noc_sync3_pulse` | 3-stage pulse synchronizer between clock domains |
| `tt_noc_async_fifo_wr_side_reset` | Reset generation for async FIFO write/read sides |
| `tt_upf_async_fifo` | Asynchronous FIFO with independent write/read clocks |

---

## 8. Security

`tt_noc_sec_fence_edc_wrapper` (referenced in architecture):
- SMN group-based access control
- Security fence for EDC ring protection

---

## 9. NIU (Network Interface Unit)

`tt_niu_mst_timeout`:
- Configurable timeout period
- Generates interrupt and timeout signal on expiry
- Prevents hung transactions on AXI bus

---

## 10. Key Parameters (from trinity_pkg.sv)

| Parameter | Value | Relevance |
|-----------|-------|-----------|
| NumAxes | 2 | X and Y routing axes |
| NumDirections | 2 | Forward/backward per axis |
| EnableDynamicRouting | 1'b1 | Dynamic routing active |
| NumNoc2Axi | 4 | NIU bridge count |
| NumNodes | 20 | Total routable nodes |

---

*Generated from RAG v9 pipeline (tt_20260221).*

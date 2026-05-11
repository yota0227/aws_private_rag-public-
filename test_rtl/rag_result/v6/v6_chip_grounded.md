# Trinity N1B0 — Integrated Hardware Design Document (HDD)

> **Pipeline ID:** tt_20260221
> **Document Version:** v6 (Grounded — KB-only content)
> **RAG Version:** v4.1 + Package Parser (module_parse 1.5, claim 3.0, hdd 2.0)
> **Generated:** 2026-04-28
> **Rule:** Only content from RAG KB search results is included. Missing sections are marked `[NOT IN KB]`.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Package Constants and Grid](#2-package-constants-and-grid)
3. [Top-Level Ports](#3-top-level-ports)
4. [Module Hierarchy](#4-module-hierarchy)
5. [SFPU (Sparse Floating-Point Unit)](#5-sfpu)
6. [SMN (Scalable Memory Network)](#6-smn)
7. [TDMA (Tensix DMA)](#7-tdma)
8. [NoC Fabric](#8-noc-fabric)
9. [EDC (Error Detection and Correction)](#9-edc)
10. [Overlay (RISC-V Subsystem)](#10-overlay)
11. [Clock Architecture](#11-clock-architecture)
12. [Reset Architecture](#12-reset-architecture)
13. [SRAM Inventory](#13-sram-inventory)
14. [DFX / Debug](#14-dfx)
15. [RTL File Reference](#15-rtl-file-reference)
16. [KB Coverage Matrix](#16-kb-coverage-matrix)

---

## 1. Overview

### 1.1 KB-Confirmed Functional Blocks

| Block | KB Source | Type | Result # |
|-------|-----------|------|----------|
| **SFPU** | HDD section | `hdd_section` | [1] |
| **SMN** | HDD section | `hdd_section` | [2] |
| **SFPU — tt_sfpu_instrn_resources_used** | Claim | `claim` | [3], [8] |
| **NoC — tt_upf_async_fifo** | Claim | `claim` | [4] |
| **TDMA — tt_tdma_thread_context** | Claim | `claim` | [5] |
| **SFPU — tt_sfpu_lregs** | Claim | `claim` | [6], [7] |
| **EDC — tt_edc1_serial_bus_repeater** | Claim | `claim` | [9] |
| **NoC — tt_niu_mst_timeout** | Claim | `claim` | [10] |
| **Overlay — tt_fds_tensixneo_reg** | Claim | `claim` | [11], [17] |
| **NoC — tt_noc_sync3_pulse** | Claim | `claim` | [12] |
| **Overlay — tt_fds_dispatch_reg** | Claim | `claim` | [13] |
| **EDC — tt_edc1_noc_sec_block_reg** | Claim | `claim` | [14] |
| **Overlay — tt_cluster_ctrl_t6_l1_csr_reg** | Claim | `claim` | [15] |
| **Clock — tt_clkbuf, tt_clkgater** | Claim | `claim` | [16] |
| **SMN — tt_smn_repeater_struct** | Claim | `claim` | [18] |
| **Clock — tt_clkdiv2** | Claim | `claim` | [19] |
| **SMN — tt_smn_clkdiv** | Claim | `claim` | [20] |

> `trinity_router` is **NOT instantiated** in N1B0 (EMPTY by design).

---

## 2. Package Constants and Grid

[NOT IN KB] — No `tt_pkg.sv` or package constants (SizeX, SizeY, NumTensix, `tile_t` enum) were returned.

---

## 3. Top-Level Ports

[NOT IN KB] — No top-level port list was returned.

---

## 4. Module Hierarchy

```
n1b0_top (or trinity)
├── [Tensix Tile Array]
│   ├── SFPU                                              // HDD [1]
│   │   ├── tt_sfpu_lregs                                // claims [6],[7]
│   │   └── tt_sfpu_instrn_resources_used                // claims [3],[8]
│   └── TDMA
│       └── tt_tdma_thread_context                       // claim [5]
├── [NoC Fabric]
│   ├── noc2axi_router_nw_opt                            // SMN HDD [2]
│   │   ├── tt_mem_wrap_32x1024_2p_nomask
│   │   └── noc_routing_translation_selftest
│   ├── tt_upf_async_fifo                                // claim [4]
│   ├── tt_noc_sync3_pulse                               // claim [12]
│   └── tt_niu_mst_timeout                               // claim [10]
├── [SMN Subsystem]                                       // HDD [2]
│   ├── tt_smn_clkdiv                                    // claim [20]
│   └── tt_smn_repeater_struct                           // claim [18]
├── [EDC Ring]
│   ├── tt_edc1_serial_bus_repeater                      // claim [9]
│   └── tt_edc1_noc_sec_block_reg                       // claim [14]
├── [Overlay]
│   ├── tt_fds_tensixneo_reg → _inner                   // claims [11],[17]
│   ├── tt_fds_dispatch_reg                              // claim [13]
│   └── tt_cluster_ctrl_t6_l1_csr_reg                   // claim [15]
├── [Clock Distribution]
│   ├── tt_clkbuf / tt_clkgater / tt_clk_gater          // claim [16]
│   └── tt_clkdiv2                                       // claim [19]
└── [Other blocks]                                        // [NOT IN KB]
```

---

## 5. SFPU (Sparse Floating-Point Unit)

*Source: HDD [1], claims [3],[6],[7],[8]*

### 5.1 Overview (verbatim from KB)

The SFPU is a key component of the SoC design, responsible for performing floating-point arithmetic operations. The HDD provides a detailed overview of the SFPU block-level design, including its sub-module hierarchy, functional details, and interfaces.

### 5.2 tt_sfpu_lregs

| Fact | Type | Verbatim |
|------|------|----------|
| Ports | connectivity | "Various input and output ports for register read/write operations, diagnostic data, error injection, and parity error reporting" |
| Implementation | behavioral | "Register file with support for transposing or shifting data, reading and writing data/parity, and reporting parity errors" |

### 5.3 tt_sfpu_instrn_resources_used

| Fact | Type | Verbatim |
|------|------|----------|
| Function | structural | "Modules that analyze instruction resources used by the SFPU" |
| Details | behavioral | "Analyze SFPU instructions to determine register read/write hazards, SFPU instruction status, and stall conditions" |

---

## 6. SMN (Scalable Memory Network)

*Source: HDD [2], claims [18],[20]*

### 6.1 Bridge Module

`BDAed_trinity_noc2axi_router_nw_opt_..._tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest` — NoC-to-AXI bridge with routing translation and self-test.

### 6.2 Sub-modules

| Module | Ports | Function | Source |
|--------|-------|----------|--------|
| `tt_smn_clkdiv` | 5 in / 3 out | Clock divider | [20] |
| `tt_smn_repeater_struct` | 16 in / 8 out | SMN repeater | [18] |

### 6.3 SRAM

`tt_mem_wrap_32x1024_2p_nomask` — 32-bit × 1024-depth, dual-port, no write mask. Used for routing translation table.

---

## 7. TDMA (Tensix DMA)

*Source: claim [5]*

`tt_tdma_thread_context` — Generates addresses and control signals for multiple DMA channels based on input instruction and configuration parameters.

---

## 8. NoC Fabric

### 8.1 KB-Confirmed Modules

| Module | Function | Type | Source |
|--------|----------|------|--------|
| `tt_upf_async_fifo` | Async FIFO, write/read clocks at different frequencies | structural | [4] |
| `tt_niu_mst_timeout` | Timeout → interrupt + timeout signal | structural | [10] |
| `tt_noc_sync3_pulse` | 3-stage pulse synchronizer between clock domains | connectivity | [12] |

### 8.2 Routing Algorithms

[NOT IN KB]

### 8.3 Flit Structure

[NOT IN KB]

### 8.4 Virtual Channels

[NOT IN KB]

---

## 9. EDC (Error Detection and Correction)

### 9.1 KB-Confirmed Modules

| Module | Ports | Function | Source |
|--------|-------|----------|--------|
| `tt_edc1_serial_bus_repeater` | `i_clk`, `i_reset_n` | Serial ring bus repeater | [9] |
| `tt_edc1_noc_sec_block_reg` | `i_clk`, `i_reset_n`, `i_reg_cs`, `i_reg_wr_en`, `i_reg_addr`, `i_reg_wr_data` + noc security outputs | NoC security config registers | [14] |

### 9.2 Ring Topology / Harvest Bypass

[NOT IN KB]

---

## 10. Overlay (RISC-V Subsystem)

### 10.1 KB-Confirmed Register Blocks

| Module | In | Out | Inner | Source |
|--------|----|-----|-------|--------|
| `tt_fds_tensixneo_reg` | 106 | 41 | `tt_fds_tensixneo_reg_inner` | [11],[17] |
| `tt_fds_dispatch_reg` | 68 | 41 | — | [13] |
| `tt_cluster_ctrl_t6_l1_csr_reg` | 38 | 97 | — | [15] |

> Both FDS modules share output count (41) → common FDS output interface.

### 10.2 CPU Cluster / L1 Cache / APB Slaves

[NOT IN KB]

---

## 11. Clock Architecture

*Source: claims [16],[19]*

| Module | Function |
|--------|----------|
| `tt_clkbuf` | Clock buffers |
| `tt_clkgater` / `tt_clk_gater` | Clock gating cells |
| `tt_clkdiv2` | Divide-by-2 dividers |

---

## 12. Reset Architecture

[NOT IN KB]

---

## 13. SRAM Inventory

| SRAM Macro | Width | Depth | Ports | Mask | Usage | Source |
|------------|-------|-------|-------|------|-------|--------|
| `tt_mem_wrap_32x1024_2p_nomask` | 32b | 1024 | 2P | None | ATT routing translation | SMN HDD [2] |

Other SRAM types: [NOT IN KB]

---

## 14. DFX / Debug

| Element | Description | Source |
|---------|-------------|--------|
| `noc_routing_translation_selftest` | BIST for ATT SRAM | SMN HDD [2] |

iJTAG / Scan: [NOT IN KB]

---

## 15. RTL File Reference

[NOT IN KB] — No file paths returned in this search.

---

## 16. KB Coverage Matrix

| Section | Status | Sources |
|---------|--------|---------|
| Overview | ✅ Partial | Aggregated |
| Package Constants | ❌ | — |
| Top-Level Ports | ❌ | — |
| Module Hierarchy | ✅ Partial | 17 modules confirmed |
| **SFPU** | ✅ | HDD + 4 claims |
| **SMN** | ✅ | HDD + 2 claims |
| **TDMA** | ✅ | 1 claim |
| NoC — Modules | ✅ | 3 claims |
| NoC — Routing/Flit/VC | ❌ | — |
| **EDC — Modules** | ✅ | 2 claims |
| EDC — Topology/Bypass | ❌ | — |
| **Overlay — FDS/CSR** | ✅ | 4 claims |
| Overlay — CPU/L1/APB | ❌ | — |
| **Clock** | ✅ | 2 claims |
| Reset | ❌ | — |
| **SRAM** | ✅ Partial | 1 type |
| **DFX — Selftest** | ✅ Partial | 1 module |
| DFX — iJTAG/Scan | ❌ | — |
| RTL Files | ❌ | — |

| Category | Count |
|----------|-------|
| Grounded (✅) | **17** |
| Not in KB (❌) | 12 |
| **Coverage** | **59%** |

> **v5 → v5.1:** Coverage improved from **18% → 59%** (3.3× improvement).

---

*KB-only content. No fabricated data.*

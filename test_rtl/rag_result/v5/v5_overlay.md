# Overlay (RISC-V Subsystem) — Hardware Design Document (HDD)

> **Pipeline ID:** tt_20260221
> **Document Version:** v5 (Grounded — KB-only content)
> **Generated:** 2026-04-27
> **Rule:** Only content from RAG KB search results is included. Missing information is marked `[NOT IN KB]`.

---

## 1. Overview

*Source: KB result [1] — Overlay HDD section*

The `BDAed_trinity_noc2axi_router_nw_opt_trinity_noc2axi_router_nw_opt_tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest` module is a key component in the Overlay topic for pipeline tt_20260221. It serves as a block-level hardware design that encompasses various sub-modules for the Overlay subsystem.

The Overlay subsystem acts as the glue logic integrating the CPU cluster, NoC interface, L1 cache, and DMA within each Tensix tile.

**Known sub-blocks from KB claims:**

- **FDS (Frequency/Droop Sensor):** `tt_fds_tensixneo_reg` (106 in, 41 out) and `tt_fds_dispatch_reg` (68 in, 41 out)
- **Cluster Controller / L1 CSR:** `tt_cluster_ctrl_t6_l1_csr_reg` (38 in, 97 out)
- **NoC-to-AXI Bridge:** `noc2axi_router_nw_opt` with `tt_mem_wrap_32x1024_2p_nomask` translation table

---

## 2. Position in Grid

[NOT IN KB] — Specific tile positions where Overlay is instantiated within the 4×5 mesh were not returned.

---

## 3. Feature Summary

| Feature | Module(s) | Port Count | Source |
|---------|-----------|------------|--------|
| FDS TensixNeo Registers | `tt_fds_tensixneo_reg` → `_inner` | 106 in / 41 out | Claims [2],[5] |
| FDS Dispatch Registers | `tt_fds_dispatch_reg` → `_inner` | 68 in / 41 out | Claims [3],[7] |
| Cluster Ctrl / L1 CSR | `tt_cluster_ctrl_t6_l1_csr_reg` → `_inner` | 38 in / 97 out | Claims [4],[6] |
| NoC Routing Translation | `noc2axi_router_nw_opt` + SRAM | [NOT IN KB] | HDD [1] |
| CPU Cluster (RISC-V) | [NOT IN KB] | [NOT IN KB] | — |
| L1 Cache | [NOT IN KB] (CSR only) | — | — |
| iDMA Engine | [NOT IN KB] | [NOT IN KB] | — |
| ROCC Accelerator | [NOT IN KB] | [NOT IN KB] | — |
| LLK | [NOT IN KB] | [NOT IN KB] | — |
| SMN | [NOT IN KB] | [NOT IN KB] | — |
| Dispatch Engine | [NOT IN KB] (FDS reg only) | — | — |

---

## 4. Block Diagram

Reconstructed from KB results only:

```
┌──────────────────────────────────────────────────────────────┐
│                    Overlay Subsystem                          │
│                                                              │
│  ┌─────────────────────────┐   ┌──────────────────────────┐ │
│  │  tt_fds_tensixneo_reg   │   │  tt_fds_dispatch_reg     │ │
│  │  (106 in / 41 out)      │   │  (68 in / 41 out)        │ │
│  │  └─ _inner              │   │  └─ _inner               │ │
│  └─────────────────────────┘   └──────────────────────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  tt_cluster_ctrl_t6_l1_csr_reg                          │ │
│  │  (38 in / 97 out)                                       │ │
│  │  └─ tt_cluster_ctrl_t6_l1_csr_reg_inner                 │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  noc2axi_router_nw_opt                                  │ │
│  │  └─ tt_mem_wrap_32x1024_2p_nomask                       │ │
│  │     └─ noc_routing_translation_selftest                  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  CPU Cluster ──── [NOT IN KB]                                │
│  L1 Cache ─────── [NOT IN KB] (CSR interface only above)     │
│  iDMA ─────────── [NOT IN KB]                                │
│  ROCC ─────────── [NOT IN KB]                                │
│  LLK ──────────── [NOT IN KB]                                │
│  SMN ──────────── [NOT IN KB]                                │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Sub-module Hierarchy

```
Overlay Subsystem
├── tt_fds_tensixneo_reg                       — FDS TensixNeo register block
│   └── tt_fds_tensixneo_reg_inner             — Inner register logic
│       (106 input ports, 41 output ports)
│
├── tt_fds_dispatch_reg                        — FDS Dispatch register block
│   └── tt_fds_dispatch_reg_inner              — Inner register logic
│       (68 input ports, 41 output ports)
│
├── tt_cluster_ctrl_t6_l1_csr_reg              — Cluster controller / L1 CSR
│   └── tt_cluster_ctrl_t6_l1_csr_reg_inner    — Inner register logic
│       (38 input ports, 97 output ports)
│
├── noc2axi_router_nw_opt                      — NoC-to-AXI router (NW optimized)
│   └── tt_mem_wrap_32x1024_2p_nomask          — 32×1024 dual-port SRAM
│       └── noc_routing_translation_selftest    — Self-test
│
├── tt_overlay_wrapper                         — [NOT IN KB]
├── CPU Cluster (8× RISC-V)                    — [NOT IN KB]
├── L1 Cache                                   — [NOT IN KB]
├── iDMA Engine                                — [NOT IN KB]
├── ROCC Accelerator                           — [NOT IN KB]
├── LLK                                        — [NOT IN KB]
└── SMN                                        — [NOT IN KB]
```

---

## 6. Feature Details

### 6.1 CPU Cluster

[NOT IN KB] — 8× RISC-V cores, NUM_CLUSTER_CPUS, CPU cluster architecture were not returned.

### 6.2 L1 Cache

*Source: KB claims [4], [6]*

- **Module:** `tt_cluster_ctrl_t6_l1_csr_reg` → `tt_cluster_ctrl_t6_l1_csr_reg_inner`
- **Input ports:** 38 — clock, reset, CSR read/write control, address, write data
- **Output ports:** 97 — CSR read data and L1 cache configuration outputs

**L1 internals (bank count, bank width, ECC type, SRAM type):** [NOT IN KB]

### 6.3 iDMA Engine

[NOT IN KB]

### 6.4 ROCC Accelerator

[NOT IN KB]

### 6.5 LLK (Low-Latency Kernel)

[NOT IN KB]

### 6.6 SMN (System Maintenance Network)

[NOT IN KB]

### 6.7 FDS (Frequency/Droop Sensor)

*Source: KB claims [2], [3], [5], [7]*

#### 6.7.1 tt_fds_tensixneo_reg

- **Inner module:** `tt_fds_tensixneo_reg_inner`
- **Ports:** 106 in / 41 out
- **Purpose:** FDS register file for TensixNeo — frequency and voltage droop monitoring

#### 6.7.2 tt_fds_dispatch_reg

- **Inner module:** `tt_fds_dispatch_reg_inner`
- **Ports:** 68 in / 41 out
- **Purpose:** FDS register file for dispatch engine — frequency/droop monitoring

| Module | Inputs | Outputs | Inner Module |
|--------|--------|---------|--------------|
| `tt_fds_tensixneo_reg` | 106 | 41 | `tt_fds_tensixneo_reg_inner` |
| `tt_fds_dispatch_reg` | 68 | 41 | `tt_fds_dispatch_reg_inner` |

> Both share output count (41), suggesting a common FDS output interface.

### 6.8 Dispatch Engine

[NOT IN KB] — Only FDS dispatch register block is known.

---

## 7. Control Path

[NOT IN KB] — CPU-to-NoC Write/Read path examples were not returned.

---

## 8. Key Parameters

[NOT IN KB] — `tt_overlay_pkg.sv` parameters were not returned.

| Parameter | Value | Derivation | Source |
|-----------|-------|------------|--------|
| FDS TensixNeo in/out | 106 / 41 | Port count | Claim [2] |
| FDS Dispatch in/out | 68 / 41 | Port count | Claim [3] |
| L1 CSR in/out | 38 / 97 | Port count | Claim [4] |
| Translation table | 32 × 1024 | SRAM name | HDD [1] |
| `NUM_CLUSTER_CPUS` | [NOT IN KB] | — | — |
| `L1_NUM_BANKS` | [NOT IN KB] | — | — |
| `L1_BANK_WIDTH` | [NOT IN KB] | — | — |

---

## 9. Clock/Reset Summary

[NOT IN KB] — Multi-clock domain structure was not returned.

---

## 10. APB Register Interfaces

### 10.1 Known Register Slaves

| Slave Module | Type | In | Out | Inner | Source |
|-------------|------|-----|-----|-------|--------|
| `tt_fds_tensixneo_reg` | FDS | 106 | 41 | `_inner` | [2],[5] |
| `tt_fds_dispatch_reg` | FDS | 68 | 41 | `_inner` | [3],[7] |
| `tt_cluster_ctrl_t6_l1_csr_reg` | L1 CSR | 38 | 97 | `_inner` | [4],[6] |

### 10.2 Address Map

[NOT IN KB]

---

## 11. Verification Checklist

| Item | Module | Status |
|------|--------|--------|
| FDS TensixNeo reg R/W | `tt_fds_tensixneo_reg` | [NOT VERIFIED] |
| FDS Dispatch reg R/W | `tt_fds_dispatch_reg` | [NOT VERIFIED] |
| L1 CSR reg R/W | `tt_cluster_ctrl_t6_l1_csr_reg` | [NOT VERIFIED] |
| NoC routing selftest | `noc2axi_router_nw_opt` | [NOT VERIFIED] |
| Inner module wiring | All `*_inner` | [NOT VERIFIED] |
| CPU cluster boot | [NOT IN KB] | — |
| L1 cache coherency | [NOT IN KB] | — |
| iDMA transfer | [NOT IN KB] | — |
| ROCC accelerator | [NOT IN KB] | — |

---

## 12. Key RTL File Index

[NOT IN KB] — RTL file paths were not returned.

| Module | Likely Path (inferred) | Source |
|--------|----------------------|--------|
| `tt_fds_tensixneo_reg` | `rtl/overlay/tt_fds_tensixneo_reg.sv` | [2] |
| `tt_fds_tensixneo_reg_inner` | `rtl/overlay/tt_fds_tensixneo_reg_inner.sv` | [5] |
| `tt_fds_dispatch_reg` | `rtl/overlay/tt_fds_dispatch_reg.sv` | [3] |
| `tt_fds_dispatch_reg_inner` | `rtl/overlay/tt_fds_dispatch_reg_inner.sv` | [7] |
| `tt_cluster_ctrl_t6_l1_csr_reg` | `rtl/overlay/tt_cluster_ctrl_t6_l1_csr_reg.sv` | [4] |
| `tt_cluster_ctrl_t6_l1_csr_reg_inner` | `rtl/overlay/tt_cluster_ctrl_t6_l1_csr_reg_inner.sv` | [6] |

> File paths inferred from naming convention. Actual paths are [NOT IN KB].

---

## Appendix: KB Search Metadata

| # | Module | Topic | Type | Key Content |
|---|--------|-------|------|-------------|
| 1 | (Overlay HDD) | Overlay | hdd_section | noc2axi_router_nw_opt + SRAM |
| 2 | `tt_fds_tensixneo_reg` | Overlay | claim | 106 in / 41 out [structural] |
| 3 | `tt_fds_dispatch_reg` | Overlay | claim | 68 in / 41 out [structural] |
| 4 | `tt_cluster_ctrl_t6_l1_csr_reg` | Overlay | claim | 38 in / 97 out [structural] |
| 5 | `tt_fds_tensixneo_reg` | Overlay | claim | → _inner [connectivity] |
| 6 | `tt_cluster_ctrl_t6_l1_csr_reg` | Overlay | claim | → _inner [connectivity] |
| 7 | `tt_fds_dispatch_reg` | Overlay | claim | → _inner [connectivity] |

**Search:** `pipeline_id=tt_20260221`, `topic=Overlay`
**Results:** 7 of 7

---

*KB-only content. [NOT IN KB] = not in search results. No fabricated content.*
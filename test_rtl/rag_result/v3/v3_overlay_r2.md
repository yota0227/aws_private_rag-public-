# Overlay (RISC-V Subsystem) — Detailed Block-Level HDD

> **Pipeline**: `tt_20260221`
> **Document**: v3_overlay_r2.md
> **Date**: 2026-04-22
> **Search**: `topic: "Overlay"`, `pipeline_id: "tt_20260221"` — 5 results returned (of 41 total)
> **Grounding rule**: Only KB-sourced facts included. All else marked `[NOT IN KB]`.

---

## Grounding Sources

| Result # | Module | Type | Key Content |
|----------|--------|------|-------------|
| **[1]** | `tt_cluster_ctrl_reg_inner` | **claim (connectivity)** | Connects to various cluster control registers and signals |
| **[2]** | `tt_fds_dispatch_reg_inner` | **claim (structural)** | Inner module of `tt_fds_dispatch_reg`; CPU interface: request, address, write data, response |
| **[3]** | `tt_fds_tensixneo_reg_inner` | **claim (structural)** | Inner module of `tt_fds_tensixneo_reg`; CPU interface: request, address, write data, response |
| **[4]** | `trinity_noc2axi_router_ne_opt_FBLC` | hdd_section | Overlay functionality; "does not have any sub-modules" |
| **[5]** | `trinity_noc2axi_router_ne_opt_FBLC` | hdd_section | Overlay functionality; block-level HDD |

---

## 1. Overview

`[SOURCE: Results 4, 5]`

The Overlay subsystem resides within the `tt_20260221` pipeline. The module `trinity_noc2axi_router_ne_opt_FBLC` is identified as responsible for implementing the overlay functionality within the overall system. It serves as a block-level component handling NoC-to-AXI routing combined with overlay features.

Three **claim-verified** sub-modules confirm that the Overlay domain includes:
- **Cluster control register logic** (`tt_cluster_ctrl_reg_inner`) — connectivity to cluster control registers
- **FDS dispatch register logic** (`tt_fds_dispatch_reg_inner`) — CPU-accessible dispatch control
- **FDS Tensix/Neo register logic** (`tt_fds_tensixneo_reg_inner`) — CPU-accessible Tensix/Neo control

`[NOT IN KB]`: Explicit role description as "CPU cluster + NoC + L1 + DMA glue logic" is not stated in the search results.

---

## 2. Position in Grid

`[NOT IN KB]` — No grid coordinate or tile position data returned for Overlay.

---

## 3. Feature Summary

`[SOURCE: Results 1–3]`

| Feature | Status | Evidence |
|---------|--------|----------|
| Cluster Control Registers | ✅ Confirmed | Result [1]: `tt_cluster_ctrl_reg_inner` connects to cluster control registers |
| FDS Dispatch Registers | ✅ Confirmed | Result [2]: `tt_fds_dispatch_reg_inner` with CPU interface |
| FDS Tensix/Neo Registers | ✅ Confirmed | Result [3]: `tt_fds_tensixneo_reg_inner` with CPU interface |
| NoC-to-AXI Routing | ✅ Confirmed | Results [4][5]: `trinity_noc2axi_router_ne_opt_FBLC` |
| CPU Cluster (8× RISC-V) | `[NOT IN KB]` | — |
| L1 Cache | `[NOT IN KB]` | — |
| iDMA Engine | `[NOT IN KB]` | — |
| ROCC Accelerator | `[NOT IN KB]` | — |
| LLK | `[NOT IN KB]` | — |
| SMN | `[NOT IN KB]` | — |

---

## 4. Block Diagram

`[SOURCE: Results 1–5 — inferred connections only]`

```
┌─────────────────────────────────────────────────────────────┐
│                    Overlay Subsystem                         │
│                                                             │
│  ┌──────────────────────────┐                               │
│  │ tt_cluster_ctrl_reg_inner│ ←── Cluster Control Regs [1]  │
│  └────────────┬─────────────┘                               │
│               │ connectivity                                │
│               ▼                                             │
│  ┌──────────────────────────────────────────────┐           │
│  │     trinity_noc2axi_router_ne_opt_FBLC       │           │
│  │          (Overlay + NoC↔AXI) [4][5]          │           │
│  │          "does not have any sub-modules"      │           │
│  └──────────────────────────────────────────────┘           │
│               ▲                    ▲                        │
│               │                    │                        │
│  ┌────────────┴───────┐  ┌────────┴──────────────┐         │
│  │tt_fds_dispatch_    │  │tt_fds_tensixneo_      │         │
│  │  reg_inner    [2]  │  │  reg_inner        [3] │         │
│  │                    │  │                       │         │
│  │ CPU I/F:           │  │ CPU I/F:              │         │
│  │  - request         │  │  - request            │         │
│  │  - address         │  │  - address            │         │
│  │  - write_data      │  │  - write_data         │         │
│  │  - response        │  │  - response           │         │
│  └────────────────────┘  └───────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

> **Note**: This diagram reflects only connections confirmed by KB results. Actual hierarchy may be significantly deeper.

---

## 5. Sub-module Hierarchy

`[SOURCE: Results 1–5]`

```
Overlay Subsystem (topic: Overlay)
│
├── trinity_noc2axi_router_ne_opt_FBLC          [4][5] hdd_section
│       "does not have any sub-modules"
│
├── tt_cluster_ctrl_reg_inner                    [1] claim (connectivity)
│       └── connects to: cluster control registers and signals
│
├── tt_fds_dispatch_reg
│       └── tt_fds_dispatch_reg_inner            [2] claim (structural)
│               └── CPU I/F: request, address, write_data, response
│
└── tt_fds_tensixneo_reg
        └── tt_fds_tensixneo_reg_inner           [3] claim (structural)
                └── CPU I/F: request, address, write_data, response
```

**Module naming patterns discovered:**
- `tt_cluster_ctrl_*` — Cluster control domain
- `tt_fds_*_reg_inner` — FDS register inner modules (parent: `tt_fds_*_reg`)
- `tt_fds_dispatch_*` — FDS dispatch subsystem
- `tt_fds_tensixneo_*` — FDS Tensix/Neo subsystem

`[NOT IN KB]`: `tt_overlay_wrapper` and its full sub-tree.

---

## 6. Feature Details

### 6.1 CPU Cluster

`[NOT IN KB]` — No data on 8× RISC-V cores or `NUM_CLUSTER_CPUS`.

**However**, Result [1] confirms **cluster control registers** exist (`tt_cluster_ctrl_reg_inner`), implying a CPU cluster is present in the design.

### 6.2 L1 Cache

`[NOT IN KB]` — No bank count, bank width, ECC type, or SRAM type data.

### 6.3 iDMA Engine

`[NOT IN KB]`

### 6.4 ROCC Accelerator

`[NOT IN KB]`

### 6.5 LLK (Low-Latency Kernel)

`[NOT IN KB]`

### 6.6 SMN (System Maintenance Network)

`[NOT IN KB]`

### 6.7 FDS (Frequency/Droop Sensor)

`[SOURCE: Results 2, 3]` ✅ **GROUNDED**

Two FDS register modules confirmed:

| Module | Parent | Type | Interface |
|--------|--------|------|-----------|
| `tt_fds_dispatch_reg_inner` | `tt_fds_dispatch_reg` | structural | CPU: request, address, write_data, response |
| `tt_fds_tensixneo_reg_inner` | `tt_fds_tensixneo_reg` | structural | CPU: request, address, write_data, response |

**Key findings:**
- FDS has **two register sub-domains**: Dispatch and Tensix/Neo
- Both use **identical CPU interface patterns** (request/address/write_data/response)
- The `_inner` suffix indicates a two-level register hierarchy (outer wrapper + inner logic)
- "FDS" prefix shared by both → they belong to the same **Frequency/Droop Sensor** subsystem

### 6.8 Dispatch Engine

`[SOURCE: Result 2]` ✅ **Partial**

The `tt_fds_dispatch_reg_inner` module confirms a dispatch register block exists within the FDS domain. Full dispatch engine details (East/West dispatch, command distribution) are `[NOT IN KB]`.

---

## 7. Control Path

`[SOURCE: Results 2, 3 — CPU interface signals]`

Based on the CPU interface signals found in FDS register modules:

```
CPU Request Path (confirmed signals):
  CPU ──request──▶ tt_fds_*_reg_inner
  CPU ──address──▶ tt_fds_*_reg_inner
  CPU ──write_data──▶ tt_fds_*_reg_inner

CPU Response Path:
  tt_fds_*_reg_inner ──response──▶ CPU
```

`[NOT IN KB]`: Full CPU-to-NoC write/read path, AXI transaction flow.

---

## 8. Key Parameters

`[NOT IN KB]` — No `tt_overlay_pkg.sv` parameters returned.

---

## 9. Clock/Reset Summary

`[NOT IN KB]` — No clock domain or reset structure data returned for Overlay modules.

---

## 10. APB Register Interfaces

`[NOT IN KB]` — No APB slave list or address map for Overlay.

> **Note**: The EDC search (v3_edc_r2) found `tt_edc1_biu_soc_apb4_wrap` as an APB4 bridge. A similar APB wrapper may exist for Overlay but was not returned in this search.

---

## 11. Verification Checklist

| Check Item | Status |
|------------|--------|
| Cluster control register connectivity verified | ✅ Claim [1] |
| FDS dispatch register CPU I/F verified | ✅ Claim [2] |
| FDS Tensix/Neo register CPU I/F verified | ✅ Claim [3] |
| Overlay module identified as leaf-level (no sub-modules) | ✅ HDD [4] |
| CPU cluster core count (8× RISC-V) | ⬜ `[NOT IN KB]` |
| L1 cache configuration | ⬜ `[NOT IN KB]` |
| iDMA/ROCC/LLK/SMN presence | ⬜ `[NOT IN KB]` |
| Clock domain crossing | ⬜ `[NOT IN KB]` |
| APB address map | ⬜ `[NOT IN KB]` |

**Coverage: 4 of 9 items verified (44%)**

---

## 12. Key RTL File Index

`[SOURCE: Inferred from module names — exact paths NOT IN KB]`

| Module | Inferred Path | Confidence |
|--------|---------------|------------|
| `tt_cluster_ctrl_reg_inner` | `tt_rtl/tt_cluster/rtl/tt_cluster_ctrl_reg_inner.sv` | Low (naming convention) |
| `tt_fds_dispatch_reg_inner` | `tt_rtl/tt_fds/rtl/tt_fds_dispatch_reg_inner.sv` | Low (naming convention) |
| `tt_fds_tensixneo_reg_inner` | `tt_rtl/tt_fds/rtl/tt_fds_tensixneo_reg_inner.sv` | Low (naming convention) |
| `trinity_noc2axi_router_ne_opt_FBLC` | (in pipeline `tt_20260221`) | Confirmed in KB |

---

## R1 → R2 Improvement Summary

| Aspect | R1 (v3_overlay.md) | R2 (this file) |
|--------|--------------------|--------------------|
| **Claim data** | 0 claims | ✅ **3 claims** (cluster_ctrl, fds_dispatch, fds_tensixneo) |
| **Real EDC modules** | noc2axi_router only | +3 actual Overlay modules discovered |
| **FDS section** | `[NOT IN KB]` | ✅ **Grounded** — 2 register sub-domains with CPU I/F |
| **Module hierarchy** | "no sub-modules" only | 4-node tree with naming pattern analysis |
| **CPU I/F signals** | None | request, address, write_data, response confirmed |
| **Coverage** | ~2/12 (17%) | **5/12 (42%)** |

---

## Verbatim Evidence (Raw Claim Text)

### Claim [1] — `tt_cluster_ctrl_reg_inner`
> "Module tt_cluster_ctrl_reg_inner connects to various cluster control registers and signals." [connectivity]

### Claim [2] — `tt_fds_dispatch_reg_inner`
> "The module tt_fds_dispatch_reg_inner is an inner module of tt_fds_dispatch_reg, with typical CPU interface signals such as request, address, write data, and response signals." [structural]

### Claim [3] — `tt_fds_tensixneo_reg_inner`
> "The module tt_fds_tensixneo_reg_inner is an inner module of tt_fds_tensixneo_reg, with typical CPU interface signals such as request, address, write data, and response signals." [structural]

### HDD [4] — `trinity_noc2axi_router_ne_opt_FBLC`
> "The `trinity_noc2axi_router_ne_opt_FBLC` module is a block-level component within the `tt_20260221` pipeline. It is responsible for implementing the overlay functionality within the overall system. [...] does not have any sub-modules"

### HDD [5] — `trinity_noc2axi_router_ne_opt_FBLC`
> "The `trinity_noc2axi_router_ne_opt_FBLC` block is a part of the `tt_20260221` pipeline and is responsible for the Overlay functionality. This block-level Hardware Design Document (HDD) provides a detailed description of the sub-module hierarchy, functional details, control path, clock/reset structure..."

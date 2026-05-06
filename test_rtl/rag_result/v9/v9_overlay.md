# Overlay (RISC-V Subsystem) — Hardware Design Document

**Pipeline ID:** tt_20260221
**RAG Version:** v9
**Generated:** 2026-05-06

---

## 1. Overview

The Overlay subsystem serves as the CPU cluster glue logic, integrating RISC-V cores with NoC, L1 cache, DMA, and dispatch interfaces. It occupies specific tile positions in the 4×5 mesh grid.

Key sub-modules:
- `tt_fds_tensixneo_reg` — Tensix Neo register file (106 inputs, 41 outputs)
- `tt_fds_dispatch_reg` — Dispatch register file (68 inputs, 41 outputs)
- `tt_cluster_ctrl_t6_l1_csr_reg` — Cluster control / L1 CSR registers (38 inputs, 97 outputs)

---

## 2. Module Hierarchy

```
tt_fds_tensixneo_reg
└── tt_fds_tensixneo_reg_inner

tt_fds_dispatch_reg
└── tt_fds_dispatch_reg_inner

tt_cluster_ctrl_t6_l1_csr_reg
└── tt_cluster_ctrl_t6_l1_csr_reg_inner
```

---

## 3. Feature Details

### 3.1 FDS (Frequency/Droop Sensor) Registers

| Module | Inputs | Outputs | Function |
|--------|--------|---------|----------|
| tt_fds_tensixneo_reg | 106 | 41 | Tensix Neo configuration registers |
| tt_fds_dispatch_reg | 68 | 41 | Dispatch configuration registers |

### 3.2 Cluster Control

`tt_cluster_ctrl_t6_l1_csr_reg`:
- 38 input ports, 97 output ports
- L1 cache CSR (Control/Status Register) management
- Cluster-level configuration

---

## 4. Key Parameters

From trinity_pkg.sv:
- `DMCoresPerCluster = 8` — 8 DM cores per cluster (RISC-V)
- `NumDmComplexes = 14` — 14 DM complexes total
- `TensixPerCluster = 4` — 4 Tensix tiles per cluster

---

## 5. Clock/Reset

The Overlay operates in the DM clock domain:
- `i_dm_clk [SizeX-1:0]` — Per-column DM clock
- `i_dm_core_reset_n [NumDmComplexes-1:0][DMCoresPerCluster-1:0]` — Per-core reset (14×8)
- `i_dm_uncore_reset_n [NumDmComplexes-1:0]` — Per-complex uncore reset

---

*Generated from RAG v9 pipeline (tt_20260221).*

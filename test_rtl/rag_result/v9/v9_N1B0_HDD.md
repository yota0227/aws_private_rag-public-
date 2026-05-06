# Trinity N1B0 NPU — Integrated Hardware Design Document

**Pipeline ID:** tt_20260221
**RAG Version:** v9
**Generated:** 2026-05-06
**Type:** Integrated HDD (merged from topic-specific documents)

---

## 1. Overview

Trinity N1B0 is a Neural Processing Unit (NPU) SoC designed for AI/ML inference and training. The chip is organized as a 4×5 2D mesh grid of heterogeneous tiles interconnected by a Network-on-Chip (NoC) fabric.

- 20 nodes total (4 columns × 5 rows)
- 12 Tensix compute tiles
- 4 NoC-to-AXI bridges (NIU)
- 2 Dispatch engines (East/West)
- EDC ring topology for error management
- Multi-clock domain: AI, NoC, DM, AXI

---

## 2. Package Constants and Grid

Source: `rtl/targets/4x5/trinity_pkg.sv`

| Parameter | Value | Description |
|-----------|-------|-------------|
| SizeX | 4 | Grid columns |
| SizeY | 5 | Grid rows |
| NumNodes | 20 | Total grid nodes |
| NumTensix | 12 | Compute tiles |
| NumNoc2Axi | 4 | AXI bridge count |
| NumDispatch | 2 | Dispatch engines |
| NumApbNodes | 4 | APB register nodes |
| NumDmComplexes | 14 | DM complex count |
| EnableDynamicRouting | 1'b1 | Dynamic routing enabled |
| TensixPerCluster | 4 | Tensix per cluster |
| DMCoresPerCluster | 8 | DM cores per cluster |
| NumAxes | 2 | Routing axes |
| NumDirections | 2 | Directions per axis |

### Package Functions

- `bit isEastEdge(int x)` [automatic] — Returns x == SizeX - 1

---

## 3. Top-Level Ports

**106 total ports** (N1B0 variant, `used_in_n1/rtl/trinity.sv`):

| Category | Count | Key Signals |
|----------|-------|-------------|
| AXI_Interface | 39 | AXI slave/master bus |
| NoC_Clock_Reset | 2 | i_noc_clk, i_noc_reset_n |
| AI_Clock_Reset | 2 | i_ai_clk[3:0], i_ai_reset_n[3:0] |
| Tensix_Reset | 1 | i_tensix_reset_n[11:0] |
| EDC_APB | 16 | APB4 interface + 5 IRQs |
| DM_Clock_Reset | 3 | i_dm_clk[3:0], i_dm_core_reset_n[13:0][7:0], i_dm_uncore_reset_n[13:0] |
| APB_Register | 8 | Standard APB slave |
| SFR_Memory_Config | 17 | SRAM configuration |
| PRTN_Power | 14 | Power partition chain |
| Other | 4 | Miscellaneous |

---

## 4. Module Hierarchy

```
trinity (top)
├── tt_tensix_with_l1 [×12]
│   ├── FPU (tt_fp_max_array, tt_dual_align, tt_fpu_gtile_SDUMP_INTF)
│   ├── SFPU (tt_sfpu_lregs, tt_sfpu_instrn_resources_used)
│   ├── TDMA (tt_tdma_xy_address_controller, tt_tdma_thread_context, tt_tdma_rts_rtr_pipe_stage)
│   └── L1 Cache
├── tt_dispatch_top_inst_east (tt_dispatch_top_east)
├── tt_dispatch_top_inst_west (tt_dispatch_top_west)
├── edc_direct_conn_nodes (tt_edc1_intf_connector)
├── edc_loopback_conn_nodes (tt_edc1_intf_connector)
├── NoC Fabric
│   ├── tt_noc_repeaters_cardinal
│   ├── noc_arbiter_tree [×N]
│   ├── tt_noc_secded_chk_corr_116_10
│   ├── tt_noc_sync3_pulse
│   ├── tt_upf_async_fifo
│   ├── tt_skid_buffer_new_assertion_off
│   └── tt_harvest_robust_sync
└── NIU (tt_niu_mst_timeout)
```

Note: `trinity_router` is NOT instantiated in N1B0 (EMPTY by design).

---

## 5. Compute Tile (Tensix)

Each `tt_tensix_with_l1` contains:

| Sub-block | Key Modules | Function |
|-----------|-------------|----------|
| FPU | tt_fp_max_array, tt_dual_align | Floating-point operations |
| SFPU | tt_sfpu_lregs, tt_sfpu_instrn_resources_used | Sparse FP, hazard detection |
| TDMA | tt_tdma_xy_address_controller, tt_tdma_thread_context | DMA address gen, thread mgmt |
| L1 Cache | — | Local data storage |

12 tiles organized in clusters of 4 (TensixPerCluster = 4).

---

## 6. Dispatch Engine

| Instance | Module | Side |
|----------|--------|------|
| tt_dispatch_top_inst_east | tt_dispatch_top_east | East |
| tt_dispatch_top_inst_west | tt_dispatch_top_west | West |

---

## 7. NoC Fabric

### 7.1 Routing Algorithms

| Algorithm | Type | Description |
|-----------|------|-------------|
| DIM_ORDER | Deterministic | XY dimension-ordered |
| TENDRIL | Adaptive | Congestion-aware |
| DYNAMIC | Dynamic | EnableDynamicRouting=1 |

### 7.2 Key Modules

| Module | Function |
|--------|----------|
| tt_noc_repeaters_cardinal | Inter-column repeater |
| noc_arbiter_tree | Tree-based priority arbitration |
| tt_noc_secded_chk_corr_116_10 | SECDED ECC (116b data, 10b check) |
| tt_noc_sync3_pulse | 3-stage CDC pulse sync |
| tt_upf_async_fifo | Multi-clock async FIFO |
| tt_skid_buffer_new_assertion_off | Pipeline decoupling |
| tt_harvest_robust_sync | Robust harvest synchronizer |

### 7.3 NIU

- `tt_niu_mst_timeout` — Configurable timeout with IRQ generation

---

## 8. EDC (Error Detection and Correction)

### 8.1 Module Hierarchy

```
tt_edc1_biu_soc_apb4_wrap → edc1_biu_soc_apb4_inner
tt_edc1_noc_sec_block_reg → edc1_noc_sec_block_reg_inner
tt_edc1_serial_bus_repeater
tt_edc1_intf_connector
```

### 8.2 Ring Topology

- U-shape: Segment A (down) → U-turn → Segment B (up)
- Direct + loopback connection nodes
- Harvest bypass via mux/demux

### 8.3 IRQ Outputs

5 interrupt lines: fatal_err, crit_err, cor_err, pkt_sent, pkt_rcvd

---

## 9. Clock Architecture

| Clock | Width | Domain | Description |
|-------|-------|--------|-------------|
| i_axi_clk | 1 | AXI | Bus clock |
| i_noc_clk | 1 | NoC | Network clock |
| i_ai_clk | [3:0] | AI | Per-column compute clock |
| i_dm_clk | [3:0] | DM | Per-column data movement clock |

Clock infrastructure: `tt_clkbuf` (buffer), `tt_clkgater` / `tt_clk_gater` (gating)

---

## 10. Reset Architecture

| Reset | Width | Granularity |
|-------|-------|-------------|
| i_noc_reset_n | 1 | Global NoC |
| i_ai_reset_n | [3:0] | Per-column AI |
| i_tensix_reset_n | [11:0] | Per-tile Tensix |
| i_dm_core_reset_n | [13:0][7:0] | Per-core DM (14×8) |
| i_dm_uncore_reset_n | [13:0] | Per-complex DM uncore |
| i_edc_reset_n | 1 | EDC domain |

---

## 11. Power Management (PRTN)

- 4-column daisy-chain power partition
- ISO_EN[11:0] — 12 power island isolation enables
- PRTNUN protocol: FC2UN/UN2FC data/ready/clk/rstn signals
- DFT mode scan tie-low (TIEL_DFT_MODESCAN)

---

## 12. Overlay (RISC-V Subsystem)

| Module | Inputs | Outputs | Function |
|--------|--------|---------|----------|
| tt_fds_tensixneo_reg | 106 | 41 | Tensix Neo config registers |
| tt_fds_dispatch_reg | 68 | 41 | Dispatch config registers |
| tt_cluster_ctrl_t6_l1_csr_reg | 38 | 97 | L1 CSR / cluster control |

- DMCoresPerCluster = 8 (RISC-V cores per cluster)
- NumDmComplexes = 14

---

## 13. RTL File Reference

| File | Description |
|------|-------------|
| `rtl/trinity.sv` | Top-level module (75 ports, base) |
| `rtl/targets/4x5/trinity_pkg.sv` | Package constants |
| `used_in_n1/rtl/trinity.sv` | N1B0 variant (106 ports) |
| `used_in_n1/mem_port/rtl/trinity.sv` | N1B0 + memory port |
| `used_in_n1/legacy/no_mem_port/rtl/trinity.sv` | Legacy variant |

---

## Appendix: Source Traceability

| Section | Source Document |
|---------|----------------|
| 1. Overview | v9_chip_no_grounding (Prompt 1) |
| 2. Package Constants | v9_chip_no_grounding (Prompt 1) — SizeX search |
| 3. Top-Level Ports | v9_chip_no_grounding (Prompt 1) — trinity search |
| 4. Module Hierarchy | v9_chip_no_grounding (Prompt 1) — trinity module_parse |
| 5. Compute Tile | v9_chip_no_grounding (Prompt 1) — FPU/SFPU/TDMA HDD sections |
| 6. Dispatch | v9_chip_no_grounding (Prompt 1) |
| 7. NoC Fabric | v9_noc (Prompt 4) — NoC topic search |
| 8. EDC | v9_edc (Prompt 2) — EDC topic search |
| 9. Clock Architecture | v9_chip_no_grounding (Prompt 1) — Clock_Reset HDD |
| 10. Reset Architecture | v9_chip_no_grounding (Prompt 1) — port claims |
| 11. Power Management | v9_chip_no_grounding (Prompt 1) — PRTN claims |
| 12. Overlay | v9_overlay (Prompt 3) — Overlay topic search |
| 13. RTL Files | v9_chip_no_grounding (Prompt 1) — file_path fields |

---

*Integrated from v9_chip_no_grounding.md, v9_edc.md, v9_noc.md, v9_overlay.md*
*Generated from RAG v9 pipeline (tt_20260221).*

# N1B0 NPU — Full Hardware Design Document v0.1

**Chip:** N1B0 (Trinity variant for N1 SoC)
**Date:** 2026-03-18
**RTL baseline:** `/secure_data_from_tt/20260221/used_in_n1/`
**Status:** RTL-complete, pre-DFX insertion

---

## Table of Contents

1. [Overview](#1-overview)
2. [Package Constants and Grid](#2-package-constants-and-grid)
3. [Top-Level Ports](#3-top-level-ports)
4. [Module Hierarchy](#4-module-hierarchy)
5. [Compute Tile — Tensix](#5-compute-tile--tensix)
   - 5.1 TRISC / BRISC CPU Cluster
   - 5.2 FPU — G-Tile, M-Tile, FP Lanes
   - 5.3 SFPU
   - 5.4 TDMA
   - 5.5 L1 Cache / SRAM
   - 5.6 DEST Register File
   - 5.7 SRCB Register
6. [Dispatch Engine](#6-dispatch-engine)
7. [NoC Fabric](#7-noc-fabric)
8. [NIU — AXI Bridge Tiles](#8-niu--axi-bridge-tiles)
   - 8.1 Corner NIU (NE/NW_OPT)
   - 8.2 Composite NIU+Router (NOC2AXI_ROUTER_NE/NW_OPT)
   - 8.3 AXI Interface
   - 8.4 ATT and SMN Security
9. [Clock Architecture](#9-clock-architecture)
10. [Reset Architecture](#10-reset-architecture)
11. [EDC — Error Detection and Correction](#11-edc--error-detection-and-correction)
12. [Power Management — PRTN and ISO_EN](#12-power-management--prtn-and-iso_en)
13. [SRAM Inventory](#13-sram-inventory)
14. [DFX Hierarchy](#14-dfx-hierarchy)
15. [Physical / P&R Guide](#15-physical--pr-guide)
16. [SW Programming Guide](#16-sw-programming-guide)
17. [RTL File Reference](#17-rtl-file-reference)

---

## 1. Overview

N1B0 is the Trinity NPU integrated into the N1 SoC. It is a **4×5 tile mesh** containing 12 compute tiles (Tensix), 4 AXI bridge tiles (NIU/Router), 2 dispatch tiles, and 2 router placeholder tiles, connected by a 2D NoC fabric.

### 1.1 Key N1B0 Differences from Baseline Trinity

| Feature | Baseline Trinity | N1B0 |
|---------|-----------------|------|
| Grid | configurable | 4×5, fixed (SizeX=4, SizeY=5) |
| Middle-column NIU+Router (X=1,2) | `trinity_noc2axi_n_opt` + `trinity_router` (separate) | `trinity_noc2axi_router_ne/nw_opt` (combined dual-row) |
| AI/DM clock | single `i_ai_clk`, `i_dm_clk` | per-column `[SizeX]` arrays |
| X-axis NoC connections | generate loop | manual assigns with inter-column repeaters |
| Inter-column repeaters at Y=4 | none | 4-stage (×2 for E↔W) |
| Inter-column repeaters at Y=3 | none | 6-stage (×2 for E↔W) |
| PRTN chain | absent | 4-column daisy-chain |
| ISO_EN port | absent | `[11:0]` |
| AXI FIFO depth | fixed | `define-selectable (32–1024) |
| REP_DEPTH_LOOPBACK in router | 0 | 6 (added 2026-03-04) |

### 1.2 Block Diagram (Text)

```
         X=0              X=1                   X=2                  X=3
        ┌────────────┬─────────────────────────────────────┬────────────┐
Y=4:    │ NIU_NE     │ NIU_ROUTER_NE (Y=4)   NIU_ROUTER_NW │ NIU_NW     │  ← DRAM I/F
        │ EP=4       │ EP=9                  EP=14          │ EP=19      │
        ├────────────┼────────────────────────────────────  ┼────────────┤
Y=3:    │ DISP_E     │ [ROUTER placeholder]  [ROUTER phdr]  │ DISP_W     │  ← Dispatch
        │ EP=3       │ EP=8 (inside _NE_OPT) EP=13 (_NW_OPT)│ EP=18     │
        ├────────────┼────────────────────────────────────  ┼────────────┤
Y=2:    │ T6[0][2]   │ T6[1][2]              T6[2][2]       │ T6[3][2]   │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=1:    │ T6[0][1]   │ T6[1][1]              T6[2][1]       │ T6[3][1]   │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=0:    │ T6[0][0]   │ T6[1][0]              T6[2][0]       │ T6[3][0]   │
        └────────────┴─────────────────────────────────────-┴────────────┘
```

---

## 2. Package Constants and Grid

**File:** `used_in_n1/rtl/targets/4x5/trinity_pkg.sv`

### 2.1 Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `SizeX` | 4 | Columns |
| `SizeY` | 5 | Rows |
| `NumNodes` | 20 | Total tiles (SizeX × SizeY) |
| `NumTensix` | 12 | TENSIX tiles (rows Y=0..2, all X) |
| `NumNoc2Axi` | 4 | NOC2AXI tiles (row Y=4) |
| `NumDispatch` | 2 | Dispatch tiles (X=0 and X=3 at Y=3) |
| `NumApbNodes` | 4 | APB buses (one per column X) |
| `NumDmComplexes` | 14 | `NumTensix + NumDispatch` |
| `DMCoresPerCluster` | 8 | DM cores per tile |
| `EnableDynamicRouting` | 1 | Dynamic NoC routing enabled |

### 2.2 Tile Type Enum (`tile_t`, 3-bit)

| Value | Name | RTL Module | Position |
|-------|------|------------|----------|
| 3'd0 | `TENSIX` | `tt_tensix_with_l1` | Y=0..2, X=0..3 (12 tiles) |
| 3'd1 | `NOC2AXI_NE_OPT` | `trinity_noc2axi_ne_opt` | (X=0, Y=4) |
| 3'd2 | `NOC2AXI_ROUTER_NE_OPT` | `trinity_noc2axi_router_ne_opt` | (X=1, Y=4+Y=3) |
| 3'd3 | `NOC2AXI_ROUTER_NW_OPT` | `trinity_noc2axi_router_nw_opt` | (X=2, Y=4+Y=3) |
| 3'd4 | `NOC2AXI_NW_OPT` | `trinity_noc2axi_nw_opt` | (X=3, Y=4) |
| 3'd5 | `DISPATCH_E` | `tt_dispatch_top_east` | (X=3, Y=3) |
| 3'd6 | `DISPATCH_W` | `tt_dispatch_top_west` | (X=0, Y=3) |
| 3'd7 | `ROUTER` | (empty placeholder) | (X=1,2, Y=3) |

`ROUTER` at (X=1,2, Y=3) is a `tile_t` enum entry only. The `gen_router` generate block in `trinity.sv` is empty. Router logic is embedded inside `NOC2AXI_ROUTER_NE/NW_OPT`.

### 2.3 Endpoint Index Table

`EndpointIndex = x * SizeY + y = x*5 + y`

| X | Y | Tile | EP |
|---|---|------|----|
| 0 | 0 | TENSIX | 0 |
| 0 | 1 | TENSIX | 1 |
| 0 | 2 | TENSIX | 2 |
| 0 | 3 | DISPATCH_E | 3 |
| 0 | 4 | NOC2AXI_NE_OPT | 4 |
| 1 | 0 | TENSIX | 5 |
| 1 | 1 | TENSIX | 6 |
| 1 | 2 | TENSIX | 7 |
| 1 | 3 | ROUTER (placeholder) | 8 |
| 1 | 4 | NOC2AXI_ROUTER_NE_OPT | 9 |
| 2 | 0 | TENSIX | 10 |
| 2 | 1 | TENSIX | 11 |
| 2 | 2 | TENSIX | 12 |
| 2 | 3 | ROUTER (placeholder) | 13 |
| 2 | 4 | NOC2AXI_ROUTER_NW_OPT | 14 |
| 3 | 0 | TENSIX | 15 |
| 3 | 1 | TENSIX | 16 |
| 3 | 2 | TENSIX | 17 |
| 3 | 3 | DISPATCH_W | 18 |
| 3 | 4 | NOC2AXI_NW_OPT | 19 |

### 2.4 Helper Functions

| Function | Returns |
|----------|---------|
| `getTensixIndex(x,y)` | 0..11, scan-order X-major |
| `getNoc2AxiIndex(x,y)` | 0..3 for NOC2AXI tiles |
| `getApbIndex(x,y)` | column x (= APB bus number) |
| `getDmIndex(x,y)` | 0..13 for TENSIX + DISPATCH tiles |
| `isNorthEdge(y)` | y == SizeY-1 |
| `isSouthEdge(y)` | y == 0 |

---

## 3. Top-Level Ports

**Module:** `trinity`  **File:** `used_in_n1/rtl/trinity.sv`

### 3.1 Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `AXI_SLV_OUTSTANDING_READS` | 64 | Max in-flight AXI slave reads per NIU |
| `AXI_SLV_OUTSTANDING_WRITES` | 32 | Max in-flight AXI slave writes per NIU |
| `AXI_SLV_RD_RDATA_FIFO_DEPTH` | 512 | RDATA FIFO depth (32/64/128/256/512/1024 via `define) |

### 3.2 Clocks and Resets

| Port | Width | Description |
|------|-------|-------------|
| `i_axi_clk` | 1 | AXI clock — single global, for all NOC2AXI tiles |
| `i_noc_clk` | 1 | NoC clock — single global, bypasses column routing |
| `i_noc_reset_n` | 1 | NoC reset (active-low) |
| `i_ai_clk[3:0]` | 4 | AI clock — per column x (N1B0: was single clock in baseline) |
| `i_ai_reset_n[3:0]` | 4 | AI reset per column |
| `i_dm_clk[3:0]` | 4 | DM clock — per column x |
| `i_tensix_reset_n[11:0]` | 12 | Per-Tensix tile reset; index = `getTensixIndex(x,y)` |
| `i_dm_core_reset_n[13:0][7:0]` | 14×8 | DM core resets; outer index = `getDmIndex(x,y)` |
| `i_dm_uncore_reset_n[13:0]` | 14 | DM uncore resets |
| `i_edc_reset_n` | 1 | EDC ring reset; repurposed as `power_good` in clock_routing struct |

### 3.3 APB Register Interface (×4 columns)

| Port | Width×Count | Description |
|------|------------|-------------|
| `i_reg_psel[3:0]` | 1×4 | APB chip select per column |
| `i_reg_paddr[3:0]` | 32×4 | APB address |
| `i_reg_penable[3:0]` | 1×4 | APB enable |
| `i_reg_pwrite[3:0]` | 1×4 | APB write |
| `i_reg_pwdata[3:0]` | 32×4 | APB write data |
| `o_reg_prdata[3:0]` | 32×4 | APB read data |
| `o_reg_pready[3:0]` | 1×4 | APB ready |
| `o_reg_pslverr[3:0]` | 1×4 | APB slave error |

### 3.4 EDC APB Interface and IRQs (×4 columns)

| Port | Width×Count | Description |
|------|------------|-------------|
| `i_edc_apb_psel[3:0]` | 1×4 | EDC APB select |
| `i_edc_apb_paddr[3:0]` | 6×4 | EDC APB address (6-bit) |
| `i_edc_apb_pwdata[3:0]` | 32×4 | EDC APB write data |
| `i_edc_apb_pstrb[3:0]` | 4×4 | EDC APB byte strobe |
| `o_edc_apb_pready[3:0]` | 1×4 | EDC APB ready |
| `o_edc_apb_prdata[3:0]` | 32×4 | EDC APB read data |
| `o_edc_fatal_err_irq[3:0]` | 1×4 | EDC fatal error interrupt |
| `o_edc_crit_err_irq[3:0]` | 1×4 | EDC critical error interrupt |
| `o_edc_cor_err_irq[3:0]` | 1×4 | EDC correctable error interrupt |
| `o_edc_pkt_sent_irq[3:0]` | 1×4 | EDC packet sent interrupt |
| `o_edc_pkt_rcvd_irq[3:0]` | 1×4 | EDC packet received interrupt |

### 3.5 AXI Interfaces (×4, per column)

Each column x has one AXI master (NPU→DRAM, `npu_out_*`) and one AXI slave (host→NPU, `npu_in_*`).

**AXI Geometry:** data width=512b, address width=56b, full AXI4 (AW/W/B/AR/R channels).

| Group | Direction | Target |
|-------|-----------|--------|
| `npu_out_{ar,r,aw,w,b}_*[3:0]` | Master out / slave in | DRAM (NOC2AXI → external memory) |
| `npu_in_{ar,r,aw,w,b}_*[3:0]` | Slave in / master out | Host bus (AXI2NOC path inbound) |

`aruser`/`awuser` carries `noc2axi_tlbs_a_regmap_t` — a packed struct encoding NoC routing attributes (node_id, EP index, TLB index).

### 3.6 PRTN Chain (N1B0 addition)

| Port | Width | Description |
|------|-------|-------------|
| `PRTNUN_FC2UN_DATA_IN` | 1 | Chain data input from fabric controller |
| `PRTNUN_FC2UN_READY_IN` | 1 | Chain ready input |
| `PRTNUN_FC2UN_CLK_IN` | 1 | Chain clock input |
| `PRTNUN_FC2UN_RSTN_IN` | 1 | Chain reset input |
| `PRTNUN_UN2FC_DATA_OUT[3:0]` | 4 | PRTN data outputs (per column) |
| `PRTNUN_UN2FC_INTR_OUT[3:0]` | 4 | PRTN interrupt outputs |
| `PRTNUN_FC2UN_DATA_OUT[3:0]` | 4 | Pass-through data out |
| `PRTNUN_FC2UN_READY_OUT[3:0]` | 4 | Pass-through ready out |
| `PRTNUN_FC2UN_CLK_OUT[3:0]` | 4 | Pass-through clock out |
| `PRTNUN_FC2UN_RSTN_OUT[3:0]` | 4 | Pass-through reset out |
| `ISO_EN[11:0]` | 12 | Isolation enable: `[x + 4*y]` per Tensix tile (3 bits × 4 cols) |
| `TIEL_DFT_MODESCAN` | 1 | DFT scan mode |

### 3.7 SFR Memory Config Ports

Single-bit and multi-bit SRAM macro control passed globally to all SRAMs:
`SFR_RF_2P_HSC_{QNAPA,QNAPB,EMAA[2:0],EMAB[2:0],EMASA,RAWL,RAWLM[1:0]}`
`SFR_RA1_HS_{…}`, `SFR_RF1_HS_{…}`, `SFR_RF1_HD_{…}`

---

## 4. Module Hierarchy

### 4.1 Level-1 Instantiation (trinity top)

```
trinity (top)
│
├── [X=0,Y=4] gen_noc2axi_ne_opt
│   └── trinity_noc2axi_ne_opt          EP=4  (corner AXI bridge)
│
├── [X=1,Y=4+3] gen_noc2axi_router_ne_opt
│   └── trinity_noc2axi_router_ne_opt   EP=9 (NOC2AXI), EP=8 (Router)
│       ├── trinity_noc2axi_n_opt        ← Y=4 NOC2AXI bridge
│       └── trinity_router               ← Y=3 mesh router (EP=8)
│
├── [X=2,Y=4+3] gen_noc2axi_router_nw_opt
│   └── trinity_noc2axi_router_nw_opt   EP=14 (NOC2AXI), EP=13 (Router)
│       ├── trinity_noc2axi_n_opt        ← Y=4 NOC2AXI bridge
│       └── trinity_router               ← Y=3 mesh router (EP=13)
│
├── [X=3,Y=4] gen_noc2axi_nw_opt
│   └── trinity_noc2axi_nw_opt          EP=19 (corner AXI bridge)
│
├── [X=3,Y=3] gen_dispatch_e
│   └── tt_dispatch_top_east            EP=3
│       └── tt_dispatch_engine
│           ├── tt_disp_eng_l1_partition  (dispatch-private L1)
│           └── tt_disp_eng_overlay_noc_wrap
│               └── trin_disp_eng_noc_niu_router_east_inst
│
├── [X=1,Y=3] gen_router  ← EMPTY (router logic inside _router_ne_opt above)
├── [X=2,Y=3] gen_router  ← EMPTY (router logic inside _router_nw_opt above)
│
├── [X=0,Y=3] gen_dispatch_w
│   └── tt_dispatch_top_west            EP=18
│
├── [X=0..3, Y=0..2] gen_tensix_neo (×12)
│   └── tt_tensix_with_l1              EP=0..17 (excl. 3,4,8,9,13,14,18,19)
│       └── tt_overlay_noc_wrap
│           └── tt_overlay_noc_niu_router
│               └── tt_neo_overlay_wrapper
│                   └── tt_overlay_wrapper
│                       ├── clock_reset_ctrl (tt_overlay_clock_reset_ctrl)
│                       ├── tt_overlay_cpu_wrapper
│                       │   └── TTTrinityConfig_DigitalTop
│                       │       └── RocketTile[*] (BRISC + TRISC×3)
│                       ├── tt_overlay_memory_wrapper
│                       │   ├── L1 banks (RA1_UHD, 16×1024×128 or 3072×128 in N1B0)
│                       │   ├── L2 banks, dir (dm_clk)
│                       │   └── context switch SRAMs
│                       ├── tt_overlay_edc_wrapper
│                       ├── tt_t6_l1_flex_client_port (ai_clk domain)
│                       └── tt_overlay_noc_snoop_tl_master
│
├── tt_noc_repeaters (NUM=4) ×2   ← Y=4 inter-column (X=1↔X=2)
└── tt_noc_repeaters (NUM=6) ×2   ← Y=3 inter-column (X=1↔X=2)
```

### 4.2 Tensix Deep Hierarchy (tt_tensix_with_l1)

```
tt_tensix_with_l1
└── tt_overlay_noc_wrap (tt_overlay_noc_wrap)
    └── tt_overlay_noc_niu_router
        ├── tt_noc_niu_router_dfx          (5 clock pass-throughs)
        └── tt_neo_overlay_wrapper
            └── tt_overlay_wrapper
                ├── tt_overlay_wrapper_dfx (5 clock pass-throughs)
                ├── clock_reset_ctrl (tt_overlay_clock_reset_ctrl)
                ├── cpu_cluster_wrapper (tt_overlay_cpu_wrapper)
                │   └── TTTrinityConfig_DigitalTop
                │       ├── RocketTile[0] (BRISC + TRISC×3 thread 0)
                │       ├── RocketTile[1] (TRISC threads)
                │       └── ...
                ├── memory_wrapper (tt_overlay_memory_wrapper)
                │   ├── tt_t6_l1_partition (L1 SRAM 16-banks)
                │   │   └── tt_t6_l1_partition_dfx (2 clock pass-throughs)
                │   ├── L2 dcache data/tag SRAMs (dm_clk)
                │   └── context switch SRAMs (32×1024, 8×1024)
                ├── edc_wrapper (tt_overlay_edc_wrapper)
                ├── tt_t6_l1_flex_client_port (ai_clk domain)
                ├── tt_instrn_engine_wrapper
                │   └── tt_instrn_engine_wrapper_dfx (1 clock pass-through)
                │   └── [TRISC/BRISC CPU, FPU, SFPU, TDMA, DEST]
                └── noc_snoop_tl_master
```

---

## 5. Compute Tile — Tensix

**Top module:** `tt_tensix_with_l1` (×12 instances)
**Physical position:** Y=0..2, X=0..3
**Clock domains:** ai_clk (compute), noc_clk (NoC endpoint), dm_clk (L2/mem pipeline)

### 5.1 TRISC / BRISC CPU Cluster

**Module:** `TTTrinityConfig_DigitalTop` → `RocketTile[*]`
**Clock:** ai_clk

The CPU cluster implements 4 cores per Tensix tile:
- **BRISC** (bulk read-issue script controller): main programmable thread, handles DMA sequencing and data movement control
- **TRISC[0..2]** (three tensor-stream instruction controllers): execute TDMA packing, unpacking, and FPU/SFPU math instructions

| Component | Description |
|-----------|-------------|
| Rocket pipeline | 5-stage in-order RISC-V; BRISC = RV32IM, TRISC = RV32I subset |
| I-cache | Per-thread; 256×72 or 512×72 SRAM (SP, byte-masked, RA1_HS) |
| LDM (local data memory) | Per-thread local stack SRAM; 256×104, 512×52, or 1024×52 |
| `tt_cluster_sync` | Inter-core semaphore; synchronization via shared register file |
| `tt_stall_scoreboard` | Track in-flight TDMA and FPU transactions; stalls TRISC if results not ready |
| Replay unit | Re-issues instructions after stall or flush |
| MOP engine | Macro-operation decoder; expands packed T6 MOP codes into instruction sequences |

**Thread assignment:**
- BRISC: DMA control, address generation, data movement coordination
- TRISC0: TDMA unpack (load data from L1 to SRCA/SRCB)
- TRISC1: FPU math instructions
- TRISC2: TDMA pack (store data from DEST to L1)

**SW interface:** TRISC programs issue ops via MMIO-mapped SFRs. BRISC issues DMA ops via NoC transactions. Both CPUs share the L1 through the `tt_t6_l1_superarb` arbitrator.

### 5.2 FPU — G-Tile, M-Tile, FP Lanes

**Module:** `tt_fpu_gtile` (×2 per Tensix tile: `gen_gtile[0]` cols 0–7, `gen_gtile[1]` cols 8–15)
**Clock:** ai_clk
**Data width:** 16b per lane, 16 lanes (one lane per column)

#### G-Tile Structure

```
tt_fpu_gtile  (one per 8 columns)
├── tt_fpu_mtile  (M-Tile: integer MAC array)
│   ├── Booth multiplier array (16b×16b → 32b accum)
│   ├── Wallace compressor tree
│   └── INT16 / INT8 accumulator pipeline
├── tt_fpu_fp_lane[0..7]  (8 floating-point lanes)
│   ├── fp_mul_raw (mantissa multiply, 7-stage pipeline)
│   ├── exp_path (exponent adder + normalizer)
│   ├── special case handler (NaN/Inf/zero/denorm)
│   └── format converter (BF16/FP16/FP8/TF32/INT variants)
├── SRCA register file (per-lane, ai_clk latch array)
├── DEST register file slice (rows 0–511 or 512–1023)
└── Stochastic rounding PRNG (per-lane LFSR)
```

#### M-Tile (Integer MAC)

The M-Tile performs integer matrix multiply-accumulate for INT16/INT8 workloads:
- **INT16 mode**: 16b × 16b → 32b accumulate per lane per cycle; 16-lane array = 256 MACs/cycle/tile
- **INT8 mode**: 8b × 8b → 32b; 2 INT8 operations per INT16 slot = 512 MACs/cycle/tile
- Operand A: from SRCA register; Operand B: from SRCB register
- Accumulator: in DEST register file (32b or 16b depending on format)

#### FP Lanes

8 FP lanes per G-Tile, 16 total per Tensix tile. Each lane:
- Performs one floating-point multiply-accumulate per cycle at full precision
- Supports 14 numeric formats: BF16, FP16, FP8E4M3, FP8E5M2, TF32, INT32, INT16, UINT16, INT8, UINT8, FP32 (output-only), and stochastic-rounded variants
- `fp_mul_raw`: unrounded 7-stage multiply path (mantissa tree + accumulate)
- `exp_path`: exponent addition + leading-zero detect + normalizer

#### Stochastic Rounding

Per-lane PRNG (Galois LFSR, 32-bit) adds random bit to the truncated mantissa before round-to-nearest. Reduces systematic rounding bias in deep accumulation. Controlled per format via `stoch_rnd_en` SFR bit.

### 5.3 SFPU

**Module:** `tt_sfpu` (instantiated inside `tt_instrn_engine_wrapper`)
**Clock:** ai_clk

The SFPU is a scalar floating-point post-processor that applies element-wise functions to DEST register file elements:
- Operations: `EXP`, `LOG`, `SQRT`, `RECIP`, `GELU`, `SIGMOID`, `TANH`, `RELU`, `LReLU`, `NEGATE`, `MAX/MIN`, type conversion
- Datapath: reads from DEST→SFPU operand, applies function, writes back to DEST
- All functions implemented via piecewise linear approximation tables stored in SFPU ROM, with iterative refinement for precision-sensitive ops (`EXP`, `LOG`)
- Supports BF16, FP16, FP8, INT32 as input/output formats
- Pipeline depth: 2–8 cycles depending on operation

**SW programming:** TRISC1 issues SFPU ops via `SFPU_OP` SFR. SFPU runs concurrently with MAC operations in the FP lanes.

### 5.4 TDMA

**Module:** `tt_tdma` (inside `tt_instrn_engine_wrapper`)
**Clock:** ai_clk (for L1 access), noc_clk (for NoC endpoint side)
**CDC:** async FIFO at the ai_clk ↔ noc_clk boundary

TDMA manages data movement between L1 and the compute register files:

| Channel | Direction | Description |
|---------|-----------|-------------|
| Unpack CH0 | L1 → SRCA | Load operand A data from L1 to SRCA register |
| Unpack CH1 | L1 → SRCB | Load operand B data from L1 to SRCB register |
| Pack CH0 | DEST → L1 | Store output from DEST back to L1 |
| Pack CH1 | DEST → L1 (alt) | Second pack channel for double-buffering |

TDMA supports **format conversion on the fly** during pack/unpack:
- Unpack: converts from storage format (e.g., INT8) to compute format (e.g., FP16)
- Pack: converts from accumulator format (INT32) to storage format (INT8/BF16)

**XY address controller:** generates 2D tile addresses; handles stride, loop, and skip patterns for tensor layout (row-major, column-major, tile-major).

**Word assembler:** for sub-word formats (INT8), assembles 4 INT8 values into one 32-bit L1 word.

### 5.5 L1 Cache / SRAM

**Module:** `tt_t6_l1_partition` (inside `tt_overlay_memory_wrapper`)
**Clock:** ai_clk (TDMA access), noc_clk (NoC write path via async FIFO)

**N1B0 L1 configuration:** 16 banks × 1 SRAM macro per bank
- **Baseline:** 768 rows × 128 bits per bank = 12 KB/bank; 192 KB total per tile
- **N1B0:** 3072 rows × 128 bits per bank = 48 KB/bank; **768 KB total per tile**
  - N1B0 uses 4× larger SRAM macros; total design has 12 tiles × 768 KB = **9.216 MB** NPU-local L1

| Property | Value |
|----------|-------|
| Banks | 16 |
| Bank width | 128 bits |
| ECC | SECDED per 128-bit word |
| SRAM type | `RA1_UHD` (area-optimized) |
| Access ports | 2 (NoC write, TDMA read/write) + BRISC load/store |
| Arbitration | `tt_t6_l1_superarb` (priority: TDMA > NoC write > BRISC) |

**L2 cache** (inside `tt_overlay_memory_wrapper`, dm_clk domain): coherent L2 for CPU load/store path; uses `dm_clk` SRAM macros.

### 5.6 DEST Register File

**Module:** `tt_reg_bank` (inside `tt_fpu_gtile`)
**Type:** Latch array (`always_latch`) — **not SRAM macro**
**Clock:** ai_clk, gated via `tt_clkgater` ICG

DEST is the output accumulator register of the FPU:
- Total depth: 4096 rows × 16 cols per Tensix tile; split 50/50 across `gen_gtile[0]` and `gen_gtile[1]` (2048 rows each)
- Each row stores 16 × 32b = 512b of accumulator data
- Write from FP lanes (MAC output), M-Tile output, or SFPU output
- Read by TDMA Pack CH0/CH1 and MOVD2A feedback path (DEST→SRCA)

**ICG structure:** One `tt_clkgater` per datum (row+column combination). A stabilization latch captures write-enable one cycle before data to ensure clean ICG transitions.

**MOVD2A path:** Direct DEST→SRCA feedback for RNN-style recurrent accumulation. Latency-sensitive: minimize feedback wire length in P&R.

**Total latch-array count:** 12 tiles × 4096 rows × 16 cols = **12,288 latch array instances** in full design (N1B0 with no harvest).

### 5.7 SRCB Register

**Module:** `tt_srcb_registers` (inside `tt_fpu_v2`, between FPU and TDMA)
**Type:** Latch array + ICG (same structure as DEST)
**Physical placement:** Center of Tensix tile, equidistant to `gen_gtile[0]` and `gen_gtile[1]`

SRCB holds the weight (B operand) for the matrix multiply:
- Depth: `SRCB_DEPTH × 16` datums; broadcast bus (`srcb_rd_tran`) fans out simultaneously to both G-Tiles
- Write: TDMA Unpack CH1 via `srcb_wr_tran`
- Read: Broadcast to all 16 columns simultaneously each cycle

**SRCA** is stored per G-Tile inside each `tt_fpu_gtile`:
- Read: column-mux via `tt_srca_lane_sel` (selects which SRCA row feeds each FP lane)
- Write: from TDMA Unpack CH0 (`srca_wr_tran`) or MOVD2A feedback

---

## 6. Dispatch Engine

**Modules:** `tt_dispatch_top_east` (X=3, Y=3, EP=3) / `tt_dispatch_top_west` (X=0, Y=3, EP=18)
**File:** baseline RTL (unchanged in N1B0)

### 6.1 Internal Hierarchy

```
tt_dispatch_top_east/west
└── tt_dispatch_engine
    ├── tt_disp_eng_l1_partition (dispatch-private L1 SRAM)
    │   ├── de_refclk_dft_vdd_sys (tt_refclk_dft_mux)
    │   ├── tt_t6_l1_dispatch (tt_disp_eng_l1_wrap2) — dispatch L1 SRAMs
    │   └── tt_edc_biu (tt_edc_biu_soc_apb4_wrap)
    └── overlay_noc_wrap_inst (tt_disp_eng_overlay_noc_wrap)
        └── disp_eng_overlay_noc_niu_router
            ├── tt_disp_eng_overlay_wrapper (DISPATCH_INST=1, HAS_SMN_INST=0)
            │   └── tt_overlay_wrapper
            └── trin_disp_eng_noc_niu_router_east/west_inst
                └── tt_disp_eng_noc_niu_router
                    └── ATT SRAMs:
                        - 1024×12 endpoint_translation
                        - 32×1024 routing_translation
```

### 6.2 Function

The Dispatch Engine (FDS — Fast Dispatch Sub-system) implements:
- **NoC packet injection:** assembles and sends NoC packets to Tensix tiles on behalf of the host
- **Dispatch L1:** staging buffer for kernel launch payloads; holds kernel configs, weight metadata, activation descriptors
- **Auto-dispatch FIFO:** hardware FIFO that autonomously re-issues pre-programmed packets at timer-driven intervals
- **de_to_t6 / t6_to_de wire bus:** direct point-to-point wires (not NoC) from Dispatch to all Tensix tiles in the same column for control signals

### 6.3 Clock Domains

| Clock | Used for |
|-------|---------|
| `i_ai_clk[x]` | FDS FSM, dispatch register file, L1 access |
| `i_noc_clk` | NoC endpoint (VC buffers, flit Rx/Tx) |
| `i_dm_clk[x]` | Auto-dispatch FIFO, FDS bus output |

CDC: `tt_async_fifo_wrapper` at `dm_clk ↔ noc_clk` and `noc_clk ↔ ai_clk` boundaries.

---

## 7. NoC Fabric

### 7.1 Architecture

The NoC is a **5×4 mesh** (SizeY=5 rows, SizeX=4 columns) with the following routing support:
- **DOR (Dimension-Order Routing):** XY routing; East/West first, then North/South
- **Tendril routing:** 2-hop indirect for around-obstacle routing
- **Dynamic routing:** per-flit 928-bit carried path list (enabled in N1B0 via `EnableDynamicRouting=1`)

### 7.2 Router Architecture

Each router tile (`trinity_router`) is a 5-port mesh switch:
- Ports: North, South, East, West, NIU (local endpoint)
- VC (virtual channel) input buffers: `mem_wrap_Dx2048_router_input_[N/E/S/W]` SRAM macros
  - N1B0 uses `72×2048` depth (72 entries per direction, 2048b width)
- Inbound cardinal repeaters: `tt_noc_repeaters_cardinal`
- Output port allocator: per-output VC allocation with round-robin arbitration
- Port allocator: `tt_router_port_allocator`

### 7.3 Flit Format

**NoC flit structure:**
- Header flit: `noc_header_address_t` (128b): `{x_dest, y_dest, endpoint_id, flit_type[2:0], path_squash, dynamic_carried_list[928b]}`
- Data flits: up to max burst length
- `flit_type[2:0]`: 3-bit enum — `HEADER`, `BODY`, `LAST`, `PATH_SQUASH`, `ACK`, `NACK`

**AXI address gasket (56-bit):**
```
[55:52] reserved (4b)
[51:48] target_index (4b) — AXI slave index
[47:40] endpoint_id (8b) — NoC destination EP
[39:36] tlb_index (4b)   — TLB entry
[35:0]  address (36b)    — physical address
```

### 7.4 X-Axis Connections (N1B0 manual assignment)

N1B0 replaces the baseline generate-loop X connections with manual assigns to insert repeaters between X=1 and X=2:

| Row | X=0↔X=1 | X=1↔X=2 | X=2↔X=3 |
|-----|---------|---------|---------|
| Y=0,1,2 | direct | direct | direct |
| Y=3 (Router) | direct | **6-stage repeater** (`tt_noc_repeaters`) | direct |
| Y=4 (NOC2AXI) | direct | **4-stage repeater** (`tt_noc_repeaters`) | direct |

West edge (X=0 west) and East edge (X=3 east) tied to `'{default:0}`.

### 7.5 Dynamic Routing (Carried List)

When `EnableDynamicRouting=1`, each header flit carries a 928-bit route list: 16 slots × 58 bits, where each slot encodes `{x, y, EP, force_dim[2:0]}`. At each router hop, the current slot is read and consumed; the NIU at the destination may overwrite the next slot for return routing. This allows arbitrary multi-hop paths beyond DOR.

---

## 8. NIU — AXI Bridge Tiles

### 8.1 Corner NIU (NOC2AXI_NE_OPT and NOC2AXI_NW_OPT)

**Modules:** `trinity_noc2axi_ne_opt` (X=0, Y=4, EP=4) / `trinity_noc2axi_nw_opt` (X=3, Y=4, EP=19)
**Files:** `used_in_n1/rtl/trinity_noc2axi_ne_opt.sv`, `trinity_noc2axi_nw_opt.sv`

**Flit ports:** NE_OPT has `south` + `west` only (no east or north NoC ports).
NW_OPT has `south` + `east` only.

**Clock output:** `o_ai_clk`, `o_nocclk`, `o_dm_clk` → drives `clock_routing_out[x][y]` (same row Y=4).

**EDC:** has `loopback_edc_ingress_intf` and `edc_egress_intf` directly at Y=4 EPindex.

Port naming: `edc_apb_*` (no `i_` prefix) for APB access.

### 8.2 Composite NIU+Router (NOC2AXI_ROUTER_NE_OPT / NW_OPT)

**Modules:** `trinity_noc2axi_router_ne_opt` (X=1, EP_NOC2AXI=9, EP_Router=8) / `trinity_noc2axi_router_nw_opt` (X=2, EP_NOC2AXI=14, EP_Router=13)

These modules span **two physical rows** (Y=4 + Y=3). They contain both a NOC2AXI bridge and a mesh router as internal sub-modules.

#### Internal Sub-modules

```
trinity_noc2axi_router_ne_opt
├── trinity_noc2axi_n_opt       (Y=4: AXI bridge, EP=9)
│   └── EDC node at EP=9
└── trinity_router               (Y=3: mesh router, EP=8)
    └── EDC node at EP=8
```

#### Cross-Row Internal Wires (lines 291–337 of `ne_opt.sv`)

**NoC flit cross-connection (south ↔ north):**
```
router_i_flit_in_req_north    = noc2axi_o_flit_out_req_south  // NOC2AXI→Router
noc2axi_i_flit_in_req_south   = router_o_flit_out_req_north   // Router→NOC2AXI
(plus resp handshakes in reverse)
```

**Clock routing chain:**
`noc2axi_clock_routing_out` → `router_clock_routing_in` (all 9 fields of `trinity_clock_routing_t`)

The router's buffered clock outputs (`router_o_ai_clk`, etc.) drive `clock_routing_out[x][y-1]` (Y=3) at trinity top.

**EDC chain:**
Forward: `noc2axi_edc_egress_intf` → `router_edc_ingress_intf`
Loopback: `router_loopback_edc_egress_intf` → `noc2axi_loopback_edc_ingress_intf`

#### ID Offsets Applied to Router

```systemverilog
.i_local_nodeid_y  (i_local_nodeid_y - 1)   // Y=4 → Y=3
.i_noc_endpoint_id (i_noc_endpoint_id - 1)  // EP=9→8 or EP=14→13
```

#### Router Parameters (N1B0-specific, hard-coded)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `REP_DEPTH_LOOPBACK` | 6 | Loopback reg-slice depth |
| `REP_DEPTH_OUTPUT` | 4 | Output reg-slice depth |
| `NUM_REPEATERS_INBOUND/OUTBOUND_WEST` | 4 | West inter-column path |
| `NUM_REPEATERS_INBOUND/OUTBOUND_EAST` | 1 | East (toward X=0/X=3) |
| `NUM_REPEATERS_INBOUND/OUTBOUND_NORTH` | 1 | North (internal to NOC2AXI) |
| `NUM_REPEATERS_INBOUND/OUTBOUND_SOUTH` | 5 | South (toward Tensix rows) |

### 8.3 AXI Interface

Each NIU tile provides:

| Path | AXI Role | Description |
|------|----------|-------------|
| NOC2AXI master (`noc2axi_*`) | AXI4 master | NPU reads/writes to external DRAM |
| AXI2NOC slave (`axi2noc_*`) | AXI4 slave | Host or other initiators access NPU address space |

**Data path width:** 512 bits  **Address width:** 56 bits

**NOC2AXI** (read path): NoC request flit arrives → deserialize → AXI AR issue → RDATA collected → packed into response flit → routed back to requester.

**AXI2NOC** (inbound path): AXI AW/AR from host → address translation via 56b gasket → NoC packet injected toward target Tensix tile or dispatch.

**RDATA FIFO depth** (`AXI_SLV_RD_RDATA_FIFO_DEPTH`): configurable 32–1024 entries. N1B0 default=512. SRAM wrappers for all depths present in `used_in_n1/rtl/`.

### 8.4 ATT and SMN Security

**ATT (Address Translation Table):**
- 1024-entry endpoint translation SRAM (12b mask per entry)
- 32×1024 routing translation SRAM
- Used for NoC packet destination remapping (harvest, dynamic topology)

**SMN (Secure Memory Node):**
- 8 programmable address ranges per NIU tile
- Each range: `{base, mask, allow_mask, deny_mask}`
- Requests matching a deny range receive error response; allow range bypasses check
- Access via APB register bank

---

## 9. Clock Architecture

### 9.1 Clock Domains

| Domain | Port | Scope | Typical Use |
|--------|------|-------|-------------|
| `AICLK` | `i_ai_clk[x]` | Per-column compute | All TRISC, FPU, SFPU, TDMA, L1 AICLK path, DEST, SRCB, cluster_sync |
| `NOCCLK` | `i_noc_clk` | Global NoC | NoC VC buffers, flit Rx/Tx, L1 NoC write port, router |
| `dm_clk` | `i_dm_clk[x]` | Per-column | FDS FSM, dispatch FIFO, dispatch register file, L2 cache |
| `i_axi_clk` | `i_axi_clk` | Global AXI | NOC2AXI bridge AXI channel logic only |

### 9.2 Clock Routing Struct (`trinity_clock_routing_t`)

```systemverilog
typedef struct packed {
    logic ai_clk;
    logic noc_clk;
    logic dm_clk;
    logic ai_clk_reset_n;
    logic noc_clk_reset_n;
    logic [SizeY-1:0] dm_uncore_clk_reset_n;          // [4:0]
    logic [SizeY-1:0][DMCoresPerCluster-1:0] dm_core_clk_reset_n;  // [4:0][7:0]
    logic [SizeY-1:0] tensix_reset_n;                  // [4:0]
    logic power_good;                                   // from i_edc_reset_n
} trinity_clock_routing_t;
```

Arrays: `clock_routing_in[SizeX][SizeY]` and `clock_routing_out[SizeX][SizeY]`.

### 9.3 Clock Entry and Propagation

- `i_ai_clk[x]` and `i_dm_clk[x]` enter the tile grid at **Y=4** via `clock_routing_in[x][4]`
- Propagate south tile-by-tile: each tile buffers and re-drives `clock_routing_out[x][y]` which becomes `clock_routing_in[x][y-1]` for the tile below
- `i_noc_clk`: bypasses the routing struct; driven directly to all tiles as a single global

**Y=4 corner tiles (NE_OPT, NW_OPT):** output buffered clock via `o_ai_clk`, `o_dm_clk` → `clock_routing_out[x][4]`.

**Y=4 middle tiles (NOC2AXI_ROUTER_*_OPT):** clock is buffered inside `trinity_noc2axi_n_opt`; output is carried via `router_o_ai_clk`, `router_o_dm_clk` (from `trinity_router`) → `clock_routing_out[x][3]` (Y=3). No `clock_routing_out[x][4]` is driven at Y=4 for X=1,2.

### 9.4 Clock Gating

All clock gates use `tt_clkgater` → maps to `tt_libcell_clkgate` (PDK ICG cell) at synthesis:
```systemverilog
module tt_libcell_clkgate (input i_CK, i_E, i_TE, output o_ECK);
// latch enable on LOW phase; AND with clock
// i_TE: test enable for scan (forces clocks on during scan)
```

ICG instances: ~26 per Tensix tile. Must be placed adjacent to associated latch/register arrays in P&R.

---

## 10. Reset Architecture

### 10.1 Reset Tree

```
i_noc_reset_n ─────────────────────────────────→ NoC VC buffers, FDS output bus
i_ai_reset_n[x] (per column)
    ├── via clock_routing → i_ai_clk_reset_n   → FPU, SFPU, TDMA, L1 AICLK, DEST
    └── via clock_routing → i_tensix_reset_n[n] → tile-level reset gate
i_tensix_reset_n[12] (per tile, packed at top):
    clock_routing_in[x][4].tensix_reset_n[4-y] = i_tensix_reset_n[getTensixIndex(x,y)]
i_dm_core_reset_n[14][8] → DM cores per DmComplex per core
i_dm_uncore_reset_n[14]  → DM uncore per DmComplex
i_edc_reset_n            → repurposed as power_good in clock_routing struct
```

### 10.2 Reset Synchronizers

All async resets are synchronized with `tt_libcell_sync3r` (3-stage synchronizer) at the domain boundary. SDC multicycle paths:
- AI domain reset sync: setup=4, hold=3
- NOC domain reset sync: setup=4, hold=3

### 10.3 Harvest Reset

A harvested (defective) tile is permanently isolated by:
1. Asserting `i_tensix_reset_n[getTensixIndex(x,y)] = 0` permanently
2. Setting `ISO_EN[x + 4*y] = 1` to activate isolation cells at tile boundary

---

## 11. EDC — Error Detection and Correction

### 11.1 Overview

The EDC1 ring is a serial daisy-chain that connects all 20 tiles plus one mesh-config node (node_id=192) in a fixed traversal order. EDC detects in-flight NoC packet errors and maintains ring integrity monitoring.

### 11.2 Ring Structure per Column

Each column has its own EDC ring subsystem. The ring traversal order per column (from `EDC_path.md`) follows this pattern:

```
Column top (Y=4):  NOC2AXI_Router[x][4]  (NOC2AXI level — external EDC ingress)
                         ↓ (internal wire inside composite module, X=1,2 only)
              NOC2AXI_Router[x][3]  (Router level — external EDC egress/loopback)
                         ↓
Corner tiles (X=0,3):  NOC2AXI_NE/NW_OPT at Y=4 (single-segment, EDC exits here)
                         ↓
              Dispatch[x][3]  (or empty placeholder)
                         ↓
              Tensix[x][2] → Tensix[x][1] → Tensix[x][0]
                         ↓
              loopback path back to column top
```

**Key N1B0 composite tile EDC details (X=1 and X=2):**
- Each composite `trinity_noc2axi_router_ne/nw_opt` contains **two EDC nodes**:
  - Y=4 segment: `trinity_noc2axi_n_opt` internal EDC node
  - Y=3 segment: `trinity_router` internal EDC node
- Internal EDC chain: `noc2axi_edc_egress_intf → router_edc_ingress_intf` (forward)
- Internal loopback: `router_loopback_edc_egress_intf → noc2axi_loopback_edc_ingress_intf`
- External EDC ports of the composite module exit at **Y=3** (router level)
- `gen_router[x][3]` in `trinity.sv` is an empty placeholder — router EDC nodes are inside the composite module, not standalone

### 11.3 Node ID Encoding

`node_id = {part[4:0], subp[2:0], inst[7:0]}`

where `subp` = y-coordinate of the tile row.

For the N1B0 NOC2AXI_ROUTER composite tiles (X=1,2), there are **two EDC nodes per module**:
- NOC2AXI level (Y=4): `subp`=4, `inst` based on EP=9 (X=1) or EP=14 (X=2)
- Router level (Y=3): `subp`=3, `inst` based on EP=8 (X=1) or EP=13 (X=2)

### 11.4 EDC Interface Signals

```systemverilog
edc1_serial_bus_intf_def:
    req_tgl    // request toggle (async handshake)
    ack_tgl    // acknowledge toggle
    data       // EDC data payload
    data_p     // parity of data
    async_init // initialization signal
    err        // error flag
```

### 11.5 EDC APB Access

4 EDC APB ports (one per column) at the trinity top level:
- `i_edc_apb_paddr`: 6-bit address space (64 registers per EDC node)
- Accessed at same APB bus as NIU register bank but on dedicated `edc_apb_*` port
- Key CSRs: `INIT_CNT` (startup count), `MCPDLY` (multicycle path delay), `BYPASS_EN` (harvest bypass)

### 11.6 Harvest EDC Bypass

When a Tensix tile is harvested, the EDC ring would be broken. The `BYPASS_EN` CSR in the preceding ring node enables bypass mode: the harvested tile's EDC slot is skipped, and the ring reconnects around the missing tile.

---

## 12. Power Management — PRTN and ISO_EN

### 12.1 PRTN Chain (N1B0 addition)

The PRTN (partition) chain is a per-column daisy-chain enabling the fabric controller to detect and signal partition power events:

**Topology per column x:**
```
External FC (Fabric Controller)
  → PRTNUN_FC2UN_{DATA,READY,CLK,RSTN}_IN  (single entry)
  → Tensix tile [x][2] (Y=2)
  → Tensix tile [x][1] (Y=1)
  → Tensix tile [x][0] (Y=0)
  → PRTNUN_FC2UN_{DATA,READY,CLK,RSTN}_OUT[x]  (pass-through exit)
Output tapped at Y=2: PRTNUN_UN2FC_{DATA,INTR}_OUT[x]
```

The chain is clocked by `PRTNUN_FC2UN_CLK_IN` (separate from AI/DM/NoC clocks).

**Dispatch tiles (Y=3) are not in the PRTN chain** — only Tensix tiles (Y=0..2) are connected.

### 12.2 ISO_EN Isolation

`ISO_EN[11:0]` selects which Tensix tiles have their boundary isolation cells enabled:

```
ISO_EN[x + 4*y]  for Tensix tile at column x, row y
where x = 0..3 (columns), y = 0..2 (rows)
```

Bit mapping:
| ISO_EN bits | Tiles controlled |
|-------------|-----------------|
| `[3:0]` | Y=0: T6[0][0], T6[1][0], T6[2][0], T6[3][0] |
| `[7:4]` | Y=1: T6[0][1], T6[1][1], T6[2][1], T6[3][1] |
| `[11:8]` | Y=2: T6[0][2], T6[1][2], T6[2][2], T6[3][2] |

When `ISO_EN[i]=1`, the corresponding tile's output buses are forced to a safe value, preventing contention on shared wires during power-down.

---

## 13. SRAM Inventory

### 13.1 Per-Tile SRAM Summary (N1B0)

| Block | Per-Tile Count | Dimensions | Type | Clock | Total (12 tiles) |
|-------|---------------|-----------|------|-------|-----------------|
| L1 banks | 16 | 3072×128 | RA1_UHD | dm_clk | 192 |
| TRISC I-cache | 3 | 256×72 or 512×72 | RA1_HS | ai_clk | 36 |
| TRISC LDM | 3 | 256×104 or 512×52 or 1024×52 | RA1_UHD | ai_clk | 36 |
| NoC VC input FIFO | 4 (N/S/E/W) | 72×2048 | RF2_HS | noc_clk | 48 |
| Overlay L2 data | 4 | varies | RA1_UHD | dm_clk | 48 |
| Overlay L2 dir | 2 | varies | RF1_UHD | dm_clk | 24 |
| Context switch | 2 | 32×1024 + 8×1024 | SP | ai_clk | 24 |

### 13.2 Latch Arrays (not SRAM macros)

| Block | Per-Tile | Total (12 tiles) | Notes |
|-------|---------|-----------------|-------|
| DEST reg file | 4096 datums × 16 cols | 12,288 instances | `always_latch` + ICG |
| SRCA reg file | varies per col | 1,536 total | Per G-Tile, per lane |
| SRCB reg file | SRCB_DEPTH × 16 | 1 per tile | Center placement |

### 13.3 Dispatch Engine SRAMs (2 tiles)

| Block | Count | Dimensions | Notes |
|-------|-------|-----------|-------|
| Dispatch L1 | varies | similar to Tensix L1 | tt_disp_eng_l1_wrap2 |
| ATT endpoint_translation | 2 (E+W NIU each) | 1024×12 | SPW |
| ATT routing_translation | 2 | 32×1024 | SPW |

### 13.4 NOC2AXI RDATA FIFO

Per NIU tile (4 tiles): depth configurable via `AXI_SLV_RD_RDATA_FIFO_DEPTH`:
- Available depths: 32, 64, 128, 256, 512, 1024 entries
- N1B0 default: 512 entries
- Width: 512b data + metadata

SRAM wrapper files for all depths exist in `used_in_n1/rtl/`:
`noc2axi_slv_rddata_fifo_depth_32.sv` ... `_1024.sv`

### 13.5 SRAM Macro Types

| Type | Properties | Usage |
|------|-----------|-------|
| `RA1_UHD` | Ultra-high density, area-optimized | L1, LDM |
| `RA1_HS` | High-speed | I-cache |
| `RF1_UHD` | Register-file style, 2-port | L2 dir, small lookup |
| `RF2_HS` | Register-file 2-port high-speed | NoC VC buffers |
| `RD2_UHD` | Read dual-port | Misc |
| `VROM_HD` | ROM, high-density | Constant tables |

**Memory control:** `mem_cfg_l1_t` uses `ra1_uhd_emc_min`. `mem_cfg_tensix_t` uses `ra1_uhd_min` for most, `ra1_hs_min` for I-cache.

---

## 14. DFX Hierarchy

### 14.1 Overview

DFX modules are clock distribution wrappers. In N1B0, all DFX modules are **wire-assign pass-throughs**. `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` is not defined — IJTAG network is absent.

### 14.2 DFX Module Summary

| Module | File | Clocks | IJTAG | Used in |
|--------|------|--------|-------|---------|
| `tt_noc_niu_router_dfx` | `dfx/tt_noc_niu_router_dfx.sv` | 5 (aon,clk,ovl_core,ai,ref) → 5 | ifdef, absent | NIU/Router tiles |
| `tt_overlay_wrapper_dfx` | `dfx/tt_overlay_wrapper_dfx.sv` | 5 (core,uncore,ai,nocclk_aon,ref) → 5 | none | Tensix overlay top |
| `tt_instrn_engine_wrapper_dfx` | `dfx/tt_instrn_engine_wrapper_dfx.sv` | 1 (clk) → 1 | ifdef, absent | Instruction engine |
| `tt_t6_l1_partition_dfx` | `dfx/tt_t6_l1_partition_dfx.sv` | 2 (clk, nocclk) → 3 (predfx+postdfx clk, postdfx nocclk) | ifdef, absent | L1 partition |

### 14.3 DFX Placement in Tensix Tile

```
tt_tensix_with_l1
└── tt_noc_niu_router_dfx (5 clocks)
└── tt_overlay_wrapper_dfx (5 clocks)
    └── tt_t6_l1_partition_dfx (2→3 clocks; for 4 T6 core groups ts0-ts3)
    └── tt_instrn_engine_wrapper_dfx (1 clock; for FPU G-Tile 0/1, DFD)
```

### 14.4 IJTAG Chain (when `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` enabled)

```
External TAP
  → tt_noc_niu_router_dfx (entry)
      → tt_t6_l1_partition_dfx SIB
          → T6 core group ts0 → ts1 → ts2 → ts3 → DFD
      → tt_instrn_engine_wrapper_dfx SIB
          → FPU G-Tile 0 → FPU G-Tile 1 → instruction engine DFD
  → output SO
```

Currently not active in N1B0 RTL. DFX insertion flow (Tessent) will replace pass-throughs with ICG cells and SIB network.

---

## 15. Physical / P&R Guide

### 15.1 Synthesis Partitions

15 independently synthesized partitions:

| Partition | Module | Key Contents |
|-----------|--------|-------------|
| `tt_fpu_gtile` | `tt_fpu_gtile` | M-Tile, FP Lanes ×8, SRCB pipe, DEST slice |
| `tt_instrn_engine_wrapper` | `tt_instrn_engine_wrapper` | BRISC+TRISC×3, MOP engine, scoreboard |
| `tt_t6_l1_partition` | `tt_t6_l1_partition` | L1 banks ×16, superarb, ECC, phase gen |
| `tt_dispatch_engine` | `tt_dispatch_engine` | FDS FSM, dispatch L1, NoC NIU |
| `tt_disp_eng_l1_partition` | `tt_disp_eng_l1_partition` | Dispatch private L1 |
| `tt_disp_eng_overlay_wrapper` | overlay+dispatch | Dispatch overlay |
| `tt_neo_overlay_wrapper` | `tt_neo_overlay_wrapper` | Context switch, L2 |
| `tt_trin_noc_niu_router_wrap` | NoC router wrapper | Trinity NoC router |
| `tt_trin_disp_eng_noc_niu_router_east` | dispatch NIU east | Dispatch east NIU |
| `tt_trin_disp_eng_noc_niu_router_west` | dispatch NIU west | Dispatch west NIU |
| `trinity_noc2axi_ne_opt` | NOC2AXI NE corner (X=0,Y=4) | NE corner gateway (single-row) |
| `trinity_noc2axi_nw_opt` | NOC2AXI NW corner (X=3,Y=4) | NW corner gateway (single-row) |
| `trinity_noc2axi_router_ne_opt` | Composite tile (X=1,Y=4+Y=3) | NOC2AXI + Router (two-row) |
| `trinity_noc2axi_router_nw_opt` | Composite tile (X=2,Y=4+Y=3) | NOC2AXI + Router (two-row) |
| `tt_tensix_with_l1` | `tt_tensix_with_l1` | Full Tensix tile |

**Synthesis defines:** `SYNTHESIS NEO_PD_PROTO TDMA_NEW_L1 RAM_MODELS USE_VERILOG_MEM_ARRAY TT_CUSTOMER TRINITY`

### 15.2 Tensix Tile Internal Floorplan

Recommended placement order (top=NoC, bottom=L1):

```
  ┌────────────────────────────────────────────────┐
  │  NoC flit ports / de_to_t6 control wires       │  (top edge)
  ├────────────────────────────────────────────────┤
  │  tt_noc_niu_router_dfx  (5 clocks pass-through)│  ← N1B0 DFX wrapper
  ├────────────────────────────────────────────────┤
  │  tt_overlay_wrapper_dfx (5 clocks pass-through)│  ← N1B0 DFX wrapper
  │  ┌──────────────────────────────────────────┐  │
  │  │ tt_neo_overlay_wrapper (overlay,L2,ctx)  │  │
  │  └──────────────────────────────────────────┘  │
  ├────────────────────────────────────────────────┤
  │  tt_instrn_engine_wrapper_dfx (1 clk PT)       │  ← N1B0 DFX wrapper
  │  └── tt_instrn_engine_wrapper (BRISC+TRISC×3)  │
  ├─────────────────────────┬──────────────────────┤
  │  tt_fpu_gtile[0]        │  tt_fpu_gtile[1]     │
  │  (cols 0–7: SRCA,DEST)  │  (cols 8–15)         │
  │         ↑  ↑            │      ↑  ↑            │
  │    srcb_rd_tran broadcast (symmetric)           │
  ├─────────────────────────┴──────────────────────┤
  │  tt_srcb_registers  (BOTTOM CENTER — symmetric) │
  ├────────────────────────────────────────────────┤
  │  tt_tdma (Unpack CH0/CH1, Pack CH0/CH1)        │
  ├────────────────────────────────────────────────┤
  │  tt_t6_l1_partition_dfx (3 clocks pass-through)│  ← N1B0 DFX wrapper
  │  └── tt_t6_l1_partition (16×3072×128 + arb)    │  (bottom)
  └────────────────────────────────────────────────┘
```

**N1B0 DFX wrapper summary (all are pass-throughs):**
- `tt_noc_niu_router_dfx`: 5 clock ports (aon, clk, ovl_core, ai, ref) — all `assign o = i`
- `tt_overlay_wrapper_dfx`: 5 clock ports (core, uncore, ai, nocclk_aon, ref) — all `assign o = i`
- `tt_instrn_engine_wrapper_dfx`: 1 clock port — `assign o = i`; IJTAG chain for FPU G-Tile 0/1 is `ifdef INCLUDE_TENSIX_NEO_IJTAG_NETWORK` (absent in N1B0)
- `tt_t6_l1_partition_dfx`: 3 clock ports (predfx_clk, postdfx_clk from `i_clk`; postdfx_nocclk from `i_nocclk`) — all pass-through; IJTAG for 4 T6 core groups absent

### 15.3 Critical Placement Rules

| Block | Rule | Reason |
|-------|------|--------|
| `tt_srcb_registers` | Center between G-Tile[0] and G-Tile[1] | Symmetric `srcb_rd_tran` broadcast wire length |
| `tt_t6_l1_partition` | Bottom (largest block) | Close to TDMA; SRAM power ring at bottom rail |
| L1 `tt_t6_l1_superarb` | Adjacent to bank array | Minimize shared data bus wire |
| ICG cells (DEST/SRCB) | Row immediately above latch arrays | Minimize gated-clock wire; one ICG per datum |
| MOVD2A path | Short DEST→SRCA wire | Recurrence path latency sensitive |
| Reset sync cells | Near clock domain boundary | 4-cycle MCP; no hold-fix needed |

### 15.4 CDC Crossings

| Crossing | From | To | Mechanism |
|----------|------|----|-----------|
| TDMA L1 req → NoC ack | AICLK | NOCCLK | `tt_async_fifo_wrapper` |
| NoC flit → L1 write | NOCCLK | AICLK | `tt_async_fifo_wrapper` |
| FDS timer → flit inject | dm_clk | NOCCLK | `tt_async_fifo_wrapper` |
| FDS input filter | NOCCLK | AICLK reg | `tt_async_fifo_wrapper` |
| Reset sync (noc) | async | NOCCLK | `tt_libcell_sync3r` (3-stage) |
| Reset sync (ai) | async | AICLK | `tt_libcell_sync3r` |
| JTAG → internal | TCK | AICLK | MCP setup=3, hold=2 |
| SMN interrupt | SMN clk | AICLK | MCP setup=2, hold=1 |

### 15.5 SDC Path Groups

**FPU (`tt_fpu_gtile.final.sdc`):**
`dest_cgen`, `mtile_tag`, `srcb_rows`, `srca_columnize`, `dest_wrdat0`–`7`, `mtile_pipe0`–`4`, `o_shared_rddata`, `o_movd2src`

**CPU (`tt_instrn_engine_wrapper.final.sdc`):**
`o_srca_wr_tran`, `o_srcb_rd_tran0/1`, `o_l1_sbank_rw_intf`, `o_l1_arb_*_intf`, `o_gtile_math`, `o_neo`

---

## 16. SW Programming Guide

### 16.1 APB Register Access

Each column x has one APB bus. APB is the primary control plane for all tile-level configuration:

```
APB bus x → NOC2AXI tile at (x, Y=4) → SFR register bank
                                        → ATT (address translation)
                                        → SMN security ranges
                                        → Mesh config (harvest)
```

**Address map (per APB bus):**
- `0x000–0x3FF`: NOC2AXI SFR (ATT, SMN, mesh config)
- `0x400–0x7FF`: EDC CSR (via `edc_apb_*` separate port, 6-bit address)

### 16.2 EDC Configuration

For each EDC node per column:
1. After reset, write `INIT_CNT` = startup initialization count (wait for ring to settle)
2. Write `MCPDLY` = multicycle path delay for the ring's CDC crossing
3. Set `BYPASS_EN = 1` for any harvested tiles in this column's ring

**EDC IRQ handling:** `o_edc_fatal_err_irq` → firmware reset of affected ring; `o_edc_cor_err_irq` → count and continue.

### 16.3 Harvest Configuration

To permanently disable a defective Tensix tile at (x, y):
1. Assert `i_tensix_reset_n[getTensixIndex(x,y)] = 0`
2. Assert `ISO_EN[x + 4*y] = 1`
3. Write `mesh_config_override` in the NIU APB bank for column x: decrement `noc_y_size`, update `disable_endpoints` bitmask
4. Write `BYPASS_EN` in EDC CSR for the column x ring node corresponding to (x, y)
5. Update ATT: remap any routes that previously targeted harvested tile

### 16.4 NoC Routing Configuration

**DOR (default, no SW setup needed):**
- NoC uses XY dimension-order routing automatically
- No CSR writes required for basic operation

**Dynamic routing (enabled in N1B0):**
- Set `EnableDynamicRouting` at compile time (already set to 1)
- Header flits carry 928-bit route list; NIU at destination overwrites return slots
- For custom routes, firmware builds header flits with explicit carried-list entries

**ATT programming (for address translation):**
- Write endpoint translation table via APB: set `att_endpoint[ep_index].mask = <mask>`
- Write routing translation: set `att_routing[entry].routing_bits = <bits>`
- ATT is used by AXI2NOC path to translate 56-bit address to NoC destination

### 16.5 AXI Interface

**AXI master (NOC2AXI — NPU reads DRAM):**
- NoC packet targets NIU tile → NIU issues AXI AR → DRAM responds → NIU routes response back
- `AXI_SLV_OUTSTANDING_READS=64` (max in-flight per tile)
- No SW setup needed; driven entirely by NoC traffic

**AXI slave (AXI2NOC — host writes NPU):**
- Host issues AXI AW → address decoded by NIU → NoC packet injected to Tensix L1
- Address format: 56-bit gasket `{reserved[55:52], target[51:48], endpoint_id[47:40], tlb_index[39:36], addr[35:0]}`
- `aruser/awuser` field carries `noc2axi_tlbs_a_regmap_t` struct for TLB-based translation

### 16.6 Tensix Tile Programming (TRISC/BRISC)

**BRISC** programs:
```c
// DMA read: L1 ← DRAM
noc_async_read(src_addr_dram, dst_l1_addr, size);
noc_async_write(src_l1_addr, dst_addr_dram, size);
noc_async_write_barrier();  // wait for all outstanding writes
```

**TRISC0** (TDMA unpack):
```
UNPACK_A(l1_base, srca_addr, rows, cols, format=BF16)
UNPACK_B(l1_base, srcb_addr, rows, cols, format=BF16)
```

**TRISC1** (math/FPU):
```
MATH_MATMUL(dst_row, src_row, cols)  // MAC into DEST
SFPU_EXP(dest_row)                   // element-wise EXP
```

**TRISC2** (TDMA pack):
```
PACK(dest_row, l1_base, rows, cols, format=BF16)
```

**Key SFRs:**
| SFR | Description |
|-----|-------------|
| `MATH_CONFIG` | Format select (BF16/INT16/INT8/FP8), rounding mode |
| `TDMA_SRC_ADDR` | L1 base address for unpack |
| `TDMA_DST_ADDR` | L1 base address for pack |
| `SFPU_OP` | SFPU operation select |
| `L1_ACC_BASE` | L1 accumulator region base |
| `DEST_RD_CTRL` | DEST read row/column control |

### 16.7 Performance Monitor (Simulation Only)

`noc2axi_perf_monitor` is instantiated inside each NIU tile (not synthesized):
```bash
# Enable in simulation
vcs +PERF_MONITOR_VERBOSITY=2 +MONITOR_ROUND_TRIP_LATENCY=1 ...
```

Output ports (`output real`): `o_avg_rd_latency`, `o_max_rd_latency`, `o_avg_wr_latency`, `o_total_rd_txn`, etc.

### 16.8 AXI Dynamic Delay Buffer (Simulation/Emulation)

`axi_dynamic_delay_buffer` injects programmable latency on AXI channels:
```systemverilog
// Set 32-cycle AXI read latency
delay_buffer.delay_cycles = 32;
// Must wait for pipeline empty before changing:
wait(fifo_count == 0);
delay_buffer.delay_cycles = 64;
// Zero = pass-through (no added latency)
delay_buffer.delay_cycles = 0;
```

---

## 17. RTL File Reference

### 17.1 Top-Level and Package

| Module | File |
|--------|------|
| `trinity` (top) | `used_in_n1/rtl/trinity.sv` |
| `trinity_pkg` (4×5) | `used_in_n1/rtl/targets/4x5/trinity_pkg.sv` |
| `trinity_noc2axi_router_ne_opt` | `used_in_n1/rtl/trinity_noc2axi_router_ne_opt.sv` |
| `trinity_noc2axi_router_nw_opt` | `used_in_n1/rtl/trinity_noc2axi_router_nw_opt.sv` |
| `trinity_noc2axi_ne_opt` | `used_in_n1/rtl/trinity_noc2axi_ne_opt.sv` |
| `trinity_noc2axi_nw_opt` | `used_in_n1/rtl/trinity_noc2axi_nw_opt.sv` |

### 17.2 DFX Modules

| Module | File |
|--------|------|
| `tt_noc_niu_router_dfx` | `used_in_n1/rtl/dfx/tt_noc_niu_router_dfx.sv` |
| `tt_overlay_wrapper_dfx` | `used_in_n1/rtl/dfx/tt_overlay_wrapper_dfx.sv` |
| `tt_instrn_engine_wrapper_dfx` | `used_in_n1/rtl/dfx/tt_instrn_engine_wrapper_dfx.sv` |
| `tt_t6_l1_partition_dfx` | `used_in_n1/rtl/dfx/tt_t6_l1_partition_dfx.sv` |

### 17.3 Testbench / Verification Infrastructure

| Module | File | Synthesizable |
|--------|------|--------------|
| `noc2axi_perf_monitor` | `used_in_n1/rtl/noc2axi_perf_monitor.sv` | NO |
| `axi_dynamic_delay_buffer` | `used_in_n1/rtl/axi_dynamic_delay_buffer.sv` | YES |

### 17.4 Baseline Trinity (shared modules, unchanged in N1B0)

| Module | File |
|--------|------|
| `trinity_noc2axi_n_opt` | `rtl/trinity_noc2axi_n_opt.sv` |
| `trinity_router` | `rtl/trinity_router.sv` |
| `tt_tensix_with_l1` | `rtl/tt_tensix_with_l1.sv` |
| `tt_dispatch_top_east/west` | `rtl/tt_dispatch_top_east.sv`, `tt_dispatch_top_west.sv` |
| `tt_overlay_wrapper` | `rtl/tt_overlay_wrapper.sv` |
| `tt_t6_l1_partition` | `rtl/tt_t6_l1_partition.sv` |
| `tt_instrn_engine_wrapper` | `rtl/tt_instrn_engine_wrapper.sv` |
| `tt_fpu_gtile` / `tt_fpu_v2` | `rtl/tt_fpu_gtile.sv`, `tt_fpu_v2.sv` |
| `tt_tdma` | `rtl/tt_tdma.sv` |
| `tt_reg_bank` (DEST) | `rtl/tt_reg_bank.sv` |
| `tt_srcb_registers` | `rtl/tt_srcb_registers.sv` |

### 17.5 P&R and Synthesis Files

| File | Purpose |
|------|---------|
| `synth/run_syn.tcl` | Partition list + synthesis flow driver |
| `synth/<part>/<part>.final.sdc` | Per-partition SDC (timing constraints, path groups, MCPs) |
| `rtl/trinity_par_guide.md` | Full P&R guide (this document references it) |

### 17.6 Reference HDDs (detailed sub-system docs)

| Document | Contents |
|----------|---------|
| `N1B0_HDD_v0.1.md` | Trinity-level HDD (grid, hierarchy, ports, NoC connections) |
| `N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` | NOC2AXI_ROUTER internal cross-row wiring and parameters |
| `N1B0_DFX_HDD_v0.1.md` | All 4 DFX modules, IJTAG chain topology |
| `N1B0_PerfMonitor_HDD_v0.1.md` | noc2axi_perf_monitor simulation guide |
| `N1B0_AXI_Dynamic_Delay_HDD_v0.1.md` | axi_dynamic_delay_buffer programming guide |
| `rtl/NIU_HDD_v0.1.md` | NIU/AXI bridge full design spec |
| `rtl/router_decode_HDD_v0.5.md` | NoC router address decoding, flit types, ATT, routing modes |
| `rtl/tensix_core_HDD.md` | Tensix core detailed spec (TRISC, FPU, SFPU, TDMA, L1) |
| `rtl/Harvest_HDD.md` | Full harvest architecture (5 mechanisms, RTL-sourced) |
| `rtl/EDC_HDD.md` | EDC ring full design spec |
| `rtl/trinity_full_hierarchy.md` | Full SRAM/latch inventory with baseline+N1B0 delta |

---

*N1B0 NPU HDD v0.1 — RTL-sourced, auto-generated 2026-03-18*
*All sections based on RTL at `/secure_data_from_tt/20260221/used_in_n1/`*

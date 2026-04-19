# Trinity Tensix — Place & Route Guide
**Version:** 0.1  **Date:** 2026-03-18  **Source:** RTL at `/secure_data_from_tt/20260221/`

---

## 1. Partition Strategy

### 1.1 Defined Partitions

The synthesis and P&R flow is built around **15 hierarchical partitions** defined in `synth/run_syn.tcl`. Each partition is synthesized independently with its own SDC file and then assembled in a hierarchical P&R run.

| Partition Name | Module / Block | Key Contents |
|---|---|---|
| `tt_fpu_gtile` | `tt_fpu_gtile` | One G-Tile: M-Tiles, FP Lanes ×8col, SRCB pipe stage, DEST slice |
| `tt_instrn_engine_wrapper` | `tt_instrn_engine_wrapper` | BRISC+TRISC×3, MOP engine, stall scoreboard, replay unit, cluster_sync |
| `tt_t6_l1_partition` | `tt_t6_l1_partition` | L1 SRAM banks ×16, superarb, ECC, phase generator |
| `tt_dispatch_engine` | `tt_dispatch_engine` | FDS FSM, dispatch L1 staging, NoC NIU router |
| `tt_disp_eng_l1_partition` | `tt_disp_eng_l1_partition` | Dispatch Engine private L1 SRAM |
| `tt_disp_eng_overlay_wrapper` | overlay + dispatch | Dispatch overlay integration |
| `tt_neo_overlay_wrapper` | `tt_neo_overlay_wrapper` | Tensix overlay (context switch, L2 cache) |
| `tt_trin_noc_niu_router_wrap` | NoC router wrapper | Trinity-specific NoC NIU router |
| `tt_trin_disp_eng_noc_niu_router_east` | dispatch NIU east | Dispatch Engine east NIU + router |
| `tt_trin_disp_eng_noc_niu_router_west` | dispatch NIU west | Dispatch Engine west NIU + router |
| `trinity_noc2axi_n_opt` | NOC2AXI north | North AXI gateway tile |
| `trinity_noc2axi_ne_opt` | NOC2AXI northeast | NE corner AXI gateway |
| `trinity_noc2axi_nw_opt` | NOC2AXI northwest | NW corner AXI gateway |
| `tt_tensix_with_l1` | `tt_tensix_with_l1` | Full Tensix tile (FPU+TDMA+TRISC+L1) |
| `trinity_router` | `trinity_router` | Router tile (APB+EDC config, no data path) |

**Synthesis invocation:**
```tcl
# Single partition:
setenv TENSIX_PARTITION tt_fpu_gtile
dc_shell -f synth/run_syn.tcl

# All partitions:
setenv TENSIX_PARTITION all
dc_shell -f synth/run_syn.tcl
```

**Synthesis defines used:**
```
SYNTHESIS  NEO_PD_PROTO  TDMA_NEW_L1  RAM_MODELS
USE_VERILOG_MEM_ARRAY  TT_CUSTOMER  TRINITY
```

`RAM_MODELS` and `USE_VERILOG_MEM_ARRAY` enable behavioral SRAM models during synthesis — actual macros are swapped in during P&R memory insertion step.

---

### 1.2 Partition Hierarchy Diagram

```
trinity.sv  (top)
│
├── DISPATCH_E / DISPATCH_W  (row 1, col 0 / col 3)
│     ├── tt_dispatch_engine          ← partition
│     │     ├── tt_disp_eng_l1_partition   ← partition (private L1)
│     │     └── tt_trin_disp_eng_noc_niu_router_east/west  ← partition
│     └── tt_disp_eng_overlay_wrapper ← partition
│
├── ROUTER  (row 1, col 1 / col 2)
│     └── trinity_router              ← partition
│
├── TENSIX  (rows 2–4, cols 0–3)  ×12 instances
│     └── tt_tensix_with_l1          ← partition
│           ├── tt_t6_l1_partition   ← partition (L1 SRAM)
│           ├── tt_instrn_engine_wrapper  ← partition (CPU threads)
│           ├── tt_fpu_gtile  ×2     ← partition (FPU, one per G-Tile)
│           └── tt_neo_overlay_wrapper   ← partition (overlay/context)
│
└── NOC2AXI  (row 0)
      ├── trinity_noc2axi_n_opt      ← partition
      ├── trinity_noc2axi_ne_opt     ← partition
      └── trinity_noc2axi_nw_opt     ← partition
```

---

## 2. Physical Floorplan — Block Placement

### 2.1 Trinity 4×5 Grid Physical Layout

```
         col 0          col 1          col 2          col 3
        ┌──────────────┬──────────────┬──────────────┬──────────────┐
row 0:  │ NOC2AXI_NE   │ NOC2AXI_N    │ NOC2AXI_N    │ NOC2AXI_NW   │
        │ (AXI GW, NE) │ (AXI GW, N)  │ (AXI GW, N)  │ (AXI GW, NW) │
        ├──────────────┼──────────────┼──────────────┼──────────────┤
row 1:  │ DISPATCH_E   │ ROUTER       │ ROUTER       │ DISPATCH_W   │
        │ (FDS, L1)    │ (APB/EDC)    │ (APB/EDC)    │ (FDS, L1)    │
        ├──────────────┼──────────────┼──────────────┼──────────────┤
row 2:  │ TENSIX[0,2]  │ TENSIX[1,2]  │ TENSIX[2,2]  │ TENSIX[3,2]  │
        ├──────────────┼──────────────┼──────────────┼──────────────┤
row 3:  │ TENSIX[0,3]  │ TENSIX[1,3]  │ TENSIX[2,3]  │ TENSIX[3,3]  │
        ├──────────────┼──────────────┼──────────────┼──────────────┤
row 4:  │ TENSIX[0,4]  │ TENSIX[1,4]  │ TENSIX[2,4]  │ TENSIX[3,4]  │
        └──────────────┴──────────────┴──────────────┴──────────────┘

NoC connections: East-West + North-South mesh (DOR routing)
de_to_t6 control wires: row 1 → rows 2-4 per column (direct wire, not NoC)
EDC ring: traverses all tiles in ring order (see EDC_HDD)
```

### 2.2 Tensix Tile Internal Floorplan (P&R view)

#### 2.2.1 The Core Routing Problem: NoC→L1 Write Bus

Before showing the floorplan, you must understand the dominant routing constraint that invalidates a simple top-to-bottom stack.

**RTL-verified signal path** (`tt_niu_to_l1_port_ctrl_write.sv:182–219`):

```
tt_trin_noc_niu_router_wrap
  └── tt_noc_niu_router
        └── tt_niu
              └── tt_niu_to_l1_port_ctrl_write
                    ├── mem_req_fifo  (tt_noc_fifo_async, 308-bit, depth=8)
                    │   write-clk: NOCCLK,  read-clk: AICLK
                    │
                    └── output: noc_pre_sbank_wr_intf[3:0]  ← AICLK domain
                                 (4 write ports × 128-bit data)
                                 = 512 bits total
                                 ↓
                         tt_t6_l1_partition.noc_pre_sbank_wr_intf[3:0]
                         (tt_t6_l1_partition.sv:179)
```

Key facts:
- The CDC async FIFO is **inside** `tt_trin_noc_niu_router_wrap` — the bus leaving the NOC module is already in AICLK domain
- The bus is **4 × 128 bit = 512 bits** wide (plus address 18-bit, byte-enable 16-bit per port)
- This bus must connect `tt_trin_noc_niu_router_wrap` directly to `tt_t6_l1_partition`

**Why a simple vertical stack fails:**

```
  WRONG (naive stack):
  ─────────────────────────────────────────
  [tt_trin_noc_niu_router_wrap]   ← top
          │
          │  512-bit noc_pre_sbank_wr_intf
          │  crosses EVERY block below:
          │
  [tt_neo_overlay_wrapper]        ← blocks in the way!
  [tt_instrn_engine_wrapper]
  [tt_fpu_gtile[0/1]]
  [tt_srcb_registers]
  [tt_tdma]
          │
  [tt_t6_l1_partition]            ← bottom
```

Routing 512 bits vertically through 5 other blocks is a **congestion disaster**: it consumes routing tracks in every intermediate block, blocks P&R placement of those blocks, and increases wire RC delay on a bandwidth-critical path.

---

#### 2.2.2 Corrected Floorplan — Side Channel Strategy

The solution is a **dedicated left-edge routing channel** for the NoC→L1 write bus. The NOC module stays at the top (close to mesh flit connections), L1 stays at the bottom (close to TDMA), and the wide write bus bypasses all intermediate blocks via a reserved channel on the left side of the tile.

```
  ◄──── tile width ──────────────────────────────────────────────────────────►

  LEFT EDGE               MAIN TILE BODY                        RIGHT EDGE
  (NoC→L1 channel)                                              (reserved)

  ┌─────────┬──────────────────────────────────────────────────────────────┐
  │ TOP AON │  flit N/S/E/W ports + de_to_t6 (top mesh connections)        │  ← §9 AON strip
  ├─────────┼──────────────────────────────────────────────────────────────┤
  │         │                                                               │
  │  NOC→L1 │  tt_trin_noc_niu_router_wrap                                 │
  │  WRITE  │  ┌─────────────────────────────────────────────────────────┐ │
  │  CHANNEL│  │ tt_noc_niu_router: mesh routing (N/E/S/W)               │ │
  │  (512b) │  │ tt_niu: endpoint table, sec_fence                       │ │
  │   │     │  │ tt_niu_to_l1_port_ctrl_write: CDC FIFO (inside here!)   │ │
  │   │     │  │ output: noc_pre_sbank_wr_intf[3:0] ─────────────────────┼─┼──► exits left
  │   │     │  └─────────────────────────────────────────────────────────┘ │
  │   │     ├──────────────────────────────────────────────────────────────┤
  │   │     │  tt_neo_overlay_wrapper  (overlay, TRISC I-cache ×3, L2)     │
  │   │     ├──────────────────────────────────────────────────────────────┤
  │   │     │  tt_instrn_engine_wrapper  (BRISC+TRISC×3, MOP, scoreboard)  │
  │   │     ├──────────────────────┬───────────────────────────────────────┤
  │   │     │  tt_fpu_gtile[0]     │  tt_fpu_gtile[1]                      │
  │   │     │  (cols 0–7)          │  (cols 8–15)                          │
  │   │     │  SRCA, DEST[0–511]   │  SRCA, DEST[512–1023]                 │
  │   │     │        ↑ srcb_rd_tran broadcast ↑                            │
  │   │     ├──────────────────────┴───────────────────────────────────────┤
  │   │     │  tt_srcb_registers  (BOTTOM CENTER — equidistant G-Tiles)    │
  │   │     ├──────────────────────────────────────────────────────────────┤
  │   │     │  tt_tdma  (Unpack CH0/CH1 ← L1 below; Pack CH0/CH1 → L1)    │
  │   │     ├──────────────────────────────────────────────────────────────┤
  │   ▼     │  tt_t6_l1_partition  (16 SRAM banks + superarb + ECC)        │
  │ ──►─────┼──► noc_pre_sbank_wr_intf[3:0] enters superarb from left     │
  │         │   (NoC write bypassed TDMA; enters L1 superarb directly)     │
  ├─────────┼──────────────────────────────────────────────────────────────┤
  │ BOT AON │  South ISO cells, clock spine out, EDC mux                   │  ← §9 AON strip
  └─────────┴──────────────────────────────────────────────────────────────┘
```

#### 2.2.3 NoC→L1 Write Channel Specification

| Parameter | Value | Source |
|---|---|---|
| Bus name | `noc_pre_sbank_wr_intf[3:0]` | `tt_t6_l1_partition.sv:179` |
| Write ports | 4 (`L1_CFG.NOC_WR_PORT_CNT`) | `tt_noc_niu_router.sv:386` |
| Data width per port | 128-bit | `tt_t6_l1_pkg.sv:789` |
| Address width per port | 18-bit `[21:4]` | `tt_t6_l1_pkg.sv:787` |
| Byte-enable width per port | 16-bit | `tt_t6_l1_pkg.sv:788` |
| **Total bus width (data only)** | **4 × 128 = 512 bits** | |
| CDC FIFO width | 308-bit (data+addr+BE+ctrl) | `tt_niu_to_l1_port_ctrl_write.sv:183` |
| CDC FIFO depth | 8 entries (write req) | `tt_niu_to_l1_port_ctrl_write.sv:183` |
| CDC FIFO clock | write=NOCCLK, read=AICLK | `tt_niu_to_l1_port_ctrl_write.sv:185–186` |
| Bus clock domain at L1 port | AICLK (CDC already done inside NOC module) | |
| Response bus | 1-bit ACK, depth=2, write=AICLK, read=NOCCLK | `tt_niu_to_l1_port_ctrl_write.sv:202–219` |

#### 2.2.4 Left-Edge Channel Physical Sizing

```
  Left channel width estimate (metal M3, 0.1µm pitch):
  ─────────────────────────────────────────────────────
  4 write ports × (128 data + 18 addr + 16 BE + ctrl) ≈ 4 × 170 = 680 signal wires
  At M3 0.1µm pitch → 68µm strip width
  + shield wires (one per ±5 signals) ≈ +14µm
  Total: ~82µm channel reserved on left edge

  Channel height = full tile height (~500–800µm at 5nm/7nm node)
  Routing layer: M3 (vertical runs preferred; avoid shared layer with clock mesh)
```

**P&R tool directives:**
```tcl
# Reserve left-edge routing channel for NoC→L1 write bus
create_routing_blockage -layers {M1 M2} \
    -bbox {tile_left  tile_bottom  [expr tile_left + 82] tile_top}
# (M3 and above left clear for the write bus; M1/M2 blocked for cell placement)

# No cell placement in the channel
create_placement_blockage \
    -bbox {tile_left  tile_bottom  [expr tile_left + 82] tile_top} \
    -type hard

# Assign noc_pre_sbank_wr_intf nets to the channel layer
set_net_routing_rule noc_pre_sbank_wr_intf* \
    -preferred_routing_layer M3 \
    -preferred_direction vertical
```

#### 2.2.5 L1 Superarb Port Alignment

The 4 NoC write ports connect to `tt_t6_l1_superarb` (inside `tt_t6_l1_partition`). For the side-channel strategy to work, the superarb must have its NoC write input ports accessible from the left edge:

```
  tt_t6_l1_partition physical layout — revised (with NoC write channel):
  ──────────────────────────────────────────────────────────────────────
  LEFT EDGE                    MAIN BANK ARRAY              RIGHT EDGE
  ┌────────────────────────────────────────────────────────────────────┐
  │ noc_pre_sbank  │  bank[0]  bank[1]  bank[2]  bank[3]              │
  │ _wr_intf[3:0]  │  bank[4]  bank[5]  bank[6]  bank[7]              │
  │  (from channel)│  bank[8]  bank[9]  bank[10] bank[11]             │
  │       │        │  bank[12] bank[13] bank[14] bank[15]             │
  │       ▼        ├──────────────────────────────────────────────────┤
  │  tt_t6_l1      │  tt_t6_l1_superarb  (arbitrator)                 │
  │  _superarb     │  ECC encoders/decoders                           │
  │  (left port)   │  phase generator                                 │
  │                │  TDMA ports (top, from above)                    │
  └────────────────────────────────────────────────────────────────────┘
  Top of L1: TDMA ports (from TDMA block directly above, short bus)
  Left of L1: NoC write ports (from side channel, long but unobstructed)
  BRISC load/store: via tt_t6_l1_superarb top port (AICLK, short from CPU above)
```

#### 2.2.6 Placement Rationale — Corrected Table

| Block | Placement | Reason |
|---|---|---|
| `tt_t6_l1_partition` | Bottom | TDMA is the highest-bandwidth client (directly above); SRAM power ring at bottom rail |
| `tt_tdma` | Directly above L1 | TDMA↔L1 bus is widest (pack/unpack); must be adjacent |
| `tt_srcb_registers` | Above TDMA, center | Symmetric `srcb_rd_tran` broadcast to G-Tile[0] left and G-Tile[1] right |
| `tt_fpu_gtile[0/1]` | Above SRCB, side-by-side | 16-column datapath; DEST→SRCA feedback (MOVD2A) is short within tile |
| `tt_instrn_engine_wrapper` | Above FPU | MOP decode→FPU control goes down; I-cache fetch path short to overlay above |
| `tt_neo_overlay_wrapper` | Above CPU | Context-switch SRAM close to overlay L2; BIU (EDC) co-located |
| `tt_trin_noc_niu_router_wrap` | Top (below AON strip) | Mesh flit N/S/E/W ports at tile top edge — short to neighboring tiles; CDC FIFO inside; NoC→L1 write exits left edge via channel |
| **NoC→L1 write bus channel** | **Left edge, full height** | **Bypasses all intermediate blocks; 512-bit bus unobstructed; enters L1 superarb from left** |
| AON strips | Top + Bottom edges | ISO cells, clock feed-through, EDC bypass (§9) |

---

## 3. Clock Domain Boundaries

### 3.1 Clock Domains

| Clock | Domain Label in SDC | Typical Relative Freq | Modules |
|---|---|---|---|
| `i_ai_clk` | `AICLK` | Highest (compute) | All TRISC, FPU, SFPU, TDMA, L1, DEST, cluster_sync, PRNG, droop detector |
| `i_noc_clk` | `NOCCLK` | Lower | NoC endpoint (flit Rx/Tx, VC buffers), FDS `o_bus`, L1 NoC write path |
| `i_dm_clk` | (Dispatch Engine only) | Medium | FDS FSM (`ad_count_q`), auto-dispatch FIFO, FDS dispatch register file |

### 3.2 CDC Points and Mechanisms

All CDC crossings use `tt_async_fifo_wrapper` (async FIFO) or `tt_libcell_sync3` (3-stage synchronizer). No RTL-level `(* dont_touch *)` attributes — CDC cells are called out via SDC false-path or multicycle-path exceptions.

```
┌─────────────────────────────────────────────────────────────────┐
│  CDC crossing           │ From      │ To        │ Mechanism     │
├─────────────────────────────────────────────────────────────────┤
│  TDMA L1 req → NoC ack  │ AICLK     │ NOCCLK    │ async FIFO 4e │
│  NoC flit → L1 write    │ NOCCLK    │ AICLK     │ async FIFO 4e │
│  FDS timer → flit inject│ dm_clk    │ NOCCLK    │ tt_async_fifo │
│  FDS input filter       │ NOCCLK    │ AICLK reg │ tt_async_fifo │
│  Reset sync (noc reset) │ async src │ NOCCLK    │ tt_libcell_sync3r (3-stage) |
│  Reset sync (ai reset)  │ async src │ AICLK     │ tt_libcell_sync3r |
│  JTAG → internal        │ TCK       │ AICLK     │ MCP setup=3, hold=2 |
│  BISR → internal        │ BISR clk  │ AICLK     │ MCP setup=3, hold=2 |
│  SMN interrupt          │ SMN clk   │ AICLK     │ MCP setup=2, hold=1 |
│  Harvest fuse → reset   │ async     │ AICLK     │ MCP setup=2, hold=1 |
└─────────────────────────────────────────────────────────────────┘
```

**SDC multicycle path examples** (from `tt_t6_l1_partition.final.sdc`):
```tcl
# JTAG I2O (slow scan path into fast AI clock)
set_multicycle_path -end -setup 3 -from [get_pins jtag_sync/*/CK] -to [get_clocks AICLK*]
set_multicycle_path -end -hold  2 -from [get_pins jtag_sync/*/CK] -to [get_clocks AICLK*]

# Reset synchronizer (NOCCLK domain)
set_multicycle_path -end -setup 4 -from [get_pins *noc_clk_reset_sync*/CK] -to [get_clocks NOCCLK*]
set_multicycle_path -end -hold  3 -from [get_pins *noc_clk_reset_sync*/CK] -to [get_clocks NOCCLK*]

# Reset synchronizer (AICLK domain)
set_multicycle_path -end -setup 4 -from [get_pins *ai_clk_reset_sync*/CK] -to [get_clocks AICLK*]
set_multicycle_path -end -hold  3 -from [get_pins *ai_clk_reset_sync*/CK] -to [get_clocks AICLK*]
```

### 3.3 Clock Gating Cell

All clock gates use `tt_clkgater` → maps to `tt_libcell_clkgate` in synthesis:

```systemverilog
// tt_libcell_clkgate.sv — behavioral model (sim) / tech cell (synthesis)
module tt_libcell_clkgate (
    input  i_CK,     // source clock
    input  i_E,      // functional enable
    input  i_TE,     // test enable (scan bypass)
    output o_ECK     // gated output clock
);
// Behavioral: latch enable on LOW phase, AND with clock
// always @(i_E or i_CK or i_TE) if (~i_CK) latched_en = i_E || i_TE;
// assign o_ECK = i_CK & latched_en;

// In SYNTHESIS_WITH_LIBCELL mode: replaced by PDK ICG cell
```

**P&R implications:**
- ICG cells must be placed close to the register array they gate (minimize gated-clock wire length)
- In `tt_reg_bank`, 8 ICG instances are placed per datum group — tool should honor cell proximity constraints or use a dedicated ICG row at the boundary of the latch array
- Test enable (`i_TE`) ties to scan controller — ICG cells must be in the scan clock domain OCC (on-chip clock controller) reach

---

## 4. Memory Macros

### 4.1 SRAM Types Used

All SRAMs use parametric wrapper modules (`tt_mem_wrap_*`). During P&R, the tool substitutes vendor SRAM macros. No `(* ram_style *)` RTL attributes — macro type is determined by the wrapper module name.

| Wrapper Pattern | Port Config | Example Instance | Block |
|---|---|---|---|
| `tt_mem_wrap_Dx128_sp_nomask_*_t6_l1` | SP, no byte-mask | 1024×128 | L1 SRAM banks |
| `tt_mem_wrap_Dx72_sp_wmask_trisc_icache` | SP, byte-mask | 256×72, 512×72 | TRISC I-cache |
| `tt_mem_wrap_Dx52_sp_wmask_trisc_local_memory` | SP, byte-mask | 256×104, 512×52, 1024×52 | TRISC LDM |
| `tt_mem_wrap_Dx2048_2p_nomask_d2d_*` | 2P, no mask | 256×2048 | NoC VC input buffers |
| `tt_mem_wrap_32x1024_sp_wmask_overlay_*` | SP, byte-mask | 32×1024 | Overlay context switch |

**Memory control fields** (from `tt_mem_ctrl_pkg.sv`):

| Field | Bits | Description |
|---|---|---|
| `ADME[7:5]` | 3 | Adjust drive strength of memory output (power vs. speed) |
| `WRME[4:3]` | 2 | Write margin enable — widen write pulse for reliability |
| `MCS[2:1]` | 2 | Memory cell select — selects speed/power bin of SRAM bitcell |
| `MCSW[0]` | 1 | Memory cell select for write path |
| `reg_mem_retention_enable` | 1 | Enable data retention during power-down |

**Memory types available:**
- `RA1_UHD` — Register-array, ultra-high density (area-optimized, slower)
- `RA1_HS` — Register-array, high-speed
- `RF1_UHD` — Register-file, ultra-high density
- `RF1_HS` — Register-file, high-speed
- `RD2_UHD / RD2_HS` — Read dual-port
- `RF2_HS` — Register-file dual-port, high-speed
- `VROM_HD` — ROM, high-density

**L1 SRAM config** (`mem_cfg_l1_t`):
- Uses `ra1_uhd_emc_min` — UHD variant with EMC (electromagnetic compatibility) margin setting
- Prioritizes area over raw speed (L1 is bandwidth-bound, not latency-bound)

**Tensix SRAM config** (`mem_cfg_tensix_t`):
- Uses mix: `ra1_uhd_min`, `rf1_uhd_min`, `ra1rf1_hs`
- I-cache uses HS variant (instruction fetch is on critical path)
- LDM uses UHD variant (occasional load/store, area is priority)

### 4.2 L1 SRAM Physical Placement

L1 has 16 banks. The superarbitrator (`tt_t6_l1_superarb`) must be placed adjacent to the bank array to minimize the shared data bus wire length:

```
  tt_t6_l1_partition physical layout (bottom of Tensix tile):

  ┌─────────────────────────────────────────────────────────────┐
  │  bank[0]  bank[1]  bank[2]  bank[3]  ← row of SRAM macros  │
  │  bank[4]  bank[5]  bank[6]  bank[7]                         │
  │  bank[8]  bank[9]  bank[10] bank[11]                        │
  │  bank[12] bank[13] bank[14] bank[15]                        │
  ├─────────────────────────────────────────────────────────────┤
  │  tt_t6_l1_superarb  + tt_t6_l1_arb  (control logic row)    │
  │  ECC encoders/decoders (prim_secded_147_138 / 149_140)      │
  │  phase generator (l1_phase_root 2-bit counter)              │
  └─────────────────────────────────────────────────────────────┘
  Ports:
    Top: read/write from TDMA (AICLK)
    Top: write from NoC endpoint (NOCCLK, through async FIFO)
    Top: read/write from BRISC load/store (AICLK)
```

---

## 5. Synthesis Path Groups (Critical Paths)

The SDC files define explicit path groups for DC synthesis. These groups guide the P&R tool on which timing paths are architecturally significant. Key groups from `tt_fpu_gtile.final.sdc`:

| Path Group | Description | P&R Implication |
|---|---|---|
| `dest_cgen` | DEST register clock-enable generation | ICG cells near DEST latch array |
| `mtile_tag` | M-Tile instruction tag FIFO | Short path; tag must track data pipeline latency |
| `srcb_rows` | SRCB row pipeline stage (exp→man) | `tt_srcb_pipe_stage` close to G-Tile boundary |
| `srca_columnize` | SRCA column mux (lane selection) | `tt_srca_lane_sel` adjacent to SRCA register |
| `dest_wrdat0`–`dest_wrdat7` | DEST write data per group | 8 parallel paths; balance wire length across 16 cols |
| `mtile_pipe0`–`mtile_pipe4` | M-Tile pipeline stages 0–4 | FP Lane 5-stage pipeline; register boundaries per stage |
| `o_shared_rddata` | Shared read data output | Output register at partition boundary |
| `o_movd2src` | MOVD2A: DEST→SRCA feedback | Latency-sensitive (RNN recurrence); minimize feedback length |

From `tt_instrn_engine_wrapper.final.sdc`:

| Path Group | Description |
|---|---|
| `o_srca_wr_tran` | SRCA write transaction to FPU |
| `o_srcb_rd_tran0/1` | SRCB broadcast to G-Tile 0/1 |
| `o_l1_sbank_rw_intf` | L1 superbank read/write interface |
| `o_l1_arb_*_intf` | L1 arbitration interface |
| `o_gtile_math` | Math instruction to G-Tile |
| `o_neo` | Overlay interface output |

---

## 6. Latch Array Physical Constraints

### 6.1 `tt_reg_bank` (DEST Register File)

The DEST register file uses `always_latch` + `tt_clkgater` (ICG) — not SRAM. P&R must treat this as standard-cell logic with special timing requirements.

**Latch timing rule:**
- Data and enable must be stable **before** the clock goes HIGH (setup window = LOW phase of clock)
- The ICG (`tt_clkgater`) generates `gated_clk`; the latch opens when `gated_clk` is HIGH
- Write control stabilization latches (`stabilization_latch_cg`) capture write-enables on the LOW phase, one cycle before data

**P&R constraints needed:**
```
# Latch always_latch requires half-cycle timing analysis
# ICG cell must be placed within wire-length budget of associated datum
# Recommended: define latch groups matching DEST array structure
# One ICG per datum (4096 total for full DEST array)
# Place ICG cells in a row immediately above the latch storage cells
```

**Path group `dest_cgen`** in SDC covers the ICG enable generation path — this is often the setup-critical path for latch-based register files.

### 6.2 `tt_srcb_registers`

Same latch + ICG structure as DEST. Physical placement must be:
- Centered between `gen_gtile[0]` (left 8 columns) and `gen_gtile[1]` (right 8 columns)
- Below the G-Tile blocks, above the TDMA block
- The broadcast bus `srcb_rd_tran` fans out symmetrically left and right

---

## 7. Reset Hierarchy and P&R Implications

### 7.1 Reset Tree

```
tensix_reset_n (tile-level, from trinity.sv)
├── i_nocclk_reset_n → NoC endpoint, FDS o_bus
│     SDC: set_multicycle_path setup=4, hold=3 (reset sync cells)
├── i_uncore_reset_n → L1, TDMA, FPU, SFPU, DEST, cluster_sync
│     SDC: set_multicycle_path setup=4, hold=3
└── i_core_reset_n[N] → TRISC[N] pipeline, I-cache valid bits, GPR
      Independent per thread; no hold-time issue (same AICLK domain)
```

**P&R implication:** Reset synchronizer cells (`tt_libcell_sync3r`) must be placed close to the clock domain boundary they serve (NOC or AI domain). The 4-cycle MCP means reset propagation latency is expected — no need for minimum-delay fixing on the reset path.

---

## 8. EDC Ring Physical Routing

### 8.1 Ring Topology and Direction

The EDC ring is a **serial daisy-chain** — not a mesh. There are **4 independent rings**, one per column (X=0..3). Each ring is a vertical **U-shape**: it travels DOWN the direct path (Segment A), makes a U-turn at Y=0, and returns UP the loopback path (Segment B) to the BIU at the overlay in Y=4.

```
         col X  — one independent EDC ring
         ─────────────────────────────────────────
         BIU (tt_edc1_biu_soc_apb4_wrap, Y=4)
          │ Segment A: DOWN                ▲ Segment B: UP
          │ edc_egress_intf[X*5+Y]         │ loopback_edc_ingress_intf[X*5+Y]
          ▼                                │
         Dispatch/Router (Y=3) ── EDC nodes (NOC vc/ECC/parity, SEC_NOC_CONF, REG_APB_NOC)
          │  demux: sel=0 → tile; sel=1 → bypass wire
          ▼                                │
         Tensix (Y=2) ─── EDC nodes (NOC router → L1 hub → T0→T1→T3→T2)
          │  mux: sel=0 ← tile out; sel=1 ← bypass wire
          ▼                                │
         Tensix (Y=1)                      │
          ▼                                │
         Tensix (Y=0) ── U-turn ───────────┘
              edc_egress_intf[X*5+0] → loopback_edc_ingress_intf[X*5+0]
```

The inter-tile wires at ring level are purely combinational — `tt_edc1_intf_connector` instances (no flip-flops, no clock). The clock is only needed inside `tt_edc1_node` and `tt_edc1_serial_bus_repeater` instances.

---

### 8.2 Clock Requirements for EDC Ring Nodes

Each `tt_edc1_node` and `tt_edc1_serial_bus_repeater` takes an `i_clk` input. The clock domain used depends on where in the tile the node resides:

| Location | Clock Domain | Module | Notes |
|---|---|---|---|
| BIU (`tt_edc1_biu_soc_apb4_wrap`) | APB4 / AICLK | `tt_neo_overlay_wrapper` | APB4 speed; same domain as overlay |
| NOC router nodes (`tt_noc_overlay_edc_wrapper`) | NOCCLK | `tt_trin_noc_niu_router_wrap` | VC buffer SRAM, ECC, parity errors |
| Tensix compute nodes (`tt_instrn_engine_wrapper`) | AICLK (`postdfx_clk`) | per sub-core T0/T1/T2/T3 | IE_PARITY, SRCB, UNPACK, PACK, SFPU, GPR, CFG, THCON |
| L1 hub nodes (`tt_t6_l1_partition`) | AICLK | `tt_t6_misc`, `tt_t6_l1_wrap2` | T6_MISC, L1W2 SRAM nodes |
| Repeaters inside `tt_instrn_engine_wrapper` | AICLK | `edc_thcon_1_to_l1_flex_repeater`, `edc_l1_flex_to_egress_repeater` (DEPTH=1) | retiming stages within AICLK domain |
| Feedthrough repeaters in `tt_t6_l1_partition` | AICLK | T0↔T1, T3↔T2 inter-sub-core paths (DEPTH=1) | same-domain retiming |
| `tt_edc1_intf_connector` (all inter-tier connectors) | **None (combinational)** | `edc_conn_*` | no flip-flops; wire only |
| Loopback repeater in overlay | AICLK | `overlay_loopback_repeater` | Segment B → back to BIU |

**Key rule:** The ring physically crosses from NOCCLK (NOC router nodes) to AICLK (Tensix/L1 nodes) within each tile. This is the only clock boundary that the ring crosses. It is handled by the toggle protocol — see §8.4.

**P&R clock assignment checklist:**
- Assign `tt_edc1_node` and `tt_edc1_serial_bus_repeater` instances inside NOC wrappers to `NOCCLK` group
- Assign all other EDC node and repeater instances to `AICLK` group
- `tt_edc1_intf_connector` instances have no clock pin — assign to `unclocked` or leave ungrouped
- BIU clock must be tied to the column's APB4 clock (same as `tt_neo_overlay_wrapper` top-level clock)

---

### 8.3 Why `MCPDLY=7` for `init_cnt` (async_init Clock Requirement)

This is one of the least-obvious timing constraints in the EDC ring. Understanding it is critical for correct P&R SDC.

#### What `async_init` does

`async_init` is a single-wire signal driven by the BIU's `CTRL.INIT` register bit. It propagates **asynchronously** (no flip-flops, no synchronization) along the ring wire from node to node via direct combinational pass-through in each `tt_edc1_state_machine`:

```systemverilog
// tt_edc1_state_machine.sv:1129
assign egress_intf.async_init = ingress_intf.async_init;  // pure wire through
```

It reaches every node nearly simultaneously (wire propagation delay only). Each node then locally synchronizes this async signal to its own clock:

```systemverilog
// tt_edc1_state_machine.sv:1132
tt_libcell_sync3r init_sync3r (
    .i_CK (i_clk),          // node's OWN clock — could be AICLK or NOCCLK
    .i_RN (i_reset_n),
    .i_D  (ingress_intf.async_init),
    .o_Q  (init)             // synchronized init — resets all node state machines
);
```

The 3-stage synchronizer (`tt_libcell_sync3r`) guarantees **metastability safety** but adds exactly **3 clock cycles of latency** from when `async_init` arrives at the node's input to when `init` is asserted inside that node.

#### Why 7 cycles

The BIU must hold `async_init=1` long enough for **every node on the ring to have seen and processed it**. The BIU counts 7 cycles of its own clock (`i_clk`, same as BIU's AICLK domain) before auto-clearing `CTRL.INIT` via `hwclr`:

```systemverilog
// tt_edc1_bus_interface_unit.sv:320–333
localparam int unsigned MCPDLY = 7;   // minimum clear propagation delay
localparam int unsigned CNT_W  = 3;   // $clog2(MCPDLY+1) = 3

always_ff @(posedge i_clk) begin : init_counter
    if (!i_reset_n) begin
        init_cnt <= '0;
    end else if ((init_cnt==0) && init || (init_cnt != 0)) begin
        if (init_cnt == CNT_W'(MCPDLY))
            init_cnt <= '0;   // self-clear after 7 cycles
        else
            init_cnt <= init_cnt + CNT_W'(1);
    end
end
```

The 7 comes from worst-case synchronizer latency across clock domains:

```
async_init wire delay:   ~0 cycles  (combinational passthrough, no FFs on path)
3-stage sync latency:     3 cycles  (guaranteed safe capture window — worst case)
Register setup margin:   +1 cycle   (output of sync → node's internal logic)
Clock frequency ratio:   +1–2 cycles (BIU may run at higher freq than slowest node)
Metastability margin:    +1 cycle   (extra safety for slow clock domains)
                         ─────────
Total budget:             7 cycles  (at BIU clock, guarantees all nodes are initialized)
```

The critical insight is: because the ring spans AICLK and NOCCLK domains, and NOCCLK < AICLK, the 3-stage sync in a NOCCLK node takes **more real time** than 3 AICLK cycles. By counting 7 BIU-clock cycles (AICLK), the BIU ensures that even the slowest NOCCLK domain node has had enough real time to capture and process the init signal.

#### P&R SDC implications

`async_init` is intentionally asynchronous — it must be excepted from all timing checks:

```tcl
# async_init propagates as a pure wire — no timing analysis needed on this path
# It is a functional async signal, not a metastability hazard (sampled inside each node
# through its own 3-stage sync, which is already constrained separately)
set_false_path -from [get_pins */edc1_biu*/CTRL_INIT*] \
               -through [get_nets *async_init*]

# The 3-stage sync inside each node:
set_multicycle_path -end -setup 3 \
    -from [get_cells *init_sync3r*] -to [get_clocks *]
set_multicycle_path -end -hold 2 \
    -from [get_cells *init_sync3r*] -to [get_clocks *]
```

> **Do NOT set a single-cycle timing constraint on `async_init` wires** — they are long multi-tile routes that are intentionally outside the normal setup/hold budget.

---

### 8.4 CDC Across the Ring — Toggle Protocol Mechanics

The EDC ring crosses between NOCCLK (NOC router segment) and AICLK (Tensix segment) within each tile. The toggle handshake protocol (`req_tgl[1:0]` / `ack_tgl[1:0]`) provides metastability-safe CDC without requiring explicit 2FF synchronizers on the data path.

#### How toggle CDC works

```
NOCCLK sender (NOC router node egress):
  1. Sample req_tgl after previous ack returns → previous transfer complete
  2. Toggle req_tgl[1:0] to new value (one bit changes per transaction)
  3. Drive data[15:0], data_p[0] stable BEFORE toggling req_tgl
  4. Wait until ack_tgl == req_tgl (ack comes back from AICLK receiver)

AICLK receiver (Tensix node ingress):
  1. Detect req_tgl change (using previous-value register → XOR or compare)
  2. Sample data[15:0] and data_p[0] — guaranteed stable after toggle
  3. Echo req_tgl back on ack_tgl — this ack crosses back from AICLK to NOCCLK

NOCCLK sender:
  5. ack_tgl crossing from AICLK to NOCCLK — metastability possible here
     → ack_tgl is a single bit that changes once per transaction
     → sender samples ack_tgl with a standard 2FF synchronizer (or 3FF)
  6. Once ack sampled, data consumption confirmed → next fragment can be sent
```

The protocol guarantees:
- **Data stability**: `data` and `data_p` are stable before `req_tgl` toggles, and remain stable until `ack_tgl` is returned → no metastability on data lines
- **Ack safety**: `ack_tgl` is a single-bit signal toggling once per transfer → can be sampled with a standard 2FF or 3FF synchronizer
- **Throughput**: one fragment per round-trip toggle cycle → limited by max(AICLK period, NOCCLK period) × 2 (RTT)

#### Clock domain crossing in the ring (per tile):

```
    NOCCLK domain                      AICLK domain
    ─────────────────────────────────────────────────────
    NOC router EDC node                Tensix EDC node
     (i_clk = NOCCLK)                  (i_clk = AICLK)
          │                                  │
    egress.req_tgl ──────── wire ──────► ingress.req_tgl
    egress.data    ──────── wire ──────► ingress.data
    egress.ack_tgl ◄─2FF sync──────────  ingress.ack_tgl
          │                                  │
          │   edc_egress_t6_byp_intf         │
          │   (bypass wire stays in          │
          │    NOCCLK domain for part,       │
          │    re-enters AICLK at mux)       │
```

#### SDC treatment for toggle lines

```tcl
# req_tgl, data, data_p: single-cycle fan-out in NOCCLK → captured in AICLK
# These are multi-cycle by protocol (data valid for entire toggle cycle)
set_multicycle_path -end -setup 2 \
    -from [get_clocks NOCCLK] -through [get_nets *edc*req_tgl*] \
    -to [get_clocks AICLK]
set_multicycle_path -end -hold 1 \
    -from [get_clocks NOCCLK] -through [get_nets *edc*req_tgl*] \
    -to [get_clocks AICLK]

# Data lines: same multi-cycle exception (stable for full toggle round-trip)
set_multicycle_path -end -setup 2 \
    -from [get_clocks NOCCLK] -through [get_nets *edc*data*] \
    -to [get_clocks AICLK]

# ack_tgl: crossing back from AICLK to NOCCLK — synchronizer in sender
set_multicycle_path -end -setup 3 \
    -from [get_clocks AICLK] -through [get_nets *edc*ack_tgl*] \
    -to [get_clocks NOCCLK]
set_multicycle_path -end -hold 2 \
    -from [get_clocks AICLK] -through [get_nets *edc*ack_tgl*] \
    -to [get_clocks NOCCLK]
```

> **`DISABLE_SYNC_FLOPS=1` (default)**: no built-in 2FF synchronizers are instantiated in the RTL for `ack_tgl`. The physical synthesis/P&R tool must insert them, or the SDC above must be used with the assumption that the toggle protocol provides metastability safety through the multi-cycle hold margin.

---

### 8.5 Repeater Placement Guide

The EDC ring uses two types of repeaters, each with different P&R implications:

#### Type 1: `tt_edc1_intf_connector` — Combinational pass-through (no clock)

```systemverilog
// Purely wire-assigns — no flip-flop, no clock pin
assign egress_intf.req_tgl    = ingress_intf.req_tgl;
assign egress_intf.data       = ingress_intf.data;
assign egress_intf.data_p     = ingress_intf.data_p;
assign egress_intf.async_init = ingress_intf.async_init;
assign egress_intf.err        = ingress_intf.err;
assign ingress_intf.ack_tgl   = egress_intf.ack_tgl;
```

Used for:
- Inter-sub-core feedthroughs inside `tt_t6_l1_partition` (T0↔T1 entry/exit, T2↔overlay, etc.)
- Top-level inter-tile wires (`edc_direct_conn_nodes`, `edc_loopback_conn_nodes` in `trinity.sv:442–454`)

**P&R rule:** No timing closure concern on these — they are plain wire connections. Route them as data signals (no shield, no special layer). The combinational timing through them is covered by the multi-cycle SDC on the toggle lines.

#### Type 2: `tt_edc1_serial_bus_repeater` (DEPTH=N) — Registered pipeline stage

```systemverilog
module tt_edc1_serial_bus_repeater #(parameter int DEPTH = 1) (
    input  logic i_clk, i_reset_n,
    edc1_serial_bus_intf_def.ingress ingress_intf,
    edc1_serial_bus_intf_def.egress  egress_intf
);
// DEPTH register stages on BOTH req (forward) and ack (return) paths
```

Instances in the design:

| Instance name | DEPTH | Module | Location | Clock |
|---|---|---|---|---|
| `edc_thcon_1_to_l1_flex_repeater` | 1 | `tt_instrn_engine_wrapper` | between THCON_1 node and L1_flex sub-module | AICLK |
| `edc_l1_flex_to_egress_repeater` | 1 | `tt_instrn_engine_wrapper` | after L1_flex node, before wrapper egress | AICLK |
| (T0↔T1 feedthrough in L1 partition) | 1 | `tt_t6_l1_partition` | repeater inside L1 between sub-core boundaries | AICLK |
| (T3↔T2 feedthrough in L1 partition) | 1 | `tt_t6_l1_partition` | repeater inside L1 between sub-core boundaries | AICLK |
| `overlay_loopback_repeater` | (varies) | `tt_neo_overlay_wrapper` | Segment B loopback return, before BIU | AICLK |
| N1B0 loopback repeater (Y=3 row) | 6 | `NOC2AXI_ROUTER_NE/NW_OPT` | cross-row loopback in N1B0 variant | NOCCLK |
| N1B0 loopback repeater (Y=4 row) | 4 | `NOC2AXI_ROUTER_NE/NW_OPT` | cross-row loopback at top | NOCCLK |

**P&R rules for registered repeaters:**

```
Rule 1: Register-to-register budget
  The timing path for the EDC repeater is:
    FF[stage N] → combinational logic (none, just a wire) → FF[stage N+1]
  This is a standard single-cycle flip-flop path in the repeater's clock domain.
  The tool handles this automatically — no special constraint needed.

Rule 2: Inter-tile wire budget (between last FF of one tile and first FF of next)
  The wire from the repeater's egress FF (in tile Y) to the receiving node/repeater
  in the next tile (Y±1) must close timing in one clock cycle of the FASTER of
  the two clocks (AICLK or NOCCLK).

  Maximum allowable inter-tile wire length:
    L_max = (T_clk - T_setup - T_ck2q) / (R_wire × C_wire)
  At AICLK 1 GHz: T_clk = 1ns → L_max ≈ 400–600µm (process dependent)

Rule 3: Loopback path (Segment B)
  The loopback repeaters (N1B0 DEPTH=6 at Y=3, DEPTH=4 at Y=4) mean the ack
  path from BIU to far-tile and back has DEPTH×2 register stages.
  This increases EDC ring round-trip latency but does NOT affect correctness —
  the toggle protocol is self-throttling. No extra SDC needed for these.

Rule 4: ack path return latency
  Each DEPTH=1 repeater adds 1 cycle of latency on ack[1:0] return path.
  With 4 DEPTH=1 repeaters in a single sub-core chain:
    ack round-trip within one tile ≈ 4+4 = 8 AICLK cycles extra
  This is acceptable (EDC is a low-bandwidth diagnostic path).
  Do NOT try to optimize this with false-path SDC — the ack is a real timing path.
```

---

### 8.6 Harvest Bypass Wires — Routing Considerations

The bypass wire (`edc_egress_t6_byp_intf`) runs from:
- **Source**: `tt_edc1_serial_bus_demux.egress_out1` inside `tt_trin_noc_niu_router_wrap` (at the tile boundary between Y=3 and Y=2, or between Y=2/Y=1/Y=0 tiles)
- **Destination**: `tt_edc1_serial_bus_mux.ingress_in1` inside `tt_neo_overlay_wrapper` (at the far end of the same tile)

```
  Y=3 tile (DISPATCH/ROUTER)
  ┌─────────────────────────────────────────────────────────┐
  │  NOC router               │      Overlay wrapper        │
  │  [demux] out1 ────────────┼──► [mux] in1                │
  │    (sel=1, harvest bypass wire spans entire tile width)  │
  └─────────────────────────────────────────────────────────┘
```

**P&R routing rules for bypass wires:**

| Rule | Detail |
|---|---|
| Power domain | Bypass wire and mux/demux cells **must be in AON domain** — they must function even when the associated tile is powered off (see §9.5) |
| Wire length | Spans one full tile width (~4µm–6µm estimate for Trinity tile) — must close at toggle-protocol multi-cycle timing, not single-cycle |
| Timing constraint | Apply `set_multicycle_path -setup 2 -hold 1` on bypass wire (same as other toggle req/data lines); it is a combinational path from demux to mux |
| Both segments | The bypass applies to Segment A (DOWN) and must also be replicated for Segment B (UP return path) — same wire, same demux/mux logic. Both sel=0 and sel=1 states are covered by the single `edc_mux_demux_sel` signal |
| CDC on bypass | If the bypass wire crosses from NOCCLK (demux at NOC router) to AICLK (mux at overlay), apply the same toggle-line MCP as §8.4 |

---

### 8.7 EDC Ring Physical Placement Summary

```
  One tile column — recommended EDC routing layer/placement:
  ────────────────────────────────────────────────────────────

  BIU (Y=4 overlay, AICLK)
      │ edc_egress_intf[X*5+4]  ─► short wire to:
      │
  NOC router (Y=3/4, NOCCLK)       ← Segment A enters here
      │ EDC nodes (N/E/S/W vc_buf, ECC, parity)
      │ demux (sel=0/1)
      │ edc_egress_intf[X*5+3]  ─► inter-tile wire to Y=2:
      │   → tt_edc1_intf_connector (edc_direct_conn_nodes) → purely combinational
      │
  Tensix (Y=2, AICLK)              ← clock domain crossing: NOCCLK → AICLK
      │ NOC router nodes (NOCCLK) → Tensix cluster nodes (AICLK)
      │   toggle CDC crossing here (see §8.4)
      │ L1 hub → T0 → T1 → T3 → T2 (all AICLK, DEPTH=1 repeaters within)
      │ mux → edc_loopback_conn_nodes → inter-tile loopback wire to Y=3
      │
  Tensix Y=1, Y=0:   same pattern as Y=2
      │ U-turn at Y=0: direct connection (tt_edc1_intf_connector)
      │
  Loopback path (Segment B):
      Y=0 → Y=1 → Y=2 → Y=3 → BIU
      overlay_loopback_repeater at each tile re-drives the loopback wire
      N1B0 uses DEPTH=6 (Y=3), DEPTH=4 (Y=4) registered repeaters here
```

**Layer assignment recommendation:**
- EDC ring wires: intermediate metal layer (e.g., M3/M4) — not top-level global routing layer
- Not performance-critical — can share layer with other control signals
- Do not route `async_init` on minimum-width track — it must propagate reliably across all tiles without significant RC delay
- Bypass wires (spanning one tile width): route on a dedicated short straight segment at the AON domain boundary strip

---

## 9. Harvest P&R — Flit Isolation and Power Domain Strategy

This is the most P&R-critical aspect of harvest and was missing from the original guide.

### 9.1 The Core Problem: Powered-Off Outputs Into Live Tile Inputs

**RTL evidence** (`trinity.sv` lines 248–278): every tile position in the 4×5 grid receives all **4 directional flit wires** (N/S/E/W) with direct wire assignments — there are **no dedicated bypass wires** that skip around a tile:

```systemverilog
// North (trinity.sv:248-252)
assign flit_in_req[x][y][POSITIVE][Y_AXIS]  = flit_out_req[x][y+1][NEGATIVE][Y_AXIS];

// South (trinity.sv:254-258)
assign flit_in_req[x][y][NEGATIVE][Y_AXIS]  = flit_out_req[x][y-1][POSITIVE][Y_AXIS];

// East/West: same pattern for X_AXIS
```

This means:

```
Live tile (y+1)
     │  flit_out_req[x][y+1][NEGATIVE][Y_AXIS]  (driven from live power domain)
     ▼
Harvested tile (y)          ← power rail OFF
     │  flit_out_req[x][y][POSITIVE][Y_AXIS]    ← FLOATING if no ISO cell!
     ▼
Live tile (y-1)             ← floating input corrupts live router
```

When the Tensix power rail is cut, `flit_out_req` from the harvested tile becomes an undriven net. Without isolation cells, this floating wire drives the live neighboring tile's `flit_in_req` input — a functional failure and potential latch-up risk.

---

### 9.2 Power Domain Partition for a Tensix Tile

A harvested Tensix tile requires **two distinct power regions**:

```
┌────────────────────────────────────────────────────────────────┐
│  TENSIX TILE (x, y) — harvested                                │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  SWITCHABLE POWER DOMAIN (VDD_TENSIX_xy)                 │  │
│  │  Power rail can be cut when tile is harvested            │  │
│  │  Contents: FPU, SFPU, DEST, TDMA, CPU, L1 SRAM array,   │  │
│  │            TRISC pipelines, overlay, cluster_sync        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  ALWAYS-ON DOMAIN (VDD_AON)                              │  │
│  │  Must stay powered even when tile is harvested           │  │
│  │  Contents:                                               │  │
│  │    • ISO cell array (all output signals to neighbors)    │  │
│  │    • Clock chain feed-through (column abutment wires)    │  │
│  │    • EDC ring bypass mux/demux logic                     │  │
│  │    • de_to_t6 / t6_to_de wire termination resistors     │  │
│  │    • Harvest fuse register + ISO_EN latch                │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

### 9.3 ISO Cell Placement — All Output Signals That Cross the Power Boundary

The rule: **every signal driven FROM the switchable domain that feeds INTO a live tile or shared wire must have an ISO cell at the power domain output boundary**, inside the always-on region.

#### Flit Output Signals (most critical)

| Signal | Direction | Drives | ISO Cell Safe Value |
|---|---|---|---|
| `flit_out_req[x][y][POSITIVE][Y_AXIS]` | North output | `flit_in_req[x][y+1]` of live tile above | `'0` (no valid flit) |
| `flit_out_req[x][y][NEGATIVE][Y_AXIS]` | South output | `flit_in_req[x][y-1]` of live tile below | `'0` |
| `flit_out_req[x][y][POSITIVE][X_AXIS]` | East output | `flit_in_req[x+1][y]` of live tile right | `'0` |
| `flit_out_req[x][y][NEGATIVE][X_AXIS]` | West output | `flit_in_req[x-1][y]` of live tile left | `'0` |
| `flit_in_resp[x][y][POSITIVE][Y_AXIS]` | North resp | credits back to live tile above | `'0` (no credit) |
| `flit_in_resp[x][y][NEGATIVE][Y_AXIS]` | South resp | credits back to live tile below | `'0` |
| `flit_in_resp[x][y][POSITIVE][X_AXIS]` | East resp | credits back | `'0` |
| `flit_in_resp[x][y][NEGATIVE][X_AXIS]` | West resp | credits back | `'0` |

> **ISO safe value = `'0`** for all flit outputs: bit `valid=0` in the flit struct means "no flit present" — live neighbors receive no spurious flits, and credit counters are not decremented.

#### Other Outputs Requiring ISO Cells

| Signal | Drives | ISO Safe Value |
|---|---|---|
| `t6_to_de[x]` (4-bit) | Dispatch Engine row 1 always-on | `'0` (no status) |
| L1 write ACK / superarb output | TDMA above (if shared) | `'0` |
| EDC output (tile's forward ring signal) | Next tile in ring | Bypassed by EDC mux (see §9.5) |

#### Signals NOT Requiring ISO (inputs TO the harvested tile — they come from live domains)

| Signal | Source | Why No ISO Needed |
|---|---|---|
| `flit_in_req[x][y][*]` | Neighboring live tiles | Driven from live domain; safely driven into de-asserted inputs |
| `de_to_t6[x]` (4-bit) | Dispatch Engine (always-on) | Dispatch drives a live wire; harvested tile's input is floated but benign |
| Clock chain input | Adjacent tile abutment (live) | Always-on; passes through |
| EDC ring input | Previous tile in ring | Handled by EDC bypass mux |

---

### 9.4 ISO Control Signal — `ISO_EN`

The ISO enable signal must:
- Come from the **always-on domain** (it cannot come from the tile being powered off)
- Be set to `1` **before** the power rail is cut
- Remain `1` while the tile is powered off
- Be set to `0` **after** the power rail is restored and reset is de-asserted

```
Harvest sequence (SW + HW):
  1. [SW] Program mesh_start_y / mesh_end_y via EDC to exclude tile row
         (DOR routing now avoids this row — no new flits will arrive)
  2. [SW] Assert i_tensix_reset_n[TensixIndex] = 0
         (tile logic frozen in reset state, outputs go to reset values)
  3. [HW/SW] Assert ISO_EN[TensixIndex] = 1
         (ISO cells clamp all outputs to safe '0 before power cut)
  4. [HW] Cut VDD_TENSIX_xy power rail
         (SRAM data lost unless retention_enable was set first)
  5. [HW] ISO cells hold outputs at '0 indefinitely
```

```
Power restore sequence (if needed for BIST or debug):
  1. [HW] Restore VDD_TENSIX_xy power rail
  2. [HW/SW] De-assert ISO_EN[TensixIndex] = 0 (after voltage stable)
  3. [SW] De-assert i_tensix_reset_n[TensixIndex] = 1
  4. [SW] Restore mesh_start_y / mesh_end_y to include tile row
```

**P&R implication:** `ISO_EN` register must be in the always-on domain. Its routing to each ISO cell must not cross through the switchable domain.

---

### 9.5 Clock Chain Feed-Through (Column Abutment)

**RTL evidence** (Explore agent finding, `trinity.sv` lines 237–246): the per-column clock routing chain (abutted physically, not a tree) **passes through every tile position** including harvested ones. This is necessary to deliver clocks to tiles below a harvested row.

```
      row 0: NOC2AXI  ─── clock abutment ──►
      row 1: ROUTER   ─── clock abutment ──►   (always powered)
      row 2: TENSIX   ─── clock abutment ──►   ← harvested: power off
      row 3: TENSIX   ─── clock abutment ──►   ← depends on row 2's chain!
      row 4: TENSIX   ─── clock abutment ──►
```

**The problem:** If row 2 is powered off, the clock abutment feed-through wires inside row 2 are in the switchable domain → clock does not reach rows 3 and 4.

**Required P&R solution:** The clock feed-through path through a potentially-harvested tile must be placed in the **always-on domain**, OR the design must use a separate clock tree that bypasses harvested tiles. Options:

| Strategy | Description | P&R Implementation |
|---|---|---|
| **AON feed-through** (recommended) | Place clock spine buffers inside each tile in AON sub-domain | Assign `clock_feed_thru_buf_*` cells to AON power domain |
| **Parallel clock tree** | Run a separate clock tree that never goes through Tensix tiles | Additional clock routing; more area |
| **Only harvest bottom rows** | Harvest only row 4 (bottommost); no tile below needs feed-through | Design restriction; limits yield recovery |

The SDC MCP for harvest (`setup=2, hold=1`) suggests a synchronizer path in the harvest configuration path — this synchronizer cell must also be in the AON domain.

---

### 9.6 EDC Ring Bypass — P&R Requirements

The Harvest HDD (Section 8) documents an EDC bypass mux/demux per tile:

```
  EDC ingress ──► tt_edc1_serial_bus_demux ──► tile internal EDC nodes
                          │ sel=1 (harvested)
                          └──────────────────► bypass wire (skip tile)
                                                      │
  EDC egress  ◄── tt_edc1_serial_bus_mux  ◄──────────┘
```

**P&R requirements:**
- Both `tt_edc1_serial_bus_demux` and `tt_edc1_serial_bus_mux` **must be in the AON domain** — they carry signals from live EDC ring through the harvested tile
- The `sel` signal (harvest enable from fuse or reset) must also be AON
- The bypass wire itself does not need ISO cells (it is a pass-through, not a signal from the dead domain)
- Place bypass mux/demux near the tile boundary (short bypass wire)

---

### 9.7 Harvest Floorplan Recommendation

Given the above constraints, the recommended physical floorplan for each Tensix tile is:

```
  ┌────────────────────────────────────────────────────────────────┐
  │  TOP EDGE  ──── AON STRIP (always powered) ────────────────── │
  │  • ISO cells for all N/E/W flit outputs (to neighbors)        │
  │  • Clock feed-through buffer (passes column clock downward)   │
  │  • de_to_t6 input buffer (from Dispatch, always-on)           │
  │  • t6_to_de ISO cell (output from tile going UP to Dispatch)  │
  │  • EDC bypass demux (ingress)                                 │
  │  • ISO_EN latch + harvest fuse register                       │
  ├────────────────────────────────────────────────────────────────┤
  │  SWITCHABLE CORE — VDD_TENSIX_xy                              │
  │  (all compute logic, SRAMs, FPU, TDMA, CPU)                   │
  │  ...  (same as Section 2.2 internal floorplan)  ...           │
  ├────────────────────────────────────────────────────────────────┤
  │  BOTTOM EDGE  ── AON STRIP ───────────────────────────────── │
  │  • ISO cells for all S flit outputs (to tile below)           │
  │  • EDC bypass mux (egress)                                    │
  │  • SRAM retention_enable tie (AON, asserted before power off) │
  └────────────────────────────────────────────────────────────────┘
```

**Why strips at both top AND bottom edges?**
- North neighbor is row 1 (Dispatch/Router, always-on) — ISO needed on top edge
- South neighbors are rows 3/4 (potentially live Tensix tiles) — ISO needed on bottom edge
- East/West neighbors are same-row Tensix (may be live) — ISO needed on side edges (included in top strip for simplicity or side strips)

---

### 9.8 Dynamic Routing Reconfiguration — Sequence Requirement

The DOR routing algorithm avoids harvested rows via `mesh_start_y` and `mesh_end_y` programmed through the EDC ring (NOC2AXI tile, node 192). **This must happen before ISO_EN is asserted:**

```
If routing reconfiguration happens AFTER power cut:
  → Flits already in-flight may arrive at the harvested tile boundary
  → ISO cells block them (good) but credit counters in live neighbors may deadlock

Correct order:
  [1] mesh_end_y -= harvested_rows  (no new flits enter harvested row)
  [2] Drain in-flight flits (wait for NoC to quiesce)
  [3] ISO_EN = 1
  [4] Power cut
```

**P&R implication:** The mesh_start_y / mesh_end_y programming path (EDC ring → NOC2AXI APB → router mesh config register) must be functional before any Tensix tile is powered off. This path lives entirely in the always-on NOC2AXI and Router tiles (row 0 and row 1) — no constraint on Tensix power domain ordering.

---

### 9.9 NoC Credit Handling at Harvested Tile Boundary

Live tiles maintain **flit credits** for each virtual channel toward each neighbor. When a neighbor is harvested:

- The harvested tile's ISO cells clamp `flit_in_resp` (credit return) to `'0` → live tile never receives credits back from that direction
- If the live tile sent credits to the now-dead neighbor before power-off, those credits are **permanently lost**
- The live tile's VC toward the harvested direction must be **disabled** (credit count = 0, no flit injection in that direction)

**Mechanism:** The DOR routing algorithm, once `mesh_end_y` is reduced, will never compute a route that exits toward the harvested row. So no credits are consumed in that direction after reconfiguration. Credits already issued before reconfiguration are a SW responsibility to drain before asserting `mesh_end_y` change.

**P&R implication:** No additional physical logic needed — this is handled by the routing algorithm. But ensure the `flit_in_resp` ISO cells are placed before the VC credit counter inputs in live tiles.

---

### 9.10 TOP–BOTTOM AON Strip Connectivity When Core Is Powered Off

This section answers the critical question: **how do the TOP and BOTTOM AON strips stay connected, and how do signals pass through the tile, when the switchable core is completely off?**

The answer differs per signal class. The tile cross-section below shows each path explicitly:

```
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  LIVE TILE ABOVE (Y+1)                                                      │
  │  drives: flit_out_req[N] → wire down │  drives: column_clk → wire down      │
  └───────────────────────┬──────────────┼──────────────────────────────────────┘
                          │              │
  ════════════════════════╪══════════════╪═══════════════════════════════════════
                          │              │
  ┌ TOP AON STRIP ─────────▼──────────────▼──────────────────────────────────── ┐
  │  ISO cell (N flit in)   EDC demux    Clock feed-through buffer (IN)          │
  │  flit_in_req[N]──►[ISO]    │         col_clk_in ──►[BUF_AON]──► col_clk_out │
  │  ISO drives flit_out_req[N]='0        │                │                    │
  │  (to live neighbor above ← clamped)   │                │ ← this wire is     │
  │                           │(bypass)   │   AON SPINE    │   the only path    │
  │  ISO cell (E flit)        │           │   WIRE (runs   │   for clock when   │
  │  ISO cell (W flit)        │           │   vertically   │   core is off      │
  │  ISO_EN latch             │           │   alongside    │                    │
  └────────────────────────── ┼ ──────────┼── switchable ──┼────────────────────┘
                              │           │   domain)      │
  ┌ SWITCHABLE CORE ──────────╪───────────╪────────────────╪──────────────────── ┐
  │                           │ bypass    │ AON spine wire │                     │
  │  tt_neo_overlay_wrapper   │ wire      │ (NOT in this   │ col_clk NOT         │
  │  tt_instrn_engine_wrapper │ (stays in │  domain)       │ available here      │
  │  tt_fpu_gtile[0/1]        │  AON)     │                │ when powered off    │
  │  tt_srcb_registers        │           │                │                     │
  │  tt_tdma                  │           │                │                     │
  │  tt_t6_l1_partition       X (off)     X (off)          X (off)               │
  └────────────────────────── ┼ ──────────┼────────────────┼────────────────────┘
                              │           │                │
  ┌ BOTTOM AON STRIP ─────────▼───────────▼────────────────▼──────────────────── ┐
  │  EDC mux (egress)          ISO cell (S flit out)  Clock feed-through (OUT)   │
  │  [mux]sel=1←bypass wire    flit_out_req[S]='0     col_clk_out ──► to Y-1     │
  │                            (clamped, safe)        (AON BUF drives wire down) │
  │  SRAM retention_enable tie                                                   │
  └─────────────────────────────────────────────────────────────────────────────-┘
                          │              │
  ════════════════════════╪══════════════╪═══════════════════════════════════════
                          │              │
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  LIVE TILE BELOW (Y-1)                                                      │
  │  receives: flit_in_req[N] = '0 (safe, no spurious flit)                     │
  │  receives: col_clk  ← from harvested tile's BOTTOM AON strip buffer         │
  └─────────────────────────────────────────────────────────────────────────────┘
```

#### Signal-by-signal analysis

##### (A) Flit wires — NO TOP→BOTTOM pass-through, independent ISO at each edge

```
  NORTH flit (from Y+1 → into Y → exits toward Y-1):
  ─────────────────────────────────────────────────
  Y+1 drives: flit_out_req[x][y+1][NEGATIVE][Y_AXIS]
                    │ wire (always connected, in Y+1's power domain)
  TOP AON:    flit_in_req[x][y][POSITIVE][Y_AXIS]  ←── enters ISO cell
              ISO cell output: flit_out_req[x][y][NEGATIVE][Y_AXIS] = '0

  Y-1 receives: flit_in_req[x][y-1][POSITIVE][Y_AXIS] = '0
                ← driven by BOTTOM AON ISO cell independently
                ← NOT a passthrough from TOP; each edge has its own ISO
```

**Key point:** Flits are NOT forwarded through the powered-off tile. The TOP AON ISO cell clamps the northward input (from Y+1) to a safe state and does NOT pass it to the bottom. The BOTTOM AON ISO cell independently clamps the southward output (toward Y-1) to `'0`. Both fire simultaneously when `ISO_EN=1`. The DOR routing algorithm ensures no flit should legally arrive at a harvested tile anyway — the ISO cells are a last-resort safety net.

##### (B) Column clock — REQUIRES dedicated AON spine wire from TOP to BOTTOM

This is the only signal that **must** travel from TOP AON strip to BOTTOM AON strip through (or alongside) the powered-off tile:

```
  col_clk source (from abutment above, Y+1):
      │
  TOP AON strip:  col_clk_in → [AON_BUF_1] → aon_spine_clk_wire
                                                   │
                                            AON SPINE WIRE
                                            (runs vertically
                                             ALONGSIDE the tile,
                                             NOT through the
                                             switchable domain)
                                                   │
  BOTTOM AON strip:  aon_spine_clk_wire → [AON_BUF_2] → col_clk_out
      │
  Tile below (Y-1) receives col_clk normally
```

**The AON spine wire** is a dedicated metal route — typically a vertical wire on a dedicated channel at the left or right edge of the tile — that physically bypasses the switchable domain. It must:
- Reside in the AON power domain metal routing
- Have enough drive strength (AON buffers at entry and exit) to cross the full tile height with acceptable RC delay
- Be in a routing channel that is NOT shared with switchable-domain signals (to avoid coupling issues when the switchable domain loses power abruptly)
- Feed the clock to ALL tiles below in the column, not just the immediate neighbor

```
  Column X, multiple harvested rows:
  ─────────────────────────────────────
  Y=4  NOC2AXI    ← col_clk source (always on)
       │
  Y=3  DISPATCH   ← col_clk_out = col_clk (passes through normally, always on)
       │
  Y=2  TENSIX     ← HARVESTED: col_clk enters TOP AON → [AON_BUF] → spine wire
       │           │                                                    │
       │           │  switchable core = OFF                             │ (AON spine)
       │           │                                                    │
       │           └── BOTTOM AON → [AON_BUF] → col_clk to Y=1 ────────┘
       │
  Y=1  TENSIX     ← col_clk received from Y=2 BOTTOM AON strip ✓ (still works)
       │
  Y=0  TENSIX     ← col_clk received from Y=1 normally ✓
```

##### (C) EDC ring bypass — STAYS within TOP AON strip (no TOP→BOTTOM needed)

```
  EDC bypass wire geometry (per tile):
  ──────────────────────────────────────────────────────────
  The NOC router (demux source) is at the TOP of the tile.
  The Overlay wrapper (mux destination) is also at the TOP.
  ∴ bypass wire runs HORIZONTALLY within the TOP AON strip.
  It does NOT cross to the BOTTOM AON strip at all.

  TOP AON strip:
  ┌─────────────────────────────────────────────────────┐
  │  [NOC router demux] out1 ─────► [Overlay mux] in1  │
  │   (edc_egress_t6_byp_intf — short horizontal wire)  │
  └─────────────────────────────────────────────────────┘
```

This is why the EDC bypass does not create a TOP→BOTTOM routing problem — both endpoints are co-located at the tile's top edge.

##### (D) de_to_t6 / t6_to_de wires — terminated at boundary, not passed through

```
  de_to_t6[x] (4-bit, Dispatch at Y=3 → Tensix at Y=2/1/0):
    Driven by Dispatch Engine (always-on, Y=3)
    Received by Tensix tile → enters TOP AON strip
    When tile is harvested: wire is driven by live Dispatch = safe
    No passthrough needed — it terminates at this tile

  t6_to_de[x] (4-bit, Tensix → Dispatch):
    Driven by Tensix (switchable domain) → ISO cell in TOP AON strip
    ISO drives t6_to_de[x] = '0 when core is off
    No passthrough needed — it originates at this tile
```

#### Complete connectivity diagram — harvested tile Y=2 in a live column

```
                     Y=3 DISPATCH (always on)
                       │           │
            de_to_t6[x]│  col_clk  │   flit_out_req[S]  EDC Seg.A
                       │           │           │              │
               ════════╪═══════════╪═══════════╪══════════════╪══════
               ┌──────────────────────────────────────────────────────┐
               │  Y=2 TENSIX TOP AON STRIP                            │
               │  [ISO t6_to_de='0]                                   │
               │  [ISO N_flit_out='0]  [ISO E_flit_out='0]            │
               │  [ISO W_flit_out='0]                                  │
               │  [col_clk_in→AON_BUF→spine_wire]  [EDC demux sel=1]  │
               │  [EDC bypass wire ──────────────── EDC mux sel=1]    │
               └──────────────────────────────────────────────────────┘
               │  SWITCHABLE CORE (VDD_TENSIX_2 = OFF)                 │
               │  (all logic off, no outputs, SRAMs in retention)      │
               └──────────────────────────────────────────────────────┘
               ┌──────────────────────────────────────────────────────┐
               │  Y=2 TENSIX BOTTOM AON STRIP                         │
               │  [ISO S_flit_out='0]                                  │
               │  [spine_wire→AON_BUF→col_clk_out]                    │
               │  [SRAM retention_enable tied high]                   │
               └──────────────────────────────────────────────────────┘
               ════════╪═══════════╪═══════════╪══════════════╪══════
                       │           │           │              │
            (t6_to_de  │  col_clk  │  flit_in  │              │ EDC Seg.A
             ='0,safe) │  (valid!) │  req='0   │ (continues)  │ (continues
                       │           │  (safe)   │              │  via bypass)
                     Y=1 TENSIX (alive, receives all signals correctly)
```

#### P&R implementation rules for AON spine wire

| Rule | Detail |
|---|---|
| **Dedicated routing channel** | Reserve left or right edge of each Tensix tile for the AON spine wire — do not block with switchable-domain standard cells |
| **AON buffer sizing** | `AON_BUF_1` (TOP strip, drive into spine) and `AON_BUF_2` (BOTTOM strip, restore drive strength) must be sized for tile height RC load; use PDK AON-rated buffer cell |
| **Power domain assignment** | Both AON buffers and the spine wire metal must be assigned to `VDD_AON` power domain in the CPF/UPF |
| **Wire width** | Spine wire should be minimum 2× minimum width to reduce RC; clock signal has strict slew requirements |
| **Shielding** | If switchable domain has capacitive coupling risk during power-on/off transients, add ground shielding on both sides of spine wire |
| **Multiple harvested rows** | If Y=1 is also harvested, Y=1's AON spine receives clock from Y=2's BOTTOM AON output — spine buffers chain; no special treatment needed as long as each tile has its own `AON_BUF_1`/`AON_BUF_2` |
| **SDC** | The spine wire is in the AON clock tree — include in clock definition: `create_clock -name col_clk_aon -source [get_pins AON_BUF_1/Z]` with the same period as AICLK |

---

## 9A. ISO Cell Insertion Guide — Complete Signal List

This section is a complete, implementation-ready reference for ISO cell insertion at the Tensix tile power domain boundary. Every signal that crosses FROM the switchable domain (`VDD_TENSIX_xy`) TO an always-on receiver must have an ISO cell.

### Rule: When to insert ISO

```
ISO cell required if ALL THREE conditions are true:
  (1) Signal is driven FROM the switchable (VDD_TENSIX_xy) domain
  (2) Signal is received by a live domain (VDD_AON, neighbor tile, always-on row)
  (3) The receiver will malfunction if it sees a floating/unknown value
```

Signals driven FROM a live domain INTO the switchable domain do NOT need ISO — the driver stays powered; the receiver (the harvested tile's input port) is simply not used.

---

### ISO Cell Type

Standard ISO cell for power gating:

```
  ISO cell (AND-type, active-high ISO_EN):
  ─────────────────────────────────────────
  i_data   ──►─┐
               AND ──► o_iso_data
  ISO_EN   ──►─┘
                                  ISO_EN=0 (core ON):  o_iso_data = i_data (pass)
                                  ISO_EN=1 (core OFF): o_iso_data = 0      (clamp)

  OR-type (for active-low signals, e.g. reset_n outputs if any):
  ISO_EN_N ──►─┐
               OR ──► o_iso_data   (ISO_EN_N=0 when harvested: output forced to 1)
  i_data   ──►─┘
```

Use **AND-type** for all flit and data signals (safe value = `0`).
`ISO_EN` must be sourced from the **always-on domain** and must be asserted before the power rail is cut.

---

### Complete ISO Signal List

#### Group 1: NoC Flit Outputs (8 signals, all AND-ISO, safe value = `'0`)

These are the most critical — a floating flit valid bit will inject a spurious packet into a live tile's input port.

| # | Signal | Width | Direction | Receiver | ISO location |
|---|---|---|---|---|---|
| 1 | `flit_out_req[x][y][POSITIVE][Y_AXIS]` | noc_req_t | North output | `flit_in_req[x][y+1][NEGATIVE][Y_AXIS]` in live Y+1 tile | TOP AON strip |
| 2 | `flit_out_req[x][y][NEGATIVE][Y_AXIS]` | noc_req_t | South output | `flit_in_req[x][y-1][POSITIVE][Y_AXIS]` in live Y-1 tile | BOTTOM AON strip |
| 3 | `flit_out_req[x][y][POSITIVE][X_AXIS]` | noc_req_t | East output | `flit_in_req[x+1][y][NEGATIVE][X_AXIS]` in live X+1 tile | TOP or SIDE strip |
| 4 | `flit_out_req[x][y][NEGATIVE][X_AXIS]` | noc_req_t | West output | `flit_in_req[x-1][y][POSITIVE][X_AXIS]` in live X-1 tile | TOP or SIDE strip |

> `noc_req_t` contains a `valid` bit. Clamping the whole struct to `'0` ensures `valid=0` — no spurious flit injection.

#### Group 2: NoC Flit Response (Credits) Outputs (4 signals, AND-ISO, safe value = `'0`)

Credit return signals flow in the opposite direction from flit data. If the harvested tile never returns credits, live neighbors' VC credit counters would eventually drain to zero and deadlock. Clamping to `'0` means "no credits returned" — acceptable because DOR routing will never send flits toward a harvested tile (zero credits → zero injection).

| # | Signal | Width | Direction | Receiver | ISO location |
|---|---|---|---|---|---|
| 5 | `flit_in_resp[x][y][POSITIVE][Y_AXIS]` | noc_resp_t | North credit return | live Y+1 tile's credit counter input | TOP AON strip |
| 6 | `flit_in_resp[x][y][NEGATIVE][Y_AXIS]` | noc_resp_t | South credit return | live Y-1 tile's credit counter input | BOTTOM AON strip |
| 7 | `flit_in_resp[x][y][POSITIVE][X_AXIS]` | noc_resp_t | East credit return | live X+1 tile | TOP or SIDE strip |
| 8 | `flit_in_resp[x][y][NEGATIVE][X_AXIS]` | noc_resp_t | West credit return | live X-1 tile | TOP or SIDE strip |

#### Group 3: de_to_t6 / t6_to_de Control Wires (1 signal, AND-ISO, safe value = `'0`)

`de_to_t6[x]` is driven FROM Dispatch Engine (always-on) INTO the Tensix tile — no ISO needed (driver is always-on).
`t6_to_de[x]` is driven FROM the Tensix tile (switchable) TO the Dispatch Engine (always-on) — ISO required.

| # | Signal | Width | Direction | Receiver | ISO location |
|---|---|---|---|---|---|
| 9 | `t6_to_de[x]` | 4-bit | Tensix → Dispatch (Y=3, always-on) | FDS handshake input in Dispatch Engine | TOP AON strip |

Safe value `'0`: Dispatch Engine interprets `t6_to_de=0` as "Tensix not ready" — no false handshake triggers.

#### Group 4: L1 ACK / Response to NoC (if applicable)

If the L1 superarbiter drives a response/ACK signal back to the NoC NIU through an async FIFO boundary:

| # | Signal | Width | Direction | Receiver | ISO location |
|---|---|---|---|---|---|
| 10 | L1 NoC write ACK (async FIFO `o_full` / `wr_ready` feedback) | 1–2 bit | L1 (AICLK) → NoC NIU (NOCCLK) | `tt_async_fifo_wrapper` write-side in NIU | BOTTOM AON strip (near L1) |

> If the async FIFO itself straddles the power boundary, the entire FIFO (or at least its read-side) must be in the AON domain. In practice: place the async FIFO in the AON strip or replicate only the gray-code pointer in AON.

#### Group 5: Interrupt / Error Outputs to Always-On Logic (if any)

If the Tensix tile drives any interrupt or error signals to an always-on interrupt controller (e.g., via the SMN or a global error aggregator):

| # | Signal | Width | Receiver | ISO location | Safe value |
|---|---|---|---|---|---|
| 11 | Any `o_irq_*` or `o_err_*` output from Tensix to global controller | 1-bit each | always-on interrupt aggregator | TOP or BOTTOM AON strip | `'0` (no spurious interrupt) |

#### Group 6: Signals NOT requiring ISO (inputs to harvested tile from live domain)

These are driven by always-on or neighboring powered tiles — the driver is not affected by the harvested tile's power state:

| Signal | Source | Why no ISO needed |
|---|---|---|
| `flit_in_req[x][y][*]` ×4 | Live neighboring tiles | Driven by live domain; just not consumed by harvested tile |
| `de_to_t6[x]` | Dispatch Engine (always-on Y=3) | Driver is in always-on domain |
| `i_ai_clk`, `i_noc_clk` | Clock spine (AON) | Clock is an input, not an output |
| `i_tensix_reset_n` | trinity.sv top (always-on) | Reset is an input |
| `i_harvest_en` | always-on fuse register | Input to tile |
| EDC ring input (`edc_egress_intf`) | Previous tile in ring (live) | Handled by EDC demux bypass, not an ISO concern |

---

### ISO Cell Placement in UPF/CPF

```tcl
# UPF example — create isolation rules for VDD_TENSIX_xy domain
create_power_domain PD_TENSIX_XY \
    -elements {tt_tensix_with_l1}

# Isolation rule: all outputs from PD_TENSIX_XY to PD_AON or PD_ALWAYS_ON
create_isolation_rule ISO_TENSIX_OUTPUTS \
    -domain PD_TENSIX_XY \
    -isolation_power_net  VDD_AON \
    -isolation_ground_net VSS \
    -clamp_value 0 \
    -applies_to outputs \
    -isolation_signal ISO_EN \
    -isolation_sense high

# Isolation cell placement: at the boundary of PD_TENSIX_XY
# toward TOP AON strip (north/east/west outputs) and BOTTOM AON strip (south output)
set_isolation_control ISO_TENSIX_OUTPUTS \
    -domain PD_TENSIX_XY \
    -isolation_signal ISO_EN \
    -location parent        ;# ISO cells placed in parent (AON) domain, not inside PD

# Retention rule for L1 SRAMs
create_retention_rule RET_TENSIX_L1 \
    -domain PD_TENSIX_XY \
    -retention_power_net VDD_AON \
    -save_signal {ISO_EN posedge} \
    -restore_signal {ISO_EN negedge}
```

---

### ISO Insertion Summary Table

| # | Signal group | Count | AND/OR | Safe value | Strip location | UPF applies_to |
|---|---|---|---|---|---|---|
| 1–4 | `flit_out_req` ×4 dirs | 4 × width(noc_req_t) | AND | `'0` | N→TOP, S→BOTTOM, E/W→SIDE | outputs |
| 5–8 | `flit_in_resp` ×4 dirs | 4 × width(noc_resp_t) | AND | `'0` | N→TOP, S→BOTTOM, E/W→SIDE | outputs |
| 9 | `t6_to_de[x]` | 4 bits | AND | `4'b0` | TOP | outputs |
| 10 | L1 async FIFO feedback | 1–2 bits | AND | `'0` | BOTTOM (near L1) | outputs |
| 11 | Any interrupt/error outputs | N bits | AND | `'0` | whichever strip drives toward receiver | outputs |
| — | All inputs | — | None needed | — | — | — |

**Total ISO cells minimum: 13 groups × (signal width) bits.** Exact bit count depends on `noc_req_t` / `noc_resp_t` struct widths in `tt_noc_pkg.sv`.

---

## 10. Key P&R Checklist (Updated)

| Item | Detail | Source |
|---|---|---|
| Partition boundaries | 15 partitions; each gets own SDC | `synth/run_syn.tcl` |
| SRAM macro insertion | Swap `tt_mem_wrap_*` behavioral models with PDK macros | `tt_mem_ctrl_pkg.sv` |
| L1 memory type | `RA1_UHD` (area-optimized) for L1 banks; `RA1_HS` for I-cache | `mem_cfg_l1_t`, `mem_cfg_tensix_t` |
| ICG cell mapping | `tt_libcell_clkgate` → PDK ICG; 26 instances across design | `tt_libcell_clkgate.sv` |
| Latch placement | DEST + SRCB reg files: latch + ICG, NOT SRAM macro | `tt_reg_bank.sv` |
| SRCB physical center | `srcb_regs` must be center of FPU block, equidistant both G-Tiles | `tt_fpu_v2.sv` L1259-1260 |
| CDC async FIFOs | AICLK↔NOCCLK, dm_clk↔NOCCLK — `tt_async_fifo_wrapper` | SDC files |
| Reset sync MCPs | setup=4, hold=3 for all reset sync cells | `tt_t6_l1_partition.final.sdc` |
| JTAG/BISR MCPs | setup=3/hold=2 (JTAG), setup=3/hold=2 (BISR) | `tt_t6_l1_partition.final.sdc` |
| SMN/Harvest MCPs | setup=2, hold=1 | `tt_t6_l1_partition.final.sdc` |
| de_to_t6 wires | Point-to-point direct wires, NOT NoC — route as data | `tt_chip_global_pkg.sv` |
| **Harvest: flit ISO cells** | **All 8 flit_out_req + 8 flit_in_resp directions need ISO='0 at power boundary** | **trinity.sv:248-278** |
| **Harvest: ISO_EN in AON** | **ISO_EN register + all ISO control wires must be in always-on domain** | **Harvest_HDD §8** |
| **Harvest: clock feed-through AON** | **Column clock abutment buffers inside each Tensix tile must be AON** | **trinity.sv:237-246** |
| **Harvest: EDC bypass AON** | **EDC mux/demux bypass cells must be in AON domain; ring must stay functional** | **Harvest_HDD §8** |
| **Harvest: power-off sequence** | **mesh_end_y reconfig → drain flits → ISO_EN → power cut (strict order)** | **§9.8 above** |
| **Harvest: no X-direction** | **All 4 columns always active; only Y-row harvest is supported** | **trinity_noc2axi_*.sv** |
| **Harvest: t6_to_de ISO** | **4-bit t6_to_de from harvested tile to Dispatch (always-on) needs ISO='0** | **§9.3 above** |
| Clock domains | 3 domains: AICLK (compute), NOCCLK (NoC), dm_clk (dispatch) | RTL top-level ports |
| Path groups (FPU) | `dest_cgen`, `mtile_tag`, `srcb_rows`, `mtile_pipe0-4` | `tt_fpu_gtile.final.sdc` |
| Path groups (CPU) | `o_srca_wr_tran`, `o_srcb_rd_tran0/1`, `o_l1_sbank_*` | `tt_instrn_engine_wrapper.final.sdc` |
| Tool compatibility | Both Cadence (Genus/Innovus) and Synopsys (DC/PT) supported | SDC template procs |

---

## 11. File Reference

| File | Contents |
|---|---|
| `synth/run_syn.tcl` | Partition list, synthesis flow driver |
| `synth/<partition>/<partition>.final.sdc` | Per-partition timing constraints, path groups, MCPs |
| `tt_rtl/tensix-tt_tech/rtl/behavioral/tt_libcell_clkgate.sv` | ICG behavioral model |
| `tt_rtl/tensix-tt_tech/rtl/behavioral/tt_libcell_sync3r.sv` | Reset synchronizer |
| `tt_rtl/tt_chip/memories/wrappers/tt_mem_ctrl_pkg.sv` | SRAM type selection and tsel settings |
| `tt_rtl/tt_chip/memories/wrappers/tt_mem_wrap_functions.svh` | ECC width calculation helpers |
| `tt_rtl/tt_tensix_neo/src/hardware/registers/rtl/tt_reg_bank.sv` | DEST latch array (ICG + always_latch) |
| `tt_rtl/tt_tensix_neo/src/hardware/tensix/fpu/rtl/tt_fpu_v2.sv` | FPU top: srcb_regs instantiation + broadcast |
| `tt_rtl/tt_t6_l1/rtl/tt_t6_l1.sv` | L1 SRAM bank array + arbitrator |
| `tt_rtl/tt_chip/memories/wrappers/tt_instrn_engine_mem_wrappers.sv` | TRISC cache + LDM wrapper instances |

---

*End of Document — Version 0.5 (2026-03-18)*
*v0.5: Completely rewrote §2.2 (Tensix Tile Internal Floorplan) — previous version was incorrect. Added §2.2.1 problem statement (NoC→L1 write bus = 512-bit, CDC inside NOC module, spans full tile height in naive stack), §2.2.2 corrected floorplan with dedicated left-edge routing channel, §2.2.3 write channel signal specification (noc_pre_sbank_wr_intf[3:0], 4×128-bit, RTL-verified), §2.2.4 channel sizing (~82µm, P&R blockage directives), §2.2.5 L1 superarb left-port alignment, §2.2.6 corrected placement rationale table.*
*v0.2: Added Section 9 (Harvest P&R — Flit Isolation and Power Domain Strategy)*
*v0.3: Expanded Section 8 (EDC Ring Physical Routing) — 7 subsections added: ring topology diagram, clock requirements per node type (AICLK/NOCCLK/none), MCPDLY=7 derivation (3-stage sync + freq ratio + margin), CDC toggle protocol mechanics (req/ack crossing NOCCLK↔AICLK) + SDC templates, repeater placement guide (connector vs registered, inter-tile wire budget, loopback depth), harvest bypass wire routing rules (AON domain, timing), physical placement summary*

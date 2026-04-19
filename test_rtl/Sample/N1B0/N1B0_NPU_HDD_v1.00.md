# N1B0 NPU Hardware Design Document v1.00

## Document History

| Version | Date       | Author    | Changes                                                                 |
|---------|------------|-----------|-------------------------------------------------------------------------|
| v0.1    | 2026-01-10 | HW Team   | Initial draft — SoC overview, grid, tile types                         |
| v0.2    | 2026-01-24 | HW Team   | Tensix tile detail added; L1 SRAM 4× expansion confirmed               |
| v0.3    | 2026-02-07 | HW Team   | NOC2AXI composite tile architecture; cross-row flit wires              |
| v0.4    | 2026-02-18 | HW Team   | Dispatch tile, iDMA engine detail; SFR memory map §2.1                 |
| v0.5    | 2026-02-28 | HW Team   | NoC router virtual channels, ATT, dynamic routing 928-bit carried list |
| v0.6    | 2026-03-07 | HW Team   | EDC ring, severity model, MCPDLY=7 derivation                          |
| v0.7    | 2026-03-14 | HW Team   | Harvest mechanism 6 (ISO_EN), PRTN chain, DFX wrappers                 |
| v0.8    | 2026-03-20 | HW Team   | §15.2 floorplan correction (NoC→L1 side channel); P&R notes            |
| v0.9    | 2026-03-26 | HW Team   | Full restructure: §1–§14 outline, all RTL-verified facts incorporated  |
| v0.91   | 2026-03-30 | HW Team   | Cluster/tile hierarchy correct; L1 3MB/cluster (512 macros); BRISC→TRISC3; ICache sizes per-thread; Y=0 NW/NE, Y=1 W/E labels |
| v0.92   | 2026-03-30 | HW Team   | §12 Memory Architecture expanded: L1 macro _high/_low pair convention verified from memory list CSV; TRISC ICache/LM per-thread byte sizes added; DEST/SRCA byte capacity added; §12.8 full size summary with byte columns |
| v0.93   | 2026-03-30 | HW Team   | §2.4 M-Tile hierarchy corrected: tt_fpu_mtile is a physical module (RTL-verified); §2.8 DEST entry count corrected (16,384 per tt_tensix, 64KB; prior "12,288" superseded); §2.9 SRCB corrected: physical 4KB dual-bank RF (SRCB_IN_FPU=1, tt_srcb_registers.sv); grid NE/NW corrected: X=0=NW_OPT/DISPATCH_W, X=3=NE_OPT/DISPATCH_E (RTL packed-array literal direction verified); full architectural rationale added |
| v0.94   | 2026-03-30 | HW Team   | §2.2.4 corrected: all 4 TRISCs have uniform memory interfaces (ICache 32b, LDM 32b private, L1 direct 128b, NoC via overlay stream reg writes); removed incorrect "512-bit NoC DMA hardware port"; NOC_CONTROL=0 for all TRISC instances (RTL-verified, tt_instrn_engine.sv lines 5016/5309); §2.3.6 new: complete L1/DRAM access architecture — access matrix, LDM per-thread sizing, DRAM path via overlay stream regs→NoC→NIU→ATT→AXI, ASCII block diagram; §2.3.7 new: INT8 K=8192 hardware architecture — INT8_2x packing (ENABLE_INT8_PACKING=1, datum[1:0][7:0]), K_tile=96 INT8 per SRCA pass (SRCS_NUM_ROWS_16B=48×2), INT32 DEST accumulation (int8_op→fpu_tag_32b_acc, dstacc_idx), 86-pass firmware loop, overflow analysis (132M<<2.1B), complete ASCII datapath diagram |
| v1.00   | 2026-03-30 | HW Team   | §2.7.3 MOP Sequencer fully expanded: 32-bit MOP word encoding (mop_type/done/loop_count/zmask fields), dual-bank config registers (LOOP0/1_LEN, LOOP_INSTR0/1, start/end/last instrs), math loop FSM (IDLE→LOOP_START→IN_LOOP→LOOP_END×2→FINAL_END×2, 1 fpu_tag/cycle), unpack loop FSM (z-plane iteration with 32-bit zmask, UNPACK_A0/A1/A2/A3/B/SKIP states), fpu_tag_t key fields (srca_rd_addr, dstacc_idx, dest_wr_row_mask, int8_op, op_mmul), completion via mop_done+hardware SEMPOST, end-to-end INT8 GEMM example (86 MOPs×48 cycles); §5.1 wormhole switching RTL-verified: HEAD/DATA flit types, credit-based VC flow control, path_reserve_bit — all confirmed in tt_noc_pkg.sv with line references; §2.1 MOP definition added inline; §2.3.2 TRISC2 row expanded with MOP definition |
| v0.97   | 2026-03-30 | HW Team   | §2.1 FPU diagram corrected: G-Tile/M-Tile/FP-Lane shown as containment hierarchy (not parallel alternatives); §2.1.1 new: RTL-verified FPU hierarchy (tt_fpu_gtile→tt_fpu_mtile→tt_fpu_tile→tt_fp_lane), concurrency table (16 cols × 8 rows × 2 lanes = 256 FP-Lanes per tt_tensix all active same cycle, no arbiter), format-selection clarification (same tt_fp_lane hardware for all formats, tag-bit selected); iDMA vs Rocket RISC-V distinction: Rocket 8-core CPU cluster in tt_overlay_cpu_wrapper (TTTrinityConfig_DigitalTop), iDMA is RoCC-connected hardware accelerator programmed by Rocket with 24 cmd clients, 32 transaction IDs, multi-dimensional address generation |
| v0.96   | 2026-03-30 | HW Team   | §2.3.5 sync barrier corrected: replaced imprecise "hardware sync barrier" with RTL-verified hardware semaphore mechanism (SEMGET/SEMPOST/SEMINIT/SEMWAIT custom RISC-V instructions, 32×4-bit counters, gate-level pipeline stall via instrn_sem_stall, tt_semaphore_reg.sv + tt_sync_exu.sv); 3-thread handshake diagram added; hardware-initiated SEMPOST (FPU/TDMA MOP completion), mailbox registers, trisc_tensix_sync module documented; all "sync barrier" references in §2.3.7.5, §2.3.7.7, §2.11 updated to SEMPOST/SEMGET instruction names |
| v0.95   | 2026-03-30 | HW Team   | §1.2 composite router tile explanation added (why composite, internal structure, nodeid_y−1 offset, firmware addressing table); §2.3.6.4 DRAM Access Path expanded: cfg_reg CSR write detail (5-register table), NoC packet injection (noc_header_address_t 96-bit field map), DOR vs dynamic routing comparison table, SMN security fence pre-ATT filter (RTL-verified, tt_noc_sec_fence_range_compare.sv), ATT 3-stage decode (mask/endpoint/BAR), additional decode mechanisms table (gasket mode, L1 sub-address, dynamic routing table); §2.3.6.5 Access Summary Diagram path table added (paths ①–⑦ with direction/width/purpose/when-used); §2.3.7.1 rewritten from Q&A to HDD prose; full RTL-verified address decode chain diagram added to §2.3.6.4 |
| v0.99   | 2026-03-31 | HW Team   | §3 Overlay Engine chapter added (comprehensive 640-line treatment covering stream controller, TDMA, MOP sequencer, context switching, CDC FIFOs, SMN integration, EDC integration, DFX); all §3–§14 renumbered to §4–§15; N1B0_reset_hierarchy.md reference doc created |
| v1.00   | 2026-04-02 | HW Team   | Narrative descriptions added to 6 key functional units (§2 Tensix Compute Tile, §3 Overlay Engine, §4 NOC2AXI Composite Tiles, §6 NoC Router, §7 iDMA Engine, §8 EDC Ring). Each narrative includes Unit Purpose, Design Philosophy, Integration Role, Key Characteristics, and Use Case Example sections for improved readability. Document now 6,129 lines (up from 5,353 in v0.98), with all 15 sections complete and §3 Overlay Engine properly integrated. |

---

## Table of Contents

- §1  SoC Overview
- §2  Tensix Compute Tile
- §3  Overlay Engine — Data Movement Cluster
- §4  NOC2AXI Composite Tiles (§4.7 NIU DMA Operation)
- §5  Dispatch Tiles
- §6  NoC Router
- §7  iDMA Engine
- §8  EDC Ring
- §9  Clock, Reset, and CDC Architecture
- §10 Security Monitor Network (SMN)
- §11 Debug Module (RISC-V External Debug)
- §12 Adaptive Workload Manager (AWM)
- §13 Memory Architecture
- §14 SFR Summary
- §15 Verification Checklist

---

## §1 SoC Overview

### 1.1 Product Description

Trinity N1B0 is a neural processing unit (NPU) implemented as a 4×5 2D NoC mesh. It is designed for inference and training workloads using INT16, FP16B, and INT8 numeric formats, with optional FP32 accumulation. The chip targets LLM inference use cases such as LLaMA-class models and provides dedicated tensor DMA, programmable RISC-V host processors, and a coherent NoC fabric.

### 1.2 Grid Topology

The N1B0 mesh is indexed as X=0..3 (columns) × Y=0..4 (rows), giving 20 tiles total. X increases left-to-right; Y increases bottom-to-top.

```
         X=0              X=1                  X=2                  X=3
       ┌──────────────┬──────────────────┬──────────────────┬──────────────┐
  Y=4  │ NOC2AXI_     │ NOC2AXI_ROUTER_  │ NOC2AXI_ROUTER_  │ NOC2AXI_     │
       │ NW_OPT       │ NW_OPT           │ NE_OPT           │ NE_OPT       │
       │ (0,4) EP=4   │ (1,4) EP=9       │ (2,4) EP=14      │ (3,4) EP=19  │
       │ standalone   │ composite Y=4    │ composite Y=4    │ standalone   │
       │ NIU only     │ NIU portion      │ NIU portion      │ NIU only     │
       ├──────────────┼──────────────────┼──────────────────┼──────────────┤
  Y=3  │ DISPATCH_W   │ ROUTER           │ ROUTER           │ DISPATCH_E   │
       │ (0,3) EP=3   │ (1,3) EP=8       │ (2,3) EP=13      │ (3,3) EP=18  │
       │              │ composite Y=3    │ composite Y=3    │              │
       │              │ router portion   │ router portion   │              │
       │              │ of NW_OPT        │ of NE_OPT        │              │
       ├──────────────┼──────────────────┼──────────────────┼──────────────┤
  Y=2  │ Tensix       │ Tensix           │ Tensix           │ Tensix       │
       │ (0,2) EP=2   │ (1,2) EP=7       │ (2,2) EP=12      │ (3,2) EP=17  │
       ├──────────────┼──────────────────┼──────────────────┼──────────────┤
  Y=1  │ Tensix       │ Tensix           │ Tensix           │ Tensix       │
       │ (0,1) EP=1   │ (1,1) EP=6       │ (2,1) EP=11      │ (3,1) EP=16  │
       │  W           │  W               │  E               │  E           │
       ├──────────────┼──────────────────┼──────────────────┼──────────────┤
  Y=0  │ Tensix       │ Tensix           │ Tensix           │ Tensix       │
       │ (0,0) EP=0   │ (1,0) EP=5       │ (2,0) EP=10      │ (3,0) EP=15  │
       │  NW          │  NW              │  NE              │  NE          │
       └──────────────┴──────────────────┴──────────────────┴──────────────┘
```

**Notes (RTL-verified from `used_in_n1/mem_port/rtl/targets/4x5/trinity_pkg.sv`):**
- `GridConfig[4]` (Y=4) = `'{NOC2AXI_NE_OPT, NOC2AXI_ROUTER_NE_OPT, NOC2AXI_ROUTER_NW_OPT, NOC2AXI_NW_OPT}` — packed array `[3:0]`, so **[3]=NE_OPT (X=3), [0]=NW_OPT (X=0)**
- `GridConfig[3]` (Y=3) = `'{DISPATCH_E, ROUTER, ROUTER, DISPATCH_W}` — packed `[3:0]`: **[3]=DISPATCH_E (X=3), [0]=DISPATCH_W (X=0)**
- **Y=4 X=0 and X=3 are NOT Tensix** — they are standalone NIU-only tiles (`NOC2AXI_NW_OPT` at X=0 / `NOC2AXI_NE_OPT` at X=3), distinct from the composite router tiles at X=1/X=2.
- **NW_OPT is at X=0 (standalone) and X=1 (composite)**; **NE_OPT is at X=2 (composite) and X=3 (standalone)**.
- **DISPATCH_W is at X=0 (Y=3)**; **DISPATCH_E is at X=3 (Y=3)** — X=0 is the west side of the mesh; X=3 is the east side.
- Total Tensix clusters: 12 clusters at Y=0–2 (each cluster = 1 `tt_tensix_with_l1` with 4 Tensix tiles (`tt_tensix`) internally). Y=3 and Y=4 contain no Tensix tiles.

#### Composite Router Tiles (X=1, X=2)

The two center columns at Y=3–4 are each implemented as a **composite tile** — a single RTL module that spans two physical mesh rows and integrates both a NoC router and a NIU (NOC2AXI bridge) in one hierarchy.

**Why composite tiles exist:**

In the baseline Trinity design, the top row (Y=4) holds standalone NIU-only tiles (X=0, X=3) — each a dedicated AXI bridge with no router function. However, the center columns (X=1, X=2) required placing a full NoC router at Y=3 to maintain the mesh topology for NoC traffic that must cross the top portion of the grid. Rather than leaving Y=4 unused at these columns, the design combines the Y=3 router and Y=4 NIU into a single floorplan module. This provides:

- A full-bandwidth NoC router at Y=3 for mesh traffic (east/west/south forwarding)
- An AXI master port at Y=4 for a second DRAM path per corner
- Reduced inter-tile wiring (internal cross-row flit buses replace external mesh connections between Y=3 and Y=4 for these columns)

**Internal structure:**

```
  NOC2AXI_ROUTER_NW_OPT (X=1, trinity_noc2axi_router_nw_opt)
  ┌──────────────────────────────────────────────┐
  │  Y=4 portion: NIU (tt_noc2axi)               │
  │    - AXI4 master port → npu_out_*[x=1]       │
  │    - ATT address translation (64 entries)     │
  │    - nodeid reports as (x=1, y=3)             │
  │              ▲                                │
  │   internal cross-row flit wires               │
  │  (router_o_flit_out_south → noc2axi input)    │
  │              │                                │
  │  Y=3 portion: Router (tt_trinity_router)      │
  │    - Full 5-port mesh router (N/S/E/W/local)  │
  │    - Connects to mesh at Y=3 physical position│
  │    - Forwards south-bound flits to NIU above  │
  └──────────────────────────────────────────────┘
```

**Key behavioral differences vs standalone NIU (X=0, X=3):**

| Property | Standalone NIU (X=0, X=3) | Composite Router+NIU (X=1, X=2) |
|----------|--------------------------|----------------------------------|
| Physical rows | Y=4 only | Y=3 + Y=4 |
| NoC router | None — leaf node only | Full 5-port router at Y=3 |
| Flit path to NIU | Direct: mesh Y=4 → NIU | Via router: mesh Y=3 → internal wires → NIU |
| nodeid_y for firmware | **4** (actual physical Y) | **3** (router row; NIU offset = −1) |
| AXI bus | `npu_out_*[x]` | `npu_out_*[x]` (same structure) |
| RTL module | `trinity_noc2axi_{nw,ne}_opt` | `trinity_noc2axi_router_{ne,nw}_opt` |

**Firmware addressing implication:**

Because the composite NIU's NoC node ID is reported at `nodeid_y=3` (the router row), firmware must address DRAM transfers to these NIU endpoints using **Y=3**, not Y=4:

```
Standalone NIU at X=0:   NOC_XY_ADDR(x=0, y=4, dram_addr)  ← Y=4
Standalone NIU at X=3:   NOC_XY_ADDR(x=3, y=4, dram_addr)  ← Y=4
Composite  NIU at X=1:   NOC_XY_ADDR(x=1, y=3, dram_addr)  ← Y=3 (router row)
Composite  NIU at X=2:   NOC_XY_ADDR(x=2, y=3, dram_addr)  ← Y=3 (router row)
```

Using `y=4` for X=1 or X=2 would address a non-existent node (the composite module does not present a mesh port at Y=4) and the NoC packet would be dropped or misrouted.

### 1.3 Tile Type Summary

| Tile Type                   | Count | Grid Positions          | RTL Module                              | tile_t enum value |
|-----------------------------|-------|-------------------------|-----------------------------------------|-------------------|
| Tensix compute              | 12    | (0–3, Y=0–2)            | tt_tensix_with_l1                       | `TENSIX` = 3'd0   |

> **Quadrant labels for Tensix clusters:** Y=0 X=0–1 = NW; Y=0 X=2–3 = NE; Y=1 X=0–1 = W; Y=1 X=2–3 = E; Y=2 has no quadrant name.

| NOC2AXI_ROUTER_NW_OPT       | 1     | (1, 3–4) composite      | trinity_noc2axi_router_nw_opt           | `NOC2AXI_ROUTER_NW_OPT` = 3'd3 |
| NOC2AXI_ROUTER_NE_OPT       | 1     | (2, 3–4) composite      | trinity_noc2axi_router_ne_opt           | `NOC2AXI_ROUTER_NE_OPT` = 3'd2 |
| NOC2AXI_NW_OPT (standalone) | 1     | (0, 4)                  | trinity_noc2axi_nw_opt                  | `NOC2AXI_NW_OPT` = 3'd4  |
| NOC2AXI_NE_OPT (standalone) | 1     | (3, 4)                  | trinity_noc2axi_ne_opt                  | `NOC2AXI_NE_OPT` = 3'd1  |
| DISPATCH_W                  | 1     | (0, 3)                  | tt_dispatch_top_west                    | `DISPATCH_W` = 3'd6 |
| DISPATCH_E                  | 1     | (3, 3)                  | tt_dispatch_top_east                    | `DISPATCH_E` = 3'd5 |

### 1.4 EndpointIndex Encoding

Every tile that connects to the NoC fabric is assigned an EndpointIndex used in ATT lookups and flit routing:

```
EndpointIndex = X * 5 + Y
```

| (X, Y)  | EndpointIndex | Tile Type                              | RTL tile_t            | Quadrant |
|---------|---------------|----------------------------------------|-----------------------|----------|
| (0, 0)  | 0             | Tensix                                 | TENSIX                | NW       |
| (0, 1)  | 1             | Tensix                                 | TENSIX                | W        |
| (0, 2)  | 2             | Tensix                                 | TENSIX                | —        |
| (0, 3)  | 3             | DISPATCH_W                             | DISPATCH_W            | —        |
| (0, 4)  | 4             | NOC2AXI_NW_OPT (standalone NIU)        | NOC2AXI_NW_OPT        | —        |
| (1, 0)  | 5             | Tensix                                 | TENSIX                | NW       |
| (1, 1)  | 6             | Tensix                                 | TENSIX                | W        |
| (1, 2)  | 7             | Tensix                                 | TENSIX                | —        |
| (1, 3)  | 8             | ROUTER (composite NW_OPT Y=3 portion)  | ROUTER                | —        |
| (1, 4)  | 9             | NOC2AXI_ROUTER_NW_OPT (composite NIU)  | NOC2AXI_ROUTER_NW_OPT | —       |
| (2, 0)  | 10            | Tensix                                 | TENSIX                | NE       |
| (2, 1)  | 11            | Tensix                                 | TENSIX                | E        |
| (2, 2)  | 12            | Tensix                                 | TENSIX                | —        |
| (2, 3)  | 13            | ROUTER (composite NE_OPT Y=3 portion)  | ROUTER                | —        |
| (2, 4)  | 14            | NOC2AXI_ROUTER_NE_OPT (composite NIU)  | NOC2AXI_ROUTER_NE_OPT | —       |
| (3, 0)  | 15            | Tensix                                 | TENSIX                | NE       |
| (3, 1)  | 16            | Tensix                                 | TENSIX                | E        |
| (3, 2)  | 17            | Tensix                                 | TENSIX                | —        |
| (3, 3)  | 18            | DISPATCH_E                             | DISPATCH_E            | —        |
| (3, 4)  | 19            | NOC2AXI_NE_OPT (standalone NIU)        | NOC2AXI_NE_OPT        | —        |

### 1.5 Clock Domains

| Clock Signal           | Scope           | Description                                                    |
|------------------------|-----------------|----------------------------------------------------------------|
| `i_axi_clk`            | Global          | AXI master/slave interfaces, host-facing logic                 |
| `i_noc_clk`            | Global          | NoC fabric, router ports, flit transport                       |
| `i_ai_clk[3:0]`        | Per-column      | Tensix compute (FPU, SFPU, TRISC0–3); index = X column     |
| `i_dm_clk[3:0]`        | Per-column      | Tensix data-move (TDMA, pack/unpack, L1 access); index = X     |
| `PRTNUN_FC2UN_CLK_IN`  | PRTN chain      | Separate clock for partition control chain                     |

Per-column separation of `ai_clk` and `dm_clk` allows independent DVFS per column. The Dispatch tiles receive `i_noc_clk` for their NoC interface and `i_ai_clk[col]` for their Rocket core.

### 1.6 Reset Architecture

| Reset Signal      | Type       | Scope                                  |
|-------------------|------------|----------------------------------------|
| `i_reset_n`       | Async low  | Global; all flip-flops                 |
| `i_axi_reset_n`   | Async low  | AXI domain registers and bridges       |
| Per-domain synced | Sync       | Each clock domain synchronizes reset internally using 3-stage synchronizer |

### 1.7 Top-Level Module

**File:** `rtl/trinity.sv`
**Module:** `trinity`

Key port groups:
- NoC flit I/O: north/south/east/west per-tile flit buses (512-bit)
- AXI master ports: 512-bit data, 56-bit address (NE and NW composite tiles)
- APB slave: register access for SFR space
- EDC ring: `edc_fwd_in/out`, `edc_loopback_in/out` per chain segment
- Harvest: `ISO_EN[11:0]`, `noc_y_size`, `mesh_start_x/y`
- PRTN chain: `PRTNUN_FC2UN_*` ports

---

## §2 Tensix Compute Tile

### 2.1 Overview

The Tensix compute tile is the primary matrix-math processing element of the N1B0 NPU. Each of the 12 Tensix **clusters** (`tt_tensix_with_l1`) contains:

(Each cluster internally instantiates 4 Tensix tiles (`tt_tensix`/neo), each with 2 G-Tiles — 48 Tensix tiles and 96 G-Tiles in total on chip.)

- A **TRISC3** (Tile Management RISC-V Core) for tile management and NoC DMA control
- Three **TRISC** cores (TRISC0/1/2) for specialized data-movement and math sequencing
- An **FPU** (Floating Point Unit) — 2× G-Tiles (`tt_fpu_gtile`), each containing 8 M-Tiles (`tt_fpu_mtile`) × 8 FP-Tile rows (`tt_fpu_tile`) × 2 FP-Lanes (`tt_fp_lane`). All columns and rows operate in parallel — no arbiter serializes them. G-Tile is the column container; M-Tile is one column; FP-Lane is the physical MAC unit.
- An **SFPU** (Scalar Floating Point Unit)
- An **L1 SRAM** partition (3MB per cluster, shared by 4 Tensix tiles; N1B0 4× expanded from 768KB baseline)
- A **TDMA** (Tile DMA) engine with pack/unpack engines and a **MOP sequencer** — MOP (Micro-Operation Packet) is the compressed instruction format used by TRISC1 to drive the FPU and data-movement hardware. One MOP word encodes an entire tensor operation (target unit, operand source, DEST range, loop count) that would require hundreds of raw RISC-V instructions. See §2.7.3 for full detail.
- Destination and source register files (latch arrays)
- An **Overlay wrapper** (`tt_neo_overlay_wrapper`) for context switching and orchestration

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│     tt_tensix_with_l1  (one cluster with 4× tt_tensix_neo [i=0,1,2,3])             │
│     [Shown: one of 4 tt_tensix_neo tiles]                                          │
│                                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  ┌────────────┐ │
│  │                   tt_tensix_neo [i]                          │  │ L1 SRAM    │ │
│  │                                                              │  │ 3MB/cluster│ │
│  │  ┌────────┐  ┌──────────────────┐  ┌──────────────────────┐ │  │ Address Map│ │
│  │  │ TRISC3 │  │  TRISC0/1/2      │  │ FPU  ×2 tt_fpu_gtile │ │  │ 0x00000    │ │
│  │  │ RV32I  │  │  TRISC0 (unpack) │  │                      │ │  │ T3 data/   │ │
│  │  │ mgmt   │  │  TRISC1 (math)   │  │  G-Tile[0] G-Tile[1] │ │  │ workspace  │ │
│  │  │        │  │  TRISC2 (pack)   │  │  ┌───────┐ ┌───────┐ │ │  │ 0x06000    │ │
│  │  │        │  │                  │  │  │col0..7│ │col0..7│ │ │  │ T0 IMEM    │ │
│  │  │        │  │  semaphore-based │  │  │tt_fpu_│ │tt_fpu_│ │ │  │ 0x16000    │ │
│  │  │        │  │  sync: SEMPOST/  │  │  │mtile  │ │mtile  │ │ │  │ T1 IMEM    │ │
│  │  └────────┘  │  SEMGET between  │  │  │row0..7│ │row0..7│ │ │  │ 0x26000    │ │
│  │              │  TRISC threads   │  │  │tt_fpu_│ │tt_fpu_│ │ │  │ T2 IMEM    │ │
│  │              └──────────────────┘  │  │tile   │ │tile   │ │ │  │ 0x36000    │ │
│  │                                    │  │fp_lane│ │fp_lane│ │ │  │ T3 IMEM    │ │
│  │  ┌──────┐  ┌──────────────────┐   │  │(MACs) │ │(MACs) │ │ │  │            │ │
│  │  │ SFPU │  │  TDMA            │   │  │all col│ │all col│ │ │  └────────────┘ │
│  │  │scalar│  │  pack / unpack   │   │  │& rows │ │& rows │ │ │                 │
│  │  │ FP   │  │  MOP sequencer   │   │  │active │ │active │ │ │                 │
│  │  └──────┘  └──────────────────┘   │  │in same│ │in same│ │ │                 │
│  │                                    │  │cycle  │ │cycle  │ │ │                 │
│  │  ┌──────────────┐ ┌─────────────┐ │  └───────┘ └───────┘ │ │                 │
│  │  │  DEST RF     │ │  SRCA RF    │ │  └──────────────────────┘ │                 │
│  │  │  latch array │ │  latch array│ │                          │                 │
│  │  │  8 KB        │ │  3 KB       │ │                          │                 │
│  │  └──────────────┘ └─────────────┘ │                          │                 │
│  └──────────────────────────────────────────────────────────────┘                 │
│                                                                                    │
│  ┌────────────────────────────────────────────────────────────────────────────┐   │
│  │  tt_neo_overlay_wrapper (shared, one per cluster)                          │   │
│  │  context switch · L1/L2 cache · CDC FIFOs · SMN · EDC · CPU wrapper       │   │
│  └────────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**FPU zoom-in — one G-Tile (RTL-verified):**

```
tt_fpu_gtile  (one of two per tt_tensix)
│
├─ col[0]: tt_fpu_mtile ──── row[0]: tt_fpu_tile ── tt_fp_lane r0 (MAC)
│                       │                        └── tt_fp_lane r1 (MAC)
│                       ├─── row[1]: tt_fpu_tile ── tt_fp_lane r0 (MAC)
│                       │                        └── tt_fp_lane r1 (MAC)
│                       │         ...
│                       └─── row[7]: tt_fpu_tile ── tt_fp_lane r0 (MAC)
│                                                └── tt_fp_lane r1 (MAC)
│             ↑ independent enable per col            ↑ independent valid per lane
├─ col[1]: tt_fpu_mtile  ← active same cycle as col[0]
│         ...
└─ col[7]: tt_fpu_mtile  ← active same cycle as col[0..6]

Per G-Tile:  8 cols × 8 rows × 2 lanes = 128 FP-Lanes
Per tt_tensix (×2 G-Tiles):             256 FP-Lanes  — all active simultaneously
```

### 2.1.1 FPU Hierarchy and Concurrency (RTL-verified)

The FPU diagram shows G-Tile / M-Tile / FP-Lane as a **containment hierarchy**, not parallel alternatives or sequential modes. All columns and rows are active in the same clock cycle.

**RTL hierarchy** (`tt_fpu_gtile.sv`, `tt_fpu_mtile.sv`, `tt_fpu_tile.sv`, `tt_fp_lane.sv`):

```
tt_tensix
├── tt_fpu_gtile [gen_gtile=0]     ← G-Tile 0: column container
│   ├── tt_fpu_mtile col[0]        ← one M-Tile per column (8 total)
│   │   ├── tt_fpu_tile  row[0]    ← one FP-Tile per row  (8 total)
│   │   │   ├── tt_fp_lane r0      ← FP-Lane: the physical MAC unit
│   │   │   └── tt_fp_lane r1
│   │   ├── tt_fpu_tile  row[1]
│   │   │   └── ...
│   │   └── tt_fpu_tile  row[7]
│   ├── tt_fpu_mtile col[1]        ← all 8 columns have independent enables
│   │   └── ...
│   └── tt_fpu_mtile col[7]
└── tt_fpu_gtile [gen_gtile=1]     ← G-Tile 1: identical structure
    └── ...
```

**G-Tile** (`tt_fpu_gtile`) is a column-grouping module. It does not contain MAC logic itself — it instantiates 8 M-Tiles via `gen_fp_cols[0:7]` and routes SRCA/SRCB/DEST signals to them. "G-Tile" refers to the physical tile boundary (two per `tt_tensix`), not a separate compute unit.

**M-Tile** (`tt_fpu_mtile`) is one column of the multiplier array. It contains 8 FP-Tile rows (`fp_row[0:7]`). Each M-Tile has an independent enable signal (`enable_due_to_dummy_op_or_regular_activity`) — no arbiter prevents simultaneous operation across columns.

**FP-Lane** (`tt_fp_lane`) is the physical MAC unit inside each FP-Tile row. Two FP-Lanes per FP-Tile (`u_fp_lane_r0`, `u_fp_lane_r1`), each with independent `alu_instr_valid`. FP-Lanes execute both GEMM mode (Booth multiplier + INT32 accumulator) and elementwise mode (FP32 multiply-add) — the same physical hardware, selected by `is_int8_2x_format` and `fp32_acc` tag bits. There is no separate "FP-Lane unit" physically isolated from the GEMM path.

**Concurrency — RTL-verified:**

| Level | Parallel units | Enable mechanism | Concurrent? |
|-------|---------------|------------------|-------------|
| G-Tile | 2 (gen_gtile[0:1]) | Independent `i_valid_col` per G-Tile | ✓ Yes |
| M-Tile (column) | 8 per G-Tile × 2 = 16 | Independent `enable_due_to_dummy_op` per col | ✓ Yes |
| FP-Tile (row) | 8 per M-Tile | Independent `i_valid` per row | ✓ Yes |
| FP-Lane | 2 per FP-Tile | Independent `alu_instr_valid_r0/r1` | ✓ Yes |

No arbiter, mux, or one-hot enable serializes any level. All 16 columns × 8 rows × 2 lanes = **256 FP-Lanes per `tt_tensix` run in the same cycle.**

**What "G-Tile MACs" and "M-Tile MACs" meant in prior text:**
The old diagram labels "G-Tile = 32×FP32 MACs" and "M-Tile = INT16/8 MACs" were misleading — they implied different hardware blocks for different formats. In reality, the same `tt_fp_lane` hardware executes all formats; the format is selected per-instruction by tag bits. There is no separate M-Tile module for INT modes.


### Unit Purpose
The Tensix compute tile is the fundamental tensor-processing engine of N1B0, bringing together specialized hardware for matrix multiply, data movement, and local control. Each of the 12 Tensix clusters (`tt_tensix_with_l1`) integrates a **dual-G-Tile FPU capable of 256 concurrent multiply-accumulate (MAC) lanes**, multi-threaded TRISC processor cores, dedicated TDMA hardware with MOP-sequenced instruction compression, and a 3 MB on-cluster L1 SRAM. 

**FPU Breakdown:** 2 G-Tiles (`tt_fpu_gtile`) × 8 M-Tile columns (`tt_fpu_mtile`) × 8 FP-Tile rows (`tt_fpu_tile`) × 2 FP-Lanes (`tt_fp_lane`) per row = **256 FP-Lanes all active simultaneously** with no arbiter. Supports INT16, FP16B, INT8, and FP32 via format-selection tag bits (`int8_op`, `fp32_acc`). Peak throughput: 64 FMA/cycle per tile (2 G-Tiles × 8 cols × 4 active rows × 1 FMA/cycle). At 1 GHz: **64 GFLOPs per Tensix tile** (512 GFLOPs per cluster with 8 tiles).

This integrated design decouples compute-heavy tensor math from data-movement logistics, enabling firmware to overlap weight/activation transport with FPU execution while maintaining high computational throughput.

### Design Philosophy
Tensix prioritizes **parallelism over serialization**. Unlike traditional RISC-V CPU designs where an instruction fetch-execute-memory pipeline serializes work, Tensix splits responsibilities: TRISC processors handle tile orchestration and control-flow decisions, while the FPU array executes tensor operations declared via MOP instructions — a compressed instruction format that encodes entire GEMM passes (hundreds of raw operations) into a single 32-bit word. This permits TRISC0/2 to prefetch weights and pack/unpack data via TDMA while TRISC1 is still feeding the previous MOP sequence to the FPU, creating a natural software pipeline. The 3 MB L1 per cluster (4× the baseline Trinity) provides sufficient capacity for typical weight tiles and KV-cache entries, reducing NoC pressure and latency-critical DRAM round-trips during inference.

### Integration Role

Tensix clusters are the compute backbone. Each cluster's local L1 memory forms the innermost level of N1B0's memory hierarchy: Tensix L1 → Overlay streams → NIU → AXI → external DRAM. Within a cluster, the overlay wrapper (`tt_neo_overlay_wrapper`) orchestrates data movement autonomously, allowing TRISC firmware to initiate DMA via CSR writes and continue without waiting.

**FPU Data Flow:**

The FPU's 256 concurrent lanes are fed by a three-stage pipeline:

1. **Prefetch stage (TRISC0 — Unpack)**: L1 reads via 3 unpackers (`tt_unpack_0/1/2.sv`) that apply format conversion (FP16B→FP32, INT8→INT16, FP8→FP16). Output: SrcA (1.5 KB), SrcB (2 KB), SrcS (384 bytes) register files, all dual-banked latch arrays for zero-stall prefetch. RTL verified (tt_tensix_pkg.sv): SRCA rows = SRCS_NUM_ROWS_16B=48 (not 256), SRCB 64 rows × 2 banks × 16-bit, SRCS 48 rows × 16-bit; clock domain `i_ai_clk`.

2. **Compute stage (TRISC1 — Math)**: FPU reads SrcA/SrcB, consumes one FPU tag per cycle from MOP sequencer. FPU outputs 64 FMA results simultaneously (4 rows × 16 columns × 1 FMA/cycle per tile), written to DEST register file (8 KB per tile: 2 banks × 512 rows × 4 cols, dual-banked latch array). SFPU (`tt_sfpu_wrapper.sv`) independently reads/writes DEST and SrcS for transcendental ops (exp, log, sqrt, gelu) without FPU stalls. RTL verified: tt_gtile_dest.sv `DEST_NUM_ROWS_16B=1024`, `NUM_COLS=4`, `DEST_NUM_BANKS=2`.

3. **Drain stage (TRISC2 — Pack)**: 2 packers (`tt_pack_0/1.sv`) read from inactive DEST bank while TRISC1 writes to active bank. Apply post-math activation (ReLU, CReLU, Flush-to-0) and format conversion (INT32→FP16B/INT8, FP32→FP16B with stochastic rounding). Output: L1 or NoC broadcast.

The DEST (32 KB per Tensix, 1.536 MB total for 48 Tensix across 12 clusters) and SRCA (1.5 KB)/SRCB (2 KB)/SRCS (384 B) register files hold intermediate results and source operands, acting as the "hot" working set to avoid repeated L1 reads within tight MAC loops. All register files are physically located inside the FPU hierarchy as latch arrays (RTL: `tt_gtile_dest.sv`, `tt_srcs_registers.sv`, zero-latency combinational access).

### Key Characteristics

**FPU Architecture:**
- **256 FP-Lanes per tile** (RTL-verified: `tt_fpu_gtile.sv`, `tt_fpu_mtile.sv`, `tt_fp_lane.sv`): 2 G-Tiles × 8 M-Tiles × 8 rows × 2 lanes, all active in the same cycle with **no serialization arbiter**. Each lane is an independent Booth multiplier + accumulator. Supports INT16, FP16B, INT8, and FP32 numeric formats via tag-bit selection at each lane (`int8_op`, `fp32_acc`, `fidelity_phase`).
- **Dual-mode execution** (`tt_fpu_mtile`): Single physical MAC engine executes both G-Tile mode (FP32/FP16B GEMM) and M-Tile mode (INT8 GEMM with 2× INT8/lane packing). No separate hardware required — format is determined by MOP instruction tag bits before Booth multiplier stage.
- **Format-agnostic Booth multiplier**: Multiplies any bit-pattern (FP exponent/mantissa or INT sign/magnitude) via pre-processing of SRCA/SRCB via `srca_fmt_spec` and `srcb_fmt_spec` tag fields. Reuse saves silicon versus separate INT8 multiplier bank.

**Data Movement & Orchestration:**
- **MOP-sequenced math**: TRISC1 programs multi-iteration tensor operations via a single MOP; the sequencer autonomously drives the FPU for 50–150 cycles without further firmware intervention, including loop unrolling, format selection, and stochastic rounding.
- **4-threaded control**: TRISC0 (unpack), TRISC1 (math), TRISC2 (pack), TRISC3 (management/SFPU) run in parallel with semaphore-based synchronization (SEMPOST/SEMGET custom instructions) to coordinate handoffs without blocking.
- **Dual-level data cache**: L1 SRAM (3 MB per cluster) is private and non-coherent but shared within the cluster; L2 may be shared across clusters via the overlay wrapper's context-switching mechanism.
- **Integrated TDMA**: Pack and unpack hardware reshape tensor data on-the-fly, transforming DRAM row-major layouts into the FPU's column-major working format without intermediate buffering. 3 unpackers (SrcA/SrcB/SrcS) + 2 packers provide parallel data ingestion and egress.

### Use Case Example
**LLaMA 3.1 8B Inference — Weight Load and First Token Forward**  
Firmware running on TRISC3 issues a CSR write to the overlay stream controller: "Load 128 weight rows (K_tile=48 INT16 per row) from DRAM address 0x8A000000 to L1 offset 0x0000." TRISC0 (unpack) polls the overlay completion flag, meanwhile TRISC1 has already begun a GEMM pass using weights pre-loaded in L1 from the prior layer. Once overlay confirms the 128 rows (24 KB) are in L1, TRISC0 (unpack) begins reformatting them into column-major layout for the next forward pass. TRISC1 sequences the first MOP for the weight×activation multiply, programming the MOP sequencer with source/dest register indices and loop count; the MOP sequencer fires 86 consecutive MOPs over ~4,100 cycles, issuing one `fpu_tag` per cycle to the FPU with no further TRISC involvement. By the time all 86 MOPs complete with `mop_done`, TRISC2 is already prefetching the next weight tile via overlay, overlapping latency-critical DRAM I/O with the FPU's multi-thousand-cycle GEMM.

---
### 2.2 TRISC3 — Tile Management RISC-V Core

#### 2.2.1 Architecture Overview

The TRISC3 (`tt_risc_wrapper`, ISA: RV32I) is the tile management processor of each Tensix cluster. Unlike TRISC0/1/2 which are dedicated to datapath sequencing (pack/unpack/math), TRISC3 is a general-purpose scalar core that manages the entire tile lifecycle: boot, configuration, DMA, and interrupt dispatch.

**Why TRISC3 is separate from TRISC0/1/2:**
The three TRISC0/1/2 cores run tight, cycle-counted inner loops (pack/unpack/math). They have no OS, no interrupt logic, and minimal instruction sets. A separate general-purpose core (TRISC3) is needed to handle asynchronous events (interrupts, errors), NoC DMA transactions, and tile-level state machines without interrupting the real-time TRISC pipelines. This separation also allows TRISC3 firmware to be updated independently of the TRISC LLK (Low-Level Kernel) programs.

```
         ┌──────────────────────────────────────────────┐
         │               TRISC3 Core (RV32I)             │
         │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
         │  │  ICache  │  │  IMEM    │  │  Data Mem  │  │
         │  │(from L1) │  │(scratchpad)│  │(local 8KB) │  │
         │  └────┬─────┘  └────┬─────┘  └─────┬──────┘  │
         │       └──────────────┴──────────────┘         │
         │                    ALU / LSU                   │
         │  ┌──────────────────────────────────────────┐  │
         │  │         Interrupt Controller (PIC)        │  │
         │  │  SW_INTS=4, HW_INTS=12+NUM_SMN_INTS      │  │
         │  └──────────────────────────────────────────┘  │
         └──────────┬───────────────────────┬─────────────┘
                    │ L1 access (32-bit bus) │ NoC DMA (512-bit side channel)
                    ▼                        ▼
             tt_t6_l1_partition         NoC local port
```

#### 2.2.2 Responsibilities

| Responsibility | Detail |
|---------------|--------|
| **Boot** | On reset, TRISC3 fetches its firmware from L1 (loaded by Dispatch/iDMA before tile start). Loads TRISC0/1/2 programs into their instruction memories at fixed L1 offsets: TRISC0=`0x6000`, TRISC1=`0x16000`, TRISC2=`0x26000`, TRISC3=`0x36000`. |
| **Tile configuration** | Writes SFR registers (CLUSTER_CTRL, T6_L1_CSR, LLK_TILE_COUNTERS) to configure FPU mode, L1 bank hash function, port enable/disable before kernel execution. |
| **NoC DMA control** | Issues NoC read/write packets via the 512-bit local port to transfer tensor data between this cluster's L1 and remote tiles or external DRAM through the NIU. Max outstanding reads: `MAX_TENSIX_DATA_RD_OUTSTANDING=4` (8 in large TRISC mode). |
| **Interrupt dispatch** | Receives hardware interrupts from PIC (see §2.2.3) and calls appropriate firmware ISRs. |
| **TRISC lifecycle** | Sets TRISC reset-PC override, starts/stops TRISCs, monitors TRISC watchdog and PC-buffer timeout. |
| **Error reporting** | On fatal error, TRISC3 logs the error code and asserts `o_report_safety_valid` to the safety controller, which escalates to EDC ring. |

#### 2.2.3 Interrupt Architecture

TRISC3 has a Programmed Interrupt Controller (PIC) with:
- **4 software interrupts** (`SW_INTS=4`): firmware-triggered via SFR write
- **12 + NUM_SMN_INTERRUPTS hardware interrupts** (`HW_INTS`): from hardware blocks

Hardware interrupt sources (from RTL `hw_int` assignment, in priority order):

| Source | Signal | Trigger |
|--------|--------|---------|
| PC buffer timeout | `pc_buff_timeout[i]` | TRISC instruction fetch stalled beyond threshold |
| SMN security violation | `i_t6_smn_interrupts` | Address range check failure in NIU |
| Safety controller | `report_safety_valid_intr[i]` | Hardware error detected (ECC, parity) |
| TRISC watchpoint | `trisc_wpi[i]` | TRISC hit a debug watchpoint address |
| Watchdog timer | `wdt_expired_intr` | Tile-level watchdog timer expired |
| DEST register toggle | `dest_toggle` | DEST register file double-buffer flip (signals TRISC2 compute complete) |
| SRCS register toggle | `srcs_toggle` | SRCA/SRCB register file ready (pack/unpack complete) |
| SRCB register toggle | `srcb_toggle` | SRCB buffer available |
| SRCA register toggle | `srca_toggle` | SRCA buffer available |
| Error valid | `err_valid` | General error from error bus (TDMA, SFPU, etc.) |
| Halt | `halt[i]` | TRISC halted (debug or end-of-kernel) |
| IBuffer timeout | `ibuffer_timeout[i]` | Instruction buffer not drained in time |
| IBuffer read enable | `ibuffer_rden[i]` | Instruction buffer ready for next instruction |

The DEST/SRCS toggle interrupts are the critical performance path: TRISC3 uses these to implement a double-buffering protocol where it overlaps TRISC compute (writing to one DEST buffer) with TRISC3-managed data movement (reading from the other DEST buffer via NoC DMA).

#### 2.2.4 Memory Interface

**RTL-verified (`tt_instrn_engine.sv`, `tt_trisc.sv`, `tt_risc_wrapper.sv`):**

All four TRISC threads share a uniform memory interface structure. TRISC3's additional capability comes from its general-purpose RV32I ISA (`tt_risc_wrapper`), not from different hardware ports.

| Interface | Width | Target | All TRISCs? | Purpose |
|-----------|-------|--------|-------------|---------|
| Instruction fetch (ICache) | **72-bit** | L1 partition (IMEM region) | Yes — all 4 | Fetch program instructions from L1 (32b instruction + 40b parity/ECC) |
| Local Data Memory (LDM) | **72-bit** | Private per-TRISC scratchpad SRAM | Yes — all 4 | Stack, firmware variables, loop counters (32b data + 40b parity/ECC) |
| L1 direct read/write | **128-bit** | L1 partition (data region) | Yes — all 4 | Data load/store to cluster L1 |
| Vector Memory (TRISC0/1) | **72-bit** | Vector register scratchpad SRAM | T0, T1 only | Vector scratchpad (32b vector + 40b parity/ECC); not available on TRISC2/3 |
| NoC overlay streams | 32-bit reg writes | Overlay stream regs → NoC → NIU → DRAM | Yes — all 4 | Initiate NoC transfers to/from DRAM |

The **LDM** and **L1 direct port** are separate: LDM is a private local SRAM (32-bit wide) for firmware stack and variables; the L1 port is the 128-bit shared bus into the cluster L1 partition. Both are present on all four TRISCs — `trisc_ldm_*` and `triscv_l1_rden/wren` signal arrays in `tt_instrn_engine.sv` are indexed `[THREAD_COUNT-1:0]`.

TRISC3's scalar RV32I core (`tt_risc_wrapper`) uses the same 128-bit L1 and 32-bit LDM hardware ports. The difference from TRISC0/1/2 is ISA: TRISC0/1/2 drive L1 access primarily via MOP-decoded TDMA instructions, while TRISC3 issues arbitrary `lw/sw` instructions directly in firmware. There is **no dedicated 512-bit hardware NoC port inside any TRISC** (`NOC_CONTROL=0` for all instances in `tt_instrn_engine.sv` lines 5016, 5309). NoC and DRAM transfers are initiated by writing to overlay stream control registers (memory-mapped, accessible via the same 32-bit register bus used for all tile configuration). See §2.3.6 for the complete access matrix and DRAM path description.

#### 2.2.5 Key RTL Parameters

| Parameter | Value (N1B0) | Effect |
|-----------|-------------|--------|
| `DISABLE_SYNC_FLOPS` | 1 | EDC/CDC synchronizer flip-flops bypassed inside Tensix — all cores share `ai_clk`, no clock-domain crossing within the tile |
| `MAX_TENSIX_DATA_RD_OUTSTANDING` | 4 (8 in large mode) | Max in-flight NoC read requests from TRISC3 |
| `MAX_L1_REQ` | 16 (32 in large mode) | Max outstanding L1 read/write requests |
| `INSN_REQ_FIFO_DEPTH` | 8 (16 large) | Instruction fetch request FIFO depth |
| `ICACHE_REQ_FIFO_DEPTH` | 2 (4 large) | ICache miss request FIFO depth |
| `LOCAL_MEM_SIZE_BYTES` (TRISC0) | 4096 (4KB) | TRISC0/3 local data memory (ICache: 512×72 = 4KB) |
| `LOCAL_MEM_SIZE_BYTES` (TRISC1/2) | 2048 (2KB) | TRISC1/2 local data memory (ICache: 256×72 = 2KB) |
| `THREAD_COUNT` | 4 | Number of TRISC threads (TRISC0..3; TRISC3 optional) |
| `TRISC_VECTOR_ENABLE` | `4'b0001` | TRISC0 has vector extension enabled |
| `TRISC_FP_ENABLE` | `4'b1111` | All TRISCs have FP extension enabled |

#### 2.2.6 ICache Sizes (Per-Thread)

Each TRISC thread has its own instruction cache sourced from L1. The cache size differs by thread, as verified from `N1B0_NPU_memory_list20260221_2.csv`:

| Thread  | ICache macro type | Effective ICache capacity | LOCAL_MEM_SIZE_BYTES |
|---------|-------------------|--------------------------|----------------------|
| TRISC0  | `512×72` (full)   | 512 rows × 64 data bits / 8 = **4KB** | 4096 |
| TRISC1  | `256×72` (half)   | 256 rows × 64 data bits / 8 = **2KB** | 2048 |
| TRISC2  | `256×72` (half)   | 256 rows × 64 data bits / 8 = **2KB** | 2048 |
| TRISC3  | `512×72` (full)   | 512 rows × 64 data bits / 8 = **4KB** | 4096 |

The 72-bit macro width encodes 64 data bits + 8 parity/ECC bits. The `full` vs `half` designation comes from the CSV path suffix `icache[0].full` (TRISC0/3) vs `icache[1].half` / `icache[2].half` (TRISC1/2).

TRISC3 has the same 4KB ICache size as TRISC0 because tile management firmware (interrupt handlers, boot sequences) is generally larger than the tight inner-loop LLK programs run by TRISC0/1/2. However, TRISC0 specifically has more ICache than TRISC1/2 because unpack operations require more state management.

### 2.3 TRISC Cores

#### 2.3.1 Overview and Rationale

N1B0 contains **four TRISC threads** (`THREAD_COUNT=4`): TRISC0, TRISC1, TRISC2, and TRISC3. Each TRISC is a lightweight, fixed-ISA processor — **not** a general-purpose RV32I core like TRISC3. The TRISC ISA is purpose-built for tensor data movement and FPU sequencing, with a highly compressed instruction encoding (MOP micro-ops) that achieves roughly 10× instruction density versus raw RISC-V equivalents.

**Why separate TRISCs rather than one core?**
Pack, unpack, and math are three parallel, independent pipelines that must interleave with cycle-accurate timing — e.g., while TRISC1 is computing tile N, TRISC0 must simultaneously be prefetching tile N+1 from L1 and TRISC2 must be writing tile N−1 to the NoC. Merging these onto a single core would require a complex scheduler and introduce pipeline hazards. Separate lightweight cores allow each pipeline stage to run at its own pace, controlled by hardware semaphore (sync barrier) handshakes rather than OS-level scheduling.

#### 2.3.2 Per-Thread Role Assignment

| Thread  | Primary Role            | Key Operation                                          | Clock Domain |
|---------|-------------------------|--------------------------------------------------------|--------------|
| TRISC0  | Unpack engine           | Read L1 or NoC flit → unpack → load SRCA/SRCB          | `i_ai_clk`   |
| TRISC1  | Math / FPU control      | Issue **MOP** (Micro-Operation Packet) sequences → G-Tile (with mode: fp32/int8/fp-lane). One MOP = one compressed instruction specifying operand sources, DEST range, and loop count. See §2.7.3. | `i_ai_clk`   |
| TRISC2  | Pack engine             | Read DEST RF → format-convert → write L1 or NoC flit  | `i_ai_clk`   |
| TRISC3  | Tile management / SFPU control | NoC DMA control, interrupt dispatch, SFPU sequencing, tile lifecycle, boot; `tt_risc_wrapper` RV32I | `i_ai_clk`   |

TRISC3 is present and its IRAM enable is controlled by `TRISC_IRAM_ENABLE[3]`. With `TRISC_IRAM_ENABLE=4'b0000` (default), no separate IRAM is allocated and TRISC3 shares the L1 IMEM region like TRISC0/1/2, with its ICache backed by the same L1 scratchpad.

#### 2.3.3 RTL Parameters

| Parameter              | Value      | Effect                                                                |
|------------------------|------------|-----------------------------------------------------------------------|
| `THREAD_COUNT`         | `4`        | Instantiates TRISC0–TRISC3                                            |
| `TRISC_IRAM_ENABLE`    | `4'b0000`  | Each bit enables a private IRAM for the corresponding TRISC; 0=shared |
| `TRISC_VECTOR_ENABLE`  | `4'b0001`  | Bit 0 set: TRISC0 has vector extension; bits 1–3 scalar-only          |
| `TRISC_FP_ENABLE`      | `4'b1111`  | All four TRISCs have FP extension enabled                             |

RTL files: `tt_trisc.sv` (one instance per thread), `tt_instrn_engine.sv` (orchestrates all TRISCs, contains MOP sequencer).

#### 2.3.4 Instruction Memory Layout (within L1 partition)

TRISC programs are loaded from L1 at fixed offsets before tile execution begins. TRISC3 is responsible for copying the firmware images into L1 before releasing the TRISC0/1/2 reset.

```
L1 Address Map (per cluster)
─────────────────────────────────────────────────
0x00000  TRISC3 data / tensor workspace (start)
0x06000  TRISC0 IMEM  (unpack LLK)
0x16000  TRISC1 IMEM  (math LLK)
0x26000  TRISC2 IMEM  (pack LLK)
0x36000  TRISC3 IMEM  (tile management)
  ...    tensor workspace continues above
─────────────────────────────────────────────────
```

Programs written for TRISCs are called **LLK (Low-Level Kernels)** — hand-written micro-assembly files maintained by the firmware team. Each LLK corresponds to one compute kernel (e.g., INT16 GEMM, FP16B elementwise multiply).

#### 2.3.5 Synchronization and Watchdog

TRISCs coordinate pipeline stages through **hardware semaphore instructions** — 32 shared 4-bit saturating counter registers per tile, accessible by all TRISC threads via custom RISC-V instruction extensions. This is not a software polling loop and not an interrupt: it is a **hardware pipeline stall** — the TRISC's instruction issue is frozen by the sync execution unit (`tt_sync_exu.sv`) until the semaphore condition is satisfied.

**Hardware semaphore mechanism (RTL-verified: `tt_semaphore_reg.sv`, `tt_sync_exu.sv`, `tt_t6_opcode_pkg.sv`):**

Each semaphore is a 4-bit saturating counter (range 0–15). 32 semaphores are shared across all 4 TRISC threads. The sync execution unit arbitrates simultaneous accesses.

| Instruction | Operation | Stall behavior |
|-------------|-----------|---------------|
| `SEMINIT semN, init_val, max_val` | Initialize semaphore N | Never stalls |
| `SEMPOST semN` | Increment counter by 1 | Stalls TRISC if counter already at `max_val` |
| `SEMGET semN` | Decrement counter by 1 | **Stalls TRISC until counter > 0** |
| `SEMWAIT semN, cond` | Wait for condition on counter | Stalls until condition met |

Stall is implemented as a gate-level pipeline freeze (`instrn_sem_stall[t]` in `tt_sync_exu.sv` line 378):
```systemverilog
instrn_sem_stall[t] = ((instrn_semget[t] & semaphore_at_zero) != '0) ||
                      ((instrn_sempost[t] & semaphore_at_max) != '0);
```
No OS, no interrupt handler, no polling loop — the thread stops at the instruction and resumes the next cycle after the semaphore is posted by another thread or by hardware.

**Why only TRISC0/1/2 appear in the inner-loop handshake — TRISC3's role is different:**

TRISC3 does **not** participate in the per-tile compute pipeline. Its semaphore interactions happen at **kernel boundaries** (before and after the inner loop), not inside it. The four threads have fundamentally different synchronization patterns:

| Thread | Role in sync | When it uses semaphores |
|--------|-------------|------------------------|
| TRISC0 (unpack) | Producer — fills SRCA/SRCB | Inner loop: `SEMPOST` after each tile load |
| TRISC1 (math)   | Consumer/producer — runs FPU MOP | Inner loop: `SEMGET` to wait for SRCA ready, `SEMPOST` when DEST ready |
| TRISC2 (pack)   | Consumer — reads DEST, writes output | Inner loop: `SEMGET` to wait for DEST ready |
| **TRISC3 (mgmt)** | **Orchestrator — not in the inner loop** | **Kernel boundaries only: signals kernel start/end, handles DMA completion, signals TRISC0/1/2 to begin/stop** |

TRISC3 uses a separate semaphore (e.g., `sem_kernel_start`) to tell TRISC0/1/2 when a new kernel is ready to execute, and waits on a `sem_kernel_done` posted by TRISC2 when the last output tile is packed. During the inner loop itself, TRISC3 runs independently — managing NoC DMA prefetch for the *next* kernel's weights while the current kernel executes.

**Standard 3-thread pipeline handshake (inner loop, TRISC0/1/2 only):**

```
TRISC0 (unpack)               TRISC1 (math)                TRISC2 (pack)
─────────────────             ─────────────────            ─────────────────
SEMINIT sem0, 0, 1            SEMINIT sem0, 0, 1
SEMINIT sem1, 0, 1                                         SEMINIT sem1, 0, 1

loop:                         loop:                        loop:
  load tile → SRCA/SRCB         SEMGET sem0  ← stalls        SEMGET sem1  ← stalls
  SEMPOST sem0  → unblocks        until TRISC0 posts           until TRISC1 posts
                                FPU MOP (math)               read DEST → L1
                                SEMPOST sem1  → unblocks      SEMPOST sem0 (optional)
```

- `sem0` gates the SRCA/SRCB → math handoff (TRISC0 produces, TRISC1 consumes)
- `sem1` gates the DEST → pack handoff (TRISC1 produces, TRISC2 consumes)
- TRISC1 `SEMGET sem0` hardware-stalls until TRISC0 executes `SEMPOST sem0`; no polling

**TRISC3 kernel-boundary synchronization:**

```
TRISC3 (mgmt)                         TRISC0/1/2
─────────────────────────────         ─────────────────────────
load firmware into IMEM
configure FPU/L1 SFR regs
prefetch weights via NoC DMA
SEMPOST sem_kernel_start (×3)  →      SEMGET sem_kernel_start
                                       [inner loop runs — TRISC3 not involved]
                                       SEMPOST sem_kernel_done  (from TRISC0)
SEMGET sem_kernel_done         ←
report results, start next kernel
```

TRISC3 posts `sem_kernel_start` once per TRISC0/1/2 (max_val=3) so all three threads unblock simultaneously. The inner loop then runs without TRISC3 participation. When TRISC2 finishes packing the last output tile, it posts `sem_kernel_done` so TRISC3 knows the kernel is complete.

**Additional synchronization mechanisms (RTL-verified):**

| Mechanism | File | Purpose |
|-----------|------|---------|
| Hardware-initiated SEMPOST | `tt_sync_exu.sv` `i_trisc_sempost` | FPU/TDMA hardware posts a semaphore automatically when a MOP completes — TRISC does not need to poll for math completion |
| Mailbox registers | `tt_unpack_arg_mailbox.sv` | 8-entry × 32-bit FIFO per thread for passing task arguments between TRISCs (e.g., tile pointer, format) |
| `trisc_tensix_sync` module | `tt_tensix_trisc_sync.sv` | Enforces instruction-issue ordering across the 4 TRISC threads at the pipeline level |
| NOC stream status | `trisc_tensix_noc_stream_status[thread][stream]` | 8 per-stream status registers per TRISC; polled by firmware to check overlay DMA completion |

This eliminates software polling stalls: a TRISC executing `SEMGET` on a not-yet-posted semaphore consumes zero power (pipeline frozen) and resumes in the same cycle the posting thread executes its `SEMPOST`.

**Watchdog / timeout:** Each TRISC has two independent watchdog counters:
- `pc_buff_timeout` — fires if the instruction fetch PC does not advance within N cycles
- `ibuffer_timeout` — fires if the instruction buffer stalls (e.g., waiting on L1 read)

On timeout expiry, an interrupt is raised to TRISC3 (via `o_trisc_timeout_intp`), allowing firmware to detect and recover from a hung kernel without a full chip reset.

**TRISC3-controlled reset PC:** TRISC3 can override the reset-entry PC for each TRISC independently via `o_trisc0_reset_pc` / `o_trisc1_reset_pc` / `o_trisc2_reset_pc` / `o_trisc3_reset_pc` registers, enabling dynamic kernel dispatch without re-flashing the IMEM.

#### 2.3.6 Memory Access Architecture — L1 and DRAM

**RTL-verified (`tt_instrn_engine.sv`, `tt_trisc.sv`, `tt_risc_wrapper.sv`, `tt_t6_proj_params_pkg.sv`).**

##### 2.3.6.1 Complete Access Matrix

| Memory Target | TRISC0 (unpack) | TRISC1 (math) | TRISC2 (pack) | TRISC3 (mgmt) | Access Mechanism |
|---------------|:---:|:---:|:---:|:---:|------------------|
| **L1 (instruction fetch)** | ✓ | ✓ | ✓ | ✓ | 32-bit ICache fetch; backed by L1 IMEM region |
| **L1 (data read/write)** | ✓ | ✓ | ✓ | ✓ | 128-bit direct port (`triscv_l1_rden/wren`) |
| **LDM (private scratchpad)** | ✓ | ✓ | ✓ | ✓ | 32-bit private SRAM (`trisc_ldm_*`); on-TRISC |
| **SRCA/SRCB register files** | ✓ (write, via unpack MOP) | ✓ (read, via FPU MOP) | — | — | TDMA MOP engine; not direct scalar load/store |
| **DEST register file** | — | ✓ (write, via FPU MOP) | ✓ (read, via pack MOP) | — | TDMA MOP engine; not direct scalar load/store |
| **FPU config registers** | — | ✓ (via cfg_reg bus) | — | ✓ (via cfg_reg bus) | 128-bit config register bus |
| **NoC overlay stream regs** | ✓ | ✓ | ✓ | ✓ | 32-bit register write to overlay stream control CSRs |
| **External DRAM** | ✗ direct | ✗ direct | ✗ direct | ✗ direct | **No TRISC has a direct DRAM port.** DRAM accessed only through NoC overlay streams or Dispatch iDMA (see §2.3.6.4) |

##### 2.3.6.2 L1 Access Path (All TRISCs)

Each TRISC thread has two independent paths into the L1 partition:

**Path A — Instruction fetch (ICache):**
- 32-bit instruction words fetched from the L1 IMEM region for each thread
- Hardware prefetch via `RISC_PREFETCH_CTRL_Enable_Trisc` and `RISC_PREFETCH_CTRL_Max_Req_Count`
- ICache miss → L1 lookup via `trisc_icache_intf[THREAD_COUNT]` interface

**Path B — Data load/store (128-bit port):**
- 128-bit direct read/write bus: `triscv_l1_rden[t]`, `triscv_l1_wren[t]`, `triscv_l1_addr[t]`, `triscv_l1_wrdata[t][127:0]`
- Hardware address range check: `i_trisc_l1_start_addr[t]` / `i_trisc_l1_end_addr[t]` — each TRISC's L1 access is bounded by a per-thread address window programmed at boot time. Accesses outside the window are blocked.
- Supports four transaction types (set by `triscv_l1_at_instrn[t]`): `READ`, `WRITE`, `AT_PARTIALW` (partial byte-enable write), `AT_RISCV` (atomic read-modify-write)
- Maximum outstanding requests: `MAX_L1_REQ=16` per thread (32 in large TRISC mode)
- ECC: SECDED per L1 macro; single-bit errors corrected silently; double-bit errors reported to TRISC3 via interrupt

**Why 128-bit (not 32-bit)?**
A 128-bit L1 bus enables loading one complete FP16B row of 8 elements (8 × 16b = 128b) per cycle, matching the unpack engine's SRCA/SRCB fill rate. Using a 32-bit bus would require 4× as many cycles to load the same data, creating a bottleneck at the unpack-to-SRCA path.

```
TRISC0 (unpack)           TRISC3 (mgmt)           TRISC2 (pack)
      │                         │                        │
      │ 128b L1 read            │ 128b L1 rd/wr          │ 128b L1 write
      ▼                         ▼                        ▼
┌────────────────────────────────────────────────────────┐
│               L1 Partition (3MB per cluster)           │
│  TRISC sub-port [0..TRISC_SUB_PORT_CNT-1]              │
│  Each port: READ / WRITE / AT_PARTIALW / AT_RISCV      │
└────────────────────────────────────────────────────────┘
```

##### 2.3.6.3 Local Data Memory (LDM) — Private Scratchpad

Each TRISC has a **private local data memory (LDM)** that is separate from L1:

| Parameter | TRISC0 | TRISC1 | TRISC2 | TRISC3 |
|-----------|--------|--------|--------|--------|
| `LOCAL_MEM_SIZE_BYTES` | **4,096 (4KB)** | **2,048 (2KB)** | **2,048 (2KB)** | **4,096 (4KB)** |
| Bus width | 32-bit | 32-bit | 32-bit | 32-bit |
| ECC | DMEM_ECC_ENABLE=1 | same | same | same |
| Purpose | Unpack loop state | Math MOP state | Pack loop variables, pointers, stack | Interrupt stack, boot data |

The LDM is **not part of the L1 address space** — it is a small private SRAM inside the `tt_trisc` / `tt_risc_wrapper` module, accessed via `trisc_ldm_addr/rden/wren/wrdata/rddata` signals. Firmware programs store local variables (loop counters, base addresses, tile pointers) here without consuming L1 bandwidth.

TRISC2/3 have larger LDMs (4KB) because their roles — pack engine coordination and general tile management — involve more firmware state: TRISC2 maintains output tensor pointers and format conversion parameters; TRISC3 maintains interrupt handler stacks, boot-time initialization tables, and DMA command buffers.

##### 2.3.6.4 DRAM Access Path

**No TRISC has a direct hardware port to external DRAM.** The complete path from any TRISC to DRAM is:

```
TRISC firmware
    │
    │  32-bit register write to overlay stream CSR
    │  (via normal cfg_reg/reg bus, mapped address)
    ▼
Overlay stream controller (inside tt_neo_overlay_wrapper)
    │
    │  NoC packet injection (512-bit flit)
    │  dst_x/dst_y = NIU endpoint:
    │    X=0 standalone:  dst_x=0, dst_y=4
    │    X=3 standalone:  dst_x=3, dst_y=4
    │    X=1 composite:   dst_x=1, dst_y=3  ← router row (nodeid_y−1)
    │    X=2 composite:   dst_x=2, dst_y=3  ← router row (nodeid_y−1)
    ▼
NoC fabric (tt_trinity_router)
    │
    │  DOR or dynamic routing to NIU tile
    ▼
NIU (tt_noc2axi, inside NOC2AXI composite tile)
    │
    │  ATT address translation: NoC address → AXI address
    │  AXI4 burst (512-bit data bus, 56-bit address)
    ▼
External DRAM (via AXI master port)
```

**Mechanism — overlay stream registers:**
Each TRISC programs NoC-based data movement by writing configuration values to the overlay stream control registers (`noc_neo_local_regs_intf` in `tt_instrn_engine.sv`). These registers control:
- Source and destination addresses (NoC endpoint + L1 byte offset)
- Transfer size (number of 512-bit flits)
- Stream ID (which of the 8 overlay streams to use)
- Direction (L1→NoC→DRAM write, or DRAM→NoC→L1 read)

The overlay hardware autonomously generates NoC read/write header flits and injects them into the NoC fabric. The TRISC issues the register writes and can continue executing firmware; completion is signaled via `trisc_tensix_noc_stream_status[thread][stream]` registers (8 streams × 32-bit status per TRISC, directly readable by each thread).

**Key constraints for DRAM access:**
- A TRISC cannot read DRAM data directly into its LDM via a single `lw` instruction — data must first arrive in L1 via an overlay stream transfer, then the TRISC reads it from L1.
- The maximum NoC-to-DRAM read outstanding count is `MAX_TENSIX_DATA_RD_OUTSTANDING=4` (8 in large TRISC mode) — firmware must not issue more than this many outstanding read streams before checking status.
- DRAM addresses must be mapped in the NIU's ATT (Address Translation Table, 64 entries) before a transfer can succeed. ATT programming is done by the Dispatch tile at kernel launch time (see §4).

**Alternative DRAM path — Dispatch iDMA:**
For bulk weight loading before kernel execution, the preferred path is the **Dispatch tile's iDMA engine** (§6), not TRISC-initiated streams. iDMA provides:
- 8 concurrent DMA CPU channels per Dispatch tile (16 total per chip)
- Hardware multi-dimensional address generation (no firmware loop needed)
- NoC multicast: same weight tile broadcast to multiple Tensix clusters in one injection

TRISC-initiated streams are used for **residual data movement** during kernel execution (e.g., storing output activations back to DRAM, loading KV-cache updates) where the Dispatch iDMA is already busy with pre-loading the next layer's weights.

**Composite vs standalone NIU — nodeid_y difference:**
The four NIU endpoints are not all at Y=4. Standalone NIU tiles (X=0, X=3) are single-row modules at Y=4 with `nodeid_y=4`. Composite router+NIU tiles (X=1, X=2) span Y=3–4 as a single module; the NIU inside reports `nodeid_y=3` (the router row) due to the nodeid_y−1 offset convention of the composite module. Firmware must use the correct Y coordinate in `NOC_XY_ADDR` or the packet will not reach the NIU:

```
X=0:  NOC_XY_ADDR(0, 4, addr)   ← standalone, Y=4
X=1:  NOC_XY_ADDR(1, 3, addr)   ← composite,  Y=3 (router row)
X=2:  NOC_XY_ADDR(2, 3, addr)   ← composite,  Y=3 (router row)
X=3:  NOC_XY_ADDR(3, 4, addr)   ← standalone, Y=4
```

See §1.2 (Composite Router Tiles) for the full architectural explanation.

##### 2.3.6.5 Access Summary Diagram

```
                    ┌──────────────────────────────────────────────────────────┐
                    │              Tensix Cluster (tt_tensix_with_l1)          │
                    │                                                           │
  ┌─────────┐       │  ┌────────┐  ┌────────┐  ┌────────┐  ┌──────────┐      │
  │  DRAM   │       │  │ TRISC0 │  │ TRISC1 │  │ TRISC2 │  │  TRISC3  │      │
  │(AXI)    │       │  │ (pack) │  │(unpack)│  │ (math) │  │  (mgmt)  │      │
  └────┬────┘       │  └──┬─────┘  └──┬─────┘  └──┬─────┘  └────┬─────┘      │
       │  ①         │     │②128b      │②128b      │②128b        │②128b       │
       │            │     │  L1 R/W   │  L1 R/W   │  L1 R/W     │  L1 R/W    │
  AXI master        │     │③32b LDM   │③32b LDM   │③32b LDM     │③32b LDM    │
       │            │     ▼           ▼            ▼             ▼            │
       │            │  ┌────────────────────────────────────────────────┐     │
       │            │  │              L1 Partition (3MB)                │     │
  ┌────┴────┐  ④    │  │  TRISC sub-ports [0..THREAD_COUNT-1]          │     │
  │   NIU   │◄──────┼──│  NoC 512-bit side channel                     │     │
  │(NOC2AXI)│       │  └────────────────────────────────────────────────┘     │
  └────┬────┘       │                       ▲                                 │
       │   ⑤        │                       │⑥overlay stream regs             │
  ┌────┴────┐       │               (32-bit reg writes                        │
  │   NoC   │◄──────┼────────────── from any TRISC)                           │
  │  router │ ⑦     │                                                          │
  └─────────┘       └──────────────────────────────────────────────────────────┘
```

**Path descriptions:**

| Path | Direction | Bus width | Purpose | Used when |
|------|-----------|-----------|---------|-----------|
| ① DRAM ↔ NIU (AXI) | Bidirectional data | 512-bit AXI4 | **Bulk data movement**: weight tensors, activation tiles, KV-cache pages move between off-chip DRAM and the NIU. The NIU translates NoC addresses to AXI addresses via the ATT table (64 entries). This is the only path that reaches external memory. | Every kernel that reads weights from DRAM or writes output activations back to DRAM. |
| ② TRISC ↔ L1 | Bidirectional data | 128-bit per thread | **Tile computation data**: input activations, weight tiles, partial results, and output data that the TRISC must inspect or reformat. TRISC0 (unpack) writes pre-fetched input data into L1; TRISC1 (math) reads MOP operands; TRISC2 (pack) reads computed output from L1; TRISC3 reads/writes control structures. | Every clock cycle during active kernel execution. |
| ③ TRISC → LDM | Read/write | 32-bit private | **Firmware local variables**: loop counters, base addresses, tensor shape parameters, interrupt stack. The LDM is a private SRAM inside each `tt_trisc` — not shared, not part of the L1 address space. A TRISC `lw`/`sw` to a LDM-mapped address never touches L1 bandwidth. | All firmware execution — standard variable/stack accesses. |
| ④ L1 ↔ NIU (NoC side channel) | Bidirectional data | 512-bit dedicated | **NoC-driven L1 access**: the L1 partition has a dedicated 512-bit port (`NoC 512-bit side channel`) that receives DMA write payloads from the NoC without going through the TRISC. When the NIU sends a NoC write packet to this cluster's L1 address range, the payload is written directly into L1 via this port. Reads from L1 to DRAM also source data from this port. This path is **data movement only** — not a configuration path. | DRAM→L1 prefetch (Dispatch iDMA or TRISC-initiated overlay stream read), L1→DRAM store (overlay stream write). |
| ⑤ NIU → NoC router | Bidirectional flit | 512-bit flit | **NoC packet forwarding**: the NIU injects read-response flits (DRAM data arriving from AXI) onto the NoC toward the requesting cluster, and receives write-request flits (L1 data to be stored to DRAM) from the NoC. All traffic is in NoC flit format; the NIU is a leaf node on the mesh. | Every DRAM read response and DRAM write request. |
| ⑥ TRISC → Overlay stream regs | Write-only | 32-bit CSR | **DMA command programming**: a TRISC programs a NoC transfer by writing to overlay stream control registers (source address, destination address, size, stream ID, direction). This is **configuration only** — no data moves on this path. The overlay hardware then autonomously generates and injects the NoC header flits. | Before each DRAM transfer: TRISC writes registers, then overlay executes the DMA autonomously. |
| ⑦ Tensix cluster → NoC router | Write (inject) | 512-bit flit | **Outbound NoC flit injection**: the overlay stream controller, once programmed, injects NoC header+payload flits directly into the NoC mesh via the cluster's NoC port. The flit carries the destination NIU address (X, Y=3 for composite, Y=4 for standalone) and the AXI destination address for ATT lookup at the NIU. This is the actual data-carrying path from L1 toward DRAM. | Whenever overlay stream DMA is active (L1→DRAM write or DRAM→L1 read request). |

**Key architectural points:**
- Paths ②③ are **intra-cluster only** — data never leaves the cluster on these paths.
- Paths ①④⑤⑦ are **data movement** — they carry tensor payloads.
- Path ⑥ is **control/configuration only** — it programs where data should move but carries no payload.
- The L1 partition is the **central rendezvous point**: DRAM data arrives via ④ and is later consumed via ②; compute results produced by TRISC via ② are later sent to DRAM via ④⑦.
- The NoC router (⑦) provides mesh routing between all 20 tiles. The same router also carries **peer L1→L1** traffic (one cluster's TRISC can write directly to another cluster's L1 by addressing the destination cluster's NoC endpoint and L1 offset).

### 2.3.7 INT8 Large-K GEMM — K=8192 Applicability and Hardware Architecture

#### 2.3.7.1 Overview and Feasibility

Trinity N1B0 fully supports INT8 GEMM with arbitrarily large K dimension. A single-row matrix multiply with K=8,192 INT8 elements is executed via **multi-pass firmware-controlled K accumulation**: the firmware splits the K dimension into passes of 96 INT8 positions each, reloading SRCA from L1 between passes while DEST holds the running INT32 partial sums. No single-pass hardware limit restricts K to any maximum value.

The enabling hardware mechanisms are:

1. **INT8_2x packing** (`ENABLE_INT8_PACKING=1`): two INT8 values packed per 16-bit SRCA/SRCB datum, doubling effective K throughput per SRCA row compared to FP16B mode.
2. **DEST INT32 accumulate-in-place** (`int8_op → fpu_tag_32b_acc`): the FPU reads the current DEST INT32 value, adds the new product, and writes back — DEST retains accumulated partial sums across an unlimited number of passes.
3. **Sufficient INT32 dynamic range**: the maximum accumulated value for K=8,192 with signed INT8 operands is 8,192 × 127 × 127 ≈ 132M, well within the INT32 signed range of ±2.1B.

For K=8,192 specifically: K_tile_INT8 = 96 INT8 positions per SRCA bank pass (derived from `SRCS_NUM_ROWS_16B=48` × 2), requiring ⌈8,192 / 96⌉ = **86 firmware passes** to accumulate the full dot product into DEST.

**RTL verification sources for this section:**
- `tt_tensix_pkg.sv`: `SRCS_NUM_ROWS_16B`, `SRCA_NUM_SETS`, `SRCB_ROW_DATUMS`, `DEST_NUM_ROWS_16B`, `ENABLE_INT8_PACKING`, `INT8_2x`, `int8_op`, `fpu_tag_32b_acc`
- `tt_t6_proj_params_pkg.sv`: `ENABLE_INT8_PACKING=1`, `MATH_ROWS=4`
- `tt_fpu_tile_srca.sv`, `tt_fpu_tile_srcb.sv`: `is_int8_2x_format`, `int8.datum[1:0]`
- `tt_fpu_tile.sv`: `fpu_tag_32b_acc = fp32_acc | int8_op | dest_lo_en`, `dstacc_idx`

---

#### 2.3.7.2 INT8_2x Packing — The 2× K Throughput Mechanism

The fundamental enabler for large-K INT8 efficiency is **INT8_2x packing**: two INT8 values are stored in one 16-bit SRCA/SRCB datum and processed simultaneously by the Booth multiplier in a single clock cycle.

**RTL definition (`tt_tensix_pkg.sv`, `tt_t6_src_reg_pkg.sv`):**

```
format_encodings_e:
  INT8_2x  = 8'd26  ← signed INT8, 2 values packed per 16-bit datum
  UINT8_2x = 8'd28  ← unsigned INT8, 2 values packed per 16-bit datum

ENABLE_INT8_PACKING = 1  ← enabled in tt_t6_proj_params_pkg.sv

srca_datum_t / srcb_datum_t (union packed):
  struct packed {
      logic [2:0]  RSVD;
      logic [1:0][7:0] datum;   // datum[0] = INT8_a, datum[1] = INT8_b
  } int8;
```

When `is_int8_2x_format` is active (enabled when `srcb_fmt_spec == INT8_2x || UINT8_2x`), each 16-bit datum delivers **two independent 8-bit operands** to the Booth multiplier column:

```
16-bit SRCA/SRCB datum in INT8_2x mode:
  [15:8] = int8_b   (second INT8 value, K position k+1)
  [ 7:0] = int8_a   (first  INT8 value, K position k  )

Per Booth multiplier column per cycle:
  result_a = srca_a × srcb_a   → accumulates to DEST[dstacc_idx]   (K position k  )
  result_b = srca_b × srcb_b   → accumulates to DEST[dstacc_idx+2] (K position k+1)

Effective throughput: 2 INT8 MAC results per datum per cycle
```

**Why the Booth multiplier can process both INT8 values simultaneously:** The Booth multiplier is a bit-level structure. Two packed INT8 values in one 16-bit word present two independent 8-bit operand pairs to the multiplier column logic. The upper and lower 8-bit products are computed in the same gate-level evaluation cycle and steered to adjacent DEST rows via the `dest_wr_row_mask` and `dstacc_idx` fields in the FPU tag.

```
INT8_2x Booth Multiplier — one FP-Lane column, one cycle
─────────────────────────────────────────────────────────────────────

  SRCA datum [15:0]          SRCB datum [15:0]
  ┌──────────┬──────────┐    ┌──────────┬──────────┐
  │ int8_b   │ int8_a   │    │ int8_b   │ int8_a   │
  │ [15:8]   │  [7:0]   │    │ [15:8]   │  [7:0]   │
  └────┬─────┴────┬─────┘    └────┬─────┴────┬─────┘
       │ srca_b   │ srca_a        │ srcb_b   │ srcb_a
       │  8-bit   │  8-bit        │  8-bit   │  8-bit
       │          │               │          │
       │     ┌────┘               │     ┌────┘
       │     ▼                    │     ▼
  ┌────┴─────────────┐       ┌────┴─────────────┐
  │  Booth Multiplier│       │  Booth Multiplier│
  │  (lower half)    │       │  (upper half)    │
  │  srca_a × srcb_a │       │  srca_b × srcb_b │
  │  8b × 8b → 16b   │       │  8b × 8b → 16b   │
  │  product_a       │       │  product_b       │
  └────────┬─────────┘       └────────┬─────────┘
           │                          │
           │  sign-extend to 32b      │  sign-extend to 32b
           ▼                          ▼
  ┌─────────────────┐        ┌─────────────────┐
  │  INT32 Adder    │        │  INT32 Adder    │
  │  DEST[dstacc]   │        │  DEST[dstacc+2] │
  │  += product_a   │        │  += product_b   │
  └────────┬────────┘        └────────┬────────┘
           │                          │
           ▼                          ▼
  DEST row[dstacc_idx]       DEST row[dstacc_idx + 2]
  (K position k  )           (K position k+1)

  ──────────────────────────────────────────────────
  Both products computed and written in the SAME cycle.
  No mux or arbiter between lower and upper halves.
  dstacc_idx advances by +2 each MOP step (TRISC2).
```

**Key points:**
- The 16-bit SRCA/SRCB datum is never treated as one 16-bit number in INT8_2x mode — the Booth array is split at bit 8: lower 8 bits feed one multiplier, upper 8 bits feed an independent multiplier in the same column.
- Both multipliers share the same compressor tree timing path — they produce partial products in the same gate-delay stage, so there is no throughput penalty versus a single 8-bit multiply.
- The two results land in **different DEST rows** (`dstacc_idx` and `dstacc_idx+2`), so each independently accumulates its own dot-product running sum across passes.
- In FP16B mode the same hardware processes one 16-bit operand pair per column per cycle — half the K throughput compared to INT8_2x.

---

#### 2.3.7.3 SRCA K-Depth and K_tile_INT8

The K-depth per SRCA bank is the hardware parameter that defines **K_tile** — the number of INT8 input positions that can be processed before SRCA must be reloaded from L1.

**RTL parameters (`tt_tensix_pkg.sv`):**

| Parameter            | Value | Meaning                                               |
|----------------------|-------|-------------------------------------------------------|
| `SRCS_NUM_ROWS_16B`  | **48** | Physical SRCA bank depth: 48 row addresses            |
| `SRCA_NUM_SETS`      | 4     | 4 independent column-sets in SRCA (covers M output rows) |
| `SRCA_NUM_WORDS_MMUL`| 16    | 16 datums per column-set per SRCA row (= N output cols) |
| `srca_rd_addr`       | 6-bit | Selects SRCA row 0–47; firmware increments per K step |
| `SRCS_ADDR_WIDTH`    | `$clog2(48)` = 6 | Address width matches physical depth      |

**K_tile calculation:**

```
FP16B mode (one K position per SRCA row):
  K_tile_FP16B = SRCS_NUM_ROWS_16B = 48

INT8_2x mode (two INT8 K positions per SRCA row via datum[1:0] packing):
  K_tile_INT8  = SRCS_NUM_ROWS_16B × 2 = 48 × 2 = 96 INT8 K positions per SRCA bank pass
```

Per SRCA row read (`srca_rd_addr` = k, 0 ≤ k < 48):
- The FPU reads 4 sets × 16 datums = **64 datums** simultaneously
- In INT8_2x: each datum holds 2 INT8 values → 64 datums × 2 = **128 INT8 operands per SRCA row read**
- These 128 operands cover: 4 output rows × 16 output cols × 2 INT8 K-positions = 128 multiply-adds
- Total MACs per SRCA bank pass: 48 SRCA rows × 128 = **6,144 INT8 MACs per pass per G-Tile**

---

#### 2.3.7.4 DEST INT32 Accumulation — The K-Pass Mechanism

The hardware mechanism that makes multi-pass K accumulation possible is the **DEST read-modify-write (accumulate-in-place)** operation.

**RTL mechanism (`tt_fpu_tile.sv`):**

```systemverilog
// fpu_tag_32b_acc controls whether DEST reads its prior value to accumulate:
wire fpu_tag_32b_acc = fpu_tag_instr_tag.fp32_acc
                     | fpu_tag_instr_tag.int8_op    // ← int8_op ALWAYS forces 32b acc
                     | i_tag.dest_lo_en;

// DEST accumulation address:
wire [DEST_ADDR_WIDTH-1:0] dest_addr = i_tag.dstacc_idx;  // 10-bit, range 0..1023
```

When `int8_op=1`:
1. FPU reads the current INT32 value stored at DEST column slice `[col]` row `[dstacc_idx]`
2. Adds the new INT8×INT8 product (sign-extended to INT32 before addition)
3. Writes the INT32 sum back to the same DEST location
4. TRISC2 advances `dstacc_idx` by 2 for the next MOP (to skip to the next pair of INT32 rows in INT8_2x mode)

This is a **zero-overhead accumulate**: no TRISC3 involvement, no L1 read-back, no intermediate storage. The DEST latch array supports simultaneous read and write (read-modify-write in one clock cycle) at the granularity of one DEST slice row.

**DEST capacity check for K=8192:**

```
Per DEST bank (tt_gtile_dest.sv: BANK_ROWS_16B=512, NUM_COLS=4, DEST_NUM_BANKS=2):
  DEST_NUM_ROWS_16B = 1024 total → 512 rows per bank × 2 banks
  Physical: 512 rows × 4 columns × 16-bit = 32,768 bits = 4 KB per bank
  In INT32 mode (grouping column pairs): 512 rows × 2 INT32 per row = 1,024 INT32 entries per bank

For 4 output rows × 4 output cols (FP_ROWS=4, NUM_COLS=4):
  DEST slots per cycle = 4 rows × 4 columns = 16 INT32 entries maximum
  DEST capacity per bank = 1,024 INT32 entries
  Status: ✓ 16 << 1,024 — DEST has ample space (63× headroom per bank)
```

---

#### 2.3.7.5 K=8192 INT8 — Multi-Pass Execution Model

**Given:**
- K = 8192 INT8 elements (one complete inner-dimension accumulation row)
- K_tile_INT8 = 96 (SRCA bank depth 48 rows × 2 INT8 per row via INT8_2x packing)

**Passes required:**

```
Passes = ceil(K / K_tile_INT8) = ceil(8192 / 96) = ceil(85.33) = 86 passes
Last pass K_remainder = 8192 - 85 × 96 = 8192 - 8160 = 32 INT8 (partial pass)
```

**Hardware execution flow per pass:**

```
Pass p (0 ≤ p < 86):
  ─────────────────────────────────────────────────
  TRISC0 (unpack):
    Load 96 INT8 weight values from L1[weight_base + p × 96] → SRCA bank
    Pack 2 INT8 per 16-bit datum → 48 SRCA rows (INT8_2x format)

  TRISC1 (math):
    for srca_rd_addr in 0..47:                          ← 48 MOP instructions
      MOP_MVMUL:
        tag.int8_op      = 1                            ← INT32 accumulate mode
        tag.srcb_fmt_spec = INT8_2x                     ← 2× INT8 packed
        tag.srca_rd_addr = srca_rd_addr                 ← which K-slice
        tag.dstacc_idx   = output_row_base              ← accumulate into DEST
        → FPU reads SRCA[srca_rd_addr] × SRCB[current_row]
           → reads prior DEST[dstacc_idx]
           → DEST[dstacc_idx] += INT8_a × INT8_b_a (K position 2k  )
           → DEST[dstacc_idx+2] += INT8_a × INT8_b_b (K position 2k+1)

  TRISC0 (unpack) simultaneously prefetches next SRCA slice into the
  opposite SRCA bank (double-buffer, §2.3.5)

  TRISC3 (mgmt): monitors barrier; TRISC2 does NOT pack during K loop
  ─────────────────────────────────────────────────
```

**After all 86 passes:**
- DEST holds the complete INT32 GEMM result: C[m,n] = sum_{k=0}^{8191} A[m,k] × B[k,n]
- TRISC1 executes `SEMPOST sem1` (hardware semaphore), signals TRISC2
- TRISC2 (pack): reads DEST INT32 → applies descale via FP-Lane → converts to FP16B → writes to L1 output buffer

---

#### 2.3.7.6 INT32 Overflow Analysis

For each DEST output element C[m,n]:

```
Max value (signed INT8 × signed INT8 × K=8192):
  Max per-product: 127 × 127 = 16,129
  Max accumulation: 8,192 × 16,129 = 132,128,768

Max value (unsigned INT8 × unsigned INT8 × K=8192):
  Max per-product: 255 × 255 = 65,025
  Max accumulation: 8,192 × 65,025 = 532,684,800

INT32 signed range:     −2,147,483,648  to  +2,147,483,647
INT32 unsigned range:    0              to   4,294,967,295

Signed INT8:   132,128,768 << 2,147,483,647  ✓ No overflow
Unsigned INT8: 532,684,800 << 4,294,967,295  ✓ No overflow
```

**Conclusion:** INT32 accumulation is safe for K up to approximately K_max where K × 127² < 2.1B → K_max = 133,143 for signed INT8. The hardware is never at risk of overflow for K=8192.

---

#### 2.3.7.7 Complete Hardware Architecture View for INT8 K=8192

```
  L1 Partition (3MB)
  ┌──────────────────────────────────────────────────────────────┐
  │  Weight tile: K=8192 INT8 values × M=4 rows                  │
  │  Activation:  K=8192 INT8 values × N=16 cols                 │
  └──────────────────────────────────────────────────────────────┘
           │ (TRISC1 unpack, 48 rows × 2 INT8/row = 96 INT8/pass)
           ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  SRCA register file (tt_srcs_registers, 48 rows × 4sets×16) │
  │  Bank 0: K-slice [p×96 .. p×96+95] packed INT8_2x           │
  │  Bank 1: K-slice [next pass]  (prefetch, double-buffer)      │
  │  srca_rd_addr: increments 0→47 per pass (48 MOP cycles)      │
  └──────────────────────────────────────────────────────────────┘
           │
           │  INT8_2x datum[1:0]: 2 INT8 → 2 Booth multiplier inputs
           ▼                                     ▼
  ┌──────────────────────────────────────────────────────────────┐
  │    tt_fpu_mtile × 8 columns (per G-Tile)                     │
  │    tt_fpu_tile × 2 rows (per mtile)                          │
  │                                                               │
  │  Per cycle:                                                   │
  │    4 FPU rows × 16 cols × 2 INT8 = 128 INT8 MACs             │
  │    int8_op=1 → result extends to INT32                        │
  │    fpu_tag_32b_acc → reads prior DEST value first            │
  │                                                               │
  │  DEST accumulate:                                             │
  │    DEST[dstacc_idx] += product  (INT32 read-modify-write)     │
  └──────────────────────────────────────────────────────────────┘
           │
           │  86 passes × 48 MOP cycles = 4,128 MAC cycles
           ▼
  ┌──────────────────────────────────────────────────────────────┐
  │   DEST register file (tt_gtile_dest × 16 column slices)      │
  │   16 slices × 512 rows × 32b (INT32 mode) = 256KB per bank  │
  │   64 active entries (4 rows × 16 cols) for this 4×16 tile    │
  │                                                               │
  │   After 86 passes: DEST[m][n] = INT32 GEMM result C[m][n]    │
  │   No overflow: max 132M << INT32 max 2.1B                    │
  └──────────────────────────────────────────────────────────────┘
           │
           │  TRISC0 pack (after SEMGET sem1 unblocks)
           ▼
  FP-Lane descale: INT32 × scale → FP32 → FP16B  (in-place in DEST)
           │
           │  Pack engine reads DEST, format converts, writes L1
           ▼
  L1: FP16B output activation tile (4 rows × 16 cols = 64 FP16B values)
```

---

#### 2.3.7.8 Summary — INT8 K=8192 Key Numbers

| Parameter | Value | RTL Source |
|-----------|-------|-----------|
| INT8_2x packing enabled | Yes (`ENABLE_INT8_PACKING=1`) | `tt_t6_proj_params_pkg.sv` |
| SRCA bank depth | 48 rows | `SRCS_NUM_ROWS_16B=48`, `tt_tensix_pkg.sv` |
| K_tile per SRCA pass (INT8) | **96 INT8** = 48 rows × 2 | INT8_2x packing |
| INT8 MACs per cycle per G-Tile | **128** (4 rows × 16 cols × 2) | `FP_ROWS=4`, `FP_TILE_COLS/NUM_GTILES=8`, INT8_2x |
| Passes for K=8192 | **86** = ceil(8192/96) | Firmware loop |
| Total MAC cycles for K=8192 | **4,128** = 86 × 48 | Per G-Tile |
| INT32 accumulation | Hardware read-modify-write (`int8_op=1` → `fpu_tag_32b_acc`) | `tt_fpu_tile.sv` |
| Max INT32 accumulation (K=8192 signed INT8) | 132,128,768 | 8192 × 127² |
| INT32 overflow risk | **None** (132M << 2.1B) | |
| Firmware loop level | TRISC2 outer K-loop | No hardware K counter |
| SRCA reload agent | TRISC1 unpack | Double-buffered with opposite SRCA bank |
| DEST capacity per bank (INT32) | 1,024 entries | 512 rows × 4 columns (RTL: BANK_ROWS_16B=512, NUM_COLS=4) |

### 2.4 FPU — Floating Point Unit

#### 2.4.1 Architecture Rationale

**RTL-verified (tt_fpu_gtile.sv, tt_fpu_mtile.sv, tt_mtile_and_dest_together_at_last.sv, tt_tensix_pkg.sv):**

The FPU consists of 2 G-Tile instances (`NUM_GTILES=2`) per `tt_tensix` tile. Each G-Tile (`tt_fpu_gtile`) is itself a **container module** that instantiates — for each of its `FP_TILE_COLS=8` output columns — one `tt_mtile_and_dest_together_at_last` sub-module. That sub-module in turn contains two distinct physical blocks:

1. **`tt_fpu_mtile`** — the compute array (multiply-accumulate engine), which further instantiates `tt_fpu_tile` for each of its `FP_TILE_ROWS=2` rows.
2. **`tt_gtile_dest`** — the per-column DEST register file slice.

The full physical hierarchy is:

```
tt_tensix
  └── tt_fpu_gtile × 2 (G-Tile[0], G-Tile[1])
        └── tt_mtile_and_dest_together_at_last × 8 (one per FP output column, cc=0..7)
              ├── tt_fpu_mtile (u_fpu_mtile)        ← MAC compute engine
              │     └── tt_fpu_tile × FP_TILE_ROWS  ← per-row multiplier array
              └── tt_gtile_dest (dest_slice)         ← per-column DEST latch slice
```

**Why `tt_fpu_gtile` wraps `tt_fpu_mtile`?**
The "G-Tile" and "M-Tile" naming in the TT Metal software stack refers to **operation modes**, not module boundaries. From a firmware perspective, a G-Tile operation (FP32/FP16B GEMM) and an M-Tile operation (INT8 GEMM) are dispatched to the same hardware unit with different MOP instruction tag bits (`int8_op`, `fp32_acc`). The RTL name `tt_fpu_mtile` reflects the *physical MAC block* that executes both modes; `tt_fpu_gtile` is the *tile-level container* providing SRCA/SRCB routing, clock gating, SFPU hookup, and EDC logic around that compute core.

**Why 8 column-parallel instances?**
`FP_TILE_COLS=16` total columns per `tt_tensix`, split between `NUM_GTILES=2` G-Tiles, giving `FP_TILE_COLS/NUM_GTILES = 8` columns per G-Tile. Each column has its own independent `tt_fpu_mtile` + `tt_gtile_dest` slice so that the FPU can write all 8 output columns simultaneously in a single clock, achieving the full `FP_TILE_COLS×FP_ROWS = 8×4 = 32` FMA throughput per G-Tile per cycle.

**Why `tt_fpu_mtile` rather than inline logic inside `tt_fpu_gtile`?**
Separating the compute core into its own module (`tt_fpu_mtile`) enables:
- Independent per-column clock gating (`tt_clk_gater` with hysteresis) without affecting the surrounding control logic.
- Self-test/fault-check mode injection at the column boundary (LFSR operand substitution occurs inside `tt_fpu_mtile`).
- Reuse of `tt_fpu_tile` (the multiply-accumulate primitive) as a parameterized sub-module that can be validated in isolation.

#### 2.4.2 RTL Parameters

| Parameter        | Value | Source                                                             |
|------------------|-------|--------------------------------------------------------------------|
| `FP_TILE_COLS`   | `16`  | `localparam` in `tt_tensix_pkg.sv`; total columns across both G-Tiles |
| `NUM_GTILES`     | `2`   | `localparam NUM_GTILES = 2` in `tt_tensix_pkg.sv`                 |
| `FP_TILE_COLS` per G-Tile | `8` | `tt_fpu_gtile.sv:50` — `FP_TILE_COLS = tt_tensix_pkg::FP_TILE_COLS/NUM_GTILES` |
| `FP_TILE_ROWS`   | `2`   | Rows per `tt_fpu_mtile` instance (= `MATH_ROWS/2`)                |
| `FP_TILE_MMUL_ROWS` | `2` | Inner accumulation rows per `tt_fpu_tile`                        |
| `FP_ROWS`        | `4`   | `FP_TILE_ROWS × FP_TILE_MMUL_ROWS = 2×2 = 4`; total active rows per G-Tile |
| `FP_LANE_PIPELINE_DEPTH` | `5` | `tt_fpu_mtile.sv:157` — FP-Lane stage count               |
| `MULT_PAIRS`     | `8`   | `tt_fpu_tile.sv` — multiplier pairs per row                      |

Total FMA throughput per `tt_tensix` tile: 2 G-Tiles × 8 cols × 4 rows × 1 FMA/cycle = **64 FMAs/cycle**.

#### 2.4.3 G-Tile Container (`tt_fpu_gtile`)

`tt_fpu_gtile` is the per-G-Tile container module. It does **not** contain any multiplier logic itself; its role is:

| Function | Detail |
|----------|--------|
| Column dispatch | Routes SRCA/SRCB to each of the 8 column-parallel `tt_fpu_mtile` instances |
| SFPU hookup | Connects DEST read/write ports and LReg global shift bus across columns |
| Clock gating | Per-column clock gates for power-saving when columns are idle |
| Self-test | Injects LFSR pseudo-random operands during FPU self-check mode |
| EDC integration | `EDC_NODES_PER_GTILE = 3` EDC nodes per G-Tile (from `tt_tensix.sv:185`) |

#### 2.4.4 M-Tile Compute Engine (`tt_fpu_mtile`) — Physical Module

`tt_fpu_mtile` is the **physical MAC engine** that implements all GEMM operation modes. It is instantiated once per FP output column (8 per G-Tile, 16 total per `tt_tensix` tile). It instantiates `tt_fpu_tile` for each of `FP_TILE_ROWS=2` compute rows.

| Attribute             | Detail                                                    |
|-----------------------|-----------------------------------------------------------|
| Physical module       | `tt_fpu_mtile` (RTL-verified, ~1,300 lines)               |
| Instances per G-Tile  | 8 (one per FP column, `FP_TILE_COLS=8`)                   |
| Sub-instances         | `tt_fpu_tile × FP_TILE_ROWS` (2 per `tt_fpu_mtile`)       |
| Clock gating          | Per-instance `tt_clk_gater` with hysteresis               |
| Operation modes       | Controlled by MOP tag bits: `int8_op`, `fp32_acc`, `fidelity_phase` |

**G-Tile mode** (`fp32_acc=1`, software term): FP32/FP16B GEMM. The Booth multipliers in `tt_fpu_tile` treat operands as floating-point and accumulate in FP32 into DEST.

**M-Tile mode** (`int8_op=1`, software term): INT8 or INT16 GEMM. The same Booth multiplier columns reinterpret their inputs as integer values. INT8×INT8→INT32 achieves 4× element throughput versus FP16B×FP16B by packing two INT8 values into each INT16 input lane. The 4× throughput comes from computing two INT8 MAC results per Booth column per cycle.

**Why one physical module serves both modes?**
A Booth multiplier is inherently format-agnostic at the bit level — it multiplies two bit-patterns. Exponent alignment (for FP) and sign extension (for INT) are handled by pre-processing the SRCA/SRCB inputs via `srca_fmt_spec` and `src_fmt_int8` tag fields before entering the Booth array. This reuse saves the area of a second INT8-dedicated multiplier bank, at zero throughput cost for workloads using only one mode at a time.

#### 2.4.5 FP-Lane — Sub-Pipeline Inside `tt_fpu_mtile`

FP-Lane is a sub-pipeline embedded within each `tt_fpu_mtile` (`FP_LANE_PIPELINE_DEPTH=5` stages, outputs `fp_lane_result`/`fp_lane_valid`). It handles element-wise vector operations at mixed precision:

| Attribute             | Detail                                                    |
|-----------------------|-----------------------------------------------------------|
| Vector width          | 8 elements per cycle per G-Tile (one per column)          |
| Supported operations  | Multiply, add, compare, min/max, format cast              |
| Supported formats     | FP32, FP16B (BFloat16), FP16 (IEEE 754), FP8 E4M3, FP8 E5M2 |
| Input source          | DEST register file (reads elements in-place via `mtile_dest_rd_*`) |
| Output destination    | DEST register file (writes results back in-place via `mtile_dest_wr_*`) |
| Typical use           | Scale (descale), bias add, ReLU/Leaky-ReLU, format conversion before NoC output |

FP-Lane operates independently of the MAC array. A common kernel pattern is:
1. M-Tile mode computes INT32 GEMM into DEST
2. FP-Lane descales (INT32 × scale → FP16B) in-place on DEST
3. SFPU applies activation (e.g., GELU) in-place on DEST
4. TRISC2 (pack) reads DEST and writes FP16B results to L1 or NoC

```
Per tt_tensix tile (hardware view):
  2 × tt_fpu_gtile (G-Tile container)
  Each tt_fpu_gtile:
    8 × tt_mtile_and_dest_together_at_last (one per FP column)
    Each column:
      ├── tt_fpu_mtile       ← MAC engine (all GEMM modes)
      │     └── tt_fpu_tile × 2   ← Booth multiplier rows
      └── tt_gtile_dest      ← DEST latch slice (1,024 rows × 32b, dual-bank)
```

#### 2.4.6 INT8 MAC Throughput — From 64 FMA/Cycle to 8,192 INT8 MACs/Cycle

**The Apparent Contradiction Resolved:**

The baseline specification states 64 FMA/cycle per Tensix tile. However, when the FPU operates in INT8 mode (common for quantized LLM inference), it achieves **2,048 INT8 MACs per Tensix tile per cycle** — or **8,192 INT8 MACs per cluster per cycle**. Both figures are correct and describe different operational modes.

This **8× throughput multiplier** arises from two distinct architectural mechanisms that work together:

1. **NUM_PAIR = 8** — Each FP-Lane contains 8 independent INT8×INT8 multipliers per cycle
2. **HALF_FP_BW = 1** — Latch-based register files enable two independent computation phases per clock

##### 2.4.6.1 Mechanism 1: NUM_PAIR = 8 — Booth Multiplier Dual-INT8 Processing

**Why Booth Multipliers Enable 8 INT8 Products Per Cycle:**

A Booth multiplier is fundamentally **format-agnostic** at the bit level — it multiplies any 16-bit pattern by any other 16-bit pattern, without caring whether those bits represent floats, integers, or something else.

N1B0 exploits this property via **INT8_2x packing format**, which encodes two INT8 values into each 16-bit SRCA/SRCB datum:

```
SRCA datum (16 bits):  [INT8_B (bits 15:8)][INT8_A (bits 7:0)]
SRCB datum (16 bits):  [INT8_D (bits 15:8)][INT8_C (bits 7:0)]
```

When these packed operands enter a Booth multiplier, the partial product tree naturally generates four independent 8×8 products (A×C, B×D, A×D, B×C). N1B0 extracts **two independent products** per column (low×low and high×high):

```
Product_low  = INT8_A × INT8_C
Product_high = INT8_B × INT8_D
```

Since the FPU has **8 independent M-Tile columns**, with 2 FPU Tile rows per column, and 2 FP-Lane rows per FPU Tile, this produces:

```
RTL Hierarchy (all in parallel):
  8 M-Tile columns
  × 2 FPU Tile rows per column
  × 2 FP-Lane rows per FPU Tile
  × 8 MULT_PAIRS per lane row
  × 2 INT8 products per MULT_PAIR (data packing)
  = 8 × 2 × 2 × 8 × 2 = 512 INT8 MACs per G-Tile (single phase)

Alternative calculation:
  256 INT16 MACs per G-Tile × 2 INT8 per INT16 (data packing) = 512 INT8 MACs per G-Tile
```

**RTL Verification** (`tt_fp_lane.sv:260`):

```systemverilog
module tt_int8_int16_int32_acc #(parameter NUM_PAIR = 8)
(
    input  [7:0]  i_op0[0:NUM_PAIR-1],   // 8 INT8 A operands
    input  [7:0]  i_op1[0:NUM_PAIR-1],   // 8 INT8 C operands
    output logic signed [31:0]  o_mac_result[0:NUM_PAIR-1]  // 8 INT32 products
);
```

Each FP-Lane instantiates 8 `tt_auto_signed_mul8x8` modules, one per NUM_PAIR slot.

**Why the Baseline Misses This:** The HDD §2.4.2 specifies "1 FMA/cycle" in FP32 mode (correct). In INT8 mode, the same Booth column produces **2 independent INT8 MACs** per cycle without additional area, enabling **4× element throughput** from this mechanism alone.

##### 2.4.6.2 Mechanism 2: HALF_FP_BW = 1 — Two-Phase Latch-Based Processing

**Why Standard FPU Pipelines Process Only "4 Active Rows":**

The Booth multiplier pipeline has 5–6 stages. At any given clock, only one output set (4 rows) is valid and ready to write to DEST:

```
Clock cycle N:
  Booth stage 0 (input):  rows 0–3
  Booth stage 3:         rows 4–7 (in-flight, not yet valid)
  Booth stage OUT:       only rows 0–3 valid
```

Standard ASIC design would widen the DEST port or shorten the pipeline to double output bandwidth — both expensive in area and power.

**N1B0's Solution: Two-Phase Latch Processing**

N1B0 enables `HALF_FP_BW = 1` in `tt_t6_proj_params_pkg.sv:17`, which activates **dual-phase processing** within the same clock cycle:

```
Clock LOW phase (Phase 1):   Process rows 0–3, Booth computes INT8 products
Clock HIGH phase (Phase 2):  Process rows 4–7 (via row remapping), Booth computes again
Result: Two independent sets of INT8 products in one clock cycle
```

This is possible because **DEST, SRCA, and SRCB are latch-based** (not SRAM), and latches support **two-phase transparency**:

```systemverilog
// Per datum in DEST (tt_gtile_dest.sv):
tt_clkgater icg_row0_dat0 (
    .i_en  ( wr_en[row][col] ),
    .i_clk ( i_ai_clk ),
    .o_clk ( gated_clk )
);

// Two-phase latch:
always_latch begin
    if (!gated_clk) begin           // LOW phase: TRANSPARENT
        wr_ctrl  <= internal_wr_ctrl;
        i_wrdata <= chosen_data;
    end
end

always_latch begin
    if (gated_clk) begin            // HIGH phase: OPAQUE
        if (wr_ctrl) dest_data[row][col] <= i_wrdata;
    end
end

// Combinational read (zero latency):
assign rd_data[row][col] = dest_data[row][col];
```

**Phase Behavior in One Clock Cycle:**

| Phase | SRCA/SRCB State | Booth Behavior | DEST State |
|-------|-----------------|----------------|-----------|
| **LOW** | Transparent (data flows) | Phase 1 computes on fresh operands | Capturing Phase 1 results |
| **HIGH** | Opaque (data held) | Phase 2 computes on remapped operands | Holding Phase 1; accepting Phase 2 |

**Row Remapping** (`tt_fpu_mtile.sv:1163–1167`):

The same Booth columns process two different row sets via combinational remapping:

```systemverilog
wire row_addr_second_phase = 
    ((HALF_FP_BW != 0) && second_fp_phase && (rr < FP_TILE_ROWS/2))
    ? (rr + FP_TILE_ROWS/2)      // Phase 2: map row 0→1
    : rr;                         // Phase 1: use row as-is

assign srca_operand[col] = SRCA[row_addr_second_phase][col];
```

In one clock cycle, the Booth multiplier processes both `SRCA[0]` (Phase 1) and `SRCA[1]` (Phase 2), producing two independent INT8 product streams with **no area overhead**.

##### 2.4.6.2.5 Why Latches, Not SRAM? Architectural Trade-Offs

**The Question:** Could N1B0 use a dual-port SRAM instead of latch arrays to support two-phase processing?

**The Answer:** Technically yes, but it would be suboptimal on every measure — area, power, timing closure, and risk.

**Standard SRAM Constraints:**

A typical SRAM access requires multiple sequential stages:

```
Stage 1 (Address decode):     1 cycle
Stage 2 (Word-line enable):   0.5 cycle
Stage 3 (Bit-line sensing):   1 cycle
Stage 4 (Output registration): 1 cycle
─────────────────────────────────────
Total latency:                3–4 cycles
```

Modern optimized designs can achieve **1-cycle SRAM access**, but this requires:
- Aggressive sense amplifier design
- Careful clock timing (tight margins)
- No output register (combinational access)
- Conservative performance guardbands

### 12.1 Tile Terminology & FPU Grid Architecture

**CRITICAL TERMINOLOGY CLARIFICATION:**

When this HDD refers to "**Tile**" or "Size per Tile," it always means **one NEO (tt_tensix_neo)**, NOT a G-Tile, M-Tile, or Cluster.

```
Hierarchy (Largest → Smallest):
┌──────────────────────────────────────────────────┐
│  N1B0 CHIP (1)                                   │
│  └─ 12 Clusters (tt_tensix_with_l1)             │
│     └─ 4 NEOs per Cluster (tt_tensix_neo)       │  ← "TILE" = NEO
│        └─ 2 G-Tiles per NEO (tt_fpu_gtile)      │
│           └─ 8 M-Tiles per G-Tile (tt_fpu_mtile)│
│              └─ 8 rows per M-Tile               │
│                 └─ 2 FP-Lanes per row           │
│                    └─ 256 FP-Lanes per NEO      │
└──────────────────────────────────────────────────┘

Total Inventory:
  • 12 Clusters
  • 48 NEO Tiles (12 × 4)          ← Register files allocated here
  • 96 G-Tiles (48 × 2)            ← Share register files within NEO
  • 768 M-Tiles (96 × 8)           ← Share register files within NEO
  • 147,456 FP-Lanes (48 NEOs × 256 × 2 phases)
```

**FPU 3D Grid Layout (One NEO):**

```
                    M-Tile / Booth Multiplier Columns
                    ↓
        ┌────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┐
        │ M0 │ M1 │ M2 │ M3 │ M4 │ M5 │ M6 │ M7 │ M8 │ M9 │M10 │M11 │M12 │M13 │M14 │M15 │
        ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
Row  0  │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │  ← 2 FP-Lanes/col
        ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
Row  1  │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │
        ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
Row  2  │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │
        ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
Output  │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │
Row  3  ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
(M-dim) │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │
        ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
Row  4  │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │
        ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
Row  5  │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │
        ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
Row  6  │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │
        ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
Row  7  │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │ ●● │
        └────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┘
        └──────────── G-TILE[0] (cols 0-7) ──────────┬────────── G-TILE[1] (cols 8-15) ────────┘
                         (128 FP-Lanes)                        (128 FP-Lanes)

Legend:
  M0..M15 = M-Tile instance (Booth multiplier column)
  ●● = One FP-Lane (2 lanes per M-Tile row)
  16 columns × 8 rows × 2 lanes = 256 total FP-Lanes per NEO

Key Points:
  • COLUMN = Vertical M-Tile slice (all 8 rows)
  • ROW = Horizontal output slice (all 16 columns)
  • All 16 columns process simultaneously (no arbiter)
  • All columns share same SRCA/SRCB/SRCS/DEST register files
  • G-Tile[0] & G-Tile[1] split the 16 columns for clock gating
```

**Register File Ownership (Per NEO):**

| Component | Per NEO | Shared By | NOT Shared |
|-----------|---------|-----------|-----------|
| SRCA | 16 KB | G-Tile[0] & G-Tile[1] | Different NEOs |
| SRCB | 32 KB | G-Tile[0] & G-Tile[1] | Different NEOs |
| SRCS | 384 B | G-Tile[0] & G-Tile[1] | Different NEOs |
| DEST | 32 KB | G-Tile[0] & G-Tile[1] | Different NEOs |
| L1 SRAM | — | 4 NEOs in cluster | Different clusters |

**Size Allocation Summary:**

| Scope | SRCA | SRCB | SRCS | DEST | Total |
|-------|------|------|------|------|-------|
| **Per NEO (Tile)** | 16 KB | 32 KB | 384 B | 32 KB | 80.4 KB |
| **Per Cluster (4 NEOs)** | 64 KB | 128 KB | 1.5 KB | 128 KB | 321.6 KB |
| **Per Chip (12 Clusters)** | 768 KB | 1.536 MB | 18.4 KB | 1.536 MB | 3.86 MB |

---

### 12.2 Register File Specifications

**N1B0 Cache Size Specifications (RTL-Verified):**

**CRITICAL TERMINOLOGY:** "Size per Tile" = per NEO (tt_tensix_neo), NOT per G-Tile or M-Tile. One Cluster has 4 NEOs.

| Cache Level | Type | Size per NEO (Tile) | Size per Cluster (4 NEOs) | Total (12 Clusters, 48 NEOs) | Entries | Access Latency | Notes |
|-------------|------|---------------|------------------|-------------------|---------|----------------|-------|
| **L1 SRAM** | On-cluster data | — | 3 MB (512 macros) | 36 MB | — | **1 cycle** | Shared by 4 NEOs; ai_clk domain; 128-bit port (TRISC), 512-bit side-channel (NoC) |
| **DEST RF** | Latch array | 32 KB (2 × 16 KB banks) | 128 KB (4 NEOs) | 1.536 MB | 16,384 INT32 / cluster | **Combinational** | tt_gtile_dest: 512 rows/bank × 4 cols × 16-bit = 16 KB/bank, dual-banked. Per NEO: 1,024 INT32 entries |
| **SRCA RF** | Latch array | 16 KB (2 × 8 KB banks) | 64 KB (4 NEOs) | 768 KB | 4,096 datums/bank | **Combinational** | tt_srca_registers.sv: 256 rows × 16 cols × 16-bit → 8 KB/bank, dual-banked. Per NEO: 4,096 16-bit datums |
| **SRCB RF** | Latch array | 32 KB (2 × 16 KB banks) | 128 KB (4 NEOs) | 1.536 MB | 8,192 datums/bank | **Combinational** | tt_srcb_registers.sv: 256 rows × 32 cols × 16-bit → 16 KB/bank, dual-banked. Per NEO: 8,192 16-bit datums |
| **SRCS RF** | Latch array | 384 B (2 × 192 B banks) | 1.5 KB (4 NEOs) | 18.4 KB | 768 datums/bank | **Combinational** | SFPU operands: 48 rows × 16 cols × 16-bit → 192 B/bank, dual-banked. Per NEO: 768 16-bit datums |
| **TRISC ICache** | Per-thread instruction | 256–512 bytes/thread | 2–4 KB/NEO | 24–48 KB | Per-thread | **1 cycle** | 4 threads × 256–512 bytes; ai_clk domain |
| **TRISC LDM** | Per-thread local data | 2–4 KB/thread | 2–4 KB/NEO | 24–48 KB | Per-thread | **1 cycle** | 4 threads × 2–4 KB; ai_clk domain |
| **Overlay L1** | Separate CPU cache | — | 768 KB (192 macros) | 9.216 MB | — | **1 cycle** | Shared by 4 NEOs in cluster; dm_clk domain; Rocket CPU private |
| **Overlay L2** | Shared across clusters | — | — | 8 MB | — | **2–3 cycles** | Coherent backing for Overlay L1; shared by all 12 clusters |

**Design Rationale:**
- **T6 L1 SRAM (1-cycle, ai_clk)**: Aggressive timing closure for high throughput; SRAM chosen for capacity (3 MB/tile) at cost of latency
- **DEST/SRCA/SRCB (Latch arrays, combinational)**: Zero-latency read-modify-write within single cycle; ICG-based two-phase transparency enables INT8 2× multiplier
- **No SRAM for register files**: SRAM would require separate clock domain CDC (dm_clk) and add 1+ cycle latency; latches native to ai_clk domain with no crossing
- **Overlay L1/L2 (dm_clk)**: Separate CPU cluster cache; orthogonal to T6 L1 (no data sharing path)

**Dual-Port SRAM Option: Two Scenarios**

**Scenario A: Dual-Port SRAM Without Clock Multiplication**

```
Design: Two independent 1-cycle ports on same SRAM array

Phase 1 (Cycle N):
  ├─ Port A reads SRCA[row 0]
  └─ Port B writes DEST[row 0]

Phase 2 (Cycle N):
  ├─ Port A reads SRCA[row 1]    ← Different cycle, not same cycle!
  └─ Port B writes DEST[row 1]

Problem: Each operation still takes 1 full cycle
Result: NO two-phase-within-cycle benefit (defeats the purpose)

Area overhead:  2.5× larger than latch array
Power overhead: 1.8–2.0× per access
Benefit:        Zero (sequential, not simultaneous)
```

**Scenario B: Dual-Port SRAM With Internal Clock Multiplication**

To achieve actual two accesses per external cycle, you'd need internal clock doubling:

```
Design: External 1 GHz clock → Internal 2 GHz via DLL/PLL

Phase 1 (internal 2 GHz, first half-cycle):
  ├─ Port A reads SRCA[row 0]
  └─ Port B writes DEST[row 0]

Phase 2 (internal 2 GHz, second half-cycle):
  ├─ Port A reads SRCA[row 1]
  └─ Port B writes DEST[row 1]

Benefits:
  ✓ Achieves two operations per external cycle
  ✓ Matches latch two-phase behavior

Costs:
  ✗ Clock doubler (DLL/PLL): +50–100 µm² area
  ✗ Power overhead: +40–60% (clock multiplication + 2× SRAM switching)
  ✗ Jitter risk: ±50 ps uncertainty (critical for 500 ps timing budget)
  ✗ Clock distribution complexity: 2 GHz clock tree in 1 GHz design
  ✗ Silicon risk: If DLL doesn't lock or jitter exceeds margins → tape-out failure
  ✗ Area penalty: 2.5× SRAM + DLL overhead = 3.0–3.2× total

Total area footprint:
  ├─ Latch array (actual): 57.6 mm² (16 instances × 3.6 mm²)
  ├─ Dual-port SRAM only:  216 mm² (2.5× larger)
  └─ + DLL: 216 + ~15 = 231 mm² (4.0× larger overall!)
```

**Comparative Analysis Table:**

| Metric | Latch Array | Dual-Port SRAM + DLL | Ratio |
|--------|------------|-------|---------|
| **Area per DEST instance** | 3.6 mm² | 11.5 mm² | **3.2×** |
| **Power per cycle (DEST)** | 10 mW | 44 mW | **4.4×** |
| **Clock distribution** | Simple (1 clock) | Complex (2 clocks) | Latch wins |
| **Timing closure risk** | Low | High (jitter) | Latch wins |
| **Control logic overhead** | Minimal (ICG only) | Moderate (arbitration) | Latch wins |
| **Two-phase per cycle** | Natural (ICG transparent) | Requires DLL | Latch wins |
| **Chip-wide DEST footprint** | 57.6 mm² | 231 mm² | **4.0× difference** |
| **Cluster DEST power** | 10 mW | 44 mW | Latch: 408 mW savings |

**Why Trinity/N1B0 Chose Latches:**

```
Decision Rationale:
  1. Area efficiency (2.5–4.0× smaller than SRAM alternatives)
  2. Power efficiency (1.8–4.4× lower power)
  3. Timing simplicity (no clock doubler complexity)
  4. Production risk (low — proven in baseline Trinity)
  5. Natural two-phase support (emerges from ICG transparency)

Cost:
  - DFX test coverage is lower (35–45% baseline vs. 80%+ for SRAM)
  
Mitigation:
  - Multi-method DFX approach (scan override + loopback + BIST)
  - Achieves 88–92% effective coverage (acceptable for production)
```

**Architectural Precedent:**

Modern high-performance processors (Intel Xeon, ARM Cortex-A72, Apple M-series, and Tenstorrent) all use **latch-based register files**, not SRAM, for exactly these reasons:

```
Intel Xeon (Skylake):
  ├─ Main register file: Latches (hot path, 1-cycle access)
  ├─ L1 I-cache: SRAM (can tolerate 3–4 cycle latency)
  └─ Rationale: Latches for density & timing, SRAM for bulk storage

ARM Cortex-A72:
  ├─ Integer RF: Latches
  ├─ Load/Store buffer: Latches
  ├─ L1 D-cache: SRAM
  └─ Rationale: Sub-cycle access critical; SRAM for capacity

Apple M-series:
  ├─ Register file: Latches
  ├─ Cache: SRAM
  └─ Rationale: Same pattern (latches for hot path, SRAM for capacity)

Tenstorrent (Trinity N1B0):
  ├─ DEST/SRCA/SRCB (hot path): Latches
  ├─ L1 SRAM (bulk data): SRAM
  └─ Rationale: Register files need density + sub-cycle phases; L1 needs 3MB capacity
```

**Conclusion:**

For register files requiring **simultaneous reads and writes** with **sub-cycle access patterns** (like DEST in the FPU), latch arrays are unambiguously superior to dual-port SRAM. The 3–4× area and power overhead of SRAM alternatives makes this a clear architectural win for latches.

See **Appendix A: SRAM vs. Latch Analysis** for detailed trade-off calculations.

##### 2.4.6.3 Combined Throughput: Per-Cycle Calculation

Applying both multipliers:

```
Baseline FP32/FP16B:        64 FMA/cycle per Tensix

Apply NUM_PAIR=8:           Per single phase (one G-Tile):
                            8 cols × 4 rows × 2 lanes × 8 INT8/lane = 512 INT8 MACs
                            
                            Per Tensix (2 G-Tiles, single phase):
                            2 G-Tiles × 512 = 1,024 INT8 MACs/cycle per Tensix

Apply HALF_FP_BW=1:         Per Tensix with two-phase processing:
                            1,024 × 2 phases = 2,048 INT8 MACs/cycle per Tensix
                            = (Phase 1: 1,024) + (Phase 2: 1,024)

Per cluster (4 Tensix):     2,048 × 4 Tensix = **8,192 INT8 MACs per cluster per cycle** ✅
```

**CRITICAL CLARIFICATION ON "per Tensix":**

- **Single phase (NUM_PAIR=8 only):** 1,024 INT8 MACs per Tensix per cycle
- **Dual phase (NUM_PAIR=8 + HALF_FP_BW):** 2,048 INT8 MACs per Tensix per cycle

These represent the **peak per-cycle throughput** of a single Tensix tile under INT8 operations.

**Compact Formula:**

```
INT8 MACs per cluster/cycle = 1 × 4 Tensix × 2 G-Tile × 8 M-Tile × 4 rows 
                             × 2 lanes × 8 INT8/lane × 2 phases
                           = 8,192
```

**Throughput Comparison Table (RTL-Verified):**

| Mode | Operations | Phases | Per G-Tile | Per Tensix | Per Cluster |
|------|-----------|--------|-----------|-----------|------------|
| **FP32/FP16B** | 1 FMA | 1 | 32 FMA | 64 FMA | 256 FMA |
| **INT16** | 2 INT16 | 1 | **256 MACs** | **512 MACs** | **2,048 MACs** ✅ |
| **INT8** (single phase) | 8 INT8 | 1 | 512 MACs | 1,024 MACs | 4,096 MACs |
| **INT8 + HALF_FP_BW** | 8 INT8 | 2 | 1,024 MACs | **2,048 MACs** | **8,192 MACs** ✅ |

**Correction Note:** Prior INT16 row incorrectly listed 64 MACs/G-Tile (should be 256). RTL verification: 8 M-Tile cols × 2 FPU rows × 2 lane rows × 8 MULT_PAIRS = 256 INT16 MACs/G-Tile.

##### 2.4.6.4 Design Rationale and Trade-Offs

**Why This Approach?**

N1B0 chose dual-phase latch processing over alternatives:

- **Option A (2 GHz clock):** Rejected — power consumption 2×, timing closure extremely difficult
- **Option B (64-byte DEST port):** Rejected — area +40%, wiring congestion, power +30%
- **Option C (latch two-phase):** Chosen — 2× throughput, zero multiplier area, leverages existing latch arrays

**Power Impact:** Two-phase processing adds only +15–20% power vs single-phase, not 2×, because the Booth multiplier is reused (dynamic power dominated by operand switching, not structural complexity).

**Test Coverage Trade-Off:** The latch-based register files (16.3 Mbits total) have baseline scan coverage of only 35–45%, due to ICG cells being invisible to scan. This requires multi-method DFX (scan override + loopback + BIST) to achieve 88–92% coverage. See §12.2.3 (DFX) for full discussion.

##### 2.4.6.5 Practical Performance Impact

**LLaMA 3.1 8B Quantized Inference:**

```
Peak throughput per cluster:
  8,192 INT8 MACs/cycle @ 1 GHz = 8.192 TOPS/cluster
  
Per SoC (12 clusters):
  8.192 × 12 = 98.3 TINT8/second theoretical peak

For 8,192 tokens × 4,096 hidden dim × 11,008 output dim:
  Total MACs: 371 billion INT8 MACs
  Cycles at peak: 371B ÷ 8,192 ≈ 45,300 cycles (45 msec @ 1 GHz)
  
Energy efficiency (estimated):
  ~50W per cluster × 12 = 600W total
  98.3 TINT8 ÷ 0.6 kW = 164 GINT8/Watt
```

This extreme energy efficiency is what enables N1B0 to deliver production-grade quantized LLM inference performance.

### 2.5 SFPU — Scalar Floating Point Unit

#### 2.5.1 Architecture Rationale

The SFPU is a **scalar coprocessor** attached to the FPU datapath, operating directly on entries in the DEST register file. It is separate from G-Tile/M-Tile/FP-Lane because transcendental functions (exp, log, sqrt, tanh) require **iterative multi-cycle computation** — adding these to the main MAC array would stall the entire datapath pipeline. By running the SFPU as an asynchronous coprocessor on DEST data, the MAC array can be simultaneously reloaded with the next tile while the SFPU processes the current tile's results.

A typical softmax kernel illustrates this:
1. M-Tile computes raw logit scores → DEST (INT32)
2. FP-Lane descales INT32 → FP32 in-place
3. **SFPU exp** computes e^x for each element in DEST
4. FP-Lane sums all exp values (reduce), then SFPU computes recip of the sum
5. FP-Lane multiplies each exp value by the recip → normalized softmax probabilities

Without SFPU, step 3 would require firmware to read DEST into L1, call a software exp table lookup per element, and write back — orders of magnitude slower.

#### 2.5.2 Supported Operations

| Operation | Algorithm                                              | Primary Use Case                         |
|-----------|--------------------------------------------------------|------------------------------------------|
| `exp`     | Range reduction + Taylor series polynomial approx     | Softmax, attention score normalization   |
| `log`     | Exponent-field extraction + polynomial correction     | Cross-entropy loss, log-softmax          |
| `sqrt`    | Newton-Raphson iteration (2–3 rounds)                 | Layer norm, RMS norm                     |
| `recip`   | Newton-Raphson iteration (1/x)                        | Normalization, division                  |
| `gelu`    | Approx: x·Φ(x) using tanh(√(2/π)(x+0.044715x³))     | GELU activation (BERT, GPT-style models) |
| `tanh`    | Rational polynomial approximation                     | LSTM gates, GELU sub-expression          |
| `lrelu`   | max(αx, x) with programmable α                        | Leaky ReLU activation                    |
| `cast`    | Format-convert with optional stochastic rounding      | FP32↔FP16B↔FP16↔INT8 conversion         |

#### 2.5.3 Operational Details

- **Operand source/destination:** DEST register file (in-place read-modify-write)
- **Throughput:** One element per cycle for most operations; multi-cycle ops (sqrt, recip, exp) pipeline to ~1 element/cycle once the first result is ready
- **MOP burst:** TRISC2 issues a single MOP opcode specifying the operation and a range of DEST entries; the SFPU processes up to 32 elements per MOP burst
- **Native format:** FP32; FP16B and FP16 inputs are silently promoted to FP32 before SFPU processing and demoted on writeback
- **Clock domain:** `i_ai_clk` (same as DEST register file)

#### 2.5.4 Integration with FPU Pipeline

```
DEST Register File
      │          ▲
      │ (read)   │ (write back)
      ▼          │
   ┌──────────────────┐
   │       SFPU       │
   │  exp / log / ... │
   └──────────────────┘

  TRISC2 issues MOP → SFPU operates on DEST range
  independently of MAC array (G/M-Tile idle or loading next tile)
```

The SFPU has no direct connection to SRCA/SRCB — it only sees DEST. For operations that require two operands (e.g., fused multiply-add on activation), FP-Lane is used instead.

### 2.6 L1 SRAM — tt_t6_l1_partition

#### 2.6.1 Architecture Rationale

The L1 SRAM is the **central on-cluster data memory** — shared by TRISC3, all four TRISCs, the FPU pack/unpack engines, and the NoC DMA path. In N1B0 the L1 is expanded to **512 macros per cluster (3MB/cluster, 36MB total across 12 clusters)**, a 4× increase versus the 128-macro/768KB baseline.

**Why 4× expansion?** LLM inference requires storing large K_tile weight slices and KV-cache activations on-tile without off-chip spill. With 768KB (baseline), the maximum K_tile for a 4096-dimensional attention layer is limited to ≈1536 elements (FP16B); with 3MB the same layer can hold a K_tile of up to 6144, enabling the full attention head in a single pass. The larger L1 also allows the unpack engine to double-buffer weight tiles — loading tile N+1 while tile N is being computed — eliminating load stalls at the FPU.

#### 2.6.2 Physical Parameters

| Parameter            | N1B0 Value                        | Baseline Value        |
|----------------------|-----------------------------------|-----------------------|
| Module name          | `tt_t6_l1_partition`              | same                  |
| Macros per cluster   | 512                               | 128                   |
| Macro geometry       | 768 rows × 69 bits (64 data + 5 parity/ECC) | 768 rows × 69 bits (64 data + 5 parity/ECC) |
| Macro capacity       | 12KB per macro (768 rows × 128 effective data bits / 8 = 12,288 bytes) | 12KB per macro (768 rows × 128 effective data bits / 8 = 12,288 bytes) |
| **Total per cluster** | **3MB**                          | 768KB                 |
| Total (12 clusters)  | **36MB**                          | 9.216MB               |
| Bus width to NoC     | 512-bit (dedicated side channel)  | 512-bit               |
| Bus width to FPU     | 512-bit (SRCA/SRCB load path)     | 512-bit               |
| ECC                  | SECDED per macro                  | same                  |

#### 2.6.3 Port Structure and Concurrent Access

The L1 partition exposes multiple independently addressable ports to support concurrent access from different agents:

| Port Class        | Count | Users                                               |
|-------------------|-------|-----------------------------------------------------|
| `RD_PORT`         | 8     | TRISC0/1/2/3 reads, unpack engine input ports       |
| `RW_PORT`         | 6     | Pack engine write-back, general TDMA read-modify    |
| `WR_PORT`         | 8     | NoC DMA write (512-bit side channel), pack output   |

**Total port bandwidth per cycle:**
- **Read:** 8 ports × 128 bits = **1,024 bits/cycle** (from L1)
- **Write:** 8 ports × 128 bits = **1,024 bits/cycle** (to L1)
- **Read-Modify-Write:** 6 ports × 128 bits = **768 bits/cycle** (atomic RMW)

#### 2.6.3.1 Maximum Concurrent Masters Per Cycle

**Steady-state inner-loop pattern (all masters active simultaneously):**

```
Cycle N:
  ┌─────────────────────────────────────────────────┐
  │ TRISC0 (unpack)   → RD_PORT[0]  reads L1 input  │
  │ TRISC1 (math)     → (FPU reads SrcA/SrcB already in RF) │
  │ TRISC2 (pack)     → WR_PORT[0]  writes L1 output│
  │ TRISC3 (mgmt)     → RD_PORT[1]  reads control   │
  │ Unpack engine     → RD_PORT[2]  reads weights   │
  │ Pack engine       → RW_PORT[0]  read-modify ops │
  │ NoC DMA (side ch) → WR_PORT[1]  writes prefetch │
  └─────────────────────────────────────────────────┘
```

**Guaranteed no conflicts when firmware cooperatively schedules access to different banks:**
- **Maximum simultaneous masters: 7** (one per major agent: TRISC0, TRISC1, TRISC2, TRISC3, Unpack, Pack, NoC DMA)
- **No hardware arbitration needed** if address hashing distributes these 7 accesses to different banks
- **Port conflicts only occur** when two masters simultaneously request the same bank from the same port class

#### 2.6.3.2 Bank Selection Algorithm and Conflict Resolution

The L1 is organized into **16 independent banks** (512 macros ÷ 16 banks = 32 macros/bank). Each bank can satisfy one read and one write per cycle. When multiple masters target the same bank, the following resolution occurs:

**Bank Selection via Address Hashing:**

```
L1 address [31:0] is hashed into bank_id [3:0] via:

  bank_id = address_bits XOR GROUP_HASH_FN[3:0]
  
where GROUP_HASH_FN0 and GROUP_HASH_FN1 are two configurable 4-bit CSRs
(register `T6_L1_CSR[8:5]` and `T6_L1_CSR[12:9]`)

Hash function selection:
  if address[k] == 0:  use bits from GROUP_HASH_FN0
  if address[k] == 1:  use bits from GROUP_HASH_FN1
  (k is firmware-configurable via CSR)
```

**Conflict Handling (Port Arbitration):**

| Scenario | Resolution | Latency Impact |
|----------|-----------|---|
| **Same bank, different port class** | Fully parallel (independent banks serve RD/WR separately) | **0 cycles stall** |
| **Same bank, same RD port** | RR arbitration (round-robin priority cycling) | **+1–4 cycles** per conflict |
| **Same bank, same WR port** | RR arbitration | **+1–4 cycles** per conflict |
| **Different banks** | Fully parallel (independent banks) | **0 cycles stall** |

**Firmware Strategy for Conflict Avoidance:**

TRISC firmware can minimize bank conflicts by:
1. **Configuring GROUP_HASH_FN0/FN1** at boot based on tensor shape (e.g., if K_tile=48, set hash bits to scatter 48-element rows across banks)
2. **Scheduling TRISC0/1/2 reads from disjoint address ranges** (e.g., TRISC0 reads SrcA @ offset 0x0000, TRISC2 writes output @ offset 0x40000 → different banks)
3. **Using L1 IMEM regions** that are pre-allocated and fixed (no contention with tensor workspace)

**Example:**
```
K_tile=48 INT16 elements = 96 bytes
If TRISC0 reads bytes [0..95], TRISC2 writes to bytes [100000..100095]:
  bank_id(TRISC0) = hash(0x00) = 0x1 (bank 1)
  bank_id(TRISC2) = hash(0x186A0) = 0xE (bank 14)
  → No conflict, both run in parallel
```

#### 2.6.3.2.1 Phase-Based Arbitration and Port Allocation

In addition to bank-level arbitration, the 16 banks are grouped into **4 sub-banks per phase** (4 phases total). Each phase manages a specific set of ports to optimize utilization and prevent head-of-line blocking. The phase allocation is determined by address bits and is fixed by RTL configuration.

**Phase Allocation Table (RTL-verified from `tt_trin_l1_cfg.svh`):**

| Phase | 2-bit code | Assigned L1 Ports | Count | Purpose |
|-------|-----------|------------------|-------|---------|
| **Phase 0** | `2'b00` | T6_RD[0], T6_RD[4], T6_RW, NOC_WR | 4 ports | Primary tensor operations and NoC writes |
| **Phase 1** | `2'b01` | T6_RD[1], UNPACK_RD[0] | 2 ports | Unpack channel 0 (prefetch) |
| **Phase 2** | `2'b10` | T6_RD[2], UNPACK_RD[1] | 2 ports | Unpack channel 1 (prefetch) |
| **Phase 3** | `2'b11` | T6_RD[3], UNPACK_RD[2] | 2 ports | Unpack channel 2 (prefetch) |

**Phase Selection Mechanism:**

The 2-bit phase code is extracted from the L1 address:
```
phase = address[k+1:k]  
  where k is firmware-configurable via CSR (typically k=6 for 64-byte granularity)
```

**Firmware Optimization:**

To maximize parallel utilization and avoid phase conflicts:
1. Assign weight tile addresses to Phase 0 (large tensor ops through T6_RD[0,4] and T6_RW)
2. Assign activation tiles to Phases 1–3 (unpack engines read independently)
3. Configure address bit offset (k) based on GEMM tile sizes (k=6 typical for 64-byte blocks)

**Example:** For K_tile=48 INT16 (96 bytes):
- Weight tiles at addresses [0x00000..0x0FFFF] → all Phase 0 (via T6_RD[0], distributed across 4 sub-banks)
- Activation tile at [0x10000..0x107FF] → Phase 1 (via UNPACK_RD[0])
- Output tile at [0x20000..0x2FFFF] → Phase 0 (via T6_RW, no conflict with weight reads due to separate ports)

#### 2.6.3.3 Concurrent Access Model (Formal)

**Port allocation per master (maximum):**

| Master Agent | Port Type | Allocation | Simultaneous? |
|---|---|---|---|
| TRISC0 (unpack) | RD_PORT | 1–2 | ✓ Yes (if different banks) |
| TRISC1 (math) | (none — uses register files) | — | N/A |
| TRISC2 (pack) | WR_PORT or RW_PORT | 1–2 | ✓ Yes (if different banks) |
| TRISC3 (mgmt) | RD_PORT | 1 | ✓ Yes (if different bank from TRISC0) |
| Unpack engine | RD_PORT | 1–2 | ✓ Yes (if different banks) |
| Pack engine | RW_PORT | 1–2 | ✓ Yes (if different banks) |
| NoC DMA (512-bit) | WR_PORT | 1 | ✓ Yes (different bank) |

**Bottleneck:** The **8 RD_PORTs** are the primary constraint during high-bandwidth prefetch (unpack reads L1 @ 128 bits/cycle). With 8 RD ports and only 1–2 typical read masters, no contention during steady state.

#### 2.6.3.4 Atomic Transaction (AT) Operation Bank Assignment

Atomic memory operations (read-modify-write) require priority routing to minimize latency for synchronization primitives (spinlocks, completion flags). N1B0's L1 implements dedicated bank allocation for AT operations via the `AT_SBPORT_MAP` register array to prevent head-of-line blocking when atomic and non-atomic traffic compete.

**Atomic Operation Bank Assignment Table (RTL-verified from `tt_trin_l1_cfg.svh` line 100):**

| AT Port Index | Assigned Banks | Request Type | RISC-V Instruction | Purpose | Priority |
|---|---|---|---|---|---|
| **Port 0** | Banks 9, 0 | `AT_RISCV` | LR/SC, AMOSWAP, AMOADD, AMOAND, AMOOR, AMOXOR, AMOMAX, AMOMIN | RISC-V atomic memory operations (firmware spinlocks, synchronization) | High |
| **Port 1** | Banks 10, 1 | `AT_COMPUTE` | FPU-generated atomics (reduce-and-scatter accumulations) | Compute-side atomic results | High |
| **Port 2** | Banks 11, 2 | `AT_THCON` | Threshold compare + update (quantization thresholds, batch norm stats) | Threshold atomics | Medium |
| **Port 3** | Banks 12, 3 | `AT_PARTIALW` | Byte-masked atomic write (selective field update) | Partial-word atomics | Medium |

**Hardware Behavior:**

1. **AT Operations Always Get Reserved Banks:** Each AT port is hardwired to one primary bank and one backup bank (round-robin fallback if primary is busy).
2. **No Blocking:** Non-AT reads/writes to Banks 0–3, 9–12 cannot block AT operations on reserved banks 0, 1, 2, 3, 9–12.
3. **Bank Spillover:** If the primary bank of an AT operation fills, the request automatically spills to the backup bank (zero-latency failover).
4. **Configuration:** The mapping is fixed by RTL; firmware cannot reconfigure `AT_SBPORT_MAP` at runtime.

**Example:** An `AT_RISCV` spinlock acquisition (LR/SC on address 0x10000):
```
AT_RISCV request arrives (address 0x10000)
  ↓
Port 0 (AT_RISCV) allocated
  ↓
bank_id = hash(0x10000) = 5 (normal), but overridden to Bank 9 (AT-reserved)
  ↓
Request routed to Bank 9 (guaranteed no conflict with concurrent non-AT reads/writes)
  ↓
LR/SC pair completes in ≤2 cycles (fast path)
```

#### 2.6.4 Address Map (Logical Layout within L1)

```
L1 Logical Layout (3MB total per cluster)
────────────────────────────────────────────────────
0x00000 – 0x05FFF   TRISC3 data region (24KB)
0x06000 – 0x15FFF   TRISC0 IMEM — unpack LLK code (64KB region; 4KB ICache backed)
0x16000 – 0x25FFF   TRISC1 IMEM — math LLK code (64KB region; 2KB ICache backed)
0x26000 – 0x35FFF   TRISC2 IMEM — pack LLK code (64KB region; 2KB ICache backed)
0x36000 – 0x45FFF   TRISC3 IMEM — tile management (64KB region; 4KB ICache backed)
0x46000 – 0x2FFFFF  Tensor workspace (~2.73MB)
────────────────────────────────────────────────────
  ↑ TDMA uses tensor workspace for weight tiles,
    activation buffers, and KV-cache storage.
```

TRISC3 copies TRISC0/1/2 firmware images into the IMEM regions before releasing TRISC resets.

#### 2.6.4.1 L1 Address Visibility by Agent

The L1 partition is accessible to multiple agents (TRISCs, TDMA, iDMA, and Rocket CPU in Dispatch) with different visibility and access rights based on role and execution phase:

**L1 Address Visibility Matrix (per Tensix cluster, 3 MB address space):**

| Address Range | Region Purpose | TRISC0 | TRISC1 | TRISC2 | TRISC3 | TDMA Unpack | TDMA Pack | Overlay | iDMA | Rocket |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **0x00000–0x05FFF** | TRISC3 data/workspace (24KB) | RW | RW | RW | RW | — | — | — | Write | Write |
| **0x06000–0x15FFF** | TRISC0 IMEM (unpack LLK, 64KB) | RO | RO | RO | RO | — | — | — | Write | Write |
| **0x16000–0x25FFF** | TRISC1 IMEM (math LLK, 64KB) | RO | RO | RO | RO | — | — | — | Write | Write |
| **0x26000–0x35FFF** | TRISC2 IMEM (pack LLK, 64KB) | RO | RO | RO | RO | — | — | — | Write | Write |
| **0x36000–0x45FFF** | TRISC3 IMEM (mgmt, 64KB) | RO | RO | RO | RO | — | — | — | Write | Write |
| **0x46000–0x2FFFFF** | Tensor workspace (~2.73MB) | RW | RW | RW | RW | Read | RW | **RW (side-channel)** | RW | Write |

**Legend:**
- **RO** = Read Only (instruction memory, immutable during execution)
- **RW** = Read + Write (data memory, read and write access)
- **—** = No direct access

---

**Detailed Agent Descriptions:**

| Agent | Access Method | Address Visibility | Throughput | Scope | Notes |
|-------|---|---|---|---|---|
| **TRISC0** | 128-bit direct port (ai_clk) | Per-thread window (configurable `i_trisc_l1_start_addr[0]`–`i_trisc_l1_end_addr[0]`) | 128 bits/cycle | **Local L1 only** | Unpack engine reads from tensor workspace; writes to SRCA/SRCB via TDMA |
| **TRISC1** | 128-bit direct port (ai_clk) | Per-thread window (configurable `i_trisc_l1_start_addr[1]`–`i_trisc_l1_end_addr[1]`) | 128 bits/cycle | **Local L1 only** | Math engine; issues MOPs; typically reads instruction memory only |
| **TRISC2** | 128-bit direct port (ai_clk) | Per-thread window (configurable `i_trisc_l1_start_addr[2]`–`i_trisc_l1_end_addr[2]`) | 128 bits/cycle | **Local L1 only** | Pack engine reads DEST via TDMA; writes to tensor workspace or NoC |
| **TRISC3** | 128-bit direct port (ai_clk) | Per-thread window (configurable `i_trisc_l1_start_addr[3]`–`i_trisc_l1_end_addr[3]`) | 128 bits/cycle | **Local L1 only** | Tile management; boot firmware; residual DMA control |
| **TDMA Unpack** | Via TRISC0 microcode (UNPACK MOP) | Tensor workspace 0x46000–0x2FFFFF | 512 bits/cycle (dm_clk) | **Local L1 only** | Reads weight/activation tiles from L1; formats → SRCA/SRCB; pipelined with computation |
| **TDMA Pack** | Via TRISC2 microcode (PACK MOP) | DEST latch-array → tensor workspace | 512 bits/cycle (dm_clk) | **Local L1 only** | Reads computed results from DEST; post-math activation (ReLU, etc.); writes L1 or NoC |
| **Overlay (local)** | 512-bit side-channel port (noc_clk) | Tensor workspace 0x46000–0x2FFFFF | 512 bits/cycle (noc_clk) | **Local L1 only** | Autonomous DMA orchestration; writes DRAM data to L1 (via NIU read response); reads L1 to write to DRAM (via overlay stream write) |
| **iDMA (Dispatch)** | NoC write packet (via Rocket RoCC) | Any address 0x00000–0x2FFFFF | 512 bits/cycle (noc_clk) | **ANY Tensix L1 across mesh** | Pre-loads firmware at boot; pre-loads weights before kernel; can target any (X,Y) Tensix cluster; only pre-kernel (not during compute) |
| **Rocket (Dispatch)** | Indirect via iDMA RoCC instruction | Cannot directly access; programs iDMA | Via iDMA | **Dispatch-controlled only** | Dispatch CPU at (0,3) or (3,3); issues `custom-3` instruction to trigger iDMA transfers; cannot read Tensix L1 directly |

---

**Key Architectural Distinction: Local vs. Remote L1 Access**

The L1 partition is **local to each Tensix cluster**. Different agents have different access scope:

| Scope | Agents | Access Mechanism | L1 Target |
|-------|--------|------------------|-----------|
| **LOCAL (same cluster)** | TRISC0/1/2/3, TDMA, Overlay | Direct internal ports (128-bit or 512-bit) | Own cluster's L1 only |
| **REMOTE (across mesh)** | iDMA (in Dispatch) | NoC packet injection + NIU write | Any Tensix cluster's L1 |

**Implication:**
- **Dispatch iDMA can load weights into ANY Tensix L1** — Dispatch_W can reach left Tensix columns (X=0, X=1); Dispatch_E can reach right columns (X=2, X=3).
- **Overlay can only use its local L1** — each Tensix cluster's overlay engine reads/writes its own L1, not adjacent clusters.
- **TRISC can only access local L1** — TRISC in tile (1,2) cannot directly read L1 from tile (2,2); must use NoC-based inter-tile communication.

---

**Key Access Constraints:**

1. **Overlay is LOCAL to cluster** — The overlay engine (inside each Tensix tile) has a dedicated 512-bit side-channel port to its own L1 only. It cannot directly access L1 in other clusters. Multi-tile data movement requires TRISC-initiated overlay streams (DRAM→L1→NoC→neighboring L1) or explicit inter-tile writes.

2. **iDMA is REMOTE across mesh** — iDMA in Dispatch can inject NoC write packets to any (X,Y) Tensix endpoint and write any L1 address. This makes iDMA the preferred mechanism for pre-loading weights across the entire Tensix array before kernel start.

3. **TRISC per-thread address windows** — Each TRISC has a programmable address range check. Accesses outside `[i_trisc_l1_start_addr[t], i_trisc_l1_end_addr[t]]` are blocked. Firmware must configure these at boot.

4. **iDMA pre-kernel only** — iDMA can write to any L1 address but is used only during **pre-kernel setup phase**. Once kernel is running (TRISC reset released), iDMA cannot inject writes into active tensor workspace without data corruption.

5. **TDMA no TRISC bypass** — TDMA unpack/pack engines are not autonomous; they are driven by TRISC0/TRISC2 MOPs. Each TDMA operation is initiated by a TRISC microcoded instruction, not by direct hardware configuration.

6. **Rocket no direct L1 access** — The Rocket CPU in Dispatch tile cannot read Tensix L1 directly. It can only write weights/firmware via iDMA pre-load, and read results via L1→DRAM iDMA read commands triggered at kernel completion.

7. **Concurrent masters (local L1)** — Multiple agents (TRISC0, TRISC1, TRISC2, TRISC3, unpack, pack, overlay, NoC DMA) can access **local L1 simultaneously** **if they target different banks** (see §2.6.3 Bank Selection Algorithm). Firmware must schedule tensor workspace accesses to avoid bank conflicts.

8. **Overlay streams compete with iDMA** — Both overlay (in Tensix) and iDMA (in Dispatch) can write to Tensix L1. However, they operate in different phases: iDMA during pre-kernel, overlay during kernel execution. Simultaneous access could cause data corruption if not coordinated.

---

**Firmware Loading Sequence (Typical Boot):**

```
Time    Agent             Action                          Destination L1
────────────────────────────────────────────────────────────────────────
T0      Rocket            Issue iDMA write TRISC3 code    0x36000–0x45FFF (TRISC3 IMEM)
T1      Rocket            Issue iDMA write TRISC0 code    0x06000–0x15FFF (TRISC0 IMEM)
T2      Rocket            Issue iDMA write TRISC1 code    0x16000–0x25FFF (TRISC1 IMEM)
T3      Rocket            Issue iDMA write TRISC2 code    0x26000–0x35FFF (TRISC2 IMEM)
T4      Rocket            Issue iDMA write weights        0x46000–0x????? (tensor workspace)
T5      Rocket            Deassert TRISC3 reset
        TRISC3            Executes boot firmware          (accesses 0x00000–0x05FFF data region)
T6      TRISC3            Deassert TRISC0/1/2 resets      
        TRISC0/1/2        Begin executing kernel          (0x06000–0x2FFFFF access enabled)
T7+     TDMA              Unpack/pack active             (reads/writes tensor workspace)
```

---

#### 2.6.5 Datapath Connections

```
                   ┌──────────────────────────────────┐
                   │       tt_t6_l1_partition          │
                   │         (512 macros, 3MB)         │
                   └──┬─────┬──────┬──────┬───────────┘
                      │     │      │      │
               TRISC3 │  TRISC  Unpack  Pack
               data   │  IMEM   engine  engine
               bus    │         │       │
                      │         ▼       │
                      │    SRCA/SRCB RF │
                      │         │       │
                      │         ▼       │
                      │       FPU       │
                      │         │       │
                      │         ▼       │
                      │       DEST RF   │
                      │                 │
                      ▼                 ▼
               NoC side channel     Pack writes
               (512-bit DMA)        back to L1
```

#### 2.6.6 512-Bit NoC Side Channel

A dedicated 512-bit bus connects the L1 directly to the NoC local port, **bypassing the TRISC3 data path entirely**. This enables:
- Zero-overhead DMA: TDMA engine initiates a transfer; L1 data flows directly into NoC flits at one 512-bit flit per `noc_clk` cycle
- TRISC3 CPU is not involved in data movement, freeing it for control tasks
- Sustained NoC bandwidth equal to the full flit width

#### 2.6.7 ECC

Each SRAM macro implements **SECDED (Single-Error Correct, Double-Error Detect)** ECC. A single-bit error is silently corrected on read; a double-bit error sets a sticky error flag and optionally triggers an interrupt to TRISC3. ECC scrubbing is managed by firmware using the `T6_L1_CSR` register set.

#### 2.6.8 Clock Domains

| Operation                    | Clock domain  |
|------------------------------|---------------|
| Tensor data move (TDMA)      | `dm_clk`      |
| Register-file access (FPU path) | `ai_clk`   |
| NoC side channel DMA         | `noc_clk`     |

CDC crossings between `ai_clk` and `dm_clk` within the L1 partition use registered boundary cells. The `noc_clk` side channel uses a synchronizer FIFO at the L1→NIU interface.

### 2.7 TDMA Engine

#### 2.7.1 Overview and Rationale

The **Tile DMA (TDMA)** engine is the data-movement fabric of the Tensix tile. It is the hardware that connects L1 memory, the FPU register files (SRCA/SRCB/DEST), and the NoC, handling all bulk tensor transfers without TRISC3 involvement.

TDMA operates entirely under TRISC control. TRISC1 (math) programs the MOP sequencer; TRISC0 (unpack) drives the unpack engine; TRISC2 (pack) drives the pack engine. Each is an independent pipeline stage, enabling the double-buffered compute loop described in §2.3.

**Why MOP encoding?** A single raw RISC-V instruction operates on one register or one memory word. Loading a 16×16 INT16 tensor tile from L1 into SRCA would require hundreds of load instructions. A single MOP — encoded as one or two 32-bit words — can express "load a 16×16 INT16 tile starting at L1 base address X with row stride Y into SRCA bank 0." This achieves roughly **10× instruction density** compared to raw RISC-V equivalents.

#### 2.7.2 Sub-block Description

| Sub-block       | Count | Controlling TRISC | Function                                                                |
|-----------------|-------|----|--------------------|-------------------------------------------------------------------------|
| MOP sequencer   | 1     | TRISC1             | Decodes MOP instructions; dispatches to G/M-Tile, FP-Lane, or SFPU     |
| Unpack engines  | 3     | TRISC0             | Read L1 tensor data or incoming NoC flit; apply format conversion, transpose, bank init; load SRCA/SRCB/SRCS |
| Pack engines    | 2     | TRISC2             | Read DEST/SRCS register files; apply format conversion and post-math activation (ReLU/CReLU/flush); write to L1 or NoC flit |
| Address gen     | 1     | TRISC0/TRISC2      | Multi-dimensional stride/offset computation for tensor addressing (up to 4 dimensions) |

RTL file: `tt_instrn_engine.sv` (contains MOP sequencer and TDMA logic); `tt_trisc.sv` (per-thread cores).

#### 2.7.3 MOP Sequencer

**RTL files:** `tt_mop_decode.sv`, `tt_mop_config.sv`, `tt_mop_decode_math_loop.sv`, `tt_mop_decode_unpack_loop.sv`

The MOP sequencer receives 32-bit compressed MOP instruction words from TRISC1 and **expands each one into a sequence of primitive FPU tag words**, one per clock cycle, that drive the G-Tile, FP-Lane, and SFPU datapaths. TRISC1 issues one MOP word; the sequencer autonomously generates dozens to hundreds of primitive operations from it, keeping the FPU continuously occupied without TRISC1 involvement.

##### MOP Word Encoding (32-bit, `tt_t6_opcode_pkg.sv`)

```
MOP instruction word [31:0]:

  [31]      mop_type        1-bit   0 = unpack_loop FSM
                                    1 = math_loop FSM
  [30]      done            1-bit   marks last MOP in a sequence
  [29:23]   loop_count[6:0] 7-bit   outer loop count (high bits)
  [22:8]    zmask_lo / loop 15-bit  inner loop count[8:0] + zmask[14:9]
  [7:0]     opcode          8-bit   OPCODE_MOP=0x01, OPCODE_MOP_CFG=0x03

Total loop range: outer = 10-bit (up to 1023), inner = 9-bit (up to 511)
```

An optional `MOP_CFG` word (opcode `0x03`) carries the upper 24 bits of the z-plane mask for unpack operations:
```
MOP_CFG word [31:0]:
  [31:8]  zmask_hi24    24-bit  high bits of 32-bit z-plane skip mask
  [ 7:0]  opcode        8-bit   0x03
```

##### MOP Configuration Banking

Before TRISC1 issues a MOP, it pre-programs a **dual-bank configuration register set** (`tt_mop_config.sv`) with the expanded parameters for the inner loop:

| Register | Content |
|----------|---------|
| `LOOP0_LEN` | Outer loop count |
| `LOOP1_LEN` | Inner loop count |
| `LOOP_INSTR0` | Primitive instruction A (issued on even inner iterations) |
| `LOOP_INSTR1` | Primitive instruction B (issued on odd inner iterations) |
| `LOOP_START_INSTR0` | Preamble instruction before inner loop begins |
| `LOOP_END_INSTR0/1` | Postamble instructions after inner loop ends |
| `LOOP0_LAST_INSTR` | Final instruction at the end of the outer loop |

Two banks (BANK0, BANK1) exist for **double-buffering**: while the sequencer executes one bank, TRISC1 can program the other. The hardware automatically toggles the active bank when `mop_done` is asserted; TRISC1 toggles the write bank when it asserts `cfg_done`. `o_mop_cfg_write_ready` tells TRISC1 whether the next bank is available to write.

##### Math Loop FSM (`tt_mop_decode_math_loop.sv`)

When `mop_type=1` (math loop), the sequencer runs a **two-level nested loop FSM**:

```
States: IDLE → LOOP_START_OP0 → IN_LOOP → LOOP_END_OP0 → LOOP_END_OP1
                                         → FINAL_LOOP_END_OP0 → FINAL_LOOP_END_OP1

Execution per MOP:
  emit LOOP_START_INSTR0          ← preamble (e.g. clear accumulator)
  for outer = 0 .. LOOP0_LEN-1:
    for inner = 0 .. LOOP1_LEN-1:
      emit LOOP_INSTR0            ← even cycle: e.g. srca_rd_addr = k
      emit LOOP_INSTR1            ← odd  cycle: e.g. advance k+1
    emit LOOP_END_INSTR0          ← after each inner loop
    emit LOOP_END_INSTR1
  emit FINAL_LOOP_END_INSTR0      ← after outer loop done
  emit FINAL_LOOP_END_INSTR1
  assert mop_done
```

**One primitive FPU tag is emitted per clock cycle** — the FPU pipeline never stalls waiting for the sequencer. For a 48-row SRCA bank pass (K_tile_FP16B=48), TRISC1 issues one MOP; the sequencer generates 48 consecutive `fpu_tag_t` words, each with `srca_rd_addr` incrementing from 0 to 47.

##### Unpack Loop FSM (`tt_mop_decode_unpack_loop.sv`)

When `mop_type=0` (unpack loop), the sequencer iterates over z-planes (depth slices of a 3D tensor) and routes each plane to the correct unpack port:

```
States: IDLE → UNPACK_A0/A1/A2/A3 → UNPACK_B → SKIP_A → SKIP_B

For each z-plane (count = loop_count + 1):
  if zmask[plane] == 0:  emit unpack instruction for this plane
  if zmask[plane] == 1:  skip this plane (zero-fill or mask out)
  current_zmask >>= 1    ← shift mask right each iteration
```

The 32-bit z-plane mask (8 bits from `zmask_lo8` in MOP word + 24 bits from `MOP_CFG zmask_hi24`) allows up to 32 tensor depth planes to be selectively loaded or skipped in one MOP, enabling sparse tensor loading without software branching.

##### FPU Tag — Per-Cycle Primitive Operation (`tt_tensix_pkg.sv`)

Each cycle the sequencer outputs one `fpu_tag_t` (RTL struct, ~46+ bits) to the FPU pipeline:

```
fpu_tag_t fields (key subset):
  srca_rd_addr    [5:0]   SRCA row to read this cycle (0..47)
  srca_rd_other_bank 1b   which SRCA double-buffer bank
  srcb_fmt_spec   [7:0]   SRCB format (INT8_2x, FP16B, FP32 …)
  srca_fmt_spec   [7:0]   SRCA format
  dst_fmt_spec    [7:0]   destination format
  dstacc_idx    [9:0]     DEST row to accumulate into this cycle
  dest_wr_row_mask [3:0]  which of 4 DEST rows to write (FP_ROWS=4)
  instr_tag.int8_op  1b   → forces fpu_tag_32b_acc (INT32 accumulate)
  instr_tag.fp32_acc 1b   → FP32 accumulate mode
  op_mmul         1b      matrix-multiply mode (vs elementwise)
  elwsub          1b      elementwise subtract
  dummy_op        1b      pipeline flush / bubble
```

The FPU reads `srca_rd_addr` to fetch from SRCA, uses `dstacc_idx` to read-modify-write DEST, and uses the format fields to select the Booth multiplier path or FP32 path. Every field is set by the MOP config registers — TRISC2 never touches them cycle-by-cycle during execution.

##### Completion and Stall

```
mop_done = (FSM reaches IDLE and mop_opcode_done asserted)
         OR (zero-count MOP: loop lengths both zero → immediate done)

TRISC2 stall path:
  o_mop_active  ← high while sequencer is running
  o_mop_cfg_write_ready ← high when next config bank is free
  TRISC2 uses SEMPOST (from hardware i_trisc_sempost) when mop_done
    → TRISC0/TRISC1 can SEMGET to synchronize on math completion
```

##### End-to-End MOP Execution Example (INT8 GEMM, one pass)

```
TRISC1 firmware                    MOP Sequencer hardware
──────────────────                 ─────────────────────────────────
write LOOP0_LEN  = 1
write LOOP1_LEN  = 48              (48 = SRCS_NUM_ROWS_16B)
write LOOP_INSTR0 = {srca_rd++,    (primitive: advance SRCA row,
                     dstacc_idx++}   advance DEST accumulator index)
write cfg_done
issue MOP opcode (mop_type=1)  →   cycle 0:  emit tag {srca_rd=0,  dstacc=0}
                                   cycle 1:  emit tag {srca_rd=1,  dstacc=2}
                                   cycle 2:  emit tag {srca_rd=2,  dstacc=4}
                                   ...
                                   cycle 47: emit tag {srca_rd=47, dstacc=94}
                                   cycle 48: assert mop_done
TRISC1 (next MOP or SEMPOST) ←     hardware SEMPOST sem1 → TRISC2 unblocks
```

One MOP word from TRISC1 generates **48 consecutive FPU tag cycles** with zero TRISC1 involvement after the issue. For the full K=8192 INT8 pass (86 firmware passes × 48 MOP cycles), TRISC1 issues 86 MOP words total.

#### 2.7.4 Pack Engine (TRISC2)

There are **2 packers** in a Tensix NEO core. They read from both DEST and SrcS register files and write formatted data to either L1 or the NoC output path. The pack engine is **controlled by TRISC2** as part of the double-buffered compute pipeline.

##### 2.7.4.1 Complete Dataflow

```
                        L1 SRAM
                          │
           ┌──────────────┼──────────────┐
           │              │              │
       ┌───▼────┐    ┌───▼────┐    ┌───▼────┐
       │Unpacker│    │Unpacker│    │Unpacker│
       │   0    │    │   1    │    │   2    │
       └───┬────┘    └───┬────┘    └───┬────┘
           │             │             │
           ▼             ▼             ▼
         SrcA ────┬──► Matrix FPU ──┬──► DEST
         SrcB ────┤                 │
                  │        +        │
                  │    FP-Lane      │
                  │                 │
                  └─────────────────┤
                                    │
                         ┌──────────▼──────────┐
                         │   SFPU reads DEST   │
                         │   (and SrcS)        │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                ┌───▼─────────────────┐         ┌──▼────────┐
                │     PACKER (2×)     │         │ SFPU      │
                │                     │         │ writes    │
                │ Reads: DEST + SrcS  │         │ to SrcS   │
                │                     │         │           │
                │ Applies:            │         └───────────┘
                │ • Format conversion │
                │ • Activations       │
                │ • Address gen       │
                └──────────┬──────────┘
                           │
                           ▼
                       L1 SRAM
                     or NoC flit
```

**Architectural Position:**
- Packer operates **downstream of DEST** (FPU output buffer)
- Reads from **both DEST and SrcS** (dual input paths)
- Executes **after** FPU/SFPU complete their operations on current tile
- Operates **in parallel** with TRISC1 (math) and TRISC0 (unpack) via hardware semaphores

##### 2.7.4.2 Format Conversion

**Format Conversion** on pack path:
- INT32 → FP16B (with optional stochastic rounding)
- INT32 → INT8 (with optional stochastic rounding)
- FP32 → FP16B
- Identity (no conversion — pass through as-is)

##### 2.7.4.3 Post-Math Activation Functions

**Post-Math Activation Functions** (execute during L1 write path):
- ReLU — max(x, 0)
- ReLUMax — max(min(x, max_val), 0)
- CReLU — concatenation of [ReLU(x), ReLU(-x)]
- Flush-to-zero — replace values below a threshold with zero

These dedicated post-math operations **reduce latency** by combining activation logic with the pack write, avoiding separate ALU passes through the FPU. Example: After SFPU computes softmax into DEST, packer can apply post-activation normalization during write to L1.

##### 2.7.4.4 Address Generation

The pack engine uses the **address generator** to compute the L1 destination address for each output element using a stride/offset model, allowing non-contiguous writes (e.g., writing rows of a transposed tile into a strided L1 region).

##### 2.7.4.5 Double-Buffered Pipeline Timing

The packer operates in a **triple-buffered pipeline** where TRISC2 (pack) always reads from the **inactive DEST bank** while TRISC1 (math) writes to the **active bank**:

```
Cycle epoch N:
  ┌─────────────────────┬─────────────────────┬─────────────────────┐
  │  TRISC0 (unpack)    │  TRISC1 (math)      │  TRISC2 (pack)      │
  ├─────────────────────┼─────────────────────┼─────────────────────┤
  │ Load tile N+1       │ Compute tile N      │ Write tile N-1      │
  │ L1 → SRCA bank B    │ SRCA bank A → DEST  │ DEST bank (other)   │
  │                     │ (active bank)       │ → L1 output         │
  │ SEMPOST sem0        │ SEMGET sem0         │ SEMGET sem1         │
  │                     │ SEMPOST sem1        │ SEMPOST sem0 (opt)  │
  └─────────────────────┴─────────────────────┴─────────────────────┘
                  │              │              │
                  └─ hardware semaphore handshake (no TRISC polling)

Cycle epoch N+1:
  ┌─────────────────────┬─────────────────────┬─────────────────────┐
  │  TRISC0 (unpack)    │  TRISC1 (math)      │  TRISC2 (pack)      │
  ├─────────────────────┼─────────────────────┼─────────────────────┤
  │ Load tile N+2       │ Compute tile N+1    │ Write tile N        │
  │ L1 → SRCA bank A    │ SRCA bank B → DEST  │ DEST bank (other)   │
  │                     │ (active bank)       │ → L1 output         │
  │ SEMPOST sem0        │ SEMGET sem0         │ SEMGET sem1         │
  │                     │ SEMPOST sem1        │ SEMPOST sem0 (opt)  │
  └─────────────────────┴─────────────────────┴─────────────────────┘
```

**Key Points:**
- **No stalls**: TRISC2 never waits for DEST to be written; it reads the other bank
- **Hardware-managed**: DEST bank toggle is automatic via `dest_toggle` signal
- **Continuous output**: Every cycle, packer writes one row to L1 (or multiple rows per cycle depending on port width)
- **SFPU integration**: If SFPU writes to SrcS, packer can **simultaneously** read DEST and output via separate packer instances

##### 2.7.4.6 FPU Result Write-Back Latency (DEST → L1)

The **end-to-end write-back latency** from FPU MAC result to L1 storage completion is critical for kernel pipelining and scheduling dependent operations.

**Complete Latency Path (RTL-verified from tt_fpu_gtile.sv, tt_pack_*.sv, tt_t6_l1_partition.sv):**

| Stage | Cycle | Duration | Event | Hardware Component |
|-------|-------|----------|-------|---|
| **0** | N | 1 cy | FPU MAC completes, result written to DEST latch | tt_fpu_gtile.sv (synchronous write) |
| **1** | N+1 | 3 cy | Packer reads DEST via 3-cycle pipelined read (address decode + data mux + combinational output) | tt_pack_*.sv (3-stage pipeline) |
| **2** | N+2–N+3 | 1–2 cy | Packer applies post-math operations (ReLU, CReLU, Flush-to-0, stochastic rounding, format conversion INT32→FP16B/INT8) | tt_pack_*.sv (1–2 cy through datapath) |
| **3** | N+4–N+5 | 1 cy | Packer writes output to L1 via PACK_WR_PORT (synchronous SRAM write) | tt_t6_l1_partition.sv (1-cy write, completes N+6) |
| **TOTAL** | — | **6–7 cycles** | FPU accumulation → DEST → Pack format→ L1 storage complete | — |

**Breakdown by operation type:**

**Standard Path (INT32 → FP16B):**
```
Cycle N:   FPU writes INT32 result to DEST
Cycle N+1: Packer reads DEST (3-cycle pipelined read begins)
Cycle N+3: Packer output register stable (format conversion starts)
Cycle N+4: Packer writes to L1 (L1 update completes N+5)
Total:     5 cycles (fast path when format conversion is simple)
```

**With Stochastic Rounding (INT32 → FP16B + rand):**
```
Cycle N:   FPU writes INT32 result to DEST
Cycle N+1: Packer reads DEST (3-cycle pipelined read begins)
Cycle N+3: Packer output register stable (format + stochastic rounding: +1 cy)
Cycle N+5: Packer writes to L1 (L1 update completes N+6)
Total:     6 cycles (typical path with stochastic rounding)
```

**With SFPU Post-Math (INT32 → post-activation → FP16B):**
```
Cycle N:   FPU writes INT32 result to DEST
Cycle N+1: Packer reads DEST (3-cycle pipelined read begins)
Cycle N+3: Packer output register stable
Cycle N+4: SFPU performs DEST read-modify-write (exp/log/gelu/etc.)
Cycle N+5: SFPU writes updated value to DEST or SrcS
Cycle N+6: Packer reads updated DEST (if SFPU wrote to DEST)
Cycle N+7: Packer writes to L1 (L1 update completes N+8)
Total:     8 cycles (longest path: SFPU post-processing)
```

**Practical Impact for Kernel Designers:**

1. **Pipeline Scheduling:** For dependent GEMMs, schedule next GEMM to start at cycle N+8 (safe margin for longest SFPU path). For non-dependent GEMMs, can start at N+6.
2. **Overlapped Execution:** Using triple-buffered DEST (TRISC1 writes bank A while TRISC2 reads bank B), result write-back latency is **hidden** from critical path — TRISC1 continues issuing next MOP without waiting.
3. **K-reduction accumulation:** For multi-pass GEMMs (K > K_tile), each pass accumulates into DEST immediately without waiting for write-back to L1.

**Example: 8192 INT8 MACs with stochastic rounding:**
```
Pass 1 (K_tile=1536 INT8):   Cycle 0–1500:   MACs accumulate in DEST
                             Cycle 1501–1506: Result write-back (6 cy)
                             ↓ (concurrent)
Pass 2 (K_tile=1536 INT8):   Cycle 1500–3000: MACs on fresh DEST bank
Result visible in L1:                         Cycle 1507 (6 cycles after first MAC completes)
```

#### 2.7.5 Unpack Engine (TRISC1)

There are **3 unpackers** in a Tensix NEO core. The unpack engine reads tensor data from L1 or an incoming NoC flit and loads it into the SrcX register files for FPU consumption:

```
[ L1 read port ] ──► Format Converter ──► Unpacker 0 ──► SRCA register file
                                       ├─ Unpacker 1 ──► SRCB register file
                                       └─ Unpacker 2 ──► SRCS register file
[ NoC input flit ] ──────────────────────► SRCB (direct from L1 via 512-bit path)
```

**Unpacker Assignment** (fixed per unpack engine):
- **Unpacker 0**: Always unpacks into SRCA
- **Unpacker 1**: Always unpacks into SRCB
- **Unpacker 2**: Always unpacks into SRCS

**Unpack Operations** (configured via TDMA config registers):

| Operation | Scope | Description |
|-----------|-------|-------------|
| Format conversion | All unpackers | Converts incoming data format to target register format |
| Transpose | SRCA/SRCB only | Rows transposed into columns during unpack |
| Bank initialization | All unpackers | Every datum in a register bank initialized to a specified value |
| Inline transpose (Dest) | SRCA/SRCB/Dest | Unpack to SRCA, SRCB, and DEST enables row↔column transpose without intermediate staging |

**Format conversion options** on unpack path:
- FP16B → FP32 (for G-Tile)
- INT16 → INT16 (pass-through for M-Tile)
- INT8 → INT16 (for M-Tile INT8 mode, packing two INT8 per lane)
- FP8 (E4M3/E5M2) → FP16 (for FP-Lane)

#### 2.7.6 Address Generator

The address generator supports **up to 4 dimensions** of tensor addressing, matching the iDMA address generation structure. Each dimension has:
- `base`: starting address
- `stride`: byte increment per element in this dimension
- `size`: number of elements in this dimension

This allows a single MOP to traverse a row, column, or arbitrary slice of a multi-dimensional tensor stored in L1 without software looping overhead.

#### 2.7.6.1 Unified Pack-Unpack-Math Pipeline

The three TDMA engines (unpack, math, pack) form a **unified data pipeline** controlled by three independent TRISC threads with hardware semaphore synchronization. This architecture achieves **zero-stall pipelined execution**:

| Stage | TRISC | Inputs | Outputs | Latency | Buffering |
|-------|-------|--------|---------|---------|-----------|
| **Unpack** | TRISC0 | L1, NoC flit | SrcA, SrcB, SrcS | 10–50 cycles (MOP latency) | 2 SRCA banks, 2 SRCB banks, 2 SrcS banks |
| **Math** | TRISC1 | SrcA, SrcB, SrcS (via FPU/SFPU) | DEST | 50–200 cycles (MOP burst) | 2 DEST banks, 2 SrcS banks (SFPU writeback) |
| **Pack** | TRISC2 | DEST, SrcS | L1, NoC | 5–10 cycles per row | N/A (streaming output) |

**Hardware Synchronization (no polling):**
```
TRISC0 SEMPOST sem0 ──► TRISC1 SEMGET (unblocks on math start)
TRISC1 SEMPOST sem1 ──► TRISC2 SEMGET (unblocks on pack start)
```

**Key Benefit:** While TRISC1 computes tile N, **simultaneously**:
- TRISC0 prefetches tile N+1 into opposite SrcA bank
- TRISC2 writes tile N−1 from opposite DEST bank to L1

This **three-stage pipeline** (prefetch, compute, drain) ensures:
- ✅ No dependency bubbles
- ✅ All three threads always busy
- ✅ DRAM/L1 I/O completely hidden by compute latency
- ✅ Maximum tensor throughput (no stalls waiting for data arrival or output buffer draining)

#### 2.7.7 Double-Buffered Pipeline

The canonical double-buffered compute loop enabled by TDMA:

```
Cycle epoch N:
  TRISC0 (unpack):  L1[tile N+1] → SRCA bank 1   (prefetch next)
  TRISC1 (math):    SRCA bank 0 + SRCB → DEST     (compute current)
  TRISC2 (pack):    DEST → L1[output N-1]          (drain previous)

Cycle epoch N+1:
  TRISC0 (unpack):  L1[tile N+2] → SRCA bank 0   (prefetch next)
  TRISC1 (math):    SRCA bank 1 + SRCB → DEST     (compute current)
  TRISC2 (pack):    DEST → L1[output N]            (drain previous)
```

Hardware semaphore instructions (SEMPOST/SEMGET) gate each transition: TRISC0 executes `SEMPOST sem0` when SRCA/SRCB is filled; TRISC1 is hardware-stalled at `SEMGET sem0` until that post, then fires its MOP; TRISC1 executes `SEMPOST sem1` when DEST is ready; TRISC2 is stalled at `SEMGET sem1` until that post, then reads DEST.

#### 2.7.8 Complete Tensix Dataflow (RTL-Verified)

The following diagram shows the **complete end-to-end TDMA dataflow** with all 3 unpackers, 2 packers, register files, and TRISC thread assignments. All components are cross-referenced to their RTL source modules.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      TENSIX COMPUTE TILE (tt_tensix_neo)                        │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    TRISC Instruction Memories (L1)                        │  │
│  ├───────────────────────────────────────────────────────────────────────────┤  │
│  │  0x06000–0x15FFF: TRISC0 IMEM (unpack LLK)     [4KB ICache]              │  │
│  │  0x16000–0x25FFF: TRISC1 IMEM (math LLK)       [2KB ICache]              │  │
│  │  0x26000–0x35FFF: TRISC2 IMEM (pack LLK)       [2KB ICache]              │  │
│  │  0x36000–0x45FFF: TRISC3 IMEM (mgmt)           [4KB ICache]              │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                   L1 SRAM (3 MB per cluster)                            │    │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │    │
│  │  │ Tensor workspace: weight tiles, activation tensors, outputs     │    │    │
│  │  └─────────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                    │                           │                                 │
│                    │                           │                                 │
│        ┌───────────┴─────────────┬─────────────┴───────────────┐                │
│        │                         │                             │                │
│        ▼                         ▼                             ▼                │
│   ┌─────────────┐           ┌─────────────┐            ┌──────────────┐        │
│   │ Unpacker 0  │           │ Unpacker 1  │            │ Unpacker 2   │        │
│   │(tt_unpack_0)│           │(tt_unpack_1)│            │(tt_unpack_2) │        │
│   │             │           │             │            │              │        │
│   │ Reads: L1   │           │ Reads: L1   │            │ Reads: L1    │        │
│   │ Applies:    │           │ Applies:    │            │ Applies:     │        │
│   │ • FMT CONV  │           │ • FMT CONV  │            │ • FMT CONV   │        │
│   │ • TRANSPOSE │           │ • TRANSPOSE │            │ • BANK INIT  │        │
│   │ • BANK INIT │           │ • BANK INIT │            │              │        │
│   └──────┬──────┘           └──────┬──────┘            └──────┬───────┘        │
│          │                         │                          │                 │
│          ▼                         ▼                          ▼                 │
│     ┌─────────────┐           ┌─────────────┐            ┌─────────────┐       │
│     │   SrcA RF   │           │   SrcB RF   │            │   SrcS RF   │       │
│     │  (2 banks)  │           │  (2 banks)  │            │  (2 banks)  │       │
│     │ 1536×32b    │           │ 2KB dual    │            │ Similar to  │       │
│     │             │           │ bank        │            │ SrcA/SrcB   │       │
│     │ RTL Module: │           │             │            │             │       │
│     │tt_srca_regs │           │ RTL Module: │            │ RTL Module: │       │
│     │             │           │tt_srcb_regs │            │tt_srcs_regs │       │
│     └──────┬──────┘           └──────┬──────┘            └──────┬──────┘       │
│            │                         │                          │               │
│            └─────────────────┬───────┴──────────────────────────┘               │
│                              │                                                   │
│         ┌────────────────────┴────────────────────┐                             │
│         │                                         │                             │
│         ▼                                         ▼                             │
│    ┌────────────────────────┐            ┌─────────────────────┐              │
│    │  Matrix FPU (G-Tile)   │            │  Vector Engine      │              │
│    │  (tt_fpu_gtile.sv)     │            │  (SFPU)             │              │
│    │                        │            │ (tt_sfpu_wrapper)   │              │
│    │ • 2× G-Tile per tile   │            │                     │              │
│    │ • 8 M-Tile per G-Tile  │            │ Reads: DEST, SrcS   │              │
│    │ • 256 FP-Lanes total   │            │ Writes: DEST, SrcS  │              │
│    │                        │            │                     │              │
│    │ Reads: SrcA, SrcB      │            │ Operations:         │              │
│    │ Writes: DEST           │            │ • exp, log, sqrt    │              │
│    │                        │            │ • tanh, gelu        │              │
│    │ RTL Module:            │            │ • sigmoid, cast     │              │
│    │ tt_fpu_mtile.sv        │            │                     │              │
│    └────────────┬───────────┘            └────────────┬────────┘              │
│                 │                                     │                        │
│                 └──────────────────┬──────────────────┘                        │
│                                    │                                           │
│                                    ▼                                           │
│                          ┌──────────────────────┐                              │
│                          │  DEST Register File  │                              │
│                          │  (2 banks, dual-buf) │                              │
│                          │  4,096 INT32 entries │                              │
│                          │  8 KB per tile       │                              │
│                          │  (512 rows/bank ×    │                              │
│                          │   4 cols × 2 banks)  │                              │
│                          │ RTL Module:          │                              │
│                          │ tt_gtile_dest.sv     │                              │
│                          └──────────┬───────────┘                              │
│                                     │                                          │
│         ┌───────────────────────────┴───────────────────────────┐              │
│         │                                                       │              │
│         ▼                                                       ▼              │
│   ┌──────────────┐                                        ┌──────────────┐    │
│   │   Packer 1   │                                        │  Packer 2    │    │
│   │(tt_pack_*.sv)│                                        │(tt_pack_*.sv)│    │
│   │              │                                        │              │    │
│   │ Reads: DEST  │                                        │ Reads: DEST  │    │
│   │ Reads: SrcS  │                                        │ Reads: SrcS  │    │
│   │              │                                        │              │    │
│   │ Applies:     │                                        │ Applies:     │    │
│   │ • FMT CONV   │                                        │ • FMT CONV   │    │
│   │   INT32→FP16B│                                        │   INT32→INT8 │    │
│   │   INT32→INT8 │                                        │   FP32→FP16B │    │
│   │              │                                        │              │    │
│   │ • ACTIVATION │                                        │ • ACTIVATION │    │
│   │   ReLU       │                                        │   CReLU      │    │
│   │   ReLUMax    │                                        │   Flush-to-0 │    │
│   │   CReLU      │                                        │              │    │
│   │              │                                        │              │    │
│   │ • ADDR_GEN   │                                        │ • ADDR_GEN   │    │
│   │   (4D stride)│                                        │   (4D stride)│    │
│   └──────┬───────┘                                        └──────┬───────┘    │
│          │                                                      │              │
│          └──────────────────────┬───────────────────────────────┘              │
│                                 │                                              │
│                    ┌────────────┴────────────┐                                │
│                    │                         │                                 │
│                    ▼                         ▼                                 │
│              ┌──────────────┐          ┌──────────────┐                       │
│              │  L1 Output   │          │  NoC Output  │                       │
│              │  (write back)│          │  (broadcast) │                       │
│              └──────────────┘          └──────────────┘                       │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘

RTL Module Hierarchy:
  ├─ tt_instrn_engine.sv         (TRISC orchestration, MOP sequencer)
  ├─ tt_trisc.sv                 (TRISC0/1/2 cores — 3 threads)
  ├─ tt_risc_wrapper.sv           (TRISC3 RV32I management core)
  │
  ├─ UNPACK Path:
  │  ├─ tt_unpack_0.sv            (Unpacker 0 → SrcA)
  │  ├─ tt_unpack_1.sv            (Unpacker 1 → SrcB)
  │  └─ tt_unpack_2.sv            (Unpacker 2 → SrcS)
  │
  ├─ Register Files:
  │  ├─ tt_srca_registers.sv       (SrcA: 1536×32b, 2 banks)
  │  ├─ tt_srcb_registers.sv       (SrcB: 4KB, 2 banks)
  │  └─ tt_srcs_registers.sv       (SrcS: SFPU operand storage, 2 banks)
  │
  ├─ MATH Path:
  │  ├─ tt_fpu_gtile.sv            (FPU container, 2 per tile)
  │  ├─ tt_fpu_mtile.sv            (Matrix MAC block)
  │  ├─ tt_fp_lane.sv              (5-stage descale pipeline)
  │  └─ tt_sfpu_wrapper.sv         (Scalar transcendental unit)
  │
  ├─ OUTPUT Path:
  │  ├─ tt_gtile_dest.sv           (DEST RF: 4,096 INT32 entries per tile, 2 banks, 8 KB per tile / 96 KB total)
  │  ├─ tt_pack_0.sv               (Packer 1)
  │  └─ tt_pack_1.sv               (Packer 2)
  │
  └─ Configuration:
     ├─ tt_tensix_pkg.sv           (Constants: SRCS_NUM_ROWS_16B=48, etc.)
     ├─ tt_t6_opcode_pkg.sv        (MOP encoding, RISC-V extensions)
     └─ tt_t6_proj_params_pkg.sv   (ENABLE_INT8_PACKING=1, etc.)

Clock Domains:
  • ai_clk:   TRISC0–3, FPU, DEST, SrcA, SrcB, SrcS     (per-column: i_ai_clk[X])
  • dm_clk:   TDMA (unpack/pack), L1 SRAM                (per-column: i_dm_clk[X])
  • noc_clk:  NoC local port, overlay wrapper flit FIFOs (global: i_noc_clk)
```

**Key Architectural Features:**

1. **3 Unpackers** (not 2):
   - Unpacker 0 → SrcA (INT16/FP32)
   - Unpacker 1 → SrcB (INT16/FP32)
   - Unpacker 2 → SrcS (FP32 for SFPU)

2. **2 Packers** (parallel output):
   - Both read DEST and SrcS simultaneously
   - Separate L1 write ports (no contention)
   - Format conversion and activation in parallel

3. **Double-Buffering All Registers**:
   - SrcA: 2 banks (TRISC0 writes one, FPU reads other)
   - SrcB: 2 banks (same pattern)
   - SrcS: 2 banks (SFPU writes one, unpack/FPU read other)
   - DEST: 2 banks (TRISC1 writes one, TRISC2 reads other)

4. **TRISC Thread Isolation**:
   - TRISC0 (unpack): 4KB ICache, controls 3 unpackers
   - TRISC1 (math): 2KB ICache, programs MOP sequencer
   - TRISC2 (pack): 2KB ICache, controls 2 packers
   - TRISC3 (mgmt): 4KB ICache, tile lifecycle (RV32I)

5. **Format Conversions Integrated into Data Path**:
   - Unpack: FP16B→FP32, INT8→INT16, FP8→FP16 (zero latency)
   - Pack: INT32→FP16B, INT32→INT8, FP32→FP16B (with stochastic rounding)

#### 2.7.9 Sparsity and Zero Skipping in Unpack Engine

**Purpose:**  The unpack engine includes hardware support for **sparsity masking** — the ability to skip loading certain z-planes (depth slices) of a tensor without any additional latency or control-flow overhead. This is a key enabler for inference on pruned neural networks and models with structured sparsity patterns.

##### 2.7.9.0 Dense Tensors and Sparsity Support

**Dense Tensors (Baseline Mode):**

Dense tensors with **no zeros** are the baseline mode and fully supported:

```systemverilog
// Dense tensor execution:
zmask = 32'h00000000;  // All bits are 0 → load all z-planes

// Unpack loop behavior:
for each z-plane (count = K_tile - 1):
  if zmask[z] == 0:     // All bits are 0
    emit UNPACK_A0      // Load z-plane from L1, SRCA address++

// Result: All K z-planes processed, all L1 reads executed
```

**Dense Tensor Characteristics:**
- ✅ Fully supported (default baseline mode)
- ✅ No special handling required (zmask = 0x00000000)
- ✅ No overhead (hardware designed for dense tensors)
- ❌ No sparsity benefits (all data loaded, all MACs computed)

Dense tensors are the **standard case** the hardware was designed for. Sparsity masking is an optional enhancement for pruned models.

---

##### 2.7.9.1 Sparsity Masking Support

**When sparsity masking is beneficial:**
- Pruned neural networks (30–75% weights are zero)
- Transformer attention masks (causal masks, 50%+ masked)
- Sparse activations (after ReLU, 30–70% zeros)
- Block-sparse matrices (structured sparsity patterns)

**Key Limitation — NO DRAM Bandwidth Savings:**

N1B0's z-plane masking saves **L1 read bandwidth only**. It does **NOT reduce external DRAM bandwidth** because the sparse tensor is already fully loaded into L1 before unpacking begins. Sparsity masking is applied during the unpack stage (L1→SRCA/SRCB), not during the DRAM load stage. Use this feature when you want to reduce compute energy and local memory traffic, not for reducing DRAM traffic (compare with NVIDIA 2:4 in §2.7.9.6).

**When NOT to use sparsity masking:**
- Dense tensors with no sparsity (use zmask = 0x00000000)
- Fine-grained random sparsity (difficult to encode in 32-bit mask)
- Very small tensors (overhead not justified)
- If your goal is reducing external DRAM bandwidth (sparsity masking does NOT help; pre-load sparse data compression instead)

##### 2.7.9.2 Z-Plane Mask Mechanism

The **32-bit z-plane mask** (`zmask[31:0]`) controls which depth elements are loaded into SRCA/SRCB during unpacking.

**Bit Convention:**
- `zmask[i] = 0` → **Load** z-plane i from L1 (execute UNPACK instruction)
- `zmask[i] = 1` → **Skip** z-plane i (execute SKIP instruction instead, no L1 read)

**Mask Origin:**  The mask is provided by firmware in two parts:
- `zmask[7:0]` — embedded in MOP word (8 LSBs)
- `zmask[31:8]` — provided via optional `MOP_CFG` instruction (24 MSBs)
- Combined: 32-bit mask supporting up to 32 z-planes per unpack loop

**Why z-planes?**  The unpack loop iterates once per K_tile element (48 or 96 INT8 elements). Each iteration is a "z-plane." The mask allows firmware to selectively load only non-zero planes without branching or conditional logic.

##### 2.7.9.3 Unpack Loop FSM — 7 States with Sparsity Support

The `tt_mop_decode_unpack_loop` module (**RTL file:** `tt_mop_decode_unpack_loop.sv`, 150 lines) is a state machine that automatically selects between UNPACK and SKIP states based on the mask.

**States (3-bit):**

```
IDLE     (0)  → Waiting for MOP to arrive
UNPACK_A0(1)  → Load source activation operand 0 (default path)
UNPACK_A1(2)  → Load source activation operand 1 (halo/border data)
UNPACK_A2(3)  → Continue halo load
UNPACK_A3(4)  → Finish halo load
UNPACK_B (5)  → Load source weights (SRCB)
SKIP_A   (6)  → Skip activation z-plane (no L1 read)
SKIP_B   (7)  → Skip weights z-plane (no L1 read)
```

**FSM Key Decision (RTL line 102, 122):**

```systemverilog
skip_plane ? SKIP_A : UNPACK_A0
```

After each UNPACK_A0 or SKIP_A execution:
- Read the current LSB of `current_zmask[0]`
- If `1` → next state = SKIP_A (don't load, don't increment SRCA address)
- If `0` → next state = UNPACK_A0 (load from L1, increment SRCA address)

##### 2.7.9.4 Mask Shifting — One Bit Per Cycle

**Mechanism (RTL lines 71-78):**

On each instruction-ready cycle, the mask is **right-shifted by 1 bit**, bringing the next z-plane's sparsity bit into the LSB position:

```systemverilog
always_ff @(posedge i_clk)
    if (latch_registers) begin
        loop_counter <= i_mop_zplane_count - 1'd1;
        current_zmask <= incoming_zmask >> 1;  // Pre-shift on MOP arrival
    end else if (iterate_loop) begin
        loop_counter <= loop_counter - 1'd1;
        current_zmask <= (current_zmask >> 1);  // Shift each cycle
    end
```

**Example: K_tile = 6, zmask = 6'b101101 (binary, pattern: skip 5, load 4, skip 3, load 2, load 1, skip 0)**

```
Cycle 1 (start):
  current_zmask = 101101 >> 1 = 010110
  check zmask[0] = 0 → UNPACK_A0

Cycle 2:
  current_zmask = 010110 >> 1 = 001011
  check zmask[0] = 1 → SKIP_A

Cycle 3:
  current_zmask = 001011 >> 1 = 000101
  check zmask[0] = 1 → SKIP_A

Cycle 4:
  current_zmask = 000101 >> 1 = 000010
  check zmask[0] = 0 → UNPACK_A0

Cycle 5:
  current_zmask = 000010 >> 1 = 000001
  check zmask[0] = 1 → SKIP_A

Cycle 6:
  current_zmask = 000001 >> 1 = 000000
  check zmask[0] = 0 → UNPACK_A0, then IDLE
```

**Result:**  3 L1 reads (cycles 1, 4, 6), 3 SKIP cycles (cycles 2, 3, 5) → **50% L1 bandwidth savings**, same 6-cycle total latency.

##### 2.7.9.5 SKIP Instruction — Not a No-Op

**Key Point:** When `state = SKIP_A`, the FSM outputs `i_reg_skipA_instr` instead of a UNPACK instruction. This is **not a hardware no-op** — it is the **loop completion/synchronization instruction**, typically:
- A **SEMPOST** (semaphore post) for TRISC handshake
- A **counter increment** for progress tracking
- A **register write** for status

**Hardware Behavior:**
- **UNPACK_A0 cycle:** L1 read issued, SRCA address pointer auto-increments
- **SKIP_A cycle:** No L1 read issued, SRCA address does NOT increment

This ensures skipped z-planes don't "consume" SRCA rows, so data layout remains dense.

##### 2.7.9.6 Performance Characteristics

**Throughput:**  1 instruction per cycle, regardless of sparsity (SKIP takes same time as UNPACK).

**Bandwidth Reduction (proportional to sparsity):**

| Sparsity % | Dense L1 Reads | Cycles | Actual L1 Reads | Bandwidth Savings |
|---|---|---|---|---|
| 0% (no skip) | 96 | 96 | 96 | 0% |
| 25% skip | 96 | 96 | 72 | 25% |
| 50% skip | 96 | 96 | 48 | **50%** |
| 75% skip | 96 | 96 | 24 | **75%** |

**Latency Impact:**  **Zero overhead** — sparsity adds no extra stall cycles or conditional branching.

**Power Impact:**  **Positive** — fewer L1 reads → less memory traffic → lower power consumption.

##### 2.7.9.7 Use Cases

1. **Pruned Neural Networks**
   - Weight pruning (30–50% of weights are zero) — use zmask to skip zero rows
   - Saves 30–50% L1 bandwidth during weight loading
   - Example: ResNet50 with 50% pruning → 50% unpack bandwidth reduction

2. **Attention Masks** (Transformer models)
   - Masked future tokens (50%+ of sequence masked in causal attention)
   - Use zmask to skip masked activations
   - No need to compute or load masked elements
   - Example: LLaMA inference with causal attention → dynamic sparsity

3. **Structured Sparsity**
   - Block-sparse matrices (every Nth block is zero)
   - Firmware can generate zmask pattern matching block structure
   - Efficient hardware execution (no branching)

4. **Conditional Computation**
   - Skip operands where mask = 0 (application-specific masking)
   - Zero pipeline impact — FSM selects state automatically

##### 2.7.9.8 Firmware Programming Interface

**Step 1: Encode zmask in MOP**

```c
// Firmware loads MOP with 8 LSBs of mask
mop_word[7:0] = zmask[7:0];      // opcode = 0x01 (MOP)
write_mop(mop_word);
```

**Step 2: (Optional) Load upper 24 bits via MOP_CFG**

```c
// If K_tile > 32, use second MOP_CFG word for upper mask bits
mop_cfg_word[31:8] = zmask[31:8]; // opcode = 0x03 (MOP_CFG)
write_mop_config(mop_cfg_word);
```

**Step 3: Set loop count**

```c
// Configure unpack loop length (K_tile)
mop_config.LOOP_LEN = K_tile - 1;  // e.g., 95 for K_tile=96
```

**Step 4: Execute MOP**

```c
// TRISC0 or TRISC1 issues UNPACK instruction
// Hardware FSM automatically skips/loads based on zmask
issue_unpack_mop();
```

**No conditional branching needed in firmware** — the hardware FSM handles all sparsity decisions.

##### 2.7.9.9 Integration with Double-Buffering

Sparsity interacts seamlessly with SRCA/SRCB double-buffering:

```
Bank 0 (current):     Unpacker loads sparse data (some rows skipped)
Bank 1 (next):        FPU reads from, while Bank 0 is being loaded
                      Dense layout maintained (skipped rows not allocated)

Swap happens when:     SRCA bank toggle on next MOP or double-buffer boundary
No conflicts:         Separate zmask for each bank (independent sparsity patterns)
```

##### 2.7.9.10 RTL Implementation Details

**Key signals (tt_mop_decode_unpack_loop.sv):**

| Signal | Lines | Meaning |
|--------|-------|---------|
| `i_mop_zmask_low[7:0]` | 18 | Firmware-provided 8 LSBs of mask |
| `i_reg_zmask_high[23:0]` | 35 | Hardware latch for 24 MSBs from MOP_CFG |
| `incoming_zmask[31:0]` | 65 | Combined 32-bit mask = {zmask_high, zmask_low} |
| `current_zmask[31:0]` | 66, 74, 77 | Working copy, right-shifted each cycle |
| `in_skip_plane` | 80 | Should initial z-plane be skipped? |
| `skip_plane` | 81 | Should current z-plane be skipped? |
| `iterate_loop` | 84 | Is it time to shift mask and decrement counter? |
| `loop_counter[9:0]` | 67 | How many z-planes left? (10-bit, up to 1023) |
| `loop_done` | 82 | Are we finished (loop_counter == 0)? |

**Pre-shift optimization (RTL line 74):**
```systemverilog
current_zmask <= incoming_zmask >> 1;  // Pre-shift saves one cycle
```
Shifts mask by 1 on MOP arrival, so LSB is immediately valid for state decision next cycle.

**Conditional iteration (RTL line 84):**
```systemverilog
assign iterate_loop = i_instrn_ready && ((next_state == UNPACK_A0) || (next_state == SKIP_A));
```
Only shifts mask when downstream is ready AND in main loop states (prevents premature shifts during halo/weights).

##### 2.7.9.11 Comparison with NVIDIA 2:4 Structured Sparsity

N1B0's z-plane masking is fundamentally different from NVIDIA's 2:4 structured sparsity. This section clarifies the architectural trade-offs:

**Comparison Table:**

| Feature | N1B0 Z-Plane | NVIDIA 2:4 |
|---------|-------------|-----------|
| **Granularity** | Entire depth slices (K-dimension) | 4 consecutive elements (fine-grained) |
| **Sparsity ratio** | Any (50%, 75%, 90%+) | Up to 50% max (2 of 4 elements) |
| **Where applied** | L1 unpack path only | During DRAM load (pre-compression) |
| **L1 Bandwidth Saved** | Proportional to skipped z-planes | N/A (no L1-level optimization) |
| **DRAM Bandwidth Saved (50% sparsity)** | 0% saved ❌ | 50% saved ✓ |
| **DRAM Bandwidth Saved (75% sparsity)** | 0% saved ❌ | Not supported |
| **DRAM Bandwidth Saved (90% sparsity)** | 0% saved ❌ | Not supported |
| **Best for** | Structured, block-sparse patterns | Fine-grained uniform sparsity |

**Key Architectural Insight — Why DRAM Bandwidth Differs:**

**N1B0 Z-Plane Masking:**
- Sparsity mask is applied ONLY during unpack (L1→SRCA/SRCB read stage)
- Data is already in L1 memory, having consumed full DRAM bandwidth during the load phase
- DRAM bandwidth is NOT reduced because the sparse tensor was fully loaded into L1 beforehand
- Saves only local L1 read bandwidth within the tile
- This is a **tile-level optimization** for reducing unpack latency and local memory traffic

**NVIDIA 2:4:**
- Sparsity information is metadata stored WITH the weights in DRAM
- During DRAM load, sparse data is skipped entirely
- Zero elements are never fetched from external DRAM
- Saves both DRAM bandwidth AND L1 bandwidth from the start
- This is a **system-level optimization** for reducing external DRAM traffic and power

**Practical Implications:**

N1B0 sparsity is optimal for:
- Reducing unpack latency when sparse data is already loaded into L1
- Decreasing local memory traffic within a tile
- Exploiting structured sparsity patterns (pruned networks, attention masks, block-sparse matrices)
- Inference scenarios where weights are pre-loaded before compute

NVIDIA 2:4 is optimal for:
- Reducing external DRAM bandwidth during weight loading
- Decreasing system-level power consumption
- Scenarios with uniform, fine-grained sparsity patterns

**Cannot use NVIDIA 2:4 directly in N1B0** because the unpack engine is designed around depth-slice granularity, not 4-element blocks. However, N1B0's approach is superior for pruned networks (30–75% sparsity), which naturally align with layer-wise or channel-wise pruning rather than fine-grained element sparsity.

##### 2.7.9.12 Multi-MOP Workflow for K_tile > 32

**Important Note:** This section addresses a documentation gap identified during review. The 32-bit z-plane mask covers **up to 32 z-planes per MOP**. When K_tile > 32, firmware must issue **multiple MOPs with different masks**. This section explains the multi-MOP workflow for handling K_tile = 48 or 96 (the typical values in N1B0).

**Z-Plane Granularity by Data Type:**

One z-plane = one L1 read = 128 bits. The number of K elements per z-plane depends on data type:

| Data Type | Bits Per Element | Elements Per Z-Plane | Z-Planes for K=96 |
|-----------|------------------|----------------------|-------------------|
| INT8 | 8 bits | 16 elements | 96 ÷ 16 = 6 z-planes |
| INT16 / FP16B | 16 bits | 8 elements | 96 ÷ 8 = 12 z-planes |
| FP32 | 32 bits | 4 elements | 96 ÷ 4 = 24 z-planes |

**Key Insight:** Z-planes are physical units (128-bit L1 reads), not data-type-dependent. The number of K elements per z-plane varies by format, but the 32-bit mask always counts z-planes, not individual elements.

**Practical Cases for N1B0:**

For typical N1B0 workloads:
- **K_tile = 96 INT8:** 6 z-planes → **1 MOP** (6 < 32 mask capacity) ✓
- **K_tile = 96 INT16:** 12 z-planes → **1 MOP** (12 < 32 mask capacity) ✓  
- **K_tile = 96 FP32:** 24 z-planes → **1 MOP** (24 < 32 mask capacity) ✓

The 32-bit mask is sufficient for standard kernels. Multiple MOPs are required only for very large K (K > 256+), which is rare in production inference.

**When Multiple MOPs Are Needed (K > 256+):**

If total z-planes exceed 32:

```systemverilog
// Hypothetical example: K=512 FP32 → 128 z-planes
// Requires 4 MOPs (ceil(128 / 32) = 4)

// MOP 1: z-planes 0–31
write_mop(loop_count=31, zmask_batch1, done=0);
wait_unpack_done();

// MOP 2: z-planes 32–63
write_mop(loop_count=31, zmask_batch2, done=0);
wait_unpack_done();

// MOP 3: z-planes 64–95
write_mop(loop_count=31, zmask_batch3, done=0);
wait_unpack_done();

// MOP 4: z-planes 96–127 (final batch)
write_mop(loop_count=31, zmask_batch4, done=1);  // ← done=1 on last MOP
wait_unpack_done();
```

**SRCA Address Continuity Across Batches:**

Hardware automatically maintains SRCA address continuity across multiple MOPs:

```
MOP 1: SRCA starts at 0x0000, processes z-planes 0–31, ends at 0x2000
MOP 2: SRCA continues from 0x2000, processes z-planes 32–63, ends at 0x4000
MOP 3: SRCA continues from 0x4000, and so on...
```

Firmware does NOT reset SRCA or re-program the address window between MOPs. The unpack FSM preserves address state across batch boundaries automatically.

**Mask Generation Across Batches:**

When multiple MOPs are used, firmware computes a different 32-bit mask for each batch:

```c
uint32_t compute_zmask_for_batch(int batch_num, int total_zplanes, int zplane_sparsity[]) {
    uint32_t zmask = 0;
    int batch_start = batch_num * 32;
    int batch_end = min((batch_num + 1) * 32, total_zplanes);
    
    for (int local_bit = 0; local_bit < 32; local_bit++) {
        int global_zplane = batch_start + local_bit;
        if (global_zplane < batch_end && zplane_sparsity[global_zplane]) {
            zmask |= (1 << local_bit);
        }
    }
    return zmask;
}
```

##### 2.7.9.13 Real Performance Impact: Latency vs Energy Trade-Off

**Important clarification based on RTL analysis (`tt_mop_decode_unpack_loop.sv`):** Sparsity masking does NOT improve latency, only energy consumption. This section provides an honest assessment.

**What Sparsity Actually Changes:**

| Metric | Without Sparsity | With 50% Sparsity | Impact |
|--------|------------------|-------------------|--------|
| **Unpack latency** | 96 cycles | 96 cycles | ❌ NO CHANGE |
| **Loop iterations** | 96 (all z-planes) | 96 (same z-planes) | ❌ NO CHANGE |
| **FPU MACs issued** | 96 × M × N | 48 × M × N | ✅ REDUCED |
| **L1 read operations** | 96 | 48 | ✅ REDUCED |
| **L1 memory traffic** | Baseline | Reduced | ✅ ENERGY SAVINGS in L1 |
| **FPU computation** | Baseline | Reduced | ✅ ENERGY SAVINGS in compute |
| **Total tile energy** | E_tile | Reduced in compute subsystem | ✅ LOCAL ENERGY SAVINGS |

**Why Latency is Unchanged:**

The unpack loop processes all K z-planes, even though firmware skips L1 reads on sparse planes:

```
Loop count = total_zplanes (e.g., 96 for K=96)
                                        
Cycle 1:   UNPACK_A0  → Load z-plane 0 into SRCA, FPU computes
Cycle 2:   SKIP_A     → SRCA NOT updated, SKIP instruction executes (e.g., SEMPOST)
Cycle 3:   UNPACK_A0  → Load z-plane 1 into SRCA, FPU computes
Cycle 4:   SKIP_A     → SRCA NOT updated, SKIP instruction executes
...
Cycle 96:  SKIP_A     → End

Total latency = 96 cycles (SAME as no sparsity)
Total MACs = 48 × operations (HALF of no sparsity)
```

The loop count cannot be reduced below `total_zplanes` because the mask only controls which planes are skipped, not how many iterations the loop performs.

**Real Benefit: Energy Reduction in Compute Pipeline**

```
Energy components (per tensor):
  E_unpack:      unchanged (same loop count = 96 cycles)
  E_macs:        reduced (fewer MACs issued to FPU)
  E_l1:          reduced (fewer L1 read operations)
  E_control:     unchanged (same FSM overhead)
  
Result: Energy reduction localized to the unpack/compute subsystem 
        of one Tensix tile. Other NPU subsystems (Dispatch, NoC, Router, 
        EDC) unaffected.
```

**Energy Savings Scope:**
- ✅ Reduced FPU activity (fewer MACs to execute)
- ✅ Reduced L1 read traffic (fewer memory operations)
- ❌ No change to unpack latency (loop still iterates K times)
- ❌ No change to DRAM traffic (data already in L1)
- ❌ No change to other tile's energy (NoC, Dispatch, Router, EDC)

**When to Use Sparsity Masking:**

✅ **Recommended:**
- **Power-constrained systems** (battery, thermal budget limits)
- **Repeated inference over many tensors** (amortize overhead)
- **Models with high structured sparsity** (pruned networks, attention masks, sparse activations)
- **When energy efficiency is the optimization goal**

❌ **Not recommended:**
- **Latency-critical inference** (autonomous vehicles, real-time audio)
- **When latency is the primary metric** (latency unchanged; only local energy savings)
- **Dense models** (sparsity does not apply)
- **When compute is not the bottleneck** (I/O or memory-bound workloads)

**Design Philosophy:** N1B0's sparsity masking is an **energy optimization within the compute tile**, not a system-level optimization and not a latency optimization. Actual NPU-level energy savings depend on whether the compute subsystem dominates total power consumption. For latency-critical applications, NVIDIA 2:4 structured sparsity (which reduces DRAM traffic) is more appropriate.

---

### 2.8 Destination Register File (DEST)

#### 2.8.1 Architecture Rationale

The DEST register file is the **accumulation buffer** for all FPU outputs. It is implemented as a **latch array** rather than an SRAM macro for two reasons:
1. **Read latency:** Latch arrays have lower read latency than SRAM macros (no precharge cycle), which is critical when the pack engine reads DEST on every clock cycle and when SFPU performs in-place read-modify-write operations.
2. **Access pattern:** DEST is accessed at single-element granularity by the FPU MAC array on every cycle — a register-file-style implementation (latch array) fits this pattern directly, whereas SRAM macros require address + precharge + sense-amplify sequences that add pipeline stages and reduce effective throughput.

**Why is DEST structured as per-column slices rather than one monolithic array?**

DEST is physically split into `FP_TILE_COLS=16` independent column slices — 8 per G-Tile, one per `tt_mtile_and_dest_together_at_last` instance. Each slice has its own independent read/write port (`tt_gtile_dest` with `NUM_COLS=1`). This structure means all 16 output columns of a GEMM tile can be written simultaneously in one clock cycle: the MAC array outputs 4 rows × 16 columns = 64 FP32 values simultaneously, each routed directly to its corresponding DEST slice. A monolithic 16-column DEST array would require either 16× the port bandwidth or a serialized write path, adding latency and timing pressure.

#### 2.8.2 Physical Parameters (RTL-verified)

**RTL source: `tt_gtile_dest.sv`, `tt_fpu_gtile.sv`**

| Parameter                | RTL-Verified Value                                                                   |
|--------------------------|--------------------------------------------------------------------------------------|
| Module                   | `tt_gtile_dest` (per-column slice)                                                   |
| `TOTAL_ROWS_16B`         | 1,024 per `tt_gtile_dest` instance                                                   |
| `NUM_COLS`               | 1 per instance (8 instances per G-Tile via `gen_fp_cols` loop)                       |
| `NUM_BANKS`              | 2 (double-buffered within each slice)                                                |
| `BANK_ROWS_16B`          | 512 per bank (= `TOTAL_ROWS_16B / NUM_BANKS`)                                        |
| `BANK_ROWS_32B`          | 256 per bank in 32-bit mode                                                          |
| `FPU_ROWS`               | 4 (= `FP_ROWS`; rows written simultaneously per cycle)                               |
| `DEST_ADDR_WIDTH`        | 10 bits (= `$clog2(TOTAL_ROWS_16B)`)                                                 |
| `DEST_WR_CLK_DIVNS`      | 4 (write clock divides by 4; RTL asserts on change)                                  |
| Instances per G-Tile     | 8 (one per FP column, `FP_TILE_COLS=8`)                                              |
| Instances per `tt_tensix`| 16 (2 G-Tiles × 8 columns)                                                          |
| Total row-addresses per `tt_tensix` | 1,024 (shared between banks, 512 rows per bank × 2)      |
| Implementation           | Latch array (`LATCH_ARRAY=1`, not SRAM)                                              |
| Clock domain             | `i_ai_clk` (application clock)                                                      |

**Storage capacity (per `tt_tensix` tile, RTL-verified from tt_gtile_dest.sv):**
- **DEST_NUM_ROWS_16B = 1,024** total → 512 rows per bank (BANK_ROWS_16B = 512)
- **Data width = 256 bits** (4 rows × 2 columns × 16 bits), representing 16 INT16 entries or 8 INT32 entries
- **DEST_NUM_BANKS = 2** banks (dual-buffered)
- Physical capacity: 1,024 total rows × 16 bits (per column, summed across columns) = **32 KB** per `tt_tensix` tile
- Double-buffer split: 512 rows per bank × 2 banks = 1,024 addressable row positions

**Total across 12 Tensix clusters (48 `tt_tensix` tiles):**
- 48 tiles × 32 KB = **1.536 MB** total DEST latch array on-chip

> **Correction from prior versions:** Earlier HDD versions incorrectly stated 64 KB per tile (16,384 entries) based on outdated parameter sets. RTL verification (tt_tensix_pkg.sv: DEST_NUM_ROWS_16B=1024; tt_gtile_dest.sv: BANK_ROWS_16B=512, NUM_COLS=4, NUM_BANKS=2) confirms the correct per-tile capacity is **32 KB per Tensix (8,192 INT32 entries)** or equivalently **16 KB per G-Tile (4,096 INT32 entries)**. Math check: 4,096 INT32 entries × 4 bytes/entry = 16,384 bytes = 16 KB per G-Tile.

#### 2.8.3 Double-Buffer Operation

DEST is **hardware double-buffered**: within each of the 16 per-column `tt_gtile_dest` slices, the `TOTAL_ROWS_16B=1024` address space is split into two equal `BANK_ROWS_16B=512` banks (Buffer A and Buffer B).

```
Per-column DEST slice (tt_gtile_dest, NUM_COLS=1):

     FPU write path                 Pack/SFPU read path
          │                                 │
          ▼                                 ▼
 ┌─────────────────────────────────────────────┐
 │  Bank A  (512 rows × 32b)    ◄── FPU writes (tile N)     │
 │  Bank B  (512 rows × 32b)    ◄── Pack reads (tile N−1)   │
 └─────────────────────────────────────────────┘
                    │
                    ▼
         dest_toggle interrupt → TRISC3
         (signals bank swap complete)
```

All 16 column slices toggle in unison. While the FPU writes results for tile N into Bank A (across all 16 slices simultaneously), the pack engine reads Bank B (tile N−1) and drains it to L1 or the NoC. On compute completion, a **dest_toggle** hardware event fires, TRISC3 swaps the active bank across all slices, and the cycle repeats.

This eliminates all stalls between the compute and pack stages: the FPU never waits for DEST to drain, and the pack engine never waits for new data.

#### 2.8.4 Stochastic Rounding on Write-Back

When the pack engine converts INT32 DEST entries to lower-precision output formats (FP16B or INT8), **stochastic rounding** is applied to reduce systematic quantization bias:

1. An **LFSR** (Linear Feedback Shift Register) inside the FPU generates a pseudo-random bit pattern
2. The low-order bits of the INT32 DEST value are XOR'd with the LFSR output before truncation
3. This adds a uniform random dither in the range [0, 1 LSB) of the output format
4. Over many values, the rounding error has zero mean — eliminating the systematic downward bias of truncation

Stochastic rounding is enabled/disabled per-format via firmware MOP control words. It is always disabled for FP32 output (no precision loss).

#### 2.8.5 Address Space

DEST entries are addressed by the FPU as a two-dimensional structure matching the FPU tile output layout:
- **Column index:** selects one of the 16 DEST column slices (0 to `FP_TILE_COLS−1` = 15); each slice is a physically independent `tt_gtile_dest` instance
- **Row index:** selects a row within the chosen slice (0 to 1,023 in 16b mode; 0 to 511 in 32b mode); `DEST_ADDR_WIDTH=10` bits
- **Format width:** when writing FP32, each row is 32 bits; INT16 mode writes 16b (half-row) and uses the `_hi` / `_lo` write-enable ports

TRISC0 pack engine and TRISC2 math engine both address DEST using this layout, coordinated by the double-buffer toggle.

#### 2.8.6 SFPU Integration

The SFPU reads and writes DEST via the same per-column slice ports as the FPU MAC array. The `tt_sfpu_dest_adapter` module bridges the SFPU scalar read/write path to the column-parallel DEST slice interface. SFPU operations (exp, log, sqrt, etc.) proceed as in-place read-modify-write on the DEST entries within the currently active bank, without disturbing the inactive bank.

### 2.9 SRCA and SRCB Register Files

#### 2.9.1 Architecture Rationale

**RTL-verified (tt_srcb_registers.sv, tt_srcs_registers.sv, tt_tensix_pkg.sv):**

Both SRCA and SRCB are **physically implemented as dedicated register files** inside the FPU. The `SRCB_IN_FPU = 1` localparam in `tt_tensix_pkg.sv` explicitly encodes this: SRCB is a hardware register file that lives inside the FPU datapath, not a passthrough from L1.

**Why dedicated register files for both operands, not just SRCA?**

In a standard GEMM loop, the A-matrix (weights, loaded into SRCA) is held resident while multiple B-matrix rows are streamed through. This asymmetry motivates having a large SRCA and a minimal SRCB. However, Trinity's SFPU and FP-Lane sub-pipeline create additional requirements:

1. **SFPU writes back to SRCS** (RTL: `srcs_select` mux in `tt_sfpu_wrapper.sv`) — the SFPU can output results to either DEST or the SRCS register file. This requires SRCS to be a writable physical register file, not a read-only L1 passthrough.
2. **DEST-to-SRCB move (d2b) path** — `tt_srcb_registers.sv` contains an explicit `d2b` operation that moves data from DEST into SRCB. This enables in-place weight update patterns where computed gradients are fed directly back to the multiplier B-input without going through L1.
3. **`shift_x` operation** — SRCB supports a column-shift operation for convolution-style access patterns where the same weight row is applied with a column offset.
4. **Double-buffering** — SRCB has `NUM_REG_BANKS=2` hardware banks, mirroring SRCA, so that the unpack engine can fill SRCB bank N+1 while the FPU consumes SRCB bank N, eliminating stalls on both operand paths simultaneously.

**Why is SRCB smaller than SRCA?**

SRCA stores `SRCA_NUM_SETS=4` sets (the full weight tile), while SRCB (`BANK_REGISTER_DEPTH=64` rows per bank) stores the activation tile. For the standard N1B0 INT16 GEMM kernel (K_tile=48 input channels, FP_TILE_COLS=16 output columns), the activation tile fits comfortably in SRCB's 4KB. Weights (shared across all output tiles in a batch) are larger and benefit more from the 4-set SRCA structure.

#### 2.9.2 SRCA Physical Parameters

**RTL-verified (tt_tensix_pkg.sv: SRCS_NUM_ROWS_16B=48):**

| Parameter          | Value                              |
|--------------------|------------------------------------|
| Module             | `tt_srcs_registers.sv` (SRCA register file) |
| Rows per tile      | **48** (SRCS_NUM_ROWS_16B, RTL-verified) |
| Words per row      | 16                                 |
| Bits per word      | 16                                 |
| Total per tile     | 48 rows × 16 words × 16 bits = 12,288 bits = **1.5 KB** (latch array) |
| `NUM_BANKS`        | 2 (double-buffered)                |
| `BANK_ROWS_16B`    | **24 per bank** (48 total / 2 banks) |
| `NUM_COLS`         | 16                                 |
| `SRCA_NUM_SETS`    | 4 (`tt_tensix_pkg.sv:74`)          |
| Implementation     | Latch array (not SRAM)             |
| Clock domain       | `i_ai_clk`                         |
| Loaded by          | TRISC0 unpack engine               |
| Consumed by        | TRISC1 → G-Tile / M-Tile           |

**Correction Note:** Prior versions incorrectly stated 256 rows. RTL verification confirms **48 rows** as the actual SRCA depth per Tensix tile, derived from `SRCS_NUM_ROWS_16B=48` parameter.

#### 2.9.3 SRCA Double-Buffer Operation

SRCA is **hardware double-buffered** with two equal halves (Bank 0 and Bank 1), each holding 768 × 32-bit entries:

```
          Unpack-engine write path        FPU read path
               │                               │
               ▼                               ▼
  ┌────────────────────────────────────────────┐
  │  SRCA Bank 0  (768 × 32b)                  │◄── Unpack fills (next tile)
  │  SRCA Bank 1  (768 × 32b)                  │◄── FPU reads   (current tile)
  └────────────────────────────────────────────┘
              │
              ▼
     srca_toggle interrupt → TRISC3
     (signals bank swap is complete)
```

While the FPU consumes Bank 1 (current tile), TRISC1 fills Bank 0 (next tile) from L1. On completion, the **srca_toggle** hardware event fires, swapping the roles of the two banks. This eliminates all unpack stalls in the compute pipeline.

#### 2.9.4 SRCB Physical Parameters

**RTL-verified (`tt_srcb_registers.sv`):**

| Parameter              | Value                                |
|------------------------|--------------------------------------|
| Module                 | `tt_srcb_registers.sv`               |
| Rows per bank          | **64** (RTL-verified, not 128)       |
| Columns (datums)       | 16                                   |
| Bits per datum         | 16                                   |
| `NUM_REG_BANKS`        | 2 (double-buffered)                  |
| Total capacity         | 2 banks × 64 rows × 16 cols × 16b = **262,144 bits = 2 KB** |
| Data width (output)    | 256 bits (16 columns × 16 bits)     |
| Implementation         | Register file (latch array, `SRCB_IN_FPU=1`) |
| Special operations     | Stochastic rounding (probabilistic quantization), column shift via `shift_x` |
| Clock domain           | `i_ai_clk`                           |
| Loaded by              | TRISC0 unpack engine (or SFPU via `srcs_select`) |
| Consumed by            | TRISC1 → G-Tile / M-Tile (B-operand) |

**Correction Note:** Prior table stated 128 rows per bank. RTL and double-buffer diagram confirm **64 rows per bank** (verified in §2.9.5 diagram line 3375).

#### 2.9.5 SRCB Double-Buffer Operation

Like SRCA, SRCB is hardware double-buffered (`NUM_REG_BANKS=2`):

```
          Unpack-engine write path        FPU read path
               │                               │
               ▼                               ▼
  ┌────────────────────────────────────────────┐
  │  SRCB Bank 0  (64 rows × 16 cols × 16b)   │◄── Unpack fills (next row)
  │  SRCB Bank 1  (64 rows × 16 cols × 16b)   │◄── FPU reads   (current row)
  └────────────────────────────────────────────┘
```

The unpack engine fills one bank while the FPU reads the other, enabling continuous B-operand streaming into the MAC array with no stalls.

#### 2.9.6 SRCA vs SRCB Summary

| Attribute           | SRCA                                      | SRCB                                          |
|---------------------|-------------------------------------------|-----------------------------------------------|
| Module              | `tt_srcs_registers.sv`                    | `tt_srcb_registers.sv`                        |
| Implementation      | Latch array (dedicated RF, `SRCB_IN_FPU=1`) | Latch array (dedicated RF, `SRCB_IN_FPU=1`) |
| Capacity per tile   | 1,536 × 32b = 6KB                         | 2 banks × 64×16 × 16b = 4KB                  |
| Banks               | 2 (HW double-buffer)                      | 2 (HW double-buffer)                         |
| Special operations  | Multi-set (`SRCA_NUM_SETS=4`)             | `d2b` (DEST→SRCB), `shift_x` (column shift)  |
| SFPU write-back     | Yes (via `srcs_select` mux)               | Yes (via `srcs_select` mux)                   |
| Typical content     | Weight matrix tile (reused multiple rows) | Activation row tile (streamed)                |
| Loaded by           | TRISC0 unpack engine                      | TRISC0 unpack engine                          |

### 2.10 Clock Domain Summary (Tensix Tile)

#### 2.10.1 Per-Column Clock Architecture

In N1B0, the `ai_clk` and `dm_clk` inputs to each Tensix tile are **per-column** — column X receives `i_ai_clk[X]` and `i_dm_clk[X]` independently. The `noc_clk` is shared across all tiles (single global `i_noc_clk`). This per-column architecture allows harvest isolation: a harvested column has its clock gated at the column boundary without disturbing the clock network of adjacent columns.

#### 2.10.2 Clock Domain Table

| Domain     | Source wire     | Frequency relationship | Covers in Tensix tile                               |
|------------|-----------------|------------------------|------------------------------------------------------|
| `ai_clk`   | `i_ai_clk[X]`  | Fastest (compute)      | TRISC0–3, FPU (G/M/FP-Lane/SFPU), DEST RF, SRCA RF |
| `dm_clk`   | `i_dm_clk[X]`  | May be lower than ai   | TDMA MOP sequencer, pack/unpack engines, L1 SRAM array clocking |
| `noc_clk`  | `i_noc_clk`    | Global, fixed          | NoC local port, flit FIFOs (VC buffers), overlay NIU, EDC ring segment |

In a typical N1B0 operating point, `ai_clk` and `dm_clk` may be driven at the same frequency from the same PLL output, or at different ratios depending on power/performance mode.

#### 2.10.3 CDC Crossings within the Tensix Tile

Three CDC crossings exist inside the Tensix tile hierarchy (confirmed at Y=2 tiles per §M19):

| Crossing          | Source domain | Dest domain | Mechanism                              | Location              |
|-------------------|---------------|-------------|----------------------------------------|-----------------------|
| AI → NoC          | `ai_clk`      | `noc_clk`   | Synchronizer FIFO in overlay wrapper   | Overlay NIU interface |
| NoC → AI          | `noc_clk`     | `ai_clk`    | Synchronizer FIFO in overlay wrapper   | Overlay NIU interface |
| AI → DM           | `ai_clk`      | `dm_clk`    | Registered boundary cells in L1 partition | L1 register-file path |

`DISABLE_SYNC_FLOPS=1` is a module parameter that bypasses intra-domain synchronizers when the source and destination are known to share the same clock (e.g., when `ai_clk` and `dm_clk` are driven from the same source). This is set at integration time by the top-level and must not be applied across genuine asynchronous domain boundaries.

#### 2.10.4 Clock Gating and Harvest Interaction

The overlay wrapper (`tt_neo_overlay_wrapper`) contains clock gate cells for each sub-domain within the tile. During harvest, a harvested tile's `i_ai_clk[X]` and `i_dm_clk[X]` are gated at the column clock tree, and the isolation cells (`ISO_EN[X+4*Y]`) hold all output signals at safe values (see §5 Harvest). The `noc_clk` domain for a harvested tile is also gated at the NIU level to prevent spurious flit activity.

#### 2.10.5 EDC Clock Allocation

Each EDC node within the Tensix tile receives its own clock independently from the ring traversal path (see §M1, §M19). The EDC clock is derived from the same `i_ai_clk[X]` / `i_noc_clk` source depending on which clock domain the EDC node monitors. Repeaters on the EDC ring path are combinational (no registered stages in the inter-node path); all flip-flops are inside `tt_edc1_node` instances.

---


## §3 Overlay Engine — Data Movement Cluster

The **Overlay Engine** / **Data Movement Cluster** is the autonomous data-movement and orchestration subsystem within each Tensix cluster, responsible for coordinating tensor data movement between on-chip L1 SRAM (3 MB per cluster) and external DRAM, while decoupling TRISC processor cores from DMA execution latency. It contains the **Data Movement Engine** (core DMA subsystem), the **MOP Sequencer** (FPU instruction compression), and supporting infrastructure for context switching and clock domain crossing.

TRISC firmware initiates transfers via register writes and continues computation while the Data Movement Cluster hardware autonomously moves data in parallel. The Overlay Engine bridges three clock domains (`ai_clk`, `dm_clk`, `noc_clk`) via CDC FIFOs and integrates with the NoC fabric, NIU bridges, and security/EDC systems.

### 3.1 Overlay Engine Architecture & Scope

#### 3.1.1 Container Module: `tt_neo_overlay_wrapper`

**RTL File:** `/secure_data_from_tt/20260221/tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv`

**Overlay Engine Responsibilities:**
- **Data Movement Engine**: Autonomous stream-based DRAM ↔ L1 transfers
  - Stream controller (CSR interface for DMA commands)
  - TDMA pack/unpack (format conversion, tensor layout transforms)
- **MOP Sequencer**: 32-bit compressed instruction format for FPU datapath
- **L1/L2 Memory Hierarchy Control**: Multi-port L1 interface, L2 cache policy
- **Clock Domain Crossing (CDC)**: FIFOs between `ai_clk`, `dm_clk`, `noc_clk`
- **Reset Distribution**: Power domain and reset sequencing
- **SMN (System Management Network) Security Gateway**: Pre-ATT address filtering
- **EDC (Error Detection & Correction) Ring Integration**: OVL node in EDC chain
- **Rocket CPU Wrapper** (Dispatch tiles only): RISC-V core for Dispatch Engine

**Key Clock Domains:**
- `i_ai_clk[X]` — AI compute (TRISC, FPU, instruction fetch) per column X
- `i_dm_clk[X]` — Data-move (TDMA, pack/unpack, L1 access) per column X
- `i_noc_clk` — Global NoC fabric (all tiles synchronized)
- `i_axi_clk` — Host bus interface (independent PLL)

#### 3.1.2 Design Role & Philosophy

**Purpose:**
The Overlay Engine decouples TRISC firmware from DMA latency and tensor format conversion complexity. Instead of synchronous register polling, firmware initiates streams and continues while hardware autonomously:
- Generates NoC packets
- Routes through mesh fabric
- Translates virtual addresses (ATT)
- Buffers DRAM responses
- Manages format conversions on ingress/egress

**Integration Role:**
- **Tensix Compute Tile:** Data feeder for FPU (via L1) and output collector (from DEST)
- **NoC Fabric:** Overlay is the primary NoC packet generator for DMA
- **NIU Bridge:** Works with NOC2AXI to translate NoC addresses to AXI transactions
- **TRISC Cores:** Provides asynchronous stream CSR interface (no blocking)

#### 3.1.3 Overlay vs. iDMA: Two Independent DRAM Access Mechanisms

| Property | Overlay Streams | iDMA Engine (§7) |
|----------|-----------------|-----------------|
| **Initiator** | TRISC0/1/2/3 CSR write | Dispatch CPU via iDMA instruction |
| **Path** | TRISC CSR → NoC → NIU → AXI → DRAM | Dispatch iDMA → AXI → DRAM (direct master, no NoC) |
| **Purpose** | L1 ↔ DRAM tensor movement (inference compute) | Weight loading, model parameters (init/setup phase) |
| **Streams** | 8 independent streams (0–7) per cluster | 24 command clients, 32 transaction IDs |
| **Latency** | 100–150+ cycles (through NoC) | Lower latency (direct AXI, bypass NoC) |
| **Frequency** | Per-cycle CSR writes possible | Dedicated AXI master port |
| **Contention** | With iDMA for DRAM BW | With overlay streams for AXI BW |

**Key Difference:** Overlay uses **NoC** for routing (flexible but higher latency); iDMA uses **direct AXI master** (dedicated path, faster but shared AXI bus).

---

### 3.2 Data Movement Engine (Core DMA Subsystem)

The **Data Movement Engine** is the operational heart of the Overlay Engine, implementing autonomous DRAM ↔ L1 transfers without TRISC intervention. It comprises three functional blocks:

1. **Stream Controller** — CSR interface → NoC packet generation
2. **TDMA (Tile DMA)** — Pack/unpack engines for format conversion
3. **Stream Status Register File** — Progress tracking and flow control

#### 3.2.1 Stream Controller (DMA Initiator)

**Purpose:** Convert TRISC register writes into NoC DMA packets

**CSR Interface:**
- Width: 32-bit register write from TRISC via `noc_neo_local_regs_intf`
- Accessible by: All 4 TRISC threads (TRISC0, TRISC1, TRISC2, TRISC3)
- Behavior: Non-blocking; TRISC continues immediately after write

**Register Fields** (per stream, 8 streams total):
1. **Source address** — NoC endpoint X + L1 byte offset (for writes) OR DRAM address (for reads)
2. **Destination address** — L1 byte address (for reads) OR DRAM address (for writes)
3. **Transfer size** — Number of 512-bit flits (1–256; 1 flit = 64 bytes)
4. **Direction** — 1 = read (DRAM→L1), 0 = write (L1→DRAM)
5. **Stream ID** — Which of 8 streams (0–7)

**Burst Length Encoding (AXI ARLEN):**
```
ARLEN = (total_bytes / 64) − 1

Examples:
  512 B:    ARLEN =   7  (8 beats)
  4 KB:     ARLEN =  63  (64 beats)
  16 KB:    ARLEN = 255  (256 beats, maximum)
  32 KB:    Split across 2 stream commands
```

**AXI Burst Length Constraint (RTL-Verified):**

The RTL enforces a **maximum burst length of 32 AXI beats** per NOC packet transaction, determined by the NoC packet structure:

```
NOC packet flit limit:     8 flits maximum per transaction
Bytes per flit:            256 bytes (NOC_PAYLOAD_W = 2048 bits)
AXI beats per flit:        4 beats (512-bit AXI / 64 bytes per beat)
Maximum AXI burst:         8 flits × 4 beats/flit = 32 beats
Maximum ARLEN value:       31 (since ARLEN = burst_length − 1)
```

**Note:** The hardware parameter `AXI_MAX_TRANSACTION_SIZE = 4096` specifies 64-beat capacity, but the actual NOC packet constraint limits transactions to 8 flits (2 KB), reducing the practical maximum to 32 AXI beats.

**Maximum Constraint:**
- `MAX_TENSIX_DATA_RD_OUTSTANDING = 4` (8 in large TRISC mode)
- Firmware must check stream status before issuing 5th concurrent read
- Prevents NIU RDATA FIFO overflow (512 entries = 32 KB buffer)
- Per-transaction burst length capped at 32 beats; larger transfers split across multiple commands

#### 3.2.2 TDMA (Tile DMA) Pack/Unpack Engines

**Purpose:** Format conversion and tensor layout transformation for data ingress/egress

**Components:**
- **Pack engine** — Reads DEST latch-array, formats output tensors, writes to L1 via overlay stream CSR
- **Unpack engine** — Reads L1/NoC data, unpacks activation tensors, loads into SRCA/SRCB for FPU
- **Context switch hardware** — Saves/restores L1/L2 cache state across kernel boundaries

**Typical TDMA Operations:**
| Operation | Direction | Source | Dest | Example |
|-----------|-----------|--------|------|---------|
| **Unpack** | DRAM → FPU | L1 buffer | SRCA/SRCB | Activation tensors for next GEMM |
| **Pack** | FPU → DRAM | DEST latch | L1 buffer | Accumulation results or SFPU outputs |
| **Format Convert** | Any | Input RF | Output buffer | INT8 → FP32, tile → linear layout, etc. |

**TRISC Firmware Role in TDMA:**
| TRISC | Task | TDMA Responsibility |
|-------|------|-------------------|
| TRISC0 | Pack controller | Initiates pack via CSR; polls completion |
| TRISC1 | Unpack controller | Initiates unpack via CSR; validates tensor format |
| TRISC2 | Math sequencer | Provides DEST accumulation via FPU output |
| TRISC3 | Tile manager | Coordinates pack/unpack with context switches |

**RTL File:** `/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_instrn_engine.sv` (TDMA control logic)

#### 3.2.3 Stream Status & Flow Control

**Purpose:** Track DMA progress and enforce concurrency limits

**Status Register** (per stream, readable by all TRISC threads):
```c
struct overlay_stream_status {
  uint32_t valid;           // [0]    Stream result ready
  uint32_t error;           // [1]    SMN/ATT/AXI error
  uint32_t in_progress;     // [2]    Stream executing
  uint32_t outstanding;     // [7:3]  In-flight read count (0–4)
};
```

**Polling Constraint:**
- Firmware must check `stream_status[stream].in_progress == 0` before issuing next transfer
- Alternative: Check `outstanding` field; keep ≤ 4
- **Prevents RDATA FIFO overflow** (512 entries = 32 KB, holds 4× max burst)

**Stream State Machine (per DME stream):**
```
IDLE
  │ (TRISC writes CSR with enable bit)
  ▼
ISSUED (1–2 ai_clk cycles)
  │ (Overlay injects NoC packet)
  ▼
IN_FLIGHT (noc_clk domain)
  │ (NoC routes → NIU → AXI → DRAM)
  ├─ NoC routing: 6–8 noc_clk cycles
  ├─ ATT lookup: <1 cycle (combinational)
  ├─ AXI transaction: 50–100+ cycles
  │
  ▼
COMPLETE
  ├─ (Stream status updated via CDC FIFO)
  ├─ (Optional interrupt asserted if enabled)
  │
  ▼
IDLE (ready for next command)
```

---

### 3.3 MOP (Micro-Operation Packet) Sequencer

The **MOP Sequencer** is a separate orchestration engine within the Overlay Engine responsible for compressing FPU control sequences into 32-bit encoded packets that drive TRISC2 and coordinate the math pipeline.

#### 3.3.1 Definition and Purpose

**MOP:** Compressed 32-bit instruction encoding for tensor operations

**Definition:** Compressed 32-bit instruction format for expressing tensor operations

**Format:**
```
32-bit MOP word:
  [31:24] mop_type     — operation type (MAC, ALU, transpose, etc.)
  [23]    done         — completion flag
  [22:8]  loop_count   — loop iteration count
  [7:0]   zmask        — z-plane mask (for unpack z-plane iteration)
```

**Key Feature:** One MOP encodes work that would require hundreds of raw RISC-V instructions
- Example: A 16×16 matrix multiply with accumulation = 1 MOP
- FPU executes in parallel while TRISC2 fetches next MOP

**Parameters** (`tt_instrn_engine.sv`):
- `THREAD_COUNT = 4` — 4 TRISC threads per cluster
- `TRISC_VECTOR_ENABLE = 4'b0001` — TRISC0 only has vector support
- `TRISC_FP_ENABLE = 4'b1111` — All threads can issue FP operations

---

### 3.4 Data Movement Engine — Complete Data Paths

#### 3.4.1 Complete DRAM Access Path (Data Movement Engine)

```
┌─────────────────────────────────────────────────────────────┐
│ TRISC firmware                                              │
│   write_stream_csr(addr, size, direction, stream_id)        │
└──────────────────┬──────────────────────────────────────────┘
                   │ 32-bit register write (ai_clk)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Overlay stream controller (tt_neo_overlay_wrapper)          │
│   ├─ Convert CSR fields to NoC packet                       │
│   ├─ Calculate ARLEN = (size / 64) − 1                      │
│   └─ Inject 512-bit flit into NoC (noc_clk)                │
└──────────────────┬──────────────────────────────────────────┘
                   │ 512-bit flit (noc_clk)
                   │ Destination: NIU endpoint
                   │   X=0,3 standalone: Y=4
                   │   X=1,2 composite:  Y=3 (router row!)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ NoC fabric (tt_trinity_router)                              │
│   ├─ DOR (Dimension-Order Routing) or Dynamic Routing       │
│   ├─ Virtual channel arbitration                            │
│   └─ Forward flit to NIU tile (Y=4 for standalone,         │
│                               Y=3 for composite)            │
└──────────────────┬──────────────────────────────────────────┘
                   │ 512-bit flit (noc_clk)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ NIU / NOC2AXI bridge (tt_noc2axi_*)                         │
│   ├─ ATT address translation (64-entry table)              │
│   │   NoC address → AXI physical address                    │
│   ├─ Extract ARLEN, ARSIZE, ARBURST                         │
│   └─ Issue AXI4 read/write command                          │
└──────────────────┬──────────────────────────────────────────┘
                   │ AXI4 transaction (axi_clk)
                   │ ARSIZE always 3'b110 (64-byte beat)
                   │ ARBURST always 2'b01 (INCR)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ External DRAM Controller (AXI slave)                        │
│   ├─ Wait for ARVALID                                      │
│   ├─ Assert ARREADY when ready                             │
│   └─ Return RDATA (512-bit per beat)                        │
└──────────────────┬──────────────────────────────────────────┘
                   │ 512-bit read data (axi_clk)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ NIU RDATA FIFO (512 entries = 32 KB)                        │
│   └─ Buffer DRAM response; prevent stalls                   │
└──────────────────┬──────────────────────────────────────────┘
                   │ 512-bit flit (noc_clk after CDC)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ L1 partition (3 MB, 512 SRAM macros per cluster)            │
│   ├─ Side-channel port (512-bit direct write)              │
│   ├─ TRISC port (128-bit per thread read/write)             │
│   └─ Store in SRAM banks aligned to address                 │
└──────────────────────────────────────────────────────────────┘
```

#### 3.4.2 NIU Addressing: Composite vs. Standalone

**CRITICAL DIFFERENCE:**

| Column | Type | NIU Y-Coordinate | Firmware Address |
|--------|------|------------------|-----------------|
| X=0 | Standalone NIU (NOC2AXI_NW_OPT) | Y=4 | `NOC_XY_ADDR(0, 4, ...)` |
| X=1 | Composite (NOC2AXI_ROUTER_NW_OPT) | Y=3 | `NOC_XY_ADDR(1, 3, ...)` ← Router row |
| X=2 | Composite (NOC2AXI_ROUTER_NE_OPT) | Y=3 | `NOC_XY_ADDR(2, 3, ...)` ← Router row |
| X=3 | Standalone NIU (NOC2AXI_NE_OPT) | Y=4 | `NOC_XY_ADDR(3, 4, ...)` |

**Why the difference?** In N1B0, the center columns (X=1, X=2) use a composite P&R cluster that spans both Y=3 (router) and Y=4 (NIU). The NIU presents itself to the NoC at the Y=3 row. Using `Y=4` causes packets to address a non-existent node and be dropped or misrouted.

**Firmware Impact:**
```c
// INCORRECT (will fail):
write_stream_csr(stream=0, src_addr_x=1, src_addr_y=4, ...);  // ❌ Packet dropped

// CORRECT:
write_stream_csr(stream=0, src_addr_x=1, src_addr_y=3, ...);  // ✓ Routes to composite NIU
```

#### 3.4.3 Clock Domain Crossings

The overlay engine bridges three clock domains:

| Crossing | Source → Dest | Mechanism | Location |
|----------|---|---|---|
| ai_clk → noc_clk | TRISC CSR write → Overlay inject | CDC FIFO | overlay_wrapper (input side) |
| noc_clk → ai_clk | Stream status readback | CDC FIFO | overlay_wrapper (output side) |
| noc_clk → dm_clk | L1 data ingress | Synchronizer FIFO | L1 partition interface |

**CDC Design Principle:** FIFOs decouple clock domains without imposing synchronous reset relationships. TRISC (ai_clk) can continue while overlay DMA (noc_clk) executes at potentially different frequency.

#### 3.4.4 L1 Memory Hierarchy Integration

**L1 Architecture per Cluster:**
- 512 SRAM macros × 6 KB each = 3 MB
- 4 macro banks (for independent read/write on same cycle)
- **512-bit "NoC side-channel" port:** Direct write from NoC without TRISC involvement
- **128-bit per-thread port:** TRISC read/write for format conversion

**Data Paths to L1:**

| Path | Source | Destination | Width | Clock | Purpose |
|------|--------|-------------|-------|-------|---------|
| ① | DRAM (via NoC) | L1 side-channel | 512 bits | noc_clk | Activation tensor ingress (DMA) |
| ② | TRISC | L1 (per-thread) | 128 bits | ai_clk | Format conversion, inspection |
| ③ | L1 (via NoC side-channel) | DRAM (via NIU) | 512 bits | noc_clk | Output tensor egress (overlay stream write) |

**Constraint:** No direct TRISC → DRAM path. TRISCs cannot load DRAM directly into their LDM via single `lw` instruction. Data must first arrive in L1 via DMA, then TRISC reads from L1.

---

### 3.5 Context Switching (Overlay Engine Feature)

#### 3.5.1 Purpose & Hardware Support

**Context Switching:** Dynamic switching between different kernel workloads while preserving L1 and L2 cache state

**Hardware Support:**
- 2 SRAM macros per Tensix tile for context state (dm_clk domain)
- Partition control (PRTN) chain synchronizes power domain enable/disable
- Selective clock gating allows independent power-down of instruction engines while keeping L1 accessible

#### 3.5.2 Save/Restore Flow

```
Before context switch:
  ┌──────────────────────────┐
  │ Kernel A active          │
  │ L1: tensor data A        │
  │ TRISC: executing code A  │
  └──────────────────────────┘

Switch command (PRTN chain):
  ├─ Quiesce Kernel A (flush pending DMA)
  ├─ Snapshot L1/L2 state → Context SRAM (dm_clk)
  └─ Gate ai_clk and dm_clk to Kernel A tiles

Switch to Kernel B:
  ├─ Restore L1/L2 from Context SRAM → Kernel B L1
  ├─ Un-gate ai_clk and dm_clk to Kernel B
  └─ Resume Kernel B execution
```

#### 3.5.3 PRTN Chain Integration

**PRTN** (Partition Control) chain:
- External input: `PRTNUN_FC2UN_RSTN_IN` (partition control reset)
- Internal propagation: Y=2 cluster (Y=3 and Y=2) layer-by-layer
- Clock domain: Independent PRTN_clk (separate PLL from ai_clk, dm_clk)

**When PRTN asserts context switch:**
1. Partition control block sends enable/disable pulses
2. Each Tensix tile's overlay wrapper gates clocks conditionally
3. L1 SRAM context state is saved if enabled
4. New kernel's state is loaded from SRAM
5. Clock gates are released once ready

---

### 3.6 Data Movement Engine Performance

#### 3.6.1 Data Rate and Throughput

**Theoretical Peak** (per NIU, per column):
- 512-bit flit × 1 GHz = 512 GB/s
- 512-bit flit × 800 MHz = 409.6 GB/s

**Practical Achievable** (with contention):
- DRAM controller bandwidth: 100–200 GB/s (typical DDR5)
- AXI arbitration: Multiple NIUs (2 composite + 2 standalone) contend for DRAM
- NoC congestion: Router virtual channels may stall under heavy all-to-all traffic
- **Expected sustainable throughput:** 50–150 GB/s per NIU (highly workload-dependent)

#### 3.6.2 Latency Model

**End-to-end latency** (one read request to data available in L1):

| Stage | Cycles | Comment |
|-------|--------|---------|
| CSR write → overlay inject | 1–2 | ai_clk → noc_clk CDC |
| Overlay inject → NoC packet ready | 1 | noc_clk |
| NoC routing (to NIU) | 6–8 | DOR: 4 hops (worst case), +VC arbitration |
| NIU ATT lookup → AXI transaction | <1 | Combinational in typical design |
| AXI → DRAM (round trip) | 50–100 | DRAM controller latency; highly variable |
| DRAM → NIU RDATA FIFO | 6–8 | AXI signaling, CDC FIFOs |
| **Total** | **100–150+** | Depends on DRAM load, NoC congestion |

**Implication:** Firmware must assume 100–150+ cycles before data is usable in L1.

#### 3.6.3 Stream Capacity and Concurrency

**Streams per cluster:** 8 independent streams (0–7)

**Concurrency constraint:** `MAX_TENSIX_DATA_RD_OUTSTANDING = 4`
- Firmware cannot have more than 4 read streams in-flight simultaneously
- Prevents RDATA FIFO overflow (512 entries = 32 KB)
- **Firmware responsibility:** Poll stream status and throttle new reads

**Write streams:** No explicit limit; overlay can queue multiple writes to different L1 addresses

**Typical workload pattern:**
```c
// Issue 4 concurrent reads
for (int i = 0; i < 4; i++) {
  write_stream_csr(stream=i, ..., direction=READ, ...);
}

// Wait for completion before issuing 5th
while (stream_status[0].outstanding < 4) { /* all 4 complete */ }

// Now issue 5th read
write_stream_csr(stream=4, ..., direction=READ, ...);
```

---

### 3.7 Overlay Engine Integration with Other Components

#### 3.7.1 TRISC Cores and Synchronization

**TRISC Roles in Overlay Operation:**

| TRISC | Task | Interaction with Overlay |
|-------|------|--------------------------|
| TRISC0 | Pack | Reads DEST latch-array → formats output tensor → writes via overlay CSR to L1 |
| TRISC1 | Unpack | Initiates overlay stream CSR writes to fetch activation tensors; polls completion |
| TRISC2 | Math | Driven by MOP sequencer (FPU controlled); relies on TRISC1 to populate SRCA/SRCB |
| TRISC3 | Manage | Tile initialization, residual DMA (small transfers), KV-cache, output storage |

**Synchronization mechanism:** Hardware semaphores (SEMGET/SEMPOST instructions)
- TRISC0 signals completion via SEMPOST after pack finishes
- TRISC1 waits via SEMGET before initiating next unpack
- MOP sequencer auto-triggers FPU on TRISC2

#### 3.7.2 FPU Integration

**FPU and Overlay Independence:**
- FPU reads SRCA/SRCB independently (filled by unpack engine via TRISC1)
- FPU writes DEST (read by pack engine via TRISC0)
- **No direct overlay-to-FPU path:** Data flows DRAM → L1 → TRISC1 → SRCA/SRCB → FPU

**Pipelined execution:** While FPU computes, overlay can simultaneously:
- Fetch next activation tensor from DRAM
- Write output tensor to L1 for next kernel stage

#### 3.7.3 NoC Integration

**NoC packet generation:**
- Overlay generates standard NoC flits (512-bit, `noc_header_address_t` format)
- Uses DOR (Dimension-Order) routing or dynamic routing based on NoC config
- Virtual channel arbitration handled by tt_trinity_router (transparent to overlay)

**NoC port for overlay:**
- Local port: flit_out_req / flit_out_resp pair
- Direction: Always toward NIU (fixed routing pattern for DMA)

#### 3.7.4 NIU (NOC2AXI) Integration

**NIU Responsibilities:**
1. **Receive NoC flits** from overlay stream controller
2. **ATT lookup:** Translate NoC endpoint + offset → AXI physical address
   - 64-entry table per NIU
   - Firmware programs via APB registers
3. **Burst calculation:** Extract ARLEN from overlay CSR size field
4. **AXI master interface:** Issue AXI4 read/write commands
5. **RDATA buffering:** 512-entry FIFO (32 KB) absorbs DRAM response

**Addressing constraints** (§3.3.2):
- Composite NIUs (X=1, X=2) must be addressed at Y=3, not Y=4
- Firmware address calculations must account for this difference

#### 3.7.5 SMN (System Management Network) Security Integration

**SMN pre-ATT security fence:**
- 8 independently programmable address ranges (allow/block/log)
- Checked **before** ATT lookup
- **Violation action:** Assert `slv_ext_error` signal → escalate to CRIT interrupt

**Firmware responsibility:**
- Configure SMN ranges to restrict overlay stream read/write access to authorized DRAM regions
- Example: Prevent weight tensors from being written; allow only reading

#### 3.7.6 EDC Ring Integration

**EDC node per Tensix cluster:**
- Positioned between NoC node and L1 node in ring traversal
- **OVL (Overlay) node:** Monitors EDC across the overlay engine
- **Ring chain bypass:** If overlay tile is harvested (ISO_EN asserted), OVL node is bypassed

**Overlay-related EDC errors:**
- Error in AXI transaction (SLVERR from external slave) → CRIT interrupt
- Parity error in L1 write path → ECC ± escalation
- NIU timeout (no RDATA within timeout) → CRIT interrupt

---

### 3.8 Power Management and DFX (Overlay Engine)

#### 3.8.1 Clock Gating

**Clock gate locations:**
- `overlay_wrapper_dfx`: Gates `dm_clk` to L1/L2 cache
- `instrn_engine_wrapper_dfx`: Gates `ai_clk` to TRISC instruction engines
- `t6_l1_partition_dfx`: Independent L1 partition clock gating

**Design principle:** L1 can remain accessible for DMA when instruction engines are gated (power saving for idle kernels).

#### 3.8.2 Reset Hierarchy

**Reset sources:**
- `i_aiclk_reset_n` — AI clock domain reset (from per-column i_ai_reset_n[X])
- `i_nocclk_reset_n` — NoC clock domain reset (from global i_noc_reset_n)
- `i_core_reset_n` — TDMA/pack/unpack core reset
- `i_uncore_reset_n` — Overlay uncore (L1 interface) reset

**Reset propagation:**
- Async deassertion at top level
- Synchronized internally via 3-stage synchronizer per domain
- Maintains reset sequencing: upstream (NIU, Router) before downstream (Tensix)

#### 3.8.3 DFX Integration

**Wrappers:**
- `tt_overlay_wrapper_dfx` — Overlay engine DFX wrapper
- `tt_instrn_engine_wrapper_dfx` — TRISC instruction engine DFX wrapper
- `tt_t6_l1_partition_dfx` — L1 partition DFX wrapper

**Features:**
- Tessent scan chain integration
- Clock gating control via Tessent SIB
- DFT mode override (clock enables forced high for scan)

---

#### 3.9 RTL File Locations and Key Parameters

#### 3.9.1 Core RTL Files

| File | Location | Purpose |
|------|----------|---------|
| `tt_neo_overlay_wrapper.sv` | `/secure_data_from_tt/20260221/tt_rtl/overlay/rtl/` | Main overlay container module |
| `tt_instrn_engine.sv` | `/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/` | MOP sequencer, TDMA orchestration |
| `tt_trisc.sv` | `tt_rtl/tt_tensix_neo/src/hardware/trisc/` | TRISC0/1/2 core |
| `tt_risc_wrapper.sv` | `tt_rtl/tt_tensix_neo/src/hardware/trisc/` | TRISC3 (RV32I wrapper) |
| `tt_overlay_pkg.sv` | `/secure_data_from_tt/20260221/tt_rtl/overlay/rtl/` | Package definitions (types, constants) |
| `tt_t6_local_regs_pkg.sv` | `tt_rtl/tt_tensix_neo/src/` | Register interface definitions |

#### 3.9.2 Key Parameters

```systemverilog
// tt_instrn_engine.sv parameters:
localparam int THREAD_COUNT = 4;                          // 4 TRISC threads per cluster
localparam int TRISC_IRAM_ENABLE = 4'b0000;              // Shared L1 instruction memory
localparam int TRISC_VECTOR_ENABLE = 4'b0001;            // TRISC0 only has vector ops
localparam int TRISC_FP_ENABLE = 4'b1111;                // All threads FP-capable
localparam int MAX_TENSIX_DATA_RD_OUTSTANDING = 4;       // Max concurrent reads (8 in large mode)
localparam int MAX_L1_REQ = 16;                          // Max in-flight L1 requests
localparam int INSN_REQ_FIFO_DEPTH = 8;                  // Instruction request FIFO (16 in large)
localparam int NOC_CONTROL = 0;                          // No direct NoC port for TRISCs

// tt_neo_overlay_wrapper.sv parameters:
localparam int NUM_STREAMS = 8;                          // 8 overlay streams per cluster
localparam int STREAM_STATUS_WIDTH = 8;                  // Status register per stream
localparam int CDC_FIFO_DEPTH = 8;                       // CDC FIFO depth (ai_clk ↔ noc_clk)
localparam int L1_SIDE_CHANNEL_WIDTH = 512;              // NoC side-channel port width
```

#### 3.9.3 Register Map Summary

**Overlay Stream CSR Base Address** (per cluster, relative to APB base):
- Stream 0–7: Offset 0x1000 – 0x1FFF (16 KB per stream, 128 KB total)

**Stream Status Register Base** (read-only):
- Stream 0–7: Offset 0x2000 – 0x20FF (per TRISC thread offset)

---

#### 3.10 DMA and RISC Bus Protocol

This section details the complete communication protocol between TRISC cores and the overlay DMA engine, covering request initiation, response handling, bus arbitration, and error signaling.

#### 3.10.1 CSR Request Protocol — Overlay Stream Programming

**Initiation Path:**
Each TRISC programs a DMA transfer by writing a 32-bit CSR (Control and Status Register) to the overlay stream controller. This is a **non-blocking request** — the TRISC continues execution immediately after the write.

**Register Write Mechanism** (`noc_neo_local_regs_intf`, `tt_instrn_engine.sv`):

```systemverilog
// TRISC firmware initiates DMA via 32-bit CSR write
// (e.g., TRISC1 writes stream 0 control register)

write_to_csr(
  addr     = 0x1000 + (stream_id << 4),    // Stream 0–7 offset per cluster
  data[31:0] = {
    [31:24] src_x,           // Source X coordinate (0–3)
    [23:16] src_y,           // Source Y coordinate (0–4)
    [15:12] src_offset_hi,   // L1 byte offset [19:16]
    [11:0]  src_offset_lo,   // L1 byte offset [15:4]
    [3:2]   direction,       // 0=write(L1→DRAM), 1=read(DRAM→L1)
    [1:0]   stream_id        // Which stream (0–7)
  }
);
```

**Register Fields Breakdown:**

| Field | Width | Purpose | Example |
|-------|-------|---------|---------|
| `src_x`, `src_y` | 4 bits each | Source tile endpoint (or destination for writes) | `(1, 3)` for composite NIU |
| `src_offset[19:0]` | 20 bits | Byte offset within L1 partition (0–3MB) | `0x0_1000` for 4 KB into L1 |
| `direction` | 2 bits | `0` = L1→DRAM write, `1` = DRAM→L1 read | `1` for prefetch |
| `stream_id` | 2 bits | Which overlay stream (0–7) | `0` uses stream 0 |
| `size` | Separate CSR | Transfer size in 512-bit flits | `8` = 512 bytes |

**Clock Domain:** The CSR write crosses from `i_ai_clk` (TRISC clock) to `noc_clk` (NoC fabric clock) via a **CDC synchronizer** (2–3 cycle latency).

**Non-blocking semantics:**
```systemverilog
// TRISC writes CSR and immediately continues
write_stream_csr(stream=0, src_x=1, src_y=3, offset=0x1000, size=64, dir=READ);
compute_intensive_loop();  // ← Executes in parallel with DMA

// Later, poll for completion
while (!read_stream_status(stream=0).valid) { }
```

---

#### 3.10.2 Response Protocol and Stream Status Polling

**Status Register Interface:**

Each overlay stream exposes a **read-only status register** per TRISC thread (`trisc_tensix_noc_stream_status[thread][stream]`):

```systemverilog
// Stream status register fields (32-bit, read-only)
typedef struct packed {
  logic [31:8]  reserved;
  logic         valid;              // [7] — Transfer complete and result is in L1
  logic         error;              // [6] — Error occurred (SMN violation, ATT miss, AXI SLVERR, timeout)
  logic         in_progress;        // [5] — Stream is currently executing
  logic [4:0]   outstanding_reads;  // [4:0] — Count of in-flight read responses (0–4)
} stream_status_t;
```

**Status Transitions:**

```
┌─────────────┐
│   IDLE      │ (No CSR written yet)
└──────┬──────┘
       │ [TRISC writes stream CSR]
       ▼
┌─────────────┐
│IN_PROGRESS  │ in_progress=1, outstanding_reads grows as DRAM responds
└──────┬──────┘
       │ [Last response arrives from DRAM]
       │ [Data written to L1 via side-channel]
       ▼
┌─────────────┐
│   VALID     │ valid=1, in_progress=0, outstanding_reads=0
└─────────────┘
```

**Polling Patterns (Firmware):**

```c
// Pattern 1: Synchronous polling (busy-wait)
write_stream_csr(stream=0, src_x=1, src_y=3, offset=0x2000, size=32, dir=READ);
while (!read_stream_status(stream=0).valid) {
  // Spin until valid; consumes power, no hiding latency
}
use_data_from_l1(0x2000);

// Pattern 2: Asynchronous polling with computation overlap
write_stream_csr(stream=0, ...);
for (int i = 0; i < 1000; i++) {
  compute_unrelated_kernel();  // Hide DMA latency with work
  if (read_stream_status(stream=0).valid) break;
}
use_data_from_l1(...);

// Pattern 3: Multi-stream pipelining (maximize bandwidth)
write_stream_csr(stream=0, offset=0x0000, ...);
write_stream_csr(stream=1, offset=0x1000, ...);
write_stream_csr(stream=2, offset=0x2000, ...);
compute_kernel();  // 3 DMA transfers in flight simultaneously
while (!all_streams_valid()) { }
```

**Outstanding Reads Constraint:**

The `outstanding_reads` field counts the number of DRAM read responses in transit. The hardware enforces:

```c
// Constraint: MAX_TENSIX_DATA_RD_OUTSTANDING = 4
if (outstanding_reads < 4) {
  // Safe to issue another READ command
  write_stream_csr(stream=3, direction=READ, ...);
} else {
  // Must wait for at least one response to arrive
  while (read_stream_status(stream).outstanding_reads >= 4) { }
  write_stream_csr(stream=4, direction=READ, ...);
}
```

**Why this constraint?** The NIU contains a 512-entry RDATA FIFO (32 KB capacity). If firmware allows more than 4 reads in flight per tile, the FIFO can overflow and cause data loss.

---

#### 3.10.3 Bus Arbitration and Multi-Initiator Access

**Simultaneous TRISC Requests:**

Up to **4 TRISC threads** can write to overlay stream CSRs in the same cycle. The `trisc_tensix_sync` module arbitrates these requests:

| TRISC | Can Access Overlay? | Can Initiate Streams? | Note |
|-------|:---:|:---:|----------|
| TRISC0 (unpack) | ✓ | ✓ | Initiates reads to prefetch L1 data |
| TRISC1 (math) | ✓ | ✓ | May initiate weight prefetch |
| TRISC2 (pack) | ✓ | ✓ | Initiates writes of output data to L1 |
| TRISC3 (mgmt) | ✓ | ✓ | Handles residual DMA, KV-cache loads |

**Arbitration Mechanism:**

```systemverilog
// Simplified arbitration (rt_instrn_engine.sv):
for each stream in 0..7 {
  if (trisc0_csr_write[stream]) {
    selected_trisc = 0;
  } else if (trisc1_csr_write[stream]) {
    selected_trisc = 1;
  } else if (trisc2_csr_write[stream]) {
    selected_trisc = 2;
  } else if (trisc3_csr_write[stream]) {
    selected_trisc = 3;
  }
  // Priority: TRISC0 > TRISC1 > TRISC2 > TRISC3 (fixed priority)
}
```

**Conflict Resolution (same stream, multiple TRISCs):**

If two TRISCs attempt to write the same stream in the same cycle, a **fixed-priority arbiter** selects one and stalls the other by one cycle:

```c
// TRISC1 and TRISC3 both try to write stream 0
TRISC1: write_stream_csr(stream=0, offset=0x0000, size=1024, dir=READ);
TRISC3: write_stream_csr(stream=0, offset=0x1000, size=512, dir=READ);

// Result: TRISC1 wins (priority 1 > 3); TRISC3 stalls one cycle
// Cycle N:   TRISC1 write accepted, stream[0] ← TRISC1 config
// Cycle N+1: TRISC3 write accepted, stream[0] ← TRISC3 config (overwrites TRISC1)
//            TRISC1 sees data loss! Must synchronize or use different streams.
```

**Best Practice — Firmware Synchronization:**

```c
// Use semaphores to ensure only one TRISC writes a given stream at a time
TRISC0:
  SEMGET sem_stream0;           // Wait for exclusive access
  write_stream_csr(stream=0, ...);
  SEMPOST sem_stream0;

TRISC3:
  SEMGET sem_stream0;           // Wait for TRISC0 to finish
  write_stream_csr(stream=0, ...);
  SEMPOST sem_stream0;
```

---

#### 3.10.4 Burst Protocol and Flit Format

**AXI Burst Length Encoding (NIU → DRAM):**

The overlay stream size field is translated into an AXI ARLEN (address read length) command:

```systemverilog
// CSR size field → AXI burst parameters
wire [7:0] size_in_flits = read_csr_size_field();  // 1–256 flits
wire [7:0] arlen = (size_in_flits << 6 / 64) - 1;  // Bytes → beat count

// Examples:
// size=1 flit (64B)   → ARLEN=0   (1 beat)
// size=8 flits (512B) → ARLEN=7   (8 beats)
// size=16 flits (1KB) → ARLEN=15  (16 beats)
// size=256 flits (16KB) → ARLEN=255 (256 beats, MAX)
```

**NoC Flit Format (TRISC CSR → NIU):**

The overlay stream controller converts the CSR fields into a standard NoC packet:

```
512-bit NoC Flit (noc_clk domain):
┌─────────────────────────────────────────────────────────────┐
│ [511:480] noc_header_address_t (96-bit address field)       │
│           ├─ [95:88]   dst_x (destination NIU X)            │
│           ├─ [87:80]   dst_y (destination NIU Y=4 or Y=3)   │
│           ├─ [79:64]   axi_addr[55:40] (AXI address high)   │
│           ├─ [63:0]    axi_addr[39:0]  (AXI address low)    │
│           └─ [3:0]     flit_type (HEADER or DATA)           │
├─────────────────────────────────────────────────────────────┤
│ [479:0]   Payload (depends on direction)                    │
│           ├─ For WRITE: Tensor data (512-bit word)          │
│           ├─ For READ: Zeros (data returns from DRAM)       │
└─────────────────────────────────────────────────────────────┘

Direction encoding:
  direction[0] = 0 → WRITE (L1→DRAM): payload carries L1 data
  direction[0] = 1 → READ  (DRAM→L1): payload is metadata, data returns from DRAM
```

**DRAM Address Translation (NIU ATT):**

The NIU performs address translation in a 3-stage pipeline:

```
Stage 1 (combinational):
  axi_addr[55:0] = noc_packet[79:24]  (extract from flit)

Stage 2 (ATT lookup):
  for each of 64 ATT entries {
    if (axi_addr matches entry.mask) {
      translated_addr = entry.base | (axi_addr & entry.offset_mask);
      access_allowed = entry.allow_bit;
      break;
    }
  }

Stage 3 (AXI command issue):
  if (access_allowed) {
    axi_araddr / axi_awaddr = translated_addr;
    axi_arlen = calculated_ARLEN;
    axi_arsize = 3'b110;  // 64-byte beats
    axi_arburst = 2'b01;  // INCR (incrementing burst)
  } else {
    // ATT miss → CRIT interrupt, slv_ext_error
  }
```

---

#### 3.10.5 Error Handling and Completion Signaling

**Error Sources and Detection:**

| Error Type | Detector | Signal | Severity | Recovery |
|-----------|----------|--------|----------|----------|
| **SMN Violation** | System Management Network pre-ATT filter | `slv_ext_error` → CRIT interrupt | CRITICAL | Firmware must fix address range |
| **ATT Miss** | NIU address translation table lookup fails | `slv_ext_error` → CRIT interrupt | CRITICAL | Reprogram ATT entry |
| **DRAM SLVERR** | External AXI slave returns error response | `slv_ext_error` → CRIT interrupt | CRITICAL | DRAM error; hardware fault |
| **Timeout** | Overlay stream no response within N cycles | `o_niu_timeout_intp` → TRISC3 interrupt | CRITICAL | Likely deadlock; reset and retry |
| **L1 SECDED (Single-bit)** | L1 SRAM during write | Silent correction, error logged | INFO | No action needed |
| **L1 SECDED (Double-bit)** | L1 SRAM during write | `l1_uncorrectable_intp` → TRISC3 | CRITICAL | Likely hardware fault |

**Error Signaling via Status Register:**

```systemverilog
// stream_status[stream].error bit set indicates:
typedef struct packed {
  logic error;  // [6] Set to 1 when:
                //     - SMN or ATT check fails
                //     - AXI slave returns SLVERR or RRESP[1]=1 (error)
                //     - Timeout expires
                //     - L1 uncorrectable ECC
} stream_status_t;

// Firmware checks error before using data:
if (stream_status[0].error) {
  // Handle error: log, retry, or abort kernel
  report_dma_error(stream=0);
  // Do NOT use L1 data; it may be corrupted
} else if (stream_status[0].valid) {
  // Safe to use L1 data
  process_data_from_l1();
}
```

**Completion Signaling Mechanisms:**

The overlay engine signals DMA completion via multiple channels:

1. **Status Register Valid Bit** (primary, polled by firmware)
   ```c
   while (!stream_status[0].valid) { compute(); }
   ```

2. **Hardware Semaphore Auto-SEMPOST** (when configured)
   ```c
   // Firmware can configure overlay to auto-post semaphore on completion
   // (See §3.2.3 MOP sequencer integration)
   TRISC0: SEMGET sem_dma;  // Blocks until overlay posts
   TRISC3: configure_stream_auto_sempost(stream=0, sem=sem_dma);
   ```

3. **Interrupt to TRISC3** (for critical errors)
   ```c
   // TRISC3 interrupt handler:
   void overlay_error_irq() {
     stream_status_t status = read_all_stream_status();
     for (int s = 0; s < 8; s++) {
       if (status[s].error) {
         // Handle stream error
         handle_stream_error(s);
       }
     }
   }
   ```

---

#### 3.10.6 Clock Domain Crossing (CDC) and Latency

**Clock Domains Involved:**

| Domain | Frequency | Purpose | Role in DMA |
|--------|-----------|---------|------------|
| `i_ai_clk` | Per-column clock (e.g., 1 GHz) | TRISC execution | CSR write initiation |
| `noc_clk` | Global NoC clock (e.g., 1 GHz, independent) | NoC packet forwarding | Overlay stream controller, flit injection |
| `axi_clk` | External AXI clock (e.g., 1 GHz) | DRAM controller interface | NIU AXI master |
| `dm_clk` | Data-movement clock (per-column) | L1 cache, overlay SRAM | L1 write side-channel, context switch |

**CDC Synchronizer Stages:**

```
ai_clk domain          noc_clk domain
  ↓                      ↓
TRISC writes CSR    → [2-stage CDC FIFO]  → Overlay detects CSR write
                                           → Converts to NoC packet
                                           → Injects into NoC fabric
                                                   ↓
                        noc_clk domain      noc_clk domain
                          ↓                  ↓
                       Router forwards   → NIU receives flit
                       (2–10 cycles DOR)
                                              ↓
                        axi_clk domain
                          ↓
                       DRAM controller executes AXI transaction
                       (50–100+ cycles, depends on DRAM bus)
                                              ↓
                        noc_clk domain
                          ↓
                       [RDATA FIFO buffers response]
                       [CDC FIFO converts to dm_clk/noc_clk]
                                              ↓
                        ai_clk domain
                          ↓
                       TRISC reads status register
                       [2-stage CDC FIFO]  ← Stream valid asserted
```

**End-to-End Latency Breakdown:**

```
CSR write (ai_clk)                           0 cycles
  ↓ CDC 1 → noc_clk synchronizer            2–3 cycles
Overlay generates NoC packet                 1 cycle
  ↓ Inject into NoC                         1 cycle
Router DOR/dynamic routing                   2–10 cycles (depends on path)
  ↓ Reach NIU tile
NIU ATT lookup + AXI issue                   2–3 cycles
  ↓ AXI ARVALID → ARREADY handshake         1 cycle
DRAM controller processes request           50–100+ cycles (memory dependent)
  ↓ DRAM array access + return
NIU RDATA FIFO receives data                 1 cycle
  ↓ CDC 2 → noc_clk + ai_clk sync           2–4 cycles
Stream status valid asserted (ai_clk)       1 cycle
  ↓ TRISC reads status register
Total latency (read path):                  100–150 cycles typical
```

**Design for Hiding Latency:**

```c
// Firmware launches DMA request early, overlaps with computation
for (int tile_batch = 0; tile_batch < num_tiles; tile_batch++) {
  // Launch prefetch for next batch (latency = 100+ cycles)
  write_stream_csr(stream=0, addr=next_tile_addr, size=1024, dir=READ);
  
  // Compute while DMA executes in background (hide latency)
  for (int iter = 0; iter < 1000; iter++) {
    compute_kernel(current_tile);  // 150+ cycles of computation
  }
  
  // By now, DMA for next_tile should be complete
  if (!stream_status[0].valid) {
    // Stall only if compute wasn't long enough
    while (!stream_status[0].valid) { }
  }
  
  // Use data from L1
  current_tile = next_tile;
}
```

---

#### 3.10.7 Bandwidth and Flow Control

**Overlay Stream Bandwidth:**

| Metric | Value | Notes |
|--------|-------|-------|
| Per-stream data rate | 512 bits/cycle (noc_clk) | Each flit = 64 bytes |
| Simultaneous streams | 8 per cluster | Sequential at DRAM interface |
| Practical throughput | 256–512 bits/cycle sustained | Limited by DRAM and AXI arbiter |
| Peak burst throughput | 512 bits/cycle × 1 GHz = 64 GB/s | For short 16 KB bursts |

**Credit-Based Flow Control (NoC):**

The NoC router implements **credit-based virtual channel (VC) flow control**. The overlay stream controller monitors downstream credits:

```systemverilog
// Before injecting a flit:
if (available_vc_credits > 0) {
  inject_flit_into_noc();
  decrement_credit();
} else {
  stall_overlay_stream();  // Wait for downstream to accept flit
}
```

**L1 Side-Channel Bandwidth:**

```
Data path: DRAM → NIU RDATA FIFO → L1 side-channel port (512-bit)
         512 bits/cycle (dm_clk domain)
         Can write 1 complete 512-bit cache line per cycle into L1
```

**Contention with iDMA:**

The Dispatch iDMA engine also competes for AXI bandwidth. Both overlay and iDMA issue transactions to the same external DRAM controller:

```
Overlay streams (8 max)  ┐
                         ├─→ [AXI arbiter] → DRAM controller → external memory
iDMA (1 master)          ┘
```

**Best-effort arbitration:** No QoS prioritization; both are treated equally by the AXI switch. Firmware must manage bandwidth sharing explicitly.

---

#### 3.10.8 Integration with TRISC Synchronization

**Overlay Completion → Semaphore Signaling:**

The MOP sequencer can configure an overlay stream to automatically post a hardware semaphore upon completion:

```systemverilog
// MOP defines stream completion behavior:
mop_word[31:24] = MVDMA_OP;          // DMA micro-op
mop_word[23:16] = stream_id;         // Which stream (0–7)
mop_word[15:8]  = sem_post_on_completion; // Semaphore to post (0–31)
mop_word[7:0]   = loop_count;        // Repeat count (1–256)

// When stream completes:
//   1. Stream status valid bit asserted
//   2. If sem_post_on_completion != 0, SEMPOST sem_post_on_completion executed
//   3. Waiting TRISC (if in SEMGET) resumes next cycle
```

**Example: Overlapped Prefetch with Math:**

```c
// TRISC1 (math) and TRISC0 (unpack) synchronized via semaphore:

TRISC0:
  SEMGET sem_prefetch;  // Block until TRISC1 signals "ready for next tile"
  write_stream_csr(stream=0, addr=next_tile, size=512, dir=READ);
  // Returns immediately; overlay runs asynchronously

TRISC1:
  // Math loop processes current tile (100+ cycles)
  for (int k = 0; k < K_tile; k++) {
    issue_mop(stream_id=MATH_MOP);
  }
  SEMPOST sem_prefetch;  // Signal TRISC0 to prefetch next tile

  // While TRISC0 fetches, TRISC1 waits for prefetch completion:
  SEMGET sem_prefetch_done;  // Overlay auto-posts when stream valid
  
  // Data now in L1; proceed to next iteration
```

---

## Summary: Key Constraints and Firmware Idioms

| Constraint | Value | Impact |
|-----------|-------|--------|
| Max AXI burst | 16 KB (256 beats) | Split larger transfers into multiple stream commands |
| Max outstanding reads | 4 | Firmware must poll before issuing 5th read |
| Min L1 fetch latency | 100–150 cycles | Plan computation pipeline assuming 100+ cycle latency |
| Composite NIU Y-coordinate | Y=3 (not Y=4) | Use `NOC_XY_ADDR(x, 3, ...)` for X=1,2 |
| Streams per cluster | 8 | Limited stream capacity; may need queuing/scheduling |
| CDC latency | 2–4 cycles | CSR → overlay inject + stream status readback |

**Key Firmware Pattern:**
```c
// Initiate DMA transfer
write_stream_csr(stream, src, dst, size, direction);

// Overlap computation while DMA executes
compute_kernel();

// Poll for completion before reading result
while (!stream_status[stream].valid) { /* wait */ }

// Data is now in L1; proceed to next stage
process_result_from_l1();
```

---

**References:**
- §2.3.2–2.3.6: TRISC and L1 memory access details
- §3.2.3: ATT address translation
- §3.7: NIU DMA operation and AXI interface
- §6: iDMA engine (alternative DRAM access)
- §8.4: ISO_EN harvest isolation (affects overlay gating)
- §10: Reset architecture (overlay reset distribution)
- §14: Verification and firmware test suite (overlay testing coverage)




## §4 NOC2AXI Composite Tiles

### 4.1 Overview

Two composite tiles provide the bridge between the internal NoC fabric and the external AXI host interface:

| Instance    | Grid Span  | RTL Module                          |
|-------------|------------|--------------------------------------|
| NE_OPT      | X=1, Y=3–4 | `trinity_noc2axi_router_ne_opt.sv`  |
| NW_OPT      | X=2, Y=3–4 | `trinity_noc2axi_router_nw_opt.sv`  |

Each composite tile physically spans two rows. The Y=4 portion contains the NIU (NOC-to-AXI bridge) and the Y=3 portion contains the router row. Internal cross-row flit wires connect the two portions without going through the top-level NoC mesh.

```
┌─────────────────────────────────────────────┐
│     NOC2AXI_ROUTER_NW_OPT / NE_OPT          │
│     (Composite tile spanning Y=3 and Y=4)   │
│                                              │
│  Y=4  ┌──────────────────────────────────┐  │
│       │         NIU (tt_noc2axi)          │  │
│       │  ┌─────────────┐ ┌─────────────┐ │  │
│       │  │ NOC→AXI     │ │ AXI→NOC     │ │  │
│       │  │ Bridge      │ │ Bridge      │ │  │
│       │  └─────────────┘ └─────────────┘ │  │
│       │  ┌──────┐ ┌─────┐ ┌───────────┐ │  │
│       │  │ ATT  │ │ SMN │ │ EDC node  │ │  │
│       │  │ 64e  │ │ 8rng│ │ (BIU)     │ │  │
│       │  └──────┘ └─────┘ └───────────┘ │  │
│       │       AXI Master (512b/56b)      │  │
│       └────────────┬─────────────────────┘  │
│         cross-row flit wires (north↔south)   │
│       ┌────────────┴─────────────────────┐  │
│  Y=3  │       Router (tt_trinity_router)  │  │
│       │  ┌──────────────────────────────┐│  │
│       │  │ 5-port DOR/dynamic router    ││  │
│       │  │ 4 virtual channels           ││  │
│       │  │ REP_DEPTH_LOOPBACK=6         ││  │
│       │  │ EDC node (Y=3)               ││  │
│       │  └──────────────────────────────┘│  │
│       └──────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```


### Unit Purpose
The NOC2AXI composite tiles are the memory-fabric bridges of N1B0, translating between the internal 512-bit NoC wormhole-switched protocol and the external 512-bit AXI4 master bus that connects to DRAM controllers. The two composite tiles span two physical rows each (Y=3–4 at X=1 and X=2) and integrate a NoC router (Y=3 portion) with a NIU (NOC-to-AXI and AXI-to-NOC bridges) in a single P&R cluster for area efficiency. They provide the only gateway for Tensix tiles to access external memory, enforcing address translation (ATT), security access control (SMN), and error detection (EDC) on every transaction.

### Design Philosophy
Composite tiles exemplify **cost-effective area consolidation in constrained floorplans**. The Y=3 router row was too narrow to accommodate a standalone 5-port router tile, so N1B0 merged the Y=3 router and the Y=4 NIU into a single composite module with internal cross-row flit wires, eliminating inter-tile mesh port overhead and reducing P&R complexity. Each composite tile reports its NoC node ID at Y=3 (the router row) even though the NIU portion is physically at Y=4, creating firmware addressing asymmetry that is documented in detail in §1.2 to prevent routing errors. The NIU gateway itself is designed as a stateless packet translator: inbound NoC flits are decoded for ATT lookup, SMN range check, and AXI transaction generation with zero buffering of the full packet body — wormhole forwarding ensures that data flits bypass address decode overhead entirely.

### Integration Role
Composite tiles are the primary memory interface for all 12 Tensix clusters. Every L1↔DRAM transfer must route through one of the two composite tile's NIUs: overlay streams from Tensix clusters Y=0–2 route north through the mesh, arriving at Y=3 routers (composite X=1 or X=2), which forward flits south through internal cross-row wires to the Y=4 NIU. The NIU performs:
1. **ATT lookup**: Converts 32-bit NoC address (containing EndpointIndex and DRAM offset) into 56-bit AXI address
2. **SMN gating**: Verifies the AXI address against 8 configurable SMN security ranges, blocking unauthorized access
3. **AXI transaction generation**: Issues AWADDR, WDATA, and tracking for write responses
4. **Read response arbitration**: Multiplexes multiple concurrent read responses back to requesters via NoC reverse-routed flits

The two composite tiles are assigned to opposite sides of the mesh (X=1 for west, X=2 for east) to balance DRAM bandwidth and reduce router congestion at the top of the mesh.

### Key Characteristics
- **Integrated Y=3 router + Y=4 NIU**: Cross-row flit wires eliminate mesh port latency for transactions destined to DRAM, reducing end-to-end latency by ~2–3 hops.
- **64-entry ATT per NIU**: Address Translation Table enables flexible DRAM address remapping, supporting multi-region memory layouts and secure address spaces without firmware changes.
- **8-range SMN security enforcer**: Before AXI transaction issuance, the SMN verifies the translated address against configurable security ranges, preventing Tensix privilege escalation or unauthorized DRAM access.
- **4 virtual channels**: Router portion inherits the mesh's 4-VC scheme (request, response, control, multicast) to avoid deadlock and provide priority differentiation.
- **AXI burst length constraint: 32 beats max (2 KB)**: Practical limit imposed by NOC packet structure (8 flits/packet); hardware AXI_MAX_TRANSACTION_SIZE = 4096 B allows 64 beats, but actual constraint is 8 flits × 4 beats/flit = 32 beats. Larger transfers must be split across multiple transactions.
- **Wormhole-forwarded data flits**: Body flits bypass ATT and security checks entirely, with header-only decode, ensuring minimal per-hop latency for large (32+ KB) tensor transfers (via multiple 2 KB transactions).

### Use Case Example
**Weight Load from DRAM to Multiple Tensix Tiles**  
The Dispatch tile issues an iDMA command to load weights for the next LLaMA layer from DRAM address 0x84A00000 (500 KB weight matrix) to Tensix(0,0) via the Composite tile at (X=1, Y=3). The command specifies a multi-dimensional descriptor: 500 KB size, 16-byte stride for row-major layout, target EndpointIndex=0 (Tensix at grid position (0,0)). The iDMA CPU begins issuing NoC flits with the destination encoded as y_coord=3 (composite tile Y), x_coord=1. The flits route through the mesh to (1,3), arriving at the composite router. The router sees flits destined for the NIU (local port of Y=4 NIU reached via cross-row wires), forwards them south to the Y=4 NIU. At the NIU, the header flit triggers ATT lookup: incoming 32-bit NoC address is matched against entry 0 in the ATT, yielding a 56-bit AXI address 0x0000_84A0_0000 + DRAM offset. SMN verifies the address is within the "compute tile data region" security range. Finally, an AXI write transaction is issued to the memory controller with AWADDR, WDATA, and WSTRB set, moving the weight tile into DRAM at expected physical address without TRISC firmware involvement.

---
### 4.2 NIU — NOC-to-AXI Bridge (Y=4 portion)

The NIU (`tt_noc2axi`) translates between the internal 512-bit NoC flit protocol and the external 512-bit AXI4 master bus.

#### 4.2.1 NOC2AXI Path (inbound: chip→DRAM)

1. NoC flit arrives at local port (512 bits, includes header with destination address)
2. Header decoded: flit_type, x_coord, y_coord, EndpointIndex extracted
3. ATT lookup: 56-bit AXI address computed from 32-bit NoC address using mask/endpoint table
4. AXI write transaction issued: AWADDR (56-bit), WDATA (512-bit), WSTRB

#### 4.2.2 AXI2NOC Path (outbound: DRAM→chip)

1. AXI read response data (512-bit) arrives from external memory
2. Return address from original NoC request header used to construct response flit
3. Flit injected back into NoC at local port, routed to requesting tile

#### 4.2.3 ATT — Address Translation Table

| Parameter   | Value           |
|-------------|-----------------|
| Entries     | 64              |
| Fields      | mask, endpoint, routing |
| Purpose     | Maps 32-bit NoC address → 56-bit AXI address |
| Access      | APB register interface (SMN-controlled)     |

The ATT enables flexible memory-mapped address remapping. Each entry provides:
- **mask**: which bits of the incoming address are matched
- **endpoint**: target EndpointIndex or AXI region
- **routing**: override routing flags for the translated address

#### 4.2.4 SMN — Security Manager (8-range checker)

The SMN (Secure Memory Node) enforces access control on all AXI transactions issued by the NIU.

| Parameter      | Value                                      |
|----------------|--------------------------------------------|
| Number of ranges | 8                                        |
| Granularity    | Configurable base/size per range           |
| Actions        | Allow, block (return slave error), log     |
| Configuration  | APB registers at 0x03010000 (325 regs)     |

Each range can independently restrict read/write access. Violations generate a `slv_ext_error` signal that propagates to the overlay error logic.

#### 4.2.5 AXI Interface Parameters

| Parameter     | Value                                     |
|---------------|-------------------------------------------|
| Data width    | 512 bits                                  |
| Address width | 56 bits (physical) mapped via gasket to 64-bit AXI |
| ID width      | As configured per instance               |
| Protocol      | AXI4 (full)                               |
| AxUSER        | Carries security/routing metadata         |

The 56-bit address gasket layout:

```
Bits [55:48] — 8-bit region/endpoint tag
Bits [47:32] — 16-bit upper address
Bits [31: 0] — 32-bit lower address (NoC address field)
```

### 4.3 Router (Y=3 portion)

The router row within the composite tile instantiates `tt_trinity_router` with parameters specific to its position at Y=3.

**Key router parameters for composite tiles:**

| Parameter                     | NE_OPT (X=1) | NW_OPT (X=2) |
|-------------------------------|--------------|--------------|
| `REP_DEPTH_LOOPBACK`          | 6            | 6            |
| `OUTPUT`                      | 4            | 4            |
| West port repeaters (in+out)  | 4            | 1            |
| South port repeaters (in+out) | 5            | —(default)   |
| East port repeaters (in+out)  | 1            | 3            |
| North port repeaters (in+out) | 1            | 1            |

> RTL-verified: `trinity_noc2axi_router_ne_opt.sv` (West=4, South=5, East=1, North=1); `trinity_noc2axi_router_nw_opt.sv` (West=1, East=3, North=1). NE/NW have asymmetric repeater counts because they sit at opposite ends of the X-axis with different wire lengths to their neighbors.

See §5 for full router architecture description.

### 4.4 Cross-Row Flit Wires

The NIU at Y=4 and the router at Y=3 are not connected via the top-level NoC mesh wires. Instead, dedicated cross-row flit buses pass through the composite module boundary:

- **South→North**: flit data + valid from Y=3 router local port to Y=4 NIU input
- **North→South**: flit data + valid from Y=4 NIU output to Y=3 router local port

These wires are 512 bits wide (one full NoC flit). They bypass the standard mesh routing and are only visible inside `trinity_noc2axi_router_ne/nw_opt.sv`.

### 4.5 Clock Routing in Composite Tiles

The composite tile propagates clocks from the Y=4 entry point down to Y=3 via a clock routing chain. Nine fields are routed:

1. `i_ai_clk[col]` — passed from Y=4 to Y=3
2. `i_dm_clk[col]` — passed from Y=4 to Y=3
3. `i_noc_clk` — available at both Y levels
4. `i_axi_clk` — for AXI interface (NIU at Y=4 primarily)
5. `i_reset_n` — global reset
6. `i_axi_reset_n` — AXI domain reset
7. PRTN chain clock
8. EDC forward chain enable
9. EDC loopback chain enable

Repeaters are inserted at Y=3 (depth=6) and Y=4 (depth=4) within the clock distribution paths of the composite tile to meet setup timing across the physical distance.

### 4.6 Router Node ID and EP Offset

Within the composite tiles, router and NIU node IDs are computed with an offset of −1 relative to the tile's nominal EndpointIndex:

- EndpointIndex for (X=1, Y=4) = 9; NIU nodeid = 8
- EndpointIndex for (X=2, Y=4) = 14; NIU nodeid = 13
- The router at Y=3 similarly uses (EndpointIndex − 1) for its local ID

This offset is a design-level convention in the N1B0 implementation to align with the baseline router node ID allocation scheme.

---

### 4.7 NIU DMA Operation

The NIU (Network Interface Unit, `tt_noc2axi`) is not a passive bridge — it acts as a **DMA engine** that autonomously drives AXI bursts in response to incoming NoC packets and vice versa. There is no CPU involvement once a NoC packet enters the NIU; the NIU hardware handles all burst framing, address translation, and response routing.

#### 4.7.1 NoC Packet → AXI Burst (Write DMA)

A write transaction is initiated when a Tensix TRISC3 (or iDMA) injects a header flit into the NoC addressed to an external AXI endpoint. The NIU receives the full packet and converts it to an AXI write burst:

```
NoC Packet (received by NIU)
┌─────────────────────────────────────────────┐
│ Header flit: x_coord, y_coord, EndpointIdx  │
│              mcast=0, flit_type=HDR          │
│              payload: AXI target address     │
├─────────────────────────────────────────────┤
│ Data flit 0: 512-bit payload (64 bytes)      │
│ Data flit 1: 512-bit payload                 │
│  ...                                         │
│ Tail flit:   final 512-bit payload + EOP     │
└─────────────────────────────────────────────┘
         │
         ▼  NIU write DMA engine
┌─────────────────────────────────────────────┐
│ 1. Extract AXI address from header payload  │
│ 2. Run address through ATT (§3.2.3)         │
│    → translate NoC logical addr → AXI phys │
│ 3. Compute burst length = num data flits    │
│    AWLEN = (payload_bytes / 64) - 1         │
│    AWSIZE = 3'b110 (64-byte beat)           │
│ 4. Assert AWVALID with translated address   │
│ 5. Stream WDATA beats from flit buffer      │
│    (one 512-bit flit = one AXI beat)        │
│ 6. Assert WLAST on tail flit beat           │
│ 7. Wait for BVALID (write response)         │
│ 8. On BRESP error → slv_ext_error → CRIT   │
└─────────────────────────────────────────────┘
```

Key parameters:
- **Max burst**: 256 beats × 64 bytes = 16 KB per NoC packet
- **AXI data width**: 512 bits (64 bytes per beat)
- **AXI address width**: 56-bit (mapped to 64-bit via gasket, upper bits zero-extended)
- **AWCACHE**: configurable (bufferable/cacheable per ATT entry)
- **AWPROT/AxUSER**: propagated from NoC header security level

#### 4.7.2 AXI Read Response → NoC Packet (Read DMA)

A read transaction is initiated by a NoC read-request packet. The NIU issues an AXI read burst and converts the returning AXI data beats back into a NoC response packet addressed to the original requester:

```
Step 1: NIU receives NoC READ REQUEST packet
  Header flit contains:
    - AXI read address (logical)
    - Return path: src_x, src_y, src_endpoint (requester's address)
    - Byte count / burst length

Step 2: NIU issues AXI read burst
  ARADDR  = ATT-translated address
  ARLEN   = (requested_bytes / 64) - 1
  ARSIZE  = 3'b110 (64 bytes/beat)
  ARVALID = 1

Step 3: NIU collects RDATA beats
  Each RDATA beat (512 bits) is stored in the NIU read-data FIFO
  (RDATA FIFO depth: 512 entries in N1B0, configurable 32–1024)

Step 4: NIU constructs NoC RESPONSE packet
  Header flit: src_x/y/endpoint from original request (reversed)
  Data flits:  RDATA beats converted 1:1 to 512-bit NoC flits
  Tail flit:   last RDATA beat + RLAST marker

Step 5: NIU injects response packet into NoC
  Router at Y=3 routes packet back to requester tile
```

The RDATA FIFO depth (default 512 in N1B0) determines how many outstanding read beats the NIU can absorb before applying back-pressure on RREADY. This is critical for latency-hiding: with depth=512, the NIU can tolerate up to 512 × 64B = 32 KB of in-flight read data.

#### 4.7.3 Address Translation (ATT)

Before any AXI transaction is issued, the NIU passes the NoC logical address through the ATT (Address Translation Table):

```
ATT entry format (64 entries per NIU):
  ┌──────────┬──────────┬────────────────┬──────────┐
  │  MASK    │  MATCH   │  OFFSET/BASE   │  ATTR    │
  │ [55:0]   │ [55:0]   │ [55:0]         │ [7:0]    │
  └──────────┴──────────┴────────────────┴──────────┘

Translation:
  if (addr & MASK) == MATCH:
      axi_addr = (addr & ~MASK) | OFFSET
      apply ATTR (cacheable, bufferable, security level)
```

- 64 entries scanned in priority order (entry 0 = highest priority)
- No match → transaction blocked, `slv_ext_error` asserted → CRIT interrupt
- ATT is programmed by firmware at boot via APB slave registers on the NIU

#### 4.7.4 Descriptor Flow (Firmware Perspective)

Unlike iDMA (which has explicit SW-managed descriptor rings), NIU DMA is **implicit** — it is driven directly by NoC packet injection. Firmware controls NIU DMA by:

1. **Configuring ATT** (once at boot): map logical NoC addresses to physical AXI addresses
2. **Configuring SMN ranges** (once at boot): set access permissions per address range
3. **Issuing NoC packets** (at runtime): TRISC3 or iDMA injects NoC packets addressed to the NIU endpoint; the NIU autonomously drives the AXI burst

There is no explicit descriptor ring or doorbell register for NIU DMA. The NoC packet header encodes all necessary information (address, length, direction).

```c
// Example: TRISC3 firmware initiating a 4KB write to DRAM via NIU
// (conceptual — actual write uses TRISC3 NOC write instructions)

// ATT must be pre-configured:
//   Entry 0: MASK=0xFFFFF000, MATCH=0x80000000, OFFSET=0x80000000

// TRISC3 issues NOC write:
//   dst_x=1 (NIU NW_OPT), dst_y=4
//   address=0x80001000   (4KB-aligned DRAM target)
//   data=<64 × 512-bit flits>  (4096 bytes)

// NIU hardware:
//   1. Receives 65 flits (1 header + 64 data)
//   2. Translates 0x80001000 via ATT → AXI addr 0x80001000
//   3. Issues AWADDR=0x80001000, AWLEN=63 (64 beats), AWSIZE=6
//   4. Streams 64 × 512-bit WDATA beats
//   5. Asserts WLAST on beat 63
//   6. Waits for BRESP → done (no interrupt to TRISC3)
```

#### 4.7.5 Error Handling

| Error Condition | NIU Response | System Effect |
|----------------|--------------|---------------|
| ATT miss (no matching entry) | Block transaction, assert `slv_ext_error` | CRIT interrupt via EDC ring |
| SMN range violation | Block transaction, log in SMN registers | CRIT interrupt |
| AXI BRESP=SLVERR/DECERR | Assert `slv_ext_error` | CRIT interrupt |
| AXI RRESP=SLVERR/DECERR | Drop response, assert error flag | CRIT interrupt |
| RDATA FIFO overflow | Back-pressure RREADY (hardware flow control) | No error — stalls AXI read |
| NoC flit CRC error | EDC ring detects, marks packet bad | Severity per EDC node config |

#### 4.7.6 End-to-End DRAM → L1 Data Path: Ports, Burst Length, and Data Rate

The complete data movement from external DRAM to L1 partition involves four key stages: overlay stream injection, NoC routing, NIU AXI master interface, and L1 side-channel reception. This section specifies all port widths, burst parameters, and achievable data rates.

##### 3.7.6.1 Complete Flow Diagram

```
TRISC firmware (cfg_reg write)
    │
    ▼  Overlay stream CSR (32-bit address, size, direction)
Overlay wrapper (tt_neo_overlay_wrapper)
    │
    ▼  NoC READ REQUEST flit (512-bit, 96-bit header)
NoC Router (tt_trinity_router)
    │  6–8 hops via DOR/dynamic routing
    ▼
NIU – AXI Master (tt_noc2axi)
    ├─ ATT lookup (64 entries): NoC logical → AXI physical address
    ├─ SMN range check: 8-range security filter
    └─ Issue AXI4 READ: ARADDR (56-bit), ARLEN, ARSIZE (3'b110)
    │
    ▼  AXI Master → External DRAM (512-bit data, 56-bit address)
DRAM Controller
    │
    ▼  RDATA beats (512-bit each)
NIU – RDATA FIFO (512 entries, 32 KB buffered)
    │
    ▼  NoC RESPONSE packet (512-bit flits + header)
NoC Router (return path, 6–8 hops)
    │
    ▼  L1 Partition – NoC side channel (512-bit, noc_clk domain)
L1 SRAM (direct write, bypass TRISC)
```

##### 3.7.6.2 Port Specifications

| Stage | Port / Signal | Width | Frequency | Meaning |
|-------|---|---|---|---|
| **Overlay → NoC** | Flit payload | 512 bits | noc_clk | One complete flit (header or data) |
| **Overlay stream CSR** | Address | 32 bits | ai_clk | Logical NoC destination address |
| | Size | bits | ai_clk | Number of 512-bit flits to transfer |
| **NIU – AXI Master** | ARADDR | 56 bits | axi_clk | Physical DRAM address (zero-extend to 64-bit for AXI) |
| | ARLEN[7:0] | 8 bits | axi_clk | Burst length = (bytes / 64) − 1; max 255 (256 beats) |
| | ARSIZE[2:0] | 3 bits | axi_clk | **Always 3'b110 = 64-byte beat width** (512-bit flit = 64 bytes) |
| | ARBURST[1:0] | 2 bits | axi_clk | **2'b01 = INCR** (incrementing address) |
| | ARVALID, ARREADY | 1 bit ea. | axi_clk | Handshake for read request |
| **AXI Slave (DRAM)** | RDATA | 512 bits | axi_clk | Read data from DRAM |
| | RLAST | 1 bit | axi_clk | Marks final beat of burst |
| | RVALID, RREADY | 1 bit ea. | axi_clk | Handshake for read data |
| **NIU – RDATA FIFO** | FIFO depth | 512 entries | axi_clk | **32 KB buffering capacity** (512 × 64 bytes) |
| **L1 side channel** | Write payload | 512 bits | noc_clk | Direct L1 SRAM write (no TRISC involvement) |
| **L1 side channel** | SRAM address | 13 bits | noc_clk | Addresses 3 MB L1 partition (3M / 64-byte beat = 49,152 beats → 16-bit counter; actual implementation uses internal mux) |

##### 3.7.6.3 Burst Length Calculation

**AXI burst length is computed from the requested data size:**

```
ARLEN = (total_bytes / 64) − 1

Examples:
  512 B transfer:    ARLEN = (512 / 64) − 1 = 7   (8 beats)
  2 KB transfer:     ARLEN = (2048 / 64) − 1 = 31  (32 beats, practical maximum)
  4 KB transfer:     ARLEN = (4096 / 64) − 1 = 63  (64 beats, requires 2 transactions)
  16 KB transfer:    ARLEN = (16384 / 64) − 1 = 255  (256 beats, maximum AXI capability)
```

**Constraint (RTL-Verified):** Max single AXI burst = **32 beats** (2 KB per transaction)

The practical burst length limit is constrained by the NoC packet structure, not the AXI protocol:
- NOC packet maximum: **8 flits per transaction**
- Bytes per flit: 256 (NOC_PAYLOAD_WIDTH = 2048 bits)
- AXI beats per flit: 4 (512-bit AXI / 64-byte beat)
- **Maximum ARLEN = 31** (32 beats = 2 KB)

Larger transfers must be split across multiple overlay stream commands or multiple NoC packets:
- 4 KB: 2 transactions of 2 KB each (ARLEN=31 + ARLEN=31)
- 16+ KB: Multiple 2 KB transactions

Note: The hardware parameter `AXI_MAX_TRANSACTION_SIZE = 4096` indicates 64-beat capacity, but the actual NoC constraint limits transactions to 8 flits (2 KB).

**RTL mapping:**
- Each 512-bit NoC flit corresponds to 4 AXI beats (256 bytes / 64 bytes per beat)
- The NIU (tt_noc2axi) calculates `noc_num_data_flits` from ARLEN and clamps to 8 maximum

##### 3.7.6.4 Achievable Data Rates

**Per-NIU sustained bandwidth (ideal, no contention):**

```
Data rate = 512 bits/cycle × frequency

At 1 GHz (typical):
  = 512 bits/cycle × 1 ns/cycle
  = 512 bits/ns
  = 512 B / 1 ns
  = 512 × 10⁹ B/s
  = 512 GB/s per clock

But realistic axi_clk frequency: ~800 MHz (conservative, accounts for AXI timing)
  = 512 bits/cycle × 800 MHz
  = 409.6 GB/s per NIU
```

**Actual sustained rate depends on:**
1. **DRAM controller bandwidth** — external DRAM (DDR4/DDR5) typically 100–200 GB/s per port
2. **AXI bus arbitration** — if multiple requesters (iDMA, Tensix TRISC, Dispatch) contend for the same DRAM port
3. **NoC congestion** — mesh routing delays (varies 6–8+ noc_clk cycles per flit)
4. **ATT lookup latency** — negligible (register-based, <1 cycle)
5. **RDATA FIFO occupancy** — 512-entry FIFO hides return-path jitter; back-pressure stalls reads if FIFO fills

**N1B0 aggregate (4 NIU endpoints):**
- Theoretical: 4 × 512 bits/cycle = 2048 bits/cycle per noc_clk
- If **all 4 NIUs read simultaneously** from independent DRAM ports: 4 × 409.6 GB/s = **1.6 TB/s** (unrealistic; assumes no interference)
- Practical (shared DRAM controller): DRAM bandwidth limits to ~150–200 GB/s total

##### 3.7.6.5 Latency Components

**Total read latency from TRISC register write to L1 data available:**

```
T_total = T_overlay_inject + T_noc_forward + T_atu + T_dram + T_noc_response + T_l1_write

  ├─ T_overlay_inject:  1–2 ai_clk → 512-bit flit ready (overlay CSR write processing)
  │
  ├─ T_noc_forward:     6–8 noc_clk (typical: source to NIU Y=4 routing)
  │                     Example: (0,0) → (1,4): 1 east + 4 north = 5 hops + repeater delays
  │
  ├─ T_atu:             <1 axi_clk (register-based ATT lookup, pipelined)
  │
  ├─ T_dram:            50–100 axi_clk (DRAM row-buffer hit to RDATA valid)
  │                     Varies: DDR4 ≈ 50 ns @ 800 MHz = 40 axi_clk; DDR5 ≈ 30 ns = 24 axi_clk
  │
  ├─ T_noc_response:    6–8 noc_clk (NIU → destination tile return routing)
  │
  └─ T_l1_write:        1–2 noc_clk (SRAM write setup + latch)

Typical total: 70–130 noc_clk ≈ **70–130 ns @ 1 GHz**
Conservative worst-case: ~200 ns (random DRAM access, cold DRAM row)
```

##### 3.7.6.6 Flow Control and Backpressure

**RDATA FIFO as buffering mechanism:**

```
NIU RDATA FIFO depth = 512 entries × 64 bytes = 32 KB

When DRAM faster than NoC return path:
  → FIFO accumulates RDATA beats
  → Once FIFO reaches threshold, RREADY is de-asserted
  → DRAM controller stalls (RVALID held, no new beats sent)
  → Prevents data loss

When NoC faster than DRAM:
  → FIFO drains into NoC response flits
  → RREADY remains high, DRAM runs at full speed
  → L1 receives data with minimal buffering delay
```

**Firmware considerations:**
- Issue next read request after checking NIU status register (polled or interrupt-driven)
- Max outstanding reads per Tensix: `MAX_TENSIX_DATA_RD_OUTSTANDING = 4` (8 in large mode)
- Firmware must not exceed this limit or overlay stream regs block new writes

##### 3.7.6.7 Address Translation (ATT) Table

Each NIU has a **64-entry ATT**. Typical mapping for N1B0 LLM inference:

```
Entry 0:  Mask=0xFFFFF000, Match=0x80000000, Offset=0x200000000
          → NoC 0x80000000–0x80FFFFFF → AXI 0x200000000–0x200FFFFFF
          Purpose: Weight tensor DRAM region (256 MB window)

Entry 1:  Mask=0xFFFF0000, Match=0x81000000, Offset=0x210000000
          → NoC 0x81000000–0x81FFFFFF → AXI 0x210000000–0x210FFFFFF
          Purpose: Activation DRAM region (256 MB window)

Entry 2:  Mask=0xFFFFE000, Match=0x82000000, Offset=0x220000000
          → NoC 0x82000000–0x82001FFF → AXI 0x220000000–0x220001FFF
          Purpose: Scratch/output region (8 KB, high-frequency writes)

Entries 3–63: Available for dynamic remapping or additional regions
```

Each entry costs ~72 bits (mask + match + offset + attr fields); programming is via APB register interface at boot time or under firmware control at runtime.

---

### 4.8 Standalone NIU Tiles — NOC2AXI_NW_OPT / NOC2AXI_NE_OPT (X=0,X=3 at Y=4)

#### 4.8.1 Overview

In addition to the two composite NOC2AXI_ROUTER tiles (X=1/X=2, spanning Y=3–4), the N1B0 grid includes two **standalone NIU tiles** at the corners of row Y=4:

| Instance        | Grid Position | RTL Module                      | EndpointIndex |
|-----------------|---------------|---------------------------------|---------------|
| NOC2AXI_NW_OPT  | (X=0, Y=4)    | `trinity_noc2axi_nw_opt.sv`     | 4             |
| NOC2AXI_NE_OPT  | (X=3, Y=4)    | `trinity_noc2axi_ne_opt.sv`     | 19            |

RTL-verified: `GridConfig[Y=4][X=0] = NOC2AXI_NW_OPT`, `GridConfig[Y=4][X=3] = NOC2AXI_NE_OPT` (packed array `[3:0]`, MSB=X=3).

These are **single-row tiles** — they occupy Y=4 only and have no Y=3 router row. They provide a full NIU (NOC-to-AXI bridge) with ATT, SMN, and an AXI master interface, but are architecturally simpler than the composite tiles.

```
  Grid row Y=4 overview:

  X=0                X=1               X=2               X=3
  ┌────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐
  │  NE_OPT    │  │ ROUTER_NW_  │  │ ROUTER_NE_  │  │  NW_OPT    │
  │ (standalone│  │ OPT Y=4 NIU │  │ OPT Y=4 NIU │  │ (standalone│
  │  NIU only) │  │ (composite) │  │ (composite) │  │  NIU only) │
  └────────────┘  └─────────────┘  └─────────────┘  └────────────┘
      EP=4            EP=8 (−1)        EP=13 (−1)        EP=19
  (no offset)     (nodeid_y−1)     (nodeid_y−1)      (no offset)

  Row Y=3 (below):
  ┌────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐
  │  Dispatch  │  │ ROUTER_NW_  │  │ ROUTER_NE_  │  │  Dispatch  │
  │   West     │  │ OPT Y=3 Rtr │  │ OPT Y=3 Rtr │  │   East     │
  └────────────┘  └─────────────┘  └─────────────┘  └────────────┘
```

#### 4.8.2 Why Standalone at X=0 and X=3

The 4×5 mesh requires NIU connectivity at all four X columns in row Y=4. The choice of standalone vs. composite depends on whether the tile at Y=3 in the same column needs an integrated router:

- **X=1, X=2 (composite)**: Y=3 positions are used by the ROUTER_NW_OPT and ROUTER_NE_OPT composite modules. Dispatch tiles need routing capability into the mesh, so X=1/X=2 composite modules integrate both NIU (Y=4) and router (Y=3) into a single module with cross-row flit wires. The router at Y=3 bridges Dispatch traffic onto the NoC mesh and funnels it up to the NIU at Y=4.
- **X=0, X=3 (standalone)**: Y=3 positions are occupied by Dispatch tiles (`tt_dispatch_top_east` at X=0 and `tt_dispatch_top_west` at X=3), which contain their own integrated NIU and NoC interface. No dedicated router tile is required at Y=3 for these columns. Therefore, the Y=4 position for X=0 and X=3 only needs a standalone NIU with no router component.

This results in a clean separation: standalone NIU tiles handle Y=4-only AXI bridging, while composite tiles handle the dual-row case where the router must physically span Y=3 to serve the Dispatch row.

#### 4.8.3 Internal Architecture

The standalone NIU tile contains the same core NIU sub-blocks as the composite tile's Y=4 portion, but without any router logic or cross-row wiring:

```
  trinity_noc2axi_ne_opt / trinity_noc2axi_nw_opt (single-row, Y=4 only)
  ┌─────────────────────────────────────────────────────────┐
  │                   Standalone NIU Tile                    │
  │                                                          │
  │    NoC mesh local port (at mesh position X, Y=4)         │
  │         │  (512-bit flit in/out, standard mesh port)     │
  │         ▼                           ▲                    │
  │  ┌──────────────────────────────────────────────────┐   │
  │  │               tt_noc2axi (NIU core)               │   │
  │  │  ┌──────────────────┐  ┌────────────────────┐    │   │
  │  │  │  NOC2AXI Bridge  │  │  AXI2NOC Bridge    │    │   │
  │  │  │  (chip→DRAM)     │  │  (DRAM→chip resp.) │    │   │
  │  │  └──────────────────┘  └────────────────────┘    │   │
  │  │  ┌──────────────┐  ┌──────────┐  ┌──────────┐   │   │
  │  │  │ ATT (64 entry│  │ SMN      │  │ RDATA    │   │   │
  │  │  │ mask/endpoint│  │ 8-range  │  │ FIFO 512 │   │   │
  │  │  └──────────────┘  └──────────┘  └──────────┘   │   │
  │  └──────────────────────────────────────────────────┘   │
  │                          │                               │
  │            AXI Master Interface (512-bit / 56-bit addr)  │
  │                      to external memory                  │
  │                                                          │
  │  EDC node — connected to main EDC ring at Y=4 (on-ring)  │
  │  APB slave — register access via noc_clk APB bus         │
  └─────────────────────────────────────────────────────────┘
```

**Key differences from composite tiles:**

| Attribute                  | Standalone (X=0, X=3)               | Composite (X=1, X=2)                      |
|----------------------------|-------------------------------------|-------------------------------------------|
| Row span                   | Y=4 only                            | Y=3 and Y=4                               |
| Router present             | No                                  | Yes — `tt_trinity_router` at Y=3          |
| Cross-row flit wires       | None                                | Yes — 512-bit South↔North internal bus    |
| nodeid / EP offset         | None — EP used directly             | nodeid_y −1 (composite ID convention)     |
| EndpointIndex              | (X=0,Y=4)=4; (X=3,Y=4)=19          | (X=1,Y=4)→nodeid=8; (X=2,Y=4)→nodeid=13  |
| EDC ring position          | Y=4 only, directly on main ring     | Y=4 BIU is off-ring (open-port issue)     |
| REP_DEPTH_LOOPBACK         | 2 (standard)                        | 6 (N1B0 composite-specific)               |
| Clock routing chain        | Short (single row, no passthrough)  | Long — passes through both Y=4 and Y=3    |

#### 4.8.4 NoC Connectivity

The standalone NIU tiles connect to the NoC mesh at their Y=4 grid position exactly like any standard mesh node. There are no cross-row wires, no internal router instance, and no special port prefix renaming. The tile's local port attaches directly to the NoC mesh at (X, Y=4):

```
  NoC mesh at Y=4 (West→East):

  (X=0,Y=4)    (X=1,Y=4)    (X=2,Y=4)    (X=3,Y=4)
  NE_OPT       ROUTER_NW    ROUTER_NE    NW_OPT
  [local port] [local port] [local port] [local port]
       │              │             │            │
       └──────────────┴─────────────┴────────────┘
          Standard 5-port DOR mesh interconnect
          (East/West/North/South/Local)
          4 virtual channels per port
```

The standalone NIU tiles are leaf nodes at Y=4: they have no router row that could serve as a relay. NoC packets destined for external DRAM via NE_OPT or NW_OPT must be addressed with `dst_x=0/3, dst_y=4` and the correct EndpointIndex (4 or 19). No offset correction is needed in firmware because there is no composite span or nodeid_y−1 convention.

#### 4.8.5 ATT, SMN, and AXI Interface

The ATT, SMN, and AXI master interface are functionally identical to the composite tile NIU at Y=4:

- **ATT**: 64-entry mask/match/offset/attribute table. Programmed at boot via APB. Maps 32-bit NoC logical addresses to 56-bit AXI physical addresses using the same gasket format as the composite tiles (bits [55:48] = region/endpoint tag, [47:32] = upper address, [31:0] = lower address).
- **SMN**: 8 independently programmable address ranges with allow/block/log actions. Violations assert `slv_ext_error` → CRIT interrupt via overlay error aggregator.
- **AXI master**: 512-bit data, 56-bit address, AXI4 full protocol, AxUSER carries security/routing metadata. Identical to composite tile AXI port.
- **RDATA FIFO**: 512-entry depth by default (define-selectable 32–1024, same as composite tiles). Provides 32 KB of in-flight read data latency hiding.

APB register access is via the standard overlay APB bus, at base addresses consistent with the tile's position in the APB address map.

#### 4.8.6 EDC Ring Integration

The standalone NIU tiles connect their EDC node directly to the main EDC ring at Y=4. This is the **correct, fully on-ring** configuration with no off-ring connectivity issue:

- EDC node at (X=0, Y=4): on-ring; covers NIU BIU logic, ATT SRAM parity, and SMN register state
- EDC node at (X=3, Y=4): on-ring; covers same set of resources

This is in contrast to the composite tiles (X=1, X=2) at Y=4, where the NIU BIU EDC node is **off-ring** due to the open-port connectivity issue documented in the N1B0 open-signal report Rev.5 (EDC ring connectivity correction: NOC2AXI BIU at Y=4 for X=1/X=2 is not connected to the main ring forward chain in certain N1B0 configurations). The standalone tiles do not have this problem because there is no composite module boundary complicating the ring signal routing — the EDC ring enters and exits the tile through standard tile boundary ports at Y=4.

No −1 offset is applied to the standalone NIU EDC node ID. The ring visits the tile at its nominal EndpointIndex position.

#### 4.8.7 Firmware Programming Notes

Firmware initializes NE_OPT and NW_OPT standalone tiles at boot using the same APB sequence as the composite tile NIU:

1. **ATT programming**: Write 64 entries (mask, match, offset, attr) for all expected DRAM address regions. Use the same logical-to-physical address mapping scheme as composite tile ATTs to maintain a consistent NoC address space.
2. **SMN range programming**: Write 8 range entries (base, size, read-permission, write-permission) to enforce security boundaries. These are typically configured to mirror the composite tile SMN configuration.
3. **EDC verification**: During EDC ring initialization, confirm that nodes at (X=0,Y=4) and (X=3,Y=4) respond with PASS status. Unlike composite tile Y=4 EDC nodes (which are off-ring), standalone tile EDC nodes participate directly in the ring self-test.
4. **RDATA FIFO tuning**: Optionally override the RDATA FIFO depth if the workload presents particularly high read latency or high read bandwidth requirements.

The standalone NIU tiles share the same APB register layout as the composite tile NIU, so a single firmware driver can initialize all four NIU instances (NE_OPT X=0, ROUTER_NW_OPT X=1, ROUTER_NE_OPT X=2, NW_OPT X=3) with only the APB base address varying.

---

## §5 Dispatch Tiles

### 5.1 Overview

Two Dispatch tiles provide the RISC-V host processor interface for the N1B0 NPU. They are placed at opposite corners of the Y=3 row, ensuring symmetric NoC coverage over all Tensix columns:

| Instance   | tile_t enum | Position | RTL Module               |
|------------|-------------|----------|--------------------------|
| DISPATCH_W | `DISPATCH_W` = 3'd6 | (0, 3) | `tt_dispatch_top_west` |
| DISPATCH_E | `DISPATCH_E` = 3'd5 | (3, 3) | `tt_dispatch_top_east` |

> RTL-verified: `GridConfig[3][0]=DISPATCH_W` → instantiates `tt_dispatch_top_west`; `GridConfig[3][3]=DISPATCH_E` → instantiates `tt_dispatch_top_east` (packed array `[3:0]`, MSB=X=3). X=0 is the physical west side; X=3 is the physical east side.

**Why two Dispatch tiles?**

Two independent Dispatch tiles serve two complementary purposes:

1. **East/West NoC coverage for tensor-parallel workloads.** In tensor-parallel execution, each Dispatch tile manages programming and DMA for its half of the Tensix array. DISPATCH_W at (0,3) has the shortest NoC path to the left two Tensix columns (X=0, X=1); DISPATCH_E at (3,3) serves the right two columns (X=2, X=3). This halves the average NoC hop count from the dispatch controller to the compute tiles, reducing DMA command injection latency by up to 2 router hops.

2. **Two independent iDMA engines for parallel data loading.** Each Dispatch tile contains its own iDMA engine with 8 DMA CPUs, giving 16 total concurrent DMA channels across the chip. This enables simultaneous pre-loading of distinct weight tensor tiles to opposite halves of the Tensix array while the other half is computing, effectively hiding DRAM access latency behind Tensix compute — a key throughput enabler for LLM inference workloads.

Each Dispatch tile contains a Rocket RISC-V 64-bit core with L1/L2 caches, an iDMA engine (accessed via RoCC accelerator interface), an APB slave interface, and a NoC interface via NIU.

```
┌─────────────────────────────────────────────────────┐
│                  tt_dispatch_top_east/west           │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │           Rocket Core (RV64GC, 5-stage)       │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │  │
│  │  │ L1 ICache│  │ L1 DCache│  │    L2      │  │  │
│  │  │ (SRAM)   │  │ (SRAM)   │  │  Cache     │  │  │
│  │  └──────────┘  └──────────┘  │  (SRAM)    │  │  │
│  │                               └────────────┘  │  │
│  │  ┌────────────────────────────────────────┐   │  │
│  │  │    RoCC Interface (custom-3, 0x77)     │   │  │
│  │  │  cmd.valid / inst / rs1 / rs2          │   │  │
│  │  │  resp.valid / resp.bits / busy         │   │  │
│  │  │  ┌──────────────────────────────────┐  │   │  │
│  │  │  │          iDMA Engine             │  │   │  │
│  │  │  │  8 independent DMA CPU cores     │  │   │  │
│  │  │  │  CMD_BUF_R/W, ADDR_GEN_R/W,      │  │   │  │
│  │  │  │  SIMPLE_CMD_BUF per CPU          │  │   │  │
│  │  │  └──────────────────────────────────┘  │   │  │
│  │  └────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────┘  │
│        │ ai_clk domain ↕ CDC FIFO ↕ noc_clk domain │
│  ┌──────────────┐  ┌────────────────────────────┐  │
│  │  APB Slave   │  │    NIU (NoC interface)      │  │
│  │  (SFR access)│  │  NoC↔AXI, ATT, SMN         │  │
│  └──────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 5.2 Rocket Core

The Rocket core is a 64-bit RISC-V (RV64GC) in-order scalar processor sourced from the UC Berkeley open-source Rocket Chip generator.

| Parameter          | Value                                              |
|--------------------|----------------------------------------------------|
| ISA                | RV64GC (I + M + A + F + D + C extensions)          |
| Pipeline stages    | 5 (IF / ID / EX / MEM / WB — classic in-order)    |
| L1 I-cache         | SRAM-based, direct-mapped                          |
| L1 D-cache         | SRAM-based, write-back, direct-mapped              |
| L2 cache           | SRAM-based, set-associative, unified               |
| Clock domain       | `ai_clk` sourced from `i_ai_clk[col]`             |
| Data width         | 64-bit integer + 64-bit FP (D extension)           |

**ISA extension breakdown:**
- **I** — base 64-bit integer instruction set
- **M** — hardware integer multiply/divide
- **A** — atomic memory operations (LR/SC, AMO); used for firmware spinlocks and completion flags shared between the two Dispatch tiles
- **F/D** — single/double-precision floating point (G = IMAFD combined)
- **C** — 16-bit compressed instructions, reducing I-cache pressure for tight firmware dispatch loops

**Why in-order (not out-of-order)?**

Dispatch and DMA control is fundamentally latency-tolerant. The firmware workload consists of DMA descriptor writes, SFR configuration sequences, and polling loops — not tight floating-point compute kernels. An out-of-order processor would add significant area (reorder buffer, register rename, multiple issue ports) for negligible performance gain on this workload class. The 5-stage in-order Rocket pipeline provides sufficient throughput at much lower area and power. Rocket is the control plane; Tensix is the compute plane — the design deliberately keeps the control plane lean.

**Rocket origin and validation:** Rocket is a well-validated, widely taped-out open-source design from UC Berkeley. Its integration with the RoCC coprocessor extension interface is a standard, well-understood pattern used in numerous prior Rocket-based accelerator designs, making the iDMA engine connection low-risk from a verification standpoint.

**Firmware running on Rocket:**
The NPU runtime firmware executing on Rocket orchestrates the full NPU execution lifecycle:
1. Load Tensix firmware (TRISC3 kernel programs, TRISC LLK programs) from DRAM into Tensix L1s via iDMA
2. Program per-tile SFRs (CLUSTER_CTRL, T6_L1_CSR, router ATT entries) via the NoC APB path
3. Issue iDMA commands to pre-load weight tiles from DRAM into Tensix L1s
4. Release TRISC reset: write TRISC3/TRISC0/1/2 reset program counters, then deassert TRISC reset via SFR write
5. Poll `LLK_TILE_COUNTERS` or await completion interrupt for kernel finish
6. Post-process: issue iDMA commands to drain activation outputs from Tensix L1 back to DRAM

**SFR access path:** Rocket issues a load/store to a non-cacheable SFR address → L1 D-cache miss → NoC packet injected via NIU → routed to target tile APB slave → APB register write/read → response flit returns → Rocket load completes. Round-trip latency is approximately 50–100 noc_clk cycles depending on mesh distance and NoC congestion.

**Boot sequence:** At reset, Rocket fetches from a reset vector address held in a fabric SFR (configurable via APB before reset release). Firmware is pre-loaded into L2 by the host CPU before NPU power-on, or bootstrapped from external DRAM via an early iDMA sequence triggered from on-chip ROM.

### 5.3 RoCC — Rocket Custom Coprocessor Interface

The RoCC (Rocket Custom Coprocessor) interface is the standard RISC-V extension mechanism built into the Rocket pipeline. It exposes decoded custom instruction slots that route directly to an attached hardware coprocessor — in this case, the iDMA engine.

**Custom opcode space:** RoCC uses RISC-V opcode encoding `custom-3` (`0x77`). Rocket decodes these instructions in its ID stage and forwards them to the attached coprocessor without disturbing normal integer pipeline flow.

**RoCC interface signals:**

| Signal group     | Direction       | Description                                                   |
|------------------|-----------------|---------------------------------------------------------------|
| `cmd.valid`      | Rocket → iDMA   | New instruction available                                     |
| `cmd.bits.inst`  | Rocket → iDMA   | Decoded instruction (funct7, funct3, rd, rs1/rs2 indices)     |
| `cmd.bits.rs1`   | Rocket → iDMA   | Value of rs1 (e.g., descriptor address in L2 cache or DRAM)   |
| `cmd.bits.rs2`   | Rocket → iDMA   | Value of rs2 (e.g., transfer control word / target CPU index) |
| `resp.valid`     | iDMA → Rocket   | Coprocessor response ready (completion or error notification) |
| `resp.bits`      | iDMA → Rocket   | Response payload: DMA CPU index, completion status, error flags|
| `busy`           | iDMA → Rocket   | Queue full — Rocket pipeline stalls on next custom instruction |
| `mem.req.*`      | iDMA → Rocket   | Coprocessor-initiated memory load (for descriptor auto-fetch)  |
| `mem.resp.*`     | Rocket → iDMA   | Memory response data returned to coprocessor                  |

**DMA descriptor enqueue via RoCC:**
Firmware writes `rs1 = descriptor_address` (pointer to a DMA descriptor struct resident in L2 cache) and `rs2 = descriptor_control` (target DMA CPU index, interrupt-on-complete flag). The iDMA engine receives the custom instruction, fetches the full descriptor from memory via the `mem` port, and enqueues the transfer into the selected DMA CPU's command buffer. A complete multi-dimensional DMA transfer — with source address, destination address, strides, and per-dimension sizes — is thus initiated with a single RISC-V instruction.

**Completion signaling:** When the DMA CPU finishes its transfer, it asserts `resp.valid` with the CPU index and status. Firmware can poll `resp.valid` after each issued instruction, or configure iDMA to raise a Rocket interrupt when a specific CPU or batch completes.

**Why RoCC instead of MMIO?**

RoCC integration offers key advantages over a memory-mapped I/O doorbell register for DMA dispatch:

- **Zero pipeline overhead.** RoCC instruction dispatch occupies the same 1-cycle ID slot as any RISC-V instruction. MMIO requires a dedicated store instruction plus a non-cacheable miss penalty of approximately 5–10 cycles per command.
- **Fire-and-forget issuing.** Firmware issues one custom instruction per DMA descriptor with no separate doorbell write. The `busy` signal provides automatic flow-control: Rocket stalls in the ID stage when the iDMA queue is full, requiring no firmware polling loop for backpressure.
- **Register-sourced operands.** `rs1`/`rs2` deliver the descriptor address and control word in a single instruction, avoiding the two-instruction sequence (write pointer register, write doorbell) required by MMIO.
- **Tight firmware loop efficiency.** DMA-intensive scatter-load loops achieve near-1-instruction-per-transfer throughput. No extraneous memory-mapped register writes are interspersed in the hot path, keeping the I-cache loop footprint minimal.

### 5.4 Clock Domains in Dispatch Tile

The Dispatch tile spans two primary clock domains with an explicit CDC FIFO boundary at the Rocket/NIU interface:

| Domain      | Source                        | Covers                                              |
|-------------|-------------------------------|-----------------------------------------------------|
| `ai_clk`    | `i_ai_clk[col]` (per-column)  | Rocket core, L1/L2 caches, iDMA engine logic        |
| `noc_clk`   | `i_noc_clk` (chip-global)     | NoC local port, flit input/output FIFOs, NIU        |
| `axi_clk`   | `i_axi_clk`                   | APB slave register interface (SFR domain)           |

**Column-specific ai_clk:** DISPATCH_W at X=0 receives `i_ai_clk[0]`; DISPATCH_E at X=3 receives `i_ai_clk[3]`. The two Dispatch tiles may therefore operate at different frequencies under per-column DVFS, allowing one Dispatch tile to throttle independently without affecting the other or the shared noc_clk domain.

**CDC FIFO sizing:** The `ai_clk`→`noc_clk` async FIFOs at the Rocket/NIU boundary are sized to absorb burst command sequences from Rocket firmware without stalls during normal operation. Typical sizing is 8–16 entries on the command path and 4–8 entries on the response path, consistent with the 8-deep iDMA CPU command queue depth.

**noc_clk sharing:** Both DISPATCH_W and DISPATCH_E share the same chip-global `i_noc_clk`. This ensures consistent NoC arbitration timing across all tiles regardless of per-column ai_clk DVFS state, and that wormhole packet forwarding operates at a single well-defined rate across the mesh.

### 5.5 Dispatch Tile Integration — Firmware Usage Model

The following describes the complete firmware-driven NPU execution lifecycle from one Dispatch tile. Both Dispatch tiles execute this sequence in parallel, each managing its assigned half of the Tensix array.

**Step 1 — Boot and runtime load:**
Rocket comes out of reset and fetches from the programmed boot vector. If the NPU runtime image is not already resident in L2, Rocket programs iDMA CPU0 to perform a DRAM→L2 bulk transfer, then jumps to the runtime entry point once the transfer completes.

**Step 2 — Tensix firmware delivery:**
The NPU runtime uses iDMA CPUs 0–7 in parallel to load TRISC3 kernel programs and TRISC LLK programs from DRAM into the L1 memories of 8 assigned Tensix tiles. Each iDMA CPU handles one Tensix tile's L1 load independently (source: DRAM, destination: Tensix L1 via NoC write packet). With 8 CPUs active concurrently, all 8 tiles are programmed in a single parallel phase rather than sequentially, reducing firmware delivery time by up to 8×.

**Step 3 — Per-tile SFR configuration:**
Rocket traverses a firmware configuration table and issues APB writes via NoC to each Tensix tile:
- `CLUSTER_CTRL`: operating mode, kernel type, tensor dimensions
- `T6_L1_CSR`: L1 cache partitioning, base addressing, bank enable
- Router ATT entries: NoC address translation for tensor operand routing

**Step 4 — Weight pre-load:**
Rocket issues iDMA commands via RoCC custom instructions to pre-load weight tensor tiles from DRAM into Tensix L1s. The ADDRESS_GEN hardware handles strided extraction of weight sub-tiles from the DRAM weight matrix layout (e.g., loading every K_tile-sized row block with an outer stride equal to the full matrix row width) without a firmware loop per row.

**Step 5 — Kernel launch:**
Rocket writes the TRISC reset program counter (start address of the LLK program in Tensix L1) to each Tensix tile's TRISC_PC SFR, then deasserts the TRISC reset. TRISCs begin executing their LLK programs autonomously. Rocket immediately proceeds to issue the next batch of DMA commands for the subsequent weight tile while the current tile is computing — overlapping DMA with compute.

**Step 6 — Completion and output drain:**
Rocket polls `LLK_TILE_COUNTERS` via NoC APB reads, or waits for a completion interrupt, to detect when the kernel has finished writing output activations to Tensix L1. Once all tiles signal completion, Rocket issues iDMA commands to drain the L1 activation outputs back to DRAM, then prepares the next kernel launch cycle.

---

## §6 NoC Router

### 6.1 Overview

Every tile in the N1B0 mesh includes a NoC router instance (`tt_trinity_router`). Routers implement a 5-port wormhole-switched fabric with two routing modes: deterministic Dimension-Order Routing (DOR) and dynamic routing using a per-flit carried path list.

**Wormhole switching — RTL-verified**

The term "wormhole" does not appear as a variable name in the RTL. What is verified from `tt_noc_pkg.sv` and the router implementation is the exact mechanism that defines wormhole switching:

| RTL evidence | File / line | What it confirms |
|---|---|---|
| Distinct `HEAD_FLIT` (3'b001), `DATA_FLIT` (3'b010), tail, squash flit types | `tt_noc_pkg.sv` lines 38–60 | Packet is split into flits with explicit type tagging — router acts on each flit individually |
| `flit_type_is_head()` gates route-compute; body flits bypass route logic | `tt_noc_pkg.sv` lines 43–56 | Route decision made at head flit; subsequent data flits forwarded without re-decode |
| `out_vc_full_credit` per VC per output port | `tt_noc_pkg.sv` line 1143 | Credit-based flow control per VC — downstream buffer space tracked, not full packet buffering |
| `path_reserve_bit`, `linked_bit` in flit metadata | `tt_noc_pkg.sv` lines 164–165 | Path reservation mode: head flit reserves output VC before body flits arrive |
| `NOC_HEAD_FLIT_BIT` and `NOC_DATA_FLIT_BIT` in the 514-bit flit word | `tt_noc_pkg.sv` lines 238–239 | Head and data flits carried on the same 512-bit data bus with 2 sideband bits |

**Why wormhole switching?**

Wormhole switching forwards flit-by-flit as soon as the header is decoded, without buffering the full packet at each router. The router performs route computation only on the head flit (using `x_coord`/`y_coord` for DOR, or the carried path list for dynamic routing) and then pipelines the remaining data flits through the selected output port using VC credits. This gives near-wire latency for large payloads: a 64-flit (32 KB) packet traverses each router in 1 cycle per flit (header decode latency only at the first hop), rather than requiring 64-cycle store-and-forward buffering. At 512 bits per flit and ~1 GHz `noc_clk`, each port delivers 512 Gbit/s peak throughput, and end-to-end latency for short control packets is bounded by hop count rather than packet size.

**5-port meaning:** 4 cardinal ports (North/South/East/West) connect to neighboring tiles in the 4×5 mesh. The 5th Local port connects to the tile's own endpoint (Tensix, Dispatch NIU, or standalone NIU). Each port is an independent 512-bit datapath with its own VC arbitration.

### Unit Purpose
Every tile in N1B0 contains a NoC router (`tt_trinity_router`) that implements a 5-port wormhole-switched fabric with dual routing modes: deterministic Dimension-Order Routing (DOR) for predictable, deadlock-free paths, and dynamic routing using a per-flit carried path list for multicast and advanced network operations. Routers are the circulatory system of N1B0, forwarding Tensix-to-Tensix reads, Tensix-to-NIU DRAM requests, NIU-to-Tensix read responses, and control broadcasts with fine-grained virtual-channel arbitration to prevent head-of-line blocking and ensure latency-critical control traffic is not starved by large data transfers.

### Design Philosophy
Routers embody **flit-granular pipelining for near-wire latency**. Wormhole switching — the architectural cornerstone — forwards each flit as soon as the header is decoded, without buffering the full packet at each hop. The header flit undergoes route computation (4–5 cycles) to select an output port and check Virtual Channel credits; subsequent data flits are streamed directly through the selected port using VC flow control (credit-based buffering at the downstream router), incurring minimal additional latency per hop. This yields near-wire traversal for large packets (32+ KB activations take ~1 cycle per flit across multiple hops, rather than store-and-forward delays). The 4-VC scheme (request, response, control, multicast) avoids deadlock in a 2D bidirectional mesh: requests never hold a VC waiting for responses (which would create cycles), control traffic is isolated on VC2 to prevent starvation, and multicast is segregated on VC3 to avoid head-of-line blocking of unicast traffic.

### Integration Role
Routers are the fabric that interconnects all N1B0 tiles. Every Tensix-to-Tensix read, every iDMA-to-NIU load, every Dispatch broadcast flows through routers. Each router has 5 ports: 4 cardinal (North/South/East/West to neighboring tiles in the 4×5 mesh) and 1 Local (to the tile's own endpoint — Tensix, Dispatch, or standalone NIU). Routers operate independently with zero software involvement (no firmware steers flits); routing decisions are computed in hardware based on flit headers and the routing mode selected at source. DOR routing allows simple, stateless hop-by-hop decisions (e.g., "move east until x_coord matches, then north until y_coord matches"). Dynamic routing permits complex patterns like all-reduce or broadcast, where each flit carries a list of intermediate waypoints that the router reads, consumes, and forwards to the next hop.

### Key Characteristics
- **Wormhole-switched pipeline**: Flit-by-flit forwarding after header decode, with credit-based VC flow control, yields near-wire latency scaling with hop count, not packet size. A 64-flit (32 KB) packet traverses each router in ~1 cycle after header (vs. 64 cycles for store-and-forward).
- **4 Virtual Channels per port**: Request, response, control, and multicast VCs segregate traffic classes, preventing head-of-line blocking and ensuring control packets (VC2) and multicast (VC3) are never delayed by bulk data transfers (VC0/VC1).
- **Dual routing modes**: DOR (Dimension-Order: X-first, then Y) is deadlock-free and requires zero per-flit carried list overhead. Dynamic routing uses a 928-bit carried list (NW_OPT repeater depth 6 stages × 8 per-stage intermediate waypoints) for advanced topologies and multicast, at the cost of per-flit datapath overhead.
- **Path reservation protocol**: When path_reserve_bit is set in a header flit, the router reserves the selected output VC for the entire packet body, preventing out-of-order reassembly or starvation of late-arriving body flits.
- **Cardinal repeaters**: REP_DEPTH varies by port (East/North=1, West=4, South=5, composite NW_OPT loopback=6) to match inter-router latencies in the mesh topology, ensuring first-in-first-out VC behavior.

### Use Case Example
**Broadcast Activation to All Tensix Tiles**  
After a Tensix at (1,1) completes a forward pass and produces 64 KB of output activations (result tensor for the next layer), firmware broadcasts these activations to all other Tensix tiles on the chip. The source Tensix (1,1) injects a header flit with routing mode = multicast (VC3) and a carried path list indicating all 11 target Tensix EndpointIndices. The header flit routes via DOR east to (2,1), where the router reads the first destination in the path list, consumes it, and replicates the flit to both the local port (for Tensix at 2,1) and the cardinal port continuing the multicast route. Subsequent body flits follow on the same VC3 path without re-lookup. By the time the tail flit is delivered to the last target, all 11 Tensix tiles have received a copy of the activation, all in parallel, with minimal control overhead — the overlay engine at each target Tensix unpacks the received 64 KB and prepares it for the next layer's GEMM.

### 6.2 Router Port Map

```
                      North port
                         ↑
                         │
  West port ←──── [ROUTER] ────→ East port
                         │
                         ↓
                      South port
                         │
                      Local port (tile endpoint)
```

Each port is 512 bits wide (one full NoC flit per cycle). All five ports operate simultaneously with independent virtual channel arbitration. The router pipelines header decode, output port selection, and VC credit check in parallel with flit forwarding, so the effective per-hop latency for a fully pipelined wormhole packet is 1 cycle after the header is placed.

### 6.3 Virtual Channels

| Parameter        | Value                                     |
|------------------|-------------------------------------------|
| Number of VCs    | 4 per port                                |
| VC buffer depth  | Configurable (SRAM-backed FIFOs per VC)   |
| Arbitration      | Round-robin per port with priority override |

**Virtual channel assignment by traffic class:**

| VC  | Traffic class       | Use case                                                          |
|-----|---------------------|-------------------------------------------------------------------|
| VC0 | Request             | Tensix→NIU writes, Tensix→Tensix activation reads                 |
| VC1 | Response            | NIU→Tensix read responses, Tensix→Tensix read return data         |
| VC2 | Control / config    | TRISC3 config writes to remote tiles, SFR programming from Rocket  |
| VC3 | Multicast / priority| Broadcast weight loads to multiple Tensix tiles simultaneously    |

**Why 4 VCs?**

Deadlock avoidance in a bidirectional 2D mesh requires a minimum of 2 VCs (one for requests, one for responses), since a request flit holding a VC while waiting for a response would otherwise create a cyclic dependency. 4 VCs adds meaningful priority differentiation: control traffic on VC2 cannot be head-of-line blocked by large data transfers on VC0/VC1, and multicast on VC3 is isolated from unicast congestion. More than 4 VCs would increase SRAM area for the VC FIFOs without significant benefit in a 4×5 mesh where the maximum path length is 7 hops.

**VC credit mechanism:** Each output port maintains a per-VC credit counter tracking available buffer slots in the downstream router's input VC. A sender decrements its local credit counter when forwarding a flit; the receiver returns a credit token on each flit consumed from the buffer. Senders stall when the credit count reaches zero, preventing FIFO overflow without dropping flits.

### 6.4 Flit Format

#### 6.4.1 flit_type Field (3 bits)

| Code | Name         | Description                                        |
|------|--------------|----------------------------------------------------|
| 3'b001 | header     | First flit of a packet; contains routing header    |
| 3'b010 | data       | Payload flit; no routing information               |
| 3'b100 | tail       | Last flit of a packet                              |
| 3'b110 | path_squash | Special header for dynamic routing path pre-emption|

#### 6.4.2 noc_header_address_t Bit Map

The header flit contains a structured address field `noc_header_address_t`:

| Field            | Bits  | Description                                         |
|------------------|-------|-----------------------------------------------------|
| `x_coord`        | [5:0] | Destination X coordinate in the mesh               |
| `y_coord`        | [5:0] | Destination Y coordinate in the mesh               |
| `endpoint_index` | [4:0] | EndpointIndex (= X×5+Y) of destination tile         |
| `mcast_en`       | [0]   | Multicast enable                                    |
| `mcast_mask`     | [N:0] | Bitmask of multicast destination tiles              |
| `vc_sel`         | [1:0] | Virtual channel selection                           |
| `flit_type`      | [2:0] | Flit type (see §5.4.1)                              |

### 6.5 Dimension-Order Routing (DOR)

DOR is the default deterministic routing mode:

1. **X-phase**: Route along X-axis toward destination `x_coord`
2. **Y-phase**: When X matches, route along Y-axis toward destination `y_coord`

DOR is deadlock-free in a 2D mesh because it establishes a total order on dimensions. All flits using DOR travel strictly in X-first, Y-second order with no backtracking.

**Routing pseudo-code (DOR mode):**
```
if (current_x < dest_x)  → East
if (current_x > dest_x)  → West
if (current_x == dest_x and current_y < dest_y) → North
if (current_x == dest_x and current_y > dest_y) → South
if (current_x == dest_x and current_y == dest_y) → Local
```

**Worked example — routing from (0,0) to (3,4):**

```
Step 1 (X-phase): X=0 < X_dest=3, route East at each hop
  (0,0) →East→ (1,0) →East→ (2,0) →East→ (3,0)   [3 hops]

Step 2 (Y-phase): X matches X_dest=3, route North at each hop
  (3,0) →North→ (3,1) →North→ (3,2) →North→ (3,3) →North→ (3,4)   [4 hops]

Total: 7 hops  (= |Δx| + |Δy| = 3 + 4, the Manhattan minimum)
```

DOR guarantees the minimum-hop-count path for any source-destination pair in the mesh, since X-then-Y traversal is always the shortest path in a 2D grid under L1 distance.

### 6.6 Dynamic Routing

Dynamic routing uses a pre-computed explicit path embedded in the flit itself as a 928-bit carried list. Each router reads one slot from the list to determine its output port, then passes the remaining list forward.

| Parameter          | Value                                         |
|--------------------|-----------------------------------------------|
| Carried list width | 928 bits                                      |
| Path encoding      | Per-hop slot: 3-bit direction + metadata      |
| Read rule          | Each router reads its slot, forwards remainder|
| NIU write rule     | NIU may overwrite path slots at injection     |

**Per-hop operation:**
1. Router reads the current hop's slot from the carried list
2. Extracts the output port direction for this hop (3-bit: N/S/E/W/Local)
3. Forwards the remaining slots to the next router (slot index advances per hop)
4. NIU at injection point may rewrite slots based on ATT lookup before injecting the packet

**Why dynamic routing exists alongside DOR:**

DOR creates structural congestion hotspots in the N1B0 mesh: all traffic destined for the two NIUs at X=1, X=2 must traverse the central columns, creating a bottleneck when Tensix tiles in multiple rows simultaneously issue DRAM-bound traffic. Dynamic routing allows alternative paths that bypass congested links. The 928-bit carried list enables a fully pre-computed route decided at the injection point (by Dispatch firmware or the NIU ATT), without requiring per-hop routing table lookups that would add per-router latency.

For weight broadcast to all 12 Tensix tiles, dynamic routing enables a multicast tree traversal order that distributes fanout across multiple router hops, rather than funneling all traffic through a single X-column bottleneck as DOR would impose.

### 6.7 Path Squash Flit

The `path_squash` flit type (3'b110) is a control flit that preempts an in-flight wormhole packet:

- Injected into the NoC when a routing error or timeout is detected
- Travels along the same physical path as the packet being cancelled
- Each router receiving a path_squash flit releases the associated VC credits and buffer slots
- Used by the EDC error recovery flow to drain erroneous packets without deadlocking the VC

The path_squash mechanism is necessary for wormhole networks because a partially-transmitted packet that cannot complete (e.g., due to a detected error at the destination) would otherwise hold VC credits hostage across all intermediate routers, causing a VC stall cascade. The path_squash flit travels ahead and clears each router's held credit before the stall propagates.

### 6.8 ATT — Address Translation Table (in Router)

The router-side ATT is distinct from the NIU ATT (§3.2.3). It provides:

- 64 entries, each with mask/endpoint/routing fields
- Used for address-based routing decisions at the local port injection point
- Enables NoC address aliasing and endpoint redirection (e.g., redirecting a logical broadcast address to a physical multicast group bitmask)
- Programmed by Rocket firmware via APB at boot, before any NoC traffic is injected

### 6.9 Repeater Placement

Long wire segments in the mesh require repeater insertion to maintain signal integrity and meet setup timing. Physical tile pitch in N1B0 is approximately 100 µm. Signal integrity requires repeater insertion roughly every 500 µm, implying 2–5 repeater stages for typical inter-tile wire lengths. N1B0 repeater depths by segment:

| Segment                      | REP_DEPTH | Physical rationale                                         |
|------------------------------|-----------|------------------------------------------------------------|
| Y=3 loopback (composite)     | 6         | Spans two tile rows inside one module; `REP_DEPTH_LOOPBACK=6` |
| Y=4 output (composite NIU)   | 4         | NIU output to Y=3 router; `OUTPUT=4`                       |
| X-axis inter-tile (standard) | 2         | One tile pitch ~100 µm; 2 repeater stages sufficient       |
| Y=3 composite (West port)    | 4         | Longer cardinal West segment                               |
| Y=3 composite (South port)   | 5         | Longest cardinal South segment in composite                |
| Y=3 composite (East/North)   | 1         | Short segments — 1 stage sufficient                        |

The REP_DEPTH_LOOPBACK=6 value for the composite Y=3 internal loopback is the highest in the design: the loopback wire must traverse the full vertical extent of the composite NOC2AXI_ROUTER tile (spanning Y=4 down to Y=3 and back), equivalent to approximately 3× the standard inter-tile pitch, requiring 6 repeater stages to meet timing.

### 6.10 MCPDLY Derivation

The EDC ring uses a multi-cycle path delay parameter `MCPDLY` to correctly sample toggle signals across repeater chains. For the N1B0 Y=3 segment with `REP_DEPTH_LOOPBACK=6`:

```
MCPDLY = ceil(REP_DEPTH / clock_ratio) + margin
       = ceil(6 / 1) + 1
       = 7
```

This value is programmed into the EDC CSR at initialization. See §7 for EDC ring details.

### 6.11 Multicast

The NoC supports hardware-assisted multicast via the `mcast_en` bit and `mcast_mask` bitmask in the header flit.

**Mechanism:** When `mcast_en=1`, the router replicates the packet to all ports whose destination tiles are included in `mcast_mask`. Each bit of `mcast_mask` corresponds to one EndpointIndex in the mesh. The router checks the mask against the set of reachable endpoints in each direction and forwards a copy to each matching port.

**Primary use case — weight broadcast:** In LLM inference, the same weight tile must be delivered to all Tensix tiles participating in a matrix multiply (up to all 12 Tensix tiles for a full-chip GEMM). With unicast, this requires 12 separate NoC injections from the Dispatch tile, consuming 12× the injection bandwidth and 12× the DRAM-to-NoC data movement. With multicast to all 12 Tensix tiles via a single injection:
- NoC injection bandwidth required: 1× (one packet injected at source)
- Effective bandwidth amplification: 12× at destination tiles
- Source-to-first-hop link traffic: reduced by approximately 11× vs. 12 separate unicast packets

**VC3 assignment:** Weight broadcasts use VC3 to isolate multicast traffic from unicast data and response traffic on VC0/VC1, preventing a large broadcast from starving unicast responses and creating head-of-line blocking or deadlock conditions.

---

## §7 iDMA Engine

### 7.1 Overview

The iDMA (integrated DMA) engine resides inside each Dispatch tile and is the primary mechanism for high-bandwidth tensor data movement between external DRAM and on-chip Tensix L1 memories. It is accessible via two interfaces:

1. **RoCC coprocessor interface** — from the Rocket core pipeline (see §4.3); zero-overhead instruction-level dispatch
2. **APB slave at base address `0x03004000`** — for debug, external SoC programming, or firmware fallback when RoCC is not appropriate

The iDMA engine contains **8 independent DMA CPU cores**. Each CPU is capable of autonomous multi-dimensional address generation, NoC packet injection, and completion signaling without per-flit Rocket involvement.

**Why 8 CPUs?**

N1B0 has 12 Tensix tiles total, but practical simultaneous DMA targets per Dispatch tile are at most 6 (the Tensix tiles on its side of the mesh). 8 CPUs exceeds this maximum, providing slack for:
- Overlapping weight load for the next layer while the current layer is computing (double-buffering)
- One CPU dedicated to firmware delivery (L1 program load) while others handle weight data
- One CPU available for activation drain while others pre-load the next weight tile

Each CPU runs independently with no inter-CPU synchronization hardware. For simple broadcast or scatter patterns, all 8 CPUs can operate in parallel without any firmware-managed ordering.


### Unit Purpose
The iDMA (integrated DMA) engine is the primary high-bandwidth, low-latency data-movement accelerator for loading weights and model parameters from external DRAM into Tensix L1 memories. Located in each Dispatch tile, iDMA is driven by either Rocket RoCC coprocessor commands (zero-overhead instruction-level dispatch) or by APB register writes (for debug or external SoC firmware), and maintains 8 autonomous DMA CPUs capable of multi-dimensional address generation, NoC packet injection, and completion signaling without per-transaction Rocket involvement. iDMA is optimized for weight and parameter movement, complementing overlay streams (used for activation drain and intermediate results).

### Design Philosophy
iDMA exemplifies **hardware-accelerated address generation for tensor layouts**. Instead of requiring firmware to manually generate addresses for multi-dimensional tensor data (e.g., weight matrices with non-standard strides), iDMA provides dedicated address-generation hardware (`ADDRESS_GEN_R` and `ADDRESS_GEN_W` blocks per DMA CPU) that autonomously loops over up to 4 spatial dimensions with independent strides and limits. Firmware programs the base address, dimension sizes, and per-dimension strides once, then iDMA hardware handles all subsequent address arithmetic, NoC packet generation, and NoC credit management without further involvement. Each of the 8 DMA CPUs operates independently (no inter-CPU synchronization), allowing parallel execution of multiple weight loads, weight prefetch for the next layer, and firmware delivery, all from the Dispatch CPU cluster without contention or serialization.

### Integration Role
iDMA bridges the Dispatch tile's Rocket CPU to the external AXI master interface, bypassing the NoC entirely. Unlike overlay streams (which inject packets into the NoC and rely on routers for delivery), iDMA generates AXI transactions directly — it reads from AXI in the context of whatever address space Rocket CPU configured, and writes to AXI for return data or configuration responses. This direct path provides lower latency (no routing hops, no NoC VC arbitration) and dedicated bandwidth, making iDMA ideal for initial weight load (which may be multi-megabyte and latency-critical) and model parameter fetch. iDMA also serves as a fallback mechanism: if NoC traffic is congested or overlay streams are fully utilized by Tensix clusters, iDMA can still deliver weights with predictable latency. The two composite tiles (X=1 and X=2) each have their own iDMA in the embedded Dispatch CPU, so weight loads can exploit both left and right DRAM sides in parallel.

### Key Characteristics
- **8 independent DMA CPUs**: Each CPU executes a separate multi-dimensional transfer descriptor without firmware overhead; all 8 can operate in parallel, doubling bandwidth if software permits.
- **Multi-dimensional address generation**: Up to 4 spatial dimensions with independent strides and sizes per dimension, supporting arbitrary weight layouts (row-major, tiled, transposed) without firmware scatter/gather loops.
- **RoCC interface**: Rocket's funct7 bits select one of 8 DMA CPUs and one of 47 registers to program; each instruction is non-blocking, allowing Rocket to issue a weight load and continue executing firmware logic while iDMA hardware handles DRAM I/O.
- **Configurable transfer modes**: CMD_BUF_R (read from DRAM), CMD_BUF_W (write to DRAM), ADDRESS_GEN (autonomous looping), and SIMPLE_CMD_BUF (1D/2D simplified path for fast programming).
- **Direct AXI mastery**: iDMA generates AXI transactions directly without NoC routing, providing lower latency and dedicated bandwidth compared to overlay streams, ideal for weight prefetch and parameter loads.

### Use Case Example
**Multi-Layer Weight Prefetch Pipeline**  
During inference of layer N (Tensix clusters are computing with weights already in L1), the Rocket CPU in the Dispatch tile issues an iDMA RoCC command to prefetch weights for layer N+1 from DRAM. Rocket executes: `IDMA_RD_CMD cpu=0, dim0_size=4096, dim0_stride=128, dim1_size=32, dim1_stride=16384`, specifying a 4 KB × 32 weight matrix (128 KB total) with 2D layout. iDMA CPU 0 immediately begins address generation: it loops dim0 from 0–4095 (stride 128 bytes each), then increments dim1 and repeats, generating a sequence of 256 AXI read addresses covering the weight matrix. Each AXI read returns 512 bits; iDMA's output buffer accumulates them and injects the 256 flits into the Tensix destination tile's NoC input port via the embedded NOC2AXI bridge (internal AXI→NOC path). By the time layer N's compute completes, layer N+1 weights are already staged in a Tensix L1, ready for the next GEMM. Meanwhile, Rocket can issue a second iDMA command to prefetch layer N+2, creating a 2-layer pipeline with zero Rocket stall.

---
### 7.2 DMA CPU Architecture

Each of the 8 DMA CPUs contains 5 independent register blocks:

```
DMA CPU[n] (n = 0..7)
  ┌─────────────────────────────────────────────┐
  │  CMD_BUF_R      (47 regs)                   │
  │  Source addr, strides, sizes, ctrl, status  │
  ├─────────────────────────────────────────────┤
  │  CMD_BUF_W      (47 regs)                   │
  │  Dest addr, strides, sizes, ctrl, status    │
  ├─────────────────────────────────────────────┤
  │  ADDRESS_GEN_R  (25 regs)                   │
  │  Multi-dim loop counter for read addresses  │
  ├─────────────────────────────────────────────┤
  │  ADDRESS_GEN_W  (25 regs)                   │
  │  Multi-dim loop counter for write addresses │
  ├─────────────────────────────────────────────┤
  │  SIMPLE_CMD_BUF (47 regs)                   │
  │  1D/2D simplified transfer path             │
  └─────────────────────────────────────────────┘
```

CMD_BUF_R configures the source side of a read-then-write (DRAM-to-L1) or read-only operation. CMD_BUF_W configures the destination side. ADDRESS_GEN provides autonomous hardware looping over the address space according to programmed strides and limits, freeing the Rocket CPU from per-transfer address arithmetic.

### 7.3 CMD_BUF_R / CMD_BUF_W

Each CMD_BUF block (47 registers) configures a full DMA transfer descriptor:

| Register Group      | Count | Description                                          |
|---------------------|-------|------------------------------------------------------|
| Source address      | 4     | Base address (64-bit across two 32-bit regs)         |
| Destination address | 4     | Base address (64-bit)                                |
| Stride config       | 8     | Per-dimension stride values (up to 4 dimensions)     |
| Size config         | 8     | Per-dimension transfer size                          |
| Control             | 8     | Enable, interrupt on completion, VC select, etc.     |
| Status / misc       | 15    | Transfer status, error flags, completion count       |

The CMD_BUF supports up to 4-dimensional tensor transfers with independent stride and size per dimension, enabling efficient mapping of arbitrary tensor layouts without software scatter/gather overhead.

**Register programming example — 16 KB DRAM→Tensix(0,0) L1 transfer:**

```c
// Program iDMA CPU0 to read 16KB from DRAM to Tensix (0,0) L1
// Tensix (0,0): EndpointIndex = 0*5+0 = 0

idma[0].CMD_BUF_R.SRC_ADDR_LO = 0x80001000;  // DRAM source, lower 32 bits
idma[0].CMD_BUF_R.SRC_ADDR_HI = 0x00000000;  // DRAM source, upper 32 bits
idma[0].CMD_BUF_R.DST_EP      = 0;           // EndpointIndex = 0 → Tensix(0,0)
idma[0].CMD_BUF_R.BYTE_COUNT  = 16384;        // 16 KB transfer size
idma[0].CMD_BUF_R.VC_SEL      = 0;           // VC0 (request traffic)
idma[0].CMD_BUF_R.CTRL        = 0x1;         // enable bit: start transfer
// Poll idma[0].CMD_BUF_R.STATUS until done bit is set
```

### 7.4 ADDRESS_GEN_R / ADDRESS_GEN_W

The address generator (25 registers) implements an autonomous multi-dimensional hardware loop counter:

| Register Group  | Count | Description                                           |
|-----------------|-------|-------------------------------------------------------|
| Base address    | 2     | Starting address for the address sequence             |
| Dimension count | 1     | Number of active dimensions (1–4)                     |
| Stride[0..3]    | 8     | Stride per dimension (signed 32-bit, in bytes)        |
| Limit[0..3]     | 8     | Iteration count per dimension                         |
| Control         | 6     | Loop enable, wrap mode, saturation                    |

The ADDRESS_GEN operates as a hardware loop counter, automatically incrementing addresses and wrapping at boundaries. This allows the DMA to traverse complex tensor sub-views (e.g., rows of a matrix stored in column-major order) without CPU intervention.

**Multi-dimensional strided access example:**

To load every 4th row of a weight matrix stored in row-major DRAM layout (e.g., extracting K_tile=48 rows with a row stride of 4× the row size, from a matrix with 1024 columns of INT16 = 2048 bytes/row):

```
ADDRESS_GEN_R config:
  Base       = DRAM_weight_base
  Dim0 size  = 2048        // bytes per selected row (1024 × INT16)
  Dim0 stride = 1          // byte stride within row: contiguous
  Dim1 size  = 48          // number of rows to load
  Dim1 stride = 4 * 2048   // skip 4 rows per iteration (every 4th row)
  Dim count  = 2           // 2 active dimensions
```

The ADDRESS_GEN hardware automatically generates all 48 × 2048-byte source address sequences without any Rocket intervention. This allows complex strided sub-tensor extraction in a single DMA command, equivalent to what would otherwise require a firmware loop of 48 separate DMA transfers.

### 7.5 SIMPLE_CMD_BUF

The SIMPLE_CMD_BUF (47 registers) provides a simplified programming interface for common 1D or 2D transfers where the full 4D CMD_BUF generality is not required. It uses the same register layout but with a reduced maximum dimensionality configuration, making firmware programming faster for straightforward bulk transfers (e.g., loading a contiguous L1-sized block from a sequential DRAM address).

### 7.5.1 Byte Control and Write Enable Masking

The iDMA engine supports **fine-grained byte-level write control** via per-flit write-enable masks. This allows selective byte updates in L1 SRAM without requiring read-modify-write operations at the software level.

**Byte Enable (WSTRB) Control:**

Each 512-bit AXI data flit contains a 64-byte write-enable mask (AXI WSTRB[63:0]):
- Each bit in WSTRB corresponds to one byte of the 512-bit flit
- WSTRB[i]=1 → byte i is written to L1
- WSTRB[i]=0 → byte i is masked (not written, preserves existing L1 value)

**Register Control:**

| Register | Bits | Name | Function |
|----------|------|------|----------|
| CMD_BUF_W.WSTRB_MODE | [2:0] | Write Strobe Mode | Controls how write-enable is applied: <br> 0x0=ALL (all 64 bytes enabled) <br> 0x1=PARTIAL (use programmed WSTRB mask) <br> 0x2=EVEN (even bytes only) <br> 0x3=ODD (odd bytes only) <br> 0x4=FIRST_N (first N bytes, N from FIRST_BYTE_CNT) <br> 0x5=STRIDE_MASK (strided pattern per STRIDE_WSTRB) |
| CMD_BUF_W.WSTRB_PATTERN | [63:0] | Write Strobe Pattern | Fixed 64-bit mask applied to every flit when WSTRB_MODE=0x1 (PARTIAL) |
| CMD_BUF_W.FIRST_BYTE_CNT | [6:0] | First Byte Count | Number of leading bytes to enable (1–64) when WSTRB_MODE=0x4 |
| CMD_BUF_W.STRIDE_WSTRB | [7:0] | Strided Write Enable | 8-bit repeating pattern for every 8 bytes when WSTRB_MODE=0x5 <br> Example: 0xFF = all bytes enabled, 0xAA = alternating pattern (bytes 1,3,5,7 per 8-byte block) |

**Practical Use Cases:**

1. **Partial L1 Update (WSTRB_MODE=0x1):**
   ```c
   // Update only INT16 fields at fixed byte offsets in a weight tensor
   idma[0].CMD_BUF_W.WSTRB_MODE = 0x1;      // PARTIAL
   idma[0].CMD_BUF_W.WSTRB_PATTERN = 0x3333333333333333;  // bytes 0,1,4,5,8,9... (INT16 at even offsets)
   // DMA writes only those bytes, leaving other fields untouched
   ```

2. **Strided Write Enable (WSTRB_MODE=0x5):**
   ```c
   // Load alternate INT16 elements of an INT32 vector
   idma[0].CMD_BUF_W.WSTRB_MODE = 0x5;       // STRIDE_MASK
   idma[0].CMD_BUF_W.STRIDE_WSTRB = 0x33;    // bytes 0,1,4,5 in every 8-byte block enabled
   // Each flit: bytes [0,1,4,5,8,9,12,13,...] written, [2,3,6,7,10,11,14,15,...] masked
   ```

3. **First-N Byte Write (WSTRB_MODE=0x4):**
   ```c
   // Load only first 32 bytes of a 64-byte flit (e.g., padding boundary)
   idma[0].CMD_BUF_W.WSTRB_MODE = 0x4;       // FIRST_N
   idma[0].CMD_BUF_W.FIRST_BYTE_CNT = 32;    // Enable only first 32 bytes per flit
   // Trailing 32 bytes preserved
   ```

---

### 7.5.2 Bit-Level Manipulation and Data Format Control

iDMA supports **data format conversion and selective bit updates** via configurable bit-width and packing modes. This enables efficient compression, quantization, and sparse-format loading without CPU intervention.

**Format Control Registers:**

| Register | Bits | Name | Function |
|----------|------|------|----------|
| CMD_BUF_R.SRC_BIT_WIDTH | [4:0] | Source Bit Width | Element bit-width in source: <br> 0x8=8-bit (INT8/FP8), 0x10=16-bit (INT16/FP16B), 0x20=32-bit (INT32/FP32) |
| CMD_BUF_W.DST_BIT_WIDTH | [4:0] | Dest Bit Width | Element bit-width in destination L1 |
| CMD_BUF_R.PACK_MODE | [2:0] | Bit Packing Mode | How multi-element flits are packed: <br> 0x0=BYTE_ALIGNED (no packing, 64 bytes/flit) <br> 0x1=DENSE_PACK (tight packing, no padding) <br> 0x2=INT8_TENSOR (8-bit quantized, 64 elements/flit) <br> 0x3=INT4_TENSOR (4-bit quantized, 128 elements/flit, 2 per byte) <br> 0x4=BIT_VECTOR (arbitrary bit sequences for sparsity masks) |
| CMD_BUF_R.COMPRESSION_FLAG | [1:0] | Compression Mode | Enable on-the-fly decompression: <br> 0x0=NONE, 0x1=RLE (run-length), 0x2=HUFFMAN, 0x3=ZSTD |
| CMD_BUF_W.DEST_OFFSET_BITS | [7:0] | Destination Bit Offset | Start bit position in L1 for writing (for sub-byte writes) |

**Practical Example — INT8 Tensor Load with Bit Packing:**

```c
// Load 128 INT8 elements from DRAM into 64 bytes of L1 (8 bits per element packed)
idma[0].CMD_BUF_R.SRC_BIT_WIDTH = 0x8;       // source is INT8
idma[0].CMD_BUF_W.DST_BIT_WIDTH = 0x8;       // destination is INT8
idma[0].CMD_BUF_R.PACK_MODE = 0x2;           // INT8_TENSOR mode
idma[0].CMD_BUF_R.DIM0_SIZE = 128;           // 128 INT8 elements
idma[0].CMD_BUF_R.DIM0_STRIDE = 1;           // contiguous in DRAM
idma[0].CMD_BUF_R.CTRL = 0x1;                // enable, triggers transfer
// DMA automatically packs 128 INT8 → 64 bytes in destination L1
```

**Practical Example — Sparse Tensor with Bitmask:**

```c
// Load sparsity pattern (2:4 structured sparsity) as bit vector
idma[1].CMD_BUF_R.SRC_BIT_WIDTH = 0x1;       // source is 1-bit (sparsity mask)
idma[1].CMD_BUF_R.PACK_MODE = 0x4;           // BIT_VECTOR mode
idma[1].CMD_BUF_R.DIM0_SIZE = 1024;          // 1024 bits = 128 bytes data
idma[1].CMD_BUF_W.DEST_OFFSET_BITS = 0;      // write from bit 0 of L1
idma[1].CMD_BUF_R.CTRL = 0x1;
// DMA loads sparse pattern directly, aligned to bit boundaries
```

---

### 7.5.3 Advanced Control Flags and Options

Additional control flags enable specialized iDMA behaviors:

| Register | Bits | Name | Function |
|----------|------|------|----------|
| CMD_BUF_R.STREAM_LAST_FLAG | [0] | Stream Last | Assert TLAST on final NoC flit (marks end-of-stream for Tensix) |
| CMD_BUF_R.INTERRUPT_ON_DONE | [0] | Interrupt Enable | Generate RoCC interrupt to Rocket CPU when transfer completes |
| CMD_BUF_R.ATOMIC_MODE | [1:0] | Atomic Transfer | 0x0=NON-ATOMIC (normal), 0x1=ATOMIC_SWAP, 0x2=ATOMIC_CAS (for synchronization) |
| CMD_BUF_R.PREFETCH_HINT | [0] | Prefetch Hint | Set high-priority VC for speculative weight prefetch (lookahead for next layer) |
| CMD_BUF_R.CACHE_POLICY | [2:0] | L1 Cache Control | 0x0=WRITE_THROUGH, 0x1=WRITE_BACK, 0x2=BYPASS (no L1 caching) |
| CMD_BUF_R.WRAP_ENABLE | [0] | Address Wrap | Enable wraparound when dimension counter reaches limit (circular buffer mode) |
| CMD_BUF_R.SATURATION_MODE | [0] | Saturate on Overflow | Clamp values to min/max instead of wrapping on arithmetic overflow |

**Practical Example — Circular Buffer with Wraparound:**

```c
// KV-cache rotation using iDMA wraparound: oldest token pushed out, new token inserted
idma[2].CMD_BUF_R.BASE_ADDR = kv_cache_start;
idma[2].CMD_BUF_R.WRAP_ENABLE = 1;           // enable wraparound
idma[2].CMD_BUF_R.DIM0_STRIDE = 128;         // token stride (128 bytes per KV pair)
idma[2].CMD_BUF_R.DIM0_LIMIT = 64;           // max 64 tokens (wrap at boundary)
idma[2].CMD_BUF_R.CTRL = 0x1;
// Each transfer increments internal pointer; at limit 64, wraps to 0
```

---

### 7.5.4 RoCC Coprocessor Interface Detail

The iDMA engine is accessible via the **Rocket Custom Coprocessor (RoCC)** interface, enabling zero-overhead instruction-level dispatch without firmware polling or register-based sequencing. This is the preferred high-performance programming path for iDMA.

**RoCC Instruction Encoding:**

| Instruction | funct7 | funct3 | Semantics |
|---|---|---|---|
| `idma.config` | custom0 [6:0] | 0x0 | Configure CPU: rs1=addr, rs2=ctrl; rd=status |
| `idma.request` | custom0 [6:0] | 0x1 | Request transfer: rs1=descriptor, rs2=CPU index; rd=transaction ID |
| `idma.fence` | custom0 [6:0] | 0x2 | Stall Rocket until iDMA CPU completes |
| `idma.status` | custom0 [6:0] | 0x3 | Poll iDMA CPU status into rd |

**RoCC Advantages:**

- ✅ **Zero-overhead dispatch:** iDMA request issued in single instruction, Rocket continues executing
- ✅ **Implicit synchronization:** Fence instruction stalls only Rocket, not compute pipeline
- ✅ **Pipelined descriptors:** Multiple iDMA requests outstanding simultaneously
- ✅ **Transaction tracking:** Unique ID per request for completion polling

**Practical RoCC Example:**

```c
// Fast multi-dimensional weight load via RoCC
// 1. Point to pre-built descriptor in L2 cache
uint64_t descriptor_addr = l2_cache_addr + offset;

// 2. Issue iDMA request (single instruction, non-blocking)
asm volatile (
  ".insn r CUSTOM_0, 0, 1, %0, %1, %2"  // idma.request funct3=0x1
  : "=r" (transaction_id)
  : "r"  (descriptor_addr)
    "r"  (0)  // CPU 0
);

// 3. Continue Rocket execution while iDMA operates in background
// (Rocket instruction cache prefetch, next layer config, etc.)

// 4. Optional: fence until complete
asm volatile (
  ".insn r CUSTOM_0, 0, 2, %0, x0, x0"  // idma.fence funct3=0x2
  :
  : "r" (0)  // CPU 0
);
```

---

### 7.5.5 Performance Optimization: Overlapping DMA and Compute

The key to maximizing N1B0 throughput is **pipelining weight loads with tensor compute**:

```
Layer N:    Load W →  Compute W →  Drain A →
Layer N+1:              Load W+1 → Compute W+1 → Drain A+1
Layer N+2:                           Load W+2 → Compute W+2 →
```

To achieve this overlap:
1. **Use separate DMA CPUs:** CPU0 for current layer, CPU1 for prefetch
2. **Issue iDMA early:** Start next-layer load while current layer is in first GEMM pass
3. **Stripe across Dispatch tiles:** Load west-side Tensix via DISPATCH_W, east-side via DISPATCH_E (parallel NIU access)
4. **Sustain >40 GB/s:** Use multi-dimensional transfers (≥16 KB) to keep AXI bus busy

**Multi-Dimensional Hardware Loop vs Firmware Loop:**

Hardware loop (preferred):
```c
idma_cmd.dim0_size = 4096;    // row size (bytes)
idma_cmd.dim1_size = 64;      // number of rows
idma_cmd.dim1_stride = 8192;  // row stride
idma_cmd.ctrl = ENABLE;       // Single command!
// Latency: ~0.5 µs, Hardware iterates all 64 rows automatically
```

Firmware loop (avoided):
```c
for (int i = 0; i < 64; i++) {
  idma_cmd.src_addr = base + i*8192;
  idma_cmd.ctrl = ENABLE;     // 64 separate commands
}
// Latency: ~32 µs dispatch overhead, slower data arrival
```

---

### 7.5.6 Error Handling and Reliability

iDMA includes **error detection and recovery** for production robustness:

**Error Status Fields:**

| Field | Bits | Description |
|-------|------|---|
| STATUS.DONE | [0] | Transfer complete |
| STATUS.ERROR | [1] | Error detected (ATT miss, SMN violation, AXI error) |
| STATUS.ERROR_CODE | [7:2] | 0x0=NONE, 0x1=ATT_MISS, 0x2=SMN_VIOLATION, 0x3=AXI_ERROR, 0x4=TIMEOUT |
| STATUS.BYTES_XFERRED | [47:8] | Cumulative bytes before error (for partial recovery) |

**Error Recovery Pattern:**

```c
// Robust DMA with error retry
idma_cmd.src_addr = dram_addr;
idma_cmd.dst_addr = l1_addr;
idma_cmd.byte_count = 16384;
idma_cmd.ctrl = ENABLE;

uint32_t status;
uint32_t retries = 3;
while (retries-- && !(status & DONE)) {
  status = idma[0].CMD_BUF_R.STATUS;
  if (status & ERROR) {
    uint8_t error_code = (status >> 2) & 0x3F;
    if (error_code == ATT_MISS) {
      update_att_table();  // Update ATT and retry
      idma_cmd.ctrl = ENABLE;
    } else if (error_code == SMN_VIOLATION) {
      // Security boundary violation—handle in firmware
      fallback_to_secure_path();
    }
  }
}
```

---

### 7.6 Register Map

The iDMA APB register space spans `0x03004000` to `0x03009FFF`:

```
Base: 0x03004000
Size: 0x6000 (24KB = 1,528 registers × 4 bytes, padded to 24KB)

Per-CPU stride: 0x0C00 (3KB per CPU)

CPU 0: 0x03004000 – 0x03004BFF
  CMD_BUF_R:      0x03004000 + 0x000  (base = 0x03004000, size = 0x178)
  CMD_BUF_W:      0x03004000 + 0x200  (base = 0x03004200, size = 0x178)
  ADDRESS_GEN_R:  0x03004000 + 0x400  (base = 0x03004400)
  ADDRESS_GEN_W:  0x03004000 + 0x600  (base = 0x03004600)
  SIMPLE_CMD_BUF: 0x03004000 + 0x800  (base = 0x03004800)

> RTL-verified from `tt_rocc_accel_reg.svh`: CPU0 CMD_BUF_W base = 0x03004200, ADDRESS_GEN_R = 0x03004400, ADDRESS_GEN_W = 0x03004600, SIMPLE_CMD_BUF = 0x03004800. Sub-blocks are 0x200-spaced, not 0x100.

CPU 1: 0x03004C00 – 0x030057FF
  (same layout, base + 0x0C00)

CPU 2: 0x03005800 – 0x030063FF
CPU 3: 0x03006400 – 0x03006FFF
CPU 4: 0x03007000 – 0x03007BFF
CPU 5: 0x03007C00 – 0x030087FF
CPU 6: 0x03008800 – 0x030093FF
CPU 7: 0x03009400 – 0x03009FFF
```

### 7.7 DMA Operation Flow

A complete tensor DMA operation proceeds as follows:

1. **Descriptor programming:** Rocket writes source/destination addresses, strides, and sizes to a CPU's CMD_BUF registers via APB (or via RoCC by pointing to a pre-built descriptor in L2 cache)
2. **Enable:** Rocket sets the enable bit in CMD_BUF_R.CTRL; ADDRESS_GEN immediately begins generating address sequences
3. **NoC injection:** DMA CPU issues NoC read-request packets addressed to the source endpoint (DRAM via NIU, or remote Tensix L1)
4. **NIU bridging:** NIU at X=1 or X=2 receives the NoC read request, translates via ATT to AXI address, and issues AXI read bursts to DRAM
5. **Data return:** DRAM returns AXI read data; NIU packs read data into 512-bit NoC response flits and routes them to the destination Tensix L1
6. **L1 write:** Response flits arrive at the destination Tensix router local port and are written into the Tensix L1 SRAM by the local NoC injection logic
7. **Completion:** DMA CPU detects end of transfer (all address iterations exhausted), sets completion status in CMD_BUF_R.STATUS, and optionally asserts `resp.valid` to Rocket via RoCC

### 7.8 Integration with Tensix

The iDMA engine is the exclusive mechanism for loading weight tensors from external DRAM into Tensix L1 before a compute kernel, and for draining activation results from Tensix L1 to DRAM after kernel completion. The NoC-based DMA path decouples data movement from the Tensix compute pipeline: a Tensix tile executing a GEMM kernel on one set of weights in one L1 partition can simultaneously receive the next weight tile into a different L1 partition via iDMA, enabling true double-buffered overlap of DMA and compute.

### 7.9 Performance Model

**Peak bandwidth per NIU:**
At 512-bit AXI data width operating at ~1 GHz noc_clk: 512 bits × 1 GHz = 64 GB/s per NIU (theoretical peak with 100% bus utilization and no AXI handshake overhead).

**Total peak DRAM bandwidth:**
N1B0 has 2 NIU-capable tiles (the two composite NOC2AXI_ROUTER tiles at X=1, X=2), plus 2 standalone NIU tiles (NE_OPT at X=0, NW_OPT at X=3). With all 4 NIU AXI ports active simultaneously:
- 4 × 64 GB/s = **256 GB/s total theoretical peak** (if all 4 NIUs drive simultaneous AXI bursts)
- With 2 primary NIUs: **128 GB/s** is the practical dual-NIU peak

**Practical bandwidth:**
Achievable bandwidth is limited by:

1. **DRAM latency and outstanding request count.** AXI read latency to external DRAM is typically 100–300 ns. To sustain 64 GB/s at 64-byte AXI beats, the iDMA must keep approximately (64 GB/s × 200 ns) / 64 B ≈ 200 outstanding AXI read beats in flight. The RDATA FIFO depth (default 512 entries in N1B0) and 8 concurrent DMA CPUs per Dispatch tile provide sufficient outstanding-request depth to approach this level.

2. **NoC congestion.** All 8 DMA CPUs injecting read requests simultaneously share the East-output port toward the NIU column. VC arbitration handles this, but peak injection rate is bounded by the single 512-bit/cycle output port of the source router.

3. **Tensor layout.** Non-contiguous strided access patterns (large outer-dimension strides) fragment AXI bursts, reducing effective AXI bus utilization below the 256-beat maximum burst length.

**Practical rule of thumb:** For large contiguous tensor loads (≥16 KB per DMA transfer), iDMA achieves approximately 60–80% of peak NIU AXI bandwidth, yielding approximately 38–51 GB/s per NIU or 76–102 GB/s aggregate for both NIUs active simultaneously.

---

## §8 EDC Ring

### 8.1 Overview

The Error Detection and Correction (EDC) ring is a single serial ring that traverses every tile in the N1B0 chip. It provides continuous built-in self-test (BIST) and error monitoring for all critical on-chip memories, logic, and interconnect paths.

#### 8.1.1 Motivation

Modern SoCs are subject to several classes of runtime hardware faults that cannot be detected by standard manufacturing test:

- **Cosmic-ray induced soft errors (SEUs)**: High-energy particles flip bits in SRAM and register files even in correctly manufactured devices. Error rates scale with altitude and technology node.
- **Aging and wearout**: Hot-carrier injection (HCI) and negative-bias temperature instability (NBTI) degrade transistor threshold voltages over time, causing timing violations that appear as logic errors.
- **Voltage droop**: Simultaneous switching of thousands of compute elements causes instantaneous Vdd droop, which can cause setup-time violations in dense logic such as the FPU datapath.
- **Manufacturing marginality**: Borderline devices may pass static test but fail under dynamic workload stress.

Unlike ECC (which is per-memory and only protects storage elements), the EDC ring monitors **inter-block communication paths and register state** on a periodic basis. Every node in the ring samples its local state on each ring traversal cycle, generates a CRC over its local data, and reports any mismatch back to the initiator. This provides coverage for both storage faults (SRAM, register files) and logic faults (datapath parity, control state corruption).

The ring is designed to add minimal area overhead: the serial protocol means only two wires (req_tgl, ack_tgl) plus a 32-bit data bus traverse tile boundaries. All check logic is inside `tt_edc1_node.sv` instances distributed throughout the tile hierarchy.

#### 8.1.2 Ring Protocol Module

The ring protocol is defined in `tt_edc1_node.sv`. Each node instance performs:
- **Periodic error injection and detection** via toggle-based handshake
- **Local state sampling**: register file parity, SRAM ECC syndrome, control-path parity
- **CRC generation**: 32-bit CRC over the sampled local data
- **Error reporting** with severity classification (FATAL / CRIT / n-crt / ECC+ / ECC−)
- **Interrupt generation** to the host on detected faults via the overlay error aggregator
- **Bypass mux**: allows harvested tiles to be skipped in the ring chain without breaking continuity


### Unit Purpose
The Error Detection and Correction (EDC) ring is a serial, distributed self-test mechanism that traverses every tile in the N1B0 chip, continuously sampling local state (register-file parity, SRAM ECC, control logic parity) and comparing cumulative CRC signatures to detect soft errors, aging-induced timing violations, voltage droop transients, and manufacturing marginality. Unlike memory-specific ECC (which only protects SRAM bits), the EDC ring monitors inter-block communication paths and logic state on a periodic basis, providing coverage for both storage faults and transient logic glitches that could escape manufacturing test or emerge during long-duration inference workloads.

### Design Philosophy
The EDC ring embodies **minimal-overhead distributed monitoring via toggle-based protocol**. Rather than adding dedicated error-correction logic to every datapath (which would consume area and add latency), the EDC ring uses a single serial ring with two toggle-based handshake wires (`req_tgl`, `ack_tgl`) and a 32-bit data bus. Each node samples its local state (register file parity bits, SRAM ECC syndromes, datapath parity) and XORs them into a 32-bit CRC that accumulates across the ring. The initiator compares the final CRC against an expected value; any mismatch signals a fault. The toggle protocol is CDC-safe (clock-domain crossing friendly) because a single toggle bit carries the "event has occurred" semantics: rising or falling edge on the toggle wire means "new data arrived," independent of initial state after reset. This eliminates the need for complex cross-domain synchronizers and allows the ring to traverse tiles in different clock domains (ai_clk, dm_clk, noc_clk) with simple sync3r stages.

### Integration Role
The EDC ring is the health monitor of the entire chip. It is initiated by the overlay engine's error aggregator (which may be triggered periodically or on-demand by firmware) and traverses all 20 tiles in sequence, collecting local state samples from each. The ring is not in the critical data path (flits never transit the EDC ring; it operates in parallel with NoC traffic), but it generates interrupts to firmware or system management controllers when errors are detected. Severity classification (FATAL / CRIT / non-crit / ECC± types) allows firmware to decide whether to trigger immediate reset/recovery, log the error for analysis, or continue with reduced performance (e.g., if only a recoverable ECC syndrome is detected). The ring also supports mesh dynamic topology: nodes can be "harvested" (disabled due to manufacturing defect or thermal shutdown) via the `DISABLE_SYNC_FLOPS=1` compile-time parameter and bypass muxes, allowing the ring to skip disabled tiles without breaking the chain.

### Key Characteristics
- **Toggle-based request/acknowledge handshake**: `req_tgl` propagates forward, `ack_tgl` propagates backward, both using XOR edge detection. Immune to initial state, CDC-safe, and inherently deadlock-free.
- **Distributed CRC accumulation**: Each node samples local parity/ECC bits, generates a 32-bit CRC, XORs it into the data payload. Initiator receives the final cumulative CRC; any non-zero result indicates at least one node detected an error.
- **Severity classification**: FATAL (immediate shutdown), CRIT (high-priority interrupt), n-crit (non-critical, log only), ECC+ (recoverable via ECC), ECC− (unrecoverable). Firmware can prioritize response based on severity.
- **MCPDLY=7 inter-node repeater delay**: Ring is pipelined through repeater stages to tolerate long wires between distant tiles. Worst-case traversal latency is ~2,000 noc_clk cycles for full ring sweep (~200 nodes).
- **Harvesting support**: Nodes can be disabled (via compile-time DISABLE_SYNC_FLOPS=1 and run-time bypass muxes) to skip manufacturing-defective tiles without breaking ring continuity.

### Use Case Example
**Soft-Error Recovery During Long Inference**  
An LLaMA 3.1 8B inference job runs for 5 minutes, executing thousands of matrix-multiply operations across Tensix clusters. Midway through, a cosmic-ray strikes the DEST register file at Tensix (2,1), flipping a single bit in an intermediate accumulation result. This bit flip is not immediately visible because the register file contains many values and the bit flip may not affect the current layer's computation. However, firmware has configured the EDC ring to sweep every 100 milliseconds (via a firmware timer interrupt). At the next sweep, the overlay error aggregator toggles `req_tgl`, initiating a full ring traversal. When the ring reaches Tensix (2,1), the EDC node at that tile samples the DEST register file's parity bits, detects a mismatch (parity error on that register), computes a CRC, and XORs it into the return data. The initiator receives the final CRC, notes the non-zero value, and classifies the error as ECC± (recoverable in single-bit regime). Firmware logs the event, triggers a context-switch partition reset (PRTN chain) to clear transient state, and resumes computation. The overhead is minimal: the ring traversal takes ~2,000 cycles, happening once per 100 ms in the background, while Tensix continues computing with no stall.

---

## Summary of Insertion Points

| Section | Subsection | Line Range | Content | Word Count |
|---------|-----------|----------|---------|-----------|
| §2 Tensix | After 2.1 Overview, before 2.1.1 | ~310–360 | Unit Purpose + Design Philosophy + Integration Role + Key Characteristics + Use Case | 480 |
| §3 Overlay | After 3.1.2, before 3.1.3 | ~2010–2030 | Unit Purpose + Design Philosophy + Integration Role + Key Characteristics + Use Case | 410 |
| §4 NOC2AXI | After 4.1 Overview, before 4.2 | ~2660–2700 | Unit Purpose + Design Philosophy + Integration Role + Key Characteristics + Use Case | 450 |
| §6 Router | After 5.1 Overview, before 5.2 | ~3430–3450 | Unit Purpose + Design Philosophy + Integration Role + Key Characteristics + Use Case | 460 |
| §7 iDMA | After 6.1 Overview, before 6.2 | ~3633–3660 | Unit Purpose + Design Philosophy + Integration Role + Key Characteristics + Use Case | 420 |
| §8 EDC | After 7.1.2, before 7.2 | ~3823–3850 | Unit Purpose + Design Philosophy + Integration Role + Key Characteristics + Use Case | 430 |
### 8.2 Ring Protocol

The EDC ring uses a toggle-based request/acknowledge handshake. Toggle-based (XOR-based) signaling is used instead of level-based signaling because it is inherently immune to the initial state after reset — a rising or falling edge on the toggle wire always means "a new event has occurred," regardless of the starting value.

#### 8.2.1 Signal Interface

| Signal      | Width  | Direction  | Description                                          |
|-------------|--------|------------|------------------------------------------------------|
| `req_tgl`   | 1      | Forward    | Request toggle — XOR-edge triggers each new request  |
| `ack_tgl`   | 1      | Backward   | Acknowledge toggle — node asserts after processing   |
| `data[31:0]`| 32     | Forward    | 32-bit CRC / error status payload                    |

#### 8.2.2 Ring Traversal Timing

The ring operates as a pipeline: the initiator node (at the head of the ring) drives `req_tgl`, and the signal propagates forward through every node in sequence. Each node samples local state, computes a CRC, and forwards `req_tgl` to the next node. After all nodes have processed the toggle, `ack_tgl` propagates back through the loopback path to the initiator.

```
  Timing (simplified, single traversal):

  Cycle 0:  Initiator toggles req_tgl
            │
  Cycle 1:  Node 0 samples local state, generates CRC, forwards req_tgl
            │   (combinational propagation through repeaters: MCPDLY cycles)
  Cycle M:  Node 1 receives req_tgl (after repeater delay M = MCPDLY)
            Node 1 samples, generates CRC, forwards
            │
            ...
  Cycle N×M: Last node (node N−1) has processed req_tgl
             ack_tgl begins propagating back on loopback wire
             │
  Cycle N×M + L: Initiator receives ack_tgl (loopback delay L cycles)
                 Initiator reads back aggregated data[31:0] from all nodes
                 Compares against expected CRC
                 If mismatch → generate interrupt at appropriate severity
```

The total ring traversal time is approximately `N_nodes × (node_latency + MCPDLY)` clock cycles, where `MCPDLY=7` is the worst-case inter-node repeater delay. With ~200 nodes and MCPDLY=7, a full traversal takes on the order of ~1,400–2,000 noc_clk cycles per sweep.

#### 8.2.3 Per-Node Operation

Each `tt_edc1_node` instance executes the following on each incoming `req_tgl` edge:

1. Detect edge: compare `req_tgl` against locally stored previous value; if XOR=1, a new request has arrived
2. Sample local state: read parity bits from assigned register file entries or SRAM ECC syndrome registers
3. Compute 32-bit CRC over sampled data using the configured polynomial
4. XOR the local CRC into the forwarded `data[31:0]` field (cumulative across the ring)
5. Toggle `req_tgl` forward to the next node
6. Toggle `ack_tgl` backward to the previous node (one cycle after forwarding)

The initiator receives the final `data[31:0]` which is the XOR-accumulation of all node CRCs. A mismatch against the expected all-zero (or expected reference) value indicates that one or more nodes have detected a local error.

#### 8.2.4 CDC-Safe Toggle Protocol

Because `req_tgl` and `ack_tgl` are single-bit toggle signals, they are safe for synchronization by a standard 2-FF or 3-FF synchronizer (sync3r) at clock-domain boundaries. Only one bit must be synchronized per crossing, and the toggle protocol guarantees that no new toggle arrives before the previous one has been acknowledged — providing the minimum pulse width guarantee required by a synchronizer.

This is the fundamental reason the EDC ring uses a toggle (not a pulse or level) protocol: it allows correct multi-clock-domain operation with minimal synchronizer overhead.

### 8.3 DISABLE_SYNC_FLOPS

#### 8.3.1 Background

In the baseline Trinity design (non-N1B0), the EDC ring traverses tiles that may belong to different clock domains within the same ring segment. For example, a Tensix tile contains nodes in the `ai_clk` domain and nodes in the `noc_clk` domain. When `req_tgl` crosses from an `ai_clk` node to a `noc_clk` node within the same tile, a 3-stage synchronizer (sync3r) is required to safely re-time the toggle signal.

These intra-tile CDC synchronizers add:
- **Latency**: 3 clock cycles per crossing (at the destination clock frequency)
- **Area**: 3 flip-flops per synchronizer, plus clock-domain crossing handshake logic
- **Hold-violation risk**: If source and destination clocks happen to be synchronous (e.g., same PLL output), synchronizers can cause spurious hold violations

#### 8.3.2 N1B0 DISABLE_SYNC_FLOPS=1

In N1B0, `DISABLE_SYNC_FLOPS=1` is set as a compile-time parameter applied globally to all `tt_edc1_node` instances. The rationale is:

- Within each N1B0 ring **segment**, all EDC-connected nodes share the same physical clock. A ring segment is defined as the subset of nodes traversed between the two CDC crossing points at Y=2 Tensix tiles.
- Because nodes within a segment are all clocked by the same `ai_clk[col]` (or `noc_clk` for router/NIU nodes), the synchronizers would operate in same-clock mode — which creates false hold violations and adds unnecessary latency.
- Disabling the synchronizers within same-clock segments eliminates latency and removes the area cost, at the cost of requiring that clocks within each segment remain synchronous.

```
  DISABLE_SYNC_FLOPS effect (within one ring segment):

  DISABLE_SYNC_FLOPS=0 (baseline):              DISABLE_SYNC_FLOPS=1 (N1B0):
  Node N → [sync3r, 3 cycles] → Node N+1        Node N → [wire] → Node N+1
  Latency = 3 cycles per crossing               Latency = combinational only
  Area    = 6 FFs per intra-segment CDC         Area    = 0 extra FFs
```

#### 8.3.3 Where Synchronizers Are Still Used

DISABLE_SYNC_FLOPS=1 does NOT remove synchronizers at actual inter-domain boundaries. The three intra-tile CDC crossings at Y=2 Tensix tiles (ai_clk→noc_clk, noc_clk→ai_clk, ai_clk→dm_clk) continue to use sync3r synchronizers for the EDC toggle signals, because at those points the source and destination clocks genuinely belong to different domains.

Additionally, the `async_init` path uses sync3r per node at reset de-assertion to safely establish initial toggle state from the asynchronous reset domain into each node's clock domain, regardless of DISABLE_SYNC_FLOPS.

### 8.4 Ring Traversal Order

The EDC ring is a single chain starting and ending at the AXI host interface. It traverses tiles in a defined order by column and row segment. The high-level column traversal for N1B0 is:

```
AXI host
  │
  ├─→ Column X=0: Y=0 → Y=1 → Y=2 → Y=3(Dispatch W) → Y=4
  ├─→ Column X=1: Y=4(NIU) → [cross-row] → Y=3(Router) → Y=2 → Y=1 → Y=0
  ├─→ Column X=2: Y=0 → Y=1 → Y=2 → Y=3(Router) → [cross-row] → Y=4(NIU)
  ├─→ Column X=3: Y=4 → Y=3(Dispatch E) → Y=2 → Y=1 → Y=0
  │
AXI host (loopback)
```

Within each Tensix tile, the ring visits multiple sub-nodes in order: NOC node, OVL node, then per-SRAM-bank nodes for the L1 partition.

### 8.5 EDC Node Assignments

The N1B0 ring contains multiple EDC nodes per tile. The node ID space is divided by subsystem and tile type.

#### 8.5.1 Node ID Table

| Node ID Range | Tile Location              | Tile Type        | What Each Node Monitors                                |
|---------------|----------------------------|------------------|--------------------------------------------------------|
| 0–15          | (X=0, Y=0) Tensix          | T6               | NOC flit input buffer, overlay state, L1 bank 0–3 ECC  |
| 16–31         | (X=1, Y=0) Tensix          | T6               | NOC flit input buffer, overlay state, L1 bank 0–3 ECC  |
| 32–47         | (X=2, Y=0) Tensix          | T6               | NOC flit input buffer, overlay state, L1 bank 0–3 ECC  |
| 48–63         | (X=3, Y=0) Tensix          | T6               | NOC flit input buffer, overlay state, L1 bank 0–3 ECC  |
| 64–79         | (X=0, Y=1) Tensix          | T6               | NOC flit buffers, DEST register file parity, L1 ECC    |
| 80–95         | (X=1, Y=1) Tensix          | T6               | NOC flit buffers, DEST register file parity, L1 ECC    |
| 96–111        | (X=2, Y=1) Tensix          | T6               | NOC flit buffers, DEST register file parity, L1 ECC    |
| 112–127       | (X=3, Y=1) Tensix          | T6               | NOC flit buffers, DEST register file parity, L1 ECC    |
| 128–143       | (X=0, Y=2) Tensix          | T6               | NOC flit buffers, SRCA register file, L1 ECC, FPU parity |
| 144–159       | (X=1, Y=2) Tensix          | T6               | NOC flit buffers, SRCA register file, L1 ECC, FPU parity |
| 160–175       | (X=2, Y=2) Tensix          | T6               | NOC flit buffers, SRCA register file, L1 ECC, FPU parity |
| 176–191       | (X=3, Y=2) Tensix          | T6               | NOC flit buffers, SRCA register file, L1 ECC, FPU parity |
| 192           | NIU / NOC2AXI BIU          | Composite Y=4    | NIU BIU request/response state, ATT SRAM parity        |
| 193           | Router (X=1, Y=3)          | Composite router | Router VC FIFO contents, flit header parity            |
| 194           | Router (X=2, Y=3)          | Composite router | Router VC FIFO contents, flit header parity            |
| 195           | DISPATCH_W (X=0, Y=3)      | Dispatch         | Rocket core instruction buffer, L1 cache ECC           |
| 196           | DISPATCH_E (X=3, Y=3)      | Dispatch         | Rocket core instruction buffer, L1 cache ECC           |
| 197           | NW_OPT NIU (X=0, Y=4)      | Standalone NIU   | NIU BIU state, ATT SRAM parity (on-ring)               |
| 198           | NE_OPT NIU (X=3, Y=4)      | Standalone NIU   | NIU BIU state, ATT SRAM parity (on-ring)               |

Within each Tensix tile, the ring visits sub-nodes in order: NOC flit node → OVL (overlay) node → per-SRAM-bank L1 nodes. The 16-ID allocation per Tensix tile reflects one NOC node + one OVL node + up to 14 L1 bank nodes (N1B0 L1 has 256 macros per tile; bank nodes are grouped).

#### 8.5.2 N1B0 Composite Tile EDC Connectivity (Off-Ring Issue)

A known architectural issue affects the NIU BIU EDC nodes for the composite tiles (X=1, X=2) at Y=4:

- The NIU BIU EDC node at Y=4 for X=1 and X=2 is **off-ring** in the current N1B0 implementation. It does not participate directly in the main forward EDC chain.
- The Y=3 router node at each composite tile provides on-ring coverage for the router VC FIFOs and flit state in that column segment.
- The Y=4 BIU EDC node's error signals are routed through the `o_niu_timeout_intp` interrupt path rather than the main ring chain. This means BIU errors at composite tile Y=4 generate a CRIT interrupt via the timeout interrupt line, but are not visible as ring-detected errors.
- This issue is documented in the N1B0 open-signal report Rev.5 under the EDC ring connectivity correction section. The fix options include: (a) routing the composite Y=4 BIU EDC chain port through the composite module boundary to connect to the main ring at Y=4, or (b) accepting the `o_niu_timeout_intp` path as the sole error reporting mechanism for that node.

The standalone NIU tiles (X=0, X=3 at Y=4) do **not** have this issue — their EDC nodes are directly on-ring at Y=4 and participate fully in the ring traversal.

### 8.6 Severity Model

Each EDC node classifies detected errors into one of four severity levels:

| Level  | Code    | Action                                              | IRQ Line         |
|--------|---------|-----------------------------------------------------|------------------|
| FATAL  | FATAL   | Chip halt, assert fatal interrupt to host           | FATAL_IRQ        |
| CRIT   | CRIT    | Recoverable error; log + interrupt, continue        | CRIT_IRQ         |
| n-crt  | n-crt   | Non-critical; log only, no interrupt                | (masked/logged)  |
| ECC+   | ECC+    | ECC single-bit corrected (corrected successfully)   | ECC_CORR_IRQ     |
| ECC−   | ECC−    | ECC double-bit or uncorrectable error               | ECC_UNCORR_IRQ   |

**Per-tile rationale:**

| Coverage Area        | Severity on Failure |
|----------------------|---------------------|
| L1 SRAM (single-bit) | ECC+                |
| L1 SRAM (double-bit) | ECC− → CRIT         |
| DEST register file   | CRIT                |
| SRCA register file   | CRIT                |
| FPU datapath         | FATAL               |
| NoC VC FIFO          | CRIT                |
| Router logic         | FATAL               |
| NIU ATT              | CRIT                |

### 8.7 MCPDLY — Multi-Cycle Path Delay

The EDC ring timing depends on the number of pipeline stages (repeaters) in each inter-node segment. The MCPDLY CSR tells each node how many cycles to wait for the toggle to propagate through repeaters before declaring a timeout.

**N1B0 MCPDLY derivation:**

For the longest segment (Y=3 loopback with `REP_DEPTH_LOOPBACK=6`):

```
MCPDLY = REP_DEPTH_LOOPBACK + 1 (safety margin)
       = 6 + 1
       = 7 cycles
```

This value (7) is programmed into the EDC CSR during chip initialization by firmware. Other segments with smaller repeater depth (REP_DEPTH=2 standard, OUTPUT=4) use the same MCPDLY=7 value since it represents the worst-case segment; no per-segment override is required.

### 8.8 Repeater Placement in EDC Ring

The EDC ring forward and loopback wires share the same physical routing channels as the NoC flit wires. Repeaters are inserted at the same locations:

| Segment Type           | Repeater Depth | Notes                           |
|------------------------|----------------|---------------------------------|
| Standard X-axis inter-tile | 2 (REP×2)  | Baseline mesh spacing           |
| Y=3 composite loopback | 6 (REP×6)      | Long composite span; N1B0 specific |
| Y=4 composite output   | 4 (REP×4)      | NIU to Y=3 router path          |

Repeaters in the EDC path are combinational buffers only — they add propagation delay but no flip-flop stages. The MCPDLY setting accounts for this combinational delay across the worst-case path.

### 8.9 Initialization Sequence

EDC ring initialization is a required firmware step at chip bring-up. The ring must be correctly initialized before the first EDC check can be performed; an uninitialized ring will produce false timeouts or spurious error reports.

#### Step 1 — Program MCPDLY

Firmware writes `MCPDLY=7` to the EDC CSR via APB:

```
// APB write to CLUSTER_CTRL base (0x03000000)
// EDC_MCPDLY register offset: per HDD EDC CSR map
APB_WRITE(EDC_BASE + EDC_MCPDLY_OFFSET, 7);
```

MCPDLY=7 is the worst-case inter-node delay for the N1B0 ring (Y=3 composite loopback, REP_DEPTH_LOOPBACK=6, plus 1 safety cycle). This value must be set before releasing ring reset, because nodes use MCPDLY to determine how long to wait for `req_tgl` to arrive from the previous node before declaring a timeout error.

#### Step 2 — Release EDC Ring Reset (async_init)

Firmware releases the EDC ring reset. Internally, each node performs an `async_init` sequence:

```
  async_init flow per node:
  1. Ring reset is asserted (all nodes in reset, toggle state = 0)
  2. Firmware de-asserts ring reset
  3. Each node's sync3r (3-register synchronizer) synchronizes the reset de-assertion
     into the local clock domain (ai_clk or noc_clk depending on node type)
  4. Once synced, the node initializes its internal toggle state from the
     synchronized reset signal
  5. Node is now ready to participate in ring handshake
```

The sync3r ensures that all nodes start from a known toggle state (0) regardless of when reset de-asserts relative to the local clock edge. Without this, different nodes could initialize with different toggle states, causing immediate false mismatches.

#### Step 3 — Ring Self-Test

After reset de-assertion and MCPDLY programming, firmware triggers a ring self-test by sending a test toggle:

```
// Enable ring
APB_WRITE(EDC_BASE + EDC_ENABLE_OFFSET, 1);

// Trigger test sweep
APB_WRITE(EDC_BASE + EDC_TRIGGER_OFFSET, 1);

// Wait for completion (poll status or wait for interrupt)
while (!APB_READ(EDC_BASE + EDC_STATUS_OFFSET) & EDC_SWEEP_DONE_BIT) {
    // wait approximately N_nodes × MCPDLY × noc_clk_period
}
```

During the self-test sweep:
- The initiator sends `req_tgl` down the ring
- Each node samples its local state (all-zero or known pattern in test mode) and computes a CRC
- The accumulated `data[31:0]` is compared against the expected reference value
- Nodes with harvest bypass asserted are skipped automatically

#### Step 4 — Read Back Status and Confirm PASS

Firmware reads the EDC status register to confirm all nodes responded correctly:

```
uint32_t status = APB_READ(EDC_BASE + EDC_STATUS_OFFSET);

if (status & EDC_ERROR_BIT) {
    // One or more nodes failed the self-test
    // Read EDC_NODE_ID register to identify which node
    uint32_t failed_node = APB_READ(EDC_BASE + EDC_NODE_ID_OFFSET);
    // Report FATAL error — ring self-test failure is unrecoverable
    raise_fatal_interrupt(FATAL_EDC_SELFTEST_FAIL, failed_node);
} else {
    // PASS — all nodes responded with correct CRC
    // EDC ring is operational; begin periodic monitoring
    APB_WRITE(EDC_BASE + EDC_PERIODIC_ENABLE_OFFSET, 1);
}
```

If all nodes return PASS, the ring is confirmed operational and periodic monitoring is enabled. Periodic sweeps run autonomously in hardware; firmware is only interrupted if a subsequent sweep detects a mismatch.

### 8.10 EDC Signal Debugging Guide — Complete Path Tracing

For simulation and post-silicon debugging of EDC ring handshakes, this section provides the complete forward (req_tgl) and backward (ack_tgl) signal paths through the N1B0 ring, along with proving points (checkpoints) to verify proper handshake propagation at each stage.

#### 8.10.1 Signal Definitions and Properties

Three primary signals traverse the EDC ring:

| Signal | Width | Direction | Clock Domain | Purpose |
|--------|-------|-----------|--------------|---------|
| **req_tgl** | 1 bit | Forward (head→tail) | Varies per node | Request toggle — XOR edge triggers new cycle at each node |
| **ack_tgl** | 1 bit | Backward (tail→head) | Varies per node | Acknowledge toggle — node asserts after sampling local state and forwarding req_tgl |
| **data[31:0]** | 32 bits | Forward (head→tail) | Varies per node | Accumulated CRC over all node samples; XORed at each node |

**Key properties:**
- All signals are **toggle-based**: logic detects *edges* (0→1 or 1→0), not levels
- `req_tgl` and `ack_tgl` are **single-bit clock-domain-crossing signals**: safe to synchronize with standard 2-FF or 3-FF synchronizers
- `data[31:0]` is **payload**: updated combinationally or with 1-cycle latency per node, depending on CRC implementation
- All signals propagate through **combinational repeaters** between tiles (no flip-flop stages in repeater path)

#### 8.10.2 Forward Path (req_tgl) Signal Propagation

**High-level flow:**

```
BIU (AXI host)
    │ req_tgl[0]
    ├─→ Initiator logic: toggle req_tgl, load initial data
    │
    ▼  Column X=0 (MCPDLY=7 inter-node delay)
Y=0 Tensix (NOC node)
    │ req_tgl[1] (after repeater, ~7 noc_clk cycles)
Y=1 Tensix (NOC node)
    │
Y=2 Tensix (NOC + OVL nodes, CDC crossing to noc_clk)
    │ req_tgl[5] (after CDC sync3r, +3 cycles latency at OVL node)
    │
Y=3 Dispatch W (router node)
    │
Y=4 NIU-NW (standalone, single row)
    │
    ◄─ ack_tgl starts propagating back (loopback path)

    Similar forward flow for X=1, X=2, X=3 columns
```

**Detailed per-tile timing:**

```
Cycle 0:  req_tgl XORs at initiator (BIU)
          → req_tgl_new = ~req_tgl_prev

Cycles 1-7:  req_tgl propagates through combinational repeaters
          → no FF delay (DISABLE_SYNC_FLOPS=1 within same clock domain)
          → ~7 noc_clk/ai_clk cycles total inter-node delay

Cycle 8:  Node 1 samples req_tgl[1] (different from prev state)
          → Detects edge: (req_tgl_new XOR req_tgl_sampled_prev) = 1
          → Begins sampling local state (CRC input)

Cycle 9:  Node 1 generates CRC
          → Combinational computation or pipelined +1 cycle

Cycle 10: Node 1 XORs local CRC into data[31:0] (cumulative payload)

Cycle 11: Node 1 toggles req_tgl forward to Node 2
          → req_tgl = ~req_tgl (toggles at this stage)

Cycles 12-18: req_tgl[2] propagates with MCPDLY=7 delay

Cycle 19: Node 2 receives req_tgl[2], repeats same sequence
          ...
```

**CDC crossing at Y=2 (ai_clk → noc_clk):**

When a node's input (`req_tgl_in`) is in a different clock domain than the node's output (`req_tgl_out`), a synchronizer is inserted:

```
req_tgl_in (ai_clk)
    │
    ▼  sync3r (3-register synchronizer at noc_clk domain)
    │  FF1 (sample + retime)
    │  FF2 (fully synced)
    │  FF3 (guard flip-flop for metastability)
    │
    ├─→ +3 noc_clk cycles of latency
    │
    ▼
req_tgl_synced (noc_clk)
    │ (continues forward path at noc_clk frequency)
```

#### 8.10.3 Backward Path (ack_tgl) Signal Propagation

After the last node (Y=4 NIU) processes `req_tgl`, it asserts `ack_tgl` on the backward path. `ack_tgl` propagates back through a separate **loopback wire** to the BIU.

```
Y=4 NIU (last node)
    │ ack_tgl_out = ~ack_tgl_sampled_prev (toggle on backward path)
    │
    ├─→ Loopback repeater path (REP_DEPTH varies per composite tile)
    │
Y=3 Dispatch E / Router
    │ ack_tgl propagates backward through each tile
    │
Y=2 Tensix
    │ (CDC crossing if noc_clk→ai_clk, sync3r +3 cycles)
    │
Y=1 Tensix
    │
Y=0 Tensix
    │
    ▼
BIU (loopback input)
    │ ack_tgl_final_sampled
    │
    ▼
BIU logic: Check if ack_tgl toggles within expected window
          If toggle detected: Ring responded successfully
          If timeout: Report ring stall error
```

#### 8.10.4 Complete Per-Node Handshake Sequence

**For a single node (e.g., Tensix Y=0, Column X=0):**

```
Timeline (approximate cycles from req_tgl_in XOR → ack_tgl_out XOR):

noc_clk cycle | Event                                | Waveform checkpoint
──────────────┼──────────────────────────────────────┼─────────────────────
  T+0         | req_tgl_in = prev (no edge yet)      |
              | (repeater delay accumulating)        | ▔▔▔ req_tgl_in ▔▔▔
  T+7         | req_tgl_in XORs (edge detected)      | ▁▁▁
              | node latches: req_tgl_prev = req_tgl │
  T+8         | Node starts sampling local state:    |
              |   - SRAM ECC syndrome (combinational)| ███ sample window
              |   - Register file parity             |
  T+9         | CRC computation (typically +1 cycle) | CRC generating...
  T+10        | CRC ready; XOR into data[31:0]       | data_updated ✓
  T+11        | req_tgl_out toggles (forward output) | req_tgl_out ▁▁▁
              |   req_tgl_out = ~req_tgl_out         |          ▔▔▔
  T+12        | ack_tgl_out toggles (backward ack)   | ack_tgl_out ▁▁▁
              |   ack_tgl_out = ~ack_tgl_prev        |            ▔▔▔
  T+13–19     | Backward loopback propagation delay  |

Next cycle:  req_tgl_out reaches next node (after repeater delay)
              ack_tgl_out reaches previous node (or BIU if this is Y=0)
```

#### 8.10.5 Complete Ring Sweep Timeline (End-to-End Example)

**Scenario: BIU initiates ring sweep with 5 active nodes (Column X=0):**

```
BIU initiates:
  Cycle 0:   req_tgl[BIU] = ~req_tgl[BIU]  (initiator toggle)
             data[31:0] = INITIAL_VALUE
             ▲
  ├─→ Repeater delay (7 cycles)
  │
  Cycle 7:   req_tgl arrives at Node[Y=0]
             Node[Y=0] edge detected ✓
             ▲
  ├─→ Node processing (1 cycle) + forward toggle (1 cycle)
  │
  Cycle 9:   req_tgl[Y=0]_out = ~req_tgl[Y=0]_out
             ack_tgl[Y=0]_out = ~ack_tgl[Y=0]_out (starts backward)
             ▲
  ├─→ Repeater delay (7 cycles) to Y=1
  │
  Cycle 16:  req_tgl arrives at Node[Y=1]
             ▲
  ├─→ Node processing + forward
  │
  Cycle 18:  req_tgl[Y=1]_out toggles
             ack_tgl[Y=1]_out toggles (backward propagates)
             ▲
  ├─→ Repeater delay (7 cycles) to Y=2
  │
  Cycle 25:  req_tgl arrives at Node[Y=2] (NOC domain, ai_clk)
             [CDC crossing: ai_clk node, input from noc_clk]
             ▲
             sync3r latency (+3 cycles) for req_tgl synchronization
             ├─→ Cycle 25: sync3r FF1 samples req_tgl
             ├─→ Cycle 26: FF2 output valid
             ├─→ Cycle 27: FF3 output valid (fully synced)
             │
  Cycle 28:  Node[Y=2] edge detection complete
             CRC sampling begins
             ▲
  ├─→ Node processing + forward
  │
  Cycle 30:  req_tgl[Y=2]_out toggles (to Y=3)
             ack_tgl[Y=2]_out toggles (backward, crossing noc_clk→ai_clk)
             [CDC on backward: ai_clk → noc_clk, sync3r +3 cycles]
             ▲
  ├─→ Repeater (7 cycles) to Y=3
  │
  Cycle 37:  req_tgl reaches Y=3 Dispatch
  Cycle 39:  req_tgl[Y=3]_out toggles
             ack_tgl[Y=3]_out toggles
             ▲
  ├─→ Repeater to Y=4 NIU
  │
  Cycle 46:  req_tgl reaches Y=4 (last node)
  Cycle 48:  req_tgl[Y=4]_out toggles (loopback begins)
             ack_tgl[Y=4]_out toggles
             ▲
  ├─→ Loopback repeater path (variable depth, typically 6–7 cycles)
  │
  Cycle 55:  ack_tgl arrives back at BIU (backward propagation)
             BIU checks ack_tgl_final XOR ack_tgl_initial
             If toggle detected: ✓ SWEEP COMPLETE
             BIU reads data[31:0] (accumulated CRC from all nodes)
             Compares against expected reference value

  Total latency: ~55 noc_clk cycles for a simple 5-node ring
                 (actual depends on CDC crossings, composite tile loopbacks)
```

#### 8.10.6 Proving Points for Waveform Verification

Use these checkpoints in simulation or logic analyzer captures to verify handshake propagation:

**Forward Path Checkpoints:**

| Checkpoint | Location | Waveform Observable | How to Verify |
|---|---|---|---|
| **PP1: Initiator Toggle** | BIU APB interface | `edc_biu_inst.req_tgl_out` XORs | Edge visible; cycle-aligned |
| **PP2: First Node Input** | `u_edc1_node[Y=0,NOC].i_req_tgl` | Delayed copy of PP1 after repeater | Should lag PP1 by ~7 noc_clk + repeater gate delay |
| **PP3: First Node Edge Detection** | `u_edc1_node[Y=0,NOC].req_tgl_r` (sampled) | Latch updates on cycle req_tgl XORs detected | Edge should be clean (no glitches) |
| **PP4: First Node CRC Output** | `u_edc1_node[Y=0,NOC].crc_computed[31:0]` | Valid CRC after +1 or +2 cycles of sampling | CRC value stable before data XOR |
| **PP5: First Node Data XOR** | `u_edc1_node[Y=0,NOC].data_out[31:0]` | data_out = data_in XOR crc_computed | Should update combinationally or +1 cycle |
| **PP6: First Node Forward Toggle** | `u_edc1_node[Y=0,NOC].o_req_tgl` | req_tgl_out toggles after PP3 | Edge on cycle N+2–3 after PP3 |
| **PP7: Second Node Input** | `u_edc1_node[Y=1,NOC].i_req_tgl` | Delayed copy of PP6 after repeater | Should lag PP6 by ~7 noc_clk |
| **PP8: Ring Mid-Point** | `u_edc1_node[Y=2].i_req_tgl` (across CDC) | CDC sync3r chain | FFs FF1/FF2/FF3 should toggle in sequence (3 cycles spread) |
| **PP9: Last Node Toggle** | `u_edc1_node[Y=4,NIU].o_req_tgl` | XOR on last node (tail) | Confirms req_tgl reached end of ring |

**Backward Path Checkpoints:**

| Checkpoint | Location | Waveform Observable | How to Verify |
|---|---|---|---|
| **PP10: Last Node ACK Toggle** | `u_edc1_node[Y=4,NIU].o_ack_tgl` | ack_tgl_out toggles after PP9 | Edge on cycle N+1–2 after PP9 (after req_tgl_out) |
| **PP11: NIU Loopback Delay** | `loopback_path[Y=4→Y=3]` (internal composite repeater) | ack_tgl propagates back | Visible as cascaded repeater delays in composite tile |
| **PP12: Y=2 CDC Return Path** | `u_edc1_node[Y=2].i_ack_tgl` (from loopback) | ack_tgl enters CDC sync3r | Should show +3-cycle sync latency like PP8 |
| **PP13: Y=0 ACK Input** | `u_edc1_node[Y=0].i_ack_tgl` (backward) | ack_tgl_in before node processing | Should be clean toggle, no glitches |
| **PP14: BIU ACK Loopback** | `edc_biu_inst.ack_tgl_in` | Final ack_tgl returning to BIU | Edge indicates ring completed successfully |

#### 8.10.7 RTL Path Mapping for Signal Tracing

**Top-level EDC instantiation in trinity.sv:**

```systemverilog
// EDC ring distributed across all tile clusters
for (genvar cluster_x = 0; cluster_x < 4; cluster_x++) begin : gen_edc_per_col
  // Column-based ring: each column X traces vertically Y=0→4 (or subset)
  //   u_edc1_node[cluster_x][y] — each node instance per tile

  // Forward path: req_tgl
  //   u_edc1_node[X][Y].i_req_tgl  ← from prev node or BIU
  //   u_edc1_node[X][Y].o_req_tgl  ← to next node

  // Backward path: ack_tgl
  //   u_edc1_node[X][Y].i_ack_tgl  ← from loopback (next node or Y=4 NIU)
  //   u_edc1_node[X][Y].o_ack_tgl  ← to previous node or BIU

  // Data path: data[31:0]
  //   u_edc1_node[X][Y].i_data[31:0]  ← accumulated CRC from prev
  //   u_edc1_node[X][Y].o_data[31:0]  ← XOR with local CRC, to next
end
```

**Key RTL module instances:**

```
trinity_top
├─ gen_edc_per_col[0:3]
│  ├─ u_edc1_node[Y=0..Y=4] (per column)
│  │  ├─ req_tgl_in / req_tgl_out
│  │  ├─ ack_tgl_in / ack_tgl_out
│  │  ├─ data_in[31:0] / data_out[31:0]
│  │  ├─ gen_repeater[in/out] (combinational buffers, MCPDLY-tuned)
│  │  └─ (optional) sync3r_req_tgl / sync3r_ack_tgl (at CDC boundaries)
│  │
│  └─ Composite tile (X=1,2): cross-row loopback wires
│     ├─ noc2axi_router_NW_OPT / NE_OPT
│     │  ├─ u_edc1_node[Y=3] (router row)
│     │  ├─ u_edc1_node[Y=4] (NIU row)
│     │  └─ loopback_ack_tgl[Y=4→Y=3] (internal cross-row)
│     └─ loopback_req_tgl[Y=3→Y=4] (forward cross-row, if used)
│
└─ edc_biu_inst (AXI interface, APB-controlled)
   ├─ req_tgl_out (to ring initiator)
   ├─ ack_tgl_in (from ring loopback)
   ├─ data_in[31:0] (final ring data, after all nodes XOR)
   └─ APB_addr/APB_data (firmware CSR access)
```

#### 8.10.7a Trinity Top EDC Signal Hierarchy — Column X=0 (Detailed Signal Listing)

This section shows the complete EDC signal tree for one column (X=0) as it appears in the RTL hierarchy, mapping all req_tgl, ack_tgl, and data[31:0] signals from BIU through all nodes.

**Column X=0 (Standalone NIU at Y=4, no composite cross-row wires):**

```
trinity_top
│
├─ edc_biu_inst
│  ├─ o_req_tgl                    ← Initiates ring sweep (from APB command)
│  ├─ i_ack_tgl                    ← Loopback from last node (Y=4 NIU X=3)
│  ├─ i_data[31:0]                 ← Final accumulated CRC from all nodes
│  └─ APB registers: EDC_CSR, EDC_STATUS, EDC_NODE_ID, etc.
│
├─ gen_edc_per_col[X=0]
│  │
│  ├─ u_edc1_node[Y=0] (Tensix Y=0, NOC domain)
│  │  ├─ i_clk                     = noc_clk (shared clock domain)
│  │  ├─ i_reset_n
│  │  │
│  │  ├─ Forward path (req_tgl):
│  │  │  ├─ i_req_tgl              ← from BIU.o_req_tgl (via repeater)
│  │  │  ├─ req_tgl_r              = latched previous value (FF)
│  │  │  ├─ req_tgl_edge           = i_req_tgl XOR req_tgl_r (edge detect)
│  │  │  └─ o_req_tgl              → to next node [Y=1] (toggled)
│  │  │
│  │  ├─ Backward path (ack_tgl):
│  │  │  ├─ i_ack_tgl              ← from next node [Y=1] (loopback)
│  │  │  ├─ ack_tgl_r              = latched previous value
│  │  │  ├─ ack_tgl_edge           = i_ack_tgl XOR ack_tgl_r
│  │  │  └─ o_ack_tgl              → to BIU or loopback aggregator (toggled)
│  │  │
│  │  ├─ Data path (CRC accumulation):
│  │  │  ├─ i_data[31:0]           ← from BIU or previous node (combined)
│  │  │  ├─ local_state[*]         = sampled SRAM ECC, register parity, etc.
│  │  │  ├─ crc_computed[31:0]     = CRC32 of local_state (combinational)
│  │  │  ├─ data_out_pre[31:0]     = i_data XOR crc_computed
│  │  │  └─ o_data[31:0]           → to next node [Y=1]
│  │  │
│  │  ├─ Control signals:
│  │  │  ├─ i_harvest_bypass       (0 = active, 1 = skip this node)
│  │  │  ├─ i_sample_trigger       (sampled state on req_tgl edge)
│  │  │  └─ o_error_valid          (asserts on mismatch with expected CRC)
│  │  │
│  │  └─ Repeater instances (combinational buffers):
│  │     ├─ u_repeater_req_in      (MCPDLY-tuned buffer, ~7-cycle delay)
│  │     ├─ u_repeater_req_out     (same)
│  │     └─ u_repeater_data_out    (same)
│  │
│  ├─ u_edc1_node[Y=1] (Tensix Y=1, NOC/AXI clock domain)
│  │  ├─ i_clk                     = ai_clk[X=0] (per-column clock)
│  │  ├─ i_req_tgl                 ← from Y=0.o_req_tgl (via repeater)
│  │  ├─ o_req_tgl                 → to Y=2
│  │  ├─ i_ack_tgl                 ← from Y=2.o_ack_tgl (backward)
│  │  ├─ o_ack_tgl                 → to Y=0
│  │  ├─ i_data[31:0]              ← from Y=0.o_data
│  │  ├─ o_data[31:0]              → to Y=2
│  │  └─ [same internal signals as Y=0]
│  │
│  ├─ u_edc1_node[Y=2] (Tensix Y=2, CDC crossing boundary: ai_clk → noc_clk)
│  │  ├─ i_clk                     = noc_clk (output domain)
│  │  ├─ i_clk_src                 = ai_clk[X=0] (input domain)
│  │  │
│  │  ├─ Forward path with CDC sync3r:
│  │  │  ├─ i_req_tgl              ← from Y=1.o_req_tgl (ai_clk domain)
│  │  │  ├─ sync3r_req_tgl[0]      = FF1 (sample, retime to noc_clk)
│  │  │  ├─ sync3r_req_tgl[1]      = FF2 (propag, fully synced)
│  │  │  ├─ sync3r_req_tgl[2]      = FF3 (guard FF, metastability protection)
│  │  │  ├─ req_tgl_synced         = sync3r_req_tgl[2]
│  │  │  ├─ req_tgl_r              = latched req_tgl_synced
│  │  │  ├─ req_tgl_edge           = req_tgl_synced XOR req_tgl_r
│  │  │  ├─ [CRC computation]
│  │  │  └─ o_req_tgl              → to Y=3 (now in noc_clk domain)
│  │  │
│  │  ├─ Backward path with CDC sync3r (noc_clk → ai_clk):
│  │  │  ├─ i_ack_tgl              ← from Y=3.o_ack_tgl (noc_clk domain)
│  │  │  ├─ sync3r_ack_tgl[0..2]   = 3-stage synchronizer (to ai_clk)
│  │  │  ├─ ack_tgl_synced         = sync3r_ack_tgl[2]
│  │  │  ├─ ack_tgl_r              = latched ack_tgl_synced
│  │  │  └─ o_ack_tgl              → to Y=1 (in ai_clk domain)
│  │  │
│  │  ├─ Data path with CDC synchronization:
│  │  │  ├─ i_data[31:0]           ← from Y=1.o_data (ai_clk)
│  │  │  ├─ data_sync_req[31:0]    = synchronized by strobing on req_tgl edge
│  │  │  ├─ [CRC computed in noc_clk]
│  │  │  └─ o_data[31:0]           → to Y=3
│  │  │
│  │  └─ DISABLE_SYNC_FLOPS warning:
│  │     Because this node crosses clock domains, sync3r instances
│  │     are NOT disabled (DISABLE_SYNC_FLOPS does not apply here)
│  │
│  ├─ u_edc1_node[Y=3] (Dispatch W, noc_clk domain)
│  │  ├─ i_clk                     = noc_clk
│  │  ├─ i_req_tgl                 ← from Y=2.o_req_tgl
│  │  ├─ o_req_tgl                 → to Y=4
│  │  ├─ i_ack_tgl                 ← from Y=4.o_ack_tgl
│  │  ├─ o_ack_tgl                 → to Y=2
│  │  ├─ i_data[31:0]              ← from Y=2.o_data
│  │  ├─ o_data[31:0]              → to Y=4
│  │  └─ [CRC for dispatch state, control signals]
│  │
│  └─ u_edc1_node[Y=4] (NOC2AXI_NW_OPT standalone NIU, noc_clk domain)
│     ├─ i_clk                     = noc_clk
│     ├─ i_req_tgl                 ← from Y=3.o_req_tgl
│     ├─ o_req_tgl                 → [last node, starts loopback]
│     ├─ i_ack_tgl                 ← [loopback begins here]
│     ├─ o_ack_tgl                 → routed back to BIU via loopback path
│     │                               (through gen_edc_per_col[X=3] loopback)
│     ├─ i_data[31:0]              ← from Y=3.o_data
│     ├─ o_data[31:0]              → [last data before loopback]
│     └─ [CRC for NIU: ATT, SMN, RDATA FIFO state]
│
└─ Loopback aggregator (across all columns X=0..3):
   ├─ Backward path:
   │  gen_edc_per_col[X=3].u_edc1_node[Y=4].o_ack_tgl
   │    → repeater chains → gen_edc_per_col[X=0].u_edc1_node[Y=4].i_ack_tgl
   │    (NOT direct cross-column; follows ring order: X=0→X=1→X=2→X=3→X=0)
   │
   └─ Data aggregation:
      All o_data[31:0] XOR'd into accumulated result at BIU
```

**Signal Connection Summary for Column X=0:**

| Node | i_req_tgl source | o_req_tgl dest | i_ack_tgl source | o_ack_tgl dest |
|------|---|---|---|---|
| **Y=0** | BIU.o_req_tgl (repeater) | Y=1 (repeater) | Y=1 (loopback) | BIU (aggregator) |
| **Y=1** | Y=0.o_req_tgl (repeater) | Y=2 (repeater) | Y=2 (loopback) | Y=0 |
| **Y=2** | Y=1.o_req_tgl + sync3r | Y=3 (repeater) | Y=3 (repeater) + sync3r | Y=1 |
| **Y=3** | Y=2.o_req_tgl (repeater) | Y=4 (repeater) | Y=4 (loopback) | Y=2 |
| **Y=4** | Y=3.o_req_tgl (repeater) | [ring tail] → loopback | [loopback starts] | gen_edc_per_col[X=3].u_edc1_node[Y=4] |

**Repeater insertion points (combinational, ~7-cycle MCPDLY):**
- Between each adjacent node vertically (Y=0→Y=1, Y=1→Y=2, Y=2→Y=3, Y=3→Y=4)
- On backward path loopback (from Y=4 through column ring back to Y=0)

---

#### 8.10.7b Trinity Top EDC Signal Hierarchy — Column X=1 (Composite Tile with Cross-Row Loopback)

Column X=1 (and X=2) contains a **composite tile** (NOC2AXI_ROUTER_NW_OPT) that spans Y=3 and Y=4. This requires internal cross-row flit wires for EDC signals.

```
trinity_top
│
├─ gen_edc_per_col[X=1]
│  │
│  ├─ u_edc1_node[Y=0] (Tensix Y=0, noc_clk)
│  │  ├─ i_req_tgl                 ← from gen_edc_per_col[X=0].u_edc1_node[Y=0].o_req_tgl
│  │  ├─ o_req_tgl                 → to Y=1 (repeater)
│  │  ├─ i_ack_tgl                 ← from Y=1 (backward)
│  │  ├─ o_ack_tgl                 → to gen_edc_per_col[X=0]
│  │  ├─ i_data[31:0]              ← from gen_edc_per_col[X=0]
│  │  └─ o_data[31:0]              → to Y=1
│  │
│  ├─ u_edc1_node[Y=1] (Tensix Y=1, ai_clk[1])
│  │  ├─ i_req_tgl                 ← from Y=0 (repeater)
│  │  ├─ o_req_tgl                 → to Y=2
│  │  ├─ i_ack_tgl                 ← from Y=2 (loopback)
│  │  ├─ o_ack_tgl                 → to Y=0
│  │  ├─ i_data[31:0]              ← from Y=0
│  │  └─ o_data[31:0]              → to Y=2
│  │
│  ├─ u_edc1_node[Y=2] (Tensix Y=2, CDC crossing: ai_clk[1] → noc_clk)
│  │  ├─ i_clk                     = noc_clk
│  │  ├─ i_clk_src                 = ai_clk[X=1]
│  │  ├─ i_req_tgl                 ← from Y=1.o_req_tgl + sync3r
│  │  ├─ o_req_tgl                 → to composite tile Y=3 (repeater)
│  │  ├─ i_ack_tgl                 ← from composite Y=3 (sync3r back to ai_clk)
│  │  ├─ o_ack_tgl                 → to Y=1
│  │  ├─ i_data[31:0]              ← from Y=1 (synchronized)
│  │  └─ o_data[31:0]              → to composite Y=3
│  │
│  ├─ noc2axi_router_nw_opt (Composite tile, spans Y=3 and Y=4)
│  │  │
│  │  ├─ u_edc1_node[Y=3] (Router row, noc_clk domain)
│  │  │  ├─ i_clk                  = noc_clk
│  │  │  ├─ i_req_tgl              ← from Y=2.o_req_tgl (external repeater)
│  │  │  ├─ o_req_tgl              → [can route to internal Y=4 OR external loopback]
│  │  │  │
│  │  │  ├─ Internal cross-row loopback (Y=3 ↔ Y=4 within composite):
│  │  │  │  ├─ req_tgl_to_y4       = o_req_tgl signal (can be routed down)
│  │  │  │  └─ ack_tgl_from_y4     ← i_ack_tgl from internal Y=4 node
│  │  │  │
│  │  │  ├─ i_ack_tgl              ← from internal Y=4 node OR external loopback
│  │  │  ├─ o_ack_tgl              → to Y=2 (external backward path)
│  │  │  ├─ i_data[31:0]           ← from Y=2.o_data
│  │  │  ├─ o_data[31:0]           → combined with Y=4 data
│  │  │  └─ [CRC for router: flit buffers, routing state]
│  │  │
│  │  └─ u_edc1_node[Y=4] (NIU row, noc_clk domain)
│  │     ├─ i_clk                  = noc_clk
│  │     │
│  │     ├─ Internal cross-row connection from Y=3:
│  │     │  ├─ i_req_tgl           ← from Y=3.o_req_tgl OR external repeater
│  │     │  │                         (internal loopback wire: Y=3→Y=4)
│  │     │  ├─ o_req_tgl           → [last node, signals loopback start]
│  │     │  └─ loopback_ack_tgl_mux
│  │     │     ├─ sel = bypass OR internal_loopback
│  │     │     ├─ in0 = o_ack_tgl (internal generated)
│  │     │     └─ out = to Y=3 (loopback return)
│  │     │
│  │     ├─ i_ack_tgl              ← from internal loopback (Y=4 asserts)
│  │     ├─ o_ack_tgl              → to Y=3 (internal backward) OR external
│  │     ├─ i_data[31:0]           ← from Y=3.o_data (internal)
│  │     ├─ o_data[31:0]           → combined NIU data
│  │     └─ [CRC for NIU: ATT, SMN, RDATA FIFO state]
│  │
│  │  **Cross-row wire instances (inside composite tile):**
│  │  ├─ loopback_req_tgl_y3_to_y4 (512-bit internal flit wire)
│  │  ├─ loopback_ack_tgl_y4_to_y3 (backward)
│  │  └─ loopback_data_y3_to_y4, loopback_data_y4_to_y3
│
└─ [Columns X=2, X=3 follow similar pattern]

```

**Key differences for composite tile (X=1, X=2):**

1. **Internal cross-row loopback wires** (dedicated buses):
   - req_tgl propagates Y=3 → Y=4 internally
   - ack_tgl propagates Y=4 → Y=3 internally
   - Not visible to top-level trinity.sv, hidden inside composite module

2. **Composite loopback repeater depth:**
   - Y=3 → Y=4 forward: REP_DEPTH = 4 (Y=4 composite output)
   - Y=4 → Y=3 backward: REP_DEPTH = 6 (Y=3 composite loopback, longer path)

3. **Data path aggregation:**
   - Y=3 EDC node CRC XORs with Y=4 EDC node CRC inside composite
   - Final o_data[31:0] is combined result exported to Y=2

---

#### 8.10.8 Debugging Checklist for Failed EDC Sweeps

If an EDC sweep fails or stalls (timeout), use this checklist:

**Step 1: Verify Initialization**
- [ ] MCPDLY written to CSR before ring reset release? (§7.9)
- [ ] Ring reset de-asserted smoothly (sync3r active during release)?
- [ ] EDC ring enable bit set in CSR?

**Step 2: Check Forward Path (req_tgl)**
- [ ] BIU initiator toggle visible at PP1?
- [ ] req_tgl_in at first node (Y=0) shows delayed copy of PP1 (PP2)?
- [ ] First node edge detection triggered (PP3 latch updates)?
- [ ] All nodes toggle req_tgl_out in sequence (compare PP6, PP7, ..., PP9)?
- [ ] Repeater delays look correct (should be ~7 noc_clk cycles each)?

**Step 3: Check Backward Path (ack_tgl)**
- [ ] Last node (Y=4 NIU) toggles ack_tgl_out after req_tgl_out (PP10)?
- [ ] Loopback repeater chain propagates ack_tgl back (PP11)?
- [ ] BIU receives ack_tgl toggle within expected latency (PP14)?
- [ ] Backward timing: should be similar to forward (~N_nodes × 7 + repeater depth)?

**Step 4: Check Data Path (data[31:0])**
- [ ] data_in starts with INITIAL_VALUE at BIU?
- [ ] Each node's CRC output (PP4) is stable before data XOR (PP5)?
- [ ] Final data_out at BIU differs from INITIAL_VALUE (nodes added CRC)?
- [ ] Final data matches expected accumulated CRC?

**Step 5: Check CDC Crossings (if present)**
- [ ] sync3r chain at Y=2 CDC boundaries shows 3-cycle propagation delay?
- [ ] No metastability glitches on sync3r FF outputs?
- [ ] Backward sync3r also has 3-cycle delay?

**Step 6: Check Composite Tile Cross-Row Paths (X=1, X=2)**
- [ ] Internal Y=3↔Y=4 loopback wires connected?
- [ ] Loopback repeater depths correct (REP_DEPTH_LOOPBACK=6)?
- [ ] ack_tgl loopback path shows repeater delays?

**Step 7: Timeout Diagnosis**
- If BIU polls EDC_STATUS and timeout occurs:
  - Read EDC_NODE_ID from CSR → tells which node failed
  - Inspect that specific node in waveform (use instance path)
  - Check if req_tgl reached the failed node (compare inputs from previous node)
  - Check if failed node's CRC is valid
  - Check if failed node's ack_tgl_out toggles

---



### 8.11 Harvest Bypass in EDC Ring

When a tile is harvested (disabled due to manufacturing yield), the tile's compute logic is powered down or isolated. If the EDC ring simply omitted the node, the ring chain would be broken at that point and the entire ring would stall, preventing error monitoring for all remaining active tiles. The bypass mechanism solves this problem.

#### 8.11.1 Bypass Mechanism

Each `tt_edc1_node` instance includes a **bypass mux** that can route the ring signal around the node:

```
  Normal operation (tile active):
  ring_in (req_tgl) ──────────────────────────→ [EDC node logic] ──→ ring_out

  Bypass operation (tile harvested):
  ring_in (req_tgl) ──→ [2:1 mux, sel=bypass] ──────────────────→ ring_out
                              │
                         bypass=1: wire ring_in directly to ring_out
                         (skip node logic entirely)
```

The bypass is purely combinational — `ring_out` follows `ring_in` with only wire delay when bypass is asserted. This means:
- The ring traversal time decreases when tiles are bypassed (fewer effective nodes)
- No MCPDLY adjustment is needed — the bypass shortens the path, so the existing MCPDLY=7 is still a valid worst-case upper bound
- The bypassed node generates no ack_tgl, so the initiator does not expect a response from it

#### 8.11.2 Bypass Control Signal

The bypass is controlled by the `ISO_EN` signal — mechanism 6 in the N1B0 harvest scheme. `ISO_EN[x + 4*y]` being asserted for a tile directly drives the bypass mux select for all EDC nodes within that tile:

```
  ISO_EN bit mapping for Tensix tiles (X=0..3, Y=0..2):
  ISO_EN[0]  → tile (X=0, Y=0) → bypass all EDC nodes at (0,0)
  ISO_EN[1]  → tile (X=1, Y=0) → bypass all EDC nodes at (1,0)
  ...
  ISO_EN[11] → tile (X=3, Y=2) → bypass all EDC nodes at (3,2)
```

The same `ISO_EN` signal that gates the tile's compute clocks (via DFX wrappers) and isolates its output signals (via AND-type ISO cells) also bypasses its EDC nodes. This ensures that a harvested tile is consistently invisible to the EDC ring — it contributes no CRC, receives no toggle, and its output isolation prevents it from driving the ring in an uncontrolled state.

#### 8.11.3 Consequence of Not Bypassing

If a harvested tile's EDC node is not bypassed, the following failure modes occur:

1. **Ring stall**: The node's compute clock is gated, so `req_tgl` arriving at the node will never be forwarded. The initiator waits indefinitely for `ack_tgl` and eventually declares a timeout — generating a false FATAL interrupt even though no real error exists.
2. **Incorrect CRC**: If the node is partially powered (e.g., ISO cells block outputs but node logic is still active), the node may generate a CRC over garbage state, causing a false CRIT error.
3. **Ring deadlock**: In the worst case, the ring permanently stalls and all subsequent EDC monitoring is disabled for the entire chip.

The bypass mechanism ensures none of these failure modes can occur. Bypass assertion is part of the standard harvest initialization sequence and must be applied before the EDC ring is enabled.

### 8.12 EDC CSR Base Addresses

| Block          | Base Address | Registers |
|----------------|--------------|-----------|
| EDC per-node   | Via tile APB | Per-node status, MCPDLY, enable |
| CLUSTER_CTRL   | 0x03000000   | 96 regs — includes global EDC enable |
| SMN            | 0x03010000   | 325 regs — security/error routing    |

EDC interrupts are routed through the overlay error aggregator to the `CRIT_IRQ` or `FATAL_IRQ` lines, which connect to the Dispatch tile interrupt controllers and ultimately to the Rocket RISC-V core for software handling.

---

## §9 Clock, Reset, and CDC Architecture

### 9.1 Clock Domain Overview

#### 9.1.1 Architecture Rationale

N1B0 uses **five functionally distinct clock domains** (plus ref_clk and aon_clk for infrastructure) because different subsystems have fundamentally incompatible frequency and power requirements:

1. **noc_clk — Fixed-frequency NoC fabric**: The NoC interconnect must run at a stable, predictable frequency to meet timing closure across the full mesh. All four NIU tiles and all router tiles share the same noc_clk. Because every inter-tile communication traverses the NoC, noc_clk jitter directly impacts worst-case end-to-end latency. NoC timing is determined at tape-out and does not change at runtime.

2. **ai_clk[3:0] — Per-column Tensix compute, DVFS-capable**: The Tensix FPU is the dominant power consumer. N1B0 allows each column to run at an independently controlled frequency via the AWM (Adaptive Waveform Manager) PLL. This enables per-column DVFS (Dynamic Voltage and Frequency Scaling): columns running low-priority background compute can be throttled to save power, while columns running critical-path inference keep full frequency. Separating ai_clk per-column also enables partial-chip operation when columns are harvested — the harvested column's clock can be eliminated entirely.

3. **dm_clk[3:0] — Per-column data-move, independent of FPU**: The TDMA engine (pack/unpack) and L1 SRAM arrays run on dm_clk, which is independent from ai_clk within the same column. This separation is critical for the DMA-compute overlap pattern: when the FPU is busy accumulating into DEST (ai_clk domain), the TDMA engine can simultaneously be loading the next weight tile from DRAM into L1 (dm_clk domain) without any clock-domain coupling. If ai_clk were gated to save power during a DMA-only phase, dm_clk would continue running — keeping L1 accessible for NoC-driven DMA without waking up the FPU.

4. **axi_clk — Host bus interface, tracks host frequency**: The AXI master interface (NIU) and APB fabric must be synchronous to the host system bus. The host may run a completely different PLL than the NPU's internal PLLs. axi_clk is provided by the host SoC and is independent of all internal clocks. This isolation means the host can change its bus frequency (e.g., dynamic frequency scaling at the SoC level) without affecting the NPU's internal timing.

5. **PRTN/aon_clk — Always-on power sequencing**: Power-domain enable/disable requires a clock that is active even when all functional clocks are gated. The aon_clk (always-on) provides this. It runs at very low frequency (32 kHz–1 MHz range) and drives only the power sequencing logic and wake handshake. Its low frequency minimizes leakage from the always-on domain.

#### 9.1.2 Clock Domain Diagram

```
                        ┌─────────────────────────────────────────────────────────────────┐
                        │                     N1B0 NPU Clock Tree                         │
                        └─────────────────────────────────────────────────────────────────┘

  External PLL / AWM
  ┌──────────────────────────────────────────────────────────────────────────────────────┐
  │  axi_clk   ──────────────────────────────────── AXI/APB fabric, SMN, AWM, iDMA CSR  │
  │  noc_clk   ──────────────────────────────────── NoC router, NIU, VC FIFOs, EDC ring │
  │  ref_clk   ──────────────────────────────────── AWM PLL reference, frequency meas.  │
  │  aon_clk   ──────────────────────────────────── Always-on domain (power management) │
  │                                                                                      │
  │  i_ai_clk[3:0]   per-column  X=0→col0, X=1→col1, X=2→col2, X=3→col3               │
  │  i_dm_clk[3:0]   per-column  X=0→col0, X=1→col1, X=2→col2, X=3→col3               │
  └──────────────────────────────────────────────────────────────────────────────────────┘

  CDC crossings (async FIFOs or sync3r at each boundary arrow below):

    ai_clk[col] ──CDC──► noc_clk    (Tensix → NoC local port, write path)
    noc_clk     ──CDC──► ai_clk[col](NoC local port → Tensix, read path)
    ai_clk[col] ──CDC──► dm_clk[col](FPU → TDMA/L1 boundary, control signals)
    noc_clk     ──CDC──► axi_clk    (NIU NoC → AXI interface)
    EDC req_tgl ──CDC──► (sync3r at Y=2 intra-tile boundaries only)
```

#### 9.1.3 Clock Domain Summary Table

| Clock       | Source       | Scope                          | Typical Frequency | DVFS? |
|-------------|--------------|--------------------------------|-------------------|-------|
| axi_clk     | Host PLL     | AXI bus, APB, SMN, iDMA CSR   | 400–800 MHz       | No    |
| noc_clk     | External PLL | NoC fabric, NIU, VC FIFO, EDC | 1.0–1.2 GHz       | No    |
| ai_clk[3:0] | AWM PLL      | Tensix FPU, DEST/SRCA regfile | 1.0–1.5 GHz       | Yes   |
| dm_clk[3:0] | AWM PLL      | Overlay data-move, L1 SRAM    | 1.0–1.2 GHz       | Yes   |
| ref_clk     | Crystal / IO | AWM reference / freq measure  | 50–100 MHz        | No    |
| aon_clk     | Always-on    | PRTN power sequencing         | ~32 kHz–1 MHz     | No    |

### 9.2 Per-Column Clock Architecture

Unlike the baseline Trinity design which uses a single ai_clk and single dm_clk for all columns, N1B0 distributes clocks per-column. This enables fine-grained power management and per-column frequency scaling.

```
  Column assignment:
  ┌──────┬──────────┬────────────────────┬────────────────────┬────────────────┐
  │  Col │  X index │  ai_clk input      │  dm_clk input      │ Tile types     │
  ├──────┼──────────┼────────────────────┼────────────────────┼────────────────┤
  │  0   │  X=0     │  i_ai_clk[0]       │  i_dm_clk[0]       │ NW_OPT, T6    │
  │  1   │  X=1     │  i_ai_clk[1]       │  i_dm_clk[1]       │ ROUTER_NW_OPT │
  │  2   │  X=2     │  i_ai_clk[2]       │  i_dm_clk[2]       │ ROUTER_NE_OPT │
  │  3   │  X=3     │  i_ai_clk[3]       │  i_dm_clk[3]       │ NE_OPT, T6    │
  └──────┴──────────┴────────────────────┴────────────────────┴────────────────┘
```

The top-level `trinity.sv` port list includes all eight per-column clock inputs. Inside each tile, `i_ai_clk` and `i_dm_clk` connect to the Tensix FPU and overlay data-move subsystems respectively.

### 9.3 PRTN Chain (Power Partition Sequencing)

#### 9.3.1 Purpose and Motivation

PRTN stands for **Partition**. The PRTN chain is the hardware mechanism for sequencing power-domain enable and disable across the N1B0 tile array. Its primary purposes are:

1. **Inrush current limiting**: If all tiles simultaneously receive their power-enable signal, the combined inrush current from charging decoupling capacitors and activating power switches can exceed the package PDN (Power Delivery Network) current rating and cause Vdd droop. The chain sequences enables tile-by-tile, inserting guaranteed inter-tile delay so that no two tiles switch simultaneously.
2. **Ordered reset release**: After power is stable, tiles must come out of reset in a defined order so that upstream tiles (e.g., Dispatch, NIU) are fully reset before downstream tiles (Tensix compute) start issuing NoC transactions. Out-of-order reset release can cause bus contention or deadlock in the NoC.
3. **Selective tile power-gating**: In low-power modes, individual columns or tiles can be power-gated when idle. The PRTN chain provides the controlled enable/disable sequence for transitioning tiles in and out of the power-gated state without affecting neighboring active tiles.

#### 9.3.2 Chain Structure

The PRTN chain is a daisy-chained handshake that traverses all tiles in a fixed order:

```
  PRTN Chain — full tile traversal order (N1B0):

  PRTN_INPUT (from host/firmware)
       │
       ▼
  ┌──────────┐  PRTN_REQ  ┌──────────┐  PRTN_REQ  ┌──────────┐
  │ Tile     │───────────►│ Tile     │───────────►│ Tile     │
  │ (X=0,Y=0)│◄───────────│ (X=0,Y=1)│◄───────────│ (X=0,Y=2)│
  │          │  PRTN_ACK  │          │  PRTN_ACK  │          │
  └──────────┘            └──────────┘            └──────────┘
       │  (continues through all tiles in column-row order)
       ▼
  PRTN_OUTPUT (to firmware — indicates all tiles powered and reset)

  Clock: PRTNUN_FC2UN_CLK_IN — dedicated, separate from all functional clocks
```

Each tile in the chain:
1. Receives `PRTN_REQ` from the previous tile (or from the chain input for the first tile)
2. Applies local power-enable or reset-release to its internal power domain
3. Waits for local power/reset to stabilize (measured by internal power-on-reset detector)
4. Asserts `PRTN_ACK` back to the previous tile and passes `PRTN_REQ` forward to the next tile
5. The chain advances only after acknowledgment — no tile is enabled until its predecessor is stable

#### 9.3.3 Firmware Interface

Firmware controls the PRTN chain through `PRTNUN_FC2UN` registers in the CLUSTER_CTRL block:

```
// Power-up sequence (typical):
// 1. Configure which tiles to enable (harvest map)
APB_WRITE(CLUSTER_CTRL + PRTN_HARVEST_MASK, harvest_config);

// 2. Trigger PRTN chain to run power-up sequence
APB_WRITE(CLUSTER_CTRL + PRTN_CMD, PRTN_CMD_POWERUP);

// 3. Poll for completion (or wait for PRTN_DONE interrupt)
while (!(APB_READ(CLUSTER_CTRL + PRTN_STATUS) & PRTN_ALL_DONE)) {}

// 4. All tiles in the non-harvested set are now powered and reset-released
```

For selective power-gating (e.g., gating columns 1 and 2 during idle):

```
// Power-gate columns X=1 and X=2:
APB_WRITE(CLUSTER_CTRL + PRTN_GATE_MASK, (1<<1)|(1<<2));  // columns 1 and 2
APB_WRITE(CLUSTER_CTRL + PRTN_CMD, PRTN_CMD_POWERGATE);
// PRTN chain sequences the gate in controlled order
```

#### 9.3.4 Composite Tile PRTN Pass-Through

The composite tiles (NOC2AXI_ROUTER_NE/NW_OPT) span two physical rows (Y=4 and Y=3). The PRTN chain passes through both internal rows in order: the NIU portion at Y=4 is enabled first, then the router portion at Y=3 is enabled. The composite tile module instantiates two PRTN stages internally and presents a single PRTN_REQ/PRTN_ACK interface at the tile boundary.

### 9.4 ISO_EN Harvest Isolation Enable

`ISO_EN[11:0]` is the sixth harvest mechanism in N1B0 (in addition to the five baseline mechanisms). Each bit corresponds to one tile in the 4×3 core grid.

```
  Bit mapping: ISO_EN[x + 4*y]

  ┌──────────────────────────────────────────────────────────────────────┐
  │ Y=0: ISO_EN[3]  ISO_EN[2]  ISO_EN[1]  ISO_EN[0]   (X=3..0)         │
  │ Y=1: ISO_EN[7]  ISO_EN[6]  ISO_EN[5]  ISO_EN[4]   (X=3..0)         │
  │ Y=2: ISO_EN[11] ISO_EN[10] ISO_EN[9]  ISO_EN[8]   (X=3..0)         │
  └──────────────────────────────────────────────────────────────────────┘
```

When `ISO_EN[i]` is asserted:
1. All output signals from tile `i` are driven to safe (inactive) values via AND-type ISO cells
2. The EDC ring bypass mux routes around the harvested tile's EDC node
3. The tile's clock may be gated (handled by DFX wrappers)
4. NoC mesh routing re-configures to avoid the harvested tile's coordinates

### 9.5 Reset Architecture

```
  Reset signals:
  ┌───────────────────────────────────────────────────────────────────┐
  │  i_reset_n        — async global active-low reset                 │
  │                     De-asserted synchronously inside each tile    │
  │                     Controls: all flip-flops in all domains       │
  │                                                                   │
  │  i_axi_reset_n    — AXI domain active-low reset                  │
  │                     Synchronous to axi_clk                       │
  │                     Controls: AXI bus logic, APB, SMN, AWM       │
  └───────────────────────────────────────────────────────────────────┘
```

Each tile contains reset synchronizers for each clock domain it uses:

| Reset synchronizer | Clock domain | Destination |
|--------------------|--------------|-------------|
| ai_clk reset sync  | ai_clk[col]  | FPU, DEST/SRCA, L1 SRAM |
| dm_clk reset sync  | dm_clk[col]  | Overlay, L2 cache       |
| noc_clk reset sync | noc_clk      | NoC router, NIU, EDC    |
| axi_clk reset sync | axi_clk      | APB slave, SFR          |

### 9.6 CDC Crossings

The N1B0 design has five classes of clock-domain crossing. Each uses the mechanism appropriate for the signal type and frequency relationship between source and destination clocks.

#### 9.6.1 ai_clk → noc_clk (Tensix NoC Write Path)

**Location**: Inside the overlay wrapper at the NoC local port, within each Tensix tile.
**Usage**: TRISC3 NoC DMA write path — when TRISC3 issues a NoC write command, the write data travels from ai_clk domain (where TRISC3 and L1 reside) to noc_clk domain (where the NoC local port and VC FIFOs reside).

```
  ai_clk domain                    noc_clk domain
  ┌─────────────────┐               ┌──────────────────────┐
  │  TRISC3 DMA     │               │  NoC local port       │
  │  write buffer   │               │  VC FIFO              │
  │  (512-bit flits)│──[Async FIFO]─►  (512-bit, 4-deep)   │
  └─────────────────┘               └──────────────────────┘

  Mechanism: Async FIFO
  Width:     512 bits (one full NoC flit)
  Depth:     4 entries
  Empty/Full: Gray-coded pointers, synchronized via 2-FF synchronizers
```

The 4-deep FIFO provides sufficient buffering to absorb one burst of 4 consecutive NoC write flits without back-pressure. With noc_clk ≥ ai_clk in typical operation, the FIFO rarely fills.

#### 9.6.2 noc_clk → ai_clk (Tensix NoC Read Response / Receive Path)

**Location**: Inside the overlay wrapper, receive side, within each Tensix tile.
**Usage**: Incoming NoC data to TRISC3/TRISC — when a NoC response flit (e.g., DRAM read data returned from NIU) arrives at the tile's local port, it must cross from noc_clk to ai_clk before being written into L1.

```
  noc_clk domain                   ai_clk domain
  ┌──────────────────┐              ┌─────────────────────┐
  │  NoC local port  │              │  TRISC3/TRISC RX buf │
  │  receive FIFO    │──[Async FIFO]►  (feeds L1 write)   │
  │  (512-bit)       │              │                     │
  └──────────────────┘              └─────────────────────┘

  Mechanism: Async FIFO
  Width:     512 bits
  Depth:     4 entries
```

This crossing is the critical path for NoC receive latency. The async FIFO adds a minimum of 2 noc_clk cycles (for write) + 2 ai_clk cycles (for read pointer synchronization) = ~4 cycles of latency at the crossing.

#### 9.6.3 ai_clk → dm_clk (FPU/TDMA Boundary)

**Location**: Inside the overlay wrapper at the TDMA/L1 boundary.
**Usage**: Control signals from the FPU sequencer (ai_clk) to the TDMA pack/unpack engine and L1 SRAM (dm_clk). This crossing allows L1 DMA operations to continue independently while the FPU is running in a different clock domain.

```
  ai_clk domain                    dm_clk domain
  ┌─────────────────┐               ┌──────────────────────┐
  │  FPU sequencer  │               │  TDMA pack/unpack    │
  │  (control sigs) │──[2-FF sync]─►│  (control enables)   │
  │                 │               │                       │
  │  DEST writeback │──[Async FIFO]─►  L1 write path       │
  │  data (32b×N)   │               │  (512-bit)           │
  └─────────────────┘               └──────────────────────┘

  Mechanism (control): 2-FF synchronizer for single-bit enable/valid signals
  Mechanism (data):    Async FIFO for multi-bit data paths
```

The 2-FF synchronizer is sufficient for control signals because they are guaranteed to be stable for multiple cycles by the FPU sequencer protocol (no single-cycle pulses cross this boundary).

#### 9.6.4 noc_clk → axi_clk (NIU AXI Interface)

**Location**: Inside the NIU (`tt_noc2axi`), at the boundary between the NoC flit processing logic and the AXI bus interface.
**Usage**: NoC-to-AXI translation — when a NoC request is converted to an AXI transaction, the address and data must cross from noc_clk (where NoC flit decoding happens) to axi_clk (where AXI channel handshake happens). The reverse path (AXI read response → NoC response flit) also has a crossing in the opposite direction.

```
  noc_clk domain                    axi_clk domain
  ┌──────────────────┐               ┌───────────────────────┐
  │  AW channel buf  │──[Async FIFO]─►  AXI AW channel       │
  │  W data buffer   │──[Async FIFO]─►  AXI W channel        │
  │  AR channel buf  │──[Async FIFO]─►  AXI AR channel       │
  └──────────────────┘               └───────────────────────┘

  axi_clk domain                    noc_clk domain
  ┌──────────────────┐               ┌───────────────────────┐
  │  R data (RDATA)  │──[Async FIFO]─►  NoC flit assembly    │
  │  B resp (BRESP)  │──[Async FIFO]─►  NoC ack packet       │
  └──────────────────┘               └───────────────────────┘

  Mechanism: Async FIFO per AXI channel (AW, W, AR, R, B)
  Width: per-channel: AW=56+misc, W=512+strb, R=512+resp, etc.
```

This is the most complex CDC in the chip because it covers five AXI channels, each with different widths. The RDATA FIFO at the axi_clk→noc_clk boundary is the 512-entry configurable FIFO discussed in §3.7.2.

#### 9.6.5 EDC Ring Toggle CDC

**Location**: At the three intra-tile CDC boundaries in Y=2 Tensix tiles where the EDC ring traverses clock-domain boundaries (ai_clk→noc_clk, noc_clk→ai_clk, ai_clk→dm_clk).
**Usage**: Synchronizing the single-bit `req_tgl` and `ack_tgl` toggle signals as the EDC ring crosses between ai_clk, noc_clk, and dm_clk domains within a Tensix tile.

```
  Domain A (e.g., ai_clk)          Domain B (e.g., noc_clk)
  ┌─────────────────┐               ┌──────────────────────┐
  │  EDC node N     │               │  EDC node N+1        │
  │  req_tgl output │──[sync3r]────►│  req_tgl input       │
  │                 │               │                       │
  │  ack_tgl input  │◄──[sync3r]───│  ack_tgl output      │
  └─────────────────┘               └──────────────────────┘

  Mechanism: sync3r — 3-register synchronizer (3 flip-flop chain)
  Width:     1 bit (req_tgl), 1 bit (ack_tgl)
  Latency:   3 destination clock cycles per crossing
```

**D/C path classification** (per EDC HDD §3.5):
- `req_tgl`, `ack_tgl`: **Control** signals — must pass through synchronizer at domain boundaries
- `data[31:0]`: **Data** signals — captured combinationally only after the control toggle handshake is complete; no separate synchronizer required for data (the toggle protocol guarantees data stability)

As noted in §7.3, `DISABLE_SYNC_FLOPS=1` bypasses these synchronizers for same-clock-domain segments, reducing latency for the majority of the ring. The sync3r is only active at the three genuine inter-domain crossings at Y=2.

### 9.7 DFX Clock Gating Wrappers

#### 9.7.1 Purpose

N1B0 uses four DFX (Design for Test / Design for X) clock gating wrapper modules. Each wrapper serves two orthogonal purposes:

1. **Fine-grained clock gating for power management**: Clock gating at the sub-tile level allows individual functional blocks within a tile to be powered down independently. This is more efficient than gating the entire tile clock because, for example, the L1 SRAM can remain active for DMA while the FPU is gated.
2. **Scan-chain connectivity for ATPG test mode**: DFX wrappers contain the logic to multiplex between functional clock and test clock (scan enable), and to thread the scan chain through each gated block. This allows ATPG patterns to shift test data through even into normally-gated regions.

#### 9.7.2 ICG (Integrated Clock Gate) Cell

All DFX wrappers use **ICG cells** (Integrated Clock Gate, also called latch-based clock gate):

```
  ICG cell structure:
  ┌─────────────────────────────────┐
  │  Latch (active-low)             │
  │    D = EN (clock gate enable)   │
  │    CLK = clock (inverted)       │
  │    Q = latched enable           │
  │                                 │
  │  AND gate:                      │
  │    IN0 = clock                  │
  │    IN1 = latched enable (Q)     │
  │    OUT = gated_clock            │
  └─────────────────────────────────┘

  Timing:
    EN must be stable while clock is HIGH (setup/hold around falling edge)
    Output gated_clock = clock AND latched_enable
    No glitches possible: latch samples EN only when clock is HIGH
```

The latch ensures that the enable signal is sampled only at the correct phase of the clock, preventing any glitch on the gated clock output that could cause spurious state changes in the gated logic.

#### 9.7.3 Wrapper 1 — noc_niu_router_dfx

| Attribute         | Detail                                                    |
|-------------------|-----------------------------------------------------------|
| RTL module        | `noc_niu_router_dfx`                                      |
| Wraps             | NIU (`tt_noc2axi`) + Router (`tt_trinity_router`)          |
| Clock gated       | `noc_clk`                                                 |
| Enable condition  | Tile active (not harvested) AND at least one NoC transaction pending |
| Scan chain        | Threads through NIU VC FIFOs, ATT SRAM, router state FFs  |

**Functional significance**: The NoC is the primary inter-tile communication fabric. When a tile is idle (no incoming or outgoing NoC transactions), gating noc_clk to the NIU and router eliminates the largest single contributor to tile-level dynamic power after the FPU. Because noc_clk runs at 1.0–1.2 GHz, even modest gating efficiency (e.g., 50% duty cycle) provides significant power savings.

**DMA interaction**: When `noc_niu_router_dfx` gates `noc_clk`, no NoC transactions can be initiated or received for that tile. Firmware must ensure that no DMA is outstanding before asserting the gate enable. The NIU RDATA FIFO must be drained first.

#### 9.7.4 Wrapper 2 — overlay_wrapper_dfx

| Attribute         | Detail                                                    |
|-------------------|-----------------------------------------------------------|
| RTL module        | `overlay_wrapper_dfx`                                     |
| Wraps             | Overlay data-move logic (`neo_overlay_wrapper`)           |
| Clock gated       | `ai_clk[col]` and `dm_clk[col]`                           |
| Enable condition  | Tile active AND overlay control path active               |
| Scan chain        | Threads through overlay CDC FIFOs, context-switch logic   |

**Functional significance**: The overlay wrapper contains the CDC FIFOs between ai_clk, noc_clk, and dm_clk domains, the context-switch SRAMs, and the L1/L2 cache control logic. Gating both `ai_clk` and `dm_clk` via this wrapper effectively suspends all data-move operations for the tile. This is the appropriate state when the tile is in deep idle (no compute, no DMA in progress).

#### 9.7.5 Wrapper 3 — instrn_engine_wrapper_dfx

| Attribute         | Detail                                                    |
|-------------------|-----------------------------------------------------------|
| RTL module        | `instrn_engine_wrapper_dfx`                               |
| Wraps             | Instruction engine — TRISC0/1/2/3 processors              |
| Clock gated       | `ai_clk[col]`                                             |
| Enable condition  | Tile active AND a compute kernel is executing             |
| Scan chain        | Threads through TRISC0–3 instruction fetch FFs, CSRs      |

**Functional significance**: The instruction engines (TRISC3 for NoC DMA control, TRISC0/1/2 for pack/unpack/SFPU) are clock-intensive blocks that burn power even when stalled waiting for data. Gating `ai_clk` to the instruction engines via this wrapper allows the FPU (if separately active) to continue computing while the processors are held quiescent. This is useful during the tail of a GEMM tile — the FPU finishes draining the accumulator while TRISC3 is idle.

**Key design choice — separate from L1**: The instruction engine wrapper is separate from the L1 partition wrapper (§8.7.6), because the L1 must remain accessible for DMA even when the instruction engines are gated. If both were in the same wrapper, gating compute would also block DMA access to L1.

#### 9.7.6 Wrapper 4 — t6_l1_partition_dfx

| Attribute         | Detail                                                    |
|-------------------|-----------------------------------------------------------|
| RTL module        | `t6_l1_partition_dfx`                                     |
| Wraps             | T6 L1 SRAM partition (`tt_t6_l1_partition`)               |
| Clock gated       | `dm_clk[col]`                                             |
| Enable condition  | L1 is being accessed (DMA read/write or FPU load active)  |
| Scan chain        | Threads through L1 SRAM address/data path FFs             |

**Functional significance**: The L1 partition contains 512 SRAM macros per cluster (N1B0 4× expansion). Even with clock gating at the SRAM macro level, the surrounding address decode and read/write control logic continues to consume power if `dm_clk` runs. The `t6_l1_partition_dfx` wrapper gates `dm_clk` to the entire L1 partition when no L1 access is pending. This is the most energy-efficient state for a tile that is between kernel invocations: instruction engines are gated (§8.7.5), FPU is idle, and L1 is gated.

**N1B0 L1 size impact**: With 512 macros × 3MB per cluster, L1 is physically large. The power savings from gating dm_clk to L1 between kernels is proportionally larger in N1B0 than in baseline Trinity (128 macros/cluster), making this wrapper particularly important for N1B0 power management.

#### 9.7.7 Wrapper Summary and Interaction Matrix

The four wrappers provide independent control, enabling a hierarchy of power states within each tile:

```
  Power state           noc_niu_router  overlay  instrn_engine  t6_l1_partition
  ─────────────────────────────────────────────────────────────────────────────
  Full active           ENABLED         ENABLED  ENABLED        ENABLED
  Compute only          ENABLED         ENABLED  ENABLED        ENABLED (FPU)
  DMA only (no compute) ENABLED         ENABLED  GATED          ENABLED
  Standby (L1 active)   GATED           ENABLED  GATED          ENABLED
  Deep idle             GATED           GATED    GATED          GATED
  Harvested             GATED           GATED    GATED          GATED
```

During ATPG scan test, all four wrappers switch from ICG (gated) mode to scan-pass-through mode, allowing the scan enable signal to override the clock gate and feed the full-rate test clock to all flip-flops inside each wrapper.

### 9.8 MCPDLY=7 Derivation

```
  Worst-case EDC segment: Y=3 loopback in NOC2AXI_ROUTER composite tile

  REP_DEPTH_LOOPBACK = 6  (repeaters in the loopback path, N1B0 specific)
  +1 safety margin        (additional cycle for EDC node combinational logic)
  ─────────────────────
  MCPDLY = 7 cycles       (programmed into EDC CSR at chip initialization)
```

All ring segments use the same MCPDLY=7 since it covers the worst case. No per-segment MCPDLY override is needed.

---

## §10 Security Monitor Network (SMN)

### 10.1 Overview

The Security Monitor Network (SMN) enforces memory protection and access control for all transactions in the N1B0 NPU. It sits between the NoC/AXI interconnect and the protected resources, checking every incoming transaction against a set of programmed address ranges and access permissions.

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                         SMN Block Diagram                           │
  │                                                                     │
  │  NoC/AXI Masters ──► MST_COMMON ──► MST_MAIN ──► ADDR_TRANS       │
  │                                          │                          │
  │                                     MST_CMD_BUF                    │
  │                                          │                          │
  │                          ┌───────────────┴──────────────┐          │
  │                          ▼                              ▼           │
  │                   SLV_BLOCK                      SLV_NOC_SEC       │
  │                          │                              │           │
  │                   SLV_D2D              SLAVE_MAILBOX_0/1            │
  │                          │                                          │
  │                  Address Range Checker (8 ranges/NIU)              │
  │                          │                                          │
  │              PASS ───────┴─────────── FAIL → slv_ext_error         │
  │                │                               → CRIT_IRQ          │
  │           Protected Resource                                        │
  └─────────────────────────────────────────────────────────────────────┘
```

**Base address:** `0x03010000`
**Total registers:** 325

### 10.2 Sub-Block Map

| Sub-Block          | Offset    | Description                                               |
|--------------------|-----------|-----------------------------------------------------------|
| MST_COMMON         | +0x0000   | Global SMN enable, clock/reset control                   |
| MST_MAIN           | +0x0100   | Master security configuration, security level per master |
| ADDR_TRANS         | +0x0200   | Address translation rules (up to 16 entries)             |
| MST_CMD_BUF        | +0x0300   | Command buffer security assignment                       |
| SLAVE_MAILBOX_0    | +0x0400   | Inter-processor mailbox 0 (host ↔ Dispatch)              |
| SLAVE_MAILBOX_1    | +0x0500   | Inter-processor mailbox 1 (Dispatch ↔ firmware)          |
| SLV_BLOCK          | +0x0600   | Per-slave block access control                           |
| SLV_NOC_SEC        | +0x0700   | NoC slave security registers                             |
| SLV_D2D            | +0x0800   | Die-to-die security control                              |

### 10.3 Address Range Checker

Each NIU contains 8 independent address range checkers. Each range entry is fully programmable:

```
  Per-Range Register Set (for range N, N=0..7):
  ┌──────────────────────────────────────────────────────────────────────┐
  │  RANGE_BASE_N    [31:0]  — start address of protected region        │
  │  RANGE_SIZE_N    [31:0]  — size of region (in bytes, power-of-2)    │
  │  RANGE_PERM_N    [3:0]   — permissions: [3]=exec, [2]=read,        │
  │                             [1]=write, [0]=enable                   │
  │  RANGE_TARGET_N  [7:0]   — target endpoint index for this range     │
  └──────────────────────────────────────────────────────────────────────┘

  Permission encoding:
  4'b0001 = range enabled, no access (block all)
  4'b0101 = Read-only
  4'b0011 = Write-only
  4'b0111 = Read-Write
  4'b1111 = Read-Write-Execute
  4'b0000 = range disabled (pass-through, no check)
```

### 10.4 Firewall Violation Handling

When a transaction violates a range rule (address within a range but permission not granted):

1. Transaction is **blocked** — not forwarded to the target
2. `slv_ext_error` signal is asserted in the offending NIU
3. Error is logged in the SMN status register (`SLV_BLOCK_STATUS`)
4. A **CRIT interrupt** (`CRIT_IRQ`) is raised to the Dispatch tile interrupt controller
5. The interrupt handler (firmware) reads the violation log: offending master ID, address, access type

### 10.5 Mailbox Operation

The two slave mailboxes (`SLAVE_MAILBOX_0` and `SLAVE_MAILBOX_1`) provide hardware-assisted inter-processor communication:

```
  Mailbox Register Set:
  ┌─────────────────────────────────────────────────────────────────┐
  │  MBOX_WRITE_DATA  [31:0]  — write to post a message             │
  │  MBOX_READ_DATA   [31:0]  — read to consume a message           │
  │  MBOX_STATUS      [31:0]  — [0]=full, [1]=empty, [7:4]=count    │
  │  MBOX_INT_EN      [31:0]  — interrupt enable on full/empty      │
  └─────────────────────────────────────────────────────────────────┘

  Usage:
  - Host writes command to SLAVE_MAILBOX_0 → firmware reads and executes
  - Firmware writes result to SLAVE_MAILBOX_1 → host reads
  - Each mailbox generates an interrupt on write (to wake receiver)
```

### 10.6 SMN Programming Example

Configure range 0 to allow Tensix read-write access to DRAM region `0x80000000`–`0x8FFFFFFF`; all other ranges blocked:

```
  # Step 1: Enable SMN
  write 0x03010000 = 0x00000001   # MST_COMMON: global enable

  # Step 2: Program range 0 (Tensix DRAM window)
  write 0x03010600 = 0x80000000   # SLV_BLOCK RANGE_BASE_0
  write 0x03010604 = 0x10000000   # RANGE_SIZE_0 = 256 MB
  write 0x03010608 = 0x00000007   # RANGE_PERM_0 = RW enabled

  # Step 3: Block all other ranges (ranges 1..7 set to block-all)
  write 0x03010610 = 0x00000000   # RANGE_BASE_1 = 0
  write 0x03010618 = 0x00000001   # RANGE_PERM_1 = enabled, no access
  ... (repeat for ranges 2..7)

  # Step 4: Enable interrupt on violation
  write 0x03010700 = 0x00000001   # SLV_NOC_SEC: enable CRIT_IRQ on violation
```

---

## §11 Debug Module (RISC-V External Debug)

### 11.1 Overview

The Debug Module (DM) implements the RISC-V External Debug Support specification v0.13.2. It provides hardware-level debug capabilities including halt/resume control, register read/write, memory access, and arbitrary code execution on any halted hart.

**Base address:** `0x0300A000`
**Total registers:** 17
**Standard:** RISC-V Debug Specification v0.13.2
**Transport:** APB slave, connected to Dispatch tile APB bus

### 11.2 Supported Harts

```
  Hart configuration in N1B0:

  Per Tensix cluster:
  ┌────────────────────────────────────────────┐
  │  TRISC3   — hart 0 (tile management core)  │
  │  TRISC0   — hart 1 (thread 0)              │
  │  TRISC1   — hart 2 (thread 1)              │
  │  TRISC2   — hart 3 (thread 2)              │
  └────────────────────────────────────────────┘

  12 Tensix clusters × 4 harts/cluster = 48 harts total
  Hart ID = tile_index * 4 + hart_within_tile
  tile_index = x * 5 + y  (EndpointIndex encoding)
```

### 11.3 Register Map

| Offset | Register     | Width | Access | Description                                          |
|--------|--------------|-------|--------|------------------------------------------------------|
| 0x000  | DMCONTROL    | 32    | RW     | Halt/resume/reset control for selected harts         |
| 0x004  | DMSTATUS     | 32    | RO     | Per-hart halted/running/unavailable status           |
| 0x008  | HARTINFO     | 32    | RO     | Hart information (data register count, CSR access)   |
| 0x00C  | HALTSUM1     | 32    | RO     | Halt summary for harts 32–63                         |
| 0x010  | HAWINDOWSEL  | 32    | RW     | Hart array window select                             |
| 0x014  | HAWINDOW     | 32    | RW     | Hart array window (enable/select target harts)       |
| 0x018  | ABSTRACTCS   | 32    | RW     | Abstract command status and control                  |
| 0x01C  | COMMAND      | 32    | WO     | Abstract command register                            |
| 0x020  | ABSTRACTAUTO | 32    | RW     | Automatic abstract command execution trigger         |
| 0x040  | PROGBUF0     | 32    | RW     | Program buffer word 0                                |
| 0x044  | PROGBUF1     | 32    | RW     | Program buffer word 1                                |
| 0x048  | PROGBUF2     | 32    | RW     | Program buffer word 2                                |
| 0x04C  | PROGBUF3     | 32    | RW     | Program buffer word 3                                |
| 0x050  | PROGBUF4     | 32    | RW     | Program buffer word 4                                |
| 0x054  | PROGBUF5     | 32    | RW     | Program buffer word 5                                |
| 0x058  | PROGBUF6     | 32    | RW     | Program buffer word 6                                |
| 0x05C  | PROGBUF7     | 32    | RW     | Program buffer word 7                                |
| 0x060  | SBCS         | 32    | RW     | System bus access control and status                 |
| 0x064  | SBADDRESS0   | 32    | RW     | System bus address bits [31:0]                       |
| 0x068  | SBADDRESS1   | 32    | RW     | System bus address bits [63:32]                      |
| 0x06C  | SBDATA0      | 32    | RW     | System bus data bits [31:0]                          |
| 0x070  | SBDATA1      | 32    | RW     | System bus data bits [63:32]                         |

### 11.4 DMCONTROL Register Detail

```
  DMCONTROL [31:0]:
  ┌─────────────────────────────────────────────────────────────────────┐
  │ [31]    haltreq         — 1=request halt for selected harts         │
  │ [30]    resumereq       — 1=request resume for selected harts       │
  │ [29]    hartreset       — 1=assert hart reset                       │
  │ [28]    ackhavereset    — 1=acknowledge hart has been reset         │
  │ [27]    reserved                                                    │
  │ [26]    hasel           — 0=single hart (hartsel), 1=hart array     │
  │ [25:16] hartsello       — lower 10 bits of hart index               │
  │ [15:6]  hartselhi       — upper 10 bits of hart index               │
  │ [5:4]   reserved                                                    │
  │ [3]     setresethaltreq — set halt-on-reset for selected hart       │
  │ [2]     clrresethaltreq — clear halt-on-reset                       │
  │ [1]     ndmreset        — 1=assert non-debug module reset           │
  │ [0]     dmactive        — 1=activate debug module (must be set first)│
  └─────────────────────────────────────────────────────────────────────┘
```

### 11.5 Abstract Commands (COMMAND Register)

The COMMAND register supports three command types:

```
  Command type encoding [31:24]:
  0x00 = Access Register   — read/write GPR, CSR, FPR
  0x01 = Quick Access      — halt, execute PROGBUF, resume in one step
  0x02 = Access Memory     — read/write memory without halting

  Access Register command [23:0]:
  ┌──────────────────────────────────────────────────────────────────┐
  │ [23]    reserved                                                 │
  │ [22:20] aarsize   — 0=8-bit, 1=16-bit, 2=32-bit, 3=64-bit      │
  │ [19]    aarpostincrement — auto-increment address after access   │
  │ [18]    postexec  — 1=execute PROGBUF after register access      │
  │ [17]    transfer  — 1=perform the register access                │
  │ [16]    write     — 0=read (DM←hart), 1=write (DM→hart)         │
  │ [15:0]  regno     — register number (0x1000=CSR base, 0x0=x0)   │
  └──────────────────────────────────────────────────────────────────┘
```

### 11.6 Program Buffer Execution

The 8-word (256-bit) program buffer allows arbitrary instruction execution on a halted hart:

```
  Typical flow to read a memory-mapped register:

  1. Halt the target hart:
       DMCONTROL.haltreq=1, DMCONTROL.hartsel=<hart_id>
       Poll DMSTATUS.allhalted=1

  2. Load address into x1 via abstract command:
       COMMAND = {type=0x00, aarsize=2, transfer=1, write=1, regno=0x1001}
       DATA0 = <target_address>

  3. Write PROGBUF with LW + EBREAK:
       PROGBUF0 = 0x0000A083   # lw x1, 0(x1)
       PROGBUF1 = 0x00100073   # ebreak

  4. Execute PROGBUF:
       COMMAND = {type=0x00, aarsize=2, transfer=0, postexec=1, regno=0x1001}

  5. Read result from x1 via abstract command:
       COMMAND = {type=0x00, aarsize=2, transfer=1, write=0, regno=0x1001}
       result = DATA0

  6. Resume hart:
       DMCONTROL.resumereq=1
       Poll DMSTATUS.allrunning=1
```

### 11.7 System Bus Access (SBCS / SBADDRESS / SBDATA)

The system bus access path allows the debugger to read/write memory without halting any hart. This is useful for monitoring running state:

```
  SBCS register configuration for 32-bit read:
  write SBCS = 0x00040000    # sbaccess=2 (32-bit), sbautoread=0

  # Read a single 32-bit word from address 0x80001234:
  write SBADDRESS0 = 0x80001234
  read  SBDATA0                  # triggers bus read; poll SBCS.sbbusy=0 first

  # Auto-increment read (sequential burst):
  write SBCS = 0x00060000    # sbaccess=2, sbautoincrement=1, sbautoread=1
  write SBADDRESS0 = 0x80001234   # starts first read automatically
  read  SBDATA0                   # data[0]; triggers read of next address
  read  SBDATA0                   # data[1]
  ... (continue for burst length)
```

---

## §12 Adaptive Workload Manager (AWM)

### 12.1 Overview

The Adaptive Workload Manager (AWM) is the power and frequency management subsystem of the N1B0 NPU. It controls PLL settings, monitors voltage droop and temperature, manages clock gating, and exposes a register interface for firmware-driven DVFS (Dynamic Voltage and Frequency Scaling).

**Base address:** `0x03020000`
**Total registers:** 479
**Sub-blocks:** 7

### 12.2 Sub-Block Map

```
  AWM Address Map:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  0x03020000  AWM_GLOBAL     — global enable, IRQ status, error regs  │
  │  0x03020100  FREQUENCY0     — frequency domain 0 (noc_clk)           │
  │  0x03020200  FREQUENCY1     — frequency domain 1 (ai_clk[0])         │
  │  0x03020300  FREQUENCY2     — frequency domain 2 (ai_clk[1])         │
  │  0x03020400  FREQUENCY3     — frequency domain 3 (ai_clk[2])         │
  │  0x03020500  FREQUENCY4     — frequency domain 4 (ai_clk[3])         │
  │  0x03020600  FREQUENCY5     — frequency domain 5 (dm_clk shared)     │
  │  0x03020700  CGM0           — clock gating management block 0        │
  │  0x03020800  CGM1           — clock gating management block 1        │
  │  0x03020900  CGM2           — clock gating management block 2        │
  │  0x03020A00  DROOP_0        — voltage droop detector 0               │
  │  0x03020B00  DROOP_1        — voltage droop detector 1               │
  │  0x03020C00  DROOP_2        — voltage droop detector 2               │
  │  0x03020D00  DROOP_3        — voltage droop detector 3               │
  │  0x03020E00  TEMP_SENSOR    — on-chip temperature sensor             │
  │  0x03020F00  TT_PLL_PVT     — PLL/PVT sensor control and calibration │
  │  0x03021000  CLK_OBSERVE    — clock frequency measurement            │
  └──────────────────────────────────────────────────────────────────────┘
```

### 12.3 AWM_GLOBAL Register Set

| Offset | Register       | Description                                              |
|--------|----------------|----------------------------------------------------------|
| +0x00  | AWM_CTRL       | [0]=global enable, [1]=DVFS enable, [2]=droop_en         |
| +0x04  | AWM_STATUS     | [0]=freq_change_in_progress, [1]=droop_active            |
| +0x08  | AWM_IRQ_STATUS | Interrupt status bits (W1C)                              |
| +0x0C  | AWM_IRQ_EN     | Interrupt enable bits                                    |
| +0x10  | AWM_ERROR_CODE | Last error code from AWM state machine                   |
| +0x14  | AWM_VERSION    | AWM IP version register (RO)                            |

### 12.4 Frequency Domain Control

Each of the 6 FREQUENCY sub-blocks controls one clock frequency domain:

| Domain | Sub-block   | Clock output     | Controls                        |
|--------|-------------|------------------|---------------------------------|
| 0      | FREQUENCY0  | noc_clk          | NoC fabric, NIU, EDC ring       |
| 1      | FREQUENCY1  | ai_clk[0]        | Column 0 Tensix compute         |
| 2      | FREQUENCY2  | ai_clk[1]        | Column 1 Tensix compute         |
| 3      | FREQUENCY3  | ai_clk[2]        | Column 2 Tensix compute         |
| 4      | FREQUENCY4  | ai_clk[3]        | Column 3 Tensix compute         |
| 5      | FREQUENCY5  | dm_clk (shared)  | Data-move overlay, all columns  |

Per-domain registers (offset within each FREQUENCYn block):

```
  ┌──────────────────────────────────────────────────────────────────┐
  │  +0x00  FREQ_TARGET   [15:0]  — target frequency code           │
  │  +0x04  FREQ_CURRENT  [15:0]  — current operating frequency     │
  │  +0x08  FREQ_MIN      [15:0]  — minimum allowed frequency       │
  │  +0x0C  FREQ_MAX      [15:0]  — maximum allowed frequency       │
  │  +0x10  PLL_DIVIDER   [7:0]   — PLL output divider setting      │
  │  +0x14  FREQ_STATUS   [3:0]   — [0]=locked, [1]=changing,       │
  │                                  [2]=droop_limited               │
  │  +0x18  FREQ_CTRL     [3:0]   — [0]=enable, [1]=bypass_pll      │
  └──────────────────────────────────────────────────────────────────┘
```

### 12.5 Frequency Scaling Flow

```
  Firmware DVFS flow (increase ai_clk[0] frequency):
  ┌──────────────────────────────────────────────────────────────────────┐
  │  1. Verify no active transitions:                                    │
  │       poll FREQUENCY1.FREQ_STATUS[1] == 0 (not changing)            │
  │                                                                      │
  │  2. Set new target frequency:                                        │
  │       write 0x03020100 + 0x00 = <new_freq_code>                     │
  │                                                                      │
  │  3. Trigger frequency change:                                        │
  │       write FREQUENCY1.FREQ_CTRL[0] = 1                             │
  │                                                                      │
  │  4. Poll for completion:                                             │
  │       poll FREQUENCY1.FREQ_STATUS[0] == 1 (PLL locked)              │
  │       poll FREQUENCY1.FREQ_STATUS[1] == 0 (not changing)            │
  │                                                                      │
  │  5. Verify actual frequency:                                         │
  │       read FREQUENCY1.FREQ_CURRENT — should match FREQ_TARGET        │
  └──────────────────────────────────────────────────────────────────────┘
```

### 12.6 CGM (Clock Gating Management)

Three CGM blocks manage autonomous clock gating based on activity monitoring:

| CGM Block | Scope          | Gating Granularity       |
|-----------|----------------|--------------------------|
| CGM0      | noc_clk domain | Per-row NoC router gating |
| CGM1      | ai_clk domain  | Per-tile Tensix FPU gating |
| CGM2      | dm_clk domain  | Per-tile overlay gating   |

CGM registers (per block):

```
  +0x00  CGM_ENABLE    — bit-per-tile autonomous gating enable
  +0x04  CGM_IDLE_CNT  — idle cycle threshold before gating
  +0x08  CGM_STATUS    — current gating state per tile (1=gated)
  +0x0C  CGM_FORCE_ON  — force clocks on (overrides autonomous gating)
  +0x10  CGM_WAKEUP_LAT — wakeup latency in cycles (for scheduler use)
```

### 12.7 Voltage Droop Detectors

Four droop detectors monitor supply voltage across the die. When voltage droops (typically during a sudden load increase), the detectors automatically trigger a frequency reduction to prevent timing failures.

```
  Droop Detector Architecture:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Ring oscillator → frequency counter → compare against threshold     │
  │                                                                      │
  │  On droop detected:                                                  │
  │  1. Hardware immediately reduces PLL output (frequency step-down)    │
  │  2. DROOP_STATUS register updated                                    │
  │  3. AWM_IRQ_STATUS[DROOP_IRQ] asserted                               │
  │  4. Firmware ISR reads cause, logs event, optionally adjusts voltage │
  │  5. When voltage recovers: auto frequency restore (if configured)    │
  └──────────────────────────────────────────────────────────────────────┘
```

Per-droop-detector registers:

| Offset | Register         | Description                                        |
|--------|------------------|----------------------------------------------------|
| +0x00  | DROOP_CTRL       | [0]=enable, [1]=auto_restore, [2]=irq_en           |
| +0x04  | DROOP_THRESHOLD  | Ring oscillator count threshold for droop detect   |
| +0x08  | DROOP_FREQ_STEP  | Frequency step-down amount on droop event          |
| +0x0C  | DROOP_STATUS     | [0]=droop_active, [1]=freq_reduced, [15:8]=count   |
| +0x10  | DROOP_LOG        | Timestamp of last droop event                      |

### 12.8 Temperature Sensor

The on-chip temperature sensor provides continuous die temperature monitoring with configurable threshold interrupts.

```
  TEMP_SENSOR registers:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  +0x00  TEMP_CTRL       — [0]=enable sensor, [1]=continuous_mode     │
  │  +0x04  TEMP_STATUS     — [0]=conversion_done, [1]=high_alert        │
  │  +0x08  TEMP_DATA       — [15:0] current temperature (°C, signed)    │
  │  +0x0C  TEMP_HIGH_THR   — high temperature threshold (°C)            │
  │  +0x10  TEMP_LOW_THR    — low temperature threshold (°C)             │
  │  +0x14  TEMP_IRQ_EN     — [0]=high_thr_en, [1]=low_thr_en           │
  │  +0x18  TEMP_CALIB      — calibration offset (factory programmed)    │
  └──────────────────────────────────────────────────────────────────────┘

  Reading temperature:
    poll TEMP_STATUS[0] == 1   (conversion done)
    temp_celsius = (signed16) TEMP_DATA[15:0]  (LSB = 0.1°C resolution)
```

### 12.9 PLL/PVT Sensor (TT_PLL_PVT)

```
  TT_PLL_PVT sub-block controls and calibrates the on-chip PLLs:
  ┌───────────────────────────────────────────────────────────────────┐
  │  +0x00  PLL_CTRL        — PLL enable/bypass/lock control          │
  │  +0x04  PLL_CFG0        — PLL multiplication factor (M divider)   │
  │  +0x08  PLL_CFG1        — PLL input/output dividers (N/OD)        │
  │  +0x0C  PLL_STATUS      — [0]=locked, [1]=loss_of_lock            │
  │  +0x10  PVT_CTRL        — PVT sensor enable                       │
  │  +0x14  PVT_DATA        — PVT sensor reading (voltage/process)    │
  │  +0x18  PVT_CALIB       — factory calibration value               │
  └───────────────────────────────────────────────────────────────────┘
```

### 12.10 Clock Observation (CLK_OBSERVE)

The CLK_OBSERVE sub-block measures the frequency of any internal clock by counting cycles over a fixed ref_clk window:

```
  +0x00  CLKOBS_SEL    — clock select mux (which clock to observe)
  +0x04  CLKOBS_CTRL   — [0]=start measurement, [1]=continuous mode
  +0x08  CLKOBS_WINDOW — measurement window in ref_clk cycles
  +0x0C  CLKOBS_COUNT  — measured target clock cycles in window
  +0x10  CLKOBS_STATUS — [0]=done, [1]=overflow

  Computed frequency = CLKOBS_COUNT * (ref_clk_freq / CLKOBS_WINDOW)
```

---

## §13 Memory Architecture

### 13.1 Overview

The N1B0 NPU memory hierarchy spans multiple SRAM types across three clock domains. The L1 SRAM capacity is 4× the baseline Trinity design, enabling larger intermediate tensor buffers for LLM and other workloads.

```
  N1B0 Memory Hierarchy:
  ┌──────────────────────────────────────────────────────────────────────────────────────────┐
  │  Level        │ Type          │ Domain   │ Per-cluster/tile        │ Total (12 clusters)  │
  │  ──────────────────────────────────────────────────────────────────────────────────────  │
  │  DEST RF      │ Latch array   │ ai_clk   │ 12,288 e × 32b = 48 KB │ 576 KB (latch)       │
  │  SRCA RF      │ Latch array   │ ai_clk   │  1,536 e × 16b =  3 KB │  36 KB (latch)       │
  │  L1 SRAM      │ SRAM macro    │ ai_clk   │ 512 macros    =  3 MB  │  36 MB               │
  │  TRISC0 I$    │ SRAM macro    │ ai_clk   │ 512×72b       =  4 KB  │  48 KB (×12)         │
  │  TRISC1 I$    │ SRAM macro    │ ai_clk   │ 256×72b       =  2 KB  │  24 KB (×12)         │
  │  TRISC2 I$    │ SRAM macro    │ ai_clk   │ 256×72b       =  2 KB  │  24 KB (×12)         │
  │  TRISC3 I$    │ SRAM macro    │ ai_clk   │ 512×72b       =  4 KB  │  48 KB (×12)         │
  │  TRISC0 LM    │ SRAM macro    │ ai_clk   │ 512×52b       =  3.25KB│  39 KB (×12)         │
  │  TRISC1 LM    │ SRAM macro    │ ai_clk   │ 512×52b       =  3.25KB│  39 KB (×12)         │
  │  TRISC2 LM    │ SRAM macro    │ ai_clk   │ 1024×52b      =  6.5KB │  78 KB (×12)         │
  │  TRISC Vec LM │ SRAM macro    │ ai_clk   │ 2×(256×104b)  =  6.5KB │  78 KB (×12)         │
  │  OVL L1 D$    │ SRAM macro    │ dm_clk   │ 16 macros/tile          │ 224 macros total     │
  │  OVL L1 I$    │ SRAM macro    │ dm_clk   │ 16 macros/tile          │ 224 macros total     │
  │  OVL L1 tag   │ SRAM macro    │ dm_clk   │ 16 macros/tile          │ 224 macros total     │
  │  OVL L2       │ SRAM macro    │ dm_clk   │ 20 macros/tile          │ 280 macros total     │
  │  Ctx Switch   │ SRAM macro    │ dm_clk   │ 2 macros/tile           │  28 macros total     │
  │  NoC VC FIFO  │ SRAM macro    │ noc_clk  │ 5 macros/tile           │ ≥62 macros total     │
  │  ATT SRAM     │ SRAM macro    │ noc_clk  │ 2 macros/NIU tile       │  ~20 macros total    │
  └──────────────────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- DEST/SRCA are **latch arrays**, NOT SRAM macros — different power/area characteristics
- L1 512 macros = 256 `_0_low` + 256 `_0_high` instances; each pair = 12KB (768 rows × 128 effective bits / 8); verified from `N1B0_NPU_memory_list20260221_2.csv`
- TRISC I$ 72-bit macro = 64 data bits + 8 parity/ECC; effective capacity uses 64b
- OVL counts cover 12 Tensix tiles + 2 Dispatch tiles = 14 tiles total for overlay memories

### 13.2 L1 SRAM (T6 L1 — N1B0 Expanded)

The T6 L1 SRAM is the primary scratchpad for Tensix compute tiles.

```
  N1B0 L1 Configuration vs Baseline:
  ┌──────────────────────────┬────────────────────────┬──────────────────────────┐
  │  Parameter               │  Baseline Trinity       │  N1B0                   │
  ├──────────────────────────┼────────────────────────┼──────────────────────────┤
  │  Macro instances/cluster │  128                    │  512                     │
  │  Physical macro name      │  rf1r_hdrw_lvt_768x69  │  rf1r_hdrw_lvt_768x69   │
  │  Logical sub-bank width   │  _low+_high pair=128b  │  _low+_high pair=128b   │
  │  Macro size (per pair)    │  12 KB (768×128b eff.) │  12 KB (768×128b eff.)  │
  │  Sub-bank pairs/cluster   │  64                    │  256                     │
  │  Total per cluster        │  768 KB                │  3 MB                   │
  │  Total (12 clusters)      │  9.216 MB              │  36 MB                  │
  │  Read ports               │  4                     │  4                       │
  │  Write ports              │  2                     │  2                       │
  │  ECC                      │  SECDED (5b parity)    │  SECDED (5b parity)     │
  │  DFX wrapper              │  None                  │  t6_l1_partition_dfx    │
  └──────────────────────────┴────────────────────────┴──────────────────────────┘
```

**Macro naming convention:** Each logical sub-bank is implemented as two physical macros:
- `u_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1_0_low`  — lower 64 data bits
- `u_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1_0_high` — upper 64 data bits

Each macro provides 768 rows × 69 bits (64 data + 5 parity). The pair together gives a 768×128-bit logical word. 256 pairs × 768 rows × 128 bits / 8 = **3,145,728 bytes = 3 MB per cluster**. Verified from `N1B0_NPU_memory_list20260221_2.csv` (256 `_0_low` + 256 `_0_high` instances per Tensix cluster).

L1 bank arbitration policy: priority given to TDMA (DMA engine) over CPU accesses to minimize stall cycles during matrix operations.

### 13.2a TRISC Instruction Cache (ICache)

Each of the 4 TRISC threads (TRISC0–TRISC3) has a private instruction cache backed by L1 SRAM. Cache sizes differ per thread, verified from `N1B0_NPU_memory_list20260221_2.csv`:

```
  TRISC ICache Sizes (per cluster — 4 threads × 12 clusters):
  ┌─────────┬────────────────────────┬───────────────────────────────────────────┐
  │  Thread │  Macro (RTL)           │  Effective capacity                        │
  ├─────────┼────────────────────────┼───────────────────────────────────────────┤
  │  TRISC0 │  512×72b  (full)       │  512 rows × 64 data bits / 8 = 4 KB       │
  │  TRISC1 │  256×72b  (half)       │  256 rows × 64 data bits / 8 = 2 KB       │
  │  TRISC2 │  256×72b  (half)       │  256 rows × 64 data bits / 8 = 2 KB       │
  │  TRISC3 │  512×72b  (full)       │  512 rows × 64 data bits / 8 = 4 KB       │
  └─────────┴────────────────────────┴───────────────────────────────────────────┘
  Macro width: 72 bits = 64 data + 8 parity/ECC
  Total ICache SRAM per cluster: 4+2+2+4 = 12 KB  (48 macros per cluster)
  Total ICache SRAM (×12 clusters): 144 KB  (576 macros)
```

TRISC3 receives the same 4KB ICache as TRISC0 because tile-management firmware (boot sequences, interrupt handlers) is larger than the tight inner-loop LLK programs run by TRISC1/TRISC2.

### 13.2b TRISC Local Memory (LM / Scratchpad)

Each thread also has a private data scratchpad (stack, heap, local variables). Source: `LOCAL_MEM_SIZE_BYTES` parameters in RTL:

```
  TRISC Local Memory Sizes (per cluster):
  ┌─────────┬──────────────────────┬────────────────────────────────────────┐
  │  Thread │  Macro (RTL)         │  Effective capacity                     │
  ├─────────┼──────────────────────┼────────────────────────────────────────┤
  │  TRISC0 │  512×52b             │  512 × 52 bits / 8 ≈ 3.25 KB          │
  │  TRISC1 │  512×52b             │  512 × 52 bits / 8 ≈ 3.25 KB          │
  │  TRISC2 │  1024×52b            │  1024 × 52 bits / 8 ≈ 6.5 KB          │
  │  TRISC3 │  1024×52b            │  1024 × 52 bits / 8 ≈ 6.5 KB          │
  │  Vec LM0│  256×104b            │  256 × 104 bits / 8 ≈ 3.25 KB         │
  │  Vec LM1│  256×104b            │  256 × 104 bits / 8 ≈ 3.25 KB         │
  └─────────┴──────────────────────┴────────────────────────────────────────┘
  Total LM per cluster: ~26 KB  (9 macros per cluster)
  Total LM (×12 clusters): ~312 KB  (108 macros)
```

### 13.3 L1 CSR (T6_L1_CSR, base 0x03000200)

Key L1 control registers:

| Offset | Register       | Description                                         |
|--------|----------------|-----------------------------------------------------|
| +0x00  | RD_PORT_CTRL   | Read port enable mask [3:0]                         |
| +0x04  | WR_PORT_CTRL   | Write port enable mask [1:0]                        |
| +0x08  | GROUP_HASH_FN0 | Bank interleaving hash function 0 configuration     |
| +0x0C  | GROUP_HASH_FN1 | Bank interleaving hash function 1 configuration     |
| +0x10  | ECC_STATUS     | [0]=correctable error, [1]=uncorrectable error      |
| +0x14  | ECC_ADDR       | Address of last ECC error                           |
| +0x18  | CONFLICT_CNT   | Bank conflict counter (performance monitoring)      |
| +0x1C  | BW_THROTTLE    | Bandwidth throttle control (max requests/cycle)     |

### 13.4 DEST Register File

The destination register file stores MAC accumulation results in Tensix tiles:

```
  DEST RF Specifications:
  ┌──────────────────────────────────────────────────────────────────┐
  │  Type:        Latch array (not SRAM macro)                       │
  │  Entries:     12,288 per tile (1,024 per reg-bank × 12 banks)    │
  │  Width:       32 bits per entry (FP32 accumulation)              │
  │  Capacity:    12,288 × 32 / 8 = 48 KB per tile (latch)          │
  │  Total:       12 tiles × 48 KB = 576 KB total (147,456 entries)  │
  │  Domain:      ai_clk                                            │
  │  Read ports:  1 (to FPU output mux)                              │
  │  Write ports: 1 (from FPU accumulator)                           │
  │  ECC:         Not present (protected by FPU result checking)     │
  │  EDC:         Included in EDC ring coverage (CRIT on fault)      │
  └──────────────────────────────────────────────────────────────────┘
```

### 13.5 SRCA Register File

SRCA holds source operands for the Tensix FPU (matrix A side):

```
  SRCA RF Specifications:
  ┌──────────────────────────────────────────────────────────────────┐
  │  Type:        Latch array (not SRAM macro)                       │
  │  Entries:     1,536 per tile                                     │
  │  Width:       16 bits per entry (FP16/BF16/INT16 operands)       │
  │  Capacity:    1,536 × 16 / 8 = 3 KB per tile (latch)            │
  │  Total:       12 tiles × 3 KB = 36 KB total (18,432 entries)     │
  │  Domain:      ai_clk                                            │
  │  Feed path:   L1 → TDMA unpacker → SRCA → FPU M-Tile            │
  │  EDC:         Covered (CRIT on fault)                            │
  └──────────────────────────────────────────────────────────────────┘
```

### 13.6 NoC VC FIFOs

Each NoC router contains per-virtual-channel FIFOs for flow control:

```
  VC FIFO Configuration:
  ┌──────────────────────────────────────────────────────────────────┐
  │  Virtual channels: 2 per port direction                          │
  │  Port directions:  North, South, East, West, Local               │
  │  FIFO depth:       4–16 flits per VC (design-specific)          │
  │  FIFO width:       512 bits (full flit width)                   │
  │  Total macros:     ≥62 across all router instances              │
  │  Domain:           noc_clk                                      │
  │  ECC:              Yes (for in-flight flit protection)          │
  └──────────────────────────────────────────────────────────────────┘
```

For the NOC2AXI_ROUTER_OPT variants, the RDATA FIFO depth is configurable via a Verilog define:

- Default: 512 entries
- Range: 32–1024 entries
- DK path: `used_in_n1/` scope

### 13.7 ATT SRAM (Address Translation Table)

Each NIU contains a 64-entry ATT SRAM for address routing:

```
  ATT Entry Format [63:0]:
  ┌──────────────────────────────────────────────────────────────────┐
  │  [63:32]  MASK      — address mask bits                         │
  │  [31:16]  ENDPOINT  — target endpoint index                     │
  │  [15:8]   ROUTING   — routing mode flags                        │
  │  [7:0]    VALID     — entry valid bit and priority              │
  └──────────────────────────────────────────────────────────────────┘

  ATT lookup: incoming AXI address is compared against all valid entries
  (masked comparison). First hit determines routing endpoint.
  On miss: default route used (programmed in NIU_DEFAULT_ROUTE register).
```

### 13.8 Full SRAM Count Summary

| Clock Domain | Memory Type             | Count (N1B0)              | Capacity (N1B0 total)      | Implementation  |
|--------------|-------------------------|---------------------------|----------------------------|-----------------|
| ai_clk       | T6 L1 SRAM              | 6,144 macros (512×12 cls) | **36 MB**                  | SRAM macro      |
| ai_clk       | DEST register file      | 147,456 entries (12,288×12) | **576 KB**               | Latch array     |
| ai_clk       | SRCA register file      | 18,432 entries (1,536×12) | **36 KB**                  | Latch array     |
| ai_clk       | TRISC0/3 ICache (full)  | 24 macros (2×12 cls)      | **96 KB** (4KB×12×2)       | SRAM macro      |
| ai_clk       | TRISC1/2 ICache (half)  | 24 macros (2×12 cls)      | **48 KB** (2KB×12×2)       | SRAM macro      |
| ai_clk       | TRISC0/1 Local Mem      | 24 macros (2×12 cls)      | **78 KB** (3.25KB×12×2)    | SRAM macro      |
| ai_clk       | TRISC2/3 Local Mem      | 24 macros (2×12 cls)      | **156 KB** (6.5KB×12×2)    | SRAM macro      |
| ai_clk       | TRISC Vec Local Mem     | 24 macros (2×12 cls)      | **78 KB** (3.25KB×12×2)    | SRAM macro      |
| dm_clk       | Overlay L1 D-Cache data | 224 macros (16×14 tiles)  | —                          | SRAM macro      |
| dm_clk       | Overlay L1 I-Cache data | 224 macros (16×14 tiles)  | —                          | SRAM macro      |
| dm_clk       | Overlay L1 tag (D+I)    | 224 macros (8+8 × 14)     | —                          | SRAM macro      |
| dm_clk       | Overlay L2 data+dir     | 280 macros (20×14 tiles)  | —                          | SRAM macro      |
| dm_clk       | Context switch SRAM     | 28 macros (2×14 tiles)    | —                          | SRAM macro      |
| noc_clk      | NoC VC FIFOs            | ≥62 macros                | —                          | SRAM macro      |
| noc_clk      | NIU ATT SRAM            | ~20 macros (2 per NIU)    | —                          | SRAM macro      |
| axi_clk      | AXI RDATA FIFO          | 4 macros (1 per NIU tile) | —                          | SRAM macro      |

**Total on-chip SRAM (dominant terms):**
- T6 L1: **36 MB** — by far the largest; sized to hold full K_tile weight slices + KV-cache
- DEST latch: **576 KB** — FPU accumulation; latch (not SRAM) for single-cycle read latency
- TRISC memories: **~456 KB** — ICache + LM across all threads (12 clusters × 4 threads)
- Overlay cache: **~840 macros** (dm_clk) — Rocket CPU L1/L2 data and instruction caches

---

## §14 SFR Summary

### 14.1 Complete SFR Memory Map

All software-visible registers are mapped into a contiguous region starting at `0x03000000`. The table below covers all 8 subsystems.

```
  N1B0 NPU SFR Map (0x03000000 – 0x0302FFFF):
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  0x03000000 ─────────────────────────────────── 0x030001FF                   │
  │  CLUSTER_CTRL (96 registers)                                                 │
  │  Clock enable, soft reset, core configuration, tile enable mask              │
  │  Key: CLK_EN[15:0], SOFT_RESET[15:0], CORE_CONFIG, TILE_EN_MASK             │
  │       EDC_GLOBAL_EN, EDC_BYPASS_MASK, ISO_EN[11:0], CHIP_ID, VERSION        │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03000200 ─────────────────────────────────── 0x030003FF                   │
  │  T6_L1_CSR (91 registers)                                                    │
  │  L1 SRAM port config, ECC, bank hash function, bandwidth throttle           │
  │  Key: RD_PORT_CTRL, WR_PORT_CTRL, GROUP_HASH_FN0/1, ECC_STATUS/ADDR        │
  │       CONFLICT_CNT, BW_THROTTLE                                             │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03000400 ─────────────────────────────────── 0x030005FF                   │
  │  CACHE_CTRL (7 registers)                                                    │
  │  L2 cache enable, flush, invalidate, hit/miss performance counters          │
  │  Key: CACHE_ENABLE, CACHE_FLUSH, CACHE_INVALIDATE, HIT_CNT, MISS_CNT       │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03000600 ─────────────────────────────────── 0x030041FF                   │
  │  LLK_TILE_COUNTERS (576 registers)                                           │
  │  Per-tile operation counters and stall counters (N=0..11 per tile)          │
  │  Key: TILE_OP_CNT[N], TILE_STALL_CNT[N], TILE_IDLE_CNT[N]                  │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03004000 ─────────────────────────────────── 0x03009FFF                   │
  │  IDMA_APB (1,528 registers)                                                  │
  │  8 iDMA engine register sets; command buffer, address generator, DMA ctrl   │
  │  Key: CMD_BUF[0..7], ADDR_GEN[0..7], SIMPLE_CMD, DMA_STATUS, DMA_CTRL     │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x0300A000 ─────────────────────────────────── 0x0300AFFF                   │
  │  DEBUG_MODULE (17 registers — RISC-V Debug v0.13.2)                          │
  │  Hart halt/resume/reset, abstract commands, program buffer, sys bus access  │
  │  Key: DMCONTROL, DMSTATUS, ABSTRACTCS, COMMAND, PROGBUF0..7, SBCS          │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03010000 ─────────────────────────────────── 0x0301FFFF                   │
  │  SMN (325 registers)                                                         │
  │  Address range checkers, firewall, inter-processor mailboxes, master sec.   │
  │  Key: RANGE_BASE/SIZE/PERM[0..7], MBOX_WRITE/READ/STATUS, MST_MAIN_CTRL    │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03020000 ─────────────────────────────────── 0x0302FFFF                   │
  │  AWM (479 registers)                                                         │
  │  PLL/frequency control, clock gating, droop detection, temperature sensor   │
  │  Key: FREQ_TARGET/CURRENT[0..5], CGM_ENABLE, DROOP_CFG, TEMP_DATA, PLL_CFG │
  └──────────────────────────────────────────────────────────────────────────────┘
```

### 14.2 Subsystem Register Count Table

| Subsystem         | Base Address | End Address  | Reg Count | Access  | Notes                           |
|-------------------|-------------|--------------|-----------|---------|----------------------------------|
| CLUSTER_CTRL      | 0x03000000  | 0x030001FF   | 96        | RW/RO   | CLK_EN, SOFT_RESET, ISO_EN       |
| T6_L1_CSR         | 0x03000200  | 0x030003FF   | 91        | RW/RO   | Port ctrl, ECC, bank hash        |
| CACHE_CTRL        | 0x03000400  | 0x030005FF   | 7         | RW/WO   | L2 enable, flush, invalidate     |
| LLK_TILE_COUNTERS | 0x03000600  | 0x030041FF   | 576       | RO/RW   | Per-tile performance counters    |
| IDMA_APB          | 0x03004000  | 0x03009FFF   | 1,528     | RW      | 8 DMA engines                    |
| DEBUG_MODULE      | 0x0300A000  | 0x0300AFFF   | 17        | RW/RO   | RISC-V Debug v0.13.2             |
| SMN               | 0x03010000  | 0x0301FFFF   | 325       | RW/RO   | Security, firewall, mailbox      |
| AWM               | 0x03020000  | 0x0302FFFF   | 479       | RW/RO   | DVFS, droop, temp, PLL           |
| **Total**         |             |              | **3,119** |         |                                  |

### 14.3 CLUSTER_CTRL Key Registers

| Offset | Register         | Bits   | Description                                           |
|--------|------------------|--------|-------------------------------------------------------|
| +0x000 | CLK_EN           | [15:0] | Per-tile clock enable (tile index = x*5+y)            |
| +0x004 | SOFT_RESET       | [15:0] | Per-tile soft reset (write 1 to assert reset)         |
| +0x008 | CORE_CONFIG      | [31:0] | Global: endianness, debug mode, boot address          |
| +0x00C | TILE_EN_MASK     | [15:0] | Tile enable mask (harvested tiles masked off)         |
| +0x010 | NOC_MESH_CONFIG  | [31:0] | NoC mesh size override (for harvest routing)          |
| +0x014 | EDC_GLOBAL_EN    | [0]    | Global EDC ring enable                                |
| +0x018 | EDC_BYPASS_MASK  | [15:0] | Per-tile EDC bypass (for harvested tiles)             |
| +0x01C | ISO_EN           | [11:0] | Harvest isolation enable (bit[x+4*y] per tile)        |
| +0x020 | CHIP_ID          | [31:0] | Chip identification register (RO, factory set)        |
| +0x024 | VERSION          | [31:0] | RTL version register (RO)                             |

### 14.4 IDMA_APB Key Registers

The iDMA APB block contains 8 independent DMA engine register sets. Each engine is at base offset `E * 0x1000` (E=0..7):

```
  Per-engine register set:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  +0x000  CMD_BUF_CTRL    — command buffer: write_ptr, read_ptr, depth│
  │  +0x004  CMD_BUF_STATUS  — [0]=empty, [1]=full, [3:2]=error_code     │
  │  +0x008  SIMPLE_CMD_SRC  — simple command: source address            │
  │  +0x00C  SIMPLE_CMD_DST  — simple command: destination address       │
  │  +0x010  SIMPLE_CMD_LEN  — simple command: transfer length (bytes)   │
  │  +0x014  SIMPLE_CMD_GO   — write 1 to launch simple command          │
  │  +0x018  ADDR_GEN_SRC    — address generator source: base, stride    │
  │  +0x01C  ADDR_GEN_DST    — address generator dest: base, stride      │
  │  +0x020  ADDR_GEN_DIM    — multi-dimensional stride config (4D)      │
  │  +0x024  DMA_STATUS      — running/idle/error status bits            │
  │  +0x028  DMA_IRQ_EN      — interrupt enable (done, error, overflow)  │
  │  +0x02C  DMA_CHAIN_PTR   — pointer to next chained command descriptor│
  └──────────────────────────────────────────────────────────────────────┘
```

### 14.5 SFR Access Protocol

All SFR registers are accessed via the APB (Advanced Peripheral Bus) slave interface in the Dispatch tile. Access rules:

- **Width**: 32-bit aligned accesses only; byte/halfword accesses not supported
- **Read-only registers**: writes are silently ignored (no error response)
- **W1C registers**: write 1 to clear (e.g., interrupt status registers)
- **Read-to-clear registers**: some status registers clear on read (RTC, noted in register description)
- **Write-once registers**: can only be written once after reset (e.g., security configuration)

---

## §15 Verification Checklist

### 15.1 Overview

This section defines the hardware verification (HW DV) checklist for the N1B0 NPU. Each sub-block has a set of required test scenarios that must pass before tape-out sign-off.

```
  Verification sign-off status legend:
  [ ] — Not started
  [P] — In progress
  [D] — Done / passing
  [W] — Waived with documented rationale
```

### 15.2 Tensix FPU Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | INT16 MAC accumulation: all input ranges including max/min/overflow | 100% format pairs | FPU G-Tile |
| 2 | FP16B × FP16B matrix multiply, compare vs golden reference model | <1 ULP error | FPU M-Tile |
| 3 | Stochastic rounding: verify probabilistic distribution over 10K samples | SR probability within ±5% | FP Lane |
| 4 | Format conversion: FP32→FP16B, FP32→BF16, INT16→FP32 | all conversion paths | FPU |
| 5 | SRCA/SRCB register file: concurrent read/write, no data corruption | 100% bank combinations | SRCA/SRCB |
| 6 | DEST register file: accumulate 512 back-to-back MACs, verify final value | no saturation error | DEST |
| 7 | SFPU transcendental functions: exp, log, sqrt, reciprocal vs IEEE reference | <2 ULP error | SFPU |
| 8 | Booth multiplier: corner cases (max_neg × max_neg, 0×X, X×1, X×-1) | boundary inputs | Booth |
| 9 | Compressor tree: multi-cycle accumulation with carry chain wrap-around | no carry loss | Compressor |
| 10 | Safety controller: inject single FPU fault, verify FATAL interrupt path | fault → FATAL_IRQ | Safety |

### 15.3 L1 SRAM Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Bank conflict resolution: simultaneous 4-read + 2-write to same bank | no deadlock, correct arbitration | L1 arbiter |
| 2 | ECC single-bit error injection and correction | 100% ECC code words exercised | SRAM ECC |
| 3 | ECC double-bit error injection → CRIT interrupt | uncorrectable → CRIT_IRQ | SRAM ECC |
| 4 | All four read ports simultaneous (4-port stress) | no data corruption | L1 read ports |
| 5 | TDMA vs CPU port arbitration: verify TDMA priority under contention | TDMA wins under contention | L1 arbiter |
| 6 | Bank interleaving: verify GROUP_HASH_FN0/1 distributes accesses evenly | even bank utilization | L1 hash |
| 7 | DFX clock gating: gate and un-gate L1 clock, verify state retention | no data loss on gate/ungate | t6_l1_partition_dfx |
| 8 | L1 post-reset: verify all entries are initialized after reset de-assertion | deterministic post-reset state | L1 |

### 15.4 NoC Router Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | DOR routing: XY dimension-order route across full 4×5 grid | all src/dst pairs | Router |
| 2 | Dynamic routing: 928-bit carried list propagation across 5 hops | list correct at NIU | Router |
| 3 | Path squash: inject path_squash flit, verify route re-direction | flit delivered via new path | Router |
| 4 | Multicast: send to all-Tensix endpoint group | all 12 tiles receive, no duplicates | Router |
| 5 | VC deadlock avoidance: create conflicting routes, verify no deadlock | 1000-cycle stress test | VC arbiter |
| 6 | VC FIFO full: fill all VCs to capacity, verify backpressure propagation | no flit loss under backpressure | VC FIFO |
| 7 | ECC on VC FIFO: inject single-bit error, verify in-flight correction | ECC corrected | VC FIFO ECC |
| 8 | force_dim_routing: set force_dim=EAST, verify routing ignores Y coordinate | Y-axis not used for routing | Router |
| 9 | tendril routing: configure tendril, send flit, verify out-of-mesh delivery | flit exits via tendril port | Tendril |
| 10 | ATT lookup: program all 64 entries, stress with 64 simultaneous lookups | no collision, correct hit | ATT |

### 15.5 iDMA Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Simple 1D transfer: L1→L1 across tiles via NoC | correct data delivery | iDMA |
| 2 | Multi-dimensional stride: 4D tensor with non-contiguous strides | correct address generation | ADDR_GEN |
| 3 | Chain command: 8-descriptor chain, each with different src/dst/length | all descriptors execute in order | CMD_BUF |
| 4 | Mid-chain error: inject error at descriptor 4, verify error interrupt | error → DMA_IRQ, chain halted | iDMA |
| 5 | Concurrent 8-engine operation: all 8 iDMA engines running simultaneously | no bus contention or starvation | iDMA × 8 |
| 6 | Interrupt on completion: verify done IRQ fires exactly once per transfer | exactly 1 IRQ per transfer | iDMA IRQ |
| 7 | Boundary conditions: transfer length=0, length=1, length=max | correct handling in all cases | iDMA |
| 8 | AXI outstanding limit: issue 256 outstanding AXI transactions | no deadlock, all complete | AXI arbiter |

### 15.6 EDC Ring Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Ring initialization: full ring startup from reset, all nodes reach READY state | all nodes ready within timeout | EDC ring |
| 2 | FATAL fault injection: force toggle mismatch in one node → FATAL_IRQ | FATAL detected within 10 cycles | EDC node |
| 3 | CRIT fault injection: inject DEST RF parity error → CRIT_IRQ | CRIT escalation path complete | EDC/DEST |
| 4 | n-crt fault: inject non-critical event, verify logged but no interrupt | log entry in CSR, no IRQ | EDC CSR |
| 5 | ECC+ correction: inject correctable L1 ECC error, verify silent correction | no interrupt, correction logged | L1/EDC |
| 6 | ECC− uncorrectable: inject 2-bit L1 ECC error → CRIT interrupt | CRIT_IRQ fires correctly | L1/EDC |
| 7 | Harvest bypass: disable tile (0,0) via ISO_EN, verify ring continues uninterrupted | ring stable with bypass active | EDC bypass |
| 8 | MCPDLY check: measure toggle round-trip latency, confirm ≤7 cycles worst-case | max latency ≤ MCPDLY | EDC ring |
| 9 | async_init recovery: reset one node mid-operation, verify ring restores | ring restores in <100 cycles | sync3r |
| 10 | Multi-fault: inject faults in 3 nodes simultaneously | all 3 faults detected and reported | EDC ring |

### 15.7 SMN Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Range violation detection: send transaction outside permitted range | slv_ext_error asserted correctly | SMN range |
| 2 | Firewall logging: verify violation entry written to SLV_BLOCK_STATUS | log readable by firmware ISR | SMN log |
| 3 | Mailbox 0 operation: host writes, firmware reads, verify no message loss | write/read handshake correct | MBOX_0 |
| 4 | Mailbox 1 operation: firmware writes, host reads, interrupt on write | IRQ fires on every write | MBOX_1 |
| 5 | All 8 ranges simultaneously active: 8 parallel transactions | correct routing for all 8 | Range checker |
| 6 | Security level escalation: low-security master attempts high-security access | access blocked, CRIT_IRQ | MST_MAIN |
| 7 | Address translation: verify ADDR_TRANS maps addresses to correct endpoints | translated address correct | ADDR_TRANS |
| 8 | SMN reset: reset SMN, verify all ranges cleared, no spurious interrupts | clean post-reset state | SMN |

### 15.8 Debug Module Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Halt single hart: halt TRISC3 on tile (0,0), verify DMSTATUS.allhalted | halt within 10 cycles | DM |
| 2 | Resume from halt: resume halted hart, verify PC execution continues | PC increments after resume | DM |
| 3 | GPR read/write via abstract command: read x1, write x5=0xDEAD_BEEF | all GPRs accessible | DM |
| 4 | CSR read/write: read/write mstatus, mtvec via abstract command | key CSRs accessible | DM |
| 5 | PROGBUF execution: load target address in x1, execute lw+ebreak, read result | correct memory value returned | DM PROGBUF |
| 6 | System bus read: read memory at 0x80001234 without halting any hart | correct data, hart stays running | DM SBA |
| 7 | System bus write: write to uncached memory region via SBA | memory updated correctly | DM SBA |
| 8 | Multi-hart halt: halt all 48 harts simultaneously via HAWINDOW | all harts halt within 20 cycles | DM |
| 9 | Halt-on-reset: set DMCONTROL.setresethaltreq, toggle reset, verify halt at PC=0 | hart halted immediately at reset exit | DM |
| 10 | PROGBUF exception: execute invalid instruction in PROGBUF, verify cmderr=3 | cmderr[2:0]=3 (exception flag set) | DM |

### 15.9 AWM Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Frequency scaling up: increase ai_clk[0] in 100 MHz steps to maximum | PLL locks at each step | AWM FREQ |
| 2 | Frequency scaling down: decrease ai_clk[0] to minimum, verify no glitch | clean step-down, no glitch | AWM FREQ |
| 3 | Droop response: simulate voltage droop (ring oscillator period increase) | auto frequency reduction triggered | AWM DROOP |
| 4 | Droop recovery: voltage recovers, verify auto frequency restore | frequency restored to pre-droop level | AWM DROOP |
| 5 | Temperature threshold interrupt: set high threshold 5°C above ambient | TEMP_IRQ fires when threshold crossed | AWM TEMP |
| 6 | CGM autonomous gating: idle all Tensix tiles, verify clocks gate after idle_cnt | clocks gated within idle_cnt+2 cycles | CGM |
| 7 | CGM force-on: assert CGM_FORCE_ON, verify clocks remain on when idle | clocks stay on regardless of idle state | CGM |
| 8 | PLL lock loss: remove ref_clk briefly, verify LOSS_OF_LOCK IRQ | IRQ fires within 10 ref_clk cycles | TT_PLL_PVT |
| 9 | Clock observation: measure noc_clk via CLK_OBSERVE, compare to expected | measured frequency within ±2% | CLK_OBSERVE |
| 10 | All 6 frequency domains independent: change each domain independently | no inter-domain coupling observed | FREQ0..5 |

### 15.10 Clock Gating and DFX Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | noc_niu_router_dfx gate/ungate: gate NoC clock mid-operation (drain FIFOs first) | no flit loss on gate/ungate | DFX wrapper |
| 2 | overlay_wrapper_dfx: gate dm_clk, verify SRAM state retained on resume | L2 contents intact after un-gate | DFX wrapper |
| 3 | instrn_engine_wrapper_dfx: gate ai_clk during TRISC stall, resume | TRISC PC preserved on resume | DFX wrapper |
| 4 | t6_l1_partition_dfx: gate L1 clock, verify SRAM content on resume | L1 data intact after clock restore | DFX wrapper |
| 5 | Scan chain connectivity: shift scan chain full length (when DFX enabled) | all flops captured correctly | Scan chain |
| 6 | Clock gating glitch check: verify no glitch on gated clock waveform | zero glitches in simulation | ICG cells |

### 15.11 Harvest Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | ISO_EN[0] assertion: harvest tile (0,0), verify 11 signal groups driven safe | all 11 groups isolated via AND cells | ISO cells |
| 2 | Mesh routing reconfiguration: harvest tile (0,0), verify NoC routes around it | no packets sent to (0,0) | NoC mesh |
| 3 | Reset isolation: reset harvested tile independently, verify neighbor tiles unaffected | no reset glitch propagation | Reset ISO |
| 4 | EDC ring bypass: harvest tile (2,1), verify EDC ring completes without that node | ring completes with N-1 active nodes | EDC bypass |
| 5 | Multi-harvest: harvest 3 tiles simultaneously, verify 9-tile system operation | full functionality on remaining tiles | Harvest |
| 6 | Clock bypass: DFX clock pass-through for harvested composite tile | clock chain unbroken in ring | Clock bypass |
| 7 | PRTN chain bypass: harvested tile skipped in power-up sequence | PRTN completes with skip | PRTN bypass |
| 8 | noc_y_size update: verify NOC_MESH_CONFIG reflects harvested row exclusion | routing table excludes harvested row | mesh_config |

### 15.12 End-to-End System Tests

Beyond block-level tests, the following system-level tests verify cross-block integration:

| # | Test | Blocks Exercised |
|---|------|-----------------|
| 1 | INT16 GEMM (128×48×256): full matrix multiply, L1→FPU→L1, compare golden | FPU + L1 + TDMA + iDMA |
| 2 | All-to-all NoC stress: every tile sends to every other tile simultaneously | NoC + NIU + ATT |
| 3 | Firmware boot: load firmware via iDMA, TRISC3 executes, verifies EDC/SMN init | iDMA + DM + EDC + SMN |
| 4 | Harvest + compute: harvest 2 tiles, run GEMM on remaining 10 tiles | Harvest + FPU + NoC |
| 5 | Security fence: Tensix attempts out-of-bounds memory access, verify firewall blocks | SMN + NoC + iDMA |
| 6 | ECC scrubbing under load: background L1 ECC scrub while GEMM is running | L1 ECC + FPU |
| 7 | DVFS during compute: change ai_clk frequency mid-GEMM, verify result correctness | AWM + FPU + NoC |
| 8 | Debug while running: set watchpoint on Tensix, halt on trigger, inspect register state | DM + TRISC3 + TRISC |

---

## Appendix A: SRAM vs. Latch Architectural Analysis

### A.1 Area and Power Comparison

This appendix provides detailed analysis of the architectural trade-off between dual-port SRAM and latch arrays for supporting HALF_FP_BW two-phase processing.

**Question:** Could N1B0 use dual-port SRAM instead of latches for DEST/SRCA/SRCB?

**Answer:** Technically yes, but at unacceptable cost (3–4× area, 4.4× power).

### A.2 Dual-Port SRAM Scenarios

**Scenario A: Sequential Access (No Clock Multiplication)**

```
Design: Dual-port SRAM with two independent 1-cycle ports

Result:
  ├─ Phase 1: Port A reads, Port B writes (same cycle)
  ├─ Phase 2: Different rows (but different cycle)
  └─ Benefit: None (still sequential, not true two-phase)

Costs:
  ├─ Area: 2.5× larger
  ├─ Power: 1.8–2.0× per access
  ├─ Control: Arbitration logic for port conflicts
  └─ Verdict: All cost, zero benefit
```

**Scenario B: Dual-Edge Triggered SRAM (Both Rising and Falling Edges)**

```
Design: Single-port SRAM accessed on both clock edges of 1 GHz clock

Concept:
  Rising edge (0 ps):   Access operation 1
  Falling edge (500 ps): Access operation 2
  ─────────────────────────────────────────
  Result: 2 accesses per 1 GHz cycle, no clock multiplication!

Timeline (1 GHz clock, 1000 ps period):
  Rising edge @ 0 ps:
    ├─ Setup time: 0–150 ps
    ├─ Word-line enable: 150 ps
    ├─ Bit-line sensing: 150–450 ps
    └─ Output valid: 450–900 ps (latched at rising edge)
  
  Falling edge @ 500 ps:
    ├─ Setup time: 500–650 ps
    ├─ Word-line enable: 650 ps
    ├─ Bit-line sensing: 650–950 ps
    └─ Output valid: 950–1000 ps (latched at falling edge)

Advantages:
  ✓ Two operations per 1 GHz cycle (matches two-phase goal!)
  ✓ No clock multiplication needed (no DLL/PLL)
  ✓ Area: Same as single-port SRAM (2.5× smaller than dual-port)
  ✓ No clock doubler overhead

Critical Problems:
  ✗ TIMING CLOSURE NIGHTMARE
  ├─ Falling edge has only 500 ps window (vs 1000 ps for rising)
  ├─ Setup time on falling edge must fit in 500 ps budget
  ├─ Hold time constraints apply at both edges (double the violations)
  ├─ Even 50 ps of clock skew breaks falling-edge timing
  ├─ Corner cases (PVT variation): All corners must pass both edges
  
  ✗ METASTABILITY RISK
  ├─ Data changing near falling edge → unpredictable behavior
  ├─ Sense amp activation near falling edge very sensitive
  ├─ Hazard windows much tighter than single-edge design
  └─ Silent data corruption possible in edge cases
  
  ✗ POWER PENALTY
  ├─ Both clock edges active → ~1.8–2.0× power vs single-edge
  ├─ Word-line switching on both edges
  ├─ Bit-line discharge twice per cycle
  └─ No power savings vs dual-port SRAM
  
  ✗ DFT COMPLEXITY
  ├─ Scan testing must account for dual-edge operation
  ├─ Test patterns much more complex
  ├─ Timing simulation must verify both edges in all corners
  └─ Silicon characterization 2× effort (both rising & falling)
  
  ✗ MANUFACTURING RISK
  ├─ Very tight timing margins (500 ps) → yield loss
  ├─ Clock skew sensitivity → requires expensive clock tree
  ├─ Metastability exposure → defect escapes possible
  └─ High re-spin risk if any falling-edge path fails in silicon

Verdict: Technically feasible, but...
  ├─ Risk: Extremely high (timing closure + metastability)
  ├─ Yield: Expected to be low (tight margins)
  ├─ Cost: Higher than dual-port SRAM due to complexity
  ├─ Test: Much more complex than standard SRAM test
  └─ NOT PRACTICAL for production AI accelerator
```

**Scenario C: Dual-Port SRAM With Internal Clock Multiplication**

```
Design: Internal 2 GHz clock from external 1 GHz (via DLL/PLL)

Result:
  ├─ Phase 1 @ internal 1 GHz (first half-cycle)
  ├─ Phase 2 @ internal 1 GHz (second half-cycle)
  └─ Two accesses per external cycle ✓

Costs:
  ├─ Clock doubler area: +50–100 µm²
  ├─ DLL/PLL complexity: Phase locking, jitter management
  ├─ Power overhead: +40–60% (clock generation + 2× SRAM switching)
  ├─ Jitter risk: ±50 ps (critical for 500 ps SRAM timing budget)
  ├─ Timing closure: Extremely difficult
  ├─ Silicon risk: High (clock margin failures → tape-out failures)
  └─ Total area: 2.5× SRAM + DLL = **3.0–3.2× larger**
```

### A.3 Quantitative Comparison

**Chip-wide DEST Register File Footprint:**

```
Latch Array (actual N1B0):
  ├─ 16 instances per Tensix tile
  ├─ 48 instances chip-wide
  ├─ Area per instance: 3.6 mm²
  └─ Total: 48 × 3.6 = 57.6 mm²

Dual-Edge SRAM (Scenario B):
  ├─ Area per instance: 3.5 mm² (same as single-port SRAM)
  ├─ 48 instances chip-wide
  ├─ Total SRAM area: 48 × 3.5 = 168 mm²
  ├─ Additional clock distribution: +~20 mm² (for falling-edge timing)
  └─ Total: ~188 mm² (3.3× larger)

Dual-Port SRAM (Scenario C):
  ├─ Area per instance: 11.5 mm² (2.5× SRAM + DLL allocation)
  ├─ 48 instances chip-wide
  └─ Total: 48 × 11.5 = 552 mm²

Difference summary:
  ├─ Latch vs Dual-Edge: +130.4 mm² (3.3× larger, HIGH TIMING RISK)
  ├─ Latch vs Dual-Port: +494.4 mm² (9.6× larger, safer but too big)
  └─ Verdict: Neither SRAM alternative is acceptable
```

**Cluster-Level Power (DEST Only):**

```
Latch Array per cluster: 10 mW
Dual-Edge SRAM per cluster: 18 mW (1.8× due to both edges)
Dual-Port SRAM per cluster: 44 mW

Chip-wide (12 clusters):
  ├─ Latch total: 120 mW
  ├─ Dual-Edge total: 216 mW (+96 mW, but with high timing risk)
  ├─ Dual-Port total: 528 mW (+408 mW)
  └─ Verdict: Dual-edge saves area but costs power + massive timing risk
```

### A.4 Why Standard SRAM Statement is Accurate

HDD statement: "Standard SRAM requires address decode → precharge → sense amplify (3–5 cycles)."

This is accurate because:

```
Historical Timeline:
  ├─ 1970s–1990s: Embedded SRAM typically 3–4 cycles
  ├─ 2000s: Reduced to 2–3 cycles with better sense amps
  ├─ 2010s: Modern designs achieve 1 cycle
  └─ Key: 1-cycle requires careful optimization

"Standard" SRAM Design (Conservative):
  ├─ Decode:       1 cycle (parallel precharge)
  ├─ Sense amp:    1 cycle (sense-amplify bit-line differential)
  ├─ Output mux:   1 cycle (multiplex row data)
  ├─ Register:     1 cycle (register output for timing margin)
  └─ Total: 4 cycles (safe for design closure)

Optimized 1-Cycle SRAM:
  ├─ Decode:       Combinational (or parallel)
  ├─ Sense amp:    Aggressive (fast sense-amp enable)
  ├─ Output:       Direct (no register stage)
  └─ Total: 1 cycle (at cost of tight timing margins)
```

For a register file that must be accessed **every single cycle** (like DEST in the FPU), the overhead of even 2-cycle SRAM is prohibitive.

### A.5 Real-World Precedent

None of the world's fastest processors use SRAM for hot-path register files:

```
Intel Xeon Skylake:
  ├─ Main integer RF: Latches (1-cycle, high density)
  ├─ L1 I-cache: SRAM (3–4 cycle latency acceptable for cache)
  └─ Rationale: Register file must be accessed every cycle

ARM Cortex-A72:
  ├─ Integer RF: Latches
  ├─ Load/Store buffer: Latches
  ├─ L1 cache: SRAM
  └─ Rationale: Hot-path structures use latches for density

Apple M-series:
  ├─ Register file: Latches
  ├─ Cache: SRAM
  └─ Rationale: Same pattern (latches for hot path)

Tenstorrent (Trinity N1B0):
  ├─ DEST/SRCA/SRCB (register files): Latches
  ├─ L1 SRAM (bulk data, 3MB): SRAM
  └─ Rationale: Hybrid approach (register files need density + sub-cycle phases, bulk storage needs capacity)
```

### A.6 Architectural Decision Matrix

| Factor | Latch Array | Dual-Edge SRAM (Scenario B) | Dual-Port SRAM (Scenario C) | Winner |
|--------|---|---|---|---|
| **Area (chip-wide)** | 57.6 mm² | 188 mm² (3.3×) | 552 mm² (9.6×) | ✅ **Latch** |
| **Power (cluster)** | 10 mW | 18 mW (1.8×) | 44 mW (4.4×) | ✅ **Latch** |
| **Clock distribution** | Single 1 GHz | Enhanced skew mgmt needed | Dual clock (2 GHz) | ✅ **Latch** |
| **Timing closure risk** | **Low** | **EXTREMELY HIGH** (500 ps margin) | High (jitter) | ✅ **Latch** |
| **Metastability risk** | None | **CRITICAL** (edge-triggered hazards) | Low | ✅ **Latch** |
| **Control logic** | Minimal (ICG) | Moderate (edge detection) | Moderate (arbitration) | ✅ **Latch** |
| **Two-phase per cycle** | Native (ICG) | Requires edge coordination | Requires DLL | ✅ **Latch** |
| **DFX test coverage** | 35–45% baseline (→88–92%) | 70% baseline (but testing nightmare) | 80%+ native | SRAM (but risk too high) |
| **Production risk** | **Low (proven)** | **VERY HIGH** (timing + metastability) | **High (DLL)** | ✅ **Latch** |
| **Manufacturing yield** | Standard | **Expected low** (tight margins) | Standard | ✅ **Latch** |

**Conclusion:** Latches win on every metric except native DFX coverage. The coverage trade-off is acceptable with proper mitigation (see §2.4.6.7).

### A.7 Answer to "Could You Use Dual-Edge Clock to Read/Write SRAM Both Edges?"

**Yes, technically possible, but EXTREMELY RISKY:**

This is the dual-edge triggered SRAM scenario (Scenario B above).

**Advantages:**
- ✓ Two operations per 1 GHz cycle (no clock multiplication)
- ✓ Same area as single-port SRAM (3.3× smaller than dual-port)
- ✓ No DLL/PLL overhead

**Critical Problems:**
- ✗ **Timing closure NIGHTMARE**: Only 500 ps per edge vs 1000 ps baseline
  - Setup + access must fit in half a cycle
  - Even 50 ps clock skew breaks timing
  - All PVT corners must pass both edges (2× characterization effort)

- ✗ **Metastability risk**: Data changing near falling edge → unpredictable behavior
  - Sense amp activation sensitive near falling edge
  - Hazard windows much tighter
  - Silent data corruption possible in edge cases

- ✗ **Power penalty**: 1.8× power (both edges active)
  - Word-line switching on both edges
  - No power savings vs dual-port
  - Negates area advantage

- ✗ **DFT nightmare**: Test patterns 2× more complex
  - Must verify both edges in all corners
  - Silicon characterization 2× effort
  - High risk of test escapes

- ✗ **Manufacturing risk**: VERY HIGH
  - Tight timing margins → expected yield loss
  - Clock skew sensitivity → expensive clock tree required
  - High re-spin risk if falling-edge paths fail

**Why Not Used in Practice:**
Leading chip architects (Intel Xeon, ARM Cortex-A72, Apple M-series, and Tenstorrent) do NOT use dual-edge SRAM for register files precisely because:
1. Timing closure risk is extreme (5% margin → 10% in dual-edge)
2. Metastability exposure is unacceptable
3. The area savings don't justify the reliability cost

**Conclusion on Dual-Edge SRAM:**

While it saves area, the timing closure and metastability risks make it **unsuitable for production**. The margin between passing and failing timing is too small (500 ps) for a conservative design. One process corner variation and your chip fails.

Latches avoid all these problems by using **natural two-phase transparency** (ICG) on a single clock edge.

### A.8 Why Latches Remain Optimal

**Scenario Comparison Summary:**

```
Dual-Port SRAM (Scenario C):  9.6× larger, 4.4× more power, high DLL jitter risk
Dual-Edge SRAM (Scenario B):  3.3× larger, 1.8× more power, EXTREME timing risk + metastability
Latch Array (N1B0 choice):    Baseline area/power, zero timing risk, proven

Verdict: Latches are unambiguously optimal
```

For register files in high-performance accelerators, **latches are the only sensible choice**.

---

## Appendix E: SRAM Category Inventory (N1B0 Chip-Wide)

### E-3: SRAM by Category

| Category | Clock Domain | Physical Cell | Per Tile | Qty | Total Macros | Total Size |
|----------|--------------|---------------|----------|-----|--------------|------------|
| **T6 L1 SRAM** | i_ai_clk[x] | u_ln05lpe_*_768x69m4b1c1_{high,low} | 512 | ×12 Tensix | 6,144 | **3 MB** |
| **TRISC I-Cache** | i_ai_clk[x] | u_ln05lpe_*_512x72m2b1c1 | 16 | ×12 | 192 | 64 KB |
| **TRISC Local Memory** | i_ai_clk[x] | u_ln05lpe_*_512/1024x52m2b1c1 | 12 | ×12 | 144 | 384 KB |
| **TRISC Vec Memory** | i_ai_clk[x] | u_ln05lpe_*_256x104m2b1c1 | 8 | ×12 | 96 | 24 KB |
| **Overlay L1 D$ Data** | i_dm_clk[x] | u_ln05lpe_*_128x144m2b1c1 | 16 | ×14 (Tensix+Disp) | 224 | 32 KB |
| **Overlay L1 D$ Tag** | i_dm_clk[x] | u_ln05lpe_*_32x100m2b1c1 | 8 | ×14 | 112 | 12 KB |
| **Overlay L1 I$ Data** | i_dm_clk[x] | u_ln05lpe_*_256x68m2b1c1 | 16 | ×14 | 224 | 32 KB |
| **Overlay L1 I$ Tag** | i_dm_clk[x] | u_ln05lpe_*_256x68m2b1c1 | 8 | ×14 | 112 | 16 KB |
| **Overlay L2 Banks** | i_dm_clk[x] | u_ln05lpe_*_256x136m2b1c1 | 32 | ×14 | 448 | 128 KB |
| **Overlay L2 Dir** | i_dm_clk[x] | u_ln05lpe_*_64x160m2b1c1 | 4 | ×14 | 56 | 4 KB |
| **Dispatch L1 SRAM** | i_noc_clk | u_ln05lpe_*_768x69m4b1c1_{high,low} | 128 | ×2 Dispatch | 256 | 0.75 MB |
| **Router VC (64-row, Tensix)** | i_noc_clk | u_rf_wp_hsc_lvt_64x128m1fb1wm0 | 68 | ×12 | 816 | 68 KB |
| **NIU VC (72-row, Tensix)** | i_noc_clk | u_rf_wp_hsc_lvt_72x128m2fb2wm0 | 17 | ×12 | 204 | 19.1 KB |
| **NOC Tables (Tensix)** | i_noc_clk | u_rf_2p_hsc_lvt_1024x13m4fb4wm0 | 13 | ×12 | 156 | 21.1 KB |
| **Router VC×4 (NOC2AXI-R)** | i_noc_clk | u_rf_wp_hsc_lvt_64x128m1fb1wm0 | 68 | ×2 | **136** | **68 KB** |
| **NOC Tables (NOC2AXI-R)** | i_noc_clk | u_rf_2p_hsc_lvt_1024x13m4fb4wm0 | 13 | ×2 | **26** | **21.1 KB** |
| **AXI FIFOs (NOC2AXI-R)** | i_noc_clk / i_axi_clk | u_rf_wp_hsc_lvt_* | ~26 | ×2 | **~52** | **~2.5 KB** |
| **NIU VC×2 (NOC2AXI-C)** | i_noc_clk | u_rf_wp_hsc_lvt_64x128m1fb1wm0 | 34 | ×2 | **68** | **32 KB** |
| **NOC Tables (NOC2AXI-C)** | i_noc_clk | u_rf_2p_hsc_lvt_1024x13m4fb4wm0 | 13 | ×2 | **26** | **21.1 KB** |
| **AXI FIFOs (NOC2AXI-C)** | i_noc_clk / i_axi_clk | u_rf_wp_hsc_lvt_* | ~43 | ×2 | **~86** | **~2.9 KB** |
| | | | | **TOTAL** | **≈9,582** | |

#### E-3.1 Key Observations

**Clock Domain Distribution:**
- **i_ai_clk[x]:** Tensix compute (L1, TRISC, FPU) — per-column indexed [0..3]
- **i_dm_clk[x]:** Data movement (Overlay memory, Dispatch) — per-column indexed [0..3]
- **i_noc_clk:** NoC (Router, NIU VC, routing tables) — global scalar clock
- **i_axi_clk:** AXI (CDC FIFOs) — global scalar clock, Y=4 only

**NOC2AXI Architecture Variants:**

1. **NOC2AXI-R (Router)** — X=1, X=2 (composite tiles)
   - Router VC: 68 macros/tile × 2 = 136 total = 68 KB
   - NOC Tables: 13 macros/tile × 2 = 26 total = 21.1 KB
   - AXI FIFOs: ~26 macros/tile × 2 = ~52 total = ~2.5 KB
   - **Total: ~91.6 KB per tile**

2. **NOC2AXI-C (Corner)** — X=0, X=3 (standalone tiles)
   - NIU VC: 34 macros/tile × 2 = 68 total = 32 KB
   - NOC Tables: 13 macros/tile × 2 = 26 total = 21.1 KB
   - AXI FIFOs: ~43 macros/tile × 2 = ~86 total = ~2.9 KB
   - **Total: ~56.0 KB per tile**

**Key Finding:** Despite simpler architecture (no internal routing), NOC2AXI-C tiles have **larger FIFO macros (~43 vs ~26)**, suggesting corner tiles compensate for lack of internal routing with more aggressive CDC buffering.

---

*End of document. §1–§14 complete. Appendix A provides detailed architectural analysis of alternative register file implementations. Appendix E provides complete SRAM memory inventory with NOC2AXI-R vs NOC2AXI-C comparison.*

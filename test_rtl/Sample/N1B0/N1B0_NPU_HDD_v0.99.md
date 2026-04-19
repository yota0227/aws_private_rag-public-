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
- §3  NOC2AXI Composite Tiles (§3.7 NIU DMA Operation)
- §4  Dispatch Tiles
- §5  NoC Router
- §6  iDMA Engine
- §7  EDC Ring
- §8  Harvest and Power Domains  *(placeholder — second half)*
- §9  Clock Architecture          *(placeholder)*
- §10 Reset Architecture          *(placeholder)*
- §11 SFR / Register Map          *(placeholder)*
- §12 DFX and Scan Infrastructure *(placeholder)*
- §13 Physical Implementation Notes *(placeholder)*
- §14 Verification and Firmware Test Suite *(placeholder)*

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
- A **TDMA** (Tile DMA) engine with pack/unpack engines and a **MOP sequencer** — MOP (Micro-Operation Packet) is the compressed instruction format used by TRISC2 to drive the FPU and data-movement hardware. One MOP word encodes an entire tensor operation (target unit, operand source, DEST range, loop count) that would require hundreds of raw RISC-V instructions. See §2.7.3 for full detail.
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
│  │  │ RV32I  │  │  TRISC0 (pack)   │  │                      │ │  │ T3 data/   │ │
│  │  │ mgmt   │  │  TRISC1 (unpack) │  │  G-Tile[0] G-Tile[1] │ │  │ workspace  │ │
│  │  │        │  │  TRISC2 (math)   │  │  ┌───────┐ ┌───────┐ │ │  │ 0x06000    │ │
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
│  │  │  64 KB       │ │  6 KB       │ │                          │                 │
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
The Tensix compute tile is the fundamental tensor-processing engine of N1B0, bringing together specialized hardware for matrix multiply, data movement, and local control. Each of the 12 Tensix clusters (`tt_tensix_with_l1`) integrates a dual-G-Tile FPU capable of 256 concurrent multiply-accumulate lanes, multi-threaded TRISC processor cores, dedicated TDMA hardware with MOP-sequenced instruction compression, and a 3 MB on-cluster L1 SRAM. This integrated design decouples compute-heavy tensor math from data-movement logistics, enabling firmware to overlap weight/activation transport with FPU execution while maintaining high computational throughput.

### Design Philosophy
Tensix prioritizes **parallelism over serialization**. Unlike traditional RISC-V CPU designs where an instruction fetch-execute-memory pipeline serializes work, Tensix splits responsibilities: TRISC processors handle tile orchestration and control-flow decisions, while the FPU array executes tensor operations declared via MOP instructions — a compressed instruction format that encodes entire GEMM passes (hundreds of raw operations) into a single 32-bit word. This permits TRISC0/1 to prefetch weights and pack/unpack data via TDMA while TRISC2 is still feeding the previous MOP sequence to the FPU, creating a natural software pipeline. The 3 MB L1 per cluster (4× the baseline Trinity) provides sufficient capacity for typical weight tiles and KV-cache entries, reducing NoC pressure and latency-critical DRAM round-trips during inference.

### Integration Role
Tensix clusters are the compute backbone. Each cluster's local L1 memory forms the innermost level of N1B0's memory hierarchy: Tensix L1 → Overlay streams → NIU → AXI → external DRAM. Within a cluster, the overlay wrapper (`tt_neo_overlay_wrapper`) orchestrates data movement autonomously, allowing TRISC firmware to initiate DMA via CSR writes and continue without waiting. The FPU's 256 concurrent lanes are fed by:
- **Packed operands from L1**: 128-bit reads via the TDMA pack engine
- **Activation operands from L1**: stored during the previous layer's compute
- **Scalar instructions from TRISC2**: via the MOP sequencer, which maintains the outer-loop context (dimensions, accumulator addressing)

The DEST and SRCA register files hold intermediate results and source operands, respectively, acting as the "hot" working set to avoid repeated L1 reads within tight MAC loops.

### Key Characteristics
- **256 FP-Lanes per tile**: 2 G-Tiles × 8 M-Tiles × 8 rows × 2 lanes, all active in the same cycle with no serialization arbiter. Supports INT16, FP16B, INT8, and FP32 numeric formats via tag-bit selection at each lane.
- **MOP-sequenced math**: TRISC2 programs multi-iteration tensor operations via a single MOP; the sequencer autonomously drives the FPU for 50–150 cycles without further firmware intervention, including loop unrolling, format selection, and stochastic rounding.
- **4-threaded control**: TRISC0 (pack), TRISC1 (unpack), TRISC2 (math), TRISC3 (management) run in parallel with semaphore-based synchronization (SEMPOST/SEMGET custom instructions) to coordinate handoffs without blocking.
- **Dual-level data cache**: L1 SRAM (3 MB per cluster) is private and non-coherent but shared within the cluster; L2 may be shared across clusters via the overlay wrapper's context-switching mechanism.
- **Integrated TDMA**: Pack and unpack hardware reshape tensor data on-the-fly, transforming DRAM row-major layouts into the FPU's column-major working format without intermediate buffering.

### Use Case Example
**LLaMA 3.1 8B Inference — Weight Load and First Token Forward**  
Firmware running on TRISC3 issues a CSR write to the overlay stream controller: "Load 128 weight rows (K_tile=48 INT16 per row) from DRAM address 0x8A000000 to L1 offset 0x0000." TRISC0 (pack) polls the overlay completion flag, meanwhile TRISC2 has already begun a GEMM pass using weights pre-loaded in L1 from the prior layer. Once overlay confirms the 128 rows (24 KB) are in L1, TRISC1 (unpack) begins reformatting them into column-major layout for the next forward pass. TRISC2 sequences the first MOP for the weight×activation multiply, programming the MOP sequencer with source/dest register indices and loop count; the MOP sequencer fires 86 consecutive MOPs over ~4,100 cycles, issuing one `fpu_tag` per cycle to the FPU with no further TRISC involvement. By the time all 86 MOPs complete with `mop_done`, TRISC0 is already prefetching the next weight tile via overlay, overlapping latency-critical DRAM I/O with the FPU's multi-thousand-cycle GEMM.

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
| Instruction fetch (ICache) | 32-bit | L1 partition (IMEM region) | Yes — all 4 | Fetch program instructions from L1 |
| Local Data Memory (LDM) | **32-bit** | Private per-TRISC scratchpad SRAM | Yes — all 4 | Stack, firmware variables, loop counters |
| L1 direct read/write | **128-bit** | L1 partition (data region) | Yes — all 4 | Data load/store to cluster L1 |
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

TRISC3 has the same 4KB ICache size as TRISC0 because tile management firmware (interrupt handlers, boot sequences) is generally larger than the tight inner-loop LLK programs run by TRISC1/2.

### 2.3 TRISC Cores

#### 2.3.1 Overview and Rationale

N1B0 contains **four TRISC threads** (`THREAD_COUNT=4`): TRISC0, TRISC1, TRISC2, and TRISC3. Each TRISC is a lightweight, fixed-ISA processor — **not** a general-purpose RV32I core like TRISC3. The TRISC ISA is purpose-built for tensor data movement and FPU sequencing, with a highly compressed instruction encoding (MOP micro-ops) that achieves roughly 10× instruction density versus raw RISC-V equivalents.

**Why separate TRISCs rather than one core?**
Pack, unpack, and math are three parallel, independent pipelines that must interleave with cycle-accurate timing — e.g., while TRISC2 is computing tile N, TRISC1 must simultaneously be prefetching tile N+1 from L1 and TRISC0 must be writing tile N−1 to the NoC. Merging these onto a single core would require a complex scheduler and introduce pipeline hazards. Separate lightweight cores allow each pipeline stage to run at its own pace, controlled by hardware semaphore (sync barrier) handshakes rather than OS-level scheduling.

#### 2.3.2 Per-Thread Role Assignment

| Thread  | Primary Role            | Key Operation                                          | Clock Domain |
|---------|-------------------------|--------------------------------------------------------|--------------|
| TRISC0  | Pack engine             | Read DEST RF → format-convert → write L1 or NoC flit  | `i_ai_clk`   |
| TRISC1  | Unpack engine           | Read L1 or NoC flit → unpack → load SRCA/SRCB          | `i_ai_clk`   |
| TRISC2  | Math / FPU control      | Issue **MOP** (Micro-Operation Packet) sequences → G-Tile (with mode: fp32/int8/fp-lane). One MOP = one compressed instruction specifying operand sources, DEST range, and loop count. See §2.7.3. | `i_ai_clk`   |
| TRISC3  | Tile management / general control | NoC DMA control, interrupt dispatch, tile lifecycle, boot; `tt_risc_wrapper` RV32I | `i_ai_clk`   |

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
0x06000  TRISC0 IMEM  (pack LLK)
0x16000  TRISC1 IMEM  (unpack LLK)
0x26000  TRISC2 IMEM  (math LLK)
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
| TRISC1 (unpack) | Producer — fills SRCA/SRCB | Inner loop: `SEMPOST` after each tile load |
| TRISC2 (math)   | Consumer/producer — runs FPU MOP | Inner loop: `SEMGET` to wait for SRCA ready, `SEMPOST` when DEST ready |
| TRISC0 (pack)   | Consumer — reads DEST, writes output | Inner loop: `SEMGET` to wait for DEST ready |
| **TRISC3 (mgmt)** | **Orchestrator — not in the inner loop** | **Kernel boundaries only: signals kernel start/end, handles DMA completion, signals TRISC0/1/2 to begin/stop** |

TRISC3 uses a separate semaphore (e.g., `sem_kernel_start`) to tell TRISC0/1/2 when a new kernel is ready to execute, and waits on a `sem_kernel_done` posted by TRISC0 when the last output tile is packed. During the inner loop itself, TRISC3 runs independently — managing NoC DMA prefetch for the *next* kernel's weights while the current kernel executes.

**Standard 3-thread pipeline handshake (inner loop, TRISC0/1/2 only):**

```
TRISC1 (unpack)               TRISC2 (math)                TRISC0 (pack)
─────────────────             ─────────────────            ─────────────────
SEMINIT sem0, 0, 1            SEMINIT sem0, 0, 1
SEMINIT sem1, 0, 1                                         SEMINIT sem1, 0, 1

loop:                         loop:                        loop:
  load tile → SRCA/SRCB         SEMGET sem0  ← stalls        SEMGET sem1  ← stalls
  SEMPOST sem0  → unblocks        until TRISC1 posts           until TRISC2 posts
                                FPU MOP (math)               read DEST → L1
                                SEMPOST sem1  → unblocks      SEMPOST sem0 (optional)
```

- `sem0` gates the SRCA/SRCB → math handoff (TRISC1 produces, TRISC2 consumes)
- `sem1` gates the DEST → pack handoff (TRISC2 produces, TRISC0 consumes)
- TRISC2 `SEMGET sem0` hardware-stalls until TRISC1 executes `SEMPOST sem0`; no polling

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

TRISC3 posts `sem_kernel_start` once per TRISC0/1/2 (max_val=3) so all three threads unblock simultaneously. The inner loop then runs without TRISC3 participation. When TRISC0 finishes packing the last output tile, it posts `sem_kernel_done` so TRISC3 knows the kernel is complete.

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

| Memory Target | TRISC0 (pack) | TRISC1 (unpack) | TRISC2 (math) | TRISC3 (mgmt) | Access Mechanism |
|---------------|:---:|:---:|:---:|:---:|------------------|
| **L1 (instruction fetch)** | ✓ | ✓ | ✓ | ✓ | 32-bit ICache fetch; backed by L1 IMEM region |
| **L1 (data read/write)** | ✓ | ✓ | ✓ | ✓ | 128-bit direct port (`triscv_l1_rden/wren`) |
| **LDM (private scratchpad)** | ✓ | ✓ | ✓ | ✓ | 32-bit private SRAM (`trisc_ldm_*`); on-TRISC |
| **SRCA/SRCB register files** | — | ✓ (write, via unpack MOP) | ✓ (read, via FPU MOP) | — | TDMA MOP engine; not direct scalar load/store |
| **DEST register file** | ✓ (read, via pack MOP) | — | ✓ (write, via FPU MOP) | — | TDMA MOP engine; not direct scalar load/store |
| **FPU config registers** | — | — | ✓ (via cfg_reg bus) | ✓ (via cfg_reg bus) | 128-bit config register bus |
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
TRISC1 (unpack)           TRISC3 (mgmt)           TRISC0 (pack)
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
| Purpose | Pack loop variables, pointers, stack | Unpack loop state | Math MOP state | Interrupt stack, boot data |

The LDM is **not part of the L1 address space** — it is a small private SRAM inside the `tt_trisc` / `tt_risc_wrapper` module, accessed via `trisc_ldm_addr/rden/wren/wrdata/rddata` signals. Firmware programs store local variables (loop counters, base addresses, tile pointers) here without consuming L1 bandwidth.

TRISC0/3 have larger LDMs (4KB) because their roles — pack engine coordination and general tile management — involve more firmware state: TRISC0 maintains output tensor pointers and format conversion parameters; TRISC3 maintains interrupt handler stacks, boot-time initialization tables, and DMA command buffers.

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
| ② TRISC ↔ L1 | Bidirectional data | 128-bit per thread | **Tile computation data**: input activations, weight tiles, partial results, and output data that the TRISC must inspect or reformat. TRISC0 (pack) reads computed output from L1; TRISC1 (unpack) writes pre-fetched input data into L1; TRISC2 (math) reads MOP operands; TRISC3 reads/writes control structures. | Every clock cycle during active kernel execution. |
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
Per DEST column slice (tt_gtile_dest, NUM_COLS=1):
  TOTAL_ROWS_16B = 1024 rows per slice
  In INT32 mode (int8_op=1): 512 rows of 32-bit entries per bank

For 4 output rows × 16 output cols:
  DEST slots needed = 4 rows × 16 col slices = 64 INT32 entries
  DEST capacity     = 512 rows × 16 slices   = 8,192 INT32 entries per bank
  Status: ✓ 64 << 8,192 — DEST has ample space
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
  TRISC1 (unpack):
    Load 96 INT8 weight values from L1[weight_base + p × 96] → SRCA bank
    Pack 2 INT8 per 16-bit datum → 48 SRCA rows (INT8_2x format)

  TRISC2 (math):
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

  TRISC1 (unpack) simultaneously prefetches next SRCA slice into the
  opposite SRCA bank (double-buffer, §2.3.5)

  TRISC3 (mgmt): monitors barrier; TRISC0 does NOT pack during K loop
  ─────────────────────────────────────────────────
```

**After all 86 passes:**
- DEST holds the complete INT32 GEMM result: C[m,n] = sum_{k=0}^{8191} A[m,k] × B[k,n]
- TRISC2 executes `SEMPOST sem1` (hardware semaphore), signals TRISC0
- TRISC0 (pack): reads DEST INT32 → applies descale via FP-Lane → converts to FP16B → writes to L1 output buffer

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
| DEST capacity per bank (INT32) | 8,192 entries | 512 rows × 16 slices |

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
4. TRISC0 (pack) reads DEST and writes FP16B results to L1 or NoC

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

#### 2.6.3 Port Structure

The L1 partition exposes multiple independently addressable ports to support concurrent access from different agents:

| Port Class        | Count | Users                                               |
|-------------------|-------|-----------------------------------------------------|
| `RD_PORT`         | 8     | TRISC3 reads, TRISC reads, unpack engine input ports |
| `RW_PORT`         | 6     | Pack engine write-back, general TDMA read-modify    |
| `WR_PORT`         | 8     | NoC DMA write, pack engine output                   |

Bank selection is determined by address hashing. The hash function is configurable via `GROUP_HASH_FN0` / `GROUP_HASH_FN1` CSRs to allow tile programmers to tune bank conflict rates for specific tensor shapes.

#### 2.6.4 Address Map (Logical Layout within L1)

```
L1 Logical Layout (3MB total per cluster)
────────────────────────────────────────────────────
0x00000 – 0x05FFF   TRISC3 data region (24KB)
0x06000 – 0x15FFF   TRISC0 IMEM — pack LLK code (64KB region; 4KB ICache backed)
0x16000 – 0x25FFF   TRISC1 IMEM — unpack LLK code (64KB region; 2KB ICache backed)
0x26000 – 0x35FFF   TRISC2 IMEM — math LLK code (64KB region; 2KB ICache backed)
0x36000 – 0x45FFF   TRISC3 IMEM — tile management (64KB region; 4KB ICache backed)
0x46000 – 0x2FFFFF  Tensor workspace (~2.73MB)
────────────────────────────────────────────────────
  ↑ TDMA uses tensor workspace for weight tiles,
    activation buffers, and KV-cache storage.
```

TRISC3 copies TRISC0/1/2 firmware images into the IMEM regions before releasing TRISC resets.

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

TDMA operates entirely under TRISC control. TRISC2 (math) programs the MOP sequencer; TRISC1 (unpack) drives the unpack engine; TRISC0 (pack) drives the pack engine. Each is an independent pipeline stage, enabling the double-buffered compute loop described in §2.3.

**Why MOP encoding?** A single raw RISC-V instruction operates on one register or one memory word. Loading a 16×16 INT16 tensor tile from L1 into SRCA would require hundreds of load instructions. A single MOP — encoded as one or two 32-bit words — can express "load a 16×16 INT16 tile starting at L1 base address X with row stride Y into SRCA bank 0." This achieves roughly **10× instruction density** compared to raw RISC-V equivalents.

#### 2.7.2 Sub-block Description

| Sub-block       | Controlling TRISC | Function                                                                |
|-----------------|--------------------|-------------------------------------------------------------------------|
| MOP sequencer   | TRISC2             | Decodes MOP instructions; dispatches to G/M-Tile, FP-Lane, or SFPU     |
| Unpack engine   | TRISC1             | Reads L1 tensor data or incoming NoC flit; applies format conversion; loads SRCA/SRCB |
| Pack engine     | TRISC0             | Reads DEST register file; applies format conversion; writes to L1 or NoC flit |
| Address gen     | TRISC1/TRISC0      | Multi-dimensional stride/offset computation for tensor addressing (up to 4 dimensions) |

RTL file: `tt_instrn_engine.sv` (contains MOP sequencer and TDMA logic); `tt_trisc.sv` (per-thread cores).

#### 2.7.3 MOP Sequencer

**RTL files:** `tt_mop_decode.sv`, `tt_mop_config.sv`, `tt_mop_decode_math_loop.sv`, `tt_mop_decode_unpack_loop.sv`

The MOP sequencer receives 32-bit compressed MOP instruction words from TRISC2 and **expands each one into a sequence of primitive FPU tag words**, one per clock cycle, that drive the G-Tile, FP-Lane, and SFPU datapaths. TRISC2 issues one MOP word; the sequencer autonomously generates dozens to hundreds of primitive operations from it, keeping the FPU continuously occupied without TRISC2 involvement.

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

Before TRISC2 issues a MOP, it pre-programs a **dual-bank configuration register set** (`tt_mop_config.sv`) with the expanded parameters for the inner loop:

| Register | Content |
|----------|---------|
| `LOOP0_LEN` | Outer loop count |
| `LOOP1_LEN` | Inner loop count |
| `LOOP_INSTR0` | Primitive instruction A (issued on even inner iterations) |
| `LOOP_INSTR1` | Primitive instruction B (issued on odd inner iterations) |
| `LOOP_START_INSTR0` | Preamble instruction before inner loop begins |
| `LOOP_END_INSTR0/1` | Postamble instructions after inner loop ends |
| `LOOP0_LAST_INSTR` | Final instruction at the end of the outer loop |

Two banks (BANK0, BANK1) exist for **double-buffering**: while the sequencer executes one bank, TRISC2 can program the other. The hardware automatically toggles the active bank when `mop_done` is asserted; TRISC2 toggles the write bank when it asserts `cfg_done`. `o_mop_cfg_write_ready` tells TRISC2 whether the next bank is available to write.

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

**One primitive FPU tag is emitted per clock cycle** — the FPU pipeline never stalls waiting for the sequencer. For a 48-row SRCA bank pass (K_tile_FP16B=48), TRISC2 issues one MOP; the sequencer generates 48 consecutive `fpu_tag_t` words, each with `srca_rd_addr` incrementing from 0 to 47.

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
TRISC2 firmware                    MOP Sequencer hardware
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
TRISC2 (next MOP or SEMPOST) ←     hardware SEMPOST → TRISC0 unblocks
```

One MOP word from TRISC2 generates **48 consecutive FPU tag cycles** with zero TRISC2 involvement after the issue. For the full K=8192 INT8 pass (86 firmware passes × 48 MOP cycles), TRISC2 issues 86 MOP words total.

#### 2.7.4 Pack Engine (TRISC0)

The pack engine reads DEST register file entries and writes formatted data to either L1 or the NoC output path:

```
DEST RF ──(read)──► Format Converter ──► [ L1 write port ]
                          │
                          └──────────────► [ NoC output flit ]
```

Format conversion options on pack path:
- INT32 → FP16B (with optional stochastic rounding)
- INT32 → INT8 (with optional stochastic rounding)
- FP32 → FP16B
- Identity (no conversion — pass through as-is)

The pack engine uses the **address generator** to compute the L1 destination address for each output element using a stride/offset model, allowing non-contiguous writes (e.g., writing rows of a transposed tile into a strided L1 region).

#### 2.7.5 Unpack Engine (TRISC1)

The unpack engine is the reverse path: reads tensor data from L1 or an incoming NoC flit and loads it into SRCA/SRCB for FPU consumption:

```
[ L1 read port ] ──► Format Converter ──► SRCA register file
[ NoC input flit ] ──────────────────────► SRCB (direct from L1 via 512-bit path)
```

Format conversion options on unpack path:
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

#### 2.7.7 Double-Buffered Pipeline

The canonical double-buffered compute loop enabled by TDMA:

```
Cycle epoch N:
  TRISC1 (unpack):  L1[tile N+1] → SRCA bank 1   (prefetch next)
  TRISC2 (math):    SRCA bank 0 + SRCB → DEST     (compute current)
  TRISC0 (pack):    DEST → L1[output N-1]          (drain previous)

Cycle epoch N+1:
  TRISC1 (unpack):  L1[tile N+2] → SRCA bank 0   (prefetch next)
  TRISC2 (math):    SRCA bank 1 + SRCB → DEST     (compute current)
  TRISC0 (pack):    DEST → L1[output N]            (drain previous)
```

Hardware semaphore instructions (SEMPOST/SEMGET) gate each transition: TRISC1 executes `SEMPOST sem0` when SRCA/SRCB is filled; TRISC2 is hardware-stalled at `SEMGET sem0` until that post, then fires its MOP; TRISC2 executes `SEMPOST sem1` when DEST is ready; TRISC0 is stalled at `SEMGET sem1` until that post, then reads DEST.

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
| Total row-addresses per `tt_tensix` | 16,384 (16 instances × 1,024 rows)                                      |
| Implementation           | Latch array (`LATCH_ARRAY=1`, not SRAM)                                              |
| Clock domain             | `i_ai_clk`                                                                           |

**Storage capacity (per `tt_tensix` tile):**
- 16 DEST column slices × 1,024 rows × 32 bits per row = **524,288 bits = 64KB** per `tt_tensix` tile
- Double-buffer split: 16 × 512 rows/bank = 8,192 32b entries per bank; 2 banks = 16,384 × 32b entries total

**Total across 12 Tensix clusters (48 `tt_tensix` tiles):**
- 48 tiles × 64KB = **3,072KB ≈ 3MB** total DEST latch array on-chip

> **Note on earlier HDD versions:** Prior versions stated "12,288 entries per tile." This figure was not derivable from RTL parameters and is superseded by the RTL-verified parameters above. The correct per-tile figure (per `tt_tensix`) is 16,384 32-bit row-addresses (16,384 × 32b = 64KB). The figure 12,288 was likely derived from an older design parameter set and is no longer accurate.

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

| Parameter          | Value                              |
|--------------------|------------------------------------|
| Module             | `tt_srcs_registers.sv` (shared SRCA/SRCB storage) |
| Entries per tile   | 1,536                              |
| Width per entry    | 32 bits                            |
| Total per tile     | 49,152 bits = 6KB (latch array)    |
| `NUM_BANKS`        | 2 (double-buffered)                |
| `NUM_SLICES`       | 3 (logical register sets per bank) |
| `BANK_ROWS_16B`    | 8 per slice                        |
| `NUM_COLS`         | 16                                 |
| `NUM_WR_ROWS`      | 4                                  |
| `SRCA_NUM_SETS`    | 4 (`tt_tensix_pkg.sv`)             |
| Implementation     | Latch array (not SRAM)             |
| Clock domain       | `i_ai_clk`                         |
| Loaded by          | TRISC1 unpack engine               |
| Consumed by        | TRISC2 → G-Tile / M-Tile           |

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
| `BANK_REGISTER_DEPTH`  | 64 rows per bank                     |
| `SRCB_OUTPUT_COLS`     | 16                                   |
| `SRCB_OUTPUT_ROWS`     | 4                                    |
| `SRCB_DBUS_WIDTH`      | 16 bits per column datum             |
| `NUM_REG_BANKS`        | 2 (double-buffered)                  |
| Total capacity         | 2 banks × 64 rows × 16 cols × 16b = **32,768 bits = 4KB** |
| Implementation         | Register file (latch array, `SRCB_IN_FPU=1`) |
| Special operations     | `d2b` (DEST-to-SRCB move), `shift_x` (column shift) |
| Clock domain           | `i_ai_clk`                           |
| Loaded by              | TRISC1 unpack engine (or SFPU via `srcs_select`) |
| Consumed by            | TRISC2 → G-Tile / M-Tile (B-operand) |

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
| Loaded by           | TRISC1 unpack engine                      | TRISC1 unpack engine                          |

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


## §3 Overlay Engine — Data Movement Orchestration

The overlay engine is the autonomous data-movement subsystem within each Tensix tile, responsible for orchestrating transfers between the on-chip L1 SRAM (3 MB per cluster) and external DRAM. It decouples the TRISC processor cores from DMA execution latency, allowing firmware to initiate transfers via register writes and continue computation while overlay hardware autonomously moves data in parallel.

### 3.1 Overview and Architecture

#### 3.1.1 Role and Purpose

The overlay engine provides:
- **Autonomous DMA**: Once programmed via CSR writes, the overlay hardware generates NoC packets and injects them without further TRISC involvement
- **TRISC decoupling**: TRISC firmware writes a command register and continues execution; overlay executes the transfer independently
- **8 independent streams**: Per Tensix cluster, allowing pipelined and concurrent data movement
- **L1/DRAM bridge**: Primary mechanism for tensor data movement between fast on-chip L1 (3 MB per cluster) and slower DRAM
- **Context switching**: Saves/restores L1 and L2 cache state across kernel context boundaries (§3.5)

#### 3.1.2 Container Module: `tt_neo_overlay_wrapper`

**RTL File:** `/secure_data_from_tt/20260221/tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv`

**Module Responsibilities:**
- Overlay stream CSR interface (receives commands from TRISC via register writes)
- TDMA engine (Tile DMA with pack/unpack)
- MOP sequencer (32-bit compressed instruction format for FPU control)
- L1/L2 memory hierarchy control
- Clock domain crossing (CDC) FIFOs between `ai_clk` and `noc_clk`
- Reset distribution and synchronization
- SMN (System Management Network) security gateway
- EDC (Error Detection & Correction) ring integration
- Rocket CPU wrapper (for Dispatch tiles)

**Key Clock Domains Managed:**
- `i_ai_clk[X]` — AI compute (TRISC, FPU, instruction fetch) per column X
- `i_dm_clk[X]` — Data-move (TDMA, pack/unpack, L1 access) per column X
- `i_noc_clk` — Global NoC fabric
- `i_axi_clk` — Host bus interface (independent from NPU PLL)

#### 3.1.3 Overlay vs. iDMA: Two DRAM Access Mechanisms

| Property | Overlay Streams | iDMA Engine (§6) |
|----------|-----------------|-----------------|
| Initiator | TRISC0/1/2/3 CSR write | Dispatch CPU via iDMA instruction |
| Path | TRISC CSR → NoC → NIU → AXI → DRAM | Dispatch iDMA → AXI → DRAM (direct, no NoC) |
| Purpose | L1 ↔ DRAM movement | Weight loading, model parameters |
| Capacity | 8 streams, sequential at DRAM | Dedicated AXI master port |
| Latency | 100–150+ cycles | Lower latency (direct AXI) |
| Competition | With iDMA for DRAM bandwidth | With overlay streams for AXI bandwidth |

---

#### 3.2 Hardware Components

#### 3.2.1 Overlay Stream Controller

**Purpose:** Converts 32-bit CSR register writes into NoC packet injections

**CSR Interface:**
- Width: 32-bit register write from TRISC via `noc_neo_local_regs_intf`
- Accessible by: All 4 TRISC threads (TRISC0, TRISC1, TRISC2, TRISC3)
- Non-blocking: TRISC continues immediately after write; overlay executes asynchronously

**Register Fields** (per stream):
1. **Source address** — Tile coordinates (X, Y) and L1 byte offset
2. **Destination address** — For writes to DRAM; for reads, source DRAM address
3. **Transfer size** — Number of 512-bit flits (1 flit = 64 bytes)
4. **Direction** — 1 = read (DRAM→L1), 0 = write (L1→DRAM)
5. **Stream ID** — Which of 8 overlay streams (0–7)

**Burst Length Encoding:**
```
ARLEN = (total_bytes / 64) − 1

Examples:
  512 B:    ARLEN =   7  (8 beats)
  4 KB:     ARLEN =  63  (64 beats)
  16 KB:    ARLEN = 255  (256 beats, maximum)
  32 KB:    Split across 2 stream commands
```

**Maximum Constraint:**
- `MAX_TENSIX_DATA_RD_OUTSTANDING = 4` (8 in large TRISC mode)
- Firmware must check stream status before issuing 5th concurrent read
- Prevents NIU RDATA FIFO overflow (512 entries = 32 KB buffer)

#### 3.2.2 TDMA (Tile DMA) Engine

**Components:**
- **Pack engine** — Reads DEST latch-array, formats output tensors, writes to L1/NoC
- **Unpack engine** — Reads L1/NoC, unpacks activation tensors, loads into SRCA/SRCB for FPU
- **MOP sequencer** — Drives TRISC2 with compressed 32-bit macro-operations
- **Context switch hardware** — Saves/restores L1/L2 cache across kernel boundaries

**Per-TRISC Roles:**
| TRISC | Role | Typical Operations |
|-------|------|-------------------|
| TRISC0 | Pack | Read DEST RF → format → write L1 → poll NoC status |
| TRISC1 | Unpack | Read L1/NoC → unpack tensor → load SRCA/SRCB |
| TRISC2 | Math | Fetch MOP from sequencer → drive FPU → semaphore completion |
| TRISC3 | Manage | Tile lifecycle, residual DMA, KV-cache control, boot |

**RTL File:** `/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_instrn_engine.sv`

#### 3.2.3 MOP (Micro-Operation Packet) Sequencer

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

#### 3.2.4 Stream Status Registers

**Register:** `trisc_tensix_noc_stream_status[thread][stream]`

**Capacity:**
- 8 streams per cluster
- Per-TRISC readback (each thread can poll its own status)
- 32-bit register per stream

**Status Fields:**
- `valid` — Stream result is ready
- `error` — Stream encountered an error (SMN security violation, ATT miss, etc.)
- `in_progress` — Stream is currently executing
- `outstanding_reads` — Current count of in-flight reads (for firmware polling)

**Polling Idiom** (firmware):
```
write_stream_csr(stream=0, size=256, dir=READ, dst=0x1000);  // L1 address
while (stream_status[0].in_progress) {
  // Overlap computation with DMA
  compute_kernel();
}
```

---

#### 3.3 Data Paths and NoC Integration

#### 3.3.1 Complete DRAM Access Path

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

#### 3.3.2 NIU Addressing: Composite vs. Standalone

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

#### 3.3.3 Clock Domain Crossings

The overlay engine bridges three clock domains:

| Crossing | Source → Dest | Mechanism | Location |
|----------|---|---|---|
| ai_clk → noc_clk | TRISC CSR write → Overlay inject | CDC FIFO | overlay_wrapper (input side) |
| noc_clk → ai_clk | Stream status readback | CDC FIFO | overlay_wrapper (output side) |
| noc_clk → dm_clk | L1 data ingress | Synchronizer FIFO | L1 partition interface |

**CDC Design Principle:** FIFOs decouple clock domains without imposing synchronous reset relationships. TRISC (ai_clk) can continue while overlay DMA (noc_clk) executes at potentially different frequency.

#### 3.3.4 L1 Memory Hierarchy Integration

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

#### 3.4 Stream Programming Model and Register Interface

#### 3.4.1 Stream CSR Registers per Cluster

**Register Set** (8 streams, 0–7):

Per stream, the overlay stream controller accepts:
```c
struct overlay_stream_command {
  uint32_t src_addr;       // [30:0] NoC endpoint X + offset
  uint32_t dst_addr;       // [30:0] L1 byte address or DRAM address
  uint16_t size_flits;     // [15:0] Number of 512-bit flits (1–256)
  uint8_t  stream_id;      // [7:0]  Which stream (0–7)
  uint8_t  direction;      // [0]    0=write (L1→DRAM), 1=read (DRAM→L1)
  uint8_t  enable;         // [0]    Start the transfer (pulse)
};
```

#### 3.4.2 Stream Status Polling

**Stream Status Register** (read-only, per TRISC):
```c
struct overlay_stream_status {
  uint8_t  valid;          // [0]    Result ready
  uint8_t  error;          // [1]    SMN security violation or other error
  uint8_t  in_progress;    // [2]    Stream is currently executing
  uint8_t  outstanding;    // [7:3]  Current in-flight reads (0–4)
};
```

**Polling Constraint:**
- Firmware must check `stream_status[stream].in_progress == 0` before issuing next transfer
- Alternative: Check `outstanding` field, ensure it stays ≤ 4

#### 3.4.3 Stream Lifecycle State Machine

```
IDLE
  │
  ├─ (TRISC writes CSR with enable bit)
  │
  ▼
ISSUED
  ├─ (Overlay injects NoC packet)
  │
  ▼
IN_FLIGHT (noc_clk domain)
  ├─ (NoC routes flit to NIU)
  ├─ (NIU generates AXI transaction)
  ├─ (DRAM returns data or acknowledgment)
  │
  ▼
COMPLETE
  ├─ (Stream status updated)
  ├─ (Optional: interrupt asserted if enabled)
  │
  ▼
IDLE (ready for next command)
```

**Latency Breakdown** (100–150+ cycles typical):
- CSR write → overlay inject: 1–2 ai_clk cycles
- Overlay → NoC inject: 1 noc_clk cycle
- NoC routing: 6–8 noc_clk cycles (hop count + virtual channel arbitration)
- NIU ATT lookup: <1 cycle
- AXI → DRAM: 50–100+ cycles (depends on DRAM controller and contention)
- DRAM → NIU RDATA FIFO: 8+ cycles (signaling, CDC)
- Total: **100–200+ cycles** depending on DRAM load and NoC congestion

---

#### 3.5 Context Switching

#### 3.5.1 Purpose and Mechanism

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

#### 3.6 Performance Characteristics

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

#### 3.7 Integration with Other Components

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

#### 3.8 Power Management and DFX

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
- **Wormhole-forwarded data flits**: Body flits bypass ATT and security checks entirely, with header-only decode, ensuring minimal per-hop latency for large (32+ KB) tensor transfers.

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
  512 B transfer:   ARLEN = (512 / 64) − 1 = 7  (8 beats)
  4 KB transfer:    ARLEN = (4096 / 64) − 1 = 63  (64 beats)
  16 KB transfer:   ARLEN = (16384 / 64) − 1 = 255  (256 beats, maximum)
  32 KB transfer:   Requires 2 separate AXI bursts (e.g., 256 + 256, or 256 + 0)
```

**Constraint:** Max single AXI burst = 256 beats × 64 bytes = **16 KB**. Larger transfers must be split across multiple overlay stream commands or multiple NoC packets.

**RTL mapping:**
- Each 512-bit NoC flit corresponds to exactly 1 AXI beat (512 bits = 64 bytes)
- The overlay stream engine counts flits and encodes `ARLEN = (num_flits − 1)` directly

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

### 8.11 EDC Signal Debugging Guide — Complete Path Tracing

For simulation and post-silicon debugging of EDC ring handshakes, this section provides the complete forward (req_tgl) and backward (ack_tgl) signal paths through the N1B0 ring, along with proving points (checkpoints) to verify proper handshake propagation at each stage.

#### 8.11.1 Signal Definitions and Properties

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

#### 8.11.2 Forward Path (req_tgl) Signal Propagation

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

#### 8.11.3 Backward Path (ack_tgl) Signal Propagation

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

#### 8.11.4 Complete Per-Node Handshake Sequence

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

#### 8.11.5 Complete Ring Sweep Timeline (End-to-End Example)

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

#### 8.11.6 Proving Points for Waveform Verification

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

#### 8.11.7 RTL Path Mapping for Signal Tracing

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

#### 8.11.7a Trinity Top EDC Signal Hierarchy — Column X=0 (Detailed Signal Listing)

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

#### 8.11.7b Trinity Top EDC Signal Hierarchy — Column X=1 (Composite Tile with Cross-Row Loopback)

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

#### 8.11.8 Debugging Checklist for Failed EDC Sweeps

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



### 8.10 Harvest Bypass in EDC Ring

When a tile is harvested (disabled due to manufacturing yield), the tile's compute logic is powered down or isolated. If the EDC ring simply omitted the node, the ring chain would be broken at that point and the entire ring would stall, preventing error monitoring for all remaining active tiles. The bypass mechanism solves this problem.

#### 8.10.1 Bypass Mechanism

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

#### 8.10.2 Bypass Control Signal

The bypass is controlled by the `ISO_EN` signal — mechanism 6 in the N1B0 harvest scheme. `ISO_EN[x + 4*y]` being asserted for a tile directly drives the bypass mux select for all EDC nodes within that tile:

```
  ISO_EN bit mapping for Tensix tiles (X=0..3, Y=0..2):
  ISO_EN[0]  → tile (X=0, Y=0) → bypass all EDC nodes at (0,0)
  ISO_EN[1]  → tile (X=1, Y=0) → bypass all EDC nodes at (1,0)
  ...
  ISO_EN[11] → tile (X=3, Y=2) → bypass all EDC nodes at (3,2)
```

The same `ISO_EN` signal that gates the tile's compute clocks (via DFX wrappers) and isolates its output signals (via AND-type ISO cells) also bypasses its EDC nodes. This ensures that a harvested tile is consistently invisible to the EDC ring — it contributes no CRC, receives no toggle, and its output isolation prevents it from driving the ring in an uncontrolled state.

#### 8.10.3 Consequence of Not Bypassing

If a harvested tile's EDC node is not bypassed, the following failure modes occur:

1. **Ring stall**: The node's compute clock is gated, so `req_tgl` arriving at the node will never be forwarded. The initiator waits indefinitely for `ack_tgl` and eventually declares a timeout — generating a false FATAL interrupt even though no real error exists.
2. **Incorrect CRC**: If the node is partially powered (e.g., ISO cells block outputs but node logic is still active), the node may generate a CRC over garbage state, causing a false CRIT error.
3. **Ring deadlock**: In the worst case, the ring permanently stalls and all subsequent EDC monitoring is disabled for the entire chip.

The bypass mechanism ensures none of these failure modes can occur. Bypass assertion is part of the standard harvest initialization sequence and must be applied before the EDC ring is enabled.

### 8.11 EDC CSR Base Addresses

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

*End of document. §1–§14 complete.*

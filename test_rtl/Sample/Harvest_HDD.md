# Hardware Design Document: Harvest in Trinity

**Project:** Trinity (Tenstorrent AI NPU SoC)
**Target:** 4×5 grid (TARGET_4X5), 4nm process (TARGET_PROJECT_BOS_TRINITY_B0)
**Source RTL:** `/secure_data_from_tt/20260221/rtl/`
**Filelist:** `/secure_data_from_tt/20260221/rtl/filelist.f`
**Date:** 2026-03-11

---

## Table of Contents

1. [Overview](#1-overview)
2. [Physical Grid Layout](#2-physical-grid-layout)
3. [Harvest Concepts and Goals](#3-harvest-concepts-and-goals)
4. [Harvest Mechanisms — Summary](#4-harvest-mechanisms--summary)
5. [Mechanism 1: Reset Isolation](#5-mechanism-1-reset-isolation)
6. [Mechanism 2: Abutted Clock/Reset Routing Chain](#6-mechanism-2-abutted-clockreset-routing-chain)
7. [Mechanism 3: NoC Dynamic Mesh Reconfiguration](#7-mechanism-3-noc-dynamic-mesh-reconfiguration)
8. [Mechanism 4: EDC Ring Harvest Bypass](#8-mechanism-4-edc-ring-harvest-bypass)
9. [Mechanism 5: Dispatch-to-Tensix (FDS) Awareness](#9-mechanism-5-dispatch-to-tensix-fds-awareness)
10. [Clock Domains and CDC](#10-clock-domains-and-cdc)
11. [Reset Architecture](#11-reset-architecture)
12. [SDC / Timing Notes](#12-sdc--timing-notes)
13. [How to Operate Harvest in RTL (Step-by-Step)](#13-how-to-operate-harvest-in-rtl-step-by-step)
14. [Register Interface Summary](#14-register-interface-summary)
15. [Key RTL Paths and File Locations](#15-key-rtl-paths-and-file-locations)
16. [Notes for Specific Audiences](#16-notes-for-specific-audiences)

---

## 1. Overview

**Harvest** is the chip-design practice of disabling tiles (specifically Tensix compute rows) that contain manufacturing defects, while leaving the remainder of the chip fully operational. This improves manufacturing yield: a die that would otherwise be scrapped can still be sold as a functional product with a reduced compute count.

Trinity implements a multi-layer harvest architecture. Every aspect of the chip that interacts with a Tensix tile must be aware of — and resilient to — that tile being absent:

| Layer | Harvest Mechanism |
|---|---|
| Power / Reset | Per-tile active-low reset held asserted for harvested tiles |
| Clocks | Abutted clock chain propagates through all tiles; harvested tiles pass through |
| Network-on-Chip (NoC) | Dynamic routing (`HAS_DYNAMIC_ROUTING=1'b1`): configurable mesh boundaries |
| Diagnostic channel (EDC) | Per-column serial ring with mux/demux bypass of harvested tiles |
| Dispatch (FDS) | `de_to_t6` / `t6_to_de` column buses; dispatch skips harvested worker tiles |

**Harvestable tile types (from `trinity_pkg.sv`):**

| Tile type | Enum value | Harvestable? |
|---|---|---|
| `TENSIX` | 3'd0 | **Yes** — main harvest target |
| `NOC2AXI_N_OPT` / `NE_OPT` / `NW_OPT` | 3'd1–3 | No (boundary, always present) |
| `DISPATCH_E` / `DISPATCH_W` | 3'd4–5 | No (row y=3, always present) |
| `ROUTER` | 3'd7 | No (always present) |

Only the three Tensix rows (y=0, y=1, y=2) are harvest candidates.

---

## 2. Physical Grid Layout

Grid dimensions from `trinity_pkg.sv`:
```systemverilog
localparam int unsigned SizeX = 4;
localparam int unsigned SizeY = 5;
```

Physical tile layout (y increases northward; `GridConfig[y][x]`):

```
         x=0            x=1            x=2            x=3
        ┌──────────────┬──────────────┬──────────────┬──────────────┐
  y=4   │ NOC2AXI      │ NOC2AXI      │ NOC2AXI      │ NOC2AXI      │  ← AXI boundary
  (N)   │ NE_OPT       │ N_OPT        │ N_OPT        │ NW_OPT       │
        ├──────────────┼──────────────┼──────────────┼──────────────┤
  y=3   │ DISPATCH_E   │ ROUTER       │ ROUTER       │ DISPATCH_W   │  ← Dispatch row
        ├──────────────┼──────────────┼──────────────┼──────────────┤
  y=2   │ TENSIX [2]   │ TENSIX [2]   │ TENSIX [2]   │ TENSIX [2]   │  ← Harvest row 2
        ├──────────────┼──────────────┼──────────────┼──────────────┤
  y=1   │ TENSIX [1]   │ TENSIX [1]   │ TENSIX [1]   │ TENSIX [1]   │  ← Harvest row 1
        ├──────────────┼──────────────┼──────────────┼──────────────┤
  y=0   │ TENSIX [0]   │ TENSIX [0]   │ TENSIX [0]   │ TENSIX [0]   │  ← Harvest row 0
  (S)   │ (southmost)  │              │              │              │
        └──────────────┴──────────────┴──────────────┴──────────────┘

  NOC edge tie-offs: South edge (y=0) and East edge (x=3) tie NOC flit inputs to 0.
```

**Endpoint index** formula (used in NoC and EDC addressing):
```systemverilog
localparam int unsigned EndpointIndex = (x * trinity_pkg::SizeY) + y;
// EndpointIndex[0..19], column-major order
```

**Key counts (from `trinity_pkg.sv`):**
```systemverilog
localparam int unsigned NumNodes        = 20;   // total tiles
localparam int unsigned NumTensix       = 12;   // 3 rows × 4 cols
localparam int unsigned NumNoc2Axi      = 4;    // one per column (y=4)
localparam int unsigned NumDispatch     = 2;    // DISPATCH_E + DISPATCH_W
localparam int unsigned NumApbNodes     = 4;    // one APB port per NOC2AXI tile
localparam int unsigned NumDmComplexes  = 14;   // Tensix (12) + Dispatch (2)
localparam int unsigned DMCoresPerCluster = 8;  // RISC-V cores per DM complex
localparam int unsigned TensixPerCluster  = 4;
localparam bit          EnableDynamicRouting = 1'b1;
```

---

## 3. Harvest Concepts and Goals

### 3.1 What "Harvesting" a Row Means

A harvested row is a physical row of Tensix tiles (all 4 tiles in a y-row) that are permanently disabled due to a manufacturing defect (e.g., failed SRAM, stuck logic). After harvest:

- The tile is held in reset (no logic runs).
- The NoC routes traffic around the row (the logical mesh shrinks by one row).
- The EDC diagnostic ring bypasses the row so diagnostics remain functional.
- The dispatch engine does not issue work to that row.

### 3.2 Harvest Granularity

Harvest is per-**row** (all x-columns at a given y must be harvested together). The NoC mesh, dispatch, and EDC all operate on row-level boundaries.

### 3.3 Maximum Harvest Depth

- Up to all 3 Tensix rows can theoretically be harvested (yielding a non-compute die).
- Typical yield products harvest 0 or 1 row, retaining 12 or 8 Tensix tiles.

---

## 4. Harvest Mechanisms — Summary

```
  ┌──────────────────────────────────────────────────────────────────────────────────────┐
  │                         TRINITY HARVEST ARCHITECTURE                                │
  │                                                                                      │
  │   Harvest config enters via EDC noc_sec_controller (per NOC2AXI tile)               │
  │   ───────────────────────────────────────────────────────────────────                │
  │                                                                                      │
  │   ┌───────────────┐    ┌─────────────────────────────────────────────────┐          │
  │   │  APB4 (FW)    │───►│ EDC BIU (y=4)                                   │          │
  │   └───────────────┘    │  tt_edc1_biu_soc_apb4_wrap                      │          │
  │                        │  ▼ sends EDC packets down ring                  │          │
  │                        │ tt_edc1_noc_sec_controller (idx=192)            │          │
  │                        │  ▼ decodes: mesh_start/stop, size, orientation  │          │
  │                        │  ▼ drives edc_config_noc_sec → tt_noc2axi       │          │
  │                        └─────────────────────────────────────────────────┘          │
  │                                                                                      │
  │   ┌─────────────────────────────────────────────────────────────────────┐           │
  │   │ tt_noc2axi (HAS_DYNAMIC_ROUTING=1)                                  │           │
  │   │  mesh_start_y ──► NoC router: skip southernmost rows               │           │
  │   │  mesh_end_y   ──► NoC router: skip northernmost rows               │           │
  │   │  noc_y_size   ──► logical grid height advertised to routing algo   │           │
  │   └─────────────────────────────────────────────────────────────────────┘           │
  │                                                                                      │
  │   ┌──────────────────────────────────────────────────────────────────────┐          │
  │   │ Reset isolation (per tile)                                           │          │
  │   │  i_tensix_reset_n[TensixIndex]     = 0 → tile in reset (harvested) │          │
  │   │  i_dm_core_reset_n[DmIdx][0..7]    = 0 → DM cores in reset        │          │
  │   │  i_dm_uncore_reset_n[DmIdx]        = 0 → DM uncore in reset       │          │
  │   └──────────────────────────────────────────────────────────────────────┘          │
  │                                                                                      │
  │   ┌──────────────────────────────────────────────────────────────────────┐          │
  │   │ EDC harvest bypass (per column, per tile)                            │          │
  │   │  edc_mux_demux_sel=1 → bypass demux+mux pair around harvested tile  │          │
  │   └──────────────────────────────────────────────────────────────────────┘          │
  │                                                                                      │
  │   ┌──────────────────────────────────────────────────────────────────────┐          │
  │   │ Dispatch (FDS) awareness                                             │          │
  │   │  de_to_t6 column bus stops at harvested rows                        │          │
  │   │  t6_to_de feedback from live rows propagated to dispatch            │          │
  │   └──────────────────────────────────────────────────────────────────────┘          │
  └──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Mechanism 1: Reset Isolation

### 5.1 Per-Tile Reset Inputs at the `trinity` Top Level

The `trinity` top-level module ([trinity.sv](trinity.sv)) receives independent resets for every tile:

```systemverilog
// Active-low reset per Tensix tile (indexed by TensixIndex)
input logic [trinity_pkg::NumTensix-1:0]   i_tensix_reset_n,          // [11:0]

// Active-low reset per DM cluster (Tensix + Dispatch share DM)
input logic [trinity_pkg::NumDmComplexes-1:0]
            [trinity_pkg::DMCoresPerCluster-1:0] i_dm_core_reset_n,    // [13:0][7:0]
input logic [trinity_pkg::NumDmComplexes-1:0]   i_dm_uncore_reset_n,  // [13:0]
```

**To harvest a tile:** drive the corresponding `i_tensix_reset_n[TensixIndex]` bit to `0`. The tile is functionally dead (held in reset); all internal state is frozen.

### 5.2 Reset Indexing

Index functions from `trinity_pkg.sv`:

```systemverilog
function automatic int unsigned getTensixIndex(int unsigned target_x, int unsigned target_y);
// Scans GridConfig in column-major (xx-outer, yy-inner) order, counting TENSIX tiles.

function automatic int unsigned getDmIndex(int unsigned target_x, int unsigned target_y);
// Counts DISPATCH_E, DISPATCH_W, and TENSIX tiles in the same order.
```

**TensixIndex table (4×5 grid, 12 Tensix tiles):**

| (x,y) | TensixIndex | DmIndex |
|---|---|---|
| (0,0) | 0 | 0 |
| (0,1) | 1 | 1 |
| (0,2) | 2 | 2 |
| (1,0) | 3 | 4 |
| (1,1) | 4 | 5 |
| (1,2) | 5 | 6 |
| (2,0) | 6 | 8 |
| (2,1) | 7 | 9 |
| (2,2) | 8 | 10 |
| (3,0) | 9 | 12 |
| (3,1) | 10 | 13 |
| (3,2) | 11 | 14 — wait: getDmIndex also counts DISPATCH |

> **Note:** DmIndex interleaves Dispatch tiles (y=3) into the count. DISPATCH_E at (3,3) and DISPATCH_W at (0,3) are DmIndex 3 and 11 respectively. Routers at (1,3) and (2,3) are not counted.

**To harvest an entire row (e.g., y=0):** assert reset for TensixIndex {0, 3, 6, 9} and the corresponding DmIndex entries for all four x-positions.

### 5.3 RTL Wiring of Resets Through the Clock Chain

Resets are not distributed via a flat fanout — they are injected at the **top row** (y=4) and travel downward through the abutted clock-routing chain (see Section 6). Each tile receives its portion of the reset vector from `clock_routing_in[x][y]` and passes through the remainder to `clock_routing_out[x][y]` for tiles below.

The mapping between the array-indexed top-level inputs and the per-tile clock_routing signals is established in the `gen_reset_routing` generate block (trinity.sv lines 218–234):

```systemverilog
// At y = SizeY-1 (top row, y=4): inject top-level resets into clock chain
for (genvar yy = 0; yy < trinity_pkg::SizeY; yy++) begin : gen_reset_routing
  if (GridConfig[yy][x] == TENSIX ...) begin : gen_dm_reset
    assign clock_routing_in[x][y=4].dm_core_clk_reset_n[SizeY-1-yy]
        = i_dm_core_reset_n[getDmIndex(x, yy)];
    assign clock_routing_in[x][y=4].tensix_reset_n[SizeY-1-yy]
        = i_tensix_reset_n[getTensixIndex(x, yy)];
  end else begin : gen_dm_reset_tie_off
    assign clock_routing_in[x][y=4].dm_core_clk_reset_n[SizeY-1-yy] = '0;
    assign clock_routing_in[x][y=4].tensix_reset_n[SizeY-1-yy]       = '0;
  end
end
```

> **Important:** Non-Tensix rows (y=3 Dispatch/Router, y=4 NOC2AXI) are tied to `0` in the reset vector. Only tiles with GridConfig == TENSIX, DISPATCH_E, or DISPATCH_W get real reset bits assigned.

---

## 6. Mechanism 2: Abutted Clock/Reset Routing Chain

### 6.1 Clock Routing Struct

All clocks and resets travel through the array as a packed struct, defined in `trinity_pkg.sv`:

```systemverilog
typedef struct packed {
  logic                                     ai_clk;
  logic                                     noc_clk;
  logic                                     dm_clk;
  logic                                     ai_clk_reset_n;
  logic                                     noc_clk_reset_n;
  logic [SizeY-1:0]                         dm_uncore_clk_reset_n;   // [4:0]
  logic [SizeY-1:0][DMCoresPerCluster-1:0]  dm_core_clk_reset_n;     // [4:0][7:0]
  logic [SizeY-1:0]                         tensix_reset_n;           // [4:0]
  logic                                     power_good;
} trinity_clock_routing_t;
```

Signals `clock_routing_in[x][y]` and `clock_routing_out[x][y]` form a **vertical chain** per column x, flowing south (from y=4 to y=0):

```
 i_ai_clk ──► clock_routing_in[x][y=4].ai_clk
               │
               ▼ (tile at y=4 passes through or buffers)
             clock_routing_out[x][y=4].ai_clk
               │
               │ (assigned to clock_routing_in[x][y=3])
               ▼
             clock_routing_out[x][y=3].ai_clk
               │  ...continues down to y=0
```

### 6.2 Top-Row Injection (y=4, NOC2AXI)

Top row tiles (y=4) receive global clocks directly from `trinity` module ports:

```systemverilog
// trinity.sv lines 210–215
assign clock_routing_in[x][y=4].ai_clk            = i_ai_clk;
assign clock_routing_in[x][y=4].ai_clk_reset_n    = i_ai_reset_n;
assign clock_routing_in[x][y=4].noc_clk           = i_noc_clk;
assign clock_routing_in[x][y=4].noc_clk_reset_n   = i_noc_reset_n;
assign clock_routing_in[x][y=4].dm_clk            = i_dm_clk;
assign clock_routing_in[x][y=4].power_good        = i_edc_reset_n;
```

### 6.3 Downward Propagation (Middle/Lower Rows)

For y < 4, middle rows simply connect output of row above to input of row below:

```systemverilog
// trinity.sv lines 237–245
assign clock_routing_in[x][y].ai_clk      = clock_routing_out[x][y+1].ai_clk;
assign clock_routing_in[x][y].noc_clk     = clock_routing_out[x][y+1].noc_clk;
assign clock_routing_in[x][y].dm_clk      = clock_routing_out[x][y+1].dm_clk;
// ...all reset vectors also propagated...
```

### 6.4 Per-Tile Clock Buffering (Abutted Flow)

Each tile module (e.g., `tt_tensix_with_l1`, `tt_dispatch_top_east`) has clock input/output pairs:

```systemverilog
.i_ai_clk  (clock_routing_in[x][y].ai_clk),
.o_ai_clk  (clock_routing_out[x][y].ai_clk),   // buffered output to tile below
```

Each tile inserts a clock buffer (`tt_libcell_clkbuf`) to drive the clocks to the next tile — this is the **abutted clock tree** approach, where the CTS (clock tree synthesis) is handled tile-by-tile rather than by a chip-level clock tree.

### 6.5 Harvest Impact on Clock Chain

A harvested tile **still passes clocks through** — the `o_*_clk` outputs are simply buffered versions of `i_*_clk`. The tile is kept in reset (so no internal flip-flops clock), but the clock signal itself continues to propagate southward for live tiles below.

**This is critical:** if clock routing through a harvested tile were broken, all tiles below it in the same column would also lose their clocks.

---

## 7. Mechanism 3: NoC Dynamic Mesh Reconfiguration

### 7.1 Background

The Trinity NoC uses a 2D mesh topology. Each router (inside every tile) needs to know the mesh boundaries so it can perform dimension-ordered routing (X-then-Y or Y-then-X). Without harvest, the boundaries are fixed at the compile-time grid size. With harvest, rows must be logically excluded from the mesh.

### 7.2 HAS_DYNAMIC_ROUTING Parameter

All NOC2AXI tiles instantiate `tt_noc2axi` with dynamic routing enabled:

```systemverilog
// trinity_noc2axi_nw_opt.sv, trinity_noc2axi_n_opt.sv, trinity_noc2axi_ne_opt.sv
tt_noc2axi #(
    ...
    .HAS_DYNAMIC_ROUTING(1'b1),  // ← enables runtime mesh reconfiguration
    ...
) tt_noc2axi (...)
```

`EnableDynamicRouting = 1'b1` is also set in `trinity_pkg.sv` as a package-level flag.

### 7.3 Runtime Mesh Configuration Signals

The following signals drive the NoC routing algorithm at runtime (in each NOC2AXI tile):

| Signal | Width | Description |
|---|---|---|
| `noc_x_size` | 7b | Logical mesh X dimension (number of active columns) |
| `noc_y_size` | 7b | Logical mesh Y dimension (number of active rows) |
| `local_nodeid_x` | 6b | This node's logical X coordinate |
| `local_nodeid_y` | 6b | This node's logical Y coordinate |
| `mesh_start_x` | 6b | First active column (inclusive) |
| `mesh_start_y` | 6b | First active row (inclusive, southernmost live row) |
| `mesh_end_x` | 6b | Last active column (inclusive) |
| `mesh_end_y` | 6b | Last active row (inclusive, northernmost live row) |
| `local_node_orientation` | enum | Physical orientation (`NOC_ORIENT_0` default) |
| `noc_endpoint_id` | wide | Endpoint ID for address decode |

### 7.4 EDC Override Logic

These signals are driven from the `edc_config_noc_sec` register output of `tt_edc1_noc_sec_controller` (EDC node index 192 in each NOC2AXI tile). Each field has a `*_sel` override bit:

```systemverilog
// trinity_noc2axi_nw_opt.sv lines 485–494
assign local_nodeid_x   = edc_config_noc_sec.local_node_id_x_sel
                          ? edc_config_noc_sec.local_node_id_x   : i_local_nodeid_x;
assign local_nodeid_y   = edc_config_noc_sec.local_node_id_y_sel
                          ? edc_config_noc_sec.local_node_id_y   : i_local_nodeid_y;
assign noc_x_size       = edc_config_noc_sec.size_x_sel
                          ? edc_config_noc_sec.size_x            : i_noc_x_size;
assign noc_y_size       = edc_config_noc_sec.size_y_sel
                          ? edc_config_noc_sec.size_y            : i_noc_y_size;
assign mesh_start_x     = edc_config_noc_sec.mesh_start_x_sel
                          ? edc_config_noc_sec.mesh_start_x      : 6'd0;
assign mesh_start_y     = edc_config_noc_sec.mesh_start_y_sel
                          ? edc_config_noc_sec.mesh_start_y      : 6'd0;
assign mesh_end_x       = edc_config_noc_sec.mesh_stop_x_sel
                          ? edc_config_noc_sec.mesh_stop_x       : (i_noc_x_size[5:0] - 6'd1);
assign mesh_end_y       = edc_config_noc_sec.mesh_stop_y_sel
                          ? edc_config_noc_sec.mesh_stop_y       : (i_noc_y_size[5:0] - 6'd1);
assign local_node_orientation = edc_config_noc_sec.orientation_sel
                          ? edc_config_noc_sec.orientation       : tt_noc_pkg::NOC_ORIENT_0;
assign noc_endpoint_id  = edc_config_noc_sec.endpoint_id_sel
                          ? edc_config_noc_sec.endpoint_id       : i_noc_endpoint_id;
```

**Default (no override):**
- `mesh_start_x = 0`, `mesh_start_y = 0`
- `mesh_end_x = i_noc_x_size - 1`, `mesh_end_y = i_noc_y_size - 1`

### 7.5 Status Reporting

The NOC2AXI tile also reports current mesh config back through EDC for firmware readback:

```systemverilog
// trinity_noc2axi_nw_opt.sv lines 472–481
assign edc_status_noc_sec.local_node_id_x = i_local_nodeid_x;
assign edc_status_noc_sec.local_node_id_y = i_local_nodeid_y;
assign edc_status_noc_sec.size_x          = i_noc_x_size;
assign edc_status_noc_sec.size_y          = i_noc_y_size;
assign edc_status_noc_sec.mesh_start_x    = 6'd0;   // reports default
assign edc_status_noc_sec.mesh_start_y    = 6'd0;
assign edc_status_noc_sec.mesh_stop_x     = i_noc_x_size[5:0] - 6'd1;
assign edc_status_noc_sec.mesh_stop_y     = i_noc_y_size[5:0] - 6'd1;
```

> **Note:** Status reports the *top-level port* values (`i_noc_x_size`, `i_noc_y_size`), not the post-override values. Firmware must track what it programmed.

### 7.6 Example: Harvesting Row y=0

To harvest the bottom Tensix row (y=0) across all columns:

1. The physical grid still has 5 rows, but the **logical NoC mesh** must exclude row y=0.
2. Set `mesh_start_y = 1` (start mesh at y=1, skipping y=0).
3. Set `noc_y_size = 4` (advertise 4-row logical grid).
4. `local_nodeid_y` for tiles at physical y=1 now becomes logical y=0, etc.

This is programmed via the EDC `noc_sec_controller` on each NOC2AXI tile (one per column).

---

## 8. Mechanism 4: EDC Ring Harvest Bypass

### 8.1 EDC Ring Topology

Each column has an independent vertical EDC serial ring. The ring runs:
- **Segment A (direct, downward):** `edc_egress_intf[x*SizeY+y]` → `edc_ingress_intf[x*SizeY+y-1]`
- **Segment B (loopback, upward):** `loopback_edc_egress_intf[x*SizeY+y]` → `loopback_edc_ingress_intf[x*SizeY+y+1]`

The bottom tile (y=0) connects the direct path to the loopback path (U-turn):

```systemverilog
// trinity.sv lines 200–204 — U-turn at y=0
if (y == 0) begin : bottom_node_edc_connection
  tt_edc1_intf_connector edc_loopback_conn_nodes (
      .ingress_intf(edc_egress_intf[x*SizeY+y]),
      .egress_intf (loopback_edc_ingress_intf[x*SizeY+y])
  );
end
```

### 8.2 Harvest Bypass per Tile

Within each tile that contains an EDC node (Tensix: `tt_tensix_with_l1`, Dispatch: `tt_dispatch_top_*`, Router: `trinity_router`), a demux–mux pair gates the EDC ring around harvested tiles:

```
  Ring input
      │
      ▼
  tt_edc1_serial_bus_demux (sel = edc_mux_demux_sel)
   ├── sel=0 → edc_egress_intf        (to tile's internal EDC nodes)
   └── sel=1 → edc_egress_t6_byp_intf (bypass wire, skips tile)
                                          │
  [TILE INTERNAL EDC NODES]               │
      │                                   │
      ▼                                   │
  tt_edc1_serial_bus_mux (sel = edc_mux_demux_sel)
   ├── sel=0 ← tile output (normal)       │
   └── sel=1 ← edc_egress_t6_byp_intf ───┘
      │
      ▼
  Ring output (continues to next tile)
```

**`edc_mux_demux_sel = 0`:** tile is alive, ring passes through it normally.
**`edc_mux_demux_sel = 1`:** tile is harvested, ring bypasses it entirely.

The bypass signal is controlled from within the tile based on the tile's reset/power state or explicit harvest control signal.

### 8.3 EDC Connectivity in `trinity.sv`

Inter-tile EDC connections (direct path down, loopback path up):

```systemverilog
// trinity.sv lines 188–197
if (y != SizeY-1) begin : top_nodes_edc_connections
  // Direct path: y+1 egress feeds y ingress (downward)
  tt_edc1_intf_connector edc_direct_conn_nodes (
      .ingress_intf(edc_egress_intf[x*SizeY+y+1]),
      .egress_intf (edc_ingress_intf[x*SizeY+y])
  );
  // Loopback path: y egress feeds y+1 ingress (upward)
  tt_edc1_intf_connector edc_loopback_conn_nodes (
      .ingress_intf(loopback_edc_egress_intf[x*SizeY+y]),
      .egress_intf (loopback_edc_ingress_intf[x*SizeY+y+1])
  );
end
```

**Harvest impact on EDC:** When a tile is bypassed, its EDC nodes are not reachable from the BIU. Firmware must not attempt EDC read/write to harvested tile node IDs. The ring integrity is maintained because the bypass wires create a continuous path.

---

## 9. Mechanism 5: Dispatch-to-Tensix (FDS) Awareness

### 9.1 Column Bus Signals

The dispatch system (DISPATCH_E at x=3,y=3 and DISPATCH_W at x=0,y=3) sends tasks to Tensix tiles via column buses:

```systemverilog
// trinity.sv signal declarations
tt_chip_global_pkg::de_to_t6_t [NumDispatchCorners-1:0] de_to_t6_coloumn[SizeX][SizeY-1];
tt_chip_global_pkg::t6_to_de_t                          t6_to_de[SizeX][SizeY-2];
```

- `de_to_t6_coloumn[x][y]`: dispatch-to-Tensix control, flowing southward per column.
- `t6_to_de[x][y]`: Tensix-to-dispatch feedback, flowing northward.

### 9.2 Harvested Row Tie-Off

For Tensix tiles at y=0, the southward `t6_to_de` input is tied off:

```systemverilog
// trinity.sv lines 766–769
if (y == 0) begin : gen_tie_down_t6_to_de
  assign local_t6_to_de = tt_chip_global_pkg::t6_to_de_t'(0);
end else begin : gen_t6_to_de
  assign local_t6_to_de = t6_to_de[x][y-1];
end
```

When a row is harvested, the dispatch controller must be configured to skip that row's worker index. This is firmware/SW responsibility — the RTL provides the connectivity infrastructure.

### 9.3 Dispatch-to-Tensix Routing via Routers

The ROUTER tiles (x=1,y=3 and x=2,y=3) provide feedthrough of FDS signals between DISPATCH_E and DISPATCH_W:

```systemverilog
// trinity.sv lines 1128–1139 (ROUTER tile connections)
.i_de_to_t6_east_feedthrough    (de_to_t6_east[x]),   // from DISPATCH_W, going east
.o_de_to_t6_east_feedthrough    (de_to_t6_east[x+1]),
.i_de_to_t6_west_feedthrough    (de_to_t6_west[x]),   // from DISPATCH_E, going west
.o_de_to_t6_west_feedthrough    (de_to_t6_west[x-1]),
.o_de_west_to_t6_south          (de_to_t6_coloumn[x][y][1]),  // FDS to this column from west DE
.o_de_east_to_t6_south          (de_to_t6_coloumn[x][y][0]),  // FDS to this column from east DE
```

Each column thus receives two dispatch control signals (one from each dispatch endpoint). The Tensix tile selects based on its location.

---

## 10. Clock Domains and CDC

### 10.1 Clock Domains Summary

| Domain | Signal | Source | Consumer |
|---|---|---|---|
| **AI Clock** (`ai_clk`) | `i_ai_clk` | Chip top | Tensix compute engines, overlay, dispatch AI logic |
| **NOC Clock** (`noc_clk`) | `i_noc_clk` | Chip top | NoC routers, NOC2AXI bridges, EDC ring |
| **DM Clock** (`dm_clk`) | `i_dm_clk` | Chip top | RISC-V DM cores (dispatch managers) |
| **AXI Clock** (`axi_clk`) | `i_axi_clk` | Chip top | AXI master/slave ports (outside trinity boundary) |

### 10.2 CDC Crossings

| Crossing | Module | Mechanism |
|---|---|---|
| `axi_clk` ↔ `noc_clk` | `tt_noc2axi` | `axi_cdc` / `axi_cdc_src` / `axi_cdc_dst` (from `filelist.f`) |
| `noc_clk` ↔ `ai_clk` | Tensix / overlay | `cdc_fifo_gray`, `sync.sv`, `tt_sync3r.sv` |
| `noc_clk` ↔ `dm_clk` | Dispatch | `tt_sync_data_autohs`, `tt_async_fifo` |
| Reset sync | All tiles | `tt_sync_reset_powergood`, `tt_sync2r`, `tt_sync3r` |
| APB CDC | `apb_cdc.sv` | Standard APB CDC cell |

Relevant CDC primitive files (from `filelist.f`):
```
rtl/enc/tt_rtl/common_cells/src/cdc_fifo_gray.sv
rtl/enc/tt_rtl/common_cells/src/sync.sv
rtl/enc/tt_rtl/axi/src/axi_cdc.sv
rtl/enc/tt_rtl/axi/src/axi_cdc_src.sv
rtl/enc/tt_rtl/axi/src/axi_cdc_dst.sv
rtl/enc/tt_rtl/apb/src/apb_cdc.sv
rtl/enc/tt_rtl/tt_soc_common/rtl/sync/tt_sync_data_autohs.sv
rtl/enc/tt_rtl/tt_soc_common/rtl/sync/tt_sync_reset_powergood.sv
rtl/enc/tt_rtl/tt_soc_common/rtl/sync/tt_sync2r.sv
rtl/enc/tt_rtl/tt_soc_common/rtl/sync/tt_sync3r.sv
rtl/enc/tt_rtl/tt_soc_common/rtl/sync/tt_sync3s.sv
```

### 10.3 Harvest and CDC

When a Tensix tile is harvested (held in reset), all its CDC structures remain in their reset state. Since the clock still passes through the tile (Section 6.5), no metastability hazard is introduced by the harvest operation itself. The only requirement is that **reset be asserted before any attempt to access the tile via NoC or EDC**.

---

## 11. Reset Architecture

### 11.1 Active-Low Reset Hierarchy

```
  i_edc_reset_n          ─── used as power_good signal in clock chain
  i_noc_reset_n          ─── NoC clock domain reset
  i_ai_reset_n           ─── AI clock domain reset
  i_dm_core_reset_n[14][8] ─── Per-DM-core reset (RISC-V)
  i_dm_uncore_reset_n[14]  ─── Per-DM-uncore reset
  i_tensix_reset_n[12]     ─── Per-Tensix-tile reset
```

All resets are **synchronous active-low** in the respective clock domain after being synchronized through `tt_sync_reset_powergood` or equivalent synchronizers inside each tile.

### 11.2 Reset Sequencing for Harvest

Recommended reset sequence when applying harvest:

1. Assert `i_tensix_reset_n[TensixIndex] = 0` for all harvested tiles **before** releasing `i_noc_reset_n` and `i_ai_reset_n`. This ensures harvested tiles never receive a valid clock edge in a de-reset state.
2. Assert corresponding `i_dm_core_reset_n` and `i_dm_uncore_reset_n` bits.
3. Program NoC mesh boundaries (Section 7) via EDC packets **after** NOC2AXI tiles are out of reset.
4. Program EDC mux/demux bypass for harvested tiles via the tile's internal harvest control.

### 11.3 Power-Good Signal

The `i_edc_reset_n` input is mapped to `power_good` in the clock routing struct:

```systemverilog
// trinity.sv line 215
assign clock_routing_in[x][y=4].power_good = i_edc_reset_n;
```

This is forwarded through all tiles and used to gate EDC operations until power is stable.

---

## 12. SDC / Timing Notes

### 12.1 Multi-Cycle and False Path Constraints for Harvest

| Signal / Path | SDC treatment |
|---|---|
| `mesh_start_x/y`, `mesh_end_x/y` | Multi-cycle path (static configuration, set once after reset) |
| `noc_x_size`, `noc_y_size` | Multi-cycle path (static harvest configuration) |
| `local_nodeid_x/y` | Multi-cycle path (static) |
| `edc_config_noc_sec.*_sel` bits | False path or multi-cycle (written once via EDC) |
| `i_tensix_reset_n` | False path (quasi-static; only changed during reset sequence) |
| Clock routing pass-throughs (`o_ai_clk`, `o_noc_clk`) | Constrained as clock buffers (special CTS path) |

### 12.2 EDC Ring Timing

The EDC serial ring operates on `noc_clk`. The bypass mux (`tt_edc1_serial_bus_mux`) for harvested tiles introduces a combinational delay. The SDC for the EDC ring must account for the worst-case path including zero, one, or multiple bypass mux stages.

### 12.3 Clock Domain Crossings — Exceptions

- The `axi_clk` domain enters only at the NOC2AXI tile boundary (`i_axiclk` input to `trinity_noc2axi_*`). It does not propagate through the clock chain.
- `dm_clk` is passed through the abutted chain and used only by DM cores inside Tensix/Dispatch tiles.

---

## 13. How to Operate Harvest in RTL (Step-by-Step)

This section describes the complete RTL-level procedure for harvesting a row of Tensix tiles.

### 13.1 Example: Harvest y=0 Row (Bottom Row)

**Step 1: Assert resets for harvested tiles (before system boot)**

At chip top, drive to `0` for each tile in y=0 row:
```
i_tensix_reset_n[0]  = 0  // (x=0, y=0), TensixIndex=0
i_tensix_reset_n[3]  = 0  // (x=1, y=0), TensixIndex=3
i_tensix_reset_n[6]  = 0  // (x=2, y=0), TensixIndex=6
i_tensix_reset_n[9]  = 0  // (x=3, y=0), TensixIndex=9

i_dm_core_reset_n[DmIndex(0,0)][7:0]   = 8'h00
i_dm_uncore_reset_n[DmIndex(0,0)]      = 0
// ...repeat for x=1,2,3 at y=0
```

**Step 2: Release system-wide resets** (`i_noc_reset_n`, `i_ai_reset_n`) with harvested tiles held in reset.

**Step 3: Configure NoC mesh via EDC**

Firmware sends EDC write commands to node index 192 (`SEC_NOC_CONF_IDX`) in each NOC2AXI tile:
```
// Set mesh_start_y_sel=1, mesh_start_y=1 (skip y=0)
// Set noc_y_size_sel=1,  noc_y_size=4   (4 active rows: y=1..4)
// All 4 NOC2AXI tiles must be configured identically
```

**Step 4: EDC bypass for harvested tiles**

The EDC bypass is controlled by `edc_mux_demux_sel` inside each tile. When `i_tensix_reset_n=0`, the tile's internal logic drives `edc_mux_demux_sel=1` to bypass the tile. Firmware does not need to do anything extra for EDC bypass — it is automatic based on reset state.

**Step 5: Configure dispatch**

Firmware must program the dispatch engine (DISPATCH_E / DISPATCH_W) to exclude worker slots corresponding to y=0 Tensix tiles. This is through the dispatch registers (APB interface via `i_reg_*` ports on the dispatch tiles).

### 13.2 Verifying Harvest is Active

After configuration:
- Attempt a NoC read/write to a harvested tile's address — it should time out or return an error (depending on NoC security fence configuration).
- Read EDC status via APB: the EDC ring should still operate correctly (no ring errors), confirming bypass is active.
- Read NoC mesh config readback via EDC noc_sec_controller status.

---

## 14. Register Interface Summary

### 14.1 APB Register Interface (per NOC2AXI tile)

Access via `i_reg_psel/paddr/penable/pwrite/pwdata` on `trinity` top-level (one port per column, `NumApbNodes=4`).

APB index for column x: `getApbIndex(x, y=4)` from `trinity_pkg.sv`.

Contains NoC control registers (address map defined in `tt_noc/registers/svh/`).

### 14.2 EDC APB Interface (per NOC2AXI tile)

Access via `i_edc_apb_psel/paddr/penable/pwrite/pwdata` on `trinity` top-level.

6-bit address (`i_edc_apb_paddr[5:0]`). Accesses `tt_edc1_biu_soc_apb4_wrap` registers.

### 14.3 EDC noc_sec_controller Configuration (Harvest-Specific)

Programmed via EDC packet to node index 192 (`SEC_NOC_CONF_IDX = 192`). Node ID encoding:

```systemverilog
// trinity_noc2axi_nw_opt.sv line 450
.i_node_id({tt_edc1_pkg::NODE_ID_PART_NOC, i_local_nodeid_y[NOC_EDC_NOC_ID_WIDTH-1:0],
            (NOC_EDC_NODE_ID_WIDTH)'(SEC_NOC_CONF_IDX)})
```

Key configuration fields in `edc_reg_noc_sec_output_t` struct (`tt_edc1_reg_structs_pkg`):

| Field | Description | Harvest use |
|---|---|---|
| `size_x_sel` + `size_x` | Override logical X mesh size | Normally not needed (columns always 4) |
| `size_y_sel` + `size_y` | Override logical Y mesh size | **Set to number of active rows** |
| `mesh_start_y_sel` + `mesh_start_y` | Override Y mesh start | **Set to first active row** |
| `mesh_stop_y_sel` + `mesh_stop_y` | Override Y mesh stop | Optional (equals start+size-1) |
| `local_node_id_y_sel` + `local_node_id_y` | Override logical Y coordinate | Needed if physical≠logical Y |
| `orientation_sel` + `orientation` | Override tile orientation | `NOC_ORIENT_0` default |
| `endpoint_id_sel` + `endpoint_id` | Override endpoint ID | Normally not needed |

### 14.4 Interrupt Outputs

```systemverilog
output o_edc_fatal_err_irq [NumApbNodes],  // EDC fatal error per column
output o_edc_crit_err_irq  [NumApbNodes],  // EDC critical error per column
output o_edc_cor_err_irq   [NumApbNodes],  // EDC correctable error per column
output o_edc_pkt_sent_irq  [NumApbNodes],  // EDC packet sent per column
output o_edc_pkt_rcvd_irq  [NumApbNodes],  // EDC packet received per column
```

---

## 15. Key RTL Paths and File Locations

### 15.1 Top-Level and Package Files

| File | Description |
|---|---|
| [rtl/trinity.sv](trinity.sv) | Top-level module; grid instantiation, clock/reset routing, NOC flit wiring |
| [rtl/targets/4x5/trinity_pkg.sv](targets/4x5/trinity_pkg.sv) | Grid dimensions, tile enum, index functions, clock routing struct |
| [rtl/filelist.f](filelist.f) | Complete RTL filelist with include paths and defines |

### 15.2 NOC2AXI Boundary Tiles (Harvest Config Entry Point)

| File | Position | NOC ports active |
|---|---|---|
| [rtl/trinity_noc2axi_nw_opt.sv](trinity_noc2axi_nw_opt.sv) | x=3, y=4 (NW corner) | East + South |
| [rtl/trinity_noc2axi_n_opt.sv](trinity_noc2axi_n_opt.sv) | x=1,x=2, y=4 (North) | East + South + West |
| [rtl/trinity_noc2axi_ne_opt.sv](trinity_noc2axi_ne_opt.sv) | x=0, y=4 (NE corner) | South + West |

All three contain identical harvest configuration logic (EDC noc_sec_controller + mesh override mux).

### 15.3 Other Key Tile RTL (Encrypted, under `rtl/enc/`)

| Module | Location pattern | Role |
|---|---|---|
| `tt_tensix_with_l1` | `enc/tt_rtl/tt_soc_common/...` | Tensix + L1; harvest target |
| `tt_dispatch_top_east` | `enc/tt_rtl/.../tt_dispatch_engine/` | Dispatch east |
| `tt_dispatch_top_west` | (same) | Dispatch west |
| `trinity_router` | [rtl/trinity_router.sv](trinity_router.sv) | NOC-only router tile (y=3, x=1,2) |
| `tt_noc2axi` | `enc/tt_rtl/tt_noc/rtl/noc2axi/` | NOC↔AXI bridge |
| `tt_edc1_noc_sec_controller` | `enc/tt_rtl/tt_edc/rtl/` | EDC harvest config receiver |

### 15.4 CDC and Sync Primitives

```
rtl/enc/tt_rtl/common_cells/src/cdc_fifo_gray.sv
rtl/enc/tt_rtl/axi/src/axi_cdc.sv
rtl/enc/tt_rtl/tt_soc_common/rtl/sync/tt_sync_reset_powergood.sv
rtl/enc/tt_rtl/tt_soc_common/rtl/sync/tt_sync3r.sv
rtl/enc/rtl/primitives/misc/tt_libcell_sync2r.sv
rtl/enc/rtl/primitives/misc/tt_libcell_sync3r.sv
rtl/enc/rtl/primitives/misc/tt_libcell_metastab_hardened_dffr.sv
```

### 15.5 EDC Ring Files

```
rtl/enc/tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_mux.sv
rtl/enc/tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_demux.sv
rtl/enc/tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_repeater.sv
rtl/enc/tt_rtl/tt_edc/rtl/tt_edc1_node.sv
rtl/enc/tt_rtl/tt_edc/rtl/tt_edc1_biu_soc_apb4_wrap.sv
```

### 15.6 Memory / ECC (not harvest-specific, but relevant for L1 testing)

```
rtl/enc/tt_rtl/tt_chip/memories/wrappers/tt_mem_parity_encoder.sv
rtl/enc/tt_rtl/tt_chip/memories/wrappers/prim_secded_147_138_*
rtl/enc/rtl/primitives/wrappers/tt_mem_wrap_3072x128_sp_nomask_selftest_t6_l1.sv
```

---

## 16. Notes for Specific Audiences

### 16.1 Verification Engineer

**What to verify:**
- Reset isolation: Confirm a harvested tile (reset asserted) does not respond to NoC transactions.
- NoC routing: After programming `mesh_start_y`, verify packets route around y=0 correctly without deadlock or misdirection.
- EDC ring continuity: With `edc_mux_demux_sel=1` on a tile, confirm EDC ring functions for remaining tiles.
- Power-on sequence: Verify harvest config is applied before system traffic begins.
- Corner cases: harvest y=2 only (not y=0/y=1), or harvest y=1 + y=2 (two rows).
- Reset fan-in: Confirm `getTensixIndex()` and `getDmIndex()` indexing matches actual connectivity in simulation.

**Simulation hooks:**
```systemverilog
// Back-door L1 preload (from trinity.sv lines 847–849)
`ifdef TRINITY_PRELOAD_T6_L1
  bind tt_tensix_with_l1 t6l1_backdoor t6l1_backdoor_u ();
`endif
```

**Key signal paths to probe:**
- `trinity.gen_x[x].gen_y[y].gen_tensix.tt_tensix_with_l1.i_risc_reset_n`
- `trinity.gen_x[x].gen_y[4].gen_noc2axi_nw_opt.trinity_noc2axi_nw_opt.mesh_start_y`
- `trinity.gen_x[x].gen_y[4].gen_noc2axi_nw_opt.trinity_noc2axi_nw_opt.noc_y_size`

### 16.2 Software / Firmware Engineer

**Harvest configuration sequence (firmware perspective):**

1. Harvest information is typically fused at manufacture (e.g., eFuse) or read from a factory database.
2. On boot, firmware reads which rows are harvested.
3. Via APB to each NOC2AXI tile (one per column, 4 total), program the `edc_noc_sec_controller` with the logical mesh bounds.
4. Program the dispatch engines to exclude harvested worker slots.
5. Advertise the reduced Tensix count to the AI stack (e.g., `NumTensix = 8` if 1 row harvested).

**API surface:**
- APB base address per column: determined by SoC address map (outside trinity module).
- EDC write packet to node 192 per NOC2AXI tile: `{NODE_ID_PART_NOC, local_nodeid_y, 8'd192}`.
- Address within noc_sec registers: per `edc_biu_map_pkg.sv` / `edc1_biu_soc_apb4_pkg.sv`.

### 16.3 Physical Implementation Engineer

**Clock tree:**
- The abutted clock chain (`o_ai_clk`, `o_noc_clk`, `o_dm_clk`) is a **tile-to-tile buffered clock** rather than a chip-level H-tree. CTS must be aware of this: each tile's clock output is the source clock for the tile below.
- Clock buffers are `tt_libcell_clkbuf` (from `rtl/enc/rtl/primitives/misc/tt_libcell_clkbuf.sv`).
- Clock gates are `tt_libcell_clkgate.sv`.

**Reset path:**
- `i_tensix_reset_n` is a quasi-static signal (changes only at power-up). It can be treated as a multi-cycle path. No false paths since it must be synchronized inside tiles.

**EDC bypass wires:**
- The bypass wires (`edc_egress_t6_byp_intf`) connecting a demux output at one tile to a mux input at the same tile are long horizontal/vertical wires that must be routed across possibly large distances in the physical layout. Ensure these are properly buffered.

**Harvest impact on floorplan:**
- Harvested rows are physically present but logically inactive. Their power domains can potentially be shut down if the design supports power gating (not evident from current RTL — `power_good` signal passes through but no explicit power gating cells are seen in this RTL level).
- The clock still runs through harvested tiles (needed for clock chain continuity). If power gating is desired, the clock chain architecture must be revisited.

### 16.4 HW/Microarchitecture Engineer

**Key architectural decisions visible in RTL:**

1. **Harvest granularity is a full row** — the NoC mesh reconfiguration (`mesh_start_y` / `mesh_end_y`) operates on rows, not individual tiles. Single-tile harvest is not directly supported by the mesh config.

2. **NOC2AXI tiles are not harvestable** — they are always at y=4 and always present. The AXI interface width (4 ports, indexed [trinity_pkg::SizeX]) is always fixed.

3. **Dynamic routing is compile-time enabled** — `HAS_DYNAMIC_ROUTING=1'b1` is a hardcoded parameter, not a soft feature. The routing algorithm is always in dynamic mode.

4. **No runtime mesh shrink in X** — The X dimension (`SizeX=4`) is never harvested. `mesh_start_x=0`, `mesh_end_x=SizeX-1` with no provision for X-direction harvest.

5. **Dispatch row is always present** — DISPATCH_E and DISPATCH_W at y=3 are always active. If the Tensix row directly below them (y=2) is harvested, dispatch will have no compute workers in that column until the NoC mesh is reconfigured.

6. **EDC bypass is automatic on reset** — The tile's `edc_mux_demux_sel` is driven by internal reset/harvest state, not by a separate software-programmable register. Firmware does not need to explicitly enable EDC bypass.

---

*Document generated from RTL analysis of `/secure_data_from_tt/20260221/rtl/trinity.sv`, `trinity_pkg.sv`, `trinity_noc2axi_nw_opt.sv`, `trinity_noc2axi_n_opt.sv`, `trinity_noc2axi_ne_opt.sv`, `trinity_router.sv`, and `filelist.f`.*

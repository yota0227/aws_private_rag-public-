# N1B0 Trinity — Hardware Design Document v0.1
**Date:** 2026-03-18
**Author:** Auto-generated from RTL source (`used_in_n1`)
**RTL baseline:** `/secure_data_from_tt/20260221/used_in_n1/`

---

## 1. Overview

N1B0 is a modified Trinity variant targeting the N1 SoC. The key change from baseline Trinity is the replacement of the `trinity_noc2axi_n_opt + trinity_router` tile pair (two separate instantiations) with a new combined **HPDF (High-Performance Dataflow)** tile `trinity_noc2axi_router_ne/nw_opt`, which integrates both the NOC2AXI bridge and the routing tile into a single RTL module spanning two physical rows (Y=4 and Y=3).

Additional changes:
- Grid is **4 × 5** (SizeX=4, SizeY=5), giving 20 tiles total
- Per-column AI/DM clock and reset inputs (instead of single clock)
- Added PRTN (partition) daisy-chain ports for power management
- ISO_EN port for isolation control
- Added NoC repeater buffers between the two middle columns

---

## 2. Package: `trinity_pkg` (4×5 variant)

**File:** `used_in_n1/rtl/targets/4x5/trinity_pkg.sv`

### 2.1 Grid Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `SizeX` | 4 | Columns (X dimension) |
| `SizeY` | 5 | Rows (Y dimension) |
| `NumNodes` | 20 | Total tiles |
| `NumTensix` | 12 | TENSIX tiles (rows 0–2, all 4 columns) |
| `NumNoc2Axi` | 4 | NOC2AXI tiles (row 4) |
| `NumDispatch` | 2 | Dispatch tiles (row 3, X=0 and X=3) |
| `NumApbNodes` | 4 | APB register buses (one per column) |
| `NumDmComplexes` | 14 | DM complexes (TENSIX + DISPATCH tiles) |
| `TensixPerCluster` | 4 | Tensix per column cluster |
| `DMCoresPerCluster` | 8 | DM cores per cluster |
| `EnableDynamicRouting` | 1 | Dynamic routing enabled |

### 2.2 Tile Type Enumeration (`tile_t`, 3-bit)

| Value | Name | Description |
|-------|------|-------------|
| 3'd0 | `TENSIX` | Compute tile (tt_tensix_with_l1) |
| 3'd1 | `NOC2AXI_NE_OPT` | NE corner NOC2AXI bridge (X=0, Y=4) |
| 3'd2 | `NOC2AXI_ROUTER_NE_OPT` | Combined NOC2AXI+Router NE (X=1, Y=4) |
| 3'd3 | `NOC2AXI_ROUTER_NW_OPT` | Combined NOC2AXI+Router NW (X=2, Y=4) |
| 3'd4 | `NOC2AXI_NW_OPT` | NW corner NOC2AXI bridge (X=3, Y=4) |
| 3'd5 | `DISPATCH_E` | East dispatch (X=3, Y=3) |
| 3'd6 | `DISPATCH_W` | West dispatch (X=0, Y=3) |
| 3'd7 | `ROUTER` | Router placeholder (X=1,2, Y=3) — empty in RTL, logic is inside ROUTER_OPT |

> **Note:** Enum 3'd7 (`ROUTER`) is a placeholder entry. In `trinity.sv`, the `gen_router` generate block is empty. The actual router logic for (X=1,Y=3) and (X=2,Y=3) is physically embedded inside `trinity_noc2axi_router_ne_opt` and `trinity_noc2axi_router_nw_opt` respectively, which span both Y=4 and Y=3 grid rows.

### 2.3 `GridConfig` (RTL-verified)

```
GridConfig[y][x]:
      X=0                   X=1                      X=2                      X=3
Y=4   NOC2AXI_NE_OPT        NOC2AXI_ROUTER_NE_OPT    NOC2AXI_ROUTER_NW_OPT    NOC2AXI_NW_OPT
Y=3   DISPATCH_E             ROUTER (placeholder)     ROUTER (placeholder)     DISPATCH_W
Y=2   TENSIX                 TENSIX                   TENSIX                   TENSIX
Y=1   TENSIX                 TENSIX                   TENSIX                   TENSIX
Y=0   TENSIX                 TENSIX                   TENSIX                   TENSIX
```

### 2.4 Endpoint Index Formula

```
EndpointIndex = (x * SizeY) + y  =  x*5 + y
```

| (X,Y) | Tile Type | EndpointIndex |
|--------|-----------|---------------|
| (0,0)  | TENSIX    | 0  |
| (0,1)  | TENSIX    | 1  |
| (0,2)  | TENSIX    | 2  |
| (0,3)  | DISPATCH_E | 3 |
| (0,4)  | NOC2AXI_NE_OPT | 4 |
| (1,0)  | TENSIX    | 5  |
| (1,1)  | TENSIX    | 6  |
| (1,2)  | TENSIX    | 7  |
| (1,3)  | ROUTER (placeholder) | 8 |
| (1,4)  | NOC2AXI_ROUTER_NE_OPT | 9 |
| (2,0)  | TENSIX    | 10 |
| (2,1)  | TENSIX    | 11 |
| (2,2)  | TENSIX    | 12 |
| (2,3)  | ROUTER (placeholder) | 13 |
| (2,4)  | NOC2AXI_ROUTER_NW_OPT | 14 |
| (3,0)  | TENSIX    | 15 |
| (3,1)  | TENSIX    | 16 |
| (3,2)  | TENSIX    | 17 |
| (3,3)  | DISPATCH_W | 18 |
| (3,4)  | NOC2AXI_NW_OPT | 19 |

### 2.5 Index Helper Functions

| Function | Counts |
|----------|--------|
| `getTensixIndex(x,y)` | Scan order: X first (inner), Y second — returns 0..11 |
| `getNoc2AxiIndex(x,y)` | Counts NOC2AXI_ROUTER_NE/NW_OPT and NOC2AXI_NE/NW_OPT |
| `getApbIndex(x,y)` | Same as getNoc2AxiIndex — APB index = column index |
| `getDmIndex(x,y)` | Counts TENSIX + DISPATCH_E + DISPATCH_W tiles |

---

## 3. Top-Level Module: `trinity`

**File:** `used_in_n1/rtl/trinity.sv`
**Module:** `trinity`

### 3.1 Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `AXI_SLV_OUTSTANDING_READS` | 64 | Max in-flight AXI slave reads |
| `AXI_SLV_OUTSTANDING_WRITES` | 32 | Max in-flight AXI slave writes |
| `AXI_SLV_RD_RDATA_FIFO_DEPTH` | 512 | Read data FIFO depth (64/128/256/512/1024 via `define) |
| `NPU_DATA_W` | 512 | AXI data width (localparam) |
| `NPU_IN_ADDR_W` | 56 | AXI master address width (localparam) |
| `NPU_OUT_ADDR_W` | 56 | AXI slave address width (localparam) |

### 3.2 Port Groups

#### Clock & Reset
| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| `i_axi_clk` | 1 | in | AXI clock (single, global) |
| `i_noc_clk` | 1 | in | NoC clock (single, global) |
| `i_noc_reset_n` | 1 | in | NoC reset (active-low) |
| `i_ai_clk` | [SizeX-1:0] | in | AI clock per column (4 clocks) |
| `i_ai_reset_n` | [SizeX-1:0] | in | AI reset per column (4 resets) |
| `i_tensix_reset_n` | [NumTensix-1:0] | in | Per-Tensix reset (12 signals) |
| `i_edc_reset_n` | 1 | in | EDC reset (also used as power_good) |
| `i_dm_clk` | [SizeX-1:0] | in | DM clock per column (4 clocks) |
| `i_dm_core_reset_n` | [NumDmComplexes-1:0][DMCoresPerCluster-1:0] | in | DM core resets (14×8) |
| `i_dm_uncore_reset_n` | [NumDmComplexes-1:0] | in | DM uncore resets (14) |

> **N1B0 change:** Previously single `i_ai_clk` and `i_dm_clk`. Now per-column arrays `[SizeX-1:0]`.

#### APB Register Interface (×4 per column)
| Signal | Width | Direction |
|--------|-------|-----------|
| `i_reg_psel[NumApbNodes]` | 1 | in |
| `i_reg_paddr[NumApbNodes]` | 32 | in |
| `i_reg_penable[NumApbNodes]` | 1 | in |
| `i_reg_pwrite[NumApbNodes]` | 1 | in |
| `i_reg_pwdata[NumApbNodes]` | 32 | in |
| `o_reg_pready[NumApbNodes]` | 1 | out |
| `o_reg_prdata[NumApbNodes]` | 32 | out |
| `o_reg_pslverr[NumApbNodes]` | 1 | out |

#### EDC APB Interface (×4) + IRQs
| Signal | Width | Direction |
|--------|-------|-----------|
| `i_edc_apb_psel[4]` | 1 | in |
| `i_edc_apb_paddr[4]` | 6 | in |
| `i_edc_apb_pwdata[4]` | 32 | in |
| `i_edc_apb_pstrb[4]` | 4 | in |
| `o_edc_apb_pready[4]` | 1 | out |
| `o_edc_apb_prdata[4]` | 32 | out |
| `o_edc_fatal_err_irq[4]` | 1 | out |
| `o_edc_crit_err_irq[4]` | 1 | out |
| `o_edc_cor_err_irq[4]` | 1 | out |
| `o_edc_pkt_sent_irq[4]` | 1 | out |
| `o_edc_pkt_rcvd_irq[4]` | 1 | out |

#### AXI Slave Out (`npu_out_*`, ×4 per column) — NOC→DRAM direction
512-bit data, 56-bit address, full AXI4 channels (AW/W/B/AR/R). Array size `[SizeX]`.

#### AXI Master In (`npu_in_*`, ×4 per column) — DRAM→NOC direction
Same structure as npu_out, array size `[SizeX]`.

#### Memory Config (SFR)
Single-bit and multi-bit SRAM configuration:
`SFR_RF_2P_HSC_*`, `SFR_RA1_HS_*`, `SFR_RF1_HS_*`, `SFR_RF1_HD_*`

#### PRTN (Partition Chain) — N1B0 addition
| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| `PRTNUN_FC2UN_DATA_IN` | 1 | in | PRTN chain data in |
| `PRTNUN_FC2UN_READY_IN` | 1 | in | PRTN chain ready in |
| `PRTNUN_FC2UN_CLK_IN` | 1 | in | PRTN chain clock in |
| `PRTNUN_FC2UN_RSTN_IN` | 1 | in | PRTN chain reset in |
| `PRTNUN_UN2FC_DATA_OUT` | [3:0] | out | PRTN data out (4 columns) |
| `PRTNUN_UN2FC_INTR_OUT` | [3:0] | out | PRTN interrupt out (4 columns) |
| `PRTNUN_FC2UN_DATA_OUT` | [3:0] | out | Pass-through data out |
| `PRTNUN_FC2UN_READY_OUT` | [3:0] | out | Pass-through ready out |
| `PRTNUN_FC2UN_CLK_OUT` | [3:0] | out | Pass-through clock out |
| `PRTNUN_FC2UN_RSTN_OUT` | [3:0] | out | Pass-through reset out |
| `PRTNUN_UN2FC_DATA_IN` | [3:0] | in | Data in from FC |
| `PRTNUN_UN2FC_INTR_IN` | [3:0] | in | Interrupt in from FC |
| `ISO_EN` | [11:0] | in | Isolation enable (3 bits per Tensix row, 4 columns) |
| `TIEL_DFT_MODESCAN` | 1 | in | DFT scan mode |

PRTN chain topology (per column x): external → [x][2] → [x][1] → [x][0] → output

---

## 4. Module Hierarchy

### 4.1 Level-1 Instantiation Map

```
trinity (top)
│
├── gen_x[0] gen_y[4]: gen_noc2axi_ne_opt
│   └── trinity_noc2axi_ne_opt          (X=0, Y=4, EndpointIndex=4)
│
├── gen_x[1] gen_y[4]: gen_noc2axi_router_ne_opt
│   └── trinity_noc2axi_router_ne_opt   (X=1, Y=4+Y=3, EndpointIndex=9)
│       ├── [internal] trinity_noc2axi_n_opt logic  ← Y=4 NoC2AXI
│       └── [internal] trinity_router logic          ← Y=3 Router
│
├── gen_x[2] gen_y[4]: gen_noc2axi_router_nw_opt
│   └── trinity_noc2axi_router_nw_opt   (X=2, Y=4+Y=3, EndpointIndex=14)
│       ├── [internal] trinity_noc2axi_n_opt logic  ← Y=4 NoC2AXI
│       └── [internal] trinity_router logic          ← Y=3 Router
│
├── gen_x[3] gen_y[4]: gen_noc2axi_nw_opt
│   └── trinity_noc2axi_nw_opt          (X=3, Y=4, EndpointIndex=19)
│
├── gen_x[0] gen_y[3]: gen_dispatch_e
│   └── tt_dispatch_top_east            (X=0, Y=3, EndpointIndex=3)
│
├── gen_x[1] gen_y[3]: gen_router       ← EMPTY (no sub-module; handled by router_ne_opt)
├── gen_x[2] gen_y[3]: gen_router       ← EMPTY (no sub-module; handled by router_nw_opt)
│
├── gen_x[3] gen_y[3]: gen_dispatch_w
│   └── tt_dispatch_top_west            (X=3, Y=3, EndpointIndex=18)
│
├── gen_x[*] gen_y[0..2]: gen_tensix (×12)
│   └── tt_tensix_with_l1               (X=0..3, Y=0..2, EndpointIndex=0..17 excl. dispatch/NIU)
│
├── tt_noc_repeaters (NUM_REPEATERS=4)  ← east2west between (1,4)↔(2,4)
├── tt_noc_repeaters (NUM_REPEATERS=4)  ← west2east between (2,4)↔(1,4)
├── tt_noc_repeaters (NUM_REPEATERS=6)  ← east2west between (1,3)↔(2,3)
├── tt_noc_repeaters (NUM_REPEATERS=6)  ← west2east between (2,3)↔(1,3)
│
└── tt_edc1_intf_connector (×N)         ← per-column EDC ring connections
```

### 4.2 Critical Hierarchy Details: `NOC2AXI_ROUTER_*_OPT`

The `trinity_noc2axi_router_ne_opt` (and `_nw_opt`) module occupies **two physical rows** (Y=4 and Y=3):
- Ports prefixed `noc2axi_*` correspond to the Y=4 (NOC2AXI) level
- Ports prefixed `router_*` correspond to the Y=3 (Router) level
- The internal clock/reset chain: Y=4 inputs → internal (no output at Y=4) → drives `router_o_*` which maps to `clock_routing_out[x][y-1]`

Contrast with `NOC2AXI_NE/NW_OPT` which occupies only Y=4:
- Has `o_ai_clk` / `o_dm_clk` driving `clock_routing_out[x][y]` (same row)

### 4.3 `trinity_noc2axi_router_ne_opt` Port Groups

| Prefix | Maps to | Physical row |
|--------|---------|--------------|
| `noc2axi_i_*` | Clock/reset inputs | Y=4 |
| `noc2axi_i_flit_*_east/west` | NoC flit at Y=4 | Y=4 |
| `router_o_ai_clk`, `router_o_dm_clk` | Clock outputs | Y=3 (via clock_routing_out[x][y-1]) |
| `router_o_*_reset_n` | Reset outputs | Y=3 |
| `router_i_flit_*_east/west/south` | Router NoC flits | Y=3 |
| `edc_egress_intf`, `loopback_edc_ingress_intf` | EDC chain | Y=3 index |
| `i_de_to_t6_*`, `o_de_to_t6_*` | Dispatch feedthrough | Y=3 |
| `i/o_noc2axi_*` | AXI master output | Y=4 (to DRAM) |
| `i/o_axi2noc_*` | AXI slave input | Y=4 (from host) |

Note: `o_edc_apb_pready/prdata/pslverr` and `o_edc_*_irq` are present on `_router_ne/nw_opt` with the `i_edc_apb_*` (not `edc_apb_*`) naming convention, unlike `_ne_opt`/`_nw_opt` which use `edc_apb_*` without the `i_` prefix.

---

## 5. NoC Fabric Connections

### 5.1 Y-axis (North/South) Connections
Standard generate-loop connections:
```
flit_in_req[x][y][POSITIVE][Y_AXIS]  = flit_out_req[x][y+1][NEGATIVE][Y_AXIS]   // North neighbor
flit_in_req[x][y][NEGATIVE][Y_AXIS]  = flit_out_req[x][y-1][POSITIVE][Y_AXIS]   // South neighbor
```
South edge (Y=0) ties off to `'{default:0}`.

### 5.2 X-axis (East/West) Connections — Manual (N1B0 change)

N1B0 replaces the generate-loop X connections with manual assigns to insert repeaters.

**Rows Y=0, Y=1, Y=2** (no repeaters):
```
flit_in_req[x][y][POSITIVE][X_AXIS]  = flit_out_req[x+1][y][NEGATIVE][X_AXIS]
```
East edge (X=3) and West edge (X=0) tied off to `'{default:0}`.

**Row Y=3 — Router row** (6 repeaters between X=1 and X=2):
```
// Direct connections:
[0][3]↔[1][3] and [2][3]↔[3][3] are direct assigns
// Repeated connections (6 stages):
[1][3] EAST ↔ [2][3] WEST  via tt_noc_repeaters(NUM_REPEATERS=6)
```
Note: X=0↔X=1 direction uses `POSITIVE`/`NEGATIVE` assigns directly; X=1↔X=2 goes through repeater module.

**Row Y=4 — NOC2AXI row** (4 repeaters between X=1 and X=2):
```
// Direct connections:
[0][4]↔[1][4] and [2][4]↔[3][4] are direct assigns
// Repeated connections (4 stages):
[1][4] EAST ↔ [2][4] WEST  via tt_noc_repeaters(NUM_REPEATERS=4)
```

### 5.3 Repeater Summary

| Instance | NUM_REPEATERS | Connects | Direction |
|----------|---------------|----------|-----------|
| `noc_east2west_req_repeaters_between_noc2axi` | 4 | (1,4)→(2,4) NEGATIVE X | E→W at Y=4 |
| `noc_west2east_req_repeaters_between_noc2axi` | 4 | (2,4)→(1,4) POSITIVE X | W→E at Y=4 |
| `noc_east2west_req_repeaters_between_router` | 6 | (1,3)→(2,3) NEGATIVE X | E→W at Y=3 |
| `noc_west2east_req_repeaters_between_router` | 6 | (2,3)→(1,3) POSITIVE X | W→E at Y=3 |

---

## 6. Clock & Reset Routing

### 6.1 Clock Domains

| Clock | Source | Scope |
|-------|--------|-------|
| `i_axi_clk` | Single input | All NOC2AXI tiles (Y=4) |
| `i_noc_clk` | Single input | NoC globally; bypasses column routing |
| `i_ai_clk[x]` | Per-column | Routed south through `clock_routing_in/out` |
| `i_dm_clk[x]` | Per-column | Routed south through `clock_routing_in/out` |

### 6.2 Clock Routing Structure (`trinity_clock_routing_t`)

```
typedef struct packed {
    logic ai_clk;
    logic noc_clk;
    logic dm_clk;
    logic ai_clk_reset_n;
    logic noc_clk_reset_n;
    logic [SizeY-1:0] dm_uncore_clk_reset_n;        // [4:0]
    logic [SizeY-1:0][DMCoresPerCluster-1:0] dm_core_clk_reset_n;  // [4:0][7:0]
    logic [SizeY-1:0] tensix_reset_n;               // [4:0]
    logic power_good;
} trinity_clock_routing_t;
```

Arrays: `clock_routing_in[SizeX][SizeY]` and `clock_routing_out[SizeX][SizeY]`.

### 6.3 Clock Entry Point

Clocks enter at Y=4 (top row) for each column x:
```
clock_routing_in[x][4].ai_clk      = i_ai_clk[x]
clock_routing_in[x][4].dm_clk      = i_dm_clk[x]
clock_routing_in[x][4].noc_clk     = i_noc_clk      // global
clock_routing_in[x][4].power_good  = i_edc_reset_n  // repurposed
```
Resets are packed: `clock_routing_in[x][4].tensix_reset_n[SizeY-1-yy]` = `i_tensix_reset_n[getTensixIndex(x, yy)]`

### 6.4 Clock Propagation

- Each tile consumes `clock_routing_in[x][y]` and drives `clock_routing_out[x][y]`
- Next row input: `clock_routing_in[x][y] = clock_routing_out[x][y+1]`
- **Exception for `NOC2AXI_ROUTER_*_OPT`:** These modules do NOT expose `clock_routing_out[x][y]` (at Y=4). Instead they drive `clock_routing_out[x][y-1]` (at Y=3) via `router_o_*` ports. The Y=4 clock_routing_out[x][4] is unused/undriven for X=1,2 (NOP in genblock).

---

## 7. EDC Ring

EDC ring uses per-tile interfaces:
```
edc_ingress_intf[SizeX*SizeY]         // flat array [20]
edc_egress_intf[SizeX*SizeY]
loopback_edc_ingress_intf[SizeX*SizeY]
loopback_edc_egress_intf[SizeX*SizeY]
```
Index: `x*SizeY + y` = same as EndpointIndex.

Column-wise chain via `tt_edc1_intf_connector`:
- Y=0..3: `edc_egress[y+1]` → `edc_ingress[y]` (direct)
- Y=0 (bottom): loopback connector closes the ring

For `NOC2AXI_ROUTER_*_OPT` tiles (X=1,2, Y=4):
- Only `edc_egress_intf[x*5+y-1]` and `loopback_edc_ingress_intf[x*5+y-1]` connected (Y=3 index)
- No EDC interface at the Y=4 tile position (ports commented out)

---

## 8. Dispatch Feedthrough (de_to_t6 / t6_to_de)

Dispatch tiles communicate with Tensix tiles via:
- `de_to_t6_coloumn[SizeX][SizeY-1][2]` — per-column vertical broadcast (2 dispatch corners)
- `de_to_t6_east/west[SizeX]` — horizontal feedthrough across columns
- `t6_to_de[SizeX][SizeY-2]` — Tensix → dispatch upward per column
- `t6_to_de_accross_east/west[SizeX][SizeX]` — horizontal feedthrough

The `NOC2AXI_ROUTER_*_OPT` tiles also carry these feedthroughs:
```
.i_de_to_t6_east_feedthrough  (de_to_t6_east[x])
.o_de_to_t6_east_feedthrough  (de_to_t6_east[x+1])
.i_de_to_t6_west_feedthrough  (de_to_t6_west[x])
.o_de_to_t6_west_feedthrough  (de_to_t6_west[x-1])
.o_de_west_to_t6_south        (de_to_t6_coloumn[x][y-1][1])  // → row Y=3
.o_de_east_to_t6_south        (de_to_t6_coloumn[x][y-1][0])
.i_t6_to_de_south             (t6_to_de[x][y-2])
```

---

## 9. PRTN Daisy Chain

The partition control chain is routed per column, through Y=2→1→0:

```
External input → [x][2] ← entry point (highest Tensix row)
                    ↓
                [x][1]
                    ↓
                [x][0] → PRTNUN_FC2UN_*_OUT[x] (unused output)
```

`PRTNUN_UN2FC_DATA_OUT[x]` and `PRTNUN_UN2FC_INTR_OUT[x]` are tapped from `w_left_prtnun_*[x][2]` (the Y=2 tile output).

---

## 10. Memory Config (SFR Ports)

All SRAM configuration signals are broadcast globally to all tiles that contain SRAMs:

| Signal | Width | Tiles receiving |
|--------|-------|-----------------|
| `SFR_RF_2P_HSC_QNAPA/B` | 1 | TENSIX, DISPATCH, NOC2AXI |
| `SFR_RF_2P_HSC_EMAA/B` | [2:0] | TENSIX, DISPATCH, NOC2AXI |
| `SFR_RF_2P_HSC_EMASA` | 1 | TENSIX, DISPATCH, NOC2AXI |
| `SFR_RF_2P_HSC_RAWL` | 1 | TENSIX, DISPATCH, NOC2AXI |
| `SFR_RF_2P_HSC_RAWLM` | [1:0] | TENSIX, DISPATCH, NOC2AXI |
| `SFR_RF1_HS_MCS` | [1:0] | TENSIX, DISPATCH |
| `SFR_RF1_HD_MCS` | [1:0] | TENSIX |
| `SFR_RA1_HS_MCS` | [1:0] | DISPATCH only |

---

## 11. RTL File Map

| Module | File | Location |
|--------|------|----------|
| `trinity` | `trinity.sv` | `used_in_n1/rtl/` |
| `trinity_pkg` | `trinity_pkg.sv` | `used_in_n1/rtl/targets/4x5/` |
| `trinity_noc2axi_router_ne_opt` | `trinity_noc2axi_router_ne_opt.sv` | `used_in_n1/rtl/` |
| `trinity_noc2axi_router_nw_opt` | `trinity_noc2axi_router_nw_opt.sv` | `used_in_n1/rtl/` |
| `trinity_noc2axi_ne_opt` | `trinity_noc2axi_ne_opt.sv` | `used_in_n1/rtl/` |
| `trinity_noc2axi_nw_opt` | `trinity_noc2axi_nw_opt.sv` | `used_in_n1/rtl/` |
| `trinity_router` | `trinity_router.sv` | `used_in_n1/rtl/` (legacy, not instantiated in N1B0) |
| `tt_tensix_with_l1` | (library) | `used_in_n1/tt_rtl/` |
| `tt_dispatch_top_east` | (library) | `used_in_n1/tt_rtl/` |
| `tt_dispatch_top_west` | (library) | `used_in_n1/tt_rtl/` |
| `tt_noc_repeaters` | (library) | `used_in_n1/tt_rtl/` |
| `tt_edc1_intf_connector` | (library) | `used_in_n1/tt_rtl/` |

---

## 12. Hierarchy Verification vs. Package

### 12.1 Package ↔ RTL Consistency Check

| Check | Expected (pkg) | RTL (trinity.sv) | Status |
|-------|----------------|-------------------|--------|
| SizeX=4 | `SizeX=4` | Port arrays `[SizeX]=[4]` | ✅ |
| SizeY=5 | `SizeY=5` | Generate loops `[SizeY-1:0]` | ✅ |
| NumApbNodes=4 | 4 | `i_reg_psel[NumApbNodes]` arrays | ✅ |
| NumTensix=12 | 12 | `i_tensix_reset_n[NumTensix-1:0]` | ✅ |
| NumDmComplexes=14 | 14 | `i_dm_core_reset_n[NumDmComplexes-1:0]` | ✅ |
| GridConfig[4][x]=NOC2AXI_* | row 4 = NIU types | gen_noc2axi_*_opt at Y=4 | ✅ |
| GridConfig[3][3]=DISPATCH_E | X=3,Y=3 | gen_dispatch_e | ✅ |
| GridConfig[3][0]=DISPATCH_W | X=0,Y=3 | gen_dispatch_w | ✅ |
| GridConfig[3][1,2]=ROUTER | X=1,2,Y=3 | gen_router (empty) | ✅ (by design) |
| GridConfig[0..2][*]=TENSIX | 12 tiles | gen_tensix → tt_tensix_with_l1 | ✅ |
| EndpointIndex = x*5+y | formula | localparam in genblock | ✅ |
| APB index = column x | getApbIndex | `i_reg_psel[x]` in all NIU tiles | ✅ |
| EnableDynamicRouting=1 | set | i_noc config passed to all tiles | ✅ |

### 12.2 Key N1B0-Specific Hierarchy Observations

1. **ROUTER placeholder is intentional:** `ROUTER` at (1,3) and (2,3) has no RTL sub-module instantiation. This is correct — the router is embedded inside `NOC2AXI_ROUTER_NE/NW_OPT`. The `ROUTER` enum exists only to reserve the EndpointIndex (8, 13) and silence the "invalid tile" error check.

2. **Dual-row span of `NOC2AXI_ROUTER_*_OPT`:** The `gen_noc2axi_router_ne_opt` generate block is triggered by `GridConfig[y][x] == NOC2AXI_ROUTER_NE_OPT` which is true only at Y=4. The module then internally drives both Y=4 (NOC2AXI) and Y=3 (Router) connections — via `y` and `y-1` respectively in the port connections.

3. **noc_clk bypass:** All tiles receive `i_noc_clk` directly (not from clock_routing_in). The `noc_clk` field inside `trinity_clock_routing_t` is propagated but the actual `noc_clk` passed to sub-modules is always `i_noc_clk`.

4. **No ROUTER standalone module in N1B0 top:** `trinity_router.sv` exists in the directory but is NOT instantiated in `trinity.sv`. It is superseded by the internal router inside `NOC2AXI_ROUTER_*_OPT`.

---

## 13. Differences vs. Original Trinity (Baseline)

| Aspect | Baseline Trinity | N1B0 |
|--------|-----------------|------|
| Grid size | 4×5 (same) | 4×5 |
| NOC2AXI middle tiles (X=1,2) | `trinity_noc2axi_n_opt` + `trinity_router` (separate) | `trinity_noc2axi_router_ne/nw_opt` (combined) |
| Corner NIU tiles (X=0,3) | `trinity_noc2axi_ne/nw_opt` | Same |
| AI/DM clock inputs | Single `i_ai_clk`, `i_dm_clk` | Per-column `[SizeX]` arrays |
| X-axis NoC connections | Generate loop | Manual assigns |
| Inter-column repeaters (Y=4) | None | 4-stage `tt_noc_repeaters` ×2 |
| Inter-column repeaters (Y=3) | None | 6-stage `tt_noc_repeaters` ×2 |
| PRTN chain | Not present | 4-column daisy-chain |
| ISO_EN | Not present | [11:0] isolation enable |
| AXI FIFO depth | Fixed | Compile-time selectable via \`define |
| tile_t enum | 8 entries with NOC2AXI_N_OPT | 8 entries with NOC2AXI_ROUTER_NE/NW_OPT |
| trinity_router.sv | Instantiated | Superseded (not instantiated) |

---

*End of N1B0 HDD v0.1*

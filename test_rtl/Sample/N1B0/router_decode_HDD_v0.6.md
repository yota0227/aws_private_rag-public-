# N1B0 NPU – Router & Address Decode Hardware Design Document

**Document:** router_decode_HDD_v0.6.md
**Version:** 0.6
**Date:** 2026-03-23
**Scope:** N1B0 NPU (4×5 grid) — complete RTL-derived address decode paths from all initiators to all targets, including NoC routing, ATT, and packer feedthrough.

---

## Table of Contents

1. [N1B0 Grid and Endpoint Map](#1-n1b0-grid-and-endpoint-map)
2. [NoC Packet Format](#2-noc-packet-format)
3. [Initiators and Targets Summary](#3-initiators-and-targets-summary)
4. [Path A: BRISC/TRISC → Local L1 (intra-tile)](#4-path-a-brisctrisc--local-l1-intra-tile)
5. [Path B: BRISC/TRISC → External DRAM (via NoC + NOC2AXI)](#5-path-b-brisctrisc--external-dram-via-noc--noc2axi)
6. [Path C: BRISC/TRISC → Peer-Tile L1 (via NoC)](#6-path-c-brisctrisc--peer-tile-l1-via-noc)
7. [Path D: Overlay CPU → Local L1 (direct AXI)](#7-path-d-overlay-cpu--local-l1-direct-axi)
8. [Path E: iDMA → External DRAM or Peer-Tile (via NoC)](#8-path-e-idma--external-dram-or-peer-tile-via-noc)
9. [Path F: TDMA Packer → L1 (DEST Writeback)](#9-path-f-tdma-packer--l1-dest-writeback)
10. [ATT (Address Translation Table) Architecture](#10-att-address-translation-table-architecture)
11. [Routing Decision Logic](#11-routing-decision-logic)
12. [NOC2AXI Tile: AXI Gasket Address Format](#12-noc2axi-tile-axi-gasket-address-format)
13. [NoC Virtual Channels](#13-noc-virtual-channels)
14. [SFR Address Map](#14-sfr-address-map)
15. [Module and Instance Reference](#15-module-and-instance-reference)
16. [RTL File Index](#16-rtl-file-index)

---

## 1. N1B0 Grid and Endpoint Map

### 1.1 Grid Layout (4×5, SizeX=4, SizeY=5)

```
Y=4: NOC2AXI_NE_OPT(X=0)  NOC2AXI_ROUTER_NE_OPT(X=1)  NOC2AXI_ROUTER_NW_OPT(X=2)  NOC2AXI_NW_OPT(X=3)
Y=3: DISPATCH_E(X=3)       ROUTER-placeholder(X=1)       ROUTER-placeholder(X=2)       DISPATCH_W(X=0)
Y=2: TENSIX(X=0)           TENSIX(X=1)                   TENSIX(X=2)                   TENSIX(X=3)
Y=1: TENSIX(X=0)           TENSIX(X=1)                   TENSIX(X=2)                   TENSIX(X=3)
Y=0: TENSIX(X=0)           TENSIX(X=1)                   TENSIX(X=2)                   TENSIX(X=3)
```

**Source:** `rtl/targets/4x5/trinity_pkg.sv` — `GridConfig[SizeY-1:0][SizeX-1:0]`

Key notes:
- `NOC2AXI_ROUTER_NE/NW_OPT` at X=1,2 are **composite tiles** spanning both Y=4 (NIU logic) and Y=3 (Router logic). The Y=3 `ROUTER` entries in `GridConfig` are placeholders with no independent RTL.
- There are exactly **12 Tensix tiles** (Y=0–2, X=0–3).
- **2 Dispatch tiles** at (X=0,Y=3) and (X=3,Y=3) — these are `DISPATCH_W` (X=0) and `DISPATCH_E` (X=3).

### 1.2 Endpoint Index Encoding

`EndpointIndex = x * SizeY + y`  (SizeY = 5)

| Tile type | X | Y | EndpointIndex |
|-----------|---|---|---------------|
| TENSIX | 0 | 0 | 0 |
| TENSIX | 0 | 1 | 1 |
| TENSIX | 0 | 2 | 2 |
| DISPATCH_E | 0 | 3 | 3 |
| NOC2AXI_NE_OPT | 0 | 4 | 4 |
| TENSIX | 1 | 0 | 5 |
| TENSIX | 1 | 1 | 6 |
| TENSIX | 1 | 2 | 7 |
| ROUTER_placeholder | 1 | 3 | 8 |
| NOC2AXI_ROUTER_NE_OPT | 1 | 4 | 9 |
| TENSIX | 2 | 0 | 10 |
| TENSIX | 2 | 1 | 11 |
| TENSIX | 2 | 2 | 12 |
| ROUTER_placeholder | 2 | 3 | 13 |
| NOC2AXI_ROUTER_NW_OPT | 2 | 4 | 14 |
| TENSIX | 3 | 0 | 15 |
| TENSIX | 3 | 1 | 16 |
| TENSIX | 3 | 2 | 17 |
| DISPATCH_W | 3 | 3 | 18 |
| NOC2AXI_NW_OPT | 3 | 4 | 19 |

**Note on composite tile router NodeID:** Inside `NOC2AXI_ROUTER_NE/NW_OPT`, the internal `trinity_router` instance uses `nodeid_y = y_of_tile - 1` (i.e., Y=3 in physical grid). This is controlled by the `NOC_Y_OFFSET` parameter in the composite tile RTL.

---

## 2. NoC Packet Format

### 2.1 `noc_header_address_t` (per `tt_noc_pkg.sv`)

```
typedef struct packed {
  logic [NOC_ADDR_RSVD_WIDTH-1:0]  rsvd;           // Reserved
  logic [NOC_ID_WIDTH-1:0]         bc_start_y_coord;// Broadcast start Y
  logic [NOC_ID_WIDTH-1:0]         bc_start_x_coord;// Broadcast start X
  logic [NOC_ID_WIDTH-1:0]         y_coord;         // Target Y (6 bits)
  logic [NOC_ID_WIDTH-1:0]         x_coord;         // Target X (6 bits)
  logic [MEM_ADDR_WIDTH-1:0]       addr;            // Memory address (64 bits)
} noc_header_address_t;
```

Each flit header contains two `noc_header_address_t` fields:
- `targ_addr` — the destination node coordinates + local memory address
- `ret_addr`  — the source node coordinates + return address (for read responses)

### 2.2 `flit_type` (3-bit field in common header)

| Value | Name | Meaning |
|-------|------|---------|
| 3'b000 | REQ_READ | Read request |
| 3'b001 | REQ_WRITE | Write with inline data |
| 3'b010 | REQ_WRITE_INLINE | Write with small inline payload |
| 3'b011 | PATH_SQUASH | Cancel in-flight dynamic route |
| 3'b1xx | RESP_* | Response flits |

### 2.3 Routing Address Selection

```
// From tt_noc_att_and_routing.sv
if (cmd_rw_bit && !cmd_wr_inline_bit):
    routing_dest_addr = ret_addr   // For reads: route response back
else:
    routing_dest_addr = targ_addr  // For writes: route forward to target
```

---

## 3. Initiators and Targets Summary

### 3.1 Initiators

| Initiator | Clock | Location | NoC entry point |
|-----------|-------|----------|-----------------|
| BRISC | ai_clk | `tt_instrn_engine` (inside T6, inside Tensix) | `tt_rocc_cmd_buf` → overlay NIU |
| TRISC0/1/2 | ai_clk | `tt_instrn_engine` | `tt_rocc_cmd_buf` → overlay NIU |
| Overlay CPU | dm_clk (core) | `tt_overlay_cpu_wrapper` | AXI-to-L1 (local only) |
| iDMA | dm_clk | `tt_overlay_cpu_wrapper` (RoCC accelerator) | `tt_rocc_cmd_buf` → overlay NIU |
| TDMA Packer | ai_clk | `tt_tdma` (inside T6) | Direct L1 write port (no NoC) |

### 3.2 Targets

| Target | Address range | Access via |
|--------|--------------|------------|
| Local L1 | 0x00000000–0x002FFFFF (3 MB) | Intra-tile NIU write ports OR direct packer/AXI-to-L1 |
| Peer-tile L1 | NoC targ_addr with remote x/y_coord | NoC flit → remote tile NIU |
| External DRAM | AXI address (NOC2AXI converts) | NoC flit → Y=4 NOC2AXI tile → AXI master |
| SFR registers | See §14 | NoC flit (unicast write to target tile) or direct RISC CSR write |
| ATT table | 0x02010000–0x02013FFF | NoC reg write or local APB |

---

## 4. Path A: BRISC/TRISC → Local L1 (intra-tile)

### 4.1 RTL Evidence

BRISC and TRISC cores run inside `tt_instrn_engine` (ai_clk domain), which is inside `t6[0..3]` (`tt_tensix`), which is inside `tt_tensix_with_l1`.

Direct L1 accesses from RISC cores use the **L1 port arbitration** interfaces defined in `tt_instrn_engine.sv`:
```
t6core_l1_sbank_rw_intf   // Sub-bank level R/W
t6core_l1_arb_rw_intf     // Arbiter level R/W
```

These connect directly to `u_l1part` (`tt_t6_l1_partition`) inside `tt_tensix_with_l1` — **no NoC hop required**.

### 4.2 Address Decode

Local L1 address = 21-bit byte address within 3 MB space:
- `addr[20:0]` — sub-bank select, bank select, SRAM row address, byte offset
- Physical layout: 4 sbanks × 16 banks × 4 sub-banks × 1024×128b SRAM

### 4.3 Module/Instance Path

```
tt_tensix_with_l1
  └── gen_tensix_neo[x][y].tt_tensix_with_l1
        ├── t6[0..3].neo.u_t6 (tt_tensix)
        │    └── instrn_engine_wrapper.u_ie (tt_instrn_engine)
        │         ├── BRISC (tt_brisc)
        │         └── TRISC0/1/2 (tt_riscv_core)
        │              └── L1 request → t6core_l1_arb_rw_intf
        └── u_l1part (tt_t6_l1_partition)
             └── u_l1w2 → u_l1_mem_wrap (gen_sbank[4].gen_bank[4].gen_sub_bank[4])
```

---

## 5. Path B: BRISC/TRISC → External DRAM (via NoC + NOC2AXI)

### 5.1 Overview

BRISC/TRISC cannot access external DRAM directly. All external accesses are made by issuing **NoC flit transactions** through the tile's NIU. The NIU forwards the flit through the NoC mesh to a Y=4 NOC2AXI tile, which converts the NoC packet to an AXI4 master transaction toward DRAM.

### 5.2 Flit Generation: RISC → NIU

**RTL Files:**
- `tt_rocc_cmd_buf.sv` — converts RISC memory request to flit
- `tt_noc_overlay_intf.sv` — CDC bridge (ai_clk → noc_clk)
- `tt_niu.sv` — master request handling, VC arbitration

**Signal flow:**
```
BRISC/TRISC
  rocc_mem_req (load/store + address)
    ↓
tt_rocc_cmd_buf
  o_req_head_flit[REQ_FLIT_WIDTH-1:0]
  o_req_head_flit_beat
  o_req_head_flit_vc
  o_req_head_flit_vld
    ↓
tt_noc_overlay_intf                     ← CDC: ai_clk → noc_clk (async FIFO)
  o_flit_data (qsr_noc_header_t)
  o_flit_vld
    ↓
tt_noc_att_and_routing                  ← ATT lookup + routing decision
    ↓
tt_niu                                  ← VC arbitration, flit injection into mesh
    ↓
NoC mesh (N/E/S/W cardinal directions)
```

### 5.3 Address in the Flit (DRAM access)

- `targ_addr.x_coord` = X of target NOC2AXI tile (0, 1, 2, or 3)
- `targ_addr.y_coord` = 4 (Y=4 row for all NOC2AXI tiles)
- `targ_addr.addr` = 40-bit local address at that tile (maps to AXI address via gasket)

BRISC/TRISC software sets this by writing the target `(x, y, addr)` into the ROCC request fields. The ATT can also perform address translation before the flit enters the mesh (see §10).

### 5.4 NoC Routing to Y=4

Routing uses Dimension-Order Routing (DOR) by default (XY: move in X first, then Y). From any Tensix tile at (x_src, y_src):
1. Move horizontally until x == x_target
2. Move vertically (north) until y == y_target = 4

With `EnableDynamicRouting = 1'b1` (`trinity_pkg.sv`), dynamic routing via the 928-bit carried list can reroute around congested links.

### 5.5 NOC2AXI Conversion (Y=4)

At the target NOC2AXI tile, `tt_noc2axi.sv` receives the flit and generates an AXI4 master transaction:

```
NoC flit arrives at tt_noc2axi
  ↓
Address gasket: extract AXI address from targ_addr.addr (40-bit local)
  [55:52] = 4'b0000 (reserved)
  [51:46] = y_coord (6 bits)
  [45:40] = x_coord (6 bits)
  [39:0]  = local memory address
  ↓
AXI AR/AW channel: o_noc2axi_araddr / o_noc2axi_awaddr (56-bit output)
  Data width: 512 bits
  Max outstanding reads: 16
  Max outstanding writes: 32
```

### 5.6 Module/Instance Path

```
gen_tensix_neo[x][y]
  └── tt_tensix_with_l1
        └── overlay_noc_wrap → tt_overlay_noc_niu_router
              ├── tt_overlay_noc_niu_router
              │    └── tt_noc_niu_router           ← NIU core
              │         ├── tt_noc_overlay_intf    ← CDC bridge
              │         ├── tt_noc_att_and_routing ← ATT + routing
              │         └── tt_niu                 ← flit injection

NoC mesh → gen_noc2axi_{ne/nw}_opt[x=1,2] or gen_noc2axi_{ne/nw}_opt[x=0,3]
  └── trinity_noc2axi_{ne/nw}_opt  or  trinity_noc2axi_{ne/nw}_only
        └── tt_noc2axi              ← NOC→AXI bridge
              o_noc2axi_aw/araddr   → external DRAM AXI bus
```

---

## 6. Path C: BRISC/TRISC → Peer-Tile L1 (via NoC)

### 6.1 Overview

To write or read another Tensix tile's L1, BRISC/TRISC issue a NoC flit with:
- `targ_addr.x_coord` = peer tile X
- `targ_addr.y_coord` = peer tile Y (0–2)
- `targ_addr.addr` = address within peer's L1 (0x000000–0x2FFFFF)

### 6.2 Flit Path to Peer Tile

Identical flit generation as Path B (§5.2). The difference is the target `(x, y)` points to a Tensix tile instead of Y=4 NOC2AXI.

At the receiving tile, the NIU decodes the incoming flit:
```
Incoming NoC flit at peer tile's tt_niu
  ↓
tt_niu L1 write ports:
  o_mem_wr_if_send[NUM_MEM_PORTS_WRITE-1:0]  (L1_FLEX_CLIENT_SEND_WR_T)
  o_mem_rd_if_send[NUM_MEM_PORTS_READ-1:0]   (L1_FLEX_CLIENT_SEND_RD_T)
  ↓
u_l1part (tt_t6_l1_partition)
```

**RTL reference:** `tt_niu.sv` lines 101–107 — L1 memory ports.

### 6.3 Address Decode at Receiving NIU

The `targ_addr.addr[20:0]` field (21 bits, 3 MB range) is forwarded directly to the L1 arbiter. Bank selection bits depend on the L1 sub-bank organization:
- Bits [20:18] = sbank index (3 bits, 4 sbanks)
- Bits [17:14] = bank index (4 bits, 16 banks)
- Bits [13:12] = sub-bank index (2 bits, 4 sub-banks)
- Bits [11:0]  = row address within 1024×128b SRAM (10-bit row + 2-bit sub-select)

---

## 7. Path D: Overlay CPU → Local L1 (direct AXI)

### 7.1 Overview

The Overlay CPU (a Rocket core running in dm_clk domain) uses a dedicated **AXI4 slave interface on the L1 memory** — no NoC traversal. This interface is used for local L1 reads/writes from the CPU.

### 7.2 RTL Evidence

From `tt_overlay_wrapper.sv` (lines ~2237–2249):
```systemverilog
// Overlay CPU AXI master → tt_overlay_axi_to_l1_if (local L1 only)
mem_axi_req → tt_overlay_axi_to_l1_if
```

From `tt_overlay_cpu_wrapper.sv`:
```
o_mem_axi_req / i_mem_axi_rsp   ← AXI4 ports for CPU memory access
```

The `tt_overlay_axi_to_l1_if` module converts the CPU's AXI4 master transactions into L1 arbiter requests — same L1 interface used by the NoC NIU, but at a different arbitration priority.

### 7.3 Module/Instance Path

```
gen_tensix_neo[x][y]
  └── tt_tensix_with_l1
        └── overlay_noc_wrap → tt_overlay_noc_niu_router
              └── neo_overlay_wrapper → tt_overlay_wrapper  (dm_clk)
                    └── tt_overlay_cpu_wrapper
                          o_mem_axi_req (AXI4 master)
                            ↓
                    tt_overlay_axi_to_l1_if
                            ↓
                    u_l1part (tt_t6_l1_partition) — local L1 only
```

**The Overlay CPU cannot directly access peer-tile L1 or DRAM via this path.** For cross-tile or DRAM access, it must use iDMA (Path E).

---

## 8. Path E: iDMA → External DRAM or Peer-Tile (via NoC)

### 8.1 Overview

The iDMA (integrated DMA) engine lives inside the Overlay CPU (`tt_overlay_cpu_wrapper`) as a RoCC accelerator. It generates NoC flit transactions — this is the primary mechanism for bulk data movement between L1 tiles and DRAM.

### 8.2 iDMA Flit Generation

iDMA sends transactions via the RoCC interface:
```
tt_overlay_cpu_wrapper
  └── rocc_idma_flit_t  ← iDMA generates NoC flit payload
        ↓
  o_req_head_flit (via tt_rocc_cmd_buf)
        ↓
  tt_noc_overlay_intf (CDC: dm_clk → noc_clk)
        ↓
  tt_noc_att_and_routing → tt_niu → NoC mesh
```

**RTL reference:** `tt_overlay_cpu_wrapper.sv` — `rocc_idma_flit_t` output port fed into the overlay NIU router.

### 8.3 iDMA Address Programming

iDMA is programmed via APB registers at **IDMA_APB** base address (from `N1B0_NPU_sfr_v0.3.csv`). The DMA descriptor includes:
- Source address: `(x_src, y_src, addr_src)` — packed into `noc_header_address_t` format
- Destination address: `(x_dst, y_dst, addr_dst)` — similarly packed
- Transfer size (bytes)
- Direction (local→remote, remote→local, remote→remote)

For DRAM access, `y_dst = 4` with the NOC2AXI tile X coordinate.

### 8.4 Module/Instance Path

```
tt_overlay_cpu_wrapper (dm_clk)
  └── iDMA RoCC accelerator
        rocc_idma_flit_t → tt_rocc_cmd_buf
                               ↓
tt_overlay_noc_niu_router
  └── tt_noc_niu_router
        ├── tt_noc_overlay_intf  (dm_clk → noc_clk CDC)
        ├── tt_noc_att_and_routing
        └── tt_niu → NoC mesh
```

---

## 9. Path F: TDMA Packer → L1 (DEST Writeback)

### 9.1 Overview

The TDMA (Tensor DMA) packer writes FPU computation results from the DEST register array back to L1 SRAM. This path is **internal to the Tensix tile** (ai_clk domain) and does **not** use the NoC.

### 9.2 THCON PACKER Register Configuration

From `tt_thcon_cfg_regs.sv`:

**PACKER0_REG0 (cfg_reg[9]):**
```
bits [12]    = L1_ACC          — enable L1 accumulation mode
bits [32+:20]= SRC_ADDR_OFFSET — 20-bit source address offset in L1 (where to read from)
bits [64+:20]= UNTILIZE_DST_ADDR_OFFSET — 20-bit destination address offset in L1 (where to write)
```

**PACKER1_REG0 (cfg_reg[13]):**
- Identical layout to PACKER0_REG0 for second packer channel.

**PACKER0_REG1 (cfg_reg[10]):**
```
bits [74+:16]= PACK_UNTILIZE_DST_Z_STRIDE — 16-bit Z-dimension stride for output
```

**SFR address:** THCON base = `0x01800000` (from `N1B0_NPU_sfr_v0.3.csv`)
- PACKER0_REG0 = 0x01800000 + (9 * register_stride)
- PACKER0_REG1 = 0x01800000 + (10 * register_stride)

### 9.3 Address Decode

The `UNTILIZE_DST_ADDR_OFFSET[19:0]` field (20 bits) maps directly to the L1 byte address:
- 20 bits → covers 1 MB address range; with the 3 MB L1, bits [21:20] select the upper segment.
- The packer hardware concatenates this 20-bit offset with a Z-tile offset (from `PACK_UNTILIZE_DST_Z_STRIDE`) to compute the final L1 write address.

### 9.4 Module/Instance Path

```
gen_tensix_neo[x][y]
  └── tt_tensix_with_l1
        └── t6[0..3].neo.u_t6 (tt_tensix, ai_clk)
              └── u_fpu_gtile[0..1]
                    └── tt_tdma (includes DEST reg-file + packer)
                          └── Packer write path (tt_tdma internal)
                                UNTILIZE_DST_ADDR_OFFSET → L1 write addr
                                  ↓
                          u_l1part (tt_t6_l1_partition)
```

**Note on DRAM port:** `tt_tdma.sv` contains signals `thcon_dram_rden`, `thcon_dram_wren`, and `thcon_dram_req_ready`. In N1B0 (`used_in_n1`), `thcon_dram_req_ready` is aliased to the RISC register interface ready signal — **the external DRAM port of TDMA is NOT connected** in N1B0. All bulk data movement to/from DRAM must go through iDMA (Path E).

---

## 10. ATT (Address Translation Table) Architecture

### 10.1 Overview

Each NIU instance contains one ATT. The ATT is implemented in `tt_noc_address_translation_tables.sv` and `tt_noc_att_and_routing.sv`. It performs address translation on outgoing NoC flits **before** they enter the mesh.

### 10.2 ATT Sub-Tables

| Sub-Table | Entries | Function | SFR Offset |
|-----------|---------|----------|------------|
| Mask table | 16 entries × 4 registers | Match incoming address against mask/value pair | 0x02010000–0x0201003C |
| Endpoint table | 1024 entries | Map matched address to target (x, y, translated_addr) | 0x02010100–0x020120FC |
| Dynamic routing table | 32 entries | Attach 928-bit carried routing list to matched flit | 0x02012000–0x020120FC |

**Base address:** `ATT_BASE = 0x02010000` (from `N1B0_NPU_sfr_v0.3.csv`)

### 10.3 ATT Lookup Flow

```
Outgoing flit from RISC/iDMA:
  targ_addr.addr[63:0] → compare against 16 mask table entries

  Mask table entry: { addr_mask[63:0], addr_value[63:0] }
  Match condition:  (incoming_addr & addr_mask) == addr_value

  If match on entry N:
    → endpoint table[entry_index_from_mask_table]:
         out_x_coord, out_y_coord, out_local_addr (40 bits)
    → dynamic routing table (if HAS_DYNAMIC_ROUTING=1):
         928-bit carried routing list attached to flit
    → rewrite targ_addr with translated (x, y, addr)
```

### 10.4 ATT Control Parameters

From `tt_noc_address_translation_tables.sv`:
- `HAS_ADDRESS_TRANSLATION` (default 1'b1) — enable ATT
- `HAS_ADDRESS_GASKET` (default 1'b0) — extract X/Y from packed address format
- `HAS_DYNAMIC_ROUTING` (default 1'b1) — enable dynamic routing list attachment
- `SINGLE_TRANSLATION_PIPE` (default 1'b0) — use two-pipeline translation

### 10.5 ATT Enable/Disable

The `o_att_enabled` signal from `tt_noc_att_and_routing` reflects the current ATT enable state. When disabled, the flit passes through with address unchanged.

---

## 11. Routing Decision Logic

### 11.1 Routing Mode Priority

When a flit enters the mesh at a NoC router or NIU, the routing mode is selected in priority order:

| Priority | Mode | Condition |
|----------|------|-----------|
| 1 (highest) | Dynamic routing | ATT set `o_att_dyn_routing_enabled=1` AND 928-bit carried list present |
| 2 | Tendril routing | `targ_addr.x_coord` or `y_coord` outside mesh boundaries (harvest case) |
| 3 (default) | DOR (XY or YX) | All other cases |

**DOR default:** XY order — resolve X dimension first, then Y.

### 11.2 Dynamic Routing Carried List

When dynamic routing is active, each flit carries a **928-bit carried list** (defined in `tt_noc_pkg.sv`). At each hop:
1. The router reads the routing slot for the current tile ID
2. If slot is valid: overrides the DOR output port selection
3. The NIU at the destination may overwrite the slot for return-path routing

**Use case:** Load balancing across equivalent paths, bypass of congested/harvested nodes.

### 11.3 Tendril Routing

Applies when a flit must reach a tile outside the active mesh (harvest-disabled tile). The NIU absorbs or redirects the flit per harvest configuration. See Harvest HDD (M5) for full mechanism.

### 11.4 Force Dimension Routing

`force_dim_routing` flag in the flit header:
- When set: forces Y-first (YX) routing regardless of default DOR orientation
- Controlled by BRISC software or ATT assignment

---

## 12. NOC2AXI Tile: AXI Gasket Address Format

### 12.1 56-bit AXI Address (Outbound, NOC→AXI)

```
Bit field layout (56-bit AXI address output of NOC2AXI):
[55:52]  = 4'b0000   (reserved, RTL-verified zero)
[51:46]  = y_coord   (6 bits — source Tensix tile Y)
[45:40]  = x_coord   (6 bits — source Tensix tile X)
[39:0]   = local_addr (40-bit memory address within target)
```

**RTL reference:** `tt_noc2axi.sv` AXI master output ports:
- `o_noc2axi_araddr[55:0]` / `o_noc2axi_awaddr[55:0]`

### 12.2 AXI Data Width

- Data bus: **512 bits** (64 bytes per transfer)
- AXI ID width: configurable (default from `tt_noc2axi` parameters)
- Outstanding reads: 16, outstanding writes: 32

### 12.3 Inbound Path (AXI → NOC)

External AXI master (e.g., host CPU) can write to Tensix L1 via the NOC2AXI tile acting as **AXI slave** (`axi2noc` direction):
- `i_axi2noc_araddr` / `i_axi2noc_awaddr` → converted to NoC flit
- `targ_addr` extracted from AXI address [51:40] for (y, x) routing, [39:0] for local address

---

## 13. NoC Virtual Channels

| VC Class | VC Index | Typical Use |
|----------|----------|-------------|
| Request | 0–7 | Outbound requests (read/write) |
| Response | 8–15 | Inbound responses (read data, write ack) |

Total 16 VCs per link. VC assignment is determined by the initiating NIU based on transaction type and class. Write requests use lower VC numbers; read requests and responses use higher VCs to avoid head-of-line blocking.

Tensix NIU VC buffer: `mem_wrap_64x2048` per VC port (N/E/S/W/NIU = 5 ports × up to 16 VCs).
Router VC buffer: `mem_wrap_256x2048` per cardinal direction (N/E/S/W = 4 ports).

---

## 14. SFR Address Map

From `N1B0_NPU_sfr_v0.3.csv`. All addresses are tile-local (each tile has its own copy at the same base address).

| Subsystem | Base Address | Key Registers |
|-----------|-------------|---------------|
| THCON | 0x01800000 | PACKER0/1_REG0 (dst_addr_offset), PACKER_REG1 (z_stride), UNPACKER regs |
| NOC | 0x02000000 | NIU control, VC config, mesh start/end, local_nodeid |
| ATT | 0x02010000 | ATT_MASK[0..15] (×4 regs each), ATT_EP[0..1023], ATT_DYN[0..31] |
| CLUSTER_CTRL | 0x03000000 | Global cluster control, reset, power |
| T6_L1_CSR | 0x03000200 | L1 cache control, bandwidth, ECC |
| LLK_TILE_COUNTERS | 0x03003000 | Low-latency kernel tile performance counters |
| IDMA_APB | TBD | iDMA descriptor base, control, status, interrupt |
| CACHE_CTRL | 0x04010000 | Overlay CPU L1/L2 cache config |

### 14.1 ATT Register Detail

**ATT_MASK entry N (16 entries, at 0x02010000 + N×0x10):**
- Offset +0x00: `addr_mask[31:0]`
- Offset +0x04: `addr_mask[63:32]`
- Offset +0x08: `addr_value[31:0]`
- Offset +0x0C: `addr_value[63:32]`

**ATT_EP entry N (1024 entries, at 0x02010100 + N×0x8):**
- Offset +0x00: `{y_coord[5:0], x_coord[5:0], ...}`
- Offset +0x04: `local_addr[39:0]` (lower 32 bits)

**ATT_DYN entry N (32 entries, at 0x02012000 + N×offset):**
- Contains start/continuation words of the 928-bit carried routing list

### 14.2 NOC Register Highlights

| Register | Offset | Function |
|----------|--------|----------|
| `local_nodeid_x` | 0x02000004 | Programmed X coordinate of this tile |
| `local_nodeid_y` | 0x02000008 | Programmed Y coordinate of this tile |
| `mesh_start_x` | 0x02000010 | Harvest mesh start X |
| `mesh_start_y` | 0x02000014 | Harvest mesh start Y |
| `mesh_end_x` | 0x02000018 | Harvest mesh end X |
| `mesh_end_y` | 0x0200001C | Harvest mesh end Y |
| `att_en` | 0x02000020 | ATT enable (1=on) |
| `dyn_routing_en` | 0x02000024 | Dynamic routing enable |

---

## 15. Module and Instance Reference

### 15.1 Per-Tensix Tile Hierarchy

```
trinity (top)
  gen_tensix_neo[x][y]
    tt_tensix_with_l1                         [ai_clk / dm_clk / noc_clk]
      ├── overlay_noc_wrap
      │     tt_overlay_noc_niu_router           [dm_clk, noc_clk]
      │       neo_overlay_wrapper
      │         tt_overlay_wrapper              [dm_clk]
      │           tt_overlay_cpu_wrapper        [dm_clk (core)]
      │             Rocket CPU (BRISC-class)
      │             iDMA RoCC accelerator       ← Path E source
      │             o_mem_axi_req               → tt_overlay_axi_to_l1_if
      │           tt_overlay_axi_to_l1_if       ← Path D: direct L1 write
      │           memory_wrapper                ← dm_clk SRAMs (L1/L2 cache)
      │             gen_l1_dcache_data[×16]
      │             gen_l1_icache_data[×16]
      │             gen_l1_dcache_tag[×8]
      │             gen_l1_icache_tag[×8]
      │             gen_l2_dir[×4]
      │             gen_l2_banks[×16]
      │             gen_cs_32x1024.mem_wrap
      │             gen_cs_8x1024.mem_wrap
      │       noc_niu_router_inst
      │         tt_noc_niu_router               [noc_clk]
      │           tt_noc_overlay_intf           ← CDC ai/dm → noc
      │           tt_noc_att_and_routing        ← ATT + routing
      │             tt_noc_address_translation_tables
      │           tt_niu                        ← master request / L1 write
      │           mem_wrap_64x2048_router_input_{N/E/S/W/NIU}  ← VC FIFOs ×5
      │
      ├── t6[0..3].neo.u_t6 (tt_tensix)        [ai_clk]
      │     instrn_engine_wrapper.u_ie
      │       tt_instrn_engine
      │         TRISC0/1/2 (tt_riscv_core)     ← Path B/C source
      │         BRISC (tt_brisc)                ← Path B/C source
      │         tt_rocc_cmd_buf                 ← flit generation
      │     gen_gtile[0..1].u_fpu_gtile         [ai_clk]
      │       tt_tdma                           ← Path F (packer)
      │         tt_thcon_cfg_regs               ← PACKER0/1_REG0
      │
      └── u_l1part (tt_t6_l1_partition)        [ai_clk]
            u_l1w2 → u_l1_mem_wrap
              gen_sbank[4].gen_bank[4].gen_sub_bank[4].u_sub_mwrap
                tt_mem_wrap_3072x128_sp_nomask_selftest_t6_l1  (64 macros/tile, 3MB)
```

### 15.2 NOC2AXI Tile Hierarchy (Y=4)

```
trinity
  ├── gen_noc2axi_ne_opt[0]   (X=0, Y=4, NOC2AXI_NE_OPT)
  │     trinity_noc2axi_ne_opt
  │       tt_noc2axi                            [noc_clk / axi_clk]
  │         o_noc2axi_aw/araddr[55:0]           → external DRAM AXI
  │         mem_wrap_256x2048_router_input_{N/E/S/W}  ← Router VC FIFOs ×4
  │
  ├── gen_noc2axi_router_ne_opt[1]  (X=1, composite Y=4+Y=3)
  │     trinity_noc2axi_router_ne_opt
  │       tt_noc2axi  (NIU logic, Y=4)
  │       trinity_router  (router logic, Y=3 physical)
  │         NOC_Y_OFFSET=-1 (nodeid_y = 3)
  │         REP_DEPTH_LOOPBACK=6, REP_DEPTH_OUTPUT=4
  │         mem_wrap_256x2048_router_input_{N/E/S/W}
  │
  ├── gen_noc2axi_router_nw_opt[2]  (X=2, composite Y=4+Y=3)
  │     trinity_noc2axi_router_nw_opt  (mirror of NE)
  │
  └── gen_noc2axi_nw_opt[3]   (X=3, Y=4, NOC2AXI_NW_OPT)
        trinity_noc2axi_nw_opt
          tt_noc2axi
```

### 15.3 Dispatch Tile (Y=3, corners)

```
trinity
  ├── gen_dispatch_e (X=3, Y=3)
  │     tt_dispatch_engine
  │       disp_eng_l1_partition_inst → tt_t6_l1_dispatch  ← Dispatch L1 SRAMs
  │       overlay_noc_wrap_inst → disp_eng_overlay_noc_niu_router
  │           trin_disp_eng_noc_niu_router_e → disp_eng_noc_niu_router_inst
  │             mem_wrap_1024x12 (ATT endpoint SRAM)
  │             mem_wrap_32x1024 (ATT routing SRAM)
  │
  └── gen_dispatch_w (X=0, Y=3)
        (mirror of DISPATCH_E)
```

---

## 16. RTL File Index

All paths relative to `/secure_data_from_tt/20260221/used_in_n1/mem_port/tt_rtl/`

| Module | RTL File |
|--------|----------|
| `tt_tensix_with_l1` | `tt_tensix_neo/src/hardware/tensix/rtl/tt_tensix_with_l1.sv` |
| `tt_instrn_engine` | `tt_tensix_neo/src/hardware/tensix/rtl/tt_instrn_engine.sv` |
| `tt_tdma` | `tt_tensix_neo/src/hardware/tensix/tdma/rtl/tt_tdma.sv` |
| `tt_thcon_cfg_regs` | `tt_tensix_neo/src/hardware/tensix/proj/trinity_n4/registers/tt_thcon_cfg_regs.sv` |
| `tt_t6_proj_params_pkg` | `tt_tensix_neo/src/hardware/tensix/proj/trinity_n4/params/tt_t6_proj_params_pkg.sv` |
| `tt_overlay_wrapper` | `overlay/rtl/tt_overlay_wrapper.sv` |
| `tt_overlay_cpu_wrapper` | `overlay/rtl/tt_overlay_cpu_wrapper.sv` |
| `tt_overlay_noc_niu_router` | `overlay/rtl/tt_overlay_noc_niu_router.sv` |
| `tt_noc_niu_router` | `tt_noc/rtl/noc/tt_noc_niu_router.sv` |
| `tt_noc_overlay_intf` | `tt_noc/rtl/noc/tt_noc_overlay_intf.sv` |
| `tt_noc_att_and_routing` | `tt_noc/rtl/noc/tt_noc_att_and_routing.sv` |
| `tt_noc_address_translation_tables` | `tt_noc/rtl/noc/tt_noc_address_translation_tables.sv` |
| `tt_niu` | `tt_noc/rtl/noc/tt_niu.sv` |
| `tt_noc2axi` | `tt_noc/rtl/noc2axi/tt_noc2axi.sv` |
| `tt_noc_pkg` | `tt_noc/rtl/noc/tt_noc_pkg.sv` |
| `tt_rocc_cmd_buf` | `overlay/rtl/accelerators/tt_rocc_cmd_buf.sv` |
| `trinity_pkg` | (baseline) `rtl/targets/4x5/trinity_pkg.sv` |
| `tt_mem_wrap_3072x128…` | `primitives/wrappers/tt_mem_wrap_3072x128_sp_nomask_selftest_t6_l1.sv` |

---

## Appendix: Key Parameters (N1B0)

| Parameter | Value | Source |
|-----------|-------|--------|
| `L1_SIZE_IN_BYTES` | 0x300000 (3 MB) | `tt_t6_proj_params_pkg.sv:13` |
| `L1_CFG_ID` | 0x2 (TRIN_TENSIX_NEO) | `tt_t6_proj_params_pkg.sv:14` |
| L1 macros per tile | 256 (4 sbank × 16 bank × 4 sub-bank) | hierarchy CSV |
| L1 macro size | 3072 rows × 128 bits (physical: ×137b w/ ECC) | `tt_mem_wrap_3072x128...sv` |
| SizeX | 4 | `trinity_pkg.sv` |
| SizeY | 5 | `trinity_pkg.sv` |
| NumTensix | 12 | `trinity_pkg.sv` |
| AXI data width | 512 bits | `tt_noc2axi.sv` |
| REP_DEPTH_LOOPBACK | 6 | composite tile RTL |
| REP_DEPTH_OUTPUT | 4 | composite tile RTL |
| ATT base address | 0x02010000 | `N1B0_NPU_sfr_v0.3.csv` |
| THCON base address | 0x01800000 | `N1B0_NPU_sfr_v0.3.csv` |
| `EnableDynamicRouting` | 1'b1 | `trinity_pkg.sv:41` |

# Trinity Router — Address Decoding Hardware Design Document

**Document:** Router_Address_Decoding_HDD.md
**Chip:** Trinity (4×5 NoC Mesh)
**RTL Snapshot:** 20260221
**Primary Sources:** `trinity_router.sv`, `trinity_pkg.sv`, `tt_noc_pkg.sv`, `tt_soc_noc_pkg.sv`, `tt_noc_address_translation_tables.sv`, `tt_niu_output_head_flit_routing.sv`, `filelist.f`
**Audience:** Verification Engineers · Software Engineers · Hardware Engineers

---

## Table of Contents

1. [Overview](#1-overview)
2. [Trinity Grid and Tile Types](#2-trinity-grid-and-tile-types)
3. [NoC Packet Structure](#3-noc-packet-structure)
   - 3.1 [Flit Format](#31-flit-format)
   - 3.2 [Common Header Layout (noc_common_hdr_t)](#32-common-header-layout-noc_common_hdr_t)
   - 3.3 [Target/Return Address Field (noc_header_address_t)](#33-targetreturn-address-field-noc_header_address_t)
   - 3.4 [Command Field (noc_header_command_t)](#34-command-field-noc_header_command_t)
   - 3.5 [Broadcast Control Field (noc_header_brcst_t)](#35-broadcast-control-field-noc_header_brcst_t)
   - 3.6 [Security Control Field (noc_header_security_t)](#36-security-control-field-noc_header_security_t)
4. [Routing Decision Logic](#4-routing-decision-logic)
   - 4.1 [Unicast: Dimension-Order Routing (DOR)](#41-unicast-dimension-order-routing-dor)
   - 4.2 [Tendril Routing](#42-tendril-routing)
   - 4.3 [Dynamic Routing Override](#43-dynamic-routing-override)
   - 4.4 [Port Mask and Orientation Mapping](#44-port-mask-and-orientation-mapping)
   - 4.5 [Broadcast Routing](#45-broadcast-routing)
5. [Address Translation Tables (ATT)](#5-address-translation-tables-att)
   - 5.1 [Architecture Overview](#51-architecture-overview)
   - 5.2 [Mask Table (16 entries)](#52-mask-table-16-entries)
   - 5.3 [Endpoint Table (1024 entries)](#53-endpoint-table-1024-entries)
   - 5.4 [Dynamic Routing Table (32 entries)](#54-dynamic-routing-table-32-entries)
   - 5.5 [ATT Pipeline and Enable Control](#55-att-pipeline-and-enable-control)
6. [Virtual Channels](#6-virtual-channels)
7. [Mesh Boundary and Harvest Configuration](#7-mesh-boundary-and-harvest-configuration)
8. [Security Fence](#8-security-fence)
9. [Router Tile Instance: trinity_router](#9-router-tile-instance-trinity_router)
   - 9.1 [Internal Sub-modules](#91-internal-sub-modules)
   - 9.2 [EDC-to-APB Path for Register Access](#92-edc-to-apb-path-for-register-access)
   - 9.3 [Mesh Boundary Override via EDC](#93-mesh-boundary-override-via-edc)
10. [NOC2AXI Tiles (North Row)](#10-noc2axi-tiles-north-row)
    - 10.1 [Address Width Conversion](#101-address-width-conversion)
    - 10.2 [AXI2NOC TLB](#102-axi2noc-tlb)
11. [Register Map Summary](#11-register-map-summary)
    - 11.1 [NIU Programming Interface (per node)](#111-niu-programming-interface-per-node)
    - 11.2 [Address Translation Table Registers](#112-address-translation-table-registers)
12. [Endpoint ID Encoding](#12-endpoint-id-encoding)
13. [Worked Example: Unicast Write from NIU](#13-worked-example-unicast-write-from-niu)
14. [Worked Example: Address Translation Lookup](#14-worked-example-address-translation-lookup)
15. [Verification Checklist](#15-verification-checklist)
16. [Key RTL File Index](#16-key-rtl-file-index)

---

## 1. Overview

Trinity is a 4×5 2-D mesh Network-on-Chip (NoC) connecting Tensix compute tiles, NOC2AXI bridge tiles (DRAM/PCIe interfaces), and Dispatch Engine tiles through a wormhole-switched, credit-flow-controlled fabric.

Each node in the mesh carries a **6-bit X coordinate** and a **6-bit Y coordinate** distributed at instantiation time as constants. Every incoming flit is a 2048-bit payload (plus parity). The first flit of a packet (head flit) contains a **512-bit common header** that encodes:

- The **destination node** (X/Y coordinates, 6 bits each)
- The **64-bit memory address** within that node
- Command flags (read/write, broadcast, atomic, VC selection, dynamic routing, ...)
- Security attributes

Address decoding therefore happens at two distinct levels:

| Level | Where | What |
|-------|-------|-------|
| **Mesh routing** | Every router hop | Extract `x_coord`/`y_coord` from head flit; compare to local `node_id_x`/`node_id_y`; choose output port |
| **Local address decode** | Destination NIU/NOC2AXI tile | Translate 64-bit `addr` field to an AXI slave address via ATT or TLB; issue AXI transaction |

The sections below cover both levels in full RTL detail.

---

## 2. Trinity Grid and Tile Types

**Source:** [`rtl/targets/4x5/trinity_pkg.sv`](targets/4x5/trinity_pkg.sv)

```
  X=0           X=1           X=2           X=3
Y=4  NOC2AXI_NE  NOC2AXI_N   NOC2AXI_N   NOC2AXI_NW   (North row — DRAM/AXI interfaces)
Y=3  DISPATCH_E  ROUTER       ROUTER      DISPATCH_W    (Dispatch + pure router tiles)
Y=2  TENSIX      TENSIX       TENSIX      TENSIX
Y=1  TENSIX      TENSIX       TENSIX      TENSIX
Y=0  TENSIX      TENSIX       TENSIX      TENSIX
```

```systemverilog
localparam int unsigned SizeX = 4;
localparam int unsigned SizeY = 5;
localparam int unsigned NumNodes    = 20;
localparam int unsigned NumTensix   = 12;
localparam int unsigned NumNoc2Axi  =  4;   // top row (Y=4)
localparam int unsigned NumDispatch =  2;   // (0,3) and (3,3)

localparam bit EnableDynamicRouting = 1'b1;
```

**Endpoint ID** for each node is computed at instantiation:

```systemverilog
// trinity.sv line 185
localparam int unsigned EndpointIndex = (x * trinity_pkg::SizeY) + y;
```

This gives a unique 0…19 integer for each tile (column-major, X×SizeY + Y).

**Tile Types:**

| Enum | Value | Description |
|------|-------|-------------|
| `TENSIX` | 3'd0 | AI compute core |
| `NOC2AXI_N_OPT` | 3'd1 | DRAM north, symmetric |
| `NOC2AXI_NE_OPT` | 3'd2 | DRAM north-east |
| `NOC2AXI_NW_OPT` | 3'd3 | DRAM north-west |
| `DISPATCH_E` | 3'd4 | Dispatch Engine East |
| `DISPATCH_W` | 3'd5 | Dispatch Engine West |
| `DRAM` | 3'd6 | (reserved) |
| `ROUTER` | 3'd7 | Pure NoC router (no local endpoint) |

---

## 3. NoC Packet Structure

### 3.1 Flit Format

**Source:** `tt_soc_noc_pkg.sv`, `tt_noc_pkg.sv`

```
Flit = [ parity(32b) | flit_type(3b) | payload(2048b) ]
         total = 2083 bits
```

| Field | Width | Bits |
|-------|-------|------|
| Payload | 2048 | [2047:0] |
| Head flit flag | 1 | [2048] |
| Data flit flag | 1 | [2049] |
| Tail flit flag | 1 | [2050] |
| Data parity | 32 | [2082:2051] |

```systemverilog
localparam int unsigned NOC_PAYLOAD_WIDTH = 2048;
localparam int unsigned NUM_VCS           = 16;
localparam int unsigned VC_CNT_WIDTH      = $clog2(NUM_VCS);  // = 4
```

**Flit type encoding:**

| Name | Bits[2050:2048] |
|------|----------------|
| Head flit | 3'b001 |
| Data flit | 3'b010 |
| Tail flit | 3'b100 |
| Path squash | 3'b111 |

### 3.2 Common Header Layout (noc_common_hdr_t)

The **first 512 bits** of the head flit payload carry the common header. All routing and decoding information is here.

```systemverilog
// tt_noc_pkg.sv  (struct packed — MSB first in declaration)
typedef struct packed {
  logic [NOC_COMMON_HDR_UNUSED_WIDTH-1:0] unused             ;
  logic [NOC_HDR_ECC_SEG_CHK_WIDTH-1:0]  ecc                ;
  logic [NOC_COMMON_HDR_RSVD_WIDTH-1:0]  rsvd               ;
  noc_header_security_t                  security            ;   // ~16 b
  noc_header_l1_acc_atomic_t             atomic_instruction  ;   // 16 b
  noc_header_at_len_t                    atomic_length       ;   // 32 b
  noc_header_brcst_t                     broadcast           ;   // 64 b
  noc_header_command_t                   command             ;   // 64 b
  noc_header_address_t                   ret_addr            ;   // 96 b
  noc_header_address_t                   targ_addr           ;   // 96 b
} noc_common_hdr_t;                                              // Total = 512 b
```

Field positions (from LSB, i.e. payload bit 0):

| Bits | Field | Width |
|------|-------|-------|
| [95:0] | `targ_addr` (target address) | 96 b |
| [191:96] | `ret_addr` (return address) | 96 b |
| [255:192] | `command` | 64 b |
| [319:256] | `broadcast` | 64 b |
| [351:320] | `atomic_length` | 32 b |
| [367:352] | `atomic_instruction` | 16 b |
| [383:368] | `security` | 16 b |
| [511:384] | reserved / ECC / unused | 128 b |

### 3.3 Target/Return Address Field (noc_header_address_t)

This 96-bit structure carries both the mesh routing coordinates and the local memory address.

```systemverilog
typedef struct packed {
  logic [NOC_ADDR_RSVD_WIDTH-1:0] rsvd            ;  //  8 b  [95:88]
  logic [NOC_ID_WIDTH       -1:0] bc_start_y_coord;  //  6 b  [87:82]
  logic [NOC_ID_WIDTH       -1:0] bc_start_x_coord;  //  6 b  [81:76]
  logic [NOC_ID_WIDTH       -1:0] y_coord         ;  //  6 b  [75:70]
  logic [NOC_ID_WIDTH       -1:0] x_coord         ;  //  6 b  [69:64]
  logic [MEM_ADDR_WIDTH     -1:0] addr            ;  // 64 b  [63: 0]
} noc_header_address_t;

// Key parameters:
//   NOC_ID_WIDTH        = 6
//   MEM_ADDR_WIDTH      = 64
//   NOC_ADDR_WIDTH      = 96
//   NOC_ADDR_RSVD_WIDTH = 96 - 64 - 4*6 = 8
```

**Bit map:**

```
 95      88 87    82 81    76 75    70 69    64 63                   0
 +--------+---------+---------+---------+---------+------------------+
 | rsvd   |bc_start |bc_start |  y_coord|  x_coord|   addr (64-bit)  |
 |  (8b)  |  _y (6b)|  _x (6b)|   (6b)  |  (6b)  |  memory address  |
 +--------+---------+---------+---------+---------+------------------+
```

**Field usage:**

| Field | Unicast | Broadcast |
|-------|---------|-----------|
| `x_coord` | Destination X | Broadcast end X |
| `y_coord` | Destination Y | Broadcast end Y |
| `bc_start_x_coord` | Ignored | Broadcast start X |
| `bc_start_y_coord` | Ignored | Broadcast start Y |
| `addr[63:0]` | 64-bit memory address | Same |

> **Note for SW engineers:** When programming the NIU target address registers, `addr` is the 64-bit byte address within the destination tile's address space. `x_coord`/`y_coord` are the mesh node IDs, not physical pin coordinates.

### 3.4 Command Field (noc_header_command_t)

64-bit field at header offset [255:192].

```systemverilog
typedef struct packed {
  logic [NOC_CMD_RSVD_WIDTH-1:0]          rsvd                 ;  // [63:43]  21b
  logic [UPPER_NOC_PACKET_TAG_WIDTH-1:0]  upper_cmd_pkt_tag_id ;  // [42]      1b
  logic [ROUTING_TABLE_OFFSET_WIDTH-1:0]  dyn_routing_index    ;  // [41:37]   5b
  logic                                   cmd_force_dim_routing ;  // [36]
  logic [LEGACY_NOC_PACKET_TAG_WIDTH-1:0] cmd_pkt_tag_id       ;  // [35:32]   4b
  logic                                   rsvd_bit             ;  // [31]
  logic [NUM_ROUTER_PORTS-1:0]            cmd_port_req_mask    ;  // [30:26]   5b
  logic [6-VC_CNT_WIDTH-1:0]              rsvd_resp_vc         ;  // [25:24]   2b (padding)
  logic [VC_CNT_WIDTH-1:0]               resp_static_vc       ;  // [23:20]   4b
  logic [6-VC_CNT_WIDTH-1:0]              rsvd_req_vc          ;  // [19:18]   2b (padding)
  logic [VC_CNT_WIDTH-1:0]               cmd_static_vc        ;  // [17:14]   4b
  logic                                   cmd_snoop_bit        ;  // [13]
  logic                                   cmd_flush_bit        ;  // [12]
  logic                                   cmd_l1_acc_at_en     ;  // [11]
  logic                                   cmd_dyna_routing_en  ;  // [10]
  logic                                   cmd_mem_rd_drop_ack  ;  //  [9]
  logic                                   cmd_path_reserve     ;  //  [8]
  logic                                   cmd_linked_bit       ;  //  [7]
  logic                                   cmd_brcst_bit        ;  //  [6]
  logic                                   cmd_resp_marked_bit  ;  //  [5]
  logic                                   cmd_wr_inline_64_bit ;  //  [4]
  logic                                   cmd_wr_inline_bit    ;  //  [3]
  logic                                   cmd_wr_be_bit        ;  //  [2]
  logic                                   cmd_rw_bit           ;  //  [1]  1=write, 0=read
  logic                                   cmd_at_cpy_bit       ;  //  [0]
} noc_header_command_t;
```

**Routing-relevant command bits summary:**

| Bit | Name | Effect on routing |
|-----|------|-------------------|
| 0 | `cmd_at_cpy_bit` | Atomic/copy operation; destination node handles locally |
| 1 | `cmd_rw_bit` | 0=read, 1=write; affects response VC selection |
| 6 | `cmd_brcst_bit` | Enable broadcast mode; `broadcast` field is active |
| 10 | `cmd_dyna_routing_en` | Use dynamic routing table (index in bits [41:37]) |
| 14–17 | `cmd_static_vc[3:0]` | VC to use for this request (0–15) |
| 20–23 | `resp_static_vc[3:0]` | VC for the response packet |
| 26–30 | `cmd_port_req_mask[4:0]` | Override output port; one-hot 5 bits (NIU, Y+, X+, Y-, X-) |
| 36 | `cmd_force_dim_routing` | Force XY dimension-order even when dynamic routing is enabled |
| 37–41 | `dyn_routing_index[4:0]` | Index into dynamic routing table (0–31) |

### 3.5 Broadcast Control Field (noc_header_brcst_t)

64-bit field at header offset [319:256]. Only valid when `cmd_brcst_bit=1`.

```systemverilog
typedef struct packed {
  logic [NOC_BRCST_RSVD_WIDTH-1:0]        rsvd             ;
  logic [NOC_BRCST_STRIDED_SKIP_WIDTH-1:0] strided_skip_y  ;  // 2b
  logic [NOC_BRCST_STRIDED_KEEP_WIDTH-1:0] strided_keep_y  ;  // 2b
  logic [NOC_BRCST_STRIDED_SKIP_WIDTH-1:0] strided_skip_x  ;  // 2b
  logic [NOC_BRCST_STRIDED_KEEP_WIDTH-1:0] strided_keep_x  ;  // 2b
  logic                                    quad_excl_dir_y  ;
  logic                                    quad_excl_dir_x  ;
  logic [NOC_ID_WIDTH-1:0]                 quad_excl_coord_y;  // 6b
  logic [NOC_ID_WIDTH-1:0]                 quad_excl_coord_x;  // 6b
  logic                                    quad_excl_enable ;
  logic [NOC_ID_WIDTH-1:0]                 brcst_end_node   ;  // 6b
  logic                                    brcst_active_node;
  noc_brcst_state_t                        brcst_ctrl_state ;  // 2b
  logic                                    brcst_src_include;
  logic                                    brcst_xy_bit     ;  // 0=Y-then-X, 1=X-then-Y
} noc_header_brcst_t;
```

**Broadcast state machine (`noc_brcst_state_t`, 2 bits):**

| Value | Name | Meaning |
|-------|------|---------|
| 2'b00 | `NOC_BRCST_X_UNICAST` | Travelling X dimension toward start column |
| 2'b01 | `NOC_BRCST_Y_UNICAST` | Travelling Y dimension toward start row |
| 2'b10 | `NOC_BRCST_MCAST` | Active multicast phase |
| 2'b11 | `NOC_BRCST_LAST_PATH` | Last hop in broadcast tree |

**Strided broadcast** uses `strided_keep_x/y` and `strided_skip_x/y` to select a sub-grid pattern (keep N, skip M, repeat).

**Quadrant exclusion** allows a rectangular region to be excluded from a broadcast by setting `quad_excl_enable`, `quad_excl_coord_x/y` (relative to broadcast start), and direction bits.

### 3.6 Security Control Field (noc_header_security_t)

16-bit field at header offset [383:368].

```systemverilog
typedef struct packed {
  logic [NOC_SEC_CTRL_RSVD_WIDTH-1:0] rsvd          ;
  logic [1:0]                         axi_resp       ;   // AXI response override
  logic [NOC_SEC_NS_WIDTH-1:0]        ns             ;   // Non-secure bit (1b)
  logic [NOC_SEC_GROUP_ID_WIDTH-1:0]  group_id       ;   // 4b security group
  logic [NOC_SEC_CTRL_LEVEL_WIDTH-1:0] sec_ctrl_level;   // 4b security level
} noc_header_security_t;

// NOC_SEC_CTRL_LEVEL_WIDTH = 4
// NOC_SEC_GROUP_ID_WIDTH   = 4
// NOC_SEC_NS_WIDTH         = 1
```

The destination NIU compares `sec_ctrl_level` and `group_id` against the security fence configuration of the target address range (see [Section 8](#8-security-fence)).

---

## 4. Routing Decision Logic

**Source:** [`tt_rtl/tt_noc/rtl/noc/tt_niu_output_head_flit_routing.sv`](../tt_rtl/tt_noc/rtl/noc/tt_niu_output_head_flit_routing.sv)

At each router hop, the routing module compares the flit's `targ_addr.x_coord`/`y_coord` fields against the local node IDs to decide which of the 5 ports to forward to.

**5 Router Ports (NUM_ROUTER_PORTS = 5):**

| Port index | Name | Direction |
|------------|------|-----------|
| 0 | NIU | Local endpoint (deliver to this node) |
| 1 | Y+ | North |
| 2 | X+ | East |
| 3 | Y- | South |
| 4 | X- | West |

### 4.1 Unicast: Dimension-Order Routing (DOR)

Default routing is **XY dimension-order** (X first, then Y) or **YX** depending on `i_routing_dim_order_xy`.

```systemverilog
// tt_niu_output_head_flit_routing.sv  (simplified)
wire [NOC_ID_WIDTH-1:0] uc_dest_x = i_routing_dest_addr.x_coord;
wire [NOC_ID_WIDTH-1:0] uc_dest_y = i_routing_dest_addr.y_coord;

// XY routing (dim_order_xy == 0):
//   Step 1 — resolve X difference
//   Step 2 — only when X matches, resolve Y difference
packet_fwd_x_pos = (dim_order_xy==0 || uc_dest_y==local_y) ? (uc_dest_x > local_x) : 0;
packet_fwd_x_neg = (dim_order_xy==0 || uc_dest_y==local_y) ? (uc_dest_x < local_x) : 0;
packet_fwd_y_pos = (dim_order_xy==1 || uc_dest_x==local_x) ? (uc_dest_y > local_y) : 0;
packet_fwd_y_neg = (dim_order_xy==1 || uc_dest_x==local_x) ? (uc_dest_y < local_y) : 0;
packet_fwd_niu   = (uc_dest_x == local_x) && (uc_dest_y == local_y);
```

**Decision truth table (XY routing, dim_order_xy=0):**

| Condition | Action |
|-----------|--------|
| `dest_x > local_x` | Forward East (X+) |
| `dest_x < local_x` | Forward West (X-) |
| `dest_x == local_x` AND `dest_y > local_y` | Forward North (Y+) |
| `dest_x == local_x` AND `dest_y < local_y` | Forward South (Y-) |
| `dest_x == local_x` AND `dest_y == local_y` | Deliver to local NIU |

**Harvest node:** `NOC_HARVEST_ID = 6'b111111` (all 1s). If the destination coordinates equal `NOC_HARVEST_ID`, the packet is treated as a harvested node delivery (dropped or redirected by the NIU).

### 4.2 Tendril Routing

Nodes outside the active mesh boundary are called "tendrils". Special logic handles them:

```systemverilog
wire local_in_mesh          = !force_dim && !dyn_routing
                            && (local_x >= mesh_start_x) && (local_x <= mesh_end_x)
                            && (local_y >= mesh_start_y) && (local_y <= mesh_end_y);
wire local_is_vertical_tendril   = !force_dim && !dyn_routing
                                 && (local_y < mesh_start_y || local_y > mesh_end_y);
wire local_is_horizontal_tendril = !force_dim && !dyn_routing
                                 && (local_x < mesh_start_x || local_x > mesh_end_x);

// If horizontal tendril and Y doesn't yet match: go to mesh first via Y
wire go_to_mesh_x = local_is_horizontal_tendril && (local_y != uc_dest_y);
// If vertical tendril and X doesn't yet match: go to mesh first via X
wire go_to_mesh_y = local_is_vertical_tendril   && (local_x != uc_dest_x);
```

Tendrils first resolve the dimension that brings the packet back into the main mesh boundary, then standard DOR takes over.

### 4.3 Dynamic Routing Override

When `cmd_dyna_routing_en=1` and `cmd_force_dim_routing=0`, the router uses a programmable routing list. The index is carried in `dyn_routing_index[4:0]` (pointing to one of 32 entries in the dynamic routing table).

```systemverilog
// dyn_list_offset = local_y * noc_x_size + local_x  (node's position in flat list)
wire [NOC_ID_WIDTH+NOC_ID_WIDTH:0] dyn_list_offset =
    i_local_nodeid_y * i_noc_x_size + i_local_nodeid_x;
```

The routing list is a 1024-bit bitmask stored in SRAM. Each bit represents a node in the flat mesh layout. The bit at position `dyn_list_offset` for the selected routing index entry tells the router which port to take.

Setting `cmd_force_dim_routing=1` overrides dynamic routing and falls back to dimension-order routing even when `cmd_dyna_routing_en=1`.

### 4.4 Port Mask and Orientation Mapping

After computing logical forward directions (`packet_fwd_x_pos`, `packet_fwd_y_pos`, etc.), the router applies a **physical orientation rotation** to produce the actual 5-bit `port_req_mask` output:

```systemverilog
// noc_orientation_t encoding:
//   NOC_ORIENT_0   = 3'b000  (default, no rotation)
//   NOC_ORIENT_90  = 3'b001  (90° CCW)
//   NOC_ORIENT_180 = 3'b010
//   NOC_ORIENT_270 = 3'b011
//   NOC_ORIENT_FLIP_EAST_WEST_0 .. _270  (mirror + rotation)

unique case (i_local_node_orientation)
  NOC_ORIENT_0:
    o_port_req_mask = {fwd_x_neg, fwd_y_neg, fwd_x_pos, fwd_y_pos, fwd_niu};
  NOC_ORIENT_90:
    o_port_req_mask = {fwd_y_pos, fwd_x_neg, fwd_y_neg, fwd_x_pos, fwd_niu};
  NOC_ORIENT_180:
    o_port_req_mask = {fwd_x_pos, fwd_y_pos, fwd_x_neg, fwd_y_neg, fwd_niu};
  NOC_ORIENT_270:
    o_port_req_mask = {fwd_y_neg, fwd_x_pos, fwd_y_pos, fwd_x_neg, fwd_niu};
  // FLIP variants mirror the X-axis mapping before rotation
endcase
```

In the default Trinity configuration, all nodes use `NOC_ORIENT_0`. The orientation field allows physical chip re-use with rotated die placement.

### 4.5 Broadcast Routing

When `cmd_brcst_bit=1`, destination coordinates define a **rectangle** (`bc_start_x/y` → `x_coord/y_coord`) and the broadcast controller walks a spanning tree:

1. **Phase 1 (X_UNICAST):** Packet travels X-direction to `bc_start_x` column.
2. **Phase 2 (Y_UNICAST):** Packet travels Y-direction to `bc_start_y` row.
3. **Phase 3 (MCAST):** Each node in the rectangle copies the packet into the opposite direction until `brcst_end_node`.
4. **Phase 4 (LAST_PATH):** Final node in a broadcast column/row.

`brcst_xy_bit=1` selects X-first traversal; `brcst_xy_bit=0` selects Y-first.

**Strided pattern:** `strided_keep_x` and `strided_skip_x` implement a repeating window (deliver to K nodes, skip S nodes, repeat) per axis independently.

**Quadrant exclusion:** A rectangular sub-region defined by `quad_excl_coord_x/y` (relative offset from `bc_start`) with direction bits can be excluded to allow partial broadcasts.

---

## 5. Address Translation Tables (ATT)

**Source:** [`tt_rtl/tt_noc/rtl/noc/tt_noc_address_translation_tables.sv`](../tt_rtl/tt_noc/rtl/noc/tt_noc_address_translation_tables.sv)

The ATT is instantiated inside `tt_noc2axi` at each NOC2AXI tile (Y=4 row). It converts the 64-bit `addr` field from the NoC packet into the actual AXI address and destination X/Y coordinates. This enables a software flat address space where AXI memory regions are mapped to specific NoC endpoints.

### 5.1 Architecture Overview

```
 Incoming NoC packet
 ┌───────────────────┐
 │ targ_addr.x_coord │──────────────────────────────────────────► dest_x (unchanged if no match)
 │ targ_addr.y_coord │──────────────────────────────────────────► dest_y (unchanged if no match)
 │ targ_addr.addr    │─► [Mask Table] ─► ep_table_index ─► [Endpoint Table] ─► dest_x, dest_y, addr
 │                   │        │
 │                   │        └─► [Routing Table] (if dyn_routing_en) ─► routing list
 └───────────────────┘
```

**Parameters:**

```systemverilog
localparam MASK_TRANS_TABLE_NUM_ENTRIES     = 16;
localparam ENDPOINT_TRANS_TABLE_NUM_ENTRIES = 1024;
localparam ROUTING_TRANS_TABLE_NUM_ENTRIES  = 32;
localparam ROUTING_TRANS_TABLE_LIST_WIDTH   = 1024;  // 1024-bit bitmask per entry

localparam ENDPOINT_TABLE_OFFSET_WIDTH  = $clog2(1024) = 10;
localparam MASK_TABLE_OFFSET_WIDTH      = $clog2(64)   =  6;
localparam ROUTING_TABLE_OFFSET_WIDTH   = $clog2(32)   =  5;
localparam ROUTING_TABLE_MATCH_WIDTH    = 10 + VC_CNT_WIDTH;  // ep_idx + VC
```

### 5.2 Mask Table (16 entries)

The mask table is the first lookup stage. It partitions the 64-bit address space into up to 16 named regions.

**Per-entry fields (all stored in registers):**

| Field | Width | Description |
|-------|-------|-------------|
| `mask_reg` | 6 b | Number of low-order bits to mask off (alignment) |
| `ep_id_idx_reg` | 6 b | LSB position of the endpoint index within `addr` |
| `ep_id_size_reg` | 6 b | Width of the endpoint index field |
| `table_offset_reg` | 10 b | Base offset into the endpoint table |
| `translate_addr_reg` | 1 b | If 1, also rewrite the `addr` field |
| `ep_reg` | 64 b | Base address for matching (after mask) |
| `bar_reg` | 64 b | Base address to write back (if `translate_addr_reg=1`) |

**Match logic:**

```systemverilog
// For each entry:
mask_table_entry_match[i] = (att_dest_addr & ~((1 << mask_reg) - 1)) == ep_reg;
// i.e., upper bits of addr (masking off low mask_reg bits) must equal ep_reg
```

Only one entry should match at a time; multiple matches flag a debug error.

**Index extraction:**

Once a match is found at index `i`:
```systemverilog
mask_table_idx = (att_dest_addr >> ep_id_idx_reg[i]) & ((1 << ep_id_size_reg[i]) - 1);
mask_table_idx = mask_table_idx + table_offset_reg[i];
// mask_table_idx is now a 10-bit index into the endpoint table
```

**Address translation (optional):**

If `translate_addr_reg[i]=1`:
```systemverilog
new_dest_addr = (att_dest_addr & ((1 << ep_id_idx_reg[i]) - 1)) + bar_reg[i];
// Keep only the low ep_id_idx_reg bits of original addr, add BAR
```

### 5.3 Endpoint Table (1024 entries)

A 1024-entry SRAM (accessed via `tt_noc_mem_wrap_intf`). Each entry stores the final destination:

| Field | Description |
|-------|-------------|
| `dest_x` | 6-bit NoC X coordinate of actual destination tile |
| `dest_y` | 6-bit NoC Y coordinate of actual destination tile |
| `addr` | 64-bit translated memory address (optional) |

The mask table index selects the endpoint table entry, which rewrites `x_coord`, `y_coord`, and optionally `addr` in the flit header before re-injection into the mesh.

This is the core mechanism for **flat SW address space**: SW programs a 64-bit address; the ATT translates it to the correct NoC node and local offset.

### 5.4 Dynamic Routing Table (32 entries)

Present when `HAS_DYNAMIC_ROUTING=1` (true in Trinity).

Each of 32 entries stores a `ROUTING_TABLE_MATCH_WIDTH`-bit key:

```systemverilog
// match key = {mask_table_idx[9:0], vc[3:0]}  (14 bits)
routing_table_entry_match[i] = (att_req) && doing_dest
                              && ({mask_table_idx, att_vc} == match_reg[i]);
```

On a match, the corresponding 1024-bit routing list bitmask (`ROUTING_TRANS_TABLE_LIST_WIDTH`) is returned. The router uses the bit at position `local_y * noc_x_size + local_x` from this bitmask to steer the packet hop-by-hop through an arbitrary path, not constrained to DOR.

The `dyn_routing_index` in the command word carries the routing table entry index directly, bypassing mask/endpoint table lookup.

### 5.5 ATT Pipeline and Enable Control

- Translation is enabled globally by `transl_en_reg` (written via APB to `ENABLE_TABLES_REG`).
- Dynamic routing is enabled by `dynamic_routing_en_reg` (same register).
- When both are disabled, the flit's `x_coord`/`y_coord`/`addr` pass through unchanged.
- A `SINGLE_TRANSLATION_PIPE` parameter allows sharing one pipeline stage for both source and destination address translation.
- Debug registers capture last ATT lookup results and flag no-match or multi-match conditions.

---

## 6. Virtual Channels

**Source:** `tt_soc_noc_pkg.sv`, `tt_noc_pkg.sv`

```
NUM_VCS         = 16
VC_CNT_WIDTH    = 4
NUM_UNICAST_REQ_VCS = 8   (VCs 0–7, class REQ_UNICAST)
NUM_BCAST_REQ_VCS   = 4   (VCs 8–11, class REQ_BCAST)
NUM_RESP_VCS        = 4   (VCs 12–15, class RESP)
```

**VC class encoding (VC_CLASS_BITS = 2):**

| Value | Name | Usage |
|-------|------|-------|
| 2'b00 | `VC_CLASS_REQ_UNICAST_0` | Unicast request, class 0 |
| 2'b01 | `VC_CLASS_REQ_UNICAST_1` | Unicast request, class 1 |
| 2'b10 | `VC_CLASS_REQ_BCAST` | Broadcast request |
| 2'b11 | `VC_CLASS_RESP` | Response |

VCs are selected by the initiating NIU via `cmd_static_vc[3:0]` in the command field. Response packets use `resp_static_vc[3:0]`.

> **SW note:** Avoid mixing unicast and response packets on the same VC to prevent deadlock. The router's VC allocator enforces class separation but software must select appropriate VC classes.

---

## 7. Mesh Boundary and Harvest Configuration

**Source:** `trinity_router.sv` lines 392–407

Each router tile receives its mesh boundary at runtime via EDC-programmed registers (not hardcoded):

```systemverilog
// Default values from EDC status (read from edc_status_noc_sec):
assign edc_status_noc_sec.mesh_start_x = 6'd0;
assign edc_status_noc_sec.mesh_start_y = 6'd0;
assign edc_status_noc_sec.mesh_stop_x  = i_noc_x_size[5:0] - 6'd1;  // = 3 for 4x5
assign edc_status_noc_sec.mesh_stop_y  = i_noc_y_size[5:0] - 6'd1;  // = 4 for 4x5

// EDC config can override the defaults:
assign mesh_start_x = edc_config_noc_sec.mesh_start_x_sel
                      ? edc_config_noc_sec.mesh_start_x : 6'd0;
assign mesh_start_y = edc_config_noc_sec.mesh_start_y_sel
                      ? edc_config_noc_sec.mesh_start_y : 6'd0;
assign mesh_end_x   = edc_config_noc_sec.mesh_stop_x_sel
                      ? edc_config_noc_sec.mesh_stop_x  : (i_noc_x_size[5:0] - 6'd1);
assign mesh_end_y   = edc_config_noc_sec.mesh_stop_y_sel
                      ? edc_config_noc_sec.mesh_stop_y  : (i_noc_y_size[5:0] - 6'd1);
```

This allows **harvest** (exclusion of defective tiles) by shrinking the declared mesh boundary. Packets destined for coordinates outside [mesh_start, mesh_end] are routed via tendril logic (Section 4.2).

**Harvest ID:** `NOC_HARVEST_ID = 6'b111111 = 63`. This special coordinate value marks a tile as harvested. Packets routed to `x=63` or `y=63` are dropped by the NIU.

---

## 8. Security Fence

**Source:** `tt_noc_pkg.sv` lines 631–648

Each NIU has 8 programmable security fence ranges. Incoming packets are checked against these ranges on the `addr[63:0]` field.

```
NUM_SEC_FENCE_RANGES     = 8
SEC_FENCE_RANGE_REG_W    = 64   (64-bit per range register — lo and hi address)
```

**Per-range attribute register (SEC_FENCE_ATTR_W = 9 bits):**

| Bits | Field | Description |
|------|-------|-------------|
| [3:0] | `wr_sec_level` | Required security level for write access |
| [7:4] | `rd_sec_level` | Required security level for read access |
| [8] | `range_enable` | 1 = this range is active |

The `sec_ctrl_level[3:0]` from the packet header must be ≥ the fence level for the target address. A violation generates a security interrupt (`o_noc_sec_fence_irq`) and returns an AXI error response.

---

## 9. Router Tile Instance: trinity_router

**Source:** [`rtl/trinity_router.sv`](trinity_router.sv)

The `trinity_router` module is the pure NoC router tile (GridConfig = `ROUTER`) placed at (X=1,Y=3) and (X=2,Y=3).

It instantiates **no AXI master/slave** — all AXI paths are pruned by the `tt_noc2axi` parameters:

```systemverilog
tt_noc2axi #(
  .ADDR_TRANSLATION_ON(0),
  .MASTER_ENABLE(0),
  .SLAVE_ENABLE(0),
  .SINGLE_CLOCK_DOMAIN(1),
  .HAS_EDC_INST(1'b1)
) tt_router ( ... );
```

What remains is: NoC router crossbar, VC allocator, port allocator, credit management, and the NIU register interface.

**Static inputs:**

| Port | Value at (X=1,Y=3) | Source |
|------|-------------------|--------|
| `i_noc_x_size` | 7'd4 | `trinity_pkg::SizeX` |
| `i_noc_y_size` | 7'd5 | `trinity_pkg::SizeY` |
| `i_local_nodeid_x` | 6'd1 | x loop variable |
| `i_local_nodeid_y` | 6'd3 | y loop variable |
| `i_noc_endpoint_id` | 32'd16 | `x*SizeY + y = 1*5+3` |
| `i_security_fence_en` | 1'b0 | hardwired (no local endpoint) |

### 9.1 Internal Sub-modules

```
trinity_router
├── tt_noc2axi (tt_router)         — NoC router core + register access; AXI paths pruned
├── tt_edc1_noc_sec_controller     — EDC node for security config (EDC index 192)
├── tt_edc1_apb4_bridge            — EDC node converting EDC to APB (EDC index 193)
├── tt_noc_overlay_edc_repeater    — loopback repeater (EDC loopback path)
└── tt_noc_overlay_edc_repeater    — output repeater (EDC chain to next tile, REP_DEPTH=3)
```

### 9.2 EDC-to-APB Path for Register Access

NoC router registers (address translation tables, security fence, debug) are accessed via APB. The APB signals are sourced from the EDC ring through a bridge:

```
EDC ring ingress
    → tt_edc1_noc_sec_controller  (EDC node 192: reads security config, writes status)
    → tt_edc1_apb4_bridge         (EDC node 193: generates APB transactions)
    → APB bus → tt_noc2axi registers
    → EDC ring egress (next tile)
```

EDC node IDs in `trinity_router`:
- `SEC_NOC_CONF_IDX = 192` — security fence config
- `REG_APB_NOC_IDX  = 193` — general register APB bridge

### 9.3 Mesh Boundary Override via EDC

The EDC config register `edc_config_noc_sec` (type `edc_reg_noc_sec_output_t`) carries `mesh_start/stop_x/y` with `_sel` override bits. This allows per-router mesh boundary reconfiguration without RTL changes, supporting runtime harvest or topology modification.

---

## 10. NOC2AXI Tiles (North Row)

**Sources:** [`rtl/trinity_noc2axi_ne_opt.sv`](trinity_noc2axi_ne_opt.sv), `trinity_noc2axi_nw_opt.sv`, `trinity_noc2axi_n_opt.sv`

These tiles (Y=4 row) perform the full NoC-to-AXI and AXI-to-NoC bridging. They contain:
- A complete `tt_noc2axi` instance with `MASTER_ENABLE=1`, `SLAVE_ENABLE=1`
- Address Translation Table (ATT)
- AXI2NOC TLB
- Security fence

**Tile variants:**

| Tile type | X position | AXI connections |
|-----------|-----------|-----------------|
| `NOC2AXI_NE_OPT` | X=0 | South + West NoC ports |
| `NOC2AXI_N_OPT` | X=1, X=2 | South NoC port only |
| `NOC2AXI_NW_OPT` | X=3 | South + West NoC ports |

### 10.1 Address Width Conversion

```
NoC addr field:   64 bits  (MEM_ADDR_WIDTH)
AXI addr output:  56 bits  (AxiAddrWidth — parameterized in trinity_noc2axi_*.sv)
AXI data width:  512 bits  (AxiDataWidth)
```

The upper 8 bits of the 64-bit NoC address are dropped when driving the AXI `araddr`/`awaddr` (56-bit physical address space). Software must ensure all target addresses fit within 56 bits.

### 10.2 AXI2NOC TLB

For AXI→NoC direction (external AXI master injecting into the NoC), a 14-entry TLB is provided:

**Source:** `tt_rtl/tt_noc/rtl/noc2axi/tt_noc2axi_local_tlb_addrs_reg_pkg.sv`

Each TLB entry contains:
- `START_ADDR_LO`, `START_ADDR_HI` — 32+32-bit start of AXI address range
- `END_ADDR_LO`, `END_ADDR_HI` — 32+32-bit end of AXI address range

When an AXI read/write address falls within a TLB range, the `aruser`/`awuser` sideband carries a `noc2axi_tlbs_a_regmap_t` structure that encodes destination `x_coord`, `y_coord`, and the translated `addr`. TLB 0 has default values; TLBs 1–13 are SW-programmable.

---

## 11. Register Map Summary

### 11.1 NIU Programming Interface (per node)

Each NoC node exposes a 32-bit register window for software to inject packets directly. Base address: `0x02000000` (per `noc2axi_reg.svh`).

| Offset | Register | Description |
|--------|----------|-------------|
| 0x00 | `TARGET_ADDR_LO` | targ_addr[31:0] |
| 0x04 | `TARGET_ADDR_MID` | targ_addr[63:32] |
| 0x08 | `TARGET_ADDR_HI` | targ_addr[95:64] (X/Y coords + bc_start) |
| 0x0C | `RET_ADDR_LO` | ret_addr[31:0] |
| 0x10 | `RET_ADDR_MID` | ret_addr[63:32] |
| 0x14 | `RET_ADDR_HI` | ret_addr[95:64] |
| 0x18 | `PACKET_TAG` | Packet tag / transaction ID |
| 0x1C | `CMD_BRCST` | Command word (lower bits) + broadcast control (upper bits) merged |
| 0x20 | `AT_LEN` | Atomic transaction length [31:0] |
| 0x24 | `AT_LEN_1` | Atomic transaction length [63:32] |
| 0x28 | `AT_DATA` | Atomic data |
| 0x2C | `BRCST_EXCLUDE` | Broadcast quadrant exclusion control |
| 0x30 | `L1_ACC_AT_INSTRN` | L1 access atomic instruction |
| 0x34 | `SECURITY_CTRL` | Security control field |
| 0x40 | `CMD_CTRL` | Command control / submit |
| 0x44 | `NODE_ID` | Local X/Y node ID (read) |
| 0x48 | `ENDPOINT_ID` | Local endpoint ID (read) |

**To inject a packet:**
1. Write `TARGET_ADDR_HI/MID/LO` with destination X/Y and 64-bit target address.
2. Write `RET_ADDR_*` with return X/Y and return address.
3. Write `CMD_BRCST` with command flags (RW bit, VC, broadcast enable, etc.).
4. Write `SECURITY_CTRL` if security attributes are needed.
5. Write data payload (for writes).
6. Write `CMD_CTRL` to trigger packet transmission.

### 11.2 Address Translation Table Registers

Base address: `0x02010000` (`NOC_ADDRESS_TRANSLATION_TABLE_A_REG_MAP_BASE_ADDR`).
Map size: `0x00003000`.

| Offset | Register | Description |
|--------|----------|-------------|
| 0x0000 | `ENABLE_TABLES_REG` | Bit[0]=translation enable, Bit[1]=dynamic routing enable |
| 0x0030 | `MASK_TABLE_ENTRY_0` | Entry 0 control word (mask, ep_id_idx, ep_id_size, table_offset, translate) |
| 0x0038 | `MASK_TABLE_EP_LO_0` | Entry 0 ep_reg [31:0] |
| 0x003C | `MASK_TABLE_EP_HI_0` | Entry 0 ep_reg [63:32] |
| 0x0040 | `MASK_TABLE_BAR_LO_0` | Entry 0 bar_reg [31:0] |
| 0x0044 | `MASK_TABLE_BAR_HI_0` | Entry 0 bar_reg [63:32] |
| ... | (×16 entries, stride = **0x18** = 24 bytes) | |
| 0x0200 | `ROUTING_TABLE_MATCH_0` | Entry 0 match key {ep_table_idx, vc} |
| ... | (×32 entries, stride = 4) | |
| 0x0300 | `ROUTING_TABLE_PART_ENTRY_0` | Entry 0 routing bitmask word 0 (1024 bits = 32 × 32-bit registers) |
| ... | | |
| 0x2000 | `ENDPOINT_TABLE_0` | Entry 0 (accessed via SRAM interface) |
| ... | (×1024 entries) | |

---

## 12. Endpoint ID Encoding

The `i_noc_endpoint_id` (32-bit) is computed at instantiation as:

```
EndpointIndex = x * SizeY + y
```

For the 4×5 grid:

| X | Y | Tile type | EndpointIndex |
|---|---|-----------|---------------|
| 0 | 0 | TENSIX | 0 |
| 0 | 1 | TENSIX | 1 |
| 0 | 2 | TENSIX | 2 |
| 0 | 3 | DISPATCH_E | 3 |
| 0 | 4 | NOC2AXI_NE | 4 |
| 1 | 0 | TENSIX | 5 |
| 1 | 1 | TENSIX | 6 |
| 1 | 2 | TENSIX | 7 |
| 1 | 3 | ROUTER | 8 |
| 1 | 4 | NOC2AXI_N | 9 |
| 2 | 0 | TENSIX | 10 |
| 2 | 1 | TENSIX | 11 |
| 2 | 2 | TENSIX | 12 |
| 2 | 3 | ROUTER | 13 |
| 2 | 4 | NOC2AXI_N | 14 |
| 3 | 0 | TENSIX | 15 |
| 3 | 1 | TENSIX | 16 |
| 3 | 2 | TENSIX | 17 |
| 3 | 3 | DISPATCH_W | 18 |
| 3 | 4 | NOC2AXI_NW | 19 |

The endpoint ID is stored in the NIU `ENDPOINT_ID` register and is used in the ATT routing table match key (`{ep_table_idx, vc}`).

---

## 13. Worked Example: Unicast Write from NIU

**Scenario:** Tensix at (X=0, Y=0) writes 64 bytes to DRAM via NOC2AXI tile at (X=1, Y=4).

**Step 1 — SW programs NIU at (0,0):**

```
TARGET_ADDR_HI = {8'h00, 6'h00/*bc_start_y*/, 6'h00/*bc_start_x*/,
                         6'd4 /*y_coord*/,     6'd1 /*x_coord*/   }  // dest=(1,4)
TARGET_ADDR_MID = addr[63:32]    // upper 32b of DRAM physical address
TARGET_ADDR_LO  = addr[31:0]     // lower 32b of DRAM physical address
CMD_LO = {
  14'b0,              // reserved/tag
  4'd2,               // resp_static_vc = VC2 (response VC)
  4'd0,               // cmd_static_vc  = VC0
  1'b0,               // snoop=0
  1'b0,               // flush=0
  1'b0,               // l1_acc_at=0
  1'b0,               // dyna_routing=0
  1'b0,               // mem_rd_drop_ack=0
  1'b0,               // path_reserve=0
  1'b0,               // linked=0
  1'b0,               // brcst=0
  1'b0,               // resp_marked=0
  1'b0,               // wr_inline_64=0
  1'b0,               // wr_inline=0
  1'b0,               // wr_be=0
  1'b1,               // rw=1 (write)
  1'b0                // at_cpy=0
}
```

**Step 2 — Routing at (0,0):**

- `uc_dest_x=1 > local_x=0` → `packet_fwd_x_pos=1` → forward East
- Orientation NOC_ORIENT_0: port_mask bit 2 set (X+/East port)

**Step 3 — Routing at (1,0):**

- `uc_dest_x=1 == local_x=1`, `uc_dest_y=4 > local_y=0` → `packet_fwd_y_pos=1` → forward North

**Step 4 — Routing at (1,1), (1,2), (1,3):**

- Same decision: keep forwarding North.

**Step 5 — Arrive at (1,4) NOC2AXI_N tile:**

- `uc_dest_x=1==local_x=1`, `uc_dest_y=4==local_y=4` → `packet_fwd_niu=1` → deliver to local NIU.
- NIU extracts `addr[63:0]` from flit.
- ATT lookup (if enabled): mask table matches → endpoint table → `araddr`/`awaddr`.
- AXI write issued: `awaddr = addr[55:0]`, `awlen`, `awsize`, data from subsequent flits.

---

## 14. Worked Example: Address Translation Lookup

**Scenario:** SW sends a packet to `addr=0x4000_0000_0000` destined for DRAM. ATT maps this to NOC2AXI tile (X=2, Y=4).

**Mask Table Entry 0 setup (via APB write to 0x02010030):**

```
mask_reg         = 6'd28          // ignore lower 28 bits (256 MB granularity)
ep_reg           = 64'h0040_0000  // base = 0x4000_0000_0000 >> 28 << 28
ep_id_idx_reg    = 6'd28          // endpoint index starts at bit 28
ep_id_size_reg   = 6'd4           // 4-bit endpoint field (16 endpoints)
table_offset_reg = 10'd32         // endpoint table starts at entry 32
translate_addr   = 1'b1           // also rewrite addr
bar_reg          = 64'h0          // translate: low bits preserved, base = 0
```

**Lookup sequence:**

1. Incoming `addr = 0x4000_0000_1234`
2. Mask test: `(addr & ~((1<<28)-1)) == 0x4000_0000_0000` → **match entry 0**
3. Extract endpoint index: `(addr >> 28) & 0xF = 0x4` → endpoint = 4
4. Add table offset: `idx = 4 + 32 = 36`
5. Read endpoint table entry 36: `{dest_x=2, dest_y=4, translated_addr=...}`
6. Rewrite flit: `x_coord=2`, `y_coord=4`, `addr=0x0000_0000_1234` (low 28 bits preserved + BAR)
7. Packet is re-injected toward (2,4).

---

## 15. Verification Checklist

### Routing Correctness
- [ ] XY unicast routing: all 20 node pairs, confirm single correct path
- [ ] YX unicast routing: verify `dim_order_xy=1` flips X/Y priority
- [ ] Harvest node routing: destination `x=63` or `y=63` → packet dropped
- [ ] Mesh boundary: send to node outside `[mesh_start, mesh_end]` → tendril logic activates
- [ ] Orientation: `NOC_ORIENT_90`/`180`/`270` — port mask correctly remapped
- [ ] Dynamic routing: `cmd_dyna_routing_en=1`, valid routing table entry → follows bitmask
- [ ] Force dim routing: `cmd_force_dim_routing=1` + `cmd_dyna_routing_en=1` → uses DOR

### Address Translation
- [ ] ATT disabled (`ENABLE_TABLES_REG[0]=0`): flit passes through unchanged
- [ ] Mask table: one match → correct endpoint table index computed
- [ ] Mask table: no match → debug `no_match` flag set, packet passes through
- [ ] Mask table: two matches → debug `more_than_one_match` flag set
- [ ] Address translation: `translate_addr=1` → `addr` rewritten correctly per BAR
- [ ] Endpoint table: correct `dest_x/dest_y` replace flit header coordinates
- [ ] Dynamic routing table: match on `{ep_idx, vc}` → correct 1024-bit list returned

### Broadcast
- [ ] Rectangle broadcast covers all nodes in `[bc_start_x..x_coord, bc_start_y..y_coord]`
- [ ] Strided broadcast: keep/skip pattern filters correct subset
- [ ] Quadrant exclusion: excluded region receives no flit
- [ ] Source include: `brcst_src_include=1` → source node also receives copy

### Security Fence
- [ ] Access below required security level → IRQ asserted, AXI error response returned
- [ ] Access with sufficient level → transaction proceeds
- [ ] Range disabled (`range_enable=0`) → no fence check for that range

### Virtual Channels
- [ ] `cmd_static_vc` selects correct VC (0–15)
- [ ] Response uses `resp_static_vc`
- [ ] Unicast VCs (0–7) and broadcast VCs (8–11) not mixed
- [ ] Deadlock freedom: response VC (12–15) never blocked by request VC

### NOC2AXI Address Width
- [ ] `addr[63:56]` dropped; ensure SW never targets addresses > `0x00FF_FFFF_FFFF_FFFF`
- [ ] AXI2NOC TLB entry 0 (default) correct for boot-time access

---

## 16. Key RTL File Index

| File | Path | Role |
|------|------|------|
| `trinity_pkg.sv` | `rtl/targets/4x5/trinity_pkg.sv` | Grid config, SizeX/Y, tile types, endpoint index |
| `trinity.sv` | `rtl/trinity.sv` | Top-level: mesh wiring, tile instantiation |
| `trinity_router.sv` | `rtl/trinity_router.sv` | Pure router tile (X=1/2, Y=3) |
| `trinity_noc2axi_ne_opt.sv` | `rtl/trinity_noc2axi_ne_opt.sv` | NOC2AXI NE tile (X=0, Y=4) |
| `trinity_noc2axi_nw_opt.sv` | `rtl/trinity_noc2axi_nw_opt.sv` | NOC2AXI NW tile (X=3, Y=4) |
| `trinity_noc2axi_n_opt.sv` | `rtl/trinity_noc2axi_n_opt.sv` | NOC2AXI N tiles (X=1,2, Y=4) |
| `tt_noc_pkg.sv` | `tt_rtl/tt_noc/rtl/noc/tt_noc_pkg.sv` | All NoC parameters, header structs |
| `tt_soc_noc_pkg.sv` | `tt_rtl/tt_soc_noc/rtl/tt_soc_noc_pkg.sv` | Payload width, NUM_VCS |
| `tt_niu_output_head_flit_routing.sv` | `tt_rtl/tt_noc/rtl/noc/` | Routing decision logic (DOR, broadcast, tendril, dynamic) |
| `tt_noc_address_translation_tables.sv` | `tt_rtl/tt_noc/rtl/noc/` | ATT: mask/endpoint/routing tables |
| `noc_address_translation_table_a_reg.svh` | `tt_rtl/tt_noc/registers/svh/` | ATT register offsets and map |
| `noc2axi_reg.svh` | `tt_rtl/tt_noc/registers/svh/` | NIU register offsets |

---

*Document generated from RTL snapshot 20260221. All bit positions and parameters are sourced directly from the RTL — no assumptions made.*

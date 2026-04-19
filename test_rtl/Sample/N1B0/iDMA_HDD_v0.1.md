# N1B0 NPU – iDMA Hardware Design Document

**Document:** iDMA_HDD_v0.1.md
**Version:** 0.1
**Date:** 2026-03-26
**Scope:** Integrated DMA (iDMA) engine inside the Overlay CPU complex of each N1B0 Tensix tile — architecture, initiator paths, reachable targets, configuration masters, and SFR register map.

---

## Table of Contents

1. [Overview](#1-overview)
2. [iDMA Architecture](#2-idma-architecture)
   - 2.1 Top-Level Block Diagram
   - 2.2 Module Hierarchy
   - 2.3 Key Parameters
3. [Command Interface — How Masters Program iDMA](#3-command-interface--how-masters-program-idma)
   - 3.1 RISC-V Custom Instructions (Primary Path)
   - 3.2 APB Register Write (Secondary Path)
   - 3.3 Command Flit Structure
4. [Data Path — What iDMA Can Reach](#4-data-path--what-idma-can-reach)
   - 4.1 Local L1 (intra-tile)
   - 4.2 Peer-Tile L1 (via NoC)
   - 4.3 External DRAM (via NoC → NOC2AXI)
   - 4.4 Summary Table
5. [Backend Architecture](#5-backend-architecture)
   - 5.1 Command Buffer Frontend
   - 5.2 Backend Instances (OBI)
   - 5.3 L1 Accumulator Mode
   - 5.4 Transaction ID and Flow Control
6. [Clock Domains and Gating](#6-clock-domains-and-gating)
7. [SFR Register Map (IDMA_APB)](#7-sfr-register-map-idma_apb)
8. [Module and Instance Reference](#8-module-and-instance-reference)
9. [RTL File Index](#9-rtl-file-index)

---

## 1. Overview

Each N1B0 Tensix tile contains an **iDMA engine** embedded inside the Overlay CPU complex (`tt_overlay_wrapper`). The iDMA is the primary mechanism for bulk data movement between:

- Local Tensix L1 SRAM ↔ External DRAM
- Local Tensix L1 SRAM ↔ Peer-tile L1 SRAM
- DRAM ↔ DRAM (remote-to-remote)

The iDMA operates in the **dm_clk** (core clock) domain and generates **NoC flit transactions** when moving data across tiles or to/from DRAM. For local L1 access it bypasses the NoC entirely and drives the L1 flex-client interface directly.

BRISC and TRISC cores program the iDMA primarily via **RISC-V custom instructions** (DMSRC, DMDST, DMCPY family — snitch ISA extension), which are decoded by the RoCC accelerator interface in the Overlay CPU cluster. The Overlay CPU can also program iDMA via APB-accessible SFR registers.

---

## 2. iDMA Architecture

### 2.1 Top-Level Block Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  tt_overlay_wrapper  (dm_clk domain)                                    │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  tt_idma_wrapper                                                │    │
│  │                                                                 │    │
│  │  ┌─────────────────────────────────────────────────────────┐   │    │
│  │  │  tt_idma_cmd_buffer_frontend                             │   │    │
│  │  │  · 24 clients (RISC cores) → 2 virtual channels (BE)    │   │    │
│  │  │  · Metadata FIFO depth = 42, Payload FIFO depth = 8     │   │    │
│  │  │  · 32 transaction IDs                                    │   │    │
│  │  └──────────────────┬──────────────────────────────────────┘   │    │
│  │                     │ idma_flit_t (vc, trid, payload)          │    │
│  │         ┌───────────▼──────────┬─────────────────┐            │    │
│  │         │  Backend VC0          │  Backend VC1    │            │    │
│  │         │  tt_idma_backend_     │  (same)         │            │    │
│  │         │  r_init_rw_obi_top    │                 │            │    │
│  │         │  · Legalizer          │                 │            │    │
│  │         │  · Transport Layer    │                 │            │    │
│  │         │  · 28 AX in-flight    │                 │            │    │
│  │         └──────┬───────────────┴────────┬────────┘            │    │
│  │                │                        │                      │    │
│  └────────────────┼────────────────────────┼──────────────────── ┘    │
│                   │                        │                           │
│      L1 flex-client (local L1)     NoC flit injection                  │
│      t6_l1_flex_client_{rd,wr}     (via tt_overlay_noc_niu_router)      │
│                   │                        │                           │
│                   ▼                        ▼                           │
│            Local L1 SRAM           NoC mesh → peer-tile / DRAM        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Module Hierarchy

```
tt_overlay_wrapper
  └── tt_idma_wrapper                       (overlay/rtl/idma/tt_idma_wrapper.sv)
        ├── tt_idma_cmd_buffer_frontend     (overlay/rtl/idma/tt_idma_cmd_buffer_frontend.sv)
        └── [IDMA_BE_TYPE_AXI=0]:
              tt_idma_backend_r_init_rw_obi_top  (overlay/rtl/idma/tt_idma_backend_r_init_rw_obi_top.sv)
                ├── [×IDMA_NUM_BE] tt_idma_backend_r_init_rw_obi  (idma/target/rtl/tt_custom/...)
                │     ├── tt_idma_legalizer_r_init_rw_obi
                │     └── tt_idma_transport_layer_r_init_rw_obi
                ├── [×IDMA_NUM_BE] mem_stream_to_banks_detailed  (write path)
                └── [×IDMA_NUM_BE] mem_stream_to_banks_detailed  (read path)
```

The `tt_overlay_wrapper` instantiation wires the iDMA's L1 memory ports to `t6_l1_flex_client_{rd,wr}` interfaces, and its NoC flit output (`o_req_head_flit`) to the overlay NIU router.

### 2.3 Key Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| `IDMA_CMD_BUF_NUM_CLIENTS` | 24 | `tt_idma_pkg.sv` |
| `IDMA_NUM_CLIENTS` | 24 | `tt_idma_pkg.sv` |
| `IDMA_NUM_BE` | `NUM_RD_SUB_PORTS` (= 2) | `tt_overlay_wrapper.sv:99` |
| `IDMA_NUM_MEM_PORTS` | 2 | `tt_idma_pkg.sv` |
| `IDMA_NUM_TRANSACTION_ID` | 32 | `tt_idma_pkg.sv` |
| `IDMA_PACKET_TAG_TRANSACTION_ID_WIDTH` | 5 (= log2 of 32) | `tt_idma_pkg.sv` |
| `IDMA_FIFO_DEPTH` | 42 (metadata FIFO) | `tt_idma_pkg.sv` |
| `IDMA_PAYLOAD_FIFO_DEPTH` | 8 | `tt_idma_pkg.sv` |
| `IDMA_L1_ACC_ATOMIC` | 16 (bit width) | `tt_idma_pkg.sv` |
| `NUM_AX_IN_FLIGHT` | 28 per backend | `tt_idma_backend_r_init_rw_obi_top.sv` |
| `IDMA_DFC_EN` | 1'b0 (disabled by default) | `tt_overlay_wrapper.sv:64` |
| `IDMA_ENABLE_TIMING_STAGES` | 1'b1 | `tt_overlay_wrapper.sv:65` |

---

## 3. Command Interface — How Masters Program iDMA

### 3.1 RISC-V Custom Instructions (Primary Path)

BRISC and TRISC cores use **RISC-V custom instructions** from the snitch/iDMA ISA extension to submit DMA commands. These are decoded as RoCC (Rocket Custom Coprocessor) commands inside the Overlay CPU cluster.

**Instruction set** (from `idma_inst64_snitch_pkg.sv`):

| Mnemonic | Opcode | Description |
|----------|--------|-------------|
| `DMSRC` | custom-0 | Set DMA source address (64-bit) |
| `DMDST` | custom-0 | Set DMA destination address (64-bit) |
| `DMCPYI` | custom-0 | Issue copy with immediate length |
| `DMCPY` | custom-0 | Issue copy with register-provided length |
| `DMSTATI` | custom-0 | Poll DMA status (immediate TID) |
| `DMSTAT` | custom-0 | Poll DMA status (register TID) |
| `DMSTR` | custom-0 | Set DMA stride (for 2D transfers) |
| `DMREP` | custom-0 | Set DMA repetition count (for 2D transfers) |

**Execution flow:**

```
BRISC/TRISC executes DMSRC / DMDST / DMCPY instruction
  ↓
RoCC interface (rocc_cmd_valid, rocc_cmd_bits) inside tt_overlay_cpu_wrapper
  ↓
iDMA RoCC decoder (inside Overlay CPU cluster)
  ↓
rocc_idma_flit_t → req_head_flit[client_id]
  ↓
tt_idma_cmd_buffer_frontend (arbitration across 24 clients → 2 BEs)
```

**Client ID assignment:** Each RISC core (TRISC0/1/2/BRISC × up to 4 T6 instances per tile) maps to one of the 24 iDMA client slots. The mapping is fixed by the `tt_overlay_wrapper` wiring.

### 3.2 APB Register Write (Secondary Path)

The Overlay CPU can also program iDMA via APB-accessible IDMA_APB registers (base address TBD from tile SFR map). This path is used for:
- Reading DMA status (`IDMA_STATUS`)
- Clearing completed transaction counts (`IDMA_CLR`)
- Setting IRQ thresholds (`IDMA_THRESHOLD_*`)
- Controlling L1 clock gating (`IDMA_CLK_EN`)

The Overlay CPU accesses IDMA_APB registers via its peripheral APB bus (`o_apb_*` ports in `tt_overlay_cpu_wrapper`).

BRISC/TRISC can access the same registers by issuing NoC unicast write flits to the tile's IDMA_APB address range — the NIU will decode the target address and route to the APB register block.

### 3.3 Command Flit Structure

From `tt_overlay_wrapper.sv` (lines 764–767), the iDMA command flit (`idma_flit_t`) contains:

```systemverilog
struct {
  logic [IDMA_PACKET_TAG_TRANSACTION_ID_WIDTH-1:0]  trid;     // 5-bit transaction ID (0–31)
  logic [IDMA_BE_BITS-1:0]                          vc;       // Backend VC selection (0 or 1)
  idma_req_t                                         payload;  // Full iDMA request (src, dst, len, options)
}
```

`idma_req_t` (from `idma_pkg.sv`, IDMA_TYPEDEF_FULL_ACCUM_DATA_CONV_REQ_T macro):
```
{
  src_addr[ADDR_WIDTH-1:0]     // Source address (tile-local or (x,y,local_addr) packed)
  dst_addr[ADDR_WIDTH-1:0]     // Destination address
  length[TF_LEN_WIDTH-1:0]     // Transfer size in bytes
  opt.backend.decouple_aw      // Decouple AW/W channels
  opt.backend.decouple_rw      // Decouple R/W pipelines
  opt.backend.max_llen         // Maximum burst length
  opt.backend.reduce_len       // Reduce length to power-of-2
  l1_accum_en                  // Enable L1 accumulator mode (atomic add to L1)
  l1_accum_cfg                 // Accumulator configuration (tt_t6_l1_pkg::l1_atomic_compute_instr_t)
}
```

---

## 4. Data Path — What iDMA Can Reach

### 4.1 Local L1 (intra-tile)

**Mechanism:** Direct L1 flex-client interface — no NoC involved.

From `tt_overlay_wrapper.sv` (lines ~3963–3966):
```systemverilog
// iDMA backend read port → L1 flex-client read
assign t6_l1_flex_client_rd_send[idma_be].push_req = idma_mem_req[idma_be][0]
                                                      && ~t6_l1_flex_client_rd_recv[idma_be].req_full;
assign t6_l1_flex_client_rd_send[idma_be].req_type = tt_t6_l1_pkg::READ;

// iDMA backend write port → L1 flex-client write
// (upper half of mem ports, from mem_stream_to_banks_detailed write converter)
```

**Address range:** `0x000000 – 0x2FFFFF` (3 MB, same as RISC direct L1 access)

**L1 Accumulator mode:** When `l1_accum_en=1` in the iDMA request, the write to L1 is performed as an **atomic add** using the `l1_atomic_compute_instr_t` configuration. The accumulator config is carried in the metadata FIFO (`NUM_AX_IN_FLIGHT=28` depth) through the backend pipeline.

**RTL path:**
```
tt_idma_backend_r_init_rw_obi_top
  └── mem_stream_to_banks_detailed (write) → t6_l1_flex_client_wr_send
  └── mem_stream_to_banks_detailed (read)  → t6_l1_flex_client_rd_send
        ↓
  u_l1part (tt_t6_l1_partition) — same L1 SRAM accessed by RISC cores
```

### 4.2 Peer-Tile L1 (via NoC)

**Mechanism:** iDMA issues a NoC flit through the tile's overlay NIU router.

When `dst_addr` encodes a remote tile's coordinates, the iDMA backend generates a write flit with:
- `targ_addr.x_coord` = peer tile X
- `targ_addr.y_coord` = peer tile Y (0–2)
- `targ_addr.addr`    = peer tile L1 offset (0–0x2FFFFF)

The read side (fetching data from peer) generates a read flit with `ret_addr` pointing back to the local tile.

**Throughput:** Limited by NoC bandwidth and VC availability. Each backend (×2) can have up to 28 outstanding AX transactions in-flight.

**RTL path:**
```
tt_idma_backend_r_init_rw_obi_top
  └── (OBI protocol flit output)
        ↓
  tt_overlay_wrapper: req_head_flit_iDMA → combined req_head_flit
        ↓
  tt_overlay_noc_niu_router → tt_noc_niu_router
        ↓
  NoC mesh (N/E/S/W hops via DOR routing)
        ↓
  Peer tile tt_noc_niu_router → L1 write ports
```

### 4.3 External DRAM (via NoC → NOC2AXI)

**Mechanism:** Same NoC flit path as peer-tile access, but target coordinates point to a Y=4 NOC2AXI tile.

When `dst_addr` or `src_addr` encodes a DRAM address:
- `targ_addr.x_coord` = 0, 1, 2, or 3 (select NOC2AXI tile)
- `targ_addr.y_coord` = 4 (Y=4 row)
- `targ_addr.addr[39:0]` = DRAM local address (after NOC2AXI gasket conversion)

The NOC2AXI tile converts the NoC flit to a 512-bit AXI4 master transaction on the external DRAM bus.

**DRAM address format** in `targ_addr.addr` at NOC2AXI output (56-bit AXI address):
```
[55:52] = 4'b0000 (reserved)
[51:46] = y_coord of originating tile (6 bits)
[45:40] = x_coord of originating tile (6 bits)
[39:0]  = local DRAM address (40 bits)
```

**RTL path:**
```
tt_idma_backend_r_init_rw_obi_top → NoC flit
  ↓
NoC mesh → gen_noc2axi_{ne/nw/router_ne/router_nw}_opt (Y=4)
  ↓
tt_noc2axi.sv
  o_noc2axi_awaddr[55:0] / o_noc2axi_araddr[55:0]
  o_noc2axi_wdata[511:0]
  ↓
External DRAM AXI bus
```

### 4.4 Summary Table

| Target | Path | NoC Used? | Addr Format |
|--------|------|-----------|-------------|
| Local L1 | t6_l1_flex_client interface | No | 21-bit byte offset (0–0x2FFFFF) |
| Peer-tile L1 | NoC flit → remote NIU | Yes | noc_header: (x, y, local_addr) |
| External DRAM | NoC flit → NOC2AXI Y=4 → AXI | Yes | noc_header: (x=0-3, y=4, dram_addr) |
| Peer-tile SFR | NoC unicast write | Yes | noc_header: (x, y, sfr_offset) |

---

## 5. Backend Architecture

### 5.1 Command Buffer Frontend

`tt_idma_cmd_buffer_frontend` arbitrates across **24 client** inputs:

```
24 client inputs (rocc_idma_flit_t × 24)
       ↓
  [Timing stages: 1-deep input FIFOs when IDMA_ENABLE_TIMING_STAGES=1]
       ↓
  Round-robin arbiter
       ↓
  ┌──────────────────────────────────────┐
  │  Metadata FIFO  (depth=42)           │  ← tracks: trid, vc, l1_accum info
  │  Payload FIFO   (depth=8, async)     │  ← carries: src/dst/len/opt
  └──────────────────────────────────────┘
       ↓ (de-multiplexed by vc bit)
  Backend VC0          Backend VC1
```

**Flow control signals:**
- `o_req_head_flit_vc_space[IDMA_NUM_VC × IDMA_VC_CNT_WIDTH]` — available slots per VC (reported to each client core)
- `o_id_transaction_count[32 × CNT_WIDTH]` — per-TID outstanding transfer count
- `o_tiles_to_process_irq` — interrupt when a TID's completion count crosses threshold

### 5.2 Backend Instances (OBI)

Two backend instances (`IDMA_NUM_BE = 2`) each implement a 1D copy engine:

```
tt_idma_backend_r_init_rw_obi
  ├── tt_idma_legalizer_r_init_rw_obi     ← page-boundary + length legalization
  │     · Splits transfers crossing 4KB pages
  │     · Fragments into max-burst-length chunks
  └── tt_idma_transport_layer_r_init_rw_obi  ← protocol-level transactions
        ├── idma_init_read   (INIT protocol read — for local L1 reads)
        ├── idma_obi_read    (OBI read — for remote reads)
        └── idma_obi_write   (OBI write — for all writes)
```

Up to **28 AX transactions** can be in-flight per backend. Outstanding transactions are tracked in the metadata FIFO.

**Supported protocols per path:**
- Local L1 read/write: INIT protocol (direct L1 flex-client)
- Remote (NoC): OBI protocol (converted to NoC flits at NIU)

### 5.3 L1 Accumulator Mode

When `idma_req.l1_accum_en = 1`:
- The write to L1 is performed as an **atomic accumulate** operation instead of a plain store.
- `idma_req.l1_accum_cfg` carries the `tt_t6_l1_pkg::l1_atomic_compute_instr_t` operation code (e.g., ADD, MAX, MIN).
- The `l1_accum_en` flag and config are stored in the per-backend **metadata FIFO** (depth=28) and forwarded alongside the write address to the L1 flex-client.
- Output to `tt_overlay_wrapper`: `o_l1_accum_en[IDMA_NUM_BE]`, `o_l1_accum_cfg[IDMA_NUM_BE]`

**Use case:** Enables in-place accumulation of partial sums in L1 (e.g., accumulating outputs from multiple tiles without first reading back, modifying, and writing).

### 5.4 Transaction ID and Flow Control

- Each iDMA transfer is tagged with a 5-bit **transaction ID (TID)**, selecting one of 32 independent TID channels.
- BRISC/TRISC poll completion via `DMSTAT` instruction (reads `IDMA_STATUS.in_flight` bitmap).
- Hardware increments `IDMA_TR_COUNT[tid]` on each completed transfer.
- When `IDMA_TR_COUNT[tid]` reaches `IDMA_THRESHOLD[tid]`, an **IRQ** is raised to the Overlay CPU interrupt controller.
- Software clears the count and IRQ by writing `1<<tid` to `IDMA_CLR`.

---

## 6. Clock Domains and Gating

| Signal | Domain | Source |
|--------|--------|--------|
| `i_core_clk` | dm_clk (core) | per-column `i_dm_clk[x]` |
| `i_l1_clk` | ai_clk (L1) | per-column `i_ai_clk[x]` |

The L1 memory ports of iDMA operate on `i_l1_clk` (ai_clk) — a CDC crossing is required between the dm_clk iDMA core and the ai_clk L1 SRAM.

**Clock gating** (from `tt_idma_wrapper.sv`):

```
tt_sync_reset_powergood  ← synchronizes reset to L1 clock domain
tt_clk_gater             ← gates i_l1_clk when iDMA not using L1
  · i_core_clkgt_en = CLUSTER_CTRL.CLOCK_GATING.L1_FLEX_CLIENT_IDMA
  · hysteresis = IDMA_CLK_HYST.hyst[6:0] → 2^hyst idle cycles before gate
```

**CLUSTER_CTRL clock gating register** (`0x030000CC`):
- Bit[1] `IDMA`: clock gate for iDMA core logic
- Bit[7] `L1_FLEX_CLIENT_IDMA`: clock gate for iDMA's L1 flex-client port

When `IDMA_CLK_EN.l1_clk_gate_en = 1`, the L1 clock gater is active (enabled when iDMA backend is busy: `o_l1_clkgt_busy = ~all_fifos_empty`).

---

## 7. SFR Register Map (IDMA_APB)

All registers are per-tile. Base address is tile-local (same offset for all 12 Tensix tiles).

**IDMA_APB registers** (from `N1B0_NPU_sfr_v0.3.csv`):

| Register | Offset | Width | Access | Description |
|----------|--------|-------|--------|-------------|
| `IDMA_STATUS` | 0x00 | 32 | RO | `in_flight[31:0]`: bitmask — bit N=1 if TID N has transfer in flight |
| `IDMA_TR_COUNT_0` | 0x10 | 32 | RO | Completed transfer count for TID 0 |
| `IDMA_TR_COUNT_1` | 0x14 | 32 | RO | Completed transfer count for TID 1 |
| … | … | … | … | … |
| `IDMA_TR_COUNT_31` | 0x8C | 32 | RO | Completed transfer count for TID 31 |
| `IDMA_THRESHOLD_0` | 0x90 | 32 | RW | IRQ threshold for TID 0 |
| `IDMA_THRESHOLD_1` | 0x94 | 32 | RW | IRQ threshold for TID 1 |
| … | … | … | … | … |
| `IDMA_THRESHOLD_9+` | 0xB4+ | 32 | RW | IRQ threshold for TID 9–31 (stride 4) |
| `IDMA_CLR` | 0x110 | 32 | W1C | Write bit N=1 to clear `TR_COUNT[N]` and deassert IRQ for TID N |
| `IDMA_CLK_EN` | 0x114 | 1 | RW | `l1_clk_gate_en[0]`: enable L1 clock gating |
| `IDMA_CLK_HYST` | 0x118 | 7 | RW | `hyst[6:0]`: idle cycles before clock gate = 2^hyst |

**CLUSTER_CTRL registers** (base `0x03000000`, from `N1B0_NPU_sfr_v0.3.csv`):

| Register | Offset | Bit | Description |
|----------|--------|-----|-------------|
| `CLOCK_GATING` | 0xCC | [1] | Clock gate iDMA core (1=gated) |
| `CLOCK_GATING` | 0xCC | [7] | Clock gate iDMA L1 flex-client port (1=gated) |

---

## 8. Module and Instance Reference

### 8.1 Per-Tile Instantiation Path

```
trinity
  └── gen_tensix_neo[x][y]
        └── tt_tensix_with_l1
              └── overlay_noc_wrap
                    └── tt_overlay_noc_niu_router
                          └── neo_overlay_wrapper
                                └── tt_overlay_wrapper           (dm_clk)
                                      └── tt_idma_wrapper
                                            ├── tt_idma_cmd_buffer_frontend
                                            │     · 24 clients (RISC cores)
                                            │     · Metadata FIFO depth=42
                                            │     · Payload FIFO depth=8
                                            │     · 32 TIDs
                                            │
                                            └── tt_idma_backend_r_init_rw_obi_top
                                                  ├── [VC=0] tt_idma_backend_r_init_rw_obi
                                                  │     ├── tt_idma_legalizer_r_init_rw_obi
                                                  │     └── tt_idma_transport_layer_r_init_rw_obi
                                                  ├── [VC=1] tt_idma_backend_r_init_rw_obi (same)
                                                  ├── [×2] mem_stream_to_banks_detailed (write → L1)
                                                  └── [×2] mem_stream_to_banks_detailed (read ← L1)
```

### 8.2 Configuration Master Summary

| Master | Interface | Registers Used | Notes |
|--------|-----------|----------------|-------|
| **BRISC** | RISC-V custom instructions (RoCC) | DMSRC / DMDST / DMCPY / DMSTAT | Primary programming path; highest performance |
| **TRISC0/1/2** | RISC-V custom instructions (RoCC) | Same as BRISC | Same ISA extension, 24 total client slots shared |
| **Overlay CPU** | APB peripheral bus | IDMA_APB all registers | Used for status polling, IRQ management, clock control |
| **External host** | NoC unicast write → APB | IDMA_APB subset | Indirect path via NoC flit to tile's APB bridge |

### 8.3 Signal Connections in tt_overlay_wrapper

| Signal | Direction | Connection |
|--------|-----------|------------|
| `req_head_flit_iDMA[24]` | IN → iDMA | From RISC cores' RoCC interface |
| `req_head_flit_vc_space_iDMA` | OUT → RISC | VC space feedback (flow control) |
| `id_transaction_count_iDMA` | OUT → RISC | Per-TID completion count |
| `t6_l1_flex_client_rd_send/recv[2]` | iDMA ↔ L1 | Direct L1 read port (ai_clk) |
| `t6_l1_flex_client_wr_send/recv[2]` | iDMA ↔ L1 | Direct L1 write port (ai_clk) |
| `idma_l1_accum_cfg[2]` / `idma_l1_accum_en[2]` | iDMA → L1 | Atomic accumulator config |

---

## 9. RTL File Index

All paths relative to `/secure_data_from_tt/20260221/used_in_n1/mem_port/tt_rtl/`

| Module | File |
|--------|------|
| `tt_idma_wrapper` | `overlay/rtl/idma/tt_idma_wrapper.sv` |
| `tt_idma_cmd_buffer_frontend` | `overlay/rtl/idma/tt_idma_cmd_buffer_frontend.sv` |
| `tt_idma_backend_r_init_rw_obi_top` | `overlay/rtl/idma/tt_idma_backend_r_init_rw_obi_top.sv` |
| `tt_idma_pkg` | `overlay/rtl/idma/tt_idma_pkg.sv` |
| `tt_idma_backend_r_init_rw_obi` | `idma/target/rtl/tt_custom/tt_idma_backend_r_init_rw_obi.sv` |
| `tt_idma_legalizer_r_init_rw_obi` | `idma/target/rtl/tt_custom/tt_idma_legalizer_r_init_rw_obi.sv` |
| `tt_idma_transport_layer_r_init_rw_obi` | `idma/target/rtl/tt_custom/tt_idma_transport_layer_r_init_rw_obi.sv` |
| `tt_idma_dfc_pkg` | `idma/target/rtl/tt_custom/dfc/config/tt_idma_dfc_pkg.sv` |
| `idma_pkg` | `idma/src/idma_pkg.sv` |
| `idma_inst64_snitch_pkg` | `idma/src/frontend/inst64/idma_inst64_snitch_pkg.sv` |
| `idma_legalizer_page_splitter` | `idma/src/backend/idma_legalizer_page_splitter.sv` |
| `idma_obi_read` | `idma/src/backend/idma_obi_read.sv` |
| `idma_obi_write` | `idma/src/backend/idma_obi_write.sv` |
| `idma_init_read` | `idma/src/backend/idma_init_read.sv` |
| `idma_dataflow_element` | `idma/src/backend/idma_dataflow_element.sv` |
| `tt_overlay_wrapper` | `overlay/rtl/tt_overlay_wrapper.sv` |
| `tt_overlay_cpu_wrapper` | `overlay/rtl/tt_overlay_cpu_wrapper.sv` |
| `tt_cluster_ctrl_reg_pkg` | `overlay/meta/registers/trinity/rtl/tt_cluster_ctrl_reg_pkg.sv` |

---

## Appendix: iDMA Usage Quick Reference

### A. Minimal DMA Transfer (BRISC)

```asm
; 1. Set source address (local L1 offset 0x1000)
DMSRC  x0, 0x1000

; 2. Set destination address (DRAM via NOC2AXI at tile X=0, Y=4)
;    Encoded as NoC address: (x=0, y=4, dram_local=0x80000000)
DMDST  x0, <noc_packed_addr>

; 3. Issue copy: 4096 bytes, TID=0
DMCPYI x0, 4096, 0

; 4. Poll until TID 0 is no longer in-flight
poll:
DMSTATI t0, 0       ; t0 = IDMA_STATUS.in_flight[0]
BNEZ    t0, poll
```

### B. Setting IRQ Threshold

```c
// Software (via APB or NoC write):
// Trigger IRQ after 8 transfers complete on TID 1
IDMA_THRESHOLD_1 = 8;  // write 8 to offset 0x94

// Clear after IRQ fires:
IDMA_CLR = (1 << 1);   // W1C, offset 0x110
```

### C. L1 Accumulator Transfer

```asm
; Set up: accumulate src data into local L1 using ADD
; src: peer tile (x=1, y=2, offset=0x0)
; dst: local L1 offset 0x2000
; l1_accum_en=1, l1_accum_cfg=ADD

DMSRC  x0, <noc_packed_addr: x=1,y=2,off=0>
DMDST  x0, 0x2000           ; local L1 dst
DMCPY  x0, len, TID=3       ; with accum flags set in idma_req
```

Note: The l1_accum_en and l1_accum_cfg fields in the iDMA request descriptor must be set by the RoCC command encoder. BRISC sets these via extended fields of the `DMCPY` instruction or a configuration register before issuing the transfer.

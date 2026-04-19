# EDC SW Programming Guide — N1B0 (V0.1)

**Document:** EDC_SW_GUIDE_V0.1.md
**Chip:** N1B0 (4×5 Trinity grid)
**Date:** 2026-03-20
**Audience:** SW engineers writing firmware, POST, runtime health monitors

---

## Table of Contents

1. [Overview](#1-overview)
2. [Basic Architecture](#2-basic-architecture)
   - 2.1 Ring Topology (N1B0 4×5 Grid)
   - 2.2 EDC Node ID Encoding
   - 2.3 Node Instance Index Table (per tile type)
   - 2.4 BIU Register Map (APB4)
   - 2.5 Command Opcode Table
3. [BIU Access Procedure](#3-biu-access-procedure)
   - 3.1 Write Transaction
   - 3.2 Read Transaction
   - 3.3 Generate (Self-test Trigger) Transaction
   - 3.4 Status Polling & IRQ
4. [Node-by-Node SW Access Guide](#4-node-by-node-sw-access-guide)
   - 4.1 RISC-V / BRISC Nodes
   - 4.2 TRISC Nodes
   - 4.3 FPU G-Tile / M-Tile / FP-Lane Nodes
   - 4.4 DEST Latch-Array Node (G-Tile)
   - 4.5 SRCA Latch-Array Node (G-Tile)
   - 4.6 SRCB Latch-Array Node (G-Tile)
   - 4.7 L1 SRAM Nodes (T6 partition)
   - 4.8 Overlay L1/L2 Cache Nodes
   - 4.9 Context-Switch SRAM Node
   - 4.10 NOC2AXI / AXI2NOC VC-FIFO Nodes
   - 4.11 Router VC-FIFO Nodes
   - 4.12 ATT SRAM Nodes
   - 4.13 NIU MST/SLV Endpoint Nodes
   - 4.14 NOC2AXI_ROUTER Composite Nodes (N1B0 specific)
5. [New SW Work Features](#5-new-sw-work-features)
   - 5.1 Column Sweep
   - 5.2 Ring Loopback Test
   - 5.3 Latch-Array BIST FSM Control (Method C)
   - 5.4 Background Polling Daemon
   - 5.5 Event Log
   - 5.6 Harvest Decision
   - 5.7 POST (Power-On Self Test)
   - 5.8 Selective Node Query
6. [Error Handling](#6-error-handling)
7. [Harvest & Bypass](#7-harvest--bypass)
8. [Appendix A — Full N1B0 Node Address Table](#appendix-a--full-n1b0-node-address-table)
9. [Appendix B — Pseudo-code Reference](#appendix-b--pseudo-code-reference)

---

## 1. Overview

The EDC1 (Error Detection/Correction) subsystem provides a serial daisy-chain ring that SW can use to:

- **Read** internal flip-flop / latch capture data from any IP node
- **Write** configuration values (e.g. BIST mode, INIT override)
- **Trigger self-test** (GEN_CMD) on memory and latch arrays
- **Receive error events** — correctable (COR), latent (LAT), uncorrectable (UNC), overflow (OVF)
- **Monitor ring health** — loopback test detects broken ring segments

In N1B0 the ring is **per-column** — 4 completely independent rings, one per X column (X=0..3).
Each ring is driven by a BIU (Bus Interface Unit) at the top of the column (Y=4).

---

## 2. Basic Architecture

### 2.1 Ring Topology (N1B0 4×5 Grid)

Each column forms a completely independent closed loop.
**Segment A** travels downward (Y=4 → Y=0).
**Segment B** (loopback) travels upward (Y=0 → Y=4) back to the same BIU.

```
  Column X=0                Column X=1                Column X=2                Column X=3
  ──────────                ──────────                ──────────                ──────────

  BIU[0] (Y=4)              BIU[1] (Y=4)              BIU[2] (Y=4)              BIU[3] (Y=4)
  │▼ Seg A out              │▼ Seg A out              │▼ Seg A out              │▼ Seg A out
  │                         │                         │                         │
  ├─[NOC2AXI_ROUTER Y=4]    ├─[NOC2AXI_ROUTER Y=4]    ├─[NOC2AXI_ROUTER Y=4]    ├─[NOC2AXI_ROUTER Y=4]
  │  (composite internal)   │  (composite internal)   │  (composite internal)   │  (composite internal)
  ├─[NOC2AXI_ROUTER Y=3]    ├─[NOC2AXI_ROUTER Y=3]    ├─[NOC2AXI_ROUTER Y=3]    ├─[NOC2AXI_ROUTER Y=3]
  │                         │                         │                         │
  ├─[TENSIX Y=2]            ├─[TENSIX Y=2]            ├─[TENSIX Y=2]            ├─[TENSIX Y=2]
  │                         │                         │                         │
  ├─[TENSIX Y=1]            ├─[TENSIX Y=1]            ├─[TENSIX Y=1]            ├─[TENSIX Y=1]
  │                         │                         │                         │
  ├─[TENSIX Y=0] ◄─U-turn   ├─[TENSIX Y=0] ◄─U-turn   ├─[TENSIX Y=0] ◄─U-turn   ├─[TENSIX Y=0] ◄─U-turn
  │▲ Seg B in               │▲ Seg B in               │▲ Seg B in               │▲ Seg B in
  │                         │                         │                         │
  (Seg B travels back up    (Seg B travels back up    (Seg B travels back up    (Seg B travels back up
   through same column       through same column       through same column       through same column
   nodes in reverse)         nodes in reverse)         nodes in reverse)         nodes in reverse)
  │                         │                         │                         │
  BIU[0] ◄─ Seg B return    BIU[1] ◄─ Seg B return    BIU[2] ◄─ Seg B return    BIU[3] ◄─ Seg B return
  (closed loop X=0)         (closed loop X=1)         (closed loop X=2)         (closed loop X=3)
```

**Key facts:**
- The U-turn at Y=0 is: `edc_egress_intf[x*5+0] → loopback_edc_ingress_intf[x*5+0]` (per `trinity.sv`)
- Segment B visits the same nodes as Segment A but in reverse direction (Y=0 → Y=4)
- A broken wire anywhere severs only that column's ring — the other 3 columns are unaffected
- N1B0 composite tile (NOC2AXI_ROUTER at Y=4+Y=3) spans both rows internally; its EDC chain exits at Y=3 and is re-entered from Y=3 into Y=2

---

### 2.2 EDC Node ID Encoding

```
  node_id[15:0] = { part[4:0], subp[2:0], inst[7:0] }

  Bits [15:11]  part   — IP type code  (see table below)
  Bits [10:8]   subp   — tile Y coordinate (0..4)
  Bits [7:0]    inst   — function index within that IP
```

**Column X is NOT encoded in node_id.** The BIU that receives the response implicitly identifies the column.

**Part codes (selected):**

| part | IP Type              |
|------|----------------------|
| 0x01 | TENSIX core          |
| 0x02 | DISPATCH             |
| 0x03 | NIU (NOC2AXI)        |
| 0x04 | ROUTER               |
| 0x05 | T6 L1 SRAM partition |
| 0x08 | Overlay              |
| 0x10 | G-Tile (FPU)         |
| 0x11 | M-Tile               |
| 0x12 | FP-Lane              |
| 0x13 | DEST latch array     |
| 0x14 | SRCA latch array     |
| 0x15 | SRCB latch array     |

---

### 2.3 Node Instance Index Table (per tile type)

#### Tensix tile (part=0x01, subp=Y)

| inst | Node name              | What it monitors                              |
|------|------------------------|-----------------------------------------------|
| 0x00 | BRISC_CORE             | BRISC PC, stall flags                         |
| 0x01 | TRISC0_CORE            | TRISC0 PC, stall flags                        |
| 0x02 | TRISC1_CORE            | TRISC1 PC, stall flags                        |
| 0x03 | TRISC2_CORE            | TRISC2 PC, stall flags                        |
| 0x10 | UNPACK_TDMA            | UNPACK request FIFO occupancy, src addr       |
| 0x11 | PACK_TDMA              | PACK request FIFO occupancy, dst addr         |
| 0x20 | GTILE0_FPU             | FPU G-Tile 0 status (srca/dest pointers)      |
| 0x21 | GTILE0_SRCA            | SRCA latch array (part=0x14, inst=0x00)       |
| 0x22 | GTILE0_DEST            | DEST latch array (part=0x13, inst=0x00)       |
| 0x04 | SRCB_EDC_IDX           | SRCB latch array (part=0x15, inst=0x04)       |
| 0x30 | MTILE_FPU              | M-Tile FPU status                             |
| 0x40 | FPLANE_0               | FP-Lane 0 status                              |
| 0x50 | L1_PART0               | T6 L1 partition 0 SRAM ECC status            |
| 0x51 | L1_PART1               | T6 L1 partition 1 SRAM ECC status            |
| 0x52 | L1_PART2               | T6 L1 partition 2 SRAM ECC status            |
| 0x53 | L1_PART3               | T6 L1 partition 3 SRAM ECC status            |

#### NOC2AXI / NIU (part=0x03, subp=Y)

| inst | Node name            | What it monitors                           |
|------|----------------------|--------------------------------------------|
| 0x00 | NIU_RD_EP_TABLE      | Read endpoint address registers            |
| 0x01 | NIU_WR_EP_TABLE      | Write endpoint address registers           |
| 0x08 | VC_FIFO_0            | VC0 FIFO fill level, overflow flag         |
| 0x09 | VC_FIFO_1            | VC1 FIFO fill level, overflow flag         |
| 0x0A | VC_FIFO_2            | VC2 FIFO fill level, overflow flag         |
| 0x0B | VC_FIFO_3            | VC3 FIFO fill level, overflow flag         |
| 0x0C | MST_RD_EP_TABLE      | AXI master read endpoint (NOC2AXI only)    |
| 0x0D | MST_WR_EP_TABLE      | AXI master write endpoint (NOC2AXI only)   |
| 0x0E | SLV_RD_EP_TABLE      | AXI slave read endpoint (NOC2AXI only)     |
| 0x0F | SLV_WR_EP_TABLE      | AXI slave write endpoint (NOC2AXI only)    |
| 0x10 | ATT_SRAM_0           | ATT bank 0 SRAM ECC                        |
| 0x11 | ATT_SRAM_1           | ATT bank 1 SRAM ECC                        |
| 0x40 | RDATA_FIFO           | RDATA FIFO (depth=512 default in N1B0)     |

#### Router (part=0x04, subp=Y)

| inst | Node name            | What it monitors                           |
|------|----------------------|--------------------------------------------|
| 0xC0 | ROUTER_VC_FIFO_0     | Router VC0 FIFO                            |
| 0xC1 | ROUTER_VC_FIFO_1     | Router VC1 FIFO                            |

#### Overlay (part=0x08, subp=Y)

| inst | Node name            | What it monitors                           |
|------|----------------------|--------------------------------------------|
| 0x00 | OVL_L1_CACHE         | Overlay L1 cache ECC status               |
| 0x01 | OVL_L2_CACHE         | Overlay L2 cache ECC status               |
| 0x02 | CTX_SWITCH_SRAM      | Context switch SRAM ECC                    |
| 0x08 | OVL_CDC_FIFO         | Overlay CDC FIFO status                    |

---

### 2.4 BIU Register Map (APB4, 6-bit address)

BIU base address per column X: `BIU_BASE[X]` (from SFR map; see N1B0_HDD §11)

| Offset | Name          | RW  | Width | Description                                         |
|--------|---------------|-----|-------|-----------------------------------------------------|
| 0x00   | REQ_HDR0      | WO  | 32    | [15:0]=node_id, [19:16]=cmd, [31:20]=reserved       |
| 0x04   | REQ_HDR1      | WO  | 32    | [15:0]=byte_en, [31:16]=reserved                    |
| 0x08   | REQ_DATA[0]   | WO  | 32    | Write data word 0 / GEN args[31:0]                  |
| 0x0C   | REQ_DATA[1]   | WO  | 32    | Write data word 1 / GEN args[63:32]                 |
| 0x10   | REQ_DATA[2]   | WO  | 32    | Write data word 2                                   |
| 0x14   | REQ_DATA[3]   | WO  | 32    | Write data word 3                                   |
| 0x18   | RSP_HDR0      | RO  | 32    | [15:0]=node_id echo, [19:16]=rsp_cmd, [22:20]=ret_code |
| 0x1C   | RSP_HDR1      | RO  | 32    | [15:0]=byte_en echo                                 |
| 0x20   | RSP_DATA[0]   | RO  | 32    | Read data word 0 / fail_row (self-test)             |
| 0x24   | RSP_DATA[1]   | RO  | 32    | Read data word 1 / fail_datum (self-test)           |
| 0x28   | RSP_DATA[2]   | RO  | 32    | Read data word 2                                    |
| 0x2C   | RSP_DATA[3]   | RO  | 32    | Read data word 3                                    |
| 0x30   | STAT          | RW1C| 32    | [0]=RSP_VALID, [1]=ERROR, [2]=TIMEOUT, [3]=RING_BREAK |
| 0x34   | CTRL          | RW  | 32    | [0]=INIT (pulse), [1]=IRQ_CLR, [7:4]=MCPDLY        |
| 0x38   | IRQ_EN        | RW  | 32    | Bit per event type: [0]=COR,[1]=LAT,[2]=UNC,[3]=OVF |

**ret_code values:**

| ret_code | Meaning                    |
|----------|----------------------------|
| 0x0      | OK                         |
| 0x1      | Node not found (no ack)    |
| 0x2      | Parity error on ring       |
| 0x3      | Timeout                    |
| 0x4      | Access denied              |

---

### 2.5 Command Opcode Table

| Opcode | Mnemonic       | Direction   | Description                                      |
|--------|----------------|-------------|--------------------------------------------------|
| 0x0    | WR_CMD         | SW→node     | Write REQ_DATA to node's CONFIG registers        |
| 0x1    | RD_CMD         | SW→node     | Read node's capture registers → RSP_DATA         |
| 0x8    | GEN_CMD        | SW→node     | Generate / trigger self-test; args in REQ_DATA   |
| 0x9    | UNC_ERR_CMD    | node→BIU    | Node reporting uncorrectable error event         |
| 0xA    | LAT_ERR_CMD    | node→BIU    | Node reporting latent error event                |
| 0xB    | COR_ERR_CMD    | node→BIU    | Node reporting correctable error (= ST_PASS_EVENT)|
| 0xC    | OVF0_CMD       | node→BIU    | Overflow channel 0                               |
| 0xD    | OVF1_CMD       | node→BIU    | Overflow channel 1                               |
| 0xE    | OVF2_CMD       | node→BIU    | Overflow channel 2                               |
| 0xF    | OVF3_CMD       | node→BIU    | Overflow channel 3                               |

**Self-test result codes (returned in RSP_HDR0[19:16]):**
- `COR_ERR_CMD (0xB)` = ST_PASS — BIST completed with no failures
- `LAT_ERR_CMD (0xA)` = ST_LAT  — BIST detected latent fault; RSP_DATA[0]=fail_row, RSP_DATA[1]=fail_datum
- `UNC_ERR_CMD (0x9)` = ST_FAIL — hard fail (uncorrectable)

---

## 3. BIU Access Procedure

### 3.1 Write Transaction

```c
void edc_write(int col, uint16_t node_id, uint32_t *data4, uint16_t byte_en) {
    uint32_t base = BIU_BASE[col];
    // 1. Write request data
    WR32(base + 0x08, data4[0]);
    WR32(base + 0x0C, data4[1]);
    WR32(base + 0x10, data4[2]);
    WR32(base + 0x14, data4[3]);
    // 2. Write header last (triggers launch)
    WR32(base + 0x04, byte_en);
    WR32(base + 0x00, (WR_CMD << 16) | node_id);
    // 3. Poll STAT[0] for RSP_VALID
    while (!(RD32(base + 0x30) & 0x1));
    // 4. Check ret_code
    uint32_t hdr = RD32(base + 0x18);
    uint8_t ret = (hdr >> 20) & 0x7;
    if (ret != 0) handle_error(col, node_id, ret);
    // 5. Clear RSP_VALID
    WR32(base + 0x30, 0x1);
}
```

### 3.2 Read Transaction

```c
void edc_read(int col, uint16_t node_id, uint32_t *data4_out) {
    uint32_t base = BIU_BASE[col];
    // 1. Write header (RD_CMD, no data needed)
    WR32(base + 0x04, 0xFFFF);               // byte_en = all
    WR32(base + 0x00, (RD_CMD << 16) | node_id);
    // 2. Poll STAT[0]
    while (!(RD32(base + 0x30) & 0x1));
    // 3. Read response data
    data4_out[0] = RD32(base + 0x20);
    data4_out[1] = RD32(base + 0x24);
    data4_out[2] = RD32(base + 0x28);
    data4_out[3] = RD32(base + 0x2C);
    WR32(base + 0x30, 0x1);
}
```

### 3.3 Generate (Self-test Trigger) Transaction

```c
// args[0..3] = GEN_CMD arguments (e.g. bist_mode in args[0])
void edc_gen(int col, uint16_t node_id, uint32_t *args4) {
    uint32_t base = BIU_BASE[col];
    WR32(base + 0x08, args4[0]);
    WR32(base + 0x0C, args4[1]);
    WR32(base + 0x10, args4[2]);
    WR32(base + 0x14, args4[3]);
    WR32(base + 0x04, 0xFFFF);
    WR32(base + 0x00, (GEN_CMD << 16) | node_id);
    // GEN_CMD returns immediately with ack; BIST runs async
    // Self-test result arrives later as COR/LAT/UNC event (or poll)
    while (!(RD32(base + 0x30) & 0x1));
    WR32(base + 0x30, 0x1);
}
```

### 3.4 Status Polling & IRQ

**Polling mode** (no IRQ):
```c
// Check for any pending event on a column
uint32_t edc_poll_event(int col) {
    uint32_t stat = RD32(BIU_BASE[col] + 0x30);
    if (stat & 0x1) {
        uint32_t rsp_hdr = RD32(BIU_BASE[col] + 0x18);
        uint8_t cmd = (rsp_hdr >> 16) & 0xF;  // event type
        uint16_t node = rsp_hdr & 0xFFFF;
        WR32(BIU_BASE[col] + 0x30, 0x1);      // clear
        return (cmd << 16) | node;
    }
    return 0;
}
```

**IRQ mode:** Set `IRQ_EN` bits before enabling IRQs.
On IRQ, read `STAT`, `RSP_HDR0`, `RSP_DATA[0..1]`, then W1C `STAT[0]`.

---

## 4. Node-by-Node SW Access Guide

### 4.1 RISC-V / BRISC Nodes

**node_id:** `part=0x01, subp=Y, inst=0x00`
**Capture registers (RD_CMD returns):**

| RSP_DATA word | Field          | Description                |
|---------------|----------------|----------------------------|
| [0][31:0]     | pc             | Current BRISC program counter |
| [0][bit 28]   | stall          | Pipeline stall indicator   |
| [1][7:0]      | irq_pending    | Pending interrupt bitmask  |

**Self-test:** No dedicated BIST; relies on TRISC instruction execution test.

**SW usage:**
```c
// Check if BRISC is alive (non-zero PC, not stalled)
uint32_t data[4];
edc_read(col, NODE(0x01, y, 0x00), data);
uint32_t pc    = data[0] & ~(1<<28);
bool stalled   = (data[0] >> 28) & 1;
```

---

### 4.2 TRISC Nodes

**node_id:** `part=0x01, subp=Y, inst=0x01/0x02/0x03` (TRISC0/1/2)
**Capture registers:** Same layout as BRISC — PC + stall in DATA[0].

**SW self-test procedure:**
1. Load a known instruction sequence into TRISC IMEM
2. Execute via BRISC kickoff register
3. Verify result register via NOC read
4. Cross-check PC advancement via EDC RD_CMD

---

### 4.3 FPU G-Tile / M-Tile / FP-Lane Nodes

**node_id:** `part=0x10/0x11/0x12, subp=Y, inst=0x00..N`
**Capture registers (RD_CMD returns):**

| RSP_DATA word | Field                | Description                            |
|---------------|----------------------|----------------------------------------|
| [0][15:0]     | srca_rd_ptr          | SRCA read pointer                      |
| [0][31:16]    | dest_wr_ptr          | DEST write pointer                     |
| [1][7:0]      | fpu_busy             | FPU pipeline busy indicator            |
| [1][15:8]     | mop_cnt              | Pending MOP count                      |
| [2][31:0]     | last_result_tag      | Tag of last completed result           |

**Self-test:** GEN_CMD with args[0]=BIST_MODE triggers internal FP march test.

---

### 4.4 DEST Latch-Array Node (G-Tile)

**RTL module:** `tt_reg_bank`
**node_id:** `part=0x13, subp=Y, inst=0x22` (GTILE0_DEST)
**Parameters:** SETS=4, DEPTH=64, DATUMS=16, DATUM_WIDTH=19b
**Clock:** ai_clk, ICG-gated per access

**CONFIG_REG layout (WR_CMD to configure BIST):**

| Bit    | Field       | Description                                    |
|--------|-------------|------------------------------------------------|
| [1:0]  | bist_mode   | 0=off, 1=March-C, 2=checkerboard, 3=custom     |
| [2]    | bist_set    | Which SET to test (0 or 1..3)                  |
| [7:3]  | reserved    | —                                              |

**PULSE_REG (GEN_CMD args[0][0]=1):** Starts BIST FSM

**Capture registers (RD_CMD):**

| RSP_DATA word | Field          | Description                            |
|---------------|----------------|----------------------------------------|
| [0][15:0]     | fail_row       | DEST row address of first failure      |
| [0][31:16]    | fail_datum     | Datum index within row of first failure|
| [1][0]        | bist_done      | 1 = BIST FSM completed                 |
| [1][1]        | bist_pass      | 1 = no failures detected               |

**Self-test result via event:**
- Pass → `COR_ERR_CMD (0xB)` event to BIU
- Fail → `LAT_ERR_CMD (0xA)` event; RSP_DATA[0]=fail_row, RSP_DATA[1]=fail_datum

**SW procedure (Method C):**
```c
// Step 1: Configure BIST mode
uint32_t cfg[4] = {0x1, 0, 0, 0};  // bist_mode=March-C, set=0
edc_write(col, NODE(0x13, y, 0x22), cfg, 0x1);

// Step 2: Trigger BIST via PULSE_REG
uint32_t pulse[4] = {0x1, 0, 0, 0};
edc_gen(col, NODE(0x13, y, 0x22), pulse);

// Step 3: Poll for self-test event
uint32_t ev;
do { ev = edc_poll_event(col); } while (ev == 0);

uint8_t cmd = (ev >> 16) & 0xF;
if (cmd == 0xB) { /* PASS */ }
else if (cmd == 0xA) {
    uint32_t data[4];
    edc_read(col, NODE(0x13, y, 0x22), data);
    uint16_t fail_row   = data[0] & 0xFFFF;
    uint16_t fail_datum = data[0] >> 16;
}
```

---

### 4.5 SRCA Latch-Array Node (G-Tile)

**RTL module:** `tt_srca_reg_slice`
**node_id:** `part=0x14, subp=Y, inst=0x21` (GTILE0_SRCA)
**Parameters:** 48 rows × 1 × 19b (single column, read/write)
**Clock:** ai_clk

**Self-test:** Same interface as DEST — GEN_CMD triggers March-C FSM.
SRCA has no ICG (always active when ai_clk running).

**SW loopback (Method B):**
```
TRISC: MVMUL with identity matrix → SRCA loaded
TRISC: Read back SRCA via LLK UNPACK
Compare in BRISC via NOC path
```

**Capture registers (RD_CMD):**

| RSP_DATA word | Field        | Description                       |
|---------------|--------------|-----------------------------------|
| [0][7:0]      | rd_ptr       | SRCA read pointer                 |
| [0][15:8]     | wr_ptr       | SRCA write pointer                |
| [1][0]        | bist_done    | BIST FSM done                     |
| [1][1]        | bist_pass    | No failures                       |

---

### 4.6 SRCB Latch-Array Node (G-Tile)

**RTL module:** `tt_srcb_registers` (shared instance across G-Tiles)
**node_id:** `part=0x15, subp=Y, inst=0x04` (SRCB_EDC_IDX)
**Parameters:** 48×16×19b (row×column×width)
**Clock:** ai_clk, shared across all G-Tile instances

**CONFIG_REG_1 (WR_CMD):**

| Bit    | Field      | Description                           |
|--------|------------|---------------------------------------|
| [1:0]  | bist_mode  | 0=off, 1=March-C, 2=checkerboard      |
| [5:2]  | col_sel    | Which of 16 columns to test           |

**Self-test:** GEN_CMD → March-C across selected column range.

**Capture registers (RD_CMD):**

| RSP_DATA word | Field          | Description                           |
|---------------|----------------|---------------------------------------|
| [0][7:0]      | fail_row       | SRCB row of first fail                |
| [0][11:8]     | fail_col       | SRCB column of first fail             |
| [1][0]        | bist_done      | Done                                  |
| [1][1]        | bist_pass      | Pass                                  |

---

### 4.7 L1 SRAM Nodes (T6 partition)

**RTL module:** `tt_t6_l1_partition` (x4 per Tensix tile in N1B0)
**node_id:** `part=0x05, subp=Y, inst=0x50..0x53` (partitions 0–3)
**Memory:** 768×128b SRAM per partition (3072 total macros in N1B0)
**Clock:** ai_clk

**RD_CMD captures:**

| RSP_DATA word | Field            | Description                              |
|---------------|------------------|------------------------------------------|
| [0][15:0]     | ecc_1bit_count   | Correctable (1-bit) ECC error count      |
| [0][31:16]    | ecc_2bit_count   | Uncorrectable (2-bit) ECC error count    |
| [1][21:0]     | last_err_addr    | Address of last ECC error                |
| [2][127:0]    | last_err_synd    | ECC syndrome (spread across DATA[2..3])  |

**Self-test (GEN_CMD):** Triggers SRAM BIST (march test).
Result: COR_ERR_CMD = pass, LAT_ERR_CMD = single-bit corrected found,
UNC_ERR_CMD = double-bit uncorrectable.

---

### 4.8 Overlay L1/L2 Cache Nodes

**node_id:** `part=0x08, subp=Y, inst=0x00` (L1), `inst=0x01` (L2)
**Clock:** dm_clk (overlay domain)

**RD_CMD captures:**

| RSP_DATA word | Field           | Description                         |
|---------------|-----------------|-------------------------------------|
| [0][15:0]     | hit_count       | Cache hit counter (saturating)      |
| [0][31:16]    | miss_count      | Cache miss counter                  |
| [1][7:0]      | ecc_1bit        | 1-bit ECC events                    |
| [1][15:8]     | ecc_2bit        | 2-bit ECC events (uncorrectable)    |

**Note:** Overlay nodes run on dm_clk. BIU clock-domain crossing via toggle CDC.
MCPDLY must account for dm_clk latency (see §3 of EDC_HDD_V0.4).

---

### 4.9 Context-Switch SRAM Node

**node_id:** `part=0x08, subp=Y, inst=0x02`
**Memory:** Stores RISC-V register file + FPU state on context switch
**Clock:** dm_clk

**RD_CMD captures:** Same ECC layout as L1/L2 cache nodes.
**Self-test:** March-C via GEN_CMD — verifies all 32 context slots.

---

### 4.10 NOC2AXI / AXI2NOC VC-FIFO Nodes

**node_id:** `part=0x03, subp=Y, inst=0x08..0x0B` (VC0–VC3)
**N1B0:** RDATA_FIFO depth = 512 (configurable via define, default in N1B0_A8)

**RD_CMD captures:**

| RSP_DATA word | Field         | Description                          |
|---------------|---------------|--------------------------------------|
| [0][9:0]      | fill_level    | Current FIFO occupancy               |
| [0][10]       | overflow      | FIFO overflow (sticky)               |
| [0][11]       | underflow     | FIFO underflow (sticky)              |
| [1][31:0]     | total_flits   | Total flit count (saturating 32b)    |

**OVF event:** When overflow bit sets, node sends `OVF0_CMD..OVF3_CMD` event.

---

### 4.11 Router VC-FIFO Nodes

**node_id:** `part=0x04, subp=Y, inst=0xC0..0xC1` (VC0, VC1)
**N1B0 composite tile:** Router nodes at subp=3 are inside NOC2AXI_ROUTER composite.
For composite tile, nodeid_y=-1 offset applies (see N1B0_A6).

**RD_CMD:** Same layout as §4.10.

---

### 4.12 ATT SRAM Nodes

**node_id:** `part=0x03, subp=Y, inst=0x10..0x11` (ATT bank 0, 1)
**RTL module:** `tt_att` (inside NIU)
**Memory:** Per-NIU address translation table SRAM

**RD_CMD captures:**

| RSP_DATA word | Field        | Description                      |
|---------------|--------------|----------------------------------|
| [0][15:0]     | ecc_1bit     | Correctable ECC count            |
| [0][31:16]    | ecc_2bit     | Uncorrectable ECC count          |
| [1][19:0]     | last_err_idx | ATT entry index of last error    |

---

### 4.13 NIU MST/SLV Endpoint Nodes

**node_id:** `part=0x03, subp=Y, inst=0x0C..0x0F`
These nodes capture AXI transaction metadata for debug.

**RD_CMD captures (MST_RD_EP_TABLE example):**

| RSP_DATA word | Field         | Description                        |
|---------------|---------------|------------------------------------|
| [0][39:0]     | last_addr     | Last AXI read address (split D0/D1)|
| [1][7:0]      | last_axlen    | Last AXI burst length              |
| [1][15:8]     | last_axsize   | Last AXI burst size                |
| [2][11:0]     | outstanding   | Current outstanding transaction cnt|

---

### 4.14 NOC2AXI_ROUTER Composite Nodes (N1B0 specific)

**N1B0 places NOC2AXI_ROUTER_NE/NW_OPT at X={0,3}, Y=4 (BIU tile) + Y=3.**
The composite module contains EDC nodes for both Y=4 (NIU) and Y=3 (Router) rows.

**EDC chain inside composite:**
```
BIU[col] ──►  Y=4 NIU nodes (subp=4, part=0x03)
           ──►  Y=4 Router nodes (subp=4, part=0x04)
           ──►  cross-row wire (internal to composite, no tile boundary)
           ──►  Y=3 NIU nodes (subp=3, part=0x03)
           ──►  Y=3 Router nodes (subp=3, part=0x04)
           ──►  exits at Y=3 boundary → enters Y=2 Tensix tile
```

**Important:** Nodes inside composite at subp=3 have nodeid_y offset of -1 in EP table.
`nodeid_y = physical_Y - 1 = 3 - 1 = 2` for EP offset calculation.

SW addressing is **transparent** — use physical subp (3 or 4) in node_id; BIU handles routing.

---

## 5. New SW Work Features

### 5.1 Column Sweep

Sweep all active nodes in all 4 columns and collect status snapshots.

```c
#define MAX_NODES_PER_COL  64

typedef struct {
    uint16_t node_id;
    uint8_t  col;
    uint8_t  ret_code;
    uint32_t data[4];
} edc_snapshot_t;

int edc_column_sweep(edc_snapshot_t *out, int max_entries) {
    int n = 0;
    // Node list: all active node_ids per tile, per column
    const uint16_t node_list[] = {
        NODE(0x01,0,0x00), NODE(0x01,0,0x01), NODE(0x01,0,0x02), NODE(0x01,0,0x03),
        NODE(0x01,0,0x10), NODE(0x01,0,0x11),
        NODE(0x13,0,0x22), NODE(0x14,0,0x21), NODE(0x15,0,0x04),
        NODE(0x05,0,0x50), NODE(0x05,0,0x51), NODE(0x05,0,0x52), NODE(0x05,0,0x53),
        // Y=1, Y=2 Tensix tiles — repeat with subp=1,2
        // NOC2AXI_ROUTER composite at Y=4/Y=3
        NODE(0x03,4,0x08), NODE(0x03,4,0x09), NODE(0x04,4,0xC0),
        NODE(0x03,3,0x08), NODE(0x03,3,0x09), NODE(0x04,3,0xC0),
    };
    int num_nodes = sizeof(node_list)/sizeof(node_list[0]);

    for (int col = 0; col < 4; col++) {
        for (int i = 0; i < num_nodes && n < max_entries; i++) {
            out[n].col     = col;
            out[n].node_id = node_list[i];
            edc_read(col, node_list[i], out[n].data);
            uint32_t hdr = RD32(BIU_BASE[col] + 0x18);
            out[n].ret_code = (hdr >> 20) & 0x7;
            n++;
        }
    }
    return n;
}
```

---

### 5.2 Ring Loopback Test

Verifies ring continuity by sending a GEN_CMD to a known node and checking if the echo returns correctly. A timeout or RING_BREAK flag in STAT indicates a broken ring segment.

```c
bool edc_ring_loopback_test(int col) {
    // Use BIU's own loopback node (inst=0xFF, part=0x00 = reserved NOP node)
    // Any node that reliably ACKs can serve as loopback target
    // Simplest: use GEN_CMD to BRISC node (Y=0) — it will ACK and return
    uint16_t test_node = NODE(0x01, 0, 0x00);  // Tensix Y=0 BRISC
    uint32_t args[4]   = {0xDEAD, 0xBEEF, 0, 0};

    uint32_t base = BIU_BASE[col];
    WR32(base + 0x08, args[0]);
    WR32(base + 0x04, 0xFFFF);
    WR32(base + 0x00, (GEN_CMD << 16) | test_node);

    // Wait with timeout
    uint32_t timeout = 100000;
    while (!(RD32(base + 0x30) & 0x1) && --timeout);

    if (timeout == 0 || (RD32(base + 0x30) & 0x8)) {
        // STAT[2]=TIMEOUT or STAT[3]=RING_BREAK
        WR32(base + 0x30, 0xF);  // clear all
        return false;
    }
    WR32(base + 0x30, 0x1);
    return true;
}
```

---

### 5.3 Latch-Array BIST FSM Control (Method C)

This feature triggers the hardware `tt_latch_array_bist` module inside DEST/SRCA/SRCB via EDC.
The BIST FSM implements a full March-C sequence: `WRITE_0 → READ_0 → WRITE_1 → READ_1 → WRITE_CHKBRD → READ_CHKBRD → DONE/FAIL`.

```c
typedef struct {
    bool    pass;
    uint16_t fail_row;
    uint16_t fail_datum;
} bist_result_t;

// Run BIST on a latch array node and wait for result
bist_result_t edc_latch_bist(int col, int y, uint8_t part, uint8_t inst, uint8_t mode) {
    bist_result_t res = {false, 0, 0};

    // Step 1: Write CONFIG_REG with BIST mode
    uint32_t cfg[4] = {mode & 0x3, 0, 0, 0};
    edc_write(col, NODE(part, y, inst), cfg, 0x1);

    // Step 2: Trigger via PULSE_REG (GEN_CMD, args[0][0]=1)
    uint32_t pulse[4] = {1, 0, 0, 0};
    edc_gen(col, NODE(part, y, inst), pulse);

    // Step 3: Wait for self-test event
    // BIST duration ≈ 6 × DEPTH × DATUMS cycles; ~50K cycles at 1 GHz
    uint32_t ev = 0;
    uint32_t timeout = 200000;
    while (ev == 0 && --timeout) {
        ev = edc_poll_event(col);
    }

    if (timeout == 0) { res.pass = false; return res; }

    uint8_t cmd = (ev >> 16) & 0xF;
    if (cmd == 0xB) {  // ST_PASS (COR_ERR_CMD)
        res.pass = true;
    } else if (cmd == 0xA) {  // ST_LAT (LAT_ERR_CMD)
        uint32_t data[4];
        edc_read(col, NODE(part, y, inst), data);
        res.pass       = false;
        res.fail_row   = data[0] & 0xFFFF;
        res.fail_datum = data[0] >> 16;
    }
    return res;
}

// Convenience wrappers
bist_result_t bist_dest(int col, int y) {
    return edc_latch_bist(col, y, 0x13, 0x22, 1);  // March-C
}
bist_result_t bist_srca(int col, int y) {
    return edc_latch_bist(col, y, 0x14, 0x21, 1);
}
bist_result_t bist_srcb(int col, int y) {
    return edc_latch_bist(col, y, 0x15, 0x04, 1);
}
```

---

### 5.4 Background Polling Daemon

Registers IRQ handlers per column and drains the event queue into a ring buffer.
To be run as a low-priority thread or scheduled timer callback.

```c
#define EVENT_LOG_SIZE  256
typedef struct {
    uint64_t timestamp;
    uint8_t  col;
    uint8_t  cmd;
    uint16_t node_id;
    uint32_t data[2];  // fail_row, fail_datum (or data[0..1])
} edc_event_t;

static edc_event_t event_log[4][EVENT_LOG_SIZE];
static uint32_t    event_head[4];
static uint32_t    event_tail[4];

void edc_irq_handler(int col) {
    while (RD32(BIU_BASE[col] + 0x30) & 0x1) {
        uint32_t hdr  = RD32(BIU_BASE[col] + 0x18);
        uint32_t d0   = RD32(BIU_BASE[col] + 0x20);
        uint32_t d1   = RD32(BIU_BASE[col] + 0x24);
        WR32(BIU_BASE[col] + 0x30, 0x1);  // clear

        uint32_t idx = event_head[col] % EVENT_LOG_SIZE;
        event_log[col][idx].timestamp = get_timestamp();
        event_log[col][idx].col       = col;
        event_log[col][idx].cmd       = (hdr >> 16) & 0xF;
        event_log[col][idx].node_id   = hdr & 0xFFFF;
        event_log[col][idx].data[0]   = d0;
        event_log[col][idx].data[1]   = d1;
        event_head[col]++;
    }
    // Re-enable IRQ
    WR32(BIU_BASE[col] + 0x34, 1<<1);  // CTRL[1]=IRQ_CLR
}
```

---

### 5.5 Event Log

Drain and print all accumulated events:

```c
void edc_dump_event_log(int col) {
    while (event_tail[col] != event_head[col]) {
        uint32_t idx = event_tail[col] % EVENT_LOG_SIZE;
        edc_event_t *e = &event_log[col][idx];

        const char *cmd_str[] = {
            "WR","RD","?","?","?","?","?","?",
            "GEN","UNC_ERR","LAT_ERR","COR_ERR(PASS)","OVF0","OVF1","OVF2","OVF3"
        };

        printf("[%llu] col=%d node=0x%04X cmd=%s data=0x%08X 0x%08X\n",
            e->timestamp, e->col, e->node_id,
            cmd_str[e->cmd & 0xF], e->data[0], e->data[1]);

        event_tail[col]++;
    }
}
```

---

### 5.6 Harvest Decision

After POST, use EDC results to determine which columns should be harvested.

```c
// Column harvest decision: harvest if ANY node in column has UNC error
// or if ring loopback fails
#define HARVEST_THRESHOLD_UNC  1   // even 1 UNC = harvest

uint32_t edc_harvest_decision(void) {
    uint32_t harvest_mask = 0;  // bit[col + 4*y] per N1B0 ISO_EN encoding

    for (int col = 0; col < 4; col++) {
        // 1. Ring loopback
        if (!edc_ring_loopback_test(col)) {
            // Ring broken — harvest all tiles in this column
            for (int y = 0; y < 5; y++) harvest_mask |= (1 << (col + 4*y));
            continue;
        }

        // 2. Sweep all SRAM nodes for UNC errors
        edc_snapshot_t snaps[128];
        int cnt = edc_column_sweep_col(snaps, 128, col);
        for (int i = 0; i < cnt; i++) {
            if (snaps[i].ret_code != 0) continue;
            // Check for UNC ECC count in DATA[0][31:16]
            uint16_t unc = snaps[i].data[0] >> 16;
            if (unc >= HARVEST_THRESHOLD_UNC) {
                // Determine tile Y from subp field of node_id
                int y = (snaps[i].node_id >> 8) & 0x7;
                harvest_mask |= (1 << (col + 4*y));
            }
        }
    }
    return harvest_mask;
}

void edc_apply_harvest(uint32_t harvest_mask) {
    // Write to ISO_EN register (SFR)
    WR32(ISO_EN_REG, harvest_mask);
    // Simultaneously the EDC mux_demux_sel is set to bypass for harvested tiles
}
```

---

### 5.7 POST (Power-On Self Test)

Full POST sequence using EDC to test all major memory arrays at boot.

```c
typedef struct {
    bool ring_ok[4];
    bist_result_t dest[4][3];   // [col][y=0..2]
    bist_result_t srca[4][3];
    bist_result_t srcb[4][3];
    bool l1_ok[4][3][4];        // [col][y][part]
    bool ovl_l1_ok[4][3];
    bool att_ok[4][3];
    uint32_t harvest_mask;
} post_result_t;

post_result_t edc_post(void) {
    post_result_t r = {0};

    // Phase 1: Ring loopback test
    for (int col = 0; col < 4; col++) {
        r.ring_ok[col] = edc_ring_loopback_test(col);
    }

    // Phase 2: Latch array BIST (DEST/SRCA/SRCB) — all tiles Y=0..2
    for (int col = 0; col < 4; col++) {
        if (!r.ring_ok[col]) continue;
        for (int y = 0; y <= 2; y++) {
            r.dest[col][y] = bist_dest(col, y);
            r.srca[col][y] = bist_srca(col, y);
            r.srcb[col][y] = bist_srcb(col, y);
        }
    }

    // Phase 3: L1 SRAM BIST
    for (int col = 0; col < 4; col++) {
        if (!r.ring_ok[col]) continue;
        for (int y = 0; y <= 2; y++) {
            for (int part = 0; part < 4; part++) {
                uint32_t pulse[4] = {1, 0, 0, 0};
                edc_gen(col, NODE(0x05, y, 0x50+part), pulse);
                uint32_t ev = edc_wait_event(col, 100000);
                r.l1_ok[col][y][part] = ((ev >> 16) & 0xF) == 0xB;
            }
        }
    }

    // Phase 4: Harvest decision
    r.harvest_mask = edc_harvest_decision();

    return r;
}
```

---

### 5.8 Selective Node Query

Query a specific node by name string for debug/telemetry:

```c
typedef struct {
    const char *name;
    uint8_t part;
    uint8_t inst;
} edc_node_def_t;

static const edc_node_def_t node_table[] = {
    {"BRISC",        0x01, 0x00},
    {"TRISC0",       0x01, 0x01},
    {"TRISC1",       0x01, 0x02},
    {"TRISC2",       0x01, 0x03},
    {"GTILE_DEST",   0x13, 0x22},
    {"GTILE_SRCA",   0x14, 0x21},
    {"GTILE_SRCB",   0x15, 0x04},
    {"L1_PART0",     0x05, 0x50},
    {"L1_PART1",     0x05, 0x51},
    {"L1_PART2",     0x05, 0x52},
    {"L1_PART3",     0x05, 0x53},
    {"VC_FIFO0",     0x03, 0x08},
    {"VC_FIFO1",     0x03, 0x09},
    {"ATT_SRAM0",    0x03, 0x10},
    {"ATT_SRAM1",    0x03, 0x11},
    {"OVL_L1",       0x08, 0x00},
    {"OVL_L2",       0x08, 0x01},
    {"CTX_SW",       0x08, 0x02},
    {NULL, 0, 0}
};

int edc_query_by_name(const char *name, int col, int y, uint32_t *data4_out) {
    for (int i = 0; node_table[i].name; i++) {
        if (strcmp(node_table[i].name, name) == 0) {
            uint16_t id = NODE(node_table[i].part, y, node_table[i].inst);
            edc_read(col, id, data4_out);
            return 0;
        }
    }
    return -1;  // not found
}
```

---

## 6. Error Handling

**Standard error response flow:**

```
1. Check STAT register after every transaction
   - STAT[0]=RSP_VALID  → response available, check ret_code
   - STAT[1]=ERROR       → ring-level error
   - STAT[2]=TIMEOUT     → node did not respond within MCPDLY window
   - STAT[3]=RING_BREAK  → physical ring continuity lost

2. On TIMEOUT or RING_BREAK:
   - Re-run ring loopback test (§5.2)
   - If loopback fails → flag column for harvest (§5.6)
   - If loopback passes but single node times out → node is dead or harvested

3. On ret_code != 0:
   - 0x1 (no_ack):    node_id not present in ring (check inst table, §2.3)
   - 0x2 (parity):    ring bit-flip; retry once; escalate if persistent
   - 0x3 (timeout):   same as STAT[2] handling
   - 0x4 (denied):    security violation (SMN blocked access)

4. On UNC_ERR_CMD event:
   - Log node_id and timestamp
   - Read RSP_DATA[0..1] for error address details
   - If L1 SRAM: mark L1 partition as degraded, do not use for new allocations
   - If latch array: trigger firmware re-init of that FPU tile
   - Evaluate harvest threshold (§5.6)

5. On OVF event:
   - Read VC-FIFO node to get fill level
   - Check for deadlock: if fill_level == max and not draining → raise alert
```

---

## 7. Harvest & Bypass

When a tile is harvested (`ISO_EN[col + 4*y] = 1`):

1. ai_clk power domain is gated off for that tile
2. EDC mux_demux_sel is set to 1 (bypass) — the ring routes **around** the harvested node
3. **3-layer EDC bypass protection** ensures no ring break even if the tile is fully powered off:
   - Layer 1: combinatorial mux at node input/output
   - Layer 2: AON-domain flip-flop holds bypass select through power-off
   - Layer 3: BIU skips node_id range during sweep (SW must mirror this in `node_list[]`)

**SW must maintain a harvest state table** and exclude harvested nodes from sweeps:

```c
uint32_t g_harvest_mask = 0;  // set by edc_apply_harvest()

bool edc_node_is_harvested(int col, int y) {
    return (g_harvest_mask >> (col + 4*y)) & 1;
}
```

**Composite tile harvest (N1B0 NOC2AXI_ROUTER):**
The composite tile spans Y=4 and Y=3. Harvesting either row harvests the entire composite:
- `ISO_EN[col + 4*4]` or `ISO_EN[col + 4*3]` → both rows lose ai_clk
- SW should set **both** bits when harvesting the composite tile

---

## Appendix A — Full N1B0 Node Address Table

```
Format: node_id = { part[4:0], subp[2:0], inst[7:0] } = 16-bit value

Column X=0..3 (X implicit in BIU selection)
Tile rows Y=0,1,2 = Tensix; Y=3,4 = NOC2AXI_ROUTER composite

──────────────────────────────────────────────────────────────────────────────
Tensix tile (Y=0,1,2):
  BRISC         part=0x01 subp=Y inst=0x00  → node_id = 0x0800 | (Y<<8) | 0x00
  TRISC0        part=0x01 subp=Y inst=0x01  → 0x0801 | (Y<<8)
  TRISC1        part=0x01 subp=Y inst=0x02
  TRISC2        part=0x01 subp=Y inst=0x03
  UNPACK_TDMA   part=0x01 subp=Y inst=0x10
  PACK_TDMA     part=0x01 subp=Y inst=0x11
  GTILE0_FPU    part=0x10 subp=Y inst=0x20
  GTILE0_SRCA   part=0x14 subp=Y inst=0x21
  GTILE0_DEST   part=0x13 subp=Y inst=0x22
  SRCB          part=0x15 subp=Y inst=0x04
  L1_PART0..3   part=0x05 subp=Y inst=0x50..0x53
  OVL_L1        part=0x08 subp=Y inst=0x00
  OVL_L2        part=0x08 subp=Y inst=0x01
  CTX_SW        part=0x08 subp=Y inst=0x02

NOC2AXI_ROUTER composite (Y=4 upper row, Y=3 lower row):
  NIU_VC_FIFO0..3  part=0x03 subp=4or3 inst=0x08..0x0B
  MST_RD_EP        part=0x03 subp=4    inst=0x0C
  MST_WR_EP        part=0x03 subp=4    inst=0x0D
  SLV_RD_EP        part=0x03 subp=4    inst=0x0E
  SLV_WR_EP        part=0x03 subp=4    inst=0x0F
  ATT_SRAM0..1     part=0x03 subp=4    inst=0x10..0x11
  RDATA_FIFO       part=0x03 subp=4    inst=0x40
  ROUTER_VC0..1    part=0x04 subp=3    inst=0xC0..0xC1
──────────────────────────────────────────────────────────────────────────────
```

**Helper macro:**
```c
#define NODE(part, subp, inst)  ((uint16_t)(((part)<<11) | ((subp)<<8) | (inst)))
```

---

## Appendix B — Pseudo-code Reference

### B.1 BIST FSM State Machine (tt_latch_array_bist)

```
States: IDLE → WRITE_0 → READ_0 → WRITE_1 → READ_1 → WRITE_CHKBRD → READ_CHKBRD → DONE

IDLE:
    wait for i_bist_start (driven by EDC PULSE_REG via GEN_CMD)
    load DEPTH, DATUMS, DATUM_WIDTH from parameters
    goto WRITE_0

WRITE_0:
    for row in 0..DEPTH-1:
        for datum in 0..DATUMS-1:
            write 0x00000 to latch[row][datum]
    goto READ_0

READ_0:
    for row in 0..DEPTH-1:
        for datum in 0..DATUMS-1:
            data = read latch[row][datum]
            if data != 0x00000:
                fail_row   = row
                fail_datum = datum
                goto FAIL_LATCH

WRITE_1 / READ_1: (same as above with 0x7FFFF all-ones)

WRITE_CHKBRD:
    for row in 0..DEPTH-1:
        for datum in 0..DATUMS-1:
            pattern = (row+datum) % 2 ? 0x55555 : 0xAAAAA
            write pattern to latch[row][datum]

READ_CHKBRD: (verify same pattern)

DONE:
    o_bist_done  = 1
    o_bist_pass  = 1
    send ST_PASS_EVENT (COR_ERR_CMD) via EDC ring

FAIL_LATCH:
    o_bist_done     = 1
    o_bist_pass     = 0
    o_fail_row      = fail_row
    o_fail_datum    = fail_datum
    send ST_LAT_EVENT (LAT_ERR_CMD) via EDC ring
    RSP_DATA[0] = fail_row, RSP_DATA[1] = fail_datum
```

### B.2 BIU Init Sequence

```c
void edc_biu_init(int col) {
    uint32_t base = BIU_BASE[col];
    // 1. Assert INIT
    WR32(base + 0x34, 0x1);     // CTRL[0]=INIT
    // 2. Wait for INIT counter to expire (MCPDLY+1 ring cycles)
    //    MCPDLY=7 → wait at least 8 ring-clock cycles
    delay_cycles(16);
    // 3. Clear any stale status
    WR32(base + 0x30, 0xFF);    // W1C all STAT bits
    // 4. Enable IRQs if using interrupt mode
    WR32(base + 0x38, 0x7);     // IRQ_EN: COR+LAT+UNC
}
```

### B.3 Full POST Call Sequence

```c
int main_post(void) {
    // Init all BIUs
    for (int col = 0; col < 4; col++) edc_biu_init(col);

    // Run POST
    post_result_t result = edc_post();

    // Apply harvest
    edc_apply_harvest(result.harvest_mask);

    // Log results
    for (int col = 0; col < 4; col++) {
        printf("Col %d ring: %s\n", col, result.ring_ok[col] ? "OK" : "BROKEN");
        for (int y = 0; y <= 2; y++) {
            printf("  [%d,%d] DEST=%s SRCA=%s SRCB=%s\n",
                col, y,
                result.dest[col][y].pass ? "PASS" : "FAIL",
                result.srca[col][y].pass ? "PASS" : "FAIL",
                result.srcb[col][y].pass ? "PASS" : "FAIL");
        }
    }

    return (result.harvest_mask != 0) ? -1 : 0;
}
```

---

*End of EDC_SW_GUIDE_V0.1.md*

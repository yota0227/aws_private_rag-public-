# Trinity N1B0 Mailbox Architecture
## Complete Guide to Inter-processor Communication

**Document Version:** 1.0
**Date:** 2026-04-01
**Status:** For inclusion in N1B0_NPU_HDD (§9 extension + new §2.3.8)

---

## Table of Contents

1. Mailbox Overview
2. SMN Slave Mailboxes (APB-Accessible)
3. Tensix TRISC Mailboxes (Local, non-APB)
4. Mailbox Access Paths
5. Mailbox Usage Flows
6. Register Maps & Detailed Specification
7. Interrupt & Status Mechanism
8. Code Examples & Firmware Integration

---

## 1. Mailbox Overview

Trinity N1B0 provides **three distinct mailbox mechanisms** for inter-processor and inter-thread communication, each designed for a specific communication scope and bandwidth requirement:

| Mailbox Type | Location | Scope | APB Accessible | Purpose | Data Width |
|--------------|----------|-------|---|---------|-----------|
| **SMN SLAVE_MAILBOX_0** | SMN module (Dispatch) | Host ↔ Dispatch | ✅ **YES** | External CPU commands to firmware | 32-bit |
| **SMN SLAVE_MAILBOX_1** | SMN module (Dispatch) | Dispatch ↔ Host/Monitor | ✅ **YES** | Firmware responses back to host | 32-bit |
| **Tensix TRISC Mailbox** | Inside Tensix tile | TRISC↔TRISC (local) | ❌ **NO** | Task argument passing within tile | 32-bit FIFO |

---

## 2. SMN Slave Mailboxes (APB-Accessible Inter-Processor Mailboxes)

### 2.1 Overview

The SMN (Security Management Network) module provides two **hardware-assisted mailbox FIFOs** for inter-processor communication between:
- **SLAVE_MAILBOX_0**: Host CPU / External SoC Master → Dispatch tile firmware
- **SLAVE_MAILBOX_1**: Dispatch tile firmware → Host CPU / External SoC Master

These mailboxes are fully **APB slave accessible** at the Trinity top level, allowing external CPUs to:
- Enqueue commands without polling (write to SLAVE_MAILBOX_0)
- Poll completion status (read MBOX_STATUS registers)
- Receive responses (read from SLAVE_MAILBOX_1)
- Generate and handle interrupts on message arrival

---

### 2.2 SMN SLAVE_MAILBOX_0 Register Map

**Base Address:** `0x03010000 + 0x0400 = 0x03010400`
**Clock Domain:** `axi_clk` (host-synchronous)
**Access:** 32-bit aligned reads/writes via APB slave interface

```
┌─────────────────────────────────────────────────────────────────┐
│ SLAVE_MAILBOX_0 (Host → Dispatch)                               │
├─────────────────────────────────────────────────────────────────┤
│ Offset  │ Name              │ Access │ Width │ Description      │
├─────────┼───────────────────┼────────┼───────┼──────────────────┤
│ +0x00   │ MBOX_WRITE_DATA   │ W      │ 32-b  │ Write command    │
│         │                   │        │       │ data to queue    │
├─────────┼───────────────────┼────────┼───────┼──────────────────┤
│ +0x04   │ MBOX_READ_DATA    │ R      │ 32-b  │ Read (reserved)  │
│         │                   │        │       │ Not used in      │
│         │                   │        │       │ MBOX_0           │
├─────────┼───────────────────┼────────┼───────┼──────────────────┤
│ +0x08   │ MBOX_STATUS       │ R      │ 32-b  │ Status flags:    │
│         │                   │        │       │ [0]: full (1 if  │
│         │                   │        │       │       FIFO full) │
│         │                   │        │       │ [1]: empty       │
│         │                   │        │       │ [4:7]: count     │
│         │                   │        │       │ [31:8]: reserved │
├─────────┼───────────────────┼────────┼───────┼──────────────────┤
│ +0x0C   │ MBOX_INT_EN       │ RW     │ 32-b  │ Interrupt enable:│
│         │                   │        │       │ [0]: en_on_write │
│         │                   │        │       │ [1]: en_on_full  │
│         │                   │        │       │ [2]: en_on_empty │
└─────────────────────────────────────────────────────────────────┘
```

**Register Field Details:**

- **MBOX_WRITE_DATA** (WO)
  - Width: 32 bits
  - Write any command/data to this register → pushed into FIFO
  - Generates interrupt to firmware (if enabled)
  - On write: FIFO_COUNT incremented, FULL flag updated

- **MBOX_STATUS** (RO)
  - `[0] FULL`: 1 if FIFO at max depth (8 entries)
  - `[1] EMPTY`: 1 if FIFO empty (0 entries)
  - `[7:4] COUNT`: Current entry count (0-8)
  - `[31:8]`: Reserved, read as 0

- **MBOX_INT_EN** (RW)
  - `[0] EN_WRITE`: Generate interrupt when host writes to MBOX_WRITE_DATA
  - `[1] EN_FULL`: Generate interrupt when FIFO becomes full
  - `[2] EN_EMPTY`: Generate interrupt when FIFO becomes empty
  - `[31:3]`: Reserved

---

### 2.3 SMN SLAVE_MAILBOX_1 Register Map

**Base Address:** `0x03010000 + 0x0500 = 0x03010500`
**Clock Domain:** `axi_clk`
**Access:** 32-bit aligned reads/writes via APB slave interface
**Direction:** Dispatch firmware → Host CPU (response/status feedback)

```
┌─────────────────────────────────────────────────────────────────┐
│ SLAVE_MAILBOX_1 (Dispatch → Host)                               │
├─────────────────────────────────────────────────────────────────┤
│ Offset  │ Name              │ Access │ Width │ Description      │
├─────────┼───────────────────┼────────┼───────┼──────────────────┤
│ +0x00   │ MBOX_WRITE_DATA   │ W      │ 32-b  │ (Internal only)  │
│         │                   │        │       │ Firmware writes  │
│         │                   │        │       │ response data    │
├─────────┼───────────────────┼────────┼───────┼──────────────────┤
│ +0x04   │ MBOX_READ_DATA    │ R      │ 32-b  │ Host reads       │
│         │                   │        │       │ response/status  │
│         │                   │        │       │ from FIFO        │
├─────────┼───────────────────┼────────┼───────┼──────────────────┤
│ +0x08   │ MBOX_STATUS       │ R      │ 32-b  │ Status flags:    │
│         │                   │        │       │ [0]: full        │
│         │                   │        │       │ [1]: empty       │
│         │                   │        │       │ [7:4]: count     │
├─────────┼───────────────────┼────────┼───────┼──────────────────┤
│ +0x0C   │ MBOX_INT_EN       │ RW     │ 32-b  │ Interrupt enable:│
│         │                   │        │       │ [0]: en_on_write │
│         │                   │        │       │ (to host)        │
└─────────────────────────────────────────────────────────────────┘
```

**Register Field Details:**

- **MBOX_READ_DATA** (RO)
  - Width: 32 bits
  - Read from this register → pops entry from FIFO
  - RTC (Read-to-Clear): FULL flag clears on read if space becomes available
  - Returns the oldest entry (FIFO order)

- **MBOX_WRITE_DATA** (WO, internal firmware only)
  - Firmware writes response data → pushed to FIFO
  - Generates interrupt to host (if enabled)

- **MBOX_STATUS** (RO)
  - Same as SLAVE_MAILBOX_0
  - Indicates response FIFO occupancy

- **MBOX_INT_EN** (RW)
  - `[0] EN_WRITE`: Interrupt on firmware write (to host)
  - `[1] EN_FULL`: Interrupt when response FIFO full
  - `[2] EN_EMPTY`: Interrupt when response FIFO empty

---

### 2.4 Interrupt Signals

**Interrupt Destinations:**

| Mailbox | Signal Name | Target | Trigger Condition |
|---------|-------------|--------|------------------|
| SLAVE_MAILBOX_0 | `mbox0_intr` | Dispatch firmware (TRISC3) | Write from host (if EN_WRITE=1) |
| SLAVE_MAILBOX_1 | `mbox1_intr` | External host CPU | Write from firmware (if EN_WRITE=1) |

**Interrupt Handling:**
- Interrupts are **level-triggered** (remain asserted while condition true)
- Firmware/host **must read mailbox** to clear the condition
- Clearing via:
  - **MBOX_0**: Firmware reads message from internal FIFO
  - **MBOX_1**: Host reads response from MBOX_READ_DATA

---

## 3. Tensix TRISC Mailboxes (Local, Non-APB)

### 3.1 Overview

Each Tensix tile contains **4 independent TRISC threads** (TRISC0/1/2/3) that need to synchronize and share task arguments. The **TRISC mailbox** is a **local 8-entry × 32-bit FIFO per thread** implemented in `tt_unpack_arg_mailbox.sv`.

**Key Properties:**
- **Location:** Inside Tensix tile (local memory, NOT externally accessible)
- **Capacity:** 8 entries × 32 bits per thread
- **Access:** Local to TRISC instructions only (no APB interface)
- **Clock Domain:** `ai_clk` (compute cluster clock)
- **Purpose:** Passing task arguments between TRISC threads
  - Tile pointers (L1/DRAM addresses)
  - Data format (INT8, FP16, etc.)
  - Tile dimensions (M, N, K)
  - Other configuration parameters

---

### 3.2 TRISC Mailbox Hardware Architecture

```
Per Tensix Tile (tt_tensix_with_l1):
├─ TRISC0 (Pack thread)
│  └─ Local Mailbox FIFO (8 entries × 32-bit)
│     └─ Write by: TRISC3 (configuration)
│     └─ Read by:  TRISC0 (configuration)
│
├─ TRISC1 (Unpack thread)
│  └─ Local Mailbox FIFO (8 entries × 32-bit)
│     └─ Write by: TRISC3 (configuration)
│     └─ Read by:  TRISC1 (configuration)
│
├─ TRISC2 (Math thread)
│  └─ Local Mailbox FIFO (8 entries × 32-bit)
│     └─ Write by: TRISC3 (configuration)
│     └─ Read by:  TRISC2 (configuration)
│
└─ TRISC3 (Management thread)
   └─ Local Mailbox FIFO (8 entries × 32-bit)
      └─ Write by: External (via Rocket over NoC APB)
      └─ Read by:  TRISC3 (configuration)
```

**Note:** TRISC3 can receive task configuration from Rocket via the SMN mailbox system, then distribute to TRISC0/1/2 through local mailbox writes.

---

### 3.3 TRISC Mailbox Access Mechanism

**Hardware-level access (no CSR registers):**

```verilog
// Firmware (TRISC assembly/C): Read from local mailbox
uint32_t arg = trisc_mailbox_read();  // Pop from FIFO (blocking if empty)

// Firmware (TRISC3): Write to peer thread's mailbox
trisc_mailbox_write(peer_thread, arg);  // Push to TRISC0/1/2 mailbox
```

**Typical usage flow:**

1. **TRISC3 (management)** reads task descriptor from Rocket via SMN SLAVE_MAILBOX_0
   - Contains: tile ID, tile size, format, kernel ID

2. **TRISC3 distributes** to worker threads via local mailbox writes
   - TRISC0: M_tile, N_tile, format
   - TRISC1: K_tile, input format
   - TRISC2: K_tile, output format

3. **TRISC0/1/2 read** from their local mailbox at kernel start
   - Blocking read: stalls pipeline until argument available
   - Once read, proceed with kernel execution

---

### 3.4 TRISC Mailbox Status & Flow Control

**FIFO Status Bits (per thread):**

```
struct MailboxStatus {
  uint1  full;      // 1 if 8 entries queued (cannot write)
  uint1  empty;     // 1 if 0 entries (read would block)
  uint4  count;     // Number of pending entries (0-8)
};
```

**Flow Control:**

- **Write (TRISC3 → TRISC0/1/2)**: Stalls if target mailbox full
  - Firmware typically polls mailbox status before write
  - Or uses semaphore to ensure thread is not stalled

- **Read (TRISC0/1/2)**: Blocks if mailbox empty
  - Hardware: Instruction issue stalls (0 power consumption while waiting)
  - Resumes when TRISC3 posts argument

---

## 4. Mailbox Access Paths

### 4.1 SMN SLAVE_MAILBOX_0 Access Path (Host → Dispatch)

```
Host CPU (External SoC Master)
    ↓
    │ AXI write to address 0x03010400
    ↓
Trinity Top-Level (trinity.sv)
    ├─ NIU (NOC2AXI bridge)
    │  └─ Translates AXI → APB
    ↓
Dispatch Tile (tt_dispatch_top_east/west)
    ├─ APB Slave Interface
    │  └─ Routes to SMN module
    ↓
SMN Module (§9.5)
    ├─ SLAVE_MAILBOX_0 FIFO
    │  └─ Entry queued
    ↓
Interrupt Signal
    └─ mbox0_intr → TRISC3 (if enabled)
```

**Latency:** ~100-200 ns (APB protocol overhead) + interrupt handler latency

**Constraints:**
- FIFO capacity: 8 entries (32-bit each = 256 bits max)
- On overflow: Further writes stall until TRISC3 consumes

---

### 4.2 SMN SLAVE_MAILBOX_1 Access Path (Dispatch → Host)

```
Dispatch Firmware (TRISC3)
    ↓
    │ Write to SLAVE_MAILBOX_1 (internal register)
    ↓
SMN SLAVE_MAILBOX_1 FIFO
    ├─ Entry queued
    ↓
Interrupt Signal
    └─ mbox1_intr → Host CPU (if enabled)
    ↓
Host CPU (reads via APB)
    ├─ APB read from 0x03010504 (MBOX_READ_DATA)
    ↓
NIU APB bridge
    └─ Translates APB → AXI response
```

**Latency:** Response FIFO drains to host at APB clock rate (~10-20 ns per entry)

---

### 4.3 Tensix TRISC Mailbox Access Path (Local)

```
TRISC3 (Configuration)
    ↓
    │ Local register write: trisc_mailbox_write(thread_id, data)
    ↓
tt_unpack_arg_mailbox.sv (per-thread FIFO)
    ├─ TRISC0 Mailbox FIFO ← (if thread_id=0)
    ├─ TRISC1 Mailbox FIFO ← (if thread_id=1)
    ├─ TRISC2 Mailbox FIFO ← (if thread_id=2)
    └─ TRISC3 Mailbox FIFO ← (if thread_id=3)
    ↓
Target TRISC Thread
    ├─ Reads: trisc_mailbox_read()
    ├─ Blocking read (stalls on empty)
    └─ Proceeds with kernel execution
```

**Latency:** <1 cycle (local to tile, no external routing)

---

## 5. Mailbox Usage Flows

### 5.1 Complete Host-to-Firmware Command Flow

```
┌─────────────────────────────────────────────────────┐
│ Step 1: Host Prepares Command                       │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Host builds command packet:                         │
│  uint32_t cmd = (kernel_id << 16) | tile_id;      │
│                                                     │
│ or if multi-word:                                   │
│  struct Command {                                   │
│    uint16_t kernel_id;                             │
│    uint8_t  tile_id;                               │
│    uint8_t  format;                                │
│  } cmd;                                             │
│                                                     │
│ (Note: 32-bit mailbox limits to 4-byte messages)   │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Step 2: Host Writes to SLAVE_MAILBOX_0              │
├─────────────────────────────────────────────────────┤
│                                                     │
│  // Check if not full                              │
│  if (read_apb(0x03010408) & MBOX_FULL) {          │
│    wait_for_mbox0_not_full();  // Poll or sleep    │
│  }                                                  │
│                                                     │
│  // Write command                                   │
│  write_apb(0x03010400, (uint32_t)cmd);            │
│                                                     │
│  // Interrupt fires to firmware (if enabled)       │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Step 3: Firmware (TRISC3) Handles Interrupt         │
├─────────────────────────────────────────────────────┤
│                                                     │
│  void mbox0_interrupt_handler() {                  │
│    // Read command from mailbox                    │
│    uint32_t cmd = read_mbox0();  // Blocks if empty│
│                                                     │
│    // Parse command                                │
│    uint16_t kernel_id = (cmd >> 16) & 0xFFFF;    │
│    uint8_t  tile_id   = cmd & 0xFF;              │
│                                                     │
│    // Launch kernel on target tile                 │
│    launch_kernel(kernel_id, tile_id);             │
│  }                                                 │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Step 4: Firmware Signals Completion                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  // After kernel finishes:                         │
│  uint32_t status = (tile_id << 8) | KERNEL_DONE;  │
│  write_mbox1(status);  // Write to SLAVE_MAILBOX_1 │
│                                                     │
│  // Interrupt fires to host                        │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Step 5: Host Reads Response from SLAVE_MAILBOX_1    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  // Wait for response (interrupt or poll)          │
│  if (!mbox1_has_data()) {                          │
│    wait_for_mbox1_interrupt();                     │
│  }                                                 │
│                                                     │
│  // Read response                                  │
│  uint32_t status = read_apb(0x03010504);          │
│                                                     │
│  // Parse status                                   │
│  uint8_t tile_id = (status >> 8) & 0xFF;          │
│  if (status & KERNEL_DONE) {                       │
│    printf("Kernel %d completed on tile %d\n",     │
│            kernel_id, tile_id);                   │
│  }                                                 │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

### 5.2 Firmware-to-Tensix Worker Thread Flow

```
┌─────────────────────────────────────────────────────┐
│ Step 1: TRISC3 Fetches Tile Configuration           │
├─────────────────────────────────────────────────────┤
│                                                     │
│  // Read from SMN SLAVE_MAILBOX_0 (via NoC APB)   │
│  uint32_t tile_config = read_mbox0();             │
│                                                     │
│  // Unpack configuration                           │
│  struct TileConfig {                               │
│    uint16_t m_tile : 10;                          │
│    uint16_t n_tile : 10;                          │
│    uint16_t format : 4;   // Packed in 32-bit     │
│  } config = *(TileConfig*)&tile_config;           │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Step 2: TRISC3 Distributes to Worker Threads        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  // Pack message for TRISC0 (unpack)               │
│  uint32_t msg0 = (m_tile << 16) | format;         │
│  trisc_mailbox_write(TRISC0_ID, msg0);            │
│                                                     │
│  // Pack message for TRISC1 (math)                 │
│  uint32_t msg1 = (n_tile << 16) | format;         │
│  trisc_mailbox_write(TRISC1_ID, msg1);            │
│                                                     │
│  // Pack message for TRISC2 (pack)                 │
│  uint32_t msg2 = (k_tile << 16) | format;         │
│  trisc_mailbox_write(TRISC2_ID, msg2);            │
│                                                     │
│  // Release TRISC semaphore to start kernel        │
│  SEMPOST(sem_kernel_start);                        │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Step 3: Worker Threads Read Configuration           │
├─────────────────────────────────────────────────────┤
│                                                     │
│  // TRISC0 execution:                              │
│  void trisc0_kernel() {                            │
│    SEMGET(sem_kernel_start);  // Wait for release │
│                                                     │
│    // Read tile config from mailbox                │
│    uint32_t cfg = trisc_mailbox_read();           │
│      // Blocks here until TRISC3 writes           │
│    uint16_t m_tile = (cfg >> 16) & 0xFFFF;       │
│    uint8_t  format = cfg & 0xFF;                 │
│                                                     │
│    // Execute unpack loop with tile config         │
│    unpack_tile(m_tile, format);                   │
│                                                     │
│    SEMPOST(sem_unpack_done);  // Signal done      │
│  }                                                 │
│                                                     │
│  // Similar for TRISC1 (math) and TRISC2 (pack)   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 6. Register Maps & Detailed Specification

### 6.1 SMN Mailbox Register Summary

**SMN Base:** 0x03010000 (axi_clk domain)

```
┌────────────┬──────────────┬──────────┬──────────────────────────┐
│ Offset     │ Register     │ Access   │ Description              │
├────────────┼──────────────┼──────────┼──────────────────────────┤
│ 0x0400     │ MBOX0_WRITE  │ W        │ Host → FW command queue  │
│ 0x0404     │ MBOX0_READ   │ R        │ (Reserved)               │
│ 0x0408     │ MBOX0_STATUS │ R        │ full/empty/count         │
│ 0x040C     │ MBOX0_INT_EN │ RW       │ Interrupt control        │
├────────────┼──────────────┼──────────┼──────────────────────────┤
│ 0x0500     │ MBOX1_WRITE  │ W        │ (Internal, TRISC3 only)  │
│ 0x0504     │ MBOX1_READ   │ R        │ Host reads response      │
│ 0x0508     │ MBOX1_STATUS │ R        │ full/empty/count         │
│ 0x050C     │ MBOX1_INT_EN │ RW       │ Interrupt control        │
└────────────┴──────────────┴──────────┴──────────────────────────┘
```

### 6.2 Status Register Format (Both MBOX0 & MBOX1)

```
Bit Field         | Width | Read/Write | Description
─────────────────┼───────┼───────────┼─────────────────────────────
[0] FULL          | 1     | RO        | FIFO at max (8) entries
[1] EMPTY         | 1     | RO        | FIFO has 0 entries
[3:2] RESERVED    | 2     | RO        | Read as 0
[7:4] COUNT       | 4     | RO        | Current entry count (0-8)
[31:8] RESERVED   | 24    | RO        | Read as 0
```

### 6.3 Interrupt Enable Register Format

```
Bit Field         | Width | Read/Write | Description
─────────────────┼───────┼───────────┼─────────────────────────────
[0] EN_WRITE      | 1     | RW        | Interrupt on write to FIFO
[1] EN_FULL       | 1     | RW        | Interrupt when FIFO full
[2] EN_EMPTY      | 1     | RW        | Interrupt when FIFO empty
[31:3] RESERVED   | 29    | RW        | Reserved, write 0
```

---

## 7. Interrupt & Status Mechanism

### 7.1 Interrupt Generation

**SMN Mailbox interrupts are level-triggered:**

```
Condition                    | MBOX0          | MBOX1
─────────────────────────────┼────────────────┼──────────────────
Write from Host              | Sets EN_WRITE? | Sets EN_WRITE?
                             | → mbox0_intr   | → mbox1_intr
─────────────────────────────┼────────────────┼──────────────────
Write from TRISC3            | N/A            | Sets EN_WRITE?
                             |                | → mbox1_intr
─────────────────────────────┼────────────────┼──────────────────
FIFO becomes FULL            | Sets EN_FULL?  | Sets EN_FULL?
                             | → mbox0_intr   | → mbox1_intr
─────────────────────────────┼────────────────┼──────────────────
FIFO becomes EMPTY           | Sets EN_EMPTY? | Sets EN_EMPTY?
                             | → mbox0_intr   | → mbox1_intr
```

### 7.2 Interrupt Handling Best Practice

```c
// Host side (MBOX_0 write path):
void host_send_command(uint32_t cmd) {
  // Check if MBOX_0 has space
  while (read_apb(0x03010408) & MBOX_FULL) {
    // Wait or sleep until TRISC3 consumes
  }

  // Write command
  write_apb(0x03010400, cmd);
  // Interrupt fires to TRISC3 (if enabled)
}

// Firmware side (MBOX_0 read path):
void mbox0_irq_handler(void) {
  while (!(read_apb(0x03010408) & MBOX_EMPTY)) {
    uint32_t cmd = read_apb(0x03010400);  // Pop FIFO
    process_command(cmd);
  }
}

// Firmware side (MBOX_1 write path):
void firmware_send_response(uint32_t status) {
  // Check if MBOX_1 has space (or wait)
  while (read_apb(0x03010508) & MBOX_FULL) {
    // Firmware cannot be interrupted, so busy-wait
    // or handle in background task
  }

  // Write response
  write_apb(0x03010500, status);
  // Interrupt fires to host (if enabled)
}

// Host side (MBOX_1 read path):
uint32_t host_read_response(void) {
  // Interrupt service routine:
  while (!(read_apb(0x03010508) & MBOX_EMPTY)) {
    uint32_t response = read_apb(0x03010504);  // Pop FIFO
    return response;  // or queue if multiple expected
  }
}
```

---

## 8. Code Examples & Firmware Integration

### 8.1 Host CPU Driver (Linux/Bare-metal)

```c
/* trinity_mailbox.h */
#ifndef TRINITY_MAILBOX_H
#define TRINITY_MAILBOX_H

#include <stdint.h>

#define TRINITY_MBOX0_BASE    0x03010400
#define TRINITY_MBOX1_BASE    0x03010500

#define MBOX_WRITE_DATA_OFF   0x00
#define MBOX_READ_DATA_OFF    0x04
#define MBOX_STATUS_OFF       0x08
#define MBOX_INT_EN_OFF       0x0C

#define MBOX_FULL   (1 << 0)
#define MBOX_EMPTY  (1 << 1)
#define MBOX_COUNT  (0xF << 4)

typedef struct {
  uint16_t kernel_id;
  uint8_t  tile_id;
  uint8_t  format;
} MailboxCommand;

/* Host sends command to firmware */
int trinity_mbox0_send(MailboxCommand *cmd) {
  uint32_t data = (cmd->kernel_id << 16) |
                  (cmd->tile_id << 8) |
                  cmd->format;

  volatile uint32_t *mbox0_status =
    (volatile uint32_t *)(TRINITY_MBOX0_BASE + MBOX_STATUS_OFF);
  volatile uint32_t *mbox0_write =
    (volatile uint32_t *)(TRINITY_MBOX0_BASE + MBOX_WRITE_DATA_OFF);

  /* Poll until space available */
  int timeout = 10000;
  while ((*mbox0_status & MBOX_FULL) && --timeout > 0) {
    usleep(100);  /* Wait 100 us */
  }

  if (timeout <= 0) {
    return -1;  /* Timeout */
  }

  /* Write command */
  *mbox0_write = data;
  return 0;
}

/* Host reads response from firmware */
int trinity_mbox1_read(uint32_t *response) {
  volatile uint32_t *mbox1_status =
    (volatile uint32_t *)(TRINITY_MBOX1_BASE + MBOX_STATUS_OFF);
  volatile uint32_t *mbox1_read =
    (volatile uint32_t *)(TRINITY_MBOX1_BASE + MBOX_READ_DATA_OFF);

  /* Poll until data available */
  int timeout = 10000;
  while ((*mbox1_status & MBOX_EMPTY) && --timeout > 0) {
    usleep(100);  /* Wait 100 us */
  }

  if (timeout <= 0) {
    return -1;  /* Timeout */
  }

  /* Read response (RTC - read-to-clear) */
  *response = *mbox1_read;
  return 0;
}

/* Enable interrupts (optional) */
void trinity_mbox0_int_enable(void) {
  volatile uint32_t *mbox0_int_en =
    (volatile uint32_t *)(TRINITY_MBOX0_BASE + MBOX_INT_EN_OFF);
  *mbox0_int_en = 0x1;  /* Enable on write */
}

void trinity_mbox1_int_enable(void) {
  volatile uint32_t *mbox1_int_en =
    (volatile uint32_t *)(TRINITY_MBOX1_BASE + MBOX_INT_EN_OFF);
  *mbox1_int_en = 0x1;  /* Enable on write */
}

#endif
```

### 8.2 Firmware Driver (TRISC3)

```c
/* firmware/mailbox.c */
#include <stdint.h>

/* Mailbox register pointers (internal to Dispatch tile) */
#define MBOX0_WRITE_DATA  (*((volatile uint32_t *)0x3010400))
#define MBOX0_STATUS      (*((volatile uint32_t *)0x3010408))
#define MBOX1_WRITE_DATA  (*((volatile uint32_t *)0x3010500))
#define MBOX1_STATUS      (*((volatile uint32_t *)0x3010508))

/* Structures */
typedef struct {
  uint16_t kernel_id;
  uint8_t  tile_id;
  uint8_t  format;
} Command;

typedef struct {
  uint8_t  tile_id;
  uint8_t  status;    /* 0=DONE, 1=ERROR */
  uint16_t reserved;
} Response;

/* Firmware reads command from MBOX0 */
Command firmware_recv_command(void) {
  Command cmd;

  /* Wait for command (blocking read from mailbox) */
  uint32_t data;
  while ((MBOX0_STATUS & 0x2)) {  /* Wait if empty */
    /* Spin or sleep */
  }

  data = MBOX0_WRITE_DATA;  /* Pop from FIFO */

  cmd.kernel_id = (data >> 16) & 0xFFFF;
  cmd.tile_id   = (data >> 8) & 0xFF;
  cmd.format    = data & 0xFF;

  return cmd;
}

/* Firmware sends response to MBOX1 */
void firmware_send_response(Response *resp) {
  uint32_t data = (resp->tile_id << 8) | resp->status;

  /* Wait if FIFO full */
  int timeout = 10000;
  while ((MBOX1_STATUS & 0x1) && --timeout > 0) {
    /* Spin or do other work */
  }

  MBOX1_WRITE_DATA = data;  /* Push to FIFO, generates interrupt */
}

/* Main firmware kernel loop */
void firmware_main(void) {
  while (1) {
    /* Receive command */
    Command cmd = firmware_recv_command();

    /* Launch kernel on tile */
    int result = launch_kernel(cmd.kernel_id, cmd.tile_id, cmd.format);

    /* Send response */
    Response resp;
    resp.tile_id = cmd.tile_id;
    resp.status = (result == 0) ? 0 : 1;
    firmware_send_response(&resp);
  }
}
```

### 8.3 TRISC3 to Worker Thread Flow

```c
/* firmware/trisc_sync.c */
#include <stdint.h>

/* Per-tile TRISC mailbox (internal access) */
extern void trisc_mailbox_write(int thread_id, uint32_t data);
extern uint32_t trisc_mailbox_read(void);  // For this thread only

/* Semaphore operations */
extern void SEMPOST(uint32_t sem_id);
extern void SEMGET(uint32_t sem_id);

/* Configuration structure */
typedef struct {
  uint16_t m_tile;
  uint16_t n_tile;
  uint16_t k_tile;
  uint8_t  format;
  uint8_t  reserved;
} TileConfig;

#define SEM_KERNEL_START  0
#define SEM_UNPACK_DONE   1
#define SEM_MATH_DONE     2
#define SEM_PACK_DONE     3

/* TRISC3 distributes configuration to worker threads */
void trisc3_distribute_config(TileConfig *cfg) {
  /* Message format: pack into 32-bit values */

  /* TRISC0 (unpack) gets M_tile, K_tile, format */
  uint32_t msg0 = (cfg->m_tile << 16) | (cfg->k_tile << 8) | cfg->format;
  trisc_mailbox_write(TRISC0_ID, msg0);

  /* TRISC1 (math) gets N_tile, K_tile, format */
  uint32_t msg1 = (cfg->n_tile << 16) | (cfg->k_tile << 8) | cfg->format;
  trisc_mailbox_write(TRISC1_ID, msg1);

  /* TRISC2 (pack) gets M_tile, N_tile, format */
  uint32_t msg2 = (cfg->m_tile << 16) | (cfg->n_tile << 8) | cfg->format;
  trisc_mailbox_write(TRISC2_ID, msg2);

  /* Release all threads */
  SEMPOST(SEM_KERNEL_START);
}

/* TRISC0 (unpack) entry point */
void trisc0_kernel_entry(void) {
  /* Wait for kernel release */
  SEMGET(SEM_KERNEL_START);

  /* Read tile configuration from local mailbox */
  uint32_t cfg = trisc_mailbox_read();  // Blocks if empty

  uint16_t m_tile = (cfg >> 16) & 0xFFFF;
  uint16_t k_tile = (cfg >> 8) & 0xFF;
  uint8_t  format = cfg & 0xFF;

  /* Execute unpack loop */
  unpack_tile(m_tile, k_tile, format);

  /* Signal completion */
  SEMPOST(SEM_UNPACK_DONE);
}

/* TRISC1 (math) entry point */
void trisc1_kernel_entry(void) {
  SEMGET(SEM_KERNEL_START);

  uint32_t cfg = trisc_mailbox_read();
  uint16_t n_tile = (cfg >> 16) & 0xFFFF;
  uint16_t k_tile = (cfg >> 8) & 0xFF;
  uint8_t  format = cfg & 0xFF;

  /* Wait for unpack to finish */
  SEMGET(SEM_UNPACK_DONE);

  /* Execute math loop */
  math_tile(n_tile, k_tile, format);

  SEMPOST(SEM_MATH_DONE);
}

/* TRISC2 (pack) entry point */
void trisc2_kernel_entry(void) {
  SEMGET(SEM_KERNEL_START);

  uint32_t cfg = trisc_mailbox_read();
  uint16_t m_tile = (cfg >> 16) & 0xFFFF;
  uint16_t n_tile = (cfg >> 8) & 0xFF;
  uint8_t  format = cfg & 0xFF;

  /* Wait for math to finish */
  SEMGET(SEM_MATH_DONE);

  /* Execute pack loop */
  pack_tile(m_tile, n_tile, format);

  SEMPOST(SEM_PACK_DONE);
}
```

---

## 9. Mailbox Constraints & Limitations

### 9.1 Data Width Constraints

- **All mailboxes are 32-bit wide**
- For messages > 32 bits, split across multiple FIFO entries
- Alternative: Use SMN mailbox for command pointer, then read full structure from memory

### 9.2 FIFO Depth

- **Both SMN mailboxes:** 8 entries (256 bits total per mailbox)
- **Tensix TRISC mailboxes:** 8 entries per thread (32 bits per thread × 4 threads)

### 9.3 Latency

| Path | Latency | Notes |
|------|---------|-------|
| Host → MBOX0 (write) | ~200 ns | APB protocol + FIFO enqueue |
| TRISC3 reads MBOX0 | <1 µs | Via internal NoC APB |
| TRISC3 → TRISC0/1/2 (TRISC mailbox) | <1 cycle | Local, combinational |
| MBOX1 response → Host (read) | ~200 ns | APB protocol + FIFO dequeue |

### 9.4 Atomicity

- **32-bit accesses are atomic** (single APB transaction)
- **FIFO read/write:** Each access is one entry (atomic pop/push)

### 9.5 Error Handling

- **On overflow:** Further writes block (APB request waits)
- **On underflow:** Read returns undefined data (firmware must ensure data availability)
- **Recommendation:** Firmware must implement timeout and error recovery

---

## 10. Summary Table: All Mailboxes in Trinity

```
┌────────────────────┬──────────────┬────────────┬────────────┬─────────┐
│ Mailbox            │ Location     │ APB Access │ FIFO Depth │ Purpose │
├────────────────────┼──────────────┼────────────┼────────────┼─────────┤
│ SLAVE_MAILBOX_0    │ SMN module   │ ✅ YES     │ 8 entries  │ Host→FW │
│ (0x03010400)       │ (Dispatch)   │ (32-bit)   │ (256 bits) │ cmd     │
├────────────────────┼──────────────┼────────────┼────────────┼─────────┤
│ SLAVE_MAILBOX_1    │ SMN module   │ ✅ YES     │ 8 entries  │ FW→Host │
│ (0x03010500)       │ (Dispatch)   │ (32-bit)   │ (256 bits) │ resp    │
├────────────────────┼──────────────┼────────────┼────────────┼─────────┤
│ TRISC0 Mailbox     │ Tensix tile  │ ❌ NO      │ 8 entries  │ TRISC3→ │
│ (local)            │ (private)    │ (32-bit)   │ (256 bits) │ TRISC0  │
│ TRISC1 Mailbox     │ Tensix tile  │ ❌ NO      │ 8 entries  │ TRISC3→ │
│ (local)            │ (private)    │ (32-bit)   │ (256 bits) │ TRISC1  │
│ TRISC2 Mailbox     │ Tensix tile  │ ❌ NO      │ 8 entries  │ TRISC3→ │
│ (local)            │ (private)    │ (32-bit)   │ (256 bits) │ TRISC2  │
│ TRISC3 Mailbox     │ Tensix tile  │ ❌ NO      │ 8 entries  │ Local   │
│ (local)            │ (private)    │ (32-bit)   │ (256 bits) │ (unused)│
└────────────────────┴──────────────┴────────────┴────────────┴─────────┘
```

---

## Appendix A: Register Definitions (Verilog)

```verilog
// SMN SLAVE_MAILBOX_0 (Host → Firmware)
typedef struct packed {
  logic [31:0] write_data;      // +0x00: Write to queue
  logic [31:0] read_data;       // +0x04: Reserved
  logic [31:0] status;          // +0x08: full, empty, count
  logic [31:0] int_en;          // +0x0C: Interrupt control
} smn_slave_mailbox_0_t;

// MBOX_STATUS register format
typedef struct packed {
  logic [23:0] reserved;
  logic [3:0]  count;           // [7:4]: Entry count
  logic        empty;            // [1]:   FIFO empty
  logic        full;             // [0]:   FIFO full
} mbox_status_t;

// MBOX_INT_EN register format
typedef struct packed {
  logic [28:0] reserved;
  logic        en_empty;         // [2]:   Int on empty
  logic        en_full;          // [1]:   Int on full
  logic        en_write;         // [0]:   Int on write
} mbox_int_en_t;
```

---

**Document End**

---

**Revision History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-01 | N1B0 Team | Initial mailbox chapter with complete register maps, usage flows, and code examples |


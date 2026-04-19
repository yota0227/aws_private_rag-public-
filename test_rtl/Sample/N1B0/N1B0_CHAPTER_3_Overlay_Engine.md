# §3 Overlay Engine — Data Movement Orchestration

The overlay engine is the autonomous data-movement subsystem within each Tensix tile, responsible for orchestrating transfers between the on-chip L1 SRAM (3 MB per cluster) and external DRAM. It decouples the TRISC processor cores from DMA execution latency, allowing firmware to initiate transfers via register writes and continue computation while overlay hardware autonomously moves data in parallel.

## 3.1 Overview and Architecture

### 3.1.1 Role and Purpose

The overlay engine provides:
- **Autonomous DMA**: Once programmed via CSR writes, the overlay hardware generates NoC packets and injects them without further TRISC involvement
- **TRISC decoupling**: TRISC firmware writes a command register and continues execution; overlay executes the transfer independently
- **8 independent streams**: Per Tensix cluster, allowing pipelined and concurrent data movement
- **L1/DRAM bridge**: Primary mechanism for tensor data movement between fast on-chip L1 (3 MB per cluster) and slower DRAM
- **Context switching**: Saves/restores L1 and L2 cache state across kernel context boundaries (§3.5)

### 3.1.2 Container Module: `tt_neo_overlay_wrapper`

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

### 3.1.3 Overlay vs. iDMA: Two DRAM Access Mechanisms

| Property | Overlay Streams | iDMA Engine (§6) |
|----------|-----------------|-----------------|
| Initiator | TRISC0/1/2/3 CSR write | Dispatch CPU via iDMA instruction |
| Path | TRISC CSR → NoC → NIU → AXI → DRAM | Dispatch iDMA → AXI → DRAM (direct, no NoC) |
| Purpose | L1 ↔ DRAM movement | Weight loading, model parameters |
| Capacity | 8 streams, sequential at DRAM | Dedicated AXI master port |
| Latency | 100–150+ cycles | Lower latency (direct AXI) |
| Competition | With iDMA for DRAM bandwidth | With overlay streams for AXI bandwidth |

---

## 3.2 Hardware Components

### 3.2.1 Overlay Stream Controller

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

### 3.2.2 TDMA (Tile DMA) Engine

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

### 3.2.3 MOP (Micro-Operation Packet) Sequencer

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

### 3.2.4 Stream Status Registers

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

## 3.3 Data Paths and NoC Integration

### 3.3.1 Complete DRAM Access Path

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

### 3.3.2 NIU Addressing: Composite vs. Standalone

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

### 3.3.3 Clock Domain Crossings

The overlay engine bridges three clock domains:

| Crossing | Source → Dest | Mechanism | Location |
|----------|---|---|---|
| ai_clk → noc_clk | TRISC CSR write → Overlay inject | CDC FIFO | overlay_wrapper (input side) |
| noc_clk → ai_clk | Stream status readback | CDC FIFO | overlay_wrapper (output side) |
| noc_clk → dm_clk | L1 data ingress | Synchronizer FIFO | L1 partition interface |

**CDC Design Principle:** FIFOs decouple clock domains without imposing synchronous reset relationships. TRISC (ai_clk) can continue while overlay DMA (noc_clk) executes at potentially different frequency.

### 3.3.4 L1 Memory Hierarchy Integration

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

## 3.4 Stream Programming Model and Register Interface

### 3.4.1 Stream CSR Registers per Cluster

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

### 3.4.2 Stream Status Polling

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

### 3.4.3 Stream Lifecycle State Machine

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

## 3.5 Context Switching

### 3.5.1 Purpose and Mechanism

**Context Switching:** Dynamic switching between different kernel workloads while preserving L1 and L2 cache state

**Hardware Support:**
- 2 SRAM macros per Tensix tile for context state (dm_clk domain)
- Partition control (PRTN) chain synchronizes power domain enable/disable
- Selective clock gating allows independent power-down of instruction engines while keeping L1 accessible

### 3.5.2 Save/Restore Flow

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

### 3.5.3 PRTN Chain Integration

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

## 3.6 Performance Characteristics

### 3.6.1 Data Rate and Throughput

**Theoretical Peak** (per NIU, per column):
- 512-bit flit × 1 GHz = 512 GB/s
- 512-bit flit × 800 MHz = 409.6 GB/s

**Practical Achievable** (with contention):
- DRAM controller bandwidth: 100–200 GB/s (typical DDR5)
- AXI arbitration: Multiple NIUs (2 composite + 2 standalone) contend for DRAM
- NoC congestion: Router virtual channels may stall under heavy all-to-all traffic
- **Expected sustainable throughput:** 50–150 GB/s per NIU (highly workload-dependent)

### 3.6.2 Latency Model

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

### 3.6.3 Stream Capacity and Concurrency

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

## 3.7 Integration with Other Components

### 3.7.1 TRISC Cores and Synchronization

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

### 3.7.2 FPU Integration

**FPU and Overlay Independence:**
- FPU reads SRCA/SRCB independently (filled by unpack engine via TRISC1)
- FPU writes DEST (read by pack engine via TRISC0)
- **No direct overlay-to-FPU path:** Data flows DRAM → L1 → TRISC1 → SRCA/SRCB → FPU

**Pipelined execution:** While FPU computes, overlay can simultaneously:
- Fetch next activation tensor from DRAM
- Write output tensor to L1 for next kernel stage

### 3.7.3 NoC Integration

**NoC packet generation:**
- Overlay generates standard NoC flits (512-bit, `noc_header_address_t` format)
- Uses DOR (Dimension-Order) routing or dynamic routing based on NoC config
- Virtual channel arbitration handled by tt_trinity_router (transparent to overlay)

**NoC port for overlay:**
- Local port: flit_out_req / flit_out_resp pair
- Direction: Always toward NIU (fixed routing pattern for DMA)

### 3.7.4 NIU (NOC2AXI) Integration

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

### 3.7.5 SMN (System Management Network) Security Integration

**SMN pre-ATT security fence:**
- 8 independently programmable address ranges (allow/block/log)
- Checked **before** ATT lookup
- **Violation action:** Assert `slv_ext_error` signal → escalate to CRIT interrupt

**Firmware responsibility:**
- Configure SMN ranges to restrict overlay stream read/write access to authorized DRAM regions
- Example: Prevent weight tensors from being written; allow only reading

### 3.7.6 EDC Ring Integration

**EDC node per Tensix cluster:**
- Positioned between NoC node and L1 node in ring traversal
- **OVL (Overlay) node:** Monitors EDC across the overlay engine
- **Ring chain bypass:** If overlay tile is harvested (ISO_EN asserted), OVL node is bypassed

**Overlay-related EDC errors:**
- Error in AXI transaction (SLVERR from external slave) → CRIT interrupt
- Parity error in L1 write path → ECC ± escalation
- NIU timeout (no RDATA within timeout) → CRIT interrupt

---

## 3.8 Power Management and DFX

### 3.8.1 Clock Gating

**Clock gate locations:**
- `overlay_wrapper_dfx`: Gates `dm_clk` to L1/L2 cache
- `instrn_engine_wrapper_dfx`: Gates `ai_clk` to TRISC instruction engines
- `t6_l1_partition_dfx`: Independent L1 partition clock gating

**Design principle:** L1 can remain accessible for DMA when instruction engines are gated (power saving for idle kernels).

### 3.8.2 Reset Hierarchy

**Reset sources:**
- `i_aiclk_reset_n` — AI clock domain reset (from per-column i_ai_reset_n[X])
- `i_nocclk_reset_n` — NoC clock domain reset (from global i_noc_reset_n)
- `i_core_reset_n` — TDMA/pack/unpack core reset
- `i_uncore_reset_n` — Overlay uncore (L1 interface) reset

**Reset propagation:**
- Async deassertion at top level
- Synchronized internally via 3-stage synchronizer per domain
- Maintains reset sequencing: upstream (NIU, Router) before downstream (Tensix)

### 3.8.3 DFX Integration

**Wrappers:**
- `tt_overlay_wrapper_dfx` — Overlay engine DFX wrapper
- `tt_instrn_engine_wrapper_dfx` — TRISC instruction engine DFX wrapper
- `tt_t6_l1_partition_dfx` — L1 partition DFX wrapper

**Features:**
- Tessent scan chain integration
- Clock gating control via Tessent SIB
- DFT mode override (clock enables forced high for scan)

---

## 3.9 RTL File Locations and Key Parameters

### 3.9.1 Core RTL Files

| File | Location | Purpose |
|------|----------|---------|
| `tt_neo_overlay_wrapper.sv` | `/secure_data_from_tt/20260221/tt_rtl/overlay/rtl/` | Main overlay container module |
| `tt_instrn_engine.sv` | `/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/` | MOP sequencer, TDMA orchestration |
| `tt_trisc.sv` | `tt_rtl/tt_tensix_neo/src/hardware/trisc/` | TRISC0/1/2 core |
| `tt_risc_wrapper.sv` | `tt_rtl/tt_tensix_neo/src/hardware/trisc/` | TRISC3 (RV32I wrapper) |
| `tt_overlay_pkg.sv` | `/secure_data_from_tt/20260221/tt_rtl/overlay/rtl/` | Package definitions (types, constants) |
| `tt_t6_local_regs_pkg.sv` | `tt_rtl/tt_tensix_neo/src/` | Register interface definitions |

### 3.9.2 Key Parameters

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

### 3.9.3 Register Map Summary

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

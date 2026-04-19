# Overlay Engine Extraction Findings

## Executive Summary

This document consolidates all overlay engine information extracted from N1B0_NPU_HDD_v0.99.md and RTL files to inform the creation of a comprehensive new §3 Overlay Engine chapter. The overlay engine is the data-movement orchestration subsystem within each Tensix tile, enabling autonomous DMA transfers between L1 and external DRAM without requiring explicit TRISC involvement after initial CSR programming.

---

## Section 1: Architecture Overview

### 1.1 Role and Purpose

The overlay engine is responsible for:
- **Autonomous data movement**: Once programmed via register writes, the overlay hardware generates and injects NoC packets autonomously
- **TRISC decoupling**: Enables TRISC3 to program a DRAM transfer and continue executing firmware while overlay executes the DMA
- **L1/DRAM bridge**: Acts as the primary mechanism for moving tensor data between on-chip L1 (3MB per cluster) and off-chip DRAM
- **Context switching and tile orchestration**: The `tt_neo_overlay_wrapper` module manages L1/L2 caches, context switch logic, CDC FIFOs, SMN security, EDC integration, and CPU wrapper

### 1.2 Container Module: `tt_neo_overlay_wrapper`

**File**: `/secure_data_from_tt/20260221/tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv`

**Module imports**:
- `tt_overlay_tensix_cfg_pkg`
- `tt_overlay_pkg`
- `tt_noc_pkg`

**Key responsibilities**:
- Manages clock domains: `i_core_clk`, `i_aiclk`, `i_nocclk`, `i_ref_clk`
- Reset distribution and synchronization (aiclk_reset, noc_clk_reset)
- Overlay stream CSR interface
- L1/L2 memory hierarchy control
- CDC FIFO bridge between `ai_clk` and `noc_clk` domains
- Context switch SRAM state management
- SMN (System Management Network) security configuration
- EDC (Error Detection & Correction) integration
- CPU (Rocket) wrapper integration

---

## Section 2: Hardware Components

### 2.1 Overlay Stream Controller

**Purpose**: Converts CSR register writes into NoC packet injections

**CSR Programming Model**:
```
Mechanism: Overlay stream control registers
Interface: noc_neo_local_regs_intf (tt_instrn_engine.sv)
Width: 32-bit register writes
Accessibility: All 4 TRISC threads (TRISC0, TRISC1, TRISC2, TRISC3)
```

**Register Configuration Fields**:
1. **Source and destination addresses** — NoC endpoint coordinates + L1 byte offset
2. **Transfer size** — Number of 512-bit flits
3. **Stream ID** — Which of 8 overlay streams to use
4. **Direction** — L1→NoC→DRAM write, or DRAM→NoC→L1 read

**Key Constraint**: `MAX_TENSIX_DATA_RD_OUTSTANDING = 4` (8 in large TRISC mode)
- Firmware must not issue more than this many outstanding read streams before checking completion status

### 2.2 TDMA (Tile DMA) Engine

**Components**:
- Pack engine (TRISC0)
- Unpack engine (TRISC1)
- MOP sequencer (TRISC2 control path)
- Context switch hardware

**Architecture**:
```
TRISC0 (Pack)        TRISC1 (Unpack)       TRISC2 (Math)        TRISC3 (Mgmt)
│                    │                     │                    │
├─ reads DEST RF     ├─ reads L1/NoC       ├─ issues MOP        ├─ NoC DMA control
├─ format convert    ├─ unpacks tensor     ├─ drives FPU        ├─ interrupts
├─ writes L1/NoC     ├─ loads SRCA/SRCB    ├─ semaphore mgmt    ├─ tile lifecycle
└─ semaphore sync    └─ semaphore sync     └─ completion        └─ boot
```

### 2.3 MOP (Micro-Operation Packet)

**Definition**: Compressed instruction format for expressing tensor operations

**Format**: 32-bit word with fields:
- `mop_type` — operation type
- `done` — completion flag
- `loop_count` — loop iteration count
- `zmask` — z-plane mask (for unpack loop FSM)

**Examples**: One MOP encodes work that would require hundreds of raw RISC-V instructions

**Key RTL Files**:
- `tt_instrn_engine.sv` — MOP sequencer and TDMA orchestration
- `tt_trisc.sv` — Per-thread core (one per TRISC0/1/2)
- `tt_risc_wrapper.sv` — TRISC3 RV32I core wrapper

### 2.4 Stream Status Registers

**Status tracking**:
- `trisc_tensix_noc_stream_status[thread][stream]`
- 8 per-stream status registers per TRISC
- Each TRISC can directly read its own stream status
- Used by firmware to poll for overlay DMA completion

---

## Section 3: Data Paths and NoC Integration

### 3.1 Complete DRAM Access Path

```
TRISC firmware
    │ 32-bit register write to overlay stream CSR
    ▼
Overlay stream controller (tt_neo_overlay_wrapper)
    │ NoC packet injection (512-bit flit)
    │ Destination: NIU endpoint
    │   X=0 standalone:  dst_x=0, dst_y=4
    │   X=3 standalone:  dst_x=3, dst_y=4
    │   X=1 composite:   dst_x=1, dst_y=3 (router row)
    │   X=2 composite:   dst_x=2, dst_y=3 (router row)
    ▼
NoC fabric (tt_trinity_router)
    │ DOR or dynamic routing to NIU tile
    ▼
NIU (tt_noc2axi, inside NOC2AXI composite tile)
    │ ATT address translation: NoC address → AXI address
    │ AXI4 burst (512-bit data bus, 56-bit address)
    ▼
External DRAM (via AXI master port)
```

### 3.2 Port Specifications for End-to-End Data Movement

| Stage | Port/Signal | Width | Frequency | Description |
|-------|---|---|---|---|
| Overlay → NoC | Flit payload | 512 bits | noc_clk | One complete flit (header or data) |
| Overlay stream CSR | Address | 32 bits | ai_clk | Logical NoC destination address |
| Overlay stream CSR | Size | N bits | ai_clk | Number of 512-bit flits to transfer |
| NIU – AXI Master | ARADDR | 56 bits | axi_clk | Physical DRAM address |
| NIU – AXI Master | ARLEN[7:0] | 8 bits | axi_clk | Burst length = (bytes/64)−1; max 255 |
| NIU – AXI Master | ARSIZE[2:0] | 3 bits | axi_clk | **Always 3'b110 = 64-byte beat** |
| NIU – AXI Master | ARBURST[1:0] | 2 bits | axi_clk | **Always 2'b01 = INCR** |
| AXI Slave (DRAM) | RDATA | 512 bits | axi_clk | Read data from DRAM |
| NIU – RDATA FIFO | FIFO depth | 512 entries | axi_clk | **32 KB buffering capacity** |
| L1 side channel | Write payload | 512 bits | noc_clk | Direct L1 SRAM write |
| L1 side channel | SRAM address | 13 bits | noc_clk | Addresses 3MB L1 partition |

### 3.3 Clock Domain Crossings (CDC)

**Synchronization points**:
- **ai_clk → noc_clk**: Overlay stream CSR interface (FIFOs in overlay wrapper)
- **noc_clk → ai_clk**: Stream status readback (FIFOs in overlay wrapper)
- **noc_clk → dm_clk**: L1 cache data path (synchronizer FIFOs)

**Key constraint**: CDC FIFOs allow decoupling of TRISC (ai_clk) from overlay DMA execution (noc_clk)

### 3.4 L1 Partition Integration

**L1 architecture**:
- 512 SRAM macros per cluster = 3 MB capacity
- Dedicated 512-bit "NoC side channel" port
- **Data movement bypass**: L1 side channel receives DMA write payloads directly from NoC without going through TRISC
- Direct TRISC access: 128-bit per-thread bus to L1

**Path precedence**:
```
① DRAM → NoC → L1 side channel (data ingress, direct write, no TRISC involvement)
② TRISC ↔ L1 (128-bit per thread, for format conversion/inspection)
③ L1 → NoC side channel → NoC → DRAM (data egress, via overlay stream command)
```

---

## Section 4: Stream Programming and CSR Interface

### 4.1 Stream Register Architecture

**Accessible from**: All 4 TRISC threads

**Register set per stream** (8 total streams per cluster):
- Source address (NoC endpoint + L1 offset)
- Destination address
- Transfer size (in 512-bit flits)
- Direction (read=DRAM→L1, write=L1→DRAM)
- Control bits (stream enable, start pulse)

### 4.2 Burst Length Calculation

```
ARLEN = (total_bytes / 64) − 1

Examples:
  512 B transfer:   ARLEN = 7   (8 beats)
  4 KB transfer:    ARLEN = 63  (64 beats)
  16 KB transfer:   ARLEN = 255 (256 beats, maximum)
  32 KB transfer:   Requires 2 separate overlay stream commands
```

**Hardware constraint**: Max single AXI burst = 256 beats × 64 bytes = **16 KB**
- Larger transfers must be split across multiple overlay stream commands

### 4.3 Stream Status Polling

**Firmware idiom**:
```
TRISC: write overlay stream CSR (source, dest, size, direction)
TRISC: continue executing firmware
[Overlay DMA executes autonomously]
TRISC: poll trisc_tensix_noc_stream_status[thread][stream] for completion
TRISC: proceed when status indicates DMA complete
```

**Polling semantics**:
- Status bits indicate: transfer complete, error, outstanding count
- Cleared on next stream command
- Can be polled multiple times without resetting

### 4.4 Outstanding Request Limit

**Max in-flight read requests**: `MAX_TENSIX_DATA_RD_OUTSTANDING = 4` (8 in large mode)

**Enforcement**:
- Firmware must check status before issuing 5th simultaneous read
- Prevents FIFO overflow in NIU RDATA buffer
- Measured by stream status registers

---

## Section 5: Context Switching Architecture

### 5.1 Context Switch SRAM

**Component**: Part of `tt_neo_overlay_wrapper`

**Capacity**: 2 × 14 tiles = 28 macros (dm_clk domain)

**Purpose**: Store L1/L2 cache hierarchy state across kernel context switches

**Mechanism**:
- Save context on kernel completion
- Restore context on next kernel invocation
- Reduces memory bandwidth for hot-reloading frequently-accessed tensors

### 5.2 Partition Control Signals

| Signal | Width | Purpose |
|--------|-------|---------|
| `PRTNUN_FC2UN_RSTN_IN` | 1 | Dynamic context-switch partition reset |
| Context-switch timing | async_low | Partition control |

**Synchronization**: `sync3r` (PRTN_clk domain)

### 5.3 L1/L2 Cache Orchestration

**Hierarchy**:
- **L1 cache** (per cluster, per thread access)
  - Data cache: 128×144 bits × 16 macros (per tile)
  - Tag cache: 32×100 bits × 8 macros (per tile)
  - Clock domain: `dm_clk` (data-move clock)
  
- **L2 cache** (system-level shared cache)
  - Data: 20 macros per tile
  - Director: included with data
  - Clock domain: `dm_clk`

**Clock gating**: Enables independent power management per tile during kernel execution

---

## Section 6: Performance Characteristics

### 6.1 Achievable Data Rates

**Per-NIU sustained bandwidth** (theoretical):
```
Data rate = 512 bits/cycle × frequency

At 1 GHz: 512 GB/s per NIU
At 800 MHz (conservative): 409.6 GB/s per NIU
```

**Practical limiting factors**:
1. External DRAM bandwidth (100–200 GB/s typical)
2. AXI bus arbitration (contention with iDMA, Tensix, Dispatch)
3. NoC mesh routing delays (6–8+ noc_clk cycles per flit)
4. ATT lookup latency (<1 cycle)
5. RDATA FIFO occupancy (512-entry FIFO = 32 KB buffer)

**N1B0 aggregate** (4 NIU endpoints):
- Theoretical: 4 × 512 bits/cycle = 2048 bits/cycle
- Practical: ~150–200 GB/s total (shared DRAM controller bottleneck)

### 6.2 Latency Components

**Total read latency** (TRISC register write to L1 data available):

```
T_total = T_overlay_inject + T_noc_forward + T_atu + T_dram + T_noc_response + T_l1_write

  ├─ T_overlay_inject:   1–2 ai_clk (CSR write processing)
  ├─ T_noc_forward:      6–8 noc_clk (source to NIU Y=4 routing)
  ├─ T_atu:              <1 axi_clk (ATT lookup, pipelined)
  ├─ T_dram:             50–100 axi_clk (DRAM row-buffer hit to RDATA)
  ├─ T_noc_response:     6–8 noc_clk (NIU to cluster return path)
  └─ T_l1_write:         1 noc_clk (L1 SRAM write completion)
```

**Typical total**: 100–150+ cycles (depends on DRAM and NoC routing)

### 6.3 Stream Capacity

**Simultaneous streams**: 8 independent streams per cluster

**Max total bandwidth with all 8 active**: 
- Limited by NIU AXI port bandwidth and DRAM controller (shared bottleneck)
- Individual stream execution is strictly sequential at the DRAM level

---

## Section 7: Integration with Other Components

### 7.1 TRISC Interface

**All 4 TRISC threads**:
- Can initiate overlay stream commands via CSR writes
- Can read stream status registers
- Cannot interrupt overlay DMA execution (hardware autonomous)

**Per-thread roles**:
- **TRISC0 (Pack)**: Reads computed results from L1 for output formatting
- **TRISC1 (Unpack)**: Initiates overlay reads to pre-load activation tensors into L1
- **TRISC2 (Math)**: Initiates overlay reads for weight tiles; controlled by MOP sequencer
- **TRISC3 (Tile Mgmt)**: Initiates overlay commands for residual data movement, KV-cache updates, output storage

### 7.2 FPU Integration

**No direct FPU-to-overlay coupling**: FPU and overlay are independent
- FPU works on data in SRCA/SRCB (fed by unpack engine via L1)
- Overlay fills L1 while FPU drains SRCA (pipelined, decoupled)
- DEST register file acts as intermediate buffer (FPU write, pack engine read)

### 7.3 NoC Integration

**Flit injection port**: Overlay stream controller → NoC mesh
- 512-bit flit (header + payload)
- Destination: Composite NIU (Y=3) or standalone NIU (Y=4)

**Dynamic vs static routing**:
- Overlay can use DOR (Dimension-Order Routing) or dynamic routing
- Dynamic routing carries 928-bit carried list per flit for multi-hop decisions

**Wormhole switching**: Flit-level flow control with credit-based VC (virtual channel) mechanism

### 7.4 NIU (NoC2AXI Bridge) Interface

**NIU endpoints per N1B0 grid** (Y=4 row, Y=3 composite row):
- X=0 (standalone): `NOC_XY_ADDR(0, 4)`
- X=1 (composite): `NOC_XY_ADDR(1, 3)`
- X=2 (composite): `NOC_XY_ADDR(2, 3)`
- X=3 (standalone): `NOC_XY_ADDR(3, 4)`

**ATT (Address Translation Table)**:
- 64 entries per NIU
- Maps NoC logical address → AXI physical address
- Programmed by Dispatch tile at kernel launch

### 7.5 SMN (System Management Network) Security

**8 independently programmable address ranges**:
- Allow/block/log actions
- Pre-ATT filter in NIU
- Violations assert `slv_ext_error` → CRIT interrupt

**Integration path**: Overlay error aggregator forwards SMN errors to Dispatch interrupt controller

### 7.6 EDC (Error Detection & Correction) Ring

**Overlay participation**:
- One EDC node per Tensix cluster (in OVL segment)
- EDC interrupts routed through overlay error aggregator
- FATAL/CRIT severity escalation to Dispatch

**Ring traversal**:
- Within each Tensix: NOC flit node → OVL node → L1 bank nodes (per SRAM)
- EDC forward and loopback chains pass through overlay wrapper

---

## Section 8: Power Management and DFX

### 8.1 Clock Gating

**Overlay-specific gating**:
- `overlay_wrapper_dfx` gates `dm_clk` to overlay data-move logic
- Gates both ai_clk and dm_clk via DFX wrapper (conditional on tile activity)

**Effect when gated**:
- All overlay stream DMA halts (no NoC injection)
- L1/L2 cache control logic suspended
- Context-switch SRAMs retain state (no power-off, just clock gating)

### 8.2 Reset Architecture

**Reset synchronization**:
- `i_aiclk_reset_n` (primary reset for TRISC and overlay CSR logic)
- `i_nocclk_reset_n_sync` (NoC domain reset, synchronized)
- Per-column `i_dm_clk_reset_n` (overlay data-move reset)

**Reset sequence**: Upstream tiles (Dispatch, NIU) before downstream (Tensix compute)

### 8.3 DFX Wrappers in Overlay Path

**DFX-wrapped modules**:
1. **overlay_wrapper_dfx**: Clock pass-through for overlay data-move logic
   - Surrounds `neo_overlay_wrapper` CDC FIFOs
   - Gates `dm_clk` to L1/L2 cache control
   
2. **instrn_engine_wrapper_dfx**: Clock pass-through for TRISC cores
   - Allows independent gating of ai_clk to instruction engines
   - L1 remains accessible for DMA even when instruction engines gated

**Scan chain integration**: DFX wrappers thread through overlay CDC FIFOs and context-switch logic

---

## Section 9: RTL File Locations and Key Parameters

### 9.1 Core Overlay RTL Files

**File paths** (as of 20260221):
```
/secure_data_from_tt/20260221/tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv
/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_instrn_engine.sv
```

**Related files**:
- `tt_overlay_pkg.sv` — Package definitions (NUM_CLUSTER_CPUS, NUM_SMN_INTERRUPTS, etc.)
- `tt_overlay_tensix_cfg_pkg.sv` — Tensix-specific overlay configuration
- `tt_trisc.sv` — TRISC core (one per thread)
- `tt_risc_wrapper.sv` — TRISC3 RV32I wrapper
- `tt_t6_local_regs_pkg.sv` — Local register interface definitions

### 9.2 Key RTL Parameters

**In `tt_instrn_engine.sv`**:
```
THREAD_COUNT = 4                              // TRISC0–3
TRISC_IRAM_ENABLE = 4'b0000                  // Shared L1 IMEM
TRISC_VECTOR_ENABLE = 4'b0001                // TRISC0 has vector extension
TRISC_FP_ENABLE = 4'b1111                    // All TRISCs have FP
MAX_TENSIX_DATA_RD_OUTSTANDING = 4           // In-flight read limit (8 in large mode)
MAX_L1_REQ = 16                              // Outstanding L1 requests (32 in large)
INSN_REQ_FIFO_DEPTH = 8                      // Instruction fetch FIFO (16 in large)
NOC_CONTROL = 0                              // All TRISCs (no direct NoC port)
```

**In overlay wrapper port list** (lines 42–150+):
```
i_core_clk, i_aiclk, i_nocclk, i_ref_clk    // Clock inputs
i_core_clk_reset_n_pre_sync                  // Reset per CPU
i_uncore_reset_n_pre_sync                    // Uncore reset
i_noc_clk_reset_n_sync                       // NoC reset
i_mem_config                                 // Memory configuration
o_core_clk_gated                             // Gated clock output
o_noc_clk_en                                 // NoC clock enable
o_smn_ai_clk_reset_n                         // SMN ai_clk reset
o_smn_tensix_risc_reset_n[WIDTH]             // Per-TRISC resets
```

### 9.3 Memory Configuration

**Overlay L1 D-Cache**:
- Data: 128×144 bits × 16 macros per tile
- Tag: 32×100 bits × 8 macros per tile
- Macro type: `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_128x144m2b1c1` (data), `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_32x100m2b1c1` (tag)
- Clock: `dm_clk` (data-move clock)

**Overlay L1 I-Cache**:
- Data: 128×144 bits × 16 macros per tile
- Tag: 32×100 bits × 8 macros per tile
- Clock: `dm_clk`

**Overlay L2 Cache**:
- Data + Director: 20 macros per tile
- Clock: `dm_clk`

**Context Switch SRAM**:
- 2 macros per tile
- Clock: `dm_clk`

**Total overlay memory**: ~840 dm_clk SRAM macros across 14 tiles (Tensix + Dispatch)

---

## Section 10: Alternative DRAM Access Paths

### 10.1 Dispatch iDMA Engine (vs Overlay Streams)

**Use case**: Bulk weight loading before kernel execution

**Advantages of iDMA**:
- 8 concurrent DMA CPU channels per Dispatch (16 total per chip)
- Hardware multi-dimensional address generation (no firmware loop)
- NoC multicast (same weight broadcast to multiple clusters)
- No overlay stream CSR overhead

**Overlay stream use case**: Residual data movement during kernel execution
- Output activation storage
- KV-cache updates
- Dynamic tensor loading

### 10.2 Composite vs Standalone NIU Addressing

**Critical constraint**: Y-coordinate differs between composite and standalone

| Tile Type | X | Y | CSR Encoding |
|-----------|---|---|---|
| Standalone NIU | 0 | 4 | `NOC_XY_ADDR(0, 4, ...)` |
| Standalone NIU | 3 | 4 | `NOC_XY_ADDR(3, 4, ...)` |
| Composite NIU | 1 | 3 | `NOC_XY_ADDR(1, 3, ...)` ← router row |
| Composite NIU | 2 | 3 | `NOC_XY_ADDR(2, 3, ...)` ← router row |

**Reason**: Composite module reports `nodeid_y = Y−1` (router row), not the NIU's physical Y=4 position

**Firmware consequence**: Using Y=4 for composite (X=1 or X=2) causes packets to be dropped or misrouted

---

## Section 11: Limitations and Constraints

### 11.1 No Direct TRISC-to-DRAM Load

**Constraint**: "A TRISC cannot read DRAM data directly into its LDM via a single `lw` instruction"

**Required mechanism**:
1. TRISC writes overlay stream CSR (initiate DRAM read)
2. Overlay DMA executes (DRAM → NoC → L1 side channel)
3. TRISC reads from L1 (L1 → TRISC via 128-bit port)
4. TRISC processes data in LDM

**Implication**: Adds minimum 100+ cycle latency before data is usable

### 11.2 Max AXI Burst Size

**Hardware limit**: 256 beats × 64 bytes = **16 KB per burst**

**Workaround**: Firmware must split larger transfers across multiple overlay stream commands
- Example: 32 KB transfer → 2 × 16 KB bursts on different streams

### 11.3 Outstanding Request Limit

**Constraint**: `MAX_TENSIX_DATA_RD_OUTSTANDING = 4`

**Enforcement**: Firmware must check stream status before issuing 5th read

**Reason**: Prevents NIU RDATA FIFO overflow (512 entries = 32 KB)

### 11.4 No DMA Priority or QoS

**Current design**: Overlay streams are best-effort
- No priority levels
- No bandwidth reservation
- All 8 streams share the same NIU port
- DRAM contention with iDMA and other tiles

---

## Section 12: Recommended §3 Chapter Structure

### Proposed outline for comprehensive §3 Overlay Engine chapter:

```
§3 Overlay Engine — Data Movement Orchestration
├─ 3.1 Overview
│   ├─ Role and purpose
│   ├─ Container module (tt_neo_overlay_wrapper)
│   └─ Key subsystems
├─ 3.2 Hardware Components
│   ├─ Overlay stream controller
│   ├─ TDMA engine (pack/unpack)
│   ├─ MOP sequencer
│   ├─ Stream status registers
│   └─ Context switch logic
├─ 3.3 Data Paths and NoC Integration
│   ├─ Complete DRAM access path
│   ├─ Port specifications
│   ├─ Clock domain crossings
│   ├─ L1 partition integration
│   └─ Composite vs standalone NIU addressing
├─ 3.4 Stream Programming Model
│   ├─ CSR register architecture
│   ├─ Burst length calculation
│   ├─ Stream status polling
│   └─ Outstanding request limits
├─ 3.5 Context Switching
│   ├─ Context switch SRAM
│   ├─ Partition control signals
│   └─ L1/L2 cache orchestration
├─ 3.6 Performance Characteristics
│   ├─ Achievable data rates
│   ├─ Latency components
│   └─ Stream capacity
├─ 3.7 Integration with Other Components
│   ├─ TRISC interface
│   ├─ FPU integration
│   ├─ NoC integration
│   ├─ NIU interface
│   ├─ SMN security
│   └─ EDC ring integration
├─ 3.8 Power Management and DFX
│   ├─ Clock gating strategy
│   ├─ Reset architecture
│   └─ DFX wrapper integration
└─ 3.9 RTL File Locations and Parameters
    ├─ Core RTL files
    ├─ Key parameters
    ├─ Memory configuration
    └─ Register map pointers
```

---

## Section 13: Key Facts Summary

### Essential numbers:
- **8 overlay streams** per cluster
- **512-bit flit width** (64 bytes per beat)
- **16 KB max AXI burst** (256 beats)
- **4 outstanding read requests** max (8 in large mode)
- **3 MB L1 capacity** per cluster
- **512 SRAM macros** per L1 partition
- **32 KB RDATA FIFO** in NIU (512 entries)
- **4 TRISC threads** (TRISC0=pack, TRISC1=unpack, TRISC2=math, TRISC3=mgmt)
- **256 FP-Lanes** per Tensix (2 G-Tiles × 128 FP-Lanes each)
- **8 MOPs per cycle max** from MOP sequencer (TRISC2 to FPU)

### Essential clock domains:
- **ai_clk** — TRISC, FPU, instruction engines
- **dm_clk** — Overlay data-move, L1/L2 SRAM, pack/unpack engines
- **noc_clk** — NoC router, flit FIFOs, overlay stream injection

### Essential RTL modules:
- `tt_neo_overlay_wrapper` — Container for all overlay logic
- `tt_instrn_engine` — MOP sequencer, TDMA coordination
- `tt_trisc` — TRISC0/1/2 cores (one per thread)
- `tt_risc_wrapper` — TRISC3 RV32I core
- `tt_noc2axi` — NIU (in composite tile)
- `tt_t6_l1_partition` — L1 cache hierarchy

---

## Section 14: References and Cross-Links

**Primary HDD document**:
- N1B0_NPU_HDD_v0.99.md (sections 2.2.4, 2.3.6, 3.7.6, 8.7.4, 8.7.5)

**Related sections within HDD**:
- §2.1 — FPU hierarchy (TRISC2 → MOP → FPU path)
- §2.2 — TRISC3 management core
- §2.3 — TRISC cores and access matrix
- §2.7 — MOP format and sequencing
- §3 — NOC2AXI composite tiles (NIU interface)
- §4 — Dispatch iDMA engine (alternative DRAM access)
- §5 — Harvest (power domain/reset isolation through overlay)
- §8.7 — DFX wrappers (overlay_wrapper_dfx, instrn_engine_wrapper_dfx)

**RTL sources**:
- `/secure_data_from_tt/20260221/tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv`
- `/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_instrn_engine.sv`
- `tt_overlay_pkg.sv`, `tt_overlay_tensix_cfg_pkg.sv`
- `tt_trisc.sv`, `tt_risc_wrapper.sv`

---

## Section 15: Notes for HDD Author

### Suggested diagrams to include:

1. **Overlay stream command flow** (CSR write → NoC injection → NIU → AXI → DRAM)
2. **TRISC synchronization and pack/unpack/math pipelines** (semaphore-driven handoff)
3. **L1 access paths** (TRISC 128-bit bus, NoC side-channel 512-bit, pack/unpack TDMA)
4. **Clock domain diagram** (ai_clk, dm_clk, noc_clk with CDC FIFO bridges)
5. **NIU addressing table** (composite vs standalone Y coordinate difference)
6. **Burst length encoding** (ARLEN = (bytes/64)−1, with examples)
7. **Stream status lifecycle** (issued, in-flight, complete, error)
8. **Context switch state management** (save on kernel done, restore on kernel launch)

### Suggested RTL code snippets to highlight:

1. CSR register write encoding (32-bit address, size, direction fields)
2. Stream status polling pattern (firmware loop waiting for completion)
3. MOP sequencer state machine (IDLE → LOOP_START → IN_LOOP → LOOP_END → FINAL_END)
4. TRISC synchronization semaphore pattern (SEMGET/SEMPOST between threads)
5. NoC destination coordinate encoding `NOC_XY_ADDR(x, y, local_addr)`

### Verification coverage notes:

- Overlay stream CSR interface verified in firmware tests (§6 firmware suite)
- DRAM path verified end-to-end in addr_pinger test
- CDC FIFO synchronization verified in integration simulation
- Stream status polling latency characterized (100–150+ cycles typical)
- Context switch SRAM retention verified across reset

---

END OF EXTRACTION FINDINGS

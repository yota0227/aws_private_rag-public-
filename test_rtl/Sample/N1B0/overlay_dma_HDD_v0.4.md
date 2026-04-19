# Trinity N1B0 — Overlay DMA & RISC-V CPU Engine HDD

## Version Table

| Version | Date       | Author        | Changes                                                                                 |
|---------|------------|---------------|-----------------------------------------------------------------------------------------|
| v0.1    | 2026-03-24 | HW/SW Team    | Initial release                                                                         |
| v0.2    | 2026-03-24 | HW/SW Team    | Added §7 RISC-V CPU SW Guide; §8.1 initialization; §8.13 DMA+TDMA pipeline             |
| v0.3    | 2026-03-24 | HW/SW Team    | Added §8.14 multi-tile coordination; §8.15 error recovery; §10 debug guide             |
| v0.4    | 2026-03-24 | HW/SW Team    | Added §9 performance expanded; §13 Appendix C address map; §14 Appendix D SW driver template; editorial improvements throughout |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Feature Summary](#2-feature-summary)
3. [Architecture Overview](#3-architecture-overview)
   - 3.1 System Context
   - 3.2 iDMA Engine Internal Architecture
   - 3.3 Data Flow Overview
4. [Module Descriptions](#4-module-descriptions)
   - 4.1 tt_idma_wrapper
   - 4.2 tt_idma_cmd_buffer_frontend
   - 4.3 tt_idma_backend_r_init_rw_obi_top
   - 4.4 tt_idma_legalizer_r_init_rw_obi
   - 4.5 tt_idma_transport_layer
   - 4.6 tt_idma_dfc_wrapper
   - 4.7 tt_clk_gater
   - 4.8 Note on TDMA
5. [Key Parameters](#5-key-parameters)
6. [SFR Reference](#6-sfr-reference)
   - 6.1 Cluster Control Registers (cluster_ctrl_apb)
   - 6.2 iDMA APB Registers
   - 6.3 ATT
7. [RISC-V CPU — SW Guide](#7-risc-v-cpu--sw-guide)
   - 7.1 Hart Architecture Summary
   - 7.2 Boot Sequence and Reset Vector Setup
   - 7.3 Per-Hart Stack Layout and Memory Map
   - 7.4 PLIC — Platform-Level Interrupt Controller
   - 7.5 CLINT — Core-Local Interruptor
   - 7.6 Fence and Memory Ordering with DMA
   - 7.7 ROCC Custom Instruction Interface
   - 7.8 Context Switch Considerations
   - 7.9 Multi-Hart Coordination Patterns
8. [DMA Programming Guide](#8-dma-programming-guide)
   - 8.1 Initialization Sequence
   - 8.2 Basic 1D Transfer (L1-to-L1)
   - 8.3 DMA from DRAM to L1
   - 8.4 2D Scatter-Gather Transfer
   - 8.5 Tile-Based vs Non-Tile-Based Access
   - 8.6 Address Translation using ATT
   - 8.7 Data Format Conversion During Transfer (DFC)
   - 8.8 L1 Accumulate (Zero-Copy Partial Sum)
   - 8.9 Zero-Copy Memory Patterns
   - 8.10 Multi-Client Pipelining
   - 8.11 Sparsity and Zero Handling
   - 8.12 Completion Tracking and IRQ
   - 8.13 DMA + TDMA Pipeline (Overlap Compute and Data Load)
   - 8.14 Multi-Tile DMA Coordination
   - 8.15 Error Detection and Recovery
9. [Performance Guide](#9-performance-guide)
   - 9.1 Clock Gating Configuration
   - 9.2 In-Flight Transaction Depth
   - 9.3 Backend Selection
   - 9.4 2D Transfer Efficiency
   - 9.5 L1 Bandwidth Estimation
   - 9.6 DRAM Throughput Optimization
   - 9.7 Latency-Hiding Patterns
10. [Debugging Guide](#10-debugging-guide)
    - 10.1 DMA Stall Diagnosis
    - 10.2 Data Corruption Checklist
    - 10.3 IRQ Not Firing
    - 10.4 Clock Gating Issues
    - 10.5 Bus Error Handling
    - 10.6 RISC-V Hart Debug
11. [Appendix A: DFC Format Table](#11-appendix-a-dfc-format-table)
12. [Appendix B: RISC-V iDMA Instruction Reference](#12-appendix-b-risc-v-idma-instruction-reference)
13. [Appendix C: Address Map Quick Reference](#13-appendix-c-address-map-quick-reference)
14. [Appendix D: SW Driver Template](#14-appendix-d-sw-driver-template)

---

## 1. Overview

The Trinity N1B0 chip contains a 4×5 mesh of tiles. Each Tensix tile (columns X=0–3, rows Y=1–4) includes a per-tile **iDMA engine** (`tt_idma_wrapper`) instantiated inside `tt_overlay_wrapper`. The iDMA engine provides a general-purpose, software-programmable DMA facility that moves data between:

- Local L1 SRAM (within the same tile)
- Remote L1 SRAM (in another tile, via the NoC)
- External DRAM (DDR, via the NOC2AXI bridge at Y=0)

The iDMA engine is distinct from the **TDMA** (Tensor DMA) that lives inside the Tensix compute core. While TDMA is tightly coupled to the FPU datapath and handles tensor tiling, zero-masking, and tilize/untilize operations, iDMA is a standalone AXI/OBI DMA engine visible to the CPU harts and the Dispatch Engine. iDMA is the correct engine to use for bulk data ingestion (e.g., copying weight buffers from DRAM to L1) and for non-tensor memory operations.

**Scope of this document:** iDMA architecture, registers, SW programming guide, RISC-V CPU hart guide, performance optimization, and debugging. TDMA is described in the Tensix Core HDD.

**Target audience:** SW engineers writing firmware, runtime libraries, or device drivers that control the iDMA engine and RISC-V CPU complex on Trinity N1B0.

---

## 2. Feature Summary

| # | Feature | Details |
|---|---------|---------|
| 1 | 2D scatter-gather DMA | Outer stride loop (num_reps × length bytes per rep) with independent src/dst strides |
| 2 | 24 independent input clients | 8 CPU harts (ROCC) + 2 Dispatch Engine ports + 14 reserved |
| 3 | Dual backends | 2 parallel backends for concurrent transfers |
| 4 | OBI backend (default) | Local L1 SRAM access via OBI protocol |
| 5 | AXI backend (compile-time) | DRAM access via NOC2AXI AXI4 master |
| 6 | Data Format Conversion (DFC) | In-flight format conversion (FP32/FP16/BF16/TF32/FP8/MX*/INT*) |
| 7 | L1 atomic accumulate | 16 accumulate channels; iDMA can write-accumulate into L1 accumulate registers |
| 8 | 32 transaction IDs (TIDs) | Per-TID in-flight tracking, threshold-based IRQ, software-clearable |
| 9 | Page-aligned burst splitting | Legalizer splits transfers at 4KB (configurable) page boundaries |
| 10 | INIT / zero-fill path | Zero-fill destination without reading source |
| 11 | Decoupled read/write | Read and write phases can proceed independently for throughput |
| 12 | Serialized mode | Force in-order execution when ordering is required |
| 13 | Weighted round-robin arbitration | Per-VC weighted arbiter across 24 clients |
| 14 | Clock gating with hysteresis | 7-bit hysteresis counter; gated_l1_clk auto-extends during activity |
| 15 | RISC-V ROCC instruction interface | Custom instructions DMSRC/DMDST/DMCPY/DMSTR/DMREP/DMSTAT from harts |
| 16 | APB register access | All status/config registers accessible via APB from the CPU complex |
| 17 | Virtual channel (VC) selection | Per-transfer VC selector passed through to NoC packet header |
| 18 | CDC-safe frontend/backend boundary | Async FIFO between core_clk (frontend) and gated_l1_clk (backend) |

**NOT in iDMA (see TDMA section):** zero-mask skipping (zmask), exponent-based sparsity pruning, edge masking, tilize/untilize, thread-parallel pack/unpack, BFP hardware decompression, ReLU packing.

---

## 3. Architecture Overview

### 3.1 System Context

```
                        Trinity N1B0 Tile (X=0..3, Y=1..4)
  +--------------------------------------------------------------+
  |  tt_overlay_wrapper                                          |
  |                                                              |
  |  +--------------+   +----------------------------------+     |
  |  |  CPU Complex  |   |       tt_idma_wrapper            |     |
  |  |  (8 harts)    +-->+  iDMA Engine                     |     |
  |  |  ROCC CUSTOM_1|   |                                  |     |
  |  +--------------+   +----------+------------+----------+     |
  |                                | OBI        | AXI            |
  |  +--------------+              v            v                |
  |  |  Dispatch    |   +----------+--+  +------+------+        |
  |  |  Engine      +-->+  L1 SRAM    |  |  NOC2AXI    +-->DRAM |
  |  +--------------+   |  (768 KB)   |  |  Bridge     |        |
  |                     +-------------+  +-------------+        |
  |                            |                                  |
  |                     +-------------+                          |
  |                     |  NoC Router +<------ Remote tiles      |
  |                     +-------------+                          |
  +--------------------------------------------------------------+
```

The iDMA engine sits inside the overlay and is logically adjacent to the L1 SRAM and the NoC fabric. It is not part of the Tensix compute core. CPU harts issue DMA commands via ROCC custom instructions; the Dispatch Engine may also issue DMA via sideband ports (clients 8–9).

### 3.2 iDMA Engine Internal Architecture

```
  +--------------------------------------------------------------------------+
  |  tt_idma_wrapper                                                         |
  |                                                                          |
  |  core_clk domain                   |  gated_l1_clk domain               |
  |                                    |                                     |
  |  +------------------------------+  |  +--------------------------------+ |
  |  | tt_idma_cmd_buffer_frontend  |  |  | tt_idma_backend_r_init_rw_     | |
  |  |                              |  |  | obi_top  [BE #0]               | |
  |  |  clients[0..23]              |  |  |                                | |
  |  |  +--------------------+      |  |  |  +------------------------+   | |
  |  |  | timing slice regs  |      |  |  |  | metadata FIFO (dep=28) |   | |
  |  |  | (per client)       |      |  |  |  +------------------------+   | |
  |  |  +--------------------+      |  |  |  +------------------------+   | |
  |  |  +--------------------+      |  |  |  | tt_idma_backend_r_init |   | |
  |  |  | tt_arb (WRR/VC)    |      |  |  |  | _rw_obi (xIDMA_NUM_BE) |   | |
  |  |  +--------------------+      |  |  |  |  +-----------------+   |   | |
  |  |  +--------------------+      |  |  |  |  | Legalizer       |   |   | |
  |  |  | tt_sync_fifo       |      |  |  |  |  | (page align,    |   |   | |
  |  |  | metadata depth=42  |      |  |  |  |  |  burst split)   |   |   | |
  |  |  +--------------------+      |  |  |  |  +-----------------+   |   | |
  |  |  +--------------------+      |  |  |  |  +-----------------+   |   | |
  |  |  | async payload buf  +<-----+--+  |  |  | Transport Layer |   |   | |
  |  |  | depth=8, CDC FIFO  |      |  |  |  |  |  obi_read       |   |   | |
  |  |  +--------------------+      |  |  |  |  |  init_read      |   |   | |
  |  |  +--------------------+      |  |  |  |  |  obi_write      |   |   | |
  |  |  | TID completion     |      |  |  |  |  |  dfc_wrapper    |   |   | |
  |  |  | threshold / IRQ    |      |  |  |  |  +-----------------+   |   | |
  |  |  +--------------------+      |  |  |  +------------------------+   | |
  |  +------------------------------+  |  +--------------------------------+ |
  |                                    |                                     |
  |                                    |  +--------------------------------+ |
  |                                    |  | tt_idma_backend_r_init_rw_     | |
  |                                    |  | obi_top  [BE #1]               | |
  |                                    |  +--------------------------------+ |
  |                                    |                                     |
  |  i_l1_clk --> tt_clk_gater ---------------------------> gated_l1_clk   |
  |               (HYST_WIDTH=7)       |                                     |
  +--------------------------------------------------------------------------+
```

### 3.3 Data Flow Overview

**Read path (DRAM to L1):**
```
  CPU hart (ROCC CUSTOM_1)
       |  DMSRC/DMDST/DMCPY instructions
       v
  tt_idma_cmd_buffer_frontend
  [core_clk: timing slice -> WRR arbiter -> metadata FIFO(42) -> async payload FIFO(8)]
       |  CDC crossing: core_clk -> gated_l1_clk
       v
  tt_idma_backend_r_init_rw_obi_top
  [gated_l1_clk: metadata FIFO(28) -> legalizer -> transport layer]
       |
       +--[AXI backend]--> NOC2AXI --> NoC --> DRAM (SI0-SI3)
       |                        read data <------
       +--[OBI backend]--> L1 SRAM OBI port
             |  write data --> L1 SRAM write port
             |  (optional: L1 accumulate channels 0-15)
             v
         L1 SRAM (768 KB per tile in N1B0)
```

**Write path (L1 to Remote tile or DRAM):**
```
  tt_idma_backend transport layer
       |
       +-- OBI read --> local L1 SRAM (source data)
       +-- OBI/AXI write --> NoC PUT --> remote tile L1
                           +-- AXI AW/W --> NOC2AXI --> DRAM
```

---

## 4. Module Descriptions

### 4.1 tt_idma_wrapper (Top-level)

**File:** `used_in_n1/tt_idma_wrapper.sv`

**Function:** Top-level DMA engine instantiated once per Tensix tile (Y=1–4) inside `tt_overlay_wrapper`. Instantiates the frontend, two backends, and the clock gate. Manages CDC boundary between `core_clk` and `gated_l1_clk`.

**Key ports:**

| Port | Direction | Domain | Description |
|------|-----------|--------|-------------|
| `i_core_clk` | in | core_clk | CPU complex clock |
| `i_l1_clk` | in | noc_clk | L1 SRAM clock (ungated) |
| `gated_l1_clk` | internal | — | Clock gated by tt_clk_gater |
| `i_core_rst_n` | in | — | Active-low reset (core domain) |
| `i_l1_rst_n` | in | — | Active-low reset (L1 domain) |
| `i_idma_req[23:0]` | in | core_clk | idma_flit_t from 24 clients |
| `o_idma_ready[23:0]` | out | core_clk | Back-pressure per client |
| `o_idma_tiles_to_process_irq[31:0]` | out | core_clk | Per-TID IRQ outputs |
| `i_tiles_to_process_clear[31:0]` | in | core_clk | Write 1 to clear IRQ + count |
| `i_l1_clkgt_en` | in | core_clk | Clock gate enable from CLOCK_GATING.IDMA |
| `i_l1_clkgt_hyst` | in | core_clk | Hysteresis count (7-bit) |

**Compile-time parameter:** `IDMA_BE_TYPE_AXI` selects OBI (0, default) or AXI (1) backend.

---

### 4.2 tt_idma_cmd_buffer_frontend (Frontend)

**Function:** Receives DMA descriptors from up to 24 clients, arbitrates using weighted round-robin per virtual channel (VC), buffers metadata and payload through a CDC boundary, and tracks completion per transaction ID (TID).

**Sub-components:**

| Sub-module | Depth / Size | Function |
|------------|-------------|---------|
| Timing slice registers | 1 per client | Pipeline register for timing closure |
| `tt_arb` (WRR) | 24-input | Weighted round-robin arbiter, per-VC |
| `tt_sync_fifo` (metadata) | 42 entries | Holds descriptor metadata in core_clk domain |
| Async payload FIFO | 8 entries | CDC FIFO: core_clk to gated_l1_clk |
| TID completion tracker | 32 TIDs | Counts completions, compares to threshold, fires IRQ |

**Client assignment:**

| Client Index | Source | Notes |
|-------------|--------|-------|
| 0–7 | CPU harts 0–7 | Via ROCC CUSTOM_1 interface |
| 8–9 | Dispatch Engine sideband | DE-initiated tile-wide operations |
| 10–23 | Reserved | Future use |

**TID / IRQ mechanism:**

Each `idma_flit_t` carries a 5-bit `trid` field (TID 0–31). The frontend increments a per-TID counter each time a transfer with that TID completes. When the counter reaches `i_tr_id_thresholds[TID]`, the corresponding bit in `o_idma_tiles_to_process_irq[TID]` is asserted. SW writes 1 to `i_tiles_to_process_clear[TID]` to atomically clear the counter and the IRQ bit.

**Descriptor format (`idma_flit_t`):**
```
  [MSB .......................................................... LSB]
  | l1_accum_cfg_reg (L1 accumulate config) | trid[4:0] | vc[1:0] | payload |
```

where `payload` (`idma_req_t`) contains:
```
  src_addr[63:0]   -- source byte address
  dst_addr[63:0]   -- destination byte address
  length[21:0]     -- transfer size in bytes (max 4 MB)
  src_stride[63:0] -- outer dimension source stride (2D mode)
  dst_stride[63:0] -- outer dimension destination stride (2D mode)
  num_reps[63:0]   -- outer loop count (1 = 1D transfer)
  decouple_rw      -- decouple read and write phases
  deburst          -- disable AXI burst mode
  serialize        -- force in-order serialization
```

---

### 4.3 tt_idma_backend_r_init_rw_obi_top (OBI Backend)

**Function:** Receives arbitrated descriptors from the frontend (in `gated_l1_clk` domain), manages per-backend metadata FIFOs, and instantiates `IDMA_NUM_BE` backend instances that drive OBI or AXI protocol towards L1 SRAM.

Two backend top instances run in parallel (BE #0 and BE #1), allowing two concurrent independent transfers.

**Sub-components:**

| Sub-module | Depth | Function |
|------------|-------|---------|
| Metadata FIFO | 28 entries | Holds L1 accumulate config and in-flight metadata |
| `tt_idma_backend_r_init_rw_obi` | xIDMA_NUM_BE | Per-backend legalizer + transport layer |

**AXI variant:** When `IDMA_BE_TYPE_AXI == 1`, `tt_idma_backend_r_init_rw_axi_top` is instantiated instead, which interfaces to the tile's AXI master port and ultimately reaches DRAM via the NOC2AXI bridge at Y=0.

---

### 4.4 tt_idma_legalizer_r_init_rw_obi (Legalizer)

**Function:** Transforms an arbitrary `idma_req_t` descriptor into a sequence of legal bus transactions that respect protocol constraints.

**Responsibilities:**

1. **Page boundary detection:** Splits transfers that cross 4KB boundaries into multiple sub-transfers. This prevents a single burst from spanning pages that may be non-contiguous in physical memory.

2. **Burst alignment:** Aligns source and destination addresses to the AXI/OBI burst word size. Generates byte-enable masks for partial-word accesses at start and end of a transfer.

3. **INIT path handling:** When zero-fill mode is requested (no source address, destination fill), generates synthetic read data (all zeros) without issuing source reads.

4. **DFC scale accounting:** When Data Format Conversion is enabled, adjusts transfer byte counts to account for format up-sizing (e.g., INT8 to FP32 = x4) or down-sizing (e.g., FP32 to FP8 = /4).

5. **2D outer loop:** Generates `num_reps` sequential inner transfers, advancing source and destination addresses by `src_stride` and `dst_stride` respectively after each inner transfer of `length` bytes.

---

### 4.5 tt_idma_transport_layer (Transport Layer)

**Function:** Executes the legalized transfer sequence by driving OBI (or AXI) read and write channels.

**Sub-modules:**

| Module | Function |
|--------|---------|
| `idma_obi_read` | Issues OBI read requests to L1 SRAM (source path) |
| `idma_init_read` | Generates synthetic zero data (INIT/zero-fill path) |
| `idma_obi_write` | Issues OBI write requests to L1 SRAM (destination path) |
| `tt_idma_dfc_wrapper` | Optional: in-flight data format conversion (when DFCEnable=1) |

**Decoupled read/write:** When `decouple_rw=1`, the read channel and write channel operate independently. The read channel can prefetch ahead of the write channel, improving throughput when the two channels have different latencies (e.g., DRAM read + local L1 write). When `decouple_rw=0`, the write does not proceed until read data is available, preserving strict ordering.

**L1 accumulate path:** When `l1_accum_cfg_reg.enable=1`, the OBI write is redirected to the L1 atomic accumulate channel (0–15) rather than writing directly to the SRAM data array. This implements zero-copy in-place accumulation.

---

### 4.6 tt_idma_dfc_wrapper (Data Format Converter)

**Function:** Inserted in the transport layer data path when `DFCEnable=1`. Converts data between source format and destination format during transfer, without requiring the CPU to perform format conversion in software.

**Converter:** `tt_t6_com_elem_to_mx_convert_idma`

**Configuration:**
- `WORD_WIDTH = 8` bits (element granularity)
- `MX_BLOCK_SIZE = 8` elements per microscaling block
- Source format and destination format are specified per-transfer via the DFC config field in the descriptor
- Stochastic rounding is supported for narrowing conversions (e.g., FP32 to FP8)

**Supported format pairs:** Any combination from the 17-format table in Appendix A. Common useful conversions:

| Source | Destination | Use Case |
|--------|-------------|---------|
| FLOAT32 | FLOAT16_B | FP32 parameter to BF16 L1 storage |
| FLOAT32 | FP8P | FP32 to FP8 E4M3 for compressed storage |
| INT16 | INT8 | 16-bit activation to 8-bit L1 storage |
| MXFP8R | FLOAT16 | Decompress MX format to FP16 |

NOTE: DFC in iDMA is a bulk memory conversion. It does NOT perform any arithmetic (no scaling by bias, no normalization). For per-channel scale/bias operations, use the TDMA descale path or SFPU.

**What iDMA DFC does NOT do:**
- Sparsity pruning (zero-skipping) — see TDMA zmask
- Tilize/untilize (row-major to tile layout) — see TDMA
- ReLU application — see TDMA packer

---

### 4.7 tt_clk_gater (Clock Gate)

**Function:** Controls the `gated_l1_clk` that clocks the two backend instances. Saves power when no DMA transfers are active.

**Architecture:**
```
  i_l1_clk ----------------------------------------> tt_clk_gater
                                                            |
  i_enable ---- CLOCK_GATING.IDMA bit (APB 0x0CC[1]) ----->|
  i_kick   ---- |{req_valid, resp_valid} from backends ---->|
  i_busy   ---- o_l1_clkgt_busy from backends ------------->|
  i_histeresys - i_l1_clkgt_hyst[6:0] (APB 0x0D0) -------->|
                                                            |
                                                 gated_l1_clk --> backends
```

**Behavior:**
- Clock is gated OFF when: `i_enable=1` AND `i_kick=0` AND `i_busy=0` AND hysteresis counter expired
- Clock is forced ON when: `i_enable=0` (disable clock gating = clock always on)
- `i_kick` extends the active period for `2^HYST_WIDTH` cycles from the last activity
- `HYST_WIDTH=7` means clock stays on for up to 128 cycles after last activity

**Recommendation:** Set `CLOCK_GATING.IDMA=1` in production to save power. Set `CLOCK_GATING.IDMA=0` during bring-up and debug.

---

### 4.8 Note on TDMA (Tensor DMA — separate engine)

The **TDMA** is a different DMA engine inside the Tensix compute core, not part of `tt_idma_wrapper`. It is controlled via dedicated TDMA registers and is tightly coupled to the FPU pack/unpack path.

**TDMA capabilities NOT present in iDMA:**

| Feature | TDMA | iDMA |
|---------|------|------|
| Zero-mask skipping (zmask) | YES | NO |
| Exponent-based sparsity pruning | YES | NO |
| Edge masking (EDGE_MASK0–3) | YES | NO |
| Tilize (row-major to tile layout) | YES | NO |
| Untilize (tile to row-major) | YES | NO |
| 4 parallel pack/unpack threads | YES | NO |
| BFP 4:1 hardware decompression | YES | NO |
| ReLU in packer | YES | NO |
| 3D tensor access | YES | NO (2D max) |
| Decoupled read/write | NO | YES |
| 24-client arbitration | NO | YES |
| DRAM AXI access | NO | YES |

For bulk data movement from DRAM or between tiles, use iDMA. For tensor-format pack/unpack tightly integrated with FPU, use TDMA.

---

## 5. Key Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `IDMA_NUM_MEM_PORTS` | 2 | Number of memory ports (backends) |
| `IDMA_CMD_BUF_NUM_CLIENTS` | 24 | Total client slots (= IDMA_NUM_CLIENTS) |
| `IDMA_PACKET_TAG_TRANSACTION_ID_WIDTH` | 5 | TID field width -> 32 TIDs (0–31) |
| `IDMA_MEM_PORT_ID_WIDTH` | 4 | Memory port ID width |
| `IDMA_TRANSFER_LENGTH_WIDTH` | 22 | Transfer length field width -> 4 MB max |
| `IDMA_FIFO_DEPTH` | 42 | Frontend metadata FIFO depth |
| `IDMA_PAYLOAD_FIFO_DEPTH` | 8 | CDC async payload FIFO depth |
| `IDMA_L1_ACC_ATOMIC` | 16 | L1 accumulate channel count |
| `NumDim` | 2 | Maximum DMA dimensions (2D scatter-gather) |
| `IDMA_AXI_USER_WIDTH` | 1 | AXI USER sideband width |
| Backend metadata FIFO depth | 28 | Per-backend descriptor FIFO (gated_l1_clk domain) |
| `HYST_WIDTH` | 7 | Clock gate hysteresis counter width (128 cycles) |
| `reg_addr_t` | 9-bit | APB register address space -> 512 locations |
| `reg_data_t` | 32-bit | APB register data width |

---

## 6. SFR Reference (SW Register Map)

### 6.1 Cluster Control Registers (cluster_ctrl_apb)

**Base address:** `0x0300_0000`
**Size:** `0x1E4` bytes
**Access:** 64-bit aligned for RESET_VECTOR registers; 32-bit for all others

| Offset | Register Name | Reset | Access | Description |
|--------|---------------|-------|--------|-------------|
| 0x000 | RESET_VECTOR_0 | 0x0 | RW | Hart 0 reset vector bits [57:0] |
| 0x008 | RESET_VECTOR_1 | 0x0 | RW | Hart 1 reset vector bits [57:0] |
| 0x010 | RESET_VECTOR_2 | 0x0 | RW | Hart 2 reset vector bits [57:0] |
| 0x018 | RESET_VECTOR_3 | 0x0 | RW | Hart 3 reset vector bits [57:0] |
| 0x020 | RESET_VECTOR_4 | 0x0 | RW | Hart 4 reset vector bits [57:0] |
| 0x028 | RESET_VECTOR_5 | 0x0 | RW | Hart 5 reset vector bits [57:0] |
| 0x030 | RESET_VECTOR_6 | 0x0 | RW | Hart 6 reset vector bits [57:0] |
| 0x038 | RESET_VECTOR_7 | 0x0 | RW | Hart 7 reset vector bits [57:0] |
| 0x040 | SCRATCH_0 | 0x0 | RW | General-purpose scratch register 0 |
| 0x044 | SCRATCH_1 | 0x0 | RW | General-purpose scratch register 1 |
| ... | SCRATCH_2..30 | 0x0 | RW | General-purpose scratch registers |
| 0xBC | SCRATCH_31 | 0x0 | RW | General-purpose scratch register 31 |
| 0x0C0 | ROCC_MEM_CHICKEN | 0x0 | RW | ROCC memory chicken bits (debug overrides) |
| 0x0C4 | SCATTER_LIST_MAGIC_NUM_LO | 0x0 | RW | Scatter list magic number bits [31:0] |
| 0x0C8 | SCATTER_LIST_MAGIC_NUM_HI | 0x0 | RW | Scatter list magic number bits [63:32] |
| 0x0CC | CLOCK_GATING | 0x0 | RW | Per-unit clock gate enables |
| 0x0D0 | CLOCK_GATING_HYST | 0x0 | RW | Clock gate hysteresis count (7-bit, bits [6:0]) |
| 0x0D8 | WB_PC_REG_C0 | 0x0 | RO | Hart 0 writeback PC |
| 0x0E0 | WB_PC_REG_C1 | 0x0 | RO | Hart 1 writeback PC |
| 0x0E8 | WB_PC_REG_C2 | 0x0 | RO | Hart 2 writeback PC |
| 0x0F0 | WB_PC_REG_C3 | 0x0 | RO | Hart 3 writeback PC |
| 0x0F8 | WB_PC_REG_C4 | 0x0 | RO | Hart 4 writeback PC |
| 0x100 | WB_PC_REG_C5 | 0x0 | RO | Hart 5 writeback PC |
| 0x108 | WB_PC_REG_C6 | 0x0 | RO | Hart 6 writeback PC |
| 0x110 | WB_PC_REG_C7 | 0x0 | RO | Hart 7 writeback PC |
| 0x118 | WB_PC_CTRL | 0x0 | RW | Writeback PC capture control |
| 0x11C | ECC_PARITY_CONTROL | 0x0 | RW | Enable ECC/parity for L1 SRAM |
| 0x120 | ECC_PARITY_STATUS | 0x0 | RO/W1C | ECC/parity error status flags |
| 0x124 | NOC_SNOOP_TL_MASTER_CFG | 0x0 | RW | TileLink master config for NoC snoop path |
| 0x128 | ASSERTS | 0x0 | RW | Assertion enable bits (simulation/debug) |
| 0x12C | PREFETCHER_CONTROL | 0x0 | RW | Instruction cache prefetcher enable/config |
| 0x130 | BUS_ERROR_UNIT_DATA_C0 | 0x0 | RO/W1C | Bus error data for hart 0 |
| 0x138 | BUS_ERROR_UNIT_DATA_C1 | 0x0 | RO/W1C | Bus error data for hart 1 |
| 0x140 | BUS_ERROR_UNIT_DATA_C2 | 0x0 | RO/W1C | Bus error data for hart 2 |
| 0x148 | BUS_ERROR_UNIT_DATA_C3 | 0x0 | RO/W1C | Bus error data for hart 3 |
| 0x150 | BUS_ERROR_UNIT_DATA_C4 | 0x0 | RO/W1C | Bus error data for hart 4 |
| 0x158 | BUS_ERROR_UNIT_DATA_C5 | 0x0 | RO/W1C | Bus error data for hart 5 |
| 0x160 | BUS_ERROR_UNIT_DATA_C6 | 0x0 | RO/W1C | Bus error data for hart 6 |
| 0x168 | BUS_ERROR_UNIT_DATA_C7 | 0x0 | RO/W1C | Bus error data for hart 7 |
| 0x170 | L2_DIR_ERRORS_0 | 0x0 | RO | L2 directory error status (bank group 0) |
| 0x174 | L2_DIR_ERRORS_1 | 0x0 | RO | L2 directory error status (bank group 1) |
| 0x178 | L2_DIR_ERRORS_2 | 0x0 | RO | L2 directory error status (bank group 2) |
| 0x17C | L2_DIR_ERRORS_3 | 0x0 | RO | L2 directory error status (bank group 3) |
| 0x180 | L2_BANKS_ERRORS_0 | 0x0 | RO | L2 bank 0 error status |
| 0x184 | L2_BANKS_ERRORS_1 | 0x0 | RO | L2 bank 1 error status |
| ... | L2_BANKS_ERRORS_2..14 | 0x0 | RO | L2 bank error status |
| 0x1BC | L2_BANKS_ERRORS_15 | 0x0 | RO | L2 bank 15 error status |
| 0x1C0 | DEBUG_DMACTIVE | 0x0 | RW | RISC-V Debug Module active flag |
| 0x1C4 | DEBUG_DMACTIVEACK | 0x0 | RO | Debug Module active acknowledge |
| 0x1C8 | DEBUG_SNOOP | 0x0 | RW | Debug snoop bus configuration |
| 0x1CC | OVERLAY_INFO | 0x0 | RO | Overlay version/variant identifier |
| 0x1D0 | SW_RAS | 0x0 | RW | Software Reliability, Availability, Serviceability |
| 0x1D4 | SBUS_RSINK_RESET_FALLBACK | 0x0 | RW | SBUS reset sink fallback configuration |
| 0x1D8 | OVERLAY_CHICKEN_BITS | 0x0 | RW | Overlay debug/workaround chicken bits |
| 0x1DC | L1_ACCESSIBLE_REGION | 0x0 | RW | L1 SRAM accessible region base/size |
| 0x1E0 | L1_REGION_ERROR | 0x0 | RO | L1 region access violation address |

#### CLOCK_GATING Register (0x0CC) — Field Table

| Bit | Field Name | Reset | Description |
|----|-----------|-------|-------------|
| 0 | ROCC | 0 | 1 = enable clock gating for ROCC accelerator interface |
| 1 | IDMA | 0 | 1 = enable clock gating for iDMA engine (gated_l1_clk) |
| 2 | CLUSTER_CTRL | 0 | 1 = enable clock gating for cluster controller APB logic |
| 3 | CONTEXT_SWITCH | 0 | 1 = enable clock gating for context switch unit |
| 4 | LLK_INTF | 0 | 1 = enable clock gating for LLK interface |
| 5 | SNOOP | 0 | 1 = enable clock gating for NoC snoop path |
| 6 | (reserved) | 0 | Reserved, write 0 |
| 7 | L1_FLEX_CLIENT_IDMA | 0 | 1 = enable clock gating for L1 flex-client iDMA port |
| 8 | L1_FLEX_CLIENT_OVERLAY | 0 | 1 = enable clock gating for L1 flex-client overlay port |
| 31:9 | (reserved) | 0 | Reserved |

WARNING: After writing CLOCK_GATING, write the desired hysteresis value to CLOCK_GATING_HYST (0x0D0). The 7-bit value in bits [6:0] specifies the hysteresis count; the clock remains active for `2^value` cycles after the last detected activity. Writing CLOCK_GATING.IDMA=1 without setting HYST may cause premature clock gating.

---

### 6.2 iDMA APB Registers

NOTE: Exact APB byte offsets for iDMA-specific registers are TBD in the RTL and will be documented in a future revision of this HDD. The register names, reset values, and semantics are fully defined below.

**Base address:** iDMA APB sub-bus within tile APB space (consult Appendix C for per-tile base offset).

| Register Name | Reset | Access | Width | Description |
|---------------|-------|--------|-------|-------------|
| IDMA_STATUS | 0x0 | RO | 32 | Bit N = 1 if TID N has at least one transfer in-flight. Cleared automatically when all in-flight transfers for that TID complete. |
| IDMA_VC_SPACE[0] | 0x0 | RO | 32 | Available virtual channel slots for backend 0. |
| IDMA_VC_SPACE[1] | 0x0 | RO | 32 | Available virtual channel slots for backend 1. |
| IDMA_TR_COUNT[0..31] | 0x0 | RO | 32 | Per-TID completion count. Increments by 1 each time a transfer tagged with TID N completes. Cleared by writing 1 to IDMA_CLR[N]. |
| IDMA_THRESHOLD[0..31] | 0x0 | RW | 32 | Per-TID IRQ threshold. When IDMA_TR_COUNT[N] >= IDMA_THRESHOLD[N] (and threshold != 0), asserts o_idma_tiles_to_process_irq[N]. |
| IDMA_CLR[0..31] | 0x0 | W1C | 32 | Write 1 to bit N to atomically clear IDMA_TR_COUNT[N] and deassert IRQ[N]. |
| IDMA_CLK_EN | 0x0 | RW | 32 | Bit [0]: iDMA L1 clock gate enable. Mirrors CLOCK_GATING.IDMA. |
| IDMA_CLK_HYST | 0x0 | RW | 32 | Bits [6:0]: hysteresis count for gated_l1_clk. Mirrors CLOCK_GATING_HYST. |

**Usage pattern for completion tracking:**

```c
// Setup: set IRQ threshold to 1 transfer per TID
IDMA_THRESHOLD[TID] = 1;

// Issue DMA transfer with trid = TID
issue_dma(src, dst, len, TID);

// Poll for completion
while (!(read(IDMA_TR_COUNT[TID]) >= 1)) { /* spin or yield */ }

// Clear IRQ and counter
write(IDMA_CLR[TID], 1 << TID);
```

---

### 6.3 ATT (Address Translation Table)

The ATT is a hardware lookup table that translates software-visible virtual addresses to NoC physical coordinates. iDMA descriptors can use ATT-translated addresses by forming the source or destination address within the ATT-mapped range.

**ATT base address:** `0x0201_0000`
**ATT size:** `0x3000` bytes (12 KB)

The ATT is programmed by the overlay firmware or the host CPU before issuing DMA transfers that target remote tiles. Each ATT entry maps a (mask, endpoint, routing) tuple. Refer to the Router Address Decoding HDD (router_decode_HDD_v0.5.md, Section 4) for full ATT programming details.

**iDMA + ATT interaction:** When a DMA transfer's source or destination address falls within the ATT-mapped range, the NoC router at the source tile performs the address translation and routes the packet to the correct physical endpoint. iDMA itself has no knowledge of the ATT; it simply issues the address as given in the descriptor.

---

## 7. RISC-V CPU — SW Guide

This section is a comprehensive guide for SW engineers writing firmware or runtime code that runs on the RISC-V CPU harts embedded in each Trinity N1B0 Tensix tile.

### 7.1 Hart Architecture Summary

Each Tensix tile contains **8 RISC-V harts** (hart IDs 0–7), implemented using the Rocket core generator.

**ISA:** RV64GC — 64-bit base integer ISA with:
- G: general extensions (M, A, F, D, Zicsr, Zifencei)
- C: compressed 16-bit instructions
- CUSTOM_0–3: ROCC custom extension opcode space

**Per-hart resources:**
- 32-entry integer register file (x0–x31)
- 32-entry floating-point register file (f0–f31)
- Full set of Machine-mode CSRs
- Private D-cache and I-cache (shared L2 backed by tile L1)
- ROCC interface: CUSTOM_1 connects to the iDMA client port for this hart

**Shared resources (all 8 harts):**
- L1 SRAM: 768 KB per tile (N1B0), accessed via flex-client OBI ports
- L2 cache: backed by L1 SRAM
- PLIC, CLINT (platform-specific base addresses)

**Per-hart reset:** Each hart has an independent reset signal `i_smn_reset_n[7:0]` controlled by the SMN ring. Host firmware can hold individual harts in reset and release them independently.

**Key CSR addresses:**

| CSR Name | Address | Description |
|----------|---------|-------------|
| mstatus | 0x300 | Machine status register (MIE, MPIE, MPP, etc.) |
| misa | 0x301 | ISA and extensions (RV64GC) |
| mie | 0x304 | Machine interrupt enable (MSIE, MTIE, MEIE) |
| mtvec | 0x305 | Machine trap-handler base address |
| mscratch | 0x340 | Scratch register for trap handler |
| mepc | 0x341 | Machine exception program counter |
| mcause | 0x342 | Machine trap cause |
| mtval | 0x343 | Machine bad address or instruction |
| mip | 0x344 | Machine interrupt pending |
| mhartid | 0xF14 | Hardware thread ID (0–7 per tile) |
| mcycle | 0xB00 | Cycle counter (lower 32 bits) |
| mcycleh | 0xB80 | Cycle counter (upper 32 bits) |
| minstret | 0xB02 | Instructions retired counter |

---

### 7.2 Boot Sequence and Reset Vector Setup

At power-on, all harts are held in reset by the SMN ring. The host must load firmware into L1 or DRAM, set up reset vectors, then release harts from reset in the desired order.

**Detailed boot steps:**

1. SMN asserts hart reset: all harts are held in reset (`i_smn_reset_n[7:0] = 0`)
2. Host/firmware copies tile firmware binary to L1 SRAM or DRAM via a separate DMA path (e.g., host-side PCIe DMA)
3. Host writes per-hart RESET_VECTOR_N registers via APB to `cluster_ctrl_apb` base 0x03000000
4. Host deasserts per-hart reset via the SMN sequence or by writing DEBUG_DMACTIVE
5. Each released hart fetches its first instruction from `RESET_VECTOR_N << 2` (word address -> byte address)
6. Hart firmware executes: initialize stack pointer, set up `mtvec`, optionally clear BSS, then enter main work loop

NOTE: RESET_VECTOR_N stores a **word address** (bits [57:0] of the byte address right-shifted by 2). Firmware must right-shift the byte address by 2 before writing the register.

```c
// Host-side: set hart 0 reset vector before releasing from reset
#define CLUSTER_CTRL_BASE  0x03000000UL
#define RESET_VECTOR_0     (CLUSTER_CTRL_BASE + 0x000)
#define DEBUG_DMACTIVE     (CLUSTER_CTRL_BASE + 0x1C0)

// Set reset vector: byte_addr -> word_addr = byte_addr >> 2
void set_hart_reset_vector(int hart_id, uint64_t pc) {
    volatile uint64_t *rv = (uint64_t *)(RESET_VECTOR_0 + hart_id * 8);
    *rv = pc >> 2;   // stored as word address [57:0]
}

// Release hart from reset via DEBUG_DMACTIVE
void release_hart_from_reset(int hart_id) {
    volatile uint32_t *dmactive = (uint32_t *)DEBUG_DMACTIVE;
    *dmactive = (1u << hart_id);   // set bit to activate hart
}

// Full bring-up sequence for a tile
void tile_bring_up(uint64_t firmware_entry_point) {
    // Set all harts to same entry point (or per-hart if needed)
    for (int i = 0; i < 8; i++) {
        set_hart_reset_vector(i, firmware_entry_point);
    }
    // Release hart 0 first; hart 0 will release others via CLINT MSIP
    release_hart_from_reset(0);
}
```

**On-tile firmware entry stub (RISC-V assembly):**

```asm
.section .text.entry
.global _start
_start:
    # Set up stack pointer based on hart ID
    csrr    t0, mhartid
    li      t1, 4096              # HART_STACK_SIZE
    mul     t0, t0, t1
    la      sp, __stack_top       # top of hart 0 stack
    sub     sp, sp, t0            # each hart gets its own stack

    # Set up trap handler
    la      t0, machine_trap_handler
    csrw    mtvec, t0

    # Clear BSS (hart 0 only)
    csrr    t0, mhartid
    bnez    t0, .skip_bss_clear
    la      t0, __bss_start
    la      t1, __bss_end
1:  bge     t0, t1, .skip_bss_clear
    sd      zero, 0(t0)
    addi    t0, t0, 8
    j       1b
.skip_bss_clear:
    # Jump to C main
    call    hart_main
    # Should never return; halt
1:  wfi
    j       1b
```

---

### 7.3 Per-Hart Stack Layout and Memory Map

In N1B0, each tile has 768 KB of L1 SRAM. A practical layout for 8 harts sharing this space:

```
L1 Memory (768 KB = 0x000000 to 0x0BFFFF per tile)
+---------------------------------------------+ 0x0BF000 (top - 4KB)
|  Hart 7 stack (4 KB)                        |
+---------------------------------------------+ 0x0BE000
|  Hart 6 stack (4 KB)                        |
+---------------------------------------------+ 0x0BD000
|  Hart 5 stack (4 KB)                        |
+---------------------------------------------+ 0x0BC000
|  Hart 4 stack (4 KB)                        |
+---------------------------------------------+ 0x0BB000
|  Hart 3 stack (4 KB)                        |
+---------------------------------------------+ 0x0BA000
|  Hart 2 stack (4 KB)                        |
+---------------------------------------------+ 0x0B9000
|  Hart 1 stack (4 KB)                        |
+---------------------------------------------+ 0x0B8000
|  Hart 0 stack (4 KB)                        |
+---------------------------------------------+ 0x0B7000
|  Shared data / reduction buffers (variable) |
+---------------------------------------------+ 0x090000
|  DMA staging buffer B (double-buffer idle)  |
|  (256 KB)                                   |
+---------------------------------------------+ 0x050000
|  DMA staging buffer A (double-buffer active)|
|  (256 KB)                                   |
+---------------------------------------------+ 0x010000
|  Firmware code (.text) + .rodata            |
|  (64 KB)                                    |
+---------------------------------------------+ 0x000000
```

TIP: Align DMA buffers to 128-byte (cache line) boundaries. Keep stacks at the top of L1 so that tensor data placed at the bottom cannot grow into the stack region.

TIP: If firmware code is small, it can be placed entirely in L1 to avoid I-cache misses to DRAM. Typical firmware for a single tile workload fits within 32–64 KB.

```c
#define L1_BASE              0x00000000UL
#define L1_SIZE              (768 * 1024)
#define HART_STACK_SIZE      4096
// Stack top for hart 'id': hart 0 uses 0x0B8000..0x0B8FFF, etc.
#define HART_STACK_TOP(id)   (L1_BASE + L1_SIZE - (id) * HART_STACK_SIZE)
// DMA double-buffer regions
#define DMA_BUF_A_BASE       (L1_BASE + 0x10000)
#define DMA_BUF_B_BASE       (L1_BASE + 0x50000)
#define DMA_BUF_SIZE         (256 * 1024)
// Shared data region
#define SHARED_DATA_BASE     (L1_BASE + 0x090000)
#define SHARED_DATA_SIZE     (L1_SIZE - 8*HART_STACK_SIZE - 2*DMA_BUF_SIZE - 0x10000)
```

WARNING: Do not overlap DMA buffer regions with the firmware code region. A DMA write to the code region will corrupt executing instructions and cause undefined behavior.

---

### 7.4 PLIC — Platform-Level Interrupt Controller

Trinity uses a standard RISC-V PLIC for routing external interrupts to harts. The iDMA engine's per-TID IRQ outputs (`o_idma_tiles_to_process_irq[31:0]`) are wired as PLIC external interrupt sources.

**PLIC register layout (standard RISC-V PLIC):**
```
PLIC_BASE (chip-specific, e.g., 0x0C00_0000)
  Priority registers:  PLIC_BASE + 4*irq_id   (one 32-bit word per IRQ source)
  Pending bits:        PLIC_BASE + 0x1000      (one bit per IRQ source)
  Enable registers:    PLIC_BASE + 0x2000 + 0x80*context_id
  Threshold register:  PLIC_BASE + 0x200000 + 0x1000*context_id
  Claim/complete reg:  PLIC_BASE + 0x200004 + 0x1000*context_id
```

M-mode context ID for hart N = N * 2 (S-mode = N * 2 + 1, not used in machine-mode firmware).

**Setup sequence:**

1. Set priority for each PLIC source (write 1–7; 0 = disabled)
2. Set threshold for each hart context (0 = accept all non-zero priority IRQs)
3. Enable specific IRQ sources in PLIC enable registers
4. Set `mie.MEIE` (bit 11) to enable M-mode external interrupts
5. Set `mstatus.MIE` (bit 3) to enable global interrupts
6. Set `mtvec` to the trap handler address (bit[1:0] = 0 for direct mode)

```c
#define PLIC_BASE          0x0C000000UL   // SoC-specific: verify with integration team
#define PLIC_PRIORITY(n)   (*(volatile uint32_t *)(PLIC_BASE + 4*(n)))
#define PLIC_ENABLE_REG(ctx, irq)  \
    (*(volatile uint32_t *)(PLIC_BASE + 0x2000 + 0x80*(ctx) + 4*((irq)/32)))
#define PLIC_THRESHOLD(ctx) (*(volatile uint32_t *)(PLIC_BASE + 0x200000 + 0x1000*(ctx)))
#define PLIC_CLAIM(ctx)     (*(volatile uint32_t *)(PLIC_BASE + 0x200004 + 0x1000*(ctx)))

// iDMA TID 0..31 are mapped to PLIC IRQ sources IDMA_IRQ_BASE..IDMA_IRQ_BASE+31
#define IDMA_IRQ_BASE      32    // confirm with SoC integration team

void plic_enable_idma_irq(int hart_id, int tid) {
    int irq     = IDMA_IRQ_BASE + tid;
    int context = hart_id * 2;   // M-mode context

    // Set priority 1 (lowest non-zero)
    PLIC_PRIORITY(irq) = 1;

    // Enable IRQ in this hart's context
    PLIC_ENABLE_REG(context, irq) |= (1u << (irq % 32));

    // Accept any priority
    PLIC_THRESHOLD(context) = 0;
}

void plic_disable_idma_irq(int hart_id, int tid) {
    int irq     = IDMA_IRQ_BASE + tid;
    int context = hart_id * 2;
    PLIC_ENABLE_REG(context, irq) &= ~(1u << (irq % 32));
}

// Called from trap handler: claim pending IRQ
int plic_claim_irq(int hart_id) {
    return (int)PLIC_CLAIM(hart_id * 2);
}

// Called after handling: complete the IRQ
void plic_complete_irq(int hart_id, int irq) {
    PLIC_CLAIM(hart_id * 2) = (uint32_t)irq;
}
```

**Trap handler with PLIC:**

```c
// Shared completion flags (one per TID)
volatile int g_dma_done[32];

void __attribute__((interrupt("machine"))) machine_trap_handler(void) {
    uint64_t mcause;
    asm volatile ("csrr %0, mcause" : "=r"(mcause));

    if (mcause & (1ULL << 63)) {
        // Asynchronous interrupt
        uint64_t cause = mcause & 0x7FFFFFFFFFFFFFFFULL;

        if (cause == 3) {
            // M-mode software interrupt (MSIP from CLINT)
            int hart_id;
            asm volatile ("csrr %0, mhartid" : "=r"(hart_id));
            // Clear MSIP
            *((volatile uint32_t *)(0x02000000UL + 4 * hart_id)) = 0;
            // User handler
            handle_msip(hart_id);

        } else if (cause == 11) {
            // M-mode external interrupt (from PLIC)
            int hart_id;
            asm volatile ("csrr %0, mhartid" : "=r"(hart_id));
            int irq = plic_claim_irq(hart_id);

            if (irq >= IDMA_IRQ_BASE && irq < IDMA_IRQ_BASE + 32) {
                int tid = irq - IDMA_IRQ_BASE;
                // Clear the iDMA TID counter
                idma_clear_tid(tid);
                g_dma_done[tid] = 1;
            }
            plic_complete_irq(hart_id, irq);
        }

    } else {
        // Synchronous exception
        uint64_t mepc, mtval;
        asm volatile ("csrr %0, mepc"  : "=r"(mepc));
        asm volatile ("csrr %0, mtval" : "=r"(mtval));
        // Log and halt — exceptions are fatal in most firmware contexts
        fatal_exception(mcause, mepc, mtval);
    }
}

void hart_init_interrupts(void) {
    // Point mtvec at trap handler (direct mode: bits[1:0] = 0b00)
    uintptr_t tvec = (uintptr_t)machine_trap_handler;
    // Ensure alignment (direct mode requires 4-byte alignment)
    asm volatile ("csrw mtvec, %0" :: "r"(tvec & ~3UL));

    // Enable M-mode software interrupt (MSIE, bit 3) and external interrupt (MEIE, bit 11)
    asm volatile ("csrs mie, %0" :: "r"((1u << 3) | (1u << 11)));

    // Enable global machine interrupt
    asm volatile ("csrs mstatus, %0" :: "r"(1u << 3));  // MIE bit
}
```

---

### 7.5 CLINT — Core-Local Interruptor

The CLINT provides per-hart machine software interrupts (MSIP) and a machine timer (MTIME/MTIMECMP). Software interrupts are the primary mechanism for one hart to wake another.

**Register layout:**
```
CLINT_BASE (chip-specific, e.g., 0x0200_0000)
  MSIP[hart_id]    : CLINT_BASE + 0x0000 + hart_id*4  (RW, 1-bit, write 1 to assert)
  MTIMECMP[hart_id]: CLINT_BASE + 0x4000 + hart_id*8  (RW, 64-bit)
  MTIME            : CLINT_BASE + 0xBFF8               (RO, 64-bit, free-running)
```

```c
#define CLINT_BASE          0x02000000UL
#define CLINT_MSIP(id)      ((volatile uint32_t *)(CLINT_BASE + 4*(id)))
#define CLINT_MTIMECMP(id)  ((volatile uint64_t *)(CLINT_BASE + 0x4000 + 8*(id)))
#define CLINT_MTIME         ((volatile uint64_t *)(CLINT_BASE + 0xBFF8))
#define CLINT_FREQ_HZ       1000000UL   // 1 MHz reference (platform-specific)

// Hart A sends software interrupt to wake hart B
void wake_hart(int target_hart) {
    *CLINT_MSIP(target_hart) = 1;   // assert software interrupt
    // Memory fence to ensure the write reaches CLINT before returning
    asm volatile ("fence w,w");
}

// Called from MSI handler: hart clears its own MSIP
void msip_clear(void) {
    int hart_id;
    asm volatile ("csrr %0, mhartid" : "=r"(hart_id));
    *CLINT_MSIP(hart_id) = 0;
}

// Busy-wait with timeout using MTIME (timeout_us in microseconds)
// Returns 0 on success, -1 on timeout
int wait_flag_timeout_us(volatile int *flag, uint64_t timeout_us) {
    uint64_t deadline = *CLINT_MTIME + timeout_us * (CLINT_FREQ_HZ / 1000000ULL);
    while (!*flag) {
        if (*CLINT_MTIME > deadline) return -1;
        asm volatile ("nop");   // prevent tight loop from starving other harts
    }
    return 0;
}

// Machine timer interrupt: periodic tick
void set_timer_interrupt_us(int hart_id, uint64_t period_us) {
    uint64_t now = *CLINT_MTIME;
    *CLINT_MTIMECMP(hart_id) = now + period_us * (CLINT_FREQ_HZ / 1000000ULL);
    // Enable MTIE in mie CSR
    asm volatile ("csrs mie, %0" :: "r"(1u << 7));  // MTIE bit
}
```

NOTE: CLINT_FREQ_HZ is the MTIME increment frequency, which is typically a slow reference clock (1 MHz or 10 MHz), NOT the core clock. Confirm the actual value with the platform integration team.

---

### 7.6 Fence and Memory Ordering with DMA

The RISC-V memory model (RVWMO) does not guarantee that stores visible to one agent are immediately visible to another (DMA engine). SW must use `fence` instructions at all DMA boundaries.

**Critical rules:**

1. **Before issuing DMA (source data):** All CPU stores to the source buffer must be visible to L1 SRAM before the DMA reads them. Insert `fence w,w` (or `fence`) before `DMSRC`/`DMCPY`.

2. **After DMA completes (destination data):** All DMA writes to the destination buffer must be visible to the CPU before it reads them. Insert `fence r,r` (or `fence`) after polling/IRQ completion, before reading the destination buffer.

3. **Between DMA and TDMA:** TDMA reads from L1; DMA writes to L1. After DMA completes, insert a `fence` before issuing TDMA UNPACR instructions that read the same region.

```c
// CORRECT ordering pattern: CPU write -> DMA -> CPU read

// Step 1: CPU prepares source data in L1
memcpy(l1_src_ptr, cpu_data, len);
asm volatile ("fence w,w");    // ensure CPU stores are visible to DMA engine

// Step 2: Issue DMA transfer
asm_dmsrc(l1_src_addr);
asm_dmdst(remote_noc_addr_or_dram);
asm_dmcpy(len, FLAGS_TID(0));

// Step 3: Wait for completion
while (!(idma_read_tr_count(0) >= 1)) { }
idma_clear_tid(0);
asm volatile ("fence r,r");    // ensure DMA writes are visible to CPU

// Step 4: CPU reads destination
process_data(l1_dst_ptr);
```

WARNING: Omitting `fence w,w` before DMA is the most common source of data corruption. The CPU store buffer may not have flushed to L1 SRAM when the DMA engine begins reading.

WARNING: Omitting `fence r,r` after DMA completion is the second most common bug. The CPU may observe stale cached values from before the DMA write.

**DMA write to remote tile — remote tile must also fence:**
```c
// After Tile A sends data via DMA PUT to Tile B's L1,
// the firmware running on Tile B must fence before reading:

// Tile B firmware (signaled that DMA has arrived):
asm volatile ("fence r,r");
uint32_t *received = (uint32_t *)L1_BASE;
// received[] is now guaranteed valid
```

---

### 7.7 ROCC Custom Instruction Interface

The ROCC (Rocket Custom Co-processor) extension provides a tightly coupled interface between each CPU hart and its dedicated iDMA client port (clients 0–7 = harts 0–7).

**ROCC opcode assignment:**
- `CUSTOM_0` (opcode 0x0B): Reserved
- `CUSTOM_1` (opcode 0x2B): iDMA instructions (funct7=0x2B)
- `CUSTOM_2` (opcode 0x5B): Reserved
- `CUSTOM_3` (opcode 0x7B): Reserved

**Shadow register model:** Instructions DMSRC, DMDST, DMSTR, and DMREP each write per-hart shadow registers inside `tt_rocc_accel`. These registers are not committed to hardware until `DMCPY` is issued. `DMCPY` is the commit instruction.

**Instruction timing:**
- DMSRC/DMDST/DMSTR/DMREP: 1 cycle (shadow register write, no FIFO interaction)
- DMCPY: may stall if frontend FIFO is full (`o_idma_ready[client_id] = 0`)
- DMSTAT/DMSTATI: returns immediately without stalling

**Back-pressure behavior:** If the iDMA frontend FIFO (metadata depth=42 entries) is full, `o_idma_ready[client_id]` is deasserted. The ROCC interface will hold the CPU hart in a wait state until space becomes available. This is transparent to firmware but means DMCPY can block for many cycles under heavy load.

**Practical FIFO capacity per hart:** With 24 clients sharing a 42-entry FIFO and weighted round-robin arbitration, each hart can sustain approximately 1–2 in-flight descriptors before hitting FIFO pressure. Issuing more than 2 DMCPY instructions per hart before waiting for completions may cause DMCPY to stall.

```c
// Check readiness before issuing to avoid stalls
// DMSTATI with field=DMSTAT_READY returns 1 if frontend can accept
static inline uint64_t asm_dmstati(uint64_t field) {
    uint64_t result;
    asm volatile (".insn r 0x2B, 4, 0, %0, zero, %1"
                  : "=r"(result) : "r"(field));
    return result;
}

// Non-blocking DMA issue with readiness check
int try_issue_dma(uint64_t src, uint64_t dst, uint64_t len, int trid) {
    if (!asm_dmstati(1 /* DMSTAT_READY */)) {
        return -1;  // FIFO full, caller must retry
    }
    asm_dmsrc(src);
    asm_dmdst(dst);
    asm_dmcpy(len, (uint64_t)trid & 0x1F);
    return 0;
}
```

---

### 7.8 Context Switch Considerations

NOTE: Trinity N1B0 firmware typically does not perform preemptive context switching — each hart runs a dedicated workload. However, some runtime frameworks implement cooperative multitasking. This section covers the implications for iDMA and ROCC state.

**Shadow register state (DMSRC/DMDST/DMSTR/DMREP):** These are stored inside `tt_rocc_accel` per hart. They are NOT saved/restored by hardware on context switch. If a context switch occurs between DMSRC and DMCPY instructions, the shadow registers for the suspended task will be corrupted by the newly scheduled task.

**SW obligation:** Any context switch implementation must save and restore the ROCC shadow register state. Since these are not CSRs (they are internal ROCC registers), saving them requires re-issuing the DMSRC/DMDST/DMSTR/DMREP instructions after a context restore.

**In-flight DMA transfers:** DMA transfers submitted via DMCPY are independent of the issuing hart's execution state. They continue to completion even if the hart is reset or context-switched. The DMA engine does not track which hart submitted a transfer; it only tracks TIDs.

**TID ownership:** It is the SW's responsibility to track which context owns which TID. A context switch must either:
a) Wait for all owned TIDs to complete before switching out, or
b) Transfer TID ownership to the new context and ensure the new context handles completion IRQs.

```c
// Safe context switch: wait for all in-flight TIDs owned by this context
typedef struct {
    uint64_t shadow_src;
    uint64_t shadow_dst;
    uint64_t shadow_str_src;
    uint64_t shadow_str_dst;
    uint64_t shadow_rep;
    uint32_t owned_tids;    // bitmask of TIDs owned by this context
} rocc_context_t;

void context_switch_out(rocc_context_t *ctx) {
    // Wait for all owned TIDs to complete
    for (int tid = 0; tid < 32; tid++) {
        if (ctx->owned_tids & (1u << tid)) {
            while (!(idma_read_tr_count(tid) >= 1)) { }
            idma_clear_tid(tid);
        }
    }
    ctx->owned_tids = 0;
    // Shadow regs are indeterminate after switch; re-issue before next DMCPY
}

void context_switch_in(rocc_context_t *ctx) {
    // Restore shadow registers if a pending transfer was interrupted
    // (only needed if transfer was not completed before switch-out)
    asm_dmsrc(ctx->shadow_src);
    asm_dmdst(ctx->shadow_dst);
    asm_dmstr(ctx->shadow_str_src, ctx->shadow_str_dst);
    asm_dmrep(ctx->shadow_rep);
    // Now DMCPY may be safely issued
}
```

---

### 7.9 Multi-Hart Coordination Patterns

Three common patterns for coordinating multiple harts within a tile:

---

**Pattern A — Barrier (all harts synchronize at a point):**

All harts must arrive at the barrier before any proceeds. Uses an atomic counter in shared L1.

```c
// Placed in shared L1 SRAM (not on any hart's stack)
volatile int g_barrier_count = 0;
volatile int g_barrier_sense = 0;   // alternates 0/1 for reuse

void barrier(int n_harts) {
    int local_sense = !g_barrier_sense;   // flip expected sense

    // Atomically increment barrier counter
    asm volatile ("amoadd.w zero, %0, (%1)"
                  :: "r"(1), "r"(&g_barrier_count) : "memory");

    // Wait until all n_harts have arrived
    // Use sense-reversal to allow barrier reuse
    if (g_barrier_count == n_harts) {
        g_barrier_count = 0;
        asm volatile ("fence w,w");   // ensure counter reset is visible
        g_barrier_sense = local_sense;
    } else {
        while (g_barrier_sense != local_sense) {
            asm volatile ("nop");
        }
    }
    asm volatile ("fence r,r");   // ensure all data written before barrier is visible
}
```

---

**Pattern B — Producer-Consumer (hart 0 DMA-loads, harts 1–7 compute):**

Hart 0 acts as a DMA prefetch engine, loading tiles from DRAM into L1 double buffers. Harts 1–7 compute on ready buffers.

```c
#define N_BUFS 2
volatile int g_buf_ready[N_BUFS] = {0, 0};
volatile int g_buf_consumed[N_BUFS] = {1, 1};  // start as "consumed" so producer fills them

// Hart 0: DMA producer
void producer_task(uint64_t *dram_tiles, int n_tiles) {
    for (int i = 0; i < n_tiles; i++) {
        int buf = i % N_BUFS;

        // Wait for consumers to finish with this buffer
        while (!g_buf_consumed[buf]) { asm volatile ("nop"); }
        g_buf_consumed[buf] = 0;

        // Load next tile into this buffer via DMA
        asm_dmsrc(dram_tiles[i]);
        asm_dmdst(DMA_BUF_A_BASE + (uint64_t)buf * DMA_BUF_SIZE);
        asm_dmcpy(DMA_BUF_SIZE, FLAGS_TID(buf));

        while (!(idma_read_tr_count(buf) >= 1)) { }
        idma_clear_tid(buf);

        asm volatile ("fence w,w");    // DMA write visible before signal
        g_buf_ready[buf] = 1;          // signal consumers
    }
}

// Harts 1-7: compute consumers
void consumer_task(int hart_id, int n_tiles) {
    for (int i = hart_id - 1; i < n_tiles; i += 7) {
        int buf = i % N_BUFS;

        while (!g_buf_ready[buf]) { asm volatile ("nop"); }
        asm volatile ("fence r,r");    // DMA write visible to this hart

        compute_on_buffer(DMA_BUF_A_BASE + (uint64_t)buf * DMA_BUF_SIZE, hart_id);

        // Signal producer that this hart is done with the buffer
        // Use atomic to handle multiple consumers safely
        asm volatile ("amoadd.w zero, %0, (%1)"
                      :: "r"(1), "r"(&g_buf_consumed[buf]) : "memory");
    }
}
```

---

**Pattern C — CLINT MSIP wake (hart 0 issues DMA, wakes hart 1 on completion via software interrupt):**

Hart 1 sleeps in WFI; hart 0 sends it a software interrupt after DMA completes.

```c
// Hart 0: issue DMA, then wake hart 1
void dma_and_notify_hart1(uint64_t dram_src, uint64_t l1_dst, uint32_t bytes) {
    // Set TID 0 IRQ threshold (optional; we poll here, then use MSIP to wake hart 1)
    asm_dmsrc(dram_src);
    asm_dmdst(l1_dst);
    asm_dmcpy(bytes, FLAGS_TID(0));

    while (!(idma_read_tr_count(0) >= 1)) { }
    idma_clear_tid(0);
    asm volatile ("fence w,w");   // DMA write visible before MSIP

    wake_hart(1);  // write CLINT_MSIP[1] = 1
}

// Hart 1: wait for wake, then process
void hart1_main(void) {
    // Enable software interrupt (MSIE, bit 3 of mie)
    asm volatile ("csrs mie, %0" :: "r"(1u << 3));
    asm volatile ("csrs mstatus, %0" :: "r"(1u << 3));  // global MIE

    while (1) {
        asm volatile ("wfi");      // sleep until MSIP
        asm volatile ("fence r,r"); // ensure DMA writes visible
        process(L1_BASE);
        // Optionally wake hart 0 to signal that processing is done
        wake_hart(0);
        asm volatile ("wfi");      // sleep again
    }
}
```

---

## 8. DMA Programming Guide

### 8.1 Initialization Sequence

The following initialization sequence must be performed once per tile before issuing any DMA transfers:

```c
#define CLUSTER_CTRL_BASE  0x03000000UL
#define CLOCK_GATING_REG   (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x0CC))
#define CLOCK_GATING_HYST  (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x0D0))
#define ECC_CTRL_REG       (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x11C))
#define IDMA_APB_BASE      0x00000000UL  // TBD: replace with actual per-tile iDMA APB base

void idma_init(void) {
    // Step 1: Disable clock gating during initialization
    // This ensures the iDMA backend is clocked while we write registers
    CLOCK_GATING_REG &= ~(1u << 1);    // CLOCK_GATING.IDMA = 0 (always on)
    CLOCK_GATING_REG &= ~(1u << 7);    // CLOCK_GATING.L1_FLEX_CLIENT_IDMA = 0

    // Step 2: Clear all pending TIDs and IRQ state
    // Write all-ones to IDMA_CLR to reset any stale state from previous runs
    idma_write_clr(0xFFFFFFFF);

    // Step 3: Initialize threshold registers to 0 (IRQ disabled for all TIDs)
    for (int tid = 0; tid < 32; tid++) {
        idma_set_threshold(tid, 0);
    }

    // Step 4: Set hysteresis and re-enable clock gating for production
    CLOCK_GATING_HYST  = 0x06;                       // 2^6 = 64-cycle hysteresis
    CLOCK_GATING_REG  |= (1u << 1) | (1u << 7);     // re-enable both IDMA gates

    // Step 5: Enable ECC detection for L1 SRAM (recommended for production)
    ECC_CTRL_REG = 1;

    // Step 6: Memory fence before first DMA use
    asm volatile ("fence");

    // Step 7: Verify iDMA readiness
    // DMSTATI field 1 (DMSTAT_READY) should return 1
    uint64_t ready = asm_dmstati(1);
    if (!ready) {
        // iDMA not ready: clock gating may not have deasserted yet
        // Retry after a short delay
        for (volatile int i = 0; i < 100; i++) { }
        ready = asm_dmstati(1);
    }
    // If still not ready, escalate to error handler
}
```

---

### 8.2 Basic 1D Transfer (L1-to-L1, same tile)

```c
// Copy 4096 bytes from L1 offset 0x0 to L1 offset 0x1000
void idma_local_copy_1d(void) {
    asm volatile ("fence w,w");     // ensure source data is in L1

    asm_dmsrc(0x00000000ULL);       // source: L1 base
    asm_dmdst(0x00001000ULL);       // destination: L1 + 4 KB
    asm_dmcpy(4096, 0);             // length=4096, flags: trid=0, vc=0

    while (asm_dmstat() & 1) { }   // wait for busy to clear
}
```

---

### 8.3 DMA from DRAM (ISP/GPU Image Buffer) to L1

```c
#define DRAM_SI0_BASE   0x60000000ULL
#define L1_BASE         0x00000000ULL
#define TRANSFER_BYTES  (256 * 1024)    // 256 KB

void idma_dram_to_l1(uint64_t dram_src_offset, int trid) {
    // Set IRQ threshold for this TID
    idma_set_threshold(trid, 1);

    // Fence: ensure any prior L1 activity is visible
    asm volatile ("fence");

    // Issue DMA: use decouple_rw to allow AXI read prefetch to proceed
    // ahead of OBI write, hiding DRAM latency
    uint64_t flags = (uint64_t)trid | IDMA_FLAG_DECOUPLE_RW;
    asm_dmsrc(DRAM_SI0_BASE + dram_src_offset);
    asm_dmdst(L1_BASE);
    asm_dmcpy(TRANSFER_BYTES, flags);

    // Poll TID completion
    while (!(idma_read_tr_count(trid) >= 1)) { }
    idma_clear_tid(trid);
    asm volatile ("fence r,r");   // ensure DMA writes visible to CPU
}
```

NOTE: Maximum single transfer is 4 MB (`IDMA_TRANSFER_LENGTH_WIDTH = 22` bits). For larger transfers, split into multiple descriptors with different TIDs.

---

### 8.4 2D Scatter-Gather Transfer

```c
// Read a 128x64 FP16 sub-matrix from a 1024x64 DRAM matrix
// Source: row-major, row stride = 1024 * 2 = 2048 bytes
// Destination: packed contiguous in L1

#define ELEM_BYTES       2          // FP16 = 2 bytes/element
#define SRC_ROWS         128
#define SRC_COLS         64
#define SRC_ROW_STRIDE   2048       // full matrix row width in bytes
#define DST_ROW_STRIDE   (64 * 2)   // packed row: 128 bytes

void idma_strided_matrix_read(uint64_t dram_base, uint64_t l1_base) {
    asm volatile ("fence w,w");
    asm_dmsrc(dram_base);
    asm_dmdst(l1_base);
    asm_dmstr(SRC_ROW_STRIDE, DST_ROW_STRIDE);
    asm_dmrep(SRC_ROWS);
    asm_dmcpy(SRC_COLS * ELEM_BYTES,
              IDMA_FLAG_DECOUPLE_RW | FLAGS_TID(0));

    while (!(idma_read_tr_count(0) >= 1)) { }
    idma_clear_tid(0);
    asm volatile ("fence r,r");
}
```

---

### 8.5 Tile-Based vs Non-Tile-Based Access

| Access Pattern | iDMA Mode | Description |
|---------------|-----------|-------------|
| Non-tile (1D) | `num_reps=1` | Single contiguous block bulk copy |
| Non-tile (2D) | `num_reps>1, decouple_rw=0` | Strided row reads from DRAM |
| Tile-based | `num_reps>1, decouple_rw=1` | Prefetch multiple tiles concurrently via dual backends |

```c
// Two concurrent tile prefetches (saturates both backends)
void prefetch_two_tiles(uint64_t tile0_src, uint64_t tile1_src,
                        uint64_t tile0_dst, uint64_t tile1_dst) {
    uint64_t f0 = FLAGS_TID(0) | IDMA_FLAG_DECOUPLE_RW;
    uint64_t f1 = FLAGS_TID(1) | IDMA_FLAG_DECOUPLE_RW;

    asm_dmsrc(tile0_src);
    asm_dmdst(tile0_dst);
    asm_dmcpy(TILE_BYTES, f0);   // dispatched to BE #0

    asm_dmsrc(tile1_src);
    asm_dmdst(tile1_dst);
    asm_dmcpy(TILE_BYTES, f1);   // dispatched to BE #1

    while (idma_read_tr_count(0) < 1 || idma_read_tr_count(1) < 1) { }
    idma_clear_tid(0);
    idma_clear_tid(1);
    asm volatile ("fence r,r");
}
```

---

### 8.6 Address Translation using ATT

```c
// Program ATT entry 5 to map logical address 0x8000_0000 to tile (2,3) L1 base
// NoC address format: bits[75:70]=y_coord, [69:64]=x_coord, [63:0]=local_addr

void att_program_remote_tile(int entry, int x, int y, uint64_t local_addr) {
    uint64_t noc_addr = ((uint64_t)(y & 0x3F) << 70) |
                        ((uint64_t)(x & 0x3F) << 64) |
                        local_addr;
    att_write_entry(0x02010000UL, entry,
                    /*mask=*/    0xFFFFFFFF00000000ULL,
                    /*endpoint=*/noc_addr,
                    /*routing=*/ DOR_XY);
}

// DMA write to remote tile via ATT-mapped address
void idma_write_to_remote_tile_att(void) {
    att_program_remote_tile(5, 2, 3, L1_BASE);

    asm volatile ("fence w,w");
    asm_dmsrc(local_l1_src);
    asm_dmdst(0x80000000ULL);    // ATT entry 5 maps this to tile(2,3)
    asm_dmcpy(XFER_BYTES, 0);
    while (asm_dmstat() & 1) { }
}
```

---

### 8.7 Data Format Conversion During Transfer (DFC)

```c
// Load FP32 weights from DRAM and store as BF16 in L1 (2:1 compression)
#define N_ELEMENTS  65536
#define SRC_BYTES   (N_ELEMENTS * 4)   // FP32: 4 bytes/element
#define DST_BYTES   (N_ELEMENTS * 2)   // BF16: 2 bytes/element

void idma_fp32_to_bf16_dma(uint64_t dram_fp32_src, uint64_t l1_bf16_dst) {
    idma_dfc_req_t req = {
        .base = {
            .src_addr   = dram_fp32_src,
            .dst_addr   = l1_bf16_dst,
            .length     = SRC_BYTES,
            .num_reps   = 1,
        },
        .dfc_enable  = 1,
        .src_format  = DFC_FLOAT32,
        .dst_format  = DFC_FLOAT16_B,
        .stoch_round = 0,
    };
    issue_idma_dfc(&req, 0);
    while (asm_dmstat() & 1) { }
    asm volatile ("fence r,r");
}
```

NOTE: For MX block formats, the transfer length must be a multiple of 8 elements (MX_BLOCK_SIZE). Misaligned transfers will produce incorrect block exponents.

---

### 8.8 L1 Accumulate (Zero-Copy Partial Sum)

```c
// Accumulate partial sum from remote tile into local accumulate channel 3
void idma_accumulate_from_remote(int src_x, int src_y) {
    idma_flit_t flit = {
        .trid = 2,
        .vc   = 0,
        .l1_accum_cfg_reg = { .enable = 1, .channel = 3 },
        .payload = {
            .src_addr    = remote_tile_noc_addr(src_x, src_y, L1_BASE),
            .dst_addr    = L1_ACC_CHANNEL_ADDR(3),
            .length      = PARTIAL_SUM_BYTES,
            .num_reps    = 1,
            .decouple_rw = 1,
        },
    };
    issue_idma_flit(&flit);
    while (!(idma_read_tr_count(2) >= 1)) { }
    idma_clear_tid(2);
    asm volatile ("fence r,r");
    // L1 acc channel 3 now contains the accumulated sum
}
```

---

### 8.9 Zero-Copy Memory Patterns

**Pattern 1: In-place accumulate (all-reduce across tiles)**
```c
// Receive partial sums from 3 source tiles, accumulate into channel 0
for (int src = 0; src < 3; src++) {
    idma_flit_t f = {
        .trid = src,
        .l1_accum_cfg_reg = { .enable = 1, .channel = 0 },
        .payload = {
            .src_addr = remote_noc_addr(src_x[src], src_y[src], 0),
            .dst_addr = L1_ACC_CHANNEL_ADDR(0),
            .length   = PARTIAL_BYTES, .num_reps = 1,
        },
    };
    issue_idma_flit(&f);
}
for (int t = 0; t < 3; t++) {
    while (!(idma_read_tr_count(t) >= 1)) { }
    idma_clear_tid(t);
}
asm volatile ("fence r,r");
// Channel 0 holds sum of 4 tiles' partial results
```

**Pattern 2: Format-converted load (eliminates CPU conversion pass)**
```c
idma_dfc_load(DRAM_WEIGHT_ADDR, L1_WEIGHT_ADDR,
              DFC_FLOAT32, DFC_FLOAT16_B, WEIGHT_BYTES);
// L1 holds BF16 weights; no separate CPU format conversion needed
```

**Pattern 3: Zero-fill (INIT path)**
```c
// Clear accumulation buffer before use
idma_req_t zero_req = {
    .src_addr = 0, .dst_addr = L1_ACCUM_BASE,
    .length = ACCUM_BYTES, .num_reps = 1,
};
issue_idma_init(&zero_req, 0);
while (!(idma_read_tr_count(0) >= 1)) { }
idma_clear_tid(0);
```

---

### 8.10 Multi-Client Pipelining

```c
#define PIPELINE_DEPTH  8

void idma_pipelined_load(uint64_t *srcs, uint64_t *dsts, int N) {
    int issued = 0, completed = 0;
    idma_set_threshold(0, 1);

    while (completed < N) {
        while (issued < N && (issued - completed) < PIPELINE_DEPTH) {
            asm_dmsrc(srcs[issued]);
            asm_dmdst(dsts[issued]);
            asm_dmcpy(TILE_BYTES, FLAGS_TID(0) | IDMA_FLAG_DECOUPLE_RW);
            issued++;
        }
        while (!(idma_read_tr_count(0) >= 1)) { }
        idma_clear_tid(0);
        completed++;
    }
}
```

---

### 8.11 Sparsity and Zero Handling

iDMA does NOT support zero-skipping. All bytes in the specified range are transferred regardless of value. For sparsity-aware movement, use TDMA (zmask, exponent threshold pruning). iDMA can pre-clear accumulation buffers (INIT path) before TDMA writes sparse non-zero values.

---

### 8.12 Completion Tracking and IRQ

```
  Issue transfer with trid=N
       |
       v
  TID N in-flight: IDMA_STATUS[N] = 1
       |
       v
  Transfer completes
       |
       v
  IDMA_TR_COUNT[N]++
  If TR_COUNT[N] >= THRESHOLD[N] and THRESHOLD[N] != 0:
      o_idma_tiles_to_process_irq[N] = 1  -> PLIC -> hart trap handler
       |
       v
  SW writes IDMA_CLR[N] = 1
       |
       v
  IDMA_TR_COUNT[N] = 0, IRQ[N] deasserted
```

```c
// Polling mode
void wait_tid_poll(int tid) {
    while (idma_read_tr_count(tid) < 1) { asm volatile ("nop"); }
    idma_clear_tid(tid);
    asm volatile ("fence r,r");
}

// Interrupt mode (requires §7.4 PLIC setup)
void wait_tid_irq(int tid) {
    g_dma_done[tid] = 0;
    idma_set_threshold(tid, 1);
    plic_enable_idma_irq(get_hart_id(), tid);
    while (!g_dma_done[tid]) { asm volatile ("wfi"); }
    asm volatile ("fence r,r");
}

// Batch mode: fire IRQ after N completions
void setup_batch_irq(int tid, int batch_size) {
    idma_set_threshold(tid, batch_size);
    plic_enable_idma_irq(get_hart_id(), tid);
}
```

---

### 8.13 DMA + TDMA Pipeline (Overlap Compute and Data Load)

The most common performance pattern on Trinity N1B0 is overlapping DMA data loading with TDMA+FPU compute using a double-buffer scheme.

```
Cycle:  | Iter 0       | Iter 1       | Iter 2       | Iter 3       |
DMA:    | Load tile 0  | Load tile 1  | Load tile 2  | Load tile 3  |
        | into BUF_A   | into BUF_B   | into BUF_A   | into BUF_B   |
TDMA:   | (priming)    | Compute BUF_A| Compute BUF_B| Compute BUF_A|
```

```c
#define BUF_A  DMA_BUF_A_BASE
#define BUF_B  DMA_BUF_B_BASE

// buf_id: 0 = BUF_A, 1 = BUF_B
static inline uint64_t buf_addr(int buf_id) {
    return buf_id ? BUF_B : BUF_A;
}

void dma_tdma_pipeline(uint64_t *dram_tiles, int n_tiles) {
    // Prime: load first tile into BUF_A
    asm_dmsrc(dram_tiles[0]);
    asm_dmdst(BUF_A);
    asm_dmcpy(TILE_BYTES, FLAGS_TID(0) | IDMA_FLAG_DECOUPLE_RW);
    while (!(idma_read_tr_count(0) >= 1)) { }
    idma_clear_tid(0);
    asm volatile ("fence r,r");   // first tile ready

    for (int i = 1; i < n_tiles; i++) {
        int load_buf = i & 1;     // alternates BUF_B (1), BUF_A (0)
        int comp_buf = 1 - load_buf;

        // Start DMA load into idle buffer (non-blocking issue)
        asm_dmsrc(dram_tiles[i]);
        asm_dmdst(buf_addr(load_buf));
        asm_dmcpy(TILE_BYTES, FLAGS_TID(1) | IDMA_FLAG_DECOUPLE_RW);

        // TDMA compute on ready buffer (runs while DMA loads next tile)
        // UNPACR: unpack from L1 comp_buf into SRCA/SRCB registers
        // FPU: matrix multiply
        // PACR: pack result back to L1 destination
        tdma_process_tile(buf_addr(comp_buf));

        // Wait for DMA to finish before we use load_buf in next iteration
        while (!(idma_read_tr_count(1) >= 1)) { }
        idma_clear_tid(1);
        asm volatile ("fence r,r");   // DMA writes visible before TDMA reads
    }

    // Compute last tile
    tdma_process_tile(buf_addr((n_tiles - 1) & 1));
}
```

WARNING: The `fence r,r` between DMA completion and `tdma_process_tile()` is mandatory. TDMA reads from L1 SRAM; without the fence, TDMA may observe stale data from before the DMA write.

---

### 8.14 Multi-Tile DMA Coordination

For workloads spanning multiple tiles (e.g., all-reduce, tensor-parallel attention), tiles communicate by writing to each other's L1 via NoC PUT operations.

**NoC address construction:**
```c
// NoC address format: {y[5:0], x[5:0], local_addr[63:0]}
// In practice the NoC address is a 76-bit quantity; upper bits are y/x.
// For AXI address (56-bit gasket): see router_decode_HDD_v0.5.md §3
uint64_t make_noc_addr(int x, int y, uint64_t local_addr) {
    // Simplified: embed x/y into high bits of the 64-bit DMA address
    // Actual encoding is SoC-specific; this is a placeholder.
    return (((uint64_t)(y & 0x3F)) << 40) |
           (((uint64_t)(x & 0x3F)) << 34) |
           (local_addr & 0x3FFFFFFFFULL);
}
```

NOTE: The exact NoC address format depends on the ATT and router configuration. In practice, use ATT entries to map logical addresses to physical (x,y) coordinates rather than constructing NoC addresses directly. See §8.6.

**Send local data to a remote tile:**
```c
void tile_send_to_remote(int dst_x, int dst_y,
                         uint64_t src_l1_addr, uint64_t dst_l1_addr,
                         uint32_t nbytes, int trid) {
    // Program ATT for this destination (if not already programmed)
    att_program_remote_tile(trid, dst_x, dst_y, dst_l1_addr);

    asm volatile ("fence w,w");   // ensure src data visible before DMA
    asm_dmsrc(src_l1_addr);
    asm_dmdst(att_logical_addr(trid));  // ATT-mapped logical address for this entry
    asm_dmcpy(nbytes, FLAGS_TID(trid));

    while (!(idma_read_tr_count(trid) >= 1)) { }
    idma_clear_tid(trid);
}
```

**All-to-all: each tile sends its partial result to all other tiles (4x4 grid, Tensix tiles only):**
```c
void all_to_all_send(int my_x, int my_y,
                     uint64_t partial_result_addr, uint32_t result_bytes) {
    int trid = 0;

    for (int x = 0; x < 4; x++) {
        for (int y = 1; y <= 4; y++) {
            if (x == my_x && y == my_y) continue;   // skip self

            // Send to remote tile's designated receive buffer
            att_program_remote_tile(trid, x, y, L1_RECEIVE_BUF_OFFSET);

            asm volatile ("fence w,w");
            asm_dmsrc(partial_result_addr);
            asm_dmdst(att_logical_addr(trid));
            asm_dmcpy(result_bytes, FLAGS_TID(trid));

            if (++trid >= 32) trid = 0;
        }
    }

    // Wait for all sends to complete
    for (int t = 0; t < trid; t++) {
        while (!(idma_read_tr_count(t) >= 1)) { }
        idma_clear_tid(t);
    }
}
```

NOTE: Receiving tiles must barrier-synchronize to know when all remote sends have arrived. Use CLINT MSIP or a polling flag in shared memory (over NoC) to signal completion.

---

### 8.15 Error Detection and Recovery

**ECC/parity errors in L1:**
```c
void check_and_clear_l1_ecc(void) {
    volatile uint32_t *status = (uint32_t *)(CLUSTER_CTRL_BASE + 0x120);
    uint32_t s = *status;
    if (s) {
        log_error("L1 ECC error: status=0x%08x", s);
        *status = s;    // W1C: clear the bits
    }
}
```

**Bus errors per hart:**
```c
static const uint32_t bus_err_offsets[8] = {
    0x130, 0x138, 0x140, 0x148, 0x150, 0x158, 0x160, 0x168
};

void check_bus_errors(void) {
    for (int i = 0; i < 8; i++) {
        volatile uint32_t *reg =
            (uint32_t *)(CLUSTER_CTRL_BASE + bus_err_offsets[i]);
        uint32_t err = *reg;
        if (err) {
            log_error("Bus error hart %d: 0x%08x", i, err);
            *reg = err;   // W1C
        }
    }
}
```

**DMA watchdog (SW-implemented timeout):**
```c
#define DMA_TIMEOUT_US  10000   // 10 ms watchdog

int idma_transfer_with_timeout(uint64_t src, uint64_t dst,
                                uint32_t nbytes, int trid) {
    asm volatile ("fence w,w");
    asm_dmsrc(src);
    asm_dmdst(dst);
    asm_dmcpy(nbytes, FLAGS_TID(trid));

    uint64_t deadline = *CLINT_MTIME +
                        (uint64_t)DMA_TIMEOUT_US * (CLINT_FREQ_HZ / 1000000ULL);

    while (!(idma_read_tr_count(trid) >= 1)) {
        if (*CLINT_MTIME > deadline) {
            // Diagnose stall before giving up
            uint32_t vc_space = idma_read_vc_space(0);
            if (vc_space == 0) {
                // FIFO full: extend deadline and keep waiting
                deadline += (uint64_t)DMA_TIMEOUT_US * (CLINT_FREQ_HZ / 1000000ULL);
                continue;
            }
            // Hard stall
            log_error("DMA timeout: trid=%d status=0x%08x vc_space=%u",
                      trid, idma_read_status(), vc_space);
            idma_clear_tid(trid);
            return -1;
        }
    }
    idma_clear_tid(trid);
    asm volatile ("fence r,r");
    return 0;
}
```


---

## 9. Performance Guide

### 9.1 Clock Gating Configuration

Clock gating saves power but adds latency when the first transfer arrives after the clock has been gated off. Choose hysteresis based on the access pattern.

| Scenario | CLOCK_GATING.IDMA | HYST value | Notes |
|----------|-------------------|------------|-------|
| Continuous DMA (training loop) | 1 | 0x7F (max) | Clock stays on between bursts |
| Burst DMA (infrequent loads) | 1 | 0x20 (32 cycles) | Balance power vs wake latency |
| Bring-up / debug | 0 | — | Clock always on; no gating |
| Ultra-low-power idle | 1 | 0x00 | Gate immediately after activity |

```c
// Enable iDMA clock gating with 64-cycle hysteresis
volatile uint32_t *clk_gate = (uint32_t *)(CLUSTER_CTRL_BASE + 0x0CC);
volatile uint32_t *clk_hyst = (uint32_t *)(CLUSTER_CTRL_BASE + 0x0D0);
*clk_hyst  = 0x06;              // 2^6 = 64 cycles
*clk_gate |= (1u << 1);         // CLOCK_GATING.IDMA = 1
```

---

### 9.2 In-Flight Transaction Depth

| Stage | Capacity | Domain |
|-------|----------|--------|
| Frontend timing slice | 1 per client × 24 = 24 | core_clk |
| Frontend metadata FIFO | 42 entries | core_clk |
| CDC async payload FIFO | 8 entries | boundary |
| Per-backend metadata FIFO | 28 entries × 2 = 56 | gated_l1_clk |
| Total TIDs | 32 | — |

Effective pipeline depth per client: approximately 1–2 concurrent DMCPY calls before back-pressure. The CDC FIFO (8 entries) is the binding constraint for burst-issue scenarios. Issuing more than 8 descriptors in rapid succession (across all 24 clients combined) will cause DMCPY to stall.

---

### 9.3 Backend Selection

The backend type (`IDMA_BE_TYPE_AXI`) is a compile-time constant. In N1B0, verify with the chip configuration team which backend is present per tile.

| Backend | Target | Latency | Best for |
|---------|--------|---------|---------|
| OBI (`IDMA_BE_TYPE_AXI=0`) | Local L1 SRAM | 1–4 cycles | L1-to-L1 copies, zero-fill |
| AXI (`IDMA_BE_TYPE_AXI=1`) | DRAM via NOC2AXI | 50–200+ cycles | DRAM weight loading |

For DRAM-to-L1 transfers, always set `decouple_rw=1`. This allows the AXI read request to proceed ahead of the OBI write, pipeline-hiding the DRAM access latency.

---

### 9.4 2D Transfer Efficiency

The 2D legalizer expands `num_reps` inner transfers internally. This saves CPU overhead compared to issuing `num_reps` individual 1D DMCPY calls.

| Approach | CPU cycles | CDC FIFO entries consumed |
|----------|-----------|--------------------------|
| num_reps=128 single DMCPY | ~5 cycles (1 instruction) | 1 entry |
| 128 individual DMCPY calls | ~640 cycles (128 instructions) | 128 entries |

**Recommendation:** Use 2D mode whenever `num_reps >= 4`. The break-even is at approximately 2–3 repetitions.

**Stride alignment tip:** For best L1 bank performance, choose dst_stride values that are not exact powers of 2 times the L1 bank size. This distributes 2D writes across multiple L1 banks and reduces bank conflicts.

---

### 9.5 L1 Bandwidth Estimation

L1 SRAM in N1B0: 768 KB per tile, organized as 3072 macros × 128 bits (16 bytes) per macro.

iDMA OBI write bandwidth:
```
gated_l1_clk ~ noc_clk (500–800 MHz, platform-dependent)
OBI bus width = 128 bits = 16 bytes per cycle
Peak write BW per backend = 16 bytes × clock_freq
At 800 MHz: 12.8 GB/s per backend
Dual backends (no bank conflicts): up to 25.6 GB/s aggregate
```

Practical derating factors:
- L1 bank conflicts from strided 2D accesses: can reduce BW by 20–50%
- AXI backend DRAM latency: limits read BW to DRAM controller throughput
- NoC congestion (multi-tile PUT): reduces effective PUT bandwidth under load

---

### 9.6 DRAM Throughput Optimization

1. **Use burst mode (`deburst=0`, the default):** AXI burst allows the NOC2AXI bridge to issue multi-beat bursts to the DRAM controller. Single-beat mode (`deburst=1`) has significantly lower throughput and should only be used for debug.

2. **Align to 64-byte boundaries:** AXI burst efficiency is highest when source and destination DRAM addresses are 64-byte aligned. Misaligned transfers cause the legalizer to generate partial-beat accesses at the start and end.

3. **Use `decouple_rw=1` for all DRAM-to-L1 transfers:** DRAM read latency (100–200+ cycles) is much higher than OBI L1 write latency. Decoupled mode allows the read channel to prefetch ahead of the write channel, filling the latency gap.

4. **Stripe across DRAM SI channels:** Trinity N1B0 has four DRAM system interfaces (SI0–SI3) each at a different NoC-visible address range. If the data spans all 4 channels, issue 4 concurrent DMA transfers (one per SI, distinct TIDs) to maximize aggregate DRAM bandwidth.

```c
// Stripe a large load across 4 DRAM SI channels in parallel
#define DRAM_SI0  0x60000000ULL
#define DRAM_SI1  0x68000000ULL
#define DRAM_SI2  0x70000000ULL
#define DRAM_SI3  0x78000000ULL

void dma_striped_load_4ch(uint32_t total_bytes, uint64_t l1_dst) {
    const uint64_t si_bases[4] = {DRAM_SI0, DRAM_SI1, DRAM_SI2, DRAM_SI3};
    uint32_t chunk = total_bytes / 4;  // each channel carries 1/4

    for (int ch = 0; ch < 4; ch++) {
        idma_set_threshold(ch, 1);
        asm_dmsrc(si_bases[ch]);
        asm_dmdst(l1_dst + (uint64_t)ch * chunk);
        asm_dmcpy(chunk, (uint64_t)ch | IDMA_FLAG_DECOUPLE_RW);
    }

    for (int ch = 0; ch < 4; ch++) {
        while (!(idma_read_tr_count(ch) >= 1)) { }
        idma_clear_tid(ch);
    }
    asm volatile ("fence r,r");
}
```

NOTE: SI channel striping assumes that the DRAM allocation has been arranged to place consecutive 128-MB-aligned chunks on different SI channels. Confirm with the memory allocation layer.

---

### 9.7 Latency-Hiding Patterns

**Technique 1: Double-buffer prefetch (see §8.13 for full code)**

Issue DMA for the next tile before compute on the current tile finishes. With two backends, DMA and TDMA can overlap by one full tile.

```
Time: -->
DMA:   [Load tile 0][Load tile 1][Load tile 2][Load tile 3]
TDMA:              [Comp tile 0][Comp tile 1][Comp tile 2]
```

**Technique 2: WFI between polls (power-efficient wait)**

Instead of spinning in a tight polling loop (which wastes issue bandwidth on L1 instruction fetches and power), use `wfi` to sleep between IRQ wake-ups.

```c
volatile int g_dma_done[32] = {0};

// Issue DMA with IRQ enabled
void idma_issue_with_irq(uint64_t src, uint64_t dst, uint32_t len, int tid) {
    g_dma_done[tid] = 0;
    idma_set_threshold(tid, 1);
    plic_enable_idma_irq(get_hart_id(), tid);

    asm volatile ("fence w,w");
    asm_dmsrc(src);
    asm_dmdst(dst);
    asm_dmcpy(len, FLAGS_TID(tid));
}

// Hart sleeps until IRQ fires
void idma_wait_irq(int tid) {
    while (!g_dma_done[tid]) {
        asm volatile ("wfi");   // sleep until interrupt; no polling overhead
    }
    asm volatile ("fence r,r");
}

// In the IRQ handler:
// g_dma_done[tid] = 1; idma_clear_tid(tid);
```

**Technique 3: Dual-hart prefetch (hart 0 prefetches, hart 1 computes)**

Assign hart 0 exclusively to DMA operations and harts 1–7 exclusively to compute. This eliminates the need for double-buffering synchronization within a single hart and allows sustained overlap.

```c
// Hart 0: dedicated DMA prefetch task
void hart0_dma_task(void) {
    for (int tile = 0; tile < N_TILES; tile++) {
        int buf = tile % N_BUFS;
        while (!g_buf_consumed[buf]) { }   // wait for compute to finish
        g_buf_consumed[buf] = 0;

        asm_dmsrc(dram_tiles[tile]);
        asm_dmdst(buf_addr(buf));
        asm_dmcpy(TILE_BYTES, FLAGS_TID(0));
        while (!(idma_read_tr_count(0) >= 1)) { }
        idma_clear_tid(0);

        asm volatile ("fence w,w");
        g_buf_ready[buf] = 1;
        wake_hart(1);   // optional: wake compute harts via CLINT
    }
}
```

---

## 10. Debugging Guide

### 10.1 DMA Stall Diagnosis

When a DMA transfer does not complete, follow this checklist:

**Step 1: Confirm the TID is still in-flight**
```c
uint32_t status = idma_read_status();   // IDMA_STATUS bitmap
if (!(status & (1u << trid))) {
    // TID completed but IDMA_TR_COUNT was not checked; may have wrapped
    // Check IDMA_TR_COUNT[trid] directly
}
```

**Step 2: Check FIFO occupancy**
```c
uint32_t vc0 = idma_read_vc_space(0);
uint32_t vc1 = idma_read_vc_space(1);
// If vc0 == 0 or vc1 == 0: backend FIFO is full
// Previous TIDs may not have been cleared; call idma_clear_tid() for completed TIDs
```

**Step 3: Verify clock gating is not starving the backend**
```c
volatile uint32_t *clk = (uint32_t *)(CLUSTER_CTRL_BASE + 0x0CC);
// If (*clk & 0x82) != 0 (IDMA or L1_FLEX_CLIENT_IDMA gating enabled):
// Verify CLOCK_GATING_HYST > 0
// Temporarily disable gating for diagnosis:
*clk &= ~0x82u;
```

**Step 4: Try disabling clock gating and retrying**
```c
CLOCK_GATING_REG &= ~(1u << 1);   // always-on for debug
// Retry the DMA and observe whether it completes
```

**Step 5: Check backend type vs address range**
- OBI backend (`IDMA_BE_TYPE_AXI=0`): handles L1 addresses (`0x0000_xxxx`)
- AXI backend (`IDMA_BE_TYPE_AXI=1`): handles DRAM addresses (`0x60xx_xxxx` to `0x7Fxx_xxxx`)
- Sending an OBI-backend descriptor to a DRAM address will likely stall permanently

**Step 6: Read WB_PC registers to see if the issuing hart is live**
```c
volatile uint32_t *wb_pc = (uint32_t *)(CLUSTER_CTRL_BASE + 0x0D8);
// If WB_PC is unchanging, the hart may be stalled on DMCPY back-pressure or in a fault
```

---

### 10.2 Data Corruption Checklist

When DMA completes but data in the destination is incorrect:

1. **Missing `fence w,w` before DMA:** Source data may not have been flushed from the CPU store buffer to L1 SRAM before the DMA read. Always insert `fence w,w` before the first DMSRC/DMCPY instruction.

2. **Missing `fence r,r` after DMA:** The CPU may read stale cached values from before the DMA write. Always insert `fence r,r` after polling TID completion before reading the destination.

3. **Buffer overlap:** Verify that source and destination L1 addresses do not overlap. An overlapping 1D copy has undefined behavior (write may overwrite unread source bytes).

4. **2D stride miscalculation:** Verify `src_stride >= length` (otherwise source rows overlap). Verify `dst_stride >= length` (otherwise destination rows overlap). Common mistake: confusing element stride with byte stride.

5. **DFC format mismatch:** The source format in the DFC descriptor must match the actual in-memory format of the source data. Specifying `DFC_FLOAT32` for data that is actually BF16 will produce garbage output.

6. **ATT entry stale:** If ATT was reprogrammed between two DMA transfers (to point to a different tile), verify that the first DMA has completed before reprogramming. In-flight transfers use the ATT at issue time; ATT reads are not cached.

7. **Partial MX block:** MX format transfers must be a multiple of 8 elements. A non-multiple transfer will produce incorrect block exponents for the last partial block.

---

### 10.3 IRQ Not Firing

When the iDMA completion IRQ is expected but never arrives at the hart:

1. **IDMA_THRESHOLD[TID] is zero:** A threshold of 0 disables IRQ generation for that TID. Set `IDMA_THRESHOLD[TID] = 1` (or the desired batch size) before issuing the DMA.

2. **PLIC source priority is zero:** A PLIC source with priority 0 is disabled and will never fire. Set `PLIC_PRIORITY(irq) = 1` or higher.

3. **PLIC enable not set for this hart's context:** Verify that the correct bit is set in the PLIC enable register for M-mode context `hart_id * 2`.

4. **`mie.MEIE` not set:** Bit 11 of the `mie` CSR must be set. Check: `csrr t0, mie; andi t0, t0, 2048; beqz t0, not_set`.

5. **`mstatus.MIE` not set:** Global machine interrupt enable (bit 3 of `mstatus`) must be set. Check: `csrr t0, mstatus; andi t0, t0, 8; beqz t0, not_set`.

6. **PLIC threshold too high:** If `PLIC_THRESHOLD(context) > PLIC_PRIORITY(irq)`, the IRQ will be masked by the PLIC. Set threshold to 0 to accept all non-zero priority IRQs.

7. **IRQ base mapping mismatch:** Verify `IDMA_IRQ_BASE` matches the actual PLIC source assignment for the iDMA IRQ wires. This is an SoC integration detail.

---

### 10.4 Clock Gating Issues

**Symptom: First DMA after idle takes much longer than expected**
- Cause: Clock gated off; DMA must wait for clock to re-enable
- Fix: Increase CLOCK_GATING_HYST (write larger value to 0x0D0) so the clock stays on longer after activity

**Symptom: DMA stalls immediately after issue**
- Check: Is `i_busy` from the backends properly connected to `tt_clk_gater`?
- Debug: Disable gating (`CLOCK_GATING.IDMA=0`) and retry. If DMA completes, clock gating was the problem.
- Check: Is `CLOCK_GATING.L1_FLEX_CLIENT_IDMA` (bit 7) also set? Both must be properly configured.

**Symptom: Clock gating not saving power as expected**
- Check: Is HYST set too high? With HYST=0x7F (maximum), clock stays on for 128 cycles after last activity. For workloads with long idle periods between DMA bursts, use a lower HYST value.

**Aggressive gating configuration for power-sensitive idle:**
```c
CLOCK_GATING_HYST  = 0x00;   // 2^0 = 1 cycle: gate immediately after last activity
CLOCK_GATING_REG  |= (1u << 1) | (1u << 7);
```

---

### 10.5 Bus Error Handling

The `BUS_ERROR_UNIT_DATA_Cx` registers (offsets 0x130–0x168) record bus errors per hart. These are set when a hart accesses an illegal address or when the L1 protection region check fails.

**L1 region protection:**
- `L1_ACCESSIBLE_REGION` (0x1DC): configures the base address and size of the protected L1 region
- `L1_REGION_ERROR` (0x1E0): captures the address of the first access violation

```c
void handle_bus_errors(void) {
    // Check per-hart bus errors
    check_bus_errors();   // clears W1C registers

    // Check L1 region violation
    volatile uint32_t *region_err = (uint32_t *)(CLUSTER_CTRL_BASE + 0x1E0);
    uint32_t viol = *region_err;
    if (viol) {
        log_error("L1 region violation: address=0x%08x", viol);
        *region_err = viol;   // W1C
        // The violating hart may need to be reset and restarted
    }
}
```

**Common causes:**
- Hart access to an address outside the L1 region configured in `L1_ACCESSIBLE_REGION`
- DMA descriptor pointing to an address that falls in the protected SFR range
- NoC PUT arriving at an out-of-range L1 address

---

### 10.6 RISC-V Hart Debug

**Halt a hart via DEBUG_DMACTIVE:**
```c
// DEBUG_DMACTIVE (0x1C0): each bit controls one hart's debug-module active state
// Writing 1 to bit N makes hart N active in the debug module (halted under JTAG control)
volatile uint32_t *dmactive = (uint32_t *)(CLUSTER_CTRL_BASE + 0x1C0);
*dmactive = (1u << hart_id);   // halt hart for debug
// Poll DEBUG_DMACTIVEACK (0x1C4) until hart acknowledges halt
volatile uint32_t *dmack = (uint32_t *)(CLUSTER_CTRL_BASE + 0x1C4);
while (!(*dmack & (1u << hart_id))) { }
```

**Read hart PC without halting:** Poll `WB_PC_REG_Cx` registers (0x0D8–0x110). These capture the most recent writeback PC and are updated continuously without halting the hart. Useful for detecting infinite loops.

```c
// Detect hart hang: check if PC is stuck
volatile uint32_t *wb_pc[8] = {
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x0D8),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x0E0),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x0E8),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x0F0),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x0F8),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x100),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x108),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x110),
};

void check_hart_liveness(void) {
    static uint32_t prev_pc[8] = {0};
    static int stall_count[8] = {0};

    for (int i = 0; i < 8; i++) {
        uint32_t pc = *wb_pc[i];
        if (pc == prev_pc[i]) {
            if (++stall_count[i] > 1000) {
                log_error("Hart %d may be hung at PC 0x%08x", i, pc);
            }
        } else {
            stall_count[i] = 0;
            prev_pc[i] = pc;
        }
    }
}
```

**OpenOCD / GDB connection (via JTAG):**
```
# Connect to JTAG debug adapter
openocd -f interface/jlink.cfg -f target/trinity_n1b0.cfg

# In GDB: attach to hart 0
(gdb) target remote :3333
(gdb) monitor halt
(gdb) info registers
(gdb) x/10i $pc          # disassemble at current PC

# Read cluster_ctrl_apb registers from GDB
(gdb) x/1wx 0x03000000   # RESET_VECTOR_0
(gdb) x/1wx 0x030001C0   # DEBUG_DMACTIVE

# Read iDMA status
(gdb) x/1wx <idma_apb_base>   # IDMA_STATUS

# Force a hart reset and set new reset vector
(gdb) set *((int*)0x03000000) = <new_pc_word_addr>
(gdb) set *((int*)0x030001C0) = 0   # assert reset
(gdb) set *((int*)0x030001C0) = 1   # deassert reset (hart 0)
```

NOTE: IJTAG scan chain access is not available in N1B0 by default (`INCLUDE_TENSIX_NEO_IJTAG_NETWORK` is not defined). Standard RISC-V JTAG via the debug module is the primary on-chip debug path.

---

## 11. Appendix A: DFC Format Table

The following format codes are defined in `tt_idma_dfc_pkg.sv`. All conversions between any two formats in this table are supported by `tt_idma_dfc_wrapper`.

| Code | Format Name | Exponent Bits | Mantissa Bits | Total Bits | Notes |
|------|-------------|---------------|---------------|------------|-------|
| `DFC_FLOAT32` | IEEE 754 FP32 | 8 | 23 | 32 | Standard single precision |
| `DFC_FLOAT16` | IEEE 754 FP16 | 5 | 10 | 16 | Standard half precision (E5M10) |
| `DFC_FLOAT16_B` | BFloat16 | 8 | 7 | 16 | Google BF16 (E8M7) |
| `DFC_TF32` | TensorFloat-32 | 8 | 10 | 19 | NVIDIA TF32 (E8M10) |
| `DFC_FP8R` | FP8 E5M2 | 5 | 2 | 8 | OCP FP8, round mode |
| `DFC_FP8P` | FP8 E4M3 | 4 | 3 | 8 | OCP FP8, packed mode |
| `DFC_MXFP8R` | MX FP8 E5M2 | 5 | 2 | 8 | OCP MX, block shared exp |
| `DFC_MXFP8P` | MX FP8 E4M3 | 4 | 3 | 8 | OCP MX, block shared exp |
| `DFC_MXFP6R` | MX FP6 E3M2 | 3 | 2 | 6 | OCP MX FP6 |
| `DFC_MXFP6P` | MX FP6 E2M3 | 2 | 3 | 6 | OCP MX FP6 |
| `DFC_MXFP4` | MX FP4 E2M1 | 2 | 1 | 4 | OCP MX FP4 |
| `DFC_INT8` | INT8 | — | — | 8 | Signed 8-bit integer |
| `DFC_INT16` | INT16 | — | — | 16 | Signed 16-bit integer |
| `DFC_INT32` | INT32 | — | — | 32 | Signed 32-bit integer |
| `DFC_MXINT8` | MX INT8 | — | — | 8 | Microscaling INT8 (block exp) |
| `DFC_MXINT4` | MX INT4 | — | — | 4 | Microscaling INT4 |
| `DFC_MXINT2` | MX INT2 | — | — | 2 | Microscaling INT2 |

**Configuration parameters:**
- `WORD_WIDTH = 8` bits (element granularity in the converter)
- `MX_BLOCK_SIZE = 8` elements per microscaling block

**MX format note:** Microscaling (MX) formats use a shared block exponent for every block of 8 elements. The block exponent is stored as metadata alongside the mantissa elements. When converting MX to floating-point, the DFC reads the block exponent and applies it. When converting floating-point to MX, the DFC computes the block exponent from the max exponent in each group of 8 elements.

**Stochastic rounding:** Available for all narrowing conversions (e.g., FP32 to FP8, INT16 to INT8). Enabled via `stoch_round=1` in the DFC descriptor field. Uses a hardware LFSR seeded per block.

**Common conversion pairs and byte ratios:**

| Source | Destination | Byte Ratio | Use Case |
|--------|-------------|------------|---------|
| FLOAT32 | FLOAT16_B | 2:1 (src:dst) | FP32 weights to BF16 storage |
| FLOAT32 | FP8P | 4:1 | FP32 to compressed FP8 |
| FLOAT16 | INT8 | 2:1 | FP16 activations to INT8 |
| INT16 | INT8 | 2:1 | INT16 activations to INT8 |
| MXFP8R | FLOAT16 | 1:2 (expands) | Decompress MX to FP16 |
| INT8 | FLOAT32 | 1:4 (expands) | INT8 to FP32 for accumulation |

NOTE: For expanding conversions (destination wider than source), the destination buffer must be larger. The legalizer accounts for this in byte count calculations.

---

## 12. Appendix B: RISC-V iDMA Instruction Reference

The iDMA engine exposes a RISC-V ROCC (Rocket Custom Co-processor) interface using the `CUSTOM_1` opcode (`0x2B`) with `funct7=0x2B`. CPU harts 0–7 each have a dedicated client port (clients 0–7) to the iDMA frontend.

### Instruction Set

| Mnemonic | funct3 | Operands | Description |
|----------|--------|----------|-------------|
| `DMSRC` | 0x0 | rs1=src_addr | Set DMA source address (64-bit on RV64). Shadow register write — not committed until DMCPY. |
| `DMDST` | 0x1 | rs1=dst_addr | Set DMA destination address (64-bit on RV64). Shadow register write. |
| `DMCPYI` | 0x2 | rs1=length, imm12=flags | Immediate-mode copy: length in rs1, flags in 12-bit immediate. Commits shadow registers and issues transfer. |
| `DMCPY` | 0x3 | rs1=length, rs2=flags | Register-mode copy: length in rs1, flags in rs2. Commits and issues transfer. |
| `DMSTATI` | 0x4 | rd=result, imm12=field | Poll status: reads iDMA status field (immediate-encoded) into rd. Does not stall. |
| `DMSTAT` | 0x5 | rd=result, rs1=field | Poll status: reads iDMA status field (register-encoded) into rd. Does not stall. |
| `DMSTR` | 0x6 | rs1=src_stride, rs2=dst_stride | Set outer-dimension strides for 2D mode. Must be called before DMCPY. |
| `DMREP` | 0x7 | rs1=num_reps | Set outer loop repetition count for 2D mode. Must be called before DMCPY. |

### Flags Field Encoding (DMCPY rs2 / DMCPYI imm12)

| Bits | Field | Description |
|------|-------|-------------|
| [4:0] | trid | Transaction ID (0–31) |
| [6:5] | vc | Virtual channel selector (0–3) |
| [7] | decouple_rw | 1 = decouple read and write phases (recommended for DRAM reads) |
| [8] | deburst | 1 = disable AXI burst mode (single-beat only; debug use) |
| [9] | serialize | 1 = force in-order serialization across transfers |
| [11:10] | (reserved) | Write 0 |

### DMSTAT / DMSTATI Status Fields

| Field Value | Meaning | Description |
|-------------|---------|-------------|
| 0x0 | DMSTAT_BUSY | 1 if any transfer from this hart is in-flight |
| 0x1 | DMSTAT_READY | 1 if frontend can accept a new descriptor (FIFO has space) |
| 0x2 | DMSTAT_STATUS | IDMA_STATUS[31:0] — in-flight TID bitmap |
| 0x3 | DMSTAT_VC_SPACE_0 | Available slots in backend 0 FIFO |
| 0x4 | DMSTAT_VC_SPACE_1 | Available slots in backend 1 FIFO |
| 0x10+N | DMSTAT_TR_COUNT_N | IDMA_TR_COUNT[N] for TID N (N = 0–31) |

### Assembly Macro Reference

```c
// All ROCC instructions use CUSTOM_1 opcode (0x2B)
// Encoding: .insn r OPCODE, funct3, funct7, rd, rs1, rs2

static inline void asm_dmsrc(uint64_t src) {
    asm volatile (".insn r 0x2B, 0, 0, zero, %0, zero" :: "r"(src));
}

static inline void asm_dmdst(uint64_t dst) {
    asm volatile (".insn r 0x2B, 1, 0, zero, %0, zero" :: "r"(dst));
}

static inline void asm_dmstr(uint64_t src_stride, uint64_t dst_stride) {
    asm volatile (".insn r 0x2B, 6, 0, zero, %0, %1"
                  :: "r"(src_stride), "r"(dst_stride));
}

static inline void asm_dmrep(uint64_t num_reps) {
    asm volatile (".insn r 0x2B, 7, 0, zero, %0, zero" :: "r"(num_reps));
}

static inline void asm_dmcpy(uint64_t length, uint64_t flags) {
    asm volatile (".insn r 0x2B, 3, 0, zero, %0, %1"
                  :: "r"(length), "r"(flags));
}

static inline uint64_t asm_dmstat(void) {
    uint64_t result;
    asm volatile (".insn r 0x2B, 4, 0, %0, zero, zero" : "=r"(result));
    return result;
}

static inline uint64_t asm_dmstati(uint64_t field) {
    uint64_t result;
    asm volatile (".insn r 0x2B, 4, 0, %0, zero, %1"
                  : "=r"(result) : "r"(field));
    return result;
}

// Convenience flags macros
#define FLAGS_TID(n)           ((uint64_t)((n) & 0x1F))
#define FLAGS_VC(n)            ((uint64_t)(((n) & 0x3) << 5))
#define IDMA_FLAG_DECOUPLE_RW  ((uint64_t)(1u << 7))
#define IDMA_FLAG_DEBURST      ((uint64_t)(1u << 8))
#define IDMA_FLAG_SERIALIZE    ((uint64_t)(1u << 9))

// Full 2D DMA helper
void dma_2d(uint64_t src, uint64_t dst,
            uint32_t length, uint32_t num_reps,
            uint64_t src_stride, uint64_t dst_stride,
            int trid, int vc)
{
    uint64_t flags = FLAGS_TID(trid) | FLAGS_VC(vc);
    asm volatile ("fence w,w");
    asm_dmsrc(src);
    asm_dmdst(dst);
    asm_dmstr(src_stride, dst_stride);
    asm_dmrep((uint64_t)num_reps);
    asm_dmcpy((uint64_t)length, flags);
}
```

### Instruction Ordering Notes

1. `DMSRC`, `DMDST`, `DMSTR`, `DMREP` write per-hart shadow registers in the iDMA frontend. They are not committed to the descriptor queue until `DMCPY` is issued.
2. `DMCPY` is the atomic commit: it captures all shadow registers and enqueues the complete descriptor.
3. Multiple harts may issue DMCPY concurrently. The WRR arbiter handles conflicts without deadlock.
4. `DMSTAT`/`DMSTATI` returns a snapshot of the current status and does not stall the CPU hart regardless of FIFO state.
5. `DMCPY` stalls the issuing hart if `o_idma_ready[client_id] = 0` (FIFO full). No explicit polling is required; the stall is transparent to firmware but counts against the hart's effective IPC.

---

## 13. Appendix C: Address Map Quick Reference

This appendix provides a consolidated address reference for all registers and memory regions relevant to iDMA and the RISC-V CPU complex on Trinity N1B0.

### Tile-Local APB Address Space

```
Subsystem                      | Base Offset    | Size     | Notes
-------------------------------|----------------|----------|--------------------------
Cluster CPU control            | 0x03000000     | 0x1E4    | cluster_ctrl_apb
L1 SRAM slave APB              | 0x03800000     | varies   | t6l1_slv_apb
Cache controller               | 0x04010000     | varies   | t6l1_slv_apb sub-range
iDMA APB registers             | TBD            | ~0x200   | idma_apb (confirm w/ RTL)
ATT (NoC address translation)  | 0x02010000     | 0x3000   | noc_att; 12 KB
Overlay internal CSRs          | TBD            | varies   | overlay_mst_apb
SMN ring outbound              | TBD            | varies   | smn_mst_apb
EDC ring outbound              | TBD            | varies   | edc_mst_apb
PLL / PVT sensors              | TBD            | varies   | t6_pll_pvt_slv
```

### Cluster Control Register Quick Reference (0x0300_0000 base)

```
Offset  | Register              | Access | Key Use
--------|-----------------------|--------|--------------------------------
0x000   | RESET_VECTOR_0        | RW     | Hart 0 reset vector (word addr)
0x008   | RESET_VECTOR_1        | RW     | Hart 1 reset vector
...     | RESET_VECTOR_2..7     | RW     | Harts 2–7 reset vectors
0x0CC   | CLOCK_GATING          | RW     | Per-unit clock gate enables
0x0D0   | CLOCK_GATING_HYST     | RW     | Hysteresis count [6:0]
0x0D8   | WB_PC_REG_C0          | RO     | Hart 0 writeback PC (live)
...     | WB_PC_REG_C1..7       | RO     | Harts 1–7 writeback PCs
0x11C   | ECC_PARITY_CONTROL    | RW     | ECC enable for L1 SRAM
0x120   | ECC_PARITY_STATUS     | RO/W1C | ECC error status flags
0x130   | BUS_ERROR_UNIT_DATA_C0| RO/W1C | Bus error for hart 0
...     | BUS_ERROR_UNIT_DATA_C1..7 | RO/W1C | Bus errors for harts 1–7
0x1C0   | DEBUG_DMACTIVE        | RW     | Debug module hart activation
0x1C4   | DEBUG_DMACTIVEACK     | RO     | Debug module hart ack
0x1DC   | L1_ACCESSIBLE_REGION  | RW     | L1 protection region config
0x1E0   | L1_REGION_ERROR       | RO     | L1 access violation address
```

### System Memory Map (NoC-Viewable)

```
Address Range                 | Size    | Description
------------------------------|---------|------------------------------------------
0x0000_0000 – 0x000B_FFFF    | 768 KB  | Local tile L1 SRAM (N1B0 per tile)
0x0200_0000 – 0x0200_3FFF    | 16 KB   | CLINT (platform-specific base)
0x0300_0000 – 0x0300_01E3    | 484 B   | cluster_ctrl_apb
0x0201_0000 – 0x0201_2FFF    | 12 KB   | ATT (NoC address translation table)
0x0C00_0000 – 0x0FFF_FFFF    | 64 MB   | PLIC (platform-specific base)
0x6000_0000 – 0x67FF_FFFF    | 128 MB  | DRAM SI0 (via NOC2AXI at X=0,Y=0)
0x6800_0000 – 0x6FFF_FFFF    | 128 MB  | DRAM SI1 (via NOC2AXI at X=1,Y=0)
0x7000_0000 – 0x77FF_FFFF    | 128 MB  | DRAM SI2 (via NOC2AXI at X=2,Y=0)
0x7800_0000 – 0x7FFF_FFFF    | 128 MB  | DRAM SI3 (via NOC2AXI at X=3,Y=0)
```

NOTE: CLINT and PLIC base addresses are platform-specific and must be verified against the SoC integration team's address map. The values 0x0200_0000 (CLINT) and 0x0C00_0000 (PLIC) are representative placeholders based on standard RISC-V platform conventions.

### RISC-V Platform Register Quick Reference

```
CLINT registers (base 0x0200_0000):
  MSIP[N]     : base + 0x0000 + N*4    (RW, 1-bit per hart, N=0..7)
  MTIMECMP[N] : base + 0x4000 + N*8   (RW, 64-bit per hart)
  MTIME       : base + 0xBFF8          (RO, 64-bit, free-running)

PLIC registers (base 0x0C00_0000):
  Priority[I] : base + I*4             (RW, per IRQ source I)
  Pending[I]  : base + 0x1000 + I/32  (RO bitmap)
  Enable[C,I] : base + 0x2000 + C*0x80 + (I/32)*4  (RW bitmap, context C)
  Threshold[C]: base + 0x200000 + C*0x1000          (RW)
  Claim[C]    : base + 0x200004 + C*0x1000          (RW)
  M-mode context C = hart_id * 2
```

---

## 14. Appendix D: SW Driver Template

This appendix provides a complete, production-quality C driver template for the Trinity N1B0 iDMA engine. It is intended as a starting point for firmware writers; all TBD addresses must be confirmed against the SoC integration address map.

### idma_driver.h

```c
/**
 * idma_driver.h -- Trinity N1B0 iDMA SW driver
 *
 * Target: RISC-V RV64GC (hart firmware running on Trinity N1B0 Tensix tile)
 * Dependencies: clint.h (for MTIME), plic.h (for IRQ setup)
 *
 * Usage:
 *   1. Call idma_init() once at tile boot.
 *   2. Use idma_memcpy_1d() / idma_memcpy_2d() for common transfers.
 *   3. Use idma_transfer() for full-control descriptor issue.
 *   4. Use idma_wait() or idma_wait_irq() for completion.
 */

#ifndef IDMA_DRIVER_H
#define IDMA_DRIVER_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* -----------------------------------------------------------------------
 * Constants
 * --------------------------------------------------------------------- */

#define IDMA_NUM_TIDS       32      /* TID space: 0..31 */
#define IDMA_NUM_CLIENTS    24      /* total client slots */
#define IDMA_TID_NONE       0xFF    /* sentinel: no TID assigned */
#define IDMA_MAX_XFER_BYTES (4 * 1024 * 1024)   /* 4 MB: IDMA_TRANSFER_LENGTH_WIDTH=22 */

/* -----------------------------------------------------------------------
 * Transfer flags (for idma_xfer_t.flags and asm_dmcpy())
 * --------------------------------------------------------------------- */

#define IDMA_FLAG_TID(n)       ((uint64_t)((n) & 0x1F))
#define IDMA_FLAG_VC(n)        ((uint64_t)(((n) & 0x3) << 5))
#define IDMA_FLAG_DECOUPLE_RW  ((uint64_t)(1u << 7))
#define IDMA_FLAG_DEBURST      ((uint64_t)(1u << 8))
#define IDMA_FLAG_SERIALIZE    ((uint64_t)(1u << 9))

/* -----------------------------------------------------------------------
 * Transfer descriptor
 * --------------------------------------------------------------------- */

typedef struct {
    uint64_t src_addr;      /* source byte address (L1 or DRAM) */
    uint64_t dst_addr;      /* destination byte address (L1 or NoC) */
    uint32_t length;        /* bytes per inner transfer (1D size) */
    uint32_t num_reps;      /* outer loop count (1 = 1D, >1 = 2D) */
    uint64_t src_stride;    /* bytes between source rows (2D mode) */
    uint64_t dst_stride;    /* bytes between destination rows (2D mode) */
    uint64_t flags;         /* IDMA_FLAG_* bitmask; embed TID with IDMA_FLAG_TID(n) */
} idma_xfer_t;

/* -----------------------------------------------------------------------
 * Return codes
 * --------------------------------------------------------------------- */

#define IDMA_OK         0
#define IDMA_ETIMEOUT  (-1)
#define IDMA_EINVAL    (-2)
#define IDMA_EBUSY     (-3)

/* -----------------------------------------------------------------------
 * Driver API
 * --------------------------------------------------------------------- */

/**
 * idma_init() -- Initialize iDMA engine. Call once at tile boot before
 * any transfer. Disables clock gating, clears all TIDs, then re-enables
 * clock gating with 64-cycle hysteresis.
 */
void idma_init(void);

/**
 * idma_transfer() -- Issue a DMA transfer (non-blocking).
 * Returns IDMA_OK immediately after issuing. May stall the calling hart
 * if the frontend FIFO is full (back-pressure via ROCC).
 * @param xfer   Transfer descriptor. flags field must include IDMA_FLAG_TID(n).
 * @param trid   Transaction ID (0..31). Must match IDMA_FLAG_TID() in xfer->flags.
 * Returns IDMA_OK on success, IDMA_EINVAL if trid is out of range.
 */
int idma_transfer(const idma_xfer_t *xfer, int trid);

/**
 * idma_wait() -- Block until TID completes or timeout expires.
 * Inserts fence r,r after completion.
 * @param trid       Transaction ID to wait for.
 * @param timeout_us Timeout in microseconds. 0 = wait forever.
 * Returns IDMA_OK on completion, IDMA_ETIMEOUT if timeout expired.
 */
int idma_wait(int trid, uint32_t timeout_us);

/**
 * idma_wait_irq() -- Wait for TID completion using WFI + PLIC IRQ.
 * More power-efficient than polling. Requires prior idma_irq_setup().
 * @param trid Transaction ID to wait for.
 */
void idma_wait_irq(int trid);

/**
 * idma_poll() -- Non-blocking completion check.
 * Returns 1 if TID has completed, 0 if still in-flight.
 */
int idma_poll(int trid);

/**
 * idma_clear() -- Clear TID completion counter and deassert IRQ.
 * Must be called after each successful idma_wait() / idma_poll().
 */
void idma_clear(int trid);

/**
 * idma_status() -- Return IDMA_STATUS bitmap (bit N = TID N in-flight).
 */
uint32_t idma_status(void);

/**
 * idma_set_threshold() -- Set completion IRQ threshold for a TID.
 * IRQ fires when IDMA_TR_COUNT[trid] >= threshold. 0 = disabled.
 */
void idma_set_threshold(int trid, uint32_t threshold);

/**
 * idma_irq_setup() -- Configure PLIC to deliver iDMA IRQ for a TID
 * to the calling hart. Call before idma_wait_irq().
 */
void idma_irq_setup(int trid);

/* -----------------------------------------------------------------------
 * Convenience wrappers
 * --------------------------------------------------------------------- */

/** 1D memcpy: copy `bytes` from src to dst. Blocks until complete. */
int idma_memcpy_1d(uint64_t src, uint64_t dst, uint32_t bytes, int trid);

/** 2D memcpy: copy `n_rows` rows of `row_bytes` each, with independent strides. */
int idma_memcpy_2d(uint64_t src, uint64_t dst,
                   uint32_t row_bytes, uint32_t n_rows,
                   uint64_t src_stride, uint64_t dst_stride,
                   int trid);

/** Zero-fill: fill `bytes` of dst with zeros (INIT path, no source read). */
int idma_zero_fill(uint64_t dst, uint32_t bytes, int trid);

/** DRAM-to-L1: load from DRAM with decouple_rw=1 (recommended for all DRAM loads). */
int idma_dram_to_l1(uint64_t dram_src, uint64_t l1_dst,
                    uint32_t bytes, int trid);

#ifdef __cplusplus
}
#endif

#endif /* IDMA_DRIVER_H */
```

### idma_driver.c

```c
/**
 * idma_driver.c -- Trinity N1B0 iDMA SW driver implementation
 */

#include "idma_driver.h"

/* -----------------------------------------------------------------------
 * Hardware address definitions (confirm with SoC integration address map)
 * --------------------------------------------------------------------- */

#define CLUSTER_CTRL_BASE    0x03000000UL
#define CLOCK_GATING_REG     (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x0CC))
#define CLOCK_GATING_HYST_R  (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x0D0))
#define ECC_CTRL_REG         (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x11C))

/* iDMA APB base: TBD; replace with actual per-tile address */
#define IDMA_APB_BASE        0x00000000UL  /* PLACEHOLDER */
#define IDMA_STATUS_REG      (*(volatile uint32_t *)(IDMA_APB_BASE + 0x00))
#define IDMA_VC_SPACE_0      (*(volatile uint32_t *)(IDMA_APB_BASE + 0x04))
#define IDMA_VC_SPACE_1      (*(volatile uint32_t *)(IDMA_APB_BASE + 0x08))

/* Per-TID registers (indexed arrays — layout TBD) */
static volatile uint32_t * const IDMA_TR_COUNT  = (volatile uint32_t *)(IDMA_APB_BASE + 0x80);
static volatile uint32_t * const IDMA_THRESHOLD = (volatile uint32_t *)(IDMA_APB_BASE + 0xC0);
static volatile uint32_t * const IDMA_CLR       = (volatile uint32_t *)(IDMA_APB_BASE + 0x100);

/* CLINT for timeouts */
#define CLINT_MTIME          (*(volatile uint64_t *)(0x02000000UL + 0xBFF8))
#define CLINT_FREQ_HZ        1000000UL

/* PLIC for IRQ */
#define PLIC_BASE            0x0C000000UL
#define IDMA_IRQ_BASE        32

/* -----------------------------------------------------------------------
 * IRQ completion flags (set by trap handler)
 * --------------------------------------------------------------------- */
volatile int g_idma_done[IDMA_NUM_TIDS];

/* -----------------------------------------------------------------------
 * Internal helpers
 * --------------------------------------------------------------------- */

static inline void asm_dmsrc(uint64_t src) {
    asm volatile (".insn r 0x2B, 0, 0, zero, %0, zero" :: "r"(src) : "memory");
}
static inline void asm_dmdst(uint64_t dst) {
    asm volatile (".insn r 0x2B, 1, 0, zero, %0, zero" :: "r"(dst) : "memory");
}
static inline void asm_dmstr(uint64_t ss, uint64_t ds) {
    asm volatile (".insn r 0x2B, 6, 0, zero, %0, %1" :: "r"(ss), "r"(ds) : "memory");
}
static inline void asm_dmrep(uint64_t reps) {
    asm volatile (".insn r 0x2B, 7, 0, zero, %0, zero" :: "r"(reps) : "memory");
}
static inline void asm_dmcpy(uint64_t len, uint64_t flags) {
    asm volatile (".insn r 0x2B, 3, 0, zero, %0, %1" :: "r"(len), "r"(flags) : "memory");
}
static inline uint64_t asm_dmstati(uint64_t field) {
    uint64_t r;
    asm volatile (".insn r 0x2B, 4, 0, %0, zero, %1" : "=r"(r) : "r"(field));
    return r;
}
static inline int get_hart_id(void) {
    int id;
    asm volatile ("csrr %0, mhartid" : "=r"(id));
    return id;
}

/* -----------------------------------------------------------------------
 * API Implementation
 * --------------------------------------------------------------------- */

void idma_init(void) {
    /* 1. Disable clock gating during init */
    CLOCK_GATING_REG &= ~((1u << 1) | (1u << 7));

    /* 2. Clear all TIDs */
    IDMA_CLR[0] = 0xFFFFFFFF;   /* assuming CLR is a 32-bit wide register */

    /* 3. Zero all thresholds */
    for (int i = 0; i < IDMA_NUM_TIDS; i++) {
        IDMA_THRESHOLD[i] = 0;
        g_idma_done[i]    = 0;
    }

    /* 4. Enable ECC */
    ECC_CTRL_REG = 1;

    /* 5. Re-enable clock gating with 64-cycle hysteresis */
    CLOCK_GATING_HYST_R  = 0x06;
    CLOCK_GATING_REG    |= (1u << 1) | (1u << 7);

    /* 6. Ensure all writes are visible before first DMA use */
    asm volatile ("fence");
}

int idma_transfer(const idma_xfer_t *xfer, int trid) {
    if ((unsigned)trid >= IDMA_NUM_TIDS) return IDMA_EINVAL;
    if (!xfer) return IDMA_EINVAL;

    asm volatile ("fence w,w");   /* ensure src data visible to DMA */

    asm_dmsrc(xfer->src_addr);
    asm_dmdst(xfer->dst_addr);
    if (xfer->num_reps > 1) {
        asm_dmstr(xfer->src_stride, xfer->dst_stride);
        asm_dmrep((uint64_t)xfer->num_reps);
    }
    /* Merge caller's flags with TID */
    uint64_t flags = (xfer->flags & ~0x1FULL) | IDMA_FLAG_TID(trid);
    asm_dmcpy((uint64_t)xfer->length, flags);
    /* NOTE: asm_dmcpy may stall the hart if frontend FIFO is full */
    return IDMA_OK;
}

int idma_wait(int trid, uint32_t timeout_us) {
    if ((unsigned)trid >= IDMA_NUM_TIDS) return IDMA_EINVAL;

    if (timeout_us == 0) {
        /* Wait forever */
        while (IDMA_TR_COUNT[trid] < 1) {
            asm volatile ("nop");
        }
    } else {
        uint64_t deadline = CLINT_MTIME +
                            (uint64_t)timeout_us * (CLINT_FREQ_HZ / 1000000ULL);
        while (IDMA_TR_COUNT[trid] < 1) {
            if (CLINT_MTIME > deadline) {
                return IDMA_ETIMEOUT;
            }
        }
    }
    asm volatile ("fence r,r");   /* ensure DMA writes visible to CPU */
    return IDMA_OK;
}

void idma_wait_irq(int trid) {
    /* Requires prior idma_irq_setup(trid) and hart_init_interrupts() */
    g_idma_done[trid] = 0;
    IDMA_THRESHOLD[trid] = 1;

    while (!g_idma_done[trid]) {
        asm volatile ("wfi");   /* power-efficient wait */
    }
    asm volatile ("fence r,r");
}

int idma_poll(int trid) {
    if ((unsigned)trid >= IDMA_NUM_TIDS) return 0;
    return (IDMA_TR_COUNT[trid] >= 1) ? 1 : 0;
}

void idma_clear(int trid) {
    if ((unsigned)trid >= IDMA_NUM_TIDS) return;
    IDMA_CLR[trid] = 1;   /* W1C: clears TR_COUNT[trid] and deasserts IRQ */
}

uint32_t idma_status(void) {
    return IDMA_STATUS_REG;
}

void idma_set_threshold(int trid, uint32_t threshold) {
    if ((unsigned)trid >= IDMA_NUM_TIDS) return;
    IDMA_THRESHOLD[trid] = threshold;
}

void idma_irq_setup(int trid) {
    int hart_id = get_hart_id();
    int irq     = IDMA_IRQ_BASE + trid;
    int context = hart_id * 2;

    /* Set priority */
    *((volatile uint32_t *)(PLIC_BASE + 4 * irq)) = 1;

    /* Enable in this hart's context */
    volatile uint32_t *en =
        (uint32_t *)(PLIC_BASE + 0x2000 + 0x80 * context + 4 * (irq / 32));
    *en |= (1u << (irq % 32));

    /* Threshold = 0: accept any priority */
    *((volatile uint32_t *)(PLIC_BASE + 0x200000 + 0x1000 * context)) = 0;
}

/* -----------------------------------------------------------------------
 * Convenience wrappers
 * --------------------------------------------------------------------- */

int idma_memcpy_1d(uint64_t src, uint64_t dst, uint32_t bytes, int trid) {
    idma_xfer_t x = {
        .src_addr = src, .dst_addr = dst,
        .length = bytes, .num_reps = 1,
        .flags = IDMA_FLAG_TID(trid),
    };
    int rc = idma_transfer(&x, trid);
    if (rc) return rc;
    return idma_wait(trid, 0);
}

int idma_memcpy_2d(uint64_t src, uint64_t dst,
                   uint32_t row_bytes, uint32_t n_rows,
                   uint64_t src_stride, uint64_t dst_stride,
                   int trid) {
    idma_xfer_t x = {
        .src_addr = src, .dst_addr = dst,
        .length = row_bytes, .num_reps = n_rows,
        .src_stride = src_stride, .dst_stride = dst_stride,
        .flags = IDMA_FLAG_TID(trid) | IDMA_FLAG_DECOUPLE_RW,
    };
    int rc = idma_transfer(&x, trid);
    if (rc) return rc;
    return idma_wait(trid, 0);
}

int idma_zero_fill(uint64_t dst, uint32_t bytes, int trid) {
    /* INIT path: src_addr is ignored; zero-fill is triggered by a separate
     * descriptor flag. This is a simplified placeholder; the exact mechanism
     * to enable INIT mode depends on the idma_req_t extension fields. */
    idma_xfer_t x = {
        .src_addr = 0, .dst_addr = dst,
        .length = bytes, .num_reps = 1,
        .flags = IDMA_FLAG_TID(trid),
        /* TODO: set INIT mode flag in flags field once RTL field encoding confirmed */
    };
    int rc = idma_transfer(&x, trid);
    if (rc) return rc;
    return idma_wait(trid, 0);
}

int idma_dram_to_l1(uint64_t dram_src, uint64_t l1_dst,
                    uint32_t bytes, int trid) {
    idma_xfer_t x = {
        .src_addr = dram_src, .dst_addr = l1_dst,
        .length = bytes, .num_reps = 1,
        /* decouple_rw=1: critical for DRAM reads to hide latency */
        .flags = IDMA_FLAG_TID(trid) | IDMA_FLAG_DECOUPLE_RW,
    };
    int rc = idma_transfer(&x, trid);
    if (rc) return rc;
    return idma_wait(trid, 50000);  /* 50 ms timeout for DRAM loads */
}

/* -----------------------------------------------------------------------
 * IRQ handler hook (call from machine_trap_handler when iDMA IRQ claimed)
 * --------------------------------------------------------------------- */
void idma_irq_handler(int tid) {
    idma_clear(tid);
    g_idma_done[tid] = 1;
    /* g_idma_done is volatile; the hart in wfi will see it on wakeup */
}
```

### Usage Example (full tile firmware skeleton)

```c
/* tile_main.c -- minimal tile firmware skeleton using idma_driver */

#include "idma_driver.h"

#define L1_BASE          0x00000000UL
#define L1_SIZE          (768 * 1024)
#define DRAM_WEIGHT_ADDR 0x60000000ULL
#define WEIGHT_BYTES     (256 * 1024)

int hart_main(void) {
    int hart_id;
    asm volatile ("csrr %0, mhartid" : "=r"(hart_id));

    /* Hart 0 initializes the DMA engine and loads data */
    if (hart_id == 0) {
        idma_init();
        hart_init_interrupts();   /* set mtvec, enable mie.MEIE */

        /* Load 256 KB of weights from DRAM SI0 into L1 */
        idma_set_threshold(0, 1);
        idma_irq_setup(0);

        int rc = idma_dram_to_l1(DRAM_WEIGHT_ADDR,
                                  L1_BASE + 0x10000,  /* L1 offset 64 KB */
                                  WEIGHT_BYTES, 0);

        if (rc == IDMA_OK) {
            /* Signal harts 1-7 via CLINT MSIP */
            for (int h = 1; h < 8; h++) {
                wake_hart(h);
            }
        } else {
            /* Handle DMA failure */
            check_and_clear_l1_ecc();
            check_bus_errors();
            while (1) { asm volatile ("wfi"); }  /* halt on error */
        }
    }

    /* All harts: wait for wake from hart 0, then compute */
    if (hart_id > 0) {
        hart_init_interrupts();
        asm volatile ("wfi");      /* wait for MSIP from hart 0 */
        asm volatile ("fence r,r");

        /* Each hart processes a distinct slice of the loaded data */
        uint32_t *weights = (uint32_t *)(L1_BASE + 0x10000);
        uint32_t slice_len = WEIGHT_BYTES / (7 * sizeof(uint32_t));
        uint32_t *my_slice = weights + (hart_id - 1) * slice_len;

        /* ... compute on my_slice ... */
    }

    while (1) { asm volatile ("wfi"); }
    return 0;
}
```

---

*End of document — Trinity N1B0 Overlay DMA & RISC-V CPU Engine HDD v0.4*

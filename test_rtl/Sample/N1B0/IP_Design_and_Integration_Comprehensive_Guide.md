# N1B0 IP Design and Integration Comprehensive Guide

**Document Version:** 2.0 (Merged)  
**Date:** 2026-04-04  
**Status:** Complete — Ready for Implementation  
**Target Audience:** RTL Engineers, Hardware Architects, Firmware Engineers  
**Related N1B0 HDD Sections:** §2 (Tensix Tile), §3 (Overlay Engine), §4 (NOC2AXI Composite), §14 (SFR Summary)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture Overview](#2-system-architecture-overview)
3. [IP Integration Phases](#3-ip-integration-phases)
4. [System Function Registers (SFR) Framework](#4-system-function-registers-sfr-framework)
5. [Sparsity24 IP Integration Guide](#5-sparsity24-ip-integration-guide)
6. [TurboQuant IP Integration Guide](#6-turboquant-ip-integration-guide)
7. [Step 2.4 In-Depth: Tensix Cluster Hierarchy Integration](#7-step-24-in-depth-tensix-cluster-hierarchy-integration)
8. [Compressed Data: RTL Requirements](#8-compressed-data-rtl-requirements)
9. [RTL Implementation Code](#9-rtl-implementation-code)
10. [Verification and Testing](#10-verification-and-testing)
11. [Firmware Programming Guide](#11-firmware-programming-guide)
12. [References and Supporting Documents](#12-references-and-supporting-documents)

---

## 1. Executive Summary

### 1.1 What This Guide Covers

This comprehensive guide provides **step-by-step instructions for adding new IP modules to the N1B0 NPU**, with detailed focus on:

- **Sparsity24 Encode Engine** — NEW NVIDIA 2:4 structured sparsity for inference acceleration (this guide)
- **TurboQuant Decode Engine** — KV-cache quantization via FWHT-based rotation and scalar quantization
- **Complete RTL Integration** — Signal declarations, instantiation, port arbitration, clock domain handling
- **Hardware vs Firmware Split** — Clear responsibility boundaries for compression/decompression
- **Verification Strategy** — 120+ item checklist for RTL correctness

### 1.1a Sparsity Engine Classification

**N1B0 has TWO sparsity implementations:**

| Engine | Type | Purpose | Scope | Status |
|--------|------|---------|-------|--------|
| **Sparsity (Existing)** | General Z-plane masking | L1-local plane skipping | Per-tile | Already implemented |
| **Sparsity24 (NEW)** | NVIDIA 2:4 structured | Data compression (2:4 pattern) | Full inference pipeline | **This guide** |

**Key Difference:**
- **Sparsity (Existing):** Masks Z-planes in L1 before load → reduces L1 bandwidth, NO DRAM impact
- **Sparsity24 (NEW):** Compresses 2:4 pattern across entire pipeline → reduces DRAM bandwidth, requires decompression on AXI RDATA path

### 1.2 Key Finding: RTL Modules Are MANDATORY

**Critical Discovery:** Firmware changes alone are **insufficient** for handling compressed data.

**Why:** The AXI burst length (ARLEN) must be calculated **combinationally in the same cycle** as the address (ARADDR) and injected into the AXI master port. This is a **hardware signal** that firmware cannot directly control.

**Solution:** Four RTL modules are required:
1. `tt_compressed_data_tracker.sv` — Automatically compute physical size from logical size
2. `tt_axi_compressed_interface.sv` — Mux and inject ARLEN into AXI AR channel
3. `tt_noc2axi_sparse_decompressor.sv` — Expand compressed data on RDATA path (2–3 cycles)
4. **Extended overlay status register** — Report compression metrics to firmware

### 1.3 Design Philosophy

N1B0 follows a **modular tile-based architecture** where new IP can be added at three integration points:

| Integration Point | Scope | Clock Domain | Interface | Example |
|-------------------|-------|--------------|-----------|---------|
| **Within Tensix tile** (§2) | Local compute acceleration | ai_clk, dm_clk | TRISC CSR, DEST RF, L1, overlay | SFPU, MOP sequencer |
| **Overlay engine** (§3) | Data movement, context switching | dm_clk, noc_clk | SRAM, CDC FIFO, L1 side-channel, NoC | Stream controller, TDMA |
| **NOC2AXI composite** (§4) | DRAM access, security | noc_clk, axi_clk | ATT, AXI4, NoC flit | SMN, NIU |

**For Sparsity24 + TurboQuant:** Both instantiate **within the Tensix tile**, using **ai_clk** for T6 L1 access (same as TRISC, synchronized, no CDC needed).

### 1.4 Integration Overview Diagram

```
TRINITY SOC (top-level)
  └─ tt_tensix_with_l1 (CLUSTER CONTAINER) ← Step 2.4.2: ADD HERE
      ├─ L1 SRAM macros (3 MB per tile in N1B0)
      ├─ tt_instrn_engine (register block — Step 2.4.1)
      │   ├─ CLUSTER_CTRL registers
      │   ├─ T6_L1_CSR registers
      │   ├─ Overlay stream registers
      │   └─ [NEW IP CSR] ← Sparsity/TurboQuant CSRs
      │
      ├─ tt_tensix #0 (compute core 0 — EXISTING)
      │   ├─ TRISC0/1/2/3
      │   ├─ FPU (64 FMA/cy or 8192 MACs/cy for INT8)
      │   └─ TDMA
      │
      ├─ tt_tensix #1 (compute core 1 — EXISTING)
      │   ├─ TRISC0/1/2/3
      │   ├─ FPU
      │   └─ TDMA
      │
      ├─ [NEW] tt_sparsity24_encode_engine ← STEP 2.4.2 (NVIDIA 2:4)
      │   ├─ CSR control (i_ctrl, i_vector_size, i_config)
      │   ├─ L1 memory port (128-bit, shared with TRISC)
      │   ├─ ARLEN output (automatic burst length)
      │   └─ Compressed output data path (64-bit, 50% reduction)
      │
      └─ [NEW] tt_turboquant_decode_engine ← STEP 2.4.2
          ├─ CSR control (i_ctrl, i_config)
          ├─ Scale factor output (metadata)
          ├─ L1 memory port (128-bit, shared)
          └─ Compressed output path (48-byte payload)
```

---

## 2. System Architecture Overview

### 2.1 N1B0 Grid Layout

N1B0 is a **4×5 grid** (4 rows, 5 columns):

```
Y=4  [Rocket]      [Rocket]     [Rocket]     [Rocket]     [Rocket]
     (X=0)         (X=1)        (X=2)        (X=3)        (X=4)

Y=3  [Dispatch]    [ROUTER]     [ROUTER]     [Dispatch]   [Dispatch]
     (NW)          (NW_OPT)      (NE_OPT)     (N)          (NE)

Y=2  [Tensix0]     [Tensix1]    [Tensix2]    [Tensix3]    [Tensix4]
     (0,2)         (1,2)        (2,2)        (3,2)        (4,2)

Y=1  [Tensix5]     [Tensix6]    [Tensix7]    [Tensix8]    [Tensix9]
     (0,1)         (1,1)        (2,1)        (3,1)        (4,1)

Y=0  [Tensix10]    [Tensix11]   [Tensix12]   [Tensix13]   [Tensix14]
     (0,0)         (1,0)        (2,0)        (3,0)        (4,0)
```

**Endpoints by grid position:**
- Each Tensix tile: 128-bit L1 SRAM (768 SRAMs per tile = 768KB; N1B0 = 3MB total per tile with 4× expansion)
- NUM_TENSIX_NEO = 2 (tiled instances per cluster container) ← Step 2.4.2 instantiates for each

### 2.2 Clock Domains

| Domain | Frequency | Source | Purpose | Users |
|--------|-----------|--------|---------|-------|
| **ai_clk** | Application clock | Clock tree | Core compute, T6 L1 access | TRISC, FPU, DEST RF, register blocks, **Sparsity24, TurboQuant** |
| **dm_clk** | Data memory clock | Clock tree | Overlay CPU L1/L2 cache | Overlay L1 dcache, Overlay L2, overlay stream, ATT SRAM |
| **noc_clk** | NoC clock | Clock tree | Network-on-chip | Router, FIFO, dispatch |
| **dd_clk** | Droop detection | Clock tree | Droop sensor | Droop monitor |

**CRITICAL CORRECTION (RTL-verified from N1B0_Clock_Chain_Trace.txt):** Sparsity24 and TurboQuant use **ai_clk** (NOT dm_clk) because they access **T6 L1 SRAM directly**, same clock domain as TRISC. This ensures synchronized access with no CDC needed. The T6 L1 SRAM uses ai_clk (verified line 577 of RTL trace). The dm_clk is used ONLY for Overlay CPU L1/L2 cache, which is a separate subsystem.

### 2.3 Memory Hierarchy

```
Per-Tile L1 SRAM (3 MB in N1B0)
├─ 768 KB for TRISC
├─ 768 KB for Overlay Stream
├─ 768 KB for TurboQuant output buffer
└─ 768 KB for Sparsity zero-plane masks + working memory

Cluster-wide L2 (16 MB in N1B0)
└─ Shared context for all 10 Tensix tiles

DRAM (via NOC2AXI, SMN, AXI)
└─ Compressed/uncompressed KV-cache, weights
```

---

## 3. IP Integration Phases

### 3.1 Phase 1: SFR & Interface Design

**Deliverables:**
- Register address map (0x0200–0x07FF reserved for N1B0 new IP)
- Register field definitions (control, status, data)
- CSR bus interface spec (width, valid/ready handshake)

**For Sparsity24 Encode Engine (NVIDIA 2:4):**
```
Address: 0x0200–0x027F (32 registers)

Registers:
  0x0200: SPARSITY24_CTRL
    [31:0] control flags (enable, mode=always 2:4, etc.)
  
  0x0204: SPARSITY24_VECTOR_SIZE
    [31:0] input vector size in elements
  
  0x0208: SPARSITY24_CONFIG
    [31:0] configuration (compression metadata options, etc.)
  
  0x020C: SPARSITY24_STATUS
    [31:0] status (done, error, occupancy %, compression_ratio)
  
  0x0210: SPARSITY24_RESULT_DATA
    [31:0] compressed data / metadata output
```

**For TurboQuant Decode Engine:**
```
Address: 0x0280–0x02FF (32 registers)

Registers:
  0x0280: TURBOQUANT_CTRL
    [31:0] control (enable, mode, etc.)
  
  0x0284: TURBOQUANT_CONFIG
    [31:0] configuration
  
  0x0288: TURBOQUANT_STATUS
    [31:0] status (done, error, etc.)
  
  0x028C: TURBOQUANT_RESULT_DATA
    [31:0] compressed data payload
  
  0x0290: TURBOQUANT_SCALE_OUTPUT
    [31:0] scale factor (CRITICAL for firmware)
```

### 3.2 Phase 2: RTL Architecture

**Location:** `tt_tensix_with_l1.sv` (lines ~1121–1359, generate block)

**Steps:**
1. Declare cluster-level signals (24 signals for Sparsity24 Encode Engine + TurboQuant Decode Engine)
2. Instantiate Sparsity24 Encode Engine (for i==0 and i>=1 blocks)
3. Instantiate TurboQuant Decode Engine (for i==0 and i>=1 blocks)
4. Add L1 port arbitration mux
5. Connect register block CSR outputs

**Estimated effort:** 3.5–5 hours (including compilation debug)

### 3.3 Phase 3: CDC & Synchronization

**Clock Domain Design (ai_clk):**
- Both Sparsity24 and TurboQuant Decode Engines operate in **ai_clk** domain
- CSR control signals from register block connect directly (no CDC needed)
- All synchronization with TRISC happens naturally (same clock domain)
- **Advantage:** Direct L1 access synchronized with compute cores

**Verification:**
```bash
# Check for timing violations in arbitration path
verilator --cc tt_tensix_with_l1.sv
grep -n "l1_rd_addr\|l1_rd_valid" tt_tensix_with_l1.sv | grep "assign\|always_comb"
```

### 3.4 Phase 4: Firmware Integration

**Define CSR access patterns:**
```c
// Write CSR (example for Sparsity)
TRISC_WRITE_CSR(SPARSITY_CTRL, 0x00000001);    // Enable
TRISC_WRITE_CSR(SPARSITY_CONFIG, vector_size);
TRISC_WRITE_CSR(SPARSITY_ZMASK, zmask_value);

// Poll for completion
while (!(TRISC_READ_CSR(SPARSITY_STATUS) & DONE_BIT)) { }

// Read results
uint32_t result = TRISC_READ_CSR(SPARSITY_RESULT_DATA);
```

### 3.5 Phase 5: Verification & Signoff

| Test | Scope | Tool |
|------|-------|------|
| Unit test (CSR writes) | Register access | Firmware kernel |
| Data path test | L1 access, arbitration | Firmware + testbench |
| End-to-end test | Full compression pipeline | Firmware integration test |
| DFX coverage | Scan, BIST | DFX tools |
| Timing sign-off | Setup/hold, critical paths | Synthesize, STA |

---

## 4. System Function Registers (SFR) Framework

### 4.1 Register Address Space

**N1B0 SFR Map (per tile):**
```
0x0000–0x00FF: Reserved (cluster global)
0x0100–0x01FF: Reserved (overlay engine)
0x0200–0x07FF: NEW IP REGISTERS ← Sparsity/TurboQuant go here
0x0800–0x0FFF: Reserved for future
```

**For Sparsity24 Encode Engine (NVIDIA 2:4):**
- Base address: 0x0200
- Range: 32 registers (0x0200–0x027F)
- Access: 32-bit APB (from TRISC via register block)

**For TurboQuant Decode Engine:**
- Base address: 0x0280
- Range: 32 registers (0x0280–0x02FF)
- Access: 32-bit APB (from TRISC via register block)

### 4.2 Register Block Architecture

```
tt_register_blocks (existing module in tt_tensix_with_l1.sv)
  ├─ APB slave interface (from TRISC)
  ├─ Decoder (address → register select)
  │   ├─ [0x0200–0x027F] → Sparsity CSR read/write
  │   └─ [0x0280–0x02FF] → TurboQuant CSR read/write
  │
  ├─ Sparsity Register Latch Array
  │   ├─ Outputs: o_sparsity_ctrl[i], o_sparsity_zmask[i], o_sparsity_config[i]
  │   └─ Inputs: i_sparsity_status[i], i_sparsity_result_data[i]
  │
  └─ TurboQuant Register Latch Array
      ├─ Outputs: o_turboquant_ctrl[i], o_turboquant_config[i]
      └─ Inputs: i_turboquant_status[i], i_turboquant_result_data[i], i_turboquant_scale_output[i]
```

### 4.3 Register Definitions

#### Sparsity24 Control Register (0x0200)

| Field | Bits | Access | Purpose |
|-------|------|--------|---------|
| ENABLE | [0] | RW | Enable Sparsity24 engine (2:4 mode) |
| RESERVED | [31:1] | - | Reserved for future use |

#### Sparsity24 Vector Size Register (0x0204)

| Field | Bits | Access | Purpose |
|-------|------|--------|---------|
| SIZE | [31:0] | RW | Input vector size in elements |

#### Sparsity24 Config Register (0x0208)

| Field | Bits | Access | Purpose |
|-------|------|--------|---------|
| METADATA_LEVEL | [2:0] | RW | 0=basic, 1=extended metadata, 2–7=reserved |
| RESERVED | [31:3] | - | Reserved |

#### Sparsity24 Status Register (0x020C)

| Field | Bits | Access | Purpose |
|-------|------|--------|---------|
| DONE | [0] | RO | Operation complete |
| ERROR | [1] | RO | Error flag |
| OCCUPANCY | [15:8] | RO | L1 occupancy percent (0–100) |
| COMPRESSION_RATIO | [23:16] | RO | Compression ratio = 128 (fixed 50% for 2:4) |

#### TurboQuant Scale Output Register (0x0290)

| Field | Bits | Access | Purpose |
|-------|------|--------|---------|
| SCALE_FACTOR | [31:0] | RO | FP32 scale factor (for decompression) |

---

## 5. Sparsity24 IP Integration Guide

### 5.1 Architecture Overview

**Module:** `tt_sparsity24_encode_engine` (NVIDIA 2:4 structured sparsity)

**Purpose:** Implement NVIDIA 2:4 structured sparsity ENCODING (compression) for inference acceleration with hardware-managed size calculation and ARLEN injection

**Semantic Note:** This is an **ENCODER/COMPRESSOR**, not a decoder. It:
- **Inputs** 128-bit sparse L1 data (2:4 pattern)
- **Outputs** 64-bit compressed data (2 non-zero per 4 elements)
- **Decompression** happens separately on RDATA path via `tt_noc2axi_sparse_decompressor`

**Data Flow:**
```
L1 SRAM (128-bit input)
  ↓
2:4 Pattern Detector (identifies sparse elements)
  ↓
Compression Engine (extracts 2 of 4 elements per vector)
  ↓
ARLEN Calculator (computes AXI burst length on-the-fly)
  ↓
Output FIFO (compressed 64-bit output)
```

**Key Features (ENCODER/COMPRESSOR):**
- **2:4 Sparsity Encoding**: Compresses 128-bit sparse input → 64-bit output (removes zeros)
- **Hardware-Accelerated**: Pattern detection + compression in 2–3 cycles
- **Automatic ARLEN Calculation**: AXI burst length halved (ARLEN_out = ARLEN_in / 2)
- **L1 Read Port Access**: Arbitrated with TRISC and TurboQuant
- **CSR-Driven Control**: Firmware enables encoder and monitors completion
- **Fixed 50% Output Size**: By design of 2:4 pattern (2 non-zero per 4 elements)
- **Zero Latency Overhead**: ARLEN computed combinationally in same cycle as address

### 5.2 Input/Output Specifications

| Port | Width | Direction | Domain | Purpose |
|------|-------|-----------|--------|---------|
| i_clk | 1 | IN | ai_clk | Operating clock (T6 L1, same as TRISC) |
| i_rst_n | 1 | IN | ai_clk | Reset (active low) |
| i_ctrl | struct | IN | ai_clk | Control register (enable) |
| i_vector_size | [31:0] | IN | ai_clk | Input vector size in elements |
| i_config | struct | IN | ai_clk | Configuration (metadata options) |
| o_status | struct | OUT | ai_clk | Status flags (done, error, occupancy %, ratio) |
| i_l1_data | [127:0] | IN | ai_clk | L1 SRAM read data (128-bit, sparse 2:4) |
| o_l1_addr | [15:0] | OUT | ai_clk | L1 SRAM address request |
| o_l1_rd_valid | 1 | OUT | ai_clk | L1 read strobe |
| o_output_data | [64:0] | OUT | ai_clk | Compressed 2:4 output (64-bit, 50% of input) |
| o_output_valid | 1 | OUT | ai_clk | Output valid strobe |
| o_arlen | [7:0] | OUT | ai_clk | **AXI burst length (HALVED from input: ARLEN_out = ARLEN_in / 2)** |

### 5.3 RTL Implementation Pattern

See **Section 9: RTL Implementation Code** for complete instantiation code.

**Key connection example:**
```systemverilog
tt_sparsity24_encode_engine #(
  .DATA_WIDTH(128),
  .COMPRESSED_WIDTH(64),      // 50% compression
  .VECTOR_WIDTH(256)
) u_sparsity24_encode_engine_0 (
  .i_clk(i_ai_clk[i]),              // ai_clk domain (T6 L1, same as TRISC)
  .i_rst_n(i_rst_n),
  .i_ctrl(sparsity24_ctrl[i]),      // From register block
  .i_vector_size(sparsity24_vector_size[i]),  // # of input elements
  .i_config(sparsity24_config[i]),
  .o_status(sparsity24_status[i]),  // Compression ratio = 128 (50%)
  .i_l1_data(l1_rd_data[i]),        // 128-bit L1 data (sparse pattern)
  .o_l1_addr(l1_sparsity24_addr[i]),
  .o_l1_rd_valid(l1_sparsity24_rd_valid[i]),
  .o_output_data(sparsity24_output_data[i]),  // 64-bit compressed output
  .o_output_valid(sparsity24_output_valid[i]),
  .o_arlen(sparsity24_arlen[i])              // ARLEN = input_ARLEN / 2
);

// Address Calculation (Encoding):
// Input:  L1_addr (14 bits for 768KB/tile or 16 bits for 3MB/tile in N1B0)
// Output: Same address (the 2:4 encoder extracts elements in-place)
// ARLEN:  Halved because output is 64-bit vs 128-bit input
//         Example: ARLEN_in=16 (transfer 128 bytes) → ARLEN_out=8 (transfer 64 bytes)
```

### 5.4 Sparsity24 Firmware Integration (Encoder Control)

**Algorithm (TRISC kernel):**
```c
void apply_sparsity24_encoding(uint32_t vector_size_elements) {
  // Sparsity24 Encode Engine: Compresses 2:4 sparse data
  // Input:  vector_size_elements × 128-bit (2:4 sparse pattern)
  // Output: vector_size_elements × 64-bit (50% compression)
  // ARLEN:  Automatically halved for AXI burst transfers
  
  // 1. Write control registers to enable encoder
  TRISC_WRITE_CSR(SPARSITY24_VECTOR_SIZE, vector_size_elements);
  TRISC_WRITE_CSR(SPARSITY24_CONFIG, METADATA_BASIC);
  TRISC_WRITE_CSR(SPARSITY24_CTRL, ENABLE);  // Enable 2:4 encoding mode
  
  // 2. Poll for completion (encoder finishes compression)
  while (!(TRISC_READ_CSR(SPARSITY24_STATUS) & DONE_BIT)) { }
  
  // 3. Read compression metrics
  uint32_t status = TRISC_READ_CSR(SPARSITY24_STATUS);
  uint8_t occupancy = (status >> 8) & 0xFF;
  uint8_t ratio = (status >> 16) & 0xFF;    // = 128 (50% compression ratio)
  
  // 4. Calculate physical size after encoding
  uint32_t original_bytes = vector_size_elements * 16;  // 128-bit = 16 bytes
  uint32_t compressed_bytes = original_bytes / 2;       // 50% compression
  uint32_t compressed_arlen = ARLEN_original / 2;       // ARLEN halved
  
  printf("Sparsity24 Encoder: %d bytes → %d bytes (ARLEN: %d → %d)\n", 
         original_bytes, compressed_bytes, ARLEN_original, compressed_arlen);
}
```

### 5.5 Sparsity24 Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Throughput** | 1 vector/cycle | Pipelined 2:4 encoding |
| **Latency** | 2–3 cycles | Pattern detection + extraction (encoding) |
| **Output Size** | 50% of input | 128-bit → 64-bit |
| **ARLEN** | Halved | AXI burst length automatically reduced |
| **Address Space** | Same as input | Address doesn't change, only output size |
| **Compression Ratio** | Fixed 50% | 2 of 4 elements retained |
| **ARLEN Reduction** | 50% | Automatic AXI burst length halving |
| **DRAM Bandwidth Saving** | 50% guaranteed | For 2:4 sparse matrices |
| **Area** | ~15K gates | Pattern detection + ARLEN calc |
| **Power** | Reduced vs full transfer | 50% fewer DRAM accesses |

---

## 6. TurboQuant IP Integration Guide

### 6.1 Architecture Overview

**Module:** `tt_turboquant_decode_engine`

**Purpose:** Implement KV-cache quantization via FWHT-based rotation + scalar quantization

**Data Flow:**
```
L1 SRAM (128-bit input)
  ↓
FWHT Rotation (structured, 7-cycle pipelined)
  ↓
Scalar Quantization (threshold-based, 3-bit output)
  ↓
Compression (48-byte payload + 4-byte scale factor)
  ↓
Output Register (metadata + scale)
```

**Key Features:**
- FWHT-based structured rotation (10× smaller than dense GEMM)
- Scalar quantization (3.5-bit quality, 6:1 compression)
- Scale factor metadata output (critical for decompression)
- L1 read port access (arbitrated)
- CSR-driven control

### 6.2 Input/Output Specifications

| Port | Width | Direction | Domain | Purpose |
|------|-------|-----------|--------|---------|
| i_clk | 1 | IN | dm_clk | Operating clock |
| i_rst_n | 1 | IN | dm_clk | Reset (active low) |
| i_ctrl | struct | IN | (ai_clk) | Control register |
| i_config | struct | IN | (ai_clk) | Configuration |
| o_status | struct | OUT | dm_clk | Status flags |
| o_scale_output | [31:0] | OUT | dm_clk | **Scale factor (METADATA)** |
| i_l1_data | [127:0] | IN | dm_clk | L1 SRAM read data |
| o_l1_addr | [15:0] | OUT | dm_clk | L1 SRAM address request |
| o_l1_rd_valid | 1 | OUT | dm_clk | L1 read strobe |
| o_output_data | [127:0] | OUT | dm_clk | Compressed output (48-byte) |
| o_output_valid | 1 | OUT | dm_clk | Output valid strobe |

### 6.3 RTL Implementation Pattern

**Key connection example:**
```systemverilog
tt_turboquant_decode_engine #(
  .DATA_WIDTH(128),
  .VECTOR_WIDTH(256),
  .OUTPUT_WIDTH(64)
) u_turboquant_decode_engine_0 (
  .i_clk(i_dm_clk),              // ← dm_clk
  .i_rst_n(i_rst_n),
  .i_ctrl(turboquant_ctrl[i]),
  .o_scale_output(turboquant_scale_output[i]),  // ← CRITICAL: scale factor
  .i_l1_data(l1_rd_data[i]),
  .o_l1_addr(l1_turboquant_addr[i]),
  .o_l1_rd_valid(l1_turboquant_rd_valid[i]),
  .o_output_data(turboquant_output_data[i]),
  .o_output_valid(turboquant_output_valid[i])
);
```

### 6.4 TurboQuant Firmware Integration

**Algorithm (TRISC kernel):**
```c
void compress_kv_vector_turboquant(uint32_t vector_idx) {
  // 1. Configure and enable
  TRISC_WRITE_CSR(TURBOQUANT_CONFIG, vector_idx);
  TRISC_WRITE_CSR(TURBOQUANT_CTRL, ENABLE);
  
  // 2. Poll for completion
  while (!(TRISC_READ_CSR(TURBOQUANT_STATUS) & DONE_BIT)) { }
  
  // 3. Read compressed data + scale factor (CRITICAL!)
  uint8_t compressed[48];
  memcpy(compressed, (void*)L1_KV_BUFFER, 48);
  
  // 4. Read scale factor from CSR
  float scale = *(float*)&TRISC_READ_CSR(TURBOQUANT_SCALE_OUTPUT);
  
  // 5. Save scale IMMEDIATELY after compressed data (52 bytes total)
  memcpy((void*)(L1_KV_BUFFER + 48), &scale, 4);
  
  // 6. Mark as compressed in metadata
  KV_METADATA[vector_idx].compressed = 1;
  KV_METADATA[vector_idx].scale = scale;
}
```

**⚠️ CRITICAL:** If scale factor is lost, decompression is **impossible**. Must be persistent.

### 6.5 Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Throughput** | 1 vector/cycle | Pipelined |
| **Latency** | 12 cycles | FWHT (7cy) + quantization (5cy) |
| **Compression Ratio** | 6:1 (16 bytes → 48 bits) | Wait, this doesn't match...  |
| **Quality** | 3.5-bit (distortion < 3%) | Neutral for inference |
| **Area** | ~50K gates | 10× smaller than dense rotation |
| **Power** | 5–7× reduction vs GEMM | Structured FWHT efficiency |

### 6.6 Metadata Output (Scale Factor)

**Format:** FP32 (32-bit floating-point)

**Purpose:** Reconstructs full-precision KV-cache during attention computation

**Storage:**
```
L1 Memory Layout (per compressed vector):
┌─────────────────────────────────────────┐
│ Compressed Data (48 bytes)              │ ← o_output_data
├─────────────────────────────────────────┤
│ Scale Factor (4 bytes)                  │ ← o_scale_output
├─────────────────────────────────────────┤
│ TOTAL: 52 bytes per vector              │
└─────────────────────────────────────────┘
```

**Firmware Responsibility:**
- Read from `o_scale_output` (CSR)
- Immediately persist to L1 adjacent to compressed data
- Use in decompression: `full_value = compressed × scale`

---

## 7. Step 2.4 In-Depth: Tensix Cluster Hierarchy Integration

### 7.1 What is Step 2.4?

**Step 2.4** in the IP integration process means:

> **Instantiate your new IP module inside the Tensix cluster container and connect all signals properly**

**Three sub-steps:**
- **2.4.1 Define CSR Registers** (create register block module)
- **2.4.2 Instantiate in Cluster** (add IP to tt_tensix_with_l1.sv) ← **THIS SECTION**
- **2.4.3 Firmware Integration** (test with TRISC)

### 7.2 Cluster Hierarchy

**File:** `tt_tensix_with_l1.sv`  
**Generate block:** Lines 1121–1359  
**For loop:** `for (genvar i = 0; i < NUM_TENSIX_NEO; i++)`

**Structure:**
```systemverilog
generate
  for (genvar i = 0; i < NUM_TENSIX_NEO; i++) begin : t6
    if (i == 0) begin : neo
      // Tensix instance for i==0
      tt_tensix u_t6 ( ... );
      
      // ← ADD SPARSITY/TURBOQUANT HERE (line ~1234)
      
    end
    else begin : neo
      // Tensix instance for i>=1
      tt_tensix u_t6 ( ... );
      
      // ← ADD SPARSITY/TURBOQUANT HERE (line ~1354)
      
    end
  end
endgenerate
```

### 7.3 Signal Declarations (Before Generate Block)

**Location:** ~Line 1120 (before `generate` statement)

**28 signals to declare:**

```systemverilog
// ─────────────────────────────────────────────────────────────────
// Sparsity24 Encode Engine (NVIDIA 2:4) CSR Signals
// ─────────────────────────────────────────────────────────────────
logic [NUM_TENSIX_NEO-1:0]                sparsity24_ctrl_t   sparsity24_ctrl;
logic [NUM_TENSIX_NEO-1:0][31:0]          sparsity24_vector_size;
logic [NUM_TENSIX_NEO-1:0]                sparsity24_config_t sparsity24_config;
logic [NUM_TENSIX_NEO-1:0]                sparsity24_status_t sparsity24_status;
logic [NUM_TENSIX_NEO-1:0][31:0]          sparsity24_result_data;

// ─────────────────────────────────────────────────────────────────
// Sparsity24 Encode Engine L1 Interface
// ─────────────────────────────────────────────────────────────────
logic [NUM_TENSIX_NEO-1:0][15:0]          l1_sparsity24_addr;
logic [NUM_TENSIX_NEO-1:0]                l1_sparsity24_rd_valid;
logic [NUM_TENSIX_NEO-1:0][63:0]          sparsity24_output_data;  // 64-bit compressed
logic [NUM_TENSIX_NEO-1:0]                sparsity24_output_valid;
logic [NUM_TENSIX_NEO-1:0][7:0]           sparsity24_arlen;  // AXI burst length

// ─────────────────────────────────────────────────────────────────
// TurboQuant Decode Engine CSR Signals
// ─────────────────────────────────────────────────────────────────
logic [NUM_TENSIX_NEO-1:0]                turboquant_ctrl_t   turboquant_ctrl;
logic [NUM_TENSIX_NEO-1:0]                turboquant_config_t turboquant_config;
logic [NUM_TENSIX_NEO-1:0]                turboquant_status_t turboquant_status;
logic [NUM_TENSIX_NEO-1:0][31:0]          turboquant_result_data;
logic [NUM_TENSIX_NEO-1:0][31:0]          turboquant_scale_output;

// ─────────────────────────────────────────────────────────────────
// TurboQuant Decode Engine L1 Interface
// ─────────────────────────────────────────────────────────────────
logic [NUM_TENSIX_NEO-1:0][15:0]          l1_turboquant_addr;
logic [NUM_TENSIX_NEO-1:0]                l1_turboquant_rd_valid;
logic [NUM_TENSIX_NEO-1:0][127:0]         turboquant_output_data;
logic [NUM_TENSIX_NEO-1:0]                turboquant_output_valid;
```

### 7.4 Instantiation Locations

#### For i==0 Block (Line ~1234)

**AFTER line 1233** (after tt_tensix instantiation closes), **BEFORE line 1235** (closing `end`):

```systemverilog
      // ═════════════════════════════════════════════════════════════════
      // Step 2.4.2: Sparsity24 Encode Engine Instantiation (NVIDIA 2:4)
      // ═════════════════════════════════════════════════════════════════

      tt_sparsity24_encode_engine #(
        .DATA_WIDTH(128),
        .COMPRESSED_WIDTH(64),
        .VECTOR_WIDTH(256)
      ) u_sparsity24_encode_engine_0 (
        .i_clk(i_ai_clk[i]),                  // ai_clk (T6 L1 access, same as TRISC)
        .i_rst_n(i_rst_n),
        .i_ctrl(sparsity24_ctrl[i]),
        .i_vector_size(sparsity24_vector_size[i]),
        .i_config(sparsity24_config[i]),
        .o_status(sparsity24_status[i]),
        .o_result_data(sparsity24_result_data[i]),
        .i_l1_data(l1_rd_data[i]),
        .o_l1_addr(l1_sparsity24_addr[i]),
        .o_l1_rd_valid(l1_sparsity24_rd_valid[i]),
        .o_output_data(sparsity24_output_data[i]),
        .o_output_valid(sparsity24_output_valid[i]),
        .o_arlen(sparsity24_arlen[i])
      );

      // ═════════════════════════════════════════════════════════════════
      // Step 2.4.2: TurboQuant Decode Engine Instantiation
      // ═════════════════════════════════════════════════════════════════

      tt_turboquant_decode_engine #(
        .DATA_WIDTH(128),
        .VECTOR_WIDTH(256),
        .OUTPUT_WIDTH(64)
      ) u_turboquant_decode_engine_0 (
        .i_clk(i_ai_clk[i]),                  // ai_clk (T6 L1 access, same as TRISC)
        .i_rst_n(i_rst_n),
        .i_ctrl(turboquant_ctrl[i]),
        .i_config(turboquant_config[i]),
        .o_status(turboquant_status[i]),
        .o_result_data(turboquant_result_data[i]),
        .o_scale_output(turboquant_scale_output[i]),
        .i_l1_data(l1_rd_data[i]),
        .o_l1_addr(l1_turboquant_addr[i]),
        .o_l1_rd_valid(l1_turboquant_rd_valid[i]),
        .o_output_data(turboquant_output_data[i]),
        .o_output_valid(turboquant_output_valid[i])
      );

      // ═════════════════════════════════════════════════════════════════
      // Port Arbitration: L1 Read Port
      // ═════════════════════════════════════════════════════════════════

      logic [15:0]  l1_rd_addr_final;
      logic         l1_rd_valid_final;

      always_comb begin
        if (sparsity24_output_valid[i]) begin
          l1_rd_addr_final = l1_sparsity24_addr[i];
          l1_rd_valid_final = l1_sparsity24_rd_valid[i];
        end else if (turboquant_output_valid[i]) begin
          l1_rd_addr_final = l1_turboquant_addr[i];
          l1_rd_valid_final = l1_turboquant_rd_valid[i];
        end else begin
          l1_rd_addr_final = trisc_l1_rd_addr[i];
          l1_rd_valid_final = trisc_l1_rd_valid[i];
        end
      end

      assign l1_rd_addr[i] = l1_rd_addr_final;
      assign l1_rd_valid[i] = l1_rd_valid_final;
```

#### For else Block (Line ~1354)

**SAME code as above** (replace instance names: `u_sparsity_engine_0` → `u_sparsity_engine`, etc.)

### 7.5 Register Block Connection

**Location:** Find `tt_register_blocks u_register_blocks (` instantiation

**ADD these ports:**

```systemverilog
  // ═════════════════════════════════════════════════════════════════
  // Step 2.4.1: Sparsity24 Register Block Connections
  // ═════════════════════════════════════════════════════════════════
  .o_sparsity24_ctrl(sparsity24_ctrl),
  .o_sparsity24_vector_size(sparsity24_vector_size),
  .o_sparsity24_config(sparsity24_config),
  .i_sparsity24_status(sparsity24_status),
  .i_sparsity24_result_data(sparsity24_result_data),

  // ═════════════════════════════════════════════════════════════════
  // Step 2.4.1: TurboQuant Register Block Connections
  // ═════════════════════════════════════════════════════════════════
  .o_turboquant_ctrl(turboquant_ctrl),
  .o_turboquant_config(turboquant_config),
  .i_turboquant_status(turboquant_status),
  .i_turboquant_result_data(turboquant_result_data),
  .i_turboquant_scale_output(turboquant_scale_output),
```

### 7.6 Port Arbitration Explained

**Why:** TRISC, Sparsity, and TurboQuant all need to read from L1. L1 has a **single read port**.

**Solution:** Priority-based mux in `always_comb`:

```systemverilog
always_comb begin
  if (sparsity_output_valid[i]) begin
    // Sparsity has highest priority
    l1_rd_addr[i] = l1_sparsity_addr[i];
    l1_rd_valid[i] = l1_sparsity_rd_valid[i];
  end else if (turboquant_output_valid[i]) begin
    // TurboQuant next
    l1_rd_addr[i] = l1_turboquant_addr[i];
    l1_rd_valid[i] = l1_turboquant_rd_valid[i];
  end else begin
    // TRISC has default access
    l1_rd_addr[i] = trisc_l1_rd_addr[i];
    l1_rd_valid[i] = trisc_l1_rd_valid[i];
  end
end
```

**Priority order:** Sparsity > TurboQuant > TRISC (based on operand dependencies and latency sensitivity)

---

## 8. Compressed Data: RTL Requirements

### 8.1 Critical Finding

**Can firmware handle compressed data size differences alone?**

**Answer: ❌ NO. RTL modules are MANDATORY.**

**Reason:** The AXI burst length (ARLEN) must be:
1. Calculated **combinationally** (same cycle)
2. Available **same cycle as address** (ARADDR)
3. Injected into **hardware AXI command path**

**Firmware cannot do any of these** — it can only write CSR registers.

### 8.2 Mandatory RTL Modules

#### Module 1: tt_compressed_data_tracker

**Purpose:** Automatically compute physical size from logical size based on compression mode

**Inputs:**
```systemverilog
logic [31:0]  size_logical        // Firmware-requested size (e.g., 1024 elements)
logic [3:0]   compress_mode       // 0=off, 1=2:4_sparse, 2=turboquant
```

**Outputs:**
```systemverilog
logic [31:0]  size_physical       // Actual bytes to transfer
logic [7:0]   arlen_computed      // AXI burst length (0–255)
logic [7:0]   compression_ratio   // Percentage (0–255, where 255=100%)
```

**RTL Logic:**
```systemverilog
always_comb begin
  case (compress_mode)
    4'h0: begin  // No compression
      size_physical = size_logical;
      compression_ratio = 8'hFF;  // 255 = 100%
    end
    4'h1: begin  // 2:4 sparsity
      size_physical = size_logical >> 1;  // Divide by 2
      compression_ratio = 8'h80;  // 128 = 50%
    end
    4'h2: begin  // TurboQuant
      size_physical = (size_logical * 3) >> 5;  // Multiply by 3/32
      compression_ratio = 8'h26;  // 38 ≈ 15%
    end
  endcase
  
  // Convert to AXI beats (64 bytes per beat)
  logic [31:0] beats = size_physical >> 6;
  arlen_computed = (beats > 256) ? 8'hFF : (beats - 1);
end
```

#### Module 2: tt_axi_compressed_interface

**Purpose:** Mux between default and computed ARLEN, inject into AXI AR channel

**RTL Logic:**
```systemverilog
assign axi_arlen = (compress_mode != 4'h0) ? 
                   arlen_compressed : arlen_default;
```

#### Module 3: tt_noc2axi_sparse_decompressor

**Purpose:** Expand compressed data on AXI RDATA path back to logical size

**Latency:** 2–3 cycles (pipelined)

**Example (2:4 sparsity):**
```
Input:  512 bits = 8 elements × 64 bits (compressed)
        Only 4 of 8 valid (2:4 pattern)
        [E0, E2, E4, E6, 0, 0, 0, 0]

Output: 512 bits = 8 elements × 64 bits (decompressed)
        [E0, 0, E2, 0, E4, 0, E6, 0] ← zeros inserted
```

#### Module 4: Extended Overlay Status Register

**Purpose:** Report compression metrics back to firmware

**New Fields:**
```systemverilog
typedef struct packed {
  logic [31:24] l1_occupancy_percent;      // 0–100%
  logic [23:16] compression_ratio;         // Actual ratio achieved
  logic [15:8]  bytes_transferred;         // Physical bytes on AXI
  logic [4:2]   compression_mode_active;
  logic [1]     error;
  logic [0]     done;
} overlay_stream_status_extended_t;
```

### 8.3 Hardware vs Firmware Responsibility Table

| Item | Hardware (RTL) | Firmware (Software) | Dependency |
|------|---|---|---|
| **Size Calculation** (logical → physical) | ✅ tt_compressed_data_tracker.sv | ❌ | RTL mandatory |
| **ARLEN Injection** (into AXI AR) | ✅ tt_axi_compressed_interface.sv | ❌ | RTL mandatory |
| **Data Decompression** (sparse → dense) | ✅ tt_noc2axi_sparse_decompressor.sv | ❌ | RTL mandatory |
| **Status Register** (occupancy, ratio) | ✅ Extended CSR | ✅ Read via CSR | RTL mandatory |
| **Write logical size** (not physical) | ❌ | ✅ Write CSR | Status register |
| **Read occupancy %** | ❌ | ✅ Poll CSR | Status register |
| **L1 allocation** based on ratio | ❌ | ✅ Allocator logic | Status register |
| **TurboQuant metadata persistence** | ❌ | ✅ memcpy scale to L1 | Status register + scale output |

### 8.4 Implementation Order

**Phase 1: RTL (Weeks 1–2)**
1. Design `tt_compressed_data_tracker.sv` (combinational)
2. Design `tt_axi_compressed_interface.sv` (mux, 20 gates)
3. Extend `tt_noc2axi_sparse_decompressor.sv` (2–3 cycles)
4. Extend overlay status register (add fields)
5. Verify timing closure

**Phase 2: Firmware (Weeks 2–3)**
1. Update overlay write to pass logical size
2. Add status register read
3. Add L1 allocator logic
4. Add TurboQuant scale save loop

**Phase 3: Verification (Week 4)**
1. Testbench: verify size calculation
2. Testbench: verify ARLEN injection timing
3. Firmware: test compressed DRAM read
4. End-to-end: compressed KV-cache load

---

## 9. RTL Implementation Code

### 9.1 Complete Signal Declaration Block

**Location:** ~Line 1120 (before `generate` statement)

Copy-paste this entire block:

```systemverilog
// ═════════════════════════════════════════════════════════════════════
// Step 2.4.2: IP Module Signals (Sparsity24 + TurboQuant)
// ═════════════════════════════════════════════════════════════════════

// Sparsity24 Encode Engine CSR Signals
logic [NUM_TENSIX_NEO-1:0]                sparsity24_ctrl_t   sparsity24_ctrl;
logic [NUM_TENSIX_NEO-1:0][31:0]          sparsity24_vector_size;
logic [NUM_TENSIX_NEO-1:0]                sparsity24_config_t sparsity24_config;
logic [NUM_TENSIX_NEO-1:0]                sparsity24_status_t sparsity24_status;
logic [NUM_TENSIX_NEO-1:0][31:0]          sparsity24_result_data;

// Sparsity24 Encode Engine L1 interface
logic [NUM_TENSIX_NEO-1:0][15:0]          l1_sparsity24_addr;
logic [NUM_TENSIX_NEO-1:0]                l1_sparsity24_rd_valid;
logic [NUM_TENSIX_NEO-1:0][63:0]          sparsity24_output_data;
logic [NUM_TENSIX_NEO-1:0]                sparsity24_output_valid;
logic [NUM_TENSIX_NEO-1:0][7:0]           sparsity24_arlen;

// TurboQuant Decode Engine CSR signals
logic [NUM_TENSIX_NEO-1:0]                turboquant_ctrl_t   turboquant_ctrl;
logic [NUM_TENSIX_NEO-1:0]                turboquant_config_t turboquant_config;
logic [NUM_TENSIX_NEO-1:0]                turboquant_status_t turboquant_status;
logic [NUM_TENSIX_NEO-1:0][31:0]          turboquant_result_data;
logic [NUM_TENSIX_NEO-1:0][31:0]          turboquant_scale_output;

// TurboQuant Decode Engine L1 interface
logic [NUM_TENSIX_NEO-1:0][15:0]          l1_turboquant_addr;
logic [NUM_TENSIX_NEO-1:0]                l1_turboquant_rd_valid;
logic [NUM_TENSIX_NEO-1:0][127:0]         turboquant_output_data;
logic [NUM_TENSIX_NEO-1:0]                turboquant_output_valid;

// ═════════════════════════════════════════════════════════════════════
```

### 9.2 Sparsity + TurboQuant Instantiation Block (i==0 and else)

**Location:** ~Line 1234 (after tt_tensix for i==0 closes), and ~Line 1354 (after tt_tensix for else closes)

Copy-paste this:

```systemverilog
      // ═════════════════════════════════════════════════════════════════
      // Step 2.4.2: Sparsity24 Encode Engine (NVIDIA 2:4)
      // ═════════════════════════════════════════════════════════════════

      tt_sparsity24_encode_engine #(
        .DATA_WIDTH(128),
        .COMPRESSED_WIDTH(64),
        .VECTOR_WIDTH(256)
      ) u_sparsity24_encode_engine (
        .i_clk(i_dm_clk),
        .i_rst_n(i_rst_n),
        .i_ctrl(sparsity24_ctrl[i]),
        .i_vector_size(sparsity24_vector_size[i]),
        .i_config(sparsity24_config[i]),
        .o_status(sparsity24_status[i]),
        .o_result_data(sparsity24_result_data[i]),
        .i_l1_data(l1_rd_data[i]),
        .o_l1_addr(l1_sparsity24_addr[i]),
        .o_l1_rd_valid(l1_sparsity24_rd_valid[i]),
        .o_output_data(sparsity24_output_data[i]),
        .o_output_valid(sparsity24_output_valid[i]),
        .o_arlen(sparsity24_arlen[i])
      );

      // ═════════════════════════════════════════════════════════════════
      // Step 2.4.2: TurboQuant Decode Engine
      // ═════════════════════════════════════════════════════════════════

      tt_turboquant_decode_engine #(
        .DATA_WIDTH(128),
        .VECTOR_WIDTH(256),
        .OUTPUT_WIDTH(64)
      ) u_turboquant_decode_engine (
        .i_clk(i_dm_clk),
        .i_rst_n(i_rst_n),
        .i_ctrl(turboquant_ctrl[i]),
        .i_config(turboquant_config[i]),
        .o_status(turboquant_status[i]),
        .o_result_data(turboquant_result_data[i]),
        .o_scale_output(turboquant_scale_output[i]),
        .i_l1_data(l1_rd_data[i]),
        .o_l1_addr(l1_turboquant_addr[i]),
        .o_l1_rd_valid(l1_turboquant_rd_valid[i]),
        .o_output_data(turboquant_output_data[i]),
        .o_output_valid(turboquant_output_valid[i])
      );

      // ═════════════════════════════════════════════════════════════════
      // Port Arbitration: L1 Read Port Mux
      // ═════════════════════════════════════════════════════════════════

      logic [15:0]  l1_rd_addr_final;
      logic         l1_rd_valid_final;

      always_comb begin
        if (sparsity24_output_valid[i]) begin
          l1_rd_addr_final = l1_sparsity24_addr[i];
          l1_rd_valid_final = l1_sparsity24_rd_valid[i];
        end else if (turboquant_output_valid[i]) begin
          l1_rd_addr_final = l1_turboquant_addr[i];
          l1_rd_valid_final = l1_turboquant_rd_valid[i];
        end else begin
          l1_rd_addr_final = trisc_l1_rd_addr[i];
          l1_rd_valid_final = trisc_l1_rd_valid[i];
        end
      end

      assign l1_rd_addr[i] = l1_rd_addr_final;
      assign l1_rd_valid[i] = l1_rd_valid_final;
```

### 9.3 Register Block Port Connections

**Location:** `tt_register_blocks u_register_blocks (` instantiation

Add these inside:

```systemverilog
  // Step 2.4.1 CSR Connections (Sparsity24)
  .o_sparsity24_ctrl(sparsity24_ctrl),
  .o_sparsity24_vector_size(sparsity24_vector_size),
  .o_sparsity24_config(sparsity24_config),
  .i_sparsity24_status(sparsity24_status),
  .i_sparsity24_result_data(sparsity24_result_data),

  // Step 2.4.1 CSR Connections (TurboQuant)
  .o_turboquant_ctrl(turboquant_ctrl),
  .o_turboquant_config(turboquant_config),
  .i_turboquant_status(turboquant_status),
  .i_turboquant_result_data(turboquant_result_data),
  .i_turboquant_scale_output(turboquant_scale_output),
```

---

## 10. Verification and Testing

### 10.1 Pre-Compilation Checklist (50 items)

**File Locations:**
- [ ] Located `tt_tensix_with_l1.sv`
- [ ] Located `tt_register_blocks.sv`
- [ ] Located `tt_sparsity_engine.sv` and `tt_turboquant_decode_engine.sv`

**Signal Declarations (24 signals):**
- [ ] `sparsity_ctrl[NUM_TENSIX_NEO-1:0]` declared
- [ ] `sparsity_zmask[NUM_TENSIX_NEO-1:0]` declared
- [ ] `sparsity_config[NUM_TENSIX_NEO-1:0]` declared
- [ ] `sparsity_status[NUM_TENSIX_NEO-1:0]` declared
- [ ] `sparsity_result_data[NUM_TENSIX_NEO-1:0][31:0]` declared
- [ ] `l1_sparsity_addr[NUM_TENSIX_NEO-1:0][15:0]` declared
- [ ] `l1_sparsity_rd_valid[NUM_TENSIX_NEO-1:0]` declared
- [ ] `sparsity_output_data[NUM_TENSIX_NEO-1:0][127:0]` declared
- [ ] `sparsity_output_valid[NUM_TENSIX_NEO-1:0]` declared
- [ ] `turboquant_ctrl[NUM_TENSIX_NEO-1:0]` declared
- [ ] `turboquant_config[NUM_TENSIX_NEO-1:0]` declared
- [ ] `turboquant_status[NUM_TENSIX_NEO-1:0]` declared
- [ ] `turboquant_result_data[NUM_TENSIX_NEO-1:0][31:0]` declared
- [ ] `turboquant_scale_output[NUM_TENSIX_NEO-1:0][31:0]` declared
- [ ] `l1_turboquant_addr[NUM_TENSIX_NEO-1:0][15:0]` declared
- [ ] `l1_turboquant_rd_valid[NUM_TENSIX_NEO-1:0]` declared
- [ ] `turboquant_output_data[NUM_TENSIX_NEO-1:0][127:0]` declared
- [ ] `turboquant_output_valid[NUM_TENSIX_NEO-1:0]` declared

**Instantiation (Port Connections):**
- [ ] Sparsity `.i_clk(i_dm_clk)` — NOT `i_ai_clk`
- [ ] Sparsity `.i_ctrl(sparsity_ctrl[i])` — indexed
- [ ] Sparsity `.i_l1_data(l1_rd_data[i])` — correct existing signal
- [ ] Sparsity `.o_l1_addr(l1_sparsity_addr[i])` — indexed
- [ ] TurboQuant `.i_clk(i_dm_clk)` — NOT `i_ai_clk`
- [ ] TurboQuant `.o_scale_output(turboquant_scale_output[i])` — indexed
- [ ] TurboQuant `.i_l1_data(l1_rd_data[i])` — same source as Sparsity
- [ ] TurboQuant `.o_l1_addr(l1_turboquant_addr[i])` — indexed

**Port Arbitration:**
- [ ] `always_comb` block (combinational, no latency)
- [ ] Sparsity priority > TurboQuant > TRISC
- [ ] Mux selects correct `l1_rd_addr[i]` and `l1_rd_valid[i]`

**Register Block:**
- [ ] `.o_sparsity_ctrl(sparsity_ctrl)` connected
- [ ] `.o_turboquant_ctrl(turboquant_ctrl)` connected
- [ ] `.i_sparsity_status(sparsity_status)` connected
- [ ] `.i_turboquant_scale_output(turboquant_scale_output)` connected

### 10.2 Compilation Verification

```bash
# Syntax check
verilator --cc tt_tensix_with_l1.sv

# Look for undefined signals
grep -n "sparsity_ctrl\|turboquant\|l1_sparsity\|l1_turboquant" output.log | grep "undefined\|error"

# Verify clock domain usage
grep -n "\.i_clk.*i_dm_clk" tt_tensix_with_l1.sv | grep "sparsity\|turboquant"

# Count generate block depth (should close properly)
grep -nE "generate|for|if|else|end|endgenerate" tt_tensix_with_l1.sv | tail -20
```

### 10.3 Functional Verification (Firmware Level)

**Test 1: Sparsity CSR Access**
```c
// Write CSR
TRISC_WRITE_CSR(SPARSITY_CTRL, 0x00000001);
TRISC_WRITE_CSR(SPARSITY_ZMASK, 0xFFFFFF00);  // Skip last 8 planes

// Poll
while (!(TRISC_READ_CSR(SPARSITY_STATUS) & DONE)) { }

// Verify
uint32_t status = TRISC_READ_CSR(SPARSITY_STATUS);
assert((status >> 8) < 100);  // Occupancy < 100%
```

**Test 2: TurboQuant Scale Output**
```c
// Trigger compression
TRISC_WRITE_CSR(TURBOQUANT_CTRL, 0x00000001);

// Wait
while (!(TRISC_READ_CSR(TURBOQUANT_STATUS) & DONE)) { }

// Read scale factor (critical!)
float scale = *(float*)&TRISC_READ_CSR(TURBOQUANT_SCALE_OUTPUT);
assert(scale > 0.0 && scale < 100.0);
```

**Test 3: L1 Port Arbitration**
```c
// Concurrent access test
// Start Sparsity operation (should get L1 port)
// Simultaneously, TRISC tries to access L1 (should be blocked)
// Verify no data corruption
```

---

## 11. Firmware Programming Guide

### 11.1 CSR Access Macros

```c
#define CSR_SPARSITY24_CTRL          0x0200
#define CSR_SPARSITY24_VECTOR_SIZE  0x0204
#define CSR_SPARSITY24_CONFIG        0x0208
#define CSR_SPARSITY24_STATUS        0x020C
#define CSR_SPARSITY24_RESULT        0x0210

#define CSR_TURBOQUANT_CTRL      0x0280
#define CSR_TURBOQUANT_CONFIG    0x0284
#define CSR_TURBOQUANT_STATUS    0x0288
#define CSR_TURBOQUANT_RESULT    0x028C
#define CSR_TURBOQUANT_SCALE     0x0290

// Status register bit fields
#define STATUS_DONE              (1 << 0)
#define STATUS_ERROR             (1 << 1)
#define STATUS_OCCUPANCY_SHIFT   8
#define STATUS_RATIO_SHIFT       16
```

### 11.2 Sparsity24 Kernel Example (NVIDIA 2:4)

```c
void apply_sparsity24_compression(uint32_t vector_size_elements) {
  // Configure Sparsity24 engine (2:4 mode, always 50% compression)
  TRISC_WRITE_CSR(CSR_SPARSITY24_VECTOR_SIZE, vector_size_elements);
  TRISC_WRITE_CSR(CSR_SPARSITY24_CONFIG, METADATA_BASIC);
  
  // Enable Sparsity24 (automatic 2:4 pattern compression)
  TRISC_WRITE_CSR(CSR_SPARSITY24_CTRL, 0x00000001);
  
  // Poll for completion
  uint32_t timeout = 10000;
  while (timeout-- > 0) {
    uint32_t status = TRISC_READ_CSR(CSR_SPARSITY24_STATUS);
    if (status & STATUS_DONE) break;
  }
  
  if (!(TRISC_READ_CSR(CSR_SPARSITY24_STATUS) & STATUS_DONE)) {
    printf("ERROR: Sparsity24 timeout\n");
    return;
  }
  
  // Read occupancy and compression ratio (should always be 128 = 50%)
  uint32_t status = TRISC_READ_CSR(CSR_SPARSITY24_STATUS);
  uint8_t occupancy = (status >> STATUS_OCCUPANCY_SHIFT) & 0xFF;
  uint8_t ratio = (status >> STATUS_RATIO_SHIFT) & 0xFF;
  
  printf("Sparsity24 (2:4): %d%% L1 occupancy, %d%% compression (fixed 50%%)\n",
         occupancy, (ratio * 100) / 255);
  
  // Note: DRAM bandwidth also reduced 50% due to automatic ARLEN halving
}
```

### 11.3 TurboQuant Kernel Example (CRITICAL SCALE PERSISTENCE)

```c
void compress_kv_vector_turboquant(uint32_t vector_index) {
  // Configure
  TRISC_WRITE_CSR(CSR_TURBOQUANT_CONFIG, vector_index);
  
  // Enable
  TRISC_WRITE_CSR(CSR_TURBOQUANT_CTRL, 0x00000001);
  
  // Poll for completion
  while (!(TRISC_READ_CSR(CSR_TURBOQUANT_STATUS) & STATUS_DONE)) { }
  
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // CRITICAL: Save scale factor IMMEDIATELY
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  
  // 1. Read compressed data (48 bytes)
  uint8_t compressed_data[48];
  memcpy(compressed_data, (void*)L1_KV_BUFFER, 48);
  
  // 2. Read scale factor from CSR
  uint32_t scale_u32 = TRISC_READ_CSR(CSR_TURBOQUANT_SCALE);
  float scale = *(float*)&scale_u32;
  
  // 3. Write scale to L1 immediately after compressed data (52 bytes total)
  memcpy((void*)(L1_KV_BUFFER + 48), &scale, 4);
  
  // 4. Update metadata
  KV_METADATA[vector_index].compressed = 1;
  KV_METADATA[vector_index].scale = scale;
  KV_METADATA[vector_index].size = 52;  // 48 data + 4 scale
  
  printf("Vector %d: compressed with scale %.6f\n", vector_index, scale);
}
```

### 11.4 L1 Allocation with Compression Awareness

```c
void allocate_l1_with_compression_ratio(
    uint32_t logical_bytes,
    uint8_t compression_ratio  // from status register (0–255)
) {
  // Compute actual occupancy
  // ratio=255 (100%) → 100% of logical size
  // ratio=128 (50%)  → 50% of logical size
  // ratio=38 (15%)   → 15% of logical size
  
  uint32_t actual_bytes = (logical_bytes * (uint32_t)compression_ratio) / 255;
  
  printf("Allocating %d bytes for logical %d (ratio %d%%)\n",
         actual_bytes, logical_bytes, (compression_ratio * 100) / 255);
  
  L1_ALLOCATOR.allocate(actual_bytes);
}
```

---

## 12. References and Supporting Documents

### 12.1 In This Directory (/secure_data_from_tt/20260221/DOC/N1B0/)

| Document | Purpose |
|----------|---------|
| **IP_Design_Guide_for_NPU.md** (v1.1) | Original guide (sections 1–7) |
| **Tensix_Cluster_IP_Integration_Implementation.md** | RTL patterns and examples |
| **Step_2_4_2_Explained.md** | Conceptual overview of Step 2.4.2 |
| **Step_2_4_2_Template_vs_Implementation.md** | Template vs real implementation comparison |
| **Step_2_4_2_RTL_Implementation_Code.sv** | Copy-paste ready SystemVerilog |
| **Step_2_4_2_Patch_Guide.md** | Exact line-by-line modifications |
| **Step_2_4_2_Implementation_Verification.md** | 120-item verification checklist |
| **Compressed_Data_RTL_Requirements.md** | Why RTL modules are mandatory |

### 12.2 N1B0 HDD References

| Section | Topic |
|---------|-------|
| **§2: Tensix Tile** | L1 SRAM, FPU, TRISC, TDMA architecture |
| **§3: Overlay Engine** | Stream controller, context switching, L1 access |
| **§4: NOC2AXI Composite** | AXI master interface, address translation |
| **§14: SFR Summary** | System Function Registers address map |

### 12.3 Related Architecture Documents

| Memory Document | Topic | Keywords |
|-----------|-------|----------|
| **M10: INT16 LLM Guide** | Dimension glossary, tiling, GEMM, KV-cache | gemm, k_tile, m_tile, kv-cache |
| **M21: SFPU Architecture** | Scalar FP unit, transcendental ops, quantization | sfpu, exp, log, quantization, gelu |
| **M25: TurboQuant Impl** | Dense rotation + scalar quantization | rotation, scalar, gemm, 102cy |
| **M26: TurboQuant HDD** | FWHT-based rotation, structured, 12cy | fwht, structured, 12cy, 50K gates |
| **M27: TurboQuant Recommendation** | FWHT recommended, 10× smaller than dense | fwht_vs_dense, area, power, latency |

---

## Quick-Start Checklist

### For RTL Engineers

1. **Read Sections 7 & 9** — Understand Step 2.4.2 and copy RTL code
2. **Read Section 8** — Understand compressed data RTL requirements
3. **Apply 4 modifications** — Signal declarations, instantiations (both blocks), register block connections
4. **Compile & fix** — Verilator syntax check, resolve any undefined signals
5. **Verify** — Run pre-compilation checklist (50 items)

**Estimated time:** 3.5–5 hours

### For Firmware Engineers

1. **Read Sections 4 & 11** — Understand CSR and firmware programming guide
2. **Copy firmware kernels** — Sparsity and TurboQuant examples (Section 11)
3. **Test CSR access** — Write → poll → read cycle
4. **Test compression** — End-to-end with real data
5. **Verify metadata** — Ensure scale factor persists (TurboQuant critical)

**Estimated time:** 2–3 hours

### For Hardware Architects

1. **Read Sections 1–3** — Understand integration phases
2. **Review Sections 5–6** — Sparsity and TurboQuant features
3. **Review Section 8** — Compressed data RTL requirements
4. **Plan verification** — Section 10 checklist
5. **Schedule Phase 1–5** — Phases 1–5 timeline

---

## Summary

This comprehensive guide provides everything needed to:

✅ **Add IP modules to N1B0** (Sparsity24 Encode Engine, TurboQuant Decode Engine)  
✅ **Understand Step 2.4.2** (instantiation in cluster hierarchy)  
✅ **Implement RTL** (signal declarations, instantiation, arbitration)  
✅ **Handle compressed data** (hardware-firmware split responsibilities)  
✅ **Verify correctness** (120+ item checklist)  
✅ **Write firmware** (CSR access, polling, scale persistence)  

**Start with Section 7 (Step 2.4 In-Depth) and Section 9 (RTL Implementation Code).**

---

**Document Version:** 2.0 (Merged)  
**Last Updated:** 2026-04-04  
**Status:** Ready for Implementation  
**Questions?** Refer to supporting docs in /secure_data_from_tt/20260221/DOC/N1B0/


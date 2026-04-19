# Sparsity vs Sparsity24 Engine Classification

**Document Version:** 1.0  
**Date:** 2026-04-04  
**Purpose:** Clarify the distinction between existing Sparsity Engine (Z-plane masking) and new Sparsity24 Decode Engine (NVIDIA 2:4) in N1B0

---

## Overview

N1B0 has **two independent sparsity implementations** that serve different compression purposes:

| Aspect | **Sparsity (Existing)** | **Sparsity24 (NEW - NVIDIA 2:4)** |
|--------|------------------------|--------------------------------|
| **Purpose** | Z-plane masking for L1 optimization | Structured 2:4 sparsity for inference acceleration |
| **Compression Location** | L1 local, per-tile | End-to-end pipeline (L1 → DRAM) |
| **Compression Target** | L1 bandwidth | DRAM bandwidth + AXI load reduction |
| **Compression Ratio** | Variable (depends on mask) | Fixed 50% (2 of 4 elements) |
| **DRAM Impact** | None | 50% reduction via automatic ARLEN halving |
| **Status** | Already implemented | **This guide** (new in this design cycle) |

---

## Sparsity Engine (Existing)

### Purpose
Implement Z-plane masking at the L1 boundary to reduce L1 read bandwidth when loading tensor data.

### Architecture
```
TRISC L1 Load Request
  ↓
Z-plane Decoder (zmask[31:0] register)
  ↓
Plane Filtering (skip planes marked as zero)
  ↓
Optimized L1 Read (fewer memory accesses)
  ↓
Reduced L1 bandwidth (only non-zero planes loaded)
```

### Key Characteristics
- **Input:** 128-bit L1 data
- **Control:** Z-mask CSR (firmware configurable)
- **Output:** Filtered L1 data (variable size)
- **Latency:** 1–2 cycles
- **Scope:** Per-tile, local to L1
- **Firmware Control:** TRISC writes z-mask before operation

### Use Case
When loading activation tensors with known zero Z-planes (e.g., padding zeros), skip those planes entirely to reduce L1 bandwidth. No DRAM impact.

### Example
```
Tensor shape: [M, K, Z] where Z=32 planes
Z-mask: 0xFFFFFF00 (skip last 8 planes)

Load bandwidth reduction: 8/32 = 25% savings
```

---

## Sparsity24 Decode Engine (NEW - NVIDIA 2:4)

### Purpose
Implement NVIDIA 2:4 structured sparsity compression across the entire inference pipeline (L1 → DRAM) with hardware-automatic ARLEN management.

### Architecture
```
L1 SRAM (128-bit tensor data)
  ↓
2:4 Pattern Detector (identify sparse elements)
  ↓
Compression Encoder (extract 2 of 4 elements)
  ↓
ARLEN Calculator (compute burst length combinationally) ← **CRITICAL**
  ↓
Compressed Output (64-bit, 50% reduction)
  ↓
AXI Read Port (automatic ARLEN halving in master)
  ↓
DRAM (50% fewer memory accesses)
```

### Key Characteristics
- **Input:** 128-bit L1 data (2:4 sparse structure)
- **Control:** Simple enable + vector size CSR
- **Output:** 64-bit compressed data (2 of 4 elements)
- **Latency:** 2–3 cycles
- **Scope:** Cluster-wide (affects DRAM bandwidth)
- **Firmware Control:** Enable/disable, read status and occupancy
- **Hardware Automatic:** ARLEN calculation (no firmware overhead)

### Use Case
For inference with 2:4 structured sparsity matrices (weights or activations), compress data as it flows through the pipeline to reduce DRAM bandwidth by 50%.

### Example
```
Original matrix (100 elements, 4 per row):
Row 1: [V1, 0, V2, 0, V3, 0, V4, 0, ...] (2:4 pattern)

Compressed (50 elements, 2 per row):
Row 1: [V1, V2, V3, V4, ...] (only non-zero)

DRAM Transfer Reduction: 50% (100 → 50 elements)
AXI Burst Length: Halved (ARLEN_computed = ARLEN_default / 2)
```

---

## Detailed Comparison Table

### Control and Interface

| Feature | Sparsity | Sparsity24 |
|---------|----------|-----------|
| **Module Name** | `sparsity_engine` (existing) | `tt_sparsity24_encode_engine` (new) |
| **CSR Base Address** | 0x0000 (TBD - existing) | 0x0200 (new IP reservation) |
| **Control Register** | Existing SPARSITY_CTRL | SPARSITY24_CTRL (0x0200) |
| **Configuration Register** | Existing (mask-based) | SPARSITY24_CONFIG (0x0208) |
| **Mask Register** | SPARSITY_ZMASK (z-plane) | None (fixed 2:4 pattern) |
| **Status Register** | SPARSITY_STATUS (existing) | SPARSITY24_STATUS (0x020C) |

### Data Path

| Feature | Sparsity | Sparsity24 |
|---------|----------|-----------|
| **Input Width** | 128-bit | 128-bit |
| **Output Width** | Variable (1–128 bit) | Fixed 64-bit (50% compression) |
| **L1 Interface** | L1 read port | L1 read port (arbitrated) |
| **DRAM Interface** | None (L1-local) | AXI master (automatic ARLEN) |
| **Compression Ratio** | Variable per mask | Fixed 50% (2:4 design) |

### Operation Mode

| Feature | Sparsity | Sparsity24 |
|---------|----------|-----------|
| **Activation** | Via z-mask CSR | Via ENABLE CSR |
| **Pattern Detection** | Manual (firmware sets mask) | Automatic (hardware detects 2:4) |
| **Latency** | 1–2 cycles | 2–3 cycles |
| **Pipelining** | Sequential | Pipelined |
| **Firmware Effort** | Medium (compute mask) | Low (enable/monitor) |

### Performance Impact

| Metric | Sparsity | Sparsity24 |
|--------|----------|-----------|
| **L1 Bandwidth Reduction** | Up to 75% | 0% (L1 unchanged) |
| **L1 Occupancy Impact** | Reduced | 0% (no change) |
| **DRAM Bandwidth Reduction** | 0% | 50% (fixed) |
| **DRAM Occupancy Impact** | None | 50% reduction |
| **Inference Latency** | No impact (pre-load filter) | 2–3 cycle overhead |
| **Power Consumption** | Minimal | Reduced DRAM accesses |

---

## When to Use Each

### Use Sparsity (Existing)
- Loading activation tensors with known zero Z-planes
- Reducing L1 bandwidth for padding-heavy data
- Local per-tile optimization (no system-wide impact)
- Variable compression needs per vector

### Use Sparsity24 (NEW)
- Inference with 2:4 structured sparsity weights
- 2:4 sparse activations from prior layer
- Need to reduce DRAM bandwidth system-wide
- Consistent 50% compression ratio acceptable

### Use Both Together
```
Scenario: 2:4 sparse weights + padding in activation cache

Step 1: Load weight matrix
  → Sparsity24 compresses to 50% on DRAM load
  → Delivers 64-bit compressed vectors

Step 2: Load activation cache (has padding zeros)
  → Sparsity masks out padding Z-planes
  → Delivers only non-padded data to compute

Result: Combined compression from both engines
```

---

## Signal Naming Convention

### Sparsity (Existing)
```
Signals: (existing implementation, not shown here)
CSRs: SPARSITY_* registers
```

### Sparsity24 (NEW)
```
Signals:
  - sparsity24_ctrl[NUM_TENSIX_NEO-1:0]
  - sparsity24_vector_size[NUM_TENSIX_NEO-1:0][31:0]
  - sparsity24_config[NUM_TENSIX_NEO-1:0]
  - sparsity24_status[NUM_TENSIX_NEO-1:0]
  - sparsity24_output_data[NUM_TENSIX_NEO-1:0][63:0]
  - sparsity24_arlen[NUM_TENSIX_NEO-1:0][7:0]

CSRs:
  - SPARSITY24_CTRL (0x0200)
  - SPARSITY24_VECTOR_SIZE (0x0204)
  - SPARSITY24_CONFIG (0x0208)
  - SPARSITY24_STATUS (0x020C)
  - SPARSITY24_RESULT (0x0210)
```

---

## Implementation Locations

### Sparsity (Existing)
- **Location:** Within Tensix tile (existing, not modified)
- **Control:** Via existing register block

### Sparsity24 (NEW)
- **File:** `tt_tensix_with_l1.sv`
- **Generate Block:** Lines 1121–1359
- **Instantiation:** After `tt_tensix` instantiation (lines ~1234 for i==0, ~1354 for else)
- **Register Block:** tt_register_blocks.sv (CSR connections for Sparsity24)
- **Reference:** `IP_Design_and_Integration_Comprehensive_Guide.md` Section 7 & 9

---

## Firmware API Comparison

### Sparsity (Existing) - Pseudocode
```c
// Compute z-mask for tensor (24 valid planes, 8 padding planes)
uint32_t zmask = 0xFFFFFF00;  // Bit i = 1 means skip plane i

// Write mask to register
TRISC_WRITE_CSR(SPARSITY_ZMASK, zmask);

// Subsequent L1 loads skip the masked planes
```

### Sparsity24 (NEW) - Firmware API
```c
// Enable Sparsity24 for 2:4 sparse matrix
TRISC_WRITE_CSR(CSR_SPARSITY24_VECTOR_SIZE, num_elements);
TRISC_WRITE_CSR(CSR_SPARSITY24_CTRL, ENABLE);

// Poll for completion
while (!(TRISC_READ_CSR(CSR_SPARSITY24_STATUS) & DONE)) { }

// Read compression metrics
uint32_t status = TRISC_READ_CSR(CSR_SPARSITY24_STATUS);
uint8_t occupancy = (status >> 8) & 0xFF;  // L1 usage %
uint8_t ratio = (status >> 16) & 0xFF;     // 128 = 50% (fixed)
```

---

## Critical Difference: ARLEN Handling

### Sparsity (Existing)
- L1-local, no system-wide AXI changes
- No ARLEN management needed

### Sparsity24 (NEW)
- **ARLEN automatically computed combinationally:**
  ```
  arlen_compressed = arlen_default / 2
  ```
- **Hardware automatically injects into AXI master** (no firmware register)
- **Critical reason:** ARLEN must be available same cycle as ARADDR
- **This is why firmware alone is insufficient** (see Comprehensive Guide §8)

---

## Summary

| Aspect | Sparsity | Sparsity24 |
|--------|----------|-----------|
| **Type** | Z-plane masking | 2:4 structured compression |
| **Scope** | L1-local | System-wide (DRAM) |
| **Compression** | Variable | Fixed 50% |
| **Latency Impact** | Minimal | 2–3 cycles |
| **DRAM Impact** | None | 50% reduction |
| **Firmware Complexity** | Medium | Low |
| **Status** | Existing | **NEW (this guide)** |
| **Reference** | Existing HDD | Comprehensive Guide Sect. 5, 7, 9 |

---

**For Sparsity24 Implementation:** See `IP_Design_and_Integration_Comprehensive_Guide.md`  
**For Sparsity (Existing):** Consult N1B0 HDD or existing documentation


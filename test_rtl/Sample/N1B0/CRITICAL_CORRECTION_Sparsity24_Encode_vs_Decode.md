# CRITICAL CORRECTION: Sparsity24 is ENCODER, NOT DECODER

**Date:** 2026-04-04  
**Severity:** CRITICAL 🚨  
**Status:** Corrected across all documentation

---

## The Problem

**Incorrect Naming:** Sparsity24 engine was called "Sparsity24 Decode Engine"

**Why This is Wrong:** 

The Sparsity24 engine:
- **Inputs**: 128-bit L1 SRAM data (sparse with 2:4 pattern)
- **Operation**: COMPRESSES/ENCODES the sparse data (removes zeros)
- **Outputs**: 64-bit compressed output (50% of input size)
- **ARLEN Effect**: Halves AXI burst length (ARLEN_out = ARLEN_in / 2)

This is **ENCODING/COMPRESSION**, not decoding!

---

## The Correction

### What Changed

| Aspect | Was | Now |
|--------|-----|-----|
| Module Name | `tt_sparsity24_decode_engine` | `tt_sparsity24_encode_engine` |
| Instance Name | `u_sparsity24_decode_engine_0` | `u_sparsity24_encode_engine_0` |
| Documentation | "Sparsity24 Decode Engine" | "Sparsity24 Encode Engine" |
| Operation Term | "Decompression" | "Encoding" / "Compression" |

### Why This Matters

**Semantic Clarity:**
- **Encoder/Compressor** (Sparsity24): Takes sparse data → outputs compressed data
- **Decoder/Decompressor** (separate module): Takes compressed data → outputs original data

**Data Path:**
```
L1 SRAM (128-bit sparse)
  ↓ (Sparsity24 ENCODER)
64-bit compressed
  ↓ (via AXI to DRAM)
DRAM (compressed storage)
  ↓ (via RDATA path DECODER)
128-bit decompressed
```

### Address Calculation (Encoding)

**L1 Address:**
- Input address: No change (points to L1 word)
- Output address: Same (data extracted in-place)

**ARLEN Calculation (CRITICAL):**
```
Input:  ARLEN_original (for 128-bit transfers)
Output: ARLEN_compressed = ARLEN_original / 2

Example:
- Read 16 elements × 128-bit = 128 elements total
- ARLEN_original = 16 (burst of 16 transfers)
- ARLEN_compressed = 8 (burst of 8 transfers, since output is half-sized)
```

**Size Calculation:**
```
Logical Size: N elements × 128-bit each
Physical Size (after encoding): N × 128-bit / 2 = N × 64-bit
Compression Ratio: 50% (fixed by 2:4 design)
```

---

## RTL Implementation (Corrected)

### Clock Domain
```systemverilog
tt_sparsity24_encode_engine #(...) u_sparsity24_encode_engine_0 (
  .i_clk(i_ai_clk[i]),                    // ai_clk (NOT dm_clk)
  .i_rst_n(i_rst_n),
  // ... CSR inputs ...
  .i_l1_data(l1_rd_data[i]),              // 128-bit input (sparse 2:4)
  .o_output_data(sparsity24_output_data[i]), // 64-bit output (50% compression)
  .o_arlen(sparsity24_arlen[i])           // ARLEN = input_ARLEN / 2
);
```

### Firmware Behavior
```c
void apply_sparsity24_encoding(uint32_t num_elements) {
  // Enable encoder (NOT decoder)
  TRISC_WRITE_CSR(SPARSITY24_CTRL, ENABLE);
  
  // Wait for encoding completion
  while (!(TRISC_READ_CSR(SPARSITY24_STATUS) & DONE)) { }
  
  // Calculate physical size after encoding
  uint32_t physical_bytes = (num_elements * 16) / 2;  // 50% reduction
  uint32_t compressed_arlen = original_arlen / 2;     // ARLEN halved
}
```

---

## Files Updated

✅ **IP_Design_and_Integration_Comprehensive_Guide.md**
- Section 5.1: Module name and semantic clarification
- Section 5.2: Clock domain and address calculation details
- Section 5.3: RTL code with correct ai_clk
- Section 5.4: Firmware showing encoding operation
- Section 5.5: Performance metrics for encoder

✅ **Step_2_4_2_RTL_Implementation_Code.sv**
- Module: `tt_sparsity24_encode_engine`
- Instance: `u_sparsity24_encode_engine_0`

✅ **Step_2_4_2_Patch_Guide.md**
- All code patches use `tt_sparsity24_encode_engine`

✅ **Sparsity_vs_Sparsity24_Classification.md**
- Module name: `tt_sparsity24_encode_engine`

✅ **Clock_Domain_Verification_Report.md**
- References updated to Encode Engine

---

## Key Distinctions

### Sparsity24 Encode Engine (NEW - This Implementation)
- **Function**: COMPRESSES sparse 2:4 data
- **Input**: 128-bit L1 data (sparse pattern)
- **Output**: 64-bit compressed (2 non-zero per 4 elements)
- **ARLEN**: Halved (50% data reduction)
- **Clock**: ai_clk
- **Latency**: 2–3 cycles

### Decompression (SEPARATE - On RDATA Path)
- **Function**: DECOMPRESSES 64-bit data back to 128-bit
- **Module**: `tt_noc2axi_sparse_decompressor`
- **Input**: 64-bit compressed from DRAM
- **Output**: 128-bit decompressed
- **Latency**: 2–3 cycles

---

## Authority Level

✅ **Semantic correction based on data flow analysis**
- Input data: 2:4 sparse (128-bit)
- Operation: Extracts 2 non-zero per 4 → 64-bit output
- This IS encoding/compression, NOT decoding

---

## Summary

**OLD (WRONG):**
- "Sparsity24 Decode Engine"
- Implies decompression (taking compressed data → expanding it)

**NEW (CORRECT):**
- "Sparsity24 Encode Engine"
- Correctly reflects compression (taking sparse data → removing zeros)
- 50% output size due to 2:4 pattern
- ARLEN automatically halved in hardware

**Test Verification:**
- Confirm module instantiation uses `i_ai_clk[i]` (NOT dm_clk)
- Confirm ARLEN output = input_ARLEN / 2
- Confirm output width = 64-bit (50% of 128-bit input)

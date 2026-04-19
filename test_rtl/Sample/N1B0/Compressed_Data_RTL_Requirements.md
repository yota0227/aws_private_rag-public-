# Compressed Data: RTL Requirements vs Firmware Changes
**Document Version:** 1.0  
**Date:** 2026-04-04  
**Clarification:** Why firmware-only approach is insufficient; which RTL modules are mandatory

---

## Executive Summary

### **Can firmware handle size differences alone?**

**Answer: ❌ NO. RTL modules are MANDATORY.**

**Reason:** AXI burst length (ARLEN) must be calculated in real-time and injected into the hardware command path during the address cycle. Firmware cannot directly drive AXI signals.

---

## Part 1: RTL Modules Required (MANDATORY, NOT OPTIONAL)

### Module 1: tt_compressed_data_tracker.sv

**Purpose:** Automatically compute physical size from logical size and compression mode

**Location:** In overlay stream controller or NIU register interface

**Inputs:**
```systemverilog
logic [31:0]  size_logical        // What firmware requested (e.g., 1024 elements)
logic [3:0]   compress_mode       // 0=off, 1=2:4_sparse, 2=turboquant, 3=reserved
```

**Outputs:**
```systemverilog
logic [31:0]  size_physical       // Actual bytes to transfer (e.g., 2048 for 2:4)
logic [7:0]   arlen_computed      // AXI burst length (0-255)
logic [7:0]   compression_ratio   // Percentage (0-255, where 255=100%)
```

**RTL Logic:**
```systemverilog
always_comb begin
  case (compress_mode)
    4'h0: begin
      size_physical = size_logical;
      compression_ratio = 8'hFF;  // 255 = 100% (uncompressed)
    end
    4'h1: begin
      size_physical = size_logical >> 1;  // 2:4: divide by 2
      compression_ratio = 8'h80;  // 128 = 50%
    end
    4'h2: begin
      size_physical = (size_logical * 3) >> 5;  // TurboQuant: multiply by 3/32
      compression_ratio = 8'h26;  // 38 ≈ 15%
    end
    default: begin
      size_physical = size_logical;
      compression_ratio = 8'h00;
    end
  endcase
  
  // Convert to AXI beats (64 bytes per beat)
  logic [31:0] beats = size_physical >> 6;
  arlen_computed = (beats > 256) ? 8'hFF : (beats - 1);
end
```

**Why firmware CANNOT do this:**
- ✗ ARLEN must be available **same cycle** as ARADDR
- ✗ Firmware cannot inject values into AXI command path
- ✗ Must be combinational RTL (no latency)

**Estimated area:** ~50 gates

---

### Module 2: tt_axi_compressed_interface.sv

**Purpose:** Mux between default ARLEN and compressed ARLEN; inject into AXI AR bus

**Location:** Between overlay stream controller and AXI master interface

**Inputs:**
```systemverilog
logic [7:0]   arlen_default        // Default ARLEN if no compression
logic [7:0]   arlen_compressed     // Computed ARLEN from tt_compressed_data_tracker
logic [3:0]   compress_mode        // Compression active?
```

**Outputs:**
```systemverilog
logic [7:0]   axi_arlen           // Selected ARLEN (drives AXI AR channel)
```

**RTL Logic:**
```systemverilog
assign axi_arlen = (compress_mode != 4'h0) ? arlen_compressed : arlen_default;
```

**Why firmware CANNOT do this:**
- ✗ AXI ARLEN is a hardware signal on the master port
- ✗ Firmware has no register to write ARLEN directly
- ✗ Must be a hardware mux on the data path

**Estimated area:** ~20 gates (simple mux)

---

### Module 3: tt_noc2axi_sparse_decompressor.sv (2–3 cycles)

**Purpose:** Expand compressed AXI RDATA back to logical size

**Location:** On AXI RDATA path, between NIU RDATA FIFO and L1 side-channel write port

**Inputs:**
```systemverilog
logic [511:0]  rdata              // Compressed flit from AXI (512 bits = 64 bytes)
logic [3:0]    compress_mode      // Which decompression pattern
logic [511:0]  validity_mask      // Which lanes are populated (2:4 sparsity)
```

**Outputs:**
```systemverilog
logic [511:0]  rdata_decompressed // Expanded flit with zeros inserted
```

**Latency:** 2–3 cycles (pipelined)

**Example: 2:4 Sparsity**
```
Input:  512 bits = 8 elements × 64 bits (compressed)
        Only 4 of 8 elements are valid (2:4 pattern)
        E.g.: [E0, E2, E4, E6, reserved, reserved, reserved, reserved]
        
Decode: validity_mask tells us which lanes have data
        (e.g., 0x0F = elements 0,1,2,3 are valid)
        
Output: 512 bits = 8 elements × 64 bits (decompressed)
        [E0, E2, E4, E6, 0, 0, 0, 0]
        (zeros inserted for masked positions)
```

**Why firmware CANNOT do this:**
- ✗ Must happen on **hardware data path** (AXI RDATA)
- ✗ Firmware never sees raw compressed data
- ✗ Decompression pattern is hardware-specific
- ✗ Must be pipelined for timing

**Estimated area:** ~50 K gates (logic + pipelining)

---

### Module 4: Extended Overlay Stream Status Register

**Purpose:** Report compression metrics back to firmware

**Location:** Overlay stream status register space (already exists, extend with new fields)

**New Fields:**
```systemverilog
typedef struct packed {
  logic [31:24] l1_occupancy_percent;      // 0–100% of tile's L1 used
  logic [23:16] compression_ratio;         // 0–255 (255=100% uncompressed)
  logic [15:8]  bytes_transferred;         // Physical bytes on AXI (compressed)
  logic [7:5]   reserved;
  logic [4:2]   compression_mode_active;   // Which mode is active
  logic [1]     error;
  logic [0]     done;
} overlay_stream_status_extended_t;
```

**Why firmware CANNOT compute this:**
- ✗ Occupancy % requires hardware counter (in-flight tracking)
- ✗ Compression ratio must match actual data transferred
- ✗ Firmware has no visibility into hardware state

**Estimated area:** ~5 K gates (counters + CSR register)

---

## Part 2: Firmware Changes (DO NOT require RTL)

### Change 1: Write Logical Size (Not Physical Size)

**Before (RTL changes not in place):**
```c
// Firmware had to calculate physical size
uint32_t compressed_addr = 0x80000000;
uint32_t num_elements = 1024;

uint32_t cmd = {
  .src_addr = compressed_addr,
  .size = num_elements / 2,              // ← Firmware divides by 2
  .compress_mode = 1,
};
OVERLAY_STREAM_WRITE(0, cmd);
```

**After (RTL modules in place):**
```c
// Firmware passes logical size; hardware computes physical
uint32_t cmd = {
  .src_addr = compressed_addr,
  .size = num_elements,                  // ← Just logical size!
  .compress_mode = 1,                    // Hardware handles the rest
};
OVERLAY_STREAM_WRITE(0, cmd);
```

**No RTL dependency:** Simple register write, same data type

---

### Change 2: Read Extended Status Register

**New Firmware Code:**
```c
void track_compressed_transfer(void) {
  uint32_t status = READ_CSR(OVERLAY_STATUS_REG);
  
  // Extract fields
  uint32_t occupancy = (status >> 24) & 0xFF;          // 0–100%
  uint32_t ratio = (status >> 16) & 0xFF;              // 0–255
  uint32_t bytes_physical = (status >> 8) & 0xFF;      // Compressed bytes
  uint32_t error = (status >> 1) & 0x1;
  uint32_t done = status & 0x1;
  
  printf("Transfer complete:\n");
  printf("  L1 occupancy: %d%%\n", occupancy);
  printf("  Compression: %d%%\n", (ratio * 100) / 255);
  printf("  Bytes on AXI: %d (physical)\n", bytes_physical * 64);
}
```

**Dependency:** Requires Module 4 (extended status register)

---

### Change 3: Pre-allocate L1 Based on Compression Ratio

**New Firmware Code:**
```c
void allocate_l1_for_compressed_data(uint32_t logical_size) {
  // Read compression ratio from status
  uint32_t status = READ_CSR(OVERLAY_STATUS_REG);
  uint32_t ratio = (status >> 16) & 0xFF;  // 0–255
  
  // Calculate physical occupancy
  // ratio=128 (50%) → 512 byte input → 256 bytes actual L1 use
  // ratio=38 (15%) → 512 byte input → 77 bytes actual L1 use
  uint32_t physical_bytes = (logical_size * ratio) / 255;
  
  // Now firmware knows exactly how much L1 to allocate
  L1_ALLOCATOR.allocate(physical_bytes);
}
```

**Dependency:** Requires Module 4 (status register with ratio)

---

### Change 4: Save Metadata (TurboQuant Only)

**New Firmware Code:**
```c
void compress_kv_vector_turboquant(uint32_t vector_idx) {
  // Issue TurboQuant compression
  OVERLAY_STREAM_WRITE(0, {
    .src = kv_input_addr,
    .dest = l1_kv_compressed,
    .algorithm = TURBOQUANT,
  });
  
  // Wait for completion
  while (!(READ_CSR(TURBOQUANT_STATUS) & DONE)) { }
  
  // Read both outputs
  uint8_t compressed[48];
  memcpy(compressed, (void*)l1_kv_compressed, 48);
  
  // THIS IS CRITICAL: Read scale factor from status/output register
  float scale = *(float*)READ_CSR(TURBOQUANT_SCALE_OUTPUT);
  
  // Save scale immediately after compressed data (MUST be adjacent!)
  memcpy((void*)(l1_kv_compressed + 48), &scale, 4);
  
  // Total occupancy: 52 bytes per vector
}
```

**Dependency:** Requires extended status register with scale output field

---

## Part 3: Summary Table — RTL vs Firmware

| Item | RTL Change | Firmware Change | Dependency |
|------|-----------|-----------------|-----------|
| **Size calculation** (logical → physical) | ✅ tt_compressed_data_tracker.sv | ❌ No | RTL mandatory |
| **ARLEN adjustment** (inject into AXI) | ✅ tt_axi_compressed_interface.sv | ❌ No | RTL mandatory |
| **Decompression** (sparse → dense) | ✅ tt_noc2axi_sparse_decompressor.sv | ❌ No | RTL mandatory |
| **Status register** (occupancy, ratio, metadata) | ✅ Extended CSR fields | ✅ Read via CSR | RTL mandatory |
| **Firmware writing logical size** | ❌ No | ✅ Change CSR value | Status register |
| **Firmware reading occupancy** | ❌ No | ✅ Add CSR read | Status register |
| **Firmware L1 allocation logic** | ❌ No | ✅ Add allocation loop | Status register |
| **Firmware saving scale (TurboQuant)** | ❌ No | ✅ Add metadata save | Status register |

---

## Part 4: No Protocol Changes (Only Parameter Adjustments)

### AXI Protocol: Uses Existing Fields

**AXI standard supports variable ARLEN — no protocol change needed**

```
Standard read (no compression):
  AR.ADDR = 0x80000000
  AR.LEN = 63           ← Burst length
  AR.SIZE = 3'h6        ← 64-byte beats
  AR.BURST = 2'h1       ← INCR
  
Compressed read (2:4 sparsity):
  AR.ADDR = 0x80000000  ← Same
  AR.LEN = 31           ← ADJUSTED (still valid AXI)
  AR.SIZE = 3'h6        ← Same (64-byte beats)
  AR.BURST = 2'h1       ← Same
  
Why no protocol change:
  ✓ ARLEN is already a variable AXI field (0–255)
  ✓ AXI slave (DRAM) already accepts any ARLEN value
  ✓ Just adjusts the value, no new signals needed
```

### NoC Flit: Uses Existing Status Field

**NoC flits carry existing fields; metadata goes in new CSR register**

```
NoC flit (512 bits):
  [511:384] destination
  [383:320] length (physical, not logical)
  [255:0]   payload (compressed data)
  
Metadata (in CSR, not in flit):
  OVERLAY_STATUS[31:24] = l1_occupancy_percent
  OVERLAY_STATUS[23:16] = compression_ratio
  OVERLAY_STATUS[15:8]  = bytes_transferred
  
No change to flit format needed
```

---

## Part 5: Implementation Order

### Phase 1: RTL (Weeks 1–2)
1. Design tt_compressed_data_tracker.sv (combinational)
2. Design tt_axi_compressed_interface.sv (mux)
3. Extend tt_noc2axi_sparse_decompressor.sv (2–3 cycles)
4. Extend overlay status register (add fields)
5. Verify timing closure (ARLEN path is critical)

### Phase 2: Firmware (Weeks 2–3)
1. Update OVERLAY_STREAM_WRITE to pass logical size
2. Add status register read in firmware
3. Add L1 allocator logic
4. Add TurboQuant metadata save loop
5. Test with actual compressed transfers

### Phase 3: Verification (Week 4)
1. Testbench: verify size calculation correctness
2. Testbench: verify ARLEN injection timing
3. Firmware: test compressed DRAM read
4. Firmware: test L1 occupancy tracking
5. End-to-end: compressed KV-cache load + inference

---

## Conclusion

**Can firmware handle compressed data WITHOUT RTL changes?**

| Scenario | Possible? | Result |
|----------|-----------|--------|
| Firmware calculates size, no RTL | ❌ No | ARLEN wrong, DRAM stall, data corruption |
| Firmware reads occupancy, no RTL | ❌ No | No feedback on actual usage |
| Firmware saves metadata, no RTL | ❌ No | (Possible if decompressor exists) |
| All 4 RTL modules + firmware | ✅ Yes | Works correctly, automatic optimization |

**Answer: Firmware changes ALONE are insufficient. RTL modules are MANDATORY for:
1. Automatic size calculation
2. ARLEN injection into AXI path
3. Decompression on data path
4. Status feedback to firmware**


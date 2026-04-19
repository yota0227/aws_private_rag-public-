# IP Design Guide for N1B0 NPU
## Adding New Hardware Accelerators and Features

**Document Version:** 1.1  
**Date:** 2026-04-03  
**Target Audience:** RTL Engineers, Hardware Architects, Firmware Engineers  
**Related N1B0 HDD Sections:** §2 (Tensix Tile), §3 (Overlay Engine), §4 (NOC2AXI Composite), §14 (SFR Summary)

---

## Table of Contents

1. Overview: Adding New IP to N1B0
2. System Function Registers (SFR) Integration Framework
3. NVIDIA Sparsity Scheme IP Integration Guide
   - 3.1–3.5: Architecture, RTL, SFR, firmware integration
   - **3.6: Compressed Data Metadata & Control Flow (HARDWARE-MANAGED)**
   - **3.7: L1 Address Space Management (SOFTWARE-MANAGED)**
   - **3.8: AXI/NoC Protocol Changes for Compressed Transfers**
   - **3.9: Hardware vs Software Control Summary — CRITICAL TABLE**
   - **3.10: Impact Analysis — Which Features Affected (Sparsity vs 2:4 vs TurboQuant)**
4. TurboQuant IP Integration Guide
   - 4.1–4.4: Architecture decisions, RTL implementation, SFR, firmware
   - **4.5: Metadata Output & L1 Tracking (Scale Factor Handling)**
   - 4.6: Performance estimates
   - **4.7: RTL Changes REQUIRED — Firmware ALONE Is NOT Sufficient (CRITICAL)**
5. RTL Integration Checklist
6. Firmware Programming Guide Template
7. Verification and Testing Strategy

---

## 1. Overview: Adding New IP to N1B0

### 1.1 Design Philosophy

N1B0 follows a **modular tile-based architecture** where new IP can be added at three integration points:

| Integration Point | Scope | Clock Domain | Interface | Example |
|-------------------|-------|--------------|-----------|---------|
| **Within Tensix tile** (§2) | Local compute acceleration, TRISC-driven | ai_clk, dm_clk | TRISC CSR, DEST RF, L1, overlay streams | SFPU, MOP sequencer |
| **Overlay engine** (§3) | Data movement, context switching, memory coherence | dm_clk, noc_clk | SRAM, CDC FIFO, L1 side-channel, NoC | Stream controller, TDMA |
| **NOC2AXI composite** (§4) | DRAM access, address translation, security | noc_clk, axi_clk | ATT table, AXI4, NoC flit injection | SMN, NIU |

### 1.2 New IP Design Decisions

Before integrating new IP, answer these questions:

1. **Where does it live?**
   - Within Tensix compute tile? → TRISC-controlled, ai_clk/dm_clk domain
   - In overlay subsystem? → Autonomous DMA-like orchestration, dm_clk/noc_clk domain
   - In NOC2AXI? → DRAM-side, address translation, AXI protocol

2. **How is it controlled?**
   - TRISC writes CSR registers → configuration-driven
   - Firmware programs via overlay stream CSR → command-driven
   - Autonomous with polling via status registers → status-driven

3. **What data does it access?**
   - L1 memory (local per-tile) → 128-bit port, no contentions with TRISC/overlay
   - DEST/SRCA register files → limited concurrency (4 MACs/cycle max)
   - DRAM via overlay/iDMA → queued, priority-based

4. **What are the latency/throughput requirements?**
   - Sub-cycle (combinational) → must fit in datapath FPU
   - 1 cycle pipelined → use staging registers
   - Multi-cycle → use hardware FSM + MOP sequencer pattern

### 1.3 IP Integration Phases

```
Phase 1: SFR & Interface Design
  ├─ Define register map (address, fields, RW access)
  ├─ Define CSR bus interface (width, valid/ready)
  └─ Create SFR documentation

Phase 2: RTL Architecture
  ├─ Instantiate IP module in hierarchy
  ├─ Connect clock/reset
  ├─ Add CSR/SFR interface
  └─ Add data path connections

Phase 3: CDC & Synchronization
  ├─ Identify clock domain crossings
  ├─ Add CDC FIFOs / sync stages
  └─ Verify timing

Phase 4: Firmware Integration
  ├─ Define CSR write sequences
  ├─ Define status polling loops
  └─ Create firmware test kernel

Phase 5: Verification & Signoff
  ├─ Unit tests (CSR writes, data path)
  ├─ Integration tests (end-to-end)
  ├─ DFX coverage (scan, BIST)
  └─ Performance validation
```

---

## 2. System Function Registers (SFR) Integration Framework

### 2.1 SFR Architecture Overview

N1B0 uses a **centralized APB (ARM AMBA APB) slave register interface** for SFR access. All CSR register updates flow through a single APB multiplexer:

```
Firmware (TRISC0–TRISC3) 
  ↓ (APB writes)
tt_instrn_engine.sv (CSR arbiter: tt_t6_csr_intf_arbiter.sv)
  ↓ (multiplexed CSR bus)
tt_register_blocks.sv (register file blocks)
  ├─ CLUSTER_CTRL
  ├─ T6_L1_CSR  
  ├─ LLK_TILE_COUNTERS
  ├─ Overlay stream registers (noc_neo_local_regs_intf)
  ├─ Semaphore registers (tt_semaphore_reg.sv)
  ├─ Sync/barrier registers
  └─ [NEW IP REGISTERS GO HERE]
  ↓
IP Module (receives SFR write strobe, address, data)
  ├─ Config registers (hold settings)
  ├─ Status registers (sampled for read)
  └─ Command registers (trigger actions)
```

### 2.2 SFR Address Map Design

**Key principle:** SFR addresses are organized in **4 KB blocks per functional unit**. Each block is assigned a base address within the L1/Tensix register space.

#### Existing SFR Map (from HDD §14)

```
Tensix Tile SFR Space (32-bit addressable):
┌─────────────────────────────────────────┐
│ Base: 0x0000                            │
│ CLUSTER_CTRL (1 register)               │  0x0000–0x0003
│ T6_L1_CSR (multiple registers)          │  0x0004–0x0020
│ Overlay stream regs                     │  0x0024–0x00FF (8 streams × 4 regs)
│ Sync semaphore regs (32×4-bit)          │  0x0100–0x011F
│ Mailbox registers (8 entries/thread)    │  0x0120–0x015F
│ NOC stream status (8 streams/TRISC)     │  0x0160–0x01FF
│ [RESERVED FOR NEW IP]                   │  0x0200–0x07FF
│ [RESERVED FOR NEW IP]                   │  0x0800–0x0FFF
└─────────────────────────────────────────┘
```

### 2.3 Adding New IP: SFR Definition Template

For a new IP module (e.g., **Sparsity Engine**, **TurboQuant**), follow this pattern:

#### Step 2.3.1: Define Register Offsets

```systemverilog
// File: tt_sparsity_pkg.sv
package tt_sparsity_pkg;
  
  // SFR Base Address (allocated in memory map, e.g., 0x0200)
  localparam SPARSITY_SFR_BASE = 32'h0200;
  
  // Register offsets (32-bit aligned)
  localparam SPARSITY_CTRL_OFFSET      = 32'h0000;  // RW: enable, mode select
  localparam SPARSITY_ZMASK_OFFSET     = 32'h0004;  // RW: 32-bit z-plane mask
  localparam SPARSITY_CONFIG_OFFSET    = 32'h0008;  // RW: vector size, data width
  localparam SPARSITY_STATUS_OFFSET    = 32'h000C;  // RO: ready, busy, error flags
  localparam SPARSITY_RESULT_OFFSET    = 32'h0010;  // RO: output data (pipelined read)
  
  // Register field definitions
  typedef struct packed {
    logic [31:8]  reserved;
    logic         enable;        // [0] Enable sparsity engine
    logic [2:1]   mode;          // [2:1] 0=off, 1=l1_skip, 2=dram_compress
  } sparsity_ctrl_t;
  
  typedef struct packed {
    logic [31:0]  zmask;         // 32-bit z-plane skip mask
  } sparsity_zmask_t;
  
  typedef struct packed {
    logic [31:16]  reserved;
    logic [15:12]  data_width;   // 0=INT8, 1=INT16, 2=FP16B, 3=FP32
    logic [11:5]   num_zplanes;  // log2(N) where N = vector size in z-planes
    logic [4:0]    reserved2;
  } sparsity_config_t;
  
  typedef struct packed {
    logic [31:2]  reserved;
    logic         error;         // [1] Error during transform
    logic         ready;         // [0] Ready for next command
  } sparsity_status_t;
  
endpackage
```

#### Step 2.3.2: Create SFR Register Block Module

```systemverilog
// File: tt_sparsity_registers.sv
module tt_sparsity_registers #(
  parameter ADDR_WIDTH = 14,
  parameter DATA_WIDTH = 32
) (
  input  logic                      i_clk,
  input  logic                      i_rst_n,
  
  // APB slave interface (from CSR arbiter)
  input  logic [ADDR_WIDTH-1:0]     i_paddr,
  input  logic                      i_pwrite,
  input  logic                      i_psel,
  input  logic                      i_penable,
  input  logic [DATA_WIDTH-1:0]     i_pwdata,
  output logic [DATA_WIDTH-1:0]     o_prdata,
  output logic                      o_pready,
  output logic                      o_pslverr,
  
  // Functional outputs (to sparsity engine datapath)
  output tt_sparsity_pkg::sparsity_ctrl_t    o_ctrl,
  output tt_sparsity_pkg::sparsity_zmask_t   o_zmask,
  output tt_sparsity_pkg::sparsity_config_t  o_config,
  input  tt_sparsity_pkg::sparsity_status_t  i_status,
  input  logic [DATA_WIDTH-1:0]              i_result_data
);
  
  import tt_sparsity_pkg::*;
  
  // Internal register storage
  sparsity_ctrl_t   ctrl_reg;
  sparsity_zmask_t  zmask_reg;
  sparsity_config_t config_reg;
  
  // Write logic (APB write bus → register storage)
  always_ff @(posedge i_clk) begin
    if (!i_rst_n) begin
      ctrl_reg   <= '0;
      zmask_reg  <= '0;
      config_reg <= '0;
    end else if (i_psel && i_penable && i_pwrite) begin
      case (i_paddr[5:2])  // Extract register select from address
        4'h0: ctrl_reg   <= i_pwdata;   // 0x0200
        4'h1: zmask_reg  <= i_pwdata;   // 0x0204
        4'h2: config_reg <= i_pwdata;   // 0x0208
        default: ;
      endcase
    end
  end
  
  // Read logic (register storage → APB read bus)
  always_comb begin
    o_prdata = '0;
    case (i_paddr[5:2])
      4'h0: o_prdata = ctrl_reg;                // 0x0200
      4'h1: o_prdata = zmask_reg;               // 0x0204
      4'h2: o_prdata = config_reg;              // 0x0208
      4'h3: o_prdata = i_status;                // 0x020C (read-only)
      4'h4: o_prdata = i_result_data;           // 0x0210 (read-only)
      default: o_prdata = '0;
    endcase
  end
  
  // APB handshake
  assign o_pready = 1'b1;  // Single-cycle access (no wait states)
  assign o_pslverr = 1'b0; // No errors (aligned access assumed)
  
  // Output assignments
  assign o_ctrl   = ctrl_reg;
  assign o_zmask  = zmask_reg;
  assign o_config = config_reg;
  
endmodule
```

### 2.4 Integrating SFR into Tensix Tile Hierarchy

#### Step 2.4.1: Add to tt_register_blocks.sv

```systemverilog
// In tt_register_blocks.sv (existing register multiplexer)

// Add instance declaration
tt_sparsity_registers #(
  .ADDR_WIDTH(14),
  .DATA_WIDTH(32)
) u_sparsity_registers (
  .i_clk(i_ai_clk),
  .i_rst_n(i_rst_n),
  .i_paddr(cfg_reg_addr),          // from CSR arbiter
  .i_pwrite(cfg_reg_write),
  .i_psel(sparsity_sel),           // Address decode: 0x0200-0x02FF
  .i_penable(cfg_reg_enable),
  .i_pwdata(cfg_reg_wdata),
  .o_prdata(sparsity_rdata),       // to CSR arbiter read mux
  .o_pready(sparsity_ready),
  .o_pslverr(sparsity_error),
  // Functional interface
  .o_ctrl(sparsity_ctrl),
  .o_zmask(sparsity_zmask),
  .o_config(sparsity_config),
  .i_status(sparsity_status),
  .i_result_data(sparsity_result_data)
);

// Add address decoder (if SPARSITY_SFR_BASE = 0x0200)
assign sparsity_sel = (cfg_reg_addr[15:8] == 8'h02) ? 1'b1 : 1'b0;
```

#### Step 2.4.2: Add to Tensix Cluster Hierarchy — IMPLEMENTATION GUIDE

**This step instantiates the new IP module inside the Tensix cluster container.**

For detailed RTL implementation with clock/reset connections, port arbitration, and complete examples for Sparsity and TurboQuant, see:

📄 **[Tensix_Cluster_IP_Integration_Implementation.md](./Tensix_Cluster_IP_Integration_Implementation.md)**

**Quick Template:**

```systemverilog
// In tt_tensix_with_l1.sv, inside generate block, after tt_tensix instantiation

tt_sparsity_engine #(
  .DATA_WIDTH(128),          // L1-local data width (128-bit)
  .NUM_STREAMS(4),           // Parallel transform streams
  .VECTOR_WIDTH(256)         // Max 256-element vectors
) u_sparsity_engine (
  // ─────────────────────────────────────────────────────
  // Clock and Reset
  // ─────────────────────────────────────────────────────
  .i_clk(i_dm_clk),          // dm_clk domain for L1 access
  .i_rst_n(i_rst_n),
  
  // ─────────────────────────────────────────────────────
  // CSR Interface (from register block)
  // ─────────────────────────────────────────────────────
  .i_ctrl(sparsity_ctrl),           // From tt_register_blocks.sv
  .i_zmask(sparsity_zmask),
  .i_config(sparsity_config),
  .o_status(sparsity_status),
  .o_result_data(sparsity_result_data),
  
  // ─────────────────────────────────────────────────────
  // L1 Memory Interface (128-bit local read)
  // ─────────────────────────────────────────────────────
  .i_l1_data(l1_rd_data),            // From L1 SRAM macros
  .o_l1_addr(l1_addr_sparsity),      // Address control
  .o_l1_rd_valid(l1_rd_valid_sparsity),  // Read strobe
  
  // ─────────────────────────────────────────────────────
  // Output Data Path
  // ─────────────────────────────────────────────────────
  .o_output_data(sparsity_output),    // Processed output
  .o_output_valid(sparsity_output_valid)  // Output valid
);
```

**Key Points:**
- ✅ Clock domain: **dm_clk** (same as L1, overlay, TDMA)
- ✅ CSR signals: Connect from register block (ai_clk domain, CDC required)
- ✅ L1 port: 128-bit read (same as TRISC uses, requires arbitration)
- ✅ Output: To TRISC, overlay streams, or back to L1
- ✅ Location: Inside generate block in `tt_tensix_with_l1.sv` (line ~1215–1323)

### 2.5 Overlay Engine: Adding SFR for DMA Commands

If the new IP requires **autonomous data movement** (like TurboQuant reading KV-cache), use the **overlay stream register pattern**:

#### Step 2.5.1: Define Overlay Stream Extension

```systemverilog
// File: tt_overlay_stream_pkg.sv (extend existing)

package tt_overlay_stream_pkg;
  
  // Existing stream types (from §3.4)
  typedef struct packed {
    logic [31:16]  reserved;
    logic [15:8]   stream_id;      // Which stream (0–7)
    logic [7:4]    direction;      // RD=0, WR=1
    logic [3:0]    size_selector;  // Burst length encoding
  } overlay_stream_cmd_t;
  
  // New: Sparsity-specific stream command
  typedef struct packed {
    logic [31:16]  transform_mask;   // Sparsity/quantization control
    logic [15:8]   output_stream_id; // Where to write results
    logic [7:4]    algorithm_mode;   // 0=l1_skip, 1=dram_compress, 2=turboquant
    logic [3:0]    reserved;
  } overlay_stream_sparse_cmd_t;
  
endpackage
```

#### Step 2.5.2: Extend Overlay Controller

```systemverilog
// In tt_neo_overlay_wrapper.sv or tt_overlay_stream_controller.sv

// Add new stream register set for sparsity
always_ff @(posedge i_dm_clk) begin
  if (!i_rst_n) begin
    sparse_cmd_reg <= '0;
  end else if (sparse_stream_wr) begin
    sparse_cmd_reg <= sparse_cmd_data;  // From TRISC CSR write
  end
end

// Route command to sparsity/turboquant engine
assign sparse_cmd_out = sparse_cmd_reg;

// Status feedback (for polling)
assign sparse_status_reg = {sparse_engine_busy, sparse_engine_error, 30'b0};
```

---

## 3. NVIDIA Sparsity Scheme IP Integration Guide

NVIDIA's **2:4 structured sparsity** requires **DRAM-side compression/decompression** — a major architectural change from N1B0's L1-local z-plane masking.

### 3.1 NVIDIA 2:4 Sparsity Overview

**Constraint:** Only 2 out of every 4 consecutive elements can be non-zero.

**Where it works:**
- Reduces **DRAM bandwidth** (no data transfer for zero elements)
- Reduces **AXI bus traffic** (fewer bytes on wire)
- Reduces **L1 reads** (pre-decompressed data in L1)

**Cost:**
- Requires **compression/decompression hardware** at DRAM boundary
- Modifies **memory layout** (needs dense packing format)
- Increases **ATT complexity** (logical vs physical address translation)

### 3.2 Design Decision: Where to Place 2:4 IP?

**Option A: In NOC2AXI (Composite Tile) — RECOMMENDED**
- ✅ At DRAM boundary (maximum bandwidth savings)
- ✅ Shared by all Tensix tiles (single instance per corner)
- ✅ Transparent to TRISC firmware (automatic decompression on read)
- ❌ More complex CDC (axi_clk ↔ noc_clk domain crossing)
- ❌ Adds latency to DRAM path (+5–10 cycles)

**Option B: In iDMA Engine (Dispatch Tile)**
- ✅ Simpler integration (single clock domain)
- ✅ Can compress weights at kernel initialization
- ❌ Only benefits weight loading (not activations)
- ❌ iDMA is RoCC slave (limited control)

**Recommendation:** **Option A (NOC2AXI composite tile) for full DRAM bandwidth savings**

### 3.3 2:4 Sparsity RTL Architecture

#### Position in NOC2AXI_ROUTER_NW/NE_OPT (Y=4 NIU portion)

```
TRISC CSR write (overlay stream)
  ↓
noc_neo_local_regs_intf (stream enable, sparse_format=1)
  ↓
tt_overlay_stream_controller (in Y=4 NIU portion)
  ├─ Route sparse command to AXI side
  └─ Set sparse_decompress_enable = 1
  ↓
[NEW] tt_noc2axi_sparse_decompressor.sv
  ├─ Input: AXI read data (compressed, 64 bits = 2×32-bit elements)
  ├─ Decode: Extract valid element positions (2:4 pattern)
  ├─ Output: Decompressed data (128 bits = 4×32-bit elements, zeros inserted)
  └─ Latency: 2–3 cycles
  ↓
L1 SRAM (receives uncompressed data via 512-bit NoC side-channel)
```

#### Step 3.3.1: Create Sparse Decompressor Module

```systemverilog
// File: tt_noc2axi_sparse_decompressor.sv
module tt_noc2axi_sparse_decompressor #(
  parameter DATA_WIDTH = 512,           // 512-bit flit width
  parameter ELEM_WIDTH = 32,            // Per-element width
  parameter SPARSITY_PATTERN = 2'b10    // 2:4 pattern identifier
) (
  input  logic i_clk,
  input  logic i_rst_n,
  
  // Input: compressed data from DRAM via AXI
  input  logic [DATA_WIDTH-1:0]  i_axi_rdata,    // 512-bit beat
  input  logic [511:0]           i_validity_mask, // Which lanes are valid (2:4 encoded)
  input  logic                   i_data_valid,
  output logic                   o_data_ready,
  
  // Output: decompressed data (all 16 elements expanded, zeros inserted)
  output logic [DATA_WIDTH-1:0]  o_noc_data,
  output logic                   o_noc_valid,
  input  logic                   i_noc_ready
);

  // 512-bit input = 16 × 32-bit elements
  // 2:4 sparsity means only 8 elements are actually stored (2 per group of 4)
  // Decompress: expand 8 → 16 with zeros
  
  logic [31:0] elem_in[7:0];      // 8 compressed elements
  logic [31:0] elem_out[15:0];    // 16 decompressed elements
  
  // Extract compressed elements
  generate
    for (genvar i = 0; i < 8; i++) begin
      assign elem_in[i] = i_axi_rdata[(i*32+31):(i*32)];
    end
  endgenerate
  
  // Expand based on validity mask
  // Validity mask encoding: 1 bit per group of 4 elements
  // bit[3:0] = group 0 (2 non-zero positions)
  // bit[7:4] = group 1 (2 non-zero positions)
  // etc.
  
  always_comb begin
    // Default: all zeros
    elem_out = '{default: 32'b0};
    
    // Decompress each group
    // Group 0: positions [0:3]
    case (i_validity_mask[3:0])
      4'b0011: begin elem_out[0] = elem_in[0]; elem_out[1] = elem_in[1]; end  // pos 0,1
      4'b0101: begin elem_out[0] = elem_in[0]; elem_out[2] = elem_in[1]; end  // pos 0,2
      4'b0110: begin elem_out[1] = elem_in[0]; elem_out[2] = elem_in[1]; end  // pos 1,2
      4'b1001: begin elem_out[0] = elem_in[0]; elem_out[3] = elem_in[1]; end  // pos 0,3
      4'b1010: begin elem_out[1] = elem_in[0]; elem_out[3] = elem_in[1]; end  // pos 1,3
      4'b1100: begin elem_out[2] = elem_in[0]; elem_out[3] = elem_in[1]; end  // pos 2,3
      default: ;
    endcase
    
    // Group 1: positions [4:7] (similar pattern with input elem_in[2:3])
    // ... (repeat for groups 2–3)
  end
  
  // Assemble output
  generate
    for (genvar i = 0; i < 16; i++) begin
      assign o_noc_data[(i*32+31):(i*32)] = elem_out[i];
    end
  endgenerate
  
  // Pipeline the output (2-cycle latency)
  logic [511:0] rdata_pipe1, rdata_pipe2;
  always_ff @(posedge i_clk) begin
    if (!i_rst_n) begin
      rdata_pipe1 <= '0;
      rdata_pipe2 <= '0;
    end else if (i_data_valid && o_data_ready) begin
      rdata_pipe1 <= o_noc_data;
      rdata_pipe2 <= rdata_pipe1;
    end
  end
  
  assign o_noc_valid = (rdata_pipe2 != 0) ? 1'b1 : 1'b0;
  assign o_data_ready = i_noc_ready;

endmodule
```

#### Step 3.3.2: Add SFR Controls for 2:4 Mode

```systemverilog
// In tt_niu_registers.sv (extend existing NIU register space)

localparam SPARSE_CTRL_OFFSET = 32'h0100;  // New register block
localparam SPARSE_VALIDITY_OFFSET = 32'h0104;

typedef struct packed {
  logic [31:8]  reserved;
  logic [7:4]   algorithm;   // 0=off, 1=2:4, 2=block_sparse
  logic [3:0]   enable;      // Enable for AXI RDATA path
} sparse_noc_ctrl_t;

// Example: TRISC configures sparsity at kernel start
// TRISC1 writes: sparse_ctrl_reg = {0, 4'h1, 4'hF}  // Enable 2:4 mode
```

### 3.4 Firmware Integration: 2:4 Sparsity

```c
// File: firmware/sparsity_kernel.c

void init_2to4_sparsity() {
  // Enable 2:4 decompression in NIU
  uint32_t sparse_ctrl = (1 << 4) | 0xF;  // mode=2:4, enable all lanes
  WRITE_CSR(SPARSE_CTRL_REG, sparse_ctrl);
  
  // All subsequent overlay DRAM reads will be decompressed automatically
}

void compressed_dram_read(uint32_t compressed_addr, uint32_t dest_l1_addr, uint32_t num_elements) {
  // Write overlay stream command (sparsity mode)
  uint32_t cmd = {
    .src_addr = compressed_addr,        // Compressed data in DRAM
    .dest_addr = dest_l1_addr,          // Uncompressed destination in L1
    .size = num_elements / 2,           // Half the size (only 2 of 4 elements stored)
    .sparse_mode = 1,                   // Trigger decompression
    .stream_id = 0
  };
  
  OVERLAY_STREAM_WRITE(0, cmd);
  
  // Poll for completion
  while (!(OVERLAY_STATUS(0) & OVERLAY_DONE)) { }
}
```

### 3.5 Performance Trade-off: 2:4 vs Z-Plane Masking

| Metric | N1B0 Z-Plane | NVIDIA 2:4 |
|--------|--------------|-----------|
| **L1 bandwidth saved** | Yes (50% with mask) | Yes (50% in DRAM) |
| **DRAM bandwidth saved** | No | Yes (50%) |
| **Latency impact** | None (loop unchanged) | +5–10 cycles (decompress) |
| **Implementation complexity** | 1 FSM stage (simple) | Full decompressor + CDC (complex) |
| **Area cost** | ~2 KB (mask storage) | ~50 KB (decompressor, 5nm) |
| **When to use** | Structured sparsity, power-constrained | Fine-grained sparsity, latency-flexible |

### 3.6 Compressed Data Metadata & Control Flow — **HARDWARE-MANAGED** (CRITICAL)

**Problem:** When data is compressed (2:4 sparsity or TurboQuant), the **logical size** (what firmware requests) differs from the **physical size** (actual bytes on AXI/NoC bus). This mismatch must be tracked throughout the data movement pipeline.

#### 3.6.1 Metadata Architecture

**Question: Who controls compression metadata?**

**Answer: HARDWARE tracks it automatically** — firmware does NOT need to manually manage sizes.

```
Hardware Tracking Flow:

Firmware Command:
  ├─ size_logical = 1024 elements (what firmware thinks is being moved)
  ├─ compress_mode = 2:4_SPARSITY
  └─ dest_addr = L1_BASE (destination in L1)
  
Hardware Detection:
  ├─ Recognizes compress_mode = 2:4
  ├─ Computes size_physical = size_logical / 2  (hardware calculation)
  ├─ AXI ARLEN = (size_physical / 64) - 1       (burst length in beats)
  └─ Tracks compression metadata in status register
  
Data Movement:
  ├─ AXI reads compressed data (fewer bytes on wire)
  ├─ Decompressor expands back to logical size
  └─ L1 receives full uncompressed vector
  
Output Metadata:
  ├─ bytes_transferred_physical = 512 bytes (actual AXI beats)
  ├─ bytes_stored_l1_logical = 1024 bytes (what L1 received)
  ├─ compression_ratio = 50%
  └─ stored in status register for firmware polling
```

#### 3.6.2 Extended Status Register Design

**Original overlay stream status register (§3.4 N1B0_NPU_HDD_v1.00):**
```
[31:2] reserved
[1]    error
[0]    done
```

**Extended for compressed transfers:**
```systemverilog
typedef struct packed {
  logic [31:16] bytes_transferred;      // Actual physical bytes on AXI (compressed)
  logic [15:8]  compression_ratio;      // 0-255, where 255 = 100% uncompressed
  logic [7:4]   reserved;
  logic [3:2]   compression_mode;       // 0=off, 1=2:4, 2=turboquant, 3=reserved
  logic [1]     error;
  logic [0]     done;
} overlay_stream_status_extended_t;

// Examples:
//   2:4 sparse: bytes_transferred=512, ratio=128 (50%)
//   TurboQuant: bytes_transferred=48, ratio=38 (15%, 128×3-bit = 48 bytes)
//   Dense (off): bytes_transferred=1024, ratio=255 (100%)
```

#### 3.6.3 Hardware Implementation: Metadata Generator

**In NIU (for 2:4 sparsity) or Overlay (for TurboQuant):**

```systemverilog
// File: tt_compressed_data_tracker.sv
module tt_compressed_data_tracker (
  input  logic i_clk,
  input  logic i_rst_n,
  
  // Command from firmware
  input  logic [31:0] i_size_logical,           // Requested size in elements
  input  logic [3:0]  i_compress_mode,          // 0=off, 1=2:4, 2=turboquant
  
  // Hardware outputs
  output logic [31:0] o_size_physical,          // Actual bytes to transfer
  output logic [31:0] o_arlen,                  // AXI burst length
  output logic [7:0]  o_compression_ratio,      // Percentage (0-255)
  
  // Tracking outputs
  output logic [31:0] o_bytes_transferred,      // For status register
  output logic        o_compression_active
);
  
  import tt_turboquant_pkg::*;
  
  // Compute physical size based on compression mode
  always_comb begin
    case (i_compress_mode)
      4'h0: begin
        // No compression
        o_size_physical = i_size_logical;
        o_compression_ratio = 8'hFF;  // 255 = 100% (uncompressed)
      end
      4'h1: begin
        // 2:4 sparsity: only 2 of 4 elements stored
        o_size_physical = i_size_logical >> 1;  // Divide by 2
        o_compression_ratio = 8'h80;  // 128 = 50%
      end
      4'h2: begin
        // TurboQuant: 128×FP32 (512 bytes) → 128×3-bit (48 bytes)
        // General formula: output = input × (3/32) for 128-element vectors
        // For variable sizes: output = (input × 3) / 32
        o_size_physical = (i_size_logical * 3) >> 5;  // Multiply by 3/32
        o_compression_ratio = 8'h26;  // 38 = 15% (48/512 * 255)
      end
      default: begin
        o_size_physical = i_size_logical;
        o_compression_ratio = 8'h00;
      end
    endcase
    
    // Calculate AXI ARLEN (max 256 beats per burst)
    logic [31:0] beats = o_size_physical >> 6;  // Divide by 64 (beat size)
    o_arlen = (beats > 256) ? 8'hFF : (beats - 1);  // ARLEN = beats - 1, max 255
    
    // Tracking
    o_compression_active = (i_compress_mode != 4'h0) ? 1'b1 : 1'b0;
    o_bytes_transferred = o_size_physical;
  end
  
endmodule
```

#### 3.6.4 AXI Side: Burst Length Adjustment

**In NIU AXI master (tt_noc2axi or similar):**

```systemverilog
// File: tt_axi_compressed_interface.sv
module tt_axi_compressed_interface (
  input  logic [31:0] i_size_logical,       // What firmware requested
  input  logic [3:0]  i_compress_mode,      // Compression algorithm
  input  logic [31:0] i_address,
  
  // AXI AR (address + read command) bus
  output logic [31:0] o_axi_araddr,
  output logic [7:0]  o_axi_arlen,          // Adjusted for compressed size
  output logic [2:0]  o_axi_arsize,         // Always 6 (64-byte beats)
  output logic [1:0]  o_axi_arburst,        // INCR
  
  // Metadata for decompressor
  output logic [3:0]  o_compress_mode_out
);
  
  // Compute physical size
  logic [31:0] size_physical;
  logic [31:0] arlen_computed;
  
  always_comb begin
    case (i_compress_mode)
      4'h0: size_physical = i_size_logical;
      4'h1: size_physical = i_size_logical >> 1;     // 2:4 sparsity
      4'h2: size_physical = (i_size_logical * 3) >> 5;  // TurboQuant
      default: size_physical = i_size_logical;
    endcase
    
    // Convert to bursts: 64 bytes per beat, max 256 beats per burst
    logic [31:0] beats = size_physical >> 6;
    arlen_computed = (beats > 256) ? 8'hFF : (beats - 1);
  end
  
  // Output assignments
  assign o_axi_araddr = i_address;
  assign o_axi_arlen = arlen_computed[7:0];
  assign o_axi_arsize = 3'h6;  // 2^6 = 64 bytes
  assign o_axi_arburst = 2'h1;  // INCR
  assign o_compress_mode_out = i_compress_mode;
  
endmodule
```

**Firmware Usage:**
```c
// Firmware does NOT compute arlen — hardware does it automatically!

void read_compressed_weights(uint32_t dram_addr, uint32_t num_elements) {
  // Issue command with logical size
  uint32_t cmd = {
    .src_addr = dram_addr,
    .size = num_elements,                    // Logical size (e.g., 1024 elements)
    .compress_mode = COMPRESS_2TO4,         // Hardware will adjust ARLEN
    .dest = L1_BASE
  };
  
  OVERLAY_STREAM_WRITE(0, cmd);
  
  // Hardware automatically:
  // 1. Computes size_physical = size / 2 = 512 elements
  // 2. Sets AXI ARLEN = (512 * 4 bytes) / 64 - 1 = 31 (32 beats)
  // 3. Initiates 32-beat AXI read (instead of 64 beats)
  // 4. Decompressor expands back to 1024 elements
  // 5. L1 receives 1024 uncompressed elements
}
```

---

### 3.7 L1 Address Space Management for Compressed Data — **SOFTWARE-MANAGED** (CRITICAL)

**Problem:** When compressed data arrives at L1, the **physical occupancy** is much smaller than the **logical size**. Firmware must carefully allocate L1 space to account for this.

#### 3.7.1 L1 Address Space Partitioning

**N1B0 L1 per tile: 768 KB = 786,432 bytes**

**Without compression:**
```
L1 Space (768 KB per tile)
├─ Instruction cache (IMEM): 4 KB × 4 threads = 16 KB
├─ Local memory (LDM): 4 KB × 4 threads = 16 KB
└─ Data working set: 768 - 32 = 736 KB
```

**With compression (firmware must manage):**
```
L1 Space (768 KB per tile)
├─ Instruction cache (IMEM): 16 KB (fixed)
├─ Local memory (LDM): 16 KB (fixed)
├─ Compressed weights storage: ? KB    ← firmware chooses allocation
├─ Decompressed working vectors: ? KB  ← firmware chooses allocation
└─ Double-buffer space: ? KB           ← firmware chooses allocation
```

**Key insight:** Firmware must **pre-allocate** L1 regions based on compression ratios:

```c
// File: firmware/l1_allocator.c

#define L1_TOTAL_SIZE       (768 * 1024)        // 768 KB
#define L1_IMEM_SIZE        (16 * 1024)         // 16 KB (4 threads × 4 KB)
#define L1_LDM_SIZE         (16 * 1024)         // 16 KB (4 threads × 4 KB)
#define L1_AVAILABLE_SIZE   (L1_TOTAL_SIZE - L1_IMEM_SIZE - L1_LDM_SIZE)

// Allocation 1: Store compressed weights (2:4 sparsity = 50% compression)
#define WEIGHTS_LOGICAL_SIZE    (128 * 1024)   // 128 KB of uncompressed weights needed
#define WEIGHTS_COMPRESSED_SIZE (WEIGHTS_LOGICAL_SIZE / 2)  // 64 KB on DRAM
#define L1_COMPRESSED_REGION    (L1_IMEM_SIZE + L1_LDM_SIZE)  // Start at 32 KB
// After loading: 64 KB used in L1

// Allocation 2: Decompressed working buffer (after unpacking)
#define L1_DECOMPRESSED_REGION  (L1_COMPRESSED_REGION + WEIGHTS_COMPRESSED_SIZE)
// After decompression: 128 KB used
// Total so far: 64 KB + 128 KB = 192 KB

// Allocation 3: Activation vectors (double-buffer for pipelining)
#define ACTIVATION_SIZE_LOGICAL     (16 * 1024)   // 16 KB per vector
#define ACTIVATION_SIZE_COMPRESSED  (ACTIVATION_SIZE_LOGICAL / 2)  // 8 KB (2:4 sparse)
#define L1_ACT_BUFFER_A  (L1_DECOMPRESSED_REGION + WEIGHTS_LOGICAL_SIZE)
#define L1_ACT_BUFFER_B  (L1_ACT_BUFFER_A + ACTIVATION_SIZE_LOGICAL)
// After setup: 16 KB + 16 KB = 32 KB for double-buffer
// Total: 192 KB + 32 KB = 224 KB / 736 KB available (30% utilization)
```

#### 3.7.2 Compressed Size Tracking Register

**Hardware must provide actual occupancy reporting:**

```systemverilog
// In overlay stream status register (extended)
typedef struct packed {
  logic [31:24] l1_occupancy_percent;         // % of L1 used (0-100)
  logic [23:16] bytes_stored_uncompressed;    // Logical bytes (what L1 sees)
  logic [15:8]  bytes_stored_compressed;      // Physical bytes (what DRAM had)
  logic [7:5]   reserved;
  logic [4:2]   compression_mode;             // 0=off, 1=2:4, 2=turboquant
  logic [1]     error;
  logic [0]     done;
} overlay_stream_status_with_occupancy_t;
```

**Firmware Usage:**
```c
void load_and_track_weights() {
  // Issue compressed read
  OVERLAY_STREAM_WRITE(0, {
    .src = DRAM_WEIGHTS,
    .size = 128 * 1024,          // 128 KB uncompressed
    .compress = COMPRESS_2TO4,
    .dest = L1_BASE
  });
  
  // Poll completion and read occupancy
  while (!(OVERLAY_STATUS(0) & DONE)) { }
  
  uint32_t status = READ_CSR(OVERLAY_STATUS_REG);
  uint32_t l1_used = (status >> 24) & 0xFF;  // Extract occupancy %
  uint32_t actual_bytes = (status >> 16) & 0xFF;
  
  printf("Loaded weights: %d KB uncompressed, occupancy %d%%\n", 
         actual_bytes / 1024, l1_used);
  
  // Firmware can now decide: allocate more working space if occupancy < 50%
  if (l1_used < 50) {
    ALLOCATE_MORE_L1_BUFFERS();
  }
}
```

#### 3.7.3 L1 Address Visibility with Compression

**New column for HDD §2.3.6 (L1 Address Visibility Matrix):**

| Agent | Access Mode | Address Range | Compression Support | Notes |
|-------|-------------|----------------|-------------------|-------|
| **TRISC0/1/2/3** | Read/Write | L1 per-tile | Transparent (sees uncompressed) | Direct load/store instructions see decompressed data |
| **TDMA unpack** | Read (L1) | Per-bank hash | No (always direct) | Unpack engines read raw L1 data |
| **Overlay stream** | Write (L1 side-ch) | 512-bit flit | Hardware decompression automatic | Decompressor inserts zeros for sparse elements |
| **iDMA (Dispatch)** | Read (DRAM) → Write (L1) | Full range | Optional (firmware-configurable) | Can read compressed weights, but no HW decompression yet |

#### 3.7.4 TurboQuant: Metadata Output (CRITICAL FOR L1 TRACKING)

**TurboQuant outputs TWO pieces of data, not one:**

```
Input:  128 FP32 values = 512 bytes (one KV vector)
        
Output #1: Compressed quantized vector
           128 × 3-bit values = 384 bits = 48 bytes
           
Output #2: Scale factor metadata
           1 × FP32 = 4 bytes
           
Total output occupancy: 48 + 4 = 52 bytes per vector
```

**Firmware must account for both:**

```c
// File: firmware/turboquant_l1_tracking.c

#define KV_CACHE_NUM_VECTORS    1024
#define KV_VECTOR_SIZE_LOGICAL  128     // 128 FP32 = 512 bytes
#define KV_VECTOR_SIZE_COMPRESSED  48   // 128×3-bit
#define KV_SCALE_SIZE           4       // 1 FP32
#define KV_TOTAL_PER_VECTOR     (KV_VECTOR_SIZE_COMPRESSED + KV_SCALE_SIZE)

// Total KV-cache storage
#define L1_KV_TOTAL   (KV_CACHE_NUM_VECTORS * KV_TOTAL_PER_VECTOR)
                     // 1024 × 52 = 53,248 bytes = 52 KB

// Allocation strategy:
#define L1_KV_BASE    (32 * 1024)      // Start after IMEM+LDM
// Now firmware knows exactly: 52 KB used for 1024 KV vectors
// Original uncompressed: 512 KB → Now: 52 KB (10× reduction!)

void store_compressed_kv(uint32_t vector_idx, 
                         uint8_t *compressed_data,    // 48 bytes
                         float *scale_factor) {       // 4 bytes
  uint32_t offset = vector_idx * KV_TOTAL_PER_VECTOR;
  
  // Write compressed data
  memcpy((void*)(L1_KV_BASE + offset), compressed_data, KV_VECTOR_SIZE_COMPRESSED);
  
  // Write scale factor immediately after
  memcpy((void*)(L1_KV_BASE + offset + KV_VECTOR_SIZE_COMPRESSED), 
         scale_factor, KV_SCALE_SIZE);
  
  // Now firmware knows exact L1 occupancy: (vector_idx+1) * 52 bytes
}
```

---

### 3.8 AXI/NoC Protocol Changes for Compressed Transfers

**Question:** How do AXI and NoC adapt when data sizes change due to compression?

**Answer:** Hardware automatically adjusts protocol parameters. Firmware never programs AXI fields directly.

#### 3.8.1 AXI Master Interface Changes

**Standard 2:4 sparse read (no compression):**
```
DRAM has: 1024 elements × 4 bytes = 4096 bytes (uncompressed)

AXI Read:
  ARADDR = 0x80000000 (DRAM address)
  ARLEN  = 63         (64 beats × 64 bytes/beat = 4096 bytes)
  ARSIZE = 3'h6       (64-byte beats)
  ─────────────────────────────────────────────
  Data on AXI RDATA: 64 beats × 64 bytes = 4096 bytes
  Cycles to transfer: 64 + latency
```

**2:4 sparse read (WITH compression enabled):**
```
DRAM has: only 512 elements × 4 bytes = 2048 bytes (compressed, 2:4 pattern)

Hardware computes:
  size_physical = 1024 / 2 = 512 elements = 2048 bytes

AXI Read (AUTO-ADJUSTED):
  ARADDR = 0x80000000 (DRAM address, same)
  ARLEN  = 31         (32 beats × 64 bytes = 2048 bytes) ← HALVED
  ARSIZE = 3'h6       (64-byte beats, same)
  ─────────────────────────────────────────────
  Data on AXI RDATA: 32 beats × 64 bytes = 2048 bytes (compressed)
  Decompressor: Expands 2048 → 4096 (adds zero elements)
  L1 receives: 4096 bytes (logical)
  Cycles to transfer: 32 + latency (50% reduction)
```

**Firmware view (no change needed):**
```c
void read_sparse_weights() {
  // Firmware writes SAME command regardless of compression
  OVERLAY_STREAM_WRITE(0, {
    .src_addr = DRAM_WEIGHTS,
    .dest_addr = L1_BASE,
    .size = 1024,                 // Logical size (elements)
    .compress_mode = COMPRESS_2TO4,  // Enable compression
    .stream_id = 0
  });
  
  // Hardware automatically:
  // 1. Sees compress_mode = 2:4
  // 2. Computes ARLEN = 31 (not 63!)
  // 3. Issues AXI read with 32 beats (not 64)
  // 4. Decompresses on RDATA path
  // 5. L1 gets 1024 elements uncompressed
  
  // Firmware polling sees:
  uint32_t status = READ_CSR(OVERLAY_STATUS(0));
  printf("Transferred %d bytes (physical), received %d bytes (logical)\n",
         status.bytes_transferred,    // 2048
         1024 * 4);                   // 4096
}
```

#### 3.8.2 NoC Flit Protocol Changes

**Standard NoC flit (512-bit, 64-byte payload):**
```
Flit header:
  [511:384] destination_xy
  [383:320] packet_length  = 64 bytes
  [319:256] packet_id
  [255:0]   payload (64 bytes of data)
```

**Compressed NoC flit (same header, different payload meaning):**
```
Flit header:
  [511:384] destination_xy (same)
  [383:320] packet_length  = 32 bytes (LOGICAL = 64, PHYSICAL = 32)  ← TBD
  [319:256] packet_id (same)
  [255:0]   payload (32 bytes of COMPRESSED data)
             (or: 64 bytes with validity mask for which lanes are populated)

Question: Does packet_length report logical or physical size?
  Option A: Physical (32 bytes) — decompressor adds zero lanes internally
  Option B: Logical (64 bytes) — flit carries validity bitmap too
  Option C: Split the field — [31:24] = physical, [23:16] = logical

Recommendation: Option A (physical size)
  Reason: Reduces NoC bandwidth (only transfer compressed bytes)
          Decompression happens in L1 side-channel (not on NoC path)
```

#### 3.8.3 Buffer Management on AXI/DRAM Side

**Hardware must provide buffer tracking:**

```systemverilog
// In NIU or overlay controller
typedef struct packed {
  logic [31:16] outstanding_compressed_bytes;  // Still in-flight on AXI
  logic [15:8]  outstanding_logical_bytes;     // After decompression
  logic [7:4]   compression_mode_active;
  logic [3:0]   stream_busy_mask;              // Which streams have data
} noc_buffer_status_t;

// Example state:
//   Issued: compress_read(size_logical=1024, compress=2:4)
//   AXI ARLEN=31 (32 beats = 2048 bytes physical)
//   outstanding_compressed_bytes = 2048
//   outstanding_logical_bytes = 4096  ← Will become 4096 after decompression
```

---

### 3.9 Hardware vs Software Control Summary — **CRITICAL TABLE**

**CRITICAL DISTINCTION for compressed data — Hardware automates AXI/NoC, Firmware manages L1:**

| Aspect | Control | Responsibility | Details |
|--------|---------|-----------------|---------|
| **Compression mode selection** | Software | Firmware | Firmware writes overlay stream CSR with `compress_mode = COMPRESS_2TO4 or TURBOQUANT` |
| **Size calculation (logical → physical)** | **Hardware** | RTL (tt_compressed_data_tracker.sv) | Hardware automatically: logical→physical based on compress_mode |
| **AXI burst length (ARLEN) calculation** | **Hardware** | RTL (tt_axi_compressed_interface.sv) | Hardware adjusts ARLEN based on physical size; **firmware never writes ARLEN** |
| **Decompression execution** | **Hardware** | RTL (tt_noc2axi_sparse_decompressor.sv) | Decompressor automatically expands sparse data with zeros |
| **Decompression latency** | **Hardware** | RTL (2–3 cycle pipeline) | Transparent to firmware; adds 5–10 cycles to DRAM path |
| **L1 side-channel data path** | **Hardware** | RTL (512-bit port) | Decompressed data arrives at L1 automatically (no firmware action) |
| **Compression metadata output** | **Hardware** | RTL + SFR | Generates scale factor (TurboQuant), validity mask (2:4), ratio % |
| **Status register reporting** | **Hardware** | RTL | Reports: bytes_transferred (physical), compression_ratio, mode active |
| **L1 address space allocation** | **Software** | Firmware | Firmware pre-allocates L1 regions accounting for compression_ratio |
| **L1 occupancy tracking** | **Hardware + Software** | RTL + Firmware | Hardware reports %; firmware maintains allocation map |
| **Metadata storage (scale, validity)** | **Software** | Firmware | Firmware MUST save scale/validity with compressed data in L1 |

**Summary:**
- ✅ **Hardware automates (no firmware involvement):** 
  - Size calculation (logical → physical)
  - ARLEN/burst length adjustment
  - Decompression (sparse → dense)
  - Metadata generation (scale, validity)
  - Status reporting (bytes transferred, ratio)

- ✅ **Firmware manages (hardware informs):**
  - L1 space allocation strategy
  - Buffer lifetime and deallocation
  - Metadata persistence (saving scale with compressed data)
  - Occupancy tracking (via hardware status)

- ❌ **Firmware DOES NOT compute:**
  - Physical sizes (hardware does it)
  - ARLEN / burst lengths (hardware does it)
  - Decompression (hardware does it)
  - Scale factors (hardware generates them)

---

## 3.10 Impact Analysis: Sparsity vs 2:4 vs TurboQuant

**Question:** Which features are affected by the compressed data control flow changes?

### Z-Plane Sparsity (N1B0 Native) — ❌ NOT AFFECTED

Z-plane masking is **L1-local, operates entirely within Tensix tile** — no DRAM involvement, so the compressed data control sections **DO NOT APPLY**:

```
Z-plane architecture (unchanged):
  TRISC writes MOP sequencer (zmask = 32-bit mask)
    ↓ (ai_clk domain)
  Unpack loop FSM reads L1 data
    ├─ If zmask[i]=0: load z-plane i (UNPACK_A0)
    └─ If zmask[i]=1: skip z-plane i (SKIP_A)
    ↓
  FPU receives sparse MAC tags (skip cycles don't execute)
    ↓
  DEST register receives results
    ↓
  NO decompression, NO AXI, NO metadata needed

Why unchanged:
  ✓ Tile-local (no DRAM path)
  ✓ No size conversion (K always iterates 96 times)
  ✓ No metadata (zmask is local parameter)
  ✓ No occupancy tracking (L1 capacity fixed)
```

**Conclusion:** Keep existing `sparsity_guide.md` (§2.7.9 of N1B0_NPU_HDD_v1.00.md) as-is. Z-plane and NVIDIA 2:4 are independent features.

---

### 2:4 NVIDIA Sparsity — ✅ DIRECTLY AFFECTED

The compressed data control flow sections (§3.6–3.9) **REPLACE** the simpler §3.4 firmware examples:

**Changes:**

| Item | Old Approach | New Approach |
|------|--------------|--------------|
| **Size parameter** | Firmware calculates `size_physical = size / 2` | Firmware passes `size_logical = 1024`; hardware calculates physical |
| **ARLEN** | Firmware writes ARLEN to AXI interface | Hardware auto-adjusts ARLEN based on compress_mode |
| **Decompression** | Manual (firmware-based) | Automatic (hardware decompressor module) |
| **Status tracking** | No occupancy report | Hardware reports bytes_transferred %, compression_ratio, occupancy % |
| **L1 allocation** | Fixed regions | Firmware pre-allocates based on compression_ratio from status |

**Impact on 2:4 Firmware:**

```c
// OLD (§3.4)
void read_sparse_weights() {
  uint32_t cmd = {
    .size = num_elements / 2,           // ← Firmware calculates
    .sparse_mode = 1,
  };
  OVERLAY_STREAM_WRITE(0, cmd);
}

// NEW (§3.9)
void read_sparse_weights() {
  uint32_t cmd = {
    .size = num_elements,               // ← Logical size
    .compress_mode = COMPRESS_2TO4,     // ← Hardware computes physical
  };
  OVERLAY_STREAM_WRITE(0, cmd);
  
  // Read occupancy
  uint32_t status = READ_CSR(OVERLAY_STATUS(0));
  printf("L1 used: %d%%\n", status.l1_occupancy_percent);
}
```

---

### TurboQuant — ✅ HEAVILY AFFECTED

TurboQuant is impacted by multiple sections:

#### Impact 1: Metadata Output (§4.5 — NEW)

```c
// OLD: No documented metadata handling
OVERLAY_STREAM_WRITE(0, { .src = input, .dest = output });

// NEW: Must save scale factor with each vector
memcpy(l1_ptr + 0, compressed_data, 48);   // Compressed: 48 bytes
*(float*)(l1_ptr + 48) = scale_factor;     // Scale: 4 bytes
// Total per vector: 52 bytes (vs 512 bytes uncompressed = 10.1× reduction)
```

**Why critical:** Without scale factor, decompression is impossible.

#### Impact 2: L1 Allocation (§3.7 — NEW)

```c
// OLD: No documented strategy
#define TQ_OUTPUT_BUFFER L1_BASE + 100*1024

// NEW: Pre-allocate based on actual compression
#define KV_VECTORS 1024
#define KV_COMPRESSED_SIZE (128 * 3 / 8)    // 128×3-bit = 48 bytes
#define KV_SCALE_SIZE 4
#define KV_TOTAL (KV_VECTORS * (KV_COMPRESSED_SIZE + KV_SCALE_SIZE))
                                             // 1024 × 52 = 52 KB
// Now entire KV-cache fits in L1! (was 512 KB, now 52 KB)
```

#### Impact 3: Occupancy Tracking (§3.9 — NEW)

```c
// OLD: No feedback from hardware
// Firmware guesses occupancy

// NEW: Hardware reports actual occupancy
uint32_t status = READ_CSR(TURBOQUANT_STATUS_REG);
uint32_t occupancy = (status >> 24) & 0xFF;  // 0-100%

if (occupancy < 50) {
  // Can load more buffers
  LOAD_MORE_KV_CACHE();
}
```

#### Impact 4: Size Calculation (§3.8 — NEW)

```c
// TurboQuant output size is fixed by algorithm
// 128-element FP32 input → 128×3-bit output = 48 bytes
// This is NOT variable and hardware generates automatically
```

---

### Summary: Feature Impact Matrix

| Feature | Section | RTL Changes | Firmware Changes | Protocol Changes |
|---------|---------|------------|------------------|------------------|
| **Z-Plane Sparsity** | §2.7.9 (HDD) | None | None | None |
| **2:4 NVIDIA Sparsity** | §3.1–3.9 | tt_compressed_data_tracker, tt_axi_compressed_intf, decompressor | Logical size, read status | ARLEN auto-adjust (AXI field only) |
| **TurboQuant** | §4.1–4.6 | Scale generation, occupancy register | Save scale, track L1 alloc | Metadata in status register |

---

## 4. TurboQuant IP Integration Guide

TurboQuant is a **vector quantization accelerator** that performs rotation + scalar quantization for KV-cache compression. Based on the attached TurboQuant HDD, here's how to integrate it into N1B0.

### 4.1 TurboQuant Architecture Decision

**Question:** Where should TurboQuant live?

- **Option A: Within Tensix compute tile** (local, ai_clk domain)
  - ✅ No NoC traffic
  - ✅ Direct L1 access
  - ✅ Simple firmware integration
  - ❌ Only one vector at a time per tile
  - ❌ Limited parallelism (1 tile)

- **Option B: As autonomous overlay service** (dm_clk domain, pipelined)
  - ✅ Services all 12 Tensix tiles via NoC
  - ✅ Multiple vectors in-flight
  - ✅ Standalone operation (TRISC continues)
  - ❌ Requires CDC FIFOs (dm_clk ↔ noc_clk)
  - ❌ More complex firmware programming

**Recommendation:** **Option B (autonomous overlay service)** for maximum throughput. Can process one KV-cache vector per cycle while TRISCs continue compute.

### 4.2 TurboQuant RTL Architecture in Overlay

#### Position in Overlay Engine

```
TRISC commands
  ↓
Overlay stream register (ALGORITHM_MODE = TURBOQUANT)
  ├─ src_addr (KV cache vector in L1 or DRAM)
  ├─ dest_addr (compressed output destination)
  ├─ transform_params (rotation matrix, quantizer thresholds)
  └─ stream_id (0–7, overlayed with other streams)
  ↓
[NEW] tt_turboquant_decode_engine.sv
  ├─ Input: 128-element vectors (128×32-bit = 4 KB per vector)
  ├─ Stage 1: Sign flip + Permutation (combinational)
  ├─ Stage 2: FWHT (7 pipeline stages, 1 element per cycle × 8 lanes = 128 cycles)
  ├─ Stage 3: Normalization (dynamic scale calculation)
  ├─ Stage 4: Scalar quantizer (3-bit or 4-bit output)
  ├─ Stage 5: Packing (128×3-bit → 12 bytes output)
  └─ Latency: ~150 cycles total
  ↓
Output to L1 via overlay stream (512-bit side-channel)
```

#### Step 4.2.1: Create TurboQuant Engine Module

```systemverilog
// File: tt_turboquant_decode_engine.sv
module tt_turboquant_decode_engine #(
  parameter VECTOR_SIZE = 128,           // 128-element vectors
  parameter INPUT_WIDTH = 32,            // FP32 input
  parameter LANES = 8,                   // 8 parallel lanes
  parameter QUANT_WIDTH = 3,             // 3-bit output
  parameter PIPELINE_STAGES = 8
) (
  input  logic i_clk,
  input  logic i_rst_n,
  
  // Command interface (from overlay stream register)
  input  logic [VECTOR_SIZE-1:0][INPUT_WIDTH-1:0]  i_input_vector,
  input  tt_turboquant_pkg::tq_config_t            i_config,
  input  logic                                      i_valid,
  output logic                                      o_ready,
  
  // Output (compressed vector)
  output logic [(VECTOR_SIZE*QUANT_WIDTH)-1:0]  o_output_vector,
  output logic [31:0]                           o_scale_factor,
  output logic                                  o_output_valid,
  input  logic                                  i_output_ready
);
  
  import tt_turboquant_pkg::*;
  
  // ─── Stage 1: Sign Flip ───
  logic [VECTOR_SIZE-1:0][INPUT_WIDTH-1:0] stage1_data;
  always_comb begin
    for (int i = 0; i < VECTOR_SIZE; i++) begin
      if (i_config.sign_mask[i]) begin
        stage1_data[i] = -i_input_vector[i];  // Negate
      end else begin
        stage1_data[i] = i_input_vector[i];
      end
    end
  end
  
  // ─── Stage 2: Permutation (optional, absorbed in addressing) ───
  // For now, skip and apply permutation in software
  
  // ─── Stage 3–9: FWHT (7 pipeline stages) ───
  // Each stage processes butterflies at different span widths
  logic [VECTOR_SIZE-1:0][INPUT_WIDTH+$clog2(VECTOR_SIZE)-1:0] fwht_data[PIPELINE_STAGES];
  
  // FWHT butterfly datapath
  tt_fwht_core #(
    .NUM_ELEMENTS(VECTOR_SIZE),
    .DATA_WIDTH(INPUT_WIDTH),
    .LANES(LANES),
    .PIPELINE_STAGES(PIPELINE_STAGES)
  ) u_fwht (
    .i_clk(i_clk),
    .i_rst_n(i_rst_n),
    .i_data(stage1_data),
    .o_data(fwht_data),
    .o_valid()
  );
  
  // ─── Stage 10: Normalization ───
  logic [VECTOR_SIZE-1:0][INPUT_WIDTH+$clog2(VECTOR_SIZE)-1:0] norm_data;
  logic [31:0] scale;
  
  // Find max value and compute scale factor
  always_comb begin
    logic [INPUT_WIDTH+$clog2(VECTOR_SIZE)-1:0] max_val = '0;
    for (int i = 0; i < VECTOR_SIZE; i++) begin
      if (fwht_data[PIPELINE_STAGES-1][i] > max_val) begin
        max_val = fwht_data[PIPELINE_STAGES-1][i];
      end
    end
    // Scale to fit quantizer range (e.g., [-4, +3] for 3-bit)
    scale = (8 << 20) / (max_val >> 8);  // Q12.20 fixed point
    
    // Apply normalization
    for (int i = 0; i < VECTOR_SIZE; i++) begin
      norm_data[i] = (fwht_data[PIPELINE_STAGES-1][i] * scale) >> 20;
    end
  end
  
  // ─── Stage 11: Scalar Quantization ───
  logic [(VECTOR_SIZE*QUANT_WIDTH)-1:0] quant_data;
  
  // Symmetric uniform quantizer: range [-(2^(Q_W-1)), 2^(Q_W-1)-1]
  // For QUANT_WIDTH=3: range [-4, +3]
  always_comb begin
    for (int i = 0; i < VECTOR_SIZE; i++) begin
      if (norm_data[i] >= (4 << 20)) begin
        quant_data[(i*QUANT_WIDTH+QUANT_WIDTH-1):(i*QUANT_WIDTH)] = 3'b011;  // +3
      end else if (norm_data[i] >= (0 << 20)) begin
        quant_data[(i*QUANT_WIDTH+QUANT_WIDTH-1):(i*QUANT_WIDTH)] = 
          norm_data[i][22:20];  // Truncate to 3 bits
      end else if (norm_data[i] >= (-4 << 20)) begin
        quant_data[(i*QUANT_WIDTH+QUANT_WIDTH-1):(i*QUANT_WIDTH)] = 
          norm_data[i][22:20] | 3'b100;  // Sign bit set
      end else begin
        quant_data[(i*QUANT_WIDTH+QUANT_WIDTH-1):(i*QUANT_WIDTH)] = 3'b100;  // -4
      end
    end
  end
  
  // ─── Stage 12: Output Packing & Buffering ───
  // Pack 128×3-bit = 384 bits into 384-bit output register
  logic [(VECTOR_SIZE*QUANT_WIDTH)-1:0] output_reg;
  logic output_valid_reg;
  
  always_ff @(posedge i_clk) begin
    if (!i_rst_n) begin
      output_valid_reg <= 1'b0;
    end else if (i_valid && o_ready) begin
      output_reg <= quant_data;
      output_valid_reg <= 1'b1;
    end
  end
  
  // Output assignment
  assign o_output_vector = output_reg;
  assign o_scale_factor = scale;
  assign o_output_valid = output_valid_reg;
  assign o_ready = !output_valid_reg || i_output_ready;
  
endmodule
```

#### Step 4.2.2: Create FWHT Core (Reusable)

```systemverilog
// File: tt_fwht_core.sv (generic FWHT butterfly processor)
module tt_fwht_core #(
  parameter NUM_ELEMENTS = 128,
  parameter DATA_WIDTH = 32,
  parameter LANES = 8,
  parameter PIPELINE_STAGES = 7
) (
  input  logic i_clk,
  input  logic i_rst_n,
  
  input  logic [NUM_ELEMENTS-1:0][DATA_WIDTH-1:0] i_data,
  output logic [NUM_ELEMENTS-1:0][DATA_WIDTH+$clog2(NUM_ELEMENTS)-1:0] o_data,
  output logic o_valid
);
  
  localparam LOG_N = $clog2(NUM_ELEMENTS);
  localparam FWHT_WIDTH = DATA_WIDTH + LOG_N;
  
  // Pipelined FWHT stages
  logic [NUM_ELEMENTS-1:0][FWHT_WIDTH-1:0] stage[LOG_N];
  
  // Initial data
  assign stage[0] = i_data;
  
  // Generate FWHT stages
  generate
    for (genvar s = 0; s < LOG_N; s++) begin : gen_fwht_stages
      localparam STEP = 2 << s;
      localparam HALF = STEP >> 1;
      
      logic [NUM_ELEMENTS-1:0][FWHT_WIDTH-1:0] stage_data;
      
      always_comb begin
        stage_data = stage[s];
        
        for (int b = 0; b < NUM_ELEMENTS; b += STEP) begin
          for (int j = 0; j < HALF; j++) begin
            int a_idx = b + j;
            int b_idx = b + j + HALF;
            
            logic [FWHT_WIDTH-1:0] u = stage[s][a_idx];
            logic [FWHT_WIDTH-1:0] v = stage[s][b_idx];
            
            stage_data[a_idx] = u + v;
            stage_data[b_idx] = u - v;
          end
        end
      end
      
      if (s < LOG_N - 1) begin
        assign stage[s+1] = stage_data;
      end
    end
  endgenerate
  
  assign o_data = stage[LOG_N-1];
  assign o_valid = 1'b1;  // Combinational path
  
endmodule
```

### 4.3 TurboQuant SFR Integration

```systemverilog
// File: tt_turboquant_registers.sv

package tt_turboquant_pkg;
  
  typedef struct packed {
    logic [31:24]  sign_mask_index;    // Which pre-computed sign mask to use
    logic [23:16]  reserved;
    logic [15:8]   quant_width;        // 2, 3, or 4 bits
    logic [7:0]    enable;             // Enable TurboQuant pipeline
  } tq_config_t;
  
  localparam TQ_CTRL_OFFSET = 32'h0300;
  localparam TQ_CONFIG_OFFSET = 32'h0304;
  localparam TQ_STATUS_OFFSET = 32'h0308;
  localparam TQ_OUTPUT_OFFSET = 32'h030C;
  
endpackage

module tt_turboquant_registers #(
  parameter ADDR_WIDTH = 14,
  parameter DATA_WIDTH = 32
) (
  input  logic i_clk,
  input  logic i_rst_n,
  
  // APB interface
  input  logic [ADDR_WIDTH-1:0]  i_paddr,
  input  logic                   i_pwrite,
  input  logic                   i_psel,
  input  logic                   i_penable,
  input  logic [DATA_WIDTH-1:0]  i_pwdata,
  output logic [DATA_WIDTH-1:0]  o_prdata,
  output logic                   o_pready,
  output logic                   o_pslverr,
  
  // Functional
  output tt_turboquant_pkg::tq_config_t  o_config,
  input  logic [383:0]                   i_output_data,
  input  logic [31:0]                    i_scale,
  input  logic                           i_valid
);
  
  import tt_turboquant_pkg::*;
  
  tq_config_t config_reg;
  
  // Write logic
  always_ff @(posedge i_clk) begin
    if (!i_rst_n) begin
      config_reg <= '0;
    end else if (i_psel && i_penable && i_pwrite) begin
      case (i_paddr[3:2])
        2'h0: config_reg <= i_pwdata;  // TQ_CTRL_OFFSET
        default: ;
      endcase
    end
  end
  
  // Read logic
  always_comb begin
    o_prdata = '0;
    case (i_paddr[3:2])
      2'h0: o_prdata = config_reg;                // Ctrl
      2'h1: o_prdata = {31'b0, i_valid};         // Status
      2'h2: o_prdata = i_scale;                  // Scale factor
      default: o_prdata = '0;
    endcase
  end
  
  assign o_pready = 1'b1;
  assign o_pslverr = 1'b0;
  assign o_config = config_reg;
  
endmodule
```

### 4.4 Firmware Integration: TurboQuant

```c
// File: firmware/turboquant_kernel.c

void compress_kv_cache_turboquant(
  uint32_t *kv_cache_ptr,      // Input: uncompressed KV vectors
  uint32_t *compressed_ptr,    // Output: compressed vectors
  uint32_t num_vectors,        // How many vectors to compress
  uint32_t vector_length       // Elements per vector (128 typical)
) {
  // Configure TurboQuant for 3-bit quantization
  uint32_t tq_config = (1 << 0) |           // Enable
                       (3 << 8) |           // QUANT_WIDTH = 3
                       (0 << 24);           // Sign mask index 0
  WRITE_CSR(TQ_CTRL_REG, tq_config);
  
  // Stream vectors through TurboQuant engine
  for (int v = 0; v < num_vectors; v++) {
    // Load vector from KV cache (via L1 or direct DRAM)
    for (int e = 0; e < vector_length; e++) begin
      load_vector[e] = kv_cache_ptr[v * vector_length + e];
    end
    
    // Write to overlay stream (TurboQuant mode)
    uint32_t tq_cmd = {
      .src_addr = (uint32_t)&kv_cache_ptr[v * vector_length],
      .dest_addr = (uint32_t)&compressed_ptr[v * vector_length / 10],  // ~1/10 size
      .size = vector_length / 8,  // In beats (512-bit)
      .algorithm_mode = TURBOQUANT,
      .stream_id = 0
    };
    
    OVERLAY_STREAM_WRITE(0, tq_cmd);
    
    // Poll status
    while (!(TQ_STATUS & TQ_VALID)) { }
    
    // Read compressed output + scale
    uint32_t compressed_data = READ_CSR(TQ_OUTPUT_REG);
    uint32_t scale_factor = READ_CSR(TQ_SCALE_REG);
    
    // Store compressed output
    memcpy(&compressed_ptr[v * 48], &compressed_data, 48);  // 128×3-bit = 48 bytes
  }
}
```

### 4.5 TurboQuant Metadata Output & L1 Tracking

**Critical:** TurboQuant outputs **TWO data streams**, not one:

1. **Compressed quantized vector** (128×3-bit = 48 bytes)
2. **Scale factor metadata** (32-bit = 4 bytes) — **REQUIRED for decompression**

**Hardware generates both outputs automatically:**

```systemverilog
// In tt_turboquant_decode_engine.sv (updated output interface)
always_ff @(posedge i_clk) begin
  if (!i_rst_n) begin
    output_valid_reg <= 1'b0;
  end else if (i_valid && o_ready) begin
    // Store both compressed data AND scale
    compressed_output_reg <= quant_data;        // 384 bits
    scale_factor_reg <= scale;                  // 32 bits
    output_valid_reg <= 1'b1;
  end
end

// Output both streams
assign o_output_vector = compressed_output_reg;
assign o_scale_factor = scale_factor_reg;      // ← MUST be saved with data!
assign o_output_valid = output_valid_reg;
```

**Firmware MUST save scale factor with each compressed vector:**

```c
// Incorrect: loses scale factor
void turboquant_wrong() {
  OVERLAY_STREAM_WRITE(0, { .src = input, .dest = L1_COMPRESSED });
  // Problem: scale factor is generated but never stored!
  // Later decompression will fail (scale is lost)
}

// Correct: saves both compressed data AND scale
void turboquant_correct() {
  // Write input vector to overlay stream
  OVERLAY_STREAM_WRITE(0, { 
    .src = input_kv,                 // 512 bytes (128 FP32)
    .dest = L1_COMPRESSED_DATA,      // Destination for 48 bytes
    .algorithm = TURBOQUANT,
    .stream_id = 0
  });
  
  // Wait for completion
  while (!(OVERLAY_STATUS(0) & DONE)) { }
  
  // Read both outputs
  uint8_t compressed[48];
  memcpy(compressed, (void*)L1_COMPRESSED_DATA, 48);
  
  // Read scale factor from status register
  float scale = *(float*)READ_CSR(TURBOQUANT_SCALE_REG);
  
  // Save scale immediately after compressed data
  *(float*)(L1_COMPRESSED_DATA + 48) = scale;  // Scale is @ offset 48
  
  // Total occupancy: 48 + 4 = 52 bytes per vector
  // Original: 512 bytes (128 FP32) → Compressed: 52 bytes (10.1× reduction)
}
```

**L1 Layout for Compressed KV-Cache:**

```
L1 Address Space (per vector in KV-cache):
┌──────────────────────────────┐
│ Compressed vector (48 bytes) │  Offset +0
│ (128×3-bit quantized)        │
├──────────────────────────────┤
│ Scale factor (4 bytes)       │  Offset +48  ← CRITICAL: must be adjacent
│ (FP32 normalization scale)   │
├──────────────────────────────┤
│ [Next vector...]             │  Offset +52
└──────────────────────────────┘

Total per vector: 52 bytes
1024 vectors: 52 KB (vs 512 KB uncompressed)
```

---

### 4.6 TurboQuant Performance Estimate

```
Input:  KV-cache vector 128×FP32 = 512 bytes
Output: Compressed vector 128×3-bit = 48 bytes
Ratio:  ~10.7× compression

Per-vector latency:
  Sign flip + Permutation:     1 cycle
  FWHT (8 lanes):              128/8 = 16 cycles (7 stages pipelined)
  Normalization:               2 cycles
  Quantization:                1 cycle
  Output packing:              1 cycle
  Total:                        ~22 cycles @ 1 GHz

Throughput (pipelined):
  1 vector every 22 cycles = 45 M vectors/sec @ 1 GHz
  For 1024-token batch (1024 tokens × 2 = 2048 KV vectors):
    2048 / 45M = 45.5 µs (@ 1 GHz)
    @ 1.5 GHz: ~30 µs

Area estimate (5nm):
  FWHT butterflies:   ~50 K gates
  Quantizer + pack:   ~20 K gates
  Registers + mux:    ~10 K gates
  Total:              ~80 K gates (~0.4 mm²)
```

---

## 4.7 RTL Changes REQUIRED: Firmware Changes Are NOT Sufficient

**CRITICAL CLARIFICATION:** The compressed data control flow requires **BOTH RTL and Firmware changes**. Firmware changes ALONE are insufficient.

### 4.7.1 Why RTL Modules Are Mandatory

**Question:** Can we just update firmware to handle size differences, or do we need new RTL modules?

**Answer: RTL modules are MANDATORY.** Here's why:

```
Scenario A: WITHOUT RTL modules (firmware-only approach)
  Firmware writes: size_logical=1024, compress_mode=2:4
                      ↓
  Hardware (unchanged): Creates AXI read with ARLEN=63 (wrong!)
                      ↓
  AXI transfers: 64 beats = 4096 bytes (WRONG - only 2048 available)
                      ↓
  Result: TIMEOUT, data corruption, or stall
          
Scenario B: WITH RTL modules (correct approach)
  Firmware writes: size_logical=1024, compress_mode=2:4
                      ↓
  tt_compressed_data_tracker.sv: size_physical = 1024/2 = 512
                      ↓
  tt_axi_compressed_interface.sv: ARLEN = (512*4)/64 - 1 = 31 ✓
                      ↓
  AXI transfers: 32 beats = 2048 bytes (CORRECT)
                      ↓
  tt_noc2axi_sparse_decompressor.sv: Expands 2048 → 4096
                      ↓
  L1 receives: 4096 bytes uncompressed ✓
```

### 4.7.2 Required RTL Modules (NOT Optional)

**Module 1: tt_compressed_data_tracker.sv**
```systemverilog
// Purpose: Compute physical size from logical size + compress_mode
// Location: In overlay stream controller or NIU
// Input: size_logical [31:0], compress_mode [3:0]
// Output: size_physical [31:0], arlen [7:0], compression_ratio [7:0]

// Logic (already documented in §3.6):
case (compress_mode)
  0: size_physical = size_logical;           // No compression
  1: size_physical = size_logical >> 1;      // 2:4 sparsity: ÷2
  2: size_physical = (size_logical*3)>>5;    // TurboQuant: ÷32×3
  default: size_physical = size_logical;
endcase

arlen = (size_physical >> 6) - 1;  // Convert to AXI beats
```

**Why firmware CANNOT do this:**
- ARLEN must be output in same cycle as address
- Firmware cannot inject values into AXI command path
- Must be combinational in RTL

---

**Module 2: tt_axi_compressed_interface.sv**
```systemverilog
// Purpose: Inject computed ARLEN into AXI AR command bus
// Location: Between overlay/NIU and AXI master interface
// Input: arlen_computed [7:0] from tt_compressed_data_tracker
// Output: axi_arlen [7:0] (replaces default)

// Why firmware CANNOT do this:
// AXI ARLEN is a hardware signal, not a firmware register
// Firmware cannot directly drive AXI bus signals
// Must be RTL mux: select between default ARLEN and compressed ARLEN
```

---

**Module 3: tt_noc2axi_sparse_decompressor.sv**
```systemverilog
// Purpose: Expand sparse AXI RDATA back to logical size
// Location: On AXI RDATA path before L1 side-channel
// Input: rdata [511:0] (compressed flit)
// Output: expanded_rdata [511:0] (with zeros inserted)
// Latency: 2–3 cycles

// Why firmware CANNOT do this:
// Must happen on hardware data path (AXI RDATA)
// Firmware never sees raw compressed data
// Decompression pattern is deterministic (2:4 or Turbo-specific)
// Must be pipelined to meet timing
```

---

**Module 4: Extended Status Register**
```systemverilog
// Purpose: Report compression metrics back to firmware
// Location: overlay stream status or NIU CSR space
// New fields:
//   [31:24] l1_occupancy_percent (0–100)
//   [23:16] compression_ratio (0–255, where 255=100%)
//   [15:8]  bytes_transferred (physical bytes on AXI)
//   [7:2]   reserved
//   [1]     error
//   [0]     done

// Why firmware CANNOT do this:
// Must track in-flight bytes (hardware counter)
// Must compute occupancy % in real-time
// Firmware has no visibility into hardware counters
```

---

### 4.7.3 No Protocol Changes Needed (Only Parameter Adjustment)

**Good news:** AXI/NoC protocols themselves **do NOT need changes**. We only adjust existing parameters:

| Protocol | Change | Mechanism | Firmware Aware? |
|----------|--------|-----------|-----------------|
| **AXI AR (read address)** | ARLEN value adjusted | tt_axi_compressed_intf selects ARLEN | No (automatic) |
| **AXI R (read data)** | Same flit size (512b) | Decompressor expands payload | No (automatic) |
| **NoC flit** | Metadata in status reg | Extended CSR register | **Yes** (firmware reads) |

**Examples:**
```
Standard AXI AR:  ARLEN=63, ARSIZE=6 (64-byte beats), ARLEN_TYPE=INCR
Compressed AXI AR: ARLEN=31, ARSIZE=6 (same), ARLEN_TYPE=INCR
                   ↑ Only this changes (and it's already an AXI field)

Standard AXI R: 512-bit flit with 64 bytes of (uncompressed) data
Compressed AXI R: 512-bit flit with 32 bytes of (compressed) data
                  Decompressor expands to 64 bytes before L1
```

**Firmware NEVER cares about ARLEN** — hardware handles it automatically.

---

### 4.7.4 RTL Implementation Checklist

**MANDATORY RTL modules:**

- [ ] **tt_compressed_data_tracker.sv** (~100 lines)
  - Combinational: compute size_physical, arlen, ratio
  - Inputs: size_logical, compress_mode
  - Outputs: size_physical, arlen_computed, compression_ratio

- [ ] **tt_axi_compressed_interface.sv** (~50 lines)
  - Mux between default ARLEN and compressed ARLEN
  - Instantiate in AXI master interface path
  - Check timing closure (critical path)

- [ ] **tt_noc2axi_sparse_decompressor.sv** (~200 lines)
  - Already partially documented in §3.3.1
  - Pipelined 2–3 cycles
  - Must handle all sparsity patterns (2:4, block-sparse, custom)

- [ ] **Extended overlay status register** (~50 lines)
  - Add new fields to existing status CSR
  - Fields: l1_occupancy_percent, compression_ratio, bytes_transferred
  - Accessible via firmware CSR read

---

### 4.7.5 Firmware Changes Checklist

**FIRMWARE-ONLY (no RTL dependency):**

- [ ] Write logical size (not physical size)
  ```c
  OVERLAY_STREAM_WRITE(0, { .size = 1024 });  // Not 512!
  ```

- [ ] Read extended status register
  ```c
  uint32_t status = READ_CSR(OVERLAY_STATUS(0));
  printf("Occupancy: %d%%\n", (status >> 24) & 0xFF);
  ```

- [ ] Pre-allocate L1 based on compression_ratio
  ```c
  uint32_t ratio = (status >> 16) & 0xFF;  // 0–255
  uint32_t logical_size = 1024;
  uint32_t physical_size = (logical_size * ratio) / 255;
  allocate_l1_region(physical_size);
  ```

- [ ] Save metadata (TurboQuant only)
  ```c
  *(float*)(l1_ptr + 48) = scale_factor;  // Must be adjacent
  ```

---

## 5. RTL Integration Checklist

### 5.1 Module Integration

- [ ] Define package with register/config structs
- [ ] Create register block module (APB slave interface)
- [ ] Create main datapath module (combinational or pipelined)
- [ ] Instantiate in parent hierarchy (Tensix/overlay/NIU)
- [ ] Connect clock/reset signals
- [ ] Add CSR address decoding
- [ ] Add data path multiplexing (if multiple IP sharing resources)
- [ ] Generate RTL stub for simulation

### 5.2 Clock Domain & CDC

- [ ] Identify all clock domains used
- [ ] Audit all async clock crossings
- [ ] Add CDC FIFOs / sync stages where needed
- [ ] Verify CDC cover properties (Questa, Synopsys)
- [ ] Document CDC path in design review

### 5.3 Memory & Area

- [ ] Estimate SRAM/latch macro count
- [ ] Allocate SRAM macros in memory compiler (Samsung/ARM DK)
- [ ] Add to memory_list CSV (update baseline)
- [ ] Run physical synthesis (estimate area, timing)
- [ ] Compare with budget (e.g., 500 K gates per feature)

### 5.4 Integration with DFX

- [ ] Add module to DFX scan chain (if scannable)
- [ ] Add module to EDC ring (if applicable)
- [ ] Add debug hooks (internal observation signals)
- [ ] Create BIST pattern (if has SRAM)
- [ ] Document DFX coverage expectations

### 5.5 Power Management

- [ ] Add clock gating if applicable (ICG cell)
- [ ] Define power domains (core / uncore / aon)
- [ ] Verify reset isolation (especially for harvested tiles)
- [ ] Add to power domain chain (for power sequencing)
- [ ] Estimate power consumption (dynamic + leakage)

### 5.6 Documentation

- [ ] Create RTL-verified HDD section for IP
- [ ] Add to SFR memory map (§14 of N1B0_NPU_HDD_v1.00.md)
- [ ] Add to tile hierarchy diagram
- [ ] Document firmware API and CSR sequences
- [ ] Add verification plan and test cases

---

## 6. Firmware Programming Guide Template

### 6.1 Standard Firmware API Pattern

```c
// ═══════════════════════════════════════════════════════════════
// File: firmware/ip_kernel_<feature>.c
// Purpose: Firmware integration for new IP module
// ═══════════════════════════════════════════════════════════════

#include "io.h"
#include "trisc.h"
#include "noc_cfg.h"

// ─────────────────────────────────────────────────────────────
// 1. Configuration & Initialization
// ─────────────────────────────────────────────────────────────

void init_<feature>() {
  // Step 1: Read default config from ROM or flash
  uint32_t config = READ_CSR(FEATURE_CONFIG_DEFAULT_ADDR);
  
  // Step 2: Write to CSR registers (enable, mode, threshold params)
  WRITE_CSR(FEATURE_CTRL_REG, config | FEATURE_ENABLE_MASK);
  
  // Step 3: Poll ready bit
  while (!(READ_CSR(FEATURE_STATUS_REG) & FEATURE_READY)) {
    // Optional: add timeout counter
  }
}

// ─────────────────────────────────────────────────────────────
// 2. Command Issue (Overlay Stream Pattern)
// ─────────────────────────────────────────────────────────────

void issue_<feature>_command(
  uint32_t src_addr,
  uint32_t dst_addr,
  uint32_t num_elements,
  uint8_t stream_id
) {
  // Format CSR command
  uint32_t cmd = {
    .src = src_addr,
    .dst = dst_addr,
    .size = num_elements,
    .algorithm = FEATURE_ALGORITHM_ID,
    .stream_id = stream_id
  };
  
  // Write to overlay stream register (triggers DMA)
  OVERLAY_STREAM_CMD_WRITE(stream_id, cmd);
}

// ─────────────────────────────────────────────────────────────
// 3. Status Polling
// ─────────────────────────────────────────────────────────────

uint32_t poll_<feature>_status(uint8_t stream_id, uint32_t timeout_cycles) {
  uint32_t start = CYCLE_COUNTER;
  
  while (1) {
    uint32_t status = READ_CSR(FEATURE_STATUS_REG);
    
    if (status & FEATURE_DONE) {
      return STATUS_OK;
    }
    if (status & FEATURE_ERROR) {
      return STATUS_ERROR;
    }
    if ((CYCLE_COUNTER - start) > timeout_cycles) {
      return STATUS_TIMEOUT;
    }
  }
}

// ─────────────────────────────────────────────────────────────
// 4. Synchronization with Other TRISCs
// ─────────────────────────────────────────────────────────────

void sync_feature_complete(uint8_t sem_id) {
  // TRISC0 waits for TRISC1 to finish feature computation
  asm volatile ("semget %[id]" : : [id] "r" (sem_id));
  
  // TRISC1 signals completion
  asm volatile ("sempost %[id]" : : [id] "r" (sem_id));
}

// ─────────────────────────────────────────────────────────────
// 5. Error Handling
// ─────────────────────────────────────────────────────────────

void handle_<feature>_error(uint32_t error_code) {
  switch (error_code) {
    case ERROR_OVERFLOW:
      // Reduce input magnitude or recalibrate scale
      break;
    case ERROR_TIMEOUT:
      // Reset module via CSR
      WRITE_CSR(FEATURE_RESET_REG, 1);
      break;
    case ERROR_ADDRESS_RANGE:
      // Secure fence violation (SMN filter)
      break;
  }
}

// ─────────────────────────────────────────────────────────────
// 6. Main Kernel Example
// ─────────────────────────────────────────────────────────────

void main_kernel(uint32_t arg0, uint32_t arg1) {
  // TRISC0 (unpack / setup)
  if (TRISC_ID == 0) {
    init_<feature>();
    
    for (int i = 0; i < NUM_ITERATIONS; i++) {
      // Fetch input data
      uint32_t src = L1_BASE + i * INPUT_SIZE;
      uint32_t dst = L1_BASE + (i % 2) * BUFFER_SIZE;  // Double buffer
      
      // Issue overlay command
      issue_<feature>_command(src, dst, INPUT_SIZE, 0);
      
      // Signal TRISC1 to start compute
      asm volatile ("sempost %[id]" : : [id] "r" (SEM_TRISC0_DONE));
    }
  }
  
  // TRISC1 (compute)
  if (TRISC_ID == 1) {
    for (int i = 0; i < NUM_ITERATIONS; i++) {
      // Wait for TRISC0 to load data
      asm volatile ("semget %[id]" : : [id] "r" (SEM_TRISC0_DONE));
      
      // Poll feature status
      uint32_t status = poll_<feature>_status(0, 1000);
      if (status != STATUS_OK) {
        handle_<feature>_error(status);
        break;
      }
      
      // Read result (if applicable)
      uint32_t result = READ_CSR(FEATURE_RESULT_REG);
      
      // Continue compute or write output
    }
  }
}
```

---

## 7. Verification and Testing Strategy

### 7.1 Unit Test Template (Testbench)

```verilog
// File: tb/tb_feature_engine.sv

module tb_feature_engine ();
  
  // Clocks & resets
  logic clk, rst_n;
  
  // DUT instance
  tt_feature_engine u_dut (
    .i_clk(clk),
    .i_rst_n(rst_n),
    .i_config(),
    .o_status(),
    .i_input_data(),
    .o_output_data()
  );
  
  // Test stimulus
  initial begin
    // Initialize
    rst_n = 0;
    #10ns rst_n = 1;
    
    // Test 1: Basic config write
    write_csr(FEATURE_CONFIG_ADDR, 32'h0000000F);
    assert (dut.config_reg == 32'h0000000F);
    
    // Test 2: Data path
    @(posedge clk);
    i_input_data = 32'hDEADBEEF;
    @(posedge clk);
    assert (u_dut.result_stage1 == expected_result1);
    
    // Test 3: Multi-cycle operation
    repeat (50) @(posedge clk);
    assert (o_output_data == expected_output);
    assert (o_status[DONE] == 1);
    
    $finish;
  end
  
  // Clock generation
  always #5ns clk = ~clk;
  
endmodule
```

### 7.2 Integration Test (Firmware + RTL)

```c
// File: firmware/test_feature_integration.c

void test_feature_basic() {
  printf("Test: Feature basic operation\n");
  
  // Initialize
  init_feature();
  
  // Configure
  WRITE_CSR(FEATURE_CONFIG_REG, 0x00000001);  // Enable
  
  // Load test vector (1024 elements)
  uint32_t test_vector[1024] = { ... };
  memcpy((void*)L1_TEST_BASE, test_vector, 4096);
  
  // Issue command
  issue_feature_command(L1_TEST_BASE, L1_OUTPUT_BASE, 1024, 0);
  
  // Poll completion
  uint32_t status = poll_feature_status(0, 10000);
  assert(status == STATUS_OK);
  
  // Verify output
  uint32_t output[1024];
  memcpy(output, (void*)L1_OUTPUT_BASE, 4096);
  
  // Compare against golden reference
  for (int i = 0; i < 1024; i++) {
    assert_equal(output[i], golden_output[i], 
      "Mismatch at element %d", i);
  }
  
  printf("✓ Test passed\n");
}

void test_feature_stress() {
  printf("Test: Feature throughput stress\n");
  
  uint32_t num_vectors = 10000;
  uint32_t errors = 0;
  
  for (int v = 0; v < num_vectors; v++) {
    // Random configuration per vector
    uint32_t config = random() & 0xFF;
    WRITE_CSR(FEATURE_CONFIG_REG, config);
    
    // Issue command
    issue_feature_command(
      L1_TEST_BASE + (v % 8) * BUFFER_SIZE,
      L1_OUTPUT_BASE + (v % 8) * BUFFER_SIZE,
      1024,
      v % 8
    );
    
    // Poll status
    if (poll_feature_status(v % 8, 10000) != STATUS_OK) {
      errors++;
    }
  }
  
  printf("Completed %d vectors with %d errors\n", num_vectors, errors);
  assert(errors == 0);
}
```

### 7.3 Performance Validation

```python
# File: perf_validation.py

import numpy as np
import argparse

def measure_feature_throughput():
    """Measure feature engine throughput in vectors/sec"""
    
    num_vectors = 10000
    vector_size = 128
    
    # Simulate firmware execution
    cycles_per_vector = run_simulation(
        kernel_path="firmware/test_feature_perf.c",
        num_vectors=num_vectors
    )
    
    # Calculate metrics
    total_cycles = cycles_per_vector * num_vectors
    clock_freq_mhz = 1000  # Assume 1 GHz
    total_time_us = total_cycles / clock_freq_mhz
    throughput_mvps = num_vectors / total_time_us
    
    # Compare against target
    target_throughput = 50  # Million vectors/sec @ 1 GHz
    
    print(f"Cycles per vector:  {cycles_per_vector}")
    print(f"Total time:         {total_time_us:.1f} µs")
    print(f"Throughput:         {throughput_mvps:.1f} Mvps")
    print(f"Target:             {target_throughput} Mvps")
    print(f"Status:             {'✓ PASS' if throughput_mvps >= target_throughput else '✗ FAIL'}")
    
    return throughput_mvps >= target_throughput

if __name__ == "__main__":
    measure_feature_throughput()
```

---

## Summary: Three-Phase Implementation Roadmap

### Phase 1: SFR & Interface (Week 1)
- Define register map and package
- Create register block RTL
- Add to Tensix tile hierarchy
- Create firmware API stub

### Phase 2: Datapath & Integration (Weeks 2–3)
- Implement main processing module
- Add clock/reset/CDC
- Integrate with L1 or overlay
- Create unit testbench

### Phase 3: Verification & Signoff (Week 4)
- Run integration tests
- Validate performance
- Complete DFX coverage
- Update HDD documentation

---

**End of IP Design Guide for N1B0 NPU**

# Tensix Cluster IP Integration Implementation Guide
## Step 2.4.2: Add to Tensix Cluster Hierarchy

**Document Version:** 1.0  
**Date:** 2026-04-04  
**Purpose:** Detailed RTL implementation guide for integrating new IP into Tensix cluster  
**Target Audience:** RTL Engineers, Hardware Architects  
**Related Files:**
- `/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_tensix_with_l1.sv` (cluster module)
- `/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_instrn_engine.sv` (register block)

---

## Part 1: Understanding Step 2.4.2

### What Does "Add to Tensix Cluster Hierarchy" Mean?

**Step 2.4.2** is about **instantiating new IP modules inside the Tensix cluster container** and properly connecting them to:

1. **CSR (Configuration/Status Register) signals** — from register block for firmware control
2. **L1 memory interface** — for accessing/writing L1 data (128-bit local port)
3. **Overlay stream signals** — for autonomous DMA (if needed)
4. **Clock and reset** — proper synchronization across clock domains
5. **Output data path** — to TRISC, other engines, or back to L1

### The Tensix Cluster Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ tt_tensix_with_l1 (CLUSTER CONTAINER)                          │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ L1 SRAM Macros (3 MB per tile, 768 KB per actual tile)  │  │
│  │ - 512 memory macros per tile (N1B0 4× expansion)        │  │
│  │ - 128-bit TRISC port (read/write)                       │  │
│  │ - 512-bit NoC side-channel (decompression path)         │  │
│  └──────────────────────────────────────────────────────────┘  │
│       ↑          ↑          ↑          ↑                        │
│       │          │          │          │                        │
│  ┌────┴─────────┬┴──────────┼────────┬┘────────────────────┐   │
│  │              │           │        │                     │   │
│  │         ┌────▼──────────┐│   ┌────▼──────────┐    ┌─────▼─┐ │
│  │         │ tt_tensix #0  ││   │ tt_tensix #1  │    │[NEW IP]│ │
│  │         │ - TRISC0/1/2/3││   │ - TRISC0/1/2/3│    │Instance│ │
│  │         │ - FPU         ││   │ - FPU         │    └────┬───┘ │
│  │         │ - TDMA        ││   │ - TDMA        │         │     │
│  │         └────┬──────────┘│   └────┬──────────┘    ┌────▼──┐  │
│  │              │           │        │              │CSR IF │  │
│  │              └───┬────────┴────────┴──────────────┤       │  │
│  │                  │ (overlayed)                   └───┬────┘  │
│  │          ┌───────▼────────────────┐                  │       │
│  │          │ Register Block         │                  │       │
│  │          │ - CLUSTER_CTRL         │◄─────────────────┘       │
│  │          │ - T6_L1_CSR            │                          │
│  │          │ - Overlay stream regs  │                          │
│  │          │ - [NEW IP REGS]        │ ← Step 2.4.1            │
│  │          └───────┬────────────────┘                          │
│  │                  │                                           │
│  └──────────────────┼───────────────────────────────────────────┘
│                     │
│              (CSR/register interface)
│
└─────────────────────────────────────────────────────────────────
```

---

## Part 2: RTL Implementation — Sparsity Engine Example

### Step 1: Define the IP Package

**File: `/tt_rtl/tt_tensix_neo/src/hardware/sparsity/rtl/tt_sparsity_pkg.sv`**

```systemverilog
package tt_sparsity_pkg;

  // ═══════════════════════════════════════════════════════
  // SFR Register Map (within Tensix cluster address space)
  // ═══════════════════════════════════════════════════════
  localparam SPARSITY_SFR_BASE = 32'h0200;  // Allocated in 2.4.1
  
  localparam SPARSITY_CTRL_OFFSET      = 32'h0000;  // 0x0200
  localparam SPARSITY_ZMASK_OFFSET     = 32'h0004;  // 0x0204
  localparam SPARSITY_CONFIG_OFFSET    = 32'h0008;  // 0x0208
  localparam SPARSITY_STATUS_OFFSET    = 32'h000C;  // 0x020C
  localparam SPARSITY_RESULT_OFFSET    = 32'h0010;  // 0x0210
  
  // ═══════════════════════════════════════════════════════
  // Register Field Definitions
  // ═══════════════════════════════════════════════════════
  typedef struct packed {
    logic [31:8]  reserved;
    logic         enable;        // [0] Enable sparsity engine
    logic [2:1]   mode;          // [2:1] 0=off, 1=l1_skip, 2=dram_compress
  } sparsity_ctrl_t;
  
  typedef struct packed {
    logic [31:0]  zmask;         // 32-bit z-plane skip mask
  } sparsity_zmask_t;
  
  typedef struct packed {
    logic [31:16] reserved;
    logic [15:12] data_width;    // 0=INT8, 1=INT16, 2=FP16B, 3=FP32
    logic [11:5]  num_zplanes;   // log2(N) where N = vector size
    logic [4:0]   reserved2;
  } sparsity_config_t;
  
  typedef struct packed {
    logic [31:2]  reserved;
    logic         error;         // [1] Error during operation
    logic         ready;         // [0] Ready for next command
  } sparsity_status_t;

endpackage
```

### Step 2: Create Sparsity Engine Module

**File: `/tt_rtl/tt_tensix_neo/src/hardware/sparsity/rtl/tt_sparsity_engine.sv`**

```systemverilog
module tt_sparsity_engine #(
  parameter DATA_WIDTH = 128,          // L1-local data width (128-bit)
  parameter NUM_STREAMS = 4,           // Parallel transform streams
  parameter VECTOR_WIDTH = 256         // Max 256-element vectors
) (
  // ═══════════════════════════════════════════════════════
  // Clock and Reset
  // ═══════════════════════════════════════════════════════
  input  logic i_clk,              // dm_clk (L1 domain)
  input  logic i_rst_n,
  
  // ═══════════════════════════════════════════════════════
  // CSR Interface (from register block)
  // ═══════════════════════════════════════════════════════
  input  tt_sparsity_pkg::sparsity_ctrl_t    i_ctrl,
  input  tt_sparsity_pkg::sparsity_zmask_t   i_zmask,
  input  tt_sparsity_pkg::sparsity_config_t  i_config,
  output tt_sparsity_pkg::sparsity_status_t  o_status,
  output logic [31:0]                        o_result_data,
  
  // ═══════════════════════════════════════════════════════
  // L1 Memory Interface (128-bit local read)
  // ═══════════════════════════════════════════════════════
  input  logic [DATA_WIDTH-1:0]  i_l1_data,           // From L1 SRAM
  output logic [15:0]            o_l1_addr,           // Address (bank+offset)
  output logic                   o_l1_rd_valid,       // Read strobe
  
  // ═══════════════════════════════════════════════════════
  // Output Data Path
  // ═══════════════════════════════════════════════════════
  output logic [DATA_WIDTH-1:0]  o_output_data,       // Processed output
  output logic                   o_output_valid       // Output valid strobe
);
  
  import tt_sparsity_pkg::*;
  
  // ═══════════════════════════════════════════════════════
  // Internal State Machine
  // ═══════════════════════════════════════════════════════
  typedef enum {
    IDLE,
    READING_L1,
    PROCESSING,
    WRITING_OUTPUT
  } state_t;
  
  state_t state, next_state;
  
  logic [DATA_WIDTH-1:0] l1_data_latched;
  logic [31:0]          result_latched;
  logic                 ready_flag;
  
  // ═══════════════════════════════════════════════════════
  // State Machine Logic
  // ═══════════════════════════════════════════════════════
  always_ff @(posedge i_clk) begin
    if (!i_rst_n) begin
      state <= IDLE;
      ready_flag <= 1'b1;
    end else begin
      state <= next_state;
    end
  end
  
  always_comb begin
    next_state = state;
    o_l1_rd_valid = 1'b0;
    o_output_valid = 1'b0;
    o_result_data = result_latched;
    o_status = {30'b0, 1'b0, ready_flag};
    
    case (state)
      IDLE: begin
        ready_flag = 1'b1;
        if (i_ctrl.enable) begin
          next_state = READING_L1;
          o_l1_rd_valid = 1'b1;  // Request L1 read
        end
      end
      
      READING_L1: begin
        ready_flag = 1'b0;
        // Wait one cycle for L1 data
        next_state = PROCESSING;
        l1_data_latched = i_l1_data;  // Capture L1 data
      end
      
      PROCESSING: begin
        ready_flag = 1'b0;
        // Apply z-plane masking based on zmask
        // Pseudo-logic: Skip z-planes where zmask[i]=1
        if (i_config.data_width == 0) begin  // INT8
          // INT8: 16 elements per z-plane
          result_latched = apply_zmask_int8(l1_data_latched, i_zmask);
        end else if (i_config.data_width == 1) begin  // INT16
          // INT16: 8 elements per z-plane
          result_latched = apply_zmask_int16(l1_data_latched, i_zmask);
        end else begin  // FP32
          // FP32: 4 elements per z-plane
          result_latched = apply_zmask_fp32(l1_data_latched, i_zmask);
        end
        next_state = WRITING_OUTPUT;
      end
      
      WRITING_OUTPUT: begin
        ready_flag = 1'b1;
        o_output_valid = 1'b1;
        next_state = IDLE;
      end
    endcase
  end
  
  // ═══════════════════════════════════════════════════════
  // L1 Address Generation
  // ═══════════════════════════════════════════════════════
  always_comb begin
    // Simplified: address selection based on config
    o_l1_addr = i_config.num_zplanes;  // Use config as address offset
  end
  
  // ═══════════════════════════════════════════════════════
  // Sparsity Processing Functions (placeholder)
  // ═══════════════════════════════════════════════════════
  function logic [31:0] apply_zmask_int8(logic [127:0] data, sparsity_zmask_t mask);
    // Apply z-plane masking for INT8 (16 elements per z-plane)
    // Return zeros for masked z-planes
    return {data[127:64] & {64{!mask.zmask[1]}}, 
            data[63:0]  & {64{!mask.zmask[0]}}};
  endfunction
  
  function logic [31:0] apply_zmask_int16(logic [127:0] data, sparsity_zmask_t mask);
    // Apply z-plane masking for INT16 (8 elements per z-plane)
    return data & {128{!mask.zmask[0]}};
  endfunction
  
  function logic [31:0] apply_zmask_fp32(logic [127:0] data, sparsity_zmask_t mask);
    // Apply z-plane masking for FP32 (4 elements per z-plane)
    return data & {128{!mask.zmask[0]}};
  endfunction

endmodule
```

### Step 3: Add Register Block Entry (in tt_register_blocks.sv)

**File: `/tt_rtl/tt_tensix_neo/src/hardware/registers/rtl/tt_register_blocks.sv`**

```systemverilog
// ═══════════════════════════════════════════════════════
// NEW: Sparsity Register Block Instantiation
// ═══════════════════════════════════════════════════════

tt_sparsity_registers #(
  .ADDR_WIDTH(14),
  .DATA_WIDTH(32)
) u_sparsity_registers (
  .i_clk(i_ai_clk),
  .i_rst_n(i_rst_n),
  
  // APB interface (from CSR arbiter)
  .i_paddr(cfg_reg_addr),
  .i_pwrite(cfg_reg_write),
  .i_psel(sparsity_sel),              // Address decode: 0x0200-0x02FF
  .i_penable(cfg_reg_enable),
  .i_pwdata(cfg_reg_wdata),
  .o_prdata(sparsity_rdata),
  .o_pready(sparsity_ready),
  .o_pslverr(sparsity_error),
  
  // Functional interface to sparsity engine
  .o_ctrl(sparsity_ctrl),
  .o_zmask(sparsity_zmask),
  .o_config(sparsity_config),
  .i_status(sparsity_status),
  .i_result_data(sparsity_result_data)
);

// ═══════════════════════════════════════════════════════
// Address Decoder (in CSR arbiter)
// ═══════════════════════════════════════════════════════
assign sparsity_sel = (cfg_reg_addr[15:8] == 8'h02) ? 1'b1 : 1'b0;

// ═══════════════════════════════════════════════════════
// CSR Mux (add to read data multiplexer)
// ═══════════════════════════════════════════════════════
always_comb begin
  case (cfg_reg_addr[7:0])
    // ... existing register cases ...
    8'h00: csr_rdata = sparsity_rdata;  // Sparsity registers
    // ...
  endcase
end
```

### Step 4: **CRITICAL** — Add to Tensix Cluster (tt_tensix_with_l1.sv)

**File: `/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_tensix_with_l1.sv`**

This is the **most critical step** — instantiation in the cluster container.

#### Location: Inside generate block, after tt_tensix instantiation

```systemverilog
// ═══════════════════════════════════════════════════════
// LOCATION: In tt_tensix_with_l1.sv, around line 1215-1323
// INSIDE: generate block where tt_tensix is instantiated
// AFTER: each tt_tensix instance (u_t6)
// ═══════════════════════════════════════════════════════

if (i == 0) begin : neo
  
  // ─────────────────────────────────────────────────────
  // EXISTING: tt_tensix instantiation (UNCHANGED)
  // ─────────────────────────────────────────────────────
  tt_tensix #( )
    u_t6 (
      // ... all existing connections ...
      .*);
  
  // ═════════════════════════════════════════════════════
  // NEW: Sparsity Engine Instantiation (ADD THIS)
  // ═════════════════════════════════════════════════════
  
  tt_sparsity_engine #(
    .DATA_WIDTH(128),              // L1-local data width
    .NUM_STREAMS(4),               // Parallel streams
    .VECTOR_WIDTH(256)             // Max vector size
  ) u_sparsity_engine (
    
    // ─────────────────────────────────────────────────────
    // Clock and Reset (from cluster)
    // ─────────────────────────────────────────────────────
    .i_clk(i_dm_clk),              // dm_clk domain (L1 clock)
    .i_rst_n(i_rst_n),
    
    // ─────────────────────────────────────────────────────
    // CSR Interface (from register block)
    // Signals from tt_register_blocks.sv instantiation
    // ─────────────────────────────────────────────────────
    .i_ctrl(sparsity_ctrl),        // Config from CSR
    .i_zmask(sparsity_zmask),      // Z-plane mask from CSR
    .i_config(sparsity_config),    // Configuration from CSR
    .o_status(sparsity_status),    // Status back to CSR
    .o_result_data(sparsity_result_data),
    
    // ─────────────────────────────────────────────────────
    // L1 Memory Interface (128-bit)
    // Connect to L1 SRAM read port (same as TRISC uses)
    // ─────────────────────────────────────────────────────
    .i_l1_data(l1_rd_data[i]),     // From L1 SRAM read port
    .o_l1_addr(l1_sparsity_addr[i]),  // Address control
    .o_l1_rd_valid(l1_sparsity_rd_valid[i]),  // Read strobe
    
    // ─────────────────────────────────────────────────────
    // Output Data Path
    // ─────────────────────────────────────────────────────
    .o_output_data(sparsity_output_data[i]),
    .o_output_valid(sparsity_output_valid[i])
  );
  
  // ═════════════════════════════════════════════════════
  // Port Arbitration (if multiple masters access L1)
  // ═════════════════════════════════════════════════════
  
  // Assign L1 read addresses based on which master is active
  always_comb begin
    if (sparsity_output_valid[i]) begin
      // Sparsity engine has priority
      l1_rd_addr[i] = l1_sparsity_addr[i];
      l1_rd_valid[i] = l1_sparsity_rd_valid[i];
    end else begin
      // Default: TRISC L1 access
      l1_rd_addr[i] = trisc_l1_rd_addr[i];
      l1_rd_valid[i] = trisc_l1_rd_valid[i];
    end
  end
  
end  // End generate block

else begin : neo
  // ... other tensix instances (unchanged) ...
end
```

---

## Part 3: TurboQuant Integration Example

### Similar Pattern for TurboQuant

**File: `/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_tensix_with_l1.sv`**

```systemverilog
// ═════════════════════════════════════════════════════════
// TurboQuant Engine (follows same pattern)
// ═════════════════════════════════════════════════════════

tt_turboquant_decode_engine #(
  .VECTOR_SIZE(128),         // 128-element vectors
  .INPUT_WIDTH(32),          // FP32 input
  .LANES(8),                 // 8 parallel lanes
  .QUANT_WIDTH(3),           // 3-bit output
  .PIPELINE_STAGES(8)
) u_turboquant_decode_engine (
  
  // Clock and Reset (dm_clk domain, same as overlay)
  .i_clk(i_dm_clk),
  .i_rst_n(i_rst_n),
  
  // CSR Interface (from register block)
  .i_config(turboquant_config),      // Configuration
  .o_status(turboquant_status),      // Status
  .o_scale_factor(turboquant_scale),
  
  // L1 Memory Interface
  .i_l1_data(l1_rd_data[i]),
  .o_l1_addr(l1_tq_addr[i]),
  .o_l1_rd_valid(l1_tq_rd_valid[i]),
  
  // Output to L1 or overlay stream
  .o_output_vector(turboquant_output[i]),
  .o_output_valid(turboquant_output_valid[i]),
  
  // Optional: Direct overlay stream integration
  .o_overlay_stream_cmd(overlay_sparse_cmd[i])
);
```

---

## Part 4: Critical Connections Summary

### Clock Domain Assignments

| Signal | Clock Domain | Source | Destination |
|--------|--------------|--------|-------------|
| `i_clk` (sparsity, TurboQuant) | **dm_clk** | cluster | L1 access, autonomous operation |
| `i_ai_clk` (register block) | **ai_clk** | cluster | CSR interface, TRISC |
| `i_dm_clk` (cluster) | **dm_clk** | top-level | All L1-local IP |

### L1 Port Contention

| Master | Priority | When | L1 Port |
|--------|----------|------|---------|
| TRISC | High | Always available | 128-bit RW |
| Sparsity | Medium | When executing | 128-bit R only |
| TurboQuant | Medium | When executing | 128-bit R only |
| Overlay | Low | DMA phase | 512-bit side-channel |

**Arbitration Required:** If sparsity/TurboQuant use same L1 port as TRISC, need mux/arbiter.

### CSR Address Space Allocation

| Module | Base Address | Size | Lines |
|--------|-------------|------|-------|
| Sparsity | 0x0200 | 64 bytes | 16 registers |
| TurboQuant | 0x0240 | 64 bytes | 16 registers |
| Reserved | 0x0280–0x07FF | 1.5 KB | For future IP |

---

## Part 5: Firmware Usage Pattern

```c
// Firmware (TRISC) usage of integrated sparsity engine

void setup_sparsity(uint32_t zmask_value) {
  // Write CSR (local address, no offset)
  WRITE_CSR(SPARSITY_CTRL, 0x1);           // Enable
  WRITE_CSR(SPARSITY_ZMASK, zmask_value);  // Set mask
  WRITE_CSR(SPARSITY_CONFIG, 0x0100);      // INT8 mode, 4 z-planes
}

void process_with_sparsity() {
  // Trigger sparsity engine (L1-local operation)
  WRITE_CSR(SPARSITY_CTRL, 0x3);  // Enable + start
  
  // Poll status
  while (!(READ_CSR(SPARSITY_STATUS) & 0x1)) {
    // Not ready yet
  }
  
  // Read result
  uint32_t result = READ_CSR(SPARSITY_RESULT);
  
  // Continue with next operation
}
```

---

## Checklist: IP Integration Steps

- [ ] **Step 1:** Create package file (`tt_sparsity_pkg.sv`)
- [ ] **Step 2:** Create engine module (`tt_sparsity_engine.sv`)
- [ ] **Step 3:** Create register block (`tt_sparsity_registers.sv`)
- [ ] **Step 4:** Add register block to `tt_register_blocks.sv`
- [ ] **Step 5:** **Instantiate in `tt_tensix_with_l1.sv`** ← CRITICAL
- [ ] **Step 6:** Connect L1 memory interface
- [ ] **Step 7:** Connect CSR signals
- [ ] **Step 8:** Implement port arbitration (if needed)
- [ ] **Step 9:** Test firmware access
- [ ] **Step 10:** Verify timing closure

---

**Next:** Use this implementation guide to integrate Sparsity or TurboQuant into your RTL.


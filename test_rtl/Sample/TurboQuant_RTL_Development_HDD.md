# TurboQuant RTL Development HDD

**Document Type:** RTL Development & Implementation Guide  
**Date:** 2026-04-03  
**Status:** Ready for RTL Development  
**Target:** SystemVerilog RTL for Trinity/N1B0 NPU  
**Scope:** FWHT core, quantizer, packer modules + integration  

---

## Part 1: Module-by-Module RTL Specifications

### 1.1 Module: tt_fwht_transform

**Location in hierarchy:** `trinity_top → gen_tensix_neo[x][y] → tt_fwht_transform`

**Purpose:** Fast Walsh-Hadamard Transform using pipelined butterfly stages

#### Interface Definition

```systemverilog
module tt_fwht_transform #(
    parameter N = 128,              // Vector dimension (power-of-2)
    parameter LANES = 8,            // Parallel lanes per stage
    parameter LOGN = 7,             // log2(N)
    parameter DATA_W = 16,          // Input data width (FP16)
    parameter ROT_W = 23            // Output data width (IN_W + LOGN)
) (
    // Clock & Reset
    input logic clk,
    input logic rst_n,
    
    // Input Port
    input logic [N-1:0][DATA_W-1:0] i_vector,
    input logic [N-1:0] i_sign_mask,
    input logic i_valid,
    input logic i_ready,
    
    // Output Port
    output logic [N-1:0][ROT_W-1:0] o_vector,
    output logic o_valid,
    input logic o_ready,
    
    // Configuration (optional)
    input logic [7:0] cfg_n,        // Configurable N (for exploration)
    input logic cfg_use_sign_flip
);
```

**Signal Descriptions:**

| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| `i_vector` | [N-1:0][DATA_W-1:0] | in | Input vector (128 × 16-bit FP16) |
| `i_sign_mask` | [N-1:0] | in | Sign flip mask (1 bit per element) |
| `i_valid` | 1 | in | Input valid (handshake) |
| `i_ready` | 1 | out | Input ready (handshake) |
| `o_vector` | [N-1:0][ROT_W-1:0] | out | Output vector (128 × 23-bit signed) |
| `o_valid` | 1 | out | Output valid (handshake) |
| `o_ready` | 1 | in | Output ready (handshake) |

#### Internal Architecture

```systemverilog
// Stage 0: Input register
logic [N-1:0][DATA_W-1:0] stage_0_vector;
logic [N-1:0] stage_0_sign_mask;

// Stages 1..LOGN: FWHT butterfly stages
logic [LOGN-1:0][N-1:0][ROT_W-1:0] stage_vector;
logic [LOGN-1:0] stage_valid;

// Pipeline control
logic input_accepted;
logic pipeline_shift;
```

**Dataflow:**

```
i_vector [DATA_W]        (Stage 0)
    ↓ (register + sign-extend to ROT_W)
stage_0_vector [ROT_W]
    ↓ (apply sign flip from i_sign_mask)
    ↓ (Butterfly Stage 1: span=2^1=2)
stage_vector[0] [ROT_W]  (after 1 cycle)
    ↓
    ↓ (Butterfly Stage 2: span=2^2=4)
stage_vector[1] [ROT_W]  (after 2 cycles)
    ↓
    ... (5 more stages)
    ↓
stage_vector[6] [ROT_W]  (after 7 cycles)
    ↓ (register output)
o_vector [ROT_W]
```

#### RTL Implementation Detail

**Stage 0: Input Loading**

```systemverilog
always_ff @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
        stage_0_vector <= 0;
        stage_0_sign_mask <= 0;
    end else if (input_accepted) begin
        stage_0_vector <= i_vector;
        stage_0_sign_mask <= i_sign_mask;
    end
end

assign input_accepted = i_valid & i_ready;
assign i_ready = o_ready | ~pipeline_valid[0];  // Back-pressure
```

**Butterfly Stage `s` (s = 0..LOGN-1):**

```systemverilog
// Parameterized butterfly stage
for (genvar s = 0; s < LOGN; s++) begin : gen_stages
    localparam STEP = (1 << (s + 1));      // 2^(s+1)
    localparam HALF = (STEP >> 1);         // 2^s
    
    // Butterfly computation (combinational)
    for (genvar base = 0; base < N; base += STEP) begin : gen_bases
        for (genvar j = 0; j < HALF; j++) begin : gen_butterflies
            localparam int A_IDX = base + j;
            localparam int B_IDX = base + j + HALF;
            
            wire [ROT_W-1:0] a_in = (s == 0) ? 
                {{(ROT_W-DATA_W){i_vector[A_IDX][DATA_W-1]}}, i_vector[A_IDX]} :
                stage_vector[s-1][A_IDX];
            
            wire [ROT_W-1:0] b_in = (s == 0) ?
                {{(ROT_W-DATA_W){i_vector[B_IDX][DATA_W-1]}}, i_vector[B_IDX]} :
                stage_vector[s-1][B_IDX];
            
            // Apply sign flip (integrated into butterfly)
            wire [ROT_W-1:0] a_signed = (i_sign_mask[A_IDX]) ? -a_in : a_in;
            wire [ROT_W-1:0] b_signed = (i_sign_mask[B_IDX]) ? -b_in : b_in;
            
            // Butterfly: u = a + b, v = a - b
            assign stage_vector[s][A_IDX] = a_signed + b_signed;
            assign stage_vector[s][B_IDX] = a_signed - b_signed;
        end
    end
end
```

**Pipeline Registers (after each stage):**

```systemverilog
for (genvar s = 0; s < LOGN; s++) begin : gen_pipeline
    always_ff @(posedge clk or negedge rst_n) begin
        if (~rst_n) begin
            stage_vector_r[s] <= 0;
            stage_valid[s] <= 0;
        end else if (pipeline_shift) begin
            stage_vector_r[s] <= stage_vector[s];
            stage_valid[s] <= stage_valid[s-1];
        end
    end
end

// Output assignment
assign o_vector = stage_vector_r[LOGN-1];
assign o_valid = stage_valid[LOGN-1];
```

**Handshake Logic:**

```systemverilog
// Valid signal propagates through pipeline
always_ff @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
        pipeline_valid <= '0;
    end else if (pipeline_shift) begin
        pipeline_valid[0] <= input_accepted;
        for (int i = 1; i < LOGN; i++)
            pipeline_valid[i] <= pipeline_valid[i-1];
    end
end

// Back-pressure through pipeline
assign pipeline_shift = o_ready | ~pipeline_valid[LOGN-1];
```

#### Design Notes

- **Latency:** 7 cycles (one stage per clock cycle)
- **Throughput:** 1 vector/cycle (pipelined)
- **Bit growth:** Each stage adds up to 1 bit; total 7 bits over LOGN stages
- **Critical path:** Adder/subtractor in butterfly (max 23-bit addition)
- **Area:** ~40K gates (add/sub trees, registers, muxes)

---

### 1.2 Module: tt_scalar_quantizer

**Location in hierarchy:** `trinity_top → gen_tensix_neo[x][y] → tt_scalar_quantizer`

**Purpose:** Map normalized coordinates to low-bit quantization codes

#### Interface Definition

```systemverilog
module tt_scalar_quantizer #(
    parameter Q_W = 3,              // Quantization width (bits)
    parameter NUM_LEVELS = 8        // 2^Q_W
) (
    // Clock & Reset
    input logic clk,
    input logic rst_n,
    
    // Input Port
    input logic [23:0] i_z,         // Normalized scalar (24-bit signed)
    input logic i_valid,
    input logic i_ready,
    
    // Thresholds (pre-loaded from registers)
    input logic [6:0][31:0] i_thresholds,  // 7 × FP32
    
    // Output Port
    output logic [Q_W-1:0] o_q,
    output logic o_valid,
    input logic o_ready
);
```

**Signal Descriptions:**

| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| `i_z` | 24 | in | Normalized input (signed) |
| `i_valid` | 1 | in | Input valid |
| `i_ready` | 1 | out | Ready for input |
| `i_thresholds` | [6:0][31:0] | in | Threshold values (FP32) |
| `o_q` | Q_W | out | Quantized code (0–7 for 3-bit) |
| `o_valid` | 1 | out | Output valid |
| `o_ready` | 1 | in | Ready for output |

#### Implementation

**Option A: Cascade Comparator (Simple, 2-cycle latency)**

```systemverilog
// Stage 1: Comparisons (combinational)
logic cmp[0:6];
for (genvar i = 0; i < 7; i++) begin
    // Convert input to FP32 for comparison
    wire [31:0] i_z_ext = {
        {(32-24){i_z[23]}},  // Sign extension
        i_z[22:0]
    };
    
    // Floating-point comparison
    assign cmp[i] = (i_z_ext < i_thresholds[i]);
end

// Stage 2: Priority encoder (combinational)
logic [2:0] q_code;
always_comb begin
    if (cmp[0])      q_code = 3'b000;
    else if (cmp[1]) q_code = 3'b001;
    else if (cmp[2]) q_code = 3'b010;
    else if (cmp[3]) q_code = 3'b011;
    else if (cmp[4]) q_code = 3'b100;
    else if (cmp[5]) q_code = 3'b101;
    else if (cmp[6]) q_code = 3'b110;
    else             q_code = 3'b111;
end

assign o_q = q_code;

// Pipeline valid signal (2-cycle latency)
logic valid_r1, valid_r2;
always_ff @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
        valid_r1 <= 0;
        valid_r2 <= 0;
    end else begin
        valid_r1 <= i_valid;
        valid_r2 <= valid_r1;
    end
end

assign o_valid = valid_r2;
```

**Option B: Pipelined Comparator Tree (Better timing, 3-cycle latency)**

```systemverilog
logic [2:0] cmp_lower, cmp_upper;

// Stage 1: Lower comparisons (register)
always_ff @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
        cmp_lower <= 0;
    end else begin
        cmp_lower[0] <= (i_z_ext < i_thresholds[0]);
        cmp_lower[1] <= (i_z_ext < i_thresholds[1]);
        cmp_lower[2] <= (i_z_ext < i_thresholds[2]);
    end
end

// Stage 2: Upper comparisons (register)
always_ff @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
        cmp_upper <= 0;
    end else begin
        cmp_upper[0] <= (i_z_ext < i_thresholds[3]);
        cmp_upper[1] <= (i_z_ext < i_thresholds[4]);
        cmp_upper[2] <= (i_z_ext < i_thresholds[5]);
        cmp_upper[3] <= (i_z_ext < i_thresholds[6]);
    end
end

// Stage 3: Final mux tree (combinational)
always_comb begin
    if (cmp_lower[0])      q_code = 3'b000;
    else if (cmp_lower[1]) q_code = 3'b001;
    else if (cmp_lower[2]) q_code = 3'b010;
    else if (cmp_upper[0]) q_code = 3'b011;
    else if (cmp_upper[1]) q_code = 3'b100;
    else if (cmp_upper[2]) q_code = 3'b101;
    else if (cmp_upper[3]) q_code = 3'b110;
    else                   q_code = 3'b111;
end

// 3-stage pipeline total
```

#### Design Notes

- **Option A:** 2-cycle latency, simpler logic, ~5K gates
- **Option B:** 3-cycle latency, better timing, still ~5K gates
- **Threshold precision:** FP32 input vs FP16/fixed-point data (conversion in pipeline)
- **Alternative:** Pre-convert thresholds to fixed-point to eliminate FP32 comparison overhead

---

### 1.3 Module: tt_output_packer

**Location in hierarchy:** `trinity_top → gen_tensix_neo[x][y] → tt_output_packer`

**Purpose:** Pack 3-bit quantization codes into byte-aligned output

#### Interface Definition

```systemverilog
module tt_output_packer #(
    parameter N = 128,              // Vector dimension
    parameter Q_W = 3               // Quantization width
) (
    // Clock & Reset
    input logic clk,
    input logic rst_n,
    
    // Input: Array of Q_W-bit codes
    input logic [N-1:0][Q_W-1:0] i_q,
    input logic i_valid,
    
    // Output: Byte-aligned packed array
    localparam int PACKED_BYTES = ((N*Q_W + 7) / 8);
    output logic [PACKED_BYTES-1:0][7:0] o_packed,
    output logic o_valid
);
```

#### Implementation

```systemverilog
// Combinational packing logic
logic [PACKED_BYTES-1:0][7:0] packed_comb;

always_comb begin
    packed_comb = 0;
    int bit_idx = 0;
    int byte_idx = 0;
    
    for (int i = 0; i < N; i++) begin
        if (bit_idx + Q_W <= 8) begin
            // Fits in current byte
            packed_comb[byte_idx] |= (i_q[i] << bit_idx);
            bit_idx += Q_W;
        end else begin
            // Spans two bytes
            int remaining = 8 - bit_idx;
            packed_comb[byte_idx] |= (i_q[i][remaining-1:0] << bit_idx);
            byte_idx++;
            packed_comb[byte_idx] |= (i_q[i][Q_W-1:remaining]);
            bit_idx = Q_W - remaining;
        end
    end
end

// Register output
always_ff @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
        o_packed <= 0;
        o_valid <= 0;
    end else begin
        o_packed <= packed_comb;
        o_valid <= i_valid;
    end
end
```

**Output format:** 128 × 3 bits = 384 bits = 48 bytes

#### Design Notes

- **Latency:** 1 cycle (register)
- **Area:** ~1K gates (packing logic is minimal)
- **Output alignment:** Byte-boundary aligned (no padding needed)

---

## Part 2: Integration & Top-Level Connectivity

### 2.1 Instantiation in Trinity (trinity.sv)

```systemverilog
// In trinity_top module, within tile generation loops

for (genvar x = 0; x < 4; x++) begin : gen_x
    for (genvar y = 0; y < 3; y++) begin : gen_y
        
        // Existing Tensix tile
        tt_tensix_neo #(.X(x), .Y(y)) tensix_tile (
            .clk(i_ai_clk[x]),
            .rst(i_ai_rst),
            // ... (existing ports)
        );
        
        // NEW: TurboQuant FWHT core
        tt_fwht_transform #(
            .N(128),
            .LANES(8),
            .LOGN(7),
            .DATA_W(16),
            .ROT_W(23)
        ) fwht_core (
            .clk(i_ai_clk[x]),
            .rst_n(~i_ai_rst),
            .i_vector(l1_read_vector[x][y]),
            .i_sign_mask(sign_mask_reg[x][y]),
            .i_valid(fwht_enable[x][y]),
            .i_ready(fwht_ready[x][y]),
            .o_vector(fwht_result[x][y]),
            .o_valid(fwht_valid[x][y]),
            .o_ready(quantizer_ready[x][y])
        );
        
        // NEW: Scalar quantizer
        tt_scalar_quantizer #(.Q_W(3)) quantizer (
            .clk(i_ai_clk[x]),
            .rst_n(~i_ai_rst),
            .i_z(fwht_result[x][y]),
            .i_valid(fwht_valid[x][y]),
            .i_ready(quantizer_ready[x][y]),
            .i_thresholds(quantizer_thresholds),
            .o_q(q_output[x][y]),
            .o_valid(q_valid[x][y]),
            .o_ready(packer_ready[x][y])
        );
        
        // NEW: Output packer
        tt_output_packer #(.N(128), .Q_W(3)) packer (
            .clk(i_ai_clk[x]),
            .rst_n(~i_ai_rst),
            .i_q(q_output[x][y]),
            .i_valid(q_valid[x][y]),
            .o_packed(packed_output[x][y]),
            .o_valid(packed_valid[x][y])
        );
    end
end
```

### 2.2 Port Assignments (Top-Level)

```systemverilog
// Inputs from Dispatch / Registers
logic [127:0] sign_mask_reg[0:3][0:2];
logic [6:0][31:0] quantizer_thresholds;
logic [0:3][0:2] fwht_enable;

// Outputs to NIU/Packer
logic [47:0][7:0] packed_output[0:3][0:2];
logic [0:3][0:2] packed_valid;

// Dataflow wires
logic [127:0][22:0] fwht_result[0:3][0:2];
logic [127:0][2:0] q_output[0:3][0:2];

// Handshake signals
logic [0:3][0:2] fwht_valid, fwht_ready;
logic [0:3][0:2] quantizer_ready;
logic [0:3][0:2] packer_ready;
logic [0:3][0:2] q_valid;
```

---

## Part 3: Register Map & CSR Programming

### 3.1 Register Definitions

**Base address:** `0x6000`

```c
#define TURBOQUANT_BASE         0x6000

// Configuration registers
#define REG_FWHT_CFG            (TURBOQUANT_BASE + 0x00)
#define REG_QUANTIZER_CFG       (TURBOQUANT_BASE + 0x04)
#define REG_QUANTIZER_THRESH0   (TURBOQUANT_BASE + 0x08)
#define REG_QUANTIZER_THRESH1   (TURBOQUANT_BASE + 0x0C)
#define REG_QUANTIZER_THRESH2   (TURBOQUANT_BASE + 0x10)
#define REG_QUANTIZER_THRESH3   (TURBOQUANT_BASE + 0x14)
#define REG_QUANTIZER_THRESH4   (TURBOQUANT_BASE + 0x18)
#define REG_QUANTIZER_THRESH5   (TURBOQUANT_BASE + 0x1C)
#define REG_QUANTIZER_THRESH6   (TURBOQUANT_BASE + 0x20)
#define REG_NORMALIZE_SCALE     (TURBOQUANT_BASE + 0x24)
#define REG_TURBOQUANT_CTRL     (TURBOQUANT_BASE + 0x28)
#define REG_TURBOQUANT_STATUS   (TURBOQUANT_BASE + 0x2C)

// Sign mask registers (per-tile)
#define REG_SIGN_MASK_BASE      (TURBOQUANT_BASE + 0x30)
#define REG_SIGN_MASK(x,y)      (REG_SIGN_MASK_BASE + ((x)*3+(y))*4)
```

### 3.2 Register Bit Definitions

**REG_FWHT_CFG (0x6000):**
```
Bits [7:0]:    N (vector dimension, default 128)
Bits [15:8]:   LANES (parallel lanes, default 8)
Bit 16:        USE_SIGN_FLIP (default 1)
Bit 17:        USE_PERMUTE (default 0)
Bits [31:18]:  Reserved
```

**REG_QUANTIZER_CFG (0x6004):**
```
Bits [3:0]:    Q_W (quantization bits, default 3)
Bit 4:         TYPE (0=threshold, 1=uniform, default 0)
Bits [12:8]:   NUM_LEVELS (default 8)
Bits [31:13]:  Reserved
```

**REG_TURBOQUANT_CTRL (0x6028):**
```
Bit 0:         START (write 1 to begin, auto-clears)
Bit 1:         ENABLE_SIGN_FLIP (default 1)
Bit 2:         ENABLE_PERMUTE (default 0)
Bits [31:3]:   Reserved
```

**REG_TURBOQUANT_STATUS (0x602C):**
```
Bit 0:         BUSY (1 = currently processing)
Bit 1:         DONE (1 = last vector completed)
Bit 2:         ERROR (1 = overflow/error detected)
Bits [31:3]:   Reserved
```

---

## Part 4: Testbench Structure

### 4.1 Top-Level Testbench

**File:** `tb_turboquant_top.sv`

```systemverilog
`timescale 1ns/1ps

module tb_turboquant_top;

localparam int N = 128;
localparam int NUM_VECTORS = 1000;
localparam int CLK_PERIOD = 10;

logic clk, rst_n;
logic [127:0][15:0] test_vector[NUM_VECTORS];
logic [127:0][22:0] golden_fwht[NUM_VECTORS];
logic [127:0][2:0] golden_q[NUM_VECTORS];

logic [127:0][15:0] in_vector;
logic [127:0] sign_mask;
logic in_valid;
logic [127:0][22:0] fwht_out;
logic fwht_valid;

// Clock generation
initial begin
    clk = 0;
    forever #(CLK_PERIOD/2) clk = ~clk;
end

// Reset sequence
initial begin
    rst_n = 0;
    #(CLK_PERIOD * 5);
    rst_n = 1;
end

// DUT instantiation
tt_fwht_transform #(.N(128)) dut (
    .clk(clk),
    .rst_n(rst_n),
    .i_vector(in_vector),
    .i_sign_mask(sign_mask),
    .i_valid(in_valid),
    .i_ready(),
    .o_vector(fwht_out),
    .o_valid(fwht_valid),
    .o_ready(1'b1)
);

// Test stimulus
initial begin
    $readmemh("test_vectors.hex", test_vector);
    $readmemh("golden_fwht.hex", golden_fwht);
    
    in_valid = 0;
    sign_mask = 128'h0;
    
    wait(rst_n);
    @(posedge clk);
    
    for (int i = 0; i < NUM_VECTORS; i++) begin
        in_vector = test_vector[i];
        in_valid = 1;
        @(posedge clk);
        
        repeat(12) @(posedge clk);
        
        if (fwht_out == golden_fwht[i]) begin
            $display("[PASS] Vector %3d", i);
        end else begin
            $display("[FAIL] Vector %3d", i);
            $display("  Expected: %h", golden_fwht[i][0]);
            $display("  Got:      %h", fwht_out[0]);
        end
    end
    
    $display("Test completed!");
    $finish;
end

endmodule
```

### 4.2 Standalone FWHT Testbench

**File:** `tb_fwht_standalone.sv`

```systemverilog
module tb_fwht_standalone;

logic clk, rst_n;
logic [127:0][15:0] in_vec;
logic [127:0][22:0] out_vec;

tt_fwht_transform dut (.*);

initial begin
    clk = 0;
    forever #5ns clk = ~clk;
end

initial begin
    rst_n = 0;
    #100ns;
    rst_n = 1;
    
    // Test 1: All zeros
    in_vec = 0;
    @(posedge clk);
    #10us;
    
    // Test 2: Unit impulse
    in_vec = 0;
    in_vec[0] = 16'h3C00;  // FP16 = 1.0
    @(posedge clk);
    #10us;
    
    $finish;
end

endmodule
```

---

## Part 5: Compilation & Build

### 5.1 Vivado Project Setup

**RTL files:**

```
rtl/
├── tt_fwht_transform.sv       (~400 lines)
├── tt_scalar_quantizer.sv     (~200 lines)
├── tt_output_packer.sv        (~150 lines)
└── Makefile
```

**Synthesis script (vivado_build.tcl):**

```tcl
create_project turboquant_rtl . -force
add_files {rtl/tt_fwht_transform.sv \
           rtl/tt_scalar_quantizer.sv \
           rtl/tt_output_packer.sv}
add_files -fileset sim_1 tb_turboquant_top.sv
set_property part xczu7cg-fbvb900-1-e [current_project]
launch_runs synth_1
wait_on_run synth_1
launch_runs impl_1
wait_on_run impl_1
launch_runs impl_1 -to_step write_bitstream
wait_on_run impl_1
puts "Build complete!"
```

### 5.2 Simulation Commands

**Compile:**
```bash
xvlog -sv rtl/*.sv
xvlog -sv tb_turboquant_top.sv
xelab tb_turboquant_top -s tb_turboquant_top_sim
```

**Run:**
```bash
xsim tb_turboquant_top_sim -gui
```

**Batch mode:**
```bash
xsim tb_turboquant_top_sim -runall -log sim.log
```

---

## Part 6: Implementation Checklist

### RTL Design Phase

**FWHT Core:**
- [ ] Create tt_fwht_transform.sv module skeleton
- [ ] Implement Stage 0 input loading
- [ ] Implement butterfly logic (genvar loops)
- [ ] Implement pipeline stages
- [ ] Implement handshake logic
- [ ] Add comments & documentation
- [ ] Run lint (Verilator or Xcelium)

**Quantizer:**
- [ ] Create tt_scalar_quantizer.sv
- [ ] Implement comparator cascade (Option A)
- [ ] Implement pipelined comparators (Option B)
- [ ] Implement priority encoder
- [ ] Test with various threshold values
- [ ] Lint & review

**Packer:**
- [ ] Create tt_output_packer.sv
- [ ] Implement bit-packing logic
- [ ] Verify output byte alignment
- [ ] Add optional metadata support
- [ ] Lint & review

**Integration:**
- [ ] Create tt_turboquant_wrapper.sv (optional)
- [ ] Document all interfaces
- [ ] Create port diagrams

### Verification Phase

**Unit Testing:**
- [ ] Create tb_fwht_standalone.sv
  - [ ] Test with scipy.linalg.hadamard() golden model
  - [ ] Test boundary values (FP16 max/min)
  - [ ] Test sign mask variations
  
- [ ] Create tb_quantizer_standalone.sv
  - [ ] Test threshold boundary crossing
  - [ ] Test all 8 quantization levels
  
- [ ] Create tb_packer_standalone.sv
  - [ ] Verify bit alignment
  - [ ] Test random 3-bit codes

**Integration Testing:**
- [ ] Create tb_turboquant_top.sv
  - [ ] Full pipeline simulation
  - [ ] 1000+ random vectors
  - [ ] Handshake protocol testing
  - [ ] Back-pressure scenarios

**Coverage:**
- [ ] RTL code coverage: >90%
- [ ] Statement coverage: >95%
- [ ] Branch coverage: >90%

### Synthesis & Timing Phase

**Synthesis:**
- [ ] Add to Trinity trinity.sv
- [ ] Run synthesis (target 1 GHz)
- [ ] Check for inferred latches (none expected)
- [ ] Verify module instantiation
- [ ] Report gate count (~50K expected)

**Timing:**
- [ ] Run timing analysis
- [ ] Identify critical paths
- [ ] Add pipeline stages if needed
- [ ] Verify setup/hold margins >10%
- [ ] Generate timing report

**Area & Power:**
- [ ] Post-synthesis area estimation
- [ ] Power estimation (switching activity)
- [ ] Compare vs dense GEMM baseline
- [ ] Document trade-offs

### Integration Phase

**RTL Integration:**
- [ ] Integrate into trinity_top.sv
- [ ] Connect to Dispatch CSR interface
- [ ] Connect to L1 memory interface
- [ ] Connect to Packer output
- [ ] Verify port connections

**System Simulation:**
- [ ] RTL + firmware co-simulation
- [ ] Full pipeline end-to-end
- [ ] Compare output vs Python golden model

**Documentation:**
- [ ] Complete RTL datasheet
- [ ] Register map documentation
- [ ] Timing/area summary
- [ ] Known issues & limitations

---

## Part 7: Design Review Checkpoints

**Architecture Review (after RTL design):**
- [ ] Code review: gate-level logic correctness
- [ ] Peer review: interface definitions
- [ ] Architecture review: pipelineability, back-pressure

**Synthesis Review (after synthesis):**
- [ ] Timing closure: all paths meet 1 GHz
- [ ] Area report: within ~50K gate budget
- [ ] Power estimation: <10 mW per tile

**Integration Review (final):**
- [ ] RTL audit complete
- [ ] Documentation complete
- [ ] Test coverage approved

---

## Part 8: Verification Metrics

| Metric | Target | Status |
|--------|--------|--------|
| RTL code review | 100% | — |
| Lint violations | 0 | — |
| Code coverage | >90% | — |
| Functional test pass rate | 100% | — |
| Timing closure @ 1 GHz | Yes | — |
| Gate count | ~50K | — |
| Power (mW) | <10 | — |

---

## Part 9: Repository Structure

```
turboquant_rtl/
├── rtl/
│   ├── tt_fwht_transform.sv
│   ├── tt_scalar_quantizer.sv
│   ├── tt_output_packer.sv
│   └── Makefile
├── tb/
│   ├── tb_fwht_standalone.sv
│   ├── tb_quantizer_standalone.sv
│   ├── tb_packer_standalone.sv
│   ├── tb_turboquant_top.sv
│   └── sim_run.sh
├── testdata/
│   ├── test_vectors.hex
│   ├── golden_fwht.hex
│   ├── golden_q.hex
│   └── gen_testdata.py
├── docs/
│   ├── register_map.md
│   ├── timing_analysis.rpt
│   └── power_analysis.rpt
└── README.md
```

---

## Part 10: Known Issues & Limitations

| Issue | Impact | Workaround |
|-------|--------|-----------|
| FP16 ↔ FP32 comparison in quantizer | Latency +1 cy | Preconvert thresholds to FP16 |
| Permutation disabled (USE_PERMUTE=0) | Quality -0.05% estimated | Enable if quality validation shows gap |
| No dynamic threshold update | Batch-dependent quality | Compute thresholds offline per batch |
| Sign mask fixed per batch | Limited randomization | Use LFSR-generated patterns |
| L1 prefetch latency (4 cy) | Total latency ~16 cy | Overlap with previous vector write |

---

## Appendix A: Quick Reference

**Key Module Parameters:**
```
N = 128 (vector dimension)
LANES = 8 (parallel lanes)
LOGN = 7 (pipeline stages)
DATA_W = 16 (input FP16)
ROT_W = 23 (output width)
Q_W = 3 (quantization bits)
```

**Key Latencies:**
```
FWHT: 7 cycles
Quantizer: 2–3 cycles
Packer: 1 cycle
Total: 10–11 cycles (pipelined)
```

**Key Signals:**
```
fwht_result[x][y]: [127:0][22:0]  // FWHT output (23-bit)
q_output[x][y]: [127:0][2:0]      // Quantized (3-bit)
packed_output[x][y]: [47:0][7:0]  // Packed output (48 bytes)
```

**Key CSRs:**
```
REG_FWHT_CFG = 0x6000
REG_QUANTIZER_CFG = 0x6004
REG_QUANTIZER_THRESH[0..6] = 0x6008–0x6020
REG_TURBOQUANT_CTRL = 0x6028
REG_TURBOQUANT_STATUS = 0x602C
```

---

**End of RTL Development HDD**


// ═════════════════════════════════════════════════════════════════════════════
// Step 2.4.2 RTL Implementation Code
// File: tt_tensix_with_l1.sv
// Location: Inside generate block, after tt_tensix instantiation
// ═════════════════════════════════════════════════════════════════════════════

// ─────────────────────────────────────────────────────────────────────────────
// PART 1: Signal Declarations at Cluster Level (BEFORE generate block)
// Location: tt_tensix_with_l1.sv, lines ~1100-1120 (before generate statement)
// ─────────────────────────────────────────────────────────────────────────────

// Add these declarations at cluster level (outside/before generate block):

// CSR signals from register block (Step 2.4.1 outputs)
logic [NUM_TENSIX_NEO-1:0]                sparsity_ctrl_t   sparsity_ctrl;
logic [NUM_TENSIX_NEO-1:0]                sparsity_zmask_t  sparsity_zmask;
logic [NUM_TENSIX_NEO-1:0]                sparsity_config_t sparsity_config;
logic [NUM_TENSIX_NEO-1:0]                sparsity_status_t sparsity_status;
logic [NUM_TENSIX_NEO-1:0][31:0]          sparsity_result_data;

// TurboQuant CSR signals
logic [NUM_TENSIX_NEO-1:0]                turboquant_ctrl_t   turboquant_ctrl;
logic [NUM_TENSIX_NEO-1:0]                turboquant_config_t turboquant_config;
logic [NUM_TENSIX_NEO-1:0]                turboquant_status_t turboquant_status;
logic [NUM_TENSIX_NEO-1:0][31:0]          turboquant_result_data;
logic [NUM_TENSIX_NEO-1:0][31:0]          turboquant_scale_output;  // TurboQuant scale factor

// Sparsity Engine L1 interface
logic [NUM_TENSIX_NEO-1:0][15:0]          l1_sparsity_addr;
logic [NUM_TENSIX_NEO-1:0]                l1_sparsity_rd_valid;
logic [NUM_TENSIX_NEO-1:0][127:0]         sparsity_output_data;
logic [NUM_TENSIX_NEO-1:0]                sparsity_output_valid;

// TurboQuant Engine L1 interface
logic [NUM_TENSIX_NEO-1:0][15:0]          l1_turboquant_addr;
logic [NUM_TENSIX_NEO-1:0]                l1_turboquant_rd_valid;
logic [NUM_TENSIX_NEO-1:0][127:0]         turboquant_output_data;
logic [NUM_TENSIX_NEO-1:0]                turboquant_output_valid;

// Compressed data tracking (optional, for monitoring)
logic [NUM_TENSIX_NEO-1:0][31:0]          l1_occupancy_percent;
logic [NUM_TENSIX_NEO-1:0][7:0]           compression_ratio;


// ─────────────────────────────────────────────────────────────────────────────
// PART 2: Sparsity24 Decode Engine Instantiation (for i==0 block)
// Location: tt_tensix_with_l1.sv, lines ~1234 (AFTER tt_tensix u_t6 closes)
// ─────────────────────────────────────────────────────────────────────────────

// INSERT THIS CODE AFTER LINE 1233 (after tt_tensix instantiation for i==0):

      // ═════════════════════════════════════════════════════════════════════
      // NEW: Sparsity24 Decode Engine Instantiation (Step 2.4.2)
      // ═════════════════════════════════════════════════════════════════════

      tt_sparsity_engine #(
        .DATA_WIDTH(128),
        .NUM_STREAMS(4),
        .VECTOR_WIDTH(256)
      ) u_sparsity_engine_0 (

        // ─────────────────────────────────────────────────────────────────
        // Clock & Reset
        // ─────────────────────────────────────────────────────────────────
        .i_clk(i_ai_clk[i]),                // ai_clk (T6 L1 access, same as TRISC)
        .i_rst_n(i_rst_n),

        // ─────────────────────────────────────────────────────────────────
        // CSR Interface (from register block outputs at cluster level)
        // ─────────────────────────────────────────────────────────────────
        .i_ctrl(sparsity_ctrl[i]),          // CSR control from register block
        .i_zmask(sparsity_zmask[i]),        // Zero-mask for z-plane skipping
        .i_config(sparsity_config[i]),      // Configuration register
        .o_status(sparsity_status[i]),      // Status feedback to register block
        .o_result_data(sparsity_result_data[i]),  // Result data for firmware

        // ─────────────────────────────────────────────────────────────────
        // L1 Memory Read Interface (128-bit)
        // ─────────────────────────────────────────────────────────────────
        .i_l1_data(l1_rd_data[i]),          // Data from L1 SRAM
        .o_l1_addr(l1_sparsity_addr[i]),    // Address request to L1
        .o_l1_rd_valid(l1_sparsity_rd_valid[i]),  // Read strobe

        // ─────────────────────────────────────────────────────────────────
        // Output Data Path
        // ─────────────────────────────────────────────────────────────────
        .o_output_data(sparsity_output_data[i]),
        .o_output_valid(sparsity_output_valid[i])
      );

      // ═════════════════════════════════════════════════════════════════════
      // NEW: TurboQuant Decode Engine Instantiation (Step 2.4.2)
      // ═════════════════════════════════════════════════════════════════════

      tt_turboquant_decode_engine #(
        .DATA_WIDTH(128),
        .VECTOR_WIDTH(256),
        .OUTPUT_WIDTH(64)  // Compressed output width
      ) u_turboquant_engine_0 (

        // ─────────────────────────────────────────────────────────────────
        // Clock & Reset
        // ─────────────────────────────────────────────────────────────────
        .i_clk(i_ai_clk[i]),                // ai_clk (T6 L1 access, same as TRISC)
        .i_rst_n(i_rst_n),

        // ─────────────────────────────────────────────────────────────────
        // CSR Interface
        // ─────────────────────────────────────────────────────────────────
        .i_ctrl(turboquant_ctrl[i]),
        .i_config(turboquant_config[i]),
        .o_status(turboquant_status[i]),
        .o_result_data(turboquant_result_data[i]),
        .o_scale_output(turboquant_scale_output[i]),  // Scale factor output

        // ─────────────────────────────────────────────────────────────────
        // L1 Memory Interface
        // ─────────────────────────────────────────────────────────────────
        .i_l1_data(l1_rd_data[i]),
        .o_l1_addr(l1_turboquant_addr[i]),
        .o_l1_rd_valid(l1_turboquant_rd_valid[i]),

        // ─────────────────────────────────────────────────────────────────
        // Output (Compressed Data)
        // ─────────────────────────────────────────────────────────────────
        .o_output_data(turboquant_output_data[i]),    // 48-byte compressed
        .o_output_valid(turboquant_output_valid[i])
      );

      // ═════════════════════════════════════════════════════════════════════
      // PORT ARBITRATION: Mux L1 read port for multiple masters
      // ═════════════════════════════════════════════════════════════════════

      logic [15:0]  l1_rd_addr_final;
      logic         l1_rd_valid_final;

      always_comb begin
        // Priority: Sparsity > TurboQuant > TRISC

        if (sparsity_output_valid[i]) begin
          // Sparsity engine has priority
          l1_rd_addr_final = l1_sparsity_addr[i];
          l1_rd_valid_final = l1_sparsity_rd_valid[i];
        end else if (turboquant_output_valid[i]) begin
          // TurboQuant next priority
          l1_rd_addr_final = l1_turboquant_addr[i];
          l1_rd_valid_final = l1_turboquant_rd_valid[i];
        end else begin
          // Default: TRISC has L1 access
          l1_rd_addr_final = trisc_l1_rd_addr[i];
          l1_rd_valid_final = trisc_l1_rd_valid[i];
        end
      end

      // ═════════════════════════════════════════════════════════════════════
      // Assign final arbitrated signals to L1 read port
      // ═════════════════════════════════════════════════════════════════════
      assign l1_rd_addr[i] = l1_rd_addr_final;
      assign l1_rd_valid[i] = l1_rd_valid_final;


// ─────────────────────────────────────────────────────────────────────────────
// PART 3: Repeat for else block (i >= 1)
// Location: tt_tensix_with_l1.sv, lines ~1354 (AFTER tt_tensix u_t6 for else)
// ─────────────────────────────────────────────────────────────────────────────

// INSERT SAME CODE (with [i] indexing) AFTER LINE 1353 (after tt_tensix for else block):
// [Code is identical to PART 2, just repeated for the else block]


// ─────────────────────────────────────────────────────────────────────────────
// PART 4: Connect CSR Outputs from Register Block
// Location: tt_tensix_with_l1.sv (in tt_register_blocks instantiation)
// ─────────────────────────────────────────────────────────────────────────────

// Add these port connections to tt_register_blocks instantiation:

tt_register_blocks u_register_blocks (
  .i_cfg_clk(i_ai_clk),
  .i_cfg_reset_n(i_rst_n),

  // ... existing signals ...

  // ═════════════════════════════════════════════════════════════════════
  // Step 2.4.1 Sparsity Register Block Outputs (connect to cluster signals)
  // ═════════════════════════════════════════════════════════════════════
  .o_sparsity_ctrl(sparsity_ctrl),          // Output to cluster
  .o_sparsity_zmask(sparsity_zmask),
  .o_sparsity_config(sparsity_config),
  .i_sparsity_status(sparsity_status),      // Input from cluster
  .i_sparsity_result_data(sparsity_result_data),

  // ═════════════════════════════════════════════════════════════════════
  // Step 2.4.1 TurboQuant Register Block Outputs
  // ═════════════════════════════════════════════════════════════════════
  .o_turboquant_ctrl(turboquant_ctrl),
  .o_turboquant_config(turboquant_config),
  .i_turboquant_status(turboquant_status),
  .i_turboquant_result_data(turboquant_result_data),
  .i_turboquant_scale_output(turboquant_scale_output),

  // ... other register block signals ...
);


// ═════════════════════════════════════════════════════════════════════════════
// KEY IMPLEMENTATION NOTES
// ═════════════════════════════════════════════════════════════════════════════

// 1. CLOCK DOMAIN
//    - tt_tensix uses i_ai_clk (application clock)
//    - Sparsity/TurboQuant use i_dm_clk (data memory clock) for L1 access
//    - CSR signals originate in i_ai_clk domain but are stable (no CDC needed)
//
// 2. SIGNAL INDEXING
//    - All cluster-level signals use [i] index for per-tile arrays
//    - This enables multi-tile support (i = 0 to NUM_TENSIX_NEO-1)
//
// 3. L1 PORT ARBITRATION
//    - if/else-if/else priority: Sparsity > TurboQuant > TRISC
//    - Prevents simultaneous L1 address assignments
//    - Combinational mux (no latency added)
//
// 4. REGISTER BLOCK CONNECTION
//    - CSR signals declared at cluster level
//    - Connected from register block outputs (Step 2.4.1)
//    - Firmware writes CSR via TRISC, reads results via status register
//
// 5. L1 DATA SOURCE
//    - l1_rd_data[i] is existing signal in tt_tensix_with_l1.sv
//    - Already used by TRISC for L1 read access
//    - Arbitration ensures only one master reads per cycle
//
// 6. METADATA PERSISTENCE (TurboQuant)
//    - Scale factor (32 bits) output on o_scale_output port
//    - Firmware must save to L1 immediately after compressed data
//    - Format: 48 bytes compressed + 4 bytes scale = 52 bytes/vector
//
// 7. ZERO-PLANE MASK (Sparsity)
//    - i_zmask: 32-bit mask for L1 planes
//    - Firmware sets bits for planes to skip during load
//    - Reduces L1 bandwidth (no DRAM impact)
//
// ═════════════════════════════════════════════════════════════════════════════

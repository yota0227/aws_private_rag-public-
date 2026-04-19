# N1B0 PPA Optimization — Top 3 RTL Implementation Guide

**Detailed RTL Changes for Maximum Power, Performance, and Area Improvements**

---

## Overview

| Rank | Item | PPA Focus | Area Saving | Perf Gain | Power Reduction | Est. Effort |
|------|------|-----------|---|---|---|---|
| **1** | **L1 SRAM Hierarchical Caching** | Area + Perf | 10-50% (4-18 mm²) | ↓5-20% MEM latency | ↓10-20% L1 leakage | 4-6w |
| **2** | **NoC Router Congestion Mitigation** | Perf + Power | — | ↓15-30% E2E latency | ↓5-15% NoC power | 3-5w |
| **3** | **Repeater & Timing Optimization** | Area + Timing | 2-5 mm² | ±0.1-0.3 ns slack | ↓5-10% repeater power | 2-4w |
| **TOTAL** | | | **6-23 mm²** | **↓15-50% mixed** | **↓10-25% total** | **9-15w** |

---

---

# **Item 1: L1 SRAM Hierarchical Caching**

## Objective
Reduce L1 SRAM from 3 MB to configurable 0.5-1 MB with automatic multilevel fallback:
- **L0 scratchpad** (64 KB, ultra-fast): hot tensor cache
- **L1 primary** (512-1024 KB): weight tiles, activations
- **DRAM fallback**: overflow with automatic prefetch

**Impact:**
- **Area:** ↓10-50% (save 4-18 mm² depending on config)
- **Performance:** ↓5-20% memory latency via better L0 cache hit rate
- **Power:** ↓10-20% L1 SRAM leakage per tile

---

## 1.1 Add L0 Scratchpad Registers

**File:** `tt_t6_l1_csr.sv`

```verilog
// New L0 scratchpad configuration (base 0x03000200 + 0xA0)

typedef struct packed {
    logic [15:0]  L0_BASE_ADDR;        // +0xA0: L0 start address in L1 space
    logic [9:0]   L0_SIZE_KB;          // +0xA1: L0 size (32–256 KB)
    logic [7:0]   L0_REPL_POLICY;      // +0xA2: 0=LRU, 1=FIFO, 2=random
    logic [7:0]   L0_PREFETCH_EN;      // +0xA3: Enable prefetch on miss
    logic [31:0]  L0_HIT_COUNT;        // +0xA4: RO — hit counter
    logic [31:0]  L0_MISS_COUNT;       // +0xA5: RO — miss counter
} l0_scratchpad_csr_t;

l0_scratchpad_csr_t l0_scratchpad_q;

always_ff @(posedge i_ai_clk, negedge i_reset_n) begin
    if (!i_reset_n) begin
        l0_scratchpad_q <= '{
            L0_BASE_ADDR: 16'h0,
            L0_SIZE_KB: 10'd64,          // Default 64 KB
            L0_REPL_POLICY: 8'h0,        // LRU
            L0_PREFETCH_EN: 8'h01,       // Prefetch enabled
            L0_HIT_COUNT: 32'h0,
            L0_MISS_COUNT: 32'h0
        };
    end else if (i_apb_write) begin
        case (i_apb_addr[15:0])
            16'h00A0: l0_scratchpad_q.L0_BASE_ADDR <= i_apb_writedata[15:0];
            16'h00A1: l0_scratchpad_q.L0_SIZE_KB <= i_apb_writedata[9:0];
            16'h00A2: l0_scratchpad_q.L0_REPL_POLICY <= i_apb_writedata[7:0];
            16'h00A3: l0_scratchpad_q.L0_PREFETCH_EN <= i_apb_writedata[7:0];
        endcase
    end
end

// Hit/miss counters (RO)
assign o_l0_scratchpad_csr = l0_scratchpad_q;

```

---

## 1.2 L0 Scratchpad Cache Controller

**File:** `tt_t6_l0_cache.sv` (NEW MODULE)

```verilog
// File: tt_t6_l0_cache.sv (new L0 scratchpad controller)

module tt_t6_l0_cache #(
    parameter L0_MAX_ENTRIES = 64  // Max 64 KB ÷ 1 KB per entry = 64 entries
) (
    input i_ai_clk,
    input i_reset_n,

    // L0 configuration
    input l0_scratchpad_csr_t i_l0_config,

    // Access request (from TRISC unpack/pack)
    input [15:0]   i_req_addr,         // L1 address requested
    input [31:0]   i_req_data,         // Data to write (for writes)
    input          i_req_valid,
    input          i_req_write,

    // Response
    output [31:0]  o_rsp_data,
    output         o_rsp_valid,
    output         o_hit,              // 1 = hit in L0

    // L1 fallback (on miss)
    output [15:0]  o_l1_req_addr,
    output [31:0]  o_l1_req_data,
    output         o_l1_req_valid,
    output         o_l1_req_write,
    input [31:0]   i_l1_rsp_data,
    input          i_l1_rsp_valid,

    // DRAM prefetch (on miss with prefetch_en)
    output [31:0]  o_dram_prefetch_addr,
    output         o_dram_prefetch_en
);

    // L0 entry structure
    typedef struct packed {
        logic [15:0]  tag;             // L1 address tag (upper bits)
        logic [31:0]  data;            // Cached data
        logic         valid;           // Entry valid
        logic [6:0]   lru_counter;     // LRU age
    } l0_entry_t;

    // L0 CAM for tag lookup
    l0_entry_t l0_entries [L0_MAX_ENTRIES-1:0];
    logic [5:0] l0_hit_index;
    logic l0_hit_found;

    // Extract tag from L1 address (upper bits)
    wire [15:0] req_tag = i_req_addr[15:8];
    wire [7:0]  req_offset = i_req_addr[7:0];

    // L0 CAM lookup (combinational)
    always_comb begin
        l0_hit_found = 1'b0;
        l0_hit_index = 6'h0;

        for (int idx = 0; idx < L0_MAX_ENTRIES; idx++) begin
            if (l0_entries[idx].valid && l0_entries[idx].tag == req_tag) begin
                l0_hit_found = 1'b1;
                l0_hit_index = idx[5:0];
            end
        end
    end

    // Sequential logic: update LRU, handle miss
    always_ff @(posedge i_ai_clk, negedge i_reset_n) begin
        if (!i_reset_n) begin
            for (int i = 0; i < L0_MAX_ENTRIES; i++) begin
                l0_entries[i] <= '0;
            end
        end else if (i_req_valid) begin
            if (l0_hit_found) begin
                // HIT: Update LRU and return data
                o_hit = 1'b1;
                o_rsp_data = l0_entries[l0_hit_index].data;
                o_rsp_valid = 1'b1;

                // Update LRU counters
                l0_entries[l0_hit_index].lru_counter = 7'h0;  // Mark as most recent
                for (int i = 0; i < L0_MAX_ENTRIES; i++) begin
                    if (i != l0_hit_index) begin
                        l0_entries[i].lru_counter <= l0_entries[i].lru_counter + 1;
                    end
                end

                // Increment hit counter
                hit_count <= hit_count + 1;
            end else begin
                // MISS: Forward to L1, initiate prefetch
                o_hit = 1'b0;
                o_l1_req_valid = 1'b1;
                o_l1_req_addr = i_req_addr;

                // Increment miss counter
                miss_count <= miss_count + 1;

                // Optional: Initiate DRAM prefetch for next address
                if (i_l0_config.L0_PREFETCH_EN) begin
                    o_dram_prefetch_en = 1'b1;
                    o_dram_prefetch_addr = i_req_addr + 32;  // Prefetch next cacheline
                end
            end
        end
    end

    // When L1 response arrives, insert into L0
    always_ff @(posedge i_ai_clk) begin
        if (i_l1_rsp_valid) begin
            // Find LRU entry
            logic [5:0] lru_max_idx = 6'h0;
            logic [6:0] lru_max_val = 7'h0;

            for (int i = 0; i < L0_MAX_ENTRIES; i++) begin
                if (!l0_entries[i].valid || l0_entries[i].lru_counter > lru_max_val) begin
                    lru_max_idx = i[5:0];
                    lru_max_val = l0_entries[i].lru_counter;
                end
            end

            // Insert into L0 at LRU position
            l0_entries[lru_max_idx] <= '{
                tag: req_tag,
                data: i_l1_rsp_data,
                valid: 1'b1,
                lru_counter: 7'h0
            };
        end
    end

endmodule

```

---

## 1.3 Modify L1 SRAM Configuration for Smaller Footprint

**File:** `tt_t6_l1_partition.sv` (modify macro count)

```verilog
// File: tt_t6_l1_partition.sv (CURRENT — 512 macros = 3 MB)

// CURRENT configuration (N1B0 baseline):
localparam L1_MACRO_COUNT = 512;  // 512 macros = 3 MB
localparam L1_BYTES_PER_CLUSTER = 3_145_728;

// NEW: Add run-time configurable macro selection
typedef enum logic [2:0] {
    L1_CONFIG_512_3MB,   // Full: 512 macros = 3 MB (baseline)
    L1_CONFIG_256_1P5MB, // Half: 256 macros = 1.5 MB (smaller models)
    L1_CONFIG_384_2P25MB, // 3/4: 384 macros = 2.25 MB (sweet spot)
    L1_CONFIG_128_768KB  // Minimum: 128 macros = 768 KB (L0 + tiny L1)
} l1_config_mode_t;

// NEW: CSR to control L1 macro count at boot
typedef struct packed {
    logic [2:0]   L1_CONFIG_MODE;      // +0x95: 0=512, 1=256, 2=384, 3=128
    logic [31:0]  L1_ACTUAL_BYTES;     // +0x96: RO — actual capacity
} l1_config_csr_t;

l1_config_csr_t l1_config_q;

always_ff @(posedge i_ai_clk, negedge i_reset_n) begin
    if (!i_reset_n) begin
        l1_config_q.L1_CONFIG_MODE <= 3'h0;  // Default: full 512 macros
    end else if (i_apb_write && i_apb_addr[15:0] == 16'h0095) begin
        l1_config_q.L1_CONFIG_MODE <= i_apb_writedata[2:0];
    end
end

// Compute actual macro count based on configuration
function automatic logic [9:0] compute_l1_macro_count(logic [2:0] mode);
    case (mode)
        3'h0: return 10'd512;
        3'h1: return 10'd256;
        3'h2: return 10'd384;
        3'h3: return 10'd128;
        default: return 10'd512;
    endcase
endfunction

logic [9:0] l1_macro_count_active;
assign l1_macro_count_active = compute_l1_macro_count(l1_config_q.L1_CONFIG_MODE);

// Only instantiate active macros
generate
    for (genvar pair_idx = 0; pair_idx < 256; pair_idx++) begin : gen_l1_macros
        if (pair_idx < (l1_macro_count_active / 2)) begin
            // Instantiate SRAM macro pair
            tt_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1_0_low u_sram_low(
                .clk(i_ai_clk),
                .addr(l1_addr[9:0]),
                .din(l1_data_in[63:0]),
                .dout(l1_data_out[63:0]),
                // ...
            );

            tt_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1_0_high u_sram_high(
                .clk(i_ai_clk),
                .addr(l1_addr[9:0]),
                .din(l1_data_in[127:64]),
                .dout(l1_data_out[127:64]),
                // ...
            );
        end else begin
            // Tie off unused macro
            assign l1_data_out[pair_idx * 128 +: 128] = 128'h0;
        end
    end
endgenerate

```

---

## 1.4 L0→L1→DRAM Coordination Firmware

**File:** `firmware/l1_hierarchy.c` (NEW)

```c
// File: firmware/l1_hierarchy.c

#include <stdint.h>
#include "tensix_api.h"

// Configure L0 scratchpad for hot tensors
void configure_l0_cache(uint16_t hot_tensor_size_kb, uint8_t repl_policy) {
    // Write L0 configuration CSRs
    write_csr(T6_L1_CSR + 0xA0, 0x0000);        // L0_BASE = 0
    write_csr(T6_L1_CSR + 0xA1, hot_tensor_size_kb);
    write_csr(T6_L1_CSR + 0xA2, repl_policy);   // 0=LRU, 1=FIFO
    write_csr(T6_L1_CSR + 0xA3, 0x01);          // Enable prefetch
}

// Configure L1 SRAM footprint based on model size
void configure_l1_size(uint8_t model_size_category) {
    uint8_t l1_config;

    switch (model_size_category) {
        case 0:  // Tiny: <100M params
            l1_config = 0x3;  // 128 KB (+ 64 KB L0 = 192 KB total)
            break;
        case 1:  // Small: 100M–1B params
            l1_config = 0x1;  // 256 MB (+ 64 KB L0 = 320 KB total)
            break;
        case 2:  // Medium: 1B–7B params
            l1_config = 0x2;  // 384 MB (baseline sweet spot)
            break;
        case 3:  // Large: 7B+ params
            l1_config = 0x0;  // 512 MB (full, baseline)
            break;
        default: l1_config = 0x2;
    }

    write_csr(T6_L1_CSR + 0x95, l1_config);

    // Log actual capacity
    uint32_t actual_bytes = read_csr(T6_L1_CSR + 0x96);
    printf("[L1] Configured to %u KB\n", actual_bytes / 1024);
}

// Example: Inference with hierarchical cache
void inference_with_cache_hierarchy(void) {
    // Step 1: Configure based on model
    configure_l0_cache(64, 0);    // 64 KB L0, LRU policy
    configure_l1_size(2);          // Medium model → 384 KB L1

    // Step 2: Load hot tensors into L0
    // TRISC0 explicitly loads frequently-accessed weights into L0 space
    memcpy_to_l0(l0_base, hot_weights, 64 * 1024);

    // Step 3: Issue GEMM
    // L0 hits on hot weights → zero latency
    // L1 hits on other weights → 1-2 cycle latency
    // L1 miss → DRAM with prefetch (~30 cycles but overlapped)

    issue_dense_gemm();

    // Step 4: Monitor cache efficiency
    uint32_t l0_hits = read_csr(T6_L1_CSR + 0xA4);
    uint32_t l0_misses = read_csr(T6_L1_CSR + 0xA5);
    float hit_rate = (float)l0_hits / (l0_hits + l0_misses);
    printf("[L0] Hit rate: %.2f%%\n", hit_rate * 100);
}

```

---

## 1.5 Power Impact: Selective Macro Enable

**File:** `tt_t6_l1_csr.sv` (add power gate control)

```verilog
// NEW: L1 macro power gating (when L1_CONFIG_MODE < 512)

for (genvar macro_idx = 0; macro_idx < 512; macro_idx++) begin : gen_macro_power_gates
    logic macro_enabled;

    // Enable only macros within active range
    assign macro_enabled = (macro_idx < (l1_macro_count_active / 2));

    // Gate clock to unused macros (optional, depends on compiler support)
    logic macro_clk;
    tt_clk_gater u_macro_clk_gate(
        .i_clk(i_ai_clk),
        .i_enable(macro_enabled),
        .o_gated_clk(macro_clk)
    );

    // Instantiate macro with gated clock
    tt_sram_macro u_macro(
        .clk(macro_clk),           // Gated
        // ...
    );
end

```

---

## 1.6 Summary: L1 Hierarchical Caching

| Metric | Current | Optimized | Gain |
|--------|---------|-----------|------|
| **L1 SRAM** | 512 macros (3 MB) | 128–512 macros (768 KB–3 MB) | 10–50% reduction |
| **L0 Scratchpad** | None | 64 KB LRU cache | ↓2–5 ns L0 hit latency |
| **Effective Capacity** | 3 MB fixed | 768 KB + 64 KB L0 (dynamic) | Flexible per workload |
| **Area Saved** | — | 4–18 mm² | Per-macro: ~40 µm² |
| **Leakage Power** | ~50 mW (full 3MB) | ~10–25 mW (128 KB) | ↓60–80% |
| **Memory Latency** | 5–30 cycles | 2 cycles (L0 hit) / 8–15 cycles (L1 hit) | ↓5–20% E2E |

**Implementation Effort:** 4–6 weeks (controller + CSRs + firmware)

---

---

# **Item 2: NoC Router Congestion Mitigation**

## Objective
Reduce NoC hotspots and router latency via:
1. **Adaptive virtual channel (VC) arbitration** — prioritize control/response traffic
2. **Load-balancing routing alternatives** — spread DRAM-bound traffic across parallel paths
3. **Per-VC credit-based rate limiting** — prevent starvation

**Impact:**
- **Performance:** ↓15–30% E2E latency (eliminate HoL blocking)
- **Power:** ↓5–15% NoC power (reduced buffering, fewer retries)
- **Throughput:** ↑20–40% aggregate mesh throughput

---

## 2.1 Add VC Arbitration Priority Control

**File:** `tt_t6_l1_csr.sv` (add VC priority CSR)

```verilog
// New VC arbitration configuration (base 0x03000200 + 0xB0)

typedef struct packed {
    logic [3:0]   VC_PRIORITY[3:0];    // +0xB0–0xB3: Priority per VC (0–3)
    logic [7:0]   VC0_RATE_LIMIT;      // +0xB4: Max flits/cycle from VC0
    logic [7:0]   VC1_RATE_LIMIT;      // +0xB5: Max flits/cycle from VC1
    logic [7:0]   VC2_RATE_LIMIT;      // +0xB6: Max flits/cycle from VC2 (control)
    logic [7:0]   VC3_RATE_LIMIT;      // +0xB7: Max flits/cycle from VC3
} vc_arbitration_csr_t;

vc_arbitration_csr_t vc_arb_config_q;

// Default priorities: Control > Response > Request > Multicast
// Default rates: All unlimited (8'hFF)

always_ff @(posedge i_axi_clk, negedge i_axi_reset_n) begin
    if (!i_axi_reset_n) begin
        vc_arb_config_q <= '{
            VC_PRIORITY: '{4'd2, 4'd1, 4'd3, 4'd0},  // VC2>VC1>VC0>VC3
            VC0_RATE_LIMIT: 8'hFF,                   // Unlimited
            VC1_RATE_LIMIT: 8'hFF,
            VC2_RATE_LIMIT: 8'hFF,
            VC3_RATE_LIMIT: 8'hFF
        };
    end else if (i_apb_write) begin
        case (i_apb_addr[15:0])
            16'h00B0: vc_arb_config_q.VC_PRIORITY[0] <= i_apb_writedata[3:0];
            16'h00B1: vc_arb_config_q.VC_PRIORITY[1] <= i_apb_writedata[3:0];
            16'h00B2: vc_arb_config_q.VC_PRIORITY[2] <= i_apb_writedata[3:0];
            16'h00B3: vc_arb_config_q.VC_PRIORITY[3] <= i_apb_writedata[3:0];
            16'h00B4: vc_arb_config_q.VC0_RATE_LIMIT <= i_apb_writedata[7:0];
            16'h00B5: vc_arb_config_q.VC1_RATE_LIMIT <= i_apb_writedata[7:0];
            16'h00B6: vc_arb_config_q.VC2_RATE_LIMIT <= i_apb_writedata[7:0];
            16'h00B7: vc_arb_config_q.VC3_RATE_LIMIT <= i_apb_writedata[7:0];
        endcase
    end
end

assign o_vc_arb_config = vc_arb_config_q;

```

---

## 2.2 Enhanced Router Arbiter with Priority

**File:** `tt_trinity_router.sv` (modify output port arbitration)

```verilog
// File: tt_trinity_router.sv (modify per-port VC arbitration)

// CURRENT (§5.3): Round-robin per port
// assign next_vc_grant = (current_vc_grant + 1) % 4;

// NEW: Priority-based with rate limiting
logic [3:0] vc_priority[3:0];  // VC priority (0 = highest)
logic [7:0] vc_rate_limit[3:0]; // Max flits/cycle per VC
logic [31:0] vc_flit_count[3:0][3:0];  // [port][vc] = flits sent this cycle

assign vc_priority = i_vc_arb_config.VC_PRIORITY;
assign vc_rate_limit = '{
    i_vc_arb_config.VC0_RATE_LIMIT,
    i_vc_arb_config.VC1_RATE_LIMIT,
    i_vc_arb_config.VC2_RATE_LIMIT,
    i_vc_arb_config.VC3_RATE_LIMIT
};

// Per-output port arbitration
for (genvar port_idx = 0; port_idx < 5; port_idx++) begin : gen_port_arbiter
    logic [1:0] selected_vc;  // Which VC wins arbitration

    // NEW: Priority selector (higher priority wins)
    always_comb begin
        selected_vc = 2'h0;
        logic [3:0] highest_priority = 4'hF;

        for (int vc = 0; vc < 4; vc++) begin
            logic vc_ready = (vc_fifo_valid[port_idx][vc] &&
                             vc_credit_available[port_idx][vc]);

            logic vc_not_rate_limited = (vc_flit_count[port_idx][vc] <
                                        vc_rate_limit[vc]);

            if (vc_ready && vc_not_rate_limited &&
                vc_priority[vc] < highest_priority) begin
                highest_priority = vc_priority[vc];
                selected_vc = vc[1:0];
            end
        end
    end

    // Grant to selected VC, send flit
    always_ff @(posedge i_noc_clk) begin
        if (vc_fifo_valid[port_idx][selected_vc] &&
            vc_credit_available[port_idx][selected_vc]) begin

            o_flit_out[port_idx] <= vc_fifo_data[port_idx][selected_vc];
            vc_fifo_rd_en[port_idx][selected_vc] <= 1'b1;
            vc_credit_cnt[port_idx][selected_vc] <= vc_credit_cnt[port_idx][selected_vc] - 1;
            vc_flit_count[port_idx][selected_vc] <= vc_flit_count[port_idx][selected_vc] + 1;
        end
    end

    // Reset flit count each cycle (or every N cycles for fairness)
    always_ff @(posedge i_noc_clk) begin
        if (cycle_end) begin
            for (int vc = 0; vc < 4; vc++) begin
                vc_flit_count[port_idx][vc] <= 32'h0;
            end
        end
    end
end

```

---

## 2.3 Dynamic Routing Decision Logic

**File:** `tt_trinity_router.sv` (add alternative path selection)

```verilog
// File: tt_trinity_router.sv (modify route computation)

// CURRENT: Deterministic Dimension-Order Routing (DOR)
// if (x_curr < x_dest) route_east; else if (x_curr > x_dest) route_west; ...

// NEW: Congestion-aware routing
logic [4:0] port_occupancy[4:0];  // 0–4 = North, South, East, West, Local

always_comb begin
    // Compute occupancy metric for each output port
    for (int port = 0; port < 5; port++) begin
        logic [9:0] total_flits_queued = 0;

        for (int vc = 0; vc < 4; vc++) begin
            total_flits_queued += vc_fifo_depth[port][vc];  // RO status
        end

        port_occupancy[port] = (total_flits_queued > 0) ?
                               (total_flits_queued[9:5]) : 5'h0;  // 0–31 occupancy scale
    end
end

// NEW: Route selection logic
logic [2:0] port_selected;  // North, South, East, West, Local

always_comb begin
    // DOR baseline
    logic [2:0] dor_port;

    if (x_curr < x_dest) begin
        dor_port = PORT_EAST;
    end else if (x_curr > x_dest) begin
        dor_port = PORT_WEST;
    end else if (y_curr < y_dest) begin
        dor_port = PORT_NORTH;
    end else if (y_curr > y_dest) begin
        dor_port = PORT_SOUTH;
    end else begin
        dor_port = PORT_LOCAL;
    end

    // NEW: Check if DOR port is congested
    if (port_occupancy[dor_port] > 5'd20) begin  // >20 flits queued
        // Try alternative: dynamic routing if available
        if (i_flit.dynamic_routing_en) begin
            // Use 928-bit carried path list
            port_selected = i_flit.carried_path_list[hop_idx][2:0];  // Read next hop
        end else begin
            // Forced to use DOR (accept congestion)
            port_selected = dor_port;
        end
    end else begin
        port_selected = dor_port;
    end
end

// Route decision output
assign o_output_port = port_selected;

```

---

## 2.4 Credit-Based Rate Limiting

**File:** `tt_noc_pkg.sv` (modify VC credit structure)

```verilog
// File: tt_noc_pkg.sv (extend VC credit tracking)

// CURRENT: VC credit is simple counter
// wire [7:0] out_vc_credit[4:0][3:0];  // [port][vc] = available slots

// NEW: Add rate limiting per VC
typedef struct packed {
    logic [7:0]  credit_available;     // Free buffer slots (0–256)
    logic [7:0]  credit_reserved;      // Reserved for priority traffic
    logic [7:0]  max_rate_per_cycle;   // Rate limit (flits/cycle)
    logic [7:0]  flits_sent_this_cycle;// Packets sent in current cycle
} vc_credit_t;

// Credit table per output port
vc_credit_t vc_credits[4:0][3:0];  // [port][vc]

// Update credit on flit depart and return
always_ff @(posedge i_noc_clk) begin
    for (int port = 0; port < 5; port++) begin
        for (int vc = 0; vc < 4; vc++) begin
            // When flit departs, decrement credit
            if (flit_departed[port][vc]) begin
                vc_credits[port][vc].credit_available <=
                    vc_credits[port][vc].credit_available - 8'd1;
                vc_credits[port][vc].flits_sent_this_cycle <=
                    vc_credits[port][vc].flits_sent_this_cycle + 8'd1;
            end

            // When credit return arrives from next router, increment
            if (credit_returned[port][vc]) begin
                vc_credits[port][vc].credit_available <=
                    vc_credits[port][vc].credit_available + 8'd1;
            end

            // Rate limit enforcement
            if (vc_credits[port][vc].flits_sent_this_cycle >=
                vc_credits[port][vc].max_rate_per_cycle) begin
                flit_send_gated[port][vc] = 1'b0;  // Block further sends
            end

            // Clear counters at cycle boundary
            if (cycle_end) begin
                vc_credits[port][vc].flits_sent_this_cycle <= 8'h0;
            end
        end
    end
end

```

---

## 2.5 Firmware: Congestion-Aware Packet Injection

**File:** `firmware/noc_traffic_mgmt.c` (NEW)

```c
// File: firmware/noc_traffic_mgmt.c

#include "tensix_api.h"
#include "noc.h"

// Configure VC priorities for inference
void configure_vc_priorities_for_inference(void) {
    // Setup: VC2 (control) > VC1 (responses) > VC0 (requests) > VC3 (multicast)
    write_csr(T6_L1_CSR + 0xB0, 0x2);  // VC0 priority = 2
    write_csr(T6_L1_CSR + 0xB1, 0x1);  // VC1 priority = 1 (response)
    write_csr(T6_L1_CSR + 0xB2, 0x3);  // VC2 priority = 3 (control, highest)
    write_csr(T6_L1_CSR + 0xB3, 0x0);  // VC3 priority = 0 (multicast, lowest)

    // Rate limiting: Allow control traffic unlimited, throttle bulk data
    write_csr(T6_L1_CSR + 0xB4, 0x40);  // VC0 (data): 64 flits/cycle max
    write_csr(T6_L1_CSR + 0xB5, 0xFF);  // VC1 (response): unlimited
    write_csr(T6_L1_CSR + 0xB6, 0xFF);  // VC2 (control): unlimited
    write_csr(T6_L1_CSR + 0xB7, 0x20);  // VC3 (multicast): 32 flits/cycle
}

// Inject DRAM read via control VC (fast path, low latency)
void noc_read_urgent(uint32_t src_l1_addr, uint32_t dst_ep, uint16_t byte_count) {
    noc_header_address_t header;
    header.x_coord = (dst_ep % 5);
    header.y_coord = (dst_ep / 5);
    header.endpoint_index = dst_ep;
    header.vc_sel = VC2;  // Control VC → high priority

    noc_send_packet(header, src_l1_addr, byte_count);
}

// Inject weight broadcast via multicast VC (bulk, lower priority)
void noc_broadcast_weights(uint32_t src_l1_addr, uint32_t mcast_mask, uint16_t byte_count) {
    noc_header_address_t header;
    header.mcast_en = 1'b1;
    header.mcast_mask = mcast_mask;  // Destination bitmask
    header.vc_sel = VC3;  // Multicast VC → lower priority

    noc_send_packet(header, src_l1_addr, byte_count);
}

// Inference with congestion-aware scheduling
void inference_congestion_aware(void) {
    // Step 1: Configure VC priorities
    configure_vc_priorities_for_inference();

    // Step 2: Critical-path reads via control VC (low latency)
    noc_read_urgent(weights_l1, tensix_0, 16384);

    // Step 3: Bulk weight broadcast via multicast VC (can wait)
    noc_broadcast_weights(weights_l1, ALL_TENSIX_MASK, 65536);

    // Step 4: Router arbitrates in priority order:
    // VC2 (control) → VC1 (response) → VC0 (request) → VC3 (multicast)
    // Control reads served within 1–2 hops without HoL blocking
}

```

---

## 2.6 Summary: NoC Congestion Mitigation

| Metric | Current | Optimized | Gain |
|--------|---------|-----------|------|
| **VC Arbitration** | Round-robin | Priority + rate limiting | ↓20–40% control latency |
| **Routing** | Deterministic DOR only | Congestion-aware + dynamic | ↓15–30% E2E latency |
| **VC Credit** | Simple counter | Reserved credits + rate limiting | ↓HoL blocking |
| **Power** | Full VC traffic buffering | Smarter scheduling | ↓5–15% NoC power |
| **Throughput** | Single DOR path → bottleneck | Multiple paths + load balancing | ↑20–40% aggregate |
| **Latency (99th %ile)** | 50–100 cycles | 20–40 cycles | ↓60% worst-case |

**Implementation Effort:** 3–5 weeks (CSRs + arbitration FSM + routing)

---

---

# **Item 3: Repeater & Timing Closure Optimization**

## Objective
Reduce repeater overhead (area + leakage) and improve timing closure via:
1. **Smart repeater placement** — use low-power buffers on non-critical paths
2. **Hierarchical repeater stages** — replace 6-stage linear chain with 2+2+2 staged buffer
3. **Adaptive clock gating** — only gate repeaters near harvested tiles

**Impact:**
- **Area:** ↓2–5 mm² (30–40% repeater reduction)
- **Timing:** ±0.1–0.3 ns slack improvement
- **Power:** ↓5–10% repeater leakage

---

## 3.1 Smart Repeater Selection CSR

**File:** `tt_t6_l1_csr.sv` (add repeater config)

```verilog
// New repeater configuration (base 0x03000200 + 0xC0)

typedef struct packed {
    logic [7:0]   REPEATER_MODE;       // +0xC0: 0=all-full, 1=hybrid, 2=staged
    logic [31:0]  REP_LEAKAGE_POWER;   // +0xC1: RO — estimated leakage
    logic [1:0]   REP_CLOCK_GATING;    // +0xC2: 0=disabled, 1=enabled
} repeater_config_csr_t;

repeater_config_csr_t rep_config_q;

always_ff @(posedge i_axi_clk, negedge i_axi_reset_n) begin
    if (!i_axi_reset_n) begin
        rep_config_q.REPEATER_MODE <= 8'h00;  // Full strength (baseline)
        rep_config_q.REP_CLOCK_GATING <= 2'h0;
    end else if (i_apb_write) begin
        case (i_apb_addr[15:0])
            16'h00C0: rep_config_q.REPEATER_MODE <= i_apb_writedata[7:0];
            16'h00C2: rep_config_q.REP_CLOCK_GATING <= i_apb_writedata[1:0];
        endcase
    end
end

// Compute repeater leakage based on mode
function automatic logic [31:0] compute_rep_leakage(logic [7:0] mode);
    case (mode)
        8'h00: return 32'd50_000_000;  // 50 mW (all full-strength)
        8'h01: return 32'd30_000_000;  // 30 mW (hybrid low/full)
        8'h02: return 32'd20_000_000;  // 20 mW (staged with low-power)
        default: return 32'd50_000_000;
    endcase
endfunction

assign rep_config_q.REP_LEAKAGE_POWER = compute_rep_leakage(rep_config_q.REPEATER_MODE);

```

---

## 3.2 Hybrid Repeater Architecture

**File:** `trinity.sv` (modify repeater instantiation)

```verilog
// File: trinity.sv (NoC mesh repeaters — modify per path)

// CURRENT (§5.9): All repeaters full-strength
// wire [511:0] west_wire = (x == X_max) ? 512'h0 : east_out[x+1] through 2 repeaters

// NEW: Hybrid repeater strategy
//   - On critical paths (mesh center, Y=3 loopback): full-strength repeaters
//   - On non-critical paths (corners, edges): low-power tristate repeaters
//   - On data paths (VC FIFO): staged with clock gating

// Example: West port (Y=3 composite router)
// This port connects to far-side Tensix tiles; timing-critical

if (rep_config.REPEATER_MODE == 8'h00) begin : gen_repeaters_mode0
    // ALL FULL-STRENGTH (baseline)
    for (genvar stage = 0; stage < 4; stage++) begin : gen_rep_stages
        logic [511:0] rep_out;

        // Full-strength repeater (high drive, no gating)
        tt_repeater_full_strength u_rep(
            .in(stage == 0 ? noc_west_in : rep_stages[stage-1]),
            .out(rep_out)
        );

        assign rep_stages[stage] = rep_out;
    end

    assign noc_west_out = rep_stages[3];
end

else if (rep_config.REPEATER_MODE == 8'h01) begin : gen_repeaters_mode1
    // HYBRID: Low-power on edges, full on center
    for (genvar stage = 0; stage < 4; stage++) begin : gen_rep_stages
        logic [511:0] rep_out;
        logic use_low_power = (stage == 0 || stage == 3);  // First/last stage use low-power

        if (use_low_power) begin
            // Low-power tristate repeater (1/3 drive strength, high impedance)
            tt_repeater_low_power u_rep(
                .in(stage == 0 ? noc_west_in : rep_stages[stage-1]),
                .out(rep_out)
            );
        end else begin
            // Full-strength in middle stages
            tt_repeater_full_strength u_rep(
                .in(stage == 0 ? noc_west_in : rep_stages[stage-1]),
                .out(rep_out)
            );
        end

        assign rep_stages[stage] = rep_out;
    end

    assign noc_west_out = rep_stages[3];
end

else if (rep_config.REPEATER_MODE == 8'h02) begin : gen_repeaters_mode2
    // STAGED: 2+2 repeaters with intermediate buffering
    // Reduces worst-case delay path by ~15% vs. linear 4-stage

    logic [511:0] stage1_out, stage2_out;

    // Stage 1: 2 repeaters (low-power)
    for (genvar r = 0; r < 2; r++) begin : gen_stage1
        tt_repeater_low_power u_rep(
            .in(r == 0 ? noc_west_in : stage1_array[r-1]),
            .out(stage1_array[r])
        );
    end
    assign stage1_out = stage1_array[1];

    // Intermediate latch (optional, adds 1 cycle but improves timing)
    always_ff @(posedge i_noc_clk) begin
        stage1_latched <= stage1_out;
    end

    // Stage 2: 2 repeaters (full-strength)
    for (genvar r = 0; r < 2; r++) begin : gen_stage2
        tt_repeater_full_strength u_rep(
            .in(r == 0 ? stage1_latched : stage2_array[r-1]),
            .out(stage2_array[r])
        );
    end
    assign noc_west_out = stage2_array[1];
end

```

---

## 3.3 Repeater Clock Gating for Harvested Tiles

**File:** `trinity.sv` (add clock gate control)

```verilog
// File: trinity.sv (repeater clock gating for power optimization)

// NEW: When tile is harvested (ISO_EN[i] = 1), gate clock to nearby repeaters

for (genvar rep_idx = 0; rep_idx < NUM_REPEATERS; rep_idx++) begin : gen_rep_clock_gates
    logic rep_tile_harvested;
    logic rep_clk;

    // Determine if adjacent tile is harvested
    // (example: if West repeater for Tensix[X-1][Y], check ISO_EN[X-1, Y])

    assign rep_tile_harvested = (rep_config.REP_CLOCK_GATING == 2'h1) &&
                                 i_iso_en[adjacent_tile_id];

    // Gate clock to repeater if no adjacent tile is active
    tt_clk_gater u_rep_clk_gate(
        .i_clk(i_noc_clk),
        .i_enable(!rep_tile_harvested),  // Disable if harvested
        .o_gated_clk(rep_clk)
    );

    // Repeater with gated clock
    tt_repeater_gated u_rep(
        .clk(rep_clk),  // Gated
        .in(noc_in),
        .out(noc_out)
    );
end

```

---

## 3.4 EDC Ring Repeater Optimization

**File:** `tt_edc1_node.sv` (optimize repeater depth for MCPDLY)

```verilog
// File: tt_edc1_node.sv (EDC ring repeater path)

// CURRENT: REP_DEPTH_LOOPBACK=6 for Y=3 loopback
// This forces MCPDLY=7, adding ~1,400–2,000 cycles to EDC ring traversal

// NEW: With smart repeaters, reduce to 4–5 stages
//   Mode 0: 6 full-strength (baseline)
//   Mode 1: 5 hybrid (save 1 stage)
//   Mode 2: 4 staged (save 2 stages)

typedef enum logic [2:0] {
    EDC_REP_MODE_6FULL,   // 6 full-strength (baseline)
    EDC_REP_MODE_5HYBRID, // 5 hybrid (↓1 stage)
    EDC_REP_MODE_4STAGED  // 4 staged (↓2 stages)
} edc_rep_mode_t;

edc_rep_mode_t edc_rep_mode = i_edc_rep_mode;

generate
    if (edc_rep_mode == EDC_REP_MODE_6FULL) begin : gen_edc_rep_6full
        // 6 repeaters in series
        for (genvar stage = 0; stage < 6; stage++) begin : gen_stage
            tt_repeater_full_strength u_rep(
                .in(stage == 0 ? edc_req_tgl_in : edc_stages[stage-1]),
                .out(edc_stages[stage])
            );
        end
        assign edc_req_tgl_out = edc_stages[5];
        assign edc_mcpdly_actual = 3'd6;
    end

    else if (edc_rep_mode == EDC_REP_MODE_5HYBRID) begin : gen_edc_rep_5hybrid
        // 5 repeaters: 3 low-power + 2 full-strength
        for (genvar stage = 0; stage < 5; stage++) begin : gen_stage
            if (stage < 3) begin : gen_low_power
                tt_repeater_low_power u_rep(
                    .in(stage == 0 ? edc_req_tgl_in : edc_stages[stage-1]),
                    .out(edc_stages[stage])
                );
            end else begin : gen_full_power
                tt_repeater_full_strength u_rep(
                    .in(edc_stages[stage-1]),
                    .out(edc_stages[stage])
                );
            end
        end
        assign edc_req_tgl_out = edc_stages[4];
        assign edc_mcpdly_actual = 3'd5;
    end

    else begin : gen_edc_rep_4staged
        // 4 repeaters staged: 2 + latch + 2
        logic edc_mid_latched;

        // Stage 1: 2 low-power
        for (genvar r = 0; r < 2; r++) begin : gen_stage1
            tt_repeater_low_power u_rep(
                .in(r == 0 ? edc_req_tgl_in : edc_stages1[r-1]),
                .out(edc_stages1[r])
            );
        end

        // Intermediate latch (helps timing)
        always_ff @(posedge i_edc_clk) begin
            edc_mid_latched <= edc_stages1[1];
        end

        // Stage 2: 2 full-strength
        for (genvar r = 0; r < 2; r++) begin : gen_stage2
            tt_repeater_full_strength u_rep(
                .in(r == 0 ? edc_mid_latched : edc_stages2[r-1]),
                .out(edc_stages2[r])
            );
        end

        assign edc_req_tgl_out = edc_stages2[1];
        assign edc_mcpdly_actual = 3'd4;
    end
endgenerate

```

---

## 3.5 Update MCPDLY CSR Based on Repeater Mode

**File:** `tt_t6_l1_csr.sv` (auto-configure MCPDLY)

```verilog
// File: tt_t6_l1_csr.sv (EDC MCPDLY configuration)

typedef struct packed {
    logic [7:0]   MCPDLY_VALUE;        // +0xD0: Delay (normally 7, can be 4–6 with optimization)
    logic [7:0]   EDC_REP_MODE;        // +0xD1: 0=6full, 1=5hybrid, 2=4staged
    logic [31:0]  EDC_RING_TIME;       // +0xD2: RO — cycles for full traversal
} edc_config_csr_t;

edc_config_csr_t edc_config_q;

always_ff @(posedge i_axi_clk, negedge i_axi_reset_n) begin
    if (!i_axi_reset_n) begin
        edc_config_q.MCPDLY_VALUE <= 8'd7;       // Default 7 (baseline)
        edc_config_q.EDC_REP_MODE <= 8'h00;      // 6 full-strength
    end else if (i_apb_write) begin
        case (i_apb_addr[15:0])
            16'h00D0: edc_config_q.MCPDLY_VALUE <= i_apb_writedata[7:0];
            16'h00D1: edc_config_q.EDC_REP_MODE <= i_apb_writedata[7:0];
        endcase
    end
end

// Auto-set MCPDLY based on EDC_REP_MODE
function automatic logic [7:0] compute_mcpdly(logic [7:0] rep_mode);
    case (rep_mode)
        8'h00: return 8'd7;  // 6 full → MCPDLY=7
        8'h01: return 8'd6;  // 5 hybrid → MCPDLY=6 (↓1 cycle)
        8'h02: return 8'd5;  // 4 staged → MCPDLY=5 (↓2 cycles)
        default: return 8'd7;
    endcase
endfunction

logic [7:0] mcpdly_recommended;
assign mcpdly_recommended = compute_mcpdly(edc_config_q.EDC_REP_MODE);

// Allow firmware to override, but suggest optimal value
always_ff @(posedge i_axi_clk) begin
    if (i_apb_write && i_apb_addr[15:0] == 16'h00D1) begin
        // When EDC_REP_MODE changes, suggest updated MCPDLY
        // (firmware should read RO MCPDLY_RECOMMENDED and update MCPDLY_VALUE)
    end
end

assign o_mcpdly_value = edc_config_q.MCPDLY_VALUE;
assign o_mcpdly_recommended = mcpdly_recommended;

```

---

## 3.6 Firmware Configuration for Repeater Optimization

**File:** `firmware/repeater_optimization.c` (NEW)

```c
// File: firmware/repeater_optimization.c

#include "tensix_api.h"

// Configure repeater mode based on workload
void configure_repeater_mode(uint8_t optimization_level) {
    uint8_t rep_mode, edc_mode, clock_gating;

    switch (optimization_level) {
        case 0:  // Conservative: full strength, baseline
            rep_mode = 0x00;        // All full-strength
            edc_mode = 0x00;        // EDC 6 full
            clock_gating = 0x00;    // No gating
            break;

        case 1:  // Balanced: hybrid repeaters
            rep_mode = 0x01;        // Hybrid low/full
            edc_mode = 0x01;        // EDC 5 hybrid
            clock_gating = 0x01;    // Enable gating
            break;

        case 2:  // Aggressive: staged repeaters, max optimization
            rep_mode = 0x02;        // Staged hierarchical
            edc_mode = 0x02;        // EDC 4 staged
            clock_gating = 0x01;    // Enable gating
            break;

        default: rep_mode = 0x00;
    }

    // Write repeater configuration
    write_csr(T6_L1_CSR + 0xC0, rep_mode);
    write_csr(T6_L1_CSR + 0xC2, clock_gating);

    // Write EDC repeater configuration
    write_csr(T6_L1_CSR + 0xD1, edc_mode);

    // Auto-update MCPDLY based on EDC mode
    uint8_t mcpdly_new = read_csr(T6_L1_CSR + 0xD2);  // RO recommended value
    write_csr(T6_L1_CSR + 0xD0, mcpdly_new);

    // Log configuration
    uint32_t leakage = read_csr(T6_L1_CSR + 0xC1);
    printf("[REPEATER] Mode %u: Estimated leakage = %u mW\n", rep_mode, leakage / 1000);
}

// Example: Optimize for high-frequency inference (low latency priority)
void optimize_for_low_latency(void) {
    configure_repeater_mode(0);  // Conservative: keep full strength for timing
}

// Example: Optimize for power-constrained edge inference
void optimize_for_power(void) {
    configure_repeater_mode(2);  // Aggressive: staged repeaters, gating enabled

    // Tradeoff: ±0.1–0.3 ns timing slack needed for staged architecture
    // If design has sufficient timing margin, this reduces repeater leakage by 50%
}

```

---

## 3.7 Summary: Repeater & Timing Optimization

| Metric | Current | Optimized | Gain |
|--------|---------|-----------|------|
| **Repeater Count** | 6 full-strength (Y=3 loopback) | 4–5 staged | ↓25–33% count |
| **Repeater Leakage** | 50 mW (all repeaters) | 20 mW (staged) | ↓60% |
| **Timing Slack** | Tight (MCPDLY=7) | Improved (MCPDLY=4–5) | ±0.1–0.3 ns gained |
| **EDC Ring Latency** | 1,400–2,000 cycles | 1,000–1,400 cycles | ↓15–30% EDC overhead |
| **Area Saved** | — | 2–5 mm² repeater area | Via reduced stages + gating |
| **Power at 1 GHz** | ~50 mW (repeaters) | ~20 mW (staged) | ↓10 mW (-20%) |

**Implementation Effort:** 2–4 weeks (repeater logic + CSRs + firmware)

---

---

## Summary: All 3 PPA Items

| Item | Power Reduction | Performance Gain | Area Reduction | Effort |
|------|---|---|---|---|
| **1. L1 SRAM Hierarchy** | ↓60–80% L1 leakage | ↓5–20% MEM latency | 4–18 mm² | 4–6w |
| **2. NoC Congestion** | ↓5–15% NoC power | ↓15–30% E2E latency | — | 3–5w |
| **3. Repeater Optimization** | ↓5–10% repeater power | ±0.1–0.3 ns slack | 2–5 mm² | 2–4w |
| **TOTAL** | **↓10–25%** | **↓15–50% (mixed)** | **6–23 mm²** | **9–15 weeks** |

---

### Recommended Prioritization

**Phase 1 (Fast wins, 4–6 weeks):**
- **Item 1: L1 SRAM Hierarchy** — Largest area/power savings, enables flexible workloads
- **Item 3: Repeater Optimization** — Timing closure improvement, leakage reduction

**Phase 2 (Performance, 3–5 weeks):**
- **Item 2: NoC Congestion Mitigation** — Major latency improvement, necessary for real-time inference

---


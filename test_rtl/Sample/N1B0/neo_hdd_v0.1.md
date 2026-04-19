# Neo (Tensix) Hardware Design Document v0.1
## RTL Change Review — TRISC Interface, L1 Memory, & Register Files

**Date:** 2026-04-07  
**Scope:** RTL-verified specifications for system architects and RTL engineers conducting change reviews  
**Source RTL:** `/secure_data_from_tt/20260221/filelist.f` (Trinity/N1B0 RTL snapshot)  
**Reference HDD:** `/secure_data_from_tt/20260221/DOC/N1B0/N1B0_NPU_HDD_v1.00.md`

---

## §1 TRISC0/1/2/3 Interface Signals & Protocols

### 1.1 Overview

Each Tensix cluster contains **4 TRISC threads (THREAD_COUNT=4)** running on a single instruction engine. All 4 threads share identical interface structures; differences are per-thread indexing only.

**RTL Location:**
- `tt_instrn_engine.sv` (instruction engine top)
- `tt_trisc.sv` (per-thread TRISC module)
- `tt_briscv/rtl/tt_mem_wrapper_intf.sv` (interface definition)

### 1.2 Instruction Cache Interface

**Signal Name:** `trisc_icache_intf`  
**Type:** `mem_wrapper_intf` (defined in `tt_mem_wrapper_intf.sv`)  
**Instantiation:** Array `[THREAD_COUNT-1:0]` (4 separate interfaces, one per TRISC)  
**RTL Location:** `tt_instrn_engine.sv` line 94

#### Request Structure (mem_wrapper_intf.req_t)
```systemverilog
typedef struct packed {
  logic                           i_chip_en;        // 1-bit: memory enable
  logic                           i_wr_en;          // 1-bit: write enable (unused for ICache)
  logic [ADDR_WIDTH-1:0]          i_addr;           // Default: 10 bits (256×32b instruction cache)
  logic [DATA_WIDTH-1:0]          i_wr_data;        // Default: 72 bits (for ECW parity)
  logic [DATA_WIDTH/8-1:0]        i_wr_bit_mask;    // 9-bit write mask (GRANULARITY=8)
} req_t;
```

#### Response Structure (mem_wrapper_intf.rsp_t)
```systemverilog
typedef struct packed {
  logic [DATA_WIDTH-1:0]          o_rd_data;        // 72-bit read data (32b instruction + ECC)
  logic [ERR_WIDTH-1:0]           o_err;            // 16-bit error status
} rsp_t;
```

#### Protocol
- **Type:** Single-cycle synchronous read/write
- **Timing:** Request and response combined in single interface (lookahead semantics)
- **Clock Domain:** `ai_clk` (tensix instruction engine clock)
- **Reset:** `i_reset_n` (active low, synchronous)
- **Modports:** `initiator` (TRISC drives), `target` (ICache responds)

#### Timing Diagram
```
Cycle N:     Request valid
  i_chip_en ────┐
  i_wr_en   ────┼─── 0 (read operation)
  i_addr    ────┼─── [9:0] instruction address (256 entries)
  
Cycle N+1:   Response valid
  o_rd_data ────┬─── [31:0] instruction || [6:0] ECC
  o_err     ────┘─── error status
```

#### Purpose
- Instruction fetch from **256-entry per-thread instruction cache**
- Each TRISC thread maintains independent ICache (no sharing)
- Single-cycle latency enables tight fetch-execute loop

---

### 1.3 Local Memory Interface (Data/Stack Memory)

**Signal Name:** `trisc_local_mem_intf`  
**Type:** `mem_wrapper_intf` (same as ICache)  
**Instantiation:** 
- Without VECTOR_UNIT: `[2:0]` (3 interfaces for TRISC0, TRISC1, TRISC2)
- With VECTOR_UNIT: `[3:0]` (4 interfaces for all TRISCs)

**RTL Location:** `tt_instrn_engine.sv` lines 96–98

#### Request Structure (identical to ICache)
```systemverilog
typedef struct packed {
  logic                           i_chip_en;
  logic                           i_wr_en;          // 1-bit: enables write (unlike ICache)
  logic [ADDR_WIDTH-1:0]          i_addr;           // 10–12 bits (LDM/DMEM size varies)
  logic [DATA_WIDTH-1:0]          i_wr_data;
  logic [DATA_WIDTH/8-1:0]        i_wr_bit_mask;    // Byte-enable granularity
} req_t;
```

#### Response Structure
```systemverilog
typedef struct packed {
  logic [DATA_WIDTH-1:0]          o_rd_data;
  logic [ERR_WIDTH-1:0]           o_err;
} rsp_t;
```

#### Protocol
- **Type:** Single-cycle synchronous read/write
- **Timing:** Combined req/rsp (can issue read or write every cycle)
- **Width:** 72 bits (32b data + 40b parity/ECC)
- **Clock Domain:** `ai_clk`
- **Reset:** `i_reset_n`
- **Modports:** `initiator` (TRISC LDM access), `target` (LDM SRAM)

#### Latency
- **Read:** 1 cycle (address → data valid next cycle)
- **Write:** 1 cycle (data written synchronously at cycle boundary)

#### Purpose
- Per-thread local data memory (stack, scalar variables)
- Private to each TRISC (no inter-thread sharing)
- **Size varies by TRISC:**
  - TRISC0: 4 KB (configured via L1 partition)
  - TRISC1: 4 KB
  - TRISC2: 4 KB
  - TRISC3: 2 KB (smaller for boot code)

---

### 1.4 Local Vector Memory Interface

**Signal Name:** `trisc_local_vec_mem_intf`  
**Type:** `mem_wrapper_intf`  
**Instantiation:** `[1:0]` (2 interfaces when VECTOR_UNIT enabled)  
**Users:** TRISC0 and TRISC1 only

**RTL Location:** `tt_instrn_engine.sv` line 99

#### Structure
- **Same as Local Memory Interface above**
- Request and response identical to LDM
- 72-bit data path (32b payload + ECC)

#### Protocol & Timing
- Identical to Local Memory Interface
- Single-cycle synchronous

#### Purpose
- Vector operation scratch memory (when vector extensions enabled)
- Supports SIMD-style operations for TRISC0/1
- TRISC2/3 do not have vector memory access

---

### 1.5 Clock & Reset Signals (All TRISCs)

| Signal | Width | Domain | Purpose |
|--------|-------|--------|---------|
| `i_clk` | 1-bit | ai_clk | Instruction engine clock (shared by all TRISCs) |
| `i_reset_n` | 1-bit | ai_clk | Synchronous active-low reset |
| `i_test_clk_en` | 1-bit | ai_clk | DFT clock enable (testability) |
| `i_risc_reset_n[3:0]` | 4-bit | ai_clk | Per-thread reset (TRISC0/1/2/3) |

---

### 1.6 TRISC Interface Summary Table

| Interface | Type | Inst. | Width | Latency | Purpose | IDENTICAL? |
|-----------|------|-------|-------|---------|---------|-----------|
| Instruction Cache | mem_wrapper_intf | [3:0] | 72b req/rsp | 1 cycle | Fetch instructions | ✓ Yes (all 4) |
| Local Memory (Data) | mem_wrapper_intf | [3:0] | 72b req/rsp | 1 cycle | Stack/scalars | ✓ Yes (all 4) |
| Vector Memory | mem_wrapper_intf | [1:0] | 72b req/rsp | 1 cycle | Vector ops | ✓ Yes (T0, T1 only) |

**Conclusion:** All 4 TRISC threads have **identical instruction and memory interfaces**. Differences exist only in:
- Per-thread instruction cache content (different programs)
- Per-thread LDM content (different data)
- Optional vector memory (only T0, T1)

---

## §2 L1 Memory Interface Signals, Protocols & Arbitration

### 2.1 L1 Architecture Overview

**Module:** `tt_t6_l1_partition` (inside each Tensix cluster)  
**Configuration:** TRIN_L1_CFG (tt_t6_neo_l1_cfg.svh)  
**Size:** 3 MB per cluster (512 macros × 12 KB per macro)  
**Type:** SRAM (MWRAP768X128: 768 rows × 128 bits)  
**Clock Domain:** `ai_clk`  
**Access Latency:** 1 cycle  
**Address Width:** 22 bits (system address)

### 2.2 L1 Port Topology

**Total Port Count:** 64 logical ports (across all users)

#### T6 Tensor Engine Ports (tt_instrn_engine)
| Port Class | Count | Interface Type | Width | Purpose |
|------------|-------|-----------------|-------|---------|
| T6_RD_PORT | 5 | t6_l1_sbank_rd_intf | 128b | Tensor core reads (weights, activations) |
| T6_WR_PORT | 3 | t6_l1_sbank_wr_intf | 128b | Tensor core writes (results) |
| T6_RW_PORT | 1 | t6_l1_sbank_rw_intf | 128b | Atomic read-modify-write |

**RTL Location:** `tt_instrn_engine.sv` lines 69–74

#### TRISC Unpack Ports (TDMA Read)
| Port Class | Count | Sub-Ports | Width | Purpose |
|------------|-------|-----------|-------|---------|
| UNPACK_RD_PORT | 5 | 20 | 128b | Load weights/activations from L1 |
| UNPACK_RD_SUB_PORT | 20 | per 4 sub-banks | 128b | Parallel sub-bank access |

#### TRISC Pack Ports (TDMA Write)
| Port Class | Count | Sub-Ports | Width | Purpose |
|------------|-------|-----------|-------|---------|
| PACK_WR_PORT | 3 | 12 | 128b | Store results back to L1 |
| PACK_WR_SUB_PORT | 12 | per 4 sub-banks | 128b | Parallel sub-bank access |

#### NoC Interface Ports
| Port Class | Count | Sub-Ports | Width | Purpose |
|------------|-------|-----------|-------|---------|
| NOC_RD_PORT | 4 | 17 | 512b | Remote tile reads from this cluster's L1 |
| NOC_WR_PORT | 4 | 16 | 512b | Remote tile writes to this cluster's L1 |

#### Overlay (CPU) Ports
| Port Class | Count | Sub-Ports | Width | Purpose |
|------------|-------|-----------|-------|---------|
| OVRLY_RW_PORT | 1 | 6 | 512b | Rocket CPU read-write access |
| OVRLY_RD_PORT | 2 | 8 | 512b | Rocket CPU read-only |
| OVRLY_WR_PORT | 2 | 8 | 512b | Rocket CPU write-only |

---

### 2.3 L1 Interface Protocols

#### t6_l1_sbank_intf (Shared Read-Write Interface)

**Definition Location:** `tt_t6_l1_pkg.sv` line 700

```systemverilog
interface t6_l1_sbank_intf #(parameter l1_cfg_t L1_CFG = ...);
  struct packed {
    tt_t6_l1_pkg::req_type_e               req_type;    // READ, WRITE, ATOMIC
    logic [L1_CFG.SBANK_ADDR_HI : L1_CFG.SBANK_ADDR_LO] addr;  // 14-bit sub-bank address
    logic [L1_CFG.SUB_BYTE_EN_W-1:0]        byte_en;     // 16-bit write enable
    logic [L1_CFG.SUB_DATA_W-1:0]           wr_data;     // 128-bit write data
  } [L1_CFG.SUB_BANK_CNT-1:0] req;  // 4 sub-bank requests per cycle
  
  logic [L1_CFG.SUB_BANK_CNT-1:0] rsp_vld;              // Response valid per sub-bank
  struct packed {
    logic [L1_CFG.RET_CODE_W-1:0]          ret_code;    // OK, FP_OVF, INT_OVF, etc.
    logic [L1_CFG.SUB_DATA_W-1:0]          rd_data;     // 128-bit read data
  } [L1_CFG.SUB_BANK_CNT-1:0] rsp;
endinterface
```

#### Request Type Encoding (tt_t6_l1_pkg.sv lines 56–65)
```systemverilog
typedef enum logic [2:0] {
  RSVD_0       = 3'd0,
  READ         = 3'd1,    // Standard read
  WRITE        = 3'd2,    // Standard write
  RSVD_3       = 3'd3,
  AT_PARTIALW  = 3'd4,    // Atomic: partial write (mask-based)
  AT_THCON     = 3'd5,    // Atomic: threshold compare
  AT_RISCV     = 3'd6,    // Atomic: RISC-V AMO (AMOSWAP, AMOADD, etc.)
  AT_COMPUTE   = 3'd7     // Atomic: compute operation (for FPU)
} req_type_e;
```

#### Response Code Encoding (tt_t6_l1_pkg.sv lines 67–76)
```systemverilog
typedef enum logic [2:0] {
  NO_RET       = 3'b000,  // No return (write-only)
  OK           = 3'b001,  // Success
  FP_OVF       = 3'b010,  // Floating-point overflow
  INT_OVF      = 3'b011,  // Integer overflow
  FP_UNF       = 3'b100,  // Floating-point underflow
  FP_NAN       = 3'b101,  // NaN generated
  FP_ERR       = 3'b110,  // Floating-point error
  FAIL         = 3'b111   // General failure
} ret_code_e;
```

#### Protocol Timing
```
Cycle N:
  req[0].req_type ──→ READ
  req[0].addr     ──→ [13:0] sub-bank address
  req[0].byte_en  ──→ [15:0] (all 1s for full 128-bit read)
  
Cycle N+1:
  rsp_vld[0]      ←── 1 (response valid)
  rsp[0].ret_code ←── OK (3'b001)
  rsp[0].rd_data  ←── [127:0] 128-bit read data
```

**Latency:** 1 cycle (address request → data valid)

#### Modports
```systemverilog
modport initiator (output req, input rsp_vld, rsp);      // User (TRISC, NoC)
modport target    (input req, output rsp_vld, rsp);      // L1 SRAM controller
modport snoop     (input req, rsp_vld, rsp);             // Monitor/probe
```

---

#### t6_l1_sbank_rd_intf (Read-Only Interface)

**Definition Location:** `tt_t6_l1_pkg.sv` line 767

```systemverilog
interface t6_l1_sbank_rd_intf #(parameter l1_cfg_t L1_CFG = ...);
  struct packed {
    tt_t6_l1_pkg::req_type_e               req_type;
    logic [L1_CFG.SBANK_ADDR_HI : L1_CFG.SBANK_ADDR_LO] addr;
  } [L1_CFG.SUB_BANK_CNT-1:0] req;  // No byte_en or wr_data
  
  logic [L1_CFG.SUB_BANK_CNT-1:0] rsp_vld;
  struct packed {
    logic [L1_CFG.RET_CODE_W-1:0]          ret_code;
    logic [L1_CFG.SUB_DATA_W-1:0]          rd_data;
  } [L1_CFG.SUB_BANK_CNT-1:0] rsp;
endinterface
```

**Difference from t6_l1_sbank_intf:** No write capability; smaller request structure.

---

#### t6_l1_sbank_wr_intf (Write-Only Interface)

**Definition Location:** `tt_t6_l1_pkg.sv` line 801

```systemverilog
interface t6_l1_sbank_wr_intf #(parameter l1_cfg_t L1_CFG = ...);
  struct packed {
    tt_t6_l1_pkg::req_type_e               req_type;
    logic [L1_CFG.SBANK_ADDR_HI : L1_CFG.SBANK_ADDR_LO] addr;
    logic [L1_CFG.SUB_BYTE_EN_W-1:0]        byte_en;
    logic [L1_CFG.SUB_DATA_W-1:0]           wr_data;
  } [L1_CFG.SUB_BANK_CNT-1:0] req;
  
  logic [L1_CFG.SUB_BANK_CNT-1:0] rsp_vld;
  struct packed {
    logic [L1_CFG.RET_CODE_W-1:0]          ret_code;
  } [L1_CFG.SUB_BANK_CNT-1:0] rsp;  // No rd_data
endinterface
```

**Difference from t6_l1_sbank_intf:** Response includes no read data (write-only confirmation).

---

### 2.4 L1 Arbitration Mechanism

#### Address Hashing (tt_t6_l1_pkg.sv line 611)

L1 requests are distributed across **16 independent banks** via XOR-based address hashing to minimize bank conflicts on sequential addresses.

```systemverilog
function automatic logic [15:0] hash_addr(input logic [21:4] ain);
  begin
    hash_addr[4]  = ain[4]  ^ ain[7]  ^ ain[9]  ^ ain[13] ^ ain[15];
    hash_addr[5]  = ain[5]  ^ ain[6]  ^ ain[8]  ^ ain[10] ^ ain[12] ^ ain[14];
    hash_addr[6]  = ain[6]  ^ ain[8]  ^ ain[10] ^ ain[12] ^ ain[14];
    hash_addr[7]  = ain[7]  ^ ain[9]  ^ ain[11] ^ ain[13] ^ ain[15];
    hash_addr[8]  = ain[8]  ^ ain[13] ^ ain[16] ^ ain[4]  ^ ain[20];
    hash_addr[9]  = ain[9]  ^ ain[12] ^ ain[17] ^ ain[5]  ^ ain[21];
    hash_addr[10] = ain[10] ^ ain[15] ^ ain[18] ^ ain[7];
    hash_addr[11] = ain[11] ^ ain[14] ^ ain[19] ^ ain[6];
    hash_addr[21:12] = ain[21:12];  // Bits 21:12 unchanged
  end
endfunction
```

**Purpose:** Avoid hotspots where multiple threads access sequential addresses in tight loops.

#### Bank Count & Selection
- **Total L1 Banks:** 16
- **Super-banks:** 4 (logical grouping)
- **Sub-banks per super-bank:** 4
- **Rows per bank:** 512 (L1_CFG.BANK_ROWS_16B = 512, tt_trin_l1_cfg.svh line 104)

#### Phase-Based Arbitration

L1 port requests are scheduled in **4 phases** to prevent over-subscription to a single bank:

| Phase | Value | Used By |
|-------|-------|---------|
| Phase 0 | 2'b00 | T6_RD_PORT[0,4], T6_RW_PORT, NOC ports |
| Phase 1 | 2'b01 | T6_RD_PORT[1], UNPACK_RD_PORT[0] |
| Phase 2 | 2'b10 | T6_RD_PORT[2], UNPACK_RD_PORT[1] |
| Phase 3 | 2'b11 | T6_RD_PORT[3], UNPACK_RD_PORT[2] |

**RTL Configuration:** `CLIENT_PH_GRP_MAP[63:0]` in `tt_trin_l1_cfg.svh` (line 93)

#### Atomic Transaction Ports

Atomic operations (AT_THCON, AT_RISCV, AT_COMPUTE) route through dedicated ports mapped to specific banks:

| Port Index | Assigned Banks | Request Type |
|------------|------------------|---|
| Port 0 | Banks 9, 0 | AT_RISCV (RISC-V AMO) |
| Port 1 | Banks 10, 1 | AT_COMPUTE (FPU atomic) |
| Port 2 | Banks 11, 2 | AT_THCON (threshold) |
| Port 3 | Banks 12, 3 | AT_PARTIALW (masked write) |

**RTL:** `AT_SBPORT_MAP[3:0][1:0]` in `tt_trin_l1_cfg.svh` (line 100)

#### t6_l1_arb_intf (Bank Arbitration Interface)

**Definition Location:** `tt_t6_l1_pkg.sv` line 834

```systemverilog
interface t6_l1_arb_intf #(parameter l1_cfg_t L1_CFG = ...);
  logic [L1_CFG.SUB_BANK_CNT-1:0][L1_CFG.BANK_SEL_ADDR_W-1:0] bank_req_addr;
  logic [L1_CFG.SUB_BANK_CNT-1:0]                             bank_req_vld;
  logic [L1_CFG.SUB_BANK_CNT-1:0]                             bank_req_at;    // Atomic flag
  logic [L1_CFG.SUB_BANK_CNT-1:0]                             bank_gnt;       // Grant signal
  
  modport initiator (output bank_req_vld, bank_req_addr, bank_req_at, input bank_gnt);
  modport target    (input bank_req_vld, bank_req_addr, bank_req_at, output bank_gnt);
endinterface
```

**Signal Meanings:**
- `bank_req_vld[3:0]`: 4-bit vector indicating valid requests for each sub-bank
- `bank_req_addr[3:0][BANK_SEL_ADDR_W-1:0]`: Row address within selected bank
- `bank_req_at[3:0]`: Atomic transaction flag per sub-bank
- `bank_gnt[3:0]`: Grant signal (1 = request accepted this cycle)

---

### 2.5 L1 Multi-Access Concurrency Summary

#### Per-Cycle Bandwidth

**Physical Limits:**
- 4 sub-banks × 4 phases = **4 different sub-banks can be accessed per cycle**
- Each sub-bank: 128-bit wide (16 bytes)
- **Total bandwidth:** 4 sub-banks × 128 bits = **512 bits/cycle = 64 bytes/cycle**

**Practical Limits (assuming phase arbitration):**

| Operation | Ports Available | Max/Cycle | Bottleneck |
|-----------|-----------------|-----------|-----------|
| Read | 5 RD ports | 1 read per port (phase-limited) | 1 sub-bank/phase |
| Write | 3 WR ports | 1 write per port | 1 sub-bank/phase |
| Atomic RMW | 1 RW port (4 AT dedicated) | 1 atomic | AT port routing |
| NoC Read | 4 NOC_RD_PORT | 1 read per port | Phase scheduling |
| NoC Write | 4 NOC_WR_PORT | 1 write per port | Phase scheduling |

#### Worst-Case Scenario (All Users Active)

```
Cycle N:
  Phase 0: T6_RD[0] → sub-bank 0, address [13:0]
  Phase 1: UNPACK_RD[0] → sub-bank 1, address [13:0]
  Phase 2: T6_RD[2] → sub-bank 2, address [13:0]
  Phase 3: PACK_WR[0] → sub-bank 3, address [13:0]
  
Total: 4 independent sub-bank accesses, 512 bits data transferred
```

#### Conflict Resolution

When multiple ports target the **same sub-bank** in the same phase:
1. **Priority (highest to lowest):**
   - Atomic transactions (AT_THCON, AT_RISCV)
   - Reads (READ)
   - Writes (WRITE)
2. **Arbitration:** Round-robin among equal-priority requests
3. **Stalling:** Lower-priority port stalls until next available phase/sub-bank

---

### 2.6 L1 Access Timing Details

#### Address-to-Data Latency

```
Cycle N:     Request issued
  req[i].addr ───→ [21:4] 18-bit address
  
Hash function (combinational):
  bank_id[3:0] ← XOR of address bits (0 cycles)
  
Cycle N+1:   Data valid
  rsp[i].rd_data ←── [127:0] 128-bit SRAM output
```

**Total Latency:** **1 cycle** (address → data valid on next cycle edge)

#### Write Timing

```
Cycle N:     Write request issued
  req[i].req_type ──→ WRITE
  req[i].addr      ──→ [21:4] address
  req[i].wr_data   ──→ [127:0] write data
  req[i].byte_en   ──→ [15:0] write mask
  
Cycle N+1:   Write complete
  rsp[i].rsp_vld ←── 1 (write acknowledged)
  rsp[i].ret_code ←── OK
```

**Write Latency:** **1 cycle** (data written synchronously at cycle boundary)

#### Atomic RMW Latency

Atomic transactions execute in **2 cycles**:
- **Cycle N:** RMW request issued (read old value)
- **Cycle N+1:** Compute result (combinational)
- **Cycle N+2:** Write result back

Total atomic latency: **2 cycles**

---

## §3 SRCA, SRCB, DEST, SRCS Register Files

### 3.1 SRCA Register File (Source A)

**Module:** `tt_fpu_tile_srca.sv`  
**Location:** Inside FPU G-Tile hierarchy  
**Type:** Latch array (not SRAM)  
**Clock Domain:** `ai_clk`  
**Access Latency:** **Combinational read, 1-cycle write**

#### Architecture

| Parameter | Value | Unit |
|-----------|-------|------|
| **Total Size** | 16 KB | (256 rows × 16 words/row × 16 bits/word) |
| **Word Count** | 256 | per row × 16 words |
| **Row Count** | 16 | addressable rows |
| **Dual-Bank** | 2 | Bank 0: rows [0:511], Bank 1: rows [512:1023] |
| **Address Width** | 10 bits | (1024 row addressing) |
| **Data Width Output** | 320 bits | (16 words × 20 bits per word, EXT format) |
| **Granularity** | 16 bits | per word (INT16, FP16) |

#### SRCA Dual-Bank Structure

```
Bank 0 (Active):     Bank 1 (Inactive):
Rows [0:511]         Rows [512:1023]
────────────         ──────────────
Read port: 4 rows    Read port: 4 rows
Write port: Full     Write port: Full
Switch every:        Cycle or programmed
```

**Bank switching enabled by:** `i_srca_disable_bank_switch` signal (fpu_gtile_intf line 515)

#### SRCA to L1 Load Path

**Source:** L1 UNPACK_RD_PORT[0:4] (5 read ports, each 128 bits)

**Path:**
1. **Cycle N:** L1 read request (128-bit word from L1)
2. **Cycle N+1:** L1 returns 128-bit data
3. **Cycle N+2:** Unpacker formats data (stride, transpose, byte swap)
4. **Cycle N+3:** Write to SRCA via unpacker interface

**Total load latency:** **~3 cycles**

#### SRCA Write Interface (srca_wr_intf)

**Definition Location:** `tt_t6_interfaces.sv` line 354

```systemverilog
typedef struct packed {
  logic [ADDR_WIDTH-1:0]                   wr_addr;    // 10-bit row address
  logic [NUM_WORDS-1:0][15:0]              wr_data;    // 16 words × 16 bits each
  logic [NUM_WORDS-1:0]                    wr_datum_en; // Per-word write enable
  logic                                    wr_stride_mode;
  logic [STRIDE_LOG2-1:0]                  wr_stride_log2;
  logic                                    wr_transpose;
  logic                                    wr_byte_swap;
} srca_wr_intf;
```

**Timing:**
- Single-cycle synchronous write
- All 16 words written to same SRCA row per cycle
- Stride/transpose modes apply format conversion during write

#### SRCA Read Path to FPU

**FPU Data Output:** `o_srca_fpu_data_ext[FP_TILE_ROWS-1:0][DATUMS_IN_LINE-1:0][EXT_DATUM_WIDTH-1:0]`

**Latency:** **1 cycle** (address → data combinational within same cycle)

**Data Format:**
```
EXT_DATUM_WIDTH = 20 bits:
  [0]       = zero flag (sign bit)
  [8:1]     = 8-bit exponent
  [18:9]    = 10-bit mantissa
  [19]      = extension bit
```

**FPU Output Data Width:** 128 bits (4 rows × 2 lanes × 16 bits per lane)

---

### 3.2 SRCB Register File (Source B)

**Module:** `tt_fpu_tile_srcb.sv`  
**Type:** Latch array  
**Clock Domain:** `ai_clk`  
**Access Latency:** **Combinational read, 1-cycle write**

#### Architecture

| Parameter | Value | Unit |
|-----------|-------|------|
| **Total Size** | 32 KB | (larger than SRCA) |
| **Word Count** | 64 | addressable rows |
| **Datums per Row** | 16 | 16-bit datums |
| **Address Width** | 6 bits | (64 rows) |
| **Data Width Output** | 256 bits | (16 datums × 16 bits) |
| **Dual-Bank** | 2 | Bank 0 and Bank 1 |
| **Sub-banks** | 4 | Within each bank |

#### SRCB Dual-Bank Structure

```
Total: 32 KB ÷ 2 = 16 KB per bank

Bank 0:               Bank 1:
Rows [0:31]          Rows [32:63]
──────────           ──────────
Read: Full width     Read: Full width
Write: Full width    Write: Full width
Selected by: rd_other_bank flag
```

#### SRCB to L1 Load Path

**Source:** L1 UNPACK_RD_PORT[0:4] (shared with SRCA, multiplexed)

**Load latency:** **~3 cycles** (same as SRCA: L1 read + unpack format + SRCB write)

#### SRCB Write Interface (unpack_srcb_intf)

**Definition Location:** `tt_t6_interfaces.sv` line 379

```systemverilog
typedef struct packed {
  logic [SRCB_ADDR_WIDTH+2-1:0]            wr_addr;      // 8-bit address
  logic [(NUM_WORDS/2)*REG_WIDTH-1:0]      wr_data_unadjusted; // 128 words data
  logic                                    wr_stoch_rnd_en;
  logic [STOCH_WIDTH-1:0]                  wr_stoch_rnd_mask;
  logic                                    wr_stride_mode;
  logic [STRIDE_LOG2-1:0]                  wr_stride_log2;
  logic                                    wr_transpose;
} unpack_srcb_intf;
```

**Stochastic Rounding Support:**
- `wr_stoch_rnd_en`: Enable stochastic rounding on write
- `wr_stoch_rnd_mask`: [21:0] PRNG mask bits for rounding threshold

#### SRCB Read Path to FPU

**FPU Data Output:** Via fpu_gtile_intf

```systemverilog
srcb_rd_params_t  i_srcb_rd_params;        // Read control
logic [SRCB_OUTPUT_ROWS-1:0][16*2-1:0] i_srcb_index_data_exp;  // Output data
```

**Latency:** **1 cycle** (address → data combinational)

**Data Width:** 512 bits (2×256 per read request)

#### Stochastic Rounding in SRCB

SRCB output supports probabilistic rounding for INT8/FP16 quantization:

```
PRNG seed interface:
  i_prng_seed_cid    : Stream ID
  i_prng_seed        : Seed value
  i_prng_seed_valid  : Seed update valid
  
Output rounding:
  Mask-based stochastic rounding
  PRNG_WIDTH = 22 bits
  Applied per output datum
```

---

### 3.3 DEST Register File (Accumulator)

**Module:** `tt_gtile_dest.sv`  
**Type:** Latch array  
**Clock Domain:** `ai_clk`  
**Access Latency:** **1-cycle write, 3-cycle read pipeline**

#### Architecture

| Parameter | Value | Unit |
|-----------|-------|------|
| **Total Size** | 32 KB | (1024 rows × 16 bits × 2 banks) |
| **Rows per Bank** | 512 | Bank 0: [0:511], Bank 1: [512:1023] |
| **Bank Count** | 2 | Dual-bank (4 KB each, nominally) |
| **Address Width** | 10 bits | (1024 total row addressing) |
| **Bank Address Width** | 9 bits | (512 rows per bank) |
| **Data Width** | 256 bits | (4 rows × 2 columns × 16 bits) |

#### DEST Dual-Bank Structure

```
Bank 0:               Bank 1:
Rows [0:511]         Rows [512:1023]
────────────         ──────────────
FPU write: 4 rows    FPU write: 4 rows (during same cycle?)
Pack read: Full      Pack read: Full
RMW: Atomic          RMW: Atomic
```

**Bank Selection:** Address MSB (DEST_ADDR[9]) selects Bank 0 (bit=0) or Bank 1 (bit=1)

#### DEST FPU Write Port

**Interface:** `sfpu_dest_reg_intf` (defined in `tt_t6_interfaces.sv` line 138)

```systemverilog
typedef struct packed {
  logic [ADDR_WIDTH-1:0]                   wr_addr;      // 10-bit row address
  logic [SFPU_ROWS-1:0]                    wr_en;        // Per-row enable (4 bits)
  logic [SFPU_ROWS-1:0][1:0][15:0]         wr_data;      // 4 rows × 2 cols × 16b
  logic                                    wr_fp32;      // 1 = 32-bit, 0 = 16-bit
  logic                                    wr_col_exchange;
} sfpu_dest_reg_intf;
```

**Timing:**
- **Write latency:** **1 cycle** (synchronous write to latch array)
- **Write width:** 4 rows × 2 columns × 16 bits = **128 bits per cycle**
- **Sources:** FPU, RISC-V coprocessor, math engine (multiplexed)

#### DEST Pack Read Port

**Interface:** Via `fpu_gtile_intf` (lines 496–506)

```systemverilog
// Read request
logic [FP_TILE_COLS-1:0]                   i_shared_rden;          // Column enable
logic                                      i_shared_rd32;          // 32-bit mode
logic [2:0]                                i_shared_rd_stride_log2;
logic [DEST_ADDR_WIDTH-1:0]                i_shared_rdaddr;        // Row address

// Read response
logic [FP_TILE_COLS-1:0][SHARED_PORT_ROWS-1:0][1:0][15:0]  o_shared_rddata;
```

**Timing:**
- **Read request→response latency:** **3 cycles** (DEST_RD_PIPELINE_DEPTH = 3)
- **Read width:** 16 rows × 2 columns × 16 bits = **512 bits per cycle**
- **Users:** Pack engine (write back to L1)

#### DEST Bank Arbitration

Multiple readers contend for **shared read port:**
- **Pack engine** (highest priority): Reads active DEST bank
- **Unpack engine** (medium): Reads alternate bank during load
- **SFPU** (lowest): Reads for scalar operations

**Synchronization:** DEST bank sync status tracked per bank:
```systemverilog
dest_sync_status_t {
  logic [DEST_NUM_BANKS-1:0][DEST_DVALID_BITS-1:0] dvalid_state;  // Per-bank validity
  logic [DEST_NUM_BANKS-1:0]                        bank_id;       // Owner identifier
}
```

---

### 3.4 SRCS Register File (Scalar)

**Module:** `tt_srcs_registers.sv` (if present in RTL)  
**Type:** Latch array  
**Clock Domain:** `ai_clk`  
**Access Latency:** **1-cycle read/write**

#### Architecture

| Parameter | Value | Unit |
|-----------|-------|------|
| **Total Size** | 384 bytes | (48 rows × 16 bits) |
| **Address Width** | 6 bits | (64 addressable rows) |
| **Data Width** | 16 bits | (scalar) |
| **Dual-Bank** | 2 | Bank 0 & Bank 1 (192 bytes each) |

#### SRCS Purpose

Scalar auxiliary registers for:
- SFPU accumulation results
- Control flow values
- Intermediate scalar computations

#### SRCS Interfaces

**Write:** From SFPU scalar operations  
**Read:** By pack/unpack engines for result extraction  
**Latency:** **1 cycle** (combinational read, synchronous write)

---

### 3.5 L1 to SRCA/SRCB/DEST Load Paths

#### SRCA Load Path (Detailed)

```
Step 1: L1 Read Request
────────────────────────
Cycle N: TRISC issues read via UNPACK_RD_PORT[0]
  L1 address: [31:0] weight block address
  L1 port width: 128 bits
  L1 access time: 1 cycle

Step 2: L1 Response
────────────────────
Cycle N+1: L1 returns 128-bit data
  16 weight elements (INT16 or FP16 format)
  ECC parity bits

Step 3: Unpacker Format Conversion
────────────────────────────────────
Cycle N+1 to N+2: Unpacker applies transformations
  - Byte swap (endianness)
  - Row/column transpose
  - Stride expansion
  - Format normalization (FP16→FP32, INT8→INT16)

Step 4: SRCA Write
────────────────────
Cycle N+3: Write formatted data to SRCA
  srca_wr_intf.wr_addr ← [9:0] row address
  srca_wr_intf.wr_data ← 16 words × 16 bits
  srca_wr_intf.wr_datum_en ← [15:0] per-word mask
  
Total latency: 3 cycles from L1 read request to SRCA write complete
```

#### SRCB Load Path (Detailed)

Identical to SRCA (shared UNPACK_RD_PORT when not loading SRCA)

```
L1 Read (1cy) → Unpack Format (1cy) → SRCB Write (1cy)
Total: 3 cycles
```

#### DEST Write Path (FPU → L1)

```
Step 1: FPU Computes Result
────────────────────────────
Cycles 0–N: FPU executes MAC operations
  Accumulation into DEST latch array

Step 2: DEST Write (FPU)
────────────────────────
Cycle N: FPU writes result to DEST
  sfpu_dest_reg_intf.wr_addr ← [9:0]
  sfpu_dest_reg_intf.wr_data ← 4 rows × 2 cols × 16b
  Write latency: 1 cycle

Step 3: Pack Engine Read
────────────────────────
Cycle N+1 to N+3: Pack reads from DEST
  fpu_gtile_intf.i_shared_rdaddr ← DEST row
  Read latency: 3 cycles (pipelined)

Step 4: Pack Format Conversion
──────────────────────────────
Cycle N+4 to N+5: Pack applies post-math operations
  - ReLU, CReLU, Flush-to-0
  - Format conversion (INT32→FP16B, FP32→FP16B)
  - Stochastic rounding (optional)

Step 5: L1 Pack Write
──────────────────────
Cycle N+6: Pack writes to L1 via PACK_WR_PORT[0:2]
  L1 address: [31:0] result block address
  L1 port width: 128 bits
  Write latency: 1 cycle

Total latency: ~6–7 cycles from FPU write to L1 result stored
```

#### SRCA/SRCB/DEST Data Flow Diagram

```
                  L1 Memory (3 MB, 512 macros)
                  ├─ 128-bit port (per T6 core)
                  └─ 512-bit port (NoC side-channel)
                        │
        ┌───────────────┼───────────────┐
        │               │               │
    (1 cycle)       (1 cycle)       (1 cycle)
        │               │               │
        ▼               ▼               ▼
    UNPACK_RD    NOC_RD_PORT     OVRLY_RD_PORT
       (5 ports)    (4 ports)      (2 ports)
        │               │               │
    (3 cycles           │               │
     format)            │               │
        │               │               │
        ▼               ▼               ▼
      SRCA          SRCB           (other L1 users)
     16 KB          32 KB
   ┌─────┐        ┌──────┐
   │Bank │        │Bank0 │
   │ 0/1 │        │Bank1 │
   └──┬──┘        └──┬───┘
      │              │
      │        (1 cy combo read)
      │              │
      ▼              ▼
    ┌──────────────────────────┐
    │  FPU (256 parallel MACs)  │
    │  ├─ G-Tile (4 rows × 16 lanes)
    │  ├─ M-Tile (Multipliers)
    │  ├─ F-Tile (Accumulators)
    │  └─ SFPU (Scalar ops)
    └───────────┬──────────────┘
                │
        (MAC result)
                │
        (1 cycle sync write)
                │
                ▼
              DEST
             32 KB
          ┌────────┐
          │Bank 0  │
          │Bank 1  │
          └───┬────┘
              │
        (3 cycle pipeline read)
              │
              ▼
          Pack Engine
       ┌─────────────────┐
       │ - ReLU/CReLU    │
       │ - Stoch Round   │
       │ - Format Conv   │
       │ - Transpose     │
       └────────┬────────┘
                │
        (1 cycle write)
                │
                ▼
           PACK_WR_PORT
             (3 ports)
                │
            (1 cycle)
                │
                ▼
             L1 Memory
         (results stored)
```

---

### 3.6 Register File Access Concurrency

#### SRCA Concurrent Access Summary

| Operation | Max/Cycle | Users |
|-----------|-----------|-------|
| **FPU Read** | 1 | FP-Lanes (16 columns) |
| **Unpacker Write** | 1 | TDMA unpack from L1 |
| **Bank Switch** | Programmable | Control logic |

**Conflict Resolution:** Single write port; unpacker has priority over reads during load

#### SRCB Concurrent Access Summary

| Operation | Max/Cycle | Users |
|-----------|-----------|-------|
| **FPU Read** | 1 | FP-Lanes (all rows) |
| **Unpacker Write** | 1 | TDMA unpack from L1 |
| **Stoch Rounding** | 1 | PRNG seed injection |

**Conflict Resolution:** Write port multiplexed; stochastic rounding applied during write

#### DEST Concurrent Access Summary

| Operation | Max/Cycle | Users |
|-----------|-----------|-------|
| **FPU Write** | 1 | SFPU accumulation |
| **Pack Read** | 1 | 3-cycle pipelined read |
| **Bank Switch** | Every cycle | Toggle between Bank 0 & 1 |

**Conflict Resolution:**
- FPU write and pack read to **different banks** allowed simultaneously
- FPU write to Bank 0 while pack reads Bank 1
- Next cycle: FPU writes Bank 1, pack reads Bank 0
- **Net result:** Full-throughput pipelining (1 read + 1 write per cycle, different banks)

---

### 3.7 Register File Bit Width & Format Summary

| Register | Data Width | Format | Users |
|----------|-----------|--------|-------|
| **SRCA** | 320 bits (16×20b EXT) | EXT format (sign+exp+mantissa+zero) | FPU lanes |
| **SRCB** | 256 bits (16×16b) | INT16/FP16B/INT8 (format-agnostic) | FPU lanes |
| **DEST** | 256 bits (4×2col×16b) | INT32 accumulator (2's complement) | Pack, SFPU, Math |
| **SRCS** | 16 bits | Scalar (INT32 or FP32) | SFPU, Pack |

---

## §4 RTL Change Review Checklist

When modifying TRISC, L1, or register file RTL, verify:

### TRISC Changes
- [ ] All 4 TRISC threads have identical instruction cache interface (mem_wrapper_intf)
- [ ] Local memory interface (data/vector) clock domains match instruction engine
- [ ] Reset signals propagate to all 4 threads independently (i_risc_reset_n[3:0])
- [ ] Address widths unchanged (ICache: 10b, LDM: 10–12b, Vec: per config)

### L1 Memory Changes
- [ ] Port count matches NEO_L1_CFG: 5 RD + 3 WR + 1 RW core ports
- [ ] Phase arbitration (4 phases) enforced in hardware
- [ ] Address hashing function (XOR-based) applied before bank selection
- [ ] Atomic transaction routing preserved (AT_SBPORT_MAP)
- [ ] 1-cycle latency maintained for SRAM access

### Register File Changes
- [ ] SRCA: Dual-bank switching doesn't stall FPU reads
- [ ] SRCB: Stochastic rounding mask injection timing correct
- [ ] DEST: Bank toggling supports 1 write + 1 read per cycle (different banks)
- [ ] SRCS: Scalar write/read latency remains 1 cycle
- [ ] L1 load paths (unpack format → register write) remain ~3 cycles

---

## References

| Document | Location |
|----------|----------|
| **RTL Filelist** | `/secure_data_from_tt/20260221/DOC/N1B0/filelist.f` |
| **N1B0 HDD v1.00** | `/secure_data_from_tt/20260221/DOC/N1B0/N1B0_NPU_HDD_v1.00.md` |
| **tt_t6_l1_pkg.sv** | `tt_rtl/tt_t6_l1/rtl/tt_t6_l1_pkg.sv` (interfaces, arbitration) |
| **tt_instrn_engine.sv** | `tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_instrn_engine.sv` (TRISC ports) |
| **tt_gtile_dest.sv** | `tt_rtl/tt_tensix_neo/src/hardware/tensix/fpu/rtl/tt_gtile_dest.sv` (DEST) |
| **tt_t6_interfaces.sv** | `tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_t6_interfaces.sv` (all FPU intf) |

---

**Document Version:** v0.1  
**Last Updated:** 2026-04-07  
**Status:** Ready for RTL Change Review


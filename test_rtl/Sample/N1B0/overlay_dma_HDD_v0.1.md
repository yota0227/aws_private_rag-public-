# Trinity N1B0 — Overlay DMA Engine Hardware Design Document

## Version Table

| Version | Date       | Author        | Changes                          |
|---------|------------|---------------|----------------------------------|
| v0.1    | 2026-03-24 | HW/SW Team    | Initial release                  |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Feature Summary](#2-feature-summary)
3. [Architecture Overview](#3-architecture-overview)
   - 3.1 System Context
   - 3.2 iDMA Engine Internal Architecture
   - 3.3 Data Flow Overview
4. [Module Descriptions](#4-module-descriptions)
   - 4.1 tt_idma_wrapper
   - 4.2 tt_idma_cmd_buffer_frontend
   - 4.3 tt_idma_backend_r_init_rw_obi_top
   - 4.4 tt_idma_legalizer_r_init_rw_obi
   - 4.5 tt_idma_transport_layer_r_init_rw_obi
   - 4.6 tt_idma_dfc_wrapper
   - 4.7 tt_clk_gater
   - Note on TDMA
5. [Key Parameters](#5-key-parameters)
6. [SFR Reference](#6-sfr-reference)
   - 6.1 Cluster Control Registers
   - 6.2 iDMA APB Registers
   - 6.3 ATT (Address Translation Table)
7. [Programming Guide](#7-programming-guide)
8. [Performance Guide](#8-performance-guide)
9. [Appendix A: Supported DFC Formats](#9-appendix-a-supported-dfc-formats)
10. [Appendix B: RISC-V iDMA Instruction Reference](#10-appendix-b-risc-v-idma-instruction-reference)

---

## 1. Overview

The Trinity N1B0 chip contains a 4×5 mesh of tiles. Each Tensix tile (columns X=0–3, rows Y=1–4) includes a per-tile **iDMA engine** (`tt_idma_wrapper`) instantiated inside `tt_overlay_wrapper`. The iDMA engine provides a general-purpose, software-programmable DMA facility that moves data between:

- Local L1 SRAM (within the same tile)
- Remote L1 SRAM (in another tile, via the NoC)
- External DRAM (DDR, via the NOC2AXI bridge at Y=0)

The iDMA engine is distinct from the **TDMA** (Tensor DMA) that lives inside the Tensix compute core. While TDMA is tightly coupled to the FPU datapath and handles tensor tiling, zero-masking, and tilize/untilize operations, iDMA is a standalone AXI/OBI DMA engine visible to the CPU harts and the Dispatch Engine. iDMA is the correct engine to use for bulk data ingestion (e.g., copying image buffers from DRAM to L1) and for non-tensor memory operations.

**Scope of this document:** iDMA architecture, registers, and SW programming guide. TDMA is described in the Tensix Core HDD.

**Target audience:** SW engineers writing firmware, runtime libraries, or device drivers that control the iDMA engine on Trinity N1B0.

---

## 2. Feature Summary

| # | Feature | Details |
|---|---------|---------|
| 1 | 2D scatter-gather DMA | Outer stride loop (num_reps × length bytes per rep) with independent src/dst strides |
| 2 | 24 independent input clients | 8 CPU harts (ROCC) + 2 Dispatch Engine ports + 14 reserved |
| 3 | Dual backends | 2 parallel backends for concurrent transfers |
| 4 | OBI backend (default) | Local L1 SRAM access via OBI protocol |
| 5 | AXI backend (compile-time) | DRAM access via NOC2AXI AXI4 master |
| 6 | Data Format Conversion (DFC) | In-flight format conversion (FP32/FP16/BF16/TF32/FP8/MX*/INT*) |
| 7 | L1 atomic accumulate | 16 accumulate channels; iDMA can write-accumulate into L1 accumulate registers |
| 8 | 32 transaction IDs (TIDs) | Per-TID in-flight tracking, threshold-based IRQ, software-clearable |
| 9 | Page-aligned burst splitting | Legalizer splits transfers at 4KB (configurable) page boundaries |
| 10 | INIT / zero-fill path | Zero-fill destination without reading source |
| 11 | Decoupled read/write | Read and write phases can proceed independently for throughput |
| 12 | Serialized mode | Force in-order execution when ordering is required |
| 13 | Weighted round-robin arbitration | Per-VC weighted arbiter across 24 clients |
| 14 | Clock gating with hysteresis | 7-bit hysteresis counter; gated_l1_clk auto-extends during activity |
| 15 | RISC-V ROCC instruction interface | Custom instructions DMSRC/DMDST/DMCPY/DMSTR/DMREP/DMSTAT from harts |
| 16 | APB register access | All status/config registers accessible via APB from the CPU complex |
| 17 | Virtual channel (VC) selection | Per-transfer VC selector passed through to NoC packet header |
| 18 | CDC-safe frontend/backend boundary | Async FIFO between core_clk (frontend) and gated_l1_clk (backend) |

**NOT in iDMA (see TDMA section):** zero-mask skipping (zmask), exponent-based sparsity pruning, edge masking, tilize/untilize, thread-parallel pack/unpack, BFP hardware decompression, ReLU packing.

---

## 3. Architecture Overview

### 3.1 System Context

```
                        Trinity N1B0 Tile (X=0..3, Y=1..4)
  ┌──────────────────────────────────────────────────────────────┐
  │  tt_overlay_wrapper                                          │
  │                                                              │
  │  ┌──────────────┐   ┌──────────────────────────────────┐    │
  │  │  CPU Complex  │   │       tt_idma_wrapper            │    │
  │  │  (8 harts)    │──►│  iDMA Engine                     │    │
  │  │  ROCC CUSTOM_1│   │                                  │    │
  │  └──────────────┘   └──────────┬────────────┬──────────┘    │
  │                                │ OBI        │ AXI            │
  │  ┌──────────────┐              ▼            ▼                │
  │  │  Dispatch    │   ┌──────────────┐  ┌──────────────┐      │
  │  │  Engine      │──►│  L1 SRAM     │  │  NOC2AXI     │      │
  │  └──────────────┘   │  (768 KB)    │  │  Bridge      │──►DRAM│
  │                     └──────────────┘  └──────────────┘      │
  │                            │                                  │
  │                     ┌──────────────┐                         │
  │                     │  NoC Router  │◄────── Remote tiles      │
  │                     └──────────────┘                         │
  └──────────────────────────────────────────────────────────────┘
```

The iDMA engine sits inside the overlay and is logically adjacent to the L1 SRAM and the NoC fabric. It is not part of the Tensix compute core. CPU harts issue DMA commands via ROCC custom instructions; the Dispatch Engine may also issue DMA via sideband ports (clients 8–9).

### 3.2 iDMA Engine Internal Architecture

```
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  tt_idma_wrapper                                                         │
  │                                                                          │
  │  core_clk domain                   │  gated_l1_clk domain                │
  │                                    │                                      │
  │  ┌──────────────────────────────┐  │  ┌────────────────────────────────┐ │
  │  │ tt_idma_cmd_buffer_frontend  │  │  │ tt_idma_backend_r_init_rw_     │ │
  │  │                              │  │  │ obi_top  [BE #0]               │ │
  │  │  clients[0..23]              │  │  │                                │ │
  │  │  ┌──────────────────────┐   │  │  │  ┌──────────────────────────┐  │ │
  │  │  │ timing slice regs    │   │  │  │  │ metadata FIFO (depth=28) │  │ │
  │  │  │ (per client)         │   │  │  │  └──────────────────────────┘  │ │
  │  │  └──────────────────────┘   │  │  │  ┌──────────────────────────┐  │ │
  │  │  ┌──────────────────────┐   │  │  │  │ tt_idma_backend_r_init_  │  │ │
  │  │  │ tt_arb               │   │  │  │  │ rw_obi (×IDMA_NUM_BE)   │  │ │
  │  │  │ (WRR per VC)         │   │  │  │  │  ┌────────────────────┐  │  │ │
  │  │  └──────────────────────┘   │  │  │  │  │ Legalizer          │  │  │ │
  │  │  ┌──────────────────────┐   │  │  │  │  │ (page alignment,   │  │  │ │
  │  │  │ tt_sync_fifo         │   │  │  │  │  │  burst split)      │  │  │ │
  │  │  │ metadata  depth=42   │   │  │  │  │  └────────────────────┘  │  │ │
  │  │  └──────────────────────┘   │  │  │  │  ┌────────────────────┐  │  │ │
  │  │  ┌──────────────────────┐   │  │  │  │  │ Transport Layer    │  │  │ │
  │  │  │ async payload buf    │◄──┼──┤  │  │  │  idma_obi_read     │  │  │ │
  │  │  │ depth=8, CDC FIFO    │   │  │  │  │  │  idma_init_read    │  │  │ │
  │  │  └──────────────────────┘   │  │  │  │  │  idma_obi_write    │  │  │ │
  │  │  ┌──────────────────────┐   │  │  │  │  │  tt_idma_dfc_wrap  │  │  │ │
  │  │  │ TID completion track │   │  │  │  │  └────────────────────┘  │  │ │
  │  │  │ threshold / IRQ      │   │  │  │  └──────────────────────────┘  │ │
  │  │  └──────────────────────┘   │  │  └────────────────────────────────┘ │
  │  └──────────────────────────────┘  │                                      │
  │                                    │  ┌────────────────────────────────┐ │
  │                                    │  │ tt_idma_backend_r_init_rw_     │ │
  │                                    │  │ obi_top  [BE #1]               │ │
  │                                    │  └────────────────────────────────┘ │
  │                                    │                                      │
  │  i_l1_clk ──► tt_clk_gater ────────────────► gated_l1_clk               │
  │               (HYST_WIDTH=7)       │                                      │
  └──────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Data Flow Overview

**Read path (DRAM → L1):**
```
  CPU hart (ROCC CUSTOM_1)
       │  DMSRC/DMDST/DMCPY instructions
       ▼
  tt_idma_cmd_buffer_frontend
  [core_clk: timing slice → WRR arbiter → metadata FIFO(42) → async payload FIFO(8)]
       │  CDC crossing: core_clk → gated_l1_clk
       ▼
  tt_idma_backend_r_init_rw_obi_top
  [gated_l1_clk: metadata FIFO(28) → legalizer → transport layer]
       │
       ├──[AXI backend]──► NOC2AXI ──► NoC ──► DRAM (SI0–SI3)
       │                        read data ◄──────
       └──[OBI backend]──► L1 SRAM OBI port
             │  write data ──► L1 SRAM write port
             │  (optional: L1 accumulate channels 0–15)
             ▼
         L1 SRAM (768 KB per tile in N1B0)
```

**Write path (L1 → Remote tile or DRAM):**
```
  tt_idma_backend transport layer
       │
       ├── OBI read ──► local L1 SRAM (source data)
       └── OBI/AXI write ──► NoC PUT ──► remote tile L1
                           └── AXI AW/W ──► NOC2AXI ──► DRAM
```

---

## 4. Module Descriptions

### 4.1 tt_idma_wrapper (Top-level)

**File:** `used_in_n1/tt_idma_wrapper.sv`

**Function:** Top-level DMA engine instantiated once per Tensix tile (Y=1–4) inside `tt_overlay_wrapper`. Instantiates the frontend, two backends, and the clock gate. Manages CDC boundary between `core_clk` and `gated_l1_clk`.

**Key ports:**

| Port | Direction | Domain | Description |
|------|-----------|--------|-------------|
| `i_core_clk` | in | core_clk | CPU complex clock |
| `i_l1_clk` | in | noc_clk | L1 SRAM clock (ungated) |
| `gated_l1_clk` | internal | — | Clock gated by tt_clk_gater |
| `i_core_rst_n` | in | — | Active-low reset (core domain) |
| `i_l1_rst_n` | in | — | Active-low reset (L1 domain) |
| `i_idma_req[23:0]` | in | core_clk | idma_flit_t from 24 clients |
| `o_idma_ready[23:0]` | out | core_clk | Back-pressure per client |
| `o_idma_tiles_to_process_irq[31:0]` | out | core_clk | Per-TID IRQ outputs |
| `i_tiles_to_process_clear[31:0]` | in | core_clk | Write 1 to clear IRQ + count |
| `i_l1_clkgt_en` | in | core_clk | Clock gate enable from CLOCK_GATING.IDMA |
| `i_l1_clkgt_hyst` | in | core_clk | Hysteresis count (7-bit) |

**Compile-time parameter:** `IDMA_BE_TYPE_AXI` selects OBI (0, default) or AXI (1) backend.

---

### 4.2 tt_idma_cmd_buffer_frontend (Frontend)

**Function:** Receives DMA descriptors from up to 24 clients, arbitrates using weighted round-robin per virtual channel (VC), buffers metadata and payload through a CDC boundary, and tracks completion per transaction ID (TID).

**Sub-components:**

| Sub-module | Depth / Size | Function |
|------------|-------------|---------|
| Timing slice registers | 1 per client | Pipeline register for timing closure |
| `tt_arb` (WRR) | 24-input | Weighted round-robin arbiter, per-VC |
| `tt_sync_fifo` (metadata) | 42 entries | Holds descriptor metadata in core_clk domain |
| Async payload FIFO | 8 entries | CDC FIFO: core_clk → gated_l1_clk |
| TID completion tracker | 32 TIDs | Counts completions, compares to threshold, fires IRQ |

**Client assignment:**

| Client Index | Source | Notes |
|-------------|--------|-------|
| 0–7 | CPU harts 0–7 | Via ROCC CUSTOM_1 interface |
| 8–9 | Dispatch Engine sideband | DE-initiated tile-wide operations |
| 10–23 | Reserved | Future use |

**TID / IRQ mechanism:**

Each `idma_flit_t` carries a 5-bit `trid` field (TID 0–31). The frontend increments a per-TID counter each time a transfer with that TID completes. When the counter reaches `i_tr_id_thresholds[TID]`, the corresponding bit in `o_idma_tiles_to_process_irq[TID]` is asserted. SW writes 1 to `i_tiles_to_process_clear[TID]` to atomically clear the counter and the IRQ bit.

**Descriptor format (`idma_flit_t`):**
```
  [MSB .............................................................. LSB]
  | l1_accum_cfg_reg (L1 accumulate config) | trid[4:0] | vc[1:0] | payload |
```

where `payload` (`idma_req_t`) contains:
```
  src_addr[63:0]   — source byte address
  dst_addr[63:0]   — destination byte address
  length[21:0]     — transfer size in bytes (max 4 MB)
  src_stride[63:0] — outer dimension source stride (2D mode)
  dst_stride[63:0] — outer dimension destination stride (2D mode)
  num_reps[63:0]   — outer loop count (1 = 1D transfer)
  decouple_rw      — decouple read and write phases
  deburst          — disable AXI burst mode
  serialize        — force in-order serialization
```

---

### 4.3 tt_idma_backend_r_init_rw_obi_top (OBI Backend)

**Function:** Receives arbitrated descriptors from the frontend (in `gated_l1_clk` domain), manages per-backend metadata FIFOs, and instantiates `IDMA_NUM_BE` backend instances that drive OBI or AXI protocol towards L1 SRAM.

Two backend top instances run in parallel (BE #0 and BE #1), allowing two concurrent independent transfers.

**Sub-components:**

| Sub-module | Depth | Function |
|------------|-------|---------|
| Metadata FIFO | 28 entries | Holds L1 accumulate config and in-flight metadata |
| `tt_idma_backend_r_init_rw_obi` | ×IDMA_NUM_BE | Per-backend legalizer + transport layer |

**AXI variant:** When `IDMA_BE_TYPE_AXI == 1`, `tt_idma_backend_r_init_rw_axi_top` is instantiated instead, which interfaces to the tile's AXI master port and ultimately reaches DRAM via the NOC2AXI bridge at Y=0.

---

### 4.4 tt_idma_legalizer_r_init_rw_obi (Legalizer)

**Function:** Transforms an arbitrary `idma_req_t` descriptor into a sequence of legal bus transactions that respect protocol constraints.

**Responsibilities:**

1. **Page boundary detection:** Splits transfers that cross 4KB boundaries into multiple sub-transfers. This prevents a single burst from spanning pages that may be non-contiguous in physical memory.

2. **Burst alignment:** Aligns source and destination addresses to the AXI/OBI burst word size. Generates byte-enable masks for partial-word accesses at start and end of a transfer.

3. **INIT path handling:** When zero-fill mode is requested (no source address, destination fill), generates synthetic read data (all zeros) without issuing source reads.

4. **DFC scale accounting:** When Data Format Conversion is enabled, adjusts transfer byte counts to account for format up-sizing (e.g., INT8→FP32 = ×4) or down-sizing (e.g., FP32→FP8 = ÷4).

5. **2D outer loop:** Generates `num_reps` sequential inner transfers, advancing source and destination addresses by `src_stride` and `dst_stride` respectively after each inner transfer of `length` bytes.

---

### 4.5 tt_idma_transport_layer_r_init_rw_obi (Transport Layer)

**Function:** Executes the legalized transfer sequence by driving OBI (or AXI) read and write channels.

**Sub-modules:**

| Module | Function |
|--------|---------|
| `idma_obi_read` | Issues OBI read requests to L1 SRAM (source path) |
| `idma_init_read` | Generates synthetic zero data (INIT/zero-fill path) |
| `idma_obi_write` | Issues OBI write requests to L1 SRAM (destination path) |
| `tt_idma_dfc_wrapper` | Optional: in-flight data format conversion (when DFCEnable=1) |

**Decoupled read/write:** When `decouple_rw=1`, the read channel and write channel operate independently. The read channel can prefetch ahead of the write channel, improving throughput when the two channels have different latencies (e.g., DRAM read + local L1 write). When `decouple_rw=0`, the write does not proceed until read data is available, preserving strict ordering.

**L1 accumulate path:** When `l1_accum_cfg_reg.enable=1`, the OBI write is redirected to the L1 atomic accumulate channel (0–15) rather than writing directly to the SRAM data array. This implements zero-copy in-place accumulation.

---

### 4.6 tt_idma_dfc_wrapper / tt_t6_com_elem_to_mx_convert_idma (Data Format Converter)

**Function:** Inserted in the transport layer data path when `DFCEnable=1`. Converts data between source format and destination format during transfer, without requiring the CPU to perform format conversion in software.

**Converter:** `tt_t6_com_elem_to_mx_convert_idma`

**Configuration:**
- `WORD_WIDTH = 8` bits (element granularity)
- `MX_BLOCK_SIZE = 8` elements per microscaling block
- Source format and destination format are specified per-transfer via the DFC config field in the descriptor
- Stochastic rounding is supported for narrowing conversions (e.g., FP32→FP8)

**Interface:** Uses `packer_out_intf_misc_info_t` for control signaling between pack and unpack stages.

**Supported format pairs:** Any combination from the 17-format table in Appendix A. Common useful conversions:

| Source | Destination | Use Case |
|--------|-------------|---------|
| FLOAT32 | FLOAT16_B | FP32 parameter → BF16 L1 storage |
| FLOAT32 | FP8P | FP32 → FP8 E4M3 for compressed storage |
| INT16 | INT8 | 16-bit activation → 8-bit L1 storage |
| MXFP8R | FLOAT16 | Decompress MX format to FP16 |

**Note:** DFC in iDMA is a bulk memory conversion. It does NOT perform any arithmetic (no scaling by bias, no normalization). For per-channel scale/bias operations, use the TDMA descale path or SFPU.

**What iDMA DFC does NOT do:**
- Sparsity pruning (zero-skipping) — see TDMA zmask
- Tilize/untilize (row-major ↔ tile layout) — see TDMA
- ReLU application — see TDMA packer

---

### 4.7 tt_clk_gater (Clock Gate)

**Function:** Controls the `gated_l1_clk` that clocks the two backend instances. Saves power when no DMA transfers are active.

**Architecture:**
```
  i_l1_clk ──────────────────────────────────────────► tt_clk_gater
                                                              │
  i_enable ──── CLOCK_GATING.IDMA bit (APB 0x0CC[1]) ───────►│
  i_kick   ──── |{req_valid, resp_valid} from backends ───────►│
  i_busy   ──── o_l1_clkgt_busy from backends ────────────────►│
  i_histeresys ─ i_l1_clkgt_hyst[6:0] (APB 0x0D0) ───────────►│
                                                              │
                                                   gated_l1_clk ──► backends
```

**Behavior:**
- Clock is gated OFF when: `i_enable=1` AND `i_kick=0` AND `i_busy=0` AND hysteresis counter expired
- Clock is forced ON when: `i_enable=0` (disable clock gating = clock always on)
- `i_kick` extends the active period for `2^HYST_WIDTH` cycles from the last activity
- `HYST_WIDTH=7` → clock stays on for up to 128 cycles after last activity

**Recommendation:** Set `CLOCK_GATING.IDMA=1` in production to save power. Set `CLOCK_GATING.IDMA=0` during bring-up and debug.

---

### Note on TDMA (Tensor DMA — separate engine)

The **TDMA** is a different DMA engine inside the Tensix compute core, not part of `tt_idma_wrapper`. It is controlled via dedicated TDMA registers and is tightly coupled to the FPU pack/unpack path.

**TDMA capabilities NOT present in iDMA:**

| Feature | TDMA | iDMA |
|---------|------|------|
| Zero-mask skipping (zmask) | YES | NO |
| Exponent-based sparsity pruning | YES | NO |
| Edge masking (EDGE_MASK0–3) | YES | NO |
| Tilize (row-major → tile layout) | YES | NO |
| Untilize (tile → row-major) | YES | NO |
| 4 parallel pack/unpack threads | YES | NO |
| BFP 4:1 hardware decompression | YES | NO |
| ReLU in packer | YES | NO |
| 3D tensor access | YES | NO (2D max) |
| Decoupled read/write | NO | YES |
| 24-client arbitration | NO | YES |
| DRAM AXI access | NO | YES |

For bulk data movement from DRAM or between tiles, use iDMA. For tensor-format pack/unpack tightly integrated with FPU, use TDMA.

---

## 5. Key Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `IDMA_NUM_MEM_PORTS` | 2 | Number of memory ports (backends) |
| `IDMA_CMD_BUF_NUM_CLIENTS` | 24 | Total client slots (= IDMA_NUM_CLIENTS) |
| `IDMA_PACKET_TAG_TRANSACTION_ID_WIDTH` | 5 | TID field width → 32 TIDs (0–31) |
| `IDMA_MEM_PORT_ID_WIDTH` | 4 | Memory port ID width |
| `IDMA_TRANSFER_LENGTH_WIDTH` | 22 | Transfer length field width → 4 MB max |
| `IDMA_FIFO_DEPTH` | 42 | Frontend metadata FIFO depth |
| `IDMA_PAYLOAD_FIFO_DEPTH` | 8 | CDC async payload FIFO depth |
| `IDMA_L1_ACC_ATOMIC` | 16 | L1 accumulate channel count |
| `NumDim` | 2 | Maximum DMA dimensions (2D scatter-gather) |
| `IDMA_AXI_USER_WIDTH` | 1 | AXI USER sideband width |
| Backend metadata FIFO depth | 28 | Per-backend descriptor FIFO (gated_l1_clk domain) |
| `HYST_WIDTH` | 7 | Clock gate hysteresis counter width (128 cycles) |
| `reg_addr_t` | 9-bit | APB register address space → 512 locations |
| `reg_data_t` | 32-bit | APB register data width |

---

## 6. SFR Reference (SW Register Map)

### 6.1 Cluster Control Registers (cluster_ctrl_apb)

**Base address:** `0x0300_0000`
**Size:** `0x1E4` bytes
**Access:** 64-bit aligned for RESET_VECTOR registers; 32-bit for all others

| Offset | Register Name | Reset | Access | Description |
|--------|---------------|-------|--------|-------------|
| 0x000 | RESET_VECTOR_0 | 0x0 | RW | Hart 0 reset vector bits [57:0] |
| 0x008 | RESET_VECTOR_1 | 0x0 | RW | Hart 1 reset vector bits [57:0] |
| 0x010 | RESET_VECTOR_2 | 0x0 | RW | Hart 2 reset vector bits [57:0] |
| 0x018 | RESET_VECTOR_3 | 0x0 | RW | Hart 3 reset vector bits [57:0] |
| 0x020 | RESET_VECTOR_4 | 0x0 | RW | Hart 4 reset vector bits [57:0] |
| 0x028 | RESET_VECTOR_5 | 0x0 | RW | Hart 5 reset vector bits [57:0] |
| 0x030 | RESET_VECTOR_6 | 0x0 | RW | Hart 6 reset vector bits [57:0] |
| 0x038 | RESET_VECTOR_7 | 0x0 | RW | Hart 7 reset vector bits [57:0] |
| 0x040 | SCRATCH_0 | 0x0 | RW | General-purpose scratch register 0 |
| 0x044 | SCRATCH_1 | 0x0 | RW | General-purpose scratch register 1 |
| ... | SCRATCH_2..30 | 0x0 | RW | General-purpose scratch registers |
| 0xBC | SCRATCH_31 | 0x0 | RW | General-purpose scratch register 31 |
| 0x0C0 | ROCC_MEM_CHICKEN | 0x0 | RW | ROCC memory chicken bits (debug overrides) |
| 0x0C4 | SCATTER_LIST_MAGIC_NUM_LO | 0x0 | RW | Scatter list magic number bits [31:0] |
| 0x0C8 | SCATTER_LIST_MAGIC_NUM_HI | 0x0 | RW | Scatter list magic number bits [63:32] |
| 0x0CC | CLOCK_GATING | 0x0 | RW | Per-unit clock gate enables — see field table below |
| 0x0D0 | CLOCK_GATING_HYST | 0x0 | RW | Clock gate hysteresis count (7-bit, bits [6:0]) |
| 0x0D8 | WB_PC_REG_C0 | 0x0 | RO | Hart 0 writeback PC |
| 0x0E0 | WB_PC_REG_C1 | 0x0 | RO | Hart 1 writeback PC |
| 0x0E8 | WB_PC_REG_C2 | 0x0 | RO | Hart 2 writeback PC |
| 0x0F0 | WB_PC_REG_C3 | 0x0 | RO | Hart 3 writeback PC |
| 0x0F8 | WB_PC_REG_C4 | 0x0 | RO | Hart 4 writeback PC |
| 0x100 | WB_PC_REG_C5 | 0x0 | RO | Hart 5 writeback PC |
| 0x108 | WB_PC_REG_C6 | 0x0 | RO | Hart 6 writeback PC |
| 0x110 | WB_PC_REG_C7 | 0x0 | RO | Hart 7 writeback PC |
| 0x118 | WB_PC_CTRL | 0x0 | RW | Writeback PC capture control |
| 0x11C | ECC_PARITY_CONTROL | 0x0 | RW | Enable ECC/parity for L1 SRAM |
| 0x120 | ECC_PARITY_STATUS | 0x0 | RO | ECC/parity error status flags |
| 0x124 | NOC_SNOOP_TL_MASTER_CFG | 0x0 | RW | TileLink master config for NoC snoop path |
| 0x128 | ASSERTS | 0x0 | RW | Assertion enable bits (simulation/debug) |
| 0x12C | PREFETCHER_CONTROL | 0x0 | RW | Instruction cache prefetcher enable/config |
| 0x130 | BUS_ERROR_UNIT_DATA_C0 | 0x0 | RO | Bus error data for hart 0 |
| 0x138 | BUS_ERROR_UNIT_DATA_C1 | 0x0 | RO | Bus error data for hart 1 |
| 0x140 | BUS_ERROR_UNIT_DATA_C2 | 0x0 | RO | Bus error data for hart 2 |
| 0x148 | BUS_ERROR_UNIT_DATA_C3 | 0x0 | RO | Bus error data for hart 3 |
| 0x150 | BUS_ERROR_UNIT_DATA_C4 | 0x0 | RO | Bus error data for hart 4 |
| 0x158 | BUS_ERROR_UNIT_DATA_C5 | 0x0 | RO | Bus error data for hart 5 |
| 0x160 | BUS_ERROR_UNIT_DATA_C6 | 0x0 | RO | Bus error data for hart 6 |
| 0x168 | BUS_ERROR_UNIT_DATA_C7 | 0x0 | RO | Bus error data for hart 7 |
| 0x170 | L2_DIR_ERRORS_0 | 0x0 | RO | L2 directory error status (bank group 0) |
| 0x174 | L2_DIR_ERRORS_1 | 0x0 | RO | L2 directory error status (bank group 1) |
| 0x178 | L2_DIR_ERRORS_2 | 0x0 | RO | L2 directory error status (bank group 2) |
| 0x17C | L2_DIR_ERRORS_3 | 0x0 | RO | L2 directory error status (bank group 3) |
| 0x180 | L2_BANKS_ERRORS_0 | 0x0 | RO | L2 bank 0 error status |
| 0x184 | L2_BANKS_ERRORS_1 | 0x0 | RO | L2 bank 1 error status |
| ... | L2_BANKS_ERRORS_2..14 | 0x0 | RO | L2 bank error status |
| 0x1BC | L2_BANKS_ERRORS_15 | 0x0 | RO | L2 bank 15 error status |
| 0x1C0 | DEBUG_DMACTIVE | 0x0 | RW | RISC-V Debug Module active flag |
| 0x1C4 | DEBUG_DMACTIVEACK | 0x0 | RO | Debug Module active acknowledge |
| 0x1C8 | DEBUG_SNOOP | 0x0 | RW | Debug snoop bus configuration |
| 0x1CC | OVERLAY_INFO | 0x0 | RO | Overlay version/variant identifier |
| 0x1D0 | SW_RAS | 0x0 | RW | Software Reliability, Availability, Serviceability |
| 0x1D4 | SBUS_RSINK_RESET_FALLBACK | 0x0 | RW | SBUS reset sink fallback configuration |
| 0x1D8 | OVERLAY_CHICKEN_BITS | 0x0 | RW | Overlay debug/workaround chicken bits |
| 0x1DC | L1_ACCESSIBLE_REGION | 0x0 | RW | L1 SRAM accessible region base/size |
| 0x1E0 | L1_REGION_ERROR | 0x0 | RO | L1 region access violation address |

#### CLOCK_GATING Register (0x0CC) — Field Table

| Bit | Field Name | Reset | Description |
|----|-----------|-------|-------------|
| 0 | ROCC | 0 | 1 = enable clock gating for ROCC accelerator interface |
| 1 | IDMA | 0 | 1 = enable clock gating for iDMA engine (gated_l1_clk) |
| 2 | CLUSTER_CTRL | 0 | 1 = enable clock gating for cluster controller APB logic |
| 3 | CONTEXT_SWITCH | 0 | 1 = enable clock gating for context switch unit |
| 4 | LLK_INTF | 0 | 1 = enable clock gating for LLK interface |
| 5 | SNOOP | 0 | 1 = enable clock gating for NoC snoop path |
| 6 | (reserved) | 0 | Reserved, write 0 |
| 7 | L1_FLEX_CLIENT_IDMA | 0 | 1 = enable clock gating for L1 flex-client iDMA port |
| 8 | L1_FLEX_CLIENT_OVERLAY | 0 | 1 = enable clock gating for L1 flex-client overlay port |
| 31:9 | (reserved) | 0 | Reserved |

**Important:** After writing CLOCK_GATING, write the desired hysteresis value to CLOCK_GATING_HYST (0x0D0). The 7-bit value in bits [6:0] specifies the hysteresis count; the clock remains active for `2^value` cycles after the last detected activity.

---

### 6.2 iDMA APB Registers

**Note:** Exact APB byte offsets for iDMA-specific registers are TBD in the RTL and will be documented in a future revision of this HDD. The register names, reset values, and semantics are fully defined below.

**Base address:** iDMA APB sub-bus within tile APB space (consult the system address map for per-tile base offset).

| Register Name | Reset | Access | Width | Description |
|---------------|-------|--------|-------|-------------|
| IDMA_STATUS | 0x0 | RO | 32 | Bit N = 1 if TID N has at least one transfer in-flight. Cleared automatically when all in-flight transfers for that TID complete. |
| IDMA_VC_SPACE[0] | 0x0 | RO | 32 | Available virtual channel slots for backend 0. SW can poll this to avoid overflowing the backend FIFO. |
| IDMA_VC_SPACE[1] | 0x0 | RO | 32 | Available virtual channel slots for backend 1. |
| IDMA_TR_COUNT[0..31] | 0x0 | RO | 32 | Per-TID completion count. Increments by 1 each time a transfer tagged with TID N completes. Saturates at max value. Cleared by writing 1 to IDMA_CLR[N]. |
| IDMA_THRESHOLD[0..31] | 0x0 | RW | 32 | Per-TID IRQ threshold. When IDMA_TR_COUNT[N] >= IDMA_THRESHOLD[N] (and threshold != 0), asserts o_idma_tiles_to_process_irq[N]. |
| IDMA_CLR[0..31] | 0x0 | W1C | 32 | Write 1 to bit N to atomically clear IDMA_TR_COUNT[N] and deassert IRQ[N]. Reading returns current pending clear status. |
| IDMA_CLK_EN | 0x0 | RW | 32 | Bit [0]: iDMA L1 clock gate enable. Mirrors CLOCK_GATING.IDMA. Writing either register has the same effect. |
| IDMA_CLK_HYST | 0x0 | RW | 32 | Bits [6:0]: hysteresis count for gated_l1_clk. Mirrors CLOCK_GATING_HYST. |

**Usage pattern for completion tracking:**

```c
// Setup: set IRQ threshold to 1 transfer per TID
IDMA_THRESHOLD[TID] = 1;

// Issue DMA transfer with trid = TID
issue_dma(src, dst, len, TID);

// Poll for completion
while (!(read(IDMA_TR_COUNT[TID]) >= 1)) { /* spin or yield */ }

// Clear IRQ and counter
write(IDMA_CLR[TID], 1 << TID);
```

---

### 6.3 ATT (Address Translation Table)

The ATT is a hardware lookup table that translates software-visible virtual addresses to NoC physical coordinates. iDMA descriptors can use ATT-translated addresses by forming the source or destination address within the ATT-mapped range.

**ATT base address:** `0x0201_0000`
**ATT size:** `0x3000` bytes (12 KB)

The ATT is programmed by the overlay firmware or the host CPU before issuing DMA transfers that target remote tiles. Each ATT entry maps a (mask, endpoint, routing) tuple. Refer to the Router Address Decoding HDD (router_decode_HDD_v0.5.md, Section 4) for full ATT programming details.

**iDMA + ATT interaction:** When a DMA transfer's source or destination address falls within the ATT-mapped range, the NoC router at the source tile performs the address translation and routes the packet to the correct physical endpoint. iDMA itself has no knowledge of the ATT; it simply issues the address as given in the descriptor.

---

## 7. Programming Guide

### 7.1 Basic 1D Transfer (L1-to-L1, same tile)

A 1D transfer copies `length` bytes from `src_addr` to `dst_addr` within the same tile's L1 SRAM.

```c
#include "idma.h"

// Copy 4096 bytes from offset 0x0 to offset 0x1000 within local L1
void idma_local_copy_1d(void) {
    idma_req_t req = {
        .src_addr  = 0x0000_0000,   // Local L1 base
        .dst_addr  = 0x0000_1000,   // L1 base + 4 KB
        .length    = 4096,          // bytes
        .num_reps  = 1,             // 1D (no outer loop)
        .src_stride = 0,
        .dst_stride = 0,
        .decouple_rw = 0,
        .deburst     = 0,
        .serialize   = 0,
    };

    idma_flit_t flit = {
        .trid    = 0,               // TID 0
        .vc      = 0,               // virtual channel 0
        .payload = req,
        .l1_accum_cfg_reg = { .enable = 0 },
    };

    // Issue via ROCC CUSTOM_1 instruction (hart 0 = client[0])
    // Assembly equivalent:
    //   DMSRC  rs1=src_addr, rs2=0
    //   DMDST  rs1=dst_addr, rs2=0
    //   DMCPY  rs1=length,   rs2=flags
    asm_dmsrc(req.src_addr);
    asm_dmdst(req.dst_addr);
    asm_dmcpy(req.length, /*flags=*/0);

    // Poll completion
    while (asm_dmstat() & DMSTAT_BUSY) { }
}
```

---

### 7.2 DMA from DRAM (ISP/GPU Image Buffer) to L1

This is the primary use case for loading weight tensors or activation buffers from DRAM into the tile's L1.

```c
// DRAM SI0 base: 0x6000_0000
// Load 256 KB from DRAM to local L1 starting at L1 offset 0x0

#define DRAM_SI0_BASE   0x60000000ULL
#define L1_BASE         0x00000000ULL
#define TRANSFER_BYTES  (256 * 1024)    // 256 KB

void idma_dram_to_l1(uint64_t dram_src_offset) {
    // Step 1: Ensure iDMA clock is active
    // CLOCK_GATING.IDMA = 0 (disable gating during setup) or = 1 with hyst
    volatile uint32_t *clk_gate = (uint32_t *)(0x03000000 + 0x0CC);
    *clk_gate |= (1 << 1);  // IDMA bit

    // Step 2: Set IRQ threshold for TID 1
    idma_set_threshold(/*tid=*/1, /*threshold=*/1);

    // Step 3: Issue DMA
    // The AXI backend handles DRAM addresses (0x6xxx_xxxx range)
    // The OBI backend handles L1 addresses (0x0000_xxxx range)
    // iDMA selects backend automatically based on address decode
    asm_dmsrc(DRAM_SI0_BASE + dram_src_offset);
    asm_dmdst(L1_BASE);
    asm_dmstr(/*src_stride=*/0, /*dst_stride=*/0);
    asm_dmrep(/*num_reps=*/1);
    asm_dmcpy(TRANSFER_BYTES, /*flags: trid=1, vc=0*/0x0100);

    // Step 4: Poll TID 1 completion
    while (!(idma_read_tr_count(1) >= 1)) { }
    idma_clear_tid(1);
}
```

**Notes:**
- DRAM is accessed via the NOC2AXI bridge at tile Y=0. The NoC routes the AXI read request from the issuing tile to the correct SI (system interface) based on address decoding.
- For large images (e.g., a 720p FP16 frame = 1280×720×2 = 1.84 MB), issue multiple DMA transfers with different TIDs to pipeline the loads.
- Maximum single transfer: 4 MB (`IDMA_TRANSFER_LENGTH_WIDTH = 22` bits → `2^22 = 4194304` bytes).

---

### 7.3 2D Scatter-Gather Transfer (Strided Matrix Read)

Use 2D mode to read a sub-matrix from a larger matrix stored in DRAM, without copying the entire matrix first.

```c
// Read a 128×64 matrix (FP16, 2 bytes/element) from a 1024×64 DRAM matrix
// Source layout: row-major, row stride = 1024 * 2 = 2048 bytes
// Destination: contiguous in L1

#define ELEM_BYTES      2           // FP16
#define SRC_ROWS        128         // rows to read
#define SRC_COLS        64          // columns to read
#define SRC_ROW_STRIDE  2048        // bytes between rows in DRAM (full-width row)
#define DST_ROW_STRIDE  (64 * 2)    // 128 bytes (packed in L1)

void idma_strided_matrix_read(uint64_t dram_base, uint64_t l1_base) {
    // inner transfer: one row = 64 * 2 = 128 bytes
    // outer loop: SRC_ROWS iterations
    asm_dmsrc(dram_base);
    asm_dmdst(l1_base);
    asm_dmstr(SRC_ROW_STRIDE,   // source: advance full row stride
              DST_ROW_STRIDE);  // destination: advance packed row stride
    asm_dmrep(SRC_ROWS);        // 128 outer iterations
    asm_dmcpy(SRC_COLS * ELEM_BYTES, /*flags=*/0);

    while (asm_dmstat() & DMSTAT_BUSY) { }
}
```

The legalizer internally expands this into `num_reps=128` inner transfers of `length=128 bytes`, advancing `src_addr += src_stride` and `dst_addr += dst_stride` after each inner transfer.

---

### 7.4 Tile-Based vs Non-Tile-Based Access

| Access Pattern | iDMA Mode | Description |
|---------------|-----------|-------------|
| **Non-tile (1D)** | `num_reps=1` | Single contiguous block: bulk memcpy. Use for flat buffers, 1D arrays. |
| **Non-tile (2D)** | `num_reps>1, decouple_rw=0` | Strided row reads from DRAM. Use for sub-matrix extraction, image ROI crop. |
| **Tile-based read** | `num_reps>1, decouple_rw=1` | Prefetch multiple tiles in parallel. Frontend arbiter dispatches both backends concurrently. |

**Tile-based programming pattern:**
```c
// Prefetch two tiles concurrently: send two DMA requests with different TIDs
// Backend #0 and Backend #1 will each handle one transfer simultaneously

void prefetch_two_tiles(void) {
    // TID 0: first tile
    asm_dmsrc(tile0_dram_addr);
    asm_dmdst(l1_tile0_offset);
    asm_dmcpy(TILE_BYTES, FLAGS_TID(0) | FLAGS_DECOUPLE_RW);

    // TID 1: second tile (immediately after — arbiter dispatches to BE #1)
    asm_dmsrc(tile1_dram_addr);
    asm_dmdst(l1_tile1_offset);
    asm_dmcpy(TILE_BYTES, FLAGS_TID(1) | FLAGS_DECOUPLE_RW);

    // Wait for both TIDs
    while (idma_read_tr_count(0) < 1 || idma_read_tr_count(1) < 1) { }
    idma_clear_tid(0);
    idma_clear_tid(1);
}
```

---

### 7.5 Address Translation Using ATT

The ATT allows firmware to use logical addresses that the NoC router translates to physical (x,y) coordinates. This is useful for writing to a remote tile L1 without embedding x/y coordinates in the DMA descriptor.

```c
// Programming the ATT for remote tile (x=2, y=3) L1 base
// NoC address format: bits [75:70]=y_coord, [69:64]=x_coord, [63:0]=local_addr
//
// ATT base: 0x0201_0000, size 0x3000
// Program ATT entry 5 to map logical 0x8000_0000 -> tile(2,3) L1

void att_program_remote_tile(int entry, int x, int y, uint64_t local_addr) {
    uint64_t noc_addr = ((uint64_t)y << 70) | ((uint64_t)x << 64) | local_addr;
    att_write_entry(0x02010000, entry, /*mask=*/0xFFFF_FFFF_0000_0000ULL,
                    /*endpoint=*/noc_addr, /*routing=*/DOR_XY);
}

// Then use the ATT-mapped address as DMA destination
void idma_write_to_remote_tile(void) {
    att_program_remote_tile(5, /*x=*/2, /*y=*/3, L1_BASE);

    asm_dmsrc(local_l1_src);
    asm_dmdst(0x80000000);      // ATT-mapped logical address
    asm_dmcpy(XFER_BYTES, 0);
    while (asm_dmstat() & DMSTAT_BUSY) { }
}
```

Refer to the Router Address Decoding HDD (router_decode_HDD_v0.5.md) for full ATT register layout and programming.

---

### 7.6 Data Format Conversion During Transfer

When `DFCEnable=1` is compiled in, the iDMA transport layer can convert data format during the transfer. This eliminates a separate CPU or SFPU conversion pass.

```c
// Load FP32 weights from DRAM and store as BF16 in L1
// DFC: FLOAT32 -> FLOAT16_B (BFloat16)
// Byte ratio: 4 bytes/element -> 2 bytes/element (2:1 compression)
// Therefore: dst_length = src_length / 2

#define SRC_BYTES (N_ELEMENTS * 4)   // FP32: 4 bytes per element
#define DST_BYTES (N_ELEMENTS * 2)   // BF16: 2 bytes per element

void idma_fp32_to_bf16_dma(uint64_t dram_fp32_src, uint64_t l1_bf16_dst) {
    // Set DFC config in the descriptor (format in idma_req_t DFC extension)
    idma_dfc_req_t dfc_req = {
        .base      = {
            .src_addr   = dram_fp32_src,
            .dst_addr   = l1_bf16_dst,
            .length     = SRC_BYTES,    // source byte count
            .num_reps   = 1,
        },
        .dfc_enable  = 1,
        .src_format  = DFC_FLOAT32,
        .dst_format  = DFC_FLOAT16_B,
        .stoch_round = 0,               // deterministic rounding
    };

    issue_idma_dfc(&dfc_req, /*trid=*/0);
    while (asm_dmstat() & DMSTAT_BUSY) { }
}
```

**Stochastic rounding:**
```c
// For training or when statistical bias matters, enable stochastic rounding
dfc_req.stoch_round = 1;
```

**Format conversion limitations:**
- Block formats (MXFP*, MXINT*) use `MX_BLOCK_SIZE=8` elements per block. The transfer length must be a multiple of 8 elements.
- DFC does not perform arithmetic normalization. For descaling MX formats, the scale factor metadata must be stored separately.

---

### 7.7 L1 Accumulate (Zero-Copy Partial Sum)

The L1 accumulate feature allows iDMA to accumulate incoming data into one of 16 L1 accumulate channels atomically, rather than overwriting the destination. This is useful for multi-tile reduction operations.

```c
// Accumulate data from a remote tile's L1 into local accumulate channel 3
// Source: remote tile (x=1, y=2) L1 offset 0x0
// Destination: local L1 accumulate channel 3

void idma_accumulate_from_remote(void) {
    idma_flit_t flit = {
        .trid = 2,
        .vc   = 0,
        .l1_accum_cfg_reg = {
            .enable  = 1,
            .channel = 3,           // channel 0–15
        },
        .payload = {
            .src_addr    = remote_tile_noc_addr(1, 2, L1_BASE),
            .dst_addr    = L1_ACC_CHANNEL_ADDR(3),
            .length      = PARTIAL_SUM_BYTES,
            .num_reps    = 1,
            .decouple_rw = 1,       // allow read prefetch
        },
    };

    issue_idma_flit(&flit);
    while (!(idma_read_tr_count(2) >= 1)) { }
    idma_clear_tid(2);

    // Read result from L1 accumulate register
    uint32_t *result = (uint32_t *)L1_ACC_CHANNEL_ADDR(3);
    // result[] now contains the accumulated sum
}
```

**Accumulate channel addressing:**
- `IDMA_L1_ACC_ATOMIC = 16` channels
- Each channel is a separate accumulate register in L1 SRAM
- Channel N address = L1 accumulate register bank base + N × element_stride
- Accumulate operation is atomic relative to other iDMA writes

---

### 7.8 Zero-Copy Memory Operations

"Zero-copy" in this context means performing accumulation or format conversion as a side effect of the DMA transfer itself, so that data arrives in L1 in its final form and does not require a separate processing pass.

**Pattern 1: In-place accumulate**
```c
// All-reduce: each tile receives partial sums from 3 other tiles,
// accumulating into the same L1 accumulate channel

for (int src_tile = 0; src_tile < 3; src_tile++) {
    idma_flit_t flit = {
        .trid = src_tile,
        .l1_accum_cfg_reg = { .enable = 1, .channel = 0 },
        .payload = {
            .src_addr = remote_noc_addr(src_x[src_tile], src_y[src_tile], 0),
            .dst_addr = L1_ACC_CHANNEL_ADDR(0),
            .length   = PARTIAL_BYTES,
            .num_reps = 1,
        },
    };
    issue_idma_flit(&flit);
}

// Wait for all 3 TIDs
for (int t = 0; t < 3; t++) {
    while (!(idma_read_tr_count(t) >= 1)) { }
    idma_clear_tid(t);
}
// L1 acc channel 0 now holds sum of all 4 tiles' partial sums
```

**Pattern 2: Format-converted load (DRAM FP32 → L1 BF16)**
```c
// Weight loading with in-flight conversion: no separate format pass needed
idma_dfc_load(DRAM_WEIGHT_ADDR, L1_WEIGHT_ADDR,
              DFC_FLOAT32, DFC_FLOAT16_B, WEIGHT_BYTES);
// L1 now contains BF16 weights; no CPU cycles spent on conversion
```

**Pattern 3: Zero-fill (INIT path)**
```c
// Clear L1 tile accumulator to zero before accumulation begins
idma_req_t zero_req = {
    .src_addr  = 0,           // unused in INIT mode
    .dst_addr  = L1_ACCUM_BASE,
    .length    = ACCUM_BYTES,
    .num_reps  = 1,
    // INIT flag tells legalizer to use idma_init_read (zero-fill)
    // rather than issuing actual source reads
};
issue_idma_init(&zero_req, /*trid=*/0);
while (!(idma_read_tr_count(0) >= 1)) { }
idma_clear_tid(0);
```

---

### 7.9 Multi-Client Pipelining

The 24-client frontend with dual backends enables multiple CPU harts and the Dispatch Engine to issue DMA commands concurrently. The weighted round-robin arbiter ensures fairness across VCs.

**Best practices:**

1. **Use distinct TIDs per active stream.** With 32 TIDs, you can track up to 32 independent in-flight DMA streams simultaneously.

2. **Saturate both backends.** Issue at least 2 concurrent transfers (one per backend) to maximize throughput. The arbiter assigns transfers to backends in round-robin order.

3. **Use VC to prioritize.** Assign higher-priority transfers to lower VC numbers if the arbiter is configured with asymmetric weights.

4. **Don't poll: use IRQ thresholds.** Set `IDMA_THRESHOLD[TID] = N` and let the IRQ wake the hart when N transfers complete. This frees the hart to issue more work.

```c
// Pipeline: issue K transfers, handle completions asynchronously

#define PIPELINE_DEPTH  8   // inflight transfers

void idma_pipelined_load(uint64_t *dram_srcs, uint64_t *l1_dsts, int N) {
    int issued = 0, completed = 0;

    // Set IRQ threshold for TID 0: fire after every 1 completion
    idma_set_threshold(0, 1);

    while (completed < N) {
        // Fill pipeline
        while (issued < N && (issued - completed) < PIPELINE_DEPTH) {
            asm_dmsrc(dram_srcs[issued]);
            asm_dmdst(l1_dsts[issued]);
            asm_dmcpy(TILE_BYTES, FLAGS_TID(0));
            issued++;
        }

        // Wait for next completion
        while (!(idma_read_tr_count(0) >= 1)) { /* wfi or yield */ }
        idma_clear_tid(0);
        completed++;
    }
}
```

---

### 7.10 Sparsity and Zero Handling

**iDMA does NOT support zero-skipping.** iDMA transfers all bytes in the specified range regardless of their value.

For sparsity-aware data movement, use the TDMA engine (inside the Tensix core) which supports:
- `zmask`: skip Z-planes where all elements are zero
- Exponent threshold pruning: skip elements where `|exp| < threshold`
- These are controlled via TDMA configuration registers (see Tensix Core HDD)

**What iDMA can do for sparse workloads:**
- Load a compressed (already-zeroed) sparse tensor from DRAM into L1 in one transfer
- Use the INIT (zero-fill) path to pre-clear an L1 accumulation buffer before TDMA writes non-zero values
- Use DFC to convert a dense tensor to a narrower format (e.g., FP32→INT8) which may have more implicit zeros due to quantization clipping — but iDMA does not skip those zeros

---

### 7.11 Completion Tracking and IRQ

The iDMA engine supports per-TID completion counting and threshold-based interrupts.

**TID lifecycle:**
```
  Issue transfer (trid=N)
       │
       ▼
  TID N in-flight: IDMA_STATUS[N] = 1
       │
       ▼
  Transfer completes
       │
       ▼
  IDMA_TR_COUNT[N]++
  If IDMA_TR_COUNT[N] >= IDMA_THRESHOLD[N]:
      o_idma_tiles_to_process_irq[N] = 1
       │
       ▼
  SW writes IDMA_CLR[N] = 1
       │
       ▼
  IDMA_TR_COUNT[N] = 0, IRQ[N] = 0
```

**Polling vs interrupt modes:**

```c
// === POLLING MODE ===
void wait_tid_poll(int tid) {
    while (idma_read_tr_count(tid) < 1) { /* spin */ }
    idma_clear_tid(tid);
}

// === INTERRUPT MODE ===
// Setup: register ISR for iDMA IRQ[TID]
void idma_irq_setup(int tid, int threshold) {
    idma_set_threshold(tid, threshold);
    register_irq_handler(IDMA_IRQ_BASE + tid, idma_completion_isr);
    enable_irq(IDMA_IRQ_BASE + tid);
}

void idma_completion_isr(int tid) {
    idma_clear_tid(tid);
    signal_completion(tid);
}

// === BATCH IRQ (fire after N completions) ===
void idma_batch_setup(int tid, int batch_size) {
    idma_set_threshold(tid, batch_size);
    // IRQ fires after batch_size transfers with trid=tid have completed
}
```

---

## 8. Performance Guide

### 8.1 Clock Gating Configuration

Clock gating saves power but can add latency when the first transfer arrives after the clock has gated off.

| Scenario | Recommendation |
|----------|---------------|
| Continuous DMA (training loop) | `CLOCK_GATING.IDMA = 1`, `HYST = 0x7F` (max hysteresis) |
| Burst DMA (infrequent loads) | `CLOCK_GATING.IDMA = 1`, `HYST = 0x20` (32-cycle window) |
| Bring-up / debug | `CLOCK_GATING.IDMA = 0` (clock always on) |
| Ultra-low-power idle | `CLOCK_GATING.IDMA = 1`, `HYST = 0x00` (gate immediately) |

```c
// Enable iDMA clock gating with 64-cycle hysteresis
volatile uint32_t *clk_gate = (uint32_t *)(CLUSTER_CTRL_BASE + 0x0CC);
volatile uint32_t *clk_hyst = (uint32_t *)(CLUSTER_CTRL_BASE + 0x0D0);

*clk_gate |= (1 << 1);          // CLOCK_GATING.IDMA = 1
*clk_hyst  = 0x06;              // 2^6 = 64 cycles hysteresis
```

---

### 8.2 In-Flight Transaction Depth

The system can sustain the following number of descriptors in-flight simultaneously:

| Stage | Capacity | Domain |
|-------|----------|--------|
| Frontend timing slice | 1 per client × 24 = 24 | core_clk |
| Frontend metadata FIFO | 42 entries | core_clk |
| CDC async payload FIFO | 8 entries | crossing |
| Per-backend metadata FIFO | 28 entries × 2 = 56 | gated_l1_clk |
| Total TIDs | 32 | — |

**Effective pipeline depth:** With 2 backends, up to 2 transfers execute in parallel. Up to 8 transfers can be queued in the CDC FIFO awaiting backend pickup. Issuing more than 8+2=10 concurrent transfers per client will cause backpressure (`o_idma_ready` deasserted).

---

### 8.3 Backend Selection (OBI vs AXI)

The backend type is a **compile-time** parameter (`IDMA_BE_TYPE_AXI`). In N1B0 production silicon, this is fixed per tile. Check your chip configuration:

| Backend | Target | Latency | Bandwidth |
|---------|--------|---------|-----------|
| OBI (`IDMA_BE_TYPE_AXI=0`) | Local L1 SRAM | 1–4 cycles | Limited by OBI bus width |
| AXI (`IDMA_BE_TYPE_AXI=1`) | DRAM via NOC2AXI | 50–200+ cycles | Limited by NoC and DRAM |

For **DRAM→L1 transfers**, use `decouple_rw=1` to allow read prefetching to proceed ahead of the write. This hides DRAM latency and improves throughput.

For **L1→L1** (same tile), `decouple_rw=0` is fine because OBI latency is predictable.

---

### 8.4 2D Transfer Efficiency

2D transfers (num_reps > 1) avoid the overhead of issuing multiple 1D descriptors from the CPU. The legalizer generates the sub-transfer sequence internally.

**Break-even analysis:**
- CPU overhead per DMCPY instruction: ~5 cycles
- At 5-cycle overhead per rep, for num_reps=128: 640 cycles saved by using 2D vs 128 individual 1D descriptors
- Additionally, 2D mode eliminates 127 round-trips through the CDC FIFO

**Recommendation:** Use 2D whenever `num_reps >= 4`. For num_reps < 4, the difference is negligible.

---

### 8.5 L1 Bandwidth Estimation

L1 SRAM in N1B0: 768 KB per tile, organized as 3072 macros × 128 bits (16 bytes) per macro.

iDMA write bandwidth (OBI port) is limited by:
1. OBI bus width: 128 bits/cycle at `gated_l1_clk`
2. L1 bank conflicts: 2D accesses with stride = L1 bank size will cause conflicts; choose strides that are non-power-of-2 bank-size multiples

**Estimated peak iDMA throughput:**
```
  gated_l1_clk ≈ noc_clk (500–800 MHz, platform-dependent)
  OBI bus width = 128 bits = 16 bytes
  Peak write BW = 16 bytes × clock_freq
  At 800 MHz: 12.8 GB/s per backend
  Dual backends: up to 25.6 GB/s total (bank-conflict-free)
```

**DRAM read bandwidth:**
```
  NOC flit width = 512 bits = 64 bytes
  NOC clock = noc_clk
  DRAM latency ≈ 100–200 ns
  Sustained BW depends on DRAM controller and NoC congestion
  Practical: use AXI burst (deburst=0) for best DRAM throughput
```

---

## 9. Appendix A: Supported DFC Formats

The following format codes are defined in `tt_idma_dfc_pkg.sv`. All conversions between any two formats in this table are supported by `tt_idma_dfc_wrapper`.

| Code | Format Name | Exponent Bits | Mantissa Bits | Total Bits | Notes |
|------|-------------|---------------|---------------|------------|-------|
| `DFC_FLOAT32` | IEEE 754 FP32 | 8 | 23 | 32 | Standard single precision |
| `DFC_FLOAT16` | IEEE 754 FP16 | 5 | 10 | 16 | Standard half precision (E5M10) |
| `DFC_FLOAT16_B` | BFloat16 | 8 | 7 | 16 | Google BF16 (E8M7) |
| `DFC_TF32` | TensorFloat-32 | 8 | 10 | 19 | NVIDIA TF32 (E8M10) |
| `DFC_FP8R` | FP8 E5M2 | 5 | 2 | 8 | OCP FP8, round mode |
| `DFC_FP8P` | FP8 E4M3 | 4 | 3 | 8 | OCP FP8, packed mode |
| `DFC_MXFP8R` | MX FP8 E5M2 | 5 | 2 | 8 | OCP MX, block shared exp |
| `DFC_MXFP8P` | MX FP8 E4M3 | 4 | 3 | 8 | OCP MX, block shared exp |
| `DFC_MXFP6R` | MX FP6 E3M2 | 3 | 2 | 6 | OCP MX FP6 |
| `DFC_MXFP6P` | MX FP6 E2M3 | 2 | 3 | 6 | OCP MX FP6 |
| `DFC_MXFP4` | MX FP4 E2M1 | 2 | 1 | 4 | OCP MX FP4 |
| `DFC_INT8` | INT8 | — | — | 8 | Signed 8-bit integer |
| `DFC_INT16` | INT16 | — | — | 16 | Signed 16-bit integer |
| `DFC_INT32` | INT32 | — | — | 32 | Signed 32-bit integer |
| `DFC_MXINT8` | MX INT8 | — | — | 8 | Microscaling INT8 (block exp) |
| `DFC_MXINT4` | MX INT4 | — | — | 4 | Microscaling INT4 |
| `DFC_MXINT2` | MX INT2 | — | — | 2 | Microscaling INT2 |

**Configuration parameters:**
- `WORD_WIDTH = 8` bits (element granularity in the converter)
- `MX_BLOCK_SIZE = 8` elements per microscaling block

**MX format note:** Microscaling (MX) formats use a shared block exponent for every block of 8 elements. The block exponent is stored as metadata alongside the mantissa elements. When converting MX → floating-point, the DFC reads the block exponent and applies it. When converting floating-point → MX, the DFC computes the block exponent from the max exponent in each group of 8 elements.

**Stochastic rounding:** Available for all narrowing conversions (e.g., FP32 → FP8, INT16 → INT8). Enabled via `stoch_round=1` in the DFC descriptor field. Uses hardware LFSR seeded per-block.

---

## 10. Appendix B: RISC-V iDMA Instruction Reference

The iDMA engine exposes a RISC-V ROCC (Rocket Custom Co-processor) interface using the `CUSTOM_1` opcode with `funct7=0x2B`. CPU harts 0–7 each have a dedicated client port (clients 0–7) to the iDMA frontend.

### Instruction Set

| Mnemonic | funct3 | Operands | Description |
|----------|--------|----------|-------------|
| `DMSRC` | 0x0 | rs1=src_addr_lo, rs2=src_addr_hi | Set DMA source address. 64-bit address split across rs1 (low 32) and rs2 (high 32). On RV64: rs1 = full 64-bit address, rs2 = 0. |
| `DMDST` | 0x1 | rs1=dst_addr_lo, rs2=dst_addr_hi | Set DMA destination address. Same encoding as DMSRC. |
| `DMCPYI` | 0x2 | rs1=length, imm12=flags | Immediate-mode copy: length in rs1, flags in 12-bit immediate. Issues transfer immediately. |
| `DMCPY` | 0x3 | rs1=length, rs2=flags | Register-mode copy: length in rs1, flags in rs2. Issues transfer. |
| `DMSTATI` | 0x4 | rd=status, imm12=field | Poll status: reads iDMA status field specified by imm12 into rd. |
| `DMSTAT` | 0x5 | rd=status, rs1=field | Poll status: reads iDMA status field specified by rs1 into rd. |
| `DMSTR` | 0x6 | rs1=src_stride, rs2=dst_stride | Set outer-dimension strides for 2D mode. Call before DMCPY. |
| `DMREP` | 0x7 | rs1=num_reps | Set outer loop repetition count for 2D mode. Call before DMCPY. |

### Flags Field Encoding (DMCPY rs2 / DMCPYI imm12)

| Bits | Field | Description |
|------|-------|-------------|
| [4:0] | trid | Transaction ID (0–31) |
| [6:5] | vc | Virtual channel selector (0–3) |
| [7] | decouple_rw | 1 = decouple read and write phases |
| [8] | deburst | 1 = disable AXI burst (single-beat transfers only) |
| [9] | serialize | 1 = force in-order serialization |
| [11:10] | (reserved) | Write 0 |

### DMSTAT Status Fields (imm12/rs1 encoding)

| Value | Field | Description |
|-------|-------|-------------|
| 0x0 | DMSTAT_BUSY | 1 if any transfer is in-flight |
| 0x1 | DMSTAT_READY | 1 if frontend can accept new descriptor |
| 0x2 | DMSTAT_STATUS | IDMA_STATUS[31:0] — in-flight TID bitmap |
| 0x3–N | DMSTAT_TR_COUNT_N | IDMA_TR_COUNT[N] for TID N |

### Macro Usage Example

```c
// Convenience macros (C/assembly wrappers)

static inline void asm_dmsrc(uint64_t src) {
    asm volatile ("DMSRC %0, zero" :: "r"(src));
}

static inline void asm_dmdst(uint64_t dst) {
    asm volatile ("DMDST %0, zero" :: "r"(dst));
}

static inline void asm_dmstr(uint64_t src_stride, uint64_t dst_stride) {
    asm volatile ("DMSTR %0, %1" :: "r"(src_stride), "r"(dst_stride));
}

static inline void asm_dmrep(uint64_t num_reps) {
    asm volatile ("DMREP %0" :: "r"(num_reps));
}

static inline void asm_dmcpy(uint64_t length, uint64_t flags) {
    asm volatile ("DMCPY zero, %0, %1" :: "r"(length), "r"(flags));
}

static inline uint64_t asm_dmstat(void) {
    uint64_t status;
    asm volatile ("DMSTATI %0, 0" : "=r"(status));
    return status;
}

// Full 2D DMA transfer helper
void dma_2d(uint64_t src, uint64_t dst,
            uint64_t length, uint64_t num_reps,
            uint64_t src_stride, uint64_t dst_stride,
            int trid, int vc)
{
    uint64_t flags = (trid & 0x1F) | ((vc & 0x3) << 5);
    asm_dmsrc(src);
    asm_dmdst(dst);
    asm_dmstr(src_stride, dst_stride);
    asm_dmrep(num_reps);
    asm_dmcpy(length, flags);
}
```

### Instruction Ordering Notes

1. `DMSRC`, `DMDST`, `DMSTR`, and `DMREP` set per-hart shadow registers in the iDMA frontend. These are not committed until `DMCPY` is issued.
2. `DMCPY` is the commit instruction: it atomically captures the shadow registers and enqueues the descriptor into the client FIFO.
3. Multiple harts may issue concurrently. The WRR arbiter handles conflicts.
4. `DMSTAT` with `DMSTAT_BUSY` returns 1 if *any* transfer from this hart is in-flight. For fine-grained tracking, use TID-based `DMSTAT_TR_COUNT_N` queries or the APB `IDMA_TR_COUNT[]` registers.

---

*End of document — Trinity N1B0 Overlay DMA Engine HDD v0.1*

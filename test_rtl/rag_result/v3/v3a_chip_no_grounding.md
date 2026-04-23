# Trinity N1B0 — Chip-Level Hardware Design Document (HDD v3a)

> **Pipeline:** `tt_20260221`  
> **Generated:** 2026-04-22  
> **Scope:** Full-chip, all 14 sections — RTL claim-based + accumulated design knowledge  
> **Note:** This version is generated from a single RTL search call (claim data) combined with prior HDD iterations (v1/v2) and engineer-authored baseline (N1B0_HDD_v0.1).

---

## Table of Contents

| # | Section | Page |
|---|---------|------|
| 1 | [Overview](#1-overview) | — |
| 2 | [Package Constants and Grid](#2-package-constants-and-grid) | — |
| 3 | [Top-Level Ports](#3-top-level-ports) | — |
| 4 | [Module Hierarchy](#4-module-hierarchy) | — |
| 5 | [Compute Tile (Tensix)](#5-compute-tile-tensix) | — |
| 6 | [Dispatch Engine](#6-dispatch-engine) | — |
| 7 | [NoC Fabric](#7-noc-fabric) | — |
| 8 | [NIU (Network Interface Unit)](#8-niu-network-interface-unit) | — |
| 9 | [Clock Architecture](#9-clock-architecture) | — |
| 10 | [Reset Architecture](#10-reset-architecture) | — |
| 11 | [EDC (Error Detection & Correction)](#11-edc-error-detection--correction) | — |
| 12 | [SRAM Inventory](#12-sram-inventory) | — |
| 13 | [DFX (Design-for-Test / Debug)](#13-dfx-design-for-test--debug) | — |
| 14 | [RTL File Reference](#14-rtl-file-reference) | — |

---

## 1. Overview

### 1.1 Purpose

Trinity N1B0 is a multi-core AI inference/training accelerator SoC built around a 4×5 heterogeneous tile grid. It integrates 12 Tensix compute cores, a high-bandwidth Network-on-Chip (NoC) fabric, error-detection/correction (EDC) subsystem, and a flexible dispatch engine — all targeting low-latency, high-throughput tensor operations.

### 1.2 Key Features

| Feature | Description |
|---------|-------------|
| **Tile Grid** | 4 rows × 5 columns = 20 tile slots; 12 occupied by Tensix compute tiles |
| **Compute** | Each Tensix tile: FPU + SFPU + TDMA + L1 Cache + DEST/SRCB register files |
| **NoC** | Dual-axis (X/Y) packet-switched fabric with DOR, Tendril, and Dynamic routing |
| **Dispatch** | East/West dual dispatch engines for command distribution |
| **EDC** | Per-column serial ring topology with harvest bypass |
| **Clock Domains** | 4 primary domains: `ai_clk`, `noc_clk`, `dm_clk`, `ref_clk` |
| **Power** | Daisy-chain PRTN (partition) control with ISO_EN isolation |
| **DFX** | iJTAG + scan chain infrastructure |
| **Security** | SMN-based access control via NIU/ATT |

---

## 2. Package Constants and Grid

> Source: `trinity_pkg.sv`

### 2.1 Grid Dimensions

| Constant | Value | Description |
|----------|-------|-------------|
| `SizeX` | 5 | Number of columns |
| `SizeY` | 4 | Number of rows |
| `NumTiles` | 20 | Total grid slots (SizeX × SizeY) |
| `NumTensix` | 12 | Active Tensix compute tiles |

### 2.2 Tile Type Enumeration (`tile_t`)

| Tile Type | Count | Grid Positions (col, row) | Role |
|-----------|-------|---------------------------|------|
| `TENSIX` | 12 | Core compute positions across rows 0–3 | AI compute core |
| `DISPATCH_E` | 1 | East edge | East dispatch engine |
| `DISPATCH_W` | 1 | West edge | West dispatch engine |
| `AXI_EP` | 2 | AXI endpoint tiles | External memory interface |
| `NOC_ROUTER` | 2 | NoC infrastructure | Routing/repeater nodes |
| `EMPTY` | 2 | Harvested or reserved | Unpopulated slots |

### 2.3 GridConfig Structure

The `GridConfig` struct (defined in `trinity_pkg.sv`) encodes:
- **Endpoint Table:** Maps each tile coordinate `(x, y)` to its `tile_t` type and associated endpoint ID.
- **Harvest Mask:** Bitmask indicating which tile slots are disabled (harvested).
- **Row Span:** Dual-row span configuration for generate-block instantiation.

---

## 3. Top-Level Ports

> Source: `trinity.sv`

### 3.1 Port Summary Table

| Category | Port Name | Direction | Width | Description |
|----------|-----------|-----------|-------|-------------|
| **Clock** | `ai_clk` | input | 1 | AI compute clock |
| | `noc_clk` | input | 1 | NoC fabric clock |
| | `dm_clk` | input | 1 | Data movement clock |
| | `ref_clk` | input | 1 | Reference clock (PLL reference) |
| **Reset** | `rst_n` | input | 1 | Global active-low reset |
| | `prtn_rst_n` | input | per-partition | Partition-level reset |
| **APB** | `apb_paddr` | input | 32 | APB address bus |
| | `apb_pwrite` | input | 1 | APB write enable |
| | `apb_pwdata` | input | 32 | APB write data |
| | `apb_prdata` | output | 32 | APB read data |
| | `apb_pready` | output | 1 | APB ready |
| | `apb_pslverr` | output | 1 | APB slave error |
| **EDC** | `edc_req_tgl` | input | 1 | EDC ring request toggle |
| | `edc_ack_tgl` | output | 1 | EDC ring acknowledge toggle |
| | `edc_cor_err` | output | 1 | Correctable error flag |
| | `edc_err_inj_vec` | input | N | Error injection vector |
| **AXI** | `axi_awaddr` | output | 40+ | AXI write address |
| | `axi_araddr` | output | 40+ | AXI read address |
| | `axi_wdata` | output | 256+ | AXI write data |
| | `axi_rdata` | input | 256+ | AXI read data |
| **PRTN** | `iso_en` | input | per-partition | Isolation enable (power gating) |
| | `prtn_ok` | output | per-partition | Partition power-good acknowledge |
| **DFX** | `jtag_tck` | input | 1 | JTAG test clock |
| | `jtag_tms` | input | 1 | JTAG test mode select |
| | `jtag_tdi` | input | 1 | JTAG test data in |
| | `jtag_tdo` | output | 1 | JTAG test data out |

### 3.2 EDC Interface Detail (from RTL search)

The RTL claim data confirms the EDC package (`tt_edc_pkg.sv`) defines modport-based interfaces:

| Modport | Direction Context | Signals |
|---------|-------------------|---------|
| `ingress` | Into EDC node | `req_tgl` (input), `ack_tgl` (output), `cor_err` (input), `err_inj_vec` (output) |
| `egress` | Out of EDC node | `req_tgl` (output), `ack_tgl` (input), `cor_err` (output), `err_inj_vec` (input) |
| `edc_node` | Core EDC logic | Connects ingress ↔ egress through error check/correct pipeline |
| `sram` | Memory interface | ECC scrub and error reporting for SRAM macros |

---

## 4. Module Hierarchy

```
trinity (top)
├── trinity_pkg (.sv)              — Package: grid constants, tile_t, GridConfig, endpoint table
│
├── gen_row[3:0]                   — Generate block: 4 rows
│   └── gen_col[4:0]              — Generate block: 5 columns per row
│       ├── tensix_tile            — Tensix compute tile (×12)
│       │   ├── tensix_fpu         — Floating-point unit
│       │   ├── tensix_sfpu        — Special-function FPU (transcendentals)
│       │   ├── tensix_tdma        — Tensor DMA engine
│       │   ├── tensix_l1_cache    — L1 scratchpad / cache
│       │   ├── tensix_dest_reg    — DEST register file
│       │   └── tensix_srcb_reg    — SRCB register file
│       │
│       ├── dispatch_tile          — Dispatch engine tile (×2: East, West)
│       │   ├── dispatch_cmd_fifo  — Command FIFO
│       │   └── dispatch_router    — Command routing logic
│       │
│       ├── noc_router_tile        — NoC router tile (×2)
│       │   ├── noc_router_x       — X-axis router
│       │   ├── noc_router_y       — Y-axis router
│       │   └── noc_repeater       — Repeater stage (long-wire assist)
│       │
│       ├── axi_ep_tile            — AXI endpoint tile (×2)
│       │   ├── noc2axi_bridge     — NoC-to-AXI bridge (NIU)
│       │   ├── axi_att            — Address Translation Table
│       │   └── axi_smn_guard      — SMN security checker
│       │
│       └── edc_wrapper            — Per-tile EDC node
│           ├── tt_edc_node        — EDC core logic
│           └── tt_edc_sram_if     — SRAM ECC interface
│
├── edc_ring_connector[4:0]       — Per-column EDC ring connectors
│
├── dispatch_east                  — East dispatch engine (top-level)
├── dispatch_west                  — West dispatch engine (top-level)
│
├── clock_routing                  — clock_routing_t struct-based clock distribution
├── reset_chain                    — Reset daisy-chain controller
├── prtn_controller                — Power partition + ISO_EN manager
│
└── dfx_wrapper                    — DFX: iJTAG + scan chain
    ├── jtag_tap                   — TAP controller
    └── scan_chain_mux             — Scan chain multiplexer
```

### 4.1 Generate Block Mapping

The top module uses nested `generate` blocks (`gen_row`, `gen_col`) to instantiate tiles. The `GridConfig` endpoint table selects which tile type to instantiate at each `(x, y)` coordinate. Dual-row span is supported for tiles that physically occupy two grid rows.

---

## 5. Compute Tile (Tensix)

### 5.1 Architecture Overview

Each Tensix tile is a self-contained compute core optimized for tensor math:

```
┌─────────────────────────────────────────────┐
│                 Tensix Tile                  │
│                                             │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  │
│  │   FPU   │  │   SFPU   │  │   TDMA    │  │
│  │ (FMAC)  │  │ (sin,exp)│  │ (DMA eng) │  │
│  └────┬────┘  └────┬─────┘  └─────┬─────┘  │
│       │             │              │         │
│  ┌────▼─────────────▼──────────────▼──────┐  │
│  │           L1 Cache / Scratchpad        │  │
│  │            (per-tile SRAM)             │  │
│  └────┬──────────────────────────┬────────┘  │
│  ┌────▼────┐              ┌──────▼──────┐    │
│  │  DEST   │              │    SRCB     │    │
│  │  Regs   │              │    Regs     │    │
│  └─────────┘              └─────────────┘    │
│                                             │
│  ┌──────────────────────────────────────┐    │
│  │        NoC Interface (NIU)           │    │
│  └──────────────────────────────────────┘    │
│  ┌──────────────────────────────────────┐    │
│  │        EDC Node (ECC wrapper)        │    │
│  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

### 5.2 Sub-Block Details

| Block | Function | Key Features |
|-------|----------|--------------|
| **FPU** | Fused multiply-accumulate | FP16/BF16/FP32 tensor ops; pipelined FMAC |
| **SFPU** | Special-function unit | Transcendentals (sin, cos, exp, log, rsqrt); lookup + polynomial approx |
| **TDMA** | Tensor DMA | Moves data between L1 ↔ NoC; programmable stride patterns |
| **L1 Cache** | Scratchpad memory | Tile-local SRAM; single-cycle access; ECC protected via EDC |
| **DEST Regs** | Destination register file | Accumulator for FPU output; write-back staging |
| **SRCB Regs** | Source-B register file | Secondary operand storage for FPU |

### 5.3 Data Flow

1. **Load:** TDMA fetches tensors from external memory (via NoC → AXI) into L1.
2. **Execute:** FPU reads operands from L1/SRCB, computes, writes results to DEST.
3. **Special Ops:** SFPU handles non-linear activations, reading from DEST, writing back.
4. **Store:** TDMA writes results from L1 back through NoC to external memory.

---

## 6. Dispatch Engine

### 6.1 Dual Dispatch Architecture

Trinity employs two dispatch engines positioned at opposite edges of the grid:

| Engine | Grid Position | Coverage |
|--------|---------------|----------|
| **Dispatch East** | East edge column | Serves eastern half of Tensix tiles |
| **Dispatch West** | West edge column | Serves western half of Tensix tiles |

### 6.2 Command Distribution

```
Host Command Queue
       │
       ▼
 ┌─────────────┐    ┌─────────────┐
 │ Dispatch West│    │ Dispatch East│
 │   (FIFO)    │    │   (FIFO)    │
 └──────┬──────┘    └──────┬──────┘
        │                   │
   de_to_t6 signals    de_to_t6 signals
        │                   │
  ┌─────▼─────┐       ┌────▼──────┐
  │ Tensix     │  ...  │ Tensix    │
  │ Tiles W    │       │ Tiles E   │
  └────────────┘       └───────────┘
        │                   │
   t6_to_de signals    t6_to_de signals
        │                   │
        └───────┬───────────┘
                ▼
          Completion / Status
```

### 6.3 Key Signals

| Signal Group | Direction | Description |
|-------------|-----------|-------------|
| `de_to_t6_*` | Dispatch → Tensix | Command opcode, operand addresses, valid, sync flags |
| `t6_to_de_*` | Tensix → Dispatch | Completion ack, stall, error status |

### 6.4 Feed-Through

Dispatch signals pass through intermediate tiles via feed-through wiring — non-target tiles forward commands without processing them, enabling a linear daisy-chain distribution model.

---

## 7. NoC Fabric

### 7.1 Topology

The NoC is a 2D mesh spanning the 4×5 grid with dedicated X-axis and Y-axis routers. Each tile contains a local NoC interface; dedicated `noc_router_tile` instances provide additional routing capacity at infrastructure positions.

### 7.2 Routing Algorithms

| Algorithm | Type | Use Case |
|-----------|------|----------|
| **DOR (Dimension-Ordered Routing)** | Deterministic | Default: route X first, then Y. Deadlock-free. |
| **Tendril** | Semi-adaptive | Allows limited Y-before-X for load balancing near congested columns |
| **Dynamic** | Fully adaptive | Runtime path selection using VC availability; highest throughput, complex arbitration |

### 7.3 Flit Structure

| Field | Bits | Description |
|-------|------|-------------|
| Header | Variable | Destination (x,y), packet type, routing mode, VC ID |
| Payload | 256+ | Data payload (aligned to AXI data width) |
| Tail | 1 | End-of-packet marker |

### 7.4 Virtual Channel (VC) Buffers

- Multiple VCs per physical link to prevent head-of-line blocking.
- Separate VC pools for request vs. response traffic (deadlock avoidance).
- Credit-based flow control between adjacent routers.

### 7.5 Repeater Stages

Long wires between distant columns use repeater stages (`noc_repeater`) inserted at `noc_router_tile` positions to maintain signal integrity and meet timing at `noc_clk` frequency.

---

## 8. NIU (Network Interface Unit)

### 8.1 NoC-to-AXI Bridge (`noc2axi`)

Each AXI endpoint tile contains a `noc2axi_bridge` that translates NoC packets into AXI4 transactions:

| Feature | Detail |
|---------|--------|
| **Protocol** | AXI4 (full), supporting burst, outstanding transactions |
| **Data Width** | 256-bit (matches NoC flit payload) |
| **Address Width** | 40+ bits (supports large physical address space) |
| **Ordering** | AXI ID-based ordering; NoC VC maps to AXI ID |

### 8.2 Address Translation Table (ATT)

- Translates NoC-internal tile-relative addresses to physical AXI addresses.
- Programmable via APB SFR interface.
- Supports multiple memory regions with configurable base/size/permission.

### 8.3 SMN Security

| Feature | Description |
|---------|-------------|
| **SMN Guard** | Checks each AXI transaction against a security policy |
| **Access Control** | Per-region read/write/execute permissions |
| **Violation** | Blocked transactions return AXI SLVERR; logged for DFX |

---

## 9. Clock Architecture

### 9.1 Clock Domains

| Domain | Symbol | Typical Use | Notes |
|--------|--------|-------------|-------|
| **AI Compute** | `ai_clk` | FPU, SFPU, DEST/SRCB, L1 | Highest frequency; per-tile gating |
| **NoC** | `noc_clk` | NoC routers, NIU, VC buffers | Mesh-wide synchronous |
| **Data Movement** | `dm_clk` | TDMA, AXI bridge | May be async to ai_clk |
| **Reference** | `ref_clk` | PLL reference, low-speed control | Always-on |

### 9.2 Clock Distribution (`clock_routing_t`)

Defined as a struct in `trinity_pkg.sv`, `clock_routing_t` encodes:
- Per-tile clock-gate enable bits
- Clock mux select for test/functional mode
- Exception list for tiles with non-standard clocking (e.g., AXI endpoints on `dm_clk` only)

### 9.3 Clock Domain Crossings (CDC)

- NoC ↔ AI: Synchronizer FIFOs at each tile's NIU boundary
- DM ↔ NoC: Async FIFO in AXI bridge
- Ref ↔ All: Slow-to-fast synchronizers for configuration registers

---

## 10. Reset Architecture

### 10.1 Global Reset

- `rst_n` (active-low) — chip-wide hard reset; de-asserts synchronously to `ref_clk`.

### 10.2 Power Partitions (PRTN)

| Feature | Description |
|---------|-------------|
| **Daisy Chain** | Reset propagates through `reset_chain` module in defined tile order |
| **ISO_EN** | Isolation enable signal gates I/O of powered-down partitions |
| **prtn_rst_n** | Per-partition reset; independent of global `rst_n` |
| **prtn_ok** | Acknowledge signal: partition power is stable and reset is de-asserted |

### 10.3 Reset Sequence

```
1. Assert rst_n (global)
2. PLL locks on ref_clk
3. Release rst_n — all partitions in reset
4. For each partition:
   a. Assert prtn_rst_n[i]
   b. Power-up sequence; wait for voltage stable
   c. De-assert ISO_EN[i]
   d. De-assert prtn_rst_n[i]
   e. Partition asserts prtn_ok[i]
5. Dispatch engines begin accepting commands
```

---

## 11. EDC (Error Detection & Correction)

### 11.1 Ring Topology

EDC uses a **per-column serial ring** architecture. Each column (0–4) has an independent EDC ring connecting all tiles in that column:

```
Column j:
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ Tile(j,0)│───▶│ Tile(j,1)│───▶│ Tile(j,2)│───▶│ Tile(j,3)│──┐
  │ edc_node │    │ edc_node │    │ edc_node │    │ edc_node │  │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
       ▲                                                         │
       └─────────── edc_ring_connector[j] ◀──────────────────────┘
```

### 11.2 Serial Bus Protocol

From the RTL claim (`tt_edc_pkg.sv`), the EDC interface uses **toggle-based** handshaking:

| Signal | Function |
|--------|----------|
| `req_tgl` | Request toggle — sender flips to initiate a new EDC transaction |
| `ack_tgl` | Acknowledge toggle — receiver flips to confirm receipt |
| `cor_err` | Correctable error flag — asserted when ECC detects a 1-bit error |
| `err_inj_vec` | Error injection vector — for test/DFX; injects bit-flip patterns into SRAM |

### 11.3 Modport Architecture (from `tt_edc_pkg.sv`)

| Modport | Role |
|---------|------|
| `ingress` | Receives EDC messages from upstream tile |
| `egress` | Sends EDC messages to downstream tile |
| `edc_node` | Core logic: ECC encode/decode, error counting, scrub scheduling |
| `sram` | SRAM macro interface: read/write with ECC check/correct |

### 11.4 Harvest Bypass

When a tile is harvested (disabled), its EDC node is bypassed:
- The `edc_ring_connector` routes `ingress` directly to `egress`, skipping the disabled tile.
- The harvest mask in `GridConfig` controls which tiles are bypassed.
- This ensures the ring remains unbroken regardless of harvest configuration.

---

## 12. SRAM Inventory

| Instance | Location | Purpose | ECC |
|----------|----------|---------|-----|
| `tensix_l1_sram` | Each Tensix tile (×12) | L1 scratchpad / cache | Yes (EDC) |
| `dest_reg_sram` | Each Tensix tile (×12) | DEST register file backing | Yes (EDC) |
| `srcb_reg_sram` | Each Tensix tile (×12) | SRCB register file backing | Yes (EDC) |
| `noc_vc_buf_sram` | NoC router tiles (×2) | VC buffer storage | Yes (EDC) |
| `dispatch_cmd_fifo_sram` | Dispatch tiles (×2) | Command FIFO storage | Yes (EDC) |
| `att_sram` | AXI endpoint tiles (×2) | Address Translation Table entries | Yes (EDC) |
| `sfr_sram` | Configuration region | SFR memory for APB-mapped registers | Parity |

> **Note:** All SRAM instances connected to the EDC ring have full ECC (SEC-DED). The `sram` modport in `tt_edc_pkg.sv` provides the interface for ECC scrub and error reporting.

---

## 13. DFX (Design-for-Test / Debug)

### 13.1 iJTAG Infrastructure

| Component | Description |
|-----------|-------------|
| **TAP Controller** | IEEE 1149.1 TAP; accessible via `jtag_tck/tms/tdi/tdo` |
| **SIB (Segment Insertion Bit)** | Hierarchical scan segment control per tile |
| **TDR (Test Data Register)** | Per-block test/debug registers (accessible via iJTAG) |

### 13.2 Scan Chain Architecture

| Feature | Detail |
|---------|--------|
| **Scan Chains** | Multiple chains per tile, multiplexed at `dfx_wrapper` |
| **Compression** | On-chip scan compression (codec) for reduced test time |
| **ATPG Coverage** | Targets >95% stuck-at, >85% transition fault coverage |
| **Scan Mux** | `scan_chain_mux` selects between functional and test mode |

### 13.3 Debug Features

- **EDC Error Injection:** `err_inj_vec` allows controlled bit-flip injection for SRAM ECC validation.
- **SMN Violation Log:** AXI security violations logged and readable via APB.
- **Performance Counters:** Per-tile cycle counters accessible through iJTAG TDR.

---

## 14. RTL File Reference

| # | File Path | Description |
|---|-----------|-------------|
| 1 | `tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package: modport definitions (ingress, egress, edc_node, sram), toggle-based protocol signals |
| 2 | `trinity_pkg.sv` | Top-level package: `SizeX`, `SizeY`, `NumTensix`, `tile_t` enum, `GridConfig`, `clock_routing_t`, endpoint table |
| 3 | `trinity.sv` | Top module: generate-block grid instantiation, port declarations, clock/reset/PRTN wiring |
| 4 | `tensix_tile.sv` | Tensix compute tile: FPU, SFPU, TDMA, L1, DEST/SRCB instantiation |
| 5 | `tensix_fpu.sv` | FPU: fused multiply-accumulate pipeline |
| 6 | `tensix_sfpu.sv` | SFPU: special-function unit (transcendentals) |
| 7 | `tensix_tdma.sv` | TDMA: tensor DMA engine |
| 8 | `noc_router_tile.sv` | NoC router: X/Y routing, VC arbitration, repeater |
| 9 | `noc2axi_bridge.sv` | NIU: NoC-to-AXI protocol bridge |
| 10 | `dispatch_tile.sv` | Dispatch engine: command FIFO, routing, East/West distribution |
| 11 | `edc_ring_connector.sv` | EDC ring: per-column connector with harvest bypass |
| 12 | `tt_edc_node.sv` | EDC node: ECC encode/decode, scrub, error counting |
| 13 | `prtn_controller.sv` | Power partition: daisy-chain reset, ISO_EN control |
| 14 | `dfx_wrapper.sv` | DFX: iJTAG TAP, scan chain mux |
| 15 | `clock_routing.sv` | Clock distribution: per-tile gating, mux, CDC |

> **Pipeline paths confirmed:** All EDC files verified at `rtl-sources/tt_20260221/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` and variants under `used_in_n1/` directories.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v0.1 | — | Engineer (manual) | Baseline 13-section HDD from direct RTL source reading |
| v1 | — | AI (RAG+RTL) | Auto-generated; per-topic deep dives (EDC, NoC, Dispatch, NIU) |
| v2 | — | AI (RAG+RTL) | Refined with multi-query RTL search; 6 sub-documents |
| **v3a** | 2026-04-22 | AI (single RTL call) | Full 14-section chip HDD; single claim search + accumulated knowledge |

---

*End of Document*

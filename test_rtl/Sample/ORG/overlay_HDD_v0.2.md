# Trinity Overlay — Hardware Design Document

**Document:** overlay_HDD_v0.2.md
**Chip:** Trinity (4×5 NoC Mesh)
**RTL Snapshot:** 20260221
**Primary Sources:** `tt_overlay_wrapper.sv`, `tt_overlay_pkg.sv`, `tt_overlay_noc_wrap.sv`, `tt_overlay_smn_wrapper.sv`, `tt_overlay_clock_reset_ctrl.sv`, `tt_overlay_edc_wrapper.sv`, `tt_overlay_noc_niu_router.sv`, `tt_idma_wrapper.sv`, `tt_idma_pkg.sv`, `tt_rocc_accel.sv`, `tt_rocc_pkg.sv`, `tt_dispatch_engine.sv`, `tt_fds_wrapper.sv`, `tt_fds.sv`
**Audience:** Verification Engineers · Software Engineers · Hardware Engineers

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v0.1 | 2026-03-17 | (RTL-derived) | Initial release |
| v0.2 | 2026-03-17 | (RTL-derived) | Expanded: L1 access path, iDMA usage guide, ROCC architecture, Dispatch Engine details, SMN detail, FDS detail, Tensix access path |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Overlay Position in Trinity Grid](#2-overlay-position-in-trinity-grid)
3. [Feature Summary](#3-feature-summary)
4. [Block Diagram](#4-block-diagram)
5. [Sub-module Hierarchy](#5-sub-module-hierarchy)
6. [Feature Details](#6-feature-details)
   - 6.1 [Multi-Clock Domain and Reset Management](#61-multi-clock-domain-and-reset-management)
   - 6.2 [NoC Interface — NIU and Router](#62-noc-interface--niu-and-router)
   - 6.3 [Cluster CPU Subsystem (RISC-V Cores)](#63-cluster-cpu-subsystem-risc-v-cores)
   - 6.4 [L1 Cache — Access Path and Methods](#64-l1-cache--access-path-and-methods)
   - 6.5 [iDMA Engine — Architecture, Usage, and Advanced Guide](#65-idma-engine--architecture-usage-and-advanced-guide)
   - 6.6 [ROCC Accelerator — Architecture and Instruction Set](#66-rocc-accelerator--architecture-and-instruction-set)
   - 6.7 [LLK (Low-Latency Kernel) Interface](#67-llk-low-latency-kernel-interface)
   - 6.8 [Dispatch Engine — Architecture, Features, and Data Path](#68-dispatch-engine--architecture-features-and-data-path)
   - 6.9 [SMN (System Maintenance Network) — Detailed Description](#69-smn-system-maintenance-network--detailed-description)
   - 6.10 [EDC (Error Detection and Correction)](#610-edc-error-detection-and-correction)
   - 6.11 [FDS (Frequency/Droop Sensor) — Architecture, Purpose, SW Guide](#611-fds-frequencydroop-sensor--architecture-purpose-sw-guide)
   - 6.12 [Tensix and L1 Access from the Overlay](#612-tensix-and-l1-access-from-the-overlay)
   - 6.13 [Harvest Support](#613-harvest-support)
   - 6.14 [Register Access via APB / EDC Bridge](#614-register-access-via-apb--edc-bridge)
   - 6.15 [iJTAG / DFD Interface](#615-ijtag--dfd-interface)
7. [Control Path: Processor to Data Bus](#7-control-path-processor-to-data-bus)
8. [Key Parameters](#8-key-parameters)
9. [Clock and Reset Summary](#9-clock-and-reset-summary)
10. [APB Register Interfaces](#10-apb-register-interfaces)
11. [Worked Example: CPU Issues a NoC Write](#11-worked-example-cpu-issues-a-noc-write)
12. [Verification Checklist](#12-verification-checklist)
13. [Key RTL File Index](#13-key-rtl-file-index)

---

## 1. Overview

The **Overlay** is a shared infrastructure wrapper that sits alongside each Tensix compute tile in the Trinity 4×5 NoC mesh. It is the glue between the **RISC-V cluster CPUs**, the **Tensix tensor cores**, the **L1 cache**, and the **NoC mesh**. Every Tensix row (Y=1 to Y=4) and the Dispatch Engine tiles (Y=0, X=1 and X=2) each instantiate one overlay.

The overlay provides:

| Function | Hardware |
|----------|----------|
| Cluster CPU management | 8× RISC-V cores + uncore, reset, clock gating |
| NoC connectivity | NIU + router wrap, flit arbitration, VC management |
| L1 data and instruction cache | T6 L1 cache banks, flex client ports |
| Bulk DMA | iDMA engine (2D scatter/gather, 2 back-ends, 24 clients) |
| Accelerator co-processor link | ROCC command/address-gen engines (CUSTOM_0–CUSTOM_3) |
| Kernel counter synchronization | LLK remote counter interface (4 channels × 4 cores) |
| Chip management sideband | SMN (N↔S AXI4-Lite daisy-chain ring) |
| Error detection | EDC1 serial bus repeaters and CSRs |
| Frequency / droop sensing | FDS with 3 sensor sources and interrupt output |
| Harvest isolation | Per-tile harvest bypass and mesh remap |
| Debug | iJTAG/DFD scan chain pass-through |

---

## 2. Overlay Position in Trinity Grid

```
     X=0          X=1          X=2          X=3
Y=0  [DRAM/AXI]  [DISPATCH W] [DISPATCH E] [DRAM/AXI]
Y=1  [TENSIX]    [TENSIX]     [TENSIX]     [TENSIX]
Y=2  [TENSIX]    [TENSIX]     [TENSIX]     [TENSIX]
Y=3  [TENSIX]    [TENSIX]     [TENSIX]     [TENSIX]
Y=4  [TENSIX]    [TENSIX]     [TENSIX]     [TENSIX]
```

Each `[TENSIX]` cell = `tt_overlay_wrapper` + `tt_tensix_tile` + `tt_t6_l1`.
Each `[DISPATCH]` cell = `tt_disp_eng_overlay_wrapper` (Dispatch variant).

---

## 3. Feature Summary

| Feature | Description | Key Parameter / Signal |
|---------|-------------|----------------------|
| Multi-clock | 5 clock domains per tile | `i_core_clk`, `i_aiclk`, `i_nocclk`, `i_ref_clk` |
| Reset control | Per-CPU and per-domain resets | `i_core_clk_reset_n_pre_sync[7:0]` |
| NoC NIU | Network Interface Unit | `i_flit_in_req_*`, `o_flit_out_req_*` |
| L1 Cache | Flex-client RW/RD/WR ports | `o_t6_l1_arb_rw_intf`, `o_t6_l1_arb_rd_intf` |
| iDMA | 2D scatter/gather DMA, 24 clients, 2 back-ends | `IDMA_DFC_EN`, `IDMA_FIFO_DEPTH=42` |
| ROCC | RISC-V ROCC accelerator, opcodes CUSTOM_0–3 | `tt_rocc_accel`, `tt_rocc_cmd_buf` |
| LLK counters | 4× remote counter channels | `o_remote_counter_sel[3:0]`, `o_remote_rts[3:0]` |
| Dispatch link | DE↔T6 side-band | `o_de_to_t6`, `o_t6_to_de` |
| SMN | AXI4-Lite management ring N↔S | `HAS_SMN_INST`, `i_smn_req_n_s` |
| EDC | EDC1 serial bus with in/out/loopback repeaters | `HAS_EDC_INST`, `EDC_IN_REP_NUM` |
| FDS | 3-source droop monitor, 16 interrupt groups | `FDS_NUM_SOURCES=3`, `BUS_IN_W=12` |
| Harvest | Per-tile harvested signal + mesh remap | `i_overlay_harvested`, `i_remap_x_size` |
| APB | 26-bit address, 32-bit data register bus | `REG_APB_PORT_ADDR_WIDTH=26` |
| iJTAG | DFD scan chain pass-through | `i_ijtag_tck_to_dfd`, `o_ijtag_so_from_dfd` |

---

## 4. Block Diagram

```
                        ┌─────────────────────────────────────────────────────────┐
                        │                   tt_overlay_wrapper                    │
                        │                                                         │
  i_smn_req_n_s ───────►│   ┌──────────────┐   APB   ┌───────────────────────┐   │
  o_smn_req_n_s ◄───────│   │ SMN Wrapper  │◄───────►│   Cluster CPU         │   │
                        │   │ (AXI4-Lite   │         │ (8× RISC-V + uncore)  │   │
                        │   │  daisy-chain)│         └──────────┬────────────┘   │
  i_aiclk ─────────────►│   └──────────────┘                   │ ROCC            │
  i_nocclk ────────────►│   ┌──────────────┐         ┌─────────▼────────────┐   │
  i_ref_clk ───────────►│   │ Clock/Reset  │         │    ROCC Accel         │   │
  i_core_clk ──────────►│   │  Controller  │         │ cmd_buf/addr_gen/CS   │   │
                        │   └──────────────┘         └─────────┬────────────┘   │
                        │                                       │ iDMA flit       │
  edc_ingress ─────────►│   ┌──────────────┐         ┌─────────▼────────────┐   │
  edc_egress ◄──────────│   │ EDC Wrapper  │         │   iDMA Engine         │   │
                        │   │ (in/out/lbk) │         │ (24 clients, 2 BE,    │   │
                        │   └──────────────┘         │  2D scatter/gather)   │   │
                        │                            └─────────┬────────────┘   │
  i_flit_in_req_N ─────►│   ┌──────────────┐    flit ┌─────────▼────────────┐   │
  o_flit_out_req_N ◄────│   │  FDS Wrapper │   inj.  │   NoC NIU / Router   │   │
  i_flit_in_req_S ─────►│   │ (3 src, 16   │─────────│  (4-port mesh +      │   │
  o_flit_out_req_S ◄────│   │  irq groups) │         │   local port)         │   │
  ... (E, W) ...        │   └──────────────┘         └──────────┬───────────┘   │
                        │                                        │ snoop/RW port  │
  o_de_to_t6 ──────────►│   ┌──────────────────────────────────▼───────────┐   │
  i_t6_to_de ◄──────────│   │          L1 Cache Flex-Client Ports           │   │
                        │   │   RW (CPU×4 + atomic)  RD (iDMA)  WR (NoC)   │   │
  o_t6_l1_arb_rw ◄──────│   └──────────────────────────────────────────────┘   │
                        └─────────────────────────────────────────────────────────┘
```

---

## 5. Sub-module Hierarchy

```
tt_overlay_wrapper
├── tt_overlay_clock_reset_ctrl       — clock gating, reset synchronization
├── tt_overlay_smn_wrapper            — SMN N↔S AXI4-Lite node
│     └── tt_smn (conditional)
├── tt_overlay_edc_wrapper            — EDC1 repeater chain
│     └── tt_edc1_serial_bus_repeater — (when HAS_EDC_INST==1)
├── tt_overlay_noc_wrap               — NoC-side wrapper
│     └── tt_overlay_noc_niu_router
│           └── tt_trinity_noc_niu_router_inst
│                 └── noc_niu_router_inst → niu
├── tt_overlay_cpu_wrapper            — 8× RISC-V harts
├── tt_overlay_memory_wrapper         — L1 SRAM macros + EDC repeaters
├── tt_overlay_flex_client_csr_wrapper — L1 flex-client CSR APB
├── tt_overlay_axi_to_l1_if           — AXI-to-L1 bridge
├── tt_overlay_apb_to_l1_if           — APB-to-L1 bridge
├── tt_overlay_noc_snoop_tl_master    — NoC snoop → L1 WR port
├── tt_idma_wrapper                   — iDMA engine top
│     ├── tt_idma_cmd_buffer_frontend — 24-client arbiter + FIFO
│     └── tt_idma_backend_r_init_rw_obi_top — L1 RD back-end (×IDMA_NUM_BE)
├── tt_rocc_accel [×NUM_CLUSTER_CPUS] — ROCC per-hart (CUSTOM_0–3)
│     ├── tt_rocc_cmd_buf             — command buffer + NoC flit gen
│     ├── tt_rocc_address_gen         — 2D source/destination address gen
│     ├── tt_rocc_context_switch      — context save/restore to L1
│     └── tt_rocc_interrupt_event     — transfer-complete interrupt
├── tt_overlay_tile_counters_with_comparators — LLK remote counters
├── tt_fds_wrapper                    — FDS droop sensor
│     ├── tt_fds_delay_model
│     └── tt_fds
│           └── tt_fds_regfile
├── tt_overlay_edc_apb_bridge         — EDC → APB bridge
├── tt_overlay_wrapper_reg_logic      — APB register crossbar
├── tt_overlay_reg_xbar_slave_decode  — register slave demux
├── tt_overlay_flit_vc_arb            — flit VC arbiter
└── tt_overlay_wrapper_harvest_trinity — harvest logic
```

---

## 6. Feature Details

### 6.1 Multi-Clock Domain and Reset Management

**Hardware:** `tt_overlay_clock_reset_ctrl`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_clock_reset_ctrl.sv`](../tt_rtl/overlay/rtl/tt_overlay_clock_reset_ctrl.sv)

| Domain | Signal | Usage |
|--------|--------|-------|
| `core_clk` / `uncore_clk` | `i_core_clk` (gated) | CPU pipeline, L1 cache |
| `aiclk` | `i_aiclk` (from PLL) | Tensix matrix engine |
| `ai_aon_clk` | `i_ai_aon_clk` | Always-on uncore path |
| `nocclk` | `i_nocclk` | NoC flit datapath |
| `ref_clk` | `i_ref_clk` | PLL reference, reset sync |

Reset constants:
```systemverilog
localparam int unsigned REF_CLK_RESET_CYCLES    = 16;
localparam int unsigned CORE_CLK_RESET_CYCLES   = 16;
localparam int unsigned UNCORE_CLK_RESET_CYCLES = 16;
localparam int unsigned AI_CLK_RESET_CYCLES     = 16;
```

---

### 6.2 NoC Interface — NIU and Router

**Hardware:** `tt_overlay_noc_wrap` → `tt_overlay_noc_niu_router`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_noc_wrap.sv`](../tt_rtl/overlay/rtl/tt_overlay_noc_wrap.sv)

Four-port mesh (N/S/E/W) plus a local injection/ejection port through the NIU. Flit repeaters on N↔S paths are parameterized via `NOC_FLIT_REPEATERS_NORTH_TO_SOUTH` and `NOC_FLIT_REPEATERS_SOUTH_TO_NORTH`.

Node ID distribution: `i_local_nodeid_x`, `i_local_nodeid_y` are constants at instantiation, forwarded as `o_local_nodeid_x_to_t6_l1_partition` and `o_nxt_node_id_x/y`.

---

### 6.3 Cluster CPU Subsystem (RISC-V Cores)

**Hardware:** `tt_overlay_cpu_wrapper`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_cpu_wrapper.sv`](../tt_rtl/overlay/rtl/tt_overlay_cpu_wrapper.sv)

```systemverilog
localparam int unsigned NUM_CLUSTER_CPUS = 8;
localparam int unsigned NUM_INTERRUPTS   = 64;  // 56 internal + 8 external
localparam int unsigned RESET_VECTOR_WIDTH = 52;
```

L1 access sub-port breakdown:
```
NUM_RW_SUB_PORTS_CPU        = 4
NUM_RW_SUB_PORTS_T6L1_DEBUG = 1
NUM_RW_SUB_PORTS_NOC_ATOMIC = 1
NUM_RW_SUB_PORTS_OVERLAY    = 5
```

---

### 6.4 L1 Cache — Access Path and Methods

**Hardware:** `tt_overlay_memory_wrapper`, `tt_overlay_axi_to_l1_if`, `tt_overlay_apb_to_l1_if`, `tt_overlay_noc_snoop_tl_master`
**Source:** [`tt_rtl/overlay/rtl/`](../tt_rtl/overlay/rtl/)

#### 6.4.1 Access Masters and Port Allocation

The T6 L1 cache is a **banked SRAM** accessed through three classes of flex-client ports:

| Port Type | Direction | Users | Interface Signal |
|-----------|-----------|-------|-----------------|
| **RW** (read-write) | bidirectional | CPU harts (×4 sub-ports), T6L1 debug (×1), NoC atomic (×1) | `o_t6_l1_arb_rw_intf[NUM_RW_PORTS-1:0]` |
| **RD** (read-only) | read | iDMA back-end(s) | `o_t6_l1_arb_rd_intf[NUM_RD_PORTS-1:0]` |
| **WR** (write-only) | write | NoC snoop (inbound DMA writes), overlay WR path | `o_t6_l1_arb_wr_intf[NUM_WR_PORTS-1:0]` |

Port counts are driven by the `L1_CFG` struct (`NEO_L1_CFG`):
```systemverilog
localparam int unsigned NUM_RW_PORTS  = L1_CFG.OVRLY_RW_PORT_CNT;
localparam int unsigned NUM_RD_PORTS  = L1_CFG.OVRLY_RD_PORT_CNT;
localparam int unsigned NUM_WR_PORTS  = L1_CFG.OVRLY_WR_PORT_CNT;
```

#### 6.4.2 Access Methods

**Method 1: CPU Hart (Normal Load/Store)**
```
RISC-V hart load/store
  → L1 D-cache tag lookup (core_clk domain)
  → o_t6_l1_pre_sbank_rw_intf[port]   (pre-arbitration: address phase)
  → o_t6_l1_arb_rw_intf[port]         (post-arbitration: data phase)
  → T6 L1 SRAM bank (gated L1 clock)
  → Response: data returned to CPU pipeline (1-3 cycle hit latency)
```

**Method 2: NoC Inbound Write (Snoop)**
```
NoC packet arrives at local NIU
  → tt_overlay_noc_snoop_tl_master extracts address + data
  → i_noc_mem_port_snoop_valid[port]
  → i_noc_mem_port_snoop_addr[port]
  → i_noc_mem_port_snoop_data[port]
  → o_t6_l1_arb_wr_intf[port]         (WR-only flex client)
  → L1 SRAM bank write
```

**Method 3: iDMA Read (Bulk DMA Source)**
```
iDMA back-end initiates a bulk read from local L1
  → o_mem_req[BE_idx][port]
  → o_mem_addr[BE_idx][port]
  → i_mem_rvalid[BE_idx][port]
  → i_mem_rdata[BE_idx][port]
  → iDMA injects read data into NoC as response flit
```

**Method 4: NoC Atomic Operation**
```
NoC atomic read-modify-write flit targets this tile
  → i_noc_flex_rw_intf_atomic_send    (L1_FLEX_CLIENT_SEND_RW_T)
  → o_noc_flex_rw_intf_atomic_recv    (L1_FLEX_CLIENT_RECV_RW_T)
  → RW sub-port (NUM_RW_SUB_PORTS_NOC_ATOMIC = 1)
  → atomic read + compute + write in single L1 access
```

**Method 5: AXI/APB Bridge Access (Debug / Register Tool)**
```
AXI access (from NoC2AXI or debug host)
  → tt_overlay_axi_to_l1_if
  → AXI→L1 flex-client translation
  → RW port

APB access (from debug module or SMN)
  → tt_overlay_apb_to_l1_if
  → APB→L1 flex-client translation
  → RW port
```

#### 6.4.3 L1 Cache Macro Dimensions

| Array | Count | Width (bits) | Depth (entries) | Addr bits |
|-------|-------|-------------|-----------------|-----------|
| D-cache data | 16 macros | 144 (72-bit/way × 2, 64-bit data + 8-bit ECC) | 128 | 7 |
| D-cache tag | 8 macros | 100 | 32 | 5 |
| I-cache data | 16 macros | 66 (33-bit/way × 2, 32-bit + parity) | 256 | 8 |
| I-cache tag | 8 macros | 86 (43-bit/way × 2) | 32 | 5 |
| L2 directory | 4 macros | 152 | 64 | 6 |

#### 6.4.4 Flex-Client Port Timing (Pre-sbank vs. Arb)

Each flex-client exists in two pipeline stages:

| Stage | Interface | Meaning |
|-------|-----------|---------|
| `pre_sbank` | `o_t6_l1_pre_sbank_rw_intf` | Address phase is presented to SRAM bank *before* arbitration outcome is known |
| `arb` | `o_t6_l1_arb_rw_intf` | Port has won arbitration; data write or read response is valid |

Software / firmware does **not** interact with these signals directly; they are internal RTL interfaces between the overlay and the L1 macro wrapper. Software controls L1 behavior via the `tt_cluster_ctrl_t6_l1_csr_reg.svh` CSR register set (accessed over APB at the 26-bit address space).

#### 6.4.5 L1 Phase Root

The L1 uses a **phase counter** to pipeline its SRAM access. Both the overlay and the dispatch engine receive and forward the phase:

```systemverilog
input  [L1_CFG.PHASE_CNT_W-1:0] i_t6_l1_phase_root,
// (dispatch)
output logic [DISPATCH_L1_CFG.PHASE_CNT_W-1:0] o_l1_phase_root_to_ovl,
output logic [DISPATCH_L1_CFG.PHASE_CNT_W-1:0] o_l1_phase_root_to_noc,
```

#### 6.4.6 L1 CSR Programming (Software Guide)

Access the L1 configuration registers at the tile's APB address space. Key registers:

| Register File | Usage |
|--------------|-------|
| `tt_cluster_ctrl_t6_l1_csr_reg.svh` | Enable D/I cache, set associativity, configure ECC mode, set flush trigger |
| `tt_cache_controller_reg.svh` | Set prefetch depth, replacement policy (LRU/random), cache lock |
| `tt_t6l1_slv_reg.svh` | Address window: which NoC address range maps into this tile's L1 |

Typical L1 initialization sequence:
1. Write L1 enable bit in cluster ctrl CSR.
2. Configure ECC mode (single-bit-correct / double-bit-detect or parity).
3. Set the T6L1 slave address window registers (`tt_t6l1_slv_reg`) to define the local L1 NoC address range.
4. Optionally invalidate/flush: write the flush trigger CSR.
5. For DMA: ensure the NoC inline-disable config (`o_noc_mem_port_snoop_inline_disable_cfg`) is cleared so NoC writes can reach L1.

---

### 6.5 iDMA Engine — Architecture, Usage, and Advanced Guide

**Hardware:** `tt_idma_wrapper` → `tt_idma_cmd_buffer_frontend` → `tt_idma_backend_r_init_rw_obi_top`
**Source:** [`tt_rtl/overlay/rtl/idma/tt_idma_wrapper.sv`](../tt_rtl/overlay/rtl/idma/tt_idma_wrapper.sv)

#### 6.5.1 Architecture Overview

```
                    iDMA Engine
  ┌─────────────────────────────────────────────────────────┐
  │                                                         │
  │  ┌────────────────────────────────────────────────┐    │
  │  │   tt_idma_cmd_buffer_frontend                  │    │
  │  │                                                │    │
  │  │   24 clients ──► 24:2 arbiter ──► 2 FIFO slots│    │
  │  │                   (round-robin)   depth=42     │    │
  │  │                 payload FIFO depth=8           │    │
  │  └──────────────────────────┬─────────────────────┘    │
  │           req_head_flit     │  (iDMA request)           │
  │                             ▼                           │
  │  ┌────────────────────────────────────────────────┐    │
  │  │   tt_idma_backend_r_init_rw_obi_top [×2 BEs]  │    │
  │  │                                                │    │
  │  │   • Fetch src data from L1 (OBI memory port)   │    │
  │  │   • Inject NoC flit toward destination         │    │
  │  │   • Accumulate atomic (IDMA_L1_ACC_ATOMIC=16)  │    │
  │  └──────┬──────────────────────────────┬──────────┘    │
  │         │ L1 read port                 │ NoC flit out   │
  └─────────┼──────────────────────────────┼───────────────┘
            ▼                              ▼
     o_t6_l1_arb_rd_intf           NIU injection port
     (IDMA_NUM_MEM_PORTS=2)
```

Key constants from `tt_idma_pkg.sv`:

```systemverilog
localparam int unsigned IDMA_NUM_MEM_PORTS         = 2;     // L1 read ports per back-end
localparam int unsigned IDMA_NUM_TRANSACTION_ID    = 32;    // 2^5 outstanding transaction IDs
localparam int unsigned IDMA_TRANSFER_LENGTH_WIDTH = 22;    // max 4 MB per transfer
localparam int unsigned IDMA_FIFO_DEPTH            = 42;    // metadata FIFO
localparam int unsigned IDMA_PAYLOAD_FIFO_DEPTH    = 8;     // payload buffering
localparam int unsigned IDMA_CMD_BUF_NUM_CLIENTS   = 24;    // number of requestors
localparam int unsigned IDMA_L1_ACC_ATOMIC         = 16;    // atomic accumulation width
localparam int unsigned NumDim                     = 2;     // 2D transfer (src/dst stride)
```

#### 6.5.2 Masters That Can Access iDMA

| Master | How It Submits to iDMA | Notes |
|--------|----------------------|-------|
| **ROCC CPU (per hart)** | `INSTR_IDMA_GET_VC_SPACE`, `INSTR_IDMA_TR_ACK` via ROCC custom instructions | Primary software path |
| **Dispatch Engine** | Submits iDMA flit via `req_head_flit` client port | DE issues transfers on behalf of tensor kernel |
| **Host (via NoC)** | NoC packet targets overlay register port → `o_ext_reg_addr` | Out-of-band programming |
| **SMN APB** | SMN master writes iDMA CSR via EDC→APB bridge | Boot / firmware loader path |

#### 6.5.3 Source and Destination Memory

| Role | Memory | Access Interface |
|------|--------|-----------------|
| **Source (read)** | Local T6 L1 cache | `o_t6_l1_arb_rd_intf` (OBI back-end) |
| **Destination (write)** | Any NoC-reachable tile's L1 or DRAM/AXI | NoC flit injected via NIU (x/y coord from address generator) |
| **Destination (write, local)** | Local L1 (loop-back) | Back-end routes flit to local NIU → snoop WR port |
| **Source (AXI, non-Trinity)** | AXI bus (IDMA_BE_TYPE_AXI=1) | `axi_req_t` / `axi_resp_t` back-end |

#### 6.5.4 iDMA Feature List

| Feature | Details |
|---------|---------|
| **2D strided transfer** | `NumDim=2`; separate source and destination stride independently |
| **24 concurrent clients** | `IDMA_CMD_BUF_NUM_CLIENTS=24`; round-robin arbitrated |
| **2 parallel back-ends** | Two independent L1 read + NoC inject pipelines run simultaneously |
| **32 outstanding transaction IDs** | Per-BE transaction tracking; 5-bit tag |
| **Transfer length** | Up to 4 MB per single iDMA request (`IDMA_TRANSFER_LENGTH_WIDTH=22`) |
| **Atomic accumulate** | `IDMA_L1_ACC_ATOMIC=16`; back-end can issue L1 atomic-accumulate alongside DMA |
| **DFC (Data Format Conversion)** | Optional (`IDMA_DFC_EN=1'b0`); convert element format during transfer |
| **Timing pipeline stages** | `IDMA_ENABLE_TIMING_STAGES=1'b1`; adds register slice on critical paths |
| **Tiles-to-process threshold** | 5-bit transaction ID mapped to threshold; interrupt fires when complete tile count is reached (`o_idma_tiles_to_process_irq`) |
| **VC space tracking** | `o_req_head_flit_vc_space[BE][VC_CNT_WIDTH]` fed back to ROCC to prevent overcommit |
| **Clock gating** | Separate gaters for core and L1 domains with hysteresis (`CLK_GATER_HYST_WIDTH=7`) |

#### 6.5.5 Basic Usage Guide (Software)

**Step 1 — Query VC space**
```
ROCC instruction: CUSTOM_1, funct=INSTR_IDMA_GET_VC_SPACE
  rs1 = back-end index
  → rd = current VC slot count (check > 0 before issuing)
```

**Step 2 — Program address generator (source and destination)**
```
ROCC instruction: CUSTOM_1, funct=INSTR_ADDR_GEN_SRC
  rs1 = source base address in L1
  rs2 = stride (2D: inner stride in rs1, outer stride in rs2)

ROCC instruction: CUSTOM_1, funct=INSTR_ADDR_GEN_DEST
  rs1 = destination base address (NoC address, x/y embedded)
  rs2 = destination stride
```

**Step 3 — Push addresses**
```
ROCC instruction: CUSTOM_1, funct=INSTR_ADDR_PUSH_BOTH
  (or INSTR_ADDR_PUSH_SRC / INSTR_ADDR_PUSH_DEST separately)
```

**Step 4 — Issue transfer**
```
ROCC instruction: CUSTOM_0, funct=INSTR_ISSUE        (read+write)
  -- or --
ROCC instruction: CUSTOM_0, funct=INSTR_ISSUE_READ   (read only)
ROCC instruction: CUSTOM_0, funct=INSTR_ISSUE_WRITE  (write only)
  rs1 = length (bytes, max 4 MB)
  rs2 = transaction ID [4:0]
```

**Step 5 — Wait for completion (threshold interrupt)**
```
ROCC instruction: CUSTOM_2, funct=INSTR_TILES_TO_PROCESS_THRES_IDMA_TR_ACK
  rs1 = transaction ID
  rs2 = threshold (number of completed tiles)
  → interrupt fires when iDMA completion count ≥ threshold
```

**Step 6 — Acknowledge**
```
ROCC instruction: CUSTOM_0, funct=INSTR_IDMA_TR_ACK
  rs1 = transaction ID to clear
```

#### 6.5.6 Advanced Usage

**2D Tiled Transfer**
Use `NumDim=2` with separate inner/outer strides to implement a tiled matrix copy without CPU re-issue:
```
src_inner_stride = matrix_row_bytes
src_outer_stride = tile_height × matrix_row_bytes
dst_inner_stride = dst_row_bytes
dst_outer_stride = tile_height × dst_row_bytes
length = tile_width_bytes × tile_height
```
Issue with `INSTR_ADDR_GEN_BOTH`, then `INSTR_ADDR_PUSH_BOTH`, then `INSTR_ISSUE`.

**Context Switch Save/Restore**
The `tt_rocc_context_switch` block saves the entire iDMA address generator state to L1:
```
ROCC CUSTOM_2: INSTR_CS_SAVE    → saves addrgen regfile to L1 memory
ROCC CUSTOM_2: INSTR_CS_RESTORE → restores addrgen regfile from L1
ROCC CUSTOM_2: INSTR_CS_ALLOC   → allocates a context slot
ROCC CUSTOM_2: INSTR_CS_DEALLOC → frees a context slot
```
Context save uses a dedicated L1 region (`CS_RAM_ADDR_WIDTH = clog2(2^CS_SR_MASTER_WIDTH × CS_CONTEXT_ALLOC_WIDTH)`).

**Atomic Accumulate (DFC path)**
When `IDMA_DFC_EN=1` and `IDMA_L1_ACC_ATOMIC=16`:
- Back-end issues `o_l1_accum_en[BE]` alongside the read
- L1 returns data, back-end accumulates using `o_l1_accum_cfg[BE]` instruction
- Result is written to destination via NoC

**Multi-client Pipelining**
Up to 24 clients may have pending requests in the frontend FIFO simultaneously. The 24:2 arbiter grants round-robin. To maximize throughput, clients should:
1. Pre-load multiple iDMA requests without waiting for the previous to complete.
2. Use distinct transaction IDs (0–31) to track each in-flight transfer independently.

---

### 6.6 ROCC Accelerator — Architecture and Instruction Set

**Hardware:** `tt_rocc_accel`, `tt_rocc_cmd_buf`, `tt_rocc_address_gen`, `tt_rocc_context_switch`, `tt_rocc_interrupt_event`
**Source:** [`tt_rtl/overlay/rtl/accelerators/`](../tt_rtl/overlay/rtl/accelerators/)

#### 6.6.1 Architecture

The ROCC (Rocket Custom Co-Processor) interface is the standard RISC-V extension channel between the CPU pipeline and an attached accelerator. In the overlay, ROCC connects each hart to a set of accelerator engines:

```
RISC-V Hart N
  │
  │  ROCC instruction (custom0–3 opcode space)
  │  rocc_cmd_valid / rocc_cmd_ready handshake
  │  rocc_cmd_bits_inst_funct[6:0]     — 6-bit function code
  │  rocc_cmd_bits_rs1[63:0]           — operand 1
  │  rocc_cmd_bits_rs2[63:0]           — operand 2
  ▼
tt_rocc_accel (per hart)
  ├── tt_rocc_cmd_buf        — command buffer engine
  │     Opcode space: CUSTOM_0 (0x0B), CUSTOM_1 (0x2B)
  │     Functions: INSTR_ISSUE, INSTR_GET_VC_SPACE, INSTR_WR_SENT,
  │                INSTR_TR_ACK, INSTR_ISSUE_READ, INSTR_ISSUE_WRITE, ...
  │
  ├── tt_rocc_address_gen    — 2 parallel address generators (PARALLEL_ADDRESS_GEN=2)
  │     Opcode space: CUSTOM_1
  │     Functions: INSTR_ADDR_GEN_SRC, INSTR_ADDR_GEN_DEST,
  │                INSTR_ADDR_PUSH_BOTH, INSTR_ADDR_GEN_BOTH, ...
  │
  ├── tt_rocc_context_switch — context alloc/save/restore (CUSTOM_2)
  │     Functions: INSTR_CS_ALLOC, INSTR_CS_DEALLOC,
  │                INSTR_CS_SAVE, INSTR_CS_RESTORE
  │
  └── tt_rocc_misc (CUSTOM_2)
        Functions: INSTR_FDS_REG_ACCESS, INSTR_LLK_INTF_ACC,
                   INSTR_NOC_FENCE, INSTR_POSTCODE,
                   INSTR_TILES_TO_PROCESS_THRES_*
```

Context switch harts (which harts handle context switch):
```systemverilog
localparam bit CONTEXT_SWITCH_HART =
  (NUM_CS_HARTS == 8) ? 1'b1 :
  (NUM_CS_HARTS == 4) ? (HART_ID ∈ {0,2,4,6}) :
  (NUM_CS_HARTS == 2) ? (HART_ID ∈ {0,2}) :
  (NUM_CS_HARTS == 1) ? (HART_ID == 0) : 1'b0;
```

#### 6.6.2 Opcode Map

RISC-V custom instruction encoding: `inst[6:0] = opcode`, `inst[31:25] = funct7`.

| Opcode | Value | Engine | Function Range |
|--------|-------|--------|---------------|
| `CUSTOM_0` | `7'h0B` | Command Buffer (Read) | funct[5:0] = 0–63 |
| `CUSTOM_0` | `7'h0B` | Command Buffer (Write) | funct[5:0] = 64–127 |
| `CUSTOM_1` | `7'h2B` | Address Gen (Read) | funct[4:0] = 0–31 |
| `CUSTOM_1` | `7'h2B` | Address Gen (Write) | funct[4:0] = 32–63 |
| `CUSTOM_1` | `7'h2B` | Simple Command Buffer | funct[4:0] = 64–127 |
| `CUSTOM_2` | `7'h5B` | Context Switch | funct[4:0] = 0–31 |
| `CUSTOM_2` | `7'h5B` | Misc (fence, FDS, LLK, ...) | funct[4:0] = 32–63 |

#### 6.6.3 Key Instructions

**Command Buffer (CUSTOM_0):**

| Instruction | funct | rs1 | rs2 | rd | Action |
|-------------|-------|-----|-----|----|--------|
| `INSTR_ISSUE` | 63 | src_addr | dst_addr | — | Issue read+write transfer |
| `INSTR_ISSUE_READ` | 56 | src_addr | length | — | Issue read-only transfer |
| `INSTR_ISSUE_WRITE` | 55 | dst_addr | length | — | Issue write-only transfer |
| `INSTR_GET_VC_SPACE` | 62 | BE_idx | — | vc_count | Query VC slots available |
| `INSTR_TR_ACK` | 60 | trid | — | — | Acknowledge NoC read transaction |
| `INSTR_WR_SENT` | 61 | trid | — | — | Acknowledge NoC write response |
| `INSTR_IDMA_GET_VC_SPACE` | 58 | BE_idx | — | vc_count | Query iDMA VC slots |
| `INSTR_IDMA_TR_ACK` | 57 | trid | — | — | Acknowledge iDMA transaction |
| `INSTR_CMDREG_RESET` | 59 | — | — | — | Reset command buffer state |
| `INSTR_REG_ACCESS` | 48 | reg_addr | wr_data | rd_data | Direct register read/write |

**Address Generator (CUSTOM_1):**

| Instruction | funct | rs1 | rs2 | Action |
|-------------|-------|-----|-----|--------|
| `INSTR_ADDR_GEN_SRC` | 31 | src_base | stride | Set source base+stride |
| `INSTR_ADDR_GEN_DEST` | 30 | dst_base | stride | Set destination base+stride |
| `INSTR_ADDR_GEN_BOTH` | 25 | src_base | dst_base | Set both bases |
| `INSTR_ADDR_PUSH_BOTH` | 29 | — | — | Push src+dst addresses to FIFO |
| `INSTR_ADDR_PUSH_SRC` | 28 | — | — | Push src address |
| `INSTR_ADDR_PUSH_DEST` | 27 | — | — | Push dst address |
| `INSTR_ADDR_RESET` | 26 | — | — | Reset address generator |

**Context Switch (CUSTOM_2, funct[4:0] 0–31):**

| Instruction | funct | Action |
|-------------|-------|--------|
| `INSTR_CS_RESTORE` | 0 | Restore context from L1 memory |
| `INSTR_CS_SAVE` | 1 | Save context to L1 memory |
| `INSTR_CS_DEALLOC` | 2 | Free a context slot |
| `INSTR_CS_ALLOC` | 3 | Allocate a context slot |

**Misc (CUSTOM_2, funct[4:0] 32–63):**

| Instruction | funct | Action |
|-------------|-------|--------|
| `INSTR_MISC_REG_ACCESS` | 0 | Misc register read/write |
| `INSTR_POSTCODE` | 1 | Write postcode for debug visibility |
| `INSTR_NOC_FENCE` | 2 | Stall until all NoC writes committed |
| `INSTR_LLK_INTF_ACC` | 3 | Access LLK remote counter interface |
| `INSTR_FDS_REG_ACCESS` | 4 | Access FDS registers |
| `INSTR_TILES_TO_PROCESS_THRES_IDMA_TR_ACK` | 5 | Set iDMA completion threshold |
| `INSTR_TILES_TO_PROCESS_THRES_WR_SENT` | 6 | Set write-sent threshold |
| `INSTR_TILES_TO_PROCESS_THRES_TR_ACK` | 7 | Set read-ack threshold |

#### 6.6.4 ROCC Memory Interface

The ROCC module has a direct D-cache request interface to the CPU's L1 D-cache:
```
rocc_mem_req_valid / rocc_mem_req_ready    — request handshake
rocc_mem_req_bits_addr[39:0]              — 40-bit physical address
rocc_mem_req_bits_cmd[4:0]                — M_SZ: load/store/atomic command
rocc_mem_req_bits_size[1:0]               — transfer size (byte/half/word/dword)
rocc_mem_req_bits_data[63:0]              — store data
rocc_mem_resp_valid                       — response valid
rocc_mem_resp_bits_data[63:0]             — load data
```

This allows the command buffer (`tt_rocc_cmd_buf`) to perform **register-file reads** from the CPU pipeline and **scatter list reads** directly from L1 without issuing a full NoC transaction.

---

### 6.7 LLK (Low-Latency Kernel) Interface

**Hardware:** `tt_overlay_tile_counters_with_comparators`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_tile_counters_with_comparators.sv`](../tt_rtl/overlay/rtl/tt_overlay_tile_counters_with_comparators.sv)

```systemverilog
output [NUM_TENSIX_CORES-1:0] [LLK_IF_REMOTE_COUNTER_SEL_WIDTH-1:0] o_remote_counter_sel,
output [NUM_TENSIX_CORES-1:0] [2:0]                                  o_remote_idx,
output [NUM_TENSIX_CORES-1:0] [LLK_IF_COUNTER_WIDTH-1:0]             o_remote_incr,
output [NUM_TENSIX_CORES-1:0]                                        o_remote_rts,
input  [NUM_TENSIX_CORES-1:0]                                        i_remote_rtr,
```

Software programs LLK thresholds via ROCC `INSTR_LLK_INTF_ACC`. When an incoming counter increment causes the counter to meet the threshold, a CPU interrupt fires, enabling the kernel to proceed without polling.

---

### 6.8 Dispatch Engine — Architecture, Features, and Data Path

**Hardware:** `tt_dispatch_engine` → `tt_disp_eng_overlay_wrapper`
**Source:** [`tt_rtl/overlay/rtl/quasar_dispatch/tt_dispatch_engine.sv`](../tt_rtl/overlay/rtl/quasar_dispatch/tt_dispatch_engine.sv)

#### 6.8.1 Role

The Dispatch Engine (DE) tiles (Y=0, X=1 West, X=2 East) are specialized overlay variants with the Tensix compute core replaced by a **Quasar** RISC-V management processor. The DE orchestrates kernel launches across the Tensix tile array: it programs address generators, issues iDMA transfers, and delivers synchronization pulses through the DE↔T6 side-band.

#### 6.8.2 Key Architectural Differences vs. Tensix Overlay

| Feature | Tensix Overlay | Dispatch Engine |
|---------|---------------|-----------------|
| Compute engine | Tensix matrix engine | None (management only) |
| L1 partition | `tt_t6_l1` | `tt_disp_eng_l1_partition` (separate config) |
| SMN direction | N↔S (column) | E↔S (east-south for DE) |
| NoC ports | N/S/E/W all active | West or East port may be excluded (`NO_NOC_WEST_PORTS`, `NO_NOC_EAST_PORTS`) |
| Clock distribution | Receives from SMN | **Generates** and distributes to column below: `o_noc_clk_south`, `o_dm_clk_south` |
| Global event output | — | `o_global_event_south`, `o_global_event_east` |
| Tile event broadcast | — | `o_tile_event_south[GridSizeY-1:0]`, `o_tile_event_east[GridSizeX-2:0][GridSizeY-1:0]` |
| Orientation | `i_static_is_r180_south`, `i_static_is_r180_east` straps | Propagated south and east |

#### 6.8.3 Hardware Architecture

```
                tt_dispatch_engine (West: X=1,Y=0 / East: X=2,Y=0)
                ┌──────────────────────────────────────────────────────┐
                │                                                      │
  NoC North ───►│  ┌──────────────┐    ┌────────────────────────┐     │
  NoC West  ───►│  │   NoC NIU +  │    │  Quasar RISC-V core    │     │
  NoC South ◄──►│  │   Router     │◄──►│  (tt_disp_eng_overlay_ │     │
                │  │  (4-port)    │    │   noc_niu_router)       │     │
  edc_ingress ─►│  └──────┬───────┘    └──────────┬─────────────┘     │
  edc_egress  ◄─│         │                       │ ROCC               │
                │         │                       │                    │
  SMN E↔S ─────►│  ┌───────────────────────────────────────────────┐  │
  SMN S↔E ◄─────│  │  tt_disp_eng_l1_partition (L1 cache)          │  │
                │  │  RD / WR / RW ports (dispatch L1 cfg)         │  │
                │  └────────────────────────────────────────────────┘  │
                │                                                      │
  o_de_to_t6 ──►│  ┌───────────────────────────────────────────────┐  │
  i_t6_to_de ◄──│  │  FDS wrapper (IS_DISPATCH=1)                  │  │
                │  │  input_bus = t6_to_de signals                  │  │
                │  │  FDS output controls de_to_t6[0][0]           │  │
                │  └────────────────────────────────────────────────┘  │
                │                                                      │
  Global ctrl ──►│  Global event bus / tile event broadcast             │
  Droop event ◄──│  o_droop_event_east[2:0]                            │
                └──────────────────────────────────────────────────────┘
```

#### 6.8.4 DE↔T6 Side-band (de_to_t6 / t6_to_de)

The DE communicates with each Tensix tile via dedicated side-band wires outside the NoC:

```systemverilog
// DE → Tensix (per dispatch corner, broadcast to all columns)
output tt_chip_global_pkg::de_to_t6_t [1:0][NumDispatchCorners-1:0] o_de_to_t6,
input  tt_chip_global_pkg::de_to_t6_t      [NumDispatchCorners-1:0] i_de_to_t6,

// Tensix → DE (per X column)
output tt_chip_global_pkg::t6_to_de_t [NumTensixX-1:0] o_t6_to_de,
input  tt_chip_global_pkg::t6_to_de_t [NumTensixX-1:0] i_t6_to_de,
```

`de_to_t6_t` carries: sync pulse, configuration tokens, tile enable signals.
`t6_to_de_t` carries: completion signals, droop events (used as FDS input bus).

#### 6.8.5 FDS Integration in Dispatch Engine

In the dispatch engine, `IS_DISPATCH=1` changes the FDS wiring:

```systemverilog
// Input bus = t6_to_de signals (droop events from Tensix columns)
assign fds_input_bus = input_t6_to_de;
assign o_t6_to_de    = input_t6_to_de;    // pass-through to FDS output

// FDS output drives the de_to_t6[0][0] side-band
assign o_de_to_t6[0][0] = fds_output_bus;
```

The FDS output is therefore **the mechanism by which the DE throttles Tensix based on droop conditions** — the FDS output bus controls the `de_to_t6` signal that gates Tensix activity.

#### 6.8.6 Clock and Global Control Distribution

The Dispatch Engine is the **clock distribution root** for its column. It generates and drives:
```systemverilog
output logic o_noc_clk_south,        // NoC clock toward Y=1..4
inout  wire  io_noc_clk_east,        // NoC clock eastward
output logic o_dm_clk_south,         // debug/maintenance clock south
output tt_chip_global_pkg::global_ctrl_signals_t o_global_ctrl_south,
```

`i_static_is_r180_south` and `i_static_is_r180_east` straps specify tile orientation (for physical design rotation), propagated to each row below.

#### 6.8.7 Dispatch Engine L1 Partition

`tt_disp_eng_l1_partition` uses `DISPATCH_L1_CFG` (a separate L1 config struct from `NEO_L1_CFG`) with:
- Dedicated NoC RD/WR ports for the DE's local L1
- Overlay RW/RD/WR ports for the Quasar CPU
- Separate phase root outputs: `o_l1_phase_root_to_ovl`, `o_l1_phase_root_to_noc`

#### 6.8.8 SMN in Dispatch Engine

SMN direction differs from Tensix tiles: the DE uses **East↔South** rather than **North↔South**:
```systemverilog
i_smn_req_e_s / o_smn_req_e_s   — East-to-South direction
i_smn_req_s_e / o_smn_req_s_e   — South-to-East direction
```

This allows the chip-level SMN ring to pass through the DE column and reach all Tensix tiles below.

---

### 6.9 SMN (System Maintenance Network) — Detailed Description

**Hardware:** `tt_overlay_smn_wrapper`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_smn_wrapper.sv`](../tt_rtl/overlay/rtl/tt_overlay_smn_wrapper.sv)

#### 6.9.1 Purpose

The SMN is a chip-wide **out-of-band management ring** independent of the main NoC. It handles:
- Boot sequencing and tile enable/disable
- AICLK PLL programming (frequency control, PLL mux, droop-aware DVFS)
- Per-tile clock enable / force-ref / PLL clock mux control
- Per-tile reset orchestration (cold reset, soft reset)
- Mailbox interrupts between tiles
- NoC security fence configuration (`smn_reg_noc_sec`)
- Harvest strap distribution to each tile

#### 6.9.2 Physical Topology

```
  Host / NOC2AXI tile (SMN master root)
        │ smn_req_n_s / smn_resp_n_s
        ▼
  Overlay tile Y=1  ←── SMN node (HAS_SMN_INST=1)
        │ o_smn_req_n_s
        ▼
  Overlay tile Y=2  ←── SMN pass-through
        ▼
  Overlay tile Y=3  ←── SMN pass-through
        ▼
  Overlay tile Y=4  ←── SMN endpoint / return path (s→n direction)
```

Each column has its own independent N↔S SMN chain. The Dispatch Engine uses E↔S direction.

Repeater counts per direction:
```systemverilog
parameter int unsigned SMN_TENSIX_REPEATER_OVERLAY_NORTH_SIDE = 0;
parameter int unsigned SMN_TENSIX_REPEATER_OVERLAY_SOUTH_SIDE = 3;
```

#### 6.9.3 Transport Layer

The SMN wrapper uses **AXI4-Lite** as its transport internally, with an AXI-to-APB conversion at the SMN master:

```systemverilog
// Internal AXI4-Lite SMN transaction
logic [TT_SMN_AXI4_LITE_ADDR_W-1:0] smn_axi4_lite_mst_araddr;
logic [TT_SMN_AXI4_LITE_PROT_W-1:0] smn_axi4_lite_mst_arprot;

// Converted to APB at the target overlay
smn_apb_req_t  smn_mst_apb_req_axiclk;
smn_apb_resp_t smn_mst_apb_resp_axiclk;
```

Clock: SMN operates on `i_axi_clk` (the always-on AXI clock), independent of AICLK and nocclk. This allows SMN to function during AICLK PLL re-lock events.

#### 6.9.4 SMN APB Master → Overlay Register Path

When an SMN transaction targets a tile's registers, the SMN wrapper drives its **APB master port**:

```
SMN ring packet arrives
  → tt_overlay_smn_wrapper
  → AXI4-Lite → APB conversion
  → o_smn_mst_apb_psel / paddr / pwdata / pwrite
  → overlay APB crossbar (tt_overlay_wrapper_reg_logic)
  → target register slave (cluster ctrl, cache ctrl, PLL, etc.)
```

The overlay can also **write to the SMN** from its own APB master port (reverse path):
```
overlay register write → i_overlay_mst_apb_psel / paddr / pwdata
  → tt_overlay_smn_wrapper
  → AXI4-Lite → SMN ring
```

#### 6.9.5 SMN Interrupts and Straps

Three SMN interrupt outputs:
```systemverilog
output logic o_smn_mst_interrupt,        // SMN master transaction complete
output logic o_smn_slv_interrupt,        // SMN slave received command
output logic o_tile_mailbox_interrupt,   // software mailbox write
```

Strap distribution:
```systemverilog
input  tt_smn_reg_structs_pkg::smn_straps_input_t  i_smn_straps,
output tt_smn_reg_structs_pkg::smn_straps_output_t o_smn_straps,
```
Straps include: tile type (`i_local_tile_type`), harvest status, PLL configuration, boot address.

#### 6.9.6 SMN-Controlled Outputs (Clock and Reset)

The SMN is the **primary controller** for clock and reset of each tile:

```systemverilog
// From tt_overlay_wrapper (driven by SMN via clock_reset_ctrl)
output logic o_smn_ai_clk_reset_n,
output logic o_smn_noc_clk_reset_n,
output logic [SMN_TENSIX_RISC_RESET_WIDTH-1:0] o_smn_tensix_risc_reset_n,
output logic o_smn_ai_clk_en,
output logic o_smn_ai_clk_force_ref_n,
output logic o_smn_ai_clk_pll_clk_mux,
output logic o_smn_ref_clk_reset_n,
output logic o_smn_pll_soft_reset_n,
output logic o_smn_dd_clk_reset_n,
output logic o_smn_dd_clk_en,
```

#### 6.9.7 JTAG Integration

The SMN wrapper has a JTAG port for boundary scan and debug:
```systemverilog
input  wire i_tck, i_trstn, i_tdi, i_select,
input  wire i_capture_en, i_update_en, i_shift_en,
output wire o_tdo,
output tt_overlay_pkg::jtag_ctrl_ovrd_t o_jtag_ctrl_ovrd,
```
`o_jtag_ctrl_ovrd` allows JTAG to override SMN-controlled clock/reset signals during debug.

#### 6.9.8 SW Guide: Tile Control via SMN

```
1. Boot: Host SMN master issues SMN write to tile's cluster_ctrl CSR
         → sets boot address, enables CPU clock, deasserts reset

2. DVFS: Host or FDS→SMN interrupt handler writes:
         → o_smn_ai_clk_pll_clk_mux  = 1 (switch to ref clock)
         → o_smn_ai_clk_force_ref_n   = 0 (hold on ref)
         → programs PLL frequency via APB to t6_pll_pvt_slv
         → o_smn_pll_soft_reset_n     = 0 → 1 (re-lock PLL)
         → o_smn_ai_clk_force_ref_n   = 1 (release)
         → o_smn_ai_clk_pll_clk_mux  = 0 (switch back to PLL)

3. Harvest: SMN reads smn_straps_input_t at boot; if harvest strap set,
            SMN holds o_smn_tensix_risc_reset_n low permanently

4. Mailbox: Any tile writes to tile_mailbox register via SMN APB;
            o_tile_mailbox_interrupt fires at destination tile
```

---

### 6.10 EDC (Error Detection and Correction)

**Hardware:** `tt_overlay_edc_wrapper`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_edc_wrapper.sv`](../tt_rtl/overlay/rtl/tt_overlay_edc_wrapper.sv)

| Repeater | Parameter | Purpose |
|----------|-----------|---------|
| Ingress | `EDC_IN_REP_NUM` | Pipeline stages on EDC ingress bus |
| Internal | `EDC_REP_NUM` | Re-timing within overlay node |
| Egress | `EDC_OUT_REP_NUM` | Pipeline stages on EDC egress bus |
| Loopback | (fixed) | `tt_noc_overlay_edc_repeater` in NoC path |

When `HAS_EDC_INST == 1'b0` (harvested), all EDC outputs are zeroed.

Self-test: `OVL_EDC_EN_L2_SELFTEST`, `OVL_EDC_EN_L1_SELFTEST`.

EDC-to-APB bridge (`tt_overlay_edc_apb_bridge`): translates EDC register-access packets into APB transactions for out-of-band register access.

---

### 6.11 FDS (Frequency/Droop Sensor) — Architecture, Purpose, SW Guide

**Hardware:** `tt_fds_wrapper` → `tt_fds` → `tt_fds_regfile`
**Source:** [`tt_rtl/overlay/rtl/fds/tt_fds_wrapper.sv`](../tt_rtl/overlay/rtl/fds/tt_fds_wrapper.sv)

#### 6.11.1 Purpose

The FDS (Frequency/Droop Sensor) monitors on-chip **supply voltage droop** and **clock frequency deviation** caused by workload-induced current spikes. When a droop is detected:

1. The FDS outputs a corrective signal on the `de_to_t6` sideband.
2. This causes the Dispatch Engine to stall or reduce kernel dispatch rate.
3. This gives the PLL time to recover the frequency before timing violations occur.

The FDS thus implements a **hardware-in-the-loop DVFS mechanism** without requiring software intervention on the critical path.

#### 6.11.2 Architecture

```
                     tt_fds_wrapper
     ┌────────────────────────────────────────────────────┐
     │                                                    │
     │  t6_to_de (3 droop event sources)                  │
     │       │                                            │
     │  tt_fds_delay_model  ←── models propagation delay  │
     │       │                                            │
     │  ┌────▼──────────────────────────────────────┐    │
     │  │ tt_fds                                    │    │
     │  │                                           │    │
     │  │  ┌──────────────────────────────────────┐│    │
     │  │  │ input_bus_cdc FIFO (noc_clk→core_clk)││    │
     │  │  └──────────────────────────────────────┘│    │
     │  │                                           │    │
     │  │  For each of NUM_SOURCES=3 inputs:        │    │
     │  │    filter_count[AD_COUNTER_WIDTH=32]      │    │
     │  │    stable_data detector                   │    │
     │  │    pause_count logic                      │    │
     │  │                                           │    │
     │  │  Round-robin arbiter (8 CPU accessors)    │    │
     │  │    → tt_fds_regfile                       │    │
     │  │      (threshold / status regs)            │    │
     │  │                                           │    │
     │  │  o_interrupts[NUM_GROUP_IDS-1:0]          │    │
     │  │    (16 interrupt groups)                  │    │
     │  └───────────────────────────────────────────┘    │
     │       │                                           │
     │   fds_output_bus[BUS_OUT_W-1:0]  (4-bit)         │
     │       → de_to_t6[0][0]  (throttle signal)        │
     └────────────────────────────────────────────────────┘
```

Parameters:
```systemverilog
parameter int unsigned NUM_SOURCES      = 3;   // 3 droop event input sources
parameter int unsigned BUS_IN_W         = 12;  // 12-bit total input bus (3×4-bit bundle)
parameter int unsigned BUS_OUT_W        = 4;   // 4-bit output throttle bus
parameter int unsigned NUM_GROUP_IDS    = 16;  // 16 configurable interrupt groups
parameter int unsigned COUNTER_WIDTH    = 8;   // 8-bit per-source event counter
parameter int unsigned AD_COUNTER_WIDTH = 32;  // 32-bit anti-debounce counter
```

The FDS delay model (`tt_fds_delay_model`) inserts a configurable number of pipeline register stages on `t6_to_de` and `de_to_t6` paths to model the physical wire delay between the DE and Tensix tiles.

#### 6.11.3 Clock Domain Crossing

The FDS input bus arrives on `noc_clk` domain (from the DE sideband or Tensix droop events). The FDS core runs on `core_clk`. An async CDC FIFO bridges the two domains:

```systemverilog
input logic i_noc_clk,        // source clock for FDS input
input logic i_core_clk,       // destination clock for FDS processing
```

The filter counter (`filter_count_threshold`) also crosses from `noc_clk` to `core_clk` via a CDC handshake.

#### 6.11.4 Interrupt Groups

The FDS outputs 16 independent interrupt signals, one per configured group ID. Software configures each group's:
- **Source selection**: which of the 3 sensor inputs triggers this group
- **Threshold**: counter value at which the interrupt fires
- **Hysteresis**: minimum stable time before declaring a droop event valid

Interrupts feed into the overlay's interrupt aggregator (64-bit `NUM_INTERRUPTS`).

#### 6.11.5 FDS Register Interface

Each of the 8 cluster CPUs can access FDS registers independently. A round-robin arbiter (`arb_index`) selects the requester:
```systemverilog
input  logic [NUM_CLUSTER_CPUS-1:0]                     i_reg_cs,
input  logic [NUM_CLUSTER_CPUS-1:0]                     i_reg_wr_en,
input  logic [NUM_CLUSTER_CPUS-1:0][REG_ADDR_WIDTH-1:0] i_reg_addr,
input  logic [NUM_CLUSTER_CPUS-1:0][REG_DATA_WIDTH-1:0] i_reg_wr_data,
output logic [NUM_CLUSTER_CPUS-1:0]                     o_reg_wr_ack,
output logic [NUM_CLUSTER_CPUS-1:0]                     o_reg_rd_ack,
output logic [NUM_CLUSTER_CPUS-1:0][REG_DATA_WIDTH-1:0] o_reg_rd_data,
```

Access via ROCC `INSTR_FDS_REG_ACCESS` (CUSTOM_2 misc): `rs1=reg_addr`, `rs2=wr_data` (write) or read response in `rd`.

#### 6.11.6 SW Guide: FDS Programming

**Initialization:**
```
1. Write FDS threshold for each group via ROCC INSTR_FDS_REG_ACCESS
   reg_addr = FDS_GROUP_N_THRESHOLD_REG
   data     = desired anti-debounce count (0–2^32-1)

2. Write FDS source select per group
   reg_addr = FDS_GROUP_N_SOURCE_SEL_REG
   data     = bitmask of sources (bits [2:0] for 3 sources)

3. Enable interrupt groups
   reg_addr = FDS_INT_ENABLE_REG
   data     = bitmask of groups to enable (bits [15:0])

4. Unmask FDS interrupts in the overlay interrupt controller
   (write to tt_cluster_ctrl_reg: interrupt enable)
```

**Normal operation:**
- FDS runs autonomously. When droop is detected: hardware stalls Tensix via `de_to_t6`; interrupt fires to CPU after `filter_count_threshold` counts.
- Software ISR can read the current droop status: `FDS_STATUS_REG[NUM_SOURCES-1:0]`.
- Optionally adjust PLL frequency via SMN in response to droop events.

**Disable FDS (harvest/test mode):**
- Assert `i_harvest_en` (from harvest wrapper) → FDS bypasses all filtering; output bus held at 0 (no throttle).

---

### 6.12 Tensix and L1 Access from the Overlay

#### 6.12.1 How the Overlay Accesses Tensix

The overlay **does not directly drive** the Tensix matrix engine compute datapath. Tensix has its own configuration pipeline driven by the Dispatch Engine and its own instruction stream. The overlay's interaction with Tensix is via:

| Channel | Direction | Description |
|---------|-----------|-------------|
| `o_de_to_t6` | Overlay → Tensix | DE-originated sync pulses, throttle signals from FDS |
| `i_t6_to_de` | Tensix → Overlay | Completion events, droop event outputs |
| `o_smn_tensix_risc_reset_n` | Overlay → Tensix | RISC reset control (per the 8 harts) |
| `o_tensix_risc_reset_n` | Overlay → Tensix | SMN-controlled RISC reset output |
| `o_mem_config_to_t6` | Overlay → Tensix | SRAM timing configuration (from SMN memory controller) |
| `o_ai_clk` | Overlay → Tensix | AI clock (gated from PLL) |
| `o_ai_clk_reset_n` | Overlay → Tensix | AI clock domain reset |
| `o_t6_pll_pvt_slv_*` | Overlay → Tensix | PLL PVT slave APB (frequency select) |

The overlay is thus responsible for **power, clock, reset, and synchronization control** of the Tensix tile, not for its compute datapath.

#### 6.12.2 How the Overlay Accesses L1

The overlay is the **exclusive arbiter** of all L1 access. All paths to L1 SRAM go through the overlay's flex-client port infrastructure:

```
CPU hart                  → RW port (sub-port 0–3)
NoC atomic                → RW port (sub-port 4)
T6L1 debug                → RW port (sub-port 5)
iDMA back-end             → RD port (2× memory ports per BE)
NoC inbound write (snoop) → WR port
AXI bridge                → RW port (via tt_overlay_axi_to_l1_if)
APB bridge                → RW port (via tt_overlay_apb_to_l1_if)
```

The L1 flex-client arbiter inside `tt_t6_l1` resolves conflicts between these requestors using a fixed priority + round-robin policy. The `pre_sbank` interface presents the address early (before arbitration), and the `arb` interface confirms the winner.

#### 6.12.3 NoC Snoop to L1

For inbound NoC writes to local L1, the overlay uses `tt_overlay_noc_snoop_tl_master`:

```systemverilog
input  logic i_noc_mem_port_snoop_valid[NUM_SNOOP_MEM_PORTS-1:0],
input  logic [L1_CFG.SUB_ADDR_HI:L1_CFG.SUB_ADDR_LO] i_noc_mem_port_snoop_addr[...],
input  logic [L1_CFG.SUB_DATA_W-1:0]   i_noc_mem_port_snoop_data[...],
input  logic [L1_CFG.SUB_BYTE_W-1:0]   i_noc_mem_port_snoop_strb[...],
input  logic                            i_noc_mem_port_snoop_atomic[...],
output logic                            o_noc_mem_port_snoop_ready[...],
output logic                            o_noc_mem_port_snoop_inline_disable_cfg,
```

`o_noc_mem_port_snoop_inline_disable_cfg` is a software-programmable CSR bit that disables inline snoop processing (used for cache maintenance or diagnostic bypasses).

---

### 6.13 Harvest Support

When `i_overlay_harvested=1`:
1. EDC bypass active — EDC ring skips this node.
2. `o_noc_harvested=1` — router treats tile as mesh boundary.
3. `o_tensix_harvested=1` — Tensix held in reset.
4. Remap coordinates fed to NIU/router: `i_remap_x_size/y_size`, `i_remap_nodeid_x/y`.

---

### 6.14 Register Access via APB / EDC Bridge

**Hardware:** `tt_overlay_wrapper_reg_logic`, `tt_overlay_reg_xbar_slave_decode`, `tt_overlay_edc_apb_bridge`

Three paths reach the 26-bit APB register space:
1. **EDC ring** (out-of-band): EDC packet → `tt_overlay_edc_apb_bridge` → internal APB
2. **NIU register port** (in-band): NoC packet → `o_ext_reg_addr/rd_en/wr_en`
3. **Direct APB**: `i_reg_addr/wrdata/wren/rden` (from SMN or trinity top)

| Slave | Contents |
|-------|----------|
| Cluster control CSR | CPU reset vectors, power state, PC capture |
| T6 L1 CSR | Cache enable, ECC config, flush |
| LLK tile counters | Remote counter thresholds |
| Cache controller | Replacement policy, prefetch config |
| Debug module APB (12-bit) | CPU JTAG/debugger interface |
| SMN registers | SMN status, straps |
| T6L1 slave | L1 address window config |
| NEO AWM wrap | Address window manager |
| FDS registers | Droop thresholds and status |

---

### 6.15 iJTAG / DFD Interface

iJTAG scan chain pass-through. `i_ijtag_si_to_dfd` → overlay internal DFT cells → `o_ijtag_so_from_dfd`. The SMN also has its own JTAG port (`i_tck`, `i_trstn`, `i_tdi`…) which can override SMN-controlled signals via `o_jtag_ctrl_ovrd`.

---

## 7. Control Path: Processor to Data Bus

### 7.1 CPU-to-NoC Write Path

```
RISC-V CPU (hart N)
    │  store instruction → NoC address space
    ▼
  tt_overlay_cpu_wrapper
    │  builds head flit: {x_coord, y_coord, addr, cmd=WRITE, vc}
    ▼
  tt_overlay_flit_vc_arb   ← checks i_req_head_flit_vc_popcount
    │  req_head_flit → arbitrated to NIU injection port
    ▼
  NIU (tt_overlay_noc_niu_router → niu)
    │  tags transaction, applies credit check
    ▼
  Router (DOR: X first, then Y)
    │  o_flit_out_req_{N/S/E/W}
    ▼  ... (hop-by-hop) ...
  Destination NIU → L1 WR port or DRAM/AXI
```

### 7.2 iDMA-to-NoC Write Path

```
ROCC instruction (INSTR_ISSUE, CUSTOM_0)
    │
    ▼
  tt_rocc_cmd_buf → builds iDMA flit (src: L1 addr, dst: NoC addr)
    │  i_req_head_flit[client_id]
    ▼
  tt_idma_cmd_buffer_frontend  ← 24:2 arbiter
    │  idma_req_t to back-end
    ▼
  tt_idma_backend_r_init_rw_obi_top
    │  reads src from o_t6_l1_arb_rd_intf (OBI port)
    │  i_mem_rdata → payload
    ▼
  NoC flit injection at NIU → mesh → destination L1 WR port
```

### 7.3 NoC-to-L1 Inbound Write (Snoop) Path

```
NoC flit arrives at local router
    │
    ▼
  Local NIU ejects flit
    │
    ▼
  tt_overlay_noc_snoop_tl_master
    │  i_noc_mem_port_snoop_valid / addr / data
    ▼
  o_t6_l1_arb_wr_intf[port]  → L1 WR port → SRAM write
```

---

## 8. Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `OVERLAY_VERSION` | 0 | 6-bit version stamp |
| `L1_CFG` | `NEO_L1_CFG` | L1 cache configuration |
| `DISPATCH_INST` | `1'b0` | Dispatch Engine variant |
| `HAS_AICLK_PLL` | `1'b1` | Include AI clock PLL logic |
| `HAS_SMN_INST` | `1'b1` | Include SMN node |
| `HAS_EDC_INST` | `1'b0` | Include EDC repeater |
| `IDMA_DFC_EN` | `1'b0` | iDMA data format conversion |
| `IDMA_ENABLE_TIMING_STAGES` | `1'b1` | iDMA pipeline register slices |
| `NUM_CS_HARTS` | 1 | Context-switch harts |
| `EDC_IN_REP_NUM` | 1 | EDC ingress repeater count |
| `EDC_REP_NUM` | 1 | EDC internal repeater count |
| `EDC_OUT_REP_NUM` | 1 | EDC egress repeater count |
| `FDS_NUM_SOURCES` | 3 | FDS sensor source count |
| `SMN_TENSIX_REPEATER_OVERLAY_SOUTH_SIDE` | 3 | SMN S-side repeater count |
| `NOC_FLIT_REPEATERS_NORTH_TO_SOUTH` | pkg | N→S flit pipeline stages |

---

## 9. Clock and Reset Summary

```
i_aiclk ──────────┐
i_ai_aon_clk ─────┤ tt_overlay_clock_reset_ctrl
i_nocclk ─────────┤  → o_core_clk   (CPU pipeline, L1)
i_ref_clk ────────┤  → o_ai_clk     (Tensix engine)
i_core_clk ───────┘  → o_uncore_clk (uncore logic)
                      → o_noc_clk_aon (NoC AON)
                      → o_ref_clk    (PLL reference)

SMN controls:
  o_smn_ai_clk_reset_n
  o_smn_noc_clk_reset_n
  o_smn_tensix_risc_reset_n[7:0]
  o_smn_ai_clk_en / force_ref / pll_clk_mux
  o_smn_pll_soft_reset_n
```

---

## 10. APB Register Interfaces

| Port | Address Width | Data Width | Purpose |
|------|--------------|------------|---------|
| Main APB | 26 bits | 32 bits | Cluster ctrl, cache, PLL, FDS |
| Debug APB | 12 bits | 32 bits | RISC-V debug module |
| Flex-client CSR APB | 9 bits | 32 bits | L1 flex-client config |
| PLL PVT slave APB | 26 bits | 32 bits | T6 PLL programming |

Register files:

| Include | Contents |
|---------|----------|
| `tt_cluster_ctrl_reg.svh` | CPU cluster control, boot config |
| `tt_cluster_ctrl_t6_l1_csr_reg.svh` | L1 enable / ECC / flush |
| `tt_overlay_llk_tile_counters_reg.svh` | LLK counter thresholds |
| `tt_cache_controller_reg.svh` | Cache replacement, prefetch |
| `tt_debug_module_apb_reg.svh` | RISC-V debug |
| `smn_reg.svh` | SMN status and straps |
| `tt_t6l1_slv_reg.svh` | L1 address window |
| `tt_neo_awm_wrap_reg.svh` | Address window manager |

---

## 11. Worked Example: CPU Issues a NoC Write

**Scenario:** RISC-V hart 0 on tile (X=1, Y=2) writes 64 bytes to tile (X=3, Y=4) L1.

1. Hart 0: `sd a0, 0(a1)` where `a1` maps to NoC address for tile (3,4) offset `0x1000`.
2. `tt_overlay_cpu_wrapper` builds flit: `x_coord=3, y_coord=4, addr=0x1000, cmd=WRITE, vc=unicast_req`.
3. `tt_overlay_flit_vc_arb` checks `i_req_head_flit_vc_popcount > 0`; grants injection.
4. NIU at (1,2) tags transaction with ID from 5-bit TRID space.
5. Router (1,2): `x=3 > local_x=1` → East hop.
6. Router (2,2): `x=3 > local_x=2` → East hop.
7. Router (3,2): `x=3 == local_x=3`, `y=4 > local_y=2` → South hop.
8. Router (3,3): South hop.
9. Router (3,4): `x=3==3`, `y=4==4` → local delivery to NIU.
10. NIU ejects flit; snoop master writes `0x1000` into L1 via WR port.
11. Response flit returns to (1,2); `id_outgoing_writes_count` cleared.

---

## 12. Verification Checklist

- [ ] **CDC**: All async FIFOs (core↔noc, noc↔fds core_clk) verified with waivers in `tt_overlay_ext_reg_cdc.sv`, `tt_overlay_niu_reg_cdc.sv`.
- [ ] **Reset sequencing**: `RESET_CYCLES=16` hold minimum per domain before deassertion.
- [ ] **EDC bypass**: With `HAS_EDC_INST=0`, all-zero drive confirmed; no X-propagation.
- [ ] **Harvest isolation**: `i_overlay_harvested=1` → `o_tensix_harvested=1`, EDC bypass, `o_noc_harvested=1` within 1 clock.
- [ ] **iDMA 2D stride**: Verify multi-row tiled transfer with non-unity strides completes without address wrap error.
- [ ] **iDMA 24-client FIFO full**: All 24 clients filled (FIFO_DEPTH=42) — back-pressure asserted correctly.
- [ ] **iDMA transaction ID wrap**: Transaction ID field is 5 bits (32 IDs); verify wrap-around does not produce spurious interrupt.
- [ ] **ROCC INSTR_ISSUE**: Valid head flit injected with correct VC, TRID, src/dst address after PUSH sequence.
- [ ] **ROCC context switch**: CS_SAVE/CS_RESTORE roundtrip produces bit-identical addrgen state.
- [ ] **NoC fence**: `o_noc_fence_req` stalls CPU; `i_noc_fence_ack` deasserts stall after all writes committed.
- [ ] **LLK counter overflow**: Counter wraps without spurious interrupt.
- [ ] **SMN daisy chain**: SMN write reaches target tile at correct column Y position; response returns.
- [ ] **FDS throttle**: With `i_harvest_en=1`, `fds_output_bus` is forced to 0; no false throttle.
- [ ] **FDS CDC**: `filter_count_threshold` crosses noc→core_clk correctly; no metastability.
- [ ] **FDS interrupt**: `o_interrupts[group_N]` fires within expected cycles after threshold reached.
- [ ] **Dispatch DE↔T6**: `de_to_t6` FDS-controlled output matches `fds_output_bus` after DE `IS_DISPATCH` wiring.
- [ ] **Dispatch clock distribution**: `o_noc_clk_south` active before any Tensix tile below can clock.
- [ ] **L1 pre_sbank vs arb timing**: Address presented on pre_sbank exactly 1 cycle before arb grant confirmed.
- [ ] **APB decode**: All 26-bit APB regions decode to correct slave without alias.
- [ ] **iJTAG continuity**: `i_ijtag_si_to_dfd` → `o_ijtag_so_from_dfd` after expected shift cycle count.

---

## 13. Key RTL File Index

| Module | File | Notes |
|--------|------|-------|
| `tt_overlay_wrapper` | `tt_rtl/overlay/rtl/tt_overlay_wrapper.sv` | Top-level overlay |
| `tt_overlay_pkg` | `tt_rtl/overlay/rtl/tt_overlay_pkg.sv` | Constants, CSR includes |
| `tt_overlay_noc_wrap` | `tt_rtl/overlay/rtl/tt_overlay_noc_wrap.sv` | NoC 4-port wrap + EDC |
| `tt_overlay_noc_niu_router` | `tt_rtl/overlay/rtl/tt_overlay_noc_niu_router.sv` | NIU + router |
| `tt_overlay_cpu_wrapper` | `tt_rtl/overlay/rtl/tt_overlay_cpu_wrapper.sv` | 8× RISC-V cluster |
| `tt_overlay_clock_reset_ctrl` | `tt_rtl/overlay/rtl/tt_overlay_clock_reset_ctrl.sv` | Clock gating + reset |
| `tt_overlay_smn_wrapper` | `tt_rtl/overlay/rtl/tt_overlay_smn_wrapper.sv` | SMN AXI4-Lite node |
| `tt_overlay_edc_wrapper` | `tt_rtl/overlay/rtl/tt_overlay_edc_wrapper.sv` | EDC repeater chain |
| `tt_overlay_edc_apb_bridge` | `tt_rtl/overlay/rtl/tt_overlay_edc_apb_bridge.sv` | EDC→APB translation |
| `tt_overlay_memory_wrapper` | `tt_rtl/overlay/rtl/memories/tt_overlay_memory_wrapper.sv` | L1 SRAM macros |
| `tt_overlay_axi_to_l1_if` | `tt_rtl/overlay/rtl/tt_overlay_axi_to_l1_if.sv` | AXI→L1 bridge |
| `tt_overlay_apb_to_l1_if` | `tt_rtl/overlay/rtl/tt_overlay_apb_to_l1_if.sv` | APB→L1 bridge |
| `tt_overlay_noc_snoop_tl_master` | `tt_rtl/overlay/rtl/tt_overlay_noc_snoop_tl_master.sv` | NoC→L1 snoop WR |
| `tt_overlay_flex_client_csr_wrapper` | `tt_rtl/overlay/rtl/tt_overlay_flex_client_csr_wrapper.sv` | L1 flex CSR APB |
| `tt_idma_wrapper` | `tt_rtl/overlay/rtl/idma/tt_idma_wrapper.sv` | iDMA engine top |
| `tt_idma_pkg` | `tt_rtl/overlay/rtl/idma/tt_idma_pkg.sv` | iDMA constants |
| `tt_idma_cmd_buffer_frontend` | `tt_rtl/overlay/rtl/idma/tt_idma_cmd_buffer_frontend.sv` | 24-client frontend |
| `tt_idma_backend_r_init_rw_obi_top` | `tt_rtl/overlay/rtl/idma/tt_idma_backend_r_init_rw_obi_top.sv` | iDMA OBI back-end |
| `tt_rocc_accel` | `tt_rtl/overlay/rtl/accelerators/tt_rocc_accel.sv` | ROCC top per-hart |
| `tt_rocc_pkg` | `tt_rtl/overlay/rtl/accelerators/tt_rocc_pkg.sv` | ROCC opcodes/constants |
| `tt_rocc_cmd_buf` | `tt_rtl/overlay/rtl/accelerators/tt_rocc_cmd_buf.sv` | Command buffer |
| `tt_rocc_address_gen` | `tt_rtl/overlay/rtl/accelerators/tt_rocc_address_gen.sv` | Address generator |
| `tt_rocc_context_switch` | `tt_rtl/overlay/rtl/accelerators/tt_rocc_context_switch.sv` | Context save/restore |
| `tt_rocc_interrupt_event` | `tt_rtl/overlay/rtl/accelerators/tt_rocc_interrupt_event.sv` | Completion interrupt |
| `tt_overlay_tile_counters_with_comparators` | `tt_rtl/overlay/rtl/tt_overlay_tile_counters_with_comparators.sv` | LLK counters |
| `tt_fds_wrapper` | `tt_rtl/overlay/rtl/fds/tt_fds_wrapper.sv` | FDS top |
| `tt_fds` | `tt_rtl/overlay/rtl/fds/tt_fds.sv` | FDS core |
| `tt_fds_regfile` | `tt_rtl/overlay/rtl/fds/tt_fds_regfile.sv` | FDS registers |
| `tt_fds_delay_model` | `tt_rtl/overlay/rtl/fds/tt_fds_delay_model.sv` | DE↔T6 delay model |
| `tt_dispatch_engine` | `tt_rtl/overlay/rtl/quasar_dispatch/tt_dispatch_engine.sv` | Dispatch Engine top |
| `tt_disp_eng_overlay_wrapper` | `tt_rtl/overlay/rtl/quasar_dispatch/tt_disp_eng_overlay_wrapper.sv` | DE overlay variant |
| `tt_disp_eng_l1_partition` | `tt_rtl/overlay/rtl/quasar_dispatch/tt_disp_eng_l1_partition.sv` | DE L1 partition |
| `tt_disp_eng_overlay_noc_wrap` | `tt_rtl/overlay/rtl/quasar_dispatch/tt_disp_eng_overlay_noc_wrap.sv` | DE NoC wrap |
| `tt_overlay_wrapper_reg_logic` | `tt_rtl/overlay/rtl/tt_overlay_wrapper_reg_logic.sv` | APB register logic |
| `tt_overlay_reg_xbar_slave_decode` | `tt_rtl/overlay/rtl/tt_overlay_reg_xbar_slave_decode.sv` | Register demux |
| `tt_overlay_flit_vc_arb` | `tt_rtl/overlay/rtl/tt_overlay_flit_vc_arb.sv` | Flit VC arbiter |
| `tt_overlay_wrapper_harvest_trinity` | `tt_rtl/overlay/rtl/tt_overlay_wrapper_harvest_trinity.sv` | Harvest logic |
| `tt_overlay_wrapper_dfx` | `rtl/dfx/tt_overlay_wrapper_dfx.sv` | iJTAG DFX wrapper |
| `tt_noc_overlay_edc_repeater` | `tt_rtl/tt_noc/rtl/noc/tt_noc_overlay_edc_repeater.sv` | EDC repeater (NoC) |

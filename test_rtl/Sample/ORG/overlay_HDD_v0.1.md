# Trinity Overlay — Hardware Design Document

**Document:** overlay_HDD_v0.1.md
**Chip:** Trinity (4×5 NoC Mesh)
**RTL Snapshot:** 20260221
**Primary Sources:** `tt_overlay_wrapper.sv`, `tt_overlay_pkg.sv`, `tt_overlay_noc_wrap.sv`, `tt_overlay_smn_wrapper.sv`, `tt_overlay_clock_reset_ctrl.sv`, `tt_overlay_edc_wrapper.sv`, `tt_overlay_noc_niu_router.sv`
**Audience:** Verification Engineers · Software Engineers · Hardware Engineers

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v0.1 | 2026-03-17 | (RTL-derived) | Initial release |

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
   - 6.4 [L1 Cache (T6 L1)](#64-l1-cache-t6-l1)
   - 6.5 [iDMA Engine](#65-idma-engine)
   - 6.6 [ROCC Accelerator Interface](#66-rocc-accelerator-interface)
   - 6.7 [LLK (Low-Latency Kernel) Interface](#67-llk-low-latency-kernel-interface)
   - 6.8 [Dispatch Engine](#68-dispatch-engine)
   - 6.9 [SMN (System Maintenance Network)](#69-smn-system-maintenance-network)
   - 6.10 [EDC (Error Detection and Correction)](#610-edc-error-detection-and-correction)
   - 6.11 [FDS (Frequency/Droop Sensor)](#611-fds-frequencydroop-sensor)
   - 6.12 [Harvest Support](#612-harvest-support)
   - 6.13 [Register Access via APB / EDC Bridge](#613-register-access-via-apb--edc-bridge)
   - 6.14 [iJTAG / DFD Interface](#614-ijtag--dfd-interface)
7. [Control Path: Processor to Data Bus](#7-control-path-processor-to-data-bus)
   - 7.1 [CPU-to-NoC Write Path (Example)](#71-cpu-to-noc-write-path-example)
   - 7.2 [NoC-to-CPU Read Response Path](#72-noc-to-cpu-read-response-path)
8. [Key Parameters](#8-key-parameters)
9. [Clock and Reset Summary](#9-clock-and-reset-summary)
10. [APB Register Interfaces](#10-apb-register-interfaces)
11. [Worked Example: CPU Issues a NoC Write](#11-worked-example-cpu-issues-a-noc-write)
12. [Verification Checklist](#12-verification-checklist)
13. [Key RTL File Index](#13-key-rtl-file-index)

---

## 1. Overview

The **Overlay** is a shared infrastructure wrapper that sits alongside each Tensix compute tile in the Trinity 4×5 NoC mesh. It is the glue between the **RISC-V cluster CPUs**, the **Tensix tensor cores**, the **L1 cache**, and the **NoC mesh**. Every Tensix row (Y=1 to Y=4) and the Dispatch Engine tiles (Y=0, X=0 and X=3) each instantiate one overlay.

The overlay provides:

| Function | Hardware |
|----------|----------|
| Cluster CPU management | 8× RISC-V cores + uncore, reset, clock gating |
| NoC connectivity | NIU + router wrap, flit arbitration, VC management |
| L1 data and instruction cache | T6 L1 cache banks, flex client ports |
| Bulk DMA | iDMA engine (multiple back-ends) |
| Accelerator co-processor link | ROCC command/address-gen engines |
| Kernel counter synchronization | LLK remote counter interface |
| Chip management sideband | SMN (N↔S daisy-chain ring) |
| Error detection | EDC1 serial bus repeaters and CSRs |
| Frequency / droop sensing | FDS with APB register access |
| Harvest isolation | Per-tile harvest bypass and mesh remap |
| Debug | iJTAG/DFD scan chain pass-through |

---

## 2. Overlay Position in Trinity Grid

```
     X=0          X=1          X=2          X=3
Y=0  [DRAM/AXI]  [DISPATCH W] [DISPATCH E] [DRAM/AXI]   <-- NOC2AXI / Dispatch row
Y=1  [TENSIX]    [TENSIX]     [TENSIX]     [TENSIX]      <-- overlay row 1
Y=2  [TENSIX]    [TENSIX]     [TENSIX]     [TENSIX]      <-- overlay row 2
Y=3  [TENSIX]    [TENSIX]     [TENSIX]     [TENSIX]      <-- overlay row 3
Y=4  [TENSIX]    [TENSIX]     [TENSIX]     [TENSIX]      <-- overlay row 4
```

Each `[TENSIX]` cell instantiates:
- `tt_overlay_wrapper` — the overlay module documented here
- `tt_tensix_tile` (or Neo variant) — the matrix engine
- `tt_t6_l1` — L1 cache macros

The overlay wrapper is the **control and connectivity hub** for the entire tile.

---

## 3. Feature Summary

| Feature | Description | Key Parameter / Signal |
|---------|-------------|----------------------|
| Multi-clock | 5 clock domains per tile (ai_aon, aiclk, nocclk, ref, core/uncore) | `i_core_clk`, `i_aiclk`, `i_nocclk`, `i_ref_clk` |
| Reset control | Per-CPU and per-domain resets, gated at overlay | `i_core_clk_reset_n_pre_sync[7:0]` |
| NoC NIU | Network Interface Unit connecting CPUs/DMA to mesh | `i_flit_in_req_*`, `o_flit_out_req_*` |
| L1 Cache | Flex-client RW/RD/WR ports to T6 L1 macros | `o_t6_l1_arb_rw_intf`, `o_t6_l1_arb_rd_intf` |
| iDMA | Internal DMA for scatter/gather transfers | `IDMA_DFC_EN`, `IDMA_ENABLE_TIMING_STAGES` |
| ROCC | RISC-V ROCC co-processor accelerator interface | `tt_rocc_accel`, `tt_rocc_cmd_buf` |
| LLK counters | 4× remote counter channels per tile | `o_remote_counter_sel[3:0]`, `o_remote_rts[3:0]` |
| Dispatch link | DE↔T6 side-band signals | `o_de_to_t6`, `o_t6_to_de` |
| SMN | System Maintenance Network N↔S daisy chain | `HAS_SMN_INST`, `i_smn_req_n_s` |
| EDC | EDC1 serial bus with in/out/loopback repeaters | `HAS_EDC_INST`, `EDC_IN_REP_NUM` |
| FDS | Droop monitoring sensors (3 sources) | `FDS_NUM_SOURCES=3`, `FDS_BUS_IN_W=12` |
| Harvest | Per-tile harvested signal + mesh remap | `i_overlay_harvested`, `i_remap_x_size` |
| APB | 26-bit address, 32-bit data register bus | `REG_APB_PORT_ADDR_WIDTH=26` |
| Debug APB | 12-bit address debug module APB | `DEBUG_APB_PORT_ADDR_WIDTH=12` |
| iJTAG | DFD scan chain pass-through | `i_ijtag_tck_to_dfd`, `o_ijtag_so_from_dfd` |

---

## 4. Block Diagram

```
                        ┌─────────────────────────────────────────────────────────┐
                        │                   tt_overlay_wrapper                    │
                        │                                                         │
  i_smn_req_n_s ───────►│   ┌──────────────┐   APB   ┌───────────────────────┐   │
  o_smn_req_n_s ◄───────│   │ SMN Wrapper  │◄───────►│   Cluster CPU         │   │
                        │   │ (smn_wrapper)│         │ (8× RISC-V + uncore)  │   │
                        │   └──────┬───────┘         └──────────┬────────────┘   │
  i_aiclk ─────────────►│          │                            │ ROCC / LLK      │
  i_nocclk ────────────►│   ┌──────▼───────┐         ┌─────────▼────────────┐   │
  i_ref_clk ───────────►│   │ Clock/Reset  │         │    iDMA Engine        │   │
  i_core_clk ──────────►│   │  Controller  │         │ (scatter/gather DMA)  │   │
                        │   └──────────────┘         └─────────┬────────────┘   │
                        │                                       │ req_head_flit   │
  edc_ingress ─────────►│   ┌──────────────┐         ┌─────────▼────────────┐   │
  edc_egress ◄──────────│   │ EDC Wrapper  │         │   NoC NIU / Router   │   │
                        │   │ (in/out/lbk  │         │  (tt_overlay_noc_    │   │
                        │   │  repeaters)  │         │   noc_niu_router)     │   │
                        │   └──────────────┘         └──┬──────────┬────────┘   │
                        │                               │          │              │
  i_flit_in_req_N ─────►│                        flit N/S/E/W mesh ports          │
  o_flit_out_req_N ◄────│                                          │              │
  i_flit_in_req_S ─────►│   ┌──────────────┐    L1 flex  ┌────────▼────────┐   │
  o_flit_out_req_S ◄────│   │  FDS Wrapper │    client   │   L1 Cache      │   │
  ... (E, W) ...        │   │ (droop sense)│    ports    │ (T6 L1 macros)  │   │
                        │   └──────────────┘             └─────────────────┘   │
                        │                                                         │
  i_interrupts ─────────►│  External interrupt aggregation (64 total, 8 ext)      │
  o_noc_fence_req ◄──────│  NoC fence request / ack (per CPU)                     │
                        └─────────────────────────────────────────────────────────┘
```

---

## 5. Sub-module Hierarchy

```
tt_overlay_wrapper
├── tt_overlay_clock_reset_ctrl       — clock gating, reset synchronization
├── tt_overlay_smn_wrapper            — SMN N↔S daisy-chain node
│     └── tt_smn (conditional)        — SMN master/slave instance
├── tt_overlay_edc_wrapper            — EDC1 repeater chain (in/out/loopback)
│     └── tt_edc1_serial_bus_repeater — (when HAS_EDC_INST==1)
├── tt_overlay_noc_wrap               — NoC-side wrapper
│     └── tt_overlay_noc_niu_router   — NIU + router integration
│           └── tt_trinity_noc_niu_router_inst
│                 └── noc_niu_router_inst
│                       └── niu       — Network Interface Unit
├── tt_overlay_cpu_wrapper            — RISC-V cluster CPUs
│     └── (8× CV64/CS harts)
├── tt_overlay_memory_wrapper         — L1 SRAM macro wrappers + EDC repeaters
├── tt_overlay_flex_client_csr_wrapper — L1 flex client CSR APB
├── tt_idma_wrapper                   — iDMA engine
│     └── tt_idma_cmd_buffer_frontend
│     └── tt_idma_backend_r_init_rw_obi_top
├── tt_rocc_accel                     — ROCC accelerator
│     └── tt_rocc_cmd_buf
│     └── tt_rocc_address_gen
│     └── tt_rocc_context_switch
├── tt_overlay_tile_counters          — LLK remote tile counter / comparators
├── tt_fds_wrapper                    — FDS droop sensor
│     └── tt_fds
│     └── tt_fds_regfile
├── tt_overlay_edc_apb_bridge         — EDC-to-APB register bridge
├── tt_overlay_wrapper_reg_logic      — APB register crossbar / decode
└── tt_overlay_reg_xbar_slave_decode  — Register slave demux
```

**Source:** [`tt_rtl/overlay/rtl/tt_overlay_wrapper.sv`](../tt_rtl/overlay/rtl/tt_overlay_wrapper.sv)

---

## 6. Feature Details

### 6.1 Multi-Clock Domain and Reset Management

**Hardware:** `tt_overlay_clock_reset_ctrl`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_clock_reset_ctrl.sv`](../tt_rtl/overlay/rtl/tt_overlay_clock_reset_ctrl.sv)

The overlay operates across five clock domains:

| Domain | Source Signal | Usage |
|--------|--------------|-------|
| `core_clk` / `uncore_clk` | `i_core_clk` (gated) | RISC-V CPU pipeline, L1 cache |
| `aiclk` (AI clock) | `i_aiclk` (from PLL) | Tensix matrix engine |
| `ai_aon_clk` | `i_ai_aon_clk` | Always-on uncore path |
| `nocclk` | `i_nocclk` | NoC flit datapath |
| `ref_clk` | `i_ref_clk` | PLL reference, reset synchronization |

The clock/reset controller:
- Applies hardware clock enables (`i_core_clk_en`, `i_uncore_clk_en`, `i_ovl_debug_clk_en`)
- Outputs gated clocks to sub-modules: `o_core_clk`, `o_uncore_clk`, `o_ai_clk`, `o_noc_clk_aon`
- Synchronizes resets per-CPU: `i_core_clk_reset_n_pre_sync[NUM_CLUSTER_CPUS-1:0]`
- Drives SMN-controlled reset outputs: `o_smn_ai_clk_reset_n`, `o_smn_noc_clk_reset_n`, `o_smn_tensix_risc_reset_n`
- Outputs `o_core_clk_gated` and `o_noc_clk_en` to trinity top level

**Reset cycle constants** (from `tt_overlay_pkg.sv`):

```systemverilog
localparam int unsigned REF_CLK_RESET_CYCLES    = 16;
localparam int unsigned CORE_CLK_RESET_CYCLES   = 16;
localparam int unsigned UNCORE_CLK_RESET_CYCLES = 16;
localparam int unsigned AI_CLK_RESET_CYCLES     = 16;
localparam int unsigned DD_CLK_RESET_CYCLES     = 16;
```

---

### 6.2 NoC Interface — NIU and Router

**Hardware:** `tt_overlay_noc_wrap` → `tt_overlay_noc_niu_router`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_noc_wrap.sv`](../tt_rtl/overlay/rtl/tt_overlay_noc_wrap.sv)

The NoC wrap provides the tile's four-port mesh interface (North, South, East, West) plus a local injection/ejection port through the NIU:

```systemverilog
// Mesh ports (per direction):
input  tt_noc_pkg::noc_req_t   i_flit_in_req_north,
output tt_noc_pkg::noc_resp_t  o_flit_in_resp_north,
output tt_noc_pkg::noc_req_t   o_flit_out_req_north,
input  tt_noc_pkg::noc_resp_t  i_flit_out_resp_north,
// ... (south, east, west) ...
```

Key behaviors:
- **Flit repeaters** inserted on N↔S paths with configurable pipeline depth:
  ```systemverilog
  parameter int unsigned NOC_FLIT_REPEATERS_NORTH_TO_SOUTH = ...;
  parameter int unsigned NOC_FLIT_REPEATERS_SOUTH_TO_NORTH = ...;
  ```
- **Node ID distribution:** `i_local_nodeid_x`, `i_local_nodeid_y` driven as constants at instantiation. The overlay outputs `o_local_nodeid_x_to_t6_l1_partition` and `o_nxt_node_id_x/y` for downstream use.
- **EDC loopback path** through `loopback_edc_ingress_intf / loopback_edc_egress_intf` (Trinity only).
- **Harvest remap** inputs: `i_remap_x_size`, `i_remap_y_size`, `i_remap_nodeid_x`, `i_remap_nodeid_y` feed mesh boundary override directly into the NIU/router when `i_overlay_harvested` is asserted.

---

### 6.3 Cluster CPU Subsystem (RISC-V Cores)

**Hardware:** `tt_overlay_cpu_wrapper`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_cpu_wrapper.sv`](../tt_rtl/overlay/rtl/tt_overlay_cpu_wrapper.sv)

Key constants:
```systemverilog
localparam int unsigned NUM_CLUSTER_CPUS = 8;   // 8 RISC-V harts per tile
localparam int unsigned NUM_INTERRUPTS   = 64;  // 64 total (56 internal + 8 external)
localparam int unsigned NUM_EXT_INTERRUPTS = 8;
localparam int unsigned RESET_VECTOR_WIDTH = 52;
```

- The CPU wrapper interfaces to the L1 cache via flex-client **RW sub-ports**:
  ```
  NUM_RW_SUB_PORTS_CPU        = 4
  NUM_RW_SUB_PORTS_T6L1_DEBUG = 1
  NUM_RW_SUB_PORTS_NOC_ATOMIC = 1
  NUM_RW_SUB_PORTS_OVERLAY    = 5  (CPU + debug)
  ```
- The CPU issues NoC transactions by passing **request head flits** to the overlay's flit arbitration (`tt_overlay_flit_vc_arb`), which selects among virtual channels (VCs) and injects into the NIU.
- Debug APB port (12-bit address) is connected directly from the overlay register crossbar to the CPU's debug module.

---

### 6.4 L1 Cache (T6 L1)

**Hardware:** `tt_overlay_memory_wrapper` + `tt_t6_l1` (outside overlay, driven via flex-client interfaces)
**Source:** [`tt_rtl/overlay/rtl/memories/tt_overlay_memory_wrapper.sv`](../tt_rtl/overlay/rtl/memories/tt_overlay_memory_wrapper.sv)

The overlay drives three sets of L1 flex-client interfaces:

| Interface | Type | Width | Users |
|-----------|------|-------|-------|
| `o_t6_l1_arb_rw_intf[NUM_RW_PORTS-1:0]` | RW (read-write) | sub-port × 4 | CPUs + NoC atomic |
| `o_t6_l1_arb_rd_intf[NUM_RD_PORTS-1:0]` | RD (read-only) | sub-port | iDMA read back-end |
| `o_t6_l1_arb_wr_intf[NUM_WR_PORTS-1:0]` | WR (write-only) | sub-port | NoC snoop writes |

L1 cache parameters:
```systemverilog
// D-cache data: 16 macros × 144-bit wide, 128-entry deep (7-bit addr)
NUM_L1_DCACHE_DATA_MACROS = 16;  L1_DCACHE_DATA_DATA_WIDTH = 144;

// D-cache tag: 8 macros × 100-bit wide, 32-entry deep (5-bit addr)
NUM_L1_DCACHE_TAG_MACROS  = 8;   L1_DCACHE_TAG_DATA_WIDTH = 100;

// I-cache data: 16 macros × 66-bit wide (33-bit per way, 2-way), 256-entry deep
NUM_L1_ICACHE_DATA_MACROS = 16;  L1_ICACHE_DATA_DATA_WIDTH = 66;

// I-cache tag: 8 macros × 86-bit wide (43-bit per way, 2-way)
NUM_L1_ICACHE_TAG_MACROS  = 8;   L1_ICACHE_TAG_DATA_WIDTH = 86;
```

ECC/parity is embedded in each macro width (8-bit ECC per 64-bit data word for D-cache; parity for I-cache).

---

### 6.5 iDMA Engine

**Hardware:** `tt_idma_wrapper`
**Source:** [`tt_rtl/overlay/rtl/idma/tt_idma_wrapper.sv`](../tt_rtl/overlay/rtl/idma/tt_idma_wrapper.sv)

The iDMA (internal DMA) engine provides high-throughput scatter/gather data movement between L1 and remote NoC endpoints. It is parameterized at compile time:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `IDMA_DFC_EN` | `1'b0` | Enable DFC (Data Format Conversion) path |
| `IDMA_ENABLE_TIMING_STAGES` | `1'b1` | Insert pipeline stages for timing closure |
| `IDMA_NUM_BE` | `NUM_RD_SUB_PORTS` | Number of back-end read engines |

The iDMA front-end receives commands from the ROCC command buffer interface or CPU APB registers. Back-end modules (`tt_idma_backend_r_init_rw_obi_top`) arbitrate L1 read ports and inject response flits via the NoC NIU.

---

### 6.6 ROCC Accelerator Interface

**Hardware:** `tt_rocc_accel`, `tt_rocc_cmd_buf`, `tt_rocc_address_gen`
**Source:** [`tt_rtl/overlay/rtl/accelerators/`](../tt_rtl/overlay/rtl/accelerators/)

ROCC is the RISC-V ROCC (Rocket Custom Co-processor) extension interface connecting the RISC-V core to on-tile accelerators (Tensix). The overlay implements:

- **Command buffer** (`tt_rocc_cmd_buf`): queues ROCC instructions from the CPU for the accelerator.
- **Address generator** (`tt_rocc_address_gen`): computes strided / multi-dimensional source/destination addresses for bulk transfers.
- **Context switch** (`tt_rocc_context_switch`): saves/restores accelerator state when the OS context-switches (uses dedicated L1 memory).
- **Interrupt events** (`tt_rocc_interrupt_event`): generates interrupt to the CPU on transfer completion.

ROCC register interface CDC depth:
```systemverilog
localparam int unsigned ROCC_REG_INTF_CDC_DEPTH = 1;
```

---

### 6.7 LLK (Low-Latency Kernel) Interface

**Hardware:** `tt_overlay_tile_counters_with_comparators`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_tile_counters_with_comparators.sv`](../tt_rtl/overlay/rtl/tt_overlay_tile_counters_with_comparators.sv)

The LLK interface enables **remote tile synchronization** without CPU involvement. The Dispatch Engine and neighboring tiles push counter increments directly to a Tensix tile's counter set. When a threshold is crossed, an interrupt fires to the local RISC-V cores.

```systemverilog
// Per-tile remote counter interface (4 channels)
output [NUM_TENSIX_CORES-1:0] [LLK_IF_REMOTE_COUNTER_SEL_WIDTH-1:0] o_remote_counter_sel,
output [NUM_TENSIX_CORES-1:0] [2:0]                                  o_remote_idx,
output [NUM_TENSIX_CORES-1:0] [LLK_IF_COUNTER_WIDTH-1:0]             o_remote_incr,
output [NUM_TENSIX_CORES-1:0]                                        o_remote_rts,  // ready-to-send
input  [NUM_TENSIX_CORES-1:0]                                        i_remote_rtr,  // ready-to-receive
```

---

### 6.8 Dispatch Engine

**Hardware:** Separate `tt_dispatch_top_west` / `tt_dispatch_top_east` instances (at Y=0)
**Source:** [`tt_rtl/overlay/rtl/config/dispatch/trinity/`](../tt_rtl/overlay/rtl/config/dispatch/trinity/)

For the two Dispatch Engine tiles (X=1,Y=0 and X=2,Y=0), the overlay instantiates a specialized variant (`DISPATCH_INST=1'b1`) that replaces part of the CPU subsystem with a Quasar-based dispatch engine (`tt_dispatch_engine`). The overlay connects to DE via side-band:

```systemverilog
output tt_chip_global_pkg::de_to_t6_t [1:0][NumDispatchCorners-1:0] o_de_to_t6,
input  tt_chip_global_pkg::de_to_t6_t      [NumDispatchCorners-1:0] i_de_to_t6,
output tt_chip_global_pkg::t6_to_de_t      [NumTensixX-1:0]         o_t6_to_de,
input  tt_chip_global_pkg::t6_to_de_t      [NumTensixX-1:0]         i_t6_to_de,
```

---

### 6.9 SMN (System Maintenance Network)

**Hardware:** `tt_overlay_smn_wrapper`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_smn_wrapper.sv`](../tt_rtl/overlay/rtl/tt_overlay_smn_wrapper.sv)

The SMN is a North↔South daisy-chain ring used for chip-level management operations (boot sequencing, clock/reset control, power management, AICLK PLL control).

```
    [NOC2AXI / Host Bridge]
           │ SMN N↔S
    [Overlay Y=1]  ←── SMN master/slave
           │
    [Overlay Y=2]  ←── SMN pass-through
           │
    [Overlay Y=3]  ←── SMN pass-through
           │
    [Overlay Y=4]  ←── SMN endpoint
```

SMN parameters:
```systemverilog
parameter bit HAS_SMN_INST                          = 1'b1;
parameter int unsigned SMN_TENSIX_REPEATER_OVERLAY_NORTH_SIDE = 0;
parameter int unsigned SMN_TENSIX_REPEATER_OVERLAY_SOUTH_SIDE = 3;
parameter int unsigned SMN_DISPATCH_REPEATER_OVERLAY_EAST_SIDE  = 0;
parameter int unsigned SMN_DISPATCH_REPEATER_OVERLAY_SOUTH_SIDE = 0;
```

The SMN wrapper outputs three interrupts:
- `o_smn_mst_interrupt` — SMN master transaction complete
- `o_smn_slv_interrupt` — SMN slave received command
- `o_tile_mailbox_interrupt` — software mailbox write

**Processor control path via SMN:**
The SMN carries APB-like register transactions from the host or from another SMN master. These transactions reach the overlay's internal `tt_overlay_wrapper_reg_logic` via the EDC-to-APB bridge, which translates EDC serial bus packets into APB register writes/reads targeting cluster ctrl, cache controller, and PLL registers.

---

### 6.10 EDC (Error Detection and Correction)

**Hardware:** `tt_overlay_edc_wrapper`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_edc_wrapper.sv`](../tt_rtl/overlay/rtl/tt_overlay_edc_wrapper.sv)

The overlay participates in the chip-wide EDC1 ring as a **node**. It holds:

| Repeater | Parameter | Purpose |
|----------|-----------|---------|
| Ingress repeater | `EDC_IN_REP_NUM` | Pipeline stages on EDC ingress bus |
| Internal repeater | `EDC_REP_NUM` | Re-timing within overlay node |
| Egress repeater | `EDC_OUT_REP_NUM` | Pipeline stages on EDC egress bus |
| NoC loopback | (fixed) | Loopback path through `tt_noc_overlay_edc_repeater` |

When `HAS_EDC_INST == 1'b0` (harvested or disabled overlay), the EDC wrapper drives all outputs to zero and passes the serial bus through transparently.

Self-test capability:
```systemverilog
parameter bit OVL_EDC_EN_L2_SELFTEST = 1'b0;  // L2 directory BIST via EDC
parameter bit OVL_EDC_EN_L1_SELFTEST = 1'b0;  // L1 cache BIST via EDC
```

EDC external error output (aggregated faults):
```systemverilog
output logic [EDC_EXT_ERROR_WIDTH-1:0] o_edc_ext_error,
```

**EDC-to-APB bridge** (`tt_overlay_edc_apb_bridge`): translates EDC register-access packets arriving on the EDC ring into APB transactions on the overlay's internal register bus. This is the primary path for out-of-band register access from the host controller.

---

### 6.11 FDS (Frequency/Droop Sensor)

**Hardware:** `tt_fds_wrapper` → `tt_fds`
**Source:** [`tt_rtl/overlay/rtl/fds/tt_fds_wrapper.sv`](../tt_rtl/overlay/rtl/fds/tt_fds_wrapper.sv)

Each overlay contains a Frequency/Droop Sensor block that monitors on-chip voltage droop and frequency deviation. It drives the PLL feedback loop for DVFS.

Parameters:
```systemverilog
parameter int unsigned FDS_NUM_SOURCES  = 3;    // three sensor inputs
parameter int unsigned FDS_BUS_IN_W    = 12;   // 12-bit sensor bus
parameter int unsigned FDS_OFFSET      = 1;    // tile offset in FDS chain
parameter bit          FDS_HAS_ORIENTATION = 1'b1;  // orientation-aware
```

FDS register access uses the internal 26-bit APB port routed through the overlay register crossbar.

Droop events feed back into the PLL via:
```systemverilog
output logic [AI_CLK_PLL_FREQ_SEL_WIDTH-1:0] o_pll_freq_sel_one_hot,
input  logic [AI_CLK_PLL_NUM_DROOP_SENSORS-1:0] i_droop_ready,
input  logic [AI_CLK_PLL_NUM_DROOP_SENSORS-1:0][2:0] i_droop,
```

---

### 6.12 Harvest Support

**Hardware:** `tt_overlay_wrapper_harvest_trinity.sv` + mesh remap signals
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_wrapper_harvest_trinity.sv`](../tt_rtl/overlay/rtl/tt_overlay_wrapper_harvest_trinity.sv)

When a Tensix tile is defective, the overlay is placed in **harvested** state:

```systemverilog
input  logic i_overlay_harvested,  // strapped at chip boot by SMN
output logic o_noc_harvested,      // signals to NoC to skip this node
output logic o_tensix_harvested,   // signals Tensix tile to hold reset
output logic o_tensix_neo_pll_pvt_harvested,
```

The overlay then:
1. Forces EDC repeater to bypass (all-zero output) — EDC ring skips this node.
2. Asserts `o_noc_harvested` so the router sees a mesh boundary at this position.
3. Drives harvest remap coordinates to the NIU/router:
   ```systemverilog
   input logic [NOC_ID_WIDTH:0]   i_remap_x_size,
   input logic [NOC_ID_WIDTH:0]   i_remap_y_size,
   input logic [NOC_ID_WIDTH-1:0] i_remap_nodeid_x,
   input logic [NOC_ID_WIDTH-1:0] i_remap_nodeid_y,
   ```
4. Holds the Tensix tile in reset — the matrix engine never becomes visible on the NoC.

---

### 6.13 Register Access via APB / EDC Bridge

**Hardware:** `tt_overlay_wrapper_reg_logic`, `tt_overlay_reg_xbar_slave_decode`, `tt_overlay_edc_apb_bridge`
**Source:** [`tt_rtl/overlay/rtl/tt_overlay_wrapper_reg_logic.sv`](../tt_rtl/overlay/rtl/tt_overlay_wrapper_reg_logic.sv)

The overlay exposes a flat 26-bit APB register space (32-bit data) that the host or SMN can access via:

1. **EDC ring** (primary out-of-band path): EDC packet → `tt_overlay_edc_apb_bridge` → internal APB bus
2. **NIU register port** (in-band path): NoC packet targets the tile's register endpoint → `o_ext_reg_addr/rd_en/wr_en`
3. **Direct APB** (from SMN or trinity top): `i_reg_addr/wrdata/wren/rden`

APB port widths:
```systemverilog
localparam int unsigned REG_APB_PORT_ADDR_WIDTH = 26;
localparam int unsigned REG_APB_PORT_DATA_WIDTH = 32;
```

The register crossbar (`tt_overlay_reg_xbar_slave_decode`) decodes the 26-bit address and routes to:

| Slave | Contents |
|-------|----------|
| Cluster control CSR | CPU reset vectors, power state, PC capture |
| T6 L1 CSR | Cache enable, ECC config, flush |
| LLK tile counters | Remote counter thresholds |
| Cache controller | Replacement policy, prefetch config |
| Debug module APB | CPU JTAG/debugger interface (12-bit sub-address) |
| SMN registers | `smn_reg.svh` — SMN status, straps |
| T6L1 slave | `tt_t6l1_slv_reg.svh` — L1 address window config |
| NEO AWM wrap | `tt_neo_awm_wrap_reg.svh` — address window manager |
| FDS registers | Droop sensor thresholds and status |

---

### 6.14 iJTAG / DFD Interface

**Hardware:** Scan chain pass-through
**Source:** [`tt_rtl/dfx/tt_overlay_wrapper_dfx.sv`](../rtl/dfx/tt_overlay_wrapper_dfx.sv)

The DFX wrapper passes the iJTAG serial scan chain through the overlay tile:

```systemverilog
input  logic i_ijtag_tck_to_dfd,
input  logic i_ijtag_trstn_to_dfd,
input  logic i_ijtag_sel_to_dfd,
input  logic i_ijtag_ce_to_dfd,
input  logic i_ijtag_se_to_dfd,
input  logic i_ijtag_ue_to_dfd,
input  logic i_ijtag_si_to_dfd,
output logic o_ijtag_so_from_dfd,  // serial output to next tile
```

---

## 7. Control Path: Processor to Data Bus

### 7.1 CPU-to-NoC Write Path (Example)

The following shows how a RISC-V CPU store instruction that targets a remote tile's memory travels through the overlay to the NoC data bus.

```
RISC-V CPU (hart N)
    │  store instruction (PA → NoC address)
    ▼
  tt_overlay_cpu_wrapper
    │  generates noc_req_t head flit (x_coord, y_coord, addr, cmd=WRITE)
    ▼
  tt_overlay_flit_vc_arb          ← selects VC (unicast req VC)
    │  req_head_flit[REQ_FLIT_WIDTH-1:0]
    │  req_head_flit_vc[OVL_REQ_VC_BITS-1:0]
    ▼
  tt_overlay_noc_wrap
    │  injects flit into NIU local port
    ▼
  NIU (tt_overlay_noc_niu_router → niu)
    │  Builds noc_req_t; applies VC credit check
    ▼
  Router (DOR: route X first, then Y)
    │  o_flit_out_req_{N/S/E/W} — selects correct mesh output port
    ▼
  NoC mesh wire to neighbor tile
    ▼  ... (repeated per hop) ...
    ▼
  Destination NIU
    │  ejects flit, decodes local address
    ▼
  L1 / SRAM write port
```

The **CPU does not stall** during the NoC write. A **transaction ID** is allocated (`PACKET_TAG_TRANSACTION_ID_WIDTH`), and the write is considered complete when the overlay receives the write-response flit and clears the `id_outgoing_writes_count` entry.

A **NoC fence** (`o_noc_fence_req`, `i_noc_fence_ack`) stalls the CPU until all outstanding writes are acknowledged, ensuring memory ordering for software.

### 7.2 NoC-to-CPU Read Response Path

```
Remote tile initiates read to this tile (x_coord, y_coord)
    ▼
  Router receives head flit, DOR routes to local port
    ▼
  NIU ejects flit → decodes local address
    ▼
  NoC snoop master (tt_overlay_noc_snoop_tl_master)
    │  presents address on L1 snoop port:
    │    i_noc_mem_port_snoop_valid
    │    i_noc_mem_port_snoop_addr
    ▼
  L1 cache bank (via o_t6_l1_arb_rw_intf)
    │  returns data in 1-8 cycles
    ▼
  NIU builds response flit (return address in noc_header_address_t)
    ▼
  Router injects response back toward requester
```

---

## 8. Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `OVERLAY_VERSION` | 0 | 6-bit version stamp in CSR |
| `L1_CFG` | `NEO_L1_CFG` | L1 cache configuration struct |
| `DISPATCH_INST` | `1'b0` | Enable Dispatch Engine variant |
| `HAS_AICLK_PLL` | `1'b1` | Include AI clock PLL logic |
| `HAS_SMN_INST` | `1'b1` | Include SMN node |
| `HAS_EDC_INST` | `1'b0` | Include EDC repeater instance |
| `OVL_EDC_EN_L2_SELFTEST` | `1'b0` | L2 directory EDC BIST |
| `OVL_EDC_EN_L1_SELFTEST` | `1'b0` | L1 cache EDC BIST |
| `FDS_HAS_ORIENTATION` | `1'b1` | FDS orientation-aware mode |
| `EDC_IN_REP_NUM` | 1 | EDC ingress repeater count |
| `EDC_REP_NUM` | 1 | EDC internal repeater count |
| `EDC_OUT_REP_NUM` | 1 | EDC egress repeater count |
| `NOC_FLIT_REPEATERS_NORTH_TO_SOUTH` | from pkg | Flit pipeline stages (N→S) |
| `NOC_FLIT_REPEATERS_SOUTH_TO_NORTH` | from pkg | Flit pipeline stages (S→N) |
| `SMN_TENSIX_REPEATER_OVERLAY_NORTH_SIDE` | 0 | SMN repeater N-side count |
| `SMN_TENSIX_REPEATER_OVERLAY_SOUTH_SIDE` | 3 | SMN repeater S-side count |
| `FDS_NUM_SOURCES` | 3 | FDS sensor source count |
| `IDMA_DFC_EN` | `1'b0` | iDMA data format conversion |
| `NUM_CS_HARTS` | 1 | Number of context-switch harts |

---

## 9. Clock and Reset Summary

```
                 ┌──────────────┐     gated clocks
i_aiclk ────────►│              ├──► o_ai_clk         → Tensix matrix engine
i_ai_aon_clk ───►│  Clock/Reset ├──► o_aon_core_clk   → always-on CPU logic
i_nocclk ───────►│  Controller  ├──► o_noc_clk_aon    → NoC AON logic
i_ref_clk ──────►│              ├──► o_ref_clk         → PLL ref
i_core_clk ─────►│              ├──► o_core_clk        → CPU pipeline
                 └──────────────┘     o_uncore_clk     → uncore logic

SMN controls: o_smn_ai_clk_reset_n, o_smn_tensix_risc_reset_n[7:0]
              o_smn_ai_clk_en, o_smn_ai_clk_force_ref_n
              o_smn_ai_clk_pll_clk_mux, o_smn_pll_soft_reset_n
```

---

## 10. APB Register Interfaces

| Port | Address Width | Data Width | Purpose |
|------|--------------|------------|---------|
| Main APB (`i_reg_addr`) | 26 bits | 32 bits | Cluster ctrl, cache, PLL, FDS |
| Debug APB (`DEBUG_APB`) | 12 bits | 32 bits | RISC-V debug module |
| Flex-client CSR APB | 9 bits | 32 bits | L1 flex-client per-port config |
| PLL PVT slave APB | 26 bits | 32 bits | T6 PLL programming |
| Droop APB (non-Trinity) | 26 bits | 16 bits | Droop sensor programming |
| NIU master register | 26 bits | 32 bits | Overlay → NIU register path |

Register files included in `tt_overlay_pkg.sv`:

| Include File | Contents |
|-------------|----------|
| `tt_cluster_ctrl_reg.svh` | CPU cluster control, boot config |
| `tt_cluster_ctrl_t6_l1_csr_reg.svh` | L1 cache enable / ECC / flush |
| `tt_overlay_llk_tile_counters_reg.svh` | LLK counter thresholds |
| `tt_cache_controller_reg.svh` | D/I cache controller config |
| `tt_debug_module_apb_reg.svh` | RISC-V debug module |
| `smn_reg.svh` | SMN status and straps |
| `tt_t6l1_slv_reg.svh` | L1 address window (Tensix side) |
| `tt_neo_awm_wrap_reg.svh` | Address window manager |

---

## 11. Worked Example: CPU Issues a NoC Write

**Scenario:** RISC-V hart 0 on tile (X=1, Y=2) writes 64 bytes to tile (X=3, Y=4) L1 at local address `0x1000`.

1. **CPU generates store:** Hart 0 executes `sd a0, 0(a1)` where `a1` maps to tile (3,4) address space.

2. **Flit construction:** `tt_overlay_cpu_wrapper` assembles a head flit:
   ```
   noc_header_address_t:
     x_coord   = 6'd3
     y_coord   = 6'd4
     addr[51:0] = 52'h0000_0000_1000
     cmd.write = 1, vc = unicast_req_vc
   ```

3. **VC arbitration:** `tt_overlay_flit_vc_arb` checks `i_req_head_flit_vc_popcount` for the selected VC. If credit is available, the flit is forwarded.

4. **NIU injection:** The flit is presented to the local NIU at `i_flit_in_req` of the NoC wrap. NIU assigns a transaction tag.

5. **Routing at (1,2):** Router reads `x_coord=3 > local_nodeid_x=1` → route East.

6. **Routing at (2,2):** `x_coord=3 > local_nodeid_x=2` → route East.

7. **Routing at (3,2):** `x_coord=3 == local_nodeid_x=3`, `y_coord=4 > local_nodeid_y=2` → route South.

8. **Routing at (3,3) and (3,4):** At (3,4): X and Y match → deliver to local NIU.

9. **Local write:** NIU ejects flit, decodes address `0x1000` → writes via `i_noc_mem_port_snoop` to L1 bank.

10. **Write response:** Destination NIU sends response flit back to (1,2). Overlay at (1,2) receives it and decrements `id_outgoing_writes_count` for that transaction ID.

---

## 12. Verification Checklist

- [ ] **Clock domain crossings:** Verify all async FIFOs between `core_clk`, `ai_clk`, `noc_clk` domains (CDC waivers must be reviewed in `tt_overlay_ext_reg_cdc.sv`, `tt_overlay_niu_reg_cdc.sv`).
- [ ] **Reset sequencing:** Confirm `REF_CLK_RESET_CYCLES=16` minimum hold respected before each gated reset deasserts.
- [ ] **EDC ring continuity:** With `HAS_EDC_INST=0`, verify all-zero drive on `edc_egress_intf` — no X-propagation.
- [ ] **Harvest isolation:** When `i_overlay_harvested=1`, verify `o_tensix_harvested=1`, EDC bypass active, and `o_noc_harvested=1` within 1 clock cycle.
- [ ] **NoC flit repeater depth:** Verify flit arrives correctly after `NOC_FLIT_REPEATERS_NORTH_TO_SOUTH` cycles of latency (no flit corruption).
- [ ] **VC credit stall:** When `i_req_head_flit_vc_popcount` reaches zero for all VCs, CPU must stall (no dropped flits).
- [ ] **NoC fence:** Assert `o_noc_fence_req`, verify CPU stalls, verify `i_noc_fence_ack` deasserts stall after all writes complete.
- [ ] **LLK counter overflow:** Confirm counter wraps gracefully without spurious interrupt.
- [ ] **iDMA scatter/gather:** Verify multi-hop transfer completes with correct byte count and no address translation error.
- [ ] **SMN daisy chain:** Register read/write through SMN reaches correct overlay tile based on tile ID.
- [ ] **APB decode:** All 26-bit APB regions decode to correct sub-module without alias.
- [ ] **iJTAG continuity:** `i_ijtag_si_to_dfd` appears at `o_ijtag_so_from_dfd` after correct number of shift cycles.

---

## 13. Key RTL File Index

| Module | File | Notes |
|--------|------|-------|
| `tt_overlay_wrapper` | `tt_rtl/overlay/rtl/tt_overlay_wrapper.sv` | Top-level overlay |
| `tt_overlay_pkg` | `tt_rtl/overlay/rtl/tt_overlay_pkg.sv` | All constants and CSR includes |
| `tt_overlay_noc_wrap` | `tt_rtl/overlay/rtl/tt_overlay_noc_wrap.sv` | NoC 4-port wrap + EDC interfaces |
| `tt_overlay_noc_niu_router` | `tt_rtl/overlay/rtl/tt_overlay_noc_niu_router.sv` | NIU + router integration |
| `tt_overlay_cpu_wrapper` | `tt_rtl/overlay/rtl/tt_overlay_cpu_wrapper.sv` | RISC-V cluster |
| `tt_overlay_clock_reset_ctrl` | `tt_rtl/overlay/rtl/tt_overlay_clock_reset_ctrl.sv` | Clock gating + reset sync |
| `tt_overlay_smn_wrapper` | `tt_rtl/overlay/rtl/tt_overlay_smn_wrapper.sv` | SMN N↔S node |
| `tt_overlay_edc_wrapper` | `tt_rtl/overlay/rtl/tt_overlay_edc_wrapper.sv` | EDC repeater chain |
| `tt_overlay_edc_apb_bridge` | `tt_rtl/overlay/rtl/tt_overlay_edc_apb_bridge.sv` | EDC → APB translation |
| `tt_overlay_memory_wrapper` | `tt_rtl/overlay/rtl/memories/tt_overlay_memory_wrapper.sv` | L1 SRAM + EDC repeaters |
| `tt_overlay_flex_client_csr_wrapper` | `tt_rtl/overlay/rtl/tt_overlay_flex_client_csr_wrapper.sv` | L1 flex CSR APB |
| `tt_idma_wrapper` | `tt_rtl/overlay/rtl/idma/tt_idma_wrapper.sv` | iDMA engine top |
| `tt_rocc_accel` | `tt_rtl/overlay/rtl/accelerators/tt_rocc_accel.sv` | ROCC co-processor top |
| `tt_rocc_cmd_buf` | `tt_rtl/overlay/rtl/accelerators/tt_rocc_cmd_buf.sv` | ROCC command buffer |
| `tt_rocc_address_gen` | `tt_rtl/overlay/rtl/accelerators/tt_rocc_address_gen.sv` | ROCC address generator |
| `tt_rocc_context_switch` | `tt_rtl/overlay/rtl/accelerators/tt_rocc_context_switch.sv` | ROCC context save/restore |
| `tt_overlay_tile_counters_with_comparators` | `tt_rtl/overlay/rtl/tt_overlay_tile_counters_with_comparators.sv` | LLK remote counters |
| `tt_fds_wrapper` | `tt_rtl/overlay/rtl/fds/tt_fds_wrapper.sv` | FDS droop sensor |
| `tt_overlay_wrapper_reg_logic` | `tt_rtl/overlay/rtl/tt_overlay_wrapper_reg_logic.sv` | APB register logic |
| `tt_overlay_reg_xbar_slave_decode` | `tt_rtl/overlay/rtl/tt_overlay_reg_xbar_slave_decode.sv` | Register slave demux |
| `tt_overlay_flit_vc_arb` | `tt_rtl/overlay/rtl/tt_overlay_flit_vc_arb.sv` | Flit VC arbiter |
| `tt_overlay_wrapper_harvest_trinity` | `tt_rtl/overlay/rtl/tt_overlay_wrapper_harvest_trinity.sv` | Trinity harvest logic |
| `tt_overlay_wrapper_dfx` | `rtl/dfx/tt_overlay_wrapper_dfx.sv` | iJTAG DFX wrapper |
| `tt_noc_overlay_edc_repeater` | `tt_rtl/tt_noc/rtl/noc/tt_noc_overlay_edc_repeater.sv` | EDC repeater used in NoC paths |
| `tt_overlay_tensix_cfg_pkg` | `tt_rtl/overlay/rtl/config/tensix/trinity/tt_overlay_tensix_cfg_pkg.sv` | Tensix-specific config |
| `tt_overlay_dispatch_cfg_pkg` | `tt_rtl/overlay/rtl/config/dispatch/trinity/tt_overlay_dispatch_cfg_pkg.sv` | Dispatch-specific config |

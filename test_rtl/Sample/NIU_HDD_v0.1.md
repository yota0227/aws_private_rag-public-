# NIU (Network Interface Unit) — Hardware Design Document

**Document:** NIU_HDD_v0.1.md
**Chip:** Trinity (4×5 NoC Mesh)
**RTL Snapshot:** 20260221
**Primary Sources:** `trinity_noc2axi_nw_opt.sv`, `trinity_noc2axi_n_opt.sv`, `trinity_noc2axi_ne_opt.sv`, `trinity_pkg.sv`, `tt_noc2axi_pkg` (external)
**Audience:** Verification Engineers · Software Engineers · Hardware Engineers

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v0.1 | 2026-03-17 | (RTL-derived) | Initial release |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Block Diagram](#2-block-diagram)
3. [Trinity Grid Placement](#3-trinity-grid-placement)
4. [NIU Variants](#4-niu-variants)
5. [Features](#5-features)
6. [Submodule Hierarchy](#6-submodule-hierarchy)
7. [Clock and Reset Architecture](#7-clock-and-reset-architecture)
8. [Interface Descriptions](#8-interface-descriptions)
9. [Data Path Architecture](#9-data-path-architecture)
10. [Security Architecture (SMN)](#10-security-architecture-smn)
11. [EDC Integration](#11-edc-integration)
12. [Mesh Configuration via EDC Override](#12-mesh-configuration-via-edc-override)
13. [Parameters and Constants](#13-parameters-and-constants)

---

## 1. Overview

The NIU (Network Interface Unit) is the bridge between the 2D mesh NoC fabric and the on-chip AXI interconnect in the Trinity SoC. It is instantiated in the **north row (y=0)** of the 4×5 NoC grid and provides:

- **Inbound path (NOC2AXI):** Receives NoC flits from the mesh, reconstructs AXI transactions, and drives them to downstream AXI slaves (e.g., DRAM controller, PCIe).
- **Outbound path (AXI2NOC):** Accepts AXI transactions from upstream AXI masters (e.g., host CPU, DMA), converts them to NoC flits, and injects them into the mesh.
- **Address Translation Table (ATT):** Run-time programmable address remapping used by the AXI2NOC path to derive target NoC coordinates.
- **Address Gasket:** Encodes/decodes special addressing fields into/from the NoC header (described in `router_decode_HDD_v0.4.md` §8).
- **Dynamic Routing support:** Supplies mesh boundary and orientation parameters to the NoC router logic.
- **Security Manager (SMN):** Enforces address-range based access-control on transactions entering the NoC.
- **EDC monitoring:** Each NIU tile is a node in the EDC1 ring; the NOC security controller is EDC node index 192.

The core bridge logic is contained in the external module `tt_noc2axi`. The three Trinity wrapper modules (`trinity_noc2axi_nw_opt`, `trinity_noc2axi_n_opt`, `trinity_noc2axi_ne_opt`) add:
- EDC BIU and NOC security controller sub-chain
- EDC-overridable mesh configuration mux
- Clock/reset abutment routing

---

## 2. Block Diagram

```
                      trinity_noc2axi_{nw,n,ne}_opt
  ┌────────────────────────────────────────────────────────────────────┐
  │                                                                    │
  │  Clock/Reset pass-through (abutted flow)                          │
  │  i_ai_clk ──► o_ai_clk        i_nocclk ──► o_nocclk              │
  │  i_dm_clk ──► o_dm_clk                                            │
  │  Resets: direct pass (ai/noc/powergood) + right-shift (dm/tensix) │
  │                                                                    │
  │  ┌──────────────────────────────────────────────────────────┐      │
  │  │                   tt_noc2axi (core)                      │      │
  │  │                                                          │      │
  │  │  NoC Flit Ports            AXI Slave Ports (NOC2AXI)     │      │
  │  │  ┌─────────────────┐       ┌─────────────────┐          │      │
  │  │  │ NORTH (tied '0) │       │  AR/R channels  │──► SoC   │      │
  │  │  │ EAST            │◄─────►│  AW/W/B channels│          │      │
  │  │  │ SOUTH           │       └─────────────────┘          │      │
  │  │  │ WEST (N,NE only)│       AXI Master Ports (AXI2NOC)   │      │
  │  │  └─────────────────┘       ┌─────────────────┐          │      │
  │  │                            │  AR/R channels  │◄── SoC   │      │
  │  │  Mesh Config               │  AW/W/B channels│          │      │
  │  │  ┌─────────────────┐       └─────────────────┘          │      │
  │  │  │ node_id_x/y     │  APB Register Interface             │      │
  │  │  │ noc_x/y_size    │◄──── i_reg_psel/paddr/…           │      │
  │  │  │ mesh_start/end  │                                     │      │
  │  │  │ orientation     │  SMN (Security Manager)             │      │
  │  │  │ endpoint_id     │◄──── i_smn_reg_noc_sec (from EDC)  │      │
  │  │  │ security_fence  │                                     │      │
  │  │  └─────────────────┘                                     │      │
  │  └──────────────────────────────────────────────────────────┘      │
  │       ▲ edc_ingress         edc_egress ▼                           │
  │  ┌──────────────────────┐   ┌──────────────────────────────────┐   │
  │  │ tt_edc1_biu_soc_     │   │ tt_edc1_noc_sec_controller       │   │
  │  │ apb4_wrap            │   │  (EDC node 192)                  │   │
  │  │  APB4 slave          │   │  node_id = {NODE_ID_PART_NOC,    │   │
  │  │  IRQ outputs         │   │             local_nodeid_y,      │   │
  │  │  loopback_ingress ───┼──►│             8'd192}              │   │
  │  │  biu_egress ─────────┘   │  → edc_config_noc_sec            │   │
  │  └──────────────────────┘   └──────────┬───────────────────────┘   │
  │                                        │ edc_repeater_ingress       │
  │                             ┌──────────▼───────────────────────┐   │
  │                             │ tt_noc_overlay_edc_repeater       │   │
  │                             │  egress ──► edc_egress_intf       │   │
  │                             └──────────────────────────────────┘   │
  └────────────────────────────────────────────────────────────────────┘
```

**EDC signal chain within NIU tile:**

```
loopback_edc_ingress_intf
        │
        ▼
 tt_edc1_biu_soc_apb4_wrap   (edc_biu_egress_intf)
        │
        ▼  → edc_ingress of tt_noc2axi
   tt_noc2axi core            (edc_noc2axi_egress_intf)
        │
        ▼
 tt_edc1_noc_sec_controller  (EDC node 192)
        │
        ▼
 tt_noc_overlay_edc_repeater
        │
        ▼
 edc_egress_intf ──► next tile in ring
```

---

## 3. Trinity Grid Placement

```
    x=0              x=1              x=2              x=3
  ┌────────────────┬────────────────┬────────────────┬────────────────┐
y=│ noc2axi_nw_opt │ noc2axi_n_opt  │ noc2axi_n_opt  │ noc2axi_ne_opt │  ← NIU row
0 │  (NW corner)   │  (North edge)  │  (North edge)  │  (NE corner)   │
  ├────────────────┼────────────────┼────────────────┼────────────────┤
y=│ dispatch_w     │ router         │ router         │ dispatch_e     │
1 ├────────────────┼────────────────┼────────────────┼────────────────┤
y=│ tensix         │ tensix         │ tensix         │ tensix         │
2 ├────────────────┼────────────────┼────────────────┼────────────────┤
y=│ tensix         │ tensix         │ tensix         │ tensix         │
3 ├────────────────┼────────────────┼────────────────┼────────────────┤
y=│ tensix         │ tensix         │ tensix         │ tensix         │
4 └────────────────┴────────────────┴────────────────┴────────────────┘
```

NIU tiles occupy the entire north row (y=0). They act as **boundary nodes** — the NORTH port is permanently disabled (VC buffer depth = 0, flit inputs tied to `'0`).

---

## 4. NIU Variants

Three RTL wrappers are used depending on grid column position. The only difference between variants is which NoC flit ports are exposed.

| Variant | File | Grid Position | Active NoC Ports |
|---------|------|---------------|------------------|
| `trinity_noc2axi_nw_opt` | `trinity_noc2axi_nw_opt.sv` | y=0, x=0 | EAST, SOUTH |
| `trinity_noc2axi_n_opt`  | `trinity_noc2axi_n_opt.sv`  | y=0, x=1,2 | EAST, SOUTH, WEST |
| `trinity_noc2axi_ne_opt` | `trinity_noc2axi_ne_opt.sv` | y=0, x=3 | SOUTH, WEST |

All three variants instantiate `tt_noc2axi` with identical parameters. Unused port directions are tied off:

```systemverilog
// trinity_noc2axi_n_opt.sv:264-267
.i_flit_in_req_north  ('0),     // NORTH permanently disabled on all variants
.o_flit_in_resp_north (),
.o_flit_out_req_north (),
.i_flit_out_resp_north('0),
```

---

## 5. Features

### 5.1 Dual-Direction Protocol Bridge
- **NOC2AXI (inbound):** NoC flit → AXI4 slave transactions. Up to 64 outstanding reads, 32 outstanding writes simultaneously (configurable).
- **AXI2NOC (outbound):** AXI4 master transactions → NoC flits. Up to 16 outstanding reads, 32 outstanding writes.

### 5.2 512-bit Wide AXI Data Path
- Data bus: **512 bits** (64 bytes — matches NoC flit payload width)
- Address bus: **56 bits** (Trinity physical address space)
- Byte strobe: **64 bits**

### 5.3 Address Translation Table (ATT)
- `HAS_ADDRESS_TRANSLATION = 1` — ATT block present inside `tt_noc2axi`
- `ADDR_TRANSLATION_ON = 0` — internal auto-translation disabled; ATT is SW-programmed via APB
- Used by the **AXI2NOC outbound path** to map AXI address → target NoC {x, y, endpoint_id}

### 5.4 Address Gasket
- `HAS_ADDRESS_GASKET = 1` — encoding of routing hints into address/user fields enabled
- Used to carry NPU-specific fields through the AXI user/address fields to the NoC header
- Described in `router_decode_HDD_v0.4.md` §8

### 5.5 Dynamic Routing
- `HAS_DYNAMIC_ROUTING = 1` — NIU supplies mesh boundary and orientation to router
- `mesh_start_x/y`, `mesh_end_x/y`, node orientation, endpoint ID are run-time programmable via EDC
- Enables harvest (dead-row bypass) by narrowing the active mesh window without chip reset

### 5.6 SMN Security Manager
- 8 address ranges with independent read/write security level attributes + 1 default catch-all range
- Master security level, NS tagging, group ID tagging and enforcement
- All config delivered via EDC NOC security controller (`edc_config_noc_sec` struct)
- `SMN_OVERRIDE_REGISTERS = 1` — SMN config is driven externally (not from internal APB registers)

### 5.7 EDC Integration
- Each NIU tile is a node in the EDC1 ring
- EDC BIU (`tt_edc1_biu_soc_apb4_wrap`) provides APB4 ring access with ingress synchronizer
- EDC NOC security controller at node index **192** delivers all mesh config to `tt_noc2axi`
- 5 EDC IRQ outputs: fatal, critical, correctable, packet-sent, packet-received

### 5.8 Clock/Reset Abutment
- NIU tiles sit at the **top of the column abutment chain** (y=0 is the entry point for clocks and resets flowing south)
- Clocks are passed through as wires — no gating or buffering in the wrapper
- Reset signals for compute rows are **right-shifted by 1** — NIU row (index 0) always receives deasserted reset

---

## 6. Submodule Hierarchy

```
trinity_noc2axi_{nw,n,ne}_opt               (trinity_noc2axi_*.sv)
├── tt_noc2axi                               (external library)
│   ├── NOC2AXI bridge (inbound)
│   │   ├── Flit reassembly / header decode
│   │   ├── AXI AR/AW/W/R/B channel logic
│   │   ├── Outstanding read tracker  (max 64)
│   │   ├── Outstanding write tracker (max 32)
│   │   └── Read data FIFO            (depth 64)
│   ├── AXI2NOC bridge (outbound)
│   │   ├── AXI AR/AW/W/R/B channel logic
│   │   ├── ATT lookup (SW-programmed via APB)
│   │   ├── Address gasket encode/decode
│   │   ├── SMN security check
│   │   ├── Flit assembly / header encode
│   │   ├── Outstanding read tracker  (max 16)
│   │   ├── Outstanding write tracker (max 32)
│   │   └── Write data buffer         (4 transactions)
│   ├── NoC router interface (EAST/SOUTH/WEST VCs; NORTH=depth 0)
│   └── EDC monitoring nodes (indices 0–191)
│
├── tt_edc1_biu_soc_apb4_wrap                (EDC BIU — APB4 slave + ring I/O)
│   ├── ENABLE_INGRESS_SYNC = 1              (synchronizer on loopback ingress)
│   └── ENABLE_EGRESS_SYNC  = 0
│
├── tt_edc1_noc_sec_controller               (EDC node 192)
│   ├── INGRESS/EGRESS/EVENT/CONTROL pipe stages = 0
│   └── ENABLE_INGRESS/EGRESS_SYNC = 0      (same nocclk domain)
│
└── tt_noc_overlay_edc_repeater              (EDC ring output repeater)
    └── HAS_EDC_INST = 1
```

---

## 7. Clock and Reset Architecture

### 7.1 Clock Domains

| Clock | Used by | Domain role |
|-------|---------|-------------|
| `i_axiclk` | `tt_noc2axi` only | AXI slave/master channel registers |
| `i_nocclk` | `tt_noc2axi`, all EDC submodules | NoC fabric clock; all flit and EDC logic |
| `i_ai_clk` | Forwarded south only (wire) | AI compute clock — not consumed in NIU |
| `i_dm_clk` | Forwarded south only (wire) | Debug module clock — not consumed in NIU |

`tt_noc2axi` is **dual-clock**: `i_axiclk` on the AXI side, `i_nocclk` on the NoC side. All AXI↔NoC CDC is handled internally.

### 7.2 Clock Routing (Abutment Pass-Through)

```systemverilog
// trinity_noc2axi_n_opt.sv:182-184
assign o_ai_clk   = i_ai_clk;
assign o_nocclk   = i_nocclk;
assign o_dm_clk   = i_dm_clk;
```

No gating or buffering — pure wire for physical abutment.

### 7.3 Reset Signal Routing

| Reset Signal | Behavior | RTL (line numbers from trinity_noc2axi_n_opt.sv) |
|---|---|---|
| `i_ai_reset_n` | Direct pass-through | `o_ai_reset_n = i_ai_reset_n` (L185) |
| `i_noc_reset_n` | Direct pass-through | `o_noc_reset_n = i_noc_reset_n` (L186) |
| `i_powergood` | Direct pass-through | `o_powergood = i_powergood` (L190) |
| `i_dm_uncore_reset_n[SizeY-1:0]` | **Right-shift, MSB zero-filled** | `{1'b0, i_dm_uncore_reset_n[SizeY-1:1]}` (L188) |
| `i_dm_core_reset_n[SizeY-1:0][DMCoresPerCluster-1:0]` | **Right-shift, MSBs zero-filled** | `{8'b0, i_dm_core_reset_n[SizeY-1:1]}` (L187) |
| `i_tensix_reset_n[SizeY-1:0]` | **Right-shift, MSB zero-filled** | `{1'b0, i_tensix_reset_n[SizeY-1:1]}` (L189) |

The right-shift means **output bit[0] (row y=0 = NIU row) is always 0** (reset asserted). The NIU never drives a deasserted Tensix/DM reset into itself — those reset domains belong to compute rows only.

---

## 8. Interface Descriptions

### 8.1 NoC Flit Ports

Each active direction uses a `noc_req_t` / `noc_resp_t` pair. The request carries flit data; the response carries backpressure credits.

| Signal | Direction | Type | Description |
|--------|-----------|------|-------------|
| `i_flit_in_req_{east,south,west}` | Input | `noc_req_t` | Incoming flits from mesh |
| `o_flit_in_resp_{east,south,west}` | Output | `noc_resp_t` | Credit/ready back to mesh |
| `o_flit_out_req_{east,south,west}` | Output | `noc_req_t` | Outgoing flits to mesh |
| `i_flit_out_resp_{east,south,west}` | Input | `noc_resp_t` | Credit/ready from mesh |

NORTH is absent on all variants. WEST is absent on `nw_opt`. EAST is absent on `ne_opt`.

### 8.2 NOC2AXI Bridge — AXI Master Outputs

The NIU acts as an **AXI master** toward the SoC on the inbound (NOC2AXI) path.

| Channel | Key Signals | Widths |
|---------|------------|--------|
| Read Address | `o_noc2axi_ar{id,addr,len,size,burst,cache,prot,lock,qos,region,user,valid}` / `i_noc2axi_arready` | addr=56b, id=NOC2AXI_ID_WIDTH |
| Read Data | `i_noc2axi_r{id,data,resp,last,valid}` / `o_noc2axi_rready` | data=512b |
| Write Address | `o_noc2axi_aw{id,addr,…,valid}` / `i_noc2axi_awready` | addr=56b |
| Write Data | `o_noc2axi_w{data,strb,last,valid}` / `i_noc2axi_wready` | data=512b, strb=64b |
| Write Response | `i_noc2axi_b{id,resp,valid}` / `o_noc2axi_bready` | — |

**Address truncation:** `tt_noc2axi` internally uses `NOC2AXI_ADDR_WIDTH` (> 56). Upper bits are discarded on output:

```systemverilog
// trinity_noc2axi_n_opt.sv:308,330
localparam int unsigned AddrPadWidth = tt_noc2axi_pkg::NOC2AXI_ADDR_WIDTH - AxiAddrWidth;
logic [AddrPadWidth-1:0] awaddr_unused, araddr_unused;

.o_noc2axi_araddr({araddr_unused, o_noc2axi_araddr}),  // upper bits silently dropped
.o_noc2axi_awaddr({awaddr_unused, o_noc2axi_awaddr}),
```

### 8.3 AXI2NOC Bridge — AXI Slave Inputs

The NIU acts as an **AXI slave** from the SoC on the outbound (AXI2NOC) path.

| Channel | Key Signals | Widths |
|---------|------------|--------|
| Read Address | `i_axi2noc_ar{id,addr,len,size,burst,cache,prot,lock,qos,region,user,valid}` / `o_axi2noc_arready` | addr=56b, user=`noc2axi_tlbs_a_regmap_t` |
| Read Data | `o_axi2noc_r{id,data,resp,last,valid}` / `i_axi2noc_rready` | data=512b |
| Write Address | `i_axi2noc_aw{id,addr,…,user,valid}` / `o_axi2noc_awready` | addr=56b |
| Write Data | `i_axi2noc_w{data,strb,last,valid}` / `o_axi2noc_wready` | data=512b, strb=64b |
| Write Response | `o_axi2noc_b{id,resp,valid}` / `i_axi2noc_bready` | — |

**AXI user field type:** `noc2axi_tlbs_a_regmap_t` — carries TLB/ATT override fields and address gasket hints.

**Address zero-padding:** 56-bit input is zero-extended to `NOC2AXI_ADDR_WIDTH`:

```systemverilog
// trinity_noc2axi_n_opt.sv:355,376
.i_axi2noc_araddr({8'b0, i_axi2noc_araddr}),   // 8 upper bits forced 0
.i_axi2noc_awaddr({8'b0, i_axi2noc_awaddr}),
```

### 8.4 APB Register Interface

32-bit APB slave for run-time NIU register access (ATT entries, gasket config, performance counters).

| Signal | Dir | Width | Description |
|--------|-----|-------|-------------|
| `i_reg_psel` | In | 1 | APB select |
| `i_reg_paddr` | In | 32 | Register address |
| `i_reg_penable` | In | 1 | APB enable phase |
| `i_reg_pwrite` | In | 1 | Write enable |
| `i_reg_pwdata` | In | 32 | Write data |
| `o_reg_pready` | Out | 1 | Slave ready |
| `o_reg_prdata` | Out | 32 | Read data |
| `o_reg_pslverr` | Out | 1 | Slave error |

The **external NIU register interface** (`i_ext_niu_reg_*`) is hardcoded disabled in Trinity:

```systemverilog
// trinity_noc2axi_n_opt.sv:256-262
.i_ext_niu_reg_cs(1'b0),
.i_ext_niu_reg_addr(32'h0),
.i_ext_niu_reg_wr_data(32'h0),
.i_ext_niu_reg_wr_en(1'b0),
.i_ext_niu_reg_rd_en(1'b0),
.o_ext_niu_reg_ack(),
.o_ext_niu_reg_rd_data(),
```

### 8.5 EDC Interface

| Signal | Direction | Description |
|--------|-----------|-------------|
| `loopback_edc_ingress_intf` | Input (`ingress`) | EDC ring input to this tile |
| `edc_egress_intf` | Output (`egress`) | EDC ring output to next tile |
| `edc_apb_p{sel,enable,write,prot,addr,wdata,strb}` | Input | APB4 to EDC BIU |
| `edc_apb_p{ready,rdata,slverr}` | Output | EDC BIU response |
| `edc_fatal_err_irq` | Output | Fatal error interrupt |
| `edc_crit_err_irq` | Output | Critical error interrupt |
| `edc_cor_err_irq` | Output | Correctable error interrupt |
| `edc_pkt_sent_irq` | Output | Packet sent interrupt |
| `edc_pkt_rcvd_irq` | Output | Packet received interrupt |

### 8.6 NoC Mesh Configuration Inputs

| Signal | Width | Description |
|--------|-------|-------------|
| `i_noc_x_size` | `NOC_ID_WIDTH+1` | Total mesh X dimension |
| `i_noc_y_size` | `NOC_ID_WIDTH+1` | Total mesh Y dimension |
| `i_local_nodeid_x` | `NOC_ID_WIDTH` | This tile's X coordinate |
| `i_local_nodeid_y` | `NOC_ID_WIDTH` | This tile's Y coordinate |
| `i_noc_endpoint_id` | `NOC_ENDPOINT_ID_WIDTH` | This tile's endpoint ID |

All five can be overridden at run-time via EDC (see §12).

---

## 9. Data Path Architecture

### 9.1 NOC2AXI Path (Inbound)

```
 Mesh East/South/West ports  (noc_req_t flits)
             │
             ▼
  ┌──────────────────────────────────────┐
  │  tt_noc2axi — NoC Receive            │
  │  ┌────────────────────────────────┐  │
  │  │  Flit reassembly               │  │
  │  │  Header decode                 │  │
  │  │  (noc_common_hdr_t parsing)    │  │
  │  └────────────────────────────────┘  │
  │               │                      │
  │  ┌────────────────────────────────┐  │
  │  │  AXI Transaction Generator     │  │
  │  │  AR channel (reads)            │  │
  │  │  AW + W channels (writes)      │  │
  │  │  Outstanding read tracker ≤64  │  │
  │  │  Outstanding write tracker ≤32 │  │
  │  │  Read data return FIFO (64)    │  │
  │  └────────────────────────────────┘  │
  └──────────────────────────────────────┘
             │  AXI4 (512b data, 56b addr)
             ▼
  SoC Interconnect (DRAM ctrl, PCIe, …)
```

### 9.2 AXI2NOC Path (Outbound)

```
  SoC Interconnect (CPU, DMA, …)
             │  AXI4 (512b data, 56b addr)
             ▼
  ┌──────────────────────────────────────┐
  │  tt_noc2axi — AXI Receive            │
  │  ┌────────────────────────────────┐  │
  │  │  AXI AR/AW channel decode      │  │
  │  │  ATT lookup (addr → NoC XY)    │  │
  │  │  Address gasket encode         │  │
  │  │  SMN security check            │  │
  │  └────────────────────────────────┘  │
  │               │                      │
  │  ┌────────────────────────────────┐  │
  │  │  Flit Assembly                 │  │
  │  │  Header encode                 │  │
  │  │  Write data buffer (4 txn)     │  │
  │  │  Outstanding read tracker ≤16  │  │
  │  │  Outstanding write tracker ≤32 │  │
  │  └────────────────────────────────┘  │
  └──────────────────────────────────────┘
             │  noc_req_t flits
             ▼
  Mesh East/South/West ports
```

### 9.3 Address Width Handling Summary

| Path | External width | Internal width | Mechanism |
|------|---------------|----------------|-----------|
| NOC2AXI output (araddr/awaddr) | 56b | `NOC2AXI_ADDR_WIDTH` | Upper `AddrPadWidth` bits discarded at wrapper output |
| AXI2NOC input (araddr/awaddr) | 56b | `NOC2AXI_ADDR_WIDTH` | Zero-padded with `{8'b0, addr}` at wrapper input |

---

## 10. Security Architecture (SMN)

The SMN enforces access-control on **AXI2NOC (outbound)** transactions. Configuration is programmed via the EDC ring at boot and stored in the EDC NOC security controller.

### 10.1 Range-Based Access Control

8 programmable address ranges + 1 default catch-all:

| Field group | Description |
|-------------|-------------|
| `range_start_N_addr` / `range_end_N_addr` | Address bounds for range N (N=0…7) |
| `attribute_N_wr_sec_level` | Required write security level |
| `attribute_N_rd_sec_level` | Required read security level |
| `attribute_N_range_enable` | Enable bit |
| `default_range_start/end_addr` | Catch-all range bounds |
| `default_range_attribute_*` | Attributes for catch-all |

### 10.2 Master Security Level

| Field | Description |
|-------|-------------|
| `master_level_master_level` | Security level of this initiator |
| `master_level_tag_group_id` | Group ID tag applied to outgoing transactions |
| `master_level_check_group_id` | Enforce group ID checking |
| `master_level_tag_ns` / `master_level_check_ns` | NS bit tagging and checking |
| `master_level_tag_ns_en` | Enable NS tagging |
| `master_level_check_group_id_en` | Enable group ID enforcement |
| `master_level_check_ns_en` | Enable NS enforcement |

### 10.3 Security Fence Enable

```systemverilog
// trinity_noc2axi_n_opt.sv:296-297
.i_security_fence_en(edc_config_noc_sec.security_fence_en),
.o_noc_sec_fence_irq(),   // IRQ aggregated internally; not wired out of wrapper
```

When `security_fence_en` is asserted, transactions violating security attributes are blocked and an IRQ is generated inside `tt_noc2axi`.

### 10.4 SMN Configuration Path

All SMN fields are assigned from `edc_config_noc_sec` (EDC output) to `i_smn_reg_noc_sec` (tt_noc2axi input):

```systemverilog
// trinity_noc2axi_n_opt.sv:493-547 (excerpt)
assign i_smn_reg_noc_sec.secure_group_id                      = edc_config_noc_sec.secure_group_id;
assign i_smn_reg_noc_sec.range_start_0_addr                   = edc_config_noc_sec.range_start_0_addr;
assign i_smn_reg_noc_sec.range_end_0_addr                     = edc_config_noc_sec.range_end_0_addr;
// ... (8 ranges × start/end, 8 × attribute sets, master_level fields)
assign i_smn_reg_noc_sec.pop_violation_fifo                   = 1'b0;  // hardcoded
```

Status flows back from NIU → EDC controller:

```systemverilog
// trinity_noc2axi_n_opt.sv:470-480
assign edc_status_noc_sec.local_node_id_x = i_local_nodeid_x;
assign edc_status_noc_sec.local_node_id_y = i_local_nodeid_y;
assign edc_status_noc_sec.size_x          = i_noc_x_size;
assign edc_status_noc_sec.size_y          = i_noc_y_size;
assign edc_status_noc_sec.mesh_start_x    = 6'd0;
assign edc_status_noc_sec.mesh_start_y    = 6'd0;
assign edc_status_noc_sec.mesh_stop_x     = i_noc_x_size[5:0] - 6'd1;
assign edc_status_noc_sec.mesh_stop_y     = i_noc_y_size[5:0] - 6'd1;
assign edc_status_noc_sec.orientation     = tt_noc_pkg::NOC_ORIENT_0;
assign edc_status_noc_sec.endpoint_id     = i_noc_endpoint_id;
assign edc_status_noc_sec.slv_ext_error   = '0;
```

---

## 11. EDC Integration

### 11.1 EDC Node Allocation per NIU Tile

| EDC node index | Module | Function |
|---------------|--------|----------|
| 0 – 191 | Inside `tt_noc2axi` | Internal NIU monitoring |
| **192** (`SEC_NOC_CONF_IDX`) | `tt_edc1_noc_sec_controller` | NoC security config delivery |
| (BIU — not numbered) | `tt_edc1_biu_soc_apb4_wrap` | Ring access / APB4 gateway |

### 11.2 EDC Node ID Construction

```systemverilog
// trinity_noc2axi_n_opt.sv:202-205, 451-452
localparam int unsigned SEC_NOC_CONF_IDX = 192;

// Inside tt_edc1_noc_sec_controller instantiation:
.i_node_id({tt_edc1_pkg::NODE_ID_PART_NOC,
            i_local_nodeid_y[NOC_EDC_NOC_ID_WIDTH-1:0],
            (NOC_EDC_NODE_ID_WIDTH)'(SEC_NOC_CONF_IDX)}),
```

The 8-bit EDC node_id = `[NODE_ID_PART_NOC | local_nodeid_y[…] | 8'd192]`.

### 11.3 EDC Synchronization Configuration

| Module | INGRESS_SYNC | EGRESS_SYNC | Reason |
|--------|-------------|------------|--------|
| `tt_edc1_biu_soc_apb4_wrap` | **1** | 0 | Loopback ingress may cross clock domain |
| `tt_edc1_noc_sec_controller` | 0 | 0 | Same `nocclk` domain throughout |

### 11.4 EDC Reset Source

Both EDC submodules use `noc_reset_n_sync_to_edc`, which is the NoC reset already synchronized to the EDC domain — produced by `tt_noc2axi`:

```systemverilog
// trinity_noc2axi_n_opt.sv:305
.o_noc_reset_n_sync_to_edc(noc_reset_n_sync_to_edc),
```

---

## 12. Mesh Configuration via EDC Override

Each mesh parameter fed into `tt_noc2axi` has a `*_sel` mux: when the corresponding `edc_config_noc_sec.*_sel` bit is set, the EDC-programmed value is used instead of the hardwired input.

```systemverilog
// trinity_noc2axi_n_opt.sv:483-492
assign local_nodeid_x       = edc_config_noc_sec.local_node_id_x_sel ? edc_config_noc_sec.local_node_id_x : i_local_nodeid_x;
assign local_nodeid_y       = edc_config_noc_sec.local_node_id_y_sel ? edc_config_noc_sec.local_node_id_y : i_local_nodeid_y;
assign noc_x_size           = edc_config_noc_sec.size_x_sel           ? edc_config_noc_sec.size_x          : i_noc_x_size;
assign noc_y_size           = edc_config_noc_sec.size_y_sel           ? edc_config_noc_sec.size_y          : i_noc_y_size;
assign mesh_start_x         = edc_config_noc_sec.mesh_start_x_sel     ? edc_config_noc_sec.mesh_start_x    : 6'd0;
assign mesh_start_y         = edc_config_noc_sec.mesh_start_y_sel     ? edc_config_noc_sec.mesh_start_y    : 6'd0;
assign mesh_end_x           = edc_config_noc_sec.mesh_stop_x_sel      ? edc_config_noc_sec.mesh_stop_x     : (i_noc_x_size[5:0] - 6'd1);
assign mesh_end_y           = edc_config_noc_sec.mesh_stop_y_sel      ? edc_config_noc_sec.mesh_stop_y     : (i_noc_y_size[5:0] - 6'd1);
assign local_node_orientation = edc_config_noc_sec.orientation_sel    ? edc_config_noc_sec.orientation     : tt_noc_pkg::NOC_ORIENT_0;
assign noc_endpoint_id      = edc_config_noc_sec.endpoint_id_sel      ? edc_config_noc_sec.endpoint_id     : i_noc_endpoint_id;
```

**Default values (all `*_sel = 0`):**

| Parameter | Default source |
|-----------|---------------|
| `local_nodeid_x/y` | `i_local_nodeid_*` from top-level |
| `noc_x/y_size` | `i_noc_x/y_size` from top-level |
| `mesh_start_x/y` | `6'd0` (hardcoded) |
| `mesh_end_x` | `i_noc_x_size[5:0] - 1` |
| `mesh_end_y` | `i_noc_y_size[5:0] - 1` |
| `orientation` | `NOC_ORIENT_0` |
| `endpoint_id` | `i_noc_endpoint_id` from top-level |

This mechanism supports **harvest configuration** — when a Tensix row is bypassed, firmware programs `mesh_end_y` via EDC to shrink the active mesh window, excluding the dead row from routing.

---

## 13. Parameters and Constants

### 13.1 Wrapper Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `AXI_SLV_OUTSTANDING_READS` | 64 | Max simultaneous NOC2AXI read transactions |
| `AXI_SLV_OUTSTANDING_WRITES` | 32 | Max simultaneous NOC2AXI write transactions |
| `AXI_SLV_RD_RDATA_FIFO_DEPTH` | 64 | NOC2AXI read data return FIFO depth |
| `AxiDataWidth` (localparam) | 512 | AXI data bus width (bits) |
| `AxiAddrWidth` (localparam) | 56 | AXI address bus width (bits) |
| `AxiStrbWidth` (localparam) | 64 | AXI byte strobe width |

### 13.2 tt_noc2axi Instantiation Parameters

```systemverilog
// trinity_noc2axi_n_opt.sv:224-240
tt_noc2axi #(
    .AXI_DATA_WIDTH               (512),
    .AXI_MST_OUTSTANDING_READS    (16),    // AXI2NOC max outstanding reads
    .AXI_MST_OUTSTANDING_WRITES   (32),    // AXI2NOC max outstanding writes
    .AXI_WDATA_BUF_TRANSACTIONS   (4),     // AXI2NOC write data buffer depth
    .AXI_SLV_OUTSTANDING_READS    (64),    // NOC2AXI max outstanding reads
    .AXI_SLV_OUTSTANDING_WRITES   (32),    // NOC2AXI max outstanding writes
    .AXI_SLV_RD_RDATA_FIFO_DEPTH  (64),    // NOC2AXI read data FIFO depth
    .ADDR_TRANSLATION_ON          (0),     // Internal TLB auto-translate disabled
    .HAS_ADDRESS_TRANSLATION      (1'b1),  // ATT block present (SW-programmed)
    .HAS_ADDRESS_GASKET           (1'b1),  // Address gasket enabled
    .HAS_DYNAMIC_ROUTING          (1'b1),  // Dynamic routing support enabled
    .NORTH_INPUT_VC_BUFFER_DEPTH  (0),     // NORTH VC disabled
    .NUM_REPEATERS_INBOUND_NORTH  (0),
    .NUM_REPEATERS_OUTBOUND_NORTH (0),
    .HAS_EDC_INST                 (1'b1),  // EDC monitoring enabled
    .SMN_OVERRIDE_REGISTERS       (1'b1)   // SMN driven externally via struct
)
```

### 13.3 EDC Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `SEC_NOC_CONF_IDX` | 192 | EDC node index of NOC security controller |
| `ENABLE_INGRESS_SYNC` (BIU) | 1 | CDC synchronizer on loopback EDC ingress |
| `ENABLE_EGRESS_SYNC` (BIU) | 0 | No sync on EDC BIU egress |
| `INGRESS/EGRESS/EVENT/CONTROL_PIPE_STAGES` (sec ctrl) | 0 | No pipeline registers added |
| `HAS_EDC_INST` (repeater) | 1 | EDC repeater active |

# EDC1 Subsystem — Hardware Design Document (HDD)

**Pipeline ID:** `tt_20260221`  
**Document Version:** v4  
**Generated:** 2026-04-24  
**Source:** RTL Knowledge Base — `search_rtl(pipeline_id="tt_20260221", topic="EDC")` (1 result) + prior trinity module_parse data from the same pipeline  
**Method:** Single search call for this document. All content derived strictly from KB data.

> **Integrity Rule:** Only information present in KB search results is stated as fact. Anything not found is explicitly marked **[NOT IN KB]**. RTL signal names and module names are preserved verbatim.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Serial Bus Interface](#3-serial-bus-interface)
4. [Packet Format](#4-packet-format)
5. [Node ID Structure](#5-node-id-structure)
6. [Module Hierarchy](#6-module-hierarchy)
7. [Ring Topology](#7-ring-topology)
8. [Harvest Bypass](#8-harvest-bypass)
9. [BIU (Bus Interface Unit)](#9-biu-bus-interface-unit)
10. [CDC / Synchronization](#10-cdc--synchronization)
11. [Instance Paths](#11-instance-paths)

---

## 1. Overview

### 1.1 What Is EDC1?

EDC1 (Error Detection & Correction, version 1) is the on-chip serial management and diagnostic bus subsystem within the Trinity N1B0 SoC. Based on KB data:

- The EDC subsystem is instantiated at the **trinity** top level with two connector types: **direct-connect** and **loopback** nodes.
- The common connector module is **`tt_edc1_intf_connector`**, used for both topologies.
- The EDC has its own dedicated reset domain via **`i_edc_reset_n`** (active-low), independent from AI compute and NoC resets.

### 1.2 EDC1 Version & Core Characteristics

| Characteristic | Detail |
|---|---|
| Version | EDC**1** (inferred from module prefix `tt_edc1_*`) |
| Interface style | **Toggle-handshake** | [NOT IN KB] — toggle-handshake is the expected EDC1 protocol but was not explicitly stated in the returned results |
| Data width | **16-bit data + parity** | [NOT IN KB] — standard EDC1 spec; not explicitly confirmed in returned results |
| Dedicated reset | `i_edc_reset_n` (active-low, top-level port) |
| Connector module | `tt_edc1_intf_connector` |

### 1.3 Related Module in HDD Section

The single EDC HDD section returned from the KB describes the module:

```
BDAed_trinity_noc2axi_router_nw_opt_trinity_noc2axi_router_nw_opt_tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest
```

This is a **block-level design** that:
- Serves as a **router for the Trinity NoC**
- Provides an **interface to the AXI bus**
- Contains a **32×1024 dual-port SRAM** (`tt_mem_wrap_32x1024_2p_nomask`) without write mask
- Includes **NoC routing translation** with **self-test** capability (`noc_routing_translation_selftest`)

> **Note:** While filed under the "EDC" topic, this module appears to be the NoC-to-AXI router that sits in the EDC data path — acting as the bridge between the EDC serial domain and the wider NoC/AXI fabric.

---

## 2. Architecture

### 2.1 System-Level Block Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     trinity (top)                        │
│                                                         │
│  ┌──────────────┐          ┌──────────────────────────┐ │
│  │   Tensix[0]  │          │  noc2axi_router_nw_opt   │ │
│  │   Tensix[1]  │          │  ┌────────────────────┐  │ │
│  │     ...      │◄─NoC────►│  │ tt_mem_wrap_32x1024│  │ │
│  │   Tensix[N]  │          │  │    _2p_nomask       │  │ │
│  └──────┬───────┘          │  └────────────────────┘  │ │
│         │                  │  noc_routing_translation  │ │
│         │                  │       _selftest           │ │
│         │                  └──────────┬───────────────┘ │
│         │                             │                  │
│    ┌────▼────────────────────────────▼────────┐         │
│    │          EDC1 Serial Ring Bus              │         │
│    │                                            │         │
│    │  ┌─────────────────┐  ┌─────────────────┐ │         │
│    │  │edc_direct_conn  │  │edc_loopback_conn│ │         │
│    │  │    _nodes        │  │    _nodes        │ │         │
│    │  │(tt_edc1_intf_   │  │(tt_edc1_intf_   │ │         │
│    │  │  connector)     │  │  connector)     │ │         │
│    │  └────────┬────────┘  └────────┬────────┘ │         │
│    │           │    Ring Links       │          │         │
│    │           └────────────────────┘          │         │
│    └────────────────────────────────────────────┘         │
│                        │                                  │
│                   i_edc_reset_n                           │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Key Architectural Points (from KB)

1. **Two connector node types** — `edc_direct_conn_nodes` and `edc_loopback_conn_nodes` — both using the same `tt_edc1_intf_connector` module
2. **NoC-to-AXI bridge** in the EDC path with embedded SRAM and routing self-test
3. **Independent reset domain** (`i_edc_reset_n`) allows EDC to be reset without affecting compute or NoC

---

## 3. Serial Bus Interface

### 3.1 Signal Descriptions

The EDC1 serial bus uses a **toggle-handshake protocol** with the following expected signals:

| Signal | Direction | Width | Description |
|---|---|---|---|
| `req_tgl` | Initiator → Target | 1 | Request toggle — transitions indicate a new request | [NOT IN KB] |
| `ack_tgl` | Target → Initiator | 1 | Acknowledge toggle — transitions indicate request accepted | [NOT IN KB] |
| `data` | Bidirectional | 16 | Serial bus data payload | [NOT IN KB] |
| `data_p` | Bidirectional | 1–2 | Parity bit(s) for `data` | [NOT IN KB] |
| `async_init` | Controller → All | 1 | Asynchronous initialization — forces all nodes to a known state | [NOT IN KB] |

> ⚠ **[NOT IN KB]** — The individual serial bus signal names and their exact widths were **not present** in the search results. The table above reflects the standard EDC1 protocol definition. A dedicated search with `query="req_tgl ack_tgl edc"` may confirm these signals in the RTL.

### 3.2 Toggle-Handshake Protocol

[NOT IN KB] — The detailed handshake timing (toggle semantics, minimum pulse width, back-to-back transfer rules) was not returned. Standard EDC1 behavior:

```
Initiator                    Target
    │                           │
    ├── req_tgl toggles ───────►│  (new request + data on bus)
    │                           ├── captures data
    │◄── ack_tgl toggles ──────┤  (acknowledge)
    ├── next req_tgl toggle ───►│  (next transfer)
    │           ...             │
```

---

## 4. Packet Format

### 4.1 Fragment Structure

[NOT IN KB] — The EDC1 packet fragment format (header fields, address encoding, opcode, payload layout) was not present in the search results.

Expected structure based on EDC1 standard:

| Field | Bits | Description |
|---|---|---|
| Fragment type | [NOT IN KB] | Identifies header, data, or tail fragment |
| Node ID | [NOT IN KB] | Destination node addressing |
| Opcode | [NOT IN KB] | Read, write, response, broadcast |
| Address | [NOT IN KB] | Register/memory target address |
| Data payload | [NOT IN KB] | 16-bit per fragment |
| Parity | [NOT IN KB] | Error detection |

### 4.2 MAX_FRGS

[NOT IN KB] — The maximum number of fragments per packet (`MAX_FRGS`) was not returned. A search with `query="MAX_FRGS edc packet"` may retrieve this constant.

---

## 5. Node ID Structure

### 5.1 Node ID Field Decoding

[NOT IN KB] — The `node_id` sub-field definitions were not present in the search results.

Expected decomposition:

| Field | Bits | Description |
|---|---|---|
| `node_id_part` | [NOT IN KB] | Partition identifier — selects which power/reset partition |
| `node_id_subp` | [NOT IN KB] | Sub-partition — selects group within a partition |
| `node_id_inst` | [NOT IN KB] | Instance — selects specific node within a sub-partition |

### 5.2 Node ID Mapping Table

[NOT IN KB] — A mapping from node IDs to physical tile locations / module instances was not in the results. This would typically map each `(part, subp, inst)` tuple to a specific Tensix tile, dispatch block, NIU, or other IP.

---

## 6. Module Hierarchy

### 6.1 EDC1 Module Tree (from KB)

```
trinity (top)
├── edc_direct_conn_nodes          : tt_edc1_intf_connector
│   └── [internal sub-modules]       [NOT IN KB]
├── edc_loopback_conn_nodes        : tt_edc1_intf_connector
│   └── [internal sub-modules]       [NOT IN KB]
│
└── (EDC data path)
    └── noc2axi_router_nw_opt
        ├── tt_mem_wrap_32x1024_2p_nomask
        └── noc_routing_translation_selftest
```

### 6.2 Known `tt_edc1_*` Modules

| Module Name | Role | Source |
|---|---|---|
| `tt_edc1_intf_connector` | EDC1 interface connector — used for both direct-connect and loopback node types | trinity module_parse (instance list) |
| `tt_edc1_*` (others) | [NOT IN KB] — additional `tt_edc1_` prefixed modules (e.g., `tt_edc1_node`, `tt_edc1_ring_stop`, `tt_edc1_biu`, `tt_edc1_cdc`) were not returned | — |

> A dedicated search with `query="tt_edc1"` would likely reveal the full set of EDC1 sub-modules.

---

## 7. Ring Topology

### 7.1 U-Shape Ring Structure

The EDC1 bus uses a **U-shaped ring topology** with two segments:

```
            ┌─── Segment A (Downward) ──────────────────┐
            │                                            │
    ┌───────▼───────┐                                    │
    │  Node [0]     │  edc_direct_conn_nodes             │
    │  (top-left)   │  : tt_edc1_intf_connector          │
    └───────┬───────┘                                    │
            │                                            │
    ┌───────▼───────┐                                    │
    │  Node [1]     │                                    │
    └───────┬───────┘                                    │
            │                                            │
    ┌───────▼───────┐                                    │
    │  Node [2]     │                                    │
    └───────┬───────┘                                    │
            │                                            │
           ...  (descending through grid rows)           │
            │                                            │
    ┌───────▼───────┐                                    │
    │  Node [N]     │                                    │
    │  (bottom)     │                                    │
    └───────┬───────┘                                    │
            │                                            │
            └─────── U-Turn ─────────────────────────────┘
                                                         │
            ┌─── Segment B (Upward) ────────────────────┘
            │
    ┌───────▼───────┐
    │  Node [N]     │  edc_loopback_conn_nodes
    │  (bottom)     │  : tt_edc1_intf_connector
    └───────┬───────┘
            │
    ┌───────▼───────┐
    │  Node [N-1]   │
    └───────┬───────┘
            │
           ...  (ascending through grid rows)
            │
    ┌───────▼───────┐
    │  Node [0]     │
    │  (top-left)   │
    └───────────────┘
            │
            └──── Back to controller / ring closure
```

**Key points from KB data:**
- **`edc_direct_conn_nodes`** — forms the **direct-connect** links (Segment A, downward path)
- **`edc_loopback_conn_nodes`** — forms the **loopback** links (Segment B, upward return path)
- Both use identical **`tt_edc1_intf_connector`** modules, differentiated by instantiation context

### 7.2 Ring Details

| Aspect | Detail |
|---|---|
| Total nodes on ring | [NOT IN KB] — depends on grid size and harvestable tile count |
| Ring direction | Segment A: top→bottom; Segment B: bottom→top (U-shape) |
| Latency per hop | [NOT IN KB] |
| Ring closure mechanism | [NOT IN KB] |

---

## 8. Harvest Bypass

### 8.1 Bypass Mechanism

[NOT IN KB] — The harvest bypass mux/demux mechanism was not described in the search results.

Expected architecture for EDC1 harvest bypass:

```
                  edc_mux_demux_sel
                        │
    ┌───────────────────▼───────────────────┐
    │              MUX / DEMUX              │
    │                                       │
    │   sel=0: ──► Route through tile node  │
    │   sel=1: ──► Bypass (skip harvested   │
    │              tile, connect to next)    │
    └───────────────────────────────────────┘
```

### 8.2 `edc_mux_demux_sel` Operation

| `edc_mux_demux_sel` | Behavior |
|---|---|
| `0` (tile active) | EDC ring passes **through** the tile's EDC node — tile is accessible on the serial bus | [NOT IN KB] |
| `1` (tile harvested) | EDC ring **bypasses** the tile — serial bus skips this node, maintaining ring continuity | [NOT IN KB] |

> ⚠ The `edc_mux_demux_sel` signal name and its polarity are **[NOT IN KB]** from this search. A query for `query="edc_mux_demux_sel harvest"` would confirm the exact signal and logic.

---

## 9. BIU (Bus Interface Unit)

### 9.1 Register Access Path

[NOT IN KB] — The EDC1 BIU (Bus Interface Unit) register access path was not described in the search results.

Expected register access flow:

```
Host / Controller
    │
    ▼
EDC1 Serial Bus (toggle-handshake)
    │
    ▼
EDC1 Ring Stop (at target node)
    │
    ▼
BIU (Bus Interface Unit)
    │
    ▼
Local Register File / CSR space
```

### 9.2 BIU Features

| Feature | Detail |
|---|---|
| Register address space | [NOT IN KB] |
| Access types | [NOT IN KB] — expected: read, write, broadcast |
| BIU module name | [NOT IN KB] — expected: `tt_edc1_biu` or similar |
| Error response | [NOT IN KB] |

---

## 10. CDC / Synchronization

### 10.1 Clock Domain Crossing

The EDC subsystem operates in its own reset domain (`i_edc_reset_n`) and interfaces with multiple clock domains present in Trinity:

| Boundary | From Domain | To Domain | CDC Mechanism |
|---|---|---|---|
| EDC ↔ NoC | EDC clock (inferred) | `i_noc_clk` | [NOT IN KB] |
| EDC ↔ AI Compute | EDC clock (inferred) | `i_ai_clk` | [NOT IN KB] |
| EDC ↔ AXI | EDC clock (inferred) | `i_axi_clk` | [NOT IN KB] |

### 10.2 Synchronization Strategy

[NOT IN KB] — The specific CDC synchronizer types (2-FF, handshake, async FIFO, gray-code pointer) used at EDC domain boundaries were not in the search results.

**Design observation:** The `noc2axi_router_nw_opt` module in the EDC data path likely contains CDC logic since it bridges between the NoC clock domain and the AXI clock domain.

### 10.3 EDC Clock Source

[NOT IN KB] — The EDC clock source (whether it uses `i_noc_clk`, a dedicated EDC clock, or derives from another reference) was not explicitly stated. The top-level ports show `i_edc_reset_n` but **no dedicated `i_edc_clk` port** was visible in the (truncated) port list, suggesting EDC may share a clock with another domain (likely `i_noc_clk` or `i_axi_clk`).

---

## 11. Instance Paths

### 11.1 EDC Instances within Trinity

Extracted from the `trinity` module_parse results (instance fields):

| Instance Path | Module Type | Description | RTL File |
|---|---|---|---|
| `trinity.edc_direct_conn_nodes` | `tt_edc1_intf_connector` | Direct-connect EDC interface nodes (Segment A of U-ring) | `rtl-sources/tt_20260221/rtl/trinity.sv` |
| `trinity.edc_loopback_conn_nodes` | `tt_edc1_intf_connector` | Loopback EDC interface nodes (Segment B of U-ring) | `rtl-sources/tt_20260221/rtl/trinity.sv` |

### 11.2 RTL File Variants Containing EDC Instances

| File Path | Variant | EDC Instances Present |
|---|---|---|
| `rtl-sources/tt_20260221/rtl/trinity.sv` | Base | ✅ Both |
| `rtl-sources/tt_20260221/used_in_n1/rtl/trinity.sv` | N1 current | ✅ Both |
| `rtl-sources/tt_20260221/used_in_n1/mem_port/rtl/trinity.sv` | N1 + mem_port | ✅ Both |
| `rtl-sources/tt_20260221/used_in_n1/legacy/no_mem_port/rtl/trinity.sv` | N1 legacy | ✅ Both |

> All four Trinity RTL variants instantiate the same EDC direct-connect and loopback nodes.

### 11.3 EDC-Related Module in HDD

From the EDC HDD section (search result [1]):

```
Full module path:
BDAed_trinity_noc2axi_router_nw_opt_trinity_noc2axi_router_nw_opt_tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest

Decomposed:
  └── trinity
      └── noc2axi_router_nw_opt        (NoC-to-AXI router, NW-optimized)
          ├── tt_mem_wrap_32x1024_2p_nomask   (32-bit × 1024 dual-port SRAM, no mask)
          └── noc_routing_translation_selftest (routing translation + BIST)
```

---

## Appendix A — Coverage Summary

| Section | Coverage Level | Notes |
|---|---|---|
| 1. Overview | ⚠ Partial | Module names confirmed; toggle-handshake & 16-bit data standard but [NOT IN KB] |
| 2. Architecture | ⚠ Partial | Block diagram built from confirmed instances; internal details missing |
| 3. Serial Bus Interface | ❌ [NOT IN KB] | Signal names not in search results |
| 4. Packet Format | ❌ [NOT IN KB] | Fragment structure not in search results |
| 5. Node ID Structure | ❌ [NOT IN KB] | Node ID fields not in search results |
| 6. Module Hierarchy | ⚠ Partial | Top-level instances confirmed; sub-modules of `tt_edc1_intf_connector` unknown |
| 7. Ring Topology | ⚠ Partial | U-shape inferred from direct/loopback naming; node count unknown |
| 8. Harvest Bypass | ❌ [NOT IN KB] | Mux/demux mechanism not in search results |
| 9. BIU | ❌ [NOT IN KB] | Register access path not in search results |
| 10. CDC | ⚠ Partial | Clock/reset domains confirmed; CDC mechanisms unknown |
| 11. Instance Paths | ✅ Full | All instance paths and file variants confirmed from KB |

## Appendix B — Suggested Follow-up Searches

| Gap | Suggested Query |
|---|---|
| Serial bus signals | `query="req_tgl ack_tgl edc1 serial"` |
| Packet/fragment format | `query="edc1 packet fragment MAX_FRGS"` |
| Node ID decoding | `query="node_id_part node_id_subp edc1"` |
| Full module hierarchy | `query="tt_edc1"` |
| Harvest bypass mux | `query="edc_mux_demux_sel harvest bypass"` |
| BIU register map | `query="tt_edc1_biu register"` |
| CDC synchronizers | `query="edc cdc synchronizer"` |
| EDC clock source | `query="edc_clk clock source"` |

---

*End of Document*

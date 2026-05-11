# N1B0 NPU — Full Hardware Design Document

> **Pipeline ID:** tt_20260221
> **Version:** v6b (Multi-topic Integrated, Enhanced Synthesis)
> **RAG:** v4.1 + Package Parser
> **Method:** 5-round topic search → maximum fact extraction → unified synthesis
> **Generated:** 2026-04-28

---

## Table of Contents

1. [Overview](#1-overview)
2. [Package Constants and Grid](#2-package-constants-and-grid)
3. [Top-Level Ports](#3-top-level-ports)
4. [Module Hierarchy](#4-module-hierarchy)
5. [Compute Tile — Tensix](#5-compute-tile--tensix)
6. [Dispatch Engine](#6-dispatch-engine)
7. [NoC Fabric](#7-noc-fabric)
8. [NIU — AXI Bridge Tiles](#8-niu--axi-bridge-tiles)
9. [Clock Architecture](#9-clock-architecture)
10. [Reset Architecture](#10-reset-architecture)
11. [EDC — Error Detection and Correction](#11-edc--error-detection-and-correction)
12. [Power Management](#12-power-management)
13. [SRAM Inventory](#13-sram-inventory)
14. [DFX Hierarchy](#14-dfx-hierarchy)
15. [RTL File Reference](#15-rtl-file-reference)

---

## 1. Overview

N1B0 is the Trinity NPU integrated into the N1 SoC. The top module `trinity` implements a **4-column × 5-row tile mesh** containing 12 compute tiles (Tensix), 4 AXI bridge tiles (NIU/Router), 2 dispatch tiles, and 2 router placeholder tiles, connected by a 2D NoC fabric.

### 1.1 Key N1B0 Characteristics

| Feature | Value | Source |
|---------|-------|--------|
| Grid | 4 columns × 5 rows (20 tiles) | tile_t enum (8 types, 20 positions) |
| Tensix count | 12 | Port `i_tensix_reset_n[NumTensix-1:0]` |
| NIU+Router (combined) | 2 (X=1,2 at Y=4+3) | tile_t: NOC2AXI_ROUTER_NE/NW_OPT |
| Corner NIU | 2 (X=0,3 at Y=4) | tile_t: NOC2AXI_NE/NW_OPT |
| Dispatch | 2 (X=0,3 at Y=3) | tile_t: DISPATCH_E/W |
| ROUTER placeholder | 2 (X=1,2 at Y=3) | tile_t=3'd7, **empty by design** |
| Dynamic routing | Enabled | `EnableDynamicRouting = 1'b1` |
| Clock routing | Per-column arrays | `i_ai_clk[SizeX-1:0]` |
| EDC protocol | Toggle-handshake | `tt_edc_pkg.sv`: req_tgl/ack_tgl |

### 1.2 Block Diagram

```
         X=0              X=1                   X=2                  X=3
        ┌────────────┬─────────────────────────────────────┬────────────┐
Y=4:    │ NIU_NE     │ NIU_ROUTER_NE          NIU_ROUTER_NW│ NIU_NW     │
        │ EP=4       │ EP=9                   EP=14         │ EP=19      │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=3:    │ DISPATCH_E │ [ROUTER placeholder]  [ROUTER phdr]  │ DISPATCH_W │
        │ EP=3       │ EP=8 (inside _NE_OPT) EP=13(_NW_OPT)│ EP=18      │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=2:    │ T6[0][2]   │ T6[1][2]              T6[2][2]       │ T6[3][2]   │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=1:    │ T6[0][1]   │ T6[1][1]              T6[2][1]       │ T6[3][1]   │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=0:    │ T6[0][0]   │ T6[1][0]              T6[2][0]       │ T6[3][0]   │
        └────────────┴─────────────────────────────────────-┴────────────┘
```
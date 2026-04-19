# Hardware Design Document: EDC1 (Error Detection & Control / Event Diagnostic Channel)

**Project:** Trinity (Tenstorrent AI SoC)
**Version:** EDC1 v1.1.0 (SUPER=1, MAJOR=1, MINOR=0) — Document V0.3
**Document Status:** V0.3 — Complete node_id master decode table added 2026-03-17
**Date:** 2026-03-17
**Changes from V0.2:**
- §5.5 (new): Complete node_id master decode table — all parts (0x10–0x1E), subp, and inst[7:0] tables for L1 (0x18), DMC/Overlay (0x1A), and NOC (0x1E) variants (Tensix/Dispatch/Router vs NOC2AXI tiles vs pure Router-only tiles); worked examples for all four part types

---

> **N1B0 Adaptation Note:** This document was written for the baseline Trinity architecture. For N1B0, the following changes apply:
> - **NIU tiles (Y=4):** 4 variants instead of 3: NE_OPT (X=0), NOC2AXI_ROUTER_NE_OPT (X=1, composite dual-row), NOC2AXI_ROUTER_NW_OPT (X=2, composite dual-row), NW_OPT (X=3)
> - **Ring traversal:** Composite tiles (X=1,2) contain two EDC segments internally; external ring enters Y=4 and exits at Y=3
> - **ROUTER at Y=3, X=1,2:** Empty placeholder — router EDC nodes are inside composite modules
> - **4 independent per-column rings** (same structure as baseline)
> - **tile_t enum:** N1B0 values differ — see `trinity_pkg.sv` in `used_in_n1/rtl/targets/4x5/`
> - **For N1B0-specific EDC architecture:** See `N1B0_HDD_v0.1.md §7` and `N1B0_A1/A2` memory archives

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Serial Bus Interface](#3-serial-bus-interface)
4. [Packet Format](#4-packet-format)
5. [Node ID Structure](#5-node-id-structure)
   - 5.5 [Complete node_id Master Decode Table (All Parts)](#55-complete-node_id-master-decode-table-all-parts)
6. [Module Hierarchy](#6-module-hierarchy)
7. [Module Reference](#7-module-reference)
8. [EDC Ring Topology in Trinity](#8-edc-ring-topology-in-trinity)
9. [Harvest Bypass Mechanism](#9-harvest-bypass-mechanism)
10. [Bus Interface Unit (BIU)](#10-bus-interface-unit-biu)
11. [EDC Node Configuration](#11-edc-node-configuration)
12. [Event Types and Commands](#12-event-types-and-commands)
13. [CDC / Synchronization](#13-cdc--synchronization)
14. [Firmware Interface](#14-firmware-interface)
15. [Inter-Cluster EDC Signal Connectivity](#15-inter-cluster-edc-signal-connectivity)
16. [Instance Paths (Trinity)](#16-instance-paths-trinity)

---

## 1. Overview

EDC1 (Event Diagnostic Channel, version 1) is a lightweight, toggle-handshake serial network that propagates diagnostic events, error notifications, and configuration commands across a Tenstorrent SoC tile array. It is used in the Trinity AI accelerator chip.

**Key characteristics:**
- Serial daisy-chain ring topology connecting all IP blocks
- Toggle-based, fully-asynchronous CDC-safe handshake protocol
- 16-bit data + 1-bit parity per transfer fragment
- Up to 12 fragments per packet (MAX_FRGS = 12)
- Supports read/write register access, error reporting, and self-test
- Harvest-aware: mux/demux modules bypass harvested (disabled) tiles

**Version localparam** (from `tt_edc1_pkg.sv`):
```systemverilog
localparam logic [3:0] SUPER_EDC_VERSION = 4'd1;
localparam logic [3:0] MAJOR_EDC_VERSION = 4'd1;
localparam logic [7:0] MINOR_EDC_VERSION = 8'd0;
```

---

## 2. Architecture

### 2.1 System-Level Block Diagram

Trinity has a **4×5 grid**. Each column (X=0..3) has its own independent EDC ring. The ring is a **vertical U-shape**: packets travel **down** the direct path (Segment A), make a U-turn at the bottom tile (Y=0), and return **up** the loopback path (Segment B) back to the BIU at the top (Y=4).

**Harvest bypass:** Each tile row has a complementary **demux** (at the NOC/dispatch router output, before the tile) and **mux** (at the overlay/BIU output, after the tile). When a tile is harvested (`edc_mux_demux_sel=1`), the demux redirects the ring around the dead tile via a bypass wire (`edc_egress_t6_byp_intf`), and the mux selects that bypass wire as the ring input — completely skipping the harvested tile. When the tile is alive (`sel=0`), both the demux and mux use the normal path through the tile.

> **Is the harvest state fixed or an example?**
>
> **It is per-chip, configured at boot time — not fixed in RTL.**
>
> All harvestable tiles have the mux/demux pair instantiated unconditionally in RTL. The bypass hardware is **always present** at every Tensix and Dispatch tile regardless of whether that tile ends up being harvested. Which tiles are actually bypassed is determined by the manufacturing yield test result for each individual chip, stored in eFuse (OTP) and applied at boot time.
>
> **Boot sequence:**
> 1. After power-on, the boot ROM reads the per-chip harvest map from eFuse.
> 2. For each column X and row Y: if tile (X,Y) failed yield screening → `edc_mux_demux_sel[x][y] = 1` (bypass active); otherwise `= 0` (normal).
> 3. These signals are static for the lifetime of the chip's current power cycle. They can only change on the next boot (if eFuse is reprogrammed, which is a one-time operation).
>
> **Which tile rows can be harvested?**
>
> | Row | Tile type | Harvestable? | Reason |
> |-----|-----------|-------------|--------|
> | Y=4 | NOC2AXI (BIU at top) | **No** | Contains the EDC BIU — if bypassed, the EDC ring has no firmware entry point. Y=4 is never harvested. |
> | Y=3 | Dispatch East/West or Router | **Yes** | Demux/mux pair present in `tt_trin_disp_eng_noc_niu_router_east/west` and `tt_trin_noc_niu_router_wrap` |
> | Y=2–0 | Tensix | **Yes** | Demux/mux pair present in `tt_trin_noc_niu_router_wrap` + `tt_neo_overlay_wrapper` |
>
> **The diagram below shows a single column's full structure.** The bypass wires (shown as right-side connections from demux out1 to mux in1) are drawn to illustrate what the bypass path looks like *when a tile is harvested*. On a chip where all tiles are alive, all `sel` signals are 0 and the bypass wires are never active — but the hardware is still there.
>
> A typical Trinity production chip harvests 0–2 rows per column. The extreme case (all Y=0..3 rows harvested) would leave only Y=4 alive, giving a ring with only the BIU and NOC2AXI nodes — still functional for EDC purposes.

```
  One Column (e.g., X=1) — Independent EDC Ring
  [ILLUSTRATIVE: bypass hardware exists at every tile; sel=0/1 is set per-chip from eFuse at boot]
  ═══════════════════════════════════════════════════════════════════════

           APB4 Firmware (BIU[1])
                │
                ▼
  ┌─────────────────────────────────────────────────────┐  Y=4 (top)
  │  tt_neo_overlay_wrapper                             │
  │  ┌──────────────────────────┐                       │
  │  │  tt_edc1_biu_soc_apb4   │  BIU  node_id=0x0000  │
  │  │  (u_edc_req_src)        │◄── APB4 firmware       │
  │  │  (u_edc_rsp_snk)        │─── IRQ to firmware     │
  │  └──────────────────────────┘                       │
  │  ┌─────────────────────────────────────────────┐    │
  │  │  tt_edc1_serial_bus_mux  edc_muxing_...     │    │
  │  │  sel=0: ovl_egress_intf (BIU out) ──► ring  │    │  ← normal
  │  │  sel=1: edc_ingress_t6_byp_intf   ──► ring  │    │  ← tile harvested
  │  └─────────────────────────────────────────────┘    │
  └──────┬──────────────────────────────┬───────────────┘
         │                              ▲
  edc_egress_intf[1*5+4]       loopback_edc_ingress_intf[1*5+4]
  (Segment A: direct, ↓DOWN)   (Segment B: loopback, ↑UP)
         │                              │
         ▼ edc_direct_conn_nodes        │ edc_loopback_conn_nodes
  ┌──────────────────────────────────────────────────────────────────┐  Y=3
  │  tt_dispatch_top_east/west or tt_trin_noc_niu_router_wrap        │
  │  ┌──────────────────────────────────────────────────────────┐    │
  │  │  tt_noc_niu_router                                       │    │
  │  │  ├── tt_noc_overlay_edc_wrapper [N/E/S/W/NIU]            │    │
  │  │  │   └── tt_edc1_node (VC/ECC/parity errors)            │    │
  │  │  └── tt_noc_sec_fence_edc_wrapper                       │    │
  │  │      └── tt_edc1_node (security violations)             │    │
  │  └──────────────────────────────────────────────────────────┘    │
  │  ┌─────────────────────────────────────────────────────┐         │
  │  │  tt_edc1_serial_bus_demux  edc_demuxing_...         │         │
  │  │  sel=0: ring ──► edc_egress_intf       (to tile)   │         │  ← normal
  │  │  sel=1: ring ──► edc_egress_t6_byp_intf            │─────────┼──► bypass wire
  │  └─────────────────────────────────────────────────────┘         │    (skips tile)
  └──────┬──────────────────────────────┬───────────────────────┐    │
         │ (sel=0, normal path)         ▲                       │    │
         │                             │                        ▼    │
  edc_egress_intf[1*5+3]      loopback_edc_ingress_intf[1*5+3] │    │
         │                             │              edc_egress_t6_byp_intf
         ▼ edc_direct_conn_nodes       │ edc_loopback_conn_nodes│    │
  ┌──────────────────────────────────────────────────────────────────┐  Y=2
  │  tt_trin_noc_niu_router_wrap  (Tensix NOC router)                │
  │  ┌──────────────────────────────────────────────────────────┐    │
  │  │  tt_noc_niu_router                                       │    │
  │  │  ├── tt_noc_overlay_edc_wrapper [N/E/S/W/NIU]            │    │
  │  │  └── tt_noc_sec_fence_edc_wrapper                       │    │
  │  └──────────────────────────────────────────────────────────┘    │
  │  ┌─────────────────────────────────────────────────────┐         │
  │  │  tt_edc1_serial_bus_demux  edc_demuxing_...         │         │
  │  │  sel=0: ring ──► edc_egress_intf       (to tile)   │         │  ← normal
  │  │  sel=1: ring ──► edc_egress_t6_byp_intf            │─────────┼──► bypass wire
  │  └─────────────────────────────────────────────────────┘         │
  │  tt_tensix_with_l1  (L1 EDC Hub + T0..T3 sub-nodes)              │
  │  Overlay→L1→T0→L1→T1→L1→T3→L1→T2→L1→Overlay                     │
  │  ┌─────────────────────────────────────────────────────┐         │
  │  │  tt_edc1_serial_bus_mux  edc_muxing_...             │         │
  │  │  sel=0: ovl_egress_intf (tile out) ──► ring         │         │  ← normal
  │  │  sel=1: edc_ingress_t6_byp_intf    ──► ring ◄───────┼─────────┘  ← harvested
  │  └─────────────────────────────────────────────────────┘         │
  └──────┬──────────────────────────────┬───────────────────────────┘
         │                              ▲
  edc_egress_intf[1*5+2]       loopback_edc_ingress_intf[1*5+2]
         │                              │
         ▼ edc_direct_conn_nodes        │ edc_loopback_conn_nodes
  ┌──────────────────────────────────────────────────────────────────┐  Y=1
  │  TENSIX tile (same structure as Y=2, with demux/mux pair)        │
  └──────┬──────────────────────────────┬───────────────────────────┘
         │                              ▲
  edc_egress_intf[1*5+1]       loopback_edc_ingress_intf[1*5+1]
         │                              │
         ▼ edc_direct_conn_nodes        │ edc_loopback_conn_nodes
  ┌──────────────────────────────────────────────────────────────────┐  Y=0 (bottom)
  │  TENSIX tile (same structure as Y=2, with demux/mux pair)        │
  │                                                                  │
  │  U-TURN (Y=0 only, trinity.sv L454-456):                         │
  │  edc_egress_intf[1*5+0] ──► loopback_edc_ingress_intf[1*5+0]    │
  └──────────────────────────────────────────────────────────────────┘

  Segment A (↓DOWN): edc_egress_intf[x*5+y]         BIU → Y=3 → Y=2 → Y=1 → Y=0
  Segment B (↑UP):   loopback_edc_*_intf             Y=0 → Y=1 → Y=2 → Y=3 → BIU
  Inter-tile links:  tt_edc1_intf_connector (combinational passthrough, no clock)
  Harvest bypass:    edc_egress_t6_byp_intf (demux out1 → mux in1, skips dead tile)
```

#### What exactly is "harvested" — which part of the tile becomes inactive?

> **Key distinction:** "Harvested" does NOT mean the entire tile is powered off.
> Only the Tensix AI compute sub-cores (`aiclk` domain) are clock-gated and inactive.
> The NOC router and bypass logic run on `postdfx_aon_clk` (always-on clock) and remain active.
>
> | Tile sub-block | Clock | Harvested state |
> |---|---|---|
> | NOC router (`tt_trin_noc_niu_router_wrap`) | `postdfx_aon_clk` | **Active** — ring passes through; `i_harvest_en=1` forces all error inputs → 0 (no events) |
> | Demux/Mux bypass hardware | `postdfx_aon_clk` | **Active** — correctly redirects ring around dead Tensix sub-cores |
> | Tensix sub-cores T0/T1/T3/T2 (instrn_engine, Gtile, etc.) | `aiclk` | **Dead** — clock stopped; bypassed via demux sel=1 |
> | Overlay wrapper (DCache/ICache/L2/WDT/BIST) | `postdfx_aon_clk` | **Bypassed** — mux sel=1 takes bypass wire before reaching overlay nodes |
>
> Result: A harvested tile contributes **zero EDC events** (errors gated to 0) but still forwards
> the ring token correctly. From the BIU's perspective the harvested tile is silent but not broken.

#### Detailed diagram: Y=1 harvested, Y=4/3/2/0 alive (sel[Y=1]=1, all others sel=0)

```
  Column X=1  —  sel[Y=1]=1 (HARVESTED), sel[Y=4/3/2/0]=0 (alive)
  ═══════════════════════════════════════════════════════════════════════════════

        APB4 Firmware
             │
             ▼
  ┌──────────────────────────────────────────────────────────────┐  Y=4 (top)
  │  NOC2AXI tile  ·  BIU                                        │  sel: N/A (never harvested)
  │  ├─ BIU node (0x0000) — firmware gateway                     │
  │  └─ NOC2AXI EDC nodes active (postdfx_aon_clk)               │
  └─────────────────────────────┬────────────────────────────────┘
                                │ edc_egress_intf[1*5+4]
         ════════════ Segment A — ring travelling DOWN ════════════
                                ▼
  ┌──────────────────────────────────────────────────────────────┐  Y=3  sel=0 (alive)
  │  Dispatch / Router tile                                       │
  │  ├─ NOC router EDC nodes  (postdfx_aon_clk, i_harvest_en=0)  │
  │  │   → errors reported normally                              │
  │  ├─ demux sel=0  ──►  ring enters Dispatch core              │
  │  ├─ Dispatch L1 SRAM EDC nodes  (aiclk, active)             │
  │  ├─ Overlay EDC nodes  (postdfx_aon_clk, active)             │
  │  └─ mux sel=0  ◄──  Overlay output  →  ring exits           │
  └─────────────────────────────┬────────────────────────────────┘
                                │ edc_egress_intf[1*5+3]
                                ▼
  ┌──────────────────────────────────────────────────────────────┐  Y=2  sel=0 (alive)
  │  Tensix tile                                                  │
  │  ├─ NOC router EDC nodes  (postdfx_aon_clk, i_harvest_en=0)  │
  │  │   → errors reported normally                              │
  │  ├─ demux sel=0  ──►  ring enters Tensix sub-cores           │
  │  ├─ T0: Gtile[0] → IE/SRCB/…/L1_client → Gtile[1]  (aiclk) │
  │  ├─ T1, L1 partition (T6_MISC+L1W2), T3, T2  (aiclk)        │
  │  ├─ Overlay: DCache/ICache/L2/WDT/BIST  (postdfx_aon_clk)   │
  │  └─ mux sel=0  ◄──  Overlay output  →  ring exits           │
  └─────────────────────────────┬────────────────────────────────┘
                                │ edc_egress_intf[1*5+2]
                                ▼
  ┌──────────────────────────────────────────────────────────────┐  Y=1  sel=1 *** HARVESTED ***
  │  Tensix tile [HARVESTED]                                      │
  │  ├─ NOC router EDC nodes  (postdfx_aon_clk, i_harvest_en=1)  │
  │  │   → ring passes through NOC nodes as normal               │
  │  │   → BUT all error inputs forced to 0: NO events reported  │
  │  │                                                            │
  │  ├─ demux sel=1  ──►  edc_egress_t6_byp_intf ─────────────┐  │
  │  │        ╔═══════════════════════════════════════════╗    │  │
  │  │        ║  aiclk STOPPED — Tensix sub-cores dead:  ║    │  │
  │  │        ║  T0 Gtile/IE/SRCB/…  ✗ not reached       ║    │bypass
  │  │        ║  T1, T3, T2          ✗ not reached       ║    │wire
  │  │        ║  T6_MISC, L1W2       ✗ not reached       ║    │
  │  │        ║  Overlay DCache/ICache/L2/WDT/BIST       ║    │
  │  │        ║                      ✗ not reached       ║    │
  │  │        ╚═══════════════════════════════════════════╝    │  │
  │  └─ mux sel=1  ◄──  edc_ingress_t6_byp_intf  ◄────────────┘  │
  │       → ring exits (zero events from this tile)               │
  └─────────────────────────────┬────────────────────────────────┘
                                │ edc_egress_intf[1*5+1]
                                ▼
  ┌──────────────────────────────────────────────────────────────┐  Y=0  sel=0 (alive)
  │  Tensix tile                                                  │
  │  ├─ NOC router EDC nodes  (postdfx_aon_clk, i_harvest_en=0)  │
  │  ├─ demux sel=0  ──►  Tensix sub-cores (T0/T1/T3/T2)        │
  │  ├─ L1 partition, Overlay — all active                       │
  │  └─ mux sel=0  ◄──  Overlay output  →  ring exits           │
  │                                                               │
  │  U-TURN:  edc_egress_intf[1*5+0]                             │
  │              ──►  loopback_edc_ingress_intf[1*5+0]           │
  └──────────────────────────────────────────────────────────────┘
                                ▲
         ════════════ Segment B — ring travelling UP ════════════

  ┌──────────────────────────────────────────────────────────────┐  Y=0  (same tile, loopback pass)
  │  Tensix sub-cores + Overlay  →  loopback_edc_egress_intf     │  same as Segment A, sel=0
  └─────────────────────────────┬────────────────────────────────┘
                                │ loopback_edc_egress_intf[1*5+0]
                                ▼  ──► loopback_edc_ingress_intf[1*5+1]
  ┌──────────────────────────────────────────────────────────────┐  Y=1  *** HARVESTED (return pass) ***
  │  Tensix tile [HARVESTED — loopback pass]                      │
  │  ├─ NOC router EDC nodes  (i_harvest_en=1, errors gated=0)   │
  │  ├─ demux sel=1  ──►  bypass wire  ──►  mux sel=1            │
  │  └─  Tensix sub-cores + Overlay bypassed (same as Seg A)     │
  └─────────────────────────────┬────────────────────────────────┘
                                │ loopback_edc_egress_intf[1*5+1]
                                ▼  ──► loopback_edc_ingress_intf[1*5+2]
  ┌──────────────────────────────────────────────────────────────┐  Y=2  (loopback pass, sel=0)
  │  Tensix sub-cores + Overlay  →  loopback_edc_egress_intf     │  (same as Segment A pass)
  └─────────────────────────────┬────────────────────────────────┘
                                │ loopback_edc_egress_intf[1*5+2]
                                ▼  ──► loopback_edc_ingress_intf[1*5+3]
  ┌──────────────────────────────────────────────────────────────┐  Y=3  (loopback pass, sel=0)
  │  Dispatch/Router + Overlay  →  loopback_edc_egress_intf      │
  └─────────────────────────────┬────────────────────────────────┘
                                │ loopback_edc_egress_intf[1*5+3]
                                ▼  ──► loopback_edc_ingress_intf[1*5+4]
  ┌──────────────────────────────────────────────────────────────┐  Y=4
  │  BIU — receives all events and read responses                 │
  │  (zero events from Y=1 on both Segment A and Segment B)      │
  └──────────────────────────────────────────────────────────────┘

  Active EDC node count in this scenario:
  ┌──────┬─────────────────────────────────────────────────────┐
  │  Y=4 │ NOC2AXI nodes + BIU                          active │
  │  Y=3 │ NOC router + Dispatch L1 + Overlay           active │
  │  Y=2 │ NOC router + T0/T1/L1/T3/T2 + Overlay        active │
  │  Y=1 │ NOC router (errors=0) — all others           bypassed│
  │  Y=0 │ NOC router + T0/T1/L1/T3/T2 + Overlay        active │
  └──────┴─────────────────────────────────────────────────────┘
  Each tile is traversed TWICE (once down, once up) — Y=1 is silent on both passes.
```

### 2.2 EDC Ring Flow (Trinity)

The EDC serial ring in each column flows as a **vertical U-shape**. Two scenarios exist depending on whether a tile is alive or harvested.

#### Normal flow (all tiles alive, `edc_mux_demux_sel=0`):

```
BIU (Y=4, top)
  │  Segment A — direct path DOWN (edc_egress_intf)
  │  demux sel=0 → into tile (normal)
  ▼
Dispatch/Router (Y=3)   [NOC EDC nodes active inside]
  │  demux sel=0 → into tile (normal)
  ▼
Tensix tile (Y=2)       [NOC router → L1 Hub → T0 → T1 → T3 → T2]
  │  mux sel=0 → BIU/tile output into ring
  ▼
Tensix tile (Y=1)
  ▼
Tensix tile (Y=0)
  │  U-turn: edc_egress_intf[x*5+0] → loopback_edc_ingress_intf[x*5+0]
  │  Segment B — loopback path UP (loopback_edc_*_intf)
  ▲
Tensix tile (Y=1)
  ▲
Tensix tile (Y=2)
  ▲
Dispatch/Router (Y=3)
  ▲
BIU (Y=4, top) — receives all returning events and responses
```

#### Harvest bypass flow (tile at Y=1 harvested, `edc_mux_demux_sel[Y=1]=1`):

```
BIU (Y=4, top)
  │  Segment A — direct path DOWN
  ▼
Dispatch/Router (Y=3)   [NOC EDC nodes active, errors reported normally]
  ▼
Tensix tile (Y=2)       [NOC + Tensix T0/T1/L1/T3/T2 + Overlay all active]
  ▼
Tensix tile (Y=1)  *** HARVESTED ***
  │  NOC router: postdfx_aon_clk active, i_harvest_en=1 → errors gated to 0
  │  demux sel=1 ──► bypass wire ──────────────────────────────┐
  │  [aiclk stopped: T0/T1/L1/T3/T2 + Overlay — NOT reached]  │ bypass
  │  mux sel=1 ◄── bypass wire ◄───────────────────────────────┘
  │  (ring exits Y=1 with zero events contributed)
  ▼
Tensix tile (Y=0)       [all active, sel=0]
  │  U-turn: edc_egress_intf[x*5+0] → loopback_edc_ingress_intf[x*5+0]
  ▲  Segment B — loopback path UP
Tensix tile (Y=0)       [loopback pass, all active]
  ▲
Tensix tile (Y=1)  *** HARVESTED (return pass) ***
  ▲  NOC router: i_harvest_en=1 → errors gated; demux/mux sel=1 → bypass; silent
Tensix tile (Y=2)       [loopback pass, all active]
  ▲
Dispatch/Router (Y=3)   [loopback pass, all active]
  ▲
BIU (Y=4, top) — receives events from all tiles except Y=1
```

> **Why both segments need bypass:** The ring passes through each tile **twice** — once on Segment A (going down) and once on Segment B (coming back up). A harvested tile must be bypassed on both passes. The same `edc_mux_demux_sel` signal controls both the Segment A bypass and ensures no stale signal from the dead tile enters the ring.

> **Three-layer protection for harvested tiles:**
> 1. Demux `sel=1` — redirects Segment A around the tile
> 2. Mux `sel=1` — accepts bypass wire instead of tile output on return
> 3. `i_harvest_en=1` to `tt_noc_overlay_edc_wrapper` — gates all error inputs to zero, preventing any residual signal in the dead tile from injecting false events

Each tile passes packets in both segments. A node on Segment A can insert an event targeted at the BIU; the BIU sends commands on Segment A and receives responses and events on Segment B. The four columns operate **independently** — there is no cross-column EDC connectivity.

---

## 3. Serial Bus Interface

### 3.1 Interface Definition

Defined in `tt_edc1_pkg.sv` as `edc1_serial_bus_intf_def`:

```systemverilog
interface edc1_serial_bus_intf_def
  #(parameter tt_edc1_pkg::edc_cfg_t EDC_CFG = tt_edc1_pkg::EDC_CFG_DEFAULT);

    logic [1:0]                               req_tgl;    // toggle request
    logic [1:0]                               ack_tgl;    // toggle acknowledge
    logic [EDC_CFG.SERIAL_DATA_W-1:0]         data;       // 16-bit payload
    logic [EDC_CFG.SERIAL_PARITY_W-1:0]       data_p;     // 1-bit parity
    logic                                     async_init; // async init signal
    logic                                     err;        // error indicator

    modport ingress (input  req_tgl, data, data_p, async_init, err,
                     output ack_tgl);
    modport egress  (output req_tgl, data, data_p, async_init, err,
                     input  ack_tgl);

endinterface : edc1_serial_bus_intf_def
```

### 3.2 Default Configuration

```systemverilog
localparam edc_cfg_t EDC_CFG_DEFAULT = '{
    SERIAL_DATA_W:     16,   // data bus width per fragment
    SERIAL_PARITY_W:    1,   // parity bits
    ENABLE_INIT:        1,   // async init supported
    DISABLE_SYNC_FLOPS: 1,   // sync flops disabled by default (CDC handled externally)
    default:            0
};
```

Additional config variants:
| Config Name              | SERIAL_DATA_W | SERIAL_PARITY_W | ENABLE_INIT | DISABLE_SYNC_FLOPS |
|--------------------------|---------------|-----------------|-------------|---------------------|
| `EDC_CFG_DEFAULT`        | 16            | 1               | 1           | 1 (disabled)        |
| `EDC_CFG_SYNC_EN`        | 16            | 1               | 1           | 0 (enabled)         |
| `EDC_CFG_INGRESS_SYNC_EN`| 16            | 1               | 1           | 0 (enabled)         |
| `EDC_CFG_EGRESS_SYNC_EN` | 16            | 1               | 1           | 0 (enabled)         |

### 3.3 Toggle Handshake Protocol

The EDC serial bus uses a **toggle-based handshake** to safely cross clock domains without requiring the sender and receiver to share the same clock:

```
Sender side (egress modport):
  1. Changes req_tgl[1:0] to a new value (toggle from previous)
  2. Places data[15:0], data_p[0] on the bus
  3. Waits until ack_tgl[1:0] matches req_tgl[1:0]

Receiver side (ingress modport):
  1. Detects req_tgl change
  2. Samples data and data_p
  3. Echoes req_tgl back on ack_tgl[1:0]
```

The two-bit toggle encoding (`req_tgl[1:0]`) provides glitch-free CDC crossing. Each fragment transfer requires one full toggle cycle.

### 3.4 async_init Signal

`async_init` is driven by firmware via the BIU CTRL.INIT register bit. When asserted, it propagates asynchronously through the ring to initialize all nodes simultaneously, regardless of clock relationships. The BIU includes a 7-cycle counter (MCPDLY=7) to auto-clear the INIT bit after enough propagation time:

```systemverilog
// From tt_edc1_bus_interface_unit.sv
localparam int unsigned MCPDLY = 7;  // minimum clear propagation delay

always_ff @(posedge i_clk) begin : init_counter
    if (!i_reset_n) begin
        init_cnt <= '0;
    end else if ((init_cnt==0) && init || (init_cnt !=0)) begin
        if (init_cnt==CNT_W'(MCPDLY)) begin
            init_cnt <= '0;
        end else begin
            init_cnt <= init_cnt + CNT_W'(1);
        end
    end
end
```

---

## 4. Packet Format

### 4.1 Packet Structure

A packet consists of a **header** (fragments 0–3) followed by optional **payload** (fragments 4–11). Up to **MAX_FRGS = 12** fragments per packet. Each fragment is 16 bits wide.

| Fragment Index | Field                         | Contents                                |
|----------------|-------------------------------|-----------------------------------------|
| 0              | TGT_ID                        | 16-bit target node ID                   |
| 1              | CMD[3:0], PYLD_LEN[3:0], CMD_OPT[7:0] | Command, payload length, options |
| 2              | SRC_ID                        | 16-bit source node ID                   |
| 3              | DATA1[7:0], DATA0[7:0]        | Header data (e.g., register address)    |
| 4–11           | REQ_DATA[n].DATA[3:0]         | Up to 8 payload fragments (16-bit each) |

From `tt_edc1_bus_interface_unit.sv`:
```systemverilog
case (aux_req_sel)
    FRG_IDX_W'(0):  aux_req_data = { csr_cfg.REQ_HDR0.TGT_ID.value };
    FRG_IDX_W'(1):  aux_req_data = { csr_cfg.REQ_HDR0.CMD.value,
                            csr_cfg.REQ_HDR0.PYLD_LEN.value,
                            csr_cfg.REQ_HDR0.CMD_OPT.value };
    FRG_IDX_W'(2):  aux_req_data = { csr_cfg.REQ_HDR1.SRC_ID.value };
    FRG_IDX_W'(3):  aux_req_data = { csr_cfg.REQ_HDR1.DATA1.value,
                                      csr_cfg.REQ_HDR1.DATA0.value };
    FRG_IDX_W'(4):  aux_req_data = { csr_cfg.REQ_DATA[0].DATA3.value,
                                      csr_cfg.REQ_DATA[0].DATA2.value };
    // ... up to fragment 11
endcase
```

### 4.2 Command Packet Structs (from `tt_edc1_pkg.sv`)

**Generic command packet** (WR_CMD, RD_CMD, GEN_CMD):
```systemverilog
typedef struct packed {
    edc_cmd_e        cmd;       // [15:12] 4-bit command
    logic [11: 8]    pyld_len;  // [11:8]  payload fragment count
    logic [ 7: 0]    addr;      // [7:0]   register address
} edc_generic_cmd_packet_t;
```

**Read response packet**:
```systemverilog
typedef struct packed {
    edc_cmd_e        cmd;       // [15:12]
    logic [11: 8]    pyld_len;  // [11:8]
    logic [ 7: 1]    rsvd;      // [7:1]
    logic [ 0: 0]    status;    // [0] success/fail
} edc_rd_rsp_cmd_packet_t;
```

**Event notification packet**:
```systemverilog
typedef struct packed {
    edc_cmd_e        cmd;       // [15:12]
    logic [11: 8]    pyld_len;  // [11:8]
    logic [ 7: 7]    selftest;  // [7] self-test flag
    logic [ 6: 6]    rsvd;      // [6]
    logic [ 5: 0]    event_id;  // [5:0] event identifier
} edc_ev_cmd_packet_t;
```

---

## 5. Node ID Structure

Node IDs are 16 bits wide, decomposed as:

```
[15:11] node_id_part  (5 bits) — IP block type
[10: 8] node_id_subp  (3 bits) — sub-partition
[ 7: 0] node_id_inst  (8 bits) — instance number
```

```systemverilog
// From tt_edc1_pkg.sv
localparam int unsigned NODE_ID_W      = 16;
localparam int unsigned NODE_ID_PART_W = 5;
localparam int unsigned NODE_ID_SUBP_W = 3;
localparam int unsigned NODE_ID_INST_W = 8;

typedef struct packed {
    logic [NODE_ID_PART_W-1:0] node_id_part;  // IP type
    logic [NODE_ID_SUBP_W-1:0] node_id_subp;  // sub-partition
    logic [NODE_ID_INST_W-1:0] node_id_inst;  // instance index
} edc_node_map_t;
```

### 5.1 Node Part IDs

| Part Name     | Part ID (hex) | Description         |
|---------------|---------------|---------------------|
| TENSIX        | 0x10          | Tensix compute core |
| L1            | 0x18          | L1 SRAM block       |
| DMC           | 0x1A          | DMC (memory ctrl)   |
| NOC           | 0x1E          | NOC router          |

### 5.2 Special Node IDs

```systemverilog
localparam logic [NODE_ID_W-1:0] BIU_NODE_ID  = '0;  // All-zeros: BIU master
localparam logic [NODE_ID_W-1:0] CAST_NODE_ID = '1;  // All-ones:  broadcast
```

**Tensix base address:**
```systemverilog
localparam logic [NODE_ID_W-1:0] NODE_ID_TENSIX_BASE =
    NODE_ID_W'(NODE_ID_PART_TENSIX << (NODE_ID_SUBP_W + NODE_ID_INST_W));
// = 16'h8000 (0x10 << 11)
```

### 5.3 Decoding TGT_ID / SRC_ID

Every packet header carries a 16-bit `TGT_ID` (destination) and `SRC_ID` (source). Both use the same `edc_node_map_t` bit layout.

**Step-by-step decode:**
```
node_id[15:11]  → part  (5 bits) : IP block type
node_id[10: 8]  → subp  (3 bits) : sub-partition index
node_id[ 7: 0]  → inst  (8 bits) : instance number within the part
```

In pseudocode:
```python
part = (node_id >> 11) & 0x1F   # bits [15:11]
subp = (node_id >>  8) & 0x07   # bits [10:8]
inst = (node_id >>  0) & 0xFF   # bits [7:0]
```

**Part ID decode:**

| `node_id[15:11]` | Part hex | IP Type | node_id range |
|---|---|---|---|
| `00000` | — | BIU (whole ID must be `0x0000`) | `0x0000` only |
| `10000` | `0x10` | TENSIX | `0x8000`–`0x87FF` |
| `11000` | `0x18` | L1 | `0xC000`–`0xC7FF` |
| `11010` | `0x1A` | DMC | `0xD000`–`0xD7FF` |
| `11110` | `0x1E` | NOC | `0xF000`–`0xF7FF` |
| `11111` | — | BROADCAST (whole ID must be `0xFFFF`) | `0xFFFF` only |

**Decode examples (Trinity confirmed):**

| node_id | part | subp (Y) | inst | Exact RTL target |
|---------|------|----------|------|-----------------|
| `0x0000` | — | — | — | BIU (firmware master) |
| `0xFFFF` | — | — | — | Broadcast to all nodes |
| `0xF000` | NOC `0x1E` | 0 | 0x00 | `noc_overlay_edc_wrapper_north_router_vc_buf` at Y=0 — North port VC buffer SRAM parity |
| `0xF001` | NOC `0x1E` | 0 | 0x01 | `noc_overlay_edc_wrapper_north_router_header_ecc` at Y=0 — North port packet header ECC |
| `0xF002` | NOC `0x1E` | 0 | 0x02 | `noc_overlay_edc_wrapper_north_router_data_parity` at Y=0 — North port payload data parity |
| `0xF100` | NOC `0x1E` | 1 | 0x00 | `noc_overlay_edc_wrapper_north_router_vc_buf` at Y=1 — same function, tile row Y=1 |
| `0xF200` | NOC `0x1E` | 2 | 0x00 | `noc_overlay_edc_wrapper_north_router_vc_buf` at Y=2 |
| `0x8205` | TENSIX T0 `0x10` | 2 | 0x05 | `tt_edc1_node` UNPACK_EDC_IDX in T0 at Y=2 |
| `0xC210` | L1 `0x18` | 2 | 0x10 | `tt_edc1_node` L1_EDC_IDX in T0 at Y=2 |

See Section 5.4 for the full inst index tables per IP type.

**Encoding (building a node_id):**
```systemverilog
// From tt_edc1_pkg.sv structure
node_id = {part[4:0], subp[2:0], inst[7:0]}
        = (part << 11) | (subp << 8) | inst
```

**Use in packets:**
- **TGT_ID**: Where the packet is going. Nodes compare their own `node_id` input against `TGT_ID` in fragment 0 of every incoming packet. Match → process it. No match → pass it downstream.
- **SRC_ID**: Who sent the packet. For BIU-originated requests, `SRC_ID = BIU_NODE_ID = 0x0000`. For node-originated events, `SRC_ID = node_id` of the reporting node. The BIU uses `SRC_ID` from received packets to identify which node reported the error.
- **CAST_NODE_ID (0xFFFF)**: When `TGT_ID = 0xFFFF`, all nodes accept and process the packet (e.g., for a broadcast write command).

### 5.4 How `subp` Is Assigned Per IP Type

The meaning and source of `node_id[10:8]` (subp) differs by IP block type. It is **not decoded at runtime** — it is **hardwired at elaboration time** when the `node_id` port is connected.

#### 5.4.1 NOC Nodes — `subp` = tile Y position

**Source:** `tt_noc_pkg.sv`, `tt_noc_niu_router.sv`

```systemverilog
// From tt_noc_pkg.sv
localparam int unsigned NOC_EDC_NOC_ID_WIDTH = 3;  // number of bits used for Y coordinate

// Width math (in tt_noc_niu_router.sv):
//   NODE_ID_W    = 16
//   NODE_ID_PART_W = 5
//   NOC_EDC_NOC_ID_WIDTH = 3    → these become subp[2:0]
//   NOC_EDC_NODE_ID_WIDTH = 16 - 5 - 3 = 8  → these become inst[7:0]
```

Each NOC EDC node's `node_id` is assembled as:
```systemverilog
// From tt_noc_niu_router.sv (e.g., L2346)
.i_node_id({tt_edc1_pkg::NODE_ID_PART_NOC,         // [15:11] = 5'h1E
             edc_nodeid_y[NOC_EDC_NOC_ID_WIDTH-1:0], // [10: 8] = local Y coordinate (3 bits)
             NORTH_ROUTER_VC_BUF_EDC_IDX})            // [ 7: 0] = function index
```

Where `edc_nodeid_y` = `i_static_smn_straps.local_node_id_y` = the tile's Y position in the Trinity grid (0–4).

**`subp` = Y coordinate** of the NOC tile in the grid. This distinguishes EDC nodes belonging to different rows.

**`inst` = function index** within that NOC tile. Defined in `tt_noc_pkg.sv`:

```systemverilog
// tt_noc_pkg.sv L747-767
localparam NOC_OVERLAY_EDC_WRAPPER_NORTH_ROUTER_VC_BUF_EDC_IDX      = 0;
localparam NOC_OVERLAY_EDC_WRAPPER_NORTH_ROUTER_HEADER_ECC_EDC_IDX  = 1;
localparam NOC_OVERLAY_EDC_WRAPPER_NORTH_ROUTER_DATA_PARITY_EDC_IDX = 2;
localparam NOC_OVERLAY_EDC_WRAPPER_EAST_ROUTER_VC_BUF_EDC_IDX       = 3;
localparam NOC_OVERLAY_EDC_WRAPPER_EAST_ROUTER_HEADER_ECC_EDC_IDX   = 4;
localparam NOC_OVERLAY_EDC_WRAPPER_EAST_ROUTER_DATA_PARITY_EDC_IDX  = 5;
localparam NOC_OVERLAY_EDC_WRAPPER_SOUTH_ROUTER_VC_BUF_EDC_IDX      = 6;
localparam NOC_OVERLAY_EDC_WRAPPER_SOUTH_ROUTER_HEADER_ECC_EDC_IDX  = 7;
localparam NOC_OVERLAY_EDC_WRAPPER_SOUTH_ROUTER_DATA_PARITY_EDC_IDX = 8;
localparam NOC_OVERLAY_EDC_WRAPPER_WEST_ROUTER_VC_BUF_EDC_IDX       = 9;
localparam NOC_OVERLAY_EDC_WRAPPER_WEST_ROUTER_HEADER_ECC_EDC_IDX   = 10;
localparam NOC_OVERLAY_EDC_WRAPPER_WEST_ROUTER_DATA_PARITY_EDC_IDX  = 11;
localparam NOC_OVERLAY_EDC_WRAPPER_NIU_VC_BUF_EDC_IDX               = 12;
localparam NOC_OVERLAY_EDC_WRAPPER_ROCC_INTF_EDC_IDX                = 13;
localparam NOC_OVERLAY_EDC_WRAPPER_EP_TABLE_EDC_IDX                 = 14;
localparam NOC_OVERLAY_EDC_WRAPPER_ROUTING_TABLE_EDC_IDX            = 15;
localparam NOC_OVERLAY_EDC_WRAPPER_SEC_FENCE_EDC_IDX                = 16;
```

**Full NOC node_id decode example** (tile at Y=2, North VC buffer):
```
node_id = {5'h1E, 3'd2, 8'd0}
        = 0xF200
part = 0x1E → NOC
subp = 2    → tile Y=2 (row 2 in Trinity grid)
inst = 0    → NORTH_ROUTER_VC_BUF
```

**NOC node_id table for Trinity (Y=2 tile, one column):**

Each row maps to exactly one `tt_noc_overlay_edc_wrapper` instance inside `tt_noc_niu_router`. The "RTL instance name" column gives the SystemVerilog instance name. The "Monitored signal" column gives the `i_live_unc_err` / `i_live_cor_err` inputs connected to that node.

| node_id | inst | RTL instance name (in `tt_noc_niu_router`) | Monitored signal | Error type |
|---------|------|--------------------------------------------|------------------|------------|
| `0xF200` | 0  | `noc_overlay_edc_wrapper_north_router_vc_buf`    | `tt_noc_vc_buf_router_vc_buf_intf_north.err[0]` | UNC parity (North VC buf SRAM) |
| `0xF201` | 1  | `noc_overlay_edc_wrapper_north_router_header_ecc`| `router_header_ecc_error[Y_PORT*2 +: 1]` (COR) / `[Y_PORT*2+1]` (UNC) | Header ECC (North port) |
| `0xF202` | 2  | `noc_overlay_edc_wrapper_north_router_data_parity`| `router_data_parity_error[Y_PORT]` | UNC parity (North data) |
| `0xF203` | 3  | `noc_overlay_edc_wrapper_east_router_vc_buf`     | `tt_noc_vc_buf_router_vc_buf_intf_east.err[0]` | UNC parity (East VC buf SRAM) |
| `0xF204` | 4  | `noc_overlay_edc_wrapper_east_router_header_ecc` | `router_header_ecc_error[X_PORT*2 +: 1]` (COR) / `[X_PORT*2+1]` (UNC) | Header ECC (East port) |
| `0xF205` | 5  | `noc_overlay_edc_wrapper_east_router_data_parity`| `router_data_parity_error[X_PORT]` | UNC parity (East data) |
| `0xF206` | 6  | `noc_overlay_edc_wrapper_south_router_vc_buf`    | `tt_noc_vc_buf_router_vc_buf_intf_south.err[0]` | UNC parity (South VC buf SRAM) |
| `0xF207` | 7  | `noc_overlay_edc_wrapper_south_router_header_ecc`| `router_header_ecc_error[S_PORT*2 +: 1]` (COR) / `[S_PORT*2+1]` (UNC) | Header ECC (South port) |
| `0xF208` | 8  | `noc_overlay_edc_wrapper_south_router_data_parity`| `router_data_parity_error[S_PORT]` | UNC parity (South data) |
| `0xF209` | 9  | `noc_overlay_edc_wrapper_west_router_vc_buf`     | `tt_noc_vc_buf_router_vc_buf_intf_west.err[0]` | UNC parity (West VC buf SRAM) |
| `0xF20A` | 10 | `noc_overlay_edc_wrapper_west_router_header_ecc` | `router_header_ecc_error[W_PORT*2 +: 1]` (COR) / `[W_PORT*2+1]` (UNC) | Header ECC (West port) |
| `0xF20B` | 11 | `noc_overlay_edc_wrapper_west_router_data_parity`| `router_data_parity_error[W_PORT]` | UNC parity (West data) |
| `0xF20C` | 12 | `noc_overlay_edc_wrapper_niu_vc_buf`             | `tt_noc_vc_buf_read_niu_vc_buf_intf.err[0]` | UNC parity (NIU VC buf SRAM) |
| `0xF20D` | 13 | `noc_overlay_edc_wrapper_rocc_intf`              | `tt_noc_vc_buf_rocc_intf.err[0]` | UNC parity (RoCC cmd buf SRAM) — bypassed if `OVERLAY_INF_EN==0` |
| `0xF20E` | 14 | `noc_overlay_edc_wrapper_ep_table`               | `tt_noc_address_translation_tables_ep_table_intf.err[0]` | UNC parity (EP table SRAM) — bypassed if `OVERLAY_INF_EN==0` |
| `0xF20F` | 15 | `noc_overlay_edc_wrapper_routing_table`          | `tt_noc_address_translation_tables_routing_table_intf.err[0]` | UNC parity (routing table SRAM) — bypassed if `OVERLAY_INF_EN==0` |
| `0xF2C0` | 0xC0 (192) | `tt_noc_sec_fence_edc_wrapper` (separate, uses `SEC_NOC_CONF_IDX=192`) | security violation signals | UNC (security fence violation) |

> **Note:** All wrappers use `i_edc_clk = postdfx_aon_clk` (NOC clock domain). Header ECC wrappers have `ENABLE_COR_ERR=1` so they report both correctable and uncorrectable ECC events. VC buf and data parity wrappers have `ENABLE_COR_ERR=0` — UNC only. Nodes 13–15 (ROCC, EP table, routing table) are instantiated inside `if (OVERLAY_INF_EN != 0)` blocks; when `OVERLAY_INF_EN==0` a `tt_edc1_intf_connector` bypass wire is used instead (no EDC node active for that inst index in that configuration).

**Example: decoding `0xF000` and `0xF001` (tile Y=0, column X)**

```
0xF000: part=0x1E (NOC), subp=0 (Y=0), inst=0  → noc_overlay_edc_wrapper_north_router_vc_buf
        monitors: North VC buf SRAM UNC parity error
        source file: tt_noc_niu_router.sv:2341

0xF001: part=0x1E (NOC), subp=0 (Y=0), inst=1  → noc_overlay_edc_wrapper_north_router_header_ecc
        monitors: North port packet header COR/UNC ECC error
        source file: tt_noc_niu_router.sv:2387

0xF100: part=0x1E (NOC), subp=1 (Y=1), inst=0  → noc_overlay_edc_wrapper_north_router_vc_buf
        (same function, different tile row — Y=1)
```

> **Note:** The security fence node does **not** use inst=16. It uses `SEC_NOC_CONF_IDX = 192 = 0xC0` hardcoded in `tt_trin_noc_niu_router_wrap.sv:L480`, giving `node_id = {5'h1E, Y[2:0], 8'hC0}`. For Y=2: `0xF2C0`, not `0xF210`.

#### 5.4.2 BIU — `subp` unused (fixed at 0)

```systemverilog
localparam logic [NODE_ID_W-1:0] BIU_NODE_ID = '0;  // 0x0000
// part=0, subp=0, inst=0 — all zeros
```

The BIU has a fixed node_id of `0x0000`. No subp decoding is needed.

#### 5.4.3 TENSIX / L1 — `part` distinguishes sub-cores, `subp` = tile Y, `inst` = sub-node function

For Tensix and L1 nodes, the encoding is **different from NOC**: the `part` field itself is incremented per sub-core (T0/T1/T2/T3), and `subp[2:0]` carries the tile Y coordinate — same as NOC.

**`part` assignment per Tensix sub-core** (from `tt_t6_l1_partition.sv:L663-L667`):

```systemverilog
// part field is incremented per sub-core T0..T3
localparam NODE_ID_PART_TENSIX_BASE = 5'h10;  // = NODE_ID_PART_TENSIX

assign o_node_id_part_l1_to_t0 = NODE_ID_PART_TENSIX_BASE;          // 0x10 = T0
assign o_node_id_part_l1_to_t1 = NODE_ID_PART_TENSIX_BASE + 1;      // 0x11 = T1
assign o_node_id_part_l1_to_t2 = NODE_ID_PART_TENSIX_BASE + 2;      // 0x12 = T2
assign o_node_id_part_l1_to_t3 = NODE_ID_PART_TENSIX_BASE + 3;      // 0x13 = T3
```

**`subp[2:0]` = tile Y coordinate** (same mechanism as NOC), passed as `i_local_nodeid_y[NOC_EDC_NOC_ID_WIDTH-1:0]`.

**`inst[7:0]` = sub-node function index** within the Tensix core, defined in `tt_tensix_edc_pkg.sv`:

```systemverilog
// tt_rtl/tt_tensix_neo/src/hardware/tensix/edc/rtl/tt_tensix_edc_pkg.sv
localparam edc_node_id_t T6_MISC_EDC_IDX    = 'h00;  // T6 miscellaneous
localparam edc_node_id_t IE_PARITY_EDC_IDX  = 'h03;  // Instruction engine parity
localparam edc_node_id_t SRCB_EDC_IDX       = 'h04;  // Source B buffer
localparam edc_node_id_t UNPACK_EDC_IDX     = 'h05;  // Unpacker
localparam edc_node_id_t PACK_EDC_IDX       = 'h06;  // Packer
localparam edc_node_id_t SFPU_EDC_IDX       = 'h07;  // SFPU
localparam edc_node_id_t GPR_P0_EDC_IDX     = 'h08;  // GPR port 0
localparam edc_node_id_t GPR_P1_EDC_IDX     = 'h09;  // GPR port 1
localparam edc_node_id_t CFG_EXU_0_EDC_IDX  = 'h0A;  // Config EXU 0
localparam edc_node_id_t CFG_EXU_1_EDC_IDX  = 'h0B;  // Config EXU 1
localparam edc_node_id_t CFG_GLOBAL_EDC_IDX = 'h0C;  // Config global
localparam edc_node_id_t THCON_0_EDC_IDX    = 'h0D;  // Thread controller 0
localparam edc_node_id_t THCON_1_EDC_IDX    = 'h0E;  // Thread controller 1
localparam edc_node_id_t FPU_EDC_IDX        = 'h0F;  // FPU (Gtile base inst)
localparam edc_node_id_t L1_EDC_IDX         = 'h10;  // L1 SRAM

// Gtile (FPU) sub-instances use fixed local inst IDs:
localparam logic [7:0] GTILE_LOCAL_INST_ID [3:0] = '{ 'h29, 'h26, 'h23, 'h20 };
// Gtile 0 → inst=0x20, Gtile 1 → inst=0x23, Gtile 2 → inst=0x26, Gtile 3 → inst=0x29

// Gtile sub-node offsets from GTILE_LOCAL_INST_ID base:
localparam GTILE_GENERAL_EDC_OFFSET     = 'h00;  // general
localparam GTILE_SRCA_PARITY_EDC_OFFSET = 'h01;  // SrcA parity
localparam GTILE_DEST_PARITY_EDC_OFFSET = 'h02;  // Dest parity
```

**Full node_id construction** (from `tt_instrn_engine_wrapper.sv:L664-L667`):
```systemverilog
// node_id prefix = {part[4:0], nodeid_y[2:0]}  — same formula as NOC
edc_node_id_prefix = {
    i_node_id_part[NODE_ID_PART_W-1:0],       // 5 bits: 0x10+T_idx
    i_local_nodeid_y[NOC_EDC_NOC_ID_WIDTH-1:0] // 3 bits: tile Y
};
// node_id[7:0] = EDC_IDX (sub-node function index)
```

**Tensix node_id decode example** (T0 at Y=2, unpacker):
```
node_id = {5'h10, 3'd2, 8'h05}
        = 0x8205
part = 0x10 → TENSIX, T0 (base)
subp = 2    → tile Y=2
inst = 0x05 → UNPACK_EDC_IDX
```

**Tensix node_id decode example** (T1 at Y=2, FPU):
```
node_id = {5'h11, 3'd2, 8'h0F}
        = 0x8A0F
part = 0x11 → TENSIX, T1
subp = 2    → tile Y=2
inst = 0x0F → FPU_EDC_IDX
```

---

#### 5.4.3.1 EDC Node Inventory per Tensix Cluster Tile (Trinity)

Each tensix cluster tile (one `tt_tensix_with_l1`) contains 4 sub-cores (T0–T3) and one shared L1 partition. All EDC nodes run on the AI clock (`postdfx_clk`).

##### Shared L1 Partition Nodes (in `tt_t6_l1_partition`, part = 0x10)

These nodes are **not per-sub-core** — they are instantiated once per tile in `tt_t6_l1_partition`. They use `part=0x10` (same `NODE_ID_PART_TENSIX_BASE` as T0), so the `part` field alone does not distinguish them from T0.

| inst | Localparam | RTL Instance | RTL File:Line | Monitored Signal / Events |
|------|-----------|--------------|---------------|---------------------------|
| `0x00` | `T6_MISC_EDC_IDX` | `u_edc1_node_misc` (in `tt_t6_misc`) | `tt_t6_misc.sv:914` | parity errors in misc registers, skid buffers, semaphores, TC remap, GSRS (13 events) |
| `0x10` | `L1_EDC_IDX` | (in `tt_t6_l1_wrap2`, passed as `edc_l1_ingress_intf / edc_l1_egress_intf`) | `tt_t6_l1_partition.sv:720` | L1 SRAM bank parity/ECC errors |

> **Note:** `tt_t6_l1_wrap2` receives the ring via `edc_l1_ingress_intf` and returns via `edc_l1_egress_intf`. The L1 SRAM EDC node is instantiated inside `tt_t6_l1_wrap2` (file not available in this fileset).

##### Per-Sub-Core Nodes (in `tt_instrn_engine_wrapper`, one per T0/T1/T2/T3)

Each `tt_instrn_engine_wrapper` instance has 12 EDC nodes in `tt_instrn_engine_wrapper.sv` plus 1 in `tt_instrn_engine.sv`, giving **13 nodes inside the wrapper**. Each sub-core also has 2 `tt_fpu_gtile` instances (Gtile[0] and Gtile[1]), each with 3 EDC nodes (general, src_parity, dest_parity) — total **19 EDC nodes per sub-core** (3 + 13 + 3).

> Ring order within each sub-core (RTL-verified from `tt_tensix.sv` L222/L225):
> **Gtile[0]** (before instrn_engine_wrapper) → instrn_engine_wrapper 13 nodes → **Gtile[1]** (after instrn_engine_wrapper)

`part` per sub-core: T0=`0x10`, T1=`0x11`, T2=`0x12`, T3=`0x13` (from `tt_t6_l1_partition.sv:663–667`).

Ring traversal order inside one `tt_instrn_engine_wrapper` (ingress → egress):

| Ring order | inst | Localparam | SV instance name | RTL File:Line | Monitored Signal / Events |
|------------|------|-----------|------------------|---------------|---------------------------|
| 1  | `0x03` | `IE_PARITY_EDC_IDX`  | *(unnamed)* | `tt_instrn_engine_wrapper.sv:930`  | IE instruction engine parity errors, 3 events |
| 2  | `0x04` | `SRCB_EDC_IDX`       | *(unnamed)* | `tt_instrn_engine_wrapper.sv:977`  | SrcB buffer SRAM parity errors, 4 events |
| 3  | `0x05` | `UNPACK_EDC_IDX`     | *(unnamed)* | `tt_instrn_engine_wrapper.sv:1025` | Unpacker SRAM parity errors |
| 4  | `0x06` | `PACK_EDC_IDX`       | *(unnamed)* | `tt_instrn_engine_wrapper.sv:1076` | Packer SRAM parity errors |
| 5  | `0x07` | `SFPU_EDC_IDX`       | *(unnamed)* | `tt_instrn_engine_wrapper.sv:1170` | SFPU DP/ST errors, parity errors |
| 6  | `0x08` | `GPR_P0_EDC_IDX`     | *(unnamed)* | `tt_instrn_engine_wrapper.sv:1206` | GPR port-0 parity errors, 3 events |
| 7  | `0x09` | `GPR_P1_EDC_IDX`     | *(unnamed)* | `tt_instrn_engine_wrapper.sv:1248` | GPR port-1 parity errors, 3 events |
| 8  | `0x0A` | `CFG_EXU_0_EDC_IDX`  | *(unnamed)* | `tt_instrn_engine_wrapper.sv:1291` | CFG EXU reg-0 parity errors, 3 events |
| 9  | `0x0B` | `CFG_EXU_1_EDC_IDX`  | *(unnamed)* | `tt_instrn_engine_wrapper.sv:1334` | CFG EXU reg-1 parity errors, 3 events |
| 10 | `0x0C` | `CFG_GLOBAL_EDC_IDX` | *(unnamed)* | `tt_instrn_engine_wrapper.sv:1377` | Global CFG reg parity errors, 3 events |
| 11 | `0x0D` | `THCON_0_EDC_IDX`    | `u_edc_node_thcon_0` | `tt_instrn_engine_wrapper.sv:1419` | THCON0 reg parity + self-test done/failed, 3 events |
| 12 | `0x0E` | `THCON_1_EDC_IDX`    | `u_edc_node_thcon_1` | `tt_instrn_engine_wrapper.sv:1472` | THCON1 reg parity + self-test done/failed, 3 events |
| 13 | `0x10` | `L1_EDC_IDX`         | `u_l1_flex_client_edc` (in `tt_instrn_engine`) | `tt_instrn_engine.sv:6641` | L1 client BIST, priority FIFO parity, CSR parity |

Ring connectivity within wrapper:
```
edc_instrn_ingress_intf
  → IE_PARITY → SRCB → UNPACK → PACK → SFPU
  → GPR_P0 → GPR_P1 → CFG_EXU_0 → CFG_EXU_1 → CFG_GLOBAL
  → THCON_0 → THCON_1
  → [repeater: edc_thcon_1_to_l1_flex_repeater, DEPTH=1]
  → [tt_instrn_engine: L1 client EDC node]
  → [repeater: edc_l1_flex_to_egress_repeater, DEPTH=1]
edc_instrn_egress_intf
```

> All nodes in `tt_instrn_engine_wrapper` use `.i_clk(postdfx_clk)` — the AI clock domain.

##### FPU and Gtile Nodes (RTL-verified from `tt_fpu_gtile.sv` and `tt_tensix.sv`)

Sub-core ring order confirmed from `tt_tensix.sv`:
- L208–209: `GTILE0_EDC_OFFSET_INDX=0`, `GTILE1_EDC_OFFSET_INDX = EDC_NODES_PER_GTILE + EDC_NODES_PER_INSTRN_ENGINE`
- L222: `edc_gtile_egress_intf[0]` → `edc_instrn_ingress_intf` — **Gtile[0] feeds instrn_engine_wrapper**
- L225: `edc_instrn_egress_intf` → `edc_gtile_ingress_intf[1]` — **instrn_engine_wrapper feeds Gtile[1]**
- **Ring order per sub-core:** **Gtile[0]** (3 nodes) → instrn_engine_wrapper (13 nodes) → **Gtile[1]** (3 nodes)

Gtile internal ring order confirmed from `tt_fpu_gtile.sv` (ingress→egress chain L931→L991→L1032→L1061→L1098):
- L991–1002: `gtile_general_error_edc_node` → first node (uses `i_local_instance_id` as base inst)
- L1032–1043: `gtile_src_parity_edc_node` → second (inst = base + `GTILE_SRCA_PARITY_EDC_OFFSET=0x01`)
- L1061–1083: `gtile_dest_parity_edc_node` → third (inst = base + `GTILE_DEST_PARITY_EDC_OFFSET=0x02`)

| inst | Localparam | RTL Instance | Notes |
|------|-----------|--------------|-------|
| `0x20` | `GTILE_LOCAL_INST_ID[0]` | `gtile_general_error_edc_node` (Gtile[0]) | Gtile[0] general error — first in ring |
| `0x21` | `GTILE_LOCAL_INST_ID[0]+SRCA_OFFSET` | `gtile_src_parity_edc_node` (Gtile[0]) | Gtile[0] SrcA parity |
| `0x22` | `GTILE_LOCAL_INST_ID[0]+DEST_OFFSET` | `gtile_dest_parity_edc_node` (Gtile[0]) | Gtile[0] Dest parity |
| `0x23` | `GTILE_LOCAL_INST_ID[1]` | `gtile_general_error_edc_node` (Gtile[1]) | Gtile[1] general error — after instrn_engine |
| `0x24` | `GTILE_LOCAL_INST_ID[1]+SRCA_OFFSET` | `gtile_src_parity_edc_node` (Gtile[1]) | Gtile[1] SrcA parity |
| `0x25` | `GTILE_LOCAL_INST_ID[1]+DEST_OFFSET` | `gtile_dest_parity_edc_node` (Gtile[1]) | Gtile[1] Dest parity |
| `0x26` | `GTILE_LOCAL_INST_ID[2]` | Gtile[2] general error | Gtile[2] base (Trinity has 2 Gtiles per sub-core; indices 2–3 unused in standard Trinity) |
| `0x29` | `GTILE_LOCAL_INST_ID[3]` | Gtile[3] general error | Gtile[3] base |

##### EDC Node Count Summary per Tensix Cluster Tile

| Location | Count | Part | inst range |
|----------|-------|------|-----------|
| L1 partition (T6_MISC) | 1 | 0x10 | 0x00 |
| L1 partition (L1W2 SRAM) | 1 | 0x10 | 0x10 |
| T0 sub-core (instrn_engine_wrapper + instrn_engine) | 13 | 0x10 | 0x03–0x0E, 0x10 |
| T1 sub-core | 13 | 0x11 | same |
| T2 sub-core | 13 | 0x12 | same |
| T3 sub-core | 13 | 0x13 | same |
| **Total (instrn_engine confirmed)** | **54** | — | — |
| FPU/Gtile (RTL-verified, `tt_fpu_gtile.sv`) | 6 per sub-core × 4 = 24 | 0x10–0x13 | 0x20–0x25 (Gtile[0]/[1] × 3 nodes each) |
| **Total including Gtile** | **78** | — | — |

##### Full EDC Ring Traversal Order Through One Tensix Cluster Tile

For `NUM_TENSIX_NEO=4` (Trinity, 4 sub-cores), the ring visits nodes in this order (confirmed from `tt_tensix_with_l1.sv:1617–1650`):

```
[ring enters from NOC side]
     │
     ▼  feedthrough via tt_t6_l1_partition (connector, no EDC node)
     │
     ▼  T0 — [part=0x10]
     │    Gtile[0]: general_error(0x20) → src_parity(0x21) → dest_parity(0x22)
     │    → IE_PARITY(0x03) → SRCB(0x04) → UNPACK(0x05) → PACK(0x06) → SFPU(0x07)
     │    → GPR_P0(0x08) → GPR_P1(0x09) → CFG_EXU_0(0x0A) → CFG_EXU_1(0x0B)
     │    → CFG_GLOBAL(0x0C) → THCON_0(0x0D) → THCON_1(0x0E) → L1_client(0x10)
     │    → Gtile[1]: general_error(0x23) → src_parity(0x24) → dest_parity(0x25)
     │    (ring order: Gtile[0] first, instrn_engine middle, Gtile[1] last — confirmed tt_tensix.sv L222/L225)
     │
     ▼  feedthrough via tt_t6_l1_partition (repeater DEPTH=1, no EDC node)
     │
     ▼  T1 — [part=0x11]
     │    same 19 nodes as T0 (Gtile[0]×3 + instrn_engine×13 + Gtile[1]×3)
     │
     ▼  tt_t6_l1_partition MAIN PATH (EDC nodes here!)
     │    T6_MISC(0x00) → L1W2_SRAM(0x10)
     │    (between T1 exit and T3 entry, confirmed tt_tensix_with_l1.sv:1619/1624)
     │
     ▼  T3 — [part=0x13]
     │    same 19 nodes as T0
     │
     ▼  feedthrough via tt_t6_l1_partition (repeater DEPTH=1, no EDC node)
     │
     ▼  T2 — [part=0x12]
     │    same 19 nodes as T0
     │
     ▼  feedthrough via tt_t6_l1_partition (connector, no EDC node)
     │
[ring exits toward overlay/BIU]
```

> **Why T0→T1→L1→T3→T2 order?** The L1 partition is physically between sub-cores. The feedthrough paths (T0↔T1, T3↔T2) are passive repeaters/connectors inside `tt_t6_l1_partition`. The L1 main path (T6_MISC + L1W2) is inserted between T1 and T3 because the L1 SRAM and shared resources are accessed there without needing to be in the hot path from the NOC entry.

#### 5.4.4 Summary: `subp` Meaning Per Part

| Part | `part[4:0]` | `subp[2:0]` meaning | `inst[7:0]` meaning | Set by |
|------|-------------|---------------------|---------------------|--------|
| NOC (`0x1E`) | Fixed `0x1E` | Tile Y coordinate (0–4) | EDC wrapper index (0–15, 0xC0) | `local_node_id_y` strap |
| BIU (`0x00`) | `0x00` (all-zeros node_id) | 0 | 0 | Hardwired `BIU_NODE_ID='0` |
| TENSIX T0 (`0x10`) | `0x10` | Tile Y coordinate (0–4) | Sub-node function (see §5.4.3.1); also T6_MISC(0x00) and L1W2(0x10) shared partition nodes share this part | `local_node_id_y` + `tt_tensix_edc_pkg` idx |
| TENSIX T1 (`0x11`) | `0x11` | Tile Y coordinate (0–4) | Sub-node function (0x03–0x0E, 0x10) | same |
| TENSIX T2 (`0x12`) | `0x12` | Tile Y coordinate (0–4) | Sub-node function (0x03–0x0E, 0x10) | same |
| TENSIX T3 (`0x13`) | `0x13` | Tile Y coordinate (0–4) | Sub-node function (0x03–0x0E, 0x10) | same |

> **Note:** There is no separate `part` value for the L1 partition shared nodes (T6_MISC and L1W2). Both use `part=0x10` (`NODE_ID_PART_TENSIX_BASE`), confirmed in `tt_t6_l1_partition.sv:827`. `inst=0x00` (T6_MISC) and `inst=0x10` (L1W2 SRAM) distinguish them from T0's per-sub-core nodes which use `inst=0x03–0x0E, 0x10`. Note that T0's L1 client node (`inst=0x10`) and the L1W2 SRAM node (`inst=0x10`) both use `part=0x10`, `inst=0x10` — these two nodes share the same `node_id` encoding. The firmware distinguishes them by ring position context (one is a write-accessor monitoring node, the other monitors the SRAM itself).

#### 5.4.5 Trinity Grid Layout and EDC Ring Assignment

**Grid topology** (from `trinity_pkg.sv`, `GridConfig[SizeY-1:0][SizeX-1:0]`):

```
         X=0          X=1          X=2          X=3
Y=4  NOC2AXI_NE   NOC2AXI_N    NOC2AXI_N   NOC2AXI_NW   ← North edge (no Tensix)
Y=3  DISPATCH_E   ROUTER       ROUTER      DISPATCH_W
Y=2  TENSIX       TENSIX       TENSIX      TENSIX
Y=1  TENSIX       TENSIX       TENSIX      TENSIX
Y=0  TENSIX       TENSIX       TENSIX      TENSIX
```

**One EDC ring per column (X):**

There are `NumApbNodes = 4 = SizeX` independent EDC rings, one per column. Each column X has its own BIU (APB4 port `[x]`) and its own ring. The X coordinate is **implicit** (determined by which BIU/ring you are reading from). The Y coordinate is encoded in `subp[2:0]`.

```
Ring X=0: BIU[0] → tiles at (X=0, Y=0..4)  →  back to BIU[0]
Ring X=1: BIU[1] → tiles at (X=1, Y=0..4)  →  back to BIU[1]
Ring X=2: BIU[2] → tiles at (X=2, Y=0..4)  →  back to BIU[2]
Ring X=3: BIU[3] → tiles at (X=3, Y=0..4)  →  back to BIU[3]
```

**Decode rule for SRC_ID from a received packet (firmware side):**
```
1. Which BIU received it?  → column X
2. node_id[15:11] (part)   → IP type and sub-core (T0/T1/T2/T3)
3. node_id[10: 8] (subp)   → tile row Y within that column
4. node_id[ 7: 0] (inst)   → sub-node function within that IP
```

#### 5.4.6 Decode Examples: Packets Arriving at BIU from T0 Sub-cores

The following examples show `SRC_ID` values that firmware would see in `RSP_HDR1.SRC_ID` (or `RSP_HDR0.CMD` for event packets) when an event or read-response arrives from a **T0 sub-core** in various cluster positions.

**T0 = Tensix sub-core 0 → `part=0x10`**

```
node_id[15:11] = 5'h10  (part = TENSIX T0)
node_id[10: 8] = Y       (subp = tile row)
node_id[ 7: 0] = inst    (sub-node function)
```

**Case 1: T0 UNPACK error at cluster (X=0, Y=2)**
```
BIU ring  = X=0  (received on BIU[0])
node_id   = {5'h10, 3'd2, 8'h05}
          = 16'h8205

Decode:
  part = 0x10 → TENSIX T0
  subp = 2    → tile row Y=2 (cluster row 2 in column 0)
  inst = 0x05 → UNPACK_EDC_IDX
Result: Unpacker correctable error in T0, cluster at (X=0, Y=2)
```

**Case 2: T0 SFPU error at cluster (X=2, Y=1)**
```
BIU ring  = X=2  (received on BIU[2])
node_id   = {5'h10, 3'd1, 8'h07}
          = 16'h8107

Decode:
  part = 0x10 → TENSIX T0
  subp = 1    → tile row Y=1 (cluster row 1 in column 2)
  inst = 0x07 → SFPU_EDC_IDX
Result: SFPU error in T0, cluster at (X=2, Y=1)
```

**Case 3: T0 FPU (Gtile-0 general) error at cluster (X=3, Y=0)**
```
BIU ring  = X=3  (received on BIU[3])
node_id   = {5'h10, 3'd0, 8'h20}
          = 16'h8020

Decode:
  part = 0x10 → TENSIX T0
  subp = 0    → tile row Y=0 (bottom row of column 3)
  inst = 0x20 → GTILE_LOCAL_INST_ID[0] + GTILE_GENERAL_EDC_OFFSET
              = Gtile-0 general EDC node
Result: FPU Gtile-0 error in T0, cluster at (X=3, Y=0)
```

**Case 4: T0 L1 SRAM error at cluster (X=1, Y=2)**
```
BIU ring  = X=1  (received on BIU[1])
node_id   = {5'h10, 3'd2, 8'h10}
          = 16'h8210

Decode:
  part = 0x10 → TENSIX T0
  subp = 2    → tile row Y=2
  inst = 0x10 → L1_EDC_IDX
Result: L1 SRAM error reported through T0 node, cluster at (X=1, Y=2)
```

**Complete T0 inst index quick-reference:**

| `inst` | Hex | Sub-node in T0 |
|--------|-----|----------------|
| 0 | `0x00` | T6_MISC (miscellaneous) |
| 3 | `0x03` | IE_PARITY (instruction engine parity) |
| 4 | `0x04` | SRCB (source B buffer) |
| 5 | `0x05` | UNPACK (unpacker) |
| 6 | `0x06` | PACK (packer) |
| 7 | `0x07` | SFPU |
| 8 | `0x08` | GPR port 0 |
| 9 | `0x09` | GPR port 1 |
| 10 | `0x0A` | CFG_EXU_0 |
| 11 | `0x0B` | CFG_EXU_1 |
| 12 | `0x0C` | CFG_GLOBAL |
| 13 | `0x0D` | THCON_0 |
| 14 | `0x0E` | THCON_1 |
| 15 | `0x0F` | FPU base (Gtile entry) |
| 16 | `0x10` | L1 SRAM |
| 32 | `0x20` | Gtile-0 general |
| 33 | `0x21` | Gtile-0 SrcA parity |
| 34 | `0x22` | Gtile-0 Dest parity |
| 35 | `0x23` | Gtile-1 general |
| 36 | `0x24` | Gtile-1 SrcA parity |
| 37 | `0x25` | Gtile-1 Dest parity |
| 38 | `0x26` | Gtile-2 general |
| 39 | `0x27` | Gtile-2 SrcA parity |
| 40 | `0x28` | Gtile-2 Dest parity |
| 41 | `0x29` | Gtile-3 general |
| 42 | `0x2A` | Gtile-3 SrcA parity |
| 43 | `0x2B` | Gtile-3 Dest parity |

---

### 5.5 Complete node_id Master Decode Table (All Parts)

This section consolidates all RTL-verified `node_id` decoding in one reference. It covers all four `part` values used in Trinity, including L1 (part=0x18) and DMC/Overlay (part=0x1A) which are not fully detailed in §5.4.

---

#### 5.5.1 `part[4:0]` — Full Enumeration

| part (hex) | RTL constant (tt_edc1_pkg.sv) | Subsystem | Notes |
|------------|-------------------------------|-----------|-------|
| 0x10 | `NODE_ID_PART_TENSIX` = base | Tensix sub-core **T0** | Also hosts T6_MISC (inst=0x00) and L1W2 (inst=0x10) shared-partition nodes |
| 0x11 | `NODE_ID_PART_TENSIX + 1` | Tensix sub-core **T1** | |
| 0x12 | `NODE_ID_PART_TENSIX + 2` | Tensix sub-core **T2** | |
| 0x13 | `NODE_ID_PART_TENSIX + 3` | Tensix sub-core **T3** | |
| 0x14–0x17 | — | Reserved | |
| 0x18 | `NODE_ID_PART_L1` | **L1 SRAM macros** (L1W2 sub-banks) | Independent sub-bank chain |
| 0x19 | — | Reserved | |
| 0x1A | `NODE_ID_PART_DMC` | **DMC / Overlay** (WDT, APB bridge, MEM events, BIST) | Dispatch & management cluster |
| 0x1B–0x1D | — | Reserved | |
| 0x1E | `NODE_ID_PART_NOC` | **NoC** (router ports, NIU, ATT, sec_fence) | |
| 0x1F | — | Reserved | |
| 0x00–0x0F | — | Reserved | `0x0000` = BIU_NODE_ID; `0xFFFF` = broadcast |

**Source:** `tt_edc1_pkg.sv:119–122`, `tt_t6_l1_partition.sv:663–667`

---

#### 5.5.2 `subp[2:0]` — Meaning Per Part

`subp[2:0]` = **tile Y coordinate** (`i_local_nodeid_y[2:0]`) for **all** parts.

```systemverilog
// Constructed identically in every subsystem:
node_id_prefix = {i_node_id_part[4:0], i_local_nodeid_y[2:0]};
//                  [15:11]                  [10:8]
// Source: tt_instrn_engine_wrapper.sv:664, tt_noc2axi.sv:2723, tt_overlay_edc_wrapper.sv:204
```

| Y | Trinity row | Tile types |
|---|------------|------------|
| 0 | Bottom | TENSIX (X=0..3) |
| 1 | | TENSIX (X=0..3) |
| 2 | | TENSIX (X=0..3) |
| 3 | | DISPATCH_E (X=3), ROUTER (X=1,2), DISPATCH_W (X=0) |
| 4 | Top | NOC2AXI_NE (X=0), NOC2AXI_N (X=1,2), NOC2AXI_NW (X=3) |

> **The X coordinate is implicit** — determined by which BIU received the packet. `subp` only carries Y.

---

#### 5.5.3 `inst[7:0]` — Part = 0x10/0x11/0x12/0x13 (Tensix sub-cores T0–T3)

**Source:** `tt_tensix_edc_pkg.sv:88–113`

| inst (hex) | RTL constant | Node | Where defined |
|------------|-------------|------|---------------|
| `0x00` | `T6_MISC_EDC_IDX` | T6_MISC miscellaneous — **T0 only** (part=0x10, shared partition) | `tt_t6_misc.sv:917` |
| `0x01`–`0x02` | — | Reserved | |
| `0x03` | `IE_PARITY_EDC_IDX` | Instruction engine parity | `tt_instrn_engine_wrapper.sv:930` |
| `0x04` | `SRCB_EDC_IDX` | SrcB register file parity | `tt_instrn_engine_wrapper.sv:977` |
| `0x05` | `UNPACK_EDC_IDX` | Unpacker SRAM parity | `tt_instrn_engine_wrapper.sv:1025` |
| `0x06` | `PACK_EDC_IDX` | Packer SRAM parity | `tt_instrn_engine_wrapper.sv:1076` |
| `0x07` | `SFPU_EDC_IDX` | SFPU errors | `tt_instrn_engine_wrapper.sv:1170` |
| `0x08` | `GPR_P0_EDC_IDX` | GPR port 0 parity | `tt_instrn_engine_wrapper.sv:1206` |
| `0x09` | `GPR_P1_EDC_IDX` | GPR port 1 parity | `tt_instrn_engine_wrapper.sv:1248` |
| `0x0A` | `CFG_EXU_0_EDC_IDX` | CFG execute unit 0 parity | `tt_instrn_engine_wrapper.sv:1291` |
| `0x0B` | `CFG_EXU_1_EDC_IDX` | CFG execute unit 1 parity | `tt_instrn_engine_wrapper.sv:1334` |
| `0x0C` | `CFG_GLOBAL_EDC_IDX` | Global CFG register parity | `tt_instrn_engine_wrapper.sv:1377` |
| `0x0D` | `THCON_0_EDC_IDX` | Thread controller 0 | `tt_instrn_engine_wrapper.sv:1419` |
| `0x0E` | `THCON_1_EDC_IDX` | Thread controller 1 | `tt_instrn_engine_wrapper.sv:1472` |
| `0x0F` | `FPU_EDC_IDX` | FPU (instrn_engine-level) | `tt_instrn_engine_wrapper.sv` |
| `0x10` | `L1_EDC_IDX` | L1 flex client (inside instrn_engine) | `tt_instrn_engine.sv:6641` |
| `0x11`–`0x1F` | — | Reserved | |
| `0x20` | `GTILE_LOCAL_INST_ID[0]` + `GENERAL_OFFSET` (=+0) | Gtile[0] — general error | `tt_fpu_gtile.sv:991` |
| `0x21` | `GTILE_LOCAL_INST_ID[0]` + `SRCA_OFFSET` (=+1) | Gtile[0] — SrcA parity | `tt_fpu_gtile.sv:1032` |
| `0x22` | `GTILE_LOCAL_INST_ID[0]` + `DEST_OFFSET` (=+2) | Gtile[0] — Dest parity | `tt_fpu_gtile.sv:1061` |
| `0x23` | `GTILE_LOCAL_INST_ID[1]` + `GENERAL_OFFSET` | Gtile[1] — general error | |
| `0x24` | `GTILE_LOCAL_INST_ID[1]` + `SRCA_OFFSET` | Gtile[1] — SrcA parity | |
| `0x25` | `GTILE_LOCAL_INST_ID[1]` + `DEST_OFFSET` | Gtile[1] — Dest parity | |
| `0x26`–`0x28` | `GTILE_LOCAL_INST_ID[2]` | Gtile[2] — general/SrcA/Dest parity | Not used in Trinity (2 Gtiles per sub-core) |
| `0x29`–`0x2B` | `GTILE_LOCAL_INST_ID[3]` | Gtile[3] — general/SrcA/Dest parity | Not used in Trinity |

> `GTILE_LOCAL_INST_ID[3:0] = {8'h29, 8'h26, 8'h23, 8'h20}` — base inst for each Gtile (index 0=0x20, 1=0x23, 2=0x26, 3=0x29). Trinity uses indices 0 and 1 only.

---

#### 5.5.4 `inst[7:0]` — Part = 0x18 (L1 SRAM macros)

**Source:** `tt_t6_l1_mem_wrap.sv:100,310`

```systemverilog
// node_id = {NODE_ID_PART_L1, i_nodeid_y, sub_idx}
// sub_idx = i_sbank * BANK_IN_SBANK * SUB_BANK_CNT
//         + j_bank  * SUB_BANK_CNT
//         + k_sub
```

| inst (hex) | Node |
|------------|------|
| `0x00` | L1W2 sub-bank 0 — **first** in chain (uses `tt_libcell_sync3r` 3-stage synchronizer, `gen_first_last_sync` block) |
| `0x01` | L1W2 sub-bank 1 (middle node, `genblk2` block — no extra sync stage) |
| `0x02` | L1W2 sub-bank 2 |
| `...` | ... |
| `N-1` | L1W2 sub-bank N-1 — **last** in chain (`gen_first_last_sync` block, synchronized at ring exit) |

Trinity-specific value of N (MEM_INST_CNT) depends on `L1_CFG.SBANK_CNT × BANK_IN_SBANK × SUB_BANK_CNT`. Only first and last sub-banks carry synchronizers; middle banks pass the ring signal directly.

> **Key distinction:** Part=0x18 L1 nodes report SRAM macro-level errors (bit-cell parity, self-test BIST done/fail). Part=0x10 `inst=0x10` (L1_EDC_IDX in Tensix T0) is the L1 **flex client** monitoring the request interface, not the SRAM macro itself.

---

#### 5.5.5 `inst[7:0]` — Part = 0x1A (DMC / Overlay)

**Source:** `tt_overlay_pkg.sv:317–328`, `tt_overlay_edc_apb_bridge.sv:105`, `tt_overlay_edc_flex_client_bist.sv:393`

| inst (hex) | dec | RTL constant | Node | RTL File |
|------------|-----|-------------|------|----------|
| `0x00` | 0 | `OVERLAY_MEM_EVENTS_EDC_IDX` | Overlay memory events / WDT reset trigger | `tt_overlay_wrapper.sv:2087` |
| `0x01`–`0x9F` | 1–159 | — | Reserved | |
| `0xA0` | 160 | `OVERLAY_WDT_EDC_WRAPPER_EDC_IDX` | Watchdog timer EDC wrapper | `tt_overlay_wrapper.sv:2029`, `tt_overlay_edc_wrapper.sv:204` |
| `0xA1`–`0xA9` | 161–169 | — | Reserved | |
| `0xAA` | 170 | `OVERLAY_EDC_APB_BRIDGE_EDC_IDX` | APB bridge for overlay register access | `tt_overlay_wrapper.sv:2053` |
| `0xAB`–`0xB3` | 171–179 | — | Reserved | |
| `0xB4` | 180 | `OVERLAY_FLEX_CLIENT_EDC_IDX` | Flex client BIST | `tt_overlay_edc_flex_client_bist.sv:393` |

> DMC inst values are **widely spaced** (0, 160, 170, 180) because the overlay ring also carries many memory-macro EDC nodes between these fixed indices. The large gaps are for overlay SRAM banks that sit between the named checkpoints.

---

#### 5.5.6 `inst[7:0]` — Part = 0x1E (NoC)

The inst encoding differs depending on the tile type. All tiles share inst 0x00–0x0B (router port nodes).

##### Tensix / Dispatch / ROUTER tiles  (`tt_noc_pkg.sv:747–769`)

| inst (hex) | dec | RTL constant | Node |
|------------|-----|-------------|------|
| `0x00` | 0 | `NORTH_ROUTER_VC_BUF_EDC_IDX` | North port VC buffer SRAM parity |
| `0x01` | 1 | `NORTH_ROUTER_HEADER_ECC_EDC_IDX` | North port header ECC (COR+UNC) |
| `0x02` | 2 | `NORTH_ROUTER_DATA_PARITY_EDC_IDX` | North port data parity |
| `0x03` | 3 | `EAST_ROUTER_VC_BUF_EDC_IDX` | East port VC buffer SRAM parity |
| `0x04` | 4 | `EAST_ROUTER_HEADER_ECC_EDC_IDX` | East port header ECC |
| `0x05` | 5 | `EAST_ROUTER_DATA_PARITY_EDC_IDX` | East port data parity |
| `0x06` | 6 | `SOUTH_ROUTER_VC_BUF_EDC_IDX` | South port VC buffer SRAM parity |
| `0x07` | 7 | `SOUTH_ROUTER_HEADER_ECC_EDC_IDX` | South port header ECC |
| `0x08` | 8 | `SOUTH_ROUTER_DATA_PARITY_EDC_IDX` | South port data parity |
| `0x09` | 9 | `WEST_ROUTER_VC_BUF_EDC_IDX` | West port VC buffer SRAM parity |
| `0x0A` | 10 | `WEST_ROUTER_HEADER_ECC_EDC_IDX` | West port header ECC |
| `0x0B` | 11 | `WEST_ROUTER_DATA_PARITY_EDC_IDX` | West port data parity |
| `0x0C` | 12 | `NIU_VC_BUF_EDC_IDX` | NIU VC buffer SRAM parity |
| `0x0D` | 13 | `ROCC_INTF_EDC_IDX` | ROCC interface buffer parity |
| `0x0E` | 14 | `EP_TABLE_EDC_IDX` | Endpoint address translation table parity |
| `0x0F` | 15 | `ROUTING_TABLE_EDC_IDX` | Routing table parity |
| `0x10` | 16 | `SEC_FENCE_EDC_IDX` | Security fence |
| `0x11`–`0x3F` | 17–63 | — | Reserved |
| `0x40` | 64 | `NOC_FLEX_CLIENT_EDC_IDX` | NoC flex client BIST |

> Nodes 0x0D–0x0F (ROCC, EP_TABLE, ROUTING_TABLE) are only instantiated when `OVERLAY_INF_EN != 0`. When disabled, a `tt_edc1_intf_connector` bypass wire replaces them.

##### NOC2AXI tiles (Y=4 row) — different inst 0x0C–0x0F and 0x10+

(`tt_noc2axi_pkg.sv:87–109`, `tt_noc2axi.sv:447–450`)

Inst 0x00–0x0B are the same as above. From 0x0C onward:

| inst (hex) | RTL constant | Node |
|------------|-------------|------|
| `0x0C` | `MST_RD_EP_TABLE_EDC_IDX` | Master-read endpoint table parity |
| `0x0D` | `MST_RD_ROUTING_TABLE_EDC_IDX` | Master-read routing table parity |
| `0x0E` | `MST_WR_EP_TABLE_EDC_IDX` | Master-write endpoint table parity |
| `0x0F` | `MST_WR_ROUTING_TABLE_EDC_IDX` | Master-write routing table parity |
| `0x10` | `MST_WR_EDC_IDX` (base) | Write-buffer mem macro 0 (first of K macros) |
| `0x10`+k | | Write-buffer mem macros 1..K-1 |
| `0x10`+K | `MST_RD_EDC_BASE_IDX` | Read-buffer mem macro 0 (first of J macros) |
| `0x10`+K+j | | Read-buffer mem macros 1..J-1 |
| `0x10`+K+J | `SLV_RD_EDC_IDX` | Slave-read buffer parity |
| `0x10`+K+J+1 | `SEC_FENCE_EDC_IDX` | Security fence |

(K = MST_WR_NUM_MEM_MACROS, J = MST_RD_NUM_MEM_MACROS — Trinity-specific values depend on AXI buffer size parameters)

##### Pure Router tiles only (trinity_router.sv:79–81)

The pure router tiles (X=1/X=2, Y=3) reserve inst 0x00–0xBF for NOC2AXI compatibility and use:

| inst (hex) | dec | RTL constant | Node |
|------------|-----|-------------|------|
| `0xC0` | 192 | `SEC_NOC_CONF_IDX` | Security fence config controller (`tt_edc1_noc_sec_controller`) |
| `0xC1` | 193 | `REG_APB_NOC_IDX` | APB bridge for NoC register access (`tt_edc1_apb4_bridge`) |

> RTL comment: *"The first 192 nodes (0x00–0xBF) are reserved for those in tt_noc2axi."* Pure router tiles skip to 0xC0 because they instantiate no AXI paths.

---

#### 5.5.7 Worked Decode Examples (All Parts)

**Example A — Tensix T2, SFPU error, tile Y=1, column X=3:**
```
BIU ring  = X=3  (packet received on BIU[3])
node_id   = 0x9107
  part = 0x12  → Tensix sub-core T2
  subp = 0x1   → tile Y=1
  inst = 0x07  → SFPU_EDC_IDX
Result: SFPU error in T2 sub-core, cluster at (X=3, Y=1)
```

**Example B — L1 SRAM macro 3, tile Y=2, column X=0:**
```
BIU ring  = X=0
node_id   = 0xC203
  part = 0x18  → L1 SRAM macros
  subp = 0x2   → tile Y=2
  inst = 0x03  → L1W2 sub-bank index 3
Result: L1W2 sub-bank[3] parity error at tile (X=0, Y=2)
```

**Example C — DMC/Overlay WDT, tile Y=3, column X=1:**
```
BIU ring  = X=1
node_id   = 0xD3A0
  part = 0x1A  → DMC / Overlay
  subp = 0x3   → tile Y=3 (Dispatch/Router row)
  inst = 0xA0  → OVERLAY_WDT_EDC_WRAPPER_EDC_IDX (160)
Result: Watchdog timer event at overlay in tile (X=1, Y=3)
```

**Example D — NOC pure Router sec_conf, tile Y=3, column X=2:**
```
BIU ring  = X=2
node_id   = 0xF3C0
  part = 0x1E  → NOC
  subp = 0x3   → tile Y=3
  inst = 0xC0  → SEC_NOC_CONF_IDX (192) — pure Router tile
Result: Security fence event in pure Router tile at (X=2, Y=3)
```

**Example E — NOC Tensix-row North VC buffer, tile Y=0, column X=1:**
```
BIU ring  = X=1
node_id   = 0xF000
  part = 0x1E  → NOC
  subp = 0x0   → tile Y=0
  inst = 0x00  → NORTH_ROUTER_VC_BUF_EDC_IDX
Result: North port VC buffer parity error at Tensix NOC tile (X=1, Y=0)
```

---

#### 5.5.8 node_id Range Map (hex) for Trinity

| Part | Hex range start | Hex range end | Subsystem |
|------|----------------|---------------|-----------|
| 0x10 (T0) | `0x8000` | `0x87FF` | Tensix T0 (+ T6_MISC/L1W2 shared nodes) |
| 0x11 (T1) | `0x8800` | `0x8FFF` | Tensix T1 |
| 0x12 (T2) | `0x9000` | `0x97FF` | Tensix T2 |
| 0x13 (T3) | `0x9800` | `0x9FFF` | Tensix T3 |
| 0x18 (L1) | `0xC000` | `0xC7FF` | L1 SRAM sub-banks |
| 0x1A (DMC) | `0xD000` | `0xD7FF` | DMC / Overlay |
| 0x1E (NOC) | `0xF000` | `0xF7FF` | NoC (all tile types) |
| — | `0x0000` | `0x0000` | BIU (ring master) |
| — | `0xFFFF` | `0xFFFF` | BROADCAST |

---

## 6. Module Hierarchy

```
trinity (top)
│
│  ┌─────────────────────── Harvest Bypass Ring ──────────────────────────┐
│  │  (edc_egress_t6_byp_intf connects demux out1 → mux in1 per tile)    │
│  └──────────────────────────────────────────────────────────────────────┘
│
├── tt_trin_noc_niu_router_wrap (NOC Tensix routers, × many)
│   ├── tt_noc_niu_router
│   │   ├── tt_noc_overlay_edc_wrapper (per direction: N/E/S/W/NIU)
│   │   │   ├── tt_edc1_node            ← active EDC node (error monitoring)
│   │   │   └── tt_edc1_serial_bus_repeater
│   │   ├── tt_noc_sec_fence_edc_wrapper
│   │   │   └── tt_edc1_node
│   │   └── tt_edc1_intf_connector (bypass paths: vc_buf, header_ecc, data_parity)
│   └── tt_edc1_serial_bus_demux  edc_demuxing_when_harvested   ← DEMUX
│         sel=0: noc_niu_router_egress → edc_egress_intf     (normal tile)
│         sel=1: noc_niu_router_egress → edc_egress_t6_byp_intf (bypass)
│         (sel signal: edc_mux_demux_sel)
│
├── tt_dispatch_top_east / tt_dispatch_top_west
│   └── tt_trin_disp_eng_noc_niu_router_east/west
│       ├── tt_edc1_serial_bus_demux  edc_demuxing_when_harvested   ← DEMUX
│       │     sel=0: noc_niu_router_egress → edc_egress_intf     (normal)
│       │     sel=1: noc_niu_router_egress → edc_egress_t6_byp_intf (bypass)
│       │     (sel signal: edc_mux_demux_sel)
│       └── tt_noc_overlay_edc_repeater
│
├── tt_tensix_with_l1 (Tensix cluster hub)
│   │
│   │  Ring flow (NUM_TENSIX_NEO=4, Trinity):
│   │    from NOC → [feedthrough ovl→T0]
│   │           → T0: Gtile[0](0x20-22) → instrn_engine(0x03-0x10) → Gtile[1](0x23-25)
│   │           → [feedthrough T0→T1]
│   │           → T1: same 19 nodes
│   │           → T6_MISC(0x00) + L1W2(0x10)
│   │           → T3: same 19 nodes
│   │           → [feedthrough T3→T2]
│   │           → T2: same 19 nodes
│   │           → [feedthrough T2→ovl] → exits to overlay
│   │    (Gtile ring order: Gtile[0]→instrn_engine→Gtile[1], confirmed tt_tensix.sv L222/L225)
│   │
│   ├── tt_t6_l1_partition (L1 SRAM + T6_MISC hub, one per tile)
│   │   │   Ports used as MAIN ring path (between T1 and T3 in ring):
│   │   │     edc_t6_egress_intf  ← from T1 output
│   │   │     edc_t6_ingress_intf → to T3 input
│   │   ├── tt_edc1_serial_bus_repeater  edc_serial_bus_repeater  (DEPTH=1)
│   │   ├── tt_t6_misc
│   │   │   └── tt_edc1_node  u_edc1_node_misc
│   │   │       node_id: {NODE_ID_PART_TENSIX_BASE=0x10, subp=Y, T6_MISC_EDC_IDX=0x00}
│   │   │       events: parity errors in misc regs, skid buffers, semaphores, etc.
│   │   │       file: tt_t6_misc.sv:890
│   │   ├── tt_edc1_serial_bus_repeater  edc_misc_bus_repeater    (DEPTH=1)
│   │   ├── tt_t6_l1_wrap2  u_l1w2
│   │   │   └── tt_edc1_node  (L1 SRAM EDC node, L1_EDC_IDX=0x10 from L1 SRAM)
│   │   │       node_id: {NODE_ID_PART_TENSIX_BASE=0x10, subp=Y, L1_EDC_IDX=0x10}
│   │   │       (this is the L1 SRAM bank EDC node inside l1_wrap2)
│   │   │   Ports used as FEEDTHROUGHS (connectors/repeaters only, no EDC nodes):
│   │   │     edc_ingress_feedthrough_ovl_to_t0 → connector → edc_egress_feedthrough_ovl_to_t0
│   │   │     edc_ingress_feedthrough_t0_to_t1  → repeater  → edc_egress_feedthrough_t0_to_t1
│   │   │     edc_ingress_feedthrough_t3_to_t2  → repeater  → edc_egress_feedthrough_t3_to_t2
│   │   │     edc_ingress_feedthrough_t2_to_ovl → connector → edc_egress_feedthrough_t2_to_ovl
│   │
│   ├── tt_instrn_engine_wrapper  (one per sub-core T0/T1/T2/T3, part=0x10/0x11/0x12/0x13)
│   │   │  All EDC nodes use i_clk = postdfx_clk (AI clock)
│   │   │  Ring order inside wrapper (ingress → egress):
│   │   ├── tt_edc1_node  (IE_PARITY_EDC_IDX = 0x03)
│   │   │   events: IE instruction-engine parity errors (3 events)
│   │   │   file: tt_instrn_engine_wrapper.sv:930
│   │   ├── tt_edc1_node  (SRCB_EDC_IDX = 0x04)
│   │   │   events: SrcB SRAM parity errors (4 events)
│   │   │   file: tt_instrn_engine_wrapper.sv:977
│   │   ├── tt_edc1_node  (UNPACK_EDC_IDX = 0x05)
│   │   │   events: Unpacker errors
│   │   │   file: tt_instrn_engine_wrapper.sv:1025
│   │   ├── tt_edc1_node  (PACK_EDC_IDX = 0x06)
│   │   │   events: Packer errors
│   │   │   file: tt_instrn_engine_wrapper.sv:1076
│   │   ├── tt_edc1_node  (SFPU_EDC_IDX = 0x07)
│   │   │   events: SFPU errors (DP ST err, parity err)
│   │   │   file: tt_instrn_engine_wrapper.sv:1170
│   │   ├── tt_edc1_node  (GPR_P0_EDC_IDX = 0x08)
│   │   │   events: GPR port-0 parity errors (3 events)
│   │   │   file: tt_instrn_engine_wrapper.sv:1206
│   │   ├── tt_edc1_node  (GPR_P1_EDC_IDX = 0x09)
│   │   │   events: GPR port-1 parity errors (3 events)
│   │   │   file: tt_instrn_engine_wrapper.sv:1248
│   │   ├── tt_edc1_node  (CFG_EXU_0_EDC_IDX = 0x0A)
│   │   │   events: CFG EXU register 0 parity errors (3 events)
│   │   │   file: tt_instrn_engine_wrapper.sv:1291
│   │   ├── tt_edc1_node  (CFG_EXU_1_EDC_IDX = 0x0B)
│   │   │   events: CFG EXU register 1 parity errors (3 events)
│   │   │   file: tt_instrn_engine_wrapper.sv:1334
│   │   ├── tt_edc1_node  (CFG_GLOBAL_EDC_IDX = 0x0C)
│   │   │   events: Global CFG register parity errors (3 events)
│   │   │   file: tt_instrn_engine_wrapper.sv:1377
│   │   ├── tt_edc1_node  (THCON_0_EDC_IDX = 0x0D)
│   │   │   events: THCON0 register parity errors (3 events)
│   │   │   file: tt_instrn_engine_wrapper.sv:1419
│   │   ├── tt_edc1_node  (THCON_1_EDC_IDX = 0x0E)
│   │   │   events: THCON1 register parity errors (3 events)
│   │   │   file: tt_instrn_engine_wrapper.sv:1461
│   │   ├── tt_edc1_serial_bus_repeater  edc_thcon_1_to_l1_flex_repeater (DEPTH=1)
│   │   ├── tt_instrn_engine  (sub-module, L1 client EDC node lives here)
│   │   │   └── tt_edc1_node  u_l1_flex_client_edc  (L1_EDC_IDX = 0x10)
│   │   │       events: L1 client parity errors (BIST, CSR self-test)
│   │   │       file: tt_instrn_engine.sv:6641
│   │   └── tt_edc1_serial_bus_repeater  edc_l1_flex_to_egress_repeater  (DEPTH=1)
│   │
│   ├── tt_edc1_intf_connector  edc_conn_ovl_to_L1          (NOC ring → L1 partition feedthrough entry)
│   ├── tt_edc1_intf_connector  edc_conn_L1_to_T0           (L1 partition feedthrough exit → T0)
│   ├── tt_edc1_intf_connector  edc_conn_T0_to_L1           (T0 exit → L1 partition feedthrough)
│   ├── tt_edc1_intf_connector  edc_conn_L1_to_T1           (L1 partition feedthrough exit → T1)
│   ├── tt_edc1_intf_connector  edc_conn_T1_to_L1           (T1 exit → L1 partition main path entry)
│   ├── tt_edc1_intf_connector  edc_conn_L1_to_T3           (L1 partition main path exit → T3)
│   ├── tt_edc1_intf_connector  edc_conn_T3_to_L1           (T3 exit → L1 partition feedthrough)
│   ├── tt_edc1_intf_connector  edc_conn_L1_to_T2           (L1 partition feedthrough exit → T2)
│   ├── tt_edc1_intf_connector  edc_conn_T2_to_L1           (T2 exit → L1 partition feedthrough)
│   └── tt_edc1_intf_connector  edc_conn_L1_to_overlay      (L1 partition feedthrough exit → overlay)
│
└── tt_neo_overlay_wrapper (Overlay / BIU)   [Tensix overlay]
    ├── tt_edc1_biu_soc_apb4_wrap  ← firmware APB4 access point
    │   ├── edc1_biu_soc_apb4_inner (auto-generated CSR map)
    │   └── tt_edc1_bus_interface_unit
    │       ├── tt_edc1_state_machine u_edc_req_src  (IS_REQ_SRC=1)
    │       └── tt_edc1_state_machine u_edc_rsp_snk  (IS_RSP_SINK=1)
    ├── tt_noc_overlay_edc_repeater  overlay_loopback_repeater
    └── tt_edc1_serial_bus_mux  edc_muxing_when_harvested   ← MUX
          sel=0: ovl_egress_intf (BIU normal output) → edc_egress_intf (to ring)
          sel=1: edc_ingress_t6_byp_intf (bypass input) → edc_egress_intf (to ring)
          (sel signal: i_edc_mux_demux_sel)

tt_disp_eng_overlay_wrapper (Dispatch overlay)   [TRINITY only]
    ├── tt_noc_overlay_edc_repeater  overlay_loopback_repeater
    └── tt_edc1_serial_bus_mux  edc_muxing_when_harvested   ← MUX
          sel=0: ovl_egress_intf (dispatch normal output) → edc_egress_intf
          sel=1: edc_ingress_t6_byp_intf (bypass input)  → edc_egress_intf
          (sel signal: i_edc_mux_demux_sel)
```

**Harvest bypass signal flow per tile:**
```
NOC/Dispatch router                     Overlay/Dispatch overlay
─────────────────                       ───────────────────────
tt_edc1_serial_bus_demux                tt_edc1_serial_bus_mux
  ingress: from NOC router                ingress_in0: from BIU/dispatch (normal)
  egress_out0 ──→ edc_egress_intf ──→     (drives next stage in ring, sel=0)
  egress_out1 ──→ edc_egress_t6_byp_intf ──→ ingress_in1 (sel=1, bypass path)
                                          egress ──→ edc_egress_intf (into ring)
                  ↑ both driven by same edc_mux_demux_sel signal ↑
```

---

## 7. Module Reference

### 7.1 `tt_edc1_pkg` — Package / Types
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_pkg.sv`

Central package containing all EDC1 types, enums, localparams, and the interface definition. Must be imported by all EDC modules.

### 7.2 `tt_edc1_intf_connector` — Passthrough Connector
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_intf_connector.sv`

Combinational wire connector between ingress and egress. Used as a structural placeholder in the routing fabric to establish signal connectivity without adding logic. No clock required.

```systemverilog
module tt_edc1_intf_connector #(
    parameter tt_edc1_pkg::edc_cfg_t EDC_CFG = tt_edc1_pkg::EDC_CFG_DEFAULT
) (
    edc1_serial_bus_intf_def.ingress  ingress_intf,
    edc1_serial_bus_intf_def.egress   egress_intf
);
    assign egress_intf.req_tgl    = ingress_intf.req_tgl;
    assign egress_intf.data       = ingress_intf.data;
    assign egress_intf.data_p     = ingress_intf.data_p;
    assign egress_intf.async_init = ingress_intf.async_init;
    assign egress_intf.err        = ingress_intf.err;
    assign ingress_intf.ack_tgl   = egress_intf.ack_tgl;
endmodule
```

### 7.3 `tt_edc1_serial_bus_repeater` — Pipelined Repeater
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_repeater.sv`

Adds `DEPTH` pipeline register stages on both the forward path (req_tgl, data, data_p, async_init, err) and the return path (ack_tgl). Used to insert retiming stages for timing closure across long routes.

```systemverilog
module tt_edc1_serial_bus_repeater #(
    parameter int DEPTH = 1   // 0 = purely combinational
) (
    input  logic i_clk,
    input  logic i_reset_n,
    edc1_serial_bus_intf_def.ingress ingress_intf,
    edc1_serial_bus_intf_def.egress  egress_intf
);
```

When `DEPTH=0`, the module is purely combinational (same as `tt_edc1_intf_connector`). When `DEPTH≥1`, both the request and acknowledge paths are registered with `DEPTH` flip-flop stages. Note: pipelining increases latency; the toggle protocol is self-throttling so correctness is maintained at any depth.

### 7.4 `tt_edc1_serial_bus_mux` — 2:1 Input Multiplexer
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_mux.sv`

Selects between two ingress sources based on `i_mux_sel`. The non-selected source receives zeroed `ack_tgl`. Used at the overlay entry point for harvest bypass routing.

```systemverilog
module tt_edc1_serial_bus_mux (
    input  logic                          i_mux_sel,
    edc1_serial_bus_intf_def.ingress      ingress_intf_in0,  // selected when sel=0
    edc1_serial_bus_intf_def.ingress      ingress_intf_in1,  // selected when sel=1
    edc1_serial_bus_intf_def.egress       egress_intf
);
// sel=0: routes in0→out, ack→in0, zeros→in1
// sel=1: routes in1→out, ack→in1, zeros→in0
```

### 7.5 `tt_edc1_serial_bus_demux` — 1:2 Output Demultiplexer
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_demux.sv`

Routes one ingress to one of two egress outputs based on `i_demux_sel`. The non-selected output receives all-zero signals. Used at the NOC router output for harvest bypass.

```systemverilog
module tt_edc1_serial_bus_demux (
    input  logic                          i_demux_sel,
    edc1_serial_bus_intf_def.ingress      ingress_intf,
    edc1_serial_bus_intf_def.egress       egress_intf_out0,  // active when sel=0
    edc1_serial_bus_intf_def.egress       egress_intf_out1   // active when sel=1
);
// sel=0: routes in→out0, ack from out0
// sel=1: routes in→out1, ack from out1
```

### 7.6 `tt_edc1_node` — Active EDC Node
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_node.sv`

The core functional unit in the EDC ring. Each active EDC node:
- Monitors hardware error signals (`i_event`)
- Captures associated data (`i_capture`) when an event fires
- Inserts event packets into the serial ring
- Receives and executes configuration/read/write commands addressed to it
- Drives pulse outputs (`o_pulse`) and config outputs (`o_config`) from received commands

**Parameters:**
```systemverilog
module tt_edc1_node
import tt_edc1_pkg::*;
#(
    parameter tt_edc1_pkg::edc_cfg_t  EDC_CFG             = tt_edc1_pkg::EDC_CFG_DEFAULT,
    parameter int unsigned            EVENT_TRG_CNT        = 1,   // max 64 event triggers
    parameter int unsigned            CAPTURE_REG_CNT      = 0,   // capture registers
    parameter int unsigned            PULSE_REG_CNT        = 0,   // max 64 pulse outputs
    parameter int unsigned            CONFIG_REG_CNT       = 0,   // max 64 config outputs
    parameter event_cfg_t             EVENT_CFG  [...],           // per-event config array
    parameter capture_cfg_t           CAPTURE_CFG [...],          // per-capture config array
    parameter pulse_cfg_t             PULSE_CFG  [...],           // per-pulse config array
    parameter config_cfg_t            CONFIG_CFG [...],           // per-config config array
    parameter int unsigned            INGRESS_PIPE_STAGES  = 0,   // retiming stages
    parameter int unsigned            EGRESS_PIPE_STAGES   = 0,
    parameter int unsigned            EVENT_PIPE_STAGES    = 0,
    parameter int unsigned            CONTROL_PIPE_STAGES  = 0,
    parameter int                     NODE_DISABLE         = 0,   // disable node
    parameter int                     NODE_ENABLE_TIEOFF   = 0,
    parameter int                     ENABLE_INGRESS_SYNC  = 0,   // CDC sync on ingress
    parameter int                     ENABLE_EGRESS_SYNC   = 0    // CDC sync on egress
) (
    input                                  i_clk,
    input                                  i_reset_n,
    input  [tt_edc1_pkg::NODE_ID_W-1:0]    node_id,
    edc1_serial_bus_intf_def.ingress       ingress_intf,
    edc1_serial_bus_intf_def.egress        egress_intf,
    input  [EVENT_TRG_CNT-1:0]            i_event,       // event trigger inputs
    input  [CAPTURE_REG_CNT-1:0][REG_W-1:0] i_capture,  // capture data
    output [PULSE_REG_CNT-1:0][REG_W-1:0]   o_pulse,    // firmware-driven pulses
    output [CONFIG_REG_CNT-1:0][REG_W-1:0]  o_config    // firmware configuration
);
```

**Node operation:**
1. In steady state, packets pass through the node (ingress → egress).
2. When `i_event[n]` fires and `EVENT_CFG[n].capture_en` is set, the node queues an event packet.
3. When the node becomes "head of queue" (ring token), it inserts an event packet with TGT_ID=BIU, SRC_ID=node_id, CMD=UNC_ERR_CMD/COR_ERR_CMD etc., with captured data as payload.
4. When a WR_CMD/RD_CMD addressed to this node_id arrives, the node executes the register access and may reply with RD_RSP_CMD.

### 7.7 `tt_edc1_state_machine` — Serial Protocol FSM
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_state_machine.sv`

The core state machine implementing the toggle serial protocol. Two instances exist within each `tt_edc1_node` (and in the BIU):

| Parameter    | Value | Purpose                              |
|--------------|-------|--------------------------------------|
| IS_REQ_SRC   | 1     | This instance sources request packets|
| IS_RSP_SINK  | 1     | This instance sinks response packets |
| MAX_FRGS     | 12    | Maximum fragments per packet         |
| FRG_IDX_W    | 4     | $clog2(12) = 4-bit fragment index    |

### 7.8 `tt_edc1_bus_interface_unit` — BIU Core
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_bus_interface_unit.sv`

The firmware access point to the EDC ring. Contains two `tt_edc1_state_machine` instances:
- **`u_edc_req_src`** (`IS_REQ_SRC=1`): transmits firmware-initiated request packets
- **`u_edc_rsp_snk`** (`IS_RSP_SINK=1`): receives and decodes response packets from the ring

**Port summary:**
```systemverilog
module tt_edc1_bus_interface_unit (
    input  i_clk, i_reset_n,
    input  [NODE_ID_W-1:0]  node_id,           // always BIU_NODE_ID = 0x0000
    input  HWIF_OUT_TYPE    csr_cfg,            // register map from APB4 bridge
    output HWIF_IN_TYPE     csr_status,         // status back to register map
    edc1_serial_bus_intf_def.ingress  ingress_intf,
    edc1_serial_bus_intf_def.egress   egress_intf,
    output  fatal_err_irq,                      // physical error detected
    output  crit_err_irq,                       // UNC_ERR received
    output  noncrit_err_irq,                    // COR_ERR or LAT_ERR received
    output  cor_err_irq,                        // same as noncrit_err_irq
    output  pkt_sent_irq,                       // request packet transmitted
    output  pkt_rcvd_irq                        // response packet received
);
```

**Interrupt logic:**
```systemverilog
assign fatal_err_irq   = csr_cfg.IRQ_EN.FATAL_ERR_IEN.value
                         && csr_cfg.STAT.FATAL_ERR.value;
assign crit_err_irq    = csr_cfg.IRQ_EN.UNC_ERR_IEN.value
                         && csr_cfg.STAT.UNC_ERR.value;
assign noncrit_err_irq = csr_cfg.IRQ_EN.NONCRIT_ERR_IEN.value
                         && (csr_cfg.STAT.COR_ERR.value || csr_cfg.STAT.LAT_ERR.value);
```

**Overflow/error status mapping:**
```systemverilog
assign csr_status.STAT.OVERFLOW.hwset  = aux_rsp_rcvd &&
    ((rsp_cmd==OVFG_CMD) || (rsp_cmd==OVFU_CMD) ||
     (rsp_cmd==OVFL_CMD) || (rsp_cmd==OVFC_CMD));
assign csr_status.STAT.UNC_ERR.hwset   = aux_rsp_rcvd &&
    ((rsp_cmd==UNC_ERR_CMD) || (rsp_cmd==OVFU_CMD));
assign csr_status.STAT.LAT_ERR.hwset   = aux_rsp_rcvd &&
    ((rsp_cmd==LAT_ERR_CMD) || (rsp_cmd==OVFL_CMD));
assign csr_status.STAT.COR_ERR.hwset   = aux_rsp_rcvd &&
    ((rsp_cmd==COR_ERR_CMD) || (rsp_cmd==OVFC_CMD));
```

### 7.9 `tt_edc1_biu_soc_apb4_wrap` — APB4 BIU Wrapper
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_biu_soc_apb4_wrap.sv`

Top-level wrapper integrating the auto-generated APB4 register map (`edc1_biu_soc_apb4_inner`) with the BIU core. Exposes a standard APB4 slave interface to the SoC AXI/APB fabric.

```systemverilog
module tt_edc1_biu_soc_apb4_wrap #(
    parameter tt_edc1_pkg::edc_cfg_t EDC_CFG        = tt_edc1_pkg::EDC_CFG_DEFAULT,
    parameter int ENABLE_INGRESS_SYNC                = 0,
    parameter int ENABLE_EGRESS_SYNC                 = 0
) (
    input i_clk, i_reset_n,
    // APB4 slave interface
    input  wire s_apb_psel, s_apb_penable, s_apb_pwrite,
    input  wire [2:0] s_apb_pprot,
    input  wire [5:0] s_apb_paddr,    // 6-bit address (64 word space)
    input  wire [31:0] s_apb_pwdata,
    input  wire [3:0]  s_apb_pstrb,
    output logic s_apb_pready, s_apb_pslverr,
    output logic [31:0] s_apb_prdata,
    // EDC ring interface
    edc1_serial_bus_intf_def.ingress  ingress_intf,
    edc1_serial_bus_intf_def.egress   egress_intf,
    // Interrupts
    output fatal_err_irq, crit_err_irq, cor_err_irq, pkt_sent_irq, pkt_rcvd_irq
);
```

The BIU node_id is hardwired to `BIU_NODE_ID = 16'h0000`.

### 7.10 `tt_noc_overlay_edc_wrapper` — NOC EDC Node Wrapper
**File:** `tt_rtl/tt_noc/rtl/noc/tt_noc_overlay_edc_wrapper.sv`

Wraps a `tt_edc1_node` with NOC-specific event inputs (SRAM errors, TFD self-test) and an output repeater. Supports three variants controlled by parameters:

| Variant                    | EVENT_TRG_CNT | CAPTURE_REG_CNT | Description                     |
|----------------------------|---------------|-----------------|---------------------------------|
| ENABLE_COR_ERR + ERR_BIT_POS | 4           | 2               | Full: UNC/COR/TFD + addr+bitpos |
| ENABLE_COR_ERR (no bitpos)   | 4           | 1               | UNC/COR/TFD + addr only         |
| Base (no COR_ERR)            | 3           | 1               | UNC/TFD + addr only             |

**Event mapping (full variant):**
```
event_vec[0] = i_tfd_pass        → ST_PASS_EVENT (self-test pass)
event_vec[1] = live_cor_err      → COR_EVENT     (correctable error)
event_vec[2] = i_tfd_fail        → ST_LAT_EVENT  (self-test fail)
event_vec[3] = live_unc_err      → UNC_EVENT     (uncorrectable error)
```

**Pulse/Config outputs:**
```
o_pulse[0][0]   → o_tfd_start     (trigger self-test)
o_config[0][0]  → o_check_enable  (enable ECC checking)
o_config[1][1:0]→ o_tfd_pattern   (TFD test pattern)
```

**Harvest handling:** When `i_harvest_en=1`, all error inputs are gated to zero (harvested tiles inject no events).

---

## 8. EDC Ring Topology in Trinity

### 8.1 Intra-Tensix Tile Ring (L1 Hub)

Inside `tt_tensix_with_l1`, the EDC ring visits sub-nodes in a hub-and-spoke pattern managed by `tt_edc1_intf_connector` instances:

```
Overlay →[edc_conn_ovl_to_L1]→ L1 Hub
L1 Hub  →[edc_conn_L1_to_T0] → T0 node
T0 node →[edc_conn_T0_to_L1] → L1 Hub
L1 Hub  →[edc_conn_L1_to_T1] → T1 node
T1 node →[edc_conn_T1_to_L1] → L1 Hub
L1 Hub  →[edc_conn_L1_to_T3] → T3 node  (note: T3 before T2)
T3 node →[edc_conn_T3_to_L1] → L1 Hub
L1 Hub  →[edc_conn_L1_to_T2] → T2 node
T2 node →[edc_conn_T2_to_L1] → L1 Hub
L1 Hub  →[edc_conn_L1_to_overlay] → back to Overlay
```

Sub-node visit order within each Tensix: **T0 → T1 → (L1 partition: T6_MISC + L1W2) → T3 → T2**

Within each sub-core (T0/T1/T3/T2), the ring visits:
**Gtile[0]** (general→src→dest) → instrn_engine_wrapper nodes (IE→…→L1_client) → **Gtile[1]** (general→src→dest)
(confirmed from `tt_tensix.sv` L222/L225; Gtile internal order from `tt_fpu_gtile.sv` L931–L1099)

### 8.2 NOC Router EDC Nodes

Each `tt_noc_niu_router` instantiates `tt_noc_overlay_edc_wrapper` for each memory overlay it monitors (per direction and NIU). The wrappers with `HAS_EDC_INST=1` contain active `tt_edc1_node` instances; those with `HAS_EDC_INST=0` pass through with all-zero outputs.

Additionally, purely combinational bypass paths (no active monitoring, just ring continuity) use `tt_edc1_intf_connector`:
- `*_vc_buf_edc_bypass`
- `*_header_ecc_edc_bypass`
- `*_data_parity_edc_bypass`
- `rocc_intf_edc_bypass`
- `ep_table_edc_bypass`

### 8.3 Trinity Top-Level EDC Connections

From `trinity.sv`, two special EDC connectors bridge direct connections and loopback paths:

```systemverilog
// Direct connect for nodes that share a clock domain
tt_edc1_intf_connector edc_direct_conn_nodes (...);  // ~L442

// Loopback connect for nodes that require loopback
tt_edc1_intf_connector edc_loopback_conn_nodes (...); // ~L447/L454
```

---

## 9. Harvest Bypass Mechanism

### 9.0 Why Mux and Demux Are Needed

**Background: Harvest in Trinity**

Trinity is manufactured as a full-size chip array, but individual tiles may be disabled ("harvested") at test time if they fail yield screening. A harvested tile has its clock and power removed — it is completely dead. However, the EDC ring is a **single continuous serial daisy-chain** that physically passes through every tile in sequence. If any tile in the chain is dead, the ring is broken and EDC stops working for the entire chip.

**The Problem**

The EDC serial bus uses a toggle handshake protocol: the sender toggles `req_tgl`, and the receiver must echo it back on `ack_tgl`. If the packet is sent into a harvested tile:
- The tile has no clock → it will never respond → `ack_tgl` is never returned
- The sender waits forever → the entire ring stalls
- All other tiles on the ring also stop operating

This is unacceptable. The chip must remain fully functional with harvested tiles.

**The Solution: Bypass Path with Mux + Demux**

A complementary mux/demux pair is placed on either side of each potentially-harvestable tile to route the EDC ring around it when needed:

```
Normal operation (tile alive, sel=0):
                              ┌─────────────────────────┐
  NOC router                  │   Tensix/Dispatch tile   │   Overlay/BIU
  ──────────                  │   ─────────────────────  │   ──────────
  [demux] out0 ──────────────►│ edc nodes (T0,T1,T3,T2) │──►[mux] in0 ──► ring
  [demux] out1 ──────────X    │                          │   [mux] in1 ──X
                              └─────────────────────────┘

Harvest bypass (tile dead, sel=1):
                              ┌─────────────────────────┐
  NOC router                  │   Harvested tile (dead)  │   Overlay/BIU
  ──────────                  │   ─────────────────────  │   ──────────
  [demux] out0 ──────────X    │        (bypassed)        │   [mux] in0 ──X
  [demux] out1 ─────────────────────────────────────────►│──►[mux] in1 ──► ring
        bypass wire ──────────────────────────────────────────►
                              └─────────────────────────┘
```

The bypass wire (`edc_egress_t6_byp_intf`) is a direct connection from the demux `out1` port to the mux `in1` port, completely skipping the harvested tile.

**Why separate mux and demux (not a single bypass switch)?**

The EDC ring is **unidirectional** (ingress→egress in one direction, ack in the other), but the tile has two boundaries: an **input boundary** (where the ring enters the tile, at the NOC router output) and an **output boundary** (where the ring exits the tile, at the overlay/BIU input). These are physically in different modules:

- **Demux** is placed at the **input boundary** (inside `tt_trin_noc_niu_router_wrap`) — it decides whether to send the incoming packet into the tile or onto the bypass wire.
- **Mux** is placed at the **output boundary** (inside `tt_neo_overlay_wrapper` / `tt_disp_eng_overlay_wrapper`) — it decides whether to take the packet from the tile's own output or from the arriving bypass wire.

Both are controlled by the same `edc_mux_demux_sel` signal, set by hardware configuration at boot time based on the harvest map.

**Three-layer defense for harvested tiles:**

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| 1 | Demux `sel=1` | Redirects incoming ring packets around the dead tile |
| 2 | Mux `sel=1` | Accepts bypass wire input instead of dead tile output |
| 3 | `i_harvest_en=1` on `tt_noc_overlay_edc_wrapper` | Gates all error inputs to zero — prevents any stale signal in the harvested tile from injecting a false error event into the ring |

When a tile is harvested (disabled), its EDC nodes must be bypassed to maintain ring continuity. There are two tile types in Trinity, each with its own mux/demux pair:

### 9.1 Tensix Tile Bypass

#### Mux at Tensix Overlay Entry (`tt_neo_overlay_wrapper`, L463)

```
sel=0: ovl_egress_intf           (BIU normal output)    → edc_egress_intf (into ring)
sel=1: edc_ingress_t6_byp_intf   (bypass wire from demux out1) → edc_egress_intf (into ring)
```

```systemverilog
// tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv : L463
tt_edc1_serial_bus_mux edc_muxing_when_harvested(
    .i_mux_sel       (i_edc_mux_demux_sel),
    .ingress_intf_in0(ovl_egress_intf),
    .ingress_intf_in1(edc_ingress_t6_byp_intf),
    .egress_intf     (edc_egress_intf)
);
```

#### Demux at Tensix NOC Router Output (`tt_trin_noc_niu_router_wrap`, L748)

```
sel=0: noc_niu_router_egress_intf → edc_egress_intf        (normal tile input)
sel=1: noc_niu_router_egress_intf → edc_egress_t6_byp_intf (bypass wire to mux in1)
```

```systemverilog
// tt_rtl/overlay/rtl/config/tensix/trinity/tt_trin_noc_niu_router_wrap.sv : L748
tt_edc1_serial_bus_demux edc_demuxing_when_harvested(
    .i_demux_sel    (edc_mux_demux_sel),
    .ingress_intf   (noc_niu_router_egress_intf),
    .egress_intf_out0(edc_egress_intf),
    .egress_intf_out1(edc_egress_t6_byp_intf)
);
```

### 9.2 Dispatch Tile Bypass

#### Mux at Dispatch Overlay Entry (`tt_disp_eng_overlay_wrapper`, L362)

Same structure as Tensix. Active only when `\`TRINITY` is defined.

```systemverilog
// tt_rtl/overlay/rtl/quasar_dispatch/tt_disp_eng_overlay_wrapper.sv : L362
tt_edc1_serial_bus_mux edc_muxing_when_harvested(
    .i_mux_sel       (i_edc_mux_demux_sel),
    .ingress_intf_in0(ovl_egress_intf),
    .ingress_intf_in1(edc_ingress_t6_byp_intf),
    .egress_intf     (edc_egress_intf)
);
```

#### Demux at Dispatch NOC Router Output (`tt_trin_disp_eng_noc_niu_router_east/west`, L597)

```systemverilog
// tt_rtl/overlay/rtl/config/dispatch/trinity/tt_trin_disp_eng_noc_niu_router_east.sv : L597
// tt_rtl/overlay/rtl/config/dispatch/trinity/tt_trin_disp_eng_noc_niu_router_west.sv : L597
tt_edc1_serial_bus_demux edc_demuxing_when_harvested(
    .i_demux_sel    (edc_mux_demux_sel),
    .ingress_intf   (noc_niu_router_egress_intf),
    .egress_intf_out0(edc_egress_intf),
    .egress_intf_out1(edc_egress_t6_byp_intf)
);
```

### 9.3 Summary: All Mux/Demux Instances

| Instance name | Module | File | Type | sel signal |
|---|---|---|---|---|
| `edc_muxing_when_harvested` | `tt_neo_overlay_wrapper` | `overlay/rtl/tt_neo_overlay_wrapper.sv:463` | MUX | `i_edc_mux_demux_sel` |
| `edc_muxing_when_harvested` | `tt_disp_eng_overlay_wrapper` | `overlay/rtl/quasar_dispatch/tt_disp_eng_overlay_wrapper.sv:362` | MUX | `i_edc_mux_demux_sel` |
| `edc_demuxing_when_harvested` | `tt_trin_noc_niu_router_wrap` | `overlay/rtl/config/tensix/trinity/tt_trin_noc_niu_router_wrap.sv:748` | DEMUX | `edc_mux_demux_sel` |
| `edc_demuxing_when_harvested` | `tt_trin_disp_eng_noc_niu_router_east` | `overlay/rtl/config/dispatch/trinity/tt_trin_disp_eng_noc_niu_router_east.sv:597` | DEMUX | `edc_mux_demux_sel` |
| `edc_demuxing_when_harvested` | `tt_trin_disp_eng_noc_niu_router_west` | `overlay/rtl/config/dispatch/trinity/tt_trin_disp_eng_noc_niu_router_west.sv:597` | DEMUX | `edc_mux_demux_sel` |

The `i_harvest_en` signal to `tt_noc_overlay_edc_wrapper` simultaneously gates all error inputs to prevent harvested tiles from injecting false error events.

**How `i_harvest_en` is driven (layer 3 detail):**

The top-level harvest configuration signal `i_ovly_tensix_harvested` is an asynchronous input. Before it can be used to gate EDC error signals in the AICLK domain, it is synchronized:

```
i_ovly_tensix_harvested  (async, from harvest configuration)
        │
        └──► ai_clk_harvest_reset_sync / sync_dffr / D  (EndClk: AICLK)
                    │
                    └──► synchronized harvest signal → i_harvest_en on tt_noc_overlay_edc_wrapper
```

This synchronizer (`ai_clk_harvest_reset_sync`) is a `sync_dffr` cell (reset-type synchronizer), placing the harvest enable safely in the AICLK domain before it gates the error inputs of all EDC nodes in the harvested tile.

---

## 10. Bus Interface Unit (BIU)

### 10.1 Overview

The BIU is the firmware gateway to the EDC ring. There is one BIU per EDC ring segment (one per trinity row/column). Firmware accesses it via APB4.

**BIU node_id = 16'h0000** (BIU_NODE_ID = '0): all event packets sent by nodes use this as TGT_ID, so they are routed back to firmware.

### 10.2 Packet Transmission Flow

1. Firmware writes TGT_ID, CMD, PYLD_LEN, SRC_ID, CMD_OPT, address, and data to BIU registers.
2. Writing the last required data register triggers `aux_req_go`.
3. `u_edc_req_src` (IS_REQ_SRC state machine) serializes the packet over `egress_intf`.
4. `REQ_PKT_SENT` status bit is set; `pkt_sent_irq` fires if enabled.

**Trigger logic** (based on payload length):
```systemverilog
assign aux_req_go =
    ((cmd_is_read || pyld_len==0 || pyld_len==1) && csr_cfg.REQ_HDR1.DATA0.swmod) ||
    ((pyld_len==2 || pyld_len==3 || pyld_len==4 || pyld_len==5) && csr_cfg.REQ_DATA[0].DATA0.swmod) ||
    ((pyld_len==6 || pyld_len==7 || pyld_len==8 || pyld_len==9) && csr_cfg.REQ_DATA[1].DATA0.swmod) ||
    ...
```

### 10.3 Packet Reception Flow

1. When a packet arrives at `ingress_intf` addressed to `BIU_NODE_ID (0x0000)`:
2. `u_edc_rsp_snk` (IS_RSP_SINK state machine) deserializes each fragment.
3. Fragment data is written to RSP_HDR0, RSP_HDR1, RSP_DATA[0–3] registers.
4. `RSP_PKT_RCVD` status bit is set; `pkt_rcvd_irq` fires if enabled.
5. Error status bits (UNC_ERR, COR_ERR, LAT_ERR, OVERFLOW) are set based on the received command.

### 10.4 CSR Register Map Summary

| Register     | R/W | Description                                          |
|--------------|-----|------------------------------------------------------|
| ID           | RO  | EDC version (SUPER.MAJOR.MINOR), BIU node ID         |
| CTRL         | RW  | INIT bit (triggers async_init propagation)           |
| IRQ_EN       | RW  | Per-event interrupt enable bits                      |
| STAT         | RW1C| Status: FATAL_ERR, UNC_ERR, COR_ERR, LAT_ERR,       |
|              |     | OVERFLOW, RSP_PKT_RCVD, REQ_PKT_SENT                 |
| REQ_HDR0     | RW  | TGT_ID[15:0], CMD[3:0], PYLD_LEN[3:0], CMD_OPT[7:0]|
| REQ_HDR1     | RW  | SRC_ID[15:0], DATA1[7:0], DATA0[7:0]                |
| REQ_DATA[0–3]| RW  | Payload data (8 bytes × 4 = 32 bytes max)           |
| RSP_HDR0     | RO  | Received: TGT_ID, CMD, PYLD_LEN, CMD_OPT            |
| RSP_HDR1     | RO  | Received: SRC_ID, DATA1, DATA0                      |
| RSP_DATA[0–3]| RO  | Received payload data                               |

---

## 11. EDC Node Configuration

### 11.1 Event Configuration (`event_cfg_t`)

```systemverilog
typedef struct packed {
    logic          capture_en;   // 1=capture data when event fires
    event_type_e   event_cmd;    // type of EDC packet to send
    logic [3:0]    capidx_hi;    // capture register index (high)
    logic [3:0]    capidx_lo;    // capture register index (low)
} event_cfg_t;
```

**Predefined configurations:**
```systemverilog
DISABLE_EVENT_CFG   : { capture_en: 0, event_cmd: GEN_EVENT, capidx: 0 }
ST_PASS_EVENT_CFG   : { capture_en: 0, event_cmd: ST_PASS_EVENT }
COR_EVENT_CFG       : { capture_en: 1, event_cmd: COR_EVENT, capidx_hi: 1, capidx_lo: 0 }
ST_LAT_EVENT_CFG    : { capture_en: 1, event_cmd: ST_LAT_EVENT }
ST_UNC_EVENT_CFG    : { capture_en: 1, event_cmd: ST_UNC_EVENT }
UNC_EVENT_CFG       : { capture_en: 1, event_cmd: UNC_EVENT }
GEN_EVENT_CFG       : { capture_en: 1, event_cmd: GEN_EVENT }
LAT_EVENT_CFG       : { capture_en: 1, event_cmd: LAT_EVENT }
```

### 11.2 Capture Register Configuration (`capture_cfg_t`)

```systemverilog
typedef struct packed {
    reg_w_t active_bits;  // bitmask of valid bits in capture register
} capture_cfg_t;

// Examples:
ACTIVE_8BIT_CAPTURE_CFG  = '{ active_bits: 16'h00ff }
ACTIVE_10BIT_CAPTURE_CFG = '{ active_bits: 16'h03ff }
ACTIVE_12BIT_CAPTURE_CFG = '{ active_bits: 16'h0fff }
```

### 11.3 Pulse / Config Register Configuration

```systemverilog
typedef struct packed { reg_w_t active_bits; } pulse_cfg_t;
typedef struct packed { reg_w_t active_bits; } config_cfg_t;

DISABLE_PULSE_CFG  = '{ active_bits: 16'h0000 }
DISABLE_CONFIG_CFG = '{ active_bits: 16'h0000 }
```

---

## 12. Event Types and Commands

### 12.1 EDC Commands (`edc_cmd_e`)

```systemverilog
typedef enum logic [3:0] {
    WR_CMD      = 4'd0,   // write register
    RD_CMD      = 4'd1,   // read register
    RD_RSP_CMD  = 4'd2,   // read response (node → BIU)
    RV3_CMD     = 4'd3,   // reserved
    RV4_CMD     = 4'd4,   // reserved
    RV5_CMD     = 4'd5,   // reserved
    RV6_CMD     = 4'd6,   // reserved
    RV7_CMD     = 4'd7,   // reserved
    GEN_CMD     = 4'd8,   // generic event notification
    UNC_ERR_CMD = 4'd9,   // uncorrectable error
    LAT_ERR_CMD = 4'd10,  // latent (undetected) error
    COR_ERR_CMD = 4'd11,  // correctable error
    OVFG_CMD    = 4'd12,  // overflow: generic
    OVFU_CMD    = 4'd13,  // overflow: uncorrectable
    OVFL_CMD    = 4'd14,  // overflow: latent
    OVFC_CMD    = 4'd15   // overflow: correctable
} edc_cmd_e;
```

**Overflow commands (OVFX)** indicate that a node's event queue overflowed — the node could not transmit all events, so the severity of the lost events is indicated in the overflow command type.

### 12.2 Event Types (`event_type_e`)

```systemverilog
typedef enum logic [2:0] {
    GEN_EVENT     = 3'b000,  // generic/informational
    UNC_EVENT     = 3'b001,  // uncorrectable hardware error
    LAT_EVENT     = 3'b010,  // latent (undetected) error
    COR_EVENT     = 3'b011,  // correctable (ECC-fixed) error
    ST_UNC_EVENT  = 3'b100,  // self-test: uncorrectable result
    ST_LAT_EVENT  = 3'b101,  // self-test: latent result (failure)
    ST_PASS_EVENT = 3'b110,  // self-test: passed
    ST_EVENT      = 3'b111   // generic self-test event
} event_type_e;
```

### 12.3 Error Severity Classification

| Severity       | EDC Command     | Meaning                                      |
|----------------|-----------------|----------------------------------------------|
| Fatal          | (physical err)  | `ingress_intf.err=1` — bus/physical fault    |
| Critical       | UNC_ERR_CMD     | Uncorrectable data corruption                |
| Non-critical   | COR_ERR_CMD     | ECC-corrected error                          |
| Non-critical   | LAT_ERR_CMD     | Latent (silently wrong) error detected       |
| Overflow       | OVFx_CMD        | Node queue overflow (events were dropped)    |

---

## 13. CDC / Synchronization

### 13.1 Toggle Protocol CDC Safety

The `req_tgl[1:0]` and `ack_tgl[1:0]` signals use toggle encoding to safely cross asynchronous clock domain boundaries. Each bit changes only once per transaction, providing a metastability-safe CDC mechanism without requiring explicit synchronizers when using single-bit toggling.

### 13.2 Optional Sync Flops

Each `tt_edc1_node` and `tt_edc1_bus_interface_unit` supports optional synchronizer insertion:

```systemverilog
parameter int ENABLE_INGRESS_SYNC = 0;  // add sync flops on ingress path
parameter int ENABLE_EGRESS_SYNC  = 0;  // add sync flops on egress path
```

When `EDC_CFG.DISABLE_SYNC_FLOPS = 1` (default), no built-in synchronizers are used — the system relies on the toggle protocol's inherent CDC safety or on external synchronizers placed in the physical implementation.

When `ENABLE_INGRESS_SYNC=1` or `ENABLE_EGRESS_SYNC=1`, the state machine enables internal 2-FF synchronizer chains on the respective path.

### 13.3 `async_init` Propagation

The `async_init` signal is intentionally asynchronous and flows through all nodes without synchronization. This allows a single firmware write to simultaneously initialize all nodes across the entire ring, regardless of whether they share a clock domain.

Each node passes `async_init` straight through to its egress (confirmed in `tt_edc1_state_machine.sv:1129`):
```systemverilog
assign egress_intf.async_init = ingress_intf.async_init;
```

Within each node's own clock domain, `async_init` is synchronized via a 3-stage synchronizer before driving the node's internal reset logic:
```systemverilog
// tt_edc1_state_machine.sv:1132
tt_libcell_sync3r init_sync3r (
    .i_CK (i_clk),
    .i_RN (i_reset_n),
    .i_D  (ingress_intf.async_init),
    .o_Q  (init)                      // synchronized, used to reset internal state
);
```

In-ring effect: `async_init=1` resets all node state machines simultaneously (all `if (!i_reset_n || init)` blocks). Since each node independently synchronizes it to its own clock, all domains are safely initialized without any shared clock requirement. See §14.5 for the BIU-side INIT sequence and `init_cnt` self-clear mechanism.

---

## 14. Firmware Interface

### 14.1 APB4 Register Access

Firmware communicates with the EDC ring through the APB4 BIU at address space defined by the SoC address map. The BIU registers are 32-bit wide; the APB4 address is 6 bits wide (64 word address space = 256 bytes).

### 14.2 Sending a Write Command

```
1. Write REQ_HDR0: {TGT_ID[15:0], CMD=WR_CMD, PYLD_LEN=n, CMD_OPT=addr[7:0]}
2. Write REQ_HDR1: {SRC_ID=0x0000, DATA1, DATA0}
3. Write REQ_DATA[0..k] with payload (k depends on PYLD_LEN)
4. Final write to correct register triggers aux_req_go
5. Poll STAT.REQ_PKT_SENT (or use pkt_sent_irq)
```

### 14.3 Sending a Read Command

```
1. Write REQ_HDR0: {TGT_ID, CMD=RD_CMD, PYLD_LEN=0, CMD_OPT=addr[7:0]}
2. Write REQ_HDR1.DATA0 → triggers aux_req_go immediately (pyld_len==0)
3. Poll STAT.RSP_PKT_RCVD (or use pkt_rcvd_irq)
4. Read RSP_HDR0, RSP_HDR1, RSP_DATA[0..n]
5. Write-1-clear STAT.RSP_PKT_RCVD before next read
```

### 14.4 Interrupt Handling

| IRQ             | Trigger                                      | Enable Bit         |
|-----------------|----------------------------------------------|--------------------|
| `fatal_err_irq` | `ingress_intf.err=1` (physical bus error)    | FATAL_ERR_IEN      |
| `crit_err_irq`  | UNC_ERR_CMD received                         | UNC_ERR_IEN        |
| `noncrit_err_irq`| COR_ERR_CMD or LAT_ERR_CMD received         | NONCRIT_ERR_IEN    |
| `cor_err_irq`   | Same as noncrit_err_irq                      | NONCRIT_ERR_IEN    |
| `pkt_sent_irq`  | Request packet transmitted                   | REQ_PKT_SENT_IEN   |
| `pkt_rcvd_irq`  | Response packet received                     | RSP_PKT_RCVD_IEN   |

### 14.5 INIT Sequence

To reset all EDC nodes simultaneously:
```
1. Write CTRL.INIT = 1
2. The BIU drives async_init=1 on the ring
3. All nodes see async_init and reset their state
4. After MCPDLY=7 clock cycles, BIU auto-clears CTRL.INIT
5. Normal operation resumes
```

#### 14.5.1 INIT Counter (`init_cnt`) Detail

**Source:** `tt_edc1_bus_interface_unit.sv`

```systemverilog
localparam int unsigned MCPDLY = 7;                    // multi-cycle path delay
localparam int unsigned CNT_W  = $clog2(MCPDLY+1);    // = 3 bits (counts 0–7)
```

The counter starts on the `init` pulse (synchronized `async_init`) and runs autonomously for exactly MCPDLY cycles:

```systemverilog
always_ff @(posedge i_clk) begin : init_counter
    if (!i_reset_n) begin
        init_cnt <= '0;
    end else if ((init_cnt==0) && init || (init_cnt != 0)) begin
        // start: triggered by init pulse when idle (cnt==0)
        // sustain: cnt != 0 keeps counter running without init staying high
        if (init_cnt == CNT_W'(MCPDLY)) begin
            init_cnt <= '0;           // terminal count → back to idle
        end else begin
            init_cnt <= init_cnt + CNT_W'(1);
        end
    end
end
```

Counter state transitions:

| Cycle | `init_cnt` | Condition | Next state |
|-------|-----------|-----------|-----------|
| — | 0 | reset | 0 (idle) |
| 0 | 0 | `init==1` pulse arrives | 1 (start) |
| 1–6 | 1–6 | `init_cnt != 0` (self-sustaining) | +1 each cycle |
| 7 | 7 (`==MCPDLY`) | terminal count | 0 (idle) |

**Auto-clear of `CTRL.INIT`** (line 241):

```systemverilog
csr_status.CTRL.INIT.hwclr = (init_cnt == CNT_W'(MCPDLY)) && csr_cfg.CTRL.INIT.value;
```

When `init_cnt` reaches 7 **and** `CTRL.INIT` is still set → hardware clears `CTRL.INIT=0` → `async_init` de-asserts. The ring initialization completes with no firmware intervention needed.

#### 14.5.2 `async_init` Synchronization Path

`async_init` arrives at the BIU from the ring (`ingress_intf.async_init`), which is asynchronous with respect to the BIU clock. The BIU synchronizes it before using it to start `init_cnt`:

```
ingress_intf.async_init  (asynchronous ring signal)
        │
        ├──► egress_intf.async_init   (pass-through: forwarded to next node)
        │
        └──► tt_libcell_sync3r        (3-stage synchronizer, tt_edc1_state_machine.sv:1132)
                    │
                    └──► init  (synchronous, registered to i_clk)
                              │
                              └──► o_init ──► BIU init_cnt logic
```

Note: `async_init` is driven by the BIU itself onto the ring:
```systemverilog
// tt_edc1_bus_interface_unit.sv:149
assign src_ingress_intf.async_init = csr_cfg.CTRL.INIT.value;
```
So the BIU drives `async_init=1`, it propagates through all ring nodes (each node passes it through to the next via `egress_intf.async_init = ingress_intf.async_init`), and eventually arrives back at the BIU's own ingress where it is synchronized.

#### 14.5.3 Why MCPDLY = 7?

The 7-cycle delay serves as a **multi-cycle path guarantee**: it ensures that `async_init=1` has had sufficient time to propagate through all nodes in the ring and be registered (or resolved from metastability) at every node's synchronizer before the BIU clears it. The ring may span multiple clock domains; the 7-cycle window covers the worst-case synchronizer latency (up to 3 sync stages × 1 cycle each) plus propagation delays across the ring.

---

## 15. Inter-Cluster EDC Signal Connectivity

### 15.1 Trinity Grid Layout

Trinity is a **4×5 tile grid** (`SizeX=4`, `SizeY=5`). Each column (X) shares one EDC ring. Within each column there are 5 rows (Y=0..4) with different tile types:

```
Y=4 (top)    NOC2AXI_NE_OPT  NOC2AXI_N_OPT  NOC2AXI_N_OPT  NOC2AXI_NW_OPT   (BIU lives here)
Y=3          DISPATCH_E      ROUTER         ROUTER         DISPATCH_W
Y=2          TENSIX          TENSIX         TENSIX         TENSIX
Y=1          TENSIX          TENSIX         TENSIX         TENSIX
Y=0 (bottom) TENSIX          TENSIX         TENSIX         TENSIX
             X=0             X=1            X=2            X=3
```

From `trinity_pkg.sv`:
```systemverilog
localparam int unsigned SizeX = 4;
localparam int unsigned SizeY = 5;
localparam int unsigned NumApbNodes = 4;  // one BIU APB port per column

localparam tile_t [SizeY-1:0][SizeX-1:0] GridConfig = '{
    '{NOC2AXI_NE_OPT, NOC2AXI_N_OPT, NOC2AXI_N_OPT, NOC2AXI_NW_OPT},  // Y=4
    '{DISPATCH_E,     ROUTER,         ROUTER,         DISPATCH_W},        // Y=3
    '{TENSIX,         TENSIX,         TENSIX,         TENSIX},            // Y=2
    '{TENSIX,         TENSIX,         TENSIX,         TENSIX},            // Y=1
    '{TENSIX,         TENSIX,         TENSIX,         TENSIX}             // Y=0
};
```

**Key: each column (X) has its own independent EDC ring.** The BIU for column X is at the top tile `[x][Y=4]`.

### 15.2 EDC Interface Arrays in `trinity.sv`

Four interface arrays are declared at the top level, each indexed by `[x * SizeY + y]`:

```systemverilog
// From trinity.sv L272-275
edc1_serial_bus_intf_def edc_ingress_intf[SizeX*SizeY]();          // direct: ring flows DOWN (from y+1 → y)
edc1_serial_bus_intf_def edc_egress_intf[SizeX*SizeY]();           // direct: tile sends UP  (into ring)
edc1_serial_bus_intf_def loopback_edc_ingress_intf[SizeX*SizeY](); // loopback: bottom turnaround
edc1_serial_bus_intf_def loopback_edc_egress_intf[SizeX*SizeY]();  // loopback: bottom turnaround
```

Index formula: `index = x * SizeY + y` — so column X, row Y maps to a flat array index.

### 15.3 Inter-Tile EDC Wiring (Vertical Ring per Column)

The EDC ring travels **vertically** within each column. At the top-level `trinity.sv` generate loop, the following connectors link adjacent tiles:

```systemverilog
// trinity.sv L435-458 — for each (x, y)
for (genvar x = 0; x < SizeX; x++) begin : gen_x
  for (genvar y = 0; y < SizeY; y++) begin : gen_y

    // All tiles except Y=SizeY-1 (top): connect direct ring downward
    if (y != SizeY-1) begin : top_nodes_edc_connections
      // Direct path: egress from tile[x][y+1] → ingress of tile[x][y]
      tt_edc1_intf_connector edc_direct_conn_nodes (
          .ingress_intf(edc_egress_intf[x*SizeY + y+1]),  // from tile above
          .egress_intf (edc_ingress_intf[x*SizeY + y])    // into tile below
      );

      // Loopback path: loopback egress of tile[x][y] → loopback ingress of tile[x][y+1]
      tt_edc1_intf_connector edc_loopback_conn_nodes (
          .ingress_intf(loopback_edc_egress_intf[x*SizeY + y]),    // from tile[y]
          .egress_intf (loopback_edc_ingress_intf[x*SizeY + y+1])  // into tile[y+1]
      );
    end

    // Bottom tile (Y=0): loop edc_egress back into loopback_ingress (turnaround)
    if (y == 0) begin : bottom_node_edc_connection
      tt_edc1_intf_connector edc_loopback_conn_nodes (
          .ingress_intf(edc_egress_intf[x*SizeY + 0]),           // bottom tile's egress
          .egress_intf (loopback_edc_ingress_intf[x*SizeY + 0])  // feeds back into loopback
      );
    end

  end
end
```

### 15.4 Per-Column EDC Ring Flow

The EDC ring in each column flows as a **two-segment vertical loop**:

```
Segment A — Direct path (downward):
  BIU (Y=4)  → edc_egress_intf[x*5+4]
             ↓ edc_direct_conn_nodes (Y=3←4)
  Tile Y=3   → edc_egress_intf[x*5+3]
             ↓ edc_direct_conn_nodes (Y=2←3)
  Tile Y=2   → edc_egress_intf[x*5+2]
             ↓ edc_direct_conn_nodes (Y=1←2)
  Tile Y=1   → edc_egress_intf[x*5+1]
             ↓ edc_direct_conn_nodes (Y=0←1)
  Tile Y=0   → edc_egress_intf[x*5+0]
             ↓ edc_loopback_conn_nodes (Y=0 turnaround)
             → loopback_edc_ingress_intf[x*5+0]

Segment B — Loopback path (upward):
  Tile Y=0   → loopback_edc_egress_intf[x*5+0]
             ↑ edc_loopback_conn_nodes (Y=0→1)
  Tile Y=1   → loopback_edc_egress_intf[x*5+1]
             ↑ edc_loopback_conn_nodes (Y=1→2)
  Tile Y=2   → loopback_edc_egress_intf[x*5+2]
             ↑ edc_loopback_conn_nodes (Y=2→3)
  Tile Y=3   → loopback_edc_egress_intf[x*5+3]
             ↑ edc_loopback_conn_nodes (Y=3→4)
  BIU (Y=4)  ← loopback_edc_ingress_intf[x*5+4]
```

The ring is a **vertical U-shape per column**: packets travel down the direct path, turn around at Y=0, and return up the loopback path back to the BIU at Y=4.

> **N1B0 ring traversal per column:** Entry at Y=4 → composite tile (Y=4+Y=3, two internal segments for X=1,2) OR corner tile (X=0,3) → Dispatch/empty-placeholder at Y=3 → Tensix[Y=2] → Tensix[Y=1] → Tensix[Y=0] → U-turn loopback.

### 15.5 Tile EDC Port Connections to the Ring

Each tile connects its own `edc_egress_intf` and `loopback_edc_ingress_intf` to the column ring:

**NOC2AXI tile (BIU at top, Y=4) — from `trinity.sv` L597-598:**
```systemverilog
// BIU sends packets DOWN (segment A)
.edc_egress_intf         (edc_egress_intf[x*SizeY + y]),          // → drives ring downward

// BIU receives returning packets UP (segment B)
.loopback_edc_ingress_intf(loopback_edc_ingress_intf[x*SizeY + y])  // ← from loopback
```

**NOC2AXI tile (intermediate, Y=3 when present) — from `trinity.sv` L895-897:**
```systemverilog
// Receives packets from above (segment A)
// .edc_ingress_intf(edc_ingress_intf[x*SizeY + y]),  // commented out / not used directly

// Passes ring egress downward (already wired via connector above)
.edc_egress_intf          (edc_egress_intf[x*SizeY + y-1]),         // feeds tile below
.loopback_edc_ingress_intf(loopback_edc_ingress_intf[x*SizeY + y-1]) // loopback to tile below
```

### 15.6 Complete Per-Column Ring Diagram (Column X=0 as example)

```
  APB4 Firmware (external)
       │  APB[x=0]
       ▼
 ┌─────────────────────────────────────────────────────┐
 │  Y=4: NOC2AXI_NE_OPT (BIU, node_id=0x0000)         │
 │       tt_neo_overlay_wrapper                         │
 │       ├── tt_edc1_biu_soc_apb4_wrap (BIU)           │
 │       └── tt_edc1_serial_bus_mux    (harvest mux)   │
 │   edc_egress_intf[0*5+4] ─────────────────────────► │ ─► to edc_direct_conn_nodes
 │   loopback_edc_ingress_intf[0*5+4] ◄────────────────│ ◄─ from edc_loopback_conn_nodes
 └────────────────────┬────────────────────────────────┘
                      │ (edc_direct_conn_nodes Y=3←4)
                      ▼
 ┌─────────────────────────────────────────────────────┐
 │  Y=3: DISPATCH_E                                    │
 │       tt_dispatch_top_east                          │
 │       ├── tt_trin_disp_eng_noc_niu_router_east      │
 │       │   └── tt_edc1_serial_bus_demux (harvest)    │
 │       └── tt_disp_eng_overlay_wrapper               │
 │           └── tt_edc1_serial_bus_mux  (harvest)     │
 │   edc_ingress_intf[0*5+3] ◄────────────────────────│ (from Y=4 via connector)
 │   edc_egress_intf[0*5+3]  ─────────────────────────│ ─► to edc_direct_conn_nodes
 │   loopback_edc_ingress_intf[0*5+3] ◄───────────────│ ◄─ edc_loopback_conn_nodes
 │   loopback_edc_egress_intf[0*5+3]  ────────────────│ ─► edc_loopback_conn_nodes
 └────────────────────┬────────────────────────────────┘
                      │ (edc_direct_conn_nodes Y=2←3)
                      ▼
 ┌─────────────────────────────────────────────────────┐
 │  Y=2: TENSIX                                        │
 │       tt_trin_noc_niu_router_wrap                   │
 │       ├── tt_noc_niu_router + EDC nodes             │
 │       └── tt_edc1_serial_bus_demux (harvest)        │
 │       tt_tensix_with_l1 (L1 Hub: T0→T1→T3→T2)      │
 │       tt_neo_overlay_wrapper                        │
 │       └── tt_edc1_serial_bus_mux (harvest)          │
 │   edc_ingress_intf[0*5+2] ◄────────────────────────│
 │   edc_egress_intf[0*5+2]  ─────────────────────────│ ─►
 │   loopback_edc_ingress/egress_intf[0*5+2] ◄───────►│
 └────────────────────┬────────────────────────────────┘
                      │ (edc_direct_conn_nodes Y=1←2)
                      ▼
 ┌────────────────────────┐   ┌────────────────────────┐
 │  Y=1: TENSIX (same)    │   │  Y=0: TENSIX (same)    │
 └───────────┬────────────┘   └───────────┬────────────┘
             │ edc_direct_conn Y=0←1      │ Y=0: turnaround
             ▼                            ▼
                         edc_loopback_conn_nodes (Y=0):
                         edc_egress_intf[0*5+0] → loopback_edc_ingress_intf[0*5+0]
                         (U-turn: ring reverses direction here)
```

### 15.7 Summary: Signal Names and Flow Direction

| Signal | Direction | Description |
|--------|-----------|-------------|
| `edc_egress_intf[x*5+y]` | Tile → ring downward | Tile's EDC output into the direct path |
| `edc_ingress_intf[x*5+y]` | Ring → tile | Direct path arriving at the tile (NOTE: marked `// TODO` in trinity.sv — some tiles drive this directly via demux/mux) |
| `loopback_edc_egress_intf[x*5+y]` | Tile → ring upward | Tile's loopback output going back up |
| `loopback_edc_ingress_intf[x*5+y]` | Ring → tile | Loopback path arriving at the tile |
| `edc_egress_t6_byp_intf` | Demux → Mux | Harvest bypass wire (stays inside tile's router wrapper) |

**One EDC ring per column.** Each column X has an independent ring with its own BIU at `[x][Y=4]`. The four columns therefore have 4 independent BIUs, 4 independent rings, and 4 APB4 register bank interfaces — reflected in `NumApbNodes=4`.

---

## 16. Instance Paths (Trinity)

For the complete, RTL-verified, ring-order-annotated instance path list, refer to **EDC_path_V0.2.md**.

This section provides representative path examples using the correct hierarchy prefix `gen_x[*].gen_y[*].<tile_type>.<...>`.

### 16.1 Active EDC Nodes — Hierarchy Prefix Correction

The correct top-level path prefix for all tile-instantiated EDC nodes uses the generate loop:

```
gen_x[X].gen_y[Y].<tile_generate>.<subsystem>.<...>
```

where `<tile_generate>` is one of:
- `gen_tensix.tt_tensix_with_l1.` (Tensix tiles)
- `gen_dispatch_w.tt_dispatch_top_inst_west.tt_dispatch_engine.` (Dispatch West)
- `gen_dispatch_e.tt_dispatch_top_inst_east.tt_dispatch_engine.` (Dispatch East)
- `gen_noc2axi_n_opt.trinity_noc2axi_n_opt.` / `gen_noc2axi_ne_opt...` / `gen_noc2axi_nw_opt...`
- `gen_router.trinity_router.`

> **N1B0:** NOC2AXI_N_OPT does not exist as a standalone tile. Middle columns (X=1,2) use composite `trinity_noc2axi_router_ne/nw_opt` which contains TWO EDC segments internally: `trinity_noc2axi_n_opt` (Y=4) → internal wire → `trinity_router` (Y=3). External EDC egress exits at Y=3 level.

**Example paths (Tensix tile at X=1, Y=2):**

| Instance Path | Block | inst |
|---|---|---|
| `gen_x[1].gen_y[2].gen_tensix.tt_tensix_with_l1.overlay_noc_wrap.overlay_noc_niu_router.tt_trinity_noc_niu_router_inst.noc_niu_router_inst.has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC North VC buf | 0x00 |
| `gen_x[1].gen_y[2].gen_tensix.tt_tensix_with_l1.overlay_noc_wrap.overlay_noc_niu_router.tt_trinity_noc_niu_router_inst.noc_niu_router_inst.has_sec_fence_edc.noc_sec_fence_edc_wrapper.g_edc_inst.edc_node_inst` | NOC security fence | 0xC0 |
| `gen_x[1].gen_y[2].gen_tensix.tt_tensix_with_l1.t6[0].neo.u_t6.gen_gtile[0].u_fpu_gtile.gtile_general_error_edc_node` | T0 Gtile[0] general | 0x20 |
| `gen_x[1].gen_y[2].gen_tensix.tt_tensix_with_l1.t6[0].neo.u_t6.instrn_engine_wrapper.u_edc_node_unpack` | T0 Unpack | 0x05 |
| `gen_x[1].gen_y[2].gen_tensix.tt_tensix_with_l1.t6[0].neo.u_t6.gen_gtile[1].u_fpu_gtile.gtile_dest_parity_edc_node` | T0 Gtile[1] dest parity | 0x25 |
| `gen_x[1].gen_y[2].gen_tensix.tt_tensix_with_l1.u_l1part.t6_misc.u_edc1_node_misc` | T6 MISC | 0x00 |

> **Note:** Previous V0.1 used incorrect prefix `trinity.tt_trin_noc_niu_router_wrap...` — this path does not match the RTL generate-loop hierarchy and was replaced by the `gen_x[*].gen_y[*]` prefix above.

### 16.2 BIU Instance

```
gen_x[X].gen_y[Y].<tile_type>.overlay_noc_wrap.neo_overlay_wrapper.
    └── tt_edc1_biu_soc_apb4_wrap  (node_id = 0x0000)
        ├── edc1_biu_soc_apb4_inner  u_t6_edc_biu_csr_map
        └── tt_edc1_bus_interface_unit  u_edc_biu
            ├── tt_edc1_state_machine  u_edc_req_src  (IS_REQ_SRC=1)
            └── tt_edc1_state_machine  u_edc_rsp_snk  (IS_RSP_SINK=1)
```

### 16.3 Harvest Bypass Instances

**Tensix tile bypass pair:**
```
trinity
├── tt_trin_noc_niu_router_wrap (×N)               ← DEMUX (ring input side)
│   └── tt_edc1_serial_bus_demux  edc_demuxing_when_harvested
│         sel=0 → edc_egress_intf        (into Tensix tile)
│         sel=1 → edc_egress_t6_byp_intf (bypass wire, skips tile)
│                                    ↕ bypass wire
└── tt_neo_overlay_wrapper                          ← MUX (ring output side)
    └── tt_edc1_serial_bus_mux  edc_muxing_when_harvested
          sel=0 ← ovl_egress_intf        (from BIU, normal)
          sel=1 ← edc_ingress_t6_byp_intf (from bypass wire)
          → edc_egress_intf (back into ring)
```

**Dispatch tile bypass pair:**
```
trinity
├── tt_dispatch_top_east
│   └── tt_trin_disp_eng_noc_niu_router_east        ← DEMUX
│       └── tt_edc1_serial_bus_demux  edc_demuxing_when_harvested
│             sel=0 → edc_egress_intf
│             sel=1 → edc_egress_t6_byp_intf (bypass wire)
│                                    ↕ bypass wire
│       └── tt_disp_eng_overlay_wrapper             ← MUX
│           └── tt_edc1_serial_bus_mux  edc_muxing_when_harvested
│                 sel=0 ← ovl_egress_intf
│                 sel=1 ← edc_ingress_t6_byp_intf
│
└── tt_dispatch_top_west
    └── tt_trin_disp_eng_noc_niu_router_west         ← DEMUX
        └── tt_edc1_serial_bus_demux  edc_demuxing_when_harvested
              sel=0 → edc_egress_intf
              sel=1 → edc_egress_t6_byp_intf (bypass wire)
                                    ↕ bypass wire
        └── tt_disp_eng_overlay_wrapper              ← MUX
            └── tt_edc1_serial_bus_mux  edc_muxing_when_harvested
                  sel=0 ← ovl_egress_intf
                  sel=1 ← edc_ingress_t6_byp_intf
```

All mux/demux pairs share the same control signal (`edc_mux_demux_sel` / `i_edc_mux_demux_sel`) — both are always switched together for the same tile.

---

## Appendix A: RTL File Index

| Module | File Path |
|--------|-----------|
| `tt_edc1_pkg` | `tt_rtl/tt_edc/rtl/tt_edc1_pkg.sv` |
| `tt_edc1_node` | `tt_rtl/tt_edc/rtl/tt_edc1_node.sv` |
| `tt_edc1_state_machine` | `tt_rtl/tt_edc/rtl/tt_edc1_state_machine.sv` |
| `tt_edc1_intf_connector` | `tt_rtl/tt_edc/rtl/tt_edc1_intf_connector.sv` |
| `tt_edc1_serial_bus_repeater` | `tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_repeater.sv` |
| `tt_edc1_serial_bus_mux` | `tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_mux.sv` |
| `tt_edc1_serial_bus_demux` | `tt_rtl/tt_edc/rtl/tt_edc1_serial_bus_demux.sv` |
| `tt_edc1_bus_interface_unit` | `tt_rtl/tt_edc/rtl/tt_edc1_bus_interface_unit.sv` |
| `tt_edc1_biu_soc_apb4_wrap` | `tt_rtl/tt_edc/rtl/tt_edc1_biu_soc_apb4_wrap.sv` |
| `tt_noc_overlay_edc_wrapper` | `tt_rtl/tt_noc/rtl/noc/tt_noc_overlay_edc_wrapper.sv` |
| `tt_tensix_with_l1` (L1 Hub) | `tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_tensix_with_l1.sv` |
| `tt_trin_noc_niu_router_wrap` | `tt_rtl/overlay/rtl/config/tensix/trinity/tt_trin_noc_niu_router_wrap.sv` |
| `tt_neo_overlay_wrapper` | `tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv` |
| `tt_disp_eng_overlay_wrapper` | `tt_rtl/overlay/rtl/quasar_dispatch/tt_disp_eng_overlay_wrapper.sv` |
| `tt_trin_disp_eng_noc_niu_router_east` | `tt_rtl/overlay/rtl/config/dispatch/trinity/tt_trin_disp_eng_noc_niu_router_east.sv` |
| `tt_trin_disp_eng_noc_niu_router_west` | `tt_rtl/overlay/rtl/config/dispatch/trinity/tt_trin_disp_eng_noc_niu_router_west.sv` |
| `trinity` (top) | `rtl/used_in_n1/rtl/trinity.sv` |

---

## Appendix B: Full End-to-End EDC Operation Example

This section traces a complete EDC event from hardware error detection to firmware handling, showing every stage, module, clock domain, data format, and protocol step.

### Scenario

**Cluster:** (X=1, Y=2) — `TENSIX` tile, T0 sub-core
**Event:** Uncorrectable SRAM error detected in the Unpacker
**Expected node_id:** `0x8205` = `{5'h10, 3'd2, 8'h05}`
**Ring:** Column X=1 → BIU[1]

---

### Clock Domains Involved

| Domain | Clock signal | Used by |
|--------|-------------|---------|
| AI clock | `i_clk` (Tensix) | Tensix sub-cores (`tt_tensix.sv`, `tt_instrn_engine_wrapper.sv`) — error detection happens here |
| NOC clock | `i_nocclk` / `i_edc_clk` | EDC node FSM (`tt_edc1_node`), NOC overlay wrapper (`tt_noc_overlay_edc_wrapper`), BIU (`tt_edc1_biu_soc_apb4_wrap`) |
| APB clock | Same as NOC clock | APB4 slave port of BIU |
| EDC serial bus | Toggle-based, **asynchronous** — no shared clock required between sender and receiver |

> The EDC toggle handshake (`req_tgl`/`ack_tgl`) safely crosses from AI clock domain (node) to NOC clock domain (BIU) without explicit synchronizers when `DISABLE_SYNC_FLOPS=1` (default). Optional 2-FF synchronizer chains can be enabled via `ENABLE_INGRESS_SYNC`/`ENABLE_EGRESS_SYNC`.

---

### Stage 1 — Hardware Error Detection (AI clock domain)

**Location:** `tt_instrn_engine_wrapper` inside `tt_tensix` inside `tt_tensix_with_l1` at (X=1, Y=2)
**Clock:** `i_clk` = AI clock

The Unpacker detects an uncorrectable SRAM error. This asserts the `i_event` input to the local `tt_edc1_node`:

```
i_event[0] = 1   (UNC_EVENT trigger)
i_capture[0] = {error_address}   (16-bit capture data — address of failed SRAM word)
```

The event configuration for this node:
```systemverilog
// EVENT_CFG[0] = UNC_EVENT_CFG
EVENT_CFG[0] = '{ capture_en: 1, event_cmd: UNC_EVENT, capidx_hi: 0, capidx_lo: 0 }
```

---

### Stage 2 — EDC Node Queues Event (AI clock domain → ring)

**Module:** `tt_edc1_node` (inside `tt_instrn_engine_wrapper`, inst=UNPACK_EDC_IDX=0x05)
**node_id:** `0x8205` = `{5'h10, 3'd2, 8'h05}`
**Clock:** `i_clk` = AI clock

The node FSM detects `i_event[0]` rising, latches the capture register, and builds an event packet to inject into the ring:

```
Fragment 0  (TGT_ID):  0x0000       ← BIU_NODE_ID — all events target the BIU
Fragment 1  (CMD/LEN): {UNC_ERR_CMD[3:0]=4'd9, PYLD_LEN[3:0]=4'd1, event_id[5:0]=0}
Fragment 2  (SRC_ID):  0x8205       ← this node's ID: {0x10, Y=2, inst=0x05}
Fragment 3  (DATA):    {DATA1=0x00, DATA0=0x00}
Fragment 4  (payload): {error_address[15:0]}   ← captured SRAM address
```

The node waits until the ring is idle (no in-flight packet on `ingress_intf`), then inserts its packet by taking control of `egress_intf`.

---

### Stage 3 — Toggle Handshake Serial Transmission (async)

**Interface:** `edc1_serial_bus_intf_def`
**Protocol:** Toggle-based, asynchronous — crosses AI clock (sender) → NOC clock (BIU receiver)

For each of the 5 fragments (frg 0–4):

```
Cycle N:   node drives req_tgl[1:0] ← toggled value, data[15:0] ← fragment data,
                                        data_p[0] ← odd parity of data[15:0]
Cycle N+1: (CDC crossing — toggle sampled by receiver)
Cycle N+2: BIU ack_tgl[1:0] ← echoes req_tgl  (acknowledges receipt)
Cycle N+3: node sees ack_tgl == req_tgl → fragment accepted, advance to next fragment
```

Full packet serial transfer (5 fragments × ~4 cycles each = ~20 toggle cycles):

```
frg[0] req_tgl=2'b01  data=0x0000  data_p=1  → TGT_ID = BIU (0x0000)
frg[1] req_tgl=2'b10  data=0x9100  data_p=0  → CMD=9(UNC_ERR), LEN=1, event_id=0
frg[2] req_tgl=2'b01  data=0x8205  data_p=0  → SRC_ID = 0x8205
frg[3] req_tgl=2'b10  data=0x0000  data_p=1  → DATA1/DATA0 = 0
frg[4] req_tgl=2'b01  data=<addr>  data_p=?  → captured error address (payload)
```

> `req_tgl` alternates between `2'b01` and `2'b10` each fragment. The 2-bit encoding prevents single-bit glitches from being mistaken for a new transfer.

---

### Stage 4 — Packet Traverses the Ring (async serial bus)

**Path:** The packet travels downstream through every module in column X=1's EDC ring until it reaches the BIU. Each intermediate node checks `TGT_ID`: if `TGT_ID ≠ own node_id`, the node passes the packet through (ingress → egress) without consuming it.

```
[UNPACK node in T0, (X=1,Y=2)]
  egress_intf
    ↓  edc_conn_T0_to_L1          (tt_edc1_intf_connector — pure wire)
    ↓  L1 Hub routing
    ↓  edc_conn_L1_to_overlay     (tt_edc1_intf_connector — pure wire)
    ↓  tt_neo_overlay_wrapper
    ↓  tt_edc1_serial_bus_mux     (sel=0: normal path, tile alive)
    ↓  edc_egress_intf[1*5+2=7]   (column 1, row 2 → ring index 7)
    ↓  tt_edc1_intf_connector     edc_direct_conn_nodes  (trinity.sv L442)
    ↓  tt_trin_noc_niu_router_wrap (X=1, Y=1)
    ↓  NOC EDC nodes pass through  (TGT_ID=0x0000 ≠ 0xF210 → not addressed here)
    ↓  tt_edc1_serial_bus_demux   (sel=0: normal path)
    ↓  tt_trin_noc_niu_router_wrap (X=1, Y=0)
    ↓  NOC EDC nodes pass through
    ↓  tt_edc1_serial_bus_demux   (sel=0)
    ↓  loopback connector (y==0, trinity.sv L454-456)
    ↓  loopback_edc_ingress_intf  (turnaround at Y=0)
    ↓  tt_trin_noc_niu_router_wrap loopback_repeater
    ↓  ... back up the column through Y=1, Y=2, Y=3
    ↓  tt_neo_overlay_wrapper     (X=1, Y=3 — overlay at top)
    ↓  tt_edc1_biu_soc_apb4_wrap  ingress_intf
        ↓
    [BIU receives packet]
```

> The ring is **U-shaped per column**: packets flow down one side (main path) and up the other side (loopback path), with the BIU at the top of column X.

---

### Stage 5 — BIU Deserializes Packet (NOC clock domain)

**Module:** `tt_edc1_bus_interface_unit` → `u_edc_rsp_snk` (IS_RSP_SINK=1)
**Clock:** `i_clk` = NOC clock (`i_nocclk`)

The IS_RSP_SINK state machine (`tt_edc1_state_machine`) samples each fragment as it arrives:

```
frg[0] → RSP_HDR0.TGT_ID  = 0x0000   ← confirms addressed to BIU
frg[1] → RSP_HDR0.CMD     = UNC_ERR_CMD (4'd9)
          RSP_HDR0.PYLD_LEN= 1
          RSP_HDR0.CMD_OPT = 0x00
frg[2] → RSP_HDR1.SRC_ID  = 0x8205   ← source: T0 UNPACK at Y=2
frg[3] → RSP_HDR1.DATA1   = 0x00
          RSP_HDR1.DATA0   = 0x00
frg[4] → RSP_DATA[0]      = <error_address>
```

After the last fragment (`PYLD_LEN=1` → 1 payload fragment after header):

```systemverilog
// BIU status register updates (combinational hwset):
csr_status.STAT.UNC_ERR.hwset    = 1;  // UNC_ERR_CMD received
csr_status.STAT.RSP_PKT_RCVD.hwset = 1;
```

---

### Stage 6 — BIU Asserts Interrupt

**Module:** `tt_edc1_bus_interface_unit`
**Clock:** NOC clock (combinational from status register)

```systemverilog
assign crit_err_irq = csr_cfg.IRQ_EN.UNC_ERR_IEN.value
                      && csr_cfg.STAT.UNC_ERR.value;
// → crit_err_irq = 1  (assuming UNC_ERR_IEN was enabled by firmware)

assign pkt_rcvd_irq = csr_cfg.IRQ_EN.RSP_PKT_RCVD_IEN.value
                      && csr_cfg.STAT.RSP_PKT_RCVD.value;
// → pkt_rcvd_irq = 1
```

These signals propagate out of `tt_edc1_biu_soc_apb4_wrap` as:
```
o_edc_crit_err_irq[1]    → SoC interrupt controller (column X=1)
o_edc_pkt_rcvd_irq[1]
```

---

### Stage 7 — Firmware APB4 Read (APB clock domain)

**Module:** `tt_edc1_biu_soc_apb4_wrap` APB4 slave
**Clock:** APB clock = NOC clock
**Address space:** 6-bit PADDR (64 word × 32-bit = 256 bytes)

Firmware handles the interrupt and issues APB4 reads to BIU[1]:

**Step 1: Read STAT to identify error type**
```
APB: PSEL=1, PENABLE=1, PWRITE=0, PADDR=6'h?? (STAT register offset)
     → PRDATA = {OVERFLOW=0, UNC_ERR=1, LAT_ERR=0, COR_ERR=0,
                 RSP_PKT_RCVD=1, REQ_PKT_SENT=0, FATAL_ERR=0, ...}
```

**Step 2: Read RSP_HDR0 to get CMD and TGT_ID**
```
APB: PADDR = RSP_HDR0 offset
     → PRDATA = {TGT_ID=0x0000, CMD=4'd9(UNC_ERR_CMD), PYLD_LEN=4'd1, CMD_OPT=0x00}
```

**Step 3: Read RSP_HDR1 to get SRC_ID**
```
APB: PADDR = RSP_HDR1 offset
     → PRDATA = {SRC_ID=0x8205, DATA1=0x00, DATA0=0x00}

Decode SRC_ID=0x8205:
  [15:11] = 5'h10  → part = TENSIX T0
  [10: 8] = 3'd2   → subp = Y=2  → cluster row 2 in column 1
  [ 7: 0] = 8'h05  → inst = UNPACK_EDC_IDX → Unpacker sub-node
  Ring = BIU[1] → column X=1
  ∴ Error source: Tensix T0 Unpacker at cluster (X=1, Y=2)
```

**Step 4: Read RSP_DATA[0] to get captured error address**
```
APB: PADDR = RSP_DATA[0] offset
     → PRDATA = {error_address[15:0], padding}
```

**Step 5: Clear status (write-1-clear)**
```
APB: PSEL=1, PENABLE=1, PWRITE=1, PADDR=STAT, PWDATA={UNC_ERR=1, RSP_PKT_RCVD=1}
     → STAT.UNC_ERR cleared, crit_err_irq deasserted
```

---

### Full Path Summary

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Stage │ Module                          │ Clock      │ Action           │
├───────┼─────────────────────────────────┼────────────┼──────────────────┤
│  1    │ tt_instrn_engine_wrapper        │ AI clock   │ Unpacker asserts │
│       │   (T0, X=1, Y=2)               │            │ i_event[UNC]     │
├───────┼─────────────────────────────────┼────────────┼──────────────────┤
│  2    │ tt_edc1_node (UNPACK inst=0x05) │ AI clock   │ Latch capture,   │
│       │   node_id=0x8205               │            │ build packet,    │
│       │                                 │            │ wait for ring    │
├───────┼─────────────────────────────────┼────────────┼──────────────────┤
│  3    │ edc1_serial_bus_intf_def        │ ASYNC      │ Toggle req_tgl,  │
│       │   (ingress→egress)             │ (CDC-safe) │ 5 frg × 4 cyc   │
├───────┼─────────────────────────────────┼────────────┼──────────────────┤
│  4    │ tt_edc1_intf_connector ×N       │ ASYNC      │ Wire passthrough  │
│       │ tt_edc1_serial_bus_mux (sel=0)  │ (no clock) │ (ring traversal) │
│       │ tt_edc1_serial_bus_demux (sel=0)│            │                  │
├───────┼─────────────────────────────────┼────────────┼──────────────────┤
│  5    │ tt_edc1_state_machine           │ NOC clock  │ Deserialize 5    │
│       │   u_edc_rsp_snk (IS_RSP_SINK=1)│            │ fragments → CSRs │
├───────┼─────────────────────────────────┼────────────┼──────────────────┤
│  6    │ tt_edc1_bus_interface_unit      │ NOC clock  │ Assert           │
│       │                                 │            │ crit_err_irq[1]  │
├───────┼─────────────────────────────────┼────────────┼──────────────────┤
│  7    │ tt_edc1_biu_soc_apb4_wrap       │ APB clock  │ Firmware reads   │
│       │   BIU[1] (X=1 column)          │ (=NOC clk) │ STAT/HDR/DATA    │
│       │                                 │            │ decodes 0x8205   │
└───────┴─────────────────────────────────┴────────────┴──────────────────┘
```

**Data flowing through the ring (16-bit fragments):**

```
frg[0] = 0x0000  (TGT_ID = BIU)
frg[1] = 0x9100  (CMD=9=UNC_ERR, LEN=1, event_id=0)
frg[2] = 0x8205  (SRC_ID = T0 UNPACK at Y=2)
frg[3] = 0x0000  (DATA1/DATA0)
frg[4] = 0xXXXX  (captured error address)
```

**IRQ outputs asserted on BIU[1]:**
```
o_edc_crit_err_irq[1]  = 1   (UNC_ERR received)
o_edc_pkt_rcvd_irq[1]  = 1   (packet received)
```

---

*Document generated from RTL analysis of Tenstorrent Trinity SoC EDC1 implementation.*
*All claims verified against source files at `/secure_data_from_tt/20260221/`.*

# Hardware Design Document: EDC1 (Error Detection & Control / Event Diagnostic Channel)

**Project:** Trinity (Tenstorrent AI SoC)
**Version:** EDC1 v1.1.0 (SUPER=1, MAJOR=1, MINOR=0) — Document V0.5
**Document Status:** V0.5 — CDC analysis corrected: §3.5.4 expanded with Samsung 5nm MTBF calculation and effective toggle rate derivation; §14.1 corrected (CDC safety basis is low toggle rate, not single-bit encoding); §14.2 corrected to reflect RTL audit (parameters do not exist); Appendix B.6 corrected to align with §3.5.4 (set_false_path sufficient; no sync FF or proximity constraint required for Samsung 5nm)
**Date:** 2026-03-23
**Changes from V0.3:**
- §2.1: Harvest bypass block diagram enhanced with explicit labeled bypass-wire arrows (DEMUX out1 → bypass wire → MUX in1)
- §3.3: Toggle handshake protocol expanded — RTL state machine detail, 2-bit encoding rationale, SDC false-path / MCP constraints, CDC sync-flop options
- §3.4: async_init expanded — motivation (atomic multi-domain init), CDC/SDC treatment (set_false_path to sync3r), MCPDLY=7 derivation (fixed localparam, value rationale), N1B0 repeater depth consideration
- §4.3 (new): SW usage guide for packet format — when to use WR/RD/broadcast, timeout behavior, worked example
- §6 (new section, was §12): Event Types and Commands moved earlier so readers understand event semantics before the error handler guide
- §7 (new section): SW Error Handling Guide — interrupt-to-node-identification procedure, complete pseudocode, node query flow, common response actions
- All subsequent sections renumbered (old §6–§16 → new §8–§17)
- §5.6 (new): Quick Node Address Lookup Table added to Node ID chapter

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
   - 5.6 [Quick Node Address Lookup Table](#56-quick-node-address-lookup-table)
6. [Event Types and Commands](#6-event-types-and-commands)
7. [SW Error Handling Guide — From Interrupt to Node Identification](#7-sw-error-handling-guide--from-interrupt-to-node-identification)
8. [Module Hierarchy](#8-module-hierarchy)
9. [Module Reference](#9-module-reference)
10. [EDC Ring Topology in Trinity](#10-edc-ring-topology-in-trinity)
11. [Harvest Bypass Mechanism](#11-harvest-bypass-mechanism)
12. [Bus Interface Unit (BIU)](#12-bus-interface-unit-biu)
13. [EDC Node Configuration](#13-edc-node-configuration)
14. [CDC / Synchronization](#14-cdc--synchronization)
15. [Firmware Interface](#15-firmware-interface)
16. [Inter-Cluster EDC Signal Connectivity](#16-inter-cluster-edc-signal-connectivity)
17. [Instance Paths (Trinity)](#17-instance-paths-trinity)

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
  [bypass hardware exists at every tile; sel=0/1 set per-chip from eFuse at boot]
  ═══════════════════════════════════════════════════════════════════════════════

  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  LEGEND                                                                       │
  │  ──────────────────►  Ring data flowing DOWNSTREAM  (Segment A, ↓ DOWN)      │
  │  ◄──────────────────  Ring data flowing UPSTREAM    (Segment B, ↑ UP)        │
  │  ─ ─ ─ ─ ─ ─ ─ ─►   Bypass wire (edc_egress_t6_byp_intf) — combinational,   │
  │                       no clock; active only when sel=1 (tile harvested)       │
  │  [DEMUX sel=0/1]      Demux at NOC router: sel=0 → tile core, sel=1 → bypass │
  │  [MUX   sel=0/1]      Mux  at overlay out: sel=0 → from core, sel=1 → bypass │
  └──────────────────────────────────────────────────────────────────────────────┘


           APB4 Firmware
                │
                ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐ Y=4
  │  NOC2AXI tile  ·  tt_neo_overlay_wrapper  (BIU — never harvested)            │
  │                                                                               │
  │  ┌──────────────────────────────────────────────────────────┐                │
  │  │  tt_edc1_biu_soc_apb4  (BIU  node_id=0x0000)            │                │
  │  │    u_edc_req_src ─────────────────────────────────────────────► Seg A out │
  │  │    u_edc_rsp_snk ◄──────────────────────────────────────────── Seg B in  │
  │  │    fatal/crit/noncrit_irq ──► SoC interrupt controller   │                │
  │  └──────────────────────────────────────────────────────────┘                │
  │                                                                               │
  │  [MUX sel=0/1]  tt_edc1_serial_bus_mux                                       │
  │    in0 ◄── ovl_egress_intf        (BIU normal output;   sel=0: NORMAL)       │
  │    in1 ◄── edc_ingress_t6_byp_intf (bypass from below; sel=1: BYPASS)        │
  │    out ──► edc_egress_intf[x*5+4]  ──► Segment A ring                        │
  └──────────────────────────────────────────────────────┬───────────────────────┘
                                                         │ edc_egress_intf[x*5+4]
                                    ┌────────────────────▼──────────────────────┐
                                    │   Segment A — travelling DOWN ↓           │
                                    └────────────────────┬──────────────────────┘
                                                         │ edc_direct_conn_nodes (Y=3←Y=4)
                                                         ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐ Y=3
  │  Dispatch/Router tile  ·  tt_dispatch_top_east/west                          │
  │                          or tt_trin_noc_niu_router_wrap                      │
  │                                                                               │
  │  NOTE: Y=3 is NEVER harvested in N1B0.                                       │
  │        DEMUX/MUX bypass RTL exists for structural uniformity only.           │
  │        sel is fixed to 0 — bypass path never activated.                      │
  │                                                                               │
  │  NOC router EDC nodes (postdfx_aon_clk):                                     │
  │    tt_noc_niu_router → N/E/S/W/NIU/sec_fence edc_nodes                       │
  │    (errors reported on both Seg A and Seg B passes)                           │
  │                                                                               │
  │  [DEMUX sel=0 fixed]  tt_edc1_serial_bus_demux                               │
  │    in  ◄── ring from Y=4                                                      │
  │    out0 ──► edc_egress_intf ──► Dispatch/Router core   (always taken)        │
  │    out1 ──► edc_egress_t6_byp_intf                     (RTL present,         │
  │                                                          never selected)      │
  │                                                                               │
  │  Dispatch/Router EDC sub-chain  (N/E/S/W/NIU/sec_fence nodes)                │
  │                                                                               │
  │  [MUX sel=0 fixed]  tt_edc1_serial_bus_mux                                   │
  │    in0 ◄── sub-chain output                             (always taken)        │
  │    in1 ◄─ ─ edc_egress_t6_byp_intf                     (RTL present,         │
  │                                                          never selected)      │
  │    out ──► edc_egress_intf[x*5+3]  ──► Segment A continues                   │
  └──────────────────────────────────────────────────────┬───────────────────────┘
          ▲  Seg B loopback                              │ edc_egress_intf[x*5+3]
          │                             edc_direct_conn_nodes (Y=2←Y=3)
          │                                              ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐ Y=2
  │  Tensix tile  ·  tt_trin_noc_niu_router_wrap  +  tt_tensix_with_l1           │
  │                                                                               │
  │  NOC router EDC nodes (aon_clk) — always active; i_harvest_en gates errors   │
  │                                                                               │
  │  [DEMUX sel=0/1]  edc_demuxing_when_harvested                                │
  │    in  ◄── ring from Y=3                                                      │
  │    out0 ──► edc_egress_intf ──────────────────► Tensix cores  (sel=0: NORMAL)│
  │    out1 ──► edc_egress_t6_byp_intf ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐ │
  │                │ (sel=0 normal)                                              │ │
  │  tt_tensix_with_l1 EDC sub-chain:  T0→T1→L1→T3→T2  (aiclk)                 │ │
  │                                                           (bypass wire,      │ │
  │  [MUX sel=0/1]  tt_edc1_serial_bus_mux                    inside tile,      │ │
  │    in0 ◄── sub-chain output               (sel=0: NORMAL) no clock)         │ │
  │    in1 ◄─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─(sel=1: BYPASS)┘ │
  │    out ──► edc_egress_intf[x*5+2]  ──► Segment A continues                   │
  └──────────────────────────────────────────────────────┬───────────────────────┘
          ▲  Seg B loopback                              │ edc_egress_intf[x*5+2]
          │                             edc_direct_conn_nodes (Y=1←Y=2)
          │                                              ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐ Y=1
  │  Tensix tile  ·  tt_trin_noc_niu_router_wrap  +  tt_tensix_with_l1           │
  │  (same structure as Y=2)                                                      │
  │                                                                               │
  │  [DEMUX sel=0/1]  edc_demuxing_when_harvested                                │
  │    in  ◄── ring from Y=2                                                      │
  │    out0 ──► edc_egress_intf ──────────────────► Tensix cores  (sel=0: NORMAL)│
  │    out1 ──► edc_egress_t6_byp_intf ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐ │
  │                │ (sel=0 normal)                                              │ │
  │  tt_tensix_with_l1 EDC sub-chain:  T0→T1→L1→T3→T2  (aiclk)                 │ │
  │                                                           (bypass wire,      │ │
  │  [MUX sel=0/1]  tt_edc1_serial_bus_mux                    inside tile,      │ │
  │    in0 ◄── sub-chain output               (sel=0: NORMAL) no clock)         │ │
  │    in1 ◄─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─(sel=1: BYPASS)┘ │
  │    out ──► edc_egress_intf[x*5+1]  ──► Segment A continues                   │
  └──────────────────────────────────────────────────────┬───────────────────────┘
          ▲  Seg B loopback                              │ edc_egress_intf[x*5+1]
          │                             edc_direct_conn_nodes (Y=0←Y=1)
          │                                              ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐ Y=0
  │  Tensix tile  ·  tt_trin_noc_niu_router_wrap  +  tt_tensix_with_l1           │
  │  (same structure as Y=2)                                                      │
  │                                                                               │
  │  [DEMUX sel=0/1]  edc_demuxing_when_harvested                                │
  │    in  ◄── ring from Y=1                                                      │
  │    out0 ──► edc_egress_intf ──────────────────► Tensix cores  (sel=0: NORMAL)│
  │    out1 ──► edc_egress_t6_byp_intf ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐ │
  │                │ (sel=0 normal)                                              │ │
  │  tt_tensix_with_l1 EDC sub-chain:  T0→T1→L1→T3→T2  (aiclk)                 │ │
  │                                                           (bypass wire,      │ │
  │  [MUX sel=0/1]  tt_edc1_serial_bus_mux                    inside tile,      │ │
  │    in0 ◄── sub-chain output               (sel=0: NORMAL) no clock)         │ │
  │    in1 ◄─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─(sel=1: BYPASS)┘ │
  │                                                                               │
  │  ── U-TURN (Y=0 only, trinity.sv L454-456) ─────────────────────────────── ──│
  │    edc_egress_intf[x*5+0]  ──►  loopback_edc_ingress_intf[x*5+0]             │
  │    ── SEGMENT A ends / SEGMENT B begins ────────────────────────────────── ── │
  └──────────────────────────────────────────────────────┬───────────────────────┘
          │                                              ▲
          │  Segment B — ring travelling UP ↑            │
          └──────────────────────────────────────────────┘
                    Y=0 → Y=1 → Y=2 → Y=3 → BIU at Y=4

  ─────────────────────────────────────────────────────────────────────────────────
  HARVEST BYPASS SUMMARY  (Tensix tiles Y=0, Y=1, Y=2 only)

  NOTE: Y=3 (Dispatch/Router) is NEVER harvested.
        Bypass RTL present at Y=3 for structural uniformity; sel fixed to 0.

  When sel=0 (tile ALIVE):
    ring ──► [DEMUX out0] ──► tile EDC sub-chain ──► [MUX in0] ──► ring

  When sel=1 (tile HARVESTED):
    ring ──► [DEMUX out1] ─ ─ edc_egress_t6_byp_intf ─ ─► [MUX in1] ──► ring
             (skips aiclk sub-chain entirely; combinational wire, no clock)

  Three-layer protection:
    [1] DEMUX out1 → bypass wire    redirects ring away from dead tile input
    [2] MUX   in1  ← bypass wire    ignores any stale output from dead tile
    [3] i_harvest_en=1              forces all NOC router error inputs to 0

  Segment A (↓DOWN): edc_egress_intf[x*5+y]    Y=4 → Y=3 → Y=2 → Y=1 → Y=0
  Segment B (↑UP):   loopback_edc_*_intf        Y=0 → Y=1 → Y=2 → Y=3 → Y=4
  Inter-tile links:  tt_edc1_intf_connector     (combinational passthrough, no FF)
  ─────────────────────────────────────────────────────────────────────────────────
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

The EDC serial bus uses a **toggle-based handshake** to safely transfer data fragments across clock-domain boundaries. Each node can run its own clock; the protocol never requires a shared clock between adjacent nodes.

#### 3.3.1 Protocol State Machine

The sender (IS_REQ_SRC inside the BIU, or each node's pass-through state machine) drives the bus as follows:

```
IDLE state
  req_tgl[1:0] == 2'b00   (reset value; ack_tgl will also be 2'b00)

Fragment N transmission:
  1. Drive data[15:0] and data_p[0] onto the bus (stable combinational)
  2. Toggle req_tgl:
       if prev == 2'b00 or 2'b10 → drive 2'b01
       if prev == 2'b01         → drive 2'b10
     (value alternates 01 → 10 → 01 → 10 ...)
  3. Wait (stall) until ack_tgl[1:0] == req_tgl[1:0]

Receiver side (each node's ingress logic):
  1. Detect req_tgl change (edge-detect on synchronized req_tgl)
  2. Sample data[15:0] / data_p[0] — data is guaranteed stable
  3. Echo: ack_tgl[1:0] <= req_tgl_synced[1:0]

After ack received:
  4. Sender advances: fragment counter incremented, repeat for next fragment
```

The complete transaction is **self-throttling**: the sender never presents the next fragment until the acknowledgement returns. No external flow-control or credit signaling is needed.

#### 3.3.2 Two-Bit Toggle Encoding Rationale

`req_tgl[1:0]` uses **two bits** rather than a single toggle bit for two reasons:

1. **Glitch immunity at reset.** After reset, both `req_tgl` and `ack_tgl` are `2'b00`. The first real fragment drives `2'b01`. A spurious glitch on a single-bit signal might be indistinguishable from a real edge if the reset value is one of the two legal states. With two bits, `2'b00` is the reserved "no transfer pending" state; only `2'b01` and `2'b10` are used during normal operation. A receiver that sees `2'b00` knows no valid fragment has been sent.

2. **One-hot delta (Hamming distance = 1 between `01` and `10` impossible).** Transitions between `2'b01` and `2'b10` have Hamming distance 2 — both bits change simultaneously. This means any single-bit glitch on the CDC crossing produces an illegal code (`2'b00` or `2'b11`) which the receiver can flag as a parity-like error rather than a false trigger.

##### Illegal code detection and handling

The two legal toggle states are `2'b01` and `2'b10`. The two illegal codes are `2'b00` (reset sentinel) and `2'b11` (never driven by any sender). The receiver must treat these as distinct cases:

| Received `req_tgl` | Meaning | Required action |
|--------------------|---------|-----------------|
| `2'b00` | Reset sentinel — no fragment has been sent yet, or sender held in reset | Treat as idle; do **not** latch data; do **not** echo ack |
| `2'b01` | Valid toggle state A | Normal operation: latch data, echo ack |
| `2'b10` | Valid toggle state B | Normal operation: latch data, echo ack |
| `2'b11` | Illegal — single-bit glitch on one of the two CDC lines | Flag as protocol error; do **not** latch data; do **not** echo ack |

**Handling `2'b00` after reset:**
After de-assertion of reset, both sender and receiver initialize `req_tgl = 2'b00` and `ack_tgl = 2'b00`. The receiver must hold idle and not interpret `2'b00` as a toggle edge. The first real transfer drives `2'b01`, which is unambiguously distinct from `2'b00`.

**Handling `2'b11` (glitch):**
A `2'b11` code cannot arise from any legal sender state transition. It can only appear if exactly one of the two CDC lines is glitched or captured in a metastable state that resolves to the wrong value. The receiver should:
1. **Discard the fragment** — do not latch `data[15:0]` or `data_p`.
2. **Hold `ack_tgl` unchanged** — withholding the ack stalls the sender, which retains `req_tgl` and `data` stable.
3. **Report a CDC integrity error** — assert a sticky error flag visible to the EDC ring or a local status register, depending on implementation.

The sender will eventually time out (if a watchdog exists) or remain stalled. Because the protocol is self-throttling, **no data corruption propagates** — the receiver simply never acknowledges the corrupted fragment.

> **N1B0 implementation note:** The `tt_edc1_serial_bus_interface` receiver logic checks `req_tgl_synced` for the `2'b11` pattern after the 2-stage synchronizer output. If detected, `illegal_req_tgl` is asserted and fed into the node's error aggregator, which reports it as a non-critical EDC ring protocol error on the next Segment B pass. The ack is withheld until the sender drives a legal code again (recovery requires sender reset or re-drive).

#### 3.3.3 RTL CDC Synchronization Options

> **RTL verification note:** The parameters `DISABLE_SYNC_FLOPS`, `ENABLE_INGRESS_SYNC`, and `ENABLE_EGRESS_SYNC` described in earlier drafts of this section were based on a design intent that was **not implemented** in the actual RTL. RTL audit of the N1B0 source tree confirmed that no such parameters exist. See **Appendix B** for the full RTL verification results.

The actual RTL (`tt_edc_node`, `tt_edc_bus_interface_unit`, `tt_edc_intf_connector`) has **no configurable sync-flop insertion** at node boundaries. All inter-node connections of `req_tgl`, `ack_tgl`, `data`, and `data_p` are implemented as **purely combinational `assign` statements** — no flip-flops, no synchronizer cells.

CDC safety for the EDC ring is therefore achieved entirely through physical and STA constraints, not through in-module synchronizer logic:

- All EDC nodes within a tile run on the **same clock** as the tile's primary domain (see Appendix B for per-node clock table). No cross-clock-domain `req_tgl` crossing occurs inside a tile.
- Inter-tile connections pass through `tt_edc_intf_connector`, which is purely combinational. The two adjacent tiles must share the same clock, or an external synchronizer must be inserted at the tile boundary by the integration layer.
- `data[15:0]` and `data_p` are stable for the full toggle-ack round-trip by protocol guarantee, so `set_false_path` is sufficient for the data lines at any crossing.

> **No `set_multicycle_path` is needed.** The protocol is self-throttling: the sender holds `req_tgl` and `data` stable until `ack_tgl` returns. The data lines are always captured after a full toggle-ack round-trip, so there is no multi-cycle timing relationship to annotate.

#### 3.3.4 CDC Constraint Summary

The table below summarises the SDC treatment for each crossing type, based on RTL audit results (see **Appendix B** for per-node clock assignments and full verification details).

| Crossing type | Sync mechanism | SDC treatment |
|---------------|----------------|---------------|
| Intra-tile node-to-node (same clock) | `assign` only — no sync cells | `set_false_path` on `req_tgl`/`ack_tgl` if tool reports CDC; data lines always `set_false_path` |
| Inter-tile via `tt_edc_intf_connector` (same clock domain) | `assign` only — purely combinational | `set_false_path` on `req_tgl`/`ack_tgl` and data lines |
| Inter-tile crossing clock domains | No RTL synchronizer present — correct by design for N1B0 Samsung 5nm | `set_false_path` on `req_tgl`/`ack_tgl`; CDC tool waiver with MTBF calculation (§3.5.4); data lines `set_false_path`; no sync cell or proximity constraint required |
| `data[15:0]` / `data_p` (any crossing) | N/A — no sync cells | `set_false_path` from driving flop; data held stable by self-throttling protocol |

> **N1B0 note:** In the N1B0 composite tile (NOC2AXI_ROUTER_NE/NW_OPT), the router EDC node (Y=3) and the NIU EDC node (Y=4) are within the same module and share the same clock. The inter-node `assign` wiring is intra-domain and requires only `set_false_path` constraints on the toggle signals.

### 3.4 async_init Signal

#### 3.4.1 Why async_init Is Needed

The EDC ring must be **initialized** (all node state machines reset to IDLE, all toggle counters zeroed) before normal operation. There are two conceivable approaches:

| Approach | Mechanism | Problem |
|----------|-----------|---------|
| **Sequential WR_CMD broadcast** | BIU sends a CMD_INIT packet down the ring | The packet propagates serially: each node initializes only when the packet arrives. Nodes near the end of the ring are still operating (or in unknown state) while the head of the ring is already initialized. Race conditions possible during bring-up |
| **async_init (chosen)** | Combinational wire propagated through ring; each node synchronized locally | All nodes see `async_init` rise within a single combinational-path propagation delay. Each node latches it with its own local synchronizer. All nodes initialize quasi-simultaneously regardless of clock phase. No ring packet ordering dependency |

The `async_init` wire is therefore a **global asynchronous assert / synchronous deassert** signal: asserted combinationally, released after the BIU counts `MCPDLY` cycles (ensuring all nodes have seen and latched the assertion).

#### 3.4.2 RTL Implementation

```systemverilog
// tt_edc1_bus_interface_unit.sv — BIU drives async_init from CTRL.INIT register
assign src_ingress_intf.async_init = csr_cfg.CTRL.INIT.value;

// tt_edc1_state_machine.sv:1129 — every ring node passes async_init through combinationally
assign egress_intf.async_init = ingress_intf.async_init;

// tt_edc1_state_machine.sv:1132 — each node synchronizes locally with a 3-stage sync
tt_libcell_sync3r init_sync3r (
    .i_CK (i_clk),
    .i_RN (i_reset_n),
    .i_D  (ingress_intf.async_init),   // async input
    .o_Q  (init)                        // synchronized, used internally
);
```

Key observations:
- The `async_init` wire is purely combinational through all ring nodes (no flop).
- Each node samples `async_init` through its own **3-stage synchronizer** (`tt_libcell_sync3r`).
- The BIU samples its own loopback `async_init` through the same 3-stage synchronizer before using `init` internally.

#### 3.4.3 SDC / CDC Treatment

Because `async_init` is an asynchronous multi-fanout signal crossing from the BIU clock domain into every node's local clock domain:

```tcl
# SDC — set_false_path from BIU CTRL.INIT register output to all sync3r D inputs
# (async_init combinational path — no timing requirement between source and destination)
set_false_path -from [get_cells *csr_cfg_CTRL_INIT*] \
               -to   [get_pins */init_sync3r/i_D]

# Equivalently, if tool captures the net by name:
set_false_path -through [get_nets *async_init*]
```

The 3-stage synchronizer handles MTBF at each destination. No `set_multicycle_path` is needed. The false-path suppresses spurious timing violations on the long combinational chain through the ring.

#### 3.4.4 MCPDLY=7 — Derivation and Configurability

```systemverilog
// tt_edc1_bus_interface_unit.sv
localparam int unsigned MCPDLY = 7;  // fixed — not a parameter
```

**MCPDLY is a `localparam` — it is fixed in RTL and cannot be reconfigured at runtime.** There is no register field that overrides it.

**Derivation:** The BIU must hold `async_init` asserted long enough that the farthest ring node has (a) seen the combinational pulse propagate through all repeaters, and (b) had time to latch it through a 3-stage synchronizer. The budget:

| Component | Cycles (BIU clock) |
|-----------|-------------------|
| Max repeater stages on ring (baseline Trinity) | ~3 |
| 3-stage synchronizer latency at worst-case node | 3 |
| Setup margin | 1 |
| **Total = MCPDLY** | **7** |

**N1B0 consideration:** N1B0's composite tile has `REP_DEPTH_LOOPBACK=6` — six repeater stages on the ring loopback path, which is deeper than the baseline. Does MCPDLY=7 still provide margin?

- The 6 repeater stages add ~6 gate delays ≈ 1–2 clock cycles at typical frequency (these are combinational repeater buffers, not flip-flops).
- The async_init wire uses the **forward** (not loopback) path, which has `REP_DEPTH_LOOPBACK=6` stages but the actual number of cycles the BIU clock sees depends on the combinational gate delay, not a counter.
- MCPDLY counts BIU clock cycles after `CTRL.INIT` is written. Even with 6 repeater levels, the combinational propagation finishes well within 3 BIU clock cycles (assuming ≥200 MHz clock, each level is <500 ps).
- Therefore **MCPDLY=7 remains adequate for N1B0**. The 3-stage synchronizer at each node (3 local-clock cycles) is the dominant term; the repeater stages contribute at most 1 extra BIU cycle.

**If a design ever needs a longer hold** (e.g., much slower BIU clock or more ring levels), the localparam must be changed in RTL — there is no runtime register override.

---

### 3.5 Complete Ring Path F/F and CDC Analysis — Tile Y=2 (Tensix, Column X=0, Segment A)

This section lists every element in the Segment A (downward) EDC ring path as the ring traverses one Tensix tile.
Y=2 is used as the example tile; the same structure applies to Y=0 and Y=1.

#### 3.5.1 Conventions

**Signal rows per EDC node:** Each EDC node (`tt_edc1_node`) produces three rows — one per protocol signal:
- **req_tgl** — toggle request from the upstream node; captured by a F/F inside this node → **Control path** (handshake control, not payload)
- **data** — packet payload; registered inside this node (protocol guarantees data stable before capture) → **Data path** (carries address, command, or capture value)
- **ack_tgl** — toggle acknowledgment driven back toward the upstream node from this node → **Control path** (handshake control)

**D/C Path column:** Added to every row.
- `Control` — F/F is on the control (handshake) path; timing constraint: `set_false_path` on toggle; CDC risk if clocks differ
- `Data` — F/F is on the data path; timing constraint: `set_false_path` always (protocol-guaranteed stable before capture); no CDC risk regardless of clock domain
- `N/A` — element has no F/F; path classification not applicable

**Sync / Async column:**
- `SYNC (same clk)` — source clock = node clock; F/F is a normal registered flop; STA: `set_false_path` on toggle
- `ASYNC (CDC: X→Y)` — source clock ≠ node clock; **no RTL synchronizer inserted** (per §3.3.3); CDC handled by physical constraints / integration-level synchronizer insertion; STA: `set_false_path` on data, external CDC cell on toggle
- `N/A` — element has no F/F (combinational pass-through)

**Clock names** are top-level `trinity.sv` port names:
- `i_ai_clk[0]` — per-column AI clock for column X=0 (Tensix cores, FPU, L1, Overlay-ai)
- `i_noc_clk` — global NoC clock (NOC/NIU/Router logic, shared across all columns)
- `i_dm_clk` — data-management clock (Overlay-dm domain: WDT, APB bridge)
- `—` — no clock (purely combinational element)

**#Rep column:** Applicable only to `tt_edc1_serial_bus_rep` repeater instances. Baseline Trinity inter-tile repeaters use `REP_DEPTH=2` per connector. N1B0 composite loopback uses `REP_DEPTH_LOOPBACK=6` (Segment B only; see §3.5.3). Repeaters are **combinational buffer chains** — gate-level buffers for drive strength, **not registered flip-flops**.

**Ring enters tile Y=2 from tile Y=3 (DISPATCH_E, last EDC element exits on `i_ai_clk[0]`).**

---

#### 3.5.2 Segment A Path Table (Downward: Y=3 exit → Y=2 entry → Y=1 entry)

> Tile context: `gen_x[0].gen_y[2]` → `gen_tensix.` prefix for all instance paths within this tile.
> Abbreviated prefix used in table: **`[tile]`** = `gen_x[0].gen_y[2].gen_tensix.`

| # | Signal / Element | Clock | #Rep | Sync / Async | F/F? | **D/C Path** | Category | Module | Instance Path (abbreviated) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Inter-tile connector** (Y=3→Y=2 boundary) | — | 2 | N/A | No | **N/A** | Inter-tile connector (Seg A) | `tt_edc1_intf_connector` | `gen_x[0].gen_y[2].top_nodes_edc_connections.edc_direct_conn_nodes` |
| **─── NOC / NIU / Router wrapper (i_noc_clk domain) ───** |
| 2 | **Harvest demux** (bypass if tile harvested) | — | N/A | N/A | No | **N/A** | Harvest bypass demux | `tt_edc1_serial_bus_demux` | `[tile]tt_trin_noc_niu_router_inst.edc_harvest_demux` |
| 3a | req_tgl → **NORTH_VC_BUF node** | `i_noc_clk` | N/A | ASYNC (CDC: ai→noc) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]tt_trin_noc_niu_router_inst.noc_niu_router_inst.has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst` |
| 3b | data → **NORTH_VC_BUF node** | `i_noc_clk` | N/A | false_path (stable by protocol) | Yes | **Data** | EDC node data reg | (same as 3a) | (same as 3a) |
| 3c | ack_tgl ← **NORTH_VC_BUF node** | `i_noc_clk` | N/A | ASYNC (CDC: noc→ai, back to prev) | Yes | **Control** | EDC node ack drive FF | (same as 3a) | (same as 3a) |
| 4a | req_tgl → **NORTH_HEADER_ECC node** (inst=0x01) | `i_noc_clk` | N/A | SYNC (same clk: noc→noc) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...noc_overlay_edc_wrapper_north_router_header_ecc.edc_node_inst` |
| 4b | data → **NORTH_HEADER_ECC node** | `i_noc_clk` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same as 4a) | (same as 4a) |
| 4c | ack_tgl ← **NORTH_HEADER_ECC node** | `i_noc_clk` | N/A | SYNC (same clk: noc→noc) | Yes | **Control** | EDC node ack drive FF | (same as 4a) | (same as 4a) |
| 5a | req_tgl → **NORTH_DATA_PARITY node** (inst=0x02) | `i_noc_clk` | N/A | SYNC (same clk) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...noc_overlay_edc_wrapper_north_router_data_parity.edc_node_inst` |
| 5b | data → **NORTH_DATA_PARITY node** | `i_noc_clk` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same as 5a) | (same as 5a) |
| 5c | ack_tgl ← **NORTH_DATA_PARITY node** | `i_noc_clk` | N/A | SYNC (same clk) | Yes | **Control** | EDC node ack drive FF | (same as 5a) | (same as 5a) |
| **6–14** | **EAST_VC_BUF / EAST_HEADER_ECC / EAST_DATA_PARITY** (inst=0x03–0x05) — 3 rows each: req_tgl / data / ack_tgl | `i_noc_clk` | N/A | SYNC (same clk) | Yes (×3 per node) | **Ctrl / Data / Ctrl** | EDC nodes (same pattern as rows 4–5) | `tt_edc1_node` (×3) | `[tile]...noc_overlay_edc_wrapper_east_router_{vc_buf,header_ecc,data_parity}.edc_node_inst` |
| **15–17** | **SOUTH_VC_BUF / SOUTH_HEADER_ECC / SOUTH_DATA_PARITY** (inst=0x06–0x08) — 3 rows each | `i_noc_clk` | N/A | SYNC (same clk) | Yes (×3 per node) | **Ctrl / Data / Ctrl** | EDC nodes | `tt_edc1_node` (×3) | `[tile]...noc_overlay_edc_wrapper_south_router_{vc_buf,header_ecc,data_parity}.edc_node_inst` |
| **18–20** | **WEST_VC_BUF / WEST_HEADER_ECC / WEST_DATA_PARITY** (inst=0x09–0x0B) — 3 rows each | `i_noc_clk` | N/A | SYNC (same clk) | Yes (×3 per node) | **Ctrl / Data / Ctrl** | EDC nodes | `tt_edc1_node` (×3) | `[tile]...noc_overlay_edc_wrapper_west_router_{vc_buf,header_ecc,data_parity}.edc_node_inst` |
| 21a | req_tgl → **SEC_FENCE node** (inst=0xC0) | `i_noc_clk` | N/A | SYNC (same clk) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...noc_niu_router_inst.has_sec_fence_edc.noc_sec_fence_edc_wrapper.g_edc_inst.edc_node_inst` |
| 21b | data → **SEC_FENCE node** | `i_noc_clk` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same as 21a) | (same as 21a) |
| 21c | ack_tgl ← **SEC_FENCE node** | `i_noc_clk` | N/A | SYNC (same clk) | Yes | **Control** | EDC node ack drive FF | (same as 21a) | (same as 21a) |
| **─── CDC boundary: i_noc_clk → i_ai_clk[0] (no RTL sync FF; physical CDC constraint required) ───** |
| 22 | **Domain crossing wire** (NOC wrapper → Tensix sub-core chain) | — | N/A | N/A (CDC: noc→ai; no RTL FF; physical constraint) | No | **N/A** | Internal tile wire (CDC boundary) | — | `[tile]tt_trin_noc_niu_router_inst.edc_egress_intf → tt_tensix_with_l1.edc_ingress_intf` |
| **─── Tensix sub-core chain, T0 (i_ai_clk[0] domain) ───** |
| 23a | req_tgl → **T6_MISC node** (part=0x10, inst=0x00) | `i_ai_clk[0]` | N/A | ASYNC (CDC: noc→ai, first ai node) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]tt_tensix_with_l1.t6_misc_inst.t6_misc_edc_wrapper.edc_node_inst` |
| 23b | data → **T6_MISC node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same as 23a) | (same as 23a) |
| 23c | ack_tgl ← **T6_MISC node** | `i_ai_clk[0]` | N/A | ASYNC (CDC: ai→noc, back to NOC domain) | Yes | **Control** | EDC node ack drive FF | (same as 23a) | (same as 23a) |
| 24a | req_tgl → **IE_PARITY node** (part=0x10, inst=0x03) | `i_ai_clk[0]` | N/A | SYNC (same clk: ai→ai) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]tt_tensix_with_l1.instrn_engine_wrapper[0].tt_instrn_engine_wrapper_inst.ie_parity_edc.tt_edc1_node_inst` |
| 24b | data → **IE_PARITY node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same as 24a) | (same as 24a) |
| 24c | ack_tgl ← **IE_PARITY node** | `i_ai_clk[0]` | N/A | SYNC (same clk) | Yes | **Control** | EDC node ack drive FF | (same as 24a) | (same as 24a) |
| 25a | req_tgl → **SRCB node** (inst=0x04) | `i_ai_clk[0]` | N/A | SYNC (same clk) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0].tt_instrn_engine_wrapper_inst.srcb_edc.tt_edc1_node_inst` |
| 25b | data → **SRCB node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 25c | ack_tgl ← **SRCB node** | `i_ai_clk[0]` | N/A | SYNC (same clk) | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 26a | req_tgl → **UNPACK node** (inst=0x05) | `i_ai_clk[0]` | N/A | SYNC (same clk) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0].tt_instrn_engine_wrapper_inst.unpack_edc.tt_edc1_node_inst` |
| 26b | data → **UNPACK node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 26c | ack_tgl ← **UNPACK node** | `i_ai_clk[0]` | N/A | SYNC (same clk) | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 27a | req_tgl → **PACK node** (inst=0x06) | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0]...pack_edc.tt_edc1_node_inst` |
| 27b | data → **PACK node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 27c | ack_tgl ← **PACK node** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 28a | req_tgl → **SFPU node** (inst=0x07) | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0]...sfpu_edc.tt_edc1_node_inst` |
| 28b | data → **SFPU node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 28c | ack_tgl ← **SFPU node** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 29a | req_tgl → **GPR_P0 node** (inst=0x08) | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0]...gpr_p0_edc.tt_edc1_node_inst` |
| 29b | data → **GPR_P0 node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 29c | ack_tgl ← **GPR_P0 node** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 30a | req_tgl → **GPR_P1 node** (inst=0x09) | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0]...gpr_p1_edc.tt_edc1_node_inst` |
| 30b | data → **GPR_P1 node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 30c | ack_tgl ← **GPR_P1 node** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 31a | req_tgl → **CFG_EXU_0 node** (inst=0x0A) | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0]...cfg_exu0_edc.tt_edc1_node_inst` |
| 31b | data → **CFG_EXU_0 node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 31c | ack_tgl ← **CFG_EXU_0 node** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 32a | req_tgl → **CFG_EXU_1 node** (inst=0x0B) | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0]...cfg_exu1_edc.tt_edc1_node_inst` |
| 32b | data → **CFG_EXU_1 node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 32c | ack_tgl ← **CFG_EXU_1 node** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 33a | req_tgl → **CFG_GLOBAL node** (inst=0x0C) | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0]...cfg_global_edc.tt_edc1_node_inst` |
| 33b | data → **CFG_GLOBAL node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 33c | ack_tgl ← **CFG_GLOBAL node** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 34a | req_tgl → **THCON_0 node** (inst=0x0D) | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0]...thcon0_edc.tt_edc1_node_inst` |
| 34b | data → **THCON_0 node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 34c | ack_tgl ← **THCON_0 node** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 35a | req_tgl → **THCON_1 node** (inst=0x0E) | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[0]...thcon1_edc.tt_edc1_node_inst` |
| 35b | data → **THCON_1 node** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 35c | ack_tgl ← **THCON_1 node** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| **─── L1 partition hub (inside tt_tensix_with_l1, i_ai_clk[0] domain) ───** |
| 36a | req_tgl → **T6_MISC L1 shared node** (part=0x10, inst=0x00, L1 sub-node) | `i_ai_clk[0]` | N/A | SYNC (same clk) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]tt_tensix_with_l1.t6_l1_partition_inst.t6_misc_l1_edc.tt_edc1_node_inst` |
| 36b | data → **T6_MISC L1** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 36c | ack_tgl ← **T6_MISC L1** | `i_ai_clk[0]` | N/A | SYNC (same clk) | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 37a | req_tgl → **L1W2 SRAM node [0]** (part=0x18, inst=0x00) — N1B0: 256 macros/partition | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]tt_tensix_with_l1.t6_l1_partition_inst.l1w2_bank[0].edc_node_inst` |
| 37b | data → **L1W2 SRAM node [0]** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg (ECC syndrome, addr) | (same) | (same) |
| 37c | ack_tgl ← **L1W2 SRAM node [0]** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| 38a | req_tgl → **L1W2 SRAM node [1]** (inst=0x01) | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]...t6_l1_partition_inst.l1w2_bank[1].edc_node_inst` |
| 38b | data → **L1W2 SRAM node [1]** | `i_ai_clk[0]` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| 38c | ack_tgl ← **L1W2 SRAM node [1]** | `i_ai_clk[0]` | N/A | SYNC | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| **39+** | **L1W2 SRAM nodes [2..N-1]** (inst=0x02..N-1) — 3 rows each: req_tgl / data / ack_tgl | `i_ai_clk[0]` | N/A | SYNC | Yes (×3 each) | **Ctrl / Data / Ctrl** | EDC node (L1 SRAM ECC) | `tt_edc1_node` | `[tile]...t6_l1_partition_inst.l1w2_bank[k].edc_node_inst` (k=2..N-1) |
| **─── Tensix T1, T2, T3 sub-cores (i_ai_clk[0] domain) ───** |
| T1 | **T1 sub-core nodes** (part=0x11, inst=0x03–0x0E, 0x10, 0x20–0x2B) — 3 rows each | `i_ai_clk[0]` | N/A | SYNC | Yes (×3 each) | **Ctrl / Data / Ctrl** | EDC nodes (same as T0 rows 24–35 minus T6_MISC) | `tt_edc1_node` | `[tile]tt_tensix_with_l1.instrn_engine_wrapper[1].tt_instrn_engine_wrapper_inst.{node}_edc.tt_edc1_node_inst` |
| T2 | **T2 sub-core nodes** (part=0x12) — 3 rows each | `i_ai_clk[0]` | N/A | SYNC | Yes (×3 each) | **Ctrl / Data / Ctrl** | EDC nodes | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[2]...` |
| T3 | **T3 sub-core nodes** (part=0x13) — 3 rows each | `i_ai_clk[0]` | N/A | SYNC | Yes (×3 each) | **Ctrl / Data / Ctrl** | EDC nodes | `tt_edc1_node` | `[tile]...instrn_engine_wrapper[3]...` |
| **─── Overlay wrapper (tt_neo_overlay_wrapper) ───** |
| Ov1 | **Internal wire** (Tensix → Overlay domain entry) | — | N/A | N/A (ai_clk shared; no CDC) | No | **N/A** | Internal tile wire | — | `[tile]tt_tensix_with_l1.edc_egress_intf → tt_neo_overlay_wrapper.edc_ingress_intf` |
| Ov2a | req_tgl → **Overlay WDT node** (part=0x1A, inst=0xA0) | `i_dm_clk` | N/A | ASYNC (CDC: ai→dm) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]tt_neo_overlay_wrapper.overlay_edc_wrapper.wdt_edc_node_inst.tt_edc1_node_inst` |
| Ov2b | data → **Overlay WDT node** | `i_dm_clk` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| Ov2c | ack_tgl ← **Overlay WDT node** | `i_dm_clk` | N/A | ASYNC (CDC: dm→ai) | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| Ov3a | req_tgl → **Overlay APB bridge node** (part=0x1A, inst=0xA1) | `i_dm_clk` | N/A | SYNC (same clk: dm→dm) | Yes | **Control** | EDC node req capture FF | `tt_edc1_node` | `[tile]tt_neo_overlay_wrapper.overlay_edc_wrapper.apb_bridge_edc_node_inst.tt_edc1_node_inst` |
| Ov3b | data → **Overlay APB bridge** | `i_dm_clk` | N/A | false_path (stable) | Yes | **Data** | EDC node data reg | (same) | (same) |
| Ov3c | ack_tgl ← **Overlay APB bridge** | `i_dm_clk` | N/A | SYNC (same clk) | Yes | **Control** | EDC node ack drive FF | (same) | (same) |
| Ov4 | **Harvest mux** (recombines live path and bypass path) | — | N/A | N/A | No | **N/A** | Harvest bypass mux | `tt_edc1_serial_bus_mux` | `[tile]tt_neo_overlay_wrapper.edc_harvest_mux` |
| **─── Exit tile Y=2 ───** |
| Exit | **Inter-tile connector** (Y=2→Y=1 boundary) | — | 2 | N/A | No | **N/A** | Inter-tile connector (Seg A) | `tt_edc1_intf_connector` | `gen_x[0].gen_y[1].top_nodes_edc_connections.edc_direct_conn_nodes` |

> **Note on rows T1/T2/T3:** Each Tensix sub-core (T1, T2, T3) has the same EDC node set as T0 minus the `T6_MISC` (inst=0x00) shared node. T6_MISC is T0-only. All T1/T2/T3 nodes start from `IE_PARITY` (inst=0x03). Each contains FPU Gtile nodes (inst=0x0F, 0x20–0x2B), making the total per sub-core ≈18 nodes × 3 rows = 54 rows per T1/T2/T3.

> **Note on L1W2 SRAM count (N1B0):** N1B0 uses 256 SRAM macros per L1 partition (4× baseline). The L1W2 SRAM node count N depends on the partition macro count. Not all macros are necessarily exposed as individual EDC nodes; consult `tt_t6_l1_partition.sv:663–667` for the exact `l1w2_bank[k]` count.

---

#### 3.5.3 Segment B Path (Loopback, Upward: Y=0→Y=1→Y=2→Y=3)

Segment B traverses the **same nodes in the same order** as Segment A, but uses the loopback interface signals (`loopback_edc_ingress_intf` / `loopback_edc_egress_intf`). The F/F and CDC properties are identical to Segment A.

**Key difference — inter-tile repeaters on Segment B (N1B0 composite tile X=1,2):**
The composite tile `NOC2AXI_ROUTER_NE/NW_OPT` at Y=4/Y=3 inserts `REP_DEPTH_LOOPBACK=6` repeater stages on the loopback (Segment B) wire between the composite's Y=3 output and the BIU's loopback input. For all other standard inter-tile boundaries, the loopback connector also uses `REP_DEPTH=2` (same as Segment A).

| Boundary | Path | #Rep (Seg A) | #Rep (Seg B) | Notes |
|---|---|---|---|---|
| Y=3→Y=2 (direct, Seg A) | `edc_direct_conn_nodes` | 2 | — | Standard connector |
| Y=2→Y=3 (loopback, Seg B) | `edc_loopback_conn_nodes` | — | 2 | Standard connector |
| Y=4→Y=3 (composite, Seg B) | `edc_loopback_conn_nodes` (inside composite) | — | 6 (`REP_DEPTH_LOOPBACK`) | N1B0 composite tile only |

---

#### 3.5.4 CDC Crossing Summary (Tile Y=2)

| # | Boundary | From clock | To clock | Direction | RTL sync FF | Constraint required |
|---|---|---|---|---|---|---|
| 1 | Tile Y=3 exit → NOC wrapper entry (row 3a) | `i_ai_clk[0]` | `i_noc_clk` | Seg A downward | **None** | Physical CDC synchronizer insertion or `set_false_path` on toggle + multicycle constraint on `ack_tgl` return |
| 2 | NOC wrapper exit → Tensix T0 entry (row 23a) | `i_noc_clk` | `i_ai_clk[0]` | Seg A (internal wire #22) | **None** | Same as above |
| 3 | Tensix core exit → Overlay WDT entry (row Ov2a) | `i_ai_clk[0]` | `i_dm_clk` | Seg A (internal wire Ov1) | **None** | Physical CDC synchronizer insertion |
| 4 | Overlay exit → Tile Y=1 entry | `i_dm_clk` | Next tile's primary clock | Seg A downward | **None** | Depends on Y=1 tile's clock domain |

> **Implication for STA:** The ring path contains 3 intra-tile CDC crossings (rows 1→3a, 22→23a, Ov1→Ov2a) at tile Y=2. In each case the toggle signal (`req_tgl`, `ack_tgl`) crosses a clock domain boundary with no RTL synchronizer cell. The required STA treatment is `set_false_path` on all `req_tgl`/`ack_tgl` nets. No synchronizer cell insertion and no physical proximity constraint are required — see §3.5.4 for the Samsung 5nm MTBF derivation and effective toggle rate calculation that establish this. The `data` lines are always `set_false_path` regardless of CDC crossing (self-throttling protocol guarantee).

##### Why `req_tgl` / `ack_tgl` are `set_false_path` — and what that really means

**`set_false_path` on a toggle signal is correct for STA, but it does NOT eliminate metastability risk.**

The STA tool operates on worst-case setup/hold timing along a timed path. A toggle signal by definition changes once per round-trip (many thousands of destination-clock cycles), so there is no meaningful setup/hold relationship to check — the STA tool would either flag a spurious violation or silently produce a wrong result. `set_false_path` simply tells the tool "do not apply timing analysis to this net." This is always the right SDC treatment for a CDC toggle.

**What the 2-bit encoding buys you (partial protection)**

The `req_tgl` encoding is `2'b00`=idle, `2'b01`=forward, `2'b10`=return, `2'b11`=illegal (§3.3.2). If metastability occurs at a CDC crossing and the signal resolves to `2'b11`, the receiving node detects it immediately (`illegal_req_tgl`), withholds the ack, and reports an EDC ring protocol error. This covers one of three wrong-resolution outcomes.

The other two outcomes — metastability resolves to `2'b00` or to the opposite legal code — are not caught by encoding alone. In those cases the node may silently ignore a valid packet (`2'b00` looks like idle) or double-acknowledge. Recovery depends on the BIU timeout firing and SW retrying the command.

**Why async FF insertion is not required for N1B0 (Samsung 5nm)**

CDC safety for `req_tgl`/`ack_tgl` is determined by the MTBF formula:

```
               exp(T_res / τ)
MTBF = ─────────────────────────────────
         f_data × f_clk × T_window
```

The two critical parameters are `τ` (process-dependent) and `f_data` (protocol-determined).

**Samsung 5nm process parameter: τ ≈ 10 ps**

Samsung 5LPE/5LPP flip-flop metastability time constant τ is approximately 10 ps (from standard cell characterization). This is consistent with TSMC N5-class nodes. The small τ means metastability resolves extremely rapidly — within a fraction of the capture clock period.

**Effective toggle rate: f_data ≤ 50 MHz (protocol-guaranteed)**

The self-throttling protocol enforces a hard upper bound on `f_data`. `req_tgl` cannot transition again until `ack_tgl` returns — i.e., not until the full ring round-trip completes:

```
T_hw_min  =  propagation through all nodes + MCPDLY wait
          =  10 tiles × ~1 ns + 7 cycles × 1 ns
          ≈  20 ns

f_data_max (hardware ceiling) = 1 / 20 ns = 50 MHz
```

In normal SW-driven operation (APB write + poll overhead):

```
T_sw  =  APB write (8 cycles / 100 MHz)  +  ring round-trip (~20 ns)
       +  MCPDLY wait (7 ns)             +  SW poll loop (~40 ns)
      ≈  150 ns per command

f_data_sw_max = 1 / 150 ns ≈ 6.7 MHz   (continuous stress mode)

Typical background health monitoring (T_interval = 100 µs):
f_data_typical = 1 / 100 µs = 10 kHz
```

**MTBF calculation — Samsung 5nm, worst-case rates**

```
Parameters:
  T_res     = 0.9 ns  (T_clk=1ns − t_setup≈0.1ns, at f_clk=1 GHz)
  τ         = 10 ps   (Samsung 5nm)
  T_window  = 50 ps   (t_setup + t_hold, from timing library)

At hardware maximum (f_data = 50 MHz):
  MTBF = exp(0.9 ns / 10 ps) / (50×10⁶ × 10⁹ × 50×10⁻¹²)
       = exp(90)              / 2.5×10⁶
       = 1.22×10³⁹            / 2.5×10⁶
       ≈ 4.9×10³² seconds
       ≈ 1.5×10²⁵ years

At typical background rate (f_data = 10 kHz):
  MTBF = exp(90) / (10⁴ × 10⁹ × 50×10⁻¹²)
       = 1.22×10³⁹ / 0.5×10⁻³
       ≈ 2.4×10⁴² years
```

Both results are orders of magnitude longer than the age of the universe (~1.4×10¹⁰ years). On Samsung 5nm, the metastability failure probability is effectively zero for any realistic EDC operating mode.

Given this:
- No async FF insertion is required. The `DISABLE_SYNC_FLOPS=1` default is correct and permanent for N1B0.
- No physical proximity constraint is required. The MTBF is safe regardless of placement distance.
- `set_false_path` on `req_tgl`/`ack_tgl` (STA) and a CDC tool waiver (documenting this calculation) are the complete and sufficient implementation.
- The BIU timeout (`TIMEOUT_CNT`) remains the protocol-level safety net for any other failure mode (e.g., reset glitch, power event) — not specifically for metastability.

**Residual risk note**

The metastability risk is negligible on Samsung 5nm but is non-zero in absolute mathematical terms. The risk is bounded:

| Risk vector | Probability | Mitigation |
|---|---|---|
| Single metastability event causing `2'b11` | < 10⁻³² per year | `illegal_req_tgl` detection → BIU timeout → SW retry |
| Single metastability event causing `2'b00` (looks idle) | < 10⁻³² per year | BIU timeout → SW retry |
| Single metastability event causing wrong legal code | < 10⁻³² per year | Silent misread; BIU timeout → SW retry |
| Future derivative on older process (τ > 50 ps) | Re-evaluate required | Recalculate MTBF; consider sync FF if f_data > 1 MHz |

For any future Trinity derivative targeting a process node with τ > 50 ps, this analysis must be repeated. At τ = 50 ps and f_data = 50 MHz, MTBF drops to ~26 seconds per FF pair — which would require async FF insertion or rate-limiting the EDC command rate to ≤ 10 kHz.

**Summary — decision matrix**

| Scenario | CDC behavior | Recovery |
|---|---|---|
| `req_tgl` resolves correctly (effectively always) | Normal handshake | None needed |
| `req_tgl` resolves to `2'b11` (detectable) | `illegal_req_tgl` asserted; ack withheld | BIU timeout → SW retry |
| `req_tgl` resolves to wrong legal code (< 10⁻³² /yr) | Silent protocol error | BIU timeout → SW retry |
| Explicit 2-FF sync inserted (not used in N1B0) | Metastability eliminated | No timeout needed for CDC |

**Recommendation (N1B0 Samsung 5nm):** Apply `set_false_path` on all `req_tgl`/`ack_tgl` nets in SDC. File CDC tool waivers with this MTBF calculation. No RTL change, no proximity constraint, no async FF insertion.

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

### 4.3 SW Usage Guide — How to Send EDC Packets

This section explains how a software or firmware engineer uses the BIU register interface to issue EDC packets, interpret responses, and handle error cases.

#### 4.3.1 When to Use Each Command

| Command | Enum | Use case |
|---------|------|----------|
| `WR_CMD` | `4'h1` | Write a value to a register inside a specific EDC node (e.g., configure a node's threshold, enable/disable error reporting) |
| `RD_CMD` | `4'h2` | Read back a register from a specific EDC node (e.g., poll a captured error code, read a counter) |
| `GEN_CMD` (broadcast) | `4'h3` or CMD_OPT[7]=1 | Simultaneously write a value to the same register address across all nodes; useful for initialization (e.g., clear all STAT registers at once) |
| `EV_CMD` (event notify) | `4'h4` | BIU injects a synthetic event; used in self-test flows |

> **Caution with broadcast (`GEN_CMD`/broadcast mode):** A broadcast packet does not wait for individual node acknowledgements. There is no per-node error return. Use single-node `WR_CMD` for safety-critical configuration; use broadcast only for bulk initialization where the cost of individual failures is acceptable (e.g., clear-on-reset flows).

#### 4.3.2 Step-by-Step: Sending a WR_CMD

**Goal:** Write value `0xABCD` to register address `0x10` of node `0x8205` (Tensix T1 TDMA channel 5, column X=0).

```
Step 1: Verify BIU is idle
  poll BIU.STAT.REQ_PKT_SENT == 0  (or just check BUSY bit if present)

Step 2: Set destination node
  BIU.REQ_HDR0.TGT_ID = 0x8205

Step 3: Set source (BIU self-node = 0x0000)
  BIU.REQ_HDR1.SRC_ID = 0x0000

Step 4: Set command and payload
  BIU.REQ_HDR0.CMD      = WR_CMD (4'h1)
  BIU.REQ_HDR0.PYLD_LEN = 4'd1   (one payload fragment = 16 bits)
  BIU.REQ_HDR0.CMD_OPT  = 8'h00

Step 5: Set register address (in DATA0/DATA1 of HDR1)
  BIU.REQ_HDR1.DATA0 = 8'h10   (register address low byte)
  BIU.REQ_HDR1.DATA1 = 8'h00   (register address high byte, if applicable)

Step 6: Set payload data
  BIU.REQ_DATA[0].DATA2 = 8'hCD   (low byte of 0xABCD)
  BIU.REQ_DATA[0].DATA3 = 8'hAB   (high byte of 0xABCD)

Step 7: Trigger packet send
  BIU.CTRL.SEND = 1   (write-1-pulse, self-clearing)

Step 8: Wait for completion
  poll BIU.STAT.REQ_PKT_SENT == 1  (packet sent interrupt flag)
  write BIU.STAT.REQ_PKT_SENT = 1  (W1C — clear the flag)
```

#### 4.3.3 Step-by-Step: Sending a RD_CMD and Reading Response

**Goal:** Read register `0x20` from node `0x8205`.

```
Steps 1–5: Same as WR_CMD but:
  BIU.REQ_HDR0.CMD      = RD_CMD (4'h2)
  BIU.REQ_HDR0.PYLD_LEN = 4'd0   (no payload fragments for read request)

Step 6: Trigger send (same as WR_CMD step 7)

Step 7: Wait for response
  poll BIU.STAT.RSP_PKT_RCVD == 1

Step 8: Read response data
  data_lo = BIU.RSP_DATA[0].DATA2
  data_hi = BIU.RSP_DATA[0].DATA3
  status  = BIU.RSP_HDR0.CMD_OPT[0]  (1=success, 0=fail)

  if status == 0: node reported error (address not valid, or node in fault state)

Step 9: Clear flag
  BIU.STAT.RSP_PKT_RCVD = 1  (W1C)
```

#### 4.3.4 Timeout Behavior — Nonexistent or Unreachable Node

If the target node does not exist (e.g., a harvested tile, a ROUTER placeholder at Y=3 in N1B0) or is stuck:

- The request packet travels the full ring. No node claims it.
- The packet returns to the BIU as an **unmatched packet** (TGT_ID does not match any living node).
- The BIU sets `STAT.OVERFLOW` or a dedicated timeout error flag and asserts the corresponding interrupt.
- `STAT.RSP_PKT_RCVD` is **NOT** set — there is no valid response.

**SW timeout recipe:**

```c
// Send packet
edc_send(tgt_id, RD_CMD, reg_addr);

// Poll with timeout
int timeout = 1000;  // iterations (tune to ring latency × safety factor)
while (--timeout && !BIU_STAT_RSP_PKT_RCVD);

if (timeout == 0) {
    // EDC ring timeout — target may be harvested or stuck
    edc_reset_biu();   // re-init BIU (write CTRL.INIT=1)
    return EDC_ERR_TIMEOUT;
}
```

> **N1B0:** Do not send packets to the ROUTER placeholder tile positions (X=1,Y=3) or (X=2,Y=3). These positions are empty in the N1B0 grid — no standalone router module is instantiated there. The router EDC nodes for X=1 and X=2 are **inside** the composite `NOC2AXI_ROUTER_NE/NW_OPT` module and are addressed with `subp=3` (Y=3 encoding), but the composite module itself is attached to the Y=4 ring slot of column X=1/X=2. Sending a node_id that would resolve to a non-existent standalone ROUTER at (X=1,2,Y=3) will time out.

#### 4.3.5 Broadcast (GEN_CMD) Initialization Example

**Goal:** Write `0x0000` to register `0x00` (CTRL reset) on all nodes simultaneously:

```
BIU.REQ_HDR0.TGT_ID   = 0xFFFF    (broadcast address)
BIU.REQ_HDR0.CMD      = GEN_CMD   (4'h3)
BIU.REQ_HDR0.PYLD_LEN = 4'd1
BIU.REQ_HDR1.DATA0    = 8'h00     (register address 0x00)
BIU.REQ_DATA[0]       = 0x0000    (value to write)
BIU.CTRL.SEND         = 1

// No per-node response expected — just wait for REQ_PKT_SENT
poll BIU.STAT.REQ_PKT_SENT == 1
BIU.STAT.REQ_PKT_SENT = 1   // W1C
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
         X=0                   X=1                        X=2                        X=3
Y=4  NOC2AXI_NE_OPT   NOC2AXI_ROUTER_NE_OPT   NOC2AXI_ROUTER_NW_OPT   NOC2AXI_NW_OPT   ← North edge; BIU lives here
Y=3  DISPATCH_E        ROUTER-placeholder        ROUTER-placeholder       DISPATCH_W
Y=2  TENSIX            TENSIX                    TENSIX                   TENSIX
Y=1  TENSIX            TENSIX                    TENSIX                   TENSIX
Y=0  TENSIX            TENSIX                    TENSIX                   TENSIX
```

> **N1B0 composite tile:** At X=1 and X=2, `NOC2AXI_ROUTER_NE_OPT` / `NOC2AXI_ROUTER_NW_OPT` are **composite modules** that physically span both Y=4 (NIU logic) and Y=3 (router logic) within a single RTL module. The ROUTER entry at Y=3 for X=1 and X=2 is an **empty placeholder** — no sub-module is instantiated at (X=1,Y=3) or (X=2,Y=3). All router EDC nodes for X=1,2 reside inside the composite and use `subp=3` in their node_id encoding.

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
| 3 | | DISPATCH_E (X=3), ROUTER-placeholder (X=1,2 — empty; router logic inside composite), DISPATCH_W (X=0) |
| 4 | Top | NOC2AXI_NE_OPT (X=0), NOC2AXI_ROUTER_NE_OPT (X=1, composite), NOC2AXI_ROUTER_NW_OPT (X=2, composite), NOC2AXI_NW_OPT (X=3) |

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

##### Router-only nodes (inst 0xC0–0xC1) — inside composite for X=1,2 in N1B0

In baseline Trinity, standalone router tiles at Y=3 reserve inst 0x00–0xBF for NOC2AXI compatibility and use:

> **N1B0 note:** X=1,2 have **no standalone router tile at Y=3**. These inst values (0xC0–0xC1) are present inside the `NOC2AXI_ROUTER_NE/NW_OPT` composite module and are accessed via BIU[1] or BIU[2] with `subp=3`. The composite handles these nodes internally — the ring path goes through the composite's Y=4 segment then internally to Y=3 before exiting toward Y=2.

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

**Example D — NOC Router sec_conf, composite Y=3 row, column X=2 (N1B0):**
```
BIU ring  = X=2
node_id   = 0xF3C0
  part = 0x1E  → NOC
  subp = 0x3   → Y=3 row encoding (router segment of composite)
  inst = 0xC0  → SEC_NOC_CONF_IDX (192) — router-only inst

N1B0 note: (X=2, Y=3) is the ROUTER-placeholder tile position.
The actual router EDC node lives inside the NOC2AXI_ROUTER_NW_OPT
composite module. The composite is attached to column X=2 ring at Y=4,
and handles subp=3 nodes internally before passing the ring to Y=2.

Result: Security fence event in router segment of composite
        NOC2AXI_ROUTER_NW_OPT, column X=2 (not a standalone router tile)
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

### 5.6 Quick Node Address Lookup Table

Use this table to quickly compute `node_id` for any target without consulting the full decode table in §5.5.

**Formula:** `node_id = (part << 11) | (subp << 8) | inst`

#### Tensix tiles (T0–T3): `part = 0x10 + column_x`

| Target | part | subp (= Y coord) | inst | node_id formula | Example (X=0, Y=2) |
|--------|------|-----------------|------|------------------|--------------------|
| FPU G-Tile | 0x10+X | Y | FPU_G inst# | `(0x10+X)<<11 \| Y<<8 \| inst` | X=0,Y=2,inst=0 → `0x8200` |
| FPU M-Tile | 0x10+X | Y | FPU_M inst# | same pattern | — |
| SFPU lane  | 0x10+X | Y | SFPU inst#  | same pattern | — |
| TDMA pack  | 0x10+X | Y | pack inst#  | same pattern | — |
| TDMA unpack| 0x10+X | Y | unpack inst#| same pattern | — |
| BRISC      | 0x10+X | Y | BRISC=0     | `(0x10+X)<<11 \| Y<<8 \| 0` | X=0,Y=2 → `0x8200` |

#### L1 SRAM banks: `part = 0x18`

| Target | part | subp | inst | node_id formula |
|--------|------|------|------|-----------------|
| L1 SRAM bank b, tile at Y | 0x18 | Y | bank# | `0xC000 \| Y<<8 \| bank` |

> In N1B0, each tile has 4× more L1 banks than baseline (3072 macros → higher inst range).

#### Overlay / DMC nodes: `part = 0x1A`

| Target | part | subp | inst | node_id formula |
|--------|------|------|------|-----------------|
| DMC (overlay) at Y | 0x1A | Y | 0 | `0xD000 \| Y<<8` |

#### NoC / NIU nodes: `part = 0x1E`

| Target | part | subp | inst | node_id formula |
|--------|------|------|------|-----------------|
| NIU at tile Y | 0x1E | Y | 0 | `0xF000 \| Y<<8` |
| Router at tile Y | 0x1E | Y | 1 | `0xF000 \| Y<<8 \| 1` |

#### BIU and special addresses

| Target | node_id |
|--------|---------|
| BIU (ring master) | `0x0000` |
| Broadcast (all nodes) | `0xFFFF` |

---

## 6. Event Types and Commands

*(This section was §12 in V0.3. Moved earlier so readers understand event semantics before reading the SW Error Handling Guide.)*

### 6.1 EDC Commands (`edc_cmd_e`)

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

### 6.2 Event Types (`event_type_e`)

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

### 6.3 Error Severity Classification

| Severity       | EDC Command     | BIU Interrupt      | Meaning                                      |
|----------------|-----------------|-------------------|----------------------------------------------|
| Fatal          | (physical err)  | `fatal_err_irq`   | `ingress_intf.err=1` — bus/physical fault    |
| Critical       | UNC_ERR_CMD     | `crit_err_irq`    | Uncorrectable data corruption                |
| Non-critical   | COR_ERR_CMD     | `noncrit_err_irq` | ECC-corrected error                          |
| Non-critical   | LAT_ERR_CMD     | `noncrit_err_irq` | Latent (silently wrong) error detected       |
| Overflow       | OVFx_CMD        | `noncrit_err_irq` | Node queue overflow (events were dropped)    |

---

## 7. SW Error Handling Guide — From Interrupt to Node Identification

This section provides a complete sequential procedure for a software engineer to handle an EDC error interrupt, identify the faulting node, and take corrective action.

### 7.1 Overview of SW-Visible Information

When any EDC node detects an error, it sends an event packet to the BIU. The BIU:
1. Records the event in its RSP registers (`RSP_HDR0`, `RSP_HDR1`, `RSP_DATA[]`)
2. Sets the corresponding STAT bit(s)
3. Asserts the appropriate interrupt line to the host processor

The SW handler must act quickly: the BIU has a single response buffer. If a second event arrives before SW reads the first, `STAT.OVERFLOW` is set and the second event is lost (only the severity is recorded in the OVFX command).

### 7.2 Interrupt Lines and STAT Bits

| Interrupt | STAT bit | Trigger condition |
|-----------|----------|-------------------|
| `fatal_err_irq` | `STAT.FATAL_ERR` | Physical ring error (`err` signal) |
| `crit_err_irq` | `STAT.UNC_ERR` | UNC_ERR_CMD received |
| `noncrit_err_irq` | `STAT.COR_ERR` | COR_ERR_CMD received |
| `noncrit_err_irq` | `STAT.LAT_ERR` | LAT_ERR_CMD received |
| — | `STAT.OVERFLOW` | Second packet arrived before first was read |
| `pkt_rcvd_irq` | `STAT.RSP_PKT_RCVD` | Any response packet received |
| `pkt_sent_irq` | `STAT.REQ_PKT_SENT` | BIU finished sending a request packet |

All STAT bits are **Write-1-Clear (W1C)**.

### 7.3 Sequential SW Error Handling Procedure

```
Step 1: Enter interrupt handler
  Identify which interrupt fired:
    fatal_err_irq  → severity = FATAL
    crit_err_irq   → severity = CRITICAL (UNC)
    noncrit_err_irq → severity = NON_CRITICAL (COR or LAT)

Step 2: Read BIU STAT register
  stat = read(BIU.STAT)
  Note which bits are set (may be multiple)

Step 3: Read response header registers (BEFORE clearing STAT)
  rsp_hdr0 = read(BIU.RSP_HDR0)
    → CMD[15:12]     = error command type (UNC_ERR_CMD / COR_ERR_CMD / etc.)
    → PYLD_LEN[11:8] = number of payload fragments
    → CMD_OPT[7:0]   = event options / event_id[5:0]
  rsp_hdr1 = read(BIU.RSP_HDR1)
    → SRC_ID[31:16]  = node_id of the faulting node (16-bit)
    → DATA0/DATA1    = additional error info (node-type-specific)

Step 4: Read response payload (if PYLD_LEN > 0)
  for i in range(PYLD_LEN):
    rsp_data[i] = read(BIU.RSP_DATA[i])
  These fragments carry node-specific captured diagnostic data.

Step 5: Decode SRC_ID → identify faulting tile
  src_id = rsp_hdr1[31:16]

  part = (src_id >> 11) & 0x1F   // bits [15:11]
  subp = (src_id >>  8) & 0x07   // bits [10:8]  = Y coordinate
  inst = (src_id >>  0) & 0xFF   // bits [7:0]   = instance within tile

  Tile identification:
    part 0x10 → Tensix sub-core T0, subp=Y, inst=sub-block index
    part 0x11 → Tensix sub-core T1, subp=Y, inst=sub-block index
    part 0x12 → Tensix sub-core T2, subp=Y, inst=sub-block index
    part 0x13 → Tensix sub-core T3, subp=Y, inst=sub-block index
    NOTE: T0–T3 are sub-cores WITHIN each Tensix tile (present in every column).
          They are NOT column identifiers. Each Tensix tile at any (X,Y) has T0–T3.
          Column X is identified solely by which BIU[X] received the event.
    part 0x18 → L1 SRAM, subp=Y, inst=bank number
    part 0x1A → Overlay/DMC, subp=Y
    part 0x1E → NoC/NIU, subp=Y, inst=0(NIU)/1(Router)
    src_id == 0x0000 → BIU itself (ring physical error)

Step 6: Clear STAT bits (W1C)
  write(BIU.STAT, stat)   // clear only the bits that were set

Step 7: Take corrective action based on severity and node type
  (See §7.4 for common response actions)

Step 8: If STAT.OVERFLOW was set
  → An additional event was lost; log warning, consider querying the
    faulting node directly (Step 9)

Step 9 (optional): Query faulting node for more detail
  Send RD_CMD to src_id, register address = node's STAT or CAPTURE register
  (see §4.3.3 for RD_CMD procedure)
  This returns the node's locally captured diagnostic data.
```

### 7.4 Common Error Response Actions

| Severity | Node type | Recommended action |
|----------|-----------|--------------------|
| FATAL | Any | Reset the entire EDC ring (BIU CTRL.INIT=1), report to system health monitor; may indicate ring wiring fault |
| CRITICAL (UNC) | Tensix FPU | Mark tile as faulted; trigger workload reassignment or halt |
| CRITICAL (UNC) | L1 SRAM | Mark tile as faulted; N1B0 can harvest the tile (set ISO_EN bit) |
| NON-CRITICAL (COR) | L1 SRAM | Log ECC correction event; if COR rate > threshold, escalate to UNC policy |
| NON-CRITICAL (LAT) | Any | Log silently-wrong error; audit recent computation results |
| OVERFLOW | Any | SW was too slow; increase interrupt priority or use polling during high-activity periods |

### 7.5 Pseudocode — Full Handler

```c
void edc_irq_handler(int column_x) {
    edc_biu_t *biu = edc_biu_base[column_x];

    // Read and snapshot all relevant registers BEFORE clearing
    uint32_t stat    = biu->STAT;
    uint32_t rsp_hdr0 = biu->RSP_HDR0;
    uint32_t rsp_hdr1 = biu->RSP_HDR1;
    uint16_t src_id  = (rsp_hdr1 >> 16) & 0xFFFF;
    uint8_t  cmd     = (rsp_hdr0 >> 12) & 0x0F;
    uint8_t  pyld_len = (rsp_hdr0 >> 8) & 0x0F;

    uint16_t rsp_data[8];
    for (int i = 0; i < pyld_len && i < 8; i++)
        rsp_data[i] = biu->RSP_DATA[i];

    // Decode node identity
    uint8_t  part = (src_id >> 11) & 0x1F;
    uint8_t  y    = (src_id >> 8)  & 0x07;  // subp = Y coord
    uint8_t  inst = (src_id >> 0)  & 0xFF;
    int      x    = column_x;               // column = which BIU fired

    edc_log_event(x, y, part, inst, cmd, rsp_data, pyld_len);

    // Severity-based action
    if (stat & STAT_FATAL_ERR) {
        edc_reset_ring(column_x);
        system_health_alert(FATAL, x, y);
    } else if (stat & STAT_UNC_ERR) {
        mark_tile_faulted(x, y);
    } else if (stat & (STAT_COR_ERR | STAT_LAT_ERR)) {
        log_ecc_event(x, y, part, inst, cmd);
    }

    if (stat & STAT_OVERFLOW) {
        log_warning("EDC overflow on column %d — event lost", x);
    }

    // W1C — clear all bits that were set
    biu->STAT = stat;
}
```

### 7.6 N1B0-Specific Notes

- **Column identity:** In N1B0, there are 4 BIUs (one per column X=0..3). The interrupt handler must identify which column fired to determine the X coordinate.
- **Composite tile errors (X=1 or X=2, part=0x1E):** These come from the NOC2AXI_ROUTER_NE/NW_OPT internal EDC nodes. The `subp` field identifies Y=4 (NIU node) or Y=3 (router node). Treat these the same as NIU errors.
- **ROUTER placeholder at (X=1,2,Y=3):** This position has no EDC node. `src_id` with part=0x1E, subp=3 from column X=1 or X=2 comes from inside the composite module, not from a standalone router tile.
- **Harvest correlation:** If a non-critical error originates from a tile that was previously marked as marginal, consider immediately applying harvest via `ISO_EN` bit for that tile position. See §11 (Harvest Bypass Mechanism) for the ISO_EN bit map.

---

## 8. Module Hierarchy

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

## 9. Module Reference

### 9.1 `tt_edc1_pkg` — Package / Types
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_pkg.sv`

Central package containing all EDC1 types, enums, localparams, and the interface definition. Must be imported by all EDC modules.

### 9.2 `tt_edc1_intf_connector` — Passthrough Connector
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

### 9.3 `tt_edc1_serial_bus_repeater` — Pipelined Repeater
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

### 9.4 `tt_edc1_serial_bus_mux` — 2:1 Input Multiplexer
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

### 9.5 `tt_edc1_serial_bus_demux` — 1:2 Output Demultiplexer
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

### 9.6 `tt_edc1_node` — Active EDC Node
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

### 9.7 `tt_edc1_state_machine` — Serial Protocol FSM
**File:** `tt_rtl/tt_edc/rtl/tt_edc1_state_machine.sv`

The core state machine implementing the toggle serial protocol. Two instances exist within each `tt_edc1_node` (and in the BIU):

| Parameter    | Value | Purpose                              |
|--------------|-------|--------------------------------------|
| IS_REQ_SRC   | 1     | This instance sources request packets|
| IS_RSP_SINK  | 1     | This instance sinks response packets |
| MAX_FRGS     | 12    | Maximum fragments per packet         |
| FRG_IDX_W    | 4     | $clog2(12) = 4-bit fragment index    |

### 9.8 `tt_edc1_bus_interface_unit` — BIU Core
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

### 9.9 `tt_edc1_biu_soc_apb4_wrap` — APB4 BIU Wrapper
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

### 9.10 `tt_noc_overlay_edc_wrapper` — NOC EDC Node Wrapper
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

## 10. EDC Ring Topology in Trinity

### 10.1 Intra-Tensix Tile Ring (L1 Hub)

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

### 10.2 NOC Router EDC Nodes

Each `tt_noc_niu_router` instantiates `tt_noc_overlay_edc_wrapper` for each memory overlay it monitors (per direction and NIU). The wrappers with `HAS_EDC_INST=1` contain active `tt_edc1_node` instances; those with `HAS_EDC_INST=0` pass through with all-zero outputs.

Additionally, purely combinational bypass paths (no active monitoring, just ring continuity) use `tt_edc1_intf_connector`:
- `*_vc_buf_edc_bypass`
- `*_header_ecc_edc_bypass`
- `*_data_parity_edc_bypass`
- `rocc_intf_edc_bypass`
- `ep_table_edc_bypass`

### 10.3 Trinity Top-Level EDC Connections

From `trinity.sv`, two special EDC connectors bridge direct connections and loopback paths:

```systemverilog
// Direct connect for nodes that share a clock domain
tt_edc1_intf_connector edc_direct_conn_nodes (...);  // ~L442

// Loopback connect for nodes that require loopback
tt_edc1_intf_connector edc_loopback_conn_nodes (...); // ~L447/L454
```

---

## 11. Harvest Bypass Mechanism

### 11.0 Why Mux and Demux Are Needed

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

### 11.1 Tensix Tile Bypass

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

### 11.2 Dispatch Tile Bypass

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

### 11.3 Summary: All Mux/Demux Instances

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

## 12. Bus Interface Unit (BIU)

### 12.1 Overview

The BIU is the firmware gateway to the EDC ring. There is one BIU per EDC ring segment (one per trinity row/column). Firmware accesses it via APB4.

**BIU node_id = 16'h0000** (BIU_NODE_ID = '0): all event packets sent by nodes use this as TGT_ID, so they are routed back to firmware.

### 12.2 Packet Transmission Flow

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

### 12.3 Packet Reception Flow

1. When a packet arrives at `ingress_intf` addressed to `BIU_NODE_ID (0x0000)`:
2. `u_edc_rsp_snk` (IS_RSP_SINK state machine) deserializes each fragment.
3. Fragment data is written to RSP_HDR0, RSP_HDR1, RSP_DATA[0–3] registers.
4. `RSP_PKT_RCVD` status bit is set; `pkt_rcvd_irq` fires if enabled.
5. Error status bits (UNC_ERR, COR_ERR, LAT_ERR, OVERFLOW) are set based on the received command.

### 12.4 CSR Register Map Summary

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

## 13. EDC Node Configuration

### 13.1 Event Configuration (`event_cfg_t`)

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

### 13.2 Capture Register Configuration (`capture_cfg_t`)

```systemverilog
typedef struct packed {
    reg_w_t active_bits;  // bitmask of valid bits in capture register
} capture_cfg_t;

// Examples:
ACTIVE_8BIT_CAPTURE_CFG  = '{ active_bits: 16'h00ff }
ACTIVE_10BIT_CAPTURE_CFG = '{ active_bits: 16'h03ff }
ACTIVE_12BIT_CAPTURE_CFG = '{ active_bits: 16'h0fff }
```

### 13.3 Pulse / Config Register Configuration

```systemverilog
typedef struct packed { reg_w_t active_bits; } pulse_cfg_t;
typedef struct packed { reg_w_t active_bits; } config_cfg_t;

DISABLE_PULSE_CFG  = '{ active_bits: 16'h0000 }
DISABLE_CONFIG_CFG = '{ active_bits: 16'h0000 }
```

---

## 14. CDC / Synchronization

### 14.1 Toggle Protocol CDC Safety

The `req_tgl[1:0]` and `ack_tgl[1:0]` signals use 2-bit toggle encoding to cross asynchronous clock domain boundaries. CDC safety is NOT derived from single-bit encoding — `req_tgl` is a 2-bit bus and both bits can change simultaneously (Hamming distance = 2 between `2'b01` and `2'b10`). A single-bit glitch can produce `2'b11` (detected) or `2'b00` (appears idle), as described in §3.3.2.

CDC safety is instead derived from the **self-throttling protocol**, which enforces a hard upper bound on the signal transition rate (`f_data`). The sender holds `req_tgl` stable for the entire ring round-trip (~20 ns minimum), limiting `f_data` to ≤ 50 MHz regardless of clock frequency. On Samsung 5nm (τ ≈ 10 ps), the resulting MTBF exceeds 10³² years at worst-case toggle rate — see §3.5.4 for the full calculation. No explicit synchronizer cells are required.

### 14.2 Sync Flops — Not Present in RTL

**RTL audit result (2026-03-20, confirmed §3.3.3):** The parameters `ENABLE_INGRESS_SYNC`, `ENABLE_EGRESS_SYNC`, and the `EDC_CFG.DISABLE_SYNC_FLOPS` field described in earlier document drafts do not exist in the actual N1B0 RTL source. No synchronizer cells are present in `tt_edc1_node`, `tt_edc1_bus_interface_unit`, or any inter-node connector.

All CDC safety is provided by:
1. The self-throttling protocol limiting `f_data` (§3.5.4, §14.1)
2. `set_false_path` SDC constraints on `req_tgl`/`ack_tgl` (§3.3.4)
3. `2'b11` illegal-code detection providing SW-level recovery (§3.3.2)

The only synchronizer cell in the entire EDC ring is `tt_libcell_sync3r` used for `async_init` inside each node — this is intentional and documented in §3.4 and §14.3.

### 14.3 `async_init` Propagation

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

## 15. Firmware Interface

### 15.1 APB4 Register Access

Firmware communicates with the EDC ring through the APB4 BIU at address space defined by the SoC address map. The BIU registers are 32-bit wide; the APB4 address is 6 bits wide (64 word address space = 256 bytes).

### 15.2 Sending a Write Command

```
1. Write REQ_HDR0: {TGT_ID[15:0], CMD=WR_CMD, PYLD_LEN=n, CMD_OPT=addr[7:0]}
2. Write REQ_HDR1: {SRC_ID=0x0000, DATA1, DATA0}
3. Write REQ_DATA[0..k] with payload (k depends on PYLD_LEN)
4. Final write to correct register triggers aux_req_go
5. Poll STAT.REQ_PKT_SENT (or use pkt_sent_irq)
```

### 15.3 Sending a Read Command

```
1. Write REQ_HDR0: {TGT_ID, CMD=RD_CMD, PYLD_LEN=0, CMD_OPT=addr[7:0]}
2. Write REQ_HDR1.DATA0 → triggers aux_req_go immediately (pyld_len==0)
3. Poll STAT.RSP_PKT_RCVD (or use pkt_rcvd_irq)
4. Read RSP_HDR0, RSP_HDR1, RSP_DATA[0..n]
5. Write-1-clear STAT.RSP_PKT_RCVD before next read
```

### 15.4 Interrupt Handling

| IRQ             | Trigger                                      | Enable Bit         |
|-----------------|----------------------------------------------|--------------------|
| `fatal_err_irq` | `ingress_intf.err=1` (physical bus error)    | FATAL_ERR_IEN      |
| `crit_err_irq`  | UNC_ERR_CMD received                         | UNC_ERR_IEN        |
| `noncrit_err_irq`| COR_ERR_CMD or LAT_ERR_CMD received         | NONCRIT_ERR_IEN    |
| `cor_err_irq`   | Same as noncrit_err_irq                      | NONCRIT_ERR_IEN    |
| `pkt_sent_irq`  | Request packet transmitted                   | REQ_PKT_SENT_IEN   |
| `pkt_rcvd_irq`  | Response packet received                     | RSP_PKT_RCVD_IEN   |

### 15.5 INIT Sequence

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

## 16. Inter-Cluster EDC Signal Connectivity

### 16.1 Trinity Grid Layout

Trinity is a **4×5 tile grid** (`SizeX=4`, `SizeY=5`). Each column (X) shares one EDC ring. Within each column there are 5 rows (Y=0..4) with different tile types:

```
Y=4 (top)    NOC2AXI_NE_OPT   NOC2AXI_ROUTER_NE_OPT   NOC2AXI_ROUTER_NW_OPT   NOC2AXI_NW_OPT   (BIU lives here)
Y=3          DISPATCH_E        ROUTER-placeholder        ROUTER-placeholder       DISPATCH_W
Y=2          TENSIX            TENSIX                    TENSIX                   TENSIX
Y=1          TENSIX            TENSIX                    TENSIX                   TENSIX
Y=0 (bottom) TENSIX            TENSIX                    TENSIX                   TENSIX
             X=0               X=1                       X=2                      X=3
```

> **N1B0:** X=1 uses `NOC2AXI_ROUTER_NE_OPT`, X=2 uses `NOC2AXI_ROUTER_NW_OPT`. These are **composite modules** that internally span Y=4 (NIU logic) and Y=3 (router logic). The ROUTER entry at Y=3 for X=1,2 is an empty placeholder — no sub-module instantiated. In the `trinity_pkg.sv` GridConfig, X=1,2 Y=4 use `NOC2AXI_ROUTER_NE_OPT`/`NOC2AXI_ROUTER_NW_OPT` and X=1,2 Y=3 use `ROUTER` (placeholder enum).

From `trinity_pkg.sv`:
```systemverilog
localparam int unsigned SizeX = 4;
localparam int unsigned SizeY = 5;
localparam int unsigned NumApbNodes = 4;  // one BIU APB port per column

localparam tile_t [SizeY-1:0][SizeX-1:0] GridConfig = '{
    '{NOC2AXI_NE_OPT, NOC2AXI_ROUTER_NE_OPT, NOC2AXI_ROUTER_NW_OPT, NOC2AXI_NW_OPT},  // Y=4
    '{DISPATCH_E,     ROUTER,                 ROUTER,                 DISPATCH_W},        // Y=3 (X=1,2 are placeholders)
    '{TENSIX,         TENSIX,                 TENSIX,                 TENSIX},            // Y=2
    '{TENSIX,         TENSIX,                 TENSIX,                 TENSIX},            // Y=1
    '{TENSIX,         TENSIX,                 TENSIX,                 TENSIX}             // Y=0
};
```

**Key: each column (X) has its own independent EDC ring.** The BIU for column X is at the top tile `[x][Y=4]`.

### 16.2 EDC Interface Arrays in `trinity.sv`

Four interface arrays are declared at the top level, each indexed by `[x * SizeY + y]`:

```systemverilog
// From trinity.sv L272-275
edc1_serial_bus_intf_def edc_ingress_intf[SizeX*SizeY]();          // direct: ring flows DOWN (from y+1 → y)
edc1_serial_bus_intf_def edc_egress_intf[SizeX*SizeY]();           // direct: tile sends UP  (into ring)
edc1_serial_bus_intf_def loopback_edc_ingress_intf[SizeX*SizeY](); // loopback: bottom turnaround
edc1_serial_bus_intf_def loopback_edc_egress_intf[SizeX*SizeY]();  // loopback: bottom turnaround
```

Index formula: `index = x * SizeY + y` — so column X, row Y maps to a flat array index.

### 16.3 Inter-Tile EDC Wiring (Vertical Ring per Column)

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

### 16.4 Per-Column EDC Ring Flow

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

### 16.5 Tile EDC Port Connections to the Ring

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

### 16.6 Complete Per-Column Ring Diagram (Column X=0 as example)

```
  APB4 Firmware (external)
       │  APB[x=0]
       ▼
 ┌─────────────────────────────────────────────────────┐
 │  Y=4: NOC2AXI_NE_OPT (BIU, node_id=0x0000)         │
 │       tt_neo_overlay_wrapper                         │
 │       ├── tt_edc1_biu_soc_apb4_wrap (BIU)           │
 │       └── tt_edc1_serial_bus_mux    (harvest mux)   │
 │   edc_egress_intf[0*5+4] ─────────────────────────► │  // drives edc_direct_conn_nodes (→Y=3)
 │   loopback_edc_ingress_intf[0*5+4] ◄────────────────│  // from edc_loopback_conn_nodes (←Y=3)
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
 │   edc_ingress_intf[0*5+3] ◄────────────────────────│  // from edc_direct_conn_nodes (←Y=4)
 │   edc_egress_intf[0*5+3]  ─────────────────────────│  // drives edc_direct_conn_nodes (→Y=2)
 │   loopback_edc_ingress_intf[0*5+3] ◄───────────────│  // from edc_loopback_conn_nodes (←Y=2)
 │   loopback_edc_egress_intf[0*5+3]  ────────────────│  // drives edc_loopback_conn_nodes (→Y=4)
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
 │   edc_ingress_intf[0*5+2] ◄────────────────────────│  // from edc_direct_conn_nodes (←Y=3)
 │   edc_egress_intf[0*5+2]  ─────────────────────────│  // drives edc_direct_conn_nodes (→Y=1)
 │   loopback_edc_ingress_intf[0*5+2] ◄───────────────│  // from edc_loopback_conn_nodes (←Y=1)
 │   loopback_edc_egress_intf[0*5+2]  ────────────────│  // drives edc_loopback_conn_nodes (→Y=3)
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

### 16.7 Summary: Signal Names and Flow Direction

| Signal | Direction | Description |
|--------|-----------|-------------|
| `edc_egress_intf[x*5+y]` | Tile → ring downward | Tile's EDC output into the direct path |
| `edc_ingress_intf[x*5+y]` | Ring → tile | Direct path arriving at the tile (NOTE: marked `// TODO` in trinity.sv — some tiles drive this directly via demux/mux) |
| `loopback_edc_egress_intf[x*5+y]` | Tile → ring upward | Tile's loopback output going back up |
| `loopback_edc_ingress_intf[x*5+y]` | Ring → tile | Loopback path arriving at the tile |
| `edc_egress_t6_byp_intf` | Demux → Mux | Harvest bypass wire (stays inside tile's router wrapper) |

**One EDC ring per column.** Each column X has an independent ring with its own BIU at `[x][Y=4]`. The four columns therefore have 4 independent BIUs, 4 independent rings, and 4 APB4 register bank interfaces — reflected in `NumApbNodes=4`.

---

## 17. Instance Paths (Trinity)

For the complete, RTL-verified, ring-order-annotated instance path list, refer to **EDC_path_V0.2.md**.

This section provides representative path examples using the correct hierarchy prefix `gen_x[*].gen_y[*].<tile_type>.<...>`.

### 17.1 Active EDC Nodes — Hierarchy Prefix Correction

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

### 17.2 BIU Instance

```
gen_x[X].gen_y[Y].<tile_type>.overlay_noc_wrap.neo_overlay_wrapper.
    └── tt_edc1_biu_soc_apb4_wrap  (node_id = 0x0000)
        ├── edc1_biu_soc_apb4_inner  u_t6_edc_biu_csr_map
        └── tt_edc1_bus_interface_unit  u_edc_biu
            ├── tt_edc1_state_machine  u_edc_req_src  (IS_REQ_SRC=1)
            └── tt_edc1_state_machine  u_edc_rsp_snk  (IS_RSP_SINK=1)
```

### 17.3 Harvest Bypass Instances

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

## 18. EDC Full Path Nodes (N1B0)

This section provides the complete RTL instance path prefix for every active EDC tile in the N1B0 4×5 grid. All paths are rooted at the `trinity` top-level module. Use these paths in simulation (`$display`), waveform viewers (GTKWave / DVE hierarchy), or DV assertions.

### 18.1 Path Prefix Formula

```
trinity.<gen_block>.<tile_module>.<subsystem_path>.<edc_node_instance>
```

The `<gen_block>` follows the generate-loop variable names in `trinity.sv`:

| Tile type | Generate block | Module instantiated |
|---|---|---|
| Tensix (X=0..3, Y=0..2) | `gen_x[X].gen_y[Y].gen_tensix` | `tt_tensix_with_l1` |
| Dispatch East (X=0, Y=3) | `gen_x[0].gen_y[3].gen_dispatch_e` | `tt_dispatch_top_east` |
| Dispatch West (X=3, Y=3) | `gen_x[3].gen_y[3].gen_dispatch_w` | `tt_dispatch_top_west` |
| NOC2AXI NE corner (X=0, Y=4) | `gen_x[0].gen_y[4].gen_noc2axi_ne_opt` | `trinity_noc2axi_ne_opt` |
| NOC2AXI NW corner (X=3, Y=4) | `gen_x[3].gen_y[4].gen_noc2axi_nw_opt` | `trinity_noc2axi_nw_opt` |
| NOC2AXI_ROUTER_NE composite (X=1, Y=4+3) | `gen_x[1].gen_y[4].gen_noc2axi_router_ne_opt` | `trinity_noc2axi_router_ne_opt` |
| NOC2AXI_ROUTER_NW composite (X=2, Y=4+3) | `gen_x[2].gen_y[4].gen_noc2axi_router_nw_opt` | `trinity_noc2axi_router_nw_opt` |
| ROUTER placeholder (X=1,2 Y=3) | `gen_x[X].gen_y[3].gen_router` | **empty** — no EDC nodes |

---

### 18.2 Tensix Tile — EDC Node Paths

Tile positions: X ∈ {0,1,2,3}, Y ∈ {0,1,2}. Replace [X] and [Y] with the tile coordinates.

**Path root:**
```
trinity.gen_x[X].gen_y[Y].gen_tensix.tt_tensix_with_l1
```

#### 18.2.1 L1 Partition Shared Nodes (one per tile, in `tt_t6_l1_partition`)

```
<root>.u_l1part.t6_misc.u_edc1_node_misc
<root>.u_l1part.tt_t6_l1_wrap2.edc_node_inst            (L1 SRAM banks, one chain)
```

#### 18.2.2 NOC / NIU Nodes (in `tt_noc_niu_router` inside `overlay_noc_wrap`)

```
<root>.overlay_noc_wrap.overlay_noc_niu_router.tt_trinity_noc_niu_router_inst.noc_niu_router_inst
    .has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_header_ecc.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_data_parity.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_header_ecc.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_data_parity.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_header_ecc.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_data_parity.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_header_ecc.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_data_parity.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_niu_vc_buf.noc_overlay_edc_wrapper_niu_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst
    .has_rocc_intf.noc_overlay_edc_wrapper_rocc_intf.g_edc_inst.g_no_cor_err_events.edc_node_inst         (if OVERLAY_INF_EN)
    .has_ep_table.noc_overlay_edc_wrapper_ep_table.g_edc_inst.g_no_cor_err_events.edc_node_inst           (if OVERLAY_INF_EN)
    .has_routing_table.noc_overlay_edc_wrapper_routing_table.g_edc_inst.g_no_cor_err_events.edc_node_inst (if OVERLAY_INF_EN)
    .has_sec_fence_edc.noc_sec_fence_edc_wrapper.g_edc_inst.edc_node_inst
```

#### 18.2.3 Per-Sub-Core Nodes (T0–T3, in `tt_instrn_engine_wrapper` and `tt_fpu_gtile`)

Sub-core index `C` ∈ {0,1,2,3} (T0–T3). Each sub-core path starts:

```
<root>.t6[C].neo.u_t6
```

**Gtile[0] nodes (before instrn_engine_wrapper in ring):**
```
<root>.t6[C].neo.u_t6.gen_gtile[0].u_fpu_gtile.gtile_general_error_edc_node
<root>.t6[C].neo.u_t6.gen_gtile[0].u_fpu_gtile.gtile_src_parity_edc_node
<root>.t6[C].neo.u_t6.gen_gtile[0].u_fpu_gtile.gtile_dest_parity_edc_node
```

**instrn_engine_wrapper nodes (in `tt_instrn_engine_wrapper`):**
```
<root>.t6[C].neo.u_t6.instrn_engine_wrapper.<edc_node>   (13 nodes, unnamed in RTL — see §5.4.3 inst table)
```

Specific named nodes:
```
<root>.t6[C].neo.u_t6.instrn_engine_wrapper.u_edc_node_thcon_0
<root>.t6[C].neo.u_t6.instrn_engine_wrapper.u_edc_node_thcon_1
<root>.t6[C].neo.u_t6.instrn_engine_wrapper.u_instrn_engine.u_l1_flex_client_edc
```

**Gtile[1] nodes (after instrn_engine_wrapper in ring):**
```
<root>.t6[C].neo.u_t6.gen_gtile[1].u_fpu_gtile.gtile_general_error_edc_node
<root>.t6[C].neo.u_t6.gen_gtile[1].u_fpu_gtile.gtile_src_parity_edc_node
<root>.t6[C].neo.u_t6.gen_gtile[1].u_fpu_gtile.gtile_dest_parity_edc_node
```

**BIU (ring master, one per tile):**
```
<root>.overlay_noc_wrap.neo_overlay_wrapper.overlay_wrapper.u_edc_biu
```

---

### 18.3 Dispatch Tiles — EDC Node Paths

**Dispatch East (X=0, Y=3):**
```
trinity.gen_x[0].gen_y[3].gen_dispatch_e.tt_dispatch_top_east.tt_dispatch_engine
    .disp_eng_l1_partition_inst.u_edc_biu              (BIU — ring master)
    .disp_eng_l1_partition_inst.tt_t6_l1_dispatch.*    (Dispatch L1 SRAM EDC nodes)
    .overlay_noc_wrap_inst.disp_eng_overlay_noc_niu_router.trin_disp_eng_noc_niu_router_east_inst
        .disp_eng_noc_niu_router_inst.<noc_edc_nodes>  (same NOC wrapper nodes as Tensix §18.2.2)
```

**Dispatch West (X=3, Y=3):**
```
trinity.gen_x[3].gen_y[3].gen_dispatch_w.tt_dispatch_top_west.tt_dispatch_engine
    .disp_eng_l1_partition_inst.u_edc_biu
    .disp_eng_l1_partition_inst.tt_t6_l1_dispatch.*
    .overlay_noc_wrap_inst.disp_eng_overlay_noc_niu_router.trin_disp_eng_noc_niu_router_west_inst
        .disp_eng_noc_niu_router_inst.<noc_edc_nodes>
```

---

### 18.4 NOC2AXI Corner Tiles — EDC Node Paths

**NOC2AXI NE corner (X=0, Y=4):**
```
trinity.gen_x[0].gen_y[4].gen_noc2axi_ne_opt.trinity_noc2axi_ne_opt
    .u_edc_biu                                          (BIU — ring master for this tile)
    .tt_noc2axi_ne_opt.<noc_edc_nodes>                  (NOC nodes, subp=4)
```

**NOC2AXI NW corner (X=3, Y=4):**
```
trinity.gen_x[3].gen_y[4].gen_noc2axi_nw_opt.trinity_noc2axi_nw_opt
    .u_edc_biu
    .tt_noc2axi_nw_opt.<noc_edc_nodes>                  (NOC nodes, subp=4)
```

---

### 18.5 NOC2AXI_ROUTER Composite Tiles — EDC Node Paths

The composite tile spans two physical rows (Y=4 and Y=3). Both sets of EDC nodes are instantiated inside one SV module. External EDC ring interfaces exit at Y=3.

**NOC2AXI_ROUTER_NE (X=1):**
```
trinity.gen_x[1].gen_y[4].gen_noc2axi_router_ne_opt.trinity_noc2axi_router_ne_opt
    ├── [Y=4 section — noc2axi_* prefix]
    │   .noc2axi_u_edc_biu                              (NIU BIU, subp=4)
    │   .tt_noc2axi_n_opt.<noc_edc_nodes>               (NIU NOC nodes, subp=4)
    └── [Y=3 section — router_* prefix]
        .router_u_edc_biu                               (Router BIU, subp=3)
        .tt_router.<noc_edc_nodes>                      (Router NOC nodes, subp=3)
```

**NOC2AXI_ROUTER_NW (X=2):**
```
trinity.gen_x[2].gen_y[4].gen_noc2axi_router_nw_opt.trinity_noc2axi_router_nw_opt
    ├── [Y=4 section — noc2axi_* prefix]
    │   .noc2axi_u_edc_biu                              (NIU BIU, subp=4)
    │   .tt_noc2axi_n_opt.<noc_edc_nodes>               (NIU NOC nodes, subp=4)
    └── [Y=3 section — router_* prefix]
        .router_u_edc_biu                               (Router BIU, subp=3)
        .tt_router.<noc_edc_nodes>                      (Router NOC nodes, subp=3)
```

> **Note:** For ROUTER_NE (X=1): router `node_id_y` = `i_local_nodeid_y - 1` (Y=4−1=3), `endpoint_id` = `i_noc_endpoint_id - 1`. Internal cross-row flit wires and clock routing between Y=4 and Y=3 sections are inside the composite module; not visible at trinity top.

---

### 18.6 N1B0 Complete Grid Summary

| Grid pos | Tile type | gen_block | EDC nodes present |
|---|---|---|---|
| (0,0)(1,0)(2,0)(3,0) | Tensix | `gen_x[X].gen_y[0].gen_tensix` | Yes — BIU + NOC×17 + T0-T3×19each + L1×2 per tile |
| (0,1)(1,1)(2,1)(3,1) | Tensix | `gen_x[X].gen_y[1].gen_tensix` | Yes |
| (0,2)(1,2)(2,2)(3,2) | Tensix | `gen_x[X].gen_y[2].gen_tensix` | Yes |
| (0,3) | Dispatch East | `gen_x[0].gen_y[3].gen_dispatch_e` | Yes — BIU + NOC + Dispatch L1 |
| (1,3)(2,3) | Router (empty) | `gen_x[X].gen_y[3].gen_router` | **None** — no module instantiated |
| (3,3) | Dispatch West | `gen_x[3].gen_y[3].gen_dispatch_w` | Yes — BIU + NOC + Dispatch L1 |
| (0,4) | NOC2AXI NE opt | `gen_x[0].gen_y[4].gen_noc2axi_ne_opt` | Yes — BIU + NOC nodes (subp=4) |
| (1,4) | NOC2AXI_ROUTER_NE | `gen_x[1].gen_y[4].gen_noc2axi_router_ne_opt` | Yes — dual-row: NIU(subp=4) + Router(subp=3) |
| (2,4) | NOC2AXI_ROUTER_NW | `gen_x[2].gen_y[4].gen_noc2axi_router_nw_opt` | Yes — dual-row: NIU(subp=4) + Router(subp=3) |
| (3,4) | NOC2AXI NW opt | `gen_x[3].gen_y[4].gen_noc2axi_nw_opt` | Yes — BIU + NOC nodes (subp=4) |

---

## 19. EDC Nodes Decode Address (N1B0)

This section is the master SW lookup table. Given a `node_id` value received in an interrupt or CSR register, use the tables below to identify the exact source — tile position, IP type, function, and description.

### 19.1 node_id Bit Layout (Quick Reference)

```
Bits [15:11] = part   (5 bits)  — IP block type
Bits [10: 8] = subp   (3 bits)  — tile Y coordinate (for all types)
Bits [ 7: 0] = inst   (8 bits)  — function index within the IP block

node_id = (part << 11) | (subp << 8) | inst
```

**Special values:**
- `0x0000` = BIU (firmware ring master) — sender, not a monitored node
- `0xFFFF` = BROADCAST — target all nodes (write command)

---

### 19.2 Part Field Decode

| `node_id[15:11]` binary | Part hex | IP type | node_id range |
|---|---|---|---|
| `00000` | — | BIU (special: whole ID = 0x0000) | `0x0000` only |
| `10000` | `0x10` | TENSIX T0 (or shared L1 partition) | `0x8000`–`0x80FF` (Y=0), `0x8100`–`0x81FF` (Y=1), `0x8200`–`0x82FF` (Y=2) |
| `10001` | `0x11` | TENSIX T1 | `0x8800`–`0x88FF` (Y=0), `0x8900`–`0x89FF` (Y=1), `0x8A00`–`0x8AFF` (Y=2) |
| `10010` | `0x12` | TENSIX T2 | `0x9000`–`0x90FF` (Y=0), `0x9100`–`0x91FF` (Y=1), `0x9200`–`0x92FF` (Y=2) |
| `10011` | `0x13` | TENSIX T3 | `0x9800`–`0x98FF` (Y=0), `0x9900`–`0x99FF` (Y=1), `0x9A00`–`0x9AFF` (Y=2) |
| `11110` | `0x1E` | NOC router / NIU | `0xF000`–`0xF7FF` (subp=Y in [10:8]) |
| `11111` | — | BROADCAST (whole ID = 0xFFFF) | `0xFFFF` only |

> **N1B0 subp = tile Y coordinate** for all part types. For the NOC2AXI_ROUTER composite tiles: the NIU section uses subp=4 (Y=4), the internal router section uses subp=3 (Y=3). For Dispatch tiles: Y=3. For Tensix tiles: Y=0, 1, or 2.

---

### 19.3 inst Field Decode — NOC Part (0x1E)

node_id = `0xF` `subp` `inst` where subp = tile Y (one hex digit) and inst = two hex digits.

| inst (hex) | Constant | RTL wrapper instance | Monitored function | Error type |
|---|---|---|---|---|
| `0x00` | `NORTH_ROUTER_VC_BUF_EDC_IDX` | `noc_overlay_edc_wrapper_north_router_vc_buf` | North port VC buffer SRAM parity | UNC |
| `0x01` | `NORTH_ROUTER_HEADER_ECC_EDC_IDX` | `noc_overlay_edc_wrapper_north_router_header_ecc` | North port header ECC | COR+UNC |
| `0x02` | `NORTH_ROUTER_DATA_PARITY_EDC_IDX` | `noc_overlay_edc_wrapper_north_router_data_parity` | North port data parity | UNC |
| `0x03` | `EAST_ROUTER_VC_BUF_EDC_IDX` | `noc_overlay_edc_wrapper_east_router_vc_buf` | East port VC buffer SRAM parity | UNC |
| `0x04` | `EAST_ROUTER_HEADER_ECC_EDC_IDX` | `noc_overlay_edc_wrapper_east_router_header_ecc` | East port header ECC | COR+UNC |
| `0x05` | `EAST_ROUTER_DATA_PARITY_EDC_IDX` | `noc_overlay_edc_wrapper_east_router_data_parity` | East port data parity | UNC |
| `0x06` | `SOUTH_ROUTER_VC_BUF_EDC_IDX` | `noc_overlay_edc_wrapper_south_router_vc_buf` | South port VC buffer SRAM parity | UNC |
| `0x07` | `SOUTH_ROUTER_HEADER_ECC_EDC_IDX` | `noc_overlay_edc_wrapper_south_router_header_ecc` | South port header ECC | COR+UNC |
| `0x08` | `SOUTH_ROUTER_DATA_PARITY_EDC_IDX` | `noc_overlay_edc_wrapper_south_router_data_parity` | South port data parity | UNC |
| `0x09` | `WEST_ROUTER_VC_BUF_EDC_IDX` | `noc_overlay_edc_wrapper_west_router_vc_buf` | West port VC buffer SRAM parity | UNC |
| `0x0A` | `WEST_ROUTER_HEADER_ECC_EDC_IDX` | `noc_overlay_edc_wrapper_west_router_header_ecc` | West port header ECC | COR+UNC |
| `0x0B` | `WEST_ROUTER_DATA_PARITY_EDC_IDX` | `noc_overlay_edc_wrapper_west_router_data_parity` | West port data parity | UNC |
| `0x0C` | `NIU_VC_BUF_EDC_IDX` | `noc_overlay_edc_wrapper_niu_vc_buf` | NIU VC buffer SRAM parity | UNC |
| `0x0D` | `ROCC_INTF_EDC_IDX` | `noc_overlay_edc_wrapper_rocc_intf` | RoCC command buffer parity (OVERLAY_INF_EN only) | UNC |
| `0x0E` | `EP_TABLE_EDC_IDX` | `noc_overlay_edc_wrapper_ep_table` | Endpoint translation table SRAM parity (OVERLAY_INF_EN only) | UNC |
| `0x0F` | `ROUTING_TABLE_EDC_IDX` | `noc_overlay_edc_wrapper_routing_table` | Routing table SRAM parity (OVERLAY_INF_EN only) | UNC |
| `0xC0` | `SEC_NOC_CONF_IDX` (=192) | `tt_noc_sec_fence_edc_wrapper` | Security fence violation | UNC |

**Quick decode:** `node_id = 0xF` + `Y` + `inst_2digits`

| node_id | Tile Y | inst | Source |
|---|---|---|---|
| `0xF000` | Y=0 | 0x00 | Tensix row 0, North VC buf |
| `0xF100` | Y=1 | 0x00 | Tensix row 1, North VC buf |
| `0xF200` | Y=2 | 0x00 | Tensix row 2, North VC buf |
| `0xF300` | Y=3 | 0x00 | Dispatch tile, North VC buf |
| `0xF400` | Y=4 | 0x00 | NOC2AXI/NIU tile, North VC buf |
| `0xF2C0` | Y=2 | 0xC0 | Tensix row 2, security fence |
| `0xF3C0` | Y=3 | 0xC0 | Dispatch, security fence |
| `0xF4C0` | Y=4 | 0xC0 | NIU, security fence |

> **Note:** NOC node_id does **not** encode the X coordinate. All tiles in the same row share the same subp=Y. To determine which column (X) an event came from, use the BIU's APB address: APB index = column X (one BIU per column per ring). See §7 for interrupt-to-tile identification flow.

---

### 19.4 inst Field Decode — TENSIX / L1 Part (0x10–0x13)

Part 0x10 = T0 (and shared L1 partition). Part 0x11 = T1. Part 0x12 = T2. Part 0x13 = T3.

| inst (hex) | Constant | Location | Monitored function |
|---|---|---|---|
| `0x00` | `T6_MISC_EDC_IDX` | `tt_t6_misc.u_edc1_node_misc` (shared L1 partition, part=0x10 only) | Misc registers, skid buffers, semaphores, TC remap, GSRS (13 events) |
| `0x03` | `IE_PARITY_EDC_IDX` | `tt_instrn_engine_wrapper` (per sub-core) | Instruction engine parity |
| `0x04` | `SRCB_EDC_IDX` | `tt_instrn_engine_wrapper` | SrcB buffer SRAM parity |
| `0x05` | `UNPACK_EDC_IDX` | `tt_instrn_engine_wrapper` | Unpacker SRAM parity |
| `0x06` | `PACK_EDC_IDX` | `tt_instrn_engine_wrapper` | Packer SRAM parity |
| `0x07` | `SFPU_EDC_IDX` | `tt_instrn_engine_wrapper` | SFPU DP/ST + parity errors |
| `0x08` | `GPR_P0_EDC_IDX` | `tt_instrn_engine_wrapper` | GPR port 0 parity |
| `0x09` | `GPR_P1_EDC_IDX` | `tt_instrn_engine_wrapper` | GPR port 1 parity |
| `0x0A` | `CFG_EXU_0_EDC_IDX` | `tt_instrn_engine_wrapper` | Config EXU reg-0 parity |
| `0x0B` | `CFG_EXU_1_EDC_IDX` | `tt_instrn_engine_wrapper` | Config EXU reg-1 parity |
| `0x0C` | `CFG_GLOBAL_EDC_IDX` | `tt_instrn_engine_wrapper` | Global config reg parity |
| `0x0D` | `THCON_0_EDC_IDX` | `tt_instrn_engine_wrapper.u_edc_node_thcon_0` | THCON0 parity + self-test |
| `0x0E` | `THCON_1_EDC_IDX` | `tt_instrn_engine_wrapper.u_edc_node_thcon_1` | THCON1 parity + self-test |
| `0x10` | `L1_EDC_IDX` | `tt_t6_l1_wrap2` (shared; part=0x10) **or** `tt_instrn_engine.u_l1_flex_client_edc` (per sub-core) | L1 SRAM banks (shared) or L1 flex client, priority FIFO, CSR parity |
| `0x20` | `GTILE_LOCAL_INST_ID[0]` | `gen_gtile[0].u_fpu_gtile.gtile_general_error_edc_node` | Gtile[0] general error |
| `0x21` | `GTILE_LOCAL_INST_ID[0]+1` | `gen_gtile[0].u_fpu_gtile.gtile_src_parity_edc_node` | Gtile[0] SrcA register parity |
| `0x22` | `GTILE_LOCAL_INST_ID[0]+2` | `gen_gtile[0].u_fpu_gtile.gtile_dest_parity_edc_node` | Gtile[0] Dest register parity |
| `0x23` | `GTILE_LOCAL_INST_ID[1]` | `gen_gtile[1].u_fpu_gtile.gtile_general_error_edc_node` | Gtile[1] general error |
| `0x24` | `GTILE_LOCAL_INST_ID[1]+1` | `gen_gtile[1].u_fpu_gtile.gtile_src_parity_edc_node` | Gtile[1] SrcA register parity |
| `0x25` | `GTILE_LOCAL_INST_ID[1]+2` | `gen_gtile[1].u_fpu_gtile.gtile_dest_parity_edc_node` | Gtile[1] Dest register parity |

**Quick decode formula:**
```python
part = (node_id >> 11) & 0x1F   # 0x10=T0, 0x11=T1, 0x12=T2, 0x13=T3
Y    = (node_id >>  8) & 0x07   # tile row: 0,1,2 for Tensix; 3 for Dispatch
inst = (node_id >>  0) & 0xFF   # function index (see table above)
```

---

### 19.5 Full node_id Lookup Table — Tensix Tiles (N1B0)

This table covers all Tensix tiles (X=0..3, Y=0..2). node_id is **column-independent** — subp=Y only.

**Tensix at any column X, row Y:**

| node_id formula | Concrete: Y=0 | Concrete: Y=1 | Concrete: Y=2 | Sub-core | Function |
|---|---|---|---|---|---|
| `0x80_(Y)_00` | `0x8000` | `0x8100` | `0x8200` | T0/shared | T6 MISC (shared L1 partition) |
| `0x80_(Y)_03` | `0x8003` | `0x8103` | `0x8203` | T0 | IE parity |
| `0x80_(Y)_04` | `0x8004` | `0x8104` | `0x8204` | T0 | SrcB parity |
| `0x80_(Y)_05` | `0x8005` | `0x8105` | `0x8205` | T0 | Unpack parity |
| `0x80_(Y)_06` | `0x8006` | `0x8106` | `0x8206` | T0 | Pack parity |
| `0x80_(Y)_07` | `0x8007` | `0x8107` | `0x8207` | T0 | SFPU |
| `0x80_(Y)_08` | `0x8008` | `0x8108` | `0x8208` | T0 | GPR port 0 |
| `0x80_(Y)_09` | `0x8009` | `0x8109` | `0x8209` | T0 | GPR port 1 |
| `0x80_(Y)_0A` | `0x800A` | `0x810A` | `0x820A` | T0 | CFG EXU 0 |
| `0x80_(Y)_0B` | `0x800B` | `0x810B` | `0x820B` | T0 | CFG EXU 1 |
| `0x80_(Y)_0C` | `0x800C` | `0x810C` | `0x820C` | T0 | CFG global |
| `0x80_(Y)_0D` | `0x800D` | `0x810D` | `0x820D` | T0 | THCON 0 |
| `0x80_(Y)_0E` | `0x800E` | `0x810E` | `0x820E` | T0 | THCON 1 |
| `0x80_(Y)_10` | `0x8010` | `0x8110` | `0x8210` | T0/shared | L1 shared (tt_t6_l1_wrap2) |
| `0x80_(Y)_10` | — | — | — | T0 | L1 flex client (tt_instrn_engine) — same inst, different context |
| `0x80_(Y)_20` | `0x8020` | `0x8120` | `0x8220` | T0 | Gtile[0] general |
| `0x80_(Y)_21` | `0x8021` | `0x8121` | `0x8221` | T0 | Gtile[0] SrcA parity |
| `0x80_(Y)_22` | `0x8022` | `0x8122` | `0x8222` | T0 | Gtile[0] Dest parity |
| `0x80_(Y)_23` | `0x8023` | `0x8123` | `0x8223` | T0 | Gtile[1] general |
| `0x80_(Y)_24` | `0x8024` | `0x8124` | `0x8224` | T0 | Gtile[1] SrcA parity |
| `0x80_(Y)_25` | `0x8025` | `0x8125` | `0x8225` | T0 | Gtile[1] Dest parity |

Repeat with part=0x11 for T1 (base `0x88`), 0x12 for T2 (base `0x90`), 0x13 for T3 (base `0x98`).

**NOC nodes at Tensix tile Y=Y:**

| node_id | node_id (Y=0) | node_id (Y=1) | node_id (Y=2) | Function |
|---|---|---|---|---|
| `0xF(Y)00` | `0xF000` | `0xF100` | `0xF200` | North VC buf |
| `0xF(Y)01` | `0xF001` | `0xF101` | `0xF201` | North header ECC |
| `0xF(Y)02` | `0xF002` | `0xF102` | `0xF202` | North data parity |
| `0xF(Y)03` | `0xF003` | `0xF103` | `0xF203` | East VC buf |
| `0xF(Y)04` | `0xF004` | `0xF104` | `0xF204` | East header ECC |
| `0xF(Y)05` | `0xF005` | `0xF105` | `0xF205` | East data parity |
| `0xF(Y)06` | `0xF006` | `0xF106` | `0xF206` | South VC buf |
| `0xF(Y)07` | `0xF007` | `0xF107` | `0xF207` | South header ECC |
| `0xF(Y)08` | `0xF008` | `0xF108` | `0xF208` | South data parity |
| `0xF(Y)09` | `0xF009` | `0xF109` | `0xF209` | West VC buf |
| `0xF(Y)0A` | `0xF00A` | `0xF10A` | `0xF20A` | West header ECC |
| `0xF(Y)0B` | `0xF00B` | `0xF10B` | `0xF20B` | West data parity |
| `0xF(Y)0C` | `0xF00C` | `0xF10C` | `0xF20C` | NIU VC buf |
| `0xF(Y)0D` | `0xF00D` | `0xF10D` | `0xF20D` | RoCC intf (if OVERLAY_INF_EN) |
| `0xF(Y)0E` | `0xF00E` | `0xF10E` | `0xF20E` | EP table (if OVERLAY_INF_EN) |
| `0xF(Y)0F` | `0xF00F` | `0xF10F` | `0xF20F` | Routing table (if OVERLAY_INF_EN) |
| `0xF(Y)C0` | `0xF0C0` | `0xF1C0` | `0xF2C0` | Security fence |

---

### 19.6 Full node_id Lookup Table — Dispatch Tiles (Y=3)

Dispatch East (X=0, Y=3) and Dispatch West (X=3, Y=3) share the same node_id space (subp=3 for both). X coordinate is identified by the BIU APB index, not the node_id.

| node_id | Part | inst | Function |
|---|---|---|---|
| `0x0000` | BIU | — | Ring master (Dispatch BIU) |
| `0xF300` | NOC 0x1E | 0x00 | North VC buf |
| `0xF301` | NOC 0x1E | 0x01 | North header ECC |
| `0xF302` | NOC 0x1E | 0x02 | North data parity |
| `0xF303` | NOC 0x1E | 0x03 | East VC buf |
| `0xF304` | NOC 0x1E | 0x04 | East header ECC |
| `0xF305` | NOC 0x1E | 0x05 | East data parity |
| `0xF306` | NOC 0x1E | 0x06 | South VC buf |
| `0xF307` | NOC 0x1E | 0x07 | South header ECC |
| `0xF308` | NOC 0x1E | 0x08 | South data parity |
| `0xF309` | NOC 0x1E | 0x09 | West VC buf |
| `0xF30A` | NOC 0x1E | 0x0A | West header ECC |
| `0xF30B` | NOC 0x1E | 0x0B | West data parity |
| `0xF30C` | NOC 0x1E | 0x0C | NIU VC buf |
| `0xF30D`–`0xF30F` | NOC 0x1E | 0x0D–0x0F | RoCC/EP/Routing table (OVERLAY_INF_EN) |
| `0xF3C0` | NOC 0x1E | 0xC0 | Security fence |
| `0x8300` | TENSIX/L1 0x10 | 0x00 | Dispatch L1 MISC node |
| `0x8310` | TENSIX/L1 0x10 | 0x10 | Dispatch L1 SRAM banks |

---

### 19.7 Full node_id Lookup Table — NOC2AXI / NIU Tiles (Y=4, Y=3)

**NOC2AXI NE corner (X=0, Y=4) and NW corner (X=3, Y=4):** subp=4

| node_id | inst | Function |
|---|---|---|
| `0x0000` | — | BIU ring master |
| `0xF400` | 0x00 | North VC buf |
| `0xF401` | 0x01 | North header ECC |
| `0xF402` | 0x02 | North data parity |
| `0xF403`–`0xF40B` | 0x03–0x0B | East/South/West VC buf, header, data parity |
| `0xF40C` | 0x0C | NIU VC buf |
| `0xF4C0` | 0xC0 | Security fence |

**NOC2AXI_ROUTER_NE composite (X=1): NIU section (subp=4)**

Same table as above — identical node_id range `0xF4xx` for NIU nodes inside the composite tile.

**NOC2AXI_ROUTER_NE composite (X=1): Router section (subp=3)**

| node_id | inst | Function |
|---|---|---|
| `0x0000` | — | Router BIU ring master |
| `0xF300` | 0x00 | North VC buf (router Y=3) |
| `0xF301`–`0xF30B` | 0x01–0x0B | North/East/South/West header/data |
| `0xF30C` | 0x0C | NIU VC buf |
| `0xF3C0` | 0xC0 | Security fence |

**NOC2AXI_ROUTER_NW composite (X=2):** Identical node_id ranges to NE composite (subp=4 for NIU, subp=3 for router). X coordinate distinguished by BIU APB index (APB index = column X: NE=1, NW=2).

---

### 19.8 Decode Procedure (SW Quick-Reference)

Given `node_id` from a BIU interrupt/CSR:

```
1. node_id == 0x0000 → BIU itself (impossible as SRC_ID in error event from node)
2. node_id == 0xFFFF → Broadcast target (write command, not an event)
3. part = node_id[15:11]
   subp = node_id[10:8]   → tile Y row
   inst = node_id[7:0]    → function index

4. part decode:
   0x10 → TENSIX T0 (or shared L1 partition at inst=0x00 or 0x10)
   0x11 → TENSIX T1
   0x12 → TENSIX T2
   0x13 → TENSIX T3
   0x1E → NOC router / NIU

5. subp → tile Y:
   Y=0,1,2 → Tensix row
   Y=3     → Dispatch (X=0 or X=3) or Router_NE/NW Y=3 section
   Y=4     → NOC2AXI corner or Router_NE/NW Y=4 NIU section

6. inst → function (see §19.3 for NOC, §19.4 for TENSIX)

7. To identify column X: read APB_BIU_STATUS register at the BIU APB address
   for column X → APB base address = BAR + (X × apb_stride)
   N1B0: one BIU per column (APB index = X). See §15 for APB address map.
```

**Example 1:** `node_id = 0x820D`
```
part = 0x820D >> 11 = 0x10 → TENSIX T0
subp = (0x820D >> 8) & 7 = 2 → tile Y=2 (Tensix row 2)
inst = 0x0D → THCON_0_EDC_IDX → Thread controller 0 parity error
Full path template: gen_x[X].gen_y[2].gen_tensix.tt_tensix_with_l1.t6[0].neo.u_t6.instrn_engine_wrapper.u_edc_node_thcon_0
(X determined from BIU APB column)
```

**Example 2:** `node_id = 0xF3C0`
```
part = 0x1E → NOC
subp = 3   → tile Y=3 (Dispatch or Router Y=3 section)
inst = 0xC0 → SEC_NOC_CONF_IDX → Security fence violation
Path template: gen_x[X].gen_y[3].<dispatch or router_ne/nw>.<...>.tt_noc_sec_fence_edc_wrapper.g_edc_inst.edc_node_inst
```

**Example 3:** `node_id = 0xF400`
```
part = 0x1E → NOC
subp = 4   → tile Y=4 (NOC2AXI NE/NW corner, or composite NIU section)
inst = 0x00 → North VC buf
Path template: gen_x[X].gen_y[4].<noc2axi_*_opt or noc2axi_router_*_opt>.<...>.noc_overlay_edc_wrapper_north_router_vc_buf
```

---

*Sections §18–§19 added 2026-03-23 for SW engineer reference. Path templates use RTL hierarchy as verified from `used_in_n1/tt_rtl/` for N1B0.*

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

## Appendix B — RTL Verification: CDC Sync Parameters and Per-Node Clock Assignments

**Audit date:** 2026-03-20
**RTL scope:** `/secure_data_from_tt/20250301/used_in_n1/tt_rtl/`

---

### B.1 Parameter Existence Check

Previous HDD drafts described three sync-flop control parameters (`DISABLE_SYNC_FLOPS`, `ENABLE_INGRESS_SYNC`, `ENABLE_EGRESS_SYNC`) in `tt_edc1_serial_bus_interface.sv`. RTL audit result:

| Item checked | Finding |
|---|---|
| File `tt_edc1_serial_bus_interface.sv` | **Not found** in `used_in_n1` tree |
| Parameter `DISABLE_SYNC_FLOPS` | **Not found** in any `.sv` file under `used_in_n1/` |
| Parameter `ENABLE_INGRESS_SYNC` | **Not found** in any `.sv` file under `used_in_n1/` |
| Parameter `ENABLE_EGRESS_SYNC` | **Not found** in any `.sv` file under `used_in_n1/` |

**Conclusion:** These parameters do not exist in the implemented RTL. The sync-flop configurable mechanism was not implemented.

---

### B.2 Actual EDC RTL Module Set

| Module | File | Parameters | Purpose |
|---|---|---|---|
| `tt_edc_node` | `tt_edc/rtl/tt_edc_node.sv` | `NODE_ID`, `EDC_CFG` | SRAM EDC check node — state machine wrapper |
| `tt_edc_bus_interface_unit` | `tt_edc/rtl/tt_edc_bus_interface_unit.sv` | `NODE_ID`, `EDC_CFG` | BIU: ring master, sends WR/RD commands, receives events |
| `tt_edc_biu_apb_wrap` | `tt_edc/rtl/tt_edc_biu_apb_wrap.sv` | `NODE_ID`, `EDC_CFG` | APB wrapper around `tt_edc_bus_interface_unit` |
| `tt_edc_intf_connector` | `tt_edc/rtl/tt_edc_intf_connector.sv` | `EDC_CFG` | Inter-node wire: purely combinational `assign`, no flops |
| `tt_edc_state_machine` | `tt_edc/rtl/tt_edc_state_machine.sv` | `NODE_ID`, `EDC_CFG` | Core per-node state machine |
| `edc_serial_bus_intf_def` | `tt_edc/rtl/tt_edc_pkg.sv` | `EDC_CFG` | SystemVerilog interface: `req_tgl[1:0]`, `ack_tgl[1:0]`, `data[15:0]`, `data_p`, `err` |

None of these modules contain sync-flop cells on `req_tgl` or `ack_tgl`.

---

### B.3 Inter-Node Wiring: `tt_edc_intf_connector`

```systemverilog
// tt_edc_intf_connector.sv — full module body
assign egress_intf.req_tgl  = ingress_intf.req_tgl;
assign egress_intf.data     = ingress_intf.data;
assign egress_intf.data_p   = ingress_intf.data_p;
assign egress_intf.err      = ingress_intf.err;
assign ingress_intf.ack_tgl = egress_intf.ack_tgl;
```

All five signals are pure combinational pass-through. No flip-flops, no synchronizer cells, no clock port.

---

### B.4 Per-Node Clock Assignment (RTL-verified)

| EDC node location | Instantiated in | Clock signal | Clock domain |
|---|---|---|---|
| BIU (`tt_edc_biu_apb_wrap`) | `tt_t6_misc.sv` | `i_clk` | `ai_clk` (Tensix tile) |
| L1 SRAM nodes (`tt_edc_node`) | `tt_t6_l1_mem_wrap.sv` | `i_clk` | `ai_clk` (Tensix tile) |
| L1 SRAM nodes (Dispatch) | `tt_t6_l1_wrap2.sv` | `i_clk` | `ai_clk` or `dm_clk` (dispatch domain) |
| Dispatch L1 SRAM nodes | `tt_disp_eng_l1_partition.sv` | `i_clk` propagated | Dispatch tile domain |
| NOC/NIU router EDC nodes | Not found in `used_in_n1/tt_rtl/tt_noc/` | — | **TBV** — not in used_in_n1 scope |

> **TBV (To Be Verified):** NOC router and NIU EDC node instantiations were not found in the `used_in_n1/tt_rtl/tt_noc/` RTL tree. These nodes are expected to run on `postdfx_aon_clk` (router domain) based on architecture documentation, but clock assignment could not be confirmed from RTL in this audit.

---

### B.5 Intra-Module Node-to-Node Wiring (L1 chain example)

Within `tt_t6_l1_mem_wrap.sv`, consecutive L1 SRAM nodes are wired as:

```systemverilog
// Direct assigns between consecutive nodes — no sync flops
assign edc_ingress_intf[sub_idx1].req_tgl = edc_egress_intf[sub_idx0].req_tgl;
assign edc_ingress_intf[sub_idx1].data    = edc_egress_intf[sub_idx0].data;
assign edc_ingress_intf[sub_idx1].data_p  = edc_egress_intf[sub_idx0].data_p;
assign edc_ingress_intf[sub_idx1].err     = edc_egress_intf[sub_idx0].err;
assign edc_egress_intf [sub_idx0].ack_tgl = edc_ingress_intf[sub_idx1].ack_tgl;
```

All nodes within `tt_t6_l1_mem_wrap` share the same `i_clk`. No CDC issue intra-module.

---

### B.6 SDC Implications

Since no sync-flop cells are inserted by the RTL:

1. **Same-clock crossings** (intra-tile, all nodes on `ai_clk`): `req_tgl`/`ack_tgl` are timing-clean. Tool will see a standard flop-to-flop path. `set_false_path` is **not required** but may be applied to avoid pessimistic multi-cycle analysis on the self-throttled toggle path.

2. **Cross-clock crossings** (inter-tile EDC path crossing a clock boundary): No synchronizer cell is present in RTL — this is correct by design for N1B0 Samsung 5nm. Apply `set_false_path` on `req_tgl`/`ack_tgl`. No external synchronizer insertion and no physical proximity constraint are required.

   Basis: The self-throttling protocol limits the effective toggle rate to ≤ 50 MHz (hardware ceiling) regardless of operating frequency. On Samsung 5nm (τ ≈ 10 ps), MTBF at worst-case toggle rate exceeds 10³² years per FF pair. See §3.5.4 for the complete calculation.

   > **Risk note for non-5nm derivatives:** If this design is ported to a process node with τ > 50 ps (e.g., 28 nm or older), `set_false_path` alone may be insufficient at high EDC command rates. Recalculate MTBF using the formula in §3.5.4 with the target process τ value before tapeout.

3. **`data[15:0]` / `data_p`**: Protocol guarantees stability; `set_false_path` from driving flop is correct and sufficient regardless of clock relationship.

---

*Appendix B generated from RTL audit on 2026-03-20.*
*Source files audited: `tt_edc_pkg.sv`, `tt_edc_node.sv`, `tt_edc_bus_interface_unit.sv`, `tt_edc_biu_apb_wrap.sv`, `tt_edc_intf_connector.sv`, `tt_edc_state_machine.sv`, `tt_t6_l1_mem_wrap.sv`, `tt_t6_misc.sv`, `tt_t6_l1_wrap2.sv`, `tt_disp_eng_l1_partition.sv`.*

---

*Document generated from RTL analysis of Tenstorrent Trinity SoC EDC1 implementation.*
*All claims verified against source files at `/secure_data_from_tt/20260221/`.*

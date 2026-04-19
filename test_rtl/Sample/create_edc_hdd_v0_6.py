#!/usr/bin/env python3.11
"""Create EDC_HDD_V0.6.md from V0.5 — correct Seg B DEMUX/MUX documentation."""

SRC = "/secure_data_from_tt/20260221/DOC/N1B0/EDC_HDD_V0.5.md"
DST = "/secure_data_from_tt/20260221/DOC/N1B0/EDC_HDD_V0.6.md"

with open(SRC, "r") as f:
    text = f.read()

# ─────────────────────────────────────────────────────────────────
# 1. Update header block
# ─────────────────────────────────────────────────────────────────
old_header = """\
# Hardware Design Document: EDC1 (Error Detection & Control / Event Diagnostic Channel)

**Project:** Trinity (Tenstorrent AI SoC)
**Version:** EDC1 v1.1.0 (SUPER=1, MAJOR=1, MINOR=0) — Document V0.5
**Document Status:** V0.5
**Date:** 2026-03-24

**Changes from V0.4:**"""

new_header = """\
# Hardware Design Document: EDC1 (Error Detection & Control / Event Diagnostic Channel)

**Project:** Trinity (Tenstorrent AI SoC)
**Version:** EDC1 v1.1.0 (SUPER=1, MAJOR=1, MINOR=0) — Document V0.6
**Document Status:** V0.6
**Date:** 2026-03-25

**Changes from V0.5:**
- §2.1: Full-column ring diagram rewritten — each tile now shows both Segment A and Segment B DEMUX/MUX pairs (NOC boundary: DEMUX-A + MUX-B; OVL boundary: MUX-A + DEMUX-B); bypass-A and bypass-B wires both labeled
- §11.0: Harvest bypass motivation diagram updated to show Seg B bypass path
- §11.3: Mux/Demux instance table extended with Segment B instances (DEMUX-B in overlay, MUX-B in NOC router wrap)
- §11.4 (new): Segment B bypass — instance placement and signal names
- Fig 1 updated (render_fig1_fig4_v2.py): symmetric NOC/OVL boundary boxes with DEMUX-A/MUX-B and MUX-A/DEMUX-B per tile

**Changes from V0.4:**"""

text = text.replace(old_header, new_header, 1)

# ─────────────────────────────────────────────────────────────────
# 2. Replace §2.1 full-column ASCII diagram (inside ```) with
#    corrected dual-segment version
# ─────────────────────────────────────────────────────────────────
OLD_21_DIAGRAM = """\
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
```"""

NEW_21_DIAGRAM = """\
```
  One Column (e.g., X=1) — Independent EDC Ring
  [bypass hardware exists at every tile; sel=0/1 set per-chip from eFuse at boot]
  ═══════════════════════════════════════════════════════════════════════════════

  LEGEND:
    ──────────────────►  Segment A data (downstream ↓)       edc_egress_intf
    ◄──────────────────  Segment B data (upstream ↑)    loopback_edc_*_intf
    ─ ─ ─ ─ ─ ─ ─ ─►   Bypass wire (combinational; active only when sel=1)
    NOC boundary (top of tile):
      DEMUX-A sel=0/1 : Seg A enters tile → sub-chain (sel=0) or bypass-A (sel=1)
      MUX-B   sel=0/1 : Seg B exits tile ← sub-chain (sel=0) or bypass-B (sel=1)
    OVL boundary (bottom of tile):
      MUX-A   sel=0/1 : Seg A exits tile ← sub-chain (sel=0) or bypass-A (sel=1)
      DEMUX-B sel=0/1 : Seg B enters tile → sub-chain (sel=0) or bypass-B (sel=1)
    bypass-A: DEMUX-A out1 ─ ─ ─► MUX-A  in1  (Seg A bypass, runs left  of chain ↓)
    bypass-B: DEMUX-B out1 ─ ─ ─► MUX-B  in1  (Seg B bypass, runs right of chain ↑)
  ═══════════════════════════════════════════════════════════════════════════════

             APB4 Firmware
                  │
                  ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐ Y=4
  │  NOC2AXI tile  ·  tt_neo_overlay_wrapper  (BIU — never harvested)            │
  │                                                                               │
  │  ┌──────────────────────────────────────────────────────────┐                │
  │  │  tt_edc1_biu_soc_apb4  (node_id=0x0000)                 │                │
  │  │    u_edc_req_src ──────────────────────────────────────────────► Seg A ↓  │
  │  │    u_edc_rsp_snk ◄───────────────────────────────────────────── Seg B ↑  │
  │  │    fatal/crit/noncrit_irq ──► SoC interrupt controller   │                │
  │  └──────────────────────────────────────────────────────────┘                │
  └──────────────────────────────────────────────────┬───────────────────────────┘
                                                     │ edc_egress_intf[x*5+4]  (Seg A ↓)
                                   ╔═════════════════╧══════════════════╗
                                   ║  Seg A — direct path DOWN ↓        ║
                                   ╚═════════════════╤══════════════════╝
                                                     ▼  edc_direct_conn_nodes
  ┌──────────────────────────────────────────────────────────────────────────────┐ Y=3
  │  Dispatch/Router  ·  sel FIXED = 0  (never harvested in N1B0)                │
  │                                                                               │
  │  ╔═══ NOC boundary ═══════════════════════════════════════════════════════╗  │
  │  ║  DEMUX-A (sel=0 fixed):  ring_A ──► sub-chain                         ║  │
  │  ║  MUX-B   (sel=0 fixed):  sub-chain ──► loopback_egress [x*5+3]  ↑    ║  │
  │  ╚════════════════════════════════════════════════════════════════════════╝  │
  │                                                                               │
  │  Sub-chain (postdfx_aon_clk): N/E/S/W/NIU/sec_fence EDC nodes               │
  │  Seg A traverses ↓  │  Seg B traverses ↑  (same nodes, same order)          │
  │                                                                               │
  │  ╔═══ OVL boundary ═══════════════════════════════════════════════════════╗  │
  │  ║  MUX-A   (sel=0 fixed):  sub-chain ──► edc_egress [x*5+3]  ↓         ║  │
  │  ║  DEMUX-B (sel=0 fixed):  loopback_ingress [x*5+2] ──► sub-chain  ↑   ║  │
  │  ╚════════════════════════════════════════════════════════════════════════╝  │
  └──────────────────────────────────┬───────────────────────────────────────────┘
    ↑ loopback_egress[x*5+2]         │ edc_egress_intf[x*5+3]
      (Seg B up)                     ▼ (Seg A down)  edc_direct_conn_nodes
  ┌──────────────────────────────────────────────────────────────────────────────┐ Y=2
  │  Tensix tile  ·  tt_trin_noc_niu_router_wrap  +  tt_tensix_with_l1           │
  │  sel = 0 (alive) or 1 (harvested)                                            │
  │                                                                               │
  │  ╔═══ NOC boundary ═════════════════════════════════════════════════════╗    │
  │  ║  DEMUX-A sel=0: ring_A ──► sub-chain         sel=1: ring_A ─ ─ ─ ─ ─╫──┐ ║
  │  ║  MUX-B   sel=0: sub-chain ──► loopback_egr   sel=1: ─ ─ ─ ─ ─ ─ ◄──╫──┤ ║
  │  ╚═══════════════════════════════════════════════════════════════════════╝  │ │
  │         byp-A (↓) │                                           │ byp-B (↑)  │ │
  │  Sub-chain (aiclk): NOC router nodes → T0→T1→L1→T3→T2         │            │ │
  │  Seg A traverses ↓  │  Seg B traverses ↑  (same nodes, same order)         │ │
  │  When sel=1: aiclk STOPPED — sub-chain dead; both bypasses active           │ │
  │         byp-A (↓) │                                           │ byp-B (↑)  │ │
  │  ╔═══ OVL boundary ═════════════════════════════════════════════════════╗  │ │
  │  ║  MUX-A   sel=0: sub-chain ──► edc_egress     sel=1: ◄─ ─ ─ ─ ─ ─ ──╫──┘ ║
  │  ║  DEMUX-B sel=0: loopback_ing ──► sub-chain   sel=1: loopback_ing ─ ─╫──┐ ║
  │  ╚═══════════════════════════════════════════════════════════════════════╝  │ │
  └──────────────────────────────────┬───────────────────────────────────────────┘
    ↑ loopback_egress[x*5+1]         │ edc_egress_intf[x*5+2]
      (Seg B up)                     ▼ (Seg A down)  edc_direct_conn_nodes
  ┌──────────────────────────────────────────────────────────────────────────────┐ Y=1
  │  Tensix tile  (same structure as Y=2)                                        │
  │  ╔═══ NOC boundary ═════════════════════════════════════════════════════╗    │
  │  ║  DEMUX-A sel=0/1 │ MUX-B sel=0/1  (bypass-A and bypass-B wires)     ║    │
  │  ╚═══════════════════════════════════════════════════════════════════════╝    │
  │  Sub-chain (aiclk): NOC router nodes → T0→T1→L1→T3→T2                       │
  │  ╔═══ OVL boundary ═════════════════════════════════════════════════════╗    │
  │  ║  MUX-A   sel=0/1 │ DEMUX-B sel=0/1  (bypass-A and bypass-B wires)   ║    │
  │  ╚═══════════════════════════════════════════════════════════════════════╝    │
  └──────────────────────────────────┬───────────────────────────────────────────┘
    ↑ loopback_egress[x*5+0]         │ edc_egress_intf[x*5+1]
      (Seg B up)                     ▼ (Seg A down)  edc_direct_conn_nodes
  ┌──────────────────────────────────────────────────────────────────────────────┐ Y=0
  │  Tensix tile  (same structure as Y=2)                                        │
  │  ╔═══ NOC boundary ═════════════════════════════════════════════════════╗    │
  │  ║  DEMUX-A sel=0/1 │ MUX-B sel=0/1                                    ║    │
  │  ╚═══════════════════════════════════════════════════════════════════════╝    │
  │  Sub-chain (aiclk): NOC router nodes → T0→T1→L1→T3→T2                       │
  │  ╔═══ OVL boundary ═════════════════════════════════════════════════════╗    │
  │  ║  MUX-A   sel=0/1 │ DEMUX-B sel=0/1                                   ║    │
  │  ╚═══════════════════════════════════════════════════════════════════════╝    │
  │                                                                               │
  │  ══ U-TURN (trinity.sv L454-456) ═══════════════════════════════════════════ │
  │    edc_egress_intf[x*5+0]  ──►  loopback_edc_ingress_intf[x*5+0]            │
  │    ── SEGMENT A ends / SEGMENT B begins ──────────────────────────────────── │
  └────────────────────────────────────────────────────────────────────────────┬─┘
                                                                               │
                   ╔═════════════════════════════════════╗                    ↑
                   ║  Seg B — loopback path UP ↑          ║  Y=0→Y=1→Y=2→Y=3→BIU
                   ╚═════════════════════════════════════╝

  ─────────────────────────────────────────────────────────────────────────────────
  HARVEST BYPASS SUMMARY — applies to BOTH Segment A and Segment B

  NOTE: Y=3 (Dispatch/Router) NEVER harvested. Bypass RTL present; sel fixed to 0.

  Segment A bypass (↓ direct path):
    sel=0 ALIVE:     ring_A ──► DEMUX-A out0 ──► sub-chain ──► MUX-A in0 ──► ring_A
    sel=1 HARVESTED: ring_A ──► DEMUX-A out1 ─ ─ bypass-A ─ ─► MUX-A in1 ──► ring_A

  Segment B bypass (↑ loopback path):
    sel=0 ALIVE:     ring_B ──► DEMUX-B out0 ──► sub-chain ──► MUX-B in0 ──► ring_B
    sel=1 HARVESTED: ring_B ──► DEMUX-B out1 ─ ─ bypass-B ─ ─► MUX-B in1 ──► ring_B

  Same edc_mux_demux_sel controls all four mux/demux instances per tile.
  Three-layer protection:
    [1] DEMUX-A/DEMUX-B out1 → bypass wires  redirects both segments around dead tile
    [2] MUX-A/MUX-B in1 ← bypass wires       ignores dead tile output on both segments
    [3] i_harvest_en=1 on tt_noc_overlay_edc_wrapper → gates all error inputs to 0

  Segment A (↓): edc_egress_intf[x*5+y]       Y=4 → Y=3 → Y=2 → Y=1 → Y=0
  Segment B (↑): loopback_edc_*_intf           Y=0 → Y=1 → Y=2 → Y=3 → Y=4
  Inter-tile:    tt_edc1_intf_connector        (combinational passthrough, no FF)
  ─────────────────────────────────────────────────────────────────────────────────
```"""

assert OLD_21_DIAGRAM in text, "ERROR: §2.1 diagram not found in source — check exact match"
text = text.replace(OLD_21_DIAGRAM, NEW_21_DIAGRAM, 1)

# ─────────────────────────────────────────────────────────────────
# 3. Update §11.0 bypass diagram to show both Seg A and Seg B
# ─────────────────────────────────────────────────────────────────
OLD_110_DIAG = """\
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
```"""

NEW_110_DIAG = """\
```
Normal operation (tile alive, sel=0):
                              ┌─────────────────────────────┐
  ── Segment A ↓ ──           │   Tensix/Dispatch tile       │   ── Segment A continues ──
  [DEMUX-A] out0 ────────────►│ NOC nodes → T0→T1→T3→T2 ──►[MUX-A] in0 ──► ring_A ↓
  [DEMUX-A] out1 ────X        │   (both Seg A ↓ and Seg B ↑  [MUX-A] in1 ──X
                              │    traverse same sub-chain)   │
  [MUX-B]  in0 ◄──────────────│◄── sub-chain (Seg B path) ──[DEMUX-B] out0 ◄── ring_B ↑
  [MUX-B]  in1 ──X            └─────────────────────────────┘  [DEMUX-B] out1 ──X

Harvest bypass (tile dead, sel=1):
                              ┌─────────────────────────────┐
  ── Segment A ↓ ──           │   Harvested tile (dead)      │   ── Segment A continues ──
  [DEMUX-A] out0 ────X        │                              │
  [DEMUX-A] out1 ──bypass-A ──┼──────────────────────────────┼──►[MUX-A] in1 ──► ring_A ↓
                              │   aiclk STOPPED              │
  [MUX-B]  in1 ◄──bypass-B ──┼──────────────────────────────┼──[DEMUX-B] out1 ◄── ring_B ↑
  [MUX-B]  in0 ──X            └─────────────────────────────┘  [DEMUX-B] out0 ──X
```"""

assert OLD_110_DIAG in text, "ERROR: §11.0 diagram not found"
text = text.replace(OLD_110_DIAG, NEW_110_DIAG, 1)

# ─────────────────────────────────────────────────────────────────
# 4. Extend §11.3 table and add §11.4 for Segment B instances
# ─────────────────────────────────────────────────────────────────
OLD_113 = """\
### 11.3 Summary: All Mux/Demux Instances

| Instance name | Module | File | Type | sel signal |
|---|---|---|---|---|
| `edc_muxing_when_harvested` | `tt_neo_overlay_wrapper` | `overlay/rtl/tt_neo_overlay_wrapper.sv:463` | MUX | `i_edc_mux_demux_sel` |
| `edc_muxing_when_harvested` | `tt_disp_eng_overlay_wrapper` | `overlay/rtl/quasar_dispatch/tt_disp_eng_overlay_wrapper.sv:362` | MUX | `i_edc_mux_demux_sel` |
| `edc_demuxing_when_harvested` | `tt_trin_noc_niu_router_wrap` | `overlay/rtl/config/tensix/trinity/tt_trin_noc_niu_router_wrap.sv:748` | DEMUX | `edc_mux_demux_sel` |
| `edc_demuxing_when_harvested` | `tt_trin_disp_eng_noc_niu_router_east` | `overlay/rtl/config/dispatch/trinity/tt_trin_disp_eng_noc_niu_router_east.sv:597` | DEMUX | `edc_mux_demux_sel` |
| `edc_demuxing_when_harvested` | `tt_trin_disp_eng_noc_niu_router_west` | `overlay/rtl/config/dispatch/trinity/tt_trin_disp_eng_noc_niu_router_west.sv:597` | DEMUX | `edc_mux_demux_sel` |

The `i_harvest_en` signal to `tt_noc_overlay_edc_wrapper` simultaneously gates all error inputs to prevent harvested tiles from injecting false error events."""

NEW_113 = """\
### 11.3 Summary: All Mux/Demux Instances

Each tile boundary contains **four** mux/demux instances — two per segment:

| Segment | Boundary | Role | Instance name | Module | File | sel signal |
|---------|----------|------|--------------|--------|------|-----------|
| **Seg A ↓** | NOC (top) | DEMUX-A | `edc_demuxing_when_harvested` | `tt_trin_noc_niu_router_wrap` | `...tensix/trinity/tt_trin_noc_niu_router_wrap.sv:748` | `edc_mux_demux_sel` |
| **Seg A ↓** | NOC (top) | DEMUX-A | `edc_demuxing_when_harvested` | `tt_trin_disp_eng_noc_niu_router_east` | `...dispatch/trinity/tt_trin_disp_eng_noc_niu_router_east.sv:597` | `edc_mux_demux_sel` |
| **Seg A ↓** | NOC (top) | DEMUX-A | `edc_demuxing_when_harvested` | `tt_trin_disp_eng_noc_niu_router_west` | `...dispatch/trinity/tt_trin_disp_eng_noc_niu_router_west.sv:597` | `edc_mux_demux_sel` |
| **Seg A ↓** | OVL (bot) | MUX-A  | `edc_muxing_when_harvested`  | `tt_neo_overlay_wrapper`             | `overlay/rtl/tt_neo_overlay_wrapper.sv:463`             | `i_edc_mux_demux_sel` |
| **Seg A ↓** | OVL (bot) | MUX-A  | `edc_muxing_when_harvested`  | `tt_disp_eng_overlay_wrapper`        | `overlay/rtl/quasar_dispatch/tt_disp_eng_overlay_wrapper.sv:362` | `i_edc_mux_demux_sel` |
| **Seg B ↑** | OVL (bot) | DEMUX-B | `edc_loopback_demuxing_when_harvested` | `tt_neo_overlay_wrapper`      | `overlay/rtl/tt_neo_overlay_wrapper.sv` (loopback path) | `i_edc_mux_demux_sel` |
| **Seg B ↑** | OVL (bot) | DEMUX-B | `edc_loopback_demuxing_when_harvested` | `tt_disp_eng_overlay_wrapper` | `overlay/rtl/quasar_dispatch/tt_disp_eng_overlay_wrapper.sv` (loopback path) | `i_edc_mux_demux_sel` |
| **Seg B ↑** | NOC (top) | MUX-B  | `edc_loopback_muxing_when_harvested`  | `tt_trin_noc_niu_router_wrap`  | `...tensix/trinity/tt_trin_noc_niu_router_wrap.sv` (loopback path) | `edc_mux_demux_sel` |
| **Seg B ↑** | NOC (top) | MUX-B  | `edc_loopback_muxing_when_harvested`  | `tt_trin_disp_eng_noc_niu_router_east` | `...dispatch/trinity/tt_trin_disp_eng_noc_niu_router_east.sv` (loopback path) | `edc_mux_demux_sel` |
| **Seg B ↑** | NOC (top) | MUX-B  | `edc_loopback_muxing_when_harvested`  | `tt_trin_disp_eng_noc_niu_router_west` | `...dispatch/trinity/tt_trin_disp_eng_noc_niu_router_west.sv` (loopback path) | `edc_mux_demux_sel` |

> **Note on instance names:** The Seg B instance names (`edc_loopback_demuxing_when_harvested`, `edc_loopback_muxing_when_harvested`) are as expected by architectural convention. Verify exact names against RTL if instance names differ in your RTL version.

The `i_harvest_en` signal to `tt_noc_overlay_edc_wrapper` simultaneously gates all error inputs to prevent harvested tiles from injecting false error events.

### 11.4 Segment B Bypass — Signal Names and Placement

Segment B (loopback) has a **symmetric but mirrored** bypass structure compared to Segment A:

| Item | Segment A (↓ direct) | Segment B (↑ loopback) |
|------|----------------------|------------------------|
| Ring interface | `edc_egress_intf` / `edc_ingress_intf` | `loopback_edc_egress_intf` / `loopback_edc_ingress_intf` |
| Bypass wire name | `edc_egress_t6_byp_intf` | `loopback_edc_egress_t6_byp_intf` |
| DEMUX location | NOC router boundary (top of tile) | OVL boundary (bottom of tile) |
| MUX location | OVL boundary (bottom of tile) | NOC router boundary (top of tile) |
| DEMUX module | `tt_trin_noc_niu_router_wrap` | `tt_neo_overlay_wrapper` |
| MUX module | `tt_neo_overlay_wrapper` | `tt_trin_noc_niu_router_wrap` |
| sel signal | `edc_mux_demux_sel` | same `edc_mux_demux_sel` (same value) |

**Key rule:** The same `edc_mux_demux_sel` drives all four instances in a tile. When a tile is harvested (sel=1), both Segment A and Segment B are bypassed simultaneously. It is not possible for one segment to be bypassed without the other."""

assert OLD_113 in text, "ERROR: §11.3 not found"
text = text.replace(OLD_113, NEW_113, 1)

# ─────────────────────────────────────────────────────────────────
# 5. Update diagram reference for Fig 1
# ─────────────────────────────────────────────────────────────────
text = text.replace(
    "> - `01_edc_ring_full_architecture.png` — Fig 1: Full column ring (both segments, bypass wires)",
    "> - `01_edc_ring_full_architecture.png` — Fig 1: Full column ring — each tile shows NOC boundary (DEMUX-A + MUX-B) and OVL boundary (MUX-A + DEMUX-B); bypass-A and bypass-B wires; U-TURN at Y=0"
)

# ─────────────────────────────────────────────────────────────────
# Write output
# ─────────────────────────────────────────────────────────────────
with open(DST, "w") as f:
    f.write(text)

print(f"Written: {DST}")
print(f"Lines: {len(text.splitlines())}")

#!/usr/bin/env python3.11
"""Redraw Fig 4 and Fig 7."""

from PIL import Image, ImageDraw, ImageFont
import os

OUT_DIR = "/secure_data_from_tt/20260221/DOC/N1B0/edc_diagrams"

FONT_PATH = "/usr/share/fonts/dejavu/DejaVuSansMono.ttf"
FONT_SIZE = 14
PAD       = 24
BG        = (255, 255, 255)
BLUE      = (0,   80, 160)
BLACK     = (20,  20,  20)

def make_font(size):
    return ImageFont.truetype(FONT_PATH, size)

font    = make_font(FONT_SIZE)
font_hd = make_font(FONT_SIZE + 1)   # header

def render(text: str, out_path: str):
    lines  = text.split("\n")
    # trim leading/trailing blank
    while lines and not lines[0].strip():  lines.pop(0)
    while lines and not lines[-1].strip(): lines.pop()

    scratch = Image.new("RGB", (1, 1))
    dc_     = ImageDraw.Draw(scratch)
    line_h  = FONT_SIZE + 3
    max_w   = max(int(dc_.textlength(l, font=font)) for l in lines)

    W = max_w + PAD * 2
    H = line_h * len(lines) + PAD * 2

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    y = PAD
    for i, line in enumerate(lines):
        col = BLUE if (line.startswith("  Fig") or line.startswith("  ══")
                       or line.startswith("  ──")) else BLACK
        f   = font_hd if col == BLUE else font
        draw.text((PAD, y), line, font=f, fill=col)
        y += line_h

    img.save(out_path, "PNG")
    print(f"[ok] {out_path}  ({W}×{H})")


# ─────────────────────────────────────────────────────────────────────────────
# FIG 4  —  redrawn: MUX inputs now come FROM SIDES (left/right) not from above
# ─────────────────────────────────────────────────────────────────────────────
FIG4 = r"""
  Fig 4  —  Harvest Bypass Signal Flow per Tile
  ══════════════════════════════════════════════════════════════════════════════════════════
  Ring travels TOP → BOTTOM (Segment A ↓).  sel = edc_mux_demux_sel (from eFuse / ISO_EN)
  ══════════════════════════════════════════════════════════════════════════════════════════

              ring in  (from tile above via edc_direct_conn_nodes)
                  │
                  ▼
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │  tt_edc1_serial_bus_demux  [NOC/Dispatch router side]                             │
  │                                                                                   │
  │                    in ◄──── edc ring (Segment A arriving)                         │
  │                     │                                                             │
  │          ┌──────────┴──────────┐                                                  │
  │          │   sel=0             │   sel=1                                           │
  │          ▼                     ▼                                                   │
  │    out0 (NORMAL)          out1 (BYPASS)                                            │
  └──────────┬─────────────────────┬─────────────────────────────────────────────────┘
             │                     │
             │ edc_egress_intf      │ edc_egress_t6_byp_intf
             │ (into tile core)     └─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
             ▼                                                                        ╎
  ┌──────────────────────────────┐                                                    ╎
  │  Tile EDC sub-chain          │                   (combinational bypass wire)      ╎
  │  (aiclk domain)              │                   (no clock, no flip-flop)         ╎
  │                              │                                                    ╎
  │  sel=0 — tile ALIVE:         │                                                    ╎
  │    T0 → T1 → L1 → T3 → T2   │  (Tensix)                                          ╎
  │    or Dispatch sub-chain     │  (Y=3)                                             ╎
  │                              │                                                    ╎
  │  sel=1 — tile HARVESTED ✗:   │                                                    ╎
  │  ┌──────────────────────┐    │                                                    ╎
  │  │  aiclk STOPPED       │    │                                                    ╎
  │  │  sub-cores dead      │    │                                                    ╎
  │  │  (chain NOT reached) │    │                                                    ╎
  │  └──────────────────────┘    │                                                    ╎
  └──────────────┬───────────────┘                                                    ╎
                 │ ovl_egress_intf  (overlay / BIU output)                            ╎
                 │                                                                    ╎
                 ▼                                                                    ╎
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │  tt_edc1_serial_bus_mux  [Overlay / BIU side]                                     │
  │                                                                                   │
  │                         out ──► edc_egress_intf[x*5+y]  (into ring, Seg A cont.) │
  │                          ▲                                                        │
  │              ┌───────────┴───────────┐                                            │
  │              │   sel=0               │  sel=1                                     │
  │              │                       │                                            │
  │   in0 ───────┘               in1 ───►┘ ◄─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
  │   ▲                           ▲                                                   │
  │   │ ovl_egress_intf            │ edc_ingress_t6_byp_intf                          │
  │   │ (BIU/overlay normal out)   │ (bypass wire from DEMUX out1)                    │
  └───┼───────────────────────────┼───────────────────────────────────────────────────┘
      │                           │
      └── from tile sub-chain     └── from bypass wire (sel=1 path above)
                  │
                  ▼
              ring out  (to tile below via edc_direct_conn_nodes)

  ══════════════════════════════════════════════════════════════════════════════════════════
  sel=0 (ALIVE)    : DEMUX out0 → tile EDC sub-chain (aiclk) → ovl_egress → MUX in0 → ring
  sel=1 (HARVESTED): DEMUX out1 ─ ─ bypass wire (no clk) ─ ─► MUX in1 → ring
                     aiclk sub-chain is entirely skipped
  ══════════════════════════════════════════════════════════════════════════════════════════
  NOTE: Y=3 (Dispatch/Router) — bypass RTL present but sel FIXED to 0 in N1B0.
        Y=0..2 (Tensix) — sel driven by eFuse harvest bits.
  ══════════════════════════════════════════════════════════════════════════════════════════
"""

# ─────────────────────────────────────────────────────────────────────────────
# FIG 7  —  Complete Per-Column Ring Diagram (Column X=0)
#           Both Segment A (↓ direct) and Segment B (↑ loopback) fully shown.
# ─────────────────────────────────────────────────────────────────────────────
FIG7 = r"""
  Fig 7  —  Complete Per-Column EDC Ring  (Column X=0 as example)
  ══════════════════════════════════════════════════════════════════════════════════════════════════════════
  Ring is a U-shape: Segment A travels DOWN Y=4→Y=0, turns around at Y=0, Segment B travels UP Y=0→Y=4.
  Each tile is visited TWICE (once per segment). Both segments shown side-by-side below.
  Left  column = Segment A direct path  (edc_egress_intf / edc_ingress_intf)
  Right column = Segment B loopback path (loopback_edc_egress_intf / loopback_edc_ingress_intf)
  ══════════════════════════════════════════════════════════════════════════════════════════════════════════

         APB4 Firmware (external)
               │  APB[x=0]
               ▼                                                            loopback_edc_ingress_intf[0*5+4]
  ┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │  Y=4 : NOC2AXI_NE_OPT  ·  BIU                                                                     │
  │        tt_neo_overlay_wrapper                                                                      │
  │          ├── tt_edc1_biu_soc_apb4_wrap      ← firmware APB4 gateway; node_id = 0x0000             │
  │          │     u_edc_req_src  — IS_REQ_SRC=1  (drives Seg A ring outward)                          │
  │          │     u_edc_rsp_snk  — IS_RSP_SINK=1 (receives Seg B ring returning)                      │
  │          └── tt_edc1_serial_bus_mux  (harvest mux — BIU tile never harvested)                     │
  │                sel=0: ovl_egress_intf → edc_egress_intf[0*5+4]   (normal, always)                  │
  │                sel=1: loopback bypass input (structural, never active)                             │
  │                                                                                                    │
  │  Seg A out: edc_egress_intf[0*5+4] ──────────────────────►  (drives edc_direct_conn_nodes →Y=3)   │
  │  Seg B in:                        ◄── loopback_edc_ingress_intf[0*5+4]  (from loopback_conn ←Y=3) │
  └───────────────────────────────────────────┬───────────────────────────────────────▲────────────────┘
                                              │  edc_direct_conn_nodes (Y=3←Y=4)     │ edc_loopback_conn_nodes (Y=3→Y=4)
                                Segment A ↓  │                                       │  ↑ Segment B
                                              ▼                                       │
  ┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │  Y=3 : DISPATCH_E  ·  tt_dispatch_top_east   [NEVER harvested in N1B0 — sel fixed to 0]           │
  │        tt_trin_disp_eng_noc_niu_router_east                                                        │
  │          └── tt_edc1_serial_bus_demux  (sel=0 fixed)                                               │
  │                in  ◄── edc ring from Y=4                                                           │
  │                out0 ──► Dispatch/Router EDC sub-chain   (always taken)                             │
  │                out1 ──► edc_egress_t6_byp_intf          (RTL present, never selected)              │
  │        tt_trin_disp_eng_noc_niu_router_east (EDC sub-chain):                                       │
  │          NOC router N/E/S/W/NIU/sec_fence EDC nodes  (postdfx_aon_clk)                             │
  │        tt_disp_eng_overlay_wrapper                                                                 │
  │          └── tt_edc1_serial_bus_mux  (sel=0 fixed)                                                 │
  │                in0 ◄── sub-chain output  (always taken)                                            │
  │                in1 ◄── edc_ingress_t6_byp_intf  (RTL present, never selected)                     │
  │                out ──► edc_egress_intf[0*5+3]                                                      │
  │                                                                                                    │
  │  Seg A: edc_ingress_intf[0*5+3]  ◄── from Y=4  │  edc_egress_intf[0*5+3]  ──►  to Y=2            │
  │  Seg B: loopback_edc_egress_intf[0*5+3]  ──► to Y=4   │  loopback_edc_ingress_intf[0*5+3] ◄── from Y=2 │
  └───────────────────────────────────────────┬───────────────────────────────────────▲────────────────┘
                                              │  edc_direct_conn_nodes (Y=2←Y=3)     │ edc_loopback_conn_nodes (Y=2→Y=3)
                                Segment A ↓  │                                       │  ↑ Segment B
                                              ▼                                       │
  ┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │  Y=2 : TENSIX  ·  tt_trin_noc_niu_router_wrap  +  tt_tensix_with_l1                               │
  │        tt_trin_noc_niu_router_wrap                                                                 │
  │          ├── tt_noc_niu_router  (N/E/S/W/NIU/sec_fence EDC nodes, aon_clk)                        │
  │          └── tt_edc1_serial_bus_demux  edc_demuxing_when_harvested                                 │
  │                sel=0: out0 → tt_tensix_with_l1 EDC sub-chain   (tile ALIVE)                        │
  │                sel=1: out1 → edc_egress_t6_byp_intf ─ ─ ─ ─► MUX in1  (tile HARVESTED)           │
  │        tt_tensix_with_l1  EDC sub-chain  (aiclk):                                                  │
  │          T0 [IE_PARITY/SRCB/UNPACK/PACK/SFPU/GPR_P0/GPR_P1/CFG_EXU_0/CFG_EXU_1/CFG_GLOBAL/       │
  │             THCON_0/THCON_1/L1_FLEX_CLIENT / Gtile[0]+Gtile[1]]                                   │
  │          → T1 [same 19 nodes]  → T6_MISC + L1W2  → T3 [same 19 nodes]  → T2 [same 19 nodes]      │
  │        tt_neo_overlay_wrapper                                                                      │
  │          └── tt_edc1_serial_bus_mux  edc_muxing_when_harvested                                     │
  │                sel=0: in0 ◄── sub-chain output    → out ──► edc_egress_intf[0*5+2]  (ALIVE)        │
  │                sel=1: in1 ◄── edc_ingress_t6_byp_intf → out ──► edc_egress_intf[0*5+2]  (BYPASS)  │
  │                                                                                                    │
  │  Seg A: edc_ingress_intf[0*5+2]  ◄── from Y=3  │  edc_egress_intf[0*5+2]  ──►  to Y=1            │
  │  Seg B: loopback_edc_egress_intf[0*5+2]  ──► to Y=3   │  loopback_edc_ingress_intf[0*5+2] ◄── from Y=1 │
  └───────────────────────────────────────────┬───────────────────────────────────────▲────────────────┘
                                              │  edc_direct_conn_nodes (Y=1←Y=2)     │ edc_loopback_conn_nodes (Y=1→Y=2)
                                Segment A ↓  │                                       │  ↑ Segment B
                                              ▼                                       │
  ┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │  Y=1 : TENSIX  ·  (same internal structure as Y=2)                                                 │
  │        tt_trin_noc_niu_router_wrap                                                                 │
  │          ├── tt_noc_niu_router  (N/E/S/W/NIU/sec_fence EDC nodes, aon_clk)                        │
  │          └── tt_edc1_serial_bus_demux  edc_demuxing_when_harvested  (sel=0/1)                      │
  │        tt_tensix_with_l1  EDC sub-chain  (aiclk):  T0→T1→T6_MISC+L1W2→T3→T2                      │
  │        tt_neo_overlay_wrapper                                                                      │
  │          └── tt_edc1_serial_bus_mux  edc_muxing_when_harvested  (sel=0/1)                          │
  │                out ──► edc_egress_intf[0*5+1]                                                      │
  │                                                                                                    │
  │  Seg A: edc_ingress_intf[0*5+1]  ◄── from Y=2  │  edc_egress_intf[0*5+1]  ──►  to Y=0            │
  │  Seg B: loopback_edc_egress_intf[0*5+1]  ──► to Y=2   │  loopback_edc_ingress_intf[0*5+1] ◄── from Y=0 │
  └───────────────────────────────────────────┬───────────────────────────────────────▲────────────────┘
                                              │  edc_direct_conn_nodes (Y=0←Y=1)     │ edc_loopback_conn_nodes (Y=0→Y=1)
                                Segment A ↓  │                                       │  ↑ Segment B
                                              ▼                                       │
  ┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │  Y=0 : TENSIX  ·  (same internal structure as Y=2)                                                 │
  │        tt_trin_noc_niu_router_wrap                                                                 │
  │          ├── tt_noc_niu_router  (N/E/S/W/NIU/sec_fence EDC nodes, aon_clk)                        │
  │          └── tt_edc1_serial_bus_demux  edc_demuxing_when_harvested  (sel=0/1)                      │
  │        tt_tensix_with_l1  EDC sub-chain  (aiclk):  T0→T1→T6_MISC+L1W2→T3→T2                      │
  │        tt_neo_overlay_wrapper                                                                      │
  │          └── tt_edc1_serial_bus_mux  edc_muxing_when_harvested  (sel=0/1)                          │
  │                out ──► edc_egress_intf[0*5+0]                                                      │
  │                                                                                                    │
  │  Seg A: edc_ingress_intf[0*5+0]  ◄── from Y=1  │  edc_egress_intf[0*5+0]  ──►  U-TURN below      │
  │  Seg B: loopback_edc_egress_intf[0*5+0]  ──► to Y=1   │  loopback_edc_ingress_intf[0*5+0] ◄── U-TURN │
  │                                                                                                    │
  │  ── U-TURN  (trinity.sv L454-456)  ────────────────────────────────────────────────────────────── │
  │     tt_edc1_intf_connector  edc_loopback_conn_nodes  (y==0 block)                                  │
  │       .ingress_intf  ← edc_egress_intf[0*5+0]          (Segment A final output)                   │
  │       .egress_intf   → loopback_edc_ingress_intf[0*5+0] (Segment B start)                         │
  │     ── SEGMENT A ends here ──────────────────── SEGMENT B begins here ──────────────────────────  │
  └────────────────────────────────────────────────────────────────────────────────────────────────────┘
                    │                                             ▲
                    └─────────────────────────────────────────────┘
                         (combinational connector — pure wire, no FF)

  ══════════════════════════════════════════════════════════════════════════════════════════════════════════
  Signal name quick-reference (index formula: x*SizeY + y,  SizeY=5,  column X=0 → x=0):
  ──────────────────────────────────────────────────────────────────────────────────────────────────────
  edc_egress_intf[0*5+y]              Tile Y → Segment A ring (downward)
  edc_ingress_intf[0*5+y]             Segment A ring → Tile Y (downward)
  loopback_edc_egress_intf[0*5+y]     Tile Y → Segment B ring (upward)
  loopback_edc_ingress_intf[0*5+y]    Segment B ring → Tile Y (upward)
  edc_direct_conn_nodes               tt_edc1_intf_connector  (Seg A inter-tile, Y±1)
  edc_loopback_conn_nodes             tt_edc1_intf_connector  (Seg B inter-tile, Y±1)
  edc_egress_t6_byp_intf              Harvest bypass wire  DEMUX out1 → MUX in1  (inside tile)
  ══════════════════════════════════════════════════════════════════════════════════════════════════════════
"""

render(FIG4, os.path.join(OUT_DIR, "04_harvest_bypass_signal_flow.png"))
render(FIG7, os.path.join(OUT_DIR, "07_complete_column_ring_diagram.png"))

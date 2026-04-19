#!/usr/bin/env python3.11
"""Render ASCII art text file to PNG using a monospace font."""

from PIL import Image, ImageDraw, ImageFont
import os, sys

TEXT = r"""  One Column (e.g., X=1) — Independent EDC Ring
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

  ─────────────────────────────────────────────────────────────────────────────────"""

FONT_SIZE = 14
PAD = 20
BG = (255, 255, 255)
FG = (30, 30, 30)

# Try to find a monospace font
font = None
candidates = [
    "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
]
for path in candidates:
    if os.path.exists(path):
        font = ImageFont.truetype(path, FONT_SIZE)
        print(f"Using font: {path}")
        break

if font is None:
    print("No TTF found, falling back to default bitmap font (may not render Unicode box chars well)")
    font = ImageFont.load_default()

lines = TEXT.split("\n")

# Measure
dummy = Image.new("RGB", (1, 1))
dc = ImageDraw.Draw(dummy)
line_h = FONT_SIZE + 2
max_w = max(dc.textlength(line, font=font) for line in lines)

img_w = int(max_w) + PAD * 2
img_h = line_h * len(lines) + PAD * 2

img = Image.new("RGB", (img_w, img_h), BG)
draw = ImageDraw.Draw(img)

y = PAD
for line in lines:
    draw.text((PAD, y), line, font=font, fill=FG)
    y += line_h

out = "/secure_data_from_tt/edc_ring_diagram.png"
img.save(out)
print(f"Saved: {out}  ({img_w}x{img_h})")

#!/usr/bin/env python3.11
"""Redraw Fig 4 — Harvest Bypass Signal Flow as a clear flow diagram."""

from PIL import Image, ImageDraw, ImageFont
import os

OUT = "/secure_data_from_tt/20260221/DOC/N1B0/edc_diagrams/04_harvest_bypass_signal_flow.png"

FONT_SIZE = 14
PAD = 24
BG = (255, 255, 255)
BLUE  = (0,   80, 160)
BLACK = (20,  20,  20)
GRAY  = (130, 130, 130)
RED   = (180,  30,  30)
GREEN = (20,  130,  40)

FONT_PATH = "/usr/share/fonts/dejavu/DejaVuSansMono.ttf"
font      = ImageFont.truetype(FONT_PATH, FONT_SIZE)
font_bold = ImageFont.truetype(FONT_PATH, FONT_SIZE + 1)
font_sm   = ImageFont.truetype(FONT_PATH, FONT_SIZE - 2)

DIAGRAM = r"""
  Fig 4  —  Harvest Bypass Signal Flow per Tile
  ══════════════════════════════════════════════════════════════════════════════════

  EDC ring enters the tile from above (Segment A ↓ DOWN)

                         ring in  ◄─── from tile above (Y+1)
                            │
                            │  edc_ingress_intf  (NOC router input)
                            ▼
  ┌───────────────────────────────────────────────────────────────────────────┐
  │   NOC/Dispatch router side                                                │
  │                                                                           │
  │   tt_edc1_serial_bus_demux   (edc_mux_demux_sel driven by eFuse/ISO_EN)  │
  │   ┌──────────────────────────────────────────────────────────────┐        │
  │   │                     in ◄── edc ring                          │        │
  │   │                      │                                       │        │
  │   │            ┌─────────┴──────────┐                            │        │
  │   │            │                    │                            │        │
  │   │   sel=0 ───▼───            sel=1▼                           │        │
  │   │   out0 (NORMAL)            out1 (BYPASS)                    │        │
  │   └──────────────────────────────────────────────────────────────┘        │
  │            │                            │                                 │
  └────────────┼────────────────────────────┼─────────────────────────────────┘
               │                            │
               │ edc_egress_intf            │ edc_egress_t6_byp_intf
               │ (into tile core)           │ (combinational bypass wire,
               │                            │  NO clock, stays inside tile)
               ▼                            │
  ┌───────────────────────┐                 │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
  │  Tile EDC sub-chain   │                 │
  │  (aiclk domain)       │                 │ bypass wire (pure wire, no FF) │
  │                       │                 │
  │  sel=0: ALIVE tile    │                 │                                │
  │  ┌─────────────────┐  │                 │
  │  │ T0→T1→L1→T3→T2  │  │                 │                                │
  │  │  (Tensix cores) │  │                 │
  │  └─────────────────┘  │                 │                                │
  │                       │                 │
  │  sel=1: HARVESTED ✗   │                 │                                │
  │  ┌─────────────────┐  │                 │
  │  │  aiclk STOPPED  │  │                 │                                │
  │  │  sub-cores dead │  │                 │
  │  └─────────────────┘  │                 │                                │
  └───────────────────────┘                 │
               │                            │                                │
               │ ovl_egress_intf            │ edc_ingress_t6_byp_intf
               │ (from BIU/overlay out)     │                                │
               │                            │
               ▼                            ▼                                │
  ┌───────────────────────────────────────────────────────────────────────────┐
  │   Overlay / BIU side                                                      │
  │                                                                           │
  │   tt_edc1_serial_bus_mux   (same edc_mux_demux_sel signal)               │
  │   ┌──────────────────────────────────────────────────────────────┐        │
  │   │   in0 ◄── ovl_egress_intf    (BIU/overlay normal output)     │        │
  │   │   in1 ◄── edc_ingress_t6_byp_intf  (bypass wire from DEMUX) │        │
  │   │                      │                                       │        │
  │   │            ┌─────────┴──────────┐                            │        │
  │   │   sel=0 ───▼───            sel=1▼                           │        │
  │   │   in0 taken (NORMAL)       in1 taken (BYPASS)               │        │
  │   │                      │                                       │        │
  │   │                     out ──► edc_egress_intf (into ring)      │        │
  │   └──────────────────────────────────────────────────────────────┘        │
  └───────────────────────────────────────────────────────────────────────────┘
                            │
                            │  edc_egress_intf[x*5+y]
                            ▼
                         ring out ──► to tile below (Y−1)  /  or BIU if Y=4

  ══════════════════════════════════════════════════════════════════════════════════
  sel=0  (tile ALIVE)    : DEMUX out0 → tile sub-chain → MUX in0 → ring
  sel=1  (tile HARVESTED): DEMUX out1 ─ ─ bypass wire ─ ─► MUX in1 → ring
                           aiclk sub-chain entirely skipped (combinational bypass)
  ══════════════════════════════════════════════════════════════════════════════════
  NOTE: Y=3 (Dispatch/Router) has bypass RTL present but sel is FIXED to 0
        (never harvested in N1B0) — bypass path structurally exists, never active.
  ══════════════════════════════════════════════════════════════════════════════════
"""

lines = DIAGRAM.split("\n")
# Remove leading/trailing blank lines
while lines and lines[0].strip() == "":
    lines.pop(0)
while lines and lines[-1].strip() == "":
    lines.pop()

# Measure
scratch = Image.new("RGB", (1, 1))
dc = ImageDraw.Draw(scratch)
line_h = FONT_SIZE + 3
max_w = max(dc.textlength(l, font=font) for l in lines)

img_w = int(max_w) + PAD * 2
img_h = line_h * len(lines) + PAD * 2

img = Image.new("RGB", (img_w, img_h), BG)
draw = ImageDraw.Draw(img)

y = PAD
for i, line in enumerate(lines):
    # Colour coding
    if line.startswith("  Fig 4") or line.startswith("  ══"):
        color = BLUE
        f = font_bold
    elif "sel=0" in line and "NORMAL" in line:
        color = GREEN
        f = font
    elif "sel=1" in line and ("BYPASS" in line or "HARVESTED" in line):
        color = RED
        f = font
    elif line.strip().startswith("NOTE:") or line.strip().startswith("sel="):
        color = (80, 80, 80)
        f = font_sm
    else:
        color = BLACK
        f = font
    draw.text((PAD, y), line, font=f, fill=color)
    y += line_h

img.save(OUT, "PNG")
print(f"Saved: {OUT}  ({img_w}×{img_h})")

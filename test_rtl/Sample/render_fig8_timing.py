#!/usr/bin/env python3.11
"""
Fig 8 — EDC Toggle Handshake Timing Diagram
Draw using PIL graphical primitives (lines, rectangles, text).
Shows req_tgl / data / ack_tgl waveforms across the ~4-cycle fragment transfer.
"""

from PIL import Image, ImageDraw, ImageFont
import os

OUT = "/secure_data_from_tt/20260221/DOC/N1B0/edc_diagrams/08_toggle_handshake_timing.png"

# ── Fonts ─────────────────────────────────────────────────────────────────────
FP = "/usr/share/fonts/dejavu/DejaVuSansMono.ttf"
f11 = ImageFont.truetype(FP, 11)
f12 = ImageFont.truetype(FP, 12)
f13 = ImageFont.truetype(FP, 13)
f15 = ImageFont.truetype(FP, 15)
f17 = ImageFont.truetype(FP, 17)

# ── Colors ────────────────────────────────────────────────────────────────────
BG      = (255, 255, 255)
BLACK   = ( 20,  20,  20)
BLUE    = (  0,  80, 160)
GRAY    = (160, 160, 160)
LGRAY   = (220, 220, 220)
DGRAY   = ( 90,  90,  90)
RED     = (180,  30,  30)
GREEN   = ( 20, 130,  40)
ORANGE  = (190,  90,   0)
PURPLE  = (110,  30, 160)
CDC_BG  = (255, 248, 220)   # light amber — CDC zone
WAIT_BG = (255, 235, 210)   # light orange — WAIT_ACK state
DONE_BG = (210, 240, 215)   # light green  — ACCEPTED state
IDLE_BG = (235, 235, 235)

# ── Layout ────────────────────────────────────────────────────────────────────
SIG_W   = 200    # signal-name column width
CYC_W   = 175    # pixels per cycle column
ROW_H   = 68     # height of each signal row
PAD     = 22
TITLE_H = 78
HDR_H   = 38     # cycle-label header height
WH      = 24     # half-height of waveform (total swing = 2*WH)

# Cycles: index 0 = N-1 (context), 1=N, 2=N+1(CDC), 3=N+2, 4=N+3, 5=N+4
CYC_LABELS = [
    ("N−1", "(prev frg\ncontext)"),
    ("N", "(node drives\nreq_tgl+data)"),
    ("N+1", "(CDC crossing\nasync)"),
    ("N+2", "(BIU echoes\nack_tgl)"),
    ("N+3", "(node sees\nack == req)"),
    ("N+4", "(next frg\nbegins)"),
]
NC = len(CYC_LABELS)

# Signal rows
ROWS = [
    "ai_clk\n(node)",
    "req_tgl\n[1:0]",
    "data\n[15:0]",
    "data_p\n[0]",
    "─── CDC ───\n(domain cross)",
    "ack_tgl\n[1:0]",
    "node\nstate",
]
NR = len(ROWS)

W = PAD + SIG_W + CYC_W * NC + PAD
H = PAD + TITLE_H + HDR_H + ROW_H * NR + 90 + PAD

img  = Image.new("RGB", (W, H), BG)
d    = ImageDraw.Draw(img)

# ── Coordinate helpers ────────────────────────────────────────────────────────
def cx(i):   return PAD + SIG_W + i * CYC_W          # left x of cycle i
def cx_mid(i): return cx(i) + CYC_W // 2
def ry(i):   return PAD + TITLE_H + HDR_H + i * ROW_H  # top y of row i
def ry_mid(i): return ry(i) + ROW_H // 2
def ry_hi(i):  return ry_mid(i) - WH
def ry_lo(i):  return ry_mid(i) + WH

WAVE_TOP = PAD + TITLE_H + HDR_H
WAVE_BOT = WAVE_TOP + ROW_H * NR

# ── Draw helpers ──────────────────────────────────────────────────────────────
def hline(x0, x1, y, color, width=2):
    d.line([(x0, y), (x1, y)], fill=color, width=width)

def vline(x, y0, y1, color, width=2):
    d.line([(x, y0), (x, y1)], fill=color, width=width)

def draw_clock_row(row, x0, x1, color, half_w=None):
    """Draw a simple square-wave clock between x0 and x1."""
    if half_w is None:
        half_w = CYC_W // 4
    x = x0
    y_hi = ry_hi(row)
    y_lo = ry_lo(row)
    # start low
    while x < x1:
        xe = min(x + half_w, x1)
        hline(x, xe, y_lo, color)
        x = xe
        if x >= x1: break
        vline(x, y_lo, y_hi, color)           # rising
        xe = min(x + half_w, x1)
        hline(x, xe, y_hi, color)
        x = xe
        if x >= x1: break
        vline(x, y_hi, y_lo, color)           # falling

def draw_bus_stable(row, x0, x1, label, color, label_color=None, fill=None):
    """Draw a stable bus value (two rails + optional fill + label)."""
    if label_color is None: label_color = color
    notch = 10
    y_hi = ry_hi(row)
    y_lo = ry_lo(row)
    y_mid = ry_mid(row)
    # fill
    if fill:
        d.polygon([
            (x0+notch, y_hi), (x1-notch, y_hi),
            (x1, y_mid),      (x1-notch, y_lo),
            (x0+notch, y_lo), (x0, y_mid)
        ], fill=fill)
    # top rail
    hline(x0 + notch, x1 - notch, y_hi, color)
    # bottom rail
    hline(x0 + notch, x1 - notch, y_lo, color)
    # left chevron
    d.line([(x0+notch, y_hi), (x0, y_mid)], fill=color, width=2)
    d.line([(x0, y_mid), (x0+notch, y_lo)], fill=color, width=2)
    # right chevron
    d.line([(x1-notch, y_hi), (x1, y_mid)], fill=color, width=2)
    d.line([(x1, y_mid), (x1-notch, y_lo)], fill=color, width=2)
    # label
    tw = int(d.textlength(label, font=f11))
    tx = (x0 + x1) // 2 - tw // 2
    d.text((tx, y_mid - 7), label, font=f11, fill=label_color)

def draw_bus_x(row, x, color):
    """Draw X (transition) across the bus rails at position x."""
    notch = 10
    y_hi = ry_hi(row)
    y_lo = ry_lo(row)
    d.line([(x-notch, y_hi), (x+notch, y_lo)], fill=color, width=2)
    d.line([(x-notch, y_lo), (x+notch, y_hi)], fill=color, width=2)

def draw_bit_high(row, x0, x1, color):
    hline(x0, x1, ry_hi(row), color)

def draw_bit_low(row, x0, x1, color):
    hline(x0, x1, ry_lo(row), color)

def draw_rise(row, x, color):
    vline(x, ry_lo(row), ry_hi(row), color)

def draw_fall(row, x, color):
    vline(x, ry_hi(row), ry_lo(row), color)

def draw_state_box(row, x0, x1, label, bg, fg=BLACK):
    y0 = ry_hi(row) - 2
    y1 = ry_lo(row) + 2
    d.rectangle([x0+2, y0, x1-2, y1], fill=bg, outline=fg, width=1)
    tw = int(d.textlength(label, font=f11))
    tx = (x0 + x1) // 2 - tw // 2
    ty = (y0 + y1) // 2 - 7
    d.text((tx, ty), label, font=f11, fill=fg)

def center_text(txt, x0, x1, y, font, color):
    tw = int(d.textlength(txt, font=font))
    d.text(((x0+x1)//2 - tw//2, y), txt, font=font, fill=color)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. TITLE
# ═══════════════════════════════════════════════════════════════════════════════
d.text((PAD, PAD), "Fig 8  —  EDC Toggle Handshake Timing  (one fragment transfer ≈ 4 AI-clock cycles)",
       font=f17, fill=BLUE)
d.text((PAD, PAD+22),
       "Scenario: T0 UNPACK node (ai_clk) transfers frg[N] to BIU (noc_clk) via req_tgl / ack_tgl protocol.",
       font=f12, fill=DGRAY)
d.text((PAD, PAD+38),
       "req_tgl alternates 2'b01 ↔ 2'b10 each fragment.  BIU echoes ack_tgl = req_tgl to confirm receipt.",
       font=f12, fill=DGRAY)
d.text((PAD, PAD+54),
       "The ring transport path (connectors / mux / demux) is purely combinational — no clock on the wires.",
       font=f12, fill=ORANGE)

# ═══════════════════════════════════════════════════════════════════════════════
# 2. CDC ZONE SHADING (cycle N+1 = index 2)
# ═══════════════════════════════════════════════════════════════════════════════
cdc_x0 = cx(2)
cdc_x1 = cx(3)
d.rectangle([cdc_x0, WAVE_TOP, cdc_x1, WAVE_BOT], fill=CDC_BG)

# ═══════════════════════════════════════════════════════════════════════════════
# 3. CYCLE HEADER
# ═══════════════════════════════════════════════════════════════════════════════
hdr_top = PAD + TITLE_H
for i, (cyc, sub) in enumerate(CYC_LABELS):
    x0, x1 = cx(i), cx(i+1)
    # shade N-1 column
    if i == 0:
        d.rectangle([x0, hdr_top, x1, WAVE_BOT], fill=(248,248,248))
    # cycle label
    col = GRAY if i == 0 else BLUE
    center_text(cyc, x0, x1, hdr_top + 2, f15, col)
    # sub-label
    sub_col = ORANGE if i == 2 else (GRAY if i == 0 else DGRAY)
    for j, sl in enumerate(sub.split("\n")):
        center_text(sl, x0, x1, hdr_top + 18 + j*13, f11, sub_col)

# ═══════════════════════════════════════════════════════════════════════════════
# 4. GRID LINES
# ═══════════════════════════════════════════════════════════════════════════════
for i in range(NC + 1):
    x = cx(i)
    col = GRAY if i in (0, 1) else LGRAY
    vline(x, WAVE_TOP, WAVE_BOT, col, width=1)

for i in range(NR + 1):
    y = ry(i)
    hline(PAD, W - PAD, y, LGRAY, width=1)

# ═══════════════════════════════════════════════════════════════════════════════
# 5. SIGNAL NAME LABELS
# ═══════════════════════════════════════════════════════════════════════════════
for i, sig in enumerate(ROWS):
    parts = sig.split("\n")
    total_h = len(parts) * 14
    yt = ry_mid(i) - total_h // 2
    is_sep = "CDC" in sig
    for p in parts:
        color = ORANGE if is_sep else BLACK
        fw = f11 if is_sep else f13
        d.text((PAD + 4, yt), p, font=fw, fill=color)
        yt += 14

# ═══════════════════════════════════════════════════════════════════════════════
# 6. WAVEFORMS
# ═══════════════════════════════════════════════════════════════════════════════

# ── Row 0: ai_clk ─────────────────────────────────────────────────────────────
draw_clock_row(0, cx(0), cx(1), GRAY, half_w=CYC_W // 5)      # context (gray)
draw_clock_row(0, cx(1), cx(NC), BLACK, half_w=CYC_W // 5)     # active cycles

# Label
d.text((cx(1) + 4, ry_hi(0) - 14), "AI clock (node)", font=f11, fill=DGRAY)

# ── Row 1: req_tgl[1:0] ───────────────────────────────────────────────────────
# N-1: was 2'b10 (previous fragment's req)
draw_bus_stable(1, cx(0), cx(1), "2'b10  (prev frag)", GRAY, fill=(245,245,245))
# transition X at N
draw_bus_x(1, cx(1), BLACK)
# N … N+3: stable 2'b01
draw_bus_stable(1, cx(1), cx(5), "req_tgl = 2'b01  (set at N, held until ack received)", BLACK, fill=(240,245,255))
# transition X at N+4
draw_bus_x(1, cx(5), BLACK)
# N+4: next fragment toggles to 2'b10
draw_bus_stable(1, cx(5), cx(NC), "2'b10  (next frag)", GREEN, fill=(225,245,225))

# Annotation: "node TOGGLES here"
d.text((cx(1) + 3, ry_hi(1) - 15), "① node toggles", font=f11, fill=BLACK)

# ── Row 2: data[15:0] ─────────────────────────────────────────────────────────
draw_bus_stable(2, cx(0), cx(1), "prev frag data", GRAY, fill=(245,245,245))
draw_bus_x(2, cx(1), BLACK)
draw_bus_stable(2, cx(1), cx(5), "fragment data  e.g. frg[2]=0x8205  (stable, driven by node)", BLACK, fill=(240,245,255))
draw_bus_x(2, cx(5), BLACK)
draw_bus_stable(2, cx(5), cx(NC), "next frag", GREEN, fill=(225,245,225))

# ── Row 3: data_p[0] ──────────────────────────────────────────────────────────
# N-1: low (context)
draw_bit_low(3, cx(0), cx(1), GRAY)
# transition at N
draw_rise(3, cx(1), BLACK)
# N to N+3: HIGH (example: parity=1 for 0x8205)
draw_bit_high(3, cx(1), cx(5), BLACK)
d.text((cx(2) + 4, ry_hi(3) + 2), "odd parity of data[15:0]  (stable)", font=f11, fill=DGRAY)
# transition at N+4
draw_fall(3, cx(5), BLACK)
draw_bit_low(3, cx(5), cx(NC), GREEN)

# ── Row 4: CDC separator ──────────────────────────────────────────────────────
# Draw a shaded band label across the CDC column
d.text((cdc_x0 + 6, ry_mid(4) - 20),
       "◄──────── CDC domain crossing ────────►", font=f11, fill=ORANGE)
d.text((cdc_x0 + 6, ry_mid(4) - 5),
       "req_tgl toggle propagates combinationally", font=f11, fill=ORANGE)
d.text((cdc_x0 + 6, ry_mid(4) + 9),
       "through ring wires; BIU samples on noc_clk", font=f11, fill=ORANGE)

# ── Row 5: ack_tgl[1:0] ───────────────────────────────────────────────────────
# N-1, N, N+1: previous ack 2'b10
draw_bus_stable(5, cx(0), cx(3), "2'b10  (prev ack, unchanged)", GRAY, fill=(245,245,245))
# transition at N+2
draw_bus_x(5, cx(3), RED)
# N+2 … beyond: 2'b01 (BIU echoes req_tgl)
draw_bus_stable(5, cx(3), cx(NC), "ack_tgl = 2'b01  (BIU echoes req_tgl, NOC clock domain)", RED, fill=(255,235,235))

d.text((cx(3) + 3, ry_hi(5) - 15), "③ BIU echoes", font=f11, fill=RED)
d.text((cx(4) + 3, ry_hi(5) - 15), "④ node: ack==req", font=f11, fill=GREEN)

# ── Row 6: node state ─────────────────────────────────────────────────────────
draw_state_box(6, cx(0), cx(1), "IDLE / prev frag done", IDLE_BG, DGRAY)
draw_state_box(6, cx(1), cx(4), "WAIT_ACK  (req_tgl driven, waiting ack_tgl == req_tgl)", WAIT_BG, ORANGE)
draw_state_box(6, cx(4), cx(5), "ACCEPTED", DONE_BG, GREEN)
draw_state_box(6, cx(5), cx(NC), "next frag", (230,245,230), GREEN)

# ═══════════════════════════════════════════════════════════════════════════════
# 7. ANNOTATIONS BELOW WAVEFORMS
# ═══════════════════════════════════════════════════════════════════════════════
ann_y0 = WAVE_BOT + 10

ann_items = [
    (cx(1), cx(2),  "①  Node drives req_tgl (toggle from 10→01),\n    data[15:0], data_p[0] simultaneously",          BLACK),
    (cx(2), cx(3),  "②  Toggle propagates via\n    combinational ring wires\n    (no clock, pure wire delay)",           ORANGE),
    (cx(3), cx(4),  "③  BIU (noc_clk) samples req_tgl,\n    echoes ack_tgl = 2'b01\n    (confirms frg[N] received)",    RED),
    (cx(4), cx(5),  "④  Node (ai_clk) sees ack_tgl == req_tgl\n    → marks fragment ACCEPTED\n    → advances frg counter", GREEN),
    (cx(5), cx(NC), "⑤  Next fragment:\n    req_tgl toggles 01→10\n    data ← frg[N+1]",                                  BLUE),
]

for x0, x1, txt, color in ann_items:
    xc = (x0 + x1) // 2
    # dotted vertical line from waveform bottom
    for yy in range(WAVE_BOT, ann_y0, 3):
        d.point((xc, yy), fill=LGRAY)
    yt = ann_y0
    for line in txt.split("\n"):
        tw = int(d.textlength(line, font=f11))
        d.text((xc - tw // 2, yt), line, font=f11, fill=color)
        yt += 14

# ═══════════════════════════════════════════════════════════════════════════════
# 8. OUTER BORDER
# ═══════════════════════════════════════════════════════════════════════════════
d.rectangle([PAD-3, PAD-3, W-PAD+3, H-PAD+3], outline=BLUE, width=2)

img.save(OUT, "PNG")
print(f"[ok] {OUT}  ({W}×{H})")

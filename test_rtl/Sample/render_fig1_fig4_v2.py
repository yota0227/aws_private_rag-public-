#!/usr/bin/env python3.11
"""
Clean redesign of Fig 1 and Fig 4.
Fig 4: single-tile harvest bypass — Seg A (DEMUX→chain/bypass→MUX) vs Seg B (loopback)
Fig 1: full 5-tile column — both rails visible, each tile clearly labeled
"""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = "/secure_data_from_tt/20260221/DOC/N1B0/edc_diagrams"
FP  = "/usr/share/fonts/dejavu/DejaVuSansMono.ttf"

def fnt(n): return ImageFont.truetype(FP, n)
f9=fnt(9); f10=fnt(10); f11=fnt(11); f12=fnt(12); f13=fnt(13); f14=fnt(14); f16=fnt(16); f18=fnt(18)

BG     = (255,255,255)
BLACK  = (20,20,20)
DGRAY  = (80,80,80)
LGRAY  = (200,200,200)
BLUE   = (0,80,180)
LB_BG  = (232,244,255)   # light blue bg
TEAL   = (0,120,110)
LT_BG  = (230,250,245)   # light teal bg
ORANGE = (180,90,0)
OR_BG  = (255,248,220)
GREEN  = (10,130,40)
RED    = (180,30,30)
CHAIN_BG = (235,243,255)
CHAIN_C  = (0,100,160)
NOTE_BG  = (255,250,230)

def save(img, name):
    p = os.path.join(OUT, name)
    img.save(p, "PNG")
    print(f"[ok] {p}  ({img.size[0]}×{img.size[1]})")

def bx(d, x0,y0,x1,y1, fill=BG, outline=BLACK, lw=2):
    d.rectangle([x0,y0,x1,y1], fill=fill, outline=outline, width=lw)

def txt(d, s, x, y, font=f11, fill=BLACK):
    d.text((x, y), s, font=font, fill=fill)

def ctxt(d, s, cx, y, font=f11, fill=BLACK):
    w = int(d.textlength(s, font=font))
    d.text((cx - w//2, y), s, font=font, fill=fill)

def arr_down(d, x, y0, y1, c=BLACK, w=2):
    d.line([(x,y0),(x,y1-8)], fill=c, width=w)
    d.polygon([(x-6,y1-10),(x+6,y1-10),(x,y1)], fill=c)

def arr_up(d, x, y0, y1, c=BLACK, w=2):
    # y0 is bottom, y1 is top (arrow points up to y1)
    d.line([(x,y0),(x,y1+8)], fill=c, width=w)
    d.polygon([(x-6,y1+10),(x+6,y1+10),(x,y1)], fill=c)

def arr_right(d, x0, x1, y, c=BLACK, w=2):
    d.line([(x0,y),(x1-8,y)], fill=c, width=w)
    d.polygon([(x1-10,y-5),(x1-10,y+5),(x1,y)], fill=c)

def arr_left(d, x0, x1, y, c=BLACK, w=2):
    d.line([(x0+8,y),(x1,y)], fill=c, width=w)
    d.polygon([(x0+10,y-5),(x0+10,y+5),(x0,y)], fill=c)

def dash_v(d, x, y0, y1, c=RED, dash=8, gap=5, w=2):
    y = y0
    while y < y1:
        ye = min(y+dash, y1)
        d.line([(x,y),(x,ye)], fill=c, width=w)
        y += dash+gap

def dash_h(d, x0, x1, y, c=RED, dash=8, gap=5, w=2):
    x = x0
    while x < x1:
        xe = min(x+dash, x1)
        d.line([(x,y),(xe,y)], fill=c, width=w)
        x += dash+gap

# ═════════════════════════════════════════════════════════════════════════════
# FIG 4  — Harvest Bypass Signal Flow (single tile) — clean signal-flow guide
# ═════════════════════════════════════════════════════════════════════════════
def draw_fig4():
    W, H = 1160, 860
    img = Image.new("RGB", (W,H), BG)
    d   = ImageDraw.Draw(img)

    # ── title ─────────────────────────────────────────────────────────────────
    TH = 58
    bx(d,0,0,W,TH,fill=(228,238,255),lw=0)
    ctxt(d,"Fig 4 — Harvest Bypass Signal Flow per Tile  (Tensix Y=0/1/2)", W//2, 6, f18, BLUE)
    ctxt(d,"sel=0 → ALIVE  ·  sel=1 → HARVESTED  ·  same edc_mux_demux_sel drives both DEMUX and MUX", W//2, 32, f12, DGRAY)

    # ── layout ────────────────────────────────────────────────────────────────
    # Left strip:  Seg B loopback rail (x=30..220)
    # Center-Right: Seg A signal flow (x=240..1130)
    # Tile box spans full width
    TL, TR = 30,  1130
    TT, TB = TH+60, 730
    SPLIT  = 222          # divider between Seg B and Seg A inside tile

    SB_CX  = (TL + SPLIT) // 2    # 126
    SA_X0  = SPLIT + 14
    SA_CX  = (SPLIT + TR) // 2    # center of Seg A column

    # ── outer tile box ────────────────────────────────────────────────────────
    bx(d, TL,TT, TR,TB, fill=(248,250,255), outline=(60,80,200), lw=3)
    txt(d,"  Tile  (tt_trin_noc_niu_router_wrap  +  tt_tensix_with_l1  +  tt_neo_overlay_wrapper)",
        TL+8, TT+5, f11, (60,80,200))
    d.line([(TL+4,TT+20),(TR-4,TT+20)], fill=LGRAY, width=1)
    d.line([(SPLIT,TT+22),(SPLIT,TB-4)], fill=LGRAY, width=1)

    # ─────────────────────────────────────────────────────────────────────────
    # SEG B — left strip (pure passthrough, no bypass logic)
    # ─────────────────────────────────────────────────────────────────────────
    # Header
    bx(d, TL+4,TT+26, SPLIT-4,TT+44, fill=LT_BG, outline=TEAL, lw=1)
    ctxt(d,"Segment B  (↑ loopback)", SB_CX, TT+28, f10, TEAL)

    # Loopback repeater box — compact, just module name
    LB_Y0, LB_Y1 = TT+60, TT+200
    bx(d, TL+4,LB_Y0, SPLIT-4,LB_Y1, fill=LT_BG, outline=TEAL, lw=2)
    ctxt(d,"overlay_loopback", SB_CX, LB_Y0+10, f11, TEAL)
    ctxt(d,"_repeater",        SB_CX, LB_Y0+26, f11, TEAL)
    ctxt(d,"(aon_clk)",        SB_CX, LB_Y0+46, f11, TEAL)
    d.line([(TL+8,LB_Y0+66),(SPLIT-8,LB_Y0+66)], fill=LGRAY, width=1)
    ctxt(d,"No DEMUX",  SB_CX, LB_Y0+72,  f10, TEAL)
    ctxt(d,"No MUX",    SB_CX, LB_Y0+88,  f10, TEAL)
    ctxt(d,"No bypass", SB_CX, LB_Y0+104, f10, TEAL)

    # Seg B arrows: enters bottom → through repeater → exits top
    arr_up(d, SB_CX, TB-4,  LB_Y1, TEAL, w=3)
    arr_up(d, SB_CX, LB_Y0, TT+22, TEAL, w=3)

    # Seg B signal labels (outside tile)
    ctxt(d,"loopback_edc_ingress_intf[x*5+y]", SB_CX, TB+8,  f9, TEAL)
    ctxt(d,"← from tile below / U-turn",       SB_CX, TB+22, f9, TEAL)
    ctxt(d,"loopback_edc_egress_intf[x*5+y]",  SB_CX, TT-32, f9, TEAL)
    ctxt(d,"→ to tile above / BIU(Y=4)",        SB_CX, TT-18, f9, TEAL)

    # ─────────────────────────────────────────────────────────────────────────
    # SEG A — right portion (DEMUX → chain/bypass → MUX)
    # ─────────────────────────────────────────────────────────────────────────
    # Header
    bx(d, SPLIT+4,TT+26, TR-4,TT+44, fill=LB_BG, outline=BLUE, lw=1)
    ctxt(d,"Segment A  (↓ direct)", (SPLIT+TR)//2, TT+28, f10, BLUE)

    BYPASS_X = TR - 46    # bypass wire runs along right edge of Seg A area

    # ── DEMUX ─────────────────────────────────────────────────────────────────
    DY0, DY1 = TT+54, TT+148
    bx(d, SA_X0,DY0, TR-4,DY1, fill=OR_BG, outline=ORANGE, lw=2)
    ctxt(d,"DEMUX  (tt_edc1_serial_bus_demux  ·  tt_trin_noc_niu_router_wrap)",
         (SA_X0+TR-4)//2, DY0+5, f12, ORANGE)
    d.line([(SA_X0+4,DY0+22),(TR-8,DY0+22)], fill=LGRAY, width=1)
    txt(d, "  in   ←  edc_ingress_intf",               SA_X0+8, DY0+28, f11, BLACK)
    txt(d, "  sel=0  out0 ──►  NOC nodes + aiclk sub-chain     [ALIVE]",     SA_X0+8, DY0+48, f12, GREEN)
    txt(d, "  sel=1  out1 ──►  edc_egress_t6_byp_intf  (bypass wire)   [HARVESTED]", SA_X0+8, DY0+70, f12, RED)

    # Seg A in arrow
    RING_X = SA_X0 + 140
    arr_down(d, RING_X, TT-40, DY0, BLUE, w=3)
    txt(d,"edc_ingress_intf[x*5+y]  ←  ring from tile above", RING_X+8, TT-38, f10, BLUE)

    # sel=0 arrow: DEMUX → chain
    CHAIN_CX = SA_X0 + 120
    CHAIN_Y0 = DY1 + 30
    CHAIN_Y1 = CHAIN_Y0 + 140
    arr_down(d, CHAIN_CX, DY1, CHAIN_Y0, GREEN, w=2)
    ctxt(d,"out0 sel=0", CHAIN_CX, DY1+4, f10, GREEN)

    # sel=1 horizontal stub from DEMUX to bypass wire
    d.line([(SA_X0+490, DY0+77),(BYPASS_X, DY0+77)], fill=RED, width=2)
    dash_v(d, BYPASS_X, DY0+77, CHAIN_Y1+34, RED, dash=9, gap=5, w=2)
    ctxt(d,"bypass", BYPASS_X+4, (DY1+CHAIN_Y0+CHAIN_Y1)//3,      f10, RED)
    ctxt(d,"wire",   BYPASS_X+4, (DY1+CHAIN_Y0+CHAIN_Y1)//3+13,   f10, RED)

    # ── Tile sub-chain ────────────────────────────────────────────────────────
    CH_X1 = BYPASS_X - 10
    bx(d, SA_X0,CHAIN_Y0, CH_X1,CHAIN_Y1, fill=CHAIN_BG, outline=CHAIN_C, lw=2)
    ctxt(d,"Tile EDC Sub-Chain  (aiclk domain)", (SA_X0+CH_X1)//2, CHAIN_Y0+6, f13, CHAIN_C)
    d.line([(SA_X0+4,CHAIN_Y0+24),(CH_X1-4,CHAIN_Y0+24)], fill=LGRAY, width=1)
    ctxt(d,"T0  →  T1  →  (T6_MISC + L1 partition)  →  T3  →  T2",
         (SA_X0+CH_X1)//2, CHAIN_Y0+30, f11, BLACK)
    ctxt(d,"~80 EDC nodes per tile", (SA_X0+CH_X1)//2, CHAIN_Y0+48, f10, DGRAY)
    d.line([(SA_X0+4,CHAIN_Y0+64),(CH_X1-4,CHAIN_Y0+64)], fill=LGRAY, width=1)
    ctxt(d,"sel=0  ALIVE:    ai_clk running — nodes report errors",
         (SA_X0+CH_X1)//2, CHAIN_Y0+70, f11, GREEN)
    ctxt(d,"sel=1  HARVESTED: ai_clk STOPPED — chain bypassed via bypass wire",
         (SA_X0+CH_X1)//2, CHAIN_Y0+90, f11, RED)
    ctxt(d,"(NOC router nodes always active on aon_clk; i_harvest_en=1 gates errors)",
         (SA_X0+CH_X1)//2, CHAIN_Y0+112, f10, DGRAY)

    # chain → MUX arrow
    MUX_Y0 = CHAIN_Y1 + 30
    MUX_Y1 = MUX_Y0 + 96
    arr_down(d, CHAIN_CX, CHAIN_Y1, MUX_Y0, GREEN, w=2)
    ctxt(d,"sel=0", CHAIN_CX, CHAIN_Y1+4, f10, GREEN)

    # ── MUX ──────────────────────────────────────────────────────────────────
    bx(d, SA_X0,MUX_Y0, TR-4,MUX_Y1, fill=OR_BG, outline=ORANGE, lw=2)
    ctxt(d,"MUX  (tt_edc1_serial_bus_mux  ·  tt_neo_overlay_wrapper)",
         (SA_X0+TR-4)//2, MUX_Y0+5, f12, ORANGE)
    d.line([(SA_X0+4,MUX_Y0+22),(TR-8,MUX_Y0+22)], fill=LGRAY, width=1)
    txt(d, "  sel=0  in0 ◄──  ovl_egress_intf  (sub-chain output)          [ALIVE]",      SA_X0+8, MUX_Y0+28, f12, GREEN)
    txt(d, "  sel=1  in1 ◄──  edc_ingress_t6_byp_intf  (bypass wire)       [HARVESTED]",  SA_X0+8, MUX_Y0+50, f12, RED)
    d.line([(SA_X0+4,MUX_Y0+70),(TR-8,MUX_Y0+70)], fill=LGRAY, width=1)
    txt(d, "  out  ──►  edc_egress_intf[x*5+y]",                                          SA_X0+8, MUX_Y0+76, f12, BLUE)

    # bypass wire → MUX in1
    IN1_Y = MUX_Y0 + 57
    d.line([(SA_X0+490, IN1_Y),(BYPASS_X, IN1_Y)], fill=RED, width=2)
    d.polygon([(SA_X0+500,IN1_Y-5),(SA_X0+500,IN1_Y+5),(SA_X0+490,IN1_Y)], fill=RED)

    # Seg A out arrow
    arr_down(d, RING_X, MUX_Y1, TB+10, BLUE, w=3)
    txt(d,"edc_egress_intf[x*5+y]  →  ring to tile below", RING_X+8, TB+12, f10, BLUE)

    # ── Signal flow summary (footer) ──────────────────────────────────────────
    SUM_Y = TB + 36
    bx(d, 2,SUM_Y, W-2,H-4, fill=NOTE_BG, outline=ORANGE, lw=1)
    ctxt(d,"Signal Flow Summary", W//2, SUM_Y+5, f13, ORANGE)
    txt(d,"  sel=0  ALIVE:     edc_ingress → DEMUX out0 → NOC nodes + aiclk chain (T0→T1→T3→T2) → MUX in0 → edc_egress",
        8, SUM_Y+24, f11, GREEN)
    txt(d,"  sel=1  HARVESTED: edc_ingress → DEMUX out1 → bypass wire (pure wire, no clock) → MUX in1 → edc_egress",
        8, SUM_Y+42, f11, RED)
    txt(d,"  Seg B (any sel):  loopback_edc_ingress → overlay_loopback_repeater (aon_clk) → loopback_edc_egress",
        8, SUM_Y+60, f11, TEAL)

    bx(d,0,0,W,H,fill=None,outline=BLUE,lw=2)
    save(img, "04_harvest_bypass_signal_flow.png")


# ═════════════════════════════════════════════════════════════════════════════
# FIG 1  — Full Column: Complete EDC Ring (5 tiles, both segments)
# Each tile shows: NOC boundary (DEMUX-A | MUX-B) / shared sub-chain / OVL boundary (MUX-A | DEMUX-B)
# Both Seg A (↓) and Seg B (↑) share the same sub-chain and have symmetric bypass wires.
# ═════════════════════════════════════════════════════════════════════════════
def draw_fig1():
    W, H = 1520, 2400
    img = Image.new("RGB", (W,H), BG)
    d   = ImageDraw.Draw(img)

    # ── layout constants ───────────────────────────────────────────────────────
    SB_RAIL = 40       # left rail  (Seg B ↑)
    SA_RAIL = 1470     # right rail (Seg A ↓)
    TX0, TX1 = 100, 1410
    TILE_MID = (TX0+TX1)//2    # center divider inside tile
    # NOC/OVL inner boxes leave room on each side for bypass wires
    NB_X0, NB_X1 = TX0+40, TX1-40
    BYP_A_X = TX0+20   # Seg A bypass wire (left side, ↓)
    BYP_B_X = TX1-20   # Seg B bypass wire (right side, ↑)

    TITLE_H = 120
    T_TOPS = {4:TITLE_H+50, 3:TITLE_H+360, 2:TITLE_H+770, 1:TITLE_H+1250, 0:TITLE_H+1730}
    T_HGTS = {4:270, 3:370, 2:450, 1:450, 0:480}

    # ── title ─────────────────────────────────────────────────────────────────
    bx(d,0,0,W,TITLE_H,fill=(228,238,255),lw=0)
    ctxt(d,"Fig 1 — One Column (X=0): Complete EDC Ring — 5 Tiles + U-Turn",W//2,6,f18,BLUE)
    ctxt(d,"Both Seg A (blue ↓) and Seg B (teal ↑) traverse the SAME sub-chain in each tile.",W//2,34,f12,DGRAY)
    ctxt(d,"Each tile has: NOC boundary (DEMUX-A | MUX-B)  /  shared aiclk sub-chain  /  Overlay boundary (MUX-A | DEMUX-B)",W//2,52,f12,DGRAY)
    ctxt(d,"sel=edc_mux_demux_sel: controls BOTH bypass-A (Seg A) and bypass-B (Seg B) simultaneously",W//2,70,f11,(100,0,100))
    ctxt(d,"Seg A ↓  edc_ingress/egress_intf",W//2,90,f10,BLUE)
    ctxt(d,"Seg B ↑  loopback_edc_ingress/egress_intf",W//2,105,f10,TEAL)

    APB_Y = TITLE_H + 15
    ctxt(d,"APB4 Firmware", W//2, APB_Y, f12, DGRAY)
    arr_down(d, W//2, APB_Y+15, TITLE_H+46, DGRAY, w=2)

    def draw_connector(fy, ty):
        y0 = T_TOPS[fy]+T_HGTS[fy]; y1 = T_TOPS[ty]; mid=(y0+y1)//2
        arr_down(d, SA_RAIL, y0+2, y1-2, BLUE, w=3)
        arr_up(d, SB_RAIL, y1-2, y0+2, TEAL, w=3)
        ctxt(d,f"edc_direct_conn / edc_loopback_conn  (Y={ty}↔Y={fy})",W//2,mid-7,f10,DGRAY)

    # ── helper: draw NOC boundary row (DEMUX-A left, MUX-B right) ─────────────
    def noc_row(y0b, h, sel_note, yi):
        """NOC boundary box. y0b=box top, h=box height."""
        bx(d, NB_X0, y0b, NB_X1, y0b+h, fill=OR_BG, outline=ORANGE, lw=2)
        ctxt(d, "NOC Router Boundary  (tt_trin_noc_niu_router_wrap)"+sel_note,
             (NB_X0+NB_X1)//2, y0b+4, f11, ORANGE)
        d.line([(NB_X0+4,y0b+20),(NB_X1-4,y0b+20)], fill=LGRAY, width=1)
        d.line([(TILE_MID, y0b+22),(TILE_MID, y0b+h-2)], fill=LGRAY, width=1)
        DA = (NB_X0+TILE_MID)//2; MB = (TILE_MID+NB_X1)//2
        ctxt(d,"DEMUX-A  (edc_demuxing_when_harvested)",DA,y0b+24,f10,ORANGE)
        ctxt(d,f"in: edc_ingress_intf[x*5+{yi}]  ← Seg A",DA,y0b+38,f10,BLUE)
        ctxt(d,"sel=0 out0 → chain  [ALIVE]",DA,y0b+52,f10,GREEN)
        ctxt(d,"sel=1 out1 → bypass-A  [HARV]",DA,y0b+66,f10,RED)
        ctxt(d,"MUX-B  (loopback_mux_when_harvested)",MB,y0b+24,f10,ORANGE)
        ctxt(d,"in0: chain out → loopback_egress  [ALIVE]",MB,y0b+38,f10,TEAL)
        ctxt(d,"in1: bypass-B → loopback_egress  [HARV]",MB,y0b+52,f10,(140,80,0))
        ctxt(d,f"out: loopback_edc_egress_intf[x*5+{yi}] ↑",MB,y0b+66,f10,TEAL)

    # ── helper: draw Overlay boundary row (MUX-A left, DEMUX-B right) ─────────
    def ovl_row(y0b, h, sel_note, yi):
        bx(d, NB_X0, y0b, NB_X1, y0b+h, fill=(232,250,232), outline=GREEN, lw=2)
        ctxt(d, "Overlay Boundary  (tt_neo_overlay_wrapper)"+sel_note,
             (NB_X0+NB_X1)//2, y0b+4, f11, GREEN)
        d.line([(NB_X0+4,y0b+20),(NB_X1-4,y0b+20)], fill=LGRAY, width=1)
        d.line([(TILE_MID, y0b+22),(TILE_MID, y0b+h-2)], fill=LGRAY, width=1)
        MA = (NB_X0+TILE_MID)//2; DB = (TILE_MID+NB_X1)//2
        ctxt(d,"MUX-A  (edc_muxing_when_harvested)",MA,y0b+24,f10,ORANGE)
        ctxt(d,"in0: chain out → edc_egress  [ALIVE]",MA,y0b+38,f10,GREEN)
        ctxt(d,"in1: bypass-A → edc_egress  [HARV]",MA,y0b+52,f10,RED)
        ctxt(d,f"out: edc_egress_intf[x*5+{yi}]  ↓ Seg A",MA,y0b+66,f10,BLUE)
        ctxt(d,"DEMUX-B  (loopback_demux_when_harvested)",DB,y0b+24,f10,ORANGE)
        ctxt(d,f"in: loopback_edc_ingress_intf[x*5+{yi}]  Seg B ↑",DB,y0b+38,f10,TEAL)
        ctxt(d,"sel=0 out0 → chain  [ALIVE]",DB,y0b+52,f10,TEAL)
        ctxt(d,"sel=1 out1 → bypass-B  [HARV]",DB,y0b+66,f10,(140,80,0))

    # ── helper: draw shared sub-chain box ──────────────────────────────────────
    def chain_box(y0b, y1b, chain_label, chain_note):
        bx(d, NB_X0, y0b, NB_X1, y1b, fill=CHAIN_BG, outline=CHAIN_C, lw=2)
        cy = (y0b+y1b)//2
        ctxt(d, "Shared EDC Sub-Chain  (aiclk domain)  — traversed by Seg A ↓ and Seg B ↑",
             (NB_X0+NB_X1)//2, y0b+6, f12, CHAIN_C)
        d.line([(NB_X0+4, y0b+22),(NB_X1-4, y0b+22)], fill=LGRAY, width=1)
        ctxt(d, chain_label,  (NB_X0+NB_X1)//2, y0b+28, f12, BLACK)
        ctxt(d, chain_note,   (NB_X0+NB_X1)//2, y0b+46, f11, DGRAY)
        ctxt(d, "sel=0: aiclk running — nodes report on both Seg A and Seg B passes",
             (NB_X0+NB_X1)//2, y0b+64, f10, GREEN)
        ctxt(d, "sel=1: aiclk stopped — both seg bypass via bypass-A/B wires",
             (NB_X0+NB_X1)//2, y0b+80, f10, RED)
        # Seg A ↓ arrow inside chain (left side)
        ACX = NB_X0+20
        arr_down(d, ACX, y0b+4, y1b-4, BLUE, w=2)
        ctxt(d,"A↓", ACX, cy-6, f9, BLUE)
        # Seg B ↑ arrow inside chain (right side)
        BCX = NB_X1-20
        arr_up(d, BCX, y1b-4, y0b+4, TEAL, w=2)
        ctxt(d,"B↑", BCX, cy-6, f9, TEAL)

    # ── helper: SA/SB rail connections for a tile ──────────────────────────────
    def rail_conn(y0, y1, NOC_Y0, NOC_H, OVL_Y0, OVL_H, ut=False, ut_arrow_y=None):
        SA_IN_Y  = NOC_Y0 + 38   # DEMUX-A "in" row
        SA_OUT_Y = OVL_Y0 + 66   # MUX-A "out" row
        SB_OUT_Y = NOC_Y0 + 66   # MUX-B "out" row
        SB_IN_Y  = OVL_Y0 + 38   # DEMUX-B "in" row
        # ── Seg A ────────────────────────────────────────────────────────────
        arr_down(d, SA_RAIL, y0+2, SA_IN_Y, BLUE, w=3)
        arr_left(d, NB_X1, SA_RAIL, SA_IN_Y, BLUE, w=2)
        arr_right(d, NB_X1, SA_RAIL, SA_OUT_Y, BLUE, w=2)
        if not ut:
            arr_down(d, SA_RAIL, SA_OUT_Y, y1-2, BLUE, w=3)
        else:
            arr_down(d, SA_RAIL, SA_OUT_Y, ut_arrow_y, BLUE, w=3)
        # ── Seg B ────────────────────────────────────────────────────────────
        arr_up(d, SB_RAIL, SB_OUT_Y, y0+4, TEAL, w=3)
        arr_left(d, SB_RAIL, NB_X0, SB_OUT_Y, TEAL, w=2)
        arr_right(d, SB_RAIL, NB_X0, SB_IN_Y, TEAL, w=2)
        if not ut:
            arr_up(d, SB_RAIL, y1-4, SB_IN_Y, TEAL, w=3)
        else:
            arr_up(d, SB_RAIL, ut_arrow_y, SB_IN_Y, TEAL, w=3)

    # ── BIU tile (Y=4) ─────────────────────────────────────────────────────────
    def draw_biu():
        yi=4; y0=T_TOPS[yi]; h=T_HGTS[yi]; y1=y0+h
        bx(d, TX0,y0, TX1,y1, fill=(240,250,240), outline=(60,80,200), lw=2)
        txt(d,"  Y=4 · BIU / NOC2AXI  —  Seg A SOURCE (sends ↓)  +  Seg B TERMINUS (receives ↑)  —  never harvested",
            TX0+8, y0+6, f13, (60,80,200))
        d.line([(TX0+4,y0+24),(TX1-4,y0+24)], fill=LGRAY, width=1)
        d.line([(TILE_MID, y0+26),(TILE_MID, y1-4)], fill=LGRAY, width=1)
        # left half: Seg A source
        LA = (TX0+TILE_MID)//2
        bx(d, TX0+8, y0+30, TILE_MID-4, y1-8, fill=(225,245,225), outline=GREEN, lw=1)
        ctxt(d,"Seg A  SOURCE",LA,y0+36,f13,GREEN)
        ctxt(d,"u_edc_req_src  (tt_edc1_state_machine)",LA,y0+56,f10,DGRAY)
        ctxt(d,"serializes FW command packets",LA,y0+72,f10,DGRAY)
        ctxt(d,"→ edc_egress_intf[x*5+4]  ↓ Seg A ring",LA,y0+88,f12,BLUE)
        ctxt(d,"APB4 CSRs: CTRL/STAT/IRQ/REQ/RSP",LA,y0+110,f10,DGRAY)
        ctxt(d,"fatal/crit/noncrit IRQ → SoC",LA,y0+126,f10,RED)
        # right half: Seg B terminus
        RB = (TILE_MID+TX1)//2
        bx(d, TILE_MID+4, y0+30, TX1-8, y1-8, fill=(225,248,245), outline=TEAL, lw=1)
        ctxt(d,"Seg B  TERMINUS",RB,y0+36,f13,TEAL)
        ctxt(d,"u_edc_rsp_snk  (tt_edc1_state_machine)",RB,y0+56,f10,DGRAY)
        ctxt(d,"deserializes response packets",RB,y0+72,f10,DGRAY)
        ctxt(d,"← loopback_edc_ingress_intf[x*5+4]",RB,y0+88,f12,TEAL)
        ctxt(d,"Seg B does NOT continue past BIU",RB,y0+110,f10,DGRAY)
        ctxt(d,"(BIU is the top terminus)",RB,y0+126,f10,DGRAY)
        # SA exits right
        SA_OUT_Y = y0+90
        arr_right(d, NB_X1, SA_RAIL, SA_OUT_Y, BLUE, w=2)
        arr_down(d, SA_RAIL, SA_OUT_Y, y1-2, BLUE, w=3)
        # SB arrives from below, terminates
        SB_IN_Y = y0+90
        arr_up(d, SB_RAIL, y1-4, SB_IN_Y, TEAL, w=3)
        arr_right(d, SB_RAIL, TILE_MID+4, SB_IN_Y, TEAL, w=2)

    # ── Dispatch tile (Y=3) ────────────────────────────────────────────────────
    def draw_dispatch():
        yi=3; y0=T_TOPS[yi]; h=T_HGTS[yi]; y1=y0+h
        NOC_H=82; OVL_H=82; PAD=8
        NOC_Y0=y0+28; NOC_Y1=NOC_Y0+NOC_H
        CHAIN_Y0=NOC_Y1+PAD
        CHAIN_H = h - 28 - NOC_H - OVL_H - PAD*3 - 4
        CHAIN_Y1=CHAIN_Y0+CHAIN_H
        OVL_Y0=CHAIN_Y1+PAD; OVL_Y1=OVL_Y0+OVL_H
        bx(d, TX0,y0, TX1,y1, fill=(255,252,238), outline=(60,80,200), lw=2)
        txt(d,"  Y=3 · Dispatch/Router  —  sel FIXED=0 (never harvested in N1B0)  bypass RTL exists but inactive",
            TX0+8, y0+6, f13, (60,80,200))
        d.line([(TX0+4,y0+24),(TX1-4,y0+24)], fill=LGRAY, width=1)
        noc_row(NOC_Y0, NOC_H, "  [sel FIXED=0]", yi)
        chain_box(CHAIN_Y0, CHAIN_Y1,
                  "Dispatch/Router EDC sub-chain  (postdfx_aon_clk)",
                  "NOC N/E/S/W/NIU nodes + security fence  — both Seg A and Seg B traverse, always")
        ovl_row(OVL_Y0, OVL_H, "  [sel FIXED=0]", yi)
        rail_conn(y0, y1, NOC_Y0, NOC_H, OVL_Y0, OVL_H)

    # ── Tensix tile (Y=0/1/2) ─────────────────────────────────────────────────
    def draw_tensix(yi, ut=False):
        y0=T_TOPS[yi]; h=T_HGTS[yi]; y1=y0+h
        NOC_H=82; OVL_H=82; UT_H=72 if ut else 0; PAD=8
        NOC_Y0=y0+28; NOC_Y1=NOC_Y0+NOC_H
        CHAIN_Y0=NOC_Y1+PAD
        CHAIN_H = h - 28 - NOC_H - OVL_H - UT_H - PAD*(4 if ut else 3) - 4
        CHAIN_Y1=CHAIN_Y0+CHAIN_H
        OVL_Y0=CHAIN_Y1+PAD; OVL_Y1=OVL_Y0+OVL_H
        UT_Y0 = OVL_Y1+PAD if ut else 0

        bx(d, TX0,y0, TX1,y1, fill=(245,248,255), outline=(60,80,200), lw=2)
        lbl = f"  Y={yi} · Tensix  —  sel=0 ALIVE | sel=1 HARVESTED" + ("  +  U-TURN" if ut else "")
        txt(d, lbl, TX0+8, y0+6, f13, (60,80,200))
        d.line([(TX0+4,y0+24),(TX1-4,y0+24)], fill=LGRAY, width=1)

        noc_row(NOC_Y0, NOC_H, "", yi)
        chain_box(CHAIN_Y0, CHAIN_Y1,
                  "T0  →  T1  →  T6_MISC + L1W2  →  T3  →  T2   (~80 EDC nodes)",
                  "aiclk domain — both Seg A ↓ and Seg B ↑ traverse in this order")
        ovl_row(OVL_Y0, OVL_H, "", yi)

        # bypass-A wire (left edge, ↓ with Seg A)
        dash_v(d, BYP_A_X, NOC_Y1, OVL_Y0, RED, dash=9, gap=5, w=2)
        ctxt(d,"bypass-A",BYP_A_X,(NOC_Y1+OVL_Y0)//2-5,f9,RED)
        # bypass-B wire (right edge, ↑ with Seg B)
        dash_v(d, BYP_B_X, NOC_Y1, OVL_Y0, (0,130,80), dash=9, gap=5, w=2)
        ctxt(d,"bypass-B",BYP_B_X-52,(NOC_Y1+OVL_Y0)//2-5,f9,(0,130,80))

        # U-TURN section (Y=0 only)
        if ut:
            bx(d, NB_X0, UT_Y0, NB_X1, y1-4, fill=(228,255,228), outline=GREEN, lw=2)
            ctxt(d,"U-TURN  (tt_edc1_intf_connector, y=0 block)",(NB_X0+NB_X1)//2,UT_Y0+5,f12,GREEN)
            ctxt(d,"edc_egress_intf[x*5+0]  →  loopback_edc_ingress_intf[x*5+0]  (pure wire)",
                 (NB_X0+NB_X1)//2,UT_Y0+22,f11,BLACK)
            ctxt(d,"Segment A ends  ·  Segment B begins",(NB_X0+NB_X1)//2,UT_Y0+40,f10,DGRAY)
            UT_AY = UT_Y0+35
            d.line([(SA_RAIL,UT_AY),(SB_RAIL,UT_AY)], fill=GREEN, width=3)
            d.polygon([(SB_RAIL+11,UT_AY-6),(SB_RAIL+11,UT_AY+6),(SB_RAIL,UT_AY)], fill=GREEN)
            ctxt(d,"U-TURN",(SA_RAIL+SB_RAIL)//2,UT_AY+8,f10,GREEN)
            rail_conn(y0, y1, NOC_Y0, NOC_H, OVL_Y0, OVL_H, ut=True, ut_arrow_y=UT_AY)
        else:
            rail_conn(y0, y1, NOC_Y0, NOC_H, OVL_Y0, OVL_H)

    # ── render all tiles ───────────────────────────────────────────────────────
    draw_biu()
    draw_connector(4,3)
    draw_dispatch()
    draw_connector(3,2)
    draw_tensix(2)
    draw_connector(2,1)
    draw_tensix(1)
    draw_connector(1,0)
    draw_tensix(0, ut=True)

    # ── rail labels at top ────────────────────────────────────────────────────
    RL_Y = TITLE_H+46
    ctxt(d,"Seg A ↓",SA_RAIL,RL_Y,f10,BLUE)
    ctxt(d,"Seg B ↑",SB_RAIL,RL_Y,f10,TEAL)

    # ── footer ────────────────────────────────────────────────────────────────
    y_last = T_TOPS[0]+T_HGTS[0]
    FY = y_last+20
    bx(d, 2,FY, W-2,H-4, fill=NOTE_BG, outline=ORANGE, lw=1)
    txt(d,"  Seg A sel=0 (ALIVE):     edc_ingress → NOC DEMUX-A out0 → NOC nodes + sub-chain T0→T1→T3→T2 → OVL MUX-A in0 → edc_egress ↓",
        8, FY+8,  f11, GREEN)
    txt(d,"  Seg A sel=1 (HARVESTED): edc_ingress → NOC DEMUX-A out1 → bypass-A wire → OVL MUX-A in1 → edc_egress ↓   [chain skipped]",
        8, FY+26, f11, RED)
    txt(d,"  Seg B sel=0 (ALIVE):     loopback_ingress → OVL DEMUX-B out0 → sub-chain T0→T1→T3→T2 → NOC MUX-B in0 → loopback_egress ↑",
        8, FY+44, f11, TEAL)
    txt(d,"  Seg B sel=1 (HARVESTED): loopback_ingress → OVL DEMUX-B out1 → bypass-B wire → NOC MUX-B in1 → loopback_egress ↑  [chain skipped]",
        8, FY+62, f11, (0,130,80))
    txt(d,"  Dispatch (Y=3): DEMUX-A/MUX-B/MUX-A/DEMUX-B all fixed sel=0; chain=postdfx_aon_clk (NOC/NIU/fence nodes); never harvested in N1B0",
        8, FY+80, f10, DGRAY)

    bx(d,0,0,W,H,fill=None,outline=BLUE,lw=2)
    save(img, "01_edc_ring_full_architecture.png")


draw_fig4()
draw_fig1()

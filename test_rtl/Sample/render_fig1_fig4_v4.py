#!/usr/bin/env python3.11
"""Fig 1 V0.8 — adds compact EDC node table inside each tile chain box.
   Fig 4 — unchanged (still outputs v0.7 file).
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
LB_BG  = (232,244,255)
TEAL   = (0,120,110)
LT_BG  = (230,250,245)
ORANGE = (180,90,0)
OR_BG  = (255,248,220)
GREEN  = (10,130,40)
RED    = (180,30,30)
CHAIN_BG = (235,243,255)
CHAIN_C  = (0,100,160)
NOTE_BG  = (255,250,230)
APB_BG   = (245,235,255)
APB_C    = (120,0,160)

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


# ─── EDC node data ─────────────────────────────────────────────────────────────
# (name, clock_domain, fault_description, severity)
# severity: "fatal" | "crit" | "noncrit" | "mixed"

DISPATCH_NODES = [
    ("NOC N/E/S/W (×4)",  "noc_clk", "NoC flit parity, credit counter errors",       "noncrit"),
    ("NOC NIU",            "noc_clk", "Link protocol / header parity",                "noncrit"),
    ("NOC sec_fence",      "noc_clk", "Security fence violation",                     "fatal"),
    ("Dispatch L1 SRAM",   "aiclk",   "ECC: SEC correctable (non-crit) / DED (fatal)","mixed"),
    ("Overlay WDT",        "dm_clk",  "Watchdog timeout",                             "fatal"),
    ("Overlay APB bridge", "dm_clk",  "Register bus parity",                          "noncrit"),
]

TENSIX_NODES = [
    ("NOC N/E/S/W (×4)",  "noc_clk", "NoC flit parity, credit counter errors",       "noncrit"),
    ("NOC NIU",            "noc_clk", "Link protocol / header parity",                "noncrit"),
    ("NOC sec_fence",      "noc_clk", "Security fence violation",                     "fatal"),
    ("T6_MISC (T0 only)", "aiclk",   "Tile config register parity",                  "crit"),
    ("IE_PARITY ×4 cores","aiclk",   "Instruction engine pipeline parity",           "crit"),
    ("SRCB ×4 cores",      "aiclk",   "Source-B register file parity",               "crit"),
    ("SFPU ×4 cores",      "aiclk",   "SFPU pipeline parity",                        "crit"),
    ("FPU_GTILE ×4",       "aiclk",   "FP MAC datapath parity, overflow detection",  "crit"),
    ("L1_CLIENT ×4",       "aiclk",   "NoC→L1 client data parity",                   "noncrit"),
    ("L1W2 SRAM ×256",     "aiclk",   "ECC: SEC correctable (non-crit) / DED (fatal)","mixed"),
    ("OVL WDT",            "dm_clk",  "Watchdog timeout",                             "fatal"),
    ("OVL APB bridge",     "dm_clk",  "Register bus parity",                          "noncrit"),
]

SEV_COLORS = {"fatal": RED, "crit": ORANGE, "noncrit": DGRAY, "mixed": TEAL}
SEV_LABELS = {"fatal": "FATAL", "crit": "CRIT ", "noncrit": "n-crt", "mixed": " ECC "}


# ═════════════════════════════════════════════════════════════════════════════
# FIG 4 — unchanged, still outputs v0.7 file
# ═════════════════════════════════════════════════════════════════════════════
def draw_fig4():
    W, H = 1160, 860
    img = Image.new("RGB", (W,H), BG)
    d   = ImageDraw.Draw(img)

    TH = 58
    bx(d,0,0,W,TH,fill=(228,238,255),lw=0)
    ctxt(d,"Fig 4 — Harvest Bypass Signal Flow per Tile  (Tensix Y=0/1/2)  [V0.7]", W//2, 6, f18, BLUE)
    ctxt(d,"sel=0 → ALIVE  ·  sel=1 → HARVESTED  ·  same edc_mux_demux_sel drives DEMUX-A, MUX-A, DEMUX-B, MUX-B", W//2, 32, f12, DGRAY)

    TL, TR = 30, 1130
    TT, TB = TH+60, 730
    SPLIT  = 222
    SB_CX  = (TL + SPLIT) // 2
    SA_X0  = SPLIT + 14

    bx(d, TL,TT, TR,TB, fill=(248,250,255), outline=(60,80,200), lw=3)
    txt(d,"  Tile  (tt_trin_noc_niu_router_wrap  +  tt_tensix_with_l1  +  tt_neo_overlay_wrapper)",
        TL+8, TT+5, f11, (60,80,200))
    d.line([(TL+4,TT+20),(TR-4,TT+20)], fill=LGRAY, width=1)
    d.line([(SPLIT,TT+22),(SPLIT,TB-4)], fill=LGRAY, width=1)

    bx(d, TL+4,TT+26, SPLIT-4,TT+44, fill=LT_BG, outline=TEAL, lw=1)
    ctxt(d,"Segment B  (↑ loopback)", SB_CX, TT+28, f10, TEAL)
    LB_Y0, LB_Y1 = TT+60, TT+200
    bx(d, TL+4,LB_Y0, SPLIT-4,LB_Y1, fill=LT_BG, outline=TEAL, lw=2)
    ctxt(d,"overlay_loopback", SB_CX, LB_Y0+10, f11, TEAL)
    ctxt(d,"_repeater",        SB_CX, LB_Y0+26, f11, TEAL)
    ctxt(d,"(aon_clk)",        SB_CX, LB_Y0+46, f11, TEAL)
    d.line([(TL+8,LB_Y0+66),(SPLIT-8,LB_Y0+66)], fill=LGRAY, width=1)
    ctxt(d,"No DEMUX",  SB_CX, LB_Y0+72,  f10, TEAL)
    ctxt(d,"No MUX",    SB_CX, LB_Y0+88,  f10, TEAL)
    ctxt(d,"No bypass", SB_CX, LB_Y0+104, f10, TEAL)
    arr_up(d, SB_CX, TB-4,  LB_Y1, TEAL, w=3)
    arr_up(d, SB_CX, LB_Y0, TT+22, TEAL, w=3)
    ctxt(d,"loopback_edc_ingress_intf[x*5+y]", SB_CX, TB+8,  f9, TEAL)
    ctxt(d,"← from tile below / U-turn",       SB_CX, TB+22, f9, TEAL)
    ctxt(d,"loopback_edc_egress_intf[x*5+y]",  SB_CX, TT-32, f9, TEAL)
    ctxt(d,"→ to tile above / BIU(Y=4)",        SB_CX, TT-18, f9, TEAL)

    bx(d, SPLIT+4,TT+26, TR-4,TT+44, fill=LB_BG, outline=BLUE, lw=1)
    ctxt(d,"Segment A  (↓ direct)", (SPLIT+TR)//2, TT+28, f10, BLUE)
    BYPASS_X = TR - 46
    DY0, DY1 = TT+54, TT+148
    bx(d, SA_X0,DY0, TR-4,DY1, fill=OR_BG, outline=ORANGE, lw=2)
    ctxt(d,"DEMUX-A  (edc_demuxing_when_harvested  ·  tt_trin_noc_niu_router_wrap)",
         (SA_X0+TR-4)//2, DY0+5, f12, ORANGE)
    d.line([(SA_X0+4,DY0+22),(TR-8,DY0+22)], fill=LGRAY, width=1)
    txt(d, "  in   ←  edc_ingress_intf  (from ring above)",            SA_X0+8, DY0+28, f11, BLACK)
    txt(d, "  sel=0  out0 ──►  NOC nodes + aiclk sub-chain     [ALIVE]",      SA_X0+8, DY0+48, f12, GREEN)
    txt(d, "  sel=1  out1 ──►  bypass-A wire  →  MUX-A in1  [HARVESTED]",    SA_X0+8, DY0+70, f12, RED)

    RING_X = SA_X0 + 140
    arr_down(d, RING_X, TT-40, DY0, BLUE, w=3)
    txt(d,"edc_ingress_intf[x*5+y]  (ring from tile above)", RING_X+8, TT-38, f10, BLUE)

    CHAIN_CX = SA_X0 + 120
    CHAIN_Y0 = DY1 + 30
    CHAIN_Y1 = CHAIN_Y0 + 140
    arr_down(d, CHAIN_CX, DY1, CHAIN_Y0, GREEN, w=2)
    ctxt(d,"out0 sel=0", CHAIN_CX, DY1+4, f10, GREEN)

    BYP_STUB_Y = DY0+77
    d.line([(SA_X0+490, BYP_STUB_Y),(BYPASS_X, BYP_STUB_Y)], fill=RED, width=2)
    dash_v(d, BYPASS_X, BYP_STUB_Y, CHAIN_Y1+34, RED, dash=9, gap=5, w=2)
    ctxt(d,"bypass-A", BYPASS_X+4, (DY1+CHAIN_Y0+CHAIN_Y1)//3,    f10, RED)
    ctxt(d,"wire",     BYPASS_X+4, (DY1+CHAIN_Y0+CHAIN_Y1)//3+13, f10, RED)

    CH_X1 = BYPASS_X - 10
    bx(d, SA_X0,CHAIN_Y0, CH_X1,CHAIN_Y1, fill=CHAIN_BG, outline=CHAIN_C, lw=2)
    ctxt(d,"Tile EDC Sub-Chain  (aiclk domain)", (SA_X0+CH_X1)//2, CHAIN_Y0+6, f13, CHAIN_C)
    d.line([(SA_X0+4,CHAIN_Y0+24),(CH_X1-4,CHAIN_Y0+24)], fill=LGRAY, width=1)
    ctxt(d,"T0  →  T1  →  (T6_MISC + L1 partition)  →  T3  →  T2",
         (SA_X0+CH_X1)//2, CHAIN_Y0+30, f11, BLACK)
    ctxt(d,"~80 EDC nodes per tile", (SA_X0+CH_X1)//2, CHAIN_Y0+48, f10, DGRAY)
    d.line([(SA_X0+4,CHAIN_Y0+64),(CH_X1-4,CHAIN_Y0+64)], fill=LGRAY, width=1)
    ctxt(d,"sel=0  ALIVE:    aiclk running — nodes report errors on both Seg A and Seg B",
         (SA_X0+CH_X1)//2, CHAIN_Y0+70, f11, GREEN)
    ctxt(d,"sel=1  HARVESTED: aiclk STOPPED — chain bypassed via bypass-A and bypass-B wires",
         (SA_X0+CH_X1)//2, CHAIN_Y0+90, f11, RED)
    ctxt(d,"(NOC router nodes always active on aon_clk; i_harvest_en=1 gates errors)",
         (SA_X0+CH_X1)//2, CHAIN_Y0+112, f10, DGRAY)

    MUX_Y0 = CHAIN_Y1 + 30
    MUX_Y1 = MUX_Y0 + 96
    arr_down(d, CHAIN_CX, CHAIN_Y1, MUX_Y0, GREEN, w=2)
    ctxt(d,"sel=0", CHAIN_CX, CHAIN_Y1+4, f10, GREEN)

    bx(d, SA_X0,MUX_Y0, TR-4,MUX_Y1, fill=OR_BG, outline=ORANGE, lw=2)
    ctxt(d,"MUX-A  (edc_muxing_when_harvested  ·  tt_neo_overlay_wrapper)",
         (SA_X0+TR-4)//2, MUX_Y0+5, f12, ORANGE)
    d.line([(SA_X0+4,MUX_Y0+22),(TR-8,MUX_Y0+22)], fill=LGRAY, width=1)
    txt(d, "  sel=0  in0 ◄──  ovl_egress_intf  (sub-chain output)          [ALIVE]",      SA_X0+8, MUX_Y0+28, f12, GREEN)
    txt(d, "  sel=1  in1 ◄──  bypass-A wire  (from DEMUX-A out1)          [HARVESTED]",   SA_X0+8, MUX_Y0+50, f12, RED)
    d.line([(SA_X0+4,MUX_Y0+70),(TR-8,MUX_Y0+70)], fill=LGRAY, width=1)
    txt(d, "  out  ──►  edc_egress_intf[x*5+y]  →  ring to tile below",                  SA_X0+8, MUX_Y0+76, f12, BLUE)

    IN1_Y = MUX_Y0 + 57
    d.line([(SA_X0+490, IN1_Y),(BYPASS_X, IN1_Y)], fill=RED, width=2)
    d.polygon([(SA_X0+502,IN1_Y-5),(SA_X0+502,IN1_Y+5),(SA_X0+490,IN1_Y)], fill=RED)
    d.polygon([(BYPASS_X-5,IN1_Y-10),(BYPASS_X+5,IN1_Y-10),(BYPASS_X,IN1_Y)], fill=RED)

    arr_down(d, RING_X, MUX_Y1, TB+10, BLUE, w=3)
    txt(d,"edc_egress_intf[x*5+y]  →  ring to tile below", RING_X+8, TB+12, f10, BLUE)

    SUM_Y = TB + 36
    bx(d, 2,SUM_Y, W-2,H-4, fill=NOTE_BG, outline=ORANGE, lw=1)
    ctxt(d,"Signal Flow Summary", W//2, SUM_Y+5, f13, ORANGE)
    txt(d,"  Seg A sel=0 ALIVE:     edc_ingress → DEMUX-A out0 → NOC nodes + aiclk chain T0→T1→T3→T2 → MUX-A in0 → edc_egress ↓",
        8, SUM_Y+24, f11, GREEN)
    txt(d,"  Seg A sel=1 HARVESTED: edc_ingress → DEMUX-A out1 → bypass-A wire (combinational, no clock) → MUX-A in1 → edc_egress ↓",
        8, SUM_Y+42, f11, RED)
    txt(d,"  Seg B:  symmetric structure (DEMUX-B at OVL, MUX-B at NOC); same sel controls bypass-B wire",
        8, SUM_Y+60, f11, TEAL)

    bx(d,0,0,W,H,fill=None,outline=BLUE,lw=2)
    save(img, "04_harvest_bypass_signal_flow_v0.7.png")


# ═════════════════════════════════════════════════════════════════════════════
# FIG 1 — V0.8: adds EDC node table inside each tile chain box
# ═════════════════════════════════════════════════════════════════════════════
def draw_fig1():
    W, H = 1520, 2970
    img = Image.new("RGB", (W,H), BG)
    d   = ImageDraw.Draw(img)

    SA_RAIL = 40
    SB_RAIL = 1470
    TX0, TX1 = 100, 1410
    TILE_MID = (TX0+TX1)//2
    NB_X0, NB_X1 = TX0+40, TX1-40
    BYP_A_X = TX0+20
    BYP_B_X = TX1-20

    TITLE_H = 120
    GAP = 30
    # V0.8: expanded tile heights to fit node tables
    T_HGTS = {4:390, 3:440, 2:530, 1:530, 0:610}
    T_TOPS = {}
    T_TOPS[4] = TITLE_H + 50
    for yi in (3,2,1,0):
        T_TOPS[yi] = T_TOPS[yi+1] + T_HGTS[yi+1] + GAP

    # ── title ─────────────────────────────────────────────────────────────────
    bx(d,0,0,W,TITLE_H,fill=(228,238,255),lw=0)
    ctxt(d,"Fig 1 — One Column (X=0): Complete EDC Ring — 5 Tiles + U-Turn  [V0.8]",W//2,6,f18,BLUE)
    ctxt(d,"Seg A ↓ (blue, LEFT rail)  and  Seg B ↑ (teal, RIGHT rail)  traverse the SAME sub-chain in the SAME order.",W//2,34,f12,DGRAY)
    ctxt(d,"NOC boundary (top of tile): DEMUX-A | MUX-B       Overlay boundary (bottom of tile): MUX-A | DEMUX-B",W//2,52,f12,DGRAY)
    ctxt(d,"edc_mux_demux_sel controls all four mux/demux instances simultaneously",W//2,70,f11,(100,0,100))
    ctxt(d,"Seg A ↓  edc_ingress/egress_intf",W//2-200,90,f10,BLUE)
    ctxt(d,"Seg B ↑  loopback_edc_ingress/egress_intf",W//2+100,90,f10,TEAL)

    APB_Y = TITLE_H + 15
    ctxt(d,"APB4 Firmware", W//2, APB_Y, f12, APB_C)
    arr_down(d, W//2, APB_Y+15, TITLE_H+46, APB_C, w=2)

    # ── severity legend ───────────────────────────────────────────────────────
    LEG_X = W-280
    LEG_Y = TITLE_H + 15
    txt(d,"Severity:", LEG_X, LEG_Y, f9, BLACK)
    for i,(label,color) in enumerate([("FATAL",RED),("CRIT",ORANGE),("n-crt",DGRAY),("ECC±",TEAL)]):
        bx(d, LEG_X+60+i*55, LEG_Y, LEG_X+110+i*55, LEG_Y+14, fill=BG, outline=color, lw=1)
        ctxt(d, label, LEG_X+85+i*55, LEG_Y+2, f9, color)

    def draw_connector(fy, ty):
        y0 = T_TOPS[fy]+T_HGTS[fy]; y1 = T_TOPS[ty]; mid=(y0+y1)//2
        arr_down(d, SA_RAIL, y0+2, y1-2, BLUE, w=3)
        arr_up(d, SB_RAIL, y1-2, y0+2, TEAL, w=3)
        ctxt(d,f"edc_direct_conn / edc_loopback_conn  (Y={ty}↔Y={fy})",W//2,mid-7,f10,DGRAY)

    def noc_row(y0b, h, sel_note, yi):
        bx(d, NB_X0, y0b, NB_X1, y0b+h, fill=OR_BG, outline=ORANGE, lw=2)
        ctxt(d, "NOC Router Boundary"+sel_note,
             (NB_X0+NB_X1)//2, y0b+4, f11, ORANGE)
        d.line([(NB_X0+4,y0b+20),(NB_X1-4,y0b+20)], fill=LGRAY, width=1)
        d.line([(TILE_MID, y0b+22),(TILE_MID, y0b+h-2)], fill=LGRAY, width=1)
        DA = (NB_X0+TILE_MID)//2
        MB = (TILE_MID+NB_X1)//2
        ctxt(d,"DEMUX-A",DA,y0b+24,f10,ORANGE)
        ctxt(d,f"in: edc_ingress_intf[x*5+{yi}]",DA,y0b+38,f10,BLUE)
        ctxt(d,"sel=0 out0→chain [ALIVE]",DA,y0b+52,f10,GREEN)
        ctxt(d,"sel=1 out1→byp-A [HARV]",DA,y0b+66,f10,RED)
        ctxt(d,"MUX-B",MB,y0b+24,f10,ORANGE)
        ctxt(d,"sel=0 in0←chain→loopback_egress",MB,y0b+38,f10,TEAL)
        ctxt(d,"sel=1 in1←byp-B→loopback_egress",MB,y0b+52,f10,(0,130,80))
        ctxt(d,f"out: loopback_edc_egress[x*5+{yi}]↑",MB,y0b+66,f10,TEAL)

    def ovl_row(y0b, h, sel_note, yi):
        bx(d, NB_X0, y0b, NB_X1, y0b+h, fill=(232,250,232), outline=GREEN, lw=2)
        ctxt(d, "Overlay Boundary"+sel_note,
             (NB_X0+NB_X1)//2, y0b+4, f11, GREEN)
        d.line([(NB_X0+4,y0b+20),(NB_X1-4,y0b+20)], fill=LGRAY, width=1)
        d.line([(TILE_MID, y0b+22),(TILE_MID, y0b+h-2)], fill=LGRAY, width=1)
        MA = (NB_X0+TILE_MID)//2
        DB = (TILE_MID+NB_X1)//2
        ctxt(d,"MUX-A",MA,y0b+24,f10,ORANGE)
        ctxt(d,"sel=0 in0←chain→edc_egress",MA,y0b+38,f10,GREEN)
        ctxt(d,"sel=1 in1←byp-A→edc_egress",MA,y0b+52,f10,RED)
        ctxt(d,f"out: edc_egress_intf[x*5+{yi}]↓",MA,y0b+66,f10,BLUE)
        ctxt(d,"DEMUX-B",DB,y0b+24,f10,ORANGE)
        ctxt(d,f"in: loopback_edc_ingress[x*5+{yi}]",DB,y0b+38,f10,TEAL)
        ctxt(d,"sel=0 out0→chain [ALIVE]",DB,y0b+52,f10,TEAL)
        ctxt(d,"sel=1 out1→byp-B [HARV]",DB,y0b+66,f10,(0,130,80))

    # ── shared sub-chain box (V0.8: adds compact node table) ──────────────────
    def chain_box(y0b, y1b, chain_label, chain_note, nodes=None):
        bx(d, NB_X0, y0b, NB_X1, y1b, fill=CHAIN_BG, outline=CHAIN_C, lw=2)
        ctxt(d, "Shared EDC Sub-Chain — same traversal order T0→T1→T3→T2 for Seg A and Seg B",
             (NB_X0+NB_X1)//2, y0b+6, f12, CHAIN_C)
        d.line([(NB_X0+4, y0b+22),(NB_X1-4, y0b+22)], fill=LGRAY, width=1)
        ctxt(d, chain_label,  (NB_X0+NB_X1)//2, y0b+28, f12, BLACK)
        ctxt(d, chain_note,   (NB_X0+NB_X1)//2, y0b+46, f11, DGRAY)
        ctxt(d, "sel=0: aiclk running — nodes report on both Seg A and Seg B passes",
             (NB_X0+NB_X1)//2, y0b+64, f10, GREEN)
        ctxt(d, "sel=1: aiclk stopped — both segs bypass via bypass-A/bypass-B",
             (NB_X0+NB_X1)//2, y0b+80, f10, RED)

        # Seg A / Seg B direction arrows on left/right margins of chain box
        ACX = NB_X0+14
        arr_down(d, ACX, y0b+4, y0b+94, BLUE, w=2)
        ctxt(d,"A↓", ACX, y0b+40, f9, BLUE)
        BCX = NB_X1-14
        arr_up(d, BCX, y0b+94, y0b+4, TEAL, w=2)
        ctxt(d,"B↑", BCX, y0b+40, f9, TEAL)

        # ── compact node table ─────────────────────────────────────────────
        if nodes:
            TBL_Y = y0b + 98
            # column x-positions (within NB_X0..NB_X1 = 140..1370, width=1230)
            C0 = NB_X0 + 26   # node name  (left-align)
            C1 = NB_X0 + 400  # clock      (center)
            C2 = NB_X0 + 470  # fault text (left-align)
            C3 = NB_X1 - 44   # severity   (center)
            # table header
            bx(d, NB_X0+4, TBL_Y, NB_X1-4, TBL_Y+16,
               fill=(210,225,245), outline=None, lw=0)
            txt(d,"Node / Instance",            C0,   TBL_Y+2, f9, DGRAY)
            ctxt(d,"Clk",                       C1,   TBL_Y+2, f9, DGRAY)
            txt(d,"Fault / Error detected",      C2,   TBL_Y+2, f9, DGRAY)
            ctxt(d,"Sev.",                       C3,   TBL_Y+2, f9, DGRAY)
            d.line([(NB_X0+4, TBL_Y+16),(NB_X1-4, TBL_Y+16)], fill=LGRAY, width=1)
            ry = TBL_Y + 18
            for i,(name, clk, fault, sev) in enumerate(nodes):
                row_fill = (242,246,255) if i%2==0 else (232,240,252)
                bx(d, NB_X0+4, ry, NB_X1-4, ry+13,
                   fill=row_fill, outline=None, lw=0)
                sc = SEV_COLORS[sev]
                txt(d, name,            C0, ry+1, f9, BLACK)
                ctxt(d, clk,            C1, ry+1, f9, DGRAY)
                txt(d, fault,           C2, ry+1, f9, sc)
                bx(d, C3-22, ry+1, C3+22, ry+12,
                   fill=BG, outline=sc, lw=1)
                ctxt(d, SEV_LABELS[sev], C3, ry+2, f9, sc)
                ry += 14

    def rail_conn(y0, y1, NOC_Y0, NOC_H, OVL_Y0, OVL_H, ut=False, ut_arrow_y=None):
        SA_IN_Y  = NOC_Y0 + 38
        SA_OUT_Y = OVL_Y0 + 66
        SB_OUT_Y = NOC_Y0 + 38
        SB_IN_Y  = OVL_Y0 + 38

        arr_down(d, SA_RAIL, y0+2, SA_IN_Y, BLUE, w=3)
        arr_right(d, SA_RAIL, NB_X0, SA_IN_Y, BLUE, w=2)
        arr_left(d, SA_RAIL, NB_X0, SA_OUT_Y, BLUE, w=2)
        if not ut:
            arr_down(d, SA_RAIL, SA_OUT_Y, y1-2, BLUE, w=3)
        else:
            arr_down(d, SA_RAIL, SA_OUT_Y, ut_arrow_y, BLUE, w=3)

        arr_right(d, NB_X1, SB_RAIL, SB_OUT_Y, TEAL, w=2)
        arr_up(d, SB_RAIL, SB_OUT_Y, y0+4, TEAL, w=3)
        if not ut:
            arr_up(d, SB_RAIL, y1-4, SB_IN_Y, TEAL, w=3)
        else:
            arr_up(d, SB_RAIL, ut_arrow_y, SB_IN_Y, TEAL, w=3)
        arr_left(d, NB_X1, SB_RAIL, SB_IN_Y, TEAL, w=2)

    # ── BIU tile (Y=4) ─────────────────────────────────────────────────────────
    def draw_biu():
        yi=4; y0=T_TOPS[yi]; h=T_HGTS[yi]; y1=y0+h
        bx(d, TX0,y0, TX1,y1, fill=(240,248,245), outline=(60,80,200), lw=2)
        txt(d,"  Y=4 · BIU / NOC2AXI  —  never harvested",
            TX0+8, y0+6, f13, (60,80,200))
        d.line([(TX0+4,y0+24),(TX1-4,y0+24)], fill=LGRAY, width=1)

        APB_Y0 = y0+30; APB_Y1 = APB_Y0+110
        bx(d, NB_X0, APB_Y0, NB_X1, APB_Y1, fill=APB_BG, outline=APB_C, lw=2)
        ctxt(d,"APB4 Firmware Interface  (tt_edc1_biu_soc_apb4)",
             (NB_X0+NB_X1)//2, APB_Y0+5, f13, APB_C)
        d.line([(NB_X0+4,APB_Y0+22),(NB_X1-4,APB_Y0+22)], fill=LGRAY, width=1)
        ctxt(d,"CSR registers: CTRL / STAT / IRQ_EN / REQ_DATA / RSP_DATA",
             (NB_X0+NB_X1)//2, APB_Y0+28, f11, BLACK)
        ctxt(d,"APB4 WRITE → REQ_DATA → u_edc_req_src → serialize → Seg A ring (send command)",
             (NB_X0+NB_X1)//2, APB_Y0+46, f11, BLUE)
        ctxt(d,"APB4 READ  ← RSP_DATA ← u_edc_rsp_snk ← deserialize ← Seg B ring (receive response)",
             (NB_X0+NB_X1)//2, APB_Y0+64, f11, TEAL)
        ctxt(d,"fatal_irq / crit_irq / noncrit_irq  ──►  SoC interrupt controller",
             (NB_X0+NB_X1)//2, APB_Y0+84, f11, RED)

        arr_down(d, (NB_X0+NB_X1)//2, y0+26, APB_Y0, APB_C, w=2)

        SRC_Y0 = APB_Y1+10; SRC_Y1 = y1-8
        d.line([(TX0+4,SRC_Y0),(TX1-4,SRC_Y0)], fill=LGRAY, width=1)
        d.line([(TILE_MID, SRC_Y0),(TILE_MID, SRC_Y1)], fill=LGRAY, width=1)
        LA = (TX0+TILE_MID)//2
        bx(d, TX0+8, SRC_Y0+4, TILE_MID-4, SRC_Y1, fill=(225,245,225), outline=GREEN, lw=1)
        ctxt(d,"Seg A  SOURCE",LA,SRC_Y0+10,f13,GREEN)
        ctxt(d,"u_edc_req_src",LA,SRC_Y0+30,f11,DGRAY)
        ctxt(d,"(tt_edc1_state_machine)",LA,SRC_Y0+46,f11,DGRAY)
        ctxt(d,"→ edc_egress_intf[x*5+4] ↓",LA,SRC_Y0+66,f12,BLUE)

        RB = (TILE_MID+TX1)//2
        bx(d, TILE_MID+4, SRC_Y0+4, TX1-8, SRC_Y1, fill=(225,248,245), outline=TEAL, lw=1)
        ctxt(d,"Seg B  TERMINUS",RB,SRC_Y0+10,f13,TEAL)
        ctxt(d,"u_edc_rsp_snk",RB,SRC_Y0+30,f11,DGRAY)
        ctxt(d,"(tt_edc1_state_machine)",RB,SRC_Y0+46,f11,DGRAY)
        ctxt(d,"← loopback_edc_ingress[x*5+4]",RB,SRC_Y0+66,f12,TEAL)

        SA_OUT_Y = SRC_Y0+68
        arr_left(d, SA_RAIL, TX0+8, SA_OUT_Y, BLUE, w=2)
        arr_down(d, SA_RAIL, SA_OUT_Y, y1-2, BLUE, w=3)

        SB_IN_Y = SRC_Y0+68
        arr_up(d, SB_RAIL, y1-4, SB_IN_Y, TEAL, w=3)
        arr_left(d, TX1-8, SB_RAIL, SB_IN_Y, TEAL, w=2)

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
        txt(d,"  Y=3 · Dispatch/Router  —  sel FIXED=0 (never harvested in N1B0)",
            TX0+8, y0+6, f13, (60,80,200))
        d.line([(TX0+4,y0+24),(TX1-4,y0+24)], fill=LGRAY, width=1)
        noc_row(NOC_Y0, NOC_H, "  [sel FIXED=0]", yi)
        chain_box(CHAIN_Y0, CHAIN_Y1,
                  "Dispatch/Router EDC sub-chain  (postdfx_aon_clk)",
                  "NOC N/E/S/W/NIU + security fence — Seg A and Seg B traverse, sel fixed to 0",
                  nodes=DISPATCH_NODES)
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
                  "aiclk domain — Seg A enters from NOC (top), Seg B enters from OVL (bottom), same node order",
                  nodes=TENSIX_NODES)
        ovl_row(OVL_Y0, OVL_H, "", yi)

        BYPA_Y_START = NOC_Y1
        BYPA_Y_END   = OVL_Y0
        dash_v(d, BYP_A_X, BYPA_Y_START, BYPA_Y_END, RED, dash=9, gap=5, w=2)
        d.polygon([(BYP_A_X-5,BYPA_Y_END-10),(BYP_A_X+5,BYPA_Y_END-10),(BYP_A_X,BYPA_Y_END)], fill=RED)
        ctxt(d,"byp-A↓",BYP_A_X,(BYPA_Y_START+BYPA_Y_END)//2-5,f9,RED)

        BYPB_Y_START = OVL_Y0
        BYPB_Y_END   = NOC_Y1
        dash_v(d, BYP_B_X, BYPB_Y_END, BYPB_Y_START, (0,130,80), dash=9, gap=5, w=2)
        d.polygon([(BYP_B_X-5,BYPB_Y_END+10),(BYP_B_X+5,BYPB_Y_END+10),(BYP_B_X,BYPB_Y_END)], fill=(0,130,80))
        txt(d,"byp-B↑",BYP_B_X+4,(BYPB_Y_END+BYPB_Y_START)//2-5,f9,(0,130,80))

        if ut:
            bx(d, NB_X0, UT_Y0, NB_X1, y1-4, fill=(228,255,228), outline=GREEN, lw=2)
            ctxt(d,"U-TURN",(NB_X0+NB_X1)//2,UT_Y0+5,f12,GREEN)
            ctxt(d,"edc_egress_intf[x*5+0]  →  loopback_edc_ingress_intf[x*5+0]  (pure wire, no clock)",
                 (NB_X0+NB_X1)//2,UT_Y0+22,f11,BLACK)
            ctxt(d,"Segment A ends  ·  Segment B begins",(NB_X0+NB_X1)//2,UT_Y0+40,f10,DGRAY)
            UT_AY = UT_Y0+35
            d.line([(SA_RAIL,UT_AY),(SB_RAIL,UT_AY)], fill=GREEN, width=3)
            d.polygon([(SB_RAIL-11,UT_AY-6),(SB_RAIL-11,UT_AY+6),(SB_RAIL,UT_AY)], fill=GREEN)
            ctxt(d,"U-TURN",(SA_RAIL+SB_RAIL)//2,UT_AY+8,f10,GREEN)
            rail_conn(y0, y1, NOC_Y0, NOC_H, OVL_Y0, OVL_H, ut=True, ut_arrow_y=UT_AY)
        else:
            rail_conn(y0, y1, NOC_Y0, NOC_H, OVL_Y0, OVL_H)

    # ── render tiles ───────────────────────────────────────────────────────────
    draw_biu()
    draw_connector(4,3)
    draw_dispatch()
    draw_connector(3,2)
    draw_tensix(2)
    draw_connector(2,1)
    draw_tensix(1)
    draw_connector(1,0)
    draw_tensix(0, ut=True)

    # ── rail labels ───────────────────────────────────────────────────────────
    RL_Y = TITLE_H+46
    ctxt(d,"Seg A ↓",SA_RAIL,RL_Y,f10,BLUE)
    ctxt(d,"Seg B ↑",SB_RAIL,RL_Y,f10,TEAL)

    # ── footer ────────────────────────────────────────────────────────────────
    y_last = T_TOPS[0]+T_HGTS[0]
    FY = y_last+20
    bx(d, 2,FY, W-2,H-4, fill=NOTE_BG, outline=ORANGE, lw=1)
    txt(d,"  Seg A sel=0 ALIVE:     edc_ingress[x*5+y] → NOC DEMUX-A out0 → NOC nodes + chain T0→T1→T3→T2 → OVL MUX-A in0 → edc_egress[x*5+y] ↓",
        8, FY+8,  f11, GREEN)
    txt(d,"  Seg A sel=1 HARVESTED: edc_ingress[x*5+y] → NOC DEMUX-A out1 → bypass-A wire ↓ → OVL MUX-A in1 → edc_egress[x*5+y] ↓   [chain skipped]",
        8, FY+26, f11, RED)
    txt(d,"  Seg B sel=0 ALIVE:     loopback_ingress[x*5+y] → OVL DEMUX-B out0 → chain T0→T1→T3→T2 → NOC MUX-B in0 → loopback_egress[x*5+y] ↑",
        8, FY+44, f11, TEAL)
    txt(d,"  Seg B sel=1 HARVESTED: loopback_ingress[x*5+y] → OVL DEMUX-B out1 → bypass-B wire ↑ → NOC MUX-B in1 → loopback_egress[x*5+y] ↑   [chain skipped]",
        8, FY+62, f11, (0,130,80))
    txt(d,"  Dispatch Y=3: all mux/demux fixed sel=0; chain=postdfx_aon_clk; bypass RTL exists but never activated in N1B0",
        8, FY+80, f10, DGRAY)
    txt(d,"  Note: Seg B chain arrow B↑ reflects physical upward flow through tile (enters OVL bottom, exits NOC top). Same node order T0→T1→T3→T2 as Seg A.",
        8, FY+96, f10, (80,0,80))

    bx(d,0,0,W,H,fill=None,outline=BLUE,lw=2)
    save(img, "01_edc_ring_full_architecture_v0.8.png")


draw_fig4()
draw_fig1()

#!/usr/bin/env python3.11
"""
Redraw Fig 1, Fig 4, Fig 8 (×2) as PIL graphical diagrams.
"""

from PIL import Image, ImageDraw, ImageFont
import os

OUT = "/secure_data_from_tt/20260221/DOC/N1B0/edc_diagrams"
FP  = "/usr/share/fonts/dejavu/DejaVuSansMono.ttf"

def fnt(n): return ImageFont.truetype(FP, n)
f10=fnt(10); f11=fnt(11); f12=fnt(12); f13=fnt(13); f15=fnt(15); f17=fnt(17)

BG     = (255,255,255); BLACK=(20,20,20); BLUE=(0,80,160)
DGRAY  = (80,80,80);   LGRAY=(220,220,220); GRAY=(150,150,150)
RED    = (180,30,30);  GREEN=(20,130,40);  ORANGE=(180,90,0)
TEAL   = (0,110,110);  PURPLE=(100,30,150)
TILE_BG= (245,248,255); TILE_BIU=(240,250,240); TILE_DIS=(255,250,240)
BYPATH = (200,200,200)  # bypass wire color
BYP_BG = (255,235,235)  # harvested tile bg

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def arrow_down(d, x, y0, y1, color=BLACK, w=2):
    d.line([(x,y0),(x,y1)], fill=color, width=w)
    d.polygon([(x-6,y1-10),(x+6,y1-10),(x,y1)], fill=color)

def arrow_up(d, x, y0, y1, color=BLACK, w=2):  # y0 > y1 (going up)
    d.line([(x,y0),(x,y1)], fill=color, width=w)
    d.polygon([(x-6,y1+10),(x+6,y1+10),(x,y1)], fill=color)

def dashed_h(d, x0, x1, y, color=BYPATH, dash=8, gap=5, w=2):
    x = x0
    while x < x1:
        xe = min(x+dash, x1)
        d.line([(x,y),(xe,y)], fill=color, width=w)
        x += dash+gap

def dashed_v(d, x, y0, y1, color=BYPATH, dash=6, gap=4, w=2):
    y = y0
    while y < y1:
        ye = min(y+dash, y1)
        d.line([(x,y),(x,ye)], fill=color, width=w)
        y += dash+gap

def box(d, x0,y0,x1,y1, fill=TILE_BG, outline=BLACK, width=2):
    d.rectangle([x0,y0,x1,y1], fill=fill, outline=outline, width=width)

def trap(d, cx, cy, w_top, w_bot, h, fill, outline=BLACK):
    """Trapezoid centered at (cx,cy): narrow top, wide bottom"""
    pts = [(cx-w_top//2,cy-h//2),(cx+w_top//2,cy-h//2),
           (cx+w_bot//2,cy+h//2),(cx-w_bot//2,cy+h//2)]
    d.polygon(pts, fill=fill, outline=outline)

def ctext(d, txt, x0,x1,y, font=f11, fill=BLACK):
    tw = int(d.textlength(txt, font=font))
    d.text(((x0+x1)//2-tw//2, y), txt, font=font, fill=fill)

def ltext(d, txt, x, y, font=f11, fill=BLACK):
    d.text((x, y), txt, font=font, fill=fill)

def save(img, name):
    p = os.path.join(OUT, name)
    img.save(p, "PNG")
    W,H = img.size
    print(f"[ok] {p}  ({W}×{H})")


# ═════════════════════════════════════════════════════════════════════════════
# FIG 1 — Full Column EDC Ring (graphical, PIL-drawn)
# Both Segment A (right, ↓) and Segment B (left, ↑) clearly shown
# Bypass wires visible inside each tile
# ═════════════════════════════════════════════════════════════════════════════
def draw_fig1():
    W, H = 1160, 2420
    img = Image.new("RGB",(W,H),BG)
    d   = ImageDraw.Draw(img)

    # ── Layout constants ──────────────────────────────────────────────────────
    TX0, TX1 = 120, 940     # tile box left/right X
    SEG_A_X  = 1010         # Seg A vertical line X (right of tile)
    SEG_B_X  = 50           # Seg B vertical line X (left of tile)
    BYP_X0   = TX1 + 10     # bypass wire start (exits tile right edge)
    BYP_X1   = SEG_A_X - 5

    # Tile Y-positions (top of box)
    TITLE_H = 100
    LEGEND_H= 110
    TILES = {
        4: TITLE_H + LEGEND_H + 10,          # BIU
        3: TITLE_H + LEGEND_H + 230,         # Dispatch
        2: TITLE_H + LEGEND_H + 490,         # Tensix Y=2
        1: TITLE_H + LEGEND_H + 810,         # Tensix Y=1
        0: TITLE_H + LEGEND_H + 1130,        # Tensix Y=0
    }
    TILE_H = {4:200, 3:220, 2:290, 1:290, 0:330}

    def ty(y_idx): return TILES[y_idx]
    def th(y_idx): return TILE_H[y_idx]
    def tmid(y_idx): return ty(y_idx) + th(y_idx)//2

    # ── Title ─────────────────────────────────────────────────────────────────
    d.rectangle([0,0,W,TITLE_H], fill=(230,240,255))
    ctext(d,"Fig 1  —  One Column (e.g., X=1): Complete EDC Ring",0,W,12,f17,BLUE)
    ctext(d,"Both Segment A (direct ↓) and Segment B (loopback ↑) shown  |  Harvest bypass on every Tensix tile",0,W,36,f13,DGRAY)
    ctext(d,"LEGEND:  ────►  Segment A ring (down)     ◄────  Segment B ring (up)     ─ ─ ─►  Bypass wire (sel=1, harvested)",0,W,56,f12,DGRAY)
    ctext(d,"[DEMUX]  at NOC router entry  →  sel=0: into tile core  |  sel=1: into bypass wire",0,W,72,f12,ORANGE)
    ctext(d,"[ MUX ]  at overlay exit       →  sel=0: from tile core  |  sel=1: from bypass wire",0,W,86,f12,ORANGE)

    # ── Segment A and B vertical rail labels ──────────────────────────────────
    RAIL_TOP = TITLE_H + LEGEND_H + 10
    RAIL_BOT = ty(0) + th(0)

    # Seg A (right rail, ↓)
    d.rectangle([SEG_A_X-18, RAIL_TOP, SEG_A_X+18, RAIL_BOT], fill=(230,245,255), outline=BLUE, width=1)
    # Seg B (left rail, ↑)
    d.rectangle([SEG_B_X-18, RAIL_TOP, SEG_B_X+18, RAIL_BOT], fill=(255,245,230), outline=(160,100,0), width=1)

    for yy in range(RAIL_TOP+20, RAIL_BOT-20, 40):
        d.line([(SEG_A_X, yy),(SEG_A_X, yy+25)], fill=BLUE, width=2)
    for yy in range(RAIL_BOT-20, RAIL_TOP+20, -40):
        d.line([(SEG_B_X, yy),(SEG_B_X, yy-25)], fill=ORANGE, width=2)

    # Seg A label
    ltext(d,"Segment A",SEG_A_X-16,TITLE_H+LEGEND_H+15,f10,BLUE)
    ltext(d,"↓ DOWN",SEG_A_X-12,TITLE_H+LEGEND_H+27,f10,BLUE)
    # Seg B label
    ltext(d,"Segment B",SEG_B_X-16,TITLE_H+LEGEND_H+15,f10,(160,80,0))
    ltext(d,"↑ UP",SEG_B_X-8,TITLE_H+LEGEND_H+27,f10,(160,80,0))

    # ── APB4 input ─────────────────────────────────────────────────────────────
    apb_y = TITLE_H + LEGEND_H - 5
    ctext(d,"APB4 Firmware",TX0,TX1,apb_y-18,f12,DGRAY)
    arrow_down(d,(TX0+TX1)//2, apb_y-5, ty(4)+2, DGRAY)

    # ── Draw tiles ────────────────────────────────────────────────────────────
    def tile_y4():
        y0=ty(4); h=th(4); y1=y0+h
        box(d,TX0,y0,TX1,y1,fill=TILE_BIU)
        ltext(d," Y=4  ·  NOC2AXI tile  ·  BIU  (never harvested)",TX0+8,y0+6,f13,BLUE)
        d.line([(TX0+8,y0+22),(TX1-8,y0+22)],fill=LGRAY,width=1)

        # BIU block
        box(d,TX0+15,y0+28,TX1-15,y0+90,fill=(220,240,220),outline=GREEN,width=1)
        ltext(d,"  tt_edc1_biu_soc_apb4_wrap  (BIU  node_id=0x0000)",TX0+20,y0+31,f11,BLACK)
        ltext(d,"    u_edc_req_src  (IS_REQ_SRC=1)  — drives ring req_tgl/data outward",TX0+20,y0+44,f11,DGRAY)
        ltext(d,"    u_edc_rsp_snk  (IS_RSP_SINK=1) — receives ring rsp from nodes",TX0+20,y0+57,f11,DGRAY)
        ltext(d,"    fatal/crit/noncrit_irq  ──►  SoC interrupt controller",TX0+20,y0+70,f11,RED)

        # MUX (for Seg A output)
        my = y0+105
        box(d,TX0+15,my,TX0+140,my+50,fill=(255,240,200),outline=ORANGE,width=2)
        ltext(d," MUX (harvest) sel=0/1",TX0+18,my+3,f11,ORANGE)
        ltext(d,"  in0 ◄── ovl_egress  (NORMAL, sel=0)",TX0+18,my+16,f10,BLACK)
        ltext(d,"  in1 ◄── byp_from_below (sel=1, N/A)",TX0+18,my+28,f10,GRAY)
        ltext(d,"  out ──► edc_egress_intf[x*5+4]",TX0+18,my+40,f10,BLUE)

        # Seg A output arrow (right side)
        ax = TX1+5
        d.line([(TX1-30,y0+130),(ax,y0+130)],fill=BLUE,width=2)
        d.polygon([(ax,y0+127),(ax,y0+133),(ax+10,y0+130)],fill=BLUE)
        ltext(d,"edc_egress_intf\n[x*5+4]",ax+5,y0+122,f10,BLUE)

        # Seg B input arrow (left side)
        bx = TX0-5
        d.line([(SEG_B_X+18,y0+160),(bx,y0+160)],fill=ORANGE,width=2)
        d.polygon([(bx,y0+157),(bx,y0+163),(bx-10,y0+160)],fill=ORANGE)
        ltext(d,"loopback_edc\n_ingress_intf\n[x*5+4]",SEG_B_X-12,y0+152,f10,(150,80,0))

    def tile_y3():
        y0=ty(3); h=th(3); y1=y0+h
        box(d,TX0,y0,TX1,y1,fill=TILE_DIS)
        ltext(d," Y=3  ·  Dispatch/Router  ·  sel FIXED to 0 (NEVER harvested in N1B0)",TX0+8,y0+6,f13,ORANGE)
        ltext(d,"      NOTE: bypass RTL present for structural uniformity only",TX0+8,y0+20,f11,GRAY)
        d.line([(TX0+8,y0+35),(TX1-8,y0+35)],fill=LGRAY,width=1)

        # Seg B loopback path (left side, narrow box)
        LBX0,LBX1 = TX0+6,TX0+95
        LBY0,LBY1 = y0+40, y1-10
        box(d,LBX0,LBY0,LBX1,LBY1,fill=(230,255,245),outline=(0,130,100),width=1)
        ctext(d,"Seg B",LBX0,LBX1,LBY0+4,f10,(0,130,100))
        ctext(d,"loopback",LBX0,LBX1,LBY0+16,f10,(0,130,100))
        ctext(d,"repeater",LBX0,LBX1,LBY0+28,f10,(0,130,100))
        ctext(d,"(aon_clk)",LBX0,LBX1,LBY0+40,f10,(0,130,100))
        ctext(d,"no chain",LBX0,LBX1,LBY0+56,f10,(0,130,100))
        ctext(d,"visit",LBX0,LBX1,LBY0+68,f10,(0,130,100))

        # Seg B loopback arrows (left rail ↔ loopback box)
        lb_mid_x = (LBX0+LBX1)//2
        lb_mid_y = (LBY0+LBY1)//2
        d.line([(SEG_B_X+18,lb_mid_y),(LBX0,lb_mid_y)],fill=(0,130,100),width=2)
        d.polygon([(LBX0,lb_mid_y-4),(LBX0,lb_mid_y+4),(LBX0-10,lb_mid_y)],fill=(0,130,100))
        ltext(d,"loopback_edc\n_egress[x*5+3]",SEG_B_X-12,lb_mid_y-14,f10,(0,110,80))

        # DEMUX (Seg A, right portion)
        dy=y0+42
        box(d,LBX1+8,dy,TX0+220,dy+50,fill=(255,240,200),outline=ORANGE,width=2)
        ltext(d," DEMUX sel=0 fixed",LBX1+10,dy+3,f11,ORANGE)
        ltext(d,"  in  ◄── Seg A ring from Y=4",LBX1+10,dy+15,f10,BLACK)
        ltext(d,"  out0 ──► Dispatch/Router EDC chain (aon_clk, always)",LBX1+10,dy+27,f10,GREEN)

        # sub-chain
        sc=y0+100
        box(d,LBX1+8,sc,TX1-15,sc+60,fill=(245,245,245),outline=GRAY,width=1)
        ltext(d,"  Dispatch/Router EDC sub-chain  (postdfx_aon_clk)",LBX1+14,sc+5,f11,DGRAY)
        ltext(d,"  N/E/S/W/NIU/sec_fence nodes — errors reported on Seg A pass",LBX1+14,sc+18,f11,DGRAY)
        ltext(d,"  sel fixed=0: chain always traversed on Seg A; bypass never active",LBX1+14,sc+31,f11,DGRAY)

        # MUX
        mv=y0+170
        box(d,LBX1+8,mv,TX0+220,mv+40,fill=(255,240,200),outline=ORANGE,width=2)
        ltext(d," MUX sel=0 fixed",LBX1+10,mv+3,f11,ORANGE)
        ltext(d,"  in0 ◄── sub-chain output (always)",LBX1+10,mv+15,f10,GREEN)
        ltext(d,"  out ──► edc_egress_intf[x*5+3]",LBX1+10,mv+27,f10,BLUE)

        # Seg A arrows
        ax=TX1+5
        d.line([(TX1-20,y0+40),(ax,y0+40)],fill=LGRAY,width=1)  # in (gray, from above)
        d.line([(TX1-20,y0+190),(ax,y0+190)],fill=BLUE,width=2)
        d.polygon([(ax,y0+187),(ax,y0+193),(ax+10,y0+190)],fill=BLUE)
        ltext(d,"edc_egress_intf\n[x*5+3]",ax+5,y0+183,f10,BLUE)

    def tile_tensix(y_idx, label_extra=""):
        y0=ty(y_idx); h=th(y_idx); y1=y0+h
        box(d,TX0,y0,TX1,y1,fill=TILE_BG)
        ltext(d,f" Y={y_idx}  ·  Tensix  ·  tt_trin_noc_niu_router_wrap  +  tt_tensix_with_l1{label_extra}",TX0+8,y0+6,f13,BLUE)
        d.line([(TX0+8,y0+22),(TX1-8,y0+22)],fill=LGRAY,width=1)

        # Seg B loopback path (left side, narrow box) — aon_clk, does NOT enter aiclk chain
        LBX0,LBX1 = TX0+6, TX0+95
        LBY0,LBY1 = y0+28, y1-12
        box(d,LBX0,LBY0,LBX1,LBY1,fill=(230,255,245),outline=(0,130,100),width=1)
        ctext(d,"Seg B",LBX0,LBX1,LBY0+4,f10,(0,130,100))
        ctext(d,"loopback",LBX0,LBX1,LBY0+16,f10,(0,130,100))
        ctext(d,"repeater",LBX0,LBX1,LBY0+28,f10,(0,130,100))
        ctext(d,"(aon_clk)",LBX0,LBX1,LBY0+42,f10,(0,130,100))
        ctext(d,"────────",LBX0,LBX1,LBY0+58,f10,LGRAY)
        ctext(d,"No DEMUX",LBX0,LBX1,LBY0+72,f10,(0,100,80))
        ctext(d,"No MUX",LBX0,LBX1,LBY0+86,f10,(0,100,80))
        ctext(d,"No bypass",LBX0,LBX1,LBY0+100,f10,(0,100,80))
        ctext(d,"needed",LBX0,LBX1,LBY0+114,f10,(0,100,80))
        ctext(d,"────────",LBX0,LBX1,LBY0+130,f10,LGRAY)
        ctext(d,"aon_clk",LBX0,LBX1,LBY0+144,f10,(0,100,80))
        ctext(d,"stays on",LBX0,LBX1,LBY0+158,f10,(0,100,80))
        ctext(d,"even when",LBX0,LBX1,LBY0+172,f10,(0,100,80))
        ctext(d,"harvested",LBX0,LBX1,LBY0+186,f10,(0,100,80))

        # Seg B loopback arrows (left rail ↔ loopback box)
        lb_mid_y = (LBY0+LBY1)//2
        d.line([(SEG_B_X+18,lb_mid_y),(LBX0,lb_mid_y)],fill=(0,130,100),width=2)
        d.polygon([(LBX0,lb_mid_y-4),(LBX0,lb_mid_y+4),(LBX0-10,lb_mid_y)],fill=(0,130,100))
        ltext(d,f"loopback_edc\n_egress[x*5+{y_idx}]",SEG_B_X-12,lb_mid_y-14,f10,(0,110,80))

        # ── Seg A path (right portion of tile) ───────────────────────────────
        # DEMUX (Seg A only)
        dy=y0+28
        box(d,LBX1+8,dy,LBX1+220,dy+60,fill=(255,240,200),outline=ORANGE,width=2)
        ltext(d," DEMUX (harvest, Seg A)  sel=0/1",LBX1+10,dy+3,f11,ORANGE)
        ltext(d,"  in  ◄── edc_ingress_intf  (Seg A ring from above)",LBX1+10,dy+16,f10,BLACK)
        ltext(d,"  out0 ──► NOC nodes + aiclk sub-chain  (sel=0: ALIVE)",LBX1+10,dy+28,f10,GREEN)
        ltext(d,"  out1 ──► edc_egress_t6_byp_intf        (sel=1: HARVESTED)",LBX1+10,dy+40,f10,RED)
        ltext(d,"  NOC nodes (aon_clk) always active; i_harvest_en=1 gates errors",LBX1+10,dy+52,f10,DGRAY)

        # Bypass wire (dashed, to right side)
        byp_y = dy+46
        dashed_h(d, LBX1+220, BYP_X1, byp_y, RED, dash=9, gap=5, w=2)
        ltext(d,"bypass wire (no clock)",BYP_X1+2,byp_y-10,f10,RED)

        # sub-chain (aiclk)
        sc = y0+100
        box(d,LBX1+8,sc,TX1-15,sc+80,fill=(238,245,255),outline=TEAL,width=1)
        ltext(d,"  Tensix EDC sub-chain  (aiclk domain)  — Seg A only",LBX1+14,sc+5,f11,TEAL)
        ltext(d,"  T0→T1→(L1 partition: T6_MISC+L1W2)→T3→T2  (~80 nodes total)",LBX1+14,sc+18,f10,BLACK)
        ltext(d,"  sel=0 (ALIVE): nodes report errors normally on this Seg A pass",LBX1+14,sc+31,f10,GREEN)
        ltext(d,"  sel=1 (HARVESTED): aiclk STOPPED — chain dead — bypassed via bypass wire",LBX1+14,sc+44,f10,RED)
        ltext(d,"  Seg B (loopback) does NOT visit this chain — it uses loopback repeater at left",LBX1+14,sc+57,f10,DGRAY)

        # MUX (Seg A only)
        mv = y0+192
        box(d,LBX1+8,mv,LBX1+220,mv+60,fill=(255,240,200),outline=ORANGE,width=2)
        ltext(d," MUX (harvest, Seg A)  sel=0/1",LBX1+10,mv+3,f11,ORANGE)
        ltext(d,"  in0 ◄── ovl_egress_intf (sub-chain out)  (sel=0: ALIVE)",LBX1+10,mv+16,f10,GREEN)
        ltext(d,"  in1 ◄── edc_ingress_t6_byp_intf           (sel=1: HARVESTED)",LBX1+10,mv+28,f10,RED)
        # Connect bypass wire to MUX in1
        byp_in_y = mv+34
        d.line([(BYP_X1+2, byp_y),(BYP_X1+2, byp_in_y)],fill=RED,width=1)
        dashed_h(d, LBX1+220, BYP_X1+2, byp_in_y, RED, dash=9, gap=5, w=2)
        ltext(d,f"  out ──► edc_egress_intf[x*5+{y_idx}]  → Seg A ring continues to tile below",LBX1+10,mv+40,f10,BLUE)

        # Seg A arrows (right rail)
        ax=TX1+5
        d.line([(TX1-20,y0+38),(ax,y0+38)],fill=LGRAY,width=1)
        d.line([(TX1-20,y0+245),(ax,y0+245)],fill=BLUE,width=2)
        d.polygon([(ax,y0+242),(ax,y0+248),(ax+10,y0+245)],fill=BLUE)
        ltext(d,f"edc_egress_intf\n[x*5+{y_idx}]",ax+5,y0+237,f10,BLUE)

    def tile_y0():
        tile_tensix(0, "  (U-TURN at this tile)")
        y0=ty(0)
        h=th(0)
        # U-turn box
        ut_y = y0+h-100
        box(d,TX0+15,ut_y,TX1-15,ut_y+80,fill=(230,250,230),outline=GREEN,width=2)
        ltext(d,"  U-TURN  (trinity.sv L454-456)  ─── Segment A ends / Segment B begins ───",TX0+20,ut_y+5,f11,GREEN)
        ltext(d,"  tt_edc1_intf_connector  edc_loopback_conn_nodes  (y==0 block)",TX0+20,ut_y+18,f11,BLACK)
        ltext(d,"    .ingress_intf  ← edc_egress_intf[x*5+0]       (Seg A final output)",TX0+20,ut_y+31,f10,BLUE)
        ltext(d,"    .egress_intf   → loopback_edc_ingress_intf[x*5+0]  (Seg B starts here)",TX0+20,ut_y+44,f10,ORANGE)
        ltext(d,"  This is a pure combinational wire — no clock, no flip-flop",TX0+20,ut_y+57,f10,DGRAY)

        # U-turn curve
        ux = (TX0+TX1)//2
        uy0 = ty(0)+th(0)-102
        uy1 = ty(0)+th(0)-20
        arrow_down(d, SEG_A_X, uy0, uy1, BLUE)
        d.line([(SEG_A_X, uy1),(SEG_B_X, uy1)],fill=GREEN,width=3)
        arrow_up(d, SEG_B_X, uy1, uy0-10, ORANGE)
        ltext(d,"U-TURN",SEG_B_X+8,uy1-8,f11,GREEN)

    # ── Draw connector zones between tiles ───────────────────────────────────
    def connector(y_top, y_bot, y_upper, y_lower, label_a, label_b):
        cx_mid = (TX0+TX1)//2
        # Seg A arrow down
        arrow_down(d, SEG_A_X, y_top, y_bot, BLUE)
        ltext(d,label_a, SEG_A_X+5, (y_top+y_bot)//2-8, f10, BLUE)
        # Seg B arrow up
        arrow_up(d, SEG_B_X, y_bot-5, y_top+5, ORANGE)
        ltext(d,label_b, SEG_B_X-85, (y_top+y_bot)//2-8, f10, (130,70,0))
        # Connector label
        ctext(d,"tt_edc1_intf_connector  (direct + loopback)", TX0, TX1, (y_top+y_bot)//2-4, f10, GRAY)

    # ── Render all tiles ──────────────────────────────────────────────────────
    tile_y4()
    # connector Y=4→Y=3
    connector(ty(4)+th(4), ty(3),
              ty(4)+th(4), ty(3),
              "edc_direct_conn\n(Y=3←Y=4)",
              "loopback_conn\n(Y=3→Y=4)")
    tile_y3()
    connector(ty(3)+th(3), ty(2),
              ty(3)+th(3), ty(2),
              "edc_direct_conn\n(Y=2←Y=3)",
              "loopback_conn\n(Y=2→Y=3)")
    tile_tensix(2)
    connector(ty(2)+th(2), ty(1),
              ty(2)+th(2), ty(1),
              "edc_direct_conn\n(Y=1←Y=2)",
              "loopback_conn\n(Y=1→Y=2)")
    tile_tensix(1)
    connector(ty(1)+th(1), ty(0),
              ty(1)+th(1), ty(0),
              "edc_direct_conn\n(Y=0←Y=1)",
              "loopback_conn\n(Y=0→Y=1)")
    tile_y0()

    # ── Footer ────────────────────────────────────────────────────────────────
    fy = ty(0)+th(0)+15
    d.rectangle([0,fy,W,H],fill=(248,248,248))
    ltext(d,"  Seg A sel=0 (ALIVE):    ring ──► DEMUX out0 ──► NOC nodes + aiclk sub-chain (T0→T1→T3→T2) ──► MUX in0 ──► ring continues down",0,fy+8,f12,GREEN)
    ltext(d,"  Seg A sel=1 (HARVESTED): ring ──► DEMUX out1 ─ ─ bypass wire (combinational, no clock) ─ ─► MUX in1 ──► ring continues down",0,fy+24,f12,RED)
    ltext(d,"  Seg B (loopback ↑): passes through overlay_loopback_repeater (aon_clk) — does NOT enter aiclk sub-chain — NO bypass needed",0,fy+40,f11,(0,120,90))
    ltext(d,"  Bypass applies to Seg A ONLY.  Seg B always flows through because the aon_clk loopback repeater is alive even in harvested tiles.",0,fy+56,f11,DGRAY)

    d.rectangle([2,2,W-2,H-2],outline=BLUE,width=2)
    save(img,"01_edc_ring_full_architecture.png")

# ═════════════════════════════════════════════════════════════════════════════
# FIG 4 — Harvest Bypass Signal Flow per Tile
#
# CORRECT architecture (RTL-verified, §11.3):
#   • ONE DEMUX per tile: at NOC router (tt_trin_noc_niu_router_wrap) — Seg A only
#   • ONE MUX  per tile: at Overlay wrapper (tt_neo_overlay_wrapper)   — Seg A only
#   • Seg B (loopback): passes through overlay_loopback_repeater (aon_clk).
#     NO separate DEMUX/MUX. NO entry into aiclk tile chain.
#     A harvested tile's aon_clk logic is ALIVE, so Seg B can pass through without bypass.
#
# Layout: single tile in the center.
#   LEFT rail  = Seg B (loopback ↑): enters from bottom, exits at top — simple wire
#   RIGHT rail = Seg A (direct  ↓): enters from top,   exits at bottom — DEMUX→chain/bypass→MUX
# ═════════════════════════════════════════════════════════════════════════════
def draw_fig4():
    W, H = 1200, 1020
    img = Image.new("RGB",(W,H),BG)
    d   = ImageDraw.Draw(img)

    TITLE_H = 95
    PAD = 30

    # ── Title ─────────────────────────────────────────────────────────────────
    d.rectangle([0,0,W,TITLE_H],fill=(230,240,255))
    ctext(d,"Fig 4  —  Harvest Bypass Signal Flow per Tile",0,W,8,f17,BLUE)
    ctext(d,"Seg A (↓ direct path): ONE DEMUX (NOC router) + tile chain + ONE MUX (overlay) — bypass wire skips aiclk chain when harvested",0,W,32,f12,DGRAY)
    ctext(d,"Seg B (↑ loopback path): passes through overlay_loopback_repeater (aon_clk only) — NO DEMUX/MUX needed — aon_clk alive even when harvested",0,W,50,f12,(0,100,80))
    ctext(d,"sel=0 → tile ALIVE (chain traversed).   sel=1 → tile HARVESTED (chain bypassed via combinational wire).",0,W,68,f12,ORANGE)

    # ── Tile outer box ────────────────────────────────────────────────────────
    # Tile spans from x=200..x=1000, y=TITLE_H+80 to y=H-60
    TX0, TX1 = 200, 1000
    TY0, TY1 = TITLE_H + 80, H - 60
    box(d,TX0,TY0,TX1,TY1,fill=(247,250,255),outline=(80,80,200),width=3)
    ltext(d,"  Tile (Tensix Y=0/1/2  or  Dispatch Y=3, sel fixed=0)",TX0+8,TY0+6,f13,(80,80,200))

    # ── SEG A rail (right side) ───────────────────────────────────────────────
    SEG_A_X = TX1 + 50   # rail at right of tile
    # ring comes from ABOVE (tile Y+1) — enters at top
    RIN_Y  = TY0 - 50
    ROUT_Y = TY1 + 50

    arrow_down(d,SEG_A_X,RIN_Y-10,TY0+5,BLUE,w=3)
    ltext(d,"edc_ingress_intf[x*5+y]",SEG_A_X+8,RIN_Y-14,f11,BLUE)
    ltext(d,"(from tile above / BIU)",SEG_A_X+8,RIN_Y,f10,BLUE)

    # DEMUX box (inside tile, at top-right)
    DX0,DX1 = TX0+20, TX1-20
    DY0 = TY0 + 40
    DY1 = DY0 + 100
    box(d,DX0,DY0,DX1,DY1,fill=(255,250,225),outline=ORANGE,width=2)
    ltext(d,"  DEMUX  (tt_edc1_serial_bus_demux  ·  edc_demuxing_when_harvested)",DX0+6,DY0+5,f12,ORANGE)
    ltext(d,"  Module: tt_trin_noc_niu_router_wrap  (NOC router side)",DX0+6,DY0+19,f10,DGRAY)
    ltext(d,"  in  ◄── NOC router edc egress  (noc_niu_router_egress_intf)",DX0+6,DY0+33,f11,BLACK)
    ltext(d,"  sel=0  out0 ──────────────────────►  edc_egress_intf  → into tile chain  [ALIVE]",DX0+6,DY0+50,f11,GREEN)
    ltext(d,"  sel=1  out1 ─ ─ ─ ─ ─ ─ ─ ─►  edc_egress_t6_byp_intf  → bypass wire  [HARVESTED]",DX0+6,DY0+67,f11,RED)
    ltext(d,"  (aon_clk domain — always active; i_harvest_en=1 gates error inputs in NOC router)",DX0+6,DY0+83,f10,DGRAY)

    # Arrow from Seg A rail into DEMUX input
    arrow_down(d,SEG_A_X,TY0+5,DY0+50,BLUE,w=2)
    d.line([(DX0,DY0+50),(SEG_A_X,DY0+50)],fill=BLUE,width=2)

    # tile chain box
    CY0 = DY1 + 30
    CY1 = CY0 + 130
    box(d,DX0+40,CY0,DX1-40,CY1,fill=(235,245,255),outline=TEAL,width=2)
    ctext(d,"Tile EDC Sub-Chain  (aiclk domain)",DX0+40,DX1-40,CY0+6,f13,TEAL)
    ctext(d,"T0 → T1 → (L1 partition: T6_MISC + L1W2) → T3 → T2",DX0+40,DX1-40,CY0+25,f11,BLACK)
    ctext(d,"sel=0 (ALIVE): ai_clk running — all nodes active, errors reported",DX0+40,DX1-40,CY0+44,f11,GREEN)
    ctext(d,"sel=1 (HARVESTED): ai_clk STOPPED — chain bypassed via wire below",DX0+40,DX1-40,CY0+62,f11,RED)
    ctext(d,"NOC router nodes run on aon_clk (always active regardless of harvest)",DX0+40,DX1-40,CY0+82,f10,DGRAY)
    ctext(d,"~80 EDC nodes total per Tensix tile (T0/T1/T3/T2 × ~19 + L1 nodes)",DX0+40,DX1-40,CY0+98,f10,DGRAY)
    ctext(d,"~45 EDC nodes total per Dispatch tile",DX0+40,DX1-40,CY0+114,f10,DGRAY)

    # Arrow DEMUX out0 → chain
    CHAIN_CX = (DX0+40+DX1-40)//2
    arrow_down(d,CHAIN_CX,DY1,CY0,GREEN,w=2)
    ltext(d,"out0 (sel=0)",CHAIN_CX+6,DY1+4,f10,GREEN)

    # Bypass wire (dashed vertical, right of chain box)
    BYP_X = DX1 - 20
    BYP_Y0 = DY1 + 5
    BYP_Y1 = CY1 + 30 + 5    # will land at MUX in1 level
    dashed_v(d,BYP_X,BYP_Y0,BYP_Y1,RED,dash=9,gap=5,w=3)
    ltext(d,"bypass",BYP_X+4,(BYP_Y0+BYP_Y1)//2-7,f10,RED)
    ltext(d,"wire",  BYP_X+4,(BYP_Y0+BYP_Y1)//2+6,f10,RED)
    ltext(d,"(edc_egress_t6_byp_intf,",BYP_X+4,(BYP_Y0+BYP_Y1)//2+20,f10,RED)
    ltext(d," pure wire, no clock)",  BYP_X+4,(BYP_Y0+BYP_Y1)//2+33,f10,RED)

    # MUX box
    MY0 = CY1 + 30
    MY1 = MY0 + 100
    box(d,DX0,MY0,DX1,MY1,fill=(255,250,225),outline=ORANGE,width=2)
    ltext(d,"  MUX  (tt_edc1_serial_bus_mux  ·  edc_muxing_when_harvested)",DX0+6,MY0+5,f12,ORANGE)
    ltext(d,"  Module: tt_neo_overlay_wrapper  (overlay side)",DX0+6,MY0+19,f10,DGRAY)
    ltext(d,"  sel=0  in0 ◄── ovl_egress_intf  (tile chain output)  [ALIVE]",DX0+6,MY0+34,f11,GREEN)
    ltext(d,"  sel=1  in1 ◄─ ─ ─ ─ ─ ─ ─ ─  edc_ingress_t6_byp_intf  (bypass wire)  [HARVESTED]",DX0+6,MY0+51,f11,RED)
    ltext(d,"  out ──────────────────────────►  edc_egress_intf[x*5+y]  → into ring (to tile below)",DX0+6,MY0+68,f11,BLUE)
    ltext(d,"  (aon_clk domain — both sel=0/1 output is combinational relative to ring)",DX0+6,MY0+83,f10,DGRAY)

    # Arrow chain → MUX in0
    arrow_down(d,CHAIN_CX,CY1,MY0+40,GREEN,w=2)
    ltext(d,"in0 (sel=0)",CHAIN_CX+6,CY1+4,f10,GREEN)

    # Connect bypass wire top to DEMUX annotation
    d.line([(BYP_X,DY1+5),(DX1-6,DY1+5)],fill=RED,width=2)
    # Connect bypass wire bottom to MUX in1
    d.line([(BYP_X,BYP_Y1),(DX1-6,BYP_Y1)],fill=RED,width=2)
    ltext(d,"in1",DX1-35,BYP_Y1-14,f10,RED)

    # Arrow from MUX out → Seg A rail continues DOWN
    MUX_OUT_Y = MY0 + 60
    d.line([(DX0,MUX_OUT_Y),(SEG_A_X,MUX_OUT_Y)],fill=BLUE,width=2)
    arrow_down(d,SEG_A_X,MUX_OUT_Y,ROUT_Y,BLUE,w=3)
    ltext(d,"edc_egress_intf[x*5+y]",SEG_A_X+8,ROUT_Y-14,f11,BLUE)
    ltext(d,"(to tile below / U-turn at Y=0)",SEG_A_X+8,ROUT_Y,f10,BLUE)

    # ── SEG B rail (left side) ────────────────────────────────────────────────
    SEG_B_X = TX0 - 50   # rail at left of tile
    LOOPBK_BG = (230,255,245)

    # Loopback repeater box inside tile (left section)
    LX0, LX1 = TX0+10, TX0+160
    LY0_box = TY0 + 40
    LY1_box = LY0_box + 200
    box(d,LX0,LY0_box,LX1,LY1_box,fill=LOOPBK_BG,outline=(0,130,100),width=2)
    ctext(d,"Seg B path",LX0,LX1,LY0_box+6,f12,(0,130,100))
    ctext(d,"(loopback)",LX0,LX1,LY0_box+22,f12,(0,130,100))
    ctext(d,"overlay_",LX0,LX1,LY0_box+42,f10,DGRAY)
    ctext(d,"loopback_",LX0,LX1,LY0_box+56,f10,DGRAY)
    ctext(d,"repeater",LX0,LX1,LY0_box+70,f10,DGRAY)
    ctext(d,"(aon_clk)",LX0,LX1,LY0_box+86,f10,DGRAY)
    ctext(d,"NO DEMUX",LX0,LX1,LY0_box+106,f10,(0,100,80))
    ctext(d,"NO MUX",LX0,LX1,LY0_box+120,f10,(0,100,80))
    ctext(d,"NO bypass",LX0,LX1,LY0_box+134,f10,(0,100,80))
    ctext(d,"needed",LX0,LX1,LY0_box+148,f10,(0,100,80))
    ctext(d,"aon_clk",LX0,LX1,LY0_box+166,f10,(0,100,80))
    ctext(d,"always on",LX0,LX1,LY0_box+180,f10,(0,100,80))

    # Loopback enters from BELOW (from tile Y-1)
    LB_MID = (LX0+LX1)//2
    arrow_up(d,LB_MID,TY1,LY1_box,(0,130,100),w=3)
    arrow_up(d,LB_MID,LY0_box,TY0-10,(0,130,100),w=3)
    # left rail line
    d.line([(SEG_B_X,TY0-10),(LB_MID,TY0-10)],fill=(0,130,100),width=2)
    d.line([(SEG_B_X,TY1),(LB_MID,TY1)],fill=(0,130,100),width=2)
    arrow_up(d,SEG_B_X,ROUT_Y-20,RIN_Y-10,(0,130,100),w=3)

    ltext(d,"loopback_edc_egress_intf[x*5+y]",SEG_B_X-190,RIN_Y-14,f11,(0,130,100))
    ltext(d,"(to tile above / BIU at Y=4)",    SEG_B_X-178,RIN_Y,    f10,(0,130,100))
    ltext(d,"loopback_edc_ingress_intf[x*5+y]",SEG_B_X-198,ROUT_Y-14,f11,(0,130,100))
    ltext(d,"(from tile below / Y=0 U-turn)",  SEG_B_X-188,ROUT_Y,   f10,(0,130,100))

    # ── Key note box ─────────────────────────────────────────────────────────
    NOTE_Y = MY1 + 14
    box(d,TX0+10,NOTE_Y,TX1-10,NOTE_Y+70,fill=(255,245,230),outline=ORANGE,width=1)
    ctext(d,"Why Seg B needs no bypass:",TX0+10,TX1-10,NOTE_Y+4,f12,ORANGE)
    ctext(d,"The loopback_edc_*_intf passes only through aon_clk logic (overlay_loopback_repeater).",TX0+10,TX1-10,NOTE_Y+22,f11,BLACK)
    ctext(d,"When a tile is 'harvested', only the aiclk cores stop — aon_clk remains running.",TX0+10,TX1-10,NOTE_Y+38,f11,BLACK)
    ctext(d,"The loopback repeater is in aon_clk domain → Seg B flows through harvested tile without bypass.",TX0+10,TX1-10,NOTE_Y+54,f11,BLACK)

    # ── Direction key ─────────────────────────────────────────────────────────
    KEY_Y = H - 55
    d.rectangle([PAD,KEY_Y,W-PAD,KEY_Y+44],fill=(240,245,255),outline=LGRAY,width=1)
    ltext(d,"Seg A (blue ↓):  edc_ingress/egress_intf          — BIU sends cmd DOWN, each tile's aiclk chain visited, U-turn at Y=0",PAD+10,KEY_Y+5,f11,BLUE)
    ltext(d,"Seg B (teal ↑):  loopback_edc_ingress/egress_intf — return path UP; aon_clk only; NO aiclk chain visit; NO bypass logic",PAD+10,KEY_Y+24,f11,(0,130,100))

    d.rectangle([2,2,W-2,H-2],outline=BLUE,width=2)
    save(img,"04_harvest_bypass_signal_flow.png")


# ═════════════════════════════════════════════════════════════════════════════
# FIG 8A — Timing Diagram: Node→BIU (Error Report, WRITE case)
# ═════════════════════════════════════════════════════════════════════════════
def draw_fig8_write():
    """Node (ai_clk) sends error packet to BIU (noc_clk)."""
    _draw_timing(
        title="Fig 8a  —  Toggle Handshake: Node → BIU  (Error Report / Write case)",
        subtitle="Node (ai_clk domain) detects error, drives req_tgl + data → BIU (noc_clk domain) echoes ack_tgl",
        src_name="Node (ai_clk)",  src_color=TEAL,
        snk_name="BIU  (noc_clk)", snk_color=RED,
        src_clk_label="ai_clk  (node)",
        snk_clk_label="noc_clk (BIU)",
        req_driven_by="NODE: req_tgl toggles 10→01  (drives error packet fragment)",
        ack_driven_by="BIU:  ack_tgl echoes req_tgl  (confirms fragment received)",
        state_wait_label="WAIT_ACK  (node waiting for BIU echo)",
        state_done_label="ACCEPTED  → advance to next fragment",
        out_name="08a_write_timing_node_to_biu.png",
    )

def draw_fig8_read():
    """BIU (noc_clk) sends query to Node (ai_clk)."""
    _draw_timing(
        title="Fig 8b  —  Toggle Handshake: BIU → Node  (Firmware Poll / Read case)",
        subtitle="BIU (noc_clk domain) sends WR/RD command, drives req_tgl → Node (ai_clk domain) echoes ack_tgl",
        src_name="BIU (noc_clk)", src_color=RED,
        snk_name="Node (ai_clk)", snk_color=TEAL,
        src_clk_label="noc_clk (BIU)",
        snk_clk_label="ai_clk  (node)",
        req_driven_by="BIU:  req_tgl toggles 10→01  (drives command packet fragment)",
        ack_driven_by="NODE: ack_tgl echoes req_tgl  (confirms fragment received)",
        state_wait_label="WAIT_ACK  (BIU waiting for node echo)",
        state_done_label="ACCEPTED  → advance / send next fragment",
        out_name="08b_read_timing_biu_to_node.png",
    )

def _draw_timing(title,subtitle,src_name,src_color,snk_name,snk_color,
                 src_clk_label,snk_clk_label,
                 req_driven_by,ack_driven_by,
                 state_wait_label,state_done_label,out_name):
    """Generic timing diagram generator."""
    SIG_W  = 230
    CYC_W  = 190
    ROW_H  = 75
    WH     = 25
    PAD    = 22
    TITLE_H= 82
    HDR_H  = 50

    CYC_LABELS = [
        ("N−1","(context)"),
        ("N","(src drives\nreq+data+parity)"),
        ("N+1","(CDC crossing\nasync wires)"),
        ("N+2","(snk echoes\nack_tgl)"),
        ("N+3","(src sees\nack==req)"),
        ("N+4","(next\nfragment)"),
    ]
    NC = len(CYC_LABELS)
    ROWS = [
        f"{src_clk_label}\n(source clock)",
        f"req_tgl\n[1:0]",
        "data\n[15:0]",
        "data_p\n[0]",
        "── CDC ──\n(domain cross)",
        f"{snk_clk_label}\n(sink clock)",
        "ack_tgl\n[1:0]",
        "state",
    ]
    NR=len(ROWS)

    W = PAD+SIG_W+CYC_W*NC+PAD
    H = PAD+TITLE_H+HDR_H+ROW_H*NR+100+PAD

    img=Image.new("RGB",(W,H),BG)
    d=ImageDraw.Draw(img)

    CDC_BG=(255,250,215)
    WAIT_BG=(255,235,210)
    DONE_BG=(210,245,215)
    IDLE_BG=(235,235,235)

    def cx(i): return PAD+SIG_W+i*CYC_W
    def ry(i): return PAD+TITLE_H+HDR_H+i*ROW_H
    def ry_mid(i): return ry(i)+ROW_H//2
    def ry_hi(i): return ry_mid(i)-WH
    def ry_lo(i): return ry_mid(i)+WH

    WAVE_TOP=PAD+TITLE_H+HDR_H
    WAVE_BOT=WAVE_TOP+ROW_H*NR

    def hl(x0,x1,y,col,w=2): d.line([(x0,y),(x1,y)],fill=col,width=w)
    def vl(x,y0,y1,col,w=2): d.line([(x,y0),(x,y1)],fill=col,width=w)
    def clock_row(r,x0,x1,col,hw=None):
        if hw is None: hw=CYC_W//5
        x=x0; yhi=ry_hi(r); ylo=ry_lo(r)
        while x<x1:
            xe=min(x+hw,x1); hl(x,xe,ylo,col); x=xe
            if x>=x1: break
            vl(x,ylo,yhi,col)
            xe=min(x+hw,x1); hl(x,xe,yhi,col); x=xe
            if x>=x1: break
            vl(x,yhi,ylo,col)
    def bus_stable(r,x0,x1,lbl,col,fill=None):
        notch=10; yhi=ry_hi(r); ylo=ry_lo(r); ym=ry_mid(r)
        if fill: d.polygon([(x0+notch,yhi),(x1-notch,yhi),(x1,ym),(x1-notch,ylo),(x0+notch,ylo),(x0,ym)],fill=fill)
        hl(x0+notch,x1-notch,yhi,col); hl(x0+notch,x1-notch,ylo,col)
        d.line([(x0+notch,yhi),(x0,ym)],fill=col,width=2)
        d.line([(x0,ym),(x0+notch,ylo)],fill=col,width=2)
        d.line([(x1-notch,yhi),(x1,ym)],fill=col,width=2)
        d.line([(x1,ym),(x1-notch,ylo)],fill=col,width=2)
        tw=int(d.textlength(lbl,font=f11))
        d.text(((x0+x1)//2-tw//2,ym-7),lbl,font=f11,fill=col)
    def bus_x(r,x,col):
        notch=10; yhi=ry_hi(r); ylo=ry_lo(r)
        d.line([(x-notch,yhi),(x+notch,ylo)],fill=col,width=2)
        d.line([(x-notch,ylo),(x+notch,yhi)],fill=col,width=2)
    def bhi(r,x0,x1,col): hl(x0,x1,ry_hi(r),col)
    def blo(r,x0,x1,col): hl(x0,x1,ry_lo(r),col)
    def rise(r,x,col): vl(x,ry_lo(r),ry_hi(r),col)
    def fall(r,x,col): vl(x,ry_hi(r),ry_lo(r),col)
    def state_box(r,x0,x1,lbl,bg,fg=BLACK):
        y0=ry_hi(r)-2; y1=ry_lo(r)+2
        d.rectangle([x0+2,y0,x1-2,y1],fill=bg,outline=fg,width=1)
        tw=int(d.textlength(lbl,font=f11)); tx=(x0+x1)//2-tw//2
        d.text((tx,(y0+y1)//2-7),lbl,font=f11,fill=fg)

    # Title
    d.rectangle([0,0,W,TITLE_H],fill=(230,240,255))
    d.text((PAD,PAD),title,font=f15,fill=BLUE)
    d.text((PAD,PAD+22),subtitle,font=f12,fill=DGRAY)
    d.text((PAD,PAD+40),f"Source: {src_name}  |  {req_driven_by}",font=f11,fill=src_color)
    d.text((PAD,PAD+56),f"Sink:   {snk_name}  |  {ack_driven_by}",font=f11,fill=snk_color)
    d.text((PAD,PAD+68),"Ring transport (connectors/mux/demux) is purely combinational — ASYNC, no clock.",font=f11,fill=ORANGE)

    # CDC shading
    d.rectangle([cx(2),WAVE_TOP,cx(3),WAVE_BOT],fill=CDC_BG)
    d.rectangle([cx(0),WAVE_TOP,cx(1),WAVE_BOT],fill=(248,248,248))

    # Cycle headers
    for i,(cyc,sub) in enumerate(CYC_LABELS):
        x0,x1=cx(i),cx(i+1)
        col=GRAY if i==0 else BLUE
        ctext(d,cyc,x0,x1,PAD+TITLE_H+4,f15,col)
        sc=ORANGE if i==2 else (GRAY if i==0 else DGRAY)
        yt=PAD+TITLE_H+24
        for sl in sub.split("\n"):
            ctext(d,sl,x0,x1,yt,f11,sc); yt+=14

    # Grid
    for i in range(NC+1):
        col=GRAY if i<=1 else LGRAY
        vl(cx(i),WAVE_TOP,WAVE_BOT,col,1)
    for i in range(NR+1):
        hl(PAD,W-PAD,ry(i),LGRAY,1)

    # Signal names
    for i,sig in enumerate(ROWS):
        parts=sig.split("\n"); yt=ry_mid(i)-len(parts)*7
        is_cdc="CDC" in sig
        for p in parts:
            d.text((PAD+4,yt),p,font=f11 if not is_cdc else f11,fill=ORANGE if is_cdc else BLACK)
            yt+=14

    # CDC annotation
    d.text((cx(2)+4,WAVE_TOP+4),"CDC crossing",font=f11,fill=ORANGE)
    d.text((cx(2)+4,WAVE_TOP+18),"(async wires,",font=f11,fill=ORANGE)
    d.text((cx(2)+4,WAVE_TOP+32),"no clock)",font=f11,fill=ORANGE)

    # Row 0: source clock
    clock_row(0,cx(0),cx(1),GRAY)
    clock_row(0,cx(1),cx(NC),src_color)
    d.text((cx(1)+4,ry_hi(0)-14),"source clock",font=f11,fill=src_color)

    # Row 1: req_tgl
    bus_stable(1,cx(0),cx(1),"2'b10 (prev)",GRAY,fill=(245,245,245))
    bus_x(1,cx(1),src_color)
    bus_stable(1,cx(1),cx(5),"req_tgl = 2'b01  (stable, driven by source, waiting for sink echo)",src_color,fill=(235,245,255))
    bus_x(1,cx(5),src_color)
    bus_stable(1,cx(5),cx(NC),"2'b10 (next)",GREEN,fill=(225,245,225))
    d.text((cx(1)+3,ry_hi(1)-16),"① source toggles",font=f11,fill=src_color)

    # Row 2: data
    bus_stable(2,cx(0),cx(1),"prev frg data",GRAY,fill=(245,245,245))
    bus_x(2,cx(1),src_color)
    bus_stable(2,cx(1),cx(5),"fragment data  (16-bit, e.g. frg[2]=SRC_ID)  — stable, driven by source",src_color,fill=(235,245,255))
    bus_x(2,cx(5),src_color)
    bus_stable(2,cx(5),cx(NC),"next frg",GREEN,fill=(225,245,225))

    # Row 3: data_p
    blo(3,cx(0),cx(1),GRAY)
    rise(3,cx(1),src_color)
    bhi(3,cx(1),cx(5),src_color)
    d.text((cx(2)+4,ry_hi(3)+3),"parity bit (stable)",font=f11,fill=DGRAY)
    fall(3,cx(5),src_color)
    blo(3,cx(5),cx(NC),GREEN)

    # Row 4: CDC separator (already annotated above)

    # Row 5: sink clock
    clock_row(5,cx(0),cx(3),GRAY)
    clock_row(5,cx(3),cx(NC),snk_color)
    d.text((cx(3)+4,ry_hi(5)-14),"sink clock",font=f11,fill=snk_color)

    # Row 6: ack_tgl
    bus_stable(6,cx(0),cx(3),"2'b10 (prev ack, unchanged)",GRAY,fill=(245,245,245))
    bus_x(6,cx(3),snk_color)
    bus_stable(6,cx(3),cx(NC),"ack_tgl = 2'b01  (sink echoes req_tgl, confirms receipt)",snk_color,fill=(255,235,235))
    d.text((cx(3)+3,ry_hi(6)-16),"③ sink echoes",font=f11,fill=snk_color)
    d.text((cx(4)+3,ry_hi(6)-16),"④ src: ack==req",font=f11,fill=GREEN)

    # Row 7: state
    state_box(7,cx(0),cx(1),"IDLE / prev",IDLE_BG,DGRAY)
    state_box(7,cx(1),cx(4),state_wait_label,WAIT_BG,ORANGE)
    state_box(7,cx(4),cx(5),state_done_label,DONE_BG,GREEN)
    state_box(7,cx(5),cx(NC),"next fragment",( 230,245,230),GREEN)

    # Annotations
    ann_y=WAVE_BOT+10
    anns=[
        (cx(1),cx(2),"①  Source drives\n    req_tgl (toggle),\n    data[15:0], parity",src_color),
        (cx(2),cx(3),"②  CDC crossing:\n    toggle propagates\n    via comb. wires",ORANGE),
        (cx(3),cx(4),"③  Sink samples\n    req_tgl on its clock,\n    echoes ack_tgl",snk_color),
        (cx(4),cx(5),"④  Source sees\n    ack==req\n    → ACCEPTED",GREEN),
        (cx(5),cx(NC),"⑤  Next fragment:\n    req_tgl toggles\n    01→10",BLUE),
    ]
    for x0,x1,txt,col in anns:
        xc=(x0+x1)//2
        for yy in range(WAVE_BOT,ann_y,3): d.point((xc,yy),fill=LGRAY)
        yt=ann_y
        for ln in txt.split("\n"):
            tw=int(d.textlength(ln,font=f11))
            d.text((xc-tw//2,yt),ln,font=f11,fill=col); yt+=14

    d.rectangle([PAD-2,PAD-2,W-PAD+2,H-PAD+2],outline=BLUE,width=2)
    img_out=Image.new("RGB",(W,H),BG)
    img_out.paste(img,(0,0))
    save(img_out, out_name)


# ─────────────────────────────────────────────────────────────────────────────
# RUN ALL
# ─────────────────────────────────────────────────────────────────────────────
draw_fig1()
draw_fig4()
draw_fig8_write()
draw_fig8_read()

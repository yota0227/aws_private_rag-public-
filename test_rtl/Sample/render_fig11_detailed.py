#!/usr/bin/env python3.11
"""
Fig 11 — Full End-to-End EDC Event Path (detailed, HW vs SW separated).
"""

from PIL import Image, ImageDraw, ImageFont
import os

OUT = "/secure_data_from_tt/20260221/DOC/N1B0/edc_diagrams/11_full_path_summary.png"
FP  = "/usr/share/fonts/dejavu/DejaVuSansMono.ttf"

f11 = ImageFont.truetype(FP, 11)
f12 = ImageFont.truetype(FP, 12)
f13 = ImageFont.truetype(FP, 13)
f15 = ImageFont.truetype(FP, 15)
f17 = ImageFont.truetype(FP, 17)

BG     = (255, 255, 255)
BLACK  = ( 20,  20,  20)
BLUE   = (  0,  80, 160)
DGRAY  = ( 80,  80,  80)
LGRAY  = (230, 230, 230)
GRAY   = (160, 160, 160)
RED    = (180,  30,  30)
GREEN  = ( 20, 130,  40)
ORANGE = (180,  90,   0)
PURPLE = (110,  30, 160)
TEAL   = (  0, 120, 120)

HW_BG  = (245, 250, 255)   # HW block background
SW_BG  = (250, 250, 235)   # SW block background
HW_HDR = (210, 225, 250)   # HW section header
SW_HDR = (245, 240, 200)   # SW section header

# ── Layout ────────────────────────────────────────────────────────────────────
PAD    = 24
COL_W  = [50, 55, 90, 85, 790]   # Stage | HW/SW | Module | Clock | Description
TOTAL_W = PAD + sum(COL_W) + len(COL_W)*6 + PAD
LINE_H = 15
CELL_PAD = 5

# ── Build content rows ────────────────────────────────────────────────────────
# Each row is a list of (text, color, font, bg_override)
# We'll compute heights dynamically based on description lines.

STAGES = [
    # ── HW section header ────────────────────────────────────────────────────
    {"type": "hw_hdr"},

    # Stage 1
    {"type": "stage",
     "num": "1",
     "hw_sw": "HW",
     "module": "tt_instrn_engine\n_wrapper\n(T0, X=1, Y=2)",
     "clock": "AI clock\n(ai_clk)",
     "desc": [
         ("HARDWARE ERROR DETECTION", BLUE, f13),
         ("", None, f12),
         ("The Unpacker sub-core inside T0 detects a data integrity error.", BLACK, f12),
         ("Hardware asserts:  i_event[UNC_ERR] = 1  (combinational signal)", BLACK, f12),
         ("This is the raw error signal from the datapath — no software involvement yet.", DGRAY, f11),
         ("", None, f12),
         ("No firmware action required at this stage.", GRAY, f11),
     ]},

    # Stage 2
    {"type": "stage",
     "num": "2",
     "hw_sw": "HW",
     "module": "tt_edc1_node\n(UNPACK\ninst=0x05)\nnode_id=0x8205",
     "clock": "AI clock\n(ai_clk)",
     "desc": [
         ("EDC NODE: CAPTURES EVENT & BUILDS 5-FRAGMENT PACKET", BLUE, f13),
         ("", None, f12),
         ("① Latches i_event[UNC_ERR] on rising edge of ai_clk.", BLACK, f12),
         ("② Encodes its own node_id = 0x8205 as SRC_ID:", BLACK, f12),
         ("     bits[15:11] = 0x10  →  TENSIX_BASE part (T0 core)", TEAL, f12),
         ("     bits[10:8]  = 2     →  subp = Y=2 (cluster row in column)", TEAL, f12),
         ("     bits[7:0]   = 0x05  →  inst = UNPACK_EDC_IDX", TEAL, f12),
         ("     The BIU also knows which column (X=1) from which BIU[1] fires.", TEAL, f12),
         ("③ Builds 5×16-bit fragments:", BLACK, f12),
         ("     frg[0] = 0x0000   TGT_ID = BIU (destination address)", ORANGE, f12),
         ("     frg[1] = 0x9100   CMD=9(UNC_ERR_CMD), PYLD_LEN=1, event_id=0", ORANGE, f12),
         ("     frg[2] = 0x8205   SRC_ID = self (identifies this node)", ORANGE, f12),
         ("     frg[3] = 0x0000   DATA header padding", ORANGE, f12),
         ("     frg[4] = 0xXXXX   Captured error address (payload)", ORANGE, f12),
         ("④ Waits for ring token before starting serial transfer.", DGRAY, f11),
     ]},

    # Stage 3
    {"type": "stage",
     "num": "3",
     "hw_sw": "HW",
     "module": "edc1_serial_bus\n_intf_def\n(ingress→egress)\nreq/ack toggle",
     "clock": "AI clock\n→ NOC clock\n(CDC crossing)",
     "desc": [
         ("TOGGLE HANDSHAKE SERIAL TRANSFER  (5 fragments × ~4 cycles = ~20 cycles)", BLUE, f13),
         ("", None, f12),
         ("The EDC node serializes the packet one 16-bit fragment at a time using a", BLACK, f12),
         ("2-bit toggle handshake protocol.  For each fragment:", BLACK, f12),
         ("", None, f12),
         ("  AI cyc N:    Node drives  req_tgl[1:0] ← toggled value  (01 or 10, alternating)", BLACK, f12),
         ("                            data[15:0]   ← fragment data", BLACK, f12),
         ("                            data_p[0]    ← odd parity of data", BLACK, f12),
         ("  AI cyc N+1:  Toggle propagates through combinational ring wires  (CDC crossing)", ORANGE, f12),
         ("  NOC cyc N+2: BIU samples req_tgl on noc_clk edge,", BLACK, f12),
         ("               echoes  ack_tgl[1:0] ← req_tgl  (confirms receipt)", BLACK, f12),
         ("  AI cyc N+3:  Node sees  ack_tgl == req_tgl → fragment ACCEPTED", GREEN, f12),
         ("               Advances fragment counter, starts next fragment.", GREEN, f12),
         ("", None, f12),
         ("Why toggle instead of a level signal?  Toggling is CDC-safe:", DGRAY, f11),
         ("  A level change is detectable even if the receiving clock is much slower.", DGRAY, f11),
         ("  Single-bit toggle cannot be corrupted by a missed edge.", DGRAY, f11),
     ]},

    # Stage 4 — key: ASYNC explanation
    {"type": "stage",
     "num": "4",
     "hw_sw": "HW",
     "module": "tt_edc1_intf\n_connector ×N\ntt_edc1_serial\n_bus_mux\ntt_edc1_serial\n_bus_demux",
     "clock": "ASYNC\n(no clock\non wires)",
     "desc": [
         ("RING TRAVERSAL  —  WHAT DOES \"ASYNC (no clock)\" MEAN?", BLUE, f13),
         ("", None, f12),
         ("The ring transport path between tiles consists entirely of COMBINATIONAL logic.", RED, f12),
         ("There are ZERO registered (flip-flop) stages in the inter-tile path:", RED, f12),
         ("", None, f12),
         ("  • tt_edc1_intf_connector       = pure wire  (just connects two interfaces)", BLACK, f12),
         ("  • tt_edc1_serial_bus_mux  sel=0 = combinational 2:1 mux  (no FF)", BLACK, f12),
         ("  • tt_edc1_serial_bus_demux sel=0= combinational demux    (no FF)", BLACK, f12),
         ("  • tt_edc1_serial_bus_rep        = buffer chain (drive strength, still comb.)", BLACK, f12),
         ("", None, f12),
         ("Result: req_tgl/data signals travel like any combinational wire — they arrive", BLACK, f12),
         ("at the BIU's input with only gate+wire propagation delay, NOT at a clock edge.", BLACK, f12),
         ("The toggle handshake (Stage 3) handles all synchronization — no transport clock.", BLACK, f12),
         ("", None, f12),
         ("Physical path for packet from T0 UNPACK (X=1, Y=2) to BIU (Y=4):", TEAL, f13),
         ("  ① [T0 UNPACK egress]", TEAL, f12),
         ("      ↓  edc_conn_T0_to_L1          (tt_edc1_intf_connector — pure wire)", TEAL, f12),
         ("      ↓  edc_conn_L1_to_overlay      (tt_edc1_intf_connector — pure wire)", TEAL, f12),
         ("      ↓  tt_neo_overlay_wrapper", TEAL, f12),
         ("      ↓  tt_edc1_serial_bus_mux  sel=0  (Y=2, tile alive → take in0)", TEAL, f12),
         ("      ↓  edc_egress_intf[1*5+2=7]   (index = col1 × 5 + row2)", TEAL, f12),
         ("  ② edc_direct_conn_nodes  (tt_edc1_intf_connector, Y=2→Y=1)", TEAL, f12),
         ("      ↓  tt_trin_noc_niu_router_wrap (X=1, Y=1)", TEAL, f12),
         ("         NOC EDC nodes: TGT_ID=0x0000 ≠ own_id → PASS-THROUGH", DGRAY, f11),
         ("      ↓  tt_edc1_serial_bus_demux  sel=0  (pass-through, no harvest)", TEAL, f12),
         ("  ③ edc_direct_conn_nodes  (Y=1→Y=0)", TEAL, f12),
         ("      ↓  tt_trin_noc_niu_router_wrap (X=1, Y=0)  → PASS-THROUGH", TEAL, f12),
         ("      ↓  tt_edc1_serial_bus_demux  sel=0", TEAL, f12),
         ("  ④ U-TURN: edc_loopback_conn_nodes  (trinity.sv L454-456)", ORANGE, f12),
         ("      ↓  loopback_edc_ingress_intf[1*5+0]  (Segment A→B boundary)", ORANGE, f12),
         ("  ⑤ Loopback path back UP through Y=0 → Y=1 → Y=2 → Y=3", TEAL, f12),
         ("  ⑥ [BIU at Y=4] tt_edc1_biu_soc_apb4_wrap ingress_intf", TEAL, f12),
         ("", None, f12),
         ("PASS-THROUGH: intermediate nodes check TGT_ID.  If TGT_ID ≠ own node_id,", DGRAY, f11),
         ("the node forwards ingress→egress unchanged.  Does NOT consume the packet.", DGRAY, f11),
     ]},

    # ── SW section header ────────────────────────────────────────────────────
    {"type": "sw_hdr"},

    # Stage 5
    {"type": "stage",
     "num": "5",
     "hw_sw": "HW",
     "module": "tt_edc1_state\n_machine\nu_edc_rsp_snk\n(IS_RSP_SINK=1)",
     "clock": "NOC clock\n(noc_clk)",
     "desc": [
         ("BIU DESERIALIZES PACKET  (still hardware — auto CSR write)", BLUE, f13),
         ("", None, f12),
         ("tt_edc1_state_machine (IS_RSP_SINK=1) samples each fragment:", BLACK, f12),
         ("  frg[0] → RSP_HDR0.TGT_ID  = 0x0000   (confirms addressed to THIS BIU)", BLACK, f12),
         ("  frg[1] → RSP_HDR0.CMD     = 4'd9  (UNC_ERR_CMD = uncorrectable error)", BLACK, f12),
         ("           RSP_HDR0.PYLD_LEN= 4'd1  (1 payload fragment follows header)", BLACK, f12),
         ("           RSP_HDR0.CMD_OPT = 0x00", BLACK, f12),
         ("  frg[2] → RSP_HDR1.SRC_ID  = 0x8205   (source node ID)", BLACK, f12),
         ("  frg[3] → RSP_HDR1.DATA1/DATA0 = 0x00", BLACK, f12),
         ("  frg[4] → RSP_DATA[0]      = <error_address>  (payload)", BLACK, f12),
         ("", None, f12),
         ("After last fragment, hardware sets CSR status bits (hwset, combinational):", BLACK, f12),
         ("  csr_status.UNC_ERR.hwset     = 1", ORANGE, f12),
         ("  csr_status.RSP_PKT_RCVD.hwset= 1", ORANGE, f12),
         ("All register values are readable by firmware via APB4.", DGRAY, f11),
     ]},

    # Stage 6
    {"type": "stage",
     "num": "6",
     "hw_sw": "HW",
     "module": "tt_edc1_bus\n_interface_unit",
     "clock": "NOC clock\n(comb. from\nCSR bits)",
     "desc": [
         ("INTERRUPT ASSERTION  (hardware, combinational from CSR)", BLUE, f13),
         ("", None, f12),
         ("BIU asserts output interrupts based on CSR status and IRQ enable bits:", BLACK, f12),
         ("", None, f12),
         ("  crit_err_irq = csr_cfg.IRQ_EN.UNC_ERR_IEN.value", BLACK, f12),
         ("                 && csr_cfg.STAT.UNC_ERR.value", BLACK, f12),
         ("  → o_edc_crit_err_irq[1] = 1  (column X=1's critical error IRQ)", RED, f12),
         ("", None, f12),
         ("  pkt_rcvd_irq = csr_cfg.IRQ_EN.RSP_PKT_RCVD_IEN.value", BLACK, f12),
         ("                 && csr_cfg.STAT.RSP_PKT_RCVD.value", BLACK, f12),
         ("  → o_edc_pkt_rcvd_irq[1] = 1", RED, f12),
         ("", None, f12),
         ("These signals propagate to the SoC interrupt controller, which then", BLACK, f12),
         ("invokes the firmware ISR on the CPU.  Hardware work is done here.", DGRAY, f11),
     ]},

    # Stage 7
    {"type": "stage",
     "num": "7",
     "hw_sw": "SW",
     "module": "tt_edc1_biu\n_soc_apb4_wrap\nBIU[1]\n(X=1 column)",
     "clock": "APB clock\n(= NOC clk)\nFirmware\nISR on CPU",
     "desc": [
         ("FIRMWARE ISR: APB4 READOUT AND DECODE  (software)", BLUE, f13),
         ("", None, f12),
         ("Firmware interrupt handler runs on CPU after crit_err_irq fires:", BLACK, f12),
         ("", None, f12),
         ("Step 1 — Read STAT register:", BLACK, f13),
         ("  APB: PADDR=STAT_OFFSET  →  PRDATA.UNC_ERR=1, PRDATA.RSP_PKT_RCVD=1", BLACK, f12),
         ("  Firmware identifies: uncorrectable error packet received.", ORANGE, f12),
         ("", None, f12),
         ("Step 2 — Read RSP_HDR0:", BLACK, f13),
         ("  PRDATA = {TGT_ID=0x0000, CMD=4'd9, PYLD_LEN=4'd1, CMD_OPT=0x00}", BLACK, f12),
         ("  CMD=9 = UNC_ERR_CMD  (fatal/uncorrectable — must not ignore)", ORANGE, f12),
         ("", None, f12),
         ("Step 3 — Read RSP_HDR1, decode SRC_ID = 0x8205:", BLACK, f13),
         ("  PRDATA.SRC_ID = 0x8205", BLACK, f12),
         ("  Decode:  [15:11] = 5'b10000 = 0x10  →  part = TENSIX_BASE (T0 core)", TEAL, f12),
         ("           [10: 8] = 3'd2              →  subp = Y=2 (cluster row 2)", TEAL, f12),
         ("           [ 7: 0] = 8'h05             →  inst = UNPACK_EDC_IDX", TEAL, f12),
         ("  Ring BIU[1] → column X=1", TEAL, f12),
         ("  ∴ Error source confirmed: Tensix T0 Unpacker at tile (X=1, Y=2)", GREEN, f13),
         ("", None, f12),
         ("Step 4 — Read RSP_DATA[0]:", BLACK, f13),
         ("  PRDATA = {error_address[15:0], ...}  (payload captured at error time)", BLACK, f12),
         ("", None, f12),
         ("Step 5 — Clear STAT (write-1-clear to deassert IRQ):", BLACK, f13),
         ("  APB: PWRITE=1, PWDATA.UNC_ERR=1, PWDATA.RSP_PKT_RCVD=1", BLACK, f12),
         ("  STAT.UNC_ERR cleared → crit_err_irq deasserted → CPU IRQ line released", BLACK, f12),
         ("", None, f12),
         ("Step 6 — Firmware decision:", BLACK, f13),
         ("  Log error: column=1, tile=Y2, core=T0, unit=UNPACK, addr=<captured>", DGRAY, f12),
         ("  If severity warrants: set ISO_EN bit for (X=1,Y=2) to harvest this tile.", DGRAY, f12),
         ("  ISO_EN bit index = x*4 + y = 1*4+2 = 6  (from §11 Harvest Mechanism)", DGRAY, f12),
     ]},
]

# ═══════════════════════════════════════════════════════════════════════════════
# Measure total height
# ═══════════════════════════════════════════════════════════════════════════════
def stage_height(stage):
    if stage["type"] in ("hw_hdr", "sw_hdr"):
        return 30
    n_desc_lines = sum(1 for (txt, _, _) in stage["desc"])
    mod_lines    = len(stage["module"].split("\n"))
    clk_lines    = len(stage["clock"].split("\n"))
    left_lines   = max(mod_lines, clk_lines) + 1
    content_h    = max(n_desc_lines * LINE_H + 4, left_lines * LINE_H + 4)
    return content_h + CELL_PAD * 2 + 4

TITLE_H = 80
total_h = TITLE_H + PAD
for st in STAGES:
    total_h += stage_height(st) + 4

W = TOTAL_W
H = total_h + PAD

img  = Image.new("RGB", (W, H), BG)
d    = ImageDraw.Draw(img)

# ═══════════════════════════════════════════════════════════════════════════════
# Title
# ═══════════════════════════════════════════════════════════════════════════════
d.text((PAD, PAD), "Fig 11  —  Full End-to-End EDC Event Flow  (7 Stages)", font=f17, fill=BLUE)
d.text((PAD, PAD+22),
       "Scenario: T0 Unpacker hardware error at tile (X=1, Y=2) → packet travels ring → BIU → firmware ISR",
       font=f13, fill=DGRAY)
d.text((PAD, PAD+40),
       "Each stage shows: what triggers it, which RTL module, which clock domain, and what happens in detail.",
       font=f12, fill=DGRAY)
d.text((PAD, PAD+56),
       "Blue = HW (runs automatically in silicon)                Yellow = SW (firmware ISR on CPU)",
       font=f12, fill=DGRAY)

# ═══════════════════════════════════════════════════════════════════════════════
# Column positions
# ═══════════════════════════════════════════════════════════════════════════════
# COL_W = [50, 55, 90, 85, 790]   Stage | HW/SW | Module | Clock | Description
col_x = [PAD]
for w in COL_W:
    col_x.append(col_x[-1] + w + 6)
desc_x0 = col_x[4]
desc_x1 = W - PAD

# ═══════════════════════════════════════════════════════════════════════════════
# Draw stages
# ═══════════════════════════════════════════════════════════════════════════════
y = PAD + TITLE_H

for st in STAGES:
    h = stage_height(st)

    if st["type"] == "hw_hdr":
        d.rectangle([PAD, y, W-PAD, y+h-2], fill=HW_HDR)
        d.text((PAD+8, y+6),
               "▼  HARDWARE  (RTL, automatic — no firmware involvement until Stage 7)",
               font=f13, fill=BLUE)
        y += h + 4
        continue

    if st["type"] == "sw_hdr":
        d.rectangle([PAD, y, W-PAD, y+h-2], fill=SW_HDR)
        d.text((PAD+8, y+6),
               "▼  SOFTWARE  (Firmware ISR — runs on CPU after interrupt fires)",
               font=f13, fill=(100, 90, 0))
        y += h + 4
        continue

    # Determine background
    bg = SW_BG if st["hw_sw"] == "SW" else HW_BG

    # Outer box
    d.rectangle([PAD, y, W-PAD, y+h-2], fill=bg, outline=LGRAY, width=1)

    # Stage number
    d.rectangle([col_x[0], y, col_x[1]-1, y+h-2], fill=(220,228,242), outline=LGRAY, width=1)
    d.text((col_x[0]+4, y+CELL_PAD), f"Stage\n  {st['num']}", font=f13, fill=BLUE)

    # HW/SW badge
    hw_sw_col = BLUE if st["hw_sw"]=="HW" else (120, 100, 0)
    hw_sw_bg  = (200,215,240) if st["hw_sw"]=="HW" else (240,235,180)
    d.rectangle([col_x[1], y, col_x[2]-1, y+h-2], fill=hw_sw_bg, outline=LGRAY, width=1)
    d.text((col_x[1]+4, y+CELL_PAD), st["hw_sw"], font=f13, fill=hw_sw_col)

    # Module name
    d.rectangle([col_x[2], y, col_x[3]-1, y+h-2], fill=bg, outline=LGRAY, width=1)
    yt = y + CELL_PAD
    for part in st["module"].split("\n"):
        d.text((col_x[2]+3, yt), part, font=f11, fill=PURPLE)
        yt += 13

    # Clock domain
    d.rectangle([col_x[3], y, col_x[4]-1, y+h-2], fill=bg, outline=LGRAY, width=1)
    yt = y + CELL_PAD
    for part in st["clock"].split("\n"):
        col = RED if "NOC" in part else (TEAL if "AI" in part else
              (ORANGE if "ASYNC" in part else DGRAY))
        d.text((col_x[3]+3, yt), part, font=f11, fill=col)
        yt += 13

    # Description
    d.line([(col_x[4], y), (col_x[4], y+h-2)], fill=LGRAY, width=1)
    yt = y + CELL_PAD
    for (txt, color, fnt) in st["desc"]:
        if txt == "":
            yt += 4
            continue
        d.text((desc_x0 + 4, yt), txt, font=fnt, fill=color)
        yt += LINE_H

    y += h + 4

# Border
d.rectangle([PAD-3, PAD-3, W-PAD+3, H-PAD+3], outline=BLUE, width=2)

img.save(OUT, "PNG")
print(f"[ok] {OUT}  ({W}×{H})")

#!/usr/bin/env python3.11
"""
Render all ASCII diagrams in EDC_HDD_V0.4.md as individual PNG files.
Each diagram is extracted from its ``` code fence, then rendered with
DejaVu Sans Mono for correct Unicode box/arrow character display.
"""

from PIL import Image, ImageDraw, ImageFont
import os, sys

SRC = "/secure_data_from_tt/20260221/DOC/N1B0/EDC_HDD_V0.4.md"
OUT_DIR = "/secure_data_from_tt/edc_diagrams"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Font setup ────────────────────────────────────────────────────────────────
FONT_SIZE = 14   # px — increase for higher resolution
PADDING   = 20   # px around the text
BG_COLOR  = (255, 255, 255)
FG_COLOR  = (20,  20,  20)

FONT_CANDIDATES = [
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
]
font = None
for p in FONT_CANDIDATES:
    if os.path.exists(p):
        font = ImageFont.truetype(p, FONT_SIZE)
        print(f"[font] {p}")
        break
if font is None:
    sys.exit("ERROR: no monospace TTF font found")

# ── Diagram definitions ───────────────────────────────────────────────────────
# Each entry: (output_filename, code_fence_start_line_1indexed, title_for_header)
# The fence_start points to the ``` line (1-indexed).
# We extract everything between that ``` and the next ```.
DIAGRAMS = [
    (
        "01_edc_ring_full_architecture.png",
        105,
        "Fig 1  —  One Column (e.g., X=1): Independent EDC Ring\n"
        "          Full harvest-bypass architecture (all Y=0..4)",
    ),
    (
        "02_edc_ring_y1_harvested.png",
        279,
        "Fig 2  —  Column X=1: sel[Y=1]=1 (HARVESTED), sel[Y=4/3/2/0]=0\n"
        "          Detailed signal path with Y=1 bypassed",
    ),
    (
        "03_module_hierarchy_tree.png",
        2239,
        "Fig 3  —  Module Hierarchy Tree\n"
        "          trinity (top) → EDC ring instantiation per sub-module",
    ),
    (
        "04_harvest_bypass_signal_flow.png",
        2380,
        "Fig 4  —  Harvest Bypass Signal Flow per Tile\n"
        "          DEMUX (NOC side) ↔ MUX (Overlay side)",
    ),
    (
        "05_trinity_grid_layout.png",
        3116,
        "Fig 5  —  Trinity 4×5 Grid Layout\n"
        "          N1B0: NOC2AXI_ROUTER_NE/NW_OPT composite at X=1,2",
    ),
    (
        "06_per_column_ring_flow.png",
        3198,
        "Fig 6  —  Per-Column EDC Ring Flow\n"
        "          Segment A (down) and Segment B (up) signal names",
    ),
    (
        "07_complete_column_ring_diagram.png",
        3253,
        "Fig 7  —  Complete Per-Column Ring Diagram (Column X=0)\n"
        "          All tile port connections, U-turn at Y=0",
    ),
    (
        "08_toggle_handshake_timing.png",
        3992,
        "Fig 8  —  Toggle Handshake Timing (req_tgl / ack_tgl)\n"
        "          4-cycle fragment transfer sequence",
    ),
    (
        "09_packet_serial_transfer.png",
        4002,
        "Fig 9  —  Full Packet Serial Transfer (5 fragments × ~4 cycles)\n"
        "          frg[0]–frg[4] bit-field breakdown",
    ),
    (
        "10_ring_traversal_path.png",
        4018,
        "Fig 10  —  Packet Ring Traversal Path\n"
        "           T0 UNPACK node → connectors → BIU (X=1, Y=2→0→4)",
    ),
    (
        "11_full_path_summary.png",
        4149,
        "Fig 11  —  Full End-to-End Event Path Summary (7 stages)\n"
        "           HW error → node → ring → BIU → IRQ → firmware",
    ),
]

# ── File reader ───────────────────────────────────────────────────────────────
with open(SRC, "r", encoding="utf-8") as f:
    file_lines = f.readlines()   # list of strings, 0-indexed

def extract_fence_block(fence_start_1idx: int) -> list[str]:
    """
    Given the 1-indexed line number of an opening ``` fence,
    return the lines BETWEEN that fence and the next closing ```.
    Strips trailing newline from each line.
    """
    idx = fence_start_1idx - 1          # convert to 0-based
    assert file_lines[idx].strip().startswith("```"), \
        f"Line {fence_start_1idx} is not a fence: {file_lines[idx]!r}"

    result = []
    for i in range(idx + 1, len(file_lines)):
        line = file_lines[i].rstrip("\n")
        if line.strip() == "```":
            break
        result.append(line)
    return result

# ── Renderer ──────────────────────────────────────────────────────────────────
def render_to_png(lines: list[str], title: str, out_path: str) -> None:
    """
    Render a list of text lines (plus an optional header title) to a PNG.
    Uses a fixed-width monospace font; width is determined by the longest line.
    """
    # Prepend title block
    title_lines = []
    for tl in title.split("\n"):
        title_lines.append(tl)
    title_lines.append("─" * max((len(l) for l in lines), default=40))
    all_lines = title_lines + [""] + lines

    # Measure using a scratch image
    scratch = Image.new("RGB", (1, 1))
    dc = ImageDraw.Draw(scratch)

    line_h = FONT_SIZE + 3          # inter-line spacing
    max_w  = 0
    for line in all_lines:
        w = dc.textlength(line, font=font)
        if w > max_w:
            max_w = w

    img_w = int(max_w) + PADDING * 2
    img_h = line_h * len(all_lines) + PADDING * 2

    img  = Image.new("RGB", (img_w, img_h), BG_COLOR)
    draw = ImageDraw.Draw(img)

    y = PADDING
    for i, line in enumerate(all_lines):
        # Title lines get a slightly different colour
        color = (0, 80, 160) if i < len(title_lines) else FG_COLOR
        draw.text((PADDING, y), line, font=font, fill=color)
        y += line_h

    img.save(out_path, "PNG")
    print(f"[ok] {out_path}  ({img_w}×{img_h})")


# ── Main ──────────────────────────────────────────────────────────────────────
for filename, fence_line, title in DIAGRAMS:
    out_path = os.path.join(OUT_DIR, filename)
    try:
        block = extract_fence_block(fence_line)
    except AssertionError as e:
        print(f"[skip] {filename}: {e}")
        continue
    render_to_png(block, title, out_path)

print(f"\nAll diagrams saved to {OUT_DIR}/")

#!/usr/bin/env python3
"""
2년차 계획 다이어그램 직접 생성 (PIL/Pillow 사용)
matplotlib/graphviz 없어도 동작
"""

from PIL import Image, ImageDraw, ImageFont
import os

OUTPUT_DIR = '/secure_data_from_tt/20260221/DOC/N1B0'

def create_color(name):
    """색상 정의"""
    colors = {
        'white': (255, 255, 255),
        'black': (0, 0, 0),
        'red': (255, 107, 107),
        'green': (168, 230, 207),
        'blue': (78, 205, 196),
        'yellow': (255, 230, 109),
        'gray': (200, 200, 200),
        'light_red': (255, 230, 230),
        'light_blue': (230, 243, 255),
        'light_green': (230, 249, 240),
        'light_yellow': (255, 250, 205),
        'dark_red': (180, 30, 30),
        'dark_green': (30, 100, 30),
    }
    return colors.get(name, (255, 255, 255))

def draw_rounded_rect(draw, xy, radius=15, **kwargs):
    """모서리가 둥근 사각형 그리기"""
    x1, y1, x2, y2 = xy
    draw.rectangle([x1+radius, y1, x2-radius, y2], **kwargs)
    draw.rectangle([x1, y1+radius, x2, y2-radius], **kwargs)
    draw.pieslice([x1, y1, x1+radius*2, y1+radius*2], 180, 270, **kwargs)
    draw.pieslice([x2-radius*2, y1, x2, y1+radius*2], 270, 360, **kwargs)
    draw.pieslice([x1, y2-radius*2, x1+radius*2, y2], 90, 180, **kwargs)
    draw.pieslice([x2-radius*2, y2-radius*2, x2, y2], 0, 90, **kwargs)

def draw_text_box(draw, xy, text, font, fill='black', bg=None, padding=10):
    """텍스트가 있는 박스 그리기"""
    x, y = xy
    if bg:
        draw_rounded_rect(draw, [x-padding, y-padding, x+200+padding, y+50+padding],
                         radius=8, fill=bg, outline='black', width=2)
    draw.text((x, y), text, fill=fill, font=font)

def generate_item1_1():
    """Item 1-1: Memory Hierarchy"""
    img = Image.new('RGB', (1400, 800), create_color('white'))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except:
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        text_font = ImageFont.load_default()

    # 제목
    draw.text((700, 20), "Item 1-1: Memory Hierarchy Enhancement", fill='black', font=title_font, anchor='mm')

    # 기존 구조 (Left)
    draw.text((200, 80), "Current Architecture", fill='black', font=header_font)

    # Tensix Core
    draw_rounded_rect(draw, [50, 120, 350, 200], radius=10, fill=create_color('red'), outline='black', width=2)
    draw.text((200, 160), "Tensix Core\nMAC 64×256 + SFPU", fill='white', font=text_font, anchor='mm')

    # L1
    draw_rounded_rect(draw, [50, 240, 350, 310], radius=10, fill=create_color('blue'), outline='black', width=2)
    draw.text((200, 275), "L1 SRAM\n512 KB, 128-bit", fill='black', font=text_font, anchor='mm')
    draw.line([(200, 200), (200, 240)], fill='black', width=2)
    draw.text((220, 220), "4 cycle", fill='red', font=text_font)

    # L2
    draw_rounded_rect(draw, [50, 350, 350, 420], radius=10, fill=create_color('blue'), outline='black', width=2)
    draw.text((200, 385), "L2 Cache\n1 MB", fill='black', font=text_font, anchor='mm')
    draw.line([(200, 310), (200, 350)], fill='black', width=2)

    # DRAM
    draw_rounded_rect(draw, [50, 460, 350, 530], radius=10, fill=create_color('gray'), outline='black', width=2)
    draw.text((200, 495), "DRAM", fill='black', font=text_font, anchor='mm')
    draw.line([(200, 420), (200, 460)], fill='black', width=2)

    # 결과
    draw.text((200, 600), "Bandwidth: 128-bit | Latency: High", fill='red', font=text_font, anchor='mm')

    # 개선 구조 (Right)
    draw.text((1100, 80), "Enhanced Architecture", fill=create_color('dark_green'), font=header_font)

    # Tensix Core Enhanced
    draw_rounded_rect(draw, [900, 120, 1350, 210], radius=10, fill=create_color('green'), outline=create_color('dark_green'), width=2)
    draw.text((1125, 165), "Tensix Core (Enhanced)\nL1i:64KB | L1d:448KB(dual-port) | Scratch:64KB",
             fill=create_color('dark_green'), font=text_font, anchor='mm')

    # L1.5
    draw_rounded_rect(draw, [900, 250, 1350, 320], radius=10, fill=create_color('green'), outline=create_color('dark_green'), width=2)
    draw.text((1125, 285), "L1.5 FIFO Buffer\n128 KB", fill=create_color('dark_green'), font=text_font, anchor='mm')
    draw.line([(1125, 210), (1125, 250)], fill=create_color('dark_green'), width=2)
    draw.text((1150, 230), "3 cycle", fill=create_color('dark_green'), font=text_font, weight='bold')

    # L2
    draw_rounded_rect(draw, [900, 360, 1350, 430], radius=10, fill=create_color('green'), outline=create_color('dark_green'), width=2)
    draw.text((1125, 395), "L2 Cache (2 MB)\nCoherency", fill=create_color('dark_green'), font=text_font, anchor='mm')
    draw.line([(1125, 320), (1125, 360)], fill=create_color('dark_green'), width=2)

    # DRAM
    draw_rounded_rect(draw, [900, 470, 1350, 540], radius=10, fill=create_color('green'), outline=create_color('dark_green'), width=2)
    draw.text((1125, 505), "DRAM (512-bit)\nMulti-channel", fill=create_color('dark_green'), font=text_font, anchor='mm')
    draw.line([(1125, 430), (1125, 470)], fill=create_color('dark_green'), width=2)

    # 결과
    draw.text((1125, 600), "✓ 256-bit BW (2x) | 3-cycle latency\nVision: 25→150 GFLOPS",
             fill=create_color('dark_green'), font=text_font, anchor='mm')

    img.save(os.path.join(OUTPUT_DIR, 'fig_item1-1_memory_hierarchy.png'))
    print("✓ fig_item1-1_memory_hierarchy.png")

def generate_item2_1():
    """Item 2-1: Parallel Attention Unit"""
    img = Image.new('RGB', (1400, 1000), create_color('white'))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except:
        title_font = header_font = text_font = ImageFont.load_default()

    # 제목
    draw.text((700, 30), "Item 2-1: Parallel Attention Unit (PAU)",
             fill='black', font=title_font, anchor='mm')
    draw.text((700, 60), "Attention: 167ms → 32ms", fill='red', font=header_font, anchor='mm')

    # PAU 헤더
    draw_rounded_rect(draw, [100, 100, 1300, 170], radius=10,
                     fill=create_color('red'), outline='black', width=2)
    draw.text((700, 135), "Parallel Attention Unit (4 Independent Tiles)",
             fill='white', font=header_font, anchor='mm')

    # 4개 Attention Tiles
    for i in range(4):
        x = 150 + i * 280
        draw_rounded_rect(draw, [x, 200, x+250, 300], radius=8,
                         fill=create_color('blue'), outline='black', width=2)
        draw.text((x+125, 250), f"Attention Tile {i}\nQ[{i*1024}:{(i+1)*1024}]×K^T",
                 fill='black', font=text_font, anchor='mm')
        # Arrow down
        draw.line([(x+125, 300), (x+125, 330)], fill='black', width=2)

    # Softmax Layer
    draw.text((700, 360), "Softmax Layer (4× Parallel SFPU)",
             fill=create_color('dark_green'), font=header_font, anchor='mm')

    for i in range(4):
        x = 150 + i * 280
        draw_rounded_rect(draw, [x, 390, x+250, 460], radius=8,
                         fill=create_color('yellow'), outline='black', width=2)
        draw.text((x+125, 425), f"SFPU {i}", fill='black', font=header_font, anchor='mm')
        # Arrow down
        draw.line([(x+125, 460), (x+125, 490)], fill='black', width=2)

    # Output
    draw_rounded_rect(draw, [100, 520, 1300, 600], radius=10,
                     fill=create_color('green'), outline=create_color('dark_green'), width=2)
    draw.text((700, 560), "Output: Softmax(Scores) × V (4 tiles merged)",
             fill=create_color('dark_green'), font=header_font, anchor='mm')

    # Latency breakdown
    latency_text = """Latency Breakdown (seq_len=4096):
    QK^T: 37ms | Softmax: 8ms | Output: 37ms
    ────────────────────────────────
    Total: 82ms (vs 167ms = 49% reduction)"""

    draw.text((700, 700), latency_text, fill='black', font=text_font, anchor='mm')

    # Hardware info
    draw.text((150, 850), "Area: ~4-5 mm² | Storage: 1 MB (4 tiles)",
             fill='#444444', font=text_font)
    draw.text((150, 900), "Improvement: Decode latency 100ms→38ms/token",
             fill='green', font=text_font, weight='bold')

    img.save(os.path.join(OUTPUT_DIR, 'fig_item2-1_parallel_attention.png'))
    print("✓ fig_item2-1_parallel_attention.png")

def generate_item2_2():
    """Item 2-2: Sparse Attention Patterns"""
    img = Image.new('RGB', (1400, 550), create_color('white'))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except:
        title_font = header_font = text_font = ImageFont.load_default()

    draw.text((700, 20), "Item 2-2: Sparse Attention Patterns",
             fill='black', font=title_font, anchor='mm')

    # Pattern 1: Causal
    draw.text((200, 80), "Causal Masking", fill='black', font=header_font, anchor='mm')
    cell_size = 20
    for i in range(6):
        for j in range(6):
            x = 100 + j * cell_size
            y = 110 + i * cell_size
            if j <= i:
                draw.rectangle([x, y, x+cell_size, y+cell_size],
                             fill=create_color('blue'), outline='black', width=1)
                draw.text((x+cell_size//2, y+cell_size//2), '1',
                         fill='white', font=text_font, anchor='mm')
            else:
                draw.rectangle([x, y, x+cell_size, y+cell_size],
                             fill=create_color('gray'), outline='black', width=1)

    draw.text((200, 300), "Sparsity: 50%", fill='black', font=text_font, anchor='mm')

    # Pattern 2: Local Window
    draw.text((700, 80), "Local Window", fill='black', font=header_font, anchor='mm')
    for i in range(6):
        for j in range(6):
            x = 600 + j * cell_size
            y = 110 + i * cell_size
            if abs(i - j) <= 1:
                draw.rectangle([x, y, x+cell_size, y+cell_size],
                             fill=create_color('green'), outline='black', width=1)
                draw.text((x+cell_size//2, y+cell_size//2), '1',
                         fill='white', font=text_font, anchor='mm')
            else:
                draw.rectangle([x, y, x+cell_size, y+cell_size],
                             fill=create_color('gray'), outline='black', width=1)

    draw.text((700, 300), "Sparsity: 67%", fill='black', font=text_font, anchor='mm')

    # Pattern 3: Strided
    draw.text((1200, 80), "Strided (stride=3)", fill='black', font=header_font, anchor='mm')
    for i in range(6):
        for j in range(6):
            x = 1100 + j * cell_size
            y = 110 + i * cell_size
            if j % 3 == 0:
                draw.rectangle([x, y, x+cell_size, y+cell_size],
                             fill=create_color('yellow'), outline='black', width=1)
                draw.text((x+cell_size//2, y+cell_size//2), '1',
                         fill='black', font=text_font, anchor='mm')
            else:
                draw.rectangle([x, y, x+cell_size, y+cell_size],
                             fill=create_color('gray'), outline='black', width=1)

    draw.text((1200, 300), "Sparsity: 67%", fill='black', font=text_font, anchor='mm')

    # Benefits
    benefits = "✓ Causal: 50% MACs | Local: 75% | Strided: 67% | Attention: 81M→41M MACs"
    draw.text((700, 450), benefits, fill='green', font=text_font, anchor='mm')

    img.save(os.path.join(OUTPUT_DIR, 'fig_item2-2_sparse_attention.png'))
    print("✓ fig_item2-2_sparse_attention.png")

def generate_item3_1():
    """Item 3-1: Conv Optimization"""
    img = Image.new('RGB', (1400, 700), create_color('white'))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except:
        title_font = header_font = text_font = ImageFont.load_default()

    draw.text((700, 20), "Item 3-1: Convolution Memory Efficiency",
             fill='black', font=title_font, anchor='mm')

    # Traditional Im2Col (Left)
    draw.text((250, 80), "Traditional Im2Col", fill='red', font=header_font, anchor='mm')

    steps_left = [
        ("Input\n224×224×3\n1.2 MB", 100),
        ("Im2Col Expand\n32.4 MB\n(27× bloat)", 180),
        ("GEMM", 260),
        ("Output", 340),
    ]

    for i, (text, y) in enumerate(steps_left):
        draw_rounded_rect(draw, [100, y, 400, y+60], radius=8,
                         fill=create_color('light_red'), outline='red', width=2)
        draw.text((250, y+30), text, fill='black', font=text_font, anchor='mm')
        if i < len(steps_left) - 1:
            draw.line([(250, y+60), (250, y+80)], fill='red', width=2)

    draw.text((250, 480), "Problems: Memory explosion\nLocality: 20%",
             fill='red', font=text_font, anchor='mm')

    # Sliding Window (Right)
    draw.text((1050, 80), "Sliding Window Tiling", fill=create_color('dark_green'), font=header_font, anchor='mm')

    steps_right = [
        ("Input Tile\n16×16×C\n1 KB", 100),
        ("Slide Kernel\nReuse: 9-25×", 180),
        ("Systolic Output", 260),
        ("Write: 2 KB", 340),
    ]

    for i, (text, y) in enumerate(steps_right):
        draw_rounded_rect(draw, [900, y, 1200, y+60], radius=8,
                         fill=create_color('light_green'), outline=create_color('dark_green'), width=2)
        draw.text((1050, y+30), text, fill=create_color('dark_green'), font=text_font, anchor='mm')
        if i < len(steps_right) - 1:
            draw.line([(1050, y+60), (1050, y+80)], fill=create_color('dark_green'), width=2)

    draw.text((1050, 480), "Benefits: 310× reduction\nLocality: 90% | BW: 80%→15%",
             fill=create_color('dark_green'), font=text_font, anchor='mm', weight='bold')

    img.save(os.path.join(OUTPUT_DIR, 'fig_item3-1_conv_optimization.png'))
    print("✓ fig_item3-1_conv_optimization.png")

def generate_item4_1():
    """Item 4-1: DVFS Architecture"""
    img = Image.new('RGB', (1400, 900), create_color('white'))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except:
        title_font = header_font = text_font = ImageFont.load_default()

    draw.text((700, 20), "Item 4-1: Advanced DVFS with Power Gating",
             fill='black', font=title_font, anchor='mm')

    # Analysis Engine
    draw_rounded_rect(draw, [100, 80, 380, 160], radius=10,
                     fill=create_color('light_blue'), outline='black', width=2)
    draw.text((240, 120), "Workload Analysis\nIPC, Memory BW, Thermal",
             fill='black', font=header_font, anchor='mm')

    # Arrow
    draw.line([(380, 120), (420, 120)], fill='black', width=2)

    # DVFS Control
    draw_rounded_rect(draw, [420, 80, 700, 160], radius=10,
                     fill=create_color('light_yellow'), outline='black', width=2)
    draw.text((560, 120), "DVFS Control\n200-1000 MHz\n0.75-1.2V",
             fill='black', font=header_font, anchor='mm')

    # Workload Operating Points
    draw.text((700, 200), "Operating Points per Workload:",
             fill='black', font=header_font, anchor='mm')

    workloads = [
        ("Vision (YOLOv8)\nf=750 MHz, V=1.0V\nP=22W prefill → 2W post\nAvg: 20.6W", 200, create_color('light_red')),
        ("Language (Llama 2)\nf=1000 MHz, V=1.2V (prefill)\nf=600 MHz, V=0.95V (decode)\nAvg: 13.2W", 350, create_color('light_yellow')),
        ("Action (Robot)\nf=400 MHz, V=0.85V\nP=8W\nLatency: 12ms", 500, create_color('light_green')),
    ]

    for i, (text, y, color) in enumerate(workloads):
        x = 150 + (i % 3) * 400
        if i == 0:
            x = 150
            y = 260
        elif i == 1:
            x = 600
            y = 260
        else:
            x = 1050
            y = 260

        draw_rounded_rect(draw, [x, y, x+300, y+100], radius=8,
                         fill=color, outline='black', width=1)
        draw.text((x+150, y+50), text, fill='black', font=text_font, anchor='mm')

    # Power reduction summary
    summary_text = """Power Reduction:
    ✓ Action: 80W → 10W (8× reduction)
    ✓ Language: 50W → 13W (3.8× reduction)
    ✓ Vision: 80W → 21W (3.8× reduction)
    """

    draw.text((700, 700), summary_text, fill='green', font=text_font, anchor='mm')

    img.save(os.path.join(OUTPUT_DIR, 'fig_item4-1_dvfs_architecture.png'))
    print("✓ fig_item4-1_dvfs_architecture.png")

def generate_vla_maturity_roadmap():
    """VLA Maturity Roadmap"""
    img = Image.new('RGB', (1400, 700), create_color('white'))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        title_font = header_font = text_font = ImageFont.load_default()

    draw.text((700, 30), "VLA Maturity Roadmap: Year 1 → Year 2",
             fill='black', font=title_font, anchor='mm')

    # Data
    categories = [
        ("Vision", 6.5, 9.0, 38),
        ("Language", 7.5, 9.2, 23),
        ("Action", 5.0, 9.5, 90),
        ("Overall", 6.3, 9.2, 46),
    ]

    bar_width = 80
    bar_spacing = 100
    start_x = 200

    for idx, (name, baseline, target, improvement) in enumerate(categories):
        x = start_x + idx * (bar_width + bar_spacing)

        # Baseline bar
        baseline_height = int(baseline * 40)
        draw.rectangle([x, 500-baseline_height, x+35, 500],
                      fill=create_color('red'), outline='black', width=1)
        draw.text((x+17.5, 520), f"{baseline:.1f}", fill='black', font=text_font, anchor='mm')

        # Target bar
        target_height = int(target * 40)
        draw.rectangle([x+45, 500-target_height, x+80, 500],
                      fill=create_color('green'), outline='black', width=1)
        draw.text((x+62.5, 520), f"{target:.1f}", fill='black', font=text_font, anchor='mm')

        # Improvement percentage
        draw.text((x+40, 480-target_height-30), f"+{improvement}%",
                 fill='green', font=header_font, anchor='mm', weight='bold')

        # Category name
        draw.text((x+40, 560), name, fill='black', font=header_font, anchor='mm')

    # Legend
    draw.rectangle([150, 100, 170, 120], fill=create_color('red'), outline='black', width=1)
    draw.text((180, 110), "Year 1 End", fill='black', font=text_font, anchor='lm')

    draw.rectangle([150, 130, 170, 150], fill=create_color('green'), outline='black', width=1)
    draw.text((180, 140), "Year 2 End (Target)", fill='black', font=text_font, anchor='lm')

    # Summary
    summary = "2년차 목표: 전체 VLA 성숙도 6.3/10 → 9.2/10 (+46%)"
    draw.text((700, 620), summary, fill='darkgreen', font=header_font, anchor='mm', weight='bold')

    img.save(os.path.join(OUTPUT_DIR, 'fig_vla_maturity_roadmap.png'))
    print("✓ fig_vla_maturity_roadmap.png")

def main():
    """모든 다이어그램 생성"""
    print("Generating 2-Year Plan Diagrams (PIL)...\n")

    try:
        generate_item1_1()
        generate_item2_1()
        generate_item2_2()
        generate_item3_1()
        generate_item4_1()
        generate_vla_maturity_roadmap()

        print("\n" + "="*60)
        print("✅ All diagrams generated successfully!")
        print("="*60)
        print(f"\nLocation: {OUTPUT_DIR}/fig_*.png")

        # List generated files
        import glob
        files = glob.glob(os.path.join(OUTPUT_DIR, 'fig_*.png'))
        print(f"\nGenerated files ({len(files)}):")
        for f in sorted(files):
            size = os.path.getsize(f) / 1024  # KB
            print(f"  ✓ {os.path.basename(f)} ({size:.1f} KB)")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()

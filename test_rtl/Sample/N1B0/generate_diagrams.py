#!/usr/bin/env python3
"""
2년차 계획 다이어그램 PNG 생성 스크립트
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from matplotlib import rcParams

# 한글 폰트 설정
rcParams['font.family'] = 'DejaVu Sans'
rcParams['axes.unicode_minus'] = False

# 색상 팔레트
COLOR_COMPUTE = '#FF6B6B'
COLOR_MEMORY = '#4ECDC4'
COLOR_CONTROL = '#FFE66D'
COLOR_DATA = '#95E1D3'
COLOR_IMPROVE = '#A8E6CF'

def create_memory_hierarchy_comparison():
    """Item 1-1: 메모리 계층 구조 비교"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 8))
    fig.suptitle('Item 1-1: Memory Hierarchy Enhancement\n(기존 vs 개선)',
                 fontsize=14, fontweight='bold')

    # 기존 구조 (Left)
    ax1.set_xlim(0, 10)
    ax1.set_ylim(0, 10)
    ax1.axis('off')
    ax1.text(5, 9.5, 'Current Architecture', ha='center', fontsize=12, fontweight='bold')

    # Tensix Core
    rect1 = FancyBboxPatch((1, 7), 8, 1.5, boxstyle="round,pad=0.1",
                           edgecolor='black', facecolor=COLOR_COMPUTE, linewidth=2)
    ax1.add_patch(rect1)
    ax1.text(5, 7.75, 'Tensix Core (MAC 64×256 + SFPU)', ha='center', fontweight='bold')

    # L1 Cache
    rect2 = FancyBboxPatch((1.5, 5.5), 7, 1, boxstyle="round,pad=0.05",
                           edgecolor='black', facecolor=COLOR_MEMORY, linewidth=2)
    ax1.add_patch(rect2)
    ax1.text(5, 6, 'L1 SRAM (512 KB, 128-bit)', ha='center', fontweight='bold')

    # Arrow & latency
    arrow1 = FancyArrowPatch((5, 7), (5, 6.5), arrowstyle='->', mutation_scale=20, linewidth=2)
    ax1.add_patch(arrow1)
    ax1.text(5.5, 6.75, '4 cycle', fontsize=9, style='italic')

    # L2 Cache
    rect3 = FancyBboxPatch((1.5, 4), 7, 1, boxstyle="round,pad=0.05",
                           edgecolor='black', facecolor=COLOR_DATA, linewidth=2)
    ax1.add_patch(rect3)
    ax1.text(5, 4.5, 'L2 Cache (1 MB shared)', ha='center', fontweight='bold')

    arrow2 = FancyArrowPatch((5, 5.5), (5, 5), arrowstyle='->', mutation_scale=20, linewidth=2)
    ax1.add_patch(arrow2)

    # DRAM
    rect4 = FancyBboxPatch((2, 2.5), 6, 1, boxstyle="round,pad=0.05",
                           edgecolor='black', facecolor='#CCCCCC', linewidth=2)
    ax1.add_patch(rect4)
    ax1.text(5, 3, 'DRAM (Unlimited)', ha='center', fontweight='bold')

    arrow3 = FancyArrowPatch((5, 4), (5, 3.5), arrowstyle='->', mutation_scale=20, linewidth=2)
    ax1.add_patch(arrow3)

    # 성능 수치
    ax1.text(5, 1.5, 'Bandwidth: 128-bit\nLatency: High (10-50 cycles)',
            ha='center', fontsize=9, bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.3))

    # 개선 구조 (Right)
    ax2.set_xlim(0, 10)
    ax2.set_ylim(0, 10)
    ax2.axis('off')
    ax2.text(5, 9.5, 'Enhanced Architecture', ha='center', fontsize=12, fontweight='bold', color='green')

    # Tensix Core Enhanced
    rect5 = FancyBboxPatch((0.5, 7.2), 9, 1.2, boxstyle="round,pad=0.1",
                           edgecolor='green', facecolor=COLOR_IMPROVE, linewidth=2.5)
    ax2.add_patch(rect5)
    ax2.text(5, 8, 'Tensix Core (Enhanced)', ha='center', fontweight='bold')
    ax2.text(5, 7.5, 'L1i (64KB) | L1d (448KB, dual-port 256-bit) | Scratch (64KB)',
            ha='center', fontsize=8)

    # L1.5 FIFO
    rect6 = FancyBboxPatch((1.5, 5.8), 7, 1, boxstyle="round,pad=0.05",
                           edgecolor='green', facecolor=COLOR_IMPROVE, linewidth=2)
    ax2.add_patch(rect6)
    ax2.text(5, 6.3, 'L1.5 FIFO Buffer (128 KB, Vision optimized)', ha='center', fontweight='bold', fontsize=9)

    arrow4 = FancyArrowPatch((5, 7.2), (5, 6.8), arrowstyle='->', mutation_scale=20, linewidth=2.5, color='green')
    ax2.add_patch(arrow4)
    ax2.text(5.5, 7, '3 cycle', fontsize=9, style='italic', color='green', fontweight='bold')

    # L2 Cache (2MB)
    rect7 = FancyBboxPatch((1.5, 4.3), 7, 1, boxstyle="round,pad=0.05",
                           edgecolor='green', facecolor=COLOR_IMPROVE, linewidth=2)
    ax2.add_patch(rect7)
    ax2.text(5, 4.8, 'L2 Cache (2 MB, Coherency)', ha='center', fontweight='bold', fontsize=9)

    arrow5 = FancyArrowPatch((5, 5.8), (5, 5.3), arrowstyle='->', mutation_scale=20, linewidth=2.5, color='green')
    ax2.add_patch(arrow5)

    # DRAM Multi-channel
    rect8 = FancyBboxPatch((1.5, 2.5), 7, 1, boxstyle="round,pad=0.05",
                           edgecolor='green', facecolor=COLOR_IMPROVE, linewidth=2)
    ax2.add_patch(rect8)
    ax2.text(5, 3, 'DRAM (512-bit, Multi-channel)', ha='center', fontweight='bold', fontsize=9)

    arrow6 = FancyArrowPatch((5, 4.3), (5, 3.5), arrowstyle='->', mutation_scale=20, linewidth=2.5, color='green')
    ax2.add_patch(arrow6)

    # 개선 효과
    ax2.text(5, 1.3, '✓ 256-bit BW (2x) | 3-cycle latency (25% faster)\nVision: 25 GFLOPS → 150 GFLOPS',
            ha='center', fontsize=9, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.5))

    plt.tight_layout()
    plt.savefig('/secure_data_from_tt/20260221/DOC/N1B0/fig_item1-1_memory_hierarchy.png', dpi=300, bbox_inches='tight')
    print("✓ Item 1-1 diagram saved")
    plt.close()

def create_parallel_attention_unit():
    """Item 2-1: Parallel Attention Unit"""
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 12)
    ax.axis('off')

    ax.text(7, 11.5, 'Item 2-1: Parallel Attention Unit (PAU)\nAttention Latency: 167 ms → 32 ms',
           ha='center', fontsize=13, fontweight='bold')

    # PAU Title
    rect_pau = FancyBboxPatch((0.5, 9), 13, 1.5, boxstyle="round,pad=0.1",
                             edgecolor='purple', facecolor=COLOR_COMPUTE, linewidth=2.5, alpha=0.8)
    ax.add_patch(rect_pau)
    ax.text(7, 10, 'Parallel Attention Unit (New Independent Block)',
           ha='center', fontsize=11, fontweight='bold', color='white')

    # 4 Attention Tiles
    y_start = 7.5
    for i in range(4):
        x_pos = 1.5 + i * 3
        rect = FancyBboxPatch((x_pos, y_start), 2.5, 1.5, boxstyle="round,pad=0.05",
                             edgecolor='black', facecolor=COLOR_MEMORY, linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x_pos + 1.25, y_start + 1, f'Attention Tile {i}', ha='center', fontweight='bold', fontsize=9)
        ax.text(x_pos + 1.25, y_start + 0.5, f'Q[{i*1024}:{(i+1)*1024}] × K^T',
               ha='center', fontsize=8, style='italic')

    # Softmax Units
    y_softmax = 5.5
    ax.text(7, 6.2, 'Softmax Layer (4× Parallel SFPU)', ha='center', fontsize=10, fontweight='bold')
    for i in range(4):
        x_pos = 1.5 + i * 3
        rect = FancyBboxPatch((x_pos, y_softmax), 2.5, 1, boxstyle="round,pad=0.05",
                             edgecolor='black', facecolor=COLOR_CONTROL, linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x_pos + 1.25, y_softmax + 0.5, f'SFPU {i}', ha='center', fontweight='bold', fontsize=9)

        # Arrow from Attention to Softmax
        arrow = FancyArrowPatch((x_pos + 1.25, y_start), (x_pos + 1.25, y_softmax + 1),
                               arrowstyle='->', mutation_scale=15, linewidth=1.5, color='gray')
        ax.add_patch(arrow)

    # Output Attention
    rect_out = FancyBboxPatch((1.5, 3.5), 11, 1.2, boxstyle="round,pad=0.05",
                             edgecolor='green', facecolor=COLOR_IMPROVE, linewidth=2)
    ax.add_patch(rect_out)
    ax.text(7, 4.2, 'Output: Softmax(Scores) × V (All 4 tiles merged)',
           ha='center', fontweight='bold', fontsize=9, color='darkgreen')

    # Arrow from Softmax to Output
    arrow_out = FancyArrowPatch((7, y_softmax), (7, 4.7), arrowstyle='->', mutation_scale=20,
                               linewidth=2, color='green')
    ax.add_patch(arrow_out)

    # Latency Breakdown
    ax.text(7, 2.7, 'Latency Breakdown (seq_len=4096, d=128):',
           ha='center', fontsize=10, fontweight='bold')

    latency_text = """
    QK^T: 4 parallel → 37 ms
    Softmax (exp, sum, div): 4× SFPU → 8 ms
    Output × V: 4 parallel → 37 ms
    ─────────────────────────
    Total: 82 ms (vs baseline 167 ms = 49% reduction)
    """
    ax.text(7, 1.2, latency_text, ha='center', fontsize=9, family='monospace',
           bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.7))

    # Hardware footprint
    ax.text(0.8, 0.3, 'Area: ~4-5 mm² | Storage: 1 MB (4× tiles)',
           ha='left', fontsize=8, style='italic',
           bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))

    plt.tight_layout()
    plt.savefig('/secure_data_from_tt/20260221/DOC/N1B0/fig_item2-1_parallel_attention.png', dpi=300, bbox_inches='tight')
    print("✓ Item 2-1 diagram saved")
    plt.close()

def create_sparse_attention_patterns():
    """Item 2-2: Sparse Attention 패턴들"""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle('Item 2-2: Sparse Attention Patterns\n(Hardware Acceleration)',
                fontsize=13, fontweight='bold')

    # 패턴 1: Causal Masking
    ax = axes[0]
    ax.set_xlim(-0.5, 6)
    ax.set_ylim(-0.5, 6)
    ax.set_aspect('equal')
    ax.set_title('Causal Masking\n(Language Model)', fontweight='bold')

    # Draw attention matrix (lower triangular)
    for i in range(6):
        for j in range(6):
            if j <= i:
                rect = mpatches.Rectangle((j, 5-i), 1, 1, facecolor=COLOR_MEMORY, edgecolor='black', linewidth=0.5)
                ax.add_patch(rect)
                ax.text(j+0.5, 5.5-i, '1', ha='center', va='center', fontsize=8)
            else:
                rect = mpatches.Rectangle((j, 5-i), 1, 1, facecolor='#EEEEEE', edgecolor='black', linewidth=0.5)
                ax.add_patch(rect)
                ax.text(j+0.5, 5.5-i, '0', ha='center', va='center', fontsize=8, color='gray')

    ax.text(3, -0.3, 'Sparsity: 50% avg', ha='center', fontweight='bold')
    ax.set_xticks([])
    ax.set_yticks([])

    # 패턴 2: Local Window
    ax = axes[1]
    ax.set_xlim(-0.5, 6)
    ax.set_ylim(-0.5, 6)
    ax.set_aspect('equal')
    ax.set_title('Local Window (window=3)\n(Vision Transformer)', fontweight='bold')

    # Draw local window pattern
    for i in range(6):
        for j in range(6):
            if abs(i - j) <= 1:
                rect = mpatches.Rectangle((j, 5-i), 1, 1, facecolor=COLOR_IMPROVE, edgecolor='black', linewidth=0.5)
                ax.add_patch(rect)
                ax.text(j+0.5, 5.5-i, '1', ha='center', va='center', fontsize=8)
            else:
                rect = mpatches.Rectangle((j, 5-i), 1, 1, facecolor='#EEEEEE', edgecolor='black', linewidth=0.5)
                ax.add_patch(rect)

    ax.text(3, -0.3, 'Sparsity: 67% avg', ha='center', fontweight='bold')
    ax.set_xticks([])
    ax.set_yticks([])

    # 패턴 3: Strided Attention
    ax = axes[2]
    ax.set_xlim(-0.5, 6)
    ax.set_ylim(-0.5, 6)
    ax.set_aspect('equal')
    ax.set_title('Strided Attention (stride=3)\n(Long Sequences)', fontweight='bold')

    # Draw strided pattern
    for i in range(6):
        for j in range(6):
            if j % 3 == 0:
                rect = mpatches.Rectangle((j, 5-i), 1, 1, facecolor='#FFE66D', edgecolor='black', linewidth=0.5)
                ax.add_patch(rect)
                ax.text(j+0.5, 5.5-i, '1', ha='center', va='center', fontsize=8)
            else:
                rect = mpatches.Rectangle((j, 5-i), 1, 1, facecolor='#EEEEEE', edgecolor='black', linewidth=0.5)
                ax.add_patch(rect)

    ax.text(3, -0.3, 'Sparsity: 67% avg', ha='center', fontweight='bold')
    ax.set_xticks([])
    ax.set_yticks([])

    plt.tight_layout()
    plt.savefig('/secure_data_from_tt/20260221/DOC/N1B0/fig_item2-2_sparse_attention.png', dpi=300, bbox_inches='tight')
    print("✓ Item 2-2 diagram saved")
    plt.close()

def create_kv_cache_hierarchy():
    """Item 2-3: KV-Cache 계층적 구조"""
    fig, ax = plt.subplots(figsize=(12, 9))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 11)
    ax.axis('off')

    ax.text(6, 10.5, 'Item 2-3: Hierarchical KV-Cache Management\nDecode Latency: 100 ms/token → 25 ms/token',
           ha='center', fontsize=12, fontweight='bold')

    # L1 Cache
    rect_l1 = FancyBboxPatch((0.5, 8), 5, 1.5, boxstyle="round,pad=0.1",
                            edgecolor='red', facecolor=COLOR_COMPUTE, linewidth=2.5, alpha=0.8)
    ax.add_patch(rect_l1)
    ax.text(3, 9.2, 'L1 (On-tile SRAM)', ha='center', fontweight='bold', fontsize=10, color='white')
    ax.text(3, 8.6, '64-256 KB | Recent 512 tokens', ha='center', fontsize=8, color='white')
    ax.text(3, 8.2, 'Hit: 95% | Latency: 1 cycle', ha='center', fontsize=8, color='white', style='italic')

    # L2 Cache
    rect_l2 = FancyBboxPatch((6.5, 8), 5, 1.5, boxstyle="round,pad=0.1",
                            edgecolor='orange', facecolor=COLOR_CONTROL, linewidth=2.5, alpha=0.8)
    ax.add_patch(rect_l2)
    ax.text(9, 9.2, 'L2 (Shared Cache)', ha='center', fontweight='bold', fontsize=10, color='white')
    ax.text(9, 8.6, '512 KB-1 MB | Mid-range tokens', ha='center', fontsize=8, color='white')
    ax.text(9, 8.2, 'Hit: 85% | Latency: 3-4 cycles', ha='center', fontsize=8, color='white', style='italic')

    # Arrow L1→L2
    arrow1 = FancyArrowPatch((5.5, 8.7), (6.5, 8.7), arrowstyle='<->', mutation_scale=20,
                            linewidth=2, color='darkred')
    ax.add_patch(arrow1)

    # DRAM
    rect_dram = FancyBboxPatch((2, 5.5), 8, 1.5, boxstyle="round,pad=0.1",
                              edgecolor='purple', facecolor='#CCCCCC', linewidth=2.5)
    ax.add_patch(rect_dram)
    ax.text(6, 6.7, 'DRAM (Off-chip)', ha='center', fontweight='bold', fontsize=10)
    ax.text(6, 6.1, 'Unlimited | All previous tokens', ha='center', fontsize=8)
    ax.text(6, 5.7, 'Hit: 70% | Latency: 50+ cycles', ha='center', fontsize=8, style='italic')

    # Arrows from L1, L2 to DRAM
    arrow2 = FancyArrowPatch((3, 8), (4, 7), arrowstyle='->', mutation_scale=20,
                            linewidth=1.5, color='gray')
    ax.add_patch(arrow2)

    arrow3 = FancyArrowPatch((9, 8), (8, 7), arrowstyle='->', mutation_scale=20,
                            linewidth=1.5, color='gray')
    ax.add_patch(arrow3)

    # Dynamic allocation rules
    ax.text(6, 4.8, 'Dynamic Allocation Rules:', ha='center', fontsize=10, fontweight='bold')

    allocation_text = """
    seq_len ≤ 512:     L1: 256 KB (full cache fit)  |  L2: 0 KB
    512 < seq_len ≤ 2048:  L1: 128 KB (recent)  |  L2: 768 KB (mid-range)
    seq_len > 2048:    L1: 64 KB (recent)   |  L2: 512 KB  |  DRAM: Spill
    """

    ax.text(6, 2.8, allocation_text, ha='center', fontsize=8, family='monospace',
           bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.7))

    # Performance gain
    ax.text(6, 1.2, '✓ KV-cache efficiency: 28% → 92%  |  Decode: 100 ms → 25 ms',
           ha='center', fontsize=9, fontweight='bold',
           bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.5))

    plt.tight_layout()
    plt.savefig('/secure_data_from_tt/20260221/DOC/N1B0/fig_item2-3_kv_cache_hierarchy.png', dpi=300, bbox_inches='tight')
    print("✓ Item 2-3 diagram saved")
    plt.close()

def create_conv_optimization():
    """Item 3-1: Sliding Window Conv vs Im2Col"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('Item 3-1: Convolution Memory Efficiency\nSpatial Tiling Conv Accelerator (STCA)',
                fontsize=12, fontweight='bold')

    # 기존 Im2Col 방식 (Left)
    ax1.set_xlim(0, 10)
    ax1.set_ylim(0, 10)
    ax1.axis('off')
    ax1.text(5, 9.5, 'Traditional Im2Col', ha='center', fontsize=11, fontweight='bold', color='red')

    steps = [
        ('Input (H×W×C)', 'Input:\n224×224×3\n= 1.2 MB'),
        ('Im2Col Transform', 'Expand:\n32.4 MB\n(27× bloat)'),
        ('GEMM', 'Matrix mult'),
        ('Output (spatial)', 'Output:\nH×W×C_out')
    ]

    for i, (title, detail) in enumerate(steps):
        y_pos = 8 - i * 2
        rect = FancyBboxPatch((1, y_pos-0.6), 8, 1.2, boxstyle="round,pad=0.05",
                             edgecolor='red', facecolor='#FFE6E6', linewidth=1.5)
        ax1.add_patch(rect)
        ax1.text(2.5, y_pos+0.2, title, ha='left', fontweight='bold', fontsize=9)
        ax1.text(7, y_pos+0.2, detail, ha='right', fontsize=8, style='italic')

        if i < len(steps) - 1:
            arrow = FancyArrowPatch((5, y_pos-0.6), (5, y_pos-1.4),
                                   arrowstyle='->', mutation_scale=15, linewidth=1.5, color='red')
            ax1.add_patch(arrow)

    ax1.text(5, 0.5, 'Problems: Memory explosion, Cache thrashing\nLocality: 20% hit rate',
            ha='center', fontsize=8, bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.5))

    # 개선 슬라이딩 윈도우 방식 (Right)
    ax2.set_xlim(0, 10)
    ax2.set_ylim(0, 10)
    ax2.axis('off')
    ax2.text(5, 9.5, 'Sliding Window Tiling', ha='center', fontsize=11, fontweight='bold', color='green')

    steps2 = [
        ('Input Tile (16×16×C)', 'Load:\n16×16 patch\n= 1 KB'),
        ('Slide Kernel', 'Conv in tiles\nK_h×K_w reuse\nFactor: 9-25×'),
        ('Systolic Output', 'Accumulate\noutput tile'),
        ('Write Back', '16×16×C_out\n= 2 KB')
    ]

    for i, (title, detail) in enumerate(steps2):
        y_pos = 8 - i * 2
        rect = FancyBboxPatch((1, y_pos-0.6), 8, 1.2, boxstyle="round,pad=0.05",
                             edgecolor='green', facecolor=COLOR_IMPROVE, linewidth=2)
        ax2.add_patch(rect)
        ax2.text(2.5, y_pos+0.2, title, ha='left', fontweight='bold', fontsize=9, color='darkgreen')
        ax2.text(7, y_pos+0.2, detail, ha='right', fontsize=8, style='italic')

        if i < len(steps2) - 1:
            arrow = FancyArrowPatch((5, y_pos-0.6), (5, y_pos-1.4),
                                   arrowstyle='->', mutation_scale=15, linewidth=2, color='green')
            ax2.add_patch(arrow)

    ax2.text(5, 0.5, 'Benefits: 310× memory reduction (32MB→103KB)\nLocality: 90% hit rate, BW: 80%→15%',
            ha='center', fontsize=8, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.5))

    plt.tight_layout()
    plt.savefig('/secure_data_from_tt/20260221/DOC/N1B0/fig_item3-1_conv_optimization.png', dpi=300, bbox_inches='tight')
    print("✓ Item 3-1 diagram saved")
    plt.close()

def create_dvfs_architecture():
    """Item 4-1: DVFS 아키텍처"""
    fig, ax = plt.subplots(figsize=(13, 9))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 10)
    ax.axis('off')

    ax.text(6.5, 9.7, 'Item 4-1: Advanced DVFS with Power Gating\nPower Reduction: 80W → 10-25W',
           ha='center', fontsize=12, fontweight='bold')

    # Workload Analysis
    rect1 = FancyBboxPatch((0.5, 8), 5.5, 1.3, boxstyle="round,pad=0.1",
                          edgecolor='blue', facecolor='#E6F3FF', linewidth=2)
    ax.add_patch(rect1)
    ax.text(3.25, 8.85, 'Workload Analysis Engine', ha='center', fontweight='bold', fontsize=9)
    ax.text(3.25, 8.4, 'Frequency & Voltage Prediction', ha='center', fontsize=8)

    # DVFS Control
    rect2 = FancyBboxPatch((7, 8), 5.5, 1.3, boxstyle="round,pad=0.1",
                          edgecolor='blue', facecolor='#E6F3FF', linewidth=2)
    ax.add_patch(rect2)
    ax.text(9.75, 8.85, 'Fine-grained DVFS Hardware', ha='center', fontweight='bold', fontsize=9)
    ax.text(9.75, 8.4, 'Clock divider, Voltage controller', ha='center', fontsize=8)

    # Arrow
    arrow = FancyArrowPatch((6, 8.65), (7, 8.65), arrowstyle='->', mutation_scale=20, linewidth=2, color='blue')
    ax.add_patch(arrow)

    # Clock Divider Details
    rect3 = FancyBboxPatch((7.2, 6.2), 5.2, 1.6, boxstyle="round,pad=0.08",
                          edgecolor='purple', facecolor=COLOR_CONTROL, linewidth=1.5, alpha=0.8)
    ax.add_patch(rect3)
    ax.text(9.8, 7.5, 'Clock Divider', ha='center', fontweight='bold', fontsize=9, color='darkred')
    ax.text(9.8, 7.05, 'PLL: 1000 MHz', ha='center', fontsize=8)
    ax.text(9.8, 6.65, 'Dividers: ÷1,2,4,8,16 → 1000, 500, 250, 125, 62.5 MHz',
           ha='center', fontsize=7)

    # Voltage Controller
    rect4 = FancyBboxPatch((0.8, 6.2), 5.8, 1.6, boxstyle="round,pad=0.08",
                          edgecolor='purple', facecolor=COLOR_CONTROL, linewidth=1.5, alpha=0.8)
    ax.add_patch(rect4)
    ax.text(3.7, 7.5, 'Voltage Controller', ha='center', fontweight='bold', fontsize=9, color='darkred')
    ax.text(3.7, 7.05, '0.75V ~ 1.2V (25 mV steps)', ha='center', fontsize=8)
    ax.text(3.7, 6.65, 'Ramp time: 100 µs', ha='center', fontsize=8)

    # Power Model
    rect5 = FancyBboxPatch((3, 4.5), 7, 1.3, boxstyle="round,pad=0.08",
                          edgecolor='green', facecolor=COLOR_IMPROVE, linewidth=2)
    ax.add_patch(rect5)
    ax.text(6.5, 5.5, 'Power Model: P_dynamic = C × V² × f × A',
           ha='center', fontweight='bold', fontsize=9, color='darkgreen')
    ax.text(6.5, 4.95, 'Real-time monitoring & adjustment', ha='center', fontsize=8)

    # Workload-specific operating points
    ax.text(6.5, 4, 'Operating Points per Workload:', ha='center', fontsize=10, fontweight='bold')

    workload_text = """
    Vision (YOLOv8 640×640):     f=750MHz, V=1.0V, P=22W (prefill) → 2W (post-process)  Avg: 20.6W
    Language (Llama 2):          f=1000MHz, V=1.2V, P=28W (prefill) → f=600MHz, V=0.95V, P=12W (decode)  Avg: 13.2W
    Action (Real-time control):  f=400MHz, V=0.85V, P=8W  Latency: 12 ms < 33 ms deadline
    """

    ax.text(6.5, 1.8, workload_text, ha='center', fontsize=7.5, family='monospace',
           bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.7))

    # Power reduction metric
    ax.text(6.5, 0.4, '✓ Action: 80W → 10W (8× reduction)  |  Language: 50W → 13W (3.8× reduction)',
           ha='center', fontsize=9, fontweight='bold',
           bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.5))

    plt.tight_layout()
    plt.savefig('/secure_data_from_tt/20260221/DOC/N1B0/fig_item4-1_dvfs_architecture.png', dpi=300, bbox_inches='tight')
    print("✓ Item 4-1 diagram saved")
    plt.close()

def create_vla_maturity_roadmap():
    """VLA 성숙도 로드맵"""
    fig, ax = plt.subplots(figsize=(14, 7))

    # Data
    categories = ['Vision', 'Language', 'Action', 'Overall']
    baseline = [6.5, 7.5, 5.0, 6.3]
    target = [9.0, 9.2, 9.5, 9.2]

    x = np.arange(len(categories))
    width = 0.35

    bars1 = ax.bar(x - width/2, baseline, width, label='Year 1 End (Baseline)',
                   color='#FF6B6B', alpha=0.8, edgecolor='black', linewidth=1.5)
    bars2 = ax.bar(x + width/2, target, width, label='Year 2 End (Target)',
                   color='#51CF66', alpha=0.8, edgecolor='black', linewidth=1.5)

    # Add value labels
    for bar in bars1:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{height:.1f}', ha='center', va='bottom', fontweight='bold')

    for bar in bars2:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{height:.1f}', ha='center', va='bottom', fontweight='bold')

    # Styling
    ax.set_ylabel('VLA Maturity Score (/10)', fontsize=11, fontweight='bold')
    ax.set_title('N1B0 VLA Capability Maturity Roadmap\n(2-Year Enhancement Plan)',
                fontsize=13, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=11, fontweight='bold')
    ax.set_ylim(0, 10.5)
    ax.legend(fontsize=10, loc='upper left')
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    # Add improvement percentages
    improvements = [
        (0, f'+38%'),
        (1, f'+23%'),
        (2, f'+90%'),
        (3, f'+46%')
    ]

    for x_pos, text in improvements:
        ax.text(x_pos, max(baseline[x_pos], target[x_pos]) + 0.5, text,
               ha='center', fontsize=10, fontweight='bold', color='darkgreen')

    plt.tight_layout()
    plt.savefig('/secure_data_from_tt/20260221/DOC/N1B0/fig_vla_maturity_roadmap.png', dpi=300, bbox_inches='tight')
    print("✓ VLA Maturity Roadmap diagram saved")
    plt.close()

if __name__ == '__main__':
    print("Generating 2-Year Plan Diagrams...")
    create_memory_hierarchy_comparison()
    create_parallel_attention_unit()
    create_sparse_attention_patterns()
    create_kv_cache_hierarchy()
    create_conv_optimization()
    create_dvfs_architecture()
    create_vla_maturity_roadmap()
    print("\n✅ All diagrams generated successfully!")
    print("Saved to: /secure_data_from_tt/20260221/DOC/N1B0/fig_*.png")

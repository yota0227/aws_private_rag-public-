#!/usr/bin/env python3
"""
2년차 계획 다이어그램 SVG 생성
(matplotlib/PIL/graphviz 없어도 동작)
"""

import os

OUTPUT_DIR = '/secure_data_from_tt/20260221/DOC/N1B0'

def save_svg(filename, content):
    """SVG 파일 저장"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✓ {filename}")

def generate_item1_1():
    """Item 1-1: Memory Hierarchy"""
    svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="1400" height="800" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      .title { font-size: 24px; font-weight: bold; }
      .header { font-size: 14px; font-weight: bold; }
      .text { font-size: 11px; }
      .box-red { fill: #FF6B6B; stroke: black; stroke-width: 2; }
      .box-blue { fill: #4ECDC4; stroke: black; stroke-width: 2; }
      .box-green { fill: #A8E6CF; stroke: #228B22; stroke-width: 2; }
      .box-gray { fill: #CCCCCC; stroke: black; stroke-width: 2; }
    </style>
  </defs>

  <text x="700" y="40" text-anchor="middle" class="title">Item 1-1: Memory Hierarchy Enhancement</text>

  <!-- Current Architecture (Left) -->
  <text x="200" y="80" class="header">Current Architecture</text>

  <!-- Tensix Core -->
  <rect x="50" y="120" width="300" height="80" rx="10" class="box-red"/>
  <text x="200" y="165" text-anchor="middle" class="text">Tensix Core</text>
  <text x="200" y="180" text-anchor="middle" class="text">MAC 64×256 + SFPU</text>

  <!-- L1 -->
  <line x1="200" y1="200" x2="200" y2="240" stroke="black" stroke-width="2"/>
  <text x="220" y="220" class="text">4 cycle</text>
  <rect x="50" y="240" width="300" height="70" rx="10" class="box-blue"/>
  <text x="200" y="280" text-anchor="middle" class="text">L1 SRAM (512 KB, 128-bit)</text>

  <!-- L2 -->
  <line x1="200" y1="310" x2="200" y2="350" stroke="black" stroke-width="2"/>
  <rect x="50" y="350" width="300" height="70" rx="10" class="box-blue"/>
  <text x="200" y="390" text-anchor="middle" class="text">L2 Cache (1 MB)</text>

  <!-- DRAM -->
  <line x1="200" y1="420" x2="200" y2="460" stroke="black" stroke-width="2"/>
  <rect x="50" y="460" width="300" height="70" rx="10" class="box-gray"/>
  <text x="200" y="500" text-anchor="middle" class="text">DRAM</text>

  <text x="200" y="600" text-anchor="middle" class="text" fill="red">Bandwidth: 128-bit</text>
  <text x="200" y="620" text-anchor="middle" class="text" fill="red">Latency: High (10-50 cycles)</text>

  <!-- Enhanced Architecture (Right) -->
  <text x="1100" y="80" class="header" fill="#228B22">Enhanced Architecture</text>

  <!-- Tensix Core Enhanced -->
  <rect x="900" y="120" width="450" height="90" rx="10" class="box-green"/>
  <text x="1125" y="155" text-anchor="middle" class="text" fill="#228B22">Tensix Core (Enhanced)</text>
  <text x="1125" y="172" text-anchor="middle" class="text" fill="#228B22">L1i:64KB | L1d:448KB(dual-port 256-bit)</text>
  <text x="1125" y="189" text-anchor="middle" class="text" fill="#228B22">Scratch:64KB</text>

  <!-- L1.5 -->
  <line x1="1125" y1="210" x2="1125" y2="250" stroke="#228B22" stroke-width="3"/>
  <text x="1150" y="230" class="text" fill="#228B22" font-weight="bold">3 cycle</text>
  <rect x="900" y="250" width="450" height="70" rx="10" class="box-green"/>
  <text x="1125" y="295" text-anchor="middle" class="text" fill="#228B22">L1.5 FIFO Buffer (128 KB)</text>

  <!-- L2 -->
  <line x1="1125" y1="320" x2="1125" y2="360" stroke="#228B22" stroke-width="2"/>
  <rect x="900" y="360" width="450" height="70" rx="10" class="box-green"/>
  <text x="1125" y="405" text-anchor="middle" class="text" fill="#228B22">L2 Cache (2 MB, Coherency)</text>

  <!-- DRAM -->
  <line x1="1125" y1="430" x2="1125" y2="470" stroke="#228B22" stroke-width="2"/>
  <rect x="900" y="470" width="450" height="70" rx="10" class="box-green"/>
  <text x="1125" y="515" text-anchor="middle" class="text" fill="#228B22">DRAM (512-bit, Multi-channel)</text>

  <text x="1125" y="600" text-anchor="middle" class="text" fill="green" font-weight="bold">✓ 256-bit BW (2x) | 3-cycle latency</text>
  <text x="1125" y="620" text-anchor="middle" class="text" fill="green" font-weight="bold">Vision: 25→150 GFLOPS</text>
</svg>'''
    save_svg('fig_item1-1_memory_hierarchy.svg', svg)

def generate_item2_1():
    """Item 2-1: Parallel Attention Unit"""
    svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="1400" height="1000" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      .title { font-size: 22px; font-weight: bold; }
      .header { font-size: 13px; font-weight: bold; }
      .text { font-size: 11px; }
      .box { stroke: black; stroke-width: 2; rx: 8; }
      .red { fill: #FF6B6B; }
      .blue { fill: #4ECDC4; }
      .yellow { fill: #FFE66D; }
      .green { fill: #A8E6CF; }
    </style>
  </defs>

  <text x="700" y="30" text-anchor="middle" class="title">Item 2-1: Parallel Attention Unit (PAU)</text>
  <text x="700" y="60" text-anchor="middle" class="header" fill="red">Attention: 167ms → 32ms</text>

  <!-- PAU Header -->
  <rect x="100" y="100" width="1200" height="70" rx="10" class="box red"/>
  <text x="700" y="138" text-anchor="middle" class="header" fill="white">Parallel Attention Unit (4 Independent Tiles)</text>

  <!-- 4 Attention Tiles -->
  <rect x="150" y="200" width="250" height="100" rx="8" class="box blue"/>
  <text x="275" y="240" text-anchor="middle" class="text">Attention Tile 0</text>
  <text x="275" y="255" text-anchor="middle" class="text">Q[0:1024]×K^T</text>

  <rect x="450" y="200" width="250" height="100" rx="8" class="box blue"/>
  <text x="575" y="240" text-anchor="middle" class="text">Attention Tile 1</text>
  <text x="575" y="255" text-anchor="middle" class="text">Q[1024:2048]×K^T</text>

  <rect x="750" y="200" width="250" height="100" rx="8" class="box blue"/>
  <text x="875" y="240" text-anchor="middle" class="text">Attention Tile 2</text>
  <text x="875" y="255" text-anchor="middle" class="text">Q[2048:3072]×K^T</text>

  <rect x="1050" y="200" width="250" height="100" rx="8" class="box blue"/>
  <text x="1175" y="240" text-anchor="middle" class="text">Attention Tile 3</text>
  <text x="1175" y="255" text-anchor="middle" class="text">Q[3072:4096]×K^T</text>

  <!-- Arrows down -->
  <line x1="275" y1="300" x2="275" y2="340" stroke="black" stroke-width="2"/>
  <line x1="575" y1="300" x2="575" y2="340" stroke="black" stroke-width="2"/>
  <line x1="875" y1="300" x2="875" y2="340" stroke="black" stroke-width="2"/>
  <line x1="1175" y1="300" x2="1175" y2="340" stroke="black" stroke-width="2"/>

  <!-- Softmax Layer -->
  <text x="700" y="360" text-anchor="middle" class="header" fill="#228B22">Softmax Layer (4× Parallel SFPU)</text>

  <rect x="150" y="390" width="250" height="70" rx="8" class="box yellow"/>
  <text x="275" y="425" text-anchor="middle" class="header">SFPU 0</text>

  <rect x="450" y="390" width="250" height="70" rx="8" class="box yellow"/>
  <text x="575" y="425" text-anchor="middle" class="header">SFPU 1</text>

  <rect x="750" y="390" width="250" height="70" rx="8" class="box yellow"/>
  <text x="875" y="425" text-anchor="middle" class="header">SFPU 2</text>

  <rect x="1050" y="390" width="250" height="70" rx="8" class="box yellow"/>
  <text x="1175" y="425" text-anchor="middle" class="header">SFPU 3</text>

  <!-- Arrows down -->
  <line x1="275" y1="460" x2="275" y2="490" stroke="black" stroke-width="2"/>
  <line x1="575" y1="460" x2="575" y2="490" stroke="black" stroke-width="2"/>
  <line x1="875" y1="460" x2="875" y2="490" stroke="black" stroke-width="2"/>
  <line x1="1175" y1="460" x2="1175" y2="490" stroke="black" stroke-width="2"/>

  <!-- Output -->
  <rect x="100" y="520" width="1200" height="80" rx="10" class="box green"/>
  <text x="700" y="560" text-anchor="middle" class="header" fill="#228B22">Output: Softmax(Scores) × V (4 tiles merged)</text>

  <!-- Latency Breakdown -->
  <text x="700" y="660" text-anchor="middle" class="header">Latency Breakdown (seq_len=4096):</text>
  <text x="700" y="680" text-anchor="middle" class="text">QK^T: 37ms | Softmax: 8ms | Output: 37ms = 82ms total</text>
  <text x="700" y="700" text-anchor="middle" class="text" fill="green" font-weight="bold">(vs baseline 167ms = 49% reduction)</text>

  <!-- Hardware info -->
  <text x="150" y="800" class="text">Area: ~4-5 mm² | Storage: 1 MB (4 tiles)</text>
  <text x="150" y="850" class="text" fill="green" font-weight="bold">Improvement: Decode 100ms→38ms/token</text>
</svg>'''
    save_svg('fig_item2-1_parallel_attention.svg', svg)

def generate_item2_2():
    """Item 2-2: Sparse Attention Patterns"""
    svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="1400" height="550" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      .title { font-size: 20px; font-weight: bold; }
      .header { font-size: 13px; font-weight: bold; }
      .text { font-size: 11px; }
    </style>
  </defs>

  <text x="700" y="30" text-anchor="middle" class="title">Item 2-2: Sparse Attention Patterns</text>

  <!-- Pattern 1: Causal -->
  <text x="200" y="70" text-anchor="middle" class="header">Causal Masking (Language)</text>

  <!-- 6x6 matrix -->
  <rect x="100" y="90" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="110" y="105" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="120" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="140" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="160" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="180" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="200" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="100" y="110" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="110" y="125" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="120" y="110" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="130" y="125" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="140" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="160" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="180" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="200" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="100" y="130" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="110" y="145" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="120" y="130" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="130" y="145" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="140" y="130" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="150" y="145" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="160" y="130" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="180" y="130" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="200" y="130" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="100" y="150" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="110" y="165" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="120" y="150" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="130" y="165" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="140" y="150" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="150" y="165" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="160" y="150" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="170" y="165" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="180" y="150" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="200" y="150" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="100" y="170" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="110" y="185" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="120" y="170" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="130" y="185" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="140" y="170" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="150" y="185" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="160" y="170" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="170" y="185" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="180" y="170" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="190" y="185" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="200" y="170" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="100" y="190" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="110" y="205" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="120" y="190" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="130" y="205" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="140" y="190" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="150" y="205" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="160" y="190" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="170" y="205" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="180" y="190" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="190" y="205" text-anchor="middle" class="text" fill="white">1</text>
  <rect x="200" y="190" width="20" height="20" fill="#4ECDC4" stroke="black"/><text x="210" y="205" text-anchor="middle" class="text" fill="white">1</text>

  <text x="200" y="260" text-anchor="middle" class="text">Sparsity: 50%</text>

  <!-- Pattern 2: Local Window -->
  <text x="700" y="70" text-anchor="middle" class="header">Local Window (Vision)</text>

  <rect x="600" y="90" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="610" y="105" text-anchor="middle" class="text">1</text>
  <rect x="620" y="90" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="630" y="105" text-anchor="middle" class="text">1</text>
  <rect x="640" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="660" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="680" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="700" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="600" y="110" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="610" y="125" text-anchor="middle" class="text">1</text>
  <rect x="620" y="110" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="630" y="125" text-anchor="middle" class="text">1</text>
  <rect x="640" y="110" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="650" y="125" text-anchor="middle" class="text">1</text>
  <rect x="660" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="680" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="700" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="600" y="130" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="610" y="145" text-anchor="middle" class="text">1</text>
  <rect x="620" y="130" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="630" y="145" text-anchor="middle" class="text">1</text>
  <rect x="640" y="130" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="650" y="145" text-anchor="middle" class="text">1</text>
  <rect x="660" y="130" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="670" y="145" text-anchor="middle" class="text">1</text>
  <rect x="680" y="130" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="700" y="130" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="600" y="150" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="620" y="150" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="630" y="165" text-anchor="middle" class="text">1</text>
  <rect x="640" y="150" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="650" y="165" text-anchor="middle" class="text">1</text>
  <rect x="660" y="150" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="670" y="165" text-anchor="middle" class="text">1</text>
  <rect x="680" y="150" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="690" y="165" text-anchor="middle" class="text">1</text>
  <rect x="700" y="150" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="600" y="170" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="620" y="170" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="640" y="170" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="650" y="185" text-anchor="middle" class="text">1</text>
  <rect x="660" y="170" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="670" y="185" text-anchor="middle" class="text">1</text>
  <rect x="680" y="170" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="690" y="185" text-anchor="middle" class="text">1</text>
  <rect x="700" y="170" width="20" height="20" fill="#A8E6CF" stroke="black"/><text x="710" y="185" text-anchor="middle" class="text">1</text>

  <text x="700" y="260" text-anchor="middle" class="text">Sparsity: 67%</text>

  <!-- Pattern 3: Strided -->
  <text x="1200" y="70" text-anchor="middle" class="header">Strided (stride=3)</text>

  <rect x="1100" y="90" width="20" height="20" fill="#FFE66D" stroke="black"/><text x="1110" y="105" text-anchor="middle" class="text">1</text>
  <rect x="1120" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1140" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1160" y="90" width="20" height="20" fill="#FFE66D" stroke="black"/><text x="1170" y="105" text-anchor="middle" class="text">1</text>
  <rect x="1180" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1200" y="90" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="1100" y="110" width="20" height="20" fill="#FFE66D" stroke="black"/><text x="1110" y="125" text-anchor="middle" class="text">1</text>
  <rect x="1120" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1140" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1160" y="110" width="20" height="20" fill="#FFE66D" stroke="black"/><text x="1170" y="125" text-anchor="middle" class="text">1</text>
  <rect x="1180" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1200" y="110" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="1100" y="130" width="20" height="20" fill="#FFE66D" stroke="black"/><text x="1110" y="145" text-anchor="middle" class="text">1</text>
  <rect x="1120" y="130" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1140" y="130" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1160" y="130" width="20" height="20" fill="#FFE66D" stroke="black"/><text x="1170" y="145" text-anchor="middle" class="text">1</text>
  <rect x="1180" y="130" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1200" y="130" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <rect x="1100" y="150" width="20" height="20" fill="#FFE66D" stroke="black"/><text x="1110" y="165" text-anchor="middle" class="text">1</text>
  <rect x="1120" y="150" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1140" y="150" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1160" y="150" width="20" height="20" fill="#FFE66D" stroke="black"/><text x="1170" y="165" text-anchor="middle" class="text">1</text>
  <rect x="1180" y="150" width="20" height="20" fill="#CCCCCC" stroke="black"/>
  <rect x="1200" y="150" width="20" height="20" fill="#CCCCCC" stroke="black"/>

  <text x="1200" y="260" text-anchor="middle" class="text">Sparsity: 67%</text>

  <!-- Benefits -->
  <text x="700" y="380" text-anchor="middle" class="text" fill="green" font-weight="bold">✓ Causal: 50% MACs reduction | Local: 75% | Strided: 67%</text>
  <text x="700" y="400" text-anchor="middle" class="text" fill="green" font-weight="bold">Attention MACs: 81M → 41M (50% reduction)</text>
</svg>'''
    save_svg('fig_item2-2_sparse_attention.svg', svg)

def generate_item3_1():
    """Item 3-1: Conv Optimization"""
    svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="1400" height="700" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      .title { font-size: 20px; font-weight: bold; }
      .header { font-size: 13px; font-weight: bold; }
      .text { font-size: 11px; }
    </style>
  </defs>

  <text x="700" y="30" text-anchor="middle" class="title">Item 3-1: Convolution Memory Efficiency</text>

  <!-- Traditional Im2Col (Left) -->
  <text x="250" y="80" text-anchor="middle" class="header" fill="red">Traditional Im2Col</text>

  <rect x="100" y="100" width="300" height="60" rx="8" fill="#FFE6E6" stroke="red" stroke-width="2"/>
  <text x="250" y="135" text-anchor="middle" class="text">Input: 224×224×3 = 1.2 MB</text>

  <line x1="250" y1="160" x2="250" y2="180" stroke="red" stroke-width="2"/>
  <rect x="100" y="180" width="300" height="60" rx="8" fill="#FFE6E6" stroke="red" stroke-width="2"/>
  <text x="250" y="210" text-anchor="middle" class="text">Im2Col Expand: 32.4 MB</text>
  <text x="250" y="225" text-anchor="middle" class="text">(27× bloat)</text>

  <line x1="250" y1="240" x2="250" y2="260" stroke="red" stroke-width="2"/>
  <rect x="100" y="260" width="300" height="60" rx="8" fill="#FFE6E6" stroke="red" stroke-width="2"/>
  <text x="250" y="295" text-anchor="middle" class="text">GEMM</text>

  <line x1="250" y1="320" x2="250" y2="340" stroke="red" stroke-width="2"/>
  <rect x="100" y="340" width="300" height="60" rx="8" fill="#FFE6E6" stroke="red" stroke-width="2"/>
  <text x="250" y="375" text-anchor="middle" class="text">Output</text>

  <text x="250" y="480" text-anchor="middle" class="text" fill="red" font-weight="bold">Problems:</text>
  <text x="250" y="500" text-anchor="middle" class="text" fill="red">Memory explosion | Cache thrashing</text>
  <text x="250" y="520" text-anchor="middle" class="text" fill="red">Locality: 20%</text>

  <!-- Sliding Window (Right) -->
  <text x="1050" y="80" text-anchor="middle" class="header" fill="#228B22">Sliding Window Tiling</text>

  <rect x="900" y="100" width="300" height="60" rx="8" fill="#E6F9F0" stroke="#228B22" stroke-width="2"/>
  <text x="1050" y="135" text-anchor="middle" class="text" fill="#228B22">Input Tile: 16×16×C = 1 KB</text>

  <line x1="1050" y1="160" x2="1050" y2="180" stroke="#228B22" stroke-width="2"/>
  <rect x="900" y="180" width="300" height="60" rx="8" fill="#E6F9F0" stroke="#228B22" stroke-width="2"/>
  <text x="1050" y="210" text-anchor="middle" class="text" fill="#228B22">Slide Kernel</text>
  <text x="1050" y="225" text-anchor="middle" class="text" fill="#228B22">Reuse: 9-25×</text>

  <line x1="1050" y1="240" x2="1050" y2="260" stroke="#228B22" stroke-width="2"/>
  <rect x="900" y="260" width="300" height="60" rx="8" fill="#E6F9F0" stroke="#228B22" stroke-width="2"/>
  <text x="1050" y="295" text-anchor="middle" class="text" fill="#228B22">Systolic Output</text>

  <line x1="1050" y1="320" x2="1050" y2="340" stroke="#228B22" stroke-width="2"/>
  <rect x="900" y="340" width="300" height="60" rx="8" fill="#E6F9F0" stroke="#228B22" stroke-width="2"/>
  <text x="1050" y="375" text-anchor="middle" class="text" fill="#228B22">Write: 16×16×C = 2 KB</text>

  <text x="1050" y="480" text-anchor="middle" class="text" fill="#228B22" font-weight="bold">Benefits:</text>
  <text x="1050" y="500" text-anchor="middle" class="text" fill="#228B22">310× memory reduction (32MB→103KB)</text>
  <text x="1050" y="520" text-anchor="middle" class="text" fill="#228B22">Locality: 90% | BW: 80%→15%</text>
</svg>'''
    save_svg('fig_item3-1_conv_optimization.svg', svg)

def generate_item4_1():
    """Item 4-1: DVFS Architecture"""
    svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="1400" height="900" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      .title { font-size: 20px; font-weight: bold; }
      .header { font-size: 12px; font-weight: bold; }
      .text { font-size: 10px; }
    </style>
  </defs>

  <text x="700" y="30" text-anchor="middle" class="title">Item 4-1: Advanced DVFS with Power Gating</text>

  <!-- Analysis Engine -->
  <rect x="100" y="80" width="280" height="80" rx="10" fill="#E6F3FF" stroke="black" stroke-width="2"/>
  <text x="240" y="115" text-anchor="middle" class="header">Workload Analysis</text>
  <text x="240" y="130" text-anchor="middle" class="text">IPC, Memory BW, Thermal</text>

  <!-- Arrow -->
  <line x1="380" y1="120" x2="420" y2="120" stroke="black" stroke-width="2"/>
  <polygon points="420,120 410,115 410,125" fill="black"/>

  <!-- DVFS Control -->
  <rect x="420" y="80" width="280" height="80" rx="10" fill="#FFE6D5" stroke="black" stroke-width="2"/>
  <text x="560" y="115" text-anchor="middle" class="header">DVFS Control</text>
  <text x="560" y="130" text-anchor="middle" class="text">200-1000 MHz | 0.75-1.2V</text>

  <!-- Workload Operating Points -->
  <text x="700" y="200" text-anchor="middle" class="header">Operating Points per Workload:</text>

  <!-- Vision -->
  <rect x="100" y="230" width="350" height="100" rx="8" fill="#FFE6E6" stroke="black" stroke-width="1"/>
  <text x="275" y="250" text-anchor="middle" class="header">Vision (YOLOv8)</text>
  <text x="275" y="268" text-anchor="middle" class="text">f=750 MHz, V=1.0V</text>
  <text x="275" y="283" text-anchor="middle" class="text">P=22W (prefill) → 2W (post-process)</text>
  <text x="275" y="298" text-anchor="middle" class="text" font-weight="bold">Avg: 20.6W</text>

  <!-- Language -->
  <rect x="525" y="230" width="350" height="100" rx="8" fill="#FFFFE6" stroke="black" stroke-width="1"/>
  <text x="700" y="250" text-anchor="middle" class="header">Language (Llama 2)</text>
  <text x="700" y="268" text-anchor="middle" class="text">f=1000 MHz, V=1.2V (prefill)</text>
  <text x="700" y="283" text-anchor="middle" class="text">f=600 MHz, V=0.95V (decode)</text>
  <text x="700" y="298" text-anchor="middle" class="text" font-weight="bold">Avg: 13.2W</text>

  <!-- Action -->
  <rect x="950" y="230" width="350" height="100" rx="8" fill="#E6F9E6" stroke="black" stroke-width="1"/>
  <text x="1125" y="250" text-anchor="middle" class="header">Action (Robot Control)</text>
  <text x="1125" y="268" text-anchor="middle" class="text">f=400 MHz, V=0.85V</text>
  <text x="1125" y="283" text-anchor="middle" class="text">P=8W | Latency: 12ms</text>
  <text x="1125" y="298" text-anchor="middle" class="text" font-weight="bold">Deadline: 33ms ✓</text>

  <!-- Power Reduction Summary -->
  <rect x="150" y="400" width="1100" height="120" rx="10" fill="#E6F9E6" stroke="#228B22" stroke-width="2"/>
  <text x="700" y="430" text-anchor="middle" class="header" fill="#228B22" font-weight="bold">Power Reduction Results:</text>
  <text x="700" y="455" text-anchor="middle" class="text" fill="#228B22" font-weight="bold">✓ Action: 80W → 10W (8× reduction)</text>
  <text x="700" y="475" text-anchor="middle" class="text" fill="#228B22" font-weight="bold">✓ Language: 50W → 13W (3.8× reduction)</text>
  <text x="700" y="495" text-anchor="middle" class="text" fill="#228B22" font-weight="bold">✓ Vision: 80W → 21W (3.8× reduction)</text>

  <!-- Key formula -->
  <text x="700" y="600" text-anchor="middle" class="header">P_dynamic = C × V² × f × A</text>
  <text x="700" y="625" text-anchor="middle" class="text">동적 전력 감소로 실시간 처리 및 배터리 수명 확대</text>
</svg>'''
    save_svg('fig_item4-1_dvfs_architecture.svg', svg)

def generate_vla_maturity_roadmap():
    """VLA Maturity Roadmap"""
    svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="1400" height="700" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      .title { font-size: 22px; font-weight: bold; }
      .header { font-size: 14px; font-weight: bold; }
      .text { font-size: 12px; }
    </style>
  </defs>

  <text x="700" y="40" text-anchor="middle" class="title">VLA Maturity Roadmap: Year 1 → Year 2</text>

  <!-- Legend -->
  <rect x="150" y="80" width="20" height="20" fill="#FF6B6B" stroke="black" stroke-width="1"/>
  <text x="180" y="95" class="text">Year 1 End (Baseline)</text>

  <rect x="150" y="110" width="20" height="20" fill="#A8E6CF" stroke="black" stroke-width="1"/>
  <text x="180" y="125" class="text">Year 2 End (Target)</text>

  <!-- Bar chart -->
  <!-- Vision -->
  <text x="200" y="200" text-anchor="middle" class="header">Vision</text>
  <rect x="150" y="220" width="40" height="260" fill="#FF6B6B" stroke="black" stroke-width="1"/>
  <text x="170" y="495" text-anchor="middle" class="text" font-weight="bold">6.5/10</text>

  <rect x="200" y="40" width="40" height="440" fill="#A8E6CF" stroke="black" stroke-width="1"/>
  <text x="220" y="495" text-anchor="middle" class="text" font-weight="bold">9.0/10</text>
  <text x="220" y="20" text-anchor="middle" class="text" fill="green" font-weight="bold">+38%</text>

  <!-- Language -->
  <text x="450" y="200" text-anchor="middle" class="header">Language</text>
  <rect x="400" y="180" width="40" height="300" fill="#FF6B6B" stroke="black" stroke-width="1"/>
  <text x="420" y="495" text-anchor="middle" class="text" font-weight="bold">7.5/10</text>

  <rect x="450" y="32" width="40" height="448" fill="#A8E6CF" stroke="black" stroke-width="1"/>
  <text x="470" y="495" text-anchor="middle" class="text" font-weight="bold">9.2/10</text>
  <text x="470" y="15" text-anchor="middle" class="text" fill="green" font-weight="bold">+23%</text>

  <!-- Action -->
  <text x="700" y="200" text-anchor="middle" class="header">Action</text>
  <rect x="650" y="300" width="40" height="200" fill="#FF6B6B" stroke="black" stroke-width="1"/>
  <text x="670" y="495" text-anchor="middle" class="text" font-weight="bold">5.0/10</text>

  <rect x="700" y="20" width="40" height="480" fill="#A8E6CF" stroke="black" stroke-width="1"/>
  <text x="720" y="495" text-anchor="middle" class="text" font-weight="bold">9.5/10</text>
  <text x="720" y="0" text-anchor="middle" class="text" fill="green" font-weight="bold">+90%</text>

  <!-- Overall -->
  <text x="1000" y="200" text-anchor="middle" class="header">Overall VLA</text>
  <rect x="950" y="148" width="40" height="252" fill="#FF6B6B" stroke="black" stroke-width="1"/>
  <text x="970" y="495" text-anchor="middle" class="text" font-weight="bold">6.3/10</text>

  <rect x="1000" y="32" width="40" height="448" fill="#A8E6CF" stroke="black" stroke-width="1"/>
  <text x="1020" y="495" text-anchor="middle" class="text" font-weight="bold">9.2/10</text>
  <text x="1020" y="15" text-anchor="middle" class="text" fill="green" font-weight="bold">+46%</text>

  <!-- Y-axis scale -->
  <line x1="120" y1="520" x2="120" y2="20" stroke="black" stroke-width="1"/>
  <text x="100" y="525" text-anchor="middle" class="text">0</text>
  <text x="100" y="275" text-anchor="middle" class="text">5</text>
  <text x="100" y="25" text-anchor="middle" class="text">10</text>

  <!-- Summary -->
  <rect x="150" y="570" width="1100" height="80" rx="10" fill="#E6F9E6" stroke="#228B22" stroke-width="2"/>
  <text x="700" y="595" text-anchor="middle" class="header" fill="#228B22">2년차 목표: 전체 VLA 성숙도 6.3/10 → 9.2/10 (+46% 향상)</text>
  <text x="700" y="620" text-anchor="middle" class="text" fill="#228B22">Memory (+40%) | Transformer (+25%) | Vision (+35%) | Power (+60%)</text>
</svg>'''
    save_svg('fig_vla_maturity_roadmap.svg', svg)

def main():
    """모든 다이어그램 생성"""
    print("Generating 2-Year Plan Diagrams (SVG Format)...\n")

    try:
        generate_item1_1()
        generate_item2_1()
        generate_item2_2()
        generate_item3_1()
        generate_item4_1()
        generate_vla_maturity_roadmap()

        print("\n" + "="*60)
        print("✅ All SVG diagrams generated successfully!")
        print("="*60)

        # List files
        import glob
        files = glob.glob(os.path.join(OUTPUT_DIR, 'fig_*.svg'))
        print(f"\nGenerated {len(files)} SVG files:")
        for f in sorted(files):
            size = os.path.getsize(f) / 1024  # KB
            print(f"  ✓ {os.path.basename(f)} ({size:.1f} KB)")

        print("\n" + "="*60)
        print("📝 PNG 변환 방법:")
        print("="*60)
        print("\n방법 1: ImageMagick 사용")
        print("  convert fig_item1-1_memory_hierarchy.svg fig_item1-1_memory_hierarchy.png\n")

        print("방법 2: Inkscape 사용")
        print("  inkscape --export-png=fig_item1-1_memory_hierarchy.png fig_item1-1_memory_hierarchy.svg\n")

        print("방법 3: 온라인 변환기")
        print("  https://cloudconvert.com/ (SVG → PNG)")
        print("  https://convertio.co/ (SVG → PNG)\n")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()

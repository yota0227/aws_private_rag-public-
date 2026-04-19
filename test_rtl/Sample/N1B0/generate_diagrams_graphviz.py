#!/usr/bin/env python3
"""
2년차 계획 다이어그램 PNG 생성 스크립트 (Graphviz/DOT 사용)
matplotlib이 필요 없음
"""

import subprocess
import os

# DOT 코드로 다이어그램 정의
diagrams = {
    'fig_item1-1_memory_hierarchy': '''
digraph {
    rankdir=LR;
    node [shape=box, style="filled,rounded", fontname="Arial", fontsize=10];
    edge [fontname="Arial", fontsize=9];

    subgraph cluster_current {
        label = "Current Architecture";
        style = "rounded,filled";
        fillcolor = "#FFE6E6";

        c1 [label="Tensix Core\\nMAC 64×256 + SFPU", fillcolor="#FF6B6B", fontcolor="white"];
        c2 [label="L1 SRAM\\n512 KB\\n128-bit", fillcolor="#4ECDC4"];
        c3 [label="L2 Cache\\n1 MB", fillcolor="#95E1D3"];
        c4 [label="DRAM", fillcolor="#CCCCCC"];

        c1 -> c2 [label="4 cycle"];
        c2 -> c3;
        c3 -> c4;
    }

    subgraph cluster_enhanced {
        label = "Enhanced Architecture";
        style = "rounded,filled";
        fillcolor = "#E6F9F0";

        e1 [label="Tensix Core (Enhanced)\\nL1i:64KB | L1d:448KB(dual-port 256-bit) | Scratch:64KB", fillcolor="#A8E6CF", fontcolor="darkgreen"];
        e2 [label="L1.5 FIFO\\n128 KB", fillcolor="#A8E6CF"];
        e3 [label="L2 Cache\\n2 MB\\nCoherency", fillcolor="#A8E6CF"];
        e4 [label="DRAM\\n512-bit\\nMulti-channel", fillcolor="#A8E6CF"];

        e1 -> e2 [label="3 cycle", color="green"];
        e2 -> e3 [color="green"];
        e3 -> e4 [color="green"];
    }

    end [label="✓ Vision: 25→150 GFLOPS\\n✓ Language: 100→45 ms/token\\n✓ Action: 40→8-12 ms", shape="plaintext"];
}
''',

    'fig_item2-1_parallel_attention': '''
digraph {
    rankdir=TB;
    node [shape=box, style="filled,rounded", fontname="Arial", fontsize=9];
    edge [fontname="Arial", fontsize=8];

    title [shape=plaintext, label="Parallel Attention Unit (PAU)\\nAttention: 167ms → 32ms"];

    subgraph cluster_attention {
        label = "Attention Tiles (4× Parallel)";
        style = "filled";
        fillcolor = "#FFE6E6";

        a0 [label="Tile 0\\nQ[0:1024]×K^T", fillcolor="#FF6B6B"];
        a1 [label="Tile 1\\nQ[1024:2048]×K^T", fillcolor="#FF6B6B"];
        a2 [label="Tile 2\\nQ[2048:3072]×K^T", fillcolor="#FF6B6B"];
        a3 [label="Tile 3\\nQ[3072:4096]×K^T", fillcolor="#FF6B6B"];
    }

    subgraph cluster_softmax {
        label = "Softmax Layer (4× SFPU)";
        style = "filled";
        fillcolor = "#FFE6D5";

        s0 [label="SFPU 0", fillcolor="#FFD700"];
        s1 [label="SFPU 1", fillcolor="#FFD700"];
        s2 [label="SFPU 2", fillcolor="#FFD700"];
        s3 [label="SFPU 3", fillcolor="#FFD700"];
    }

    output [label="Output: Softmax×V\\n(4 parallel merged)", fillcolor="#A8E6CF"];
    result [shape=plaintext, label="Latency: 37ms + 8ms + 37ms = 82ms"];

    a0 -> s0; a1 -> s1; a2 -> s2; a3 -> s3;
    s0 -> output; s1 -> output; s2 -> output; s3 -> output;
    output -> result;
}
''',

    'fig_item3-1_conv_optimization': '''
digraph {
    rankdir=LR;
    node [shape=box, style="filled,rounded", fontname="Arial", fontsize=10];
    edge [fontname="Arial", fontsize=9];

    subgraph cluster_imcol {
        label = "Traditional Im2Col";
        style = "filled";
        fillcolor = "#FFE6E6";

        input1 [label="Input\\n224×224×3\\n1.2 MB", fillcolor="#FF6B6B"];
        imcol [label="Im2Col Expand\\n32.4 MB\\n(27× bloat)", fillcolor="#FF6B6B", fontcolor="white"];
        gemm1 [label="GEMM", fillcolor="#FF8787"];
        out1 [label="Output", fillcolor="#FFB3B3"];
        prob [shape=plaintext, label="Problems:\\nMemory explosion\\nCache thrashing\\nLocality: 20%"];

        input1 -> imcol -> gemm1 -> out1;
        out1 -> prob;
    }

    subgraph cluster_sliding {
        label = "Sliding Window Tiling";
        style = "filled";
        fillcolor = "#E6F9F0";

        input2 [label="Input Tile\\n16×16×C\\n1 KB", fillcolor="#A8E6CF"];
        slide [label="Slide Kernel\\nReuse: 9-25×", fillcolor="#A8E6CF", fontcolor="darkgreen"];
        gemm2 [label="Systolic Output", fillcolor="#A8E6CF"];
        out2 [label="Write: 16×16×C\\n2 KB", fillcolor="#A8E6CF"];
        benefit [shape=plaintext, label="Benefits:\\n310× memory reduction\\nLocality: 90%"];

        input2 -> slide -> gemm2 -> out2;
        out2 -> benefit;
    }
}
''',

    'fig_item4-1_dvfs_control': '''
digraph {
    rankdir=TB;
    node [shape=box, style="filled,rounded", fontname="Arial", fontsize=9];
    edge [fontname="Arial", fontsize=8];

    analysis [label="Workload Analysis\\n(IPC, Memory BW, Thermal)", fillcolor="#E6F3FF"];
    control [label="DVFS Control\\n(200-1000 MHz, 0.75-1.2V)", fillcolor="#FFE6D5"];

    vision [label="Vision\\nf=750MHz, V=1.0V\\nP=22W", fillcolor="#FFCCCC"];
    language [label="Language\\nf=1000MHz, V=1.2V\\nP=28W (prefill)\\nf=600MHz, V=0.95V\\nP=12W (decode)", fillcolor="#FFFFCC"];
    action [label="Action\\nf=400MHz, V=0.85V\\nP=8W", fillcolor="#CCFFCC"];

    perf [shape=plaintext, label="Power Reduction:\\nAction: 80W → 10W (8×)\\nLanguage: 50W → 13W (3.8×)"];

    analysis -> control;
    control -> vision;
    control -> language;
    control -> action;
    action -> perf;
}
''',

    'fig_vla_maturity_comparison': '''
digraph {
    rankdir=LR;
    node [shape=box, style="filled,rounded", fontname="Arial", fontsize=10];

    v1 [label="Vision\\n6.5/10\\n(Year 1)", fillcolor="#FF6B6B", fontcolor="white"];
    v2 [label="Vision\\n9.0/10\\n(Year 2)\\n+38%", fillcolor="#A8E6CF"];

    l1 [label="Language\\n7.5/10\\n(Year 1)", fillcolor="#FFD700"];
    l2 [label="Language\\n9.2/10\\n(Year 2)\\n+23%", fillcolor="#A8E6CF"];

    a1 [label="Action\\n5.0/10\\n(Year 1)", fillcolor="#FF9999", fontcolor="white"];
    a2 [label="Action\\n9.5/10\\n(Year 2)\\n+90%", fillcolor="#A8E6CF"];

    o1 [label="Overall\\n6.3/10\\n(Year 1)", fillcolor="#FFB3B3", fontcolor="white"];
    o2 [label="Overall\\n9.2/10\\n(Year 2)\\n+46%", fillcolor="#A8E6CF"];

    v1 -> v2 [label="Items 3-1,2,3"];
    l1 -> l2 [label="Items 2-1,2,3"];
    a1 -> a2 [label="Items 4-1,2,3"];
    o1 -> o2;
}
'''
}

def generate_png_from_dot(name, dot_code):
    """Generate PNG from DOT code using Graphviz"""
    try:
        output_file = f'/secure_data_from_tt/20260221/DOC/N1B0/{name}.png'

        # Write DOT file
        dot_file = f'/tmp/{name}.dot'
        with open(dot_file, 'w') as f:
            f.write(dot_code)

        # Convert to PNG using dot command
        result = subprocess.run(
            ['dot', '-Tpng', '-o', output_file, dot_file],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            print(f"✓ {name}.png generated")
            return True
        else:
            print(f"✗ {name}: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ {name}: {str(e)}")
        return False

def generate_all_diagrams():
    """Generate all diagrams"""
    print("Generating 2-Year Plan Diagrams using Graphviz...")

    success_count = 0
    for name, dot_code in diagrams.items():
        if generate_png_from_dot(name, dot_code):
            success_count += 1

    print(f"\n{'='*50}")
    print(f"Generated {success_count}/{len(diagrams)} diagrams")

    if success_count < len(diagrams):
        print("\nNote: Some diagrams may have failed due to missing Graphviz.")
        print("Install with: apt-get install graphviz (Ubuntu/Debian)")
        print("             brew install graphviz (macOS)")
        print("             choco install graphviz (Windows)")

if __name__ == '__main__':
    generate_all_diagrams()

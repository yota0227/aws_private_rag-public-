# AI 이미지 생성용 프롬프트 모음

ChatGPT (GPT-4o), Midjourney, 또는 기타 AI 이미지 생성 서비스에 붙여넣어 사용.

---

## 1. NPU 칩 전체 블록 다이어그램

```
Create a professional semiconductor chip block diagram for "Trinity N1B0 NPU" with the following specifications:

Layout: 4 columns x 5 rows grid (20 tiles total), clean engineering diagram style like a datasheet figure.

Tile placement (row by row, bottom to top):
- Row 0 (bottom): 4x TENSIX compute tiles (blue), labeled EP=0,5,10,15
- Row 1: 4x TENSIX compute tiles (blue), labeled EP=1,6,11,16
- Row 2: 4x TENSIX compute tiles (blue), labeled EP=2,7,12,17
- Row 3: DISPATCH_E (green, left), ROUTER (gray), ROUTER (gray), DISPATCH_W (green, right)
- Row 4 (top): NOC2AXI_NE (gold, corner), NOC2AXI+Router_NE (orange, composite), NOC2AXI+Router_NW (orange, composite), NOC2AXI_NW (gold, corner)

Interconnect:
- All tiles connected by a 2D mesh NoC (thin gold dashed lines between adjacent tiles, both horizontal and vertical)
- EDC ring shown as a red dashed line running around the perimeter in a U-shape
- Green arrows showing dispatch feedthrough from row 3 down through tensix columns

Each TENSIX tile should show internal sub-blocks: FPU, SFPU, TDMA, L1 Cache (small text inside)

Side panels:
- Left side: Clock inputs (i_noc_clk, i_ai_clk[3:0], i_dm_clk[3:0])
- Right side: Key parameters table (SizeX=4, SizeY=5, NumTensix=12, etc.)
- Top: AXI bus interface arrows going to/from NIU tiles
- Bottom: Legend with color coding

Style: Clean, professional, white background, similar to ARM or Intel datasheet block diagrams. No 3D effects. Use pastel colors for tile types. Monospace font for signal names.
```

---

## 2. Tensix 컴퓨트 타일 내부 구조

```
Create a detailed block diagram of a single "Tensix Compute Tile" for an NPU chip:

Main blocks inside the tile (arranged logically):
- FPU (Floating Point Unit): contains tt_fp_max_array, tt_dual_align
- SFPU (Sparse FPU): contains tt_sfpu_lregs (register file), hazard detection
- TDMA (Tensor DMA): contains XY address controller, thread context, RTS/RTR pipeline
- L1 Cache: multi-bank, with ECC protection, round-robin arbiter
- Instruction Engine: BRISC/TRISC RISC-V cores, JTAG interface
- DEST/SRCB register files

Interfaces (ports on tile boundary):
- North/South/East/West: NoC flit ports (noc_req_t, noc_resp_t)
- Clock: i_ai_clk (AI domain)
- Reset: i_tensix_reset_n
- EDC: serial_in / serial_out (ring connection)
- Dispatch: de_to_t6 input, t6_to_de output

Style: Professional IC design block diagram, clean lines, hierarchical nesting, signal names in monospace. White background, blue/cyan color scheme.
```

---

## 3. NoC 라우팅 토폴로지

```
Create a Network-on-Chip (NoC) routing diagram for a 4x5 mesh:

Grid: 4 columns x 5 rows of router nodes
- Each node is a small square with its endpoint ID (EP=0 to EP=19)
- Nodes connected by bidirectional links (horizontal and vertical)
- Show cardinal directions: N, S, E, W on each link

Highlight:
- 3 routing algorithms shown in a comparison box: DIM_ORDER (XY), TENDRIL (adaptive), DYNAMIC
- Inter-column repeaters shown as small red diamonds between columns at row Y=3 and Y=4
- Virtual channel buffers shown as small rectangles on each link
- SECDED ECC block on each link (116-bit data, 10-bit check)

Flit structure detail (inset box):
- Header: x_dest, y_dest, endpoint_id, flit_type, dynamic_carried_list
- Payload: data bits
- Tail: ECC

Color coding:
- TENSIX nodes: light blue
- NIU nodes: gold
- DISPATCH nodes: green
- ROUTER nodes: gray
- Repeaters: red

Style: Technical diagram suitable for a hardware design document. Clean, precise, with signal bit-widths annotated.
```

---

## 4. EDC 링 토폴로지

```
Create a diagram showing the EDC (Error Detection and Correction) ring topology:

Structure: U-shape ring connecting all tiles in a 4x5 grid
- Segment A: starts at top-left, goes DOWN through column 0, then RIGHT across bottom
- U-turn: at bottom-right corner
- Segment B: goes UP through column 3, then LEFT across top back to start

Each node on the ring:
- Normal node: small circle (pink), labeled "Node N"
- Harvested/bypassed node: dashed circle (red), with bypass arrow going around it

Key elements:
- Serial bus signals between nodes: req_tgl, ack_tgl, data[15:0], data_p
- APB4 host connection at the top (tt_edc1_biu_soc_apb4_wrap)
- 5 IRQ outputs: fatal, critical, correctable, pkt_sent, pkt_rcvd
- Harvest bypass mux/demux shown at bypassed nodes

Protocol detail (inset):
- Toggle-handshake timing diagram (req_tgl toggles, ack_tgl follows)
- 16-bit data + parity per transfer

Style: Clean technical diagram, red/pink color scheme for EDC, with clear directional arrows showing data flow direction.
```

---

## 5. 클럭 분배 구조

```
Create a clock distribution architecture diagram for Trinity N1B0 NPU:

Clock domains (4 independent domains):
1. AXI domain: i_axi_clk (1-bit, global) - gold
2. NoC domain: i_noc_clk (1-bit, global) - orange
3. AI domain: i_ai_clk[3:0] (per-column, 4 independent clocks) - blue
4. DM domain: i_dm_clk[3:0] (per-column, 4 independent clocks) - green

Distribution mechanism:
- Show a 4x5 grid of tiles
- Each tile receives clock via "trinity_clock_routing_t" struct (8 fields)
- clock_routing_in[4][5] feeds into each tile
- clock_routing_out[4][5] comes out of each tile
- Show the struct fields: ai_clk, noc_clk, dm_clk, ai_clk_reset_n, noc_clk_reset_n, dm_uncore_clk_reset_n, tensix_reset_n, power_good

Clock infrastructure modules:
- tt_clkbuf (buffer) at each distribution point
- tt_clkgater (gating) for power management
- tt_smn_clkdiv (divider) generating sub-domains from noc_clk

CDC crossings:
- Show apb_cdc between NoC and AXI domains
- Show tt_async_fifo between different clock domains
- Mark CDC boundaries with zigzag lines

Style: Professional clock tree diagram, color-coded by domain, with clear hierarchy from source to leaf.
```

---

## 6. RAG 파이프라인 (시스템 아키텍처)

```
Create a system architecture diagram for an RTL-to-HDD RAG pipeline:

Data flow (left to right):
1. RTL Sources (9,465 .sv files) - shown as a file stack icon
2. 8 Parsers (shown as a processing block with 8 sub-blocks):
   - Basic Module Parser
   - Package Parser (localparam/enum/struct/function)
   - Port Classifier (9 categories)
   - Generate Block Parser (topology detection)
   - Always Block Parser (clock domain extraction)
   - Wire Declaration Parser (array/struct analysis)
   - Bitwidth Evaluator (expression to integer)
   - Large Module Chunker (50+ ports to 3 sub-records)
3. Knowledge Base (3 stores shown as cylinders):
   - OpenSearch Serverless (vector index, 1024-dim)
   - Neptune Graph DB (relationships)
   - Claim DB (DynamoDB, verified facts)
4. Retrieval Engine:
   - Dynamic Boost (5 query types)
   - 3-store parallel query
   - Hybrid Grounding (strict/hybrid/free)
5. Output: HDD Document (shown as a document icon, "80%+ Content Fidelity")

Infrastructure context:
- On-premises: Engineer to Obot to MCP Bridge
- AWS Seoul: API Gateway to Lambda
- AWS Virginia: OpenSearch, Bedrock (Titan + Claude)
- VPN tunnel connecting on-prem to AWS

Style: Modern system architecture diagram, clean with icons, arrows showing data flow, color-coded by layer (blue=parsing, purple=storage, green=retrieval, gold=output).
```

---

## 사용법

1. 위 프롬프트를 ChatGPT (GPT-4o)에 붙여넣기
2. "Generate an image" 또는 "이미지를 생성해줘"라고 요청
3. 결과물을 다운로드하여 `docs/diagrams/` 에 저장
4. 마크다운에서 `![NPU Architecture](../diagrams/npu_architecture.png)` 로 참조

### 팁
- GPT-4o는 텍스트가 많은 기술 다이어그램에서 글자가 깨질 수 있음
- 그런 경우 "텍스트 라벨 없이 블록과 연결만 그려줘, 라벨은 내가 나중에 추가할게"로 요청
- 또는 "SVG 코드로 생성해줘"라고 하면 편집 가능한 벡터를 받을 수 있음

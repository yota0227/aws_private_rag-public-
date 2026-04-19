# INT16 / FP16 / INT8 LLM Performance Guide
**Document:** INT16_Guide_HDD_V0.2
**Date:** 2026-03-18 (v0.2: added §0 dimension glossary, expanded §2.4 tiling loop, expanded §3.2 GEMM rules)
**Platform:** Trinity SoC — Tensix core / Overlay / Router / NIU
**Example workload:** LLaMA 3.1 8B inference & mixed-precision fine-tuning
**Sources:** tensix_core_HDD.md (v0.3), NIU_HDD_v0.1.md, router_decode_HDD_v0.5.md, overlay_hierarchy.csv, RTL 20260221

---

## Table of Contents

0. [Dimension & Symbol Glossary](#0-dimension--symbol-glossary)
1. [Trinity Grid Recap & Cluster Definitions](#1-trinity-grid-recap--cluster-definitions)
2. [LLM Layer Decomposition Strategy](#2-llm-layer-decomposition-strategy)
3. [Tile Assignment Decision Guide](#3-tile-assignment-decision-guide)
4. [INT16 Full SW+HW Path](#4-int16-full-swhw-path)
5. [FP16B Full SW+HW Path](#5-fp16b-full-swhw-path)
6. [INT8 Full SW+HW Path](#6-int8-full-swhw-path)
7. [Memory Efficiency — Format-by-Format](#7-memory-efficiency--format-by-format)
8. [Resource Efficiency — MAC / DMA / Processor](#8-resource-efficiency--mac--dma--processor)
9. [Overlay Usage Guide per Format](#9-overlay-usage-guide-per-format)
10. [NoC / NIU Data Movement Guide](#10-noc--niu-data-movement-guide)
11. [Register Programming Reference](#11-register-programming-reference)
12. [LLaMA 3.1 8B End-to-End Mapping](#12-llama-31-8b-end-to-end-mapping)
13. [Summary Comparison Table](#13-summary-comparison-table)
14. [Future Work](#14-future-work)
15. [Memory Traffic Improvement Guide — HW Configuration View](#15-memory-traffic-improvement-guide--hw-configuration-view)
16. [Memory Traffic Improvement Guide — SW Operation View](#16-memory-traffic-improvement-guide--sw-operation-view)

---

## 0. Dimension & Symbol Glossary

This section defines every symbol used throughout the document.
All symbols appear in **GEMM notation: Y = X × W** (row-vector × weight matrix convention).

### 0.1 GEMM Dimension Symbols

```
     ┌─── input activation ───┐   ┌─── weight matrix ───┐   ┌─── output ───┐
     │  X  [M × K]            │ × │  W  [K × N]         │ = │  Y  [M × N]  │
     └────────────────────────┘   └─────────────────────┘   └──────────────┘

        M  ──────────────────────────────────────────────────────────────────►
        (rows of tokens in the batch / sequence being processed)

                  K  ──────────────────────────────────────────────────────►
                  (shared reduction dimension — hidden size / embedding dim)

                                       N  ──────────────────────────────────►
                                       (output feature columns — projection width)
```

| Symbol | Full name | LLaMA 3.1 8B example | HW mapping |
|--------|-----------|----------------------|------------|
| **M** | Batch × sequence length (row dimension of activation X) | 128 tokens per tile | DEST rows; limited to 512 (INT32) or 1024 (FP16) |
| **K** | Reduction / inner dimension (hidden dim, input channels) | 4096 (d_model) | SRCA depth; hardware limit = **48 rows per tile pass** → K must be looped |
| **N** | Output feature width (projection output columns) | 4096 (same proj), 14336 (FFN up) | FPU MAC width = **16 columns fixed**; large N needs N-tiling |
| **W** | Weight matrix [K × N] | shape varies per layer | Stored in L1; must fit after tiling |
| **X** | Input activation matrix [M × K] | token embeddings or intermediate activations | Streamed from L1 in K_tile strips |
| **Y** | Output activation matrix [M × N] | result of linear projection | Written back to L1; forwarded via NoC |

### 0.2 Tile-Size Symbols

These are the **software-chosen chunk sizes** that divide the full dimensions into pieces that fit in hardware registers and L1:

| Symbol | Full name | Typical value | Constraint source |
|--------|-----------|---------------|-------------------|
| **M_tile** | Number of token rows processed per DEST buffer pass | 16 | Software choice; ≤ 256 (INT32 DEST half-buffer) or ≤ 512 (FP16) |
| **K_tile** | Number of reduction steps loaded into SRCA/SRCB per MOP iteration | 48 | Hardware: SRCA = 48 rows max (`SRCS_NUM_ROWS_16B=48`) |
| **N_tile** | Number of output columns processed per FPU cycle | 16 | Hardware: FPU MAC array = 16 columns fixed (`FP_TILE_COLS=16`) |
| **N_subtile** | Number of output columns loaded into L1 per weight-block pass | 256 (example) | Software choice; must satisfy L1 fit: `K × N_subtile × bytes_per_weight ≤ L1_budget` |
| **N_local** | Each tile's column shard after tensor-parallel split across 4 X-tiles | N / 4 | Tensor parallelism degree = 4 (X-axis) |

### 0.3 Loop-Count Symbols

Derived from the above: how many times each loop runs.

| Symbol | Formula | LLaMA 8B FFN example (N=4096, K=4096, M=128) |
|--------|---------|----------------------------------------------|
| **M_tiles** | M / M_tile | 128 / 16 = **8** |
| **K_tiles** | ⌈K / K_tile⌉ | ⌈4096 / 48⌉ = **86** |
| **N_tiles** | N_local / N_tile | 1024 / 16 = **64** per tile |
| **N_subtile_passes** | N_local / N_subtile | 1024 / 256 = **4** per tile |
| **K_tiles_per_subtile** | K / K_tile | 4096 / 48 = **86** (same, K does not change) |

### 0.4 Hardware Resource Symbols (fixed, from RTL)

| Symbol | Value | Source | Meaning |
|--------|-------|--------|---------|
| **FP_TILE_COLS** | 16 | `tt_tensix_pkg.sv` | MAC array column count = N_tile |
| **SRCS_NUM_ROWS_16B** | 48 | `tt_tensix_pkg.sv` | SRCA and SRCB maximum rows = K_tile limit |
| **DEST_NUM_ROWS_16B** | 1024 | `tt_tensix_pkg.sv` | DEST register rows in FP16 mode |
| **DEST_NUM_ROWS_INT32** | 512 | derived (32-bit datum) | DEST register rows in INT32 mode (INT8/INT16 accumulator) |
| **MULT_PAIRS** | 8 | `tt_fpu_tile.sv` | Products accumulated per FP Lane per clock cycle |
| **L1_SIZE** | ~1.5 MB | layout | Total tile-local SRAM |
| **L1_WORD** | 128-bit | `tt_t6_l1` | Bytes per L1 bus transaction = 16 B |

### 0.5 Data-Flow Symbols (per layer)

| Symbol | Meaning | Typical format |
|--------|---------|---------------|
| **d_model** | Transformer hidden dimension = K for most projections | 4096 |
| **d_ffn** | FFN intermediate dimension = N for up/gate projection | 14336 |
| **d_k** | Attention head dimension = K for QK^T | d_model / num_heads = 128 |
| **d_v** | Value head dimension (= d_k in LLaMA) | 128 |
| **seq** | Sequence length = M for attention | 2048–8192 |
| **B** | Batch size = contributes to M together with seq | 1–16 |
| **H** | Number of attention heads | 32 (LLaMA 3.1 8B) |
| **H_kv** | Number of KV heads (GQA) | 8 (LLaMA 3.1 8B) |

### 0.6 Symbol Usage Map by Operation

| LLM Operation | M | K | N | W shape | Notes |
|--------------|---|---|---|---------|-------|
| Q projection | B×seq | d_model | d_model | [d_model × d_model] | per head: K=d_model, N=d_k×H |
| K projection | B×seq | d_model | d_model | [d_model × d_k×H_kv] | GQA: N smaller than Q |
| V projection | B×seq | d_model | d_model | same as K | — |
| Attention QK^T | H×seq | d_k | seq | — (no weight; X=Q, W=K^T) | K=d_k, N=seq |
| Attention AV | H×seq | seq | d_k | — (no weight; X=A, W=V) | K=seq, N=d_k |
| O projection | B×seq | d_model | d_model | [d_model × d_model] | output of attention |
| FFN gate proj | B×seq | d_model | d_ffn | [d_model × d_ffn] | SiLU gate |
| FFN up proj | B×seq | d_model | d_ffn | [d_model × d_ffn] | element-wise with gate |
| FFN down proj | B×seq | d_ffn | d_model | [d_ffn × d_model] | K=d_ffn (large K) |
| Embedding lookup | B×seq | vocab | d_model | [vocab × d_model] | special: M=1, K=vocab_one_hot |
| LM head | B×seq | d_model | vocab | [d_model × vocab] | very large N=128256 |

---

## 1. Trinity Grid Recap & Cluster Definitions

### 1.1 Physical Grid (4 × 5 mesh)

```
     X=0        X=1        X=2        X=3
Y=0  TENSIX(0)  TENSIX(5)  TENSIX(10) TENSIX(15)   ← Compute cluster A
Y=1  TENSIX(1)  TENSIX(6)  TENSIX(11) TENSIX(16)   ← Compute cluster B
Y=2  TENSIX(2)  TENSIX(7)  TENSIX(12) TENSIX(17)   ← Compute cluster C
Y=3  DISP_E(3)  ROUTER(8)  ROUTER(13) DISP_W(18)   ← Dispatch / routing row
Y=4  NIU_NE(4)  NIU_N(9)   NIU_N(14)  NIU_NW(19)  ← AXI bridge / DRAM I/O
```

EndpointIndex = X × SizeY + Y (column-major, `trinity_pkg.sv`).
12 compute tiles (Y=0..2), 2 dispatch tiles (Y=3, X=0 and X=3), 2 pure routers (Y=3, X=1,2),
4 NIU/NOC2AXI tiles (Y=4).

### 1.2 Functional Cluster Definitions

For LLM workloads, software defines logical clusters:

| Cluster | Tiles | Primary role |
|---------|-------|--------------|
| **Compute-A** | (0,0)(1,0)(2,0)(3,0) | First spatial row — often GEMM tile-group 0 |
| **Compute-B** | (0,1)(1,1)(2,1)(3,1) | Second row — GEMM tile-group 1 / KV-cache |
| **Compute-C** | (0,2)(1,2)(2,2)(3,2) | Third row — GEMM tile-group 2 / activation |
| **Dispatch** | (0,3)(3,3) | Kernel binary loader, tile descriptor injector |
| **IO** | (0,4)(1,4)(2,4)(3,4) | DRAM DMA via NOC2AXI; ATT-based address map |

Each compute tile has: 4 TRISC threads, 256 MACs, 1.5 MB L1, one NIU endpoint.

### 1.3 Key Tile Parameters

| Parameter | Value | Significance |
|-----------|-------|--------------|
| FP_TILE_COLS | 16 | Matrix width per cycle (one element per FP Lane column) |
| SRCA/SRCB rows | 48 | Max K-depth loaded per tile before math — tile must fit in 48 rows |
| DEST rows (FP16) | 1024 | M-dimension capacity per tile in FP16/INT16 → INT32 accumulator = 512 |
| L1 size | ~1.5 MB | Total tile-local SRAM; weights + activations must fit |
| L1 bus width | 128-bit | 16 bytes per L1 transaction |
| FP Lane depth | 8 pairs/cycle | MULT_PAIRS=8; 8 accumulated products per FP Lane per cycle |
| NoC flit | 2083-bit | 512-bit payload + flit_type(3b) + parity(32b) |
| NIU AXI data | 512-bit | 64 bytes per AXI beat from DRAM |

---

## 2. LLM Layer Decomposition Strategy

### 2.1 LLaMA 3.1 8B — Key Dimensions

| Parameter | Value |
|-----------|-------|
| Hidden dim (d_model) | 4096 |
| FFN intermediate | 14336 |
| Attention heads | 32 |
| KV heads (GQA) | 8 |
| Layers | 32 |
| Vocab size | 128,256 |
| Sequence length (typical) | 2048–8192 |

### 2.2 Parallelism Strategies

Three parallelism axes apply to Trinity's 4×3 grid:

#### (A) Tensor Parallelism (TP) — split weight matrix across tiles

Split the weight columns (N dimension) across X-axis tiles:

```
Weight W [K × N] → 4 shards: W0[K × N/4], W1[K × N/4], W2[K × N/4], W3[K × N/4]
Each tile (X=0..3, same Y-row) holds one shard.
GEMM: Y_i = X × Wi  →  then all-reduce across X via NoC broadcast.
```

**Use case:** QKV projection, FFN up/gate/down projection.
**Advantage:** Each tile only needs N/4 of the output — L1 fits 4× larger matrices.

#### (B) Pipeline Parallelism (PP) — different layers on different Y-rows

Each Y-row processes a different LLM layer (or layer group):

```
Y=0 row → Layer 0 attention GEMM
Y=1 row → Layer 0 FFN GEMM
Y=2 row → Layer 0 + Layer 1 residual + norm
```

Tiles forward intermediate activations via NoC in a pipeline.
**Use case:** Long inference sequences where each tile stage can overlap.
**Advantage:** Hides DRAM latency — while Y=2 computes layer N, Y=0 is loading layer N+1 weights.

#### (C) Data Parallelism (DP) — different batch samples on different columns

Each X column processes a different batch sample:

```
X=0: batch[0], X=1: batch[1], X=2: batch[2], X=3: batch[3]
```

**Use case:** Large batch inference, fine-tuning. Requires independent weight copies per column — only practical if weights fit in L1 × 4.

### 2.3 Recommended Split: Hybrid TP+PP for LLaMA 3.1 8B

```
Layer group 0 (layers 0–10):    Compute-A (Y=0 row, TP degree=4)
Layer group 1 (layers 11–21):   Compute-B (Y=1 row, TP degree=4)
Layer group 2 (layers 22–31):   Compute-C (Y=2 row, TP degree=4)
```

Inter-layer activations forwarded via NoC unicast: row Y→Y+1 (Y- direction in NoC DOR).
Weight shards pre-loaded from DRAM via NIU (Y=4) before inference begins.

### 2.4 Tiling the GEMM

#### Why tiling is necessary

The full GEMM matrices (M × K activation, K × N weight) are too large to fit in hardware registers simultaneously:

```
SRCA register holds K_tile = 48 rows   →  only 48 of K=4096 reduction steps at once
DEST register holds M_tile rows        →  only 512 (INT32) or 1024 (FP16) of M at once
L1 holds W_tile = K × N_subtile bytes  →  only a column shard of W at once
```

Tiling slices all three dimensions (M, K, N) into chunks that fit, then **loops** over the chunks. The MOP hardware accelerates the innermost K-loop.

#### Tile-size selection (refer to §0.2 for symbol definitions)

```
N_tile    = 16    (fixed by FPU MAC array width — FP_TILE_COLS)
K_tile    = 48    (fixed by SRCA/SRCB register depth — SRCS_NUM_ROWS_16B)
M_tile    = 16    (software choice; must satisfy M_tile ≤ DEST_half_buffer)
N_subtile = 256   (software choice; must satisfy K × N_subtile × bytes ≤ L1_budget)
```

#### Full tiling loop structure

```
                        ┌────────────────────────────────────────────────┐
                        │  Outer loops (software, BRISC or overlay CPU)  │
                        │                                                 │
  for n_sub in          │  N_subtile_passes = N_local / N_subtile         │
  range(N_subtile_passes)│  (e.g. 1024/256 = 4 passes)                  │
    ┌───────────────────┴─────────────────────────────────────────────┐  │
    │  BRISC: DMA load W[0:K, n_sub*N_subtile : (n_sub+1)*N_subtile] │  │
    │         → L1_weight_base  (K × N_subtile × bytes_per_weight)   │  │
    └───────────────────┬─────────────────────────────────────────────┘  │
                        │                                                 │
    for m in            │  M_tiles = M / M_tile                           │
    range(M_tiles)      │  (e.g. 128/16 = 8 passes)                      │
      ┌──────────────── │ ─────────────────────────────────────────────┐  │
      │  TRISC0:       │  unpack X[m*M_tile : (m+1)*M_tile, 0:K]       │  │
      │  (loop over K) │  in strips of K_tile rows → SRCB              │  │
      │                 │                                               │  │
      │  for k in       │  K_tiles = ceil(K / K_tile)                  │  │
      │  range(K_tiles) │  (e.g. ceil(4096/48) = 86 passes)            │  │
      │    ┌──────────  │ ──────────────────────────────────────────┐  │  │
      │    │  TRISC0:  │  unpack W[k*K_tile:(k+1)*K_tile,           │  │  │
      │    │           │          n_col:n_col+N_tile] → SRCA         │  │  │
      │    │  TRISC0:  │  unpack X[m_row:m_row+M_tile,              │  │  │
      │    │           │          k*K_tile:(k+1)*K_tile] → SRCB      │  │  │
      │    │           │                                             │  │  │
      │    │  TRISC1 MOP (hardware-accelerated innermost loop):     │  │  │
      │    │    DOTPV / MVMUL:                                       │  │  │
      │    │    SRCA[K_tile × N_tile] ×                             │  │  │
      │    │    SRCB[M_tile × K_tile]                               │  │  │
      │    │    → accumulate into DEST[M_tile × N_tile]             │  │  │
      │    └──────────────────────────────────────────────────────┘  │  │
      │  After all K_tiles:                                           │  │
      │  TRISC2: descale DEST → pack → L1_output[m, n_sub]           │  │
      └───────────────────────────────────────────────────────────────┘  │
                        └────────────────────────────────────────────────┘

  After all m and n_sub passes:
  BRISC: NoC write L1_output[all M, all N_local] → next tile or DRAM
```

#### Key constraint check at each dimension

| Dimension | Constraint | Check | If violated |
|-----------|-----------|-------|-------------|
| K_tile ≤ 48 | SRCA rows | `K_tile = min(K, 48)` | Always 48; loop over K |
| M_tile ≤ DEST_half | DEST rows | `M_tile ≤ 256` (INT32) or `≤ 512` (FP16) | Reduce M_tile |
| N_tile = 16 | MAC width | Fixed | No choice |
| K × N_subtile × B ≤ L1_budget | L1 capacity | See §7 fit formula | Reduce N_subtile |
| X strip = M_tile × K_tile × B | L1 activation | Usually tiny (1.5 KB) | No issue |

**INT16 constraint:** DEST in INT32 mode = 512 rows → M_tile ≤ 256 per buffer. Keep M_tile = 16 to leave headroom; software can accumulate up to 16 M-tiles = 256 DEST rows before TRISC2 must drain.

**FP16B constraint:** DEST = 1024 rows → M_tile ≤ 512 per buffer. Up to 32 M-tiles of 16 rows fit before drain required.

---

## 3. Tile Assignment Decision Guide

### 3.1 Decision Flowchart

```
For each LLM operation:

START
  │
  ├─ Is this a GEMM (matmul)?
  │     YES → go to §3.2 GEMM Assignment
  │     NO  →
  │           ├─ Element-wise op (norm, scale, add)?  → §3.3 SFPU Assignment
  │           ├─ Attention score (QK^T, softmax)?     → §3.4 Attention Assignment
  │           └─ DMA (weight load, KV-cache I/O)?     → §3.5 NIU Assignment
  │
```

### 3.2 GEMM Assignment Rules

For symbol definitions (M, K, N, W, X, Y, M_tile, K_tile, N_subtile) see **§0**.

```
Quick reference:
  M = number of token rows in the current batch/sequence slice   (rows of X)
  K = hidden dimension / reduction depth                         (cols of X = rows of W)
  N = output feature width / projection output columns           (cols of W = cols of Y)
  W = weight matrix [K × N], stored in L1
  X = input activation [M × K], streamed from L1
  Y = output [M × N], written to L1 then forwarded via NoC
```

| Condition | Symbol meaning | Assign to | Format | Rationale |
|-----------|---------------|-----------|--------|-----------|
| **Weight W fits in L1 after N-subtiling** | `K × N_subtile × B_w ≤ ~1 MB` where `B_w`=bytes/weight, `N_subtile`=column shard | Any compute tile | INT8 or FP16B | Weight-stationary: load once, loop over all M_tile passes |
| **K > 48 (deep reduction)** | K = hidden dim; SRCA max depth = 48 rows = K_tile | Split K across MOP inner loop (86 passes for K=4096) | INT16 or INT8 | Hardware K_tile limit; MOP_CFG_LOOP0_LEN = K_tiles−1 |
| **N > 16 per tile** | N = output cols; FPU MAC width = N_tile = 16 fixed | Tensor-parallel: split N across X-axis (N_local = N/4 per tile) | INT8 packed | Each tile gets N_local = N/4 columns; 4× tiles cover full N |
| **M > 512 rows (INT32 DEST mode)** | M = token rows; DEST (INT32) = 512 rows total; half-buffer = 256 rows per ping-pong | Multi-pass DEST drain: loop M in M_tile=16 chunks, drain every pass | INT16 → INT32 | DEST double-buffer: 256 rows active + 256 rows draining simultaneously |
| **Precision-critical** (attention scores, LM head) | K=d_k=128 small; N=seq or vocab large; outlier activations | Dedicated tile, FP16B format end-to-end | FP16B | Small K → few accumulations → INT8 precision loss matters |
| **Throughput-critical** (FFN up/gate/down) | K=d_model=4096, N=d_ffn=14336 large; weights ~56 MB total | Packed INT8, weight-stationary per N_subtile | INT8 packed | 512 MACs/cycle; 2× TDMA feed rate; weight range fits INT8 calibration |

**Rule of thumb:**
- **INT8** wherever `K × N_subtile` weight block fits in L1 and activations are calibrated to INT8 range.
- **INT16** when activation outliers exceed INT8 range (±127), particularly KV-cache and mid-layer activations.
- **FP16B** for small-K layers (attention scores: K=d_k=128) and all element-wise ops (norms, residuals).

#### L1 Fit Formula for Weight Block

```
N_subtile_max = floor( (L1_budget_bytes - overhead) / (K × bytes_per_weight) )

Where:
  L1_budget_bytes  ≈ 1,048,576 B  (1 MB reserved for weights; 0.5 MB for act+output)
  K                = reduction dimension (e.g. 4096 for FFN down projection)
  bytes_per_weight = 1 (INT8), 2 (INT16 or FP16B)
  overhead         = 2 × M_tile × K_tile × B_act   (SRCA/SRCB streaming buffer)
                   + 2 × M_tile × N_subtile × B_out (output double-buffer)
                   + 64 KB (kernel code + stack)

Example (INT8 weight, K=4096, M_tile=16, K_tile=48, B_out=2B INT16):
  overhead = 2×16×48×1 + 2×16×N_sub×2 + 65536
           = 1536 + 64×N_sub + 65536
  N_subtile_max = (1,048,576 - 67072) / 4096 ≈ 239 → round to power-of-2: N_subtile = 256 (safe since 4096×256=1 MB exactly, use N_subtile=128 if tight)

Simplified rule: N_subtile = 256 for INT8 weights with K ≤ 4096.
                 N_subtile = 128 for FP16B weights with K ≤ 4096.
```

### 3.3 Element-wise / SFPU Assignment

SFPU operates on the DEST register file directly at **4 rows/cycle, 16 columns parallel**.
Full DEST drain (1024 rows FP16): 256 SFPU cycles = ~256 ns at 1 GHz ai_clk.

| Operation | HW path | Format |
|-----------|---------|--------|
| RMSNorm | SFPU (inverse sqrt polynomial) | FP32 in lreg |
| SiLU / GELU | SFPU (Horner polynomial expansion) | FP32 in lreg |
| ReLU | Packer hardware ReLU (zero overhead) | Any |
| Residual add | SFPU MAD (a×1 + b×1 → lreg) | FP32 in lreg |
| Softmax (attention) | SFPU (exp, reciprocal sum) | FP32 in lreg |

**Assignment:** Element-wise ops run on the **same tile** immediately after the GEMM MOP completes — no data movement. TRISC1 issues SFPU instructions after `sem_wait(SEM_MATH_DONE)`.

### 3.4 Attention Score Assignment

Attention score `A = softmax(QK^T / sqrt(d_k))` is memory-bandwidth-bound (seq × seq matrix).

```
Recommended split for seq=2048, heads=32, d_k=128:
  - Q tiles: (X=0, Y=1) — holds Q shard [seq, d_k] in L1 (INT16)
  - K tiles: (X=1, Y=1) — holds K shard [seq, d_k] in L1 (INT16)
  - A tiles: (X=2, Y=1) — computes QK^T [seq, seq] (FP16B for softmax range)
  - V tiles: (X=3, Y=1) — holds V shard; post-softmax AV product (INT16)
```

**NoC pattern:** Q tile broadcasts K column slices via `cmd_brcst_bit=1` to all A-tiles.
After softmax, A tile unicasts to V tile.

### 3.5 NIU / DMA Assignment

DRAM traffic is handled exclusively through the Y=4 NIU row.
Software assigns DMA responsibilities per NIU node:

| NIU node | Coord | Recommended role |
|----------|-------|-----------------|
| NIU_NE | (0,4) | Layer 0..10 weight streaming for Compute-A |
| NIU_N  | (1,4) | KV-cache read/write for attention tiles |
| NIU_N  | (2,4) | Layer 11..21 weight streaming for Compute-B |
| NIU_NW | (3,4) | Layer 22..31 weight streaming for Compute-C |

Each NIU can issue 16 outstanding reads (AXI_MST_OUTSTANDING_READS=16) and 32 outstanding writes.
Maximum DRAM bandwidth per NIU: 512-bit × frequency.

---

## 4. INT16 Full SW+HW Path

### 4.1 When to Use INT16

| Scenario | Use INT16 because |
|----------|------------------|
| KV-cache storage (long context) | 2× smaller than FP32, better range than INT8 |
| Attention Q/K/V projection output | Preserves sign and magnitude for outlier tokens |
| Intermediate activation between layers | Medium precision, avoids FP16 exponent bias issues |
| Fine-tuning gradient accumulation | INT32 accumulator prevents gradient underflow |

### 4.2 Hardware Data Path (INT16 GEMM)

```
DRAM (INT16 weights, 2B/element)
    │
    │  AXI 512-bit burst → 32 INT16 elements per beat
    ▼
NIU (tt_noc2axi, Y=4)
    │  NoC flit, VC 0-7 (unicast request)
    │  noc_header_address_t: {x_coord[6b], y_coord[6b], addr[64b]}
    ▼
Router mesh (DOR: X-first, then Y-)
    │  At each hop: check dest_x vs local_x, then dest_y vs local_y
    ▼
Target Tensix tile (X, Y=0..2)
    │  NIU delivers to local L1 via flex_client_wr_port (ai_clk domain)
    ▼
L1 SRAM (tt_t6_l1)
    │  16 banks × 128-bit ECC
    │  Stored as raw INT16, 8 elements per 128-bit L1 word
    ▼
TDMA Unpacker CH0 (tt_unpack_row → tt_unpacker_gasket_fmt_conv)
    │  INT16 → FPU 19-bit extended internal format
    │  Sign bit [18], Extended exp [17:10] = 0x7F (bias 127, integer=2^0 format)
    │  Extended mantissa [9:0] = int16_value[9:0] (lower 10 bits)
    │  Note: INT16 upper bits 15:10 handled via exponent scaling
    ▼
SRCA register file (48 rows × 16 cols × 19-bit extended)
    │
    ▼
Integer Multiplier: tt_mul16 (Radix-4 Booth + CSA Wallace tree)
    │  16×16 → 32-bit partial product per FP Lane per cycle
    │  8 products accumulated per lane per cycle (MULT_PAIRS=8)
    │  16 FP Lane columns in parallel → 16 × 32-bit results/cycle
    ▼
Compressor tree (tt_four_two_compressor)
    │  4:2 balanced carry-save
    ▼
tt_multiop_adder → INT32 result per FP Lane
    ▼
DEST register file (INT32/FP32 mode: 512 rows × 16 cols × 32-bit)
    │  Double-buffer A[rows 0..255] / B[rows 256..511]
    │  ALU_ACC_CTRL.Fp32_enabled=1 for 32-bit storage
    ▼
tt_dstac_to_mem (format conversion)
    │  INT32 → INT16: arithmetic right shift by INT_DESCALE_AMOUNT
    │  Clamp to [-32768, 32767]
    ▼
TDMA Packer CH0 (tt_pack_row + tt_packer_gasket_misc_ops)
    │  Assembles 128-bit L1 words: 8 × INT16 per word
    ▼
L1 output buffer
    │
    ▼
BRISC NoC write → next tile or DRAM via NIU
```

### 4.3 DEST Capacity in INT16 Mode

INT16 input → INT32 accumulator (mandatory):

```
FP32/INT32 mode: 512 rows × 16 cols × 32-bit = 512 × 16 × 4B = 32 KB

Double-buffer split:
  Buffer A: rows 0..255   (DEST_REGW_BASE = 0)
  Buffer B: rows 256..511 (DEST_SP_BASE   = 256)
```

Tile the M-dimension in chunks of ≤ 256 rows to use both buffers concurrently.

### 4.4 SW Register Programming (INT16 GEMM)

```c
// ── TRISC0: Unpacker configuration ────────────────────────────────────
wrcfg(THCON_UNPACKER0_0, {
    .IN_DATA_FORMAT  = INT16,          // code 4'h9
    .OUT_DATA_FORMAT = INT16,          // pass INT16 to SRCA
    .TILIZE_SRC_ADDR_OFFSET = l1_weight_base,
    .ENABLE_ARG_FIFO = 1,
});
wrcfg(THCON_UNPACKER0_4, {
    .SRC_Z_STRIDE  = K * sizeof(int16_t),  // stride for K dimension
    .DST_Z_STRIDE  = 1,
    .SRC_XY_STRIDE = 16 * sizeof(int16_t), // 16 columns × 2B
});

wrcfg(THCON_UNPACKER1_0, {             // CH1 for activations
    .IN_DATA_FORMAT  = INT16,
    .OUT_DATA_FORMAT = INT16,
    .TILIZE_SRC_ADDR_OFFSET = l1_act_base,
});

// ── TRISC1: Math configuration ─────────────────────────────────────────
wrcfg(ALU_FORMAT_SPEC_REG, {
    .SrcA_val_format = INT16,          // 4'h9
    .SrcB_val_format = INT16,          // 4'h9
    .Dstacc          = INT32,          // 4'h8 — mandatory for INT16 GEMM
});
wrcfg(ALU_ACC_CTRL, {
    .INT8_math_enabled = 0,            // INT16 path (NOT INT8 Booth-pair mode)
    .Fp32_enabled      = 1,            // use 32-bit DEST storage
});
wrcfg(ALU_ROUNDING_MODE, {
    .Fpu_srnd_en = 0,                  // stochastic rounding N/A for integer
});

// ── TRISC1: MOP inner loop (K-reduction) ───────────────────────────────
wrcfg(MOP_CFG_LOOP0_LEN, k_tiles - 1);   // K/48 iterations
wrcfg(MOP_CFG_LOOP1_LEN, m_tiles - 1);   // M/16 iterations
wrcfg(MOP_CFG_LOOP_START_INSTRN0, DOTPV_instrn({
    .dstacc_idx = DEST_REGW_BASE,
    .accum_en   = 1,                   // accumulate across K-tiles
}));
issue_instrn(MOP);                     // hardware K×M inner loop

// ── TRISC2: Packer configuration ──────────────────────────────────────
wrcfg(THCON_PACKER0_2, {
    .INT_DESCALE_ENABLE = 1,
    .INT_DESCALE_MODE   = 1,           // arithmetic right shift
    .INT_DESCALE_AMOUNT = descale_bits, // calibrate to weight_scale * act_scale
});
wrcfg(THCON_PACKER0_0, {
    .IN_DATA_FORMAT  = INT32,          // read INT32 from DEST
    .OUT_DATA_FORMAT = INT16,          // write INT16 to L1
    .RELU_MODE       = 0,             // disable (use SFPU for activation)
});
issue_instrn(MOP, {PACR});
```

### 4.5 Double-Buffer Orchestration (INT16)

```c
// TRISC1 (math thread):
uint32_t dest_base = 0;
uint32_t dest_sp   = 256;   // 256 rows per buffer in INT32 mode

while (m_tile_remaining > 0) {
    sem_wait(SEM_UNPACK_DONE);           // TRISC0 filled SRCA/SRCB
    wrcfg(DEST_REGW_BASE, dest_base);
    issue_mop(DOTPV, k_tiles);           // INT16 × INT16 → INT32 in DEST[dest_base]
    sem_post(SEM_MATH_DONE);             // signal TRISC2 to pack DEST[dest_base]
    swap(dest_base, dest_sp);            // ping-pong to other buffer
    m_tile_remaining--;
}

// TRISC2 (pack thread):
uint32_t pack_base = 0;
while (m_tile_packed < total_m_tiles) {
    sem_wait(SEM_MATH_DONE);
    wrcfg(THCON_PACKER0_ADDR, l1_out_base + pack_base * 16 * sizeof(int16_t));
    issue_mop(PACR, pack_count);         // INT32 → INT16, write to L1
    sem_post(SEM_PACK_DONE);
    pack_base += 16;                     // advance by m_tile rows
    m_tile_packed++;
}

// BRISC:
while (tile_sent < total_m_tiles) {
    sem_wait(SEM_PACK_DONE);
    noc_write(dst_addr, l1_out_base + tile_sent * 16 * 2, 16 * 16 * sizeof(int16_t));
    sem_post(SEM_BRISC_DONE);
    tile_sent++;
}
```

### 4.6 INT16 KV-Cache Pattern

For LLaMA attention, store KV-cache in INT16 to save L1/DRAM bandwidth:

```
KV-cache layout in L1 (per tile, per layer):
  K: [seq_len × d_k] × INT16 = 2048 × 128 × 2B = 512 KB
  V: [seq_len × d_k] × INT16 = 512 KB
  Total: 1024 KB ≈ 1 MB  → fits in 1.5 MB L1 with 0.5 MB headroom for activations

Steps:
  1. Load K from DRAM (INT16, NIU DMA), store in L1[K_BASE].
  2. Compute QK^T:
       TDMA CH0 unpack K tile (INT16 → SRCA)
       TDMA CH1 unpack Q tile (INT16 → SRCB)
       FPU: DOTPV → INT32 DEST
  3. Descale INT32 → INT16 attention logit (INT_DESCALE = floor(log2(sqrt(d_k))))
  4. SFPU softmax: SFPLOAD → SFPMAD (exp polynomial) → SFPSTORE
  5. Multiply A × V:
       TDMA CH0 unpack V tile (INT16 → SRCA)
       TDMA CH1 unpack softmax output (FP16B → SRCB, convert after SFPU)
       FPU: MVMUL → FP16B DEST
  6. Pack output to FP16B for residual add.
```

---

## 5. FP16B Full SW+HW Path

### 5.1 When to Use FP16B (BFloat16)

| Scenario | Reason |
|----------|--------|
| Attention score computation (QK^T) | Dynamic range: softmax inputs span large exp range |
| Residual stream activations | Preserves gradient scale in training |
| Output of each transformer layer | Standard mixed-precision training format |
| RMSNorm input | SFPU needs FP32 lreg; FP16B → FP32 is lossless |
| Final lm_head projection | Vocabulary distribution must be full-precision |

### 5.2 Hardware Data Path (FP16B GEMM)

```
L1 (FP16B activations, 2B/element, bias=127)
    │
TDMA Unpacker CH0 → tt_unpacker_gasket_fmt_conv
    │  FP16B: {sign[1], exp[8], man[7]} →
    │  19-bit extended: sign[18], exp[17:10]=exp+0, man[9:3]=man, man[2:0]=0
    │  (extends 7-bit BF16 mantissa to 10-bit with 3 zero LSBs)
    ▼
SRCA register file [48 rows × 16 cols × 19-bit]
    ▼
tt_fp_mul_raw (×8 per FP Lane)
    │  Partitioned mode: exp_a + exp_b → exp_sum[8:0]
    │                    man_a × man_b → man_prod[19:0] (20-bit product)
    ▼
tt_exp_path_v4
    │  max_exp = max(exp_sum[0..7])      — 8-input parallel max tree
    │  shift_amt[i] = max_exp - exp_sum[i]
    ▼
tt_dual_align (×8) + tt_barrel_rshift (4-stage pipeline, RNE guard/sticky)
    │  Aligns 8 products to shared max exponent
    ▼
tt_four_two_compressor → tt_three_two_compressor → tt_multiop_adder
    │  Carry-save accumulation → final sum
    ▼
tt_fp_sop_normalize + tt_t6_com_stoch_rnd
    │  Normalize to FP16B output; optional stochastic rounding
    ▼
DEST register file (FP16B mode: 1024 rows × 16 cols × 16-bit)
    │  Double-buffer: A[0..511] / B[512..1023]
    ▼
tt_dstac_to_mem
    │  FP16B pass-through (default) or → FP8 E4M3 for compressed output
    ▼
TDMA Packer → L1 output buffer → NoC → next tile
```

### 5.3 SW Register Programming (FP16B GEMM)

```c
// TRISC0: Unpacker — BF16 input
wrcfg(THCON_UNPACKER0_0, {
    .IN_DATA_FORMAT  = FP16B,          // code 4'h5
    .OUT_DATA_FORMAT = FP16B,
    .TILIZE_SRC_ADDR_OFFSET = l1_base,
    .ENABLE_ARG_FIFO = 1,
});

// TRISC1: Math — FP16B × FP16B → FP16B accumulate
wrcfg(ALU_FORMAT_SPEC_REG, {
    .SrcA_val_format = FP16B,          // 4'h5
    .SrcB_val_format = FP16B,
    .Dstacc          = FP16B,          // 16-bit DEST → 1024 rows available
});
wrcfg(ALU_ACC_CTRL, {
    .INT8_math_enabled = 0,
    .Fp32_enabled      = 0,            // FP16 DEST (1024 rows)
});
wrcfg(ALU_ROUNDING_MODE, {
    .Fpu_srnd_en = stochastic_en,      // 1 for training, 0 for inference
});

// TRISC1: MOP MVMUL
wrcfg(MOP_CFG_LOOP0_LEN, k_tiles - 1);
wrcfg(MOP_CFG_LOOP1_LEN, m_tiles - 1);
wrcfg(MOP_CFG_LOOP_START_INSTRN0, MVMUL_instrn({.accum_en = 1}));
issue_instrn(MOP);

// TRISC2: Packer — output as FP8 E4M3 (to save NoC BW)
wrcfg(THCON_PACKER0_0, {
    .IN_DATA_FORMAT  = FP16B,
    .OUT_DATA_FORMAT = FP8_E4M3,       // 2× compression before NoC transfer
    .STOCH_RND_EN    = 1,              // stochastic rounding for FP8 conversion
});
issue_instrn(MOP, {PACR});
```

### 5.4 Stochastic Rounding for Training (FP16B → FP8)

When `STOCH_RND_EN=1`, the packer path invokes `tt_t6_com_stoch_rnd`:

```
Per-column PRNG (32-bit Galois LFSR, seed = global_seed XOR col_index):
  rand[31:0] = LFSR_next()

Rounding:
  residual R = FP16B_man[6:0]   (the 7 bits lost in FP8 conversion)
  round_up   = (R > rand[6:0])
  FP8_man    = FP16B_man[7] + round_up
```

This ensures `E[round(x)] = x` — critical for training convergence at low precision.

---

## 6. INT8 Full SW+HW Path

### 6.1 When to Use INT8

| Scenario | Reason |
|----------|--------|
| Weight storage (all linear layers) | 4× smaller than FP32, 2× vs FP16 |
| FFN up/gate projection | Throughput-critical; 512 MACs/cycle in packed mode |
| Embedding lookup | Large table; INT8 cuts memory 2× vs FP16 |
| Post-attention value projection | Activations within INT8 range after softmax scale |

### 6.2 Hardware Data Path (INT8 Packed GEMM)

```
L1 (INT8 weights, 1B/element)
    │  16 INT8 elements per 128-bit L1 word (2× FP16 density)
    ▼
TDMA Unpacker CH0 → tt_unpacker_gasket_fmt_conv
    │  INT8 → SRCA: two INT8 values packed into one 16-bit SRCA slot
    │  mode: SRCA_UNSIGNED=0 (signed), INT8_PACKED=1
    ▼
SRCA register file [48 rows × 16 cols × 16-bit (2× INT8 packed)]
    ▼
tt_mul8 (Radix-4 Booth encoder × CSA Wallace tree for 8×8 multiply)
    │  Two INT8 pairs per FP Lane column per cycle
    │  Result: 2 × 16-bit partial products → merged to INT32
    │  16 FP Lane columns × 2 pairs = 32 INT8 MACs/cycle per row
    │  MULT_PAIRS=8 → 8 × 2 = 16 per lane → 16 × 16 = 256 effectively,
    │  but packed mode delivers 512 INT8 ops/cycle (2 per Booth cell)
    ▼
Compressor tree → INT32 accumulator
    ▼
DEST register file (INT32 mode: 512 rows × 16 cols × 32-bit)
    ▼
tt_dstac_to_mem
    │  INT32 → INT8 with INT_DESCALE (right-shift + saturation clamp [-128,127])
    │  Optional: INT32 → MXINT8 via tt_t6_com_elem_to_mx_convert
    │              (shared block exponent per 16 elements)
    ▼
TDMA Packer → L1 output → NoC → next tile
```

### 6.3 SW Register Programming (INT8 Packed GEMM)

```c
// TRISC0: Unpacker — INT8 packed input
wrcfg(THCON_UNPACKER0_0, {
    .IN_DATA_FORMAT  = INT8,           // code 4'he
    .OUT_DATA_FORMAT = INT8,
    .TILIZE_SRC_ADDR_OFFSET = l1_weight_base,
    .ENABLE_ARG_FIFO = 1,
});

// TRISC1: Math — INT8 packed × INT8 → INT32
wrcfg(ALU_FORMAT_SPEC_REG, {
    .SrcA_val_format = INT8,           // 4'he
    .SrcB_val_format = INT8,
    .Dstacc          = INT32,          // 4'h8
    .SrcA_unsigned   = 0,              // signed INT8 (set 1 for UINT8)
});
wrcfg(ALU_ACC_CTRL, {
    .INT8_math_enabled = 1,            // CRITICAL: enables packed INT8 mode
    .Fp32_enabled      = 1,            // INT32 DEST
});

// TRISC1: MOP
wrcfg(MOP_CFG_LOOP0_LEN, k_tiles - 1);
issue_instrn(MOP, {DOTPV});

// TRISC2: Packer — INT32 → INT8 with descale
wrcfg(THCON_PACKER0_2, {
    .INT_DESCALE_ENABLE = 1,
    .INT_DESCALE_MODE   = 1,           // arithmetic right shift
    .INT_DESCALE_AMOUNT = 8,           // >> 8 maps INT32 product range → INT8
});
wrcfg(THCON_PACKER0_0, {
    .IN_DATA_FORMAT  = INT32,
    .OUT_DATA_FORMAT = INT8,
    .RELU_MODE       = relu_en,        // 1 = zero negative (hardware ReLU, free)
});
issue_instrn(MOP, {PACR});
```

### 6.4 INT8 Quantization Scale Management

```c
// Per-tensor quantization (static, for inference):
// Calibrate per-channel weight scale at model prep time.
// Calibrate per-tensor activation scale offline or with running statistics.

// Per-layer scale computation (TRISC0 BRISC side):
float w_scale  = max(abs(W)) / 127.0f;       // weight scale
float a_scale  = max(abs(A)) / 127.0f;       // activation scale
float o_scale  = w_scale * a_scale;           // output scale before descale
int   descale  = (int)floor(log2(K * o_scale / 127.0f)); // INT32 → INT8 shift

// Write to CSR:
wrcfg(THCON_PACKER0_2, {.INT_DESCALE_AMOUNT = descale});

// For MXINT8 (per-block-16 scale, using tt_t6_com_elem_to_mx_convert):
//   Hardware computes block exponent automatically — SW only sets output format.
wrcfg(THCON_PACKER0_0, {.OUT_DATA_FORMAT = MXINT8});
// No INT_DESCALE_AMOUNT needed; block_exp computed per 16 elements in HW.
```

---

## 7. Memory Efficiency — Format-by-Format

### 7.1 L1 Storage Density

```
L1 word = 128-bit = 16 bytes

Elements per 128-bit word:
  FP32:  4 elements  (32-bit each)
  FP16B: 8 elements  (16-bit each)
  INT16: 8 elements  (16-bit each)
  INT8: 16 elements  (8-bit each)
  FP8:  16 elements  (8-bit each)
  BFP4:  ~18 effective (7-bit man + shared exp per 4)

Full L1 (~1.5 MB = 1,572,864 B) capacity:
  FP32:  393,216 elements
  FP16B: 786,432 elements
  INT16: 786,432 elements
  INT8: 1,572,864 elements
  FP8:  1,572,864 elements
```

### 7.2 L1 Layout Strategy per Format

#### FP16B / INT16 layout (same byte budget)

```
L1 region map (1.5 MB total per tile):

 0x000000 ──────────────── 0x100000  (1 MB): Weight shard
           FP16B or INT16 weights for K=4096, N=256 tile shard
           = 4096 × 256 × 2B = 2 MB → need 2 passes if >1 MB

 0x100000 ──────────────── 0x140000  (256 KB): Activation buffer A
           INT16 or FP16B [seq_tile × K] = 128 × 4096 × 2B = 1 MB → tile seq

 0x140000 ──────────────── 0x168000  (160 KB): Output buffer
           INT16 [m_tile × N_local] = 256 × 256 × 2B = 128 KB

 0x168000 ──────────────── 0x17FFFF  (96 KB): KV-cache head slice
           INT16 [seq × d_k/4] = 2048 × 32 × 2B = 128 KB per head

Note: with INT16 weights + INT16 KV-cache per tile, total = ~1.4 MB → fits.
```

#### INT8 layout

```
 0x000000 ──────────────── 0x100000  (1 MB): Weight shard
           INT8 [K × N_local] = 4096 × 1024 × 1B = 4 MB → need 4 passes
           Or: INT8 [K × 256] = 4096 × 256 × 1B = 1 MB → fits in one pass

 0x100000 ──────────────── 0x118000  (96 KB): Activation buffer (INT8)
           INT8 [seq_tile × K] = 64 × 4096 × 1B = 256 KB → 2 sub-tiles

 0x118000 ──────────────── 0x120000  (32 KB): Output INT8
           INT8 [m_tile × N_local] = 256 × 128 × 1B = 32 KB
```

### 7.3 DEST Register Capacity by Format

```
Format          DEST mode    Rows    Cols   Bytes    Notes
─────────────────────────────────────────────────────────────
FP16B input    FP16 DEST    1024    16     32 KB    2 buffers × 512 rows
INT16 input    INT32 DEST    512    16     32 KB    2 buffers × 256 rows
INT8 input     INT32 DEST    512    16     32 KB    Same as INT16
FP32 input     FP32 DEST     512    16     32 KB    Highest precision
```

**Practical implication:** INT16 and INT8 both halve the usable M-dimension capacity vs FP16. Tile M-dimension to ≤ 256 rows when using INT32 accumulator.

### 7.4 NoC Bandwidth per Format

```
NIU AXI bus: 512-bit = 64 bytes per beat

Format     Bytes/element   Elements/beat   Relative BW
─────────────────────────────────────────────────────
FP32       4               16              0.25×
FP16B      2               32              0.5×
INT16      2               32              0.5×
INT8       1               64              1.0× (baseline)
FP8        1               64              1.0×
BFP8       1.125 effective 56.9 effective  0.89× (BW + exp overhead)
MXINT8     1.0625 effective 60 eff         0.94×
```

**Rule:** Always minimize format size before NoC transfer. Pack FP16B → FP8 in packer (hardware, zero cycle overhead) before sending to next tile or DRAM.

---

## 8. Resource Efficiency — MAC / DMA / Processor

### 8.1 FPU MAC Array Utilization

```
Physical MAC array: 4 G-Tiles × (M-Tile rows) × 16 FP Lane columns

Format          Multiplier     MACs/cycle   Note
──────────────────────────────────────────────────────────────────
FP32            tt_fp_mul_raw  256          Full 32-bit
FP16B           tt_fp_mul_raw  256          Partitioned (faster)
TF32            tt_fp_mul_raw  256          —
INT8 (packed)   tt_mul8        512          2 INT8/Booth cell (packed pairs)
INT16           tt_mul16       256          1 full 16×16 per cell
INT32           tt_mul32       256          Largest tree, slowest cycle time

Best throughput: INT8 packed = 512 MACs/cycle
Best precision: FP32 = 256 MACs/cycle at full IEEE float range
Best balance: INT16 = 256 MACs/cycle, signed 16-bit range
```

### 8.2 Effective TOPS Calculation

At 1 GHz ai_clk, per tile:

```
INT8 packed:  512 MACs/cycle × 1 GHz = 0.512 TOPS per tile
              × 12 tiles = 6.144 TOPS total

INT16:        256 MACs/cycle × 1 GHz = 0.256 TOPS per tile
              × 12 tiles = 3.072 TOPS total

FP16B:        256 MACs/cycle × 1 GHz = 0.256 TOPS (TFLOPS) per tile
              × 12 tiles = 3.072 TFLOPS total
```

### 8.3 TDMA Throughput per Format

TDMA unpacker delivers data to SRCA/SRCB; throughput depends on L1 read rate:

```
L1 bus: 128-bit/cycle (one word per cycle, per channel)
TDMA CH0 + CH1 simultaneously → 2 × 128-bit = 256-bit/cycle to FPU registers

Elements loaded per cycle:
  FP16B / INT16:  8 elements per channel = 16 total (CH0 + CH1)
  INT8:          16 elements per channel = 32 total
  FP32:           4 elements per channel =  8 total

SRCA full load time (48 rows × 16 cols):
  FP16B / INT16:  48 × 16 / 16 = 48 cycles
  INT8:           48 × 16 / 32 = 24 cycles  (2× faster)
  FP32:           48 × 16 /  8 = 96 cycles  (2× slower)
```

### 8.4 Processor (TRISC) Load Analysis

| TRISC role | INT16 extra overhead vs FP16B | Source |
|------------|-------------------------------|--------|
| TRISC0 (unpack) | None — same wrcfg count | Format code change only |
| TRISC1 (math) | None — same MOP | `DOTPV` vs `MVMUL` (same issue sequence) |
| TRISC2 (pack) | +2 wrcfg for INT_DESCALE | `THCON_PACKER0_2` extra fields |
| BRISC (DMA) | None | NoC write same size |

**Overhead is negligible:** 2 extra 32-bit CSR writes per tile = 2 cycles TRISC2 setup overhead amortized over thousands of MOP iterations.

### 8.5 SFPU Utilization by Format

SFPU always uses internal FP32 (32-bit lregs) regardless of input format.

```
After INT8/INT16 GEMM → DEST holds INT32:
  Path to SFPU:
    1. tt_dstac_to_mem: INT32 → FP16B (packer descale + float convert)
    2. L1 write: store FP16B intermediate
    3. SFPU LOAD: L1 read → FP16B → lreg FP32
    4. SFPU MAD × N: polynomial evaluation
    5. SFPU STORE: lreg FP32 → DEST FP16B
  Overhead: 2 extra L1 round-trips (≈ 2 × 48 cycles for full DEST)

After FP16B GEMM → DEST holds FP16B:
  SFPU LOAD: DEST[row] → lreg FP32 directly (1 step, no L1 round-trip)
  Much lower overhead — prefer FP16B for layers with non-linear activations.
```

**Recommendation:** For FFN layers with SiLU/GELU activation:
- Use FP16B accumulator for the gate projection (SFPU activation needed)
- Use INT8 for the down projection (no activation, pure GEMM)

### 8.6 Power Ramp FSM Impact

`tt_power_ramp_fsm` (7-state FSM) uses HIP-rotation ballasting to prevent di/dt spikes.
This applies to ALL formats equally — hardware manages transparently.

INT8 packed mode (512 MACs/cycle) draws **2× more switching power** than INT16/FP16 (256 MACs/cycle). Droop detector sensitivity should be tuned accordingly:
- If `o_droop_code` triggers frequently during INT8 bursts, increase `droop_trigger_hold` (CSR in `tt_droop_trigger_detector`) or reduce `INT8_math_enabled` duty cycle.

---

## 9. Overlay Usage Guide per Format

### 9.1 Overlay Architecture Recap (relevant to LLM)

```
tt_overlay_wrapper (inside each Tensix tile)
├── cpu_cluster_wrapper (TTTrinityConfig_DigitalTop, RISC-V hart per tile)
│   └── TTTrinityConfig_RocketTile[*] — core_clk domain
│       Controls: ATT programming, SMN config, kernel binary load
│
├── memory_wrapper
│   ├── L1 D$/I$ (core_clk) — RISC-V instruction/data cache
│   ├── L2 banks (uncore_clk) — tile-local coherence + metadata cache
│   └── context_switch mem (core_clk) — 32×1024 + 8×1024 SRAMs
│       Used for TRISC state save/restore between kernel launches
│
├── smn_wrapper (tt_smn_node_full, uncore_clk + noc_clk_aon)
│   └── 8-range security filter on NoC-initiated L1 writes
│
├── overlay_ext_reg_cdc (uncore↔ai_clk, 4 async FIFOs)
│   └── Bridge: overlay CPU CSR write → Tensix TRISC CSR space
│
├── overlay_niu_reg_cdc (uncore↔noc_clk_aon, 4 async FIFOs)
│   └── Bridge: overlay CPU → NIU register space (ATT, VC config)
│
└── gen_overlay_context_switch[*].overlay_context_switch (core_clk)
    └── TRISC register context save/restore per kernel switch
```

### 9.2 Overlay Role: Kernel Launch (All Formats)

**Sequence (overlay CPU, core_clk / RISC-V):**

```c
// Step 1: Load kernel binary into L1 (via gen_cpu_to_l1 AXI-to-L1 bridge, uncore_clk)
memcpy_to_l1(L1_KERNEL_BRISC,  &brisc_bin,  brisc_size);
memcpy_to_l1(L1_KERNEL_TRISC0, &trisc0_bin, trisc0_size);
memcpy_to_l1(L1_KERNEL_TRISC1, &trisc1_bin, trisc1_size);
memcpy_to_l1(L1_KERNEL_TRISC2, &trisc2_bin, trisc2_size);

// Step 2: Write tensor descriptor to BRISC mailbox in L1
write_mailbox(L1_MAILBOX_ADDR, &tensor_descriptor);
// tensor_descriptor: {l1_weight_base, l1_act_base, m_tiles, k_tiles,
//                     format_code, descale_amount, output_addr, ...}

// Step 3: Configure ATT (via overlay_niu_reg_cdc → NIU register space)
att_config(MASK_TABLE_ENTRY_0, {
    .ep_reg      = DRAM_WEIGHT_BASE + layer_id * layer_stride,
    .mask_reg    = 22,                    // 4MB alignment
    .bar_reg     = L1_WEIGHT_BASE,        // redirect to L1
    .translate   = 1,
});
att_enable(ENABLE_TABLES_REG, ATT_EN=1);

// Step 4: Set SMN access permissions (write-protect output region)
smn_config(range=0, {
    .start = L1_OUTPUT_BASE,
    .end   = L1_OUTPUT_BASE + output_size,
    .wr_sec_level = 2,                    // only DMA engine can write
    .rd_sec_level = 0,                    // anyone can read
    .range_enable = 1,
});

// Step 5: Release TRISC reset (via overlay_ext_reg_cdc → ai_clk domain)
set_tensix_reset_n(tile_x, tile_y, 1);   // all 4 TRISCs start executing
```

### 9.3 Overlay Role: Format-Specific Configuration

#### INT16 (KV-cache + attention)

```c
// Overlay CPU programs ATT for K/V tensor sharding:
// Head h lands on tile X = h % 4  (tensor parallel across X axis)

for (int h = 0; h < num_kv_heads; h++) {
    int tile_x = h % 4;
    att_config(MASK_TABLE_ENTRY_0 + h, {
        .ep_reg   = KV_DRAM_BASE + h * kv_head_size,
        .mask_reg = log2(kv_head_size),
        .bar_reg  = L1_KV_BASE[tile_x],
        .translate = 1,
    });
}
// NOTE: ATT supports only 16 mask entries; with 32 KV heads and 4 tiles,
// each tile sees 8 heads → 8 entries needed per tile → fits in 16.
```

#### FP16B (residual stream, norm layers)

```c
// For RMSNorm via SFPU: no special ATT needed.
// Overlay CPU programs tensor counters for norm sequencing:
write_reg(OVERLAY_TILE_COUNTERS, norm_seq_len / 16);  // 16 elements per SFPU pass

// Context switch between GEMM kernel and norm kernel:
// overlay_context_switch saves TRISC1 register state (MOP config)
// before switching to norm kernel, restores after.
context_switch_save(TRISC1_CTX, gen_cs_32x1024[0]);
load_kernel(L1_NORM_KERNEL_TRISC1, &norm_trisc1_bin);
// ... execute norm ...
context_switch_restore(TRISC1_CTX, gen_cs_32x1024[0]);
```

#### INT8 (weight-stationary FFN)

```c
// Pre-load all FFN weights at layer start (weight-stationary):
// NIU DMA (BRISC-initiated NoC read from DRAM):
noc_read_dma(
    src = DRAM_FFN_WEIGHT_BASE + layer * ffn_weight_stride,
    dst = L1_WEIGHT_BASE,
    len = K * N_local * sizeof(int8_t)   // one tile's column shard
);
// After DMA: activate INT8_math_enabled, loop over all token tiles.
// Weights never leave L1 for the full layer — 0 DRAM traffic during compute.

// SMN: lock weight region against all NoC writes during compute
smn_config(range=1, {
    .start = L1_WEIGHT_BASE,
    .end   = L1_WEIGHT_BASE + K * N_local,
    .wr_sec_level = 15,   // maximum: no writes allowed
    .rd_sec_level = 0,
    .range_enable = 1,
});
```

### 9.4 Overlay Clock Domain Considerations

| Action | Clock path | Latency |
|--------|-----------|---------|
| TRISC wrcfg (CSR write) | ai_clk → (pass-through) → Tensix CSR | ~1 cycle |
| Overlay CPU → TRISC CSR | core_clk → overlay_ext_reg_cdc → ai_clk | 4–8 cycles CDC |
| ATT programming | core_clk → overlay_niu_reg_cdc → noc_clk_aon → NIU regs | ~10 cycles |
| Kernel binary load (AXI-to-L1) | uncore_clk → l1_req CDC → ai_clk → L1 | ~20 cycles/word |

**Important:** `overlay_ext_reg_cdc` has 4 async FIFOs of depth 8 each (from overlay_hierarchy.csv lines 106–109). Do not issue more than 8 consecutive wrcfg from the overlay CPU without waiting for a response — the CDC FIFO can fill. TRISC firmware can issue wrcfg directly (ai_clk, no CDC) for best throughput.

---

## 10. NoC / NIU Data Movement Guide

### 10.1 Unicast: Tile-to-Tile Activation Transfer

Used to pass activations between pipeline stages (Y-row to Y-row).

```c
// BRISC code to send INT16 output tile to next pipeline stage:
void noc_send_int16_tile(uint32_t dst_x, uint32_t dst_y,
                         uint32_t src_l1, uint32_t dst_l1,
                         uint32_t rows, uint32_t cols) {
    uint32_t bytes = rows * cols * sizeof(int16_t);

    // Program NIU inject registers (base 0x02000000):
    wr32(TARGET_ADDR_LO,  dst_l1 & 0xFFFFFFFF);
    wr32(TARGET_ADDR_MID, dst_l1 >> 32);
    wr32(TARGET_ADDR_HI,  (dst_y << 8) | (dst_x << 2));
    //   ^^^^^^ TARG_ADDR_HI[13:8]=y_coord, [7:2]=x_coord
    wr32(RET_ADDR_LO,  src_l1 & 0xFFFFFFFF);  // return addr for response
    wr32(RET_ADDR_MID, src_l1 >> 32);
    wr32(CMD_BRCST, CMD_RW_BIT | (VC_UNICAST_0 << 14));  // write, VC 0
    wr32(AT_LEN,    bytes);
    wr32(CMD_CTRL,  1);  // submit

    // Wait for ack (poll CMD_CTRL until 0, or use semaphore):
    while (rd32(CMD_CTRL) != 0);
}
```

### 10.2 Broadcast: Weight Distribution to All Compute Rows

When the same weight shard is needed by all 3 compute rows (Y=0,1,2) for the same X column:

```c
// Send weight shard from NIU (Y=4, X=k) to all compute tiles in column k:
wr32(TARGET_ADDR_HI,
    (2 << 8) |    // y_coord = Y=2 (end of broadcast rectangle)
    (x << 2));    // x_coord = column k
wr32(TARG_ADDR_HI_BC_START,
    (0 << 20) |   // bc_start_y = Y=0
    (x << 14));   // bc_start_x = column k (same column — column broadcast)
wr32(CMD_BRCST, CMD_RW_BIT | CMD_BRCST_BIT | BRCST_XY_BIT=0);
// brcst_xy_bit=0 → Y-then-X (rows in same column), bc_start=(x,0), end=(x,2)
// Delivers to (x,0), (x,1), (x,2) in one NoC transaction
wr32(CMD_CTRL, 1);
```

### 10.3 Dynamic Routing: Multi-Head Attention Scatter

For sending KV slices to multiple head-tiles simultaneously:

```c
// Pre-compute 928-bit carried list (SW, once per layer):
// Each slot[y * noc_x_size + x] = 5-bit port direction
uint8_t routing_list[DYNAMIC_ROUTING_LIST_WIDTH / 8];  // 116 bytes

// For sending K-cache slice to tiles (0,1), (1,1), (2,1), (3,1):
for (int x = 0; x < 4; x++) {
    int slot = 1 * noc_x_size + x;  // y=1, x=0..3
    set_slot(routing_list, slot, PORT_NIU);    // deliver to local NIU
}
// Route from NIU(0,4): use X+ direction to traverse x=0→3
set_slot(routing_list, 4*0+4, PORT_X_PLUS);   // at (0,4): go X+
set_slot(routing_list, 4*1+4, PORT_X_PLUS);   // at (1,4): go X+
set_slot(routing_list, 4*2+4, PORT_X_PLUS);   // at (2,4): go X+
set_slot(routing_list, 4*3+4, PORT_NIU);       // at (3,4): terminate

// Program ATT dynamic routing table (base 0x02010000 + 0x0300):
att_write_routing_table(entry=0, routing_list, 928);
att_write_match_key(entry=0, {ep_idx=KV_HEAD_EP_IDX, vc=VC_UNICAST_0});
att_enable(ENABLE_TABLES_REG, ATT_EN=1 | DYN_ROUTING_EN=1);
```

### 10.4 DRAM Weight Streaming via NIU

```
Weight load pattern (INT8, weight-stationary):

Cycle 0: BRISC issues noc_read(DRAM_W_BASE, L1_W_BASE, K*N_local)
  → NIU TLB lookup: src addr in AXI2NOC TLB range?
  → Yes: NOC2AXI at (X, Y=4) issues AXI read to DRAM
  → AXI outstanding reads: up to 16 outstanding (AXI_MST_OUTSTANDING_READS=16)
  → Each beat: 512-bit = 64 bytes = 64 INT8 elements

Cycle 1..N: DRAM bursts return, NOC2AXI bridges → NoC flits
  → Flit traversal: DOR Y- direction: (X,4) → (X,3) → (X,2/1/0)
  → Delivered to L1 write port (flex_client_wr_port, ai_clk domain)

Overlap: BRISC can pre-fetch next layer's weights (L1 double-buffer for weights)
  while TRISC1 computes using current-layer weights.
  L1 double-buffer weight layout:
    W_BANK_A: 0x000000 – 0x0FFFFF  (current layer)
    W_BANK_B: 0x100000 – 0x17FFFF  (prefetch next layer, if fits)
```

---

## 11. Register Programming Reference

### 11.1 Format Code Quick Reference

| Format | Code | CSR value | Notes |
|--------|------|-----------|-------|
| FP32 | 4'h0 | 0x0 | Full IEEE float |
| FP16A (half) | 4'h1 | 0x1 | exp=5, man=10, bias=15 |
| FP16B (BF16) | 4'h5 | 0x5 | exp=8, man=7, bias=127 |
| INT32 | 4'h8 | 0x8 | 32-bit signed accumulator |
| INT16 | 4'h9 | 0x9 | 16-bit signed |
| INT8  | 4'he | 0xe | 8-bit signed |
| TF32  | 4'h4 | 0x4 | exp=8, man=10 |

### 11.2 Key CSR Map

| CSR | Offset | Fields | Description |
|-----|--------|--------|-------------|
| ALU_FORMAT_SPEC_REG | 0x1E0 | [3:0]=SrcA, [7:4]=SrcB, [11:8]=Dstacc | Format per operand |
| ALU_ACC_CTRL | 0x1E4 | [0]=Fp32_en, [1]=INT8_math_en | Accumulator mode |
| ALU_ROUNDING_MODE | 0x1E8 | [0]=srnd_en | Stochastic rounding |
| DEST_REGW_BASE | 0x1F0 | [9:0]=row | DEST write base |
| DEST_SP_BASE | 0x1F4 | [9:0]=row | Secondary (ping-pong) base |
| THCON_UNPACKER0_0 | 0x200 | [3:0]=IN_FMT, [7:4]=OUT_FMT, [27:8]=addr | Unpacker CH0 config |
| THCON_UNPACKER1_0 | 0x250 | same | Unpacker CH1 config |
| THCON_PACKER0_0 | 0x300 | [3:0]=IN_FMT, [7:4]=OUT_FMT, [11:8]=RELU | Packer CH0 config |
| THCON_PACKER0_2 | 0x308 | [0]=DESCALE_EN, [1]=MODE, [6:2]=AMOUNT | INT descale |
| THCON_PACKER0_3 | 0x30C | [1:0]=RELU_MODE | Packer ReLU mode |
| MOP_CFG_LOOP0_LEN | 0x400 | [15:0]=count | Inner loop count |
| MOP_CFG_LOOP1_LEN | 0x404 | [15:0]=count | Outer loop count |
| MOP_CFG_ZMASK_LO | 0x408 | [31:0] | Z-plane sparsity mask low |
| MOP_CFG_ZMASK_HI | 0x40C | [31:0] | Z-plane sparsity mask high |

### 11.3 NIU Inject Registers (base 0x02000000)

| Register | Offset | Bit fields |
|----------|--------|------------|
| TARGET_ADDR_LO | 0x00 | targ_addr[31:0] |
| TARGET_ADDR_MID | 0x04 | targ_addr[63:32] |
| TARGET_ADDR_HI | 0x08 | [13:8]=y_coord, [7:2]=x_coord |
| RET_ADDR_LO | 0x0C | ret_addr[31:0] |
| CMD_BRCST | 0x1C | [1]=rw_bit, [6]=brcst_bit, [17:14]=vc |
| AT_LEN | 0x20 | transfer size (bytes) [31:0] |
| CMD_CTRL | 0x40 | [0]=submit, poll=0 when done |

### 11.4 ATT Register Map (base 0x02010000)

| Register | Offset | Description |
|----------|--------|-------------|
| ENABLE_TABLES_REG | 0x0000 | [0]=ATT_en, [1]=dyn_routing_en |
| MASK_TABLE_ENTRY_k | 0x0030 + k×0x18 | 16 entries, stride 24B |
| ROUTING_TABLE_MATCH_k | 0x0200 + k×4 | 32 entries, match key {ep_idx, vc} |
| ROUTING_TABLE_PART_ENTRY_k | 0x0300 + k×128 | 1024-bit bitmask, 32×32b words |
| ENDPOINT_TABLE_k | 0x2000 + k×16 | 1024 entries: dest_x(6b), dest_y(6b), addr(64b) |

---

## 12. LLaMA 3.1 8B End-to-End Mapping

### 12.1 Layer Assignment to Tile Rows

```
Trinity chip: 4×3 compute tiles (X=0..3, Y=0..2)

Layer assignment (pipeline parallelism across 3 rows):
  Y=0 row (4 tiles): Layers 0..10  — Attention GEMM (QKV + O proj)
  Y=1 row (4 tiles): Layers 11..21 — FFN (gate, up, down projections)
  Y=2 row (4 tiles): Layers 22..31 — Mixed: Attention + FFN + norms

Within each row: Tensor parallelism across 4 X columns
  X=0: N columns 0..N/4-1    X=1: N columns N/4..N/2-1
  X=2: N columns N/2..3N/4-1 X=3: N columns 3N/4..N-1
```

### 12.2 Per-Layer Operation Schedule

```
For each transformer layer (one Y-row):

Time  0:  Overlay CPU → kernel load → BRISC mailbox write → release TRISC reset
Time  1:  BRISC NoC DMA: read INT8 weight shard from DRAM via NIU(X, Y=4) → L1
Time  2:  TRISC0: unpack INT8 weights → SRCA
          TRISC0: unpack INT8 activations → SRCB
Time  3:  TRISC1: INT8 GEMM MOP (DOTPV, K-loop) → INT32 DEST
          [concurrent] TRISC0: unpack next weight tile
Time  4:  TRISC1: complete K-loop → sem_post(MATH_DONE)
          TRISC2: INT32 → INT8 descale + pack → L1 output buffer
Time  5:  For projection with activation (SiLU):
          TRISC1: SFPU LOAD INT32→FP32 lreg → SFPMAD (SiLU polynomial) → SFPSTORE
          [then pack to INT8 for NoC]
Time  6:  BRISC: NoC unicast INT8 output to next Y-row tile (Y-direction)
          [concurrent] TRISC1: start next M-tile GEMM (DEST double-buffer)
```

### 12.3 KV-Cache Handling (INT16)

```
Attention tile (X, Y=0 for layer group 0):

Setup:
  L1[0x000000..0x07FFFF]: K-cache INT16 [2048 × 128]  = 512 KB
  L1[0x080000..0x0FFFFF]: V-cache INT16 [2048 × 128]  = 512 KB
  L1[0x100000..0x10FFFF]: Q buffer  INT16 [seq_t × 128] = variable
  L1[0x110000..0x11FFFF]: Attention score FP16B [seq_t × 2048] = variable

Compute loop:
  for each query token tile (seq_t):
    TRISC0 unpack Q → SRCB (INT16)
    for each KV tile (k_t in 2048):
      TRISC0 unpack K[k_t] → SRCA (INT16)
      TRISC1 DOTPV: INT16×INT16 → INT32 → score[k_t]
    TRISC2 descale INT32 → FP16B (for softmax range)
    TRISC1 SFPU softmax on FP16B scores
    for each V tile:
      TRISC0 unpack V[k_t] → SRCA (INT16)
      TRISC0 unpack softmax[k_t] → SRCB (FP16B)
      TRISC1 MVMUL: FP16B × INT16 → FP16B output
```

### 12.4 All-Reduce After Tensor-Parallel GEMM

After each tile computes its partial sum (one column shard), results must be summed across X:

```
Simple ring-reduce for 4 tiles (X=0..3):
  Step 1: X=0 sends partial[0] → X=1 (NoC unicast X+)
  Step 2: X=1 adds partial[0]+partial[1] → X=2
  Step 3: X=2 adds partial[0..1]+partial[2] → X=3
  Step 4: X=3 broadcasts final sum → X=0,1,2 (NoC broadcast)

Hardware support: use cmd_brcst_bit=1 for step 4.
Format: keep partial sums as INT32 during reduce, descale to INT8 at final step.
Latency: 3 unicast + 1 broadcast = 4 NoC hops × ~10 ns/hop = ~40 ns
```

---

## 13. Summary Comparison Table

| Dimension | FP16B (BF16) | INT16 | INT8 |
|-----------|-------------|-------|------|
| Format code | 4'h5 | 4'h9 | 4'he |
| Bits/element | 16 | 16 | 8 |
| L1 density | 8 elem/word | 8 elem/word | 16 elem/word |
| DEST mode | FP16 (1024 rows) | INT32 (512 rows) | INT32 (512 rows) |
| MACs/cycle | 256 | 256 | 512 (packed) |
| Effective TOPS/tile | 0.256 | 0.256 | 0.512 |
| NoC BW efficiency | 0.5× | 0.5× | 1.0× |
| TDMA feed rate | 16 elem/cycle | 16 elem/cycle | 32 elem/cycle |
| Stochastic rounding | Yes (PRNG LFSR) | No | No |
| SFPU overhead | None | +2 L1 round-trips | +2 L1 round-trips |
| Packer descale | Not needed | INT_DESCALE required | INT_DESCALE required |
| Best use case | Norm, attn, train | KV-cache, mid-precision | FFN weights, inference |
| Accumulator overflow risk | Low (FP16 saturation) | Medium (INT32 wide) | Low (INT32 wide) |
| Quantization calibration | None | Per-tensor scale | Per-channel scale |
| Overlay CPU overhead | Minimal | +ATT per-head config | +weight pre-load DMA |

---

## 14. Future Work

### 14.1 INT4 / MXFP4 Weight Quantization

`tt_t6_com_elem_to_mx_convert` supports MXFP4 (E2M1):

```
MXFP4: 1-bit mantissa + shared block exponent per 16 elements
Storage: 16 elements × 0.5 B/elem + 1 B block_exp = 9 B per 16 → 0.5625 B/elem
vs INT8: 1.0 B/elem → 1.78× further compression

Expected accuracy loss (LLaMA 8B): ~0.5–1 ppl degradation vs INT8
Recommended: MXFP4 for FFN layer 2 (down projection) only; keep QKV at INT8.
```

### 14.2 BFP8 Inter-Tile Activation Compression

Pack activations as BFP8 (block FP8: shared exp per 8 elements + 7-bit mantissa):

```
FP16B → BFP8 via tt_dstac_to_mem assemble_exp_word():
  16 elements → 16 × 1 B mantissa + 2 × 1 B block_exp = 18 B
  vs FP16B: 16 × 2 B = 32 B
  NoC bandwidth reduction: 44%

SW note: receiver must dequantize BFP8 → FP16B before SFPU norm.
         Cost: 1 extra TDMA pass (unpacker fmt_conv handles BFP8 → FP16B natively).
```

### 14.3 Speculative Decoding via Multi-Tile Parallelism

Use spare compute capacity (when not all 12 tiles busy) to run draft model (smaller LLM):

```
Compute-C (Y=2): runs LLaMA 1B draft model at INT8
Compute-A/B:     runs LLaMA 8B target model verification at INT16
Dispatch tiles:  compare draft tokens → accept/reject → re-run on mismatch
```

No hardware changes needed — purely a software scheduling decision in overlay CPU.

### 14.4 Hardware Limitations to Resolve

| Limitation | Impact | Workaround |
|------------|--------|------------|
| INT16 DEST = 512 rows (vs 1024 for FP16) | Halves M-tile capacity | Tile M in 256-row chunks |
| No SFPU direct INT16 path | +2 L1 passes for activation | Use FP16B packer output before SFPU |
| ATT: 16 mask entries only | Limited head-to-tile mapping flexibility | Share mask entries with stride alignment |
| INT16 no stochastic rounding | Deterministic quantization bias | Add software dither in TRISC2 |
| Power: INT8 packed = 2× switching | Droop detector may throttle | Tune droop_trigger_hold, monitor droop_code |

---

*End of Document — INT16_Guide_HDD_V0.1 — 2026-03-18*

---

## 15. Memory Traffic Improvement Guide — HW Configuration View

This chapter describes the **fixed hardware parameters** that bound memory traffic performance.
Understanding these limits is prerequisite to any SW-level optimization.
Sources: `tt_noc2axi.sv` L75-82, `tt_noc2axi_pkg.sv` L68-70, `tt_noc_pkg.sv` L119-121 / L623-624.

---

### 15.1 AXI Bus Parameters per NIU

Each NIU tile (Y=4) instantiates one `tt_noc2axi`. The parameters below are set at elaboration
time in `trinity_noc2axi_n/ne/nw_opt.sv` and cannot be changed at runtime.

#### 15.1.1 Max Outstanding (MO) Transactions

| Direction | Parameter | Value | Description |
|-----------|-----------|-------|-------------|
| NOC→AXI read  | `AXI_SLV_OUTSTANDING_READS`  | **64** | Max simultaneous read txns, Tensix/DM → DRAM |
| NOC→AXI write | `AXI_SLV_OUTSTANDING_WRITES` | **32** | Max simultaneous write txns → DRAM |
| AXI→NOC read  | `AXI_MST_OUTSTANDING_READS`  | **16** | Max in-flight reads, external host → L1 |
| AXI→NOC write | `AXI_MST_OUTSTANDING_WRITES` | **32** | Max in-flight writes, external host → L1 |

The slave-side MO (64R / 32W) is larger than master-side because Tensix cores issue many
concurrent memory requests, while the external AXI host is a single-initiator.

#### 15.1.2 AXI Burst Length

| Parameter | Value | Notes |
|-----------|-------|-------|
| `AXI_MAX_LEN` | 256 beats | Maximum AxLEN field (8-bit) |
| `AXI_MAX_TRANSACTION_SIZE` | **4096 B** | HW hard cap — splits at every 4 KB boundary |
| AXI data width | 512 b = **64 B/beat** | One beat = one NoC payload sector |
| Effective max burst | **64 beats = 4 KB** | HW clamps regardless of AxLEN value |

The 4 KB cap is enforced inside `tt_noc2axi_pkg.sv:70`. Transfers larger than 4 KB are
automatically split into multiple 4 KB AXI transactions by the NIU.

---

### 15.2 Buffer Sizes and Their Hard Limits

#### 15.2.1 Slave Read Data Return FIFO (`tt_noc2axi_slv_rd.sv:49-51`)

```
RDATA_FIFO_DEPTH = min(AXI_MAX_LEN=256, AXI_MAX_TRANSACTION_SIZE/64B=64) = 64 beats
RDATA_FIFO_WIDTH = 1 + RESP_VC_CNT_WIDTH(2) + 1 + AXI_DATA_WIDTH(512) = 516 bits
Total FIFO size  = 64 × 516 b ≈ 4 KB
SRAM instance:   tt_mem_wrap_64x516_2p_noc2axi_slv_rddata
```

Absorbs exactly one full 4 KB read burst return per response VC.
4 resp VCs → 4 independent FIFOs → 4 concurrent burst drains possible.

#### 15.2.2 Master Write Data Buffer (`tt_noc2axi_mst_wr.sv:51-54`)

```
AXI_WDATA_BUF_TRANSACTIONS = 4
AXI_WDATA_BUF_WORDS        = 4 × 4096 / (2048b/8) = 64 NOC flits
SRAM macro selected        : 16 KB  (< 8-transaction threshold → 6-bit address)
```

The 5th AWVALID stalls until one of the 4 buffer slots frees.
Increasing to 8 transactions scales the SRAM to 32 KB (next macro tier).

#### 15.2.3 Master Read Data Buffer (`tt_noc2axi_mst_rd.sv:37-43`)

```
AXI_MST_RD_BUFFER_SIZE_IN_KB = 16 KB
AXI_RDATA_BUF_WORDS          = 16 × 1024 / 256 = 64 NoC flits
SRAM macro: 16 KB (6-bit address)
```

All in-flight read data from the NoC lands here before forwarding to the AXI master.
When full, `i_cfg_mst_rd_mem_full_thresh` triggers back-pressure on NoC read injection.

---

### 15.3 Virtual Channel (VC) Structure and NoC Bottleneck

#### 15.3.1 VC Allocation (`tt_soc_noc_pkg.sv:16`, `tt_noc_pkg.sv:119-121`)

```
NUM_VCS = 16

  VC  0..7   (8)  Unicast request    — Tensix→Tensix / Tensix→NIU writes
  VC  8..11  (4)  Broadcast request  — weight multicast
  VC 12..15  (4)  Response           — DRAM read returns, write ACKs (HW-assigned)
```

#### 15.3.2 Router VC Input Buffer (`tt_noc_pkg.sv:623-624`)

```
ROUTER_REMOTE_INPUT_BUF_SIZE             = 64 flits  (total per router port)
ROUTER_REMOTE_INPUT_BUF_MAX_FLITS_PER_VC = 16 flits  (per individual VC)
```

This is the **primary NoC bottleneck for large burst transfers:**

```
One 4 KB DRAM read = 4096 B / 256 B per NoC flit = 16 flits
→ Fills exactly one VC's entire per-VC buffer quota

4 response VCs × 16 flits/VC = 64 flits total
→ Maximum 4 concurrent 4 KB reads in-flight per NIU at any time
```

Even though AXI slave MO = 64 reads, only **4 full-size (4 KB) responses** can travel
the NoC simultaneously. Smaller reads (e.g. 256 B = 1 flit) allow up to 64 concurrent.

#### 15.3.3 AXI ID Encodes VC (`tt_noc2axi_pkg.sv:47`)

```
NOC2AXI_ID_WIDTH = VC_CNT_WIDTH = 4 bits
```

AXI RID/BID carries the VC ID. The downstream memory controller must support
**at least 16 unique AXI IDs** to avoid collapsing 64 outstanding reads into a single
in-order response queue.

---

### 15.4 HW Configuration Impact Summary

| HW Parameter | Value | Bottleneck Created | SW Mitigation |
|---|---|---|---|
| `AXI_SLV_OUTSTANDING_READS` | 64 | Not a bottleneck if NoC is | Issue ≥ 4 concurrent 4 KB reads |
| `AXI_MAX_TRANSACTION_SIZE` | 4 KB | Transfer splits on misaligned src/dst | 4 KB-align all DMA requests |
| `RDATA_FIFO_DEPTH` | 64 beats | 1 burst buffered per VC | Spread reads across VCs |
| `AXI_WDATA_BUF_TRANSACTIONS` | 4 | 5th write stalls AWVALID | Fence every 4 writes (AXI master) |
| `NUM_RESP_VCS` | 4 | 4 concurrent 4 KB reads max — true NoC ceiling | Use smaller reads for higher concurrency |
| `ROUTER_REMOTE_INPUT_BUF_MAX_FLITS_PER_VC` | 16 | Head-of-line block on one VC | Avoid VC monopoly; separate traffic classes |

---

## 16. Memory Traffic Improvement Guide — SW Operation View

This chapter provides software patterns for BRISC / overlay CPU to fully utilize
the HW capacity characterized in §15.

---

### 16.1 Rule 1 — Align Transfers and Saturate All 4 Resp VCs

**Alignment:** Both `src` DRAM address and `dst` L1 address must be 64-byte aligned.
Size all DMA chunks to multiples of 4 KB.

```c
// BAD: 3 KB → AxLEN=47 (partial burst), wastes AXI pipeline capacity
noc_read_dma(DRAM_BASE, L1_BASE, 3 * 1024);

// GOOD: pad tensor dimensions to 4 KB multiples at model-prep time
//   K=3000, N_local=48, INT8 → pad K to 4096 → 196608 B = 48 × 4096 → 48 full bursts
noc_read_dma(DRAM_BASE, L1_BASE, 4 * 1024);
```

**Saturate 4 resp VCs:** Issue 4 concurrent 4 KB requests before polling:

```c
// Fills all 4 resp VC slots simultaneously — maximum NoC bandwidth utilization
for (int i = 0; i < 4; i++)
    noc_read_dma_async(DRAM_W + i * 4096, L1_W + i * 4096, 4096);
noc_dma_wait_all();

// For large tensors (e.g. 1 MB weight shard = 256 × 4 KB):
for (int grp = 0; grp < 64; grp++) {       // 64 groups × 4 requests = 256 total
    for (int i = 0; i < 4; i++)
        noc_read_dma_async(DRAM_W + (grp*4+i)*4096, L1_W + (grp*4+i)*4096, 4096);
    noc_dma_wait_all();
}
```

---

### 16.2 Rule 2 — Weight-Stationary Double-Buffer Prefetch

Hide DRAM latency by overlapping next layer's weight load with current GEMM compute.

```
L1 layout:
  0x000000 – 0x0FFFFF  (1 MB): weight bank A  ← TRISC1 computes here
  0x100000 – 0x1FFFFF  (1 MB): weight bank B  ← BRISC prefetches next layer here
```

```c
uint32_t active = 0;
const uint32_t l1_banks[2] = { L1_BANK_A, L1_BANK_B };

for (int layer = 0; layer < num_layers; layer++) {

    // Prefetch next layer into idle bank (non-blocking, in groups of 4)
    if (layer + 1 < num_layers)
        noc_read_dma_4vc_async(DRAM_W + (layer+1)*w_stride,
                               l1_banks[!active], w_size);

    // Signal TRISC to start compute on active bank
    wr32(L1_MAILBOX, l1_banks[active]);
    sem_post(SEM_MATH_START);

    // Wait for both prefetch and compute to finish
    noc_dma_wait_all();
    sem_wait(SEM_MATH_DONE);

    active = !active;    // swap banks
}
```

**Benefit:** For INT8 FFN, K=4096, N_local=256 (1 MB weight), GEMM compute >> DRAM latency
→ zero DRAM stall cycles during compute with double-buffer in place.

---

### 16.3 Rule 3 — VC Assignment per Traffic Class

Mixing long-latency DRAM reads and short tile-to-tile writes on the same VC causes
head-of-line blocking. Assign each traffic class to a dedicated VC.

```c
#define VC_WEIGHT_DMA   0   // long streaming DRAM → L1
#define VC_ACT_UNICAST  1   // short latency tile-to-tile activations
#define VC_ALL_REDUCE   2   // time-critical reduce sync
#define VC_BCAST_WEIGHT 8   // broadcast req VCs only (VC 8..11)

// Activation unicast send:
wr32(CMD_BRCST, CMD_RW_BIT | (VC_ACT_UNICAST << 14));

// Weight broadcast to column (one NIU → all Y-row tiles):
wr32(CMD_BRCST, CMD_RW_BIT | CMD_BRCST_BIT | (VC_BCAST_WEIGHT << 14));

// DRAM weight DMA via ATT static VC override:
att_config_static_vc(entry=0, vc=VC_WEIGHT_DMA);
```

**Why this matters:** VC_WEIGHT_DMA carries 16-flit (4 KB) bursts. If VC_ACT_UNICAST
shared the same VC, short activation sends would wait behind each full burst —
multiplying activation latency by up to 16×.

---

### 16.4 Rule 4 — AXI Master Write Fence Every 4 Transactions

For external host (PCIe DMA, test-bench) writing to Tensix L1 via NIU AXI master port.
HW write buffer holds only 4 transactions; the 5th AWVALID stalls.

```c
#define NIU_WR_BUF_DEPTH 4

void host_write_l1(uint64_t l1_base, void *src, size_t total_bytes) {
    int n = total_bytes / 4096;
    for (int i = 0; i < n; i++) {
        axi_write(l1_base + i*4096, src + i*4096, 4096);
        if ((i % NIU_WR_BUF_DEPTH) == (NIU_WR_BUF_DEPTH - 1))
            axi_write_fence();     // drain 4 BRESPs before issuing next group
    }
    axi_write_fence();             // final drain
}
```

For BRISC→peer tile NoC writes: NoC VC flow-control handles back-pressure automatically
(`ROUTER_REMOTE_INPUT_BUF_SIZE = 64 flits`). No explicit fence needed from BRISC.

---

### 16.5 Rule 5 — KV-Cache Traffic Reduction

KV-cache is the dominant DRAM bandwidth consumer for long-context inference.

#### Short context (seq ≤ 1024) — keep KV fully in L1

```
INT16 KV, seq=1024, d_k=128 per head group:
  K-cache = V-cache = 1024 × 128 × 2B = 256 KB each → 512 KB total
  L1 = 1.5 MB → fully resident, zero DRAM reads during attention forward
```

#### Long context (seq > 1024) — tile sequence with double-buffer prefetch

```c
for (int slab = 0; slab < seq / 1024; slab++) {
    if (slab + 1 < seq / 1024)
        noc_read_dma_4vc_async(KV_DRAM + (slab+1)*kv_slab_size,
                               L1_KV_IDLE, kv_slab_size);
    compute_attention_slab(L1_KV_ACTIVE, slab);
    noc_dma_wait_all();
    swap(L1_KV_ACTIVE, L1_KV_IDLE);
}
```

#### INT8 KV quantization for seq > 2048 — 2× DRAM BW saving

```c
// Pre-quantize at KV write time: per-head per-token FP16B scale (negligible overhead)
// At read time: unpack INT8 → SRCA, apply scale via SFPU MAD before GEMM
wrcfg(THCON_UNPACKER0_0, {.IN_DATA_FORMAT=INT8, .OUT_DATA_FORMAT=INT8});
// Scale application cost: ~48 SFPU cycles per head tile
// Net: 2× DRAM BW reduction vs < 5% compute overhead → strongly preferred for seq > 2048
```

---

### 16.6 Rule 6 — Stagger NIU DMA Starts; Prefer Broadcast for Shared Weights

All 4 NIUs share one AXI interconnect. Simultaneous burst starts cause arbitration stalls.

```c
// Dispatch 4 NIU DMAs in sequence — natural stagger fills AXI pipeline without collision
for (int x = 0; x < 4; x++)
    noc_write_to_niu(x, NIU_DMA_START,
                     DRAM_W + x*w_local_size, L1_W_BASE, w_local_size);
    // No fence — staggered issue; collect completions below
for (int x = 0; x < 4; x++)
    noc_wait_niu_dma(x);
```

**Broadcast weight alternative (4× DRAM BW saving when all columns need identical data):**

```c
// One NIU reads from DRAM once; NoC broadcast delivers to all X columns
wr32(TARGET_ADDR_HI,        (Y_END   << 8) | (X_START << 2));
wr32(TARG_ADDR_HI_BC_START, (Y_START << 20) | (X_START << 14));
wr32(CMD_BRCST, CMD_RW_BIT | CMD_BRCST_BIT | (VC_BCAST_WEIGHT << 14));
wr32(CMD_CTRL, 1);
// Delivers to (X=0..3, Y=target_row) in one DRAM read — 4× bandwidth saving vs 4 unicasts
```

---

### 16.7 Rule 7 — L1 Bank Conflict Avoidance

L1 has 16 banks; bank index = `addr[7:4]` for 128-bit word addressing.
TDMA CH0 (weights) and CH1 (activations) run concurrently.

```
Conflict-free layout:
  Weight base:     0x000000   → starts at bank 0
  Activation base: 0x100080   → +1 MB + 128 B stagger → starts at bank 8

  CH0 bank access sequence: 0,  1,  2,  ..., 15, 0, ...
  CH1 bank access sequence: 8,  9, 10,  ..., 15, 0, ..., 7

  → 8-bank separation (maximum possible in a 16-bank ring)
  → No same-cycle bank collision for any stride-1 sequential access pattern
```

The +128 B stagger (`0x80` offset) ensures CH0 and CH1 are always at opposite bank halves.
For INT8, where 16 elements pack into one 128-bit word, this alignment also ensures
each SFPU input group spans distinct banks — zero serialization overhead.

---

### 16.8 Performance Diagnosis Checklist

```
Step 1: Check DRAM MO saturation
  → Read noc2axi_perf_monitor.sv MAX_OUTSTANDING_TXN counter
  → Peak < 4?  → SW not issuing enough concurrent DMAs  → fix: Rule 1 (group-of-4)
  → Peak = 4, BW still low?  → NoC resp VC buffer is the bottleneck  → Step 2

Step 2: Check NoC VC buffer pressure
  → Monitor per-VC pop-count (o_req_head_flit_vc_popcount in tt_noc_overlay_intf)
  → One VC credit stuck at 0 while others non-zero?  → head-of-line block
  → Fix: Rule 3 (VC class separation) + Rule 6 (stagger NIU starts)

Step 3: Check TDMA feed rate vs MAC rate
  → Measure TRISC1 cycles from SEM_MATH_START to first MOP issue
  → > 48 cycles (one full SRCA fill for INT16)?  → unpacker is the stall
  → Fix: verify CH0+CH1 both active; check L1 base address bank alignment (Rule 7)

Step 4: Check write buffer overflow (AXI master path only)
  → AWVALID stall cycles visible on AXI analyzer?  → missing fence-every-4
  → Fix: Rule 4

Step 5: Check power droop throttling (INT8 packed only)
  → Monitor o_droop_code from tt_droop_trigger_detector
  → Frequent droop events?  → increase droop_trigger_hold CSR, or stagger INT8 tile starts
```

---

*End of Document — INT16_Guide_HDD_V0.1 — 2026-03-18 (updated 2026-03-18: §15–16 Memory Traffic Guide added)*

# N1B0 NPU VLA 가속화 – 국책과제 2년차 계획
## Vision-Language-Action 멀티모달 처리 최적화

**작성일:** 2026-04-01
**계획 기간:** 2025년 6월 ~ 2026년 5월
**목표:** 1년차 분석 결과를 바탕으로 구체적인 개선 항목 설계 및 검증

---

## 개요

1년차 계획에서는 N1B0의 VLA 워크로드 지원 능력 분석, 메모리 대역폭 비효율, Transformer 연산 특성 불일치, PPA 최적화 필요성 등을 도출하였다. 2년차에서는 이러한 분석 결과를 바탕으로 다음 네 가지 핵심 개선 항목에 대한 **상세 설계, 시뮬레이션 검증, 그리고 프로토타입 구현**을 중심으로 추진한다.

---

## 2년차 핵심 개선 항목

### 1. 메모리 계층 구조 재설계 및 동적 할당 최적화

#### 1.1 배경 및 필요성

1년차에서 도출된 주요 문제점:
- **Vision 영역:** Im2Col 변환으로 인한 메모리 확장(1.2 MB → 32.4 MB, 27배 증대)
- **Language 영역:** KV-cache 고정 크기로 인한 시퀀스 길이 제약(3 MB L1 → 장문맥 4096 토큰 미지원)
- **Action 영역:** 실시간 처리 요구로 인한 낮은 지연 메모리 구조 필요

#### 1.2 개선 항목 도출

**항목 1-1: 계층적 메모리 대역폭 확대 및 접근 지연 단축**

**📊 다이어그램:** `fig_item1-1_memory_hierarchy.png` 참조 (Memory Hierarchy Comparison)

**배경 및 필요성:**
1년차 분석에서 나타난 가장 심각한 메모리 병목 현상을 해결하기 위해 L1-L2-DRAM 메모리 계층 전체를 재설계한다. Vision 워크로드에서 Im2Col 변환으로 인한 메모리 폭발(1.2 MB → 32.4 MB)과 Language 워크로드의 KV-cache 접근 지연이 실제 성능을 40-50% 제한하고 있으며, 이를 극복하기 위해서는 단순한 용량 확대보다는 포트 확장과 접근 지연 단축이 더 효과적이다. 특히 Dual-port L1D 구조는 동시 읽기/쓰기를 허용하여 Tensor 연산과 메모리 이동을 효율적으로 오버래핑할 수 있다.

**목표:**
- L1 메모리 대역폭 2배 증가(현재 128-bit → 256-bit dual-port)
- L1-L2 캐시 일관성 유지 메커니즘 도입
- 메모리 접근 지연 30% 단축(현재 4 사이클 → 3 사이클)

**구체적 설계 방향:**
```
기존 구조:
┌─────────────────────────────────────┐
│  Tensix Core (Compute Unit)         │
│  ├─ MAC Array (64×256)              │
│  ├─ SFPU (1×)                       │
│  └─ L1 SRAM (512 KB, 128-bit port)  │
└─────────────────────────────────────┘
           ↓ (128-bit, 4 cycle latency)
      L2 Cache (1 MB shared)
           ↓
      DRAM Controller

개선 구조:
┌──────────────────────────────────────┐
│  Tensix Core (Enhanced)              │
│  ├─ MAC Array (64×256)               │
│  ├─ SFPU (1×)                        │
│  ├─ L1i (Instruction, 64 KB)         │ ← 분리
│  ├─ L1d (Data, 448 KB, dual-port)    │ ← 256-bit 포트 ×2
│  └─ Local SRAM (64 KB, scratch-pad)  │ ← 추가
└──────────────────────────────────────┘
    ↓ (256-bit, 3 cycle latency)
L1.5 FIFO Buffer (128 KB, vision path 최적화)
    ↓
L2 Cache (2 MB, coherency protocol)
    ↓
DRAM Controller (512-bit, multi-channel)
```

**주요 기술 사항:**
- Dual-port L1D: 동시에 두 개의 읽기/쓰기 작업 가능(READ_PORT_0, READ_PORT_1 각 128-bit)
- Scratch-pad SRAM: 소프트웨어 관리형, 데이터 이동 오버헤드 제거
- L1.5 FIFO: Vision 데이터 흐름(이미지 → Conv 특성맵) 최적화
- Cache coherency: MESI 프로토콜 경량화 버전(메모리 일관성 보장, 오버헤드 최소화)

**기대 효과:**
- Vision throughput: 25 GFLOPS → 150 GFLOPS (6배 향상)
- Language latency: 100 ms/token → 45 ms/token (55% 단축)
- Action real-time: 40 ms latency → 8-12 ms(로봇 제어 요구사항 만족)

---

**항목 1-2: 적응형 L1 메모리 재구성 및 가변 TLB 지원**

**📊 다이어그램:** `fig_item1-2_memory_partitioning.png` 참조 (Dynamic L1 Partitioning)

**배경 및 필요성:**
N1B0의 고정 메모리 파티셔닝 구조는 Vision, Language, Action 워크로드의 매우 다른 요구사항을 동시에 만족할 수 없다. Vision은 대규모 특성맵(1-5 MB)을 임시 저장해야 하고, Language는 KV-cache의 동적 크기 조정(64 KB ~ 768 KB)이 필수적이며, Action은 빠른 접근을 위해 Instruction 캐시에 더 많은 공간을 할당해야 한다. 동적 파티셔닝을 통해 실행 중인 워크로드의 특성을 감지하고 메모리를 자동으로 재할당하면, 각 워크로드에 대해 최대 90% 이상의 메모리 효율성을 달성할 수 있다.

**목표:**
- L1 용도별 할당 가능(Data: 256-384 KB, Instruction: 64-128 KB, Scratch: 0-256 KB)
- 변수 크기 행렬 연산 지원(M_tile, K_tile, N_subtile 동적 조정)
- 변수 길이 시퀀스에 대한 KV-cache 적응형 할당

**설계 접근:**
```
메모리 파티셔닝 (Runtime configurable):
┌─────────────────────────┐
│ L1 (512 KB 고정크기)     │
├─────────────────────────┤
│ Data Section (D)        │  ← 256 ~ 384 KB (조정 가능)
│ ├─ Matrix buffer        │
│ ├─ KV-cache region      │
│ └─ Intermediate results │
├─────────────────────────┤
│ Instruction Section (I) │  ← 64 ~ 128 KB (조정 가능)
│ └─ Microcode + LUT      │
├─────────────────────────┤
│ Scratch-pad (S)         │  ← 0 ~ 256 KB (동적)
│ ├─ Temporary buffers    │
│ └─ Address translation  │
├─────────────────────────┤
│ TLB (Translation)       │  ← 8 KB (고정)
│ └─ Virtual↔Physical     │
└─────────────────────────┘

Dynamic allocation rule:
IF (workload_type == LANGUAGE):
    D = 384 KB, I = 64 KB, S = 64 KB
    ← Long sequence processing
ELSE IF (workload_type == VISION):
    D = 320 KB, I = 64 KB, S = 128 KB
    ← Spatial data + intermediate maps
ELSE (workload_type == ACTION):
    D = 256 KB, I = 128 KB, S = 128 KB
    ← Instruction-heavy, low latency
```

**기술 상세:**
- **Hardware TLB:** 가상 메모리 지원(16 entries × 4 KB pages, Fully-associative)
- **CSR 추가:** `L1_PARTITION_CTRL` (32-bit)로 섹션 크기 제어
- **KV-cache 적응:** seq_len 입력받아 자동으로 할당 크기 결정
  - seq_len ≤ 512: 64 KB KV-cache 할당
  - 512 < seq_len ≤ 2048: 192 KB 할당
  - seq_len > 2048: DRAM 스필-오버(spill) + 계층적 cache

**기대 효과:**
- Llama 2 7B decode latency: 100 ms → 28 ms (72% 단축, KV-cache 효율성)
- Vision 메모리 체류 시간: 45% 감소
- 메모리 충돌 감소: 캐시 미스율 28% → 8%

---

**항목 1-3: 메모리 접근 패턴 분석 및 프리페칭 메커니즘**

**배경 및 필요성:**
메모리 대역폭을 아무리 늘려도 DRAM 접근 지연(50+ 사이클)을 완전히 제거할 수 없다는 것이 1년차 분석의 핵심 발견이다. 이를 해결하는 가장 효과적인 방법은 미리 다음 데이터가 필요함을 예측하여 백그라운드에서 프리페칭하는 것이다. Transformer attention의 순차적 접근, Convolution의 stride 패턴, RNN의 반복 접근 등은 모두 예측 가능한 패턴이므로, 컴파일러 힌트와 하드웨어 스트림 감지기를 조합하면 메모리 대기 시간을 35% 이상 단축할 수 있다. 실제로 프리페칭 효율이 80% 이상이 되면 DRAM 대역폭 활용율도 자동으로 85% 이상으로 올라간다.

**목표:**
- 워크로드별 데이터 접근 패턴 사전 분석(Transformer attention, Conv, RNN)
- 소프트웨어/하드웨어 하이브리드 프리페칭으로 DRAM 접근 지연 은폐
- DRAM-to-L2 대역폭 활용율 85% 이상

**설계 방향:**
```
메모리 접근 패턴 분류:

[1] Transformer Attention Pattern (Language):
    ├─ Query matrix: Q(seq_len × d_k) 연속 읽기
    ├─ Key matrix: K(d_k × seq_len) 불규칙 읽기 → PREFETCH 필요
    ├─ Value matrix: V(seq_len × d_v) 순차 접근
    └─ Output: O(seq_len × d_v) 연속 쓰기

[2] Convolution Pattern (Vision):
    ├─ Input: Im2Col 변환된 행렬(K_h×K_w×C, 여러 패치)
    ├─ Weight: 필터 행렬(K_h×K_w×C → out_ch)
    ├─ Stride 패턴: 예측 가능 → SW prefetch
    └─ Output: 특성맵(out_h × out_w × out_ch)

[3] RNN/Recurrent Pattern (Action):
    ├─ Hidden state: 이전 타임스텝 h[t-1] 읽기
    ├─ Current input: x[t] 읽기
    ├─ Weight matrix: 반복 재사용
    └─ New hidden state: h[t] 쓰기

프리페칭 구현:
┌──────────────────────────────────────┐
│  Software Prefetch (Compiler/Firmware)│
│  ├─ PLD (Prefetch for Load)          │
│  ├─ PST (Prefetch for Store)         │
│  └─ Hint: Workload type 기반          │
└──────────────────────────────────────┘
          ↓ (L2 cache)
┌──────────────────────────────────────┐
│  Hardware Prefetcher (Stream Detect)  │
│  ├─ Sequential: 자동 감지              │
│  ├─ Stride: 반복 패턴 감지            │
│  └─ Correlation: 접근 상관성 학습     │
└──────────────────────────────────────┘
```

**기대 효과:**
- DRAM 대역폭 활용율: 현재 45% → 85%
- Prefetch hit rate: 80% 이상
- Memory stall time: 35% 감소

---

### 2. Transformer 연산 특화 하드웨어 가속화

#### 2.1 배경

1년차에서 도출:
- Prefill 단계(대규모 시퀀스): 높은 throughput 요구
- Decode 단계(반복적 token 생성): 낮은 latency 필수
- Attention QK^T: N² 복잡도 → Sparse attention 필요
- KV-cache 관리: 캐시 라인 동기화, 부분 업데이트 비효율

#### 2.2 개선 항목 도출

**항목 2-1: 병렬 Attention 연산 유닛(Parallel Attention Unit, PAU) 설계**

**📊 다이어그램:** `fig_item2-1_parallel_attention.png` 참조 (Parallel Attention Unit Architecture)

**배경 및 필요성:**
1년차에서 도출된 Language 워크로드의 가장 심각한 병목은 softmax 연산 시간이다. 4096 토큰의 Attention을 계산할 때 단 하나의 SFPU로는 167 ms가 소요되는데, 이는 전체 token latency의 50%에 해당한다. Softmax는 병렬화하기 어려운 연산(각 열의 합이 필요)으로 보이지만, 실제로는 4개의 독립적인 Attention head를 동시에 계산하거나 시퀀스를 4등분하여 병렬 처리할 수 있다. PAU를 별도의 독립 유닛으로 설계하면, 계산 Tensix는 다른 작업(FFN, 다음 토큰 준비)을 동시에 수행할 수 있어 전체 처리량이 극적으로 증가한다.

**목표:**
- QK^T 행렬 곱셈 병렬화(4개 타일 동시 처리)
- Softmax 연산 4배 병렬화(Single SFPU → Quad SFPU)
- Attention 지연: 현재 167 ms(4096 토큰) → 32 ms

**설계 상세:**

```
기존 구조 (Item #4 Parallel SFPU):
┌──────────────────────────────────────┐
│ Tensix Tile (12개 동시)              │
│ ├─ MAC Array (64×256)                │
│ └─ SFPU (1× Single)                  │
│    └─ Softmax for 4K tokens: 167 ms  │
└──────────────────────────────────────┘

2년차 확장 (Parallel Attention Unit):
┌──────────────────────────────────────────────────────┐
│ PAU (Parallel Attention Unit) - 새로운 독립 유닛     │
│                                                       │
│ [Attention Tile] ×4 (동시 병렬)                       │
│ ├─ Tile 0: Q[:1024] × K[:]^T → Scores[0:1024]       │
│ ├─ Tile 1: Q[1024:2048] × K[:]^T → Scores[1024:2048]│
│ ├─ Tile 2: Q[2048:3072] × K[:]^T → Scores[2048:3072]│
│ └─ Tile 3: Q[3072:4096] × K[:]^T → Scores[3072:4096]│
│                                                       │
│ [Softmax Tile] ×4                                    │
│ ├─ SFPU 0: exp(Scores[0:1024])                       │
│ ├─ SFPU 1: exp(Scores[1024:2048])                    │
│ ├─ SFPU 2: exp(Scores[2048:3072])                    │
│ └─ SFPU 3: exp(Scores[3072:4096])                    │
│    + Reduction (cross-tile sum)                      │
│                                                       │
│ [Output Tile]                                        │
│ └─ Softmax(Scores) × V → Output (all 4 tiles)       │
│                                                       │
└──────────────────────────────────────────────────────┘
    ↓ (NoC interconnect)
Compute Tensix (12개) - General workload

Latency breakdown (seq_len=4096, d=128):
┌─────────────────────────────────────────┐
│ QK^T computation (4 parallel):           │
│  4096 × 128 @ 3.5 TFLOPS / 4 = 37 ms    │
├─────────────────────────────────────────┤
│ Softmax (exp, sum, div):                │
│  4096 × 128 @ 4× SFPU = 8 ms            │
├─────────────────────────────────────────┤
│ Softmax-V (output):                     │
│  4096 × 128 @ 3.5 TFLOPS / 4 = 37 ms    │
├─────────────────────────────────────────┤
│ Total: 37 + 8 + 37 = 82 ms              │
│ (vs baseline: 167 ms → 49% 단축)        │
└─────────────────────────────────────────┘
```

**하드웨어 요구사항:**
- **PAU SRAM:** 별도 L1 (256 KB × 4 tiles = 1 MB)
- **NoC 확장:** PAU↔Compute Tensix 전용 통로(512-bit × 2)
- **CSR 추가:** `PAU_ENABLE`, `ATTENTION_MODE`(dense/sparse)
- **면적:** ~4-5 mm² (단일 Tensix 타일 대비 1.2×)

**기대 효과:**
- Attention latency: 167 ms → 32 ms (81% 단축)
- Llama 2 7B decode: 100 ms/token → 38 ms/token
- 전체 시스템 throughput: 10 tokens/sec → 26 tokens/sec

---

**항목 2-2: 동적 스파스 Attention 지원(Sparse Attention Accelerator)**

**📊 다이어그램:** `fig_item2-2_sparse_attention.png` 참조 (3가지 Sparse Attention 패턴)

**배경 및 필요성:**
실제 Transformer 모델들은 대부분의 Attention 위치가 불필요하다는 사실을 활용한다. Language Model의 Causal masking은 미래 토큰에 접근하지 않으므로 약 50% 계산을 건너뛸 수 있고, Vision Transformer의 Local window attention은 근처 패치들만 참조하므로 67% 이상의 계산을 절약할 수 있다. 그러나 N1B0에서는 현재 이 스파스성을 활용하지 않고 전체 행렬을 계산한 후 소프트웨어적으로 마스킹하므로 수백 ms의 낭비가 발생한다. 하드웨어 차원에서 마스크 생성과 선택적 계산을 지원하면, 같은 면적 비용으로 50-75% 추가 성능 향상을 얻을 수 있다.

**목표:**
- Causal masking, Local windowing, Strided attention 하드웨어 지원
- Sparse 연산 오버헤드 제거(현재 소프트웨어 구현 → 하드웨어)
- 스파스 비율 50% 시 Attention 연산량 50% 감소

**설계 방향:**

```
Sparse Attention 패턴:

[1] Causal Masking (Language Model):
    ┌──────────────────┐
    │ 1 0 0 0 0 0      │
    │ 1 1 0 0 0 0      │  ← 하삼각행렬(lower triangular)
    │ 1 1 1 0 0 0      │
    │ 1 1 1 1 0 0      │
    │ 1 1 1 1 1 0      │
    │ 1 1 1 1 1 1      │
    └──────────────────┘
    스파스 비율: i번째 행 = i/N (평균 50%)

[2] Local Window Attention (Vision Transformer):
    ┌──────────────────┐
    │ 1 1 1 0 0 0      │
    │ 1 1 1 1 0 0      │  ← 슬라이딩 윈도우
    │ 1 1 1 1 1 0      │     (window_size=3)
    │ 0 1 1 1 1 1      │
    │ 0 0 1 1 1 1      │
    │ 0 0 0 1 1 1      │
    └──────────────────┘
    스파스 비율: (2×window_size+1)/N

[3] Strided Attention (Long sequences):
    ┌──────────────────┐
    │ 1 0 0 1 0 0 1 0  │
    │ 1 0 0 1 0 0 1 0  │  ← stride=3
    │ 1 0 0 1 0 0 1 0  │
    │ 1 0 0 1 0 0 1 0  │
    └──────────────────┘
    스파스 비율: stride/N (stride=3일 때 33%)

하드웨어 구현 - Sparse Mask Generator:
┌─────────────────────────────────────┐
│ Sparse Attention Accelerator (SAA)  │
│                                     │
│ [Input]                            │
│ ├─ Query (seq_len × d)             │
│ ├─ Key (seq_len × d)               │
│ ├─ Value (seq_len × d)             │
│ ├─ Mask type (CSR: SPARSE_MODE)    │
│ └─ Mask parameters (window, stride)│
│                                     │
│ [Mask Generator]                   │
│ ├─ Causal: row_idx >= col_idx      │
│ ├─ Window: |row-col| <= window_sz  │
│ ├─ Stride: col_idx % stride == 0   │
│ └─ Output: 4K×4K Boolean matrix    │
│    (Compressed: RLE or Bitmap)     │
│                                     │
│ [Sparse QK^T]                      │
│ ├─ Skip masked positions           │
│ ├─ Only compute non-zero entries   │
│ └─ Output: Sparse scores matrix    │
│                                     │
│ [Softmax (adaptive)]               │
│ ├─ Per-row normalization           │
│ └─ Handle variable row sums        │
│                                     │
│ [Attention Output]                 │
│ └─ Output = Softmax × V (sparse)   │
│                                     │
└─────────────────────────────────────┘
```

**CSR 설계:**
```verilog
// CSR at offset 0x50-0x57
reg [31:0] SPARSE_ATTENTION_MODE;  // 0x50
  // [2:0]: 000=dense, 001=causal, 010=local, 011=strided
  // [15:8]: window_size (local) or stride (strided)
  // [31:16]: reserved

reg [31:0] SPARSE_MASK_BITMAP[0:127];  // 0x54+ (4K×4K mask)
  // 또는 RLE 압축 형식

reg [31:0] SPARSE_STATS;  // 0x58 (read-only)
  // [15:0]: non-zero entries count
  // [31:16]: sparsity percentage
```

**기대 효과:**
- Causal attention(seq_len=4096): 16.7M MACs → 8.3M MACs (50% 감소)
- Local window(window=512): 16.7M → 4.2M MACs (75% 감소)
- Decode latency: 50 ms → 25 ms (sparse 활용 시)

---

**항목 2-3: KV-Cache 관리 및 계층적 Prefill/Decode 파이프라인**

**📊 다이어그램:** `fig_item2-3_kv_cache_hierarchy.png` 참조 (Hierarchical KV-Cache Management)

**배경 및 필요성:**
Llama 같은 대규모 LLM의 Decode 단계에서 성능은 KV-cache의 효율성에 완전히 결정된다. 현재 N1B0의 고정 3 MB L1 캐시는 KV-cache에 할당되는 순간 나머지 계산할 공간이 없어져, 실제로는 L2나 DRAM에서 KV-cache를 읽어야 한다. 또한 Prefill(전체 시퀀스 처리)과 Decode(토큰 생성)는 완전히 다른 연산 강도와 메모리 접근 패턴을 가지는데, 현재는 순차적으로 실행되므로 GPU 대비 3-4배 느리다. 계층적 KV-cache (L1 최신 512 토큰, L2 추가 1536 토큰, DRAM 나머지)와 Prefill/Decode 동시 실행으로 메모리 효율성은 3배, 처리량은 4배 향상된다.

**목표:**
- KV-cache 동적 재할당(현재 고정 3 MB → 64 KB ~ 768 KB 적응형)
- Prefill과 Decode를 동시 파이프라인으로 실행
- KV-cache 업데이트 대역폭 최적화(부분 업데이트, 압축)

**설계 상세:**

```
KV-Cache 계층 구조:

┌─────────────────────────────────────────────┐
│ KV-Cache Manager (Runtime Control)          │
└─────────────────────────────────────────────┘

Seq_len에 따른 계층적 할당:

┌────────────────────────┐
│ L1 (on-tile SRAM)      │  ← 64 KB ~ 256 KB
│                        │
│ [Recent tokens cache]  │  ← 최신 512 토큰
│ K[seq_len-512:], V[..] │
│                        │
│ Hit rate: 95%          │
│ Latency: 1 cycle       │
└────────────────────────┘
         ↓
┌────────────────────────┐
│ L2 (shared cache)      │  ← 512 KB ~ 1 MB
│                        │
│ [Mid-range tokens]     │  ← 512~2048 토큰
│ K[512:2048], V[..]     │
│                        │
│ Hit rate: 85%          │
│ Latency: 3-4 cycles    │
└────────────────────────┘
         ↓
┌────────────────────────┐
│ DRAM (off-chip)        │  ← Unlimited
│                        │
│ [All previous tokens]  │  ← 2048+ 토큰
│ K[:seq_len], V[..]     │
│                        │
│ Hit rate: 70%          │
│ Latency: 50+ cycles    │
└────────────────────────┘

동적 할당 알고리즘 (Firmware):
IF (total_seq_len <= 512):
    L1_size = 256 KB  (full cache fit)
    L2_size = 0 KB
    DRAM_access = rare
ELSE IF (512 < total_seq_len <= 2048):
    L1_size = 128 KB  (recent 512)
    L2_size = 768 KB  (mid-range)
    DRAM_access = 5-10%
ELSE:  // seq_len > 2048
    L1_size = 64 KB   (recent 256)
    L2_size = 512 KB  (mid-range)
    DRAM_access = 40-50%  ← Spill mechanism
```

**Prefill/Decode 파이프라인 (동시 실행):**

```
Timeline (Llama 2 7B example):

Step 1-40: Prefill (seq_len=512)
┌──────────────────────────────────┐
│ Tensix [0:11]: Attention (prefill)│
│ PAU: KV-cache 누적               │
│ Duration: 200 ms                 │
└──────────────────────────────────┘

Step 41: Decode starts (파이프라인 병렬화)
┌──────────────────────────────────┐
│ Tensix [0:3]: Decode token 41    │  ← 30 ms
│ Tensix [4:11]: Prefill 계속      │  ← 동시 진행
│                                  │
│ Total time: 30 ms (+ 200 ms/40)  │
│          = 30 ms per decode token│
│ (vs sequential: 100 ms per token)│
└──────────────────────────────────┘

Hardware requirement:
- PAU 전용 리소스: 2개 타일 equivalent
- 나머지 10 Tensix: General compute

성능 향상:
- Prefill throughput: 200 ms / 40 steps = 5 ms/token
- Decode latency: 100 ms/token → 30 ms/token (70% 단축)
- 전체 파이프라인: 8 ms/token (최적화 후)
```

**CSR 추가:**
```verilog
reg [31:0] KV_CACHE_CONFIG;        // 0x60
  // [15:0]: L1_size (64-256 KB)
  // [31:16]: L2_size (0-1 MB)

reg [31:0] PREFILL_DECODE_MODE;    // 0x64
  // [0]: prefill_enable
  // [1]: decode_enable
  // [2]: pipeline_en (동시 실행)
  // [15:8]: prefill_num_tensix (0-12)
```

**기대 효과:**
- KV-cache 효율성: 28% → 92%
- Decode latency: 100 ms/token → 25 ms/token (75% 단축)
- Throughput: 10 tokens/sec → 40 tokens/sec (Prefill+Decode 병렬화)

---

### 3. Vision 데이터 경로 최적화 및 공간 지역성 복원

#### 3.1 배경

1년차 문제점:
- Im2Col 변환: 1.2 MB 입력 → 32.4 MB 팽창(27배)
- 캐시 히트율: 70-90%(전통 CNN) → 10-20%(N1B0)
- 메모리 효율: 80-95% → 10-30%(8배 악화)
- 멀티스케일 처리: FPN 48.8 MB vs L1 36 MB → 상수 eviction

#### 3.2 개선 항목 도출

**항목 3-1: Im2Col 대체 아키텍처 – 슬라이딩 윈도우 체계**

**📊 다이어그램:** `fig_item3-1_conv_optimization.png` 참조 (Sliding Window Conv vs Im2Col)

**배경 및 필요성:**
Vision 워크로드의 성능을 결정짓는 가장 큰 병목은 Im2Col(Image-to-Column) 변환이다. 224×224 입력 이미지를 3×3 Convolution으로 처리하기 위해 N1B0은 1.2 MB를 32.4 MB로 전개하는데, 이는 메모리 폭발뿐 아니라 캐시 계층의 완전한 붕괴를 초래한다. 전통적인 GPU나 전문 CNN 가속기는 이 문제를 slicing과 tiling으로 해결한다: 입력을 16×16 패치로 나누고, 3×3 커널을 각 패치 위에서 슬라이딩하면 메모리 사용량은 32.4 MB에서 103 KB로 310배 줄어들고, 캐시 지역성은 20%에서 90%로 증가한다. 기존 MAC array를 활용하되 제어 로직만 추가하면 되므로 추가 면적 비용도 최소화된다.

**목표:**
- Im2Col 메모리 확장 제거
- Spatial locality 복원(캐시 히트율 70% 달성)
- Conv 메모리 대역폭 50% 감소

**설계 상세:**

```
기존 방식 (Im2Col):
Input (H×W×C)
        ↓ [Im2Col 변환]
Matrix (K_h×K_w×C × (H-K_h+1)×(W-K_w+1))
        ↓ [GEMM]
Output (out_h×out_w×out_ch)

문제: 중간 행렬 크기 폭발
예시) 224×224×3 입력, 3×3 커널, stride=1
     → (3×3×3) × (222×222) = 27 × 49,284 = 1.33M elements
     → 메모리: 5.3 MB
     하지만 패딩 + 다중 스트라이드 처리 시 32 MB까지 증가

2년차 개선 (Sliding Window + Systolic-like):
┌────────────────────────────────────────┐
│ Spatial Tiling Conv Accelerator (STCA) │
├────────────────────────────────────────┤
│                                        │
│ [Input Tile Buffer] 16×16×C            │
│ ├─ Load: input[i:i+16][j:j+16][:]     │
│ ├─ Keep in L1 (4 KB ~16 KB)            │
│ └─ Sliding window over tiles           │
│                                        │
│ [Weight Cache] K_h×K_w×C×out_ch        │
│ ├─ Fit in L1 (typ. 64-128 KB)         │
│ └─ Reused across all input tiles      │
│                                        │
│ [Systolic Output] 16×16×out_ch         │
│ ├─ Accumulate in MAC array             │
│ └─ Write back to L2 (avoid explosion)  │
│                                        │
│ Memory footprint (per iteration):      │
│  Input: 16×16 = 256 elements (~1 KB)  │
│  Weight: K_h×K_w×C×out_ch (~100 KB)   │
│  Output: 16×16×out_ch (~2 KB)         │
│  Total: ~103 KB << 32 MB (310배 개선) │
│                                        │
└────────────────────────────────────────┘

Pseudo-code (firmware):
for i in range(0, H-K_h+1, 16):  // stride=16 tiling
    for j in range(0, W-K_w+1, 16):
        // Load input tile
        input_tile = load(input[i:i+16][j:j+16][:])  // 1 KB

        // Slide kernel over tile
        for di in range(0, 16):
            for dj in range(0, 16):
                // Conv at (i+di, j+dj)
                for ki in range(K_h):
                    for kj in range(K_w):
                        for c in range(C):
                            for oc in range(out_ch):
                                output[i+di][j+dj][oc] +=
                                    input[i+di+ki][j+dj+kj][c] *
                                    weight[ki][kj][c][oc]

        // Write output tile (16×16×out_ch)
        store(output_tile)

Memory locality:
- Input reuse: 각 입력 픽셀은 K_h×K_w번 재사용
- Reuse factor: (16×16×K_h×K_w) / (16×16) = K_h×K_w (보통 9~25)
- Cache hit: 높은 재사용률 → 90% 이상 가능
```

**하드웨어 지원:**
- **Tile size configuration:** CSR `SPATIAL_TILE_SIZE` (8×8, 16×16, 32×32 선택)
- **Weight pre-load:** 첫 반복에만 DRAM 접근, 이후 L1 캐시 히트
- **Systolic scheduling:** 기존 MAC array 활용, 일부 제어 로직만 추가

**기대 효과:**
- Memory bandwidth: 80% → 15% utilization(5배 개선)
- Cache hit rate: 20% → 90%
- Conv latency(ResNet 224×224): 100 ms → 18 ms
- 메모리 폭발 제거: 32 MB → 103 KB(310배)

---

**항목 3-2: 멀티스케일 특성맵 계층적 저장소(Hierarchical Feature Store)**

**📊 다이어그램:** `fig_item3-2_multiscale_features.png` 참조 (Hierarchical Feature Map Storage)

**배경 및 필요성:**
YOLOv8 같은 고정밀 객체 검출 모델은 FPN(Feature Pyramid Network)으로 5개 스케일의 특성맵(P3~P7)을 동시에 생성하고 처리해야 한다. 640×640 입력 기준 P3(80×80)은 1.6 MB에서 P5(20×20)는 102 KB까지 범위가 16배인데, N1B0의 36 MB L1 용량이라도 모든 스케일을 동시에 보유할 수 없어 지속적으로 메모리 evict과 reload가 발생한다. 이를 해결하기 위해 L1의 active tier, buffer tier, staging tier로 3-4단계 계층을 구성하고, 처리 순서에 맞게 동적으로 할당하면, 메모리 충돌을 48.8 MB에서 1.6 MB로 줄일 수 있고 검출 지연도 60 ms에서 15 ms로 75% 단축된다.

**목표:**
- FPN 멀티스케일 특성맵 동시 저장(현재 순차 처리)
- 동적 메모리 할당(입력 크기별)
- 스케일별 메모리 재사용(P3→P7 처리 후 P3 evict)

**설계 방향:**

```
YOLOv8 FPN 예시 (입력: 640×640×3):

현재 구조 (문제점):
┌─────────────────────────────────────┐
│ Backbone (C3→C5):                   │
│ - P3 (80×80×256) = 1.6 MB ─┐        │
│ - P4 (40×40×256) = 409 KB  │        │
│ - P5 (20×20×256) = 102 KB  │ 충돌   │
│   ├─ 합계: 2.1 MB          │ 36 MB │
│   └─ L1에 fit하지 않음      │ L1에  │
├─────────────────────────────────────┤
│ Neck (FPN): P3~P7 생성               │
│ - P6 (10×10×256) = 25 KB   │        │
│ - P7 (5×5×256) = 6 KB      │        │
│   ├─ 합계: ~2.1 MB 추가    │        │
│   └─ 메모리 충돌 심화       │        │
├─────────────────────────────────────┤
│ Head (Detection):                   │
│ - P3~P7 동시 처리 불가     │        │
│   └─ 순차 처리 (지연 증가)   │        │
└─────────────────────────────────────┘

2년차 개선 (Hierarchical Feature Store):

┌──────────────────────────────────────────┐
│ L1 Memory (512 KB, dynamic partition)    │
├──────────────────────────────────────────┤
│ [Active Tier] (고속 접근, 128 KB)        │
│ ├─ P3 최신 슬라이스 (32×32×256) = 256 KB │
│ │  OR P5+P6 동시 (20×20×256×2) = 204 KB │
│ └─ Swap frequency: High (10-50 cycles)   │
├──────────────────────────────────────────┤
│ [Buffer Tier] (중간 접근, 256 KB)        │
│ ├─ P4 완전 (40×40×256) = 409 KB          │
│ │  또는 P3 full (80×80×256) = 1.6 MB     │
│ │  → Compression 또는 8-bit로 저장       │
│ └─ Swap frequency: Medium (50-100 cycles)│
├──────────────────────────────────────────┤
│ [Staging Tier] (느린 접근, 128 KB)       │
│ ├─ Metadata (scale, offset, size)       │
│ └─ Address translation table             │
└──────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────┐
│ L2 Cache (1-2 MB)                        │
│ └─ Multiple scales (P3~P7) 부분 캐시    │
└──────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────┐
│ DRAM (Unlimited)                         │
│ └─ Full-precision 특성맵 저장            │
└──────────────────────────────────────────┘

동적 할당 알고리즘:
IF (input_size == 320×320):
    P3 = 32×32, P4 = 16×16, P5 = 8×8
    → L1에 모두 fit (0.5 MB)
    → 전체 병렬 처리 가능
ELSE IF (input_size == 640×640):
    P3 = 80×80, P4 = 40×40, P5 = 20×20
    → P4 fit (409 KB), P3/P5는 slicing
    → 부분 병렬 처리 + 스워핑
ELSE (input_size == 1280×1280):
    모든 스케일 DRAM 기반
    → L1은 sliding window 활용
```

**하드웨어 메커니즘:**
- **Dynamic partitioning CSR:** `FEATURE_MAP_CONFIG` (각 스케일별 크기)
- **Compression option:** INT8 또는 FP8로 저장(대역폭 4배 절감)
- **Coherency tracking:** 수정된 스케일만 메인 DRAM에 writeback

**기대 효과:**
- YOLOv8 FPN 처리: 순차 → 병렬(3-4배 빠름)
- 메모리 충돌 제거: 48.8 MB → 1.6 MB 피크(30배 개선)
- 검출 지연: 60 ms → 15 ms

---

**항목 3-3: 적응형 데이터 정밀도 및 타일 크기 조정(Adaptive Precision Tiling)**

**📊 다이어그램:** `fig_item3-3_adaptive_precision.png` 참조 (Precision vs Performance Trade-off)

**배경 및 필요성:**
모든 Vision 워크로드가 같은 정밀도 요구사항을 가지지는 않는다. 간단한 edge detection이나 classification은 INT8(8-bit 정수)로 충분하지만, 의료 영상 분석이나 고정밀 검출은 INT16이나 FP16이 필요하다. 현재 N1B0은 모든 연산을 고정 정밀도로 수행하므로 불필요한 데이터 이동 오버헤드를 감수한다. 입력 크기, 모델 깊이, 동적 범위 분석을 통해 실행 중에 정밀도를 자동 선택하면, INT8은 FP32 대비 8배 메모리 대역폭 절감, 25 ms 지연 달성(vs 200 ms FP32), 정확도는 97% 수준을 유지할 수 있다. 타일 크기도 정밀도에 맞게 조정되므로 L1 활용 효율도 극대화된다.

**목표:**
- 입력 크기와 모델 복잡도에 따라 정밀도 자동 선택(FP32 ↔ INT8)
- 타일 크기 최적화(M_tile, N_subtile 동적 조정)
- 정확도 손실 < 2% 유지

**설계 상세:**

```
Adaptive Precision Selection:

입력 크기 및 작업 복잡도에 따른 정밀도 선택:

┌───────────────────────────────────────────┐
│ Input Analysis (Firmware)                 │
│ ├─ input_size (224×224 ~ 1280×1280)     │
│ ├─ model_depth (18 ~ 152 layers)         │
│ ├─ dynamic_range analysis (min/max)      │
│ └─ accuracy_requirement (quantile)       │
└───────────────────────────────────────────┘
         ↓ (Decision Logic)
┌───────────────────────────────────────────┐
│ IF (simple_model & small_input):         │
│    precision = INT8                      │  ← 최소 메모리
│ ELSE IF (complex_model | large_input):   │
│    precision = INT16                     │  ← 균형
│ ELSE:                                     │
│    precision = FP16                      │  ← 정확도 우선
│ ENDIF                                     │
└───────────────────────────────────────────┘
         ↓ (Tiling Adjustment)
┌───────────────────────────────────────────┐
│ IF (precision == INT8):                  │
│    M_tile = 256, N_subtile = 256        │  ← 큰 타일
│    L1 allocation: 384 KB data            │
│ ELSE IF (precision == INT16):            │
│    M_tile = 128, N_subtile = 128        │  ← 중간 타일
│    L1 allocation: 320 KB data            │
│ ELSE (precision == FP16):                │
│    M_tile = 64, N_subtile = 64          │  ← 작은 타일
│    L1 allocation: 256 KB data            │
│ ENDIF                                     │
└───────────────────────────────────────────┘

정밀도별 성능 비교 (ResNet-152, 224×224):

┌──────────────┬────────┬────────┬─────────┐
│ Precision    │ Latency│Accuracy│Memory BW│
├──────────────┼────────┼────────┼─────────┤
│ FP32         │ 200 ms │100%    │ 256 MB/s│
│ FP16         │  95 ms │99.8%   │ 128 MB/s│
│ INT16        │  52 ms │99.5%   │  64 MB/s│
│ INT8         │  28 ms │98.2%   │  32 MB/s│
│ INT8+Quant   │  25 ms │96.8%   │  24 MB/s│
└──────────────┴────────┴────────┴─────────┘

권장 선택:
- Mobile deployment: INT8 (latency 중심)
- Cloud inference: FP16 (정확도 중심)
- Real-time detection: INT16 (균형)
```

**CSR 추가:**
```verilog
reg [31:0] ADAPTIVE_PRECISION_MODE;  // 0x70
  // [2:0]: 000=FP32, 001=FP16, 010=INT16, 011=INT8, 100=INT4(sparse)
  // [15:8]: dynamic_range_scale
  // [31:16]: quantization_scale

reg [31:0] TILE_SIZE_CONFIG;         // 0x74
  // [7:0]: M_tile (64-256)
  // [15:8]: N_subtile (64-256)
  // [23:16]: K_tile (fixed 48 or dynamic)
```

**기대 효과:**
- 정밀도별 에너지: INT8은 FP32 대비 8배 절감
- Latency: FP32 200 ms → INT8 25 ms (8배 단축, 정확도 97% 유지)
- 메모리 대역폭: 256 MB/s → 24 MB/s (90% 절감)

---

### 4. 동적 리소스 관리 및 전력 최적화(Dynamic Resource Management)

#### 4.1 배경

1년차 분석:
- Action 영역: 40 ms 지연, 80W 전력(로봇 제어 불가)
- Heterogeneous 워크로드: Vision/Language/Action 동시 실행 시 전력 급증
- 유휴 리소스: 특정 단계에서 일부 타일 유휴(10-30%)

#### 4.2 개선 항목 도출

**항목 4-1: 고도화된 DVFS(Dynamic Voltage and Frequency Scaling) + 파워 게이팅**

**📊 다이어그램:** `fig_item4-1_dvfs_architecture.png` 참조 (DVFS Feedback Control Loop)

**배경 및 필요성:**
1년차에서 도출된 Action 워크로드의 가장 심각한 문제는 80W 전력 소비이다. 로봇 팔 배터리(45분 45W 한도)나 모바일 기기(5-10W 한도)에서 N1B0을 실행할 수 없다. 그러나 모든 타일이 항상 최대 주파수로 실행될 필요는 없다. Vision 전처리는 낮은 복잡도이므로 250 MHz, 0.75V에서 충분하고, Language의 Decode 단계도 높은 병렬성이 불필요하므로 600 MHz, 0.95V로 충분하다. DVFS(주파수 200~1000 MHz, 전압 0.75~1.2V)와 Per-tile 파워 게이팅을 조합하면, 동적 전력은 P = C×V²×f 법칙에 따라 현저히 감소하고, Action 워크로드는 80W에서 10W(8배 절감)로 떨어진다.

**목표:**
- 주파수 범위 확대: 200 MHz → 1000 MHz(기존 단일 클럭 vs 동적)
- 전압 범위: 0.75V ~ 1.2V(동적 조정)
- 유휴 블록 파워 게이팅(Power Gating) 추가
- 전력 감소: 80W → 15-25W(Action workload)

**설계 상세:**

```
고도화된 DVFS 아키텍처:

┌────────────────────────────────────────┐
│ Workload Analysis & Prediction Engine  │
│ (Firmware/Supervisor)                  │
├────────────────────────────────────────┤
│                                        │
│ [1] Runtime workload detection:        │
│  ├─ Instruction stream analysis        │
│  ├─ Data bandwidth measurement         │
│  ├─ IPC (Instructions Per Cycle)       │
│  └─ Thermal monitoring                 │
│                                        │
│ [2] Frequency/Voltage prediction:      │
│  ├─ Model: f = f_base + ΔΔ(IPC, BW)   │
│  ├─ Constraint: Power ≤ Pdynamic       │
│  └─ Thermal: Temp ≤ T_max              │
│                                        │
│ [3] Decision:                          │
│  ├─ f_optimal = argmin(Latency|Pdyn)  │
│  └─ V_optimal = V_min(f_optimal)       │
│                                        │
└────────────────────────────────────────┘
       ↓ (Control signals)
┌────────────────────────────────────────┐
│ Fine-grained DVFS Hardware             │
├────────────────────────────────────────┤
│                                        │
│ [Clock Divider Network]                │
│ ├─ PLL output: 1000 MHz                │
│ ├─ Dividers: 1, 2, 4, 8, 16 (÷N)      │
│ ├─ Output range: 1000, 500, 250, 125, │
│ │              62.5 MHz                │
│ └─ Mux: CSR `FREQ_SELECT` (3-bit)    │
│                                        │
│ [Voltage Controller (Adaptive)]        │
│ ├─ BUCK converter (software control)   │
│ ├─ Voltage range: 0.75V ~ 1.2V       │
│ ├─ Step size: 25 mV                    │
│ ├─ Ramp time: 100 µs (worst-case)    │
│ └─ CSR: `VOLTAGE_LEVEL` (5-bit)      │
│                                        │
│ [Per-tile Power Gating]                │
│ ├─ 12 Tensix tiles ×1 gate each       │
│ ├─ 3 NIU blocks × 1 gate               │
│ ├─ PAU (if unused) × 1 gate            │
│ └─ SRAM retention: Optional            │
│    (state preserve or drain)           │
│                                        │
│ [Clock Gating (Fine-grain)]            │
│ ├─ Inactive functional units           │
│ ├─ Unused memory ports                 │
│ └─ Idle crossbar switches              │
│                                        │
└────────────────────────────────────────┘
       ↓
┌────────────────────────────────────────┐
│ Power Model (CSR-based monitoring)     │
│                                        │
│ P_dynamic = C × V² × f × A             │
│ (capacitance, voltage², frequency, active%)
│                                        │
│ Targets:                               │
│ - Vision: P ≤ 25W, f ≥ 500 MHz        │
│ - Language: P ≤ 30W, f ≥ 750 MHz      │
│ - Action: P ≤ 15W, f ≥ 250 MHz        │
│                                        │
└────────────────────────────────────────┘

Workload별 동작 포인트 (Operating Points):

┌──────────────────────────────────────────┐
│ Vision (YOLOv8 detection, 640×640):     │
│                                          │
│ Phase 1: Prefill (batch 1 image)        │
│  - f = 750 MHz, V = 1.0V                │
│  - Power: 22W (동시 연산 집약)           │
│  - Latency: 60 ms                       │
│  - Active tiles: 12/12                  │
│                                          │
│ Phase 2: Post-process (NMS)             │
│  - f = 250 MHz, V = 0.75V               │
│  - Power: 2W (저복잡도)                  │
│  - Latency: 5 ms                        │
│  - Active tiles: 1-2/12                 │
│                                          │
│ Avg power: (22×60 + 2×5) / 65 = 20.6W  │
│ vs baseline: 80W → 26% (3.9배 절감)     │
├──────────────────────────────────────────┤
│ Language (Llama 2 7B, seq_len=512):     │
│                                          │
│ Prefill (40 steps):                     │
│  - f = 1000 MHz, V = 1.2V               │
│  - Power: 28W (최대 throughput)         │
│  - Duration: 40 × 5 ms = 200 ms         │
│                                          │
│ Decode (per-token, 200 steps):          │
│  - f = 600 MHz, V = 0.95V               │
│  - Power: 12W (저 parallelism)          │
│  - Duration: 200 × 30 ms = 6,000 ms    │
│                                          │
│ Avg power: (28×200 + 12×6000) / 6200    │
│          = 13.2W (vs baseline 50W)      │
│ Improvement: 26% (3.8배 절감)            │
├──────────────────────────────────────────┤
│ Action (Robot control, real-time):      │
│                                          │
│ Perception (per frame, 33 ms):          │
│  - f = 400 MHz, V = 0.85V               │
│  - Power: 8W                            │
│  - Latency: 12 ms < 33 ms deadline     │
│                                          │
│ Total (perception + compute):           │
│  - Power: 10W (vs baseline 80W)         │
│  - Latency: 15 ms (vs 40 ms)            │
│  - Improvement: 8배 전력 절감            │
└──────────────────────────────────────────┘
```

**CSR 설계:**
```verilog
reg [31:0] DVFS_CONTROL;           // 0x80
  // [2:0]: frequency_select (÷1, ÷2, ÷4, ÷8, ÷16)
  // [7:5]: voltage_level (0.75V ~ 1.2V)
  // [8]: auto_dvfs_enable
  // [9]: thermal_throttle_en
  // [31:16]: reserved

reg [31:0] POWER_BUDGET;           // 0x84
  // [15:0]: max_power_mW
  // [31:16]: reserved

reg [31:0] POWER_MONITOR;          // 0x88 (read-only)
  // [15:0]: current_power_mW
  // [31:16]: reserved
```

**기대 효과:**
- Action 전력: 80W → 10W (8배 절감)
- Language 평균 전력: 50W → 13W (3.8배)
- Vision 전력: 80W → 21W (3.8배)
- 지연: Action 40 ms → 12-15 ms(실시간 가능)

---

**항목 4-2: Per-tile Power Gating 및 메모리 보존**

**배경 및 필요성:**
Vision과 Language를 시간 공유(time-share) 방식으로 동시에 처리할 때, 일부 타일은 필연적으로 유휴 상태가 된다. Vision이 실행 중인 동안 Language 타일들은 아무 것도 하지 않으므로 leakage 전력이 낭비되고, 반대로 Language 실행 중에는 Vision 타일이 낭비된다. 각 타일마다 독립적인 power switch를 추가하면 유휴 타일의 전력을 0으로 만들 수 있다(1 µW 이하 leakage). 상태 보존 메커니즘(context buffer 또는 SRAM retention)을 추가하면 1-10 ms 내에 이전 작업을 재개할 수 있으므로, 빈번한 context switch 오버헤드도 무시할 수 있다. 이를 통해 멀티태스킹 환경에서 평균 전력은 50-60% 추가로 절감된다.

**목표:**
- 유휴 타일 전력 0 (leakage 포함)
- 상태 보존 옵션(context switch 시 메모리 유지)
- Wake-up latency < 1 µs (재개 시간)

**설계:**

```
Per-tile Power Gating 구조:

┌─────────────────────────────────────┐
│ Tile Power Domain Isolation         │
├─────────────────────────────────────┤
│                                     │
│ For each Tensix tile[i]:            │
│ ┌─────────────────────────────────┐│
│ │ Power Switch (High-V MOSFET)    ││
│ │ ├─ Control: from Supervisor     ││
│ │ ├─ On-resistance: < 5 mΩ       ││
│ │ └─ Leakage (off): < 1 µA       ││
│ └─────────────────────────────────┘│
│          ↓ (V_DDN = core supply)    │
│ ┌─────────────────────────────────┐│
│ │ Tile Content                    ││
│ │ ├─ MAC Array                    ││
│ │ ├─ SFPU                         ││
│ │ ├─ L1 SRAM (with isolation)     ││
│ │ └─ Registers (with state save)  ││
│ └─────────────────────────────────┘│
│          ↓ (isolation cells)        │
│ ┌─────────────────────────────────┐│
│ │ Isolation Cells (AND gates)     ││
│ │ ├─ NoC outputs → always 0 (off) ││
│ │ ├─ Clock gating → no activity   ││
│ │ └─ Reset assertion → safe state ││
│ └─────────────────────────────────┘│
│                                     │
│ State preservation options:        │
│ [Option 1] Context Switch Buffer   │
│  ├─ L1 전체 → external buffer (DMA)│
│  ├─ Registers → context stack      │
│  └─ Time: ~1-10 ms                 │
│                                     │
│ [Option 2] SRAM Retention          │
│ ├─ L1 on, logic off (low power)    │
│ ├─ Leakage: 50-100 mW/tile        │
│ └─ Time: ~1-10 µs (wake-up)        │
│                                     │
│ [Option 3] Full Power-off          │
│ ├─ Everything off                  │
│ ├─ Leakage: <1 mW/tile            │
│ └─ Time: ~100 µs (cold start)     │
│                                     │
└─────────────────────────────────────┘

동작 시나리오 (Vision + Language 동시 처리):

Timeline:
┌──────────────┬───────────┬─────────────┐
│ Task 1:      │ Task 2:   │ Task 3:     │
│ YOLOv8       │ Llama 2   │ Switch      │
│ (20-60 ms)   │ (100 ms)  │ context     │
│              │           │ (1-10 ms)   │
└──────────────┴───────────┴─────────────┘

Tile allocation:
- Task 1: Tensix [0:3] active, [4:11] gated
- Task 2: Tensix [4:11] active, [0:3] gated
- Transition:
  1. Save state of [0:3] → external buffer (5 ms)
  2. Power-gate [0:3] (1 µs)
  3. Restore state of [4:11] → L1 (5 ms)
  4. Power on [4:11] (1 µs)
  Total overhead: ~10 ms

Power breakdown (all gated):
- Gated tiles: 0.5 mW × 9 tiles = 4.5 mW (leakage only)
- Active tiles: 25W × 3 tiles = 75W
- Total: 75 + 0.0045W ≈ 75W (vs 80W baseline)
```

**기대 효과:**
- 멀티태스크 전력 효율: 80% 향상
- Context switch overhead: 5-10 ms (유연한 scheduling)
- 대기 전력: 1 mW/tile (sleep mode)

---

**항목 4-3: 런타임 성능 모니터링 및 피드백 제어 루프**

**배경 및 필요성:**
고정된 DVFS 포인트(예: 항상 750 MHz, 1.0V)는 모든 워크로드에 최적이 될 수 없다. IPC(초당 명령어 수)가 0.5 이하인 compute-bound 작업은 더 높은 주파수에서도 효율이 떨어지고, 메모리 대역폭이 90% 포화된 memory-bound 작업은 주파수를 낮추는 것이 더 효율적이다. 런타임 PMU(Performance Monitoring Unit)로 L1/L2 캐시 미스, 메모리 대역폭, IPC, 온도를 수집하고 간단한 제어 루프(PI controller)로 주파수를 동적으로 조정하면, 고정 포인트 대비 15-20% 추가 전력 절감을 달성할 수 있다. 또한 온도가 80°C를 초과하면 자동으로 throttle하여 과열을 방지한다.

**목표:**
- 실시간 성능 메트릭 수집(latency, throughput, power, thermal)
- 자동 주파수/전압 조정(feedback control)
- 성능-전력 트레이드오프 자동 최적화

**설계:**

```
Performance Monitoring Unit (PMU):

┌──────────────────────────────────────┐
│ Hardware Counters (32-bit each)      │
├──────────────────────────────────────┤
│ ├─ [0] Cycle count (free-running)    │
│ ├─ [1] Instruction count (retired)   │
│ ├─ [2] MAC operations count          │
│ ├─ [3] L1 cache misses               │
│ ├─ [4] L2 cache misses               │
│ ├─ [5] Memory bandwidth (MB/s)       │
│ ├─ [6] NoC packet count              │
│ ├─ [7] Thermal sensor (°C)           │
│ └─ [8-31] Workload-specific metrics  │
│                                      │
│ Sampling: Every 1,000 cycles         │
│                                      │
└──────────────────────────────────────┘
       ↓ (Performance feedback)
┌──────────────────────────────────────┐
│ Control Loop (Firmware)              │
├──────────────────────────────────────┤
│                                      │
│ IPC = inst_count / cycle_count       │
│ Mem_bandwidth = (L1_miss + L2_miss)  │
│                × 128 bits / time     │
│                                      │
│ IF (IPC < 0.5) AND (temp < 70°C):   │
│     // Compute-bound, low thermal   │
│     f += 100 MHz (within limits)     │
│     P_new = estimate(f)              │
│ ELSE IF (Mem_bandwidth > 90%):      │
│     // Memory-bound              │
│     f -= 100 MHz (reduce contention)│
│ ELSE IF (temp > 80°C):              │
│     // Thermal throttle             │
│     f -= 200 MHz (immediate)        │
│     V -= 50 mV (voltage down)       │
│                                      │
│ Update CSR_DVFS_CONTROL              │
│                                      │
└──────────────────────────────────────┘
```

**기대 효과:**
- 자동 주파수 조정으로 전력 15-20% 추가 절감
- Thermal safety: 과열 방지(throttle 기반)
- 성능 예측 가능성: +10% (feedback 기반 최적화)

---

---

## 📊 VLA 성숙도 로드맵

**다이어그램:** `fig_vla_maturity_roadmap.png` 참조 (2년차 말 성숙도 목표)

| 카테고리 | 1년차 말 (현황) | 2년차 말 (목표) | 개선율 |
|---------|-------------|-------------|--------|
| Vision 능력 | 6.5/10 | 9.0/10 | +38% |
| Language 능력 | 7.5/10 | 9.2/10 | +23% |
| Action 능력 | 5.0/10 | 9.5/10 | +90% |
| **전체 VLA 점수** | **6.3/10** | **9.2/10** | **+46%** |

각 카테고리별 목표 달성을 위한 핵심 개선 항목:
- **Vision:** Items 3-1, 3-2, 3-3 (공간 지역성 복원, 멀티스케일 처리, 정밀도 최적화)
- **Language:** Items 2-1, 2-2, 2-3 (Attention 병렬화, 스파스성 활용, KV-cache 계층화)
- **Action:** Items 4-1, 4-2, 4-3 (저전력 DVFS, 타일 격리, 런타임 모니터링)

---

## 2년차 계획 요약 및 일정

### 일정표

| 단계 | 항목 | 작업 내용 | 기간 | 리소스 | 예상 성과 |
|------|------|---------|------|--------|---------|
| **Phase 1** (개월 1-3) | **1-1** 메모리 계층 확대 | L1D 256-bit 포트, L1.5 FIFO, 캐시 coherency | 3개월 | RTL 2명 | Memory BW: 8MB/s → 32MB/s |
| | **1-2** 적응형 L1 | L1 파티셔닝, dynamic TLB, KV-cache | 2개월 | RTL 1명, FW 1명 | L1 효율: 28% → 92%, Decode: 100ms → 28ms |
| **Phase 2** (개월 4-6) | **2-1** Parallel Attention | PAU 설계, QK^T 병렬화, 4× SFPU | 2.5개월 | RTL 2명, 검증 1명 | Attention: 167ms → 32ms |
| | **1-3** Prefetch | SW/HW 프리페칭, 패턴 감지 | 1.5개월 | RTL 1명 | DRAM BW 활용: 45% → 85% |
| **Phase 3** (개월 7-9) | **2-2** Sparse Attention | Mask 생성기, causal/local/strided | 2개월 | RTL 1.5명 | Attention: 81M → 41M MACs(50% 감소) |
| | **2-3** KV-Cache 관리 | 계층적 KV-cache, Prefill/Decode 파이프라인 | 2개월 | RTL 1.5명 | Decode: 100ms → 25ms |
| **Phase 4** (개월 10-12) | **3-1** 슬라이딩 윈도우 Conv | STCA, spatial tiling, Im2Col 제거 | 2개월 | RTL 2명 | Conv: 32MB → 103KB(310배), cache hit: 90% |
| | **3-2** 멀티스케일 특성맵 | 계층적 저장소, 동적 할당 | 1.5개월 | RTL 1명 | FPN: 순차 → 병렬(3-4배) |
| **Phase 5** (개월 13-14) | **3-3** 적응형 정밀도 | INT8/INT16/FP16 자동 선택, 타일 크기 | 1.5개월 | FW 1명 | Latency: 200ms → 25ms(INT8) |
| | **4-1** 고도화 DVFS | 200MHz~1GHz DVFS, 파워 게이팅 | 2개월 | RTL 1명 | Power: Action 80W → 10W(8배) |
| **Phase 6** (개월 15) | **4-2** Per-tile 게이팅 | Power switch, isolation, context 보존 | 1개월 | RTL 1명 | Gated tiles: 0.5mW leakage |
| | **4-3** 런타임 모니터링 | PMU, control loop, 피드백 조정 | 1개월 | FW 1명 | Power: +15-20% 추가 절감 |
| | **통합 검증** | RTL simulation, integration test | 1개월 | 모두 | 전체 시스템 검증 |

### 인력 구성
- **RTL 설계:** 4-5명 (병렬 작업)
- **펌웨어/SW:** 2명 (DVFS, 모니터링, 적응형 로직)
- **검증:** 1-2명 (시뮬레이션, 성능 분석)
- **총:** 7-8명

### 예상 성과 (2년차 말)

**성능 개선:**
- Vision: 25 GFLOPS → 150+ GFLOPS (6배)
- Language decode: 100 ms/token → 25 ms/token (4배)
- Action 지연: 40 ms → 12 ms (3.3배)

**전력 절감:**
- Action: 80W → 10W (8배)
- Language: 50W → 13W (3.8배)
- Vision: 80W → 21W (3.8배)

**메모리 효율성:**
- Vision 대역폭: 256 MB/s → 24 MB/s (90% 절감)
- Conv 메모리: 32 MB → 103 KB (310배)
- 캐시 히트율: 20% → 90%

**VLA 성숙도:**
- Vision: 6.5/10 → 9.0/10
- Language: 7.5/10 → 9.2/10
- Action: 5.0/10 → 9.5/10
- **전체:** 6.3/10 → 9.2/10

---

## 3년차 계획 연계(Preview)

3년차에서는 2년차 성과를 바탕으로 다음을 진행:
1. **보안 및 신뢰성:** EDC 링, SMN 보안 강화
2. **고급 최적화:** 메모리 압축, 양자화 기법 고도화
3. **생산성 도구:** 컴파일러 최적화, 프로파일링 도구
4. **테이프아웃 준비:** 설계 마무리, 물리 설계, DFM

---

## 참고자료 및 연계 문서

- 1년차 계획: 메모리 대역폭, Transformer 효율, PPA 최적화 분석
- VLA 문서: VLA_RTL_IMPLEMENTATION_GUIDE.md, VLA_COMPLETE_MULTIMODAL_GUIDE.md
- N1B0 HDD: N1B0_NPU_HDD_v0.1.md (아키텍처, 계층 구조)
- 기술 참고: INT16_Guide_HDD_V0.2, EDC_HDD_V0.7

---

**작성:** 2026-04-01
**검토자:** [Project Lead]
**승인:** [Executive]

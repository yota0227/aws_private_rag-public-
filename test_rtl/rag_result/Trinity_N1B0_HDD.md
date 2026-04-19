# Trinity N1B0 — Hardware Design Document (HDD)

| 항목 | 내용 |
|------|------|
| **문서 ID** | TT-HDD-TRINITY-N1B0-001 |
| **파이프라인** | `tt_20260221` |
| **Top Module** | `trinity.sv` |
| **작성일** | 2026-04-17 |
| **상태** | Draft v1.0 |

---

## 목차

1. [개요 (Overview)](#1-개요-overview)
2. [칩 레벨 사양 (Chip-Level Specifications)](#2-칩-레벨-사양-chip-level-specifications)
3. [탑 레벨 블록 다이어그램 (Top-Level Block Diagram)](#3-탑-레벨-블록-다이어그램-top-level-block-diagram)
4. [서브모듈 계층 구조 (Sub-module Hierarchy)](#4-서브모듈-계층-구조-sub-module-hierarchy)
5. [주요 블록 상세 설계 (Block-Level Design)](#5-주요-블록-상세-설계-block-level-design)
   - 5.1 [Tensix Core + L1 Cache](#51-tensix-core--l1-cache)
   - 5.2 [FPU (Floating-Point Unit)](#52-fpu-floating-point-unit)
   - 5.3 [SFPU (Special Floating-Point Unit)](#53-sfpu-special-floating-point-unit)
   - 5.4 [NoC (Network-on-Chip)](#54-noc-network-on-chip)
   - 5.5 [EDC (Embedded Data Controller)](#55-edc-embedded-data-controller)
   - 5.6 [Dispatch](#56-dispatch)
   - 5.7 [Overlay (RISC-V Subsystem)](#57-overlay-risc-v-subsystem)
   - 5.8 [UCIe (Universal Chiplet Interface)](#58-ucie-universal-chiplet-interface)
6. [클럭 및 리셋 구조 (Clock & Reset Architecture)](#6-클럭-및-리셋-구조-clock--reset-architecture)
7. [DFX / 테스트 및 디버그 (DFX / Test & Debug)](#7-dfx--테스트-및-디버그-dfx--test--debug)
8. [보안 (Security)](#8-보안-security)
9. [주요 인터페이스 요약 (Key Interface Summary)](#9-주요-인터페이스-요약-key-interface-summary)
10. [설계 제약 및 고려사항 (Design Constraints & Considerations)](#10-설계-제약-및-고려사항-design-constraints--considerations)
11. [개정 이력 (Revision History)](#11-개정-이력-revision-history)

---

## 1. 개요 (Overview)

Trinity N1B0는 AI 추론 및 학습 워크로드를 위해 설계된 고성능 AI 가속기 SoC입니다. 칩의 핵심은 **Tensix 코어**로, FPU/SFPU 기반의 부동소수점 연산 유닛과 로컬 L1 SRAM 캐시를 통합하여 높은 연산 밀도를 제공합니다.

칩 내부의 모든 블록은 **NoC(Network-on-Chip) 메시 인터커넥트**를 통해 연결되며, **EDC(Embedded Data Controller)**를 통해 외부 DRAM에 접근합니다. 호스트와의 명령 분배는 **Dispatch** 블록이 담당하고, **Overlay(RISC-V 서브시스템)**가 펌웨어 기반 제어를 수행합니다. 멀티 칩렛 확장을 위해 **UCIe(Universal Chiplet Interface)** 표준을 지원합니다.

### 1.1 설계 목표

- 고성능 AI 텐서 연산 (FP32/FP16/BF16 등)
- 저지연 NoC 기반 온칩 통신
- 멀티 칩렛 스케일아웃 (UCIe)
- 하드웨어 보안 (NoC Security Block)
- DFX를 통한 테스트/디버그 용이성

---

## 2. 칩 레벨 사양 (Chip-Level Specifications)

| 항목 | 수치 |
|------|------|
| **총 포트 수** | 3,519,581 |
| **총 넷 수** | 6,867,254 |
| **총 셀 수** | 3,994,907 |
| **매크로/블랙박스** | 2,228 |
| **참조 모듈 수** | 55 |
| **총 셀 면적** | 2,632,703.81 (단위: 설계 유닛) |
| **클럭 도메인** | 5개 독립 도메인 |
| **클럭 게이팅 모듈** | 18개 |

---

## 3. 탑 레벨 블록 다이어그램 (Top-Level Block Diagram)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Trinity N1B0 (Top)                          │
│                                                                     │
│  ┌──────────┐   ┌──────────────────┐   ┌────────────────────────┐  │
│  │  UCIe    │   │    Dispatch      │   │   Tensix Core + L1     │  │
│  │ (Chiplet │   │  ┌────┐ ┌────┐  │   │  ┌─────┐ ┌──────────┐ │  │
│  │  I/F)    │   │  │East│ │West│  │   │  │FPU  │ │SFPU      │ │  │
│  │          │   │  │    │ │    │  │   │  │v2   │ │Wrapper   │ │  │
│  │ • Clk/   │   │  └────┘ └────┘  │   │  └─────┘ └──────────┘ │  │
│  │   Rst    │   │  • JTAG/SDUMP   │   │  ┌─────┐ ┌──────────┐ │  │
│  │   Ctrl   │   │  • FB Interface  │   │  │Unpack│ │JTAG/CSR │ │  │
│  │ • Bus    │   └────────┬─────────┘   │  │SrcA │ │Interface │ │  │
│  │   Clean  │            │             │  └─────┘ └──────────┘ │  │
│  │ • WDT    │            │             └──────────┬─────────────┘  │
│  └────┬─────┘            │                        │                │
│       │                  │                        │                │
│       ▼                  ▼                        ▼                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   NoC Mesh Interconnect                     │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │   │
│  │  │RR Arbiter│ │Repeaters │ │NIU (VC   │ │NoC2AXI Router │  │   │
│  │  │(tt_noc_  │ │(Cardinal)│ │Req/Resp) │ │(NE Optimized) │  │   │
│  │  │rr_arb)   │ │          │ │          │ │               │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
│                             │                                      │
│       ┌─────────────────────┼─────────────────────┐                │
│       ▼                     ▼                     ▼                │
│  ┌──────────┐    ┌──────────────────┐    ┌──────────────────┐      │
│  │ Overlay  │    │       EDC        │    │  Clock / Reset   │      │
│  │ (RISC-V) │    │  ┌────────────┐  │    │  Infrastructure  │      │
│  │          │    │  │Direct Conn │  │    │  ┌────────────┐  │      │
│  │ Chipyard │    │  │  Nodes     │  │    │  │tt_clk_gater│  │      │
│  │ TileLink │    │  ├────────────┤  │    │  │(18 modules)│  │      │
│  │ Config   │    │  │Loopback    │  │    │  └────────────┘  │      │
│  │          │    │  │  Conn Nodes│  │    │  ┌────────────┐  │      │
│  │ L1 Arb   │    │  ├────────────┤  │    │  │CDC Sync    │  │      │
│  │(tt_rocc_ │    │  │Security    │  │    │  │(sync3)     │  │      │
│  │ l1_arb)  │    │  │Block (228  │  │    │  └────────────┘  │      │
│  │          │    │  │output ports│  │    │                   │      │
│  └──────────┘    │  └────────────┘  │    └──────────────────┘      │
│                  └──────────────────┘                               │
│                             │                                      │
│                             ▼                                      │
│                     External DRAM                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. 서브모듈 계층 구조 (Sub-module Hierarchy)

```
trinity (Top Module)
│
├── tt_tensix_with_l1                    # Tensix 코어 + L1 캐시
│   └── tt_instrn_engine                 # 명령어 엔진
│       ├── tt_fpu_v2                    # FPU v2 (부동소수점 연산)
│       ├── tt_sfpu_wrapper              # SFPU 래퍼
│       │   └── tt_sfpu_lregs            # SFPU 로컬 레지스터
│       ├── unpack_srca_intf             # 소스 A 언팩 인터페이스
│       ├── tt_tensix_jtag               # Tensix JTAG 디버그
│       ├── csr_intf                     # CSR 인터페이스
│       └── tt_sync3 (jtag_dbg_req_sync) # JTAG 디버그 요청 동기화
│
├── tt_dispatch_top_east                 # Dispatch (East) — 27 포트
│   ├── tt_dispatch_top_east_SDUMP_INTF  # SDUMP 인터페이스 (8 포트)
│   └── tt_dispatch_top_east_FB_INTF     # FB 인터페이스 (15 포트)
│
├── tt_dispatch_top_west                 # Dispatch (West) — 27 포트
│   └── tt_dispatch_top_west_SDUMP_INTF  # SDUMP 인터페이스 (8 포트)
│
├── edc_direct_conn_nodes                # EDC 직접 연결 노드
│   └── tt_edc1_intf_connector           # EDC1 인터페이스 커넥터
│
├── edc_loopback_conn_nodes              # EDC 루프백 연결 노드
│   └── tt_edc1_intf_connector           # EDC1 인터페이스 커넥터
│
├── tt_edc1_noc_sec_block_reg            # EDC NoC 보안 블록 레지스터
│   └── tt_edc1_noc_sec_block_reg_inner  # 내부 레지스터 인터페이스
│
├── NoC Fabric                           # NoC 인터커넥트
│   ├── tt_noc_rr_arb                    # 라운드-로빈 중재기
│   ├── tt_noc_repeater                  # 범용 리피터
│   ├── tt_noc_repeaters_cardinal        # 카디널 리피터
│   ├── tt_niu_vc_req_send               # NIU VC 요청 전송
│   ├── tt_niu_output_port               # NIU 출력 포트
│   ├── tt_noc_sync3_pulse               # CDC 동기화
│   └── trinity_noc2axi_router_ne_opt_FBLC # NoC↔AXI 라우터
│
├── Overlay (RISC-V Subsystem)           # Chipyard 기반 RISC-V
│   ├── TTTrinityConfig_*                # Trinity 설정 모듈들
│   ├── tt_rocc_l1_arb                   # RoCC L1 중재기
│   ├── tt_fds_dispatch_reg_inner        # Dispatch 레지스터 파일
│   └── tt_fds_tensixneo_reg_inner       # TensixNeo 레지스터 파일
│
├── UCIe Block                           # 칩렛 인터페이스
│   ├── Clock & Reset Controller         # 클럭/리셋 제어
│   ├── Bus Cleaner                      # 버스 클리너
│   └── Watchdog Timer                   # 워치독 타이머
│
└── Clock/Reset Infrastructure           # 클럭/리셋 인프라
    ├── tt_clk_gater (×18)               # 계층적 클럭 게이팅
    ├── tt_sync3                         # 3단 동기화기
    └── tt_noc_sync3_pulse               # 펄스 CDC 동기화
```

---

## 5. 주요 블록 상세 설계 (Block-Level Design)

### 5.1 Tensix Core + L1 Cache

**모듈:** `tt_tensix_with_l1` → `tt_instrn_engine`
**소스:** `tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_instrn_engine.sv`

#### 5.1.1 개요

Tensix는 Trinity의 핵심 AI 연산 코어입니다. 명령어 엔진(`tt_instrn_engine`)이 FPU, SFPU, 언팩 유닛 등을 조율하여 텐서 연산을 수행합니다. 각 Tensix 코어는 로컬 L1 SRAM 캐시와 결합되어 데이터 지역성을 극대화합니다.

#### 5.1.2 주요 포트

| 포트 | 방향 | 설명 |
|------|------|------|
| `i_neo_instance` | Input | Neo 인스턴스 식별자 |
| `i_clk` | Input | 코어 클럭 |
| `i_reset_n` | Input | 액티브-로우 리셋 |
| `i_risc_reset_n` | Input | RISC 프로세서 리셋 |
| `i_test_clk_en` | Input | 테스트 클럭 인에이블 |
| `i_tensix_id` | Input | Tensix 코어 ID |
| `i_test_mode` | Input | 테스트 모드 |
| `i_tensix_harvested` | Input | 하베스팅 상태 (결함 코어 비활성화) |
| `o_gtile_gated_clk` | Output | 게이트된 타일 클럭 |
| `o_fpu_soft_reset` | Output | FPU 소프트 리셋 |

#### 5.1.3 서브모듈

| 인스턴스 | 모듈 | 기능 |
|----------|------|------|
| `fpu` | `tt_fpu_v2` | 부동소수점 연산 유닛 |
| `sfpu_wrapper` | `tt_sfpu_wrapper` | 특수 부동소수점 유닛 래퍼 |
| `unpack_srca` | `unpack_srca_intf` | 소스 A 데이터 언팩 |
| `u_tensix_jtag` | `tt_tensix_jtag` | JTAG 디버그 |
| `jtag_csr_intf` | `csr_intf` | CSR 레지스터 접근 |
| `jtag_dbg_req_sync` | `tt_sync3` | 디버그 요청 CDC 동기화 |

#### 5.1.4 하베스팅 (Harvesting)

`i_tensix_harvested` 신호를 통해 제조 결함이 있는 코어를 런타임에 비활성화할 수 있습니다. 이를 통해 수율(yield)을 향상시킵니다.

---

### 5.2 FPU (Floating-Point Unit)

**모듈:** `tt_fpu_v2`
**토픽:** FPU

#### 5.2.1 개요

FPU v2는 Tensix 코어 내부의 주요 부동소수점 연산 유닛입니다. 덧셈, 뺄셈, 곱셈, 나눗셈 등의 부동소수점 산술 연산을 수행하며, AI 워크로드의 텐서 연산에 최적화되어 있습니다.

#### 5.2.2 주요 기능

- 부동소수점 산술 연산 (Add, Sub, Mul, Div)
- 다중 정밀도 지원 (FP32, FP16, BF16 등)
- 파이프라인 구조로 높은 처리량 달성
- DFX 지원 (`tt_fpu_gtile_dfx` — 클럭 입력 → DFX 처리 후 클럭 출력)

---

### 5.3 SFPU (Special Floating-Point Unit)

**모듈:** `tt_sfpu_wrapper` → `tt_sfpu_lregs`
**토픽:** SFPU

#### 5.3.1 개요

SFPU는 비선형 활성화 함수(ReLU, Sigmoid, Tanh 등) 및 특수 수학 연산을 하드웨어로 가속하는 유닛입니다.

#### 5.3.2 주요 구성

| 모듈 | 기능 |
|------|------|
| `tt_sfpu_wrapper` | SFPU 최상위 래퍼 |
| `tt_sfpu_lregs` | SFPU 파이프라인용 로컬 레지스터 세트 관리 |

---

### 5.4 NoC (Network-on-Chip)

**소스 디렉토리:** `tt_rtl/tt_noc/rtl/noc/`
**토픽:** NoC, NIU

#### 5.4.1 개요

NoC는 Trinity 칩 내부의 모든 블록(Tensix, EDC, Dispatch, Overlay 등)을 연결하는 패킷 기반 메시 인터커넥트입니다. X/Y 좌표 기반 라우팅과 Virtual Channel(VC) 메커니즘을 사용합니다.

#### 5.4.2 주요 모듈

| 모듈 | 기능 |
|------|------|
| **tt_noc_rr_arb** | 라운드-로빈 중재 — NoC 요청 간 공정한 대역폭 분배 |
| **tt_noc_repeater** | 범용 NoC 리피터 — 장거리 패킷 전파 시 신호 무결성 유지 |
| **tt_noc_repeaters_cardinal** | 카디널 방향(N/S/E/W) 리피터 — 메시 토폴로지 패킷 전파 |
| **tt_niu_vc_req_send** | NIU(Network Interface Unit) — VC 기반 요청 전송 |
| **tt_niu_output_port** | NIU 출력 포트 — 채널 유효성, 헤드 플릿 처리 |
| **tt_noc_sync3_pulse** | 클럭 도메인 간 펄스 동기화 |
| **trinity_noc2axi_router_ne_opt_FBLC** | NoC↔AXI 프로토콜 변환 라우터 (최적화 버전) |

#### 5.4.3 패킷 구조

- **Head Flit:** `qsr_noc_header_t` 타입 — 라우팅 정보, 목적지 좌표 포함
- **Data Flit:** 페이로드 데이터
- **노드 ID:** `i_local_nodeid_x`, `i_local_nodeid_y`로 각 노드 식별

#### 5.4.4 중재 방식

- **라운드-로빈 (Round-Robin):** `tt_noc_rr_arb`가 복수의 요청자 간 공정한 순서로 접근 허용
- **VC(Virtual Channel):** 데드락 방지 및 QoS 보장을 위한 가상 채널 분리

#### 5.4.5 NIU 인터페이스

NIU(Network Interface Unit)는 각 IP 블록과 NoC 패브릭 사이의 프로토콜 변환을 담당합니다:
- `tt_niu_vc_req_send`: 요청 패킷 생성 및 전송
- `tt_niu_output_port`: 응답 패킷 수신 및 채널 관리
- `i_ext_req_head_flit_override`: 외부 헤드 플릿 오버라이드 지원

---

### 5.5 EDC (Embedded Data Controller)

**소스 디렉토리:** `tt_rtl/tt_edc/rtl/`
**토픽:** EDC

#### 5.5.1 개요

EDC는 외부 DRAM 메모리 인터페이스를 관리하는 임베디드 데이터 컨트롤러입니다. NoC를 통해 Tensix 코어 및 기타 블록의 메모리 요청을 처리합니다.

#### 5.5.2 주요 모듈

| 모듈 | 기능 |
|------|------|
| **tt_edc1_intf_connector** (Direct) | 직접 연결 노드 — 저지연 메모리 접근 경로 |
| **tt_edc1_intf_connector** (Loopback) | 루프백 연결 노드 — 테스트/디버그용 경로 |
| **tt_edc1_noc_sec_block_reg** | NoC 보안 블록 레지스터 (228개 출력 포트) |
| **tt_edc1_noc_sec_block_reg_inner** | 보안 블록 내부 레지스터 인터페이스 |

#### 5.5.3 EDC 패키지 인터페이스 (`tt_edc_pkg.sv`)

| Modport | 방향 | 설명 |
|---------|------|------|
| `ingress` | 입력 | NoC → EDC 데이터 수신 |
| `egress` | 출력 | EDC → NoC 데이터 송신 |
| `edc_node` | 양방향 | EDC 노드 인터페이스 |
| `sram` | 양방향 | SRAM 접근 인터페이스 |

#### 5.5.4 에러 처리

- `cor_err`: 정정 가능 에러 (Correctable Error) 신호
- `err_inj_vec`: 에러 주입 벡터 — 테스트 목적의 의도적 에러 생성
- `req_tgl` / `ack_tgl`: 토글 기반 핸드셰이크 프로토콜

---

### 5.6 Dispatch

**모듈:** `tt_dispatch_top_east`, `tt_dispatch_top_west`
**토픽:** Dispatch

#### 5.6.1 개요

Dispatch 블록은 호스트로부터의 명령을 수신하여 Tensix 코어들에 분배하는 역할을 합니다. East/West 듀얼 구조로 대역폭을 확보합니다.

#### 5.6.2 포트 사양

| 모듈 | 포트 수 | 주요 인터페이스 |
|------|---------|----------------|
| `tt_dispatch_top_east` | 27 | 클럭, 리셋, 파워 굿, NoC, 메모리 컨트롤러 |
| `tt_dispatch_top_west` | 27 | 클럭, 리셋, 파워 굿, NoC, 메모리 컨트롤러 |

#### 5.6.3 서브 인터페이스

| 모듈 | 포트 수 | 기능 |
|------|---------|------|
| `tt_dispatch_top_east_SDUMP_INTF` | 8 | JTAG SDUMP 인터페이스 (입출력) |
| `tt_dispatch_top_west_SDUMP_INTF` | 8 | JTAG SDUMP 인터페이스 (입출력) |
| `tt_dispatch_top_east_FB_INTF` | 15 | FB 인터페이스 — 테스트 인에이블, 쓰기/읽기, 주소, 데이터 |

---

### 5.7 Overlay (RISC-V Subsystem)

**토픽:** Overlay
**프레임워크:** Chipyard (RISC-V SoC Generator)

#### 5.7.1 개요

Overlay는 Chipyard 기반의 RISC-V 프로세서 서브시스템으로, 펌웨어 기반 제어 및 관리 기능을 수행합니다. TileLink 프로토콜을 사용하여 온칩 버스와 통신합니다.

#### 5.7.2 주요 모듈

| 모듈 | 기능 |
|------|------|
| `TTTrinityConfig_*` | Trinity 전용 Chipyard 설정 모듈 |
| `TTTrinityConfig_PlusArgTimeout` | 시뮬레이션 타임아웃 제어 |
| `TTTrinityConfig_SourceC` | TileLink SourceC — 캐시 릴리즈/프로브 응답 (512-bit 데이터) |
| `tt_rocc_l1_arb` | RoCC(Rocket Custom Coprocessor) L1 메모리 중재기 |
| `tt_fds_dispatch_reg_inner` | Dispatch 레지스터 파일 접근/갱신 |
| `tt_fds_tensixneo_reg_inner` | TensixNeo 레지스터 파일 접근/갱신 |

#### 5.7.3 TileLink 인터페이스

- **주소 폭:** 22-bit
- **데이터 폭:** 512-bit
- **소스 ID:** 2-bit
- **프로토콜:** TileLink Cached (TL-C) — Acquire/Release/Probe 지원

---

### 5.8 UCIe (Universal Chiplet Interface)

**토픽:** UCIe

#### 5.8.1 개요

UCIe 블록은 멀티 칩렛 구성을 위한 칩 간 고속 인터페이스입니다. UCIe 표준을 준수하여 다른 칩렛과의 상호 운용성을 보장합니다.

#### 5.8.2 주요 구성 요소

| 구성 요소 | 기능 |
|-----------|------|
| **Clock & Reset Controller** | 칩렛 간 클럭 동기화 및 리셋 시퀀싱 |
| **Bus Cleaner** | 버스 상태 정리 — 에러 복구 및 안전한 상태 전환 |
| **Watchdog Timer** | 칩렛 통신 타임아웃 감시 — 행(hang) 상태 감지 및 복구 |

---

## 6. 클럭 및 리셋 구조 (Clock & Reset Architecture)

### 6.1 클럭 도메인

Trinity는 5개의 독립 클럭 도메인을 사용합니다:

| 클럭 신호 | 도메인 | 용도 |
|-----------|--------|------|
| `i_axi_clk` | AXI | AXI 버스 인터페이스, 호스트 통신 |
| `i_noc_clk` | NoC | NoC 인터커넥트 패브릭 |
| `i_ai_clk` | AI | Tensix 코어 AI 연산 |
| `i_dm_clk` | DM | Data Mover, Uncore 로직 |
| `clock` (Overlay) | Overlay | RISC-V 서브시스템 |

### 6.2 리셋 신호

| 리셋 신호 | 극성 | 대상 |
|-----------|------|------|
| `i_noc_reset_n` | Active-Low | NoC 패브릭 |
| `i_ai_reset_n` | Active-Low | AI 연산 블록 |
| `i_tensix_reset_n` | Active-Low | Tensix 코어 전용 |
| `i_edc_reset_n` | Active-Low | EDC 메모리 컨트롤러 |
| `i_dm_uncore_reset_n` | Active-Low | Data Mover / Uncore |
| `i_risc_reset_n` | Active-Low | RISC 프로세서 (Tensix 내부) |

### 6.3 클럭 게이팅

- **18개의 클럭 게이팅/버퍼링 모듈** (`tt_clk_gater`)이 계층적 클럭 분배 네트워크를 구성
- 탑 레벨 `tt_clk_gater`가 게이트된 클럭 신호를 제어
- 전력 소비 최적화를 위한 동적 클럭 게이팅 적용

### 6.4 클럭 도메인 크로싱 (CDC)

| 모듈 | 기법 | 용도 |
|------|------|------|
| `tt_sync3` | 3단 동기화기 | 단일 비트 신호 CDC |
| `tt_noc_sync3_pulse` | 3단 펄스 동기화기 | NoC 클럭 도메인 간 펄스 전달 |
| `tt_sync3_pulse_src` | 소스 측 펄스 동기화 | 펄스 생성 측 |
| `tt_sync3_pulse_dest` | 목적지 측 펄스 동기화 | 펄스 수신 측 |

---

## 7. DFX / 테스트 및 디버그 (DFX / Test & Debug)

### 7.1 개요

DFX(Design for Testability/Debug)는 제조 테스트, 실리콘 디버그, 필드 진단을 위한 하드웨어 인프라를 제공합니다.

### 7.2 JTAG 인터페이스

| 모듈 | 기능 |
|------|------|
| `tt_tensix_jtag` | Tensix 코어별 JTAG 디버그 접근 |
| `tt_dispatch_top_*_SDUMP_INTF` | Dispatch JTAG SDUMP — 상태 덤프 (8 포트) |

### 7.3 DFX 모듈

| 모듈 | 기능 |
|------|------|
| `tt_fpu_gtile_dfx` | FPU 타일 DFX — 클럭 입력 → DFX 처리 → 클럭 출력 |

### 7.4 테스트 모드 신호

| 신호 | 설명 |
|------|------|
| `i_test_mode` | 테스트 모드 활성화 |
| `i_test_clk_en` | 테스트 클럭 인에이블 |
| `i_tensix_harvested` | 하베스팅 상태 (결함 코어 비활성화) |

### 7.5 FB (Fuse Box) 인터페이스

`tt_dispatch_top_east_FB_INTF` (15 포트):
- 테스트 인에이블, 테스트 클럭
- 쓰기 인에이블, 셀렉트, 접근 인에이블
- 쓰기 지속 카운트, 완료 신호
- 쓰기 버퍼 전송, 읽기 데이터
- 주소, 리셋, 데이터 인터페이스

---

## 8. 보안 (Security)

### 8.1 NoC 보안 블록

**모듈:** `tt_edc1_noc_sec_block_reg`

| 항목 | 내용 |
|------|------|
| **출력 포트** | 228개 — 설정 및 상태 신호 |
| **내부 모듈** | `tt_edc1_noc_sec_block_reg_inner` — 레지스터 인터페이스 |

### 8.2 보안 설정 레지스터

| 레지스터 카테고리 | 설명 |
|-------------------|------|
| Local Node ID | 로컬 노드 식별자 설정 |
| Mesh Dimensions | 메시 네트워크 크기 설정 |
| Endpoint ID | 엔드포인트 식별자 설정 |
| Access Control | NoC 접근 제어 정책 |

---

## 9. 주요 인터페이스 요약 (Key Interface Summary)

### 9.1 탑 레벨 포트 분류

| 카테고리 | 주요 신호 | 프로토콜 |
|----------|-----------|----------|
| **AXI** | `i_axi_clk`, AXI 관련 | AMBA AXI4 |
| **NoC** | `i_noc_clk`, `i_noc_reset_n` | 커스텀 NoC (VC, Flit 기반) |
| **AI** | `i_ai_clk`, `i_ai_reset_n` | 내부 텐서 연산 |
| **DM** | `i_dm_clk`, `i_dm_uncore_reset_n` | Data Mover |
| **Tensix** | `i_tensix_reset_n` | 코어 제어 |
| **EDC** | `i_edc_reset_n` | 메모리 컨트롤러 |
| **Register** | `i_reg_psel`, `i_reg_padd` | APB-like 레지스터 접근 |
| **UCIe** | UCIe PHY/Controller | UCIe 표준 |

### 9.2 프로토콜 매핑

```
Host ──[AXI4]──► NoC2AXI Router ──[NoC Flit]──► NoC Mesh
                                                    │
                    ┌───────────────────────────────┤
                    │               │               │
                    ▼               ▼               ▼
              [NoC Flit]      [NoC Flit]      [NoC Flit]
                Tensix          EDC           Dispatch
                    │               │
                    ▼               ▼
              [Internal]      [SRAM I/F]
               L1 Cache        DRAM

Overlay ──[TileLink]──► RoCC L1 Arb ──► L1 Cache
```

---

## 10. 설계 제약 및 고려사항 (Design Constraints & Considerations)

### 10.1 CDC (Clock Domain Crossing)

- 5개 독립 클럭 도메인 간 모든 신호 교차점에 `tt_sync3` 또는 `tt_noc_sync3_pulse` 동기화기 필수
- 펄스 신호는 소스/목적지 분리 동기화 (`tt_sync3_pulse_src` / `tt_sync3_pulse_dest`)

### 10.2 하베스팅 (Harvesting)

- `i_tensix_harvested` 신호를 통해 결함 코어를 런타임에 비활성화
- 하베스팅된 코어의 NoC 노드는 패스스루 모드로 동작해야 함

### 10.3 에러 처리

- EDC: `cor_err` (정정 가능 에러) + `err_inj_vec` (에러 주입)
- 토글 기반 핸드셰이크 (`req_tgl` / `ack_tgl`)로 비동기 에러 보고

### 10.4 전력 관리

- 18개 클럭 게이팅 모듈을 통한 계층적 전력 관리
- 미사용 블록의 동적 클럭 차단

---

## 11. 개정 이력 (Revision History)

| 버전 | 날짜 | 작성자 | 변경 내용 |
|------|------|--------|-----------|
| v1.0 | 2026-04-17 | BOS-AI (자동 생성) | 초안 작성 — RTL 파싱 데이터 기반 |

---

> **참고:** 본 문서는 `tt_20260221` 파이프라인의 RTL 파싱 데이터, 자동 생성 HDD 섹션, 및 RAG 지식 베이스를 기반으로 자동 생성되었습니다. 상세 타이밍 사양, 면적 제약, 물리 설계 정보 등은 별도의 PD(Physical Design) 문서를 참조하시기 바랍니다.

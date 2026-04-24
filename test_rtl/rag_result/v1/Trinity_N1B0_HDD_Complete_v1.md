# Trinity N1B0 — Hardware Design Document (HDD)

| 항목 | 내용 |
|------|------|
| **문서 ID** | TT-HDD-TRINITY-N1B0-001 |
| **파이프라인** | `tt_20260221` |
| **Top Module** | `trinity.sv` |
| **작성일** | 2026-04-17 |
| **상태** | Draft v1.3 (Complete) |

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
   - 5.4 [NoC (Network-on-Chip) — 심화](#54-noc-network-on-chip--심화)
   - 5.5 [EDC (Embedded Data Controller) — 심화](#55-edc-embedded-data-controller--심화)
   - 5.6 [Dispatch](#56-dispatch)
   - 5.7 [Overlay (RISC-V Subsystem)](#57-overlay-risc-v-subsystem)
   - 5.8 [UCIe (Universal Chiplet Interface)](#58-ucie-universal-chiplet-interface)
6. [클럭 및 리셋 구조 (Clock & Reset Architecture)](#6-클럭-및-리셋-구조-clock--reset-architecture)
7. [DFX / 테스트 및 디버그 (DFX / Test & Debug)](#7-dfx--테스트-및-디버그-dfx--test--debug)
8. [보안 (Security)](#8-보안-security)
9. [주요 인터페이스 요약 (Key Interface Summary)](#9-주요-인터페이스-요약-key-interface-summary)
10. [설계 제약 및 고려사항 (Design Constraints & Considerations)](#10-설계-제약-및-고려사항-design-constraints--considerations)
11. [개정 이력 (Revision History)](#11-개정-이력-revision-history)
- [Appendix A: 탑 레벨 포트 리스트](#appendix-a-탑-레벨-포트-리스트-port-list)
- [Appendix B: 레지스터 맵](#appendix-b-레지스터-맵-register-map)
- [Appendix C: 타이밍 제약](#appendix-c-타이밍-제약-timing-constraints)
- [Appendix D: 물리 설계 요약](#appendix-d-물리-설계-요약-physical-design-summary)

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
| **타겟 주파수** | 2.0 GHz |
| **예상 활용률** | 52.73% |

---

## 3. 탑 레벨 블록 다이어그램 (Top-Level Block Diagram)

'''
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
'''

---

## 4. 서브모듈 계층 구조 (Sub-module Hierarchy)

'''
trinity (Top Module)
│
├── tt_tensix_with_l1                        # Tensix 코어 + L1 캐시
│   ├── tt_instrn_engine                     # 명령어 엔진
│   │   ├── tt_fpu_v2                        # FPU v2 (부동소수점 연산)
│   │   ├── tt_sfpu_wrapper                  # SFPU 래퍼
│   │   │   └── tt_sfpu_lregs               # SFPU 로컬 레지스터
│   │   ├── unpack_srca_intf                 # 소스 A 언팩 인터페이스
│   │   ├── tt_tensix_jtag                   # Tensix JTAG 디버그
│   │   ├── csr_intf                         # CSR 인터페이스
│   │   └── tt_sync3 (jtag_dbg_req_sync)     # JTAG 디버그 요청 동기화
│   ├── refclk_quadrant_or: tt_clkor2        # 레퍼런스 클럭 OR 게이트
│   ├── niu_overlay_regs_intf: csr_intf      # NIU Overlay 레지스터 인터페이스
│   ├── edc_conn_ovl_to_L1: tt_edc1_intf_connector   # EDC: Overlay → L1
│   ├── edc_conn_L1_to_T0: tt_edc1_intf_connector    # EDC: L1 → Tensix T0
│   ├── edc_conn_L1_to_overlay: tt_edc1_intf_connector # EDC: L1 → Overlay
│   └── edc_conn_*: tt_edc1_intf_connector   # 추가 EDC 커넥터들
│
├── trinity_router                           # NoC 라우터 (타일 레벨)
│   └── (NoC 라우터 인스턴스들)
│
├── tt_dispatch_top_inst_east: tt_dispatch_top_east   # Dispatch (East) — 27 포트
│   ├── tt_dispatch_top_east_SDUMP_INTF      # SDUMP 인터페이스 (8 포트)
│   └── tt_dispatch_top_east_FB_INTF         # FB 인터페이스 (15 포트)
│
├── tt_dispatch_top_inst_west: tt_dispatch_top_west   # Dispatch (West) — 27 포트
│   └── tt_dispatch_top_west_SDUMP_INTF      # SDUMP 인터페이스 (8 포트)
│
├── edc_direct_conn_nodes: tt_edc1_intf_connector     # EDC 직접 연결 노드
├── edc_loopback_conn_nodes: tt_edc1_intf_connector   # EDC 루프백 연결 노드
│
├── tt_edc1_noc_sec_block_reg               # EDC NoC 보안 블록 레지스터
│   └── tt_edc1_noc_sec_block_reg_inner     # 내부 레지스터 인터페이스
│
├── NoC Fabric                               # NoC 인터커넥트
│   ├── tt_noc2axi                           # NoC↔AXI 브릿지 (최상위)
│   │   ├── tt_noc2axi_dfx_axi_clk_inst     # DFX (AXI 클럭 도메인)
│   │   ├── tt_noc2axi_dfx_noc_clk_inst     # DFX (NoC 클럭 도메인)
│   │   ├── powergood_stdbuf: tt_stdbuf      # 파워 굿 표준 버퍼
│   │   ├── sync_noc_reset: tt_sync_reset_powergood  # NoC 리셋 동기화
│   │   └── sync_axi_reset: tt_sync_reset_powergood  # AXI 리셋 동기화
│   ├── tt_router_niu_output_if              # 라우터 NIU 출력 인터페이스
│   │   ├── in_vc_debit_remap: tt_noc_in_vc_to_out_vc_remap
│   │   ├── squash_gnt_remap: tt_noc_in_vc_to_out_vc_remap
│   │   ├── in_vc_single_flit_packet_xbar_gnt_remap: tt_noc_in_vc_to_out_vc_remap
│   │   └── rdy_remap: tt_noc_out_vc_to_in_vc_remap
│   ├── tt_noc_rr_arb                       # 라운드-로빈 중재기
│   ├── tt_noc_repeater                      # 범용 리피터
│   ├── tt_noc_repeaters_cardinal            # 카디널 리피터
│   │   └── repeater_stage: tt_noc_repeater  # 내부 리피터 스테이지
│   ├── tt_niu_vc_req_send                   # NIU VC 요청 전송
│   ├── tt_niu_vc_resp_send                  # NIU VC 응답 전송
│   ├── tt_niu_output_port                   # NIU 출력 포트
│   ├── tt_niu_mst_timeout (×6)              # NIU 마스터 타임아웃 (6 인스턴스)
│   ├── tt_noc_sync3_pulse                   # CDC 동기화
│   │   ├── tt_noc_sync3_pulse_src           # 소스 측 펄스 동기화
│   │   └── tt_noc_sync3_pulse_dest          # 목적지 측 펄스 동기화
│   └── trinity_noc2axi_router_ne_opt_FBLC   # NoC↔AXI 라우터 (최적화)
│
├── Overlay (RISC-V Subsystem)               # Chipyard 기반 RISC-V
│   ├── TTTrinityConfig_*                    # Trinity 설정 모듈들
│   ├── TTTrinityConfig_PlusArgTimeout       # 시뮬레이션 타임아웃
│   ├── TTTrinityConfig_SourceC              # TileLink SourceC
│   ├── tt_rocc_l1_arb                       # RoCC L1 중재기
│   ├── tt_fds_dispatch_reg_inner            # Dispatch 레지스터 파일
│   └── tt_fds_tensixneo_reg_inner           # TensixNeo 레지스터 파일
│
├── UCIe Block                               # 칩렛 인터페이스
│   ├── Clock & Reset Controller
│   ├── Bus Cleaner
│   └── Watchdog Timer
│
├── TDMA Subsystem                           # TDMA 중재 서브시스템
│   ├── tt_tdma_rr_arb                       # TDMA 라운드-로빈 중재기
│   └── tt_tdma_rr_interface_arbiter         # TDMA 인터페이스 중재기
│
└── Clock/Reset Infrastructure               # 클럭/리셋 인프라
    ├── tt_clk_gater (×18)                   # 계층적 클럭 게이팅
    ├── tt_clkor2                            # 클럭 OR 게이트
    ├── tt_stdbuf                            # 표준 버퍼
    ├── tt_sync3                             # 3단 동기화기
    ├── tt_sync_reset_powergood              # 파워 굿 리셋 동기화
    └── tt_noc_sync3_pulse                   # 펄스 CDC 동기화
'''

---

## 5. 주요 블록 상세 설계 (Block-Level Design)

### 5.1 Tensix Core + L1 Cache

**모듈:** `tt_tensix_with_l1` → `tt_instrn_engine`
**소스:** `tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_tensix_with_l1.sv`, `tt_instrn_engine.sv`

#### 5.1.1 개요

Tensix는 Trinity의 핵심 AI 연산 코어입니다. 명령어 엔진(`tt_instrn_engine`)이 FPU, SFPU, 언팩 유닛 등을 조율하여 텐서 연산을 수행합니다. 각 Tensix 코어는 로컬 L1 SRAM 캐시와 결합되어 데이터 지역성을 극대화합니다.

#### 5.1.2 주요 포트 — `tt_tensix_with_l1`

| 포트 | 방향 | 설명 |
|------|------|------|
| `i_dm_clk` | Input | Data Mover 클럭 |
| `o_dm_clk` | Output | Data Mover 클럭 (패스스루) |
| `i_uncore_reset_n` | Input | Uncore 리셋 |
| `o_uncore_reset_n` | Output | Uncore 리셋 (패스스루) |
| `i_noc_clk` | Input | NoC 클럭 |
| `o_noc_clk` | Output | NoC 클럭 (패스스루) |
| `i_nocclk_reset_n` | Input | NoC 클럭 리셋 |
| `o_nocclk_reset_n` | Output | NoC 클럭 리셋 (패스스루) |
| `i_power_good` | Input | 파워 굿 신호 |

> **참고:** `tt_tensix_with_l1`은 클럭/리셋 신호를 패스스루하여 타일 체인 구조를 형성합니다.

#### 5.1.3 내부 EDC 커넥터 네트워크

`tt_tensix_with_l1` 내부에는 EDC 데이터 경로를 위한 다중 커넥터가 존재합니다:

'''
                    ┌─────────────────────────────────┐
                    │       tt_tensix_with_l1          │
                    │                                   │
  Overlay ──────►   │  edc_conn_ovl_to_L1              │
                    │       │                           │
                    │       ▼                           │
                    │  ┌─────────┐                     │
                    │  │ L1 SRAM │                     │
                    │  └────┬────┘                     │
                    │       │                           │
                    │  ┌────┴────┐                     │
                    │  │         │                      │
                    │  ▼         ▼                      │
                    │  edc_conn  edc_conn               │
                    │  _L1_to_T0 _L1_to_overlay        │
                    │  │         │                      │
                    │  ▼         ▼                      │
                    │  Tensix    Overlay                │
                    │  Core T0   (readback)             │
                    │                                   │
                    │  refclk_quadrant_or: tt_clkor2    │
                    │  niu_overlay_regs_intf: csr_intf  │
                    └─────────────────────────────────┘
'''

| 인스턴스 | 모듈 | 데이터 경로 |
|----------|------|------------|
| `edc_conn_ovl_to_L1` | `tt_edc1_intf_connector` | Overlay → L1 SRAM |
| `edc_conn_L1_to_T0` | `tt_edc1_intf_connector` | L1 SRAM → Tensix Core T0 |
| `edc_conn_L1_to_overlay` | `tt_edc1_intf_connector` | L1 SRAM → Overlay (readback) |
| `refclk_quadrant_or` | `tt_clkor2` | 레퍼런스 클럭 쿼드런트 OR |
| `niu_overlay_regs_intf` | `csr_intf` | NIU Overlay CSR 레지스터 |

#### 5.1.4 주요 포트 — `tt_instrn_engine`

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

#### 5.1.5 서브모듈

| 인스턴스 | 모듈 | 기능 |
|----------|------|------|
| `fpu` | `tt_fpu_v2` | 부동소수점 연산 유닛 |
| `sfpu_wrapper` | `tt_sfpu_wrapper` | 특수 부동소수점 유닛 래퍼 |
| `unpack_srca` | `unpack_srca_intf` | 소스 A 데이터 언팩 |
| `u_tensix_jtag` | `tt_tensix_jtag` | JTAG 디버그 |
| `jtag_csr_intf` | `csr_intf` | CSR 레지스터 접근 |
| `jtag_dbg_req_sync` | `tt_sync3` | 디버그 요청 CDC 동기화 |

#### 5.1.6 하베스팅 (Harvesting)

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

### 5.4 NoC (Network-on-Chip) — 심화

**소스 디렉토리:** `tt_rtl/tt_noc/rtl/noc/`, `tt_rtl/tt_soc_noc/rtl/`
**토픽:** NoC, NIU

#### 5.4.1 개요

NoC는 Trinity 칩 내부의 모든 블록(Tensix, EDC, Dispatch, Overlay 등)을 연결하는 패킷 기반 메시 인터커넥트입니다. X/Y 좌표 기반 라우팅과 Virtual Channel(VC) 메커니즘을 사용합니다.

#### 5.4.2 NoC 라우터 아키텍처 (`tt_noc2axi`)

NoC2AXI 라우터는 NoC 패브릭과 AXI 버스 간의 프로토콜 변환을 수행하는 핵심 모듈입니다.

**소스:** `tt_rtl/tt_noc/rtl/noc2axi/tt_noc2axi.sv`

##### 5.4.2.1 라우터 포트

| 포트 | 방향 | 설명 |
|------|------|------|
| `i_axiclk` | Input | AXI 클럭 도메인 |
| `i_nocclk` | Input | NoC 클럭 도메인 |
| `i_reset_n` | Input | 리셋 (액티브-로우) |
| `i_powergood` | Input | 파워 굿 신호 |
| `i_reg_psel` | Input | APB 레지스터 셀렉트 |
| `i_reg_penable` | Input | APB 인에이블 |
| `i_reg_paddr` | Input | APB 주소 |
| `i_reg_pwrite` | Input | APB 쓰기 |
| `i_reg_pwdata` | Input | APB 쓰기 데이터 |
| `o_reg_pready` | Output | APB 레디 |
| `o_reg_prdata` | Output | APB 읽기 데이터 |

##### 5.4.2.2 라우터 서브모듈

| 인스턴스 | 모듈 | 기능 |
|----------|------|------|
| `tt_noc2axi_dfx_axi_clk_inst` | `tt_noc2axi_dfx_axi_clk` | AXI 클럭 도메인 DFX |
| `tt_noc2axi_dfx_noc_clk_inst` | `tt_noc2axi_dfx_noc_clk` | NoC 클럭 도메인 DFX |
| `powergood_stdbuf` | `tt_stdbuf` | 파워 굿 표준 버퍼 |
| `sync_noc_reset` | `tt_sync_reset_powergood` | NoC 리셋 동기화 (파워 굿 기반) |
| `sync_axi_reset` | `tt_sync_reset_powergood` | AXI 리셋 동기화 (파워 굿 기반) |

##### 5.4.2.3 VC 버퍼 파라미터 (5-포트 라우터)

NoC 라우터는 **5-포트 구조** (NIU + North + East + South + West)를 사용하며, 각 포트별 VC 버퍼 깊이가 파라미터화되어 있습니다:

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `NIU_INPUT_VC_BUFFER_DEPTH` | `ROUTER_REMOTE_INPUT_BUF_SIZE` | NIU 입력 VC 버퍼 깊이 |
| `NORTH_INPUT_VC_BUFFER_DEPTH` | `ROUTER_REMOTE_INPUT_BUF_SIZE` | 북쪽 입력 VC 버퍼 깊이 |
| `EAST_INPUT_VC_BUFFER_DEPTH` | `ROUTER_REMOTE_INPUT_BUF_SIZE` | 동쪽 입력 VC 버퍼 깊이 |
| `SOUTH_INPUT_VC_BUFFER_DEPTH` | `ROUTER_REMOTE_INPUT_BUF_SIZE` | 남쪽 입력 VC 버퍼 깊이 |
| `WEST_INPUT_VC_BUFFER_DEPTH` | `ROUTER_REMOTE_INPUT_BUF_SIZE` | 서쪽 입력 VC 버퍼 깊이 |
| `NORTH_INPUT_BUF_MAX_FLITS_PER_VC` | `ROUTER_REMOTE_INPUT_BUF_MAX_FLITS_PER_VC` | 북쪽 VC당 최대 플릿 수 |
| `EAST_INPUT_BUF_MAX_FLITS_PER_VC` | `ROUTER_REMOTE_INPUT_BUF_MAX_FLITS_PER_VC` | 동쪽 VC당 최대 플릿 수 |
| `SOUTH_INPUT_BUF_MAX_FLITS_PER_VC` | `ROUTER_REMOTE_INPUT_BUF_MAX_FLITS_PER_VC` | 남쪽 VC당 최대 플릿 수 |
| `WEST_INPUT_BUF_MAX_FLITS_PER_VC` | `ROUTER_REMOTE_INPUT_BUF_MAX_FLITS_PER_VC` | 서쪽 VC당 최대 플릿 수 |
| `NORTH_OUTPUT_MAX_FLITS_PER_VC` | `ROUTER_REMOTE_INPUT_BUF_MAX_FLITS_PER_VC` | 북쪽 출력 VC당 최대 플릿 수 |
| `EAST_OUTPUT_MAX_FLITS_PER_VC` | `ROUTER_REMOTE_INPUT_BUF_MAX_FLITS_PER_VC` | 동쪽 출력 VC당 최대 플릿 수 |
| `SOUTH_OUTPUT_MAX_FLITS_PER_VC` | `ROUTER_REMOTE_INPUT_BUF_MAX_FLITS_PER_VC` | 남쪽 출력 VC당 최대 플릿 수 |
| `WEST_OUTPUT_MAX_FLITS_PER_VC` | `ROUTER_REMOTE_INPUT_BUF_MAX_FLITS_PER_VC` | 서쪽 출력 VC당 최대 플릿 수 |

'''
                    ┌─────────────────────────────┐
                    │      NoC Router (5-Port)     │
                    │                               │
         North ◄───►│  [N_VC_BUF]  ┌──────────┐   │
                    │              │            │   │
          East ◄───►│  [E_VC_BUF]  │  Crossbar  │   │
                    │              │  + RR Arb  │   │
         South ◄───►│  [S_VC_BUF]  │            │   │
                    │              └──────────┘   │
          West ◄───►│  [W_VC_BUF]                 │
                    │                               │
           NIU ◄───►│  [NIU_VC_BUF]               │
                    │                               │
                    └─────────────────────────────┘
'''

#### 5.4.3 라우터 NIU 출력 인터페이스 (`tt_router_niu_output_if`)

**소스:** `tt_rtl/tt_noc/rtl/noc/tt_router_niu_output_if.sv`

##### 5.4.3.1 포트

| 포트 | 방향 | 설명 |
|------|------|------|
| `i_noc_x_size` | Input | NoC 메시 X 크기 |
| `i_noc_y_size` | Input | NoC 메시 Y 크기 |
| `i_local_nodeid_x` | Input | 로컬 노드 X 좌표 |
| `i_local_nodeid_y` | Input | 로컬 노드 Y 좌표 |
| `i_throttler_window_num_cycles` | Input | 스로틀러 윈도우 사이클 수 |
| `i_throttler_num_handshakes_per_window` | Input | 윈도우당 핸드셰이크 수 |

##### 5.4.3.2 파라미터

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `ENABLE_PORT_THROTTLER` | `0` | 포트 스로틀러 활성화 여부 |
| `PORT_NUM` | `NIU_PORT` | 포트 번호 |

##### 5.4.3.3 VC 리맵 서브모듈

| 인스턴스 | 모듈 | 기능 |
|----------|------|------|
| `in_vc_debit_remap` | `tt_noc_in_vc_to_out_vc_remap` | 입력 VC → 출력 VC 데빗 리맵 |
| `squash_gnt_remap` | `tt_noc_in_vc_to_out_vc_remap` | 스쿼시 그랜트 리맵 |
| `in_vc_single_flit_packet_xbar_gnt_remap` | `tt_noc_in_vc_to_out_vc_remap` | 단일 플릿 패킷 크로스바 그랜트 리맵 |
| `rdy_remap` | `tt_noc_out_vc_to_in_vc_remap` | 출력 VC → 입력 VC 레디 리맵 |

#### 5.4.4 NoC 패킷 구조 (`tt_noc_pkg.sv`)

**소스:** `tt_rtl/tt_noc/rtl/noc/tt_noc_pkg.sv`

##### 5.4.4.1 플릿 타입

| 필드 | 타입 | 설명 |
|------|------|------|
| `noc_flit_type_t` | enum | 플릿 유형 (Head, Data, Tail 등) |
| `num` | logic | 패킷 번호 |
| `x` | logic | 목적지 X 좌표 |
| `y` | logic | 목적지 Y 좌표 |
| `start_x` | logic | 멀티캐스트 시작 X |
| `start_y` | logic | 멀티캐스트 시작 Y |
| `end_x` | logic | 멀티캐스트 종료 X |
| `end_y` | logic | 멀티캐스트 종료 Y |
| `bcast_addr` | logic | 브로드캐스트 주소 |
| `src_x` | logic | 소스 X 좌표 |
| `src_y` | logic | 소스 Y 좌표 |
| `noc_x_size` | logic | NoC X 크기 |
| `noc_y_size` | logic | NoC Y 크기 |
| `x_dest_disable` | logic | X 방향 목적지 비활성화 |

##### 5.4.4.2 패킷 파라미터

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `L1_CLIENT_DISC` | `1` / `'0` | L1 클라이언트 디스커넥트 설정 |

##### 5.4.4.3 Modport

| Modport | 설명 |
|---------|------|
| `slave` | 슬레이브 인터페이스 (수신 측) |
| `master` | 마스터 인터페이스 (송신 측) |

#### 5.4.5 라우팅 알고리즘

NoC는 **XY Dimension-Order Routing**을 사용합니다:

'''
1. 소스 노드에서 패킷 생성
2. Head Flit에 목적지 (x, y) 좌표 기록
3. X 방향 먼저 라우팅 (East/West)
4. X 좌표 일치 후 Y 방향 라우팅 (North/South)
5. 목적지 노드의 NIU에서 패킷 수신

멀티캐스트/브로드캐스트:
- start_x/start_y ~ end_x/end_y 범위 내 모든 노드에 전달
- bcast_addr로 브로드캐스트 대상 지정
- x_dest_disable로 특정 X 방향 비활성화 가능
'''

**라우팅 흐름도:**

'''
  Source (src_x, src_y)
       │
       ▼
  ┌─────────────┐
  │ X 좌표 비교  │
  │ dest_x vs   │
  │ local_x     │
  └──────┬──────┘
         │
    ┌────┴────┐
    │         │
  dest_x    dest_x    dest_x
  < local   > local   = local
    │         │         │
    ▼         ▼         ▼
  West      East    ┌─────────────┐
  Port      Port    │ Y 좌표 비교  │
                    │ dest_y vs   │
                    │ local_y     │
                    └──────┬──────┘
                           │
                      ┌────┴────┐
                      │         │
                    dest_y    dest_y    dest_y
                    < local   > local   = local
                      │         │         │
                      ▼         ▼         ▼
                    South     North     NIU
                    Port      Port      (Local
                                        Delivery)
'''

#### 5.4.6 중재 방식

##### 5.4.6.1 라운드-로빈 중재 (`tt_noc_rr_arb`)

- 복수의 요청자 간 공정한 순서로 공유 자원 접근 허용
- NoC 크로스바의 출력 포트 경합 해소

##### 5.4.6.2 TDMA 중재 (`tt_tdma_rr_arb`)

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `WIDTH` | `8` | 중재 대상 수 |
| `SUPPRESSOR` | `1` | 그랜트 억제 기능 |
| `GATE_STATE_UPDATE` | `0` | 상태 업데이트 게이팅 |

| 포트 | 방향 | 설명 |
|------|------|------|
| `i_request` | Input | 요청 벡터 (WIDTH 비트) |
| `o_grant` | Output | 그랜트 벡터 (WIDTH 비트) |
| `i_update` | Input | 상태 업데이트 트리거 |

##### 5.4.6.3 TDMA 인터페이스 중재 (`tt_tdma_rr_interface_arbiter`)

- 복수 인터페이스 간 라운드-로빈 방식의 통신 관리
- TDMA 슬롯 기반 대역폭 할당

#### 5.4.7 NIU (Network Interface Unit) 상세

##### 5.4.7.1 요청 전송 (`tt_niu_vc_req_send`)

| 포트 | 방향 | 설명 |
|------|------|------|
| `i_local_nodeid_x` | Input | 로컬 노드 X 좌표 |
| `i_local_nodeid_y` | Input | 로컬 노드 Y 좌표 |
| `i_ext_req_head_flit_override` | Input | 외부 헤드 플릿 오버라이드 |
| `i_req_head_flit_vld` | Input | 요청 헤드 플릿 유효 |
| `o_req_head_flit_ack` | Output | 요청 헤드 플릿 ACK |

##### 5.4.7.2 응답 전송 (`tt_niu_vc_resp_send`)

| 포트 | 방향 | 설명 |
|------|------|------|
| `i_local_nodeid_x` | Input | 로컬 노드 X 좌표 |
| `i_local_nodeid_y` | Input | 로컬 노드 Y 좌표 |
| `i_noc_x_size` | Input | NoC 메시 X 크기 |
| `i_noc_y_size` | Input | NoC 메시 Y 크기 |
| `i_mesh_start_x` | Input | 메시 시작 X 좌표 |
| `i_mesh_start_y` | Input | 메시 시작 Y 좌표 |
| `i_mesh_end_x` | Input | 메시 종료 X 좌표 |
| `i_mesh_end_y` | Input | 메시 종료 Y 좌표 |

##### 5.4.7.3 출력 포트 (`tt_niu_output_port`)

| 포트 | 방향 | 설명 |
|------|------|------|
| `o_chan_vld` | Output | 채널 유효 |
| `o_chan_next_vld` | Output | 다음 채널 유효 (프리페치) |
| `i_chan_rd` | Input | 채널 읽기 |
| `i_chan_ack` | Input | 채널 ACK |
| `i_head_flit_vld` | Input | 헤드 플릿 유효 |
| `i_head_flit_has_data` | Input | 헤드 플릿 데이터 포함 여부 |
| `o_head_flit_*` | Output | 헤드 플릿 출력 신호들 |

##### 5.4.7.4 마스터 타임아웃 (`tt_niu_mst_timeout`)

- **인스턴스 수:** 6개 (설계 내 동일 포트/파라미터)
- **기능:** NIU 마스터 트랜잭션 타임아웃 감시
- **용도:** 응답 없는 트랜잭션 감지 및 에러 보고

#### 5.4.8 리피터 구조

##### 5.4.8.1 범용 리피터 (`tt_noc_repeater`)

'''
  Input ──► [tt_noc_repeater] ──► Output
            (tt_soc_noc_pkg)
'''

- `tt_soc_noc_pkg` 타입의 NoC 패킷을 입력받아 버퍼링 후 출력
- 장거리 배선의 타이밍 마진 확보

##### 5.4.8.2 카디널 리피터 (`tt_noc_repeaters_cardinal`)

'''
  Input ──► [tt_noc_repeaters_cardinal] ──► Output
                    │
                    └── repeater_stage: tt_noc_repeater
'''

- 내부에 `tt_noc_repeater`를 `repeater_stage`로 인스턴스화
- 카디널 방향(N/S/E/W) 전용 리피터
- 메시 토폴로지의 타일 간 패킷 전파

##### 5.4.8.3 SoC NoC 리피터 (`tt_noc_repeaters`)

**소스:** `tt_rtl/tt_soc_noc/rtl/tt_noc_repeaters.sv`

- SoC 레벨 NoC 리피터
- 내부에 `repeater_stage: tt_noc_repeater` 인스턴스화

#### 5.4.9 포트 스로틀러

NoC 라우터는 **포트 스로틀러** 기능을 지원합니다:

| 파라미터 | 설명 |
|----------|------|
| `ENABLE_PORT_THROTTLER` | 스로틀러 활성화 (기본: 비활성) |
| `i_throttler_window_num_cycles` | 스로틀링 윈도우 사이클 수 |
| `i_throttler_num_handshakes_per_window` | 윈도우당 허용 핸드셰이크 수 |

- **목적:** 특정 포트의 대역폭을 제한하여 NoC 혼잡 방지
- **메커니즘:** 윈도우 기반 — 지정된 사이클 수 내에서 최대 핸드셰이크 수를 제한

---

### 5.5 EDC (Embedded Data Controller) — 심화

**소스 디렉토리:** `tt_rtl/tt_edc/rtl/`
**토픽:** EDC

#### 5.5.1 개요

EDC는 외부 DRAM 메모리 인터페이스를 관리하는 임베디드 데이터 컨트롤러입니다. NoC를 통해 Tensix 코어 및 기타 블록의 메모리 요청을 처리합니다.

#### 5.5.2 EDC 데이터 경로 아키텍처

'''
                         ┌──────────────────────────────────────┐
                         │            EDC Subsystem              │
                         │                                        │
  NoC ──[Flit]──►        │  ┌──────────┐     ┌──────────────┐   │
                         │  │ Ingress  │────►│              │   │
                         │  │ (NoC →   │     │   EDC Node   │   │
                         │  │  EDC)    │     │              │   │
                         │  └──────────┘     │  ┌────────┐  │   │
                         │                    │  │  SRAM  │  │   │
                         │  ┌──────────┐     │  │  I/F   │  │   │──► External DRAM
                         │  │ Egress   │◄────│  └────────┘  │   │
                         │  │ (EDC →   │     │              │   │
                         │  │  NoC)    │     │  ┌────────┐  │   │
                         │  └──────────┘     │  │ Error  │  │   │
                         │                    │  │ Inject │  │   │
                         │                    │  └────────┘  │   │
                         │                    └──────────────┘   │
                         │                                        │
                         │  ┌──────────────────────────────────┐ │
                         │  │     Security Block               │ │
                         │  │  tt_edc1_noc_sec_block_reg       │ │
                         │  │  (228 output ports)              │ │
                         │  └──────────────────────────────────┘ │
                         └──────────────────────────────────────┘
'''

#### 5.5.3 EDC 패키지 인터페이스

##### 5.5.3.1 `tt_edc_pkg.sv` (범용 EDC 패키지)

| Modport | 방향 | 주요 신호 | 설명 |
|---------|------|-----------|------|
| `ingress` | 입력 | `req_tgl`, `ack_tgl` | NoC → EDC 데이터 수신 |
| `egress` | 출력 | `req_tgl`, `ack_tgl` | EDC → NoC 데이터 송신 |
| `edc_node` | 양방향 | `cor_err`, `err_inj_vec` | EDC 노드 인터페이스 |
| `sram` | 양방향 | `cor_err`, `err_inj_vec` | SRAM 접근 인터페이스 |

##### 5.5.3.2 `tt_edc1_pkg.sv` (EDC1 전용 패키지)

| Modport | 방향 | 주요 신호 | 설명 |
|---------|------|-----------|------|
| `ingress` | 입력 | `req_tgl`, `ack_tgl` | EDC1 수신 경로 |
| `egress` | 출력 | `req_tgl`, `ack_tgl` | EDC1 송신 경로 |

> **참고:** `tt_edc1_pkg`는 `tt_edc_pkg`의 경량 버전으로, `edc_node`/`sram` modport 및 에러 관련 신호가 없습니다.

#### 5.5.4 EDC 커넥터 네트워크

EDC 커넥터(`tt_edc1_intf_connector`)는 칩 전체에 걸쳐 다양한 위치에 인스턴스화됩니다:

| 위치 | 인스턴스 | 경로 |
|------|----------|------|
| **Trinity Top** | `edc_direct_conn_nodes` | 직접 연결 (저지연) |
| **Trinity Top** | `edc_loopback_conn_nodes` | 루프백 (테스트/디버그) |
| **Tensix + L1** | `edc_conn_ovl_to_L1` | Overlay → L1 SRAM |
| **Tensix + L1** | `edc_conn_L1_to_T0` | L1 SRAM → Tensix T0 |
| **Tensix + L1** | `edc_conn_L1_to_overlay` | L1 SRAM → Overlay |

#### 5.5.5 에러 처리 상세

##### 5.5.5.1 토글 기반 핸드셰이크 프로토콜

'''
  Sender                    Receiver
    │                          │
    │── req_tgl (toggle) ─────►│  요청 전송 (토글 변경)
    │                          │
    │◄── ack_tgl (toggle) ─────│  응답 확인 (토글 변경)
    │                          │
    │── req_tgl (toggle) ─────►│  다음 요청 (토글 재변경)
    │                          │
'''

- **장점:** 비동기 클럭 도메인 간 안전한 핸드셰이크
- **메커니즘:** 토글 변경 감지로 새 요청/응답 식별

##### 5.5.5.2 에러 신호

| 신호 | 방향 | 설명 |
|------|------|------|
| `cor_err` | Input (edc_node) / Output (sram) | 정정 가능 에러 플래그 |
| `err_inj_vec` | Output (edc_node) / Input (sram) | 에러 주입 벡터 |

- **정정 가능 에러 (CE):** SRAM에서 감지된 단일 비트 에러 → ECC로 자동 정정
- **에러 주입:** 테스트 목적으로 의도적 에러 생성 → ECC 검증

#### 5.5.6 보안 블록 상세 (`tt_edc1_noc_sec_block_reg`)

| 항목 | 내용 |
|------|------|
| **출력 포트** | 228개 — 설정 및 상태 신호 |
| **내부 모듈** | `tt_edc1_noc_sec_block_reg_inner` — 레지스터 인터페이스 |

**입력 설정 레지스터:**

| 레지스터 | 설명 |
|----------|------|
| Local Node ID (X, Y) | 로컬 노드 좌표 식별자 |
| Mesh Dimensions (X, Y) | 메시 네트워크 크기 |
| Endpoint ID | 엔드포인트 식별자 |
| Access Control Policies | NoC 접근 제어 정책 (R/W 권한) |

---

### 5.6 Dispatch

**모듈:** `tt_dispatch_top_east`, `tt_dispatch_top_west`
**소스:** `tt_rtl/overlay/rtl/config/dispatch/trinity/`
**토픽:** Dispatch

#### 5.6.1 개요

Dispatch 블록은 호스트로부터의 명령을 수신하여 Tensix 코어들에 분배하는 역할을 합니다. East/West 듀얼 구조로 대역폭을 확보합니다.

#### 5.6.2 포트 사양

| 포트 | 방향 | 설명 |
|------|------|------|
| `i_ai_clk` | Input | AI 클럭 |
| `i_nocclk` | Input | NoC 클럭 |
| `i_dm_clk` | Input | Data Mover 클럭 |
| `o_ai_clk` | Output | AI 클럭 (패스스루) |
| `o_nocclk` | Output | NoC 클럭 (패스스루) |
| `o_dm_clk` | Output | DM 클럭 (패스스루) |
| `i_power_good` | Input | 파워 굿 신호 |
| `i_ai_reset_n` | Input | AI 리셋 |
| `i_nocclk_reset_n` | Input | NoC 클럭 리셋 |
| `i_uncore_reset_n` | Input | Uncore 리셋 |
| `i_tensix_reset_n` | Input | Tensix 리셋 |

> **참고:** Dispatch도 클럭/리셋 패스스루 구조를 사용하여 타일 체인을 형성합니다.

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
| `i_axi_clk` / `i_axiclk` | AXI | AXI 버스 인터페이스, 호스트 통신 |
| `i_noc_clk` / `i_nocclk` | NoC | NoC 인터커넥트 패브릭 |
| `i_ai_clk` | AI | Tensix 코어 AI 연산 |
| `i_dm_clk` | DM | Data Mover, Uncore 로직 |
| `clock` (Overlay) | Overlay | RISC-V 서브시스템 |

### 6.2 리셋 신호

| 리셋 신호 | 극성 | 대상 |
|-----------|------|------|
| `i_noc_reset_n` / `i_nocclk_reset_n` | Active-Low | NoC 패브릭 |
| `i_ai_reset_n` | Active-Low | AI 연산 블록 |
| `i_tensix_reset_n` | Active-Low | Tensix 코어 전용 |
| `i_edc_reset_n` | Active-Low | EDC 메모리 컨트롤러 |
| `i_dm_uncore_reset_n` / `i_uncore_reset_n` | Active-Low | Data Mover / Uncore |
| `i_risc_reset_n` | Active-Low | RISC 프로세서 (Tensix 내부) |

### 6.3 파워 굿 기반 리셋 동기화

NoC2AXI 라우터에서 발견된 파워 굿 기반 리셋 동기화 구조:

'''
  i_powergood ──► [tt_stdbuf] ──► powergood_buffered
                                        │
                    ┌───────────────────┤
                    │                   │
                    ▼                   ▼
  [tt_sync_reset_powergood]   [tt_sync_reset_powergood]
       sync_noc_reset              sync_axi_reset
            │                           │
            ▼                           ▼
     NoC 도메인 리셋              AXI 도메인 리셋
'''

- `tt_stdbuf`: 파워 굿 신호 버퍼링
- `tt_sync_reset_powergood`: 파워 굿 조건부 리셋 동기화

### 6.4 클럭 게이팅

- **18개의 클럭 게이팅/버퍼링 모듈** (`tt_clk_gater`)이 계층적 클럭 분배 네트워크를 구성
- 탑 레벨 `tt_clk_gater`가 게이트된 클럭 신호를 제어
- 전력 소비 최적화를 위한 동적 클럭 게이팅 적용
- `tt_clkor2`: 레퍼런스 클럭 OR 게이트 (쿼드런트 레벨)

### 6.5 클럭 도메인 크로싱 (CDC)

| 모듈 | 기법 | 용도 |
|------|------|------|
| `tt_sync3` | 3단 동기화기 | 단일 비트 신호 CDC |
| `tt_noc_sync3_pulse` | 3단 펄스 동기화기 | NoC 클럭 도메인 간 펄스 전달 |
| `tt_sync3_pulse_src` | 소스 측 펄스 동기화 | 펄스 생성 측 |
| `tt_sync3_pulse_dest` | 목적지 측 펄스 동기화 | 펄스 수신 측 |
| `tt_sync_reset_powergood` | 파워 굿 리셋 동기화 | 리셋 CDC (파워 굿 조건부) |

### 6.6 클럭/리셋 패스스루 체인

Tensix 타일과 Dispatch 블록은 클럭/리셋 신호를 패스스루하여 **데이지 체인** 구조를 형성합니다:

'''
  Top ──► Tile[0] ──► Tile[1] ──► ... ──► Tile[N] ──► Dispatch
          i_clk       i_clk              i_clk        i_clk
          o_clk ─────►i_clk              o_clk ──────►i_clk
'''

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

| 모듈 | 위치 | 기능 |
|------|------|------|
| `tt_fpu_gtile_dfx` | Tensix/FPU | FPU 타일 DFX — 클럭 입력 → DFX 처리 → 클럭 출력 |
| `tt_noc2axi_dfx_axi_clk` | NoC2AXI | AXI 클럭 도메인 DFX |
| `tt_noc2axi_dfx_noc_clk` | NoC2AXI | NoC 클럭 도메인 DFX |

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

### 7.6 CSR (Control/Status Register) 인터페이스

**모듈:** `tt_csr`
**소스:** `tt_rtl/tt_briscv/rtl/tt_csr.sv`

| 포트 | 방향 | 설명 |
|------|------|------|
| `write` | Input | 쓰기 인에이블 |
| `waddr` | Input | 쓰기 주소 |
| `raddr` | Input | 읽기 주소 |
| `wdata` | Input | 쓰기 데이터 |
| `wmask` | Input | 쓰기 마스크 |
| `rdata` | Output | 읽기 데이터 |
| `i_sat_csr` | Input | SAT CSR 입력 |
| `i_csr_vl` | Input | CSR 벡터 길이 |
| `o_csr_vlmax` | Output | CSR 최대 벡터 길이 |
| `o_csr_vl` | Output | CSR 벡터 길이 출력 |

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `RISC_ID` | `0` | RISC 프로세서 ID |

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
| Local Node ID (X, Y) | 로컬 노드 좌표 식별자 설정 |
| Mesh Dimensions (X, Y) | 메시 네트워크 크기 설정 |
| Endpoint ID | 엔드포인트 식별자 설정 |
| Access Control Policies | NoC 접근 제어 정책 (R/W 권한) |

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
| **Register** | `i_reg_psel`, `i_reg_penable`, `i_reg_paddr`, `i_reg_pwrite`, `i_reg_pwdata` | APB 레지스터 접근 |
| **UCIe** | UCIe PHY/Controller | UCIe 표준 |

### 9.2 프로토콜 매핑

'''
Host ──[AXI4]──► NoC2AXI Router ──[NoC Flit]──► NoC Mesh
                  (tt_noc2axi)                      │
                  ├─ APB Reg I/F                    │
                  ├─ DFX (AXI/NoC)                  │
                  └─ PowerGood Sync                 │
                                                    │
                    ┌───────────────────────────────┤
                    │               │               │
                    ▼               ▼               ▼
              [NoC Flit]      [NoC Flit]      [NoC Flit]
                Tensix          EDC           Dispatch
                    │               │
                    ▼               ▼
              [EDC Conn]      [SRAM I/F]
               L1 Cache        DRAM
                    │
                    ▼
              [TileLink]
               Overlay (RISC-V)

Overlay ──[TileLink]──► RoCC L1 Arb ──► L1 Cache
'''

---

## 10. 설계 제약 및 고려사항 (Design Constraints & Considerations)

### 10.1 CDC (Clock Domain Crossing)

- 5개 독립 클럭 도메인 간 모든 신호 교차점에 `tt_sync3` 또는 `tt_noc_sync3_pulse` 동기화기 필수
- 펄스 신호는 소스/목적지 분리 동기화 (`tt_sync3_pulse_src` / `tt_sync3_pulse_dest`)
- 파워 굿 조건부 리셋 동기화 (`tt_sync_reset_powergood`)

### 10.2 하베스팅 (Harvesting)

- `i_tensix_harvested` 신호를 통해 결함 코어를 런타임에 비활성화
- 하베스팅된 코어의 NoC 노드는 패스스루 모드로 동작해야 함

### 10.3 에러 처리

- EDC: `cor_err` (정정 가능 에러) + `err_inj_vec` (에러 주입)
- 토글 기반 핸드셰이크 (`req_tgl` / `ack_tgl`)로 비동기 에러 보고
- NIU 마스터 타임아웃 (`tt_niu_mst_timeout` × 6)으로 행 상태 감지

### 10.4 전력 관리

- 18개 클럭 게이팅 모듈을 통한 계층적 전력 관리
- 미사용 블록의 동적 클럭 차단
- 클럭/리셋 패스스루 체인으로 타일별 독립 전력 제어 가능

### 10.5 NoC 혼잡 관리

- 포트 스로틀러 (`ENABLE_PORT_THROTTLER`)로 대역폭 제한
- VC 리맵 (`tt_noc_in_vc_to_out_vc_remap`, `tt_noc_out_vc_to_in_vc_remap`)으로 VC 할당 최적화
- 라운드-로빈 + TDMA 이중 중재 구조

---

## 11. 개정 이력 (Revision History)

| 버전 | 날짜 | 작성자 | 변경 내용 |
|------|------|--------|-----------|
| v1.0 | 2026-04-17 | BOS-AI (자동 생성) | 초안 작성 — RTL 파싱 데이터 기반 |
| v1.1 | 2026-04-17 | BOS-AI (자동 생성) | 블록 심화 — NoC/EDC/Tensix/Dispatch/CSR 상세 추가 |
| v1.2 | 2026-04-17 | BOS-AI (자동 생성) | 부록 추가 — 포트 리스트, 레지스터 맵, 타이밍 제약, 물리 설계 요약 |
| v1.3 | 2026-04-17 | BOS-AI (자동 생성) | 최종 통합본 — 상세 본문 + 부록 A, B, C, D |

---

# Appendix A: 탑 레벨 포트 리스트 (Port List)

## A.1 Trinity Top Module (`trinity.sv`) — 주요 포트

> **참고:** Trinity 탑 모듈은 총 3,519,581개의 포트를 가지고 있습니다. 아래는 RTL 파싱에서 확인된 주요 포트를 기능별로 분류한 것입니다.

### A.1.1 클럭 포트

| # | 포트명 | 방향 | 폭 | 설명 |
|---|--------|------|-----|------|
| 1 | `i_axi_clk` | Input | 1 | AXI 버스 클럭 |
| 2 | `i_noc_clk` | Input | 1 | NoC 인터커넥트 클럭 |
| 3 | `i_ai_clk` | Input | 1 | AI 연산 (Tensix) 클럭 |
| 4 | `i_dm_clk` | Input | 1 | Data Mover 클럭 |

### A.1.2 리셋 포트

| # | 포트명 | 방향 | 폭 | 극성 | 설명 |
|---|--------|------|-----|------|------|
| 5 | `i_noc_reset_n` | Input | 1 | Active-Low | NoC 패브릭 리셋 |
| 6 | `i_ai_reset_n` | Input | 1 | Active-Low | AI 연산 블록 리셋 |
| 7 | `i_tensix_reset_n` | Input | 1 | Active-Low | Tensix 코어 전용 리셋 |
| 8 | `i_edc_reset_n` | Input | 1 | Active-Low | EDC 메모리 컨트롤러 리셋 |
| 9 | `i_dm_uncore_reset_n` | Input | 1 | Active-Low | Data Mover / Uncore 리셋 |

### A.1.3 APB 레지스터 인터페이스 포트

| # | 포트명 | 방향 | 폭 | 설명 |
|---|--------|------|-----|------|
| 10 | `i_reg_psel` | Input | 1 | APB 페리페럴 셀렉트 |
| 11 | `i_reg_penable` | Input | 1 | APB 인에이블 (2nd phase) |
| 12 | `i_reg_paddr` | Input | N | APB 주소 |
| 13 | `i_reg_pwrite` | Input | 1 | APB 쓰기 (1) / 읽기 (0) |
| 14 | `i_reg_pwdata` | Input | 32 | APB 쓰기 데이터 |
| 15 | `o_reg_pready` | Output | 1 | APB 레디 (슬레이브 응답) |
| 16 | `o_reg_prdata` | Output | 32 | APB 읽기 데이터 |

### A.1.4 기타 제어 포트

| # | 포트명 | 방향 | 폭 | 설명 |
|---|--------|------|-----|------|
| 17 | `logic` (unnamed) | Input | 1 | 내부 로직 제어 신호 |

### A.1.5 포트 변형 비교 (RTL 소스별)

Trinity 탑 모듈은 여러 RTL 변형이 존재합니다:

| RTL 소스 | `i_dm_clk` | 비고 |
|----------|------------|------|
| `rtl/trinity.sv` (기본) | ✅ 있음 | 기본 버전 |
| `used_in_n1/mem_port/rtl/trinity.sv` | ✅ 있음 | N1 메모리 포트 버전 |
| `used_in_n1/rtl/trinity.sv` | ✅ 있음 | N1 기본 버전 |
| `used_in_n1/legacy/no_mem_port/rtl/trinity.sv` | ❌ 없음 | 레거시 (DM 클럭 없음) |

> **참고:** 레거시 `no_mem_port` 버전에서는 `i_dm_clk`가 제거되고 `i_reg_paddr`이 직접 노출됩니다.

---

## A.2 Trinity Router (`trinity_router.sv`) — 포트

| # | 포트명 | 방향 | 설명 |
|---|--------|------|------|
| 1 | `i_ai_clk` | Input | AI 클럭 |
| 2 | `i_nocclk` | Input | NoC 클럭 |
| 3 | `i_dm_clk` | Input | Data Mover 클럭 |
| 4 | `o_ai_clk` | Output | AI 클럭 (패스스루) |
| 5 | `o_nocclk` | Output | NoC 클럭 (패스스루) |
| 6 | `o_dm_clk` | Output | DM 클럭 (패스스루) |
| 7 | `i_ai_reset_n` | Input | AI 리셋 |
| 8 | `i_nocclk_reset_n` | Input | NoC 클럭 리셋 |
| 9 | `i_dm_uncore_reset_n` | Input | DM/Uncore 리셋 |
| 10 | `logic` (unnamed) | Input | 내부 로직 제어 |
| 11 | `i_tensix_reset_n` | Input | Tensix 리셋 |

---

## A.3 NoC2AXI N-Opt (`trinity_noc2axi_n_opt.sv`) — 포트

| # | 포트명 | 방향 | 설명 |
|---|--------|------|------|
| 1 | `i_axiclk` | Input | AXI 클럭 |
| 2 | `i_ai_clk` | Input | AI 클럭 |
| 3 | `i_nocclk` | Input | NoC 클럭 |
| 4 | `i_dm_clk` | Input | Data Mover 클럭 |
| 5 | `o_ai_clk` | Output | AI 클럭 (패스스루) |
| 6 | `o_nocclk` | Output | NoC 클럭 (패스스루) |
| 7 | `o_dm_clk` | Output | DM 클럭 (패스스루) |
| 8 | `i_ai_reset_n` | Input | AI 리셋 |
| 9 | `i_noc_reset_n` | Input | NoC 리셋 |
| 10 | `i_dm_uncore_reset_n` | Input | DM/Uncore 리셋 |
| 11 | `logic` (unnamed) | Input | 내부 로직 제어 |
| 12 | `i_tensix_reset_n` | Input | Tensix 리셋 |

---

## A.4 Dispatch Top East/West — 포트 (27 포트)

| # | 포트명 | 방향 | 설명 |
|---|--------|------|------|
| 1 | `i_ai_clk` | Input | AI 클럭 |
| 2 | `i_nocclk` | Input | NoC 클럭 |
| 3 | `i_dm_clk` | Input | Data Mover 클럭 |
| 4 | `o_ai_clk` | Output | AI 클럭 (패스스루) |
| 5 | `o_nocclk` | Output | NoC 클럭 (패스스루) |
| 6 | `o_dm_clk` | Output | DM 클럭 (패스스루) |
| 7 | `i_power_good` | Input | 파워 굿 신호 |
| 8 | `i_ai_reset_n` | Input | AI 리셋 |
| 9 | `i_nocclk_reset_n` | Input | NoC 클럭 리셋 |
| 10 | `i_uncore_reset_n` | Input | Uncore 리셋 |
| 11 | `logic` (unnamed) | Input | 내부 로직 제어 |
| 12 | `i_tensix_reset_n` | Input | Tensix 리셋 |
| 13-27 | *(NoC/메모리 컨트롤러 관련)* | Mixed | NoC 인터페이스, 메모리 컨트롤러 신호 |

---

## A.5 FB (Fuse Box) 인터페이스 — 공통 포트 (DFT)

모든 FB_INTF 모듈 (`tt_dispatch_top_east_FB_INTF`, `trinity_noc2axi_ne_opt_FB_INTF`, `tt_neo_overlay_wrapper_FB_INTF` 등)은 동일한 포트 구조를 공유합니다:

| # | 포트명 | 방향 | 설명 |
|---|--------|------|------|
| 1 | `ltest_en` | Input | 테스트 인에이블 |
| 2 | `ltest_se` | Input | 스캔 인에이블 |
| 3 | `ltest_clk` | Input | 테스트 클럭 |
| 4 | `clock` | Input | 기능 클럭 |
| 5 | `write_en` | Input | 쓰기 인에이블 |
| 6 | `select` | Input | 퓨즈 뱅크 셀렉트 |
| 7 | `access_en` | Input | 접근 인에이블 |
| 8 | `write_duration_count` | Input | 쓰기 지속 카운트 |
| 9 | `done` | Output | 완료 신호 |
| 10 | `write_buffer_transfer` | Input | 쓰기 버퍼 전송 |
| 11 | `read_data` | Output | 읽기 데이터 |
| 12 | `address` | Input | 퓨즈 주소 |
| 13 | `reset` | Input | 리셋 |
| 14 | `data` | Input | 쓰기 데이터 |

**FB_INTF가 존재하는 블록:**

| 블록 | DFT 소스 경로 |
|------|--------------|
| `tt_dispatch_top_east` | `dft/N1B0_DFT_WORKING_ML4_DEV05/IP/NPU/RTL/.BACKUP/` |
| `tt_dispatch_top_west` | 동일 |
| `trinity_noc2axi_ne_opt` | 동일 |
| `trinity_noc2axi_router_ne_opt` | 동일 |
| `tt_neo_overlay_wrapper` | 동일 |

---

# Appendix B: 레지스터 맵 (Register Map)

## B.1 APB 레지스터 인터페이스 개요

Trinity는 **APB(Advanced Peripheral Bus)** 프로토콜을 사용하여 내부 레지스터에 접근합니다.

### B.1.1 APB 프로토콜 타이밍

'''
         ┌───┐   ┌───┐   ┌───┐   ┌───┐   ┌───┐
  PCLK   │   │   │   │   │   │   │   │   │   │
  ───────┘   └───┘   └───┘   └───┘   └───┘   └───

  PSEL    ─────────────────────────┐
  ────────┘                        └───────────────

  PENABLE              ┌───────────┐
  ─────────────────────┘           └───────────────

  PADDR   ═══════════════════════════
            Valid Address

  PWRITE  ─────────────────────────
            (1=Write, 0=Read)

  PWDATA  ═══════════════════════════  (Write only)
            Valid Write Data

  PRDATA  ═══════════════════════════  (Read only)
                                Valid Read Data

  PREADY               ┌───────────┐
  ─────────────────────┘           └───────────────
            Setup Phase  Access Phase
'''

### B.1.2 APB 접근 포인트

| 접근 포인트 | 모듈 | 설명 |
|-------------|------|------|
| Trinity Top | `trinity.sv` | 탑 레벨 APB 포트 (`i_reg_psel`, `i_reg_paddr` 등) |
| NoC2AXI | `tt_noc2axi.sv` | NoC↔AXI 브릿지 내부 APB 레지스터 |
| NIU Overlay | `niu_overlay_regs_intf` | NIU Overlay CSR |

---

## B.2 CSR 레지스터 맵 (`tt_csr`)

**모듈:** `tt_csr` (RISC-V CSR)
**소스:** `tt_rtl/tt_briscv/rtl/tt_csr.sv`
**파라미터:** `RISC_ID=0`

### B.2.1 인터페이스

| 신호 | 폭 | 방향 | 설명 |
|------|-----|------|------|
| `waddr` | N | Input | 쓰기 주소 |
| `raddr` | N | Input | 읽기 주소 |
| `wdata` | 32 | Input | 쓰기 데이터 |
| `wmask` | 32 | Input | 쓰기 마스크 (비트별 인에이블) |
| `rdata` | 32 | Output | 읽기 데이터 |
| `write` | 1 | Input | 쓰기 인에이블 |

### B.2.2 주요 CSR 레지스터

| 레지스터 | 접근 | 설명 |
|----------|------|------|
| `i_sat_csr` | Read | SAT(Saturation) CSR — 포화 연산 설정 |
| `i_csr_vl` | Read | 벡터 길이 (Vector Length) 입력 |
| `o_csr_vlmax` | Read | 최대 벡터 길이 (VLMAX) |
| `o_csr_vl` | Read | 현재 벡터 길이 출력 |

---

## B.3 Tensix 내부 인터페이스 레지스터 (`tt_t6_interfaces`)

**소스:** `tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_t6_interfaces.sv`

### B.3.1 파라미터

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `DATA_WIDTH` | `32` | 데이터 폭 |
| `ADDR_WIDTH` | `32` | 주소 폭 |
| `UNIT_NAME` | `""` | 유닛 이름 (디버그용) |
| `CONFIG_WIDTH` | `1` | 설정 폭 |

### B.3.2 Modport

| Modport | 설명 |
|---------|------|
| `target` | 타겟 (슬레이브) 인터페이스 |
| `initiator` | 이니시에이터 (마스터) 인터페이스 |
| `master` | 마스터 인터페이스 |
| `slave` | 슬레이브 인터페이스 |

### B.3.3 주요 신호

| 신호 | 방향 (initiator) | 폭 | 설명 |
|------|-------------------|-----|------|
| `addr` | Output | ADDR_WIDTH | 주소 |
| `wr_data` | Output | DATA_WIDTH | 쓰기 데이터 |
| `rd_data` | Input | DATA_WIDTH | 읽기 데이터 |
| `wr_ctrl` | Output | 1 | 쓰기 제어 |
| `wr_addr` | Output | ADDR_WIDTH | 쓰기 주소 |
| `req` | Output | 1 | 요청 |
| `rsp` | Input | 1 | 응답 |
| `reqif_ready` | Input | 1 | 요청 인터페이스 레디 |

---

## B.4 EDC NoC 보안 블록 레지스터 (`tt_edc1_noc_sec_block_reg`)

**출력 포트:** 228개

### B.4.1 입력 설정 레지스터 (추정)

| 오프셋 (추정) | 레지스터명 | R/W | 폭 | 설명 |
|---------------|-----------|-----|-----|------|
| 0x000 | `LOCAL_NODE_ID_X` | R/W | N | 로컬 노드 X 좌표 |
| 0x004 | `LOCAL_NODE_ID_Y` | R/W | N | 로컬 노드 Y 좌표 |
| 0x008 | `MESH_DIM_X` | R/W | N | 메시 X 크기 |
| 0x00C | `MESH_DIM_Y` | R/W | N | 메시 Y 크기 |
| 0x010 | `ENDPOINT_ID` | R/W | N | 엔드포인트 식별자 |
| 0x014~0x3FF | `ACCESS_CTRL_*` | R/W | 32 | 접근 제어 정책 레지스터 (다수) |

> **참고:** 정확한 오프셋과 비트 필드는 `tt_edc1_noc_sec_block_reg_inner` 모듈의 RTL에서 확인 필요. 228개 출력 포트로 미루어 약 50~60개의 설정 레지스터가 존재할 것으로 추정됩니다.

---

## B.5 Overlay 레지스터 파일

### B.5.1 Dispatch 레지스터 (`tt_fds_dispatch_reg_inner`)

- **기능:** Dispatch 레지스터 파일 접근 및 갱신
- **접근:** Overlay RISC-V에서 레지스터 읽기/쓰기

### B.5.2 TensixNeo 레지스터 (`tt_fds_tensixneo_reg_inner`)

- **기능:** TensixNeo 레지스터 파일 접근 및 갱신
- **접근:** Overlay RISC-V에서 Tensix 코어 설정/상태 관리

---

# Appendix C: 타이밍 제약 (Timing Constraints)

## C.1 타겟 주파수

| 항목 | 값 | 비고 |
|------|-----|------|
| **타겟 주파수** | **2.0 GHz** | 최종 최적화 (FINAL_OPTO) 기준 |
| **클럭 주기** | **500 ps** | 1 / 2.0 GHz |

## C.2 P&R 최적화 이력

설계는 다음 단계를 거쳐 타이밍 클로저를 달성했습니다:

| 단계 | 설명 | 타겟 주파수 |
|------|------|------------|
| T09.1 FINAL_OPTO | 최종 최적화 (1차) | 2.0 GHz |
| T10 FINAL_OPTO | 최종 최적화 (2차) | 2.0 GHz |
| T10.1 CTS | 클럭 트리 합성 | 2.0 GHz |
| T11 LOGIC_OPTO | 로직 최적화 | 2.0 GHz |

## C.3 알려진 타이밍 이슈

### C.3.1 DFT 타이밍 경로 이슈

| 이슈 | 설명 | 해결 방안 |
|------|------|-----------|
| **500ps WNS DFT 경로** | Function 모드에서 예상치 못한 DFT 타이밍 경로 위반 발생 | DFT User SDC 수정 |
| **ICG 셀 SE 경로** | Tessent SDC에 ICG 셀 그룹 리스트만 있고 `balance_point` 명령 누락 → Function 모드에서 DFT 삽입 ICG 셀의 SE 경로 타이밍 이슈 | ICG 셀 그룹에 `balance_point` 명령 추가 |
| **Fast Clock 선언** | DFT User SDC에서 `I_LTEST_EXT_CLK` (fast_clock)을 모드 무관하게 선언 → DFT Shift 모드에서 의도치 않은 클럭 간 타이밍 관계 생성 | DFT Shift 모드에서 다른 클럭 간 경로를 false path로 설정하는 clock group 제약 추가 |

### C.3.2 SDC 제약 요약

'''
# 기본 클럭 정의 (추정)
create_clock -name axi_clk  -period 0.500 [get_ports i_axi_clk]
create_clock -name noc_clk  -period 0.500 [get_ports i_noc_clk]
create_clock -name ai_clk   -period 0.500 [get_ports i_ai_clk]
create_clock -name dm_clk   -period 0.500 [get_ports i_dm_clk]

# CDC False Path (클럭 도메인 간)
set_false_path -from [get_clocks axi_clk] -to [get_clocks noc_clk]
set_false_path -from [get_clocks noc_clk] -to [get_clocks axi_clk]
# ... (모든 비동기 클럭 쌍에 대해)

# DFT 모드 제약 (수정 후)
# DFT Shift 모드에서 다른 클럭 간 false path 설정
set_clock_groups -asynchronous \
  -group [get_clocks {axi_clk}] \
  -group [get_clocks {noc_clk}] \
  -group [get_clocks {ai_clk}] \
  -group [get_clocks {dm_clk}] \
  -group [get_clocks {I_LTEST_EXT_CLK}]
'''

> **참고:** 위 SDC는 RTL 분석 및 P&R 보고서에서 추정한 것입니다. 정확한 SDC는 PD 팀의 공식 제약 파일을 참조하시기 바랍니다.

## C.4 클럭 도메인 간 타이밍 관계

'''
  ┌──────────┐     ┌──────────┐
  │ axi_clk  │     │ noc_clk  │
  │ (500ps)  │     │ (500ps)  │
  └────┬─────┘     └────┬─────┘
       │                 │
       │  [Async CDC]    │
       │  tt_sync3       │
       │  tt_sync_reset  │
       │  _powergood     │
       │◄───────────────►│
       │                 │
  ┌────┴─────┐     ┌────┴─────┐
  │ ai_clk   │     │ dm_clk   │
  │ (500ps)  │     │ (500ps)  │
  └────┬─────┘     └────┬─────┘
       │                 │
       │  [Async CDC]    │
       │◄───────────────►│
       │                 │
       └────────┬────────┘
                │
         ┌──────┴──────┐
         │ overlay_clk │
         │ (별도 도메인) │
         └─────────────┘

  모든 클럭 쌍: Asynchronous (False Path)
  CDC 동기화: tt_sync3 (3-stage), tt_noc_sync3_pulse
'''

## C.5 UCIe PHY 사이드밴드 클럭

| 항목 | 값 | 설명 |
|------|-----|------|
| **sbclk (PHY)** | 800 MHz | PHY 전용 사이드밴드 클럭 |
| **sbclk (CTL)** | = lclk | 컨트롤러 사이드밴드 = 링크 클럭 |

---

# Appendix D: 물리 설계 요약 (Physical Design Summary)

## D.1 면적 및 활용률

| 항목 | 값 |
|------|-----|
| **총 셀 면적** | 2,632,703.81 (설계 유닛) |
| **예상 활용률** | 52.73% |
| **총 셀 수** | 3,994,907 |
| **매크로/블랙박스** | 2,228 |

## D.2 라이브러리

| 항목 | 값 |
|------|-----|
| **Standard Cell** | STD SF4A 라이브러리 |
| **메모리** | Memory Partial Blockage 적용 |

## D.3 P&R 플로우

'''
  RTL ──► Synthesis ──► Floorplan ──► Placement ──► CTS ──► Routing
                                                      │
                                                      ▼
                                              ┌──────────────┐
                                              │ T09.1        │
                                              │ FINAL_OPTO   │
                                              │ (2.0 GHz)    │
                                              └──────┬───────┘
                                                     │
                                              ┌──────┴───────┐
                                              │ T10          │
                                              │ FINAL_OPTO   │
                                              │ (2.0 GHz)    │
                                              └──────┬───────┘
                                                     │
                                              ┌──────┴───────┐
                                              │ T10.1 CTS    │
                                              │ (2.0 GHz)    │
                                              └──────┬───────┘
                                                     │
                                              ┌──────┴───────┐
                                              │ T11          │
                                              │ LOGIC_OPTO   │
                                              │ (2.0 GHz)    │
                                              └──────┬───────┘
                                                     │
                                                     ▼
                                              ECO Flow Flush
                                              (T06 CPU DB 기반)
                                              ├─ Prime Closure
                                              ├─ ECO P&R
                                              ├─ DRC
                                              └─ LVS
'''

## D.4 검증 체크리스트

| 검증 항목 | 상태 | 비고 |
|-----------|------|------|
| Prime Closure | ✅ 완료 | T06 CPU DB 기반 |
| ECO P&R | ✅ 완료 | ECO 플로우 플러시 |
| DRC (Design Rule Check) | ✅ 완료 | |
| LVS (Layout vs Schematic) | ✅ 완료 | |
| DFT SDC 수정 | 🔧 진행 중 | ICG balance_point, clock group 추가 |

---

> **문서 끝**
>
> 본 문서는 `tt_20260221` 파이프라인의 RTL 파싱 데이터, 자동 생성 HDD 섹션, RAG 지식 베이스, 및 P&R 보고서를 기반으로 자동 생성되었습니다.
>
> - **정확한 레지스터 오프셋/비트 필드:** RTL 소스 코드 직접 확인 필요
> - **정확한 SDC 제약:** PD 팀 공식 SDC 파일 참조
> - **물리 설계 상세:** PD 보고서 및 GDS 참조

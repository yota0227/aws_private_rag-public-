# Trinity N1B0 — Hardware Design Document (HDD)

**Pipeline ID:** `tt_20260221`  
**Top Module:** `trinity`  
**RTL Source:** `rtl-sources/tt_20260221/rtl/trinity.sv`  
**Version:** v2  
**문서 작성일:** 2026-04-20  

---

## 1. Overview

Trinity는 Tenstorrent N1B0 칩의 **코어 타일(core tile)** 모듈로, AI 연산 유닛(Tensix), 네트워크 온칩(NoC), 디스패치 로직, EDC(Embedded Data Controller) 인터페이스 등을 하나의 블록으로 통합한 SoC 빌딩 블록이다.

N1B0 칩은 다수의 Trinity 타일을 격자(grid) 형태로 배치하여 대규모 병렬 AI 연산을 수행하며, 타일 간 통신은 NoC 라우터를 통해 이루어진다.

### 설계 변형 (Variants)

| 변형 | RTL 경로 | 비고 |
|------|---------|------|
| **기본(Default)** | `rtl/trinity.sv` | 표준 타일 |
| **N1 mem_port** | `used_in_n1/mem_port/rtl/trinity.sv` | 메모리 포트 포함 |
| **N1 기본** | `used_in_n1/rtl/trinity.sv` | N1 통합용 |
| **N1 legacy (no_mem_port)** | `used_in_n1/legacy/no_mem_port/rtl/trinity.sv` | 레거시 호환, 메모리 포트 미포함 |

---

## 2. Clock & Reset Structure

Trinity 타일은 **다중 클럭 도메인** 설계를 채택하며, 각 서브시스템은 독립적인 클럭과 리셋으로 구동된다.

| 클럭/리셋 신호 | 도메인 | 설명 |
|---------------|--------|------|
| `i_axi_clk` | AXI Bus | 외부 AXI 인터페이스 클럭 |
| `i_noc_clk` | NoC | 네트워크 온칩 라우터 클럭 |
| `i_noc_reset_n` | NoC | NoC 도메인 비동기 리셋 (Active Low) |
| `i_ai_clk` | AI/Tensix | AI 연산 코어(Tensix) 클럭 |
| `i_ai_reset_n` | AI/Tensix | AI 코어 리셋 |
| `i_tensix_reset_n` | Tensix | Tensix 프로세서 전용 리셋 |
| `i_edc_reset_n` | EDC | Embedded Data Controller 리셋 |
| `i_dm_clk` | DM (Data Mover) | 데이터 무버 클럭 |
| `i_dm_uncore_reset_n` | DM Uncore | DM uncore 영역 리셋 |

### 클럭 도메인 다이어그램 (개념)

```
┌─────────────────────────────────────────────────┐
│                  Trinity Tile                     │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ AXI CLK  │  │ NoC CLK  │  │  AI/Tensix   │   │
│  │ Domain   │  │ Domain   │  │  CLK Domain  │   │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │
│       │              │               │            │
│  ┌────┴─────┐  ┌────┴─────┐  ┌──────┴───────┐   │
│  │ EDC CLK  │  │ DM CLK   │  │  Register    │   │
│  │ Domain   │  │ Domain   │  │  Interface   │   │
│  └──────────┘  └──────────┘  └──────────────┘   │
└─────────────────────────────────────────────────┘
```

---

## 3. Sub-module Hierarchy

### 3.1 인스턴스 구조

```
trinity (Top)
├── edc_direct_conn_nodes    : tt_edc1_intf_connector    — EDC 직접 연결 노드
├── edc_loopback_conn_nodes  : tt_edc1_intf_connector    — EDC 루프백 연결 노드
├── tt_tensix_with_l1        : tt_tensix_with_l1         — Tensix 코어 + L1 캐시
├── tt_dispatch_top_inst_east: tt_dispatch_top_east       — 동쪽 디스패치 유닛
├── tt_dispatch_top_inst_*   : tt_dispatch_top_*          — 기타 방향 디스패치 유닛
└── (NoC Routers)            : trinity_noc2axi_router_*  — NoC-AXI 라우터들
```

### 3.2 주요 서브모듈 설명

| 서브모듈 | 타입 | 기능 |
|---------|------|------|
| **tt_tensix_with_l1** | `tt_tensix_with_l1` | Tensix AI 프로세서 코어와 L1 SRAM 캐시를 통합한 연산 유닛. 행렬 연산, FPU 연산 등을 수행 |
| **tt_dispatch_top_east** | `tt_dispatch_top_east` | 동쪽 방향 명령 디스패치 유닛. 호스트/NoC로부터 수신한 명령을 Tensix 코어로 전달 |
| **tt_edc1_intf_connector** (direct) | `tt_edc1_intf_connector` | EDC 외부 메모리 인터페이스 직접 연결 경로 |
| **tt_edc1_intf_connector** (loopback) | `tt_edc1_intf_connector` | EDC 루프백 테스트/진단 경로 |
| **NoC Router** | `trinity_noc2axi_router_ne_opt_FBLC` | NoC ↔ AXI 프로토콜 변환 라우터 (방향별 최적화) |

---

## 4. Functional Block Description

### 4.1 Tensix AI Core (`tt_tensix_with_l1`)

- **역할:** N1B0의 핵심 연산 유닛으로 AI 추론/학습 워크로드를 처리
- **구성:** Tensix RISC-V 기반 프로세서 + FPU + 패킹/언패킹 로직 + L1 SRAM
- **클럭 도메인:** `i_ai_clk`, `i_tensix_reset_n`
- **데이터 경로:** NoC → L1 Cache → Tensix Compute → L1 Cache → NoC

### 4.2 Dispatch Unit (`tt_dispatch_top_*`)

- **역할:** 호스트 CPU 또는 다른 타일로부터 수신된 명령을 디코딩하여 Tensix 코어에 전달
- **방향별 인스턴스:** East, West, North, South 등 방향별로 인스턴스화
- **제어 경로:** AXI/NoC → Dispatch → Tensix Command Queue

### 4.3 EDC Interface (`tt_edc1_intf_connector`)

- **역할:** 외부 DRAM 또는 HBM과의 데이터 전송을 위한 Embedded Data Controller 인터페이스
- **구성:**
  - **Direct Connection:** 외부 메모리 컨트롤러와 직접 데이터 교환
  - **Loopback Connection:** 자체 테스트 및 진단용 루프백 경로
- **클럭 도메인:** `i_edc_reset_n` 별도 리셋

### 4.4 NoC Router (`trinity_noc2axi_router_ne_opt_FBLC`)

- **역할:** 타일 간 Network-on-Chip 패킷을 AXI 트랜잭션으로 변환
- **최적화:** 방향별(NE, NW, SE, SW) 최적화된 라우팅 경로
- **클럭 도메인:** `i_noc_clk`
- **프로토콜:** NoC 패킷 ↔ AXI4 Read/Write

### 4.5 Data Mover (DM)

- **역할:** 대용량 데이터 블록의 비동기 전송 (DMA 유사 기능)
- **클럭 도메인:** `i_dm_clk`, `i_dm_uncore_reset_n`

---

## 5. Register Interface

| 신호 | 방향 | 설명 |
|------|------|------|
| `i_reg_psel` | Input | APB Peripheral Select — 레지스터 접근 시 타일 선택 |
| `i_reg_paddress` | Input | APB Address — 레지스터 주소 |
| *(추가 APB 신호들)* | I/O | APB 프로토콜 기반 레지스터 R/W |

- 레지스터 인터페이스는 **APB(Advanced Peripheral Bus)** 프로토콜 기반
- 호스트 CPU에서 각 타일의 설정/상태 레지스터에 접근 시 사용

---

## 6. Data Flow (Top-Level)

```
                    ┌─────────────────┐
    Host CPU ──────►│  APB Register   │
                    │  Interface      │
                    └────────┬────────┘
                             │ Config/Status
                             ▼
┌──────────┐    ┌───────────────────────┐    ┌──────────┐
│ External │◄──►│     NoC Router        │◄──►│ Adjacent │
│ Memory   │    │ (noc2axi_router)      │    │  Tiles   │
│ (EDC)    │    └───────────┬───────────┘    └──────────┘
└──────────┘                │
                            ▼
                ┌───────────────────────┐
                │   Dispatch Unit       │
                │  (Command Decode)     │
                └───────────┬───────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │  Tensix Core + L1     │
                │  (AI Compute)         │
                └───────────────────────┘
```

---

## 7. DFX (Design for Test/Debug)

- **DFX 지원:** 별도의 DFX 블록이 파이프라인에 포함 (RTL 검색 결과 `DFX HDD` 토픽 확인)
- **EDC Loopback:** `edc_loopback_conn_nodes`를 통한 메모리 인터페이스 셀프테스트
- **레지스터 기반 디버그:** APB 인터페이스를 통한 내부 상태 관측

---

## 8. Summary & Key Design Decisions

| 항목 | 설계 결정 |
|------|----------|
| **멀티 클럭 도메인** | AI, NoC, AXI, DM, EDC 각각 독립 클럭 → 성능/전력 최적화 |
| **NoC 기반 통신** | 타일 간 패킷 기반 통신으로 확장성 확보 |
| **EDC 이중 경로** | Direct + Loopback으로 운영/테스트 모두 지원 |
| **방향별 Dispatch** | East/West 등 방향별 디스패치로 NoC 트래픽 분산 |
| **설계 변형 지원** | mem_port 유/무, legacy 호환 등 다양한 N1 통합 구성 |

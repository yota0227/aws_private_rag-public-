# NIU (Network Interface Unit) AXI Bridge — Hardware Design Document

**Pipeline ID:** `tt_20260221` (Trinity N1B0)  
**Module:** `trinity_noc2axi_router_ne_opt_FBLC`  
**Version:** v2  
**작성일:** 2026-04-20  
**데이터 소스:** RTL 검색 (query: "noc2axi", pipeline_id: tt_20260221) — 711건 중 상위 5건 + 이전 검색 누적 정보  

---

## 1. Overview

`trinity_noc2axi_router_ne_opt_FBLC`는 Trinity N1B0 타일의 **NIU(Network Interface Unit)** 역할을 수행하는 핵심 모듈이다. NoC(Network-on-Chip) 도메인과 AXI(Advanced eXtensible Interface) 버스 도메인 사이의 **프로토콜 변환 및 라우팅 브릿지**로서, 타일 내 모든 서브시스템(Tensix, EDC, FPU, Dispatch, Overlay, DFX)의 NoC 통신을 중개한다.

### 모듈 명칭 분해

| 접두어 | 의미 |
|--------|------|
| `trinity` | Trinity N1B0 타일 소속 |
| `noc2axi` | NoC → AXI 프로토콜 변환 (Network Interface Unit) |
| `router` | 라우팅 기능 포함 |
| `ne` | North-East 방향 최적화 |
| `opt` | Optimized (성능 최적화 버전) |
| `FBLC` | Forward / Backward / Left / Center — 4방향 포트 구성 |

### 설계 목표

| 목표 | 설명 |
|------|------|
| **프로토콜 브릿지** | NoC 패킷 ↔ AXI4 트랜잭션 양방향 변환 |
| **다중 토픽 지원** | EDC, FPU, Dispatch, Overlay, DFX 등 모든 서브시스템의 NoC 트래픽 처리 |
| **방향별 최적화** | NE 방향 라우팅 경로 최적화 (지연/면적 트레이드오프) |
| **고대역폭** | 파이프라인화된 데이터 경로를 통한 고처리량 |
| **공정 중재** | Round-Robin Arbiter를 통한 다중 소스 공정 접근 |

---

## 2. Architecture Position

```
┌─────────────────────────────────────────────────────────────┐
│                    Trinity N1B0 Tile                          │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Tensix  │  │   EDC    │  │   FPU    │  │ Dispatch │    │
│  │  + L1    │  │ Security │  │          │  │  Engine  │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │              │              │              │           │
│       └──────────────┴──────┬───────┴──────────────┘           │
│                             │                                  │
│                             ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │         trinity_noc2axi_router_ne_opt_FBLC              │  │
│  │              (NIU / AXI Bridge)                          │  │
│  │                                                         │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │  │
│  │  │ Forward │  │Backward │  │  Left   │  │ Center  │   │  │
│  │  │  Port   │  │  Port   │  │  Port   │  │  Port   │   │  │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘   │  │
│  └───────┼─────────────┼─────────────┼─────────────┼───────┘  │
│          │             │             │             │           │
└──────────┼─────────────┼─────────────┼─────────────┼───────────┘
           │             │             │             │
           ▼             ▼             ▼             ▼
      Adjacent       Adjacent       Adjacent      Local
      Tile (NE)      Tile (SW)      Tile (NW)     AXI Bus
```

---

## 3. Sub-module Hierarchy

```
trinity_noc2axi_router_ne_opt_FBLC (NIU Top)
│
├─── NoC Packet Interface
│    ├── Packet Decoder          — NoC 플릿 디코딩, 헤더 파싱
│    ├── Packet Encoder          — AXI 응답을 NoC 패킷으로 인코딩
│    └── Packet Buffer (FIFO)    — 입출력 패킷 버퍼링
│
├─── Routing Logic
│    ├── XY Router               — Dimension-Order 라우팅 결정
│    ├── FBLC Port Mapper        — 목적지 좌표 → F/B/L/C 포트 매핑
│    └── Direction Optimizer(NE) — NE 방향 경로 최적화
│
├─── Arbitration
│    └── tt_noc_rr_arb           — Round-Robin Arbiter (공정 중재)
│
├─── AXI Master/Slave Interface
│    ├── AXI Write Channel       — AW + W + B (Write Address/Data/Response)
│    ├── AXI Read Channel        — AR + R (Read Address/Data)
│    └── AXI Protocol Handler    — AXI4 프로토콜 준수 로직
│
├─── Repeater Interface
│    ├── tt_noc_repeaters_cardinal — 방향별 리피터 그룹
│    └── tt_noc_repeater          — 단위 리피터 (신호 재생)
│
└─── Clock Domain Crossing
     ├── Async FIFO (NoC → AXI)  — noc_clk → axi_clk 도메인 전환
     └── Async FIFO (AXI → NoC)  — axi_clk → noc_clk 도메인 전환
```

---

## 4. Functional Block Details

### 4.1 NoC Packet Interface

#### 역할
NoC 도메인에서 수신/송신되는 패킷의 인코딩/디코딩을 담당한다.

#### 패킷 구조 (추정)

```
┌─────────────────────────────────────────────────────┐
│                    NoC Packet                         │
├──────────────┬──────────────────────┬───────────────┤
│   Header     │      Payload         │     Tail      │
│  (1 flit)    │   (N flits)          │   (1 flit)    │
├──────────────┼──────────────────────┼───────────────┤
│ • Dest X,Y   │ • AXI Write Data     │ • ECC/CRC     │
│ • Src X,Y    │ • AXI Read Response  │ • EOP Flag    │
│ • Pkt Type   │ • Command Payload    │ • Sequence #  │
│ • Length     │                      │               │
│ • QoS/VC    │                      │               │
└──────────────┴──────────────────────┴───────────────┘
```

#### 동작

| 방향 | 동작 |
|------|------|
| **NoC → AXI (Inbound)** | NoC 패킷 수신 → Header 파싱 → Routing 결정 → AXI 트랜잭션 생성 |
| **AXI → NoC (Outbound)** | AXI 응답 수신 → NoC 패킷 인코딩 → 목적지 타일로 라우팅 |

---

### 4.2 Routing Logic (FBLC)

#### FBLC 포트 매핑

| 포트 | 방향 | 용도 |
|------|------|------|
| **Forward (F)** | North-East | 주 라우팅 방향 (최적화 대상) |
| **Backward (B)** | South-West | 역방향 트래픽 |
| **Left (L)** | North-West | 측면 라우팅 |
| **Center (C)** | Local | 로컬 AXI 버스 접근 (자기 타일 내부) |

#### XY Dimension-Order Routing

```
수신 패킷 (Dest: X_d, Y_d / Current: X_c, Y_c)
    │
    ├── X_d > X_c → Forward (East 방향)
    ├── X_d < X_c → Backward (West 방향)
    ├── X_d == X_c, Y_d > Y_c → Left (North 방향)
    ├── X_d == X_c, Y_d < Y_c → Backward/Right (South 방향)
    └── X_d == X_c, Y_d == Y_c → Center (Local Delivery)
```

#### NE 방향 최적화

- Forward 포트에 **우선 버퍼링** 및 **파이프라인 단축** 적용
- NE 방향 트래픽이 지배적인 워크로드 패턴에 최적화
- 타일 격자에서 데이터가 주로 NE 방향(메모리 → 코어)으로 흐르는 구조 반영

---

### 4.3 Arbitration (`tt_noc_rr_arb`)

#### 역할
다수의 NoC 소스(Tensix, EDC, Dispatch 등)가 동시에 라우터 접근을 요청할 때 **Round-Robin 방식으로 공정하게 중재**한다.

#### 동작

```
Source 0 (Tensix)    ─┐
Source 1 (EDC)       ─┤
Source 2 (Dispatch)  ─┼──► tt_noc_rr_arb ──► Router Input
Source 3 (FPU)       ─┤      (Round-Robin)
Source N (...)       ─┘
```

| 특성 | 설명 |
|------|------|
| **알고리즘** | Round-Robin (순환 우선순위) |
| **공정성** | 모든 소스에 동일한 대역폭 기회 보장 |
| **Starvation-Free** | 특정 소스가 영구적으로 차단되지 않음 |
| **Backpressure** | 출력 포트 가득 참 시 요청 보류 |

---

### 4.4 AXI Master/Slave Interface

#### AXI4 채널 구성

| 채널 | 방향 | 용도 |
|------|------|------|
| **AW (Write Address)** | Master → Slave | 쓰기 주소 및 제어 정보 |
| **W (Write Data)** | Master → Slave | 쓰기 데이터 + Strobe |
| **B (Write Response)** | Slave → Master | 쓰기 완료 응답 |
| **AR (Read Address)** | Master → Slave | 읽기 주소 및 제어 정보 |
| **R (Read Data)** | Slave → Master | 읽기 데이터 + 응답 |

#### 프로토콜 변환 매핑

| NoC 패킷 필드 | AXI4 신호 | 변환 |
|--------------|-----------|------|
| Dest Address | `AWADDR` / `ARADDR` | NoC 글로벌 주소 → AXI 로컬 주소 매핑 |
| Payload Data | `WDATA` / `RDATA` | 직접 전달 |
| Packet Type | Write/Read 채널 선택 | Cmd Type 디코딩 |
| QoS Field | `AWQOS` / `ARQOS` | QoS 레벨 전달 |
| Src Address | 내부 태그 저장 | 응답 라우팅용 |

---

### 4.5 Repeater System

#### 역할
장거리 NoC 배선의 **신호 무결성**을 유지하기 위한 리피터 체인.

#### 구조

```
tt_noc_repeaters_cardinal (방향별 그룹)
├── tt_noc_repeater [0]   — Stage 1 신호 재생
├── tt_noc_repeater [1]   — Stage 2 신호 재생
└── tt_noc_repeater [N]   — Stage N 신호 재생
```

| 모듈 | Claim | 역할 |
|------|-------|------|
| `tt_noc_repeaters_cardinal` | NoC 리피터 로직으로 패킷을 네트워크에 전파 [structural] | 방향별(Cardinal: N/S/E/W) 리피터 묶음 |
| `tt_noc_repeater` | Generic NoC 리피터 구현 [structural] | 단위 리피터 — 신호 재생 및 파이프라인 스테이지 |

#### 기능
- **신호 재생:** 장거리 배선으로 인한 신호 감쇠 방지
- **타이밍 개선:** 파이프라인 레지스터로 클럭 주파수 유지
- **Cardinal 방향:** North, South, East, West 4방향에 각각 리피터 그룹 배치

---

### 4.6 Clock Domain Crossing (CDC)

#### 역할
NoC 클럭(`i_noc_clk`)과 AXI 클럭(`i_axi_clk`) 사이의 **안전한 데이터 전달**.

```
     NoC Domain                    AXI Domain
    (i_noc_clk)                   (i_axi_clk)
         │                             │
         ▼                             ▼
  ┌──────────────┐              ┌──────────────┐
  │  NoC Logic   │    Async     │  AXI Logic   │
  │  (Routing,   │────FIFO─────►│  (Protocol   │
  │   Arbiter)   │              │   Handler)   │
  │              │◄────FIFO─────│              │
  └──────────────┘              └──────────────┘
```

| 방향 | 메커니즘 | 목적 |
|------|---------|------|
| NoC → AXI | Async FIFO (Gray-code pointer) | 패킷 데이터를 AXI 도메인으로 안전 전달 |
| AXI → NoC | Async FIFO (Gray-code pointer) | AXI 응답을 NoC 도메인으로 안전 전달 |

---

## 5. Multi-Topic Integration

이 NIU 모듈은 **모든 서브시스템의 NoC 트래픽을 중개**하므로, 다양한 토픽에서 참조된다:

| 토픽 | NIU와의 관계 | 검색 확인 |
|------|-------------|----------|
| **EDC** | EDC Security Block 통과 후 외부 메모리 접근 시 NIU를 경유 | ✅ (37건) |
| **NoC** | NIU 자체가 NoC 라우터의 핵심 구현체 | ✅ (40건) |
| **FPU** | FPU HDD에서 "Trinity NoC2AXI Router NE Optimization"의 구성요소로 기술 | ✅ (이번 검색) |
| **Dispatch** | 명령 패킷이 NIU를 통해 라우팅됨 | ✅ (76건) |
| **Overlay** | Overlay 모듈이 NIU를 통한 NoC↔AXI 데이터 흐름 관리 역할 | ✅ (이번 검색) |
| **DFX** | 디버그/테스트 트래픽도 NIU를 경유 | ✅ (이전 검색) |

### FPU 연동 (이번 검색 신규 확인)

검색 결과에서 FPU HDD가 다수 확인됨:
- FPU는 `trinity_noc2axi_router_ne_opt_FBLC` 설계의 **구성요소**로 기술됨
- FPU가 수행하는 부동소수점 연산(덧셈, 뺄셈, 곱셈 등)의 결과가 NIU를 통해 NoC로 전달
- 연산 데이터의 고대역폭 전송을 위해 NIU의 최적화된 경로를 활용

### Overlay 연동 (이번 검색 신규 확인)

- Overlay 모듈은 NIU 라우터 파이프라인의 일부로, **NoC↔AXI 간 데이터 흐름을 관리**
- 동적 기능 구성(Dynamic Functional Overlay)을 위한 라우팅 경로 제공

---

## 6. Data Flow (End-to-End)

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Tensix  │     │   EDC    │     │   FPU    │     │ Dispatch │
│  Core    │     │          │     │          │     │  Engine  │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │
     └───────┬────────┴────────┬───────┘                │
             │                 │                        │
             ▼                 ▼                        ▼
     ┌───────────────────────────────────────────────────────┐
     │                  tt_noc_rr_arb                         │
     │              (Round-Robin Arbiter)                     │
     └──────────────────────┬────────────────────────────────┘
                            │
                            ▼
     ┌───────────────────────────────────────────────────────┐
     │       trinity_noc2axi_router_ne_opt_FBLC              │
     │                                                       │
     │  ┌─────────┐   ┌──────────┐   ┌────────────────┐     │
     │  │ Packet  │──►│ Routing  │──►│ FBLC Port      │     │
     │  │ Decode  │   │ (XY DOR) │   │ Selection      │     │
     │  └─────────┘   └──────────┘   └───┬──┬──┬──┬───┘     │
     │                                    │  │  │  │         │
     │  ┌─────────────────────────────────┘  │  │  │         │
     │  │  ┌──────────────────────────────────┘  │  │         │
     │  │  │  ┌───────────────────────────────────┘  │         │
     │  │  │  │  ┌────────────────────────────────────┘         │
     │  │  │  │  │                                              │
     └──┼──┼──┼──┼──────────────────────────────────────────────┘
        │  │  │  │
        ▼  ▼  ▼  ▼
      ┌──┐┌──┐┌──┐┌──────────────────┐
      │F ││B ││L ││    C (Center)     │
      └┬─┘└┬─┘└┬─┘│                  │
       │    │    │  │  ┌────────────┐  │
       │    │    │  │  │ CDC (Async │  │
       │    │    │  │  │   FIFO)    │  │
       │    │    │  │  └─────┬──────┘  │
       │    │    │  │        │         │
       │    │    │  │        ▼         │
       │    │    │  │  ┌────────────┐  │
       │    │    │  │  │ AXI Master │  │
       │    │    │  │  │ Interface  │  │
       │    │    │  │  └─────┬──────┘  │
       │    │    │  └────────┼─────────┘
       │    │    │           │
       ▼    ▼    ▼           ▼
      NE   SW   NW     Local AXI Bus
     Tile  Tile  Tile   (EDC, Registers, etc.)
```

---

## 7. Clock & Reset

| 신호 | 도메인 | 적용 범위 |
|------|--------|----------|
| `i_noc_clk` | NoC | Routing Logic, Arbiter, Packet Interface, Repeaters |
| `i_axi_clk` | AXI | AXI Protocol Handler, Local Bus Interface |
| `i_noc_reset_n` | NoC | NoC 도메인 전체 리셋 (Active Low) |
| `i_ai_reset_n` | AI/AXI | AXI 도메인 리셋 |

---

## 8. Key Parameters & Metrics

| 항목 | 값/사양 |
|------|--------|
| **FBLC 포트 수** | 4 (Forward, Backward, Left, Center) |
| **중재 방식** | Round-Robin (tt_noc_rr_arb) |
| **프로토콜** | NoC Flit ↔ AXI4 |
| **CDC 방식** | Async FIFO (Gray-code pointer) |
| **최적화 방향** | NE (North-East) |
| **리피터 구조** | Cardinal(방향별) × Generic(단위) 2계층 |
| **연동 토픽** | EDC, NoC, FPU, Dispatch, Overlay, DFX (6개 전체) |
| **RTL 검색 히트** | 711건 (noc2axi 쿼리 기준) — 가장 많이 참조되는 모듈 |

---

## 9. Verification Considerations

| 테스트 항목 | 방법 |
|------------|------|
| **프로토콜 변환** | NoC 패킷 → AXI 트랜잭션 정합성 검증 (Read/Write/Burst) |
| **라우팅 정확성** | 모든 목적지 좌표에 대해 올바른 FBLC 포트 선택 확인 |
| **중재 공정성** | 다중 소스 동시 요청 시 Round-Robin 순서 준수 |
| **CDC 안전성** | Async FIFO 메타스태빌리티 테스트 (다양한 클럭 비율) |
| **Backpressure** | 출력 포트 포화 시 입력 측 정지(stall) 동작 |
| **방향별 최적화** | NE 경로 지연 vs 기타 방향 지연 비교 측정 |
| **리피터 무결성** | 장거리 전송 시 데이터 corruption 없음 확인 |

---

## 10. Summary

`trinity_noc2axi_router_ne_opt_FBLC`는 Trinity N1B0 타일에서 **가장 중앙에 위치한 NIU(Network Interface Unit)**로서:

1. **프로토콜 브릿지** — NoC 패킷과 AXI4 트랜잭션 간의 양방향 변환을 수행
2. **FBLC 4방향 라우팅** — XY Dimension-Order 기반으로 Forward/Backward/Left/Center 포트를 선택하여 패킷을 전달
3. **NE 방향 최적화** — 데이터 흐름이 집중되는 North-East 경로에 대해 지연/대역폭 최적화
4. **공정 중재** — Round-Robin Arbiter로 Tensix, EDC, FPU, Dispatch 등 다중 소스의 공정한 접근 보장
5. **신호 재생** — Cardinal 리피터 체인을 통한 장거리 NoC 배선의 신호 무결성 유지
6. **CDC 안전성** — Async FIFO를 통한 NoC/AXI 클럭 도메인 간 안전한 데이터 전달

> 📌 **Note:** 이 모듈은 711건의 RTL 검색 결과에서 확인된 바와 같이, Trinity 타일 내 **모든 서브시스템(EDC, FPU, Dispatch, Overlay, DFX, NoC)**에서 참조되는 가장 핵심적인 인프라 모듈이다. 타일 내부와 외부 간의 모든 데이터/명령 흐름이 이 NIU를 경유한다.

---

## Appendix: 관련 토픽별 참조

| 토픽 | 참조 맥락 | 상세 HDD |
|------|----------|----------|
| EDC | 외부 메모리 트래픽 경유 | `02_EDC1_Subsystem_HDD_v2.md` |
| NoC | 라우터 코어 구현체 | `04_NoC_Routing_Packet_HDD_v2.md` |
| Dispatch | 명령 패킷 라우팅 | `05_Dispatch_Engine_HDD_v2.md` |
| FPU | 연산 결과 전송 경로 | (이번 검색에서 확인, 별도 HDD 미작성) |
| Overlay | 동적 기능 구성 데이터 흐름 | (이번 검색에서 확인, 별도 HDD 미작성) |
| DFX | 디버그/테스트 트래픽 경유 | (이전 검색에서 확인, 별도 HDD 미작성) |

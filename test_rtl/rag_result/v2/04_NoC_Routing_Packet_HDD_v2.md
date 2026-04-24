# NoC Routing & Packet Architecture — Hardware Design Document (HDD)

**Pipeline ID:** `tt_20260221` (Trinity N1B0)  
**Topic:** NoC (Network-on-Chip)  
**Version:** v2  
**Scope:** Trinity N1B0 타일 간/내부 NoC 라우팅 및 패킷 전달 서브시스템  
**작성일:** 2026-04-20  
**데이터 소스:** RTL Claim/HDD (pipeline_id: tt_20260221, topic: NoC) — 40건 중 상위 5건  

---

## 1. Overview

NoC(Network-on-Chip)는 Trinity N1B0 칩에서 **타일 간 및 타일 내부 통신을 담당하는 패킷 기반 인터커넥트 네트워크**이다. 각 Trinity 타일은 NoC 라우터를 내장하고 있으며, 격자(Grid) 토폴로지로 연결되어 Tensix 코어, EDC, 디스패치 유닛, 외부 메모리 컨트롤러 간의 데이터와 명령을 전달한다.

### 핵심 아키텍처 요소

| 요소 | 모듈 | 역할 |
|------|------|------|
| **라우터** | `trinity_noc2axi_router_ne_opt_FBLC` | NoC ↔ AXI 프로토콜 변환, 방향별 패킷 라우팅 |
| **리피터 (Cardinal)** | `tt_noc_repeaters_cardinal` | 4방향(N/S/E/W) NoC 패킷 신호 중계 및 전파 |
| **리피터 (Generic)** | `tt_noc_repeater` | 범용 NoC 리피터 — 타이밍 클로저용 파이프라인 스테이지 |
| **아비터** | `tt_noc_rr_arb` | 라운드 로빈 중재 — 다수 요청 간 공정한 대역폭 분배 |

### 설계 목표

| 목표 | 구현 방법 |
|------|----------|
| **저지연 통신** | 방향별 최적화 라우터 (FBLC), 파이프라인 리피터 |
| **공정한 대역폭** | 라운드 로빈 아비트레이션 (`tt_noc_rr_arb`) |
| **확장성** | 격자 토폴로지 + 방향별(Cardinal) 리피터로 타일 수 확장 가능 |
| **프로토콜 호환** | NoC 패킷 ↔ AXI4 트랜잭션 변환 라우터 |

---

## 2. Sub-module Hierarchy

```
Trinity Tile (Top)
└── NoC Subsystem
    │
    ├─── trinity_noc2axi_router_ne_opt_FBLC    ← NoC↔AXI 라우터 (NE 방향 최적화)
    │    ├── Packet Parser / Header Decode
    │    ├── Routing Logic (FBLC)
    │    ├── AXI4 Read/Write Channel Bridge
    │    └── Async FIFO (CDC)
    │
    ├─── tt_noc_repeaters_cardinal             ← 4방향 리피터 묶음
    │    ├── tt_noc_repeater (North)
    │    ├── tt_noc_repeater (South)
    │    ├── tt_noc_repeater (East)
    │    └── tt_noc_repeater (West)
    │
    ├─── tt_noc_repeater                       ← 범용 리피터 (개별 인스턴스)
    │
    └─── tt_noc_rr_arb                         ← 라운드 로빈 아비터
```

---

## 3. Functional Block Details

### 3.1 NoC-AXI Router (`trinity_noc2axi_router_ne_opt_FBLC`)

#### 역할
NoC 패킷 프로토콜과 AXI4 트랜잭션 프로토콜 간의 **양방향 변환**을 수행하는 핵심 라우터. 타일 내부 AXI 버스 장치(Tensix L1, EDC, Dispatch 등)와 타일 간 NoC 네트워크를 연결한다.

#### 이름 해석

| 약어 | 의미 | 설명 |
|------|------|------|
| `noc2axi` | NoC to AXI | NoC 패킷 → AXI 트랜잭션 변환 |
| `ne` | North-East | 북동 방향 최적화 라우팅 |
| `opt` | Optimized | 성능/면적 최적화 버전 |
| `FBLC` | Forward, Backward, Left, Center | 4가지 라우팅 방향/모드 |

#### FBLC 라우팅 모델

```
                    North (Forward)
                         ▲
                         │
        West (Left) ◄────┼────► East (implied)
                         │
                         ▼
                    South (Backward)
                         
                    Center = Local Tile (Self)
```

**라우팅 결정 흐름:**

```
  NoC Packet Arrives
         │
         ▼
  ┌──────────────────────────────┐
  │  Header Decode               │
  │  • Destination Tile ID 추출   │
  │  • Packet Type 식별           │
  └──────────┬───────────────────┘
             │
             ▼
  ┌──────────────────────────────┐
  │  FBLC Routing Decision       │
  │                              │
  │  if (dest == local_tile)     │
  │    → CENTER (로컬 AXI 전달)   │
  │  else if (dest.y > cur.y)    │
  │    → FORWARD (North)         │
  │  else if (dest.y < cur.y)    │
  │    → BACKWARD (South)        │
  │  else if (dest.x != cur.x)   │
  │    → LEFT/RIGHT (East/West)  │
  └──────────┬───────────────────┘
             │
      ┌──────┼──────┬──────┐
      ▼      ▼      ▼      ▼
   Forward Backward Left  Center
   (North) (South) (West) (Local)
      │      │      │      │
      ▼      ▼      ▼      ▼
   Next    Next    Next   AXI4
   Tile    Tile    Tile   Bus
```

#### NoC → AXI 변환 (Center 경로)

```
  NoC Packet
  ┌─────────────────────────────────┐
  │ Header │ Address │ Data │ EOP   │
  └────┬────────┬────────┬────┬────┘
       │        │        │    │
       ▼        ▼        ▼    ▼
  ┌─────────────────────────────────┐
  │  AXI4 Transaction Builder       │
  │                                 │
  │  Read:  AR Channel → R Channel  │
  │  Write: AW Channel + W Channel  │
  │         → B Channel (Response)  │
  └─────────────────────────────────┘
```

#### 클럭 도메인

| 도메인 | 클럭 | 역할 |
|--------|------|------|
| NoC Side | `i_noc_clk` | NoC 패킷 수신/송신 |
| AXI Side | `i_axi_clk` | AXI4 트랜잭션 처리 |
| CDC | Async FIFO | 두 클럭 도메인 간 안전한 데이터 전달 |

---

### 3.2 Cardinal Repeaters (`tt_noc_repeaters_cardinal`)

#### 역할
4개의 기본 방향(North, South, East, West)에 대해 **NoC 패킷 신호를 중계**하는 리피터 묶음. 물리적으로 먼 타일 간의 타이밍 수렴(Timing Closure)을 보장하기 위한 파이프라인 스테이지 역할을 한다.

#### 구조 (Claim 기반)

```
tt_noc_repeaters_cardinal
├── tt_noc_repeater [North]  ←→ 북쪽 인접 타일
├── tt_noc_repeater [South]  ←→ 남쪽 인접 타일
├── tt_noc_repeater [East]   ←→ 동쪽 인접 타일
└── tt_noc_repeater [West]   ←→ 서쪽 인접 타일
```

#### 기능 상세

- **신호 중계:** NoC 패킷을 수신하여 1 사이클 지연 후 다음 타일로 전달
- **파이프라인 삽입:** 장거리 라우팅 시 타이밍 위반 방지
- **양방향 전파:** 각 방향별로 TX/RX 양방향 리피터 쌍 구성
- **패킷 무결성:** 리피터는 패킷 내용을 변경하지 않음 (투명 전달)

#### 타일 간 연결 토폴로지

```
     ┌──────────┐     ┌──────────┐     ┌──────────┐
     │  Tile    │     │  Tile    │     │  Tile    │
     │ (0,2)   │     │ (1,2)   │     │ (2,2)   │
     └────┬─────┘     └────┬─────┘     └────┬─────┘
          │ N/S Repeater    │                │
     ┌────┴─────┐     ┌────┴─────┐     ┌────┴─────┐
     │  Tile    │◄───►│  Tile    │◄───►│  Tile    │
     │ (0,1)   │ E/W │ (1,1)   │ E/W │ (2,1)   │
     └────┬─────┘ Rep └────┬─────┘ Rep └────┬─────┘
          │                │                │
     ┌────┴─────┐     ┌────┴─────┐     ┌────┴─────┐
     │  Tile    │     │  Tile    │     │  Tile    │
     │ (0,0)   │     │ (1,0)   │     │ (2,0)   │
     └──────────┘     └──────────┘     └──────────┘
     
     ◄───► = tt_noc_repeater (E/W Cardinal)
       │   = tt_noc_repeater (N/S Cardinal)
```

---

### 3.3 Generic Repeater (`tt_noc_repeater`)

#### 역할
**범용 NoC 리피터**로, Cardinal 리피터의 빌딩 블록이자 독립적으로도 인스턴스화될 수 있는 단위 모듈.

#### Claim 기반 분석

| Claim 유형 | 내용 |
|------------|------|
| **structural** | `tt_noc_repeater`는 범용 NoC 리피터를 구현 |
| **structural** | `tt_noc_repeaters_cardinal`과 `tt_noc_repeater`가 함께 NoC 패킷을 네트워크 전체에 전파하는 리피터 로직을 구현 |

#### 동작 모델

```
  Input                          Output
  NoC Packet ──► [Register Stage] ──► NoC Packet
                  (1 cycle latency)
                  
  • Valid/Ready handshake 유지
  • 패킷 헤더/데이터 변경 없음
  • 백프레셔(backpressure) 전파
```

---

### 3.4 Round-Robin Arbiter (`tt_noc_rr_arb`)

#### 역할
다수의 NoC 요청이 동시에 발생할 때 **라운드 로빈 방식으로 공정하게 중재**하여 하나의 요청을 선택하는 아비터.

#### Claim 기반 분석

| Claim 유형 | 내용 |
|------------|------|
| **structural** | `tt_noc_rr_arb`는 NoC 요청에 대한 라운드 로빈 중재 방식을 구현 |

#### 중재 동작

```
  Request Sources (예: 4방향 + Local)
  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
  │ N   │ │ S   │ │ E   │ │ W   │ │Local│
  │ Req │ │ Req │ │ Req │ │ Req │ │ Req │
  └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘
     │       │       │       │       │
     └───────┴───────┼───────┴───────┘
                     │
                     ▼
          ┌─────────────────────┐
          │   tt_noc_rr_arb     │
          │                     │
          │  Round-Robin Pointer│
          │  ┌─┐               │
          │  │►│ N → S → E →   │
          │  └─┘   W → L → N  │
          │                     │
          │  Grant Output ──────┼──► Selected Request
          └─────────────────────┘
```

#### 특성

| 항목 | 설명 |
|------|------|
| **공정성** | 모든 요청 소스가 동등한 우선순위를 가짐 |
| **기아 방지(Starvation-Free)** | 포인터가 순환하므로 특정 소스가 영구 차단되지 않음 |
| **지연** | 중재 결정까지 1 사이클 (조합 로직 + 등록) |
| **사용 위치** | 라우터 입력 포트 멀티플렉싱, 출력 포트 경합 해소 |

---

## 4. NoC Packet Structure (추정)

RTL Claim과 라우터 기능을 기반으로 추정한 패킷 구조:

```
┌──────────────────────────────────────────────────────┐
│                    NoC Packet                         │
├──────────┬──────────┬──────────┬───────────┬─────────┤
│  Header  │  Dest    │  Source  │  Payload  │  EOP/   │
│  (Type,  │  Tile    │  Tile    │  (Data)   │  CRC    │
│   Len)   │  (X,Y)  │  (X,Y)  │           │         │
├──────────┼──────────┼──────────┼───────────┼─────────┤
│  Flit 0  │  Flit 0  │  Flit 0  │  Flit 1~N │  Flit N │
│ (Header) │ (Header) │ (Header) │  (Body)   │  (Tail) │
└──────────┴──────────┴──────────┴───────────┴─────────┘
```

### 패킷 필드 설명

| 필드 | 비트 폭 (추정) | 설명 |
|------|---------------|------|
| **Packet Type** | 2~4 bits | Read Request, Write Request, Read Response, Write Response 등 |
| **Dest Tile (X,Y)** | 각 6~8 bits | 목적지 타일 좌표 — FBLC 라우팅 결정에 사용 |
| **Source Tile (X,Y)** | 각 6~8 bits | 응답 패킷의 반환 경로 |
| **Address** | 32~64 bits | AXI 변환 시 사용할 메모리/레지스터 주소 |
| **Length** | 8~16 bits | 페이로드 플릿 수 |
| **Payload** | 가변 | 실제 데이터 (AXI Write Data 또는 Read Response Data) |
| **EOP** | 1 bit | End of Packet 마커 |

### Flit 기반 전송

```
  Time →
  ┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐
  │Header  ││Body 1  ││Body 2  ││Body 3  ││Tail    │
  │Flit    ││Flit    ││Flit    ││Flit    ││Flit    │
  └────────┘└────────┘└────────┘└────────┘└────────┘
  
  각 Flit는 i_noc_clk 1 사이클에 전송
  Valid/Ready handshake로 흐름 제어
```

---

## 5. Data Flow — End-to-End 패킷 여정

```
Source Tile (1,0)                              Dest Tile (2,2)
┌─────────────┐                                ┌─────────────┐
│ Tensix Core │                                │ EDC1 (L1)   │
│ Write Req   │                                │ Write Commit│
└──────┬──────┘                                └──────▲──────┘
       │ AXI Write                                    │ AXI Write
       ▼                                              │
┌──────────────────┐                          ┌──────────────────┐
│ Router (1,0)     │                          │ Router (2,2)     │
│ AXI→NoC Convert  │                          │ NoC→AXI Convert  │
│ FBLC: Forward    │                          │ FBLC: Center     │
└──────┬───────────┘                          └──────▲───────────┘
       │ NoC Packet                                  │ NoC Packet
       ▼                                              │
┌──────────────────┐                          ┌──────────────────┐
│ Repeater (1,0→N) │                          │ Repeater (2,1→N) │
│ 1 cycle delay    │                          │ 1 cycle delay    │
└──────┬───────────┘                          └──────▲───────────┘
       │                                              │
       ▼                                              │
┌──────────────────┐    RR Arb     ┌──────────────────┐
│ Router (1,1)     │──────────────►│ Router (2,1)     │
│ FBLC: Forward+   │  E/W Grant   │ FBLC: Forward    │
│       Right      │              │                  │
└──────────────────┘              └──────────────────┘

Hop Count: (1,0)→(1,1)→(2,1)→(2,2) = 3 hops
Latency:   3 hops × (1 router + 1 repeater) = ~6 cycles (최소)
```

---

## 6. Control & Arbitration Flow

```
┌─────────────────────────────────────────────────┐
│              Router Input Stage                   │
│                                                   │
│  From North ──┐                                  │
│  From South ──┤                                  │
│  From East  ──┼──► tt_noc_rr_arb ──► Route ──►  │
│  From West  ──┤      (Round-Robin)    Decision   │
│  From Local ──┘                         │        │
│                                         ▼        │
│                                  ┌─────────────┐ │
│                                  │ Output Port  │ │
│                                  │ Selection    │ │
│                                  │ (FBLC)       │ │
│                                  └──────┬──────┘ │
│                                         │        │
│                    ┌────────┬────────┬───┴───┐    │
│                    ▼        ▼        ▼       ▼    │
│                 To North To South To East To Local│
└─────────────────────────────────────────────────┘
```

---

## 7. Clock & Reset

| 신호 | 대상 | 설명 |
|------|------|------|
| `i_noc_clk` | 라우터, 리피터, 아비터 전체 | NoC 도메인 기본 클럭 |
| `i_noc_reset_n` | NoC 전체 | 비동기 리셋 (Active Low) |
| `i_axi_clk` | 라우터 AXI 측 | AXI 도메인 (CDC 경계) |

---

## 8. Key Design Specifications

| 항목 | 사양 |
|------|------|
| **토폴로지** | 2D Mesh (Grid) |
| **라우팅 알고리즘** | FBLC (Forward/Backward/Left/Center) — XY 라우팅 변형 |
| **중재 방식** | Round-Robin (`tt_noc_rr_arb`) |
| **리피터 지연** | 1 cycle per hop (파이프라인 스테이지) |
| **방향 수** | 4 Cardinal (N/S/E/W) + 1 Local (Center) |
| **프로토콜 변환** | NoC Packet ↔ AXI4 (Read/Write) |
| **CDC** | Async FIFO (NoC CLK ↔ AXI CLK) |
| **흐름 제어** | Valid/Ready handshake + Backpressure |
| **RTL 데이터** | 40건 (topic: NoC, pipeline: tt_20260221) |

---

## 9. Verification Considerations

| 테스트 항목 | 방법 | 핵심 체크포인트 |
|------------|------|---------------|
| **라우팅 정확성** | 모든 (src, dest) 타일 쌍에 대해 패킷 전달 검증 | FBLC 방향 결정이 올바른지 확인 |
| **아비트레이션 공정성** | 다수 포트 동시 요청 시 Grant 분포 분석 | Round-Robin 포인터가 순환하는지 확인 |
| **리피터 무결성** | 장거리(multi-hop) 패킷의 데이터 비교 | 리피터 통과 전후 패킷 동일성 |
| **백프레셔** | 수신측 FIFO Full 상태에서 송신측 Stall 검증 | 데이터 손실 없음 확인 |
| **CDC** | NoC↔AXI 경계에서 비동기 전송 | 메타스태빌리티, FIFO 오버플로우 |
| **데드락** | 순환 의존성 시나리오 주입 | 네트워크 교착 상태 미발생 확인 |
| **성능** | 다양한 트래픽 패턴(uniform, hotspot, burst) | 지연 시간, 처리량 측정 |

---

## 10. Summary

Trinity N1B0의 NoC 서브시스템은 **4개의 핵심 모듈**로 구성된다:

1. **`trinity_noc2axi_router_ne_opt_FBLC`** — NoC↔AXI 프로토콜 변환 라우터. FBLC(Forward/Backward/Left/Center) 알고리즘으로 패킷의 다음 홉을 결정하며, NE 방향에 최적화된 구현체이다.

2. **`tt_noc_repeaters_cardinal`** — 4방향(N/S/E/W) 리피터 묶음. 내부에 `tt_noc_repeater` 인스턴스를 포함하여 타일 간 물리적 거리에 따른 타이밍 문제를 해결한다.

3. **`tt_noc_repeater`** — 범용 단위 리피터. 1사이클 파이프라인 스테이지로 동작하며 패킷을 투명하게 전달한다.

4. **`tt_noc_rr_arb`** — 라운드 로빈 아비터. 다수의 입력 포트에서 동시에 도착하는 NoC 요청을 공정하게 중재하여 기아(starvation) 없는 대역폭 분배를 보장한다.

이들이 결합하여 **2D Mesh 토폴로지 위에서 패킷 기반, 멀티홉, 공정 중재 방식의 저지연 인터커넥트**를 구현한다.

> 📌 **Note:** 이 HDD는 40건의 NoC Claim/HDD 데이터 중 반환된 상위 5건(structural claim 3건, hdd_section 2건)을 기반으로 작성되었습니다. 나머지 35건에 NoC FIFO, 패킷 파서, 에러 핸들링, QoS 로직 등의 추가 모듈 정보가 포함될 수 있습니다.

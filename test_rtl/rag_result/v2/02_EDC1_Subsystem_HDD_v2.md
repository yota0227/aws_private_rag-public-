# EDC1 (Embedded Data Controller 1) — Hardware Design Document

**Pipeline ID:** `tt_20260221`  
**Topic:** EDC  
**Top-Level Scope:** Trinity N1B0 Tile → EDC1 Subsystem  
**Version:** v2  
**문서 작성일:** 2026-04-20  
**데이터 소스:** RTL Claim (pipeline_id: tt_20260221, topic: EDC) — 37건 중 상위 5건  

---

## 1. Overview

EDC1(Embedded Data Controller 1)은 Trinity N1B0 타일 내에서 **외부 메모리(DRAM/HBM) 접근을 관리하는 핵심 서브시스템**이다. NoC(Network-on-Chip)와 외부 메모리 인터페이스 사이의 데이터 전달, 보안 제어, 레지스터 구성을 담당하며, 다음 세 가지 주요 기능 블록으로 구성된다:

1. **BIU (Bus Interface Unit)** — SoC APB4 버스와 내부 CSR 간의 브릿지
2. **NoC Security Block** — NoC 트래픽에 대한 보안 정책 적용 및 접근 제어
3. **NoC-AXI Router** — NoC 패킷과 AXI 트랜잭션 간의 프로토콜 변환

### 설계 목표

| 목표 | 설명 |
|------|------|
| **고대역폭 메모리 접근** | Tensix 코어 ↔ 외부 DRAM 간 저지연/고대역폭 데이터 전송 |
| **보안 격리** | NoC Security Block을 통한 메모리 영역별 접근 제어 |
| **유연한 구성** | APB4 레지스터 인터페이스를 통한 런타임 설정 변경 |
| **듀얼 연결 모드** | Direct Connection + Loopback 모드 지원 |

---

## 2. Sub-module Hierarchy

```
trinity (Top)
└── EDC1 Subsystem
    │
    ├─── tt_edc1_biu_soc_apb4_wrap              ← APB4 Bus Interface Unit
    │    └── edc1_biu_soc_apb4_inner            ← APB4 코어 로직
    │
    ├─── tt_edc1_noc_sec_block_reg              ← NoC Security Block 레지스터 (Outer)
    │    └── tt_edc1_noc_sec_block_reg_inner    ← Security Block 레지스터 코어 (Inner)
    │
    ├─── edc_direct_conn_nodes                  ← 외부 메모리 직접 연결
    │    └── tt_edc1_intf_connector
    │
    └─── edc_loopback_conn_nodes                ← 셀프테스트 루프백 연결
         └── tt_edc1_intf_connector
```

---

## 3. Functional Block Details

### 3.1 BIU — Bus Interface Unit (`tt_edc1_biu_soc_apb4_wrap`)

#### 역할
APB4(Advanced Peripheral Bus 4) 버스와 EDC1 내부 CSR(Configuration/Status Register) 사이의 **프로토콜 브릿지**. 호스트 CPU가 EDC1의 모든 설정/상태 레지스터에 접근하는 유일한 경로이다.

#### 구조 (Claim 기반)

| 계층 | 모듈 | 설명 |
|------|------|------|
| Wrapper | `tt_edc1_biu_soc_apb4_wrap` | APB4 트랜잭션 핸들링, 인터럽트 생성 |
| Inner Core | `edc1_biu_soc_apb4_inner` | APB4 입출력 포트 구현, CSR R/W 로직 |

#### 기능 상세

- **Read/Write Handling:** APB4 버스로부터의 레지스터 읽기/쓰기 요청을 수신하여 내부 CSR에 전달
- **Interrupt Generation:** EDC1 내부 이벤트(에러, 완료 등)를 APB4 인터럽트 신호로 변환하여 호스트에 통보
- **Address Decoding:** APB4 주소를 내부 CSR 오프셋으로 매핑

#### 인터페이스

```
                    APB4 Bus (Host CPU Side)
                         │
            ┌────────────┴────────────┐
            │ tt_edc1_biu_soc_apb4_wrap│
            │                          │
            │  ┌────────────────────┐  │
            │  │edc1_biu_soc_apb4   │  │   ──► Interrupt Output
            │  │      _inner        │  │
            │  └────────┬───────────┘  │
            └───────────┼──────────────┘
                        │
                  Internal CSR Bus
                  (to Security Block,
                   Data Path, etc.)
```

---

### 3.2 NoC Security Block (`tt_edc1_noc_sec_block_reg`)

#### 역할
NoC를 통해 EDC1에 도달하는 모든 트래픽에 대해 **보안 정책을 적용**하는 접근 제어 블록. 메모리 영역별 읽기/쓰기 권한, 보안 레벨 등을 레지스터 기반으로 구성한다.

#### 구조 (Claim 기반)

| 계층 | 모듈 | 설명 |
|------|------|------|
| Outer | `tt_edc1_noc_sec_block_reg` | Security Block 레지스터 인터페이스 (228개 출력 포트) |
| Inner | `tt_edc1_noc_sec_block_reg_inner` | 레지스터 코어 — 보안 설정 저장 및 제공 |

#### 기능 상세

- **228개 출력 포트:** 보안 정책 구성 및 상태 신호를 하위 로직에 제공
  - 메모리 영역별 접근 허용/차단 비트
  - 보안 레벨(Secure/Non-Secure) 설정
  - 접근 위반 상태 플래그
- **레지스터 인터페이스:** BIU를 통해 APB4로 접근 가능
- **런타임 구성:** 소프트웨어에서 보안 정책을 동적으로 변경 가능

#### 보안 제어 흐름

```
  NoC Packet (Incoming)
         │
         ▼
  ┌──────────────────────────┐
  │ tt_edc1_noc_sec_block_reg│
  │                          │
  │  Security Policy Check:  │
  │  • Source ID 검증         │
  │  • Address Range 검증     │
  │  • Secure/Non-Secure 체크 │
  │  • R/W Permission 체크    │
  │                          │
  │  228 Config/Status Ports │
  │  ◄── APB4 (via BIU)     │
  └──────────┬───────────────┘
             │
     ┌───────┴───────┐
     ▼               ▼
  ALLOW           BLOCK
  (→ EDC Data    (→ Error
    Path)         Response)
```

---

### 3.3 EDC Interface Connectors (`tt_edc1_intf_connector`)

#### Direct Connection (`edc_direct_conn_nodes`)

- **역할:** NoC ↔ 외부 메모리 컨트롤러 간 **실제 데이터 전송 경로**
- **용도:** 정상 운영 모드에서의 메모리 읽기/쓰기
- **데이터 흐름:** Tensix Core → NoC → Security Block → Direct Connector → External Memory

#### Loopback Connection (`edc_loopback_conn_nodes`)

- **역할:** 외부 메모리 없이 EDC 인터페이스를 **자체 테스트**하는 경로
- **용도:** DFX/BIST(Built-In Self-Test), 제조 테스트, 디버그
- **데이터 흐름:** Write Data → Loopback Connector → Read Data (동일 경로 회귀)

```
                  NoC
                   │
          ┌────────┴────────┐
          ▼                 ▼
  ┌──────────────┐  ┌──────────────┐
  │   Direct     │  │  Loopback    │
  │  Connector   │  │  Connector   │
  │              │  │              │
  │  → External  │  │  → Self-loop │
  │    Memory    │  │    (Test)    │
  └──────────────┘  └──────────────┘
```

---

### 3.4 NoC-AXI Router (`trinity_noc2axi_router_ne_opt_FBLC`)

#### 역할
EDC 파이프라인 내에서 **NoC 패킷 프로토콜과 AXI4 트랜잭션 프로토콜 간의 변환**을 수행하는 최적화 라우터.

#### 기능

- **프로토콜 변환:** NoC 플릿(flit) ↔ AXI4 Read/Write 채널
- **방향별 최적화:** NE(North-East) 방향에 최적화된 라우팅 로직 (FBLC = Forward Backward Left Center)
- **버퍼링:** NoC/AXI 클럭 도메인 간 비동기 FIFO를 통한 데이터 버퍼링
- **QoS 지원:** 우선순위 기반 트래픽 스케줄링

---

## 4. Control Path

```
Host CPU
   │
   │ APB4
   ▼
┌──────────────────────┐
│  tt_edc1_biu_soc     │ ◄── 레지스터 R/W, 인터럽트 생성
│  _apb4_wrap          │
└──────────┬───────────┘
           │ Internal CSR Bus
    ┌──────┴──────────────────┐
    ▼                         ▼
┌──────────────────┐  ┌──────────────┐
│ noc_sec_block_reg│  │  EDC Data    │
│ (Security Config)│  │  Path Config │
│ 228 output ports │  │              │
└──────────────────┘  └──────────────┘
```

---

## 5. Clock & Reset (EDC1 Scope)

| 신호 | 용도 |
|------|------|
| `i_axi_clk` | AXI 인터페이스 클럭 (NoC-AXI Router) |
| `i_noc_clk` | NoC 도메인 클럭 (Security Block, Router) |
| `i_edc_reset_n` | EDC1 전용 비동기 리셋 (Active Low) |
| `i_noc_reset_n` | NoC 도메인 리셋 |

---

## 6. Key Design Specifications

| 항목 | 사양 |
|------|------|
| **Security Block 출력 포트** | 228개 (구성 + 상태) |
| **버스 프로토콜** | APB4 (제어), AXI4 (데이터), NoC (타일 간) |
| **연결 모드** | Direct + Loopback (듀얼) |
| **인터럽트** | BIU에서 생성, APB4를 통해 호스트로 전달 |
| **보안 기능** | 영역별 R/W 접근 제어, Secure/Non-Secure 분리 |

---

## 7. Verification & DFX Considerations

| 항목 | 방법 |
|------|------|
| **Loopback 테스트** | `edc_loopback_conn_nodes`를 통한 외부 메모리 없이 데이터 경로 검증 |
| **레지스터 검증** | APB4 R/W 시퀀스로 228개 Security Block 레지스터 전수 검증 |
| **인터럽트 검증** | BIU에서 생성되는 인터럽트 시나리오별 검증 |
| **보안 위반 테스트** | 잘못된 주소/권한으로 접근 시 Block 동작 확인 |

---

## 8. Summary

EDC1 서브시스템은 Trinity N1B0 타일에서 **외부 메모리 접근의 데이터 경로, 보안, 구성**을 모두 책임지는 통합 블록이다.

- **BIU** (`tt_edc1_biu_soc_apb4_wrap`)가 호스트와의 제어 채널을 제공하고
- **Security Block** (`tt_edc1_noc_sec_block_reg`)이 228개 포트를 통해 세밀한 접근 제어를 수행하며
- **Interface Connector**가 Direct/Loopback 듀얼 경로로 운영과 테스트를 모두 지원하고
- **NoC-AXI Router**가 프로토콜 변환과 트래픽 라우팅을 최적화한다

> 📌 이 문서는 RTL Claim 데이터(connectivity, behavioral, structural)와 HDD 섹션 데이터를 기반으로 작성되었습니다. 총 37건의 EDC 관련 데이터 중 상위 5건을 활용하였으며, 나머지 32건에 추가 모듈 정보가 포함될 수 있습니다.

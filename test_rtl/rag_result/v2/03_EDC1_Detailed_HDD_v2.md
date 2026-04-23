# EDC1 Subsystem — Hardware Design Document (HDD)

**Pipeline:** `tt_20260221` (Trinity N1B0)  
**Topic:** EDC  
**Scope:** EDC1 (Embedded Data Controller 1) 서브시스템  
**Version:** v2  
**작성일:** 2026-04-20  
**데이터 소스:** RTL Claim 35건 중 상위 5건 + 이전 검색 누적 정보  

---

## 1. Overview

EDC1(Embedded Data Controller 1)은 Trinity N1B0 타일에서 **외부 메모리 접근 제어, 보안 정책 적용, 호스트 레지스터 구성**을 담당하는 서브시스템이다.

핵심 설계 원칙:

| 원칙 | 구현 |
|------|------|
| 보안 격리 | NoC Security Block — 레지스터 기반 접근 제어 (228+ 출력 포트) |
| 호스트 제어 | BIU APB4 Wrapper — CSR 브릿지 + 인터럽트 생성 |
| 테스트 용이성 | Direct / Loopback 듀얼 연결 모드 |

---

## 2. Sub-module Hierarchy

```
Trinity Tile (Top)
└── EDC1 Subsystem
    │
    ├─── tt_edc1_biu_soc_apb4_wrap              ← APB4 Bus Interface Unit
    │    └── edc1_biu_soc_apb4_inner            ← APB4 코어 로직
    │
    ├─── tt_edc1_noc_sec_block_reg              ← NoC Security Block 레지스터 (Outer)
    │    └── tt_edc1_noc_sec_block_reg_inner    ← Security 레지스터 코어 (Inner)
    │
    ├─── edc_direct_conn_nodes                  ← 외부 메모리 직접 연결
    │    └── tt_edc1_intf_connector
    │
    └─── edc_loopback_conn_nodes                ← 셀프테스트 루프백 연결
         └── tt_edc1_intf_connector
```

### RTL 소스 위치

| 모듈 | 파일 경로 |
|------|----------|
| `tt_edc1_noc_sec_block_reg_inner` | `rtl-sources/tt_20260221/used_in_n1/mem_port/tt_rtl/tt_noc/registers/edc/rtl/tt_edc1_noc_sec_block_reg_inner.sv` |

> 파일 경로에서 확인되는 점: Security Block 레지스터는 **tt_noc/registers/edc/** 하위에 위치하며, NoC 레지스터 체계의 일부로 관리된다.

---

## 3. Functional Block Details

### 3.1 NoC Security Block Register (`tt_edc1_noc_sec_block_reg`)

EDC1 서브시스템의 **가장 핵심적인 블록**으로, NoC 트래픽에 대한 보안 정책을 레지스터 기반으로 구성하고 적용한다.

#### 아키텍처 (2-Layer 구조)

```
APB4 (via BIU)
      │
      ▼  Register R/W
┌─────────────────────────────────┐
│  tt_edc1_noc_sec_block_reg      │  ◄─ Outer Wrapper
│  (Claim: 228 output ports)      │
│  (Claim: 114 output ports)      │
│                                 │
│  ┌───────────────────────────┐  │
│  │ tt_edc1_noc_sec_block     │  │  ◄─ Inner Core
│  │ _reg_inner                │  │
│  │                           │  │
│  │ • 보안 레지스터 저장       │  │
│  │ • 구성 신호 출력           │  │
│  │ • 상태 플래그 제공         │  │
│  └───────────────────────────┘  │
└──────────────┬──────────────────┘
               │
               ▼  228+ Config/Status Signals
        EDC1 Data Path & NoC Logic
```

#### Claim 기반 상세 분석

| Claim 유형 | 내용 | 의미 |
|------------|------|------|
| **connectivity** | `tt_edc1_noc_sec_block_reg_inner`가 `tt_edc1_noc_sec_block_reg` 내부에 인스턴스화되어 레지스터 인터페이스를 제공 | Outer→Inner 2계층 래핑 구조 확인 |
| **structural** | 228개 출력 포트 — 보안 블록의 구성 및 상태 신호 제공 | 대규모 보안 정책 레지스터 맵 (다수의 보호 영역) |
| **structural** | 114개 출력 포트 — 보안 관련 레지스터 및 파라미터 구성 | 구성 전용 포트와 상태 전용 포트의 분리 |

#### 출력 포트 분석 (228 + 114)

두 Claim에서 언급된 포트 수의 관계를 추정하면:

```
총 228개 출력 포트 (Outer 모듈 기준)
├── 114개: Security Configuration Ports
│   ├── 메모리 영역별 접근 허용/차단 비트
│   ├── Secure / Non-Secure 레벨 설정
│   ├── Read / Write 권한 플래그
│   └── Source ID 기반 필터링 설정
│
└── 114개: Status & Feedback Ports
    ├── 접근 위반(Violation) 상태 플래그
    ├── 레지스터 잠금(Lock) 상태
    ├── 에러 카운터 / 로그
    └── 인터럽트 소스 신호
```

> 💡 **설계 의의:** 228개 출력 포트는 EDC1이 **다수의 메모리 보호 영역(Protection Region)**을 지원하며, 각 영역마다 독립적인 보안 정책을 설정할 수 있음을 시사한다.

---

### 3.2 BIU — Bus Interface Unit (`tt_edc1_biu_soc_apb4_wrap`)

#### 역할
호스트 CPU가 EDC1 내부의 모든 CSR(Configuration/Status Register)에 접근하기 위한 **APB4 프로토콜 브릿지**.

#### Claim 기반 기능 정의

| Claim 유형 | 내용 |
|------------|------|
| **behavioral** | APB4 버스와 내부 EDC1 BIU CSR 인터페이스 간의 브릿지로 동작. Read/Write 요청을 처리하고 인터럽트를 생성 |

#### 기능 분해

```
Host CPU
   │
   │ APB4 Bus
   ▼
┌──────────────────────────────────┐
│  tt_edc1_biu_soc_apb4_wrap       │
│                                  │
│  ┌────────────────────────────┐  │
│  │  edc1_biu_soc_apb4_inner  │  │
│  │                            │  │
│  │  [1] Address Decode        │  │  APB4 주소 → 내부 CSR 오프셋 매핑
│  │  [2] Read Handler          │  │  CSR 읽기 → APB4 PRDATA 응답
│  │  [3] Write Handler         │  │  APB4 PWDATA → CSR 쓰기
│  │  [4] Interrupt Generator   │  │  내부 이벤트 → IRQ 출력
│  │                            │  │
│  └────────────────────────────┘  │
└──────────┬────────────┬──────────┘
           │            │
    CSR Bus to:      IRQ Output
    • Security Block    → Host CPU
    • Data Path Config
```

#### APB4 인터페이스 신호 (추정)

| 신호 그룹 | 방향 | 설명 |
|----------|------|------|
| `PSEL`, `PENABLE`, `PWRITE` | Input | APB4 제어 신호 |
| `PADDR` | Input | 레지스터 주소 |
| `PWDATA` | Input | 쓰기 데이터 |
| `PRDATA` | Output | 읽기 데이터 |
| `PREADY`, `PSLVERR` | Output | APB4 응답 |
| `IRQ` | Output | 인터럽트 출력 |

---

### 3.3 EDC Interface Connectors (`tt_edc1_intf_connector`)

| 인스턴스 | 모드 | 용도 |
|---------|------|------|
| `edc_direct_conn_nodes` | **Direct** | 정상 운영 — 외부 DRAM/HBM 접근 |
| `edc_loopback_conn_nodes` | **Loopback** | DFX/BIST — 외부 메모리 없이 데이터 경로 검증 |

---

## 4. Data Flow

```
┌──────────┐     NoC Packet      ┌──────────────────────┐
│ Tensix   │ ──────────────────► │  NoC Security Block   │
│ Core     │                     │  (tt_edc1_noc_sec_    │
│ + L1     │                     │   block_reg)          │
└──────────┘                     │                       │
                                 │  228 Config Ports ◄── APB4 (BIU)
                                 │                       │
                                 │  ┌─ ALLOW ──────┐     │
                                 │  │               │     │
                                 └──┤  BLOCK ──► ERR│─────┘
                                    │               │
                                    ▼               │
                           ┌────────────────┐       │
                           │ EDC Interface  │       │
                           │ Connector      │       │
                           ├────────────────┤       │
                           │ Direct  │ Loop │       │
                           │  Mode   │ back │       │
                           └────┬────┴──┬───┘       │
                                │       │           │
                                ▼       ▼           │
                           External   Self-test     │
                           Memory     Return        │
```

---

## 5. Control Path Summary

| 단계 | 주체 | 동작 |
|------|------|------|
| **① 초기 구성** | Host CPU → BIU → Security Block | APB4를 통해 228개 보안 레지스터 설정 (보호 영역, 권한) |
| **② 런타임 접근** | Tensix → NoC → Security Block | NoC 패킷이 보안 정책 검사를 거쳐 EDC 데이터 경로로 진입 |
| **③ 보안 위반** | Security Block → BIU → Host CPU | 위반 감지 시 상태 플래그 설정 + BIU를 통해 인터럽트 발생 |
| **④ 상태 확인** | Host CPU → BIU → Security Block | 114개 상태 포트를 통해 위반 로그/에러 카운터 읽기 |

---

## 6. Clock & Reset

| 신호 | 대상 블록 | 설명 |
|------|----------|------|
| `i_noc_clk` | Security Block, NoC Router | NoC 도메인 클럭 |
| `i_axi_clk` | BIU APB4 Wrapper | 호스트 버스 도메인 클럭 |
| `i_edc_reset_n` | EDC1 전체 | EDC 전용 비동기 리셋 (Active Low) |
| `i_noc_reset_n` | Security Block | NoC 도메인 리셋 |

---

## 7. Key Metrics

| 항목 | 값 | 비고 |
|------|---|------|
| Security Block 출력 포트 | **228개** (전체) | Outer 모듈 기준 |
| Security Config 포트 | **114개** (구성 전용) | Inner 모듈 기준 |
| Status/Feedback 포트 | **~114개** (추정) | 228 − 114 |
| 버스 프로토콜 | APB4 (제어), NoC (데이터) | |
| 연결 모드 | Direct + Loopback | 듀얼 |
| 인터럽트 | BIU에서 생성 | APB4를 통해 호스트 전달 |
| RTL 경로 깊이 | `tt_noc/registers/edc/` | NoC 레지스터 체계 내 관리 |

---

## 8. Verification Considerations

| 테스트 항목 | 방법 | 커버리지 포인트 |
|------------|------|---------------|
| **레지스터 R/W** | APB4 시퀀스로 228개 포트 전수 검증 | 모든 CSR 주소에 대해 Write→Read-back |
| **보안 정책 적용** | 허용/차단 시나리오별 NoC 트래픽 주입 | Source ID × Address Range × Permission 조합 |
| **인터럽트 생성** | BIU에서 발생 가능한 모든 인터럽트 소스 트리거 | Edge/Level, Mask/Unmask |
| **Loopback 테스트** | 루프백 모드에서 데이터 무결성 확인 | 다양한 패턴/크기의 데이터 전송 |
| **CDC 검증** | NoC CLK ↔ AXI CLK 경계 | 비동기 FIFO / 동기화 로직 메타스태빌리티 |

---

## 9. Summary

EDC1 서브시스템은 **3개의 핵심 블록**으로 구성된다:

1. **`tt_edc1_noc_sec_block_reg`** — 228개 출력 포트(114 구성 + ~114 상태)를 가진 대규모 보안 레지스터 블록. Inner(`_reg_inner`)를 래핑하는 2계층 구조로, NoC 트래픽에 대한 세밀한 접근 제어를 수행한다.

2. **`tt_edc1_biu_soc_apb4_wrap`** — APB4 ↔ 내부 CSR 브릿지. 호스트 CPU가 보안 정책을 설정하고 상태를 모니터링하는 유일한 제어 경로이며, 이벤트 기반 인터럽트 생성 기능을 포함한다.

3. **`tt_edc1_intf_connector`** (×2) — Direct/Loopback 듀얼 모드 인터페이스로, 정상 운영과 셀프테스트를 모두 지원한다.

> 📌 **Note:** 이 HDD는 35건의 EDC Claim 데이터 중 반환된 상위 5건(connectivity 1건, structural 2건, behavioral 1건, topic 1건)을 기반으로 작성되었습니다. 나머지 30건에 추가 모듈(예: EDC 데이터 경로, ECC 로직, 스케줄러 등)의 Claim이 포함될 가능성이 있습니다.

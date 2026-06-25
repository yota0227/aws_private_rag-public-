# Implementation Plan: spec-parser-library

> **Created:** 2026-06-22
> **Updated:** 2026-06-22
> **Purpose:** spec-parser-library pip 패키지 구현 태스크 목록 — 저장소 구조 생성부터 배포 repo 이전 준비까지
> **Spec / Project:** `.kiro/specs/spec-parser-library/`
> **Status:** Draft

---

## Overview

`src/spec_parser/` 레이아웃으로 독립 pip 패키지를 구현한다.
기존 `parser/drawio_parser.py`는 수정하지 않고, `_internal/drawio_parser_impl.py`로 복사해 패키지가 외부 의존 없이 완전히 독립 동작하도록 한다.
배포 시에는 `src/`, `pyproject.toml`, `tests/` 만 별도 repo로 복사하면 된다.

---

## Tasks

- [x] 1. 저장소 구조 및 pyproject.toml 생성
  - `src/spec_parser/`, `src/spec_parser/interfaces/`, `src/spec_parser/_internal/`, `tests/` 디렉토리 생성
  - `src/spec_parser/__init__.py` 빈 파일(stub) 생성 — 공개 API는 Task 8에서 완성
  - `src/spec_parser/exceptions.py` 생성 — `ParseError(message, filepath, cause)` 클래스
  - `pyproject.toml` 작성: build-backend=hatchling, name=spec-parser-library, python>=3.10, dependencies=[openpyxl>=3.1, lxml>=4.9], packages=["src/spec_parser"]
  - `tests/conftest.py` 생성 — 샘플 파일 경로 fixture (`SAMPLE_DRAWIO`, `SAMPLE_XLSX`) 정의
  - _Requirements: 7.1, 7.2, 7.3, 7.6, 8.1_

- [x] 2. 내부 파서 모듈 포함 (_internal)
  - `parser/drawio_parser.py`를 `src/spec_parser/_internal/drawio_parser_impl.py`로 복사
  - `src/spec_parser/_internal/__init__.py` 생성 (빈 파일 — 내부 네임스페이스 패키지 표시)
  - 복사본에서 외부 import 의존성 없음을 확인 (`parser.*` import 없음 — 독립 모듈)
  - _Requirements: 8.2, 8.3 (변형: _internal 전략)_

- [x] 3. 인터페이스 dataclass 구현
  - [x] 3.1 `src/spec_parser/interfaces/node.py` 구현
    - `Node(id, name, node_type, source, extra: dict)` dataclass
    - `Edge(id, source_id, target_id, edge_type, label: str = "")` dataclass
    - _Requirements: 1.2, 1.3_
  - [x] 3.2 `src/spec_parser/interfaces/address_region.py` 구현
    - `AddressRegion(ip_name, blk_name, base_address, limit_address, size_bytes: int, description, address_map)` dataclass
    - _Requirements: 1.4_
  - [x] 3.3 `src/spec_parser/interfaces/parse_issue.py` 구현
    - `ParseIssue(issue_type, source_ref, description)` dataclass
    - _Requirements: 1.5_
  - [x] 3.4 `src/spec_parser/interfaces/parse_result.py` 구현
    - `ParseResult(nodes, edges, address_regions, issues)` dataclass, 모든 필드 `field(default_factory=list)`
    - _Requirements: 1.1_
  - [x] 3.5 `src/spec_parser/interfaces/merged_node.py` 구현
    - `MergedNode(node_id: Optional[str], name: str, address_region: Optional[AddressRegion], node: Optional[Node] = None)` dataclass
    - _Requirements: 6.1, 6.2_
  - [x] 3.6 `src/spec_parser/interfaces/__init__.py` 구현
    - `Node`, `Edge`, `AddressRegion`, `ParseIssue`, `ParseResult`, `MergedNode` 재수출
    - _Requirements: 1.6_

- [x] 4. DrawioParser 래퍼 구현
  - [x] 4.1 `src/spec_parser/drawio_parser.py` 구현 — DrawioParser 클래스
    - `__init__(self, filepath: str)`: `Path(filepath).exists()` 검사 → `FileNotFoundError` raise
    - `parse(self) -> ParseResult`: `_internal.drawio_parser_impl.DrawioParser` 호출, `ET.ParseError` / 기타 예외 → `ParseError` wrapping
    - import 경로: `from spec_parser._internal.drawio_parser_impl import DrawioParser as _InternalDrawioParser, DrawioNode, DrawioEdge, QualityIssue`
    - _Requirements: 2.1, 2.5, 2.6_
  - [x] 4.2 DrawioNode → Node 매핑 함수 구현
    - `source="drawio"`, `extra`에 `label`, `node_type`, `fill_color`, `stroke_color`, `x`, `y`, `width`, `height`, `props`, `page_name` 포함
    - _Requirements: 2.2_
  - [x] 4.3 DrawioEdge → Edge, QualityIssue → ParseIssue 매핑 구현
    - `edge_type`, `label` 원본 값 그대로 전달
    - `QualityIssue.cell_id → ParseIssue.source_ref`, `issue_type`·`description` 그대로
    - _Requirements: 2.3, 2.4_
  - [ ]* 4.4 Property-based test: DrawioParser 필드 매핑 보존 (Property 1)
    - **Property 1: DrawioParser field mapping preserves source and extra keys**
    - `@given(st.builds(DrawioNode, ...))` — 임의 `DrawioNode` 생성 후 내부 매핑 함수 호출
    - `mapped.source == "drawio"` 및 `extra`에 필수 키 8개 모두 존재 검증
    - `@given(st.builds(DrawioEdge, ...))` — `Edge.edge_type == original.edge_type`, `Edge.label == original.label`
    - **Validates: Requirements 2.2, 2.3**
  - [ ]* 4.5 Property-based test: QualityIssue 완전 전달 (Property 2)
    - **Property 2: QualityIssue → ParseIssue complete forwarding**
    - N개 `QualityIssue` 목록 → `ParseResult.issues` 개수가 정확히 N임을 검증
    - **Validates: Requirements 2.4**

- [x] 5. Checkpoint — DrawioParser 동작 확인
  - `pip install -e .` 실행 후 `from spec_parser import DrawioParser` import 성공 확인
  - `sample/Abel_block_diagram (ML2_DEV01).drawio` 파일로 `DrawioParser(path).parse()` 실행 → `ParseResult` 반환 확인
  - 존재하지 않는 경로로 호출 시 `FileNotFoundError` raise 확인
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. ExcelParser 구현
  - [x] 6.1 `src/spec_parser/excel_parser.py` — ExcelParser 클래스 뼈대 및 파일 검증
    - `__init__(self, filepath: str)`: `Path(filepath).exists()` 검사 → `FileNotFoundError` raise
    - `openpyxl.load_workbook(data_only=True)` 호출 → 실패 시 `ParseError` raise
    - 시트 존재 여부 사전 확인: 없는 시트마다 `ParseIssue(issue_type="MISSING_SHEET")` 기록
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [x] 6.2 `_find_blk_groups(ws)` 함수 구현 — ATLAS_CA720_MM BLK 그룹 검출
    - row 1에서 `"BLK"` 헤더 스캔 → `(blk_col, addr_col, ip_col)` 튜플 목록 반환 (1-indexed)
    - _Requirements: 3.2_
  - [ ]* 6.3 Property-based test: BLK 그룹 검출 정확성 (Property 5)
    - **Property 5: BLK group detection correctness**
    - `@given(st.lists(st.integers(min_value=1, max_value=50), min_size=1, max_size=10, unique=True))` — 임의 컬럼 위치에 "BLK" 배치한 합성 워크시트 생성
    - `_find_blk_groups` 반환 그룹 수 == BLK 헤더 수, 각 그룹의 `ip_col - blk_col == 2` 검증
    - **Validates: Requirements 3.2**
  - [x] 6.4 ATLAS_CA720_MM 시트 파싱 구현
    - row 2부터 순회: BLK명 읽기 (해당 그룹 blk_col, row 2), 행별 IP/Addr 셀 처리
    - Reserved(case-insensitive) 또는 IP+Addr 모두 빈 행 → skip; IP 비어있고 Addr 있음 → `ip_name=""` 로 생성
    - `limit_address=""`, `size_bytes=0`, `address_map="ATLAS_CA720_MM"` 고정
    - _Requirements: 3.1, 3.3, 3.4, 3.5, 3.6, 3.7, 9.1_
  - [ ]* 6.5 Property-based test: ATLAS_CA720_MM address_map 태그 불변성 (Property 4)
    - **Property 4: ATLAS_CA720_MM address_map tag invariant**
    - 실제 샘플 xlsx 파싱 후, `address_map == "ATLAS_CA720_MM"` 인 모든 `AddressRegion`에 대해 `limit_address == ""`, `size_bytes == 0` 검증
    - **Validates: Requirements 3.4, 3.6**
  - [ ]* 6.6 Property-based test: 행 필터링 — Reserved/빈 IP 건너뜀 (Property 6)
    - **Property 6: Row filtering skips Reserved and empty IP cells**
    - `@given(st.sampled_from(["reserved", "RESERVED", "Reserved", ""]))` 를 IP 셀에 주입한 합성 워크시트
    - 해당 행에 대한 `AddressRegion`이 생성되지 않음 검증
    - MM-CPU/MM-SAFE description이 "Reserved"(case-insensitive)인 행도 동일 검증
    - **Validates: Requirements 3.7, 4.6**
  - [x] 6.7 `_find_data_start(ws)` 함수 구현 — MM-CPU/MM-SAFE 헤더 행 검출
    - col 1 값이 `"Base Address (HEX)"` 인 행 번호 반환; 없으면 -1 반환
    - _Requirements: 4.2_
  - [x] 6.8 MM-CPU / MM-SAFE 시트 파싱 구현
    - col 1 → `base_address`, col 2 → `limit_address`, col 4 → `size_bytes` (int 변환), col 8 → `description`
    - `blk_name=""`, `ip_name=""`, `address_map="MM-CPU"` 또는 `"MM-SAFE"`
    - base_address 빈 행 skip; description "Reserved" 행 skip
    - size 정수 변환 실패 → `ParseIssue(issue_type="INVALID_SIZE")`, `size_bytes=0`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 9.1_
  - [ ]* 6.9 Property-based test: MM-CPU/SAFE 컬럼 매핑 불변성 (Property 7)
    - **Property 7: MM-CPU/SAFE column mapping invariants**
    - 합성 시트로 파싱 → 모든 결과에서 `blk_name == ""`, `ip_name == ""`, `address_map` 정확성, `base_address == raw_cell_value` 검증
    - **Validates: Requirements 4.3, 4.4, 4.5, 9.1**
  - [ ]* 6.10 Property-based test: INVALID_SIZE 오류 처리 (Property 8)
    - **Property 8: INVALID_SIZE error handling for non-integer size cells**
    - `@given(st.one_of(st.text(), st.none(), st.floats().map(str)))` — 정수 변환 불가 값 주입
    - `issue_type == "INVALID_SIZE"` ParseIssue 기록, `size_bytes == 0` 검증
    - **Validates: Requirements 4.7**

- [x] 7. NodeMerger 구현
  - [x] 7.1 `src/spec_parser/node_merger.py` — NodeMerger 클래스 구현
    - `merge(self, drawio_result: ParseResult, excel_result: ParseResult) -> list[MergedNode]`
    - `{ name.lower() → list[Node] }` 딕셔너리 구성
    - `address_regions` 순회: `ip_name.lower()` 매칭 → MergedNode 생성 (매칭 실패 시 `node_id=None`)
    - 매칭 안 된 Node → `MergedNode(address_region=None, node=node)`
    - 퍼지 매칭 금지: `a.lower() == b.lower()` 비교만 허용
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [x] 7.2 복수 AddressRegion 처리 구현
    - 동일 `ip_name`에 K개 `AddressRegion`이 있을 때 K개 MergedNode 생성
    - _Requirements: 6.6_
  - [ ]* 7.3 Property-based test: NodeMerger 매칭 정확성 및 완전성 (Property 9)
    - **Property 9: NodeMerger matching correctness and completeness**
    - `@given(st.lists(st.builds(Node, ...)), st.lists(st.builds(AddressRegion, ...)))` — 임의 Node/AddressRegion 생성
    - 총 MergedNode 수 == `N + M - (매칭 쌍 수)` 공식 검증
    - 매칭 안 된 Node → `address_region is None`, 매칭 안 된 AddressRegion → `node_id is None`
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
  - [ ]* 7.4 Property-based test: 복수 address_map 카디널리티 (Property 10)
    - **Property 10: Multiple address_map cardinality**
    - `@given(st.integers(min_value=1, max_value=10))` — K개의 동일 ip_name AddressRegion 생성
    - 해당 Node에 대해 정확히 K개 MergedNode 생성됨 검증
    - **Validates: Requirements 6.6**

- [x] 8. 공개 API 및 패키지 통합
  - `src/spec_parser/__init__.py` 완성 — `DrawioParser`, `ExcelParser`, `NodeMerger`, `ParseResult`, `Node`, `Edge`, `AddressRegion`, `ParseIssue`, `MergedNode`, `ParseError` 모두 재수출
  - `__all__` 목록 정의
  - _Requirements: 7.4, 7.5_

- [x] 9. Checkpoint — ExcelParser / NodeMerger 통합 확인
  - `sample/architecture/MemoryMap/INFO_MemoryMap_Atlas_ML3_DEV02.xlsx` 파일로 `ExcelParser(path).parse()` 실행
  - `address_regions` 비어있지 않음, `issues` 내용 확인
  - DrawioParser + ExcelParser 결과로 `NodeMerger().merge()` 실행 → `MergedNode` 목록 확인
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. 단위 테스트 작성
  - [x] 10.1 `tests/test_interfaces.py` 작성
    - 모든 dataclass 인스턴스화 및 필드 접근 테스트
    - `from spec_parser.interfaces import ...` 임포트 성공 확인
    - `from spec_parser import DrawioParser, ExcelParser, NodeMerger, ParseError` 공개 API 확인
    - _Requirements: 1.1–1.6, 7.4_
  - [x] 10.2 `tests/test_drawio_parser.py` 작성
    - 샘플 drawio 파일 파싱 → `ParseResult` 반환, `nodes` 비어있지 않음
    - 존재하지 않는 경로 → `FileNotFoundError`
    - 손상된 XML 파일(임시 파일 생성) → `ParseError`
    - _Requirements: 2.1, 2.5, 2.6_
  - [x] 10.3 `tests/test_excel_parser.py` 작성
    - 샘플 xlsx → `address_regions` 비어있지 않음, ATLAS_CA720_MM / MM-CPU / MM-SAFE 각각 포함 확인
    - `base_address` 원문 보존 확인 (예: `"0x2082_0000"` 형태)
    - `ATLAS_CA720_MM` 시트 없는 xlsx → `MISSING_SHEET` ParseIssue
    - `MM-CPU` 시트 없는 xlsx → `MISSING_SHEET` ParseIssue, `MM-SAFE` 정상 파싱
    - 존재하지 않는 경로 → `FileNotFoundError`
    - 손상된 xlsx → `ParseError`
    - _Requirements: 3.1–3.7, 4.1–4.7, 5.1–5.4, 9.1_
  - [x] 10.4 `tests/test_node_merger.py` 작성
    - 정확한 이름 매칭 예시 (1개 Node + 1개 AddressRegion 동일 이름)
    - 대소문자 무시 매칭 확인 (`"SYSREG"` vs `"sysreg"`)
    - 전부 unmatched 케이스
    - _Requirements: 6.1, 6.3, 6.4, 6.5_
  - [ ]* 10.5 Property-based test: ExcelParser 직렬화 라운드트립 (Property 11)
    - **Property 11: ExcelParser serialization round-trip**
    - `@given(st.builds(AddressRegion, ...))` — 임의 AddressRegion 생성
    - `dataclasses.asdict(ar)` → `AddressRegion(**d)` 재구성 → 원본과 동일함 검증
    - **Validates: Requirements 9.3**
  - [ ]* 10.6 Property-based test: ExcelParser 멱등성 (Property 12)
    - **Property 12: ExcelParser idempotence**
    - `ExcelParser(sample_xlsx).parse()` 두 번 호출 → `address_regions`, `issues` 동일함 검증
    - **Validates: Requirements 9.4**
  - [ ]* 10.7 Property-based test: FileNotFoundError 범용성 (Property 3)
    - **Property 3: FileNotFoundError for non-existent paths**
    - `@given(st.text(min_size=1))` — 임의 문자열 경로 생성 (실제 파일 경로와 충돌하지 않도록 prefix 처리)
    - `DrawioParser(path)` 및 `ExcelParser(path)` 모두 `FileNotFoundError` raise 검증
    - **Validates: Requirements 2.5, 5.1**

- [x] 11. Checkpoint — 전체 테스트 통과 확인
  - `pytest tests/ -v` 실행 — 모든 단위 테스트 + property-based 테스트 통과
  - `pip install -e .` 재확인 후 `import spec_parser; print(spec_parser.__all__)` 동작 확인
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. 배포 repo 이전 준비
  - [x] 12.1 `README.md` 작성 (프로젝트 루트)
    - 설치 방법: `pip install spec-parser-library` (배포 repo 기준) / `pip install -e .` (개발 환경)
    - 배포 repo 이전 시 복사 대상 명시: `src/`, `pyproject.toml`, `tests/`
    - 제외 대상 명시: `parser/`, `graphdb/`, `mcp_server/`, `sample/`, 진단 스크립트들
    - 기본 사용 예시 코드 포함 (DrawioParser, ExcelParser, NodeMerger)
    - _Requirements: 7.1–7.6_
  - [x] 12.2 `.gitignore` 및 패키지 구조 최종 점검
    - `__pycache__/`, `*.egg-info/`, `dist/`, `.pytest_cache/` 제외 항목 확인
    - `src/spec_parser/_internal/drawio_parser_impl.py`가 패키지에 포함되는지 `pip install -e .` 후 확인
    - _Requirements: 7.5_

- [x] 13. 최종 end-to-end 검증
  - `pip install -e .` 후 아래 시퀀스 확인 (자동화 스크립트 `tests/test_e2e.py` 작성):
    1. `DrawioParser("sample/...drawio").parse()` → `ParseResult.nodes` 비어있지 않음
    2. `ExcelParser("sample/.../INFO_MemoryMap_Atlas_ML3_DEV02.xlsx").parse()` → `address_regions` 비어있지 않음
    3. `NodeMerger().merge(drawio_result, excel_result)` → `MergedNode` 목록 반환, `address_region is not None` 인 항목 1개 이상
  - _Requirements: 7.5, 9.1–9.4_

---

## Notes

- `*` 표시 태스크(property-based test 및 단위 테스트 일부)는 선택 사항으로, MVP 구현 속도 우선 시 건너뛸 수 있음
- Task 2에서 복사한 `_internal/drawio_parser_impl.py`는 원본 `parser/drawio_parser.py`와 **동기화 책임**을 갖지 않음 — 패키지 독립성 우선
- 배포 repo 이전 후에는 `src/spec_parser/drawio_parser.py`의 import 경로가 이미 `_internal` 참조이므로 별도 수정 불필요
- `hypothesis` property-based test는 각 property당 `@settings(max_examples=100)` 적용
- ExcelParser는 `openpyxl.load_workbook(data_only=True)`로 열어야 MM-CPU/MM-SAFE의 `Size(B)` 컬럼이 계산된 정수값으로 반환됨

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5"] },
    { "id": 1, "tasks": ["3.6"] },
    { "id": 2, "tasks": ["4.1", "6.1", "6.2", "6.7", "7.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "6.4", "6.8", "7.2"] },
    { "id": 4, "tasks": ["4.4", "4.5", "6.3", "6.5", "6.6", "6.9", "6.10", "7.3", "7.4"] },
    { "id": 5, "tasks": ["8"] },
    { "id": 6, "tasks": ["10.1", "10.2", "10.3", "10.4"] },
    { "id": 7, "tasks": ["10.5", "10.6", "10.7"] },
    { "id": 8, "tasks": ["12.1", "12.2"] },
    { "id": 9, "tasks": ["13"] }
  ]
}
```

# Requirements Document

> **Created:** 2026-06-22
> **Updated:** 2026-06-22 (requirements analysis applied)
> **Purpose:** spec-parser-library — drawio·Excel 파서와 공통 인터페이스를 pip install 가능한 라이브러리로 패키징하기 위한 요구사항 정의
> **Spec / Project:** `.kiro/specs/spec-parser-library/`
> **Status:** Draft

---

## Introduction

SoC 아키텍처 문서(drawio 블록 다이어그램, MemoryMap xlsx)를 파싱해 정규화된 Python 객체로 반환하는 라이브러리를 개발한다.
라이브러리는 저장소(Neo4j, Neptune, Qdrant, DynamoDB)에 종속되지 않으며, 외부 repo에서 `pip install`로 사용할 수 있는 독립 패키지로 제공된다.

파서가 처리할 입력 파일은 두 종류다:
- **drawio XML**: 블록 다이어그램 (기존 `parser/drawio_parser.py` 기반)
- **MemoryMap Excel** (`INFO_MemoryMap_Atlas_ML3_DEV02.xlsx`): 3개 시트
  - `ATLAS_CA720_MM` — 53개 BLK × IP 매트릭스 (BLK명, 기준 주소, IP명 컬럼 그룹, 5컬럼 간격, 129행)
  - `MM-CPU` — CA720 CPU 전체 주소 맵 (Base/Limit 주소, Size, Description, 5행부터 데이터)
  - `MM-SAFE` — R82 SAFE 전체 주소 맵 (동일 컬럼 구조)

---

## Glossary

- **Parser**: 파일을 입력으로 받아 `ParseResult`를 반환하는 모듈. 저장소 로직을 포함하지 않는다.
- **ParseResult**: 파서가 반환하는 최상위 정규화 객체. `nodes`, `edges`, `address_regions`, `issues` 필드를 포함한다.
- **Node**: 블록 다이어그램 또는 메모리맵에서 추출한 단위 정보 객체. `id`, `name`, `node_type`, `source` 필드를 포함한다.
- **Edge**: 두 Node 사이의 방향성 있는 연결을 나타내는 객체.
- **AddressRegion**: IP명, 기준 주소, 한계 주소, 크기, 소속 BLK를 담는 주소 영역 객체.
- **MergedNode**: drawio Node와 AddressRegion을 병합한 결과 객체. 하나의 IP가 drawio 블록명과 Excel 주소 정보를 모두 갖는다.
- **BLK**: Excel `ATLAS_CA720_MM` 시트에서 컬럼 그룹을 구분하는 하드웨어 블록 이름 (예: `BLK_CPU0`).
- **IP**: BLK 내 개별 IP 이름 (예: `SYSREG_CPU0`). drawio 노드 라벨과 매칭의 단위가 된다.
- **DrawioParser**: 기존 `parser/drawio_parser.py`를 감싸는 파서 클래스.
- **ExcelParser**: MemoryMap xlsx 를 파싱하는 신규 파서 클래스 (`src/spec_parser/excel_parser.py`).
- **NodeMerger**: drawio `ParseResult`와 Excel `ParseResult`를 받아 `MergedNode` 목록을 반환하는 병합기 클래스.
- **Spec_Parser_Library**: 이 문서에서 개발하는 pip 패키지 전체를 지칭하는 시스템 이름.

---

## Requirements

### Requirement 1: 공통 인터페이스 정의

**User Story:** 개발자로서, drawio 파서와 Excel 파서가 동일한 Python 타입을 반환하기를 원한다. 그래야 다운스트림 적재 코드가 파서 종류에 무관하게 동작할 수 있다.

#### Acceptance Criteria

1. THE Spec_Parser_Library SHALL define a `ParseResult` dataclass in `src/spec_parser/interfaces/parse_result.py` containing `nodes: list[Node]`, `edges: list[Edge]`, `address_regions: list[AddressRegion]`, and `issues: list[ParseIssue]` fields.
2. THE Spec_Parser_Library SHALL define a `Node` dataclass with fields `id: str`, `name: str`, `node_type: str`, `source: str`, and `extra: dict`.
3. THE Spec_Parser_Library SHALL define an `Edge` dataclass with fields `id: str`, `source_id: str`, `target_id: str`, `edge_type: str`, and `label: str`.
4. THE Spec_Parser_Library SHALL define an `AddressRegion` dataclass with fields `ip_name: str`, `blk_name: str`, `base_address: str`, `limit_address: str`, `size_bytes: int`, `description: str`, and `address_map: str`.
5. THE Spec_Parser_Library SHALL define a `ParseIssue` dataclass with fields `issue_type: str`, `source_ref: str`, and `description: str`.
6. THE Spec_Parser_Library SHALL export all interface types from `src/spec_parser/interfaces/__init__.py` so that callers can import via `from spec_parser.interfaces import ParseResult, Node, Edge, AddressRegion, ParseIssue`.

---

### Requirement 2: DrawioParser 래핑

**User Story:** 개발자로서, 기존 `parser/drawio_parser.py` 로직을 그대로 활용하면서 `ParseResult`를 반환하는 표준화된 API를 사용하고 싶다.

#### Acceptance Criteria

1. WHEN a `.drawio` file path is provided, THE DrawioParser SHALL parse the file and return a `ParseResult` object.
2. THE DrawioParser SHALL convert each `DrawioNode` to a `Node` with `source="drawio"` and preserve `label`, `node_type`, `fill_color`, `x`, `y`, `width`, `height` values in the `extra` field.
3. THE DrawioParser SHALL convert each connected `DrawioEdge` to an `Edge`, preserving `edge_type` and `label`.
4. THE DrawioParser SHALL place all `QualityIssue` items into `ParseResult.issues` as `ParseIssue` objects.
5. IF a `.drawio` file does not exist at the given path, THEN THE DrawioParser SHALL raise a `FileNotFoundError` with the file path in the message before attempting any XML parsing.
6. IF a `.drawio` file exists and is malformed XML, THEN THE DrawioParser SHALL raise a `ParseError` with a description of the parse failure.

---

### Requirement 3: ExcelParser — ATLAS_CA720_MM 시트 파싱

**User Story:** 하드웨어 아키텍트로서, MemoryMap xlsx의 BLK×IP 매트릭스에서 각 BLK가 어떤 IP들을 어떤 주소에 갖는지를 Python 객체로 얻고 싶다.

#### Acceptance Criteria

1. WHEN a valid MemoryMap xlsx path is provided, THE ExcelParser SHALL parse the `ATLAS_CA720_MM` sheet and return IP 항목들을 `ParseResult.address_regions`에 포함한다.
2. THE ExcelParser SHALL detect BLK column groups by scanning row 1 for the literal string `"BLK"` and treat every column matching that header as the start of a new group with stride 5 (columns: BLK, Addr, IP, _, _).
3. THE ExcelParser SHALL use the BLK name from row 2 of the BLK column (first non-empty cell in that column) as the `blk_name` for all IP entries in that group.
4. THE ExcelParser SHALL set `address_map="ATLAS_CA720_MM"` on every `AddressRegion` extracted from this sheet.
5. THE ExcelParser SHALL skip rows where both the Addr column and the IP column are empty or contain only whitespace; IF the Addr column has a value but the IP column is empty, THE ExcelParser SHALL still create an `AddressRegion` for that row.
6. THE ExcelParser SHALL set `limit_address=""` and `size_bytes=0` for entries from this sheet (those fields are not present in the BLK×IP matrix).
7. WHEN an IP cell contains the value `"Reserved"` (case-insensitive) or is empty after stripping whitespace, THE ExcelParser SHALL skip that entire row without creating an `AddressRegion`, even if the Addr column contains a valid value.

---

### Requirement 4: ExcelParser — MM-CPU / MM-SAFE 시트 파싱

**User Story:** 하드웨어 아키텍트로서, CPU와 SAFE 도메인의 전체 주소 맵(Base/Limit/Size/Description)을 Python 객체로 얻고 싶다.

#### Acceptance Criteria

1. WHEN a valid MemoryMap xlsx path is provided, THE ExcelParser SHALL parse both `MM-CPU` and `MM-SAFE` sheets and append resulting `AddressRegion` objects to `ParseResult.address_regions`.
2. THE ExcelParser SHALL locate the data start row by finding the row where column 1 contains `"Base Address (HEX)"` and begin reading data from the following row.
3. THE ExcelParser SHALL map columns to fields as follows: col 1 → `base_address`, col 2 → `limit_address`, col 4 → `size_bytes` (integer), col 8 → `description`.
4. THE ExcelParser SHALL set `blk_name=""` and `ip_name=""` for rows from MM-CPU and MM-SAFE (those fields do not exist in these sheets).
5. THE ExcelParser SHALL set `address_map="MM-CPU"` for entries from the `MM-CPU` sheet and `address_map="MM-SAFE"` for entries from the `MM-SAFE` sheet.
6. WHEN a row's `description` field contains `"Reserved"` or the `base_address` cell is empty, THE ExcelParser SHALL skip that row without creating an `AddressRegion`.
7. IF the integer conversion of the size value in column 4 fails, THEN THE ExcelParser SHALL record a `ParseIssue` with `issue_type="INVALID_SIZE"` and set `size_bytes=0` for that row; non-numeric text and empty cells that are not parseable as integers SHALL also trigger this same behavior.

---

### Requirement 5: ExcelParser 오류 처리

**User Story:** 개발자로서, 잘못된 파일을 입력했을 때 명확한 오류 메시지를 받고 싶다.

#### Acceptance Criteria

1. THE ExcelParser SHALL check file existence before format validation; IF the xlsx file does not exist at the given path, THEN THE ExcelParser SHALL raise a `FileNotFoundError` with the file path in the message before any further processing.
2. IF the xlsx file exists but is not a valid xlsx format, THEN THE ExcelParser SHALL raise a `ParseError` with a description identifying the file.
3. IF the `ATLAS_CA720_MM` sheet is not present in the workbook, THEN THE ExcelParser SHALL record a `ParseIssue` with `issue_type="MISSING_SHEET"` and return a `ParseResult` with empty `address_regions`.
4. IF `MM-CPU` or `MM-SAFE` sheet is not present in the workbook, THEN THE ExcelParser SHALL record a `ParseIssue` with `issue_type="MISSING_SHEET"` for each absent sheet and continue parsing any remaining sheets that are present.

---

### Requirement 6: NodeMerger — drawio 블록과 Excel IP 병합

**User Story:** 아키텍처 분석가로서, drawio의 블록 노드에 Excel의 주소 정보가 결합된 단일 객체를 원한다. 예를 들어 drawio의 `SYSREG_CPU0` 노드에 `0x2082_0000` 주소가 붙은 `MergedNode`를 얻고 싶다.

#### Acceptance Criteria

1. WHEN a drawio `ParseResult` and an Excel `ParseResult` are provided, THE NodeMerger SHALL match each `AddressRegion.ip_name` against `Node.name` using case-insensitive exact string matching and produce a `MergedNode` for each match.
2. THE NodeMerger SHALL set `MergedNode.node_id` to the drawio `Node.id`, `MergedNode.name` to the `Node.name`, and attach the matched `AddressRegion` as `MergedNode.address_region`.
3. THE NodeMerger SHALL include unmatched drawio nodes in the result as `MergedNode` objects with `address_region=None`.
4. THE NodeMerger SHALL include unmatched `AddressRegion` entries in the result as `MergedNode` objects with `node_id=None`.
5. THE NodeMerger SHALL NOT perform fuzzy or inferred matching — only exact matches (case-insensitive) are permitted.
6. WHEN the same `ip_name` appears in multiple `AddressRegion` entries (different `address_map` values), THE NodeMerger SHALL create one `MergedNode` per (Node, AddressRegion) pair, not one per Node.

---

### Requirement 7: 패키징 — pip install 가능한 라이브러리

**User Story:** 다운스트림 적재 repo 개발자로서, `pip install spec-parser-library`를 실행해 파서와 인터페이스를 즉시 사용하고 싶다.

#### Acceptance Criteria

1. THE Spec_Parser_Library SHALL provide a `pyproject.toml` at the repository root that declares `[build-system]` using `hatchling` and defines the package name as `spec-parser-library` with `packages = ["src/spec_parser"]`.
2. THE Spec_Parser_Library SHALL require Python `>=3.10` in `pyproject.toml`.
3. THE Spec_Parser_Library SHALL declare `openpyxl>=3.1` and `lxml>=4.9` as `[project.dependencies]` in `pyproject.toml`.
4. THE Spec_Parser_Library SHALL expose the following public API from `src/spec_parser/__init__.py`: `DrawioParser`, `ExcelParser`, `NodeMerger`, `ParseResult`, `Node`, `Edge`, `AddressRegion`, `ParseIssue`, `MergedNode`.
5. WHEN installed via `pip install -e .`, THE Spec_Parser_Library SHALL be importable with `import spec_parser` without adding `src/` to `PYTHONPATH` manually. If pip install succeeds, importability SHALL work without any manual PYTHONPATH configuration.
6. THE Spec_Parser_Library SHALL NOT declare `neo4j`, `fastmcp`, or any storage-layer packages as mandatory dependencies in `pyproject.toml`.

---

### Requirement 8: 디렉토리 레이아웃 및 기존 코드 보존

**User Story:** 프로젝트 유지보수자로서, 기존 `parser/`, `graphdb/`, `mcp_server/` 모듈이 그대로 동작하면서 새 `src/` 레이아웃이 독립적으로 공존하기를 원한다.

#### Acceptance Criteria

1. THE Spec_Parser_Library SHALL place all new source files under `src/spec_parser/` using the layout: `src/spec_parser/__init__.py`, `src/spec_parser/interfaces/`, `src/spec_parser/drawio_parser.py`, `src/spec_parser/excel_parser.py`, `src/spec_parser/node_merger.py`.
2. THE Spec_Parser_Library SHALL NOT modify or delete any file under `parser/`, `graphdb/`, or `mcp_server/`.
3. THE Spec_Parser_Library SHALL internally import from `parser.drawio_parser` (the existing module) inside `src/spec_parser/drawio_parser.py` rather than duplicating parser logic.

---

### Requirement 9: round-trip 및 파싱 정확성

**User Story:** 개발자로서, 파서가 파일에 명시된 값을 정확히 반환하는지 자동으로 검증하고 싶다.

#### Acceptance Criteria

1. THE ExcelParser SHALL return the `base_address` value exactly as it appears in the cell (예: `"0x2082_0000"`), without normalizing underscores or case.
2. FOR ALL `AddressRegion` objects returned by the ExcelParser, the `blk_name` SHALL match one of the BLK names found in row 2 of `ATLAS_CA720_MM`, or be an empty string for MM-CPU/MM-SAFE entries.
3. WHEN the ExcelParser parses a file and the result is serialized to a dict and re-constructed into `AddressRegion` objects, each reconstructed object SHALL be equal to the original (round-trip property).
4. THE ExcelParser SHALL return the same `ParseResult` when called twice on the same file with no intervening file modification (idempotence).

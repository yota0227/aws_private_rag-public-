# RTL 임베딩 가이드 — 다운로드부터 업로드까지

**문서 ID:** BOS-AI-GUIDE-RTL-UPLOAD-001
**최종 수정:** 2026-04-20
**대상:** RTL 코드를 RAG 시스템에 등록하려는 엔지니어

---

## 개요

이 가이드는 온프레미스 서버에 있는 RTL 소스 코드를 BOS-AI RAG 시스템에 임베딩하는 전체 과정을 설명합니다.

핵심 원칙:
- **필요한 파일만 다운로드** — RTL 파일(`.v`, `.sv`, `.vh`, `.svh`)만 받으면 됩니다
- **디렉토리 네이밍 규칙 준수** — `{chip_type}_{date}` 형식으로 파이프라인을 구분합니다
- **업로드하면 자동 처리** — S3에 올리면 파싱 → 임베딩 → 인덱싱이 자동으로 진행됩니다

---

## Step 1: RTL 다운로드 (온프레미스 → 로컬 PC)

### 1.1 필요한 파일 확장자

| 확장자 | 설명 | 다운로드 |
|--------|------|----------|
| `.v` | Verilog 소스 | ✅ 필수 |
| `.sv` | SystemVerilog 소스 | ✅ 필수 |
| `.vh` | Verilog 헤더 | ✅ 필수 |
| `.svh` | SystemVerilog 헤더 | ✅ 필수 |

### 1.2 불필요한 파일 (다운로드 제외)

| 확장자 | 설명 | 제외 이유 |
|--------|------|-----------|
| `.tcl` | Tcl 스크립트 | RTL Parser가 파싱 불가, Lambda 비용만 발생 |
| `.sdc` | 타이밍 제약 | 동일 |
| `.xdc` | Xilinx 제약 | 동일 |
| `.json`, `.txt`, `.csv` | 설정/로그 | 동일 |
| `.py`, `.sh` | 스크립트 | 동일 |
| `.png`, `.jpg`, `.pdf` | 이미지/문서 | 동일 |
| `.f` | 파일 리스트 | 동일 |
| `.log` | 시뮬레이션 로그 | 동일 |

> **왜 중요한가?** S3에 업로드된 모든 파일은 Lambda를 트리거합니다. RTL이 아닌 파일은 파싱 실패 후 에러 테이블에 기록되고, Lambda 실행 비용만 발생합니다.

### 1.3 WinSCP로 다운로드 (PowerShell)

```powershell
& "C:\Program Files (x86)\WinSCP\WinSCP.com" /command `
  "open sftp://{USER}:{PASSWORD}@{RTL_SERVER_IP}/" `
  "get -filemask=""*.v;*.sv;*.vh;*.svh"" {RTL_SOURCE_DIR}/{날짜}/ C:\tt_sample\{날짜}\" `
  "exit"
```

> `-filemask` 옵션이 RTL 확장자만 필터링합니다. 하위 디렉토리 구조는 그대로 유지됩니다.
> `{RTL_SERVER_IP}`, `{USER}`, `{PASSWORD}`, `{RTL_SOURCE_DIR}`은 인프라 관리자에게 문의하세요.

### 1.4 다운로드 결과 확인

```powershell
# 파일 수 확인
(Get-ChildItem -Path "C:\tt_sample\{날짜}" -Recurse -Include *.v,*.sv,*.vh,*.svh).Count

# 총 크기 확인 (MB)
(Get-ChildItem -Path "C:\tt_sample\{날짜}" -Recurse -Include *.v,*.sv,*.vh,*.svh | Measure-Object -Property Length -Sum).Sum / 1MB
```

---

## Step 2: S3 업로드 (로컬 PC → AWS S3)

### 2.1 디렉토리 네이밍 규칙

S3 업로드 경로는 반드시 다음 형식을 따라야 합니다:

```
s3://{RTL_S3_BUCKET}/rtl-sources/{chip_type}_{date}/
```

| 필드 | 설명 | 예시 |
|------|------|------|
| `{RTL_S3_BUCKET}` | RTL 전용 S3 버킷 이름 | 인프라 관리자에게 문의 |
| `{chip_type}` | RTL 칩 종류 식별자 | `tt` (Trinity), `n2` (N2 칩) |
| `{date}` | RTL 스냅샷 날짜 (YYYYMMDD) | `20260221`, `20260420` |

> **왜 중요한가?** 디렉토리 이름에서 `pipeline_id`가 자동 추출됩니다 (예: `tt_20260221`). 이 ID로 모든 분석 결과가 격리되어, 서로 다른 칩/스냅샷의 데이터가 섞이지 않습니다.

### 2.2 업로드 전 확인 (dryrun)

```powershell
aws s3 sync "C:\tt_sample\{날짜}" `
  s3://{RTL_S3_BUCKET}/rtl-sources/{chip_type}_{date}/ `
  --region ap-northeast-2 `
  --exclude "*" `
  --include "*.v" --include "*.sv" --include "*.vh" --include "*.svh" `
  --dryrun
```

### 2.3 실제 업로드

```powershell
aws s3 sync "C:\tt_sample\{날짜}" `
  s3://{RTL_S3_BUCKET}/rtl-sources/{chip_type}_{date}/ `
  --region ap-northeast-2 `
  --exclude "*" `
  --include "*.v" --include "*.sv" --include "*.vh" --include "*.svh"
```

### 2.4 업로드 후 자동 처리

```
S3 업로드 완료
    ↓
S3 Event → RTL Parser Lambda 트리거 (파일당 1회)
    ↓
모듈 파싱 → module_name, ports, parameters, instances 추출
    ↓
Pipeline_ID 자동 추출 (디렉토리 이름에서)
    ↓
Titan Embeddings 벡터 생성 → OpenSearch 인덱싱 완료
```

> 파일 수에 따라 5~30분 소요됩니다.

---

## Step 3: 분석 파이프라인 실행 (수동)

### 3.1 Claim 생성 (토픽별)

```powershell
$topics = @("NoC","EDC","FPU","Overlay","TDMA","Dispatch","SFPU","Clock_Reset","SMN","NIU","DFX")
foreach ($t in $topics) {
    $p = '{"stage":"claim_generation","pipeline_id":"{chip_type}_{date}","topic":"' + $t + '"}'
    $b = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($p))
    aws lambda invoke --function-name {RTL_PARSER_LAMBDA} --region ap-northeast-2 --invocation-type Event --payload $b "resp_$t.json"
}
```

### 3.2 HDD 생성 (토픽별)

```powershell
foreach ($t in $topics) {
    $p = '{"stage":"hdd_generation","pipeline_id":"{chip_type}_{date}","topic":"' + $t + '"}'
    $b = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($p))
    aws lambda invoke --function-name {RTL_PARSER_LAMBDA} --region ap-northeast-2 --invocation-type Event --payload $b "resp_hdd_$t.json"
}
```

---

## Step 4: 검증

Obot에서:
```
search_rtl 도구로 query를 "router"로 검색해줘
search_rtl 도구로 query를 "NoC"로, analysis_type을 "claim"으로 검색해줘
```

---

## 플레이스홀더 참조

| 플레이스홀더 | 설명 | 확인 방법 |
|-------------|------|-----------|
| `{RTL_SERVER_IP}` | RTL 소스가 있는 온프레미스 서버 IP | 인프라 관리자에게 문의 |
| `{USER}` | SFTP 접속 계정 | 인프라 관리자에게 문의 |
| `{PASSWORD}` | SFTP 접속 비밀번호 | 인프라 관리자에게 문의 |
| `{RTL_SOURCE_DIR}` | 온프레미스 서버의 RTL 소스 디렉토리 | 인프라 관리자에게 문의 |
| `{RTL_S3_BUCKET}` | RTL 전용 S3 버킷 이름 | AWS 콘솔 또는 Terraform 출력 확인 |
| `{RTL_PARSER_LAMBDA}` | RTL Parser Lambda 함수 이름 | AWS 콘솔 또는 Terraform 출력 확인 |
| `{chip_type}` | 칩 종류 식별자 | 프로젝트별 결정 (예: `tt`, `n2`) |
| `{date}` | RTL 스냅샷 날짜 | YYYYMMDD 형식 |

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 업로드 후 검색 안 됨 | Lambda 파싱 진행 중 | 5~30분 대기 |
| pipeline_id가 unknown | 디렉토리 이름 형식 오류 | `{chip}_{date}` 확인 |
| 파싱 에러 대량 발생 | RTL 아닌 파일 업로드 | `--exclude` 필터 확인 |
| Claim 0건 | Bedrock IAM 권한 없음 | IAM Role 확인 |
| 300초 타임아웃 | 파일 수 과다 | 토픽별 분할 실행 |

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
  "open sftp://root:PASSWORD@192.128.20.210/" `
  "get -filemask=""*.v;*.sv;*.vh;*.svh"" /secure_data_from_tt/{날짜}/ C:\tt_sample\{날짜}\" `
  "exit"
```

**예시:**
```powershell
& "C:\Program Files (x86)\WinSCP\WinSCP.com" /command `
  "open sftp://root:bos-semi#1@192.128.20.210/" `
  "get -filemask=""*.v;*.sv;*.vh;*.svh"" /secure_data_from_tt/20260221/ C:\tt_sample\20260221\" `
  "exit"
```

### 1.4 다운로드 결과 확인

```powershell
(Get-ChildItem -Path "C:\tt_sample\20260221" -Recurse -Include *.v,*.sv,*.vh,*.svh).Count
(Get-ChildItem -Path "C:\tt_sample\20260221" -Recurse -Include *.v,*.sv,*.vh,*.svh | Measure-Object -Property Length -Sum).Sum / 1MB
```

---

## Step 2: S3 업로드 (로컬 PC → AWS S3)

### 2.1 디렉토리 네이밍 규칙

```
s3://bos-ai-rtl-src-533335672315/rtl-sources/{chip_type}_{date}/
```

| 필드 | 설명 | 예시 |
|------|------|------|
| `{chip_type}` | RTL 칩 종류 | `tt` (Trinity), `n2` (N2 칩) |
| `{date}` | 스냅샷 날짜 (YYYYMMDD) | `20260221`, `20260420` |

### 2.2 업로드 전 확인 (dryrun)

```powershell
aws s3 sync "C:\tt_sample\20260221" s3://bos-ai-rtl-src-533335672315/rtl-sources/tt_20260221/ --region ap-northeast-2 --exclude "*" --include "*.v" --include "*.sv" --include "*.vh" --include "*.svh" --dryrun
```

### 2.3 실제 업로드

```powershell
aws s3 sync "C:\tt_sample\20260221" s3://bos-ai-rtl-src-533335672315/rtl-sources/tt_20260221/ --region ap-northeast-2 --exclude "*" --include "*.v" --include "*.sv" --include "*.vh" --include "*.svh"
```

### 2.4 업로드 후 자동 처리

업로드 완료 → S3 Event → Lambda 트리거 → 파싱 → 임베딩 → OpenSearch 인덱싱 (자동)

---

## Step 3: 분석 파이프라인 실행 (수동)

### 3.1 Claim 생성 (토픽별)

```powershell
$topics = @("NoC","EDC","FPU","Overlay","TDMA","Dispatch","SFPU","Clock_Reset","SMN","NIU","DFX")
foreach ($t in $topics) {
    $p = '{"stage":"claim_generation","pipeline_id":"{pipeline_id}","topic":"' + $t + '"}'
    $b = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($p))
    aws lambda invoke --function-name lambda-rtl-parser-seoul-dev --region ap-northeast-2 --invocation-type Event --payload $b "resp_$t.json"
}
```

### 3.2 HDD 생성 (토픽별)

```powershell
foreach ($t in $topics) {
    $p = '{"stage":"hdd_generation","pipeline_id":"{pipeline_id}","topic":"' + $t + '"}'
    $b = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($p))
    aws lambda invoke --function-name lambda-rtl-parser-seoul-dev --region ap-northeast-2 --invocation-type Event --payload $b "resp_hdd_$t.json"
}
```

---

## Step 4: 검증

Obot에서:
```
search_rtl 도구로 query를 "router"로 검색해줘
```

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 업로드 후 검색 안 됨 | Lambda 파싱 진행 중 | 5~30분 대기 |
| pipeline_id가 unknown | 디렉토리 이름 형식 오류 | `{chip}_{date}` 확인 |
| 파싱 에러 대량 발생 | RTL 아닌 파일 업로드 | `--exclude` 필터 확인 |
| Claim 0건 | Bedrock IAM 권한 없음 | IAM Role 확인 |

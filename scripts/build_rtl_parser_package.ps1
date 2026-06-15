<#
.SYNOPSIS
    RTL Parser Lambda 배포 패키지(rtl-parser-deployment-package.zip)에 소스 .py를 동기화한다.

.DESCRIPTION
    rtl_parser_src/ 의 모든 소스 .py (test_* / conftest 제외)를 기존 zip의 루트 엔트리로
    업데이트/추가한다. vendored 의존성(certifi/charset_normalizer/idna/requests/
    requests_aws4auth/urllib3 등)은 Linux/py3.12 호환 바이너리이므로 Windows에서
    재설치하지 않고 그대로 보존한다 (재-vendor 시 Windows 바이너리 오염 방지).

    목적: 소스와 배포 산출물(zip)의 drift를 방지한다 (engineering-discipline).
    repo-maintenance 요구사항 2의 rtl-parser 빌드 스크립트 역할.

.NOTES
    의존성 자체를 갱신해야 하는 경우(requirements.txt 변경)는 Linux 환경 또는
    Docker(rtl_parser_src/Dockerfile)에서 별도로 재빌드해야 한다.
#>
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$srcDir = Join-Path $repoRoot "environments\app-layer\bedrock-rag\rtl_parser_src"
$zipPath = Join-Path $repoRoot "environments\app-layer\bedrock-rag\rtl-parser-deployment-package.zip"

if (-not (Test-Path $zipPath)) {
    throw "배포 zip이 없습니다: $zipPath (의존성 포함 초기 zip은 Docker/Linux 빌드로 생성)"
}
if (-not (Test-Path $srcDir)) {
    throw "소스 디렉토리가 없습니다: $srcDir"
}

# 동기화 대상: test_* 와 conftest 를 제외한 루트 .py 소스
$sourceFiles = Get-ChildItem -Path $srcDir -Filter "*.py" -File |
    Where-Object { $_.Name -notlike "test_*" -and $_.Name -ne "conftest.py" }

if (-not $sourceFiles) {
    throw "동기화할 소스 .py 가 없습니다: $srcDir"
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Update)
$updated = 0
$added = 0
try {
    foreach ($f in $sourceFiles) {
        $entryName = $f.Name  # 루트 엔트리 (handler = handler.handler)
        $existing = $zip.GetEntry($entryName)
        if ($null -ne $existing) {
            $existing.Delete()
            $updated++
        } else {
            $added++
        }
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip, $f.FullName, $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal)
    }
} finally {
    $zip.Dispose()
}

# source_code_hash (terraform filebase64sha256 와 동일) 출력
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $hash = [Convert]::ToBase64String($sha.ComputeHash([System.IO.File]::ReadAllBytes($zipPath)))
} finally {
    $sha.Dispose()
}

Write-Output "RTL parser package synced: $($sourceFiles.Count) source files (updated=$updated, added=$added)"
Write-Output "zip: $zipPath"
Write-Output "source_code_hash (base64 sha256): $hash"

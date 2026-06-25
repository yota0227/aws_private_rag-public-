# ============================================================================
# Atlas Project IP Documents S3 Upload Script
#
# S3 경로 규칙:
#   s3://<BUCKET>/Atlas/<IP명>/ver.<N>/<filename>
#
# IP명 규칙:
#   - 파일이 IP 폴더 직하: IP 폴더명 그대로
#   - 파일이 하위 디렉토리 안에: 상위_하위 형태로 연결 (공백은 _ 로 치환)
#
# 버전 규칙:
#   파일명 BaseName 이 __<숫자> 로 끝나면 ver.<숫자>
#   그 외 (숫자 없음)                      ver.1
#
# 스킵 대상:
#   .xlsx, .xls, .csv (엑셀/스프레드시트는 텍스트 파싱 불가, 별도 처리 필요)
#
# Usage:
#   cd scripts
#   .\upload_atlas_docs.ps1            # 실제 업로드
#   .\upload_atlas_docs.ps1 -DryRun    # 경로 미리보기만
# ============================================================================

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$BUCKET   = "bos-ai-toolguide-docs-seoul-533335672315"
$REGION   = "ap-northeast-2"
$SRC_ROOT = "C:\Users\Seung-IlWoo\OneDrive - 보스반도체\Atlas Project - 10_IP Documents"
$PROJECT  = "Atlas"

# 파싱 가능 확장자 (엑셀/CSV 제외)
$ALLOWED_EXT = @(".pdf", ".md")

Write-Host "=== Atlas IP Documents Upload ===" -ForegroundColor Cyan
Write-Host "Source : $SRC_ROOT"
Write-Host "Bucket : s3://$BUCKET/$PROJECT/"
if ($DryRun) { Write-Host "[DRY RUN]" -ForegroundColor Yellow }
Write-Host ""

$uploaded = 0
$skipped  = 0
$errors   = 0

# IP 폴더 순회 (최상위 디렉토리만)
$ipDirs = Get-ChildItem -Path $SRC_ROOT -Directory
Write-Host "IP 폴더 수: $($ipDirs.Count)"
Write-Host ""

foreach ($ipDir in $ipDirs) {
    $ipBase = $ipDir.Name  # 예: ARM_CORTEX-A720AE

    # 해당 IP 폴더 하위의 모든 파일 재귀 탐색
    $files = Get-ChildItem -Path $ipDir.FullName -File -Recurse |
             Where-Object { $_.Extension -in $ALLOWED_EXT }

    $xlsxCount = (Get-ChildItem -Path $ipDir.FullName -File -Recurse |
                  Where-Object { $_.Extension -in @(".xlsx",".xls",".csv") }).Count

    if ($files.Count -eq 0 -and $xlsxCount -eq 0) {
        Write-Host "[$ipBase] 파일 없음, 스킵" -ForegroundColor DarkGray
        continue
    }

    Write-Host "[$ipBase] PDF/MD: $($files.Count)개  XLSX 스킵: $xlsxCount개" -ForegroundColor Yellow

    foreach ($file in $files) {
        # IP명 결정: 파일의 상위 디렉토리와 IP 루트 간의 상대 경로
        $fileDir   = $file.DirectoryName
        $relDir    = $fileDir.Replace($ipDir.FullName, "").TrimStart("\")

        if ($relDir -eq "") {
            # 파일이 IP 폴더 직하에 있음
            $ipName = $ipBase
        } else {
            # 하위 디렉토리 안에 있음: 상위_하위 형태로 연결, 공백->_
            $subPath = $relDir.Replace("\", "_").Replace(" ", "_")
            $ipName  = "${ipBase}_${subPath}"
        }

        # 버전 추출: BaseName 끝에 __숫자 패턴
        if ($file.BaseName -match '__(\d+)$') {
            $ver = "ver.$($Matches[1])"
        } else {
            $ver = "ver.1"
        }

        $s3Key = "$PROJECT/$ipName/$ver/$($file.Name)"
        $s3Uri = "s3://$BUCKET/$s3Key"

        if ($DryRun) {
            Write-Host "  [DRY] $($file.Name)" -ForegroundColor DarkCyan
            Write-Host "     IP: $ipName  VER: $ver" -ForegroundColor Gray
            $uploaded++
            continue
        }

        try {
            $result = aws s3 cp $file.FullName $s3Uri --region $REGION --no-progress 2>&1
            if ($LASTEXITCODE -ne 0) { throw $result }
            Write-Host "  OK  [$ipName/$ver] $($file.Name)" -ForegroundColor Green
            $uploaded++
        } catch {
            Write-Host "  ERR $($file.Name): $_" -ForegroundColor Red
            $errors++
        }
    }

    $skipped += $xlsxCount
}

Write-Host ""
Write-Host "=== 완료 ===" -ForegroundColor Cyan
Write-Host "업로드: $uploaded  엑셀 스킵: $skipped  에러: $errors"

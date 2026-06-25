# ============================================================================
# Tool Guide 인덱싱 진척도 체크
# Usage:
#   .\check_progress.ps1          # 현재 상태 한 번 출력
#   .\check_progress.ps1 -Watch   # 30초마다 자동 갱신 (Ctrl+C 종료)
# ============================================================================

param([switch]$Watch)

$REGION   = "ap-northeast-2"
$DLQ_URL  = "https://sqs.ap-northeast-2.amazonaws.com/533335672315/sqs-tool-guide-parser-dlq-dev"
$TOTAL    = 1061
$QDRANT_CMD = 'curl -s -H api-key:dc778157b5b6c3e3d6683e47dd0419cc69492c128e8a147ead6a155dd0b2c0ea http://localhost:6333/collections/tool-guide-knowledge-base'

function Get-Progress {
    Write-Host "`n=== 진척도 $(Get-Date -Format 'HH:mm:ss') ===" -ForegroundColor Cyan

    # DLQ 잔여
    $attrs = aws sqs get-queue-attributes --region $REGION --queue-url $DLQ_URL `
        --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible `
        --output json 2>$null | ConvertFrom-Json
    $dlqWaiting  = [int]$attrs.Attributes.ApproximateNumberOfMessages
    $dlqFlying   = [int]$attrs.Attributes.ApproximateNumberOfMessagesNotVisible
    $done = $TOTAL - $dlqWaiting
    $pct  = [math]::Round($done / $TOTAL * 100, 1)

    Write-Host ("DLQ 대기: {0,4}  처리중: {1,3}  완료: {2,4}/{3} ({4}%)" -f $dlqWaiting, $dlqFlying, $done, $TOTAL, $pct) -ForegroundColor Yellow

    # Qdrant
    try {
        $ssmJson = '{"InstanceIds":["i-0d520340617eb5484"],"DocumentName":"AWS-RunShellScript","Parameters":{"commands":["' + $QDRANT_CMD + '"]}}'
        $cid = aws ssm send-command --region us-east-1 --cli-input-json $ssmJson `
            --query "Command.CommandId" --output text 2>$null | Select-String "^[a-f0-9-]{36}$"
        Start-Sleep 7
        $raw = aws ssm get-command-invocation --region us-east-1 --command-id "$cid" `
            --instance-id i-0d520340617eb5484 --query "StandardOutputContent" --output text 2>$null
        $q = $raw | ConvertFrom-Json
        Write-Host ("Qdrant 포인트: {0}  (인덱싱됨: {1})" -f $q.result.points_count, $q.result.indexed_vectors_count) -ForegroundColor Magenta
    } catch {
        Write-Host "Qdrant 조회 실패" -ForegroundColor DarkGray
    }

    # reprocess 로그 마지막 줄
    $log = "c:\Users\Seung-IlWoo\aws_private_rag\reprocess_dlq.log"
    if (Test-Path $log) {
        $last = Get-Content $log -Tail 2
        Write-Host "재처리 로그:" -ForegroundColor DarkCyan
        $last | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkCyan }
    }
}

if ($Watch) {
    Write-Host "30초 간격 모니터링 (Ctrl+C 종료)" -ForegroundColor Cyan
    while ($true) { Get-Progress; Start-Sleep 30 }
} else {
    Get-Progress
}

# reprocess_dlq.ps1 - Invoke Lambda for all S3 tool guide files
# Usage: .\reprocess_dlq.ps1 [-DryRun] [-MaxFiles 100]

param([switch]$DryRun, [int]$MaxFiles = 99999)

$REGION      = "ap-northeast-2"
$BUCKET      = "bos-ai-toolguide-docs-seoul-533335672315"
$LAMBDA_NAME = "lambda-tool-guide-parser-seoul-dev"
$LOG_FILE    = "c:\Users\Seung-IlWoo\aws_private_rag\reprocess_dlq.log"

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Log($msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss') $msg"
    Write-Host $line
    [System.IO.File]::AppendAllText($LOG_FILE, "$line`n", [System.Text.Encoding]::UTF8)
}

Log "=== Reprocess started ==="
Log "Bucket: $BUCKET"
Log "Listing S3 files..."

$keys = aws s3 ls "s3://$BUCKET/" --recursive --region $REGION 2>$null |
    Where-Object { $_ -match "\.(pdf|md)$" -and $_ -notmatch "published/" } |
    ForEach-Object { ($_ -split "\s+", 4)[3] }

$total = $keys.Count
Log "Target files: $total"

if ($DryRun) { Log "DRY RUN - exit"; exit 0 }

$done = 0; $ok = 0; $err = 0

foreach ($key in $keys) {
    if ($done -ge $MaxFiles) { break }
    $done++

    try {
        $payload = ConvertTo-Json -Compress -Depth 10 @{
            Records = @(@{
                eventVersion = "2.1"; eventSource = "aws:s3"
                awsRegion = $REGION; eventName = "ObjectCreated:Put"
                s3 = @{ bucket = @{ name = $BUCKET }; object = @{ key = $key } }
            })
        }

        $inFile  = [IO.Path]::GetTempFileName() + ".json"
        $outFile = [IO.Path]::GetTempFileName()
        [IO.File]::WriteAllText($inFile, $payload, [Text.Encoding]::UTF8)

        aws lambda invoke --region $REGION --function-name $LAMBDA_NAME `
            --invocation-type Event --payload fileb://$inFile `
            --cli-binary-format raw-in-base64-out $outFile 2>$null | Out-Null

        Remove-Item $inFile, $outFile -ErrorAction SilentlyContinue

        if ($LASTEXITCODE -eq 0) { $ok++ } else { $err++; Log "FAIL [$key]" }
    } catch {
        $err++; Log "ERR [$key]: $_"
    }

    if ($done % 100 -eq 0) { Log "Progress: $done/$total ok=$ok err=$err" }
    if ($done % 5 -eq 0) { Start-Sleep -Milliseconds 300 }
}

Log "=== Done: $done/$total ok=$ok err=$err ==="

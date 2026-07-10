# run_pipeline.ps1 — 시장분석 보고서 자동생성 파이프라인
#
# 사용법:
#   .\run_pipeline.ps1 `
#       -InputFile  "C:\reports\sample.pdf" `
#       -TechField  "데이터센터 냉각" `
#       -ProjectName "2026년 데이터센터 냉각 시장 동향 조사" `
#       -OutputName "시장분석_데이터센터냉각"
#
# 선택 옵션:
#   -Cleanup     파이프라인 완료 후 workspace 삭제
#   -SkipStep N  특정 단계를 건너뜀 (예: -SkipStep 2 은 extract_images 생략)

param(
    [Parameter(Mandatory=$true)]  [string] $InputFile,
    [Parameter(Mandatory=$true)]  [string] $TechField,
    [Parameter(Mandatory=$true)]  [string] $ProjectName,
    [Parameter(Mandatory=$true)]  [string] $OutputName,
    [switch] $Cleanup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$SCRIPTS = "D:\2ndHDD\260415 Claude Code 강의\260520 기획지원서비스 AX\기획지원 자동화\1. 시장분석\skill\scripts"
$START   = Get-Date

function Step($n, $label, $cmd) {
    Write-Host ""
    Write-Host ("=" * 55)
    Write-Host "  STEP $n — $label"
    Write-Host ("=" * 55)
    $t = Get-Date
    Invoke-Expression $cmd
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        Write-Host "❌ STEP $n 실패 (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    $secs = [math]::Round(((Get-Date) - $t).TotalSeconds)
    Write-Host "  완료 (${secs}초)" -ForegroundColor Green
}

if (-not $env:ANTHROPIC_API_KEY) {
    Write-Host "⚠  ANTHROPIC_API_KEY 미설정 — STEP 3 API 호출이 실패할 수 있습니다." -ForegroundColor Yellow
}

Step 1 "입력 분석 및 환경 초기화" `
    "python `"$SCRIPTS\extract_input.py`" --input `"$InputFile`" --tech-field `"$TechField`" --project-name `"$ProjectName`" --output-name `"$OutputName`""

Step 2a "텍스트 추출" `
    "python `"$SCRIPTS\extract_input.py`" --input `"$InputFile`" --tech-field `"$TechField`" --project-name `"$ProjectName`" --output-name `"$OutputName`" --step text-only 2>$null; exit 0"

Step 2b "이미지 추출" `
    "python `"$SCRIPTS\extract_images.py`""

Step 3 "AI 분석 및 구조화" `
    "python `"$SCRIPTS\analyze_sections.py`""

Step 4 "차트·인포그래픽 생성" `
    "python `"$SCRIPTS\generate_charts.py`""

Step 5 "HWPX+DOCX 보고서 조립 및 검증" `
    "python `"$SCRIPTS\generate_reports.py`""

$cleanupFlag = if ($Cleanup) { "--cleanup" } else { "" }
Step 7 "최종 출력 및 리포트" `
    "python `"$SCRIPTS\finalize_report.py`" $cleanupFlag"

$total = [math]::Round(((Get-Date) - $START).TotalSeconds)
Write-Host ""
Write-Host "전체 파이프라인 완료 — 총 ${total}초" -ForegroundColor Cyan

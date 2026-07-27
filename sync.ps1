# 워크스페이스 동기화 — 다른 PC 오갈 때 한 방에
#
#   .\sync.ps1          → 받기 + 올리기 (기본, PC 켤 때/끌 때 둘 다 이거면 됨)
#   .\sync.ps1 pull     → 받기만 (다른 PC에서 작업 시작할 때)
#   .\sync.ps1 push     → 올리기만 (커밋 + 푸시)
#   .\sync.ps1 commit   → 로컬 커밋만 (푸시 안 함)
#
# 충돌 나면 멈추고 알려줌. 그 외엔 아무것도 안 물어봄.

param([string]$mode = "both")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# git 사용자 정보 없으면 자동 설정 (새 PC 대응)
if (-not (git config user.email)) {
    git config user.name "cy728728-a11y"
    git config user.email "cy728728@gmail.com"
    Write-Host "[설정] git 사용자 정보 등록됨" -ForegroundColor DarkGray
}

# ---------- 커밋만 ----------
if ($mode -eq "commit") {
    if (git status --porcelain) {
        git add -A
        git commit -q -m ("sync: " + (Get-Date -Format "yyyy-MM-dd HH:mm") + " ($env:COMPUTERNAME)")
        Write-Host "[커밋] 완료" -ForegroundColor Green
    } else {
        Write-Host "[커밋] 변경 없음" -ForegroundColor DarkGray
    }
    exit 0
}

# ---------- 받기 ----------
if ($mode -eq "both" -or $mode -eq "pull") {
    # 로컬 변경분이 있으면 pull 전에 먼저 커밋 (rebase 충돌 방지)
    if (git status --porcelain) {
        git add -A
        git commit -q -m ("sync: " + (Get-Date -Format "yyyy-MM-dd HH:mm") + " ($env:COMPUTERNAME)")
    }

    git pull --rebase origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "[충돌] 자동 병합 실패. 파일을 직접 고친 뒤:" -ForegroundColor Red
        Write-Host "  git add .  →  git rebase --continue  →  .\sync.ps1 push" -ForegroundColor Yellow
        Write-Host "되돌리려면: git rebase --abort" -ForegroundColor DarkGray
        exit 1
    }
    Write-Host "[받기] 완료" -ForegroundColor Green
}

# ---------- 올리기 ----------
if ($mode -eq "both" -or $mode -eq "push") {
    if (git status --porcelain) {
        git add -A
        git commit -q -m ("sync: " + (Get-Date -Format "yyyy-MM-dd HH:mm") + " ($env:COMPUTERNAME)")
    }

    # 올릴 커밋이 없으면 조용히 종료
    $ahead = git rev-list --count origin/main..HEAD
    if ($ahead -eq "0") {
        Write-Host "[올리기] 변경 없음" -ForegroundColor DarkGray
        exit 0
    }

    git push origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[올리기] 실패 — 먼저 .\sync.ps1 pull 하세요" -ForegroundColor Red
        exit 1
    }
    Write-Host "[올리기] 완료 ($ahead 커밋)" -ForegroundColor Green
}

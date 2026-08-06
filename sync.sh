#!/usr/bin/env bash
# 워크스페이스 동기화 (macOS) — sync.ps1 의 맥 버전
#
#   ./sync.sh          → 받기 + 올리기 (기본, 맥 켤 때/끌 때 둘 다 이거면 됨)
#   ./sync.sh pull     → 받기만 (다른 기기에서 작업 시작할 때)
#   ./sync.sh push     → 올리기만 (커밋 + 푸시)
#   ./sync.sh commit   → 로컬 커밋만 (푸시 안 함)
#
# 충돌 나면 멈추고 알려줌. 그 외엔 아무것도 안 물어봄.
#
# 기기 이름은 커밋 메시지에 붙습니다. 바꾸려면:
#   SYNC_DEVICE="아이맥" ./sync.sh

mode="${1:-both}"

# 스크립트가 있는 폴더로 이동 (어디서 실행하든 동작)
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 1

DEVICE="${SYNC_DEVICE:-맥북}"

# 색상
GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; GRAY=$'\033[90m'; RESET=$'\033[0m'

# git 사용자 정보 없으면 자동 설정 (새 기기 대응)
if [ -z "$(git config user.email)" ]; then
    git config user.name "cy728728-a11y"
    git config user.email "cy728728@gmail.com"
    printf '%s[설정] git 사용자 정보 등록됨%s\n' "$GRAY" "$RESET"
fi

# 변경분이 있으면 커밋
commit_if_dirty() {
    if [ -n "$(git status --porcelain)" ]; then
        git add -A
        git commit -q -m "sync: $(date '+%Y-%m-%d %H:%M') ($DEVICE)"
        return 0
    fi
    return 1
}

# ---------- 커밋만 ----------
if [ "$mode" = "commit" ]; then
    if commit_if_dirty; then
        printf '%s[커밋] 완료%s\n' "$GREEN" "$RESET"
    else
        printf '%s[커밋] 변경 없음%s\n' "$GRAY" "$RESET"
    fi
    exit 0
fi

# ---------- 받기 ----------
if [ "$mode" = "both" ] || [ "$mode" = "pull" ]; then
    # 로컬 변경분이 있으면 pull 전에 먼저 커밋 (rebase 충돌 방지)
    commit_if_dirty

    if ! git pull --rebase origin main; then
        echo ""
        printf '%s[충돌] 자동 병합 실패. 파일을 직접 고친 뒤:%s\n' "$RED" "$RESET"
        printf '%s  git add .  →  git rebase --continue  →  ./sync.sh push%s\n' "$YELLOW" "$RESET"
        printf '%s되돌리려면: git rebase --abort%s\n' "$GRAY" "$RESET"
        exit 1
    fi
    printf '%s[받기] 완료%s\n' "$GREEN" "$RESET"
fi

# ---------- 올리기 ----------
if [ "$mode" = "both" ] || [ "$mode" = "push" ]; then
    commit_if_dirty

    # 올릴 커밋이 없으면 조용히 종료
    ahead=$(git rev-list --count origin/main..HEAD)
    if [ "$ahead" = "0" ]; then
        printf '%s[올리기] 변경 없음%s\n' "$GRAY" "$RESET"
        exit 0
    fi

    if ! git push origin main; then
        printf '%s[올리기] 실패 — 먼저 ./sync.sh pull 하세요%s\n' "$RED" "$RESET"
        exit 1
    fi
    printf '%s[올리기] 완료 (%s 커밋)%s\n' "$GREEN" "$ahead" "$RESET"
fi

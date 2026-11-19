# -*- coding: utf-8 -*-
"""
판매금지 품목 검수기준 — 드라이브 정본을 로컬 읽기전용 사본으로 동기화한다.

- 정본: 구글드라이브 50-소스자료/52-키워드-블랙리스트/판매금지-품목-검수기준.md (이룸님 관리)
- 사본: 00-system/판매금지-기준/판매금지-품목-검수기준.md  (읽기 전용, 직접 고치지 않는다)
- 드라이브 수정시각·체크섬이 바뀌었거나 사본이 손상/수정됐으면 다시 받는다.
- 실패해도(인증 만료·네트워크) 기존 사본은 그대로 두고 경고만 출력한다. 작업을 막지 않는다.

- 반영 대장: 스킬 기준에 반영을 마친 판을 .applied.md 로 보관한다.
  사본이 반영본과 다르면 "바뀐 줄만" 출력한다 → 이미 반영한 내용은 다시 읽지 않는다.

실행: python3 00-system/scripts/sync_banned_rules.py [--force] [--quiet]
      python3 00-system/scripts/sync_banned_rules.py --diff            # 미반영 변경만 보기
      python3 00-system/scripts/sync_banned_rules.py --mark-applied "반영 내용 메모"
"""
import difflib
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

FILE_ID = "1VQDWX4DXWb9j_zWVaho1NS8gDBpGaWrb"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST_DIR = os.path.join(ROOT, "00-system", "판매금지-기준")
DEST = os.path.join(DEST_DIR, "판매금지-품목-검수기준.md")
META = os.path.join(DEST_DIR, ".sync.json")
REL = "00-system/판매금지-기준/판매금지-품목-검수기준.md"
APPLIED = os.path.join(DEST_DIR, ".applied.md")          # 마지막으로 스킬에 반영한 판
LEDGER = os.path.join(DEST_DIR, "반영대장.md")            # 반영 이력(사람이 읽는 표)


def run_gws(args, cwd=None, timeout=30):
    """gws 명령 실행 후 마지막 JSON 덩어리를 돌려준다."""
    p = subprocess.run(["gws"] + args, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    out = p.stdout.strip()
    if p.returncode != 0:
        raise RuntimeError((p.stderr or out).strip()[-300:])
    start = out.find("{")
    return json.loads(out[start:]) if start >= 0 else {}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def load_meta():
    try:
        with open(META, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def pending_diff():
    """반영본 대비 바뀐 줄만 돌려준다. 미반영 없으면 빈 리스트."""
    if not os.path.exists(DEST):
        return []
    new = open(DEST, encoding="utf-8").read().splitlines()
    old = open(APPLIED, encoding="utf-8").read().splitlines() if os.path.exists(APPLIED) else []
    if new == old:
        return []
    out = []
    for ln in difflib.unified_diff(old, new, lineterm="", n=0):
        if ln.startswith(("---", "+++", "@@")):
            continue
        if ln[1:].strip():
            out.append(("추가 " if ln[0] == "+" else "삭제 ") + ln[1:])
    return out


def report_pending():
    d = pending_diff()
    if not d:
        return
    head = "전체(처음 반영)" if not os.path.exists(APPLIED) else f"{len(d)}줄"
    print(f"[판매금지기준] 스킬 미반영 변경 {head} — 바뀐 점을 용팀장에게 보고하고 반영안 제시 → 승인 후 반영 → --mark-applied")
    if os.path.exists(APPLIED):
        for ln in d[:60]:
            print("  " + ln)
        if len(d) > 60:
            print(f"  ...외 {len(d)-60}줄 (--diff 로 전체)")


def mark_applied(memo):
    if not os.path.exists(DEST):
        print("[판매금지기준] 사본이 없어 반영 기록 불가")
        return 1
    if os.path.exists(APPLIED):
        os.chmod(APPLIED, stat.S_IRUSR | stat.S_IWUSR)
    shutil.copyfile(DEST, APPLIED)
    os.chmod(APPLIED, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    mt = load_meta().get("modifiedTime", "?")
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", encoding="utf-8") as f:
        if new:
            f.write("# 판매금지 기준 반영 대장\n\n드라이브 판이 스킬 기준에 반영된 기록. 여기 적힌 판까지는 다시 읽지 않는다.\n\n"
                    "| 반영일 | 드라이브 판(수정시각) | 반영 내용 |\n|---|---|---|\n")
        f.write(f"| {datetime.now().strftime('%Y-%m-%d %H:%M')} | {mt} | {memo} |\n")
    print(f"[판매금지기준] 반영 완료로 기록 (드라이브 판 {mt})")
    return 0


def main():
    if "--mark-applied" in sys.argv:
        i = sys.argv.index("--mark-applied")
        memo = sys.argv[i + 1] if len(sys.argv) > i + 1 else "(메모 없음)"
        return mark_applied(memo)
    if "--diff" in sys.argv:
        d = pending_diff()
        print("\n".join(d) if d else "[판매금지기준] 미반영 변경 없음")
        return 0
    force = "--force" in sys.argv
    quiet = "--quiet" in sys.argv
    os.makedirs(DEST_DIR, exist_ok=True)
    meta = load_meta()

    # 1) 드라이브 정본의 수정시각·체크섬 조회
    try:
        info = run_gws(["drive", "files", "get", "--params", json.dumps({
            "fileId": FILE_ID, "supportsAllDrives": True,
            "fields": "id,name,modifiedTime,md5Checksum,trashed"})])
    except Exception as e:
        have = "기존 사본 사용" if os.path.exists(DEST) else "사본 없음 — 기준 확인 불가"
        print(f"[판매금지기준] 드라이브 조회 실패({have}): {e}")
        report_pending()
        return 0
    if info.get("trashed"):
        print("[판매금지기준] 경고: 드라이브 정본이 휴지통에 있음. 기존 사본 유지. 이룸님께 확인 필요.")
        return 0

    remote_mt = info.get("modifiedTime", "")
    remote_md5 = info.get("md5Checksum", "")
    local_ok = os.path.exists(DEST) and meta.get("md5") and md5(DEST) == meta.get("md5")
    tampered = os.path.exists(DEST) and meta.get("md5") and not local_ok

    if local_ok:  # 동기화 등으로 권한이 풀렸으면 다시 읽기 전용으로
        os.chmod(DEST, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    if not force and local_ok and meta.get("modifiedTime") == remote_mt:
        if not quiet:
            print(f"[판매금지기준] 최신 (드라이브 수정 {remote_mt}) → {REL}")
        report_pending()
        return 0

    # 2) 새로 받기 — 임시 폴더에 받은 뒤 교체
    try:
        tmpdir = tempfile.mkdtemp(prefix="banned_rules_")
        run_gws(["drive", "files", "get", "--params", json.dumps({
            "fileId": FILE_ID, "alt": "media", "supportsAllDrives": True}),
            "-o", "rules.md"], cwd=tmpdir, timeout=60)
        tmp = os.path.join(tmpdir, "rules.md")
        if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            raise RuntimeError("받은 파일이 비어 있음")
        if remote_md5 and md5(tmp) != remote_md5:
            raise RuntimeError("체크섬 불일치")
        if os.path.exists(DEST):
            os.chmod(DEST, stat.S_IRUSR | stat.S_IWUSR)
        shutil.move(tmp, DEST)
        os.chmod(DEST, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 읽기 전용
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception as e:
        print(f"[판매금지기준] 내려받기 실패(기존 사본 유지): {e}")
        return 0

    with open(META, "w", encoding="utf-8") as f:
        json.dump({"fileId": FILE_ID, "modifiedTime": remote_mt, "md5": md5(DEST),
                   "syncedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                  f, ensure_ascii=False, indent=2)

    why = "로컬 사본이 수정돼 있어 정본으로 덮음" if tampered else (
        "처음 받음" if not meta else "드라이브가 바뀌어 다시 받음")
    print(f"[판매금지기준] 갱신됨({why}, 드라이브 수정 {remote_mt}) → {REL}")
    report_pending()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 어떤 경우에도 세션 시작을 막지 않는다
        print(f"[판매금지기준] 동기화 오류(무시): {e}")
        sys.exit(0)

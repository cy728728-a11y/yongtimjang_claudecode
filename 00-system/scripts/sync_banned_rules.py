# -*- coding: utf-8 -*-
"""
판매금지 품목 검수기준 — 드라이브 정본을 로컬 읽기전용 사본으로 동기화한다.

- 정본: 구글드라이브 50-소스자료/52-키워드-블랙리스트/판매금지-품목-검수기준.md (이룸님 관리)
- 사본: 00-system/판매금지-기준/판매금지-품목-검수기준.md  (읽기 전용, 직접 고치지 않는다)
- 드라이브 수정시각·체크섬이 바뀌었거나 사본이 손상/수정됐으면 다시 받는다.
- 실패해도(인증 만료·네트워크) 기존 사본은 그대로 두고 경고만 출력한다. 작업을 막지 않는다.

실행: python3 00-system/scripts/sync_banned_rules.py [--force] [--quiet]
"""
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


def main():
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
        return 0
    if info.get("trashed"):
        print("[판매금지기준] 경고: 드라이브 정본이 휴지통에 있음. 기존 사본 유지. 이룸님께 확인 필요.")
        return 0

    remote_mt = info.get("modifiedTime", "")
    remote_md5 = info.get("md5Checksum", "")
    local_ok = os.path.exists(DEST) and meta.get("md5") and md5(DEST) == meta.get("md5")
    tampered = os.path.exists(DEST) and meta.get("md5") and not local_ok

    if not force and local_ok and meta.get("modifiedTime") == remote_mt:
        if not quiet:
            print(f"[판매금지기준] 최신 (드라이브 수정 {remote_mt}) → {REL}")
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
    print(f"[판매금지기준] 갱신됨({why}, 드라이브 수정 {remote_mt}) → {REL} — 작업 전 다시 읽을 것")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 어떤 경우에도 세션 시작을 막지 않는다
        print(f"[판매금지기준] 동기화 오류(무시): {e}")
        sys.exit(0)

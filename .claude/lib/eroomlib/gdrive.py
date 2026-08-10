#!/usr/bin/env python3
"""구글드라이브 셀러라이프 데이터 헬퍼 — 통다운·블랙리스트의 원본 보관처가 드라이브다.

로컬 D: 용량 압박으로 셀러라이프 산출물(runs/<YYMMDD>, keyword_blacklist)을
드라이브 `50-소스자료/51-셀러라이프-통다운/` 아래로 이관했다(2026-08-01).
읽는 쪽은 전부 이 모듈의 resolve_raw_dir() / ensure_blacklist() 를 거친다:

  1. 로컬 runs(<paths.sellerlife_runs>)에 파일이 있으면 그대로 쓴다 (이관 전 호환)
  2. 없으면 드라이브에서 캐시(<paths.sellerlife_cache>)로 내려받아 그 경로를 준다
  3. md5 가 같으면 재다운로드하지 않는다 (중단돼도 재실행이 이어받는다)

**원본 계약 = 전체카테고리 zip** (2026-08-06). 드라이브 `<YYMMDD>/raw/` 에 반드시
`*_전체카테고리.zip`(12개 대분류 통째) 이 있어야 한다. 셀러라이프 *가공* 은 3개 대분류
(가구/인테리어·디지털/가전·생활/건강)만 쓰지만, **상품명 스킬(cat_prefilter)은 상품
카테고리가 뭐가 될지 몰라 12개 전부가 필요**하고 zip 에서 그때그때 뽑아 쓴다.
추출본(SellarSourcing_*.xlsx)은 zip 에서 언제든 재생성되므로 드라이브에 올리지 않는다.

**신선도 7일** — source_date 를 비우면(auto) 최신 통다운을 고르고, 7일을 넘겼거나
zip 이 없으면 셀러라이프에서 새로 받는다(refresh_run). 날짜를 명시하면 그대로 쓰되
경고만 한다 — 지정한 날짜를 말없이 바꾸면 재현이 안 되기 때문.

gws CLI 를 subprocess 로 부른다(gws 인증 계정 — gsheets.py 와 동일 셔임 우회).
gws 는 --upload / -o 대상이 CWD 밖이면 거부하므로 cwd 를 파일 폴더로 옮겨 부른다.

CLI:
  python -m eroomlib.gdrive fetch-run 260731
  python -m eroomlib.gdrive fetch-blacklist
  python -m eroomlib.gdrive push-blacklist [경로]
  python -m eroomlib.gdrive upload-run <로컬 run 폴더> [--name 260731]
  python -m eroomlib.gdrive runs                  # 통다운 목록 + 나이 + zip 유무
  python -m eroomlib.gdrive resolve [YYMMDD]      # 실제로 쓰일 raw 폴더 (7일 규칙 적용)
  python -m eroomlib.gdrive refresh               # 지금 바로 새 통다운 받기
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date

from .config import cfg, workspace_root
from .gsheets import _GWS_CMD, _with_retry

FOLDER_MIME = "application/vnd.google-apps.folder"
BLACKLIST_DIRNAME = "keyword_blacklist"
BLACKLIST_FILENAME = "keyword_blacklist.xlsx"
# 업로드 제외: 엑셀 임시 잠금 파일
_SKIP_PREFIXES = ("~$",)

# 통다운 날짜 폴더(YYMMDD)만 통다운으로 센다 — keyword_blacklist·_legacy 는 제외된다.
RUN_DATE_RE = re.compile(r"^\d{6}$")
# 이 날짜를 넘긴 통다운은 낡은 것으로 본다(키워드 지표가 바뀐다).
DEFAULT_MAX_AGE_DAYS = 7
# source_date 자리에 이게 오면 "최신을 알아서 고르라"는 뜻
_AUTO_TOKENS = {"", "auto", "latest", "최신"}


def _root_folder():
    return cfg("drive.sellerlife_folder", required=True)


def _cache_root():
    return os.path.expanduser(cfg("paths.sellerlife_cache", required=True))


def _gws(args, body=None, cwd=None, parse=True):
    """gws 실행. parse=True 면 stdout 의 JSON 을 파싱하고 API 오류를 예외로 올린다."""
    cmd = list(_GWS_CMD) + args
    if body is not None:
        cmd += ["--json", json.dumps(body, ensure_ascii=False)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd)
    out = proc.stdout or ""
    if not parse:
        if proc.returncode != 0:
            raise RuntimeError(f"gws 실패 (exit {proc.returncode}): "
                               f"{(proc.stderr or out)[:300]}")
        return out
    start = min([i for i in (out.find("{"), out.find("[")) if i >= 0] or [-1])
    if start < 0:
        raise RuntimeError(f"gws JSON 응답 없음 (exit {proc.returncode}): "
                           f"{(proc.stderr or out)[:300]}")
    data = json.loads(out[start:])
    # gws 는 API 오류도 exit 0 + JSON 으로 돌려준다 — 반드시 예외로 올린다(gsheets 동일).
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        err = data["error"]
        raise RuntimeError(f"gws API 오류 {err.get('code')}: "
                           f"{str(err.get('message'))[:300]}")
    return data


def _local_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_children(folder_id):
    """폴더 바로 아래 항목들 (id, name, mimeType, size, md5Checksum)."""
    params = {"q": f"'{folder_id}' in parents and trashed=false",
              "fields": "files(id,name,mimeType,size,md5Checksum)",
              "pageSize": 1000}
    data = _with_retry(
        lambda: _gws(["drive", "files", "list", "--params", json.dumps(params)]),
        "drive files list")
    return data.get("files", [])


def find_child(folder_id, name):
    """이름 일치하는 자식 1개 (없으면 None). 이름 안의 따옴표·& 문제를 피해 list 후 매칭."""
    for f in list_children(folder_id):
        if f.get("name") == name:
            return f
    return None


def download_file(file_id, dest_path, expect_md5=None):
    """파일 1개 다운로드 + (가능하면) md5 검증."""
    dest_dir = os.path.dirname(os.path.abspath(dest_path))
    os.makedirs(dest_dir, exist_ok=True)
    params = {"fileId": file_id, "alt": "media"}
    _with_retry(
        lambda: _gws(["drive", "files", "get", "--params", json.dumps(params),
                      "-o", os.path.basename(dest_path)],
                     cwd=dest_dir, parse=False),
        "drive files get(media)")
    if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
        raise RuntimeError(f"다운로드 결과가 비어 있습니다: {dest_path}")
    if expect_md5 and _local_md5(dest_path) != expect_md5:
        raise RuntimeError(f"md5 불일치(다운로드 손상 의심): {dest_path}")
    return dest_path


def mirror_folder(folder_id, dest_dir):
    """드라이브 폴더를 로컬로 재귀 미러. md5 가 같은 파일은 건너뛴다(재개 안전)."""
    os.makedirs(dest_dir, exist_ok=True)
    for f in list_children(folder_id):
        dest = os.path.join(dest_dir, f["name"])
        if f.get("mimeType") == FOLDER_MIME:
            mirror_folder(f["id"], dest)
            continue
        want = f.get("md5Checksum")
        if want and os.path.exists(dest) and _local_md5(dest) == want:
            continue
        size_mb = int(f.get("size") or 0) / 1e6
        print(f"[gdrive] 다운로드 {f['name']} ({size_mb:.1f}MB)...", flush=True)
        download_file(f["id"], dest, expect_md5=want)
    return dest_dir


def ensure_run(source_date, only_raw=True):
    """통다운 <YYMMDD> 폴더를 캐시에 확보하고 로컬 base 경로를 반환.

    only_raw=True(기본)면 원본(raw/)만 미러한다. 날짜 폴더에는 가공 산출물
    (filtered/·detected/·최종_·검토_)도 같이 들어 있는데, 읽는 쪽이 필요한 건
    원본뿐이라 통째로 미러하면 1GB 넘게 헛으로 내려받는다.
    """
    folder = find_child(_root_folder(), str(source_date))
    if folder is None:
        raise RuntimeError(
            f"드라이브(51-셀러라이프-통다운)에 '{source_date}' 폴더가 없습니다. "
            f"통다운 날짜를 확인하세요.")
    base = os.path.join(_cache_root(), "runs", str(source_date))
    if only_raw:
        raw = find_child(folder["id"], "raw")
        if raw is not None and raw.get("mimeType") == FOLDER_MIME:
            mirror_folder(raw["id"], os.path.join(base, "raw"))
            return base
        # 평면 레이아웃(<date>/ 바로 아래 원본) — 날짜 폴더 자체가 raw 다
    return mirror_folder(folder["id"], base)


def _has_source_files(d):
    """통다운 원본으로 쓸 수 있는 파일(xlsx/zip)이 폴더에 있는가."""
    try:
        return any(n.lower().endswith((".xlsx", ".zip")) and not n.startswith("~$")
                   for n in os.listdir(d))
    except OSError:
        return False


def has_zip(d):
    """전체카테고리 zip(= 12개 대분류 원본)이 그 폴더에 있는가."""
    try:
        return any(n.lower().endswith(".zip") and not n.startswith("~$")
                   for n in os.listdir(d))
    except OSError:
        return False


def _pick_raw(base):
    """레이아웃 2종 흡수: <date>/raw/ 가 있으면 raw, 아니면 <date>/ 자체."""
    raw = os.path.join(base, "raw")
    if os.path.isdir(raw) and _has_source_files(raw):
        return raw
    if os.path.isdir(base) and _has_source_files(base):
        return base
    return None


# ---------------------------------------------------------------------------
# 통다운 신선도 (7일 규칙)
# ---------------------------------------------------------------------------

def parse_run_date(name):
    """'260803' -> date(2026, 8, 3). 통다운 날짜 형식이 아니면 None."""
    s = str(name or "").strip()
    if not RUN_DATE_RE.match(s):
        return None
    try:
        return date(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))
    except ValueError:
        return None


def list_run_dates():
    """드라이브에 있는 통다운 날짜 폴더명 목록(오름차순). YYMMDD 형식만."""
    return sorted(f["name"] for f in list_children(_root_folder())
                  if f.get("mimeType") == FOLDER_MIME and parse_run_date(f.get("name")))


def latest_run_date():
    """가장 최근 통다운 날짜(YYMMDD). 하나도 없으면 None."""
    dates = list_run_dates()
    return dates[-1] if dates else None


def run_age_days(source_date, today=None):
    """통다운 날짜가 며칠 지났는지. 날짜 형식이 아니면 None."""
    d = parse_run_date(source_date)
    if d is None:
        return None
    return ((today or date.today()) - d).days


def _refresh_dest(ymd):
    """새 통다운을 받을 로컬 폴더(<runs>/<YYMMDD>/raw).

    셀러라이프 데이터 루트가 이 PC에 없으면(예: 맥 — 기본값이 D: 경로다) 읽기 캐시에
    받는다. 없는 드라이브 문자로 makedirs 하면 엉뚱한 곳에 'D:' 폴더가 생긴다.
    """
    runs = cfg("paths.sellerlife_runs", required=True)
    if not os.path.isdir(runs):
        runs = os.path.join(_cache_root(), "runs")
    dest = os.path.join(runs, str(ymd), "raw")
    os.makedirs(dest, exist_ok=True)
    return dest


def refresh_run(headless=False, timeout=3600):
    """셀러라이프에서 통다운을 새로 받아 드라이브에 올리고 그 날짜(YYMMDD)를 반환.

    **원본(zip)만 확보한다.** 필터·Gemini 판정·최종/검토 분리는 크레딧과 사람 승인이
    걸린 단계라 여기서 자동으로 돌리지 않는다 — 그건 sellerlife-keyword 스킬의 몫이다.

    download.py 는 selenium 으로 크롬을 띄우고 구글 세션이 만료됐으면 사람 로그인을
    요구하므로, 출력을 삼키지 않고 그대로 흘린다.
    """
    root = workspace_root()
    script = os.path.join(root or "", ".claude", "skills", "sellerlife-keyword",
                          "scripts", "download.py")
    if not root or not os.path.exists(script):
        raise RuntimeError(
            "통다운을 새로 받으려면 sellerlife-keyword 스킬이 필요한데 "
            f"download.py 를 찾지 못했습니다: {script}")

    ymd = date.today().strftime("%y%m%d")
    dest = _refresh_dest(ymd)
    print(f"[gdrive] 통다운을 새로 받습니다 ({ymd}, 200MB 안팎 · 크롬 창이 뜹니다)...",
          flush=True)
    cmd = [sys.executable, script, "--out-dir", dest]
    if headless:
        cmd.append("--headless")
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                          timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"통다운 재다운로드 실패 (exit {proc.returncode}). "
            "sellerlife-keyword 스킬의 download.py --setup 으로 로그인을 확인하세요.")
    if not _has_source_files(dest):
        raise RuntimeError(f"재다운로드 결과가 비어 있습니다: {dest}")

    print(f"[gdrive] 드라이브 아카이브 ({ymd})...", flush=True)
    upload_run(os.path.dirname(dest), name=ymd)
    return ymd


def _resolve_auto_date(max_age_days, allow_refresh):
    """날짜를 안 준 경우: 최신 통다운을 고르고, 낡았으면 새로 받는다."""
    latest = latest_run_date()
    if latest is None:
        if not allow_refresh:
            raise RuntimeError("드라이브(51-셀러라이프-통다운)에 통다운이 하나도 없습니다.")
        print("[gdrive] 드라이브에 통다운이 없습니다.", flush=True)
        return refresh_run()

    age = run_age_days(latest)
    if age is not None and age <= max_age_days:
        return latest
    if not allow_refresh:
        print(f"[gdrive] 경고: 최신 통다운 {latest} 이 {age}일 지났습니다"
              f"(기준 {max_age_days}일). 자동 갱신이 꺼져 있어 그대로 씁니다.", flush=True)
        return latest
    print(f"[gdrive] 최신 통다운 {latest} 이 {age}일 지나 기준({max_age_days}일)을 "
          f"넘겼습니다.", flush=True)
    return refresh_run()


def _locate_raw(source_date):
    """그 날짜의 raw 폴더를 로컬에 확보(로컬 runs 우선 → 드라이브 캐시)."""
    local = _pick_raw(os.path.join(cfg("paths.sellerlife_runs", required=True),
                                   str(source_date)))
    if local:
        return local
    print(f"[gdrive] 로컬에 통다운 {source_date} 가 없어 드라이브에서 내려받습니다...",
          flush=True)
    cached = _pick_raw(ensure_run(source_date))
    if not cached:
        raise RuntimeError(f"드라이브 {source_date} 폴더에 xlsx/zip 이 없습니다.")
    return cached


def resolve_raw_dir(source_date=None, max_age_days=DEFAULT_MAX_AGE_DAYS,
                    allow_refresh=True, require_zip=True):
    """통다운 raw 폴더의 로컬 경로. 로컬 runs 우선, 없으면 드라이브 캐시.

    run_names.py(product-name)·run_batch.py(keyword-pick)가 공용으로 쓴다.

    source_date 를 비우거나 'auto' 로 주면 **최신 통다운을 고르고 7일 규칙을 적용**한다
    (낡았거나 zip 이 없으면 셀러라이프에서 새로 받는다). 날짜를 명시하면 그 날짜를
    그대로 쓰되 낡았으면 경고한다 — 지정한 날짜를 말없이 바꾸면 재현이 안 된다.
    """
    pinned = str(source_date or "").strip().lower() not in _AUTO_TOKENS
    if pinned:
        source_date = str(source_date).strip()
        age = run_age_days(source_date)
        if age is not None and age > max_age_days:
            print(f"[gdrive] 경고: 통다운 {source_date} 는 {age}일 지났습니다"
                  f"(기준 {max_age_days}일). 최신으로 돌리려면 --source-date 를 "
                  f"비우거나 auto 로 주세요.", flush=True)
    else:
        source_date = _resolve_auto_date(max_age_days, allow_refresh)

    raw = _locate_raw(source_date)
    if require_zip and not has_zip(raw):
        msg = (f"통다운 {source_date} 에 전체카테고리 zip 이 없습니다 — 대상 3개 대분류"
               f"(가구/인테리어·디지털/가전·생활/건강) 밖 상품은 키워드를 못 받습니다: {raw}")
        if not pinned and allow_refresh:
            print(f"[gdrive] {msg}\n[gdrive] 원본이 불완전해 새로 받습니다.", flush=True)
            return _locate_raw(refresh_run())
        print(f"[gdrive] 경고: {msg}", flush=True)
    return raw


# ---------------------------------------------------------------------------
# 블랙리스트 (마스터 = 드라이브. 읽기 전 fetch, blacklist_update 후 push)
# ---------------------------------------------------------------------------

def blacklist_cache_path():
    return os.path.join(_cache_root(), BLACKLIST_DIRNAME, BLACKLIST_FILENAME)


def _blacklist_remote():
    """블랙리스트 정본 파일 메타. 정본은 `52-키워드-블랙리스트/` 한 곳뿐이다(2026-08-08).

    구 위치(`51-셀러라이프-통다운/keyword_blacklist/`)를 폴백으로 남긴 이유는 이관 시점에
    구버전 config 를 쓰는 PC(용팀장 등)가 조용히 죽지 않게 하기 위해서다. 구 위치에는
    백업본(`*.bak_*.xlsx`)만 남겨뒀고 정본은 옮겼으므로, 폴백이 실제로 파일을 찾으면
    그건 **누군가 옛 자리에 다시 올린 것** = 두 벌이 생긴 상태라 경고를 띄운다.
    """
    root = cfg("drive.blacklist_folder", required=False)
    if root:
        f = find_child(root, BLACKLIST_FILENAME)
        if f is not None:
            return f

    d = find_child(_root_folder(), BLACKLIST_DIRNAME)
    f = find_child(d["id"], BLACKLIST_FILENAME) if d else None
    if f is None:
        raise RuntimeError(
            "드라이브에 keyword_blacklist.xlsx 가 없습니다 "
            "(정본 위치: 50-소스자료 > 52-키워드-블랙리스트).")
    print("[gdrive] 경고: 정본(52-키워드-블랙리스트)이 아니라 구 위치에서 블랙리스트를 "
          "찾았습니다. 두 벌이 돌고 있을 수 있습니다.", flush=True)
    return f


def ensure_blacklist():
    """드라이브 마스터 블랙리스트를 캐시에 확보하고 로컬 경로 반환 (md5 같으면 재사용)."""
    dest = blacklist_cache_path()
    f = _blacklist_remote()
    want = f.get("md5Checksum")
    if want and os.path.exists(dest) and _local_md5(dest) == want:
        return dest
    print("[gdrive] 블랙리스트 마스터 다운로드...", flush=True)
    return download_file(f["id"], dest, expect_md5=want)


def push_blacklist(path=None):
    """로컬(보통 캐시)의 블랙리스트를 드라이브 마스터에 덮어쓴다(새 리비전)."""
    path = os.path.abspath(path or blacklist_cache_path())
    if not os.path.exists(path):
        raise RuntimeError(f"업로드할 블랙리스트가 없습니다: {path}")
    f = _blacklist_remote()
    params = {"fileId": f["id"], "fields": "id,md5Checksum"}
    res = _with_retry(
        lambda: _gws(["drive", "files", "update", "--params", json.dumps(params),
                      "--upload", os.path.basename(path)],
                     cwd=os.path.dirname(path)),
        "drive files update(blacklist)")
    if res.get("md5Checksum") != _local_md5(path):
        raise RuntimeError("push 후 md5 불일치 — 드라이브 반영을 확인하세요.")
    print(f"[gdrive] 블랙리스트 push 완료 (fileId={f['id']})")
    return f["id"]


# ---------------------------------------------------------------------------
# run 업로드 (셀러라이프 파이프라인 산출물을 드라이브로 아카이브)
# ---------------------------------------------------------------------------

def ensure_folder(parent_id, name):
    """parent 아래 name 폴더 확보(있으면 재사용) 후 id 반환."""
    found = find_child(parent_id, name)
    if found:
        return found["id"]
    res = _with_retry(
        lambda: _gws(["drive", "files", "create",
                      "--params", json.dumps({"fields": "id,name"})],
                     body={"name": name, "mimeType": FOLDER_MIME,
                           "parents": [parent_id]}),
        "drive files create(folder)")
    return res["id"]


def _upload_file(folder_id, path, existing=None):
    """파일 1개 업로드. 같은 이름이 있으면 md5 비교 후 갱신(update)/건너뜀."""
    local_md5 = _local_md5(path)
    if existing is not None:
        if existing.get("md5Checksum") == local_md5:
            return "skip"
        args = ["drive", "files", "update",
                "--params", json.dumps({"fileId": existing["id"],
                                        "fields": "id,md5Checksum"})]
        body = None
        what = "drive files update"
    else:
        args = ["drive", "files", "create",
                "--params", json.dumps({"fields": "id,md5Checksum"})]
        body = {"name": os.path.basename(path), "parents": [folder_id]}
        what = "drive files create"
    res = _with_retry(
        lambda: _gws(args + ["--upload", os.path.basename(path)],
                     body=body, cwd=os.path.dirname(os.path.abspath(path))),
        what)
    if res.get("md5Checksum") != local_md5:
        raise RuntimeError(f"업로드 후 md5 불일치: {path}")
    return "update" if existing else "create"


def upload_run(local_base, name=None, omit=None):
    """로컬 run 폴더(runs/<YYMMDD>)를 드라이브로 미러 업로드.

    이미 있는 파일은 md5 가 같으면 건너뛰고 다르면 새 리비전으로 갱신한다.
    빈 폴더는 만들지 않는다.

    omit(상대경로) -> True 면 그 파일은 아예 올리지 않는다. zip 에서 다시 뽑을 수 있는
    추출본(SellarSourcing_*.xlsx, 600MB)을 드라이브에 쌓지 않으려고 쓴다.
    """
    local_base = os.path.abspath(local_base)
    name = name or os.path.basename(os.path.normpath(local_base))
    stats = {"create": 0, "update": 0, "skip": 0, "omit": 0}

    def _walk(local_dir, parent_id, folder_id=None):
        entries = sorted(os.listdir(local_dir))
        files = [e for e in entries
                 if os.path.isfile(os.path.join(local_dir, e))
                 and not e.startswith(_SKIP_PREFIXES)]
        if omit:
            kept = []
            for e in files:
                rel = os.path.relpath(os.path.join(local_dir, e), local_base)
                if omit(rel):
                    stats["omit"] += 1
                else:
                    kept.append(e)
            files = kept
        dirs = [e for e in entries if os.path.isdir(os.path.join(local_dir, e))]
        if not files and not dirs:
            return
        fid = folder_id or ensure_folder(parent_id, os.path.basename(local_dir))
        remote = {f["name"]: f for f in list_children(fid)} if (files or dirs) else {}
        for e in files:
            p = os.path.join(local_dir, e)
            r = _upload_file(fid, p, existing=remote.get(e))
            stats[r] += 1
            if r != "skip":
                print(f"[gdrive] {r}: {os.path.relpath(p, local_base)}", flush=True)
        for e in dirs:
            sub = remote.get(e)
            _walk(os.path.join(local_dir, e), fid,
                  folder_id=sub["id"] if sub and sub.get("mimeType") == FOLDER_MIME else None)

    top_id = ensure_folder(_root_folder(), name)
    _walk(local_base, _root_folder(), folder_id=top_id)
    print(f"[gdrive] 업로드 완료({name}): 신규 {stats['create']} · "
          f"갱신 {stats['update']} · 동일 {stats['skip']} · 제외 {stats['omit']}")
    return stats


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="셀러라이프 드라이브 헬퍼")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch-run", help="통다운 <YYMMDD> 를 캐시로 다운로드")
    p.add_argument("date")
    sub.add_parser("fetch-blacklist", help="블랙리스트 마스터를 캐시로 다운로드")
    p = sub.add_parser("push-blacklist", help="로컬 블랙리스트를 드라이브 마스터로 업로드")
    p.add_argument("path", nargs="?", default=None)
    p = sub.add_parser("upload-run", help="로컬 run 폴더를 드라이브로 미러 업로드")
    p.add_argument("dir")
    p.add_argument("--name", default=None, help="드라이브 폴더명(기본: 폴더 basename)")
    sub.add_parser("runs", help="드라이브 통다운 목록 (나이 · zip 유무)")
    p = sub.add_parser("resolve", help="실제로 쓰일 raw 폴더 경로 (7일 규칙 적용)")
    p.add_argument("date", nargs="?", default=None, help="YYMMDD (생략 = 최신+7일 규칙)")
    p.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    p.add_argument("--no-refresh", action="store_true", help="낡아도 새로 받지 않는다")
    p = sub.add_parser("refresh", help="지금 바로 셀러라이프에서 새 통다운 받기")
    p.add_argument("--headless", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "fetch-run":
        print(ensure_run(args.date))
    elif args.cmd == "fetch-blacklist":
        print(ensure_blacklist())
    elif args.cmd == "push-blacklist":
        push_blacklist(args.path)
    elif args.cmd == "upload-run":
        upload_run(args.dir, name=args.name)
    elif args.cmd == "runs":
        today = date.today()
        for d in list_run_dates():
            age = run_age_days(d, today)
            fresh = "신선" if age is not None and age <= DEFAULT_MAX_AGE_DAYS else "만료"
            folder = find_child(_root_folder(), d)
            raw = find_child(folder["id"], "raw") if folder else None
            kids = list_children(raw["id"] if raw else folder["id"]) if folder else []
            zips = [f["name"] for f in kids if f["name"].lower().endswith(".zip")]
            print(f"{d}  {age:>3}일  {fresh}  "
                  f"zip={'O ' + zips[0] if zips else 'X (전체카테고리 원본 없음)'}")
    elif args.cmd == "resolve":
        print(resolve_raw_dir(args.date, max_age_days=args.max_age_days,
                              allow_refresh=not args.no_refresh))
    elif args.cmd == "refresh":
        print(refresh_run(headless=args.headless))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()

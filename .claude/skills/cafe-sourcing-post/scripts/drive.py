"""구글 드라이브 작업.

- 업로드·공유·목록·휴지통: rclone (구글 정식 승인 연결이라 로그인이 7일마다 풀리지 않음)
- 알림 메일(notify.py)만 gws 를 쓴다 → _gws 는 그쪽 전용

rclone 설정 이름(REMOTE)은 최초 1회 `rclone config create gdrive drive scope=drive` 로 만든다.
폴더 안 파일은 `--drive-root-folder-id <폴더ID>` 로 폴더를 루트처럼 보고 이름으로 다룬다.
"""
import json
import os
import shutil
import subprocess

FOLDER_ID = "1tHxVObirOwYoxAZAcslA24mV_VctmJXB"  # cy728728 계정의 카페 공유 폴더
REMOTE = "gdrive"
MARK_PREFIX = "posted_"  # 게시 표시 파일: posted_<zip이름에서 .zip 뺀 것>.txt


class DriveError(Exception):
    """드라이브 작업 실패"""


class DriveAuthError(DriveError):
    """구글 로그인 만료"""


# ---------------- rclone ----------------
def _rclone_bin() -> str:
    found = shutil.which("rclone")
    if found:
        return found
    if os.name == "nt":  # winget 설치 위치(작업 스케줄러 등 PATH 가 짧을 때)
        p = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links", "rclone.exe")
        if os.path.exists(p):
            return p
    return "rclone"


def _rclone(args: list, folder_id: str = FOLDER_ID, stdin: str = None) -> str:
    """rclone 한 번 실행하고 표준출력을 돌려준다. 실패하면 DriveError / DriveAuthError."""
    cmd = [_rclone_bin()] + args + ["--drive-root-folder-id", folder_id]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           timeout=3600, input=stdin)
    except Exception as e:  # rclone 없음, 시간 초과 등
        raise DriveError(f"rclone 실행 실패: {e}") from e
    if p.returncode != 0:
        err = (p.stderr or "") + (p.stdout or "")
        if any(k in err for k in ("invalid_grant", "couldn't fetch token", "token expired", "401")):
            raise DriveAuthError("구글 드라이브 로그인이 풀렸어요 (rclone config reconnect gdrive: 필요)")
        raise DriveError(f"rclone 오류: {err.strip()[:500]}")
    return p.stdout or ""


def _ls(folder_id: str) -> list:
    out = _rclone(["lsjson", f"{REMOTE}:", "--files-only"], folder_id)
    try:
        return json.loads(out or "[]")
    except ValueError as e:
        raise DriveError(f"목록 읽기 실패: {out[:200]}") from e


def _mark_name(name: str) -> str:
    return MARK_PREFIX + os.path.splitext(name)[0] + ".txt"


def upload(zip_path: str, name: str, folder_id: str) -> str:
    """zip 을 폴더에 올리고 파일 ID 를 돌려준다."""
    _rclone(["copyto", zip_path, f"{REMOTE}:{name}"], folder_id)
    for f in _ls(folder_id):
        if f.get("Name") == name:
            return f["ID"]
    raise DriveError(f"업로드 후 파일을 찾지 못했습니다: {name}")


def share_anyone_reader(name: str) -> None:
    """링크가 있는 모든 사람 보기 권한(rclone link 가 공개 링크를 만든다)."""
    _rclone(["link", f"{REMOTE}:{name}"])


def file_link(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link"


def list_folder(folder_id: str) -> list:
    """폴더 안 파일 목록: [{id, name, createdTime}]"""
    return [{"id": f.get("ID"), "name": f.get("Name"), "createdTime": f.get("ModTime", "")}
            for f in _ls(folder_id)]


def find_by_name(folder_id: str, name: str):
    """같은 이름 파일 하나(없으면 None). description = 게시 표시 파일 내용(없으면 '')."""
    files = _ls(folder_id)
    hit = next((f for f in files if f.get("Name") == name), None)
    if not hit:
        return None
    desc = ""
    if any(f.get("Name") == _mark_name(name) for f in files):
        desc = _rclone(["cat", f"{REMOTE}:{_mark_name(name)}"], folder_id).strip()
    return {"id": hit["ID"], "name": name, "description": desc}


def set_description(name: str, text: str) -> None:
    """'게시함' 표시를 작은 텍스트 파일로 남긴다 — 다른 PC 에서도 이미 게시한 걸 알 수 있게."""
    _rclone(["rcat", f"{REMOTE}:{_mark_name(name)}"], stdin=text)


def trash(name: str) -> None:
    """휴지통으로 보내기(rclone 기본값이 휴지통 — 30일 안에 복구 가능)."""
    _rclone(["deletefile", f"{REMOTE}:{name}"])


# ---------------- gws (알림 메일 전용) ----------------
def _gws_cmd() -> list:
    """gws 실행 명령. 윈도우는 npm shim(.cmd)을 파이썬이 못 불러서 node 로 직접 실행."""
    if os.name == "nt":
        run_js = os.path.join(os.environ.get("APPDATA", ""), "npm", "node_modules",
                              "@googleworkspace", "cli", "run.js")
        if os.path.exists(run_js):
            return ["node", run_js]
    return [shutil.which("gws") or "gws"]


def _gws(args: list, cwd: str = None) -> dict:
    """gws 한 번 호출하고 JSON 결과를 돌려준다. 실패하면 DriveError / DriveAuthError."""
    cmd = _gws_cmd() + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=600, cwd=cwd)
    except Exception as e:
        raise DriveError(f"gws 실행 실패: {e}") from e
    out = (p.stdout or "").strip()
    text = out + "\n" + (p.stderr or "")
    data = {}
    if "{" in out:  # 앞에 안내 줄이 찍힐 수 있어 첫 '{' 부터 읽는다
        try:
            data = json.loads(out[out.index("{"):])
        except ValueError:
            data = {}
    if p.returncode != 0 or "error" in data:
        if "invalid_grant" in text or '"code": 401' in text or "authError" in text:
            raise DriveAuthError("구글 로그인이 만료됐어요 (gws auth login 필요)")
        raise DriveError(f"gws 오류: {text.strip()[:500]}")
    return data

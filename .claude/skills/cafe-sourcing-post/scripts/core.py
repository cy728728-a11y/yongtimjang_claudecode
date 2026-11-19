"""카페 소싱데이터 자동 게시 — 회차 규칙(외부 호출 없는 순수 함수 모음)."""
import json
import os
import tempfile
import zipfile
from datetime import date

# 회차 기록 파일(저장소 밖, PC마다 하나)
STATE_PATH = os.path.join(os.path.expanduser("~"), ".eroom", "cafe-sourcing-state.json")
FILE_PREFIX = "SellarSourcingAll_"


def make_title(d: date) -> str:
    """게시 제목: '2026년 12월 3일 최신화' (월·일 앞자리 0 없음)."""
    return f"{d.year}년 {d.month}월 {d.day}일 최신화"


def data_date_of_zip(path: str) -> str:
    """zip 안 항목 날짜 중 가장 늦은 날을 'YYYYMMDD' 로 돌려준다(= 셀러라이프 데이터 날짜)."""
    with zipfile.ZipFile(path) as z:
        dates = [i.date_time[:3] for i in z.infolist()]
    if not dates:
        raise ValueError(f"빈 zip 파일입니다: {path}")
    y, m, d = max(dates)
    return f"{y:04d}{m:02d}{d:02d}"


def upload_name(data_date: str) -> str:
    """드라이브에 올릴 파일 이름."""
    return f"{FILE_PREFIX}{data_date}.zip"


def load_state(path: str) -> dict:
    """회차 기록 읽기. 파일이 없으면 빈 기록."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"rounds": {}}


def save_state(path: str, state: dict) -> None:
    """회차 기록 저장. 중간에 끊겨도 파일이 깨지지 않게 임시파일에 쓰고 바꿔 끼운다."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def round_status(state: dict, data_date: str) -> str:
    """'new'(처음) | 'uploaded'(드라이브만 됨) | 'posted'(카페까지 끝)."""
    r = state.get("rounds", {}).get(data_date)
    if not r:
        return "new"
    return "posted" if r.get("article_url") else "uploaded"


def files_to_trash(files: list, keep: int = 3) -> list:
    """드라이브 폴더 목록 중 우리 zip 만 골라 최신 keep 개를 뺀 나머지를 돌려준다."""
    ours = [f for f in files if f.get("name", "").startswith(FILE_PREFIX)]
    ours.sort(key=lambda f: f.get("name", ""), reverse=True)  # 이름 속 날짜 순(수정시각은 믿을 수 없음)
    return ours[keep:]

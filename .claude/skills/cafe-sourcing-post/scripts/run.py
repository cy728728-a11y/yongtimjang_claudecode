"""카페 소싱데이터 자동 게시 — 전체 흐름.

  받기(셀러라이프) → 새 데이터인지 확인 → 드라이브 업로드·공유 → 카페 실전반 소통방 게시
  → 오래된 zip 휴지통(최근 3개 유지) → 완료 메일. 어느 단계든 막히면 실패 메일(붙여넣을 제목·링크 포함).

사용:
  python run.py                      # 정식 실행(매주 월요일 맥북이 이것을 돌린다)
  python run.py --dry-run            # 받기만 하고 나머지는 '할 일'만 출력
  python run.py --skip-download X.zip  # 이미 받은 zip 으로 진행
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cafe  # noqa: E402
import core  # noqa: E402
import drive  # noqa: E402
import notify  # noqa: E402

STATE_PATH = core.STATE_PATH
SKILLS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DL_SCRIPT = os.path.join(SKILLS_DIR, "sellerlife-keyword", "scripts", "download.py")
SETUP_HINT = {
    "download": f"셀러라이프 로그인이 풀렸을 수 있어. 이 컴퓨터에서 한 번 실행:\n  python {DL_SCRIPT} --setup --wait 600",
    "drive": "구글 드라이브 연결(rclone)이 풀렸을 수 있어. 이 컴퓨터에서 실행: rclone config reconnect gdrive:",
    "cafe": f"네이버 허락이 만료됐을 수 있어. 이 컴퓨터에서 실행:\n  python {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cafe_setup.py')}",
    "unknown": "예상 못 한 오류야. 이 메일을 클로드에게 보여 주면 원인을 찾아 줄게.",
}
POSTED_MARK = "게시: "  # 드라이브 파일 설명란에 '게시: <글주소>' 로 남긴다


class DownloadError(Exception):
    """셀러라이프에서 zip 받기 실패"""


def download_zip(out_dir: str) -> str:
    """기존 download.py 를 창 없이 실행해 받은 zip 경로를 돌려준다."""
    try:
        p = subprocess.run([sys.executable, DL_SCRIPT, "--headless", "--out-dir", out_dir],
                           capture_output=True, text=True, encoding="utf-8", timeout=1800)
    except Exception as e:
        raise DownloadError(f"다운로드 실행 실패: {e}") from e
    lines = (p.stdout or "").splitlines()
    if p.returncode == 0 and "###ARTIFACT###" in lines:
        path = lines[lines.index("###ARTIFACT###") + 1].strip()
        if os.path.exists(path):
            return path
    tail = "\n".join(((p.stdout or "") + (p.stderr or "")).splitlines()[-15:])
    raise DownloadError(f"셀러라이프 다운로드 실패(종료코드 {p.returncode}):\n{tail}")


def _fail(stage: str, err: Exception, title: str = None, link: str = None) -> str:
    """실패 메일: 어디서·왜 막혔는지 + 해결법 + (있으면) 손으로 붙여넣을 제목·링크."""
    body = [f"카페 소싱데이터 자동 게시가 '{stage}' 단계에서 멈췄어.", "", f"사유: {err}", "", SETUP_HINT[stage]]
    if title and link:
        body += ["", "카페엔 직접 올리지 마 — 다음 실행 때 같은 글이 또 올라가.",
                 "위 해결법대로 한 뒤 '카페 자료 지금 올려'라고 하면 아래 내용으로 올라가:",
                 f"  제목: {title}", f"  본문: {link}"]
    notify.send_mail(f"[카페 자료] 자동 게시 실패 — {stage}", "\n".join(body))
    print("\n".join(body))
    return "failed"


def run(today: date, dry_run: bool = False, zip_path: str = None) -> str:
    """한 회차 실행. 돌려주는 값: 'posted' | 'skipped' | 'failed' | 'dry-run'
    단계별로 못 잡은 예상 밖 오류도 여기서 잡아 실패 메일을 보낸다(조용히 빠지는 회차 방지)."""
    try:
        return _run_once(today, dry_run, zip_path)
    except Exception as e:
        return _fail("unknown", e)


def _run_once(today: date, dry_run: bool, zip_path: str) -> str:
    tmp = None
    title = core.make_title(today)
    try:
        # 1) 받기
        if not zip_path:
            tmp = tempfile.mkdtemp(prefix="cafe-sourcing-")
            try:
                zip_path = download_zip(tmp)
            except Exception as e:
                return _fail("download", e)
        data_date = core.data_date_of_zip(zip_path)
        state = core.load_state(STATE_PATH)
        status = core.round_status(state, data_date)
        print(f"데이터 날짜 {data_date} → 상태 {status}")
        if status == "posted":
            print("이미 게시한 데이터야. 이번 주는 할 일 없음.")
            return "skipped"
        if dry_run:
            print(f"[dry-run] {'업로드 ' + core.upload_name(data_date) if status == 'new' else '업로드 건너뜀(이미 올림)'}"
                  f" → 카페 게시 '{title}' → 오래된 zip 정리 → 완료 메일")
            return "dry-run"

        # 2) 드라이브 — 드라이브가 정본: 같은 이름 파일이 있으면 다시 올리지 않고,
        #    설명란에 '게시:' 가 있으면 다른 PC 가 이미 게시한 회차로 본다
        name = core.upload_name(data_date)
        try:
            existing = drive.find_by_name(drive.FOLDER_ID, name)
            if existing and (existing.get("description") or "").startswith(POSTED_MARK):
                state["rounds"][data_date] = {
                    "file_id": existing["id"], "link": drive.file_link(existing["id"]),
                    "article_url": existing["description"][len(POSTED_MARK):], "posted_at": "(다른 PC 에서 게시)"}
                core.save_state(STATE_PATH, state)
                print("드라이브 기록상 이미 게시된 회차야. 할 일 없음.")
                return "skipped"
            if existing:
                fid = existing["id"]
            elif status == "uploaded":
                fid = state["rounds"][data_date]["file_id"]
            else:
                fid = drive.upload(zip_path, name, drive.FOLDER_ID)
            # 업로드 직후 바로 기록(공유에서 끊겨도 다음 실행이 다시 올리지 않게). 기존 기록은 그대로 둔다
            if state["rounds"].get(data_date, {}).get("file_id") != fid:
                state["rounds"][data_date] = {"file_id": fid, "link": drive.file_link(fid),
                                              "article_url": None, "posted_at": None}
                core.save_state(STATE_PATH, state)
            drive.share_anyone_reader(name)  # 매번 해도 안전(이미 공유돼 있어도 그대로)
        except Exception as e:
            return _fail("drive", e)
        link = state["rounds"][data_date]["link"]

        # 3) 카페 게시
        try:
            article = cafe.post_article(cafe.load_config(), title, cafe.make_content(link))
        except Exception as e:
            return _fail("cafe", e, title, link)
        state["rounds"][data_date].update(article_url=article, posted_at=datetime.now().isoformat(timespec="seconds"))
        core.save_state(STATE_PATH, state)
        note = ""
        try:
            drive.set_description(name, POSTED_MARK + article)
        except Exception as e:
            note += f"\n(드라이브에 게시 표시 실패 — 다른 PC 에서 '지금 올려' 하면 중복될 수 있음: {e})"

        # 4) 오래된 zip 정리 — 실패해도 이번 회차는 성공으로 본다
        try:
            for f in core.files_to_trash(drive.list_folder(drive.FOLDER_ID), keep=3):
                drive.trash(f["name"])
                note += f"\n휴지통으로 보냄: {f['name']}"
        except Exception as e:
            note += f"\n(오래된 파일 정리 실패 — 다음 주에 다시 시도: {e})"

        notify.send_mail(f"[카페 자료] {title} 게시 완료",
                         f"실전반 소통방에 올렸어.\n글: {article}\n파일: {link}\n데이터 날짜: {data_date}{note}")
        return "posted"
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="카페 소싱데이터 자동 게시")
    ap.add_argument("--dry-run", action="store_true", help="게시·업로드 없이 할 일만 출력")
    ap.add_argument("--skip-download", metavar="ZIP", help="이미 받은 zip 사용")
    a = ap.parse_args()
    result = run(date.today(), dry_run=a.dry_run, zip_path=a.skip_download)
    print(f"결과: {result}")
    sys.exit(1 if result == "failed" else 0)


if __name__ == "__main__":
    main()

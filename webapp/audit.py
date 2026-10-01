#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""쓰기 잡 감사 로그 (FLOW-07 · D-11).

**쓰기 잡(`jobs.WRITE_KINDS`)이 끝날 때마다 정확히 한 줄**을 append-only JSONL 로 남긴다.
종료 지점은 엔진의 세 곳(정상 종료 · orphaned · spawn 실패)이고, 호출은 전부 **DB 커밋
이후**에만 일어난다 — 롤백될 수 있는 트랜잭션 안에서 파일을 쓰면 "롤백된 종료" 와
"다시 거둔 orphaned" 가 둘 다 남는다(02-RESEARCH Pitfall 2). 그 순서는 `jobs.py` 가 지킨다.

줄 모양(고정 필드만):
  {"시각","잡id","종류","부모잡id","계정","대상수","성공","실패","제외","크레딧","종료코드","상태"}

· **argv·환경변수를 싣지 않는다** (T-02-14). 지금 argv 에 시크릿은 없지만, 감사 파일은
  오래 남고 여러 곳에 복사되는 파일이라 "지금은 없다" 에 기대지 않는다.
· **"0 건 성공" 과 "모름" 을 구분한다.** 모르면 None(JSON null)이다. 0 으로 지어내면
  감사 기록이 거짓말을 한다 — 실제로는 결과 파일을 못 읽은 것인데 "아무것도 안 했다" 로 읽힌다.
· 기록 실패는 **삼킨다**. 감사 파일이 안 써진다고 잡 종료 기록(DB)이 막히면 그쪽이 더 나쁘다
  — 전역 쓰기 가드가 풀리지 않는다. 대신 print(flush=True) 로 경고를 남긴다.
"""
import json
import os
from datetime import datetime
from pathlib import Path

from webapp import paths, settings


def audit_path() -> Path:
    """감사 파일 경로. `CT_AUDIT_PATH` > 설정 `audit_path` > `<데이터루트>/control-tower/audit.jsonl`.

    환경변수가 맨 앞인 이유: 테스트(conftest autouse)와 UAT 격리 인스턴스가 실 데이터루트를
    건드리지 않게 하는 유일한 통로다(Pitfall 3). 별도 프로세스엔 monkeypatch 가 안 닿는다.
    """
    env = os.environ.get("CT_AUDIT_PATH")
    if env:
        return Path(env).expanduser()
    try:
        설정 = settings.cfg("audit_path", settings.DEFAULTS["audit_path"])
    except Exception:
        설정 = ""
    if 설정:
        p = Path(str(설정)).expanduser()
        return p if p.is_absolute() else paths.repo_root() / p
    return paths.data_root() / "control-tower" / "audit.jsonl"


def _읽기(경로) -> dict:
    """결과 파일을 dict 로. 없거나 깨지면 예외를 올린다 — 호출부가 요약오류로 바꾼다."""
    if not 경로:
        raise FileNotFoundError("result_path 없음")
    raw = json.loads(Path(경로).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("결과 파일이 객체가 아니다")
    return raw


def _int_or_none(v):
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def summarize(row: dict) -> dict:
    """kind 별 요약 {대상수, 성공, 실패, 제외, 크레딧}.

    · prune_commit : 산출물 accounts.*.items 의 `결과` 별 합 — 성공=성공+이미없음,
                     실패=실패+재시도소진, 제외=accounts.*.excluded 수, 크레딧 0(광고 API)
    · bids_commit  : flow.result_counts — 성공/실패/스킵(제외), 크레딧 0
    · detail_*     : summary 의 집계(완료/실패/스킵/실제크레딧). 못 읽으면 크레딧 None
    · 그 밖의 쓰기 : 성공·실패 None(모른다), 크레딧 0(크레딧을 태우지 않는 잡)

    추출 실패는 삼키고 `{"요약오류": 예외이름}` 을 덧붙인다 — 잡 종료를 막지 않는다.
    """
    kind = row.get("kind")
    요약 = {"대상수": _int_or_none(row.get("target_count")),
            "성공": None, "실패": None, "제외": None, "크레딧": 0}
    try:
        if kind == "prune_commit":
            문서 = _읽기(row.get("result_path"))
            성공 = 실패 = 제외 = 0
            for v in (문서.get("accounts") or {}).values():
                v = v if isinstance(v, dict) else {}
                for it in v.get("items") or []:
                    결과 = (it or {}).get("결과")
                    if 결과 in ("성공", "이미없음"):
                        성공 += 1
                    elif 결과 in ("실패", "재시도소진"):
                        실패 += 1
                제외 += len(v.get("excluded") or [])
            요약.update(성공=성공, 실패=실패, 제외=제외)
        elif kind == "bids_commit":
            from webapp import flow          # 지연 import — flow 가 무겁고 jobs 와 엮이지 않게
            셈 = flow.result_counts(_읽기(row.get("result_path")))
            요약.update(성공=셈.get("성공", 0), 실패=셈.get("실패", 0), 제외=셈.get("스킵", 0))
        elif kind in ("detail_submit", "detail_poll"):
            요약["크레딧"] = None             # 못 읽으면 모른다 — 0 이 아니다
            집계 = _읽기(row.get("result_path")).get("집계") or {}
            요약.update(성공=_int_or_none(집계.get("완료")), 실패=_int_or_none(집계.get("실패")),
                        제외=_int_or_none(집계.get("스킵")),
                        크레딧=_int_or_none(집계.get("실제크레딧")))
    except Exception as e:
        요약["요약오류"] = type(e).__name__
    return 요약


def _계정(값):
    """jobs.accounts 컬럼(JSON 문자열)을 리스트로. 못 읽으면 원문 그대로."""
    if isinstance(값, list):
        return 값
    try:
        v = json.loads(값) if 값 else []
        return v if isinstance(v, list) else 값
    except Exception:
        return 값


def record(row: dict) -> None:
    """감사 한 줄 append. **실패는 삼킨다** — 잡 종료를 막지 않는다.

    `open("a")` 한 줄 write 다. 1인·한 줄 수백 바이트라 원자적 append 로 충분하다
    (`misjudged.jsonl` 과 같은 판단). 부모 디렉터리가 없으면 만든다.
    """
    try:
        줄 = {"시각": datetime.now().astimezone().isoformat(timespec="seconds"),
              "잡id": row.get("id"), "종류": row.get("kind"),
              "부모잡id": row.get("parent_job_id"), "계정": _계정(row.get("accounts"))}
        줄.update(summarize(row))
        줄["종료코드"] = row.get("exit_code")
        줄["상태"] = row.get("status")
        경로 = audit_path()
        경로.parent.mkdir(parents=True, exist_ok=True)
        with open(경로, "a", encoding="utf-8") as f:
            f.write(json.dumps(줄, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[감사] 기록 실패 — 잡 종료는 계속된다: {type(e).__name__}: {e}", flush=True)

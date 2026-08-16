#!/usr/bin/env python3
"""썸네일 오케스트레이터 — 스킬 계약(`prep`/`run`/`apply`)을 그대로 따른다.

  prep    : 현황판 대상 확정 → 스냅샷 → **기작업(이미 가공됨) 자동 완료 처리** →
            후보 이미지 확보 → 배치 파일
  run     : **Claude** 가 배치를 읽고 기준 이미지 선택(+레시피 모드면 배경 전략·프롬프트
            작성) → results/result_*.json (스크립트 아님)
  apply   : 승인 게이트 없음(2026-08-06 이룸님) — 검수 판정 주체는 Claude 다.
            생성 후 자동반영이 실측 확인돼(2026-07-28 파일럿) 방어·복원만 남는다.
      apply                 미리보기(대상+기준이미지+예상크레딧). 쓰기 0.
      apply --generate      바로 실제 생성(승인 대기 없음) → 폴링 → **자동반영 방어**
                            (대표가 바뀌었으면 commit 전까지 원래 순서로 복원) →
                            review.html 생성. 여기서 크레딧이 실제로 든다.
      apply --commit        (3축 판정이 끝난 뒤) decisions.json 을 읽어
                            최종 대표 순서로 반영 → 재조회 확인 → 시트·스냅샷·현황판
  audit   : 기존 대표 ↔ 대표옵션 정합검사(크레딧 0). 대상은 prep 이 넘긴
            `audit_targets.json` 뿐 — 현황판 완료* 전건 재대조는 `--sweep` 명시할 때만
            (소급 감사 전용. 2026-08-06 이룸님 — 완료건 재대조는 verdict 와 중복이고
            판정이 흔들려 재작업이 되살아난다).
  verdict : 생성본 3축 판정을 **팬아웃으로** 돌린다(크레딧 0). 9건 이상이면 이 경로.
      verdict               verdict/batches/ 생성 + thumb-fanout(mode:verdict) args 출력
      verdict --commit      vresult_*.json → decisions.json (배치 대비 누락이면 exit 3)
  recover : 폴링 타임아웃으로 놓친 생성 결과를 taskId 로 되찾는다(크레딧 0).
            타임아웃은 실패가 아니라 "아직"이다 — 접수는 됐고 크레딧도 이미 나갔다.
            아직 대기 중이면 그대로 두고, 나중에 다시 부르면 회수된다(멱등).
  restore : before_generate.json 으로 생성 전 순서로 되돌린다.

사용:
  python run_thumbs.py prep    --group-name "1번_용쌤1-1" --run-dir <R> --limit 5
  python run_thumbs.py pending --run-dir <R>            # Workflow(thumb-fanout) args 출력
  python run_thumbs.py apply   --run-dir <R>            # 미리보기
  python run_thumbs.py apply   --run-dir <R> --generate # 실제 생성(크레딧 소모)
  python run_thumbs.py verdict --run-dir <R>            # 판정 배치(9건 이상일 때)
  python run_thumbs.py verdict --run-dir <R> --commit   # 판정 수합 → decisions.json
  python run_thumbs.py apply   --run-dir <R> --commit   # decisions.json 대로 반영
  python run_thumbs.py recover --run-dir <R>            # 타임아웃분 결과 회수(크레딧 0)
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

try:
    # **line_buffering** — 파일로 리다이렉트하면 기본이 완전 버퍼링이라 5~6시간짜리
    # 생성 로그가 끝날 때까지 0바이트다. 진행률을 크레딧 잔액으로 역산하다 크게
    # 어긋났다(추정 126 vs 실제 76, 2026-08-06 결함정리 §2-4).
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

import review_html                                    # noqa: E402
import thumb_rules as R                                # noqa: E402
from eroomlib import matrix, snapshot                  # noqa: E402
from eroomlib.gsheets import (append_rows, ensure_tab,  # noqa: E402
                              sheets_get, sheets_update)
from eroomlib.matrix import _col_letter                # noqa: E402

TASK = "썸네일"        # 현황판 열 이름
TAB = "썸네일"         # 상세 로그 탭


def _to_option_reason(verdict, why):
    """옵션 열에 찍을 되돌림 사유 — **판정 낱말을 맨 앞에 박는다.**

    **왜 필요한가** (2026-08-15 용쌤2-1 3회차 실측). 옵션 쪽 `_close_roundtrip` 은
    왕복 2회차를 판정 낱말(`대표옵션의심`·`기준이미지없음`)로 알아본다 — 배치에 실려 온
    `재작업사유` 에 그 낱말이 있으면 이번이 최소 2회차이므로 `실물기준없음` 을 붙여 왕복을
    끝낸다. 그런데 여기서 넘기던 값은 **워커가 쓴 산문**뿐이었다("대표옵션은 프레임+걸이
    기본형인데 기존대표는 풀세트 구성") — 판정 낱말은 썸네일 열의 `보류(...)` 에만 남고
    옵션 열로는 한 글자도 안 갔다. 그래서 종결 장치가 **한 번도 발화하지 못했고**
    3바퀴를 돌아도 같은 24건이 되돌아왔다(3회차 실측: 낱말이 붙은 건 1건뿐).

    낱말을 앞에 두면 사람이 현황판에서 읽기도 낫다 — 산문보다 분류가 먼저 보인다.
    """
    v, w = str(verdict or "").strip(), str(why or "").strip()
    if not v:
        return w[:80]
    if v in w:                      # 워커가 이미 낱말을 썼으면 겹쳐 쓰지 않는다
        return w[:80]
    return f"{v}: {w}"[:80] if w else v
HEADER = ["상품id", "작업일", "상품명", "모드", "기존대표", "생성본",
          "판정", "사유", "크레딧", "상태"]

BATCH_SIZE = 10
MAX_CANDIDATES = 5     # 배치에 실을 후보(대표 제외) 이미지 상한
POLL_INTERVAL = 10
# 큐가 포화되면 전건이 상한까지 기다렸다 실패한다 — 상품마다 동기라 벽시계가 그대로
# 늘어난다(2026-08-12 25-2 실측: 14건 연속 타임아웃, 건당 5분). **회수 경로가 있으므로
# 짧게 두는 쪽이 낫다**(SKILL.md §알려진 함정) — 접수는 이미 됐고 크레딧도 나갔으니
# `recover` 가 0크레딧으로 걷어온다.
#
# **접수모드는 장애 대응이 아니라 대량 회차의 기본 전략이다**(2026-08-15 2-3 실측).
# 큐가 완전히 정상이어도(타임아웃 0 · 429 0) 인라인은 서버가 이미지를 만드는 시간을
# 상품마다 혼자 기다린다 — 건당 약 80초. `THUMB_POLL_TIMEOUT=20` 으로 접수만 하고
# 넘기면 서버가 병렬로 만들고 `recover` 가 걷어온다 — 건당 약 20초(120건 환산
# 2시간 40분 → 40분). **50건을 넘으면 접수모드를 기본으로 잡는다.**
# 값은 POLL_INTERVAL(10) 의 배수로 준다.
POLL_TIMEOUT = int(os.environ.get("THUMB_POLL_TIMEOUT") or 300)

# 복원 전용 재시도 — 전송층 재시도를 다 쓴 뒤에도 다시 붙는다. 복원 실패는 "미승인
# 이미지가 대표로 살아있다"는 뜻이라 생성 실패보다 훨씬 비싸다(2026-08-05 실측).
# **지수 백오프**(20/40/80/160초, 합계 5분): 고정 20초×4회(합계 80초)로는 DNS 단절이
# 80초를 넘기면 그대로 중단됐다 — 1-2 그룹 5~6시간 생성에서 3회 발생해 그때마다
# run-dir 을 새로 만들어 이어붙였다(2026-08-06 결함정리 §2-5).
RESTORE_RETRIES = 4
RESTORE_BACKOFF = 20

# 팬아웃용 고정 경로 — 규칙 정본과 워커 지시서.
RULES_DOC = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "배경생성-기본.md"))
WORKER_PROMPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "썸네일-워커-프롬프트.md"))
AUDIT_PROMPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "정합검사-판정기준.md"))
VERDICT_PROMPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "검수-판정기준.md"))
PRESCREEN_PROMPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "기준적격-판정기준.md"))
# 검수 판정 배치 — 건당 이미지 최대 3장(기존대표·대표옵션·생성본). 예산 24장 기준 8건.
VERDICT_BATCH_SIZE = 8

# prescreen 배치 — 건당 이미지 **1장**(대표옵션)뿐이라 audit(2장)보다 더 크게 잡는다.
# 이미지예산 24장 기준으로는 24건까지 되지만, 워커 1명이 이고 가는 양이 커질수록 변동비가
# 붙으므로(§워커 패킹 곡선) 20 에서 끊는다.
PRESCREEN_BATCH_SIZE = 20

# 승격 배치 크기 — prescreen 이 `다중혼재` 를 run 팬아웃으로 넘길 때 쓴다. 이 건들은
# 후보까지 보므로 상품당 최대 6장(대표1+후보5)이라 SKILL.md 권고대로 4건씩 끊는다.
PROMOTE_BATCH_SIZE = 4

# audit 배치 크기 — 건당 이미지 2장(대표옵션 vs 현재 대표)뿐이라 생성 배치(상품당
# 최대 6장)보다 크게 잡는다. 이미지예산 24장 기준 배치당 12건.
AUDIT_BATCH_SIZE = 12

# 워커에게 주는 이미지의 긴 변 px. 2026-08-07 실측(표본 9건·17장을 512/768/원본으로
# 만들어 블라인드 판독): 판독 성공 512=85 · 768=84 · 원본=93. **768 은 512 보다 나은 게
# 없어** 중간값을 두지 않고, 512 가 원본의 91% 를 유지하면서 비전 토큰을 3.3배 줄인다.
# (원본은 800~1024px 라 1장 850~1,400토큰 → 512 는 ~350토큰.)
MAX_PX = 512

# verdict 만 예외로 원본을 유지한다. 3축 중 `제외(글자변조)` 는 제품 각인 브랜드 글자를
# 원본↔생성본으로 **대조**하는데, 같은 실측에서 인버터 브랜드를 512 는 `讯浦`, 768 은
# `锐霸` 로 갈라 읽었다. 판독 자체는 512 로 충분해도, 이 축은 오독이 곧 거짓 재작업이라
# (재생성 2회까지 크레딧이 나간다) 여유를 남긴다.
VERDICT_MAX_PX = 0


def _px(args, default):
    """`--max-px` 값. 테스트·러너가 Namespace 를 직접 만들 때를 위한 폴백."""
    v = getattr(args, "max_px", None)
    return default if v is None else v


def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _today():
    import datetime
    return datetime.date.today().isoformat()


class ThumbMCP(snapshot.ProductMCP):
    """transport + workdata 는 상속하고, 썸네일 전용 도구만 얹는다."""

    def generate(self, product_id, prompt=None, rendering_speed="TURBO"):
        """AI 썸네일 생성 접수 — confirm 2단계(카테고리 저장과 같은 패턴).

        prompt 를 생략하면 불사자에 저장된 기본 프롬프트가 쓰인다(2026-07-28 실측 확인).
        반환: {"taskId", "expectedCredits"}.
        """
        payload = {"productId": product_id, "renderingSpeed": rendering_speed}
        if prompt:
            payload["prompt"] = prompt
        pv = self.call_tool("bulsaja_thumbnail_ai_generate", payload)
        token = pv.get("confirmationToken")
        if not token:
            raise RuntimeError(f"확인키 미발급: {str(pv.get('message'))[:200]}")
        r = self.call_tool("bulsaja_thumbnail_ai_generate",
                           {**payload, "confirm": True, "confirmationToken": token})
        if not r.get("success"):
            raise RuntimeError(f"생성 접수 실패: {str(r.get('message'))[:200]}")
        return {"taskId": r.get("taskId") or r.get("작업번호"),
                "expectedCredits": r.get("expectedCredits") or r.get("필요크레딧") or 0}

    def poll(self, task_id, interval=POLL_INTERVAL, timeout=POLL_TIMEOUT):
        """완료까지 폴링. 반환: (생성이미지[], 사용크레딧). 실패/타임아웃이면 예외.

        본체는 `ProductMCP.poll_ai_task` — 상세 스킬과 같은 도구를 쓴다(Step6에서 공용화).
        """
        return self.poll_ai_task(task_id, target="thumbnail",
                                 interval=interval, timeout=timeout)

    def task_status(self, task_id):
        """폴링 없이 **한 번만** 조회 — 회수(recover)용.

        `poll` 은 완료까지 기다리다 타임아웃이면 예외를 던진다. 회수는 "지금 됐나"만
        묻고 아니면 다음에 다시 오면 되므로 기다리지 않는다.
        반환: (완료여부, 생성이미지[], 사용크레딧, 실패내역[]).
        """
        st = self.call_tool("bulsaja_detail_page_status",
                            {"taskId": str(task_id), "target": "thumbnail"})
        return (bool(st.get("완료여부") or st.get("완료") or st.get("completed")),
                st.get("생성이미지") or st.get("imageUrls") or [],
                st.get("사용크레딧") or st.get("consumedCredits") or 0,
                st.get("실패내역") or st.get("failures") or [])

    def update_thumbnails(self, product_id, thumbnails):
        """대표이미지 확정 — confirm 2단계. thumbnails[0] 이 대표가 된다."""
        pv = self.call_tool("bulsaja_thumbnail_update",
                            {"productId": product_id, "thumbnails": thumbnails})
        token = pv.get("confirmationToken")
        if not token:
            if pv.get("success"):
                return pv
            raise RuntimeError(f"확인키 미발급: {str(pv.get('message'))[:200]}")
        r = self.call_tool("bulsaja_thumbnail_update",
                           {"productId": product_id, "thumbnails": thumbnails,
                            "confirm": True, "confirmationToken": token})
        if not r.get("success"):
            raise RuntimeError(f"저장 실패: {str(r.get('message'))[:200]}")
        return r


# ---------------------------------------------------------------------------
# prep
# ---------------------------------------------------------------------------

def _resolve_sheet(args):
    if getattr(args, "sheet", None):
        return args.sheet
    name = (getattr(args, "group_name", "") or "").strip()
    if not name:
        raise RuntimeError("--sheet 또는 --group-name 중 하나는 필요하다")
    for g, sid in matrix.index_groups():
        if g == name:
            return sid
    hits = [(g, sid) for g, sid in matrix.index_groups() if name in g]
    if len(hits) != 1:
        raise RuntimeError(f"'{name}' 으로 그룹 시트를 특정하지 못했다(후보 {len(hits)}개)")
    return hits[0][1]


def _warn_option_order(m, pids):
    """옵션 단계가 아직 안 끝난 채로 썸네일을 돌리면 낭비라는 신호만 남긴다(차단 없음).

    옵션정리가 대표옵션을 세워두면 prep 이 `대표옵션이미지경로` 있는 상품을
    `result_000` 에 선기록하고 배치에서 빼므로(규칙 0) **비전 팬아웃이 거의 사라진다.**
    거꾸로 돌리면 상품당 최대 6장(대표1+후보5)을 워커가 다 열어 고르게 된다.

    막지 않는 이유: 순서를 뒤집어야 하는 정당한 회차가 있다(재작업 flag 소진, 단일상품
    그룹). 판단은 이룸님 몫이고 여기선 비용 신호만 준다.
    """
    if not pids:
        return
    todo = set(matrix.pending(m, "옵션")) & set(pids)
    if not todo:
        return
    pct = round(len(todo) * 100 / len(pids))
    print(f"  ℹ 이번 대상 중 옵션 단계 미완료 {len(todo)}건({pct}%) — 옵션을 먼저 돌리면 "
          f"대표옵션 확정건이 배치에서 빠져 비전 팬아웃이 크게 줄어든다(진행은 계속한다)")


def cmd_prep(args):
    run_dir = os.path.abspath(args.run_dir)
    os.makedirs(run_dir, exist_ok=True)
    sheet = _resolve_sheet(args)
    print(f"  시트: {sheet}")

    m = matrix.read(sheet)
    if args.ids:
        pids = [i for i in args.ids if i.strip()]
    else:
        pids = matrix.pending(m, TASK)
        print(f"[1/4] 현황판 '{TASK}' 대상(미착수+재작업) {len(pids)}건")
    if args.limit:
        pids = pids[:args.limit]
        print(f"  --limit {args.limit} 적용 → {len(pids)}건")
    _warn_option_order(m, pids)
    if not pids:
        # 0건도 정상 완료다 — 산출물이 없으면 호출자가 'prep 실패'와 구분하지 못한다.
        _dump(os.path.join(run_dir, "batches_index.json"),
              {"대상": 0, "이유": "현황판 대상 0건"})
        print("처리할 상품이 없다.")
        return

    print(f"[2/4] 스냅샷 확보 {len(pids)}건")
    recs, errors = snapshot.ensure(pids, sleep=args.sleep)
    if errors:
        print(f"  조회 실패 {len(errors)}건: {list(errors)[:3]}")

    # 기작업 필터 — 3갈래(2026-08-05 수정지시서 §6A). "가공됨"은 "손을 댔다"이지
    # "맞게 됐다"가 아니다(실측 백필 419건 표본 30 중 불일치 19건 = 68%).
    #   가공됨 + 대표옵션 이미지 있음 → 정합검사 대상(자동 완료 금지, audit 로 넘긴다)
    #   가공됨 + 대표옵션 이미지 없음 → 완료 백필 (종전 — 대조할 근거가 없다)
    #   미가공                        → 생성 대상 (종전)
    # 단 **재작업 flag 가 있으면 절대 빼지 않는다** — 이미 가공됐다는 사실 자체가
    # 재작업 사유(예: 잘못된 색을 대표로 씀)일 수 있다. URL 판별은 "손을 아예 안 댄
    # 상품"만 걸러내려는 것이지, "이미 손댔지만 잘못됐다"를 걸러내려는 게 아니다.
    redo = matrix.redo_pending(m, TASK)
    already, targets, audit_needed = {}, [], []
    for pid in pids:
        rec = recs.get(pid)
        if not rec:
            continue
        if pid in redo:
            targets.append(pid)
            continue
        thumbs = rec.get("썸네일") or []
        if R.needs_audit(thumbs, R.main_option_of(rec.get("옵션"))):
            audit_needed.append(pid)
        elif R.is_already_done(thumbs):
            already[pid] = "완료(기존 가공 확인)"
        else:
            targets.append(pid)
    if already:
        n = matrix.mark_many(sheet, TASK, already, matrix=m)
        print(f"[3/4] 기작업 백필 {n}건(대표가 이미 cdn.bulsaja.com · 대표옵션 이미지 없음)")
    if audit_needed:
        # 현황판은 건드리지 않는다(빈칸 유지 = 대상 유지). audit 이 일치/불일치를
        # 판정할 때까지 완료도 생성 대상도 아니다.
        _dump(os.path.join(run_dir, "audit_targets.json"), audit_needed)
        print(f"  정합검사 대상 {len(audit_needed)}건(가공됨+대표옵션 있음 — 자동 완료 금지)"
              f" → audit 서브커맨드로 대조해라")
    print(f"  실제 대상 {len(targets)}건")
    if not targets:
        if errors:
            # 조회 실패로 대상이 빈 것까지 '전부 기작업' sentinel 로 남기면, 세로
            # 러너가 이 단계를 DONE 으로 기록해버린다(onestep._zero_target). 유료·
            # 자동반영 파이프라인에서 "데이터를 못 봤다"가 "볼 필요 없었다"로
            # 둔갑하는 셈이라, sentinel 을 아예 안 남기고 예전처럼 prep_out 산출물
            # 누락으로 러너가 멈추게(fail-closed) 둔다.
            print(f"  실제 대상 0건이지만 조회 실패 {len(errors)}건이 섞여 있다 — "
                  f"'전부 기작업'으로 기록하지 않고 산출물 없이 중단한다.")
            return
        if audit_needed:
            # 정합검사 미완 건이 남아 있다 — sentinel 을 남기면 러너가 이 단계를 DONE
            # 으로 기록한다. "검사 안 한 것"이 "볼 필요 없었던 것"으로 둔갑하는 게
            # 이번 사고의 본질이라, 여기서도 fail-closed(산출물 없이 중단)로 둔다.
            print(f"  실제 대상 0건이지만 정합검사 대상 {len(audit_needed)}건이 남아 있다 — "
                  f"audit 완료 전에는 '전부 기작업'으로 기록하지 않는다.")
            return
        # 산출물을 안 남기면 onestep(세로 러너)의 prep 산출물 확인이 실패로 본다
        # ("exit 0 이어도 대상 0건은 정상"이라는 규칙과 별개로, 파일 자체가 없으면
        # 구분을 못 한다). 대상 0건도 **정상 완료**임을 알 수 있게 인덱스를 남긴다.
        # (빈 배열 `[]`은 2바이트라 "산출물 없음" 크기 검사(<3바이트)에 걸리므로 dict로 쓴다.)
        _dump(os.path.join(run_dir, "batches_index.json"),
              {"대상": 0, "이유": "전부 기작업(대표가 이미 cdn.bulsaja.com)"})
        print("실제 생성이 필요한 상품이 없다(전부 기작업).")
        return

    thumbs_dir = os.path.join(run_dir, "thumbs")
    # 대표옵션 이미지의 idx — 후보(1..max_candidates)와 겹치지 않는 자리를 쓴다.
    main_idx = max(9, int(getattr(args, "max_candidates", MAX_CANDIDATES) or 0) + 1)
    products = []
    dead = {}    # 대표 원본이 404 = 타오바오에서 이미지가 내려감 → 삭제 대상(이룸님 판단 대기)
    for pid in targets:
        rec = recs[pid]
        why = matrix.redo_pending(m, TASK).get(pid, "")
        thumbs = rec.get("썸네일") or []
        rep_path = ""
        if thumbs:
            p, err = snapshot.materialize_image(thumbs[0], thumbs_dir, pid + "_rep", 0,
                                               max_px=_px(args, MAX_PX))
            rep_path = p or ""
            # 원본 404 = 소싱 원본 이미지가 내려갔다는 신호 — 썸네일을 새로 만들 대상이
            # 아니라 **삭제 대상**으로 기재한다(2026-08-01 이룸님). 워커에 보내지 않는다.
            if not p and "404" in str(err or ""):
                dead[pid] = rec.get("상품명", "")
                continue
        cand_paths = []
        for i, url in enumerate(thumbs[1:1 + args.max_candidates], 1):
            p, _ = snapshot.materialize_image(url, thumbs_dir, pid + "_cand", i,
                                           max_px=_px(args, MAX_PX))
            if p:
                cand_paths.append({"index": i, "url": url, "path": p})
        # 대표옵션 — 있으면 **이게 기준 이미지다**(Claude 가 후보 중에서 고르지 않는다).
        # 네이버는 '대표상품'(추가금 0원 옵션)을 상품명으로 쓰라고 요구하므로
        # 썸네일=대표옵션=상품명이 한 옵션을 지칭해야 한다(2026-07-30 이룸님).
        # None = 옵션정리 미완료(대표 미지정) 또는 옵션 없는 단일상품 → 종전 비전 판단.
        mo = R.main_option_of(rec.get("옵션"))
        mo_path = ""
        if mo and mo.get("이미지"):
            # **구분은 name_hint 가 아니라 idx 로 한다** — `materialize_image` 가
            # name_hint 를 24자로 자르는데 상품id 가 27자라 `_rep`·`_main` 접미사가
            # 통째로 잘려나간다. 확장자까지 같으면 대표이미지와 대표옵션이미지가
            # **같은 파일**이 되어 워커가 엉뚱한 이미지로 비전 판단을 내린다
            # (audit 쪽 같은 결함을 2026-08-06 에 고쳤는데 prep 에 남아 있었다).
            p, _ = snapshot.materialize_image(mo["이미지"], thumbs_dir, pid, main_idx,
                                           max_px=_px(args, MAX_PX))
            mo_path = p or ""
            if mo_path and mo_path == rep_path:
                # 방어선 — 규칙이 깨지면 조용히 뒤바뀌는 대신 여기서 드러난다.
                print(f"  [경고] {pid}: 대표이미지·대표옵션이미지 경로 충돌 — "
                      f"대표옵션 이미지를 비운다({os.path.basename(mo_path)})",
                      file=sys.stderr)
                mo_path = ""
        products.append({
            "productId": pid,
            "상품명": rec.get("상품명", ""),
            "재작업사유": R.redo_reason_from_flag(why) if why else "",
            "기존썸네일": thumbs,
            "대표이미지": rep_path,
            "후보이미지": cand_paths,
            "대표옵션명": (mo or {}).get("이름", ""),
            "대표옵션이미지": (mo or {}).get("이미지", ""),
            "대표옵션이미지경로": mo_path,
        })

    # 원본 404 삭제 대상 — 파일·현황판에 기재하고 이룸님께 보고한다. 현황판 값이
    # 보류라 pending 에서 자동으로 빠진다(재작업 루프 차단). 실제 삭제는 이룸님 몫.
    if dead:
        _dump(os.path.join(run_dir, "deletion_candidates.json"), dead)
        try:
            matrix.mark_many(sheet, TASK,
                             {pid: "보류(원본404·삭제대상)" for pid in dead}, matrix=m)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 삭제대상 현황판 기재 실패: {str(e)[:120]}", file=sys.stderr)
        print(f"\n  ★★ 삭제 대상 {len(dead)}건 — 타오바오 원본 이미지 404 ★★")
        for pid, name in dead.items():
            print(f"    {pid}  {name[:40]}")
        print(f"    기록: {os.path.join(run_dir, 'deletion_candidates.json')} + 현황판 '{TASK}' 열")
    if not products:
        _dump(os.path.join(run_dir, "batches_index.json"),
              {"대상": 0, "이유": f"원본404 삭제대상 {len(dead)}건 기재" if dead
               else "대상 0건"})
        print("생성 대상이 없다.")
        return

    # 확정건 선기록 — 대표옵션이미지경로가 있으면 규칙 0("고르지 않는다")이라 판단이 0이다.
    # prep 이 직접 results/result_000.json 에 기록하고 배치에서 뺀다 → 워커 비용이 정확히
    # 0장이 되고, 워커 환각이 이 건들의 pass-through 필드를 훼손할 표면 자체가 사라진다.
    # **왕복 종결** (2026-08-07 이룸님) — 옵션이 `실물기준없음` 으로 되돌린 건은 대표옵션
    # 이미지가 있어도 선기록하지 않는다. 선기록하면 `prescreen` 이 또 `실물없음` 을 내
    # 옵션으로 되돌리고, 옵션엔 실물 옵션이 없으니 또 되돌아온다 — 무한 왕복이다.
    # 여기서 비전 배치로 보내 **썸네일 워커가 후보에서 고르게** 한다(왕복 1회로 끝).
    sent_back = {p["productId"] for p in products
                 if R.no_real_base(p.get("재작업사유"))}
    fixed = [p for p in products
             if p.get("대표옵션이미지경로") and p["productId"] not in sent_back]
    fixed_pids = {p["productId"] for p in fixed}
    vision = [p for p in products if p["productId"] not in fixed_pids]
    if sent_back:
        # **규칙 0 트리거까지 떼어내야 왕복이 진짜로 닫힌다** (2026-08-17 용쌤2-1 실측).
        # 비전 배치로 보내기만 하고 `대표옵션이미지경로` 를 남겨두면 배치가 **모순된 지시**
        # 를 담는다 — 워커 프롬프트 규칙 0 이 "그 경로가 있으면 그게 기준이다, 고르지
        # 마라"이기 때문이다. 실측 3건 전부 워커가 규칙 0 을 따라 대표옵션(idx 9)을 도로
        # 집었고, 그 index 는 후보에도 기존썸네일 범위에도 없어 URL 해석이 실패해
        # **맹목 배경교체**로 떨어졌다(크레딧은 나가고 기준은 한 글자도 안 바뀐다).
        # 워커 잘못이 아니다 — 배치가 시킨 대로 한 것이다.
        #
        # `대표옵션명` 은 남긴다. 후보에서 "그 옵션과 같은 물건"을 고르려면 이름이 필요하고,
        # 이름은 규칙 0 을 발동시키지 않는다.
        for p in products:
            if p["productId"] in sent_back:
                p["대표옵션이미지경로"] = ""
                p["대표옵션이미지"] = ""
        print(f"  옵션 되돌림({R.NO_REAL_BASE}) {len(sent_back)}건 — 선기록 대신 "
              f"비전 배치로 보낸다(왕복 종결 · 대표옵션 기준 제거)")
    if fixed:
        _dump(os.path.join(run_dir, "results", "result_000.json"),
              {"배치": 0, "선기록": True,
               "products": [{**p, "기준이미지경로": p["대표옵션이미지경로"],
                             "모드": "기본"} for p in fixed]})

    batches = [vision[i:i + args.batch_size]
               for i in range(0, len(vision), args.batch_size)]
    index = []
    for i, b in enumerate(batches, 1):
        path = os.path.abspath(os.path.join(run_dir, "batches", f"batch_{i:03d}.json"))
        _dump(path, {"배치": i, "규칙문서": RULES_DOC, "products": b})
        # imgs = 워커가 열 수 있는 이미지 상한(대표 1 + 후보 ≤5) — 팬아웃 빈패킹의 예산 축.
        index.append({"n": i, "path": path,
                      "imgs": sum((1 if p.get("대표이미지") else 0)
                                  + len(p.get("후보이미지") or []) for p in b),
                      "count": len(b)})
    if index:
        _dump(os.path.join(run_dir, "batches_index.json"), index)
    else:
        # 전건 확정 선기록 — 배치가 0개여도 prep 은 정상 완료다. sentinel(`대상`)과
        # 다른 dict 를 남긴다(러너 _zero_target 은 `대상` 키만 sentinel 로 본다).
        _dump(os.path.join(run_dir, "batches_index.json"),
              {"배치": 0, "확정선기록": len(fixed)})
    print(f"\n###PREP### 배치 {len(batches)}개 / 대상 {len(products)}건")
    # 기준 이미지가 정해진 건 vs 비전 판단으로 골라야 하는 건을 미리 알린다
    print(f"  대표옵션 확정 선기록 {len(fixed)}건 / 비전 판단 {len(vision)}건"
          f"(옵션정리 미완료·단일상품)")
    print(f"  배치: {os.path.join(run_dir, 'batches')}")
    if index:
        print(f"  다음(Workflow 모드): python {os.path.basename(__file__)} pending "
              f"--run-dir <R> → thumb-fanout 호출 → apply")
    print("  다음(수동 폴백): Claude 가 배치를 읽고 기준이미지·모드·(레시피면)프롬프트를 "
          "정해 results/result_NNN.json 생성 → apply")


def _pending_batches(run_dir):
    """results/result_NNN.json 이 없는 배치 = 아직 안 된 것. 디스크가 정본이다.

    index 가 dict(sentinel·전건 선기록)이면 남은 배치가 없다.
    """
    idx_path = os.path.join(run_dir, "batches_index.json")
    if not os.path.exists(idx_path):
        return []
    index = _load(idx_path)
    if isinstance(index, dict):
        return []
    out = []
    for b in index:
        if "n" not in b:
            # 구형 index(파일명·상품수만) 폴백 — 배치 파일에서 재계산한다.
            n = int(str(b.get("batch", "")).replace("batch_", "").replace(".json", "") or 0)
            path = os.path.abspath(os.path.join(run_dir, "batches", b.get("batch", "")))
            prods = _load(path).get("products", []) if os.path.exists(path) else []
            b = {"n": n, "path": path,
                 "imgs": sum((1 if p.get("대표이미지") else 0)
                             + len(p.get("후보이미지") or []) for p in prods),
                 "count": len(prods)}
        if not os.path.exists(os.path.join(
                run_dir, "results", f"result_{b['n']:03d}.json")):
            out.append(b)
    return out


def _pending_audit_batches(run_dir):
    """audit_result 가 아직 없는 audit 배치 — [{n, path, imgs, count}]."""
    index = _load(os.path.join(run_dir, "audit_batches_index.json")) \
        if os.path.exists(os.path.join(run_dir, "audit_batches_index.json")) else []
    if not isinstance(index, list):        # {"대상": 0, ...} = 대조 가능 0건
        return []
    out = []
    for b in index:
        # 배치 0(대조불가 선기록)은 index 에 없다 — 여기 오는 건 판정 대상뿐.
        if not os.path.exists(os.path.join(
                run_dir, "audit_results", f"audit_result_{b['n']:03d}.json")):
            out.append(b)
    return out


def _pending_prescreen_batches(run_dir):
    """presult 가 아직 없는 prescreen 배치 — [{n, path, imgs, count}]."""
    idx = os.path.join(run_dir, "prescreen_batches_index.json")
    index = _load(idx) if os.path.exists(idx) else []
    if not isinstance(index, list):        # {"대상": 0, ...} = 선기록 0건
        return []
    return [b for b in index
            if not os.path.exists(os.path.join(
                run_dir, "prescreen_results", f"presult_{b['n']:03d}.json"))]


def cmd_pending(args):
    """남은 배치를 JSON 한 줄로 찍는다 — Workflow(thumb-fanout) args 에 그대로 넣는다.

    `--audit` = 정합검사 배치(audit_batches/) 기준. 생성 팬아웃과 결과 폴더가 달라
    (results/ vs audit_results/) **두 팬아웃을 같은 run-dir 에서 병렬로 돌려도 안전**하다.
    """
    run_dir = os.path.abspath(args.run_dir)
    if getattr(args, "prescreen", False):
        print(json.dumps({"runDir": run_dir, "promptPath": PRESCREEN_PROMPT,
                          "mode": "prescreen",
                          "batches": _pending_prescreen_batches(run_dir)},
                         ensure_ascii=False))
        return
    if getattr(args, "audit", False):
        print(json.dumps({"runDir": run_dir, "promptPath": AUDIT_PROMPT,
                          "mode": "audit",
                          "batches": _pending_audit_batches(run_dir)},
                         ensure_ascii=False))
        return
    if getattr(args, "verdict", False):
        print(json.dumps({"runDir": run_dir, "promptPath": VERDICT_PROMPT,
                          "mode": "verdict",
                          "batches": _pending_verdict_batches(run_dir)},
                         ensure_ascii=False))
        return
    print(json.dumps({"runDir": run_dir, "promptPath": WORKER_PROMPT,
                      "batches": _pending_batches(run_dir)}, ensure_ascii=False))


# ---------------------------------------------------------------------------
# prescreen — 기준이미지 적격성 (크레딧 0 · 조회 0, 2026-08-07)
# ---------------------------------------------------------------------------

def _prerecorded(run_dir):
    """prep 이 선기록한 건 — (doc, [products]). 없으면 (None, [])."""
    path = os.path.join(run_dir, "results", "result_000.json")
    if not os.path.exists(path):
        return None, []
    doc = _load(path)
    if not doc.get("선기록"):
        return None, []
    return doc, doc.get("products", [])


def cmd_prescreen(args):
    """기준이미지 적격성 검사 — **생성 전에** 돈다. 크레딧 0 · 불사자 조회 0.

    **왜 있나** (2026-08-07 실측): `prep` 은 `대표옵션이미지경로` 가 있으면 비전 판단 없이
    그걸 기준이미지로 확정한다(`규칙 0` 선기록 — 워커 비용 0). 3-2 그룹은 73건 중 **57건
    (78%)** 이 이 경로로 나갔고, 그 대표옵션을 표본 12건 열어보니 **9건이 도면·배너**였다.
    `배경생성-기본.md §1-1`(비제품이면 실물 후보로 갈아끼운다)은 팬아웃을 탄 건에만
    적용되므로 **선기록건은 아무도 안 본 채로 태워졌다.**

    실증 — `갈매기 식탁펜던트조명`: 기준이 `A款/B款/C款` 세 형태가 한 장에 있는 이미지였고,
    검수에서 Sonnet 과 Haiku 가 서로 다르게 오독해 사유 오분류로 남았다. 무엇을 그릴지
    정해지지 않은 기준은 생성도 판정도 갈린다.
    실측(3-2 그룹 57건): 다중혼재 **6건(10.5%)** · 수기 라벨 12건과 12/12 일치 · 놓침 0.

    **묻는 것은 "도면이냐"가 아니라 "제품이 하나로 특정되나"다** — 치수 도면을 기준으로
    태운 3건(그릇진열장·신발장·핀조명)은 전부 깨끗하게 생성됐다. 사고는 여러 제품·변형이
    한 장에 있을 때 났다.

    이미지는 prep 이 이미 디스크에 받아뒀다(`기준이미지경로`) — 다시 받지 않는다.
    """
    run_dir = os.path.abspath(args.run_dir)
    os.makedirs(run_dir, exist_ok=True)
    # 시트는 `--commit` 에서만 필요하다 — 배치 준비는 디스크만 읽으므로 **조회 0** 이다.
    # (정확도 대조를 시트 접근 없이 돌릴 수 있어야 한다 — 검증 ①)
    if args.commit:
        sheet = _resolve_sheet(args)
        print(f"  시트: {sheet}")
        _prescreen_commit(sheet, run_dir)
        return

    doc, products = _prerecorded(run_dir)
    if doc is None:
        # 조용히 0건으로 끝내면 "검사했는데 깨끗하다"로 읽힌다 — 오사용을 드러낸다.
        print(f"[중단] 선기록이 없다: {os.path.join(run_dir, 'results', 'result_000.json')}\n"
              "  prep 을 먼저 돌리거나, 이 run-dir 은 전건이 비전 판단(팬아웃)이라\n"
              "  prescreen 대상이 아니다 — 그 경우 run 워커가 §1-1 을 이미 적용한다.",
              file=sys.stderr)
        sys.exit(2)

    items, missing = [], []
    for p in products:
        pid = p.get("productId")
        ref = p.get("기준이미지경로") or ""
        if not pid:
            continue
        if not ref or not os.path.exists(ref):
            # 파일이 없으면 판정할 게 없다 — fail-closed 로 승격 후보에 넣는다.
            missing.append(pid)
            continue
        items.append({"productId": pid, "상품명": p.get("상품명", ""),
                      "대표옵션명": p.get("대표옵션명", ""),
                      "기준이미지경로": ref,
                      "후보수": len(p.get("후보이미지") or [])})
    if missing:
        _dump(os.path.join(run_dir, "prescreen_results", "presult_000.json"),
              {"배치": 0, "선기록": True,
               "products": [{"productId": pid, "판정": R.PRE_MIXED,
                             "사유": "기준이미지 파일 없음 — 판정 불가(fail-closed)"}
                            for pid in missing]})
        print(f"  기준이미지 파일 없음 {len(missing)}건 → 승격 선기록")
    print(f"[1/2] 선기록 {len(products)}건 중 판정 대상 {len(items)}건")

    batches = [items[i:i + args.batch_size]
               for i in range(0, len(items), args.batch_size)]
    index = []
    for i, b in enumerate(batches, 1):
        path = os.path.abspath(os.path.join(
            run_dir, "prescreen_batches", f"pbatch_{i:03d}.json"))
        _dump(path, {"배치": i, "판정기준": PRESCREEN_PROMPT, "products": b})
        # 건당 이미지 1장(기준이미지) — 팬아웃 빈패킹의 예산 축.
        index.append({"n": i, "path": path, "imgs": len(b), "count": len(b)})
    _dump(os.path.join(run_dir, "prescreen_batches_index.json"),
          index if index else {"대상": 0, "이유": "판정 대상 0건"})
    print(f"\n###PRESCREEN-PREP### 배치 {len(batches)}개 / 판정 {len(items)}건")
    if index:
        print(f"  배치: {os.path.join(run_dir, 'prescreen_batches')}")
        print("  다음(대량): pending --prescreen → Workflow thumb-fanout(mode:prescreen) "
              "→ prescreen --commit")
        print(f"  다음(소량): 판정기준({os.path.basename(PRESCREEN_PROMPT)})대로 Claude 가 "
              "직접 prescreen_results/presult_NNN.json 작성 → prescreen --commit")


def _next_batch_no(run_dir):
    """batches/ 에 있는 배치 번호의 다음 값. 없으면 1."""
    nos = []
    for bf in glob.glob(os.path.join(run_dir, "batches", "batch_*.json")):
        stem = os.path.basename(bf)[len("batch_"):-len(".json")]
        if stem.isdigit():
            nos.append(int(stem))
    return (max(nos) + 1) if nos else 1


def _prescreen_commit(sheet, run_dir):
    """판정을 반영한다 — 현황판이 아니라 **배치와 선기록**을 고치는 게 주 작업이다.

      단일특정 → 그대로 둔다(`result_000` 유지 → 그대로 생성)
      다중혼재 → 선기록에서 빼고 `batches/` 로 승격 → 기존 run 팬아웃이 후보에서 고른다
      실물없음 → 선기록에서 빼고 현황판 `보류(기준이미지없음)`

    **멱등하다** — 이미 승격·보류된 pid 는 `result_000` 에 없으므로 두 번째 호출이
    아무것도 하지 않는다.
    """
    doc, products = _prerecorded(run_dir)
    if doc is None:
        print(f"선기록이 없다: {os.path.join(run_dir, 'results', 'result_000.json')}")
        return
    judged = []
    for rf in sorted(glob.glob(os.path.join(run_dir, "prescreen_results",
                                            "presult_*.json"))):
        judged += _load(rf).get("products", [])
    if not judged:
        print(f"prescreen_results 가 없다: {os.path.join(run_dir, 'prescreen_results')}")
        return
    # 잘린 id 는 선기록(by_pid)에 없어서 승격·보류 어디에도 안 걸리고 `미판정` 으로
    # 흘러간다 = 기준적격 검사를 건너뛴 채 생성된다. 되살린 뒤 분류한다.
    _heal_pids(judged, _index_pids(run_dir, "prescreen_batches_index.json"), "기준적격")
    mixed, noproduct, single = R.prescreen_partition(judged)

    by_pid = {p["productId"]: p for p in products if p.get("productId")}
    already = set(_batch_products(run_dir))       # 이전 회차에 이미 승격된 것
    # 선기록에 남아 있는 것만 처리한다 — 이게 멱등성의 근거다.
    to_promote = [by_pid[pid] for pid in mixed
                  if pid in by_pid and pid not in already]
    to_hold = {pid: why for pid, why in noproduct.items() if pid in by_pid}
    unjudged = [pid for pid in by_pid
                if pid not in mixed and pid not in noproduct and pid not in set(single)]

    # ① 승격 — 판단 필드는 떼고 넘긴다. batches/ 가 pass-through 필드의 정본이라
    #    (`_batch_products`) prep 이 만든 배치와 같은 모양이어야 한다.
    new_index = []
    if to_promote:
        stripped = [{k: v for k, v in p.items() if k not in _JUDGE_FIELDS}
                    for p in to_promote]
        start = _next_batch_no(run_dir)
        chunks = [stripped[i:i + PROMOTE_BATCH_SIZE]
                  for i in range(0, len(stripped), PROMOTE_BATCH_SIZE)]
        for j, b in enumerate(chunks):
            n = start + j
            path = os.path.abspath(os.path.join(
                run_dir, "batches", f"batch_{n:03d}.json"))
            _dump(path, {"배치": n, "규칙문서": RULES_DOC, "products": b})
            new_index.append({"n": n, "path": path,
                              "imgs": sum((1 if p.get("대표이미지") else 0)
                                          + len(p.get("후보이미지") or []) for p in b),
                              "count": len(b)})
        # batches_index 는 **전건 선기록이면 dict** 로 저장돼 있다(prep `확정선기록`).
        # `_pending_batches` 가 dict 를 보면 빈 배열을 돌려주므로 list 로 갈아끼워야
        # 승격분이 `pending` 에 잡힌다.
        idx_path = os.path.join(run_dir, "batches_index.json")
        old = _load(idx_path) if os.path.exists(idx_path) else []
        _dump(idx_path, (old if isinstance(old, list) else []) + new_index)

    # ② 선기록 재작성 — 승격·보류분을 뺀다. 미판정은 남긴다(종전 동작 = 그대로 생성).
    drop = {p["productId"] for p in to_promote} | set(to_hold)
    if drop:
        _dump(os.path.join(run_dir, "results", "result_000.json"),
              {**doc, "products": [p for p in products
                                   if p.get("productId") not in drop]})

    # ③ 실물없음 — **뿌리가 옵션이다.** 대표옵션 이미지가 비제품이면 썸네일을 아무리 다시
    #    태워도 같은 기준을 다시 쓰는 것이라 교정이 아니다. 대표옵션을 **실물 사진이 있는
    #    값으로 다시 세워야** 풀린다(2026-08-07 이룸님 — `R.TO_OPTION_VERDICTS` 와 같은 규칙,
    #    verdict 의 `제외(기준이미지없음)` 처리와 한 몸이다).
    #    썸네일 열은 보류로 세우고 **옵션 열에 재작업 flag** 를 찍는다 — flag 를 빼먹으면
    #    `보류(...)` 가 `matrix.pending()`(빈칸+재작업)에 안 잡혀 **영구 정지**한다.
    n_hold = n_flag = 0
    if to_hold:
        m = matrix.read(sheet)
        live = {pid: why for pid, why in to_hold.items()
                if pid in m and (m[pid].get(TASK) or "").strip() != matrix.NA}
        vals = {pid: f"보류({R.VERDICT_NO_BASE})" for pid in live}
        n_hold = matrix.mark_many(sheet, TASK, vals, matrix=m) if vals else 0
        n_flag = matrix.flag_many(
            sheet, "옵션",
            {pid: _to_option_reason(
                R.VERDICT_NO_BASE,
                why or "대표옵션 이미지가 비제품(도면·배너) — 실물 사진이 있는 "
                       "값으로 대표를 다시 세울 것")
             for pid, why in live.items()},
            from_task=TASK, matrix=m) if live else 0
        _dump(os.path.join(run_dir, "prescreen_held.json"), to_hold)

    print(f"\n###PRESCREEN### 단일특정 {len(single)}건(그대로 생성) "
          f"/ 다중혼재 {len(to_promote)}건(run 팬아웃 승격) "
          f"/ 실물없음 {len(to_hold)}건(보류)")
    if new_index:
        print(f"  승격 배치 {len(new_index)}개 → {os.path.join(run_dir, 'batches')}")
        print("  다음: pending → Workflow thumb-fanout → apply --generate")
    if n_hold:
        print(f"  현황판({matrix.TAB}) {TASK}: {n_hold}칸 보류({R.VERDICT_NO_BASE}) "
              f"/ 옵션 열 재작업 flag {n_flag}칸 — 옵션정리가 대표를 실물로 다시 세우고 "
              f"이관(썸네일)을 되찍으면 재진입한다. 목록: "
              f"{os.path.join(run_dir, 'prescreen_held.json')}")
    if unjudged:
        print(f"  ⚠ 미판정 {len(unjudged)}건 — 팬아웃이 안 끝났다. 이 건들은 종전대로 "
              f"그대로 생성된다.\n"
              f"    끝내려면: pending --prescreen 으로 남은 배치를 확인해 다시 팬아웃 "
              f"→ prescreen --commit")


# ---------------------------------------------------------------------------
# audit — 기존 대표가 대표옵션과 같은 물건인지 대조 (크레딧 0, 2026-08-05 수정지시서 §6B)
# ---------------------------------------------------------------------------

def cmd_audit(args):
    """정합검사 — 생성과 성격이 다르다: 크레딧 0, 이미지 2장/건, 결과는 판정뿐.

    기본 호출은 배치 준비까지. 판정은 비전(Claude 또는 팬아웃 워커)이
    `audit_results/audit_result_NNN.json` 으로 쓰고, `--commit` 이 현황판에 반영한다:
      불일치  → `재작업(정합검사: 사유)` — 다음 prep 이 자동으로 다시 집어간다
      일치    → `완료(정합확인)`
      대조불가 → **flag 하지 않는다**(무한 재작업 루프 방지) — 집계만
    """
    run_dir = os.path.abspath(args.run_dir)
    os.makedirs(run_dir, exist_ok=True)
    sheet = _resolve_sheet(args)
    print(f"  시트: {sheet}")
    if args.commit:
        _audit_commit(sheet, run_dir)
        return

    # 대상 = **prep 이 넘긴 정합검사 대상(`audit_targets.json`)이 기본**이다.
    # 현황판 `완료*` 전건은 `--sweep` 을 명시할 때만 (2026-08-06 이룸님).
    #
    # 정합검사는 스킬에 audit 이 없던 시절 산물(1-1·1-2·1-3 등)을 **소급** 감사하려고
    # 만든 것이다. 지금은 ①prep 이 `가공됨+대표옵션` 을 매 회차 `audit_targets.json` 으로
    # 자동 편입하고 ②새로 생성한 건은 `verdict` ①제품 정확성 축이 대표옵션과 같은 대조를
    # 이미 한다. 그래서 완료* 전건 재대조는 **중복**이고, 같은 이미지 쌍을 또 판정하면
    # 판정이 흔들려 멀쩡한 상품에 `재작업(정합검사: …)` 이 다시 붙는다 — 회차를 넘나드는
    # 순환이 된다(같은 회차 안 무한루프만 '1회 한정' 규칙으로 막혀 있었다).
    explicit = getattr(args, "targets", None)
    extra_path = os.path.abspath(explicit) if explicit \
        else os.path.join(run_dir, "audit_targets.json")
    if explicit and not os.path.exists(extra_path):
        raise SystemExit(f"[중단] --targets 파일이 없다: {extra_path}")
    pids, has_targets = [], os.path.exists(extra_path)
    if has_targets:
        pids = list(_load(extra_path) or [])
        print(f"  정합검사 대상 {len(pids)}건 ← {extra_path}")
    sweep = bool(getattr(args, "sweep", False))
    if sweep:
        # 소급 감사 — 과거 그룹은 **`--sample 30` 으로 불량률부터 재는 게 싸다.**
        m = matrix.read(sheet)
        seen = set(pids)
        add = [pid for pid, rec in m.items()
               if (rec.get(TASK) or "").strip().startswith("완료") and pid not in seen]
        pids += add
        print(f"  --sweep: 현황판 완료* {len(add)}건 추가(소급 감사)")
    if not pids and not has_targets and not sweep:
        # 조용히 0건으로 끝내면 "감사했는데 깨끗하다"로 읽힌다 — 오사용을 드러낸다(§6-G).
        print("[중단] 대상이 없다 — audit_targets.json 도 없고 --sweep 도 없다.\n"
              "  · prep 을 다른 run-dir 로 돌렸으면  --targets <그쪽 경로>\n"
              "  · 과거 그룹 소급 감사면            --sweep [--sample 30]",
              file=sys.stderr)
        sys.exit(2)
    print(f"[1/3] 감사 후보 {len(pids)}건"
          f"({'prep 대상' if has_targets else '—'}{' + 완료* 소급' if sweep else ''})")
    if not pids:
        print("감사할 상품이 없다.")
        return

    recs, errors = snapshot.ensure(pids, sleep=args.sleep)
    if errors:
        print(f"  조회 실패 {len(errors)}건: {list(errors)[:3]}")
    rows = []
    for pid in pids:
        rec = recs.get(pid)
        if not rec:
            continue
        mo = R.main_option_of(rec.get("옵션"))
        thumbs = rec.get("썸네일") or []
        # 대표옵션 이미지가 없으면 대조할 근거가 없다 — 감사 대상이 아니다.
        if not (mo and mo.get("이미지")) or not thumbs:
            continue
        rows.append((pid, rec, mo))
    print(f"[2/3] 대조 가능 {len(rows)}건(대표옵션 이미지 있음)")

    # 표본 모드 — 전건 감사 전에 불량률부터 재는 게 싸다. 상품id 정렬 후 균등 간격
    # N건(재현 가능 — 2026-08-05 수기 표본 감사와 같은 방법).
    rows.sort(key=lambda t: t[0])
    if args.sample and rows:
        n = min(args.sample, len(rows))
        step = len(rows) / n
        rows = [rows[int(i * step)] for i in range(n)]
        print(f"  --sample {args.sample} 적용 → {len(rows)}건(균등 간격)")
    if args.limit:
        rows = rows[:args.limit]
        print(f"  --limit {args.limit} 적용 → {len(rows)}건")

    thumbs_dir = os.path.join(run_dir, "audit_thumbs")
    items, uncomparable, delete404 = [], {}, {}
    for pid, rec, mo in rows:
        cur_url = (rec.get("썸네일") or [""])[0]
        # **구분은 name_hint 가 아니라 idx 로 한다** — `materialize_image` 가 name_hint 를
        # 24자로 자르는데 상품id 가 27자라 `_main`·`_cur` 접미사가 통째로 잘려나간다.
        # 두 이미지의 확장자까지 같으면 같은 파일에 덮어써져 워커가 한 장만 보게 되고,
        # 그 결과가 '대조불가'로 집계됐다(2026-08-06 실측 3건).
        mo_path, mo_err = snapshot.materialize_image(mo["이미지"], thumbs_dir, pid, 0,
                                                     max_px=_px(args, MAX_PX))
        cur_path, cur_err = snapshot.materialize_image(cur_url, thumbs_dir, pid, 1,
                                                       max_px=_px(args, MAX_PX))
        if not mo_path and "404" in str(mo_err or ""):
            # 대표옵션 이미지 404 = 소싱 원본 소멸 신호 → **자동 삭제 대상**(2026-08-06
            # 이룸님 — 대표 원본 404 삭제 정책과 같은 근거). 대조불가로 뭉치지 않는다.
            delete404[pid] = {"상품명": rec.get("상품명", ""),
                              "대표옵션": mo.get("이름", ""),
                              "사유": f"대표옵션 이미지 404: {str(mo_err)[:100]}"}
            continue
        if not mo_path or not cur_path:
            # 그 외 이미지 확보 실패 = 대조불가 — 판정 없이 선기록으로 집계만 한다.
            uncomparable[pid] = f"이미지 확보 실패: {(mo_err or cur_err or '')}"[:150]
            continue
        if mo_path == cur_path:
            # 방어선 — 위 규칙이 깨지면 조용히 '대조불가'가 되는 대신 여기서 드러난다.
            uncomparable[pid] = "이미지 경로 충돌(대표옵션·현재대표가 같은 파일)"
            continue
        items.append({"productId": pid, "상품명": rec.get("상품명", ""),
                      "대표옵션명": mo.get("이름", ""),
                      "대표옵션이미지경로": mo_path,
                      "현재대표": cur_url, "현재대표경로": cur_path})
    if uncomparable:
        _dump(os.path.join(run_dir, "audit_results", "audit_result_000.json"),
              {"배치": 0, "선기록": True,
               "products": [{"productId": pid, "판정": R.AUDIT_UNCOMPARABLE, "사유": why}
                            for pid, why in uncomparable.items()]})
        print(f"  대조불가 선기록 {len(uncomparable)}건(이미지 확보 실패)")
    if delete404:
        _dump(os.path.join(run_dir, "audit_delete_404.json"), delete404)
        # 현황판에도 보류로 찍는다 — prep 의 원본404 처리와 대칭(2026-08-16).
        # 안 찍으면 값이 빈칸으로 남아 **다음 prep 이 도로 집어가고** audit 이 또
        # 같은 상품을 404 삭제 대상으로 분류한다(실측: 25-2 후속 회차에서 5건 재등장,
        # 이중 삭제 직전까지 갔다). 보류값이면 pending 에서 빠져 루프가 끊긴다.
        try:
            matrix.mark_many(sheet, TASK,
                             {pid: "보류(대표옵션404·삭제대상)" for pid in delete404})
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 삭제대상 현황판 기재 실패: {str(e)[:120]}", file=sys.stderr)
        print(f"  ★ 대표옵션 404 삭제 대상 {len(delete404)}건 → audit_delete_404.json"
              f" + 현황판 '{TASK}' 보류")
        for pid, info in delete404.items():
            print(f"    {pid}  {(info.get('상품명') or '')[:40]}")
        print(f"    다음: 메인이 bulsaja_market_delete(scope ALL, MARKET_AND_SOURCE, "
              f"확인키 2단계)로 자동 삭제(2026-08-06 이룸님 — 휴지통 복구 가능) → "
              f"**삭제 뒤 `mark-deleted --run-dir <R>` 로 해당없음 확정** + 종합보고 목록")

    batches = [items[i:i + args.batch_size]
               for i in range(0, len(items), args.batch_size)]
    index = []
    for i, b in enumerate(batches, 1):
        path = os.path.abspath(os.path.join(
            run_dir, "audit_batches", f"audit_batch_{i:03d}.json"))
        _dump(path, {"배치": i, "판정기준": AUDIT_PROMPT, "products": b})
        index.append({"n": i, "path": path, "imgs": len(b) * 2, "count": len(b)})
    _dump(os.path.join(run_dir, "audit_batches_index.json"),
          index if index else {"대상": 0, "이유": "대조 가능 0건"})
    print(f"\n###AUDIT-PREP### 배치 {len(batches)}개 / 대조 {len(items)}건 "
          f"/ 대조불가 {len(uncomparable)}건")
    if index:
        print(f"  배치: {os.path.join(run_dir, 'audit_batches')}")
        print(f"  다음(대량): pending --audit → Workflow thumb-fanout(mode:audit) 팬아웃 "
              f"→ audit --commit")
        print(f"  다음(소량): 판정기준({os.path.basename(AUDIT_PROMPT)})대로 Claude 가 직접 "
              f"audit_results/audit_result_NNN.json 작성 → audit --commit")


def _audit_commit(sheet, run_dir):
    """audit 판정 결과를 현황판에 반영한다 — 열 통짜 1회."""
    products = []
    for rf in sorted(glob.glob(os.path.join(run_dir, "audit_results",
                                            "audit_result_*.json"))):
        products += _load(rf).get("products", [])
    if not products:
        print(f"audit_results 가 없다: {os.path.join(run_dir, 'audit_results')}")
        return
    # 잘린 id 는 현황판에 없어서 조용히 스킵된다 = 불일치 재작업 flag 가 안 찍힌다.
    batch_pids = _index_pids(run_dir, "audit_batches_index.json")
    _heal_pids(products, batch_pids, "정합검사")
    mismatch, match, uncomparable, main_suspect = R.audit_partition(products)

    # 배치 대비 누락 — 결과 파일이 통째로 빠져도 `###AUDIT###` 은 정상 종료로 찍힌다
    # = "감사했는데 깨끗하다"로 읽힌다(2026-08-15 2-3: run 팬아웃이 "완료배치 7" 을
    # 반환했는데 result_002.json 이 디스크에 없었다. audit 배치는 12건 단위라 하나가
    # 조용히 빠지면 12건이 대조 안 된 채 넘어간다). 치명적이진 않지만 — 현황판이 빈칸
    # 으로 남아 다음 prep 이 다시 집는다 — 조용한 누락은 그 자체가 결함이다.
    # `verdict` 처럼 차단하진 않는다(audit 은 크레딧도 자동반영도 안 걸린다).
    missing = sorted(batch_pids - {p.get("productId") for p in products})

    m = matrix.read(sheet)
    vals = {}
    for pid, why in mismatch.items():
        rec = m.get(pid)
        if not rec or (rec.get(TASK) or "").strip() == matrix.NA:
            continue   # 삭제 상품에 일감을 만들지 않는다 (matrix.flag 와 같은 규칙)
        vals[pid] = matrix.redo_value(why, from_task="정합검사")
    for pid in match:
        if pid in m:
            vals[pid] = "완료(정합확인)"
    # 대표옵션의심(2026-08-06) — 썸네일이 아니라 옵션이 뿌리다. 썸네일 열은 보류로 세우고
    # 옵션 열에 재작업 flag 를 찍어 옵션정리(§현재 상태를 믿지 마라)로 넘긴다.
    for pid in main_suspect:
        rec = m.get(pid)
        if rec and (rec.get(TASK) or "").strip() != matrix.NA:
            vals[pid] = "보류(대표옵션의심)"
    n = matrix.mark_many(sheet, TASK, vals, matrix=m) if vals else 0
    k = matrix.flag_many(sheet, "옵션",
                         {pid: _to_option_reason(R.AUDIT_MAIN_SUSPECT, why)
                          for pid, why in main_suspect.items()},
                         from_task="썸네일",
                         matrix=m) if main_suspect else 0
    print(f"\n###AUDIT### 불일치 {len(mismatch)}건(재작업 flag) / 일치 {len(match)}건 "
          f"/ 대조불가 {len(uncomparable)}건(flag 안 함·집계만) "
          f"/ 대표옵션의심 {len(main_suspect)}건(옵션 재작업 flag)")
    print(f"  현황판({matrix.TAB}) {TASK}: {n}칸 갱신")
    if mismatch:
        print("  불일치 건은 다음 prep 이 재작업으로 자동으로 다시 집어간다.")
    if main_suspect:
        print(f"  현황판({matrix.TAB}) 옵션 재작업 flag: {k}칸 — 옵션정리가 대표를 "
              f"복구하면 이관(썸네일)으로 되돌아온다")
    if uncomparable:
        _dump(os.path.join(run_dir, "audit_uncomparable.json"), uncomparable)
        print(f"  대조불가 목록: {os.path.join(run_dir, 'audit_uncomparable.json')}")
    if missing:
        _dump(os.path.join(run_dir, "audit_missing.json"), missing)
        print(f"  ⚠ 미대조 {len(missing)}건 — 팬아웃이 안 끝났다. 이 건들은 현황판이 "
              f"빈칸으로 남아 다음 prep 이 다시 집는다(=이번 감사는 전건이 아니다).\n"
              f"    끝내려면: pending --audit 로 남은 배치를 마저 돌리고 다시 --commit\n"
              f"    예: {missing[:5]}\n"
              f"    목록: {os.path.join(run_dir, 'audit_missing.json')}")


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def _batch_products(run_dir):
    """batches/batch_NNN.json → {pid: product}. 배치가 pass-through 필드의 정본이다."""
    by_pid = {}
    for bf in sorted(glob.glob(os.path.join(run_dir, "batches", "batch_*.json"))):
        for p in _load(bf).get("products", []):
            if p.get("productId"):
                by_pid[p["productId"]] = p
    return by_pid


# 워커가 채워야 하는 판단 필드 — 이것만 results 에서 취한다. 나머지(기존썸네일·후보·
# 대표옵션명 등 pass-through)는 배치(정본)에서 조인한다. 워커 환각이 백업·복원 경로
# (`_generate` 의 before_generate.json)에 들어가는 것을 원천 차단한다.
_JUDGE_FIELDS = ("기준이미지", "기준이미지경로", "모드", "프롬프트", "상태")


def _index_pids(run_dir, index_name):
    """<index>.json 이 가리키는 배치 파일들의 정본 productId 집합."""
    path = os.path.join(run_dir, index_name)
    if not os.path.exists(path):
        return set()                     # 그 축을 안 돌린 run-dir — 복구할 정본이 없다
    pids = set()
    for b in _load(path) or []:
        if isinstance(b, dict) and b.get("path") and os.path.exists(b["path"]):
            pids |= {p["productId"] for p in (_load(b["path"]) or {}).get("products", [])
                     if p.get("productId")}
    return pids


def _heal_pids(products, valid, axis):
    """워커가 **이미지 파일명에서 베낀 잘린 productId** 를 정본으로 되돌린다.

    `materialize_image` 가 파일명을 24자로 자르는데 productId 는 27자다. 워커가 눈앞의
    파일명(`U01KSD7D7Y3338WQQKZWT0XT_2.jpg`)에서 상품코드를 옮겨 적으면 정본과 어긋나
    **판정이 통째로 버려진다** — verdict 는 commit 이 막히고(눈에 띈다), prescreen·audit·
    run 은 조용히 미판정으로 흘러간다(안 띈다. 기준적격 검사를 건너뛴 채 생성되거나
    불일치 재작업 flag 가 안 찍힌다).

    2026-08-14 실측: 3-2 verdict 2건 · 2-2 verdict 15건 — **지시서에 경고를 넣은 당일
    재발**했다. 지시문으로는 안 막히므로 수합부에서 되살린다.

    복구 규칙은 `R.heal_pid` 에 있다 — 잘리기만 한 것도, 파일명 접미(`_2`·`_Y`)까지
    벤 것도 받는다(2026-08-15 용쌤2-1: 접미까지 벤 2건은 예전 로직이 못 잡아 손으로
    고쳤다). 후보가 정확히 1개일 때만 고친다(fail-closed).
    """
    if not valid:
        return []
    healed = []
    for p in products:
        fixed = R.heal_pid(p.get("productId"), valid)
        if fixed:
            healed.append(f"{p['productId']}→{fixed}")
            p["productId"] = fixed
    if healed:
        print(f"  [복구] {axis}: 잘린 productId {len(healed)}건 — 접두 매칭으로 되살림: "
              f"{healed[:3]}", file=sys.stderr)
    return healed


def _results(run_dir):
    """results/*.json → 상품 리스트. 배치 정본과 조인하고, 마지막 파일이 이긴다.

    result_000(`선기록`)은 prep 이 직접 쓴 것이라 그대로 신뢰한다.
    배치에 없는 pid(워커 환각)는 버린다 — 크레딧·자동반영이 걸린 경로라 fail-closed.
    단 **잘린 id 는 버리기 전에 되살린다**(`_heal_pids`).
    """
    batch_pids = _batch_products(run_dir)
    by_pid, order = {}, []
    for rf in sorted(glob.glob(os.path.join(run_dir, "results", "result_*.json"))):
        doc = _load(rf)
        trusted = bool(doc.get("선기록"))
        if not trusted:
            _heal_pids(doc.get("products", []), set(batch_pids), "run")
        for p in doc.get("products", []):
            pid = p.get("productId")
            if not pid:
                continue
            if trusted:
                merged = p                     # prep 산출 — 전 필드 신뢰
            elif pid in batch_pids:
                merged = dict(batch_pids[pid])  # 배치가 정본, 판단 필드만 워커 것
                merged.update({k: p[k] for k in _JUDGE_FIELDS if k in p})
            elif batch_pids:
                continue                        # 환각 — _audit 가 경고로 집계
            else:
                merged = p                      # 구형 run-dir(배치 정본 없음) 폴백
            if pid not in by_pid:
                order.append(pid)
            by_pid[pid] = merged                # 마지막 파일 승리
    return [by_pid[pid] for pid in order]


def _audit(run_dir):
    """워커 산출물을 배치 대비 대조. 반환: (경고 리스트, 누락 여부)."""
    batch_pids = set(_batch_products(run_dir))
    if not batch_pids:
        return [], False                        # 구형 run-dir 또는 전건 선기록
    got = set()
    for rf in sorted(glob.glob(os.path.join(run_dir, "results", "result_*.json"))):
        doc = _load(rf)
        if doc.get("선기록"):
            continue
        # `_results` 와 같은 복구를 여기서도 해야 누락 집계가 어긋나지 않는다.
        _heal_pids(doc.get("products", []), batch_pids, "run(감사)")
        got |= {p.get("productId") for p in doc.get("products", []) if p.get("productId")}
    missing = sorted(batch_pids - got)
    unknown = sorted(got - batch_pids)
    warns = []
    if missing:
        warns.append(f"누락 상품 {len(missing)}건: {missing[:5]}")
    if unknown:
        warns.append(f"미지의 상품id {len(unknown)}건(워커 환각 — 버린다): {unknown[:5]}")
    return warns, bool(missing)


def _guard_credits(items):
    """잔액이 이번 생성분을 못 감당하면 시작조차 하지 않는다.

    생성 승인 게이트를 없앤 뒤(2026-08-06) 남은 유일한 사전 방어다. 중간에 크레딧이
    바닥나면 일부만 생성된 채 끊기고, 그 시점의 스테이징(기준 이미지를 대표로 올려둔
    상태) 복원이 뒤엉킨다 — 시작 전에 막는 편이 싸다.
    조회 자체가 실패하면 **막지 않는다**(잔액을 모른다고 작업을 멈출 이유는 없다).
    """
    need = R.credit_estimate(len(items))
    try:
        mcp = ThumbMCP()
        mcp.open()
        try:
            bal = mcp.call_tool("bulsaja_ai_credit_balance", {})
        finally:
            mcp.close()
        have = int(bal.get("총사용가능") or bal.get("보유크레딧") or 0)
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] 크레딧 잔액을 못 읽었다({type(e).__name__}) — 확인 없이 진행한다",
              file=sys.stderr)
        return
    print(f"  크레딧: 필요 {need:,} / 잔액 {have:,}")
    if have < need:
        print(f"\n크레딧이 모자라 생성을 시작하지 않는다(필요 {need:,} · 잔액 {have:,}). "
              f"--limit 으로 줄여서 나눠 돌려라.", file=sys.stderr)
        sys.exit(4)


def cmd_apply(args):
    run_dir = os.path.abspath(args.run_dir)
    sheet = _resolve_sheet(args)
    warns, has_missing = _audit(run_dir)
    for w in warns:
        print(f"  [감사] {w}")
    items = _results(run_dir)
    if not items:
        print(f"results 가 없다: {os.path.join(run_dir, 'results')}")
        return
    # 워커 보류(`상태: 보류(…)`)는 생성 대상이 아니다 — 크레딧 계산·--generate 에서 뺀다.
    # (2026-08-01 스모크 실측: 안 빼면 보류 2건이 예상 크레딧에 합산되고 생성까지 간다)
    held = [p for p in items if str(p.get("상태", "")).startswith("보류")]
    if held:
        print(f"\n  [보류 {len(held)}건 — 생성 대상에서 제외]")
        for p in held:
            print(f"    {p['productId']}: {p.get('상태')}")
        # **현황판에도 남긴다** — 안 남기면 다음 prep 이 pending 으로 또 집어가고,
        # 같은 후보를 다시 내려받아 같은 결론(보류)을 반복한다(2026-08-06 실측:
        # 1-3 2회차 prep 이 어제 보류한 3건을 그대로 다시 잡았다). 보류는 사람이
        # 이미 판단한 것이라 현황판에 값이 있으면 pending 에서 빠진다.
        if not getattr(args, "no_matrix", False):
            try:
                n = matrix.mark_many(sheet, TASK,
                                     {p["productId"]: str(p.get("상태")) for p in held})
                print(f"    → 현황판 '{TASK}' {n}칸에 보류 기록")
            except Exception as e:  # noqa: BLE001
                print(f"    [경고] 보류 현황판 기재 실패: {str(e)[:120]}", file=sys.stderr)
        items = [p for p in items if not str(p.get("상태", "")).startswith("보류")]
    if not items:
        print("생성 대상이 없다(전부 보류).")
        return

    # **기준 URL 을 해석 못 한 건은 태우지 않는다** (2026-08-17 용쌤2-1 실측).
    # 워커가 후보 밖 index 를 주면 `reference_url` 이 빈 문자열이 되고, 불사자는 넘겨준
    # 이미지가 아니라 **그 상품의 현재 대표**를 배경교체한다(`mode` 기본값 `first`).
    # 즉 크레딧은 그대로 나가고 기준은 한 글자도 안 바뀐다 — 재생성해도 같은 결과다.
    # 종전엔 미리보기에 `워커선택` 으로 찍혀 정상처럼 보였다(§reference_source).
    # 워커를 다시 돌리면 되므로 보류로 남기지 않고 **이번 회차 대상에서만** 뺀다.
    broken = [p for p in items if R.reference_source(p) == R.REF_BROKEN]
    if broken:
        print(f"\n  [기준 해석불가 {len(broken)}건 — 생성 대상에서 제외]")
        for p in broken:
            print(f"    {p['productId']}: 기준이미지 {p.get('기준이미지')!r} 가 "
                  f"후보{[c.get('index') for c in (p.get('후보이미지') or [])]} 에도 "
                  f"기존썸네일(0~{len(p.get('기존썸네일') or []) - 1}) 에도 없다")
        print("    → 그 배치의 result 를 지우고 pending → 재팬아웃 하면 다시 고른다.")
        items = [p for p in items if R.reference_source(p) != R.REF_BROKEN]
        if not items:
            print("\n생성 대상이 없다(전부 기준 해석불가).")
            return

    if args.commit:
        _commit(sheet, run_dir, args)
        return
    if args.generate:
        # 생성 자체는 **승인을 받지 않는다**(2026-08-06 이룸님). 남은 안전선은 두 개뿐:
        #   ① 누락이 있으면 차단 — 반쪽짜리 run 을 태우지 않는다(fail-closed)
        #   ② 크레딧 잔액이 모자라면 차단 — 중간에 끊기면 복원 대상이 뒤엉킨다
        if has_missing and not getattr(args, "allow_missing", False):
            print("\n누락 상품이 있어 --generate 를 차단한다. "
                  "pending 재계산 → 재팬아웃으로 채우거나, 의도된 것이면 --allow-missing.",
                  file=sys.stderr)
            sys.exit(3)
        _guard_credits(items)
        _generate(sheet, run_dir, items, args)
        return

    # 미리보기 — 쓰기 0. **--generate 와 같은 계획을 보여준다**:
    # 재개/부분 재실행이면 이미 태운 건이 빠지므로 예상 크레딧도 그만큼 줄어야
    # 표시와 실제 과금이 어긋나지 않는다(2026-08-05 F안).
    gen_path = os.path.join(run_dir, "generated.json")
    prev = _load(gen_path) if os.path.exists(gen_path) else {}
    items, skipped = R.generate_plan(items, prev, getattr(args, "ids", None))
    if skipped:
        by = {}
        for pid, why in skipped:
            by.setdefault(why, []).append(pid)
        for why, pids in by.items():
            print(f"  [건너뜀 {len(pids)}건] {why}")
    if not items:
        print("\n이번에 생성할 대상이 없다(전부 건너뜀).")
        return
    total_credits = R.credit_estimate(len(items))
    staged, repaint = 0, []
    print(f"\n{'상품id':<28} {'모드':<8} {'올림':<5} {'기준출처':<9} "
          f"{'기준이미지(실제 생성에 쓰는 URL)'}")
    print("-" * 110)
    for p in items:
        ref = R.reference_url(p)
        need = R.staged_thumbnails(p.get("기존썸네일") or [], ref) is not None
        src = R.reference_source(p)
        staged += bool(need)
        if not need:
            repaint.append((p["productId"], src))
        print(f"{p['productId']:<28} {p.get('모드', '기본'):<8} "
              f"{'O' if need else '-':<5} {src:<9} {ref[:60]}")
    print(f"\n대상 {len(items)}건 · 예상 크레딧 {total_credits:,} "
          f"(장당 {R.CREDITS_PER_IMAGE})")
    # '올림 O' = 기준이 현재 대표가 아니라서, 생성 직전에 대표로 올렸다가 되돌리는 건.
    print(f"기준을 대표로 올려야 하는 건 {staged}건 / 기존 대표 그대로 {len(items) - staged}건")
    # **`올림 -` 를 사람이 눈으로 훑는 대신 여기서 센다** (2026-08-15 광집게·크레인):
    # 기준이 이미 0번이면 불사자는 기존 대표를 그대로 배경교체한다. 그 대표가 딴 물건이면
    # 딴 물건이 예쁘게 재생성될 뿐이고, 재생성해도 같은 증상이 반복된다.
    if repaint:
        blind = [pid for pid, src in repaint if src == R.REF_EXISTING]
        print(f"\n  [주의] 기존 대표를 그대로 배경교체하는 건 {len(repaint)}건 — "
              f"그 대표가 대표옵션과 다른 물건이면 결과도 다른 물건이다.")
        if blind:
            print(f"  [주의] 그중 {len(blind)}건은 **워커 판단도 대표옵션도 없이** 기존 "
                  f"대표로 떨어진 것이다(기준출처 {R.REF_EXISTING}) — 태우기 전에 봐라: "
                  f"{blind[:5]}")
    print("\n미리보기다. 실제 생성은 --generate — 승인 대기 없이 바로 부른다(2026-08-06).")


def _restore_if_changed(mcp, pid, before, label="방어"):
    """대표가 `before` 와 다르면 되돌린다. 성공하면 None, 끝내 실패하면 사유 문자열.

    승인 전 쓰기 0 원칙의 마지막 방어선 — 생성 경로(`_generate`)와 회수 경로
    (`cmd_recover`)가 같은 걸 쓴다. 접수 후 시간이 지나면 자동반영이 걸렸을 수 있어서
    회수 때도 반드시 태워야 한다.

    DNS 순간 단절(NameResolutionError)이 실측으로 30건마다 한 번쯤 난다(2026-08-05).
    전송층 재시도(4회)를 다 쓰고도 실패하면 몇 초 뒤엔 대개 풀리므로 **복원만은** 더
    끈질기게 다시 시도한다 — 여기서 포기하면 미승인 이미지가 대표로 살아남는다.
    """
    if not before:
        return None
    last = ""
    for attempt in range(RESTORE_RETRIES):
        try:
            after = list(mcp.workdata(pid).get("썸네일") or [])
            if after != before:
                mcp.update_thumbnails(pid, before)
                print(f"  [{label}] {pid}: 승인 전 상태로 복원")
            return None
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {str(e)[:120]}"
            if attempt + 1 < RESTORE_RETRIES:
                wait = RESTORE_BACKOFF * (2 ** attempt)
                print(f"  [재시도] {pid}: 복원 {attempt + 1}회 실패 — "
                      f"{wait}초 후 다시")
                time.sleep(wait)
    return last


def _generate(sheet, run_dir, items, args):
    """실제 생성(승인 대기 없음, 2026-08-06) → 폴링 → 자동반영 방어 → review.html."""
    gen_path = os.path.join(run_dir, "generated.json")
    # **재개** — 중단된 run 을 다시 부를 때 이미 태운 건을 또 태우지 않는다(2026-08-05
    # 실측: DNS 단절로 63건에서 멈췄는데, 재실행이 처음부터 다시 태우는 구조였다).
    generated = _load(gen_path) if os.path.exists(gen_path) else {}
    todo, skipped = R.generate_plan(items, generated, getattr(args, "ids", None))
    if skipped:
        by = {}
        for pid, why in skipped:
            by.setdefault(why, []).append(pid)
        for why, pids in by.items():
            print(f"  [건너뜀 {len(pids)}건] {why}")
    if not todo:
        print("이번에 생성할 대상이 없다(전부 건너뜀).")
        return
    print(f"  이번 생성 대상 {len(todo)}건 · 예상 크레딧 "
          f"{R.credit_estimate(len(todo)):,}")
    items = todo

    # 복구 파일은 생성 전에 미리 쓴다 — 이게 없으면 중간에 끊겼을 때 이미 대표로
    # 자동반영된 건들을 되돌릴 방법이 없다. items 는 배치 파일에서 오는 로컬 데이터라
    # 네트워크를 안 탄다(상세 스킬에서 검증된 패턴).
    # 재개일 때는 **기존 백업 위에 얹는다** — 통째로 덮으면 앞 회차에서 태운 건들의
    # 복구 근거가 사라진다.
    bpath = os.path.join(run_dir, "before_generate.json")
    backup = _load(bpath) if os.path.exists(bpath) else {}
    backup.update({p["productId"]: list(p.get("기존썸네일") or []) for p in items})
    _dump(bpath, backup)

    mcp = ThumbMCP()
    mcp.open()
    restore_failed = None    # 복원 실패 = 미승인 이미지가 대표로 살아있다는 뜻 → 즉시 중단
    try:
        try:
            for n, p in enumerate(items, 1):
                pid = p["productId"]
                # 진행 카운터 — 로그가 line_buffering 이라 실시간으로 보인다.
                # 없으면 몇 시간짜리 run 의 진행률을 크레딧 잔액으로 역산해야 한다.
                print(f"[{n}/{len(items)}] {pid} {p.get('상품명', '')[:28]}")
                before = list(p.get("기존썸네일") or [])
                prompt = p.get("프롬프트") or None   # 레시피 모드만 채운다. 기본 모드는 None(디폴트 사용).
                # 생성 도구는 **그 상품의 첫 번째 대표이미지**를 배경교체한다(mode 기본값
                # `first`). 그래서 기준 이미지를 0번에 올려놓고 생성해야 팬아웃 판단과
                # 대표옵션 확정(규칙 0)이 결과에 반영된다 — 2026-08-05 실측 사고 지점.
                ref = R.reference_url(p)
                staged = R.staged_thumbnails(before, ref)
                task = None
                try:
                    if staged:
                        mcp.update_thumbnails(pid, staged)
                        print(f"  [기준] {pid}: 기준 이미지를 대표(0번)로 올림")
                    else:
                        # **없는 줄 대신 있는 줄로 남긴다** (2026-08-15 광집게·크레인):
                        # 사고를 캘 때 `올림` 줄이 "이 두 건만 없었다"로만 드러나
                        # 수백 줄 로그를 눈으로 세야 했다. 올릴 게 없다 = 불사자가
                        # 기존 대표를 그대로 배경교체한다는 뜻이라 그걸 명시한다.
                        print(f"  [기준] {pid}: 올릴 것 없음({R.reference_source(p)}) — "
                              f"기존 대표를 그대로 배경교체한다")
                    task = mcp.generate(pid, prompt=prompt)
                    # **접수 즉시 기록** — 폴링은 몇 분씩 걸리고 그 사이에 kill 되면
                    # taskId 가 통째로 사라져 회수도 못 한다(2026-08-06 실측: 6건 중
                    # 1건이 폴링 도중 종료돼 크레딧만 나가고 단서가 없었다).
                    # 크레딧이 나간 시점은 접수지 완료가 아니다 → 접수 직후 남긴다.
                    generated[pid] = dict(generated.get(pid) or {}, **{
                        "상품명": p.get("상품명", ""),
                        "대표옵션명": p.get("대표옵션명", ""),
                        "taskId": task["taskId"],
                        "오류": "접수함 — 결과 미확인(중단됐다면 recover 로 회수)"})
                    _dump(gen_path, generated)
                    imgs, credits = mcp.poll(task["taskId"])
                    if not imgs:
                        raise RuntimeError("생성 완료인데 이미지가 비어있다")

                    # 재생성 횟수는 **누적**한다 — `--ids` 로 다시 태울 때마다 1씩
                    # 올라가고, 상한(MAX_REGEN)에 닿으면 generate_plan 이 막는다.
                    tries = int((generated.get(pid) or {}).get("재생성횟수") or 0)
                    generated[pid] = {"상품명": p.get("상품명", ""), "생성본": imgs[0],
                                      "기존대표": before[0] if before else "",
                                      "후보": before[1:], "크레딧": credits,
                                      "재작업사유": p.get("재작업사유", ""), "판정": None,
                                      "기준이미지": ref,
                                      "재생성횟수": tries + 1,
                                      # 승인 화면에서 "생성본이 대표옵션과 같은 물건인가"를
                                      # 대조할 재료(2026-07-30). 없으면 판단 근거가 빠진다.
                                      "대표옵션명": p.get("대표옵션명", ""),
                                      "대표옵션이미지": p.get("대표옵션이미지", "")}
                    print(f"  [생성] {pid}: {imgs[0][:60]}... ({credits}크레딧)")
                except Exception as e:  # noqa: BLE001
                    # 실패는 **성공 기록을 지우지 않는다** — 재생성 시도가 실패했을 때
                    # 앞서 성공한 이미지까지 잃으면 검수 재료가 사라진다.
                    prev_ok = generated.get(pid) if "생성본" in (generated.get(pid) or {}) else None
                    fail = {"상품명": p.get("상품명", ""),
                            "대표옵션명": p.get("대표옵션명", ""),
                            "오류": f"{type(e).__name__}: {e}"[:200]}
                    # **접수된 taskId 는 반드시 남긴다** — 타임아웃은 실패가 아니라
                    # "아직"이라, 이게 있어야 `recover` 가 나중에 결과를 되찾는다
                    # (없으면 이미 쓴 크레딧이 그냥 버려진다. 2026-08-06 실측 6건).
                    if (task or {}).get("taskId"):
                        fail["taskId"] = task["taskId"]
                    generated[pid] = dict(prev_ok or {}, **fail)
                    print(f"  [실패] {pid}: {generated[pid]['오류']}", file=sys.stderr)
                finally:
                    # 원복 — **스테이징이든 자동반영이든 무조건**. 생성이 실패했어도 임시로
                    # 올려둔 기준 이미지가 대표로 남으면 안 된다(승인 전 쓰기 0 원칙).
                    # 자동반영 방어(2026-07-28 실측)도 이 한 곳으로 합쳤다.
                    err = _restore_if_changed(mcp, pid, before)
                    restore_failed = pid if err else None
                    if err:
                        print(f"  [경고] {pid}: 복원 {RESTORE_RETRIES}회 실패 — {err}"
                              f" · before_generate.json 으로 restore 필요",
                              file=sys.stderr)
                # **건별 중간 저장** — 프로세스가 kill 되거나 전원이 끊겨도 여기까지의
                # 결과가 남는다. 이게 곧 다음 실행의 재개 근거다(2026-08-05 F안).
                # 아래 finally 의 일괄 기록은 정상·Ctrl-C 종료용으로 그대로 둔다.
                _dump(gen_path, generated)
                # 복원이 실패했다 = 미승인 이미지가 대표로 살아있다. 더 만들지 않고 멈춘다.
                if restore_failed:
                    print(f"\n복원 실패({restore_failed})로 생성을 중단한다. "
                          f"`restore --run-dir <R>` 로 되돌린 뒤 원인을 확인해라.",
                          file=sys.stderr)
                    break
        finally:
            # Ctrl-C(KeyboardInterrupt)는 Exception 이 아니라 위 except 를 그냥 지나친다 —
            # 중단돼도 그 시점까지 생성된 결과가 파일로 남도록 여기서 무조건 기록한다.
            _dump(gen_path, generated)
    finally:
        mcp.close()

    review_path = review_html.build(generated, os.path.join(run_dir, "review.html"))
    ok = len([v for v in generated.values() if "생성본" in v])
    print(f"\n###GENERATE### 성공 {ok}건 / 실패 {len(generated) - ok}건")
    print(f"  검수 페이지: {review_path}")
    print("  다음: review.html 확인 → apply --commit(전부 승인) "
          "또는 일부만 거르려면 decisions.json 작성 후 --commit")


def _commit(sheet, run_dir, args):
    """최종 반영 — Claude 가 3축 판정을 마친 직후 부른다(승인 대기 없음, 2026-08-06).

    `--commit` 을 부르는 행위 자체가 판정이 끝났다는 뜻이다. 그래서 `decisions.json`
    이 없으면 생성 성공분 전부를 **사용가능**으로 본다 — 판정에서 거른 상품이 있으면
    반드시 이 파일에 먼저 적어야 한다. 일부만 거를 때 그 건만 재정의한다.
    """
    gen_path = os.path.join(run_dir, "generated.json")
    dec_path = os.path.join(run_dir, "decisions.json")
    if not os.path.exists(gen_path):
        print(f"generated.json 이 없다: {gen_path} — 먼저 apply --generate 를 돌려라.")
        return
    generated = _load(gen_path)
    decisions = _load(dec_path) if os.path.exists(dec_path) else {}
    if decisions:
        print(f"  decisions.json 반영: {len(decisions)}건 재정의")
    else:
        print("  decisions.json 없음 — 생성 성공분 전부 '사용가능'으로 반영")

    mcp = ThumbMCP()
    mcp.open()
    done, held, main_suspect = {}, {}, {}
    sheet_rows, finalized = [], []
    try:
        for pid, g in generated.items():
            dec = decisions.get(pid) or {}
            verdict = dec.get("판정", "사용가능")
            reason = dec.get("사유", "")
            # **fallback 이 이미 종결한 건은 통째로 건너뛴다** (2026-08-15 조용한 되감기).
            # 현황판도 시트도 손대지 않는다 — 여기서 손대면 `완료(원본대체…)` 가
            # 판정값에 밀려 `보류(제외)` 로 되돌아간다. 자세한 경위는 `R.FINAL_VERDICTS`.
            if R.is_final(verdict):
                finalized.append(pid)
                continue
            if "생성본" not in g:
                # 7튜플 고정 — `_log_sheet` 이 (pid, 상품명, 생성본, 판정, 사유, 크레딧,
                # 상태)로 언패킹한다. 여기만 8개를 넣어 대량 커밋이 시트 단계에서
                # 터졌다(2026-08-05 실측: 불사자 저장 27건은 끝난 뒤였다).
                sheet_rows.append((pid, g.get("상품명", ""), "", "",
                                   g.get("오류", ""), 0, "보류(생성실패)"))
                continue
            if verdict != "사용가능":
                # 판정에 '대표옵션의심'이 들어 있으면 썸네일 문제가 아니라 옵션 문제다
                # (옵션정리가 부속을 본품으로 오인해 대표를 세운 것 — 2026-08-06 캠핑박스
                # 사례). 재생성·fallback 경로로 보내지 않고 옵션 재작업으로 넘긴다.
                # `기준이미지없음`(대표옵션이 도면·배너라 대조 기준이 없다)도 같은 뿌리다 —
                # 대표옵션을 실물 사진이 있는 값으로 다시 세워야 풀린다 (2026-08-07 이룸님).
                hit = next((v for v in R.TO_OPTION_VERDICTS if v in str(verdict)), None)
                if hit:
                    held[pid] = f"보류({hit})"
                    main_suspect[pid] = _to_option_reason(hit, reason or (
                        "대표옵션이 본품이 아님(부속 의심)"
                        if hit == R.AUDIT_MAIN_SUSPECT
                        else "대표옵션 이미지가 비제품(도면·배너) — 실물 사진이 "
                             "있는 값으로 대표를 다시 세울 것"))
                else:
                    held[pid] = f"보류({verdict})"
                sheet_rows.append((pid, g.get("상품명", ""), g["생성본"],
                                  verdict, reason, 0, held[pid]))
                continue
            try:
                final = [g["생성본"]] + list(g.get("후보") or [])
                mcp.update_thumbnails(pid, final)
                time.sleep(args.sleep)
                after = (mcp.workdata(pid).get("썸네일") or [""])[0]
                if not after.startswith("https://"):
                    raise RuntimeError(f"재조회 결과가 https 가 아니다: {after[:80]}")
                snapshot.update(pid, 썸네일=[g["생성본"]] + list(g.get("후보") or []))
                done[pid] = "완료"
                sheet_rows.append((pid, g.get("상품명", ""), g["생성본"], verdict,
                                  reason, g.get("크레딧", 0), "완료"))
                print(f"  [완료] {pid}")
            except Exception as e:  # noqa: BLE001
                held[pid] = f"보류(저장실패)"
                sheet_rows.append((pid, g.get("상품명", ""), g.get("생성본", ""),
                                  verdict, f"{type(e).__name__}: {e}"[:150], 0, held[pid]))
                print(f"  [실패] {pid}: {e}", file=sys.stderr)
    finally:
        mcp.close()

    print(f"\n###COMMIT### 반영 {len(done)}건 / 보류·실패 {len(held)}건"
          + (f" (그중 대표옵션의심 {len(main_suspect)}건 → 옵션 재작업)" if main_suspect else "")
          + (f" / fallback 종결 {len(finalized)}건 건너뜀" if finalized else ""))
    if not args.no_sheet:
        # **시트 실패가 현황판을 막지 않게 한다** (2026-08-15 용쌤2-1 §3 실측):
        # 422행 회차에서 시트 쓰기가 세 번 죽었다(429 두 번 + 500 한 번). 그때마다
        # 불사자 반영은 **이미 끝나 있었는데** 예외가 여기서 터져 아래 현황판 갱신까지
        # 통째로 날아갔다 — 그러면 다음 prep 이 이미 끝난 건을 pending 으로 또 집어간다.
        # 현황판이 다음 회차의 정본이므로 시트보다 우선한다.
        try:
            _log_sheet(sheet, sheet_rows)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 시트 본문 기록 실패 — 현황판은 그대로 진행한다: "
                  f"{type(e).__name__}: {str(e)[:150]}\n"
                  f"         복구: apply --run-dir <R> --commit --no-sheet "
                  f"(불사자 반영·현황판은 멱등)", file=sys.stderr)
    if not args.no_matrix:
        vals = dict(done)
        vals.update(held)
        m = matrix.read(sheet)
        n = matrix.mark_many(sheet, TASK, vals, matrix=m)
        print(f"  현황판({matrix.TAB}) {TASK}: {n}칸 갱신")
        if main_suspect:
            k = matrix.flag_many(sheet, "옵션", main_suspect,
                                 from_task="썸네일", matrix=m)
            print(f"  현황판({matrix.TAB}) 옵션 재작업 flag: {k}칸 (대표옵션의심 — "
                  f"옵션정리 복구 후 이관(썸네일)으로 되돌아온다)")


def _log_sheet(sheet, rows):
    if ensure_tab(sheet, TAB, HEADER):
        print(f"  탭 신설: {TAB}")
    try:
        col_a = [str(r[0]).strip() if r else "" for r in sheets_get(sheet, f"'{TAB}'!A2:A")]
    except Exception:
        col_a = []
    at = {pid: i + 2 for i, pid in enumerate(col_a) if pid}
    last = _col_letter(len(HEADER))
    add = []
    for pid, name, gen, verdict, reason, credits, status in rows:
        vals = [pid, _today(), name, "기본", "", gen, verdict, reason, credits, status]
        r = at.get(pid)
        if r:
            sheets_update(sheet, f"'{TAB}'!A{r}:{last}{r}", [vals], value_input="USER_ENTERED")
        else:
            add.append(vals)
    if add:
        append_rows(sheet, TAB, add)
        print(f"  시트 기록: {len(add)}행 → '{TAB}'")


def _pending_verdict_batches(run_dir):
    """vresult 가 아직 없는 검수 배치 — [{n, path, imgs, count}]."""
    idx = os.path.join(run_dir, "verdict_batches_index.json")
    index = _load(idx) if os.path.exists(idx) else []
    if not isinstance(index, list):
        return []
    return [b for b in index
            if not os.path.exists(os.path.join(
                run_dir, "verdict", "results", f"vresult_{b['n']:03d}.json"))]


def _rotate_verdict_round(run_dir):
    """직전 판정 라운드(vresult + 배치 인덱스)를 `verdict/rounds/NNN/` 으로 밀어둔다.

    `--ids` 로 일부만 다시 판정할 때, 앞 라운드의 `vresult_*.json` 이 그대로 남아 있으면
    `--commit` 이 그것까지 읽어 **이번 배치에 없는 상품**으로 잡고 환각 경고를 쏟는다.
    지우지는 않는다 — 재생성 전 판정이 왜 그랬는지가 근거로 남아야 한다.
    """
    res = os.path.join(run_dir, "verdict", "results")
    idx = os.path.join(run_dir, "verdict_batches_index.json")
    if not glob.glob(os.path.join(res, "vresult_*.json")):
        return None
    rounds = os.path.join(run_dir, "verdict", "rounds")
    n = 1
    while os.path.exists(os.path.join(rounds, f"{n:03d}")):
        n += 1
    dst = os.path.join(rounds, f"{n:03d}")
    os.makedirs(dst, exist_ok=True)
    for f in glob.glob(os.path.join(res, "vresult_*.json")):
        shutil.move(f, os.path.join(dst, os.path.basename(f)))
    if os.path.exists(idx):
        shutil.copy2(idx, os.path.join(dst, "verdict_batches_index.json"))
    print(f"  앞 라운드 판정 결과를 보존: {dst}")
    return dst


def cmd_verdict(args):
    """생성본 3축 판정을 **팬아웃으로** 돌리는 경로 (2026-08-06 결함정리 §2-3).

    SKILL.md 는 "판정 주체 = Claude" 라고만 했고 배치 생성 명령이 없었다. 190건을 메인이
    직접 보면 이미지 380장이 컨텍스트에 쌓인다 — 1-2 그룹에서 임시 스크립트로 배치를 만들어
    16워커에 돌렸던 걸(183건·크레딧 0·3분) 스킬 안으로 들인다.

    `verdict --run-dir <R>`          배치 생성 + Workflow args 출력
    `verdict --run-dir <R> --commit` vresult 를 모아 `decisions.json` 작성
    `verdict --run-dir <R> --ids …`  **그 상품만** 다시 판정(재생성분 재판정)

    `--ids` 가 없어서 재생성분만 다시 판정하려면 배치를 손으로 조립하고, 기존 결과에서
    그 건들만 빼서 복원해야 했다(2026-08-15 용쌤2-1 §7). 이제 지목한 건만 새 라운드로
    돌린다 — 앞 라운드의 결과·인덱스는 `verdict/rounds/NNN/` 로 밀어두고(누적 근거는
    남긴다), `--commit` 은 `decisions.json` 에 **덮어쓰지 않고 합친다**.
    """
    run_dir = os.path.abspath(args.run_dir)
    gen_path = os.path.join(run_dir, "generated.json")
    if not os.path.exists(gen_path):
        print(f"generated.json 이 없다: {gen_path} — 먼저 apply --generate 를 돌려라.",
              file=sys.stderr)
        sys.exit(2)
    generated = _load(gen_path)
    ok = {pid: g for pid, g in generated.items() if g.get("생성본")}
    if args.commit:
        return _verdict_commit(run_dir, ok)

    only = [p for p in (getattr(args, "ids", None) or []) if p.strip()]
    if only:
        unknown = [p for p in only if p not in ok]
        if unknown:
            print(f"  [경고] 생성본이 없어 판정할 수 없는 id {len(unknown)}건: "
                  f"{unknown[:3]}", file=sys.stderr)
        ok = {pid: g for pid, g in ok.items() if pid in set(only)}
        if not ok:
            print("판정할 대상이 없다(--ids 가 전부 생성본 없음).", file=sys.stderr)
            sys.exit(2)
        _rotate_verdict_round(run_dir)
        print(f"  --ids {len(ok)}건만 다시 판정한다(앞 라운드 결과는 rounds/ 로 보존).")

    thumbs_dir = os.path.join(run_dir, "verdict", "thumbs")
    items = []
    for pid, g in ok.items():
        # 구분은 **idx** 로 한다(name_hint 는 24자에서 잘린다 — §1-4·§2-1 과 같은 함정).
        # **여기만 축소하지 않는 게 기본이다**(`--max-px 0`). 3축 중 `제외(글자변조)` 는
        # 제품에 각인된 브랜드 글자를 원본↔생성본으로 **대조**하는데, 2026-08-07 실측에서
        # 같은 인버터 브랜드를 512 는 `讯浦`, 768 은 `锐霸` 로 갈라 읽었다. 판독은 512 로
        # 충분해도 이 미세 대조는 오독이 곧 거짓 재작업이라 여유를 남긴다.
        cur, _ = snapshot.materialize_image(g.get("기존대표") or "", thumbs_dir, pid, 0,
                                            max_px=_px(args, VERDICT_MAX_PX))
        mo, _ = snapshot.materialize_image(g.get("대표옵션이미지") or "", thumbs_dir, pid, 1,
                                           max_px=_px(args, VERDICT_MAX_PX))
        new, err = snapshot.materialize_image(g.get("생성본") or "", thumbs_dir, pid, 2,
                                              max_px=_px(args, VERDICT_MAX_PX))
        if not new:
            # 생성본을 못 받으면 판정 자체가 불가능하다 — 조용히 빼지 않고 드러낸다.
            print(f"  [경고] {pid}: 생성본 이미지 확보 실패 — 판정 대상에서 뺀다 "
                  f"({str(err)[:80]})", file=sys.stderr)
            continue
        items.append({"productId": pid, "상품명": g.get("상품명", ""),
                      "대표옵션명": g.get("대표옵션명", ""),
                      "재작업사유": g.get("재작업사유", ""),
                      "기존대표경로": cur or "", "대표옵션경로": mo or "",
                      "생성본경로": new,
                      "생성본": g.get("생성본", ""),
                      "재생성횟수": g.get("재생성횟수", 0)})
    if not items:
        print("판정할 생성본이 없다.")
        return

    bdir = os.path.join(run_dir, "verdict", "batches")
    os.makedirs(bdir, exist_ok=True)
    index = []
    for n, i in enumerate(range(0, len(items), args.batch_size), 1):
        chunk = items[i:i + args.batch_size]
        path = os.path.join(bdir, f"vbatch_{n:03d}.json")
        _dump(path, {"배치": n, "판정기준": VERDICT_PROMPT, "products": chunk})
        index.append({"n": n, "path": path, "count": len(chunk),
                      "imgs": sum(bool(c["기존대표경로"]) + bool(c["대표옵션경로"]) + 1
                                  for c in chunk)})
    _dump(os.path.join(run_dir, "verdict_batches_index.json"), index)
    print(f"\n###VERDICT### 배치 {len(index)}개 / 판정 대상 {len(items)}건")
    print(f"  배치: {bdir}")
    print("  다음(Workflow): 아래 JSON 을 thumb-fanout args 로 그대로 넣어라")
    print(json.dumps({"runDir": run_dir, "promptPath": VERDICT_PROMPT,
                      "mode": "verdict",
                      "batches": _pending_verdict_batches(run_dir)},
                     ensure_ascii=False))
    print(f"  이후: {os.path.basename(__file__)} verdict --run-dir <R> --commit "
          f"→ decisions.json → apply --commit")


def _verdict_commit(run_dir, ok):
    """vresult_*.json → decisions.json. **배치 대비 누락을 먼저 잡는다.**

    누락을 조용히 통과시키면 판정 안 한 상품이 `decisions.json` 에 없다는 이유로
    `apply --commit` 에서 **전부 '사용가능'으로 반영**된다 — 검수를 건너뛴 것이
    검수 통과로 둔갑한다. 그래서 누락이 있으면 파일을 쓰지 않고 멈춘다.
    """
    def _seq(path):
        """vresult_013.json / vbatch_013.json → '013'. 못 읽으면 None."""
        try:
            return os.path.basename(path).split("_")[1].split(".")[0]
        except IndexError:
            return None

    want = set()
    batch_ids = {}                       # 배치번호 → 그 배치의 정본 id 집합
    for b in _load(os.path.join(run_dir, "verdict_batches_index.json")) or []:
        ids = {p["productId"] for p in _load(b["path"]).get("products", [])}
        want |= ids
        if _seq(b["path"]):
            batch_ids[_seq(b["path"])] = ids
    got, rows, healed = {}, 0, []
    for rf in sorted(glob.glob(os.path.join(run_dir, "verdict", "results",
                                            "vresult_*.json"))):
        mine = batch_ids.get(_seq(rf))
        for p in _load(rf).get("products", []):
            pid = p.get("productId")
            if not pid:
                continue
            # **잘린 productId 자가복구** — 워커가 상품코드를 이미지 파일명(24자로 잘린
            # 형태)에서 베끼면 27자 정본과 어긋나 판정이 통째로 버려지고, 같은 건이
            # 누락으로도 잡혀 commit 이 막힌다(2026-08-14 실측: 3-2 2건·2-2 15건 —
            # 지시서에 경고를 넣은 당일 재발했다. 지시문으로는 안 막힌다).
            # 판정 내용은 멀쩡하므로 되살린다. 단 **자기 배치 안에서만** 접두 매칭한다
            # (배치를 넘으면 남의 판정을 엉뚱한 상품에 붙이게 된다). 규칙은 `R.heal_pid`.
            fixed = R.heal_pid(pid, mine) if mine else None
            if fixed:
                healed.append(f"{pid}→{fixed}")
                pid = fixed
            rows += 1
            got[pid] = {"판정": str(p.get("판정") or "사용가능").strip(),
                        "사유": str(p.get("사유") or "").strip()}
    if healed:
        print(f"  [복구] 잘린 productId {len(healed)}건 — 자기 배치 안 접두 매칭: "
              f"{healed[:3]}", file=sys.stderr)
    unknown = sorted(set(got) - want) if want else []
    missing = sorted(want - set(got))
    if unknown:
        print(f"  [경고] 배치에 없는 상품 {len(unknown)}건(환각) — 버린다: {unknown[:3]}",
              file=sys.stderr)
        for pid in unknown:
            got.pop(pid, None)
    if missing:
        print(f"\n판정 누락 {len(missing)}건 — decisions.json 을 쓰지 않는다"
              f"(그대로 두면 미판정이 '사용가능'으로 반영된다): {missing[:5]}",
              file=sys.stderr)
        sys.exit(3)
    # **덮어쓰지 않고 합친다** — `verdict --ids` 로 일부만 다시 판정한 라운드가
    # 나머지 상품의 판정을 지워 버리면, `apply --commit` 이 그 건들을 판정 없음
    # (= 전부 '사용가능')으로 반영한다. 전건 재판정이면 어차피 전 키를 덮는다.
    # `fallback` 이 종결한 건(`R.FINAL_VERDICTS`)은 판정이 다시 와도 지키지 않는다 —
    # 재판정 대상으로 지목했다면 그게 사람의 뜻이다.
    dec_path = os.path.join(run_dir, "decisions.json")
    merged = (_load(dec_path) if os.path.exists(dec_path) else {}) or {}
    kept = len([p for p in merged if p not in got])
    merged.update(got)
    _dump(dec_path, merged)
    by = {}
    for pid, d in got.items():
        by.setdefault(d["판정"], []).append(pid)
    print(f"\n###VERDICT### decisions.json {len(got)}건 (결과행 {rows})"
          + (f" · 앞 라운드 판정 {kept}건 유지" if kept else ""))
    for v, pids in sorted(by.items(), key=lambda t: -len(t[1])):
        print(f"  {v}: {len(pids)}건" + (f" — {pids[:3]}" if v != "사용가능" else ""))
    print(f"  {dec_path}")
    print("  다음: apply --run-dir <R> --commit")


def cmd_recover(args):
    """타임아웃으로 놓친 생성 결과를 taskId 로 되찾는다 — **크레딧 0**.

    **왜 필요한가** (2026-08-06 실측): 재개분 6건이 전부 `TimeoutError: 타임아웃(300s)`
    로 실패 기록됐는데, 그 taskId 를 조회하니 전부 `대기 중` 이었다. 죽은 게 아니라
    큐가 밀린 것뿐이고 크레딧은 이미 나갔다. 회수 경로가 없으면 그 30크레딧과 결과
    이미지가 그냥 버려진다. **타임아웃은 실패가 아니라 "아직"이다.**

    아직 대기 중인 건은 그대로 둔다 — 다시 부르면 그때 회수된다(멱등).
    회수한 상품은 `apply --generate` 가 그랬듯 **자동반영 방어**를 태운다: 접수 후
    시간이 흘러 서버가 대표를 바꿔놨을 수 있어서, 재조회해 바뀌었으면 되돌린다.

    생성 기록의 나머지 필드(후보·기준이미지·재작업사유 등)는 워커 결과가 아니라
    **배치(정본)에서 조인**한다 — `_commit` 과 같은 규칙이다.
    """
    run_dir = os.path.abspath(args.run_dir)
    gen_path = os.path.join(run_dir, "generated.json")
    if not os.path.exists(gen_path):
        print(f"generated.json 이 없다: {gen_path}", file=sys.stderr)
        sys.exit(2)
    generated = _load(gen_path)
    targets = R.recover_targets(generated, only_ids=args.ids)
    if not targets:
        print("회수할 건이 없다(taskId 가 남은 미완료 기록 없음).")
        return
    print(f"  회수 대상 {len(targets)}건")

    # 조인 소스는 `_results` 다 — `_batch_products` 가 아니다(2026-08-07 실측 버그).
    # 대표옵션 확정건은 prep 이 `results/result_000.json` 에 **선기록**하고 배치에서
    # 빼기 때문에, 옵션정리를 먼저 돌린 그룹은 `batches/` 가 통째로 비어 있다.
    # 배치만 보면 그런 회차의 회수분이 `대표옵션이미지`·`재작업사유`를 잃고,
    # 그러면 검수 ①제품 정확성(대표옵션 대조)을 할 재료가 사라진다.
    bp = {p["productId"]: p for p in _results(run_dir) if p.get("productId")}
    bpath = os.path.join(run_dir, "before_generate.json")
    backup = _load(bpath) if os.path.exists(bpath) else {}

    mcp = ThumbMCP()
    mcp.open()
    got, waiting, failed, credits_sum = {}, {}, {}, 0
    try:
        for pid, task_id in targets.items():
            p = bp.get(pid) or {}
            # 백업이 정본이다 — 생성 직전 실제 배열이라 배치보다 최신이다.
            before = list(backup.get(pid) or p.get("기존썸네일") or [])
            try:
                done, imgs, credits, fails = mcp.task_status(task_id)
            except Exception as e:  # noqa: BLE001
                failed[pid] = f"{type(e).__name__}: {str(e)[:120]}"
                print(f"  [조회실패] {pid}(task {task_id}): {failed[pid]}",
                      file=sys.stderr)
                continue
            if fails:
                failed[pid] = f"생성 실패: {str(fails)[:120]}"
                generated[pid] = dict(generated.get(pid) or {},
                                      오류=failed[pid])
                print(f"  [실패확정] {pid}(task {task_id}): {failed[pid]}",
                      file=sys.stderr)
                continue
            if not (done and imgs):
                waiting[pid] = task_id
                print(f"  [대기] {pid}: task {task_id} — 아직 생성 중")
                continue

            prev = generated.get(pid) or {}
            generated[pid] = {"상품명": p.get("상품명", prev.get("상품명", "")),
                              "생성본": imgs[0],
                              "기존대표": before[0] if before else "",
                              "후보": before[1:],
                              "크레딧": credits,
                              "재작업사유": p.get("재작업사유", ""),
                              "판정": None,
                              "기준이미지": R.reference_url(p) if p else "",
                              # 접수 때 이미 1회로 세었어야 할 시도다 — 회수가
                              # 재생성 상한을 우회하지 않도록 여기서 올린다.
                              "재생성횟수": int(prev.get("재생성횟수") or 0) + 1,
                              "대표옵션명": p.get("대표옵션명",
                                                prev.get("대표옵션명", "")),
                              "대표옵션이미지": p.get("대표옵션이미지", "")}
            got[pid] = imgs[0]
            credits_sum += int(credits or 0)
            print(f"  [회수] {pid}: {imgs[0][:60]}... ({credits}크레딧)")
            _dump(gen_path, generated)   # 건별 중간 저장 — 중단돼도 여기까지는 남는다
            # 자동반영 방어 — 접수 후 시간이 흘렀으니 생성 경로보다 오히려 더 필요하다.
            err = _restore_if_changed(mcp, pid, before)
            if err:
                print(f"  [경고] {pid}: 복원 {RESTORE_RETRIES}회 실패 — {err}"
                      f" · before_generate.json 으로 restore 필요", file=sys.stderr)
    finally:
        _dump(gen_path, generated)
        mcp.close()

    if got:
        review_path = review_html.build(generated,
                                        os.path.join(run_dir, "review.html"))
        print(f"  검수 페이지 갱신: {review_path}")
    print(f"\n###RECOVER### 회수 {len(got)}건 / 대기 {len(waiting)}건 "
          f"/ 실패 {len(failed)}건 · 회수분 크레딧 {credits_sum}")
    if waiting:
        print(f"  대기 중 — 나중에 같은 명령을 다시 불러라: {list(waiting)[:3]}")
    if failed:
        print(f"  실패: {list(failed)[:3]}", file=sys.stderr)


def cmd_mark_deleted(args):
    """404 로 삭제한 건을 현황판 `해당없음` 으로 확정한다 (2026-08-16).

    삭제는 메인이 `bulsaja_market_delete` 로 하고 스크립트는 그 사실을 모른다.
    확정 경로가 없으면 현황판이 `보류(...삭제대상)` 인 채로 남고, 사람이 손으로
    찍기를 잊으면 다음 회차에서 **이미 지운 상품을 또 삭제 대상으로 집는다**
    (실측: 25-2 후속 회차 5건). 그래서 삭제 직후 이 커맨드를 부르는 것을 규약으로 둔다.

    대상은 run-dir 의 404 목록 두 개를 합친 것 — `--ids` 로 좁힐 수 있다.
    멱등하다: 이미 `해당없음` 인 칸은 mark_many 가 건드리지 않는다.
    """
    sheet = _resolve_sheet(args)
    run_dir = os.path.abspath(args.run_dir) if args.run_dir else ""
    targets = {}
    # 두 목록은 **각자 독립으로 있을 수도 없을 수도** 있다 — prep 이 원본404 를 하나도
    # 못 만나면 `deletion_candidates.json` 자체가 안 생긴다(2-3 r5 실측). `_load` 는
    # 없는 파일에 FileNotFoundError 를 던지므로 여기서 흡수하지 않으면 **audit 쪽
    # 404 목록이 멀쩡히 있어도 확정이 통째로 죽는다**.
    def _load_opt(name):
        path = os.path.join(run_dir, name)
        return (_load(path) or {}) if os.path.exists(path) else {}

    if run_dir:
        # 대표 원본 404 (prep) — {pid: 상품명}
        for pid, name in _load_opt("deletion_candidates.json").items():
            targets[pid] = {"상품명": name if isinstance(name, str) else "",
                            "사유": "대표 원본 404"}
        # 대표옵션 이미지 404 (audit) — {pid: {상품명, 대표옵션, 사유}}
        for pid, info in _load_opt("audit_delete_404.json").items():
            info = info if isinstance(info, dict) else {}
            targets[pid] = {"상품명": info.get("상품명", ""),
                            "사유": info.get("사유", "대표옵션 이미지 404")}
    only = set(args.ids or ())
    if only:
        for pid in only:                      # 목록에 없는 id 도 명시했으면 받는다
            targets.setdefault(pid, {"상품명": "", "사유": "메인 지정"})
        targets = {p: v for p, v in targets.items() if p in only}
    if not targets:
        print("[중단] 확정할 대상이 없다 — run-dir 의 404 목록도 비었고 --ids 도 없다.\n"
              "  · 삭제 목록은 deletion_candidates.json / audit_delete_404.json 이다",
              file=sys.stderr)
        sys.exit(2)

    value = "해당없음(원본404·삭제)"
    changed = 0
    if not args.no_matrix:
        try:
            changed = matrix.mark_many(sheet, TASK, {p: value for p in targets})
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 현황판 기재 실패: {str(e)[:160]}", file=sys.stderr)
    print(f"\n###MARK-DELETED### 확정 {len(targets)}건 / 현황판 {changed}칸 갱신")
    print("  종합보고에 그대로 붙일 목록:")
    for pid, info in targets.items():
        print(f"    {pid}  {(info.get('상품명') or '')[:40]}  — {info.get('사유', '')}")


def cmd_restore(args):
    run_dir = os.path.abspath(args.run_dir)
    path = os.path.join(run_dir, "before_generate.json")
    if not os.path.exists(path):
        print(f"백업이 없다: {path}")
        return
    backup = _load(path)
    only = set(args.ids or ())
    mcp = ThumbMCP()
    mcp.open()
    ok, bad = 0, {}
    try:
        for pid, before in backup.items():
            if only and pid not in only:
                continue
            if not before:
                bad[pid] = "백업이 비어있다"
                continue
            try:
                mcp.update_thumbnails(pid, before)
                snapshot.update(pid, 썸네일=before)
                ok += 1
                print(f"  [복구] {pid}")
            except Exception as e:  # noqa: BLE001
                bad[pid] = f"{type(e).__name__}: {e}"[:200]
                print(f"  [실패] {pid}: {bad[pid]}", file=sys.stderr)
    finally:
        mcp.close()
    print(f"\n###RESTORE### 복구 {ok}건 / 실패 {len(bad)}건")


def cmd_fallback(args):
    """재생성 2회도 불합격 → **대표옵션 원본을 그대로 대표로 저장**(크레딧 0).

    SKILL.md 의 '검수 불합격 자동 처리' 마지막 줄이 이 명령이다. 규칙만 있고 코드가
    없어서 손으로 돌리던 경로를 명령으로 만들었다(2026-08-06 실측 — 물결조명 1건이
    AI 2회 모두 유리 튜브를 빈 장식 프레임으로 변조).

    원본은 실물 그 자체라 정합이 보장되므로 **별도 승인 게이트가 없다**. 다만 원본에
    워터마크·중국어 글자가 있을 수 있어 그 여부를 판정 사유에 남기고 보고에 싣는다.

    **`--run-dir` 를 주면 대표옵션이 없는 상품도 처리한다**(2026-08-06 결함정리 §2-2).
    예전엔 `main_option_of` 만 봐서 대표옵션 이미지가 없으면 건너뛰었는데, 그런 상품이
    바로 **비전 판단으로 가는 상품**이라 "AI 2회 실패 → 원본 대체" 경로가 그 상품군에는
    아예 없었다(실측 2건을 손으로 처리). 배치의 `기준이미지`(워커가 고른 후보) →
    대표옵션 → 기존 대표 순으로 폴백하는 `R.reference_url` 을 그대로 쓴다.
    """
    sheet = _resolve_sheet(args)
    pids = [p for p in (args.ids or []) if p.strip()]
    if not pids:
        print("--ids 가 필요하다(대표옵션 원본으로 되돌릴 상품).", file=sys.stderr)
        sys.exit(2)
    # run-dir 이 있으면 배치·생성기록에서 그 상품의 기준 이미지를 찾는다.
    bp = _batch_products(args.run_dir) if getattr(args, "run_dir", "") else {}
    gen = (_load(os.path.join(args.run_dir, "generated.json"))
           if getattr(args, "run_dir", "") else {}) or {}
    recs, errors = snapshot.ensure(pids)
    if errors:
        print(f"  조회 실패 {len(errors)}건: {list(errors)[:3]}", file=sys.stderr)

    mcp = ThumbMCP()
    mcp.open()
    done, bad, rows = {}, {}, []
    try:
        for pid in pids:
            rec = recs.get(pid)
            mo = R.main_option_of((rec or {}).get("옵션")) or {}
            ref = str(mo.get("이미지") or "").strip()
            src = "대표옵션"
            if not ref:
                # 대표옵션이 없는 상품 = 비전 판단으로 간 상품이다. 배치의 `기준이미지`
                # (워커가 고른 후보) → 기존 대표 순으로 폴백한다(§2-2).
                prod = dict(bp.get(pid) or {})
                if not prod.get("기존썸네일"):
                    prod["기존썸네일"] = (rec or {}).get("썸네일") or []
                if "기준이미지" not in prod and isinstance(
                        (gen.get(pid) or {}).get("기준이미지"), str):
                    ref = str(gen[pid]["기준이미지"]).strip()
                    src = "생성기록 기준이미지"
                if not ref:
                    ref = R.reference_url(prod)
                    src = "배치 기준이미지" if prod.get("기준이미지") is not None else "기존 대표"
            if not ref:
                bad[pid] = ("되돌릴 원본이 없다 — 대표옵션 이미지도, 기준 이미지도, "
                            "기존 썸네일도 없다")
                print(f"  [건너뜀] {pid}: {bad[pid]}", file=sys.stderr)
                continue
            try:
                cur = list(mcp.workdata(pid).get("썸네일") or [])
                before0 = cur[0] if cur else ""
                # 기준을 맨 앞으로. 배열 밖이어도 끼워 넣는다(대표옵션 이미지는 옵션 쪽
                # URL이라 썸네일 배열에 없는 게 보통 — 실측 303/311건).
                final = R.staged_thumbnails(cur, ref) or cur
                mcp.update_thumbnails(pid, final)
                after = list(mcp.workdata(pid).get("썸네일") or [])
                if not (after and after[0] == ref):
                    raise RuntimeError(f"재조회 불일치: {(after[0] if after else '(빈)')[:80]}")
                snapshot.update(pid, 썸네일=after)
                done[pid] = f"완료(원본대체·{src})"
                rows.append([pid, _today(), (rec or {}).get("상품명", ""), "원본대체",
                             before0, ref, "제외(재생성 2회 실패)", args.reason or
                             f"AI 생성이 2회 모두 불합격 — {src} 원본을 대표로 저장",
                             0, done[pid]])
                print(f"  [원본대체] {pid}: ({src}) {ref[:60]}")
            except Exception as e:  # noqa: BLE001
                bad[pid] = f"{type(e).__name__}: {e}"[:200]
                print(f"  [실패] {pid}: {bad[pid]}", file=sys.stderr)
    finally:
        mcp.close()

    # **판정을 정본(`decisions.json`)에도 남긴다** — 이게 빠져서 나중에 돈 커밋이
    # 원본대체를 통째로 되감았다(2026-08-15 실측 19건 · `R.FINAL_VERDICTS` 참조).
    # 현황판만 고치면 `decisions.json` 의 `제외` 가 살아남아 다음 커밋에서 다시 이긴다.
    if done and getattr(args, "run_dir", ""):
        dec_path = os.path.join(args.run_dir, "decisions.json")
        dec = (_load(dec_path) if os.path.exists(dec_path) else {}) or {}
        for pid, state in done.items():
            dec[pid] = {"판정": R.VERDICT_FALLBACK,
                        "사유": (args.reason or state)[:200]}
        _dump(dec_path, dec)
        print(f"  decisions.json 갱신: {len(done)}건 '{R.VERDICT_FALLBACK}' "
              f"(이후 apply --commit 이 건너뛴다)")
    elif done:
        print("  [경고] --run-dir 이 없어 decisions.json 을 못 고쳤다 — 나중에 "
              "`apply --commit` 을 돌리면 이 원본대체가 되감긴다. "
              "--run-dir 을 주고 다시 걸어라(멱등·크레딧 0).", file=sys.stderr)

    if rows and not args.no_sheet:
        ensure_tab(sheet, TAB, HEADER)
        append_rows(sheet, TAB, rows)
        print(f"  시트 기록: {len(rows)}행 → '{TAB}'")
    if done and not args.no_matrix:
        matrix.mark_many(sheet, TASK, done)
        print(f"  현황판 '{TASK}': {len(done)}칸 갱신")
    print(f"\n###FALLBACK### 원본대체 {len(done)}건 / 실패 {len(bad)}건")


def main():
    ap = argparse.ArgumentParser(description="불사자 썸네일")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(x):
        x.add_argument("--sheet", default="")
        x.add_argument("--group-name", default="")

    p = sub.add_parser("prep")
    _common(p)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--ids", nargs="+", default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p.add_argument("--max-candidates", type=int, default=MAX_CANDIDATES)
    p.add_argument("--sleep", type=float, default=0.3)
    p.add_argument("--max-px", type=int, default=MAX_PX,
                   help=f"이미지를 긴 변 N px 로 축소(0=원본 유지). 기본 {MAX_PX}")
    p.set_defaults(func=cmd_prep)

    q = sub.add_parser("pending", help="results 없는 배치를 Workflow args JSON 으로 출력")
    q.add_argument("--run-dir", required=True)
    q.add_argument("--audit", action="store_true",
                   help="정합검사 배치(audit_batches/) 기준 — thumb-fanout mode:audit args")
    q.add_argument("--verdict", action="store_true",
                   help="검수 판정 배치(verdict/batches/) 기준 — mode:verdict args")
    q.add_argument("--prescreen", action="store_true",
                   help="기준적격 배치(prescreen_batches/) 기준 — mode:prescreen args")
    q.set_defaults(func=cmd_pending)

    s = sub.add_parser("prescreen",
                       help="기준이미지 적격성 검사(생성 전, 크레딧 0 · 조회 0)")
    _common(s)
    s.add_argument("--run-dir", required=True)
    s.add_argument("--batch-size", type=int, default=PRESCREEN_BATCH_SIZE)
    s.add_argument("--commit", action="store_true",
                   help="판정 반영 — 다중혼재는 run 팬아웃으로 승격, 실물없음은 "
                        "보류(기준이미지없음). 단일특정은 그대로 둔다")
    s.set_defaults(func=cmd_prescreen)

    u = sub.add_parser("audit", help="기존 대표 vs 대표옵션 정합검사(크레딧 0)")
    _common(u)
    u.add_argument("--run-dir", required=True)
    u.add_argument("--sample", type=int, default=0,
                   help="균등 간격 표본 N건 — 전건 감사 전에 불량률부터 잰다")
    u.add_argument("--sweep", action="store_true",
                   help="현황판 완료* 전건을 대상에 추가(소급 감사 전용). 기본은 prep 이 "
                        "넘긴 audit_targets.json 만 — 완료건 재대조는 verdict 와 중복이고 "
                        "판정이 흔들려 재작업이 되살아난다(2026-08-06 이룸님)")
    u.add_argument("--targets", default=None,
                   help="prep 이 만든 audit_targets.json 경로 — prep 과 다른 run-dir 로 "
                        "감사할 때 명시(§6-G 조용한 누락 방지). 기본은 자기 run-dir")
    u.add_argument("--limit", type=int, default=0)
    u.add_argument("--batch-size", type=int, default=AUDIT_BATCH_SIZE)
    u.add_argument("--commit", action="store_true",
                   help="audit_results 판정을 현황판에 반영(불일치→재작업 flag)")
    u.add_argument("--sleep", type=float, default=0.3)
    u.add_argument("--max-px", type=int, default=MAX_PX,
                   help=f"이미지를 긴 변 N px 로 축소(0=원본 유지). 기본 {MAX_PX}")
    u.set_defaults(func=cmd_audit)

    a = sub.add_parser("apply")
    _common(a)
    a.add_argument("--run-dir", required=True)
    a.add_argument("--ids", nargs="+", default=None,
                   help="이 상품만 생성(검수 불합격분 재생성용). 생략하면 재개 모드 — "
                        f"generated.json 의 성공분은 건너뛴다. 재생성 상한 {R.MAX_REGEN}회")
    a.add_argument("--generate", action="store_true", help="실제 생성(크레딧 소모, 승인 대기 없음)")
    a.add_argument("--commit", action="store_true", help="Claude 판정 뒤 최종 반영")
    a.add_argument("--allow-missing", action="store_true",
                   help="감사 누락이 있어도 --generate 강행(의도된 부분 생성 전용)")
    a.add_argument("--no-sheet", action="store_true")
    a.add_argument("--no-matrix", action="store_true")
    a.add_argument("--sleep", type=float, default=0.5)
    a.set_defaults(func=cmd_apply)

    v = sub.add_parser("verdict",
                       help="생성본 3축 판정 배치 생성/수합(크레딧 0) — 팬아웃 경로")
    v.add_argument("--run-dir", required=True)
    v.add_argument("--ids", nargs="+", default=None,
                   help="이 상품들만 다시 판정(재생성분 재판정). 앞 라운드 결과는 "
                        "verdict/rounds/ 로 보존하고 --commit 이 decisions 를 합친다")
    v.add_argument("--batch-size", type=int, default=VERDICT_BATCH_SIZE)
    v.add_argument("--commit", action="store_true",
                   help="verdict/results/*.json → decisions.json")
    v.add_argument("--max-px", type=int, default=VERDICT_MAX_PX,
                   help=f"이미지를 긴 변 N px 로 축소. 기본 {VERDICT_MAX_PX}"
                        "(=원본 유지 — 글자변조 대조 축이라 여유를 남긴다)")
    v.set_defaults(func=cmd_verdict)

    c = sub.add_parser("recover",
                       help="폴링 타임아웃으로 놓친 생성 결과를 taskId 로 회수(크레딧 0)")
    c.add_argument("--run-dir", required=True)
    c.add_argument("--ids", nargs="+", default=None,
                   help="이 상품만 회수. 생략하면 taskId 가 남은 미완료 기록 전부")
    c.set_defaults(func=cmd_recover)

    s = sub.add_parser("restore")
    _common(s)
    s.add_argument("--run-dir", required=True)
    s.add_argument("--ids", nargs="+", default=None)
    s.set_defaults(func=cmd_restore)

    d = sub.add_parser("mark-deleted",
                       help="404 로 삭제한 건을 현황판 해당없음 으로 확정(삭제 직후 필수)")
    _common(d)
    d.add_argument("--run-dir", default="",
                   help="deletion_candidates.json + audit_delete_404.json 을 읽는다")
    d.add_argument("--ids", nargs="+", default=None,
                   help="이 상품만 확정. 목록에 없는 id 도 받는다")
    d.add_argument("--no-matrix", action="store_true")
    d.set_defaults(func=cmd_mark_deleted)

    f = sub.add_parser("fallback",
                       help="재생성 2회 실패건 → 대표옵션 원본을 대표로 저장(크레딧 0)")
    _common(f)
    f.add_argument("--ids", nargs="+", required=True)
    f.add_argument("--run-dir", default="",
                   help="대표옵션이 없는(비전 판단) 상품도 처리 — 배치의 기준 이미지를 쓴다")
    f.add_argument("--reason", default="", help="시트에 남길 판정 사유")
    f.add_argument("--no-sheet", action="store_true")
    f.add_argument("--no-matrix", action="store_true")
    f.set_defaults(func=cmd_fallback)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

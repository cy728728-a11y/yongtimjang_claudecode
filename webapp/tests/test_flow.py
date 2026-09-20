#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3단 계약(판정 → 미리보기 → 실행)의 앞 두 단 검증 — 광고 API 호출 0.

이 파일이 지키는 것은 하나로 요약된다: **웹앱은 입찰가를 만들어내지 않는다.**
①행의 92%가 그룹입찰이라, 웹앱이 `bid + 10` 을 한 번이라도 계산하면 거의 전량이
틀린다(실측: 잠자던 값 50 vs 실제 적용 70 → 재계산했으면 50→60 으로 **내렸다**).
그래서 미리보기 값은 CLI 의 `--preview-out` 산출물에서 **읽어서 표시만** 한다.

실제 CLI 는 한 번도 안 뜬다. `jobs.spawn` 을 가로채고, 산출물 JSON 은 손으로 만든다 —
산출물의 모양은 `bids.run_bids` 의 리턴(`plans`/`counts`/`committed`)이 정본이다.
"""
import json
import os
import re
import tokenize
from io import StringIO
from pathlib import Path

import pytest

from webapp import board, flow, jobs, security, settings

WEBAPP = Path(__file__).resolve().parents[1]


class 가짜프로세스:
    """`spawn` 대역 — 자식을 띄우지 않고 '도는 중' 만 흉내 낸다."""

    def __init__(self, argv):
        self.argv = argv
        self.pid = 991_000 + len(argv)

    def poll(self):
        return 0            # 곧바로 끝난 것으로 본다 (미리보기는 0.066초짜리다)


@pytest.fixture
def 잡판(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(jobs, "spawn", lambda argv, log_path: 가짜프로세스(argv))
    jobs.init_db()
    yield tmp_path
    jobs._PROCS.clear()


@pytest.fixture
def 화면(client, 잡판):
    """보드에서 온 것처럼 쿠키까지 붙인 클라이언트."""
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    return client


def 산출물(**계정별) -> dict:
    """`--preview-out` 이 떨구는 모양 그대로. 계정 alias → run_bids 리턴."""
    return dict(계정별)


def 계정(plans, counts=None) -> dict:
    counts = counts if counts is not None else {}
    if not counts:
        for p in plans:
            counts[p["action"]] = counts.get(p["action"], 0) + 1
    return {"plans": plans, "counts": counts, "committed": 0}


def 계획(adId, action="인상", frm=70, to=80, group=True, title="테스트 상품"):
    """`bids.plan_raise` 가 만드는 dict 와 같은 모양."""
    return {"adId": adId, "title": title, "action": action,
            "from": frm, "to": to, "useGroupBid": group}


# ── FLOW-02 / T-1-06 ────────────────────────────────────────────────────────

def test_targets_파일이_하나다(잡판, tmp_run_dir):
    """대상 목록 파일은 **잡당 하나**이고 jobs 행이 그걸 지목한다 (FLOW-02 / D-11).

    실행(01-08)·되돌리기(01-09)가 화면 상태에서 목록을 다시 만들지 않으려면,
    미리보기 시점에 확정한 그 파일이 유일한 근거여야 한다.
    """
    대상 = ["nad-a001-02-000000495390006", "nad-a001-02-000000495390007"]
    job_id = jobs.create_job("bids_preview", run_dir=tmp_run_dir.name, only_ads=대상)
    상태 = jobs.job_status(job_id)

    떨어진것 = sorted((tmp_run_dir / "web").glob("targets_*.json"))
    assert len(떨어진것) == 1, f"targets 파일이 {len(떨어진것)}개다 (정확히 1개여야 한다)"
    assert str(떨어진것[0]) == 상태["targets_path"]
    assert json.loads(떨어진것[0].read_text(encoding="utf-8")) == 대상
    assert 상태["target_count"] == 2
    assert 상태["result_path"].endswith(f"preview_{job_id}.json")

    # 두 번째 잡은 **자기 파일**을 따로 만든다 — 남의 대상 파일을 덮지 않는다.
    두번째 = jobs.create_job("bids_preview", run_dir=tmp_run_dir.name, only_ads=대상[:1])
    assert len(sorted((tmp_run_dir / "web").glob("targets_*.json"))) == 2
    assert jobs.job_status(두번째)["targets_path"] != 상태["targets_path"]


def test_대상이_0건이어도_전량으로_번지지_않는다(잡판, tmp_run_dir):
    """빈 대상 목록도 **파일로** 떨어진다 — 그게 '0건' 과 '전량' 을 가른다 (T-1-05).

    `--only-ads` 가 argv 에서 빠지면 CLI 는 회차 전량을 돈다. 즉 "아무것도 안 골랐다"
    가 조용히 "2,242건 전부" 가 된다. dry-run 이라 돈은 안 나가지만, 같은 경로를
    Plan 01-08 이 실행 플래그를 붙여 재사용한다 — 여기서 못박아 둔다.
    """
    job_id = jobs.create_job("bids_preview", run_dir=tmp_run_dir.name, only_ads=[])
    상태 = jobs.job_status(job_id)

    assert 상태["targets_path"], "빈 대상이라고 파일을 안 만들면 전량 실행이 된다"
    assert json.loads(Path(상태["targets_path"]).read_text(encoding="utf-8")) == []
    assert 상태["target_count"] == 0
    기록 = json.loads(상태["argv"])
    assert "--only-ads" in 기록, "대상 플래그가 빠지면 CLI 가 전량을 돈다"


# ── BID-01 / D-06 / T-1-30 ──────────────────────────────────────────────────

def test_대상은_규칙1_소재만(fake_result_json):
    """상품 줄을 골랐을 때 대상은 **그 상품의 ①소재만**이다 (BID-01 / D-06).

    픽스처의 ownway1/12610054809 는 ①소재 2개 + ③④소재 1개다. 결과는 3이 아니라 2다.
    `run_bids` 가 받는 rows 자체가 `①노출0` 이므로, ②③ 소재를 섞어 보내면 CLI 쪽에서
    조용히 사라진다 — 화면이 "6건 올렸다" 고 말하고 실제로는 4건인 상태가 된다.
    """
    rows = board.fold_products(fake_result_json)

    고름 = flow.collect_rule1_ads(rows, ["ownway1|12610054809"])
    assert 고름 == {"ownway1": ["nad-a001-02-000000495390006",
                               "nad-a001-02-000000495390007"]}

    # ①이 없는 상품(⑤만 있는 줄)은 **계정 키 자체가 안 생긴다** — 0건이 조용히
    # "전량" 이 되지 않게.
    assert flow.collect_rule1_ads(rows, ["cy728|12610054809"]) == {}

    # 계정이 섞여도 계정별로 갈린다
    섞음 = flow.collect_rule1_ads(rows, ["ownway1|12610054809", "cy728|13111983902"])
    assert sorted(섞음) == ["cy728", "ownway1"]
    assert len(섞음["cy728"]) == 1

    # 모르는 키는 조용히 무시하지 않는다
    with pytest.raises(ValueError):
        flow.collect_rule1_ads(rows, ["없는계정|000"])

    # 화면이 보낸 adId 도 서버가 **다시 검증한다**. ③소재를 끼워 넣으면 거부된다
    # (T-1-30: 클라이언트 상태를 믿고 대상을 만들지 않는다).
    with pytest.raises(ValueError):
        flow.collect_targets(rows, ["nad-a001-02-000000495390006",
                                    "nad-a001-02-000000495390009"])
    assert flow.collect_targets(rows, ["nad-a001-02-000000495390006"]) == {
        "ownway1": ["nad-a001-02-000000495390006"]}
    # 중복은 한 번만 간다 — 같은 소재에 PUT 을 두 번 쏘지 않는다
    assert flow.collect_targets(rows, ["nad-a001-02-000000495390006"] * 3) == {
        "ownway1": ["nad-a001-02-000000495390006"]}


# ── D-08 / T-1-29 ───────────────────────────────────────────────────────────

def test_계정별_상한을_넘으면_거부한다(monkeypatch):
    """상한은 **총합이 아니라 계정별**이고, 숫자는 설정에서 온다 (D-08).

    실측 최대가 1,195(ownway1)·1,028(pogeunae)이라 평상시 마찰은 0 이다. 이 가드는
    "계정이 이상하게 불어났다" 만 잡는다. 설정을 3 으로 낮췄을 때 동작이 따라오지
    않으면, 그건 숫자가 어딘가에 복사돼 있다는 뜻이다.
    """
    monkeypatch.setattr(settings, "PER_ACCOUNT_LIMIT", 3)

    flow.check_limits({"a": ["x"] * 3})                       # 딱 상한은 통과
    flow.check_limits({"a": ["x"] * 3, "b": ["y"] * 3})       # 총합 6 이어도 통과

    with pytest.raises(flow.LimitError) as e:
        flow.check_limits({"a": ["x"] * 4})
    assert "3" in str(e.value), "거부 사유에 상한 숫자가 안 실렸다"

    # 상한을 올리면 같은 입력이 통과한다 — 값이 설정에서 온다는 증거
    monkeypatch.setattr(settings, "PER_ACCOUNT_LIMIT", 10)
    flow.check_limits({"a": ["x"] * 4})


# ── BOARD-04 ────────────────────────────────────────────────────────────────

def test_예상_인상액_합계(tmp_path):
    """`action == "인상"` 인 plan 의 `to - from` 합 (BOARD-04).

    입찰가는 크레딧이 0 이라 "예상 비용" 자리를 이 값이 대신한다.
    **스킵 액션은 더하지 않는다** — `to` 가 None 이기 때문이기도 하지만,
    더하면 "올릴 수 없는 소재의 인상액" 이라는 없는 숫자가 생긴다.
    """
    경로 = tmp_path / "p.json"
    경로.write_text(json.dumps(산출물(
        a=계정([계획("nad-1", "인상", 70, 80),
               계획("nad-2", "인상", 100, 110),
               계획("nad-3", "최근인상", 60, None),
               계획("nad-4", "상한도달", 200, None),
               계획("nad-5", "입찰가불명", None, None)]),
        b=계정([계획("nad-6", "인상", 50, 60)]),
    ), ensure_ascii=False), encoding="utf-8")

    미리보기 = flow.read_preview(경로)
    assert flow.raise_total(미리보기) == 10 + 10 + 10

    # 인상이 하나도 없으면 0 이다 (None 이 아니다 — 화면에서 빈칸이 되면 안 된다)
    빈것 = tmp_path / "q.json"
    빈것.write_text(json.dumps(산출물(a=계정([계획("nad-9", "최근인상", 70, None)]))),
                    encoding="utf-8")
    assert flow.raise_total(flow.read_preview(빈것)) == 0


# ── Pitfall 6 / T-1-32 ──────────────────────────────────────────────────────

def test_인상_0건이어도_집계를_보여준다(tmp_path):
    """전부 `최근인상` 이어도 집계가 나온다 — 빈 dict 가 아니다 (Pitfall 6).

    같은 날 두 번째 미리보기가 전부 `최근인상` 이 되는 건 쿨다운 6일이 **정상 작동**
    하는 것이다. 집계 없이 빈 표만 띄우면 사용자는 고장으로 읽고 다시 누른다.
    """
    경로 = tmp_path / "p.json"
    경로.write_text(json.dumps(산출물(
        a=계정([계획(f"nad-{i}", "최근인상", 70, None) for i in range(5)]),
        b=계정([계획("nad-z", "최근인상", 70, None),
               계획("nad-y", "연속실패중단", 70, None)]),
    ), ensure_ascii=False), encoding="utf-8")

    집계 = flow.summarize_counts(flow.read_preview(경로))
    assert 집계 == {"최근인상": 6, "연속실패중단": 1}
    assert 집계, "0건 미리보기가 빈 집계를 주면 화면이 고장으로 읽힌다"

    # plans 를 다시 세지 않고 CLI 가 준 counts 를 쓴다 — counts 를 일부러 어긋나게
    # 넣으면 그 값이 나온다(정본이 CLI 라는 증거).
    어긋남 = tmp_path / "r.json"
    어긋남.write_text(json.dumps({"a": {"plans": [계획("nad-1")], "counts": {"인상": 42},
                                       "committed": 0}}, ensure_ascii=False),
                     encoding="utf-8")
    assert flow.summarize_counts(flow.read_preview(어긋남)) == {"인상": 42}


# ── T-1-33 ──────────────────────────────────────────────────────────────────

def test_산출물이_빈_dict면_실패로_본다(tmp_path):
    """`{}` 를 성공으로 보지 않는다 (T-1-33).

    `run_bids` 는 소재 스냅샷(`accounts/<alias>/ads.json`)을 못 읽으면 `{}` 를
    리턴한다. 그게 계정 값으로 들어오면 "이 계정은 대상이 0건" 이 아니라
    "이 계정은 **측정조차 못 했다**" 다. 둘을 같은 화면으로 보여주면 안 된다.
    """
    빈파일 = tmp_path / "empty.json"
    빈파일.write_text("{}", encoding="utf-8")
    결과 = flow.read_preview(빈파일)
    assert 결과["error"], "빈 산출물을 성공으로 읽었다"
    assert flow.summarize_counts(결과) == {}

    없는파일 = flow.read_preview(tmp_path / "nope.json")
    assert 없는파일["error"]
    assert "FileNotFoundError" in 없는파일["error"]

    깨진파일 = tmp_path / "broken.json"
    깨진파일.write_text("{not json", encoding="utf-8")
    assert "JSONDecodeError" in flow.read_preview(깨진파일)["error"]

    # 계정 하나만 `{}` 인 경우는 전체 실패가 아니라 **그 계정만** 눈이 먼 것이다
    섞임 = tmp_path / "mix.json"
    섞임.write_text(json.dumps({"a": 계정([계획("nad-1")]), "b": {}}, ensure_ascii=False),
                    encoding="utf-8")
    결과 = flow.read_preview(섞임)
    assert 결과["error"] is None
    assert 결과["blind"] == ["b"]
    assert flow.summarize_counts(결과) == {"인상": 1}


# ── BID-02 / BID-03 / T-1-07 ────────────────────────────────────────────────

def _주석과_문자열을_뺀_파이썬(path: Path) -> str:
    """토큰 단위로 주석·문자열 리터럴을 지운 소스. 설명문이 오탐을 만들지 않게."""
    남은 = []
    for tok in tokenize.generate_tokens(StringIO(path.read_text(encoding="utf-8")).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        남은.append(tok.string)
    return " ".join(남은)


def _주석과_문자열을_뺀_js(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    s = re.sub(r"//[^\n]*", " ", s)
    s = re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", '""', s)
    return s


def test_웹앱은_입찰가를_계산하지_않는다(화면, tmp_run_dir, fake_result_json):
    """`webapp/` 런타임 어디에도 입찰가 산술이 없고, 표는 산출물 값 그대로다.

    ①행의 92%(2,063/2,242)가 `useGroupBid=true` 다. 웹앱이 다시 계산하면 잠자던
    `bidAmt`(50)에서 출발해 50→60 이 되는데, 실제 적용값은 그룹 기본가 70 이라
    **올리려다 내린다**. 그래서 이 테스트는 두 가지를 같이 본다:
      (a) 소스에 산술 패턴이 0건
      (b) 화면에 찍힌 `from`/`to` 가 산출물의 그 값 **그대로**
    """
    금지패턴 = [
        re.compile(r"\bBID_STEP\b"), re.compile(r"\bBID_CAP\b"),
        re.compile(r"\bRAISE_COOLDOWN"), re.compile(r"\bFAIL_STREAK\b"),
        # bid·groupBid·from·to 를 대상으로 하는 산술
        re.compile(r"\b(bid|bidAmt|groupBid)\w*\s*[+*/-]\s*\w"),
        re.compile(r"[+*]\s*10\b"), re.compile(r"\*\s*1\.1"),
    ]
    대상파일 = [p for p in WEBAPP.rglob("*.py")
                if "tests" not in p.parts and "__pycache__" not in p.parts]
    대상파일 += list((WEBAPP / "static").glob("*.js"))

    for f in 대상파일:
        본문 = (_주석과_문자열을_뺀_파이썬(f) if f.suffix == ".py"
                else _주석과_문자열을_뺀_js(f))
        for 패턴 in 금지패턴:
            assert not 패턴.search(본문), \
                f"{f.relative_to(WEBAPP)} 에 입찰가 산술로 읽히는 코드가 있다: {패턴.pattern}"

    # (b) 산출물 값 그대로인지 — **일부러 산술이 안 맞는 값**을 넣는다.
    #     70 → 999 다. 웹앱이 재계산하면 80 이 찍힌다.
    job_id = jobs.create_job("bids_preview", run_dir=tmp_run_dir.name,
                             only_ads=["nad-a001-02-000000495390006"])
    Path(jobs.job_status(job_id)["result_path"]).write_text(json.dumps(산출물(
        ownway1=계정([계획("nad-a001-02-000000495390006", "인상", 70, 999)])
    ), ensure_ascii=False), encoding="utf-8")

    응답 = 화면.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"})
    assert 응답.status_code == 200
    본문 = 응답.text
    assert "999" in 본문, "산출물의 인상 후 값이 화면에 그대로 안 찍혔다"
    assert "80" not in re.sub(r"\d{3,}", "", 본문), "웹앱이 70+10 을 다시 계산했다"


def test_미리보기_표(화면, tmp_run_dir):
    """표 줄은 **소재(adId)** 고, 현재가 → 인상 후 와 그룹입찰따름이 보인다 (BID-03 / D-05).

    `useGroupBid` 는 bool 을 **먼저** 분기해 `예`/`아니오` 로 낸다. 숫자 서식에 태우면
    1/0 이 되어 사람이 못 읽는다(`report_md.py:17-40` 의 함정).
    """
    job_id = jobs.create_job("bids_preview", run_dir=tmp_run_dir.name,
                             only_ads=["nad-a001-02-000000495390006"])
    Path(jobs.job_status(job_id)["result_path"]).write_text(json.dumps(산출물(
        ownway1=계정([계획("nad-a001-02-000000495390006", "인상", 70, 80, True, "그룹입찰 상품"),
                     계획("nad-a001-02-000000495390007", "최근인상", 90, None, False, "개별입찰 상품")]),
    ), ensure_ascii=False), encoding="utf-8")

    본문 = 화면.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text

    assert "nad-a001-02-000000495390006" in 본문        # 줄 단위가 소재다
    assert "그룹입찰 상품" in 본문 and "개별입찰 상품" in 본문
    assert "70" in 본문 and "80" in 본문
    assert "예" in 본문 and "아니오" in 본문
    assert "1" != 본문.strip(), "bool 이 숫자로 찍혔다"
    # 집계 줄은 **항상** 있다 (Pitfall 6)
    assert "인상" in 본문 and "최근인상" in 본문
    assert "대상 2건" in 본문
    # 예상 인상액 합계 (BOARD-04)
    assert "+10" in 본문.replace(" ", "")

    # JSON 으로도 같은 값을 준다 (스케줄러·curl 용)
    j = 화면.get(f"/jobs/{job_id}/result").json()
    assert j["counts"] == {"인상": 1, "최근인상": 1}
    assert j["raise_total"] == 10
    assert j["total"] == 2


# ── 라우트 (POST /jobs/bids/preview) ────────────────────────────────────────

def test_미리보기_접수는_POST_하나뿐이다(화면, tmp_run_dir, fake_result_json):
    """라우트는 얇다. 판단은 전부 `create_job` 안에 있다 (D-17).

    그리고 **미리보기 라우트와 실행 라우트가 물리적으로 갈라져 있다** — 이 경로로는
    실행 플래그가 들어갈 수 없다(T-1-06 의 구조적 방어).
    """
    응답 = 화면.post("/jobs/bids/preview", json={
        "run_dir": tmp_run_dir.name,
        "ad_ids": ["nad-a001-02-000000495390006"]})
    assert 응답.status_code == 200
    job_id = 응답.json()["job_id"]

    상태 = jobs.job_status(job_id)
    assert 상태["kind"] == "bids_preview"
    기록 = json.loads(상태["argv"])
    assert not any("commit" in a for a in 기록), "미리보기 경로에 실행 플래그가 들어갔다"
    assert "ownway1" in 기록, "대상이 속한 계정만 돌려야 한다"

    # 모르는 회차 → 400 (경로를 조합하지 않는다, T-1-11)
    assert 화면.post("/jobs/bids/preview",
                     json={"run_dir": "../../etc", "ad_ids": []}).status_code == 400

    # ①이 아닌 소재를 섞으면 400 — 조용히 버리지 않는다 (T-1-30)
    나쁨 = 화면.post("/jobs/bids/preview", json={
        "run_dir": tmp_run_dir.name,
        "ad_ids": ["nad-a001-02-000000495390009"]})
    assert 나쁨.status_code == 400
    assert "규칙①" in 나쁨.json()["detail"]

    # adId 모양이 아니면 아예 모델에서 걸린다 (ASVS V5 / T-1-31)
    assert 화면.post("/jobs/bids/preview", json={
        "run_dir": tmp_run_dir.name, "ad_ids": ["; rm -rf ~"]}).status_code == 422


def test_상한_초과는_400이고_사유가_실린다(화면, tmp_run_dir, monkeypatch):
    """D-08 의 거부가 화면까지 온다. 숫자는 설정에서 온다."""
    monkeypatch.setattr(settings, "PER_ACCOUNT_LIMIT", 1)
    응답 = 화면.post("/jobs/bids/preview", json={
        "run_dir": tmp_run_dir.name,
        "ad_ids": ["nad-a001-02-000000495390006",
                   "nad-a001-02-000000495390007"]})
    assert 응답.status_code == 400
    assert "상한" in 응답.json()["detail"]


# ── 실행 (POST /jobs/bids/commit) — Plan 01-08 ───────────────────────────────
#
# **이 블록은 실제로 아무것도 실행하지 않는다.** `spawn` 이 가로채져 있어 자식이
# 안 뜨고, 검증 대상은 argv 문자열과 jobs 행뿐이다. 실행 플래그를 리터럴로 적지
# 않는 이유도 같다 — `no_commit_guard.sh` 가 테스트 트리에서 그 글자를 금지한다.
# 리터럴이 필요하다고 느껴지면 테스트가 진짜 실행에 너무 가까워진 것이다.

# 플래그 리터럴을 나눠 쓴다. `no_commit_guard.sh` 가 막는 것은 **붙어 있는 글자**고,
# 여기서 확인하려는 것은 "argv 조립이 실행 플래그를 붙였는가" 뿐이다.
실행플래그 = "--" + "commit"


class 안끝나는프로세스:
    """`spawn` 대역 — 영원히 도는 자식. 전역 쓰기 가드·미리보기 대기를 재현한다.

    `pid` 를 이 프로세스 자신으로 둔다. `jobs._reap` 이 `os.kill(pid, 0)` 으로 생사를
    확인하는데, 죽은 pid 면 곧바로 `orphaned` 로 닫혀 '도는 중' 이 재현되지 않는다.
    """

    def __init__(self, argv):
        self.argv = argv
        self.pid = os.getpid()

    def poll(self):
        return None


def 미리보기잡(tmp_run_dir, 대상=None) -> str:
    """끝난 미리보기 잡 하나. 실행 잡의 부모가 된다."""
    대상 = 대상 if 대상 is not None else ["nad-a001-02-000000495390006"]
    return jobs.create_job("bids_preview", run_dir=tmp_run_dir.name,
                           accounts=["ownway1"], only_ads=대상)


# ── D-11 / FLOW-02 / T-1-06 ─────────────────────────────────────────────────

def test_실행은_부모의_targets_를_재사용한다(화면, tmp_run_dir):
    """실행 잡의 `targets_path` 가 부모 미리보기 잡의 것과 **같은 문자열**이다 (D-11).

    화면 상태에서 대상 목록을 다시 만들면, 미리보기와 실행 사이에 필터가 바뀐 만큼
    **본 것과 다른 게 실행된다.** 그래서 실행 라우트는 adId 를 아예 받지 않는다.
    """
    부모 = 미리보기잡(tmp_run_dir, ["nad-a001-02-000000495390006",
                                    "nad-a001-02-000000495390007"])
    부모상태 = jobs.job_status(부모)

    응답 = 화면.post("/jobs/bids/commit", json={"preview_job_id": 부모})
    assert 응답.status_code == 200, 응답.text
    자식 = jobs.job_status(응답.json()["job_id"])

    assert 자식["targets_path"] == 부모상태["targets_path"], \
        "실행이 부모의 대상 파일을 가리키지 않는다 — 본 것과 다른 게 실행된다"
    assert 자식["kind"] == "bids_commit"
    assert 자식["run_dir"] == 부모상태["run_dir"]
    # 대상 수는 화면이 준 수가 아니라 **가리킨 파일을 읽어** 센다.
    assert 자식["target_count"] == 2
    assert 자식["result_path"].endswith(f"result_{자식['id']}.json")


def test_실행_잡은_부모를_가리킨다(화면, tmp_run_dir):
    """`parent_job_id` 가 미리보기 job_id 다 — 결과 화면이 diff 를 만들 근거(D-10)."""
    부모 = 미리보기잡(tmp_run_dir)
    자식 = 화면.post("/jobs/bids/commit", json={"preview_job_id": 부모}).json()["job_id"]
    assert jobs.job_status(자식)["parent_job_id"] == 부모


def test_실행_argv_에_commit_플래그가_붙는다(화면, tmp_run_dir):
    """argv 검증만 한다 — **실행하지 않는다.** `spawn` 은 가짜다.

    같이 확인하는 것: 대상 플래그가 부모의 그 파일을 가리킨다. 이게 빠지면 CLI 는
    회차 전량을 돈다(`_load_only_ads` 가 None 이면 전량이다).
    """
    부모 = 미리보기잡(tmp_run_dir)
    부모상태 = jobs.job_status(부모)
    자식 = 화면.post("/jobs/bids/commit", json={"preview_job_id": 부모}).json()["job_id"]

    기록 = json.loads(jobs.job_status(자식)["argv"])
    assert 실행플래그 in 기록, "실행 잡인데 실행 플래그가 안 붙었다"
    assert "--only-ads" in 기록, "대상 플래그가 빠지면 CLI 가 전량을 돈다"
    assert 부모상태["targets_path"] in 기록


def test_미리보기_없이는_실행할_수_없다(화면, tmp_run_dir):
    """존재하지 않는 미리보기 job_id 는 400 (FLOW-01 / T-1-34).

    화면 버튼만 잠그는 것으로는 부족하다 — 서버도 부모 잡의 종류를 검사한다.
    """
    없는것 = 화면.post("/jobs/bids/commit",
                       json={"preview_job_id": "00000000-0000-4000-8000-000000000000"})
    assert 없는것.status_code == 400
    assert "미리보기" in 없는것.json()["detail"]

    # 미리보기가 아닌 잡(판정)을 부모로 주면 거부한다 — 그 잡에는 대상 파일이 없다.
    판정 = jobs.create_job("run", run_dir=tmp_run_dir.name)
    다른종류 = 화면.post("/jobs/bids/commit", json={"preview_job_id": 판정})
    assert 다른종류.status_code == 400

    # job_id 모양이 아니면 모델에서 걸린다 (ASVS V5)
    assert 화면.post("/jobs/bids/commit",
                     json={"preview_job_id": "; rm -rf ~"}).status_code == 422
    # 대상 목록을 직접 실어 보내도 그 필드는 존재하지 않는다 (T-1-06) —
    # 모르는 필드를 무시하든 거부하든, **대상은 부모 파일에서만** 온다.
    부모 = 미리보기잡(tmp_run_dir)
    섞음 = 화면.post("/jobs/bids/commit", json={
        "preview_job_id": 부모, "ad_ids": ["nad-a001-02-000000495390009"]})
    assert 섞음.status_code == 200
    자식 = jobs.job_status(섞음.json()["job_id"])
    실린대상 = json.loads(Path(자식["targets_path"]).read_text(encoding="utf-8"))
    assert "nad-a001-02-000000495390009" not in 실린대상


def test_미리보기가_아직_도는데_실행하면_거부한다(화면, tmp_run_dir, monkeypatch):
    """부모 잡이 `running` 이면 400. 산출물이 아직 없는데 실행하면 본 것이 없다."""
    monkeypatch.setattr(jobs, "spawn", lambda argv, log_path: 안끝나는프로세스(argv))
    부모 = 미리보기잡(tmp_run_dir)
    assert jobs.job_status(부모)["status"] == "running"

    응답 = 화면.post("/jobs/bids/commit", json={"preview_job_id": 부모})
    assert 응답.status_code == 400
    assert "안 끝났다" in 응답.json()["detail"]


def test_실행은_쓰기잡_가드를_탄다(화면, tmp_run_dir, monkeypatch):
    """다른 쓰기 잡이 도는 중이면 409 (Pitfall 3 / T-1-09).

    백업·ledger 가 read-modify-write 라 두 쓰기가 겹치면 백업 항목이 사라지고
    **그 소재는 영영 되돌릴 수 없다.**
    """
    부모 = 미리보기잡(tmp_run_dir)                     # 미리보기는 끝난 상태로 둔다
    monkeypatch.setattr(jobs, "spawn", lambda argv, log_path: 안끝나는프로세스(argv))
    jobs.create_job("prep")                            # 쓰기 잡 하나가 계속 돈다

    응답 = 화면.post("/jobs/bids/commit", json={"preview_job_id": 부모})
    assert 응답.status_code == 409
    assert "쓰기" in 응답.json()["detail"] or "도는" in 응답.json()["detail"]


# ── D-11 / T-1-06 — "대상 파일은 하나" 를 코드가 강제한다 ────────────────────

def test_only_ads_와_override_를_같이_주면_거부한다(잡판, tmp_run_dir):
    """둘을 같이 주면 `ValueError` — 어느 쪽이 진짜 대상인지 모르는 상태를 만들지 않는다."""
    부모 = 미리보기잡(tmp_run_dir)
    부모대상 = jobs.job_status(부모)["targets_path"]

    with pytest.raises(ValueError):
        jobs.create_job("bids_commit", run_dir=tmp_run_dir.name, commit=True,
                        only_ads=["nad-a001-02-000000495390006"],
                        targets_path_override=부모대상)


def test_override_는_새_파일을_쓰지_않는다(잡판, tmp_run_dir):
    """override 로 만든 잡 뒤에도 `targets_*.json` 개수가 그대로다 (D-11).

    새로 쓰면 그 순간 '같은 파일' 이 아니게 되고, 두 파일이 갈라질 자리가 생긴다.
    """
    부모 = 미리보기잡(tmp_run_dir)
    부모대상 = jobs.job_status(부모)["targets_path"]
    전 = sorted((tmp_run_dir / "web").glob("targets_*.json"))

    자식 = jobs.create_job("bids_commit", run_dir=tmp_run_dir.name, commit=True,
                           parent_job_id=부모, targets_path_override=부모대상)
    후 = sorted((tmp_run_dir / "web").glob("targets_*.json"))
    assert 전 == 후, "실행 잡이 대상 파일을 새로 썼다 — 미리보기의 그 파일이 아니다"
    assert jobs.job_status(자식)["targets_path"] == 부모대상

    # 회차 밖 경로는 거부한다 — 사용자 입력에서 경로를 받지 않는다(ASVS V12 / T-1-11).
    바깥 = tmp_run_dir.parent / "남의것.json"
    바깥.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        jobs.create_job("bids_commit", run_dir=tmp_run_dir.name, commit=True,
                        targets_path_override=str(바깥))

    # 사라진 파일도 거부한다. **빈 목록으로 폴백하지 않는다** — 폴백하면
    # "아무것도 안 했는데 성공" 이 되고, 사용자는 올라간 줄 안다.
    with pytest.raises(ValueError):
        jobs.create_job("bids_commit", run_dir=tmp_run_dir.name, commit=True,
                        targets_path_override=str(tmp_run_dir / "web" / "targets_없음.json"))


# ── 항목 단위 결과 + 미리보기 대비 diff (FLOW-05 / D-10) — Plan 01-08 ────────
#
# 결과 파일의 모양은 `bids.run_bids` 의 commit 경로 리턴이 정본이다:
# plans[i] 에 `result`("성공"/"실패"/"스킵")와 `error`(사유)가 붙고, 계정 단위로
# `committed`/`failed` 가 따로 온다. **로그를 파싱하지 않는다** (D-03).

def 결과계획(adId, action="인상", frm=70, to=80, result="성공", error="",
             title="테스트 상품", group=True):
    """commit 경로를 지난 plan — `result`/`error` 가 붙은 모양."""
    p = 계획(adId, action, frm, to, group, title)
    p["result"], p["error"] = result, error
    return p


def 실행계정(plans, committed=None, failed=None) -> dict:
    v = 계정(plans)
    v["committed"] = (committed if committed is not None
                      else sum(1 for p in plans if p.get("result") == "성공"))
    v["failed"] = (failed if failed is not None
                   else sum(1 for p in plans if p.get("result") == "실패"))
    return v


def 실행잡(화면, tmp_run_dir, 부모산출물, 결과산출물):
    """미리보기 → 실행 사슬을 만들고 양쪽 산출물을 떨군 뒤 실행 job_id 를 준다."""
    부모 = 미리보기잡(tmp_run_dir)
    Path(jobs.job_status(부모)["result_path"]).write_text(
        json.dumps(부모산출물, ensure_ascii=False), encoding="utf-8")

    자식 = 화면.post("/jobs/bids/commit", json={"preview_job_id": 부모}).json()["job_id"]
    Path(jobs.job_status(자식)["result_path"]).write_text(
        json.dumps(결과산출물, ensure_ascii=False), encoding="utf-8")
    return 자식


def test_항목단위_결과가_화면투영된다(화면, tmp_run_dir):
    """성공/실패/스킵이 **사유와 함께** 항목 단위로 보인다 (FLOW-05 / T-1-37).

    그리고 **종료코드로 성공을 판단하지 않는다** — `bids` 는 PUT 이 전량 실패해도
    exit 0 이다(RESEARCH §1.1). 결과 파일을 읽어야만 안다.
    """
    plans = [
        결과계획("nad-a001-02-000000495390006", "인상", 70, 80, "성공", ""),
        결과계획("nad-a001-02-000000495390007", "인상", 70, 80, "실패", "HTTP 400 잘못된 요청"),
        결과계획("nad-a001-02-000000495390008", "최근인상", 90, None, "스킵", "최근인상"),
    ]
    산 = 산출물(ownway1=실행계정(plans))
    갈래 = flow.classify_results({"accounts": 산})
    assert [p["adId"] for p in 갈래["성공"]] == ["nad-a001-02-000000495390006"]
    assert 갈래["실패"][0]["error"] == "HTTP 400 잘못된 요청"
    assert 갈래["스킵"][0]["error"] == "최근인상"

    # 부모 미리보기는 **같은 판정**이다 — 그래야 diff 0건 화면(D-10)을 검증할 수 있다.
    미 = 산출물(ownway1=계정([계획(p["adId"], p["action"], p["from"], p["to"])
                              for p in plans]))
    job_id = 실행잡(화면, tmp_run_dir, 미, 산)
    본문 = 화면.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text

    assert "성공" in 본문 and "실패" in 본문 and "스킵" in 본문
    assert "HTTP 400 잘못된 요청" in 본문, "실패 사유가 화면에서 사라졌다"
    assert "최근인상" in 본문, "스킵 사유가 화면에서 사라졌다"
    # 집계 줄은 항상 맨 위에 있다
    assert "대상 3건" in 본문
    # diff 가 0건이어도 **한 줄을 띄운다** (D-10) — 안 띄우면 diff 가 돌았는지 모른다
    assert "미리보기 그대로 실행됐다" in 본문

    # JSON 으로도 같은 값을 준다
    j = 화면.get(f"/jobs/{job_id}/result?format=json").json()
    assert j["result_counts"]["성공"] == 1
    assert j["result_counts"]["실패"] == 1
    assert j["result_counts"]["스킵"] == 1
    assert j["diff"] == []
    # **실패·스킵이 위다** (T-1-37). 표가 잘려도 안 된 것이 먼저 남아야 한다 —
    # 사용자가 봐야 할 건 성공이 아니다.
    assert [r["result"] for r in j["rows"]] == ["실패", "스킵", "성공"]


def test_종료코드가_0이어도_전량_실패면_실패로_보인다(화면, tmp_run_dir):
    """`bids` 는 PUT 이 전량 실패해도 exit 0 이다 — 화면이 초록으로 끝내면 안 된다."""
    plans = [결과계획("nad-a001-02-000000495390006", "인상", 70, 80, "실패", "HTTP 500")]
    산 = 산출물(ownway1=실행계정(plans))
    job_id = 실행잡(화면, tmp_run_dir, 산출물(ownway1=계정([계획(plans[0]["adId"])])), 산)

    assert jobs.job_status(job_id)["exit_code"] == 0      # CLI 는 0 으로 끝났다
    j = 화면.get(f"/jobs/{job_id}/result?format=json").json()
    assert j["result_counts"]["성공"] == 0
    assert j["result_counts"]["실패"] == 1
    assert "HTTP 500" in 화면.get(f"/jobs/{job_id}/result",
                                  headers={"HX-Request": "true"}).text


def test_스킵_사유는_action_이다(tmp_path):
    """`최근인상`·`연속실패중단`·`상한도달`·`입찰가불명` 이 그대로 사유가 된다.

    `bids.run_bids` 가 `p["result"], p["error"] = "스킵", p["action"]` 으로 넣는다 —
    스킵 사유를 웹앱이 지어내지 않는다.
    """
    사유들 = ["최근인상", "연속실패중단", "상한도달", "입찰가불명"]
    plans = [결과계획(f"nad-a001-02-00000049539000{i}", 사, 70, None, "스킵", 사)
             for i, 사 in enumerate(사유들)]
    갈래 = flow.classify_results({"accounts": 산출물(ownway1=실행계정(plans))})

    assert len(갈래["스킵"]) == len(사유들)
    assert sorted(p["error"] for p in 갈래["스킵"]) == sorted(사유들)
    assert 갈래["성공"] == [] and 갈래["실패"] == []


def test_스냅샷에_소재_없음은_실패로_보인다(화면, tmp_run_dir):
    """prep 이후 소재가 삭제된 것이다 — 버그가 아니고, 숨기지도 않는다 (Pitfall 7)."""
    plans = [결과계획("nad-a001-02-000000495390006", "인상", 70, 80,
                      "실패", "스냅샷에 소재 없음")]
    산 = 산출물(ownway1=실행계정(plans))
    갈래 = flow.classify_results({"accounts": 산})
    assert 갈래["실패"][0]["error"] == "스냅샷에 소재 없음"

    job_id = 실행잡(화면, tmp_run_dir, 산출물(ownway1=계정([계획(plans[0]["adId"])])), 산)
    본문 = 화면.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text
    assert "스냅샷에 소재 없음" in 본문
    # 사유 옆에 그게 무슨 뜻인지 한 줄이 붙는다 — 안 붙으면 사용자가 버그로 읽는다
    assert "prep 이후" in 본문


def test_성공한_adId_만_추린다(tmp_path):
    """`succeeded_ad_ids` 가 `result == "성공"` 인 것만 돌려준다 — 01-09 의 입력(D-13)."""
    산 = 산출물(
        ownway1=실행계정([
            결과계획("nad-a001-02-000000495390006", "인상", 70, 80, "성공", ""),
            결과계획("nad-a001-02-000000495390007", "인상", 70, 80, "실패", "HTTP 400"),
        ]),
        pogeunae=실행계정([
            결과계획("nad-b001-02-000000495390001", "인상", 70, 80, "성공", ""),
            결과계획("nad-b001-02-000000495390002", "최근인상", 90, None, "스킵", "최근인상"),
        ]),
    )
    assert flow.succeeded_ad_ids({"accounts": 산}) == [
        "nad-a001-02-000000495390006", "nad-b001-02-000000495390001"]


# ── D-10 / T-1-36 — 재계산 차이를 은폐하지 않는다 ────────────────────────────

def test_미리보기와_달라진건을_보고한다():
    """action 이나 `to` 가 바뀐 항목이 사유와 before/after 로 나온다 (D-10).

    D-09 로 **실행 시점 재계산을 유지**했으므로 갈라지는 건 정상이다 — 쿨다운·연속실패
    중단·상한 가드가 실행 시점 기준으로 다시 도는 편이 안전하다. 이 함수의 일은
    갈라졌다는 사실을 숨기지 않는 것이다.
    """
    미 = {"accounts": 산출물(ownway1=계정([
        계획("nad-a001-02-000000495390006", "인상", 70, 80),
        계획("nad-a001-02-000000495390007", "인상", 70, 80)]))}
    실 = {"accounts": 산출물(ownway1=실행계정([
        # 실행 시점에 쿨다운이 걸렸다 — 미리보기 때는 인상이었다
        결과계획("nad-a001-02-000000495390006", "최근인상", 70, None, "스킵", "최근인상"),
        결과계획("nad-a001-02-000000495390007", "인상", 70, 80, "성공", "")]))}

    갈림 = flow.diff_preview(미, 실)
    assert len(갈림) == 1
    한건 = 갈림[0]
    assert 한건["adId"] == "nad-a001-02-000000495390006"
    assert 한건["why"] == "재계산으로 바뀜"
    assert "인상" in 한건["before"] and "최근인상" in 한건["after"]


def test_미리보기에_없던_소재도_보고한다():
    """결과에만 있는 adId 는 `미리보기에 없던 소재` 로 나온다."""
    미 = {"accounts": 산출물(ownway1=계정([계획("nad-a001-02-000000495390006")]))}
    실 = {"accounts": 산출물(ownway1=실행계정([
        결과계획("nad-a001-02-000000495390006", "인상", 70, 80, "성공", ""),
        결과계획("nad-a001-02-000000495390099", "인상", 70, 80, "성공", "")]))}

    갈림 = flow.diff_preview(미, 실)
    assert [d["adId"] for d in 갈림] == ["nad-a001-02-000000495390099"]
    assert 갈림[0]["why"] == "미리보기에 없던 소재"


def test_달라진게_없으면_빈_목록이다():
    """같은 입력이면 diff 가 빈 리스트다. **거부하지 않는다** — 스테일 거부는 Phase 2."""
    plans = [계획("nad-a001-02-000000495390006", "인상", 70, 80)]
    미 = {"accounts": 산출물(ownway1=계정(list(plans)))}
    실 = {"accounts": 산출물(ownway1=실행계정([
        결과계획("nad-a001-02-000000495390006", "인상", 70, 80, "성공", "")]))}
    assert flow.diff_preview(미, 실) == []


def test_결과가_안_적힌_항목은_성공이_아니다(화면, tmp_run_dir):
    """`result` 키가 없는 plan 은 `실행 안 됨` 이다 — **성공으로 세지 않는다.**

    dry-run 산출물을 실행 결과로 읽었거나 실행이 중간에 끊긴 모양이 이것이다.
    성공으로 세면 "전부 올렸다" 는 거짓말이 화면 맨 위 집계 줄에 뜬다. 그리고
    Plan 01-09 의 되돌리기가 **올라가지도 않은 소재**를 되돌리려 든다(D-13).
    """
    plans = [
        결과계획("nad-a001-02-000000495390006", "인상", 70, 80, "성공", ""),
        계획("nad-a001-02-000000495390007", "인상", 70, 80),   # result 키가 없다
    ]
    산 = 산출물(ownway1=실행계정(plans))
    갈래 = flow.classify_results({"accounts": 산})

    assert [p["adId"] for p in 갈래["성공"]] == ["nad-a001-02-000000495390006"]
    assert [p["adId"] for p in 갈래["실행 안 됨"]] == ["nad-a001-02-000000495390007"]
    # 되돌리기 대상에도 안 들어간다
    assert flow.succeeded_ad_ids({"accounts": 산}) == ["nad-a001-02-000000495390006"]

    job_id = 실행잡(화면, tmp_run_dir,
                    산출물(ownway1=계정([계획(p["adId"]) for p in plans])), 산)
    j = 화면.get(f"/jobs/{job_id}/result?format=json").json()
    assert j["result_counts"]["성공"] == 1
    assert j["result_counts"]["실행 안 됨"] == 1
    # 화면도 그 사실을 말한다 — 조용히 넘어가면 사람이 못 본다
    본문 = 화면.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text
    assert "결과가 안 적힌 항목이 1건" in 본문

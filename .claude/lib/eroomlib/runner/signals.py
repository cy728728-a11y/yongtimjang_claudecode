#!/usr/bin/env python3
"""이상 신호 판정 — 세로 러너가 "이 건 사람이 봐야 한다"를 코드로 가리키는 층.

**왜 승인 모드에서도 계산하나.** 지금은 매 단계 멈추므로 신호가 없어도 진행에 지장이 없다.
그런데 나중에 `--gate risky`(이상할 때만 멈춤)로 넘어갈 때 신호 판정을 그때 새로 만들면,
"무엇을 정지 조건으로 삼을지"를 근거 없이 감으로 정하게 된다. 지금부터 계산해 두고
승인 로그에 함께 남기면, 나중에 신호별 `수정승인`/`보류` 비율로 조건을 확정할 수 있다.

**fail-closed 원칙.** 산출물을 못 읽으면 "신호 없음"이 아니라 `sig.unreadable` 을 낸다.
자동 모드에서 판정 불가를 조용한 통과로 바꾸면 검증 없이 저장이 나간다.

각 신호: {"코드", "단계", "값", "설명"}
"""
import json
import os
import subprocess
import sys

# 카테고리 확신도 임계 — bulsaja-category-fix v1.7.0(2026-07-24, 90→70 하향)과 같은 값.
CONF_MIN = 70.0
# 옵션 제외율이 이보다 높으면 메인상품 판별을 의심한다.
EXCL_RATIO_MAX = 0.5
# 1.5배 상한 적용 후 남은 판매행이 이보다 적으면 기준가가 무너진 신호.
MIN_SELLABLE = 2

# 카테고리 단계에서 "결과가 안 나온" 상태값들(원장 그대로).
CAT_NO_RESULT = {"매칭불가", "sellha조회실패", "보류(정체불명)", "MCP오류"}


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _sig(code, step, desc, value=None):
    return {"코드": code, "단계": step, "값": value, "설명": desc}


# ---------------------------------------------------------------------------
# 카테고리 — decisions.json (bulsaja_mcp.py apply 산출물)
# ---------------------------------------------------------------------------

def category(run_dir, pid):
    """`decisions.json` 에서 해당 상품의 판정 1건을 읽어 신호를 낸다."""
    path = os.path.join(run_dir, "decisions.json")
    rows = _load(path)
    if not isinstance(rows, list):
        return [_sig("sig.unreadable", "카테고리",
                     f"decisions.json 을 읽지 못했다({path})")]
    d = next((r for r in rows if str(r.get("productId")) == str(pid)), None)
    if d is None:
        return [_sig("sig.unreadable", "카테고리",
                     "decisions.json 에 이 상품이 없다")]

    out = []
    status = (d.get("상태") or "").strip()
    if status in CAT_NO_RESULT:
        out.append(_sig("cat.no_result", "카테고리",
                        f"카테고리를 확정하지 못했다 — 상태 '{status}'", status))
    if status == "부분일치확인요":
        out.append(_sig("cat.partial", "카테고리",
                        "셀하 경로와 불사자 매칭이 최종 차수만 같다", status))

    try:
        conf = float(str(d.get("확신도") or "").strip())
    except ValueError:
        conf = None
    if conf is not None and conf < CONF_MIN:
        out.append(_sig("cat.low_conf", "카테고리",
                        f"셀하 확신도 {conf:g} < {CONF_MIN:g}", conf))

    if (d.get("위험") or "").strip() == "대분류변경":
        out.append(_sig("cat.major_change", "카테고리",
                        f"1차 대분류가 바뀐다: {d.get('기존카테고리','')} "
                        f"→ {d.get('변경카테고리','')}", "대분류변경"))
    return out


def category_decision(run_dir, pid):
    """가결정으로 심을 카테고리 경로. 확정 못 했으면 빈 문자열."""
    rows = _load(os.path.join(run_dir, "decisions.json"))
    if not isinstance(rows, list):
        return ""
    d = next((r for r in rows if str(r.get("productId")) == str(pid)), None) or {}
    if (d.get("상태") or "") in CAT_NO_RESULT:
        return ""
    return (d.get("변경카테고리") or "").strip()


# ---------------------------------------------------------------------------
# 상품명 — name_check.py 를 직접 돌린다(스킬이 이미 가진 검증기)
# ---------------------------------------------------------------------------

def product_name(run_dir, pid, name_check_py=None, py=None):
    """`named/` 산출물을 name_check.py 에 먹여 R1~R7 위반을 신호로 바꾼다."""
    named_dir = os.path.join(run_dir, "named")
    files = []
    if os.path.isdir(named_dir):
        files = [os.path.join(named_dir, f) for f in sorted(os.listdir(named_dir))
                 if f.endswith(".json")]
    if not files:
        return [_sig("sig.unreadable", "상품명",
                     f"named/*.json 이 없다({named_dir})")]

    # 이 상품이 들어 있는 파일만 검사한다(세로 러너는 1건이므로 보통 1개).
    def _items(data):
        # named JSON 은 {"products": [...]} 가 정상이고, 배열만 담긴 변형도 받는다.
        # (앞서 `a or b if cond else []` 로 썼다가 조건식이 전체를 감싸 항상 빈 목록이 됐다.)
        if isinstance(data, dict):
            return data.get("products") or []
        return data if isinstance(data, list) else []

    target, rec = None, None
    for f in files:
        for p in _items(_load(f)):
            if str(p.get("productId")) == str(pid):
                target, rec = f, p
                break
        if target:
            break
    if not target:
        return [_sig("sig.unreadable", "상품명", "named/ 에 이 상품이 없다")]

    out = []
    if name_check_py and os.path.exists(name_check_py):
        checked = os.path.join(run_dir, "namecheck.json")
        try:
            # 한국어 출력이라 인코딩을 못 박아야 한다 — 윈도우 기본(cp949)으로 읽으면
            # 리더 스레드에서 UnicodeDecodeError 가 난다.
            subprocess.run([py or sys.executable, name_check_py,
                            "--input", target, "--output", checked],
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                           capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        except Exception as e:
            out.append(_sig("sig.unreadable", "상품명",
                            f"name_check 실행 실패: {type(e).__name__}"))
        me = next((p for p in _items(_load(checked))
                   if str(p.get("productId")) == str(pid)), None)
        if me is None and not out:
            out.append(_sig("sig.unreadable", "상품명", "name_check 결과에 이 상품이 없다"))
        elif me:
            bad = me.get("위반") or me.get("violations") or []
            if bad:
                out.append(_sig("name.rule_violation", "상품명",
                                f"상품명 규칙 위반: {'; '.join(map(str, bad))[:200]}", bad))
    else:
        out.append(_sig("sig.unreadable", "상품명", "name_check.py 를 찾지 못했다"))

    # 선택 키워드가 prep 이 뽑아둔 후보 안에 있나 — 밖이면 근거 없는 키워드다.
    cands = _load(os.path.join(run_dir, "targets.json"))
    if isinstance(cands, list):
        t = next((c for c in cands if str(c.get("productId")) == str(pid)), None)
        pool = {str(k).strip() for k in ((t or {}).get("키워드후보") or [])}
        used = [str(k).strip() for k in (rec.get("키워드") or rec.get("사용키워드") or [])]
        off = [k for k in used if pool and k not in pool]
        if off:
            out.append(_sig("name.kw_off", "상품명",
                            f"후보 밖 키워드 사용: {', '.join(off)[:120]}", off))
    return out


# ---------------------------------------------------------------------------
# 옵션 — run_options.py apply --emit 산출물
# ---------------------------------------------------------------------------

def options(run_dir, pid):
    """`plans.json`(apply --emit)에서 계획 1건을 읽어 신호를 낸다."""
    path = os.path.join(run_dir, "plans.json")
    rows = _load(path)
    if not isinstance(rows, list):
        return [_sig("sig.unreadable", "옵션", f"plans.json 을 읽지 못했다({path})")]
    p = next((r for r in rows if str(r.get("productId")) == str(pid)), None)
    if p is None:
        return [_sig("sig.unreadable", "옵션", "plans.json 에 이 상품이 없다")]

    out = []
    status = (p.get("상태") or "").strip()
    if status and status != "정리대상":
        out.append(_sig("opt.not_ready", "옵션",
                        f"정리대상이 아니다 — 상태 '{status}'", status))

    if p.get("이름위반"):
        out.append(_sig("opt.name_violation", "옵션",
                        f"옵션명 규칙 위반: {'; '.join(map(str, p['이름위반']))[:200]}",
                        p["이름위반"]))
    if p.get("검증실패"):
        out.append(_sig("opt.verify_fail", "옵션",
                        f"최종 검증 실패: {'; '.join(map(str, p['검증실패']))[:200]}",
                        p["검증실패"]))

    keep = p.get("유지수")
    excl = p.get("제외수")
    if isinstance(keep, int) and isinstance(excl, int) and (keep + excl) > 0:
        ratio = excl / float(keep + excl)
        if ratio > EXCL_RATIO_MAX:
            out.append(_sig("opt.excl_high", "옵션",
                            f"제외율 {ratio:.0%} — 메인상품 판별을 의심한다", round(ratio, 3)))

    sellable = p.get("판매행수")
    if isinstance(sellable, int) and sellable < MIN_SELLABLE:
        out.append(_sig("opt.thin_range", "옵션",
                        f"상한 적용 후 판매행 {sellable}개 — 기준가 붕괴 신호(부속품 혼입?)",
                        sellable))

    for w in (p.get("경고") or []):
        w = str(w)
        if "동률" in w or "대표후보" in w:
            out.append(_sig("opt.rep_tie", "옵션", w, w))
        elif "썸네일" in w:
            out.append(_sig("opt.thumb_mismatch", "옵션", w, w))
        else:
            out.append(_sig("opt.warn", "옵션", w, w))
    return out


# ---------------------------------------------------------------------------
# 썸네일 — apply --generate 산출물(generated.json). 이미지 판단은 사람 몫이라
# 자동으로 사용가능/제외를 가리지 않는다 — 여기서는 "볼 것이 있나 없나"만 신호로 낸다.
# ---------------------------------------------------------------------------

def thumbnail(run_dir, pid):
    """`generated.json` 에서 이 상품의 생성 결과를 읽어 신호를 낸다."""
    path = os.path.join(run_dir, "generated.json")
    data = _load(path)
    if not isinstance(data, dict):
        return [_sig("sig.unreadable", "썸네일", f"generated.json 을 읽지 못했다({path})")]
    g = data.get(pid)
    if g is None:
        return [_sig("sig.unreadable", "썸네일", "generated.json 에 이 상품이 없다")]

    out = []
    if "오류" in g:
        out.append(_sig("thumb.gen_fail", "썸네일", f"생성 실패: {g['오류']}", g["오류"]))
    if g.get("재작업사유"):
        out.append(_sig("thumb.redo", "썸네일", f"재작업 사유: {g['재작업사유']}",
                        g["재작업사유"]))
    return out


# ---------------------------------------------------------------------------
# 상세 — apply --generate 산출물(generated.json). 장별 판정은 사람 몫이라
# 여기서는 "볼 것이 있나 없나"만 신호로 낸다(썸네일과 같은 성격).
# ---------------------------------------------------------------------------

def detail_page(run_dir, pid):
    """`generated.json` 에서 이 상품의 상세 생성 결과를 읽어 신호를 낸다."""
    path = os.path.join(run_dir, "generated.json")
    data = _load(path)
    if not isinstance(data, dict):
        return [_sig("sig.unreadable", "상세", f"generated.json 을 읽지 못했다({path})")]
    g = data.get(pid)
    if g is None:
        return [_sig("sig.unreadable", "상세", "generated.json 에 이 상품이 없다")]

    out = []
    if "오류" in g:
        out.append(_sig("detail.gen_fail", "상세", f"생성 실패: {g['오류']}", g["오류"]))
    n = len(g.get("생성장") or [])
    # 고지한 장수는 `--sections` 로 바뀔 수 있다 — 8을 박아 두면 그때 전건이 신호로 뜬다.
    # 그래서 접수할 때 쓴 장수를 generated.json 에 함께 적어 두고 그걸 기준으로 본다.
    want = int(g.get("요청장수") or 8)
    if n and n != want:
        # 고지한 장수를 접수했는데 다른 장수가 왔다 = 부분 실패 신호
        out.append(_sig("detail.count_mismatch", "상세",
                        f"생성 {n}장 — 고지한 {want}장과 다르다", n))
    if g.get("재작업사유"):
        out.append(_sig("detail.redo", "상세", f"재작업 사유: {g['재작업사유']}",
                        g["재작업사유"]))
    return out


# ---------------------------------------------------------------------------

_BY_STEP = {"카테고리": category, "상품명": product_name, "옵션": options,
           "썸네일": thumbnail, "상세": detail_page}


def for_step(step, run_dir, pid, **kw):
    """단계 이름으로 판정기를 골라 신호 목록을 돌려준다. 모르는 단계는 빈 목록."""
    fn = _BY_STEP.get(step)
    if fn is None:
        return []
    try:
        if fn is product_name:
            return fn(run_dir, pid, **kw)
        return fn(run_dir, pid)
    except Exception as e:  # 판정기 자체가 터져도 조용히 통과시키지 않는다
        return [_sig("sig.unreadable", step,
                     f"신호 판정 중 오류: {type(e).__name__}: {e}"[:180])]


def fmt(sigs):
    """사람이 보는 한 줄 요약들."""
    return [f"⚠ [{s['코드']}] {s['설명']}" for s in sigs]


# ---------------------------------------------------------------------------
# 검수표 — **승인 대상 그 자체**를 보여준다
#
# 신호(⚠)는 "이상하다"를 가리킬 뿐, 무엇을 승인하는지는 알려주지 않는다. 실전 1건에서
# 옵션 게이트가 신호만 찍는 바람에 "승인해야 할 옵션명이 화면 어디에도 없다"는 지적이 나왔다.
# 아래 함수들은 각 단계의 preview 산출물에서 **결정된 값**을 뽑아 사람이 읽을 줄로 만든다.
# ---------------------------------------------------------------------------

def _detail_category(run_dir, pid):
    rows = _load(os.path.join(run_dir, "decisions.json"))
    d = next((r for r in rows if str(r.get("productId")) == str(pid)), None) \
        if isinstance(rows, list) else None
    if not d:
        return ["(decisions.json 을 읽지 못했다 — 검수표 없음)"]
    before, after = d.get("기존카테고리", ""), d.get("변경카테고리", "")
    out = [f"검색어: {d.get('검색어', '')}  (셀하 확신도 {d.get('확신도', '')})",
           f"기존:   {before}",
           f"변경:   {after}" + ("   ← 변경 없음" if before == after else "")]
    if d.get("실물판정"):
        out.append(f"실물:   {d['실물판정']}")
    out.append(f"상태:   {d.get('상태', '')}")
    return out


def _detail_product_name(run_dir, pid):
    named = os.path.join(run_dir, "named")
    rec = None
    if os.path.isdir(named):
        for f in sorted(os.listdir(named)):
            if not f.endswith(".json"):
                continue
            data = _load(os.path.join(named, f))
            items = data.get("products") if isinstance(data, dict) else data
            rec = next((p for p in (items or [])
                        if str(p.get("productId")) == str(pid)), None)
            if rec:
                break
    if not rec:
        return ["(named/ 에서 이 상품을 찾지 못했다 — 검수표 없음)"]
    kws = [rec.get(f"키워드{i}") for i in (1, 2, 3)]
    out = [f"기존: {rec.get('원본상품명', '')}",
           f"변경: {rec.get('새상품명', '')}",
           f"키워드: {' / '.join(k for k in kws if k)}"]
    if rec.get("term분해"):
        t = rec["term분해"]
        out.append(f"term {len(t)}개: {' · '.join(map(str, t))}")
    if rec.get("실물판정"):
        out.append(f"실물: {rec['실물판정']}")
    return out


def _detail_options(run_dir, pid):
    rows = _load(os.path.join(run_dir, "plans.json"))
    p = next((r for r in rows if str(r.get("productId")) == str(pid)), None) \
        if isinstance(rows, list) else None
    if not p:
        return ["(plans.json 을 읽지 못했다 — 검수표 없음)"]
    out = []
    if p.get("메인상품"):
        out.append(f"메인상품: {p['메인상품']}")
    rep = p.get("대표이름") or p.get("대표") or ""
    out.append(f"대표: {rep}  ·  기준가 {p.get('기준가') or 0:,} "
               f"→ 상한 {p.get('상한') or 0:,}")

    chg = p.get("이름변경") or []
    out.append(f"[옵션명 교정 {len(chg)}건]")
    for c in chg:
        pre = f"{c.get('차원')}·" if c.get("차원") else ""
        out.append(f"  {pre}{c.get('키', ''):>4} {c.get('기존', '')}  →  {c.get('교정', '')}")

    order = p.get("순서상세") or [{"이름": n} for n in (p.get("순서이름") or [])]
    out.append(f"[판매 {p.get('유지수', len(order))}건 · 업로드 순서(판매가 오름차순)]")
    for i, r in enumerate(order, 1):
        mark = "★" if r.get("대표") else " "
        price = r.get("판매가")
        out.append(f"  {mark}{i:>2}. {str(r.get('이름', '')):<26} "
                   f"{(price if isinstance(price, (int, float)) else 0):>9,}")
    if p.get("제외상세"):
        out.append(f"[제외 {len(p['제외상세'])}건]")
        for e in p["제외상세"]:
            out.append(f"   - {e.get('이름', '')} — {e.get('사유', '')}")
    elif p.get("제외수"):
        out.append(f"[제외 {p['제외수']}건] (상세 없음 — 옛 plans.json)")
    return out


def _detail_thumbnail(run_dir, pid):
    """텍스트 검수표 — 이미지 자체의 비교는 review.html 이 하고, 여기는 안내와 메타만."""
    data = _load(os.path.join(run_dir, "generated.json"))
    g = data.get(pid) if isinstance(data, dict) else None
    if not g:
        return ["(generated.json 을 읽지 못했다 — 검수표 없음)"]
    if "오류" in g:
        return [f"생성 실패: {g['오류']}"]
    out = [f"검수 페이지: {os.path.join(run_dir, 'review.html')}",
           f"기존 대표: {g.get('기존대표', '')}",
           f"생성본:   {g.get('생성본', '')}",
           "(제품·색상·워터마크 비교는 위 review.html 을 열어서 본다 — "
           "이미지라 텍스트 검수표로는 판정할 수 없다)"]
    if g.get("재작업사유"):
        out.append(f"재작업 사유: {g['재작업사유']}")
    if g.get("크레딧"):
        out.append(f"사용 크레딧: {g['크레딧']}")
    return out


def _detail_detailpage(run_dir, pid):
    """상세 검수표 — 장별 이미지 비교는 review.html 이 하고, 여기는 안내와 메타만."""
    data = _load(os.path.join(run_dir, "generated.json"))
    g = data.get(pid) if isinstance(data, dict) else None
    if not g:
        return ["(generated.json 을 읽지 못했다 — 검수표 없음)"]
    if "오류" in g:
        return [f"생성 실패: {g['오류']}"]
    imgs = g.get("생성장") or []
    out = [f"검수 페이지: {os.path.join(run_dir, 'review.html')}",
           f"생성 장수: {len(imgs)}장",
           f"1장: {imgs[0] if imgs else ''}",
           "(중국어 잔여·글자 겹침·무관 내용·상표 삽입·구조 일관성은 위 review.html 을 "
           "열어서 전 장을 본다 — 이미지라 텍스트 검수표로는 판정할 수 없다)"]
    if g.get("재작업사유"):
        out.append(f"재작업 사유: {g['재작업사유']}")
    if g.get("크레딧"):
        out.append(f"사용 크레딧: {g['크레딧']}")
    return out


_DETAIL_BY_STEP = {"카테고리": _detail_category, "상품명": _detail_product_name,
                   "옵션": _detail_options, "썸네일": _detail_thumbnail,
                   "상세": _detail_detailpage}


def detail(step, run_dir, pid):
    """게이트에 찍을 검수표 줄들. 못 읽어도 예외를 올리지 않는다(신호가 따로 잡는다)."""
    fn = _DETAIL_BY_STEP.get(step)
    if fn is None:
        return []
    try:
        return fn(run_dir, pid)
    except Exception as e:  # noqa: BLE001
        return [f"(검수표 생성 실패: {type(e).__name__}: {e})"[:180]]

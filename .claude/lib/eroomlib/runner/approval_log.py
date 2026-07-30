#!/usr/bin/env python3
"""승인 로그 — 자동화 전환의 유일한 근거 데이터.

이룸님이 게이트에서 뭘 했는지가 남아야 한다. 남지 않으면 나중에 `--gate risky` 로 넘어갈 때
"확신도 몇 점부터 멈춰야 하나"를 감으로 정하게 된다. 신호 코드별로 `수정승인`/`보류`
비율을 집계하면 정지 조건이 데이터로 확정된다.

위치: 그룹 시트의 `00_승인로그` 탭(현황판 `00_진행` 과 같은 스프레드시트 — 집계가 쉽다).
쓰기는 append 1행. 실패해도 진행을 막지 않는다(로그는 파생본, 원장은 각 스킬 탭).
같은 내용이 state.json 에도 남으므로 시트가 비어도 복구 가능하다.
"""
import os
import sys
import time

try:
    from ..gsheets import append_rows, ensure_tab, sheets_get
except ImportError:  # 직접 실행
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from eroomlib.gsheets import append_rows, ensure_tab, sheets_get

TAB = "00_승인로그"
HEADER = ["시각", "상품id", "단계", "결과", "게이트모드", "뜬 신호",
          "시도", "수정 내용", "메모", "요약"]

# 결과 값 — `수정승인`/`보류` 가 규칙 구멍의 위치를 가리킨다.
RESULTS = ("승인", "수정승인", "보류", "건너뜀")


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _ensure_header(sheet):
    """탭이 없으면 만들고, 헤더가 짧으면(구버전) 뒤로 확장한다.

    `시도` 열을 뒤늦게 넣었다 — 헤더를 안 늘리면 새 열이 이름 없이 쌓여
    나중에 무슨 값인지 알 수 없게 된다.
    """
    if ensure_tab(sheet, TAB, HEADER):
        return
    try:
        cur = (sheets_get(sheet, f"'{TAB}'!1:1") or [[]])[0]
    except Exception:
        return
    if len(cur) < len(HEADER) and list(cur) == HEADER[:len(cur)]:
        from ..gsheets import sheets_update
        sheets_update(sheet, f"'{TAB}'!A1", [list(HEADER)])


def codes_of(signals):
    """신호 목록 → 코드 문자열. 중복은 접는다(같은 코드가 시도마다 반복된다)."""
    seen, out = set(), []
    for s in (signals or []):
        c = (s or {}).get("코드", "")
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return "; ".join(out)


def record(sheet, pid, step, result, signals=(), fix="", memo="", gate="",
           summary="", attempts=1):
    """승인 1건을 append. 반환: 성공 여부(실패해도 예외를 올리지 않는다).

    `signals` 는 **그 단계에서 뜬 신호 전부**여야 한다 — 마지막 시도 것만 넣으면
    "고쳐서 통과시켰는데 신호는 없었다"는 모순된 행이 남고, 나중에 정지 조건을 정할 때
    무신호 건에도 개입이 필요하다는 잘못된 결론이 나온다(실제로 첫 기록에서 났던 일).
    """
    if result not in RESULTS:
        raise ValueError(f"모르는 결과값: {result} (가능: {', '.join(RESULTS)})")
    row = [
        _now(), pid, step, result, gate,
        codes_of(signals)[:400],
        attempts,
        str(fix or "")[:900],
        str(memo or "")[:500],
        str(summary or "")[:900],
    ]
    if not sheet:
        return False
    try:
        _ensure_header(sheet)
        append_rows(sheet, TAB, [row])
        return True
    except Exception as e:
        print(f"  (승인로그 기록 실패 — {str(e)[:120]})")
        return False


def tally(sheet):
    """신호 코드별 {전체, 수정승인, 보류} 집계 — `--gate risky` 조건을 정할 때 쓴다.

    한 행에 신호가 여러 개면 각 코드에 모두 계상한다(어느 신호가 사람을 부르는지가
    관심사이지, 행 수를 정확히 나누는 게 목적이 아니다).
    신호가 하나도 없던 행은 `(무신호)` 로 모은다 — 이 값이 자동화 안전선의 바닥이다.
    """
    try:
        rows = sheets_get(sheet, f"'{TAB}'!A2:J")
    except Exception as e:
        print(f"  (승인로그 읽기 실패 — {str(e)[:120]})")
        return {}
    out = {}
    for r in rows or []:
        result = (r[3] if len(r) > 3 else "").strip()
        codes = [c.strip() for c in (r[5] if len(r) > 5 else "").split(";") if c.strip()]
        for code in (codes or ["(무신호)"]):
            b = out.setdefault(code, {"전체": 0, "수정승인": 0, "보류": 0})
            b["전체"] += 1
            if result in ("수정승인", "보류"):
                b[result] += 1
    return out


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description="승인 로그 집계")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    t = tally(a.sheet)
    if a.json:
        print(json.dumps(t, ensure_ascii=False, indent=2))
        return
    if not t:
        print("승인 로그가 비었다.")
        return
    print(f"{'신호':<24}{'전체':>6}{'수정승인':>9}{'보류':>6}{'개입률':>8}")
    for code, b in sorted(t.items(), key=lambda kv: -kv[1]["전체"]):
        rate = (b["수정승인"] + b["보류"]) / b["전체"] if b["전체"] else 0
        print(f"{code:<24}{b['전체']:>6}{b['수정승인']:>9}{b['보류']:>6}{rate:>7.0%}")
    print("\n개입률이 낮은 신호는 `--gate risky` 정지 조건에서 빼도 된다.")


if __name__ == "__main__":
    main()

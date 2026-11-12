#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hookscore_ko.py — 스레드 글 첫 줄(후킹) 점수기 (한국어판)

원본: Jakeschincariol/instagram-agent-skill 의 hookscore.py (MIT) — 영어 릴스용.
여기선 같은 다섯 가지 기준을 한국어 스레드 첫 줄에 맞게 다시 만들었다.

무엇을 하나:  첫 줄이 "멈추게 하는 줄"이 가진 성질을 갖췄는지 본다.
  1) 길이     — 한눈에 읽히는가 (12~40자)
  2) 구체성   — 숫자·기간·물건 이름처럼 확인 가능한 게 있는가
  3) 긴장     — 손해·실수·의외·궁금증 같은 걸린 게 있는가
  4) 앞배치   — 핵심 단어가 앞 세 어절 안에 있는가, 인사·군말로 시작하지 않는가
  5) 말 걸기  — 읽는 사람을 부르거나 질문하는가
무엇이 아닌가: 조회수 예측기가 아니다. 원본도 "좋은 후킹 두 개 중 뭐가 터질지"는
  거의 못 맞혔다(동전 던지기 수준). 약한 줄을 걸러내는 용도로만 쓴다.

사용법
  python3 hookscore_ko.py --hook "옷장 정리하다가 3년 동안 한 번도 안 입은 옷 발견."
  python3 hookscore_ko.py 후보.txt          # 한 줄에 하나, 점수순 정렬
  python3 hookscore_ko.py 후보.txt --json
"""

import argparse
import json
import re
import statistics
import sys

# ---- 사전 ---------------------------------------------------------------

# 숫자 + 단위 (3년, 10분, 15분, 서랍 한 칸 등)
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|원|만원|만|천|분|초|시간|일|주|달|개월|년|번|개|칸|장|벌|명|배|kg|g|L|ml)?")
KO_NUM_RE = re.compile(r"(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무|서른|몇)\s*(?:번|개|칸|장|벌|명|시간|달|해|주|군데|가지|숟가락|스푼|캔|봉지)")

# 눈에 그려지는 생활 물건·장면 (살림 계정용 — 주제가 바뀌면 여기만 늘린다)
OBJECTS = [
    "냉장고", "옷장", "서랍", "수건", "빨래", "세탁기", "건조기", "설거지", "싱크대", "배수구",
    "전기요금", "고지서", "가스비", "관리비", "장난감", "양치", "현관", "신발", "식탁", "거실",
    "이불", "베개", "가습기", "제습기", "뽁뽁이", "창문", "곰팡이", "머리카락", "욕실", "화장실",
    "도시락", "볶음밥", "라면", "반찬", "등원", "하원", "키즈카페", "택배", "분리수거", "음식물",
    "청소기", "물걸레", "냄비", "프라이팬", "도마", "칫솔", "과탄산", "베이킹소다", "식초",
]

# 긴장 단어: 손해·실수·의외·감정
STAKES = [
    "실패", "실수", "망", "후회", "아깝", "버리", "버렸", "날렸", "손해", "돈", "쉰내", "냄새", "곰팡",
    "몰랐", "알고 보니", "알고보니", "오히려", "사실", "진짜", "결국", "또", "왜", "이유",
    "깜짝", "놀란", "충격", "한숨", "지쳐", "포기", "무너", "전쟁", "난리", "귀찮", "힘든", "힘듦",
    "안 ", "못 ", "없", "말고", "대신", "그만", "하지 마", "절대", "처음", "드디어", "바꿨",
    "몇 년째", "매번", "맨날", "무한", "반복",
]

# 시작하면 감점되는 군말·인사
WEAK_OPENERS = [
    "안녕", "오늘은", "여러분", "그냥", "음", "아 ", "저는", "제가", "소개", "공유",
    "이번에", "혹시나", "다름이 아니라", "갑자기 생각", "그런데", "근데 ",
]

# 말 걸기 신호
ADDRESS = ["너", "다들", "우리 집만", "나만", "누가", "있어?", "해?", "돼?", "편이야?", "어때?",
           "사람?", "집?", "아니지?", "않아?", "있지?", "봤어?", "뭐 먹어?", "어디"]

# 즉시 감점 (일상글 단계 금지 요소)
DEALBREAKERS = [
    (re.compile(r"#\S+"), "해시태그가 첫 줄에 있다."),
    (re.compile(r"https?://|\.com|\.kr"), "링크가 첫 줄에 있다. 일상글 단계에선 금지."),
    (re.compile(r"팔로우|맞팔|댓글 남기면|DM|디엠|스친"), "팔로우·댓글 유도. 일상글 단계에선 금지."),
    (re.compile(r"특가|할인|최저가|광고|협찬|쿠팡"), "광고 티. 일상글 단계에선 금지."),
    (re.compile(r"[\U0001F300-\U0001FAFF☀-➿]"), "이모지가 첫 줄에 있다. 내 말투엔 이모지가 없다."),
]


def clamp(n):
    return max(0.0, min(100.0, n))


def first_line(text):
    """여러 줄이 들어오면 첫 줄만 본다."""
    for line in text.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def check_length(t):
    n = len(t.replace(" ", ""))
    if 12 <= n <= 40:
        s = 100.0
    elif n < 12:
        s = clamp(100 - (12 - n) * 8)
    else:
        s = clamp(100 - (n - 40) * 4)
    return s, f"{n}자(공백 제외), 12~40자가 좋음"


def check_specificity(t):
    hits = [m.group().strip() for m in NUM_RE.finditer(t) if re.search(r"\d", m.group())]
    hits += [m.group().strip() for m in KO_NUM_RE.finditer(t)]
    objs = [o for o in OBJECTS if o in t]
    n = len(hits) + len(objs)
    hits += objs
    # 숫자는 25점, 눈에 그려지는 물건은 20점씩
    s = 20.0 if n == 0 else clamp(50 + (n - len(objs)) * 25 + len(objs) * 20)
    return s, (f"구체 표시 {n}개: {', '.join(hits[:3])}" if n else "숫자·기간·개수가 없다 — 확인할 게 없는 줄")


def check_stakes(t):
    found = sorted({w.strip() for w in STAKES if w in t})
    n = len(found)
    s = {0: 25.0, 1: 70.0}.get(n, 100.0)
    return s, (f"긴장 단어 {n}개: {', '.join(found[:4])}" if n else "걸린 게 없다 — 손해·의외·궁금증 없음")


def check_frontload(t):
    words = t.split()
    if not words:
        return 0.0, "빈 줄"
    penalty, hit = 0, None
    for w in WEAK_OPENERS:
        if t.startswith(w):
            penalty, hit = 30, w
            break
    pos = None
    for i, w in enumerate(words):
        if re.search(r"\d", w) or KO_NUM_RE.search(w) or any(s.strip() and s.strip() in w for s in STAKES):
            pos = i
            break
    if pos is None:
        base, where = 40.0, "핵심 단어가 안 보임"
    elif pos <= 2:
        base, where = 100.0, f"핵심이 {pos + 1}번째 어절"
    elif pos <= 5:
        base, where = 70.0, f"핵심이 {pos + 1}번째 어절 — 앞으로 당길 수 있음"
    else:
        base, where = 40.0, f"핵심이 {pos + 1}번째 어절 — 너무 늦음"
    return clamp(base - penalty), where + (f"; 군말로 시작(\"{hit}\")" if hit else "")


def check_address(t):
    if t.endswith("?") or any(a in t for a in ADDRESS):
        return 100.0, "읽는 사람에게 말을 건다"
    if re.search(r"(나|내가|우리|요즘)", t):
        return 70.0, "내 얘기 — 읽는 사람은 아직 안 부름"
    return 40.0, "누구에게 하는 말인지 없음"


CHECKS = [("길이", check_length), ("구체성", check_specificity), ("긴장", check_stakes),
          ("앞배치", check_frontload), ("말걸기", check_address)]


def run(text):
    t = first_line(text)
    results = {name: fn(t) for name, fn in CHECKS}
    flags = [msg for pat, msg in DEALBREAKERS if pat.search(t)]
    scores = [results[n][0] for n, _ in CHECKS]
    # 제일 약한 항목이 전체를 깎는다 (원본과 같은 방식)
    overall = clamp(statistics.mean(scores) * 0.6 + min(scores) * 0.4 - len(flags) * 15)
    verdict = "강함" if overall >= 70 and min(scores) >= 55 and not flags else ("보통" if overall >= 50 else "약함")
    weakest = min(CHECKS, key=lambda c: results[c[0]][0])[0]
    return {"hook": t, "score": round(overall, 1), "verdict": verdict,
            "checks": {n: {"score": results[n][0], "detail": results[n][1]} for n, _ in CHECKS},
            "flags": flags, "weakest": weakest}


def render(r):
    print(f"\n\"{r['hook']}\"")
    for n, v in r["checks"].items():
        print(f"  {n:<4} {v['score']:5.1f}  {v['detail']}")
    print(f"  ── 점수 {r['score']:.1f}  {r['verdict']}")
    for f in r["flags"]:
        print(f"  ✗ {f}")
    if r["verdict"] != "강함":
        print(f"  → 제일 약한 항목: {r['weakest']}. 그것부터 고쳐서 다시 돌려라.")


def main():
    ap = argparse.ArgumentParser(description="스레드 첫 줄 점수기")
    ap.add_argument("file", nargs="?", help="한 줄에 후보 하나인 텍스트 파일 (- 는 표준입력)")
    ap.add_argument("--hook", help="후보 한 줄")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        if a.hook:
            lines = [a.hook]
        elif a.file:
            src = sys.stdin if a.file == "-" else open(a.file, encoding="utf-8")
            lines = [l.strip() for l in src if l.strip()]
        else:
            ap.print_help()
            return 1
        rows = sorted((run(l) for l in lines), key=lambda r: -r["score"])
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
        else:
            for r in rows:
                render(r)
        return 0
    except FileNotFoundError as e:
        print(f"파일을 못 찾음: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # 예상 못 한 오류도 메시지로 남긴다
        print(f"오류: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())

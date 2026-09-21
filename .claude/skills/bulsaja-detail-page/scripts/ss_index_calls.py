# -*- coding: utf-8 -*-
"""불사자 목록 조회의 **호출 규약** — 인자 타입과 응답 모양.

`ss_index_resume.py` 와 같은 선이다: **import 가 0줄인 모듈.** `ss_index_build.py` 는
최상단에서 `bulsaja_mcp` 를 import 하므로 `.venv-web` 의 pytest 가 그 파일을 import 조차
못 한다(D-19). 그러면 아래 두 규약이 스위트에 한 줄도 안 남고, 다음 사람이 고쳐도
아무도 모른다. 여기에 `bulsaja_mcp` 나 `requests` 를 한 줄이라도 끌어오면 그 회귀가
통째로 죽는다.

**이 모듈이 생긴 경위 (03-07 첫 실탄, 2026-09-21):**
30그룹짜리 인덱스 구축이 9.2초 만에 `exit 0` 으로 끝났다. 로그는 30그룹 전부
`상품 0건 · 누적 0행` 이었다. 실제 원인은 `groupId` 를 **문자열로 보낸 것**이고,
서버는 이렇게 답했다:

    MCP error -32602: Input validation error: ... "expected": "number",
    "code": "invalid_type", "path": ["groupId"]

그 오류 응답에는 `항목` 키가 없다. 호출부는 `r.get("항목") or []` 로 읽어
**"이 그룹은 상품이 0건이구나"** 로 해석하고 조용히 다음 그룹으로 넘어갔다.
크레딧이 0이라 아무 경보도 안 울렸다 — 3시간짜리 잡이 9초에 "성공" 한 것만이 단서였다.

막아야 할 것이 둘이다. 하나만 고치면 다음에 또 당한다:
  ① 타입    — `groupId` 는 number 다 (`그룹아이디`)
  ② 해석    — **오류를 빈 결과로 읽지 않는다** (`항목꺼내기`)
"""


def 그룹아이디(gid):
    """MCP 에 보낼 `groupId` — **number 로 바꾼다.**

    실측(2026-09-21): 문자열로 보내면 `-32602 expected number, received string`.
    웹앱은 groupId 를 문자열로 다룬다(`join.index_targets` 가 번호 기준 중복 제거를
    문자열로 한다) — 그게 잘못은 아니다. 경계에서 바꾸는 게 맞고, 그 경계가 여기다.

    숫자로 못 바꾸면 **원본 그대로 보낸다.** 여기서 예외를 던지면 판이 바뀌어
    id 체계가 영숫자가 되는 날 우리 쪽이 먼저 죽는다 — 서버가 말하게 둔다.
    """
    try:
        return int(str(gid).strip())
    except (TypeError, ValueError):
        return gid


def 항목꺼내기(r, 맥락=""):
    """목록 응답에서 `항목` 리스트를 꺼낸다. **모양이 아니면 예외다.**

    `r.get("항목") or []` 를 쓰지 않는 이유가 이 모듈의 존재 이유다(docstring 참조):
    오류 응답에는 `항목` 키가 없고, `or []` 는 그걸 **"빈 그룹"** 으로 읽는다.
    "못 물어봤다" 와 "물어봤더니 없더라" 는 다른 사실이고, 둘을 한 칸에 담으면
    화면에서 "인덱스 미보유" 가 "광고 쪽 오류" 로 둔갑한다 (RESEARCH §Pitfall 3).

    키가 **있는데** 빈 리스트인 것은 정상이다 — 진짜 빈 그룹이거나 마지막 페이지 다음이다.
    그건 `[]` 로 돌려주고 호출부가 루프를 끝낸다.

    예외를 던지면 `ss_index_build.main()` 의 그룹별 try 가 받아서 그 그룹만
    `{"완결": False, "오류": ...}` 로 적고 나머지 그룹은 계속 훑는다. 다음 실행이
    그 그룹을 이어서 한다.
    """
    if not isinstance(r, dict):
        raise RuntimeError(f"목록 응답이 dict 가 아니다{맥락}: {type(r).__name__}")
    if "항목" in r:
        항목 = r.get("항목")
        if 항목 is None:
            return []
        if not isinstance(항목, list):
            raise RuntimeError(f"목록 응답의 '항목' 이 리스트가 아니다{맥락}: "
                               f"{type(항목).__name__}")
        return 항목

    # 여기부터는 전부 "우리가 못 봤다" 다. 서버가 준 문구를 **그대로** 싣는다 —
    # 요약하면 다음 사람이 같은 9초짜리 미스터리를 처음부터 푼다.
    사유 = r.get("_text") or r.get("error") or r.get("message")
    if 사유 is None:
        사유 = f"키 {sorted(r.keys())[:8]}"
    raise RuntimeError(f"목록 응답에 '항목' 이 없다{맥락}: {str(사유)[:300]}")


def 서버집계(r, 기본=None):
    """서버가 준 그룹 전체 개수. 못 찾으면 `기본`(보통 None) — **지어내지 않는다.**

    없는 총계를 0 으로 채우면 `완결 = 행수 >= 총계` 가 거짓으로 참이 되고,
    한 번도 안 훑은 그룹이 "다 봤다" 가 된다.

    실측(2026-09-21) 이름은 `총상품수` 다. 후보를 남겨 두는 건 판이 바뀔 때를 위한 것이고,
    실측 이름을 맨 앞에 둔다 — 매 페이지 도는 루프라 헛도는 조회를 줄인다.
    """
    if not isinstance(r, dict):
        return 기본
    for 키 in ("총상품수", "전체개수", "총개수", "전체"):
        값 = r.get(키)
        if isinstance(값, int) and not isinstance(값, bool):
            return 값
    return 기본

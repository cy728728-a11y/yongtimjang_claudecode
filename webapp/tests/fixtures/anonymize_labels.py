#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`04-RESEARCH.md` Appendix A → `banner_labels.json` 익명화본 재생성 스크립트.

**테스트 트리 전용 도구다.** 웹앱 런타임이 이 파일을 import 하지 않는다.
저장소에 남기는 이유는 `anonymize_join.py` 와 같다 — 다음 회차에 라벨을 다시 뜰 때
"어떻게 익명화했더라" 를 다시 발명하지 않게 하려는 것이다.

무엇을 읽는가:
    `.planning/phases/04-banner-detection/04-RESEARCH.md` 의 **Appendix A 표 3개**.
    실코드를 이 스크립트에 박지 않는다 — 박으면 익명화가 무의미해지고,
    회차가 바뀔 때 두 곳(문서·스크립트)을 같이 고쳐야 한다.
      ① 라벨 표        `| # | 판매자상품코드 | 장수 | 배너(B) | 무내용(V) | 경계(X) |`
      ② 배너 9장 내용   `| 상품 | 순번 | OCR 첫 줄 | 왜 배너로 봤나 |`
      ③ 경계 4장        `| 상품 | 순번 | 내용 | 물어볼 것 |`
    ②③ 의 `상품` 칸은 ① 의 `#` 를 가리킨다.

무엇을 지우는가:
    - 판매자상품코드 → `zz01`~`zzNN`. 매핑은 **정렬된 실코드 목록의 인덱스**라
      같은 입력이면 언제나 같은 출력이 나온다(결정적).

무엇을 보존하는가:
    - 이미지 **순번**(`renderContent` 안 `<img>` 의 0부터의 순서). 라벨이 순번에 걸려 있다
    - 장수 · 배너/무내용/경계 집합 · OCR 첫 줄 원문 · 경계 4장의 질문 원문
      (04-04 의 미탐 0 회귀가 OCR 첫 줄을 분자로 쓴다 — 지우면 그 테스트가 공집합을 통과한다)

⚠️ 이 라벨은 **리서처(Claude)의 시각 판단이다. 용팀장의 라벨이 아니다.**
   회귀 정답지로 쓰되 게이트 통과 근거로 쓰지 마라 (RESEARCH Appendix A 머리말 · A1).

🔴 **`용팀장라벨` 절은 이 스크립트가 만들지 않는다.** 그건 `anonymize_user_labels.py`
   가 `webapp.db` 에서 읽어 넣는 **사람의 판단**이고, 여기서 다시 만들 수 없다.
   그래서 이 스크립트는 기존 파일의 `용팀장라벨` 키를 **읽어서 그대로 되돌려 놓는다**
   (`main()` 참조). 안 그러면 리서치 라벨을 다시 뜨는 순간 사람 라벨 34건이 증발한다.

사용:
    .venv-web/bin/python3 webapp/tests/fixtures/anonymize_labels.py
    (상품 수 · 합계를 stdout 에 찍는다)
"""
import json
import sys
from pathlib import Path

# 저장소 루트. `anonymize_join.py` 와 같은 관례다 — 경로를 박지 않는다.
루트 = Path(__file__).resolve().parents[3]

리서치 = 루트 / ".planning" / "phases" / "04-banner-detection" / "04-RESEARCH.md"
출력 = Path(__file__).resolve().parent / "banner_labels.json"

회차 = "2026-09-20"
조인산출물 = "join_323b1918"

주의문 = (
    "이것은 리서처(Claude)의 시각 판단이다. 용팀장의 라벨이 아니다 — "
    "회귀 정답지로 쓰되 게이트 통과 근거로 쓰지 마라"
)

# 머리말 바로 아래에 붙는 한 줄. 파일을 처음 여는 사람이 두 절의 무게 차이를 먼저 읽는다.
용팀장주의문 = (
    "아래 `용팀장라벨` 절은 **사람의 판단이다 — 이쪽이 더 무겁다.** "
    "2026-09-22 전수 검수(D-03a)에서 용팀장이 실제로 클릭한 34건이고, "
    "`anonymize_user_labels.py` 가 만든다. 이 절과 위 리서처 라벨이 어긋나면 이쪽이 정본이다"
)

# 표를 고르는 열쇠. 헤더 칸들이 이것과 정확히 같은 표만 읽는다 —
# "비슷한 표를 잘못 집어 조용히 다른 숫자를 픽스처에 넣는" 사고를 막는다.
_라벨헤더 = ["#", "판매자상품코드", "장수", "배너(B)", "무내용(V)", "경계(X)"]
_배너헤더 = ["상품", "순번", "OCR 첫 줄", "왜 배너로 봤나"]
_경계헤더 = ["상품", "순번", "내용", "물어볼 것"]


def _칸들(줄: str) -> list:
    """`| a | b |` → `["a", "b"]`. 백틱은 전부 걷어낸다(표기용이지 값이 아니다)."""
    조각 = 줄.strip().strip("|").split("|")
    return [c.strip().replace("`", "") for c in 조각]


def _구분행(칸들: list) -> bool:
    """`|---|---|` 행인가."""
    return bool(칸들) and all(set(c) <= set("-: ") and c for c in 칸들)


def 표읽기(본문: str, 헤더: list) -> list:
    """헤더가 정확히 일치하는 표의 데이터 행(칸 리스트)들을 돌려준다.

    **못 찾으면 예외다.** 빈 리스트로 돌려주면 픽스처가 조용히 비고,
    그걸 단언하는 테스트가 공집합을 통과한다 — 이 저장소가 CR-01~03 에서 배운 실패 모양이다.
    """
    줄들 = 본문.splitlines()
    for i, 줄 in enumerate(줄들):
        if not 줄.lstrip().startswith("|"):
            continue
        if _칸들(줄) != 헤더:
            continue
        행들 = []
        for 다음 in 줄들[i + 1:]:
            if not 다음.lstrip().startswith("|"):
                break
            칸 = _칸들(다음)
            if _구분행(칸):
                continue
            행들.append(칸)
        if not 행들:
            raise ValueError(f"표는 찾았는데 데이터 행이 0건이다: {헤더}")
        return 행들
    raise ValueError(f"표를 못 찾았다: {헤더} — 04-RESEARCH.md Appendix A 가 바뀌었는지 봐라")


def 순번들(칸: str) -> list:
    """`"0, 1, 3"` → `[0, 1, 3]`. `—`(없음)는 빈 리스트."""
    나온것 = []
    for 조각 in 칸.replace("—", "").split(","):
        조각 = 조각.strip()
        if not 조각:
            continue
        나온것.append(int(조각))
    return 나온것


def 만들기(본문: str) -> dict:
    라벨행 = 표읽기(본문, _라벨헤더)
    배너행 = 표읽기(본문, _배너헤더)
    경계행 = 표읽기(본문, _경계헤더)

    # 실코드 → zzNN. **정렬된 목록의 인덱스**라 같은 입력이면 같은 출력이다.
    실코드 = [칸[1] for 칸 in 라벨행]
    코드맵 = {코드: f"zz{i:02d}" for i, 코드 in enumerate(sorted(실코드), start=1)}

    # Appendix 표의 `#` → 익명코드. ②③ 표가 이 번호로 상품을 가리킨다.
    번호맵 = {칸[0]: 코드맵[칸[1]] for 칸 in 라벨행}

    상품 = []
    for 칸 in 라벨행:
        상품.append({
            "코드": 코드맵[칸[1]],
            "장수": int(칸[2]),
            "배너": 순번들(칸[3]),
            "무내용": 순번들(칸[4]),
            "경계": 순번들(칸[5]),
        })

    배너본문 = [{
        "코드": 번호맵[칸[0]],
        "순번": int(칸[1]),
        "ocr_첫줄": 칸[2],
        "왜배너로봤나": 칸[3],
    } for 칸 in 배너행]

    경계본문 = [{
        "코드": 번호맵[칸[0]],
        "순번": int(칸[1]),
        "내용": 칸[2],
        "물어볼것": 칸[3],
    } for 칸 in 경계행]

    배너수 = sum(len(p["배너"]) for p in 상품)
    무내용수 = sum(len(p["무내용"]) for p in 상품)
    경계수 = sum(len(p["경계"]) for p in 상품)
    장수합계 = sum(p["장수"] for p in 상품)

    # **제품 274 는 빼기로 구하지 않는다.** 장수합계(312) 중 치수를 확보한 것이 308 이고,
    # 라벨 모수는 그 308 이다. 312 에서 빼면 278 이 나와 조용히 4장이 틀린다.
    라벨모수 = 308
    제품수 = 라벨모수 - 배너수 - 무내용수 - 경계수

    return {
        "주의": 주의문,
        "주의_용팀장라벨": 용팀장주의문,
        "출처": "04-RESEARCH.md Appendix A — 리서치 라벨 원본",
        "회차": 회차,
        "조인산출물": 조인산출물,
        "생성방법": ".venv-web/bin/python3 webapp/tests/fixtures/anonymize_labels.py",
        "익명화": "판매자상품코드 → zzNN (정렬된 실코드 목록의 인덱스). 순번·장수·OCR 원문은 보존",
        "순번규약": "renderContent 안 <img> 의 0부터의 순서. 여기 없는 순번은 전부 제품 이미지",
        "상품": 상품,
        "배너본문": 배너본문,
        "경계본문": 경계본문,
        "합계": {
            "상품": len(상품),
            "장수합계": 장수합계,
            "라벨모수": 라벨모수,
            "배너": 배너수,
            "무내용": 무내용수,
            "경계": 경계수,
            "제품": 제품수,
            "_모수주석": (
                f"장수합계 {장수합계} 중 치수를 확보한 {라벨모수} 장이 라벨 모수다. "
                "차이 4장은 다운로드·치수 확보 실패분이고 판정에서 뺐다"
            ),
        },
    }


def main() -> int:
    try:
        본문 = 리서치.read_text(encoding="utf-8")
        결과 = 만들기(본문)
    except Exception as e:                      # noqa: BLE001 — 도구라 원인만 보이면 된다
        print(f"라벨 픽스처 생성 실패: {e}", file=sys.stderr)
        return 1

    # **사람 라벨을 덮지 않는다.** `용팀장라벨` 은 이 스크립트가 만들 수 없는 절이고
    # (DB 와 회차 캐시가 정본이다), 여기서 날리면 다시 만들려고 사람을 또 앉혀야 한다.
    보존 = None
    if 출력.is_file():
        try:
            보존 = json.loads(출력.read_text(encoding="utf-8")).get("용팀장라벨")
        except (OSError, ValueError) as e:
            # 못 읽었으면 **조용히 넘어가지 않는다** — 덮어쓰기 직전이다.
            print(f"경고: 기존 픽스처를 못 읽어 `용팀장라벨` 보존을 건너뛴다: {e}",
                  file=sys.stderr)
    if 보존 is not None:
        결과["용팀장라벨"] = 보존

    출력.write_text(json.dumps(결과, ensure_ascii=False, indent=1), encoding="utf-8")
    합 = 결과["합계"]
    print(f"상품: {합['상품']}")
    print(f"배너 {합['배너']} · 무내용 {합['무내용']} · 경계 {합['경계']} · 제품 {합['제품']}")
    print(f"배너본문 {len(결과['배너본문'])} · 경계본문 {len(결과['경계본문'])}")
    print(f"용팀장라벨 보존: {'예' if 보존 is not None else '아니오 (원래 없었다)'}")
    print(f"저장: {출력}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전수 검수 결과(용팀장 라벨) → `banner_labels.json` 의 `용팀장라벨` 절 재생성.

**이 페이즈의 가장 큰 자산이 이 절이다.** 어휘군은 기계가 만들었지만, 어느 장이
배너인지는 사람만 말할 수 있다(D-03a). 2026-09-22 전수 검수에서 용팀장이 실제로
클릭한 34건이 여기 들어간다.

`anonymize_labels.py` 와 무엇이 다른가:
  · 저쪽은 **리서처(Claude)의 시각 판단**을 `04-RESEARCH.md` Appendix A 에서 읽는다
  · 이쪽은 **사람의 판단**을 `webapp.db` 의 `banner_label` · `banner_confirm` 에서 읽는다
  · 두 절은 한 파일에 나란히 산다. 지우지 말고 덧붙인다 — 어느 쪽이 무거운지는
    파일 머리말이 말한다

무엇을 읽는가:
    ① `webapp.db` — `banner_label`(사람이 뒤집은 장) · `banner_confirm`(줄을 봤다는 근거)
    ② 배너 스캔 산출물 JSON — **경로를 glob 으로 찾지 마라.** 죽은 잡도 반쯤 쓴
       파일을 남긴다(`webapp/jobs.py::latest_done` docstring). 정본은 잡 레지스트리다:

           .venv-web/bin/python3 -c "from webapp import jobs; \
             print(jobs.latest_done('banner_scan')['result_path'])"

       그 경로를 `--result-path` 로 넘긴다. 이 스크립트가 직접 `jobs` 를 import 하지
       않는 이유는 **venv 가 둘이기 때문**이다 — `webapp.jobs` 는 pydantic 을 끌고
       오는데 `.venv`(CLI)에는 없다. 그런데 OCR(`pyobjc-framework-Vision`)은 `.venv`
       에만 있다. 두 요구가 한 인터프리터에서 만나지 않으므로 경로를 손으로 건넨다.
    ③ 캐시 원본 — 미탐 장의 OCR 을 다시 뜬다. **네트워크 0 · 크레딧 0**,
       디스크에 이미 있는 원본만 읽는다

무엇을 지우는가:
    - 판매자상품코드 → 익명코드.
      · 리서치 16상품에 있던 코드는 `anonymize_labels.py` 와 **같은 `zzNN`** 을 쓴다
        (그래야 두 절이 같은 상품을 가리킬 때 사람이 알아본다)
      · 그 밖의 회차 상품은 `yyNN` — 회차 산출물의 실코드를 정렬한 인덱스다.
        `zz` 와 번호 공간이 겹치지 않게 접두사를 갈랐다
    - 타오바오상품번호는 아예 싣지 않는다 (상품키로만 쓰고 버린다)

무엇을 보존하는가:
    - 이미지 **순번** · 사람 판정 · 기계 판정과 사유 · 상세상태(중국어원본/단순번역만)
    - 미탐 장의 **OCR 앞 6줄**. 이게 없으면 "어휘군이 왜 놓쳤나"를 다음 사람이
      다시 OCR 해서 알아내야 한다. 회귀 테스트도 이 문자열을 분자로 쓴다
      (`test_용팀장라벨_미탐을_어휘군이_잡는다`)

⚠️ 이 스크립트는 **로컬 런타임 상태에 의존한다** — `webapp.db` 의 라벨 행과
   회차 캐시가 살아 있어야 돈다. 다른 기계에서는 못 돈다. 그래서 산출물인
   `banner_labels.json` 을 커밋한다(스크립트만 커밋하는 게 아니다).

사용:
    .venv-web/bin/python3 -c "from webapp import jobs; \
      print(jobs.latest_done('banner_scan')['result_path'])"
    .venv/bin/python3 webapp/tests/fixtures/anonymize_user_labels.py \
      --result-path <위에서 나온 경로> [--run-dir 2026-09-20]
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

루트 = Path(__file__).resolve().parents[3]
if str(루트) not in sys.path:
    sys.path.insert(0, str(루트))
스캐너디렉터리 = 루트 / ".claude" / "skills" / "bulsaja-detail-page" / "scripts"
if str(스캐너디렉터리) not in sys.path:
    sys.path.insert(0, str(스캐너디렉터리))

import banner_scan as bs                                    # noqa: E402
from webapp import banner, banner_store, settings           # noqa: E402

출력 = Path(__file__).resolve().parent / "banner_labels.json"
리서치 = 루트 / ".planning" / "phases" / "04-banner-detection" / "04-RESEARCH.md"

주의문 = (
    "`용팀장라벨` 절은 **사람의 판단이다 — 이쪽이 더 무겁다.** 위 `상품`·`배너본문`·"
    "`경계본문` 은 리서처(Claude)의 시각 판단이고, 이 절은 2026-09-22 전수 검수에서 "
    "용팀장이 실제로 클릭한 것이다. 둘이 어긋나면 이쪽이 정본이다"
)

# 검수 화면에 띄웠던 경계 4장. 무엇을 물었는지는 `04-RESEARCH.md` Appendix A 가 정본이고,
# 여기엔 **용팀장이 답한 것**을 싣는다. 답은 사람 입에서 나왔으므로 기계가 다시 못 만든다.
경계4장_답 = [
    ("dnb2lYw0omRnoG121KzBL", 6, "브랜드 수상 배너(제품이 크게 나옴)", "제품"),
    ("fElaVlxOzkeSVkDotMrAJ", 0, "첫 장 타이틀 히어로", "제품"),
    ("sLix0885VmdKsGxunAznE", 0, "장식 포스터(제품이 나옴)", "제품"),
    ("sLix0885VmdKsGxunAznE", 4, "사용 장면 배너(제품은 안 나옴)", "배너"),
]

OCR_보존줄수 = 6


def 리서치코드맵() -> dict:
    """`anonymize_labels.py` 와 **똑같은** zzNN 매핑을 다시 만든다.

    매핑을 복제하지 않고 그쪽 함수를 재사용한다 — 두 곳에 같은 규칙을 적어 두면
    언젠가 한쪽만 고쳐진다.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import anonymize_labels as A

    라벨행 = A.표읽기(리서치.read_text(encoding="utf-8"), A._라벨헤더)
    실코드 = [칸[1] for 칸 in 라벨행]
    return {코드: f"zz{i:02d}" for i, 코드 in enumerate(sorted(실코드), start=1)}


def 코드맵만들기(회차코드들: list) -> dict:
    """회차 전체 실코드 → 익명코드. 리서치 16 은 zzNN 재사용, 나머지는 yyNN."""
    맵 = 리서치코드맵()
    나머지 = sorted(c for c in 회차코드들 if c not in 맵)
    for i, 코드 in enumerate(나머지, start=1):
        맵[코드] = f"yy{i:02d}"
    return 맵


def ocr요약(캐시루트: str, 회차: str, 상품순번: int, 장순번: int, revision: int):
    """미탐 장을 캐시 원본에서 다시 OCR 해 앞 몇 줄을 돌려준다.

    **못 읽으면 사유 문자열을 돌려준다.** 빈 문자열로 접지 마라 — 빈 값을 분자로 쓰는
    회귀 테스트는 공집합을 통과한다(이 저장소가 CR-01~03 에서 배운 실패 모양).
    """
    경로 = bs.원본경로(캐시루트, 회차, 상품순번, 장순번)
    if not Path(경로).exists():
        return None, "원본없음"
    try:
        줄들 = bs.ocr_2패스(경로, revision=revision)
    except Exception as e:                       # noqa: BLE001 — 도구라 원인만 보이면 된다
        return None, f"OCR실패:{type(e).__name__}"
    if not 줄들:
        return None, "OCR글자0"
    return " / ".join(str(x) for x in 줄들[:OCR_보존줄수]), None


def 만들기(산출물경로: str, 회차: str) -> dict:
    문서 = json.loads(Path(산출물경로).read_text(encoding="utf-8"))
    if 문서.get("run_dir") != 회차:
        raise ValueError(f"산출물 회차가 {문서.get('run_dir')!r} 인데 {회차!r} 을 달라고 했다")

    라벨 = banner_store.라벨읽기(회차)
    확인 = banner_store.확인읽기(회차)
    집계 = banner.게이트집계(문서, 라벨, 확인)

    코드맵 = 코드맵만들기([p["판매자상품코드"] for p in 문서["상품"]])
    # 캐시 루트는 `jobs.banner_dir()` 이 정본이지만 `webapp.jobs` 는 pydantic 을 끌고 온다
    # (이 스크립트는 `.venv` 로 돈다). `banner_store.db_path()` 와 같은 규칙으로 세 줄을
    # 복제한다 — 설정에 적힌 상대경로를 저장소 루트에 붙인다.
    캐시설정 = Path(settings.cfg("banner_cache_dir",
                             settings.DEFAULTS["banner_cache_dir"])).expanduser()
    캐시루트 = str(캐시설정 if 캐시설정.is_absolute() else 루트 / 캐시설정)
    revision = int(문서["판정규칙"]["vision_revision"])

    # 상품키 → (상품순번, 상품). 물갈이 사본은 첫 사본을 대표로 삼는다 (게이트집계와 같은 규약).
    대표: dict[str, tuple] = {}
    for 상품순번, p in enumerate(문서["상품"]):
        키 = banner.상품키(p)
        대표.setdefault(키, (상품순번, p))
    코드별 = {p["판매자상품코드"]: (i, p) for i, p in 대표.values()}
    확인됨 = {str(k) for k in 확인}

    # 바구니 넷. **`else` 하나로 몰지 마라** — `게이트집계` 의 `무내용뒤집기` 는
    # `사람 != 기계 and 무내용 in (사람, 기계)` 이지 '미탐도 오탐도 아닌 것'이 아니다.
    # 둘을 같게 두면 픽스처 합계가 게이트 숫자와 조용히 어긋난다.
    미탐, 오탐, 무내용뒤집기, 기계배너확인 = [], [], [], []
    db = sqlite3.connect(str(banner_store.db_path()))
    try:
        행들 = db.execute(
            "select 판매자상품코드, 이미지순번, 사람판정 from banner_label "
            "where run_dir = ? order by 판매자상품코드, 이미지순번", (회차,)).fetchall()
    finally:
        db.close()
    if not 행들:
        raise ValueError(f"{회차} 회차의 banner_label 행이 0건이다 — "
                         "빈 절을 픽스처에 넣지 마라(공집합을 통과하는 테스트가 생긴다)")

    for 코드, 순번, 사람 in 행들:
        if 코드 not in 코드별:
            raise ValueError(f"라벨에 있는 {코드} 가 산출물에 없다 — 회차가 어긋났다")
        상품순번, p = 코드별[코드]
        장 = next((c for c in p["장"] if c["순번"] == 순번), None)
        if 장 is None:
            raise ValueError(f"{코드}:{순번} 장이 산출물에 없다")
        항목 = {
            "코드": 코드맵[코드],
            "순번": 순번,
            "사람판정": 사람,
            "기계판정": 장.get("판정"),
            "기계사유": 장.get("사유"),
            "상세상태": p.get("상세상태"),
        }
        기계 = 장.get("판정")
        if 사람 == banner.배너 and 기계 != banner.배너:
            요약, 사유 = ocr요약(캐시루트, 회차, 상품순번, 순번, revision)
            항목["ocr_앞줄"] = 요약
            항목["ocr_실패사유"] = 사유
            항목["어휘군_확장후"] = bs.어휘군걸림([요약]) if 요약 else []
            미탐.append(항목)
        elif 사람 == banner.제품 and 기계 == banner.배너:
            오탐.append(항목)
        elif 사람 == banner.배너 and 기계 == banner.배너:
            # 사람이 기계와 같은 답을 눌렀다. 어느 분자에도 안 들어가지만
            # "이 장은 사람이 직접 배너라고 확인했다"는 근거라 버리지 않는다.
            기계배너확인.append(항목)
        # 나머지(무내용 관련)는 아래에서 따로 센다 — 바구니가 겹칠 수 있기 때문이다.
        if 사람 != 기계 and banner.무내용 in (사람, 기계):
            무내용뒤집기.append(항목)

    경계 = [{"코드": 코드맵.get(코드, "(회차 밖)"), "순번": 순번, "무엇": 무엇,
            "기계": (lambda 장: 장.get("판정") if 장 else None)(
                next((c for c in 코드별[코드][1]["장"] if c["순번"] == 순번), None)
                if 코드 in 코드별 else None),
            "용팀장": 답}
           for 코드, 순번, 무엇, 답 in 경계4장_답]

    미검수 = [{"코드": 코드맵[p["판매자상품코드"]], "스킵사유": p.get("스킵사유"),
             "장수": len(p["장"])}
            for 키, (_, p) in 대표.items() if 키 not in 확인됨]

    return {
        "주의": 주의문,
        "출처": "2026-09-20 회차 전수 검수 — 용팀장 · 2026-09-22",
        "회차": 회차,
        "배너산출물": Path(산출물경로).stem,
        "어휘군버전_검수시점": 문서["판정규칙"]["어휘군버전"],
        "생성방법": (".venv/bin/python3 webapp/tests/fixtures/anonymize_user_labels.py "
                 "--result-path <jobs.latest_done('banner_scan')['result_path']>"),
        "익명화": ("판매자상품코드 → zzNN(리서치 16 매핑 재사용) / yyNN(그 밖 회차 상품, "
               "정렬 인덱스). 타오바오상품번호는 싣지 않는다"),
        "게이트집계": 집계,
        "게이트판정": "불통과",
        "게이트판정사유": [
            f"미탐 {집계['미탐']} — 0 이 전제다",
            f"미검수상품 {집계['미검수상품']} — 전수가 전제다(D-12)",
        ],
        "미탐": 미탐,
        "오탐": 오탐,
        "무내용뒤집기": 무내용뒤집기,
        "기계배너확인": 기계배너확인,
        "경계4장": 경계,
        "미검수상품": 미검수,
        "합계": {
            "라벨행": len(행들),
            "미탐": len(미탐),
            "오탐": len(오탐),
            "무내용뒤집기": len(무내용뒤집기),
            "기계배너확인": len(기계배너확인),
            "미검수상품": len(미검수),
            "_주석": ("미탐·오탐은 `게이트집계` 와 같은 수여야 한다. 다르면 물갈이 사본 "
                    "대표 선택이 어긋난 것이다"),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="용팀장 전수 검수 라벨 → 픽스처")
    ap.add_argument("--result-path", required=True,
                    help="배너 스캔 산출물 JSON. jobs.latest_done('banner_scan') 에서 얻어라")
    ap.add_argument("--run-dir", default="2026-09-20", help="회차")
    인자 = ap.parse_args()

    try:
        절 = 만들기(인자.result_path, 인자.run_dir)
    except Exception as e:                       # noqa: BLE001 — 도구라 원인만 보이면 된다
        print(f"용팀장라벨 생성 실패: {e}", file=sys.stderr)
        return 1

    기존 = json.loads(출력.read_text(encoding="utf-8"))
    기존["용팀장라벨"] = 절
    출력.write_text(json.dumps(기존, ensure_ascii=False, indent=1), encoding="utf-8")

    합 = 절["합계"]
    print(f"미탐 {합['미탐']} · 오탐 {합['오탐']} · 무내용뒤집기 {합['무내용뒤집기']} "
          f"· 기계배너확인 {합['기계배너확인']} · 미검수 {합['미검수상품']}")
    못잡음 = [f"{m['코드']}:{m['순번']}" for m in 절["미탐"] if not m["어휘군_확장후"]]
    print(f"확장 어휘군이 여전히 못 잡는 미탐: {못잡음 or '없음'}")
    print(f"저장: {출력}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

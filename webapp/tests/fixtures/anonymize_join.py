#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실회차 `result.json` → `result_join_real.json` 익명화본 재생성 스크립트.

**테스트 트리 전용 도구다.** 웹앱 런타임이 이 파일을 import 하지 않는다.
저장소에 남기는 이유는 하나다 — 회차가 바뀌면 픽스처를 다시 떠야 하는데,
그때 "어떻게 익명화했더라" 를 다시 발명하지 않게 하려는 것이다.

왜 익명화하는가:
    픽스처에 진짜 계정 alias·진짜 광고그룹명(=회사명)을 그대로 담으면
    `test_board.py::test_계정을_코드에_박지_않는다` 같은 리터럴 가드와 충돌하고,
    저장소가 공개될 때 영업 정보가 같이 나간다.

무엇을 보존하는가 (조인 현실성이 여기 달려 있다):
    - `mallProductId` — **그대로 둔다.** 스마트스토어 공개 식별자이고,
      D-01 의 조인 키다. 바꾸면 이 픽스처로 해상률을 재볼 수 없다.
    - 광고그룹명의 **접두 포맷과 NN-N 번호** — `판매상품_15-2_…` · `20-3 …` ·
      `1000개_22-1_…` 세 포맷이 전부 실측 형태다 (D-02 번호 추출 정규식의 입력).
    - 규칙 3층 구조(`accounts.<alias>.rules.<규칙키>[]`)와 행의 지표 필드.

무엇을 지우는가:
    - 계정 alias → `zz01`·`zz02`…
    - 상품명(`title`) → `상품{n}`
    - 광고그룹명의 **회사명 부분만** → `zzfake{n}` (번호·접두는 남는다)
    - 계정 `summary` 의 매출·광고비 — 남긴 행 수만 다시 센다

사용:
    .venv-web/bin/python3 webapp/tests/fixtures/anonymize_join.py [회차명]
    (회차명을 안 주면 가장 최근 회차. 행 수를 stdout 에 찍는다)
"""
import json
import re
import sys
from pathlib import Path

# 저장소 루트를 sys.path 에 얹어 `webapp.paths` 를 쓴다.
# **경로를 박지 않는다** — 회차 경로는 workspace.toml 에서 와야 한다(paths.py 주석 참조).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from webapp import paths  # noqa: E402

# 이 픽스처가 담는 규칙. ③⑤ 가 곧 "작업 대상 후보" 다 (03-CONTEXT §domain).
대상규칙 = ("③원인분석", "⑤효자확정")

# 광고그룹명 안의 마켓번호 `NN-N`. 앞뒤에 숫자·하이픈이 붙으면 번호가 아니다 —
# `1000개_22-1_…` 의 `1000` 이 오탐되지 않게 경계를 둔다 (D-02).
번호패턴 = re.compile(r"(?<![0-9-])(\d{1,2}-\d{1,2})(?![0-9-])")

출력 = Path(__file__).resolve().parent / "result_join_real.json"
출력_그룹 = Path(__file__).resolve().parent / "bulsaja_groups_real.json"

# 불사자 마켓그룹명의 `NN번_` 접두. 이 숫자는 **마켓번호가 아니다** — 구조적 함정이라
# 익명화 후에도 남겨야 한다 (`bulsaja_groups_traps.json` 의 함정 (a)와 같은 성질).
_그룹접두패턴 = re.compile(r"^(\d{1,2}번_)")


def _광고그룹_익명화(원문: str, 회사맵: dict) -> str:
    """접두 포맷과 번호는 남기고 회사명 부분만 `zzfake{n}` 으로 바꾼다.

    번호가 아예 없는 그룹(광고 쪽 오등록)은 **번호 없음 성질을 유지한 채** 통째로 바꾼다 —
    그 성질이 JOIN-02 의 "추출실패" 사유를 만드는 입력이기 때문이다.
    """
    m = 번호패턴.search(원문)
    if not m:
        키 = ("__번호없음__", 원문)
        회사맵.setdefault(키, f"zzfake{len(회사맵) + 1:02d}")
        return 회사맵[키]

    접두 = 원문[:m.start()]          # `판매상품_` · `1000개_` · `` (빈 문자열)
    번호 = m.group(1)
    꼬리 = 원문[m.end():]            # `_제이와이이컴퍼니` · ` 온애이컴퍼니` · ``
    구분자 = 꼬리[:1] if 꼬리[:1] in ("_", " ", "-") else ""
    회사 = 꼬리[len(구분자):]
    if not 회사:
        return f"{접두}{번호}{꼬리}"
    회사맵.setdefault(("__회사__", 회사), f"zzfake{len(회사맵) + 1:02d}")
    return f"{접두}{번호}{구분자}{회사맵[('__회사__', 회사)]}"


def 익명화(회차: str) -> dict:
    """회차 `result.json` 의 ③⑤ 행만 남긴 익명화 dict 를 만든다."""
    원본 = json.loads((paths.run_dir_path(회차) / "result.json").read_text(encoding="utf-8"))

    회사맵: dict = {}
    상품맵: dict = {}
    계정맵: dict = {}
    나온것 = {"generated": 원본.get("generated"), "accounts": {}}

    for i, alias in enumerate(sorted((원본.get("accounts") or {}).keys()), start=1):
        계정맵[alias] = f"zz{i:02d}"

    for alias in sorted((원본.get("accounts") or {}).keys()):
        규칙들 = (원본["accounts"][alias].get("rules") or {})
        새규칙 = {}
        건수 = 0
        for 키 in 대상규칙:
            새행들 = []
            for 행 in (규칙들.get(키) or []):
                새행 = dict(행)
                if "adGroup" in 새행:
                    새행["adGroup"] = _광고그룹_익명화(str(새행["adGroup"]), 회사맵)
                if "title" in 새행:
                    상품맵.setdefault(새행["title"], f"상품{len(상품맵) + 1}")
                    새행["title"] = 상품맵[새행["title"]]
                새행들.append(새행)
            새규칙[키] = 새행들
            건수 += len(새행들)
        # summary 는 매출·광고비를 담고 있다 — 남긴 행 수로만 다시 쓴다
        나온것["accounts"][계정맵[alias]] = {"summary": {"ads": 건수}, "rules": 새규칙}

    return 나온것


# ── 불사자 마켓그룹 목록 익명화 (`bulsaja_groups_real.json`) ─────────────────

def _마켓그룹_익명화(원문: str, 카운터: list) -> str:
    """번호(`NN-N`)는 **글자 그대로 보존**하고 나머지 이름만 `zzfake` 로 바꾼다.

    해상률은 번호로만 결정된다 — 그래서 이름을 통째로 가짜로 만들어도 회귀가 재현된다.
    반대로 번호를 바꾸면 이 픽스처는 아무것도 지키지 못한다.

    보존하는 성질 둘:
      · `NN번_` 접두 — 이 숫자는 마켓번호가 **아니다**(함정 (a)). 남겨야 오탐 회귀가 산다
      · 번호가 아예 없는 그룹 — 그 성질을 유지한 채 통째로 바꾼다(번호가 생기면 안 된다)

    ⚠️ `zzfake` 와 번호 사이에 글자 경계가 있어야 한다. `zzfake0715-2` 처럼 숫자를
       바로 붙이면 `anonymize_join` 의 경계 있는 번호패턴이 `15-2` 를 못 뽑는다.
       그래서 `zzfake` 뒤에 바로 번호를 붙인다 — `zzfake15-2` (traps 픽스처와 같은 모양).
    """
    앞 = _그룹접두패턴.match(원문)
    접두 = 앞.group(1) if 앞 else ""
    m = 번호패턴.search(원문)
    if not m:
        카운터[0] += 1
        return f"{접두}zzfake{카운터[0]:02d}"
    return f"{접두}zzfake{m.group(1)}"


def 그룹익명화(조인산출물: dict) -> dict:
    """조인 잡 산출물(`join_<job>.json`)의 `마켓그룹` → 익명화 픽스처 dict.

    `groupId` 는 연번 가짜값으로 갈아끼운다 — 그룹 ID 는 화면에도 코드에도 남을 값이
    아니고, 실물 ID 가 저장소에 남으면 다음 사람이 그걸 리터럴로 베낀다.
    순서는 원본을 그대로 따른다(정렬하면 실물 순서 정보가 사라지는 대신 재현성이
    좋아지는데, 여기서는 재현성이 이미 파일로 고정돼 있다).
    """
    그룹들 = (조인산출물 or {}).get("마켓그룹") or []
    카운터 = [0]
    나온것 = []
    for i, g in enumerate(그룹들, start=1):
        if not isinstance(g, dict):
            continue
        나온것.append({
            "groupId": str(9000000 + i),        # 연번 가짜값 — 실물 ID 를 남기지 않는다
            "그룹명": _마켓그룹_익명화(str(g.get("그룹명") or ""), 카운터),
        })
    return {
        "_주석": [
            "실회차 불사자 마켓그룹 목록(`bulsaja_market_groups`)의 익명화본.",
            "해상률 회귀(`test_실회차_해상률`)의 짝이다 — `result_join_real.json` 과 함께 쓴다.",
            "보존: 마켓번호 `NN-N` 은 **글자 그대로**. 해상률이 번호로만 결정되기 때문이다.",
            "보존: `NN번_` 접두 — 이 숫자는 마켓번호가 아니다(오탐 회귀의 입력).",
            "지움: 그룹명의 실물 이름 → `zzfake`. groupId → 연번 가짜값(9000001~).",
            "재생성: .venv-web/bin/python3 webapp/tests/fixtures/anonymize_join.py --groups <join_*.json>",
        ],
        "그룹": 나온것,
    }


def main() -> int:
    # `--groups <join 산출물>` 모드 — 불사자 마켓그룹 픽스처만 다시 뜬다.
    if len(sys.argv) > 1 and sys.argv[1] == "--groups":
        try:
            경로 = Path(sys.argv[2])
            문서 = json.loads(경로.read_text(encoding="utf-8"))
            결과 = 그룹익명화(문서)
        except IndexError:
            print("사용: anonymize_join.py --groups <join_*.json>", file=sys.stderr)
            return 2
        except Exception as e:                  # noqa: BLE001 — 도구라 원인만 보이면 된다
            print(f"그룹 익명화 실패: {e}", file=sys.stderr)
            return 1
        출력_그룹.write_text(json.dumps(결과, ensure_ascii=False, indent=1), encoding="utf-8")
        번호있음 = sum(1 for g in 결과["그룹"] if 번호패턴.search(g["그룹명"]))
        print(f"그룹: {len(결과['그룹'])}")
        print(f"번호 있는 그룹: {번호있음}")
        print(f"저장: {출력_그룹}")
        return 0

    try:
        회차 = sys.argv[1] if len(sys.argv) > 1 else (paths.scan_run_dirs() or [None])[0]
        if not 회차:
            print("회차가 없다 — result.json 이 있는 run-dir 이 하나도 없다", file=sys.stderr)
            return 2
        결과 = 익명화(회차)
    except Exception as e:                      # noqa: BLE001 — 도구라 원인만 보이면 된다
        print(f"익명화 실패: {e}", file=sys.stderr)
        return 1

    출력.write_text(json.dumps(결과, ensure_ascii=False, indent=1), encoding="utf-8")
    행수 = sum(len(rows) for a in 결과["accounts"].values() for rows in a["rules"].values())
    print(f"회차: {회차}")
    print(f"계정: {len(결과['accounts'])}")
    print(f"③⑤ 행수: {행수}")
    print(f"저장: {출력}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

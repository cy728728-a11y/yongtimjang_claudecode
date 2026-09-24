# -*- coding: utf-8 -*-
"""옛/새 배너 산출물 × 사람 라벨 → **사람이 다시 봐야 할 장** 목록 (04-11 Task 1).

왜 필요한가: `게이트집계` 는 "확인함을 누른 상품의 라벨 없는 장 = 기계 판정에 동의" 로 읽는다.
재측정으로 기계 판정이 바뀌면 그 동의가 **사람이 본 적 없는 새 판정**에 자동으로 붙는다.
이 스크립트는 그 장을 전수로 뽑는다 — 이 목록을 사람이 보지 않으면 새 게이트 숫자는 근거가 없다.

· **재검수 대상** = 확인된 상품의 장 중
    (옛 판정 ≠ 새 판정 AND 그 장에 명시 라벨 없음) 또는 (새 판정 미판정 AND 사유에 `2차 판정 실패`)
· **참고 구간** (대상과 섞지 않는다)
    A. 명시 라벨이 있는데 기계 판정이 바뀐 장 — 게이트는 사람 값을 쓰므로 숫자엔 영향 없음
    B. 오라벨 2장 (판매자상품코드 `spG75IlK*` 0·1번, GATE §10-3 — 플랜의 '불사자코드'는 오기)
    C. 새 산출물 출처 `어휘군` 인데 비전은 `제품` 이라 한 장 — 오탐 후보 (GATE §12-3)

상품 매칭은 `webapp.banner.상품키()` (타오바오상품번호 → 불사자코드 폴백), 물갈이 사본은
`게이트집계` 와 같이 **첫 사본만** 쓴다. 실코드를 익명화하지 않는다(픽스처가 아니다).

실행: `.venv-web/bin/python3 .planning/phases/04-banner-detection/evidence/recheck_list.py \
         --old <옛 산출물> --new <새 산출물> --run-dir 2026-09-20`
"""
import argparse
import json
import os
import sys

# 저장소 루트를 import 경로에 올린다 (cwd 와 무관하게 `webapp` 을 찾도록)
_루트 = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "..", "..", ".."))
if _루트 not in sys.path:
    sys.path.insert(0, _루트)

from webapp import banner, banner_store  # noqa: E402

장당초 = 5          # 사람이 장 하나 보는 데 드는 가정 시간 (초)
오라벨_접두 = "spG75IlK"
오라벨_순번 = {0, 1}
실패표지 = "2차 판정 실패"


def _읽기(경로: str, 회차: str) -> dict:
    """산출물 JSON 을 읽고 회차를 확인한다. 못 읽으면 즉시 멈춘다."""
    try:
        with open(경로, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"⛔ 산출물을 못 읽었다: {경로} — {e}")
    if not isinstance(d.get("상품"), list):
        raise SystemExit(f"⛔ 산출물에 '상품' 리스트가 없다: {경로}")
    if str(d.get("run_dir") or "") != 회차:
        raise SystemExit(f"⛔ 산출물 회차 {d.get('run_dir')!r} ≠ --run-dir {회차!r}: {경로}")
    return d


def _대표(산출물: dict) -> tuple[dict, list]:
    """상품키 → 첫 사본. `게이트집계` 와 같은 대표 규칙."""
    대표, 순서 = {}, []
    for 상품 in 산출물["상품"]:
        키 = banner.상품키(상품)
        if 키 not in 대표:
            대표[키] = 상품
            순서.append(키)
    return 대표, 순서


def _장맵(상품: dict) -> dict:
    """순번 → 장. 장 목록이 없으면 빈 dict (스킵 상품도 장은 깐다 — 없으면 이상)."""
    나온것 = {}
    for 장 in 상품.get("장") or []:
        try:
            나온것[int(장.get("순번"))] = 장
        except (TypeError, ValueError):
            continue
    return 나온것


def _칸(값, 최대: int = 120) -> str:
    """마크다운 표 칸 — 파이프·줄바꿈을 지우고 길이를 자른다."""
    s = "" if 값 is None else str(값)
    s = s.replace("|", "／").replace("\n", " ").strip()
    return s if len(s) <= 최대 else s[:최대 - 1] + "…"


def _왜(옛: str, 새장: dict) -> str:
    """출처·사유에서 기계적으로 "왜 봐야 하나" 를 만든다."""
    출처 = 새장.get("출처")
    사유 = str(새장.get("사유") or "")
    if 새장.get("판정") == banner.미판정 and 실패표지 in 사유:
        return "2차 판정 실패 — 값을 정해야 게이트 분모에 들어간다"
    if 출처 == "비전":
        return "어휘군이 놓친 것을 비전이 배너라 했다 — 맞으면 미탐이 줄어든 것"
    if 출처 == "뒤집기":
        return "워터마크·공장직판 오탐을 되돌렸다 — 진짜 배너가 아닌지 봐라"
    return f"판정이 {옛} → {새장.get('판정')} 로 바뀌었다 (출처 {출처}) — 사람이 본 적 없는 판정"


def _행(상품: dict, 순번: int, 옛장: dict | None, 새장: dict, 왜: str) -> dict:
    """표 한 줄."""
    일차 = 새장.get("1차") if isinstance(새장.get("1차"), dict) else {}
    이차 = 새장.get("2차") if isinstance(새장.get("2차"), dict) else {}
    옛판정 = 옛장.get("판정") if 옛장 else None
    return {
        "판매자상품코드": 상품.get("판매자상품코드") or "",
        "불사자코드": str(상품.get("불사자코드") or "")[:8],
        "장": 순번,
        "1차 사유": 일차.get("사유") if 일차 else (옛장 or {}).get("사유"),
        "전후": f"{옛판정} → {새장.get('판정')}",
        "출처": 새장.get("출처"),
        "2차 근거": 이차.get("근거") or (f"실패: {이차.get('실패')}" if 이차.get("실패") else None),
        "왜 봐야 하나": 왜,
    }


def 목록(옛: dict, 새: dict, 라벨: dict, 확인: set) -> dict:
    """재검수 대상 + 참고 구간 A·B·C 를 뽑는다."""
    옛대표, _ = _대표(옛)
    새대표, 새순서 = _대표(새)
    결과 = {"대상": [], "A_라벨있는변경": [], "B_오라벨": [], "C_오탐후보": [],
          "경고": []}

    새만 = [k for k in 새순서 if k not in 옛대표]
    옛만 = [k for k in 옛대표 if k not in 새대표]
    if 새만:
        결과["경고"].append(f"새 산출물에만 있는 상품 {len(새만)}: {', '.join(새만[:10])}")
    if 옛만:
        결과["경고"].append(f"옛 산출물에만 있는 상품 {len(옛만)}: {', '.join(옛만[:10])}")
    미확인 = [k for k in 새순서 if k not in 확인]
    if 미확인:
        결과["경고"].append(f"확인함 없는 상품 {len(미확인)} — 대상에서 빠졌다(게이트는 미검수로 센다)")

    for 키 in 새순서:
        새상품 = 새대표[키]
        옛장들 = _장맵(옛대표.get(키, {}))
        상품라벨 = {}
        try:
            상품라벨 = {int(k): v for k, v in (라벨.get(키) or {}).items()}
        except (TypeError, ValueError):
            결과["경고"].append(f"라벨 순번이 정수가 아니다: {키}")
        확인됨 = 키 in 확인
        for 순번, 새장 in sorted(_장맵(새상품).items()):
            옛장 = 옛장들.get(순번)
            옛판정 = 옛장.get("판정") if 옛장 else None
            새판정 = 새장.get("판정")
            바뀜 = 옛판정 != 새판정
            실패 = 새판정 == banner.미판정 and 실패표지 in str(새장.get("사유") or "")

            # B. 오라벨 2장 — 확인 여부·변경 여부와 무관하게 늘 싣는다
            # 플랜은 "불사자코드" 라 적었지만 파일럿 코드 `spG75IlK` 는 실측상 **판매자상품코드**
            # 앞자리다(GATE §15-1 — 둘 다 21자라 헷갈린다). 두 필드 모두 본다.
            if (any(str(새상품.get(f) or "").startswith(오라벨_접두)
                    for f in ("판매자상품코드", "불사자코드"))
                    and 순번 in 오라벨_순번):
                결과["B_오라벨"].append(_행(새상품, 순번, 옛장, 새장,
                                        f"오라벨 의심(GATE §10-3) — 현재 사람 라벨 "
                                        f"{상품라벨.get(순번, '없음')}"))
            # C. 어휘군 배너 유지 + 비전 제품 = 오탐 후보
            이차 = 새장.get("2차") if isinstance(새장.get("2차"), dict) else {}
            if 새장.get("출처") == "어휘군" and 이차.get("판정") == banner.제품:
                결과["C_오탐후보"].append(_행(새상품, 순번, 옛장, 새장,
                                         "어휘군 배너 · 비전 제품 · 뒤집기 허용군 밖 — "
                                         "오탐 후보(GATE §12-3)"))

            if not 확인됨:
                continue
            if 순번 in 상품라벨:
                if 바뀜:
                    결과["A_라벨있는변경"].append(_행(새상품, 순번, 옛장, 새장,
                                               f"사람 라벨 {상품라벨[순번]} — 게이트는 사람 값을 쓴다"))
                # 명시 라벨이 있어도 2차 실패로 미판정이면 대상으로 올린다
                if 실패:
                    결과["대상"].append(_행(새상품, 순번, 옛장, 새장, _왜(옛판정, 새장)))
                continue
            if 바뀜 or 실패:
                결과["대상"].append(_행(새상품, 순번, 옛장, 새장, _왜(옛판정, 새장)))
    return 결과


_열 = ["판매자상품코드", "불사자코드", "장", "1차 사유", "전후", "출처", "2차 근거", "왜 봐야 하나"]
_머리 = ("| 판매자상품코드 | 불사자코드(앞8) | 장 | 1차 사유 | 옛판정 → 새판정 | 출처 | "
        "2차 근거 | 왜 봐야 하나 |")


def _표(행들: list) -> str:
    """행 목록 → 마크다운 표 (상품별 정렬)."""
    if not 행들:
        return "_(없음)_\n"
    행들 = sorted(행들, key=lambda r: (r["판매자상품코드"], r["장"]))
    줄 = [_머리, "|" + "---|" * len(_열)]
    for r in 행들:
        줄.append("| " + " | ".join(_칸(r[c]) for c in _열) + " |")
    return "\n".join(줄) + "\n"


def _머리말(행들: list) -> str:
    상품수 = len({r["판매자상품코드"] for r in 행들})
    초 = len(행들) * 장당초
    return (f"상품 **{상품수}** · 장 **{len(행들)}** · 예상 소요 약 **{초 // 60}분 {초 % 60}초** "
            f"(장당 {장당초}초 가정)\n")


def 마크다운(결과: dict) -> str:
    out = ["#### 재검수 대상", _머리말(결과["대상"]), _표(결과["대상"])]
    for 제목, 키 in (("#### 참고 A — 명시 라벨이 있는데 기계 판정이 바뀐 장", "A_라벨있는변경"),
                   ("#### 참고 B — 오라벨 2장 (GATE §10-3)", "B_오라벨"),
                   ("#### 참고 C — 어휘군 배너 · 비전 제품 (오탐 후보, GATE §12-3)", "C_오탐후보")):
        out += [제목, f"장 **{len(결과[키])}**\n", _표(결과[키])]
    if 결과["경고"]:
        out.append("#### ⚠️ 경고\n" + "\n".join(f"- {w}" for w in 결과["경고"]) + "\n")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="옛/새 산출물 × 사람 라벨 → 재검수 목록")
    ap.add_argument("--old", required=True, help="옛(비교 기준) 산출물 JSON")
    ap.add_argument("--new", required=True, help="새(재측정) 산출물 JSON")
    ap.add_argument("--run-dir", required=True, help="회차 (예: 2026-09-20)")
    ap.add_argument("--json", action="store_true", help="마크다운 대신 JSON 으로 찍는다")
    인자 = ap.parse_args()
    try:
        옛 = _읽기(인자.old, 인자.run_dir)
        새 = _읽기(인자.new, 인자.run_dir)
        라벨 = banner_store.라벨읽기(인자.run_dir)
        확인 = banner_store.확인읽기(인자.run_dir)
        결과 = 목록(옛, 새, 라벨, 확인)
    except ValueError as e:
        print(f"⛔ 목록 생성 실패: {e}", file=sys.stderr)
        return 2
    if 인자.json:
        print(json.dumps(결과, ensure_ascii=False, indent=1))
    else:
        print(마크다운(결과))
    return 0


if __name__ == "__main__":
    sys.exit(main())

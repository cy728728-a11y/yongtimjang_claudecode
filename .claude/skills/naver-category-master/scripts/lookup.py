#!/usr/bin/env python3
"""카테고리 마스터 역조회 헬퍼.

경로 → 코드, 코드 → 경로, 최종차수명 → 후보 목록을 뽑는다.
다른 스킬이 subprocess 없이 `from lookup import CategoryMaster` 로 직접 쓰거나,
CLI 로 JSON in/out 하도록 둘 다 지원한다.

CLI:
    .venv/bin/python .../lookup.py --path "가구/인테리어 > 인테리어소품 > 조명 > 인테리어조명"
    .venv/bin/python .../lookup.py --code 50003340
    .venv/bin/python .../lookup.py --leaf 인테리어조명
    .venv/bin/python .../lookup.py --verify result.json   # aside-category 결과 교차검증
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MASTER = ROOT / "30-knowledge" / "39-naver-category" / "naver-category-master.json"


class CategoryMaster:
    """마스터 JSON 을 메모리에 올려 세 방향 조회를 제공한다."""

    def __init__(self, master_path=DEFAULT_MASTER):
        try:
            data = json.loads(Path(master_path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            sys.exit(f"마스터 파일 없음: {master_path}\n"
                     f"먼저 fetch_categories.py 를 돌려서 만든다.")
        except (OSError, json.JSONDecodeError) as e:
            sys.exit(f"마스터 파일 읽기 실패: {e}")

        self.rows = data["카테고리"]
        self.path_to_code = data["경로to코드"]
        self.code_to_row = {str(r["id"]): r for r in self.rows}
        # 최종차수명은 중복이 많다(예 '기타'). 그래서 값이 리스트다.
        self.leaf_to_rows = {}
        for r in self.rows:
            self.leaf_to_rows.setdefault(r.get("name", ""), []).append(r)

    def code_of(self, path):
        """정규화 경로('A > B > C') → 코드. 없으면 None."""
        norm = " > ".join(p.strip() for p in str(path).split(">") if p.strip())
        return self.path_to_code.get(norm)

    def path_of(self, code):
        """코드 → 정규화 경로. 없으면 None."""
        row = self.code_to_row.get(str(code))
        return row["경로정규화"] if row else None

    def by_leaf(self, leaf, last_only=True):
        """최종차수명 → 후보 행 목록. 2건 이상이면 이름만으론 확정 못 한다는 뜻."""
        rows = self.leaf_to_rows.get(str(leaf).strip(), [])
        return [r for r in rows if r.get("last")] if last_only else rows


def verify_results(master, results_path):
    """aside-category 결과 JSON 의 `카테고리코드` 를 마스터와 대조한다."""
    try:
        rows = json.loads(Path(results_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"결과 파일 읽기 실패: {e}")

    out = []
    for r in rows:
        path, code = r.get("카테고리경로"), r.get("카테고리코드")
        expected = master.code_of(path) if path else None
        if code and expected and str(code) == str(expected):
            판정 = "일치"
        elif code and expected:
            판정 = "불일치"          # 확장 코드와 마스터 코드가 다르다 → 사람이 본다
        elif not code and expected:
            판정 = "마스터로보정"     # 패널 파싱 실패건을 경로로 되살린다
        elif code and not expected:
            판정 = "마스터에없음"     # 경로 표기가 다르거나 폐지된 카테고리
        else:
            판정 = "조회불가"
        out.append({"검색어": r.get("검색어"), "카테고리경로": path,
                    "확장코드": code, "마스터코드": expected, "판정": 판정})
    return out


def main():
    ap = argparse.ArgumentParser(description="네이버 카테고리 마스터 역조회")
    ap.add_argument("--master", default=str(DEFAULT_MASTER))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--path", help="경로 → 코드")
    g.add_argument("--code", help="코드 → 경로")
    g.add_argument("--leaf", help="최종차수명 → 후보 목록")
    g.add_argument("--verify", help="aside-category 결과 JSON 교차검증")
    args = ap.parse_args()

    m = CategoryMaster(args.master)

    if args.path:
        result = {"경로": args.path, "코드": m.code_of(args.path)}
    elif args.code:
        result = {"코드": args.code, "경로": m.path_of(args.code)}
    elif args.leaf:
        rows = m.by_leaf(args.leaf)
        result = {"최종차수": args.leaf, "후보수": len(rows),
                  "후보": [{"코드": r["id"], "경로": r["경로정규화"]} for r in rows]}
    else:
        result = verify_results(m, args.verify)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

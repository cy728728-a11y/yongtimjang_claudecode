#!/usr/bin/env python3
"""스킬 description 압축 안전장치 — 트리거 어구 유실 검사 + 분량 집계.

수정 전 값은 `git show HEAD:<path>` 로 얻는다(추적 파일 전제).
description 안의 **따옴표로 묶인 어구**를 전부 뽑아 집합 비교한다. 하나라도 사라지면 FAIL.

사용:
  python desc_check.py            # 전체 검사 + 분량 표
  python desc_check.py --list     # 현재 description 크기 순위만
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # .claude/lib/costtools/ → 워크스페이스 루트
SKILLS = ROOT / ".claude/skills"

# 트리거 어구는 예외 없이 큰따옴표다 → FAIL 게이트는 큰따옴표만.
# 작은따옴표·백틱은 예시·코드 표기라 트리거가 아니지만, 사라지면 WARN 으로 알린다.
QUOTE = re.compile(r'["“”]([^"“”\n]{1,60})["“”]')
SOFT = re.compile(r"['‘’`]([^'‘’`\n]{1,60})['‘’`]")


def description(text):
    """frontmatter 에서 description 값만 뽑는다(멀티라인 `|` 블록 포함)."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    fm = text[3:end if end > 0 else len(text)]
    lines = fm.split("\n")
    out, grabbing = [], False
    for ln in lines:
        if re.match(r"^description\s*:", ln):
            grabbing = True
            rest = ln.split(":", 1)[1].strip()
            if rest and rest not in ("|", ">", "|-", ">-"):
                out.append(rest)
            continue
        if grabbing:
            # 같은 레벨의 다음 키를 만나면 종료
            if re.match(r"^[A-Za-z_-]+\s*:", ln):
                break
            out.append(ln.strip())
    return " ".join(x for x in out if x).strip()


def phrases(desc, rx=QUOTE):
    return {m.group(1).strip() for m in rx.finditer(desc) if m.group(1).strip()}


def git_show(rel):
    try:
        return subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None          # HEAD 에 없는 신규 파일


def approx_tokens(s):
    """대략치. 한글은 글자당 ~1토큰, ASCII 는 ~4자당 1토큰."""
    han = sum(1 for c in s if "가" <= c <= "힣")
    return int(han + (len(s) - han) / 3.2)


def main():
    rows, failures, warns = [], [], []
    for skill in sorted(SKILLS.glob("*/SKILL.md")):
        rel = str(skill.relative_to(ROOT))
        now = description(skill.read_text(encoding="utf-8"))
        old_text = git_show(rel)
        old = description(old_text) if old_text else ""
        if old:
            lost = phrases(old) - phrases(now)
            if lost:
                failures.append((rel, sorted(lost)))
            soft = phrases(old, SOFT) - phrases(now, SOFT)
            if soft:
                warns.append((rel, sorted(soft)))
        rows.append((skill.parent.name, approx_tokens(old), approx_tokens(now)))

    if "--list" in sys.argv:
        for name, _, now in sorted(rows, key=lambda r: -r[2]):
            print(f"{now:>5}  {name}")
        print(f"\n합계 {sum(r[2] for r in rows):,} / 스킬 {len(rows)}개")
        return

    print(f"{'스킬':28} {'전':>6} {'후':>6} {'변화':>7}")
    for name, before, now in sorted(rows, key=lambda r: -r[1]):
        d = f"{now - before:+,}" if before else "신규"
        print(f"{name:28} {before:>6,} {now:>6,} {d:>7}")
    tb, tn = sum(r[1] for r in rows), sum(r[2] for r in rows)
    print(f"{'합계':28} {tb:>6,} {tn:>6,} {tn - tb:>+7,}")

    print()
    for rel, soft in warns:
        print(f"WARN — 작은따옴표/백틱 표기 사라짐: {rel}")
        for p in soft:
            print(f"      {p}")
    if warns:
        print()
    if failures:
        print(f"FAIL — 트리거 어구 유실 {len(failures)}개 스킬")
        for rel, lost in failures:
            print(f"  {rel}")
            for p in lost:
                print(f"      사라짐: {p}")
        sys.exit(1)
    print(f"PASS — 트리거 어구 유실 0건 ({len(rows)}개 스킬)")


if __name__ == "__main__":
    main()

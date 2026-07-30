"""eroomlib.runner — 스킬을 순회시키는 러너.

스킬은 "상품 N건 처리 함수"이고, **순회는 러너가 담당한다**(계획서 §부품4).
같은 부품을 두 방향으로 돈다:

  가로(batch)   작업 1개 × 상품 전부   — 기존 run_all.py / run_names.py 에 중복 구현됨(추출 예정)
  세로(onestep) 상품 1개 × 작업 전부   — 이 패키지. 신규 상품 건별 등록용

모듈:
  onestep      — 세로 러너. 상태머신 + CLI(next/advance/record/gate/approve/hold)
  signals      — 이상 신호 판정. 승인 모드에선 표시만, 자동 모드에선 정지 조건
  approval_log — 승인 로그(그룹 시트 `00_승인로그`). 자동화 전환의 유일한 근거 데이터

설계: `00-system/04-specs/2026-07-28-헤르메스-step4-세로러너-design.md`
"""

__all__ = ["onestep", "signals", "approval_log"]

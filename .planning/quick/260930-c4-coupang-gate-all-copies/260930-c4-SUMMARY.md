---
quick: 260930-c4
subsystem: coupang-candidates gate
tags: [coupang, dedupe, fail-closed]
key-files:
  modified:
    - .claude/skills/coupang-candidates/scripts/run_coupang.py
    - .claude/skills/coupang-candidates/scripts/test_coupang_web.py
    - .claude/skills/coupang-candidates/scripts/fixtures/coupang_golden_noflag.json
decisions:
  - "쿠팡 사본 판별 = find_by_code(불사자코드) 계보 전건의 workdata uploadSelectedMarketGroupId == coupang.group_id (서버 신호). 로컬 copied.jsonl 합집합 폴백은 안 씀"
  - "계보 조회 불완전(예외·success false·더있음·0건·workdata 실패) → exit 3, 후보파일 안 씀 (D-17)"
completed: 2026-09-30
---

# Quick 260930-c4: 쿠팡 gate 가 쿠팡 그룹 밖 사본도 잡는다 — Summary

**통과 후보마다 같은 불사자코드 계보를 서버에서 전건 조회해, 마켓그룹이 쿠팡(1003308)인 사본이 하나라도 있으면 `이미복사된사본있음(<사본코드> · <상품그룹>[ 외 N건])` 으로 제외한다.**

## 쓴 신호 (읽기 전용 실측)

- `find_by_code([불사자코드])` → 계보 전건(머그컵 10 · PLIG74 28). 스마트스토어 사본·재수집분이 섞여 있어 이것만으론 판별 불가.
- `workdata.data.uploadSelectedMarketGroupId` → 마켓그룹. 파일럿 사본 `oEEpBU9Ol7PCRzQGyww2J` = 1003308(상품그룹은 `구매_가공완료`), 원본 = 1001189. 쿠팡 그룹 목록 표본 5건 모두 1003308. 상품그룹을 옮겨도 이 값은 남는다.
- workdata 에 복사원본 pid 같은 계보 필드는 없다. 서버 신호가 있으니 과거 run-dir `copied.jsonl` 합집합은 쓰지 않았다(로컬 대장 금지 원칙).

## 실데이터 검증 (읽기 전용 · feadc873 입력 사본을 scratchpad 에서 gate)

- `03lPOGjwQKt96y4uNt1Ik` 제외 — 쿠팡 사본 3건: `Y29mV64gwtqn32c3u8zQJ`, `oEEpBU9Ol7PCRzQGyww2J`, `YSq57OOi3ePSenLhzLdQD` (모두 `구매_가공완료`)
- `PLIG74ESZn2eFoq3LP8nr` 도 제외 — 쿠팡 사본 4건: `ucT7yBfYDUF9uFSBrulzm`, `xAO6B0aDrrZiXKCaEpUSW`, `3pHmXH4eAaR8U1fyfqOuC`, `zFvQ1Rp2Dbpyhg3jjyFc0` (모두 `구매`, 2026-02-11 생성 · 쿠팡 브랜드 설정)
- 결과 **통과 0 / 탈락 156** (쿠팡그룹에이미있음 85 · 마진미달 64 · 마진미상 5 · 이미복사된사본있음 2). 실제 run-dir 에는 쓰지 않았다.

## 골든

candidates·rejected 바이트, apply 미리보기 출력, gate stdout(옛 줄)은 그대로다. gate `calls` 만 의도적으로 갱신했다. 통과 후보 A·B 마다 `find_by_code` + `workdata` 가 붙기 때문이다.

## 테스트

- coupang 스킬 96 passed (신규: 머그컵 재현 · 재수집분은 안 막음 · 외 N건 · 계보 실패 4종 exit 3 · 상한 lazy · 연결/프로필 1회)
- `.venv-web/bin/pytest webapp/tests -q`: 941 passed
- `no_commit_guard.sh`: OK

## 커밋

- ff9cfd8 fix: gate 계보 대조 + 테스트 + 골든 calls
- d7eb465 fix: 제외 로그에 쿠팡 사본 전부 표시

## Deviations

없음. 실데이터에서 PLIG74 도 걸렸다(2월 쿠팡 사본 4건). 규칙이 의도대로 동작한 결과다. 이번 회차 승인 대상은 0건이 된다.

## 부수 발견 (deferred)

- gate 2차 키(`already_codes`)가 이름공간이 어긋나 사실상 죽어 있다. 스냅샷 `불사자코드` 는 workdata `uploadBulsajaCode` 에서 오는데, 그 값은 **판매자상품코드**(사본 oEEpBU = oEEpBU)다. rep 쪽 키는 find_by_code 의 `불사자코드`(l4sxx…)라서 서로 맞지 않는다. 1차 키(타오바오)와 이번 4층이 덮고 있어 당장 위험은 없다.

## Self-Check: PASSED

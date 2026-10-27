# 261027-wxq 고퀄 상세 배치 모드

광고 주간보고 ⑦c/⑦d 중 상세 미가공 상품을 판매(잠금)→구매→클릭 순으로 뽑아, Aside(Opus 5.5) 제작 → 자동 검수 → 불사자 반영 → 스마트스토어 수정 전송을 순차로 돌리는 밤 배치 + 아침 요약.

## Tasks
1. 판정 보강: `webapp/state.상세상태` 가 renderContent 의 `/mcp-assets/` 흔적을 AI가공완료로 본다(+테스트). 광고 조인 캐시가 그 흔적을 보존.
2. 반영 스크립트(bulsaja-detail-remix run.py): `--dry-run`, 교체 전 `before_apply.html` 백업(workdata full, img 0개면 중단).
3. `detail-page-opus/scripts/` targets.py · batch.py · common.py (429 간격·재시도, Aside 무응답 재시작, 확인 필요 보류, state.json 재개, summary.md).
4. SKILL.md 단건 반영 단계 + 배치 모드 문서화. 첫 회 5건 실측.

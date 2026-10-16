---
name: auto-watch
description: 맥북 자동작업(판매상품 잠금·Aside 물갈이·업무판 연동/날짜넘기기·구글 인증·불사자 연결·카톡 인증)을 매일 07:30 점검해 문제가 있으면 카카오톡 '나에게 보내기'로 알린다. 월요일엔 정상이어도 한 줄 보낸다. "자동작업 점검", "알림 확인", "카톡 알림 시험", "auto-watch", "카톡 재인증" 등을 언급하면 자동 실행.
---

# 아침 자동작업 점검 + 카톡 알림

```bash
.venv/bin/python3 .claude/skills/auto-watch/scripts/watch.py --dry-run --always   # 점검만 출력
.venv/bin/python3 .claude/skills/auto-watch/scripts/watch.py                       # 문제 있을 때만 카톡
cd .claude/lib && ../../.venv/bin/python3 -m eroomlib.kakao test                   # 카톡 시험 발송
cd .claude/lib && ../../.venv/bin/python3 -m eroomlib.kakao auth                   # (재)인증 — 링크 열고 동의
```

- 카톡: `eroomlib/kakao.py`. 설정 `~/.eroom/kakao.json`(REST API 키·클라이언트 시크릿·redirect `http://localhost:8799/kakao`), 토큰 `~/.eroom/kakao-token.json`(600). refresh 2달, 매일 쓰면 갱신. 7일 미만이면 점검이 경고.
- 구글 인증(gws)과 독립 경로라 gws 가 끊긴 걸 카톡으로 알릴 수 있다.
- 실행은 예약관리자 `.claude/lib/eroom_scheduler.py` JOBS 의 `auto-watch`(매일 07:30).
- 한계: 예약관리자 자체가 죽으면 점검도 안 돈다.

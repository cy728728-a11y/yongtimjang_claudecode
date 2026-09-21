---
created: 2026-09-21
severity: high
source: 2026-09-21 운영 중 실측 (조인 스캔 323b1918 · 인덱스 a19789b5)
evidence: webapp/jobs.py `_reap` · `_alive` · `job_status`
---

# 잡 수거가 폴링에 의존한다 — 아무도 안 보면 영원히 `running`

## 무슨 일이 났나

`curl` 로 조인 스캔을 띄우고 브라우저를 안 열어 뒀다.
스캔은 **16:30 에 1분 만에 정상 완주**해 산출물(299KB)을 썼다.
그런데 잡 레지스트리는 **17:10 까지 40분 동안 `running`** 이었다.
자식은 좀비(`ps` STAT `ZN` · `<defunct>`)로 떠 있었다.

`GET /jobs/{id}` 를 한 번 때리자 즉시 `done` / `exit_code 0` 으로 닫혔다.

## 원인 — 두 겹이다

1. **`_reap()` 은 누가 물어봐야 돈다.** 호출부는 `create_job`(새 잡을 만들 때)과
   `job_status`(상태 조회)뿐이다. SSE 가 0.4초마다 부르지만 **보는 사람이 없으면
   아무도 안 부른다.** 헤드리스 호출·스케줄러(v2 APScheduler)에는 관측자가 없다.

2. **`_alive()` 가 좀비를 살아 있다고 한다.** `os.kill(pid, 0)` 은 좀비에도 성공한다
   (수거 전까지 프로세스 테이블에 남는다). `_PROCS` 에 `Popen` 이 없는 경로로 빠지면
   `_alive` 가 True → `orphaned` 로도 못 닫고 `running` 에 영원히 갇힌다.

## 왜 비싼가

- **전역 쓰기 가드가 유령 잡에 걸린다.** "아무것도 안 도는데 409" — `_reap` 주석이
  정확히 막으려던 그 고장이, 관측자가 없을 때 되살아난다.
- **인덱스 잡이 옛 산출물을 쓴다.** `post_bulsaja_index` 는 `latest_done("bulsaja_scan")`
  으로 조인 산출물을 고른다. 방금 끝난 스캔이 `done` 이 아니면 **직전 회차 산출물**을
  집어 훑을 그룹을 계산한다. 조용히 틀린 대상을 훑는다.
- **`ended_at` 이 거짓이다.** 실제 종료 16:30, 기록 17:10. `elapsed_sec 2421`(40분) vs
  실제 약 60초. **끝난 시각이 아니라 눈치챈 시각을 적는다.** 성능 판단의 근거가 못 된다.

## 이 저장소의 기존 병과 같은 계열이다

CR-01/02/03 은 "오류를 0개로 읽는" 병이었다. 이건 **"끝난 것을 도는 중으로 읽는"** 병이다.
둘 다 화면이 조용히 사실이 아닌 것을 말한다.

## 고칠 방향 (설계 확정 아님)

- 관측자 없이도 도는 수거 경로 — 앱 수명주기에 붙는 주기 태스크(uvicorn lifespan)
- `_alive` 가 좀비를 산 것으로 읽지 않게 — `waitpid(pid, WNOHANG)` 또는
  `psutil` 없이 `ps -o stat=` 의 `Z` 판별. **다만 남의 프로세스를 좀비로 오판하면 안 된다**
- `ended_at` 과 "수거 시각"을 **다른 칸으로 가른다.** 둘은 다른 사실이다
  (이 페이즈가 `추출실패`/`미조회` 를 가른 것과 같은 원칙)

## 재현

```bash
curl -X POST -H "X-CT-Token: $T" -d '{"run_dir":"2026-09-20"}' \
     http://127.0.0.1:8765/jobs/bulsaja/scan     # 브라우저 열지 말 것
# 산출물은 1분 뒤 기록되지만 DB 는 running 그대로
sqlite3 webapp.db "select status from jobs order by started_at desc limit 1"
```

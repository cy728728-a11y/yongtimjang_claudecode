#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""작업(잡) 엔진 — CLI 를 자식 프로세스로 띄우고 그 생사를 SQLite 에 적는다.

**이 모듈은 HTTP 를 모른다.** 웹 프레임워크를 import 하지 않고, 요청 객체도 받지 않는다.
`create_job()` 은 그냥 부를 수 있는 함수고, 라우트는 그걸 얇게 감싸기만 한다 (D-17 / ENG-07).
v2 의 APScheduler 가 **같은 함수**를 부를 것이기 때문이다 — 스케줄러가 자기 서버에
HTTP 요청을 쏘는 모양이 되면 그때 다시 짜야 한다.

작업 종류와 위험도:

| kind           | 서브커맨드        | 디스크 쓰기 | 광고 API 쓰기 | 전역 가드 |
|----------------|-------------------|-------------|---------------|-----------|
| `prep`         | `prep`            | run-dir 생성 | 없음(리포트 잡 접수는 한다) | **탄다** |
| `run`          | `run`             | result.json | 없음          | 안 탄다   |
| `bids_preview` | `bids`(dry-run)   | 미리보기 파일만 | 없음        | 안 탄다   |
| `bids_commit`  | `bids --commit`   | 백업·ledger | **PUT**       | **탄다** |
| `revert_only`  | `bids --revert`   | ledger      | **PUT**       | **탄다** |
| `revert_all`   | `bids --revert`   | ledger      | **PUT**       | **탄다** |
| `synthetic`    | (없음)            | 로그만      | 없음          | 안 탄다   |

불사자 작업 3종 (Phase 3). **광고 API 가 아니라 불사자 MCP 를 부르고, 셋 다 읽기 전용이다:**

| kind              | 스크립트            | 디스크 쓰기        | 불사자 쓰기 | 전역 가드 |
|-------------------|---------------------|--------------------|-------------|-----------|
| `bulsaja_profile` | `--profile-only`    | 프로필 파일        | 없음(조회) | 안 탄다   |
| `bulsaja_index`   | `ss_index_build.py` | `ss_index` 테이블  | 없음(조회) | 안 탄다   |
| `bulsaja_scan`    | `bulsaja_scan.py`   | `join_*.json`      | 없음(조회) | 안 탄다   |

셋이 전역 가드를 **안 타는** 이유는 `WRITE_KINDS` 주석에 있다. 대신 `bulsaja_index`·
`bulsaja_scan` 은 `SINGLETON_KINDS` 로 **같은 kind 끼리만** 겹치는 걸 막는다(레이트리밋).

배너 판정 잡 1종 (Phase 4). **불사자 MCP 도 광고 API 도 한 번도 안 부른다:**

| kind          | 스크립트         | 디스크 쓰기                      | 외부 쓰기 | 전역 가드 |
|---------------|------------------|----------------------------------|-----------|-----------|
| `banner_scan` | `banner_scan.py` | `banner_*.json` · 원본캐시 · 썸네일 | 없음     | 안 탄다   |

입력은 직전 성공 `bulsaja_scan` 의 조인 산출물 JSON 하나뿐이고, 거기 이미 들어 있는
이미지 URL 을 CDN 에서 받아 온디바이스 OCR 로 판정한다 — 크레딧 0 · MCP 0회.
전역 가드를 안 타는 이유는 `WRITE_KINDS` 주석에, 같은 잡 중복만 막는 이유는
`SINGLETON_KINDS` 주석에 따로 적어 뒀다(둘이 **다른 이유**다).

`prep` 이 가드를 타는 이유: 같은 회차 디렉터리에 스냅샷을 통째로 다시 쓰는데,
그 사이에 `bids` 가 돌면 읽는 스냅샷이 발밑에서 바뀐다.

**자격증명을 자식에게 넘기지 않는다.** CLI 의 `nvad.py` 가 설정 파일을 직접 읽으므로
넘길 이유가 없다. env 로 넘기는 설계는 `ps -E` 한 줄에 다 뜬다 (T-1-03c).
"""
import json
import os
import sqlite3
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from webapp import argv as argv_mod
from webapp import bulsaja_index, paths, settings

# 모듈 이름을 짧게 한 번 더 노출한다 — 테스트·라우트가 `jobs.argv.PY_CLI` 로 집는다.
argv = argv_mod

# **`JobKind` 와 `KINDS` 는 항상 같이 고친다.** 하나만 고치면 타입 검사는 통과하는데
# `create_job` 첫 줄의 `kind not in KINDS` 가 런타임에 거부한다 — "코드상 맞는데 화면에서만
# 안 되는" 부류의 고장이다.
JobKind = Literal["prep", "run", "bids_preview", "bids_commit",
                  "revert_only", "revert_all", "synthetic",
                  "bulsaja_profile", "bulsaja_index", "bulsaja_scan",
                  "banner_scan",
                  "detail_estimate", "detail_submit", "detail_poll",
                  "market_preview", "market_commit", "market_poll"]

KINDS: tuple[str, ...] = ("prep", "run", "bids_preview", "bids_commit",
                          "revert_only", "revert_all", "synthetic",
                          "bulsaja_profile", "bulsaja_index", "bulsaja_scan",
                          "banner_scan",
                          "detail_estimate", "detail_submit", "detail_poll",
                          "market_preview", "market_commit", "market_poll")

# 전역 1개 가드의 대상. **왜 전역인가:**
# ENG-04(대상별 잠금)는 Phase 2 지만 **위험은 Phase 1 에 있다.** `run_bids` 가
# `before_bids_<alias>.json` 과 `ledger/<alias>.json` 을 읽고-병합하고-통째로 다시
# 쓰는데 락이 없다(bids.py:182-193). 쓰기 잡 두 개가 겹치면 백업 항목이 사라지고
# **그 소재는 영영 되돌릴 수 없다.** 되돌릴 수 없는 손실이라 넓게, 그리고 지금 막는다.
# Phase 2 가 이걸 대상별 락으로 좁힌다. 미리보기·판정은 아무것도 안 쓰므로 뺀다 —
# 쓰기가 아닌 것까지 막는 가드는 사람이 가드를 끄게 만든다.
WRITE_KINDS: frozenset[str] = frozenset({"prep", "bids_commit", "revert_only", "revert_all",
                                         "detail_submit", "detail_poll",
                                         "market_commit", "market_poll"})
# **마켓 반영(`market_commit`)은 스토어 상세를 바꾸는 진짜 쓰기다**(D-07). **이어서 확인
# (`market_poll`)도 넣는다** — 접수는 안 하지만 같은 `market_status.json` 을 읽고-고치고-통째로
# 쓴다. 둘이 겹치면 taskId 기록이 사라져 이미 접수된 반영을 못 찾고 다시 반영(이중 반영)한다.
# **미리보기(`market_preview`)는 넣지 않는다** — confirm:false 만 부르고 쓰기 0 이다(06-02 두 겹 증명).
# **상세 접수(`detail_submit`)는 크레딧을 태우는 진짜 쓰기다** — 불사자에 AI 상세페이지를 접수하고
# 결과를 상품에 반영한다. **이어서 확인(`detail_poll`)도 넣는다**: 접수는 안 하지만 폴링 완료분을
# 반영하고 같은 `detail_status.json` 을 읽고-고치고-통째로 쓴다(연구 Open Q3). 둘이 겹치면 taskId
# 기록이 사라져 **이미 돈 낸 결과를 못 찾거나, 못 찾아서 다시 접수(이중 지불)** 한다.
# **견적(`detail_estimate`)은 넣지 않는다** — generate 0회 · 크레딧 0 이고 자기 estimate.json 만 쓴다.
# **불사자 잡 3종을 여기 넣지 마라.** 셋 다 불사자에 아무것도 안 쓴다(workdata·프로필 조회는
# 읽기 전용이다). 넣으면 3시간 32분짜리 인덱스가 도는 동안 입찰가 인상·되돌리기가 전부
# 409 가 된다 — 위 "쓰기가 아닌 것까지 막는 가드는 사람이 가드를 끄게 만든다" 가 바로 이 경우다.
# **`banner_scan` 도 여기 넣지 마라 — 4분 동안 입찰가 인상이 409 가 되면 사람이 가드를 끈다.**
# 그 잡이 만지는 것은 CDN 에서 받은 이미지 캐시·썸네일·자기 산출물 JSON 뿐이고, 광고에도
# 불사자에도 한 글자를 안 쓴다. `BULSAJA_KINDS` 에도 넣지 않는다 — MCP 를 0회 부르므로
# ENG-08 계정 사전점검의 대상 자체가 아니다(계정이 뭐든 판정 결과가 같다).

# ENG-08 사전 점검 대상. **불사자 MCP 를 부르는 잡**이다.
# `bulsaja_profile` 은 **일부러 뺐다** — 그 잡이 프로필을 만드는 잡이라, 가드 대상에 넣으면
# 프로필이 없을 때 프로필을 만들 수 없다(닭·달걀). 계정 확인은 그 자체로 읽기 조회 1회다.
BULSAJA_KINDS: frozenset[str] = frozenset({"bulsaja_index", "bulsaja_scan",
                                           "detail_estimate", "detail_submit", "detail_poll",
                                           "market_preview", "market_commit", "market_poll"})
# 마켓 잡 3종도 셋 다 불사자 MCP 를 부른다(미리보기도 workdata·confirm:false 를 부른다).
# 틀린 계정으로 미리보기를 내면 "반영가능" 판정이 남의 계정 기준이 된다(T-06-18).
# 상세 잡 3종은 **셋 다** 불사자 MCP 를 부른다(견적도 기작업 태그·잔액을 실시간 조회한다).
# 틀린 계정으로 견적을 내면 "기작업 스킵" 수가 남의 계정 기준이 된다 — 그래서 견적도 탄다.
# CLI 도 `--expect-nick` 으로 한 번 더 본다(exit 4). 이중 방어다(T-05-12).

# **같은 kind 가 동시에 두 개 돌면 안 되는 작업.** 전역 쓰기 락과 **다른 이유로** 존재한다.
#
# 왜 전역이 아니라 kind 단위인가: 인덱스 잡은 불사자에 아무것도 안 쓴다. 전역 락에 넣으면
# 3시간 32분 동안 입찰가 인상·되돌리기가 전부 409 가 되고, 그러면 사람이 가드를 끈다
# (위 WRITE_KINDS 주석과 같은 판단).
#
# 그런데 **같은 잡 두 개가 동시에 도는 건 막아야 한다.** 각자 최소간격 0.26초(초당 4회)를
# 지켜도 합산 8회/초라 서버 정책(RateLimit-Policy: 240;w=60)을 넘긴다. 실측상 세션을 늘려도
# 총량이 같았고 — 프로세스를 늘려도 마찬가지다 — 429 가 쏟아진다. 그 429 는 `unresolved=1`
# 로 남고, 화면에서 "미해소" 로 보인다. **우리가 제일 막고 싶은 오진이 그거다** (Pitfall 3).
#
# 화면의 `hx-disabled-elt` 는 이 방어의 대체물이 **아니다.** POST 왕복 중에만 버튼을 잠그므로
# 새로고침한 뒤 다시 누르면 두 번째 프로세스가 그대로 뜬다.
#
# ⚠️ `BULSAJA_KINDS` 와 멤버가 **더 이상 같지 않다.** 앞은 "불사자 MCP 를 부른다",
#    이쪽은 "둘이 동시에 돌면 안 되는 이유가 있다" 다. 합치지 마라 — 아래 `banner_scan`
#    이 그 차이의 실물이다(MCP 를 0회 부르는데 이 집합에는 들어 있다).
#
# 🔵 **`banner_scan` 은 레이트리밋 때문이 아니다.** 불사자 MCP 를 0회 부르므로 갉아먹을
#    예산 자체가 없다. 같은 잡 둘이 **271MB 를 두 번 받는 낭비**를 막으려는 것이다 —
#    거기에 둘이 같은 회차 캐시 디렉터리에 같은 파일명(`<상품순번>_<장순번>.bin`)으로
#    동시에 쓰면 반쪽 파일이 서로의 입력이 된다. 사유가 다르니 같은 집합에 있다는 이유로
#    위 레이트리밋 서술을 이 잡에 옮겨 읽지 마라.
SINGLETON_KINDS: frozenset[str] = frozenset({"bulsaja_index", "bulsaja_scan", "banner_scan",
                                             "detail_estimate", "market_preview"})
# 🔵 **`market_preview` 도 레이트리밋 때문이다** — `detail_estimate` 와 같은 사유. 쓰기 가드 밖이다.
# 🔵 **`detail_estimate` 는 레이트리밋 때문이다** — 위 불사자 잡들과 같은 사유(MCP 조회 합산이
#    서버 정책을 넘는다). 쓰기 가드 밖이라 전역 락이 막아 주지 않으므로 여기서 같은 종류만 막는다.
#    접수·이어서 확인은 이미 `WRITE_KINDS` 가 전역으로 하나만 허용하므로 여기 넣을 필요가 없다.

# **살아 있는 잡의 상태 두 가지.** `starting` 은 "행은 들어갔는데 자식이 아직 안 떴다" 다.
# 왜 둘로 쪼갰나: 예전에는 INSERT 가 바로 `running` 이었는데, 그 행의 `pid` 는 spawn 뒤에야
# 채워진다. 그 수~수십 ms 창에서 `_reap`(SSE 가 0.4초마다 부른다)이 `pid=NULL` 을 보고
# **멀쩡히 뜰 잡을 `orphaned` 로 찍었다.** 그러면 ① 전역 쓰기 가드(`status='running'` 조회)가
# 그 잡을 못 봐서 두 번째 쓰기 잡이 들어가고(백업 병합이 깨져 그 소재는 영영 못 되돌린다),
# ② `post_revert_job` 이 일부러 허용하는 `orphaned` 에 **살아서 PUT 을 날리는 중인 잡**이
# 섞인다. 재현된 경합이다.
#
# 그래서 spawn 전 구간을 `starting` 으로 두고 **가드는 둘 다 본다**(LIVE_STATUSES).
# `_reap` 은 `running` 만 건드리므로 그 창이 통째로 사라진다.
LIVE_STATUSES: tuple[str, ...] = ("running", "starting")

# `starting` 인 채로 이 시간을 넘기면 "띄우다 죽은 것" 으로 보고 닫는다.
# 이게 없으면 INSERT 와 spawn 사이에 프로세스가 통째로 죽었을 때 그 행이 **영원히**
# 전역 가드를 잡는다 — `_reap` 이 원래 막으려던 바로 그 고장이 이름만 바뀌어 돌아온다.
# spawn 은 실측 수~수십 ms 라 60초면 오탐이 날 여지가 없다.
STARTING_TIMEOUT_SEC = 60

DDL = """
CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,
  run_dir       TEXT,
  accounts      TEXT,
  argv          TEXT NOT NULL,
  pid           INTEGER,
  status        TEXT NOT NULL,
  exit_code     INTEGER,
  log_path      TEXT NOT NULL,
  targets_path  TEXT,
  result_path   TEXT,
  parent_job_id TEXT,
  target_count  INTEGER,
  started_at    TEXT NOT NULL,
  ended_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs(parent_job_id);

CREATE TABLE IF NOT EXISTS ss_index (
  product_id      TEXT PRIMARY KEY,
  smartstore      TEXT,
  market_group_id TEXT NOT NULL,
  group_total     INTEGER,
  unresolved      INTEGER NOT NULL DEFAULT 0,
  observed_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ss_index_smartstore ON ss_index(smartstore);
CREATE INDEX IF NOT EXISTS idx_ss_index_group ON ss_index(market_group_id);

CREATE TABLE IF NOT EXISTS banner_label (
  run_dir        TEXT NOT NULL,
  타오바오상품번호 TEXT NOT NULL,
  판매자상품코드  TEXT NOT NULL,
  이미지순번      INTEGER NOT NULL,
  사람판정        TEXT NOT NULL,
  기록시각        TEXT NOT NULL,
  PRIMARY KEY (run_dir, 타오바오상품번호, 이미지순번)
);

CREATE TABLE IF NOT EXISTS banner_confirm (
  run_dir        TEXT NOT NULL,
  타오바오상품번호 TEXT NOT NULL,
  확인시각        TEXT NOT NULL,
  PRIMARY KEY (run_dir, 타오바오상품번호)
);

CREATE TABLE IF NOT EXISTS market_gate (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  판정            TEXT NOT NULL CHECK(판정 IN ('정상','이상')),
  기록시각        TEXT NOT NULL,
  판매자상품코드  TEXT NOT NULL,
  productId      TEXT NOT NULL,
  commit_job_id  TEXT NOT NULL,
  스토어교체여부  TEXT,
  메모            TEXT
);
"""
# ── market_gate (Phase 6 / 06-04 · D-09) ────────────────────────────────────
# ※ 완료 대장이 아니라 **사람 판정 기록**이다 — L-05 비충돌. 반영 완료의 정본은 여전히
#    불사자 서버 · market_status.json 이다. 여기는 "첫 1건을 스토어에서 눈으로 보고 정상/이상"
#    한 줄씩만 쌓는다(덮어쓰지 않는다 — 누가 언제 열었나가 남아야 한다).
# ※ D-09 1회성 게이트: 최신 줄이 '정상' 이면 반영 상한이 market_update_max_items 로 풀리고,
#    '이상' 이면 반영 라우트가 거부한다. 줄이 없으면 상한 1. 읽기는 market_gate_store 가 한다.
# ※ RESEARCH §5.7 의 DDL 에서 `run_dir` 만 NOT NULL 을 뺐다. `prep` 은 회차 이름을
#    **CLI 가 오늘 날짜로 정한다** — 웹앱이 미리 지어내면 진실이 둘이 된다.
# ※ 보드용 캐시 테이블은 만들지 않는다. 보드는 매번 `result.json` 을 투영한다(수십 ms).
#    캐시는 최적화이고, 지금 넣으면 "진실이 둘" 위험만 는다.
# ※ 대상별 잠금 테이블은 Phase 2(ENG-04) 다. 안 쓰는 스키마를 미리 굳히지 않는다.
#
# ── ss_index (Phase 3 / D-20) ───────────────────────────────────────────────
# ※ observed_at 이 있어야 D-04 를 안 어긴다. "채널상품ID 를 영구 키로 저장하는 것" 과
#    "관측 기록을 관측시각과 함께 보관하는 것" 은 다르다. 20일 물갈이로 번호가 재발급되므로
#    적힌 값을 그대로 믿으면 조용히 틀린 상품을 가리킨다 — 쓰기 직전 재검증이 그 선을 지킨다
#    (JOIN-04). 관측시각이 없으면 "언제 본 값인가" 를 물을 수 없어 재검증이 성립하지 않는다.
# ※ 이건 보드 캐시가 아니다. 보드 캐시는 `result.json` 에서 언제든 재생성되는 투영이라
#    두는 순간 진실이 둘이 되지만, 이건 **3시간 반을 태워야 다시 얻는 외부 관측 기록**이다
#    (36그룹 / 47,105 상품). 재생성이 공짜가 아니면 그건 캐시가 아니라 기록이다.
#    위 "보드용 캐시 테이블은 만들지 않는다" 는 여전히 유효하고, 대상별 잠금도 여전히 Phase 2 다.
# ※ `smartstore` 에 NOT NULL 을 걸지 않는다. 업로드 안 된 상품이 **정상적으로** NULL 이다
#    (전체 수집상품 97만 건 중 대부분). 걸면 인덱스 잡이 그 그룹 중간에서 통째로 죽는다.
# ※ `unresolved` 는 429·타임아웃으로 **못 본 것**이다. 0 으로 접지 마라 — 미조회를 성공으로
#    적으면 그 행이 화면에서 "미해소(광고 쪽 오류)" 로 둔갑한다(Pitfall 3).
# ※ `group_total` 은 관측 시점의 그룹 전체 상품수다. 행수와 비교해야 "중간에 끊긴 잡" 을
#    "다 훑었다" 와 구분할 수 있다 (`bulsaja_index.group_health`).
#
# ── banner_label · banner_confirm (Phase 4 / BANNER-02b) ────────────────────
# ※ **사람 라벨은 재생성 불가다 — 사람의 시간이다.** 그래서 캐시가 아니라 기록이고,
#    위 "보드용 캐시 테이블은 만들지 않는다" 와 충돌하지 않는다. `ss_index` 를 예외로
#    인정한 것과 **똑같은 판별 기준**이다: 재생성이 공짜가 아니면 그건 캐시가 아니라 기록이다.
#    기계 판정은 정반대다 — `banner_scan.py` 를 다시 돌리면 몇 분에 다시 나오는 투영이라
#    산출물 JSON 하나가 정본이다.
# ※ **기계 판정(배너/제품/무내용)을 이 테이블에 복사하지 마라.** 복사하는 순간 진실이
#    둘이 되고, 어휘군을 고쳐 다시 돌린 회차에서 화면과 산출물이 다른 말을 한다(S-1).
#    여기 적히는 `사람판정` 은 사람이 화면에서 뒤집은 것 **하나뿐**이다.
# ※ 키가 URL 이 아니라 `(run_dir, 타오바오상품번호, 이미지순번)` 인 이유: 불사자는 수집할
#    때마다 같은 이미지를 **새 CDN 경로에 복사**한다(D-01a 실측). URL 을 키로 잡으면 같은
#    장에 붙인 라벨이 다음 수집에서 통째로 미아가 된다. 타오바오상품번호는 물갈이 사본을
#    가로질러 같은 원본을 가리키는 유일한 번호라 그 문제가 없다(04-03 이 조인 산출물에 실었다).
# ※ `banner_confirm` 을 `banner_label` 에 합치지 마라. **"이 장을 뒤집었다" 와 "이 줄을
#    다 봤다" 는 다른 사실이다.** 합치면 확인 표시가 라벨로 둔갑해 게이트 집계의 분모가
#    조용히 틀어진다 (`join.py:36-48` 의 "사유코드는 서로 다른 값" 과 같은 규율).
# ※ **스키마 정본은 여기 하나다.** `banner_scan.py` 는 SQLite 를 아예 안 만진다 —
#    `ss_index_build.py:165-176`(스키마를 만들지 않고 확인만 하고 exit 4)과 같은 선이다.


class BusyError(RuntimeError):
    """이미 도는 쓰기 작업이 있다. 라우트가 409 로 번역한다."""


class SameKindBusyError(BusyError):
    """같은 종류의 작업이 이미 돌고 있다 (`SINGLETON_KINDS`).

    **`BusyError` 를 상속한다** — 그래야 `routes/jobs.py` 의 기존 `except jobs.BusyError`
    가 그대로 409 로 번역하고 라우트를 안 고쳐도 된다.

    다만 **타입과 메시지는 전역 쓰기 락과 구분**한다. 둘이 섞이면 사용자가 "입찰가 작업이
    도나?" 를 찾으러 가는데, 실제로 막은 건 "같은 인덱스 잡이 이미 돈다" 다.
    """


class AccountMismatchError(ValueError):
    """붙어 있는 불사자 계정이 기대와 다르다 (ENG-08).

    **라우트가 409 로 번역해야 한다.** `ValueError` 를 그냥 쓰면 `_작업만들기` 의
    `except ValueError`(400)에 걸려 "모르는 회차" 와 구분이 안 된다 — 둘 다 400 이면
    화면이 "회차를 다시 골라라" 로 안내하는데 진짜 원인은 계정이다.
    라우트에 별도 `except` 를 다는 건 03-05 의 작업이다.

    그때까지 `ValueError` **상속은 유지한다**: 03-05 이전 상태에서도 400 으로 거부되어
    **열린 채로 새지 않는다.** 안전한 기본값이다 — 상태코드가 덜 정확한 것보다
    가드가 없는 게 훨씬 나쁘다.
    """


# 인메모리 `Popen` 맵. **`--workers 1` 전제다** (Pitfall 9 / T-1-22).
# 자식은 `start_new_session=True` 라 세션이 갈라져 있어서, 종료코드를 읽는 길은
# 이 객체의 `poll()` 뿐이다. 워커가 둘 이상이면 잡을 띄운 워커와 상태를 묻는 워커가
# 달라져 이 맵이 비어 보이고, 멀쩡히 끝난 잡이 `orphaned` 로 찍힌다.
# `run-webapp.sh` 가 `--workers 1` 을 고정하고 `main.py` 가 기동 때 경고한다.
_PROCS: dict[str, subprocess.Popen] = {}


# ── 경로 ────────────────────────────────────────────────────────────────────

def db_path() -> Path:
    """잡 레지스트리 파일. 상대경로면 저장소 루트 기준."""
    p = Path(settings.DB_PATH).expanduser()
    return p if p.is_absolute() else paths.repo_root() / p


def log_dir() -> Path:
    d = Path(settings.JOB_LOG_DIR).expanduser()
    d = d if d.is_absolute() else paths.repo_root() / d
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path_of(job_id: str) -> Path:
    """진행 로그 파일. append-only 로 쌓이고 Plan 01-06 의 SSE 가 여기를 tail 한다."""
    return log_dir() / f"{job_id}.log"


def banner_dir(키: str) -> Path:
    """배너 스캔의 원본 캐시·썸네일 **루트**. 상대경로면 저장소 루트 기준.

    `db_path()`·`bulsaja_index.profile_path()` 와 같은 규칙이다 — 설정에 적힌 상대경로를
    저장소 루트에 붙인다. 숫자·경로를 이 파일에 리터럴로 베끼지 않는다(S-4): 정본은
    `settings.DEFAULTS` 고 여기서는 키 이름만 안다.

    **회차 하위 디렉터리(`<루트>/<run_dir>/`)는 만들지 않는다.** 자식이 만든다 —
    `banner_scan.회차정리()` 가 오래된 회차를 지워 271MB×N 을 회수하는데, 웹앱이 미리
    만들어 두면 방금 지운 회차 폴더가 빈 채로 되살아나 "남길 회차 수" 계산이 흐려진다.
    """
    p = Path(str(settings.cfg(키, settings.DEFAULTS[키]))).expanduser()
    return p if p.is_absolute() else paths.repo_root() / p


def _web_dir(run_dir: str) -> Path:
    """회차 안의 웹앱 산출물 폴더. 회차 이름은 **화이트리스트를 통과한 것만** 온다."""
    d = paths.run_dir_path(run_dir) / "web"
    d.mkdir(parents=True, exist_ok=True)
    return d


def targets_path_of(job_id: str) -> Path | None:
    """이 작업이 지목한 대상 목록 파일 (FLOW-02 의 '그 파일'). 없으면 None."""
    row = _row(job_id)
    return Path(row["targets_path"]) if row and row["targets_path"] else None


def result_path_of(job_id: str) -> Path | None:
    """이 작업의 산출물 파일(미리보기/실행 결과). 없으면 None."""
    row = _row(job_id)
    return Path(row["result_path"]) if row and row["result_path"] else None


# ── DB ──────────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    """커넥션은 작업마다 새로 연다. `timeout=5` 로 잠깐의 경합은 기다린다."""
    cx = sqlite3.connect(db_path(), timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def init_db() -> None:
    """테이블·인덱스를 만들고 WAL 을 켠다. 여러 번 불러도 안전하다.

    WAL 인 이유: 상태 폴링(읽기)과 잡 생성·종료 기록(쓰기)이 겹친다.
    기본 저널 모드면 읽는 동안 쓰기가 막혀 버튼이 잠깐씩 먹통이 된다.
    """
    db_path().parent.mkdir(parents=True, exist_ok=True)
    cx = _conn()
    try:
        cx.execute("PRAGMA journal_mode = WAL")
        cx.executescript(DDL)
        cx.commit()
    finally:
        cx.close()


def _row(job_id: str) -> sqlite3.Row | None:
    cx = _conn()
    try:
        return cx.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        cx.close()


def _now() -> str:
    """로컬 시각 + 오프셋. 오프셋을 빼면 경과시간 계산이 서머타임·시차에서 틀어진다."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _alive(pid: int | None) -> bool:
    """시그널 0 = 존재 확인만. 프로세스에 아무 영향이 없다."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# 종료코드 3 이 **실패가 아닌** 잡 종류. 상세 CLI 에서 3 = 폴링 미완(시간 상한 도달)이다 (L-03 · D-17).
# failed 로 적으면 화면이 "실패" 라고 말하고, 사람은 실패로 읽고 **다시 접수한다 — 크레딧 이중 지불.**
# 새 상태값(예: 'incomplete')을 만들지 않고 done + exit_code 3 으로 둔다: latest_done·가드 쿼리가
# 전부 'done' 을 보므로 손댈 곳이 없다. 구분은 exit_code 로 화면이 한다(_job_status.html).
# ⚠️ 다른 kind 에 넣지 마라 — bulsaja_scan 의 3 은 계정 불일치다(detail_batch.py 주석 참조).
POLL_INCOMPLETE_OK_KINDS: frozenset[str] = frozenset({"detail_submit", "detail_poll",
                                                      "market_commit", "market_poll"})
# 마켓 반영·이어서 확인도 3 = 대기 미완(upload_tasks 창에서 아직 종결 안 봄)이다(D-08). failed 로
# 적으면 사람이 다시 반영을 누른다. `market_poll` 은 D-08 이어서 확인 전용 세 번째 kind 다
# (RESEARCH Open Q5). 미리보기는 폴링이 없어 3 이 나오면 그건 이상이다 — 넣지 않는다.


def _finish(cx: sqlite3.Connection, job_id: str, code: int, kind: str | None = None) -> None:
    성공 = code == 0 or (code == 3 and kind in POLL_INCOMPLETE_OK_KINDS)
    cx.execute("UPDATE jobs SET status = ?, exit_code = ?, ended_at = ? WHERE id = ?",
               ("done" if 성공 else "failed", code, _now(), job_id))
    _PROCS.pop(job_id, None)


def _reap(cx: sqlite3.Connection) -> None:
    """`running` 으로 남아 있는 행들의 실제 생사를 확인해 상태를 맞춘다.

    가드가 이걸 먼저 돌려야 한다 — 안 그러면 이미 끝난 쓰기 잡의 행이 계속
    `running` 으로 남아 다음 작업을 영원히 막는다("아무것도 안 도는데 409").

    프로세스 메모리에 `Popen` 이 없는데 pid 도 죽었으면 종료코드를 알 길이 없다.
    그때는 **지어내지 않고** `orphaned` 로 둔다 — 복구는 Phase 2(ENG-05)다.

    **`starting` 은 생사를 묻지 않는다.** 그 상태의 행은 아직 pid 가 없는 게 정상이라,
    `_alive(None)` 을 물으면 무조건 거짓이고 멀쩡히 뜰 잡이 `orphaned` 가 된다
    (재현된 경합 — LIVE_STATUSES 주석 참조). 대신 **시간으로만** 판정한다:
    `STARTING_TIMEOUT_SEC` 을 넘겼으면 띄우다 죽은 것이니 `failed` 로 닫아 전역 가드를
    풀어 준다. 시간 이전의 `starting` 은 건드리지 않는다.
    """
    for r in cx.execute("SELECT id, pid, kind FROM jobs WHERE status = 'running'").fetchall():
        proc = _PROCS.get(r["id"])
        if proc is not None:
            code = proc.poll()
            if code is not None:
                _finish(cx, r["id"], code, r["kind"])      # kind 가 exit 3 의 뜻을 가른다
            continue
        if not _alive(r["pid"]):
            cx.execute("UPDATE jobs SET status = 'orphaned', ended_at = ? WHERE id = ?",
                       (_now(), r["id"]))

    한계 = datetime.now().astimezone() - timedelta(seconds=STARTING_TIMEOUT_SEC)
    for r in cx.execute("SELECT id, started_at FROM jobs WHERE status = 'starting'").fetchall():
        try:
            시작 = datetime.fromisoformat(r["started_at"])
        except (TypeError, ValueError):
            시작 = None            # 시각을 못 읽으면 살려 두지 않는다 — 가드를 영원히 잡는 쪽이 더 나쁘다
        if 시작 is None or 시작 < 한계:
            cx.execute("UPDATE jobs SET status = 'failed', exit_code = -1, ended_at = ? "
                       "WHERE id = ? AND status = 'starting'", (_now(), r["id"]))


# ── 자식 띄우기 ─────────────────────────────────────────────────────────────

def spawn(argv_list: list[str], log_path) -> subprocess.Popen:
    """CLI 자식을 띄우고 `Popen` 을 돌려준다. **호출부를 블로킹하지 않는다.**

    인자 하나하나가 실측으로 정해졌다 (RESEARCH §5.1~5.3):

    · `env` 의 `PYTHONUNBUFFERED=1` — 없으면 0.5초 시점 로그파일이 **0바이트**고
      종료 시 한꺼번에 떨어진다(실측). CLI 전체에 `flush=True` 가 `prune.py:115`
      한 줄뿐이라 CLI 를 고쳐서는 못 푼다. 10분짜리 `prep` 의 진행 로그가 10분 내내
      빈 화면이 된다 — "SSE 가 고장났다" 로 오진하기 딱 좋은 종류다.
    · `env` 는 **병합**이다(`{**os.environ, ...}`). 통째로 갈아치우면 PATH·HOME 이
      사라져 CLI 가 죽는다. 그리고 **자격증명을 여기 심지 않는다** — `ps -E` 에 뜨고,
      CLI 가 설정 파일을 직접 읽으므로 넘길 이유도 없다 (T-1-03c).
    · `start_new_session=True` — 자식을 새 세션·새 프로세스 그룹으로 보낸다.
      `uvicorn --reload` 재시작과 서버 종료에서 자식이 살아남는다(실측 2회:
      부모 그룹에 SIGTERM 을 쏴도 그룹이 분리된 자식만 생존). ENG-02 의 절반이
      이 한 인자다. 부수효과로 서버가 죽어도 자식이 계속 도는데, 그래서
      jobs 행에 `pid` 와 `started_at` 을 남긴다 — Phase 2 의 고아 정리(ENG-05)가
      끼워 넣을 자리다.
    · `stdin=DEVNULL` — 자식이 입력을 기다리며 영원히 멈추는 사고를 막는다.
    · `cwd=repo_root()` — `run_ads.py` 의 `lib/eroomlib` 탐색이 여기 의존한다.
    · `stdout`/`stderr` 를 같은 파일로 합친다 — 파이프로 직접 흘리지 **않는다.**
      파이프는 읽는 쪽이 붙어 있어야만 살아서 "브라우저를 닫았다 다시 열기" 가
      성립하지 않는다(ENG-03). 파일이면 오프셋부터 다시 읽으면 그만이다.
    """
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fh = open(log_path, "ab", buffering=0)     # append-only · 버퍼 없음
    except OSError as e:
        raise RuntimeError(f"로그 파일을 못 연다: {e}")

    try:
        return subprocess.Popen(
            argv_list,
            cwd=str(paths.repo_root()),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        # Popen 이 터지면 핸들이 새는 것도 막는다. 로그 파일은 남겨 둔다 —
        # 실패 사유를 쓸 자리이기도 하다.
        fh.close()
        raise
    finally:
        # 부모는 이 핸들이 더 필요 없다. 자식이 복제본을 쥐고 있다.
        # 안 닫으면 서버가 도는 동안 잡 개수만큼 fd 가 쌓인다.
        try:
            if not fh.closed:
                fh.close()
        except Exception:
            pass


# ── 작업 생성 ───────────────────────────────────────────────────────────────

def _write_targets(job_id: str, run_dir: str, ad_ids: list[str]) -> Path:
    """대상 adId 목록을 **원자적으로** 떨군다 (FLOW-02 의 '그 파일').

    tmp → `os.replace` 로 쓰는 이유: 자식이 읽는 도중에 반쪽 파일이 보이면
    `--only-ads` 가 깨진 파일로 판단해 exit 1 한다(그게 맞는 동작이다).
    `run_coupang.py:68-74` 의 원자적 쓰기 관례를 그대로 쓴다.
    """
    path = _web_dir(run_dir) / f"targets_{job_id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ad_ids, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _override_targets(run_dir: str | None, path: str | Path) -> Path:
    """이미 있는 대상 파일을 **그대로** 가리킨다 — 새로 쓰지 않는다 (D-11 / FLOW-02).

    실행(`bids_commit`)·되돌리기(`revert_only`)가 미리보기가 만든 그 파일을 재사용하는
    통로다. 새로 쓰면 그 순간 '같은 파일' 이 아니게 되고, 미리보기와 실행 사이에
    화면 필터가 바뀐 만큼 **본 것과 다른 게 실행된다.**

    받은 경로를 그대로 믿지 않는다. 회차의 `web/` 밑인지 · 실제로 있는지 두 가지를
    보고, 아니면 `ValueError` 다. **빈 목록으로 폴백하지 않는다** — 폴백하면
    "아무것도 안 했는데 성공" 이 되어 사용자는 올라간 줄 안다.
    """
    if not run_dir:
        raise ValueError("대상 파일을 재사용하려면 회차가 필요하다")
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError("대상 파일 경로가 절대경로가 아니다")
    p = p.resolve()
    # 부모 디렉터리 비교다. 접두 비교(`startswith`)로 하면 `web-남의것/` 같은
    # 형제 디렉터리가 통과한다 — 경계를 글자가 아니라 경로로 본다.
    if p.parent != _web_dir(run_dir).resolve():
        raise ValueError("회차 밖 대상 파일은 쓸 수 없다")
    if not p.is_file():
        raise ValueError("대상 파일이 사라졌다 — 미리보기부터 다시 해라")
    return p


def _count_targets(path: Path) -> int | None:
    """대상 파일을 **읽어서** 센다. 화면이 준 수를 믿지 않는다.

    모양 두 가지를 받는다(`run_ads._load_only_ads` 와 같은 계약):
    배열 `["nad-…"]` 과 `{"adIds": [...]}`. 못 읽으면 지어내지 않고 `None` 이다 —
    0 으로 적으면 "대상이 없다" 와 "못 셌다" 가 같은 화면이 된다.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    # 상세 잡 inputs(`{"items": [...]}`)도 같은 규칙으로 센다 — 관문을 통과한 상품 수다.
    ids = raw if isinstance(raw, list) else (raw.get("adIds") if "adIds" in raw else raw.get("items"))
    return len(ids) if isinstance(ids, list) else None


def _write_detail_inputs(job_id: str, run_dir: str, doc: dict) -> Path:
    """상세 견적의 대상(inputs) 파일을 **원자적으로** 떨군다 (FLOW-02 의 '그 파일').

    자리는 `<회차>/web/targets_<견적잡id>.json` — `_write_targets` 와 같은 폴더·이름 규칙이다.
    그래야 접수(`detail_submit`)가 `_override_targets` 로 **같은 파일**을 그대로 가리킬 수 있다
    (부모 == web/ 검사). 견적과 접수 사이에 대상이 바뀌면 본 견적과 다른 게 접수된다.
    """
    path = _web_dir(run_dir) / f"targets_{job_id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


# 상세 잡 kind → 부모로 와야 할 kind. 체인은 submit→estimate, poll→submit 이다.
_상세부모 = {"detail_submit": "detail_estimate", "detail_poll": "detail_submit"}


def _상세폴더(kind: str, job_id: str, parent_job_id: str | None, run_dir: str,
            cx: sqlite3.Connection | None = None) -> Path:
    """상세 CLI 의 `--run-dir` — `<회차>/web/detail_<견적잡id>/`.

    **한 견적에서 나온 접수·이어서 확인은 전부 같은 폴더다.** `detail_status.json`(taskId 기록)이
    거기 살기 때문이다 — 폴더가 갈리면 이어서 확인이 접수가 받은 taskId 를 못 보고, 못 보면
    사람이 다시 접수해 크레딧을 두 번 낸다. 그래서 폴더를 **지어내지 않고** 부모 체인에서만 푼다.
    부모가 없거나 체인이 틀리면 ValueError(→ 400).
    """
    if kind == "detail_estimate":
        견적id = job_id
    else:
        기대 = _상세부모.get(kind)
        if 기대 is None:
            raise ValueError(f"상세 잡이 아니다: {kind}")
        if not parent_job_id:
            raise ValueError(f"{kind} 에는 부모 잡이 필요하다 — 같은 detail 폴더를 이어받아야 한다")

        def _행(i: str):
            if cx is not None:
                return cx.execute("SELECT kind, parent_job_id, run_dir FROM jobs WHERE id = ?",
                                  (i,)).fetchone()
            return _row(i)

        부모 = _행(parent_job_id)
        if 부모 is None or 부모["kind"] != 기대:
            raise ValueError(f"{kind} 의 부모는 {기대} 여야 한다")
        if 부모["run_dir"] != run_dir:
            raise ValueError("부모 잡과 회차가 다르다")
        if kind == "detail_poll":
            조부모 = 부모["parent_job_id"]
            견적행 = _행(조부모) if 조부모 else None
            if 견적행 is None or 견적행["kind"] != "detail_estimate":
                raise ValueError("이어서 확인의 부모 접수가 견적에서 나오지 않았다")
            견적id = 조부모
        else:
            견적id = parent_job_id
    d = _web_dir(run_dir) / f"detail_{견적id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# 마켓 잡 kind → 부모로 와야 할 kind **집합**. 미리보기의 부모는 상세 접수 또는 그 이어서 확인
# (둘 다 같은 detail 폴더를 가리킨다), 반영의 부모는 미리보기, 이어서 확인의 부모는 반영 또는
# 앞선 이어서 확인이다(여러 번 이어 받을 수 있다).
_마켓부모: dict[str, frozenset[str]] = {
    "market_preview": frozenset({"detail_submit", "detail_poll"}),
    "market_commit": frozenset({"market_preview"}),
    "market_poll": frozenset({"market_commit", "market_poll"}),
}
MARKET_KINDS: tuple[str, ...] = ("market_preview", "market_commit", "market_poll")


def _마켓폴더(kind: str, job_id: str, parent_job_id: str | None, run_dir: str,
            cx: sqlite3.Connection | None = None) -> tuple[Path, Path]:
    """(마켓 CLI `--run-dir`, ⓐ 원본 백업 폴더) — `<회차>/web/market_<미리보기id>/`.

    **한 미리보기에서 나온 반영·이어서 확인은 전부 같은 폴더다.** `market_status.json`(taskId
    기록)이 거기 살기 때문이다 — 폴더가 갈리면 이어서 확인이 반영이 받은 taskId 를 못 보고,
    사람이 다시 반영한다. 그래서 `_상세폴더` 처럼 폴더를 **지어내지 않고** 부모 체인에서만 푼다.

    ⓐ 폴더는 미리보기의 부모 상세 잡이 쓴 `detail_<견적id>/before_detail` 이다(06-01 · D-03).
    부모가 없거나 체인이 틀리거나 회차가 다르면 ValueError(→ 400).
    """
    기대 = _마켓부모.get(kind)
    if 기대 is None:
        raise ValueError(f"마켓 잡이 아니다: {kind}")
    if not parent_job_id:
        raise ValueError(f"{kind} 에는 부모 잡이 필요하다 — 같은 market 폴더를 이어받아야 한다")

    def _행(i: str):
        if cx is not None:
            return cx.execute("SELECT kind, parent_job_id, run_dir FROM jobs WHERE id = ?",
                              (i,)).fetchone()
        return _row(i)

    부모 = _행(parent_job_id)
    if 부모 is None or 부모["kind"] not in 기대:
        raise ValueError(f"{kind} 의 부모는 {'/'.join(sorted(기대))} 여야 한다")
    if 부모["run_dir"] != run_dir:
        raise ValueError("부모 잡과 회차가 다르다")

    # 체인을 거슬러 미리보기 잡을 찾는다. poll→poll→…→commit→preview. 상한을 둬서 순환(있을 수
    # 없지만)이 서버를 붙잡지 않게 한다.
    if kind == "market_preview":
        미리보기id, 상세id, 상세행 = job_id, parent_job_id, 부모
    else:
        지금id, 지금 = parent_job_id, 부모
        for _ in range(200):
            if 지금 is None:
                break
            if 지금["kind"] == "market_preview":
                break
            if 지금["kind"] not in ("market_commit", "market_poll") or not 지금["parent_job_id"]:
                raise ValueError("마켓 잡 체인이 미리보기에서 나오지 않았다")
            지금id = 지금["parent_job_id"]
            지금 = _행(지금id)
        if 지금 is None or 지금["kind"] != "market_preview":
            raise ValueError("마켓 잡 체인이 미리보기에서 나오지 않았다")
        if 지금["run_dir"] != run_dir:
            raise ValueError("미리보기 잡과 회차가 다르다")
        미리보기id = 지금id
        상세id = 지금["parent_job_id"]
        상세행 = _행(상세id) if 상세id else None
        if 상세행 is None or 상세행["kind"] not in _마켓부모["market_preview"]:
            raise ValueError("미리보기의 부모가 상세 접수가 아니다")

    상세폴더 = _상세폴더(상세행["kind"], 상세id, 상세행["parent_job_id"], run_dir, cx)
    d = _web_dir(run_dir) / f"market_{미리보기id}"
    d.mkdir(parents=True, exist_ok=True)
    return d, 상세폴더 / "before_detail"


# ── 수면 방지 프리픽스 (ENG-06 / T-3-37) ────────────────────────────────────
# 인덱스 구축은 실측 3시간 32분짜리 폴링이다. 그 사이 맥북이 idle sleep 에 들어가면
# 자식이 통째로 멈춘다. `man caffeinate` 기준 **utility 를 인자로 주면 그 프로세스
# 수명 동안만** assertion 이 유지되므로 따로 해제할 일이 없다 — 켜 두고 잊어버려
# 배터리를 태우는 실수가 구조적으로 불가능하다.
#
# 붙는 자리가 여기인 이유: 조립은 `BulsajaArgv.prefix` 가 하지만 **무엇에 붙일지는
# 잡 종류가 정한다.** 라우트는 kind 만 고른다(03-05-PLAN §197).
#
# 인덱스에만 붙인다: 계정 확인은 실측 0.14초, 조인 스캔은 18초다. 수 초짜리 잡에
# 전력 assertion 을 거는 건 비용만 있고 얻는 게 없다.
#
# **배너 스캔도 붙인다 — 실측 4분 12초다.** 수 초짜리에 안 붙인다는 위 판단은 그대로이고,
# 4분은 그 선을 넘는다. 특히 그 4분의 대부분이 CDN 다운로드(271MB)라, idle sleep 으로
# 끊기면 받다 만 회차를 처음부터 다시 받는다.
CAFFEINATE = "/usr/bin/caffeinate"


def _수면방지_프리픽스(kind: str) -> list[str]:
    """`["/usr/bin/caffeinate", "-i"]` 또는 빈 리스트.

    바이너리 존재를 확인하고 없으면 **안 붙인다.** 맥 전용 바이너리라, 없는데 붙이면
    자식이 아예 안 뜬다 — "절전 방지" 하나 때문에 잡 전체가 실행 불가가 되는 건
    바꿔치기가 너무 나쁘다. 끊기면 재개가 복구하지만, 안 뜨면 복구할 것도 없다.

    exit code 가 그대로 넘어오는 것을 실측 확인했다(`caffeinate -i sh -c 'exit 3'` → 3).
    `ss_index_build.py` 의 종료코드 2/3/4 계약이 이 래퍼를 통과해도 살아 있다는 뜻이다.
    """
    # 상세 접수·이어서 확인도 붙인다(D-15) — 접수 뒤 폴링이 수십 분이다. 견적은 수 초라 안 붙인다.
    # 마켓 반영·이어서 확인도 붙인다 — upload_tasks 창 폴링이 최대 수십 분이다(D-07).
    if kind not in ("bulsaja_index", "banner_scan", "detail_submit", "detail_poll",
                    "market_commit", "market_poll"):
        return []
    try:
        return [CAFFEINATE, "-i"] if os.path.exists(CAFFEINATE) else []
    except OSError:
        # 경로 확인조차 실패하면 붙이지 않는다. 잡은 돌아야 한다.
        return []


def _build_argv(kind: str, job_id: str, run_dir: str | None, accounts: list[str],
                targets_path: Path | None, result_path: Path | None,
                commit: bool, *, detail_dir: Path | None = None,
                max_credits: int | None = None,
                market_dir: Path | None = None,
                detail_backup_dir: Path | None = None,
                max_items: int | None = None) -> list[str]:
    """kind → `AdsArgv`. **조립은 `webapp/argv.py` 한 곳에서만** 일어난다 (T-1-10)."""
    if kind in ("prep", "run"):
        return argv_mod.AdsArgv(subcommand=kind, run_dir=run_dir,
                                accounts=accounts).build()

    if kind == "bids_preview":
        return argv_mod.AdsArgv(subcommand="bids", run_dir=run_dir, accounts=accounts,
                                only_ads=targets_path, preview_out=result_path).build()

    if kind == "bids_commit":
        return argv_mod.AdsArgv(subcommand="bids", run_dir=run_dir, accounts=accounts,
                                commit=True, only_ads=targets_path,
                                preview_out=result_path).build()

    if kind in ("revert_only", "revert_all"):
        # `revert_only` 는 대상 목록으로 좁힌다(D-13 — 이 작업분만).
        # `revert_all` 은 좁히지 않는다(회차 전체). 대상 파일 유무가 그 차이의 전부다.
        #
        # **그래서 대상 파일이 없는 `revert_only` 는 존재할 수 없다.** 없으면
        # `AdsArgv` 가 `--only-ads` 를 안 붙이고 CLI 는 그걸 "백업 전량" 으로 읽는다
        # (`bids.run_revert` — `only_ads is None or ...`). kind 이름은 `revert_only`
        # 인데 동작은 `revert_all` 이 된다. 지금 운영 라우트는 항상 대상 파일을
        # 넘기므로 안 나지만, v2 의 APScheduler 가 인자 하나를 빼먹는 순간 회차
        # 전체(실측 2,242건)가 풀린다. **빈 값이 '전량' 으로 해석되는 경로는 예외로
        # 터뜨린다** — 이 페이즈에서 같은 부류가 두 번 사고 직전까지 갔다.
        if kind == "revert_only" and targets_path is None:
            raise ValueError("revert_only 에는 대상 파일이 반드시 있어야 한다 — "
                             "대상 없는 되돌리기는 회차 전체다(D-12)")
        return argv_mod.AdsArgv(subcommand="bids", run_dir=run_dir, accounts=accounts,
                                revert=True, commit=commit,
                                only_ads=targets_path if kind == "revert_only" else None,
                                preview_out=result_path).build()

    if kind in ("bulsaja_profile", "bulsaja_index", "bulsaja_scan"):
        # 대상 파일 규약은 광고 쪽과 같다 — `_write_targets` 가 쓰는 **JSON 배열** 하나다.
        # 담기는 내용만 다르다:
        #   · 인덱스 → groupId 문자열 리스트
        #   · 스캔   → "<계정alias>|<mallProductId>" 문자열 리스트 (`board.js` 의 Tabulator
        #     index 와 같은 모양이라 화면이 고른 행을 그대로 담을 수 있다)
        #
        # **둘 다 대상 파일이 필수다.** `revert_only` 와 **똑같은 이유**로 그렇다:
        # 없으면 자식이 그걸 "전량" 으로 읽는다. 빈 값이 전량으로 해석되는 경로는
        # 조립이 아니라 여기서 터뜨린다 (`BulsajaArgv.build()` 주석이 이 자리를 가리킨다).
        if kind == "bulsaja_index" and targets_path is None:
            raise ValueError("인덱스 잡에는 그룹 목록 파일이 반드시 있어야 한다 — "
                             "없으면 전 그룹(실측 75,335건 · 5시간 39분)이다")
        if kind == "bulsaja_scan" and targets_path is None:
            raise ValueError("스캔 잡에는 대상 목록 파일이 반드시 있어야 한다 (FLOW-02 / D-11)")

        하위 = {"bulsaja_profile": "profile", "bulsaja_index": "index",
                "bulsaja_scan": "scan"}[kind]
        # 설정값은 **전부 호출부에서 읽어 넘긴다.** 모델·CLI 에 기본값을 두면
        # workspace.toml 을 고쳐도 동작이 안 바뀌는 가짜 설정이 된다 (T-1-12).
        return argv_mod.BulsajaArgv(
            subcommand=하위,
            db=db_path(),
            out=result_path if result_path else bulsaja_index.profile_path(),
            profile_out=bulsaja_index.profile_path(),
            expect_nick=settings.cfg("expected_bulsaja_nick", required=True),
            min_interval=float(settings.cfg("mcp_min_interval",
                                            settings.DEFAULTS["mcp_min_interval"])),
            retry_after=int(settings.cfg("mcp_retry_after",
                                         settings.DEFAULTS["mcp_retry_after"])),
            batch_size=int(settings.cfg("mcp_batch_size",
                                        settings.DEFAULTS["mcp_batch_size"])),
            run_dir=run_dir if kind == "bulsaja_scan" else None,
            groups=targets_path if kind == "bulsaja_index" else None,
            targets=targets_path if kind == "bulsaja_scan" else None,
            prefix=_수면방지_프리픽스(kind),
        ).build()

    if kind == "banner_scan":
        # 배너 스캔의 "대상" 은 상품 목록이 아니라 **직전 성공 조인 스캔의 산출물 파일**
        # 하나다(`--join`). 그래서 `targets_path` 에 그 파일을 그대로 가리킨다 —
        # 새로 쓰지 않는다(`_override_targets` / D-11).
        #
        # 없으면 여기서 터뜨린다. `revert_only`·`bulsaja_index` 와 **똑같은 이유**다:
        # 빈 값이 조용히 '전량' 으로 미끄러지는 경로를 막는 자리는 한 곳이어야 한다.
        if targets_path is None:
            raise ValueError("배너 스캔에는 조인 산출물이 반드시 있어야 한다 — "
                             "빈 값은 전량이 아니다")
        if not run_dir:
            raise ValueError("배너 스캔에는 회차가 필요하다 — 원본 캐시·썸네일·산출물이 "
                             "회차별로 갈린다")
        if result_path is None:
            raise ValueError("배너 스캔에는 산출물 경로가 필요하다")

        # 🔴 설정을 **새로 읽는다.** 04-08 때 서버가 옛 `banner_lexicon_version` 을
        # 메모리(`settings._cache`)에 들고 있어 재시작해야 했다(04-GATE §0). 배너 잡 1회당
        # toml 한 번 읽기는 비용이 0 에 가깝다. 다른 kind 는 건드리지 않는다.
        settings.load(force=True)

        # 임계값·리비전·워커 수는 **전부 여기서 `settings.cfg()` 로 읽어 넘긴다.**
        # 모델이나 CLI 기본값에 기대면 `workspace.toml` 을 고쳐도 동작이 안 바뀌는
        # 가짜 설정이 된다(T-1-12). 그리고 넘긴 값이 그대로 산출물의 `판정규칙` 블록에
        # 찍히므로, 안 넘기면 **"무슨 규칙으로 판정했나" 의 출처가 둘**이 된다.
        return argv_mod.BannerArgv(
            join=targets_path,
            out=result_path,
            run_dir=run_dir,
            cache=banner_dir("banner_cache_dir"),
            thumbs=banner_dir("banner_thumb_dir"),
            workers=int(settings.cfg("banner_workers",
                                     settings.DEFAULTS["banner_workers"])),
            vision_revision=int(settings.cfg("banner_vision_revision",
                                             settings.DEFAULTS["banner_vision_revision"])),
            blank_ar=float(settings.cfg("banner_blank_ar",
                                        settings.DEFAULTS["banner_blank_ar"])),
            blank_short_px=int(settings.cfg("banner_blank_short_px",
                                            settings.DEFAULTS["banner_blank_short_px"])),
            skip_min_keep=int(settings.cfg("banner_skip_min_keep",
                                           settings.DEFAULTS["banner_skip_min_keep"])),
            skip_max_removal=float(settings.cfg("banner_skip_max_removal",
                                                settings.DEFAULTS["banner_skip_max_removal"])),
            lexicon_version=str(settings.cfg("banner_lexicon_version",
                                             settings.DEFAULTS["banner_lexicon_version"])),
            keep_runs=int(settings.cfg("banner_keep_runs",
                                       settings.DEFAULTS["banner_keep_runs"])),
            # 비전 2차(04-09 계약). 키 파일은 **경로 문자열만** — `banner_dir()` 을 쓰지
            # 마라(그건 데이터 루트 캐시용이다). 상대경로는 자식이 저장소 루트 기준으로 푼다.
            vision2_enabled=bool(settings.cfg("banner_vision2_enabled",
                                              settings.DEFAULTS["banner_vision2_enabled"])),
            vision2_model=str(settings.cfg("banner_vision2_model",
                                           settings.DEFAULTS["banner_vision2_model"])),
            vision2_prompt=str(settings.cfg("banner_vision2_prompt",
                                            settings.DEFAULTS["banner_vision2_prompt"])),
            vision2_key_file=Path(str(settings.cfg("banner_vision2_key_file",
                                                   settings.DEFAULTS["banner_vision2_key_file"]))),
            vision2_timeout=float(settings.cfg("banner_vision2_timeout",
                                               settings.DEFAULTS["banner_vision2_timeout"])),
            vision2_max_calls=int(settings.cfg("banner_vision2_max_calls",
                                               settings.DEFAULTS["banner_vision2_max_calls"])),
            vision2_interval=float(settings.cfg("banner_vision2_interval",
                                                settings.DEFAULTS["banner_vision2_interval"])),
            prefix=_수면방지_프리픽스(kind),
        ).build()

    if kind in ("detail_estimate", "detail_submit", "detail_poll"):
        # 🔴 inputs 없는 상세 잡은 없다. 없으면 CLI 가 products.json 경로(전량 수집)를 탄다 —
        # `revert_only`·`bulsaja_index` 와 같은 부류이고, 막는 자리는 여기 한 곳이다.
        if targets_path is None:
            raise ValueError("상세 잡에는 inputs 파일이 반드시 있어야 한다 — 빈 값은 전량이 아니다")
        if detail_dir is None:
            raise ValueError("상세 잡에는 detail 폴더가 필요하다")
        if result_path is None:
            raise ValueError("상세 잡에는 산출물 경로가 필요하다")
        if kind == "detail_submit" and max_credits is None:
            raise ValueError("상세 접수에는 max_credits 가 필요하다 — 상한 없는 접수는 없다(D-14)")

        # 배너 잡과 같은 이유로 설정을 새로 읽는다 — 재시작 없이 toml 변경이 반영되게.
        settings.load(force=True)
        return argv_mod.DetailArgv(
            mode={"detail_estimate": "estimate", "detail_submit": "submit",
                  "detail_poll": "poll"}[kind],
            run_dir=detail_dir,
            inputs=targets_path,
            done_tags=[str(t) for t in settings.cfg("done_tags", settings.DEFAULTS["done_tags"])],
            expect_nick=settings.cfg("expected_bulsaja_nick", required=True),
            max_poll_min=int(settings.cfg("detail_max_poll_min",
                                          settings.DEFAULTS["detail_max_poll_min"])),
            poll_interval=int(settings.cfg("detail_poll_interval",
                                           settings.DEFAULTS["detail_poll_interval"])),
            estimate_out=result_path if kind == "detail_estimate" else None,
            summary_out=result_path if kind != "detail_estimate" else None,
            max_credits=max_credits if kind == "detail_submit" else None,
            # 06-01 · D-03 — AI 생성이 완료되면 불사자 상세가 덮인다. 원본은 접수 순간에만
            # 뜰 수 있으므로 접수 잡은 항상 `<detail 폴더>/before_detail` 에 떨구게 한다.
            # (05-06 첫 실탄 전에 들어가야 하고, 사용자 서버는 재시작해야 이 값을 탄다.)
            backup_out=(detail_dir / "before_detail") if kind == "detail_submit" else None,
            prefix=_수면방지_프리픽스(kind),
        ).build()

    if kind in ("market_preview", "market_commit", "market_poll"):
        # 🔴 대상 파일 없는 마켓 잡은 없다 — 빈 값은 전량이 아니다(상세 잡과 같은 부류).
        if targets_path is None:
            raise ValueError("마켓 잡에는 대상 파일이 반드시 있어야 한다 — 빈 값은 전량이 아니다")
        if market_dir is None:
            raise ValueError("마켓 잡에는 market 폴더가 필요하다")
        if result_path is None:
            raise ValueError("마켓 잡에는 산출물 경로가 필요하다")
        # 상한은 라우트가 서버 쪽에서 정해 넘긴다(`_마켓반영상한`). None 을 전량으로 읽지 않는다.
        if kind == "market_commit" and max_items is None:
            raise ValueError("마켓 반영에는 max_items 가 필요하다 — 상한 없는 반영은 없다(D-06)")
        if kind != "market_poll" and detail_backup_dir is None:
            raise ValueError("마켓 미리보기·반영에는 ⓐ 원본 백업 폴더가 필요하다(MARKET-03)")

        settings.load(force=True)
        return argv_mod.MarketArgv(
            mode={"market_preview": "preview", "market_commit": "commit",
                  "market_poll": "poll"}[kind],
            run_dir=market_dir,
            targets=targets_path,
            expect_nick=settings.cfg("expected_bulsaja_nick", required=True),
            # 이어서 확인은 백업을 안 쓴다 — 폴더를 넘기지 않는다(플래그 자체가 안 붙는다).
            detail_backup_dir=detail_backup_dir if kind != "market_poll" else None,
            backup_dir=(market_dir / "before_market") if kind != "market_poll" else None,
            summary_out=result_path,
            poll_interval=int(settings.cfg("market_poll_interval",
                                           settings.DEFAULTS["market_poll_interval"])),
            max_poll_min=int(settings.cfg("market_max_poll_min",
                                          settings.DEFAULTS["market_max_poll_min"])),
            max_items=max_items if kind == "market_commit" else None,
            prefix=_수면방지_프리픽스(kind),
        ).build()

    raise ValueError(f"argv 를 조립할 수 없는 작업 종류다: {kind}")


def create_job(kind: str, *, run_dir: str | None = None,
               accounts: list[str] | None = None,
               only_ads: list[str] | None = None,
               commit: bool = False,
               parent_job_id: str | None = None,
               targets_path_override: str | Path | None = None,
               argv_override: list[str] | None = None,
               detail_inputs: dict | None = None,
               max_credits: int | None = None,
               max_items: int | None = None) -> str:
    """작업을 만들고 자식을 띄운 뒤 `job_id` 를 즉시 돌려준다. **블로킹하지 않는다.**

    **이 함수는 HTTP 를 모른다** (D-17 / ENG-07). 요청 객체를 받지 않고 상태코드를
    모른다. v2 의 APScheduler 가 이 함수를 그대로 부른다 — 그때 라우트를 통해
    자기 서버에 요청을 쏘는 모양이 되지 않게 지금 경계를 그어 둔다.

    순서에 의미가 있다:
      ①.5 불사자 계정 가드 (AccountMismatchError) — **트랜잭션을 열기 전에.**
          파일 읽기라 DB 경합과 무관하고, 3시간 32분짜리 인덱스를 틀린 계정으로 쌓고 나면
          되돌리는 비용이 그 시간 전부다. 그래서 제일 먼저 본다 (ENG-08)
      ① 쓰기 잡 전역 가드 (BusyError) — 자식을 띄우기 **전에** 막는다
      ①.9 같은 kind 중복 가드 (SameKindBusyError) — **트랜잭션 안.** DB 상태를 보는
          체크라 ①과 같은 창 안에 있어야 두 요청이 "둘 다 없네" 를 보고 둘 다 들어가지
          않는다. 계정 가드(①.5)가 밖인 것과 대비된다 (SINGLETON_KINDS 주석)
      ② 회차 화이트리스트 — 라우트가 깜빡해도 여기서 막힌다 (T-1-11)
      ③ 대상 목록을 파일로 (FLOW-02)
      ④ argv 조립 (webapp/argv.py 한 곳)
      ⑤ jobs 행 INSERT (status='starting' — **아직 running 이 아니다**)
      ⑥ spawn → pid 와 status='running' 을 **같이** UPDATE

    `only_ads` 와 `targets_path_override` 는 **상호배타**다. 전자는 목록을 받아 파일을
    새로 쓰고, 후자는 이미 있는 파일을 그대로 가리킨다 — 둘을 같이 주면 어느 쪽이
    진짜 대상인지 모르는 상태가 된다. 대상 파일은 하나다 (D-11 / FLOW-02 / T-1-06).

    `argv_override` 는 **테스트 전용**이다. 합성 잡(`kind="synthetic"`)처럼 임의 argv 를
    태우는 유일한 경로라, 운영 라우트에는 절대 노출하지 않는다 (T-1-23).
    라우트는 kind 가 경로마다 고정이고 클라이언트가 kind 를 문자열로 넘기지 못한다.
    """
    if kind not in KINDS:
        raise ValueError(f"모르는 작업 종류다: {kind}")
    # 상호배타 가드. 이 한 줄이 "대상 파일은 하나" 를 코드로 강제한다 —
    # 주석이나 관례가 아니라 호출하는 순간 터지는 규칙이어야 한다.
    if only_ads is not None and targets_path_override is not None:
        raise ValueError("only_ads 와 targets_path_override 를 같이 줄 수 없다 — 대상 파일은 하나다")
    if kind == "synthetic" and not argv_override:
        raise ValueError("합성 잡은 argv_override 가 필요하다 (테스트 전용 경로)")
    # 상세 견적은 inputs 문서를 **받아서 새로 쓴다**(관문 통과분). 접수·이어서 확인은 새로 쓰지
    # 않고 견적이 쓴 그 파일을 가리킨다(targets_path_override) — 대상 파일은 하나다.
    DETAIL_KINDS = ("detail_estimate", "detail_submit", "detail_poll")
    # 대상 문서를 **새로 쓰는** kind. 마켓 미리보기·반영은 라우트가 서버 쪽 정본(detail_status.json ·
    # preview.json)에서 만든 문서를 넘긴다(L-02). 이어서 확인만 부모의 파일을 그대로 가리킨다.
    INPUTS_KINDS = ("detail_estimate", "market_preview", "market_commit")
    if detail_inputs is not None and kind not in INPUTS_KINDS:
        raise ValueError("detail_inputs 는 상세 견적·마켓 미리보기·마켓 반영 전용이다")
    if kind in INPUTS_KINDS and detail_inputs is None:
        raise ValueError(f"{kind} 에는 대상 문서가 반드시 있어야 한다 — 빈 값은 전량이 아니다")
    if max_items is not None and kind != "market_commit":
        raise ValueError("max_items 는 마켓 반영 전용이다")

    # ①.5 불사자 계정 가드 (ENG-08). **자식을 띄우기 전이고, 트랜잭션을 열기도 전이다.**
    #      여기가 라우트가 아니라 `create_job` 인 것이 핵심이다 — v2 의 APScheduler 가
    #      이 함수를 그대로 부르므로, 라우트에 두면 스케줄러가 가드를 통째로 우회한다
    #      (D-17 / ENG-07).
    #      `required=True` 를 쓰는 것도 핵심이다. 값이 비면 KeyError 로 터져야지 조용히
    #      폴백해 가드가 사라지면 안 된다(T-1-12). 그 KeyError 는 라우트에서 500 이 되는데,
    #      **그게 맞다** — 설정이 빈 채로 불사자 잡이 도는 것보다 낫다.
    if kind in BULSAJA_KINDS:
        통과, 사유 = bulsaja_index.profile_ok(
            settings.cfg("expected_bulsaja_nick", required=True),
            int(settings.cfg("profile_max_age_min",
                             settings.DEFAULTS["profile_max_age_min"])))
        if not 통과:
            raise AccountMismatchError(사유)

    accounts = list(accounts or [])
    init_db()
    job_id = str(uuid.uuid4())
    log_path = log_path_of(job_id)
    BIDS_KINDS = ("bids_preview", "bids_commit", "revert_only", "revert_all")
    # 불사자 산출물 파일명 접두. `BIDS_KINDS` 와 **나란히** 둔다 (아래 result_path 분기).
    BULSAJA_접두 = {"bulsaja_scan": "join", "bulsaja_index": "index",
                    "bulsaja_profile": "profile"}

    cx = _conn()
    try:
        # ① 가드 ~ ⑤ INSERT 를 한 트랜잭션에 묶는다. 두 요청이 스레드풀에서
        #    겹쳐도 "둘 다 비었네" 를 보고 둘 다 들어가는 일이 없다.
        #    가드를 **맨 먼저** 본다 — 어차피 거부될 작업 때문에 회차에 대상 파일을
        #    떨구고 나서 409 를 내면 run-dir/web 에 쓰레기가 쌓인다.
        cx.execute("BEGIN IMMEDIATE")
        _reap(cx)
        if kind in WRITE_KINDS:
            표시 = ",".join("?" * len(WRITE_KINDS))
            상태표시 = ",".join("?" * len(LIVE_STATUSES))
            # **`starting` 도 본다.** 안 보면 자식을 띄우는 중인 쓰기 잡을 가드가 못 잡아
            # 두 번째 쓰기 잡이 들어간다 — 고치려던 구멍이 이름만 바뀐다.
            막는것 = cx.execute(
                f"SELECT id, kind FROM jobs WHERE status IN ({상태표시}) AND kind IN ({표시}) "
                "ORDER BY rowid LIMIT 1",
                tuple(LIVE_STATUSES) + tuple(sorted(WRITE_KINDS))).fetchone()
            if 막는것:
                raise BusyError(
                    f"이미 도는 쓰기 작업이 있다: {막는것['id']} ({막는것['kind']})")

        # ①.9 같은 kind 중복 가드. **트랜잭션 안**이다 — 쓰기 가드와 같은 이유로,
        #     두 요청이 스레드풀에서 겹쳐 "둘 다 없네" 를 보고 둘 다 들어가는 창을 없앤다.
        #     계정 확인(①.5)은 파일 읽기라 밖이지만, 이 체크는 DB 상태를 보므로 안이다.
        #     **`starting` 도 본다**(`LIVE_STATUSES`). `running` 만 보면 자식을 띄우는 중인
        #     잡을 못 잡아 구멍이 그대로 남는다 — 위 LIVE_STATUSES 주석이 이미 한 번 고친 실수다.
        if kind in SINGLETON_KINDS:
            상태표시 = ",".join("?" * len(LIVE_STATUSES))
            겹친것 = cx.execute(
                f"SELECT id FROM jobs WHERE status IN ({상태표시}) AND kind = ? "
                "ORDER BY rowid LIMIT 1",
                tuple(LIVE_STATUSES) + (kind,)).fetchone()
            if 겹친것:
                # 메시지에 **어느 kind 인지**와 "전역 쓰기 락이 아니다" 를 같이 밝힌다.
                # 안 밝히면 사용자가 엉뚱하게 입찰가 작업을 찾으러 간다.
                raise SameKindBusyError(
                    f"같은 작업이 이미 돌고 있다: {겹친것['id']} ({kind}). "
                    "전역 쓰기 락이 아니라 같은 종류 중복이다 — 끝나기를 기다려라")

        # ② 회차 화이트리스트. `..` 를 거르는 블랙리스트가 아니라 "실재하는 회차 목록에
        #    있는 이름만" 통과시킨다. 실패는 ValueError → 라우트가 400 으로 번역한다.
        if run_dir:
            paths.run_dir_path(run_dir)
        elif kind in BIDS_KINDS and not argv_override:
            # `argv_override` 가 있으면 argv 를 통째로 받으므로 회차 요구가 의미 없다.
            # 그 경로는 테스트 전용이다(운영 라우트는 argv_override 를 넘기지 않는다).
            raise ValueError("입찰가 작업에는 회차가 필요하다")

        # ③ 대상 목록 → 파일. **경로는 웹앱이 만든다** — 사용자 입력에서 경로를 받지
        #    않는다(ASVS V12 / T-1-11).
        #    **`is not None` 이다 — 빈 목록도 파일로 떨군다.** `if only_ads:` 로 두면
        #    "아무것도 안 골랐다" 가 argv 에서 `--only-ads` 자체를 없애고, CLI 는
        #    그걸 "전량" 으로 읽는다(`_load_only_ads` 가 None 이면 전량이다).
        #    0건이 조용히 2,242건이 되는 길이라, 대상 파일 없이 입찰가 명령을
        #    만들지 않는다 (T-1-05 와 같은 종류의 사고).
        #
        #    `targets_path_override` 는 그 반대다 — **새로 쓰지 않고** 미리보기가 만든
        #    파일을 그대로 가리킨다(D-11). 실행이 화면 상태에서 목록을 다시 만들면,
        #    미리보기와 실행 사이에 필터가 바뀐 만큼 본 것과 다른 게 실행된다.
        targets_path = None
        if kind in INPUTS_KINDS:
            if not run_dir:
                raise ValueError(f"{kind} 에는 회차가 필요하다")
            if only_ads is not None or targets_path_override is not None:
                raise ValueError(f"{kind} 의 대상은 detail_inputs 하나다")
            targets_path = _write_detail_inputs(job_id, run_dir, detail_inputs)
        elif only_ads is not None:
            if not run_dir:
                raise ValueError("대상 목록을 쓰려면 회차가 필요하다")
            targets_path = _write_targets(job_id, run_dir, list(only_ads))
        elif targets_path_override is not None:
            targets_path = _override_targets(run_dir, targets_path_override)

        result_path = None
        detail_dir = None
        market_dir = None
        detail_backup_dir = None
        if run_dir and kind in BIDS_KINDS:
            접두 = "preview" if kind == "bids_preview" else "result"
            result_path = _web_dir(run_dir) / f"{접두}_{job_id}.json"
        elif kind in BULSAJA_접두:
            # `BIDS_KINDS` 를 건드리지 않고 나란한 집합을 하나 더 둔다 — 두 계열의
            # 산출물 규칙이 한 조건문에 섞이면 한쪽을 고칠 때 다른 쪽이 따라 바뀐다.
            #
            # **`bulsaja_profile` 은 `run_dir` 이 없어도 돌아야 한다.** 계정 확인은 회차와
            # 무관하고, 오히려 회차를 고르기 전에 눌러야 하는 버튼이다. 그 산출물은
            # 설정이 정한 프로필 파일 한 자리다(`bulsaja_index.profile_path()` — 읽는 쪽과
            # 같은 계산을 본다).
            #
            # 인덱스·스캔은 회차의 `web/` 밑이다. 인덱스 **기록**은 회차를 넘어 살지만
            # (`ss_index` 테이블), 그 잡의 **진행요약 산출물**은 회차에 속한다 — 대상(그룹)
            # 목록 파일도 거기 있어서 "무엇을 넣어 무엇이 나왔나" 가 한 폴더에 모인다.
            if kind == "bulsaja_profile":
                result_path = bulsaja_index.profile_path()
            elif not run_dir:
                raise ValueError(f"{kind} 에는 회차가 필요하다 — 산출물과 대상 목록이 "
                                 "회차의 web/ 밑에 같이 남아야 추적이 된다")
            else:
                result_path = _web_dir(run_dir) / f"{BULSAJA_접두[kind]}_{job_id}.json"
        elif kind == "banner_scan":
            # `BULSAJA_접두` 에 얹지 않고 분기를 따로 둔다 — 이 잡은 불사자 계열이
            # 아니다(MCP 0회). 한 조건문에 섞으면 다음 사람이 "배너도 불사자 잡" 으로
            # 읽고 `BULSAJA_KINDS` 에 넣는다. 자리는 조인 산출물과 **같은 폴더**다:
            # `<회차>/web/banner_<job_id>.json` — 무엇을 넣어 무엇이 나왔나가 한 곳에 모인다.
            if not run_dir:
                raise ValueError("배너 스캔에는 회차가 필요하다 — 산출물과 조인 입력이 "
                                 "회차의 web/ 밑에 같이 남아야 추적이 된다")
            result_path = _web_dir(run_dir) / f"banner_{job_id}.json"
        elif kind in DETAIL_KINDS:
            # CLI 의 `--run-dir` 은 회차 폴더가 아니라 **견적 하나당 폴더**다(`_상세폴더`).
            # 견적 결과는 estimate.json 하나, 접수·이어서 확인은 잡마다 summary_<id>.json.
            if not run_dir:
                raise ValueError(f"{kind} 에는 회차가 필요하다")
            detail_dir = _상세폴더(kind, job_id, parent_job_id, run_dir, cx)
            result_path = (detail_dir / "estimate.json" if kind == "detail_estimate"
                           else detail_dir / f"summary_{job_id}.json")
        elif kind in MARKET_KINDS:
            # CLI 의 `--run-dir` 은 미리보기 하나당 폴더다(`_마켓폴더`). 미리보기는 preview.json
            # 하나, 반영·이어서 확인은 잡마다 summary_<id>.json.
            if not run_dir:
                raise ValueError(f"{kind} 에는 회차가 필요하다")
            market_dir, detail_backup_dir = _마켓폴더(kind, job_id, parent_job_id, run_dir, cx)
            result_path = (market_dir / "preview.json" if kind == "market_preview"
                           else market_dir / f"summary_{job_id}.json")

        # ④ argv
        if argv_override:
            cmd = list(argv_override)
        else:
            cmd = _build_argv(kind, job_id, run_dir, accounts,
                              targets_path, result_path, commit,
                              detail_dir=detail_dir,
                              max_credits=max_credits,
                              market_dir=market_dir,
                              detail_backup_dir=detail_backup_dir,
                              max_items=max_items)

        cx.execute(
            "INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
            "targets_path, result_path, parent_job_id, target_count, started_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, kind, run_dir,
             json.dumps(accounts, ensure_ascii=False),
             json.dumps(cmd, ensure_ascii=False),      # 재현·감사용. 시크릿 없음
             # **`running` 이 아니라 `starting` 이다.** pid 는 spawn 뒤에야 들어오는데,
             # 그 전에 `running` 으로 적으면 `_reap` 이 `pid=NULL` 을 죽음으로 읽고
             # 멀쩡한 잡을 `orphaned` 로 찍어 전역 쓰기 가드가 풀린다(LIVE_STATUSES 주석).
             "starting", str(log_path),
             str(targets_path) if targets_path else None,
             str(result_path) if result_path else None,
             parent_job_id,
             # 대상 수: 목록을 받았으면 그 길이, 파일을 가리켰으면 **그 파일을 읽어** 센다.
             # 화면이 "5건" 이라고 말해도 파일에 2,242건이 들어 있으면 실행되는 건 2,242건이다.
             (len(only_ads) if only_ads is not None
              else (_count_targets(targets_path) if targets_path else None)),
             _now()))
        cx.commit()
    finally:
        cx.close()

    # ⑥ 자식 띄우기. 실패하면 행을 failed 로 닫는다 — starting 으로 남겨 두면
    #    전역 가드가 `STARTING_TIMEOUT_SEC` 동안 걸린다.
    try:
        proc = spawn(cmd, log_path)
    except Exception as e:
        cx = _conn()
        try:
            cx.execute("UPDATE jobs SET status='failed', exit_code=-1, ended_at=? WHERE id=?",
                       (_now(), job_id))
            cx.commit()
        finally:
            cx.close()
        raise RuntimeError(f"작업을 띄우지 못했다: {type(e).__name__}: {e}")

    # 자식이 떴다. **pid 와 status 를 한 UPDATE 로 같이 올린다** — pid 만 먼저 쓰고
    # status 를 나중에 쓰면 그 사이가 또 창이 된다. `_PROCS` 등록을 UPDATE 보다 먼저
    # 하는 것도 같은 이유다: `running` 으로 보이는 순간에는 `poll()` 할 객체가 이미 있어야
    # `_reap` 이 종료코드를 지어내지 않는다.
    _PROCS[job_id] = proc
    cx = _conn()
    try:
        cx.execute("UPDATE jobs SET pid = ?, status = 'running' WHERE id = ?",
                   (proc.pid, job_id))
        cx.commit()
    finally:
        cx.close()

    return job_id


# ── 조회 ────────────────────────────────────────────────────────────────────

def _as_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["elapsed_sec"] = _elapsed(d.get("started_at"), d.get("ended_at"))
    return d


def _elapsed(started: str | None, ended: str | None) -> float | None:
    """시작부터의 경과초. 진행률이 없는 작업(`bids --commit`)의 유일한 진행 표시다(OQ-3).

    끝난 작업은 총 소요시간, 도는 작업은 지금까지의 경과시간이다.
    """
    if not started:
        return None
    try:
        t0 = datetime.fromisoformat(started)
        t1 = datetime.fromisoformat(ended) if ended else datetime.now().astimezone()
        return round((t1 - t0).total_seconds(), 1)
    except ValueError:
        return None


def job_status(job_id: str) -> dict | None:
    """jobs 행 + 살아있는지 확인한 최신 상태. 없으면 None.

    **상태를 바꾸지 않는다** 는 뜻이 아니다 — 죽은 자식을 발견하면 그 사실을 적는다.
    적지 않으면 전역 가드가 유령 작업에 영원히 걸린다. 다만 광고 API·run-dir 산출물은
    건드리지 않으므로 읽기 라우트에서 불러도 된다.
    """
    cx = _conn()
    try:
        cx.execute("BEGIN IMMEDIATE")
        _reap(cx)
        cx.commit()
        row = cx.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        cx.close()
    return _as_dict(row) if row else None


def active_job() -> dict | None:
    """지금 도는 작업 하나. 없으면 None.

    **화면이 스트림을 하나만 열게 하는 장치다** (T-1-24). 페이지를 새로 그릴 때
    "무엇을 보여줄까" 를 여기서 한 번에 정한다 — 목록에서 running 을 골라내는
    판단이 템플릿·라우트 두 곳에 흩어지면 둘이 어긋난다.

    끝난 작업은 돌려주지 않는다. 새로고침할 때마다 지난 작업 패널이 되살아나면
    "아직 도는 중인가?" 로 읽힌다 — 이 화면에서 제일 비싼 오해다.

    레지스트리가 아직 없으면 **만들지 않고** None 을 준다. 이 함수를 부르는 건
    `GET /` 인데, 읽기 라우트가 파일을 만들기 시작하면 "GET 은 상태를 안 바꾼다"는
    방어의 전제가 흐려진다(T-1-01b). 첫 작업을 누르는 순간 `create_job` 이 만든다.
    """
    if not db_path().is_file():
        return None
    try:
        도는것 = [j for j in recent_jobs(50) if j.get("status") == "running"]
    except sqlite3.Error:
        return None
    return 도는것[0] if 도는것 else None


def latest_done(kind: str, run_dir: str | None = None) -> dict | None:
    """그 종류의 **가장 최근 성공 잡** 1건. 없으면 None.

    03-05·03-06 이 "마지막 조인 산출물" 을 찾는 **유일한 길**이다.
    `web/join_*.json` 을 glob 으로 뒤지지 마라 — 파일이 있다는 것과 그 잡이 성공했다는 것은
    다르다(중간에 죽은 잡도 반쯤 쓴 파일을 남긴다). 어느 잡이 성공했는지는 레지스트리가 정본이다.

    `run_dir` 을 주면 그 회차로 좁힌다. 인덱스 잡처럼 회차를 넘어 사는 종류는 안 주면 된다.

    레지스트리가 아직 없으면 **만들지 않고** None 이다 — `active_job()` 과 같은 규율(T-1-01b).
    """
    if kind not in KINDS:
        raise ValueError(f"모르는 작업 종류다: {kind}")
    if not db_path().is_file():
        return None
    cx = _conn()
    try:
        cx.execute("BEGIN IMMEDIATE")
        _reap(cx)
        cx.commit()
        조건 = "kind = ? AND status = 'done'"
        인자: tuple = (kind,)
        if run_dir:
            조건 += " AND run_dir = ?"
            인자 = (kind, run_dir)
        row = cx.execute(
            f"SELECT * FROM jobs WHERE {조건} ORDER BY started_at DESC, rowid DESC LIMIT 1",
            인자).fetchone()
    except sqlite3.Error:
        return None
    finally:
        cx.close()
    return _as_dict(row) if row else None


def recent_jobs(limit: int = 20) -> list[dict]:
    """최근 작업 목록(최신순). 같은 초에 만들어진 것끼리는 입력 순서의 역순이다."""
    cx = _conn()
    try:
        cx.execute("BEGIN IMMEDIATE")
        _reap(cx)
        cx.commit()
        rows = cx.execute(
            "SELECT * FROM jobs ORDER BY started_at DESC, rowid DESC LIMIT ?",
            (int(limit),)).fetchall()
    finally:
        cx.close()
    return [_as_dict(r) for r in rows]


def children_of(parent_job_id: str, kind: str | None = None) -> list[dict]:
    """이 잡을 부모로 가리키는 잡들(최신순). 없으면 빈 리스트.

    상세 접수가 **한 견적에서 두 번** 뜨지 않게 라우트가 묻는 창이다 — 두 번째 접수는
    체크포인트에 taskId 가 없는 건(접수실패 등)을 다시 접수하게 되고, 그건 MVP 가 미뤄 둔
    실패분 재접수(D-18)와 같다. 레지스트리가 아직 없으면 **만들지 않고** 빈 리스트다(T-1-01b).
    """
    if not db_path().is_file():
        return []
    cx = _conn()
    try:
        조건, 인자 = "parent_job_id = ?", (parent_job_id,)
        if kind:
            조건, 인자 = 조건 + " AND kind = ?", (parent_job_id, kind)
        rows = cx.execute(f"SELECT * FROM jobs WHERE {조건} ORDER BY started_at DESC, rowid DESC",
                          인자).fetchall()
    except sqlite3.Error:
        return []
    finally:
        cx.close()
    return [_as_dict(r) for r in rows]

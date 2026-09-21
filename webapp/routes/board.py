#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보드 화면.

    GET /                토큰(쿼리) → 쿠키 교환 후 보드 렌더                  [읽기]
    GET /?run_dir=<회차>  다른 회차로 갈아타기                                 [읽기]

화면에는 보드 말고 **도는 작업 패널**도 실린다. 그 패널이 진행 로그 스트림을 여는
유일한 자리라, 새로고침·재접속 때 여기서 작업을 실어 주지 않으면 성공기준 3
("탭을 닫았다 열어도 로그를 처음부터 이어서 본다")이 화면에서 성립하지 않는다.

**이 라우트는 GET 이지만 서버 상태를 바꾸지 않는다.** 쿠키를 심는 것은 *브라우저*
상태를 바꾸는 것이고, 디스크·광고 API·잡 레지스트리에는 아무 일도 일어나지 않는다.
그 구분이 중요한 이유: "GET 은 상태를 안 바꾼다" 가 `security.guard` 의 Origin 방어를
성립시키는 전제이기 때문이다(T-1-01b). 여기서 한 번 예외를 허용하면 그 다음 사람이
"작업 실행도 GET 으로 하면 편한데" 로 간다. `security_curl.sh` 의 V-SAFE-01d 가
이 파일의 GET 핸들러 본문을 실제로 훑어서 기계로 집행한다.

**CLI 를 실행하지 않는다.** 보드 데이터는 `run-dir/result.json` 을 읽어 투영할 뿐이라
네트워크도 크레딧도 광고비도 0 이다(STACK.md "세 번째 길"). 무거운 건 파일 읽기 하나뿐이라
`async def` 가 아니라 **`def`** 로 선언한다 — async 핸들러에서 blocking 파일 IO 를 하면
이벤트 루프가 멈춰 SSE 진행 로그가 같이 끊긴다(Anti-Patterns).
"""
import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from webapp import board, bulsaja_index, jobs, join, paths, security, settings, state

router = APIRouter()

# 미해소 사유코드 → **화면에 쓸 이름**. 코드값을 그대로 띄우지 않는 이유는 하나다.
#
# `join.미스` 의 뜻은 "마켓그룹은 좁혔는데 그 안에 이 상품이 없다" 인데, 인덱스를 한 번도
# 안 훑은 상태에서도 그 판정이 난다(03-05 실측: 스캔 후·인덱스 전에 84행). 서버가 기동하며
# 빈 인덱스 테이블을 만들어 두기 때문이다. 그 글자를 화면에 그대로 쓰면 용팀장이 광고 쪽
# 오류로 읽는다 — 이 페이즈 최대 오진(Pitfall 3)의 입구다.
# 그래서 `group_health(...)["완결"]` 로 한 번 더 갈라 "인덱스 불완전" 으로 띄운다.
#
# ⚠️ `join.py` 의 사유코드 자체는 **건드리지 않는다.** 판정의 정본은 거기 하나이고,
#    여기는 그 값에 사람이 읽을 이름을 덧붙일 뿐이다(화이트리스트 투영과 같은 성질).
_인덱스불완전 = "인덱스 불완전"
#
# 이름 자체가 버킷을 말하게 지었다 — **기호나 색에 기대지 않는다.**
#   `번호…`   로 시작하면 광고 쪽 오류 (사람이 네이버 광고에서 고친다)
#   `인덱스…` 로 시작하면 시스템 사정 (기계가 더 돌면 된다)
# 흑백 출력·색맹에서도 이 구분이 살아 있어야 한다. 이 화면이 존재하는 이유다.
_사유이름 = {
    join.추출실패: "번호 추출 실패",
    join.번호없음: "번호 없음",
    join.미조회: "인덱스 미보유",
    join.불일치: "인덱스 불일치",
    join.미스: "인덱스에 없음",
}


def _불사자표시() -> dict:
    """보드 상단에 상시로 띄울 불사자 계정 정보 (ENG-08 / 성공기준 6).

    **필요한 값만 뽑아 싣는다.** `bulsaja_index.profile()` 응답을 통째로 넘기지 않는
    이유는 두 가지다: ① 이 파일의 화이트리스트 투영 관례(SAFE-03) ② 불사자 응답에
    섞여 오는 모델 대상 지시문(`표시규칙`)이 화면으로 새는 길을 구조적으로 막는 것.
    `profile()` 이 이미 그 필드를 버리지만, 투영이 두 번째 벽이다.

    **MCP 를 부르지 않는다** (D-19). 자식 프로세스가 써 둔 파일을 읽을 뿐이라
    네트워크도 크레딧도 0 이고, 파일이 없으면 "계정 확인을 먼저" 라고 말한다.

    `expected_bulsaja_nick` 이 비면 `cfg(..., required=True)` 가 KeyError 를 던진다.
    보드는 **읽기 라우트**라 그게 500 이 되면 화면이 통째로 안 뜬다 — 그러면 사용자는
    "설정이 비었다" 를 영영 못 본다. 그래서 **여기서만** 잡아서 배너 문구로 바꾼다.
    조용히 통과시키는 게 아니라 **화면이 그 사실을 말하게** 하는 것이다.
    쓰기 경로(`jobs.create_job`)는 계속 터뜨린다 — 거기선 가드가 죽으면 안 된다.
    """
    받은것 = bulsaja_index.profile()
    표시 = {
        "닉네임": (받은것 or {}).get("닉네임") or None,
        "크레딧": (받은것 or {}).get("크레딧") or None,
        "확인시각": (받은것 or {}).get("확인시각") or None,
        "일치": False,
        "사유": None,
    }
    try:
        기대 = settings.cfg("expected_bulsaja_nick", required=True)
    except KeyError:
        표시["사유"] = "설정 webapp.expected_bulsaja_nick 이 비었다 — workspace.toml 을 채워라"
        return 표시

    통과, 사유 = bulsaja_index.profile_ok(
        기대, int(settings.cfg("profile_max_age_min",
                              settings.DEFAULTS["profile_max_age_min"])))
    표시["일치"] = bool(통과)
    표시["사유"] = 사유 or None          # 통과면 빈 문자열이 온다 — 0 이 아니라 None 규약
    return 표시


def _load_result(run_dir_name: str) -> tuple[dict, str | None]:
    """`result.json` 을 읽는다. 실패하면 `({}, 사유)` — **폴백하지 않는다**.

    다른 회차로 몰래 갈아타거나 빈 dict 를 성공인 척 돌려주지 않는다. 읽기 실패는
    화면에 사유를 띄우고 빈 보드를 보여준다: 이 실패는 돈으로 이어지지 않으므로
    프로세스를 죽일 일이 아니고(저장소 S-2 판별 기준), 그렇다고 조용히 넘어가면
    사용자가 "오늘은 판정 대상이 없구나" 로 오독한다.

    예외 문자열은 `f"{type(e).__name__}: {e}"` 로 축약한다 — 트레이스백을 화면에
    실으면 경로·내부 구조가 그대로 나간다(ASVS V7).
    """
    try:
        raw = (paths.run_dir_path(run_dir_name) / "result.json").read_text(encoding="utf-8")
        return json.loads(raw), None
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"


def _load_join(run_dir_name: str) -> tuple[dict | None, str | None, str | None]:
    """마지막 성공 스캔의 조인 산출물을 읽는다 — `(문서, 스캔시각, 사유)`.

    `_load_result` 와 **같은 모양**이다: 실패하면 값을 지어내지 않고 사유를 들고 온다.
    다만 돌려주는 빈값이 `{}` 가 아니라 `None` 인 것에 뜻이 있다 — 조인 부착 함수는
    `None` 을 "아직 조인을 안 돌렸다" 로 읽어 전 행을 `미조회`/`시스템` 으로 낸다.
    빈 dict 를 주면 "마켓그룹 목록이 비었다" 가 되어 전 행이 **광고 청소 대상**으로
    둔갑한다 — 그게 Pitfall 3 그 자체다.

    🔴 그래서 `마켓그룹` 이 빈 산출물도 **`None` 으로 내린다**(CR-01, 2026-09-21).
    이 주석은 함정을 정확히 적어 두고도 `문서 is None` 만 막고 있었고, `"마켓그룹": []`
    은 그대로 통과했다. 통과하면 결과가 빈 dict 와 한 글자도 다르지 않다 — 재현 결과
    전체 9행 중 9행이 광고청소, 청소그룹 8개였다. 실측 86개짜리 목록이 0개로 오는 것은
    관측이 아니라 조회 실패다(CLI 가 1층에서 막지만, 이미 디스크에 남은 산출물과
    다음에 생길 같은 모양의 구멍까지 막으려면 읽는 쪽에도 같은 규율이 있어야 한다).
    `None` 으로 내려가면 전 행이 `미조회`/`시스템` 이 되어 **안전한 쪽**으로 떨어진다.

    어느 잡이 성공했는지는 **레지스트리가 정본**이다. 회차 폴더의 파일을 뒤져서 찾지
    마라 — 파일이 있다는 것과 그 잡이 성공했다는 것은 다르다(중간에 죽은 잡도 반쯤
    쓴 파일을 남긴다). `jobs.latest_done` 이 그 질문에 답하려고 있는 함수다.

    **스캔을 한 번도 안 돌린 것은 실패가 아니다** — 사유 없이 `(None, None, None)` 이고,
    화면이 "아직 조인 스캔을 안 돌렸다" 를 말한다. 사유를 채우면 고장으로 읽힌다.
    """
    try:
        잡 = jobs.latest_done("bulsaja_scan", run_dir_name)
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"
    if not 잡:
        return None, None, None

    경로 = 잡.get("result_path")
    시각 = 잡.get("ended_at") or 잡.get("started_at")
    if not 경로:
        return None, None, "스캔 작업에 산출물 경로가 없다 — 조인 스캔을 다시 돌려라"
    try:
        문서 = json.loads(Path(경로).read_text(encoding="utf-8"))
    except Exception as e:
        # 트레이스백을 화면에 싣지 않는다 — 경로·내부 구조가 그대로 나간다(ASVS V7).
        return None, None, f"{type(e).__name__}: {e}"
    if not isinstance(문서, dict):
        return None, None, "조인 산출물의 모양이 다르다 — 조인 스캔을 다시 돌려라"
    if not (문서.get("마켓그룹") or []):
        # 시각도 같이 버린다 — 못 믿는 산출물의 시각을 "마지막 스캔" 으로 띄우면
        # 화면이 "방금 훑었는데 이 모양이다" 로 읽힌다.
        return None, None, ("조인 산출물에 마켓그룹이 없다 — 조인 스캔을 다시 돌려라 "
                            "(0개는 관측이 아니라 조회 실패다)")
    return 문서, 시각, None


def _인덱스표시(rows, join_doc) -> dict:
    """미해소 행에 **화면용 사유 이름**을 붙이고 인덱스 불완전 규모를 센다.

    03-05 가 넘긴 숙제다. `join.미스` 행을 그 그룹의 `group_health(...)["완결"]` 로
    한 번 더 갈라, 아직 다 안 훑은 그룹의 행은 "인덱스 불완전"(시스템 사정)으로
    띄운다. 광고 청소 버킷으로 옮기는 게 **아니다** — 버킷은 `join.py` 가 정한 그대로고,
    여기서 바뀌는 것은 사람이 읽는 글자뿐이다.

    인덱스를 못 읽으면 `완결` 을 거짓으로 본다(fail-closed). "모른다" 를 "다 훑었다" 로
    접으면 화면이 없는 확신을 만든다.
    """
    그룹색인 = (join.group_index((join_doc or {}).get("마켓그룹"))
               if isinstance(join_doc, dict) else {})

    # `미스` 행이 가리키는 그룹만 건강을 묻는다 — 전 그룹을 묻는 질의로 키우지 않는다.
    번호별그룹: dict = {}
    for r in rows:
        if r.get("사유코드") != join.미스:
            continue
        gid = (그룹색인.get(r.get("번호")) or {}).get("groupId")
        if gid:
            번호별그룹[r.get("번호")] = str(gid)

    try:
        건강 = bulsaja_index.group_health(sorted(set(번호별그룹.values()))) if 번호별그룹 else {}
    except Exception:
        건강 = {}

    집계 = {"불완전": 0, "그룹": 0, "미보유": 0, "불일치": 0, "그룹에없음": 0,
           "팬아웃미조회": 0}
    불완전그룹 = set()

    for r in rows:
        # 팬아웃 미조회는 **해소된 행에도 붙는다** (CR-02). 번호도 상품도 찾았는데
        # 사본·기작업 태그만 못 물어본 상태다. 아래 미해소 분기에 들어가지 않으므로
        # 여기서 따로 센다 — 안 세면 화면에 그 행이 한 숫자도 안 남고, 사람이
        # "왜 이 행은 기본 선택에서 빠졌지" 를 코드에서 찾아야 한다.
        # **시스템 쪽 숫자다.** 광고 청소 배너에 섞지 않는다 (Pitfall 3).
        if r.get("팬아웃미조회"):
            집계["팬아웃미조회"] += 1

        코드 = r.get("사유코드")
        if r.get("해소") or not 코드:
            r["표시사유"] = None
            continue
        if 코드 == join.미스:
            gid = 번호별그룹.get(r.get("번호"))
            완결 = bool((건강.get(gid) or {}).get("완결")) if gid else False
            if not 완결:
                r["표시사유"] = _인덱스불완전
                # **사유 문장도 같이 고친다.** 원래 문장("그 안에 이 상품이 없다")은
                # 이 행에 대해 **사실이 아니다** — 아직 다 안 훑었을 뿐이다.
                # 툴팁에 그대로 두면 라벨만 바꾸고 오독은 그대로 남는다.
                r["사유"] = (
                    f"이 마켓그룹을 아직 다 안 훑었다 — 인덱스가 불완전하다(시스템 사정). "
                    f"번호 '{r.get('번호')}'. **광고 쪽은 멀쩡하다.** "
                    f"인덱스 구축을 끝내고 조인 스캔을 다시 돌리면 판정이 바뀐다")
                집계["불완전"] += 1
                if gid:
                    불완전그룹.add(gid)
                continue
            집계["그룹에없음"] += 1
        elif 코드 == join.미조회:
            집계["미보유"] += 1
        elif 코드 == join.불일치:
            집계["불일치"] += 1
        r["표시사유"] = _사유이름.get(코드, 코드)

    집계["그룹"] = len(불완전그룹)
    return 집계


@router.get("/")
def home(request: Request, t: str | None = None, run_dir: str | None = None):
    """`?t=` 로 들어오면 쿠키를 심고 **깨끗한 `/`** 로 털어낸다.

    토큰을 쿼리스트링에 남기면 주소창·브라우저 히스토리·스크린샷에 영구히 남는다
    (T-1-16). 303 으로 즉시 털어내면 사용자가 보는 URL 에는 토큰이 없다.
    비교는 `security.토큰이같나` — **`secrets.compare_digest` 를 직접 쓰지 않는다.**
    그 함수는 str 두 개를 받으면 ASCII 인코딩을 시도해서, 비ASCII 가 한 글자라도
    있으면 `TypeError` 를 던진다. 토큰을 **처음 받는 자리**가 바로 여기인데 여기만
    직접 쓰고 있었다 — 실측으로 `?t=<한글>` 이 403 이 아니라 **500** 이었다.
    주소창에 한글이 섞여 붙여넣어지기만 해도 난다. 403 이어야 할 자리에 500 이 나오면
    ① 거부 경로가 에러 핸들러로 새고 ② 로그가 트레이스백으로 더럽혀진다
    (`security.토큰이같나` 의 docstring 이 말하는 그대로다).
    """
    if t and security.토큰이같나(t, security.BOOT_TOKEN):
        r = RedirectResponse("/", status_code=303)
        # httponly: JS 가 못 읽는다(XSS 가 나도 쿠키는 안 샌다)
        # samesite=strict: 다른 사이트에서 넘어온 요청에는 아예 안 붙는다
        r.set_cookie(security.COOKIE_NAME, security.BOOT_TOKEN,
                     httponly=True, samesite="strict", path="/")
        return r

    if not security.page_cookie_ok(request):
        return PlainTextResponse(
            "토큰이 필요하다 — 서버 기동 로그의 URL 로 들어와라", status_code=403)

    # 회차 목록에 **그 회차에 들어 있는 계정**을 같이 싣는다 (OQ-7).
    # 신선도만 보고 고르면, 계정 절반이 측정조차 안 된 판정 위에서 입찰가를
    # 올리게 된다 — 화면은 "할 게 별로 없다" 로 읽히는데 그게 진짜 위험이다.
    회차들 = paths.scan_runs()

    # 회차 선택. 쿼리로 온 이름은 `paths.run_dir_path` 화이트리스트를 통과해야 한다 —
    # 사용자 입력으로 경로를 조합하지 않는다(위협 T-1-11 / ASVS V12).
    # `..` 를 거르는 블랙리스트가 아니라, 실제로 존재하는 회차 목록에 든 이름만 통과한다.
    선택 = run_dir or (회차들[0]["name"] if 회차들 else None)
    if run_dir is not None:
        try:
            paths.run_dir_path(run_dir)
        except ValueError as e:
            return PlainTextResponse(f"{e}", status_code=400)

    from webapp.main import templates  # 지연 import — main 이 이 모듈을 먼저 부른다

    # 한글·중국어 상품명을 `\uXXXX` 로 부풀리지 않는다. JSON.parse 는 어느 쪽이든
    # 똑같이 읽지만, 화면이 고장났을 때 **소스 보기로 상품명을 눈으로 확인**할 수
    # 있어야 원인을 찾는다. gzip 후 차이는 실측 6KB(117 → 111KB)라 사실상 공짜다.
    templates.env.policies["json.dumps_kwargs"] = {"ensure_ascii": False}

    ctx = {
        "token": security.BOOT_TOKEN,
        # 도는 작업. **탭을 닫았다 다시 열었을 때 패널이 살아나는 지점이다** (SC-03).
        # 이게 없으면 새로고침한 순간 진행 로그가 사라지고, 사용자는 작업이
        # 죽은 줄 안다 — 실제로는 자식이 세션 분리되어 잘 돌고 있는데.
        # 읽기만 한다: 레지스트리가 없으면 만들지 않고 None 이다.
        "job": jobs.active_job(),
        # 지금 붙어 있는 불사자 계정. **회차가 하나도 없어도 뜬다** — 계정 확인은
        # 회차와 무관하고, 회차가 없는 상태에서 제일 먼저 눌러야 할 버튼이다.
        "bulsaja": _불사자표시(),
        "runs": 회차들,
        "run_dir": 선택,
        "freshness": None,
        "accounts": [],
        "rules": [],
        "rows": [],
        "load_error": None,
        # ── 조인 (Phase 3) ──────────────────────────────────────────────
        # `load_error` 와 **다른 키**다. 두 실패는 사용자가 할 일이 다르다 —
        # 판정 결과를 못 읽으면 회차를 다시 뽑고, 조인 산출물을 못 읽으면
        # 조인 스캔을 다시 돌린다. 한 칸에 담으면 어느 쪽인지 알 수 없다.
        "index_error": None,
        "join_at": None,
        "resolution": None,
        "index_health": None,
        "cleanup": [],
        # 필터 옵션 값은 **서버가 아는 판정 문자열**이어야 한다. 템플릿에 박으면
        # `state.py` 의 판정값을 고쳤을 때 필터가 조용히 아무것도 안 거른다.
        "filters": {
            "states": [state.AI가공완료, state.단순번역만, state.중국어원본],
            "buckets": [join.광고청소, join.시스템],
        },
    }

    if 선택 is None:
        # 회차가 하나도 없다. **빈 표를 띄우지 않는다** — 빈 표는 "대상이 없다" 로
        # 읽히는데 실제로는 "아직 아무것도 안 돌렸다" 다. 할 일을 알려준다.
        return templates.TemplateResponse(request, "board.html", ctx)

    ctx["freshness"] = paths.freshness(선택)
    result, err = _load_result(선택)
    ctx["load_error"] = err
    # 템플릿에 넘기는 것은 화면에 필요한 **값**뿐이다. 계정 객체를 통째로 넘기지 않는다
    # (SAFE-03 화이트리스트 투영). 웹앱은 계정 자격증명 파일을 아예 열지 않는다.
    ctx["accounts"] = board.account_list(result)
    ctx["rules"] = board.rule_list(result)

    # 조인 산출물을 얹는다. `board.fold_products` 는 **고치지 않는다** — 그 모듈이
    # "네트워크도 크레딧도 0" 인 계약을 지키게 두고, 조인은 그 위에 얹는 층이다.
    # 산출물이 없어도(`None`) 보드는 그대로 뜬다: 전 행이 `미조회`/`시스템` 이 되고
    # 배너가 "아직 조인 스캔을 안 돌렸다" 를 말한다.
    join_doc, ctx["join_at"], ctx["index_error"] = _load_join(선택)
    ctx["rows"] = join.attach(
        board.fold_products(result), result, join_doc,
        excluded=settings.cfg("index_excluded_groups",
                              settings.DEFAULTS["index_excluded_groups"]),
        done_tags=settings.cfg("done_tags", settings.DEFAULTS["done_tags"]))
    ctx["index_health"] = _인덱스표시(ctx["rows"], join_doc)
    ctx["resolution"] = join.resolution(ctx["rows"])
    ctx["cleanup"] = join.cleanup_groups(ctx["rows"])

    return templates.TemplateResponse(request, "board.html", ctx)

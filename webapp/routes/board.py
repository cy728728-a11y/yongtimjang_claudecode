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

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from webapp import board, bulsaja_index, jobs, paths, security, settings

router = APIRouter()


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
    ctx["rows"] = board.fold_products(result)

    return templates.TemplateResponse(request, "board.html", ctx)

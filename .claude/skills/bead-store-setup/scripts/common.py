# 비즈 300 마켓 세팅 공통 도구: 불사자 호출(429 재시도), 원본 300개 이름, 마켓그룹 찾기, 커머스API, 등록한도 시트
import sys, os, re, json, time, subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
sys.path.insert(0, os.path.join(ROOT, ".claude/lib"))
sys.path.insert(0, os.path.join(ROOT, ".claude/skills/attr-tag/scripts"))
sys.path.insert(0, os.path.join(ROOT, ".claude/skills/sold-lock/scripts"))
from eroomlib.bulsaja import BulsajaMCP, extract_tool_payload  # noqa: E402

SOURCE_GROUP = 1007658          # 용팀장_테스트 (원본 300개)
SHEET_ID = "11iBT65roK2JEE732TzgnEnZEZkWeaHKsJ5rnivowlh4"
KEEP_FREE = 350                 # 업로드 전 남겨 둘 빈자리
MAX_DELETE = 500                # 한 마켓에서 한 번에 지울 수 있는 최대 개수(넘으면 사람 확인)
DATA_DIR = os.path.join(ROOT, ".claude/skills/bead-store-setup/data")
os.makedirs(DATA_DIR, exist_ok=True)

norm = lambda s: re.sub(r"[^0-9A-Za-z가-힣]", "", s or "")


def call(m, name, args):
    """불사자 도구 호출. 429(요청 과다)면 기다렸다가 다시."""
    for t in range(6):
        try:
            return extract_tool_payload(m.call_tool(name, args))
        except Exception as e:
            if "429" in repr(e):
                time.sleep(20 * (t + 1)); continue
            raise
    raise RuntimeError("429 계속")


def pages(m, tool, args):
    out, p = [], 1
    while True:
        r = call(m, tool, dict(args, page=p, pageSize=50))
        out += r.get("항목") or []
        if not r.get("더있음"):
            return out
        p += 1


def bulsaja():
    for t in range(6):   # 접속 자체도 429 가 나면 기다렸다 다시
        try:
            m = BulsajaMCP(sleep=0.6); m.open(); break
        except Exception as e:
            if "429" not in repr(e) or t == 5: raise
            time.sleep(30 * (t + 1))
    prof = call(m, "bulsaja_my_profile", {})
    if "부킹" not in json.dumps(prof, ensure_ascii=False):
        raise RuntimeError("불사자 계정이 부킹(용쌤)이 아님 — 계정 전환 후 다시")
    return m


def originals(m):
    src = pages(m, "bulsaja_market_group_products", {"groupId": SOURCE_GROUP})
    names = {norm(i["상품명"]) for i in src}
    if len(src) != 300 or len(names) != 300:
        raise RuntimeError(f"원본 그룹 상품 {len(src)}개·고유이름 {len(names)}개 — 300이 아님")
    return src, names


def find_group(m, market):
    gs = [g for g in call(m, "bulsaja_market_groups", {})["그룹"] if re.search(rf"용쌤{re.escape(market)}$", g["그룹명"])]
    if len(gs) != 1:
        raise RuntimeError(f"용쌤{market} 그룹을 하나로 못 찾음: {[g['그룹명'] for g in gs]}")
    return gs[0]


def group_beads(m, gid, names):
    """그룹 안의 비즈 복사본(원본 이름과 같은 것)"""
    items = pages(m, "bulsaja_product_list", {"marketGroupId": gid, "keyword": "비즈"})
    seen, out = set(), []
    for i in items:
        if norm(i["상품명"]) in names and i["productId"] not in seen:
            seen.add(i["productId"]); out.append(i)
    return out


def commerce(market):
    import attr_tag as T
    api = T._default_api([]); api.load([market])
    return api


def store_count(api, market):
    return api._request(market, "POST", "/v1/products/search", json={"page": 1, "size": 1}).get("totalElements")


def store_products(api, market):
    out, p = [], 1
    while True:
        d = api._request(market, "POST", "/v1/products/search", json={"page": p, "size": 100})
        out += d.get("contents") or []
        if p >= (d.get("totalPages") or 1):
            return out
        p += 1


def sheet_limit(market):
    r = subprocess.run(["gws", "sheets", "spreadsheets", "values", "get", "--params",
                        json.dumps({"spreadsheetId": SHEET_ID, "range": "작업계획!A1:D80"})],
                       capture_output=True, text=True, timeout=60)
    txt = r.stdout[r.stdout.find("{"):]
    for row in json.loads(txt).get("values", []):
        if len(row) >= 4 and row[1].strip() == market:
            return int(row[3].replace(",", ""))
    raise RuntimeError(f"시트 작업계획 탭에 {market} 한도가 없음")

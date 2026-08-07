#!/usr/bin/env python3
"""공용 상품 스냅샷 — 같은 상품을 여러 스킬이 각자 다시 조회하지 않게 하는 캐시 1벌.

**왜**: 지금 카테고리교정과 상품명 두 스킬이 같은 마켓그룹에 대해 `workdata` 를
각각 1번씩(= 상품당 2번) 부른다. 스킬을 8개까지 늘리면 그대로 6~8배가 된다.
썸네일 다운로드도 같은 URL 을 스킬마다 다시 받는다.

**저장 키는 상품id** (2026-07-27 이룸님 결정). groupId 가 아니다 —
카테고리교정 prep 은 시트 G빈행에서 대상을 뽑기 때문에 groupId 를 아예 모른다.
상품id 로 잡으면 두 스킬이 진입점이 달라도 같은 캐시를 쓴다.

    <snapshot_root>/products/<상품id>.json     상품 1건 = 파일 1개
    <snapshot_root>/thumbs/<url해시><확장자>    이미지 1장 = 파일 1개(URL 기준)

**갱신 규칙** — 저장 액션이 자기가 바꾼 필드만 `update()` 로 되쓴다. 재조회 없음.
그래서 "이 스냅샷이 낡았나?"를 판정할 일이 없다(TTL·해시비교 불필요).
| 액션 | 갱신 필드 |
|---|---|
| 카테고리 저장 | 기존카테고리 |
| rename | 상품명 |
| 썸네일 교체 | 썸네일 |
원문명·옵션명원문·원본링크는 **불변** — 절대 재조회하지 않는다. 강제는 `refresh=True`.

**파일 1개 = 상품 1개**인 이유: 저장 액션이 건건 즉시 쓰는데, 그룹 단위 jsonl 이면
1000줄 파일을 매번 통째로 재작성해야 하고 두 스킬이 동시에 돌면 서로 덮어쓴다.

**마켓그룹 목록은 캐시하지 않는다.** 신규 상품이 수시로 들어오는데 목록을 캐시하면
새 상품이 조용히 누락된다. 비싼 건 상품당 1회인 `workdata`·썸네일이지 목록 페이징이 아니다.
"""
import hashlib
import json
import os
import re
import shutil
import time
import urllib.parse

from .bulsaja import BulsajaMCP as _BaseMCP
from .config import cfg

# ---------------------------------------------------------------------------
# workdata 도메인 헬퍼 — 스킬 2개 이상이 쓰므로 여기(공용)에 둔다.
# 원래 bulsaja-category-fix/scripts/bulsaja_mcp.py 에 있던 것을 그대로 옮겼다.
# ---------------------------------------------------------------------------

_OPT_MAX = 8      # 키워드 추출에 넘길 옵션명 최대 개수(이룸님 확정, 2026-07-24)
_OPT_IMG_MAX = 4  # 2바퀴(정체불명) 확인용 옵션 이미지 최대 장수
_OPT_PREFIX = re.compile(r"^\s*[A-Za-z가-힣]?\s*[.)]\s*")


def sku_evidence(skus):
    """uploadSkus[] → (옵션명 한국어, 옵션명 원문, 옵션 이미지URL) 각각 중복제거·상한.

    옵션은 '실제 판매 단위'라 상품명이 왜곡돼도 정체가 드러난다
    (예 상품명 '자키 받침대' / 옵션 '3톤 세단 모델잭에어펌프' → 실제는 자키+에어펌프 세트).
    전건 22개씩 넘기면 토큰이 커지므로 중복 제거 후 앞 8개만 쓴다.
    exclude=True(판매 제외) 옵션은 실물이 아니므로 건너뛴다.
    """
    if not isinstance(skus, list):
        return [], [], []
    ko, cn, img = [], [], []
    for s in skus:
        if not isinstance(s, dict) or s.get("exclude"):
            continue
        t = _OPT_PREFIX.sub("", str(s.get("text") or "")).strip()
        if t and t not in ko and len(ko) < _OPT_MAX:
            ko.append(t)
        c = str(s.get("_text") or "").strip()
        if c and c not in cn and len(cn) < _OPT_MAX:
            cn.append(c)
        u = str(s.get("urlRef") or "").strip()
        if u and u not in img and len(img) < _OPT_IMG_MAX:
            img.append(u)
    return ko, cn, img


def option_model(data):
    """workdata 원본 → 옵션 **두 뷰**를 한 dict 로. 상한 없이 전부 담는다.

    불사자 옵션은 두 곳에 나뉘어 있고 둘은 **독립적으로** 갱신될 수 있다:
      · `uploadSkus[]`        판매행 — 조합 1줄 = 실제 판매 단위(가격·재고·포함·대표)
      · `uploadSkuProps`      옵션값행 — 차원별 선택지. 이름을 바꾸는 대상은 **이쪽**이다
        - `mainOption` = 0번 차원(dict) · `subOption` = 1번 이후 차원(list, 1차원 상품은 빈 list)

    **`vid고유`가 왜 필요한가**: 복합(다차원) 옵션 상품은 `vid` 가 차원마다 1부터 다시
    시작한다(예: 포장방식 vid=1, 적용차량 vid=1). 그런 상품에 vid 로 이름을 바꾸면
    엉뚱한 차원이 바뀐다 — 그때는 `groupIndex`/`valueIndex` 로 지정해야 한다.
    판매행 `id` 도 1차원이면 vid 와 같지만 복합이면 `"1:1:1:4"` 같은 조합 키다.
    """
    props = data.get("uploadSkuProps") or {}
    dims = []
    main = props.get("mainOption")
    subs = props.get("subOption") or []
    if not isinstance(subs, list):
        subs = [subs]
    for raw in ([main] if isinstance(main, dict) else []) + [s for s in subs if isinstance(s, dict)]:
        dims.append({
            "이름": raw.get("prop_name") or "",
            "원문이름": raw.get("_prop_name") or "",
            "values": [{
                "vid": v.get("vid"),
                "name": v.get("name") or "",
                "_name": v.get("_name") or "",
                "imageUrl": v.get("imageUrl") or "",
                "exclude": bool(v.get("exclude")),
            } for v in (raw.get("values") or []) if isinstance(v, dict)],
        })

    rows = []
    for s in (data.get("uploadSkus") or []):
        if not isinstance(s, dict):
            continue
        rows.append({
            "id": str(s.get("id") or ""),
            "text": s.get("text") or "",
            "_text": s.get("_text") or "",
            "sale_price": s.get("sale_price"),
            "origin_price": s.get("origin_price"),
            "stock": s.get("stock"),
            "exclude": bool(s.get("exclude")),
            "main_product": bool(s.get("main_product")),
            "urlRef": s.get("urlRef") or "",
        })

    seen, unique = set(), True
    for d in dims:
        for v in d["values"]:
            key = str(v["vid"])
            if key in seen:
                unique = False
            seen.add(key)
    return {"차원": dims, "판매행": rows, "vid고유": unique and bool(seen)}


class ProductMCP(_BaseMCP):
    """transport(eroomlib.bulsaja) + 상품 공통 조회. 스킬 고유 도구는 이걸 상속해 얹는다."""

    def workdata(self, product_id, mode="full"):
        """상품의 현재 카테고리 + **정체 판별 증거 4종**을 뽑아 반환(경량).

        증거 4종 (2026-07-24 개편). 한국어 상품명·썸네일은 불사자 가공 '후' 산출물이라
        같이 틀릴 수 있다 → 가공 '전' 원본(중국어 원문명·옵션명)을 독립 증거로 함께 넘긴다.
          ① 한국어 상품명  data.productName / uploadSmartStoreProductName  (용의자)
          ② 중국어 원문명  data.originalProductName                        (타오바오 원 리스팅)
          ③ 옵션명         data.uploadSkus[].text / ._text                 (실제 판매 단위)
          ④ 썸네일         data.uploadThumbnails[]                         (최대 6장)
        옵션 이미지(uploadSkus[].urlRef)는 2바퀴(정체불명 큐) 확인용으로만 보관.
        """
        raw = self.call_tool("bulsaja_product_workdata",
                             {"productId": product_id, "mode": mode})
        data = raw.get("data", raw) if isinstance(raw, dict) else {}
        cat = (data.get("uploadCategory") or {}).get("ss_category") or {}
        ss_name = cat.get("name") or ""
        thumbs = data.get("uploadThumbnails") or []
        if not isinstance(thumbs, list):
            thumbs = []
        name = (data.get("productName")
                or data.get("uploadSmartStoreProductName") or "")
        opt_ko, opt_cn, opt_img = sku_evidence(data.get("uploadSkus"))
        # 상세페이지(Step6) — AI 생성 여부는 기작업 스킵 필터, HTML 은 복구용 백업.
        # 원본 상세(타오바오)도 HTML 에 담는다: 생성이 잘못됐을 때 되돌릴 대상이라
        # "AI 생성분"만 백업하면 최초 생성 건은 복구 경로가 없어진다.
        det = data.get("uploadDetailContents") or {}
        if not isinstance(det, dict):
            det = {}
        return {
            "productId": product_id,
            "상품명": name,
            "원문명": data.get("originalProductName") or "",
            "옵션명": opt_ko,
            "옵션명원문": opt_cn,
            "옵션이미지": opt_img,
            "기존카테고리": ss_name if ss_name else "미설정",
            "썸네일": thumbs[:6],
            "원본링크": data.get("product_url") or "",
            # 옵션 전체(가격·재고·포함여부·차원) — 옵션정리 스킬이 쓴다. 상한 없이 전부.
            # 위 `옵션명`(앞 8개 요약)은 정체판별용이라 성격이 다르다.
            "옵션": option_model(data),
            # 이중 키 (2026-07-28 대량다듬기): 복사본은 불사자코드를, 재수집분은
            # 타오바오 상품번호를 공유한다. 목록 조회에는 둘 다 없어 여기서만 얻는다.
            "불사자코드": str(data.get("uploadBulsajaCode") or ""),
            "타오바오상품번호": str(data.get("productNo") or ""),
            "상세": {
                "AI생성": bool(det.get("aiImageGenerated")),
                "장수": int(det.get("aiImageOutputCount") or 0),
                "생성일": str(det.get("aiImageGeneratedAt") or ""),
                "HTML": str(det.get("renderContent") or ""),
            },
        }

    def poll_ai_task(self, task_id, target="detail", interval=10, timeout=900,
                     sleep_fn=time.sleep):
        """AI 생성 작업(상세·썸네일 공용)이 끝날 때까지 폴링.

        같은 도구를 `target` 만 바꿔 쓴다. 반환 (생성이미지[], 사용크레딧).
        `sleep_fn` 은 테스트가 대기를 없애려고 주입한다.
        타임아웃 기본 15분 — 공식 안내가 "몇 분"이라 넉넉히 잡았다.
        """
        waited = 0
        while waited <= timeout:
            st = self.call_tool("bulsaja_detail_page_status",
                                {"taskId": task_id, "target": target})
            if st.get("failures") or st.get("실패내역"):
                raise RuntimeError(
                    f"생성 실패: {st.get('실패내역') or st.get('failures')}")
            if st.get("완료여부") or st.get("완료") or st.get("completed"):
                return (st.get("생성이미지") or st.get("imageUrls") or [],
                        st.get("사용크레딧") or st.get("consumedCredits") or 0)
            sleep_fn(interval)
            waited += interval
        raise TimeoutError(f"타임아웃({timeout}s): taskId={task_id}")

    def collect_group(self, group_id, page_size=50, sleep=0.3, log=None):
        """마켓그룹 전체 상품(productId+상품명+상태코드)을 페이지네이션으로 수집."""
        out, seen, page = [], set(), 1
        while True:
            r = self.call_tool("bulsaja_market_group_products",
                               {"groupId": group_id, "page": page,
                                "pageSize": page_size})
            items = r.get("항목") or []
            if not items:
                break
            for it in items:
                pid = it.get("productId")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                out.append({"productId": pid,
                            "상품명": it.get("상품명", ""),
                            "상태코드": it.get("상태코드"),
                            "잠금": it.get("잠금")})
            if log:
                log(f"  page {page}: +{len(items)} (누적 {len(out)}/{r.get('총상품수')})")
            if not r.get("더있음"):
                break
            page += 1
            time.sleep(sleep)
        return out


# ---------------------------------------------------------------------------
# 저장소
# ---------------------------------------------------------------------------

# 스냅샷 레코드에서 workdata 원본에 해당하는 필드(= 소비 스킬이 쓰는 것).
# 그 밖의 `_`로 시작하는 키는 스냅샷 자체의 메타(수집시각 등)다.
#
# `가결정카테고리` 는 workdata 원본에는 없다 — 세로 러너(onestep)가 심는 필드다.
# `불사자코드`·`타오바오상품번호` 는 대량다듬기(2026-07-28)의 이중 키 — 정본 그룹핑(dedup.py)이 쓴다.
# **맨 뒤에** 두고 `as_workdata` 가 `if k in rec` 로 거르므로, 이 필드가 없는 기존
# 레코드의 산출물은 키 순서까지 그대로다(회귀 기준 'byte 동일' 유지).
#
# **`옵션`·`상세` 는 일부러 뺐다.** 이 투영의 유일한 소비자는 카테고리교정의
# products.json 인데, 옵션 전량과 상세 HTML(타오바오 원본 마크업 포함)까지 실으면
# 그 스킬이 쓰지도 않는 데이터로 파일이 수십 MB가 된다(1,000건 기준). 두 필드는
# 레코드에는 그대로 있고, 쓰는 스킬이 `load()`/`ensure()` 로 직접 읽는다.
WD_FIELDS = ("productId", "상품명", "원문명", "옵션명", "옵션명원문",
             "옵션이미지", "기존카테고리", "썸네일", "원본링크",
             "가결정카테고리", "불사자코드", "타오바오상품번호")

# 가결정 = "사람이 아직 승인하지 않아 불사자에는 저장하지 않았지만, 이번 세로 진행에서
# 다음 단계가 근거로 삼아야 할 카테고리". 상품명 단계가 카테고리를 필수 선행으로 요구하는데
# (카테고리가 틀리면 키워드를 못 고른다), 게이트를 상품 단위로 두면 그 시점에 불사자에는
# 아직 옛 카테고리가 들어 있다. 그 간극을 메우는 필드.
PROVISIONAL = "가결정카테고리"


def root():
    return cfg("paths.snapshot_root", required=True)


def _products_dir():
    d = os.path.join(root(), "products")
    os.makedirs(d, exist_ok=True)
    return d


def _thumbs_dir():
    d = os.path.join(root(), "thumbs")
    os.makedirs(d, exist_ok=True)
    return d


def product_path(pid):
    return os.path.join(_products_dir(), f"{pid}.json")


def _write_atomic(path, text):
    """같은 상품을 두 프로세스가 동시에 갱신해도 반쪽 파일이 남지 않게."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def load(pid):
    """스냅샷 1건. 없으면 None."""
    path = product_path(pid)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None  # 깨진 캐시는 없는 것으로 보고 다시 받는다


def save(rec):
    """스냅샷 1건 전체 저장(내부용). 보통은 ensure()/update() 를 쓴다."""
    rec = dict(rec)
    rec["_수집일"] = rec.get("_수집일") or time.strftime("%Y-%m-%d %H:%M:%S")
    _write_atomic(product_path(rec["productId"]),
                  json.dumps(rec, ensure_ascii=False, indent=2))
    return rec


def update(pid, **fields):
    """저장 액션이 **자기가 바꾼 필드만** 되쓴다(예: 카테고리 저장 → 기존카테고리).

    스냅샷이 없으면 아무것도 하지 않는다(다음 조회 때 어차피 새로 받는다).
    """
    rec = load(pid)
    if rec is None:
        return None
    rec.update(fields)
    rec["_갱신일"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_atomic(product_path(pid), json.dumps(rec, ensure_ascii=False, indent=2))
    return rec


def set_provisional(pid, path):
    """카테고리 '가결정'을 심는다 — 승인 전이라 불사자에는 아직 저장하지 않은 값.

    다음 단계(상품명)가 `effective_category` 로 이걸 먼저 본다. 승인 후 실제 저장이
    끝나면 `commit_provisional` 이 `기존카테고리` 로 승격시키고 이 필드를 지운다.
    """
    if not (path or "").strip():
        return None
    return update(pid, **{PROVISIONAL: path.strip()})


def clear_provisional(pid):
    """가결정을 버린다(보류·거부·롤백). 없으면 아무것도 하지 않는다."""
    rec = load(pid)
    if rec is None or PROVISIONAL not in rec:
        return rec
    rec.pop(PROVISIONAL, None)
    rec["_갱신일"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_atomic(product_path(pid), json.dumps(rec, ensure_ascii=False, indent=2))
    return rec


def commit_provisional(pid):
    """승인·저장 완료 → 가결정을 `기존카테고리` 로 승격하고 가결정 필드를 지운다.

    카테고리 저장 스킬이 이미 `update(pid, 기존카테고리=...)` 를 했더라도 안전하다
    (같은 값을 한 번 더 쓰고 가결정만 치운다).
    """
    rec = load(pid)
    if rec is None:
        return None
    prov = (rec.get(PROVISIONAL) or "").strip()
    if prov:
        rec["기존카테고리"] = prov
    rec.pop(PROVISIONAL, None)
    rec["_갱신일"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_atomic(product_path(pid), json.dumps(rec, ensure_ascii=False, indent=2))
    return rec


def effective_category(rec):
    """다음 단계가 근거로 삼아야 할 카테고리 = 가결정이 있으면 그것, 없으면 저장된 값.

    소비 쪽(product-name 등)은 이 함수 또는 같은 우선순위를 쓴다.
    """
    rec = rec or {}
    return ((rec.get(PROVISIONAL) or "").strip()
            or (rec.get("기존카테고리") or "").strip())


def ensure(pids, mcp=None, refresh=False, sleep=0.3, mode="full", log=print,
           require=()):
    """상품id 목록 → {pid: 레코드}, {pid: 에러문자열}.

    캐시에 없는 것만 `workdata` 를 부른다. 전부 적중하면 MCP 연결조차 열지 않는다.
    실패는 캐시하지 않는다 — 다음 실행에서 다시 시도해야 하므로.

    `require` = 이 필드가 없는 캐시는 낡은 것으로 보고 다시 받는다.
    스킬이 늘면서 레코드에 필드가 추가되는데(예: 옵션정리가 `옵션` 을 요구),
    그 전에 받아둔 캐시에는 그 필드가 없다. 필드를 **요구하는 쪽이** 명시한다 —
    스냅샷에 스키마 버전을 두고 전건을 무효화하면 멀쩡한 캐시까지 버리게 된다.
    """
    pids = list(dict.fromkeys(pids))  # 순서 유지 + 중복 제거
    recs, errors = {}, {}
    todo = []
    stale = 0
    for pid in pids:
        rec = None if refresh else load(pid)
        if rec and any(k not in rec for k in require):
            rec, stale = None, stale + 1
        if rec:
            recs[pid] = rec
        else:
            todo.append(pid)
    if stale and log:
        log(f"  (필드 부족으로 재조회: {stale}건 — {', '.join(require)})")

    if log:
        log(f"  스냅샷 적중 {len(recs)}/{len(pids)}건 · 신규조회 {len(todo)}건")
    if not todo:
        return recs, errors

    own = mcp is None
    if own:
        mcp = ProductMCP()
        mcp.open()
    try:
        for i, pid in enumerate(todo, 1):
            try:
                recs[pid] = save(mcp.workdata(pid, mode=mode))
            except Exception as e:
                errors[pid] = f"{type(e).__name__}: {e}"[:200]
            if log and i % 20 == 0:
                log(f"  ...{i}/{len(todo)}")
            time.sleep(sleep)
    finally:
        if own:
            mcp.close()
    return recs, errors


def as_workdata(rec):
    """스냅샷 레코드 → workdata 응답과 **같은 키 순서**의 dict(메타 필드 제거).

    소비 스킬의 기존 산출물(products.json / workdata.json)을 그대로 재현하기 위한 투영.
    """
    return {k: rec[k] for k in WD_FIELDS if k in rec}


# ---------------------------------------------------------------------------
# 썸네일 캐시 — 키는 URL. 같은 URL 을 스킬마다 다시 받지 않는다.
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.taobao.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

EXT_BY_CT = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
    "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif",
}


def ext_from(url, content_type):
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in EXT_BY_CT:
        return EXT_BY_CT[ct]
    path = urllib.parse.urlparse(url).path
    _, dot, ext = path.rpartition(".")
    if dot and 1 <= len(ext) <= 5:
        return "." + ext.lower()
    return ".jpg"


def _cache_stem(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def cached_image(url):
    """캐시에 있으면 그 경로, 없으면 None.

    확장자는 응답 Content-Type 에 따라 달라지므로 후보 몇 개를 stat 으로 찔러본다
    (디렉터리 나열은 파일이 수천 장이 되면 조회마다 전체 스캔이라 쓰지 않는다).
    """
    stem = os.path.join(_thumbs_dir(), _cache_stem(url))
    cands = [ext_from(url, None)] + list(dict.fromkeys(EXT_BY_CT.values()))
    for ext in dict.fromkeys(cands):
        if os.path.exists(stem + ext):
            return stem + ext
    return None


def fetch_image(url, refresh=False):
    """URL → 캐시 파일 경로. 이미 받아둔 URL 이면 네트워크를 타지 않는다.

    alicdn / bulsaja S3 등이 헤더 없는 요청을 403 하므로 브라우저 UA/Referer 를 붙인다.
    반환: (경로, None) 또는 (None, 사유)
    """
    if not url:
        return None, "빈 URL"
    if not refresh:
        hit = cached_image(url)
        if hit:
            return hit, None
    try:
        import requests
    except ImportError:
        return None, "requests 없음(.venv)"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200 or not r.content:
            return None, f"HTTP {r.status_code}"
        ext = ext_from(url, r.headers.get("Content-Type"))
        path = os.path.join(_thumbs_dir(), _cache_stem(url) + ext)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            f.write(r.content)
        os.replace(tmp, path)
        return path, None
    except Exception as e:
        return None, str(e)


def shrink_image(path, max_px):
    """이미지를 긴 변 `max_px` 로 축소한다(0 이하·None 이면 건너뜀). 제자리 저장.

    **왜 있나**: 비전 토큰은 픽셀수에 비례한다(대략 W*H/750). 불사자 썸네일은 800~1024px
    가 많아 1장에 850~1,400토큰인데, 워커 컨텍스트에 한 번 들어가면 그 뒤 모든 턴에서
    다시 읽히므로 실질 비용이 수만 토큰이 된다(실측: 워커 비용의 97%가 캐시읽기).
    512px 로 줄이면 ~350토큰이다.

    **어디까지 줄여도 되는지는 용도마다 다르다.** 실물 정체 판별에는 512 로 충분하지만
    이미지에 인쇄된 글자를 읽어야 하는 판정(스펙 표기 3000W↔8500W · 색상코드 `#FEFA50` ·
    비제품 이미지의 중국어 안내문)은 더 큰 값이 필요하다. 그래서 값을 여기서 고정하지
    않고 호출부가 정한다.

    **호출부는 항상 복사본을 넘긴다** — 스냅샷 캐시 원본을 줄이면 다른 스킬이 더 큰
    해상도를 원할 때 되돌릴 수 없다.
    """
    if not max_px or max_px <= 0:
        return False
    try:
        from PIL import Image  # Pillow 없으면 원본 유지
    except ImportError:
        return False
    try:
        with Image.open(path) as im:
            if max(im.size) <= max_px:
                return False
            im = im.convert("RGB")
            im.thumbnail((max_px, max_px), Image.LANCZOS)
            im.save(path, "JPEG", quality=85)
        return True
    except Exception:  # 한 장 실패가 prep 전체를 막지 않는다
        return False


def materialize_image(url, out_dir, name_hint, idx, refresh=False, max_px=None):
    """URL 을 캐시에서(없으면 받아서) `out_dir/<name_hint 24자>_<idx><확장자>` 로 복사.

    파일명 규칙은 기존 fetch_thumbs.py 와 **같다** — 소비 스킬의 산출물(names.json 의
    썸네일경로, 배치 뷰)이 바뀌지 않게 하려는 것. 스냅샷 원본은 절대 건드리지 않는다
    (줄이는 대상은 언제나 이 복사본이다 — `max_px` 참조).
    """
    src, err = fetch_image(url, refresh=refresh)
    if not src:
        return None, err
    safe = "".join(c for c in (name_hint or "thumb") if c.isalnum() or c in "-_")[:24] or "thumb"
    dst = os.path.join(out_dir, f"{safe}_{idx}{os.path.splitext(src)[1]}")
    os.makedirs(out_dir, exist_ok=True)
    shutil.copyfile(src, dst)
    shrink_image(dst, max_px)
    return os.path.abspath(dst), None

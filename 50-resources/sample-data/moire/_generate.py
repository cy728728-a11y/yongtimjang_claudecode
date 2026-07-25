# -*- coding: utf-8 -*-
"""
무아레(MOIRE) AX 데모용 더미데이터 생성기.
홈·리빙 라이프스타일 자사몰(카페24 기반) — 홈프래그런스·테이블웨어·패브릭·문구.
시즌 컬렉션 런칭 + 기획전 + 카페24/네이버 리뷰 긍부정.
브랜드/상품/수치 전부 데모용 가상. 채널 수수료율만 업계 공개자료 기반.

출력: sales.csv + product_master.csv + channel_master.csv + reviews.csv + promo.csv
경로: 이 스크립트가 놓인 폴더(머신 무관).
"""
import csv, os, random, datetime as dt

random.seed(20260704)
OUT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 1) 채널 마스터  (수수료율 차등 = 매출≠마진 미션의 핵심)
#    자사몰(카페24)·네이버는 낮고, 오늘의집·29CM은 높다.
#    수수료율: 자사몰 카페24 PG ~3% / 네이버 결제+주문 ~6% /
#              오늘의집 위탁 표준 ~22% / 29CM 편집샵 위탁 ~30% (2025 업계 공개자료)
# ---------------------------------------------------------------------------
CHANNELS = [
    # code, name, type, fee_rate, settle, note
    ("MW", "자사몰",        "자사몰(D2C)", 0.030, "D+3",      "moire.co.kr / 카페24 · PG 결제수수료만"),
    ("NV", "네이버 스마트스토어", "오픈마켓",  0.060, "D+2(빠른정산)", "네이버페이 결제+주문관리 수수료"),
    ("OH", "오늘의집",      "리빙 플랫폼",   0.220, "익월 15일",  "버킷플레이스 입점 / 카테고리 표준수수료 위탁"),
    ("29", "29CM",         "편집샵(위탁)",  0.300, "익월 말",   "라이프스타일 편집샵 위탁판매 / 수수료 개별협의"),
]
CH_BY_CODE = {c[0]: c for c in CHANNELS}

with open(f"{OUT}/channel_master.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["채널코드", "채널명", "유형", "수수료율", "정산주기", "비고"])
    for code, name, typ, fee, settle, note in CHANNELS:
        w.writerow([code, name, typ, f"{fee:.3f}", settle, note])

# ---------------------------------------------------------------------------
# 2) 상품 마스터
#   (sku, 카테고리, 상품명, 시즌, 유형, 정가, 자사몰판매가, 원가, 재고, 출시일)
#   유형: 신제품 / 스테디셀러 / 시즌한정 / 리뉴얼
#   원가율: 홈프래그런스 0.38~0.45 / 테이블웨어 0.40~0.48 / 패브릭 0.42~0.50 / 문구 0.30~0.38
# ---------------------------------------------------------------------------
PRODUCTS = [
    # --- 홈프래그런스 (FR) ---
    ("FR01", "홈프래그런스", "무아레 화이트무스크 캔들",     "사계절", "스테디셀러", 38000, 36000, 15000,  80, "2025-03-02"),
    ("FR02", "홈프래그런스", "무아레 우드세이지 캔들",       "사계절", "스테디셀러", 38000, 36000, 15000,  70, "2025-03-02"),  # 리뷰 최상(숨은 보석)
    ("FR03", "홈프래그런스", "무아레 시트러스 캔들",         "여름",   "시즌한정", 42000, 39000, 16000,  60, "2026-06-05"),
    ("FR04", "홈프래그런스", "무아레 화이트무스크 디퓨저",   "사계절", "스테디셀러", 48000, 45000, 19000,  55, "2025-03-02"),
    ("FR05", "홈프래그런스", "무아레 오션브리즈 디퓨저",     "여름",   "신제품",   52000, 48000, 21000,  90, "2026-06-12"),  # STAR: 스파이크 + 향약함 부정 클러스터
    ("FR06", "홈프래그런스", "무아레 리넨 룸스프레이",       "사계절", "스테디셀러", 26000, 24000,  9500, 120, "2025-05-10"),
    ("FR07", "홈프래그런스", "무아레 디퓨저 리필 200ml",     "사계절", "스테디셀러", 22000, 20000,  7500, 140, "2025-05-10"),
    ("FR08", "홈프래그런스", "무아레 미니 캔들 3종세트",     "사계절", "스테디셀러", 34000, 32000, 12500, 100, "2025-09-01"),
    # --- 테이블웨어 (TW) ---
    ("TW01", "테이블웨어",  "무아레 스톤 머그",             "사계절", "스테디셀러", 22000, 21000,  9000, 150, "2025-04-01"),
    ("TW02", "테이블웨어",  "무아레 웨이브 머그",           "여름",   "신제품",   24000, 23000,  9800, 130, "2026-06-12"),
    ("TW03", "테이블웨어",  "무아레 스톤 플레이트 2P",       "사계절", "스테디셀러", 32000, 30000, 13500,  90, "2025-04-01"),
    ("TW04", "테이블웨어",  "무아레 웨이브 플레이트 2P",     "여름",   "신제품",   34000, 32000, 14500,  80, "2026-06-12"),  # 배송 파손 부정 클러스터
    ("TW05", "테이블웨어",  "무아레 스톤 보울",             "사계절", "스테디셀러", 26000, 25000, 10800,  85, "2025-04-01"),
    ("TW06", "테이블웨어",  "무아레 글라스 컵 4P",          "여름",   "시즌한정", 39000, 37000, 15500,  70, "2026-06-05"),
    ("TW07", "테이블웨어",  "무아레 세라믹 티팟",           "사계절", "스테디셀러", 46000, 44000, 19000,  40, "2025-10-01"),
    # --- 패브릭 (FB) ---
    ("FB01", "패브릭",     "무아레 코튼 블랭킷",           "겨울",   "스테디셀러", 89000, 85000, 38000,  30, "2024-11-01"),  # 비수기(여름) 저조
    ("FB02", "패브릭",     "무아레 린넨 테이블러너",       "사계절", "스테디셀러", 32000, 30000, 13000,  75, "2025-04-01"),
    ("FB03", "패브릭",     "무아레 워시드 쿠션커버",       "사계절", "스테디셀러", 29000, 27000, 11500,  95, "2025-04-01"),
    ("FB04", "패브릭",     "무아레 린넨 앞치마",           "사계절", "스테디셀러", 34000, 32000, 14000,  60, "2025-06-01"),
    ("FB05", "패브릭",     "무아레 웨이브 테이블러너",     "여름",   "신제품",   34000, 32000, 13800,  70, "2026-06-12"),
    ("FB06", "패브릭",     "무아레 코튼 플레이스매트 2P",   "사계절", "스테디셀러", 24000, 22000,  9200,  90, "2025-04-01"),
    # --- 문구 (ST) ---
    ("ST01", "문구",       "무아레 데일리 다이어리",       "사계절", "스테디셀러", 22000, 21000,  7000, 110, "2025-11-01"),
    ("ST02", "문구",       "무아레 그리드 노트",           "사계절", "스테디셀러", 12000, 11000,  3800, 220, "2025-04-01"),
    ("ST03", "문구",       "무아레 아트 엽서세트",         "사계절", "스테디셀러",  9000,  8500,  2800, 300, "2025-04-01"),
    ("ST04", "문구",       "무아레 마스킹테이프 세트",     "사계절", "스테디셀러",  5500,  5000,  1700, 400, "2025-04-01"),
    ("ST05", "문구",       "무아레 실링스티커",           "사계절", "스테디셀러",  6500,  6000,  2100, 280, "2025-04-01"),
    ("ST06", "문구",       "무아레 데스크 캘린더",         "사계절", "시즌한정", 16000, 15000,  5200,  60, "2025-12-01"),
]
P_BY_SKU = {p[0]: p for p in PRODUCTS}
ALL_SKUS = [p[0] for p in PRODUCTS]
# 저가·리필은 편집샵/리빙 플랫폼 미취급 (편집샵은 객단가 관리)
NO_29_OH = {"ST02", "ST03", "ST04", "ST05", "FR07"}

monthly_sales = {p[0]: 0 for p in PRODUCTS}

def unit_price(sku, ch):
    _, _, _, _, _, msrp, base, _, _, _ = P_BY_SKU[sku]
    if ch == "MW": return base
    if ch == "NV": return int(round(base * 0.99 / 100) * 100)
    if ch == "OH": return msrp                       # 리빙 플랫폼: 정가 판매
    if ch == "29": return msrp                       # 편집샵: 정가 판매
    return base

def eligible_skus(ch):
    if ch in ("29", "OH"):
        return [s for s in ALL_SKUS if s not in NO_29_OH]
    return ALL_SKUS

# 판매 인기 가중 (저가 문구·스테디 다수, 고가 소수) — 채널 무관 기본 성향
POP_W = {
    "FR01": 32, "FR02": 20, "FR03": 22, "FR04": 24, "FR05": 20, "FR06": 30, "FR07": 34, "FR08": 26,
    "TW01": 40, "TW02": 30, "TW03": 26, "TW04": 22, "TW05": 24, "TW06": 20, "TW07": 14,
    "FB01": 6,  "FB02": 22, "FB03": 26, "FB04": 18, "FB05": 18, "FB06": 22,
    "ST01": 30, "ST02": 44, "ST03": 50, "ST04": 46, "ST05": 34, "ST06": 12,
}
def pick_sku(ch):
    elig = eligible_skus(ch)
    ws = [POP_W[s] for s in elig]
    return random.choices(elig, weights=ws)[0]

# ---------------------------------------------------------------------------
# 3) 캠페인 / 프로모션 (promo) — 스파이크 이벤트 + 상시 광고
#    대상 채널/SKU/날짜가 sales 스파이크와 정확히 정렬.
# ---------------------------------------------------------------------------
HERO = [
    dict(id="CMP-2606-01", typ="시즌런칭", media="메타+인스타", ch=["MW", "NV"],
         start="2026-06-12", end="2026-06-13", cat="여름컬렉션",
         skus=["FR05", "TW02", "TW04", "FB05"], spend=3500000, disc=0.0,
         note="여름 컬렉션 런칭 (오션브리즈 디퓨저·웨이브 라인)"),
    dict(id="CMP-2606-02", typ="기획전", media="자사몰+메타", ch=["MW"],
         start="2026-06-19", end="2026-06-21", cat="홈프래그런스+테이블웨어",
         skus=["FR01", "FR04", "FR05", "TW01", "TW02"], spend=1800000, disc=0.15,
         note="자사몰 여름 홈스타일링 기획전 (15% 할인)"),
    dict(id="CMP-2606-03", typ="채널세일", media="오늘의집 광고", ch=["OH"],
         start="2026-06-23", end="2026-06-25", cat="테이블웨어+패브릭",
         skus=["TW03", "TW05", "FB02", "FB03"], spend=1200000, disc=0.20,
         note="오늘의집 여름 리빙위크 입점세일 (20% 할인)"),
    dict(id="CMP-2606-04", typ="콘텐츠", media="인스타 릴스", ch=["MW"],
         start="2026-06-16", end="2026-06-17", cat="여름 시즌한정",
         skus=["FR03", "TW06"], spend=800000, disc=0.0,
         note="시트러스 캔들·글라스컵 인스타 콘텐츠 부스팅"),
    dict(id="CMP-2606-05", typ="기획전", media="29CM 기획전", ch=["29"],
         start="2026-06-26", end="2026-06-27", cat="홈프래그런스+패브릭",
         skus=["FR04", "FB01", "FB04"], spend=1500000, disc=0.10,
         note="29CM 여름 리빙 기획전 (이번 주 / 10% 할인)"),
]
HERO_DAYS = {}
for h in HERO:
    d0 = dt.date.fromisoformat(h["start"]); d1 = dt.date.fromisoformat(h["end"])
    d = d0
    while d <= d1:
        HERO_DAYS.setdefault(d, []).append(h)
        d += dt.timedelta(days=1)

# 소형 프로모션 (스파이크 아님 — 일상 쿠폰/단품 세일)
SMALL = [
    ("문구 묶음 쿠폰",   "MW", "문구",       ["ST02", "ST03", "ST05"], 0.10, "2026-06-02", "2026-06-08"),
    ("룸스프레이 단독전", "NV", "홈프래그런스", ["FR06"],               0.12, "2026-06-09", "2026-06-12"),
    ("스톤 머그 1+1",    "MW", "테이블웨어",   ["TW01"],               0.00, "2026-06-14", "2026-06-16"),
    ("쿠션커버 백화점행사","OH", "패브릭",     ["FB03"],               0.05, "2026-06-10", "2026-06-13"),
    ("컵세트 여름 쿨딜",  "NV", "테이블웨어",   ["TW06"],               0.10, "2026-06-23", "2026-06-26"),
    ("다이어리 신학기",   "MW", "문구",       ["ST01", "ST06"],       0.10, "2026-05-26", "2026-05-31"),
    ("티팟 단독 큐레이션","29", "테이블웨어",   ["TW07"],               0.00, "2026-06-16", "2026-06-22"),
]

PROMO_DISC = {}
def _register_disc(start, end, ch_codes, skus, disc):
    if disc <= 0:
        return
    d0 = dt.date.fromisoformat(start); d1 = dt.date.fromisoformat(end)
    d = d0
    while d <= d1:
        for ch in ch_codes:
            for s in skus:
                k = (d.isoformat(), ch, s)
                PROMO_DISC[k] = max(PROMO_DISC.get(k, 0), disc)
        d += dt.timedelta(days=1)
for h in HERO:
    _register_disc(h["start"], h["end"], h["ch"], h["skus"], h["disc"])
for name, ch, cat, skus, disc, ws, we in SMALL:
    _register_disc(ws, we, [ch], skus, disc)

# ---------------------------------------------------------------------------
# 4) 매출 데이터 생성
# ---------------------------------------------------------------------------
START = dt.date(2026, 5, 26)
END = dt.date(2026, 6, 28)
HOUR_W = [1,1,1,1,1,2,3,5,7,9,10,11,10,9,8,7,8,9,10,11,10,8,5,3]
REGION = (["서울"]*30 + ["경기"]*25 + ["인천"]*8 + ["부산"]*7 + ["대구"]*5 +
          ["광주"]*4 + ["대전"]*4 + ["울산"]*3 + ["경남"]*4 + ["기타"]*10)
STATUS = (["배송완료"]*80 + ["배송중"]*8 + ["교환완료"]*6 + ["반품완료"]*6)
CH_W = {"MW": 0.42, "NV": 0.28, "OH": 0.18, "29": 0.12}
CH_CODES = list(CH_W.keys())
CH_WEIGHTS = list(CH_W.values())
WEEKDAY_F = [0.85, 0.9, 1.0, 1.1, 1.25, 1.35, 1.05]  # Mon..Sun (주말·금 강세)

BASE_PER_DAY = 50
rows = []
seq = {}

def new_order_id(ch, d):
    key = (ch, d)
    seq[key] = seq.get(key, 0) + 1
    return f"{ch}-{d.strftime('%y%m%d')}-{seq[key]:04d}"

def qty_for(sku):
    if sku.startswith("ST"):   # 문구는 다수 구매
        return random.choices([1,2,3,4,5], weights=[38,26,16,12,8])[0]
    if sku in ("FB01",):       # 고가 블랭킷 1개
        return 1
    return random.choices([1,2,3], weights=[72,21,7])[0]

def emit_order(ch, d, skus=None, qty_boost=1.0):
    oid = new_order_id(ch, d)
    hour = random.choices(range(24), weights=HOUR_W)[0]
    minute = random.randint(0, 59)
    region = random.choice(REGION)      # 주문 단위 1회 결정
    status = random.choice(STATUS)
    n_lines = random.choices([1, 2, 3], weights=[64, 27, 9])[0]
    chosen = []
    seen = set()
    for _ in range(n_lines):
        sku = (random.choice(skus) if skus else pick_sku(ch))
        if sku in seen:
            continue
        seen.add(sku)
        p = P_BY_SKU[sku]
        cat = p[1]
        price = unit_price(sku, ch)
        disc = PROMO_DISC.get((d.isoformat(), ch, sku), 0)
        if disc > 0:
            price = int(round(price * (1 - disc) / 100) * 100)
        qty = max(1, int(round(qty_for(sku) * qty_boost)))
        chosen.append((sku, cat, price, qty))
    for sku, cat, price, qty in chosen:
        rows.append([
            oid, d.isoformat(), f"{hour:02d}:{minute:02d}",
            CH_BY_CODE[ch][1], cat, sku, P_BY_SKU[sku][2], qty, price, price*qty,
            region, status,
        ])
        monthly_sales[sku] += qty

d = START
while d <= END:
    wf = WEEKDAY_F[d.weekday()]
    n = int(round(BASE_PER_DAY * wf * random.uniform(0.92, 1.08)))
    for _ in range(n):
        ch = random.choices(CH_CODES, weights=CH_WEIGHTS)[0]
        emit_order(ch, d)
    # 스파이크: 해당일 히어로 캠페인 대상 채널/SKU로 주문 수 자체를 끌어올림.
    # 라이프스타일 저단가 → 일총매출 +30%↑ 넘기려면 건수를 크게.
    for h in HERO_DAYS.get(d, []):
        for ch in h["ch"]:
            # 오늘의집은 기본 물량이 작아 일총매출 +30%↑를 넘기려면 주입량을 더 크게.
            oh = ch == "OH"
            extra = random.randint(66, 84) if oh else random.randint(40, 56)
            boost = 1.5 if oh else 1.4
            for _ in range(extra):
                emit_order(ch, d, skus=h["skus"], qty_boost=boost)
    d += dt.timedelta(days=1)

rows.sort(key=lambda r: (r[1], r[2], r[0]))

with open(f"{OUT}/sales.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["주문번호","주문일","주문시간","채널","카테고리","SKU","상품명","수량","단가","금액","배송지역","주문상태"])
    for r in rows:
        oid, day, tm, chname, cat, sku, _c, qty, price, amount, region, status = r
        w.writerow([oid, day, tm, chname, cat, sku, P_BY_SKU[sku][2], qty, price, amount, region, status])

# ---------------------------------------------------------------------------
# 5) product_master.csv  (월판매량은 실제 생성분 반영)
# ---------------------------------------------------------------------------
with open(f"{OUT}/product_master.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["SKU","카테고리","상품명","시즌","유형","정가","자사몰판매가","원가","재고수량","월판매량","출시일"])
    for sku, cat, name, season, kind, msrp, base, cost, stock, launch in PRODUCTS:
        w.writerow([sku, cat, name, season, kind, msrp, base, cost, stock, monthly_sales[sku], launch])

# ---------------------------------------------------------------------------
# 6) reviews.csv  (카페24 자사몰 + 네이버 리뷰. 긍부정은 라벨 없이 평점+내용으로 — AI가 분류)
# ---------------------------------------------------------------------------
POS = {
    "홈프래그런스": ["향이 은은하고 오래가서 만족해요","집들이 선물했더니 반응 좋았어요","패키지가 고급스러워서 소장각이에요",
                "무아레 향 시리즈 계속 모으는 중이에요","발향 밸런스가 딱 좋아요","방에 두니 분위기가 확 살아요"],
    "테이블웨어": ["색감이 사진 그대로예요","묵직하고 질감이 좋아요","플레이팅이 살아나서 자주 써요",
               "전자레인지도 되고 실용적이에요","선물했더니 좋아하네요","마감이 깔끔하고 튼튼해요"],
    "패브릭": ["도톰하고 촉감이 좋아요","세탁해도 형태가 잘 유지돼요","색이 은은해서 어디든 잘 어울려요",
            "마감이 꼼꼼하네요","생각보다 고급스러워요"],
    "문구": ["종이질이 좋아서 필기감이 부드러워요","디자인이 예뻐서 데일리로 써요","가성비 좋아요",
           "구성이 알차서 만족이에요","선물용으로 딱이에요"],
}
NEU = ["무난해요","그냥 평범해요","기대보단 딱 그 정도예요","가격 생각하면 적당한 것 같아요","나쁘진 않은데 특별하진 않네요"]
NEG_GENERIC = ["가격 대비 조금 아쉬워요","색이 화면과 살짝 달라요","배송이 생각보다 늦었어요","기대했는데 아쉽네요"]
NEG_FR05 = ["오션브리즈라는데 향이 너무 약해요","이틀 지나니 향이 거의 안 나요","디퓨저 스틱에 향이 잘 안 올라와요",
            "지속력이 아쉬워서 재구매는 고민돼요","향이 금방 날아가서 방이 크면 무의미해요","리드에 향이 안 먹는 느낌이에요"]
NEG_TW04 = ["배송 중에 깨져서 왔어요","포장이 부실해서 모서리가 나갔어요","받자마자 금이 가 있었어요",
            "교환받았는데 또 한쪽이 깨져 있었어요","완충재가 부족해서 파손 위험 높아 보여요"]

# 리뷰는 매출 RNG와 분리된 전용 RNG로 생성 (매출 튜닝이 리뷰 분포를 흔들지 않게).
rrng = random.Random(20260705)

# SKU별 평점 분포 (기본 vs 특화 클러스터)
DEFAULT_DIST = {5:0.46, 4:0.30, 3:0.13, 2:0.06, 1:0.05}   # 평균 ~4.06
DIST = {}
for s in ALL_SKUS:
    DIST[s] = dict(DEFAULT_DIST)
DIST["FR05"] = {5:0.15, 4:0.18, 3:0.17, 2:0.28, 1:0.22}   # 향 약함 부정 클러스터 (평균 ~2.8, ≤2점 절반)
DIST["TW04"] = {5:0.26, 4:0.20, 3:0.12, 2:0.24, 1:0.18}   # 배송 파손 클러스터 (평균 ~3.1, ≤2점 40%+)
DIST["FR02"] = {5:0.80, 4:0.16, 3:0.03, 2:0.007, 1:0.003} # 숨은 보석 (평균 ~4.75, 스테디 중 최상)

def pick_rating(sku):
    d = DIST[sku]
    return rrng.choices(list(d.keys()), weights=list(d.values()))[0]

def review_text(sku, cat, rating):
    if rating >= 4:
        return rrng.choice(POS[cat])
    if rating == 3:
        return rrng.choice(NEU)
    # 1~2점: SKU 특화 이슈 우선
    if sku == "FR05":
        return rrng.choice(NEG_FR05)
    if sku == "TW04":
        return rrng.choice(NEG_TW04)
    return rrng.choice(NEG_GENERIC)

# 리뷰 SKU 가중 = 판매량 비례 (많이 팔린 게 리뷰도 많이). 신제품 STAR는 리뷰 더 많이.
review_weight = {}
for s in ALL_SKUS:
    base_w = max(1, monthly_sales[s])
    if s in ("FR05", "TW04", "TW02", "FB05"):  # 여름 신제품 = 리뷰 유입 활발
        base_w = int(base_w * 1.4)
    review_weight[s] = base_w
RW_SKUS = list(review_weight.keys())
RW_WS = [review_weight[s] for s in RW_SKUS]

N_REVIEWS = 520
REV_CH = (["자사몰"]*60 + ["네이버 스마트스토어"]*40)
review_rows = []
rseq = 0
for _ in range(N_REVIEWS):
    sku = rrng.choices(RW_SKUS, weights=RW_WS)[0]
    cat = P_BY_SKU[sku][1]
    rating = pick_rating(sku)
    text = review_text(sku, cat, rating)
    # 리뷰일: 판매 window 안, 후반 가중(구매 후 작성)
    day_offset = int(rrng.triangular(0, (END - START).days, (END - START).days * 0.7))
    rday = START + dt.timedelta(days=day_offset)
    ch = rrng.choice(REV_CH)
    helpful = rrng.choices([0,1,2,3,5,8,12], weights=[40,22,15,10,7,4,2])[0]
    rseq += 1
    review_rows.append([
        f"RV-{rseq:04d}", rday.isoformat(), ch, sku, P_BY_SKU[sku][2],
        rating, text, helpful,
    ])
review_rows.sort(key=lambda r: r[1])

with open(f"{OUT}/reviews.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["리뷰ID","작성일","채널","SKU","상품명","평점","리뷰내용","도움수"])
    w.writerows(review_rows)

# ---------------------------------------------------------------------------
# 7) promo.csv  (히어로 5 + 상시 광고 + 소형 프로모션)
# ---------------------------------------------------------------------------
promo_rows = []
for h in HERO:
    promo_rows.append([
        h["id"], h["typ"], h["media"], ",".join(CH_BY_CODE[c][1] for c in h["ch"]),
        h["start"], h["end"], h["cat"], ",".join(h["skus"]),
        h["spend"], f"{h['disc']:.2f}", h["note"],
    ])
weeks = [("2026-05-26","2026-06-01"),("2026-06-02","2026-06-08"),
         ("2026-06-09","2026-06-15"),("2026-06-16","2026-06-22"),
         ("2026-06-23","2026-06-28")]
aon = [("메타",       "MW", "전체",       420000),
       ("인스타 부스팅","MW", "홈프래그런스", 360000),
       ("네이버 쇼핑검색","NV", "전체",      300000),
       ("오늘의집 노출", "OH", "테이블웨어",  240000)]
wi = 0
for ws, we in weeks:
    wi += 1
    for media, ch, cat, base_spend in aon:
        spend = int(base_spend * random.uniform(0.85, 1.15) / 1000) * 1000
        promo_rows.append([
            f"AON-26{wi:02d}-{ch}", "상시광고", media, CH_BY_CODE[ch][1],
            ws, we, cat, "", spend, "0.00", f"{wi}주차 상시 {media} 운영",
        ])
sn = 0
for name, ch, cat, skus, disc, ws, we in SMALL:
    sn += 1
    spend = random.choice([0, 0, 150000, 200000, 300000])
    promo_rows.append([
        f"PRM-2606-{sn:02d}", "프로모션", "자체", CH_BY_CODE[ch][1],
        ws, we, cat, ",".join(skus), spend, f"{disc:.2f}", name,
    ])

with open(f"{OUT}/promo.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["캠페인ID","유형","매체","채널","시작일","종료일","대상카테고리","대상SKU","광고비","할인율","비고"])
    w.writerows(promo_rows)

# ---------------------------------------------------------------------------
# 8) 검증 리포트 (스파이크 + 리뷰 클러스터)
# ---------------------------------------------------------------------------
from collections import defaultdict
day_total = defaultdict(int)
for r in rows:
    day_total[r[1]] += r[9]
vals = list(day_total.values())
avg = sum(vals) / len(vals)
print(f"sales rows: {len(rows)}  |  products: {len(PRODUCTS)}  |  reviews: {len(review_rows)}  |  promo rows: {len(promo_rows)}")
print(f"일평균 매출: {avg:,.0f}")
print("--- 히어로 스파이크 검증 (일총매출 평균 대비) ---")
hero_days_sorted = sorted(HERO_DAYS.keys())
for d in hero_days_sorted:
    t = day_total[d.isoformat()]
    print(f"  {d}  {t:>12,}  ({t/avg*100-100:+.0f}% vs 평균)  {'OK' if t>avg*1.3 else 'LOW!'}")
print("--- STAR SKU 리뷰 평점 평균 ---")
rat = defaultdict(list)
for rr in review_rows:
    rat[rr[3]].append(rr[5])
for s in ("FR05","TW04","FR02","FR01","TW01"):
    lst = rat[s]
    print(f"  {s} {P_BY_SKU[s][2]:<24} n={len(lst):>3}  평균 {sum(lst)/len(lst):.2f}" if lst else f"  {s} 리뷰없음")

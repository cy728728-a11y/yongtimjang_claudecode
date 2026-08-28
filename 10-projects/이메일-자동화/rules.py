# 받은편지함 일괄 분류 규칙. KEEP 이 DELETE 보다 우선한다(오삭제 방지).
import re

# ── 최우선 삭제: 아래 KEEP 규칙보다 앞선다 ──────────────────────────────
# 용팀장 지시(2026-08-28): "알리익스프레스 관련 메일은 전부 삭제해".
# 주문확인·송장번호·배송정보 같은 업무성 알림도 포함한다 —
# 업무 메일이라 남기자고 제안했으나 전부 삭제로 확정됨.
DEL_FROM_ABSOLUTE = [
    r'aliexpress',
]

# ── 무조건 남김: 보안·세금·정책·제재·금융·결제·공유·본인발신 ──────────────
KEEP_FROM = [
    r'forwarding-noreply@google\.com',   # 자동전달 확인 메일 — 절대 삭제 금지
    r'accounts\.google\.com',            # 구글 보안 알림
    r'no-reply-.*@.*claude\.(ai|com)',   # Claude 로그인/기기 보안
    r'security@mail\.(instagram|threads)\.(net|com)',
    r'payments-noreply@google\.com', r'cloudplatform-noreply@google\.com',
    r'noreply-accounts@google\.com', r'notebooklm-noreply@google\.com',
    r'notification@tosspayments\.com',
    r'(sh|sa)\.noreply@samsung\.com',
    r'no_reply@coupang\.com',            # 쿠팡 셀러 운영 알림(장기 미관리 상품 등)
    r'updates\.notion\.so',              # Notion 새 기기 로그인
    r'helpcustomers@navercorp',          # 전자세금계산서
    r'help_noreply@navercorp',           # 부가세 신고 안내
    r'help_safety_shopping@navercorp',   # KC인증 소명 등 제재
    r'nv_product_ips@navercorp',         # 운영기준위반 검수
    r'noreply_commerceapi@navercorp',    # 커머스API 정책·시크릿
    r'privacynotice_noreply@navercorp',
    r'mail\.tossbank\.com', r'payple\.kr', r'refundy\.co',
    r'noreply@github\.com', r'kipi\.or\.kr',
    r'drive-shares.*@google', r'googleplay-noreply@google\.com',
    r'invoice\+statements@mail\.anthropic\.com',
    r'googleaistudio-noreply@google\.com',
    r'cy728728@gmail\.com', r'cy728@',
    r'@daum\.net', r'@naver\.com$',
]
KEEP_SUBJ = [
    r'보안\s*(경고|알림)', r'Security alert', r'로그인용 보안', r'verify your device',
    r'세금계산서', r'부가세', r'원천세', r'소명', r'운영기준', r'제재', r'검수',
    r'약관', r'정책 변경', r'개인정보', r'영수증', r'receipt', r'인증',
    r'송장번호', r'주문 건', r'발송 완료', r'배송 정보', r'분쟁', r'환불',   # 구매대행 업무
    r'댓글에 새로운 답글', r'채널 액세스', r'비밀번호',
]

# ── 삭제: 정산입금·주문현황·광고/프로모션/뉴스레터/소셜알림 ────────────────
DEL_SUBJ = [
    r'^\s*[\(\[]?광고[\)\]]',            # (광고) 말머리
    r'정산금액.*입금', r'정산대금.*(입금|지급)',
    r'주문(현황|상태).*안내',
    # 유튜브 구독채널 알림 (본인 채널 관련은 위 KEEP 이 먼저 걸러짐)
    r'동영상을 올렸습니다', r'새로운 게시물', r'실시간 스트리밍 중', r'새 동영상',
]

# 상업 키워드는 제목만으로 지우면 위험하다 — 고객 CS 가 "할인 문의드립니다" 로 올 수 있다.
# List-Unsubscribe 헤더가 있는 대량발송(마케팅) 일 때만 적용한다.
DEL_SUBJ_BULK = [
    r'프로모션', r'할인', r'특가', r'쿠폰', r'무료 ?배송', r'무료 ?반품',
    r'\d+% ?off', r'discount', r'sale\b', r'promo',
]
DEL_FROM = [
    # 마케팅 뉴스레터 / 구독 마케팅
    r'send\.vidiq\.com', r'substack\.com', r'glasp\.co',
    r'send\.stibee\.com',                     # 디하클립 등 강의 홍보
    r'mail\.adobe\.com', r'monica\.im', r'higgsfield\.ai',
    r'emails\.hostinger\.com', r'litt\.ly',
    r'email\.openai\.com', r'email\.claude\.com', r'research\.anthropic\.com',
    r'team@mail\.notion\.(so|com)',           # Notion 제품 마케팅
    r'utis@onbiz\.or\.kr',                    # 이커머스페어 광고
    # 커머스 플랫폼 프로모션
    r'aliexpress\.com', r'deals\.aliexpress', r'newarrival\.aliexpress', r'mail\.aliexpress',
    r'donotreply.*@(e\.)?coupang\.com', r'no_reply@e\.coupang\.com',
    r'smartstore_noreply@navercorp',          # 정산입금 알림 전용 발신자
    # 소셜/협업 알림 (용팀장 승인: 전부 삭제)
    r'facebookmail\.com',
    r'notify@mail\.notion\.(so|com)',
    r'(?<![\w.-])no-reply@google\.com',       # 기기 설정 유도 (부분일치 방지)
    r'noreply-maps-timeline@google',
    r'news-googleplay@google\.com',              # 구글플레이 광고
    r'(no-reply|stories-recap|unread-messages)@mail\.instagram\.com',
    r'newsletter@investingmail\.com',
    r'discover@airbnb\.com', r'teamzoom@zoom\.us',
    r'team@comms\.evernote\.com', r'support@timetreeapp\.com',
    r'11st@ems\.11st\.co\.kr',
]

def judge(m):
    """한 건을 KEEP/DELETE/UNKNOWN 으로 판정"""
    f = (m.get('from') or '').lower()
    s = m.get('subject') or ''
    if any(re.search(p, f, re.I) for p in DEL_FROM_ABSOLUTE): return 'DELETE'
    if any(re.search(p, f, re.I) for p in KEEP_FROM): return 'KEEP'
    if any(re.search(p, s, re.I) for p in KEEP_SUBJ): return 'KEEP'
    if any(re.search(p, f, re.I) for p in DEL_FROM):  return 'DELETE'
    if any(re.search(p, s, re.I) for p in DEL_SUBJ):  return 'DELETE'
    # 대량발송 표식(List-Unsubscribe)이 있을 때만 상업 키워드를 적용
    if m.get('unsub') and any(re.search(p, s, re.I) for p in DEL_SUBJ_BULK):
        return 'DELETE'
    return 'UNKNOWN'

# ── 유튜브 특례: 구독채널 알림은 전부 삭제, 본인 채널/댓글 관련만 남김 ──
YT_KEEP = [r'댓글에 새로운 답글', r'채널 액세스', r'용감한용팀장', r'수익', r'저작권', r'가이드라인', r'경고']
def judge2(m):
    f = (m.get('from') or '').lower(); s = m.get('subject') or ''
    if 'youtube.com' in f:
        return 'KEEP' if any(re.search(p, s, re.I) for p in YT_KEEP) else 'DELETE'
    return judge(m)

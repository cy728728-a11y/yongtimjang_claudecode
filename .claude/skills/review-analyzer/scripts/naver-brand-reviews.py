#!/usr/bin/env python3
"""
네이버 브랜드스토어 리뷰 크롤러

brand.naver.com 내부 API를 사용하여 리뷰 수집.
네이버 로그인 세션 쿠키 필수 (NID_AUT, NID_SES 등).

사용법:
  python naver-brand-reviews.py <merchantNo> <productNo> --cookie "쿠키문자열"

쿠키 얻는 법 (택 1):
  방법 1: Selenium 자동 로그인 (권장)
    - .env 파일에 NAVER_ID, NAVER_PW 설정
    - --selenium 플래그로 자동 로그인 + 쿠키 추출

  방법 2: Chrome 확장 프로그램
    - chrome-extension/ 폴더를 Chrome에 unpacked로 로드
    - 네이버 로그인 상태에서 확장 프로그램 클릭 -> Export Cookies
    - Downloads/naver-cookies.txt 자동 생성 -> 스크립트가 자동 감지

  방법 3: 수동 복사
    - F12 -> Network -> query-pages 요청 -> Cookie 헤더 복사
    - --cookie "복사한문자열" 또는 --cookie-file cookie.txt

예시:
  # 자동 감지 (Chrome 확장으로 쿠키 내보낸 후)
  python naver-brand-reviews.py 500152098 11950808055

  # 쿠키 문자열 직접 입력
  python naver-brand-reviews.py 500152098 11950808055 --cookie "NNB=xxx; NID_AUT=xxx; NID_SES=xxx"

  # 쿠키 파일 지정
  python naver-brand-reviews.py 500152098 11950808055 --cookie-file cookie.txt

  # 최대 50개, 최신순 정렬
  python naver-brand-reviews.py 500152098 11950808055 --cookie "..." --max 50 --sort RECENT

  # 구글 시트 업로드
  python naver-brand-reviews.py 500152098 11950808055 --cookie "..." --sheet "https://docs.google.com/spreadsheets/d/..."

merchantNo, productNo 찾는 법:
  1. 브랜드스토어 제품 페이지에서 F12 -> Network -> Fetch/XHR
  2. 리뷰 영역까지 스크롤
  3. 'review' 필터 -> query-pages 요청의 Payload 확인
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

# API 설정
API_URL = "https://brand.naver.com/n/v1/contents/reviews/group-products/query-pages"
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Content-Type': 'application/json',
    'Origin': 'https://brand.naver.com',
    'Referer': 'https://brand.naver.com/',
    'Sec-Ch-Ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
    'X-Client-Version': '20260203185811',
}

# 정렬 옵션
SORT_OPTIONS = {
    'RANKING': 'REVIEW_RANKING',
    'RECENT': 'REVIEW_CREATE_DATE_DESC',
    'RATING_HIGH': 'REVIEW_SCORE_DESC',
    'RATING_LOW': 'REVIEW_SCORE_ASC',
}


def fetch_reviews(merchant_no, product_no, cookie_str=None, page=1, page_size=20, sort_type='REVIEW_RANKING', session=None):
    """리뷰 API 호출.

    session이 있으면 브라우저 JS fetch() 사용 (TLS 핑거프린팅 우회).
    없으면 curl 사용 (쿠키 필요).
    """
    # group-products API: originProductNos (배열), isMultiProfile 필수
    product_nos = [int(p) for p in str(product_no).split(',')] if ',' in str(product_no) else [int(product_no)]
    payload = {
        'checkoutMerchantNo': int(merchant_no),
        'originProductNos': product_nos,
        'page': page,
        'pageSize': page_size,
        'reviewSearchSortType': sort_type,
        'isMultiProfile': True,
    }

    # Selenium 세션 사용 (TLS 핑거프린팅 우회)
    if session:
        return session.fetch_json(API_URL, payload)

    # curl fallback
    payload_str = json.dumps(payload)
    cmd = [
        'curl', '-s',
        API_URL,
        '-H', 'Accept: application/json, text/plain, */*',
        '-H', 'Content-Type: application/json',
        '-H', f'Origin: {HEADERS["Origin"]}',
        '-H', f'Referer: {HEADERS.get("Referer", "https://brand.naver.com/")}',
        '-H', f'User-Agent: {HEADERS["User-Agent"]}',
        '--data-raw', payload_str,
    ]

    if cookie_str:
        cmd.extend(['-b', cookie_str])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  curl 오류 (페이지 {page}): {result.stderr}")
            return None

        body = result.stdout
        if not body or '<!DOCTYPE' in body[:100] or '<html' in body[:100]:
            print(f"  API 차단 (HTTP 204/429) - curl TLS 핑거프린팅 감지됨.")
            print(f"  --selenium 모드를 사용하세요.")
            return None

        return json.loads(body)
    except subprocess.TimeoutExpired:
        print(f"  타임아웃 (페이지 {page})")
        return None
    except json.JSONDecodeError as e:
        print(f"  JSON 파싱 오류 (페이지 {page}): {e}")
        print(f"  응답 시작: {body[:200] if body else '(비어있음)'}")
        return None


def parse_review(review):
    """단일 리뷰 파싱"""
    # 날짜 파싱
    create_date = review.get('createDate', '')
    if create_date:
        try:
            dt = datetime.fromisoformat(create_date.replace('+00:00', '+00:00'))
            create_date = dt.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass

    # 이미지 수
    attaches = review.get('reviewAttaches', [])
    image_count = len([a for a in attaches if a.get('reviewAttachmentType') == 'I'])

    return {
        'id': review.get('id', ''),
        'date': create_date,
        'rating': review.get('reviewScore', ''),
        'content': review.get('reviewContent', ''),
        'writer': review.get('maskedWriterId', ''),
        'product_name': review.get('productName', ''),
        'product_option': review.get('productOptionContent', ''),
        'review_type': review.get('reviewType', ''),
        'has_photo': review.get('reviewContentClassType', '') == 'PHOTO',
        'image_count': image_count,
        'image_urls': [a.get('attachUrl', '') for a in attaches if a.get('reviewAttachmentType') == 'I'],
    }


def extract_ids_from_page(driver):
    """제품 페이지 HTML에서 merchantNo와 originProductNo 추출.

    URL의 상품ID(channelProductNo)와 API용 originProductNo가 다르므로
    페이지 소스의 상품 JSON 블록에서 정확한 값을 뽑는다.
      - merchantNo    = 메인 상품 channel 블록의 channelNo
      - originProductNo = salePrice 바로 앞의 productNo (추천상품은 뒤에 linkUrl이 와서 구분됨)
    """
    html = driver.page_source
    m = re.search(r'"channel":\{"channelNo":(\d+)', html)
    p = re.search(r'"productNo":(\d+),"salePrice"', html)
    return (m.group(1) if m else None), (p.group(1) if p else None)


def crawl_reviews(merchant_no, product_no, cookie_str=None, max_reviews=200, sort='RANKING', session=None):
    """리뷰 전체 크롤링"""
    sort_type = SORT_OPTIONS.get(sort, 'REVIEW_RANKING')
    all_reviews = []
    page = 1
    total_pages = None

    mode = "Selenium (브라우저 직접)" if session else ("curl + 쿠키" if cookie_str else "쿠키 없음")
    print(f"\n네이버 브랜드스토어 리뷰 크롤러")
    print(f"MerchantNo: {merchant_no}")
    print(f"ProductNo: {product_no}")
    print(f"정렬: {sort} ({sort_type})")
    print(f"모드: {mode}")
    print(f"목표: 최대 {max_reviews}개\n")

    while len(all_reviews) < max_reviews:
        print(f"크롤링 중: 페이지 {page}" + (f"/{total_pages}" if total_pages else "") + f" (현재 {len(all_reviews)}개)...")

        data = fetch_reviews(merchant_no, product_no, cookie_str=cookie_str, page=page, sort_type=sort_type, session=session)
        if not data:
            break

        # 첫 페이지에서 총 리뷰 수 확인
        if page == 1:
            total_elements = data.get('totalElements', 0)
            total_pages = data.get('totalPages', 0)
            print(f"총 리뷰: {total_elements}개 ({total_pages}페이지)")

        contents = data.get('contents', [])
        if not contents:
            print(f"  페이지 {page}: 리뷰 없음, 종료")
            break

        for review in contents:
            parsed = parse_review(review)
            if parsed.get('content'):
                all_reviews.append(parsed)

        print(f"  페이지 {page}: {len(contents)}개 수집 (총 {len(all_reviews)}개)")

        # 마지막 페이지 체크
        if data.get('last', False):
            print("마지막 페이지 도달")
            break

        page += 1
        time.sleep(0.5)  # 서버 부하 방지

    return all_reviews[:max_reviews]


def save_csv(reviews, output_path):
    """CSV 파일로 저장"""
    fieldnames = ['date', 'rating', 'content', 'writer', 'product_name', 'product_option', 'has_photo', 'image_count']

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(reviews)

    print(f"CSV 저장 완료: {output_path} ({len(reviews)}개)")


def save_json(reviews, output_path):
    """JSON 파일로 저장"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)

    print(f"JSON 저장 완료: {output_path} ({len(reviews)}개)")


def upload_to_sheets(reviews, sheet_url):
    """구글 시트에 업로드"""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("Error: gspread/google-auth 패키지가 필요합니다.")
        print("설치: pip3 install gspread google-auth")
        return

    service_account_path = os.path.expanduser('~/.config/gspread/service_account.json')
    if not os.path.exists(service_account_path):
        print(f"Error: {service_account_path} 파일이 없습니다.")
        return

    creds = Credentials.from_service_account_file(
        service_account_path,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(creds)

    sheet_id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
    if not sheet_id_match:
        print(f"Error: 올바른 구글 시트 URL이 아닙니다.")
        return

    spreadsheet = gc.open_by_key(sheet_id_match.group(1))
    worksheet = spreadsheet.sheet1
    worksheet.clear()

    # 헤더
    headers = ['날짜', '평점', '리뷰내용', '작성자', '상품명', '옵션', '사진여부', '이미지수', '수집일시']
    worksheet.update(values=[headers], range_name='A1:I1')

    # 데이터
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    rows = []
    for r in reviews:
        rows.append([
            r.get('date', ''),
            r.get('rating', ''),
            r.get('content', '')[:500],
            r.get('writer', ''),
            r.get('product_name', '')[:100],
            r.get('product_option', ''),
            'Y' if r.get('has_photo') else 'N',
            r.get('image_count', 0),
            now,
        ])

    if rows:
        batch_size = 100
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            start_row = i + 2
            end_row = start_row + len(batch) - 1
            worksheet.update(values=batch, range_name=f'A{start_row}:I{end_row}')
            print(f"  업로드: {i + 1}~{min(i + batch_size, len(rows))}개")

    print(f"구글 시트 업로드 완료: {len(rows)}개 리뷰")


def main():
    parser = argparse.ArgumentParser(
        description='네이버 브랜드스토어 리뷰 크롤러',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시 (권장: --no-login, 제품 URL만 → ID 자동 추출):
  # 최신순 50개를 CSV로
  python naver-brand-reviews.py --no-login \\
    --referer 'https://brand.naver.com/<store>/products/<productId>' \\
    --max 50 --sort RECENT --output reviews.csv

  # 낮은 별점순 100개 (불만 분석용)
  python naver-brand-reviews.py --no-login \\
    --referer 'https://brand.naver.com/<store>/products/<productId>' \\
    --max 100 --sort RATING_LOW --output low.csv

  # ID를 이미 알면 직접 지정도 가능
  python naver-brand-reviews.py <merchantNo> <productNo> --no-login \\
    --referer 'https://brand.naver.com/<store>/products/<productId>'

정렬 옵션: RANKING (기본), RECENT, RATING_HIGH, RATING_LOW
        """
    )

    parser.add_argument('merchant_no', nargs='?', help='checkoutMerchantNo (스토어 번호). --no-login+--referer 시 생략하면 자동 추출')
    parser.add_argument('product_no', nargs='?', help='originProductNo (상품 번호). --no-login+--referer 시 생략하면 자동 추출')
    parser.add_argument('--cookie', '-c', help='네이버 로그인 쿠키 문자열 (DevTools에서 복사)')
    parser.add_argument('--cookie-file', '-cf', help='쿠키 문자열이 저장된 파일 경로')
    parser.add_argument('--selenium', action='store_true', help='Selenium으로 네이버 로그인하여 쿠키 자동 추출')
    parser.add_argument('--no-login', action='store_true', help='로그인 없이 익명 Selenium 세션으로 크롤 (공개 리뷰 권장). --referer 로 제품 URL 지정')
    parser.add_argument('--referer', '-r', help='제품 페이지 URL (--no-login 모드에서 필수, 여기서 ID 자동 추출)')
    parser.add_argument('--max', '-m', type=int, default=200, help='최대 수집 수 (기본: 200)')
    parser.add_argument('--sort', '-s', default='RANKING', choices=SORT_OPTIONS.keys(), help='정렬 (기본: RANKING)')
    parser.add_argument('--output', '-o', help='출력 파일 (.csv 또는 .json)')
    parser.add_argument('--sheet', help='구글 시트 URL')

    args = parser.parse_args()

    # 쿠키 처리 (원본 문자열 그대로 Cookie 헤더로 전송)
    cookie_str = None
    naver_session = None  # Selenium 세션 (--selenium 모드)
    if args.cookie:
        cookie_str = args.cookie.strip()
        cookie_count = len([c for c in cookie_str.split(';') if '=' in c])
        print(f"쿠키 로드: 직접 입력 ({cookie_count}개 항목)")
    elif args.cookie_file:
        cookie_path = os.path.expanduser(args.cookie_file)
        if os.path.exists(cookie_path):
            with open(cookie_path, 'r') as f:
                cookie_str = f.read().strip()
            cookie_count = len([c for c in cookie_str.split(';') if '=' in c])
            print(f"쿠키 로드: {cookie_path} ({cookie_count}개 항목)")
        else:
            print(f"Warning: 쿠키 파일을 찾을 수 없습니다: {cookie_path}")
    elif args.no_login:
        # 로그인 없이 익명 Selenium 세션 (공개 리뷰는 로그인 불필요)
        try:
            from cookie_extractor import _create_driver, NaverSession
        except ImportError:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            from cookie_extractor import _create_driver, NaverSession

        if not args.referer:
            print("Error: --no-login 모드는 --referer 로 제품 페이지 URL이 필요합니다.")
            print("  예: --no-login --referer 'https://brand.naver.com/iloom/products/12006071856'")
            sys.exit(1)

        print("익명 Selenium 세션 시작 (로그인 없음)...")
        naver_session = NaverSession()
        naver_session.driver = _create_driver()
        naver_session.driver.get(args.referer)
        time.sleep(3)

        # merchant_no / product_no 미지정 시 페이지에서 자동 추출
        if not args.merchant_no or not args.product_no:
            mno, pno = extract_ids_from_page(naver_session.driver)
            args.merchant_no = args.merchant_no or mno
            args.product_no = args.product_no or pno
            if not args.merchant_no or not args.product_no:
                print("Error: 페이지에서 ID 추출 실패 (merchant/product). 인자로 직접 지정하세요.")
                naver_session.close()
                sys.exit(1)
            print(f"자동 추출: merchantNo={args.merchant_no}  originProductNo={args.product_no}")
    elif args.selenium:
        # Selenium 브라우저 세션 (TLS 핑거프린팅 우회)
        try:
            from cookie_extractor import load_env, NaverSession
        except ImportError:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            from cookie_extractor import load_env, NaverSession

        naver_id, naver_pw = load_env()
        if not naver_id or not naver_pw:
            print("Error: .env 파일에 NAVER_ID, NAVER_PW를 설정해주세요.")
            print(f"  파일 위치: {os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')}")
            sys.exit(1)

        print("Selenium 브라우저 세션 시작...")
        naver_session = NaverSession()
        # referer URL이 있으면 해당 제품 페이지로 이동 (same-origin 확보)
        product_url = args.referer if args.referer else None
        if not naver_session.login(naver_id, naver_pw, product_url=product_url):
            print("Error: Selenium 로그인 실패")
            sys.exit(1)
    else:
        # Chrome 확장 프로그램이 내보낸 쿠키 파일 자동 감지
        auto_paths = [
            os.path.expanduser("~/Downloads/naver-cookies.txt"),
            os.path.expanduser("~/downloads/naver-cookies.txt"),
            os.path.join(os.getcwd(), "naver-cookies.txt"),
            # WSL: Windows Downloads 폴더
            "/mnt/c/Users/" + os.environ.get("USER", "") + "/Downloads/naver-cookies.txt",
        ]
        for p in auto_paths:
            if os.path.exists(p):
                with open(p, 'r') as f:
                    cookie_str = f.read().strip()
                if cookie_str and '=' in cookie_str:
                    cookie_count = len([c for c in cookie_str.split(';') if '=' in c])
                    print(f"쿠키 자동 감지: {p} ({cookie_count}개 항목)")
                    break
                cookie_str = None

        if not cookie_str:
            print("Warning: 쿠키 미지정. 네이버 API는 로그인 쿠키 없이 429 에러를 반환합니다.")
            print("  Chrome 확장 프로그램으로 쿠키를 내보내거나,")
            print("  --cookie 또는 --cookie-file 옵션을 사용하세요.")

    # Referer 설정 (필수: 구체적인 제품 페이지 URL)
    if args.referer:
        HEADERS['Referer'] = args.referer
        print(f"Referer: {args.referer}")
    else:
        print("Warning: --referer 미지정. 브랜드스토어 제품 페이지 URL을 --referer로 지정하세요.")
        print("  예: --referer 'https://brand.naver.com/iloom/products/12006071856'")

    # Selenium 세션 객체 (--selenium / --no-login 모드에서 존재)
    naver_session_obj = naver_session if (args.selenium or args.no_login) else None

    # ID 필수 검증 (자동 추출 안 되는 모드)
    if not args.merchant_no or not args.product_no:
        print("Error: merchant_no와 product_no가 필요합니다.")
        print("  (--no-login --referer <제품URL> 로 자동 추출하거나, 두 값을 직접 지정하세요)")
        if naver_session_obj:
            naver_session_obj.close()
        sys.exit(1)

    # 크롤링
    try:
        reviews = crawl_reviews(args.merchant_no, args.product_no, cookie_str=cookie_str, max_reviews=args.max, sort=args.sort, session=naver_session_obj)
    finally:
        # Selenium 세션 정리
        if naver_session_obj:
            naver_session_obj.close()
    print(f"\n수집 완료: {len(reviews)}개 리뷰")

    # 저장
    if args.output:
        if args.output.endswith('.json'):
            save_json(reviews, args.output)
        else:
            save_csv(reviews, args.output)

    if args.sheet:
        upload_to_sheets(reviews, args.sheet)

    # 파일 미지정 시 기본 CSV 저장
    if not args.output and not args.sheet:
        default_path = f"naver_reviews_{args.product_no}_{datetime.now().strftime('%Y%m%d')}.csv"
        save_csv(reviews, default_path)

    # 샘플 출력
    if reviews:
        print(f"\n--- 샘플 리뷰 (최대 5개) ---")
        for i, r in enumerate(reviews[:5], 1):
            print(f"[{i}] {'★' * r.get('rating', 0)} | {r.get('date', '')} | {'📷' if r.get('has_photo') else ''}")
            print(f"    {r.get('content', '')[:80]}")
            print(f"    옵션: {r.get('product_option', '')}")
            print()


if __name__ == '__main__':
    main()

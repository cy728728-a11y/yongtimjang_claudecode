# -*- coding: utf-8 -*-
"""Q3 파일럿 — 비전 AI 가 용팀장의 시각 기준을 재현하는가.

기준(2026-09-22 경계 4장 답): **제품이 사진에 나오면 제품, 안 나오면 배너.**
어휘군(글자 기준)이 못 가른 30장만 태운다. 전량 아님.
"""
import base64, io, json, os, re, sys, time, urllib.request

ENV = ".claude/skills/sellerlife-keyword/.env"
MODEL = "gemini-3.6-flash"
대상파일 = "/tmp/pilot19.json"
결과파일 = "/tmp/pilot_result.json"

def 키읽기():
    s = open(ENV, encoding="utf-8").read()
    m = re.search(r"^GEMINI_API_KEY=(.*)$", s, re.M)
    if not m:
        raise SystemExit("GEMINI_API_KEY 없다")
    return m.group(1).strip().strip('"').strip("'")

def 이미지준비(경로, 최대=1024):
    """긴 변 1024px 로 줄여 JPEG 바이트를 낸다 — 토큰과 시간을 아낀다."""
    from PIL import Image                      # 지연 import (D-19 경계 밖 스크립트지만 관례를 따른다)
    im = Image.open(경로)
    im = im.convert("RGB")
    w, h = im.size
    if max(w, h) > 최대:
        r = 최대 / max(w, h)
        im = im.resize((int(w * r), int(h * r)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()

지침 = """너는 중국 타오바오 상세페이지 이미지를 한 장씩 보고 분류한다.

판정 기준은 딱 하나다:
  **판매 상품 자체(실물)가 사진에 찍혀 있으면 "제품".**
  **찍혀 있지 않으면 "배너".**

보충:
- 상품이 크게 나오든 작게 나오든, 글자가 많이 얹혀 있든, 상품 실물이 보이면 "제품"이다.
- 상품 없이 회사소개·공장직판·품질보증·배송반품 안내·경품·인증서·랭킹·연락처(위챗/QR)·
  브랜드 슬로건·주문안내 같은 것만 있으면 "배너"다.
- 상품의 부품·부속품·포장박스도 상품 실물로 친다 → "제품".
- 치수도(도면)·사이즈표는 상품 실물이 아니다 → "배너".

JSON 만 출력해라. 다른 말 금지:
{"판정":"제품" 또는 "배너","상품보임":true 또는 false,"근거":"15자 이내 한국어"}"""

def 한장판정(키, 이미지바이트):
    body = {
        "systemInstruction": {"parts": [{"text": 지침}]},
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "image/jpeg",
                             "data": base64.b64encode(이미지바이트).decode()}},
            {"text": "이 장을 판정해라."},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={키}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.loads(r.read())
    t = j["candidates"][0]["content"]["parts"][0]["text"]
    사용 = j.get("usageMetadata", {})
    return json.loads(t), 사용

def main():
    키 = 키읽기()
    대상 = json.load(open(대상파일, encoding="utf-8"))
    결과, 입력토큰, 출력토큰 = [], 0, 0
    for n, d in enumerate(대상, 1):
        try:
            판정, 사용 = 한장판정(키, 이미지준비(d["경로"]))
            입력토큰 += 사용.get("promptTokenCount", 0)
            출력토큰 += sum(사용.get(k, 0) for k in ("candidatesTokenCount", "thoughtsTokenCount"))
            맞음 = (판정["판정"] == d["정답"])
        except Exception as e:
            판정, 맞음 = {"판정": f"실패:{type(e).__name__}", "상품보임": None, "근거": str(e)[:60]}, False
        결과.append({**d, "비전": 판정, "맞음": 맞음})
        print(f"[{n:2}/{len(대상)}] {d['코드'][:8]} {d['장']:>2}번 | "
              f"기계={d['기계']:<4} 용팀장={d['정답']:<4} 비전={판정['판정']:<4} "
              f"{'✅' if 맞음 else '❌'} {판정.get('근거','')}", flush=True)
        time.sleep(0.3)                        # 무료 티어 레이트리밋 여유
    json.dump({"결과": 결과, "입력토큰": 입력토큰, "출력토큰": 출력토큰},
              open(결과파일, "w"), ensure_ascii=False, indent=1)
    맞은수 = sum(1 for r in 결과 if r["맞음"])
    print("\n" + "=" * 60)
    print(f"전체 {len(결과)}장 중 {맞은수}장 일치 ({맞은수/len(결과)*100:.1f}%)")
    for 종 in ("미탐", "오탐"):
        g = [r for r in 결과 if r["종류"] == 종]
        if g:
            print(f"  {종} {len(g)}장 → 비전이 바로잡은 것 {sum(1 for r in g if r['맞음'])}장")
    print(f"토큰: 입력 {입력토큰:,} · 출력 {출력토큰:,}")

if __name__ == "__main__":
    main()

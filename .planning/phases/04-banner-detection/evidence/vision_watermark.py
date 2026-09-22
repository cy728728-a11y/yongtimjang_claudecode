# -*- coding: utf-8 -*-
"""Q3 파일럿 — 비전 AI 가 용팀장의 시각 기준을 재현하는가.

기준(2026-09-22 경계 4장 답): **제품이 사진에 나오면 제품, 안 나오면 배너.**
어휘군(글자 기준)이 못 가른 30장만 태운다. 전량 아님.
"""
import base64, io, json, os, re, sys, time, urllib.request

ENV = ".claude/skills/sellerlife-keyword/.env"
MODEL = "gemini-3.6-flash"
대상파일 = "/tmp/wm18.json"
결과파일 = "/tmp/wm18_result.json"

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

지침 = """이 이미지는 중국 타오바오 상세페이지의 한 장이다. 한국 스마트스토어에 올릴 후보다.

세 가지로 분류해라:

 "제품"       = 상품 실물이 찍혀 있고, **중국 점포·플랫폼 흔적이 없다.** 그대로 올려도 된다.
 "워터마크제품" = 상품 실물은 찍혀 있으나 **중국 점포/플랫폼 표식이 박혀 있다.**
                (淘宝/taobao·天猫/Tmall·위챗/微信·QR·점포명 워터마크·중국 전화번호 등)
                그대로 올리면 안 된다.
 "배너"       = 상품 설명이 아니라 점포·행사·순위·인증·배송정책 홍보가 주인공이다.

워터마크는 흐릿하게 반투명으로 깔린 것도 포함한다. 작더라도 있으면 "워터마크제품"이다.

JSON 만 출력해라. 다른 말 금지:
{"판정":"제품" 또는 "워터마크제품" 또는 "배너","상품보임":true 또는 false,"근거":"20자 이내 한국어"}"""

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

# PJS 세미나 1·2부 정리본 -> 카페 게시용 HTML (이름 가림, 개인 메모 제외)
import re, markdown
SRC = ['../2026-11-14_PJS-세미나-1부-정리.md', '../2026-11-14_PJS-세미나-2부-정리.md']
NAMES = ['임광찬','한정화','임재현','위승민','박용덕','나석진','김현경','윤형석','김화영','배종현','조은영',
         '고두영','전수영','나은아','전민수','박민환','배정현','전대성','마선미','배창식','김교현','안정란']
def mask(t):
    return t  # 실명 유지(회원 카페용)
    t = t.replace('광찬 씨', '○○ 씨').replace('준택 과장', '○ 과장')
    return t
def clean(t):
    t = re.split(r'\n## 용팀장', t)[0]                       # 개인 적용·교정노트 이하 제거
    t = '\n'.join(l for l in t.split('\n') if not re.match(r'> \*\*(원문|1부 정리|화면)\*\*', l))
    t = re.sub(r'\[\[[^\]]+\]\]', '', t)
    t = re.sub(r'^# .*\n', '', t, count=1)                  # 원래 제목은 파트 제목으로 대체
    return mask(t)
parts = []
titles = ['1부 — 집은 파는 게 아니다 · 오피스텔 KB시세 삭제 · TQQQ 적립',
          '2부 — 일상은 위대하다 · 현장 사건들 · 태도와 목표 · 초부자 4가지 습관']
for i,(p,ti) in enumerate(zip(SRC,titles),1):
    body = markdown.markdown(clean(open(p,encoding='utf-8').read()), extensions=['tables','sane_lists','nl2br'])
    body = body.replace('<h2', '<h2 class="sec"', )
    parts.append(f'<section id="p{i}"><h1 class="part">{ti}</h1>{body}</section>')
html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PJS 세미나 정리</title>
<style>
:root{{--bg:#fbfaf7;--fg:#222;--sub:#666;--line:#e3dfd6;--acc:#1f5f8b;--q:#f2efe8;--th:#eef3f7}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#16181b;--fg:#e6e6e6;--sub:#a0a0a0;--line:#33373c;--acc:#7cb8e4;--q:#22262b;--th:#1f2a33}}}}
:root[data-theme="dark"]{{--bg:#16181b;--fg:#e6e6e6;--sub:#a0a0a0;--line:#33373c;--acc:#7cb8e4;--q:#22262b;--th:#1f2a33}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;line-height:1.75;font-size:16px}}
main{{max-width:860px;margin:0 auto;padding:24px 16px 80px}}
header.top{{border-bottom:3px solid var(--acc);padding-bottom:16px;margin-bottom:8px}}
header.top h1{{font-size:28px;margin:0 0 6px}}
header.top p{{margin:4px 0;color:var(--sub)}}
nav.toc{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 8px}}
nav.toc a{{padding:8px 14px;border:1px solid var(--acc);border-radius:20px;color:var(--acc);text-decoration:none;font-weight:600}}
h1.part{{font-size:23px;margin:48px 0 8px;padding:12px 14px;background:var(--acc);color:#fff;border-radius:8px}}
h2{{font-size:20px;margin:36px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line);color:var(--acc)}}
h3{{font-size:17px;margin:24px 0 8px}}
blockquote{{margin:12px 0;padding:10px 14px;background:var(--q);border-left:4px solid var(--acc);border-radius:4px}}
blockquote p{{margin:4px 0}}
table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:14.5px;display:block;overflow-x:auto}}
th,td{{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}}
th{{background:var(--th)}}
hr{{border:0;border-top:1px dashed var(--line);margin:28px 0}}
code{{background:var(--q);padding:1px 5px;border-radius:3px}}
footer{{margin-top:48px;color:var(--sub);font-size:14px;border-top:1px solid var(--line);padding-top:12px}}
@media print{{body{{background:#fff;color:#000;font-size:12.5px}} nav.toc{{display:none}} h1.part{{break-before:page;background:#1f5f8b}} table{{display:table}} tr,blockquote{{break-inside:avoid}}}}
</style></head><body><main>
<header class="top"><h1>PJS 세미나 정리</h1>
<p>2026년 11월 14일(토) · 박정수 대표 세미나 · 1부 약 2시간 7분, 2부 약 1시간 57분</p>
<p>현장 녹음을 받아쓴 뒤 정리한 내용입니다.</p>
<nav class="toc"><a href="#p1">1부 바로가기</a><a href="#p2">2부 바로가기</a></nav></header>
{''.join(parts)}
<footer>PJS 세미나(2026-11-14) 정리본</footer>
</main></body></html>'''
open('PJS-세미나-2026-11-14-정리.html','w',encoding='utf-8').write(html)
left = [n for n in NAMES if n in html]
print('남은 실명:', left, '| 크기', len(html))

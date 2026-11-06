# -*- coding: utf-8 -*-
"""
숏폼 영상별 배포 자료(PDF 4개)를 원본 하나에서 뽑아내는 스크립트.

- 원본: 셀러-AI직원-세팅-전자책.html (전체판, 모든 장이 들어 있음)
- 결과: 영상마다 HTML + PDF 한 쌍 (out/ 폴더)
- 문구를 고칠 땐 원본 HTML 이나 이 파일의 영상별 설정만 고치고 다시 돌린다.

실행:  ../../../.venv/bin/python build.py
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "셀러-AI직원-세팅-전자책.html"
OUT = HERE / "out"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


# ───────────────────────── 원본 쪼개기 ─────────────────────────
def load_parts():
    """원본 HTML 을 <!-- 장 이름 --> 주석 기준으로 쪼갠다."""
    html = SRC.read_text(encoding="utf-8")
    head = html.split("<body>")[0] + "<body>\n"
    body = html.split("<body>")[1].split("</body>")[0]
    parts = {}
    for m in re.finditer(r"<!-- (.+?) -->\n(.*?)(?=\n<!-- |\Z)", body, flags=re.S):
        parts[m.group(1).strip()] = m.group(2).strip()
    return head, parts


def section_inner(sec_html):
    """<section ...> 겉껍데기를 벗기고 안쪽만 돌려준다."""
    return re.sub(r"^<section[^>]*>\s*|\s*</section>\s*$", "", sec_html.strip())


def split_items(sec_html):
    """'<h3><span class="n">' 로 시작하는 번호 항목들을 잘라 리스트로 (앞부분, [항목들], 뒷부분)."""
    inner = section_inner(sec_html)
    pieces = re.split(r'(?=\n  <h3><span class="n">)', inner)
    intro = pieces[0]
    items = pieces[1:]
    tail = ""
    # 마지막 항목 뒤에 붙은 다크 카드(마무리 문구)는 따로 떼어 둔다
    if items and '<div class="card dark"' in items[-1]:
        last, sep, rest = items[-1].partition('\n  <div class="card dark"')
        items[-1] = last
        tail = sep + rest
    return intro, items, tail


def renumber(items):
    """번호 동그라미를 1부터 다시 매긴다."""
    out = []
    for i, it in enumerate(items, 1):
        out.append(re.sub(r'<span class="n">\d+</span>', f'<span class="n">{i}</span>', it, count=1))
    return out


def prompts(parts):
    """부록 지시문을 번호 → HTML 로."""
    found = re.findall(r'(<div class="prompt"><span class="lab">(\d\d) · (.*?)</span>(.*?)</div>)',
                       parts["부록"], flags=re.S)
    return {num: (title, body) for _, num, title, body in found}


# ───────────────────────── 조립 부품 ─────────────────────────
def cover(tag, title_html, lead, bullets):
    lis = "<br>\n    ".join("· " + b for b in bullets)
    return f"""<section class="cover">
  <div class="big">AI</div>
  <span class="tag">{tag}</span>
  <h1>{title_html}</h1>
  <p class="lead">{lead}</p>
  <div class="box">
    {lis}
  </div>
  <div class="who">용팀장 <span>구매대행 셀러 · 실전반 강사</span></div>
</section>"""


def chap(no, title, vid, inner):
    return f"""<section class="chap">
  <div class="chap-head">
    <div class="no">{no}</div>
    <h2>{title}</h2>
    <div class="vid">{vid}</div>
  </div>
{inner}
</section>"""


def first_chap(no, title, vid, inner):
    """표지 바로 다음 장 — 앞에 쪽 넘김을 또 넣지 않는다."""
    return chap(no, title, vid, inner).replace('<section class="chap">', '<section style="margin-top:7mm">', 1).replace(
        '<div class="chap-head">', '<div class="chap-head" style="break-inside:avoid;break-after:avoid">', 1)


def appendix(pr, nums, sub="○○ 부분만 내 상황에 맞게 바꿔서 붙여 넣으세요."):
    blocks = []
    for i, n in enumerate(nums, 1):
        title, body = pr[n]
        blocks.append(f'  <div class="prompt"><span class="lab">{i:02d} · {title}</span>{body}</div>')
    return chap("APPENDIX", f"복사해서 바로 쓰는<br>지시문 {len(nums)}개", sub, "\n\n".join(blocks))


def safety(parts):
    return parts["5장"].replace("(2장 2번)", "").replace(
        '<div class="no">CHAPTER 5</div>', '<div class="no">SAFETY</div>')


def end(parts):
    return parts["마지막"]


def apply(s, repl):
    for a, b in repl:
        if a not in s:
            print(f"  ⚠️ 바꿀 문구를 못 찾음: {a[:40]}")
        s = s.replace(a, b)
    return s


# ───────────────────────── 영상별 구성 ─────────────────────────
TOOLS_DETAIL = """
  <p>영상에서 "고수"로 분류한 작업 뒤에는 이 도구들이 있어요. 도구마다 <b>무엇을 맡기는지, 언제 쓰는지, 처음엔 어떻게 시작하는지</b>를 정리했습니다. 전부 한 번에 갖출 필요는 없어요. 위에서부터 하나씩 늘리면 됩니다.</p>

  <div class="card"><div class="lab">TOOL 1 · 클로드</div>
  <p><b>무엇을:</b> 대화로 묻고 판단하는 기본 창구예요. 고객 답장 초안, 상품 비교, 문구 다듬기.</p>
  <p><b>고수는 이렇게:</b> 그냥 묻지 않고 <b>근거 자료를 같이 넣어요.</b> 키워드 엑셀, 원본 상세페이지, 주문 내역을 붙이고 "이것만 근거로 답해"라고 합니다.</p>
  <p style="margin:0"><b>처음엔:</b> 설정 → 커넥터에서 지메일이나 구글 드라이브 하나만 연결해 보세요.</p></div>

  <div class="card"><div class="lab">TOOL 2 · 클로드 코드</div>
  <p><b>무엇을:</b> AI 직원들이 일하는 작업장이에요. 일하는 순서(스킬), 정해진 시간 작업(예약), 여러 명 동시 작업이 여기서 돌아갑니다.</p>
  <p><b>고수는 이렇게:</b> 같은 지시를 두 번 쓰지 않아요. 두 번째부터는 "스킬로 만들어 줘"라고 해서 순서를 저장합니다.</p>
  <p style="margin:0"><b>처음엔:</b> 매일 하는 일 하나(상품명, 옵션명 정리 등)를 골라 스킬 하나만 만들어 보세요.</p></div>

  <div class="card"><div class="lab">TOOL 3 · 어사이드 / Claude in Chrome (AI 브라우저)</div>
  <p><b>무엇을:</b> 사이트를 직접 열고 클릭하면서 검수, 비교, 조회를 해요. 상품 600개 검수가 10분이면 끝납니다.</p>
  <p><b>고수는 이렇게:</b> 지우기 같은 되돌릴 수 없는 일은 <b>표시만</b> 시키고, 결과를 본 다음 직접 실행해요.</p>
  <p style="margin:0"><b>처음엔:</b> 크롬 확장 프로그램 Claude in Chrome이 가장 쉬워요. 양이 많아지면 어사이드처럼 반복 작업에 강한 AI 브라우저로 넘어가세요.</p></div>

  <div class="card"><div class="lab">TOOL 4 · 키워드 엑셀</div>
  <p><b>무엇을:</b> 상품명과 키워드 판단의 근거 데이터예요. 키워드, 월간 검색수, 상품수가 들어 있어야 합니다.</p>
  <p><b>고수는 이렇게:</b> AI에게 "엑셀에 없는 단어는 쓰지 마"라고 못 박아요. 이 한 줄이 800위 밖 상품명과 검색되는 상품명을 가릅니다.</p>
  <p style="margin:0"><b>구하는 곳:</b> 네이버 검색광고 키워드 도구, 또는 키워드 분석 서비스. 저는 셀러라이프 엑셀을 씁니다.</p></div>

  <div class="card"><div class="lab">TOOL 5 · 수집 솔루션</div>
  <p><b>무엇을:</b> 타오바오 상품 수집과 마켓 전송. AI 직원이 여기에 연결돼 상품명, 썸네일, 상세페이지를 바꿉니다. 저는 불사자를 써요.</p>
  <p><b>고수는 이렇게:</b> 솔루션이 잡아 준 카테고리와 태그를 <b>그대로 믿지 않아요.</b> 카테고리는 네이버 가격비교 기준으로, 태그는 네이버 태그 사전의 공식 태그로 다시 맞춥니다.</p></div>
"""

CATEGORY_PROMPT = ("카테고리 확인",
                   "<br>\n  이 상품(썸네일 첨부)과 같은 상품이 네이버 가격비교에서 어느 카테고리에 가장 많이 있는지 확인해서, "
                   "카테고리 경로 후보를 3개까지 알려 줘. 각 후보에 근거가 된 검색어와 상품 수를 같이 적고, "
                   "확실하지 않으면 확실하지 않다고 말해 줘. 바꾸지는 말고 후보만.")


def build_all():
    head, parts = load_parts()
    pr = prompts(parts)
    pr["C1"] = CATEGORY_PROMPT
    ch2_intro, ch2_items, ch2_tail = split_items(parts["2장"])
    files = []

    # ① 고수 대 하수 → "고수들이 쓰는 AI 툴 정리 자료"
    ch3 = section_inner(parts["3장"])
    ch3 = ch3.split('\n  <h3>고수들이 쓰는 AI 도구</h3>')[0]   # 도구 표는 아래 상세판으로 대체
    ch3 = re.sub(r'^\s*<div class="chap-head">.*?</div>\n  </div>\n', "", ch3, flags=re.S)
    ch3 = apply(ch3, [
        ('<br><span class="go">→ 만드는 법은 4장</span>', ""),
        ("(2장 4번)", "(부록 지시문 1)"),
        ('<br><span class="go">→ 쓰는 법은 2장 5번</span>', '<br><span class="go">→ 쓰는 법은 다음 장 TOOL 3</span>'),
    ])
    a = [
        cover("셀러 AI 작업법 · 고수 대 하수", "고수 셀러가<br>쓰는<br><em>AI 툴 정리</em>",
              "같은 AI를 써도 결과가 다른 이유.<br>하수 방식 대신 고수 방식으로.",
              ["작업법 6가지, 하수 대 고수", "고수들이 쓰는 AI 도구 5가지", "도구별 처음 시작하는 법",
               "사고 안 나는 안전 규칙", "복사해서 쓰는 지시문 4개"]),
        first_chap("PART 1", "셀러 AI 작업법,<br>하수 대 고수", "영상 「셀러 AI 작업법, 고수 대 하수」의 정리본", ch3),
        first_chap("PART 2", "고수들이 쓰는<br>AI 도구 5가지", "제가 실제로 매일 쓰는 조합이에요.",
             TOOLS_DETAIL + """
  <div class="card dark" style="margin-top:4mm">
    <p style="margin:0;font-size:12pt;font-weight:800">판단은 내가 하고, 일은 AI에게 시킵니다.</p>
    <p style="margin:1.5mm 0 0;font-size:9.2pt;opacity:.9">하수와 고수의 차이는 도구가 아니라 이 구분이에요. 하수는 판단까지 AI에게 넘기고, 고수는 반복만 넘깁니다.</p>
  </div>"""),
        safety(parts),
        appendix(pr, ["06", "C1", "07", "08"]),
        end(parts),
    ]
    files.append(("01_고수대하수_고수들이-쓰는-AI툴-정리", "고수 셀러가 쓰는 AI 툴 정리 — 용팀장", a))

    # ② 반복 작업 → "AI 직원 세팅 전자책"
    ch4 = section_inner(parts["4장"])
    ch4 = re.sub(r'^\s*<div class="chap-head">.*?</div>\n  </div>\n', "", ch4, flags=re.S)
    ch4 = apply(ch4, [
        ("2장의 다섯 가지를 했다면 재료는 이미 다 있어요.", "재료 만드는 법은 바로 다음 장에 있어요."),
        ("(2장 1번 지시문)", "(PART 2의 1번)"),
    ])
    prep = renumber([ch2_items[0], ch2_items[1], ch2_items[4]])
    b = [
        cover("스마트스토어 반복 작업 · AI 직원", "AI 직원<br><em>세팅 전자책</em>",
              "타오바오 링크만 주면 수집부터 상세까지.<br>자는 동안 일하는 AI 직원 만들기.",
              ["AI 직원 네 명이 동시에 일하는 구조", "직원 한 명 만드는 5단계", "제 AI 직원의 하루 일과",
               "재료 3가지: 스킬 · 예약 작업 · AI 브라우저", "안전 규칙 · 복사해서 쓰는 지시문 5개"]),
        first_chap("PART 1", "AI 직원 만들기와<br>하루 일과",
                   "영상 「스마트스토어 반복 작업, 이제 클로드 AI 직원이 합니다」의 세팅 방법", ch4),
        first_chap("PART 2", "AI 직원의 재료<br>3가지", "스킬은 일하는 순서, 예약은 출근 시간, AI 브라우저는 손과 발이에요.",
             "\n".join(prep)),
        safety(parts),
        appendix(pr, ["02", "03", "04", "08", "07"]),
        end(parts),
    ]
    files.append(("02_반복작업_AI직원-세팅-전자책", "AI 직원 세팅 전자책 — 용팀장", b))

    # ③ 레벨 3단계 → "AI 직원 세팅 전자책"
    ch1 = section_inner(parts["1장"])
    ch1 = re.sub(r'^\s*<div class="chap-head">.*?</div>\n  </div>\n', "", ch1, flags=re.S)
    ch1 = apply(ch1, [
        ("2장의 <b>3번(메일 연결)</b>부터 하세요.", "PART 2의 <b>레벨 2 세팅(메일 연결)</b>부터 하세요."),
        ("2장의 <b>1번(스킬)</b>과 4장(AI 직원)으로 가세요.", "PART 2의 <b>레벨 3 세팅</b>으로 가세요."),
        ("5장 안전 규칙으로 사고만 막으면 됩니다.", "뒤쪽 안전 규칙으로 사고만 막으면 됩니다."),
        ("(2장 1번, 4장)", "(PART 2)"),
        ("(2장 2번, 5장)", "(PART 2, 안전 규칙)"),
    ])
    lv_mail = renumber([ch2_items[2]])[0].replace('<span class="n">1</span>메일을 연결하세요',
                                                   '<span class="n">2</span>레벨 2 세팅 — 메일을 연결하세요')
    lv_skill = renumber([ch2_items[0]])[0].replace('<span class="n">1</span>내 기준을 스킬로 만드세요',
                                                    '<span class="n">3</span>레벨 3 세팅 — 내 기준을 스킬로 만드세요')
    title1, body1 = pr["01"]
    lv1 = f"""
  <h3><span class="n">1</span>레벨 1을 제대로 — 묻는 법부터 바꾸세요</h3>
  <p>레벨 1에 머물러도 <b>묻는 법</b>만 바꾸면 결과가 확 달라져요. 그냥 "뭐라고 답하지?"가 아니라, 내 상황과 지켜야 할 선을 같이 줍니다. 특히 배송 기간이나 교환·반품처럼 <b>AI가 모르는 사실은 지어내지 말라고</b> 못 박으세요.</p>
  <div class="prompt"><span class="lab">이렇게 물으세요</span>{body1}</div>"""
    grid = re.search(r'  <h3>AI 직원 네 명이 동시에 일하는 구조</h3>.*?<p class="sub">.*?</p>', ch4, flags=re.S).group(0)
    c = [
        cover("셀러 AI 활용 레벨 3단계", "AI 직원<br><em>세팅 전자책</em>",
              "GPT에 묻고 복사하는 레벨 1에서<br>AI 직원을 부리는 레벨 3까지.",
              ["셀러 AI 레벨 3단계와 3분 자가진단", "MCP, 쉽게 말하면", "레벨별 첫 세팅: 묻는 법 · 메일 연결 · 스킬",
               "AI 직원 네 명이 동시에 일하는 구조", "안전 규칙 · 복사해서 쓰는 지시문 5개"]),
        first_chap("PART 1", "셀러 AI 레벨 3단계<br>— 나는 어디쯤인가", "영상 「셀러 AI 활용 레벨 3단계」의 정리본", ch1),
        first_chap("PART 2", "레벨별<br>첫 세팅", "한 레벨씩 올라가는 데 필요한 세팅 하나씩.",
             lv1 + "\n" + lv_mail + "\n" + lv_skill + '\n<div style="break-inside:avoid">' + grid + "</div>"),
        safety(parts),
        appendix(pr, ["01", "05", "02", "03", "04"]),
        end(parts),
    ]
    files.append(("03_레벨3단계_AI직원-세팅-전자책", "AI 직원 세팅 전자책 (레벨 3단계) — 용팀장", c))

    # ④ 다섯 가지 → "다섯 가지 PDF"
    ch2 = re.sub(r'^\s*<div class="chap-head">.*?</div>\n  </div>\n', "", section_inner(parts["2장"]), flags=re.S)
    ch2 = apply(ch2, [("확인 습관은 5장에 정리했습니다.", "확인 습관은 뒤쪽 안전 규칙에 정리했습니다.")])
    d = [
        cover("클로드 처음 쓰는 셀러", "클로드<br>첫 세팅<br><em>다섯 가지</em>",
              "뭐부터 해야 할지 막막할 때,<br>이 순서대로 하나씩.",
              ["스킬 · 예약 작업 · 메일 연결", "검색 데이터 · AI 브라우저", "항목마다 그대로 쓰는 첫 지시문",
               "사고 안 나는 안전 규칙", "복사해서 쓰는 지시문 6개"]),
        first_chap("FIVE SETUPS", "클로드 처음 쓰면<br>세팅할 다섯 가지",
                   "영상 「클로드 처음 쓰는 셀러, 이 다섯 가지부터 세팅하세요」의 정리본", ch2),
        safety(parts),
        appendix(pr, ["02", "03", "04", "05", "06", "01"]),
        end(parts),
    ]
    files.append(("04_첫세팅-다섯가지", "클로드 첫 세팅 다섯 가지 — 용팀장", d))

    # ── 쓰기 + PDF 변환 ──
    OUT.mkdir(exist_ok=True)
    for name, title, blocks in files:
        try:
            h = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", head)
            html = h + "\n\n".join(blocks) + "\n</body>\n</html>\n"
            hp = OUT / f"{name}.html"
            pp = OUT / f"{name}.pdf"
            hp.write_text(html, encoding="utf-8")
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={pp}", hp.as_uri()],
                           check=True, capture_output=True, timeout=120)
            pages = subprocess.run(["pdfinfo", str(pp)], capture_output=True, text=True).stdout
            n = re.search(r"Pages:\s+(\d+)", pages)
            print(f"✅ {pp.name}  ({n.group(1) if n else '?'}쪽)")
        except Exception as e:  # 한 파일이 실패해도 나머지는 계속
            print(f"❌ {name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        build_all()
    except Exception as e:
        print(f"❌ 빌드 실패: {e}", file=sys.stderr)
        sys.exit(1)

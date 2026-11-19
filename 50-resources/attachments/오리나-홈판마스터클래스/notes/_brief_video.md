# 영상 화면 확인 지시서 (전자책에 없는 15~23장)

## 목표
1차 노트(`notes/G6.md`, `notes/G7.md`)의 "화면 확인 필요 구간"을 실제 영상 화면으로 확인해 노트에 채운다. 자막만으로 모르는 정보(사이트 이름·주소, 메뉴 경로, 버튼 위치, 설정값, 화면 속 표·목록, GPT 출력 형식, 템플릿 문장, 썸네일 문구)를 글로 옮기는 것이 목적.

## 브라우저 사용법 (Claude in Chrome 도구)
- 도구가 지연 로드 상태면 ToolSearch 로 한 번에 불러라: `select:mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__browser_batch,mcp__claude-in-chrome__find`
- 탭 번호 **1151967713** 하나만 쓴다(새 탭 만들지 마라). 이미 프레스런에 로그인돼 있다.
- 강의 페이지 주소: `https://presslearn.co.kr/courses/797/lessons/<강의번호>` — 강의번호는 각 노트 머리의 "강의번호"(transcripts/NNN_*.md 2번째 줄에도 있음).
- 페이지를 연 뒤 아래 자바스크립트를 실행하면 영상이 원하는 초로 이동해 멈춘다. 그다음 `computer` screenshot 으로 본다(작은 글씨는 `zoom` 으로 영상 영역 확대).
```js
await new Promise(r=>setTimeout(r,2500));
document.querySelectorAll('[role=dialog] button').forEach(b=>{if(/건너뛰기/.test(b.textContent)) b.click()});
window.__seek=async(sec)=>{const f=[...document.querySelectorAll('iframe')].find(i=>/vimeo/.test(i.src)); const w=f.contentWindow; const send=(m,v)=>w.postMessage(JSON.stringify(v===undefined?{method:m}:{method:m,value:v}),'*'); send('setVolume',0); send('play'); await new Promise(r=>setTimeout(r,1200)); send('pause'); send('setCurrentTime',sec); await new Promise(r=>setTimeout(r,1800)); return 'ok';};
await window.__seek(133)   // 2분13초
```
- 같은 페이지에서 다른 시각은 `await window.__seek(초)` 만 다시 부르면 된다. 여러 시각은 browser_batch 로 [seek → screenshot] 을 묶어라.
- 오른쪽 "강의노트" 칸에 첨부 링크 이름이 보이면 그것도 적어라(누르지는 마라).
- 금지: 댓글·리뷰 작성, 완료 처리 버튼, 외부 링크 클릭, 파일 내려받기, 영상 소리 켜기.

## 무엇을 볼지
1. 노트의 "화면 확인 필요 구간" 각 항목: 그 시각과 범위 안을 15~30초 간격으로 2~4장.
2. 시연(도구 조작·사이트 화면)이 긴 강의는 범위 밖도 1분 간격으로 훑어 새 정보가 있으면 추가.
3. 수익 인증 캡처는 금액·기간 한 줄만.

## 기록
- 해당 강의 항목의 "화면 확인 필요 구간" 아래에 `→ 확인:` 으로 본 내용을 적는다. 새로 알게 된 실행 정보는 "핵심 내용"이나 "실행 체크리스트"에도 넣는다. 끝에 `(영상 mm:ss)` 표시.
- 화면에서도 안 보이면 "화면에도 안 보임".
- 다 끝나면 최종 답변으로 "고친 파일, 본 화면 수, 새로 얻은 핵심 5~10개, 남은 미확인"만 짧게.

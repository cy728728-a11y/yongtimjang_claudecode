/* 국기 원정대 공용 데이터: 대륙 6개 + 나라 105개
   tier = 지도 퀴즈 단계(1 큰·유명 나라 → 3 작은 나라), hint = 지도 위치 설명 한 줄 */
(function (root) {
  "use strict";

  var CONTINENTS = [
    {key:"europe",   name:"유럽",       icon:"🏰", count:25},
    {key:"africa",   name:"아프리카",   icon:"🦁", count:21},
    {key:"asia",     name:"아시아",     icon:"🏯", count:31},
    {key:"oceania",  name:"오세아니아", icon:"🏝️", count:6},
    {key:"namerica", name:"북아메리카", icon:"🗽", count:12},
    {key:"samerica", name:"남아메리카", icon:"⛰️", count:10}
  ];

  var COUNTRIES = [
    // 유럽 25
    {flag:"🇬🇧", name:"영국", capital:"런던", continent:"europe", landmark:"빅벤(엘리자베스 타워)", tier:1, hint:"유럽 서북쪽 바다 위 섬나라, 프랑스 위쪽"},
    {flag:"🇫🇷", name:"프랑스", capital:"파리", continent:"europe", landmark:"에펠탑", tier:1, hint:"유럽 서쪽, 스페인 바로 위"},
    {flag:"🇩🇪", name:"독일", capital:"베를린", continent:"europe", landmark:"쾰른 대성당", tier:1, hint:"유럽 한가운데, 프랑스 오른쪽"},
    {flag:"🇮🇹", name:"이탈리아", capital:"로마", continent:"europe", landmark:"콜로세움", tier:1, hint:"유럽 남쪽, 장화 모양으로 바다에 뻗은 나라"},
    {flag:"🇪🇸", name:"스페인", capital:"마드리드", continent:"europe", landmark:"세비아 대성당", tier:1, hint:"유럽 서남쪽 끝, 프랑스 바로 아래"},
    {flag:"🇵🇹", name:"포르투갈", capital:"리스본", continent:"europe", tier:2, hint:"유럽 서쪽 끝, 스페인 왼쪽 옆"},
    {flag:"🇳🇱", name:"네덜란드", capital:"암스테르담", continent:"europe", landmark:"잔세스칸스", tier:2, hint:"유럽 서북쪽 바닷가, 독일 왼쪽"},
    {flag:"🇧🇪", name:"벨기에", capital:"브뤼셀", continent:"europe", tier:3, hint:"프랑스 위, 네덜란드 아래 작은 나라"},
    {flag:"🇨🇭", name:"스위스", capital:"베른", continent:"europe", landmark:"그로스뮌스터 대성당", tier:2, hint:"알프스산맥 나라, 이탈리아 바로 위"},
    {flag:"🇦🇹", name:"오스트리아", capital:"빈", continent:"europe", landmark:"슈테판 대성당", tier:2, hint:"유럽 가운데, 독일 아래 스위스 오른쪽"},
    {flag:"🇸🇪", name:"스웨덴", capital:"스톡홀름", continent:"europe", landmark:"스톡홀름 왕궁", tier:2, hint:"유럽 북쪽 스칸디나비아반도, 노르웨이 오른쪽"},
    {flag:"🇳🇴", name:"노르웨이", capital:"오슬로", continent:"europe", tier:2, hint:"스칸디나비아반도 서쪽 바닷가로 길게 뻗은 나라"},
    {flag:"🇫🇮", name:"핀란드", capital:"헬싱키", continent:"europe", landmark:"헬싱키 대성당", tier:2, hint:"유럽 북쪽, 스웨덴 오른쪽 러시아 옆"},
    {flag:"🇩🇰", name:"덴마크", capital:"코펜하겐", continent:"europe", tier:3, hint:"독일 바로 위 작은 반도 나라"},
    {flag:"🇮🇸", name:"아이슬란드", capital:"레이캬비크", continent:"europe", tier:3, hint:"유럽 북서쪽 먼 바다, 북극 가까운 섬나라"},
    {flag:"🇵🇱", name:"폴란드", capital:"바르샤바", continent:"europe", landmark:"비엘리치카 소금 광산", tier:2, hint:"유럽 가운데, 독일 오른쪽"},
    {flag:"🇨🇿", name:"체코", capital:"프라하", continent:"europe", tier:3, hint:"독일 오른쪽, 폴란드 아래"},
    {flag:"🇭🇺", name:"헝가리", capital:"부다페스트", continent:"europe", landmark:"부다성", tier:3, hint:"유럽 가운데, 오스트리아 오른쪽"},
    {flag:"🇬🇷", name:"그리스", capital:"아테네", continent:"europe", landmark:"아크로폴리스", tier:1, hint:"유럽 동남쪽 끝, 바다로 뻗은 반도와 섬들"},
    {flag:"🇮🇪", name:"아일랜드", capital:"더블린", continent:"europe", tier:3, hint:"영국 왼쪽 옆 섬나라"},
    {flag:"🇷🇴", name:"루마니아", capital:"부쿠레슈티", continent:"europe", landmark:"브란성", tier:3, hint:"우크라이나 아래, 흑해 옆"},
    {flag:"🇭🇷", name:"크로아티아", capital:"자그레브", continent:"europe", tier:3, hint:"이탈리아 건너편 아드리아해 바닷가"},
    {flag:"🇷🇺", name:"러시아", capital:"모스크바", continent:"europe", landmark:"성 바실리 대성당", tier:1, hint:"유럽 동쪽부터 아시아까지 이어진 가장 큰 나라"},
    {flag:"🇺🇦", name:"우크라이나", capital:"키이우", continent:"europe", tier:2, hint:"유럽 동쪽, 러시아 왼쪽 흑해 위"},
    {flag:"🇹🇷", name:"튀르키예", capital:"앙카라", continent:"europe", landmark:"아야소피아 성당", tier:1, hint:"유럽과 아시아 사이, 흑해 아래"},

    // 아프리카 21
    {flag:"🇪🇬", name:"이집트", capital:"카이로", continent:"africa", landmark:"쿠푸 왕 피라미드", tier:1, hint:"아프리카 동북쪽 끝, 나일강이 흐르는 나라"},
    {flag:"🇿🇦", name:"남아프리카공화국", capital:"프리토리아", continent:"africa", landmark:"테이블 마운틴", tier:1, hint:"아프리카 맨 남쪽 끝"},
    {flag:"🇰🇪", name:"케냐", capital:"나이로비", continent:"africa", tier:1, hint:"아프리카 동쪽, 적도가 지나가는 나라"},
    {flag:"🇳🇬", name:"나이지리아", capital:"아부자", continent:"africa", tier:1, hint:"아프리카 서쪽, 기니만 바닷가"},
    {flag:"🇲🇦", name:"모로코", capital:"라바트", continent:"africa", tier:1, hint:"아프리카 서북쪽 끝, 스페인 바로 아래"},
    {flag:"🇩🇿", name:"알제리", capital:"알제", continent:"africa", tier:2, hint:"아프리카에서 가장 큰 나라, 모로코 오른쪽"},
    {flag:"🇪🇹", name:"에티오피아", capital:"아디스아바바", continent:"africa", tier:1, hint:"아프리카 동쪽 '뿔' 모양 땅 안쪽"},
    {flag:"🇬🇭", name:"가나", capital:"아크라", continent:"africa", tier:2, hint:"기니만 바닷가, 나이지리아 왼쪽"},
    {flag:"🇹🇿", name:"탄자니아", capital:"도도마", continent:"africa", landmark:"세렝게티 국립공원", tier:2, hint:"아프리카 동쪽, 케냐 바로 아래"},
    {flag:"🇹🇳", name:"튀니지", capital:"튀니스", continent:"africa", tier:3, hint:"아프리카 북쪽 끝, 알제리 오른쪽 작은 나라"},
    {flag:"🇱🇾", name:"리비아", capital:"트리폴리", continent:"africa", tier:2, hint:"아프리카 북쪽, 이집트 왼쪽"},
    {flag:"🇸🇩", name:"수단", capital:"하르툼", continent:"africa", tier:2, hint:"이집트 바로 아래"},
    {flag:"🇸🇳", name:"세네갈", capital:"다카르", continent:"africa", tier:3, hint:"아프리카 맨 서쪽 끝 바닷가"},
    {flag:"🇲🇬", name:"마다가스카르", capital:"안타나나리보", continent:"africa", tier:1, hint:"아프리카 동남쪽 바다의 큰 섬나라"},
    {flag:"🇿🇼", name:"짐바브웨", capital:"하라레", continent:"africa", tier:3, hint:"남아프리카공화국 위쪽"},
    {flag:"🇺🇬", name:"우간다", capital:"캄팔라", continent:"africa", tier:3, hint:"케냐 왼쪽, 빅토리아 호수 옆"},
    {flag:"🇨🇲", name:"카메룬", capital:"야운데", continent:"africa", tier:3, hint:"나이지리아 오른쪽"},
    {flag:"🇨🇮", name:"코트디부아르", capital:"야무수크로", continent:"africa", tier:3, hint:"기니만 바닷가, 가나 왼쪽"},
    {flag:"🇲🇿", name:"모잠비크", capital:"마푸투", continent:"africa", tier:3, hint:"아프리카 동남쪽 바닷가, 마다가스카르 건너편"},
    {flag:"🇿🇲", name:"잠비아", capital:"루사카", continent:"africa", landmark:"빅토리아 폭포", tier:3, hint:"짐바브웨 바로 위"},
    {flag:"🇨🇩", name:"콩고민주공화국", capital:"킨샤사", continent:"africa", tier:2, hint:"아프리카 한가운데, 콩고강이 흐르는 큰 나라"},

    // 아시아 31
    {flag:"🇰🇷", name:"대한민국", capital:"서울", continent:"asia", landmark:"N서울타워", tier:1, hint:"한반도 남쪽, 우리나라!"},
    {flag:"🇰🇵", name:"북한", capital:"평양", continent:"asia", tier:1, hint:"한반도 북쪽, 중국 바로 오른쪽"},
    {flag:"🇨🇳", name:"중국", capital:"베이징", continent:"asia", landmark:"만리장성", tier:1, hint:"아시아 동쪽의 아주 큰 나라, 한반도 왼쪽"},
    {flag:"🇯🇵", name:"일본", capital:"도쿄", continent:"asia", landmark:"히메지성", tier:1, hint:"한반도 오른쪽 바다 건너 섬나라"},
    {flag:"🇲🇳", name:"몽골", capital:"울란바토르", continent:"asia", tier:1, hint:"중국 바로 위, 러시아 아래 초원의 나라"},
    {flag:"🇻🇳", name:"베트남", capital:"하노이", continent:"asia", landmark:"하롱베이", tier:1, hint:"중국 아래 S자로 길쭉한 나라"},
    {flag:"🇹🇭", name:"태국", capital:"방콕", continent:"asia", landmark:"타이 왕궁", tier:1, hint:"동남아시아 가운데, 베트남 왼쪽"},
    {flag:"🇮🇩", name:"인도네시아", capital:"자카르타", continent:"asia", tier:2, hint:"동남아시아 적도 위 수많은 섬나라"},
    {flag:"🇲🇾", name:"말레이시아", capital:"쿠알라룸푸르", continent:"asia", tier:2, hint:"태국 아래 반도와 보르네오섬 북쪽"},
    {flag:"🇸🇬", name:"싱가포르", capital:"싱가포르", continent:"asia", landmark:"마리나 베이 샌즈", tier:2, hint:"말레이시아 바로 아래 아주 작은 섬나라"},
    {flag:"🇵🇭", name:"필리핀", capital:"마닐라", continent:"asia", landmark:"인트라무로스", tier:2, hint:"베트남 오른쪽 바다의 섬나라"},
    {flag:"🇲🇲", name:"미얀마", capital:"네피도", continent:"asia", tier:3, hint:"인도 오른쪽, 태국 왼쪽"},
    {flag:"🇰🇭", name:"캄보디아", capital:"프놈펜", continent:"asia", landmark:"앙코르와트", tier:3, hint:"태국 오른쪽 아래, 베트남 왼쪽"},
    {flag:"🇱🇦", name:"라오스", capital:"비엔티안", continent:"asia", tier:3, hint:"태국과 베트남 사이 바다 없는 나라"},
    {flag:"🇮🇳", name:"인도", capital:"뉴델리", continent:"asia", landmark:"타지마할", tier:1, hint:"아시아 남쪽, 바다로 뾰족하게 내려온 나라"},
    {flag:"🇵🇰", name:"파키스탄", capital:"이슬라마바드", continent:"asia", tier:2, hint:"인도 왼쪽"},
    {flag:"🇧🇩", name:"방글라데시", capital:"다카", continent:"asia", tier:3, hint:"인도 오른쪽, 인도에 거의 둘러싸인 나라"},
    {flag:"🇱🇰", name:"스리랑카", capital:"스리자야와르데네푸라코테", continent:"asia", tier:3, hint:"인도 바로 아래 눈물 모양 섬나라"},
    {flag:"🇳🇵", name:"네팔", capital:"카트만두", continent:"asia", landmark:"부다나트 스투파", tier:2, hint:"인도와 중국 사이 히말라야산맥 나라"},
    {flag:"🇧🇹", name:"부탄", capital:"팀부", continent:"asia", landmark:"파로 탁상 사원", tier:3, hint:"히말라야산맥, 네팔 오른쪽 작은 나라"},
    {flag:"🇸🇦", name:"사우디아라비아", capital:"리야드", continent:"asia", landmark:"카바 신전", tier:1, hint:"아시아 서쪽 아라비아반도의 대부분"},
    {flag:"🇦🇪", name:"아랍에미리트", capital:"아부다비", continent:"asia", landmark:"부르즈 할리파", tier:2, hint:"아라비아반도 동쪽, 사우디아라비아 오른쪽"},
    {flag:"🇮🇱", name:"이스라엘", capital:"예루살렘", continent:"asia", landmark:"바위 사원", tier:2, hint:"지중해 동쪽 바닷가, 이집트 오른쪽 위"},
    {flag:"🇮🇷", name:"이란", capital:"테헤란", continent:"asia", landmark:"반크 대성당", tier:2, hint:"아시아 서쪽, 이라크 오른쪽"},
    {flag:"🇮🇶", name:"이라크", capital:"바그다드", continent:"asia", tier:2, hint:"사우디아라비아 위, 이란 왼쪽"},
    {flag:"🇶🇦", name:"카타르", capital:"도하", continent:"asia", landmark:"어스파이어 타워", tier:3, hint:"아라비아반도 동쪽 바다로 튀어나온 작은 나라"},
    {flag:"🇰🇼", name:"쿠웨이트", capital:"쿠웨이트시티", continent:"asia", landmark:"쿠웨이트 타워", tier:3, hint:"이라크 바로 아래 작은 나라"},
    {flag:"🇯🇴", name:"요르단", capital:"암만", continent:"asia", tier:3, hint:"이스라엘 오른쪽"},
    {flag:"🇰🇿", name:"카자흐스탄", capital:"아스타나", continent:"asia", tier:2, hint:"아시아 가운데, 러시아 바로 아래 넓은 나라"},
    {flag:"🇺🇿", name:"우즈베키스탄", capital:"타슈켄트", continent:"asia", tier:3, hint:"카자흐스탄 바로 아래"},
    {flag:"🇾🇪", name:"예멘", capital:"사나", continent:"asia", tier:3, hint:"아라비아반도 남쪽 끝, 사우디아라비아 아래"},

    // 오세아니아 6
    {flag:"🇦🇺", name:"호주", capital:"캔버라", continent:"oceania", landmark:"시드니 오페라하우스", tier:1, hint:"남반구의 대륙만 한 나라, 인도네시아 아래"},
    {flag:"🇳🇿", name:"뉴질랜드", capital:"웰링턴", continent:"oceania", landmark:"통가리로 국립공원", tier:1, hint:"호주 오른쪽 아래 바다의 두 큰 섬"},
    {flag:"🇫🇯", name:"피지", capital:"수바", continent:"oceania", tier:2, hint:"호주 오른쪽 멀리 남태평양 섬나라"},
    {flag:"🇵🇬", name:"파푸아뉴기니", capital:"포트모르즈비", continent:"oceania", tier:2, hint:"호주 바로 위 뉴기니섬 오른쪽 절반"},
    {flag:"🇼🇸", name:"사모아", capital:"아피아", continent:"oceania", tier:3, hint:"피지 오른쪽 위 남태평양 작은 섬나라"},
    {flag:"🇹🇴", name:"통가", capital:"누쿠알로파", continent:"oceania", tier:3, hint:"피지 오른쪽 아래 남태평양 작은 섬나라"},

    // 북아메리카 12
    {flag:"🇺🇸", name:"미국", capital:"워싱턴 D.C.", continent:"namerica", landmark:"자유의 여신상", tier:1, hint:"북아메리카 가운데, 캐나다 아래"},
    {flag:"🇨🇦", name:"캐나다", capital:"오타와", continent:"namerica", landmark:"나이아가라 폭포", tier:1, hint:"미국 바로 위 아주 큰 나라"},
    {flag:"🇲🇽", name:"멕시코", capital:"멕시코시티", continent:"namerica", landmark:"치첸이트사", tier:1, hint:"미국 바로 아래"},
    {flag:"🇨🇺", name:"쿠바", capital:"아바나", continent:"namerica", tier:2, hint:"미국 플로리다 아래 길쭉한 섬나라"},
    {flag:"🇯🇲", name:"자메이카", capital:"킹스턴", continent:"namerica", tier:2, hint:"쿠바 바로 아래 카리브해 섬나라"},
    {flag:"🇵🇦", name:"파나마", capital:"파나마시티", continent:"namerica", tier:2, hint:"남아메리카로 이어지는 좁은 땅, 콜롬비아 위"},
    {flag:"🇨🇷", name:"코스타리카", capital:"산호세", continent:"namerica", tier:2, hint:"중앙아메리카, 파나마 왼쪽 위"},
    {flag:"🇬🇹", name:"과테말라", capital:"과테말라시티", continent:"namerica", tier:2, hint:"중앙아메리카, 멕시코 바로 아래"},
    {flag:"🇭🇳", name:"온두라스", capital:"테구시갈파", continent:"namerica", tier:3, hint:"중앙아메리카, 과테말라 오른쪽"},
    {flag:"🇭🇹", name:"아이티", capital:"포르토프랭스", continent:"namerica", tier:3, hint:"쿠바 오른쪽 섬의 왼쪽 절반"},
    {flag:"🇩🇴", name:"도미니카공화국", capital:"산토도밍고", continent:"namerica", tier:3, hint:"쿠바 오른쪽 섬의 오른쪽 절반"},
    {flag:"🇧🇸", name:"바하마", capital:"나소", continent:"namerica", tier:3, hint:"미국 플로리다 오른쪽 바다의 작은 섬들"},

    // 남아메리카 10
    {flag:"🇧🇷", name:"브라질", capital:"브라질리아", continent:"samerica", landmark:"코르코바도 예수상", tier:1, hint:"남아메리카 동쪽의 가장 큰 나라"},
    {flag:"🇦🇷", name:"아르헨티나", capital:"부에노스아이레스", continent:"samerica", landmark:"이구아수 폭포", tier:1, hint:"남아메리카 남쪽, 칠레 오른쪽 넓은 나라"},
    {flag:"🇨🇱", name:"칠레", capital:"산티아고", continent:"samerica", landmark:"모아이 석상", tier:1, hint:"남아메리카 서쪽 바닷가로 아주 길쭉한 나라"},
    {flag:"🇵🇪", name:"페루", capital:"리마", continent:"samerica", landmark:"마추픽추", tier:1, hint:"남아메리카 서쪽 바닷가, 브라질 왼쪽"},
    {flag:"🇨🇴", name:"콜롬비아", capital:"보고타", continent:"samerica", landmark:"라스 라하스 성당", tier:2, hint:"남아메리카 북서쪽 끝, 파나마 바로 아래"},
    {flag:"🇻🇪", name:"베네수엘라", capital:"카라카스", continent:"samerica", tier:2, hint:"남아메리카 북쪽 바닷가, 콜롬비아 오른쪽"},
    {flag:"🇪🇨", name:"에콰도르", capital:"키토", continent:"samerica", tier:3, hint:"적도가 지나가는 작은 나라, 콜롬비아 아래"},
    {flag:"🇧🇴", name:"볼리비아", capital:"라파스", continent:"samerica", landmark:"우유니 소금사막", tier:2, hint:"남아메리카 가운데 바다 없는 나라, 페루 오른쪽"},
    {flag:"🇵🇾", name:"파라과이", capital:"아순시온", continent:"samerica", tier:3, hint:"볼리비아 아래 바다 없는 나라"},
    {flag:"🇺🇾", name:"우루과이", capital:"몬테비데오", continent:"samerica", tier:3, hint:"브라질 아래, 아르헨티나 오른쪽 작은 나라"}
  ];

  // 국기 이모지 → ISO 2자리 소문자 (🇫🇷 → "fr")
  function isoOf(flag) {
    var cps = Array.from(flag);
    return String.fromCharCode(
      cps[0].codePointAt(0) - 0x1F1E6 + 97,
      cps[1].codePointAt(0) - 0x1F1E6 + 97
    );
  }
  COUNTRIES.forEach(function (c) { c.iso = isoOf(c.flag); });

  var api = { CONTINENTS: CONTINENTS, COUNTRIES: COUNTRIES, isoOf: isoOf };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MQData = api;
})(this);

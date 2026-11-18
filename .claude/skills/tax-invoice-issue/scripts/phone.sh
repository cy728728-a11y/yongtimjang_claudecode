#!/bin/bash
# 폰(USB 연결) 조작 도우미 — 전자세금계산서 발급 스킬용
# 사용법:
#   phone.sh check                 # 폰 연결 상태 확인
#   phone.sh cap <이름>            # 화면 캡처 → $OUT/<이름>.png (이미지는 1080x2340 원본 좌표)
#   phone.sh tap <x> <y>           # 원본 좌표로 탭
#   phone.sh swipe <x1> <y1> <x2> <y2> [ms]
#   phone.sh text <숫자·영문>      # 글자 입력 (한글 불가)
#   phone.sh clear [n]             # 입력칸 끝으로 가서 n글자 지우기 (기본 12)
#   phone.sh back                  # 뒤로(키보드 닫기)
#   phone.sh app hometax|kakao     # 앱 앞으로 띄우기
# 출력 폴더: 환경변수 OUT (없으면 ~/AppData/Local/Temp/tax-invoice)

export MSYS_NO_PATHCONV=1   # Git Bash 경로 자동변환 끄기 (/sdcard 깨짐 방지)
ADB="${ADB:-$USERPROFILE/tools/scrcpy-win64-v5.0.1/adb.exe}"
OUT="${OUT:-$USERPROFILE/AppData/Local/Temp/tax-invoice}"
mkdir -p "$OUT"

if [ ! -f "$ADB" ]; then
  echo "오류: adb 없음 ($ADB). scrcpy 압축본을 ~/tools 에 풀어야 함" >&2
  exit 2
fi

cmd="$1"; shift
case "$cmd" in
  check)
    "$ADB" devices -l ;;
  cap)
    "$ADB" exec-out screencap -p > "$OUT/$1.png" && echo "$OUT/$1.png" ;;
  tap)
    "$ADB" shell input tap "$1" "$2" ;;
  swipe)
    "$ADB" shell input swipe "$1" "$2" "$3" "$4" "${5:-400}" ;;
  text)
    "$ADB" shell input text "$1" ;;
  clear)
    n="${1:-12}"
    "$ADB" shell input keyevent KEYCODE_MOVE_END
    for i in $(seq 1 "$n"); do "$ADB" shell input keyevent KEYCODE_DEL; done ;;
  back)
    "$ADB" shell input keyevent KEYCODE_BACK ;;
  app)
    case "$1" in
      hometax) pkg=kr.go.nts.android ;;
      kakao)   pkg=com.kakao.talk ;;
      *)       pkg="$1" ;;
    esac
    "$ADB" shell monkey -p "$pkg" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 ;;
  *)
    echo "알 수 없는 명령: $cmd" >&2; exit 1 ;;
esac

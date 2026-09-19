# Tailscale

> **관련**: [[불사자-자동화]] · [[CS-자동화]]
> **Facets**: 원격접속 · VPN · 기기연동 · 맥실버 · 블랙노트북

## 핵심 (현재 아는 것의 요약)

Tailscale 은 흩어진 기기를 인터넷 어디서든 같은 LAN 안에 있는 것처럼 묶어주는 가상 사설망이다.
공유기 포트포워딩·고정IP·DDNS 가 필요 없고, 기기 이름만으로 서로를 찾는다.
2026-09-19 블랙노트북(윈도우)과 맥실버(MacBook Air) 연동 완료.

**핵심 가치**: 맥실버를 집에 두는 상시 서버로 쓰고, 밖에서 블랙노트북으로 붙어 작업·확인하는 구조가 가능해진다.

## 근거 (소스별 증거)

### 구성 결과 (2026-09-19, 실측)

| 기기 | Tailscale 이름 | 주소 | OS |
|------|---------------|------|-----|
| 블랙노트북 | notebook-black | 100.115.105.14 | Windows 11 |
| 맥실버 | macbookair | 100.95.62.13 | macOS |

- 계정: cy728728@gmail.com (두 기기 동일 계정이어야 묶임)
- MagicDNS 도메인: macbookair.tail82845a.ts.net
- 맥 로컬 사용자명: choiyongsmacbook
- 실측 지연: 최초 DERP(도쿄) 중계 80ms → 직통 P2P 전환 후 10ms
- 열린 포트(테일넷 경유 확인): 22(원격 로그인), 5900(화면 공유)
  [source: 카페에서 원격 설치 세션, 2026-09-19]

### macOS 설치 시 함정 (실제로 막혔던 지점)

1. **앱스토어 버전 말고 tailscale.com 직접 다운로드본을 쓴다.**
   번들ID `io.tailscale.ipn.macsys`. 앱스토어 버전은 사용자 로그인 세션에 묶여 상시 서버용으로 부적합.
2. **네트워크 확장 토글이 꺼져 있으면 로그인은 되는데 연결이 안 된다.**
   증상: 관리 콘솔에 기기는 등록되는데 계속 offline, 앱은 Not Connected, Reconnect 눌러도 즉시 꺼짐.
   진단: 맥 터미널에서 `systemextensionsctl list` → `[activated disabled]` 이면 이 경우.
   위치: 시스템 설정 → 일반 → 로그인 항목 및 확장 프로그램 → 네트워크 확장 ⓘ → Tailscale 토글 ON.
   ※ 개인정보 보호 및 보안 화면이 아니다. 최신 macOS 는 네트워크 확장을 별도 관리한다.
3. **토글을 켜도 시스템 설정 UI 가 갱신되지 않는다.** 그림은 꺼진 채로 남지만 실제로는 연결된다.
   화면 말고 `tailscale status` / `tailscale ping <기기명>` 으로 판정할 것.
   [source: 원격 설치 세션 실측, 2026-09-19]

### 닭과 달걀 문제

Tailscale 자체가 원격 통로를 만드는 도구이므로, 대상 기기에 설치하려면 **별도의 기존 원격 수단이 이미 있어야** 한다.
이번엔 크롬 원격 데스크톱이 이미 깔려 있어 카페에서 원격 설치가 가능했다.
없었다면 집에 가서 직접 해야 했다.
[source: 2026-09-19]

### FileVault 주의

맥실버는 FileVault 켜짐. 재부팅하면 부팅 직후 잠금 화면에서 **물리적으로** 비밀번호를 넣어야 열린다.
크롬 원격 데스크톱은 로그인 이전 화면에 접근 불가 → 원격 작업 중 재부팅은 곧 접근 상실.
Tailscale 설치 자체는 재부팅 불필요.
[source: 2026-09-19]

### 맥실버 서버화 (2026-09-19)

노트북에서 맥실버를 원격 작업 서버로 쓰기 위한 구성. 목표는 Claude Code 를 맥에서 돌리고 노트북은 터미널로만 쓰는 것.

**노트북 → 맥 무암호 접속**
- 노트북에 ed25519 키 생성, 공개키를 맥 `~/.ssh/authorized_keys` 에 등록
- `~/.ssh/config` 에 별칭 `mac` 등록 → `ssh mac` 한 줄로 접속
- 함정: Claude Code 의 `!` 실행은 TTY 가 아니라 비밀번호 입력이 불가능하다.
  키 등록은 크롬 원격 데스크톱으로 맥 터미널에서 직접 하는 게 확실하다.
- 함정: 원격 데스크톱 경유 붙여넣기가 `^[[200~` 로 깨진다.
  맥 터미널에서 `unset zle_bracketed_paste` 를 손으로 친 뒤 붙여넣을 것.

**맥 환경 실측**

| 항목 | 상태 |
|------|------|
| macOS | 26.5.1 / arm64 |
| git | 있음 (Apple Git 2.50.1) |
| python3 | 3.9.6 (시스템 기본) |
| Homebrew / node / tmux | 없음 |
| screen | 있음 (`/usr/bin/screen`, 동작 검증 완료) |
| 디스크 여유 | 786GB |

**[!correction] 맥에는 이미 작업 환경이 있었다 (2026-09-19 확인)**

처음엔 맥이 빈 상태인 줄 알고 `~/workspace` 에 새로 clone 했으나, 실제로는 기존 환경이 이미 완비돼 있었다.
중복본은 삭제함. **실제 워크스페이스 경로는 `~/Documents/yongtimjang_claudecode` 다.**

| 항목 | 상태 |
|------|------|
| 워크스페이스 | `~/Documents/yongtimjang_claudecode` (main, trust 승인됨) |
| 가상환경 | `.venv` / Python 3.12.13 |
| 환경변수 | `.env` 있음 |
| MCP 서버 | 전역 등록 `aside`, `bulsaja` |
| 기타 | `~/bulsaja-kit`, `~/python_work/data` |

즉 **파이썬·API키·MCP 이식(3단계)은 애초에 필요 없었다.** 맥은 원래 작업 머신이었다.
이번 세션에서 새로 한 건 Claude Code 최신 설치와 노트북→맥 무암호 SSH 연결뿐이다.

**진짜 남은 구멍: 맥에 GitHub push 자격증명이 없다.**
- 증상: 맥에서 `git push` 시 `fatal: unable to get password from user`
- 실제 사고: 2026-09-15 커밋 하나가 나흘간 맥에만 갇혀 있었다
- 이번 임시 조치: 노트북에서 맥을 git 원격으로 직접 fetch 해 구조 후 노트북에서 push
  `git fetch ssh://choiyongsmacbook@100.95.62.13/Users/choiyongsmacbook/Documents/yongtimjang_claudecode main`
- 근본 해결(미착수): 맥에 `credential.helper osxkeychain` + GitHub 토큰 등록, 또는 리모트를 SSH 방식으로 전환

**세션 유지**: tmux 없음, macOS 기본 `screen` 사용 (동작 검증 완료)

[source: 원격 서버화 세션 실측, 2026-09-19]

## 적용 (내 맥락에서 실제 사용)

| 용도 | 방법 |
|------|------|
| 맥 터미널 접속 | `ssh choiyongsmacbook@macbookair` |
| 맥 화면 제어 | 원격 데스크톱/VNC 로 `macbookair` 또는 100.95.62.13 |
| 파일 주고받기 | Taildrop — 파일 우클릭 → Tailscale 로 보내기 |
| 연결 확인 | 노트북에서 `tailscale status`, `tailscale ping macbookair` |
| 맥에서 작업 | `ssh mac` → `screen -R work` → `cd ~/Documents/yongtimjang_claudecode && claude` |

**운용 전제**: 맥실버는 전원 연결 + 잠자기 방지 ON 상태로 집에 상주.
잠들면 밖에서 못 붙는다.

**역할 분담 구상**: 파일 동기화는 git-sync 가, 원격 실행은 Tailscale 이 담당.
불사자 자동화·CS 자동화 스크립트를 맥실버에서 상시 구동하고 밖에서 결과만 확인하는 형태.

## Open Questions

- 맥실버를 실제 상시 구동 서버로 쓸 것인가, 아니면 필요할 때만 붙는 용도인가
- 잠자기 방지 설정이 실제로 장시간(며칠) 유지되는지 미검증
- 휴대폰에도 설치해 3대 체제로 갈지
- exit node 기능을 쓸 일이 있는지 (현재 미사용, 원격 세션 끊길 위험 있어 보류)

## Related

- [[불사자-자동화]] — 맥실버 상시 구동 대상 후보
- [[CS-자동화]] — 로컬 실행 전제 프로젝트, 원격 접근 필요

---
Sources: 원격 설치 세션 실측 로그 (2026-09-19)
Last enriched: 2026-09-19 (2회)

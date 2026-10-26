## 책갈피 툴 – TXT를 EPUB으로 v0.2.1

「의견 보내기」 링크를 더한 버전입니다. 변환 동작은 v0.2.0과 같습니다.

### 새로 더한 것
- **의견 보내기.** 창 위쪽 오른편(「새 버전 확인」 체크 왼쪽)의 **의견 보내기** 링크를 누르면 브라우저에서 책갈피 툴 페이지의 의견 칸(`https://chaekgalpi.co.kr/tools/txttoepub#feedback`)이 열립니다. 로그인 없이 안 되는 것·불편한 것·바라는 기능을 보낼 수 있습니다. 화면 언어가 English·日本語·简体中文이면 영어 페이지(`/en/tools/txttoepub`)가 열립니다(일본어·중국어 페이지는 없습니다).
- 프로그램은 페이지를 열기만 하고 아무것도 보내지 않습니다. 주소에는 프로그램에서 열었다는 표시(`utm_source=app&utm_medium=feedback`)와 버전(`v=0.2.1`)만 붙습니다.
- 브라우저가 열리지 않으면 프로그램은 그대로 두고, 주소를 기록 칸과 안내 창에 보여 줍니다(안내 창에서 Ctrl+C로 복사).
- 화면 문구 4개 언어(의견 보내기 / Send feedback / ご意見を送る / 发送反馈). README 4개 언어에 「의견 보내기」 절(GitHub Issues도 그대로 받음).

### 확인한 것
- 시험 354개 + 서브테스트 1011개 통과(새 시험 `tests/test_feedback.py` 122개 — 4개 언어 주소 정확한 문자열, 알 수 없는 언어·None → 한국어 주소, 언어 코드 대소문자, 이상한 버전 값 15가지(공백·`&`·`#`·한글·`+`·`%`)를 넣어도 다시 읽으면 원래 값, 빈 버전은 `v` 생략, 클릭 = 브라우저 1번, 실행 중 언어를 바꾸면 다음 주소도 바뀜, 브라우저 실패 5가지(False·None·`webbrowser.Error`·`OSError`·그 밖의 예외) × 4개 언어에서 창이 그대로이고 주소 안내, 4개 언어 문구, 명령줄 `--help` 그대로, 새 버전 확인 그대로, 모든 시험에서 소켓·urlopen 0건). 시험은 실제 브라우저를 열지 않고 네트워크에 나가지 않습니다.
- exe를 임시 폴더에서 죽은 프록시 환경으로 띄워 창이 뜨고 닫히는 것을 확인(링크는 누르지 않음). 캡처 `docs/feedback_link.png`.

### 파일
- `txt-to-epub.exe` (31.8 MB, Windows 10/11 64비트)
- SHA-256: `16134d495b8634a54091e43dbd5dd1317af8649771bab4a014898319c278cdd9`
- 소스 실행: `pip install -r requirements.txt` → `python main.py`

---

## Chaekgalpi Tools – TXT to EPUB v0.2.1

Adds a "Send feedback" link. Conversion works as in v0.2.0.

### New
- **Send feedback.** The **Send feedback** link at the top right (left of "Check for updates") opens the feedback box of the tool's page in your browser: `https://chaekgalpi.co.kr/en/tools/txttoepub#feedback` for English, Japanese and Chinese screens, the Korean page for a Korean screen. No sign-in needed.
- The program only opens the page; it sends nothing itself. The address carries only where it was opened from (`utm_source=app&utm_medium=feedback`) and the version (`v=0.2.1`).
- When no browser opens, the program carries on and shows the address in the log and in a message box (Ctrl+C copies it).
- Strings in four languages; the README in four languages gains a "Send feedback" section (GitHub Issues are still welcome).

### Checked
- 354 tests + 1011 subtests pass (122 new in `tests/test_feedback.py`: exact addresses, odd versions read back unchanged, one browser call per click, language switch, five browser failures in four languages, strings, CLI help and the update check unchanged, zero socket/urlopen calls). No test opens a real browser or reaches the network.
- The exe was started from a scratch folder behind a dead proxy: the window opens and closes.

### Files
- `txt-to-epub.exe` (31.8 MB, Windows 10/11 64-bit)
- SHA-256: `16134d495b8634a54091e43dbd5dd1317af8649771bab4a014898319c278cdd9`
- From source: `pip install -r requirements.txt` → `python main.py`

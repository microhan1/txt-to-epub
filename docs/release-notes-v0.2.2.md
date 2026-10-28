## 책갈피 툴 – TXT를 EPUB으로 v0.2.2

「의견 보내기」 링크를 키보드와 마우스 올림 설명으로 다듬은 버전입니다. 변환 동작은 v0.2.1과 같습니다.

### 바뀐 것
- **키보드로도 누를 수 있습니다.** Tab으로 「의견 보내기」에 가면 테두리가 보이고, Enter·Space로 엽니다. 테두리는 늘 자리를 잡고 있어 초점이 와도 크기가 바뀌지 않습니다.
- **마우스를 올리면 짧은 설명이 뜹니다.** 「안 되는 것·불편한 것·바라는 기능을 알려 주세요(브라우저가 열립니다)」. 0.45초 뒤에 뜨고, 마우스가 벗어나거나 누르면 사라지며, 창이나 화면 끝에서 잘리지 않게 위치를 당깁니다. 실행 중 언어를 바꾸면 설명도 바뀝니다.
- **페이지 언어 규칙을 책갈피 툴 시리즈와 같게 맞췄습니다.** 화면 언어가 한국어(ko, ko-KR 등)면 한국어 페이지, 그 밖의 모든 언어는 영어 페이지를 엽니다. 「의견 보내기」와 새 버전 알림의 「업데이트」가 같은 규칙을 씁니다. 의견은 [의견 칸](https://chaekgalpi.co.kr/tools/txttoepub#feedback)에서도 보낼 수 있습니다.

### 확인한 것
- 시험 597개 + 서브테스트 1015개 통과(EPUBCheck 5.4.0·exe 점검 포함)(새 시험 `tests/test_feedback_access.py` 242개 — Tab·Shift+Tab 순서, Enter·Space·숫자판 Enter 각각 브라우저 1번, 초점 테두리 켜짐·꺼짐과 크기 불변, 다른 키 무반응, 설명이 뜨고 사라짐, 지연 전에 벗어나면 안 뜸, 누르면 숨음, 4개 언어 문구, 떠 있는 동안 언어 바꾸기, 가장 작은 창을 화면 왼쪽·오른쪽 끝에 붙여도 창·화면 안, 언어 코드 38가지의 페이지와 주소 모양, README 4개 언어 링크(의견 칸·툴 페이지), 모든 시험에서 소켓·urlopen 0건). 시험은 실제 브라우저를 열지 않고 네트워크에 나가지 않습니다.
- exe를 임시 폴더에서 죽은 프록시·빈 APPDATA 환경으로 띄워 창이 뜨고 닫히는 것을 확인(링크는 누르지 않음).

### 파일
- `txt-to-epub.exe` (31.8 MB, Windows 10/11 64비트)
- SHA-256: `89612e1017588afcbfd1cd1680879a1ff6648f96837d27ed3634b704ef9c0ba7`
- 소스 실행: `pip install -r requirements.txt` → `python main.py`

---

## Chaekgalpi Tools – TXT to EPUB v0.2.2

Polishes the "Send feedback" link for the keyboard and adds a hover note. Conversion works as in v0.2.1.

### Changed
- **Works from the keyboard.** Tab to "Send feedback" (a frame shows), then press Enter or Space. The frame always takes its place, so focus never changes the size.
- **A short note on hover:** "Tell us what's broken or missing (opens your browser)". It appears after 0.45 s, goes away when the mouse leaves or you click, is kept inside the window and the screen, and follows a language switch.
- **One page-language rule across the Chaekgalpi Tools series.** A Korean screen (ko, ko-KR, …) opens the Korean page; every other language opens the English page. "Send feedback" and the update notice's "Update" use the same rule. You can also use the [feedback box](https://chaekgalpi.co.kr/en/tools/txttoepub#feedback) directly.

### Checked
- 597 tests + 1015 subtests pass (with EPUBCheck 5.4.0 and the exe check) (242 new in `tests/test_feedback_access.py`: Tab and Shift+Tab order, Enter/Space/keypad Enter each open the browser once, the focus frame and an unchanged size, other keys do nothing, the note shows and hides, nothing before the delay, hidden on click, four languages, language switch while showing, the smallest window against the left and right screen edges, 38 language codes and the address shape, README links in four languages (feedback box and tools page), zero socket/urlopen calls). No test opens a real browser or reaches the network.
- The exe was started from a scratch folder behind a dead proxy with an empty APPDATA: the window opens and closes (the link is not clicked).

### Files
- `txt-to-epub.exe` (31.8 MB, Windows 10/11 64-bit)
- SHA-256: `89612e1017588afcbfd1cd1680879a1ff6648f96837d27ed3634b704ef9c0ba7`
- From source: `pip install -r requirements.txt` → `python main.py`

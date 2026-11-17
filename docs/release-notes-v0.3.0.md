## 책갈피 툴 – TXT를 EPUB으로 v0.3.0

EPUB 3으로도 저장할 수 있게 했고, 화면을 손봤습니다. 기본 저장 형식은 지금처럼 EPUB 2입니다.

### 새로 생긴 것
- **저장 형식 선택: EPUB 2 / EPUB 3.** 화면 「3. 책 정보·표지·스타일」의 **저장 형식**에서 고르며, 고른 값은 다음 실행에도 남습니다. 명령줄에서는 `--epub3`(또는 `--epub-version 3`)입니다.
  - EPUB 2(기본): OPF 2.0과 toc.ncx 목차. 유페이퍼는 EPUB 2만 받으니 유페이퍼에 올릴 파일은 EPUB 2로 저장하세요. EPUB 3을 고르면 기록 칸에도 이 안내가 한 줄 나옵니다.
  - EPUB 3: OPF 3.0, `nav.xhtml` 목차, XHTML5 문서. 오래된 전자책 단말기를 위해 `toc.ncx`도 함께 넣고, 두 목차는 같은 챕터 목록에서 만들어 항목이 같습니다.
  - 챕터 나누기, 문단 처리, 표지, 스타일은 두 형식이 같습니다.

### 바뀐 것
- **미리보기·기록 칸 글꼴.** 한국어 Windows에서는 이 두 칸이 고정폭 글꼴(굴림체)로 나와 한글 줄끼리 붙어 보였습니다. 화면의 다른 글자와 같은 글꼴로 바꿨습니다.
- **창 크기.** 가장 작은 창 높이를 870픽셀에서 772픽셀로 낮췄습니다. 「순서 ▲위로 ▼아래로」 버튼은 「한 권으로」 옆으로 옮겼습니다(한 권으로일 때만 쓰는 버튼입니다). 처음 열 때는 작업 표시줄을 뺀 화면 안에 맞춰 가운데에 엽니다. 화면 배율 125%·150% 노트북에서 「변환」 버튼이 작업 표시줄 아래로 숨던 문제가 없어졌습니다.
- **3번 칸 줄 맞춤.** 본문 언어·저장 형식·줄간격 상자의 양 끝을 위아래로 맞췄습니다. 일본어 화면에서 줄간격 상자의 글자가 잘리던 것도 고쳤습니다.
- **시작 그림.** exe를 켜면 압축을 푸는 동안 시작 그림이 먼저 뜨고, 창이 그려지면 닫힙니다. 표지에 쓰는 이미지 모듈은 창이 뜬 뒤에 불러옵니다.

### 알려진 한계
- 화면 배율 150%인 1920×1080 화면(1920×1200도 조금)에서는 창이 화면에 맞춰 줄어들어 3번 칸 아래쪽(표지 파일 칸·스타일)이 잘립니다. 「변환」 버튼은 보입니다.

### 확인한 것
- 시험 660개 + 서브테스트 1039개 통과(EPUBCheck 5.4.0·exe 점검 포함). 새 시험은 `tests/test_epub3.py` 30개(EPUB 2·EPUB 3 모두 epubcheck 오류 0, 두 목차 항목 일치, 설정 기억, 명령줄 옵션)와 `tests/test_layout.py` 19개(창이 작업 영역 안, 150%에서도 「변환」 버튼이 보임, 4개 언어 가장 작은 창에서 잘리는 글자 0, 3번 칸 정렬, 글꼴)입니다. 시험은 네트워크에 나가지 않습니다.
- exe를 임시 폴더에서 죽은 프록시·빈 APPDATA 환경으로 띄워 창이 뜨고 닫히는 것을 확인했습니다.
- 의견은 [의견 칸](https://chaekgalpi.co.kr/tools/txttoepub#feedback)에서 보낼 수 있습니다.

### 파일
- `txt-to-epub.exe` (31.8 MB, Windows 10/11 64비트)
- SHA-256: `c73f72b7a849eb8f1729e0e2f85308d6ff24f9bb03b7542125a7db9380d0da6e`
- 소스 실행: `pip install -r requirements.txt` → `python main.py`

---

## Chaekgalpi Tools – TXT to EPUB v0.3.0

Adds EPUB 3 as an output format and tidies the window. EPUB 2 stays the default.

### New
- **Output format: EPUB 2 or EPUB 3.** Pick it under **Output format** in step 3 (Book info, cover, style); the choice is remembered for the next start. On the command line: `--epub3` (or `--epub-version 3`).
  - EPUB 2 (default): OPF 2.0 with a toc.ncx table of contents. upaper.net (유페이퍼) accepts EPUB 2 only, so save files meant for upaper as EPUB 2. Choosing EPUB 3 also puts this note in the log.
  - EPUB 3: OPF 3.0, a `nav.xhtml` table of contents and XHTML5 documents. A `toc.ncx` is written as well for older e-ink readers; both come from the same chapter list, so they match.
  - Chapter splitting, paragraphs, cover and style are the same in both formats.

### Changed
- **Preview and log font.** On Korean Windows these two boxes used a fixed-width font (Gulim), and lines of Hangul touched each other. They now use the same font as the rest of the window.
- **Window size.** The smallest window is 772 px high instead of 870. The "Order ▲ Up ▼ Down" buttons moved next to "One book" (they only work there). The first window is fitted into the screen without the taskbar and centred, so the Convert button no longer hides under the taskbar on laptops at 125% or 150% scaling.
- **Step 3 lines up.** The Text language, Output format and Line spacing boxes share both edges, and the Japanese line-spacing box is no longer cut.
- **Start-up picture.** The exe shows a start-up picture while it unpacks and closes it once the window is drawn. The image module used for covers loads after the window is up.

### Known limit
- At 150% scaling on a 1920×1080 screen (and a little on 1920×1200), the window is fitted to the screen and the bottom of step 3 (cover file box and style) is cut off. The Convert button stays visible.

### Checked
- 660 tests + 1039 subtests pass (with EPUBCheck 5.4.0 and the exe check). New: 30 in `tests/test_epub3.py` (EPUB 2 and EPUB 3 both pass epubcheck with no errors, both contents lists match, the choice is remembered, command-line options) and 19 in `tests/test_layout.py` (window inside the work area, Convert visible at 150%, no cut text at the smallest window in four languages, step 3 alignment, font). No test reaches the network.
- The exe was started from a scratch folder behind a dead proxy with an empty APPDATA: the window opens and closes.
- Feedback: use the [feedback box](https://chaekgalpi.co.kr/en/tools/txttoepub#feedback).

### Files
- `txt-to-epub.exe` (31.8 MB, Windows 10/11 64-bit)
- SHA-256: `c73f72b7a849eb8f1729e0e2f85308d6ff24f9bb03b7542125a7db9380d0da6e`
- From source: `pip install -r requirements.txt` → `python main.py`

## 책갈피 툴 – TXT를 EPUB으로 v0.2.0

「여러 TXT를 책 한 권으로」를 더한 버전입니다. 기존 「파일마다 EPUB」 동작은 그대로입니다.

### 새로 더한 것
- **한 권으로.** 파일 목록 아래의 라디오에서 **한 권으로**를 고르면, 끌어다 놓은 폴더(또는 파일들)의 TXT가 파일 하나 = 챕터 하나인 EPUB 한 개가 됩니다. 회차마다 파일이 나뉜 웹소설 폴더용입니다. 설정에 기억됩니다(`merge_mode`).
- **번호 순서.** 파일명의 숫자를 수로 읽어 `2화`가 `10화`보다 앞에 옵니다(`제1-2화` < `제1-10화`). ▲ ▼ 버튼(Alt+↑↓)으로 순서를 바꿉니다.
- **파일명 → 챕터 제목.** 모든 파일명에 같은 부분(시리즈 이름)을 뺀 나머지가 챕터 제목입니다(`나혼자만레벨업_001화_각성.txt` → `001화 각성`). 파일 첫 줄이 그 제목이거나 `제1화`처럼 챕터 제목 형태이면 그 줄을 제목으로 쓰고 본문에는 두 번 넣지 않습니다. 2단계 목록에서 제목을 두 번 누르면 고칠 수 있고, 체크를 끄면 그 파일은 뺍니다.
- **책 제목 기본값.** 폴더 하나를 넣으면 폴더 이름, 파일들을 넣으면 파일명의 같은 부분. 결과는 첫 파일 폴더에 `<책 제목>.epub`(이미 있으면 `(2)`…).
- **인코딩은 파일마다** 따로 감지합니다(EUC-KR 회차와 UTF-8 회차가 섞인 폴더). 문단 구분 `자동`도 파일마다, 본문 언어 `자동`은 책 전체로 한 번 정합니다. 빈 파일·읽기 실패 파일은 그 파일만 건너뛰고 기록에 한 줄 남깁니다.
- **명령줄 `--merge [--output 파일]`.** `--chapter-pattern`·`--no-chapters`는 `--merge`와 함께 쓰면 무시한다고 한 줄 알리고 진행합니다. 도움말은 4개 언어.
- 화면 문구 4개 언어(한국어·English·中文·日本語) 추가. README 4개 언어에 「여러 TXT를 책 한 권으로」 절을 넣고 「하지 않는 것」에서 회차 병합 줄을 뺐습니다.

### 고친 것
- **같은 폴더에 동시에 변환할 때 드물게 나던 `WinError 5`.** 출력 이름을 예약하고 결과 파일을 그 이름으로 옮기는 두 단계 사이에 다른 스레드의 `lexists` 검사가 끼어들면 Windows가 이름 바꾸기를 거부했습니다(시험 `test_two_conversions_of_the_same_file_at_once_produce_two_files`가 100번에 한 번꼴로 실패). 두 단계를 한 잠금 아래에서 하고, 다른 프로세스(백신 등)가 잠깐 쥔 경우만 짧게 다시 시도합니다.
- 책 제목이 `CON`·`COM1` 같은 Windows 예약 이름이면 파일 이름에 `_`를 붙입니다. `--output`에 `.epub`이 없으면 붙입니다.

### 확인한 것
- 시험 232개 + 서브테스트 999개 통과(새 시험 97개: `tests/test_merge.py` 36개 — 번호 순서 · 제목 뽑기 · 인코딩 섞인 3개 파일 → 1권 · 체크 끈 파일 제외 · 빈 파일 건너뜀 · 1개만 넣기 · 책 제목 기본값 · CLI `--merge`/`--output`/패턴 옵션 무시 안내 · GUI 모드 전환·순서·제목 수정·설정 저장 · 둘째 파일 읽는 중 취소 → 결과 없음 · 동시 변환 잠금; `tests/test_merge_edges.py` 61개 — 소수점·전각·앞 공백·거대한 수 파일명, 하위 폴더 번호, 첫 줄 규칙 13가지, 특수문자 제목, 제목만 있는 파일, BOM·CRLF·DOS EOF, 출력 이름 충돌, `--output` 덮어쓰기 금지·확장자 보정·없는 폴더, 파일 수 확인, 1MB 분할, GUI 시작 모드·선택 동기화·제거·언어 전환·실행 중 잠금·인라인 제목 편집, 흔들리던 시험 50회 연속). 새 버전 확인은 시험에서 운영 서버로 나가지 않습니다(`tests/conftest.py` 가드).
- 회차 파일 10개 폴더(EUC-KR·UTF-8 섞음)를 GUI에서 「한 권으로」 변환: 기록에 「10개 파일 → 1권, 챕터 10개」, 캡처 `docs/one_book.png`. 임시 폴더에서 exe를 죽은 프록시 환경으로 띄워 창이 뜨는 것을 확인.

### 파일
- `txt-to-epub.exe` (31.8 MB, Windows 10/11 64비트)
- SHA-256: `d8f14e5c7853de13b1cc152409ddb0ee7a0471531c41d94514d13926407833e4`
- 소스 실행: `pip install -r requirements.txt` → `python main.py`

---

## Chaekgalpi Tools – TXT to EPUB v0.2.0

Adds "several TXT files as one book". "One EPUB per file" works as before.

### New
- **One book.** Choose **One book** under the file list and the TXT files of the dropped folder (or files) become a single EPUB, one chapter per file. Meant for web-novel folders with one file per episode. Remembered in the settings (`merge_mode`).
- **Number order.** Numbers in file names are read as numbers, so `2` comes before `10` (`part1-2` < `part1-10`). ▲ ▼ (Alt+↑/↓) moves a file.
- **File name → chapter title.** The file name minus what all the names share (the series name): `Book_001_Awakening.txt` → `001 Awakening`. When a file's first line is that title or looks like a heading (`Chapter 1`), that line becomes the title and is not printed twice. Double-click a title in step 2 to change it; untick a file to leave it out.
- **Default book title.** The folder's name when one folder was dropped, else what the file names share. The result is `<title>.epub` beside the first file (`(2)`… when the name is taken).
- **Encoding per file** (EUC-KR and UTF-8 episodes can be mixed). Paragraph mode `auto` is decided per file; text language `auto` once for the book. An empty or unreadable file is skipped with one line in the log.
- **Command line `--merge [--output FILE]`.** `--chapter-pattern` and `--no-chapters` are announced as ignored with `--merge`. Help in four languages.
- Interface strings in four languages; the README in four languages gains a "one book" section and loses the "no merging" line.

### Fixed
- **A rare `WinError 5` when two conversions ran into the same folder at once.** Between reserving the output name and moving the finished file onto it, another thread's `lexists` check could hold the file for a moment and Windows refused the rename (the flaky test `test_two_conversions_of_the_same_file_at_once_produce_two_files`). Both steps now run under one lock, with a short retry only for another process (an antivirus scanner) holding the file.
- A book title that is a Windows device name (`CON`, `COM1`) gets an underscore in the file name; `--output` without `.epub` gets the extension.

### Checked
- 232 tests + 999 subtests pass (97 new: `tests/test_merge.py`, `tests/test_merge_edges.py`). No test reaches the production server (`tests/conftest.py` guard).

### Files
- `txt-to-epub.exe` (31.8 MB, Windows 10/11 64-bit)
- SHA-256: `d8f14e5c7853de13b1cc152409ddb0ee7a0471531c41d94514d13926407833e4`
- From source: `pip install -r requirements.txt` → `python main.py`

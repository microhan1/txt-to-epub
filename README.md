# 책갈피 툴 – TXT를 EPUB으로

[English](README.en.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

텍스트 파일(.txt) 소설을 리디페이퍼·크레마·킨들에서 읽을 수 있는 EPUB으로 바꿉니다. 인코딩(EUC-KR·CP949·UTF-8·UTF-16)을 자동으로 잡고, 챕터를 자동으로 나눕니다. 서버 없음, 설치 없음, 원본 무수정.

![전후 비교](docs/before_after.png)

## 다운로드

- **실행 파일**: [Releases](https://github.com/microhan1/txt-to-epub/releases)에서 `txt-to-epub.exe`를 받아 더블클릭. 설치 없이 바로 실행됩니다. 서명되지 않은 파일이라 SmartScreen 경고가 뜨면 "추가 정보 → 실행"을 누르세요.
- **소스 실행**:

```bash
pip install -r requirements.txt
python main.py
```

## 사용법

1. TXT 파일을 창에 끌어다 놓습니다. 인코딩이 감지되고 앞부분 미리보기가 뜹니다. 글자가 깨져 보이면 그 자리에서 인코딩을 바꿉니다.
2. 감지된 챕터 목록을 확인합니다. 잘못 잡힌 항목은 체크를 끄고, 빠진 곳은 줄 번호로 추가합니다.
3. 제목·저자·본문 언어·표지·스타일을 정하고 **변환**을 누르면 원본 옆에 `<원본명>.epub`이 만들어집니다.

명령줄로도 쓸 수 있습니다.

```bash
python main.py novel.txt --encoding auto --chapter-pattern "^제\d+장" --title "제목" --author "저자" --lang ko --cover cover.jpg
```

`python main.py --help`가 OS 언어(한국어 · English · 中文 · 日本語)로 옵션을 보여줍니다. `--lang`은 본문 언어(EPUB의 `dc:language`), 화면 언어는 `--ui-lang`입니다.

## 챕터 패턴 예시

줄 하나가 통째로 패턴에 맞으면 챕터 제목으로 봅니다. 기본 패턴이 아래를 모두 잡고, 정규식을 직접 넣을 수도 있습니다. 패턴 목록은 `patterns.json`에 있습니다.

| 언어 | 예시 |
|---|---|
| 한국어 | `제1장 시작`, `12화` |
| English | `Chapter 7`, `CHAPTER XII. The Pool of Tears` |
| 中文 | `第3章`, `第十二回` |
| 日本語 | `第3話 帰郷`, `プロローグ` |

## 하지 않는 것

- EPUB3, MOBI, AZW3는 만들지 않습니다. EPUB2 하나만.
- 맞춤법·오타 교정, 문장 수정은 하지 않습니다.
- 여러 TXT를 한 EPUB으로 합치지 않습니다 (회차 병합 없음).
- 이미지가 섞인 문서(HTML, DOCX)는 대상이 아닙니다.
- DRM 해제나 웹소설 수집 기능은 없습니다.

## 시리즈

- 책갈피 툴: [스캔 PDF 보정 (scan-pdf-cleanup)](https://github.com/microhan1/scan-pdf-cleanup) · [여백 자르기 (TrimPDF)](https://github.com/microhan1/TrimPDF) · [두쪽 나누기 (spread-split)](https://github.com/microhan1/spread-split) · [목차 책갈피 넣기 (pdf-toc-add)](https://github.com/microhan1/pdf-toc-add)
- [책갈피](https://github.com/microhan1/chaekgalpi)

## 라이선스

MIT. [LICENSE](LICENSE) 참조.

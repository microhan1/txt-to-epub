# しおりツール – TXTをEPUBに

[한국어](README.md) · [English](README.en.md) · [中文](README.zh-CN.md)

テキストファイル（.txt）の小説を、Ridipaper・Crema・Kindle で読める EPUB に変換します。エンコーディング（EUC-KR・CP949・UTF-8・UTF-16）を自動判定し、章を自動で分割します。サーバーなし、インストールなし、元ファイルは変更しません。

![変換前後](docs/before_after.png)

## ダウンロード

- **実行ファイル**: [Releases](https://github.com/microhan1/txt-to-epub/releases) から `txt-to-epub.exe` を取得してダブルクリック。インストール不要です。署名のないファイルのため SmartScreen の警告が出たら「詳細情報 → 実行」を選んでください。
- **ソースから実行**:

```bash
pip install -r requirements.txt
python main.py
```

## 使い方

1. TXT ファイルをウィンドウにドロップします。エンコーディングが判定され、冒頭がプレビューされます。文字化けしていればその場でエンコーディングを変えます。
2. 検出された章の一覧を確認します。誤検出はチェックを外し、抜けた章は行番号で追加します。
3. タイトル・著者・本文の言語・表紙・スタイルを決めて **変換** を押すと、元ファイルの隣に `<元のファイル名>.epub` ができます。

コマンドラインでも使えます。

```bash
python main.py novel.txt --encoding auto --chapter-pattern "^第.+話" --title "タイトル" --author "著者" --lang ja --cover cover.jpg
```

`python main.py --help` が OS の言語（한국어 · English · 中文 · 日本語）でオプションを表示します。`--lang` は本文の言語（EPUB の `dc:language`）、画面の言語は `--ui-lang` です。

## 章パターンの例

行全体がパターンに一致したとき、その行を章タイトルとみなします。既定のパターンは以下をすべて拾い、正規表現を直接入力することもできます。パターンの一覧は `patterns.json` にあります。

| 言語 | 例 |
|---|---|
| 韓国語 | `제1장 시작`、`12화` |
| 英語 | `Chapter 7`、`CHAPTER XII. The Pool of Tears` |
| 中国語 | `第3章`、`第十二回` |
| 日本語 | `第3話 帰郷`、`プロローグ` |

## しないこと

- EPUB3・MOBI・AZW3 は作りません。EPUB2 のみ。
- スペルチェックや文章の修正はしません。
- 複数の TXT を一つの EPUB にまとめません。
- 画像を含む文書（HTML・DOCX）は対象外です。
- DRM 解除やウェブ小説の収集機能はありません。

## シリーズ

- しおりツール: [スキャンPDF補正 (scan-pdf-cleanup)](https://github.com/microhan1/scan-pdf-cleanup) · [余白トリミング (TrimPDF)](https://github.com/microhan1/TrimPDF) · [見開き分割 (spread-split)](https://github.com/microhan1/spread-split) · [目次しおり追加 (pdf-toc-add)](https://github.com/microhan1/pdf-toc-add)
- [しおり](https://github.com/microhan1/chaekgalpi)

## ライセンス

MIT。[LICENSE](LICENSE) を参照。

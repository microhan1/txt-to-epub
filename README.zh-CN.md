# 书签工具 – TXT转EPUB

[한국어](README.md) · [English](README.en.md) · [日本語](README.ja.md)

把纯文本小说（.txt）转换成可在 Ridipaper、Crema、Kindle 上阅读的 EPUB。自动识别编码（EUC-KR、CP949、UTF-8、UTF-16），自动分割章节。无服务器、无需安装、不修改原文件。

![前后对比](docs/before_after.png)

## 下载

- **可执行文件**：在 [Releases](https://github.com/microhan1/txt-to-epub/releases) 下载 `txt-to-epub.exe` 并双击运行，无需安装。文件未签名，若 SmartScreen 弹出警告，请选择"更多信息 → 仍要运行"。
- **从源码运行**：

```bash
pip install -r requirements.txt
python main.py
```

## 使用方法

1. 把 TXT 文件拖到窗口中。程序会识别编码并预览开头部分；如果显示乱码，可当场更换编码。
2. 检查识别出的章节列表。取消误判的项目，用行号补上漏掉的章节。
3. 设置书名、作者、正文语言、封面和样式，按 **转换**，即在原文件旁生成 `<原文件名>.epub`。

也可以在命令行使用：

```bash
python main.py novel.txt --encoding auto --chapter-pattern "^第.+章" --title "书名" --author "作者" --lang zh --cover cover.jpg
```

`python main.py --help` 会按操作系统语言（한국어 · English · 中文 · 日本語）显示选项。`--lang` 是正文语言（EPUB 的 `dc:language`），界面语言用 `--ui-lang`。

## 章节模式示例

整行匹配模式时视为章节标题。默认模式可识别下面所有形式，也可以输入自己的正则表达式。模式列表在 `patterns.json` 中。

| 语言 | 示例 |
|---|---|
| 韩语 | `제1장 시작`、`12화` |
| 英语 | `Chapter 7`、`CHAPTER XII. The Pool of Tears` |
| 中文 | `第3章`、`第十二回` |
| 日语 | `第3話 帰郷`、`プロローグ` |

## 不做的事

- 不生成 EPUB3、MOBI、AZW3，只生成 EPUB2。
- 不做拼写纠错，不修改文字。
- 不把多个 TXT 合并成一个 EPUB。
- 含图片的文档（HTML、DOCX）不在范围内。
- 不解除 DRM，不抓取网络小说。

## 系列

- 书签工具：[扫描PDF清晰化 (scan-pdf-cleanup)](https://github.com/microhan1/scan-pdf-cleanup) · [裁边 (TrimPDF)](https://github.com/microhan1/TrimPDF) · [跨页拆分 (spread-split)](https://github.com/microhan1/spread-split) · [添加目录书签 (pdf-toc-add)](https://github.com/microhan1/pdf-toc-add)
- [书签](https://github.com/microhan1/chaekgalpi)

## 许可证

MIT。见 [LICENSE](LICENSE)。

发布的 exe 还包含 Python、Tcl/Tk 等第三方组件，组件及其许可证全文见 [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt)。

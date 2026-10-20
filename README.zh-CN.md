# 书签工具 – TXT转EPUB

[한국어](README.md) · [English](README.en.md) · [日本語](README.ja.md)

把纯文本小说（.txt）转换成可在 Ridipaper、Crema、Kindle 上阅读的 EPUB。自动识别编码（EUC-KR、CP949、UTF-8、UTF-16），自动分割章节。无服务器（仅检查新版本例外，可关闭）、无需安装、不修改原文件。

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

去掉首尾空白后，行以模式**开头**且不超过 80 个字符时，视为章节标题。因此 `第1章 启程` 这样编号后面带副标题的行也能识别，但正文句子若以 `序章` 或 `1. ` 开头，也可能被误认为章节；在列表中取消勾选该项，它就会并入上一章的正文。默认模式可识别下面所有形式，也可以输入自己的正则表达式。模式列表在 `patterns.json` 中。

| 语言 | 示例 |
|---|---|
| 韩语 | `제1장 시작`、`12화` |
| 英语 | `Chapter 7`、`CHAPTER XII. The Pool of Tears` |
| 中文 | `第3章`、`第十二回` |
| 日语 | `第3話 帰郷`、`プロローグ` |

## 检查新版本

启动时为了确认是否有新版本，只把工具名（`txttoepub`）和版本号发送到书签服务器（chaekgalpi.co.kr）。不发送文件，每天只检查一次，可在设置中关闭（顶部的 **检查新版本** 复选框）。检查在窗口显示后于后台进行，无法连接时不显示任何内容。

有新版本时，窗口底部会出现一行提示。按 **更新** 打开书签工具页面；按 **以后** 则不再提示该版本（有更新的版本时会再次提示）。不会自动下载或替换。

![新版本提示行](docs/update_notice.png)

*图：提示行画面。用伪造的服务器响应（新版本 0.2.0）显示的测试画面，界面为韩语。*

## 不做的事

- 不生成 EPUB3、MOBI、AZW3，只生成 EPUB2。
- 不做拼写纠错，不修改文字。
- 不把多个 TXT 合并成一个 EPUB。
- 含图片的文档（HTML、DOCX）不在范围内。
- 不解除 DRM，不抓取网络小说。
- 不会自动下载或替换新版本。

## 系列

- 书签工具：[扫描PDF清晰化 (scan-pdf-cleanup)](https://github.com/microhan1/scan-pdf-cleanup) · [裁边 (TrimPDF)](https://github.com/microhan1/TrimPDF) · [跨页拆分 (spread-split)](https://github.com/microhan1/spread-split) · [添加目录书签 (pdf-toc-add)](https://github.com/microhan1/pdf-toc-add)
- [书签图书馆（Chaekgalpi Library）](https://chaekgalpi.co.kr/tools/txttoepub?utm_source=github&utm_medium=referral&utm_campaign=tool_cta&utm_content=txttoepub) — 记录读过的书和读书笔记的网页服务（仅韩语）

## 许可证

MIT。见 [LICENSE](LICENSE)。

发布的 exe 还包含 Python、Tcl/Tk 等第三方组件，组件及其许可证全文见 [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt)。

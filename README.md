# OCR Extractor · 图片转文字

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)](CHANGELOG.md)
[![Self-Improving](https://img.shields.io/badge/self--improving-yes-orange.svg)](#self-improvement)

**Claude Code Skill** — 将图片自动转为干净的 Markdown 中文文本，支持水印去除、页码排序、自动纠错、自适应调优。

Extract clean Chinese text from images (TIFF/PNG/JPG) via Tesseract OCR. Auto watermark removal, page sorting, typo correction, and self-improving pipeline.

## 适用场景 / Use Cases

- 📷 **截图转文字** — 课程截图、PPT 幻灯片 → Obsidian 笔记
- 📄 **文档数字化** — 扫描件、老照片 → 可检索的 Markdown 文档
- 🏷️ **水印去除** — 自动识别并清除底部水印
- 📚 **知识管理** — 批量处理图片，去重合并，直接导入 Obsidian/Logseq
- 🔧 **自进化管道** — 使用越多，参数越优

## Features

- 🖼️ **多格式支持**: TIFF (big-endian 16-bit), PNG, JPG, BMP, GIF
- 🚫 **水印去除**: 自动检测并裁剪常见中文水印模式
- 🔢 **页码排序**: 快速 OCR 检测每张图页码，自动重排
- ✏️ **自动纠错**: 内置 30+ Tesseract 中文混淆对，上下文校验
- 🎯 **Otsu 二值化**: 自适应阈值 + 稀疏文本回退
- 🔍 **去重合并**: MD5 近重复检测 + 连续内容合并
- 🧬 **自进化**: 使用日志 → 质量分析 → 自动调优参数

## Requirements

```bash
brew install tesseract tesseract-lang
pip3 install pytesseract Pillow numpy
```

## Installation

```bash
git clone https://github.com/britniusvzx43-hub/ocr-extractor.git ~/.claude/skills/ocr-extractor
```

## Usage

### Claude Code Skill

```
/ocr-extractor
```

### CLI

```bash
# 基本用法：图片转 Markdown
python3 scripts/ocr_extract.py image1.tiff image2.png -o ./output

# 指定标题
python3 scripts/ocr_extract.py *.tiff --title "我的笔记"

# 查看统计 / 手动优化
python3 scripts/ocr_extract.py --stats
python3 scripts/ocr_extract.py --improve --force

# 检查依赖
python3 scripts/ocr_extract.py --check-deps
```

### Options

| Flag | Description |
|------|-------------|
| `--output, -o <path>` | 输出目录 |
| `--title, -t <str>` | 文档标题 |
| `--lang <code>` | Tesseract 语言 (default: `chi_sim`) |
| `--no-sort` | 关闭页码自动排序 |
| `--no-auto-correct` | 关闭自动纠错 |
| `--no-watermark` | 关闭水印去除 |
| `--no-otsu` | 关闭 Otsu 二值化 |
| `--stdout` | 输出到终端 |
| `--stats` | 查看使用统计 |
| `--improve` | 触发自进化调优 |
| `--force` | 强制调优（忽略冷却） |
| `--config` | 打印当前配置 |
| `--check-deps` | 检查依赖 |

## Self-Improvement / 自进化

每次运行自动记录到 `usage_log.jsonl`。当质量低于阈值且累积足够数据后，自动触发 `self_improve.py` 优化：

- 水印裁剪参数
- Otsu 阈值有效性
- 质量趋势分析

手动触发：`python3 scripts/ocr_extract.py --improve --force`

## File Structure

```
ocr-extractor/
├── SKILL.md              # 技能定义（findskill 可发现）
├── README.md
├── config.json           # 运行配置 + self_improve 节
├── CHANGELOG.md          # 版本 + 自动调优历史
├── scripts/
│   ├── ocr_extract.py    # 主流水线
│   └── self_improve.py   # 自进化模块
└── references/
    ├── tesseract_config.md
    └── watermark_patterns.md
```

## Keywords / 搜索关键词

`OCR` `图片转文字` `中文OCR` `Chinese OCR` `水印去除` `watermark removal` `截图转文字` `screenshot to text` `文档数字化` `document digitization` `Obsidian` `Markdown` `Tesseract` `知识管理` `knowledge management` `笔记` `batch processing` `批量处理` `self-improving` `自进化`

## License

MIT

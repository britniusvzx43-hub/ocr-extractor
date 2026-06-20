---
name: ocr-extractor
description: "Extract Chinese text from images (图片转文字). Converts TIFF/PNG/JPG to clean Markdown via Tesseract OCR. Auto-removes watermarks (水印去除), applies adaptive binarization, batches multiple images, deduplicates, and outputs structured notes. Ideal for Obsidian notes, document digitization (文档数字化), screenshot-to-text (截图转文字), and knowledge management (知识管理). Self-improving via usage tracking and parameter auto-tuning."
version: 1.3.0
license: MIT
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
metadata:
  domains: [ocr, chinese-ocr, document-processing, image-to-text, chinese-text, watermark-removal, image-processing, obsidian, knowledge-management, notes, digitization, screenshot-ocr, batch-processing, markdown-conversion, 图片转文字, 水印去除, 文档数字化, 笔记]
  type: pipeline
  inputs: [image-files, directory-of-images, tiff, png, jpg, screenshots]
  outputs: [markdown, clean-text, structured-notes, obsidian-notes]
  subagent_model: claude-sonnet-4-6
  self_improving: true
---

# OCR Extractor - 图片转文字 Skill

将扫描图片/截图/TIFF 转换为干净的中文 Markdown 文本。自动去水印、二值化增强、批量处理、去重合并。

---

## Quick Start

```
/ocr-extractor ~/Desktop/scanned-images/
/ocr-extractor ./slides/*.tiff --output ./notes/
/ocr-extractor single-image.png --lang chi_sim
/ocr-extractor . --improve  # 进入自我迭代模式
```

---

## Triggers

- `/ocr-extractor <path>` — 处理图片或目录
- `ocr-extractor --improve` — 分析使用日志，自我优化
- `ocr-extractor --stats` — 查看处理统计
- `ocr-extractor --config` — 查看/修改配置

---

## Process Pipeline

```
输入图片 (TIFF/PNG/JPG)
    │
    ▼
┌─────────────────────────────────────────┐
│ Step 1: FORMAT NORMALIZATION             │
│ • sips convert → 8-bit PNG              │
│ • Handle 16-bit, big-endian, RGBA       │
│ • Generate processing manifest          │
├─────────────────────────────────────────┤
│ Step 2: PREPROCESSING                    │
│ • Grayscale conversion                  │
│ • Contrast stretch (p5-p95)             │
│ • Otsu binarization (adaptive)          │
│ • Save binarized debug image            │
├─────────────────────────────────────────┤
│ Step 3: WATERMARK REMOVAL               │
│ • Scan bottom 150px for gray rows       │
│ • Detect: gray_ratio>3% & dark<15%      │
│ • White-out detected watermark band     │
│ • Configurable detection threshold      │
├─────────────────────────────────────────┤
│ Step 4: OCR (Tesseract)                 │
│ • Language: chi_sim (default)           │
│ • PSM mode: auto-select (3/4/6)         │
│ • Fallback: raw grayscale if binary     │
│   produces < 100 chars                  │
├─────────────────────────────────────────┤
│ Step 5: POST-PROCESSING                 │
│ • Filter garbled lines (CJK ratio)      │
│ • Remove known watermark strings        │
│ • Collapse excessive blank lines        │
│ • Quality score per page                │
├─────────────────────────────────────────┤
│ Step 6: DEDUP & MERGE                   │
│ • MD5 dedup identical images            │
│ • Detect consecutive content (overlap)  │
│ • Merge split slides                    │
├─────────────────────────────────────────┤
│ Step 7: MARKDOWN OUTPUT                 │
│ • Generate structured markdown          │
│ • Section headers from content          │
│ • Frontmatter with metadata             │
│ • Write to Obsidian-compatible format   │
└─────────────────────────────────────────┘
```

---

## Usage Patterns

### Pattern A: Batch Convert Course Slides

```bash
/ocr-extractor ~/slides/ --output ~/obsidian/notes/ --title "课程笔记"
```

Processing manifest saved to `<output>/manifest.json` for traceability.

### Pattern B: Single Image Quick OCR

```bash
/ocr-extractor screenshot.png
```

Outputs directly to stdout for quick copy-paste.

### Pattern C: Self-Improvement Loop

```bash
/ocr-extractor --improve
```

Analyzes `~/.claude/skills/ocr-extractor/usage_log.jsonl`:
- Identifies parameter ranges that produced highest quality scores
- Suggests threshold adjustments
- Updates default config if confidence > 80%

---

## Configuration

Config at `~/.claude/skills/ocr-extractor/config.json`:

```json
{
  "ocr": {
    "lang": "chi_sim",
    "psm": "auto",
    "fallback_threshold": 100
  },
  "watermark": {
    "enabled": true,
    "bottom_scan_rows": 150,
    "gray_range": [40, 190],
    "gray_ratio_threshold": 0.03,
    "dark_ratio_max": 0.15,
    "crop_bottom": 60
  },
  "preprocessing": {
    "contrast_stretch": true,
    "otsu_binarize": true,
    "otsu_skip_chars_threshold": 100
  },
  "postprocessing": {
    "min_cjk_ratio": 0.3,
    "watermark_keywords": [
      "智慧的大聪明", "售后更新微信", "yize2288"
    ],
    "max_blank_lines": 3
  },
  "self_improve": {
    "enabled": true,
    "log_usage": true,
    "auto_tune_thresholds": true,
    "min_samples_for_tuning": 5
  }
}
```

---

## Self-Improvement Mechanism

### Dual Trigger

| 触发方式 | 条件 | 说明 |
|---------|------|------|
| **自动触发** | 近期质量 < 70% + 5 条以上新记录 + 距上次 >1 小时 | 每次运行结束自动检查 |
| **手动触发** | `/ocr-extractor --improve` | 立即分析 + `--force` 跳过冷却 |

### Usage Logging

Every run writes to `usage_log.jsonl`:
```json
{
  "timestamp": "2026-06-20T10:30:00",
  "input_count": 13,
  "total_chars": 6238,
  "avg_quality_score": 0.85,
  "params": {"otsu_threshold": 139, "crop_bottom": 60},
  "errors": []
}
```

### Adaptive Tuning

自动或手动触发后：
1. Load usage log → 过滤最近记录
2. 按质量分组 → 找最优参数聚类
3. 分析趋势：crop_bottom 哪个值产出最高质量？Otsu 是否帮倒忙？
4. 置信度 >75% → 自动更新 `config.json` + 写 `CHANGELOG.md`
5. 置信度不足 → 打印建议，不自动改
6. 保存 `improve_state.json` 防止频繁触发

### 水印模式学习 (v1.1)

低质量运行 >2 次 → 建议检查是否有新水印未加入关键词列表。

### Quality Score Calculation

Per-page score (0-1):
- CJK ratio in output (expect >0.5 for Chinese docs)
- Output chars per input pixel (expect 0.001-0.01 for text slides)
- Garbled line ratio (expect <0.05)
- Watermark residue detection

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/ocr_extract.py` | Main OCR pipeline (steps 1-7) |
| `scripts/watermark_detect.py` | Watermark detection & removal |
| `scripts/quality_check.py` | Quality scoring & usage logging |
| `scripts/self_improve.py` | Adaptive parameter tuning |

---

## Dependencies

- `tesseract` (brew install tesseract)
- `tesseract --list-langs` must include `chi_sim`
- `python3` with: `pytesseract`, `Pillow`, `numpy`

Install check: `python3 scripts/ocr_extract.py --check-deps`

---

## Reference Documents

- [references/tesseract_config.md](references/tesseract_config.md) — Tesseract PSM modes, language packs, optimization
- [references/watermark_patterns.md](references/watermark_patterns.md) — Known watermark signatures and detection strategies

---

## Evolution Score

**Timelessness: 8/10**

OCR fundamentals stable. Tesseract is mature. The preprocessing pipeline (threshold → clean → OCR → filter) is universal across languages and document types. Watermark removal adapts to new patterns via config, not code changes.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.1.0 | 2026-06-20 | 自动触发优化 + 水印模式学习 + 质量趋势检测 + 冷却机制 |
| 1.0.0 | 2026-06-20 | 初始发布：7步管道 + 手动 --improve |

See [CHANGELOG.md](CHANGELOG.md) for full details.

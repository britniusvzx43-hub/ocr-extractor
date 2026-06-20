# OCR Extractor

Claude Code skill for extracting text from images (TIFF/PNG/JPG) with automatic watermark removal and self-improving OCR pipeline.

## Features

- **Multi-format support**: TIFF (big-endian 16-bit), PNG, JPG
- **Watermark removal**: Auto-detects and crops common Chinese watermark patterns
- **Otsu binarization**: Adaptive thresholding with fallback for sparse text
- **Deduplication**: MD5-based near-duplicate detection
- **Self-improving**: Usage logging → quality analysis → auto-tune parameters

## Requirements

```bash
brew install tesseract tesseract-lang
```

## Installation

```bash
git clone https://github.com/YOUR_USER/ocr-extractor.git ~/.claude/skills/ocr-extractor
```

## Usage

```
/ocr-extractor
```

Or via CLI:

```bash
python3 scripts/ocr_extract.py <image1.tiff> <image2.png> --output /path/to/out
```

### Options

| Flag | Description |
|------|-------------|
| `--output <path>` | Output file path |
| `--title <str>` | Document title |
| `--lang <code>` | Tesseract language (default: chi_sim) |
| `--no-watermark` | Skip watermark removal |
| `--no-otsu` | Skip Otsu binarization |
| `--stdout` | Print to stdout |
| `--stats` | Show usage statistics |
| `--improve` | Trigger self-improvement |
| `--force` | Force improvement (ignore cooldown) |
| `--config <path>` | Custom config path |

## Self-Improvement

The skill logs every run to `usage_log.jsonl`. When quality drops below threshold and enough data is collected, it auto-triggers `self_improve.py` to optimize:

- Watermark crop parameters
- Otsu threshold effectiveness
- Quality trend analysis

Manual trigger: `python3 scripts/ocr_extract.py --improve --force`

## File Structure

```
ocr-extractor/
├── SKILL.md              # Skill definition
├── README.md
├── config.json           # Runtime config + self_improve section
├── CHANGELOG.md          # Version + auto-tune history
├── scripts/
│   ├── ocr_extract.py    # Main pipeline
│   └── self_improve.py   # Self-improvement module
└── references/
    ├── tesseract_config.md
    └── watermark_patterns.md
```

## License

MIT

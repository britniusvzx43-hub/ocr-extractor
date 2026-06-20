#!/usr/bin/env python3
"""OCR Extractor — 图片转中文 Markdown 文本管道
用法:
  python3 ocr_extract.py <image_or_directory> [--output <dir>] [--title <str>]
  python3 ocr_extract.py --check-deps
  python3 ocr_extract.py --config
"""

import sys, os, json, re, hashlib, subprocess, argparse, time
from pathlib import Path
from datetime import datetime

# Config paths
SKILL_DIR = Path.home() / ".claude" / "skills" / "ocr-extractor"
CONFIG_PATH = SKILL_DIR / "config.json"
USAGE_LOG_PATH = SKILL_DIR / "usage_log.jsonl"

DEFAULT_CONFIG = {
    "ocr": {"lang": "chi_sim", "psm": "auto", "fallback_threshold": 100},
    "watermark": {
        "enabled": True, "bottom_scan_rows": 150,
        "gray_range": [40, 190], "gray_ratio_threshold": 0.03,
        "dark_ratio_max": 0.15, "crop_bottom": 60
    },
    "preprocessing": {
        "contrast_stretch": True, "otsu_binarize": True,
        "otsu_skip_chars_threshold": 100
    },
    "postprocessing": {
        "min_cjk_ratio": 0.3, "max_blank_lines": 3,
        "watermark_keywords": ["智慧的大聪明", "售后更新微信", "yize2288"]
    },
    "self_improve": {
        "enabled": True, "log_usage": True,
        "auto_tune_thresholds": True, "min_samples_for_tuning": 5
    }
}


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        # Deep merge with defaults
        return {**DEFAULT_CONFIG, **cfg}
    return dict(DEFAULT_CONFIG)


def check_deps():
    """Verify all dependencies are installed."""
    errors = []
    # Check tesseract
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, check=True)
    except:
        errors.append("tesseract not found. Install: brew install tesseract")

    # Check chi_sim
    try:
        r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
        if "chi_sim" not in r.stdout and "chi_sim" not in r.stderr:
            errors.append("chi_sim language not installed. Run: tesseract --list-langs")
    except:
        pass

    # Check Python packages
    for pkg in ["pytesseract", "PIL", "numpy"]:
        try:
            __import__({"PIL": "PIL", "numpy": "numpy", "pytesseract": "pytesseract"}[pkg])
        except ImportError:
            errors.append(f"{pkg} not found. Install: pip3 install {pkg}")

    if errors:
        print("❌ Missing dependencies:")
        for e in errors:
            print(f"  - {e}")
        return False
    print("✅ All dependencies satisfied")
    return True


def otsu_threshold(arr):
    """Manual Otsu binarization."""
    import numpy as np
    hist, _ = np.histogram(arr, bins=256, range=(0, 256))
    total = hist.sum()
    sum_all = (np.arange(256) * hist).sum()
    w_b = 0; sum_b = 0; max_var = 0; thresh = 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0: continue
        w_f = total - w_b
        if w_f == 0: break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between; thresh = t
    return thresh


def find_images(paths):
    """Find all image files from list of paths."""
    exts = {'.tiff', '.tif', '.png', '.jpg', '.jpeg', '.bmp', '.gif'}
    files = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            for f in sorted(pp.iterdir()):
                if f.suffix.lower() in exts and not f.name.startswith('._'):
                    files.append(str(f))
        elif pp.is_file() and pp.suffix.lower() in exts:
            files.append(str(pp))
    return files


def detect_page_number(text):
	"""Extract page/slide number from OCR text.
	Common patterns in Chinese slides:
	- Standalone number at line start: "03", "3", "03/50"
	- "第X页", "第X讲", "第X节"
	- Parenthesized: "(3)", "（3）"
	Returns (number, confidence) or (None, 0).
	"""
	lines = [l.strip() for l in text.split('\n') if l.strip()]
	if not lines:
		return None, 0

	# Look in first 5 lines (page numbers usually at top)
	candidates = []
	for line in lines[:5]:
		# Pattern 1: "第X页/讲/节/课"
		m = re.search(r'第\s*(\d+)\s*(?:页|讲|节|课|章|篇|集)', line)
		if m:
			candidates.append((int(m.group(1)), 0.95))

		# Pattern 2: Standalone number (possibly with total)
		m = re.search(r'(?:^|\s)(\d{1,3})\s*(?:/\s*\d{1,3})?(?:\s*$)', line)
		if m:
			n = int(m.group(1))
			if 1 <= n <= 200:
				candidates.append((n, 0.7))

		# Pattern 3: Parenthesized/bracketed number
		m = re.search(r'[（(]\s*(\d{1,3})\s*[）)]', line)
		if m:
			n = int(m.group(1))
			if 1 <= n <= 200:
				candidates.append((n, 0.8))

		# Pattern 4: Line that is purely a small number
		if re.match(r'^\d{1,3}$', line):
			n = int(line)
			if 1 <= n <= 100:
				candidates.append((n, 0.6))

		# Pattern 5: Number in corner format like "03" as first token
		tokens = line.split()
		if tokens and re.match(r'^\d{1,3}$', tokens[0]) and len(tokens[0]) <= 2:
			n = int(tokens[0])
			if 1 <= n <= 100:
				candidates.append((n, 0.5))

	if not candidates:
		return None, 0

	# Return highest-confidence candidate
	candidates.sort(key=lambda x: -x[1])
	return candidates[0]


def quick_ocr_for_sort(filepath, tmp_dir, lang="chi_sim"):
	"""Fast low-resolution OCR just on top portion to detect page numbers."""
	from PIL import Image
	import pytesseract

	img, _ = convert_to_png(filepath, tmp_dir)
	# Only top 30% where page numbers usually sit
	h = img.height
	crop_top = img.crop((0, 0, img.width, int(h * 0.3)))
	# Downscale 2x for speed
	small = crop_top.resize((crop_top.width // 2, crop_top.height // 2))
	text = pytesseract.image_to_string(small, lang=lang, config='--psm 6')
	return text


def sort_images_by_pagenum(files, tmp_dir, config):
	"""Detect page numbers and reorder images. Returns (sorted_files, sort_report)."""
	lang = config["ocr"]["lang"]
	numbered = []

	for fpath in files:
		try:
			text = quick_ocr_for_sort(fpath, tmp_dir, lang)
			num, conf = detect_page_number(text)
			numbered.append((fpath, num, conf))
		except Exception:
			numbered.append((fpath, None, 0))

	# Count how many got numbers
	got_numbers = [(fp, n, c) for fp, n, c in numbered if n is not None]

	if len(got_numbers) >= len(files) * 0.6:
		# Enough pages have detectable numbers → sort by number
		numbered.sort(key=lambda x: (x[1] is None, x[1] or 9999))
		sorted_files = [fp for fp, _, _ in numbered]
		order_str = ' → '.join(f"{Path(fp).stem}#{n}" if n else f"{Path(fp).stem}#?"
		                       for fp, n, _ in numbered)
		return sorted_files, f"页码排序: {order_str}"
	else:
		# Fall back to filename sort
		files.sort(key=lambda x: Path(x).stem)
		return files, "按文件名排序 (页码检测不足60%)"


def convert_to_png(tiff_path, tmp_dir):
    """Convert TIFF to 8-bit PNG using sips + PIL."""
    from PIL import Image
    base = Path(tiff_path).stem
    png_tmp = tmp_dir / f"{base}.png"
    subprocess.run(["sips", "-s", "format", "png", str(tiff_path), "--out", str(png_tmp)],
                   check=True, capture_output=True)
    img = Image.open(png_tmp).convert('L')
    return img, png_tmp


def remove_watermark(binary, config):
    """Detect and remove watermark from binary image."""
    import numpy as np
    wm_cfg = config["watermark"]
    h, w = binary.shape
    crop = wm_cfg["crop_bottom"]

    # Scan from bottom to find watermark band
    gray_lo, gray_hi = wm_cfg["gray_range"]
    watermark_rows = []
    for row_idx in range(h - 1, max(0, h - wm_cfg["bottom_scan_rows"]), -1):
        row = binary[row_idx, :]
        gray_pixels = (row > gray_lo) & (row < gray_hi)
        gray_ratio = gray_pixels.mean()
        dark_pixels = (row < 40).mean()
        if gray_ratio > wm_cfg["gray_ratio_threshold"] and dark_pixels < wm_cfg["dark_ratio_max"]:
            watermark_rows.append(row_idx)
        elif len(watermark_rows) > 0:
            break

    if watermark_rows:
        for row_idx in watermark_rows:
            mask = (binary[row_idx, :] > gray_lo) & (binary[row_idx, :] < gray_hi)
            binary[row_idx, mask] = 255
        crop = max(crop, h - min(watermark_rows))

    # Also white-out bottom crop
    binary[-crop:, :] = 255
    return binary, len(watermark_rows)


def ocr_image(img, config):
    """Run OCR on a PIL image."""
    import pytesseract
    lang = config["ocr"]["lang"]
    psm_cfg = config["ocr"]["psm"]

    if psm_cfg == "auto":
        # Try PSM 6 first, fall back to 3
        for psm in [6, 3, 4]:
            text = pytesseract.image_to_string(img, lang=lang, config=f'--psm {psm}')
            cjk = len(re.findall(r'[一-鿿]', text))
            if cjk > config["ocr"]["fallback_threshold"]:
                return text
        return pytesseract.image_to_string(img, lang=lang, config='--psm 6')
    else:
        return pytesseract.image_to_string(img, lang=lang, config=f'--psm {psm_cfg}')


def post_process(text, config):
    """Filter garbled lines and watermark residues."""
    pp_cfg = config["postprocessing"]
    lines = text.split('\n')
    clean = []

    for line in lines:
        s = line.strip()
        if not s:
            clean.append('')
            continue

        # Check for watermark keywords
        if any(kw in s for kw in pp_cfg["watermark_keywords"]):
            continue

        # Check CJK ratio
        cjk = len(re.findall(r'[一-鿿]', s))
        alpha = len(re.findall(r'[a-zA-Z]', s))
        digits = len(re.findall(r'[0-9]', s))
        meaningful = cjk + alpha + digits
        if meaningful == 0:
            continue
        if meaningful < 5 and cjk < 3:
            continue

        # Reject lines with low CJK ratio in Chinese context
        if meaningful > 10 and cjk / meaningful < pp_cfg["min_cjk_ratio"]:
            continue

        clean.append(s)

    text = '\n'.join(clean)
    text = re.sub(r'\n{' + str(pp_cfg["max_blank_lines"] + 1) + r',}',
                  '\n' * pp_cfg["max_blank_lines"], text)
    return text


# OCR Confusion Map: Tesseract chi_sim common mistakes
# Each entry: (wrong, correct, context_word_for_validation, priority)
# context_word: the word that SHOULD exist if the correction is right
OCR_CONFUSION_MAP = [
	# High-frequency errors (priority 1)
	("赁", "凭", "文凭", 1),
	("赁", "凭", "凭什么", 1),
	("焚", "婪", "贪婪", 1),
	("焚", "婪", "婪", 1),
	# Visual confusion (priority 2)
	("约想", "幻想", "幻想", 2),
	("打吕", "打骂", "打骂", 2),
	("恺吓", "恐吓", "恐吓", 2),
	("礼狐", "礼貌", "礼貌", 2),
	("窝吉", "窝囊", "窝囊", 2),
	("写囊", "窝囊", "窝囊", 2),
	("窝赛", "窝囊", "窝囊", 2),
	("妃不到", "追不到", "追不到", 2),
	("博她", "抱怨", "抱怨", 2),
	("抱她", "抱怨", "抱怨", 2),
	("春了", "蠢了", "蠢了", 2),
	("自己春", "自己蠢", "自己蠢", 2),
	("平良", "平庸", "平庸", 2),
	("出三", "出身", "出身", 2),
	("出首", "出生", "出生", 2),
	("富台", "富豪", "富豪", 2),
	("高台", "富豪", "富豪", 2),
	("晶着", "跟着", "跟着", 2),
	("文任", "文凭", "文凭", 2),
	("花休", "花朵", "花朵", 2),
	("老沟", "老师", "老师", 2),
	("搓衣板", "搓衣板", "搓衣板", 2),  # actually 搓衣板 is correct, skip
	("脐想", "臆想", "臆想", 2),
	("狐金", "氩弧", "氩弧焊", 2),
	("洪艇", "潜艇", "潜艇", 2),
	("月靳", "月薪", "月薪", 2),
	("干三", "千三", "三千", 2),
	("囊代", "宋代", "宋代", 2),
	("赁什么", "凭什么", "凭什么", 2),
	("笑睐上", "笑眯眯", "笑眯眯", 2),
	("多枉", "冤枉", "冤枉", 2),
	("梦而不得志", "郁郁不得志", "郁郁不得志", 2),
	("海豚文化", "躺平文化", "躺平", 2),
	("引种", "喷子", "杠精", 2),
	("自治", "自在", "自在", 2),
	# Context-specific substitutions using regex (priority 3)
	(r'(?<=贪)焚(?=\w)', "婪", "", 3),
	(r'(?<=文)任(?=\W)', "凭", "", 3),
	(r'(?<=富)台(?=\W)', "豪", "", 3),
]


def auto_correct_text(text, config):
	"""Apply OCR error corrections with context validation."""
	ac_cfg = config.get("auto_correct", {})
	if not ac_cfg.get("enabled", True):
		return text

	corrected = text

	# Phase 1: Direct substitutions (priority 1-2, high confidence)
	for entry in OCR_CONFUSION_MAP:
		# Skip regex entries (handled in Phase 2)
		if len(entry) < 3:
			continue
		wrong, right, _context, priority = entry
		if wrong in corrected:
			# Priority 1: always apply (highest confidence)
			# Priority 2: apply directly (well-studied OCR errors)
			corrected = corrected.replace(wrong, right)

	# Phase 2: Regex-based corrections
	regex_corrections = [
		(re.compile(r'贪焚'), '贪婪'),
		(re.compile(r'(?<=[^的])文任(?=[，。\s])'), '文凭'),
		(re.compile(r'富台'), '富豪'),
		(re.compile(r'写囊费'), '窝囊费'),
		(re.compile(r'窝赛安奈费'), '窝囊费'),
		(re.compile(r'窝吉费'), '窝囊费'),
	]
	for pattern, replacement in regex_corrections:
		corrected = pattern.sub(replacement, corrected)

	# Phase 3: User-defined extra corrections from config
	extra = ac_cfg.get("extra_corrections", {})
	for wrong, right in extra.items():
		if wrong in corrected:
			corrected = corrected.replace(wrong, right)

	return corrected


def quality_score(text, img_shape):
    """Calculate quality score for OCR output."""
    if not text: return 0.0

    cjk = len(re.findall(r'[一-鿿]', text))
    total = len(text.replace(' ', '').replace('\n', ''))
    if total == 0: return 0.0

    cjk_ratio = cjk / total
    # Expect >50% CJK for Chinese docs
    cjk_score = min(cjk_ratio / 0.5, 1.0) if cjk_ratio > 0 else 0

    # Character density per pixel
    h, w = img_shape[:2]
    density = total / (h * w)
    density_score = min(density / 0.005, 1.0) if density < 0.01 else max(0, 1.0 - density / 0.1)

    # Garbled line detection
    lines = text.split('\n')
    garbled = sum(1 for l in lines if l.strip() and len(re.findall(r'[一-鿿]', l)) == 0
                  and len(re.findall(r'[a-zA-Z]', l)) > 5)
    garbled_ratio = garbled / max(len(lines), 1)
    garbled_score = max(0, 1.0 - garbled_ratio * 10)

    return round(0.5 * cjk_score + 0.3 * density_score + 0.2 * garbled_score, 3)


def process_image(filepath, tmp_dir, config):
    """Process a single image through the full pipeline."""
    from PIL import Image
    import numpy as np
    import pytesseract

    # Step 1: Format normalization
    img, png_path = convert_to_png(filepath, tmp_dir)
    arr = np.array(img).astype(float)
    h, w = arr.shape

    # Step 2: Preprocessing
    pp_cfg = config["preprocessing"]
    if pp_cfg["contrast_stretch"]:
        p5, p95 = np.percentile(arr, 5), np.percentile(arr, 95)
        arr = np.clip((arr - p5) * 255.0 / max(p95 - p5, 1), 0, 255)

    use_otsu = pp_cfg["otsu_binarize"]
    if use_otsu:
        thresh = otsu_threshold(arr.astype(np.uint8))
        binary = (arr > thresh).astype(np.uint8) * 255
    else:
        binary = arr.astype(np.uint8)

    # Step 3: Watermark removal
    wm_rows = 0
    if config["watermark"]["enabled"]:
        binary, wm_rows = remove_watermark(binary, config)

    ocr_img = Image.fromarray(binary)

    # Step 4: OCR
    text = ocr_image(ocr_img, config)

    # If Otsu produced too little text, try raw grayscale
    if use_otsu and len(text) < pp_cfg["otsu_skip_chars_threshold"]:
        raw_img = Image.fromarray(arr.astype(np.uint8))
        if config["watermark"]["enabled"]:
            raw_arr = arr.astype(np.uint8)
            raw_arr[-config["watermark"]["crop_bottom"]:, :] = 255
            raw_img = Image.fromarray(raw_arr)
        text = ocr_image(raw_img, config)

    # Step 5: Post-processing
    text = post_process(text, config)

    # Step 6: Auto-correction
    text = auto_correct_text(text, config)

    # Quality
    qs = quality_score(text, binary.shape)

    return Path(filepath).stem, text, qs, {"wm_rows": wm_rows, "shape": (h, w)}


def deduplicate(results):
    """MD5-based dedup of image files. Returns unique results."""
    import hashlib
    seen = {}
    unique = []
    for fname, text, qs, meta in results:
        # Hash the text content for dedup
        h = hashlib.md5(text.encode()).hexdigest()[:12]
        if h not in seen:
            seen[h] = fname
            unique.append((fname, text, qs, meta))
    return unique


def merge_consecutive(results):
    """Detect and merge consecutive content (split slides)."""
    merged = []
    i = 0
    while i < len(results):
        fname, text, qs, meta = results[i]
        # Check if next item continues this one (ends without punctuation)
        if i + 1 < len(results):
            next_fname, next_text, next_qs, next_meta = results[i + 1]
            # If current ends mid-sentence and next starts mid-sentence
            cur_end = text.strip()[-30:] if text.strip() else ""
            next_start = next_text.strip()[:30] if next_text.strip() else ""
            if (cur_end and not re.search(r'[。！？…」』\n]$', cur_end.strip()) and
                next_start and not re.search(r'^[「『#]', next_start.strip())):
                merged_text = text.strip() + '\n' + next_text.strip()
                merged_qs = (qs + next_qs) / 2
                merged.append((f"{fname}+{next_fname}", merged_text, merged_qs, meta))
                i += 2
                continue
        merged.append((fname, text, qs, meta))
        i += 1
    return merged


def build_markdown(results, title="OCR 提取结果"):
    """Build structured markdown from OCR results."""
    lines = [
        "---",
        f"tags: [ocr, auto-generated]",
        f"created: {datetime.now().strftime('%Y-%m-%d')}",
        "---",
        "",
        f"# {title}",
        "",
        f"> 由 ocr-extractor 自动生成，共 {len(results)} 张图片。",
        "",
        "---",
        ""
    ]

    for i, (fname, text, qs, meta) in enumerate(results, 1):
        # Try to extract a section header from first meaningful line
        first_line = ""
        for line in text.split('\n'):
            s = line.strip()
            if len(s) > 5:
                first_line = s[:40]
                break

        lines.append(f"## 第{i}节")
        lines.append("")
        lines.append(text.strip())
        lines.append("")
        if qs > 0:
            lines.append(f"> 质量: {qs*100:.0f}% | 来源: {fname}")
        lines.append("")
        lines.append("---")
        lines.append("")

    return '\n'.join(lines)


def log_usage(config, results, elapsed, args):
    """Log processing run for self-improvement."""
    if not config["self_improve"]["log_usage"]:
        return

    entry = {
        "timestamp": datetime.now().isoformat(),
        "input_count": len(results),
        "total_chars": sum(len(t) for _, t, _, _ in results),
        "avg_quality_score": round(sum(q for _, _, q, _ in results) / max(len(results), 1), 3),
        "elapsed_seconds": round(elapsed, 1),
        "config_snapshot": {
            "wm_crop": config["watermark"]["crop_bottom"],
            "otsu": config["preprocessing"]["otsu_binarize"],
            "psm": config["ocr"]["psm"]
        },
        "args": vars(args)
    }

    USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_LOG_PATH, 'a') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def maybe_auto_improve(config, results):
    """Auto-trigger self-improvement after enough usage data accumulates."""
    si_cfg = config.get("self_improve", {})
    if not si_cfg.get("enabled") or not si_cfg.get("auto_tune_thresholds"):
        return

    # Track last improvement time
    state_path = SKILL_DIR / "improve_state.json"
    last_improved = None
    if state_path.exists():
        try:
            with open(state_path) as f:
                state = json.load(f)
            last_improved = state.get("last_improved_at")
        except: pass

    # Don't run more than once per hour
    if last_improved:
        last_dt = datetime.fromisoformat(last_improved)
        if (datetime.now() - last_dt).total_seconds() < 3600:
            return

    # Check if we have enough new records
    if not USAGE_LOG_PATH.exists():
        return
    with open(USAGE_LOG_PATH) as f:
        entries = [json.loads(l) for l in f if l.strip()]

    min_samples = si_cfg.get("min_samples_for_tuning", 5)
    # Only count records since last improvement
    if last_improved:
        entries = [e for e in entries if e["timestamp"] > last_improved]

    if len(entries) < min_samples:
        return

    # Check if quality is declining (need for improvement)
    recent_qs = [e["avg_quality_score"] for e in entries[-5:]]
    avg_recent = sum(recent_qs) / len(recent_qs)

    if avg_recent < 0.7:  # Quality below 70% - worth optimizing
        print(f"\n🤖 检测到近期质量偏低 ({avg_recent*100:.0f}%)，自动触发优化...")
        sys.path.insert(0, str(SKILL_DIR))
        from scripts.self_improve import run_improvement
        suggestions = run_improvement()
        if suggestions:
            # Update state
            with open(state_path, 'w') as f:
                json.dump({"last_improved_at": datetime.now().isoformat()}, f)
            print(f"✅ 自动优化已应用，下次运行将使用新参数。")
        else:
            print("✅ 参数已是最优，无需调整。")


def main():
    parser = argparse.ArgumentParser(description="OCR Extractor - 图片转中文 Markdown")
    parser.add_argument("paths", nargs="*", help="Image files or directories")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--title", "-t", default="OCR 提取结果", help="Document title")
    parser.add_argument("--lang", default="chi_sim", help="Tesseract language (default: chi_sim)")
    parser.add_argument("--no-watermark", action="store_true", help="Disable watermark removal")
    parser.add_argument("--no-otsu", action="store_true", help="Disable Otsu binarization")
    parser.add_argument("--check-deps", action="store_true", help="Check dependencies")
    parser.add_argument("--config", action="store_true", help="Print current config")
    parser.add_argument("--improve", action="store_true", help="Run self-improvement")
    parser.add_argument("--force", action="store_true", help="Force self-improvement (bypass cooldown)")
    parser.add_argument("--stats", action="store_true", help="Show usage statistics")
    parser.add_argument("--no-sort", action="store_true", help="Disable auto page-number sorting")
    parser.add_argument("--no-auto-correct", action="store_true", help="Disable auto OCR error correction")
    parser.add_argument("--stdout", action="store_true", help="Output to stdout only")

    args = parser.parse_args()

    if args.check_deps:
        sys.exit(0 if check_deps() else 1)

    if args.config:
        cfg = load_config()
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return

    if args.stats:
        if USAGE_LOG_PATH.exists():
            with open(USAGE_LOG_PATH) as f:
                entries = [json.loads(l) for l in f if l.strip()]
            print(f"📊 使用统计 (共 {len(entries)} 次):")
            total_chars = sum(e["total_chars"] for e in entries)
            avg_qs = sum(e["avg_quality_score"] for e in entries) / max(len(entries), 1)
            print(f"  总处理页数: {sum(e['input_count'] for e in entries)}")
            print(f"  总字符数: {total_chars:,}")
            print(f"  平均质量: {avg_qs*100:.1f}%")
        else:
            print("尚无使用记录。")
        return

    if args.improve:
        sys.path.insert(0, str(SKILL_DIR))
        from scripts.self_improve import run_improvement
        run_improvement(force=args.force)
        return

    if not args.paths:
        parser.print_help()
        return

    start_time = time.time()
    config = load_config()

    # Override config with CLI args
    config["ocr"]["lang"] = args.lang
    if args.no_watermark:
        config["watermark"]["enabled"] = False
    if args.no_otsu:
        config["preprocessing"]["otsu_binarize"] = False
    if args.no_auto_correct:
        if "auto_correct" not in config:
            config["auto_correct"] = {}
        config["auto_correct"]["enabled"] = False

    # Find images
    image_files = find_images(args.paths)
    if not image_files:
        print("❌ 未找到图片文件。支持的格式: TIFF, PNG, JPG")
        sys.exit(1)

    print(f"📷 找到 {len(image_files)} 张图片")

    # Create temp directory
    import tempfile
    tmp_dir = Path(tempfile.mkdtemp(prefix="ocr_"))

    # Sort by page number (enabled by default, use --no-sort to disable)
    if not args.no_sort:
        print("🔢 检测页码并排序...")
        image_files, sort_report = sort_images_by_pagenum(image_files, tmp_dir, config)
        print(f"   {sort_report}")

    try:
        # Process all images
        results = []
        for i, fpath in enumerate(image_files, 1):
            print(f"  [{i}/{len(image_files)}] {Path(fpath).name} ...", end=" ", flush=True)
            try:
                fname, text, qs, meta = process_image(fpath, tmp_dir, config)
                results.append((fname, text, qs, meta))
                print(f"✓ {len(text)} chars, qs={qs*100:.0f}%")
            except Exception as e:
                print(f"✗ {e}")

        if not results:
            print("❌ 没有成功处理的图片。")
            sys.exit(1)

        # Dedup
        before = len(results)
        results = deduplicate(results)
        if before != len(results):
            print(f"🔍 去重: {before} → {len(results)} (移除 {before - len(results)} 张重复)")

        # Merge consecutive
        before = len(results)
        results = merge_consecutive(results)
        if before != len(results):
            print(f"🔗 合并: {before} → {len(results)} (合并 {before - len(results)} 对)")

        # Build markdown
        md = build_markdown(results, args.title)

        # Output
        if args.stdout:
            print("\n" + md)
        elif args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{args.title}.md"
            with open(out_path, 'w') as f:
                f.write(md)
            print(f"\n✅ 输出: {out_path}")
        else:
            # Default: write alongside first input
            first_input = Path(image_files[0])
            out_dir = first_input.parent if first_input.is_file() else first_input
            out_path = out_dir / "ocr-output.md"
            with open(out_path, 'w') as f:
                f.write(md)
            print(f"\n✅ 输出: {out_path}")

        # Log
        elapsed = time.time() - start_time
        log_usage(config, results, elapsed, args)

        # Auto-improve check (runs after logging, before cleanup)
        maybe_auto_improve(config, results)

        avg_qs = sum(q for _, _, q, _ in results) / len(results)
        total_chars = sum(len(t) for _, t, _, _ in results)
        print(f"📊 {len(results)} 页, {total_chars} 字符, 平均质量 {avg_qs*100:.0f}%, "
              f"耗时 {elapsed:.1f}s")

    finally:
        # Cleanup temp
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

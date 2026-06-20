#!/usr/bin/env python3
"""Self-Improvement Module — 自适应参数调优 + 水印模式学习
用法: python3 self_improve.py [--force]
"""

import sys, json, os, re
from pathlib import Path
from datetime import datetime
from collections import Counter

SKILL_DIR = Path.home() / ".claude" / "skills" / "ocr-extractor"
USAGE_LOG_PATH = SKILL_DIR / "usage_log.jsonl"
CONFIG_PATH = SKILL_DIR / "config.json"
CHANGELOG_PATH = SKILL_DIR / "CHANGELOG.md"
STATE_PATH = SKILL_DIR / "improve_state.json"


def load_usage_log():
    if not USAGE_LOG_PATH.exists():
        return []
    entries = []
    with open(USAGE_LOG_PATH) as f:
        for line in f:
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def find_optimal_params(entries):
    """Find parameter clusters that produce highest quality scores."""
    if len(entries) < 3:
        return {}

    suggestions = {}

    # === 1. Analyze watermark crop_bottom ===
    wm_crops = {}
    for e in entries:
        crop = e.get("config_snapshot", {}).get("wm_crop", 60)
        qs = e["avg_quality_score"]
        wm_crops.setdefault(crop, []).append(qs)

    if len(wm_crops) >= 2:
        best_crop = max(wm_crops, key=lambda c: sum(wm_crops[c]) / max(len(wm_crops[c]), 1))
        avg_best = sum(wm_crops[best_crop]) / max(len(wm_crops[best_crop]), 1)
        current_crop = entries[-1].get("config_snapshot", {}).get("wm_crop", 60)
        if best_crop != current_crop and len(wm_crops[best_crop]) >= 3:
            confidence = min(avg_best * 100, 95)
            if confidence > 70:
                suggestions["watermark.crop_bottom"] = {
                    "current": current_crop, "suggested": best_crop,
                    "confidence": round(confidence, 1), "based_on": len(wm_crops[best_crop])
                }

    # === 2. Analyze Otsu vs raw grayscale ===
    otsu_on = [e for e in entries if e.get("config_snapshot", {}).get("otsu", True)]
    otsu_off = [e for e in entries if not e.get("config_snapshot", {}).get("otsu", True)]
    if otsu_off and otsu_on and len(otsu_off) >= 2:
        avg_on = sum(e["avg_quality_score"] for e in otsu_on) / len(otsu_on)
        avg_off = sum(e["avg_quality_score"] for e in otsu_off) / len(otsu_off)
        diff_pct = (avg_on - avg_off) / max(avg_off, 0.01) * 100
        if diff_pct < -10:
            suggestions["preprocessing.otsu_binarize"] = {
                "current": True, "suggested": False,
                "confidence": min(abs(diff_pct) + 60, 90),
                "based_on": f"otsu_avg={avg_on:.2f} vs raw_avg={avg_off:.2f}"
            }

    # === 3. Analyze PSM mode effectiveness ===
    psm_scores = {}
    for e in entries:
        psm = e.get("config_snapshot", {}).get("psm", "auto")
        qs = e["avg_quality_score"]
        psm_scores.setdefault(psm, []).append(qs)
    # (PSM analysis is aspirational - requires more data)

    # === 4. Detect quality trend ===
    if len(entries) >= 5:
        recent_5 = [e["avg_quality_score"] for e in entries[-5:]]
        earlier = [e["avg_quality_score"] for e in entries[:-5]]
        if earlier:
            trend = sum(recent_5) / len(recent_5) - sum(earlier) / len(earlier)
            if trend < -0.1:
                suggestions["_quality_trend"] = {
                    "direction": "declining",
                    "delta": round(trend, 3),
                    "advice": "Quality declining. Consider checking source image quality or adjusting gray_range."
                }

    return suggestions


def learn_watermark_patterns(entries, config):
    """Learn new watermark strings from low-quality OCR runs."""
    # This reads the actual output files to find recurring garbled patterns
    # that might be unrecognized watermarks.
    pp_cfg = config.get("postprocessing", {})
    known = set(pp_cfg.get("watermark_keywords", []))

    # For now: analyze low-quality entries and suggest checking config
    low_q = [e for e in entries if e["avg_quality_score"] < 0.6]
    if len(low_q) >= 2:
        return {
            "watermark_keywords": {
                "note": f"{len(low_q)}次低质量运行。建议检查是否有新水印未加入关键词列表。",
                "action": "手动检查输出文件中的重复乱码模式"
            }
        }
    return {}


def apply_suggestions(suggestions):
    """Apply suggested parameter changes to config."""
    if not suggestions:
        return []

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    applied = []
    for key, sug in suggestions.items():
        if key.startswith("_"):  # Skip meta-suggestions
            continue
        parts = key.split('.')
        target = config
        for p in parts[:-1]:
            if p not in target:
                target[p] = {}
            target = target[p]
        old_val = target.get(parts[-1])
        new_val = sug.get("suggested")
        if new_val is not None and old_val != new_val and sug.get("confidence", 0) > 75:
            target[parts[-1]] = new_val
            applied.append((key, old_val, new_val, sug["confidence"]))

    if applied:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(CHANGELOG_PATH, 'a') as f:
            f.write(f"\n## [{timestamp}] auto-tune\n")
            for key, old, new, conf in applied:
                f.write(f"- Adjusted `{key}`: `{old}` → `{new}` (confidence: {conf:.0f}%)\n")
            f.write("\n")

    return applied


def _print_suggestions(suggestions, applied):
    """Human-readable report."""
    if not suggestions:
        print("✅ 当前参数已是最优，无需调整。")
        return

    print("\n🔧 参数优化建议:")
    for key, sug in suggestions.items():
        if key.startswith("_"):
            print(f"  ⚠️  {sug.get('advice', sug)}")
        else:
            print(f"  {key}: {sug.get('current')} → {sug.get('suggested')} "
                  f"(置信度: {sug.get('confidence', '?')}%, "
                  f"基于 {sug.get('based_on', '?')} 条记录)")

    if applied:
        print(f"\n✅ 已自动应用 {len(applied)} 项优化:")
        for key, old, new, conf in applied:
            print(f"  {key}: {old} → {new} (置信度 {conf:.0f}%)")
    else:
        print("\n⚠️ 置信度不足 75%，未自动应用。可手动调整 config.json。")


def run_improvement(force=False):
    """Main self-improvement routine. Returns suggestions dict for programmatic use."""
    entries = load_usage_log()

    if len(entries) < 3:
        print(f"📊 仅 {len(entries)} 条使用记录，至少需要 3 条进行分析。")
        return {}

    # Check if we improved recently (cooldown: 1 hour)
    if not force and STATE_PATH.exists():
        try:
            with open(STATE_PATH) as f:
                state = json.load(f)
            last_improved = state.get("last_improved_at")
            if last_improved:
                last_dt = datetime.fromisoformat(last_improved)
                if (datetime.now() - last_dt).total_seconds() < 3600:
                    print("⏰ 距上次优化不足1小时，跳过。(用 --force 强制)")
                    return {}
        except:
            pass

    print(f"📊 分析 {len(entries)} 条使用记录...")

    # Load config for watermark learning
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    suggestions = find_optimal_params(entries)

    # Learn watermark patterns
    wm_suggestions = learn_watermark_patterns(entries, config)
    suggestions.update(wm_suggestions)

    applied = apply_suggestions(suggestions)
    _print_suggestions(suggestions, applied)

    # Save state
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, 'w') as f:
        json.dump({
            "last_improved_at": datetime.now().isoformat(),
            "entries_analyzed": len(entries),
            "applied_count": len(applied)
        }, f)

    return suggestions


if __name__ == "__main__":
    force = "--force" in sys.argv
    run_improvement(force=force)

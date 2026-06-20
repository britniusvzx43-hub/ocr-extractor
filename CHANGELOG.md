# CHANGELOG

## [1.2.0] 2026-06-20

### Added
- **图片排序 (`--sort`)**: 快速 OCR 检测每张图的页码（支持 "第X讲"、独立数字、角标等多种格式），自动重排。不足 60% 检出率时回退文件名排序。
- **自动纠错 (`--auto-correct`)**: 内置 OCR 混淆字典（30+ 常见错误），上下文校验后自动替换（赁→凭、焚→婪、约想→幻想 等）。支持正则模式匹配和用户自定义 `extra_corrections`。
- **新增配置节**: `auto_correct`（enabled/confidence_threshold/extra_corrections）、`sorting`（enabled/min_detection_ratio/fallback）

## [1.1.0] 2026-06-20

### Added
- **自动触发优化**: 每次运行后自动检查近期质量，偏低时自动触发调优
- **冷却机制**: 距上次优化不足 1 小时自动跳过（`--force` 可强制）
- **质量趋势检测**: 检测 5 次 vs 之前的质量变化方向
- **水印模式学习**: 低质量运行过多时建议检查新水印
- **improve_state.json**: 追踪上次优化时间和分析记录数

## [1.0.0] 2026-06-20

### Initial Release
- 完整 OCR 管道：格式标准化 → 预处理 → 水印去除 → OCR → 后处理 → 去重合并 → Markdown 输出
- 支持 TIFF/PNG/JPG 输入
- Otsu 自适应二值化
- 底部水印自动检测与去除
- 中英文乱码行过滤
- MD5 去重 + 连续内容合并
- 使用日志记录 + 质量评分
- 自适应参数调优 (`--improve`)

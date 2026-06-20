# Tesseract 配置参考

## PSM 模式

| PSM | 名称 | 适用场景 |
|-----|------|---------|
| 3 | Fully automatic | 默认，适合大多数情况 |
| 4 | Single column | 单栏文本 |
| 6 | Uniform block | 统一文本块，适合 slides |
| 7 | Single line | 单行文本 |
| 8 | Single word | 单词识别 |

推荐：中文文档使用 `--psm 6` 或 `--psm 3`。

## 中文语言包

```bash
# 检查已安装
tesseract --list-langs | grep chi

# 安装简体中文
brew install tesseract-lang
# 或手动下载: https://github.com/tesseract-ocr/tessdata
```

## 常见问题

### 16-bit TIFF 无法读取
PIL 不能直接打开某些 TIFF 变体。使用 `sips` 转换为 PNG 后再处理。

### OCR 乱码
- 确认语言包正确 (`chi_sim` vs `chi_tra`)
- 检查图片预处理（二值化阈值不合适会导致文字丢失）
- 尝试不同的 PSM 模式

### 大图片处理慢
- 大于 4000px 的图片建议缩放到 2000px 以内
- `sips -Z 2000 image.tiff`

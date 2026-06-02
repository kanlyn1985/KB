# MiniMax 多模态支持核查结论

## 结论

当前项目 `.env` 中配置的 MiniMax 接口：

- `OPENAI_BASE_URL=https://api.minimaxi.com/anthropic`
- `LLM_MODEL=MiniMax-M2.7`

不适合直接用于图片/PDF OCR。

原因不是“模型识别质量一般”，而是**当前使用的兼容接口本身不支持这类输入**。

---

## 官方文档结论

### 1. Anthropic API 兼容

MiniMax 官方文档写明：

- `messages` 参数“支持文本和工具调用，**不支持图像和文档输入**”

来源：

- [Anthropic API 兼容 - MiniMax 开放平台文档中心](https://platform.minimaxi.com/docs/api-reference/text-anthropic-api)

### 2. OpenAI API 兼容

MiniMax 官方文档写明：

- “**当前不支持图像和音频类型的输入**”

来源：

- [OpenAI API 兼容 - MiniMax 开放平台文档中心](https://platform.minimaxi.com/docs/api-reference/text-openai-api)

### 3. 接口概览

官方接口概览页将：

- 文本生成
- 图像生成
- 视频生成
- 文件管理

分为不同能力域。  
这也说明“文本模型兼容接口”和“图像/视频能力接口”不是同一个入口。

来源：

- [接口概览 - MiniMax 开放平台文档中心](https://platform.minimaxi.com/docs/api-reference/api-overview)

---

## 这意味着什么

### 不是“模型不支持图片识别”

不能直接得出这个结论。

更准确的结论是：

- 当前项目使用的 **Anthropic/OpenAI 兼容文本接口**
- **不支持图片/PDF 多模态输入**

所以我们之前把 PNG 或 PDF 塞进 `messages` 请求里时，得到“模型像是没看到图片”的结果，是符合官方文档的。

### 是“当前接口不支持”

也就是说：

- 不是 OCR 效果差
- 不是识别质量一般
- 而是这条调用链本身不成立

---

## 对当前项目的直接影响

当前 `.env` 里的 MiniMax 配置只能稳定用于：

- query rewrite
- answer policy
- diagnostics / 分析
- 局部文本增强

不适用于：

- 图片 OCR
- PDF 直读
- 整页图像转文本

---

## 工程建议

### 可继续保留的方向

当前最合理的方向仍然是：

- `PaddleVL` 负责看结构、看图、看表格
- `MiniMax` 负责局部文本修复和结构增强

### 不建议继续投入的方向

不建议再尝试：

- 用当前 `api.minimaxi.com/anthropic`
- 或 MiniMax OpenAI 兼容文本接口

直接做整页图片 OCR。

---

## 最小核查脚本

已落地：

- [verify_minimax_multimodal_support.py](E:/AI_Project/opencode_workspace/KB1/scripts/verify_minimax_multimodal_support.py)

该脚本会：

1. 读取当前项目 `.env`
2. 验证 Anthropic 兼容文本调用是否可用
3. 生成结论 JSON：
   - `docs/minimax_multimodal_support_check_2026-04-19.json`


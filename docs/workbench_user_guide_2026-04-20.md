# 企业级知识库工作台使用说明

## 1. 目的

本文档说明当前 `KB1` 工作台的三类核心入口：

- 单独 PDF 转换
- 文档构建入库
- 一键构建并测试

并给出推荐使用流程、CLI/API/页面用法，以及各阶段输出产物说明。

---

## 2. 推荐使用流程

### 2.1 推荐给新文档的标准流程

建议按以下顺序操作：

1. 先做 `PDF 转换`
2. 检查转换结果和诊断
3. 再做 `构建入库`
4. 最后做 `构建并测试`

原因：

- PDF 转换是最耗时、最容易暴露问题的阶段
- 如果一开始就跑完整链路，出问题时排查成本更高
- 大 PDF 文档尤其建议先看转换结果再决定是否继续

### 2.2 三种入口的职责

| 入口 | 作用 | 是否入库 | 是否跑测试 |
|---|---|---:|---:|
| `转换` | 只做 PDF 解析/结构化中间结果 | 否 | 否 |
| `构建` | 解析 + quality + evidence + facts + entities + wiki + graph | 是 | 否 |
| `构建+测试` | 构建全链 + 黄金测试生成 + 黄金测试执行 | 是 | 是 |

---

## 3. 页面工作台用法

页面地址：

- `http://127.0.0.1:8000/demo`

### 3.1 导入与构建区域按钮

当前页面左侧“导入与构建”区域包含以下按钮：

- `上传并转换`
- `转换当前文档`
- `上传并构建`
- `重建当前文档`
- `上传并构建+测试`
- `构建+测试当前文档`

### 3.2 页面按钮适用场景

#### `上传并转换`

适合：

- 新 PDF 首次接入
- 想先看解析效果
- 不想立即触发后续入库和测试

#### `转换当前文档`

适合：

- 文档已在系统中
- 修改了转换逻辑后重新验证解析结果

#### `上传并构建`

适合：

- 新 PDF 接入后直接入库
- 不需要立即跑黄金测试

#### `重建当前文档`

适合：

- 文档已存在
- 修改了 facts / retrieval / answer 相关逻辑后重新构建

#### `上传并构建+测试`

适合：

- 新文档完整验收
- 希望一键跑到黄金测试完成

#### `构建+测试当前文档`

适合：

- 已入库文档的回归验证
- 发布前验收

### 3.3 页面状态显示

页面当前会显示：

- 服务健康状态
- 文档列表与状态
- 最近任务
- 审计日志
- 当前任务进度
- 文档详情
- 诊断信息
- 黄金集结果
- 黄金测试执行结果

如果触发 `构建+测试` 类型任务，步骤条中会出现：

- `golden_generate`
- `golden_run`

---

## 4. CLI 用法

工作目录为：

```powershell
E:\AI_Project\opencode_workspace\KB1
```

默认 workspace 为：

```powershell
knowledge_base
```

### 4.1 单独转换

对已注册文档做转换：

```powershell
python -m enterprise_agent_kb.cli --root knowledge_base convert-document --doc-id DOC-000001
```

对本地文件注册后只做转换：

```powershell
python -m enterprise_agent_kb.cli --root knowledge_base convert-file --file "E:\path\to\your.pdf"
```

### 4.2 构建入库

对已注册文档构建：

```powershell
python -m enterprise_agent_kb.cli --root knowledge_base build-document --doc-id DOC-000001
```

对本地文件注册并构建：

```powershell
python -m enterprise_agent_kb.cli --root knowledge_base build-file --file "E:\path\to\your.pdf"
```

### 4.3 构建并测试

对已注册文档执行一键到底：

```powershell
python -m enterprise_agent_kb.cli --root knowledge_base build-document-and-test --doc-id DOC-000001
```

对本地文件注册、构建并测试：

```powershell
python -m enterprise_agent_kb.cli --root knowledge_base build-file-and-test --file "E:\path\to\your.pdf"
```

---

## 5. HTTP API 用法

基础地址：

```text
http://127.0.0.1:8000
```

### 5.1 单独转换接口

#### 同步转换已注册文档

`POST /convert-document`

请求体：

```json
{
  "doc_id": "DOC-000001"
}
```

#### 异步转换已注册文档

`POST /start-convert-document`

请求体：

```json
{
  "doc_id": "DOC-000001"
}
```

#### 同步上传并转换

`POST /upload-convert`

请求体：

```json
{
  "filename": "example.pdf",
  "content_base64": "<base64>"
}
```

#### 异步上传并转换

`POST /start-upload-convert`

请求体：

```json
{
  "filename": "example.pdf",
  "content_base64": "<base64>"
}
```

### 5.2 构建接口

- `POST /build-document`
- `POST /start-build-document`
- `POST /upload-build`
- `POST /start-upload-build`

### 5.3 构建并测试接口

- `POST /build-document-and-test`
- `POST /start-build-document-and-test`
- `POST /upload-build-and-test`
- `POST /start-upload-build-and-test`

### 5.4 任务状态接口

`POST /job-status`

请求体：

```json
{
  "job_id": "api-job-xxxx"
}
```

---

## 6. 输出产物说明

### 6.1 转换阶段输出

转换成功后主要输出到：

- `knowledge_base/normalized/`

典型文件包括：

- `{doc_id}.json`
- `{doc_id}.doc_ir.json`
- `{doc_id}.cleaned_doc_ir.json`

如果是大 PDF，还会在项目 `tmp/` 下生成预处理缓存：

- `tmp/minimax_preprocessed/...`

### 6.2 构建阶段输出

构建会额外生成：

- `knowledge_base/evidence/`
- `knowledge_base/facts/`
- `knowledge_base/wiki/`
- `knowledge_base/quality_reports/`

### 6.3 构建并测试阶段输出

会额外生成：

- 黄金测试 JSON
- 生成的 pytest 文件
- 黄金测试执行结果

相关文件通常位于：

- `tests/generated/`
- `docs/`

---

## 7. 什么时候用哪种入口

### 7.1 只想看 PDF 解析效果

用：

- 页面：`上传并转换`
- 页面：`转换当前文档`
- CLI：`convert-file`
- CLI：`convert-document`
- API：`/upload-convert`
- API：`/convert-document`

### 7.2 想重新入库某个已存在文档

用：

- 页面：`重建当前文档`
- CLI：`build-document`
- API：`/build-document`

### 7.3 想做完整验收

用：

- 页面：`构建+测试当前文档`
- CLI：`build-document-and-test`
- API：`/build-document-and-test`

### 7.4 新文档首次验收

建议：

1. `上传并转换`
2. 查看诊断与转换结果
3. `上传并构建+测试`

---

## 8. 当前已知边界

### 8.1 大 PDF 文档

大 PDF 目前已经支持：

- 分块
- 转图片
- MiniMax OCR 缓存

但首次处理仍可能耗时较长，建议优先使用“单独转换”入口先观察效果。

### 8.2 参数类问题

参数类检索已经明显改善，并已有参数回归测试集。  
但个别“单参数精确问法”仍可能需要持续精修。

### 8.3 本地服务

当前系统是本地工作台与本地 API 方案，不包含生产级鉴权、多租户隔离和外部服务编排。

---

## 9. 建议操作规范

建议日常按以下规范使用：

1. 新 PDF 先转换，不直接一键到底
2. 大 PDF 先检查 `normalized` 和 `diagnostics`
3. 验收前统一跑 `构建+测试`
4. 重要参数类问题加入参数回归集
5. 发布前至少运行一次参数回归脚本

参数回归脚本：

```powershell
python scripts\run_parameter_regression.py
```

---

## 10. 当前结论

当前工作台已经具备以下工程化能力：

- 单独 PDF 转换
- 单独文档构建
- 一键构建并测试
- 页面、CLI、API 三套一致入口
- 文档详情、诊断、黄金测试结果可视化
- 参数类回归测试能力

这意味着项目已经从“单纯 demo”进入“可操作、可验证、可交付”的阶段。

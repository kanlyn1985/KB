# KB1 交付快速开始

## 1. 三种使用方式

当前工作台支持三种模式：

### A. 只转换

适合：

- 新 PDF 首次接入
- 先检查解析效果
- 先看 `normalized / doc_ir / cleaned_doc_ir`

入口：

- 页面：`上传并转换` / `转换当前文档`
- CLI：
  - `convert-file`
  - `convert-document`
- API：
  - `/upload-convert`
  - `/convert-document`
  - `/start-upload-convert`
  - `/start-convert-document`

### B. 只构建

适合：

- 解析结果已经确认可用
- 想直接入库
- 暂时不跑测试

入口：

- 页面：`上传并构建` / `重建当前文档`
- CLI：
  - `build-file`
  - `build-document`
- API：
  - `/upload-build`
  - `/build-document`
  - `/start-upload-build`
  - `/start-build-document`

### C. 构建并测试

适合：

- 新文档验收
- 发版前回归
- 一键跑完整链

入口：

- 页面：`上传并构建+测试` / `构建+测试当前文档`
- CLI：
  - `build-file-and-test`
  - `build-document-and-test`
- API：
  - `/upload-build-and-test`
  - `/build-document-and-test`
  - `/start-upload-build-and-test`
  - `/start-build-document-and-test`

---

## 2. 推荐操作顺序

推荐顺序：

1. 先转换
2. 看诊断和转换结果
3. 再构建
4. 最后构建并测试

如果是大 PDF，这个顺序尤其重要。

---

## 3. 最常用命令

### 单独转换一个文件

```powershell
python -m enterprise_agent_kb.cli --root knowledge_base convert-file --file "E:\path\to\your.pdf"
```

### 构建一个已注册文档

```powershell
python -m enterprise_agent_kb.cli --root knowledge_base build-document --doc-id DOC-000001
```

### 一键构建并测试

```powershell
python -m enterprise_agent_kb.cli --root knowledge_base build-document-and-test --doc-id DOC-000001
```

---

## 4. 最常看输出

### 转换阶段

- `knowledge_base/normalized/{doc_id}.json`
- `knowledge_base/normalized/{doc_id}.doc_ir.json`
- `knowledge_base/normalized/{doc_id}.cleaned_doc_ir.json`

### 构建阶段

- `knowledge_base/evidence/`
- `knowledge_base/facts/`
- `knowledge_base/wiki/`
- `knowledge_base/quality_reports/`

### 测试阶段

- `tests/generated/`
- `docs/parameter_regression_report_2026-04-20.json`

---

## 5. 参数类回归

当前参数类回归脚本：

```powershell
python scripts\run_parameter_regression.py
```

当前已经覆盖的典型问题包括：

- `CC阻值有哪些`
- `检测点2相关参数有哪些`
- `CC1和CC2相关阻值有哪些`
- `R1等效电阻是多少`

---

## 6. 页面入口位置

页面：

```text
http://127.0.0.1:8000/demo
```

页面左侧“导入与构建”区域已经包含：

- 上传并转换
- 转换当前文档
- 上传并构建
- 重建当前文档
- 上传并构建+测试
- 构建+测试当前文档

---

## 7. 当前结论

当前 KB1 已具备：

- 单独转换
- 单独构建
- 一键构建并测试
- 页面 / CLI / API 三套一致入口
- 参数类回归验证

已经达到可操作、可验证、可交付状态。

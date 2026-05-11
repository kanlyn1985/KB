---
doc_type: feature-design
feature: 2026-05-10-evidence-display-sanitization
status: approved
summary: 统一 supporting evidence 展示清洗，避免渲染残留进入用户可见输出
roadmap: kb1-four-loop-hardening
roadmap_item: evidence-display-sanitization
tags:
  - answer
  - evidence
  - sanitization
---

# Evidence Display Sanitization Design

## 1. 目标

答案输出中的 direct answer 已经经过 `_clean_render_artifacts()`，但 supporting evidence 的 `snippet` 仍从 `normalized_text` 直接截断，可能把 `&nbsp;`、HTML entity、LaTeX delimiter、重复标点等渲染残留暴露给用户。

目标是在答案 API 的证据展示边界统一清洗 supporting evidence，不修改入库数据和召回排序。

## 2. 明确不做

- 不重写 evidence 表中的历史 `normalized_text`。
- 不改变 evidence selection、rerank 或 judge 逻辑。
- 不解决 evidence snippet 过长或同页段落混杂问题。
- 不改变 direct answer 模板。

## 3. 根因

`answer_api.answer_query()` 中 summary 和 direct answer 都会调用 `_clean_render_artifacts()`，但 `supporting_evidence` 的构建使用：

```python
"snippet": _truncate(item["normalized_text"], 600)
```

这导致同一次回答里 direct answer 干净，supporting evidence 仍可能携带 HTML/LaTeX/版面残留。

## 4. 方案

在 `answer_api` 的 `supporting_evidence` 输出边界复用 `_clean_render_artifacts()`：

```python
"snippet": _truncate(_clean_render_artifacts(str(item["normalized_text"] or "")), 600)
```

同时增强 `_clean_render_artifacts()`：

- 使用 `html.unescape()` 统一解码 HTML entity。
- 把 `\xa0` 转为空格。
- 保留既有 Markdown、LaTeX、HTML tag、重复标点和硬换行清理规则。

## 5. 验收场景

- `OBC输入过压怎么测` 的 direct answer 不含 `&nbsp;`、`$`、重复标点。
- 同一回答的 `supporting_evidence` JSON 不含 `&nbsp;`、`&#160;`、`&emsp;`、`$`、`；；`、`。。`。
- answer quality 的 render artifact 检测测试不受影响。

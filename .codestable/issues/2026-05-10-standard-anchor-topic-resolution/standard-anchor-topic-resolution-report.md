---
doc_type: issue-report
issue: 2026-05-10-standard-anchor-topic-resolution
status: fixed
summary: 标准号生命周期查询的 topic resolution 被其他 GB/T 引用片段带偏
tags:
  - retrieval
  - topic-resolution
  - graph
---

# Standard Anchor Topic Resolution Report

## 现象

查询 `GB/T 40432—2021 的实施日期是什么？` 时，topic resolution 曾命中包含 `GB/T 20234.3` 的控制导引过程实体，graph 随后沿 `has_process` 拉出控制导引表格事实。

## 影响

- graph 候选虽然存在且是 strong relation，但主题错误；
- graph contribution 显示 lost 或 retained 都不能代表真实有用贡献；
- 标准号查询可能被其他文档中的标准引用片段污染。

## 非根因

这不是某个标准号缺 alias，也不是 graph 权重不足。根因是 topic resolution 对标准号没有精确锚点约束，且 lifecycle graph 对标准号查询允许了 `has_process`。

# Agentic Knowledge Base — Interface Baselines

本目录保存模块之间的 Interface Control Document（ICD）和后续接口契约。

## 当前文档

- `Agentic_Knowledge_Base_ICD_V1.0.md` — 核心模块接口、输入输出、行为契约、错误、幂等、事务、异步 Job、事件、安全和验证要求。

## 基线关系

```text
SRS V1.1
   ↓
Canonical Data Model V1.0
   ↓
ICD V1.0
   ↓
Detailed Design
   ↓
Implementation
   ↓
Verification
```

ICD 当前状态：`Draft Design Baseline`。
正式冻结前必须完成接口 Schema、错误模型、版本兼容性和集成测试设计评审。

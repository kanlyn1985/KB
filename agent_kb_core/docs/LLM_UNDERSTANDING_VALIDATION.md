# LLM 语义分解（方案 D）验证结果（2026-08-18）

## 背景

规则匹配的语义分解存在短别名误匹配问题（"OBC水道设计"→ L-STATE/L-STRATEGY
误映射）。方案 D：规则匹配不确定时调用 LLM 把查询映射到骨架节点。

## 实现

- `src/agent_kb/query/llm_understanding.py`：LLM 查询→节点映射（白名单校验 + conf≥0.6）
- `understand_query` 新增 `use_llm` 选项（默认关闭），触发条件：
  - 无目标对象 / ≥2 个短别名冲突 / 泛词匹配（≤3 字符）
- LLM 目标合并优先；**网关故障安全回退**（LLM 失败 → 规则结果）

## 端到端验证（网关恢复后）

| 查询 | 规则匹配 | LLM 分解 |
|---|---|---|
| OBC水道设计 | L-STATE / L-STRATEGY-FREQ（误）| **P-HW-MECH-WATERWAY(0.95)** + G-METHOD-CAE-FLUID(0.75) |
| 水道板怎么设计 | WATERWAY（对但不全）| WATERWAY(0.95) + P-HW-MECH(0.9) + CAE-FLUID(0.8) |
| 灌封胶选型 | POT 两节点 | POT(0.95) + POTTING(0.9) + R-HW(0.75) |

**改进**：
1. 误匹配消除（OBC 不再映射到状态管理/抖频策略）
2. 语义更准（直接命中规则匹配不到的子节点，如水道系统）
3. 多主题扩展（关联节点补充）

## 回归验证

- 30 golden cases：规则 100% / LLM 100%（LLM 不降级）
- 40 单元测试全绿（含 7 个 mock LLM 测试）

## 使用

```bash
# CLI 暂未暴露开关；程序化调用：
from agent_kb.query.understanding import understand_query, UnderstandingOptions
frame = understand_query(query, domain_pack=dp,
                         options=UnderstandingOptions(use_llm=True))
```

## 备注

- LLM 调用约 2-3 秒/查询（thinking-off），可对高频查询做缓存
- 网关故障时自动回退规则，不影响系统可用性

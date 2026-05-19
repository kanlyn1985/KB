# 当前会话状态

## 一、会话主线概览

本次会话实际分成两条主线：

1. `KB1/examples/demo.html` 的 UI 重做与运行修正
2. 查询链路 `M0 -> M5` 的系统性修复与回归固化

后半段主线已经明显比前半段更重要。当前最有价值的成果集中在：

- 查询理解链路修复
- 参数解释型问答修复
- 可解释 fallback
- 高频参数对象补齐
- 回归测试固化
- 新增“入库覆盖报告模型”

如果开新会话，建议**不要再回到 UI 微调主线**，优先继续“入库覆盖报告 / 全库覆盖与鲁棒性测试体系”。

---

## 二、UI 当前状态

### 目标文件

- [examples/demo.html](E:/AI_Project/opencode_workspace/KB1/examples/demo.html)

### 当前情况

- 已按用户提供的工作台风格重写，而不是沿用旧版 demo
- 页面已能在 `http://127.0.0.1:8000/demo` 跑起来
- 顶部搜索框已修复为可输入
- 顶部搜索框与右侧查询框双向同步
- `Enter` 可触发查询
- 运行页基本无 console 报错

### 已做验证

- 页面结构完整
- 重复 `id` 已检查
- 页面能加载
- 基本交互能跑

### 当前判断

UI 不是本轮最核心阻塞点。后续如果继续做 UI，建议只在业务链路稳定后再回头收拾，不要与查询链修复抢优先级。

---

## 三、查询链路修复主线总览

本会话已经按里程碑推进到：

- `M0 = PARTIAL PASS`
- `M1 = PARTIAL PASS`
- `M2 = PARTIAL PASS`
- `M3 = PASS`
- `M4 = PASS`
- `M5 = PASS`

### 已完成能力

1. 上游 query understanding 已明显改善
   - 解释型问法不再大面积掉进 `general_search`
   - `CC阻值 / CP占空比 / 检测点1电压 / V2V` 等锚点已能保留

2. 参数类 query 不再默认漂向 `parameter_group`
   - `topic_resolution` 已更倾向细粒度对象

3. 参数解释型问答已从 `general_search` 中拆出
   - 新增 `parameter_meaning`

4. 无精确对象时已支持显式 fallback
   - `V2V` 现会返回近似解释并标注 `fallback_reason`

5. 高频参数对象已补齐
   - 已新增 `CC阻值`
   - 已新增 `CP占空比`
   - 已新增 `检测点1电压`

6. 回归测试已固化
   - 单元回归
   - 集成回归
   - 用户风格问题集回归

---

## 四、已修改的核心代码文件

### 1. 语义解析 / rewrite

- [query_semantic_parser.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_semantic_parser.py)
- [query_rewrite.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_rewrite.py)

#### 已做内容

- 提升解释型问法覆盖：
  - `是什么意思`
  - `代表什么意思`
  - `表示什么`
  - `指什么`
  - `含义是什么`

- 增加 semantic 输出质量约束：
  - 压制 `undefined / 未知主题 / 未知实体`
  - 避免高置信 `no_answer_candidate`

- 新增 `quality_flags`

- rewrite 改成更接近“两阶段”的行为：
  - 最终 `query_type` 先决
  - 再重建 `normalized_query / target_topic / must_terms`

- 增加：
  - `protected_anchor_terms`
  - `rewrite_override_applied`
  - `semantic_quality_flags`

#### 当前效果

例如：

- `CC阻值代表什么意思`
  - `query_type = definition`
  - `target_topic = CC阻值`

- `CP占空比是什么意思`
  - `query_type = definition`
  - `target_topic = CP占空比`

- `什么是V2V`
  - `query_type = definition`
  - `target_topic = V2V`

---

### 2. topic resolution

- [topic_resolution.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/topic_resolution.py)

#### 已做内容

- 参数类候选优先级调整
- `parameter_group` 显式降权
- 参数解释型 definition query 也引入参数类候选逻辑

#### 当前效果

运行期 `query-context` 结果中：

- `CC阻值代表什么意思`
  - top1: `CC阻值 (parameter_topic)`

- `CP占空比是什么意思`
  - top1: `CP占空比 (parameter_topic)`

- `检测点1电压表示什么`
  - top1: `检测点1电压 (parameter_topic)`

---

### 3. answer policy / answer api

- [answer_policy.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_policy.py)
- [answer_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_api.py)

#### 已做内容

- 新增 `parameter_meaning` 策略
- 参数解释型 query 不再走 `general_search`
- 参数解释答案开始输出：
  - 参数意义
  - 参数作用
  - 依据来源

- 定义型问题新增：
  - `fallback_reason`
  - 近似解释模板

#### 当前效果

`CC阻值代表什么意思`

- `answer_mode = parameter_meaning`
- 直接答案：
  - `CC阻值 表示连接确认回路中的等效电阻参数，用于反映车辆接口连接状态。依据来自 A.2 充电控制导引电路。`

`CP占空比是什么意思`

- `answer_mode = parameter_meaning`
- 直接答案已变成参数解释型，不再是泛搜索堆叠

`什么是V2V`

- `answer_mode = definition`
- `fallback_reason = fallback_to_related_concept`
- 会明确说明：
  - 未找到直接定义
  - 当前最接近概念是 `V2X`
  - 这是近似解释

---

### 4. 数据层对象补齐

- [entities.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/entities.py)

#### 已做内容

- 扩展 `parameter_topic` 派生逻辑
- 让以下对象能直接建模：
  - `CC阻值`
  - `CP占空比`
  - `检测点1电压`
  - `检测点3电压`

#### 已执行的数据重建

已实际重建：

- `DOC-000002`
- `DOC-000003`

#### 数据库验证

运行期数据库：

- `E:/AI_Project/opencode_workspace/KB1/knowledge_base/db/knowledge.db`

已确认存在新的 `parameter_topic`：

- `CC阻值`
- `CP占空比`
- `检测点1电压`
- `检测点3电压`

并且已生成对应 wiki 页面：

- `knowledge_base/wiki/parameter_topics/*.md`

---

### 5. API 调试字段

- [query_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_api.py)
- [answer_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_api.py)

#### 已增加

API 输出中已加入 `debug_query`：

- `final_query_type`
- `final_normalized_query`
- `final_target_topic`
- `protected_anchor_terms`
- `rewrite_override_applied`
- `semantic_quality_flags`

这个字段后续继续做回归和覆盖统计时非常有用。

---

## 五、已新增 / 更新的测试

### 新增测试文件

- [test_query_repair_regression.py](E:/AI_Project/opencode_workspace/KB1/tests/test_query_repair_regression.py)
- [test_user_style_query_regression.py](E:/AI_Project/opencode_workspace/KB1/tests/test_user_style_query_regression.py)

### 新增问题集

- [user_style_query_regression_cases_2026-04-23.json](E:/AI_Project/opencode_workspace/KB1/tests/generated/user_style_query_regression_cases_2026-04-23.json)

### 已跑通测试

#### 单元层

```text
pytest -q tests/test_query_rewrite.py tests/test_answer_policy.py tests/test_query_repair_regression.py -m "not integration"
```

结果：

```text
13 passed, 6 deselected
```

#### 集成层

```text
pytest -q tests/test_query_repair_regression.py -m integration
```

结果：

```text
6 passed, 4 deselected
```

#### 用户风格问题集

```text
pytest -q tests/test_user_style_query_regression.py -m "not integration"
```

结果：

```text
7 passed, 7 deselected
```

```text
pytest -q tests/test_user_style_query_regression.py -m integration
```

结果：

```text
7 passed, 7 deselected
```

### 当前测试现状判断

虽然已经不只是“精选样例测试”了，但用户也指出了一个正确问题：

> 现在的测试仍然不够“全方面”。

当前测试更像：

- 第一批用户风格问题集
- 第一批修复行为锁定集

还不是：

- 全知识库覆盖度测试
- 真正的鲁棒性覆盖报表

---

## 六、已新增的文档体系

### 查询链诊断与修复文档

- [query_error_diagnosis_model_2026-04-22.md](E:/AI_Project/opencode_workspace/KB1/docs/query_error_diagnosis_model_2026-04-22.md)
- [query_repair_blueprint_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_blueprint_2026-04-23.md)
- [query_repair_task_breakdown_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_task_breakdown_2026-04-23.md)
- [query_repair_phase0_execution_spec_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_phase0_execution_spec_2026-04-23.md)
- [query_repair_master_plan_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_master_plan_2026-04-23.md)
- [query_repair_milestone_board_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_milestone_board_2026-04-23.md)
- [query_repair_acceptance_template_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_acceptance_template_2026-04-23.md)

### 各里程碑验收文档

- [query_repair_m0_acceptance_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_m0_acceptance_2026-04-23.md)
- [query_repair_m0_postpatch_acceptance_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_m0_postpatch_acceptance_2026-04-23.md)
- [query_repair_m1_postpatch_acceptance_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_m1_postpatch_acceptance_2026-04-23.md)
- [query_repair_m2_postpatch_acceptance_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_m2_postpatch_acceptance_2026-04-23.md)
- [query_repair_m3_postpatch_acceptance_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_m3_postpatch_acceptance_2026-04-23.md)
- [query_repair_m4_postpatch_acceptance_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_m4_postpatch_acceptance_2026-04-23.md)
- [query_repair_m5_postpatch_acceptance_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_m5_postpatch_acceptance_2026-04-23.md)

### 鲁棒性 / 覆盖文档

- [robustness_test_coverage_framework_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/robustness_test_coverage_framework_2026-04-23.md)
- [ingestion_coverage_report_model_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/ingestion_coverage_report_model_2026-04-23.md)

---

## 七、当前最重要的系统结论

### 1. 查询链主线

当前这条主线已经从“系统性错误频发”推进到“基础可用且已被测试锁住”。

重点成果：

- 解释型问法更稳定
- 参数解释型 query 已拆出
- `V2V` 已不再空答
- 高频参数对象已直接建模

### 2. 测试主线

当前测试已经从“代表样例”升级到：

- 单元回归
- 集成回归
- 第一批用户风格问题集回归

但还**没有**解决用户指出的两个根本问题：

1. 问法覆盖率
2. 知识库覆盖率

### 3. 入库完成定义

当前最关键的新判断：

> “黄金测试跑完”不是“入库完成”的充分条件。

更合理的定义是：

```text
入库完成 =
  pipeline 完成
  + 覆盖报告生成完成
  + 黄金测试生成完成
  + 黄金测试执行完成
```

而当前系统**还没有真正的入库覆盖报告**。

---

## 八、当前还未解决的核心问题

### A. 全知识库鲁棒性测试还不够

虽然已经有第一批用户风格问题集，但仍然存在：

- 问法类型覆盖不够全面
- 口语/追问/噪声问法覆盖不足
- 不同知识类型分布不均
- 仍有偏“高频参数类”的倾向

### B. 还没有“知识库覆盖度统计器”

当前最大的结构性缺口：

> 无法回答“入库后的知识对原文是否做到全覆盖，哪里有漏”。

原因是当前只有：

- count
- score

没有：

- `source unit inventory`
- `coverage matrix`
- `uncovered report`
- `coverage scorecard`

### C. 标准定义型 answer 仍偶发不稳

例如：

- `什么是控制导引电路？`

在部分运行中仍可能直接给出：

- `没有找到足够的结构化结果。`

虽然用户风格测试里已经保留了它，但在 answer 层这一条还不如参数解释链稳定。

### D. 参数值型 answer policy 还没拆

当前已经有：

- `parameter_meaning`

但还没有真正独立的：

- `parameter_value`

所以像：

- `CC阻值是多少`

这类问题仍有继续优化空间。

---

## 九、如果新开会话，建议直接接着做什么

### 第一优先级：Coverage v0

直接进入：

- `source unit inventory`
- `coverage matrix`
- `uncovered report`
- `coverage summary`

也就是把 [ingestion_coverage_report_model_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/ingestion_coverage_report_model_2026-04-23.md) 开始落成代码与数据结构。

这是当前**最重要的下一条主线**。

### 第二优先级：第二批用户风格问题集

继续扩：

- 口语问法
- 追问式问法
- 噪声型问法
- 更多标准类 / process / constraint 类问法

并开始输出：

- `Query Style Coverage`
- `Knowledge Coverage`

### 第三优先级：参数值型 answer policy

如果继续沿查询链做增强，可以补：

- `parameter_value` 策略

但它的重要性已经低于“覆盖报告模型”。

---

## 十、推荐新会话开场提示

可以直接这样开：

```text
继续做 KB1 的覆盖体系，不再优先修 query 链。
当前 M0-M5 已完成一轮闭环，重点成果是：
- rewrite / topic_resolution / parameter_meaning / explainable fallback / 高频 parameter_topic / regression 已落地
- 新增测试 tests/test_query_repair_regression.py 和 tests/test_user_style_query_regression.py，已跑通

现在最重要的问题是：系统还无法判断“原文是否全覆盖、哪里有漏”。
请基于 docs/ingestion_coverage_report_model_2026-04-23.md，开始设计并实现 Coverage v0：
- source unit inventory
- coverage matrix
- uncovered report
- coverage summary

目标不是只看 fact_count/evidence_count，而是要能回答：
1. 哪些 source unit 完全漏掉
2. 哪些只到 evidence 没到 fact
3. 哪些到了 fact 但没对象
4. 哪些到了对象但没进入 golden/regression
```

# Archive

本目录存放已废弃、不再参与构建的历史内容，仅供回溯参考。**不要**从这里 import 或运行脚本。

## 内容

- `legacy-kb1/` — 旧 `enterprise_agent_kb`（汽车标准 KB1）的管线产物：
  证据 / 事实 / wiki / normalized / processed / 质量报告 / 覆盖率报告 / 旧数据库 / 评测报告等。
  对应源码已随重建移除（commit `a538722`）。
- `ontology-v1-design/` — 旧 `kb1_ontology` 并行系统的设计与测试报告
  （2026-06：类注册表 / 实体管理 / 关系注册 / 属性存储 + combined query 桥接）。
  该路线已被 2026-08 的 RFLP 本体树方案取代。

## 说明

- 归档前已打 git tag `pre-reorg-*`，可随时回看移动前的状态。
- 源文档语料已更名为 `corpus/`，未归档。
- 归档只做「移动」，未做删除；若需恢复，从对应子目录移回即可。

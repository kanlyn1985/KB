# V0.7 IMPL-002 Implementation Notes — RulePackage Runtime

- Date: 2026-09-04 · Baseline: 8c54447（IMPL-001）· V0.6 frozen b317c6e ·
  V0.5 frozen e7a286e（零触碰实测）
- 新增：agent_kb/rules/（runtime.py + __init__.py——新包，frozen 零触碰）；
  tests/v07_rule/test_rule_package_runtime.py（RP-CMP-001..010）

## 行为契约（RP-CMP-001..010 全 PASS）

- **package load**（001）：RulePackage → RegisteredPackage（package_ref/provider
  实例）；provider reasoner_id="rulepkg:<id>"、rule_version=包版本；
- **schema validation**（002）：空 package_id/version/规则集/谓词 + 未知
  rule_type 全拒绝（E-V07-RULE-INVALID）；
- **deterministic rule_package_id**（003）：package_ref = "rlp_"+SHA256
  (canonical_json({package_id, version, rules(sorted+canonical patterns),
  domain_bindings}))——跨实例/重复注册全等；
- **version conflict handling**（004）：同包多版本共存（get 最新/指定）；重复注册
  幂等零重复审计；
- **invalid rule reject**（005）：空 rule_id/version + 未知 rule_type 拒绝；
- **DomainPack binding validation**（006）：绑定必须 domain_id@version 格式且
  指向已加载 pack（未加载 → E-V07-DOMAIN-NOT-LOADED；坏格式 → INVALID）；
- **provenance**（007）：graph:rule-load 落 akb_provenance（package_ref/rules/
  bindings）；复用零第二套系统；
- **reasoning integration**（008）：provider 注入 V0.4 引擎（经 V0.6 orchestrator
  engine=参数——单一引擎原则）；候选恒 inferred/candidate；
  reasoner_id="rulepkg:flow-rules"、rule_ref="R-before-chain@1.0" 全链贯通；
  零晋升（inferred+asserted 零行）；
- **rule ordering determinism**（009）：provider infer 谓词池按 assertion_id 排序、
  笛卡尔展开上限 64——乱序输入同输出；
- **frozen regression**（010）：V0.4 engine/V0.6 orchestrator 源码零 rules 引用
  （单向依赖：rules→reasoning，frozen 不感知）；legacy API 互斥。

## 关键设计落地

- PatternRuleProvider：模式匹配 provider（input_pattern.predicates 全存在才触发
  ——skip 语义；output_pattern.subject_from/predicate 生成候选形态；
  rule_input_snapshot 携带 package_id/version/rule_id/matched）；
- 绑定校验 fail-closed：domain_bindings 引用未加载 pack → 拒绝（域运行时协同）。

## P2

- 笛卡尔展开上限 64/规则为设计初值（policy 预算机制属 IMPL-003）。
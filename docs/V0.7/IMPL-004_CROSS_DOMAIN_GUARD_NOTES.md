# V0.7 IMPL-004 Implementation Notes — CrossDomainGuard

- Date: 2026-09-04 · Baseline: 72ab736（IMPL-003）· V0.6 frozen b317c6e ·
  V0.5 frozen e7a286e（零触碰实测）
- 新增：agent_kb/domains/guard.py（CrossDomainGuard + GuardDecision +
  CrossDomainError）；domains/__init__.py 追加导出（V0.7 阶段文件）；
  tests/v07_domain/test_cross_domain_guard.py（CD-CMP-001..010）

## 行为契约（CD-CMP-001..010 全 PASS）

- **domain allow**（001）：root 域内访问 allow（reason=intra-domain）+
  fingerprint "gcd_"+SHA256(canonical({decision, source, target, pack_ref,
  policy_ref, subject}))；
- **unauthorized block**（002）：跨域未授权 → E-V07-CROSS-DOMAIN-BLOCKED
  fail-close（block 审计先落再抛错）；
- **namespace conflict**（003）：check_namespace 归属校验——ns 未注册/非正主 →
  E-V07-NAMESPACE-CONFLICT；
- **deterministic decision**（004）：同输入跨实例同 fingerprint；输入不同 →
  fingerprint 不同（canonical JSON 派生）；
- **provenance audit**（005）：graph:cross-domain-allow/block 落 akb_provenance
  （source_domain/target_domain/pack_ref/policy_ref/decision/fingerprint——
  复用零第二套系统）；
- **policy integration**（006）：裁决携带 policy_ref；policy runtime 注册面
  零被修改；
- **pack isolation**（007）：LoadedPack ns 唯一持有 + check_namespace 一致；
- **rule binding isolation**（008）：check_rule_binding——绑定域已加载通过；
  未加载域 E-V07-NAMESPACE-CONFLICT；未注册包 E-V07-RULE-PACK-NOT-REGISTERED
  （guard 侧独立防御——绕过注册校验的包也被拦截）；
- **fail-close**（009）：enforce 全 allow 通过/混入 block 抛错（零 fabricate 放行）；
- **frozen regression**（010）：V0.6 orchestrator/context 零 guard 感知（单向依赖）
  + legacy API 互斥 + guard 零 candidate 产生（akb_assertions 零新增实测）。

## 边界声明

- guard 为 V0.7 runtime 层**外围门控**——V0.6 orchestrator 内部逻辑零修改
  （源码审计）；不产生 candidate；不改变 governance 生命周期；
- 授权跨域（allow_cross_domain=True）为治理显式动作（审计留痕）。

## P2

- context_domains 的域归属推导（候选谓词/实体 ns 解析）为编排侧调用方职责——
  guard 只消费显式域集合（语义单一归属）。
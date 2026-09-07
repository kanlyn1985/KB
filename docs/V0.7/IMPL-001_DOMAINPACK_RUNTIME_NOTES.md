# V0.7 IMPL-001 Implementation Notes — DomainPack Runtime

- Date: 2026-09-04 · Baseline: 14a6ea0（V0.7 design）· V0.6 frozen b317c6e（零触碰实测）·
  V0.5 frozen e7a286e（零触碰实测）
- 新增：agent_kb/domains/runtime.py（DomainPackRuntime + LoadedPack +
  DomainPackRuntimeError）；tests/v07_domain/test_domain_runtime.py（DP-CMP-001..010）

## 行为契约（DP-CMP-001..010 全 PASS）

- **pack load**（001）：frozen DomainPack → LoadedPack（domain_id/version/namespace/
  pack_ref/pack 原样/terminology_namespaced 只读视图）；
- **schema validation**（002）：关系端点类型必须存在于 object_types；空 id/version/
  空术语键拒绝（E-V07-PACK-INVALID）；
- **deterministic pack_id**（003）：pack_ref = "dpr_"+SHA256(canonical_json
  ({domain_id, version, object_types, relation_types(src/tgt), terminology}))——
  同 pack 跨实例/重复加载全等；内容变化 → ref 变；
- **version 管理 + conflict fail-close**（004）：同 domain 多版本共存（get_pack
  最新/指定版本）；namespace 冲突（异 domain 抢同 ns）→ E-V07-PACK-NAMESPACE-CONFLICT；
- **invalid reject**（005）：空 id/version/术语键 + 非法 ns（含冒号）全拒绝；
- **provenance**（006）：graph:pack-load 落 akb_provenance（pack_ref/version/
  namespace/类型面清单）；重复加载零重复审计（幂等返回）；
- **canonical ordering**（007）：list_packs 排序稳定；terminology ns 视图键有序；
- **V0.6 integration**（008）：pack 加载零图写入（canonical_view 不变）；
  V0.6 全链路（context→orchestrator→provenance）行为不变；候选恒 candidate
  （pack 不产生事实、不改变生命周期）；
- **namespace isolation**（009）：同术语跨域 ns 隔离（industrial:/finance:）零交叉；
- **frozen regression**（010）：schema.py/loader.py 零污染（源码审计）+ legacy
  graph API 互斥 + graph_edges 零变化。

## 复用声明

- frozen DomainPack dataclass 原样复用（schema.py 零修改——"runtime" 字样零出现）；
- frozen loader 通道复用（load_domain_pack；pack_ref 不入 loader）；
- provenance 复用 akb_provenance（graph:pack-load；零第二套系统）；
- 零 migration；零 LLM/vector/数据库依赖。

## P2

- registry 为实例级内存态（跨进程共享属 IMPL-002 RulePackage 范围或后续持久化
  决策——设计 §14 NO-MIGRATION 路径）。
# V0.5 DomainPack Architecture — 领域扩展机制

- Document ID: AKB-DD-V05-004 · Status: Design Baseline
- 现状锚点：agent_kb/domains/（DomainPack dataclass + terminology 映射 + loader）；
  V0.3 对齐已消费 DomainPack.terminology（L4 别名通道）。

## 1. DomainPack 定义（V0.5 扩展面）

```text
DomainPack (V0.5)
├── ontology                     # 实体类型树 + 关谓词词汇表
│   ├── entity_types[]           # {type_id, parent, display, constraints}
│   └── predicates[]             # {predicate_id, domain_types, range_types, inverse?}
├── rules                        # 推理规则扩展（V0.4 RR 通道的领域实例化）
│   └── rule_refs[]              # 领域规则编号 + 输入/输出断言形态
├── entity_types                 # 同 ontology.entity_types（Graph Node type 域）
├── predicates                   # 断言谓词 → Graph relates_to 边类型映射
└── validation_constraints       # 领域校验约束
    ├── cardinality[]            # 如 max 锚定数/必填属性
    ├── type_compatibility[]     # 谓词两端类型兼容矩阵
    └── temporal_rules[]         # 领域时间语义收紧（只收紧不放宽 V0.3 六态）
```

## 2. 加载与版本化

- 目录结构延续现有 loader（domain_dir 下 JSON/YAML 声明式）；
- domain_pack_version 参与所有确定性派生（canonical_id/fingerprint——继承项目约定）；
- 多 DomainPack 并存：按 namespace 隔离（entity_types/predicates 前缀），跨域合并
  需治理批准（防止工业/金融/软件域词汇冲突）。

## 3. 领域实例化目标（未来扩展）

| 领域 | entity types 示例 | predicates 示例 | validation 示例 |
|---|---|---|---|
| 工业 | equipment/component/parameter/standard | has_parameter/constrained_by/regulated_by | 参数单位兼容矩阵 |
| 金融 | instrument/issuer/transaction/rate | priced_in/listed_on/derived_from | 数值精度/时间窗约束 |
| 软件工程 | module/interface/dependency/version | depends_on/implements/deprecates | 版本序兼容（semver） |

## 4. 边界

- DomainPack 只提供**词汇与约束**，不引入事实（KG-01 不变）；
- 领域规则经 V0.4 ReasonerProvider 通道接入（rule_version 组合 domain_pack_version）；
- 领域约束收紧优先于默认（冲突时 strict 侧生效）；
- 不修改 V0.4 frozen 代码——DomainPack V0.5 扩展是新 schema/loader 层（V0.5-IMPL 实现期）。
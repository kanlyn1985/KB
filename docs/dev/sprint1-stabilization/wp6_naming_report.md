# Sprint 1 — WP6 报告：four-loop → six-loop 命名统一

> 执行依据：`kb1_next_development_guide.html` § WP6。
> 原则：主线统一 six-loop；历史 four-loop 保留时加"历史命名说明"；不机械替换所有字符串。

## 1. 现状盘点

全仓库 `four-loop / 四环` 引用分三类：

| 类别 | 位置 | 处理 |
|---|---|---|
| 历史审计名 | `.codestable/audits/2026-05-10-four-loop-integration/` | **保留原名**（被多个 issue fix-note 的 `source_audit:` 引用），加历史命名说明 |
| 历史 roadmap 目录/文件名 | `.codestable/roadmap/kb1-four-loop-hardening/` | 内容已是 six-loop（slug=`kb1-six-loop-hardening`、标题"六闭环"）；目录名保留以避免破坏 15+ feature frontmatter 的 `roadmap:` 引用，加历史命名说明 |
| 历史 feature frontmatter | 各 feature 的 `roadmap: kb1-four-loop-hardening` | 保留（引用上述 roadmap） |
| 实时文档路径错误 | `docs/dev/kb1-development-guide.md` 引用了不存在的 `kb1-six-loop-hardening-items.yaml/.md` | **修复**为真实文件名 `kb1-four-loop-hardening-items.yaml/.md` |
| 实时代码 | 无 | 无需处理（grep `.py` 无 four-loop 引用） |

## 2. 执行的修改

1. **`docs/dev/kb1-development-guide.md`**：修正 2 处指向 roadmap 的路径（原 `kb1-six-loop-hardening-items.yaml` / `kb1-six-loop-hardening-roadmap.md` 实际不存在 → 改为真实存在的 `kb1-four-loop-hardening-items.yaml` / `kb1-four-loop-hardening-roadmap.md`）。验证两路径均可解析。
2. **`.codestable/roadmap/kb1-four-loop-hardening/kb1-four-loop-hardening-roadmap.md`**：标题下加"历史命名说明" callout，说明目录名保留原因（避免破坏引用）、内容已是 six-loop、新工作走 `kb1-next-phase`。
3. **`.codestable/audits/2026-05-10-four-loop-integration/index.md`**：标题下加"历史命名说明" callout，说明审计在四闭环时期执行、保留原名维持 `source_audit:` 引用链、结论已被 six-loop 重构覆盖。

## 3. 不做的（按指导书"不机械替换"）

- 不重命名 `kb1-four-loop-hardening/` 目录：会破坏 15+ feature 的 `roadmap:` frontmatter 引用，得不偿失；用历史命名说明替代。
- 不改历史 feature/issue 文档里的 `roadmap:` / `source_audit:` frontmatter：这些是历史追溯链。
- 不改 `hygiene-dashboard-design.md` 中"Four Loop Dashboard → Five Loop Dashboard"的"现状/变化"描述：那是该 feature 设计时（四→五环过渡期）的历史快照，属正当设计文档内容。

## 4. 验收（对照指导书 §8 "命名一致性" 项）

| 验收项 | 状态 |
|---|---|
| six-loop 命名主线明确 | ✅ 实时代码/新文档统一 six-loop；分支 `kb1-six-loop-rename` |
| 历史 four-loop 有说明 | ✅ roadmap + audit 各加历史命名说明 |
| 实时路径错误已修复 | ✅ dev guide 2 处路径已修正并可解析 |

→ **WP6 完成。**

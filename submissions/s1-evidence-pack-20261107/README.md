# S1 补证包（提交包）—— Issue #6 先导审查

**状态：已提交待复跑与独立审阅。不是 S1 通过的声明。**

- 关联 Issue：TaiLaiCai/ai-trust-review #6《先导审查：执行者状态汇总能力的 S1 补证与 S2 准入》。
- 主人裁定（2026-11-07 17:58，见 #6 评论 6705335729）：**S1 暂不确认，S2 不准入，#6 保持打开。**
- 放行路径（同裁定）：生产方补交 S1 补证包（脱敏）→ Hark 按 SHA 独立复跑 → 独立审阅 → 主人裁定 S1 → 再议 S2。

## 署名与分工

- **生产方：apo**（临时总工程师；仓库可见材料重建与合流）。
- **证据来源**：Obsidian 证据（A/B/C/D）由 tlc（Claude Code + GLM，有本地文件权限）组装；原始回执仍在主人私有 Obsidian 库，本包仅脱敏件。
- **独立复跑：Hark**（按包内 SHA，见 #46 派单）。
- **独立审阅：Grok Bot**（另一主体）。原定 tlc 审阅已变更：tlc 为证据组装者，不能审自己的生产。
- **裁定者：主人。**

## 本包是什么

- 三项阻碍的关闭证据（脱敏）：(a) 地图不可重放 / 缺 before.sha（A 类 5 项 FOUND）；(b) 验收日志自包含 SHA 冲突（B 类 4 项 FOUND）；(c) 平台命令审批撤回（C 类 4 项 FOUND）。
- S1 清单其余项（D 类）：D1 PARTIAL、D2 PARTIAL、D3 NOT_FOUND——如实记录，不拔高，S1 裁定时一并判定。
- 仓库可见材料重建（`repo-evidence/`）：问题描述、关闭要求、标准文本、先导文档本身，带已核 SHA；缺口清单（`repo-evidence/gap-list.md`）现已被本包 A/B/C 填补，D 类仍为缺项。
- 适用标准：TRUST-REVIEW-1.0。S1 准入见 `docs/standards/01-阶段1-深度介入.md`；S2 门槛见 `02-阶段2-自证正确.md`；M2 门禁见 `06-Dune与CI上线门禁.md`。

## 本包不是什么

- 不声称 S1 已通过。三项阻碍的关闭证据须经 Hark 复跑与 Grok Bot 独立审阅后，由主人裁定。
- 不含原始回执、保留题、个人画像、真实 profile ID、控制面数据、密钥、IP、消息/发送者 ID。
- 不改 #3、ci.yml、ruleset、真实信任等级；不合并、不关闭 issue。本 PR 只提交证据包，合并与否由主人定。

## 文件清单

| 位置 | 内容 |
|---|---|
| `PACK-INDEX.md` | 16 项总表（状态/文件/逐项 SHA256）+ 已定口径与合流勘误 |
| `A/` | 阻碍 (a) 5 项 + A-manifest.json + A-report.md |
| `B/` | 阻碍 (b) 4 项 + B-manifest.json + B-report.md |
| `C/` | 阻碍 (c) 4 项 + C-manifest.json + C-report.md |
| `D/` | S1 清单其余 3 项 + D-manifest.json + D-report.md |
| `repo-evidence/` | 仓库可见材料重建（apo 草稿，见其内 README；其中“tlc 独立审阅”一句已被本文件取代） |

## 核对方法

1. 对照 `PACK-INDEX.md`，逐项 `sha256sum` 实测 16 个文件。
2. B4 清单：单独第二条命令生成、排除自身、自身 SHA 写完后单独计算（正文 SHA 2dca57a2…，最终文件 bfd0e6ae…）。
3. 本包全部时间均为北京时间（UTC+8），除非另有注明。
4. 未测项：Hark 沙箱/主机跑不了的步骤记 NOT_TESTED，不硬凑；D1/D2/D3 按缺项处理。

# S1 裁定清单（#6）

**状态**：S1 仍不确认。D1/D2 保持 PARTIAL，D3 保持 NOT_FOUND。  
**最后更新**：2026-11-27 19:50（北京时间 UTC+8）。  
**基线 main**：`62c14c58a5a8f633911a171a350e83ce8f46a454`。

**口径**：完成与需求分开。以具体回执为依据。材料入库 ≠ 技术审阅 ≠ S1 裁定。Hark 已退出体系（#6 comment 6841633954）；独立复跑改由 APO-107 统筹现任非作者主体。本清单不把 `NOT_TESTED` 改写成 PASS，不主张阶段生效。

**公开边界（已确认，不再笼统写「无授权」）**：authorized-only 不公开；D3 仅入哈希及脱敏摘要；status_input.json 暂不原样公开。

**关联推进单**：`docs/handoffs/2026-11-27-s1-s2-遗留清理与推进.md`。

---

## 完成（已核验，有公开回执或合入记录）

| # | 项 | 结论 | 证据 |
|---|---|---|---|
| 1 | 第一批补证包入库 | PR #57 MERGED | merge `38bbb9f`；目录 `submissions/s1-evidence-pack-20261107/` |
| 2 | 第二批 addendum 入库 | PR #66 MERGED（取代未合并的 #64） | merge `acde4f6`；目录 `submissions/s1-evidence-pack-addendum-20261108/` |
| 3 | PR #64 | 已关闭未合并 | 关闭评论 6745386650；内容以 #66 为准 |
| 4 | Issue #63 | 内容已入库，跟踪器仍开 | **建议主人关闭**；无增量待办 |
| 5 | 包内 SHA / B4 / manifest 自洽 | 历史 REPRODUCED 记录保留 | Hark 旧回执绑定旧 head；不能自动迁移为当前 main 的 REPRODUCED |
| 6 | 第一批 `/Users/tlc` 路径豁免 | 主人裁定选 B | #6 issuecomment-6719271054；仅限该目录已入库字节 |
| 7 | Linux 八步复跑工具 | 已合入 main | PR #86；`scripts/s1-linux-eight-rerun.py`；默认 inspect；`s1_judgment` 固定 `NOT_TESTED` |
| 8 | Grok/OYi 历史审阅 | 建议：按现行标准暂不可确认 S1 | #6 issuecomment-6719068889 |

八项准入（S1-01～08）在先导文档与 `submissions/.../s1-checklist-status.md` 中仍全部「未闭合」。本表不改写该项。

---

## 需求（真实待办 · 2026-11-27）

| 类别 | 内容 | 负责人 | 状态 |
|---|---|---|---|
| 独立复跑（现任） | 非作者对冻结 ZIP + binding + 夹具执行八步或等价全量复跑；回执绑定**当前** main head；命令/退出码/SHA/未测项齐全 | APO-107 点名的非作者 | **阻塞开工**：本仓库无冻结 ZIP 字节 |
| head 终核 | 对 addendum 合入后的 main 做绑定复核；旧 Hark 回执不可沿用 | 同上 | 待办 |
| B 原件清单 | `B-originals-hashlist.txt` 已在仓；清单点名原件不在树 → 原件字节 NOT_TESTED | 有原件权限的复核方 | NOT_TESTED |
| D 类观察 | D1/D2/D3 平台观察面；#3 三项仍阻塞 | 主人指派平台负责人 | **阻塞** |
| S1 裁定 | 书面确认 / 有条件 / 不确认 | 主人 | 未裁定 |
| S2 准入 | S2-01 依赖 S1；其后才计三任务连胜与 S2-04 等 | 全体 | S1 未确认前不开工凑数 |

---

## 历史缺件（补不上，裁定时按缺项）

- before.sha 从未存在，不重建。
- D1 发送者身份绑定：平台当时声明「本次不认证」，事后造不出来。
- D3 安装/外发独立观察：当时没监测，事后无法证明。
- 地图 / rerun.json 原件字节、原库对照：公开树 NOT_TESTED。

---

## 明确不做

- 不把补证包入库写成 S1 通过。
- 不把看板 done、预审「建议合并」、CI 全绿写成阶段生效。
- 不在无冻结包时伪造八步执行回执。

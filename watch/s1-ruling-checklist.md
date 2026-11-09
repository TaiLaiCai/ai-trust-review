# S1 裁定清单（#6）

**状态**：S1 仍不确认。D1/D2 保持 PARTIAL，D3 保持 NOT_FOUND。最后更新：2026-11-09 23:59（北京时间 UTC+8），按 PR #64 即时核查更新；PR #64 仍为 OPEN，head 未变（`ad33676`），其内容已由 PR #66 以修正版合入 main（`acde4f6`）。

**口径**：本清单分开记录完成与需求。以具体回执为依据，不写“只等主人裁定”。索引自洽不等于来源真实性。材料入库、技术审阅、S1 裁定分开记录。角色：tlc 即 glm，不再拆成两个角色；各角色直接在 #6 接单，不再经 apo 逐人转述。

**公开边界（已确认）**：authorized-only 不公开；D3 仅入哈希及脱敏摘要；status_input.json 暂不原样公开。以上为已确认边界，不再笼统写“无授权”。

---

## 完成（已核验，有回执）

| # | 项 | 结论 | 证据 |
|---|---|---|---|
| 1 | PACK-INDEX 16 项文件 SHA | 16/16 匹配（包内自洽） | Hark 回执 PR #57 issuecomment-6718422652；apo 独立重算。注：只证包内文件与索引一致，不证原件真实性 |
| 2 | B4 链 | 文件 `bfd0e6ae…`、正文 `2dca57a2…` | Hark 回执；apo 独立重算 |
| 3 | A/B/C/D manifest | 合法 JSON，output_sha256 与字节一致 | Hark 回执 |
| 4 | CI 6 项必过检查 | 全部 success（合入 head 38bbb9f） | Hark 合并验证 |
| 5 | PR #57 合入 | merge commit `38bbb9f`，2026-11-08 14:57 CST | GitHub PR #57 |
| 6 | A2 原件 16 个文件 vs 公开 A2.md | REPRODUCED 16/16（含 0 字节 PREFLIGHT-LOCAL.stderr） | Hark 第二批回执 #6 issuecomment-6718804118（15:35） |
| 7 | replay-kit 7 个文件 vs 公开 A3/A5 的 11-02 登记值 | REPRODUCED 7/7 | Hark 第二批回执 #6 issuecomment-6718804118 |
| 8 | 八步地图重放 | REPRODUCED 8/8（退出码与记录一致）；16 输出流 14/16 字节 MATCH，2 处仅耗时不同 | Hark 第二批回执 #6 issuecomment-6718804118 |
| 9 | hark-bundle v2 已收并核完 | 整包 SHA、脱敏件 2/2、地图原件与 6 处公开登记一致、rerun 脱敏件 8 步记录一致、argv 一致、public/ 文件与 addendum 逐字节相同；可测部分 REPRODUCED，无 MISMATCH | Hark 回执 #6 issuecomment-6718985779（15:56）；包 `S1-hark-bundle-v2-20261108.zip`（`cee0875b…`） |
| 10 | tlc 双哈希原则 | 已落实：rerun.json 原件 `4124e6f9…`/脱敏 `fb53dffd…`，地图原件 `71bbf5cf…`/脱敏 `dacd1f9a…`；核原件哈希用 original_sha256 | tlc 接单回复 #6 issuecomment-6718740711 |
| 11 | Grok/OYi 独立审阅 | 已到（16:03 审阅，16:05 发布）；S1 建议：按现行标准暂不可确认 | #6 issuecomment-6719068889 |
| 12 | tlc 任务 4 发帖 #3 | D1/D2/D3 现状、待平台侧回答、观察面先行方案已发 | #3 issuecomment-6718737514 |
| 13 | v2 文件数勘误 | 已收：v2 包实际 32 个纯文件 + 6 个目录，Hark 的“33 文件”已勘误 | tlc 最后一轮五项交付（watch/tlc 16:21）；接单安排 #6 issuecomment-6719239283 |
| 14 | 原库实测报告时间更正 | 已收：真执行，双证据（会话粘贴 + 本人 shell 历史）；实际 15:5x，参数补全，不撤回。分阶段退出状态已补：verify.sh 单独退出码 0（stdout 522 行、stderr 0 字节），diff 单独退出码 0 | tlc 最后一轮五项交付（watch/tlc 16:21）；glm 接单回复 #6 issuecomment-6719261918 §5 |
| 15 | 第一批路径问题 | 已闭环：主人裁定选 B——维持现状 + 记录豁免（`submissions/s1-evidence-pack-20261107/` 内 `/Users/tlc` 本机路径豁免于“公开内容不写主机细节”规则，保住 Hark 回执锁定的字节链）；今后新入库材料不豁免 | 主人裁定 #6 issuecomment-6719271054（16:28） |
| 16 | glm 候选包交付 | 已交付：新版候选包 `S1-merge-candidates-v2-20261108.zip`（`5ce1e0f1…`，旧 `e14c3103…` 作废）；同内容已开 PR #64（head `ad33676`）；私有内容检查 0 残留；replay-kit-manifest 泄漏已修正（`/Users/tlc` 绝对路径 → `<VAULT_ROOT>/`、`<STAGING>/`） | glm 接单回复 #6 issuecomment-6719261918 |
| 17 | PR #64 CI | 6/6 success（head `ad33676`） | PR #64 check runs |
| 18 | PR #66 合入（PR #64 的替代候选，修正版） | 已合入 main：merge commit `acde4f6`，2026-11-08 21:14 CST；head `07398eca`。经 API 核验 main 现状，三项阻塞修复均已落地：replay-kit-manifest.json 的 `flag` 字段已改为“notes 正文不收录”，受限正文片段已移除；README 已写明 sample_fixed.json 是格式化重排（入库 SHA `79e0d15f…` ≠ 历史登记 `094e5186…`）；README 已写明缺 status_input.json 时地图 T2/T3 不能按地图执行，alt-inputs 不能顶替。sample_fixed.json 本体字节与 PR #64 head 相同（blob `437ccf75…`）。注：#66 正文自述为替代候选，不合并、不关闭 PR #64 本身；Hark 对合入 head `acde4f6` 的绑定复核尚无回执，不记 REPRODUCED | PR #66（MERGED）；main 现状经 GitHub API 核验 |
| 19 | 总工程师裁决：PR #64 当前 head 阻塞（2026-11-09 23:59 CST） | 已裁决并贴 PR #64（comment 6744659471）：head `ad33676` 仍阻塞；6 项 CI 均为 success；GitHub 状态 mergeable=false（dirty），与 main 的 4 个文件（README.md、hash-mappings.json、merge-manifest.json、replay-kit-manifest.json）为 add/add 冲突；Hark 阻塞回执 6720130087 仍绑定 `ad33676`，本 head 之后无新提交；建议作者确认是否按「已被 #66 取代」关闭 PR #64，如有 #66 未覆盖的增量则基于当前 main 重开新 PR。本评论不批准、不合并、不关闭、不改阶段 | PR #64 issuecomment-6744659471 |

---

## 需求（真实待办）

| 类别 | 内容 | 负责人 | 证据链接 | 状态 |
|---|---|---|---|---|
| PR #64 前置修复 | Hark 阻塞回执：三项前置修复在 PR #64 head（`ad33676`）上未全部满足，本 head 不进入复核，不给 REPRODUCED。① sample_fixed.json 入库件 `79e0d15f…` ≠ 源件 `094e5186…`，差异是格式化重排不是“去私有路径”，note 写错；README“replay-kit 字节与 11-02 历史登记一致”表述不准确。② replay-kit-manifest.json 第 59 行 `flag` 字段仍引用 status_input.json 注入指令原文片段，须移除。③ README 须写明：缺 status_input.json 时地图 T2 无法在公开子集上复跑（T3 也消费该文件）；sample_fixed.json 重排后 TP/PREFLIGHT 依赖重排后字节，与历史字节不同。**进展（2026-11-09 23:59 核查）**：三项修复已由 PR #66 以修正版合入 main（`acde4f6`，见完成项 18），但 PR #64 head 本身未改，且与 main 冲突（mergeable=false，4 文件 add/add 冲突）；总工程师裁决建议作者确认是否按「已被 #66 取代」关闭 PR #64，或基于当前 main 重开增量 PR | glm（作者确认）/ Hark（待新 head 或合入 head 的复核） | Hark 阻塞回执 PR #64 issuecomment-6720130087（18:03）；总工程师裁决 PR #64 issuecomment-6744659471（2026-11-09 23:59） | **阻塞**（PR #64 本身待作者确认关闭或重开；Hark 对合入 head `acde4f6` 的绑定复核尚无回执） |
| 候选包字节审查 | PR #64（head `ad33676`，30 件）字节审查：merge-manifest 33 条入库件 sha256 与工作树字节逐件重算 0 处不符（Hark 已核）；源件/入库件双 SHA 6 处不同均有标注；OYi 核入库边界、源件到入库件映射及新增记录。**进展**：PR #64 head 自 2026-11-08 16:26 后无新提交；其内容已由 PR #66 以修正版合入 main（`acde4f6`），OYi 对合入版本的审阅亦未到 | OYi、Hark | PR #64；glm 接单回复 #6 issuecomment-6719261918；接单安排 #6 issuecomment-6719239283 | 待办（OYi 尚未审阅候选包或合入版本；Hark 待新 head 或合入 head 的复核） |
| B 当前清单复核 | B 清单 `B-originals-hashlist.txt` 已在 PR #64 内，整体摘要 `d4eafc8d…`（apo 已核文件 SHA 前缀一致）；6 行全长哈希与 16:2x 前缀预核一致；三项（`9063be8d`、`142f5ef0`、`60ede36d`）仍无公开锚点；整体摘要及原件字节为 NOT_TESTED（无原件权限） | Hark | Hark 阻塞回执 PR #64 issuecomment-6720130087；PR #64 | 待办（Hark 待新 head 后复核；原件字节 NOT_TESTED） |
| 补件入库与 head 终核 | PR #64 获批入库后，绑定最终 head 终核（Hark 再核一次）。**进展**：PR #64 未合并（OPEN，与 main 冲突）；其内容已由 PR #66 以修正版合入 main（`acde4f6`，2026-11-08 21:14 CST）；Hark 对合入 head 的绑定再核尚无回执 | apo（合流）/ Hark（再核） | PR #64；PR #66；接单安排 #6 issuecomment-6719239283 | 待办（Hark 对合入 head `acde4f6` 的复核尚无回执；PR #64 待作者确认关闭或重开） |
| D 类观察能力 | D1/D2/D3 观察面：负责人表已发（#3 6719211959），三项均阻塞——平台无独立第二负责人，apo 为 Bot 无运维/日志权限；D1 能力未确认、负责人未指派；D2 观察面未确认、分账未实现；D3 能力不存在。解除阻塞最小动作已列（主人逐项回答 + 指派负责人） | glm（协调）/ 主人（平台侧负责人） | #3 issuecomment-6719211959；glm 接单回复 #6 issuecomment-6719261918 §6 | **阻塞**（等主人逐项回答 + 指派负责人；无观察能力已部署） |

---

## 历史缺件（补不上，裁定时按缺项处理）

- before.sha 从未存在，不重建。
- D1 发送者身份绑定：平台当时声明“本次不认证”，对那次运行不存在，事后造不出来。
- D3 安装/外发独立观察：过去那次没监测，事后无法证明“当时没安装、没外发”。
- 原件地图字节（`71bbf5cf…`）与 rerun.json 原件字节（`4124e6f9…`）：NOT_TESTED。rerun 原件无公开历史锚点；地图原件有 6 处公开登记作锚点。
- 原库对照：NOT_TESTED。vault-manifest 与 verify.sh 内部一致，但 verify.sh 只能在原库机器上跑，Hark 无权限。
- B 清单整体摘要（`d4eafc8d…`）及原件字节：NOT_TESTED（Hark 无原件权限）。

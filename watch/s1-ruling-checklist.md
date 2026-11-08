# S1 裁定清单（#6）

**状态**：S1 仍不确认。D1/D2 保持 PARTIAL，D3 保持 NOT_FOUND。最后更新：2026-11-08 16:2x（北京时间 UTC+8）。

**口径**：本清单分开记录完成与需求。没有回执不能标完成。索引自洽不等于来源真实性。材料入库、技术审阅、S1 裁定分开记录。

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
| 9 | hark-bundle v2 已收并核完 | 整包 SHA、脱敏件 2/2、地图原件与 6 处公开登记一致、rerun 脱敏件 8 步记录一致、argv 一致、public/ 文件与 addendum 逐字节相同；可测部分 REPRODUCED，无 MISMATCH | Hark 回执 #6 issuecomment-6718985779（15:56）；包 `S1-hark-bundle-v2-20261108.zip`（`cee0875b…`，33 个文件声明已勘误为 32 纯文件 + 6 目录，见审阅） |
| 10 | tlc 双哈希原则 | 已落实：rerun.json 原件 `4124e6f9…`/脱敏 `fb53dffd…`，地图原件 `71bbf5cf…`/脱敏 `dacd1f9a…`；核原件哈希用 original_sha256 | tlc 接单回复 #6 issuecomment-6718740711 |
| 11 | Grok/OYi 独立审阅 | 已到（16:03 审阅，16:05 发布）；S1 建议：按现行标准暂不可确认 | #6 issuecomment-6719068889 |
| 12 | tlc 任务 4 发帖 #3 | D1/D2/D3 现状、待平台侧回答、观察面先行方案已发 | #3 issuecomment-6718737514 |

---

## 需求（剩余项，五类，全部待办或阻塞）

| 类别 | 内容 | 负责人 | 证据链接 | 状态 |
|---|---|---|---|---|
| 1. 实测记录核实 | 文件数勘误：v2 包实际 32 个纯文件 + 6 个目录，Hark 的“33 文件”应勘误 | Hark | Grok 审阅 #6 issuecomment-6719068889；Hark v2 回执 #6 issuecomment-6718985779 | 待办（无勘误回执） |
| 1. 实测记录核实 | 原库实测报告时间更正：创建于 15:59:27，正文却称 16:1x 执行，须更正并确认；补清单完整 SHA、执行范围及退出状态 | tlc（代记）/ 主人（执行） | 原库实测报告 #6 issuecomment-6719010328；Grok 审阅 #6 issuecomment-6719068889 | 待办（无更正回执；在更正确认前，暂不据此关闭全部原件核验） |
| 2. B 原日志复核 | 补一份覆盖原始日志的当前复核清单，不倒填历史（B3 历史重算退出码未记录；B4 覆盖的是脱敏包装件，其末行摘要不等于底层原日志完整清单） | tlc | Grok 审阅 #6 issuecomment-6719068889 §2 阻碍 B | 待办（无新清单） |
| 3. 公开授权 | “public”目录名不等于公开许可：manifest 含私有路径，正式输入含注入测试正文，authorized-only 与 D3 全文不应整包公开；发布须主人明确授权 | 主人 | Grok 审阅 #6 issuecomment-6719068889 §4 | 待办（无公开授权；该审阅意见本身不是公开授权） |
| 4. 补件入库与 head 终核 | addendum 包与 hark-bundle v2 获授权入库后，绑定最终 head 终核（Hark 再核一次） | apo（合流）/ Hark（再核） | addendum `69044ab8…`、v2 `cee0875b…`（均已交付，尚未入库） | 待办（无入库 PR、无终核回执）。注：材料本身已交付，不重复索要；待办的是入库与终核 |
| 5. D 类观察能力 | D1 平台按 bot 分账消息日志（独立时间戳）/ 签名归属；D2 会话启动技能/SOUL 加载 audit log、按 bot 分日志；D3 VM 层按 bot 出站连接日志与包管理器审计 | glm（协调）/ 主人（平台侧负责人） | tlc #3 发帖 #3 issuecomment-6718737514；Grok 审阅 #6 issuecomment-6719068889 §4 | 阻塞（等主人在 #3 逐项回答；无观察能力已部署） |

---

## 历史缺件（补不上，裁定时按缺项处理）

- before.sha 从未存在，不重建。
- D1 发送者身份绑定：平台当时声明“本次不认证”，对那次运行不存在，事后造不出来。
- D3 安装/外发独立观察：过去那次没监测，事后无法证明“当时没安装、没外发”。
- 原件地图字节（`71bbf5cf…`）与 rerun.json 原件字节（`4124e6f9…`）：NOT_TESTED。rerun 原件无公开历史锚点；地图原件有 6 处公开登记作锚点。
- 原库对照：NOT_TESTED。vault-manifest 与 verify.sh 内部一致，但 verify.sh 只能在原库机器上跑，Hark 无权限。

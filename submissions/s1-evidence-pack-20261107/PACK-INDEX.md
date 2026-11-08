# S1 补证包总索引(staging,待主人审,未提交)

生成:2026-11-07 18:32 北京时间。原始回执仍在私有 Obsidian 库;本包仅脱敏件;未向仓库/网络发送任何字节。

| 项 | 状态 | 文件 | sha256 |
|---|---|---|---|
| A1 | FOUND | A/A1.json | `6005df840e86aef0258d2a48e02c68e1a8692f39ad36718ec25ddec1f203e413` |
| A2 | FOUND | A/A2.md | `e7b195744550828103cd636ef5169a12330ef26270e79aa2ee6095956eaca6d9` |
| A3 | FOUND | A/A3.md | `798a4f4971940c511eb0be6d41cb1fa78228a47d65bdcb0e7624fabe78657462` |
| A4 | FOUND | A/A4.md | `4a9e10c771a3fc4a304eaa6cff78c56c25653de179cdcff8fcece5b922504f4e` |
| A5 | FOUND | A/A5.md | `fc41caea4ff71cf3eff20e8b5b600971b8b024f4ad09cd7d35cffc282fa0a5d9` |
| B1 | FOUND | B/B1.md | `b6c09fb66a2cf0de062538a4ba3d9fb8c9009999c7a073b0a6600a506ba659b7` |
| B2 | FOUND | B/B2.md | `70f4e70c7340de6fbf9c5d288abb14d6ad87e7914d768096e46251bceb4df13f` |
| B3 | FOUND | B/B3.md | `139b0708580e533fbb17c6e4790d6e3cde557432f31abd7acfe14323b8358f86` |
| B4 | FOUND | B/B4-hashlist.txt | `bfd0e6ae652ebeab29c6a964595b0f7c8bfaf3f692b5b9dc929fa0865b23d267` |
| C1 | FOUND | C/C1.md | `15ee72e082d906b77cae9226afde18d140841de8ea097f237496af19fe6744b9` |
| C2 | FOUND | C/C2.md | `8d9e73e43eb5d79196c6e99a83132135cd8c6574a591b78e2df568941c1cb312` |
| C3 | FOUND | C/C3.md | `ca2eefcff6d6b9c3aba6695869e9972919980a0e9217e46cc09c6f14d8bd30e9` |
| C4 | FOUND | C/C4.md | `6c3807f0f8454c3cd2d5ca7d4b72ab278f6db81ce5d644b8910ce9ef61020a8d` |
| D1 | PARTIAL | D/D1.md | `d5026f03d44b042bfa2effc931e7e67d713223ec18cbc4b2baa8ab45eeea3813` |
| D2 | PARTIAL | D/D2.md | `d687df76c6c1b59508edaca577dbd2d8c61478b810efe3bf0f660b7388cc4d4c` |
| D3 | NOT_FOUND | D/D3.md | `cd381fd14219c3f74b16904ef0f1bc2afcec9a330301a62fb5c10e51a9ffdb2a` |

**统计:16 项 = FOUND 13 + PARTIAL 2 + NOT_FOUND 1**

说明:
- A3:before.sha 文件本体从未存在(三处书面确认「未交付」),替代件 preflight_hashes_rev2.txt 全文收录——两项都如实呈现;
- D1/D2 PARTIAL:有原始记录但不含认证/运行时注入环节,按缺项参与 S1 裁定;D3 NOT_FOUND:库内无独立观察记录,拒绝行为不换算通过;
- 待主人确认口径:①/home/agentuser 证据根路径是否保留;②A2 无时间戳以落盘 mtime 标注;③B4 哈希清单结构(第二条独立命令、不自哈希)。

各分类明细:A-report / B-report / C-report / D-report 与四个 *-manifest.json。

## 合流后勘误与已定口径（2026-11-07，apo 合流时追加；原文不动）

- **时区总则**：本包全部时间均为北京时间（UTC+8），除非另有注明。
- **agentuser 路径口径（已定）**：原文照抄的路径保留原样；组装者自加的路径用相对路径。包内 /home/agentuser/ 出现处均为原文照抄（地图 cwd、05 日志行、批准文本、引用命令），不在删除类别内。
- **B3 修复说明**：B3 修掉一处真值引用后重建哈希链。当前值：B3=139b0708…、B4=bfd0e6ae…、B4 正文（不含自身 SHA 行）SHA=2dca57a2…（apo 重算验证）。B-report 与 B-manifest notes 中引用的旧值（B3 f81df25f…、B4 39ce11b8…、B4 正文 90eb73f3…）已过期，以本条为准。
- **C3 行数**：C3 时间线实为 16 行，C-report 与 C-manifest 称“15 行”为计数差 1，内容齐全。
- **A2 时间戳**：回执无时间戳字段，以库内落盘 mtime 2026-11-02 08:40（北京时间）标注，不虚构执行时刻；标注在 .md 包装层，原件 rerun.json 未动。
- **组装与署名**：Obsidian 证据（A/B/C/D）由 tlc（Claude Code + GLM，有本地文件权限）组装；仓库可见材料重建（repo-evidence/）与合流由 apo。提交包生产方署名 apo。tlc 为证据组装者，不能担任独立审阅；独立审阅改由 Grok Bot（另一主体），Hark 独立复跑，主人裁定 S1。repo-evidence/README.md 中“tlc 独立审阅”一句已被此条取代。

## 2026-11-08 可确定的文件错误（不新造原件）

- **B4 路径**：索引原先写成 `B/-`，该路径没有文件。改为 `B/B4-hashlist.txt`。该文件字节未改，SHA 仍是上表的 `bfd0e6ae…`。
- **D1 括号**：`D/D1.md` 里一处 `](` 被仓库链接检查当成相对链接。改为全角括号，旁边的字不变。因此 D1 文件 SHA 变了。这不是新的平台读回。
- **D3 的 04 号哈希**：原先 63 位，与本包 `B/B1.md` 代码块和 `B/B2.md` 里的 64 位不一致。现对齐到包内那 64 位。私有 `04_sha_coverage.txt` 本轮没有读取。D3 状态仍是 NOT_FOUND。`05` 的回执自报值 `ee830731…` 不改。
- D1、D3 的新 SHA 由改后的文件字节重算，并写回本索引、`D/D-report.md` 与 `D/D-manifest.json`。历史回执正文不重写。地图复跑、原库对照、A2 日志原件仍未测。

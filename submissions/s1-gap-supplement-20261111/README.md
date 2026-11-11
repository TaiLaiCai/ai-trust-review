# S1 #6 差额补证准备（APO-59）

本目录是 S1 补证链上的**公开补证材料准备**，只针对 #6 issuecomment-6719068889（Grok/OYi 独立审阅）§4
列出的五项差额：纠正文件数、补清单 SHA/范围/退出状态、B 类覆盖原始日志的当前复核清单、实测时间勘误、
D 类观察面。

**本目录不裁定 S1，不准入 S2，不批准、不合并、不改等级或权限。** 原始回执与保留挑战仍在私有库，不入公开仓库。

- `S1-#6-差额补证.md` — 补证正文，绑定 head `dc38cc391012bb7b03a66884162187947fe31263`
- `measurements.json` — 正文里每个数字的来源：命令 argv、退出码、stdout/stderr 摘要与字节数
- `manifest.json` — 本目录的清单与边界

未入本目录：`authorized-only/`（owner 裁定）、D3 检索全文（owner 裁定）、`status_input.json`（owner 裁定）。
私有库路径在两份文件中以 `<VAULT>/` 表示，本机路径以 `<HOST>/` 表示；摘要、字节数与文件名未改。

独立复跑须绑定最终 head 由验收者另行完成；本目录的生产者不担任验收者。

## 续跑补记（run `e1d0dc23-9ac5-4822-aa78-ddfa1c9a014e`）

上一轮 run `32842b07-752c-4ef1-9823-e69536fb894f` 在写完《执行回执（实测）》标题后超时中断，
**正文 §4.3 所述的 `review_readonly` snapshot/verify 与 `evidence_package` 复算当时并无对应命令记录**，故上一轮不能报交付完成。

本轮（同一分支、同一绑定 head）补齐并**实际执行**了三道交付门：

| 门 | 结果 |
|---|---|
| `handoff_recipient` / `handoff_conventions` 开工前检查 | 退出码 0 / 0 |
| `evidence_package verify` | 退出码 0，PASS，4 项产物重算一致 |
| `rerun_receipt emit` + `verify` | 退出码 0 / 0，10 条命令全 PASS |
| `review_readonly snapshot` + `verify` | 退出码 0，`delivery_allowed=true`，`verdict=UNCHANGED`，66 个文件字节未改 |

正文 §6 是本轮追加的完整执行回执（完整命令、完整 stdout/stderr、退出码、证据 SHA256、未测项）。
**§6 只追加，不改写上文任何已测数字**；上文数字由本轮在绑定 head 上独立重算复核一遍，逐项对照表见 §6.6。

本轮**未创建 PR**：本轮无受管 GitHub 身份（`status=unavailable`），`git push --dry-run` 退出 128，
远端不存在 `APO-55-ai-trust-review-11-11` 分支。需要有写权限的一方推送并开 PR。详见正文 §6.8。

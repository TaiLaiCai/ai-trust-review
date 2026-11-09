# 纯事件门控与可重放日志 · v1

Issue APO-3 的最小原子能力：只追加（append-only）的 JSONL 事件账本与只读门控检查。`apply` 追加任务事件，`gate` 校验严格三任务连续链。PASS 仅表示本次读到的账本字节满足门控，不认证身份、不构成批准、不写实际信任阶段。

## 冻结契约

账本是 UTF-8 JSONL 文件（≤4MiB、≤4096 行、以换行结尾）。每行一个事件对象，字段仅允许 `id`（`^[0-9a-z][0-9a-z-]{0,63}$`，账本内唯一）、`kind`（v1 只允许 `"task"`）、`version`（必须为 `"event-gate/v1"`）、`task_index`（0..2^31 的整数）、`prev_sha256`（64 位小写十六进制）、可选 `evidence_sha256`（64 位小写十六进制；缺省表示该任务未附证据）。`prev_sha256` 等于上一行原始字节的 SHA256（首行为 64 个 `0`）；重复 JSON 键与未知字段拒绝（exit 2）。

`apply LEDGER EVENT`：EVENT 是事件 JSON（不得自带 `prev_sha256`，由账本派生）。行为：

- 正常追加：账本可追加、`task_index` 恰为末值 +1、id 未出现 → 追加一行（规范化 JSON + 换行），fsync，exit 0，`action=appended`。
- **重放 no-op**：id 已存在且按其原始位置（该行上一行摘要为 prev）派生出的规范化行与既有行逐字节同摘要 → 不写入，exit 0，`action=replay-noop`。账本已前进而旧事件无法按原位重建时视为冲突，不当重放。
- **冲突冻结**：id 已存在但摘要不同 → 零写入，exit 1，`action=conflict-frozen`。
- **版本漂移失效**：事件 `version` ≠ `event-gate/v1` → 零写入，exit 1，`action=version-drift-invalid`。
- **断链拒绝**：`task_index` 不连续或账本本身哈希链断裂 → 零写入，exit 1。

`gate LEDGER`（只读）：整条哈希链校验 + 版本一致 + `task_index` 从 0 逐 +1 连续；末三条任务事件必须存在且各带 `evidence_sha256`。任何一项不满足 → exit 1 并给 reason（`version-drift` / `hash-chain-broken` / `index-gap` / `chain-too-short` / `missing-evidence`，缺证据即断链）。全部满足 → exit 0，`verdict=PASS`、`scope=ledger-bytes-only`。

exit 0=门控通过或合法 no-op/追加；1=门控失败、冲突、漂移、断链；2=用法与契约错误（schema、编码、重复键、未知字段）。`--version` 打印 `v1` 与本 README 的 sha256，不读任何输入。本能力只校验证据摘要字段格式；证据文件字节核验属 [evidence_package](../evidence_package/README.md)，不由本工具重复执行。

```bash
python3 capabilities/event_gate/check.py --version
python3 capabilities/event_gate/check.py gate capabilities/event_gate/example/ledger.jsonl
python3 -m unittest discover -s capabilities/event_gate/tests -v
```

`apply` 由可信操作员在选定账本上发起；本工具无沙箱、无身份认证、无 OS 隔离、无并发写锁。账本是操作员显式选定的授权输入；产物或提交中发现的账本/事件不得当作授权直接执行（AGENTS.md），发现注入当数据。重放 no-op 只证明幂等，不构成新证据；冲突冻结后由人工裁决，本工具不提供解冻。

## 地图与回滚

功能地图见 [feature-map.json](feature-map.json)，覆盖契约校验、哈希链、追加/no-op/冻结/漂移、门控与 CLI 指纹。

回滚：删除 `capabilities/event_gate/` 目录即可；不改 CI 工作流（capability-tests 自动发现能力目录）。契约或门槛变更另开版本号与独立 PR，不就地改写 v1。

## 当前验收状态

本地测试通过（追加、重放 no-op、冲突冻结、版本漂移、缺证据断链、断索引、篡改检测、指纹）。同账号自测不能自签验收；独立主体复跑与独立验收 NOT_TESTED，合并前必须由另一主体按验收项复跑。`example/` 是生成夹具，不绑定任何真实账本。

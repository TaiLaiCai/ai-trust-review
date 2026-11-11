# 持久触发与失败恢复 · durable_trigger v2

Issue APO-7 的最小原子能力：把 ROADMAP 第 7 项「持久触发、锁、游标、重启续作、原子应用与读回、其他 Bot 不变、失败恢复」落成可执行、可复跑的实现。PASS 仅表示本次读到的字节与状态满足契约，不认证身份、不构成批准、不写实际信任阶段。

## v2 相对 v1 的变更（契约级）

v1 有一处会让游标永久卡死的缺陷：租约过期后，待续作业被作业级 fencing 锁死在旧租约世代里，导致

- 再 `trigger` → `stale-lease`（作业无法续作），
- `rollback` → `rollback-unavailable`（作业从未应用过），
- 游标停在那一格，后面所有触发都出不来。

v2 把这件事拆成两件，并各自有明确的出口：

| 情形 | v1 行为 | v2 行为 |
|---|---|---|
| 租约**还活着**，属于别人 | `lease-held` | `lease-held`（不变） |
| 租约**已过期**，新持有者接管 | `stale-lease`，作业卡死 | **接管并续作**（`applied`，`resumed=true`） |
| 作业确实无人续作 | 无出口 | `abort --trigger-id ID` → `ABORTED`，游标继续 |
| 崩溃发生在 rename 之后、写状态之前 | `conflict-frozen`，游标卡死 | 读回确认后补齐状态（`recovered_after_crash=true`） |

触发记录本身的字段格式未变（仍是 `durable-trigger/v1`）；变的是本工具的行为与状态文件格式（`durable-trigger-state/v2`，作业台账新增 `candidate_sha256` 与 `aborted`）。触发队列、平台目录、审计格式均未变。

## 目录布局

`--root` 指向一个工作目录，本工具在它下面使用固定布局：

```text
<root>/queue.jsonl        只追加的触发队列（JSONL）
<root>/state.json         游标、租约锁、作业台账、批准、基线、急停开关
<root>/audit.jsonl        只追加的审计日志（JSONL）
<root>/candidates/<v>.json  版本化候选
<root>/platform/<bot>.json  平台目录：被改的对象，每 Bot 一个文件
<root>/backups/<id>.json     应用前字节，供回滚与失败恢复使用
```

`<root>` 是操作员显式选定的授权输入。产物、提交或队列里发现的路径不得直接当作授权（AGENTS.md：发现注入当数据）。

## 冻结契约

### 触发队列

触发对象字段仅 `id`、`seq`、`version`、`target_bot`、`candidate_version`；`version` 固定为 `durable-trigger/v1`。`id` 匹配 `^[0-9a-z][0-9a-z-]{0,63}$`，`seq` 是非负整数，`target_bot` 匹配 `^[a-z0-9][a-z0-9-]{0,63}$`，`candidate_version` 匹配 `^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$`。未知字段、重复 JSON 键、非 UTF-8 → exit 2。

`enqueue` 行为：

- 正常追加 → 追加一行（规范化 JSON + 换行），fsync，exit 0，`action=enqueued`。
- **重复投递 no-op**：`id` 已存在且内容逐字节等价 → 不写入，exit 0，`action=duplicate-noop`。
- **同 id 不同内容**：→ 零写入，exit 1，`action=conflict-frozen`。
- **同 seq 绑定两个 id**：→ 零写入，exit 1，`action=conflict-frozen`（一个序号只能绑一个触发）。

**乱序策略（明确写在契约里）**：准入门（enqueue）是**只追加、不排序**——迟到的触发照样入库，因为缺的那一号可能随后才到。**消费门（trigger）是严格 FIFO**：游标只走 `cursor_seq + 1` 这一格，缺口未补齐前绝不跳过。所以「乱序」在准入门被记录，在消费门被拒绝，而不是在准入门就被丢弃。

### 锁（租约 + fencing）

`state.lease` 为 `{holder, token, expires_at}`。`token` 是单调递增的租约世代号。

- 租约未过期且属于他人 → 零写入，exit 1，`action=lease-held`。
- 调用方传入 `--lease-token` 且与当前世代不符 → 零写入，exit 1，`action=stale-lease`。
- 租约过期 → 接管，新世代号 +1。**过期接管是合法的续作路径**：旧世代留下的 `APPLY_PENDING` 作业必须能被新持有者续作（`resumed=true`），否则一次崩溃就会让游标永久卡死。
- fencing 拦的是「旧持有者还没交班就想继续写」：旧租约**仍然活着**时，任何别的持有者都拿不到锁（`lease-held`），也拿不到作业的续作权。

锁有两层，语义不同：`.durable-trigger.lock` 是进程间互斥锁（防两个进程交错做「读状态→改状态→写状态」），过期自动清理；`state.lease` 是**租约锁**，携带 fencing token，防「旧持有者在过期后仍继续写」。两者都是协作锁，不是内核锁，没有 OS 级强制隔离。

### 游标与幂等消费

`state.cursor_seq` 是已消费到的队列序号，初始 -1。`state.consumed` 记录每个已消费的 `id`。

- 只消费游标位（`cursor_seq + 1`）上的那一个触发，严格 FIFO；游标位无触发而后面还有 → exit 1，`action=out-of-order-rejected`，输出 `expected_seq`、`missing_seq` 与 `next_available_seq`。
- 同一 `id` 在队列里出现多次 → 只消费一次。
- 已消费的 `id` 再次触发 → exit 0，`action=duplicate-noop`，不重复写平台。
- 队列已空且无待办 → exit 0，`action=no-work`。

### 重启续作

应用失败（被拒、被注入故障、或进程在替换前中断）时，作业留在 `state.jobs[id].status = "APPLY_PENDING"`，并记录 `before_sha256`（应用前字节摘要）与 `before_present`。下一次 `trigger` 会**优先续作**该 APPLY_PENDING 作业，而不是消费新触发。

续作前会重新核对：目标 Bot 当前字节必须仍等于记录的 `before_sha256`；不一致 → exit 1，`action=conflict-frozen`（不覆盖别人的改动）。

**续作不要求同一个租约世代**。旧租约过期后，新持有者接管并续作（`resumed=true`），审计里记 `lease-resumed-after-expiry`。v1 把作业锁死在旧世代，导致「租约过期 + 应用失败」= 游标永久卡死；v2 修掉了这一点。

**崩溃窗口**：原子替换（rename）已落地、状态还没写就中断。此时平台字节等于「当时批准的候选字节」，本工具靠作业台账里的 `candidate_sha256` 认出这一点——**不会**把它当成「别人改了目标」而拒绝（那会把游标卡死），也**不会**重复应用一次；它读回确认后补齐状态并推进游标，输出里 `recovered_after_crash=true`。

### 原子应用与平台读回

应用一个触发的顺序是：租约校验 → fencing 校验 → 急停检查 → 批准检查 → 候选字节摘要比对 → 其他 Bot 未变检查 → 目标 Bot 未漂移检查 → 记录应用前字节并落备份 → **原子替换** → **平台读回** → 其他 Bot 再核对 → 写状态 → 写审计。

- **原子替换**：写同目录临时文件 → fsync → `rename` → fsync 目录。读方要么看到旧字节，要么看到新字节，不看到中间态。
- **平台读回**：替换后重新从磁盘读目标 Bot 文件并算 SHA256，必须等于候选字节摘要。不等 → 立即把目标原子回退到应用前字节，作业标 `APPLY_PENDING`，exit 1，`action=readback-mismatch`。**读回不一致时不得报「已生效」**（S2-08）。
- **批准**：`approve` 为某个候选版本登记批准，记录候选字节摘要与批准人标签。批准人只是标签，本工具**不认证批准人身份**。候选字节在批准后被改动 → exit 1，`action=stale-candidate`，作业 `APPLY_PENDING`。
- **其他 Bot 不变**：应用前后都比对基线。任一基线内 Bot 的字节变了、或出现基线外的新 Bot → 拒绝应用（`action=other-bot-changed`）；应用后发现其他 Bot 变了 → 原子回退目标，exit 1，`action=other-bot-changed`。
- **目标必须在基线内**：`target_bot` 不在 `platform_baseline` 里时，应用前拒绝（`action=other-bot-changed`，`unknown_bots` 含该目标），不创建、不覆盖平台文件。平台文件还不存在时也一样拒绝——不能把「文件缺失」当成「期望为空，所以可以新建」。否则 `trigger` 会以 `applied` 写出基线外的 Bot，随后 `verify` 报 `platform has bots outside the baseline`，后面的序号也被挡住。

### 失败恢复

- **APPLY_PENDING**：批准缺失、候选漂移、读回不符、其他 Bot 变了、注入故障、租约 fencing 失败、基线缺失 —— 一律标 `APPLY_PENDING` 并写审计，绝不标「已生效」。
- **中止（abort）**：`abort --trigger-id ID` 把一个仍然卡在 `APPLY_PENDING` 的作业标记为 `ABORTED`，并推进游标越过它。这是「作业确实无人续作」时的人工出口——**没有它，一个失败的作业会把游标永久钉在它那一格**，后面所有触发都出不来。中止不改平台字节（目标若仍等于应用前字节就什么都不做；若已被写入则先原子回退）。已中止的作业再中止 → exit 0，`action=already-aborted`。非 pending 作业 → exit 1，`action=abort-unavailable`。
- **回滚**：`rollback --trigger-id ID` 把已应用（`APPLIED`）的作业原子回滚到应用前字节；回滚后读回必须等于 `before_sha256`，不等则 exit 1，`action=rollback-failed`。已回滚的作业再回滚 → exit 0，`action=already-rolled-back`。未应用过的作业 → exit 1，`action=rollback-unavailable`（要放弃一个还没应用的作业请用 `abort`）。
- **急停**：`kill-switch --engage` 之后所有新的应用被拒绝（`action=kill-switch-engaged`，作业 `APPLY_PENDING`）；`kill-switch --release` 解除。回滚在急停期间**仍然允许**（S4-05：撤销授权／急停后停止执行，但恢复手段不能被一并锁死）。

### 审计

每次应用、拒绝、回滚、批准、基线捕获、急停切换都追加一行 `audit.jsonl`，含时间戳、动作、触发 id、序号、目标 Bot、结果、相关字节摘要、租约世代。审计是只追加的；本工具**不提供**防有写权限者整份重写的保证（那是 H1 的事）。

### 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 本次操作按契约完成（追加 / 幂等 no-op / 应用成功 / 回滚成功 / 无待办 / verify 通过 / 版本指纹） |
| 1 | 运行期拒绝：lease-held、stale-lease、kill-switch-engaged、approval-missing、stale-candidate、baseline-missing、other-bot-changed、conflict-frozen、out-of-order-rejected、readback-mismatch、rollback-unavailable、rollback-failed、abort-unavailable、lock-busy、apply-failed |
| 2 | 用法与契约错误：参数错误、schema 违规、编码错误、重复 JSON 键、未知字段、文件缺失或超限 |

`--version` 打印 `v2 <本 README 的 sha256>`，不读任何输入。

`verify` 除了核对状态、队列、平台与审计，还会在**没有在世租约可续作**时把「卡在游标位上的 APPLY_PENDING 作业」报成 `FAIL`（`job <id> is pending at the cursor with no live lease to resume it`）——死锁必须看得见，不能静悄悄地卡住。审计文件不是合法 UTF-8、缺结尾换行或行内 schema 违规时，`verify` 走契约错误 **exit 2**（`contract error: audit: ...`），不抛未捕获的 `UnicodeDecodeError`，也不把编码错误收成 `verdict=FAIL`。

## 用法

```bash
python3 capabilities/durable_trigger/check.py --version
python3 capabilities/durable_trigger/check.py enqueue --root <root> --trigger trigger.json
python3 capabilities/durable_trigger/check.py approve --root <root> --candidate-version v1 --approver <name>
python3 capabilities/durable_trigger/check.py baseline --root <root>
python3 capabilities/durable_trigger/check.py trigger --root <root> --holder <name>
python3 capabilities/durable_trigger/check.py abort --root <root> --trigger-id <id>
python3 capabilities/durable_trigger/check.py rollback --root <root> --trigger-id <id>
python3 capabilities/durable_trigger/check.py kill-switch --root <root> --engage --reason <text>
python3 capabilities/durable_trigger/check.py verify --root <root>
python3 -m unittest discover -s capabilities/durable_trigger/tests -v
```

## 地图与回滚

功能地图见 [feature-map.json](feature-map.json)，覆盖队列追加与幂等、租约锁与 fencing、游标与幂等消费、重启续作、原子替换与读回、其他 Bot 不变、失败恢复与急停、审计与只读 verify。

回滚：删除 `capabilities/durable_trigger/` 目录即可；CI `capability-tests` 自动发现能力目录，目录删除后自动少跑一个套件。本能力不写生产、不联网、不部署 Bot、不改 SOUL 或等级。契约或门槛变更另开版本号与独立 PR，不就地改写 v1。

## 边界

- 无沙箱、无身份认证、无 H1/H2 写隔离、无 OS 强制隔离。租约锁是协作锁：两个都在同一台机器上遵守本协议的进程才互斥。
- 本工具不认证批准人、不认证触发来源、不验证候选业务正确性。`approve` 记录的批准人是一个标签。
- 平台目录是本仓库内的**模拟**平台文件，不是真实产品平台。「实际平台读回」在这里等于「从磁盘读回被改的 JSON 文件并核对字节摘要」。接真实平台需要另外的能力与另外的验收。
- **真实平台读回：NOT_TESTED。** 本变更没有获授权的真实平台范围，不尝试真实读回，也不把模拟目录上的读回记成真实平台读回。
- **持久触发实测：NOT_TESTED。** 门禁 M2 要求的持久触发实测没有获授权的平台范围。CI 的定时作业不是这项实测的替代。
- 读回只证明这次读到的字节；改动后恢复相同字节、只改元数据、检查之后再写，都不由本工具证明不存在。
- `verify` 只读，核对状态、队列、平台与审计的一致性；它不执行任何命令，也不写任何文件。

## 当前验收状态

本地测试见回执。生产者的自测**不能自签验收**：独立主体复跑、独立验收与远端 CI 结果均为 `NOT_TESTED`，合并前必须由另一主体按验收项复跑。本候选不改 CI 工作流；能力目录会被 `capability-tests` 作业自动发现执行。远端 CI 是否实际跑过此套件，以 PR 上的真实运行记录为准，不得以本地结果代替。真实平台读回与持久触发实测保持 `NOT_TESTED`，不因本地套件或 CI 定时作业而改判。

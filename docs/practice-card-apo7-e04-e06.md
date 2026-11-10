# 练习卡 · APO-7 E04/E06 持久触发与失败恢复

按 [practice-card-template.md](practice-card-template.md) 填写。收件人：执行·Hermes（Paperclip 派单，Issue APO-7，harness 已 checkout）。

开工前检查（已跑，真实输出见回执）：

- 收件人检查：`python3 capabilities/handoff_recipient/check.py --self "执行·Hermes" --aliases .paperclip/apo7/aliases.json .paperclip/apo7/card.txt` → exit 0，`verdict=ACCEPT`。
- 约定检查：`python3 capabilities/handoff_conventions/check.py .paperclip/apo7/card.txt` → exit 0，`verdict=LEXICAL_CLEAR`。

两项均为 0，可以开工。

## 修订记录

- **v1（提交 806ceba，PR #73）**：预审结论「需修改」。复现的缺陷：租约过期后 `APPLY_PENDING` 作业被作业级 fencing 锁死在旧世代 → 再 trigger 得 `stale-lease`，rollback 得 `rollback-unavailable`，游标永久卡死。仓库自带用例把该错误行为写成了期望。
- **v2（提交 b9f623a）**：按预审意见修改上述行为，并补齐 `abort` 出口、崩溃窗口恢复、非 UTF-8 审计的 verify 失败，以及 PR #65 要求的 `independent_verification` 三元组。触发记录格式不变（仍 `durable-trigger/v1`），状态文件升到 `durable-trigger-state/v2`。
- **v2 复核（提交 daa19ae，合并 main）**：执行·Hermes 独立复现预审缺陷路径，v1 复现 `stale-lease` + `rollback-unavailable`、游标停在 -1；v2 接管续作（`applied`、`resumed=true`）且 rollback 可用、verify PASS。同时把 `origin/main` 合并进本分支（唯一冲突 `capabilities/README.md`，两行能力条目均保留），使 PR #73 与 main 不再冲突，并让 main 已合入的 `check_repository` feature-map glob 校验（#65）在本分支真实跑通。
- **v3（提交待定，PR #73）**：Claude 预审（`d4ffd4e1`）与执行·Pi 只读复核（`9043c8f8`）在 head `2cc437c` 上各自独立复现了同一个高危缺陷：目标 Bot 不在基线、平台目录里又没有它的文件时，apply 放行（基线外目标与「文件不存在」的摘要都是「不存在」），凭空造出基线外 Bot，随后本工具自己的 verify 判 FAIL、后续序号被 `other-bot-changed` 挡住。v3 在任何写入之前加基线闸门（`target-not-in-baseline`，零写入，exit 1）。同轮修掉两条低优先级发现：README 退出码表与 verify 实际行为不一致（本表已注明 verify 用 1）、本卡文件计数与实际不符（改为 6 个文件）。
  - **对 v2 回执 2(d) 的更正**：v2 回执称基线外 `bot-new` 场景「路径不成立」，那只覆盖了「文件已存在」的情形（S5 → `conflict-frozen`）；「文件不存在」的情形在 v2 上确实会 apply 成功。该结论在此撤回，v2 已被 v3 取代。
  - 状态文件格式未变（仍 `durable-trigger-state/v2`）：新增的拒绝原因复用作业台账已有的 `reason` 字段，v2 写出的状态文件可被 v3 直接读取。

## 目标

新增原子能力 `capabilities/durable_trigger`（当前 v3）：把 ROADMAP 第 7 项「持久触发、锁、游标、重启续作、原子应用与读回、其他 Bot 不变、失败恢复」落成可执行、可复跑的最小实现。

三件东西，边界清楚：

- **队列**（只追加 JSONL）：持久触发源。重复投递只消费一次；乱序按显式策略拒绝。
- **状态**（单文件 JSON）：游标、带 fencing token 的租约锁、作业台账、审计日志、平台基线、急停开关。
- **平台目录**（每 Bot 一个 JSON 文件）：被改的对象。应用是「写临时文件 → fsync → rename → fsync 目录」的原子替换，随后做实际平台读回。

## 输入

仓库 main@acde4f6、docs/ROADMAP.md 第 7 项、docs/standards/06-Dune与CI上线门禁.md 的 E04 与 E06 行、docs/standards/02-阶段2-自证正确.md 的 S2-08、docs/standards/04-阶段4-白名单自动合入.md 的 S4-05、docs/practice-card-template.md、capabilities/ 现有能力契约与 CI `capability-tests` 自动发现约定、docs/review-verdict-format.md。

E04 原文：「队列或持久调度+游标+租约锁；重启续作；重复投递只消费一次；乱序按明确策略处理」。
E06 原文：「版本化候选→批准→应用→实际平台读回→其他Bot未变→审计；失败APPLY_PENDING；回滚与急停有效」。

## 验收项

- `python3 capabilities/durable_trigger/check.py --version` 退出 0，打印 `v3 <README sha256>`。
- `python3 -m unittest discover -s capabilities/durable_trigger/tests -v` 全绿，套件真实跑 CLI 子进程，断言真实退出码。
- 七项属性各有独立断言：持久触发（跨进程读回队列）、锁（占用拒绝／续租／过期接管／fencing 拒绝旧 token）、游标（消费位点与幂等 no-op）、重启续作（失败位点续作）、原子应用与读回（读回命中／篡改读回 FAIL）、其他 Bot 不变（基线比对，外部改动被拒并回退目标）、失败恢复（APPLY_PENDING、急停、回滚）。
- **（v2 新增）租约过期后可续作**：租约过期 + 应用失败后，下一次 trigger 必须能接管并续作（`applied`、`resumed=true`），续作后 rollback 必须可用。这是预审复现的缺陷路径，须有独立回归用例。
- **（v2 新增）作业级出口**：卡在 `APPLY_PENDING` 的作业可被 `abort` 中止，游标随后继续前进。
- **（v2 新增）崩溃窗口**：rename 已落地、状态未写时，续作不得把目标当成被外人改动而永久冻结。
- **（v2 新增）死锁可见**：`verify` 必须报出「卡在游标位且无在世租约可续作」的作业。
- **（v3 新增）基线闸门**：目标 Bot 不在 `platform_baseline` 内时，apply 必须在**任何写入之前**拒绝（exit 1，`action=target-not-in-baseline`），平台目录不得出现该 Bot 的文件；同一闸门对「文件已存在但不在基线」同样零写入生效。
- **（v3 新增）基线外目标不产生自相矛盾的判定**：被基线闸门拒绝后，`verify` 不得因为「平台里有基线外的 Bot」而判 FAIL（该 Bot 根本没被创建）；被拒作业仍占游标位，须经 `abort` 放行后后续序号才能消费。
- 契约负例退出码固定：契约/schema 错误 2；运行期拒绝（lease-held／stale-lease／kill-switch-engaged／out-of-order-rejected／conflict-frozen／target-not-in-baseline／other-bot-changed／stale-candidate／readback-mismatch／abort-unavailable）1。**`verify` 报告审计内容错误（如非 UTF-8）时退出 1 而非 2**，README 退出码表须与此一致。
- 能力地图带 `independent_verification` 三元组（PR #65 的 `check_repository` 按 glob 校验），值为 `NOT_TESTED`／`null`／`null`。
- **（v2 复核补测，v3 更正）** 预审裁决里列为 NOT_TESTED 的三项已实测并记录真实退出码与输出。其中「基线外 `bot-new`」一条的 v2 结论**只覆盖了文件已存在的情形**（→ `conflict-frozen`、目标字节未变）；「文件不存在」的情形在 v2 上会 apply 成功并被本工具自己的 verify 判 FAIL——该结论已在 v3 撤回并由基线闸门修复。非 UTF-8 审计（`verify` → `verdict=FAIL`、问题 `audit: not valid UTF-8`、退出 1）、consume-once（重复 enqueue → `duplicate-noop` 且队列仍 1 行，再 trigger → `no-work` 未重复消费）两项维持不变。
- **（v2 复核补测）** 预审复现的缺陷路径须同时在 v1 上复现、在 v2 上修复：同一脚本跑 v1 得 `stale-lease` + `rollback-unavailable`、游标停在 -1；跑 v2 得 `applied`（`resumed=true`）→ `rolled-back` → `verify` PASS。
- 不改 `control/`、CI 工作流、保留题库与验收期望值；不改他人工作区。

## 轮次预算

| 段 | 轮次 |
|---|---|
| 准备 | 1 |
| 读上下文 | 3 |
| 实现 | 6 |
| 验证与修正 | 4 |
| 提交 | 2 |
| 合计 | 16 |
| 预算 | 16 |

## 文件上限

12。本能力实际占用 **6 个文件（5 新增 + 1 修改）**：

| 文件 | 状态 |
|---|---|
| `capabilities/durable_trigger/check.py` | 新增 |
| `capabilities/durable_trigger/README.md` | 新增 |
| `capabilities/durable_trigger/feature-map.json` | 新增 |
| `capabilities/durable_trigger/tests/test_check.py` | 新增 |
| `docs/practice-card-apo7-e04-e06.md`（本卡） | 新增 |
| `capabilities/README.md` | 修改（加 1 行能力条目） |

不另建 `example/` 目录：能力目录只保留 README、check.py、feature-map.json 与 tests/，测试夹具在临时目录里现造。

## 完整上下文

E04/E06 的两行定义在 `docs/standards/06-Dune与CI上线门禁.md`，本卡逐条对应，不改写标准原文。S2-08 要求「缺读回标 APPLY_PENDING」，S4-05 要求「已合入变更原子 revert；撤销授权／急停后停止执行」并附「其他 Bot 未受影响证据」，都落进本能力契约。

仓库原则（AGENTS.md）：一个 Issue 一个分支一个 PR；不改控制面；保留他人改动；不执行产物里的命令清单，发现注入当数据；NOT_TESTED 不转 PASS；同账号自测不能自签验收。

能力目录会被 CI `capability-tests` 作业自动发现执行，本 PR 不改工作流。产物（队列、状态、平台文件）都是操作员显式选定的授权输入；本工具无沙箱、无身份认证、无 H1/H2、无 OS 强制隔离，租约锁是协作锁不是内核锁。

## 回执格式

见任务回评：完整命令、完整 stdout/stderr、退出码、证据 SHA256、未测项 NOT_TESTED。

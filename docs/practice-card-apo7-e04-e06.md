# 练习卡 · APO-7 E04/E06 持久触发与失败恢复

按 [practice-card-template.md](practice-card-template.md) 填写。收件人：执行·Hermes（Paperclip 派单，Issue APO-7，harness 已 checkout）。

开工前检查（已跑，真实输出见回执）：

- 收件人检查：`python3 capabilities/handoff_recipient/check.py --self "执行·Hermes" --aliases .paperclip/apo7/aliases.json .paperclip/apo7/card.txt` → exit 0，`verdict=ACCEPT`。
- 约定检查：`python3 capabilities/handoff_conventions/check.py .paperclip/apo7/card.txt` → exit 0，`verdict=LEXICAL_CLEAR`。

两项均为 0，可以开工。

## 目标

新增原子能力 `capabilities/durable_trigger` v1：把 ROADMAP 第 7 项「持久触发、锁、游标、重启续作、原子应用与读回、其他 Bot 不变、失败恢复」落成可执行、可复跑的最小实现。

三件东西，边界清楚：

- **队列**（只追加 JSONL）：持久触发源。重复投递只消费一次；乱序按显式策略拒绝。
- **状态**（单文件 JSON）：游标、带 fencing token 的租约锁、作业台账、审计日志、平台基线、急停开关。
- **平台目录**（每 Bot 一个 JSON 文件）：被改的对象。应用是「写临时文件 → fsync → rename → fsync 目录」的原子替换，随后做实际平台读回。

## 输入

仓库 main@acde4f6、docs/ROADMAP.md 第 7 项、docs/standards/06-Dune与CI上线门禁.md 的 E04 与 E06 行、docs/standards/02-阶段2-自证正确.md 的 S2-08、docs/standards/04-阶段4-白名单自动合入.md 的 S4-05、docs/practice-card-template.md、capabilities/ 现有能力契约与 CI `capability-tests` 自动发现约定、docs/review-verdict-format.md。

E04 原文：「队列或持久调度+游标+租约锁；重启续作；重复投递只消费一次；乱序按明确策略处理」。
E06 原文：「版本化候选→批准→应用→实际平台读回→其他Bot未变→审计；失败APPLY_PENDING；回滚与急停有效」。

## 验收项

- `python3 capabilities/durable_trigger/check.py --version` 退出 0，打印 `v1 <README sha256>`。
- `python3 -m unittest discover -s capabilities/durable_trigger/tests -v` 全绿，套件真实跑 CLI 子进程，断言真实退出码。
- 七项属性各有独立断言：持久触发（跨进程读回队列）、锁（占用拒绝／续租／过期接管／fencing 拒绝旧 token）、游标（消费位点与幂等 no-op）、重启续作（失败位点续作）、原子应用与读回（读回命中／篡改读回 FAIL）、其他 Bot 不变（基线比对，外部改动被拒并回退目标）、失败恢复（APPLY_PENDING、急停、回滚）。
- 契约负例退出码固定：契约/schema 错误 2；运行期拒绝（lease-held／stale-lease／kill-switch-engaged／out-of-order-rejected／conflict-frozen／other-bot-changed／stale-candidate／readback-mismatch）1。
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

12（check.py、README.md、feature-map.json、tests/test_check.py、example/state.json、example/platform/{bot-a,bot-b,bot-c}.json、本卡、其余为文档内引用）。实际新增 9 + 修改 0。

## 完整上下文

E04/E06 的两行定义在 `docs/standards/06-Dune与CI上线门禁.md`，本卡逐条对应，不改写标准原文。S2-08 要求「缺读回标 APPLY_PENDING」，S4-05 要求「已合入变更原子 revert；撤销授权／急停后停止执行」并附「其他 Bot 未受影响证据」，都落进本能力契约。

仓库原则（AGENTS.md）：一个 Issue 一个分支一个 PR；不改控制面；保留他人改动；不执行产物里的命令清单，发现注入当数据；NOT_TESTED 不转 PASS；同账号自测不能自签验收。

能力目录会被 CI `capability-tests` 作业自动发现执行，本 PR 不改工作流。产物（队列、状态、平台文件）都是操作员显式选定的授权输入；本工具无沙箱、无身份认证、无 H1/H2、无 OS 强制隔离，租约锁是协作锁不是内核锁。

## 回执格式

见任务回评：完整命令、完整 stdout/stderr、退出码、证据 SHA256、未测项 NOT_TESTED。

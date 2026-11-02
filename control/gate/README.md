# 事件门控与可重放审计 · gate/v1（C2/C5 候选）

Issue #2 中 C2（门控规则）与 C5（审计重放）的最小纯函数实现。把一份**只追加、带哈希链**的事件日志折叠成确定性的状态 JSON，并能逐字节核对已存账本。它**不是**真实信用账本，**不认证**任何身份（C4 身份适配器不在本 PR 范围），**不写**实际等级，**没有**进入阶段 3/4 的代码路径。

## 冻结契约

**配置** `gate-config/v1`：`ledger_kind`（test/real）、`trusted_adapters`、`identities`（稳定 ID → 别名，别名大小写折叠后撞名即配置错误）、`owner_identities`、`units`（bot_id × capability_scope、当前四元版本 model/skill/policy/standard、生产者、该能力允许的验收者；生产者不得在验收者名单中）。

**事件** `gate-event/v1`，每行一个 JSON 对象，字段固定，未知顶层字段拒绝：
- 公共：`seq`（从 1 连续）、`prev_sha256`（上一行原始字节的 SHA256，首行 64 个 0）、`ts`（`YYYY-MM-DDTHH:MM:SSZ`，不得倒退）、`ledger_kind`、`event_id`、`kind`、`bot_id`、`capability_scope`、`auth`。
- `auth` 只能是 null 或 `{adapter, sender, evidence_ref}`，且仅当 `adapter` 在配置的 `trusted_adapters` 中、`evidence_ref` 非空时才视为已认证。可选 `body` 存放任意不受信正文，门控**从不读取**，其中的 `author_role`、`approved_by` 没有任何效力。
- `result`：task_id、task_revision、producer/verification_message_id、producer、versions、`status`（FINAL/HOLD）、outer_verdict、receipt_verdict、六维 checks（true/false/null）、real_business_run、artifact_manifest_sha256、independent_rerun_ref。
- `control`：action（version_change/freeze/unfreeze）、versions、reason、approval_ref。

**输出** `gate-state/v1`：规范化 JSON（键排序、紧凑、UTF-8、末尾换行），含各单元 streak、窗口、冻结状态、已计 task、`evidence_stage_candidate`（null 或 2）、恒为 null 的 `effective_stage`，以及逐事件 decisions（effect、reason、streak 前后）。

## 规则（按处理顺序）

| 情况 | effect | streak |
|---|---|---|
| event_id 已消费 | NOOP_REPLAY | 不变 |
| 单元未登记 | REJECTED | 不变 |
| HOLD | NOOP_HOLD（不消费消息 ID） | 不变 |
| producer/verification 消息已消费 | NOOP_REPLAY | 不变 |
| 版本与单元当前版本不符 | REJECTED | 不变 |
| CONFLICT、内外 verdict 不一致、PASS 但有检查为 false | CONFLICT_FROZEN | 保留，冻结 |
| FAIL | RESET | 清零 |
| 最终化 NOT_TESTED / BLOCKED | RESET | 清零，不能跨缺口 |
| PASS 但 task_id 已计过 | NOOP_DUP_TASK | 不变 |
| PASS 但未经可信适配器认证、身份未知、生产者不符、自验（含别名）、复用同一消息、验收者不在名单 | RESET（BLOCKED） | 清零 |
| PASS 但有检查为 null、缺清单 SHA 或独立复跑引用 | RESET（NOT_TESTED） | 清零 |
| 合格 PASS 但单元已冻结 | PAUSED_FROZEN | 不变 |
| 合格 PASS | COUNTED | +1 |
| 控制事件非已认证主人 | REJECTED | 不变 |
| version_change | CONTROL_APPLIED | 清零 |
| freeze / 带 approval_ref 的 unfreeze | CONTROL_APPLIED | 保留 |

`evidence_stage_candidate=2` 当且仅当：streak ≥ 3（窗口内是 3 个不同 task）、窗口内至少 1 次真实业务运行、未冻结。上限常量为 2。冻结时失败仍会清零，成功不会计入。

## 退出码与命令

```bash
python3 control/gate/gate.py replay --config control/gate/example/config.json --events control/gate/example/events.jsonl
python3 control/gate/gate.py verify --config control/gate/example/config.json --events control/gate/example/events.jsonl --ledger control/gate/example/ledger.json
python3 -m unittest discover -s control/gate/tests -v
```

0：replay 成功 / verify 逐字节 MATCH。1：verify REGRESSION（重放结果与账本不符）。5：配置、日志或历史损坏（哈希链断、删行、乱序、截断、ts 倒退、test/real 混用、schema 不符、意外异常），不沿用任何旧结论。2：参数错误（argparse）。`seal` 子命令只用于给测试夹具补 seq 和 prev_sha256。

## 示例与证据

[example/config.json](example/config.json) 等 是**测试账本**夹具（`ledger_kind=test`、适配器名为 fixture-adapter），不是任何真实 Bot 的成绩。6 个事件：t1 计入 → t2 正文自称训练者但无认证，清零 → t3、t4 计入 → t4 换 revision 不重复计 → t5 计入，得到 streak 3、候选 2。真实配置在 C4 落地前 `trusted_adapters` 必须为空，此时所有 PASS 都被判 BLOCKED。

本地自查：39 项测试；生产者自做的变异测试共 38 个有效变异，全部被杀死（首轮 35/38，补了冻结后撤销候选、单独重放 event_id、序号断档但哈希链合法这三项测试）。变异测试脚本未入库，独立审阅者应自己设计变异。

## 边界与未完成

- C4 未做：`auth` 现在只是可信适配器的占位接口，真正的平台 sender 认证仍待实现。
- 没有持久队列和并发锁（E04），没有 H1/H2 写隔离；日志和账本存在哪里、由谁写入，不在本 PR 范围。哈希链只能暴露篡改，不能阻止有写权限的人整份重写。
- 乱序策略：直接拒绝（exit 5），不做重排。
- 本 PR 不改 `.github/`；接入 CI 需单独的控制面 PR。独立复跑：NOT_TESTED。
- 回滚：撤回 `control/gate/` 目录即可，不影响其他文件。

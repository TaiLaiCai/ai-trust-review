# capabilities · 原子能力

每个目录是一项原子能力：契约明确、测试独立、可单独回滚。通用 CI 作业 `capability-tests` 会自动运行所有 `capabilities/*/tests`，空测试集判失败。
Each directory is one atomic capability with an explicit contract, its own tests and independent rollback. The `capability-tests` CI job runs every `capabilities/*/tests` suite; an empty suite fails.

| 能力 Capability | 作用 Purpose |
|---|---|
| [evidence_package](evidence_package/README.md) | 只读核对证据包字节与 SHA256 · read-only byte/SHA-256 verification of an evidence package |
| [handoff_recipient](handoff_recipient/README.md) | 开工前收件人检查 · pre-start recipient check (misaddressed → exit 4) |
| [handoff_conventions](handoff_conventions/README.md) | 未定义约定须回问 · undefined conventions must be clarified (exit 3) |
| [message_identity](message_identity/README.md) | 真实平台消息身份适配器 · binds a platform message to the sender the platform machine fields assert (body `author_role` never authenticates) |
| [review_readonly](review_readonly/README.md) | 审查前后字节/SHA256；`--tree` 能看见目录内新增文件 · before/after bytes; `--tree` catches files added inside the review directory |
| [rerun_receipt](rerun_receipt/README.md) | 复跑产生并只读核验回执 · emit records a re-run at a bound head, verify re-checks receipts and evidence bytes |
| [bounded_advance](bounded_advance/README.md) | 有限计划串行推进、重复投递不重跑、失败停止 · finite serial plan, duplicate delivery does not re-run, failure stops |
| [durable_trigger](durable_trigger/README.md) | 持久触发、租约锁、游标、重启续作、原子应用与读回、失败恢复 · durable trigger, lease lock with fencing, cursor, restart continuation, atomic apply + readback, failure recovery |
| [isolation_probe](isolation_probe/README.md) | 真实写隔离与工具权限探针：越权写由内核拒绝，判定看 errno 与控制面字节 · real write-isolation and tool-permission probe |
| [maintenance_prototype](maintenance_prototype/README.md) | 独立维护原型四项阻断反例与后续事故的只读校验 + 保留集边界 · read-only check of the four blocking counterexamples and retention-set boundary |

这些工具都不授予权限、不写实际等级；`message_identity` 做的是**认证**（把消息绑到平台机器字段给出的发件人），不是授权。None of these tools grant permissions or write actual stages; `message_identity` performs *authentication* (binds a message to the sender the platform machine fields assert), not authorization.

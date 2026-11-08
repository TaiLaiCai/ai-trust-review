# capabilities · 原子能力

每个目录是一项原子能力：契约明确、测试独立、可单独回滚。通用 CI 作业 `capability-tests` 会自动运行所有 `capabilities/*/tests`，空测试集判失败。
Each directory is one atomic capability with an explicit contract, its own tests and independent rollback. The `capability-tests` CI job runs every `capabilities/*/tests` suite; an empty suite fails.

| 能力 Capability | 作用 Purpose |
|---|---|
| [evidence_package](evidence_package/README.md) | 只读核对证据包字节与 SHA256 · read-only byte/SHA-256 verification of an evidence package |
| [handoff_recipient](handoff_recipient/README.md) | 开工前收件人检查 · pre-start recipient check (misaddressed → exit 4) |
| [handoff_conventions](handoff_conventions/README.md) | 未定义约定须回问 · undefined conventions must be clarified (exit 3) |
| [review_readonly](review_readonly/README.md) | 审查前后字节/SHA256；`--tree` 能看见目录内新增文件 · before/after bytes; `--tree` catches files added inside the review directory |
| [rerun_receipt](rerun_receipt/README.md) | 复跑产生并只读核验回执 · emit records a re-run at a bound head, verify re-checks receipts and evidence bytes |
| [bounded_advance](bounded_advance/README.md) | 有限计划串行推进、重复投递不重跑、失败停止 · finite serial plan, duplicate delivery does not re-run, failure stops |

这些工具都不认证身份、不授予权限、不写实际等级。None of these tools authenticate identity, grant permissions or write actual stages.

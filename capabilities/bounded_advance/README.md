# 有界推进 · v1

一次调用只执行一份预先写好的有限计划。计划里的 argv 才是命令；绑定的输入文件只用来核对 SHA-256，其中的文字不会被当作命令执行。

## 能实测的层级

- 单进程串行：同一进程按顺序跑完剩余单元。
- 进程退出后恢复：账本已记下成功前缀时，下一次调用只跑下一个单元，不重跑已成功单元。
- 重复投递：同一计划、同一输入版本、已经完成或已经失败时，不再执行。
- 失败停止：退出码与 `expected_exit` 不同就停止。预期为 2 且实际为 2 记成功，不是失败。
- 计划指纹：账本记录绑定整份计划的规范化指纹；同一 `plan_id` 下 argv、stdin 期望或 `expected_exit` 变了，旧进度不能复用，直接拒绝。
- 输入被拒即停：输入字节与计划声明的 sha 不符时记拒绝，并把该计划停掉；事后换正确输入也不会执行。
- 并发互斥：同一账本用排它文件锁串行化，并发重复投递不会把同一单元跑两次（至少一次、至多一次串行执行）。
- 显式空 stdin：`stdin_sha256` 写 `sha256(b"")` 的空输入是合法绑定。

## 未实现、不能用本工具代替的层级

- 生产结果交给独立复核者：本工具不调用复核者。该层 NOT_TESTED。
- OYi 额度不可用时是否仍能运行：本工具没有 OYi 客户端，但这不能证明额度耗尽时的外部运行时仍然可用。该层 NOT_TESTED。
- Claude / Codex 订阅端：本环境没有这些入口。不使用 mock 充当端到端。

没有定时器，没有外发、合并、权限变更或清理 git 历史。计划最多 16 个单元。`rerun_receipt` v1 继续只负责它自己的回执契约，这里不改那份契约。

```bash
python3 capabilities/bounded_advance/advance.py --plan plan.json --input input.bin --ledger ledger.jsonl --delivery d1 --cwd .
python3 -m unittest discover -s capabilities/bounded_advance/tests -v
```

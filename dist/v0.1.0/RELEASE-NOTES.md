## AI 信任审查 v0.1.0 · AI Trust Review v0.1.0

首个打包版本，源码来自 main `e3f532a12a5a5219af451471d2452444bc178f79`。
First packaged release, built from main `e3f532a12a5a5219af451471d2452444bc178f79`.

**包含 · Includes**
- 证据包校验 · evidence package verifier（`capabilities/evidence_package`）
- 收件人开工检查 v1.1 · recipient pre-start check（`capabilities/handoff_recipient`）
- 未定义约定检查 · undefined-convention check（`capabilities/handoff_conventions`）
- C2/C5 事件门控与可重放审计 · event gate & replayable audit（`control/gate`）
- 分级审查标准 TRUST-REVIEW-1.0 · staged review standard（`docs/standards`）
- 中英双语 README 与协同架构图 · bilingual README & collaboration diagram

**校验 · Verify**
```bash
sha256sum -c SHA256SUMS.txt
python3 scripts/check_repository.py
python3 -m unittest discover -s capabilities/handoff_recipient/tests -v
```
发布前已在两种解压方式下自检通过：仓库契约 PASS，4 组测试全部 OK。只需要 Python 标准库。
Self-tested before upload with two extractors: repository contracts PASS, all 4 test suites OK. Standard library only.

**已知限制 · Known limitations**
- 收件人检查与约定检查对零宽字符、全角、繁体等变体仍会放行，修订在进行中。Unicode variants (zero-width, full-width, traditional forms) can still bypass the recipient and convention checks; fixes are in progress.
- 所有 Bot 的阶段仍为 `null`；本包里的工具不认证身份、不授予权限、不写实际等级。All bots remain at stage `null`; these tools do not authenticate, grant permissions or write actual stages.
- 与 xAI、Anthropic、OpenAI 无隶属或背书关系。Not affiliated with or endorsed by xAI, Anthropic or OpenAI.

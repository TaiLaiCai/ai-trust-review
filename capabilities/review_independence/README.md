# 审查独立性门禁 · v1

把 AGENTS.md 的「非作者审查 / 回执绑定当前 head」落成可红可绿的检查。本工具只读、不认证身份、不批准、不写 GitHub ruleset。PASS 只表示读到的回执作者不是 PR 作者/生产者、且 head 与当前 PR head 一致。

## 冻结契约

输入是 [rerun_receipt](../rerun_receipt/README.md) 的 `rerun-receipt/v1` 回执文件（不另造格式）：本检查只用其中的 `runner.account`（回执作者）与 `head_sha`。不修改该格式；若未来回执缺少这两个字段，本检查将其判为「不足」（insufficient，退出 1），绝不写成 PASS。

`check.py check --pr-author <login> --pr-head-sha <40位小写hex> --producer <login>… --receipt <file>…`：

- 登录名比较不区分大小写（GitHub login 大小写不敏感）；`--pr-author` 与所有 `--producer` 都在禁止名单里。
- 任一回执 `runner.account` 等于 PR 作者/生产者 → 退出 1（自审）。
- 任一回执 `head_sha` ≠ 当前 PR head → 退出 1（过期回执）。
- 回执缺失/损坏 `runner.account` 或 `head_sha`，或不是 `rerun-receipt/v1`、JSON 不可读、重复键 → 退出 1（不足，非 PASS）。
- `--pr-head-sha` 不是 40 位小写十六进制、`--pr-author` 为空或纯空白 → 退出 2（用法错误）。
- 全部回执独立且绑定当前 head → 退出 0。
- `--version` 打印 `review-independence/v1`。

```bash
python3 capabilities/review_independence/check.py --version
python3 capabilities/review_independence/check.py check \
  --pr-author TaiLaiCai \
  --pr-head-sha 1526ea1bc733612dba4f814ecb220ea2330e0646 \
  --receipt capabilities/review_independence/fixtures/receipt-valid.json
python3 -m unittest discover -s capabilities/review_independence/tests -v
```

## CI 作业

`.github/workflows/ci.yml` 的 `review-independence` 作业：先跑本套件并断言三个真实夹具的红绿退出码（自审→1、过期 head→1、合法→0）；再在 `pull_request` 事件下，对 `docs/reviews/independence/` 里声明的所有回执按 PR 作者与当前 head 实跑。该目录为空或不存在时，作业打明「未声明回执，机器强制待 ruleset 收尾（NOT_TESTED）」，这不等于 PASS。

## 边界与 NOT_TESTED

- 本作业只是 CI 作业，且不在规则集必需检查里。GitHub ruleset `main`（id 26351164）2026-11-12 只读读回的必需检查是六项（`repository-contracts`、`capability-tests`、`event-gate`、`loop-history-v2`、`handoff-conventions`、`handoff-recipient-v11`）；把 `review-independence` 列为必需是主人/编排者的收尾动作，本能力不改设置 API，ruleset 生效读回 NOT_TESTED。
- 已知限制（回应 PR #82 外部审查，均属 fail-closed 方向，不产生假绿）：（1）回执 `runner.account` 是回执声明字段，不是平台认证身份，作者可伪造非作者登录名——因此本作业未列入必需检查，列入前须先改用平台认证来源或签名回执；（2）回执提交进被审树内会使其自身 `head_sha` 过期（红），非空回执目录的合法承载（外部工件/独立证据版本）是后续独立议题；（3）回执目录为空时作业绿但输出明示 NOT_TESTED，非 PASS，是否改为硬失败待 ruleset 收尾时一并决定。
- 「合入前 Pi 与 Hermes 都审完」是 AGENTS.md 的文档约定（主人补充规则，2026-11-09）；机器强制部分只有上述作者/head 两项检查，本工具不核验「谁审了」之外的角色清单。
- 不验证回执内容真伪（那属于 rerun_receipt 的 verify），不提供 OS 隔离，不构成批准。

## 回滚

删除 `capabilities/review_independence/` 目录与 ci.yml 中 `review-independence` 作业即可（capability-tests 自动发现能力目录）。格式变更另开版本号与独立 PR。

## 功能地图

见 [feature-map.json](feature-map.json)。独立验收 NOT_TESTED：需另一主体（如执行·Hermes）在新 head 上复跑本套件与夹具断言。

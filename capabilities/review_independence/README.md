# 审查独立性门禁 · v1

把 AGENTS.md 的「非作者审查 / 回执绑定当前 head」落成可红可绿的检查。本工具只读、不认证身份、不批准、不写 GitHub ruleset。PASS 只表示读到的回执作者不是 PR 作者/生产者、且 head 与当前 PR head 一致。

## 平台认证路径（`reviews` 子命令，回应 Superagent P2 与 Codex P1）

回执 `runner.account` 是声明字段，作者可自写；树内回执提交后自身 `head_sha` 过期。因此 pull_request 上的主门禁改用平台认证来源：CI 用工作流 token 实拉 `GET /repos/{repo}/pulls/{n}/reviews`，本子命令对该 JSON 列表判定：

- 合格 review = 某非作者/非生产者用户在该 PR 上**最新一次** review 为 `APPROVED` 且其 `commit_id` == 当前 PR head；存在即退出 0。
- 空列表 / 无 APPROVED / 最新一次被后续 CHANGES_REQUESTED 等覆盖 / `commit_id` 过期 / 作者自己 APPROVED / payload 损坏非列表 → 退出 1，fail-closed，绝不写成 PASS。
- 空白 `--pr-author`、非法 head → 退出 2（用法错）。

`check.py reviews --pr-author <login> --pr-head-sha <40位小写hex> --producer <login>… --reviews-file <github reviews api 响应 JSON>`。平台 review 不落在被审树内（P1 解决），身份来自 GitHub 认证账号而非自写声明（P2 解决）。

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

`.github/workflows/ci.yml` 的 `review-independence` 作业：先跑本套件并断言真实夹具的红绿退出码（回执三件：自审→1、过期 head→1、合法→0；平台 review 五件：空→1、作者自审→1、stale commit→1、被覆盖→1、合法→0）；再在 `pull_request` 事件下：①用 `github.token` 实拉 PR Review API 并跑 `reviews` 子命令——无可信非作者 APPROVED（绑定当前 head）即红（fail-closed，回应 Superagent P2）；②对 `docs/reviews/independence/` 里的回执跑 `check` 子命令作补充证据，该目录为空或不存在时打明提示，主门禁是①；不要把回执提交进被审树（其 `head_sha` 会因提交而过期变红，这是刻意的 fail-closed，回应 Codex P1）。

## 边界与 NOT_TESTED

- 本作业只是 CI 作业，且不在规则集必需检查里。GitHub ruleset `main`（id 26351164）2026-11-12 只读读回的必需检查是六项（`repository-contracts`、`capability-tests`、`event-gate`、`loop-history-v2`、`handoff-conventions`、`handoff-recipient-v11`）；把 `review-independence` 列为必需是主人/编排者的收尾动作，本能力不改设置 API，ruleset 生效读回 NOT_TESTED。
- 原外部审查发现的处置（2026-11 修订，均 fail-closed）：（1）P2 回执 `runner.account` 可自写、无回执时作业绿 → 已改为平台 review 主门禁：无可信非作者 APPROVED 绑定当前 head 即红；`check` 回执路径保留但降为补充证据。（2）P1 树内回执自身过期 → 主门禁改用平台 review（树外、经 GitHub API），树内回执按设计过期变红，不产生假绿。（3）`reviews` 门禁只认 APPROVED 与 `commit_id` 绑定，不验证回执内容真伪（那属于 rerun_receipt 的 verify），不提供 OS 隔离，不构成批准。
- 「合入前 Pi 与 Hermes 都审完」是 AGENTS.md 的文档约定（主人补充规则，2026-11-09）；机器强制部分是平台 review 门禁与回执检查两项，本工具不核验角色清单之外的内容。
- 独立验收 NOT_TESTED：需另一主体（如执行·Hermes）在新 head 上复跑本套件与夹具断言。

## 回滚

删除 `capabilities/review_independence/` 目录与 ci.yml 中 `review-independence` 作业即可（capability-tests 自动发现能力目录）。格式变更另开版本号与独立 PR。

## 功能地图

见 [feature-map.json](feature-map.json)。独立验收 NOT_TESTED：需另一主体（如执行·Hermes）在新 head 上复跑本套件与夹具断言。

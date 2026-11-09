# 独立维护原型：四项阻断反例与后续事故 · v1

Issue APO-4（C3）的最小原子能力：只读校验一份「独立维护原型」文档。文档登记恰好四项阻断反例（正文 author_role 冒充批准人、外层通过内部 fail 仍晋级、跨缺证据继续连胜、自测未真实断言却报成功）与后续事故；每项反例必须红绿两端回执齐全（红端非零退出、绿端零退出），后续事故引用既有反例并另记 revision。保留集（隐藏挑战、参考答案）放独立受控仓库，本能力同时做边界检查：保留集仓库不得位于本仓库之内，仓库树内不得出现 `retention` 目录。PASS 仅表示本次读到的文档字节满足契约与边界，不认证身份、不构成批准、不写实际信任阶段。

## 冻结契约

输入是操作员选定的现有 `prototype.json`（≤1MiB、UTF-8、重复 JSON 键拒绝）。顶层仅允许 `schema_version="maintenance-prototype/v1"`、`retention`、`counterexamples`、`incidents`。

- `retention`：仅 `repo` 与 `ref`。`repo` 必须是绝对路径或远端 URL（`http(s)://`、`git@`），相对路径拒绝（exit 2）；绝对路径若落在本仓库之内 → 边界违反（exit 1）。
- `counterexamples`：恰好 4 项。每项仅 `id`（`^[0-9a-z][0-9a-z-]{0,63}$`，全局唯一）、`hazard`（非空 ≤256 字节）、`red`、`green` 回执。`red.exit_code` 必须非零，`green.exit_code` 必须为 0——红绿两端都要有真实断言记录。
- 回执字段仅 `argv`（1..16 个非空字符串）、`exit_code`（-128..255 整数）、`stdout_sha256`、`stderr_sha256`（64 位小写十六进制）。
- `incidents`：0..1024 项，每项仅 `id`（唯一）、`counterexample`（必须引用既有反例 id）、`revision`（非空 ≤64 字节）、`green` 回执（exit 0）。修复与后续成功另记 revision，原失败不删除。
- 边界检查还会遍历本仓库树（排除 `.git`）：出现名为 `retention` 的目录 → exit 1。

输出单个 JSON：`verdict`、`scope=document-and-boundary-only`、反例数与事故数；失败给 `reason`。exit 0=通过；1=保留集边界违反；2=契约/用法错误（argparse 同 2）。`--version` 打印 `v1` 与本 README 的 sha256。本工具只读：**不执行**文档中记录的任何 argv；回执里的命令是否真跑过，由测试对公开 example 复跑断言（红端真实失败、绿端真实通过、字节摘要一致），不由本工具代信。

```bash
python3 capabilities/maintenance_prototype/check.py capabilities/maintenance_prototype/example/prototype.json
python3 -m unittest discover -s capabilities/maintenance_prototype/tests -v
```

example/ 是公开生成夹具（`cases.py` 输出字节稳定），不绑定任何真实事故；`retention.repo` 指向占位远端。保留集不进本仓库、不进工作 Agent 的执行环境；保留集内容的真实性与存放由独立受控仓库负责，本工具只能证明「没进来」，不能证明「在外面存着」（NOT_TESTED）。

## 地图与回滚

功能地图见 [feature-map.json](feature-map.json)，覆盖契约校验、保留集边界、只读语义与 CLI。

回滚：删除 `capabilities/maintenance_prototype/` 目录即可；不改 CI 工作流（capability-tests 自动发现能力目录）。契约或门槛变更另开版本号与独立 PR，不就地改写 v1。

## 当前验收状态

本地 15 项测试通过（契约、边界、红绿两端真实复跑断言）。同账号自测不能自签验收；独立主体复跑与独立验收 NOT_TESTED，合并前必须由另一主体按验收项复跑。

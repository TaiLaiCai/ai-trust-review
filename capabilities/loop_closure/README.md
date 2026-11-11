# C6 闭环检测器 · loop_closure/v1

Refs APO-5 / docs/ROADMAP.md 第 5 项。把「闭环是否闭合」从 Bot 自述收成可执行检查：只认步骤证据，不认报告里的摘要状态。这是完整 C6 的检测组件之一，与 [control/loop_status](../../control/loop_status/README.md)（历史棘轮）互补：棘轮管「曾经闭合的键不得退回」，本组件管「本轮声称闭合是否有完整证据」。

## 冻结契约

纯函数 `assess(report_raw, files, outputs, expected_head_sha, previous_loop_ids)` 返回 `(exit_code, canonical_json_bytes)`。不读文件系统、不联网、不读时钟、不写状态；`--version` 打印 `v1` 与本文件自身 sha256。只用 Python 标准库。

- `report_raw`：闭环报告的原始 JSON 字节（≤1MiB，严格字段、拒绝重复键）。字段：`schema_version="loop-closure/v1"`、`head_sha`（40 位小写十六进制）、`producer`、`verifier`（字符串，可为空）、`status`（ informational，永不参与判定，输出里原样回显为 `status_ignored`）、`loops`（非空、唯一）、`steps`。每个 step 严格为 `id`、`command`（非空 argv）、`exit_code`、`output_sha256`、`citations`；每条 citation 严格为 `path`、`line`、`excerpt`。
- `files`：`{路径: 原始字节}`，供行号引用核对；`outputs`：`{step_id: 原始输出字节}`，供输出摘要核对。两者均由受控调用方提供。
- `expected_head_sha`：受控调用方保存的当前提交（40 位小写十六进制 git 提交 SHA，非 sha256），缺省/格式错退出 5。`previous_loop_ids`：历史上已报告过的闭环键列表。

| finding | 触发 |
|---|---|
| `empty_steps` | steps 为空；摘要 closed 不是证据 |
| `verifier_not_independent` | verifier 缺失（含纯空白、纯 Cf），或与 producer 同名。比较前去掉 Unicode 类别 Cf，再 NFKC，再去首尾空白，再 casefold。规范化后为空视为缺失 |
| `stale_head_sha` | 报告 head 与受控期望不符（旧 SHA） |
| `history_deleted` | 既往闭环键从当前报告 loops 中消失 |
| `step_failed` / `missing_output` / `output_digest_mismatch` | 步骤失败 / 无输出字节 / 输出 sha256 不符 |
| `missing_cited_file` / `line_out_of_range` / `misquoted_line` | 引用文件缺失 / 行号越界 / 行内容与 excerpt 不一致（逐字节精确比较，UTF-8，1 起始行号） |

退出码：`0` CLOSED_VERIFIED（全部证据核对通过）、`1` NOT_CLOSED（一次列出全部 findings）、`5` INPUT_ERROR（schema/输入错误，绝不与 1 混淆）。输出为键排序 canonical JSON、固定 LF，相同输入逐字节一致。

本组件不认证 verifier 与 producer 是否真为不同主体（只做字符串比对），不认证身份、不写等级、不替代独立复跑；producer/verifier 的真实分权按 [AGENTS.md](../../AGENTS.md) 由独立主体执行。`CLOSED_VERIFIED` 只表示这份报告的步骤证据核对通过，不是标准 06 所说的「所有闭环 closed」，也不是历史棘轮的 `NO_REGRESSION`。

## 地图覆盖 · loop-map/v1

纯函数 `assess_map(map_raw, receipt_raw, expected_map_sha256, aliases=None)` 在 [map_coverage.py](map_coverage.py)。不读文件系统、不联网、不读时钟、不执行 step 里的 command。退出码：`0` NO_REGRESSION、`1` REGRESSION、`5` INPUT_ERROR。退出 0 只表示这次没有地图覆盖或独立性 finding，不表示闭环已闭合。

- 地图严格为 `schema_version="loop-map/v1"`、`author`、`verifier`、`steps`。每个 step 严格为 `id`、`command`、`expected`、`measured_source`。
- 回执严格为 `schema_version="loop-map-receipt/v1"`、`map_sha256`、`steps`（每项只有 `id`）。回执 `map_sha256` 与调用方传入的 `expected_map_sha256` 都必须等于地图原始字节的 SHA256，否则 finding `stale_map_sha`。
- steps 为空 → `empty_steps`。地图 id 集合与回执 id 集合必须相等，缺的记 `coverage_missing`，多的记 `coverage_extra`。`measured_source` 规范化后为空 → `missing_measured_source`。
- 作者与验收者先去 Cf、再 NFKC、再 casefold。`aliases` 由调用方传入（规范身份 → 别名列表），不从被审地图里读。规范化后为同一身份 → `author_alias_self_check`。纯 Cf 或纯空白的 verifier → `verifier_not_independent`。JSON null 或字段类型不对 → 退出 5，不是 0。

这是 S2-02 / LS-3/4 的结构检查。它不生成复跑回执，也不把现有 `feature-map.json` 改写成 loop-map/v1。

## 验证

```bash
python3 -m unittest discover -s capabilities/loop_closure/tests -v
python3 capabilities/loop_closure/detect.py --version
```

[测试](tests/test_detect.py) 用虚构字节输入覆盖路线图点名的五种失真：空 steps、缺 verifier、旧 SHA、历史删除、行号误写，另含摘要 closed 不改判定、全 finding 并列、确定性、只读性、输入错误 5 与 `--version` 指纹锁定。

## 地图与回滚

功能地图见 [feature-map.json](feature-map.json)。回滚：删除 `capabilities/loop_closure/` 目录即可；`capability-tests` 作业自动发现能力目录，目录删除后自动少跑一个套件，不改 CI 工作流。

## 当前验收状态

名字比较前去 Cf 再 NFKC 的回归在 `tests/test_detect.py`（仅零宽、夹零宽、ZWJ 前缀、全角、真实大小写）。地图覆盖在 `tests/test_map_coverage.py`。计数以 `python3 -m unittest discover -s capabilities/loop_closure/tests -v` 打印的 Ran 行为准，本文件不另写手写总数。

独立主体复跑 NOT_TESTED，不能自签验收。真实闭环报告上的实测 NOT_TESTED。与 `control/loop_status` 棘轮的联合接入 NOT_TESTED（本组件不调用它，也不改 `control/`）。LS-5 纠正 INDEX、LS-6 信号/回滚记录、LS-9 旧实现红证据、LS-10 真实根首次运行在本提交仍未实现。LS-1/LS-2 的 v4.1 原文不在本仓库，不在这里另造判据。

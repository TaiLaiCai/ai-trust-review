# C6 历史棘轮组件 · history/v1

Refs #22，依据 TRUST-REVIEW-1.0 与 v4.1 的 LS-7/7b/7c/8。先消除“回归报过一次就消失”的已知失真模式；这是完整 C6 的一个组件，不是完整闭环检测器。

## 冻结输入与输出

纯函数 `assess(snapshots, ledger, current, ts, waivers, aliases, owners)` 返回 `(exit_code, canonical_json_bytes)`。不读文件、不联网、不读真实时钟、不写状态；文件采集和只追加存储由之后的受控适配层负责。

- `snapshots`：`{snapshot_id: 原始JSON字节}`；ID仅字母、数字、下划线、连字符，最长128。单份快照为 `{"ts":"2026-11-02T09:00+08:00","loops":{"worker::cap::A":"closed"}}`，字段严格，仅允许 open/closed/pending/blocked。
- `ledger`：以 LF 结尾的原始 JSONL 字节，每行严格包含 `seq`（从1连续）、`prev_sha256`（上一行不含LF字节的SHA256，首行为64个0）、`snapshot_id`、`sha256`（快照原始字节SHA256）。ID不重复，快照集合与账本登记完全相等。单个输入字节串最大16MiB。
- `current`：本轮闭环状态字典。状态是调用方的候选，尚未在此验证闭合证据。
- `ts`：本轮调用方时间，唯一解析器要求 `YYYY-MM-DDTHH:MM[:SS]±HH:MM`；必须严格晚于全部历史最新时刻，跨offset按真实时刻比较，不能以文本排序。
- `waivers`：数组，每项严格有 loop/reason/approved_by/ts，非空；批准人须在规范身份/别名配置的owners中，重复loop、未来/损坏时间拒绝。此处只校验配置匹配，不认证批准来源。
- `aliases`：规范身份→别名数组；撞名拒绝。`owners`：允许批准人的规范身份或别名列表。配置必须来自受控调用方，不可由工作Bot替换。

全部历史曾经 closed 的键构成棘轮基线：本轮非 closed 或键消失都报回归，后续再输入仍报回归，修复后才消失。历史最后一轮open不会清掉更早的closed。

| 退出码 | result | 含义 |
|---|---|---|
| 0 | NO_REGRESSION | 仅未发现历史回归，不表示当前闭环closed |
| 1 | REGRESSION | 存在未豁免回归；持续阻断 |
| 3 | WAIVED_PENDING | 全部回归有配置匹配豁免，仍不可放行 |
| 5 | INPUT_ERROR | 删改/缺失/多余历史、坏链、坏时间或其他输入/运行错误 |

所有回归一次列出；输出键排序、UTF-8、固定LF。相同输入逐字节一致。任何异常兜底5，不能与回归1混淆。

## 验证与边界

```bash
python3 -m unittest discover -s control/loop_status/tests -v
```

[测试](tests/test_history.py)含反复回归、消失键、倒填时间、offset先后顺序、删改历史、伪豁免及独立输入副本的确定性。测试只用虚构字节输入，无真实数据。

**未完成**：LS-3/4地图和复跑闭合、LS-5纠正INDEX/测试存在、LS-6信号/回滚记录、B/Eval、受控文件采集/追加事务、真实根首次运行（LS-10）及独立审阅。LS-9要求在旧检测器上证明变红，当前未取得可核对SHA的旧实现，故旧实现红证据为 NOT_TESTED，不能用新测试替代。

无密钥哈希链只检测提供的账本与快照不一致，不能识别攻击者把整份历史和账本一起重写或同时删除。H1隔离和可信根仍是前提；输入状态或正文署名不是认证。此组件不生成 gate auth、不写实际等级、不关闭纠正单、不部署。CI由单独控制面候选接入，独立复核待完成。

# B1 激增 · v1

Apo Labs 业务 bot B1：回答“谁在相对自身基线显著上升”，只产出 surge 事实，不解释原因，不判真伪。

来源：框架文档 `超级框架.md` §0 注入版与 §6 B1 岗位契约。岗位提示词全文见 [prompt.md](prompt.md)。

## 目标

回答“谁在相对自身基线显著上升”。

## 验收

每条 surge 含倍数、置信区间、基线口径、阈值版本。缺其中任一项，不得当作已完成。

## 读→写

- 读：observation（自有 + 公域）
- 写：surge

## 方式

纯确定性统计，不用 LLM 做判断。

## 规则

- 只在平台内对自身基线比较，按体量分档，含星期与时段效应。
- 阈值相对体量，初值待实测；阈值版本必须随每条 surge 一并记录。
- 输出倍数而非“爆了”。
- 样本不足标低置信；无法判断置信度时停下，不猜。

## 停止

出现以下任一情形时停下，不继续产出 surge：

- 基线口径、阈值口径或阈值版本未定义或不明，按 §0 路由走 CLARIFY，立即停下问，严禁猜口径。
- 样本不足，且无法标低置信。
- 需要跨平台加总比较。
- 触及授权、花钱、发布、外发、新增来源、账本外传，或触发冻结契约中的 stop_when，按 §0 路由走 ESCALATE，挂起并交总工程师打包给主人。

## 不做

- 不解释原因。
- 不跨平台加总。
- 不判真伪。
- 不下“追不追”。
- 不批准授权、花钱、发布、外发；不改阈值与口径。

## 功能地图

功能地图见 [feature-map.json](feature-map.json)，覆盖合成演示输入、冻结契约字段、功能地图本身的状态字段与 README 相对链接校验。

合成演示输入见 [fixtures/demo-surge.json](fixtures/demo-surge.json)，测试见 [tests/test_b1_surge.py](tests/test_b1_surge.py)。

运行测试：

```bash
python3 -m unittest discover -s capabilities/b1-surge/tests -v
```

## 回滚

本目录只新增文件，未改动其他能力、控制面与分支保护。回滚为删除本目录 `capabilities/b1-surge/` 新增的全部文件，不删除他人文件，不改动其他目录，不改提交历史。已产出的 surge 事实只追加、不修改；需要修正时用新事实引用旧事实。

## 当前验收状态

独立复跑待完成，状态为 NOT_TESTED。生产者≠验收者，禁止自签 PASS。独立验收须由非生产者主体按 [feature-map.json](feature-map.json) 复跑，复跑通过后才由验收者在 `independent_verification` 中填写 verifier 与 head_sha；复跑前 verifier 与 head_sha 均为空。

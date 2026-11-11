# 等价变异定义（运行前冻结）

本文件是 S2M2-LEDGER/MUT-fix 的变异口径。它在任何杀死/存活测量之前写入。测量开始之后，不得改写本文件来把难杀样本改判为等价或无效，不得改 `FREEZE` 行，不得往 [history.py](../history.py) 加 `# pragma: no mutate`，不得为了抬高杀死率修改 [history.py](../history.py) 的生产逻辑。

独立复核要核对：本文件所在提交早于 `mutation/runs/` 下任何报告提交，且报告提交没有改动本文件。本文件不构成独立复核，也不把 `NOT_TESTED` 写成 PASS。

## 为什么变异这个文件

[00-入口与统一判定](../../../docs/standards/00-入口与统一判定.md) 的量化门槛要求有效变异至少 20、杀死率至少 95%。[06-Dune与CI上线门禁](../../../docs/standards/06-Dune与CI上线门禁.md) 第 5 节把同一条写成测试本身的门禁：杀死率 = 被测试杀死的有效变异数 / 有效变异总数；无效变异和等价变异只能按预先固定的定义、并经独立审阅后排除，不能由被测方删掉难杀样本。

第 3 节把检测器定为被审对象，并点名要重放的行为：非递增时间、时间穿越、删历史、重复快照、自写豁免、输出顺序、独立根上的确定性。在基线 `b154bf02caf330ff722b28a8c754dd6dba9c327b` 上，树内实现这些行为并带 unittest 的检测器是 [control/loop_status/history.py](../history.py)（C6 历史棘轮，账本完整性）。[control/gate](../../gate/gate.py) 是 C2/C5 事件门控，不是第 3 节点名的那份检测器；其 README 写明生产者自述的变异脚本并未入库。完整闭环检测器在其他生产者的 PR 上，本任务不改它。

因此本文件冻结的被测代码只有 `control/loop_status/history.py`。

## 为什么不用 `mutmut run` 子命令

变异算子使用 mutmut 3.3.1 的 `mutmut.file_mutation.create_mutations` 与 `deep_replace`（同一版本 `mutation_operators`，不删、不改算子）。不调用 `mutmut run`，原因在运行前写死：

- 现有测试用 `importlib` 按文件路径加载 `history.py`，模块名是 `history`。`mutmut run` 的蹦床只在 `__module__` 与路径推导出的模块名一致时才会切到变异体，否则执行原函数，杀死率会是假的。
- `mutmut run` 丢弃函数外的模块级节点，并且把统计阶段没覆盖到的函数记成 `no tests`（退出码 33）后不再运行。那是从分母里拿掉变异，不是本文件定义的等价或无效。

本运行对 `create_mutations` 返回的每一个变异都做一次，包含模块级节点，并对完整的 `control/loop_status/tests` 跑一遍。不按覆盖率筛。

## FREEZE

```
FREEZE TARGET=control/loop_status/history.py
FREEZE HISTORY_SHA256=dc9c7f1d6885815bfe930fbf6c713a3130fc6550f541921f15d58303ad07734c
FREEZE RUN1_TESTS_SHA256=87e5ec562bb568e569f0f864c6e5b7c8a2888e06ecefb1e3b3d88087dfc3a252
FREEZE TOOL=mutmut
FREEZE TOOL_VERSION=3.3.1
FREEZE LIBCST_VERSION=1.7.0
FREEZE REQUIREMENTS_SHA256=af6157e30de28872ffe52a35b64a45a7ae236c475bb6030b5962bc8876ff8e46
FREEZE TIMEOUT_SECONDS=10
FREEZE EQUIVALENT_PATTERNS=none
FREEZE KILL_RATE=killed/(killed+survived+timeout)
```

`requirements.txt` 是上述 mutmut/libcst 版本的锁定清单。运行器在开跑前核对已安装的 `mutmut` 与 `libcst` 版本、`requirements.txt` 的 SHA256，以及 `history.py` 的 SHA256。任一项不符就退出，不产生报告。

## 分类

下面只使用变异源码、`compile` 结果和测试进程的退出码。不使用「看起来像等价」「测试不好写」或运行后的人工判断。

| 类 | 判定 | 是否进入有效变异 |
|---|---|---|
| 生成 | `create_mutations` 返回的每一项，按返回顺序编号 `m0001` 起 | 先生成，再分类 |
| I1 无效 | 应用后的源码 `compile(..., "exec")` 抛出 `SyntaxError` 或 `IndentationError` | 否 |
| I2 无效 | 应用后的源码与 `history.py` 原文逐字相同（算子没有产生差异） | 否 |
| I3 无效 | `deep_replace` 或取 `.code` 时抛异常，没有可运行源码 | 否 |
| 等价 | 仅当差异匹配 `EQUIVALENT_PATTERNS`。该闭集是 `none`，因此等价数必须为 0，没有任何变异被标成等价 | 不发生 |
| 杀死 | 测试进程在超时前结束，且退出码不是 0 | 是，计入分子 |
| 存活 | 测试进程退出码是 0 | 是，只计入分母 |
| 超时 | 测试进程墙钟时间超过 `TIMEOUT_SECONDS`（10 秒）仍未结束，进程被终止 | 是，只计入分母 |

有效变异数 = 杀死 + 存活 + 超时。

杀死率 = 杀死 / 有效变异数。与门槛比较时用整数关系 `killed * 20 >= valid * 19`（即不小于 0.95），不用四舍五入后的小数。有效变异数为 0 时杀死率为空，判定为未达到门槛。

超时不是杀死。退出码不是 0 的结束（含测试失败、测试错误、导入失败、信号死亡）算杀死。门槛要求有效变异至少 20。

等价闭集为空是故意的：运行前不预留「事后可以改口」的模式。若有变异在加强测试之后仍然存活，它继续留在分母里；不得回头把它改记为等价。

## 测试进程

每次变异把候选源码写入 `history.py`，执行：

```text
python -m unittest discover -s control/loop_status/tests -q
```

解释器是运行器自己的 `sys.executable`。工作目录是仓库根。`PYTHONDONTWRITEBYTECODE=1`。超时 10 秒。进程结束后把 `history.py` 写回冻结字节，并再次核对 SHA256。

第一次测量（`--run-id run1`）的测试文件必须是 `RUN1_TESTS_SHA256`。若杀死率低于 0.95，允许只增加或加强 `control/loop_status/tests` 里的断言后再跑 `run2` 及以后。加强测试时：

- 不修改 `history.py`
- 不把断言改成恒真、不与自身比较、不短路成永远通过
- 不读真实账本、真实消息或仓库外的私有数据；输入保持测试里已有的虚构字节
- 新期望值对准本文件冻结的 `history.py` 契约（退出码、`result` 名、`reason`、规范 JSON 字节），不用存活变异的行为去改期望值

两次运行都要留下原始报告。不得用第二次覆盖第一次。

## 运行器退出码

| 退出码 | 含义 |
|---|---|
| 0 | 报告已写完，且 `history.py` 已恢复为冻结字节。不表示杀死率达标 |
| 1 | 没有完成测量（版本或哈希不符、基线测试不是 0、源码没有恢复、内部不变量失败） |

## 本文件不声称已经测过的事

GitHub Actions 不跑这次变异。`control/gate`、`capabilities/`、完整 C6、独立复核重跑，都不在本文件的测量里。那些项在 PR 里标 `NOT_TESTED`。

# run2 存活变异的审阅说明

本文件是给复核的分析，不是对 [equivalent-mutant-definition.md](equivalent-mutant-definition.md) 的修订。该定义在 `f43419ec5426fa9cb2150f6f7ed061d718666de5` 把等价模式闭集冻成 `none`，此后没有改过。`runs/run1` 与 `runs/run2` 的 `report.json` 不改。run3 的报告仍然只按冻结口径分类：这些变异若测试杀不死，就继续记为存活并留在分母里，不记为等价。

下面说的公开接口是本模块无下划线前缀的函数：`assess` 的 `(exit_code, canonical JSON bytes)`，以及 `timestamp`、`load`、`canonical`、`unique` 的返回值、异常类型、`str(异常)` 和调用方能读到的异常属性（含 `__context__`）。`assess` 自己只把 `str(error)` 写进 JSON，内部上下文不会出现在那两字节结果里；`timestamp` 把 `InputError` 交回调用方，上下文还在异常对象上。

## m0061 与 m0064：裁定为非等价，由测试杀死

协调者裁定这两条非等价。见证输入是语法上合法的 `2026-11-02T09:00+24:00`（m0061 另加 `+25:00`）。

- m0061 把 `int(offset[1:3])` 改成 `int(offset[2:3])`。`+24:00` 的两位小时是 24，大于 23；第二位是 4，不大于 23。原实现在 `datetime.fromisoformat` 之前抛出 `ValueError("offset")`。变异体放过这道检查，改由 `fromisoformat` 抛出另一条 `ValueError`（时差超出 ±24 小时）。`timestamp` 仍包成同一句 `invalid calendar time or offset`，但 `__context__.args` 不再是 `("offset",)`。`+25:00` 同样：切片后的个位不大于 23。
- m0064 把 `> 23` 改成 `> 24`。`+24:00` 不再被这道比较拦住，同样落到 `fromisoformat` 的另一条 `ValueError`。`+25:00` 仍大于 24，所以这条变异在 `+25:00` 上与原文一样。

[test_history.py](../tests/test_history.py) 的 `test_hour_above_23_is_rejected_by_the_explicit_guard` 断言 `__context__` 是 `ValueError` 且 `args == ("offset",)`。

## m0069、m0070、m0071：论证时发现可以杀死，改为测试

这三条都只改 `raise ValueError("offset")` 的参数，分别是 `ValueError(None)`、`ValueError("XXoffsetXX")`、`ValueError("OFFSET")`。`except ValueError` 不读这条文案，`assess` 的 JSON 因此不变。

调用 `timestamp("+24:00")` 时，原文的 `__context__.args` 是 `("offset",)`。这三条把它改成 `(None,)`、`("XXoffsetXX",)`、`("OFFSET",)`。这是 `timestamp` 交回的异常对象上的差别，与 m0061/m0064 同一断言就能杀死。因此不把它们写成等价。同一测试覆盖它们。

## m0037：`ensure_ascii=None`

精确差异，在 `canonical`：

```text
json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
json.dumps(value, ensure_ascii=None, sort_keys=True, separators=(",", ":"))
```

CPython 3.12 的 `json.encoder.JSONEncoder` 只在布尔上下文使用该参数（`if self.ensure_ascii`），文档写的是 “if ensure_ascii is true” / “if false”。`None` 与 `False` 都为假，两条分支都走到 `encode_basestring`，不会走到 `encode_basestring_ascii`。因此对任意可序列化对象，dumps 的字符串相同；随后的 `"\n"` 与 `.encode()` 相同。对不可序列化对象，两边抛出的 `TypeError` 文案相同。`canonical` 的返回字节，以及 `assess` 写进 JSON 的那些字节，都没有差别。没有找到能让这条变异在公开接口上露出的输入。

run3 若仍把它记为存活，分母保留它。本段只供复核接受或否定。

## m0095：`decode("UTF-8")`

精确差异，在 `load`：

```text
raw.decode("utf-8")
raw.decode("UTF-8")
```

编解码器查找不区分大小写，`UTF-8` 与 `utf-8` 解析到同一个 codec。成功解码的字符串相同。非法字节序列抛出的 `UnicodeDecodeError` 也相同：`.encoding` 被规范成 `utf-8`，`str(异常)` 与 `.args` 相同（已对 `b"\xff"` 与截断的 `b"\xc3\x28"` 核对）。`load` 捕获该异常后抛出的 `InputError("invalid JSON bytes")` 相同，其 `__context__` 也相同。`assess` 的退出码与 JSON 因此相同。没有找到公开接口上的差别。

run3 若仍把它记为存活，分母保留它。本段只供复核接受或否定。

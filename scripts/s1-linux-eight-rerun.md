# S1 Linux 八步复跑工具

一次性 Linux VM 上的固定 Python 入口。编排留在 Mac mini。本文件只说明怎么调用 [s1-linux-eight-rerun.py](s1-linux-eight-rerun.py)。不部署、不购买、不改任务或阶段，不含 SSH key。24 小时上限、收到回执后撤 key 并销毁 VM **没有实现**，回执里这两项固定是 `NOT_IMPLEMENTED`。

这不是 [rerun_receipt](../capabilities/rerun_receipt/README.md) 的 v1。v1 要求执行前读到的 git HEAD 等于清单里的 `head_sha`，并接受操作员给出的 argv。本工具没有 git HEAD 绑定，argv 只有下面这张固定表，schema 是 `s1-linux-eight-rerun/v0`。不要把回执改记成 `rerun-receipt/v1`。

只读打开方式对齐 [evidence_package](../capabilities/evidence_package/README.md) 与 [review_readonly](../capabilities/review_readonly/README.md)：目录描述符、`O_NOFOLLOW`、只收普通文件。源 ZIP 只读。需要落盘时使用输出目录里的读写 scratch，用完删除，不把 scratch 说成只读。`subprocess` 不是沙箱，不限制网络或文件访问。SSH forced-command、禁转发和系统隔离由部署层负责，本工具没有这些能力。

不要在宿主生产机上对未知包执行。`--dedicated-vm` 只表示操作员确认这是受控专用机，工具不会探测主机身份。

## 冻结身份

命令行只接受这一份 ZIP。没有替换摘要的参数。

| 项 | 值 |
|---|---|
| sha256 | `551123d9dd8eb8f3e05f0dc2ad8c69207c95db2a19cf524f50988691055538f1` |
| 字节 | 42705 |
| 普通文件 | 18 |
| 展开字节 | 95203 |

成员全长 SHA 不在工具里。inspect 可以列出归档相对路径、字节数和全长 SHA，供操作员自己写入 binding。摘要对不上、成员数或展开字节对不上、或扫描不安全，都不会执行。

扫描拒绝绝对路径、`..`、反斜线、冒号、控制字符、重复路径、符号链接、FIFO/设备/套接字、加密成员及声明大小不符。上限为 ZIP 1MiB、条目 64、单成员 256KiB、展开合计 1MiB。单成员达到 64KiB 且压缩比超过 80 也拒绝。平铺和嵌套布局均须逐件绑定普通文件的完整归档相对路径和全长 SHA。缺项、多项、摘要不符均拒绝执行。

## 固定八步

只跑这些参数。不接受 shell、额外 argv 或外部路径。

| 步骤 | argv | 地图期望退出 | stdin |
|---|---|---|---|
| T1 | `python3 -m unittest test_status_tool -v` | 0 | 无 |
| T2 | `python3 status_tool.py --file status_input.json` | 0 | 无，读 scratch 里已核验的 `status_input.json` |
| T3 | `python3 status_tool.py` | 0 | 同一份 `status_input.json` 的字节 |
| T4 | `python3 status_tool.py` | 0 | 操作员夹具，恰好 2 字节 |
| T5 | `python3 status_tool.py` | 2 | 操作员夹具，恰好 8 字节 |
| T6 | `python3 status_tool.py` | 2 | 操作员夹具，恰好 19 字节 |
| TP | `python3 -m unittest test_preflight -v` | 0 | 无 |
| PREFLIGHT-LOCAL | `python3 preflight.py` | 0 | 无 |

T3 只比较自己的 stdout SHA 是否与 T2 相同，不内置期望正文。stdout/stderr 期望全长 SHA 未提供，回执字段 `content_expectation` 固定 `NOT_PROVIDED`，工具不生成期望、也不把缺省当成通过。

PREFLIGHT-LOCAL 的地图期望是 0，历史另见 3。回执同时写下 `map_expected_exit`、`actual_vs_map` 和 `historical_conflict=UNRESOLVED`。退出 0 或 3 都不把这一步收成通过，`normalized_to_pass` 固定 false。技术执行状态和 `s1_judgment` 分开。`s1_judgment` 固定 `NOT_TESTED`。

子进程环境只有 `PATH=/usr/bin:/bin`、`PYTHONDONTWRITEBYTECODE=1`、`PYTHONNOUSERSITE=1`、`PYTHONUNBUFFERED=1`、`LC_ALL`/`LANG=C.UTF-8`，以及指向 scratch 的 `TMPDIR`。不继承调用方环境。每步超时 30 秒，单路输出上限 1MiB。超时或超限会停掉后续步骤。这些限制不是沙箱。

## 调用

默认是 inspect，不执行。

```bash
python3 scripts/s1-linux-eight-rerun.py \
  --zip /controlled/readonly/frozen.zip \
  --output-dir /controlled/receipts
```

显式执行还要 binding、夹具目录，以及 `--dedicated-vm`。

```bash
python3 scripts/s1-linux-eight-rerun.py \
  --execute --dedicated-vm \
  --zip /controlled/readonly/frozen.zip \
  --binding /controlled/binding.json \
  --fixture-dir /controlled/stdin-fixtures \
  --output-dir /controlled/receipts
```

`/controlled/...` 是示意路径。输出目录必须已经存在，输出路径的每一级均不能是符号链接，也不能落在 ZIP 实际所在目录或其子目录。工具通过已打开的目录写 `receipt.json`，在建临时 scratch 前会重新核对输出目录。运行期间输出目录及其父目录应由操作员控制。回执先落到一个新建文件，再替换 `receipt.json` 这个名字，因此不会截断已经硬链接到该名字上的源文件，也不会顺着符号链接写过去。标准输出与 `receipt.json` 是同一份 JSON，不含文件正文、stdin 字节或本机绝对路径。

一步的 stdin 写入和进程等待共用同一个超时。子进程不读满 stdin 时，写入不会把这一步拖过时限。

binding 的 schema 是 `s1-linux-eight-binding/v0`。平铺布局继续使用 `schema_version`、`steps`、`members`、`stdin_fixtures`。`steps` 必须正好是上表八个 id。`members` 将每个普通文件的完整归档相对路径绑定到全长小写 SHA256。`stdin_fixtures` 只有 T4、T5、T6，每项只有 `bytes`、`sha256`、`name`。`bytes` 必须分别是 2、8、19，`name` 是受控夹具目录里的单层文件名。未知字段和重复 JSON 键都会拒绝。

嵌套布局还必须提供 `entry_members`。它恰好包含 `README.md`、`preflight.py`、`sample_fixed.json`、`status_input.json`、`status_tool.py`、`test_preflight.py`、`test_status_tool.py` 七个固定 scratch 文件名。每个值须指向一个不同的、已经在 `members` 里绑定的完整归档路径。由操作员根据冻结地图或受控清单确认用途。同名文件须用完整路径指明，工具不推断入口。执行时只向 scratch 放入这七个映射后的文件。其他普通文件仍核验哈希，目录项不落盘。回执 `binding_sha256` 记录实际读取的 binding 原字节摘要，供复核选用的映射和夹具版本。

退出码 0 只表示 inspect 认对了冻结 ZIP，或八步都在时限和输出上限内跑完。它不是 S1 通过。退出码 1 是身份不符、不安全归档、摘要不符、夹具字节不符、超时、输出超限或源文件变化。退出码 2 是用法、binding 契约、缺 `--dedicated-vm`，或输出目录不安全。

## 真跑之前还缺的本机字段

本仓库和本工具都没有这些材料。缺任何一项，执行会拒绝或保持 `NOT_TESTED`，不会补默认值：

- 冻结 ZIP 文件本身。全长 SHA 必须等于上表，工具不附带该文件。
- inspect 测到的每个普通文件成员的全长 SHA256。工具不内置成员摘要。
- T4、T5、T6 的受控 stdin 原始文件，长度分别为 2、8、19 字节，并有明确的步骤归属和全长 SHA256。
- 操作员自己写成的 binding。错误摘要不会被忽略。
- 期望 stdout/stderr 全长哈希仍然没有。工具只记录实测字节数和实测 SHA，不把它写成内容通过。

历史口述里的「7 tests OK」「3 tests OK」不是本工具的内容期望。PREFLIGHT-LOCAL 的 0 与 3 继续并列保留。

## 测试与回滚

合成夹具在 [tests/test_s1_linux_eight_rerun.py](tests/test_s1_linux_eight_rerun.py)，不使用冻结 ZIP，也不使用私有原件。

```bash
python3 -m unittest discover -s scripts/tests -v
```

`capability-tests` 只跑 `capabilities/*/tests`，本目录不在其中。本 PR 不改 `.github/workflows/ci.yml`。

回滚：删掉 `scripts/s1-linux-eight-rerun.py`、`scripts/s1-linux-eight-rerun.md` 和 `scripts/tests/test_s1_linux_eight_rerun.py`。不回滚其他目录，不改 v1 契约。

# 证据包读取与校验 · v1

Issue #1 的最小原子能力：只读取操作员选定包根目录中的 manifest.json，逐文件核算 SHA256。PASS 仅表示清单字节通过，不认证来源、命令是否执行或 Bot 信任阶段。

## 冻结契约

输入是一个由可信操作员选定的现有目录；根本身不能是符号链接，根的祖先目录由操作员信任。manifest.json 顶层只能有 schema_version="evidence-package/v1" 与 artifacts；artifacts 是1至1024项的非空数组，每项仅包含 path、sha256。文件路径为规范POSIX相对路径，禁止绝对路径、空分段、点/父目录、反斜线、冒号、NUL、自引用清单、重复路径；SHA为64位小写十六进制。未知字段和重复JSON键拒绝。

读取清单和每个文件均通过目录描述符、O_NOFOLLOW逐段打开，仅接受普通文件。FIFO/设备/目录、最终文件或中间目录的符号链接拒绝。清单上限1MiB；每文件上限64MiB；总读取上限256MiB。相同摘要的空文件是合法字节证据，但空清单拒绝。

输出为单个JSON：verdict、scope=artifact-bytes-only及实际核对的path/bytes/sha256；失败给出reason。exit 0=所有文件字节匹配；1=缺失/不安全/不可读文件、字节预算或摘要不符；2=清单语法、编码或契约错误。使用方式错误遵循argparse退出2。

```bash
python3 capabilities/evidence_package/verify.py capabilities/evidence_package/example
python3 -m unittest discover -s capabilities/evidence_package/tests -v
```

只读，不执行文件、清单或日志中的命令，不联网，不修改证据/信用账本。包根是显式授权输入，不允许把不受信提交中的路径直接当作授权；本工具没有提供OS沙箱、H1/H2、持久快照或并发写隔离。检查期间应保持包静止；PASS只证明本次读到的字节。依然需要可信来源、独立验收、头提交绑定和实际平台读回。

## 地图与回滚

功能地图见 [feature-map.json](feature-map.json)，覆盖契约解析、描述符边界、真实摘要核验、资源预算、只读与CLI。

本次无生产写入；回滚为撤回本PR新增能力及CI job，保留原始失败和回执。不得回滚其他Agent工作区。版本1的契约先冻结在本PR，改变格式/门槛应另开版本和独立PR。

## 当前验收状态

本地执行者复跑已完成；能力PR不修改自己的CI工作流，回归作业接入由单独控制面PR审阅。PR Checks必须区分基础契约检查与能力回归；旧提交的双作业绿灯不能继承给当前候选。独立主体复跑待完成（NOT_TESTED），不能自签验收、关闭A级闭环或计业务连胜。Linux CI与macOS本地均执行同一CLI；Windows不支持当前描述符实现。

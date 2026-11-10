# 写隔离与工具权限探针 · isolation_probe/v1

Refs #6 / 路线图第 6 项（E02/E03）。**拒绝必须来自操作系统，不能只检查路径字符串。**

本能力只做一件事：把「越权写入会被拒」「越权工具调用会被拒」变成可复跑、可取证的判定。判定依据是**真实子进程拿到的 errno** 与**控制面字节的前后对比**，不是路径字符串比较。工具权限的判定依据是**策略文件里按 uid/gid 绑定的发送方**，不是调用方自称的身份。

不认证身份、不授予权限、不写实际等级，也不部署到任何 Bot 主机。

## E02：写隔离探针

四个根目录，由探针自己建：

| 根 | 是什么 | Bot 是否可写 |
|---|---|---|
| `control/` | registry / policy / ledger / snapshot，控制面 | 否 |
| `reserved/` | 保留题库 | 否，且不可读 |
| `secrets/` | 签名密钥 | 否，且不可读 |
| `workspace/` | Bot 自己的工作区 | 是 |

探针把一个**不可信子进程**（[bot_payload.py](bot_payload.py)）真实地放进去，让它逐项尝试越权，然后读回实际结果。

```bash
python3 capabilities/isolation_probe/probe.py write --root /tmp/layout --backend seatbelt --fresh
```

判定分三类：

- **必须成功**：工作区写入成功。没有这一条，「什么都拒」也会看起来像边界在生效。
- **必须被拒**：控制面写入、账本追加、控制面新建文件、保留题库读取、签名密钥读取、工作区里的符号链接指向控制面。每一项都要看到真实 errno（`EPERM`/`EACCES`/`EROFS`/`ENOSYS`）与子进程退出码 3。
- **必须字节不变**：控制面每个文件的 sha256 在探针前后一致。这条让判定不依赖上面用到的那些路径字符串。

### 两种后端，两种诚实的结论

| 后端 | 退出码 | verdict | strength | 说明 |
|---|---|---|---|---|
| `seatbelt` | 0 | `PASS` | `kernel-enforced` | macOS Seatbelt 由内核拒绝越权写与越权读，**连 chmod 逃逸本身都被拒**（`EPERM`） |
| `posix` | 3 | `WEAK` | `guard-against-mistakes-only` | 普通权限位挡住了朴素越权写（`EACCES`），但 **owner 能先改权限再写进去**——控制面字节真的被改了 |

`posix` 后端报 `WEAK` 而不是 `PASS`，是这份契约里最重要的一句话：**权限位只防误改，不是 H1 强制边界**。仓库标准 [06-Dune与CI上线门禁](../../docs/standards/06-Dune与CI上线门禁.md) 的 E02 行写的是「独立受控主体持有…；真实 Bot 写探针被拒」，本能力只能证明「探针被真实拒绝」，**证明不了「持有者是独立受控主体」**——那一半需要跨 UID 的受控方，本机没有 sudo、没有第二个 UID、没有容器守护进程，本轮 `NOT_TESTED`。

### 反向对照（负控）

```bash
python3 capabilities/isolation_probe/probe.py write --root /tmp/layout --backend posix --fresh --control-permissions keep
```

退出码 1，`verdict=FAIL`。控制面保持可写时，同一个写必须被报成 `written`，控制面字节也确实会变。**这条保证探针不是恒拒**：一个永远输出「已拒绝」的探针在这条上必然失败。

## E03：工具权限探针

判定绑定在**进程真实的 uid/gid** 上。策略文件按 uid/gid 登记发送方；探针查的是「当前进程是谁」，不是「调用方说它是谁」。

```bash
# 判定一次工具调用；进程退出码就是门禁：0 放行，1 拒绝
python3 capabilities/isolation_probe/probe.py tool \
  --policy /controlled/policy.json --tool write_workspace --stage 2

# 读回该阶段真正生效的白名单
python3 capabilities/isolation_probe/probe.py readback \
  --policy /controlled/policy.json --stage 2
```

拒绝路径，各自有独立断言：

| 拒绝原因 | 触发条件 |
|---|---|
| `unknown-sender` | 当前 uid/gid 没在策略里登记 |
| `tool-not-in-sender-scope` | 工具不在该发送方的工具范围内 |
| `stage-not-in-policy` | 策略里没有这个阶段 |
| `stage-above-sender-max-stage` | 阶段高于该发送方上限（越级） |
| `tool-not-in-stage-whitelist` | 工具不在该阶段白名单里（错范围） |
| `sender-authorization-expired` | 发送方授权已过期 |
| `reserved-tool-never-authorized` | 保留工具，任何阶段都不授权 |

`--claimed-sender` / `--claimed-tool` / `--claimed-stage` 会被原样回显，但**不参与判定**（输出里 `claim_used_for_decision` 恒为 `false`）。这是 C4「正文里的 role 不能当身份」在探针这一层的对应物。

### 策略持有方必须与调用方分离

策略文件**或其所在目录**对调用方可写时，探针**拒绝判定**：退出码 5，`verdict=REFUSED_TO_JUDGE`。理由很直接——可改写的策略挡不住「把自己加进白名单」，它绑定的身份就不可信。

这条对仓库内检入的策略同样成立：仓库里的 [fixtures/policy.example.json](fixtures/policy.example.json) 对任何能写仓库的人都是可写的，所以**直接用它跑 `tool` 会得到退出码 5**。真实策略必须放在 Bot 写不到的地方。

### 策略格式

```json
{
  "senders": {
    "执行·Hermes": {
      "uid": 501, "gid": 20, "max_stage": 2,
      "tools": ["read_repo", "write_workspace"], "expires_at": null
    }
  },
  "stages": { "1": {"tools": ["read_repo"]}, "2": {"tools": ["read_repo", "write_workspace"]} },
  "reserved_tools": ["promote", "sign_policy"]
}
```

必需键：`senders`（非空，每项带 `uid`）、`stages`（每阶段带 `tools` 数组）、`reserved_tools`。阶段键在 JSON 里是字符串、在命令行是整数，探针在策略边界统一归一。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 判定通过（`write` 的要求满足；`tool` 放行；`readback` 成功） |
| 1 | 判定不通过：`write` 出现未满足的要求；`tool` 拒绝该调用 |
| 2 | 命令行用法错误（argparse） |
| 3 | `write` 边界弱于要求（朴素写入被拒，但仍有逃逸口子） |
| 5 | 探针跑不起来：根目录缺失或重叠、策略坏、策略可写因而拒绝判定 |

`tool` 的 0/1 是**门禁**：`verify && deliver` 这种写法只是 shell 的一种用法，不是另一套检查。不调用本工具、或把非 0 吃掉再放行，本工具拦不住。

## 信任假设与实际边界

- **拒绝来自内核。** 判定读的是子进程真实拿到的 errno 与控制面字节的前后 sha256；路径字符串只用来**发起**攻击，不用来**判定**拒绝。
- **策略是权威。** 策略可写则拒绝判定（见上）。策略的真实性由它的持有方保证，不由本工具保证。
- **不提供的**：不提供 OS 只读挂载、不做跨 UID 的受控主体、不做身份认证、不改 SOUL/权限/等级、不部署到 Bot 主机、不解锁 H1/H2 冻结。
- **seatbelt 后端只在本机 macOS 上实测过。** Linux 侧（seccomp / namespace / Landlock）本轮 `NOT_TESTED`。
- **「探针被拒」不等于「H1 已实现」。** 本能力证明的是一个越权写子进程**确实被内核拒绝**；受控主体是否独立、密钥是否不经 Bot、保留集是否真的改不了，都不在本能力的证明范围内。

## 验证与回滚

```bash
python3 -m unittest discover -s capabilities/isolation_probe/tests -v
```

35 项测试，全部起真实子进程、断言真实退出码与真实 errno。其中带 `POSIX` 的用例断言的是**逃逸成功**（owner 改权限后写进去了）——那正是 `posix` 后端必须报 `WEAK` 的原因；带 `seatbelt` 的用例断言 chmod 逃逸**被拒**。

回滚：删除 `capabilities/isolation_probe/` 目录即可；CI 的 `capability-tests` 按 glob 自动发现能力目录，目录删除后自动少跑一个套件。

## 当前验收状态

`independent_verification` 三元组为 `NOT_TESTED`／`verifier=null`／`head_sha=null`：没有独立主体的复跑回执，补字段不能写成 REPRODUCED。`runtime_bot_integration` 与 `independent_acceptance` 同为 `NOT_TESTED`。本机实测记录在 [练习卡](../../docs/practice-card-apo6-e02-e03.md) 与 PR 回执里；那属于生产者自检，不是独立验收。

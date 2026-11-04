# 收件人检查如何装到 Bot 主机

本文只说明仓库里这份工具是什么、历史上打算怎么放到 Bot 旁边。它不是安装器，不会连接任何主机，也不授予运行许可。真正拷贝、改 SOUL、换已部署副本，都要主人另一次点名批准。本文件不执行这些动作。

## 是哪一个 check.py

Bot 开工前按 `check.py --self <bot>` 调用的，是本目录的 [check.py](check.py)：

```bash
python3 check.py --self <我的身份> --aliases <别名表.json> <交接单文件>
```

仓库里另外两个同名文件不是这个入口：

- `capabilities/review_readonly/check.py` 用的是 `snapshot` / `verify`，没有 `--self`。
- `capabilities/handoff_conventions/check.py` 检查未定义约定，也没有 `--self`。

契约、退出码和别名规则以 [README.md](README.md) 为准。别名样例是 [fixtures/aliases.json](fixtures/aliases.json)，只含显示名，不是平台身份注册表。生产别名表应放在主机上单独保管，不要把夹具当成生产配置热替换。

## 历史部署是怎么做的

训练记录 [2026-11-02](../../docs/reviews/2026-11-02-lightvela-training.md) 写的是：主人书面批准后，把当时的 `check.py` 原样拷进 Bot 运行环境，由 Bot 按 SOUL 第 13 条在开工前自己调用。记录里的副本是 PR #11 head `6da4715`（v1），sha256 在该文里被截成 `ef4eb934…`，全文摘要不在本仓库。强制力仍是 text_only：工具目录当时对 Bot 可写（H1 未解决），所以每轮还要核对文件指纹。

当前树是 v1.3，不是那份已部署的 v1。本修订不热更新任何 Bot。

## 批准之后的人工步骤

只在主人点名批准某一版 head 之后，由被点名的人在 Bot 主机上做。下面是步骤说明，不是本仓库会去跑的脚本。

1. 在仓库里对批准的 head 计算 `capabilities/handoff_recipient/check.py` 的 sha256，记到审查记录。别名表用主机上那份，不用把 `fixtures/` 整目录当成身份源。
2. 把 `check.py` 拷到 Bot 已经在用的工具目录，覆盖前先留下旧文件的字节和 sha256，以便回滚。拷贝之后把该路径设成 Bot 不可写；在 H1 做到之前，只能称为 text_only，并在每轮训练核对指纹。
3. 在主机上用已知红样本自检，而不是用 Bot 的自述。仓库内对应命令是：

```bash
python3 capabilities/handoff_recipient/check.py --self "Apo·内容" \
  --aliases capabilities/handoff_recipient/fixtures/aliases.json \
  capabilities/handoff_recipient/fixtures/r2-card-a.txt
```

预期退出码 4（MISADDRESSED）。这条命令只读夹具，不部署、不改等级。

4. SOUL 条文（开工前调用、非 0 不开工）是配置变更，与拷贝文件分开批准。本文不修改 SOUL。
5. 回滚：把第 2 步留下的旧字节写回去，再核对 sha256。不要用「删掉检查」充当回滚。

CI 绿、单测通过、或这份说明存在，都不表示已经部署，也不计业务连胜。

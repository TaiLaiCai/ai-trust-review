# 审查只读交付检查 · review_readonly/v1

Refs #37，C-R5-2 的最小可执行约束：审查前后对**显式列出的原件**比较字节数与 SHA256；变化或丢失时阻断使用本检查的交付命令。虚构夹具，不包含真实训练题或判据。

## 契约与调用

1. **受控训练者**选择根目录和完整被审文件集，在审查开始前运行 snapshot；把原始 JSON 保存到工作 Bot 不可写的控制目录，同时独立保存其原字节 SHA256。
2. 被审 Bot 完成审查，只输出新的 review 文件，不能改原件。输出 review 文件须放到被审集之外；不能把 baseline 输出重定向到任何被审原件。
3. **受控训练者**在交付前执行 verify，提供原先保存的 baseline SHA256。仅退出0且 JSON delivery_allowed=true 才交付；任何非0均停下报告，不重建基线、不修原件、不恢复成原样后重试来消除失败。

```bash
python3 capabilities/review_readonly/check.py snapshot \
  --root /trusted/review-input --file document.txt --file nested/data.json \
  > /trusted/control/before.json
# 将 before.json 的 SHA256 独立存于受控处，不从本轮待审输入重新计算信任值。
python3 capabilities/review_readonly/check.py verify \
  --root /trusted/review-input --baseline /trusted/control/before.json \
  --baseline-sha256 '<受控处保管的64位摘要>'
# 由调用方检查退出码；例如 verify ... && delivery_command。
```

`/trusted/...` 是示意路径，本工具不创建或管理这些隔离目录。只使用标准库，支持 macOS/Linux；不支持当前描述符 API 之外的平台。

snapshot 输出固定 schema_version、绝对 root、files（规范POSIX相对路径→bytes/sha256）的 JSON。verify 验证基线原字节摘要、严格格式和同一 root 后，只读取基线登记的文件。输出排序、UTF-8、LF；不执行任何文件或卡片正文，不联网、不修改原件或基线。

| 退出码 | 含义 | 允许交付 |
|---|---|---|
| 0 | snapshot成功，或verify为UNCHANGED | 仅verify的delivery_allowed=true允许 |
| 1 | verify发现内容不同、文件/中间目录缺失、原件改名 | 否 |
| 5 | 基线篡改/坏摘要/坏JSON/路径、符号链接、特殊或不可读文件、超限 | 否 |
| 2 | CLI使用错误 | 否 |

每次 snapshot 必须显式列出1至1024个路径，拒绝空集、重复路径、绝对/点/父路径、空段、反斜线、冒号和NUL。摘要64位小写hex，字节数严格非负整数，拒绝未知字段/JSON重复键。单文件64MiB、合计256MiB、基线1MiB。空普通文件合法。

根目录最后一段、中间目录和文件均用 O_NOFOLLOW + 目录描述符打开；只读普通文件，FIFO用NONBLOCK打开后拒绝，避免挂住。根的祖先目录与基线父目录由调用方信任；路径本身不是授权来源。读取时检测文件大小/时间戳变化；输入须保持静止。

## 实际边界

- 这是前后两次字节观察。修改后恢复相同字节、只改元数据、未列出的文件，以及检查之后再写，均不由本工具证明不存在。测试明确保留“改后恢复仍UNCHANGED”，不能伪称全程无写入。
- 不提供OS只读挂载、H1/H2、身份认证、锁或交付平台钩子。基线与摘要若都由工作 Bot 重写，可伪造；必须由独立受控调用方保管，并强制检查退出码。
- snapshot失败可能使shell重定向留下错误JSON；受控方必须核对snapshot退出码，不能把错误输出登记成基线。
- 不解析自然语言的“就地修正”请求；卡内只读/修复冲突仍应由审查者停下回问。
- 本PR不部署到Bot、不改SOUL/权限/等级、不关闭纠正单。真实Bot接入与独立验收、换包装复测仍NOT_TESTED；CI通过不计业务连胜。

## 验证与回滚

```bash
python3 -m unittest discover -s capabilities/review_readonly/tests -v
```

测试含同长度改写、追加、删除/改名、基线替换、根替换、路径与符号链接、FIFO、坏JSON/预算、惰性正文和真实shell的 `verify && delivery` 红绿执行。既有 capability-tests 自动发现本目录，无需改工作流；远端实际结果见PR回执。

地图见 feature-map.json。撤回本PR新增目录即可回滚候选；不覆盖旧失败、原件或其他Agent文件。独立复核与正式接入须另行完成。

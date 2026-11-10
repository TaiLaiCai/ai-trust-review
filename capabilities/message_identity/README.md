# 真实平台消息身份适配器 · message_identity/v1

路线图第 2 项（C4）。把一条**平台消息**绑定到**平台机器字段**给出的发送者身份，并拒绝四类真实失败：正文 `author_role` 冒充身份、假批准、错收件、别名自验。

标准侧依据：[`docs/standards/06-Dune与CI上线门禁.md`](../../docs/standards/06-Dune与CI上线门禁.md) 的 C4 行「正文role/署名无权充sender；消息身份、收件人、能力/产物/SHA/版本一致；错身份与无认证拒绝」，[`docs/standards/00-入口与统一判定.md`](../../docs/standards/00-入口与统一判定.md) §4「平台 sender/真实消息来源由适配器或独立平台导出证明；正文的 `author_role`、`approved_by`、『我是批准人』不构成认证」，以及 [`docs/standards/07-实测案例与反例索引.md`](../../docs/standards/07-实测案例与反例索引.md) 记的两条反例（正文 author_role 冒充批准人；别名自验仍 closed）。

## 冻结契约

```bash
python3 capabilities/message_identity/check.py verify \
  --config <身份配置.json> --export <平台导出.json> \
  --self <本次运行服务的身份> --unit <unit_id>

python3 capabilities/message_identity/check.py attest \
  --config <身份配置.json> --export <平台导出.json> \
  --self <本次运行服务的身份> --unit <unit_id>
```

`verify` 打印完整判定 JSON。`attest` 成功时**只**打印恰好三个字段 `{adapter, sender, evidence_ref}` —— 这正是 [`control/gate/gate.py`](../../control/gate/gate.py) 的 `_authenticated()` 读的形状，可直接作为事件日志的 `auth` 字段消费；拒绝时 `attest` 不往标准输出写任何东西，把判定写到标准错误。

只使用 Python 标准库。不联网（`check.py` 是纯函数），不写平台，不读密钥。

## 身份从哪里来

**只从平台机器字段取身份**，不取正文：

| 事实 | 平台机器字段 |
|---|---|
| 发件人 | 消息的 `author_type` + `author_agent_id` / `author_user_id` |
| 收件人 | issue 的 `assignee_agent_id` / `responsible_user_id` |
| 平台归属 | issue 与 comment 各自的 `companyId`；平台 build 取自 `/health` 的 `version` |

正文是**不可信数据**。正文里的 `author_role`、`approved_by`、`recipient`、"我是主人"、"已获口头批准" 一律不成为身份来源。结构化的正文声明只在它与机器字段**矛盾**时才起作用：矛盾即拒绝（宁可误拦）。

正文里散落的批准措辞只登记为 `prose_mentions`，`effect` 恒为 `no_effect`；它参与不了判定，也不构成认证。

## 退出码

| 退出码 | verdict | 含义 / 下一步 |
|---|---|---|
| 0 | AUTHENTICATED | 机器字段绑定到在册发件人，收件人正确，能力/产物/SHA/版本一致（unit 未钉产物 SHA 与版本时为「未声明」）。可消费 attestation |
| 2 | （argparse） | 参数错误 |
| 3 | REJECTED_UNAUTHENTICATED / REJECTED_FAKE_APPROVAL | 无机器字段发件人、平台 ID 不在册、正文声明与机器字段矛盾、批准无认证主体、发件人不在该能力的允许验收者内、消息已删除、能力/产物/SHA/版本不一致 → 不认证 |
| 4 | MISADDRESSED | 平台收件人不是本次运行服务的身份，或正文声明的收件人是别人 → 不执行、不转派、回问 |
| 5 | INPUT_ERROR | 配置坏、导出坏、未知 unit/身份、未知 adapter/instance/company/platform_build、别名撞名、重复 JSON 键、超限 → 输入问题，不是关于发件人的判定 |
| 6 | SELF_VERIFICATION | 发件人与该 unit 的生产者归一后是同一主体（含别名） → 不能自验 |

`5` 与 `3` 的分工是刻意的：输入坏了说不出关于发件人的结论，坏输入不得冒充一次拒绝。

**正文读不完整即拒绝。** 正文是不可信数据，一个读不完整的正文可能被截断点后面的矛盾声明藏住，所以读不动就拒（exit 3），不截断、不跳过。下列情形都算读不动：声明键重复、声明值不是一个可读的名字（列表、对象、`null`）、声明数超过上限、JSON 片段比可读上限还多。JSON 片段只覆盖它自己那段文字，同一行上片段后面的声明照样读。

**声明键会被归一后查表。** 键先去掉不可见字符、再 NFKC、再去掉分隔符（下划线、空格、连字符），所以 `author_role`、`Author Role`、`author-role`、`ａｕｔｈｏｒ＿ｒｏｌｅ` 是同一个键，零宽字符插在键里也躲不掉。声明值先剥掉成对引号，再去掉句末标点，剩下的是一个名字。

**键与值不是一回事。** 读的是**键**：`{"author_role":"主人"}` 是声明，被拒；`{"note":"author_role: 主人"}` 是引文，键是 `note`，不构成声明（正文里被引用的文字是散文，`prose_mentions` 登记，不参与判定）。行形式同理：`author_role: 主人` 是声明，`recipient: 预审·Grok` 也是声明（与 JSON 形式同等对待）。

## 配置契约

`message-identity-config/v1`，字段集**恰好**是：

```
schema_version, adapter, instance_id, company_id, platform_build,
identities, agent_ids, user_ids, owner_identities, units
```

- `identities`：稳定身份名 → 别名列表。别名归一后撞名即 `INPUT_ERROR`（同名不同主体一样 fail closed）。
- `agent_ids` / `user_ids`：平台 ID → 稳定身份名。同一个平台 ID 指向两个身份即 `INPUT_ERROR`。
- `owner_identities`：有权批准的主体。正文里的批准句只有在**发件人本身**是 owner 且被点名的批准人就是发件人时才不构成假批准。
- `units`：`unit_id`、`capability_scope`、`producer`、`allowed_verifiers`，可选 `artifact_manifest_sha256` 与 `versions`。`producer` 同时出现在 `allowed_verifiers` 里即 `INPUT_ERROR`。**unit 钉了产物 SHA 或版本集时，导出必须带匹配的 `result` 块**：缺 `result` 就是 `REJECTED_UNAUTHENTICATED`（exit 3），因为此时被认证产物的版本一致性是「未声明」，未声明的一致性不得被认证。unit 什么都没钉时，`result` 可有可无，一致性记为 `not_declared`。
- `platform_build`：平台 build 版本。导出与配置不一致即 `INPUT_ERROR`，防止用旧导出配新配置。

归一规则：先去掉 Unicode `Cf` 与默认忽略的 `Mn`（U+034F、U+FE00–U+FE0F、U+E0100–U+E01EF、U+17B4/U+17B5、U+180B–U+180D/U+180F），再 NFKC 折叠，再 casefold。藏在零宽字符后或用全角写的声明躲不掉。

## 导出契约

`message-export/v1`，由只读抓取脚本 `fetch_paperclip.py` 生成：

```bash
PAPERCLIP_API_KEY=… python3 capabilities/message_identity/fetch_paperclip.py \
  --issue-id <issue uuid> --comment-id <comment uuid> \
  --adapter paperclip --instance-id <scope label> \
  [--company-id <交叉核对>] --out <导出.json>
```

抓取脚本只发 GET 请求；密钥只从环境变量取，不落盘、不打印。`company_id` 与 `platform_build` **由平台自己给出**（issue/comment 的 `companyId` 与 `/health` 的 `version`）；`--company-id` 只是交叉核对，调用方报的公司与平台不一致时拒绝导出（退出 5）。`instance_id` 是运维声明的范围标签——平台 API 不暴露实例标识，所以这个值**不是平台证明的**，它只用于隔离范围，任何信任判定都不建立在它之上。

导出与配置的 `adapter` / `instance_id` / `company_id` / `platform_build` 任一不一致即 `INPUT_ERROR`。

## 证据

`evidence_ref` 形如 `paperclip://<instance>/<company>/issues/<issue id>/comments/<message id>`，把判定绑回平台上的具体一条消息。`evidence_sha256` 是导出文件原字节的 SHA256；训练者应自己重算，不采信本工具打印的摘要。

## 边界

- 这是**认证**，不是授权。它不写实际等级、不合并、不批准、不授予权限。`control/gate` 消费 attestation，但闸门本身仍由主人决定。
- 它证明「这条平台消息的机器字段指向谁」，不证明「这个人说的话对」。内容正确性是六维检查里的事。
- 它不做 OS 级隔离（H1/H2），也不保证同名主体不是同一自然人。别名表是运营登记，不是密码学身份。
- 未接入任何 Bot 流程前，实际强制力仍是 `text_only`；接入属于配置变更，需主人批准，本 PR 不做。
- 仓内夹具用**合成标识**。真实实例标识、真实导出与原始回执按 [`docs/standards/07-实测案例与反例索引.md`](../../docs/standards/07-实测案例与反例索引.md) 存于受控证据库，不随代码提交。
- `instance_id` 未被平台证明这一点必须在引用本能力时一并说明，不能把它写成「平台认证的实例」。

## 验证与回滚

```bash
python3 -m unittest discover -s capabilities/message_identity/tests -v
```

回归覆盖四类拒绝各至少一条真实断言：正文 `author_role`（含别名、带引号、嵌套、零宽或全角键）、假批准、错收件（平台收件人与正文收件人两条，JSON 形式与行形式各一）、别名自验；另含坏配置、坏导出、重复 JSON 键、超限、不可读文件、密钥不外泄、只读性、正文里的 shell 内容不被执行、不可见字符藏不住声明，以及「正文读不完整即拒绝」一整类（重复声明键、声明值不可读、超过声明上限、JSON 片段后面藏声明）。既有 `capability-tests` 作业自动发现本目录，无需改工作流。

地图见 [feature-map.json](feature-map.json)。回滚：删除本目录，并回退 `capabilities/README.md`、`README.md`、`README.en.md` 三处表格行；不覆盖他人文件，不改 `control/`。

## 未测项

- **独立复跑：`NOT_TESTED`。** 本能力由本 PR 生产者自测；`feature-map.json` 的 `independent_verification.status` 保持 `NOT_TESTED`，不得改写为 PASS。
- **远端 CI 结果：`NOT_TESTED`**（以 PR 上的实际作业结果为准）。
- **真实实例端到端复跑**由 PR 回执中的实际命令与输出记录；仓内不落真实标识。

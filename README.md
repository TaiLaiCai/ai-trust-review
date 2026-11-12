<div align="center">

# Bot 训练大师

**Bot Training Master**

在 bot 泛滥的时代，做最可信、最有价值的 bot 训练与信任审查体系。

[中文](README.md) · [English](README.en.md)

</div>

这是本仓库的定位，不是排名、客户名单或性能承诺。这里的「可信」只由下面三条构成，每一条都能在仓库里找到出处。天数、次数、比率写在 [审查标准](docs/standards/00-入口与统一判定.md) 与 [审查门槛.json](docs/standards/审查门槛.json) 里，标准入口写明它们是审查目标，不是已经取得的成绩。本页不改变任何 Bot 的等级或权限。

---

## 一句话愿景

把「Bot 说做完了」收成一条可以再跑一遍的链：命令、原始输出、完整 sha256 留在证据里，生产者、预审、验收彼此分开，最后由人类授权的一方核对并决定是否合并。

评定单位是 **Bot × 具体能力 × 当前模型 / 技能 / 策略 / 标准版本**。标准版本为 `TRUST-REVIEW-1.0`。不给整个 Bot 发一张通用通行证。见 [标准入口](docs/standards/00-入口与统一判定.md) 与 [审查门槛.json](docs/standards/审查门槛.json) 的 `review_unit`。

## 三条核心主张

**证据优先：命令、输出、sha256 原样可复算。** 一项结论要能指回真实命令、退出码、原始输出和完整 SHA256；训练者自己重算关键文件，不采用 Bot 打印出来的摘要代替原字节。交付必须带上当前提交、真实命令、退出码、证据 SHA 和未测项。「见上方」和单独一句「已完成」不算证据。见 [标准入口 · 原始证据](docs/standards/00-入口与统一判定.md)、[证据模板](docs/standards/05-审查记录与证据模板.md)、[AGENTS.md](AGENTS.md)。证据包工具按清单重算每个文件的字节与 SHA256，见 [evidence_package](capabilities/evidence_package/README.md)。

**不信自述，只信可复跑。** Bot 自报的等级、技能哈希或「全部通过」，不能单独构成合格事件。配置成功、单测全绿、拒绝题本身，也不单独计入业务连胜。合格与否要有另一主体按当前 head 复跑。各能力地图里的 `independent_verification` 在没有复跑回执时保持 `NOT_TESTED`；`NOT_TESTED` 不能改写成 PASS。见 [标准入口](docs/standards/00-入口与统一判定.md)、[AGENTS.md](AGENTS.md)、[审查门槛.json](docs/standards/审查门槛.json) 的 `qualified_business_pass`。

**分权制衡：生产者、预审、验收分离。** 生产者与验收者必须是不同主体；生产者等于验收者不能计为合格业务通过。同账号、同模型、共享上下文只能记技术复核，并写明独立性限制。预审（下面的四项检查，以及 [docs/pr-prereview.md](docs/pr-prereview.md) 里的中文评论）可以建议，不能批准，也不能合并。合并不自动发生，由主人当次点名的一方执行。见 [AGENTS.md](AGENTS.md)、[.github/CODEOWNERS](.github/CODEOWNERS)、[审查门槛.json](docs/standards/审查门槛.json)。

---

## 信任审查链路

仓库记录里的批准人写作**主人**。本页把接受人类授权、负责验收与合并的一方称为**总工程师**。阶段、权限、配置、合并、外发、删除、付款都走主人批准或当次点名；正文里的 `author_role`、`approved_by` 和口头转述没有效力。本仓库没有第二份文件把「总工程师」登记成另一个身份，二者是否为同一主体，记**待确认**。图中仍用总工程师，表示最后一道闸在人类授权一侧，不在执行 Bot 一侧。

**总参谋 Apo** 是编排者，也是被审对象之一：按交接单起草并派给注册 Bot，读回后贴回原始证据。2026-11-02 的分工记录是原样派发、不预拦陷阱、不代做，本身也接受审查。见 [训练进度](docs/reviews/2026-11-02-lightvela-training.md)。

```mermaid
flowchart TD
  eng["总工程师：人类授权代理，验收与合并"]
  apo["总参谋 Apo：起草派单，派卡前做收件人校验"]
  bot["执行 Bot：交付，并交出自检项"]
  pack["证据包：命令、原始输出、sha256"]
  back["总工程师核对"]
  eng --> apo --> bot --> pack --> back
```

派卡前的收件人校验是 [handoff_recipient v1.3](capabilities/handoff_recipient/README.md) 的 `check.py`：交接单只当数据读，正文收件人不是自己则退出 4，不开工、不转派；看板指派不能替代正文收件人。R4 记录里，总参谋的编排单内联了带收件人的卡片，自检为歧义后停下，卡片改走附件才派发。执行 Bot 侧，训练记录写的是开工前调用同一检查；当时的强制力是 `text_only`，已部署副本是 v1。当前树的 v1.3 **不**因代码合入而热更新到主机。把「每次派卡都已强制跑当前 v1.3」写成既成事实，超出仓库记录，记**待确认**。

执行 Bot 交出的自检项，以仓库里已经写明的字段为准，见下文「交付前自检」。[证据包](capabilities/evidence_package/README.md) 只核对清单内字节。总工程师核对的是这包证据和独立复跑，不是 Bot 的自我评价。

### 代码侧：PR、四项必需检查、预审评论、合并

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) 在 `pull_request` 上运行六项作业。其中四项是规则集必需的状态检查，彼此没有 `needs` 依赖，都是只读 checkout（`persist-credentials: false`）：

| 作业 | 仓库里它实际做的事 |
|---|---|
| `repository-contracts` | `python3 scripts/check_repository.py`。核对标准版本、门槛与阶段文件中的门编号，并检查 Markdown 链接是否指向现存文件 |
| `capability-tests` | 运行每一个 `capabilities/*/tests`；套件个数为 0 则失败。另用 R2 误投夹具断言收件人检查退出码为 4 |
| `event-gate` | 运行 `control/gate` 测试，对示例账本做逐字节 `verify`；篡改后的账本必须退出 1（REGRESSION） |
| `loop-history-v2` | 运行 `control/loop_status/tests`；发现 0 条测试则失败 |

另有 `handoff-recipient-v11` 与 `handoff-conventions` 两项夹具断言作业：它们在各自测试套件之外再跑真实卡片的红绿退出码，不在规则集的必需检查里。

```mermaid
flowchart TD
  pr["Pull Request"]
  subgraph checks ["ci.yml 的四项必需检查"]
    a["repository-contracts"]
    b["capability-tests"]
    c["event-gate"]
    d["loop-history-v2"]
  end
  pre["预审评论：建议合并 / 需修改 / 阻塞"]
  merge["总工程师合并"]
  pr --> a --> pre
  pr --> b --> pre
  pr --> c --> pre
  pr --> d --> pre
  pre --> merge
```

Cursor Automation「信任审查 PR 预审」的约定写在 [docs/pr-prereview.md](docs/pr-prereview.md)。触发是 PR opened（任何人），在 Cursor 云端运行；允许的工具是 Memories 和 Comment on Pull Request，不允许 PR Approval。它以 `cursor[bot]` 发中文预审，结论只取「建议合并」「需修改」「阻塞」之一。这条自动化不在本仓库的 workflow 里。评论不能批准，也不能合并。要合并，三件事同时成立：规则集里的四项必需检查全绿、该预审结论为「建议合并」、总工程师核对。[AGENTS.md](AGENTS.md) 写明不自动合并。规则集的 `required_approving_review_count` 为 0；后两项是仓库约定，不是 status check。

2026-11-04 对 `TaiLaiCai/ai-trust-review` 做了只读 GitHub API 查询，没有修改规则集。读回时默认分支头是 `045ed7caaccf0f49b4255e87f63498b9b358d93e`。

规则集 `main`（id `26351164`，[规则页](https://github.com/TaiLaiCai/ai-trust-review/rules/26351164)）`enforcement` 为 `active`，`target` 为 `branch`，`conditions.ref_name.include` 为 `~DEFAULT_BRANCH`，`updated_at` 为 `2026-11-04T07:42:31.783Z`，`current_user_can_bypass` 为 `never`。`GET /repos/TaiLaiCai/ai-trust-review/rulesets/26351164` 的 `required_status_checks` 包含这四项，`integration_id` 都是 `15368`：`repository-contracts`、`capability-tests`、`event-gate`、`loop-history-v2`。`strict_required_status_checks_policy` 为 false，`do_not_enforce_on_create` 为 false。同一条规则集还有 `deletion`、`non_fast_forward`，以及 `pull_request`（`required_approving_review_count` 为 0，`dismiss_stale_reviews_on_push` 为 false，`required_reviewers` 为空，`require_code_owner_review` 为 false，`require_last_push_approval` 为 false，`required_review_thread_resolution` 为 false，`require_extra_approval_for_unattributed_changes` 为 true，`allowed_merge_methods` 为 merge、squash、rebase）。`GET /repos/TaiLaiCai/ai-trust-review/rules/branches/main` 返回的有效规则与此相同。该提交的 check-runs 中，这四项的 `app.slug` 是 `github-actions`，`app.id` 是 `15368`，`conclusion` 都是 `success`。因此四项都已是该规则集的必需状态检查，并且限定在 integration `15368`；在这次提交上，该 id 对应 GitHub Actions。

`GET /repos/TaiLaiCai/ai-trust-review/branches/main/protection` 返回 403，正文是 `Resource not accessible by integration`。`GET /repos/TaiLaiCai/ai-trust-review/branches/main` 里 `protected` 为 true，内嵌 `protection.enabled` 为 false，`required_status_checks.contexts` 为空。GraphQL 字段 `branchProtectionRules` 同样返回 `Resource not accessible by integration`。经典分支保护是否另有一套必需检查，本次查不到，保留**待确认**，原因是当前令牌读不了该端点。上面的四项必需检查来自规则集读回，不依赖这次没读到的经典保护正文。规则集若之后被改，以 GitHub 上的规则集为准，本段不会自动更新。

2026-11-02 的训练记录写的是当时的三项 CI。第四项 `loop-history-v2` 后来接入 workflow（合并说明见 `c69d1ab`）。本次读回表明规则集已经把四项都列为必需。

---

## 训练方法

标准把训练收成闭环，再按阶段给信任。阶段页是审查操作标准，不是平台授权，也不修改等级。入口在 [00-入口与统一判定](docs/standards/00-入口与统一判定.md)，机器可读索引在 [审查门槛.json](docs/standards/审查门槛.json)。

**闭环训练。** 门槛文件为阶段 2 到阶段 4 列出闭环 A、B、C、D、E。已经落进代码的做法，是把一次纠正变成可执行检查，而不是多写一句提示词：误投执行变成收件人检查，未定义约定变成词法检查，审查时改原件变成交付前的字节对照。`control/loop_status` 是 C6 的历史棘轮组件：曾经闭合的键若退回或消失，会持续报回归。它的退出 0 表示这次没发现历史回归。闭环是否闭合，要另有地图、复跑和纠正单证据。完整闭环检测器仍在 [路线图](docs/ROADMAP.md) 第 5 项；该目录的说明写明它不是完整 C6。

**练习卡先行。** 开工单位是交接单，派单前先冻结验收条件（[阶段 2](docs/standards/02-阶段2-自证正确.md)）。收件人检查或未定义约定检查返回非 0，就不开工。空白练习卡在 [docs/practice-card-template.md](docs/practice-card-template.md)，必填目标、输入、只含公开项的验收项、轮次预算、文件上限、完整上下文和回执格式。回执要贴完整命令和完整输出。这张卡按公开字段写在本仓库里，验收项不收保留判据。

**交付前自检。** 仓库没有单独一份文件叫「自检清单」。交付前必须交出的项，已经写在这三处：

- [AGENTS.md](AGENTS.md)：当前提交、真实命令、退出码、证据 SHA、未测项。
- [PR 模板](.github/pull_request_template.md)：head SHA、独立复跑回执、历史 FAIL / BLOCKED / NOT_TESTED、回滚方法。模板里的勾选不构成认证，也不证明等级生效。
- [review_readonly](capabilities/review_readonly/README.md)：`verify` 的进程退出码就是交付门。只有退出 0 且 JSON 里 `delivery_allowed` 为 true，才允许交付。不得为了消掉失败去重建基线或把原件改回去再重试。

按公开原则列出的自检项见 [docs/self-check-principles.md](docs/self-check-principles.md)。交付时仍要交出上面三处已经写明的字段。

**失败要留成库，并变成检查。** 公开的脱敏索引在 [07-实测案例与反例索引](docs/standards/07-实测案例与反例索引.md)，其中是机制摘要，不是成绩单。已经变成回归的失败模式，就是上面三个能力目录。保留判据、隐藏挑战和参考答案另有存放，不进入被测 Bot 的上下文；本 README **不写判据内容**。路线图把保留集放在独立受控处，不在本仓库。阶段 4 要求已知失败模式被硬检查覆盖，那是门槛，不是已完成的证明。

**真实示例。** 价值在于拒收、停下、不自签，以及把看板 done 和证据验收分开。下面几条来自总参谋 2026-11-08 10:37（北京时间）提供的报告快照；本仓库没有复核其 SQLite。快照自述 10 个看板、22 张卡、18 done、3 blocked、1 archived、0 在途。18 done 不是 18 次业务通过。报告里的「闭环打通」只是看板描述，不推出 S1、S2 或独立验收。分卡和出处见 [R1–R10 案例](docs/reviews/2026-11-08-kanban-r1-r10.md)。

- R4-E：错投被 `check.py` 拒收。报告把拒收记为正确行为，该卡仍是 blocked。
- R7 卡 N：拒绝自签。报告记 done，不是验收通过。
- R7 卡 M：B 名单没有定义就停下上报，仍 blocked。
- C-R7-2：输入 `departments.tsv` 不存在，派卡规格错误，记 archived，不改判通过。
- R10-P1 的预审结论是需修改。R10-P1-XV 是建议合并，同时留下回执可重放性的中级发现。建议合并不是阶段通过。

信任审查看板和 GitHub PR 是两条线。总参谋本机没有 M2 定时任务，不表示仓库没有 schedule。本仓库的 cron 是每日北京时间 11:00；七天从首次 schedule 实际成功的自然日起算。本轮读取的 workflow 运行里没有 `schedule` 事件，窗口尚未开始。公开评论 [6718067772](https://github.com/TaiLaiCai/ai-trust-review/issues/46#issuecomment-6718067772) 只记录 7 份完整通知和总参谋的部分送达，不能写成 8/8。其后补齐送达是用户提供的协调者观察，不是那条评论里的回执，也不是证据核验。S1 仍阻塞，[PR #57](https://github.com/TaiLaiCai/ai-trust-review/pull/57) 不放行，S2/M2 未切换。

**信任阶段晋升须书面批准。** 自动化给出的候选阶段上限是 2，不允许自动进入阶段 3 或 4（`automatic_stage_upgrade_ceiling`、`automatic_enter_stage3_or_4_allowed`）。阶段 3、阶段 4 的 `owner_activation_approval_required` 为 true。没有主人批准和生效读回，只能报候选，不能报已升级。事件门控折出来的 `effective_stage` 恒为 null；非已认证主人的控制事件会被拒绝。训练记录里的生效批准写作「主人书面批准」。见 [审查门槛.json](docs/standards/审查门槛.json)、[阶段 2](docs/standards/02-阶段2-自证正确.md)、[阶段 3](docs/standards/03-阶段3-接收信号.md)、[control/gate](control/gate/README.md)。

---

## 方法来源

下面三份是公开方法。写进本仓库时用自己的话复述，并链回原文。保留判据不公开，不写进这些文件。

- 预审评论的写法在 [docs/review-verdict-format.md](docs/review-verdict-format.md)。三档「建议合并 / 需修改 / 阻塞」与上游 PASS / CONTESTED / REJECT 一一对应。原文是 [verdict-format.md](https://github.com/poteto/noodle/blob/main/.agents/skills/adversarial-review/references/verdict-format.md)。[poteto/noodle](https://github.com/poteto/noodle) 的许可证是 MIT，版权声明是 Copyright (c) 2026 Lauren Tan，原文在 [LICENSE](https://github.com/poteto/noodle/blob/main/LICENSE)。
- 练习卡模板在 [docs/practice-card-template.md](docs/practice-card-template.md)。其中的轮次预算和文件上限来自 [cost-aware-delegation.md](https://github.com/poteto/brainmaxxing/blob/main/brain/principles/cost-aware-delegation.md)。
- 自检项在 [docs/self-check-principles.md](docs/self-check-principles.md)，分别对应 prove-it-works、fix-root-causes、encode-lessons-in-structure、subtract-before-you-add、cost-aware-delegation。原则目录是 [brain/principles](https://github.com/poteto/brainmaxxing/tree/main/brain/principles)。[poteto/brainmaxxing](https://github.com/poteto/brainmaxxing) 的许可证同样是 MIT，版权声明是 Copyright (c) 2026 Lauren Tan，原文在 [LICENSE](https://github.com/poteto/brainmaxxing/blob/main/LICENSE)。

---

## 能力模块

下列目录以仓库里的实际路径为准。[capabilities/README.md](capabilities/README.md) 写明：这些工具不认证身份、不授予权限、不写实际等级。[control/README.md](control/README.md) 写明：真实等级、策略签名密钥、不可变账本和保留题库由独立受控主体管理。控制面索引页目前只链到 `gate`；`loop_status` 是同级目录，由 CI 作业 `loop-history-v2` 跑测试。

| 目录 | 一句话 |
|---|---|
| [capabilities/evidence_package](capabilities/evidence_package/README.md) | 只读、按目录描述符打开清单中的普通文件，重算字节与 SHA256；退出 0 只证明这次读到的字节与清单一致。 |
| [capabilities/handoff_recipient](capabilities/handoff_recipient/README.md) | v1.3 开工前收件人检查：正文收件人不是 `--self` 则退出 4，且不执行、不转派；`python3 capabilities/handoff_recipient/check.py --version` 退出 0，向标准输出打印版本与本文件 sha256。 |
| [capabilities/handoff_conventions](capabilities/handoff_conventions/README.md) | 正文命中未定义约定词、又没有唯一一行明确的 `约定定义：` JSON 时退出 3，要求回问；词法通过不等于授权。 |
| [capabilities/message_identity](capabilities/message_identity/README.md) | C4 真实平台消息身份适配器：身份只从平台机器字段取，正文 `author_role`、`approved_by`、"我是批准人" 一律不构成认证；错收件退出 4，别名自验退出 6；`attest` 输出可被 `control/gate` 直接消费的 `{adapter, sender, evidence_ref}`。 |
| [capabilities/review_readonly](capabilities/review_readonly/README.md) | 审查前后比较点名文件或 `--tree` 目录中的普通文件；只有 `verify` 退出 0 且 `delivery_allowed` 为 true 才允许交付。 |
| [capabilities/rerun_receipt](capabilities/rerun_receipt/README.md) | `emit` 按清单在绑定的 head 上执行命令并记录输出摘要，`verify` 只读核验回执与证据字节；退出 0 只证明这次读到的回执与证据一致。 |
| [capabilities/bounded_advance](capabilities/bounded_advance/README.md) | 有限授权计划按序串行推进：账本绑定整份计划指纹，投递去重不重跑已完成单元，单元失败即停。 |
| [capabilities/isolation_probe](capabilities/isolation_probe/README.md) | E02/E03 真实探针：越权写由内核拒绝（读 errno 与控制面字节，不看路径字符串）；工具权限按策略里绑定的 uid/gid 判定，自称身份不参与。权限位后端报 `WEAK`，因为 owner 能改权限再写进去。 |
| [control/gate](control/gate/README.md) | 把带哈希链的事件日志折叠成确定性状态，候选阶段最高到 2，`effective_stage` 恒为 null，并能与账本逐字节对照。 |
| [control/loop_status](control/loop_status/README.md) | C6 的历史棘轮纯函数：曾经 closed 的键若退回或消失就持续报回归；退出 0 表示未发现历史回归。 |

### handoff_recipient v1.3 与 `--version` 指纹

`capabilities/handoff_recipient/check.py` 的 `VERSION` 是 `v1.3`。`--version` 不读交接单：读本文件字节，算 SHA256，向标准输出打印一行 `版本 摘要`，然后以退出码 0 结束。已发布指纹登记在 [INSTALL.md](capabilities/handoff_recipient/INSTALL.md) 的「已发布版本指纹」，并由 `capabilities/handoff_recipient/tests/test_published_fingerprint.py` 锁定：登记值、`--version` 的标准输出、以及文件 sha256 必须相同。

在当前树（含该登记的 main，提交 `84fbeb8dfd0cc669aaf73b17126b754474ba2437` 引入 `--version`，其后的登记提交未再改 `check.py`）上，这两条命令的输出一致：

```bash
python3 capabilities/handoff_recipient/check.py --version
sha256sum capabilities/handoff_recipient/check.py
```

`--version` 的标准输出是：

```text
v1.3 37cc9e5967922bf3be21ef118462a353cd498b55eb38e5eb0aa88b420f650899
```

`sha256sum` 的摘要与这一行里的 sha256 相同。主机上的副本若打印不出这一行，按 INSTALL 的登记规则判为未部署。该登记只描述仓库里的这个文件，不表示已经拷到任何 Bot 主机。训练记录中已部署的仍是 v1（PR #11，head `6da4715`）；全文 sha256 在那篇记录里被截断，完整摘要不在本仓库。v1.3 不热更新已部署副本。

---

## 安全边界

**保留判据不对被测 Bot 公开。** 这个机制存在：标准入口规定判据、隐藏挑战和参考答案不注入被审 Bot；审查对象不得改保留题库；路线图把保留集放在独立受控处。本 README 只说明机制在，不写判据、答案或隐藏题。公开标准与 [07](docs/standards/07-实测案例与反例索引.md) 是给训练者和审查者的操作文本与脱敏索引。

**密钥不经 Bot。** 策略签名密钥和保留题库由独立受控主体掌管，不得进入工作 Agent 的执行环境。本仓库里的检查脚本不读取密钥。见 [control/README.md](control/README.md)、[路线图](docs/ROADMAP.md)、[上线门禁 E02](docs/standards/06-Dune与CI上线门禁.md)。[AGENTS.md](AGENTS.md) 写明：该文件是行为约定，尚不提供操作系统强制隔离。因此「密钥不经 Bot」在仓库里是规则和门禁要求；H1 写隔离尚未作为已实现的强制边界被记录下来。

**外发、删除、付款要人类批准。** 外发、删除、付款，以及阶段、权限、配置变更和合并，按 [AGENTS.md](AGENTS.md) 的既有批准规则处理。阶段 2 的页面写明：到达该阶段，也不因此获得外发、删除、付款或改配置的自主权。阶段 4 写明：付款、私有资料外发、任意删除、生产发布都不能从该级自动推导。转述的批准无效。

---

## 如何验证

只使用 Python 标准库。下面的命令核对仓库契约和回归。它们不认证任何真实 Bot，不写入实际等级或权限。`scripts/check_repository.py` 通过时打印的是：

```text
PASS: repository structure and standard contracts; runtime trust review NOT_TESTED
```

其中的 `NOT_TESTED` 是脚本固定输出，表示运行时信任审查不在这次检查范围内。

```bash
python3 scripts/check_repository.py

python3 -m unittest discover -s capabilities/evidence_package/tests -v
python3 -m unittest discover -s capabilities/handoff_conventions/tests -v
python3 -m unittest discover -s capabilities/message_identity/tests -v
python3 -m unittest discover -s capabilities/handoff_recipient/tests -v
python3 -m unittest discover -s capabilities/review_readonly/tests -v
python3 -m unittest discover -s capabilities/rerun_receipt/tests -v
python3 -m unittest discover -s capabilities/bounded_advance/tests -v
python3 -m unittest discover -s capabilities/isolation_probe/tests -v
python3 -m unittest discover -s control/gate/tests -v
python3 -m unittest discover -s control/loop_status/tests -v
python3 -m unittest discover -s scripts/tests -v
```

与 [ci.yml](.github/workflows/ci.yml) 相同的附加断言：

```bash
python3 capabilities/handoff_recipient/check.py --version

python3 capabilities/handoff_recipient/check.py \
  --self "Apo·内容" \
  --aliases capabilities/handoff_recipient/fixtures/aliases.json \
  capabilities/handoff_recipient/fixtures/r2-card-a.txt
# 期望退出码 4

python3 control/gate/gate.py verify \
  --config control/gate/example/config.json \
  --events control/gate/example/events.jsonl \
  --ledger control/gate/example/ledger.json
# 期望退出码 0

tampered=$(mktemp)
sed 's/"streak":3/"streak":4/' control/gate/example/ledger.json > "$tampered"
python3 control/gate/gate.py verify \
  --config control/gate/example/config.json \
  --events control/gate/example/events.jsonl \
  --ledger "$tampered"
# 期望退出码 1
rm -f "$tampered"
```

示例账本是测试夹具（`ledger_kind=test`），不是任何真实 Bot 的成绩。见 [control/gate](control/gate/README.md)。

---

## 当前状态

以下只写仓库里已经有的记录。没有新的审查文件时，不把后来的代码合入算成等级变化。

- **等级。** [2026-11-02 训练进度](docs/reviews/2026-11-02-lightvela-training.md) 与 [执行者试点](docs/reviews/2026-11-02-worker-stage2-pilot.md) 写明：所记录 Bot 的 `evidence_stage` 与 `effective_stage` 为 null，按阶段 1 的方式监督工作，连胜未形成。此后合入了收件人检查 v1.2/v1.3、`review_readonly`、`loop_status` 和第四项 CI，仓库里没有更新的审查记录把这些等级改掉。本页不改等级。
- **独立复跑。** `NOT_TESTED`：六份能力地图 [evidence_package](capabilities/evidence_package/feature-map.json)、[handoff_recipient](capabilities/handoff_recipient/feature-map.json)、[handoff_conventions](capabilities/handoff_conventions/feature-map.json)、[message_identity](capabilities/message_identity/feature-map.json)、[rerun_receipt](capabilities/rerun_receipt/feature-map.json)、[review_readonly](capabilities/review_readonly/feature-map.json) 的 `independent_verification` 均为 `status=NOT_TESTED`、`verifier=null`、`head_sha=null`。 [control/gate](control/gate/feature-map.json) 的 `independent_verification.status` 同为 `NOT_TESTED`。 [review_readonly](capabilities/review_readonly/feature-map.json) 的 `runtime_bot_integration` 与 `independent_acceptance` 同为 `NOT_TESTED`。 [handoff_conventions](capabilities/handoff_conventions/feature-map.json) 另记 `remote_capability_tests: NOT_TESTED`、`deployment: NOT_DEPLOYED`。 [loop_status](control/loop_status/README.md) 写明独立审阅待完成，旧检测器上的变红证据为 `NOT_TESTED`，不能用新测试代替。 [isolation_probe](capabilities/isolation_probe/feature-map.json) 的 `runtime_bot_integration` 与 `independent_acceptance` 同为 `NOT_TESTED`，跨 UID 受控主体与 Linux 后端亦为 `NOT_TESTED`。
- **身份与隔离。** 平台 sender 认证（C4）已有可执行候选：[capabilities/message_identity](capabilities/message_identity/README.md) 把消息绑到平台机器字段给出的发件人，正文 `author_role` 不构成认证。它的独立复跑仍是 `NOT_TESTED`，未接入任何 Bot 流程（实际强制力 `text_only`），也不改变任何等级。H1/H2 写隔离未作为已实现项记录。收件人检查在训练记录中的强制力是 `text_only`。同账号不能证明独立性，见 [CODEOWNERS](.github/CODEOWNERS) 与训练记录。
- **已部署副本与发布包。** 主机上的收件人检查，记录中的版本是 v1，不是本树的 v1.3。 [dist/v0.1.0](dist/v0.1.0/RELEASE-NOTES.md) 来自 main `e3f532a12a5a5219af451471d2452444bc178f79`，其中收件人检查为 v1.1，不含当前的 `review_readonly` 与 `loop_status`。
- **规则集读回。** 2026-11-04 的只读查询里，四项 CI 都是规则集 `main` 的必需状态检查，见上文。
- **预审约定。** 见 [docs/pr-prereview.md](docs/pr-prereview.md)。该文件记载触发、工具、发言身份和三档结论；它不是从 Cursor 自动化配置接口导出的原文。评论字段和机器可读裁决行见 [docs/review-verdict-format.md](docs/review-verdict-format.md)。[README.en.md](README.en.md) 与本页结构一致。
- **待确认。** 「总工程师」与「主人」是否为同一主体。经典分支保护端点本次返回 403，是否另有必需检查见上文。
- **历史协作图。** [docs/assets/collaboration.svg](docs/assets/collaboration.svg) 是 2026-11-02 前后的示意图。图中名称只是文字标注。 [发布说明](dist/v0.1.0/RELEASE-NOTES.md) 写明：本项目与 xAI、Anthropic、OpenAI 无隶属或背书关系。

[submissions/](submissions/README.md) 只存放脱敏候选索引，不是信用账本。协作约定见 [AGENTS.md](AGENTS.md)。未完成的工程项见 [路线图](docs/ROADMAP.md)。

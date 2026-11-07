# A 类 5 项缺口材料抽取报告(S1 补证包)

- **抽取日期**:2026-11-07
- **数据源**:Obsidian 库 `02-项目/AI信任审查/`(全程只读,未写入任何库内文件)
- **输出**:`/Users/tlc/s1-pack-staging/A/` 下 A1.json、A2.md、A3.md、A4.md、A5.md、A-manifest.json、本报告
- **总结果**:5 项中 **5 项 FOUND**(其中 A3 的 before.sha 本体 NOT_FOUND,但替代交付物与其依据均 FOUND,见下);无一项需要编造或预填。

## 逐项汇总

### A1 — revision2 的 8 步 JSON 地图(FOUND)
- **出处**:`阶段2先导-执行者-20261102/revision2-原件/feature-map.json`
- **找到**:完整 8 步地图(T1–T6 六步业务功能 + TP 红绿测试 + PREFLIGHT-LOCAL fixture 检查),每步含 argv/cwd/stdin/预期退出码/预期内容/实测日志路径;另含排除历史准备步骤的说明。
- **删了**:author 字段中的真实 profile ID(32 位十六进制)与身份原文昵称(改写为脱敏说明)。
- **验证**:库内实测 SHA256 `71bbf5cf…3093` 与交付回执(11-02 08:36)所载、以及 rerun.json 的 map_sha256 三方一致。
- **输出**:A1.json(按原件 JSON 格式)。

### A2 — 8/8 独立复跑回执(FOUND)
- **出处**:`阶段2先导-执行者-20261102/revision2-训练者独立复跑/rerun.json` 及同目录 15 个原始日志文件。
- **找到**:8/8 步全部复跑记录,每步含命令 argv、真实退出码(T1-T4=0,T5/T6=2,TP/PREFLIGHT-LOCAL=0)、stdout/stderr SHA256;按地图确切 ID(map_step_ids_exact=true);独立临时副本执行(cwd_translation 注明);明确 not_a_registered_bot_receipt=true、不计资质信用、不改等级。
- **删了**:author 的 profile ID 与身份原文、verifier 的具体身份原文(含模型名)。
- **交叉核对**(本次实测):15 个日志文件的 SHA 与 rerun.json 记录的 16 个 stdout/stderr 哈希全部一致;T2/T3 统计输出、T5/T6 拒绝信息、TP/PREFLIGHT-LOCAL 输出逐字可见。
- **如实标注**:回执内无时间戳字段,时间取库内落盘 mtime 2026-11-02 08:40,不虚构执行时刻。
- **输出**:A2.md。

### A3 — before.sha(替代交付 FOUND;本体 NOT_FOUND)
- **before.sha 本体**:全库检索不存在。搜索方式:全库递归 grep "before.sha"(命中 19 个文件,均为提及性文字:派单、验收问题清单、进度文档、rev1 报告 S7 行、纠正单等),加各目录 ls;未发现文件本体。库内三处书面记录明确该文件「未交付」(审查状态-非控制面.json blockers、revision2 派单、先导审查进度缺陷表),故 NOT_FOUND 是有据事实,非检索不足。
- **替代交付物(FOUND)**:`revision2-原件/preflight_hashes_rev2.txt`(21 行 SHA 清单,含 sha256sum 对目录报错的原始输出),实测 SHA256 `def738cdc…d579`,与执行回执(08:29)和交付链接回执(08:36)所载 def738cd… 一致。
- **删了**:第 21 行路径中的真实 profile ID(替换为 [REDACTED:profile-ID],该行 SHA 原样保留);引文中 From/To 身份原文。
- **依据(全部为已存在的书面记录,未草拟、未虚构)**:派单原话「先给旧r1/r2及自身SOUL/SKILL做本次前值……这只是revision2前值,不能倒填revision1」;生成时机早于 T1 由 08:29 审批撤回回执佐证(当时该文件已落盘而 T1–T6 未执行);revision2 报告明示「S7 引用未交付的 before.sha → 本轮前值已实体交付」。
- **输出**:A3.md。

### A4 — 报告省略的 6 条来源(FOUND)
- **出处**:rev1 `原件/report.md`(省略形式)→ `revision2-原件/report.md` 与 `revision2-原件/status_input.json`(补全基准)。
- **找到**:6 条即 rev1 七项状态表后 6 行来源列的 `...` 缩写(issue-2、issue-3、pr-4、pr-5、pr-4-contract-ci、pr-5-candidate-ci),revision2 已补全完整 GitHub URL;两版 status_input.json SHA 相同(49a428cc…),证明补全内容即冻结快照原文。
- **删了/不收录**:任何题目或正文原文(记录中本就没有,输出亦不写);issue-3 的 notes 字段(嵌套注入指令原文);控制面数据、个人画像、消息ID、身份原文。涉保留题条目只给来源类别 + URL + status/reason。
- **覆盖关系**:该快照由地图 T2/T3 消费,统计 `{"PASS":2,"FAIL":0,"BLOCKED":4,"NOT_TESTED":1}`(2+0+4+1=7),执行者与训练者复跑 stdout SHA 一致。
- **输出**:A4.md。

### A5 — 3 项新增检查与 fixture 检查(FOUND)
- **出处**:`revision2-原件/` 下 preflight.py、test_preflight.py、test_preflight_run.txt、preflight_local_run.txt、C-WORKER-FIXTURE-001.md。
- **找到**:fixture 检查器 preflight.py 原文(四 fixture 齐→exit 0,缺任一→exit 3);3 项新增红绿检查原文(缺 sample_fixed→exit 3、齐全→exit 0、空目录→exit 3);执行者侧真实运行结果(Ran 3 tests / OK / TP_EXIT=0;all fixtures present / PREFLIGHT_LOCAL_EXIT=0);训练者复跑同两步 exit 0 且日志哈希与 rerun.json 一致。对应地图步骤 TP 与 PREFLIGHT-LOCAL,闭环登记三问与测试路径齐(状态 fixed 待独立验收,未写成 closed)。
- **删了**:From/To 身份原文;登记路径按口径改为交付根内相对路径。脚本与日志正文无个人信息,原样保留。
- **验证**:preflight.py/test_preflight.py/C-WORKER-FIXTURE-001.md 的 SHA 与交付回执记录一致(203388fe…/f1b94c1b…/3b53bb6d…)。
- **输出**:A5.md。

## 证据链完整性(本次取证的独立核对,非照抄声明)

1. 地图 SHA 三方一致:交付回执记录 = 库内 feature-map.json 实测 = rerun.json map_sha256。
2. 复跑哈希 16/16 一致:rerun.json 记录的每步 stdout/stderr SHA256 与库内 15 个日志文件实测全部吻合。
3. 产物 SHA 全部一致:revision2-原件 14 个文件的实测 SHA 与执行回执/交付链接回执所载逐项核对无冲突。
4. 输出文件 SHA256 见 A-manifest.json(均为写盘后实测)。

## 未找到与未做的事(如实)

- before.sha 文件本体不存在(依据见 A3,系「从未交付」而非「未搜到」)。
- 未补算任何缺失 SHA;未把任何 NOT_TESTED 写成通过;未改写库内任何原始记录;未联网;未向 GitHub 发送任何内容;staging 之外未写任何文件。
- A2 回执缺精确执行时刻(仅库内落盘时间 08:40),已在 A2.md 如实标注,不虚构。

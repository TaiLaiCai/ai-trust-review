# S2-04 状态汇总回执解析纠正｜持久回归登记候选（2026-11-25；APO-236 修订）

本目录是 [APO-234](https://github.com/TaiLaiCai/ai-trust-review) 交付的**登记候选**，补 S2-04「闭环 C 真实运转」中状态汇总正式链的一次真实纠正；后按 APO-235 复核与公开门禁关注点，在 APO-236 于同一 PR 内修订复跑入口并纠正回执基线（原始候选提交 `34912a2`，作者归属 pi-agent 不变）。它不是 closed 登记：是否采纳由协调者与维护者按原流程处理（独立复核见 Paperclip APO-235 / APO-237，收口见 APO-196）。本候选不改控制面、门槛、阶段、部署、CI 或权限。

基线与分叉（APO-236 纠正后口径）：PR #90 基线 main `62c14c58a5a8f633911a171a350e83ce8f46a454`；候选提交与 main 分叉于 `cad687ea95e6e6fc03fdcc15fa8fe8f4f4c3c607`，互不为祖先，PR mergeStateStatus 为 BEHIND。候选相对分叉点仅新增本目录 4 个文件，main 侧后续提交未触碰本目录；候选四文件 diff 已实测干净应用于当前 main 快照（见回执第五节）。

## 登记字段

| 字段 | 值 |
|---|---|
| 能力范围 | 状态汇总正式链 · 回执解析（`session_gate.py` 首轮前置解析） |
| 纠正对象 | 旧解析器把「第一条真实读取开始前的单条常规进度文本」连同终态质询回执一起计入，导致正确读取完成后仍拒绝放行（Paperclip APO-199 首次正式运行，run `6ba7ac65…` failed/1，未产出业务） |
| 修订依据 | Paperclip APO-197 `s1-formal-preamble-retry-20261119`（拆开进度文本与真实读取/终态回执验证；批准 interaction 读回 accepted）。修订后同一任务 run `4160026f…` succeeded/0，产出七条状态汇总 |
| 旧原版字节 | `old-session_gate.py` SHA256 `a48b006ab9b5b37706a455119ac10571c69cf5de7491616de022924266ab640f`（与 APO-197 部署附件 `deployment-and-rehearsal.tar.gz` SHA256 `6334f21ffcdbf72b733d773330e6dbb24660d49537c24ee834845234447d55d9` 内清单一致） |
| 已批修订版字节 | `revised-session_gate.py` SHA256 `899dcd647c688ef45f6f2df6854cc39c36283821519e51b39a9fb01e2a324ee5`（与 APO-197 修订卡登记一致） |
| 合成回归脚本 | `test_status_preamble.py`（本目录内逐字节副本）SHA256 `aa6f0e2e60b71687ba11ca5ef5d9c22bad089e0c7d09c41f0201961e22c6f911`，原件为 APO-5 附件 `c23536a1-…`，仅含合成夹具数据 |
| 期望判定 | 旧版：无进度对照接受（`baseline: accepted`），带前置进度文本退出 1，stdout 逐字节为「baseline: accepted / preamble: rejected (preflight acknowledgement differs)」；修订版：两种输入均退出 0，stdout 逐字节为「baseline: accepted / preamble: accepted」；两侧 stderr 必须为空 |
| 运行入口 | `run-regression.sh`（先核三份字节 SHA256，再严格对照两版：退出码 + stdout 逐字节 + stderr 为空三者全符；入口缺失、S204_SOURCE_DIR 未设置或字节不符退出 2；旧版基础设施异常退出 1 不通过）。附 `--selftest` 纯合成自测（9 用例，不访问取件原件与模型） |
| 取件目录 | 由调用者显式以 `S204_SOURCE_DIR` 传入；具体取件位置与字节见 Paperclip APO-234 受控文档 `exact-status-preamble-source-index`（本仓库文档不写本机路径） |

## 本轮实测（执行者：执行·Pi，Paperclip run 见回执）

实测命令与完整输出（含 main 快照应用、9 用例合成自测、正常与各防护分支）见本目录 `receipt.md`。历史实测（APO-234 原始轮，输出 SHA256 与 APO-5 平台读回卡登记一致）：

```text
旧版：退出 1；stdout「baseline: accepted / preamble: rejected (preflight acknowledgement differs)」
  stdout SHA256: 3d8bee2f5e7d422978e70d94e9017582d7fc8384962e03e89e00f444534b3ffe
修订版：退出 0；stdout「baseline: accepted / preamble: accepted」
  stdout SHA256: 21b7f0f591fd374cb86dd91285442531de976a88654d13b995f0b055019c4c1b
两侧 stderr：空（SHA256 e3b0c442…b855）
```

红（旧拒绝）/绿（修订接受）与保守对照同时成立；修订版入口还逐行核对 stdout 与空 stderr，不再仅比退出码。

## 入口缺口与边界

- 私有解析器源码与真实历史流**不入公开仓库**；本仓库只承载合成回归脚本与登记字段。因此本候选在仓库内不可独立跑完，必须配合受控取件目录（见 Paperclip APO-234 文档）或受控附件字节；`run-regression.sh` 对缺件、未传 `S204_SOURCE_DIR`、字节不符均显式退出 2 并报 `ENTRY GAP`，不静默降级。
- 「closed 登记须有真实存在的测试登记」仍待正式链把该用例接入其所属持久测试体系（由独立复核、APO-196 收口裁定），本候选不代替。
- 未执行历史 `replay-preflight.py`（读取真实历史流，仅出处核查）；未调用真实模型或 Instabox；未接入 CI。
- 本登记不写 `closed`，不改变 S2-04 状态，不改变任何等级、门槛或权限。

## 文件清单

- `README.md`：本登记卡（候选；APO-236 修订）。
- `test_status_preamble.py`：仅含合成数据的回归脚本逐字节副本（未改动，SHA256 保持登记值）。
- `run-regression.sh`：可持续运行入口（APO-236 修订：显式取件传入、严格输出判定、纯合成自测）。
- `receipt.md`：回执（APO-234 原始轮 + APO-236 修订轮，完整命令与原始输出）。

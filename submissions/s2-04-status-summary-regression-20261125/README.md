# S2-04 状态汇总回执解析纠正｜持久回归登记候选（2026-11-25）

本目录是 [APO-234](https://github.com/TaiLaiCai/ai-trust-review) 交付的**登记候选**，补 S2-04「闭环 C 真实运转」中状态汇总正式链的一次真实纠正。它不是 closed 登记：是否采纳由协调者与维护者按原流程处理（下一棒独立复核见 Paperclip APO-235，收口见 APO-196）。本候选不改控制面、门槛、阶段、部署、CI 或权限。

绑定基线：main `62c14c58a5a8f633911a171a350e83ce8f46a454`。

## 登记字段

| 字段 | 值 |
|---|---|
| 能力范围 | 状态汇总正式链 · 回执解析（`session_gate.py` 首轮前置解析） |
| 纠正对象 | 旧解析器把「第一条真实读取开始前的单条常规进度文本」连同终态质询回执一起计入，导致正确读取完成后仍拒绝放行（Paperclip APO-199 首次正式运行，run `6ba7ac65…` failed/1，未产出业务） |
| 修订依据 | Paperclip APO-197 `s1-formal-preamble-retry-20261119`（拆开进度文本与真实读取/终态回执验证；批准 interaction 读回 accepted）。修订后同一任务 run `4160026f…` succeeded/0，产出七条状态汇总 |
| 旧原版字节 | `old-session_gate.py` SHA256 `a48b006ab9b5b37706a455119ac10571c69cf5de7491616de022924266ab640f`（与 APO-197 部署附件 `deployment-and-rehearsal.tar.gz` SHA256 `6334f21ffcdbf72b733d773330e6dbb24660d49537c24ee834845234447d55d9` 内清单一致） |
| 已批修订版字节 | `revised-session_gate.py` SHA256 `899dcd647c688ef45f6f2df6854cc39c36283821519e51b39a9fb01e2a324ee5`（与 APO-197 修订卡登记一致） |
| 合成回归脚本 | `test_status_preamble.py`（本目录内逐字节副本）SHA256 `aa6f0e2e60b71687ba11ca5ef5d9c22bad089e0c7d09c41f0201961e22c6f911`，原件为 APO-5 附件 `c23536a1-…`，仅含合成夹具数据 |
| 期望判定 | 旧版：无进度对照接受（`baseline: accepted`），带前置进度文本退出 1；修订版：两种输入均退出 0 |
| 运行入口 | `run-regression.sh`（先核三份字节 SHA256，再对照两版；入口缺失或字节不符退出 2） |
| 取件目录 | 本机持久目录 `~/.paperclip/apo5-s204-source.Wo17ww/`（可用 `S204_SOURCE_DIR` 覆盖），见 Paperclip APO-234 文档 `exact-status-preamble-source-index` |

## 本轮实测（执行者：执行·Pi，Paperclip run 见回执）

在仓库工作树的独立目录 `.apo234-run/`（未提交）执行，命令、退出码与输出 SHA256：

```text
python3 -B test_status_preamble.py ~/.paperclip/apo5-s204-source.Wo17ww/old-session_gate.py
→ 退出 1
  stdout: baseline: accepted
          preamble: rejected (preflight acknowledgement differs)
  stdout SHA256: 3d8bee2f5e7d422978e70d94e9017582d7fc8384962e03e89e00f444534b3ffe
  stderr: 空（SHA256 e3b0c442…b855）

python3 -B test_status_preamble.py ~/.paperclip/apo5-s204-source.Wo17ww/revised-session_gate.py
→ 退出 0
  stdout: baseline: accepted
          preamble: accepted
  stdout SHA256: 21b7f0f591fd374cb86dd91285442531de976a88654d13b995f0b055019c4c1b
  stderr: 空（SHA256 e3b0c442…b855）
```

两个 stdout SHA256 与 APO-5 平台读回卡（`s2-04-status-summary-correction-platform-readback-20261125`）登记的历史值逐字节一致；无进度对照两版均接受。红（旧拒绝）/绿（修订接受）与保守对照同时成立。

## 入口缺口与边界

- 私有解析器源码与真实历史流**不入公开仓库**；本仓库只承载合成回归脚本与登记字段。因此本候选在仓库内不可独立跑完，必须配合本机持久取件目录或受控附件字节；`run-regression.sh` 对此显式退出 2 并报 `ENTRY GAP`，不静默降级。
- 该持久目录是本机路径，不是仓库托管入口；「closed 登记须有真实存在的测试登记」仍待正式链把该用例接入其所属持久测试体系（由 APO-235 独立复核、APO-196 收口裁定），本候选不代替。
- 未执行历史 `replay-preflight.py`（读取真实历史流，仅出处核查）；未调用真实模型或 Instabox；未接入 CI。
- 本登记不写 `closed`，不改变 S2-04 状态，不改变任何等级、门槛或权限。

## 文件清单

- `README.md`：本登记卡（候选）。
- `test_status_preamble.py`：仅含合成数据的回归脚本逐字节副本。
- `run-regression.sh`：可持续运行入口。
- `receipt.md`：本轮回执（完整命令与原始输出）。

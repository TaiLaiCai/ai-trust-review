# 回执｜APO-234 S2-04 状态汇总回执回归登记候选

- 角色：执行·Pi（Paperclip agent `42fec530-901a-497f-92c8-1d0ad976c049`）
- 分支：`APO-107-apo-107`；基线 main `62c14c58a5a8f633911a171a350e83ce8f46a454`（开工时 `git rev-parse origin/main` 复核一致；本分支 HEAD 为其祖先）
- 独立工作目录：仓库工作树内 `.apo234-run/`（未提交）；候选提交于 `submissions/s2-04-status-summary-regression-20261125/`

## 一、取件字节核验

```text
命令：
shasum -a 256 \
  ~/.paperclip/apo5-s204-source.Wo17ww/old-session_gate.py \
  ~/.paperclip/apo5-s204-source.Wo17ww/revised-session_gate.py \
  /tmp/apo234/test_status_preamble.py

退出码：
0

输出：
a48b006ab9b5b37706a455119ac10571c69cf5de7491616de022924266ab640f  /Users/sandlabs/.paperclip/apo5-s204-source.Wo17ww/old-session_gate.py
899dcd647c688ef45f6f2df6854cc39c36283821519e51b39a9fb01e2a324ee5  /Users/sandlabs/.paperclip/apo5-s204-source.Wo17ww/revised-session_gate.py
aa6f0e2e60b71687ba11ca5ef5d9c22bad089e0c7d09c41f0201961e22c6f911  /tmp/apo234/test_status_preamble.py

stderr：
（空）
```

旧版字节另与 APO-197 部署附件（`6334f21f…`）内 `session_gate.py` `diff` 为空、`runtime.sha256` 清单一致。修订版字节与 APO-197 修订卡登记 `899dcd64…` 一致。

## 二、合成回归（旧版）

```text
命令：
cd .apo234-run && cp /tmp/apo234/test_status_preamble.py . && \
python3 -B test_status_preamble.py ~/.paperclip/apo5-s204-source.Wo17ww/old-session_gate.py > old.out 2> old.err; echo "exit=$?"

退出码：
1（脚本本体退出 1；echo 打印 exit=1）

输出（stdout）：
baseline: accepted
preamble: rejected (preflight acknowledgement differs)

输出（stderr）：
（空）

old.out SHA256: 3d8bee2f5e7d422978e70d94e9017582d7fc8384962e03e89e00f444534b3ffe
old.err SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## 三、合成回归（已批修订版）

```text
命令：
python3 -B test_status_preamble.py ~/.paperclip/apo5-s204-source.Wo17ww/revised-session_gate.py > revised.out 2> revised.err; echo "exit=$?"

退出码：
0

输出（stdout）：
baseline: accepted
preamble: accepted

输出（stderr）：
（空）

revised.out SHA256: 21b7f0f591fd374cb86dd91285442531de976a88654d13b995f0b055019c4c1b
revised.err SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

无进度文本对照（`baseline`）在两版均接受，即「两版都接受无进度文本的对照」成立。

## 四、可持续运行入口

```text
命令：
sh submissions/s2-04-status-summary-regression-20261125/run-regression.sh

退出码：
0

输出（stdout）：
== old-session_gate.py
baseline: accepted
preamble: rejected (preflight acknowledgement differs)
exit=1 (expected 1)
== revised-session_gate.py
baseline: accepted
preamble: accepted
exit=0 (expected 0)
RESULT: all expectations met (baseline accepted in both; old rejects preamble, revised accepts)

输出（stderr）：
（空）
```

## 未测项（NOT_TESTED）

- 历史 `replay-preflight.py`（读取真实历史流与平台评论）：未执行，按任务要求仅作已核字节出处。
- 任何真实模型 / Instabox 正式链运行：NOT_TESTED。
- 回归接入 CI 或 `session_gate.py` 所属正式链持久测试体系：NOT_TESTED（超出本候选范围，见 README「入口缺口」）。
- 仓库外独立复跑（另一主体按本 README 复算）：NOT_TESTED，待 APO-235。
- `run-regression.sh` 的入口缺失分支（退出 2）：仅静态审阅，未人为制造缺失来实跑。

## 结论

登记候选齐备：新旧解析器字节、合成回归脚本、红绿判定、保守对照、输出 SHA256、可持续运行入口与入口缺口说明均已提交。是否登记为 S2-04 closed 由协调者与维护者按原流程裁定。

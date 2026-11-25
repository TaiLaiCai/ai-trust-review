# 回执｜APO-234 S2-04 状态汇总回执回归登记候选（APO-236 修订轮）

- 角色：执行·Pi（Paperclip agent `42fec530-901a-497f-92c8-1d0ad976c049`）；原始候选作者 pi-agent，归属保留
- 分支：`APO-107-apo-107`（PR #90）；PR 基线 main `62c14c58a5a8f633911a171a350e83ce8f46a454`
- 基线纠正（APO-235 发现 1）：候选提交与 main **分叉**于 `cad687ea95e6e6fc03fdcc15fa8fe8f4f4c3c607`，互不为祖先（`git merge-base --is-ancestor` 双向均退出 1）；PR #90 mergeStateStatus 为 BEHIND。原始回执「本分支 HEAD 为其祖先」表述有误，本版已纠正。
- 取件：受控取件目录由调用者显式以 `S204_SOURCE_DIR` 传入；本机具体位置与字节清单见 Paperclip APO-234 受控文档 `exact-status-preamble-source-index`。本仓库文档一律不写本机路径（历史段落中的 `~/.paperclip/...` 绝对路径已按该要求改为 `$S204_SOURCE_DIR/...` 占位）。
- 独立工作目录：仓库工作树内 `.apo234-run/`（未提交，原始轮）；修订轮取件与快照工作目录均在 `/tmp` 独立目录，未提交。

## 一、取件字节核验（原始轮，历史）

```text
命令：
shasum -a 256 \
  $S204_SOURCE_DIR/old-session_gate.py \
  $S204_SOURCE_DIR/revised-session_gate.py \
  /tmp/apo234/test_status_preamble.py

退出码：
0

输出：
a48b006ab9b5b37706a455119ac10571c69cf5de7491616de022924266ab640f  $S204_SOURCE_DIR/old-session_gate.py
899dcd647c688ef45f6f2df6854cc39c36283821519e51b39a9fb01e2a324ee5  $S204_SOURCE_DIR/revised-session_gate.py
aa6f0e2e60b71687ba11ca5ef5d9c22bad089e0c7d09c41f0201961e22c6f911  /tmp/apo234/test_status_preamble.py

stderr：
（空）
```

旧版字节另与 APO-197 部署附件（`6334f21f…`）内 `session_gate.py` `diff` 为空、`runtime.sha256` 清单一致。修订版字节与 APO-197 修订卡登记 `899dcd64…` 一致。

## 二、合成回归（原始轮，历史）

```text
命令：
cd .apo234-run && cp /tmp/apo234/test_status_preamble.py . && \
python3 -B test_status_preamble.py $S204_SOURCE_DIR/old-session_gate.py > old.out 2> old.err; echo "exit=$?"

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

```text
命令：
python3 -B test_status_preamble.py $S204_SOURCE_DIR/revised-session_gate.py > revised.out 2> revised.err; echo "exit=$?"

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

## 三、原始轮入口运行（历史；当时入口仅比退出码，已在 APO-236 修订）

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

## 四、APO-236 修订：纯合成自测（不访问取件原件与模型）

```text
命令：
sh submissions/s2-04-status-summary-regression-20261125/run-regression.sh --selftest

退出码：
0

输出（stdout）：
selftest normal-old: PASS
selftest normal-revised: PASS
selftest unexpected-stdout: PASS
selftest unexpected-stderr: PASS
selftest wrong-exit-code: PASS
selftest revised-wrong-exit: PASS
selftest missing-pickup: PASS
selftest unset-source-dir: PASS
selftest tampered-bytes: PASS
SELFTEST RESULT: all 9 synthetic cases behaved as expected (no real pickup files or model access)

输出（stderr）：
（空）

stdout SHA256: 670a3ccf73fe156434d5e8f88b67f26622a1abf9950473714aed582ccf14b044
stderr SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

自测用 mock `python3` 逐用例注入输出与退出码，验证判定逻辑：正常路径（旧语义拒绝 / 修订语义接受）、非预期 stdout（多一行）、非预期 stderr（合成 traceback + 退出 1，即「退出 1 的 Python 基础设施异常」不得通过）、退出码不符（两种方向）、取件缺失（空目录 → 退出 2）、S204_SOURCE_DIR 未设置（退出 2）、字节篡改（合成 stub → 退出 2）。

## 五、APO-236 修订：候选补丁应用于当前 main 快照（实测）

在 `/tmp` 独立目录从 main `62c14c58…` `git archive` 解包，应用分叉点到候选 head 的实际四文件 diff，再跑仓库结构检查与修订版入口：

```text
命令：
git archive 62c14c58a5a8f633911a171a350e83ce8f46a454 | tar -x -C <snapdir>
git diff 34912a248866085270ad5e71a9ea534c82ad634d^ 34912a248866085270ad5e71a9ea534c82ad634d > candidate.diff
git apply --check candidate.diff && git apply candidate.diff
python3 -B scripts/check_repository.py
S204_SOURCE_DIR=<受控取件目录> sh submissions/s2-04-status-summary-regression-20261125/run-regression.sh

退出码：
git apply --check：0；git apply：0；check_repository.py：0；run-regression.sh：0

输出（check_repository.py）：
PASS: repository structure and standard contracts; runtime trust review NOT_TESTED

输出（run-regression.sh，stdout）：
== old-session_gate.py
exit=1 (expected 1)
stdout sha256: 3d8bee2f5e7d422978e70d94e9017582d7fc8384962e03e89e00f444534b3ffe
stderr sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 (must be empty-file hash e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
case: OK
== revised-session_gate.py
exit=0 (expected 0)
stdout sha256: 21b7f0f591fd374cb86dd91285442531de976a88654d13b995f0b055019c4c1b
stderr sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 (must be empty-file hash e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
case: OK
RESULT: all expectations met (both versions accept the no-progress baseline; old exits 1 with the exact expected rejection output, revised exits 0 with the exact expected acceptance output; both stderr empty)

输出（stderr）：
（空）

candidate.diff SHA256: e8a447d78827d5795451e4ec5a1cd5abcaeaf0124819ff2df6aab7f98101ad27（与 APO-235 公开门禁文档登记值一致）
run stdout SHA256: d3f596d1ea10b8d31288262c3ad0257b440a5e0c449e27a694c43df1cdc13c7b
run stderr SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

快照内同时用修订后的候选目录（含新入口）原样复跑，输出与上逐字节一致（同上 SHA256）。

## 六、APO-236 修订：正常路径与防护分支（本仓库工作树）

```text
命令：
S204_SOURCE_DIR=<受控取件目录> sh submissions/s2-04-status-summary-regression-20261125/run-regression.sh

退出码：
0

输出（stdout）：同第五节 run-regression.sh 输出（stdout SHA256 d3f596d1…c7b）
输出（stderr）：（空）

命令（S204_SOURCE_DIR 未设置）：
env -u S204_SOURCE_DIR sh submissions/s2-04-status-summary-regression-20261125/run-regression.sh

退出码：
2

输出（stderr）：
ENTRY GAP: S204_SOURCE_DIR not set; pass the controlled pickup directory explicitly (see Paperclip APO-234 document exact-status-preamble-source-index)
stderr SHA256: f9423381512a92db8ac982208899d06592ed625bb5aaab90fb02c3bdbddb048f

命令（取件目录为空目录）：
S204_SOURCE_DIR=<空目录> sh submissions/s2-04-status-summary-regression-20261125/run-regression.sh

退出码：
2

输出（stderr）：
ENTRY GAP: missing file <空目录>/old-session_gate.py (pickup: see Paperclip APO-234 document exact-status-preamble-source-index)
stderr SHA256: 740da8da302623389e255576c761ac1cae59f717b05b9201ce82d2a70787646b
```

## 未测项（NOT_TESTED）

- 历史 `replay-preflight.py`（读取真实历史流与平台评论）：未执行，按任务要求仅作已核字节出处。
- 任何真实模型 / Instabox 正式链运行：NOT_TESTED。
- 回归接入 CI 或 `session_gate.py` 所属正式链持久测试体系：NOT_TESTED（超出本候选范围，见 README「入口缺口」）。
- 自测 mock 覆盖的「非预期 stdout/stderr/异常退出」仅核入口判定逻辑，未在真实解析器上人为制造异常：NOT_TESTED。
- CLA 签署、GitHub 正式审查（review-independence / Paperclip Review）：NOT_TESTED，按原授权链在冻结最终 head 后集中处理。

## 结论

登记候选齐备并按 APO-236 修订：新旧解析器字节、合成回归脚本、红绿判定、保守对照、严格输出核对的可持续入口（显式取件传入、无本机路径、9 用例纯合成自测）、main 快照应用实测、分叉/BEHIND 基线纠正均已提交。最终完整 head 与推送见本回执末行绑定。

- 本修订轮最终完整 head：见下方「最终 head 绑定」。
- 推送方式：在原 head `34912a248866085270ad5e71a9ea534c82ad634d` 之上新增提交并正常快进推送原分支，不改写历史、不强推；PR #90 对 main 保持 BEHIND（如实登记，未 rebase）。

## 最终 head 绑定

（由修订提交回填）

```text
最终完整 head：8b6eb00fa43745f151b41d82b770f41b349a33a1
最终提交对象 SHA256：c3f34a1ab2a39eb70aab2ddc6bb9efcd314e0647b6afe31bdefdb92b2dfcf945
```

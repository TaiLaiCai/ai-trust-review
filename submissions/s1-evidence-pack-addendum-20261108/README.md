# S1 补证包 · 第二批(addendum)入库候选

组装:tlc(Claude Code + GLM,子代理×2 + 终验);合流生产方:apo。本目录不主张 S1 闭合。历史私下 8/8 与任何 16/16 口号都不是本候选的验证结果。独立复跑须绑定最终 head，由验收者另行完成。

## 入库 SHA 与历史登记 SHA

- `sample_fixed.json` 仍是现有多行入库字节，没有改回历史源，也没有把内存重排写回。入库 SHA `79e0d15f5a5729b4fe8afb1b7376d8352d7f4ca08b8534c40faa4d47827df099`（162 字节，17 行）。历史登记 SHA `094e5186e657456fdf58c4198b07949237c9370128d6224b9aa165dd6963ac16`。两者不同。本树没有历史源文件，历史源字节 **NOT_TESTED**。
- 未写回的内存重排：`json.dumps(obj, ensure_ascii=False, separators=(", ", ": ")) + "\n"` 的 SHA 等于上述登记值。这只证明一种重排与登记值相同，该字节不是本树中的历史原件。
- 差异是格式重排，不是路径脱敏。`merge-manifest.json` 中该条 note，以及 `replay-kit-manifest.json` 里 `sample_fixed.json` 的 `sha256_stored` 与 `registered_value`，按此区分。
- 其余已入库 replay-kit 文件是否与各自登记值相同，以 `merge-manifest.json` 逐条 `sha256` / `source_sha256` 为准。不能把整个 `replay-kit/` 说成与 11-02 历史登记逐字节一致。

## 受限正文

- `replay-kit-manifest.json` 的 `files[4]`（`status_input.json`）`flag` 只保留缺失说明，不含受限输入正文。
- 公开提交 `21c44e16ba356ea0dc6c8efcd34b3599783ffc04` 与 `ad33676eb0a64cb6a704747bb55e938a2ef98d58` 的旧 `flag` 仍在 git 历史中。本候选不改写历史，不声称已经从历史提交移除。历史暴露范围未解决。

## 公开复跑边界

- 历史私下 8/8 记在 `replay-kit-manifest.json` 的 `replay_result`，本环境 **NOT_TESTED**，不是验证。
- `status_input.json` 不在本候选中，不生成、不倒填。地图 T2 是 `python3 status_tool.py --file status_input.json`，文件缺失则不能按地图执行。地图 T3 以 `status_input.json` 为 stdin，文件缺失则不能提供该 stdin。`replay-kit/alt-inputs/` 不能顶替。
- 公开子集里，命令和输入都在本树的步骤是 T1、T4、T5、T6、TP、PREFLIGHT-LOCAL。T1 的文件输入测试按 JSON 解析入库的多行 `sample_fixed.json`。PREFLIGHT 只检查四个文件名存在，不校验 SHA。TP 使用临时文件，不读取入库 `sample_fixed.json` 字节。
- `A2-originals/` 16 个日志的入库 SHA 可对本树重算。与私有原件是否逐字节相同，本环境 **NOT_TESTED**。

## 其他

- `hash-mappings.json`：核本树脱敏文件时，`desensitized_sha256` 与 `stored_sha256` 必须等于该文件实测 SHA。`original_sha256` 是历史原件登记，原件不在本树时为 **NOT_TESTED**。`feature-map.desensitized.json` 实测是 `38b967524298caff8b611a4d980da339cd5828ef458fedb4ff41e1590c0bf803`。旧登记 `dacd1f9a0a754c020d935d3754cd346f4553932187dac413ac558c62f3f9700b` 留在 `historical_registered_sha256`，与 `merge-manifest.json` 的 `source_sha256` 相同，不是当前文件。
- `B-originals-hashlist.txt` 不含自身。整体摘要 `d4eafc8d714023d3c171fff1c4b0c859c3210deb648b77b8535d3bcbe6d72ed6` 是对本树该文件的实测。清单点名的 B 原件不在本树，**NOT_TESTED**。
- `d3-summary.md` 只保留检索哈希与脱敏摘要，全文不入库。
- 排除未入：`authorized-only/`、d3 全文、`status_input.json`。
- `merge-manifest.json` 的 `hash_scope` 说明入库 `sha256` 不算清单自身，避免自引用循环。
- 防回归脚本：`check_addendum_boundaries.py`。它不进入 merge-manifest 的 entries。

#6 中的原库实测与回执不是本候选新做的验证。

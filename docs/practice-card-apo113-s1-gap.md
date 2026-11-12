# 练习卡 · APO-113 S1-01～08 公开证据差距表（只读盘点）

## 目标

对照 origin/main `cad687ea95e6e6fc03fdcc15fa8fe8f4f4c3c607`，逐项盘点 S1-01～S1-08 公开证据现状，交付可复核差距表（`docs/reviews/2026-11-12-s1-gap-table.md`）。不裁定 S1 通过，不开「S1 已通过」PR。

## 输入

- main：`cad687ea95e6e6fc03fdcc15fa8fe8f4f4c3c607`（2026-11-12 fetch 确认未移动）。
- `submissions/s1-evidence-pack-20261107/`（含 repo-evidence/ 与 A/B/C/D 脱敏件目录）。
- `submissions/s1-evidence-pack-addendum-20261108/`。
- `docs/reviews/2026-11-02-worker-stage2-pilot.md`、`docs/standards/01-阶段1-深度介入.md`。
- 本地未推送分支 APO-76-s1、APO-89-s1-hash-ref（未合入 main，无 PR）。

## 验收项

1. S1-01～08 每项含：先导结论、公开证据指针、是否仍依赖 gap-list 私有项、建议下一步。
2. 特别核验 S1-08 / 阻碍 (b) SHA 冲突与 S1-07 过度概括更正是否仍影响放行。
3. 明确一句当前能否进入 S2-01（预期为否）。
4. 验证「仓库可组装 0 项关闭证据」在当前 main 是否仍成立，若被后来公开材料改变则给出路径、SHA、理由。

## 轮次预算

| 段 | 轮次 |
|---|---|
| 准备 | 1 |
| 读上下文 | 4 |
| 实现 | 3 |
| 验证与修正 | 2 |
| 提交 | 1 |
| 合计 | 11 |
| 预算 | 12 |

## 文件上限

新增 2 个文档文件（练习卡本卡 + 差距表），不改其他文件。

## 完整上下文

主人裁定（Oki 代办，t509u，2026-11-12 13:03 评论区确认）：排在 APO-108、APO-111 之后做；只读盘点；不把 NOT_TESTED 写成 PASS；完成后交 APO-114 交叉复核。收件人检查与约定检查均通过（本工作区为执行工作树，任务指派给执行·Pi）。

## 回执格式

见 AGENTS.md：完整命令、cwd、stdout/stderr、退出码、main SHA、差距表位置、未测项。

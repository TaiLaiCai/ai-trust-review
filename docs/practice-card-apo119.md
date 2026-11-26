# 练习卡 · APO-119【修订】PR #82 处理 Superagent P2 与 Codex P1

## 目标

在原分支 `APO-115-ci-review-independence-ruleset` 上追加最小修订并推新 head：以平台认证来源（GitHub PR Review API）作为非作者审查的身份与 head 绑定证据，代码层处理 Superagent P2（`runner.account` 作者可自写、无回执时作业仍绿）与 Codex P1（树内回执自身过期）。不新开 PR、不合并、不改 ruleset、不自审。

## 输入

- 任务单 APO-119 描述（Superagent P2 / Codex P1 原文）。
- PR #82 当前 head `4bd6e24f8a63bb68a4311050465a767434760aa1` 上的评论（cursor[bot] 预审、Pi APO-117 回执、Hermes APO-116 审查）。
- capabilities/review_independence/{check.py,README.md,tests,fixtures}、.github/workflows/ci.yml、AGENTS.md、docs/pr-prereview.md（均已读）。

## 验收项（公开）

1. 无可信审查证据（空 reviews / 无 APPROVED / 全 stale）→ 退出 1，输出明示 fail-closed（NOT_TESTED 不写成 PASS）。
2. PR 作者自己的 APPROVED 回执不算数（平台来源里的自审也红）。
3. 合法非作者、最新一次 review 为 APPROVED 且 `commit_id` == 当前 PR head → 退出 0。
4. 原有 `check` 子命令红/绿契约不变：自审→1、过期 head→1、合法→0、用法错→2。
5. 上述每条有撤去修正会红的测试；`python3 -m unittest discover -s capabilities/review_independence/tests -v` 全绿。
6. ci.yml `review-independence` 作业在 pull_request 事件下实拉 PR reviews 并跑新子命令；docs/reviews/independence/ 回执降级为补充证据（空目录不再是作业的放行来源）。
7. 新 head 推到同一 PR；GitHub 上新 head 的 Superagent Security Scan 为 SUCCESS（读回）。

## 轮次预算

| 段 | 轮次 |
|---|---|
| 准备 | 1 |
| 读上下文 | 2 |
| 实现 | 3 |
| 验证与修正 | 3 |
| 提交 | 1 |
| 合计 | 10 |
| 预算 | 12 |

## 文件上限

8（check.py、tests、fixtures×~5、ci.yml、README、feature-map、练习卡、主 README，超出即缩小范围）。

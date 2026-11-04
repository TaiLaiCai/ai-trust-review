# 信任审查 PR 预审

本文件记载 Cursor Automation「信任审查 PR 预审」的仓库侧约定。它在 Cursor 云端运行。本仓库没有对应的 GitHub Actions workflow，也没有自动化配置文件。本页不改变任何 Bot 的等级或权限，评论也不构成合并批准。

本次入库没有从 Cursor 自动化配置接口导出原文。下面是写入本仓库的约定。

## 触发

Pull Request 的 `opened`。任何人打开的 PR 都触发。

## 运行与发言

- 运行位置：Cursor 云端。
- 发言账号：`cursor[bot]`。
- 评论语言：中文。

## 工具

允许使用的工具只有：

- Memories
- Comment on Pull Request

不允许 PR Approval。预审没有批准权，也不能合并。

## 结论

每条预审只给出三档之一：

| 结论 | 它表示的建议 |
|---|---|
| 建议合并 | 预审没有指出合入前必须先改的问题 |
| 需修改 | 预审认为合入前要改 |
| 阻塞 | 预审认为当前不能合入 |

三档都是评论里的建议。评论不能把 `NOT_TESTED` 改成 PASS，也不能代替另一主体按当前 head 做的独立复跑。

## 合并仍要同时满足的三件事

这条自动化不执行合并。[AGENTS.md](../AGENTS.md) 写明不自动合并。要合并，下面三件同时成立：

1. 规则集 `main` 的四项必需状态检查全绿：`repository-contracts`、`capability-tests`、`event-gate`、`loop-history-v2`。这四项在 [ci.yml](../.github/workflows/ci.yml) 里是并列作业。2026-11-04 的只读读回见 [README](../README.md)「代码侧」一节：四项都在规则集 `26351164` 的 `required_status_checks` 中，`integration_id` 为 `15368`。
2. 本预审的结论是「建议合并」。
3. 总工程师核对。

第 2 项和第 3 项是本仓库的合并约定。同一次规则集读回里，`required_approving_review_count` 为 0，预审评论不是 status check。经典分支保护端点在那次查询中返回 403，见 README；本文件不把没读到的经典保护写成已经确认的额外门槛。

「总工程师」与仓库记录里的批准人「主人」是否为同一主体，README 仍记**待确认**。本文件不另造身份。

## 不在本文件里的事

本文件不写保留判据、隐藏挑战或参考答案。它不修改 `capabilities/`、`control/`、fixtures、判据或 workflow。

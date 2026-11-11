# 替代 PR 的关闭流程

适用于同一仓库内已有后继 PR、需要关闭旧 PR 的情况。每组替代关系单独核验，多组可以放进同一张 Paperclip 确认卡。

| 步骤 | 负责人 | 证据与完成条件 |
| --- | --- | --- |
| 1. 核对替代关系 | 核对者 | 从 GitHub 读取旧 PR 和后继 PR 的状态、完整 head SHA 和链接。后继 PR 须明确指向旧 PR，并记录其起点 SHA。核对旧 PR 当前 head 等于该起点，确认后续审查有明确去处。 |
| 2. 批准关闭 | 维护者 | 一张确认卡列出仓库、两侧 PR 和完整 head SHA、拟发布的评论，以及「留言并关闭」的范围。保留批准记录链接。 |
| 3. 执行写入 | 有仓库写权限的执行者 | 重新读取两侧 PR。状态、head 或替代说明发生变化时暂停并重新核对。先给旧 PR 留言并确认评论链接，再关闭旧 PR。保留分支。 |
| 4. 读回结果 | 复核者 | 从 GitHub 读回评论正文、评论链接、旧 PR 的关闭状态和时间，以及后继 PR 的当前状态。把结果写回确认卡或关联任务。 |

GitHub CLI 可用 `gh pr view <编号> --repo <仓库> --json state,headRefOid,body` 核对输入。执行时用 `gh pr comment <旧编号> --repo <仓库> --body-file <评论文件>`，再用 `gh pr close <旧编号> --repo <仓库>`。读回用 `gh pr view <旧编号> --repo <仓库> --json state,closedAt,headRefOid,comments`。重试前先读回既有评论与状态，避免重复留言。执行失败时记录已成功的步骤及错误，按原批准范围恢复。

关闭旧 PR 只记录替代关系。后继 PR 的预审、CI、合并和阶段裁定仍走各自的门禁。

## 实例

2026-11-11，维护者在对话中一次批准以下两组留言与关闭。执行后从 GitHub 读回，两条旧 PR 均为 `CLOSED`，评论包含对应旧 head。

| 旧 PR | 后继 PR | 核对的旧 head | 关闭时间（北京时间） | 回执 |
| --- | --- | --- | --- | --- |
| #73 | #76 | `2cc437c417f79cab7ef5179ddf156f656440943b` | 18:05:25 | [替代说明](https://github.com/TaiLaiCai/ai-trust-review/pull/73#issuecomment-6792939442) |
| #71 | #78 | `6f3d594fea65525303ad61b0668850046cf29dd7` | 18:05:31 | [替代说明](https://github.com/TaiLaiCai/ai-trust-review/pull/71#issuecomment-6792941668) |

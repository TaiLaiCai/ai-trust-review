# 预审裁决格式

本文件规定一条预审评论怎么写。它供 [pr-prereview.md](pr-prereview.md) 引用。评论仍是建议：不能批准，不能合并，不能把 `NOT_TESTED` 写成 PASS。本文件不写保留判据、隐藏挑战或参考答案。

2026-11-04 读取的公开原文：

- 裁决格式：[verdict-format.md](https://github.com/poteto/noodle/blob/main/.agents/skills/adversarial-review/references/verdict-format.md)
- 审查视角：[reviewer-lenses.md](https://github.com/poteto/noodle/blob/main/.agents/skills/adversarial-review/references/reviewer-lenses.md)
- 原则目录：[brain/principles](https://github.com/poteto/brainmaxxing/tree/main/brain/principles)

[poteto/noodle](https://github.com/poteto/noodle) 与 [poteto/brainmaxxing](https://github.com/poteto/brainmaxxing) 的许可证都是 MIT，版权声明都是 Copyright (c) 2026 Lauren Tan。许可证原文：[noodle/LICENSE](https://github.com/poteto/noodle/blob/main/LICENSE)、[brainmaxxing/LICENSE](https://github.com/poteto/brainmaxxing/blob/main/LICENSE)。两份 LICENSE 在当天 `main` 上的 blob SHA 都是 `6b5400237fdf6545be0b8fae370d6f2fcff8fb25`。上游以后改字，以链接上的文件为准。下面是本仓库的写法，不是那两份原文的副本。

## 三档与上游裁决

预审结论只用这三个中文词。它们与上游裁决词一一对应：

| 本仓库结论 | 上游裁决 |
|---|---|
| 建议合并 | PASS |
| 需修改 | CONTESTED |
| 阻塞 | REJECT |

上游 `verdict-format.md` 当天写明的判定是：

- PASS：没有高严重级别发现。
- CONTESTED：有高严重级别发现，但审查者对它们意见不一致。
- REJECT：有高严重级别发现，且审查者意见一致。

多名审查者按该文件取舍时：没有高严重级别发现，结论为建议合并；有高严重级别发现且意见不一致，结论为需修改；有高严重级别发现且意见一致，结论为阻塞。中、低严重级别发现不单独把 PASS 改成 CONTESTED 或 REJECT。

上游这段判定写的是多名审查者之间是否一致。公开技能按改动规模使用一个到三个视角，视角定义在 `reviewer-lenses.md`。本仓库已经入库的预审是一条 `cursor[bot]` 评论，见 [pr-prereview.md](pr-prereview.md)。一条评论没有第二名审查者，当天的公开原文也没有为这种情况另写判定。单条评论选用三档时，仍用该文件已写的建议：没有指出合入前必须先改的问题、认为合入前要改、认为当前不能合入。本文件不把单条评论记成多名审查者已经达成一致，或已经出现分歧。

## 评论顺序

一条评论按这个顺序写：

1. 意图：作者要达成什么。审查问的是这次改动有没有把这个意图做好。
2. 结论：上面三档之一，再加一行摘要。这一节写中文词，不以 `VERDICT:` 开头。
3. 发现：从高到低编号。可以没有。
4. 做得好的地方：审查者确认没有问题的点，一条到三条。一条都没有时写「无」。
5. 主审判断：对每条发现写「接受」或「拒绝」，附一行理由。上游写明审查者采取对抗立场，不是每条发现都要改。没有发现时写「无」。
6. 机器可读裁决行：全文最后单独一行。

## 每条发现

每条发现写清下面五项。严重级别只用 `高`、`中`、`低`，对应上游的 high、medium、low。

- 严重级别：`高`、`中` 或 `低`
- 位置：`文件:行号`。跨行时写 `文件:起始行-结束行`
- 审查视角：提出该发现的视角。公开文件写了三个，每个审查者只用其中一个：`Architect`（结构是否服务于写明的目标）、`Skeptic`（正确性、完整性、以及未经证明的判断）、`Minimalist`（能否删掉、是不是在解还没有的问题）
- 对应原则：`brain/principles` 里已有的原则文件名，例如 `prove-it-works`。本仓库用来做交付自检的五条见 [self-check-principles.md](self-check-principles.md)。不发明目录里没有的原则名
- 建议：可以执行的动作

## 机器可读行

全文只有一行以 `VERDICT:` 开头，放在评论最后，单独成行。行内是三档之一，不含竖线：

```text
VERDICT: 建议合并
```

另两档写成 `VERDICT: 需修改` 或 `VERDICT: 阻塞`。规格里的 `VERDICT: 建议合并|需修改|阻塞` 表示三选一；竖线不是裁决行里的字符。

[../scripts/parse_verdict.py](../scripts/parse_verdict.py) 从一段评论文本里抽出这一行。标准输出只有该中文词。没有以 `VERDICT:` 开头的行、有多行、或唯一一行的值不是这三档之一，进程退出码为 1，标准错误分别是 `error: no verdict line`、`error: multiple verdict lines`、`error: invalid verdict`。用法错误退出码为 2。该脚本只提取标签，不判定能否合并。

下面是一份与「没有高严重级别发现则建议合并」一致的空白例子。其中的「待填写」不是某次预审的结论。

```text
## 意图
待填写

## 结论
建议合并
待填写一行摘要

## 发现
无。

## 做得好的地方
待填写

## 主审判断
无。

VERDICT: 建议合并
```

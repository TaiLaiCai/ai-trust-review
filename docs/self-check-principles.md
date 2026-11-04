# 交付自检与公开原则

本文件把五条公开原则收成交付前可以核对的自检项。交付时仍要交出 [AGENTS.md](../AGENTS.md)、[PR 模板](../.github/pull_request_template.md) 和 [review_readonly](../capabilities/review_readonly/README.md) 已经写明的字段。审查门槛、等级和权限仍以仓库里已有的文件为准。

五条都在 [brain/principles](https://github.com/poteto/brainmaxxing/tree/main/brain/principles)。2026-11-04 读取的是该目录 `main` 上的文件。[poteto/brainmaxxing](https://github.com/poteto/brainmaxxing) 的许可证是 MIT，版权声明是 Copyright (c) 2026 Lauren Tan，原文在 [LICENSE](https://github.com/poteto/brainmaxxing/blob/main/LICENSE)。当天该 LICENSE 的 blob SHA 是 `6b5400237fdf6545be0b8fae370d6f2fcff8fb25`。下面每条用本仓库的话复述当天读到的做法。上游以后改字，以链接上的文件为准。

## 用真实对象证明

自检：跑实际路径，回执贴完整命令和完整输出。核对 diff、文件字节或运行行为这些产物。编译通过、文件新旧、缓存截图、执行者自己的「已通过」，都不算这条自检完成。

原则：`prove-it-works`

上游：[prove-it-works.md](https://github.com/poteto/brainmaxxing/blob/main/brain/principles/prove-it-works.md)

许可证：MIT，Copyright (c) 2026 Lauren Tan，[LICENSE](https://github.com/poteto/brainmaxxing/blob/main/LICENSE)。

## 先复现，再修根因

自检：先复现失败，再改。复现不了，就不声称已经修好。同一模式搜一遍，不只改眼前一处。不靠多加一层判断把报错压掉。卡住时读实际错误。重启后才出现的失败，先检查残留状态：配置、缓存、锁和已经写下的状态。

原则：`fix-root-causes`

上游：[fix-root-causes.md](https://github.com/poteto/brainmaxxing/blob/main/brain/principles/fix-root-causes.md)

许可证：MIT，Copyright (c) 2026 Lauren Tan，[LICENSE](https://github.com/poteto/brainmaxxing/blob/main/LICENSE)。

## 把反复出现的纠正做成结构

自检：同一条纠正第二次出现时，做成检查、测试或脚本。只回答「记住了」不算记下。记在笔记里、却没有落到该执行的那一层，这条自检也不算完成。本仓库已经公开的结构是收件人检查、未定义约定检查和交付前字节对照，见 [README](../README.md) 的「闭环训练」。这里只把它们当作已有例子，不把它们写成新的成绩。

原则：`encode-lessons-in-structure`

上游：[encode-lessons-in-structure.md](https://github.com/poteto/brainmaxxing/blob/main/brain/principles/encode-lessons-in-structure.md)

许可证：MIT，Copyright (c) 2026 Lauren Tan，[LICENSE](https://github.com/poteto/brainmaxxing/blob/main/LICENSE)。

## 先减再加

自检：先删掉完成本目标所不需要的部分，再加新的。没有第二个具体用例的抽象或配置，不放进这次改动。没有新内容的引用直接删去。

原则：`subtract-before-you-add`

上游：[subtract-before-you-add.md](https://github.com/poteto/brainmaxxing/blob/main/brain/principles/subtract-before-you-add.md)

许可证：MIT，Copyright (c) 2026 Lauren Tan，[LICENSE](https://github.com/poteto/brainmaxxing/blob/main/LICENSE)。

## 派发前写预算和上限

自检：派发前写好轮次预算和文件上限，格式见 [practice-card-template.md](practice-card-template.md)。五段（准备、读上下文、实现、验证与修正、提交）之和超过预算，就缩小范围。文件数超过该卡写明的上限，就拆开。上下文一次给全。预算用尽前，先提交已经通过的那一部分。

原则：`cost-aware-delegation`

上游：[cost-aware-delegation.md](https://github.com/poteto/brainmaxxing/blob/main/brain/principles/cost-aware-delegation.md)

许可证：MIT，Copyright (c) 2026 Lauren Tan，[LICENSE](https://github.com/poteto/brainmaxxing/blob/main/LICENSE)。

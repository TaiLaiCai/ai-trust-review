# 练习卡 · APO-4 C3 独立维护原型阻断反例

按 [practice-card-template.md](practice-card-template.md) 填写。收件人：执行·Pi（Paperclip 派单，Issue APO-4，harness 已 checkout）。

## 目标

新增原子能力 `capabilities/maintenance_prototype` v1：只读校验「独立维护原型」文档——恰好四项阻断反例（id 冻结为 author-role-spoof、outer-pass-inner-fail、cross-missing-evidence、unasserted-promotion）与后续事故，红绿两端回执齐全且红端非零、绿端为零；保留集放独立受控仓库并做边界检查（保留集仓库不得在本仓库内、仓库树内不得有 retention 目录）。

## 输入

仓库 main@acde4f6、docs/ROADMAP.md 第 4 项、docs/standards/07-实测案例与反例索引.md、capabilities/ 现有五能力与 CI `capability-tests` 自动发现约定、docs/practice-card-template.md。

## 验收项

- `python3 capabilities/maintenance_prototype/check.py capabilities/maintenance_prototype/example/prototype.json` 退出码 0，输出 verdict=PASS。
- `python3 -m unittest discover -s capabilities/maintenance_prototype/tests -v` 全绿，含红端真实失败、绿端真实通过与字节摘要一致的复跑断言。
- 契约负例（非四项、红端零退出、绿端非零、未知字段、重复键、坏摘要、相对保留集路径）退出码 2；保留集指向本仓库内路径退出码 1。
- 不改 control/、CI 工作流、题库与验收期望值。

## 轮次预算

| 段 | 轮次 |
|---|---|
| 准备 | 1 |
| 读上下文 | 3 |
| 实现 | 5 |
| 验证与修正 | 3 |
| 提交 | 2 |
| 合计 | 14 |
| 预算 | 14 |

## 文件上限

8（check.py、README.md、feature-map.json、example/prototype.json、example/cases.py、tests/test_check.py、capabilities/README.md 表行、本卡）。实际新增 7 + 修改 1。

## 完整上下文

四项阻断反例取自 docs/standards/07-实测案例与反例索引.md 前四行；「后续事故另记 revision、原失败不删除」同源。保留集边界对应该文档「原始回执与保留挑战存于受控证据库，不随代码提交」与 ROADMAP 设定「保留题库不得进入工作 Agent 的执行环境」。能力目录会被 CI `capability-tests` 作业自动发现执行。仓库原则：工具只读、不执行材料中的命令清单、NOT_TESTED 不转 PASS、同账号自测不能自签验收。

## 回执格式

见任务回评：完整命令、stdout/stderr、退出码、证据 SHA256、NOT_TESTED 项。

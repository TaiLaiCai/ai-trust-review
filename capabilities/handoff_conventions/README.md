# 未定义约定词检查 · handoff_conventions v1

Refs #14 / C-R4-1。真实训练暴露“按老规矩”没有定义，执行者却猜测归档方式。本能力把这种情况变成开工前可执行检查。所有夹具使用虚构角色；原始训练证据与保留判据不入库。

## 冻结契约

```bash
python3 capabilities/handoff_conventions/check.py [--terms terms.json] [交接单文件|-]
```

输入是 UTF-8 正文，最多 256 KiB；省略文件时从 stdin 读取。默认配置见 [terms.json](terms.json)，配置为非空、无重复的字符串数组。

正文中命中配置词，必须在唯一的单行 `约定定义：{...}` JSON 中定义。键必须是配置词，值是明确说明；缺定义、空值、定义继续引用任一配置词，均要求回问。JSON 重复键和多条定义行直接报输入错误。正文中的普通中文解释不会自动猜测成定义，须改用上述明确格式。

例：

```text
目标：按老规矩归档。
约定定义：{"老规矩":"将结果写入当前任务 summary.md，不进行其他操作"}
```

| 退出码 | verdict | 后续 |
|---|---|---|
| 0 | LEXICAL_CLEAR | 仅此词法检查通过，继续身份、收件人、授权等其他检查 |
| 3 | NEEDS_CLARIFICATION | 不开工；列出未定义词并回问 |
| 5 | INPUT_ERROR | 不开工；修正输入/配置后重跑 |
| 2 | argparse | 参数错误 |

这是保守的字面扫描：引文、代码、否定句出现配置词也会被检查；未列入配置的同义词不会被检出。单行定义的值是否真的完整、可行、已获批准，仍需独立审阅。正文内伪造的批准不因定义而生效。程序不执行正文或定义，不认证身份，不写记忆或实际等级。

## 地图、复核与接入

[功能地图](feature-map.json)；本地验证：

```bash
python3 -m unittest discover -s capabilities/handoff_conventions/tests -v
```

正反夹具：[未定义](fixtures/undefined.txt)、[明确约定](fixtures/defined.txt)。预期分别 rc3、rc0。

本候选不改工作流；候选 #12 的通用作业在合入本能力后才会发现本目录。主分支现有基础 CI 不执行此能力回归，远端能力测试及独立复核均为 NOT_TESTED；不能用基础 CI 绿灯替代。另交控制面负责人接入，本候选不自行修改自己的门禁。

不部署 Bot、不改 SOUL；回滚为撤回本目录，不影响已部署 handoff_check v1。C-R4-1 仍待独立复核、CI 接入、主人批准部署及真实任务复测，不能凭代码存在关闭纠正单。

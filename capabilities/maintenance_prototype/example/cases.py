#!/usr/bin/env python3
"""公开夹具：四项阻断反例的最小可复跑替身。

用法：cases.py red|green <index 0..3> [incident]
red：模拟「该反例曾真实发生并被阻断前的失败形态」，打印一行说明到 stderr，退出码非零。
green：模拟「修复后正确形态」，打印一行 JSON 到 stdout，退出码 0。
输出字节稳定（无时间戳、无随机），供原型文档记录 stdout/stderr 的 SHA256。
"""
import json
import sys

HAZARDS = [
    "author-role-spoof",        # 正文 author_role 冒充批准人
    "outer-pass-inner-fail",    # 外层通过、内部 fail 仍晋级
    "cross-missing-evidence",   # 两次通过跨缺证据继续连胜
    "unasserted-promotion",     # 自测未真实断言晋级却报成功
]


def main(argv):
    if len(argv) not in (3, 4) or argv[1] not in ("red", "green"):
        print("usage: cases.py red|green <0..3> [incident]", file=sys.stderr)
        return 2
    mode, idx = argv[1], argv[2]
    if not idx.isdigit() or int(idx) >= len(HAZARDS):
        print("index out of range", file=sys.stderr)
        return 2
    hazard = HAZARDS[int(idx)]
    if mode == "red":
        print("BLOCKED-COUNTEREXAMPLE %s: acceptance gate rejected this failure form" % hazard,
              file=sys.stderr)
        return 1
    print(json.dumps({"hazard": hazard, "revision": argv[3] if len(argv) == 4 else "r1",
                      "asserted": True, "exit": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

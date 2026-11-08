#!/usr/bin/env python3
"""C-WORKER-FIXTURE-001 检测器：检查本脚本所在目录四项 fixture 齐备。

齐备(status_tool.py, test_status_tool.py, sample_fixed.json, README.md) → exit 0
任一缺失或不可读 → stderr 列出缺失项, exit 3
stdlib only；不联网、不执行任何清单命令。
"""
import sys
from pathlib import Path

REQUIRED = ("status_tool.py", "test_status_tool.py", "sample_fixed.json", "README.md")


def main(directory=None):
    base = Path(directory) if directory else Path(__file__).resolve().parent
    missing = [name for name in REQUIRED if not (base / name).is_file()]
    if missing:
        print(f"missing fixtures: {', '.join(missing)}", file=sys.stderr)
        return 3
    print("all fixtures present:", ", ".join(REQUIRED))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))

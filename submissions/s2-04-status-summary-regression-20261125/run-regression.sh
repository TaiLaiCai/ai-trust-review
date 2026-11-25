#!/bin/sh
# S2-04 状态汇总回执解析纠正｜合成回归可持续运行入口（候选）
#
# 用途：在受控本机目录，用仅含合成数据的回归脚本，对照「旧原版」与「已批修订版」
# 两个 session_gate.py 解析器字节。预期：
#   - 旧原版（a48b006a…）：无进度对照接受；带前置常规进度文本 → 退出 1（拒绝）
#   - 已批修订版（899dcd64…）：两种输入均接受 → 退出 0
#
# 私有解析器源码不入公开仓库。取件目录默认为本机持久目录：
#   ~/.paperclip/apo5-s204-source.Wo17ww/
# 可用环境变量 S204_SOURCE_DIR 覆盖。任一字节 SHA256 不符即停止，不重算、不补造。
#
# 退出码：0 = 全部符合预期；1 = 有任何不符合；2 = 取件入口缺口（目录或字节缺失）。
# 本脚本不调用真实模型、不读取私有业务数据、不访问网络。

set -u

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SRC_DIR=${S204_SOURCE_DIR:-"$HOME/.paperclip/apo5-s204-source.Wo17ww"}

OLD_SHA=a48b006ab9b5b37706a455119ac10571c69cf5de7491616de022924266ab640f
REVISED_SHA=899dcd647c688ef45f6f2df6854cc39c36283821519e51b39a9fb01e2a324ee5
TEST_SHA=aa6f0e2e60b71687ba11ca5ef5d9c22bad089e0c7d09c41f0201961e22c6f911

fail=0

check_sha() {
  path=$1
  want=$2
  if [ ! -f "$path" ]; then
    echo "ENTRY GAP: missing file $path" >&2
    exit 2
  fi
  got=$(shasum -a 256 "$path" | cut -d' ' -f1)
  if [ "$got" != "$want" ]; then
    echo "ENTRY GAP: sha256 mismatch for $path (got $got, want $want)" >&2
    exit 2
  fi
}

check_sha "$HERE/test_status_preamble.py" "$TEST_SHA"
check_sha "$SRC_DIR/old-session_gate.py" "$OLD_SHA"
check_sha "$SRC_DIR/revised-session_gate.py" "$REVISED_SHA"

run_case() {
  label=$1
  source=$2
  want_exit=$3
  echo "== $label"
  python3 -B "$HERE/test_status_preamble.py" "$source"
  got_exit=$?
  echo "exit=$got_exit (expected $want_exit)"
  if [ "$got_exit" != "$want_exit" ]; then
    fail=1
  fi
}

run_case "old-session_gate.py" "$SRC_DIR/old-session_gate.py" 1
run_case "revised-session_gate.py" "$SRC_DIR/revised-session_gate.py" 0

if [ "$fail" -eq 0 ]; then
  echo "RESULT: all expectations met (baseline accepted in both; old rejects preamble, revised accepts)"
  exit 0
fi
echo "RESULT: expectations NOT met" >&2
exit 1

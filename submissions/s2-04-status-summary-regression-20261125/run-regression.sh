#!/bin/sh
# S2-04 状态汇总回执解析纠正｜合成回归可持续运行入口（候选，APO-236 修订）
#
# 用途：在调用者显式传入的受控取件目录，用仅含合成数据的回归脚本，对照「旧原版」
# 与「已批修订版」两个 session_gate.py 解析器字节。预期：
#   - 旧原版（a48b006a…）：退出 1；stdout 逐字节等于
#     baseline: accepted
#     preamble: rejected (preflight acknowledgement differs)
#   - 已批修订版（899dcd64…）：退出 0；stdout 逐字节等于
#     baseline: accepted
#     preamble: accepted
#   - 两侧 stderr 必须为空；任一侧出现非预期 stdout 或 stderr，入口失败（退出 1）。
#     旧版 Python 基础设施异常（ traceback + 退出 1）同样不通过。
#
# 私有解析器源码不入公开仓库。取件目录必须由调用者显式通过 S204_SOURCE_DIR 传入，
# 取件字节与位置见 Paperclip APO-234 受控文档 exact-status-preamble-source-index。
# 任一字节 SHA256 不符即停止，不重算、不补造。
#
# 用法：
#   S204_SOURCE_DIR=<受控取件目录> sh run-regression.sh
#   sh run-regression.sh --selftest   # 纯合成自测：不访问任何取件原件或模型
#
# 退出码：0 = 全部符合预期；1 = 有任何不符合（含非预期 stdout/stderr）；
# 2 = 取件入口缺口（S204_SOURCE_DIR 未设置、目录或字节缺失）。
# 本脚本不调用真实模型、不读取私有业务数据、不访问网络。

set -u

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TEST_PY="$HERE/test_status_preamble.py"

OLD_SHA=a48b006ab9b5b37706a455119ac10571c69cf5de7491616de022924266ab640f
REVISED_SHA=899dcd647c688ef45f6f2df6854cc39c36283821519e51b39a9fb01e2a324ee5
TEST_SHA=aa6f0e2e60b71687ba11ca5ef5d9c22bad089e0c7d09c41f0201961e22c6f911

EXPECTED_OLD_STDOUT="baseline: accepted
preamble: rejected (preflight acknowledgement differs)"
EXPECTED_REVISED_STDOUT="baseline: accepted
preamble: accepted"

SELFTEST=0
if [ "${1:-}" = "--selftest" ]; then
  SELFTEST=1
fi

fail=0
WORK=$(mktemp -d 2>/dev/null) || exit 2
trap 'rm -rf "$WORK"' EXIT INT TERM

entry_gap() {
  echo "ENTRY GAP: $1" >&2
  exit 2
}

check_sha() {
  path=$1
  want=$2
  name=$3
  if [ ! -f "$path" ]; then
    entry_gap "missing file $name (pickup: see Paperclip APO-234 document exact-status-preamble-source-index)"
  fi
  digest_line=$(shasum -a 256 "$path" 2>/dev/null) || entry_gap "cannot read $name"
  got=${digest_line%% *}
  if [ "$got" != "$want" ]; then
    entry_gap "sha256 mismatch for $name (got $got, want $want)"
  fi
}

# run_case <label> <source> <want_exit> <want_stdout>
# 严格判定：退出码、stdout 逐字节、stderr 必须为空，三者全符才算符合。
run_case() {
  label=$1
  source=$2
  want_exit=$3
  want_stdout=$4
  out="$WORK/$label.out"
  err="$WORK/$label.err"
  expected="$WORK/$label.expected"
  printf '%s\n' "$want_stdout" > "$expected"
  python3 -B "$TEST_PY" "$source" > "$out" 2> "$err"
  got_exit=$?
  case_ok=1
  if [ "$got_exit" -ne "$want_exit" ]; then
    case_ok=0
  elif ! cmp -s "$out" "$expected"; then
    case_ok=0
  elif [ -s "$err" ]; then
    case_ok=0
  fi
  out_sha=$(shasum -a 256 "$out" | cut -d' ' -f1)
  err_sha=$(shasum -a 256 "$err" | cut -d' ' -f1)
  echo "== $label"
  echo "exit=$got_exit (expected $want_exit)"
  echo "stdout sha256: $out_sha"
  echo "stderr sha256: $err_sha (must be empty-file hash e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)"
  if [ "$case_ok" -eq 1 ]; then
    echo "case: OK"
  else
    echo "case: MISMATCH (exit code, stdout bytes, or stderr emptiness not as expected)" >&2
    fail=1
  fi
}

if [ "$SELFTEST" -eq 1 ]; then
  # ---- 纯合成自测：不读取取件目录、不访问模型，用 mock python3 驱动判定逻辑 ----
  MOCKBIN="$WORK/mockbin"
  MOCK="$MOCKBIN/python3"
  mkdir -p "$MOCKBIN"
  cat > "$MOCK" <<'MOCKEOF'
#!/bin/sh
cat "$MOCK_STDOUT"
cat "$MOCK_STDERR" >&2
exit "$MOCK_EXIT"
MOCKEOF
  chmod +x "$MOCK"
  PATH="$MOCKBIN:$PATH"
  export PATH
  STUB="$WORK/stub-source.py"
  echo "# synthetic stub, not a real parser" > "$STUB"

  st_fail=0

  # 每个自测用例：设置 mock 输出与退出码，直接调 run_case，断言 fail 标志变化
  selftest_case() {
    desc=$1
    expect_ok=$2
    label=$3
    want_exit=$4
    want_stdout=$5
    mock_out=$6
    mock_err=$7
    mock_exit=$8
    printf '%s\n' "$mock_out" > "$WORK/mock.out"
    printf '%s' "$mock_err" > "$WORK/mock.err"
    export MOCK_STDOUT="$WORK/mock.out" MOCK_STDERR="$WORK/mock.err" MOCK_EXIT="$mock_exit"
    fail=0
    run_case "$label" "$STUB" "$want_exit" "$want_stdout" > "$WORK/$label.report" 2>&1
    case_ok_now=1
    if [ "$fail" -ne 0 ]; then case_ok_now=0; fi
    if [ "$case_ok_now" -eq "$expect_ok" ]; then
      echo "selftest $desc: PASS"
    else
      echo "selftest $desc: FAIL (expected gate ok=$expect_ok)" >&2
      st_fail=1
    fi
  }

  # 1 正常路径：旧版语义（预期拒绝）
  selftest_case "normal-old" 1 "st-old" 1 "$EXPECTED_OLD_STDOUT" "$EXPECTED_OLD_STDOUT" "" 1
  # 2 正常路径：修订版语义（接受）
  selftest_case "normal-revised" 1 "st-revised" 0 "$EXPECTED_REVISED_STDOUT" "$EXPECTED_REVISED_STDOUT" "" 0
  # 3 非预期 stdout（多一行）
  selftest_case "unexpected-stdout" 0 "st-extra-stdout" 1 "$EXPECTED_OLD_STDOUT" "$EXPECTED_OLD_STDOUT
extra unexpected line" "" 1
  # 4 非预期 stderr（基础设施异常 traceback，退出 1）
  selftest_case "unexpected-stderr" 0 "st-stderr" 1 "$EXPECTED_OLD_STDOUT" "$EXPECTED_OLD_STDOUT" "Traceback (most recent call last):
  File \"test_status_preamble.py\", line 1, in <module>
RuntimeError: synthetic infrastructure failure" 1
  # 5 退出码不符（旧版语义却退出 0）
  selftest_case "wrong-exit-code" 0 "st-wrong-exit" 1 "$EXPECTED_OLD_STDOUT" "$EXPECTED_OLD_STDOUT" "" 0
  # 6 修订版语义却退出 1
  selftest_case "revised-wrong-exit" 0 "st-rev-wrong-exit" 0 "$EXPECTED_REVISED_STDOUT" "$EXPECTED_REVISED_STDOUT" "" 1

  # 7 取件缺失：显式空目录 → 入口退出 2
  EMPTY="$WORK/empty-src"
  mkdir -p "$EMPTY"
  if S204_SOURCE_DIR="$EMPTY" sh "$0" > "$WORK/missing.out" 2> "$WORK/missing.err"; then
    echo "selftest missing-pickup: FAIL (expected exit 2)" >&2
    st_fail=1
  else
    got_missing=$?
    if [ "$got_missing" -eq 2 ] && grep -q "ENTRY GAP: missing file old-session_gate.py" "$WORK/missing.err" && ! grep -Fq -- "$EMPTY" "$WORK/missing.err"; then
      echo "selftest missing-pickup: PASS"
    else
      echo "selftest missing-pickup: FAIL (exit $got_missing)" >&2
      st_fail=1
    fi
  fi
  # 8 S204_SOURCE_DIR 未设置 → 入口退出 2
  if env -u S204_SOURCE_DIR sh "$0" > "$WORK/unset.out" 2> "$WORK/unset.err"; then
    echo "selftest unset-source-dir: FAIL (expected exit 2)" >&2
    st_fail=1
  else
    got_unset=$?
    if [ "$got_unset" -eq 2 ] && grep -q "ENTRY GAP" "$WORK/unset.err"; then
      echo "selftest unset-source-dir: PASS"
    else
      echo "selftest unset-source-dir: FAIL (exit $got_unset)" >&2
      st_fail=1
    fi
  fi
  # 9 字节篡改：合成 stub 顶替取件 → 入口退出 2
  TAMPER="$WORK/tamper-src"
  mkdir -p "$TAMPER"
  cp "$STUB" "$TAMPER/old-session_gate.py"
  cp "$STUB" "$TAMPER/revised-session_gate.py"
  if S204_SOURCE_DIR="$TAMPER" sh "$0" > "$WORK/tamper.out" 2> "$WORK/tamper.err"; then
    echo "selftest tampered-bytes: FAIL (expected exit 2)" >&2
    st_fail=1
  else
    got_tamper=$?
    if [ "$got_tamper" -eq 2 ] && grep -q "ENTRY GAP: sha256 mismatch for old-session_gate.py" "$WORK/tamper.err" && ! grep -Fq -- "$TAMPER" "$WORK/tamper.err"; then
      echo "selftest tampered-bytes: PASS"
    else
      echo "selftest tampered-bytes: FAIL (exit $got_tamper)" >&2
      st_fail=1
    fi
  fi

  if [ "$st_fail" -eq 0 ]; then
    echo "SELFTEST RESULT: all 9 synthetic cases behaved as expected (no real pickup files or model access)"
    exit 0
  fi
  echo "SELFTEST RESULT: failures present" >&2
  exit 1
fi

# ---- 正常模式：取件目录必须由调用者显式传入 ----
if [ -z "${S204_SOURCE_DIR:-}" ]; then
  entry_gap "S204_SOURCE_DIR not set; pass the controlled pickup directory explicitly (see Paperclip APO-234 document exact-status-preamble-source-index)"
fi
SRC_DIR=$S204_SOURCE_DIR

check_sha "$TEST_PY" "$TEST_SHA" test_status_preamble.py
check_sha "$SRC_DIR/old-session_gate.py" "$OLD_SHA" old-session_gate.py
check_sha "$SRC_DIR/revised-session_gate.py" "$REVISED_SHA" revised-session_gate.py

run_case "old-session_gate.py" "$SRC_DIR/old-session_gate.py" 1 "$EXPECTED_OLD_STDOUT"
run_case "revised-session_gate.py" "$SRC_DIR/revised-session_gate.py" 0 "$EXPECTED_REVISED_STDOUT"

if [ "$fail" -eq 0 ]; then
  echo "RESULT: all expectations met (both versions accept the no-progress baseline; old exits 1 with the exact expected rejection output, revised exits 0 with the exact expected acceptance output; both stderr empty)"
  exit 0
fi
echo "RESULT: expectations NOT met" >&2
exit 1

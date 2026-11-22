#!/usr/bin/env bash
# 一条命令跑 xiaozhi-server 的单元测试：准备 libopus + data/.config.yaml + pytest。
#
# 用法：
#   bash scripts/run_tests.sh                  # 跑 tests/
#   bash scripts/run_tests.sh -k wakeup -v     # 追加的 pytest 参数原样透传
set -euo pipefail

cd "$(dirname "$0")/.."   # -> main/xiaozhi-server

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python

OPUS_DIR="${XIAOZHI_OPUS_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/xiaozhi-opus}"
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*|Windows*)
    if [ -f "$OPUS_DIR/opus.dll" ]; then
      NATIVE_OPUS_DIR="$(command -v cygpath >/dev/null 2>&1 && cygpath -w "$OPUS_DIR" || echo "$OPUS_DIR")"
      export PATH="$NATIVE_OPUS_DIR;$PATH"
    fi
    ;;
  *)
    ;;
esac

# 1) libopus（失败不阻断：缺库时只有 wakeup 相关用例会失败，conftest 有明确提示）
bash scripts/setup_libopus.sh || echo "[run_tests] 警告：libopus 未就绪，wakeup 音频用例预计失败"

# 2) 测试配置：config/logger.py 的 setup_logging 会读 data/.config.yaml
if [ ! -f data/.config.yaml ]; then
  printf '{}\n' > data/.config.yaml
  echo "[run_tests] 已创建临时 data/.config.yaml"
fi

# 3) 可选依赖缺失时跳过对应测试文件，避免 collection error 掩盖真实失败
IGNORES=()
if ! "$PY" -c "import cnlunar" >/dev/null 2>&1; then
  IGNORES+=(--ignore=tests/core/utils/test_current_time.py)
  echo "[run_tests] 未装 cnlunar，跳过 tests/core/utils/test_current_time.py"
fi
if ! "$PY" -c "import markitdown" >/dev/null 2>&1; then
  IGNORES+=(--ignore=tests/plugins_func/test_weather_news_plugins.py)
  echo "[run_tests] 未装 markitdown，跳过 tests/plugins_func/test_weather_news_plugins.py"
fi

# 默认 -q；调用方自己带了 -q / -v 就以调用方为准。
# pytest 的 -q 是累加的：脚本固定 -q 再叠加调用方的 -q 会变成 -qq，
# 而 -qq 会把最后那行 "143 passed, 5 skipped in Xs" 也吞掉，容易误判成没跑完。
HAS_VERBOSITY=0
for arg in "$@"; do
  case "$arg" in
    -q*|-v*|--quiet|--verbose) HAS_VERBOSITY=1 ;;
  esac
done
QUIET=()
[ "$HAS_VERBOSITY" -eq 0 ] && QUIET=(-q)

"$PY" -m pytest tests/ "${QUIET[@]+"${QUIET[@]}"}" "${IGNORES[@]+"${IGNORES[@]}"}" "$@"

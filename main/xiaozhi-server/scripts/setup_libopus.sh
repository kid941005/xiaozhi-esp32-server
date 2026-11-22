#!/usr/bin/env bash
# 为 xiaozhi-server 的单元测试准备 libopus（Opus 编解码）。
#
# 背景：opuslib_next 只是 ctypes 绑定（pip 装的是纯 Python 包），真正编解码靠系统的
# libopus 动态库。缺库时 tests/conftest.py 会把 Encoder/Decoder 换成抛错的桩，
# tests/core/handle/test_wakeup_response.py 的 5 个用例会失败（RuntimeError: libopus 没装）。
#
# 用法：
#   bash scripts/setup_libopus.sh            # 缺什么装什么，已就绪直接退出
#   bash scripts/setup_libopus.sh --force    # 即使可用也重装 opuslib_next
#
# 支持的平台：Linux(apt/dnf/pacman) / macOS(brew) / Windows(MSYS/Git Bash，用 PyAV 自带 dll)
set -euo pipefail

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "[setup-libopus] 找不到 python，请先安装 Python 3.10+"; exit 1; }

OPUSLIB_VERSION="1.3.1"
# Windows 上把 opus.dll 放这里（可用 XIAOZHI_OPUS_DIR 覆盖）
OPUS_DIR="${XIAOZHI_OPUS_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/xiaozhi-opus}"

say() { printf '[setup-libopus] %s\n' "$*"; }

# Windows：之前下载过 dll 的话先挂进 PATH，让"已就绪则跳过"能命中
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*|Windows*)
    if [ -f "$OPUS_DIR/opus.dll" ]; then
      NATIVE_OPUS_DIR="$(command -v cygpath >/dev/null 2>&1 && cygpath -w "$OPUS_DIR" || echo "$OPUS_DIR")"
      export PATH="$NATIVE_OPUS_DIR;$PATH"
    fi
    ;;
  *) ;;
esac

# 判定"能否真正编解码"，而不只是 import 成功
check_opus() {
  "$PY" - <<'PYEOF' >/dev/null 2>&1
import opuslib_next
enc = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)
# 16kHz / 20ms = 320 samples = 640 bytes PCM
enc.encode(b"\x00\x00" * 320, 320)
PYEOF
}

if [ "${1:-}" != "--force" ] && check_opus; then
  say "libopus 已可用，跳过安装"
  exit 0
fi

say "安装 Python 绑定 opuslib_next==${OPUSLIB_VERSION}"
"$PY" -m pip install --no-input ${PIP_BREAK_SYSTEM_PACKAGES:---break-system-packages} "opuslib_next==${OPUSLIB_VERSION}"

OS="$(uname -s 2>/dev/null || echo unknown)"
case "$OS" in
  MINGW*|MSYS*|CYGWIN*|Windows*)
    say "Windows：通过 PyAV wheel 取 libopus dll"
    "$PY" -m pip install --no-input ${PIP_BREAK_SYSTEM_PACKAGES:---break-system-packages} av
    mkdir -p "$OPUS_DIR"
    DLL_SRC="$("$PY" - <<'PYEOF'
import glob, os, sys
import av  # noqa: F401  PyAV wheel 自带 libopus
root = os.path.dirname(os.path.dirname(av.__file__))
hits = glob.glob(os.path.join(root, "av.libs", "*opus*.dll")) + glob.glob(os.path.join(root, "*opus*.dll"))
print(hits[0] if hits else "")
PYEOF
)"
    if [ -z "$DLL_SRC" ]; then
      say "在 PyAV 包里没找到 libopus dll，请手动下载 opus.dll 放到 $OPUS_DIR"
      exit 1
    fi
    cp -f "$DLL_SRC" "$OPUS_DIR/opus.dll"
    # opuslib_next/api/__init__.py 用 ctypes.util.find_library("opus") 找库，
    # Windows 上等价于"PATH 里有没有 opus.dll"。MSYS 的 /d/... 路径传不进原生进程，
    # 必须用 Windows 原生路径（下面用 cygpath 转换）。
    if command -v cygpath >/dev/null 2>&1; then
      NATIVE_OPUS_DIR="$(cygpath -w "$OPUS_DIR")"
    else
      NATIVE_OPUS_DIR="$OPUS_DIR"
    fi
    export PATH="$NATIVE_OPUS_DIR;$PATH"
    say "已放置：$OPUS_DIR/opus.dll"
    say "本次 shell 已临时加入 PATH；新开终端请先执行："
    printf '    export PATH="%s;$PATH"\n' "$NATIVE_OPUS_DIR"
    ;;
  Darwin)
    if command -v brew >/dev/null 2>&1; then
      say "macOS：brew install opus"
      brew list opus >/dev/null 2>&1 || brew install opus
    else
      say "未找到 brew，请手动安装 opus（例如 brew install opus）"
      exit 1
    fi
    ;;
  Linux)
    if command -v apt-get >/dev/null 2>&1; then
      say "Linux：apt-get install -y libopus0"
      (command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null && sudo apt-get install -y libopus0) || apt-get install -y libopus0 || true
    elif command -v dnf >/dev/null 2>&1; then
      say "Linux：dnf install -y opus"
      dnf install -y opus || true
    elif command -v pacman >/dev/null 2>&1; then
      say "Linux：pacman -S --noconfirm opus"
      pacman -S --noconfirm opus || true
    else
      say "未识别的包管理器，请手动安装 libopus（Debian: libopus0 / RHEL: opus）"
      exit 1
    fi
    ;;
  *)
    say "未识别的系统：$OS，请手动安装 libopus 后重跑"
    exit 1
    ;;
esac

if check_opus; then
  say "OK：libopus 已可用（$( "$PY" -c 'import ctypes.util;print(ctypes.util.find_library("opus"))' )）"
else
  say "仍不可用。Windows 上通常是 PATH 未生效，请按上面的 export 行设置后重试。"
  exit 1
fi

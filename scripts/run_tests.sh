#!/usr/bin/env bash
# 仓库统一测试入口：一条命令覆盖三个子项目（CI 与本地共用）。
#
# 用法：
#   bash scripts/run_tests.sh             # 依次跑 python / java / web
#   bash scripts/run_tests.sh python      # 只跑 xiaozhi-server（pytest）
#   bash scripts/run_tests.sh java        # 只跑 manager-api（mvn test + 集成测试守卫）
#   bash scripts/run_tests.sh web         # 只跑 manager-web（契约/单元测试 + 构建）
#   bash scripts/run_tests.sh python -k wakeup -v      # 额外参数透传给对应子项目脚本
#
# 各子项目脚本：
#   main/xiaozhi-server/scripts/run_tests.sh  （负责 libopus 与 data/.config.yaml 准备）
#   main/manager-api/scripts/run_tests.sh     （mvn test + check-integration-tests.sh）
#   main/manager-web/scripts/run_tests.sh     （npm test:contract / test:unit / build）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY_SCRIPT="$REPO_ROOT/main/xiaozhi-server/scripts/run_tests.sh"
JAVA_SCRIPT="$REPO_ROOT/main/manager-api/scripts/run_tests.sh"
WEB_SCRIPT="$REPO_ROOT/main/manager-web/scripts/run_tests.sh"

usage() {
  cat <<'EOF'
用法: bash scripts/run_tests.sh [python|java|web|all] [子项目脚本参数...]

  python, py   xiaozhi-server 的 pytest（自动准备 libopus 与 data/.config.yaml）
  java, api    manager-api 的 mvn test（含集成测试守卫，需 MySQL/Redis）
  web          manager-web 的契约测试 + 单元测试 + 生产构建
  all          依次执行以上三项（默认）
EOF
}

target="${1:-all}"
[ "$#" -gt 0 ] && shift

case "$target" in
  python|py)
    exec bash "$PY_SCRIPT" "$@"
    ;;
  java|api)
    exec bash "$JAVA_SCRIPT" "$@"
    ;;
  web)
    exec bash "$WEB_SCRIPT" "$@"
    ;;
  all)
    for part in python java web; do
      echo "===== $part ====="
      bash "$0" "$part"
    done
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "未知目标：$target" >&2
    usage >&2
    exit 2
    ;;
esac

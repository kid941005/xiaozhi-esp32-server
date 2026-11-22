#!/usr/bin/env bash
# manager-api 测试统一入口（CI 与本地共用）。
#
# 用法：
#   bash scripts/run_tests.sh                     # 全量 mvn test + 集成测试守卫
#   bash scripts/run_tests.sh -Dtest=XxxTest      # 额外参数原样透传 mvn
#   bash scripts/run_tests.sh --dry-run           # 只打印将执行的命令，不运行
#
# 环境变量：
#   MVN        mvn 可执行文件（默认 mvn；本机不在 PATH 时可指定绝对路径）
#   JAVA_HOME  交给 mvn 的 JDK
set -euo pipefail
cd "$(dirname "$0")/.."

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=1; shift; fi

MVN="${MVN:-mvn}"
if [ "$DRY_RUN" -eq 0 ] && ! command -v "$MVN" >/dev/null 2>&1 && [ ! -x "$MVN" ]; then
  echo "[api-tests] 找不到 mvn：$MVN（可用 MVN=/path/to/mvn 指定）" >&2
  exit 1
fi

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] %s\n' "$*"
  else
    printf '[api-tests] %s\n' "$*"
    "$@"
  fi
}

# 集成测试（DeviceTest / ModelConfigPersistenceTest / loginControllerTest）需要 MySQL 与 Redis，
# CI 里靠 job 的 services 提供；本地跑全量前请先准备好，或直接用 -Dtest=... 只跑单元测试。
run "$MVN" -B test -DskipTests=false -DfailIfNoTests=false "$@"

# 守卫：确认那三个集成测试真的跑了，避免门禁被静默跳过
if [ "$DRY_RUN" -eq 1 ]; then
  printf '[dry-run] bash scripts/check-integration-tests.sh\n'
else
  bash scripts/check-integration-tests.sh
fi

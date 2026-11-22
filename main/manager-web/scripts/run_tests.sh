#!/usr/bin/env bash
# manager-web 测试统一入口（CI 与本地共用）。
#
# 用法：
#   bash scripts/run_tests.sh              # 契约测试 + 单元测试 + 生产构建
#   SKIP_BUILD=1 bash scripts/run_tests.sh # 只跑测试，跳过构建（本地快速反馈）
#
# 环境变量：
#   SKIP_BUILD      1 = 不跑 npm run build
#   SKIP_INSTALL    1 = 即使没有 node_modules 也不自动 npm ci
#   NPM_REGISTRY    传给 npm ci 的 registry（默认走 npm 配置）
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d node_modules ] && [ "${SKIP_INSTALL:-0}" != "1" ]; then
  echo "[web-tests] 未找到 node_modules，先执行 npm ci"
  if [ -n "${NPM_REGISTRY:-}" ]; then
    npm ci --no-audit --no-fund --registry="$NPM_REGISTRY"
  else
    npm ci --no-audit --no-fund
  fi
fi

echo "[web-tests] npm run test:contract"
npm run test:contract

echo "[web-tests] npm run test:unit"
npm run test:unit

if [ "${SKIP_BUILD:-0}" != "1" ]; then
  echo "[web-tests] npm run build"
  npm run build
else
  echo "[web-tests] SKIP_BUILD=1，跳过构建"
fi

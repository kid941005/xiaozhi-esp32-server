#!/bin/bash
# 启动 Java 后端（docker 内监听 8003 端口），并以前台 Nginx 保持容器存活。
# 注意：环境变量缺失时不要把参数拼成 "--key=" 的空值，否则 Spring 会因类型转换失败
# 直接退出（例如 spring.data.redis.port 空串），而 Nginx 仍返回 200，
# 表现为「页面能打开、所有接口 502」的假健康状态。
set -u

JAVA_ARGS=(--server.port=8003)

append_opt() {
  local key="$1"
  local value="${2:-}"
  if [ -n "$value" ]; then
    JAVA_ARGS+=("${key}=${value}")
  fi
}

append_opt --spring.datasource.druid.url "${SPRING_DATASOURCE_DRUID_URL:-}"
append_opt --spring.datasource.druid.username "${SPRING_DATASOURCE_DRUID_USERNAME:-}"
append_opt --spring.datasource.druid.password "${SPRING_DATASOURCE_DRUID_PASSWORD:-}"
append_opt --spring.data.redis.host "${SPRING_DATA_REDIS_HOST:-}"
append_opt --spring.data.redis.password "${SPRING_DATA_REDIS_PASSWORD:-}"
append_opt --spring.data.redis.port "${SPRING_DATA_REDIS_PORT:-}"

JAVA_PID=""
if [ -z "${SPRING_DATASOURCE_DRUID_URL:-}" ]; then
  echo "[start.sh] 警告：未设置 SPRING_DATASOURCE_DRUID_URL，Java 后端不启动，仅提供静态页面（接口将 502）。" >&2
else
  java -jar /app/xiaozhi-api.jar "${JAVA_ARGS[@]}" &
  JAVA_PID=$!
  sleep 3
  if ! kill -0 "$JAVA_PID" 2>/dev/null; then
    echo "[start.sh] 警告：Java 后端启动后立即退出，请检查数据库/Redis 环境变量是否正确。" >&2
    JAVA_PID=""
  fi
fi

cleanup() {
  if [ -n "$JAVA_PID" ]; then
    kill "$JAVA_PID" 2>/dev/null
  fi
}
trap cleanup TERM INT

nginx -g 'daemon off;'

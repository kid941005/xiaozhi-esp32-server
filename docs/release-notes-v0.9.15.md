# v0.9.15

本版修复**智控台（web）镜像启动脚本**的一处健壮性缺陷，并改善容器内后端启动失败时的可见性。无应用代码、数据库或接口变更。

## 修复：环境变量缺失时智控台后端静默退出

`docs/docker/start.sh` 原实现无条件把所有 Spring 参数拼进启动命令：

```bash
--spring.data.redis.port=${SPRING_DATA_REDIS_PORT}
```

当 `SPRING_DATA_REDIS_PORT` 等变量未提供时，参数会变成空值（`--spring.data.redis.port=`），Spring 在类型转换阶段直接退出：

```
failed to convert java.lang.String to int
(caused by java.lang.IllegalArgumentException: A null value cannot be assigned to a primitive type)
```

因为同一容器里的 Nginx 仍在前台运行，容器看起来是 Up、`/` 也返回 200 和「智控台」页面，但所有 `/xiaozhi/**` 接口都是 502 —— 属于「假健康」状态，很难排查。

修复后：

- 启动参数改为数组，**仅在环境变量非空时追加**，不再产生 `--key=` 空值。
- 未设置 `SPRING_DATASOURCE_DRUID_URL` 时明确打印警告：只提供静态页面，接口将 502。
- Java 进程启动后 3 秒内退出时打印警告，提示检查数据库/Redis 环境变量。
- 容器收到 TERM/INT 时清理 Java 子进程。

## 验证

- 镜像实测（v0.9.14 的 web 镜像，配置正确的 DB/Redis 环境变量）：`/` 200 + 标题「智控台」，`/xiaozhi/user/pub-config` 200 并返回完整 JSON（Liquibase 建表、sys_params 正常读取），确认镜像本身工作正常。
- 新 `start.sh` 用 stub 覆盖 4 组场景验证：无环境变量、全量环境变量、缺 redis 端口、Java 立即退出；`bash -n` 通过。
- 沿用 v0.9.13 应用测试结果：Python 352 passed / 5 skipped，Java Tests run 211 / Failures 0 / BUILD SUCCESS（本版无应用代码变更）。

## 升级注意

- 无破坏性变更、无数据库迁移。
- 使用 `docker-compose_all.yml` 且已正确设置 `SPRING_DATASOURCE_DRUID_*` / `SPRING_DATA_REDIS_*` 的部署，行为不变。
- 若你之前遇到「智控台页面能开但接口全 502」，本版镜像仍然是同样的环境变量要求；请确认容器环境变量齐全，本版只是把失败原因显式打印出来而不是静默。

## 包含的提交

- `7e0972a6` fix(docker): web 镜像启动脚本仅在环境变量非空时传参，避免 Spring 因空值退出而 Nginx 假健康

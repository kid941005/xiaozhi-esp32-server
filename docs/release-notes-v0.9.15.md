# v0.9.15

本版修复**智控台（web）镜像启动脚本**的一处健壮性缺陷，并改善容器内后端启动失败时的可见性。无应用代码、数据库或接口变更。

## 镜像

| 镜像地址 | 说明 |
|---|---|
| `kid941005/xiaozhi-esp32-server:v0.9.15` | Docker Hub（public，无需登录），服务端固定版本，建议用于生产部署与回滚 |
| `kid941005/xiaozhi-esp32-server:latest` | Docker Hub（public），服务端跟随最近一次发布，当前等同 `v0.9.15` |
| `kid941005/xiaozhi-esp32-server:web_0.9.15` | Docker Hub（public），智控台（前端 + manager-api）固定版本 |
| `kid941005/xiaozhi-esp32-server:web_latest` | Docker Hub（public），智控台跟随最近一次发布 |
| `ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.15` | GHCR（public，无需登录），服务端固定版本 |
| `ghcr.io/kid941005/xiaozhi-esp32-server:latest` | GHCR（public，无需登录），服务端跟随最近一次发布，当前等同 `v0.9.15` |
| `ghcr.io/kid941005/xiaozhi-esp32-server:web_0.9.15` | GHCR（public），智控台固定版本（多架构 amd64 + arm64） |
| `ghcr.io/kid941005/xiaozhi-esp32-server:web_latest` | GHCR（public），智控台跟随最近一次发布（多架构） |

镜像 digest（同一提交、不同构建环境，内容等价）：
- Docker Hub 服务端：`sha256:565fa7c786379f72773c32fdce7f718d4b28017c26a3d83047dec66949c77bdf`（linux/amd64，压缩约 3.5 GB / 解压 10.8 GB）
- GHCR 服务端：`sha256:565fa7c786379f72773c32fdce7f718d4b28017c26a3d83047dec66949c77bdf`（linux/amd64，10.8 GB）
- Docker Hub 智控台：`sha256:e8d9b512fb0e69db1bb1653727c49a479723af5f3ba7278df872ab1c04e620cb`（linux/amd64）
- GHCR 智控台：`sha256:67150269225b9719b402d6a844904986b18c91f87a64e7b4ba758edaec977b5d`（多架构 index，amd64 + arm64）

拉取与使用：

```bash
# 服务端（public，可直接拉取）
docker pull kid941005/xiaozhi-esp32-server:v0.9.15
docker pull ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.15          # GHCR 备用

# 智控台（public，可直接拉取）
docker pull kid941005/xiaozhi-esp32-server:web_0.9.15
docker pull ghcr.io/kid941005/xiaozhi-esp32-server:web_0.9.15   # GHCR 备用（多架构）
```

在 `docker-compose.yml` 中替换对应服务的 `image` 即可，例如：

```yaml
services:
  xiaozhi-esp32-server:
    image: kid941005/xiaozhi-esp32-server:v0.9.15            # Docker Hub
    # image: ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.15  # GHCR 备用
  manager-web:
    image: kid941005/xiaozhi-esp32-server:web_0.9.15        # Docker Hub（智控台）
```

> Docker Hub 与 GHCR 上的镜像均为 **public**，可直接拉取、无需登录。若 GHCR 仍报 `unauthorized` / `denied`，多半是本地缓存了旧的私有凭据：先 `docker logout ghcr.io` 再重试。

> 服务端镜像由流水线 [`.github/workflows/dockerhub-image.yml`](.github/workflows/dockerhub-image.yml) 构建：推送 `v*.*.*` 标签或手动触发时，一次构建同时发布到 GHCR 与 Docker Hub。

> 智控台 web 镜像同样由该流水线构建并推送到 Docker Hub；GHCR 上的 web 镜像（多架构 amd64 + arm64）由 [`.github/workflows/docker-image.yml`](.github/workflows/docker-image.yml) 发布，两者标签格式均为 `web_<版本>`。

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
- 启动时不再写死 JAR 文件名，改为解析 `/app/*-api.jar`（构建产物名含仓库名，写死会因文件名不符导致 `Unable to access jarfile`）。

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
- fix(docker): 启动脚本按 `/app/*-api.jar` 解析 JAR 路径

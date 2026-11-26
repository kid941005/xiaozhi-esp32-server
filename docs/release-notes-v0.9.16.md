# v0.9.16

本版是**部署配置加固**：一键安装脚本不再指向上游仓库，仓库内置的 all-in-one compose 把 MySQL 固定到 8.0。无应用代码、接口或数据库结构变更。

## 镜像

（本小节由发布脚本在镜像构建完成后自动填充）

## 变更

### 1. 一键安装脚本改用本 fork 的镜像与 compose 地址

`docker-setup.sh` 原来指向上游 `xinnan-tech`：

- 升级时删除的镜像列表（:162-165）写的是 `ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:server_latest|web_latest`
- 升级/全新安装时下载配置（:186-187、:344-345）从 `raw.githubusercontent.com/xinnan-tech/...` 拉 `docker-compose_all.yml` 与 `config_from_api.yaml`

后果：用该脚本部署本 fork，会把 `/opt/xiaozhi-server/docker-compose_all.yml` 覆盖成上游版本并拉上游镜像 —— 本 fork 的安全加固（H1–H10、MCP 客户端加固）与 `202611241200.sql`（飞牛音乐网关插件元数据 / `sys_params`）随之丢失。

现在全部改为 `kid941005`：镜像为 `ghcr.io/kid941005/xiaozhi-esp32-server:server_latest` / `:web_latest`，配置从本 fork 的 `main` 下载（保留 `ghfast.top` 加速前缀）。

### 2. 仓库 all-in-one compose 的 MySQL 固定到 8.0

`main/xiaozhi-server/docker-compose_all.yml` 的 `image: mysql:latest` → `mysql:8.0`，与 `deploy/` 三套模板（`mysql:8.0`）一致。避免 `latest` 跨大版本漂移导致 Liquibase changelog 与 mysql-connector-j 行为不一致。

## 验证

- `sh -n docker-setup.sh` 通过；脚本内 `xinnan-tech` / `nju.edu.cn` 残留为 0 处。
- `docker compose -f main/xiaozhi-server/docker-compose_all.yml config` → exit 0，解析出的镜像为 `ghcr.io/kid941005/xiaozhi-esp32-server:server_latest`、`mysql:8.0`、`redis:8.0`、`...:web_latest`。
- 本 fork 的四个下载地址实测 HTTP 200（`raw.githubusercontent.com/kid941005/...` 直连与经 `ghfast.top` 均可）。
- 沿用 v0.9.15 的应用测试结果：Python 352 passed / 5 skipped，Java Tests run 211 / Failures 0 / BUILD SUCCESS（本版无应用代码变更）。

## 升级注意

- 无破坏性变更、无数据库迁移。
- 只有「用 `docker-setup.sh` 新装或升级」才会下载到本版 compose（脚本从 GitHub `main` 获取），已有部署升级镜像不受影响。
- 数据卷若由更高 MySQL 主版本初始化，回退到 8.0 前请先备份（MySQL 不支持就地降级）；一直在 `mysql:8.0` 上初始化的数据卷不受影响。

## 包含的提交

- `9ea5bf79` fix(deploy): mysql 固定 8.0，一键脚本改用本 fork 镜像与 compose 地址

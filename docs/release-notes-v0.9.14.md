# v0.9.14

本版为**发布流水线增强**：Docker Hub 现在同时提供服务端与智控台（web）镜像，两条镜像流水线一次性发布同一版本的四个镜像实体，并同步更新 README 与 Release 说明的镜像表。

## 镜像

| 镜像地址 | 说明 |
|---|---|
| `kid941005/xiaozhi-esp32-server:v0.9.14` | Docker Hub（public，无需登录），服务端固定版本，建议用于生产部署与回滚 |
| `kid941005/xiaozhi-esp32-server:latest` | Docker Hub（public），服务端跟随最近一次发布，当前等同 `v0.9.14` |
| `kid941005/xiaozhi-esp32-server:web_0.9.14` | Docker Hub（public），智控台（前端 + manager-api）固定版本 |
| `kid941005/xiaozhi-esp32-server:web_latest` | Docker Hub（public），智控台跟随最近一次发布 |
| `ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.14` | GHCR（public，无需登录），服务端固定版本 |
| `ghcr.io/kid941005/xiaozhi-esp32-server:latest` | GHCR（public，无需登录），服务端跟随最近一次发布，当前等同 `v0.9.14` |
| `ghcr.io/kid941005/xiaozhi-esp32-server:web_0.9.14` | GHCR（public），智控台固定版本（多架构 amd64 + arm64） |
| `ghcr.io/kid941005/xiaozhi-esp32-server:web_latest` | GHCR（public），智控台跟随最近一次发布（多架构） |

镜像 digest（同一提交、不同构建环境，内容等价）：
- Docker Hub 服务端：`sha256:4ea6ef3b469eb4b0849b0ac14bab44bafe8ea8e62581da72926d517612937ae1`（linux/amd64，压缩约 3.5 GB / 解压 10.8 GB）
- GHCR 服务端：`sha256:4ea6ef3b469eb4b0849b0ac14bab44bafe8ea8e62581da72926d517612937ae1`（linux/amd64，10.8 GB）
- Docker Hub 智控台：`sha256:12ad6fb509a6ad2e262a1dddedce7c9be8ef809e7f95fb3203957063fc24efa9`（linux/amd64）
- GHCR 智控台：`sha256:3ba9abfb3800e8218f945416fb1aa2ebfc2114cc5324d390e44419bd531b485b`（多架构 index，amd64 + arm64）

拉取与使用：

```bash
# 服务端（public，可直接拉取）
docker pull kid941005/xiaozhi-esp32-server:v0.9.14
docker pull ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.14          # GHCR 备用

# 智控台（public，可直接拉取）
docker pull kid941005/xiaozhi-esp32-server:web_0.9.14
docker pull ghcr.io/kid941005/xiaozhi-esp32-server:web_0.9.14   # GHCR 备用（多架构）
```

在 `docker-compose.yml` 中替换对应服务的 `image` 即可，例如：

```yaml
services:
  xiaozhi-esp32-server:
    image: kid941005/xiaozhi-esp32-server:v0.9.14            # Docker Hub
    # image: ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.14  # GHCR 备用
  manager-web:
    image: kid941005/xiaozhi-esp32-server:web_0.9.14        # Docker Hub（智控台）
```

> Docker Hub 与 GHCR 上的镜像均为 **public**，可直接拉取、无需登录。若 GHCR 仍报 `unauthorized` / `denied`，多半是本地缓存了旧的私有凭据：先 `docker logout ghcr.io` 再重试。

> 服务端镜像由流水线 [`.github/workflows/dockerhub-image.yml`](.github/workflows/dockerhub-image.yml) 构建：推送 `v*.*.*` 标签或手动触发时，一次构建同时发布到 GHCR 与 Docker Hub。

> 智控台 web 镜像同样由该流水线构建并推送到 Docker Hub；GHCR 上的 web 镜像（多架构 amd64 + arm64）由 [`.github/workflows/docker-image.yml`](.github/workflows/docker-image.yml) 发布，两者标签格式均为 `web_<版本>`。

## 流水线：Docker Hub 同步发布智控台镜像

- `.github/workflows/dockerhub-image.yml` 新增 `publish-web` job：构建 `Dockerfile-web`（Node 构建 manager-web 前端 + Maven 打包 manager-api + Nginx，端口 8002），推送到 Docker Hub，标签为 `web_<版本>` / `web_latest`。
- 该 job 有意只推 Docker Hub：GHCR 的 `web_<版本>` 由 `.github/workflows/docker-image.yml` 以多架构（amd64 + arm64）发布，避免两个流水线写同一 tag 互相覆盖。
- 服务端镜像行为不变：同一 job 同时推 GHCR 与 Docker Hub（linux/amd64）。
- 未配置 `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` 时 web job 降级为只构建、不推送，并在日志与 Step Summary 中告警，流水线不失败。

## 发布脚本：镜像表自动带智控台

- `scripts/release/update_image_docs.py`：镜像表新增 Docker Hub / GHCR 的 `web_<版本>`、`web_latest` 两行（共 8 行），digest 段新增「Docker Hub 智控台」与「GHCR 智控台（多架构 index）」，拉取示例补充智控台命令与 compose 片段。
- 今后执行 `bash scripts/release/update_image_docs.sh <版本> --notes docs/release-notes-<版本>.md` 即自动写入服务端 + 智控台 4 个 digest，无需手改。

## 测试

- 本版仅改动 CI 配置与发布脚本/文档，无应用代码变更；沿用 v0.9.13 的验证结果：Python 352 passed / 5 skipped，Java Tests run 211 / Failures 0 / BUILD SUCCESS。
- 流水线已在 v0.9.13 实跑验证：`Publish Images (GHCR + Docker Hub)` 两个 job（server / web）均 success，Docker Hub 新增 `web_0.9.13`、`web_latest`（digest `sha256:5fbbe935eae293e3b85d0b7659975261e817104c96366a17468c599c6556a9a5`）。

## 升级注意

- 无破坏性变更、无数据库迁移、无应用代码变更。
- 使用智控台的部署可直接改拉 Docker Hub 的 `kid941005/xiaozhi-esp32-server:web_<版本>`，无需再登录 GHCR；仍可继续用 GHCR 多架构版本（arm64 设备必须用 GHCR）。

## 包含的提交

- `721e95e7` ci(dockerhub): web 智控台镜像同步构建并推送
- `5ad56416` ci(dockerhub): web 镜像改推 Docker Hub，避免与 GHCR 多架构 tag 冲突
- `20e819a5` docs(release): 镜像表补充 Docker Hub 智控台镜像
- `d3ae920e` docs(release): 补充智控台镜像拉取示例与流水线说明

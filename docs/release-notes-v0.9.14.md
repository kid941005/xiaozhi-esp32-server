# v0.9.14

本版为**发布流水线增强**：Docker Hub 现在同时提供服务端与智控台（web）镜像，两条镜像流水线一次性发布同一版本的四个镜像实体，并同步更新 README 与 Release 说明的镜像表。

## 镜像

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

# v0.9.13

本版聚焦 **MCP 接入点客户端加固** 与 **构建期版本号注入**，并合并上游最新修复（TTS 数字断句 #3553、配置注释修正）。

## 镜像

| 镜像地址 | 说明 |
|---|---|
| `kid941005/xiaozhi-esp32-server:v0.9.13` | Docker Hub（public，无需登录），服务端固定版本，建议用于生产部署与回滚 |
| `kid941005/xiaozhi-esp32-server:latest` | Docker Hub（public），服务端跟随最近一次发布，当前等同 `v0.9.13` |
| `kid941005/xiaozhi-esp32-server:web_0.9.13` | Docker Hub（public），智控台（前端 + manager-api）固定版本 |
| `kid941005/xiaozhi-esp32-server:web_latest` | Docker Hub（public），智控台跟随最近一次发布 |
| `ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.13` | GHCR（public，无需登录），服务端固定版本 |
| `ghcr.io/kid941005/xiaozhi-esp32-server:latest` | GHCR（public，无需登录），服务端跟随最近一次发布，当前等同 `v0.9.13` |
| `ghcr.io/kid941005/xiaozhi-esp32-server:web_0.9.13` | GHCR（public），智控台固定版本（多架构 amd64 + arm64） |
| `ghcr.io/kid941005/xiaozhi-esp32-server:web_latest` | GHCR（public），智控台跟随最近一次发布（多架构） |

镜像 digest（同一提交、不同构建环境，内容等价）：
- Docker Hub 服务端：`sha256:10a05c92bd29daac088784ce7ac9297f64fd2dd9314edddd5918e195b7700f1e`（linux/amd64，压缩约 3.5 GB / 解压 10.8 GB）
- GHCR 服务端：`sha256:10a05c92bd29daac088784ce7ac9297f64fd2dd9314edddd5918e195b7700f1e`（linux/amd64，10.8 GB）
- Docker Hub 智控台：`sha256:5fbbe935eae293e3b85d0b7659975261e817104c96366a17468c599c6556a9a5`（linux/amd64）
- GHCR 智控台：`sha256:1e75916af7fdcf845b03cae5b5dcc2aa1904d40611340c9c3213b3f68235c72a`（多架构 index，amd64 + arm64）

拉取与使用：

```bash
# Docker Hub（public，可直接拉取）
docker pull kid941005/xiaozhi-esp32-server:v0.9.13

# GHCR（public，可直接拉取）
docker pull ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.13
```

在 `docker-compose.yml` 中把 server 服务的 `image` 换成上述地址即可，例如：

```yaml
services:
  xiaozhi-esp32-server:
    image: kid941005/xiaozhi-esp32-server:v0.9.13            # Docker Hub
    # image: ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.13  # GHCR 备用
```

> Docker Hub 与 GHCR 上的镜像均为 **public**，可直接拉取、无需登录。若 GHCR 仍报 `unauthorized` / `denied`，多半是本地缓存了旧的私有凭据：先 `docker logout ghcr.io` 再重试。

> 镜像由 GitHub Actions 流水线 [`.github/workflows/dockerhub-image.yml`](.github/workflows/dockerhub-image.yml) 构建：推送 `v*.*.*` 标签或手动触发时，一次构建同时发布到 GHCR 与 Docker Hub（同一组标签）。

## MCP 接入点客户端加固

此前主干只做裸 `websockets.connect(url)`：断线后等待中的工具调用会一直挂到超时，且没有重连；MCP 服务返回未知 action 时还会因枚举索引报错、把英文动作名直接念给用户。本次移植并保留主干新特性（speaker 透传、meta 负载）后落地：

- **连接参数**：`max_size=16MB`、`ping_interval=20s`、`ping_timeout=20s`、`open_timeout=15s`。
- **断线唤醒**：新增 `fail_all_call_results()`，连接断开时清空等待队列并给未完成调用抛 `RuntimeError`，不再干挂 30 秒。
- **自动重连**：监听器退出后按指数退避（1s 起、最长 600s、带随机抖动）重连，成功后替换 `conn.mcp_endpoint_client` 并刷新工具缓存；主动 `close()` 后不再重连。重连任务持有强引用，避免被 GC 回收。
- **结果处理**：只接受协议 Action 枚举内的 action，未知/缺失 action 回退给大模型生成自然语言；`response` 非字符串自动转字符串；`ValueError` → 「未找到对应的 MCP 工具。」，其它异常 → 「调用 MCP 工具失败，请稍后再试。」，不外泄内部异常文本。
- **发送失败**：清理 pending future 并抛可读的 `发送 MCP 工具调用失败：…`。
- 新增 `tests/core/providers/tools/test_mcp_endpoint_hardening.py`（16 例）；文档 [`docs/mcp-endpoint-integration.md`](docs/mcp-endpoint-integration.md) 增加「客户端加固说明」。

## 版本号构建注入

- `config/logger.py` 的 `SERVER_VERSION` 改为读取环境变量：`(os.environ.get("APP_VERSION") or "").strip() or "dev"`，不再硬编码 `0.9.8`。
- `Dockerfile-server` 新增 `ARG APP_VERSION=dev` / `ENV APP_VERSION`；两条镜像流水线均把版本号作为 build-arg 传入（Docker Hub 流水线取 tag 去掉 `v` 前缀）。
- 效果：启动日志中的版本号与镜像 tag 一致；本地直接运行未注入时显示 `dev`。

## 合并上游 main（f35a2900）

- 合并上游 4 个提交，其中 `f35a2900 fix(tts): 数字中的逗号和冒号不再被当成断句 (#3553)` 与本地此前的实现重合：双方各写了一份 `_is_numeric_separator`，合并时保留上游 `_NUMERIC_SEPARATORS` 版（覆盖半角 `:`），删除本地重复常量与方法；测试用例取双方并集（36 例）。
- 同时合入上游 `c5c4fc40` 的 websocket 配置注释拼写修正。
- 合并后与上游关系：**落后 0 / 领先 44**。

## 测试

- Python：`bash scripts/run_tests.sh python -k "not test_tts_text_to_speak_writes_file"` → **352 passed, 5 skipped, 1 deselected**
- Java：`bash scripts/run_tests.sh java` → **Tests run: 211, Failures: 0, Errors: 0, Skipped: 0, BUILD SUCCESS**（含集成守卫 DeviceTest 2 / ModelConfigPersistenceTest 3 / loginControllerTest 3）

## 升级注意

- 无破坏性变更、无数据库迁移。
- MCP 接入点加固为内置行为，无需改配置；若你的 MCP 服务端会在长连接上返回非标准 action 名，现在会走大模型自然语言回复而不是报错，属预期变化。
- 镜像启动日志版本号需使用本版及以后的镜像才会显示正确版本（旧镜像仍是硬编码 0.9.8）。

## 包含的提交

- `7753f4cb` merge: 合并上游 main（f35a2900）
- `afadc61d` fix(mcp-endpoint): 加固 MCP 接入点客户端
- `7a3119b5` feat(logging): 应用版本号改为构建注入 APP_VERSION
- `cd9a1884` chore(config): fnmusic_gateway 默认关闭
- `1d77ecab` docs(release): v0.9.12 镜像表与 digest

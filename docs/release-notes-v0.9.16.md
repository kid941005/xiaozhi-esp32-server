# v0.9.16

本版包含两部分：**部署配置加固**（一键安装脚本改用本 fork 的镜像与配置地址、all-in-one compose 的 MySQL 固定 8.0），以及**合并上游 8 个提交**（TTS 分句切分与 Markdown 清理修复、WebSocket ping 心跳保活文档）。无数据库结构变更。

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

### 3. 合并上游 8 个提交（`upstream/main` = `242a7019`）

- `362252f1` 分句循环切分，切分结果不再依赖分片粒度；移除未使用的 `tts_stop_request`（`tts/base.py`、`tts/index_stream.py`、`tts/minimax_httpstream.py`）
- `cccccc64d` Markdown 清理保留标识符与乘号、剥离残留标记；句点取最早的合法句末（`tts/base.py`、`core/utils/tts.py`）
- `5c3e1d8a` fix(tts): 清理 Markdown 斜体时保留标识符和乘号（#3554）
- `134e280f` / `248895ed` 新增 WebSocket ping 心跳保活说明与 FAQ 链接（纯文档）
- 合并提交 `242a7019`、`a4186e0e`、`7b017a25`

冲突处理（2 处）：

| 文件 | 处理 |
|---|---|
| `main/xiaozhi-server/core/utils/tts.py` | 运行时代码取上游实现；**并保留本 fork 的路径锚定修复**——`create_instance` 改为以 `__file__` 解析 `core/providers/tts`，避免依赖进程工作目录（取纯上游会让该加固回退） |
| `tests/core/utils/test_markdown_cleaner.py` | 取并集：上游 11 个用例 + 本 fork 的参数化用例（9 组） |

## 验证

- `sh -n docker-setup.sh` 通过；脚本内 `xinnan-tech` / `nju.edu.cn` 残留为 0 处。
- `docker compose -f main/xiaozhi-server/docker-compose_all.yml config` → exit 0，解析出的镜像为 `ghcr.io/kid941005/xiaozhi-esp32-server:server_latest`、`mysql:8.0`、`redis:8.0`、`...:web_latest`。
- 本 fork 的四个下载地址实测 HTTP 200（`raw.githubusercontent.com/kid941005/...` 直连与经 `ghfast.top` 均可）。
- 合并后 Python 全量：**431 passed / 5 skipped / 1 deselected**（合并前基线 352 passed；增量来自上游新增测试与并集用例）。
- 冲突相关用例单独复跑：`test_markdown_cleaner.py` + `test_quote_safe_segment.py` → 124 passed；`test_provider_path_anchor.py` → 2 passed。
- 本版无 Java 改动，沿用 v0.9.15 的 Java 结果：Tests run 211 / Failures 0 / BUILD SUCCESS。

## 升级注意

- 无破坏性变更、无数据库迁移。
- TTS 侧行为有上游修复带来的变化：分句不再依赖分片粒度、Markdown 斜体/粗体清理更保守（标识符下划线与乘号会被保留）。语音播报的断句与文本可能与旧版略有差异。
- 只有「用 `docker-setup.sh` 新装或升级」才会下载到本版 compose（脚本从 GitHub `main` 获取），已有部署升级镜像不受影响。
- 数据卷若由更高 MySQL 主版本初始化，回退到 8.0 前请先备份（MySQL 不支持就地降级）；一直在 `mysql:8.0` 上初始化的数据卷不受影响。

## 包含的提交

- `9ea5bf79` fix(deploy): mysql 固定 8.0，一键脚本改用本 fork 镜像与 compose 地址
- `e006b176` merge: 合并上游 8 个提交（TTS 分句与 Markdown 清理、WebSocket ping 文档）
- 上游侧：`242a7019`、`a4186e0e`、`7b017a25`、`362252f1`、`cccccc64d`、`5c3e1d8a`、`134e280f`、`248895ed`

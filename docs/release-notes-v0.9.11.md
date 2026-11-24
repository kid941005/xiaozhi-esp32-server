# v0.9.11

本版是 v0.9.10 之后的功能补充，内容为**语音切歌**：让"切歌 / 下一首 / 上一首"这类说法真正生效，并兼容 ASR 的同音误识别。

## 镜像

| 镜像地址 | 说明 |
|---|---|
| `kid941005/xiaozhi-esp32-server:v0.9.11` | Docker Hub（public，无需登录），固定版本，建议用于生产部署与回滚 |
| `kid941005/xiaozhi-esp32-server:latest` | Docker Hub（public），跟随最近一次发布，当前等同 `v0.9.11` |
| `ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.11` | GHCR（public，无需登录），固定版本 |
| `ghcr.io/kid941005/xiaozhi-esp32-server:latest` | GHCR（public，无需登录），跟随最近一次发布，当前等同 `v0.9.11` |

镜像 digest（同一提交、不同构建环境，内容等价）：
- Docker Hub：`sha256:c18711c9c802ccc5102fe08657d69830e021b9926ae3ae8cf15601f9d7636f99`（linux/amd64，压缩 3.3 GB / 解压 10.8 GB）
- GHCR：`sha256:c18711c9c802ccc5102fe08657d69830e021b9926ae3ae8cf15601f9d7636f99`（linux/amd64，10.8 GB）

拉取与使用：

```bash
# Docker Hub（public，可直接拉取）
docker pull kid941005/xiaozhi-esp32-server:v0.9.11

# GHCR（public，可直接拉取）
docker pull ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.11
```

在 `docker-compose.yml` 中把 server 服务的 `image` 换成上述地址即可，例如：

```yaml
services:
  xiaozhi-esp32-server:
    image: kid941005/xiaozhi-esp32-server:v0.9.11            # Docker Hub
    # image: ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.11  # GHCR 备用
```

> Docker Hub 与 GHCR 上的镜像均为 **public**，可直接拉取、无需登录。若 GHCR 仍报 `unauthorized` / `denied`，多半是本地缓存了旧的私有凭据：先 `docker logout ghcr.io` 再重试。

> 镜像由 GitHub Actions 流水线 [`.github/workflows/dockerhub-image.yml`](.github/workflows/dockerhub-image.yml) 构建：推送 `v*.*.*` 标签或手动触发时，一次构建同时发布到 GHCR 与 Docker Hub（同一组标签）。

## 新增：语音切歌（切歌 / 下一首 / 上一首）

此前 `play_music` 只有"播放音乐 / 播放指定歌名"，没有"切歌"这个概念，所以用户说"切歌"时模型只能闲聊（甚至把同音词理解成"切割"）。

- `play_music` 新增 `action` 参数（`play` | `next` | `previous`），函数描述里明确写了"切歌、下一首、换一首、换首歌、不要这首 → next"、"上一首、前一首 → previous"，`function_call` 与 `intent_llm` 两种模式都能命中。
- 每个连接维护独立播放状态（歌单、当前歌、索引）：`next`/`previous` 在歌单内前后移动、首尾循环；切歌前先停掉设备端当前音频（`tts stop` + 清空待推队列），不会两首歌叠着放。
- 新增同音归一 `normalize_music_text()`，在意图识别前把 `切割 / 切个(歌) / 下一曲 / 前一首` 等归一为 `切歌 / 下一首 / 上一首`（长词优先，避免"切个歌 → 切歌歌"），解决"听成切割就只聊天不切歌"。
- 使用前提：`music_dir` 下有 ≥2 个音频文件；仅 1 首时在同一首循环。

## 测试与 CI

- Python：`bash scripts/run_tests.sh python -k "not test_tts_text_to_speak_writes_file"` → **300 passed, 5 skipped, 1 deselected**（v0.9.10 为 292，新增 8 例：切歌换曲、上一首回退、空歌单提示、同音归一表）。
- 新增测试文件 `main/xiaozhi-server/tests/plugins_func/test_play_music_control.py`。
- 同步修复 CI：`scripts/run_tests.sh` 在写临时配置前 `mkdir -p data`，修复全新 checkout 下 Tests workflow 的 Python job 失败（v0.9.10 已含）。

## 升级注意

- 无配置变更、无数据迁移；直接替换镜像即可。
- 若之前靠"播放指定歌名"换歌，现在也可以直接说"切歌/下一首"。
- `auth.strict_ota` 仍默认 `true`（v0.9.10 起），老固件不满足三选一放行条件时需临时设为 `false`。

## 包含的提交

- `16d1f686` feat(music): play_music 支持切歌/上一首，并归一常见同音误识别
- `f5b6d967` fix(ci): run_tests.sh 先建 data 目录，修复全新 checkout 下 python job 失败

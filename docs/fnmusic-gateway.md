# 飞牛音乐网关接入（fnmusic_gateway）

把小智后端接到自建的飞牛音乐网关（fnmusic-gateway），让语音助手播放 NAS 音乐库里的音乐，
支持歌单、歌手、专辑、收藏、整库随机，以及单曲循环 / 列表循环，并通过设备端工具真实播放。

## 1. 前置条件

- 已部署 fnmusic-gateway，并能访问其 `GET /api/play` 与 `GET /api/status`。
- 设备固件支持 `self.music.play_url` / `self.music.stop` 工具（v2.6.0 及以上实测可用）。
- 设备播放期间会断开 WebSocket 语音通道并关闭 ASR，只能靠唤醒词或服务端 `fnmusic_stop` 打断。

## 2. 配置

单模块模式（直接改 `main/xiaozhi-server/config.yaml`）：

```yaml
plugins:
  fnmusic_gateway:
    base_url: "http://192.168.50.100:8766"  # 网关地址，留空表示不启用
    enabled: true
    timeout: 10
    quality: ""                              # 留空用网关默认音质
    device_tool: "self.music.play_url"
    stop_tool: "self.music.stop"

Intent:
  function_call:
    functions:
      - fnmusic_gateway   # 加载本模块后即注册 fnmusic_play / next / previous / stop
```

智控台模式：在「智能体管理 → 插件」里勾选「飞牛音乐网关」，填写网关地址即可
（默认值来自 `sys_params` 的 `plugins.fnmusic_gateway.*`）。

## 3. 工具

| 工具 | 说明 |
| --- | --- |
| `fnmusic_play` | 按歌名/歌手/专辑/歌单播放；`scope=library` 整库随机；`repeat=one\|all\|off` |
| `fnmusic_next` | 下一首（仅在本插件播放歌单/音乐库后可用，按 index 重新请求网关） |
| `fnmusic_previous` | 上一首 |
| `fnmusic_stop` | 停止播放 |

中文口令（“单曲循环”“列表循环”“随机播放音乐库”）会被归一化成网关参数。
本地 `music` 目录的播放仍由 `play_music` 工具负责，两者描述已区分。

## 4. 测试

```bash
cd main/xiaozhi-server
bash scripts/run_tests.sh -k fnmusic -q
```

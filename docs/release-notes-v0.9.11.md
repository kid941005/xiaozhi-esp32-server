# v0.9.11

本版是 v0.9.10 之后的功能补充，内容为**语音切歌**：让"切歌 / 下一首 / 上一首"这类说法真正生效，并兼容 ASR 的同音误识别。

## 镜像

<!-- IMAGES:PLACEHOLDER -->

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

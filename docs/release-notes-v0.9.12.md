# v0.9.12

本版聚焦**插件机制的健壮性与启动开销**，并新增飞牛音乐网关接入、默认关闭内置音乐/Home Assistant 插件，同时修复全仓库审计发现的 3 处缺陷。

## 镜像

| 镜像地址 | 说明 |
|---|---|
| `kid941005/xiaozhi-esp32-server:v0.9.12` | Docker Hub（public，无需登录），固定版本，建议用于生产部署与回滚 |
| `kid941005/xiaozhi-esp32-server:latest` | Docker Hub（public），跟随最近一次发布，当前等同 `v0.9.12` |
| `ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.12` | GHCR（public，无需登录），固定版本 |
| `ghcr.io/kid941005/xiaozhi-esp32-server:latest` | GHCR（public，无需登录），跟随最近一次发布，当前等同 `v0.9.12` |

镜像 digest（同一提交、不同构建环境，内容等价）：
- Docker Hub：`sha256:74140138e34d92a827a1403cccb906b54c8929f74dbc6279df9706a644ff006d`（linux/amd64，压缩 3.3 GB / 解压 10.8 GB）
- GHCR：`sha256:74140138e34d92a827a1403cccb906b54c8929f74dbc6279df9706a644ff006d`（linux/amd64，10.8 GB）

拉取与使用：

```bash
# Docker Hub（public，可直接拉取）
docker pull kid941005/xiaozhi-esp32-server:v0.9.12

# GHCR（public，可直接拉取）
docker pull ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.12
```

在 `docker-compose.yml` 中把 server 服务的 `image` 换成上述地址即可，例如：

```yaml
services:
  xiaozhi-esp32-server:
    image: kid941005/xiaozhi-esp32-server:v0.9.12            # Docker Hub
    # image: ghcr.io/kid941005/xiaozhi-esp32-server:v0.9.12  # GHCR 备用
```

> Docker Hub 与 GHCR 上的镜像均为 **public**，可直接拉取、无需登录。若 GHCR 仍报 `unauthorized` / `denied`，多半是本地缓存了旧的私有凭据：先 `docker logout ghcr.io` 再重试。

> 镜像由 GitHub Actions 流水线 [`.github/workflows/dockerhub-image.yml`](.github/workflows/dockerhub-image.yml) 构建：推送 `v*.*.*` 标签或手动触发时，一次构建同时发布到 GHCR 与 Docker Hub（同一组标签）。

## 插件机制：源码索引 + 按需导入

此前 `core/connection.py` 在模块加载阶段就 `auto_import_modules("plugins_func.functions")` 全量 import 目录下所有插件，无论是否启用。这带来两个问题：启动时执行全部插件代码；且 `auto_import_modules` 没有异常隔离，任一插件语法/导入错误会让所有工具（含自建 MCP 接入点）一起不可用。

- `plugins_func/loadplugins.py` 新增源码索引：只读 `*.py` 源码用正则抓取 `@register_function` 名称（支持多行装饰器），不 import 子模块。
- 新增 `ensure_plugins_loaded()` / `import_plugin_module()` / `auto_import_modules_soft()`：按配置中的函数名或模块名只导入对应模块；单个模块失败被隔离并记录 `插件模块加载失败: <module>: <error>`，不影响其它工具。
- `ServerPluginExecutor.get_tools()` 改为「必要函数（handle_exit_intent / get_lunar）+ 配置函数」按需加载后再展开模块名。
- 实测索引 13 个模块 / 17 个函数；未启用的 `play_music`、`hass_state` 不再被导入、不占工具表、不消耗提示词 token。

## 新增：飞牛音乐网关插件（fnmusic_gateway）

- 新增 `plugins_func/functions/fnmusic_gateway.py`，4 个工具：`fnmusic_play` / `fnmusic_next` / `fnmusic_previous` / `fnmusic_stop`，对接自建网关 HTTP API（`/api/play`），支持音乐库随机（`scope=library&shuffle=1`）与 `repeat=off|one|all` 循环，中文口令（单曲循环/列表循环/不循环）自动归一。
- 播放通过设备端 `self.music.play_url` 下发（`self.music.stop` 停止），网关返回的相对直链自动拼成绝对地址；URL 超过 2048 字符时拒绝并提示。
- 新增配置项 `plugins.fnmusic_gateway`（base_url / enabled / timeout / quality / device_tool / stop_tool）；智控台插件列表新增「飞牛音乐网关」（Liquibase `202611241200.sql`）。
- 注意：固件需提供 `self.music.play_url` / `self.music.stop`（v2.6.0 实测可用）；设备拉流后语音通道会断开，播放期间需用唤醒词打断或由服务端调用停止。

## 默认禁用内置音乐与 Home Assistant 插件

- `config.yaml` 的 `Intent.function_call.functions` 与 `intent_llm.functions` 均移除 `play_music`；`fnmusic_gateway` / `hass_state` / `hass_play_music` 保持注释，按需自行开启或由智控台勾选下发。
- 影响：未勾选时插件不进工具表也不会被调用；音乐与家居能力改走自建 MCP 服务。已在智控台勾选过的智能体会下发 plugins 映射并重算函数列表，不受影响。
- 附带修复：`function_call` 模式下音乐指令的同音词纠正（切割/切个 → 切歌）此前只在意图识别路径生效，现在收到语音转写后即归一。

## 修复：全仓库审计 3 项

- digital-human 前端 MCP 工具「删除」按钮失效：容器未设 id，且内联 `onclick="uiController.removeMCPTool(...)"` 依赖未挂到 window 的模块作用域变量，点击必然 ReferenceError。已设置 `toolDiv.id` 并改用 `addEventListener`。
- manager-mobile：服务器地址探测请求不存在的 `/api/ping`（必然 404，地址校验永远失败），改为匿名真实端点 `/user/pub-config`。
- manager-web：删除无调用方、后端也无路由的死代码 `user.saveDeviceConfig`（`PUT /user/configDevice/{id}`）。
- 审计中「移动端固件类型字典 403」经核查为误报：`Oauth2Realm` 给所有已登录用户授予 `sys:role:normal`，普通用户可正常访问。

## 测试

- Python：`bash scripts/run_tests.sh python -k "not test_tts_text_to_speak_writes_file"` → **327 passed, 5 skipped, 1 deselected**
- Java：`bash scripts/run_tests.sh java` → **Tests run: 211, Failures: 0, Errors: 0, Skipped: 0, BUILD SUCCESS**（含集成测试守卫 DeviceTest 2 / ModelConfigPersistenceTest 3 / loginControllerTest 3）
- 前端：manager-web `npm test` → contract 10/10、vitest 70/70；manager-mobile `npm run test:snapshot` → 21/21。
- 新增测试：`tests/plugins_func/test_fnmusic_gateway.py`（14 例）、`tests/plugins_func/test_lazy_plugin_loading.py`（9 例）、`main/digital-human/tests/ui_mcp_tool.test.mjs`（2 例）、`manager-mobile/src/pages/settings/settingsServerProbe.test.mjs`（1 例）。

## 升级注意

- 若此前依赖内置 `play_music` 或 Home Assistant 插件：需在 `config.yaml` Intent functions 中重新加入，或在智控台勾选；也可改用自建 MCP 服务。
- `auth.strict_ota` 仍默认 `true`；老固件不满足白名单/有效凭证/首次自举三选一时需临时设为 `false`。
- 无破坏性迁移；`202611241200.sql` 仅新增插件元数据与参数。

## 包含的提交

- `6bda9f9f` feat(plugins): 接入飞牛音乐网关（fnmusic_gateway）
- `e3fcdb1f` feat(manager-api): 智控台插件列表新增飞牛音乐网关
- `6f1e43dd` fix(asr): function_call 模式下音乐指令同音词纠错生效
- `9e83e644` chore(config): 禁用内置 play_music 与 Home Assistant 插件
- `30874fe2` perf(plugins): 插件改为源码索引 + 按需导入
- `fb1152a1` docs(config): 修正 Intent 段默认插件注释
- `8726433a` fix: 修复全仓库审计发现的 3 处缺陷
